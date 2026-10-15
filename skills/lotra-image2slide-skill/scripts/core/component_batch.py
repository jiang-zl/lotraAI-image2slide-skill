"""Gather independent numeric parts or native instances into one transaction."""
import copy
from .common import read_json,write_json,identity,writer


def compatible(actions,chosen,limit):
    """Keep dependencies and owner writes disjoint within a single mother family."""
    operation=chosen['operation'];row=chosen['component']
    family=row.get('mother') if operation=='instantiate' else row.get('parent')
    result=[];owners=set()
    for action in actions:
        part=action['component']
        if not action['executable'] or action['operation']!=operation or action['stage_index']!=chosen['stage_index']:continue
        if (part.get('mother') if operation=='instantiate' else part.get('parent'))!=family:continue
        if owners.intersection(part['owners']):continue
        if any(part.get('mother')==other['id'] or part.get('parent')==other['id'] for other in result):continue
        result.append(action);owners.update(part['owners'])
        if len(result)>=limit:break
    return result


def fit_batch(task,request):
    from . import agent_runtime as a,component_workflow as c
    from .component_fit import fit
    task,state=a._state(task);contract,ledger=c._load(task,state);candidate=c._candidate(state)
    names=request['components']
    if not names or len(names)>contract['policy']['max_actions_per_advance'] or len(set(names))!=len(names):
        raise ValueError('Bounded distinct numeric batch required')
    rows=[c.component_row(task,state,contract,key) for key in names]
    if len({row.get('parent') for row in rows})!=1 or any(row['route']!='local_fit' for row in rows):
        raise ValueError('Numeric batch requires independent parts of one mother family')
    outputs=[];ready=[]
    for name in names:
        result=fit(task,{**request,'component':name,'commit':False});outputs.append(result)
        if result['status']=='NUMERIC_READY':ready.append(name)
    if ready and request.get('commit',True):
        result=commit(task,{**request,'components':ready})
        return dict(result,numeric_results=outputs)
    return {'status':'NUMERIC_BATCH_READY' if ready else 'SOURCE_DECISIONS_REQUIRED',
            'components':ready,'numeric_results':outputs,'whole_audit_executed':False}


