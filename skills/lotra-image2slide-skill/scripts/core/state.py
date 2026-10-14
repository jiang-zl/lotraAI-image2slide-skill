"""Versioned Scene transactions. Workers write candidates, never current state."""

import copy
import os
from pathlib import Path
import uuid
import jsonschema
from .common import ROOT, identity, read_json, write_json, writer
from .scene import validate, FACETS

FIELD_FACET = {"content": "content", "parent": "structure", "semantic_type": "content",
               "render_type": "structure", "style": "style", "bbox": "placement",
               "z_order":"placement","component":"structure"}


def closure(scene, targets):
    affected = set(targets)
    edges = []
    for o in scene["objects"]:
        if o.get("parent"):
            edges.append({o["id"], o["parent"]})
        if o["render_type"] == "connector":
            edges.extend([{o["id"], o["content"][field]} for field in ("source", "target","source_anchor_object","target_anchor_object") if o['content'].get(field)])
        if o.get("prototype_id"):
            edges.append({o["id"], o["prototype_id"]})
    for relation in scene["relations"]:
        edges.append({relation["source"], relation["target"]})
    while True:
        expanded = affected | set().union(*(e for e in edges if affected & e)) if edges else affected
        if expanded == affected:
            return affected
        affected = expanded


def patch_scene(scene, patch, grant, base):
    """Grant is supplied by the coordinator, separately from worker's patch."""
    try:
        jsonschema.validate(patch,read_json(ROOT/"schemas/patch.json"))
        jsonschema.validate(grant,read_json(ROOT/"schemas/grant.json"))
    except jsonschema.ValidationError as exc:
        raise ValueError("Invalid patch/grant contract: "+exc.message) from exc
    objects = validate(scene, base)
    if patch["task_id"] != grant["task_id"]:
        raise ValueError("Task authorization mismatch")
    scoped=patch.get('dependency_mode')=='field_spatial_v1'
    if not scoped and (patch["base_scene_revision"] != scene["revision"] or patch["base_scene_hash"] != identity(scene)):
        raise ValueError("Stale patch")
    if not patch["operations"]:
        raise ValueError("Empty patch")
    targets = {op["object_id"] for op in patch["operations"]}
    if not targets <= set(grant["object_ids"]):
        raise ValueError("Cross-object unauthorized patch")
    dependencies = set() if scoped else closure(scene, targets)
    new = copy.deepcopy(scene)
    updated = {o["id"]: o for o in new["objects"]}
    touched = set()
    for op in patch["operations"]:
        id, field = op["object_id"], op["field"]
        if field not in FIELD_FACET or field not in grant["allowed_fields"]:
            raise ValueError("Unauthorized field/path")
        facet = FIELD_FACET[field]
        if objects[id]["locks"][facet]:
            raise ValueError("Locked " + facet)
        if field == "parent":
            for parent_id in (objects[id].get("parent"), op["value"]):
                if parent_id is None:
                    continue
                if parent_id not in grant["object_ids"] or objects[parent_id]["locks"]["structure"]:
                    raise ValueError("Parent membership is locked or unauthorized")
                touched.add((parent_id, "structure"))
        if grant.get("role") == "global_layout" and field != "bbox":
            raise ValueError("Global layout cannot modify scientific content")
        if field == "bbox":
            if objects[id]["render_type"] == "group":
                raise ValueError("Group placement needs explicit descendant patch; implicit child edits forbidden")
            previous, value = objects[id]["bbox"], op["value"]
            if len(value) != 4:
                raise ValueError("Invalid bbox")
            dx, dy = abs(value[0]-previous[0]), abs(value[1]-previous[1])
            bound = grant.get("max_translation_px", 0)
            if dx > bound or dy > bound:
                raise ValueError("Layout displacement exceeds grant")
            if value[2:] != previous[2:]:
                if objects[id]["render_type"] == "equation" or not grant.get("allow_uniform_scale", False):
                    raise ValueError("Scaling not authorized")
                if abs(value[2]/previous[2]-value[3]/previous[3]) > 1e-9:
                    raise ValueError("Nonuniform scale forbidden")
        updated[id][field] = copy.deepcopy(op["value"])
        touched.add((id, facet))
    for id, facet in touched:
        updated[id]["versions"][facet] += 1
    new["revision"] += 1
    validate(new, base)
    if scoped:
        from .dependencies import plan
        p=plan(scene,patch['operations'],new)
        if patch.get('reference_hashes')!=p['reference_hashes'] or patch.get('dependency_signature')!=p['signature']:
            raise ValueError('Stale source, spatial or relationship dependency')
        expected={id:{f:objects[id]['versions'][f] for f in facets} for id,facets in p['read_facets'].items()}
        if patch.get('expected_facets')!=expected:raise ValueError('Stale or incomplete facet dependencies')
        dependencies=set(p['checks'])
    else:
        dependencies |= closure(new, targets)
        versions = {id: objects[id]["versions"] for id in dependencies if id in objects}
        if patch["expected_versions"] != versions:
            raise ValueError("Stale or incomplete dependency versions")
    return new, sorted(dependencies)


def initialize(directory, scene):
    directory = Path(directory)
    with writer(directory):
        if (directory / "current.json").exists():
            raise FileExistsError("State already initialized")
        revision = "rev-0-" + identity(scene)[:12]
        write_json(directory / revision / "scene.json", scene)
        write_json(directory / "current.json", {"revision_dir": revision, "scene_hash": identity(scene)})


def current(directory):
    directory = Path(directory)
    pointer = read_json(directory / "current.json")
    revision = pointer["revision_dir"]
    if "/" in revision or "\\" in revision or not revision.startswith("rev-"):
        raise ValueError("Unsafe state pointer")
    scene = read_json(directory / revision / "scene.json")
    if identity(scene) != pointer["scene_hash"]:
        raise ValueError("State changed outside transaction")
    return scene


def commit_patch(directory, patch, grant, base):
    directory = Path(directory)
    with writer(directory):
        old = current(directory)
        new, affected = patch_scene(old, patch, grant, base)
        name = f"rev-{new['revision']}-{identity(new)[:12]}"
        pending = directory / (".pending-" + uuid.uuid4().hex)
        write_json(pending / "scene.json", new)
        details={}
        if patch.get('dependency_mode')=='field_spatial_v1':
            from .dependencies import plan
            details={'invalidation_plan':plan(old,patch['operations'],new),'rebased_from_revision':patch['base_scene_revision']}
        write_json(pending / "transaction.json", {"base": identity(old), "patch": patch,
                   "grant_hash": identity(grant), "invalidated_objects": affected,
                   "invalidated_checks": ["render", "structure", "semantic", "grid", "global", "native", "delivery"],**details})
        os.replace(pending, directory / name)
        # Only this pointer is the commit point; incomplete revision dirs are not active.
        write_json(directory / "current.json", {"revision_dir": name, "scene_hash": identity(new)})
        return {"scene_revision": new["revision"], "scene_hash": identity(new), "invalidated_objects": affected}


def rollback_patch(scene, snapshot, ids, task_id):
    """Rollback becomes a new monotonic revision through the same authorization path."""
    before = {o["id"]: o for o in snapshot["objects"]}
    objects = {o["id"]: o for o in scene["objects"]}
    operations = [{"object_id": id, "field": f, "value": before[id][f]}
                  for id in ids for f in FIELD_FACET if before[id].get(f) != objects[id].get(f)]
    return {"task_id": task_id, "base_scene_revision": scene["revision"], "base_scene_hash": identity(scene),
            "expected_versions": {id: objects[id]["versions"] for id in closure(scene, ids) if id in objects}, "operations": operations}
