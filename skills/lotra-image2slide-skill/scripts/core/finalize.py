"""Prepare one honest delivery; missing acceptance never becomes success."""

from pathlib import Path
import shutil
import tempfile
from lxml import etree as E
from PIL import Image
from .common import digest,identity,read_json,write_json,writer
from .inspect import check,inventory,xml
from .log import export_log
from .qa import gate


def prepare(scene,base,pptx,render_dir,components_dir,assets_dir,qa_path,output,*,drawing_plan=None,action_journal=None,runtime_task=None):
    from .execution_contract import require_delivery
    execution_receipt=require_delivery(runtime_task,pptx)
    if not scene.get('analysis'):
        raise ValueError('v1.0.2 selected delivery requires source analysis and visual closure')
    pptx=Path(pptx)
    render_dir,components_dir,assets_dir,output=map(Path,(render_dir,components_dir,assets_dir,output))
    if output.exists():raise FileExistsError(output)
    user_output=output
    output=Path(runtime_task)/'exports'/('legacy-internal-'+identity({'pptx':digest(pptx),'destination':str(user_output)})[:24])
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise FileExistsError('Inspect the existing internal export')
    qa=read_json(qa_path)
    rr=read_json(render_dir/"render.json")
    binding=qa["binding"]
    if qa.get('evidence_attachments'):
        from .review import implementation_hash
        from .session import implementation_identity
        from .common import safe_path
        if binding.get('implementation_hash')!=implementation_hash() or binding.get('implementation')!=implementation_identity():
            raise ValueError('QA implementation binding is stale')
        for ref in qa['evidence_attachments']:
            if digest(safe_path(base,ref['path']))!=ref['sha256']:
                raise ValueError('QA evidence attachment changed')
    if binding["scene_hash"]!=identity(scene) or binding["pptx_hash"]!=digest(pptx) or binding["profile_hash"]!=scene["profile"]["sha256"]:
        raise ValueError("QA binding is stale")
    if scene.get('analysis'):
        from .qa import verify_visual_closure
        if verify_visual_closure(qa,base,scene,pptx)!= 'PASS':
            raise ValueError('Selected reconstruction still has missing or unreviewed source content')
    preview,pdf=render_dir/"Final_preview.png",render_dir/"Final.pdf"
    if rr["pptx_hash"]!=digest(pptx) or rr["preview_hash"]!=digest(preview) or rr["pdf_hash"]!=digest(pdf) or binding["preview_hash"]!=digest(preview):
        raise ValueError("Final render artifacts are stale")
    fresh=check(scene,base,pptx)
    if fresh["status"]!="PASS":raise ValueError("Final saved deck failed fresh structural check")
    from .common import safe_path
    from .hierarchy import evaluate as check_hierarchy
    analysis=read_json(safe_path(base,scene['analysis']['path']))
    with tempfile.TemporaryDirectory(prefix='sci-final-hierarchy-') as temp:
        hierarchy=check_hierarchy(analysis,base,scene,pptx,Path(temp)/'hierarchy.json')
    plan_report=None
    if scene.get('analysis'):
        from .drawing_plan import check_conformance
        drawing_plan=Path(drawing_plan) if drawing_plan else Path(base)/'drawing-plan.json'
        if not drawing_plan.is_file():
            raise ValueError('Analyzed delivery requires its frozen drawing plan')
        journal=Path(action_journal) if action_journal else Path(base)/'actions.json'
        plan_report=check_conformance(read_json(drawing_plan),analysis,scene,base,pptx,
                                      render_receipt=render_dir/'render.json',
                                      action_journal=journal if journal.is_file() else None)
        if plan_report['status']=='FAIL':
            raise ValueError('Final saved deck violates its frozen drawing plan')
    index=read_json(components_dir/"index.json")
    component_deck=components_dir/"Components_editable.pptx"
    if index["source_pptx_hash"]!=digest(pptx) or index["native_pptx_hash"]!=digest(component_deck) or index["scene_hash"]!=identity(scene):
        raise ValueError("Component native master is stale")
    expected={o["id"] for o in scene["objects"] if o["render_type"]=="group" and o.get('component',not o.get('parent'))}
    if not expected or {c["semantic_id"] for c in index["components"]}!=expected:
        raise ValueError("Required component inventory incomplete")
    assets=read_json(assets_dir/"assets.json")
    if assets["source_pptx_hash"]!=digest(component_deck) or {c["semantic_id"] for c in assets["components"]}!=expected:
        raise ValueError("Component exports are stale/incomplete")
    asset_files=[]
    for c in assets["components"]:
        if {a["format"] for a in c["assets"]}!={"png","svg"}:
            raise ValueError("Required component PNG/SVG missing")
        for a in c["assets"]:
            if a["status"]!="EXPORTED" or a["path"]!=c["semantic_id"]+"."+a["format"]:
                raise ValueError("Component asset missing or unsafe")
            file=assets_dir/a["path"]
            if digest(file)!=a["sha256"]:raise ValueError("Component asset hash mismatch")
            if a["format"]=="svg":
                root=E.parse(str(file),E.XMLParser(resolve_entities=False,no_network=True)).getroot()
                representation=next(item['representation'] for item in index['components'] if item['semantic_id']==c['semantic_id'])
                if root.tag!="{http://www.w3.org/2000/svg}svg" or representation=='vector' and root.findall(".//{http://www.w3.org/2000/svg}image"):
                    raise ValueError("Schematic vector export contains raster substitution")
            else:
                img=Image.open(file)
                if img.convert("RGBA").getextrema()[-1][0]==255:
                    raise ValueError("Component preview lacks expected transparency")
            asset_files.append(file)
    # Copy verified files once. Manifest is the final closure, not an acceptance bypass.
    qa["structure"]=fresh
    qa["channels"]["deliverables"]="PASS"
    if hierarchy['hard_status']!='PASS':
        current=qa['channels'].get('semantic_review')
        if current!='FAIL':
            qa['channels']['semantic_review']=hierarchy['hard_status']
    profile=read_json(Path(base)/scene["profile"]["path"])
    qa["status"]=gate(profile,qa["channels"],True)
    if plan_report and plan_report['status']!='PASS' and qa['status']=='ACCEPTED':
        qa['status']='UNVERIFIED'
    with writer(output):
        shutil.copyfile(pptx,output/"Final_editable.pptx")
        shutil.copyfile(preview,output/"Final_preview.png")
        components=output/"Components"
        components.mkdir()
        shutil.copyfile(component_deck,components/"Components_editable.pptx")
        for file in asset_files:shutil.copyfile(file,components/file.name)
        write_json(components/"index.json",index | {"assets":assets["components"]})
        export_log(scene,qa,output/"iteration_log.xlsx",{"target_backend":rr.get("backend"),"target_version":rr.get("backend_version"),"office_build":rr.get("office_build")})
        if plan_report is not None:
            write_json(output/'plan-conformance.json',plan_report)
        write_json(output/'hierarchy.json',hierarchy)
        write_json(output/'Acceptance.json',execution_receipt)
        files={p.relative_to(output).as_posix():digest(p) for p in output.rglob("*") if p.is_file() and p.name!=".writer.lock"}
        manifest={"status":qa["status"],"scene_hash":identity(scene),"scene_revision":scene["revision"],"files":files,
                  "binding":qa["binding"],"render_receipt_hash":digest(render_dir/"render.json"),
                  "channels":qa["channels"],"unmet":[k for k,v in qa["channels"].items() if v!="PASS"],
                  "plan_status":plan_report['status'] if plan_report else 'NOT_APPLICABLE_LEGACY_SCENE',
                  "hierarchy_hard_status":hierarchy['hard_status'],
                  "plan_hash":plan_report['plan_hash'] if plan_report else None,
                  "scope":"selected reconstruction delivery; quality and full-spec acceptance are reported independently"}
        write_json(output/"delivery.json",manifest)
    from .component_report import generate
    from .user_delivery import expose
    details=generate(runtime_task,output/'Metrics',office_bounds=render_dir/'text-bounds.json')
    from .agent_runtime import _state
    current_task,current_state=_state(runtime_task)
    result=expose(pptx,None,details,user_output,output/'compact-audit',status=manifest['status'],acceptance=execution_receipt,
        caps=current_state['capabilities'],base_render=render_dir/'render.json')
    from .transient_export import release_task_pdfs
    if result['status']=='ACCEPTED':
        release_task_pdfs(current_task)
        from .projection_gc import dispose
        dispose(current_task)
    return result


def verify_delivery(directory):
    directory=Path(directory)
    if not (directory/'delivery.json').exists():
        from .user_delivery import verify
        return verify(directory)
    manifest=read_json(directory/"delivery.json")
    required={"Final_editable.pptx","Final.pdf","Final_preview.png","iteration_log.xlsx","Components/Components_editable.pptx","Components/index.json"}
    if 'hierarchy_hard_status' in manifest:
        required.add('hierarchy.json')
    if not required<=set(manifest["files"]):raise ValueError("Required delivery artifacts absent from manifest")
    found={p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
    if found!=set(manifest["files"])|{"delivery.json"}:raise ValueError("Missing or unexpected delivery files")
    from .common import safe_path
    for path,hash_ in manifest["files"].items():
        if digest(safe_path(directory,path))!=hash_:raise ValueError("Delivery artifact changed: "+path)
    return {"integrity":"PASS","product_status":manifest["status"],"scope":"saved_delivery_integrity_only","file_count":len(manifest["files"])}
