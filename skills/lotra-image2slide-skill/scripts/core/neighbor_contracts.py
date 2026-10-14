"""All-neighbor coverage, immutable predicate compilation and actual execution.

Source interpretation is host evidence. Range discovery and independent
exhaustive coverage audit, required predicates and numerical verdicts are code.
No semantic 'unrelated', root, lock or top-k exemption exists here.
"""
import copy,math
from itertools import combinations
from pathlib import Path
from shapely import wkt
from shapely.geometry import box
from shapely.strtree import STRtree
from .common import read_json,write_json,digest,identity,safe_path,writer
from . import neighbor_geometry as ng

VERSION='all-neighbor-closure-1'
RULE={'long_edge':1000.,'min_radius':4.,'stroke_multiplier':3.,'short_side_fraction':.20,'block_size':128}
PREDICATES=('identity','relative_vector','visible_gap','overlap_containment','layer','current_execution')

def _finite(value):
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        if not math.isfinite(value):raise ValueError('Nonfinite neighbor measurement')
    elif isinstance(value,(list,tuple)):
        for child in value:_finite(child)
    elif isinstance(value,dict):
        for child in value.values():_finite(child)

def validate_rows(rows):
    if not rows or len({r.get('id') for r in rows})!=len(rows):raise ValueError('Nonempty unique source role inventory required')
    for r in rows:
        if not r.get('id') or not r.get('objects') or len(set(r['objects']))!=len(r['objects']):raise ValueError('Stable source role and native mapping required')
        b=r.get('box');_finite(r)
        if not isinstance(b,list) or len(b)!=4 or min(b[2:])<=0:raise ValueError('Unknown/empty conservative role boundary: '+r['id'])
        if not isinstance(r.get('stroke'),(int,float)) or r['stroke']<0:raise ValueError('Finite conservative source stroke upper bound required')
        if not isinstance(r.get('uncertainty_px'),(int,float)) or r['uncertainty_px']<0:raise ValueError('Freeze source localization uncertainty before comparing output')
        if not r.get('source_evidence') or not r.get('measurement_method'):raise ValueError('Source role needs independent interpretation and measurement evidence')
        g=wkt.loads(r['geometry']);ng.serial(g)
        x,y,w,h=b;a,c,d,e=g.bounds
        if a<x-1e-7 or c<y-1e-7 or d>x+w+1e-7 or e>y+h+1e-7:raise ValueError('Bounding envelope does not contain source geometry')

def distance_box(a,b):
    x,y,w,h=a;u,v,s,t=b
    return math.hypot(max(0.,u-x-w,x-u-s),max(0.,v-y-h,y-v-t))

def radius(a,b,scale):
    return max(RULE['min_radius']/scale,RULE['stroke_multiplier']*max(a['stroke'],b['stroke']),
               RULE['short_side_fraction']*min(min(a['box'][2:]),min(b['box'][2:])))

def pair_id(a,b):return 'near:'+identity(sorted((a,b)))[:24]

def indexed(rows,size,floor=None):
    """STRtree range query; deliberately no nearest(), nearest-k or cap."""
    names=sorted(rows);values=[rows[n] for n in names];scale=RULE['long_edge']/max(size)
    geometries=[box(r['box'][0],r['box'][1],r['box'][0]+r['box'][2],r['box'][1]+r['box'][3]) for r in values]
    tree=STRtree(geometries);lookup={id(g):i for i,g in enumerate(geometries)};result=set()
    max_stroke=max(r['stroke'] for r in values)
    floor=floor or {}
    max_source_stroke=max([r['stroke'] for r in floor.values()]+[0.])
    max_short=max([min(r['box'][2:]) for r in floor.values()]+[0.])
    for i,(g,a) in enumerate(zip(geometries,values)):
        reach=max(RULE['min_radius']/scale,RULE['stroke_multiplier']*max(max_stroke,max_source_stroke),
                  RULE['short_side_fraction']*max(min(a['box'][2:]),max_short))
        found=tree.query(g.buffer(reach).envelope)
        for item in found:
            j=int(item) if not hasattr(item,'geom_type') else lookup[id(item)]
            if j<=i:continue
            b=values[j];rr=radius(a,b,scale)
            if a['id'] in floor and b['id'] in floor:rr=max(rr,radius(floor[a['id']],floor[b['id']],scale))
            if distance_box(a['box'],b['box'])<=rr:result.add((a['id'],b['id']))
    return result

