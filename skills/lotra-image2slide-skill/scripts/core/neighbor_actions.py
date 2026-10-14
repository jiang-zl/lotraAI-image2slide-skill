"""Bounded rigid pose repair over measured paint, with exact native replay.

The host chooses movable roles and axes. It cannot supply coordinates or
change source tolerances. The solver preserves all incident source predicates,
including ancestors and cross-root neighbors, before writing a candidate.
"""
import copy,math
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import numpy as np
from lxml import etree as E
from shapely.affinity import translate
from shapely.ops import unary_union
from scipy.optimize import minimize
from .common import identity,digest,read_json,write_json,safe_path,writer
from .mathml import NS
from . import neighbor_contracts as nc,neighbor_geometry as ng

VERSION='neighbor-rigid-repair-1'


def _validate(request):
    if set(request)-{'expected_baseline_sha256','source_hash','items'}:
        raise ValueError('Neighbor repair accepts roles/axes/budgets, never coordinates or new tolerances')
    items=request.get('items',[])
    if not 1<=len(items)<=8 or len({i['role'] for i in items})!=len(items):
        raise ValueError('One finite batch of distinct movable roles required')
    for item in items:
        axes=item.get('axes',['x','y']);budget=item.get('max_translation_px',4.)
        if set(item)-{'role','axes','max_translation_px'} or not axes or len(set(axes))!=len(axes) or not set(axes)<={'x','y'} or type(budget) not in (int,float) or not math.isfinite(budget) or not 0<budget<=32:
            raise ValueError('Finite positive budget (at most 32 source pixels) and distinct x/y axes required')
    return items


