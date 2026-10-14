"""Persistent work/stop supervision of the existing whole-quality loop.

This is not an acceptance engine. Only quality_loop can accept artwork. A
checkpoint records every current failed leaf and the exact next existing
packet; a pruned strategy never clears an obligation or completes a task.
"""
import copy
from pathlib import Path
from .common import identity, digest, read_json, write_json, safe_path, writer

VERSION = 'task-completion-1'
BAD = {'required_unmeasured', 'UNMEASURED', 'UNVERIFIED', 'UNSUPPORTED', 'STALE',
       'MISSING', 'WORK_REQUIRED', 'SOURCE_BINDING_REQUIRED'}

def target_basis(state):
    flow = state.get('task_completion', {})
    return identity({k: flow.get(k) for k in ('kind', 'criteria', 'scope', 'amendments')})

def initialize(state, kind='reconstruction', scope=None, criteria=None):
    if kind not in ('reconstruction', 'skill_upgrade', 'local_edit'):
        raise ValueError('Declare the task kind; example acceptance and upgrade acceptance differ')
    if 'task_completion' in state:
        flow = state['task_completion']
        if flow['kind'] != kind: raise ValueError('A status message cannot change the task kind')
        return flow
    criteria = criteria or (['production_current','required_behavior_regressions','verified_publication'] if kind=='skill_upgrade' else ['current_whole_acceptance', 'official_current_export'])
    if kind=='skill_upgrade' and criteria!=['production_current','required_behavior_regressions','verified_publication']:
        raise ValueError('Upgrade must verify current production, executable behavior and publication')
    if kind != 'skill_upgrade' and set(criteria) != {'current_whole_acceptance', 'official_current_export'}:
        raise ValueError('Reconstruction cannot finish with a draft or a partial check')
    flow = {'schema': VERSION, 'kind': kind, 'criteria': criteria, 'scope': scope or {},
            'amendments': [], 'backlog': {}, 'branches': {}, 'checkpoints': [], 'status': 'ACTIVE'}
    state['task_completion'] = flow
    return flow

def failed_leaves(value, path=''):
    """Keep individual checks, not only aggregate counts/goal summaries."""
    rows=[]
    if isinstance(value, dict):
        status=value.get('status'); failed=value.get('passed') is False or status in BAD
        if failed:
            detail={k:copy.deepcopy(value[k]) for k in ('id','object','unit','kind','reason','cause','actual','target','tolerance','measurement_basis','next_action') if k in value}
            rows.append({'id': path or 'whole', 'status': status or 'MEASURED_FAIL','result':detail})
        for key, child in value.items():
            if key in ('history','source_ast','native_ast','expected','actual','limits'): continue
            if isinstance(child,(dict,list)): rows.extend(failed_leaves(child,path+'/'+key))
    elif isinstance(value,list):
        for i,child in enumerate(value):
            label=next((str(child[k]) for k in ('id','object','unit','goal') if isinstance(child,dict) and k in child),str(i))
            rows.extend(failed_leaves(child,path+'/'+label))
    return rows

