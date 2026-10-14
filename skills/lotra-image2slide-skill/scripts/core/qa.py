"""Real saved-render measurements and fail-closed acceptance aggregation."""

from pathlib import Path
from PIL import Image
from .common import digest, identity, read_json, safe_path, write_json, raster_rgb
from .inspect import check
from .grids import windows, coverage
from .metrics import balance, foreground, iou, aesthetic, render_canvas_mapping


def _scalar_measurements(value, prefix=""):
    """Keep numeric observations scalar, with explicit names and missing values."""
    for key, item in value.items():
        name=prefix+key
        if isinstance(item,dict):
            yield from _scalar_measurements(item,name+".")
        elif item is None or isinstance(item,(int,float,bool)):
            yield name,item


def attach_evidence(scene, base, pptx, preview, render_receipt, qa_path,
                    review_manifest_path, review_paths, output, *,
                    native_verification_path=None, native_plan_path=None,
                    native_office_dir=None, stage_records=None):
    """Attach current, independently supplied evidence without inventing PASS.

    review_paths is a sequence of reviewer JSON files for the same frozen crop
    plan. stage_records contains {kind: session|stage|patch_commit, path, sha256}
    relative to base. Historical stage durations come only from those files.
    Native PASS requires a bound plan, actual Office artifacts and a fresh
    deterministic recheck. The uncalibrated local/global channels stay unknown.
    All input attachments must be within the task base; output must be new.
    """
    import copy
    import math
    import tempfile
    from . import VERSION
    from .review import current_binding, import_review
    from .session import implementation_identity
    base=Path(base).resolve()
    if Path(output).exists():raise FileExistsError(output)

    def attachment(path):
        path=Path(path).resolve()
        if not path.is_relative_to(base):
            raise ValueError("Evidence attachment must reside within task base")
        return {"path":path.relative_to(base).as_posix(),"sha256":digest(path)}

    current=current_binding(scene,base,pptx,preview,render_receipt,implementation_version=VERSION)
    implementation=implementation_identity()
    qa=copy.deepcopy(read_json(qa_path))
    for key in ("source_hash","evidence_hash","scene_hash","scene_revision","profile_hash",
                "pptx_hash","preview_hash","render_receipt_hash","component_versions"):
        if qa.get("binding",{}).get(key)!=current[key]:
            raise ValueError("Stale base QA binding: "+key)
    if qa["binding"].get("implementation") not in (None,implementation):
        raise ValueError("Stale QA implementation")
    manifest=read_json(review_manifest_path)
    if manifest["binding"]!=current:raise ValueError("Stale review manifest binding")
    paths=list(review_paths)
    if not paths:raise ValueError("At least one explicit reviewer file required")
    reports=[]
    references=[attachment(qa_path),attachment(review_manifest_path)]
    for path in paths:
        ref=attachment(path)
        report=import_review(manifest,read_json(path),current_binding=current,
                             review_directory=Path(review_manifest_path).parent)
        report["artifact"]=ref
        reports.append(report)
        references.append(ref)
    grouped={}
    for report in reports:
        for obs in report["observations"]:
            grouped.setdefault((obs["target_id"],obs["criterion"]),[]).append(obs["level"])
    missing=[{"target_id":t["id"],"criterion":c} for t in manifest["targets"]
             for c in t["required_criteria"] if not any(v is not None for v in grouped.get((t["id"],c),[]))]
    conflicts=[{"target_id":key[0],"criterion":key[1],"levels":values} for key,values in grouped.items()
               if len({v for v in values if v is not None})>1]
    local=[]
    kinds={o["id"]:o["render_type"] for o in scene["objects"]}
    manifest_ref=attachment(review_manifest_path)
    for target in manifest["targets"]:
        for field in ("measurements","object_measurements"):
            for metric,value in _scalar_measurements(target.get(field,{})):
                if isinstance(value,float) and not math.isfinite(value):
                    raise ValueError("Nonfinite measured value")
                local.append({"object_or_window_id":target["id"],"category":kinds.get(target["id"].removeprefix("object:"),target["kind"]),
                              "metric_id":metric,"raw_value":value,"normalized_score":None,"threshold":None,
                              "status":"UNVERIFIED","evidence_ref":manifest_ref["path"]+"#/targets/"+target["id"]+"/"+field,
                              "evidence_sha256":manifest_ref["sha256"]})
    qa.update(visual_reviews=reports,review_coverage={"missing":missing,"conflicts":conflicts,
              "planned_target_count":len(manifest["targets"]),
              "covered_target_count":sum(all(any(v is not None for v in grouped.get((t["id"],c),[]))
                  for c in t["required_criteria"]) for t in manifest["targets"])},
              local_measurements=local,raw_global=manifest["raw_global"],evidence_attachments=references)
    qa["critical_defects"]=[dict(defect,review_artifact=report["artifact"]) for report in reports
                            for defect in report["defects"] if defect["severity"]=="critical"]
    if qa["critical_defects"]:qa["channels"]["semantic_review"]="FAIL"
    source_reviews=[obs for report in reports for obs in report["observations"]
                    if obs["target_id"]=="source-only" and obs["criterion"]=="source_omission_review"]
    source_defects=[defect for report in reports for defect in report["defects"]
                    if "source-only" in defect.get("target_ids",[]) or
                    any(target_id.startswith(("coarse-","fine-","shifted_fine-"))
                        for target_id in defect.get("target_ids",[]))]
    omission_observations=[obs for report in reports for obs in report["observations"]
                           if obs["criterion"] in ("source_omission_review","omission_extras")]
    if source_defects or any(obs["level"] is not None and obs["level"]<3 for obs in omission_observations):
        qa["channels"]["source_omission_review"]="FAIL"
    elif (source_reviews and all(obs["level"]==3 for obs in source_reviews)
          and not manifest["source_missing_items"] and
          not any(item["target_id"]=="source-only" for item in missing) and
          not any(item["target_id"]=="source-only" for item in conflicts)):
        qa["channels"]["source_omission_review"]="PASS"
    # Only explicit adverse evidence changes channels here. Rubric coverage and
    # a measured zero are not a calibrated quality acceptance rule.
    for report in reports:
        for obs in report["observations"]:
            if obs["level"] is not None and obs["level"]<=1:
                if obs["criterion"] in ("semantic_content","natural_parts"):
                    qa["channels"]["semantic_review"]="FAIL"
                elif obs["criterion"]=="source_omission_review":
                    qa["channels"]["source_omission_review"]="FAIL"
                elif obs["criterion"]=="omission_extras":
                    qa["channels"]["source_omission_review"]="FAIL"
                elif obs["target_id"].startswith(("coarse-","fine-","shifted_fine-")):
                    qa["channels"]["grid_review"]="FAIL"
                elif obs["target_id"].startswith("object:"):
                    qa["channels"]["local_metrics"]="FAIL"
                elif obs["criterion"] in ("direction_topology","occlusion_continuity"):
                    qa["channels"]["scene_relations"]="FAIL"
    for target in manifest["targets"]:
        values=target.get("object_measurements",{})
        if values.get("text_exact") is False or values.get("formula_ast_exact") is False:
            qa["channels"]["local_metrics"]="FAIL"
    qa["native_verification"]=None
    if native_verification_path is not None:
        native=read_json(native_verification_path)
        ref=attachment(native_verification_path);references.append(ref)
        if native.get("source_pptx_hash")!=current["pptx_hash"] or native.get("scene_hash")!=current["scene_hash"]:
            raise ValueError("Stale native verification source binding")
        if native.get("implementation_version")!=VERSION:
            raise ValueError("Stale native verification implementation version")
        if native.get("implementation") is not None and native["implementation"]!=implementation:
            raise ValueError("Stale native verification implementation files")
        verified=False
        missing_native=[]
        if native_plan_path is None or native_office_dir is None:
            missing_native.append("native plan and actual Office directory required for recheck")
        elif native.get("implementation") is None or native.get("plan_hash") is None:
            missing_native.append("native report lacks full implementation or plan hash")
        else:
            plan=read_json(native_plan_path)
            if native["plan_hash"]!=digest(native_plan_path) or plan.get("implementation")!=implementation:
                raise ValueError("Stale native plan binding")
            if plan.get("pptx_hash")!=current["pptx_hash"] or plan.get("scene_hash")!=current["scene_hash"]:
                raise ValueError("Native plan does not bind current saved inputs")
            refs=[attachment(native_plan_path),attachment(Path(native_office_dir)/"operations.json"),
                  attachment(Path(native_office_dir)/"Native_test_copy.pptx")]
            references.extend(refs)
            if native.get("edited_pptx_hash")!=refs[-1]["sha256"] or native.get("operations_hash")!=refs[-2]["sha256"]:
                raise ValueError("Native edited files changed")
            from .native_task import verify
            with tempfile.TemporaryDirectory(prefix="sci-rebuild-native-check-") as directory:
                fresh=verify(native_plan_path,native_office_dir,Path(directory)/"verification.json")
            if fresh!=native:raise ValueError("Native verification does not match fresh saved-file checks")
            verified=True
        qa["native_verification"]={"report":native,"artifact":ref,"binding_verified":verified,
                                    "missing":missing_native,"scope":"listed actual native operations only"}
        qa["channels"]["native_edit_roundtrip"]="FAIL" if native.get("status")=="FAIL" else (
            "PASS" if verified and native.get("status")=="PASS" else "UNVERIFIED")
    else:
        qa["channels"]["native_edit_roundtrip"]="UNVERIFIED"
    history=[]
    for record in stage_records or []:
        if record.get("kind") not in ("session","stage","patch_commit"):
            raise ValueError("Explicit supported stage record kind required")
        path=safe_path(base,record["path"])
        if digest(path)!=record["sha256"]:raise ValueError("Stage history artifact hash changed")
        data=read_json(path)
        references.append(attachment(path))
        if record["kind"]=="session":
            if data.get("source",{}).get("sha256")!=current["source_hash"]:
                raise ValueError("Stage session source mismatch")
            entries=data.get("stages",[])
        else:entries=[data]
        for index,entry in enumerate(entries):
            for key in ("elapsed_seconds","cpu_seconds"):
                value=entry.get(key)
                if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or value<0):
                    raise ValueError("Invalid recorded stage timing")
            history.append({"kind":record["kind"],"record":entry,"artifact":dict(record),
                            "evidence_ref":record["path"]+("#/stages/"+str(index) if record["kind"]=="session" else "")})
    qa["stage_history"]=history
    profile=read_json(safe_path(base,scene["profile"]["path"]))
    qa["binding"]=qa["binding"] | current | {"implementation":implementation}
    qa["global_dimensions"]={k:None for k in profile["global_aesthetic"]["weights"]}
    qa["global_aesthetic"]=aesthetic(profile,qa["global_dimensions"])
    qa["channels"]["global_aesthetic"]="UNVERIFIED"
    qa["local_scores"]=None
    qa["status"]=gate(profile,qa["channels"],True)
    qa["note"]="Bound measurements, rubric observations, native rechecks and actual history; uncalibrated totals remain unavailable"
    if current_binding(scene,base,pptx,preview,render_receipt,implementation_version=VERSION)!=current or implementation_identity()!=implementation:
        raise ValueError("Artifacts or implementation changed during QA attachment")
    for ref in references:
        if digest(safe_path(base,ref["path"]))!=ref["sha256"]:
            raise ValueError("Evidence attachment changed during QA aggregation")
    write_json(output,qa)
    return qa

