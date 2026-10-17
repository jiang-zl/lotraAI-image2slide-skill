"""Focused decisions, final repair grants and persistent user field locks."""
import copy
from .common import read_json,write_json,identity,writer


def overlap(left,right):
    """An ancestor lock also protects every descendant field."""
    return left[:min(len(left),len(right))]==right[:min(len(left),len(right))]


def descendants(contract,selected):
    result=set(selected)
    while True:
        updated=result|{r['id'] for r in contract['components'] if r.get('parent') in result}
        if updated==result:return result
        result=updated


def guard_user_locks(task,state,scene,allowed=None):
    from . import component_workflow as c
    from .component_transactions import differences
    contract,ledger=c._load(task,state);baseline=c._candidate(state)
    if not contract or not baseline:return
    old={n['id']:n for n in read_json(c._resource(task,baseline['scene']))['objects']}
    new={n['id']:n for n in scene['objects']}
    records=[*ledger['components'].values(),{'user_locks':ledger.get('orphan_user_locks',[])}]
    for record in records:
        for lock in record.get('user_locks',[]):
            owner=lock['owner']
            if owner not in old or owner not in new:
                if old.get(owner)!=new.get(owner):raise ValueError('USER_LOCK_CONFLICT: '+owner)
                continue
            if any(overlap(lock['field'],patch['field']) for patch in differences(old[owner],new[owner])):
                raise ValueError('USER_LOCK_CONFLICT: '+owner+' '+repr(lock['field']))


def locks(task,request,remove=False):
    from . import agent_runtime as a,component_workflow as c
    task,state=a._state(task);contract,ledger=c._load(task,state);candidate=c._candidate(state)
    if request.get('pptx_hash')!=(candidate or {}).get('pptx',{}).get('sha256'):
        raise ValueError('Current user native revision required')
    if request.get('authority')!='user' or not request.get('reason') or not request.get('evidence'):
        raise ValueError('Explicit user instruction and retained evidence required for a user lock change')
    c._resource(task,request['evidence'])
    rows={r['id']:r for r in contract['components']}
    for item in request.get('locks',[]):
        if remove and not item.get('component'):
            target={'owner':item['owner'],'field':item['field']}
            if not any((v['owner'],v['field'])==(target['owner'],target['field']) for v in ledger.get('orphan_user_locks',[])):
                raise ValueError('Existing orphan lock required')
            ledger['orphan_user_locks']=[v for v in ledger['orphan_user_locks'] if (v['owner'],v['field'])!=(target['owner'],target['field'])]
            ledger.setdefault('lock_history',[]).append({'action':'unlock_orphan','target':target,'evidence':request['evidence'],'reason':request['reason']})
            continue
        row=rows[item['component']]
        if item['owner'] not in row['owners'] or not isinstance(item['field'],list):
            raise ValueError('Located owned field lock required')
        record=ledger['components'][row['id']];existing=record.setdefault('user_locks',[])
        target={'owner':item['owner'],'field':item['field']}
        if remove:
            for entry in ledger['components'].values():
                entry['user_locks']=[v for v in entry.get('user_locks',[]) if (v['owner'],v['field'])!=(target['owner'],target['field'])]
            ledger['orphan_user_locks']=[v for v in ledger.get('orphan_user_locks',[]) if (v['owner'],v['field'])!=(target['owner'],target['field'])]
            ledger.setdefault('lock_history',[]).append({'action':'unlock','target':target,'evidence':request['evidence'],'reason':request['reason']})
        elif not any((v['owner'],v['field'])==(target['owner'],target['field']) for v in existing):
            existing.append(dict(target,evidence=request['evidence'],reason=request['reason']))
    with writer(task):c._save_ledger(task,state,ledger,'user_locks_changed',{'remove':remove,'evidence':request['evidence']})
    return {'status':'USER_LOCKS_UPDATED','acceptance':False}


