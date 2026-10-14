"""Result-driven host loop with cumulative protection and transactional selection.

The host observes images and chooses a repair. This module never pretends to
see, generate, or judge an image. It supplies bounded work, protects previous
results, and keeps incomplete work distinct from a deliverable.
"""

import copy
import math
from pathlib import Path
import time

import numpy as np
from PIL import Image

from .common import digest, identity, read_json, safe_path
from .session import _atomic_json, _exhausted, _lock, _save, load
from .saved_ppt_diff import snapshot

ASSESSMENTS = ("source_coverage", "text_math_semantics", "layout_spacing",
               "clarity_texture", "complete_reusable_layers", "native_editability",
               "protected_content")
TERMINALS = {"ACCEPTED_DELIVERABLE", "STALLED_NOT_ACCEPTED",
             "PAUSED_RESOURCE_LIMIT", "BLOCKED_CAPABILITY"}


def _resource(work, ref):
    path = safe_path(work, ref["path"])
    if digest(path) != ref["sha256"]:
        raise ValueError("Visual loop input changed: " + ref["path"])
    return path


def _ref(work, path):
    path = Path(path).resolve()
    return {"path": path.relative_to(work).as_posix(), "sha256": digest(path)}


def _input(work, value):
    return safe_path(work, value)


def _record(work, ref):
    return read_json(_resource(work, ref)) if ref else None


def _state(work):
    value = read_json(work / "visual-loop.json")
    if value.get("schema_version") != "visual-loop-1":
        raise ValueError("Unsupported visual loop state")
    return value


def _save_state(work, state):
    state["revision"] += 1
    _atomic_json(work / "visual-loop.json", state)


def _box(roi, canvas):
    if (not isinstance(roi, list) or len(roi) != 4 or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in roi)):
        raise ValueError("Located source ROI must be finite xywh")
    x, y, w, h = roi
    if min(x, y) < 0 or min(w, h) <= 0 or x+w > canvas[0] or y+h > canvas[1]:
        raise ValueError("ROI outside source canvas")
    return roi


def _overlap(a, b):
    return a[0] < b[0]+b[2] and b[0] < a[0]+a[2] and a[1] < b[1]+b[3] and b[1] < a[1]+a[3]


def _rect(roi, canvas, size):
    x, y, w, h = roi
    sx, sy = size[0]/canvas[0], size[1]/canvas[1]
    return (math.floor(x*sx), math.floor(y*sy), math.ceil((x+w)*sx), math.ceil((y+h)*sy))


def _mask(work, spec, canvas, size):
    if spec.get("mask"):
        with Image.open(_resource(work, spec["mask"])) as image:
            data = np.asarray(image.convert("L"))
        if data.shape != (size[1], size[0]) or not set(np.unique(data)) <= {0, 255} or not data.any():
            raise ValueError("Protection mask must be nonempty binary at saved-render dimensions")
        result = data > 0
        bounds = np.zeros_like(result)
        l, t, r, b = _rect(spec["roi"], canvas, size)
        bounds[t:b, l:r] = True
        if np.any(result & ~bounds):
            raise ValueError("Protection mask exceeds declared ROI")
        return result
    result = np.zeros((size[1], size[0]), dtype=bool)
    l, t, r, b = _rect(spec["roi"], canvas, size)
    result[t:b, l:r] = True
    return result


def _product(obj):
    return {k: v for k, v in obj.items() if k not in ("versions", "locks")}


