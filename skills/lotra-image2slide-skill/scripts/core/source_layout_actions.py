"""Finite source-relation translation, with exact saved-property protection."""
import copy
import math
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
from .common import digest,identity,safe_path,read_json,write_json,writer
from .mathml import NS

def _xml(file):
    from .inspect import xml,inventory
    tree=xml(file);nodes,duplicates=inventory(tree)
    if duplicates:raise ValueError('Source layout requires unambiguous native owner identities')
    return tree,{k:r['node'] for k,r in nodes.items()}

def _move(node,delta,size,canvas,parent_matrix=None):
    from .native_commit import _sp
    from .boundary_geometry import _transform
    import numpy as np
    if node.tag=='{'+NS['p']+'}grpSp':raise ValueError('Use the existing compound group operator for group translations')
    off=_sp(node).find('a:xfrm/a:off',NS)
    if off is None:raise ValueError('Actual native translation has no saved position')
    if parent_matrix is None:
        parent_matrix=np.diag([size[0]/int(canvas.get('cx')),size[1]/int(canvas.get('cy')),1.])
        for ancestor in reversed(list(node.iterancestors())):
            if ancestor.tag=='{'+NS['p']+'}grpSp':parent_matrix=parent_matrix@_transform(ancestor.find('p:grpSpPr/a:xfrm',NS),True)
    local=np.linalg.solve(parent_matrix[:2,:2],np.array([delta.get('x',0),delta.get('y',0)],float))
    for axis,key,index in (('x','x',0),('y','y',1)):
        off.set(key,str(int(off.get(key))+round(local[index])))

def _body_frame(name,rows,frames):
    """Restore only a simple native body to independently frozen original ink.

    The request cannot supply coordinates. Complex/tail/effect/rotated bodies
    require their own existing source operator instead of a frame substitute.
    """
    related=[r for r in rows if r['kind']=='containment' and r['objects'][1]==name]
    entry=frames.get(name,{})
    if not related or entry.get('preset')!='rect' or entry.get('error') or entry.get('box') is None:
        raise ValueError('Source-body restoration needs a supported simple native rectangle')
    boxes=[r['source_bounds'][name] for r in related]
    if any(r['body']['shape']!='rect' for r in related) or any(b!=boxes[0] for b in boxes):
        raise ValueError('Resolve conflicting original body extents before frame restoration')
    x,y,w,h=boxes[0];stroke=entry['stroke_px']
    if min(w,h)<=stroke:raise ValueError('Original body has no positive stroke-cleared frame')
    return [x+stroke/2,y+stroke/2,w-stroke,h-stroke]

def _branches(items,rows,source_hash):
    from .rule_actions import rule_source
    result={}
    for item in items:
        name=item['object'];related=[r for r in rows if name in r['objects']]
        # Source geometry/cause, not prose, budget, caller order or renamed
        # relation identifiers, determines a finite branch.
        facts=[rule_source(r['id'],{'source_hash':source_hash,'rules':{r['id']:{'kind':'frame','contract':r}}})['measurement'] for r in related]
        basis={'source_hash':source_hash,'object':name,'operation':item.get('operation','translate'),
               'measurements':sorted(facts,key=identity)}
        result[name]=identity(basis)
    return result

