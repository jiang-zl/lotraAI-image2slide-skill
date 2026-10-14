"""Set-complete recursive source/native checking and executable repair plans.

Every receipt is produced from current program results. A source READY status
is discovery only. No root review or reported count substitutes for children.
"""
import copy
from .common import identity,digest,read_json,write_json,safe_path,writer

VERSION='recursive-obligations-1'

def current_basis(task,state,candidate):
    from .execution_contract import _basis
    # The executor, source rules/readings, observations, and exact artifacts
    # must all remain current. Registering a plan does not change the drawing
    # or its check basis; including this registry would invalidate itself.
    checked=state.copy();checked.pop('recursive_repair_plans',None)
    return _basis(checked,candidate)

def _closed_graph(rows):
    keys={r['id'] for r in rows}
    if len(keys)!=len(rows):raise ValueError('Duplicate recursive obligation')
    for row in rows:
        if not set(row['dependencies'])<=keys:raise ValueError('Unregistered recursive dependency: '+row['id'])
    by_id={r['id']:r for r in rows}
    from collections import deque
    unresolved={k:len(set(v['dependencies'])) for k,v in by_id.items()};parents={k:[] for k in keys}
    for key,row in by_id.items():
        for dep in set(row['dependencies']):parents[dep].append(key)
    ready=deque(sorted(k for k,n in unresolved.items() if not n));order=[]
    while ready:
        key=ready.popleft();order.append(key)
        for parent in parents[key]:
            unresolved[parent]-=1
            if not unresolved[parent]:ready.append(parent)
    if len(order)!=len(keys):raise ValueError('Cyclic recursive dependency')
    return {k:by_id[k] for k in order}

