"""Source-bound drawing decisions and checks against the saved presentation.

The host authors semantic decisions; this module checks identity, coverage and
observable output.  Neither a declared method nor an action log is proof of
visual quality or of an editor operation.
"""

from collections import defaultdict
from pathlib import Path

from lxml import etree as E

from . import VERSION
from .common import ROOT, digest, identity, read_json, safe_path
from .inspect import check as inspect_saved, inventory, xml
from .mathml import NS
from .scene import validate as validate_scene
from .source_analysis import contract_gaps, type_render_route, validate as validate_analysis


REPRESENTATIONS = {"native", "photo", "raster_candidate", "hybrid"}
TEXTURE_ROLES = {"semantic_mark", "material_texture", "decorative_texture", "none"}
OPERATIONS = {"build", "render", "inspect", "native_edit", "raster_compare", "complete_hidden", "measure"}
NATIVE_KINDS = {"text", "shape", "group", "connector", "bezier", "path", "trace", "equation", "table"}
MAX_PLAN_DETAIL_SHAPES = 200000  # Resource guard only; actual editor timing remains required.


def _acyclic(edges, label):
    children = defaultdict(list)
    for before, after in edges:
        children[before].append(after)
    active, done = set(), set()

    def visit(node):
        if node in active:
            raise ValueError(label + " cycle")
        if node in done:
            return
        active.add(node)
        for child in children[node]:
            visit(child)
        active.remove(node)
        done.add(node)

    for node in list(children):
        visit(node)


