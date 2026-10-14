"""Immutable human-review copies with explicit pending status, never acceptance.

This endpoint exposes an actual complete working drawing and its full audit.
It does not select, accept, install an output, waive debt or call helper finalise.
"""
import shutil
from pathlib import Path
from . import agent_runtime as a,execution_contract as ec
from .common import read_json,write_json,digest,identity,writer,safe_path


def _review_details(audit_result,audit):
    """Read real schema-specific diagnostics before creating any output."""
    schema=audit.get('schema')
    key={'whole-working-audit-1':'numeric_summary','whole-quality-loop-1':'legacy_summary'}.get(schema)
    summary=audit.get(key) if key else None
    if (not isinstance(summary,dict) or any(not isinstance(k,str) or type(v) is not int or v<0
            for k,v in summary.items())):
        raise ValueError('Review audit requires a supported schema and actual measurement counts')
    failures=audit.get('failures')
    if schema=='whole-quality-loop-1' and (not isinstance(failures,list) or
            any(not isinstance(r,dict) or not isinstance(r.get('goal'),str) for r in failures)):
        raise ValueError('Review audit requires actual whole-result failure evidence')
    return {'numeric_summary':summary,'audit_schema':schema,'audit_status':audit.get('status'),
        'final_gate_status':audit_result.get('final_gate','NOT_EXECUTED_BY_REVIEW_EXPORT'),
        'observations':audit.get('observations'),'content_summary':audit.get('content_summary'),
        'failed_goals':[r['goal'] for r in failures] if failures is not None else None}


def export_review(task,output):
    from .working_audit import audit_task
    audit_result=audit_task(task)
    task,state=a._state(task);candidate=state.get('active_candidate') or state.get('selected')
    output=Path(output).resolve()
    if output.exists():raise FileExistsError('A review bundle must use a new directory')
    refs={k:candidate[k] for k in ('pptx','scene','preview','render')}
    original=digest(ec.resource(task,state['source']));native=digest(ec.resource(task,refs['pptx']))
    receipt=read_json(ec.resource(task,refs['render']))
    audit=read_json(ec.resource(task,audit_result['report']))
    details=_review_details(audit_result,audit)
    if (audit['pptx_hash']!=native or audit['source_hash']!=original or
            audit['implementation']!=ec._implementation() or
            receipt.get('pptx_hash')!=native or receipt.get('preview_hash')!=refs['preview']['sha256']):
        raise ValueError('Review requires current exact drawing, original, executor and actual render')
    inventory,_,_=ec.inventory(task,state,candidate)
    coverage=ec.report(task,state,candidate)
    from .frame_plan import guard as frame_guard
    from .semantic_composition import report as composition_report
    frames=frame_guard(task,state,candidate)
    composition=composition_report(task,state,candidate)
    pdf=None
    if receipt.get('pdf',{}).get('status')=='EXPORTED':
        render=ec.resource(task,refs['render'])
        pdf=safe_path(render.parent,receipt['pdf']['path'])
        if digest(pdf)!=receipt.get('pdf_hash'):raise ValueError('Actual review PDF is missing or changed')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.mkdir(exist_ok=False)
    with writer(output):
        from . import VERSION
        shutil.copyfile(ec.resource(task,refs['pptx']),output/('Working-v'+VERSION+'.pptx'))
        shutil.copyfile(ec.resource(task,refs['preview']),output/'Preview.png')
        if pdf:shutil.copyfile(pdf,output/'Preview.pdf')
        evidence=output/'Evidence';evidence.mkdir()
        for key,value in [('Whole-audit',audit),('Execution-coverage',coverage),
            ('Frame-plan-check',frames),('Semantic-composition',composition),('Native-inventory',inventory)]:
            write_json(evidence/(key+'.json'),value)
        shutil.copyfile(ec.resource(task,refs['render']),evidence/'Actual-render.json')
        write_json(evidence/'Original-artifact-bindings.json',{'source':state['source'],
            'source_size':state['source_size'],'candidate':refs,'runtime_task':str(task),
            'implementation':ec._implementation(),'status':'ACTUAL_WORKING_ARTIFACTS_ONLY'})
        blocked=audit.get('final_gate_receipt')
        if blocked:shutil.copyfile(ec.resource(task,blocked),evidence/'Final-gate.json')
        component_index={'schema':'working-native-reuse-index-1','pptx_hash':native,
            'status':'NATIVE_GROUPS_AVAILABLE_QUALITY_PENDING','components':[
                {'root':name,'native_leaves':leaves,'source_reading':state.get('rule_coverage',{}).get('roots',{}).get(name),
                 'reuse':'Select/copy the exact named native group from the full working PPT; preserve ancestor transforms.',
                 'cross_file_office_roundtrip':'NOT_RUN'} for name,leaves in inventory['groups'].items()],
            'limits':'Independent current owner mattes are measurement evidence, not a cross-file editing or font portability certificate.'}
        write_json(output/'Components-index.json',component_index)
        status={'schema':'working-human-review-1','status':'WORKING_NOT_ACCEPTED','formal_acceptance':False,
            'source_hash':original,'pptx_hash':native,'preview_hash':refs['preview']['sha256'],
            'render_backend':receipt.get('backend'),'native_count':len(inventory['native_names']),
            **details,
            'pending_coverage':[r['id'] for r in coverage['items'] if not r['passed']],
            'limits':'Complete actual working result for review. Failed/unmeasured source, semantic, text/math/font requirements remain in the same runtime task; this bundle cannot bypass formal export.'}
        write_json(output/'Review-status.json',status)
        manifest={'schema':'working-review-manifest-1','status':'WORKING_NOT_ACCEPTED',
            'source_hash':original,'pptx_hash':native,'implementation':ec._implementation(),
            'files':{p.relative_to(output).as_posix():{'sha256':digest(p),'size':p.stat().st_size}
                for p in sorted(output.rglob('*')) if p.is_file() and p.name!='.writer.lock'}}
        write_json(output/'Manifest.json',manifest)
    if digest(ec.resource(task,candidate['pptx']))!=native or digest(ec.resource(task,state['source']))!=original:
        raise ValueError('Review copying unexpectedly changed source/drawing bytes')
    return {'status':'WORKING_NOT_ACCEPTED','output':str(output),'manifest_hash':digest(output/'Manifest.json'),
        'pptx_hash':native,'native_count':len(inventory['native_names']),'numeric_summary':details['numeric_summary']}