def _scopes(scene, plan):
    objects = {o["id"]: o for o in scene["objects"]}
    nodes = {n["id"]: n for n in plan.get("nodes", [])}
    scopes = {}
    for key in list(nodes) + [key for key in objects if key not in nodes]:
        todo = [key]; ids = set(); seen = set()
        while todo:
            current = todo.pop()
            if current in seen:
                continue
            seen.add(current)
            if current in nodes:
                ids.update(nodes[current].get("render_ids", []))
                todo.extend(n["id"] for n in nodes.values() if n.get("parent") == current)
            elif current in objects:
                ids.add(current)
            for oid in list(ids):
                ids.update(o["id"] for o in objects.values() if o.get("parent") == oid)
        # Include arbitrarily deep native descendants, without a recursion cap.
        while True:
            extra = {o["id"] for o in objects.values() if o.get("parent") in ids}
            if extra <= ids:
                break
            ids |= extra
        boxes = [objects[i]["bbox"] for i in ids if i in objects]
        if not boxes:
            continue
        left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
        right, bottom = max(b[0]+b[2] for b in boxes), max(b[1]+b[3] for b in boxes)
        width, height = scene["canvas"]["width"], scene["canvas"]["height"]
        left, top, right, bottom = max(0, left), max(0, top), min(width, right), min(height, bottom)
        if right <= left or bottom <= top:
            continue
        node = nodes.get(key, objects.get(key, {}))
        scopes[key] = {"ids": sorted(ids), "roi": [left, top, right-left, bottom-top],
                       "parent": node.get("parent"), "semantic": key in nodes,
                       "appearance_policy": node.get("appearance_policy", "source_faithful")}
    return scopes


def _incident(scene, ids):
    return [r for r in scene.get("relations", []) if r.get("source") in ids or r.get("target") in ids]


def _frame(receipt, size):
    return {k: receipt.get(k) for k in ("backend", "backend_version", "environment")} | {"size": list(size)}


def _protect(work, state, old, candidate, edit):
    """Product protection is part of selection, not a separate test campaign."""
    with Image.open(_resource(work, candidate["preview"])) as image:
        after = np.asarray(image.convert("RGBA"))
    faults = []
    scene = read_json(_resource(work, candidate["scene"]))
    objects = {o["id"]: o for o in scene["objects"]}
    for owner, anchor in state["frozen"].items():
        origin = _record(work, anchor["candidate"])
        if origin["frame"] != candidate["frame"]:
            faults.append("renderer_changed:" + owner); continue
        for key, value in anchor["saved_objects"].items():
            if candidate["saved"]["objects"].get(key) != value:
                faults.append("frozen_saved_object:" + key)
        for key, value in anchor["scene_objects"].items():
            if key not in objects or _product(objects[key]) != value:
                faults.append("frozen_scene_object:" + key)
        if _incident(scene, set(anchor["scene_objects"])) != anchor["relations"]:
            faults.append("frozen_relations:" + owner)
        with Image.open(_resource(work, origin["preview"])) as image:
            before = np.asarray(image.convert("RGBA"))
        mask = _mask(work, anchor, state["canvas"], (after.shape[1], after.shape[0]))
        if np.any(before[mask] != after[mask]):
            faults.append("frozen_pixels:" + owner)
    if old is None:
        return faults
    if old["frame"] != candidate["frame"]:
        return faults + ["renderer_or_dimensions_changed"]
    previous = read_json(_resource(work, old["scene"]))
    write = set(edit["write_objects"])
    for obj in previous["objects"]:
        if obj["id"] not in write and (obj["id"] not in objects or _product(obj) != _product(objects[obj["id"]])):
            faults.append("outside_scene_write_set:" + obj["id"])
    for key in ("canvas", "source", "prototypes"):
        if previous.get(key) != scene.get(key):
            faults.append("shared_scene:" + key)
    old_ids = {o["id"] for o in previous["objects"]}
    new_ids = set(objects) - old_ids
    relation_write = write | (new_ids if edit.get('allow_new_parts') else set())
    def untouched(relations):
        return [r for r in relations if r.get("source") not in relation_write and r.get("target") not in relation_write]
    if untouched(previous.get("relations", [])) != untouched(scene.get("relations", [])):
        faults.append("outside_write_relations")
    if new_ids and not edit.get("allow_new_parts"):
        faults.append("unplanned_new_parts")
    for oid in new_ids:
        x, y, w, h = objects[oid]["bbox"]; rx, ry, rw, rh = edit["roi"]
        if x < rx or y < ry or x+w > rx+rw or y+h > ry+rh:
            faults.append("new_part_outside_repair_roi:" + oid)
    allowed_paths = {key for key in old["saved"]["objects"] if key.rsplit("/", 1)[-1] in write}
    for key, value in old["saved"]["objects"].items():
        if key not in allowed_paths and candidate["saved"]["objects"].get(key) != value:
            faults.append("outside_ppt_write_set:" + key)
    for key in set(candidate['saved']['objects']) - set(old['saved']['objects']):
        if key.rsplit('/', 1)[-1] not in new_ids | write:
            faults.append('unmapped_new_saved_object:' + key)
    old_order = [k for k in old['order'] if k not in allowed_paths]
    protected_order_keys = set(old_order)
    retained_order = [k for k in candidate['order'] if k in protected_order_keys]
    if retained_order != old_order:
        faults.append('protected_layer_order_changed')
    if old["saved"]["slide_shells"] != candidate["saved"]["slide_shells"]:
        faults.append("slide_background_or_context_changed")
    theme = lambda saved: {k: v for k, v in saved["shared_parts"].items() if k.startswith("ppt/theme/")}
    if theme(old["saved"]) != theme(candidate["saved"]):
        faults.append("shared_theme_changed")
    with Image.open(_resource(work, old["preview"])) as image:
        before = np.asarray(image.convert("RGBA"))
    allowed = _mask(work, edit, state["canvas"], (after.shape[1], after.shape[0]))
    if np.any(before[~allowed] != after[~allowed]):
        faults.append("render_changed_outside_repair_roi")
    return sorted(set(faults))


