"""Execute whole-result diagnostics without inventing model observations."""
from collections import Counter
from . import agent_runtime as a,execution_contract as ec,source_quality as sq
from .common import read_json,write_json,digest,identity,writer


def audit_task(task):
    task,state=a._state(task);ec.policy(state)
    if state.get('quality_intent'):
        from .quality_loop import audit
        result=audit(task,state)
        return {'status':result['status'],'report':state['quality_result'],'numeric_summary':result['legacy_summary'],
                'observations':result['observations'],'content_summary':result['content_summary']}
    implementation=ec._implementation()
    candidate=state.get('active_candidate') or state.get('selected')
    if not candidate or not candidate.get('render'):raise ValueError('Audit the actual rendered complete saved candidate')
    original=digest(ec.resource(task,state['source']));native=digest(ec.resource(task,candidate['pptx']))
    receipt=read_json(ec.resource(task,candidate['render']))
    if receipt.get('pptx_hash')!=native or receipt.get('preview_hash')!=digest(ec.resource(task,candidate['preview'])):
        raise ValueError('Working audit needs exact native/preview render identities')
    items=[]
    for unit in state.get('quality',{}).get('units',{}).values():
        try:result=sq.evaluate(task,state,candidate,unit)
        except (ValueError,KeyError,FileNotFoundError,TypeError) as error:
            result={'unit':unit['id'],'status':'required_unmeasured','reason':str(error)}
        items.append(result)
        from .quality_observations import record_program
        record_program(state,'source_correspondence',unit['id'],result,
                       identity({'source':state['source'],'candidate':candidate['pptx'],'unit':unit,'implementation':implementation}))
    result={'schema':'whole-working-audit-1','status':'CHECKS_EXECUTED_QUALITY_PENDING',
        'source_hash':original,'pptx_hash':native,'render_backend':receipt.get('backend'),
        'implementation':implementation,'source_units':items,
        'numeric_summary':dict(Counter(r['status'] for r in items)),
        'independent_observation_count':len(state.get('quality',{}).get('observations',{})),
        'limits':'Numeric measurements do not manufacture original semantic/content observations or acceptance.'}
    try:
        result['final_gate']=ec.final_gate(task,state,candidate)
        result['status']='ACCEPTED_DIAGNOSTICS'
    except (ValueError,KeyError,FileNotFoundError,TypeError) as error:
        result['final_gate_error']=str(error)
        if state.get('acceptance'):
            value=read_json(ec.resource(task,state['acceptance']))
            if value.get('basis')==ec._basis(state,candidate):result['final_gate_receipt']=state['acceptance']
    if ec._implementation()!=implementation:
        raise ValueError('Executor changed during the audit; retain diagnostics and rerun on frozen code')
    if digest(ec.resource(task,candidate['pptx']))!=native or digest(ec.resource(task,state['source']))!=original:
        raise ValueError('A read/check audit unexpectedly changed source or drawing bytes')
    folder=task/'audits';folder.mkdir(exist_ok=True)
    path=folder/('working-audit-'+identity(result)+'.json');write_json(path,result)
    with writer(task):
        state['working_audit']={'path':path.relative_to(task).as_posix(),'sha256':digest(path)}
        a._event(task,'whole_actual_drawing_audited',{'report':state['working_audit'],
            'numeric_summary':result['numeric_summary'],'drawing_gain':False,'acceptance':result['status']=='ACCEPTED_DIAGNOSTICS'})
        a._save(task,state)
    return {'status':result['status'],'report':state['working_audit'],'numeric_summary':result['numeric_summary'],
        'original_unchanged':original,'pptx_unchanged':native,'final_gate':result.get('final_gate',{}).get('status','BLOCKED')}