def report(task,state,candidate,context):
    from .source_recursion import load,_objects
    from .execution_contract import inventory,_implementation
    tree=load(task,state);inv,scene,nodes=inventory(task,state,candidate)
    units=state.get('quality',{}).get('units',{});policies=state.get('quality_intent',{}).get('items',[])
    native={r['object']:r for r in context['native']};appearance={r['id']:r for r in context['appearance']}
    semantic={r['id']:r for r in context['host']};regions={r['id']:r for r in context['recursion']['items']}
    source={r['unit']:r for r in context['legacy']};feature_rows=context['features']['items'];connection=context['connections']
    basis=current_basis(task,state,candidate)
    rows=[];receipts={}
    def add(key,kind,subject,deps,checks):
        check_ids=[]
        for label,result in checks.items():
            rid=key+'/'+label;check_ids.append(rid)
            receipts[rid]={'id':rid,'obligation':key,'basis':basis,'result':copy.deepcopy(result)}
        rows.append({'id':key,'kind':kind,'subject':subject,'dependencies':sorted(set(deps)), 'required_checks':check_ids})
    def descendants(names):
        found=set(names)
        while True:
            added={n for n,p in inv['parents'].items() if p in found}-found
            if not added:break
            found|=added
        return found
    for name in inv['native_names']:
        children=['native:'+n for n,p in inv['parents'].items() if p==name]
        row=native.get(name)
        add('native:'+name,'saved_native',name,children,{'saved_and_actual':row or {'passed':False,'status':'MISSING_INDEPENDENT_NATIVE_CHECK'}})
    for uid,unit in units.items():
        bound=descendants(unit.get('objects',[]));covered=[p for p in policies if uid in p['quality_units']]
        required_names=set(unit.get('objects',[]));missing=sorted(required_names-set(inv['native_names']))
        # Explicit migrations cannot erase old source requirements. They bind
        # the entire new root and need an exact constructor proof elsewhere.
        migration=[p for p in covered if p.get('binding_migration')]
        if missing and migration:
            bound=descendants({n for p in migration for n in p['objects']});missing=[]
        actual=source.get(uid)
        source_check={'passed':bool(actual) and actual.get('status')!='required_unmeasured' and not any(c.get('status')=='required_unmeasured' for c in actual.get('constraints',[])),
                      'result':actual,'scope':'All original numeric predicates measured; active purpose requirements independently checked'}
        geometry_deps=['geometry:'+r['id'] for r in feature_rows if r['unit']==uid]
        if uid in state.get('source_detail_contracts',{}).get('units',{}):geometry_deps.append('detail:'+uid)
        add('unit:'+uid,'semantic_part',uid,['native:'+n for n in bound if n in nodes]+geometry_deps,{
            'binding':{'passed':bool(bound) and not missing,'missing':missing},'source_measurement':source_check,
            'purpose_checks':{'passed':bool(covered) and all(appearance.get(p['id'],{}).get('passed') is True for p in covered),'policies':[p['id'] for p in covered]}})
        for f in unit.get('features',[]):
            check={'passed':bool(covered) and all(semantic.get(p['id'],{}).get('passed') is True for p in covered),
                   'original_feature':f,'actual_observations':[semantic.get(p['id']) for p in covered],
                   'scope':'Independent part observation with individual native/purpose checks; semantic meaning remains host evidence'}
            add('property:'+uid+':'+f['id'],'original_property',f['id'],['unit:'+uid],{'source_and_actual':check})
    if tree:
        for key,node in tree['nodes'].items():
            deps=['region:'+child for child in node['children']]
            bound=descendants(_objects(state,node));deps+=['native:'+n for n in bound if n in nodes]
            for f in node['critical_features']:
                fid='region-feature:'+key+':'+f['id'];owners=descendants(_objects(state,node,f))
                applicable=[uid for uid,u in units.items() if descendants(u.get('objects',[]))&owners]
                deps.append(fid)
                raw=next((r for r in regions.get(key,{}).get('critical_features',[]) if r['id']==f['id']),{})
                add(fid,'source_region_feature',f['id'],['unit:'+u for u in applicable]+['native:'+n for n in owners if n in nodes],{
                    'source_result':raw or {'passed':False,'status':'MISSING_SOURCE_FEATURE_RESULT'},
                    'independent_output':{'passed':bool(applicable) or f['role']=='relationship','units':applicable}})
            add('region:'+key,'source_region',key,deps,{'discovery_and_content':regions.get(key) or {'passed':False,'status':'UNINSPECTED_SOURCE_REGION'}})
    else:add('region:missing','source_region','missing',[],{'tree':{'passed':False,'status':'ORIGINAL_TREE_REQUIRED'}})
    for r in feature_rows:add('geometry:'+r['id'],'source_geometry',r['id'],['native:'+p['object'] for p in r['parts'] if p['object'] in nodes],{'actual_feature_geometry':r})
    neighbors=context.get('neighbors',{})
    for pair in neighbors.get('items',[]):
        names={n for p in pair['results'] if p['id'].endswith(':identity') for ns in p['actual'].values() for n in ns}
        deps=['native:'+n for n in names if n in nodes]
        for predicate in pair['results']:
            add('neighbor:'+predicate['id'],'neighbor_predicate',pair['objects'],deps,{'actual_numeric_predicate':predicate})
    add('neighbor:independent-coverage','neighbor_coverage','whole original and actual role set',[],{'independent_all_pair_audit':neighbors or {'passed':False,'status':'ALL_NEIGHBOR_CHECK_REQUIRED'}})
    for paper in context.get('coherent_paper',{}).get('items',[]):
        add('coherent-paper:'+paper['unit'],'coherent_paper',paper.get('root'),['native:'+paper['root']+'__'+r for r in paper.get('native_roles',{})],{'actual_saved_geometry':paper})
    for primitive in connection.get('primitives',[]):
        add('connection-primitive:'+primitive['id'],'original_connection_primitive',primitive['id'],['native:'+primitive['object']],{'original_and_actual':primitive})
    for terminal in connection.get('terminals',[]):
        add('terminal:'+terminal['id'],'connection_terminal',terminal['id'],['native:'+terminal['object']],{'actual_terminal':terminal})
    for decision in connection.get('candidate_decisions',[]):
        add('connection-decision:'+decision['candidate'],'original_connection_decision',decision['candidate'],[],{'source_decision':{'passed':True,'result':decision,'basis':connection.get('source_integrity')}})
    for r in connection.get('items',[]):
        deps=['native:'+n for n in r.get('objects',[]) if n in nodes]
        deps+=['terminal:'+t['id'] for t in connection.get('terminals',[]) if t['connection']==r['id']]
        deps+=['connection-primitive:'+p['id'] for p in connection.get('primitives',[]) if p['connection']==r['id']]
        add('connection:'+r['id'],'connection',r['id'],deps,{'actual_connection':r})
    add('connection:original-survey','original_connection_survey','all original recursive regions',[],{'source_integrity':connection.get('source_integrity',{'passed':False})})
    if not connection['passed']:add('connection:coverage','connection','complete connector set',[],{'coverage':connection})
    for primitive in connection.get('primitives',[]):
        parent=next((r for r in rows if r['id']=='region:'+primitive['region']),None)
        if parent:parent['dependencies']=sorted(set(parent['dependencies'])|{'connection:'+primitive['connection']})
    if context.get('details'):
        details=context['details']
        for detail in details['source_facts']['items']:
            names={n for p in detail['observed_parts'] for n in p['objects']}
            add('detail:'+detail['id'],'original_detail',detail['id'],['native:'+n for n in names if n in nodes],{'every_source_detail_check':detail})
        add('detail:whole-source-triage','original_detail_context','every original unit',[],{'current_source_context':details['triage']})
        for row in rows:
            if row['kind']=='source_region' and not tree['nodes'].get(row['subject'],{}).get('parent'):
                row['dependencies']=sorted(set(row['dependencies'])|{'detail:whole-source-triage'})
    for kind in ('containment','office_math','clarity'):
        measured=context.get(kind,{})
        for item in measured.get('items',[]):
            key=kind+':'+item['id']
            checks={'current':item}
            if kind=='containment':checks.update(item.get('axes',{}))
            deps=[]
            if kind=='containment':
                deps=['containment:'+m for m in item.get('direct_members',[]) if m in measured.get('containment_tree',{})]
            elif kind=='office_math':
                deps=['native:'+item['object']] if item.get('object') in nodes else []
            elif kind=='clarity':
                deps=['native:'+n for n in item.get('hd',{}).get('native_parts',[]) if n in nodes]
                checks.update({'hd:'+r['id']:r for r in item.get('hd',{}).get('relations',[])})
                checks.update({'hd-scale:'+str(r['scale']):r for r in item.get('hd',{}).get('scales',[])})
                checks.update({'hd-paired-edge:'+r['id']:r for r in item.get('hd',{}).get('paired_clarity',{}).get('probes',[])})
                checks.update({'hd-material:'+r['id']:r for r in item.get('hd',{}).get('materials',[])})
                checks.update({'preserved-comparator:'+str(i):r for i,r in enumerate(item.get('preservation',{}).get('comparisons',[]))})
                checks.update({'preserved-material:'+r['id']:r for r in item.get('preservation',{}).get('materials',[])})
                checks.update({'preserved-style:'+r['id']:r for r in item.get('preservation',{}).get('review',{}).get('checks',[])})
            add(key,kind,item['id'],deps,checks)
        add(kind+':coverage',kind+'_coverage','complete original and actual set',[kind+':'+r['id'] for r in measured.get('items',[])],{'complete':measured or {'passed':False,'status':'required_unmeasured'}})
    graph=_closed_graph(rows)
    # Equality, not counts: every expected check needs one current receipt.
    expected={c for r in rows for c in r['required_checks']};actual=set(receipts)
    errors=[]
    if expected!=actual:errors.append({'missing':sorted(expected-actual),'unexpected':sorted(actual-expected)})
    memo={}
    for key in graph:
        r=graph[key];bad=[c for c in r['required_checks'] if c not in receipts or receipts[c]['basis']!=basis or receipts[c]['result'].get('passed') is not True]
        failed_deps=[d for d in r['dependencies'] if not memo[d]]
        r.update(passed=not bad and not failed_deps,failed_checks=bad,failed_dependencies=failed_deps)
        memo[key]=r['passed']
    result={'schema':VERSION,'passed':not errors and bool(rows) and all(r['passed'] for r in rows),'basis':basis,
            'source_hash':state['source']['sha256'],'pptx_hash':candidate['pptx']['sha256'],'items':rows,'checks':receipts,'set_errors':errors,
            'unclosed':[r['id'] for r in rows if not r['passed']],
            'scope':'Union of every discovered original region/property/part and every actually saved native layer, with bottom-up result closure'}
    path=task/'audits/recursive-obligations'/(identity(result)+'.json');write_json(path,result)
    previous=state.get('recursive_obligations_result')
    ref={'path':path.relative_to(task).as_posix(),'sha256':digest(path)}
    if previous and previous!=ref:state.setdefault('recursive_obligations_history',[]).append(previous)
    state['recursive_obligations_result']=ref
    return result