def _charge(work):
    with _lock(work / ".session.lock"):
        session = load(work)
        if _exhausted(session, candidate=True):
            raise TimeoutError("PAUSED_RESOURCE_LIMIT")
        session["budget"]["candidates_used"] += 1
        _save(work, session)


def _register(work, state, request):
    if state.get("current"):
        raise ValueError("Observe or reject the pending candidate before registering another")
    selected = _record(work, state.get("selected"))
    edit = state.get("repair")
    if selected and not edit:
        raise ValueError("Declare the defect, write set and repair method first")
    scene_path, pptx, preview, receipt_path = [_input(work, request[k]) for k in ("scene", "pptx", "preview", "render_receipt")]
    scene, receipt = read_json(scene_path), read_json(receipt_path)
    plan_path = _input(work, request["plan"])
    plan = read_json(plan_path)
    if (scene["source"]["sha256"] != state["source"]["sha256"] or
            plan.get("binding", {}).get("scene_hash") != identity(scene) or
            plan.get("binding", {}).get("source_hash") != state["source"]["sha256"]):
        raise ValueError("Candidate plan/Scene must describe this source and saved revision")
    if receipt.get("pptx_hash") != digest(pptx) or receipt.get("preview_hash") != digest(preview) or not receipt.get("backend"):
        raise ValueError("Render must belong to the actual saved PPT")
    with Image.open(preview) as image:
        size = image.size
    key = identity({"pptx": digest(pptx), "preview": digest(preview), "scene": identity(scene)})[:24]
    if key in state["history"]:
        raise ValueError("Candidate already observed; change the hypothesis or inputs")
    candidate = {"id": key, "scene": _ref(work, scene_path), "pptx": _ref(work, pptx),
                 "preview": _ref(work, preview), "render_receipt": _ref(work, receipt_path),
                 "plan": _ref(work, plan_path), "frame": _frame(receipt, size),
                 "saved": snapshot(pptx), "scopes": _scopes(scene, plan),
                 "edit": edit, "reviews": {}, "base": state.get("selected")}
    candidate['order'] = list(candidate['saved']['objects'])
    faults = _protect(work, state, selected, candidate, edit)
    if faults:
        state["history"][key] = {"status": "REJECTED_PROTECTION", "faults": faults[:20]}
        state["repair"] = None
        state["status"] = "NEEDS_DIAGNOSIS"
        state["stalled_attempts"] += 1
        if state["stalled_attempts"] >= state["max_stalled_attempts"]:
            state.update(status="STALLED_NOT_ACCEPTED", stop_reason="Repeated protected-content violations; preserve the prior selection and revise the repair strategy")
        return {"status": "REJECTED_PROTECTION", "faults": faults[:20], "selected": state.get("selected")}
    if not selected:
        journal = read_json(work / 'actions.json') if (work / 'actions.json').exists() else {'operations': []}
        already_charged = any(item.get('candidate_slot_charged') and any(
            isinstance(v, dict) and v.get('sha256') == candidate['pptx']['sha256'] for v in item.get('outputs', {}).values())
            for item in journal['operations'])
        if not already_charged:
            _charge(work)
    from .review import prepare_loop_views
    prior_views = selected.get("views", []) if selected else []
    candidate["views"] = prepare_loop_views(work, scene_path, pptx, preview, candidate["scopes"],
                                             list(state["issues"].values()), key, prior_views)
    path = work / "visual-candidates" / (key + ".json")
    _atomic_json(path, candidate)
    state["current"] = _ref(work, path)
    state["status"] = "NEEDS_OBSERVATION"
    state["repair"] = None
    return _next(work, state)


