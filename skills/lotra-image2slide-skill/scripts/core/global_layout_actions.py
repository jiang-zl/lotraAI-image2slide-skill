"""Finite global layout search: no host coordinates, no object regeneration."""
import copy,math
from zipfile import ZipFile,ZIP_DEFLATED
import numpy as np
from lxml import etree as E
from .common import identity,digest,read_json,write_json,safe_path,writer
from .mathml import NS

def validate_request(request,names):
    if set(request)-{'expected_baseline_sha256','items'}:raise ValueError('Global layout accepts identities and bounded finite operations only')
    items=request.get('items',[])
    if not 1<=len(items)<=12 or len({i.get('object') for i in items})!=len(items):raise ValueError('Distinct bounded global owners required')
    for item in items:
        if set(item)-{'object','operation','axes','max_translation_px','max_scale_change'} or item.get('object') not in names or item.get('operation') not in ('translate','uniform_scale','paint_order'):
            raise ValueError('Unknown global owner/operation; agent coordinates and XML are prohibited')
        if item.get('operation')=='translate' and (not item.get('axes') or len(item['axes'])!=len(set(item['axes'])) or not set(item['axes'])<={'x','y'} or type(item.get('max_translation_px')) not in (int,float) or not math.isfinite(item['max_translation_px']) or item['max_translation_px']<=0):raise ValueError('Finite positive translation budget required')
        if item.get('operation')=='uniform_scale' and (type(item.get('max_scale_change')) not in (int,float) or not math.isfinite(item['max_scale_change']) or not 0<item['max_scale_change']<=.2):raise ValueError('Bounded uniform scaling required')
    return items

def frames_from_nodes(nodes):
    from .global_aesthetic import _bbox
    from .native_connection_transaction import verify_anchor
    frames={n:copy.deepcopy(r.get('frame')) for n,r in nodes.items()}
    for name,entry in nodes.items():
        if verify_anchor(entry):frames[name]=None
    unresolved={n for n,r in nodes.items() if r['tag']=='grpSp'}
    for _ in range(len(unresolved)+1):
        changed=False
        for n in list(unresolved):
            children=[c for c,r in nodes.items() if r.get('parent_name')==n]
            if any(c in unresolved for c in children):continue
            frames[n]=_bbox([frames[c] for c in children]);unresolved.remove(n);changed=True
        if not changed:break
    return frames

def solve(plan,frames,items,size):
    from scipy.optimize import minimize
    from .global_aesthetic import alignment_values,layout_values
    variables=[];bounds=[];settings=plan['settings'];limit=settings['maximum_translation_canvas']*math.hypot(*size)
    for item in items:
        if item['operation']!='translate':continue
        if frames.get(item['object']) is None:raise ValueError('Global owner has no actual saved extent')
        budget=item['max_translation_px']
        if budget>limit:raise ValueError('Translation exceeds frozen global change allowance')
        for axis in sorted(item['axes']):variables.append((item['object'],axis));bounds.append((-budget,budget))
    if not variables:return {},{'improved':False,'reason':'No translation variables','iterations':0}
    def patched(x):
        result=copy.deepcopy(frames)
        for (name,axis),delta in zip(variables,x):
            owned=[name]+plan.get('_descendants',{}).get(name,[])
            for owner in owned:
                if result.get(owner) is not None:result[owner][0 if axis=='x' else 1]+=float(delta)
        return result
    def objective(x):
        current=patched(x);alignment=alignment_values(plan,current)
        # Direct source-frame targets avoid derivative plateaus for distant
        # object positions; both source position and alignment are explicit.
        cost=0.
        for region in plan['regions']:
            target=region.get('target_bounds',region['source_bounds'])
            for name in region['objects']:
                if name not in current or current[name] is None:continue
                if name not in {v[0] for v in variables}:continue
                a=current[name];cost+=sum(((a[k]+a[k+2]/2-target[k]-target[k+2]/2)/max(3.,settings['position_tolerance_canvas']*math.hypot(*size)))**2 for k in (0,1))
        cost+=sum((r['error_px']/next(p['tolerance_px'] for p in plan[r['family']] if p['objects']==r['objects']))**2 for r in alignment['relations'] if r.get('error_px') is not None)
        return float(cost+1e-6*np.dot(x,x))
    def inside(x):
        current=patched(x);values=[]
        for name in {v[0] for v in variables}:
            b=current[name];values.extend((b[0],b[1],size[0]-b[0]-b[2],size[1]-b[1]-b[3]))
        return np.array(values)
    zero=np.zeros(len(variables));before=objective(zero)
    solved=minimize(objective,zero,bounds=bounds,constraints={'type':'ineq','fun':inside},method='SLSQP',
        options={'maxiter':settings['solver_iterations'],'ftol':1e-10})
    after=objective(solved.x)
    if not np.isfinite(solved.x).all() or np.min(inside(solved.x),initial=0)<-1e-7 or after>=before-1e-6:
        raise ValueError('No bounded feasible global improvement; retain independent object bests')
    deltas={}
    for (name,axis),delta in zip(variables,solved.x):deltas.setdefault(name,{})[axis]=float(delta)
    return deltas,{'improved':True,'before_objective':before,'after_objective':after,'iterations':int(solved.nit),
        'method':'deterministic bounded SLSQP','iteration_limit':settings['solver_iterations'],'actual_render_required':True}