def exhaustive(rows,size,floor=None):
    """Independent blocked all-pair enumeration, never reads indexed output."""
    names=sorted(rows);scale=RULE['long_edge']/max(size);floor=floor or {};required=set();total=0;blocks=[]
    for start in range(0,len(names),RULE['block_size']):
        count=0
        for i in range(start,min(start+RULE['block_size'],len(names))):
            a=rows[names[i]]
            for name in names[i+1:]:
                b=rows[name];count+=1;total+=1
                # Independent scalar implementation of the box test.
                aa,bb=a['box'],b['box'];dx=max(0.,aa[0]-bb[0]-bb[2],bb[0]-aa[0]-aa[2]);dy=max(0.,aa[1]-bb[1]-bb[3],bb[1]-aa[1]-aa[3])
                rr=max(4./scale,3.*max(a['stroke'],b['stroke']),.20*min(aa[2],aa[3],bb[2],bb[3]))
                if a['id'] in floor and b['id'] in floor:rr=max(rr,radius(floor[a['id']],floor[b['id']],scale))
                if dx*dx+dy*dy<=rr*rr:required.add((a['id'],b['id']))
        blocks.append({'start':start,'pairs_examined':count,'status':'COMPLETE'})
    if total!=len(names)*(len(names)-1)//2:raise ValueError('Exhaustive neighbor coverage incomplete')
    return required,{'objects':len(names),'all_unordered_pairs':total,'blocks':blocks,'rule':RULE}

def relation(a,b):
    ga,gb=a['geometry'],b['geometry'];ac,bc=ga.centroid,gb.centroid
    intersection=ga.intersection(gb).area
    denom=max(min(ga.area,gb.area),1e-12)
    return {'vector':[bc.x-ac.x,bc.y-ac.y],'gap':ga.distance(gb),'overlap':intersection/denom,
            'a_contains_b':ga.covers(gb),'b_contains_a':gb.covers(ga),'layer':int(a['order']<b['order'])}

def _load(task,state):
    ref=state.get('neighbor_source')
    if not ref:return None
    file=safe_path(task,ref['path'])
    if digest(file)!=ref['sha256']:raise ValueError('Frozen original neighbor inventory changed')
    v=read_json(file)
    if v.get('source_hash')!=state['source']['sha256'] or v.get('source_size')!=state['source_size'] or v.get('rule')!=RULE:raise ValueError('Source neighbor rule/coordinate binding changed')
    validate_rows(v['roles'])
    return v

def source_rows(v):
    return {r['id']:{**r,'geometry':wkt.loads(r['geometry'])} for r in v['roles']}

def actual_rows(v,native):
    from shapely.ops import unary_union
    out={};errors=[];mapped=set()
    for role in v['roles']:
        names=role['objects'];missing=[n for n in names if n not in native or native[n].get('nonpaint')]
        if missing:errors.append({'code':'WRONG_MEASUREMENT_BINDING','role':role['id'],'missing':missing});continue
        pieces=[native[n] for n in names];g=pieces[0]['geometry'] if len(pieces)==1 else unary_union([r['geometry'] for r in pieces]);mapped.update(names)
        out[role['id']]={**role,'geometry':g,'box':ng.box_xywh(g),'stroke':max(r['stroke'] for r in pieces),'order':min(r['order'] for r in pieces),
                         'actual_methods':[r['method'] for r in pieces]}
    unbound={n for n,r in native.items() if not r.get('nonpaint')}-mapped
    if unbound:errors.append({'code':'NATIVE_ROLE_UNBOUND','objects':sorted(unbound)})
    return out,errors

