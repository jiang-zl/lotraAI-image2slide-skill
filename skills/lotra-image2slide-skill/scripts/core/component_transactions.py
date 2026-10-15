"""Journaled native transactions, idempotent adoption and field-scoped reversal."""
import copy
import os
from pathlib import Path
from .common import identity,read_json,write_json,digest,safe_path,writer

PHASES=('PLANNED','STAGED','NATIVE_SAVED','DISPLAY_PENDING','LOCAL_RESULT_READY','ADOPTED','CLOSED')


from .component_fields import differences


def begin(task,state,scene,baseline,allowed,reason):
    from . import component_workflow as c
    contract,ledger=c._load(task,state)
    if ledger.get('pending_transaction'):
        raise ValueError('Resume the registered transaction before native mutation')
    before=read_json(c._resource(task,baseline['scene'])) if baseline else {'objects':[]}
    old={node['id']:node for node in before['objects']};new={node['id']:node for node in scene['objects']}
    patches=[]
    for owner in sorted(set(old)|set(new)):
        if old.get(owner)!=new.get(owner):
            if baseline and owner not in allowed: raise ValueError('Transaction escaped declared native owner scope')
            if owner not in old or owner not in new:
                patches.append({'owner':owner,'field':[],'before_exists':owner in old,'after_exists':owner in new,
                                'before':old.get(owner),'after':new.get(owner)})
            else:
                patches.extend(dict(item,owner=owner) for item in differences(old[owner],new[owner]))
    plan={'task':state['task_id'],'source':state['source']['sha256'],'base_revision':state['revision'],
          'baseline':baseline,'allowed':allowed,'reason':reason,'patches':patches,
          'contract':state['component_workflow']['contract'],'post_save':copy.deepcopy((reason or {}).get('post_save',{}))}
    if (reason or {}).get('kind')=='component_numeric_batch':
        plan['post_save']['statuses']={key:'ACTUAL_NATIVE_CONFIRMATION_REQUIRED' for key in reason['components']}
    key=identity(plan);folder=task/'transactions'/key;folder.mkdir(parents=True,exist_ok=True)
    file=folder/'Transaction.json'
    if file.exists():
        tx=read_json(file)
        if tx['phase'] not in ('CLOSED',):
            ledger['pending_transaction']={'id':key,'path':tx['path']}
            with writer(task):c._save_ledger(task,state,ledger,'orphan_transaction_registered',{'id':key})
            raise ValueError('RECOVERY_REQUIRED: existing transaction registered; continue through next/recover')
        return tx
    planned=folder/'Planned-scene.json';write_json(planned,scene)
    tx={**plan,'id':key,'phase':'PLANNED','planned_scene':c._ref(task,planned),
        'path':file.relative_to(task).as_posix(),'candidate':None,
        'local_components':[row['id'] for row in contract['components'] if not allowed or set(row['owners']).intersection(allowed)]}
    write_json(file,tx)
    ledger['pending_transaction']={'id':key,'path':tx['path']}
    with writer(task):c._save_ledger(task,state,ledger,'transaction_planned',{'id':key})
    phase(task,tx,'STAGED')
    return tx


def phase(task,tx,value,**fields):
    if value not in PHASES: raise ValueError('Unknown transaction stage')
    tx.update(fields,phase=value)
    write_json(safe_path(task,tx['path']),tx)
    return tx


def saved(task,tx,candidate):
    """Ready is written last, after all immutable artifacts have final names."""
    for key in ('scene','pptx'):
        file=safe_path(task,candidate[key]['path'])
        if digest(file)!=candidate[key]['sha256']:raise ValueError('Saved transaction artifact changed')
    retain_native(task,candidate)
    folder=safe_path(task,tx['path']).parent
    # Persist the complete plan before its ready marker, including instance expectations.
    marker=folder/('Ready-'+candidate['pptx']['sha256']+'.json')
    phase(task,tx,'STAGED',candidate=candidate,ready_marker=marker.relative_to(task).as_posix())
    manifest={'transaction':tx['id'],'candidate':candidate,'planned_scene':tx['planned_scene'],
              'post_save':copy.deepcopy(tx.get('post_save',{}))}
    write_json(marker,manifest)
    write_json(folder/'Ready.json',manifest)
    phase(task,tx,'NATIVE_SAVED',candidate=candidate)


