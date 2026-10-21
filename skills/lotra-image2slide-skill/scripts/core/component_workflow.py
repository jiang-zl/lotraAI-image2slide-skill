"""Integrated component-first task coordinator; final visual audit is deferred.

The existing Scene/native writers/render receipts remain authoritative.
Contracts are source decisions, not passes. Ledger qualifications have exact
facet dependencies. Office behavior exclusions are recorded, never scored.
"""
import copy
import json
import time
from uuid import uuid4
from pathlib import Path
from .common import read_json, write_json, digest, identity, safe_path, writer, ROOT
from .component_protocol import VERSION as CONTRACT_VERSION, FACETS, facets, policy
from .component_protocol import validate_contract, metric_result, impact, ready_for_final
from .component_solver import rank_actions

VERSION = 'component-workflow-1.32.0'
from .spatial_frames import reference


def implementation():
    names = ('component_actions','component_search','component_dependencies','component_transactions',
             'component_revision','component_batch','component_metric_adapters','component_user_sync','component_import','rebuild_existing',
             'component_features','component_fields','component_native_plan','component_font_instances','native_scope','native_ownership','font_collection','component_fonts','font_retention','font_resources',
             'component_variants','constructor_registry','state_repository','tables','native_input',
             'component_protocol','component_workflow','component_solver','component_metrics',
             'component_relations','component_fit','component_final','component_constructor','component_instances','component_calibration','native_core_checks',
             'native_core_inspect','boundary_geometry','neighbor_geometry','native_snapshot',
             'font_contract','font_embedding','geometry','mathml','presets','semantic_curves',
             'render','host_render','office_bridge','tool_router','native_commit',
             'agent_runtime','quality_loop','workflow_control','execution_contract','build',
             'curve_functions','problem_control','knowledge_flow','component_source_features','native_surfaces','surface_metrics',
             'spatial_frames','spatial_checks','spatial_constructors','spatial_observation',
             'spatial_footprints','spatial_fit','spatial_repair','presentation_backend','office_compatibility','export_destination','libreoffice_backend',
             'workflow_guard','incremental_contract','workflow_delivery')
    files={name:digest(ROOT/'scripts/core'/(name+'.py')) for name in names}
    for name in ('config/component-workflow.json','config/font-collections.json','schemas/component-contract.schema.json','scripts/sci_rebuild.py','scripts/check_before_finish.py'):
        files[name]=digest(ROOT/name)
    return identity(files)


def actual_render(task, state, candidate, independent=False):
    """A preview path alone does not prove that it renders these native bytes."""
    for key in ('pptx','preview','render'): _resource(task,candidate[key])
    receipt=read_json(_resource(task,candidate['render']))
    if (receipt.get('status') != 'PASS' or receipt.get('backend') not in ('PowerPoint','WPS','LibreOffice') or
        receipt.get('pptx_hash') != candidate['pptx']['sha256'] or receipt.get('preview_hash') != candidate['preview']['sha256']):
        raise ValueError('Actual preview belongs to another saved candidate')
    if candidate.get('render_environment')!=state['capabilities'].get('fingerprint'):
        raise ValueError('ACTUAL_RENDER_REQUIRED: current renderer environment differs from the saved display')
    # Existing host/portable render submission already verifies the receipt.
    # Recheck the same declared artifact hashes here, without opening Office.
    if independent:
        if receipt.get('scope')=='host_observed_target_render_only':
            from .host_render import verify_render
            verify_render(_resource(task,candidate['pptx']),_resource(task,candidate['preview']),receipt)
        else:
            from .native_capture_batch import verify_actual_render
            verify_actual_render(_resource(task,candidate['pptx']),_resource(task,candidate['render']))
    return receipt


def enabled(state):
    return state.get('objectives', {}).get('component_first') is True


def _ref(task, file):
    file = Path(file).resolve()
    return {'path': file.relative_to(task).as_posix(), 'sha256': digest(file)}


def _resource(task, ref):
    file = safe_path(task, ref['path'])
    if not file.is_file() or digest(file) != ref['sha256']:
        raise ValueError('Component resource changed: ' + ref['path'])
    return file


def _candidate(state):
    return state.get('active_candidate') or state.get('selected')


def _load(task, state, allow_policy_change=False):
    record = state.get('component_workflow')
    if not record: return None, None
    contract = read_json(_resource(task, record['contract']))
    ledger = read_json(safe_path(task, record['ledger_path']))
    if ledger.get('contract_hash') != record['contract']['sha256']:
        raise ValueError('Component ledger belongs to another source contract')
    if contract['source_hash'] != state['source']['sha256']:
        raise ValueError('Component source changed')
    if contract.get('design_revision',0)>8: raise ValueError('Unsupported future component contract')
    refs=[contract['source_scene'],contract['authority']]
    for ref in {r['path']:r for r in refs}.values():_resource(task,ref)
    return contract, ledger


def _save_ledger(task, state, ledger, event, details=None):
    from . import agent_runtime as a
    file = safe_path(task, state['component_workflow']['ledger_path'])
    ledger['events'].append({'sequence': len(ledger['events'])+1, 'kind': event,
                             'details': details or {}})
    from .state_repository import store_document
    store_document(file,ledger,task=task)
    from .state_repository import Repository,LazyDict
    components=ledger['components']
    Repository(task).index_rows('component_state',dict(dict.items(components)) if isinstance(components,LazyDict) else components)
    state['packet'] = None
    a._event(task, 'component_' + event, details or {})
    a._save(task, state)


def failure_decision(task, state, contract, ledger, candidate, checks, row=None, reason=None):
    """Persist the failure and its next legal source/measurement operation together."""
    def invalid(value):
        if isinstance(value,dict):
            return value.get('valid') is False or value.get('status') in ('MEASUREMENT_REQUIRED','MEASUREMENT_INVALID') or any(invalid(v) for v in value.values())
        return isinstance(value,list) and any(invalid(v) for v in value)
    status = 'MEASUREMENT_DIAGNOSIS_REQUIRED' if invalid(checks) else 'SOURCE_DECISION_REQUIRED'
    names = [row['id']] if row else []
    if not names:
        names = [r['id'] for r in contract['components'] if not r.get('parent')][:1]
    file=task/'component-workflow'/('Failure-checks-'+identity(checks)+'.json')
    if not file.exists():write_json(file,checks)
    decision = {'status':status,'components':names,'global':row is None,'checks':_ref(task,file),
        'source_hash':state['source']['sha256'],'pptx_hash':candidate['pptx']['sha256'],
        'reason':reason or 'Resolve the located source/native/measurement failure before another drawing action'}
    for name in names:
        ledger['components'][name].update(status=status,source_decision=copy.deepcopy(decision))
    ledger.update(pending_decision=decision,layout_ready=False,final_dirty=True,final_result=None)
    if ledger.get('repair_batch'):
        ledger['repair_batch']['status']='DIAGNOSIS_REQUIRED' if status=='MEASUREMENT_DIAGNOSIS_REQUIRED' else 'SOURCE_DECISION_REQUIRED'
    with writer(task):_save_ledger(task,state,ledger,'failure_decision_required',decision)
    return {**decision,'acceptance':False,'best_retained':True,'native_writes_granted':False}


