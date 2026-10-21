"""Product protocol grants, not a security boundary against writable local code."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from .common import read_json, safe_path, digest

POLICY='workflow-execution-1.37.0'
_GRANT=ContextVar('lotra_workflow_grant',default=None)


def enabled(state):
    return state.get('execution_policy')==POLICY


def developer_active():
    return (_GRANT.get() or {}).get('mode')=='developer_draft'


def blocked(reason):
    raise ValueError('WORKFLOW_REQUIRED: '+reason+'; use current next/submit, retain progress, and do not deliver a candidate as accepted')


@contextmanager
def packet_writer(task,state,packet):
    task=Path(task).resolve()
    if enabled(state):
        if (packet.get('packet_id')!=(state.get('packet') or {}).get('packet_id') or
                packet.get('source')!=state['source']['sha256'] or packet.get('revision')!=state['revision']):
            blocked('a current original/revision-bound packet is required')
        if digest(safe_path(task,state['source']['path']))!=state['source']['sha256']:
            blocked('the original evidence changed')
    grant={'task':task,'source':state['source']['sha256'],'packet_id':packet.get('packet_id'),
        'kind':packet.get('kind'),'target':packet.get('target'),
        'operation':packet.get('submit_operation') or packet.get('component_action',{}).get('operation'),'mode':'packet'}
    token=_GRANT.set(grant)
    try:yield
    finally:_GRANT.reset(token)


@contextmanager
def finite_writer(task):
    """Only the existing deterministic bounded action generator calls this."""
    task=Path(task).resolve();token=_GRANT.set({'task':task,'mode':'finite'})
    try:yield
    finally:_GRANT.reset(token)


def require(task,operation):
    task=Path(task).resolve()
    from .agent_runtime import _read_state
    state=_read_state(task/'state.json')
    if not enabled(state):return
    grant=_GRANT.get()
    if not grant or grant.get('task')!=task:blocked(operation+' requires the current task writer grant')
    if grant.get('mode')=='packet':
        kind,target=grant.get('kind'),grant.get('target')
        if operation=='original observation' and (kind!='component_contract_source' or target!='source_features'):
            blocked('original observation requires the current source-feature packet')
        if operation=='bind' and not (kind=='component_contract_source' and target in ('component_contract','component_migration') or
                kind in ('component_user_mapping','component_repair_work') or kind=='component_local_work' and grant.get('operation')=='source_or_measurement_decision'):
            blocked('binding requires the current source-contract packet')
        if operation=='layout' and kind!='component_layout_work':blocked('layout requires the current layout packet')
        if operation=='review' and kind!='component_final_visual':blocked('whole review requires its current final-visual packet')
        if operation=='native construction' and kind not in ('component_build_work','component_local_work','component_repair_work',
                'component_font_review','component_user_mapping','font_binding','tool_font_embedding'):
            blocked('native construction is not allowed in this packet phase')


def packet_required(function):
    @wraps(function)
    def guarded(task,*args,**kwargs):
        require(task,function.__name__)
        return function(task,*args,**kwargs)
    return guarded


def finite_entry(function):
    @wraps(function)
    def guarded(task,*args,**kwargs):
        with finite_writer(task):return function(task,*args,**kwargs)
    return guarded


@contextmanager
def developer_writer(project):
    project=Path(project).resolve();token=_GRANT.set({'project':project,'mode':'developer_draft'})
    try:yield
    finally:_GRANT.reset(token)


def require_build(base,output):
    base,output=Path(base).resolve(),Path(output).resolve();grant=_GRANT.get()
    if grant and grant.get('mode')=='developer_draft':
        root=grant['project']/'.lotraAI-build/developer-drafts'
        if not output.is_relative_to(root):blocked('developer drafts must stay in private developer-drafts storage')
        return
    if not (base/'state.json').is_file():blocked('raw Scene build has no registered task')
    require(base,'native construction')
    if not output.is_relative_to(base):blocked('native construction must stay in its registered task')
    from .agent_runtime import _read_state
    state=_read_state(base/'state.json')
    if enabled(state) and (not state.get('component_workflow') or not state.get('source_feature_observation')):
        blocked('freeze the complete original and component contract before construction')


# Non-task historical writers are retained as implementation resources, not
# independent product workflows. Pure diagnostics remain callable.
RAW_WRITERS={'compile-task','finalize','install-output','apply-patch','patch-native-ppt-leaf',
    'group-saved-native-owner','promote-local-edit','reconcile-desktop-scene',
    'replace-picture-layers','instantiate-recipe','generate-illustrative-variant'}
TASK_COMMANDS={'next','submit','export','delivery-check','harness-check','source-reading',
    'source-ocr','source-word-anchors','source-material','source-material-grid','source-residuals',
    'source-formulas','source-fragments','source-fragment-plan','source-material-response',
    'source-occluded-band','source-layer-domain','source-repeat','source-detail','source-repeat',
    'context-control','context-usage','packet-template','review-batch','prioritize',
    'refresh-render','sync','authorize-edit','revisit','task-completion'}


@contextmanager
def command_scope(args):
    command=args.command;task=getattr(args,'task',None) or getattr(args,'workdir',None)
    if command in ('build','probe'):
        if not getattr(args,'developer_draft',False) or not getattr(args,'project',None):
            blocked('standalone '+command+' requires explicit --developer-draft --project PROJECT')
        output=Path(args.out).resolve()
        if command=='build' and output.name!='Draft_editable.pptx':
            blocked('developer build filename must be Draft_editable.pptx')
        with developer_writer(args.project):
            root=Path(args.project).resolve()/'.lotraAI-build/developer-drafts'
            if not output.is_relative_to(root):blocked('developer output must be private')
            yield
        return
    state=None
    if task and (Path(task)/'state.json').is_file():
        from .agent_runtime import _read_state
        state=_read_state(Path(task)/'state.json')
    if command in RAW_WRITERS and not state:
        blocked('historical standalone writer '+command+' is outside a registered workflow')
    if state and enabled(state):
        operation=getattr(args,'operation',None)
        if command=='component-workflow' and operation in ('status','export'):pass
        elif command=='workflow-control' and operation in ('plan','preflight','profile','advance'):pass
        elif command not in TASK_COMMANDS:blocked('direct '+command+' is not a current packet submission')
        if command=='task-completion' and operation not in ('status','resume','stop','begin'):
            blocked('task completion cannot lower the source contract')
    yield
