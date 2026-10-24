"""One first-render local closure in the registered component action loop."""
from .common import read_json,writer


def enabled(contract):return contract.get('source_review_policy')=='source-review-1.37.5'


def current(row,record):
    review=record.get('appearance_review') or {}
    return review.get('passed') is True and review.get('signature')==record.get('observed_measurement_signature') and review.get('feature_basis')==row.get('feature_basis')


def submit(task,request):
    from .workflow_guard import require
    require(task,'review_local')
    from . import component_workflow as c,agent_runtime as a
    task,state=a._state(task);contract,ledger=c._load(task,state);candidate=c._candidate(state)
    if not enabled(contract) or not candidate:raise ValueError('Current early-local-review contract/candidate required')
    c.actual_render(task,state,candidate,independent=True);c.refresh(task,state,contract,ledger,candidate)
    name=request['component'];row=c.component_row(task,state,contract,name);record=ledger['components'][name]
    if record['status']!='QUALIFIED':raise ValueError('Close native consistency before appearance review')
    evidence=request['evidence'];actual=read_json(c._resource(task,evidence))
    if (actual.get('source_hash')!=state['source']['sha256'] or actual.get('pptx_hash')!=candidate['pptx']['sha256'] or
        actual.get('preview_hash')!=candidate['preview']['sha256'] or actual.get('component')!=name or
        actual.get('observer') not in ('host_model','human') or not actual.get('observations')):
        raise ValueError('Local appearance evidence needs this original, saved bytes, actual preview, component and observer')
    from .component_source_features import local_review,probes
    features=local_review(row,actual)
    checks={'feature_appearance':features,'source_probes':probes(task,state,candidate,row.get('source_features',[]))}
    from .text_appearance import evaluate as text_evaluate
    checks['whole_string_ink']=text_evaluate(task,state,candidate,row.get('source_features',[]))
    ids={f['id'] for f in row.get('source_features',[]) if f.get('line')}
    if ids:
        from .line_verification import evaluate as line_evaluate
        checks['source_lines_render']=line_evaluate(task,state,candidate,contract,render=True,feature_ids=ids)
    if actual.get('verdict')!='PASS' or not all(v.get('passed') is True for v in checks.values()):
        return c.failure_decision(task,state,contract,ledger,candidate,{'local_appearance':checks,'visual':actual,'evidence':evidence},row,
            'Resolve this first-render local source/native/measurement failure before reuse and final layout')
    record['appearance_review']={'passed':True,'signature':record['observed_measurement_signature'],
        'feature_basis':row.get('feature_basis'),'evidence':evidence,'checks':checks,
        'pptx_hash':candidate['pptx']['sha256'],'preview_hash':candidate['preview']['sha256']}
    with writer(task):c._save_ledger(task,state,ledger,'first_render_local_reviewed',{'component':name})
    return {'status':'LOCAL_APPEARANCE_REVIEWED','component':name,'whole_audit_executed':False,'acceptance':False}