def bind(task, request, *, prepare_only=False, native_apply=None):
    from .workflow_guard import require
    require(task,'bind')
    from . import agent_runtime as a
    task, state = a._state(task)
    from .tables import normalize_scene
    raw_scene = read_json(_resource(task, request['source_scene']))
    from .knowledge_flow import expand
    scene = normalize_scene(expand(task, state, copy.deepcopy(raw_scene), request))
    contract = copy.deepcopy(request['contract'])
    previous, _ = _load(task, state) if state.get('component_workflow') else (None, None)
    # Old contracts keep their policy until an explicit migration request.
    contract.setdefault('workflow_version', (previous or {}).get('workflow_version', '1.35.2'))
    if not previous and contract['workflow_version'] != '1.35.2':
        raise ValueError('New v1.35 tasks cannot bypass spatial/feature contracts with a legacy policy')
    if previous and previous.get('workflow_version') != contract['workflow_version']:
        if not request.get('migrate_spatial') or contract['workflow_version'] != '1.35.2':
            raise ValueError('Old tasks retain policy; an explicit migrate_spatial source rebind is required')
    from .spatial_frames import prepare_binding
    prepare_binding(task, state, contract)
    recompiled_owners=set()
    if previous and contract.get('workflow_version') in ('1.35.1','1.35.2'):
        from .native_surfaces import revise_scene
        permitted={o for r in previous['components']+contract['components'] for o in r['owners']}
        scene,recompiled_owners=revise_scene(scene,previous,contract,permitted)
    from .native_surfaces import expand as expand_surfaces
    if contract.get('workflow_version') in ('1.34.0', '1.35.0', '1.35.1','1.35.2'):
        scene = expand_surfaces(scene, contract)
    from .curve_functions import prepare as prepare_curves
    from .problem_control import bind as bind_problems
    scene = prepare_curves(task, state, contract, scene, execute=False)
    from .scene import validate
    validate(scene,task)
    if scene['source']['sha256']!=state['source']['sha256'] or [scene['canvas']['width'],scene['canvas']['height']]!=state['source_size']:
        raise ValueError('Frozen source Scene must retain the original identity and canvas')
    from .component_calibration import source_tolerance
    from .constructor_registry import select,precision_inputs
    from .component_dependencies import source_region
    if contract.get('design_revision',8)>8:raise ValueError('Unsupported future component design revision')
    contract['design_revision']=8
    nodes={n['id']:n for n in scene['objects']}
    for row in contract.get('components',[]):
        select(row,nodes)
        row['source_region_key']=source_region(task,state,row)
        for metric in row.get('metrics',[]):
            calibration=metric.get('source_calibration')
            if calibration:
                calibration=precision_inputs(metric,row,scene)
                model=policy().get('calibration_models',{}).get(calibration.pop('model',None))
                if not model or metric.get('unit')!=model['unit']:
                    raise ValueError('Select a predeclared type/unit calibration model')
                if calibration.get('coefficients') is not None and calibration['coefficients']!=model['coefficients']:
                    raise ValueError('Source decisions cannot loosen the predeclared calibration coefficients')
                calibration['coefficients']=model['coefficients']
                frozen=source_tolerance(**calibration)
                if frozen['status']!='FROZEN_SOURCE_TOLERANCE':raise ValueError('SOURCE_DECISION_REQUIRED: original uncertainty exceeds its allowed range')
                if metric.get('threshold') is not None and metric['threshold']!=frozen['value']:raise ValueError('Target conflicts with source calibration')
                metric['threshold']=frozen['value'];metric['calibration_result']=frozen
    from .component_source_features import bind as bind_features
    bind_features(task, state, contract, scene)
    if contract.get('workflow_version') in ('1.35.1','1.35.2'):
        from .spatial_fit import prepare as prepare_spatial_fit
        previous_spatial_rows={r['id']:r for r in (previous or {}).get('components',[])}
        for row in contract['components']:
            prepare_spatial_fit(contract,row,scene,previous_spatial_rows.get(row['id']))
            select(row,nodes)
    if contract.get('workflow_version') in ('1.35.0', '1.35.1','1.35.2'):
        from .spatial_constructors import validate_instances
        validate_instances(contract)
    validate_contract(contract, scene, state['source']['sha256'])
    for component in contract['components']:
        for ref in component['source_refs']: _resource(task, ref)
        for key in ('support_mask',):
            if component.get(key): _resource(task,component[key])
    existing = state.get('component_workflow')
    if existing:
        _,old_ledger=_load(task,state,allow_policy_change=True)
        if old_ledger.get('pending_transaction'):raise ValueError('Recover before rebinding a source contract')
    if existing and not request.get('revision_reason'):
        raise ValueError('Retain the previous contract and explain a source/scope revision')
    source_ref = copy.deepcopy(state['source']); _resource(task, source_ref)
    contract['source_scene'] = request['source_scene']
    contract['authority'] = request['authority']
    _resource(task, contract['authority'])
    contract['policy'] = policy()
    if prepare_only:return {'contract':contract,'source_scene':scene}
    if recompiled_owners and native_apply is None and _candidate(state):
        # A corrected common frame must produce a concrete scoped native plan,
        # rather than leave old compiled owners colliding during rebind or
        # strand fixed components with no way to apply the new projection.
        base=_candidate(state)
        current=read_json(_resource(task,base['scene']))
        proposed,changed_owners=revise_scene(current,previous,contract,permitted)
        file=task/'component-workflow'/('Spatial-source-rebind-'+identity(proposed)+'.json')
        write_json(file,proposed)
        old_rows={r['id']:r for r in previous['components']}
        scope=[r['id'] for r in contract['components']
               if (set(r['owners'])|set(old_rows.get(r['id'],{}).get('owners',[]))) & changed_owners]
        if not scope:raise ValueError('Source recompile needs explicit current component ownership')
        native_apply={'scene':_ref(task,file),'components':scope,
            'fields':[{'owner':o,'field':[]} for o in sorted(changed_owners)],
            'rebuild_owners':[],
            'previous_owners':{key:old_rows.get(key,{}).get('owners',[]) for key in scope}}
    bind_problems(task, state, contract, previous)
    scene=prepare_curves(task,state,contract,scene)
    folder = task / 'component-workflow'; folder.mkdir(exist_ok=True)
    if scene!=raw_scene:
        source_file=folder/('Source-scene-'+identity(scene)+'.json')
        if not source_file.exists():write_json(source_file,scene)
        contract['source_scene']=_ref(task,source_file)
    file = folder / ('Contract-' + identity(contract) + '.json')
    if not file.exists(): write_json(file, contract)
    ref = _ref(task, file)
    previous_contract, previous_ledger = _load(task, state,allow_policy_change=True) if existing else (None, None)
    previous_rows = {row['id']: row for row in previous_contract['components']} if previous_contract else {}
    components = {}
    for row in contract['components']:
        prior = (previous_ledger or {}).get('components', {}).get(row['id'])
        reusable=prior and previous_rows.get(row['id'])==row and prior.get('dependencies')==__import__(__package__+'.component_dependencies',fromlist=['consumer']).consumer(row,policy(),state)
        components[row['id']] = copy.deepcopy(prior) if reusable else {
            'component_id':row['id'],'status': 'PENDING', 'history': [], 'best': None, 'locked': {}, 'current': None}
        if prior:
            components[row['id']]['user_locks']=copy.deepcopy(prior.get('user_locks',[]))
            components[row['id']]['search_budgets']=copy.deepcopy(prior.get('search_budgets',{}))
            if not reusable:
                components[row['id']]['retained_bests']=copy.deepcopy(prior.get('retained_bests',[]))
                if prior.get('best'):
                    components[row['id']]['retained_bests'].append({'contract':existing['contract'],
                        'best':copy.deepcopy(prior['best']),'reason':request.get('revision_reason'),
                        'current_qualification':False})
        if prior and previous_rows.get(row['id'],{}).get('source_region_key')==row.get('source_region_key'):
            choices=copy.deepcopy(prior.get('source_model_choices',[]))
        else:choices=[]
        model_key=identity({'model':row.get('model'),'fit':row.get('fit')})
        if model_key not in choices:choices.append(model_key)
        if len(choices)>3:raise ValueError('SOURCE_DECISION_REQUIRED: three source-supported models exhausted')
        components[row['id']]['source_model_choices']=choices
    removed=set(previous_rows)-{r['id'] for r in contract['components']}
    orphan_locks=copy.deepcopy((previous_ledger or {}).get('orphan_user_locks',[]))
    for key in removed:
        orphan_locks.extend(previous_ledger['components'][key].get('user_locks',[]))
    ledger = {'schema': VERSION, 'contract_hash': ref['sha256'], 'source_hash': source_ref['sha256'],
              'components': components, 'relations': {}, 'layout_ready': False,
              'final_dirty': True, 'events': [], 'action_history': {}, 'pending_transaction': None,
              'final_result': None}
    if previous_contract:
        changes={row['id']:['assembly','geometry'] for row in contract['components'] if previous_rows.get(row['id'])!=row}
        affected=impact(contract,changes)
        for key in affected['components']:
            if components[key]['status']=='QUALIFIED':components[key]['status']='RECHECK_REQUIRED'
            components[key].pop('instantiation',None)
    ledger['implementation'] = implementation()
    all_locks=orphan_locks+[lock for record in components.values() for lock in record.get('user_locks',[])]
    all_locks=list({identity({'owner':v['owner'],'field':v['field']}):v for v in all_locks}.values())
    owned={owner:row['id'] for row in contract['components'] for owner in row['owners']}
    ledger['orphan_user_locks']=[copy.deepcopy(v) for v in all_locks if v['owner'] not in owned]
    for key,record in components.items():record['user_locks']=[copy.deepcopy(v) for v in all_locks if owned.get(v['owner'])==key]
    if previous_ledger:
        ledger['repair_batch']=copy.deepcopy(previous_ledger.get('repair_batch'))
        if previous_ledger.get('pending_decision'):
            ledger['repair_batch']=None
            for name in previous_ledger['pending_decision'].get('components',[]):
                if name in components:
                    components[name]['status']='RECHECK_REQUIRED'
                    components[name].pop('source_decision',None)
        if any(r.get('spatial_repair_schedule') for r in previous_ledger['components'].values()):
            # Old plans remain in the retained previous ledger. Current checks
            # generate replacement failures instead of forcing a no-op edit.
            ledger['repair_batch']=None
            for record in components.values():
                if record.get('spatial_repair_schedule'):
                    record['status']='RECHECK_REQUIRED'
                    record.pop('source_decision',None)
                record.pop('spatial_repair_schedule',None)
                record.pop('repair_grant',None)
        ledger['user_reconciliation']=copy.deepcopy(previous_ledger.get('user_reconciliation'))
        for key in ('applied_post_save','lock_history'):
            if key in previous_ledger:ledger[key]=copy.deepcopy(previous_ledger[key])
        from .component_fonts import basis as font_basis
        prior_review=previous_ledger.get('font_review') or {}
        if prior_review.get('status')=='COMPLETE' and prior_review.get('basis')==font_basis(scene,state):
            ledger['font_review']=copy.deepcopy(prior_review)
    if native_apply:
        base=_candidate(state)
        ledger['structural_grant']={'components':native_apply['components'],'fields':native_apply['fields'],
            'source_hash':state['source']['sha256'],'pptx_hash':base['pptx']['sha256'],
            'contract':ref,'scene':native_apply['scene'],'rebuild_owners':native_apply.get('rebuild_owners',[])}
        for row in contract['components']:
            if row['id'] not in native_apply['components']:continue
            record=components[row['id']]
            record.update(status='SOURCE_DECISION_APPLY_REQUIRED',repair_base=base['pptx']['sha256'],
                repair_grant=[g for g in native_apply['fields'] if g['owner'] in
                    set(row['owners'])|set(native_apply['previous_owners'].get(row['id'],[]))],
                repair_context={'row':identity(row),'source':state['source']['sha256'],
                                'native':base.get('retained_pptx',base['pptx'])})
    if existing:
        ledger['migration'] = {'previous_contract':existing['contract'],
            'reason':request['revision_reason'],'previous_state_retained':True,
            'excluded_checks_are_passes':False}
    revision = len(state.get('component_workflow_history', []))+1+int(bool(existing))
    ledger_path = 'component-workflow/Ledger-' + str(revision) + '-' + uuid4().hex[:10] + '.json'
    with writer(task):
        if existing: state.setdefault('component_workflow_history', []).append(copy.deepcopy(existing))
        state['component_workflow'] = {'schema': VERSION, 'contract': ref,
                                       'ledger_path': ledger_path, 'revision_reason': request.get('revision_reason')}
        from .incremental_contract import seal_state
        seal_state(task,state,'binding')
        state['objectives']['component_first'] = True
        state.pop('source_observation_rebind_required', None)
        from .state_repository import Repository
        repository=Repository(task)
        repository.index_rows('component_contract:'+ref['sha256'],{row['id']:row for row in contract['components']})
        repository.index_rows('source_unit:'+ref['sha256'],{row['id']:row for row in contract['source_inventory']})
        if contract.get('source_observation'):
            observation = read_json(_resource(task, contract['source_observation']))
            repository.index_rows('source_feature:'+ref['sha256'],{f['id']:f for f in observation['features']})
        repository.index_rows('native_owner:'+ref['sha256'],{owner:{'component':row['id']} for row in contract['components'] for owner in row['owners']})
        _save_ledger(task, state, ledger, 'contract_bound', {'components': len(components), 'source_hash': source_ref['sha256']})
    return {'status': 'COMPONENT_CONTRACT_BOUND', 'components': len(components),
            'contract': ref, 'acceptance': False, 'action_references': [reference(contract)]}


