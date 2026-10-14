"""Condition-based recipes and executable, bounded object work orders."""
import copy
from .common import ROOT, identity, read_json, write_json
from .source_analysis import contract_gaps, validate, postorder

VERSION='object-contract-compiler-0.2.0'
OPERATIONS={'fit_color','fit_circle','fit_linear_gradient','set_parameters','font_candidates','fit_path','fit_boundary_segment'}
PARAMETERS={'fill','gradient','gradient_angle','line_width','font','font_size','bold','char_spacing_pt',
            'baseline_offset_pt','adjustments','bbox','part_bbox','path_points','route_points',
            'arrow_width','arrow_length','row_heights','column_widths','merges','padding','z_order','preset','contours','component'}


def subtree(analysis,id):
    nodes={n['id']:n for n in analysis['nodes']};selected={id}
    while True:
        new=selected|{n['id'] for n in nodes.values() if n.get('parent') in selected}
        if new==selected:return selected
        selected=new


def select_examples(analysis,id,backend,defects=(),limit=2):
    nodes={n['id']:n for n in analysis['nodes']};node=nodes[id]
    parts={nodes[k]['semantic_class'] for k in subtree(analysis,id)-{id}}
    catalog=read_json(ROOT/'references/examples/index.json');selected=[];excluded=[]
    for example in catalog['examples']:
        cond=example['conditions'];reasons=[]
        for key,value in [('types',node['type']),('views',node['view']),('classes',node['semantic_class'])]:
            if cond.get(key) and value not in cond[key]:reasons.append(key)
        if cond.get('required_parts') and not set(cond['required_parts'])<=parts:reasons.append('visible parts')
        if not set(cond.get('backend_capabilities',[]))<=set(backend.get('capabilities',[])):reasons.append('backend')
        if set(cond.get('exclude_styles',[]))&set(node['style_tags']):reasons.append('excluded style')
        if cond.get('raster_permission') and not analysis['user_constraints'].get('allow_data_raster',False):reasons.append('raster prohibited')
        if cond.get('required_defects_any') and not set(cond['required_defects_any'])&set(defects):reasons.append('no applicable defect')
        if any(analysis.get('task_properties',{}).get(k)!=v for k,v in cond.get('requires_context',{}).items()):reasons.append('missing task context')
        if reasons:excluded.append({'id':example['id'],'reasons':reasons});continue
        score=len(set(example.get('defects',[]))&set(defects))+len(set(example.get('style_tags',[]))&set(node['style_tags']))
        selected.append((score,example['id'],example))
    selected.sort(key=lambda row:(-row[0],row[1]))
    return {'selected':[r[2] for r in selected[:limit]],'excluded':excluded,'selection_scope':'explicit conditions, then structure/style/current defect; not a learned retriever'}


def _range_intersection(a,b):
    if a is None:return b
    if b is None:return a
    result=[max(a[0],b[0]),min(a[1],b[1])]
    if result[0]>result[1]:raise ValueError('Conflicting parameter ranges')
    return result


