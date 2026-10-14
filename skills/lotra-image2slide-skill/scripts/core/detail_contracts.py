"""Executable original-detail facts and source-root closure, independent of approval."""
import copy,math
from .common import identity,read_json,write_json,safe_path,digest
TYPES={'native_frame','source_function_frame','native_type','join','contains','layer','source_patch','parts_present'}

def amend_compiled_layers(task,state,observations):
    """Compile located fine-source corrections through the existing ledger."""
    from . import semantic_composition as sc
    from .quality_intent import source_view
    if not sc.enabled(state):return
    active=sc.contracts(task,state);rows=[]
    for observation in observations:
        for c in observation['checks']:
            if c['type']!='layer':continue
            earlier=next((r for r in active if r['kind']=='order' and r['objects']==[c['b'],c['a']]),None)
            if not earlier:continue
            # Preserve old bytes and inferred intent as history. Only the
            # same located pair is superseded; no unrelated permission grows.
            row=copy.deepcopy(earlier)
            row.update(id='source-detail-order-'+identity([observation['id'],c])[:24],objects=[c['a'],c['b']],
                       source_view=source_view(task,state,observation['original_roi'],1),
                       source_evidence=c['source_evidence'],interpretation_reliability='observed_original_detail',
                       replaces=earlier['id'],source_correction={'kind':'original_interpretation',
                         'reason':observation['diagnosis'],'evidence':{'original_view':observation['original_view'],'detail_check':c}})
            rows.append(row)
    if rows:
        replacements={r['replaces']:r for r in rows};decisions=[]
        for previous in state.get('semantic_composition',{}).get('decisions',{}).values():
            changed=set(previous.get('contracts',[]))&set(replacements)
            if not changed:continue
            decision=copy.deepcopy(previous)
            decision['contracts']=[replacements[c]['id'] if c in replacements else c for c in decision['contracts']]
            row=replacements[next(iter(changed))]
            if decision['decision']=='ordered':decision['roles']={'first':row['objects'][0],'second':row['objects'][1]}
            decision.update(source_view=row['source_view'],evidence=row['source_evidence'])
            decisions.append(decision)
        sc._bind(task,state,{'contracts':rows,'decisions':decisions,'ownership':[]})

def validate_checks(checks,size):
    from .source_contract import finite
    from .adaptive_detail import _box
    finite(checks,'source_detail.checks')
    if not checks or len({c.get('id') for c in checks})!=len(checks):raise ValueError('Distinct executable detail checks required')
    for c in checks:
        if c.get('type') not in TYPES or not c.get('id') or not c.get('source_evidence'):raise ValueError('Typed source-evidenced detail check required')
        if c['type']=='native_frame':
            _box(c['expected_frame'],size)
            if not 0<=c.get('tolerance_source_px',1.5)<=3:raise ValueError('Bounded original frame uncertainty required')
        elif c['type']=='source_function_frame':
            if not all(isinstance(c.get(k),str) and c[k] for k in ('unit','object','function_hash')):
                raise ValueError('Source function frame needs an exact independently frozen unit, part and function identity')
        elif c['type']=='join':
            if c.get('axis') not in ('x','y') or c.get('a_anchor') not in ('min','center','max') or c.get('b_anchor') not in ('min','center','max'):raise ValueError('Explicit source join anchors required')
            if not 0<=c.get('tolerance_source_px',1.5)<=3:raise ValueError('Bounded join interval required')
        elif c['type']=='source_patch':
            _box(c['roi'],size)
            if c.get('metric') not in ('edge_f1','ssim','mean_absolute_rgb_error'):raise ValueError('Implemented local source metric required')
            if not 0<=c.get('min',0)<=1 or not 0<=c.get('max',1)<=1:raise ValueError('Bounded local metric required')
        elif c['type']=='native_type':
            if c.get('tag') not in ('sp','grpSp','cxnSp','graphicFrame','pic'):raise ValueError('Actual native type required')
        elif c['type']=='contains':
            if not 0<=c.get('tolerance_source_px',.5)<=1.5:raise ValueError('Bounded source containment required')