def _signatures(task, state, candidate):
    from .native_core_checks import snapshots
    from .boundary_geometry import saved_nodes
    scene = read_json(_resource(task, candidate['scene']))
    native = snapshots(_resource(task, candidate['pptx']), component_mode=True)
    world = saved_nodes(_resource(task,candidate['pptx']),state['source_size'])
    result = {}
    for node in scene['objects']:
        values = facets(node)
        values['native_body'] = native.get(node['id'], {}).get('body')
        entry=world.get(node['id'],{})
        matrix=entry.get('matrix')
        values['native_placement'] = identity({'matrix':matrix.tolist() if matrix is not None else None,
            'error':entry.get('error'),'parent':entry.get('parent_name')})
        values['native_order'] = native.get(node['id'], {}).get('paint_order')
        values['bbox'] = node.get('bbox')
        if node['render_type']=='trace':
            children={name:{k:value[k] for k in ('body','placement')} for name,value in native.items()
                      if value.get('parent')==node['id']}
            values['native_body']=identity([values['native_body'],children])
        entry=native.get(node['id'])
        if entry:
            from lxml import etree as E
            from .mathml import NS
            xf=entry['node'].find('p:grpSpPr/a:xfrm' if node['render_type']=='group' else 'p:spPr/a:xfrm',NS)
            values['local_placement']=identity(E.tostring(xf).decode() if xf is not None else None)
        result[node['id']] = values
    return scene, result


def _component_signature(row, signatures, body=True, contract=None):
    keys = ('content', 'paint', 'geometry', 'native_body') if body else tuple(FACETS)+('native_body', 'native_placement')
    result={owner: {key: signatures.get(owner, {}).get(key) for key in keys} for owner in row['owners']}
    if row['route']=='assembly' and contract:
        # Mother qualification covers internal anatomy, independent of page pose.
        result={owner:{k:signatures.get(owner,{}).get(k) for k in ('content','paint','geometry','native_body')} for owner in row['owners']}
        descendants={row['id']}
        while True:
            expanded=descendants|{c['id'] for c in contract['components'] if c.get('parent') in descendants}
            if expanded==descendants: break
            descendants=expanded
        for child in contract['components']:
            if child['id'] in descendants-{row['id']}:
                for owner in child['owners']:
                    result[owner]={k:signatures.get(owner,{}).get(k) for k in ('content','paint','geometry','assembly','native_body','local_placement')}
    return result


def _measurement_signature(row,signatures,contract):
    """Source-ROI measurements depend on page pose as well as intrinsic anatomy."""
    intrinsic=_component_signature(row,signatures,contract=contract)
    return {'intrinsic':intrinsic,'placement':{owner:{key:signatures.get(owner,{}).get(key)
        for key in ('pose','assembly','native_placement')} for owner in intrinsic},
        'native_ancestors':{owner:signatures.get(owner,{}).get('native_placement')
                            for owner in row.get('spatial_context',{}).get('native_ancestors',[])}}


def invalidate_stale_final(task,state,contract,ledger,candidate):
    ref=ledger.get('final_result')
    if not ref:return False
    final=read_json(_resource(task,ref))
    current=(final.get('implementation')==implementation() and final.get('source_hash')==state['source']['sha256'] and
        final.get('contract')==state['component_workflow']['contract'] and final.get('pptx_hash')==candidate['pptx']['sha256'] and
        final.get('preview_hash')==candidate.get('preview',{}).get('sha256') and
        final.get('render_environment')==state['capabilities']['fingerprint'])
    if current:return False
    retained=ledger.setdefault('retained_final_results',[])
    if ref not in retained:retained.append(copy.deepcopy(ref))
    ledger.update(final_dirty=True,final_result=None)
    return True


def refresh(task, state, contract, ledger, candidate):
    """Only affected facets invalidate qualification; page changes mark final dirty."""
    if not candidate: return None, None
    invalidate_stale_final(task,state,contract,ledger,candidate)
    scene, signatures = _signatures(task, state, candidate)
    from .component_dependencies import consumer
    for row in contract['components']:
        record=ledger['components'][row['id']]
        dependencies=consumer(row,contract['policy'],state)
        from .component_fit import basis as fit_basis
        measured=_measurement_signature(row,signatures,contract)
        record['observed_measurement_signature']=measured
        record['probe_context']=fit_basis(row,contract['policy'],state,measured)
        probe=record.get('immediate_probe')
        if probe and probe.get('context')!=record['probe_context']:record.pop('immediate_probe',None)
        if record['status']=='NUMERIC_READY' and record.get('numeric_input_signature')!=measured:
            record['status']='RECHECK_REQUIRED'
        if record.get('dependencies')!=dependencies:
            if record['status']=='QUALIFIED': record['status']='RECHECK_REQUIRED'
            if record['status']=='NUMERIC_READY':record['status']='RECHECK_REQUIRED'
            record['dependencies']=dependencies
            affected=impact(contract,{row['id']:['geometry']})
            for name in affected['components']:
                if ledger['components'][name]['status']=='QUALIFIED':
                    ledger['components'][name]['status']='RECHECK_REQUIRED'
            for name in affected['relations']:ledger['relations'].pop(name,None)
            for name in affected['components']:
                if ledger['components'][name].get('instantiation',{}).get('candidate',{}).get('sha256')!=candidate['pptx']['sha256']:
                    ledger['components'][name].pop('instantiation',None)
            ledger.update(layout_ready=False,final_dirty=True,final_result=None)
    changed = {}
    previous_facets=ledger.get('last_facets',{})
    pose_changes={}
    for row in contract['components']:
        record = ledger['components'][row['id']]
        current = _component_signature(row, signatures, body=row['route'] not in ('assembly', 'instance'),contract=contract)
        if previous_facets and any(any(previous_facets.get(owner,{}).get(key)!=signatures.get(owner,{}).get(key)
                for key in ('pose','assembly','native_placement')) for owner in row['owners']):
            pose_changes[row['id']]=['pose']
            if row.get('spatial_basis') and record['status']=='QUALIFIED':
                record['status']='RECHECK_REQUIRED'
        if row.get('spatial_context',{}).get('native_ancestors') and previous_facets:
            if any(previous_facets.get(owner,{}).get('native_placement') != signatures.get(owner,{}).get('native_placement')
                   for owner in row['spatial_context']['native_ancestors']):
                if record['status']=='QUALIFIED':record['status']='RECHECK_REQUIRED'
        previous=record.get('qualified_signature') if record['status']=='QUALIFIED' else record.get('observed_signature')
        record['observed_signature']=current
        probe=record.get('immediate_probe')
        if probe and probe.get('signature')!=record['observed_measurement_signature']:record.pop('immediate_probe',None)
        if previous is not None and previous != current:
            changed[row['id']] = ['assembly'] if row['route']=='assembly' else ['pose'] if row['route']=='instance' else ['geometry']
    old_candidate = ledger.get('last_candidate')
    if old_candidate != candidate['pptx']['sha256']:
        ledger['last_candidate'] = candidate['pptx']['sha256']; ledger['final_dirty'] = True
        ledger['final_result'] = None
    if changed:
        affected = impact(contract, changed)
        for name in affected['components']:
            record = ledger['components'][name]
            if record['status'] == 'QUALIFIED': record['status'] = 'RECHECK_REQUIRED'
        for name in affected['relations']: ledger['relations'].pop(name, None)
        for name in affected['components']:
            if ledger['components'][name].get('instantiation',{}).get('candidate',{}).get('sha256')!=candidate['pptx']['sha256']:
                ledger['components'][name].pop('instantiation',None)
        ledger['layout_ready'] = False
        ledger['events'].append({'sequence': len(ledger['events'])+1, 'kind': 'local_invalidation',
                                 'details': {**affected, 'changed': changed}})
    if pose_changes:
        affected=impact(contract,pose_changes)
        for name in affected['components']:
            # An internal child move changes its mother's assembly and copies.
            if name not in pose_changes and ledger['components'][name]['status']=='QUALIFIED':
                ledger['components'][name]['status']='RECHECK_REQUIRED'
                if ledger['components'][name].get('instantiation',{}).get('candidate',{}).get('sha256')!=candidate['pptx']['sha256']:
                    ledger['components'][name].pop('instantiation',None)
        for name in affected['relations']: ledger['relations'].pop(name,None)
        ledger['layout_ready']=False
    if previous_facets:
        points={b['landmark']:b['owner'] for b in contract.get('spatial_bindings',[])}
        pairs=[('spatial:'+r['id'],[points[p] for p in r['landmarks']])
               for r in contract.get('spatial',{}).get('relations',[]) if r['kind']=='occludes']
        components={r['id']:r for r in contract['components']}
        pairs += [(r['id'],r.get('owners') or [components[k]['owners'][0] for k in r['components']])
                  for r in contract.get('relations',[]) if r['kind']=='layer_before']
        for name,owners in pairs:
            if len(owners)!=2:continue
            old=[previous_facets.get(o,{}).get('native_order') for o in owners]
            now=[signatures.get(o,{}).get('native_order') for o in owners]
            if None not in old+now and (old[0]<old[1])!=(now[0]<now[1]):
                ledger['relations'].pop(name,None)
                ledger.update(layout_ready=False,final_dirty=True,final_result=None)
    ledger['last_facets']=signatures
    return scene, signatures