def compile_object(analysis,base,object_id,backend,knowledge=(),defects=(),use_cases=True):
    parsed=validate(analysis,base);node=parsed['nodes'][object_id]
    catalog=read_json(ROOT/'config/contracts.json');cards={c['id']:c for c in catalog['cards']}
    parent=parsed['nodes'].get(node.get('parent'));ids=[node['level'],node['type'],node['role'],'M03','M04','M06','M07']
    if parent:ids.append(parent['level'])
    if any(n.get('parent')==object_id for n in analysis['nodes']):ids.append('M05')
    ids=list(dict.fromkeys(ids));selected=[cards[id] for id in ids]
    constraints=set();metrics=[];ranges={};operations=set(node['edit_targets'])
    for card in selected:
        constraints.update(card['hard_constraints']);operations.update(card['outputs']['native_operations'])
        metrics.extend(card['metric_refs'])
        for key,p in card['parameters'].items():ranges[key]=_range_intersection(ranges.get(key),p['range'])
    for key,value in node.get('parameter_ranges',{}).items():
        if key not in PARAMETERS:raise ValueError('Unknown parameter range')
        ranges[key]=_range_intersection(ranges.get(key),value)
    # Geometry placement is an explicit allowed operation, never an implied edit
    # of children or scientific content by a styling recipe.
    ranges.setdefault('bbox',None)
    examples=select_examples(analysis,object_id,backend,[d['kind'] for d in defects]) if use_cases else {'selected':[],'excluded':[]}
    descendants=subtree(analysis,object_id);render_ids={r for k in descendants for r in parsed['nodes'][k].get('render_ids',[])+parsed['nodes'][k].get('wrapper_ids',[])}
    source_gaps=contract_gaps(node,parsed['children'].get(object_id,[]),analysis.get('relations',[]))
    evidence_ids={r for k in descendants for r in parsed['nodes'][k]['evidence_refs']}
    results=[];actions=[]
    for proposed in knowledge:
        item=copy.deepcopy(proposed);reasons=[]
        if item.get('object_id')!=object_id:continue
        if item.get('source_hash')!=analysis['source']['sha256']:reasons.append('source identity')
        if not item.get('evidence_refs') or not set(item['evidence_refs'])<=evidence_ids:reasons.append('unrelated/unlocated evidence')
        elif any(parsed['observations'][k]['status']!='observed' for k in item['evidence_refs']):reasons.append('source evidence unresolved/inferred')
        if item.get('kind') not in ('method','hypothesis'):reasons.append('knowledge is not a method or explicit hypothesis')
        if item.get('new_parts'):reasons.append('new parts require a separately versioned source observation')
        facts=node.get('facts',{})
        for key,value in item.get('requires_facts',{}).items():
            if facts.get(key)!=value:reasons.append('source fact conflict: '+key)
        if not item.get('actions') or not item.get('expected_change') or not item.get('metric_refs'):reasons.append('no comparable drawing decision')
        for action in item.get('actions',[]):
            if action.get('op') not in OPERATIONS or action['op'] not in backend.get('operations',[]):reasons.append('backend operation unavailable')
            if not set(action.get('targets',[]))<=render_ids or not action.get('targets'):reasons.append('cross-object action')
            for target in action.get('targets',[]):
                owner=parsed['owners'].get(target)
                if action.get('op')=='fit_circle' and owner and parsed['nodes'][owner].get('facts',{}).get('contour') not in ('circle','approximately_circular'):
                    reasons.append('circle fit lacks observed circular contour')
            for parameter in action.get('parameters',{}):
                if parameter not in PARAMETERS:reasons.append('not an allowed drawing parameter: '+parameter)
            for key,value in action.get('parameters',{}).items():
                if key in node.get('fixed_parameters',{}) and node['fixed_parameters'][key]!=value:reasons.append('violates observed fixed parameter: '+key)
                bound=ranges.get(key)
                if bound is not None and isinstance(value,(int,float)) and not bound[0]<=value<=bound[1]:reasons.append('parameter outside contract range: '+key)
            if action.get('parameters',{}).get('preset') and action['parameters']['preset'] not in backend.get('presets',[]):reasons.append('native preset unavailable')
        item['proposal_hash']=identity(proposed);item['status']='rejected' if reasons else 'evidence_compatible'
        item['filter_reasons']=sorted(set(reasons));item['utility']='unmeasured'
        results.append(item)
        if not reasons:
            for a in item['actions']:actions.append(dict(a,knowledge_id=item['id']))
    needed=set(operations);missing=sorted(needed-set(backend.get('edit_operations',[])))
    # Unsupported editing is visible even if file construction can proceed.
    order={'compiler_version':VERSION,'source_hash':analysis['source']['sha256'],'analysis_hash':parsed['analysis_hash'],
           'object_id':object_id,'contracts':ids,'contract_digest':identity(selected),'type':node['type'],
           'render_types':cards[node['type']]['applies']['render_types'],'render_ids':sorted(render_ids),
           'source_observations':[parsed['observations'][k] for k in sorted(evidence_ids)],
           'decomposition':node['decomposition'],'hard_checks':sorted(constraints),
           'source_contract_gaps':source_gaps,'parameter_ranges':ranges,
           'metrics':list(dict.fromkeys(metrics)),'cases':[{k:e[k] for k in ('id','status','method','counterexample','path')} for e in examples['selected']],
           'knowledge':results,'actions':actions,'defects':list(defects),'native_operations':sorted(needed),
           'backend':backend,'missing_native_operations':missing,
           'status':'COMPILED_WITH_LIMITS' if missing or source_gaps else 'COMPILED',
           'parent_id':node.get('parent'),'parent_checks':any(c['interfaces']['parent_checks'] for c in selected),
           'stop_policy':{'unresolved':'UNVERIFIED','budget':'PAUSED_RESOURCE_LIMIT','no_fixed_round_success':True},
           'provenance':'Host supplies observations/knowledge; this compiler calls no model and asserts no improvement'}
    order['work_order_hash']=identity(order)
    return order


def compile_task(analysis,base,backend,knowledge,output,defects=(),use_cases=True):
    from pathlib import Path
    output=Path(output)
    if output.exists():raise FileExistsError(output)
    validate(analysis,base);orders=[]
    for id in postorder(analysis):
        order=compile_object(analysis,base,id,backend,knowledge,[d for d in defects if d.get('object_id')==id],use_cases)
        write_json(output/(id+'.json'),order);orders.append({'object_id':id,'path':id+'.json','hash':order['work_order_hash']})
    index={'analysis_hash':identity(analysis),'order':'semantic_postorder','objects':orders,'version':VERSION}
    write_json(output/'index.json',index);return index


def record_utility(knowledge_id,decision,action_receipt,baseline,candidate,directions,output):
    from .typed_metrics import dominance
    same=all(baseline.get(k)==candidate.get(k) and baseline.get(k) is not None for k in ('plan_hash','source_hash','backend_hash'))
    if not same:result={'result':'unmeasured','reason':'Source, plan or backend mismatch/confounded comparison'}
    elif candidate.get('hard_status')=='FAIL':result={'result':'harmful','reason':'Noncompensable requirement failed'}
    elif candidate.get('hard_status')!='PASS' or candidate.get('context_status')!='PASS':result={'result':'unmeasured','reason':'Necessary object/parent evidence incomplete'}
    else:result=dominance(baseline['vector'],candidate['vector'],directions)
    record={'knowledge_id':knowledge_id,'changed_decision':decision,'executed_action':action_receipt,
            'baseline':baseline,'candidate':candidate,'measurements':result,
            'status':'locally_validated' if result['result']=='helped' else 'rejected' if result['result']=='harmful' else 'evidence_compatible',
            'scope':'single controlled comparison; not cross-instance calibration or a probability'}
    write_json(output,record);return record