OPERATORS={'source_structure':'source_structure_actions','source_text':'source_text_actions','source_layout':'source_layout_actions','connector_geometry':'connection_geometry','neighbor_pose':'neighbor_actions',
           'recursive_center':'recursive_containment','structured_math':'office_math_contract'}

def bind_plan(task,request):
    from . import agent_runtime as a
    task,state=a._state(task);current=state.get('active_candidate') or state['selected'];ref=state.get('recursive_obligations_result')
    if not ref or request.get('check_report')!=ref:raise ValueError('Repair plan must bind the current complete recursion report')
    if digest(safe_path(task,ref['path']))!=ref['sha256']:raise ValueError('Recursive check report changed')
    check=read_json(safe_path(task,ref['path']))
    if check['pptx_hash']!=current['pptx']['sha256'] or check['basis']!=current_basis(task,state,current) or request.get('source_hash')!=state['source']['sha256']:
        raise ValueError('Repair planning basis is stale')
    items=request.get('actions',[]);known={r['id'] for r in check['items']};keys=[r.get('id') for r in items]
    if not items or len(items)>16 or len(set(keys))!=len(keys):raise ValueError('Unique bounded executable actions required')
    for row in items:
        if row.get('operator') not in OPERATORS or not row.get('targets') or not set(row['targets'])<=known or not row.get('reason') or not row.get('expected_change') or not isinstance(row.get('request'),dict):
            raise ValueError('Plan action requires registered targets, finite operator, reason and measurable expected change')
        if not row.get('protected_scope'):raise ValueError('Explicit protection scope required')
        if row['request'].get('expected_baseline_sha256') not in (None,current['pptx']['sha256']):raise ValueError('Action baseline mismatch')
    plan={'schema':'recursive-repair-plan-1','source_hash':state['source']['sha256'],'baseline':current['pptx'],
          'check_report':ref,'actions':copy.deepcopy(items),'status':'PLANNED'}
    path=task/'plans/recursive-repair'/(identity(plan)+'.json');write_json(path,plan)
    with writer(task):
        targets={t for r in items for t in r['targets']}
        for ref in request.get('supersedes',[]):
            old=next((p for p in state.get('recursive_repair_plans',[]) if p['plan']==ref),None)
            if not old or old.get('superseded_by'):raise ValueError('Unknown or already superseded plan')
            prior=read_json(safe_path(task,ref['path']))
            if not {t for r in prior['actions'] for t in r['targets']}<=targets:raise ValueError('Supersession cannot discard planned target obligations')
            old['superseded_by']=a._file(task,path);old['supersession_reason']=request.get('supersession_reason')
            if not old['supersession_reason']:raise ValueError('Explicit supersession reason required')
        state.setdefault('recursive_repair_plans',[]).append({'plan':a._file(task,path),'executions':[]});a._save(task,state)
    return {'status':'EXECUTABLE_PLAN_COMPILED','plan':a._file(task,path)}

