"""Versioned task copies with transitive, hash-verified resource closure."""
import copy,shutil
from pathlib import Path
from .common import digest,read_json,write_json,safe_path

def copy_resources(value,source,destination,seen=None,missing=None,depth=0):
    seen=set() if seen is None else seen;missing=[] if missing is None else missing
    if depth>48 or len(seen)>20000:raise ValueError('Task resource closure exceeds migration budget')
    if isinstance(value,dict):
        if {'path','sha256'}<=set(value):
            # Logical task resources only. Host/tool configuration paths are
            # not followed, copied, reinterpreted or executed.
            try:file=safe_path(source,value['path'])
            except (ValueError,TypeError):file=None
            if file is not None:
                key=(value['path'],value['sha256'])
                if key not in seen:
                    seen.add(key)
                    if not file.is_file():missing.append({'path':value['path'],'sha256':value['sha256'],'reason':'not_in_historical_task'})
                    elif digest(file)!=value['sha256']:raise ValueError('Historical resource bytes changed: '+value['path'])
                    else:
                        target=safe_path(destination,value['path']);target.parent.mkdir(parents=True,exist_ok=True)
                        if target.exists() and digest(target)!=value['sha256']:raise ValueError('Preserve different destination resource: '+value['path'])
                        if not target.exists():shutil.copyfile(file,target)
                        if file.suffix.lower()=='.json' and value['path']!='source/history/state.json':
                            # Contract/scene/frame descriptors can own further
                            # source mattes; copying only top-level refs loses
                            # these valid executable obligations.
                            document=read_json(file)
                            copy_resources(document,source,destination,seen,missing,depth+1)
                            if isinstance(document,dict) and document.get('source_recursion_hash'):
                                # This is an identity-named implicit dependency
                                # of historical connection replay, not a page.
                                from .common import identity
                                h=document['source_recursion_hash'];relative='source/recursion/revisions/'+h+'.json'
                                tree=safe_path(source,relative)
                                if not tree.is_file() or identity(read_json(tree))!=h:
                                    raise ValueError('Missing immutable original recursion dependency: '+relative)
                                copy_resources({'path':relative,'sha256':digest(tree)},source,destination,seen,missing,depth+1)
                            # Renderer page/PDF paths are receipt-relative,
                            # unlike ordinary task resource IDs. Copy their
                            # exact hashed bytes in that namespace as well.
                            if isinstance(document,dict) and document.get('pptx_hash') and document.get('backend'):
                                for page in document.get('pages',[]):
                                    if not {'path','sha256'}<=set(page):raise ValueError('Actual renderer page lacks identity')
                                    image=safe_path(file.parent,page['path'])
                                    relative=image.relative_to(source).as_posix()
                                    copy_resources({'path':relative,'sha256':page['sha256']},source,destination,seen,missing,depth+1)
                                pdf=document.get('pdf',{})
                                if pdf.get('status')=='EXPORTED' and document.get('pdf_hash'):
                                    image=safe_path(file.parent,pdf['path'])
                                    copy_resources({'path':image.relative_to(source).as_posix(),'sha256':document['pdf_hash']},source,destination,seen,missing,depth+1)
        # Missing-history diagnostics and the frozen historical source state
        # quote earlier artifacts. They are not current task dependencies.
        # A later version can reuse a relative filename; following that quote
        # in the new namespace falsely treats another artifact as tampering.
        # Copy the historical state bytes above, never relabel its old hashes.
        for key,child in value.items():
            # Hint-migration prior hashes quote superseded Scene bytes. The
            # live baseline Scene has its own independently verified resource.
            if key in ('historical_missing','scene_hint_migrations'):continue
            # A historical candidate.reason is explanatory provenance. Its
            # transaction's authoritative ref is independently verified via
            # source_target_attempts[*].contract. v1.21 captured reason's hash
            # before adding owner_transport; that obsolete quote is retained
            # inside the copied JSON, not followed as a current dependency.
            # Actual action contracts and all source/native resources remain
            # hash-verified; this does not approve a changed executable file.
            if key=='reason' and isinstance(child,dict) and child.get('kind')=='source-target-action-1' and 'contract' in child:continue
            copy_resources(child,source,destination,seen,missing,depth+1)
    elif isinstance(value,list):
        for child in value:copy_resources(child,source,destination,seen,missing,depth+1)
    return {'files_examined':len(seen),'historical_missing':missing}