def release_local(task,state,ledger,tx):
    apply_post_save(task,state,ledger,tx,candidate=tx['candidate'])
    ledger['pending_transaction']=None
    owners=set((tx.get('allowed') or {}).keys())
    contract,_=__import__(__package__+'.component_workflow',fromlist=['_load'])._load(task,state)
    for row in contract['components']:
        if not owners or owners.intersection(row['owners']):
            record=ledger['components'][row['id']]
            if record['status']=='QUALIFIED':
                tx.setdefault('local_results',{})[row['id']]=True
            else:
                record['local_transaction']=tx['path'];record['component_id']=row['id']
    phase(task,tx,'LOCAL_RESULT_READY')
    if set(tx.get('local_components',[]))<=set(tx.get('local_results',{})):
        if all(tx['local_results'].values()):phase(task,tx,'ADOPTED')
        phase(task,tx,'CLOSED')


def local_result(task,record,passed):
    ref=record.get('local_transaction')
    if not ref:return
    tx=read_json(safe_path(task,ref))
    # A batch can serve multiple parts; closure of one is not a pass for others.
    tx.setdefault('local_results',{})[record.get('component_id','local')]=bool(passed)
    if set(tx.get('local_components',[]))<=set(tx['local_results']):
        if all(tx['local_results'].values()):phase(task,tx,'ADOPTED')
        phase(task,tx,'CLOSED',local_results=tx['local_results'])
    else:write_json(safe_path(task,tx['path']),tx)
    record.pop('local_transaction',None)