REQUIRED = ("structure", "semantic_review", "source_omission_review", "local_metrics", "scene_relations",
            "grid_review", "global_aesthetic", "native_edit_roundtrip", "target_render", "deliverables")


def verify_visual_closure(qa, base, scene, pptx, preview=None):
    """Recheck the source-to-output review before a candidate earns selection credit."""
    if not scene.get('analysis'):
        return 'UNVERIFIED'
    from .common import safe_path
    analysis_ref=scene['analysis']
    analysis_path=safe_path(base,analysis_ref['path'])
    if digest(analysis_path)!=analysis_ref['sha256']:
        return 'UNVERIFIED'
    analysis=read_json(analysis_path)
    if (any(item.get('status')=='unresolved' for group in ('observations','nodes','relations')
            for item in analysis.get(group,[])) or
            any(node.get('required',True) and
                node.get('decomposition',{}).get('decision') in ('unresolved','resource_stop')
                for node in analysis.get('nodes',[]))):
        return 'UNVERIFIED'
    binding=qa.get('binding',{})
    if (binding.get('source_hash')!=scene['source']['sha256'] or
            binding.get('scene_hash')!=identity(scene) or
            binding.get('pptx_hash')!=digest(pptx) or
            preview is not None and binding.get('preview_hash')!=digest(preview)):
        raise ValueError('Source closure belongs to another saved candidate')
    if qa.get('channels',{}).get('source_omission_review')!='PASS':
        return qa.get('channels',{}).get('source_omission_review','UNVERIFIED')
    refs=qa.get('evidence_attachments',[])
    if not refs or any(digest(safe_path(base,ref['path']))!=ref['sha256'] for ref in refs):
        return 'UNVERIFIED'
    manifest_refs=[ref for ref in refs if Path(ref['path']).name=='review-manifest.json']
    if len(manifest_refs)!=1:
        return 'UNVERIFIED'
    manifest_path=safe_path(base,manifest_refs[0]['path'])
    manifest=read_json(manifest_path)
    from .review import import_review
    for report in qa.get('visual_reviews',[]):
        if any(binding.get(key)!=value for key,value in report.get('binding',{}).items()):
            return 'UNVERIFIED'
        artifact=report.get('artifact')
        if not artifact or artifact not in refs:
            return 'UNVERIFIED'
        reviewer=read_json(safe_path(base,artifact['path']))
        fresh=import_review(manifest,reviewer,current_binding=report['binding'],
                            review_directory=manifest_path.parent)
        stable=lambda value:{key:item for key,item in value.items()
                             if key not in ('artifact','reviewed_at')}
        if stable(fresh)!=stable(report):
            return 'UNVERIFIED'
    observations=[obs for report in qa.get('visual_reviews',[])
                  for obs in report.get('observations',[])
                  if obs.get('target_id')=='source-only' and obs.get('criterion')=='source_omission_review']
    if not observations or any(obs.get('level')!=3 for obs in observations):
        return 'UNVERIFIED'
    if any(report.get('source_missing_items') or
           any('source-only' in defect.get('target_ids',[]) for defect in report.get('defects',[]))
           for report in qa['visual_reviews']):
        return 'FAIL'
    coverage=qa.get('review_coverage',{})
    if any(item.get('target_id')=='source-only' for key in ('missing','conflicts')
           for item in coverage.get(key,[])):
        return 'UNVERIFIED'
    return 'PASS'