def checkpoint(task, state, candidate, result, next_packet=None):
    from .execution_contract import _basis, _implementation, resource
    if result.get('basis') != _basis(state,candidate) or result.get('implementation') != _implementation():
        raise ValueError('Checkpoint needs the complete current program audit')
    if read_json(resource(task,state['quality_result'])) != result:
        raise ValueError('Caller-supplied PASS fields are not an audit')
    flow=state.get('task_completion') or initialize(state)
    basis=_basis(state,candidate); old=flow['backlog']; current={}
    for row in failed_leaves(result['gates']):
        before=old.get(row['id'],{})
        current[row['id']]={**row, 'basis':basis,'candidate':candidate['pptx']['sha256'],
            'first_seen':before.get('first_seen',basis),'dependencies':before.get('dependencies',[]),
            'write_set':before.get('write_set',{}),'protected_set':before.get('protected_set',{}),
            'next_action':copy.deepcopy(next_packet)}
    resolved=[{'id':k,'prior':v['basis'],'current':basis} for k,v in old.items() if k not in current]
    # Removal is only a new complete current audit transition; manual reset of
    # backlog never enters this writer. The immutable prior result remains.
    flow['backlog']=current; flow['audit']=copy.deepcopy(state['quality_result'])
    flow['candidate']=copy.deepcopy(candidate['pptx']); flow['target_basis']=target_basis(state)
    flow['next']=copy.deepcopy(next_packet); flow['status']='EXPORT_REQUIRED' if result['status']=='ACCEPTED' else 'ACTIVE'
    flow['checkpoints'].append({'basis':basis,'report':copy.deepcopy(state['quality_result']),
        'resolved':resolved,'remaining':sorted(current),'next':copy.deepcopy(next_packet)})
    return {'schema':VERSION,'status':flow['status'],'unresolved':len(current),
            'next':next_packet,'can_finish':False,'reason':'Current acceptance still needs its verified official export' if not current else 'Every unresolved check remains actionable or needs evidenced diagnosis'}

def branch(state, request):
    flow=state.get('task_completion') or initialize(state)
    ids=request.get('obligations',[])
    if not ids or not set(ids)<=set(flow['backlog']) or not request.get('strategy'):
        raise ValueError('A strategy binds existing unresolved check IDs')
    key=identity({'obligations':sorted(ids),'strategy':request['strategy'],'target':target_basis(state)})
    row=flow['branches'].setdefault(key,{'id':key,'strategy':request['strategy'],'obligations':ids,'attempts':[]})
    attempt=request.get('attempt')
    if attempt:
        if attempt.get('outcome') not in ('gain','no_gain','failed','unmeasured') or not attempt.get('evidence'):
            raise ValueError('Branch outcomes require actual result evidence')
        row['attempts'].append(copy.deepcopy(attempt))
    row['pruned']=sum(a['outcome'] in ('no_gain','failed') for a in row['attempts'][-2:])==2
    # no_gain is branch pruning, not task stop, acceptance or debt deletion.
    return row

def amend(state, request):
    flow=state.get('task_completion') or initialize(state)
    if request.get('kind')=='status': return {'status':flow['status'],'next':flow.get('next'),'unresolved':len(flow['backlog'])}
    if request.get('kind')!='user_target' or not request.get('user_evidence') or not request.get('target'):
        raise ValueError('Persist an explicit user amendment, separately from original facts and candidate')
    flow['amendments'].append(copy.deepcopy(request));flow['status']='ACTIVE'
    flow.pop('completion',None);state.pop('acceptance',None);state.pop('quality_result',None)
    return {'status':'TARGET_AMENDED_RECHECK_REQUIRED','target_basis':target_basis(state),'unresolved':len(flow['backlog'])}