def compile_plan(analysis, scene, decisions, base):
    """Compile explicit, independently observed decisions into a frozen plan."""
    validate_scene(scene, base)
    checked = validate_analysis(analysis, base, scene)
    if decisions.get("schema_version") != "drawing-decisions-1":
        raise ValueError("Unknown drawing decision schema")
    if decisions.get("author", {}).get("kind") not in ("host_model", "human"):
        raise ValueError("Drawing decisions need a real host/human author")
    if decisions.get("source_analysis_hash") != identity(analysis):
        raise ValueError("Drawing decisions refer to stale source observations")
    if decisions.get("scene_hash") != identity(scene):
        raise ValueError("Drawing decisions refer to stale Scene")
    if type(decisions.get("revision")) is not int or decisions["revision"] < 0:
        raise ValueError("Plan revision must be a nonnegative integer")
    budget = decisions.get("budget", {})
    if not all(type(budget.get(k)) is int and budget[k] > 0 for k in ("seconds", "candidates")):
        raise ValueError("A finite positive drawing budget is required")
    analysis_nodes = checked["nodes"]
    source_gaps={node_id:contract_gaps(node,checked['children'].get(node_id,[]),
                                       analysis.get('relations',[]))
                 for node_id,node in analysis_nodes.items()}
    source_gaps={node_id:gaps for node_id,gaps in source_gaps.items() if gaps}
    if source_gaps:
        raise ValueError('Observed type contracts must be completed before drawing: '+
                         ', '.join(f'{node_id}({len(gaps)})' for node_id,gaps in sorted(source_gaps.items())))
    selected = decisions.get("nodes", [])
    chosen = {x.get("id"): x for x in selected}
    if len(chosen) != len(selected) or set(chosen) != set(analysis_nodes):
        raise ValueError("Drawing decisions must cover every observed semantic node exactly once")
    objects = {o["id"]: o for o in scene["objects"]}
    type_routes={card['id']:set(card['applies']['render_types'])
                 for card in read_json(ROOT/'config/contracts.json')['cards']
                 if card['axis']=='object_type'}
    for node_id,node in analysis_nodes.items():
        for render_id in node.get('render_ids',[]):
            item=objects[render_id]
            if type_render_route(node,item,type_routes[node['type']],analysis) is None:
                raise ValueError('Source type/render route mismatch before drawing: '+
                                 node_id+' / '+render_id+' / '+item['render_type'])
    family_representations = defaultdict(set)
    nodes = []
    for node_id, source_node in analysis_nodes.items():
        choice = chosen[node_id]
        from .appearance import drawing_policy
        appearance = drawing_policy(choice, source_node)
        representation = choice.get("representation")
        texture = choice.get("texture_role")
        family = choice.get("family_id")
        if representation not in REPRESENTATIONS or texture not in TEXTURE_ROLES or not isinstance(family, str) or not family.strip():
            raise ValueError("Explicit representation, texture role and family are required: " + node_id)
        detail_limit = choice.get('max_detail_shapes')
        if detail_limit is not None and (type(detail_limit) is not int
                                         or not 1 <= detail_limit <= MAX_PLAN_DETAIL_SHAPES):
            raise ValueError('Native detail limit must be a positive bounded integer: ' + node_id)
        if source_node["status"] == "unresolved" and representation in ("raster_candidate", "hybrid"):
            raise ValueError("Unresolved semantics cannot silently authorize a raster route")
        if texture == "semantic_mark" and representation != "native":
            raise ValueError("Semantic marks require native construction: " + node_id)
        if source_node.get("scientific_content") is True or source_node["role"] in ("R3", "R4"):
            if representation != "native":
                raise ValueError("Scientific content requires native construction: " + node_id)
        if representation in ("raster_candidate", "hybrid") and not choice.get("raster_reason"):
            raise ValueError("Raster route needs a scoped reason: " + node_id)
        semantic_class = source_node["semantic_class"].lower().replace("-", "_")
        if ("road" in semantic_class or "callout" in semantic_class or
                source_node.get("continuous_outline")) and representation != "native":
            raise ValueError("Observed road/continuous outline must use native geometry: " + node_id)
        if representation == "native" and any(objects[r]["render_type"] not in NATIVE_KINDS for r in source_node.get("render_ids", [])):
            raise ValueError("Native promise conflicts with Scene representation: " + node_id)
        if representation == "photo" and any(objects[r]["render_type"] != "photo" for r in source_node.get("render_ids", [])):
            raise ValueError("Photo declaration conflicts with Scene representation: " + node_id)
        if any(objects[r]["render_type"] == "photo" and
               objects[r]["semantic_type"] in ("environment_asset", "illustration_asset")
               for r in source_node.get("render_ids", [])) and representation not in ("raster_candidate", "hybrid"):
            raise ValueError("Complex-scene raster requires the measured native-first exception: " + node_id)
        family_representations[family].add(representation)
        if source_node["status"] == "observed" and not choice.get("observation_note"):
            raise ValueError("Observed node lacks a source-specific drawing decision: " + node_id)
        nodes.append({"id": node_id, "parent": source_node.get("parent"), "family_id": family,
                      "source_evidence_refs": source_node["evidence_refs"], "render_ids": source_node.get("render_ids", []),
                      "natural_parts": checked["children"].get(node_id, []), "representation": representation,
                      "texture_role": texture, "raster_reason": choice.get("raster_reason"),
                      "observation_note": choice.get("observation_note"), "objective": choice.get("objective"),
                      "editable_parts": choice.get("editable_parts", []), "max_detail_shapes": choice.get("max_detail_shapes"),
                      **appearance})
    inconsistent = [family for family, values in family_representations.items() if len(values) > 1]
    if inconsistent:
        raise ValueError("Mixed native/raster/photo representation within semantic family: " + ", ".join(inconsistent))
    occlusion = []
    for relation in analysis.get("relations", []):
        if relation["type"] == "occludes":
            occlusion.append([relation["source"], relation["target"]])
        elif relation["type"] == "behind":
            occlusion.append([relation["target"], relation["source"]])
    _acyclic(occlusion, "Occlusion")
    actions = decisions.get("actions", [])
    action_ids = {a.get("id") for a in actions}
    if not actions or len(action_ids) != len(actions) or not all(isinstance(x, str) and x for x in action_ids):
        raise ValueError("Plan needs distinct concrete actions")
    covered = set()
    for action in actions:
        if action.get("operation") not in OPERATIONS:
            raise ValueError("Unsupported drawing operation")
        if not isinstance(action.get("targets"), list) or not action["targets"] or not set(action["targets"]) <= set(analysis_nodes):
            raise ValueError("Action needs known semantic targets")
        if not isinstance(action.get("depends_on"), list) or not set(action["depends_on"]) <= action_ids - {action["id"]}:
            raise ValueError("Invalid action dependency")
        if not action.get("expected_outputs") or not action.get("required_checks") or not action.get("on_failure"):
            raise ValueError("Action requires output, check and failure branch")
        covered.update(action["targets"])
    _acyclic([(d, a["id"]) for a in actions for d in a["depends_on"]], "Action dependency")
    if covered != set(analysis_nodes):
        raise ValueError("Required semantic nodes have no planned action")
    raster_nodes = {node["id"] for node in nodes if node["representation"] in ("raster_candidate", "hybrid")}
    compared = {target for action in actions if action["operation"] == "raster_compare"
                for target in action["targets"]}
    if raster_nodes - compared:
        raise ValueError("Each raster exception needs a frozen native-first comparison: " +
                         ", ".join(sorted(raster_nodes - compared)))
    objectives = decisions.get("objectives", {})
    if not objectives.get("profile_id") or not objectives.get("primary_metric") or not objectives.get("metrics"):
        raise ValueError("Input-specific objectives and profile are required")
    if objectives["primary_metric"] not in objectives["metrics"]:
        raise ValueError("Primary metric is absent from objective set")
    if objectives.get("calibration_status") not in ("CALIBRATED", "UNCALIBRATED"):
        raise ValueError("Metric calibration status must be explicit")
    plan = {"schema_version": "drawing-plan-1", "revision": decisions["revision"],
            "status": "PLAN_READY_NOT_EXECUTED", "author": decisions["author"],
            "binding": {"analysis_hash": identity(analysis), "scene_hash": identity(scene),
                        "source_hash": scene["source"]["sha256"], "profile_hash": scene["profile"]["sha256"],
                        "implementation_version": VERSION},
            "budget": budget, "nodes": nodes, "occlusion_front_to_back": occlusion,
            "scientific_relations": [r for r in analysis.get("relations", []) if r["type"] not in ("occludes", "behind", "contains", "part_of")],
            "actions": actions, "objectives": objectives}
    return plan