def _target(a,b,override=None):
    values=relation(a,b);u=a['uncertainty_px']+b['uncertainty_px']+2*ng.PRECISION
    target={'vector_intervals':[[p-u,p+u] for p in values['vector']],'gap_interval':[max(0.,values['gap']-u),values['gap']+u],
            'source_relation':values,'uncertainty_px':u,'overlap_interval':[0.,1.],
            'layer_required':bool(values['overlap']>.01 and not set(a['objects'])&set(b['objects']) and
                a['id'] not in b.get('ancestors',[]) and b['id'] not in a.get('ancestors',[]))}
    # Robust topological constraints remain meaningful under measured edge
    # uncertainty: source objects far apart cannot overlap in the output.
    if values['gap']>u:target['overlap_interval']=[0.,0.]
    elif values['overlap']>.99 and a.get('containment_required') and b.get('containment_required'):
        target['required_containment']='a_contains_b' if values['a_contains_b'] else 'b_contains_a' if values['b_contains_a'] else None
    if override:
        if not override.get('source_evidence') or not override.get('measurement_basis'):raise ValueError('An original-specific relation target needs independent source numeric evidence')
        if override.get('layer_required') is False and target['layer_required']:
            raise ValueError('Applicable source overlap layer checking cannot be waived')
        for key in ('vector_intervals','gap_interval','overlap_interval','layer_required','required_containment'):
            if key in override:target[key]=copy.deepcopy(override[key])
        target['specific_source_target']=override
    _finite(target)
    for key in ('gap_interval','overlap_interval'):
        if len(target[key])!=2 or target[key][0]>target[key][1]:raise ValueError('Invalid frozen neighbor interval')
    return target

def expected_contract(a,b,v,inventory_hash=None):
    pid=pair_id(a['id'],b['id']);override=v.get('relations',{}).get(pid)
    target=_target(a,b,override);deps={a['id']:a['objects'],b['id']:b['objects']}
    return {'id':pid,'objects':[a['id'],b['id']],'predicates':[{ 'id':pid+':'+p,'checker':VERSION+':'+p,'dependencies':deps} for p in PREDICATES],
            'target':target,'source_hash':v['source_hash'],'source_inventory_hash':inventory_hash or identity(v),'rule':RULE}

def executed_pairs(task,state,source):
    """An executed transaction's incident set survives later spatial changes.

    Read the frozen contract independently of the current registry and mutable
    status rows. Pair IDs are recovered from that contract's original roles;
    deleting a registry row or moving away cannot delete a required recheck.
    """
    required=set()
    for record in state.get('neighbor_repair_attempts',[]):
        ref=record['contract'];file=safe_path(task,ref['path'])
        if digest(file)!=ref['sha256']:raise ValueError('Executed neighbor contract changed')
        contract=read_json(file)
        if contract['source_hash']!=state['source']['sha256'] or record['proposal']!=contract['proposal']:
            raise ValueError('Executed incident set is not its frozen source transaction')
        original_ref=contract['source_inventory'];original_file=safe_path(task,original_ref['path'])
        if digest(original_file)!=original_ref['sha256']:raise ValueError('Executed original role inventory changed')
        old=source_rows(read_json(original_file));wanted=set(contract['proposal']['check_set'])
        matched={pair_id(aa,bb):(aa,bb) for aa,bb in combinations(sorted(old),2) if pair_id(aa,bb) in wanted}
        if set(matched)!=wanted:raise ValueError('Executed incident set has an unknown original pair')
        for aa,bb in matched.values():
            if any(n not in source or source[n]['objects']!=old[n]['objects'] for n in (aa,bb)):
                raise ValueError('Executed roles require explicit source mapping migration')
            required.add((aa,bb))
    return required