def solve(v,native,size,items):
    source=nc.source_rows(v);actual,errors=nc.actual_rows(v,native)
    if errors:raise ValueError('Missing measured paint before solving: '+repr(errors[:4]))
    roots=[];variables=[];bounds=[]
    for item in items:
        names=source[item['role']]['objects']
        if len(names)!=1:raise ValueError('Use one actual native root per rigid role')
        root=names[0]
        if root in roots:raise ValueError('Duplicate native movable root')
        roots.append(root)
        for axis in sorted(item.get('axes',['x','y'])):
            variables.append((root,axis));budget=float(item.get('max_translation_px',4.));bounds.append((-budget,budget))
    def descendants(root):
        names={root}
        while True:
            extra={n for n,r in native.items() if r.get('parent') in names}-names
            if not extra:return names
            names|=extra
    scopes={r:descendants(r) for r in roots}
    if any(scopes[a]&scopes[b] for i,a in enumerate(roots) for b in roots[i+1:]):
        raise ValueError('Movable native subtrees cannot overlap')
    changed=set().union(*scopes.values());affected_roles=set()
    affected_groups={name for name,row in native.items() if row.get('method')=='DESCENDANT_PAINT_UNION' and descendants(name)&changed}
    for role in actual:
        if set(source[role]['objects'])&changed or any(changed&descendants(n) for n in source[role]['objects']):affected_roles.add(role)
    # Derive the check closure independently from both source and actual range
    # sets. Retained pairs are supplied by the immutable current registry below.
    pairs=nc.indexed(source,size)|nc.indexed(actual,size,source)|{tuple(sorted(p)) for p in v.get('confirmed_pairs',[])}
    pairs|={tuple(c['objects']) for c in v.get('_retained_contracts',[])}
    inventory_hash=identity({k:x for k,x in v.items() if not k.startswith('_')})
    contracts=[nc.expected_contract(source[a],source[b],v,inventory_hash)
               for a,b in sorted(pairs) if {a,b}&affected_roles]
    failing_gap=set()
    for contract in contracts:
        a,b=contract['objects'];gap=nc.relation(actual[a],actual[b])['gap'];lo,hi=contract['target']['gap_interval']
        if not lo-1e-9<=gap<=hi+1e-9:failing_gap.add(contract['id'])
    def geometries(values):
        deltas={root:[0.,0.] for root in roots}
        for (root,axis),value in zip(variables,values):deltas[root][0 if axis=='x' else 1]=float(value)
        out={n:{**r} for n,r in native.items()}
        for root,names in scopes.items():
            dx,dy=deltas[root]
            for name in names:
                if not out[name].get('nonpaint'):out[name]['geometry']=translate(native[name]['geometry'],dx,dy)
        # Recompute ancestor paint unions; translating a child can alter its
        # parent's centroid and every relation to external objects.
        for name,row in reversed(list(out.items())):
            if name not in affected_groups:continue
            children=[r['geometry'] for r in out.values() if r.get('parent')==name and not r.get('nonpaint')]
            out[name]['geometry']=unary_union(children)
        return nc.actual_rows(v,out)[0]
    def slack(values,reserve=.05):
        current=geometries(values);s=[]
        for contract in contracts:
            a,b=contract['objects'];measured=nc.relation(current[a],current[b]);target=contract['target']
            for value,(lo,hi) in zip(measured['vector'],target['vector_intervals']):
                s.extend((value-lo,hi-value))
            for key,interval in (('gap','gap_interval'),('overlap','overlap_interval')):
                lo,hi=target[interval];value=measured[key]
                margin=min(reserve,(hi-lo)/4) if key=='gap' and contract['id'] in failing_gap else 0.
                s.extend((value-lo-margin,hi-margin-value))
            if target.get('required_containment') and not measured[target['required_containment']]:s.append(-1.)
            if target['layer_required'] and measured['layer']!=target['source_relation']['layer']:s.append(-1.)
        return np.asarray(s,float)
    zero=np.zeros(len(variables))
    if np.min(slack(zero,0),initial=0)>=-1e-8:raise ValueError('No failing incident predicate: no zero-action revision')
    # Original centroid displacement is the only additional seed; no random
    # restarts, caller coordinates or registration of the output to the source.
    seed=[]
    for (root,axis),(lo,hi) in zip(variables,bounds):
        role=next(i['role'] for i in items if source[i['role']]['objects']==[root]);k=0 if axis=='x' else 1
        delta=list(source[role]['geometry'].centroid.coords)[0][k]-list(actual[role]['geometry'].centroid.coords)[0][k]
        seed.append(float(np.clip(delta,lo,hi)))
    starts=[zero,np.asarray(seed,float)] if not np.allclose(zero,seed) else [zero];feasible=[]
    for start in starts:
        result=minimize(lambda x:float(x@x),start,jac=lambda x:2*x,bounds=bounds,
            constraints={'type':'ineq','fun':slack},method='SLSQP',options={'maxiter':96,'ftol':1e-10})
        if np.isfinite(result.x).all() and np.min(slack(result.x),initial=0)>=-1e-6:feasible.append(result)
    if not feasible:
        # Contact/containment distances can have flat zero derivatives. Use
        # a finite coordinate seed set inside the same budget, then bisection
        # along a verified feasible ray. These seeds do not alter constraints.
        from types import SimpleNamespace
        probes=[]
        for k,(lo,hi) in enumerate(bounds):
            for value in (lo,lo/2,hi/2,hi):
                probe=zero.copy();probe[k]=value;probes.append(probe)
        probes.extend(np.array([bound[k] for bound in bounds]) for k in (0,1))
        for probe in probes:
            if np.min(slack(probe),initial=0)<-1e-7:continue
            lo=0.;hi=1.
            for _ in range(40):
                middle=(lo+hi)/2
                if np.min(slack(probe*middle),initial=0)>=-1e-7:hi=middle
                else:lo=middle
            feasible.append(SimpleNamespace(x=probe*hi))
    if not feasible:raise ValueError('No bounded rigid translation satisfies every incident source predicate; original reidentification/reconstruction required')
    best=min(feasible,key=lambda r:(float(r.x@r.x),tuple(r.x)));translations={}
    for (root,axis),value in zip(variables,best.x):translations.setdefault(root,{})[axis]=float(value)
    return {'translations':translations,'affected_roles':sorted(affected_roles),'check_set':sorted(c['id'] for c in contracts),
            'solver':{'method':'deterministic bounded SLSQP plus finite coordinate/ray fallback','starts':len(starts),'maxiter_per_start':96,'fallback_seeds_max':4*len(variables)+2,'ray_iterations':40,'reserve_px':.05},
            'write_set':sorted(changed)}


def _payload(file,size,translations):
    from .source_layout_actions import _xml
    from .boundary_geometry import saved_nodes
    tree,nodes=_xml(file);saved=saved_nodes(file,size)
    with ZipFile(file) as z:canvas=E.fromstring(z.read('ppt/presentation.xml')).find('p:sldSz',NS)
    for name,delta in translations.items():
        node=nodes[name];tag='p:grpSpPr' if saved[name]['tag']=='grpSp' else 'p:spPr'
        off=node.find('p:xfrm/a:off' if saved[name]['tag']=='graphicFrame' else tag+'/a:xfrm/a:off',NS)
        if off is None:raise ValueError('Movable root has no saved native position')
        local=np.linalg.solve(saved[name]['parent_matrix'][:2,:2],np.array([delta.get('x',0),delta.get('y',0)],float))
        for k,key in enumerate(('x','y')):off.set(key,str(int(off.get(key))+round(local[k])))
    return E.tostring(tree,encoding='utf-8',xml_declaration=True,standalone=True)