def execute_plan(task,request):
    from . import agent_runtime as a
    import importlib
    task,state=a._state(task);entry=next((p for p in state.get('recursive_repair_plans',[]) if p['plan']==request.get('plan')),None)
    if not entry:raise ValueError('Only a registered immutable program-compiled plan may execute')
    file=safe_path(task,entry['plan']['path'])
    if digest(file)!=entry['plan']['sha256']:raise ValueError('Repair plan changed')
    plan=read_json(file);row=next((r for r in plan['actions'] if r['id']==request.get('action')),None)
    if not row or entry.get('superseded_by') or any(e['action']==row['id'] and e['status']=='EXECUTED_REQUIRES_CURRENT_WHOLE_CHECK' for e in entry['executions']):raise ValueError('Action missing, superseded or already executed')
    current=state.get('active_candidate') or state['selected']
    if current['pptx']!=plan['baseline']:raise ValueError('Replan remaining actions against changed current artifact')
    checked=safe_path(task,plan['check_report']['path'])
    if digest(checked)!=plan['check_report']['sha256'] or read_json(checked)['basis']!=current_basis(task,state,current):
        raise ValueError('Source rules, checked artifact or executor changed; recheck and replan before execution')
    payload=copy.deepcopy(row['request']);payload['expected_baseline_sha256']=current['pptx']['sha256'];payload['source_hash']=state['source']['sha256']
    if sum(e['action']==row['id'] and e['status']=='EXECUTION_FAILED' for e in entry['executions'])>=2:raise ValueError('Failed branch exhausted; analyze and replan without removing targets')
    try:
        module=importlib.import_module('.'+OPERATORS[row['operator']],__package__)
        if row['operator'] in ('recursive_center','structured_math'):
            payload['baseline_hash']=current['pptx']['sha256'];result=module.dispatch(task,'repair',payload)
        else:result=module.execute(task,payload)
    except Exception as error:
        task,state=a._state(task);entry=next(p for p in state['recursive_repair_plans'] if p['plan']==request['plan'])
        with writer(task):
            entry['executions'].append({'action':row['id'],'baseline':current['pptx'],'status':'EXECUTION_FAILED','reason':str(error)});a._save(task,state)
        raise
    task,state=a._state(task);entry=next(p for p in state['recursive_repair_plans'] if p['plan']==request['plan'])
    with writer(task):
        entry['executions'].append({'action':row['id'],'baseline':current['pptx'],'result':result,'status':'EXECUTED_REQUIRES_CURRENT_WHOLE_CHECK'})
        state.pop('acceptance',None);state.pop('quality_result',None);a._save(task,state)
    return result