def merge_facts(task,state,observations):
    from . import source_recursion as sr
    tree=copy.deepcopy(sr.load(task,state));ledger=copy.deepcopy(state.get('source_detail_contracts',{'schema':'source-detail-contracts-1','units':{},'history':[]}))
    for row in observations:
        uid=row['id'];old=ledger['units'].get(uid)
        contract={'source_hash':state['source']['sha256'],'original_view':row['original_view'],'original_roi':row['original_roi'],
                  'observed_parts':row['observed_parts'],'relations':row.get('relations',[]),'checks':row['checks'],
                  'diagnosis':row['diagnosis'],'resolution':row['resolution'],'trigger_context':row['trigger_context'],
                  'source_observability':row['source_observability']}
        if old and old!=contract:ledger['history'].append({'unit':uid,'contract':old})
        ledger['units'][uid]=contract
        if not tree:continue
        parent=tree['nodes'].get('unit:'+uid)
        if not parent:raise ValueError('Detail finding has no independent source region')
        parent.setdefault('detail_revision_history',[]).append({'prior_status':parent['status'],'prior_features':copy.deepcopy(parent['critical_features'])})
        retained=[f for f in parent['critical_features'] if not f.get('source_detail')]
        for p in row['observed_parts']:
            feature={'id':'detail:'+p['id'],'roi':p['roi'],'role':'shape','objects':p['objects'],
                     'source_detail':True,'observed':p['observed'],'detail_contract_unit':uid}
            retained.append(feature)
        parent['critical_features']=retained
        from .adaptive_detail import source_units,profile
        parent_unit=source_units(state)[uid]
        for p in row['observed_parts']:
            if p['roi'][2]*p['roi'][3]>=parent_unit['roi'][2]*parent_unit['roi'][3]*.95:continue
            child_uid=uid+'::detail:'+p['id'];key='unit:'+child_uid
            unit={'id':child_uid,'roi':p['roi'],'profile':parent_unit['profile'],'refinement_profile':profile(state,parent_unit),
                  'owner':parent_unit['owner'],'part':p['id'],'objects':p['objects'],'parent_source_unit':uid,
                  'features':[{'id':p['id'],'expected':p['observed'],'category':'content','status':'observed'}]}
            old_unit=state.setdefault('source_detail_units',{}).get(child_uid)
            if old_unit and old_unit!=unit:raise ValueError('Source detail child cannot be silently redefined; create an evidenced revision')
            state['source_detail_units'][child_uid]=unit
            if key not in tree['nodes']:
                tree['nodes'][key]=sr._node(key,parent['id'],p['roi'],parent_unit['owner'],'drawing',
                    source_parts=[parent_unit.get('part')],semantic_class='structured',
                    source_detail_parent=uid,source_detail_part=p['id'],
                    leaf_type='verified_assembly',representation={'kind':'native','objects':p['objects'],'source_parts':[parent_unit.get('part')],
                        'edit_scope':['select','move','replace'],'structure_explanation':p['observed']},
                    observed_content=[p['observed']],critical_features=[{'id':'original_detail','roi':p['roi'],'role':'shape','objects':p['objects']}],
                    status='SOURCE_LEAF_READY',attempts=[{'action':'source_detail_child','view':row['original_view'],'reason':p['observed'],'submission_hash':identity(p)}])
                parent['children'].append(key)
            tree['nodes'][key].update(source_detail_parent=uid,source_detail_part=p['id'])
        parent['source_detail_contract']=identity(contract)
        parent['attempts'].append({'action':'adaptive_detail_reobserve','reason':row['diagnosis'],'view':row['original_view'],
                                  'submission_hash':identity(row),'detail_features':[p['id'] for p in row['observed_parts']]})
        # Source interpretation and current output checks are separate.
        # A restoration finding never closes saved-result quality here.
        parent['unexplained']=[] if row['resolution']!='uncertain' else [{'roi':row['original_roi'],'reason':row['diagnosis']}]
        if row['resolution']=='uncertain':parent['status']='REOBSERVE'
        else:
            parent['status']='SOURCE_PARTITION_REVIEWED' if parent['children'] else 'SOURCE_LEAF_READY'
        up=parent.get('parent')
        while up:
            tree['nodes'][up]['detail_recheck_required']=True;up=tree['nodes'][up].get('parent')
    state['source_detail_contracts']=ledger
    if tree:sr._store(task,state,tree)
    amend_compiled_layers(task,state,observations)
    state.pop('recursive_obligations_result',None);state.pop('object_lifecycle_result',None)

def _anchor(frame,axis,where):
    i=0 if axis=='x' else 1
    return frame[i]+{'min':0,'center':.5,'max':1}[where]*frame[i+2]