def _same_zip(before,after,payload):
    with ZipFile(before) as a,ZipFile(after) as b:
        return sorted(a.namelist())==sorted(b.namelist()) and all(b.read(n)==(payload if n=='ppt/slides/slide1.xml' else a.read(n)) for n in a.namelist())


def execute(task,request):
    from . import agent_runtime as a
    from .native_snapshot import snapshot
    task,state=a._state(task);items=_validate(request);baseline=state.get('active_candidate') or state.get('selected')
    if not baseline or not baseline.get('render') or request.get('expected_baseline_sha256')!=baseline['pptx']['sha256'] or request.get('source_hash')!=state['source']['sha256']:
        raise ValueError('Use exact current native/render/original identities')
    v=nc._load(task,state);native,errors=ng.read(task,state,baseline,state.get('neighbor_mattes'))
    if errors:raise ValueError('Capture every missing actual owner before repair')
    registry=read_json(safe_path(task,state['neighbor_registry']['path']));v['_retained_contracts']=registry['contracts']
    proposal=solve(v,native,state['source_size'],items);before=safe_path(task,baseline['pptx']['path']);payload=_payload(before,state['source_size'],proposal['translations'])
    branch=identity({'source':state['neighbor_source'],'items':items})
    attempts=[r for r in state.get('neighbor_repair_attempts',[]) if r['branch']==branch]
    if len(attempts)>=2 or any(r['baseline']['pptx']['sha256']==baseline['pptx']['sha256'] for r in attempts):raise ValueError('Finite unchanged repair branch exhausted')
    contract={'schema':VERSION,'source_hash':state['source']['sha256'],'source_inventory':state['neighbor_source'],'registry':state['neighbor_registry'],
              'baseline':copy.deepcopy(baseline),'baseline_mattes':copy.deepcopy(state.get('neighbor_mattes',{})),'request':request,'proposal':proposal}
    folder=task/'versions'/('neighbor-'+identity(contract)[:16]);folder.mkdir(exist_ok=True);output=folder/'drawing.pptx'
    if output.exists():
        if not _same_zip(before,output,payload):raise ValueError('Uncommitted neighbor output differs from exact replay')
    else:
        with ZipFile(before) as z,ZipFile(output,'x',ZIP_DEFLATED,compresslevel=9) as out:
            for info in z.infolist():out.writestr(info,payload if info.filename=='ppt/slides/slide1.xml' else z.read(info.filename))
    scene=snapshot(task,state,output,read_json(safe_path(task,baseline['scene']['path'])));scene_file=folder/'scene.json';write_json(scene_file,scene)
    contract_file=folder/'contract.json';write_json(contract_file,contract)
    candidate=copy.deepcopy(baseline);candidate.update(pptx=a._file(task,output),scene=a._file(task,scene_file),allowed={n:['bbox.'+('left' if axis=='x' else 'top') for axis in delta] for n,delta in proposal['translations'].items()})
    candidate['prior_render']=candidate.pop('render');candidate.pop('preview',None);candidate['reason']={'kind':VERSION,'contract':a._file(task,contract_file)}
    from .semantic_composition import guard_saved
    candidate['semantic_composition_guard']=guard_saved(task,state,output)
    record={'schema':VERSION,'branch':branch,'candidate':candidate['pptx']['sha256'],'baseline':copy.deepcopy(baseline),'contract':a._file(task,contract_file),'proposal':proposal,'status':'SAVED_REQUIRES_ACTUAL_RENDER_AND_ALL_INCIDENT_RECHECK'}
    with writer(task):
        state.setdefault('neighbor_repair_attempts',[]).append(record);state.update(active_candidate=candidate,scene=candidate['scene'],stage='host_render',packet=None)
        state.pop('acceptance',None);state.pop('quality_result',None);a._save(task,state)
    return record