def recover(task,request=None):
    from . import agent_runtime as a,component_workflow as c
    task,state=a._state(task);contract,ledger=c._load(task,state)
    pending=ledger.get('pending_transaction')
    if not pending:return {'status':'NO_PENDING_COMPONENT_TRANSACTION'}
    if not pending.get('path'):
        return {'status':'LEGACY_TRANSACTION_INSPECTION_REQUIRED','transaction':pending,
                'reason':'Legacy artifacts retained; bind their exact output before stage recovery'}
    tx=read_json(safe_path(task,pending['path']));folder=safe_path(task,tx['path']).parent
    current=c._candidate(state)
    baseline_hash=(tx.get('baseline') or {}).get('pptx',{}).get('sha256')
    current_hash=(current or {}).get('pptx',{}).get('sha256')
    accepted_inputs={baseline_hash,*tx.get('prior_candidate_hashes',[])}
    ready=safe_path(task,tx['ready_marker']) if tx.get('ready_marker') else folder/'Ready.json'
    if not ready.exists() and tx['phase']=='STAGED' and tx.get('candidate'):
        # The saved() journal contains hashes only after both final files exist.
        # Recreate its missing ready marker, retaining those exact bytes.
        saved(task,tx,tx['candidate'])
        ready=safe_path(task,tx['ready_marker'])
    if tx['source']!=state['source']['sha256']:
        return {'status':'TRANSACTION_INPUT_CONFLICT','transaction':tx['id'],'field':'source'}
    request=request or {}
    font_redecision=request.get('action')=='retain_font_candidate_and_redecide'
    if font_redecision:
        if not current or current.get('font_delivery',{}).get('embedding',{}).get('status')!='FONT_EMBEDDING_PROVIDER_REQUIRED':
            raise ValueError('A retained pending font candidate is required')
        if not request.get('reason') or not request.get('evidence'):raise ValueError('Located font recovery decision required')
        c._resource(task,request['evidence'])
        for name in tx.get('local_components',[]):
            if name in ledger['components']:ledger['components'][name]['status']='SOURCE_DECISION_REQUIRED'
        ledger['pending_transaction']=None
        state.update(stage='review',packet=None)
        phase(task,tx,'CLOSED',outcome='FONT_CANDIDATE_RETAINED_NOT_QUALIFIED',closure_evidence=request['evidence'])
        with writer(task):c._save_ledger(task,state,ledger,'font_provider_redecision',{'transaction':tx['id']})
        return {'status':'FONT_SOURCE_DECISION_REQUIRED','candidate_retained':True,'acceptance':False}
    if not ready.exists() and request.get('action')=='retain_and_redecide':
        if current_hash!=baseline_hash or not request.get('reason') or not request.get('evidence'):
            raise ValueError('Retained baseline, located reason and evidence required to close an incomplete attempt')
        c._resource(task,request['evidence'])
        for name in tx.get('local_components',[]):
            if name in ledger['components']:ledger['components'][name]['status']='SOURCE_DECISION_REQUIRED'
        phase(task,tx,'CLOSED',outcome='INCOMPLETE_ATTEMPTS_RETAINED',closure_evidence=request['evidence'])
        ledger['pending_transaction']=None
        with writer(task):c._save_ledger(task,state,ledger,'incomplete_transaction_retained',{'id':tx['id']})
        return {'status':'SOURCE_DECISION_REQUIRED','artifacts_preserved':True,'acceptance':False}
    if tx.get('contract') and tx['contract']!=state['component_workflow']['contract']:
        return {'status':'TRANSACTION_CONTRACT_CONFLICT','transaction':tx['id']}
    if ready.exists():
        record=read_json(ready)
        if record['transaction']!=tx['id'] or record['planned_scene']!=tx['planned_scene']:
            raise ValueError('Transaction ready marker belongs to another plan')
        if record.get('post_save',{})!=tx.get('post_save',{}):raise ValueError('Ready postconditions differ from the saved journal')
        candidate=record['candidate']
        for key in ('pptx','scene'):c._resource(task,candidate[key])
        if current_hash not in accepted_inputs|{candidate['pptx']['sha256']}:
            return {'status':'TRANSACTION_NATIVE_CONFLICT','transaction':tx['id'],'candidate_retained':True}
        if current_hash!=candidate['pptx']['sha256']:
            state.update(active_candidate=candidate,scene=candidate['scene'],revision=candidate['revision'],stage='host_render',packet=None)
            with writer(task):a._save(task,state)
            current=candidate
        tx['candidate']=current
        apply_post_save(task,state,ledger,tx,current)
        with writer(task):c._save_ledger(task,state,ledger,'transaction_postconditions_restored',{'id':tx['id']})
        if current.get('font_delivery',{}).get('embedding',{}).get('status')=='FONT_EMBEDDING_PROVIDER_REQUIRED':
            state.update(stage='font_delivery',active_candidate=current,packet=None)
            with writer(task):a._save(task,state)
            return {'status':'FONT_EMBEDDING_PROVIDER_REQUIRED','candidate':current}
        for row_id,expectation in tx.get('instance_expectations',{}).items():
            ledger['components'][row_id]['instantiation']={'candidate':current['pptx'],'expectation':expectation}
        if tx.get('instance_expectation'):
            row_id=tx['reason']['id']
            ledger['components'][row_id]['instantiation']={'candidate':current['pptx'],'expectation':tx['instance_expectation']}
        if current.get('preview') and current.get('render'):
            c.actual_render(task,state,current)
            release_local(task,state,ledger,tx)
            with writer(task):c._save_ledger(task,state,ledger,'transaction_local_ready',{'id':tx['id']})
            return {'status':'LOCAL_RESULT_READY','transaction':tx['id']}
        if tx.get('display_required',True):
            phase(task,tx,'DISPLAY_PENDING',candidate=current)
            return {'status':'ACTUAL_RENDER_REQUIRED','candidate':current,'transaction':tx['id']}
        release_local(task,state,ledger,tx)
        with writer(task):c._save_ledger(task,state,ledger,'transaction_local_ready',{'id':tx['id']})
        return {'status':'LOCAL_RESULT_READY','transaction':tx['id']}
    if tx['phase'] in ('PLANNED','STAGED'):
        if current_hash!=baseline_hash:
            return {'status':'TRANSACTION_NATIVE_CONFLICT','transaction':tx['id']}
        if len(tx.get('native_attempts',[]))>=contract['policy'].get('recovery_attempt_limit',3):
            return {'status':'RECOVERY_INSPECTION_REQUIRED','transaction':tx['id'],
                    'return':'action=retain_and_redecide, reason, evidence; preserve baseline and incomplete artifacts'}
        if (tx.get('reason') or {}).get('kind')=='component_batch':
            from .component_batch import commit
            return commit(task,{**tx['reason']['request'],'_transaction':tx})
        if (tx.get('reason') or {}).get('kind')=='component_instance_copy':
            from .component_instances import instantiate
            return instantiate(task,{'component':tx['reason']['id'],'source_hash':state['source']['sha256'],
                                     'pptx_hash':current_hash,'_transaction':tx})
        from .component_constructor import construct
        scene=read_json(c._resource(task,tx['planned_scene']))
        candidate=construct(task,state,scene,baseline=tx['baseline'],allowed=tx['allowed'],reason=tx['reason'],transaction=tx)
        return {'status':'TRANSACTION_NATIVE_RESUMED','candidate':candidate}
    if tx['phase'] in ('ADOPTED','CLOSED'):
        phase(task,tx,'CLOSED');ledger['pending_transaction']=None
        with writer(task):c._save_ledger(task,state,ledger,'transaction_closed',{'id':tx['id']})
        return {'status':'TRANSACTION_CLOSED','transaction':tx['id']}
    return {'status':'TRANSACTION_ARTIFACT_REQUIRED','transaction':tx['id'],'artifacts_preserved':True}