def _xf(node):
    tag=E.QName(node).localname
    return node.find('p:xfrm',NS) if tag=='graphicFrame' else node.find('p:grpSpPr/a:xfrm' if tag=='grpSp' else 'p:spPr/a:xfrm',NS)

def _apply(nodes,entries,deltas,scales,orders):
    for name,delta in deltas.items():
        mapping=entries[name]['parent_matrix'];local=np.linalg.solve(mapping[:2,:2],np.array([delta.get('x',0),delta.get('y',0)],float))
        off=_xf(nodes[name]).find('a:off',NS)
        for index,axis in enumerate(('x','y')):off.set(axis,str(int(off.get(axis))+round(local[index])))
    for name,factor in scales.items():
        xf=_xf(nodes[name]);off=xf.find('a:off',NS);ext=xf.find('a:ext',NS)
        for axis,key in (('x','cx'),('y','cy')):
            value=int(ext.get(key));new=round(value*factor)
            if new<=0:raise ValueError('Uniform scaling would create an empty native frame')
            off.set(axis,str(int(off.get(axis))+round((value-new)/2)));ext.set(key,str(new))
    for order in orders:
        selected=[nodes[n] for n in order];parent=selected[0].getparent()
        if any(n.getparent() is not parent for n in selected):raise ValueError('Paint-order repair cannot reparent semantic objects')
        indices=sorted(parent.index(n) for n in selected)
        for n in selected:parent.remove(n)
        for i,n in zip(indices,selected):parent.insert(i,n)

def _derive(plan,frames,items,size):
    deltas,proof=solve(plan,frames,items,size) if any(i['operation']=='translate' for i in items) else ({},{'improved':False,'iterations':0})
    scales={};orders=[]
    for item in items:
        name=item['object']
        if item['operation']=='uniform_scale':
            related=[r for r in plan['regions'] if r['objects']==[name]]
            if len(related)!=1 or frames.get(name) is None:raise ValueError('Scale needs one independently source-bound semantic owner')
            source=related[0].get('target_bounds',related[0]['source_bounds']);actual=frames[name];budget=item['max_scale_change']
            if budget>plan['settings']['maximum_scale_change']:raise ValueError('Uniform scale exceeds frozen global bound')
            ideal=math.sqrt(source[2]*source[3]/(actual[2]*actual[3]));factor=min(1+budget,max(1-budget,ideal))
            if abs(factor-1)<1e-5:raise ValueError('No source-supported uniform-scale change is needed')
            scales[name]=factor;proof['improved']=True
        elif item['operation']=='paint_order':
            rules=[r for r in plan['orders'] if name in r['objects']]
            if not rules:raise ValueError('Paint-order change needs an independently frozen source order')
            for r in rules:
                if r['objects'] not in orders:orders.append(r['objects'])
            proof['improved']=True
    return deltas,scales,orders,proof

def _solver_plan(plan,entries):
    result=copy.deepcopy(plan);descendants={n:[] for n in entries}
    for name,entry in entries.items():
        parent=entry.get('parent_name')
        while parent:
            descendants[parent].append(name);parent=entries[parent].get('parent_name')
    result['_descendants']=descendants;return result