def process_report(task,state,candidate,closure):
    rows=[]
    for entry in state.get('recursive_repair_plans',[]):
        file=safe_path(task,entry['plan']['path'])
        if digest(file)!=entry['plan']['sha256']:raise ValueError('Immutable repair plan changed')
        plan=read_json(file);done={e['action']:e for e in entry['executions']}
        if entry.get('superseded_by'):
            rows.append({'plan':entry['plan'],'passed':True,'status':'SUPERSEDED_WITH_ALL_TARGETS_RETAINED','superseded_by':entry['superseded_by'],
                         'reason':entry['supersession_reason'],'executions':entry['executions']})
            continue
        for action in plan['actions']:
            e=done.get(action['id']);actual={r['id']:r for r in closure['items']}
            target_results=[actual.get(t) for t in action['targets']]
            passed=bool(e) and e['status']=='EXECUTED_REQUIRES_CURRENT_WHOLE_CHECK' and all(r and r['passed'] for r in target_results)
            rows.append({'plan':entry['plan'],'action':action['id'],'passed':passed,'executed':bool(e),
                         'expected_change':action['expected_change'],'targets':action['targets'],'current_target_closure':target_results})
    actual={r['id']:r for r in closure['items']}
    from .neighbor_contracts import PREDICATES
    from .neighbor_actions import guard as neighbor_guard
    for entry in state.get('neighbor_repair_attempts',[]):
        if entry['candidate']!=candidate['pptx']['sha256']:continue
        proof=neighbor_guard(task,state,candidate,entry['baseline'],_chain_only=True)
        targets=['neighbor:'+rid+':'+predicate for rid in entry['proposal']['check_set'] for predicate in PREDICATES]
        failed=[target for target in targets if target not in actual or not actual[target]['passed']]
        passed=proof.get('passed') is True and not failed and bool(candidate.get('render'))
        rows.append({'plan':entry['contract'],'action':'finite_original_neighbor_pose','passed':passed,'executed':proof.get('passed') is True,
                     'write_set':entry['proposal']['write_set'],'expected_check_set':entry['proposal']['check_set'],
                     'missing_or_failed_targets':failed,'status':'CURRENT_EXECUTION_AND_ALL_INCIDENT_PREDICATES_CLOSED' if passed else 'CURRENT_EXECUTION_RECHECK_REQUIRED'})
    for entry in state.get('source_target_attempts',[]):
        if entry['candidate']!=candidate['pptx']['sha256']:continue
        from .target_actions import guard
        proof=guard(task,state,candidate,entry['baseline'],_chain_only=True)
        contract=read_json(safe_path(task,entry['contract']['path']));plan=contract['plan']
        prefix='containment:' if plan['kind']=='recursive-containment-1' else 'office_math:math-owner:'
        targets=[prefix+v for v in plan['check_set']]
        missing=[v for v in targets if v not in actual or not actual[v]['passed']]
        rows.append({'plan':entry['contract'],'action':plan['kind'],'write_set':entry['write_set'],
            'executed':proof.get('passed') is True,'passed':proof.get('passed') is True and bool(candidate.get('render')) and not missing,
            'missing_or_failed_targets':missing,'status':'CURRENT_EXECUTION_AND_RECURSIVE_TARGETS_CLOSED' if not missing and proof.get('passed') is True else 'CURRENT_EXECUTION_RECHECK_REQUIRED'})
    return {'passed':all(r['passed'] for r in rows),'items':rows,'scope':'Every registered action executed and its targets independently closed on the current saved result'}