def stop_report(task,state,candidate,request):
    from .execution_contract import resource, _basis, _implementation
    flow=state.get('task_completion') or initialize(state)
    reason=request.get('reason')
    if reason=='complete':
        if flow['kind']=='skill_upgrade':
            from .upgrade_validation import verify as verify_upgrade
            result=verify_upgrade(task,state,request)
            flow['status']='COMPLETE';flow['completion']=copy.deepcopy(state['upgrade_validation'])
            return result
        from .quality_loop import final_gate
        final_gate(task,state,candidate)
        acceptance=read_json(resource(task,state['acceptance']))
        audit=read_json(resource(task,state['quality_result']))
        if (acceptance.get('status')!='ACCEPTED' or audit.get('status')!='ACCEPTED'
            or audit.get('basis')!=_basis(state,candidate) or audit.get('implementation')!=_implementation()
            or audit.get('pptx_hash')!=candidate['pptx']['sha256'] or flow['backlog']):
            raise ValueError('Current full acceptance is required; a saved file or partial pass is not completion')
        delivery=read_json(resource(task,request['delivery']))
        if (delivery.get('status')!='ACCEPTED' or delivery.get('pptx_hash')!=candidate['pptx']['sha256']
                or delivery.get('implementation')!=_implementation() or delivery.get('target_basis')!=target_basis(state)):
            raise ValueError('An old export/helper/PDF cannot complete the current task')
        if request['delivery']!=state.get('official_delivery'):raise ValueError('Use the actual official export writer receipt')
        compact=delivery.get('user_delivery')
        if not compact or digest(compact['receipt'])!=compact['receipt_sha256']:
            raise ValueError('Completion needs the actual current compact user delivery, not only an internal export')
        from .user_delivery import verify as verify_compact
        if verify_compact(compact['directory'],compact['receipt'])['file_count']!=2:
            raise ValueError('Completion needs the PPTX/report-only verified final delivery')
        folder=Path(delivery['output']).resolve()
        for path,ref in delivery['files'].items():
            if digest(safe_path(folder,path))!=ref['sha256']:raise ValueError('Official output changed: '+path)
        status='COMPLETE'
    elif reason in ('user_pause','scope_change'):
        if not request.get('user_evidence'):raise ValueError('Stopping needs an explicit human instruction')
        status='PAUSED' if reason=='user_pause' else 'SCOPE_CHANGED'
    elif reason=='external_block':
        blocks=request.get('blocks',[])
        if not blocks:raise ValueError('A workload estimate is not external blocking evidence')
        covered=set()
        for block in blocks:
            if not all(block.get(k) for k in ('operation','error','impact','attempted_routes','no_remaining_route','recovery','obligations','evidence')):
                raise ValueError('Record the exact failure, adequate attempted routes, impact and minimum recovery')
            for ref in block['evidence']: resource(task,ref)
            covered.update(block['obligations'])
        if covered!=set(flow['backlog']):
            raise ValueError('Independent unresolved work remains; continue it before stopping')
        status='EVIDENCED_EXTERNAL_BLOCK'
    else:raise ValueError('Draft/time/workload/failures/branch pruning are not authorized stop reasons')
    result={'schema':VERSION,'status':status,'kind':flow['kind'],'criteria':flow['criteria'],
        'target_basis':target_basis(state),'candidate':candidate['pptx'],'unresolved':sorted(flow['backlog']),
        'next':flow.get('next'),'stop_basis':copy.deepcopy(request)}
    file=task/'audits'/('task-stop-'+identity(result)+'.json');write_json(file,result)
    flow['status']=status;flow['completion']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    return result

def dispatch(task, operation, request=None):
    from . import agent_runtime as a
    task,state=a._state(task);candidate=state.get('active_candidate') or state.get('selected');request=request or {}
    with writer(task):
        if operation=='status': result={'status':state.get('task_completion',{}).get('status','ACTIVE'),'flow':state.get('task_completion',{})}
        elif operation=='begin':result=initialize(state,request.get('kind','reconstruction'),request.get('scope'),request.get('criteria'))
        elif operation=='branch':
            for ref in request.get('attempt',{}).get('evidence',[]):
                from .execution_contract import resource
                resource(task,ref)
            result=branch(state,request)
        elif operation=='amend':result=amend(state,request)
        elif operation=='stop':result=stop_report(task,state,candidate,request)
        elif operation=='resume':
            # Same target, candidate, debt and branch history survive; current
            # implementation/artifact checks invalidate old evidence naturally.
            flow=state.get('task_completion') or initialize(state);flow['status']='ACTIVE'
            flow.pop('completion',None);result={'status':'ACTIVE','candidate':candidate['pptx'] if candidate else None,'next':flow.get('next'),'unresolved':sorted(flow['backlog']),'target_basis':target_basis(state)}
        else:raise ValueError('Unknown task-completion operation')
        a._save(task,state)
    return result