def execute(task,request):
    from . import agent_runtime as a
    from .global_aesthetic import resolved_plan
    from .boundary_geometry import saved_nodes
    from .source_layout_actions import _xml
    from .native_snapshot import snapshot
    task,state=a._state(task);before=identity(state);baseline=state.get('active_candidate') or state['selected'];plan=resolved_plan(task,state,baseline)
    if not plan or request.get('expected_baseline_sha256')!=baseline['pptx']['sha256'] or not baseline.get('render'):raise ValueError('Global layout needs frozen source targets and exact actual-rendered baseline')
    file=safe_path(task,baseline['pptx']['path']);tree,nodes=_xml(file);items=validate_request(request,set(nodes))
    entries=saved_nodes(file,state['source_size']);frames=frames_from_nodes(entries)
    selected={i['object'] for i in items}
    for name in selected:
        parent=entries[name]['parent_name']
        while parent:
            if parent in selected:raise ValueError('Overlapping parent/child layout writes need one semantic root operation')
            parent=entries[parent]['parent_name']
    strategy=strategy_key(plan,items)
    attempts=state.get('global_layout_attempts',[])
    failures=sum(r.get('reflection',{}).get('status')=='NO_ACTUAL_GAIN' for r in attempts if r.get('strategy')==strategy)
    if failures>=plan['settings']['branch_attempt_limit']:raise ValueError('Global strategy exhausted after actual no-gain reflections; unresolved quality remains unaccepted')
    if obligations(state):raise ValueError('Close every outstanding actual global reflection or exact no-gain rollback before any next strategy')
    from .global_aesthetic import _basis
    reference=state.get('global_aesthetic_result')
    before_global=read_json(safe_path(task,reference['path'])) if reference else None
    if not before_global or digest(safe_path(task,reference['path']))!=reference['sha256'] or before_global.get('basis')!=_basis(state,baseline) or before_global.get('score') is None:raise ValueError('Measure current six-dimensional global quality before bounded optimization')
    branch=identity({'strategy':strategy,'items':items,'baseline':baseline['pptx']['sha256']})
    if any(r['branch']==branch for r in state.get('global_layout_attempts',[])):raise ValueError('Unchanged global action branch already attempted')
    deltas,scales,orders,proof=_derive(_solver_plan(plan,entries),frames,items,state['source_size']);_apply(nodes,entries,deltas,scales,orders)
    # An order permutation affects every member's sibling index. Account for
    # the complete finite write set; each member still keeps intrinsic locks.
    selected |= {n for order in orders for n in order}
    # Intrinsic locks are enforced on actual payloads, not just field names.
    directory=task/'versions'/('global-layout-'+branch[:18]);directory.mkdir(exist_ok=True);output=directory/'drawing.pptx'
    payload=E.tostring(tree,encoding='utf-8',xml_declaration=True,standalone=True)
    if output.exists():
        with ZipFile(output) as z:
            if z.read('ppt/slides/slide1.xml')!=payload:raise ValueError('Uncommitted global artifact differs; preserve it')
    else:
        with ZipFile(file) as z,ZipFile(output,'x',ZIP_DEFLATED,compresslevel=9) as out:
            for info in z.infolist():out.writestr(info,payload if info.filename=='ppt/slides/slide1.xml' else z.read(info.filename))
    from .object_lifecycle import native_facets
    previous=native_facets(file);current=native_facets(output)
    if {n:r['intrinsic'] for n,r in previous.items()}!={n:r['intrinsic'] for n,r in current.items()}:raise ValueError('Global operation changed locked content, icon structure or paint')
    scene=snapshot(task,state,output,read_json(safe_path(task,baseline['scene']['path'])));scene_file=directory/'scene.json';write_json(scene_file,scene)
    candidate=copy.deepcopy(baseline);candidate.update(pptx={'path':output.relative_to(task).as_posix(),'sha256':digest(output)},scene={'path':scene_file.relative_to(task).as_posix(),'sha256':digest(scene_file)},allowed={n:['bbox.left','bbox.top','bbox.width','bbox.height','z_order'] for n in selected})
    candidate['prior_render']=candidate.pop('render');candidate.pop('preview',None);candidate['reason']={'kind':'global_layout_solver','branch':branch}
    record={'branch':branch,'strategy':strategy,'before_global':copy.deepcopy(before_global),'baseline':baseline['pptx']['sha256'],'baseline_artifact':{k:baseline[k] for k in ('pptx','scene','preview','render')},'candidate':candidate['pptx']['sha256'],
        'source_hash':state['source']['sha256'],'plan_hash':plan['compiled_hash'],'items':items,'translations':deltas,'scales':scales,'orders':orders,'objects':sorted(selected),
        'solver':proof,'status':'SAVED_REQUIRES_ACTUAL_RENDER'}
    with writer(task):
        if identity(a._state(task)[1])!=before:raise ValueError('Task changed during global construction; preserve staged artifact')
        state.setdefault('global_layout_attempts',[]).append(record);state['active_candidate']=candidate;state.update(scene=candidate['scene'],stage='host_render',packet=None)
        state.pop('acceptance',None);state.pop('quality_result',None);a._event(task,'finite_global_layout_saved',record);a._save(task,state)
    return record