def _freeze(work, state, candidate, ref, owners):
    scene = read_json(_resource(work, candidate["scene"]))
    objects = {o["id"]: o for o in scene["objects"]}
    for item in owners:
        owner = item["owner"]
        if owner in state["frozen"]:
            continue
        scope = candidate["scopes"].get(owner)
        if not scope or not item.get("note"):
            raise ValueError("Freeze a known, actually observed semantic owner with a reason")
        if any(i["status"] == "open" and _overlap(i["roi"], scope["roi"]) for i in state["issues"].values()):
            raise ValueError("Owner still intersects an unresolved defect")
        ids = set(scope["ids"])
        saved_paths = {key for key in candidate["saved"]["objects"] if key.rsplit("/", 1)[-1] in ids}
        if not saved_paths:
            raise ValueError("Frozen owner has no mapped saved PPT objects")
        # Ancestor transforms/styles are dependencies, not additional write grants.
        for oid in list(ids):
            parent = objects[oid].get("parent")
            while parent:
                ids.add(parent); parent = objects[parent].get("parent")
        paths = set(saved_paths)
        for path in saved_paths:
            parts = path.split("/")
            paths.update("/".join(parts[:n]) for n in range(2, len(parts)))
        anchor = {"candidate": ref, "roi": scope["roi"], "origin": "agent", "note": item["note"],
                  "scene_objects": {i: _product(objects[i]) for i in ids},
                  "saved_objects": {p: candidate["saved"]["objects"][p] for p in paths},
                  "relations": _incident(scene, ids)}
        if item.get("mask"):
            anchor["mask"] = item["mask"]
            _mask(work, anchor, state["canvas"], candidate["frame"]["size"])
        if item.get("origin") == "user":
            if not item.get("user_authorization"):
                raise ValueError("User-approved freeze needs the actual instruction")
            anchor.update(origin="user", user_authorization=item["user_authorization"])
        state["frozen"][owner] = anchor