def rollback(task,request):
    from . import agent_runtime as a,component_workflow as c
    from .component_constructor import construct
    task,state=a._state(task);contract,ledger=c._load(task,state);candidate=c._candidate(state)
    tx=read_json(safe_path(task,request['transaction']))
    scene=read_json(c._resource(task,candidate['scene']));nodes={n['id']:n for n in scene['objects']}
    conflicts=[]
    for patch in tx['patches']:
        owner=patch['owner'];pointer=nodes.get(owner);exists=owner in nodes
        from .component_fields import lookup
        if exists:exists,pointer=lookup(pointer,patch['field'])
        if exists!=patch['after_exists'] or exists and pointer!=patch['after']:conflicts.append({'owner':owner,'field':patch['field']})
    if conflicts:return {'status':'ROLLBACK_FIELD_CONFLICT','fields':conflicts,'user_edits_preserved':True}
    for patch in tx['patches']:
        owner=patch['owner'];path=patch['field']
        if not path:
            if patch['before_exists']:nodes[owner]=copy.deepcopy(patch['before'])
            else:nodes.pop(owner,None)
        else:
            pointer=nodes[owner]
            for key in path[:-1]:pointer=pointer[key]
            if patch['before_exists']:pointer[path[-1]]=copy.deepcopy(patch['before'])
            else:pointer.pop(path[-1],None)
    scene['objects']=[nodes[n['id']] for n in scene['objects'] if n['id'] in nodes]
    present={n['id'] for n in scene['objects']}
    scene['objects'].extend(value for key,value in nodes.items() if key not in present)
    affected=set(p['owner'] for p in tx['patches'])
    for row in contract['components']:
        if affected.intersection(row['owners']):
            record=ledger['components'][row['id']]
            if record.get('user_locks'):return {'status':'USER_LOCK_CONFLICT','component':row['id']}
            record['status']='RECHECK_REQUIRED'
    with writer(task):c._save_ledger(task,state,ledger,'field_rollback_planned',{'transaction':tx['id']})
    saved_candidate=construct(task,state,scene,candidate,tx['allowed'],{'kind':'field_rollback','transaction':tx['id']})
    return {'status':'ROLLBACK_CANDIDATE_SAVED','candidate':saved_candidate,'unrelated_edits_preserved':True}



