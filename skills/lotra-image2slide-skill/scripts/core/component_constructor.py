"""Component task construction using the established native writer and fonts."""
import copy
import os
from .common import read_json,write_json,identity,safe_path


def construct(task,state,scene,baseline=None,allowed=None,reason=None,transaction=None):
    from . import agent_runtime as a,component_workflow as c,font_contract as fonts
    from .build import build
    from .scene import validate
    from .tables import normalize_scene
    scene=normalize_scene(scene)
    if baseline:c.guard_changes(task,state,scene,allowed,(reason or {}).get('revision_components',()))
    from .semantic_curves import compile_scene
    scene=compile_scene(scene,allowed)
    validate(scene,task)
    if scene['source']['sha256']!=state['source']['sha256'] or [scene['canvas']['width'],scene['canvas']['height']]!=state['source_size']:
        raise ValueError('Source-bound original canvas required for native construction')
    if scene.get('font_plan'):
        try:scene=fonts.compile_scene(scene)
        except ValueError as error:
            if not str(error).startswith(('FONT_BINDING_REQUIRED','FONT_LANGUAGE_CONFLICT')):raise
            scene=copy.deepcopy(scene);scene.pop('font_plan',None)
    if not scene.get('font_plan'):
        fonts.auto_bind(task,state,scene)
        if fonts.missing(scene,state):
            file=task/'scratch'/('component-font-pending-'+identity(scene)[:16]+'.json');write_json(file,scene)
            state['font_pending_candidate']={'scene':a._file(task,file),'baseline':baseline,'allowed':allowed,'reason':reason,
                'transaction_path':transaction['path'] if transaction else None}
            state.update(stage='font_binding',packet=None);a._save(task,state);return None
        scene=fonts.bind_scene(task,state,scene)
    from .component_transactions import begin,phase,saved,release_local,attempt_folder
    tx=transaction or begin(task,state,scene,baseline,allowed,reason)
    if transaction:
        from .component_fields import canonical_node
        before=read_json(c._resource(task,tx['planned_scene']))
        if [canonical_node(n) for n in before['objects']]!=[canonical_node(n) for n in scene['objects']]:
            raise ValueError('Recovered font binding cannot change the retained native plan')
        revised=task/'transactions'/tx['id']/('Font-bound-scene-'+identity(scene)+'.json')
        if not revised.exists():write_json(revised,scene)
        phase(task,tx,'STAGED',planned_scene=c._ref(task,revised))
    number=tx['base_revision']+1;folder=attempt_folder(task,tx)
    file=folder/'drawing.pptx';staged=folder/'drawing.part.pptx'
    contract,ledger=c._load(task,state)
    affected=set(allowed or (owner for row in contract['components'] for owner in row['owners']))
    display_required=any(row['route']!='fixed_parameters' and affected.intersection(row['owners']) for row in contract['components'])
    phase(task,tx,'STAGED',display_required=display_required)
    if baseline:
        from .native_commit import donor_scene,merge_native
        donor=folder/'donor.pptx';construction=build(donor_scene(scene,allowed),task,donor)
        merge_native(c._resource(task,baseline['pptx']),donor,allowed,staged)
    else:construction=build(scene,task,staged)
    font_delivery=fonts.finalize(scene,staged) if baseline else construction['font_delivery']
    os.replace(staged,file)
    scene_file=folder/'scene.json';write_json(scene_file,scene)
    candidate={'revision':number,'scene':a._file(task,scene_file),'pptx':a._file(task,file),
        'reason':reason or {'kind':'component_source_constructor'},'baseline':baseline['pptx']['sha256'] if baseline else None,
        'allowed':allowed,'component_constructor':'native-scene-1.32.0','font_delivery':font_delivery}
    saved(task,tx,candidate)
    state.update(revision=number,active_candidate=candidate,scene=candidate['scene'],stage='host_render' if display_required else 'review',packet=None)
    state.pop('font_pending_candidate',None);state.pop('acceptance',None);a._save(task,state)
    if font_delivery['embedding']['status']=='FONT_EMBEDDING_PROVIDER_REQUIRED':
        state.update(stage='font_delivery',packet=None);a._save(task,state)
        return candidate
    # Persist native bytes first; an export failure resumes this exact candidate.
    if display_required and state['capabilities'].get('libreoffice',{}).get('available') and state.get('render_dispatch',{}).get('mode')!='native_host_tool':
        from .tool_router import render_saved
        render_saved(file,folder/'render',state['capabilities'],state['objectives']['render_width'])
        candidate['preview']=a._file(task,folder/'render/Final_preview.png');candidate['render']=a._file(task,folder/'render/render.json');candidate['render_environment']=state['capabilities']['fingerprint']
        state['stage']='review';a._save(task,state)
    task,state=a._state(task);contract,ledger=c._load(task,state)
    from .component_transactions import apply_post_save
    from .common import writer
    apply_post_save(task,state,ledger,tx,candidate)
    with writer(task):c._save_ledger(task,state,ledger,'transaction_postconditions_saved',{'id':tx['id']})
    c.qualify_constructed_fixed(task,affected)
    task,state=a._state(task);contract,ledger=c._load(task,state)
    if not display_required or candidate.get('preview'):
        release_local(task,state,ledger,tx)
        from .common import writer
        with writer(task):c._save_ledger(task,state,ledger,'transaction_local_ready',{'id':tx['id']})
    else:
        phase(task,tx,'DISPLAY_PENDING',candidate=candidate)
        from .common import writer
        with writer(task):c._save_ledger(task,state,ledger,'transaction_display_pending',{'id':tx['id']})
    a._event(task,'component_native_constructed',{'pptx':candidate['pptx'],'whole_audit_executed':False})
    return candidate


