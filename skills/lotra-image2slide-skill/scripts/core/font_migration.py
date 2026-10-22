"""Explicit old-task font policy migration; resource/family changes stay staged."""
import copy
from pathlib import Path
from .common import read_json, write_json, digest, identity
from .font_resolution import POLICY, request_key


def offer(task,state,scene):
    from .font_contract import requests
    rows=requests(scene,state)
    value={'source_hash':state['source']['sha256'],'requests':rows,
        'exact_task_font_requests':state.get('objectives',{}).get('font_requests',{}),
        'rule':'Inspect every listed request. Preserve exact user/source-metadata families; classify ordinary construction fonts as hints only with original observations.'}
    file=Path(task)/'source'/('Font-policy-inputs-'+identity(value)+'.json')
    if not file.exists():write_json(file,value)
    return {'target_policy':POLICY,'scope':'explicit whole-task identity migration; no native font write',
        'inputs':{'path':file.relative_to(task).as_posix(),'sha256':digest(file)},
        'return':'font_policy_migration{source_hash,reason,intent_map:{path,sha256}}; intent_map contains source_hash, observer:host_model|human, observations, and requests[{request_id,mode:hint|exact,family?}] covering every listed request. Existing exact authority cannot become a hint.'}


def migrate(task,state,scene,request):
    from . import font_contract as fonts, component_workflow as workflow
    from . import font_resources as resources
    from .font_resolution import verify_source_spans
    if state.get('font_workflow_policy')==POLICY:
        raise ValueError('This task already binds the current font policy')
    if request.get('source_hash')!=state['source']['sha256'] or not request.get('reason'):
        raise ValueError('Font policy migration needs the current original and an explicit reason')
    observed=read_json(workflow._resource(task,request['intent_map']))
    rows={row['id']:row for row in fonts.requests(scene,state)}
    entries=observed.get('requests',[])
    if (observed.get('source_hash')!=state['source']['sha256'] or observed.get('observer') not in ('host_model','human')
            or not observed.get('observations') or len(entries)!=len(rows)
            or {entry.get('request_id') for entry in entries}!=set(rows)):
        raise ValueError('Font migration needs independent original observations for every current request')
    working=copy.deepcopy(state);pending=working['font_pending_candidate']
    old_ledger=copy.deepcopy(fonts.pending_state(state).get('font_contract',{'version':fonts.VERSION,'bindings':{},'history':[]}))
    overrides={}
    for entry in entries:
        row=rows[entry['request_id']];prior=old_ledger['bindings'].get(row['id'])
        demanded=fonts.user_family(state,row)
        exact=demanded or (prior['family'] if prior and prior.get('origin') in ('user','source_metadata','compiler') else None)
        if entry.get('mode') not in ('hint','exact'):
            raise ValueError('Each legacy font request must be classified as hint or exact')
        if exact and (entry['mode']!='exact' or not entry.get('family')
                or resources.name_key(entry['family'])!=resources.name_key(exact)):
            raise ValueError('FONT_MIGRATION_EXACT_AUTHORITY: preserve every existing exact font request')
        if entry['mode']=='exact':
            family=entry.get('family')
            if not family or not exact:
                raise ValueError('Raster observation cannot invent exact font metadata during migration')
            overrides[row['id']]=family
    retained={'policy':state.get('font_workflow_policy'),'source_hash':state['source']['sha256'],
        'bindings':old_ledger,'samples':state.get('font_samples',{}),'constraints':state.get('font_constraints',{}),
        'rankings':state.get('font_rankings',{}),'intent_map':request['intent_map'],'reason':request['reason']}
    file=Path(task)/'source'/('Font-policy-before-'+identity(retained)+'.json')
    if not file.exists():write_json(file,retained)
    working.update(font_workflow_policy=POLICY,font_intent_overrides=overrides,font_constraints={},font_groups={},font_rankings={})
    scene=copy.deepcopy(scene);scene['font_workflow_policy']=POLICY;scene.pop('font_plan',None)
    verify_source_spans(task,working,scene)
    new_rows={row['id']:row for row in fonts.requests(scene,working)}
    ledger=copy.deepcopy(old_ledger);mapping=[]
    for key,prior in old_ledger['bindings'].items():
        if key not in rows or not fonts._request_match(prior,rows[key]):
            continue
        if digest(prior['resource']['path'])!=prior['resource']['file_sha256']:
            raise ValueError('Font migration cannot adopt changed resource bytes')
        revised=copy.deepcopy(prior);revised['request']=new_rows[key];revised['request_hash']=request_key(new_rows[key])
        revised['policy_migration_prior']=identity(prior);ledger['bindings'][key]=revised
        mapping.append({'request_id':key,'prior_binding_hash':identity(prior),'new_binding_hash':identity(revised)})
    ledger['history'].append({'operation':'explicit_font_policy_migration','policy':POLICY,'mapping':mapping,
        'evidence':copy.deepcopy(request['intent_map']),'retained':{'path':file.relative_to(task).as_posix(),'sha256':digest(file)}})
    pending['staged_font_contract']=ledger
    revised_file=Path(task)/'source'/('Font-policy-scene-'+identity(scene)+'.json');write_json(revised_file,scene)
    pending['scene']={'path':revised_file.relative_to(task).as_posix(),'sha256':digest(revised_file)}
    # Source samples retain their literal/ROI obligations and are revalidated;
    # narrowing and family decisions must be made under the new policy.
    from .font_collection import store_samples
    old_samples={key:row['samples'] for key,row in state.get('font_samples',{}).items()
        if key in rows and row.get('source_hash')==state['source']['sha256'] and row.get('request_hash')==request_key(rows[key])}
    working['font_samples']={}
    if old_samples:store_samples(task,working,scene,old_samples)
    if working.get('component_workflow'):
        contract,component_ledger=workflow._load(task,working)
        owners={row['owner'] for row in new_rows.values()}
        for row in contract['components']:
            if owners.intersection(row['owners']):component_ledger['components'][row['id']]['status']='RECHECK_REQUIRED'
        component_ledger.update(final_dirty=True,final_result=None,layout_ready=False)
        component_ledger.pop('font_review',None);component_ledger.pop('font_review_plan',None)
        working.update(packet=None,stage='font_binding',actions=working['actions']+1)
        workflow._save_ledger(task,working,component_ledger,'font_policy_explicitly_migrated',{'policy':POLICY,'retained':str(file.name)})
    else:
        from .agent_runtime import _save
        working.update(packet=None,stage='font_binding',actions=working['actions']+1);_save(task,working)
    return {'status':'FONT_POLICY_MIGRATED_PREPARATION_REQUIRED','policy':POLICY,'native_write':False,
        'preserved_prior_ledger':True,'mapped_bindings':len(mapping),'acceptance':False,'next':'next '+str(task)}