def decide(task,request):
    """Submit the selected component's revised source model through next/submit."""
    from . import agent_runtime as a,component_workflow as c
    task,state=a._state(task);contract,ledger=c._load(task,state);candidate=c._candidate(state)
    if ledger.get('pending_transaction'):raise ValueError('Recover pending native work before a source revision')
    if request.get('source_hash')!=state['source']['sha256'] or request.get('pptx_hash')!=(candidate or {}).get('pptx',{}).get('sha256'):
        raise ValueError('Decision must bind current original and native revision')
    if not request.get('revision_reason'):raise ValueError('Describe the original/model/measurement correction')
    if contract.get('workflow_version') in ('1.34.0','1.35.0') and request.get('decision_kind') not in (
            'source_omission','representation_insufficient','parameter_error','measurement_invalid',
            'native_mismatch','relation_error','source_ambiguity','spatial_frame','spatial_pose',
            'face_alignment','support_relation','spatial_occlusion'):
        raise ValueError('Classify the located source/model/measurement failure before repairing')
    from .problem_control import reserve
    reserve(task,state,c.component_row(task,state,contract,request['component']),'source_reads',token=identity(request))
    selected={request['component']};scope=descendants(contract,selected)
    old={r['id']:r for r in contract['components']}
    replacements=request.get('replacements') or [request['replacement_component']]
    changed={r['id']:copy.deepcopy(r) for r in replacements}
    additions=set(changed)-set(old)
    if not (set(changed)-additions)<=scope:raise ValueError('Decision escaped the packet component subtree')
    while additions:
        permitted={key for key in additions if changed[key].get('parent') in scope}
        if not permitted:raise ValueError('New parts must belong to the selected assembly')
        scope.update(permitted);additions-=permitted
    removed=set(request.get('remove_components',[]))
    if not removed<=scope or selected&removed:raise ValueError('Keep the packet component and unrelated source parts')
    rows={**old,**changed}
    for key in removed:rows.pop(key,None)
    revised=copy.deepcopy(contract);revised['components']=list(rows.values())
    if 'feature_bindings' in request:
        prior={b['feature']:b for b in contract.get('feature_bindings',[])}
        after={b['feature']:b for b in request['feature_bindings']}
        for key in set(prior)|set(after):
            if prior.get(key)!=after.get(key) and any(b and b.get('component') not in scope for b in (prior.get(key),after.get(key))):
                raise ValueError('Feature revision escaped the selected component subtree')
        revised['feature_bindings']=copy.deepcopy(request['feature_bindings'])
    if 'native_constructions' in request:
        from .native_surfaces import construct
        permitted={o for key in scope for o in rows.get(key,old.get(key,{})).get('owners',[])}
        permitted.update(o for key in scope for o in old.get(key,{}).get('owners',[]))
        prior={s['id']:s for s in contract.get('native_constructions',[])}
        after={s['id']:s for s in request['native_constructions']}
        for key in set(prior)|set(after):
            if prior.get(key)==after.get(key):continue
            for spec in (prior.get(key),after.get(key)):
                if spec and not {o['id'] for o in construct(spec)[0]}<=permitted:
                    raise ValueError('Native construction revision escaped the selected owner resource group')
        revised['native_constructions']=copy.deepcopy(request['native_constructions'])
    if 'relations' in request:
        prior={r['id']:r for r in contract['relations']};after={r['id']:r for r in request['relations']}
        for key in set(prior)|set(after):
            if prior.get(key)!=after.get(key) and not any(set(r.get('components',[]))&scope for r in (prior.get(key,{}),after.get(key,{}))):
                raise ValueError('Unrelated relation changed')
        revised['relations']=copy.deepcopy(request['relations'])
    if 'source_inventory' in request:
        units={u for key in scope for u in rows.get(key,old.get(key,{})).get('source_units',[])}
        units.update(u for key in scope for u in old.get(key,{}).get('source_units',[]))
        prior={v['id']:v for v in contract['source_inventory']};after={v['id']:v for v in request['source_inventory']}
        if any(prior.get(k)!=after.get(k) for k in (set(prior)|set(after))-units):raise ValueError('Unrelated source inventory changed')
        revised['source_inventory']=request['source_inventory']
    source_ref=request.get('source_scene',contract['source_scene'])
    from .tables import normalize_scene
    before=normalize_scene(read_json(c._resource(task,contract['source_scene'])))
    after=normalize_scene(read_json(c._resource(task,source_ref)))
    allowed={owner for key in scope for owner in old.get(key,{}).get('owners',[])}
    allowed.update(owner for key in scope for owner in rows.get(key,{}).get('owners',[]))
    bnodes={n['id']:n for n in before['objects']};anodes={n['id']:n for n in after['objects']}
    if any(bnodes.get(key)!=anodes.get(key) for key in (set(bnodes)|set(anodes))-allowed):
        raise ValueError('Source Scene revision escaped the selected anatomy')
    if any(before.get(k)!=after.get(k) for k in set(before)|set(after) if k not in ('objects','relations','font_plan')):
        raise ValueError('A focused decision cannot change the original canvas or global source facts')
    if request.get('apply_scene'):
        proposed=read_json(c._resource(task,request['apply_scene']))
        current=read_json(c._resource(task,candidate['scene']))
        from .component_native_plan import prepare
        prepare(task,state,current,proposed,[{'owner':owner,'field':[]} for owner in allowed],request.get('rebuild_owners',[]))
    # Validate the complete normalized contract before publishing revised source facts.
    c.bind(task,{'contract':revised,'source_scene':source_ref,'authority':request['authority'],
                 'revision_reason':request['revision_reason']},prepare_only=True)
    native_apply=({'scene':request['apply_scene'],'components':sorted(scope&set(rows)),
        'fields':[{'owner':owner,'field':[]} for owner in sorted(allowed)],
        'rebuild_owners':request.get('rebuild_owners',[]),
        'previous_owners':{key:old.get(key,{}).get('owners',[]) for key in scope}} if request.get('apply_scene') else None)
    result=c.bind(task,{'contract':revised,'source_scene':source_ref,'authority':request['authority'],
                        'revision_reason':request['revision_reason']},native_apply=native_apply)
    task,state=a._state(task);contract,ledger=c._load(task,state)
    for key in scope&set(ledger['components']):
        record=ledger['components'][key]
        if not request.get('apply_scene'):record['status']='RECHECK_REQUIRED'
    with writer(task):c._save_ledger(task,state,ledger,'source_decision_submitted',{'components':sorted(scope),'reason':request['revision_reason']})
    if request.get('apply_scene'):
        # No implicit overwrite: the submitted actual Scene and grants remain focused.
        return edit_native(task,{'components':sorted(scope&set(rows)), 'scene':request['apply_scene'],
            'rebuild_owners':request.get('rebuild_owners',[]),
            'pptx_hash':candidate['pptx']['sha256'],'source_hash':state['source']['sha256']})
    return dict(result,status='SOURCE_DECISION_APPLIED',acceptance=False)