def guard(task,state,candidate,approved,_chain_only=False):
    record=next((r for r in state.get('neighbor_repair_attempts',[]) if r['candidate']==candidate['pptx']['sha256']),None)
    if not record:return {'passed':False,'objects':[],'reason':'Missing finite neighbor transaction'}
    ref=record['contract'];file=safe_path(task,ref['path'])
    if digest(file)!=ref['sha256']:raise ValueError('Neighbor transaction contract changed')
    contract=read_json(file);baseline=contract['baseline'];original=read_json(safe_path(task,contract['source_inventory']['path']))
    if digest(safe_path(task,contract['source_inventory']['path']))!=contract['source_inventory']['sha256'] or original['source_hash']!=state['source']['sha256']:raise ValueError('Wrong frozen original neighbor inventory')
    original['_retained_contracts']=read_json(safe_path(task,contract['registry']['path']))['contracts']
    native,errors=ng.read(task,state,baseline,contract['baseline_mattes'])
    if errors:raise ValueError('Baseline paint measurement no longer executable')
    replay=solve(original,native,state['source_size'],_validate(contract['request']))
    if identity(replay)!=identity(contract['proposal']):raise ValueError('Neighbor translation differs from deterministic source solver')
    old=safe_path(task,baseline['pptx']['path']);new=safe_path(task,candidate['pptx']['path'])
    if digest(old)!=baseline['pptx']['sha256'] or digest(new)!=candidate['pptx']['sha256']:raise ValueError('Neighbor native input changed')
    passed=_same_zip(old,new,_payload(old,state['source_size'],replay['translations']))
    prior={'passed':True,'objects':[]}
    if baseline['pptx']['sha256']!=approved['pptx']['sha256']:
        from .source_layout_actions import guard as prior_guard
        prior=prior_guard(task,state,baseline,approved,_chain_only=True);passed &= prior['passed']
    result={'passed':bool(passed),'objects':sorted(set(prior.get('objects',[]))|set(replay['write_set'])),
            'method':VERSION,'contract':ref,'protected':'Every ZIP entry and every native property outside the exact rigid transform equals replay',
            'check_set':replay['check_set'],'source_function_items':prior.get('source_function_items',[])}
    if not _chain_only:
        if not candidate.get('render') or not candidate.get('preview'):result['passed']=False
        # Result acceptance still uses the independently recompiled whole
        # neighbor/assembly gate; prediction is never an executed check.
        result['requires_current_all_neighbor_recheck']=True
    return result


_POSE_PROOFS={}

def verified_pose(task,state,candidate,name,nodes):
    """Separate shape construction from source-constrained rigid placement.

    Only an exact saved transform transaction AND the current whole-neighbor
    result can delegate pose. Arbitrary host coordinates never reach this API.
    Original source-pixel frame checks remain unchanged; this applies to the
    constructor-frame domain, not independently read absolute pixel facts.
    """
    record=next((r for r in state.get('neighbor_repair_attempts',[]) if r['candidate']==candidate['pptx']['sha256']),None)
    if not record:return {'x':0.,'y':0.}
    from .execution_contract import _implementation
    ref=state.get('neighbor_result')
    if not ref:raise ValueError('Current all-neighbor execution required before constructor pose delegation')
    file=safe_path(task,ref['path'])
    if digest(file)!=ref['sha256']:raise ValueError('Pose delegation neighbor receipt changed')
    implementation=_implementation()
    key=identity({'native':candidate['pptx'],'contract':record['contract'],'check':ref,'implementation':implementation})
    if key not in _POSE_PROOFS:
        check=read_json(file)
        if not check.get('passed') or check['execution']['pptx']!=candidate['pptx'] or check['execution']['implementation']!=implementation:
            raise ValueError('Rigid pose needs current successful whole-neighbor checks')
        proof=guard(task,state,candidate,record['baseline'],_chain_only=True)
        if not proof.get('passed'):raise ValueError('Constructor pose differs from exact original-bound finite transform')
        _POSE_PROOFS[key]=True
    delta={'x':0.,'y':0.};by_candidate={r['candidate']:r for r in state['neighbor_repair_attempts']};cursor=record;seen=set()
    while cursor:
        if cursor['candidate'] in seen:raise ValueError('Cyclic rigid pose history')
        seen.add(cursor['candidate']);ancestor=name
        while ancestor:
            if ancestor in cursor['proposal']['translations']:
                for axis,value in cursor['proposal']['translations'][ancestor].items():delta[axis]+=value
            ancestor=nodes.get(ancestor,{}).get('parent_name')
        cursor=by_candidate.get(cursor['baseline']['pptx']['sha256'])
    return delta