def _observe(work, state, request):
    candidate = _record(work, state.get("current"))
    if not candidate or request.get("candidate_id") != candidate["id"]:
        raise ValueError("Observation must address the pending saved candidate")
    if request.get("observer", {}).get("kind") not in ("host_model", "human"):
        raise ValueError("Actual host or human visual observation is required")
    views = {v["id"]: v for v in candidate["views"]}
    for item in request.get("views", []):
        view = views.get(item.get("view_id"))
        if not view or item.get("status") not in ("satisfactory", "defect", "uncertain") or not item.get("note"):
            raise ValueError("Observation needs a located view, judgment and concrete note")
        for ref in (view["source"], view["candidate"]):
            _resource(work, ref)
        candidate["reviews"][view["id"]] = item
    # Persist review batches; no absent view becomes a pass.
    issues = copy.deepcopy(candidate.get("proposed_issues", state["issues"]))
    for finding in request.get("findings", []):
        item = copy.deepcopy(finding)
        if (not item.get("id") or not item.get("expected") or not item.get("actual") or
                not item.get("kind") or item.get("severity") not in ("critical", "major", "minor") or
                item.get("view_id") not in candidate["reviews"]):
            raise ValueError("Finding needs identity, expectation, actual defect, severity and observed view")
        _box(item["roi"], state["canvas"])
        item.update(status="open", candidate_id=candidate["id"])
        if item.get("owner") and item["owner"] not in candidate["scopes"]:
            raise ValueError("Use null owner for an unmapped source region")
        issues[item["id"]] = item
    for resolution in request.get("resolved", []):
        issue_id = resolution.get("id")
        if (issue_id not in issues or not candidate.get("edit") or
                issue_id not in candidate["edit"]["issues"] or not resolution.get("note") or
                resolution.get("view_id") not in candidate["reviews"] or
                candidate["reviews"][resolution["view_id"]]["status"] != "satisfactory"):
            raise ValueError("Close only repaired issues actually observed satisfactory in this candidate")
        issues[issue_id].update(status="resolved", resolution=resolution)
    candidate["proposed_issues"] = issues
    pending = [v["id"] for v in candidate["views"] if not v.get("reuse") and v["id"] not in candidate["reviews"]]
    for item in candidate["reviews"].values():
        if item["status"] in ("defect", "uncertain") and not any(
                i["view_id"] == item["view_id"] and i["status"] == "open" for i in issues.values()):
            pending.append(item["view_id"] + ":needs_located_finding")
    candidate_path = work / 'visual-candidates' / (candidate['id'] + '-observation-' + str(state['revision']+1) + '.json')
    if not request.get("complete"):
        _atomic_json(candidate_path, candidate)
        state["current"] = _ref(work, candidate_path)
        return {"status": "NEEDS_OBSERVATION", "pending": pending[:8]}
    if pending:
        raise ValueError("Unobserved or undiagnosed result views remain: " + repr(pending[:8]))
    assessment = request.get("assessment", {})
    if any(assessment.get(k, {}).get("status") not in ("satisfactory", "defect", "uncertain") or
           not assessment[k].get("note") for k in ASSESSMENTS):
        raise ValueError("Result assessment needs every delivery dimension and a concrete note")
    for dimension, item in assessment.items():
        if item.get("status") != "satisfactory" and not any(i["status"] == "open" for i in issues.values()):
            raise ValueError("Unsatisfactory assessment requires an actionable finding: " + dimension)
    candidate["assessment"] = assessment
    selected = _record(work, state.get("selected"))
    from .iteration import visual_working_selection
    decision = visual_working_selection(selected is not None, issues.values(), request.get('outcome'), request.get('improvement_note'))
    keep = decision['keep']
    for view in candidate["views"]:
        if view["id"] in candidate["reviews"]:
            view["review"] = candidate["reviews"][view["id"]]
    candidate["outcome"] = request.get("outcome", "initial")
    candidate["improvement_note"] = request.get("improvement_note")
    candidate['selection'] = decision
    _atomic_json(candidate_path, candidate)
    ref = _ref(work, candidate_path)
    if keep:
        state["selected"] = ref
        state["issues"] = issues
        state["stalled_attempts"] = 0
        owners = {item['owner']: item for item in request.get('satisfied_owners', [])}
        # Successful work is protected by default, not only when the host
        # remembers a second optional freeze command.
        for view in candidate['views']:
            owner = view.get('owner')
            if (view['kind'] not in ('module', 'bitmap_context') or owner not in candidate['scopes'] or
                    view.get('review', {}).get('status') != 'satisfactory'):
                continue
            scope = candidate['scopes'][owner]
            if not any(i['status'] == 'open' and _overlap(i['roi'], scope['roi']) for i in issues.values()):
                owners.setdefault(owner, {'owner': owner, 'note': view['review']['note']})
        for resolution in request.get('resolved', []):
            owner = issues[resolution['id']].get('owner')
            if owner in candidate['scopes'] and not any(i['status'] == 'open' and _overlap(i['roi'], candidate['scopes'][owner]['roi']) for i in issues.values()):
                owners.setdefault(owner, {'owner': owner, 'note': resolution['note']})
        _freeze(work, state, candidate, ref, list(owners.values()))
    else:
        state["stalled_attempts"] += 1
    state["history"][candidate["id"]] = {"status": "SELECTED_WORKING" if keep else "REJECTED_NO_IMPROVEMENT",
                                            "candidate": ref, "note": request.get("improvement_note")}
    state["current"] = None
    state["status"] = "NEEDS_DIAGNOSIS"
    if state['stalled_attempts'] >= state['max_stalled_attempts']:
        state.update(status='STALLED_NOT_ACCEPTED', stop_reason='Distinct repair attempts did not improve the observed result; substantive work remains')
    return _next(work, state)