def _check_nonpaint(task, candidate, contract):
    from .native_core_inspect import inventory, xml
    from .mathml import NS
    saved, duplicate = inventory(xml(_resource(task, candidate['pptx'])))
    if duplicate: raise ValueError('Ambiguous native identity')
    for owner in contract.get('nonpaint_owners', []):
        if owner not in saved: raise ValueError('Nonpaint owner absent')
        node = saved[owner]['node']; props = node.find('p:spPr', NS)
        if (props is None or props.find('a:noFill', NS) is None or
            props.find('a:ln/a:noFill', NS) is None or node.findall('.//a:t', NS) or
            node.findall('.//m:t', NS) or props.find('a:effectLst', NS) is not None):
            raise ValueError('Declared nonpaint owner actually paints: ' + owner)
    expected = {n for row in contract['components'] for n in row['owners']} | set(contract.get('nonpaint_owners', []))
    scene=read_json(_resource(task,candidate['scene']))
    from .native_ownership import check as ownership
    result=ownership(scene,task,saved)
    if {n['id'] for n in scene['objects']}!=expected:
        result.update(passed=False,reason='Semantic source owners differ from contract ownership')
    return result



def fixed_style_checks(task,candidate,contract,row,scene):
    """Source-fixed paint stays fixed while uncertain geometry is fitted."""
    from .native_core_checks import style_checks
    from .native_core_inspect import inventory,xml
    expected={n['id']:n for n in read_json(_resource(task,contract['source_scene']))['objects']}
    current={n['id']:n for n in scene['objects']};native,_=inventory(xml(_resource(task,candidate['pptx'])))
    checks=[]
    variable={}
    for name,binding in row.get('fit',{}).get('bindings',{}).items():
        if row.get('parameters',{}).get(name,{}).get('state')=='tunable' and binding['field'][0]=='style':
            variable.setdefault(binding['owner'],set()).add(binding['field'][1])
    for owner in row['owners']:
        wanted=copy.deepcopy(expected[owner]);actual=current[owner]
        for field in variable.get(owner,set()):wanted['style'][field]=actual['style'][field]
        from .component_fields import canonical_node
        equal=canonical_node(wanted)['style']==canonical_node(actual)['style'] and wanted['render_type']==actual['render_type']
        wanted['style']['font_faces']=copy.deepcopy(actual['style'].get('font_faces',{}))
        saved=style_checks(wanted,native[owner]['node'])
        checks.append({'owner':owner,'passed':equal and all(r['status']=='PASS' for r in saved),
                       'source_fixed_fields':equal,'saved_style':saved})
    return {'passed':all(r['passed'] for r in checks),'items':checks,'raster_measurement':False}


def qualify_constructed_fixed(task,owners):
    from . import agent_runtime as a
    task,state=a._state(task);contract,ledger=_load(task,state)
    selected=[row['id'] for row in contract['components'] if row['route']=='fixed_parameters'
              and set(row['owners'])<=set(owners) and ledger['components'][row['id']]['status']!='QUALIFIED']
    if selected:return evaluate(task,{'components':selected})


def evaluate(task, request=None):
    from .workflow_guard import require
    require(task,'evaluate')
    from . import agent_runtime as a
    from .component_metrics import measure
    from .native_core_checks import batch_check
    task, state = a._state(task); contract, ledger = _load(task, state)
    if not contract: return {'status': 'COMPONENT_CONTRACT_REQUIRED'}
    if contract.get('design_revision',0)<8:return {'status':'COMPONENT_MIGRATION_REQUIRED','action':'component-workflow migrate','whole_audit_executed':False}
    candidate = _candidate(state)
    if not candidate: return {'status': 'SAVED_CANDIDATE_REQUIRED'}
    scene, signatures = refresh(task, state, contract, ledger, candidate)
    inventory = _check_nonpaint(task, candidate, contract)
    if not inventory['passed']: return {'status': 'OWNERSHIP_RECONCILIATION_REQUIRED', 'inventory': inventory}
    frozen = read_json(_resource(task, contract['source_scene']))
    selected = set((request or {}).get('components', [row['id'] for row in contract['components']]))
    by_id={name:component_row(task,state,contract,name) for name in selected}
    if not selected <= {r['id'] for r in contract['components']}: raise ValueError('Unknown local component selection')
    report = []
    fixed_owners=[owner for name in selected for owner in by_id[name]['owners']
                  if by_id[name]['route']=='fixed_parameters' and ledger['components'][name]['status']!='QUALIFIED']
    fixed_checks=batch_check(scene,frozen,task,_resource(task,candidate['pptx']),fixed_owners,'body') if fixed_owners else {}
    for name in sorted(selected):
        row = by_id[name]; record = ledger['components'][name]
        sig = _component_signature(row, signatures, body=row['route'] not in ('assembly', 'instance'),contract=contract)
        if record['status'] == 'QUALIFIED' and record.get('qualified_signature') == sig:
            report.append({'id': name, 'status': 'QUALIFICATION_RETAINED', 'measured': False}); continue
        if row['route'] == 'fixed_parameters':
            checked = {owner:fixed_checks[owner] for owner in row['owners']}
            result = {'passed': all(value['status'] == 'PASS' for value in checked.values()),
                      'native_parameters': checked, 'route': row['route'], 'raster_measurement': False}
            if not result['passed']:result['status']='HARD_CONSTRAINT_FAILED'
        elif row['route'] == 'local_fit':
            actual_render(task,state,candidate)
            from .problem_control import reserve
            reserve(task, state, row, 'native_confirmations', token=candidate['pptx']['sha256'])
            measured = measure(task, state, candidate, row)
            result = metric_result(row, measured['metrics'])
            from .native_core_inspect import check
            structural=check(scene,task,_resource(task,candidate['pptx']),row['owners'],'body')
            result['native_checks']=structural
            fixed=fixed_style_checks(task,candidate,contract,row,scene);result['fixed_paint']=fixed
            result['passed']=result['passed'] and structural['status']=='PASS' and fixed['passed'] and all(measured['hard_checks'].values())
            if structural['status']!='PASS' or not fixed['passed']:result['status']='HARD_CONSTRAINT_FAILED'
            elif any(m['role']=='target' and m['status']=='MEASUREMENT_REQUIRED' for m in result['items']):result['status']='MEASUREMENT_REQUIRED'
            result.update(measurement=measured, route=row['route'])
        elif row['route'] == 'assembly':
            children = [child['id'] for child in contract['components'] if child.get('parent') == name]
            pending = [child for child in children if ledger['components'][child]['status'] != 'QUALIFIED']
            result = {'passed': False, 'status': 'ASSEMBLY_RELATIONS_REQUIRED', 'children_pending': pending,
                      'route': row['route']}
        else:
            result = {'passed': False, 'status': 'SPECIALIST_OR_INSTANCE_EVIDENCE_REQUIRED', 'route': row['route']}
        if contract.get('workflow_version') in ('1.34.0', '1.35.0', '1.35.1','1.35.2'):
            from .component_source_features import source_check
            source_basis = source_check(row)
            result['source_basis'] = source_basis
            result['qualification_channels'] = {'source_basis':source_basis['passed'],
                'native_consistency':result.get('native_checks',{}).get('status')=='PASS' if row['route']=='local_fit' else result.get('passed',False),
                'appearance':'DEFERRED_TO_ASSEMBLY_AND_FINAL' if row['route']=='fixed_parameters' else result.get('passed',False)}
            result['passed'] = result['passed'] and source_basis['passed']
            if not source_basis['passed']: result['status'] = source_basis['status']
        if contract.get('workflow_version') in ('1.35.0', '1.35.1','1.35.2'):
            from .spatial_checks import evaluate as spatial_evaluate
            spatial = spatial_evaluate(task, state, candidate, contract, row)
            result['spatial_native'] = spatial
            result['passed'] = result['passed'] and spatial['passed']
            if not spatial['passed']:
                if not spatial['valid']:result['status']='MEASUREMENT_REQUIRED'
                elif result.get('status') not in ('HARD_CONSTRAINT_FAILED','SOURCE_AMBIGUITY_REQUIRED','SPATIAL_SOURCE_DECISION_REQUIRED'):
                    result['status']='SPATIAL_RELATIONS_UNMET'
        record['current'] = {'signature': sig, 'result': result, 'candidate_hash': candidate['pptx']['sha256']}
        record['history'].append(copy.deepcopy(record['current']))
        if result['passed']:
            record.update(status='QUALIFIED', qualified_signature=sig, best=copy.deepcopy(record['current']))
            if row['route'] != 'instance': record['locked'] = {key: sig for key in ('content', 'paint', 'geometry')}
        else: record['status'] = result.get('status', 'LOCAL_TARGETS_UNMET')
        from .knowledge_flow import local_feedback
        local_feedback(state,scene,row,result,candidate)
        from .component_transactions import local_result
        record['component_id']=name
        local_result(task,record,result['passed'])
        report.append({'id': name, 'status': record['status'], 'result': result, 'measured': True})
    invalid=[item for item in report if item.get('status') in ('MEASUREMENT_REQUIRED','MEASUREMENT_INVALID','MEASUREMENT_DIAGNOSIS_REQUIRED')]
    if invalid:
        item=invalid[0]
        decision=failure_decision(task,state,contract,ledger,candidate,item['result'],by_id[item['id']])
        return dict(decision,items=report,whole_audit_executed=False)
    with writer(task): _save_ledger(task, state, ledger, 'local_evaluated', {'components': sorted(selected)})
    return {'schema': VERSION, 'status': 'LOCAL_EVALUATED', 'items': report,
            'whole_audit_executed': False, 'office_behavior_executed': False,
            'ready': ready_for_final(contract, ledger, state)}


