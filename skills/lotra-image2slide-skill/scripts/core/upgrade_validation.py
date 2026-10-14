"""Upgrade receipt verifier; artwork acceptance remains quality_loop only."""
from pathlib import Path
from .common import digest,identity,read_json,write_json

CRITERIA=['production_current','required_behavior_regressions','verified_publication']

def verify_behaviors(entries,output):
    """Replay actual Office evidence against predeclared positive/negative checks."""
    from .native_task import verify as verify_native
    if not entries:raise ValueError('Freeze actual Office positive and negative behavior probes in upgrade scope')
    result=[];math_seen=False;connector_seen=False
    for entry in entries:
        plan=Path(entry['plan']).resolve()
        if digest(plan)!=entry['plan_sha256']:raise ValueError('Frozen actual behavior plan changed')
        checked=verify_native(plan,Path(entry['office_directory']).resolve(),Path(output)/('actual-behavior-'+identity(entry)+'.json'))
        if checked.get('actual_host_job_verified') is not True or checked.get('current_implementation_verified') is not True:
            raise ValueError('Actual Office behavior has no current implementation-bound verified host job')
        actual=[(r['object_id'],r['action'],r['status']) for r in checked['checks']]
        expected=[(r['object_id'],r['action'],r['status']) for r in entry['expected_checks']]
        if not expected or actual!=expected:
            raise ValueError('Actual behavior differs from the frozen complete positive/negative expectations')
        for row in entry['expected_checks']:
            if row['status'] not in ('PASS','FAIL'):raise ValueError('Behavior expectations must be explicit passing or rejected negative cases')
            math_seen=math_seen or row['action']=='math'
            connector_seen=connector_seen or row['action'] in ('connector','all_affected_endpoints')
        result.append({'status':'EXPECTED_BEHAVIOR_VERIFIED','plan_sha256':digest(plan),'checks':checked['checks'],
            'actual_native_status':checked['status'],'scope':'A correctly rejected negative fixture is not a passing reconstructed connector'})
    if not math_seen or not connector_seen:raise ValueError('Upgrade requires actual equation and connector behavior coverage')
    return result

def verify(task,state,request):
    from .execution_contract import _implementation,resource
    from . import VERSION,agent_runtime as a
    import package_skill as package
    flow=state['task_completion']
    if flow['kind']!='skill_upgrade' or flow['criteria']!=CRITERIA:
        raise ValueError('Freeze upgrade production, regression and publication criteria before execution')
    # Rerun bundled executable assertions; supplied PASS fields are not used.
    import regression_contracts as regressions
    tested=regressions.run(Path(task)/'audits/upgrade-regression')
    if tested['status']!='PASS':raise ValueError('Current executable upgrade regressions failed')
    behavior=verify_behaviors(flow['scope'].get('behavior_probes',[]),Path(task)/'audits')
    cases=[]
    for entry in flow['scope'].get('case_tasks',[]):
        t,s=a._state(Path(entry['path']));c=s.get('active_candidate') or s['selected']
        if s['source']['sha256']!=entry['source_hash']:raise ValueError('Changed upgrade original case')
        from .recursive_containment import report as containment_report
        from .office_math_contract import report as math_report
        from .source_layout_actions import guard
        container=containment_report(t,s,c);math=math_report(t,s,c)
        baseline=entry['baseline'];protection=guard(t,s,c,baseline)
        render=read_json(resource(t,c['render']))
        if (not container['passed'] or not math['passed'] or not protection['passed'] or
            render.get('pptx_hash')!=c['pptx']['sha256'] or render.get('preview_hash')!=digest(resource(t,c['preview']))):
            raise ValueError('Upgrade case needs current real math, recursive centering, protection and actual render')
        cases.append({'source_hash':s['source']['sha256'],'pptx':c['pptx'],'containment':container,'math':math,'protection':protection,
            'whole_artwork_status':'Separate current quality_loop result; feature validation never accepts artwork'})
    if not cases:raise ValueError('Actual source-bound case behavior is required for this upgrade')
    archive=resource(task,request['package']);payload,_,manifest=package.verify_archive(archive)
    if manifest['version']!=VERSION or payload!=package.collect_source(package.SOURCE):raise ValueError('Package is not the current verified production implementation')
    publication=read_json(resource(task,request['publication']))
    root=Path(publication['root']).resolve()
    if publication.get('version')!=VERSION or not publication.get('files'):raise ValueError('Current published file inventory required')
    from .common import safe_path
    for name,row in publication['files'].items():
        if digest(safe_path(root,name))!=row['sha256']:raise ValueError('Published file changed: '+name)
    result={'schema':'upgrade-validation-1','status':'VERIFIED_UPGRADE','version':VERSION,'implementation':_implementation(),
        'criteria':CRITERIA,'regressions':tested,'actual_behavior':behavior,'cases':cases,'package':request['package'],'publication':request['publication'],
        'target_basis':__import__(__package__+'.task_completion',fromlist=['target_basis']).target_basis(state),
        'scope':'Production and upgrade behavior only; never a replacement for full artwork acceptance'}
    file=Path(task)/'audits'/('upgrade-validation-'+identity(result)+'.json');write_json(file,result)
    state['upgrade_validation']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    return result