def _plan_repair(work, state, request):
    candidate = _record(work, state.get("selected"))
    if not candidate or state.get("current") or state.get("repair"):
        raise ValueError("Repair needs one observed selection and no pending candidate/action")
    ids = request.get("issues", [])
    if not ids or any(i not in state["issues"] or state["issues"][i]["status"] != "open" for i in ids):
        raise ValueError("Repair must target open visual findings")
    if any(not request.get(k) for k in ("hypothesis", "method", "tool", "expected_change")):
        raise ValueError("Repair needs a cause, method, real tool and expected visual change")
    _box(request["roi"], state["canvas"])
    if any(not _overlap(state["issues"][i]["roi"], request["roi"]) for i in ids):
        raise ValueError("Repair ROI must address its findings")
    scene = read_json(_resource(work, candidate["scene"]))
    known = {o["id"] for o in scene["objects"]}
    write = set(request.get("write_objects", []))
    if not write <= known or (not write and not request.get("allow_new_parts")):
        raise ValueError("Declare existing write objects or explicit missing-part creation")
    for owner, anchor in state["frozen"].items():
        if write & set(anchor["scene_objects"]):
            raise ValueError("BLOCKED_FROZEN_CONFLICT: " + owner)
    signature = identity({k: request.get(k) for k in ("issues", "hypothesis", "method", "write_objects", "roi")})
    if signature in state["attempts"]:
        raise ValueError("This repair was already attempted; change the hypothesis or method")
    _charge(work)
    repair = copy.deepcopy(request)
    repair.update(signature=signature, base_candidate=candidate["id"],
                  protected_owners=list(state["frozen"]), status="READY_FOR_HOST_EXECUTION")
    folder = 'visual-work/' + signature[:24]
    repair['output_paths'] = {k: folder + '/' + name for k, name in
                              (('pptx', 'candidate.pptx'), ('scene', 'scene.json'),
                               ('plan', 'drawing-plan.json'), ('preview', 'preview.png'),
                               ('render_receipt', 'render.json'))}
    state["repair"] = repair
    state["attempts"].append(signature)
    state["status"] = "REPAIR_READY"
    return {"status": "REPAIR_READY", "repair": repair,
            "next": "Execute on a new candidate using existing native/picture/desktop tools; register the saved PPT and render"}