def gate(profile, channels, binding_valid, stop_reason=None):
    if not channels or not binding_valid:
        return "BLOCKED"
    config=profile["global_aesthetic"]
    calibrated=profile["status"]=="calibrated" and config["overall_threshold"] is not None and all(v is not None for v in config["dimension_floors"].values())
    eligible = calibrated and all(channels.get(k) == "PASS" for k in REQUIRED)
    if eligible:
        return "ACCEPTED"
    if stop_reason == "resource_limit":
        return "PAUSED_RESOURCE_LIMIT"
    if stop_reason == "stagnation":
        return "STALLED_NOT_ACCEPTED"
    return "BLOCKED"


def evaluate(scene, base, pptx, preview, render_receipt, output):
    structure = check(scene, base, pptx)
    profile = read_json(safe_path(base, scene["profile"]["path"]))
    r = read_json(render_receipt)
    if r["pptx_hash"] != digest(pptx) or r["preview_hash"] != digest(preview):
        raise ValueError("Render receipt does not bind current saved artifacts")
    reference = raster_rgb(Image.open(safe_path(base,scene["source"]["path"])),scene['canvas'].get('background_rgb',[255,255,255]))
    actual = Image.open(preview).convert("RGB")
    w,h = scene["canvas"]["width"],scene["canvas"]["height"]
    if reference.size != (w,h):
        raise ValueError("Reference canvas mismatch")
    canvas_mapping = render_canvas_mapping((w,h),actual.size)
    actual = actual.resize((w,h), Image.Resampling.LANCZOS)
    tiles = windows(w,h,profile["grid"]["halo"])
    for t in tiles:
        a,b = reference.crop(t["core"]),actual.crop(t["core"])
        t.update({"foreground_iou":iou(foreground(a),foreground(b)),"status":"UNVERIFIED",
                  "reason":"Raw numeric measurement; fixed visual rubric/threshold not calibrated"})
    dimensions = {k:None for k in profile["global_aesthetic"]["weights"]}
    channels = {k:"UNVERIFIED" for k in REQUIRED}
    channels["structure"] = structure["status"]
    if (r.get("scope")=="host_observed_target_render_only"
            or "host_observation" in r or str(r.get("receipt_version","")).startswith("host-render-")):
        from .host_render import verify_render
        channels["target_render"]=verify_render(pptx,preview,r)["status"]
    else:
        channels["target_render"] = "PASS" if r.get("backend") == "PowerPoint" and r.get("status") == "PASS" else "UNVERIFIED"
    report = {"status":gate(profile,channels,True),"channels":channels,"structure":structure,
              "raw_global":{"reference_balance":balance(reference),"candidate_balance":balance(actual)},
              "global_aesthetic":aesthetic(profile,dimensions),"global_dimensions":dimensions,
              "global_weights":profile["global_aesthetic"]["weights"],"local_scores":None,
              "windows":tiles,"coverage":coverage(tiles,w,h),"canvas_mapping":canvas_mapping,"binding":structure["binding"] | {"preview_hash":digest(preview),"render_receipt_hash":digest(render_receipt)},
              "note":"Probe/source-only numeric evidence is not calibrated reconstruction acceptance"}
    write_json(output,report)
    return report