def obligations(state):
    """Transaction debt persists across strategies and candidate descendants."""
    return [r for r in state.get('global_layout_attempts',[]) if not r.get('rolled_back')
        and r.get('reflection',{}).get('status') in (None,'CURRENT_GLOBAL_OBSERVATIONS_REQUIRED','NO_ACTUAL_GAIN')]

def strategy_key(plan,items):
    return identity({'plan':plan['compiled_hash'],'operations':sorted([
        {'object':i['object'],'operation':i['operation'],'axes':sorted(i.get('axes',[]))} for i in items],key=lambda i:i['object'])})

def confirm_no_native_change(task,record):
    """A verified no-op has no changed geometry to roll back."""
    if record.get('reflection',{}).get('status')!='NO_ACTUAL_GAIN':return False
    before=record['baseline_artifact'];render=safe_path(task,record['reflection']['actual_render']['path'])
    if digest(render)!=record['reflection']['actual_render']['sha256']:raise ValueError('Actual global no-op render changed')
    receipt=read_json(render);after=render.parent.parent/'drawing.pptx';old=safe_path(task,before['pptx']['path'])
    if digest(after)!=record['candidate'] or digest(old)!=before['pptx']['sha256'] or receipt['pptx_hash']!=record['candidate']:
        raise ValueError('Immutable saved global predecessor and attempt required')
    from .object_lifecycle import native_facets
    from .inspect import xml,inventory
    no_native_change=native_facets(old)==native_facets(after) and list(inventory(xml(old))[0])==list(inventory(xml(after))[0])
    import hashlib
    with ZipFile(old) as first,ZipFile(after) as second:
        resources=lambda z:{n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith(('ppt/fonts/','ppt/media/'))}
        no_native_change &= resources(first)==resources(second)
    same_pixels=before['preview']['sha256']==receipt['preview_hash']
    if not no_native_change or not same_pixels:return False
    record['reflection'].update(status='NO_NATIVE_OR_PAINT_CHANGE',gain=False,
        no_op_proof={'before':before['pptx'],'attempt_sha256':record['candidate'],'native_content_placement_and_order_equal':True,'font_media_resources_equal':True,'actual_preview_equal':True},
        reason='Complete native contents, placements, paint order, font/media resources and actual preview equal the predecessor; no mutation exists to roll back. No quality gain claimed.')
    return True


def reflect(state,candidate,global_result,local_result,task=None):
    """Count actual post-render outcomes, across different candidate baselines."""
    for record in state.get('global_layout_attempts',[]):
        if record['candidate']!=candidate['pptx']['sha256'] or record.get('rolled_back'):continue
        before=record['before_global'];score=global_result.get('score')
        if score is None:
            record['reflection']={'status':'CURRENT_GLOBAL_OBSERVATIONS_REQUIRED','actual_candidate':candidate['pptx']['sha256']};continue
        below=[k for k,v in global_result['dimensions'].items() if v is None or v<before['dimensions'][k]-.002]
        gain=score>before['score']+.002 and not below and local_result['passed'] and not any(global_result['hard_vetoes'].values())
        source_order_gain=(bool(record.get('orders')) and all(i['operation']=='paint_order' for i in record['items'])
                           and len(global_result.get('raw',{}).get('paint_order_errors',[]))<len(before.get('raw',{}).get('paint_order_errors',[])))
        record['reflection']={'status':'ACTUAL_GAIN' if gain else 'ACTUAL_SOURCE_ORDER_MET_LOCAL_CHECKS_REQUIRED' if source_order_gain else 'NO_ACTUAL_GAIN','gain':gain,
            'before_score':before['score'],'after_score':score,'regressed_dimensions':below,'local_convergence_preserved':local_result['passed'],
            'actual_preview':candidate['preview']['sha256'],'actual_render':candidate['render'],
            'source_order_constraints_improved':source_order_gain,
            'reason':'Actual same-ruler score improves without dimension/hard/local regression' if gain else
                     'Frozen original paint order now holds; no aesthetic gain claimed and independent local/global acceptance remains required' if source_order_gain else
                     'Predicted optimization did not yield an acceptable actual global improvement'}
        if task is not None:confirm_no_native_change(task,record)