def prepare(task,state,candidate):
    v=_load(task,state)
    if not v:return {'passed':False,'status':'ORIGINAL_NEIGHBOR_INVENTORY_REQUIRED'}
    native,errors=ng.read(task,state,candidate,state.get('neighbor_mattes'));source=source_rows(v);actual,binding_errors=actual_rows(v,native)
    errors+=binding_errors
    if errors:return {'passed':False,'status':'NEIGHBOR_MEASUREMENT_REQUIRED','errors':errors}
    discovered=indexed(source,state['source_size'])|indexed(actual,state['source_size'],source)
    existing=state.get('neighbor_registry')
    retained=set()
    if existing:
        file=safe_path(task,existing['path'])
        if digest(file)!=existing['sha256']:raise ValueError('Neighbor registry changed')
        retained={tuple(r['objects']) for r in read_json(file)['contracts']}
    confirmed={tuple(sorted(r)) for r in v.get('confirmed_pairs',[])}
    retained |= executed_pairs(task,state,source)
    pairs=discovered|retained|confirmed
    if any(set(p)-set(source) for p in pairs):raise ValueError('Retire identities only through explicit source mapping migration')
    inventory_hash=identity(v)
    registry={'schema':VERSION,'source_hash':v['source_hash'],'source_inventory_hash':inventory_hash,'retained_pairs':[list(p) for p in sorted(retained)],
              'contracts':[expected_contract(source[a],source[b],v,inventory_hash) for a,b in sorted(pairs)]}
    file=Path(task)/'source/neighbors'/('registry-'+identity(registry)+'.json');write_json(file,registry)
    state['neighbor_registry']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    return {'passed':True,'status':'NEIGHBOR_PREDICATES_COMPILED','pairs':len(pairs),'registry':state['neighbor_registry']}

def bind(task,request):
    from . import agent_runtime as a
    task,state=a._state(task);v={k:copy.deepcopy(request[k]) for k in ('source_hash','roles')}
    if v['source_hash']!=state['source']['sha256'] or request.get('source_size')!=state['source_size']:raise ValueError('Use the unchanged original and frozen source coordinate transform')
    v.update(schema=VERSION,source_size=state['source_size'],rule=RULE,relations=copy.deepcopy(request.get('relations',{})),confirmed_pairs=request.get('confirmed_pairs',[]),assemblies=request.get('assemblies',[]))
    # Output execution is mutable derived evidence, never an original fact.
    # Keep constructor scope/expected roles in the frozen source inventory.
    proposed={}
    for assembly in v['assemblies']:
        proposed[assembly['id']]={}
        for role,provider in assembly.get('providers',{}).items():
            proposed[assembly['id']][role]={k:provider.pop(k) for k in ('execution_pptx_hash','native_dependency_hash') if k in provider}
            proposed[assembly['id']][role]['objects']=provider['objects']
    validate_rows(v['roles'])
    if state.get('neighbor_source'):
        old=_load(task,state)
        if old!=v:
            if request.get('prior_source_inventory_hash')!=identity(old) or not request.get('revision_evidence'):raise ValueError('Retain predecessor and original findings when revising neighbor facts')
            if {r['id'] for r in old['roles']}-{r['id'] for r in v['roles']}:raise ValueError('Cannot erase an original role to remove failed constraints')
            state.setdefault('neighbor_source_history',[]).append(state['neighbor_source'])
    file=task/'source/neighbors'/('original-'+identity(v)+'.json');write_json(file,v)
    with writer(task):
        state['neighbor_source']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
        candidate=state.get('active_candidate') or state['selected']
        native,errors=ng.read(task,state,candidate,state.get('neighbor_mattes'))
        if errors:raise ValueError('Measure actual owner geometry before binding assembly execution')
        from .assembly_contracts import evaluate
        # Input acknowledgements cannot certify stale current executions.
        initial=evaluate(v['assemblies'],source_rows(v),native,candidate,[],proposed)
        provider_errors=[e for row in initial['items'] for e in row['errors'] if not e['code'].startswith('ASSEMBLY_RELATION_')]
        if provider_errors:raise ValueError('Original assembly binding has insufficient/stale execution: '+repr(provider_errors[:4]))
        _store_execution(task,state,candidate,proposed,{'method':'independently_measured_initial_provider_binding'})
        result=prepare(task,state,state.get('active_candidate') or state['selected']);a._save(task,state)
    return result


def _store_execution(task,state,candidate,providers,proof):
    from .execution_contract import _implementation
    value={'schema':'assembly-execution-1','source_inventory':state['neighbor_source'],'candidate':copy.deepcopy(candidate),
           'providers':providers,'proof':proof,'implementation':_implementation()}
    file=Path(task)/'audits'/('assembly-execution-'+identity(value)+'.json');write_json(file,value)
    if state.get('neighbor_execution'):state.setdefault('neighbor_execution_history',[]).append(state['neighbor_execution'])
    state['neighbor_execution']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    return state['neighbor_execution']