def _joint(items,rows,frames,baseline_hash):
    """Bounded deterministic joint translation over fixed actual envelopes."""
    import numpy as np
    from scipy.optimize import minimize
    from .relative_layout import measure
    variables=[];limits=[]
    for item in items:
        if item.get('operation','translate')!='translate':continue
        name=item['object'];axes=item.get('axes',['y']);limit=item.get('max_translation_px',12)
        if (not axes or len(set(axes))!=len(axes) or not set(axes)<={'x','y'} or
                type(limit) not in (int,float) or not math.isfinite(limit) or limit<=0):
            raise ValueError('Finite positive translation budget and distinct axes required')
        if frames[name]['error'] or frames[name]['box'] is None:raise ValueError('Resolve actual owner ink before joint solving')
        for axis in sorted(axes):variables.append((name,axis));limits.append((-float(limit),float(limit)))
    affected=[r for r in rows if set(r['objects'])&{i['object'] for i in items}]
    def patched(values):
        result=copy.deepcopy(frames)
        for (name,axis),delta in zip(variables,values):
            k=0 if axis=='x' else 1;result[name]['box'][k]+=float(delta);result[name]['frame'][k]+=float(delta)
        return result
    def slack(values):
        result=[];current=patched(values)
        for row in affected:
            observed=measure(row,current)
            if observed['status']=='required_unmeasured':raise ValueError('Every joint source relationship needs measured owners')
            key={'separation':'gap_px','alignment':'anchor_offset_px','containment':'clearance_px','intentional_overlap':'paint_envelope_overlap_px2'}[row['kind']]
            value=observed['values'][key];lo,hi=row['interval'];reserve=min(.25,(hi-lo)/4)
            result.extend((value-lo-reserve,hi-reserve-value))
            if observed['values'].get('correct_paint_order',1)!=1:result.append(-1.)
        return np.asarray(result,float)
    zero=np.zeros(len(variables))
    if not variables:
        if np.min(slack(zero),initial=0)<-1e-7:raise ValueError('Source body restoration alone does not satisfy all affected relations')
        return {},[],affected
    # Signed containment is the minimum over four sides. At a horizontal
    # limiting side its y derivative is flat, even when a feasible vertical
    # solution exists. Use one additional original-owned anchor seed; never a
    # random restart, candidate registration or caller-supplied coordinate.
    anchored=[]
    for (name,axis),(lo,hi) in zip(variables,limits):
        k=0 if axis=='x' else 1
        targets=[r['source_bounds'][name][k]-frames[name]['box'][k] for r in affected if name in r['objects']]
        anchored.append(min(hi,max(lo,float(np.median(targets)))))
    starts=[zero]
    if not np.allclose(zero,anchored,rtol=0,atol=1e-9):starts.append(np.asarray(anchored,float))
    feasible=[];iterations=0
    for start in starts:
        attempt=minimize(lambda x:float(x@x),start,jac=lambda x:2*x,bounds=limits,
            constraints={'type':'ineq','fun':slack},method='SLSQP',options={'maxiter':128,'ftol':1e-9})
        iterations+=int(attempt.nit)
        if np.isfinite(attempt.x).all() and np.min(slack(attempt.x),initial=0)>=-1e-6:feasible.append(attempt)
    if not feasible:
        raise ValueError('No joint bounded source translation meets every affected relationship; no candidate written')
    solved=min(feasible,key=lambda r:(float(r.x@r.x),tuple(r.x)))
    translations={}
    for (name,axis),delta in zip(variables,solved.x):translations.setdefault(name,{})[axis]=float(delta)
    decisions=[{'object':n,'baseline_hash':baseline_hash,'source_delta_px':d,'status':'JOINT_BOUNDED_TRANSLATION_PROPOSAL',
        'relation_ids':[r['id'] for r in affected if n in r['objects']],
        'solver':{'method':'deterministic SLSQP','iteration_limit_per_start':128,'starts':len(starts),'iterations':iterations,'sampling_reserve_px':.25}} for n,d in translations.items()]
    return translations,decisions,affected