def rollback(task,request):
    from . import agent_runtime as a
    from .global_aesthetic import _basis
    task,state=a._state(task);candidate=state.get('active_candidate') or state['selected']
    if set(request)-{'expected_baseline_sha256','attempt'} or request.get('expected_baseline_sha256')!=candidate['pptx']['sha256']:raise ValueError('Global rollback needs current immutable native identity')
    record=next((r for r in state.get('global_layout_attempts',[]) if r['branch']==request.get('attempt') and r['candidate']==candidate['pptx']['sha256']),None)
    if not record or record.get('reflection',{}).get('status')!='NO_ACTUAL_GAIN':raise ValueError('Only an actually reflected ineffective global transaction can roll back')
    # Execute created only layout changes and retained every intrinsic payload;
    # restoring that exact immediate predecessor retains all earlier local gains.
    previous=copy.deepcopy(candidate);previous.update(copy.deepcopy(record['baseline_artifact']))
    for key in ('pptx','scene','preview','render'):
        if digest(safe_path(task,previous[key]['path']))!=previous[key]['sha256']:raise ValueError('Global rollback predecessor changed')
    from .object_lifecycle import native_facets
    now=native_facets(safe_path(task,candidate['pptx']['path']));before=native_facets(safe_path(task,previous['pptx']['path']))
    if {n:r['intrinsic'] for n,r in now.items()}!={n:r['intrinsic'] for n,r in before.items()}:raise ValueError('Later intrinsic edits cannot be overwritten by a global rollback')
    with writer(task):
        record['rolled_back']=True;state['active_candidate']=previous;state['scene']=previous['scene'];state.update(stage='review',packet=None)
        history=state.get('global_aesthetic_observation_history',[])
        observation=next((r for r in reversed(history) if r.get('basis')==_basis(state,previous)),None)
        if observation:state['global_aesthetic_observations']=copy.deepcopy(observation)
        state.pop('quality_result',None);state.pop('acceptance',None);a._event(task,'ineffective_global_layout_rolled_back',{'branch':record['branch'],'retained_native':previous['pptx']});a._save(task,state)
    return {'status':'PREVIOUS_LOCAL_BEST_COMPOSITION_RETAINED','candidate':previous['pptx'],'actual_render':previous['render'],'whole_loop_required':True}

def guard(task,state,candidate,approved,_chain_only=False):
    from .global_aesthetic import resolved_plan
    from .source_layout_actions import _xml,guard as original_guard
    from .boundary_geometry import saved_nodes
    records={r['candidate']:r for r in state.get('global_layout_attempts',[])};record=records.get(candidate['pptx']['sha256'])
    if not record:return {'passed':False,'objects':[]}
    plan=resolved_plan(task,state,candidate)
    if not plan or record['plan_hash']!=plan['compiled_hash'] or record['source_hash']!=state['source']['sha256']:raise ValueError('Global transaction uses a stale source plan')
    predecessor=record['baseline_artifact'];base=safe_path(task,predecessor['pptx']['path']);new=safe_path(task,candidate['pptx']['path'])
    if digest(base)!=record['baseline']:raise ValueError('Global transaction baseline changed')
    if predecessor['pptx']['sha256']==approved['pptx']['sha256']:prior={'passed':True,'objects':[]}
    elif predecessor['pptx']['sha256'] in records:prior=guard(task,state,predecessor,approved,_chain_only=True)
    else:prior=original_guard(task,state,predecessor,approved,_chain_only=True)
    if not prior['passed']:return {'passed':False,'objects':[],'reason':'Global predecessor does not preserve approved native properties','predecessor_result':prior}
    tree,nodes=_xml(base);entries=saved_nodes(base,state['source_size']);frames=frames_from_nodes(entries)
    deltas,scales,orders,proof=_derive(_solver_plan(plan,entries),frames,record['items'],state['source_size'])
    if deltas!=record['translations'] or scales!=record['scales'] or orders!=record['orders']:raise ValueError('Global action differs from deterministic source-bound solver replay')
    _apply(nodes,entries,deltas,scales,orders);actual,_=_xml(new)
    passed=E.tostring(tree,method='c14n',exclusive=True)==E.tostring(actual,method='c14n',exclusive=True)
    with ZipFile(base) as a,ZipFile(new) as b:passed &= sorted(a.namelist())==sorted(b.namelist()) and all(a.read(n)==b.read(n) for n in a.namelist() if n!='ppt/slides/slide1.xml')
    names=set(prior['objects'])|set(record['objects'])
    while True:
        children={n for n,e in entries.items() if e.get('parent_name') in names}-names
        if not children:break
        names|=children
    return {'passed':bool(passed),'objects':sorted(names),'method':'exact_frozen_global_layout_solver_replay','protected':'All non-layout native fields, fonts, content, geometry and media are byte preserved.'}