def _next(work, state):
    if state["status"] in TERMINALS:
        return {"status": state["status"], "selected": state.get("selected"), "reason": state.get("stop_reason"),
                'unresolved': [i for i in state['issues'].values() if i['status'] == 'open']}
    if state.get("current"):
        candidate = _record(work, state["current"])
        views = [v for v in candidate["views"] if not v.get("reuse") and v["id"] not in candidate["reviews"]]
        return {"status": "NEEDS_OBSERVATION", "candidate_id": candidate["id"], "views": views[:8],
                "remaining_views": len(views), "next": "View the paired images; describe unknown deficiencies, or record concrete satisfactory observations"}
    if state.get("repair"):
        repair = state['repair']
        existing = [k for k, path in repair['output_paths'].items() if _input(work, path).exists()]
        return {"status": "RECONCILE_REPAIR_OUTPUTS" if existing else "REPAIR_READY", "repair": repair,
                "existing_outputs": existing,
                "next": 'Register complete saved outputs or reconcile a partial save; never blindly repeat an uncertain tool edit' if existing else 'Execute the declared repair on a new candidate'}
    open_issues = [i for i in state["issues"].values() if i["status"] == "open"]
    if not state.get("selected"):
        return {"status": "DRAW_INITIAL", "next": "Use the input-specific plan, save and render, then register candidate"}
    if not open_issues:
        return {"status": "READY_TO_FINISH", "next": "finish applies the delivery exit to the actual latest observation"}
    if all(i['kind'] == 'polish' and i['severity'] == 'minor' for i in open_issues):
        return {'status': 'POLISH_DECISION', 'issues': open_issues,
                'next': 'Repair worthwhile polish, or finish with a concrete defer_polish reason for each item; do not generate an extra candidate just to stop'}
    if _exhausted(load(work), candidate=True):
        return {"status": "PAUSED_RESOURCE_LIMIT", "selected": state["selected"], "unresolved": open_issues}
    ranked = sorted(open_issues, key=lambda i: ({"critical": 0, "major": 1, "minor": 2}[i["severity"]], i["id"]))
    from .repair import visual_repair_brief
    selected = _record(work, state['selected'])
    return {"status": "NEEDS_DIAGNOSIS", "issue": ranked[0], "open_count": len(open_issues),
            'brief': visual_repair_brief(ranked[0], selected['scopes'], state['frozen']),
            'source': state['source'], 'selected_preview': selected['preview'],
            "frozen_owners": list(state["frozen"]), "stalled_attempts": state["stalled_attempts"],
            "next": "Diagnose one issue; declare minimal write set, method and expected change; missing owners return to source analysis"}


def next_step(workdir):
    work = Path(workdir).resolve()
    return _next(work, _state(work))


def accepted_output(workdir, pptx):
    work = Path(workdir).resolve()
    state = _state(work)
    if state['status'] != 'ACCEPTED_DELIVERABLE' or state.get('current') or state.get('repair'):
        raise ValueError('The visual loop has not reached its deliverable exit')
    selected = _record(work, state['selected'])
    for key in ('pptx', 'preview', 'scene', 'plan', 'render_receipt'):
        _resource(work, selected[key])
    if selected['pptx']['sha256'] != digest(pptx):
        raise ValueError('Delivery must use the actual selected visual-loop result')
    from .execution_contract import require_delivery
    require_delivery(state.get('runtime_task'),pptx)
    return {'status': 'VISUAL_LOOP_ACCEPTED', 'candidate_id': selected['id']}