def validate_plan(plan, analysis, scene, base):
    """Revalidate identities and all non-output requirements after a revision."""
    if plan.get("schema_version") != "drawing-plan-1" or plan.get("binding", {}).get("analysis_hash") != identity(analysis) or plan["binding"].get("scene_hash") != identity(scene):
        raise ValueError("Drawing plan is stale or has an unknown schema")
    if plan["binding"].get("implementation_version") != VERSION:
        raise ValueError("Drawing plan was compiled for another implementation version")
    choices = {k: plan[k] for k in ("revision", "author", "budget", "actions", "objectives")}
    choices.update(schema_version="drawing-decisions-1", source_analysis_hash=identity(analysis),
                   scene_hash=identity(scene), nodes=[{k: n[k] for k in ("id", "family_id", "representation", "texture_role", "raster_reason", "observation_note", "objective", "editable_parts", "max_detail_shapes", "appearance_policy", "semantic_constraints", "target_reuse_inches") if k in n} for n in plan["nodes"]])
    rebuilt = compile_plan(analysis, scene, choices, base)
    if rebuilt != plan:
        raise ValueError("Drawing plan differs from compiled source decisions")
    return {"status": "VALID_NOT_EXECUTED", "nodes": len(plan["nodes"]), "actions": len(plan["actions"])}