def refresh_execution(task,state,candidate):
    """Refresh current measurement only after an exact finite mutation proof.

    Source contours, role sets, numeric intervals and constructor scopes are
    untouched. A changed artifact without replay cannot inherit completion.
    """
    ref=state.get('neighbor_execution')
    if not ref:raise ValueError('Bind the independently measured initial provider executions first')
    file=safe_path(task,ref['path'])
    if digest(file)!=ref['sha256']:raise ValueError('Assembly execution receipt changed')
    old=read_json(file);v=_load(task,state)
    if old['source_inventory']!=state['neighbor_source']:raise ValueError('Original inventory revision needs explicit provider rebinding')
    proof={'passed':True,'method':'same_exact_native_artifact_current_geometry_recheck'}
    if old['candidate']['pptx']!=candidate['pptx']:
        from .neighbor_actions import guard
        proof=guard(task,state,candidate,old['candidate'],_chain_only=True)
        if not proof.get('passed'):raise ValueError('Changed provider execution lacks an exact finite original-bound mutation proof')
    native,errors=ng.read(task,state,candidate,state.get('neighbor_mattes'))
    if errors:raise ValueError('Current actual provider geometry is incomplete')
    providers={}
    for assembly in v['assemblies']:
        providers[assembly['id']]={}
        for role,p in assembly['providers'].items():
            names=p['objects']
            providers[assembly['id']][role]={'objects':names,'execution_pptx_hash':candidate['pptx']['sha256'],
                'native_dependency_hash':identity({n:{'geometry':native[n]['geometry'].wkt,'order':native[n]['order'],'method':native[n]['method']} for n in names})}
    return {'status':'CURRENT_ASSEMBLY_EXECUTION_REPLAYED','receipt':_store_execution(task,state,candidate,providers,proof)}

def _verdict(contract,measured):
    target=contract['target'];out=[];pid=contract['id']
    def row(name,passed,actual,expected,status=None):out.append({'id':pid+':'+name,'checker':VERSION+':'+name,'passed':bool(passed),'actual':actual,'expected':expected,**({'status':status} if status else {})})
    row('identity',True,measured['bindings'],contract['predicates'][0]['dependencies'])
    row('relative_vector',all(lo-1e-9<=x<=hi+1e-9 for x,(lo,hi) in zip(measured['vector'],target['vector_intervals'])),measured['vector'],target['vector_intervals'])
    lo,hi=target['gap_interval'];row('visible_gap',lo-1e-9<=measured['gap']<=hi+1e-9,measured['gap'],[lo,hi])
    lo,hi=target['overlap_interval'];inside=target.get('required_containment')
    row('overlap_containment',lo-1e-9<=measured['overlap']<=hi+1e-9 and (not inside or measured[inside]),{'overlap':measured['overlap'],'a_contains_b':measured['a_contains_b'],'b_contains_a':measured['b_contains_a']},{'overlap':target['overlap_interval'],'containment':inside})
    required=target['layer_required'];row('layer',not required or measured['layer']==target['source_relation']['layer'],measured['layer'],target['source_relation']['layer'] if required else None,None if required else 'NOT_APPLICABLE_NO_REQUIRED_SOURCE_OCCLUSION')
    row('current_execution',bool(measured['execution_identity']),measured['execution_identity'],'Current saved/native/render/source/code identity')
    return out

