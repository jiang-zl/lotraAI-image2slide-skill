"""Adopt user native bytes with component mappings and persistent field locks."""
import copy
import shutil
from pathlib import Path
from .common import read_json,write_json,identity,writer


def sync(task,state,edited_pptx):
    from . import component_workflow as c
    from .native_snapshot import snapshot
    from .native_core_checks import snapshots
    from .component_transactions import differences
    from .state_repository import Repository
    contract,ledger=c._load(task,state);old=c._candidate(state)
    if not contract or not old:raise ValueError('A component contract and native baseline are required')
    if ledger.get('pending_transaction'):raise ValueError('Recover the component transaction before adopting external edits')
    edited=Path(edited_pptx).resolve()
    if not edited.is_file():raise ValueError('Edited native file absent')
    revision=state['revision']+1;folder=task/'versions'/('component-user-'+str(revision).zfill(4))
    folder.mkdir(exist_ok=False);retained=folder/'drawing.pptx';shutil.copyfile(edited,retained)
    before=read_json(c._resource(task,old['scene']))
    actual=snapshot(task,state,retained,before)
    bnodes={n['id']:n for n in before['objects']};anodes={n['id']:n for n in actual['objects']}
    old_native=snapshots(c._resource(task,old.get('retained_pptx',old['pptx'])),component_mode=True)
    new_native=snapshots(retained,component_mode=True)
    changed={key for key in set(old_native)|set(new_native) if
        any(old_native.get(key,{}).get(field)!=new_native.get(key,{}).get(field) for field in ('body','placement'))}
    # Keep unchanged source recipes exactly; import only actual modified owners.
    actual['objects']=[anodes[key] if key in changed else bnodes.get(key,anodes[key]) for key in anodes]
    scene_file=folder/'scene.json';write_json(scene_file,actual)
    candidate={**old,'revision':revision,'pptx':c._ref(task,retained),'scene':c._ref(task,scene_file),
               'reason':{'kind':'component_user_sync'},'native_authority':'user_edit'}
    candidate.pop('preview',None);candidate.pop('render',None)
    candidate.pop('font_delivery',None)
    from .component_transactions import retain_native
    retain_native(task,candidate)
    repository=Repository(task);scope=state['component_workflow']['contract']['sha256']
    mapped={};unmapped=[]
    for owner in sorted(changed):
        binding=repository.lookup('native_owner:'+scope,owner)
        if not binding:
            row=next((r for r in contract['components'] if owner in r['owners']),None)
            if row:
                binding={'component':row['id']};repository.index_rows('native_owner:'+scope,{owner:binding})
        if not binding:
            # A renamed/new object needs an explicit component contract decision.
            unmapped.append(owner);continue
        key=binding['component'];record=ledger['components'][key]
        patches=list(differences(bnodes.get(owner),anodes.get(owner),before_exists=owner in bnodes,after_exists=owner in anodes))
        fields=[p['field'] for p in patches if not p['field'] or p['field'][0] in ('bbox','style','content','parent')]
        # Native-only edits still need protection when the Scene importer cannot decode them.
        if not fields:fields=[[]]
        locks=record.setdefault('user_locks',[])
        for field in fields:
            if not any(v['owner']==owner and v['field']==field for v in locks):
                locks.append({'owner':owner,'field':field,'authority':'user','pptx':candidate['pptx'],
                              'reason':'Explicitly adopted user native edit'})
        record.update(status='USER_INTENT_REQUIRED');record.pop('instantiation',None)
        mapped.setdefault(key,[]).append(owner)
    structural=sorted(set(bnodes)^set(anodes))
    unresolved=sorted(set(unmapped)|set(structural))
    if unresolved:
        ledger.setdefault('orphan_user_locks',[]).extend(
            {'owner':owner,'field':[],'authority':'user','pptx':candidate['pptx'],'reason':'Unmapped adopted user object'} for owner in unmapped)
        ledger['user_reconciliation']={'status':'OWNER_MAPPING_REQUIRED','owners':unresolved,'candidate':candidate['pptx']}
    state.setdefault('external_versions',[]).append({'revision':revision,'prior':old,'candidate':candidate,
                                                    'changed_owners':sorted(changed),'unmapped_owners':unmapped})
    state.update(revision=revision,active_candidate=candidate,selected=None,scene=candidate['scene'],
                 stage='host_render',packet=None)
    state.pop('acceptance',None)
    c.refresh(task,state,contract,ledger,candidate)
    ledger.update(layout_ready=False,final_dirty=True,final_result=None)
    # Refresh invalidation must never discard the user's intent or lock authority.
    for key in mapped:ledger['components'][key]['status']='USER_INTENT_REQUIRED'
    with writer(task):c._save_ledger(task,state,ledger,'user_native_adopted',{'components':mapped,'unmapped':unmapped})
    return {'status':'USER_ADOPTED_COMPONENT_RECONCILIATION_REQUIRED','revision':revision,
            'changed_owners':sorted(changed),'unmapped_owners':unmapped,
            'user_locks_preserved':True,'acceptance':False,'whole_audit_executed':False}


def reconcile(task,request):
    """Explicitly map a retained user snapshot; never infer quality approval."""
    from . import agent_runtime as a,component_workflow as c
    task,state=a._state(task);contract,ledger=c._load(task,state);candidate=c._candidate(state)
    pending=ledger.get('user_reconciliation')
    if not pending or request.get('pptx_hash')!=candidate['pptx']['sha256']:
        raise ValueError('Current user ownership reconciliation required')
    if request.get('authority_kind')!='user_intent' or not request.get('revision_reason'):
        raise ValueError('Locate the adopted user intent and its component mapping')
    expected=read_json(c._resource(task,request['source_scene']))
    actual=read_json(c._resource(task,candidate['scene']))
    if {n['id'] for n in expected['objects']}!={n['id'] for n in actual['objects']}:
        raise ValueError('Reconciliation must cover every actually adopted owner')
    old_by_owner={owner:record for row in contract['components'] for owner in row['owners']
                  for record in [ledger['components'][row['id']]]}
    proof=request['authority'];c._resource(task,proof)
    result=c.bind(task,request)
    task,state=a._state(task);contract,ledger=c._load(task,state)
    for row in contract['components']:
        locks=ledger['components'][row['id']].setdefault('user_locks',[])
        for owner in row['owners']:
            for lock in old_by_owner.get(owner,{}).get('user_locks',[]):
                if lock['owner']==owner and lock not in locks:locks.append(copy.deepcopy(lock))
    ledger['user_reconciliation']=None
    with writer(task):c._save_ledger(task,state,ledger,'user_owner_mapping_bound',{'evidence':proof})
    return dict(result,status='USER_OWNER_MAPPING_BOUND_QUALITY_PENDING')