def qualify(task, request):
    from .workflow_guard import require
    require(task,'qualify')
    """Assembly/instance/specialist evidence is bound to actual current output."""
    from . import agent_runtime as a
    task, state = a._state(task); contract, ledger = _load(task, state); candidate = _candidate(state)
    if not contract or not candidate: raise ValueError('Current component contract and saved candidate required')
    if request.get('source_hash') != state['source']['sha256'] or request.get('pptx_hash') != candidate['pptx']['sha256']:
        raise ValueError('Qualification requires current source and candidate')
    _, signatures = refresh(task, state, contract, ledger, candidate)
    rows = {row['id']: row for row in contract['components']}
    name = request['component']; row = component_row(task,state,contract,name)
    if row['route'] in ('fixed_parameters', 'local_fit'):
        raise ValueError('Fixed/numeric parts use the executable evaluate route')
    children = [child['id'] for child in contract['components'] if child.get('parent') == name]
    if any(ledger['components'][child]['status'] != 'QUALIFIED' for child in children):
        raise ValueError('Qualify actual child parts before assembly')
    if row.get('mother') and ledger['components'][row['mother']]['status'] != 'QUALIFIED':
        raise ValueError('Instance requires a qualified mother')
    evidence = request.get('evidence'); _resource(task, evidence)
    actual = read_json(_resource(task, evidence))
    if (actual.get('source_hash') != state['source']['sha256'] or
        actual.get('pptx_hash') != candidate['pptx']['sha256'] or actual.get('component') != name):
        raise ValueError('Evidence does not describe this actual component')
    checks = program_checks(task,state,candidate,contract,row)
    if not all(check.get('passed') is True for check in checks.values()):
        return failure_decision(task,state,contract,ledger,candidate,checks,row)
    if row.get('visual_review_required', True) or contract.get('workflow_version') in ('1.34.0', '1.35.0', '1.35.1','1.35.2'):
        actual_render(task,state,candidate)
        if not candidate.get('preview') or actual.get('preview_hash') != candidate['preview']['sha256']:
            raise ValueError('Assembly visual evidence must bind the actual current preview')
        if actual.get('observer') not in ('host_model', 'human') or not actual.get('observations'):
            raise ValueError('Actual original/current local visual observations required')
        if actual.get('verdict') != 'PASS':
            return failure_decision(task,state,contract,ledger,candidate,{'visual':actual,'evidence':evidence},row,
                'Revise the located source/native decision from this current local visual failure')
        if contract.get('workflow_version') in ('1.34.0', '1.35.0', '1.35.1','1.35.2'):
            from .component_source_features import local_review
            feature_review = local_review(row, actual)
            if not feature_review['passed']:
                return failure_decision(task,state,contract,ledger,candidate,{'feature_review':feature_review},row)
            checks['feature_appearance'] = feature_review
    sig = _component_signature(row, signatures, body=row['route'] not in ('assembly', 'instance'),contract=contract)
    record = ledger['components'][name]
    current = {'signature': sig, 'evidence': evidence, 'program_checks':checks,'candidate_hash': candidate['pptx']['sha256']}
    record['history'].append(current); record.update(status='QUALIFIED', current=current,
        best=copy.deepcopy(current), qualified_signature=sig)
    if row['route'] == 'assembly': record['locked'] = {'anatomy': sig}
    from .component_transactions import local_result
    record['component_id']=name
    local_result(task,record,True)
    from .knowledge_flow import capture_qualified
    scene = read_json(_resource(task,candidate['scene']))
    capture_qualified(task,state,contract,ledger,scene)
    with writer(task): _save_ledger(task, state, ledger, 'assembly_qualified', {'component': name})
    return {'status': 'COMPONENT_QUALIFIED', 'component': name, 'whole_acceptance': False}


def layout(task, request):
    from .workflow_guard import require
    require(task,'layout')
    from . import agent_runtime as a
    task, state = a._state(task); contract, ledger = _load(task, state); candidate = _candidate(state)
    if not contract or not candidate: raise ValueError('Current component drawing required')
    refresh(task, state, contract, ledger, candidate)
    if any(row['status'] != 'QUALIFIED' for row in ledger['components'].values()):
        raise ValueError('Finish parts, assemblies and instances before final layout readiness')
    evidence = request['evidence']; actual = read_json(_resource(task, evidence))
    if actual.get('pptx_hash') != candidate['pptx']['sha256'] or actual.get('source_hash') != state['source']['sha256']:
        raise ValueError('Layout evidence belongs to another drawing')
    from .component_relations import evaluate as evaluate_relations,source_placement
    evaluated=evaluate_relations(task,state,candidate,contract)
    checks=evaluated['items']
    if not evaluated['passed']:
        if any(item.get('valid') is False for item in checks.values()):
            return failure_decision(task,state,contract,ledger,candidate,evaluated)
        from .component_revision import queue_final_repair
        queue_final_repair(ledger,['layout_relation:'+key for key,value in checks.items() if not value['passed']],evidence)
        with writer(task):_save_ledger(task,state,ledger,'layout_repair_required',{'checks':evaluated})
        return {'status':'LAYOUT_RELATIONS_UNMET','checks':evaluated,'next':'component repair plan'}
    placed=source_placement(task,state,candidate,contract)
    if not placed['passed']:
        if not placed.get('valid',True):
            return failure_decision(task,state,contract,ledger,candidate,placed)
        from .component_revision import queue_final_repair
        queue_final_repair(ledger,['layout_owner:'+v['owner'] for v in placed['items'] if not v['passed']],evidence)
        with writer(task):_save_ledger(task,state,ledger,'layout_repair_required',{'checks':placed})
        return {'status':'SOURCE_LAYOUT_UNMET','checks':placed,'next':'component repair plan'}
    if contract.get('workflow_version') in ('1.35.0', '1.35.1','1.35.2'):
        from .spatial_checks import evaluate as spatial_evaluate
        spatial = spatial_evaluate(task,state,candidate,contract)
        if not spatial['passed']:
            if not spatial['valid']:
                return failure_decision(task,state,contract,ledger,candidate,spatial)
            from .component_revision import queue_final_repair
            failures=['spatial_relation:'+k for k,v in spatial['relations'].items() if not v['passed']]
            failures += ['spatial_anchor:'+k for k,v in spatial['anchors'].items() if not v['passed']]
            failures += ['spatial_footprint:'+k for k,v in spatial.get('footprints',{}).items() if not v['passed']]
            queue_final_repair(ledger,failures,evidence)
            with writer(task):_save_ledger(task,state,ledger,'spatial_layout_repair_required',{'checks':spatial})
            return {'status':'SPATIAL_LAYOUT_UNMET','checks':spatial,'next':'component repair plan'}
        ledger['spatial_layout'] = spatial
    if not actual.get('layout_observations'): raise ValueError('Located layout observations required')
    ledger['relations'] = {key: {'status': 'QUALIFIED', 'evidence': evidence,'result':result} for key,result in checks.items()}
    ledger['layout_ready'] = True
    ledger['layout_evidence']=evidence
    ledger['layout_placement']=placed
    with writer(task): _save_ledger(task, state, ledger, 'layout_ready', {'relations': len(checks)})
    return {'status': 'LAYOUT_READY', 'ready': ready_for_final(contract, ledger, state)}