def checks_report(task,state,candidate):
    from .boundary_geometry import saved_nodes
    from .adaptive_detail import metrics,_box
    from .appearance_metrics import canvas
    nodes=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size']);rows=[]
    original=canvas(str(safe_path(task,state['source']['path'])),state['source']['sha256'],tuple(state['source_size']))
    actual=canvas(str(safe_path(task,candidate['preview']['path'])),candidate['preview']['sha256'],tuple(state['source_size']))
    for uid,contract in state.get('source_detail_contracts',{}).get('units',{}).items():
        validate_checks(contract['checks'],state['source_size'])
        results=[]
        for c in contract['checks']:
            kind=c['type'];good=False;data={}
            if kind=='parts_present':
                missing=[n for n in c['objects'] if n not in nodes or nodes[n]['error']]
                good=not missing;data={'missing':missing}
            elif kind=='source_function_frame':
                from .source_feature_functions import specifications,construct,semantic_root
                spec=specifications(task,state).get(c['unit']);unit=state['quality']['units'].get(c['unit'])
                def source_owned(name):
                    seen=set()
                    while name and name not in seen:
                        if name in unit.get('objects',[]):return True
                        seen.add(name);name=nodes.get(name,{}).get('parent_name')
                    return False
                if spec and unit and identity(spec)==c['function_hash'] and source_owned(c['object']):
                    expected={o['id']:o for o in construct(task,state,{'id':semantic_root(unit,spec),'roi':unit['roi'],'semantic_class':unit['profile']},spec)}
                    e=nodes.get(c['object']);wanted=expected.get(c['object'])
                    if e and wanted and not e['error'] and e['frame']:
                        from .neighbor_actions import verified_pose
                        from .source_feature_functions import expected_frame
                        pose=verified_pose(task,state,candidate,c['object'],nodes);target=expected_frame(wanted,pose)
                        err=max(abs(a-b) for a,b in zip(e['frame'],target));good=err<=.03
                        data={'actual_frame':e['frame'],'original_function_frame':wanted['bbox'],'verified_original_relation_pose':pose,
                              'posed_constructor_frame':target,'max_error_source_px':err,'native_serialization_tolerance_px':.03,'function_hash':c['function_hash']}
                if not data:data={'status':'FROZEN_ORIGINAL_FUNCTION_CORRESPONDENCE_REQUIRED'}
            elif kind in ('native_frame','native_type'):
                e=nodes.get(c['object']);good=bool(e and not e['error'])
                if good and kind=='native_frame':
                    frame=e['frame'];err=max(abs(a-b) for a,b in zip(frame,c['expected_frame'])) if frame else math.inf
                    good=err<=c.get('tolerance_source_px',1.5);data={'actual_frame':frame,'expected_frame':c['expected_frame'],'max_error_source_px':err if math.isfinite(err) else None}
                elif good:
                    good=e['tag']==c['tag'];data={'actual_tag':e['tag'],'expected_tag':c['tag']}
            elif kind in ('join','contains','layer'):
                a,b=nodes.get(c['a']),nodes.get(c['b']);good=bool(a and b and not a['error'] and not b['error'] and a['frame'] and b['frame'])
                if good and kind=='join':
                    err=abs(_anchor(a['frame'],c['axis'],c['a_anchor'])-_anchor(b['frame'],c['axis'],c['b_anchor'])-c.get('expected_offset',0))
                    good=err<=c.get('tolerance_source_px',1.5);data={'anchor_error_source_px':err,'axis':c['axis']}
                elif good and kind=='contains':
                    x,y,w,h=a['frame'];u,v,p,q=b['frame'];tol=c.get('tolerance_source_px',.5)
                    good=u>=x-tol and v>=y-tol and u+p<=x+w+tol and v+q<=y+h+tol;data={'outer_frame':a['frame'],'inner_frame':b['frame']}
                elif good:
                    # Saved traversal order is actual paint order, including
                    # descendants at the ancestor's group location.
                    order=list(nodes);good=order.index(c['a'])<order.index(c['b']);data={'behind_index':order.index(c['a']),'front_index':order.index(c['b'])}
            elif kind=='source_patch':
                x,y,u,v=_box(c['roi'],state['source_size']);values=metrics(original[y:v,x:u],actual[y:v,x:u])[0];value=values.get(c['metric'])
                good=value is not None and c.get('min',-math.inf)<=value<=c.get('max',math.inf);data={'value':value,'metric':c['metric'],'roi':c['roi']}
            results.append({'id':c['id'],'type':kind,'passed':bool(good),**data})
        named={n for p in contract['observed_parts'] for n in p['objects']};missing=sorted(named-set(nodes))
        from .adaptive_detail import source_units
        from .source_observability import report_one,comparison_values
        unit=source_units(state)[uid];x,y,u,v=_box(unit['roi'],state['source_size'])
        try:
            source_values=comparison_values(state,unit,contract.get('source_observability',{}),original,actual)
            observable=report_one(contract.get('source_observability',{}),source_values)
        except ValueError as error:
            observable={'passed':False,'kind':contract.get('source_observability',{}).get('kind'),
                        'checks':[{'id':'original_comparison_support','passed':False,'reason':str(error)}],
                        'route':'REFINE_ORIGINAL_SOURCE_OWNERSHIP_REQUIRED'}
        passed=bool(results) and not missing and all(r['passed'] for r in results) and contract['resolution']!='uncertain' and observable['passed']
        rows.append({'id':uid,'passed':passed,'checks':results,'missing_source_part_objects':missing,
                     'source_contract_hash':identity(contract),'observed_parts':contract['observed_parts'],
                     'source_observability':observable,
                     'status':'SOURCE_DETAIL_STRUCTURE_MET' if passed else 'SOURCE_DETAIL_REPAIR_REQUIRED'})
    return {'passed':all(r['passed'] for r in rows),'items':rows}

def report(task,state,candidate,scan_result=None):
    from .adaptive_detail import scan
    triage=scan_result or scan(task,state,candidate);facts=checks_report(task,state,candidate)
    passed=triage['passed'] and facts['passed']
    return {'schema':'source-detail-acceptance-1','passed':passed,
            'status':'ORIGINAL_DETAIL_AND_CONTEXT_VERIFIED' if passed else 'ORIGINAL_DETAIL_WORK_REQUIRED',
            'triage':triage,'source_facts':facts,
            'scope':'Original/current local discrepancy coverage, retained source facts and every compiled detail relation; no historical appearance policy can waive these checks.'}
