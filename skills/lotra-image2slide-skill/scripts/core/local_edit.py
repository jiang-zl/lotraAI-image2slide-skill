"""Strict leaf edits on an approved scene and immutable saved-PPT baseline.

An edit contract grants exactly the named scalar leaves. Dependency reads and
rechecks never add write permission. Saved-PPT and visual checks are separate
gates; this module cannot declare an Office operation or page fidelity PASS.
"""

import copy
from pathlib import Path

from .common import digest, identity, read_json, safe_path
from .dependencies import make_patch, plan as dependency_plan
from .scene import validate as validate_scene
from .state import patch_scene


LEAF_FIELDS = {"style", "content", "bbox"}
META_FIELDS = {"revision", "versions"}


def _assets(scene, base):
    """Bind all packaged source and object-local assets used by this Scene."""
    found = {}

    def walk(value, path):
        if isinstance(value, dict):
            if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
                file = safe_path(base, value["path"])
                actual = digest(file)
                if actual != value["sha256"]:
                    raise ValueError("Scene asset changed: " + path)
                found[path] = {"path": value["path"], "sha256": actual}
            for key, child in value.items():
                walk(child, path + "/" + str(key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, path + "/" + str(index))

    walk(scene, "scene")
    return found


def freeze_baseline(scene, base, pptx, preview, render_receipt, approval):
    """Record a user's accepted working version without manufacturing QA PASS."""
    validate_scene(scene, base)
    if approval.get("kind") != "user_confirmed" or not approval.get("statement"):
        raise ValueError("Approved baseline needs explicit user-confirmation evidence")
    pptx, preview, render_receipt = map(Path, (pptx, preview, render_receipt))
    receipt = read_json(render_receipt)
    if receipt.get("pptx_hash") != digest(pptx):
        raise ValueError("Baseline rendering is not for this saved PPT")
    if not preview.is_file() or not render_receipt.is_file():
        raise ValueError("Approved baseline requires actual saved preview and render receipt")
    if receipt.get("preview_hash") != digest(preview):
        raise ValueError("Baseline preview differs from the saved render receipt")
    if receipt.get("backend") == "LibreOffice" or receipt.get("schema")=="presentation-backend-1.36.0":
        from .render import verify_alternative_render
        verify_alternative_render(pptx, render_receipt)
    elif receipt.get("backend") == "PowerPoint":
        from .host_render import verify_render
        verify_render(pptx, preview, receipt)
    else:
        raise ValueError("Baseline needs a recognized, verified saved render")
    resources = _assets(scene, base)
    return {"schema_version": "approved-baseline-1", "status": "USER_CONFIRMED_NOT_FULL_QA",
            "approval": approval, "scene_hash": identity(scene), "pptx_hash": digest(pptx),
            "preview_hash": digest(preview), "render_receipt_hash": digest(render_receipt),
            "assets_hash": identity(resources), "assets": resources,
            "environment": receipt.get("environment") or receipt.get("current_environment") or {},
            "source_reference_hash": scene["source"]["sha256"],
            "protected_anchor_scene_hash": identity(scene)}


def _tokens(path):
    if not isinstance(path, str) or not path.startswith("/") or path.endswith("/"):
        raise ValueError("A concrete JSON pointer leaf is required")
    raw = path.split("/")[1:]
    if not raw or any(not token for token in raw):
        raise ValueError("Empty JSON pointer token")
    result = []
    for token in raw:
        decoded = token.replace("~1", "/").replace("~0", "~")
        if "~" in token.replace("~1", "").replace("~0", ""):
            raise ValueError("Invalid JSON pointer escape")
        result.append(decoded)
    if result[0] not in LEAF_FIELDS or len(result) < 2:
        raise ValueError("Only scalar leaves under content/style/bbox may be edited")
    return result


def _leaf(root, tokens):
    current = root
    for token in tokens:
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise ValueError("Leaf does not exist in approved Scene")
    if isinstance(current, (dict, list)):
        raise ValueError("Whole objects, maps and arrays cannot be replaced by a leaf edit")
    return current


def _put(root, tokens, value):
    parent = root
    for token in tokens[:-1]:
        parent = parent[int(token)] if isinstance(parent, list) else parent[token]
    last = tokens[-1]
    if isinstance(parent, list):
        parent[int(last)] = value
    else:
        parent[last] = value


def _product_differences(before, after, prefix=""):
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            if not prefix and key in META_FIELDS:
                continue
            if key not in before or key not in after:
                result.append(prefix + "/" + str(key))
            else:
                result.extend(_product_differences(before[key], after[key], prefix + "/" + str(key)))
        return result
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return [prefix]
        result = []
        for index, (old, new) in enumerate(zip(before, after)):
            result.extend(_product_differences(old, new, prefix + "/" + str(index)))
        return result
    return [] if type(before) is type(after) and before == after else [prefix]


def _by_id(scene):
    nodes = {o["id"]: o for o in scene["objects"]}
    if len(nodes) != len(scene["objects"]):
        raise ValueError("Duplicate semantic object identity")
    return nodes


def check_scene_protection(baseline_scene, candidate_scene, allowed):
    """Check all product leaves, including unlisted leaves on the target."""
    original, result = _by_id(baseline_scene), _by_id(candidate_scene)
    if set(original) != set(result):
        raise ValueError("Local edit changed the object inventory or stable IDs")
    differences = []
    for object_id in original:
        for path in _product_differences(original[object_id], result[object_id]):
            differences.append((object_id, path))
    for key in ("canvas", "source", "evidence", "profile", "relations", "prototypes"):
        if baseline_scene[key] != candidate_scene[key]:
            raise ValueError("Local edit changed shared Scene data: " + key)
    unauthorized = [item for item in differences if item not in allowed]
    if unauthorized:
        raise ValueError("Unapproved product changes: " + repr(unauthorized[:8]))
    return {"changed_leaves": [{"object_id": obj, "path": path} for obj, path in differences],
            "unapproved_changes": 0, "status": "PASS_SCENE_PRODUCT_ONLY"}


def prepare_leaf_edit(scene, base, baseline, current_pptx, contract, authorization):
    """Validate frozen baseline, apply exact leaves, and derive read/check scopes."""
    validate_scene(scene, base)
    if baseline.get("schema_version") != "approved-baseline-1" or contract.get("schema_version") != "local-edit-contract-1":
        raise ValueError("Unknown local-edit baseline or contract")
    approval = baseline.get("approval") or {}
    if (baseline.get("status") == "USER_CONFIRMED_NOT_FULL_QA"
            and (approval.get("kind") != "user_confirmed" or not approval.get("statement"))):
        raise ValueError("Local edit needs the user's accepted working baseline")
    if (baseline.get("status") == "SELECTED_FROM_USER_CONFIRMED_NOT_FULL_QA"
            and (approval.get("kind") != "inherited_from_user_confirmed"
                 or not approval.get("original_approved_baseline_hash"))):
        raise ValueError("Selected local edit lost its original user-approved anchor")
    if baseline.get("status") not in {"USER_CONFIRMED_NOT_FULL_QA",
                                      "SELECTED_FROM_USER_CONFIRMED_NOT_FULL_QA"}:
        raise ValueError("Local edit needs a user-approved working baseline")
    if contract.get("mode") != "local_edit" or contract.get("protect_unlisted_paths") is not True:
        raise ValueError("Local edit must protect every unlisted product path")
    binding = contract.get("base_bindings", {})
    expected = {"scene_hash": identity(scene), "pptx_hash": digest(current_pptx),
                "assets_hash": identity(_assets(scene, base))}
    if any(binding.get(key) != value or baseline.get(key) != value for key, value in expected.items()):
        raise ValueError("Stale Scene, PPT or asset binding; preserve external changes and reconcile a new baseline")
    if contract.get("baseline_id") != identity(baseline):
        raise ValueError("Edit refers to another approved baseline")
    if (authorization.get("schema_version") != "local-edit-authorization-1"
            or authorization.get("issuer") != "coordinator"
            or authorization.get("edit_id") != contract.get("edit_id")
            or authorization.get("baseline_id") != identity(baseline)
            or not authorization.get("user_intent_ref")
            or contract.get("authorization_hash") != identity(authorization)):
        raise ValueError("Local edit needs a separately frozen user-intent authorization")
    authorized = {(item.get("object_id"), item.get("path")) for item in authorization.get("allowed_paths", [])}
    if not authorized or len(authorized) != len(authorization["allowed_paths"]):
        raise ValueError("Authorization paths must be distinct and nonempty")
    writes = contract.get("writes", []) + contract.get("derived_writes", [])
    if not writes or not contract.get("intent"):
        raise ValueError("Local edit requires explicit intent and leaf writes")
    old = _by_id(scene)
    staged = copy.deepcopy(scene)
    updated = _by_id(staged)
    allowed = set()
    affected = set()
    transitions = []
    for change in writes:
        object_id, path = change.get("object_id"), change.get("path")
        if object_id not in old or change.get("op") != "replace":
            raise ValueError("Local edit needs an existing named object and replace operation")
        tokens = _tokens(path)
        key = (object_id, path)
        if key not in authorized:
            raise ValueError("Read or recheck scope does not grant write permission: " + repr(key))
        if key in allowed:
            raise ValueError("Duplicate or conflicting leaf edit")
        allowed.add(key)
        field = tokens[0]
        facet = {"style": "style", "content": "content", "bbox": "placement"}[field]
        if old[object_id]["locks"][facet]:
            raise ValueError("The requested leaf is locked")
        previous = _leaf(old[object_id], tokens)
        if "expected" not in change or type(previous) is not type(change["expected"]) or previous != change["expected"]:
            raise ValueError("Leaf old-value precondition failed")
        value = change.get("value")
        if isinstance(value, (dict, list)) or type(value) is not type(previous):
            raise ValueError("Leaf value must preserve its scalar type")
        _put(updated[object_id], tokens, value)
        transitions.append({"object_id": object_id, "path": path,
                            "expected": previous, "value": value})
        affected.add((object_id, field))
    operations = [{"object_id": object_id, "field": field,
                   "value": copy.deepcopy(updated[object_id][field])}
                  for object_id, field in sorted(affected)]
    grant = {"task_id": contract.get("edit_id") or "local-edit", "object_ids": sorted({x[0] for x in affected}),
             "allowed_fields": sorted({x[1] for x in affected}), "role": "geometry_worker",
             "max_translation_px": contract.get("max_translation_px", 0),
             "allow_uniform_scale": False}
    patch = make_patch(scene, operations, grant["task_id"], staged)
    candidate, invalidated = patch_scene(scene, patch, grant, base)
    protection = check_scene_protection(scene, candidate, allowed)
    for object_id, path in allowed:
        if (object_id, path) not in {(x["object_id"], x["path"]) for x in protection["changed_leaves"]}:
            raise ValueError("No-op leaf edit needs an explicit no-op workflow, not silent acceptance")
    impact = dependency_plan(scene, operations, candidate)
    from pptx import Presentation
    source_to_emu_scale = Presentation(current_pptx).slide_width / scene["canvas"]["width"]
    return candidate, {"schema_version": "local-edit-preparation-1", "status": "SCENE_CANDIDATE_NOT_ACCEPTED",
                       "contract_hash": identity(contract), "baseline_hash": identity(baseline),
                       "authorization_hash": identity(authorization),
                       "candidate_scene_hash": identity(candidate), "base_pptx_hash": expected["pptx_hash"],
                       "write_set": [{"object_id": obj, "path": path} for obj, path in sorted(allowed)],
                       "transitions": transitions,
                       "source_to_emu_scale": source_to_emu_scale,
                       "read_set": impact["read_facets"], "check_set": impact["checks"],
                       "protected_set": "all unlisted Scene product leaves plus frozen PPT/render anchors",
                       "old_new_regions": impact["regions"], "invalidated_objects": invalidated,
                       "scene_protection": protection}