def queue_final_repair(ledger,failures,evidence):
    ledger['repair_batch']={'status':'PLAN_REQUIRED','failures':failures,'evidence':evidence}
    ledger['final_dirty']=True;ledger['final_result']=None


def repair(task,request):
    from . import agent_runtime as a,component_workflow as c
    from .component_protocol import impact
    task,state=a._state(task);contract,ledger=c._load(task,state);candidate=c._candidate(state)
    batch=ledger.get('repair_batch')
    if not batch or batch['status']!='PLAN_REQUIRED':raise ValueError('Current located repair decision required')
    if request.get('source_hash')!=state['source']['sha256'] or request.get('pptx_hash')!=candidate['pptx']['sha256']:
        raise ValueError('Final repair plan is stale')
    if contract.get('workflow_version') == '1.35.0':
        from .spatial_checks import evaluate as spatial_evaluate
        spatial = spatial_evaluate(task,state,candidate,contract)
        if not spatial['valid']:
            return {'status':'MEASUREMENT_DIAGNOSIS_REQUIRED','spatial':spatial,
                    'acceptance':False,'native_writes_granted':False}
    rows={r['id']:r for r in contract['components']};items=request.get('items',[])
    if not items:raise ValueError('Locate final failures to nonempty component field grants')
    if contract.get('workflow_version')=='1.35.0' and any(item.get('frame_pose_diagnosis')=='shared_frame' for item in items):
        return {'status':'SPATIAL_SOURCE_DECISION_REQUIRED','acceptance':False,'best_retained':True,
                'next':'Revise the source-owned common frame with located spatial_corrections, then rebind all consumers. Local drawing patches cannot repair a shared projection definition.'}
    if len({v['component'] for v in items})!=len(items):raise ValueError('Merge fields for the same component into one repair item')
    covered=set();changed={}
    for item in items:
        row=rows[item['component']];record=ledger['components'][row['id']]
        if contract.get('workflow_version') == '1.35.0':
            from .spatial_frames import PHASE
            source_relations = {r['id']:r for r in contract['spatial']['relations']}
            selected_relations = item.get('spatial_relations', [])
            if not set(selected_relations) <= set(source_relations):
                raise ValueError('Repair references unknown source spatial relations')
            record['repair_phase'] = min((PHASE[source_relations[k]['kind']] for k in selected_relations), default=5)
            if any(source_relations[k]['kind'] in ('axis_direction','pose_projection') for k in selected_relations) and not item.get('frame_pose_diagnosis'):
                raise ValueError('Distinguish shared projection from local pose before drawing an orientation repair')
        if not item.get('reason') or not item.get('failures'):raise ValueError('Link each correction to a final failure')
        if not set(item['failures'])<=set(batch['failures']):raise ValueError('Unknown final failure')
        covered.update(item['failures'])
        fields=item.get('fields',[])
        if not fields:raise ValueError('Explicit native write fields required')
        for grant in fields:
            if grant['owner'] not in row['owners'] or not isinstance(grant.get('field'),list):raise ValueError('Repair field escaped its component')
            if any(lock['owner']==grant['owner'] and overlap(lock['field'],grant['field']) for lock in record.get('user_locks',[])):
                raise ValueError('USER_LOCK_CONFLICT: preserve the adopted user field')
        record['repair_grant']=copy.deepcopy(fields);record['repair_base']=candidate['pptx']['sha256'];record['status']='REPAIR_REQUIRED'
        record['repair_context']={'row':identity(row),'source':state['source']['sha256'],'native':candidate.get('retained_pptx',candidate['pptx'])}
        changed[row['id']]=['geometry','assembly']
    if covered!=set(batch['failures']):raise ValueError('Every final failure needs a located correction')
    affected=impact(contract,changed)
    for name in affected['components']:
        if name not in changed:ledger['components'][name]['status']='RECHECK_REQUIRED'
        ledger['components'][name].pop('instantiation',None)
    for name in affected['relations']:ledger['relations'].pop(name,None)
    batch.update(status='LOCAL_REPAIR',items=copy.deepcopy(items))
    ledger.update(layout_ready=False,final_dirty=True,final_result=None)
    with writer(task):c._save_ledger(task,state,ledger,'final_repair_scoped',{'affected':affected})
    return {'status':'LOCAL_REPAIR_REQUIRED','components':sorted(changed),'whole_audit_executed':False}