def check_conformance(plan, analysis, scene, base, pptx, *, render_receipt=None, action_journal=None):
    """Check saved objects; report unexecuted or unverified actions explicitly."""
    validate_plan(plan, analysis, scene, base)
    pptx = Path(pptx)
    native = inspect_saved(scene, base, pptx)
    saved, duplicates = inventory(xml(pptx))
    findings = []
    def finding(scope, status, detail):
        findings.append({"scope": scope, "status": status, "detail": detail})
    finding("saved_structure", native["status"], "Fresh saved-package native check")
    if duplicates:
        finding("saved_names", "FAIL", duplicates)
    for node in plan["nodes"]:
        ids = node["render_ids"]
        if not ids:
            continue
        for render_id in ids:
            if render_id not in saved:
                finding(render_id, "FAIL", "Planned owner missing from saved PPT")
                continue
            item = saved[render_id]["node"]
            tag = E.QName(item).localname
            media = bool(item.xpath(".//a:blip", namespaces=NS))
            if node["representation"] == "native" and (tag == "pic" or media):
                finding(render_id, "FAIL", "Native owner contains a picture or embedded raster")
            elif node["representation"] == "photo" and tag != "pic":
                finding(render_id, "FAIL", "Declared photo is not a separate picture")
            elif node["representation"] in ("raster_candidate", "hybrid"):
                finding(render_id, "UNVERIFIED", "Raster exception needs a measured same-protocol candidate comparison")
            else:
                finding(render_id, "PASS", "Saved object matches the declared representation")
        limit = node.get('max_detail_shapes')
        if limit is not None:
            leaves = set()
            for render_id in ids:
                if render_id not in saved:
                    continue
                for element in saved[render_id]['node'].iter():
                    tag = E.QName(element)
                    if tag.namespace == NS['p'] and tag.localname in ('sp', 'cxnSp', 'pic', 'graphicFrame'):
                        leaves.add(id(element))
            finding('detail_budget:' + node['id'], 'PASS' if len(leaves) <= limit else 'FAIL',
                    {'saved_native_or_media_leaves': len(leaves), 'frozen_limit': limit})
    if render_receipt is None:
        finding("render", "UNVERIFIED", "No actual saved PPT render receipt")
    else:
        receipt = read_json(render_receipt)
        try:
            if receipt.get("backend") == "LibreOffice" or receipt.get("schema")=="presentation-backend-1.36.0":
                from .render import verify_alternative_render
                verified = verify_alternative_render(pptx, render_receipt)
            elif receipt.get("backend") == "PowerPoint":
                from .host_render import verify_render
                preview = Path(render_receipt).parent / "Final_preview.png"
                verified = verify_render(pptx, preview, receipt)
            else:
                raise ValueError("Unknown renderer backend")
        except (KeyError, OSError, ValueError) as exc:
            finding("render", "FAIL", "Render artifacts or observation failed verification: " + str(exc))
        else:
            finding("render", "PASS", "Saved PPT and fresh PDF rasterization agree; " + verified["scope"])
    journal = read_json(action_journal) if action_journal else None
    for action in plan["actions"]:
        operation = action["operation"]
        matches = [] if journal is None else [x for x in journal.get("operations", [])
                  if x.get("plan_hash") == identity(plan) and x.get("action_id") == action["id"]
                  and x.get("status") == "VERIFIED"]
        invalid = None
        if matches:
            from .action_journal import audit_verified
            try:
                for record in matches:
                    audit_verified(Path(action_journal).parent, record)
            except (KeyError, OSError, ValueError) as exc:
                invalid = str(exc)
        if invalid is not None:
            status, detail = "FAIL", "Action journal failed fresh verification: " + invalid
        elif not matches:
            status, detail = "UNVERIFIED", "No independently verified task-bound action receipt"
        elif operation in ("build", "inspect") and native["status"] != "PASS":
            status, detail = "FAIL", "Saved native package failed"
        elif operation == "build" and not any(x.get("outputs", {}).get("Candidate.pptx", {}).get("sha256") == digest(pptx) for x in matches):
            status, detail = "FAIL", "Verified build receipt belongs to another PPT"
        elif operation == "render" and next(x["status"] for x in findings if x["scope"] == "render") != "PASS":
            status, detail = "FAIL", "Actual render receipt failed"
        elif operation == "render" and not any(x.get("outputs", {}).get("render.json", {}).get("sha256") == digest(render_receipt) for x in matches):
            status, detail = "FAIL", "Verified action render receipt belongs to another rendering"
        elif operation == "native_edit" and not any(
                x.get('outputs', {}).get('Candidate.pptx', {}).get('sha256') == digest(pptx)
                for x in matches):
            status, detail = "UNVERIFIED", "Editor action saved another candidate; reconcile the selected PPT and Scene"
        elif operation == "native_edit":
            status, detail = "PASS", "Task-owned editor result, saved-product protection and action receipt match"
        elif operation == 'raster_compare':
            decisions = {x.get('checked_status') for x in matches}
            status = ('FAIL' if 'REJECTED_RASTER_EXCEPTION' in decisions else
                      'UNVERIFIED' if decisions != {'ELIGIBLE_FOR_SEMANTIC_AND_EDITOR_REVIEW'} else 'PASS')
            detail = 'Fresh same-protocol raster trial; eligibility still requires semantic and editor review'
        elif operation == 'complete_hidden':
            decisions = {x.get('checked_status') for x in matches}
            status = ('FAIL' if 'FAIL' in decisions else
                      'PASS' if decisions == {'PASS_COMPONENT_COMPLETION'} else 'UNVERIFIED')
            detail = 'Fresh hidden-only composition and component semantic review'
        elif operation == 'measure':
            status = 'PASS' if all(x.get('checked_status') == 'MEASURED_NOT_ACCEPTED' for x in matches) else 'FAIL'
            detail = 'Fixed-domain metrics recomputed; measurements do not confer visual acceptance'
        else:
            status, detail = "PASS", "Task-bound action, saved output and independent check match"
        finding("action:" + action["id"], status, detail)
    overall = "FAIL" if any(x["status"] == "FAIL" for x in findings) else "UNVERIFIED" if any(x["status"] == "UNVERIFIED" for x in findings) else "PASS"
    return {"status": overall, "scope": "saved representation and completed deterministic actions; not full visual or editor acceptance",
            "plan_hash": identity(plan), "scene_hash": identity(scene), "pptx_hash": digest(pptx),
            "render_receipt_hash": digest(render_receipt) if render_receipt else None,
            "findings": findings}