def build_task(task,request=None):
    from . import agent_runtime as a,component_workflow as c
    task,state=a._state(task);contract,ledger=c._load(task,state)
    if not contract:raise ValueError('Freeze the original component contract before construction')
    if contract.get('design_revision',0)<8:
        return {'status':'COMPONENT_MIGRATION_REQUIRED','action':'component-workflow migrate','whole_audit_executed':False}
    pending=state.get('component_import_pending')
    if pending:
        current=c._candidate(state)
        if current['pptx']['sha256']!=pending['baseline']['pptx']['sha256']:
            raise ValueError('Resume the saved import transaction before another completion')
        candidate=construct(task,state,read_json(c._resource(task,pending['scene'])),pending['baseline'],
                            pending['allowed'],pending['reason'])
        return {'status':'PARTIAL_PPT_COMPLETION_SAVED' if candidate else 'FONT_BINDING_REQUIRED',
                'candidate':candidate,'whole_audit_executed':False}
    if c._candidate(state):raise ValueError('Preserve saved work; use a scoped local transaction')
    if state.get('input_pptx'):
        from .component_import import adopt
        return adopt(task,c._resource(task,state['input_pptx']),
            {'source_hash':state['source']['sha256'],'expected_pptx_sha256':state['input_pptx']['sha256']})
    candidate=construct(task,state,read_json(c._resource(task,contract['source_scene'])))
    return {'status':'NATIVE_CANDIDATE_SAVED' if candidate else 'FONT_BINDING_REQUIRED','candidate':candidate,
            'whole_audit_executed':False,'office_behavior_executed':False}


def accept_font_provider(task,result):
    """Preserve the pending font candidate; journal a new immutable font copy."""
    import shutil
    from . import agent_runtime as a,component_workflow as c,font_contract as fonts
    from .font_embedding import transfer_provider
    from .component_transactions import saved,phase
    from .common import digest,writer
    task,state=a._state(task);contract,ledger=c._load(task,state);candidate=c._candidate(state)
    provider=result.get('font_provider',{});file=safe_path(task,provider.get('path',''))
    original=c._resource(task,candidate['pptx'])
    if (provider.get('input_sha256')!=candidate['pptx']['sha256'] or not file.is_file() or
        digest(file)!=provider.get('sha256') or file.resolve()==original.resolve()):
        raise ValueError('Font provider must bind the immutable input and a separate staged output')
    tx=read_json(safe_path(task,ledger['pending_transaction']['path']))
    attempts=tx.setdefault('font_provider_attempts',[])
    if len(attempts)>=contract['policy'].get('recovery_attempt_limit',3):
        raise ValueError('FONT_PROVIDER_INSPECTION_REQUIRED: bounded provider attempts retained')
    folder=safe_path(task,tx['path']).parent/('font-provider-'+identity(provider)[:20]+'-'+str(len(attempts)+1))
    attempts.append(folder.relative_to(task).as_posix());phase(task,tx,tx['phase'],font_provider_attempts=attempts)
    folder.mkdir(exist_ok=False);output=folder/'drawing.pptx';shutil.copyfile(original,output)
    scene=read_json(c._resource(task,candidate['scene']))
    embedded=transfer_provider(output,file,fonts.current_bindings(scene))
    updated=copy.deepcopy(candidate)
    updated.update(pptx=c._ref(task,output),font_delivery={'binding':fonts.guard_saved(scene,output),'embedding':embedded})
    updated.pop('preview',None);updated.pop('render',None)
    tx.setdefault('prior_candidate_hashes',[]).append(candidate['pptx']['sha256'])
    saved(task,tx,updated)
    phase(task,tx,'DISPLAY_PENDING',candidate=updated)
    state.update(active_candidate=updated,scene=updated['scene'],stage='host_render',packet=None)
    with writer(task):a._save(task,state)
    return {'status':'FONT_RESOURCES_SAVED_ACTUAL_RENDER_REQUIRED','candidate':updated,
            'whole_audit_executed':False,'office_behavior_executed':False}


def retain_render_failure(task,result):
    from . import agent_runtime as a,component_workflow as c
    from .common import writer
    task,state=a._state(task);contract,ledger=c._load(task,state);candidate=c._candidate(state)
    ref=result['render_failure'];failure=read_json(c._resource(task,ref))
    if failure.get('pptx_hash',failure.get('input_sha256'))!=candidate['pptx']['sha256']:
        raise ValueError('Render failure must identify the current native input')
    ledger.setdefault('render_failures',[]).append({'candidate':candidate['pptx'],'failure':ref})
    state.update(stage='host_render',packet=None)
    with writer(task):c._save_ledger(task,state,ledger,'actual_render_failed',{'failure':ref})
    return {'status':'ACTUAL_RENDER_RECOVERY_REQUIRED','candidate':candidate,'failure':ref,
            'native_rebuild_required':False,'whole_audit_executed':False}