def report(task,state,candidate):
    v=_load(task,state)
    if not v:return {'passed':False,'status':'ORIGINAL_NEIGHBOR_INVENTORY_REQUIRED','errors':[{'code':'SOURCE_ROLE_INVENTORY_MISSING'}]}
    native,errors=ng.read(task,state,candidate,state.get('neighbor_mattes'));source=source_rows(v);actual,binding_errors=actual_rows(v,native)
    errors=[{'code':'MEASUREMENT_MISSING',**r} for r in errors]+binding_errors
    if errors:return {'passed':False,'status':'NEIGHBOR_INPUT_INCOMPLETE','errors':errors}
    reference,coverage=exhaustive(source,state['source_size']);current,current_coverage=exhaustive(actual,state['source_size'],source)
    reference |= current|{tuple(sorted(p)) for p in v.get('confirmed_pairs',[])}|executed_pairs(task,state,source)
    ref=state.get('neighbor_registry')
    if not ref:return {'passed':False,'status':'NEIGHBOR_REGISTRY_MISSING','errors':[{'code':'PREDICATE_MISSING'}]}
    f=safe_path(task,ref['path'])
    if digest(f)!=ref['sha256']:raise ValueError('Changed neighbor registry')
    registry=read_json(f);contracts=registry['contracts'];pairs=[tuple(c['objects']) for c in contracts]
    retained={tuple(p) for p in registry.get('retained_pairs',[])};reference|=retained
    if len(set(pairs))!=len(pairs):errors.append({'code':'DUPLICATE_NEIGHBOR_PAIR'})
    for p in sorted(reference-set(pairs)):errors.append({'code':'NEIGHBOR_PAIR_MISSING','objects':list(p),'distance_source_px':distance_box(source[p[0]]['box'],source[p[1]]['box']),'radius_source_px':radius(source[p[0]],source[p[1]],1000/max(state['source_size']))})
    from .execution_contract import _implementation
    execution={'source':state['source'],'source_inventory':state['neighbor_source'],'registry':state['neighbor_registry'],'matte_basis':identity(state.get('neighbor_mattes')),'pptx':candidate['pptx'],'render':candidate.get('render'),'preview':candidate.get('preview'),'implementation':_implementation(),'geometry_checker':ng.VERSION,'rule':RULE}
    if not candidate.get('render') or not candidate.get('preview'):errors.append({'code':'CHECK_NOT_EXECUTED','reason':'Actual render missing'})
    elif digest(safe_path(task,candidate['preview']['path']))!=candidate['preview']['sha256'] or read_json(safe_path(task,candidate['render']['path'])).get('pptx_hash')!=candidate['pptx']['sha256']:errors.append({'code':'STALE_RESULT'})
    items=[];inventory_hash=identity(v)
    geometry_dependencies={n:identity({'geometry':ng.serial(r['geometry']),'methods':r['actual_methods'],'order':r['order']}) for n,r in actual.items()}
    for contract in contracts:
        aa,bb=contract['objects']
        if aa not in source or bb not in source:errors.append({'code':'WRONG_MEASUREMENT_BINDING','pair':contract['id']});continue
        expected=expected_contract(source[aa],source[bb],v,inventory_hash)
        if contract!=expected:
            missing=set(p['id'] for p in expected['predicates'])-set(p['id'] for p in contract.get('predicates',[]))
            errors.append({'code':'PREDICATE_MISSING' if missing else 'WRONG_MEASUREMENT_BINDING','pair':contract['id'],'missing':sorted(missing)});continue
        measured={**relation(actual[aa],actual[bb]),'bindings':{aa:source[aa]['objects'],bb:source[bb]['objects']},'execution_identity':identity(execution),
                  'actual_geometry_dependencies':{n:geometry_dependencies[n] for n in (aa,bb)}}
        _finite(measured);results=_verdict(contract,measured)
        items.append({'id':contract['id'],'objects':contract['objects'],'measured':measured,'results':results,'passed':all(r['passed'] for r in results),'contract_hash':identity(contract)})
    failed=[{'code':'PREDICATE_FAILED','pair':r['id'],'objects':r['objects'],'predicates':[p for p in r['results'] if not p['passed']]} for r in items if not r['passed']]
    from .assembly_contracts import evaluate
    providers={};execution_ref=state.get('neighbor_execution')
    if execution_ref:
        execution_file=safe_path(task,execution_ref['path'])
        if digest(execution_file)!=execution_ref['sha256']:raise ValueError('Assembly execution receipt changed')
        current_execution=read_json(execution_file)
        if current_execution.get('source_inventory')==state['neighbor_source'] and current_execution.get('candidate',{}).get('pptx')==candidate['pptx']:
            providers=current_execution['providers']
        else:errors.append({'code':'ASSEMBLY_EXECUTION_RECEIPT_STALE'})
    assemblies=evaluate(v.get('assemblies',[]),source,native,candidate,items,providers)
    result={'schema':VERSION,'passed':not errors and not failed and assemblies['passed'],'status':'NEIGHBOR_AND_ASSEMBLY_CLOSED' if not errors and not failed and assemblies['passed'] else 'NEIGHBOR_WORK_REQUIRED',
            'execution':execution,'coverage_audit':coverage,'current_coverage_audit':current_coverage,'required_pair_ids':sorted(pair_id(*p) for p in reference),
            'errors':errors,'failed':failed,'items':items,'assemblies':assemblies,'limits':'Finite role/method/uncertainty guarantee. Source semantics remain host interpretation; no claim that an unrecognized source feature is proved nonexistent.'}
    file=Path(task)/'audits'/('neighbors-'+identity(result)+'.json');write_json(file,result)
    state['neighbor_result']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    return result

