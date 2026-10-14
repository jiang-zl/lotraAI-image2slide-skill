"""Per-instance measured candidate archive. No worker-supplied quality scores."""

import copy
import math
from pathlib import Path
import shutil
from PIL import Image
from .common import digest, identity, read_json, safe_path, write_json, writer, raster_rgb
from .inspect import check
from .metrics import foreground, iou
from .state import closure


def record_candidate(scene, base, object_id, pptx, preview, render_receipt, registry):
    """Keep a version-bound local best from a real saved native candidate/render.

    Ranking here is exploratory foreground IoU with hard structural veto. It
    never asserts calibrated local PASS or a globally feasible reconstruction.
    """
    objects={o["id"]:o for o in scene["objects"]}
    if object_id not in objects:
        raise ValueError("Unknown candidate object")
    evidence=read_json(safe_path(base,scene["evidence"]["path"]))
    refs={o["id"]:o for o in evidence.get("objects",[])}
    if object_id not in refs:
        raise ValueError("No frozen reference ROI for candidate")
    rr=read_json(render_receipt)
    if rr.get("pptx_hash")!=digest(pptx) or rr.get("preview_hash")!=digest(preview):
        raise ValueError("Candidate/render mismatch")
    structure=check(scene,base,pptx)
    ref=raster_rgb(Image.open(safe_path(base,scene["source"]["path"])),scene['canvas'].get('background_rgb',[255,255,255]))
    actual=Image.open(preview).convert("RGB")
    if actual.width/actual.height!=ref.width/ref.height:
        raise ValueError("Candidate canvas changed")
    actual=actual.resize(ref.size,Image.Resampling.LANCZOS)
    roi=refs[object_id].get("bbox",refs[object_id].get("roi"))
    if not isinstance(roi,list) or len(roi)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in roi):
        raise ValueError("Frozen evidence needs a finite xywh bbox or roi")
    x,y,w,h=roi
    box=(round(x),round(y),round(x+w),round(y+h))
    if not 0<=box[0]<box[2]<=ref.width or not 0<=box[1]<box[3]<=ref.height:
        raise ValueError("Invalid frozen candidate ROI")
    score=iou(foreground(ref.crop(box)),foreground(actual.crop(box)))
    from .typed_metrics import image_measure,DEFAULT_PROTOCOL,scalar_vector,dominance,VERSION as METRIC_VERSION
    measured=image_measure(ref.crop(box),actual.crop(box),dict(DEFAULT_PROTOCOL,background_rgb=scene['canvas'].get('background_rgb',[255,255,255])))
    vector=scalar_vector(measured)
    dependencies={k:objects[k]["versions"] for k in closure(scene,{object_id}) if k in objects}
    local_key=identity({"source":scene["source"]["sha256"],"evidence":scene["evidence"]["sha256"],"profile":scene["profile"]["sha256"],
                        "object":object_id,"backend":rr.get("backend"),"version":rr.get("backend_version"),
                        "fonts":rr.get("fonts",rr.get("environment")),"metric_version":METRIC_VERSION})
    record={"object_id":object_id,"scene_hash":identity(scene),"scene_revision":scene["revision"],"local_key":local_key,
            "dependency_signatures":{k:identity(objects[k]) for k in dependencies},
            "dependency_versions":dependencies,"source_pptx_hash":digest(pptx),"preview_hash":digest(preview),
            "render_receipt_hash":digest(render_receipt),"foreground_iou":score,"structural_status":structure["status"],
            "metric_vector":vector,"metric_version":METRIC_VERSION,"measurements":measured,
            "status":"UNVERIFIED","reason":"Measured candidate; semantic review/calibration/context acceptance still required"}
    candidate_id=identity(record)[:20]
    registry=Path(registry)
    with writer(registry):
        index=read_json(registry/"index.json") if (registry/"index.json").exists() else {"objects":{},"best_feasible_scene":None}
        entry=index["objects"].setdefault(object_id,{"candidates":[],"best_local":None,"best_in_scene":None})
        if candidate_id in entry["candidates"]:
            return read_json(registry/candidate_id/"candidate.json")
        target=registry/candidate_id
        target.mkdir()
        for src,name in [(pptx,"Candidate.pptx"),(preview,"preview.png"),(render_receipt,"render.json")]:
            shutil.copyfile(src,target/name)
        if digest(target/"Candidate.pptx")!=record["source_pptx_hash"] or digest(target/"preview.png")!=record["preview_hash"] or digest(target/"render.json")!=record["render_receipt_hash"]:
            raise ValueError("Candidate changed while being archived")
        write_json(target/"scene.json",scene)
        write_json(target/"candidate.json",record)
        entry["candidates"].append(candidate_id)
        best=read_json(registry/entry["best_local"]/"candidate.json") if entry["best_local"] else None
        directions={'color':'min','residual':'min','boundary_f1':'max','internal_edge_f1':'max'}
        comparison=dominance(best.get('metric_vector',{}) if best else {},vector,directions)
        if structure["status"]=="PASS" and all(vector.get(k) is not None for k in directions) and (best is None or best["local_key"]==local_key and comparison['result']=='helped'):
            entry["best_local"]=candidate_id
        # No record here can award semantic/context/native acceptance to itself.
        entry["best_in_scene"]=None
        write_json(registry/"index.json",index)
    return record | {"candidate_id":candidate_id,"best_local":entry["best_local"]}


def best_snapshot(registry,object_id,current_scene):
    registry=Path(registry)
    entry=read_json(registry/"index.json")["objects"][object_id]
    if not entry["best_local"]:
        raise ValueError("No structurally feasible measured local candidate")
    path=registry/entry["best_local"]
    record=read_json(path/"candidate.json")
    snapshot=read_json(path/"scene.json")
    if identity(snapshot)!=record["scene_hash"] or digest(path/"Candidate.pptx")!=record["source_pptx_hash"] or digest(path/"preview.png")!=record["preview_hash"]:
        raise ValueError("Candidate archive changed")
    current_objects={o["id"]:o for o in current_scene["objects"]}
    context_valid=all(id in current_objects and current_objects[id]["versions"]==v and identity(current_objects[id])==record["dependency_signatures"][id] for id,v in record["dependency_versions"].items())
    context_valid=context_valid and all(current_scene[k]==snapshot[k] for k in ("source","evidence","profile"))
    return {"snapshot":snapshot,"candidate_id":entry["best_local"],"context_valid":context_valid,"status":"UNVERIFIED"}