def commit(task,request):
    from . import agent_runtime as a,component_workflow as c
    from .component_fit import apply
    from .component_constructor import construct
    task,state=a._state(task);contract,ledger=c._load(task,state);candidate=c._candidate(state)
    c.refresh(task,state,contract,ledger,candidate)
    if ledger.get('pending_transaction') and not request.get('_transaction'):raise ValueError('Recover the current transaction first')
    if request.get('source_hash')!=state['source']['sha256'] or request.get('pptx_hash')!=candidate['pptx']['sha256']:
        raise ValueError('Batch requires the current original and native base')
    selected=request.get('components',[request.get('component')])
    if not selected or len(selected)>contract['policy']['max_actions_per_advance'] or len(set(selected))!=len(selected):
        raise ValueError('Bounded distinct batch required')
    rows=[c.component_row(task,state,contract,name) for name in selected];routes={row['route'] for row in rows}
    if len(routes)!=1 or not routes<={'instance','local_fit'}:raise ValueError('Batch one independent operation family')
    family={row.get('mother') if row['route']=='instance' else row.get('parent') for row in rows}
    if len(family)!=1:raise ValueError('Batch only source-related parts of one mother family')
    owned=set()
    for row in rows:
        if owned.intersection(row['owners']):raise ValueError('Batch write sets overlap')
        owned.update(row['owners'])
        from .component_revision import overlap
        writes=([{'owner':owner,'field':[]} for owner in row['owners']] if row['route']=='instance' else
                [v for key,v in row['fit']['bindings'].items() if row['parameters'][key]['state']=='tunable'])
        if any(item['owner']==lock['owner'] and overlap(item['field'],lock['field'])
               for item in writes for lock in ledger['components'][row['id']].get('user_locks',[])):
            raise ValueError('USER_LOCK_CONFLICT: batch write overlaps an adopted field')
    scene=read_json(c._resource(task,candidate['scene']))
    if routes=={'local_fit'}:
        _,signatures=c._signatures(task,state,candidate);allowed={}
        for row in rows:
            record=ledger['components'][row['id']]
            measurement_signature=c._measurement_signature(row,signatures,contract)
            if record['status']!='NUMERIC_READY' or record.get('numeric_input_signature')!=measurement_signature:
                raise ValueError('Numeric result no longer describes this part')
            fit=read_json(c._resource(task,record['last_fit']))
            from .component_fit import basis as fit_basis
            if fit['status']!='TARGETS_MET' or fit.get('fit_basis')!=fit_basis(row,contract['policy'],state,measurement_signature):
                raise ValueError('Only a current numerically ready result can be committed')
            scene,writes=apply(scene,row,fit['parameters']);allowed.update(writes)
        with writer(task):c._save_ledger(task,state,ledger,'numeric_batch_planned',{'components':selected})
        saved=construct(task,state,scene,candidate,allowed,{'kind':'component_numeric_batch','components':selected})
        task,state=a._state(task);contract,ledger=c._load(task,state)
        # Status transition is journaled before Ready and replayed by recovery.
        if not saved:return {'status':'FONT_BINDING_REQUIRED','components':selected,'candidate':None,'whole_audit_executed':False}
        with writer(task):c._save_ledger(task,state,ledger,'numeric_batch_saved',{'components':selected})
        return {'status':'ACTUAL_NATIVE_CONFIRMATION_REQUIRED' if saved else 'FONT_BINDING_REQUIRED',
                'components':selected,'candidate':saved,'whole_audit_executed':False}
    from .component_transactions import begin,attempt_folder,saved,phase,differences
    from .component_instances import instantiate
    allowed={owner:['replace_native'] for owner in owned}
    durable_request={k:v for k,v in request.items() if not k.startswith('_')}
    tx=request.get('_transaction') or begin(task,state,scene,candidate,allowed,
        {'kind':'component_batch','components':selected,'request':durable_request})
    folder=attempt_folder(task,tx);working=candidate;expected={}
    for index,row in enumerate(rows):
        part_folder=folder/('instance-'+str(index));part_folder.mkdir()
        result=instantiate(task,{'component':row['id'],'source_hash':state['source']['sha256'],
            'pptx_hash':working['pptx']['sha256'],'_transaction':tx,'_prepare':True,
            '_candidate':working,'_folder':part_folder})
        working=result['candidate'];expected[row['id']]=result['expectation']
    final_scene=read_json(c._resource(task,working['scene']))
    previous={n['id']:n for n in scene['objects']};patches=[]
    for node in final_scene['objects']:
        if node['id'] in owned:patches.extend(dict(p,owner=node['id']) for p in differences(previous[node['id']],node))
    tx.update(patches=patches,planned_scene=working['scene'],display_required=True,instance_expectations=expected)
    tx['post_save']={'statuses':{name:'INSTANCE_NATIVE_CONFIRMATION_REQUIRED' for name in selected}}
    working.update(baseline=candidate['pptx']['sha256'],allowed=allowed,
                   reason={'kind':'component_instance_batch','components':selected})
    saved(task,tx,working);phase(task,tx,'DISPLAY_PENDING',candidate=working)
    task,state=a._state(task);contract,ledger=c._load(task,state)
    state.update(active_candidate=working,scene=working['scene'],revision=working['revision'],stage='host_render',packet=None)
    for name,expectation in expected.items():
        ledger['components'][name].update(status='INSTANCE_NATIVE_CONFIRMATION_REQUIRED',
            instantiation={'candidate':working['pptx'],'expectation':expectation})
    with writer(task):c._save_ledger(task,state,ledger,'instance_batch_saved',{'components':selected})
    return {'status':'INSTANCE_SAVED_ACTUAL_RENDER_REQUIRED','components':selected,
            'candidate':working,'whole_audit_executed':False}