def status(task):
    from . import agent_runtime as a
    task, state = a._state(task); contract, ledger = _load(task, state)
    if not contract:
        result={'status':'COMPONENT_CONTRACT_REQUIRED','enabled':enabled(state)}
        from .workflow_guard import enabled as controlled
        if controlled(state):
            from .incremental_contract import source_phase,load,visible_counts
            phase=source_phase(task,state)[0] if not state.get('source_feature_observation') else 'bind_chunk'
            result.update(execution_policy=state['execution_policy'],phase=phase,coverage=visible_counts(load(task,state)),
                next_action='next '+str(task),acceptance=False)
        return result
    refresh(task, state, contract, ledger, _candidate(state))
    write_json(safe_path(task,state['component_workflow']['ledger_path']),ledger)
    return {'schema': VERSION, 'status': 'COMPONENT_WORKFLOW', 'source_hash': state['source']['sha256'],
            'counts': {key: sum(row['status'] == key for row in ledger['components'].values())
                       for key in sorted({row['status'] for row in ledger['components'].values()})},
            'pending': [key for key, row in ledger['components'].items() if row['status'] != 'QUALIFIED'],
            'ready': ready_for_final(contract, ledger, state), 'final_dirty': ledger['final_dirty'],
            'excluded_checks': contract.get('scope', {}).get('excluded_checks', []),
            'action_references': [reference(contract)]}


def next_action(task, state, candidate=None):
    """Called by the ordinary next/quality entry, not a parallel task engine."""
    from . import agent_runtime as a
    contract, ledger = _load(task, state); candidate = candidate or _candidate(state)
    if state.get('source_observation_rebind_required'):
        packet=a._packet(task,state,'component_contract_source','component_contract',
            'Rebind only the affected source-feature correspondences; retain prior work, budgets and locks.',
            extra={'source_observation':state['source_feature_observation'],
                   'previous_contract':state['component_workflow']['contract'],
                   'action_references':[reference(contract)],'whole_audit_allowed':False})
        return {'status':'WORK_PACKET','packet':packet}
    if state.get('spatial_source_decision'):
        from .problem_control import remaining
        rows={r['id']:r for r in contract['components']}
        exhausted=[name for name in state['spatial_source_decision']['components'] if remaining(task,state,rows[name],'source_reads')==0]
        if exhausted:
            return {'status':'ORIGINAL_PROBLEM_UNRESOLVED','components':exhausted,
                    'best_retained':True,'acceptance':False,'reason':'Located shared-frame source-read budget exhausted',
                    'spatial_source_decision':state['spatial_source_decision']}
        packet=a._packet(task,state,'component_contract_source','source_features',
            'Resolve the located common-frame/projection interpretation against the unchanged original. Submit a complete retained observation with revision_reason and spatial_corrections; preserve independent targets and bounds, then rebind every actual consumer.',
            extra={'source_hash':state['source']['sha256'],'source':state['source'],
                   'source_observation':state.get('source_feature_observation'),
                   'spatial_source_decision':state['spatial_source_decision'],
                   'action_references':[reference(contract)],'whole_audit_allowed':False})
        return {'status':'WORK_PACKET','packet':packet}
    if ledger and ledger.get('pending_decision'):
        decision=ledger['pending_decision'];name=decision['components'][0]
        global_decision=decision.get('global',False)
        packet=a._packet(task,state,'component_contract_source' if global_decision else 'component_local_work',
            'component_contract' if global_decision else name,
            'Resolve the retained source/measurement failure; drawing and acceptance remain blocked until a valid rebind.',
            extra={'component_batch':[name],'submit_operation':'source_or_measurement_decision',
                'source_decision':decision,'previous_contract':state['component_workflow']['contract'],
                'source_scene':contract['source_scene'],'action_references':[reference(contract)],
                'component_action':{'operation':'source_or_measurement_decision'},'whole_audit_allowed':False})
        return {'status':'WORK_PACKET','packet':packet}
    if not contract:
        if not state.get('source_feature_observation'):
            packet=a._packet(task,state,'component_contract_source','source_features',
                'Observe the unchanged original before native owners. Submit source-features-1.35.1 recursive units, visible features, hierarchical spatial classifications, frames, observable pose/support/face-centering targets, uncertainty and decomposition stops; do not derive targets from a candidate.',
                extra={'source_hash':state['source']['sha256'],'source':state['source'],
                       'canvas':state['source_size'],'action':'component-workflow observe_source',
                       'action_references':[reference(contract)],'whole_audit_allowed':False,
                       'spatial_requirements':__import__(__package__+'.spatial_frames',fromlist=['packet']).packet()})
            return {'status':'WORK_PACKET','packet':packet}
        from .knowledge_flow import has_candidates
        if not state.get('knowledge_menu') and has_candidates(state):
            packet=a._packet(task,state,'component_contract_source','knowledge_outline',
                'Observe current semantic class, view, parts/counts and edit needs before detailed geometry. Submit semantic_outline; program returns a deduplicated descriptor menu.',
                extra={'source_hash':state['source']['sha256'],'knowledge_outline_required':True,
                       'action_references':['references/workflow-v133.md']})
            return {'status':'WORK_PACKET','packet':packet}
        extra = {'source_hash': state['source']['sha256'],
                 'input_pptx':state.get('input_pptx'),
                 'scene': (candidate or {}).get('scene'), 'action': 'component-workflow bind',
                  'instruction': 'Compile original-read parts and relations. Freeze semantic_class and observed view for every assembly. For an uploaded partial PPT use actual native owner names and target_width_inches and include missing image parts. Keep source uncertainty explicit; uncertain curves use source-bound function_spec.',
                  'knowledge_menu':state.get('knowledge_menu'),
                  'recipe_selection':'Optional recipe_bindings expands selected data-only constructors before Scene validation; all generated owners require current source contract ownership.',
                  'source_observation':state.get('source_feature_observation'),
                  'action_references': [reference(contract),'references/workflow-v133.md']}
        packet = a._packet(task, state, 'component_contract_source', 'component_contract',
                            'Bind the component-first source contract before local qualification.', extra=extra)
        return {'status': 'WORK_PACKET', 'packet': packet}
    if ledger.get('pending_transaction'):
        packet=a._packet(task,state,'component_recovery_work','transaction',
            'Resume the registered transaction before construction or local work.',
            extra={'transaction':ledger['pending_transaction'],'action':'component-workflow recover',
                   'action_references':[reference(contract)],'whole_audit_allowed':False})
        return {'status':'WORK_PACKET','packet':packet}
    if contract.get('design_revision',0)<8:
        packet=a._packet(task,state,'component_contract_source','component_migration',
            'Explicitly migrate the retained source contract to revision 8; preserve source decisions, native work and existing protections.',
            extra={'previous_contract':state['component_workflow']['contract'],'source_scene':contract['source_scene'],
                   'action':'component-workflow migrate','action_references':[reference(contract)],'whole_audit_allowed':False})
        return {'status':'WORK_PACKET','packet':packet}
    if ledger.get('user_reconciliation'):
        packet=a._packet(task,state,'component_user_mapping','user_owner_mapping',
            'Map adopted user native additions, removals or aliases to an explicit revised component contract; preserve user locks.',
            extra={'reconciliation':ledger['user_reconciliation'],'action_references':[reference(contract)],'whole_audit_allowed':False})
        return {'status':'WORK_PACKET','packet':packet}
    if not candidate:
        packet=a._packet(task,state,'component_build_work','native_construction',
            'Construct the frozen source Scene once, then qualify local parts.',
            extra={'action':'component-workflow build','action_references':[reference(contract)],'whole_audit_allowed':False})
        return {'status':'WORK_PACKET','packet':packet}
    if state.get('component_import_pending'):
        packet=a._packet(task,state,'component_build_work','partial_ppt_completion',
            'Resume the retained partial PPT completion plan through the ordinary constructor.',
            extra={'action':'component-workflow build','whole_audit_allowed':False,'action_references':[reference(contract)]})
        return {'status':'WORK_PACKET','packet':packet}
    refresh(task, state, contract, ledger, candidate)
    write_json(safe_path(task, state['component_workflow']['ledger_path']), ledger)
    if contract.get('workflow_version') in ('1.35.1','1.35.2'):
        from .spatial_repair import advance as advance_repair_phases
        scene=read_json(_resource(task,candidate['scene']))
        if advance_repair_phases(task,state,candidate,contract,ledger,scene):
            with writer(task):_save_ledger(task,state,ledger,'spatial_repair_phase_advanced')
    from .problem_control import remaining
    exhausted=[r['id'] for r in contract['components'] if r.get('problem_id') and ledger['components'][r['id']]['status']!='QUALIFIED'
               and remaining(task,state,r,'source_reads')==0 and (remaining(task,state,r,'evaluations')==0 or remaining(task,state,r,'native_confirmations')==0)]
    if exhausted:return {'status':'ORIGINAL_PROBLEM_UNRESOLVED','components':exhausted,'best_retained':True,'acceptance':False,
                         'next':'Finite automatic work stopped. Inspect retained source/model/measurement diagnosis; no targets were loosened.'}
    if ledger.get('pending_transaction'):
        return {'status':'COMPONENT_TRANSACTION_RECOVERY_REQUIRED','transaction':ledger['pending_transaction'],
                'whole_audit_allowed':False,'action':'component-workflow recover','action_references':[reference(contract)]}
    if (ledger.get('repair_batch') or {}).get('status')=='PLAN_REQUIRED':
        packet=a._packet(task,state,'component_repair_work','final_repairs',
            'Locate each final failure to component fields and submit one scoped repair batch.',
            extra={'repair_batch':ledger['repair_batch'],'action_references':[reference(contract)],'whole_audit_allowed':False})
        return {'status':'WORK_PACKET','packet':packet}
    final=ledger.get('final_result')
    if not ledger['final_dirty'] and final and read_json(_resource(task,final)).get('status')=='ACCEPTED':
        from .workflow_guard import enabled as controlled
        return {'status':'ACCEPTED','action':'export' if controlled(state) else 'quality-loop export','report':final}
    from .component_actions import available
    ranked=rank_actions(available(contract,ledger,candidate))
    if ranked:
        ranked[0]['component']=component_row(task,state,contract,ranked[0]['id'])
    if ranked:
        chosen = ranked[0]; component = chosen['component']
        from .component_batch import compatible
        batch=compatible(ranked,chosen,contract['policy']['max_actions_per_advance']) if chosen['operation'] in ('fit','commit','instantiate') else [chosen]
        batch_ids=chosen.get('repair_components') or [item['id'] for item in batch] or [chosen['id']]
        packet = a._packet(task, state, 'component_local_work', chosen['id'],
                            'Execute the selected source-bound local action; retain fixed parts and do not run the whole audit.',
                            roi=component.get('roi'), extra={'component_action': chosen,
                            'action_references': [reference(contract)], 'whole_audit_allowed': False,
                            'spatial_requirements': __import__(__package__+'.spatial_frames',fromlist=['packet']).packet(contract,component) if contract.get('workflow_version') in ('1.35.0','1.35.1','1.35.2') else None,
                             'source_decision':ledger['components'][chosen['id']].get('source_decision'),
                            'submit_operation':chosen['operation'],'component_batch':batch_ids,
                            'repair_atomic':bool(chosen.get('repair_components'))})
        return {'status': 'WORK_PACKET', 'packet': packet}
    readiness = ready_for_final(contract, ledger, state)
    if readiness['ready'] and not (candidate.get('preview') and candidate.get('render')):
        state.update(active_candidate=candidate,stage='host_render',packet=None)
        with writer(task):a._save(task,state)
        return a._host_render_work(task,state)
    if readiness['ready']:
        from .component_fonts import current as font_review_current,packet as font_review_packet
        scene=read_json(_resource(task,candidate['scene']))
        if not font_review_current(scene,state,ledger):
            extra=font_review_packet(task,state,contract,ledger,candidate)
            with writer(task):_save_ledger(task,state,ledger,'final_font_review_prepared')
            packet=a._packet(task,state,'component_font_review','final_fonts',
                'Complete the single deferred Chinese/English font review before the whole-page visual judgment.',extra=extra)
            return {'status':'WORK_PACKET','packet':packet}
        from .component_final import _visual
        if _visual(task,state,candidate,ledger)['passed']:
            packet=a._packet(task,state,'component_final_audit','final_audit',
                'All parts, layout, fonts and current visual review are ready; close the final audit and acceptance.',
                extra={'action':'component-workflow final','whole_audit_allowed':True,'action_references':[reference(contract)]})
            return {'status':'WORK_PACKET','packet':packet}
    kind = 'component_final_visual' if readiness['ready'] else 'component_layout_work'
    feature_extra = {}
    if readiness['ready'] and contract.get('workflow_version') in ('1.34.0', '1.35.0', '1.35.1','1.35.2'):
        from .component_source_features import diagnostics
        actual_render(task,state,candidate)
        feature_extra = {'source_observation':contract['source_observation'],
            'feature_bindings_hash':identity(contract['feature_bindings']),
            'feature_diagnostics':diagnostics(task,state,candidate,contract),
            'feature_review_required':'Compare every required feature and independently check every original unit for omissions; diagnostics are suspicions, not semantic verdicts.'}
    packet = a._packet(task, state, kind, 'final_visual' if readiness['ready'] else 'final_layout',
                        'Review the actual complete page.' if readiness['ready'] else 'Complete instance placement and actual relation evidence.',
                        extra={'readiness': readiness, 'action_references': [reference(contract)],
                               'whole_audit_allowed': readiness['ready'],**feature_extra})
    return {'status': 'WORK_PACKET', 'packet': packet}