def current_result(task,state,candidate):
    """Consume only a complete independently audited result on these bytes.

    This does not execute a new check or infer semantic correctness. A source,
    registry, matte, implementation, native or actual-render change invalidates
    the receipt before another mechanism may consume its numerical evidence.
    """
    ref=state.get('neighbor_result')
    if not ref:return None
    file=safe_path(task,ref['path'])
    if digest(file)!=ref['sha256']:raise ValueError('Current neighbor receipt changed')
    result=read_json(file)
    from .execution_contract import _implementation
    expected={'source':state['source'],'source_inventory':state.get('neighbor_source'),'registry':state.get('neighbor_registry'),
              'matte_basis':identity(state.get('neighbor_mattes')),'pptx':candidate['pptx'],'render':candidate.get('render'),
              'preview':candidate.get('preview'),'implementation':_implementation(),'geometry_checker':ng.VERSION,'rule':RULE}
    if not result.get('passed') or result.get('execution')!=expected:return None
    for key in ('pptx','render','preview'):
        value=candidate.get(key)
        if not value or digest(safe_path(task,value['path']))!=value['sha256']:return None
    render=read_json(safe_path(task,candidate['render']['path']))
    if render.get('pptx_hash')!=candidate['pptx']['sha256'] or render.get('preview_hash')!=candidate['preview']['sha256']:return None
    return result


def closed_assembly_pairs(inventory,result,constructor_roots):
    """Connect exact coherent-constructor proofs to whole-assembly checks.

    A partial fold proof, a missing expected descendant, a failed current pair,
    or a relation outside this assembly cannot resolve a source interaction.
    Single-native bindings avoid substituting an aggregate/group measurement
    for the two specific physical parts being considered.
    """
    if not result or not result.get('passed'):return {}
    roles={r['id']:r for r in inventory['roles']};closed={r['id'] for r in result['assemblies']['items'] if r['passed']};out={}
    for assembly in inventory.get('assemblies',[]):
        root=assembly['root'];expected={r for r,v in roles.items() if r==root or root in v.get('ancestors',[])}
        if root not in constructor_roots or assembly['id'] not in closed or not expected or set(assembly['required_roles'])!=expected:continue
        for pair in result['items']:
            if not pair['passed'] or not set(pair['objects'])<=expected:continue
            bindings=[roles[r]['objects'] for r in pair['objects']]
            if any(len(names)!=1 for names in bindings):continue
            names=tuple(sorted(names[0] for names in bindings))
            out[names]={'assembly':assembly['id'],'root':root,'pair':pair['id'],'contract_hash':pair['contract_hash'],
                        'predicates':[r['id'] for r in pair['results']]}
    return out


def repair_packet(task,state,candidate):
    result=report(task,state,candidate)
    if result['passed']:return None
    failed=result.get('failed',[]);roles=sorted({n for r in failed for n in r['objects']})
    v=_load(task,state);byid={r['id']:r for r in v['roles']} if v else {}
    impacted=[r['id'] for r in result.get('items',[]) if set(r['objects'])&set(roles)]
    return {'kind':'neighbor_constraints','objective':'Supply missing original geometry, or repair only measured failing roles; execute finite operators and recheck all affected pairs.',
            'source':state['source'],'candidate':candidate['pptx'],'result':state.get('neighbor_result'),'errors':result.get('errors',[]),
            'failures':failed,'write_set':sorted({n for role in roles for n in byid[role]['objects']}),'check_set':impacted,
            'allowed_strategies':['original_only_reidentification','source_parameter_fit','bounded_geometry_translation','coherent_assembly_reconstruction'],
            'protected_set':'Every object/property outside the program-derived write set; retain content and approved appearance.'}