def dispatch(workdir, operation, request):
    work = Path(workdir).resolve()
    with _lock(work / ".visual-loop.lock"):
        if operation == "start":
            if (work / "visual-loop.json").exists():
                return next_step(work)
            session = load(work)
            stall_limit = request.get('max_stalled_attempts', 3)
            if type(stall_limit) is not int or not 1 <= stall_limit <= 10:
                raise ValueError('Freeze a finite stagnation limit from 1 to 10 at task start')
            state = {"schema_version": "visual-loop-1", "revision": 0, "status": "DRAW_INITIAL",
                     "source": session["source"], "canvas": [session["source"]["width"], session["source"]["height"]],
                     "selected": None, "current": None, "repair": None, "issues": {}, "frozen": {},
                     "history": {}, "attempts": [], "reopened": [], "stalled_attempts": 0,
                     'max_stalled_attempts': stall_limit}
            _save_state(work, state)
            return _next(work, state)
        state = _state(work)
        if operation == "status":
            return _next(work, state)
        if state["status"] in TERMINALS:
            raise ValueError("Loop stopped; start a new authorized task rather than resetting its budget")
        if operation == "candidate":
            result = _register(work, state, request)
        elif operation == "observe":
            result = _observe(work, state, request)
        elif operation == "plan-repair":
            result = _plan_repair(work, state, request)
        elif operation == 'abandon-repair':
            if state.get('current') or not state.get('repair') or not request.get('reason'):
                raise ValueError('Abandon only a pending repair with a reason; completed outputs remain preserved')
            state['history']['abandoned:' + state['repair']['signature']] = {'reason': request['reason'], 'repair': state['repair']}
            state['repair'] = None
            state['status'] = 'NEEDS_DIAGNOSIS'
            result = _next(work, state)
        elif operation == "reopen":
            owner = request["owner"]; anchor = state["frozen"][owner]
            issue = state["issues"].get(request.get("issue_id"))
            if (state.get("current") or state.get("repair") or not issue or issue["status"] != "open" or
                    not _overlap(issue["roi"], anchor["roi"]) or not request.get("reason")):
                raise ValueError("Reopen requires a new located defect and no active writer")
            if anchor["origin"] == "user" and not request.get("user_authorization"):
                raise ValueError("User-approved scope needs a new actual user instruction")
            state["reopened"].append({"owner": owner, "anchor": anchor, "request": request})
            del state["frozen"][owner]
            result = _next(work, state)
        elif operation == "stop":
            if request.get("status") not in TERMINALS - {"ACCEPTED_DELIVERABLE"} or not request.get("reason"):
                raise ValueError("Explicit capability, resource or stalled reason is required")
            state.update(status=request["status"], stop_reason=request["reason"])
            result = _next(work, state)
        elif operation == "finish":
            candidate = _record(work, state.get("selected"))
            if not candidate or state.get("current") or state.get("repair"):
                raise ValueError("Finish needs one observed selection and no unfinished action")
            for key in ('pptx', 'preview', 'scene', 'render_receipt', 'plan'):
                _resource(work, candidate[key])
            from .execution_contract import require_delivery
            require_delivery(request.get('runtime_task'),_resource(work,candidate['pptx']))
            state['runtime_task']=str(Path(request['runtime_task']).resolve())
            if any(candidate.get("assessment", {}).get(k, {}).get("status") != "satisfactory" for k in ASSESSMENTS):
                raise ValueError("Result still has a substantive deficiency or uncertainty")
            for issue in state["issues"].values():
                if issue["status"] != "open":
                    continue
                reason = request.get("defer_polish", {}).get(issue["id"])
                if issue["severity"] != "minor" or issue["kind"] != "polish" or not reason:
                    raise ValueError("Unresolved substantive finding: " + issue["id"])
                issue.update(status="deferred_polish", reason=reason)
            state.update(status="ACCEPTED_DELIVERABLE", stop_reason="Current observed result meets task goals; no substantive unresolved finding")
            result = {"status": state["status"], "pptx": candidate["pptx"], "preview": candidate["preview"],
                      "best_scope": "best observed admissible working result, not a global optimum",
                      "remaining_polish": [i for i in state["issues"].values() if i["status"] == "deferred_polish"]}
        else:
            raise ValueError("Unknown visual-loop operation")
        _save_state(work, state)
        return result