def program_checks(task,state,candidate,contract,row):
    from .native_core_inspect import check
    from .component_relations import evaluate as relations
    scene=read_json(_resource(task,candidate['scene']))
    native=check(scene,task,_resource(task,candidate['pptx']),row['owners'],'body')
    required=row.get('required_checks',['native_structure','relations'])
    if set(required)-{'native_structure','relations','connection_geometry','numeric_targets','visual'}:
        raise ValueError('Unknown executable check; use a supported source-bound specialist route')
    checks={'native_structure':{'passed':native['status']=='PASS','result':native}}
    if contract.get('workflow_version') in ('1.34.0', '1.35.0', '1.35.1','1.35.2'):
        from .component_source_features import source_check
        checks['source_basis'] = source_check(row)
    if contract.get('workflow_version') in ('1.35.0', '1.35.1','1.35.2'):
        from .spatial_checks import evaluate as spatial_evaluate
        checks['spatial_native'] = spatial_evaluate(task, state, candidate, contract, row)
    checks['source_fixed_paint']=fixed_style_checks(task,candidate,contract,row,scene)
    if contract.get('workflow_version') in ('1.34.0', '1.35.0', '1.35.1','1.35.2') and any(f.get('metrics') for f in row.get('source_features',[])):
        from .component_source_features import probes
        actual_render(task,state,candidate)
        checks['source_feature_probes'] = probes(task,state,candidate,row['source_features'])
    from .component_protocol import qualification_relations
    relation_ids=qualification_relations(contract,row)
    if 'relations' in required or row['route']=='instance':
        result=relations(task,state,candidate,contract,relation_ids)
        if row['route']=='instance' and not any(r['kind']=='instance_of' and r['id'] in relation_ids for r in contract.get('relations',[])):
            raise ValueError('Instance needs an executable instance_of relation')
        checks['relations']=result
    if 'connection_geometry' in required:
        from .connection_geometry import report
        checks['connection_geometry']=report(task,state,candidate)
    if 'numeric_targets' in required:
        from .component_metrics import measure
        actual_render(task,state,candidate)
        value=measure(task,state,candidate,row)
        checks['numeric_targets']=metric_result(row,value['metrics'])
    return checks


def review(task,request):
    from .workflow_guard import require
    require(task,'review')
    from .component_final import observe
    return observe(task,request)


def audit_final(task,state=None,candidate=None,persist=True):
    from .component_final import audit
    return audit(task,state,candidate,persist)


def accept_final(task,state,candidate,measured=None):
    from .component_final import accept
    return accept(task,state,candidate,measured)


def run(task):
    from . import agent_runtime as a
    task,state=a._state(task);contract,ledger=_load(task,state);candidate=_candidate(state)
    if not contract or not candidate: return next_action(task,state,candidate)
    refresh(task,state,contract,ledger,candidate)
    write_json(safe_path(task,state['component_workflow']['ledger_path']),ledger)
    if not ready_for_final(contract,ledger,state)['ready'] or not candidate.get('preview') or not candidate.get('render'):
        return next_action(task,state,candidate)
    from .component_fonts import current as font_review_current
    scene=read_json(_resource(task,candidate['scene']))
    from .component_final import _visual
    if not font_review_current(scene,state,ledger) or not _visual(task,state,candidate,ledger)['passed']:
        return next_action(task,state,candidate)
    result=audit_final(task,state,candidate)
    if result['status']!='ACCEPTED': return {'status':'WORK_REQUIRED','result':result,'next':next_action(task,state,candidate)}
    acceptance=accept_final(task,state,candidate,result)
    with writer(task):
        state['selected']=copy.deepcopy(candidate);state['active_candidate']=None
        state.update(stage='accepted',packet=None);a._save(task,state)
    return {'status':'ACCEPTED','acceptance':acceptance,'report':state['quality_result']}


def export(task,output=None,**options):
    from .component_final import export as export_final
    return export_final(task,output,**options)


def fit(task,request):
    from .workflow_guard import require
    require(task,'fit')
    from .component_fit import fit as fit_local
    if not request.get('components'):return fit_local(task,request)
    from .component_batch import fit_batch
    return fit_batch(task,request)


def advance(task,request=None):
    from .workflow_guard import finite_writer
    with finite_writer(task):return _advance(task,request)