def guard(task,state,candidate,approved,_chain_only=False):
    """Reconstruct finite source-text/layout corrections from approved bytes.

    Exact node payloads are checked, not a caller-supplied list of exceptions.
    Source contracts/intervals, committed baselines and native resources bind
    each action. Source text corrections are independently checked elsewhere.
    """
    if any(r['candidate']==candidate['pptx']['sha256'] for r in state.get('source_target_attempts',[])):
        from .target_actions import guard as target_guard
        return target_guard(task,state,candidate,approved,_chain_only=_chain_only)
    if any(r['candidate']==candidate['pptx']['sha256'] for r in state.get('neighbor_repair_attempts',[])):
        from .neighbor_actions import guard as neighbor_guard
        return neighbor_guard(task,state,candidate,approved,_chain_only=_chain_only)
    if any(r['candidate']==candidate['pptx']['sha256'] for r in state.get('global_layout_attempts',[])):
        from .global_layout_actions import guard as global_guard
        return global_guard(task,state,candidate,approved,_chain_only=_chain_only)
    if any(r['candidate']==candidate['pptx']['sha256'] for r in state.get('object_rollback_attempts',[])):
        from .object_lifecycle import rollback_guard
        return rollback_guard(task,state,candidate,approved)
    if any(r['candidate']==candidate['pptx']['sha256'] for r in state.get('connection_attempts',[])):
        from .connection_geometry import guard as connection_guard
        return connection_guard(task,state,candidate,approved,_chain_only=_chain_only)
    if any(r['candidate']==candidate['pptx']['sha256'] for r in state.get('preview_resource_attempts',[])):
        from .preview_resource_actions import guard as preview_guard
        return preview_guard(task,state,candidate,approved)
    if any(r['candidate']==candidate['pptx']['sha256'] for r in state.get('source_structure_attempts',[])):
        from .source_structure_actions import guard as structure_guard
        return structure_guard(task,state,candidate,approved,_chain_only=_chain_only)
    old_file=safe_path(task,approved['pptx']['path']);new_file=safe_path(task,candidate['pptx']['path'])
    old_tree,old=_xml(old_file);current_tree,current=_xml(new_file);ledger=state.get('source_layout_attempts',[]);by_candidate={r['candidate']:r for r in ledger}
    chain=[];cursor=candidate['pptx']['sha256'];seen=set()
    # A text-only predecessor can occur before the first layout operation, or
    # be the sole complete finite correction under the same exact guard.
    while cursor in by_candidate:
        if cursor in seen:raise ValueError('Cyclic source layout evidence')
        seen.add(cursor);record=by_candidate[cursor];chain.insert(0,record);cursor=record['baseline']
    if not chain and cursor==approved['pptx']['sha256']:return {'passed':False,'objects':[]}
    allowed_predecessors={approved['pptx']['sha256']}|{r['candidate'] for r in state.get('source_text_attempts',[]) if r['baseline']==approved['pptx']['sha256']}
    if cursor not in allowed_predecessors:return {'passed':False,'objects':[],'reason':'Layout chain is not based on the protected approved artwork'}
    from .relative_layout import contracts
    current_rows=contracts(task,state)
    from .relative_layout import historical_raw
    raw_rows=[historical_raw(r) for r in current_rows]
    live={r['id']:{identity(r),identity(raw)} for r,raw in zip(current_rows,raw_rows)}
    from .inspect import inventory
    expected_tree=copy.deepcopy(old_tree);index,duplicates=inventory(expected_tree)
    expected={n:r['node'] for n,r in index.items()};names=set()
    if cursor!=approved['pptx']['sha256']:
        predecessor=next(r for r in state['source_text_attempts'] if r['candidate']==cursor and r['baseline']==approved['pptx']['sha256'])
        uid=predecessor['unit'];unit=state['quality']['units'][uid]
        from .source_reading import confirmed_record
        from .source_text_actions import expected_node
        reading=confirmed_record(task,state,unit)
        policy=next((r for r in state.get('quality_intent',{}).get('items',[]) if r.get('appearance_target')=='source_content' and r.get('source_content_correction',{}).get('unit')==uid),None)
        if not reading or not policy or policy['source_content_correction']['reading_hash']!=identity(reading):
            raise ValueError('Layout predecessor requires the independently frozen original text constructor')
        name=unit['objects'][0];replacement=expected_node(expected[name],reading)
        expected[name].getparent().replace(expected[name],replacement);expected[name]=replacement;names.add(name)
    from .boundary_geometry import saved_nodes
    parents=saved_nodes(old_file,state['source_size'])
    from .relative_layout import painted_bounds
    from .frame_actions import _position
    approved_frames=painted_bounds(old_file,state['source_size']);live_rows=current_rows
    with ZipFile(old_file) as z:canvas=E.fromstring(z.read('ppt/presentation.xml')).find('p:sldSz',NS)
    for record in chain:
        if record.get('source_hash')!=state['source']['sha256'] or any(v not in live.get(k,set()) for k,v in record['source_contracts'].items()):
            raise ValueError('Source layout action no longer matches its frozen original relationships')
        for name,frame in record.get('source_body_frames',{}).items():
            replay_rows=[r if record['source_contracts'].get(r['id'])==identity(r) else raw for r,raw in zip(current_rows,raw_rows)]
            derived=_body_frame(name,replay_rows,approved_frames)
            if frame!=derived:raise ValueError('Saved body target differs from the frozen original-derived constructor')
            _position({**parents[name],'node':expected[name]},derived);names.add(name)
        for name,delta in record['translations'].items():_move(expected[name],delta,state['source_size'],canvas,parents[name]['parent_matrix']);names.add(name)
    # Compare the reconstructed complete slide, not just directly moved nodes.
    # Parent transforms, siblings, order and slide metadata are protected too.
    passed=set(old)==set(current) and E.tostring(expected_tree,method='c14n',exclusive=True)==E.tostring(current_tree,method='c14n',exclusive=True)
    with ZipFile(old_file) as a,ZipFile(new_file) as b:
        passed &= sorted(a.namelist())==sorted(b.namelist()) and all(a.read(n)==b.read(n) for n in a.namelist() if n!='ppt/slides/slide1.xml')
    return {'passed':bool(passed),'objects':sorted(names),'method':'exact_source_solver_translation_constructor',
        'protected':'Translation preserves content, fonts, geometry and paint. Explicit source-body restoration changes only its original-derived native frame. All other resources and owners remain protected.',
        'actions':[r['branch'] for r in chain]}

