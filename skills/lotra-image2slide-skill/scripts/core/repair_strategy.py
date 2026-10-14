"""Finite evidence-bound repair branches; one exhausted branch is not a task."""
from .common import identity

OPERATORS={'geometry','paint_order','native_style','font','representation','render','source_rebinding'}


def operator(cause, grants, method=None):
    stage=cause.get('stage')
    if stage in ('source_specification','font','render','z_order'):
        return {'source_specification':'source_rebinding','font':'font','render':'render','z_order':'paint_order'}[stage]
    fields={f for values in grants.values() for f in values}
    if fields & {'replace_component','add','remove'}:return 'representation'
    if any(f.startswith(('bbox','geometry','position','group_translate')) for f in fields):return 'geometry'
    return 'native_style'


def key(state,issue,cause,op):
    spec=state.get('quality',{}).get('specifications',{}).get(issue.get('owner'),{})
    # Free-form explanations, candidate file names and changed prose cannot
    # create a fresh branch. A source correction gets a preserved new spec.
    return identity({'issue':issue['id'],'property':issue['property'],'source_spec':identity(spec),
                     'stage':cause.get('stage'),'operator':op})


def authorize(state,issue,cause,grants,method=None):
    if any('paint_order' in fields for fields in grants.values()) and cause.get('stage')!='z_order':
        raise ValueError('A paint-order operation needs an explicit pair-specific layer diagnosis')
    op=operator(cause,grants,method); branch=key(state,issue,cause,op)
    record=issue.setdefault('strategies',{}).setdefault(branch,{'operator':op,'stage':cause['stage'],'failures':0,'attempts':0,'gains':0})
    if record['failures']>=min(2,state['objectives'].get('max_branch_failures',2)):
        raise ValueError('This source/cause/operator branch is exhausted; new wording is not new evidence')
    if issue.get('attempt_count',0)>=state['objectives'].get('max_issue_repairs',12):
        raise ValueError('Issue repair budget exhausted; keep the best and explicit unresolved debt')
    proposed=issue.get('proposed_strategy')
    if proposed and (proposed['stage']!=cause['stage'] or proposed['operator']!=op):
        raise ValueError('Execute the selected evidenced strategy, or explicitly revise it')
    record['attempts']+=1
    return branch


def record(state,issue,candidate,*,gain,meaningful=True):
    branch=(candidate.get('reason') or {}).get('strategy_branch')
    if not branch:return
    value=issue['strategies'][branch]
    if gain and meaningful:
        value['gains']+=1;value['failures']=0;issue.pop('needs_strategy',None)
    else:
        value['failures']+=1
        if value['failures']>=state['objectives'].get('max_branch_failures',2):issue['needs_strategy']=True
    issue.pop('proposed_strategy',None)


def choose(task,state,issue,result):
    choice=result.get('strategy') or {}
    if choice.get('action')=='stop':
        issue['strategy_exhausted']=True;issue['stop_reason']=choice.get('reason','No evidenced useful route');return
    if choice.get('action')!='select':raise ValueError('Select a concrete strategy or stop this issue')
    cause=choice.get('cause') or {};op=choice.get('operator')
    if op not in OPERATORS:raise ValueError('Choose a finite operation class, not an invented alias')
    from .source_quality import validate_cause
    validate_cause(task,state,issue,cause)
    branch=key(state,issue,cause,op)
    if issue.get('strategies',{}).get(branch,{}).get('failures',0)>=state['objectives'].get('max_branch_failures',2):
        raise ValueError('Choose a different source-supported cause/operator branch')
    old_stages={v['stage'] for v in issue.get('strategies',{}).values() if v.get('failures',0)>=2}
    if cause['stage'] not in old_stages and not cause.get('evidence',{}).get('contrast_artifact'):
        raise ValueError('A changed cause needs a contrasting real intermediate artifact')
    contrast=cause.get('evidence',{}).get('contrast_artifact')
    if contrast:
        from .common import safe_path,digest
        if digest(safe_path(task,contrast['path']))!=contrast['sha256']:raise ValueError('Contrasting root evidence changed')
        if contrast['sha256']==cause['evidence']['artifact']['sha256']:raise ValueError('Two identical artifacts do not distinguish causes')
    issue['proposed_strategy']={'stage':cause['stage'],'operator':op,'cause':cause}
    issue.pop('needs_strategy',None)