def attempt_folder(task,tx):
    """Never reuse half-written native files; bound and retain every attempt."""
    from .component_protocol import policy
    attempts=tx.setdefault('native_attempts',[])
    limit=policy().get('recovery_attempt_limit',3)
    if len(attempts)>=limit:
        raise ValueError('RECOVERY_INSPECTION_REQUIRED: native attempt budget exhausted; partial artifacts retained')
    folder=safe_path(task,tx['path']).parent/('native-attempt-'+str(len(attempts)+1).zfill(3))
    if folder.exists():raise ValueError('Unregistered native attempt retained for inspection')
    # Journal reservation precedes file creation, so restart advances monotonically.
    attempts.append(folder.relative_to(task).as_posix())
    phase(task,tx,'STAGED',native_attempts=attempts)
    folder.mkdir()
    return folder


def retain_native(task,candidate):
    """Keep a content-addressed preimage if the user edits the visible task file."""
    import shutil
    from . import component_workflow as c
    source=c._resource(task,candidate['pptx'])
    folder=task/'resources/native-preimages';folder.mkdir(parents=True,exist_ok=True)
    file=folder/(candidate['pptx']['sha256']+'.pptx')
    if not file.exists():
        temp=file.with_suffix('.pptx.part')
        if temp.exists():
            if digest(temp)==candidate['pptx']['sha256']:os.replace(temp,file)
            else:
                archived=temp.with_name(temp.name+'.retained-'+digest(temp)[:24])
                if archived.exists():
                    raise ValueError('RECOVERY_INSPECTION_REQUIRED: repeated incomplete preimage retained')
                os.replace(temp,archived)
        if not file.exists():shutil.copyfile(source,temp);os.replace(temp,file)
    elif digest(file)!=candidate['pptx']['sha256']:
        raise ValueError('Immutable native preimage changed')
    candidate['retained_pptx']=c._ref(task,file)


def apply_post_save(task,state,ledger,tx,candidate):
    """Replay the ledger transition persisted before Ready, once per native identity."""
    post=tx.get('post_save',{})
    if post.get('complete_import'):state.pop('component_import_pending',None)
    # Replay binding state even when the ledger was committed before an interrupted state save.
    for key,value in post.get('state_updates',{}).items():
        if key not in ('font_contract','font_collection'):raise ValueError('Unsupported reconstruction post-save state field')
        state[key]=copy.deepcopy(value)
    token=tx['id']+':'+candidate['pptx']['sha256']
    applied=ledger.setdefault('applied_post_save',[])
    if token in applied:return
    for name,status in post.get('statuses',{}).items():
        ledger['components'][name]['status']=status
    if (tx.get('reason') or {}).get('kind')=='component_numeric_batch':
        for name in tx['reason']['components']:
            record=ledger['components'][name]
            record['numeric_saved_result']={'candidate':copy.deepcopy(candidate),'fit':record.get('last_fit')}
    for name,expectation in tx.get('instance_expectations',{}).items():
        ledger['components'][name].update(status='INSTANCE_NATIVE_CONFIRMATION_REQUIRED',
            instantiation={'candidate':candidate['pptx'],'expectation':expectation})
    if tx.get('instance_expectation'):
        name=tx['reason']['id']
        ledger['components'][name].update(status='INSTANCE_NATIVE_CONFIRMATION_REQUIRED',
            instantiation={'candidate':candidate['pptx'],'expectation':tx['instance_expectation']})
    for name in post.get('consume_grants',[]):ledger['components'][name].pop('repair_grant',None)
    if post.get('consume_structural_grant'):ledger.pop('structural_grant',None)
    if post.get('font_review'):
        ledger['font_review']=copy.deepcopy(post['font_review'])
    for name in post.get('drop_instantiation',[]):ledger['components'][name].pop('instantiation',None)
    for name in post.get('relations_remove',[]):ledger['relations'].pop(name,None)
    if post.get('layout_dirty'):ledger.update(layout_ready=False,final_dirty=True,final_result=None)
    if post.get('repair_batch_status') and ledger.get('repair_batch'):
        ledger['repair_batch']['status']=post['repair_batch_status']
    applied.append(token)