def execute(task,request):
    from . import agent_runtime as a
    from .relative_layout import contracts,painted_bounds,evaluate_contract,measure
    from .native_snapshot import snapshot
    task,state=a._state(task);before=identity(state);baseline=state.get('active_candidate') or state.get('selected')
    if not baseline or request.get('expected_baseline_sha256')!=baseline['pptx']['sha256'] or not baseline.get('render'):
        raise ValueError('Source layout requires the exact actually rendered native baseline')
    items=request.get('items',[])
    if set(request)-{'expected_baseline_sha256','items'} or not 1<=len(items)<=8 or len({r.get('object') for r in items})!=len(items) or any(set(r)-{'object','axes','max_translation_px','operation'} for r in items):
        raise ValueError('Use one bounded distinct object/axis/budget batch; host coordinates and XML are not inputs')
    if any(i.get('operation','translate') not in ('translate','source_body_frame') for i in items):raise ValueError('Unknown finite source layout operation')
    rows=contracts(task,state)
    file=safe_path(task,baseline['pptx']['path']);tree,nodes=_xml(file)
    with ZipFile(file) as z:canvas=E.fromstring(z.read('ppt/presentation.xml')).find('p:sldSz',NS)
    frames=painted_bounds(file,state['source_size'])
    for row in rows:
        observed=evaluate_contract(task,state,baseline,row,frames)
        for proof in observed.get('ink_evidence',[]):frames[proof['object']].update(box=list(proof['paint_bounds']),error=None)
    branches=_branches(items,rows,state['source']['sha256']);attempts=state.setdefault('source_layout_attempts',[])
    for name,key in branches.items():
        prior=[]
        for record in attempts:
            known=record.get('branches')
            if known is None:
                legacy=[{'object':d['object']} for d in record.get('decisions',[])]
                old_rows=[r for r in rows if r['id'] in record.get('source_contracts',{})]
                known=_branches(legacy,old_rows,state['source']['sha256'])
            if known.get(name)==key:prior.append(record)
        if len(prior)>=2 or any(r['baseline']==baseline['pptx']['sha256'] for r in prior):
            raise ValueError('Finite source layout branch exhausted or unchanged; do not repeat it')
    source_frames={};from .boundary_geometry import saved_nodes
    from .frame_actions import _position
    saved=saved_nodes(file,state['source_size'])
    for item in items:
        if item.get('operation')!='source_body_frame':continue
        name=item['object'];target=_body_frame(name,rows,frames);old=frames[name]['frame'];budget=item.get('max_translation_px',12)
        if type(budget) not in (int,float) or not math.isfinite(budget) or budget<=0:
            raise ValueError('Original-derived body frame exceeds the explicit finite change budget')
        change=max(abs(a-b) for a,b in zip(target,old))
        # Floating subtraction may put an exact legal boundary a few ULPs
        # above its budget. Only tolerate numerical roundoff, capped below
        # one quarter of the smallest actual native EMU in source pixels.
        quantum=min(state['source_size'][0]/int(canvas.get('cx')),state['source_size'][1]/int(canvas.get('cy')))
        roundoff=min(quantum/4,32*math.ulp(max(1.,abs(change),float(budget))))
        if change-budget>roundoff:
            raise ValueError('Original-derived body frame exceeds the explicit finite change budget')
        _position({**saved[name],'node':nodes[name]},target);source_frames[name]=target
        stroke=frames[name]['stroke_px'];frames[name].update(frame=target,box=[target[0]-stroke/2,target[1]-stroke/2,target[2]+stroke,target[3]+stroke])
    translations,decisions,affected=_joint(items,rows,frames,baseline['pptx']['sha256'])
    for name,delta in translations.items():
        _move(nodes[name],delta,state['source_size'],canvas)
        for axis,value in delta.items():
            k=0 if axis=='x' else 1;frames[name]['box'][k]+=value;frames[name]['frame'][k]+=value
    if any(measure(r,frames)['status']!='minimum_met' for r in affected):raise ValueError('Combined solver translations conflict; no candidate written')
    with ZipFile(file) as z:unchanged=E.tostring(tree,method='c14n',exclusive=True)==E.tostring(E.fromstring(z.read('ppt/slides/slide1.xml')),method='c14n',exclusive=True)
    if unchanged:raise ValueError('No native source-layout change is needed; do not create a cyclic zero-action candidate')
    branch=identity(sorted(branches.values()))
    directory=task/'versions'/('layout-'+identity({'baseline':baseline['pptx'],'translations':translations,'source_body_frames':source_frames})[:16]);output=directory/'drawing.pptx';recovered=None
    payload=E.tostring(tree,encoding='utf-8',xml_declaration=True,standalone=True)
    if directory.exists():
        if not output.is_file():raise ValueError('Uncommitted source-layout directory has no recoverable native artifact')
        with ZipFile(file) as original_archive,ZipFile(output) as recovered_archive:
            valid=sorted(original_archive.namelist())==sorted(recovered_archive.namelist()) and all(recovered_archive.read(n)==(payload if n=='ppt/slides/slide1.xml' else original_archive.read(n)) for n in original_archive.namelist())
        if not valid:raise ValueError('Existing source-layout artifact differs; preserve it and reject recovery')
        recovered={'path':output.relative_to(task).as_posix(),'sha256':digest(output),'method':'exact ZIP payload and deterministic source constructor recovery'}
    else:
        directory.mkdir()
        with ZipFile(file) as z,ZipFile(output,'x',ZIP_DEFLATED,compresslevel=9) as out:
            for info in z.infolist():out.writestr(info,payload if info.filename=='ppt/slides/slide1.xml' else z.read(info.filename))
    scene=snapshot(task,state,output,read_json(safe_path(task,baseline['scene']['path'])));scene_path=directory/('scene-'+identity(scene)[:16]+'.json')
    if scene_path.exists() and read_json(scene_path)!=scene:raise ValueError('Recovered native snapshot differs; preserve it')
    if not scene_path.exists():write_json(scene_path,scene)
    record={'branch':branch,'branches':branches,'baseline':baseline['pptx']['sha256'],'candidate':digest(output),'source_hash':state['source']['sha256'],
        'source_contracts':{r['id']:identity(r) for r in affected},'translations':translations,'source_body_frames':source_frames,'decisions':decisions,'status':'SAVED_REQUIRES_ACTUAL_RENDER'}
    if recovered:record['recovered_uncommitted_artifact']=recovered
    candidate=copy.deepcopy(baseline);candidate.update(pptx={'path':output.relative_to(task).as_posix(),'sha256':digest(output)},scene={'path':scene_path.relative_to(task).as_posix(),'sha256':digest(scene_path)})
    candidate['prior_render']=candidate.pop('render');candidate.pop('preview',None);candidate['allowed']={n:['bbox.'+('left' if a=='x' else 'top') for a in d] for n,d in translations.items()}
    for name in source_frames:candidate['allowed'][name]=['bbox.left','bbox.top','bbox.width','bbox.height']
    candidate['reason']={'kind':'source_solver_layout','branch':branch}
    with writer(task):
        if identity(a._state(task)[1])!=before:raise ValueError('Task changed during source layout construction; preserved uncommitted output')
        attempts.append(record);state['active_candidate']=candidate;state['scene']=candidate['scene'];state.update(stage='host_render',packet=None)
        state.pop('acceptance',None);state.pop('quality_result',None);a._event(task,'source_relation_native_translation_saved',record);a._save(task,state)
    return record
