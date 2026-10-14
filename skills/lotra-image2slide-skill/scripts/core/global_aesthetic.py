"""Source-bound six-dimension global score, independent of local similarity.

Deterministic numeric proxies supplement, rather than impersonate, the host's
source interpretation and whole-image observations. Missing remains null.
"""
import copy,math
from pathlib import Path
import numpy as np
from .common import identity,digest,read_json,write_json,safe_path,writer

VERSION='global-aesthetic-quality-1'
DIMENSIONS=('layout','visual_balance','alignment_spacing','layer_occlusion','color_style','readability')

def configuration():
    from .execution_contract import ROOT
    return read_json(ROOT/'config/object-global-quality.json')

def validate_settings(settings):
    weights=settings['weights'];floors=settings['dimension_floors']
    if set(weights)!=set(DIMENSIONS) or set(floors)!=set(DIMENSIONS):raise ValueError('All six independent global dimensions required')
    values=list(weights.values())+list(floors.values())+[settings['overall_threshold']]
    if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in values) or any(v<=0 for v in weights.values()) or abs(sum(weights.values())-1)>1e-8:
        raise ValueError('Finite positive normalized weights and finite thresholds required')
    for key in ('position_tolerance_canvas','size_ratio_tolerance','balance_center_tolerance','density_distribution_tolerance','color_histogram_tolerance','alignment_tolerance_px','spacing_tolerance_px','maximum_translation_canvas','maximum_scale_change'):
        if type(settings[key]) not in (int,float) or not math.isfinite(settings[key]) or settings[key]<=0:raise ValueError('Finite positive global bound required: '+key)
    if settings['maximum_translation_canvas']>.10 or settings['maximum_scale_change']>.20:raise ValueError('Global repair cannot substantially rebuild a region')
    return settings

def combine(settings,dimensions):
    validate_settings(settings);missing=[k for k in DIMENSIONS if dimensions.get(k) is None]
    if missing:return {'passed':False,'status':'GLOBAL_DIMENSIONS_UNMEASURED','score':None,'missing':missing,'dimensions':{k:dimensions.get(k) for k in DIMENSIONS}}
    if any(type(dimensions[k]) not in (int,float) or not math.isfinite(dimensions[k]) or not 0<=dimensions[k]<=1 for k in DIMENSIONS):raise ValueError('Nonfinite or unnormalized global dimension')
    score=sum(settings['weights'][k]*dimensions[k] for k in DIMENSIONS)
    below=[k for k in DIMENSIONS if dimensions[k]<settings['dimension_floors'][k]]
    passed=score>=settings['overall_threshold'] and not below
    return {'passed':passed,'status':'GLOBAL_TARGETS_MET' if passed else 'GLOBAL_LAYOUT_OR_OBSERVATION_REPAIR_REQUIRED','score':score,'missing':[],
        'dimensions':{k:dimensions[k] for k in DIMENSIONS},'weights':settings['weights'],'threshold':settings['overall_threshold'],
        'dimension_floors':settings['dimension_floors'],'below_floors':below,'direction':'Higher is better; error proxies and raw measurements are reported separately.'}

def _exp(error):return float(math.exp(-float(error)**2))

