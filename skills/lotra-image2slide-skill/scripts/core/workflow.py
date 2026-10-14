"""Resumable deterministic half of the host-image → native reconstruction workflow."""
import importlib.metadata
from pathlib import Path
import platform
import time
from . import VERSION
from .common import digest,read_json,write_json,identity,safe_path
from .session import resume,stage,cache_binding,cache_lookup,cache_store
from .scene import validate
from .build import build
from .inspect import check
from .office import probe,inspect_environment


def compile_task(workdir,scene_path,*,office=True,prepare_crops=True,drawing_plan=None,action_journal=None):
    workdir=Path(workdir).resolve();scene_path=Path(scene_path).resolve()
    resume(workdir)
    scene=read_json(scene_path);validate(scene,scene_path.parent)
    desktop_pending=workdir/'desktop-pending.json'
    if desktop_pending.is_file():
        pending=read_json(desktop_pending)
        reconciled=pending.get('candidate_scene')
        saved_pptx=pending.get('candidate_pptx') or {}
        source_result=pending.get('result') or {}
        if (pending.get('scene_state')!='SCENE_RECONCILED_TO_SAVED_PPT'
                or not isinstance(reconciled,dict)
                or reconciled.get('sha256')!=digest(scene_path)
                or not isinstance(saved_pptx,dict)
                or digest(safe_path(workdir,saved_pptx['path']))!=saved_pptx['sha256']
                or digest(safe_path(workdir,source_result['path']))!=source_result['sha256']):
            raise ValueError('A saved desktop edit is authoritative; reconcile the Scene before rebuilding')
        if pending.get('reconciliation'):
            receipt=pending['reconciliation']
            if (digest(safe_path(workdir,receipt['path']))!=receipt['sha256']
                    or read_json(safe_path(workdir,receipt['path'])).get('candidate_scene')!=reconciled):
                raise ValueError('Desktop Scene reconciliation receipt changed')
    plan=analysis=None
    if scene.get('analysis') and drawing_plan is None:
        conventional=workdir/'drawing-plan.json'
        if conventional.is_file():
            drawing_plan=conventional
        else:
            raise ValueError('Analyzed v1.0.2 tasks require a frozen drawing plan before building')
    if drawing_plan is not None:
        if not scene.get('analysis'):
            raise ValueError('Drawing plan requires frozen source analysis in Scene')
        from .drawing_plan import validate_plan
        analysis=read_json(safe_path(scene_path.parent,scene['analysis']['path']))
        plan=read_json(drawing_plan)
        validate_plan(plan,analysis,scene,scene_path.parent)
        if action_journal is None and (workdir/'actions.json').is_file():
            action_journal=workdir/'actions.json'
    if action_journal is not None:
        action_journal=Path(action_journal).resolve()
        if plan is None or action_journal != workdir/'actions.json':
            raise ValueError('Action journal must belong to this planned task workspace')
    with stage(workdir,'current-platform-preflight') as notes:
        env=inspect_environment() if office else {'backend_version':'file-only','platform':platform.platform(),'font_inventory_hash':'not-rendered'}
        env['runtime_packages']={k:importlib.metadata.version(k) for k in ('python-pptx','lxml','Pillow','numpy','jsonschema')}
        notes.update(environment=env)
    binding=cache_binding(workdir,scene=scene_path,backend='native-pptx',environment=env,options={'operation':'build-inspect'})
    cached=cache_lookup(workdir,binding)
    build_dir=workdir/'builds'/identity(binding)[:20]
    claimed_build=None
    if action_journal is not None and action_journal.is_file():
        journal=read_json(action_journal)
        active=[item for item in journal.get('operations', [])
                if item.get('plan_hash')==identity(plan) and item.get('status')=='RUNNING']
        if active:
            if len(active)!=1 or active[0].get('operation')!='build':
                raise ValueError('An unresolved non-build action blocks a new Scene build')
            claimed_build=active[0]
            scene_ref=claimed_build.get('inputs', {}).get('scene', {})
            target=claimed_build.get('output_targets', {}).get('Candidate.pptx')
            if (scene_ref.get('sha256')!=digest(scene_path) or not target
                    or cached is not None):
                raise ValueError('Claimed build must bind this Scene and a new frozen output path')
            build_dir=(workdir/target).resolve().parent
            if (not build_dir.is_relative_to(workdir)
                    or (workdir/target).resolve()!=build_dir/'Candidate.pptx'
                    or ('structure.json' in claimed_build['output_targets']
                        and claimed_build['output_targets']['structure.json']!=
                            (build_dir/'structure.json').relative_to(workdir).as_posix())):
                raise ValueError('Claimed build targets must share the task-owned build directory')
    with stage(workdir,'build-and-inspect',candidate=not bool(cached) and claimed_build is None) as notes:
        if cached:
            notes.update(cache_hit=True,binding=binding)
        else:
            if build_dir.exists():
                if claimed_build is not None:
                    raise FileExistsError('Frozen claimed build directory already exists; reconcile the action')
                build_dir=workdir/'builds'/(identity(binding)[:20]+'-'+str(time.time_ns()))
            build_dir.mkdir(parents=True)
            pptx=build_dir/'Candidate.pptx';build(scene,scene_path.parent,pptx)
            report=check(scene,scene_path.parent,pptx);write_json(build_dir/'structure.json',report)
            if report['status']!='PASS':raise ValueError('Saved native structure failed; inspect '+str(build_dir/'structure.json'))
            cache_store(workdir,binding,{'pptx':pptx,'structure':build_dir/'structure.json'})
            cached=cache_lookup(workdir,binding);notes.update(cache_hit=False,binding=binding,object_count=len(scene['objects']),
                                                            candidate_charge='action_claim' if claimed_build else 'stage')
    # cache_lookup returns verified entry with artifact path records.
    artifact=cached['artifacts']['pptx'];pptx=workdir/artifact['path']
    result={'implementation_version':VERSION,'scene':str(scene_path),'pptx':str(pptx),'pptx_hash':digest(pptx),'status':'BUILT_NOT_ACCEPTED'}
    if not office:
        if plan is not None:
            from .drawing_plan import check_conformance
            report=check_conformance(plan,analysis,scene,scene_path.parent,pptx,action_journal=action_journal)
            path=workdir/'plan-conformance.json';write_json(path,report)
            result.update(plan_conformance=str(path),plan_status=report['status'])
        return result
    render_binding=cache_binding(workdir,scene=scene_path,backend='PowerPoint',environment=env,inputs={'pptx':pptx},options={'operation':'render','width':scene['canvas']['width']})
    rendered=cache_lookup(workdir,render_binding)
    render_dir=workdir/'renders'/identity(render_binding)[:20]
    with stage(workdir,'target-render') as notes:
        if not rendered:
            if render_dir.exists():render_dir=workdir/'renders'/(identity(render_binding)[:20]+'-'+str(time.time_ns()))
            probe(pptx,render_dir,render_only=True,preview_width=scene['canvas']['width'])
            rr=read_json(render_dir/'render.json');rr['current_environment']=env;write_json(render_dir/'render.json',rr)
            cache_store(workdir,render_binding,{'preview':render_dir/'Final_preview.png','pdf':render_dir/'Final.pdf','receipt':render_dir/'render.json'})
            rendered=cache_lookup(workdir,render_binding);notes['cache_hit']=False
        else:notes['cache_hit']=True
    preview=workdir/rendered['artifacts']['preview']['path'];receipt=workdir/rendered['artifacts']['receipt']['path']
    result.update(render_dir=str(preview.parent),preview=str(preview),render_receipt=str(receipt))
    if prepare_crops:
        from .review import prepare_review
        from .measure import measure
        directory=workdir/'reviews'/str(time.time_ns())
        with stage(workdir,'measure-and-prepare-review') as notes:
            actual=measure(scene,pptx)
            review=prepare_review(scene,scene_path.parent,pptx,preview,receipt,directory,implementation_version=VERSION,actual_objects=actual)
            write_json(directory/'actual-objects.json',actual)
            notes.update(review=str(directory),targets=len(review['targets']))
        result['review_dir']=str(directory)
    if plan is not None:
        from .drawing_plan import check_conformance
        report=check_conformance(plan,analysis,scene,scene_path.parent,pptx,render_receipt=receipt,
                                 action_journal=action_journal)
        path=workdir/'plan-conformance.json';write_json(path,report)
        result.update(plan_conformance=str(path),plan_status=report['status'])
    write_json(workdir/'latest-build.json',result)
    return result