def edit_native(task,request):
    from . import agent_runtime as a,component_workflow as c
    from .component_transactions import differences
    from .component_constructor import construct
    task,state=a._state(task);contract,ledger=c._load(task,state);candidate=c._candidate(state)
    if request.get('source_hash')!=state['source']['sha256'] or request.get('pptx_hash')!=candidate['pptx']['sha256']:
        raise ValueError('Local edit requires the current source/native revision')
    selected=set(request.get('components',[request.get('component')]))
    if not selected or not selected<=set(ledger['components']):raise ValueError('Current component scope required')
    grants=[v for name in selected for v in ledger['components'][name].get('repair_grant',[])]
    for name in selected:
        if ledger['components'][name].get('repair_base',candidate['pptx']['sha256'])!=candidate['pptx']['sha256']:
            record=ledger['components'][name];context=record.get('repair_context')
            row=next(r for r in contract['components'] if r['id']==name)
            if not context or context['row']!=identity(row) or context['source']!=state['source']['sha256']:
                raise ValueError('Repair grant source/component context changed')
            from .native_core_checks import snapshots
            before_native=snapshots(c._resource(task,context['native']),component_mode=True)
            now_native=snapshots(c._resource(task,candidate['pptx']),component_mode=True)
            owned={v['owner'] for v in record.get('repair_grant',[])}
            if any(before_native.get(owner)!=now_native.get(owner) for owner in owned):
                raise ValueError('Located native owner changed after the repair decision; replan its fields')
    structural=ledger.get('structural_grant')
    if structural and selected<=set(structural['components']):
        if any(structural[k]!=v for k,v in (('source_hash',state['source']['sha256']),('pptx_hash',candidate['pptx']['sha256']),('contract',state['component_workflow']['contract']))):
            raise ValueError('Structural source grant is stale')
        if structural['scene']!=request['scene']:raise ValueError('Structural edit must apply the retained decided Scene')
        grants+=structural['fields']
    old=read_json(c._resource(task,candidate['scene']));proposed=read_json(c._resource(task,request['scene']))
    from .component_native_plan import prepare
    rebuild=request.get('rebuild_owners',(structural or {}).get('rebuild_owners',[]))
    scene,allowed,_=prepare(task,state,old,proposed,grants,rebuild)
    if not allowed:raise ValueError('No proposed field correction')
    post={'statuses':{name:'RECHECK_REQUIRED' for name in selected},'consume_grants':sorted(selected),
          'consume_structural_grant':bool(structural and selected<=set(structural['components'])),
          'repair_batch_status':'RECHECK_REQUIRED' if ledger.get('repair_batch') else None}
    saved=construct(task,state,scene,candidate,allowed,{'kind':'component_scoped_repair','components':sorted(selected),'post_save':post})
    # The saved journal owns status/grant transitions, including a font/provider pause.
    return {'status':'LOCAL_REPAIR_SAVED' if saved else 'FONT_BINDING_REQUIRED','candidate':saved,'whole_audit_executed':False}