def _advance(task,request=None):
    from . import agent_runtime as a
    from .component_actions import available
    request=request or {};limit=request.get('max_actions',policy()['default_actions_per_advance'])
    if type(limit) is not int or not 1<=limit<=policy()['max_actions_per_advance']:raise ValueError('Finite action batch required')
    steps=[]
    while len(steps)<limit:
        task,state=a._state(task);contract,ledger=_load(task,state);candidate=_candidate(state)
        if not contract or not candidate or contract.get('design_revision',0)<8:break
        if (state.get('spatial_source_decision') or state.get('source_observation_rebind_required') or
                ledger.get('pending_decision') or (ledger.get('repair_batch') or {}).get('status')=='PLAN_REQUIRED'):break
        if ledger.get('pending_transaction'):
            if request.get('recover'):
                from .component_fit import recover
                return recover(task,request)
            break
        if state.get('component_import_pending'):break
        refresh(task,state,contract,ledger,candidate)
        if state.get('stage') in ('host_render','font_delivery','font_binding') or state.get('font_pending_candidate'):break
        ranked=rank_actions(available(contract,ledger,candidate))
        if ranked:
            ranked[0]['component']=component_row(task,state,contract,ranked[0]['id'])
        executable=[row for row in ranked if row['executable']]
        if not executable:break
        chosen=executable[0];operation=chosen['operation']
        if operation in ('fit','commit','instantiate'):
            from .component_batch import compatible,commit
            batch=compatible(executable,chosen,max(1,limit-len(steps)-(1 if operation=='fit' else 0)))
            ready=[]
            for action in batch:
                if operation=='fit':
                    result=fit(task,{'component':action['id'],'source_hash':state['source']['sha256'],
                        'pptx_hash':candidate['pptx']['sha256'],'commit':False})
                    steps.append(result)
                    if result.get('status')=='NUMERIC_READY':ready.append(action['id'])
                else:ready.append(action['id'])
            if ready and len(steps)<limit:
                result=commit(task,{'components':ready,'source_hash':state['source']['sha256'],'pptx_hash':candidate['pptx']['sha256']})
                steps.append(result);break
            if len(steps)>=limit:break
            continue
        selected={'component':chosen['id'],'source_hash':state['source']['sha256'],'pptx_hash':candidate['pptx']['sha256']}
        if operation=='evaluate':selected={'components':[chosen['id']]}
        result=dispatch(task,operation,selected);steps.append(result)
        if result.get('status') in ('ACTUAL_NATIVE_CONFIRMATION_REQUIRED','INSTANCE_SAVED_ACTUAL_RENDER_REQUIRED','SOURCE_DECISION_REQUIRED'):break
    task,state=a._state(task)
    following=a.next_packet(task) if state.get('stage') in ('host_render','font_delivery','font_binding') or state.get('font_pending_candidate') else next_action(task,state)
    return {'status':'ADVANCED' if steps else 'HOST_ACTION_REQUIRED','steps':steps,'whole_audit_executed':False,'next':following}


def submit_result(task,result,packet):
    kind=packet['kind'];request=result.get('component_request',result.get('request'))
    if not isinstance(request,dict): raise ValueError('Submit an explicit component_request with the packet')
    if kind=='component_contract_source':
        from .workflow_guard import enabled as controlled
        from . import agent_runtime as a
        task,state=a._state(task)
        if controlled(state) and packet.get('incremental'):
            if request.get('operation') not in packet['incremental']['allowed_operations']:
                raise ValueError('Submit the current incremental operation; retain all prior chunks')
            from .incremental_contract import submit as staged_submit
            return staged_submit(task,request)
        if packet['target']=='source_features':
            from .component_source_features import observe
            return observe(task,request)
        if packet['target']=='knowledge_outline':
            from .knowledge_flow import outline
            from . import agent_runtime as a
            task,state=a._state(task)
            state['knowledge_menu']=outline(task,state,request);state['packet']=None
            a._save(task,state)
            return {'status':'KNOWLEDGE_DESCRIPTORS_READY','reference':state['knowledge_menu'],'next':next_action(task,state)}
        return bind(task,request)
    if kind=='component_recovery_work': return dispatch(task,'recover',request)
    if kind=='component_repair_work': return dispatch(task,'repair',request)
    if kind=='component_user_mapping':
        from .component_user_sync import reconcile
        return reconcile(task,request)
    if kind=='component_build_work':
        from .component_constructor import build_task
        return build_task(task,request)
    if kind=='component_layout_work': return layout(task,request)
    if kind=='component_final_visual': return review(task,request)
    if kind=='component_final_audit':return run(task)
    if kind=='component_font_review':
        from .component_fonts import submit
        return submit(task,request)
    if kind=='component_local_work':
        operation=result.get('operation')
        if operation not in ('evaluate','fit','qualify','instantiate','reproject','source_prepare','rollback','source_or_measurement_decision','commit','edit'): raise ValueError('Choose the actual local operation')
        expected_operation=packet.get('submit_operation') or packet.get('component_action',{}).get('operation')
        if expected_operation and operation not in (expected_operation,'source_or_measurement_decision'):
            raise ValueError('Submit the packet-selected operation; alternative writes require a focused source decision')
        expected=packet['target']
        selected=request.get('components',[request.get('component')])
        scope=packet.get('component_batch',[expected])
        if not selected or expected not in selected or not set(selected)<=set(scope):
            raise ValueError('Submit only the packet-selected component batch')
        atomic_edit=operation=='edit' and packet.get('repair_atomic') and set(selected)==set(scope)
        if operation=='edit' and packet.get('repair_atomic') and not atomic_edit:
            raise ValueError('Submit the complete approved icon repair batch atomically')
        if len(selected)>1 and operation not in ('fit','commit','instantiate') and not atomic_edit:
            raise ValueError('This operation accepts one focused decision')
        decided=packet.get('component_action',{}).get('decided_scene')
        if operation=='edit' and decided:
            request=dict(request)
            request.setdefault('scene',decided)
            request.setdefault('rebuild_owners',packet['component_action'].get('rebuild_owners',[]))
        return dispatch(task,operation,request)
    raise ValueError('Unsupported component packet')


def guard_changes(task,state,scene,allowed,revision_components=()):
    """Qualified intrinsic properties cannot be overwritten by a layout action."""
    contract,ledger=_load(task,state)
    if not contract: return
    if state.get('spatial_source_decision') or state.get('source_observation_rebind_required') or ledger.get('pending_decision'):
        raise ValueError('Resolve/rebind the pending source or measurement decision before native writes')
    from .component_revision import guard_user_locks
    guard_user_locks(task,state,scene,allowed)
    before=read_json(_resource(task,_candidate(state)['scene']))
    structural=ledger.get('structural_grant')
    if structural:
        from .component_fields import canonical_node
        decided=read_json(_resource(task,structural['scene']))
        nodes=lambda value:{n['id']:canonical_node(n) for n in value['objects']}
        if nodes(scene)!=nodes(decided):
            raise ValueError('Finish the retained source-apply plan before another native write')
    from .spatial_repair import guard_scene
    guard_scene(contract,ledger,before,scene)
    old={n['id']:n for n in before['objects']};new={n['id']:n for n in scene['objects']}
    for row in contract['components']:
        if ledger['components'][row['id']]['status']!='QUALIFIED': continue
        if row['id'] in revision_components and set(row['owners']).intersection(allowed or {}):continue
        for owner in row['owners']:
            if owner not in new or owner not in old: raise ValueError('Cannot delete a qualified owner')
            a,b=facets(old[owner]),facets(new[owner])
            if any(a[k]!=b[k] for k in ('content','paint','geometry')):
                raise ValueError('Intrinsic properties locked; revise the source/model contract before changing '+owner)


def dispatch(task, operation, request=None):
    if operation not in ('status','export','advance'):
        from .workflow_guard import require
        require(task,operation)
    if request and any(str(key).startswith('_') for key in request):
        raise ValueError('Private transaction fields are not public workflow inputs')
    if operation=='observe_source':
        from .component_source_features import observe
        return observe(task,request)
    if operation in ('source_or_measurement_decision','repair','lock','unlock','edit'):
        from .component_revision import decide,repair,locks,edit_native
        if operation=='source_or_measurement_decision':return decide(task,request)
        if operation=='repair':return repair(task,request)
        if operation=='edit':return edit_native(task,request)
        return locks(task,request,remove=operation=='unlock')
    if operation=='fonts':
        from .component_fonts import submit
        return submit(task,request)
    if operation=='commit':
        from .component_batch import commit
        return commit(task,request)
    if operation=='source_prepare':
        from .constructor_registry import source_prepare
        return source_prepare(task,request)
    if operation in ('recover','rollback'):
        from .component_transactions import recover,rollback
        return (recover if operation=='recover' else rollback)(task,request or {})
    if operation=='instantiate':
        from .component_batch import commit
        return commit(task,{**request,'components':request.get('components',[request.get('component')])})
    if operation=='reproject':
        from .spatial_constructors import reproject
        return reproject(task,request)
    if operation=='build':
        from .component_constructor import build_task
        return build_task(task,request)
    operations={'bind':bind,'migrate':bind,'evaluate':evaluate,'qualify':qualify,
                'layout':layout,'review':review,'fit':fit,'advance':advance}
    if operation in operations:return operations[operation](task,request)
    if operation=='status':return status(task)
    if operation=='final':return run(task)
    raise ValueError('Unsupported component workflow operation: '+operation)


def component_row(task,state,contract,name):
    """Resolve only a requested row and its original evidence through scoped indexes."""
    from .state_repository import Repository
    repo=Repository(task);scope=state['component_workflow']['contract']['sha256']
    row=repo.lookup('component_contract:'+scope,name)
    if row is None:
        row=next((r for r in contract['components'] if r['id']==name),None)
        if row is None:raise ValueError('Unknown component '+name)
        repo.index_rows('component_contract:'+scope,{name:row})
    for unit in row.get('source_units',[]):
        found=repo.lookup('source_unit:'+scope,unit)
        if found is None:
            found=next((r for r in contract['source_inventory'] if r['id']==unit),None)
            if found is None:raise ValueError('Missing original semantic unit '+unit)
            repo.index_rows('source_unit:'+scope,{unit:found})
    for ref in row.get('source_refs',[]):_resource(task,ref)
    if row.get('support_mask'):_resource(task,row['support_mask'])
    return row
