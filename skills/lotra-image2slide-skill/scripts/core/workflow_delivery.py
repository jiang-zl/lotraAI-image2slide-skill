"""Read-only, final-byte delivery checks for cooperating harnesses and users."""
from pathlib import Path
from .common import read_json,digest,identity,safe_path
from .workflow_guard import POLICY,enabled


def binding(task,state,candidate,acceptance):
    """Put the current task identity in the private existing delivery receipt."""
    if enabled(state):
        if not acceptance or acceptance.get('status')!='ACCEPTED':raise ValueError('Current acceptance required for official delivery binding')
    return {'schema':'workflow-delivery-1.37.0','task_id':state['task_id'],'task':str(Path(task).resolve()),
        'execution_policy':state.get('execution_policy'),'source':state['source'],
        'contract':state.get('component_workflow',{}).get('contract'),
        'candidate':candidate['pptx'],'final_result':acceptance.get('result') if acceptance else None,
        'acceptance_identity':identity(acceptance)}


def _resource(task,ref):
    if not isinstance(ref,dict) or not ref.get('path') or not ref.get('sha256'):raise ValueError('Missing hash-bound workflow resource')
    file=safe_path(task,ref['path'])
    if not file.is_file() or digest(file)!=ref['sha256']:raise ValueError('Workflow evidence changed: '+ref['path'])
    return file


def verify(task,directory=None,attachment=None):
    # Do not call next, refresh, accept or any writer: verification never creates
    # acceptance and can be used by a harness's separate final-attachment gate.
    from . import agent_runtime as a,component_workflow as c
    from .component_protocol import ready_for_final
    task=Path(task).resolve();state=a._read_state(task/'state.json')
    if not enabled(state):raise ValueError('This task is bound to an older execution policy; do not relabel its evidence')
    _resource(task,state['source'])
    progress=state.get('incremental_contract')
    if not progress:raise ValueError('Original/binding coverage checkpoint required')
    staged=read_json(_resource(task,progress))
    if not staged.get('source_sealed') or not staged.get('binding_sealed'):
        raise ValueError('Original/binding coverage has not been completely sealed')
    contract,ledger=c._load(task,state)
    if not contract or not ledger or not contract.get('components') or not ledger.get('components'):
        raise ValueError('Nonempty component contract and ledger required')
    _resource(task,contract.get('source_observation'))
    if staged.get('sealed_contract')!=state['component_workflow']['contract']:
        # Explicit revisions retain the original staged closure but must bind
        # their own current source/feature inventory through the same validators.
        if not state.get('component_workflow_history'):raise ValueError('Sealed contract identity differs')
    if not ready_for_final(contract,ledger,state)['ready'] or ledger.get('final_dirty'):
        raise ValueError('Current components/layout/final evidence are incomplete or dirty')
    candidate=c._candidate(state)
    if not candidate:raise ValueError('No current accepted native candidate')
    _resource(task,candidate['pptx']);_resource(task,candidate['scene']);_resource(task,candidate['preview'])
    acceptance=read_json(_resource(task,state.get('acceptance')))
    final=read_json(_resource(task,acceptance.get('result')))
    from .line_contracts import enabled as evidence_enabled,require_contract
    if evidence_enabled(state):
        require_contract(state,contract)
        required={'component_qualification','font_language_and_binding','ownership','native_resources',
                  'assembly_and_layout','source_placement','actual_render','source_feature_basis',
                  'source_feature_probes','final_visual','spatial_native','source_lines'}
        if set(final.get('gates',{}))!=required:
            raise ValueError('Final evidence-policy gate set is incomplete or changed')
        from .line_contracts import require_report
        require_report(state,candidate,contract,final['gates']['source_lines'])
    if (acceptance.get('status')!='ACCEPTED' or final.get('status')!='ACCEPTED' or
            final.get('source_hash')!=state['source']['sha256'] or final.get('contract')!=state['component_workflow']['contract'] or
            acceptance.get('source_hash')!=state['source']['sha256'] or acceptance.get('result')!=ledger.get('final_result') or
            acceptance.get('pptx_hash')!=candidate['pptx']['sha256'] or final.get('pptx_hash')!=candidate['pptx']['sha256'] or
            final.get('preview_hash')!=candidate['preview']['sha256'] or
            final.get('render_environment')!=state['capabilities']['fingerprint'] or
            acceptance.get('implementation')!=c.implementation() or final.get('implementation')!=c.implementation() or
            not final.get('gates') or final.get('failures') or
            not all(g.get('passed') is True for g in final['gates'].values())):
        raise ValueError('Final acceptance is stale, incomplete or belongs to different input bytes')
    c.actual_render(task,state,candidate,independent=True)
    receipt_file=_resource(task,state.get('official_delivery'));receipt=read_json(receipt_file)
    expected=binding(task,state,candidate,acceptance)
    if receipt.get('task_binding')!=expected or receipt.get('acceptance')!=acceptance or receipt.get('status')!='ACCEPTED':
        raise ValueError('Official delivery does not bind this task/current acceptance')
    output=Path(receipt['output']).resolve()
    if directory is not None and Path(directory).resolve()!=output:raise ValueError('Requested directory is not this registered official delivery')
    from .user_delivery import verify as verify_bytes
    integrity=verify_bytes(output,receipt_file)
    if attachment is not None:
        file=Path(attachment).resolve()
        if not file.is_file() or digest(file)!=receipt['files']['Final_editable.pptx']:
            raise ValueError('Attachment bytes differ from the verified final PPTX')
    return {'schema':'harness-finish-check-1.37.0','status':'ACCEPTED_DELIVERY_VERIFIED','allow_finish':True,
        'task_id':state['task_id'],'execution_policy':POLICY,'source_hash':state['source']['sha256'],
        'pptx':str(output/'Final_editable.pptx'),'pptx_sha256':receipt['files']['Final_editable.pptx'],
        'report':str(output/'Report.md'),'receipt_sha256':digest(receipt_file),'integrity':integrity,
        'scope':'Current complete workflow and exact final bytes; semantic judgments retain their explicit observer scope',
        'trust_boundary':'Local editable program/receipts are not cryptographic isolation from their host'}


def check(task,directory=None,attachment=None):
    try:return verify(task,directory,attachment)
    except (ValueError,KeyError,TypeError,FileNotFoundError,OSError) as error:
        return {'schema':'harness-finish-check-1.37.0','status':'WORKFLOW_NOT_DELIVERABLE','allow_finish':False,
            'reason':str(error),'next_action':'Resume the current next/submit packet, or report the retained external blocker',
            'candidate_delivery_authorized':False}