def clone(source,destination):
    from .agent_runtime import SCHEMA
    from . import VERSION
    source=Path(source).resolve();destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError('Preserve existing task and choose a new versioned task name')
    if source.parents[1]!=destination.parents[1] or destination.parent.name!='tasks':
        raise ValueError('Task upgrade stays inside the same project .lotraAI-build/tasks')
    state=read_json(source/'state.json')
    if state.get('schema')!=SCHEMA or digest(safe_path(source,state['source']['path']))!=state['source']['sha256']:
        raise ValueError('Valid immutable original task required')
    destination.mkdir(parents=True);result=copy_resources(state,source,destination)
    result['actual_render_sidecars']=copy_render_sidecars(state,source,destination)
    state=copy.deepcopy(state);state['task_id']=destination.name;state['project']=str(destination.parents[2])
    state['objectives']['whole_quality_intent']=True
    state['objectives']['source_contract_seals']=True
    state['objectives']['all_neighbor_closure']=True
    state.setdefault('quality',{})['_pending_source_seals']=list(state.get('quality',{}).get('specifications',{}))
    for key in ('quality_intent','quality_result','quality_observations','source_readings','acceptance','working_audit'):state.pop(key,None)
    state['packet']=None;state['version_upgrade']={'to':VERSION,'prior_state_sha256':digest(source/'state.json'),
        'source_task':str(source),'resource_closure':result,'status':'QUALITY_REINTERPRETATION_REQUIRED'}
    for folder in ('source','versions','scratch','views','components'):(destination/folder).mkdir(exist_ok=True)
    from .source_contract import seal_pending,verify_seals
    seal_pending(destination,state);verify_seals(destination,state)
    from .source_recursion import activate,initialize
    activate(destination,state);initialize(destination,state)
    write_json(destination/'state.json',state)
    return {'status':'VERSIONED_WORK_COPY_READY','task':str(destination),**result,'acceptance':False}

def copy_render_sidecars(state,source,destination):
    """Retain observed glyph ownership, bound to the exact saved input bytes.

    Legacy render receipts did not expose these generated companion files as
    resource refs. Do not infer them from Scene or ignore missing measurements.
    """
    refs={};records=[]
    def collect(value):
        if isinstance(value,dict):
            if {'pptx','render'}<=set(value) and isinstance(value['render'],dict) and isinstance(value['pptx'],dict) and {'path','sha256'}<=set(value['pptx']) and 'path' in value['render']:
                refs[(value['render']['path'],value['pptx']['sha256'])]=value
            for k,v in value.items():
                if k not in ('historical_missing','prior_source_requirements'):collect(v)
        elif isinstance(value,list):
            for v in value:collect(v)
    collect(state)
    for (render,expected),artifact in refs.items():
        file=safe_path(source,render)
        if not file.is_file():continue
        sidecar=file.parent/'text-bounds.json'
        if not sidecar.is_file():continue
        data=read_json(sidecar)
        if data.get('pptx_hash')!=expected:continue
        receipt=read_json(file)
        if receipt.get('pptx_hash')!=expected:raise ValueError('Actual render sidecar input mismatch')
        target=safe_path(destination,sidecar.relative_to(source).as_posix());target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and digest(target)!=digest(sidecar):raise ValueError('Preserve different glyph-owner sidecar')
        if not target.exists():shutil.copyfile(sidecar,target)
        records.append({'path':target.relative_to(destination).as_posix(),'sha256':digest(target),'pptx_hash':expected})
    return records