def balance_values(source,actual,settings=None):
    settings=settings or configuration()['global']
    def values(a):
        gray=a@np.array([.2126,.7152,.0722]);weight=1-gray;total=float(weight.sum())
        if total<=1e-10:return None
        h,w=gray.shape;center=[float(weight.sum(axis=0)@((np.arange(w)+.5)/w)/total),float(weight.sum(axis=1)@((np.arange(h)+.5)/h)/total)]
        quadrants=[float(weight[y:y+h//2,x:x+w//2].sum()/total) for y in (0,h//2) for x in (0,w//2)]
        return {'center':center,'quadrants':quadrants,'whitespace':float((gray>.96).mean())}
    first,second=values(source),values(actual)
    if first is None or second is None:return {'score':None,'reason':'No contrast mass for visual balance'}
    center=float(np.linalg.norm(np.subtract(first['center'],second['center'])))
    density=float(np.abs(np.subtract(first['quadrants'],second['quadrants'])).sum()/2)
    blank=abs(first['whitespace']-second['whitespace'])
    score=(_exp(center/settings['balance_center_tolerance'])*_exp(density/settings['density_distribution_tolerance'])*_exp(blank/settings['density_distribution_tolerance']))**(1/3)
    return {'score':score,'source':first,'actual':second,'visual_center_offset':center,'density_distribution_tv':density,'whitespace_error':blank,
        'reference':'Original intended mass and whitespace; symmetry is not forced.'}

def _bbox(boxes):
    boxes=[b for b in boxes if b is not None]
    if not boxes:return None
    x=min(b[0] for b in boxes);y=min(b[1] for b in boxes)
    return [x,y,max(b[0]+b[2] for b in boxes)-x,max(b[1]+b[3] for b in boxes)-y]

def discover(task,state,candidate=None):
    plan=state.get('quality_intent',{});items=plan.get('items',[])
    roots=[r for r in items if not r.get('semantic_parent')]
    # An independently optimized tiny icon need not become another global
    # layout region when its complete actual ownership is already represented
    # by a source-declared containing module. Keep maximal ownership sets;
    # object lifecycle still retains every small unit separately.
    roots=[r for r in roots if not any(set(r['objects'])<set(other['objects']) for other in roots)]
    regions=[{'id':r['id'],'objects':r['objects'],'source_bounds':r['roi'],'source_facts':r['source_facts'],
              'source_view':r['source_view'],'evidence':r['source_evidence']} for r in roots]
    if not regions:
        regions=[{'id':c['id'],'objects':[],'source_bounds':c['roi'],'source_facts':[c.get('source_note','')],
            'evidence':c.get('source_note','')} for c in state.get('analysis',{}).get('components',[]) if c.get('roi')]
    return {'kind':'global_aesthetic_source','source_hash':state['source']['sha256'],'source':state['source'],
        'regions':regions,'settings':configuration()['global'],'alignments':[],'spacings':[],'style_groups':[],'orders':[],
        'reading_order':[r['id'] for r in regions],
        'instruction':'Inspect the original whole figure. Freeze region roles, original bounds and intentional alignment/spacing/style/order. Keep authorized improvements separate. Never derive source geometry from the candidate. Bind original plan before comparison; source-plan objects bind after native construction.'}

def bind(task,request):
    from . import agent_runtime as a
    from .quality_intent import validate
    from .execution_contract import inventory
    task,state=a._state(task);candidate=state.get('active_candidate') or state.get('selected')
    if request.get('source_hash')!=state['source']['sha256'] or not request.get('evidence'):raise ValueError('Independent whole-original evidence required for global plan')
    allowed={'source_hash','regions','settings','alignments','spacings','style_groups','orders','reading_order','evidence','revision_reason'}
    if set(request)-allowed:raise ValueError('Unknown global source-plan fields')
    settings=validate_settings(copy.deepcopy(request.get('settings',configuration()['global'])))
    prior=state.get('global_aesthetic_plan')
    if prior and settings!=prior['settings']:raise ValueError('Frozen global ruler cannot be loosened after comparison')
    rows=copy.deepcopy(request.get('regions',[]));size=state['source_size']
    if not rows or len({r.get('id') for r in rows})!=len(rows):raise ValueError('Distinct complete original global regions required')
    names=set();inv=None
    if candidate:validate(task,state,candidate);inv,_,_=inventory(task,state,candidate);names=set(inv['native_names'])
    for row in rows:
        if set(row)-{'id','objects','source_bounds','source_facts','source_view','evidence','target_bounds','authorization'} or not row.get('evidence') or not row.get('source_facts'):raise ValueError('Source region facts and concrete original evidence required')
        bounds=row.get('source_bounds')
        if not bounds or len(bounds)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in bounds) or min(bounds[2:])<=0 or bounds[0]<0 or bounds[1]<0 or bounds[0]+bounds[2]>size[0]+1 or bounds[1]+bounds[3]>size[1]+1:raise ValueError('Source region is outside the original canvas')
        if row.get('target_bounds')!=None and row['target_bounds']!=bounds and not row.get('authorization'):raise ValueError('Improved layout targets need a separate authorized purpose')
        if len(row.get('objects',[]))!=len(set(row.get('objects',[]))) or candidate and not set(row.get('objects',[]))<=names:raise ValueError('Global plan names unknown actual owners')
    for key in ('alignments','spacings','style_groups','orders'):
        for rule in request.get(key,[]):
            if not rule.get('objects') or len(rule['objects'])<2 or not rule.get('evidence') or candidate and not set(rule['objects'])<=names:raise ValueError('Group relation needs source evidence and actual named members')
            if key in ('alignments','spacings'):
                if rule.get('axis') not in ('x','y') or rule.get('anchor','start') not in ('start','center','end') or type(rule.get('tolerance_px')) not in (int,float) or not 0<rule['tolerance_px']<=10:raise ValueError('Finite source alignment/spacing relation required')
    reading=request.get('reading_order',[])
    if len(reading)!=len(set(reading)) or set(reading)!={r['id'] for r in rows}:raise ValueError('Reading hierarchy must account for each original region')
    plan={'schema':VERSION,'source_hash':state['source']['sha256'],'regions':rows,'settings':settings,
          **{k:copy.deepcopy(request.get(k,[])) for k in ('alignments','spacings','style_groups','orders','reading_order')},
          'evidence':request['evidence'],'configuration_hash':identity(configuration()),'history':copy.deepcopy(prior.get('history',[])) if prior else []}
    if candidate:
        from .native_connection_transaction import PREFIX
        covered=set(n for r in rows for n in r['objects'])
        # Group owners cover their actual saved descendants, never a guessed
        # count. Nonpaint derived ports retain their connection gate.
        for n in inv['native_names']:
            parent=inv['parents'].get(n)
            while parent and parent not in covered:parent=inv['parents'].get(parent)
            if parent:covered.add(n)
        missing=sorted(n for n in names-covered if not n.startswith(PREFIX))
        if missing:raise ValueError('Global plan omits saved owners: '+repr(missing[:8]))
    if prior:
        if not request.get('revision_reason'):raise ValueError('Global plan revisions require located source correction evidence')
        plan['history'].append({k:v for k,v in prior.items() if k!='history'})
    plan['compiled_hash']=identity({k:v for k,v in plan.items() if k not in ('compiled_hash','history')})
    with writer(task):
        state['global_aesthetic_plan']=plan;state.pop('acceptance',None);state.pop('quality_result',None)
        a._event(task,'global_original_plan_frozen',{'hash':plan['compiled_hash'],'regions':[r['id'] for r in rows]});a._save(task,state)
    return {'status':'GLOBAL_PLAN_FROZEN','hash':plan['compiled_hash']}

def validate_plan(state):
    plan=state.get('global_aesthetic_plan')
    if not plan:return None
    if plan['source_hash']!=state['source']['sha256'] or plan['compiled_hash']!=identity({k:v for k,v in plan.items() if k not in ('compiled_hash','history')}) or plan['configuration_hash']!=identity(configuration()):
        raise ValueError('Global original plan is stale or modified; evidence-preserving source revision required')
    validate_settings(plan['settings']);return plan

def resolved_plan(task,state,candidate):
    """Compile preconstruction source regions to the complete saved inventory.

    Original facts stay immutable; bindings are derived from source-owned policy
    roots. A new drawing can never manufacture a new original region extent.
    """
    plan=copy.deepcopy(validate_plan(state))
    if not plan:return None
    policies=state.get('quality_intent',{}).get('items',[])
    for region in plan['regions']:
        if not region['objects']:
            matched=[p for p in policies if p['id'] in (region['id'],'root:'+region['id'])]
            if len(matched)!=1:raise ValueError('Original global region has no unique complete native binding: '+region['id'])
            region['objects']=matched[0]['objects']
    from .execution_contract import inventory
    from .native_connection_transaction import PREFIX
    inv,_,_=inventory(task,state,candidate);covered={n for r in plan['regions'] for n in r['objects']}
    if covered-set(inv['native_names']):raise ValueError('Global source binding contains absent actual native owners')
    for name in inv['native_names']:
        parent=inv['parents'].get(name)
        while parent and parent not in covered:parent=inv['parents'].get(parent)
        if parent:covered.add(name)
    missing=[n for n in inv['native_names'] if n not in covered and not n.startswith(PREFIX)]
    if missing:raise ValueError('Global region binding omits current saved objects: '+repr(missing[:8]))
    return plan

def _basis(state,candidate):
    from .execution_contract import _implementation
    return identity({'source':state['source'],'candidate':{k:candidate.get(k) for k in ('pptx','preview','render')},
                     'plan':state.get('global_aesthetic_plan'),'implementation':_implementation()})

def packet(task,state,candidate):
    if not validate_plan(state):return discover(task,state,candidate)
    old=state.get('global_aesthetic_observations',{})
    if old.get('basis')==_basis(state,candidate) and set(old.get('dimensions',{}))==set(DIMENSIONS):return None
    return {'kind':'global_aesthetic_observation','source_hash':state['source']['sha256'],'candidate_hash':candidate['pptx']['sha256'],
        'source':state['source'],'actual_preview':candidate['preview'],'basis':_basis(state,candidate),
        'dimensions':list(DIMENSIONS),'rubric':{'0':'Major defect','1':'Repair needed','2':'Acceptable; state minor limits','3':'No located defect in this dimension'},
        'instruction':'Inspect actual whole-source and whole-output views. For each dimension report level, actual facts, evidence and located issues. A local icon approval or a check count is not a global observation.'}

def observe(task,request):
    from . import agent_runtime as a
    task,state=a._state(task);candidate=state.get('active_candidate') or state['selected'];validate_plan(state)
    if request.get('source_hash')!=state['source']['sha256'] or request.get('candidate_hash')!=candidate['pptx']['sha256'] or request.get('basis')!=_basis(state,candidate) or request.get('preview_sha256')!=candidate['preview']['sha256']:
        raise ValueError('Global observations must bind exact source, current actual preview, plan and implementation')
    dimensions=request.get('dimensions',{})
    if set(dimensions)!=set(DIMENSIONS):raise ValueError('Six actual global observations required; missing is not zero')
    for key,row in dimensions.items():
        if set(row)-{'level','actual_facts','evidence','issues'} or type(row.get('level')) is not int or row['level'] not in range(4) or not row.get('actual_facts') or not row.get('evidence') or not isinstance(row.get('issues'),list):
            raise ValueError('Each whole-image observation needs finite ordinal level, actual facts, concrete evidence and located issues')
        if row['level']<2 and not row['issues']:raise ValueError('A failed global dimension needs located repair evidence')
    record={'schema':VERSION,'basis':_basis(state,candidate),'source':state['source'],'candidate':{k:candidate[k] for k in ('pptx','preview','render')},'dimensions':copy.deepcopy(dimensions)}
    with writer(task):
        old=state.get('global_aesthetic_observations')
        if old and old!=record:state.setdefault('global_aesthetic_observation_history',[]).append(old)
        state['global_aesthetic_observations']=record;state.pop('quality_result',None);state.pop('acceptance',None)
        a._event(task,'actual_global_observations_recorded',{'basis':record['basis'],'levels':{k:r['level'] for k,r in dimensions.items()}});a._save(task,state)
    return {'status':'GLOBAL_OBSERVATIONS_RECORDED','basis':record['basis']}

def layout_values(plan,frames,size):
    settings=plan['settings'];diagonal=math.hypot(*size);rows=[]
    for region in plan['regions']:
        actual=_bbox([frames.get(n) for n in region['objects']]);reference=region.get('target_bounds',region['source_bounds'])
        if actual is None:rows.append({'id':region['id'],'score':None,'reason':'Missing actual saved region bounds'});continue
        center=math.hypot(actual[0]+actual[2]/2-reference[0]-reference[2]/2,actual[1]+actual[3]/2-reference[1]-reference[3]/2)/diagonal
        ratios=[abs(actual[k]-reference[k])/reference[k] for k in (2,3)]
        # Regions declared as source crop windows include white margins; the
        # geometry score is explicit about this limitation, never re-registers
        # to a candidate. Host layout observations remain independently required.
        score=(_exp(center/settings['position_tolerance_canvas'])+sum(_exp(v/settings['size_ratio_tolerance']) for v in ratios)/2)/2
        rows.append({'id':region['id'],'source_bounds':region['source_bounds'],'target_bounds':reference,'actual_bounds':actual,
            'center_error_canvas':center,'size_ratio_errors':ratios,'score':score})
    score=float(np.mean([r['score'] for r in rows])) if rows and all(r['score'] is not None for r in rows) else None
    return {'score':score,'regions':rows,'errors_direction':'Lower is better'}

def alignment_values(plan,frames):
    rows=[]
    for family in ('alignments','spacings'):
        for rule in plan[family]:
            boxes=[frames.get(n) for n in rule['objects']]
            if any(b is None for b in boxes):rows.append({'family':family,'score':None,'reason':'Actual group member missing'});continue
            axis=0 if rule['axis']=='x' else 1;anchor=rule.get('anchor','start');fraction={'start':0.,'center':.5,'end':1.}[anchor]
            coords=[b[axis]+fraction*b[axis+2] for b in boxes]
            if family=='alignments':error=float(np.std(coords))
            else:
                ordered=sorted(boxes,key=lambda b:b[axis]);gaps=[b[axis]-(a[axis]+a[axis+2]) for a,b in zip(ordered,ordered[1:])]
                error=float(np.std(gaps));
                if rule.get('target_gap_px') is not None:error=max(error,float(np.mean([abs(g-rule['target_gap_px']) for g in gaps])))
            rows.append({'family':family,'objects':rule['objects'],'error_px':error,'score':_exp(error/rule['tolerance_px'])})
    return {'score':float(np.mean([r['score'] for r in rows])) if rows and all(r['score'] is not None for r in rows) else None,
        'relations':rows,'applicability':'source-declared relations' if rows else 'No common-grid alignment declared; whole-image observation still required.'}

def evaluate(task,state,candidate,gates):
    from .execution_contract import resource
    from .appearance_metrics import canvas,image_values
    from .boundary_geometry import saved_nodes
    plan=resolved_plan(task,state,candidate)
    if not plan:return {'passed':False,'status':'GLOBAL_SOURCE_PLAN_REQUIRED','score':None,'missing':list(DIMENSIONS)}
    actual=saved_nodes(resource(task,candidate['pptx']),state['source_size'])
    from .global_layout_actions import frames_from_nodes
    frames=frames_from_nodes(actual)
    source=canvas(str(resource(task,state['source'])),state['source']['sha256'],tuple(state['source_size']))
    image=canvas(str(resource(task,candidate['preview'])),candidate['preview']['sha256'],tuple(state['source_size']))
    settings=plan['settings'];layout=layout_values(plan,frames,state['source_size']);balance=balance_values(source,image,settings)
    alignment=alignment_values(plan,frames);color=image_values(source,image)['color_histogram_tv']
    style_rows=[]
    for group in plan['style_groups']:
        widths=[]
        for name in group['objects']:
            if name not in actual:continue
            line=actual[name]['node'].find('p:spPr/a:ln',__import__(__package__+'.mathml',fromlist=['NS']).NS)
            if line is not None and line.get('w'):
                mapping=actual[name]['parent_matrix'];widths.append(float(line.get('w'))*math.sqrt(abs(float(np.linalg.det(mapping[:2,:2])))))
        style_rows.append({'objects':group['objects'],'stroke_width_std_px':float(np.std(widths)) if len(widths)>=2 else None})
    order_errors=[]
    for rule in plan['orders']:
        nodes=[actual[n]['node'] for n in rule['objects']];parents=[n.getparent() for n in nodes]
        if any(p is not parents[0] for p in parents) or [parents[0].index(n) for n in nodes]!=sorted(parents[0].index(n) for n in nodes):order_errors.append(rule['objects'])
    structural=all(gates[k]['passed'] for k in ('frame','composition','layout','connection_geometry','whole_inventory')) and not order_errors
    content=all(gates[k]['passed'] for k in ('text_math','original_content_predicates','source_typography'))
    observation=state.get('global_aesthetic_observations',{});current=observation.get('basis')==_basis(state,candidate)
    host={k:settings['observation_levels'][observation['dimensions'][k]['level']] if current and k in observation.get('dimensions',{}) else None for k in DIMENSIONS}
    style_scores=[_exp(r['stroke_width_std_px']/settings['alignment_tolerance_px']) for r in style_rows if r['stroke_width_std_px'] is not None]
    if style_rows and len(style_scores)!=len(style_rows):style_score=None
    else:style_score=float(np.mean([_exp(color/settings['color_histogram_tolerance'])]+style_scores))
    numeric={'layout':layout['score'],'visual_balance':balance['score'],'alignment_spacing':alignment['score'],
        'layer_occlusion':float(structural),'color_style':style_score,'readability':float(content)}
    dimensions={k:None if host[k] is None else host[k] if numeric[k] is None and k=='alignment_spacing' else
        None if numeric[k] is None else (host[k]+numeric[k])/2 for k in DIMENSIONS}
    result=combine(settings,dimensions)
    # Structural/content failures and a model's located repair severity are
    # hard vetoes; they cannot be averaged away by color or whitespace scores.
    host_issues=[k for k in DIMENSIONS if current and observation['dimensions'][k]['level']<2]
    result['passed'] &= structural and content and not host_issues
    if not result['passed'] and not result['missing']:result['status']='GLOBAL_REPAIR_REQUIRED'
    result.update(schema=VERSION,plan_hash=plan['compiled_hash'],basis=_basis(state,candidate),numeric_dimensions=numeric,observation_dimensions=host,
        raw={'layout':layout,'visual_balance':balance,'alignment_spacing':alignment,'color_histogram_tv':color,'style_line_widths':style_rows,'paint_order_errors':order_errors},
        hard_vetoes={'local_structure':not structural,'local_content':not content,'host_repair_dimensions':host_issues},
        local_scores_mixed_into_global=False,limits=configuration()['limits'])
    path=task/'audits'/('global-aesthetic-'+identity(result)+'.json');write_json(path,result)
    state['global_aesthetic_result']={'path':path.relative_to(task).as_posix(),'sha256':digest(path)}
    return result
