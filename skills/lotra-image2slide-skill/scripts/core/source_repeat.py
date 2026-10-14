"""Original-only repeat discovery and immutable semantic prototype reuse.

Similarity proposes a family, never its meaning. The host distinguishes a
shared shape from varying content. Source functions are cloned numerically;
every instance keeps the ordinary independent original and native checks.
"""
import copy,math
import numpy as np
from pathlib import Path
from .common import identity,digest,read_json,write_json,safe_path
VERSION='original-repeat-families-1'
POLICY={'sample_size':24,'edge_cosine_min':.84,'rgb_mae_max':.11,
        'maximum_candidates':96,'quarter_turns':[0,1,2,3],
        'role':'Engineering candidate screening, not semantic equivalence or acceptance'}

def discover(task,state):
    from PIL import Image
    from scipy.ndimage import sobel
    from .adaptive_detail import source_units,_box
    from .appearance_metrics import canvas
    units={k:u for k,u in source_units(state).items() if not u.get('parent_source_unit')
        and u['profile'] not in ('text','formula','relation','texture') and min(u['roi'][2:])>=3}
    basis=identity({'source':state['source'],'policy':POLICY,
        'units':{k:{'roi':u['roi'],'profile':u['profile']} for k,u in units.items()}})
    path=task/'source/repeats'/('discovery-'+basis+'.json')
    if path.is_file():return read_json(path)
    original=canvas(str(safe_path(task,state['source']['path'])),state['source']['sha256'],tuple(state['source_size']))
    samples={};size=POLICY['sample_size']
    for uid,u in units.items():
        x,y,r,b=_box(u['roi'],state['source_size']);data=original[y:b,x:r]
        im=Image.fromarray(np.rint(data*255).astype('uint8')).resize((size,size),Image.Resampling.LANCZOS)
        rgb=np.asarray(im,float)/255;grey=rgb.mean(2);edge=np.hypot(sobel(grey,0),sobel(grey,1))
        if np.count_nonzero(edge>.3)<8:continue
        samples[uid]=(rgb,edge)
    ids=sorted(samples);pairs=[]
    for i,a in enumerate(ids):
        for b in ids[i+1:]:
            ua,ub=units[a],units[b]
            if ua['profile']!=ub['profile']:continue
            # Overlapping source windows are often two granularities of one
            # object, not independent repetitions.
            ax,ay,aw,ah=ua['roi'];bx,by,bw,bh=ub['roi']
            overlap=max(0,min(ax+aw,bx+bw)-max(ax,bx))*max(0,min(ay+ah,by+bh)-max(ay,by))
            if overlap>.2*min(aw*ah,bw*bh) or max(aw*ah,bw*bh)>64*min(aw*ah,bw*bh):continue
            ar,ae=samples[a];br,be=samples[b];best=None
            for turns in POLICY['quarter_turns']:
                re=np.rot90(be,turns);rr=np.rot90(br,turns)
                cosine=float(np.sum(ae*re)/(np.linalg.norm(ae)*np.linalg.norm(re)+1e-12));error=float(np.mean(np.abs(ar-rr)))
                if cosine>=POLICY['edge_cosine_min'] and error<=POLICY['rgb_mae_max']:
                    row={'objects':[a,b],'edge_cosine':cosine,'rgb_mae':error,'source_quarter_turn':turns}
                    if best is None or cosine-error>best['edge_cosine']-best['rgb_mae']:best=row
            if best:pairs.append(best)
    pairs.sort(key=lambda p:(-(p['edge_cosine']-p['rgb_mae']),p['objects']))
    # A finite spanning forest gives each similar object a proposal without
    # sending all pairwise combinations to the model.
    parent={k:k for k in ids}
    def root(k):
        while parent[k]!=k:k=parent[k]
        return k
    retained=[]
    for p in pairs:
        a,b=p['objects'];ra,rb=root(a),root(b)
        if ra==rb:continue
        if len(retained)>=POLICY['maximum_candidates']:break
        parent[rb]=ra;p['id']=identity({'basis':basis,'pair':p['objects']});retained.append(p)
    result={'schema':VERSION,'source_hash':state['source']['sha256'],'basis':basis,'policy':POLICY,
        'units':{k:{'roi':u['roi'],'objects':u['objects'],'profile':u['profile']} for k,u in units.items()},
        'pairs':retained,'pairwise_candidates':len(pairs),'screened_units':len(units),
        'limits':'Quarter-turn screening can miss arbitrary poses, occlusion or varying content. The host may nominate additional original-supported families; independent source completeness never depends on this detector.'}
    write_json(path,result);return result

def packet(task,state):
    from .quality_intent import source_view
    scan=discover(task,state);known=state.get('source_repeat_decisions',{});pending=[]
    for p in scan['pairs']:
        if known.get(p['id'],{}).get('basis')==scan['basis']:continue
        row=copy.deepcopy(p);row['views']=[{'unit':uid,'original_view':source_view(task,state,scan['units'][uid]['roi'],3)} for uid in p['objects']];pending.append(row)
    if not pending:return None
    return {'kind':'source_repeat_observation','schema':VERSION,'source_hash':scan['source_hash'],'basis':scan['basis'],
        'items':pending[:6],'remaining':len(pending),'instruction':'Compare original anatomy and content. Declare shared_geometry, shared_with_variants or distinct with located evidence. Similar pixels alone do not authorize copying text, formulas, ports or differing marks. For a confirmed family, optimize one mother and instantiate source poses; still check every instance.'}

def bind(task,state,request):
    from .quality_intent import source_view
    scan=discover(task,state);pairs={p['id']:p for p in scan['pairs']};rows=request.get('items',[])
    if request.get('source_hash')!=scan['source_hash'] or request.get('basis')!=scan['basis'] or not rows:
        raise ValueError('Current original repeat survey required')
    if len({r.get('id') for r in rows})!=len(rows):raise ValueError('Unique source family decisions required')
    ledger=copy.deepcopy(state.get('source_repeat_decisions',{}))
    for row in rows:
        p=pairs.get(row.get('id'))
        if not p or row.get('decision') not in ('shared_geometry','shared_with_variants','distinct') or not row.get('evidence'):
            raise ValueError('Explicit original anatomy/content decision required')
        expected=[source_view(task,state,scan['units'][uid]['roi'],3)['sha256'] for uid in p['objects']]
        if row.get('original_view_hashes')!=expected:raise ValueError('Observe both unchanged original instances')
        if row['decision']=='shared_with_variants' and not row.get('variants'):raise ValueError('Name the independently preserved variant roles')
        ledger[row['id']]={**copy.deepcopy(row),'basis':scan['basis'],'objects':p['objects']}
    state['source_repeat_decisions']=ledger;state.pop('acceptance',None);state.pop('quality_result',None)
    return {'status':'ORIGINAL_REPEAT_DECISIONS_RETAINED','recorded':len(rows)}

def freeze_mother(task,state,unit_id):
    from .source_feature_functions import specifications,report as function_report
    from .detail_contracts import checks_report
    spec=specifications(task,state).get(unit_id)
    if not spec:raise ValueError('Rebuild and freeze the mother source function first')
    candidate=state.get('active_candidate') or state.get('selected')
    if not candidate or not candidate.get('preview'):raise ValueError('Actually render and check the mother before reuse')
    native=[r for r in function_report(task,state,candidate)['items'] if r['unit']==unit_id]
    local=[r for r in checks_report(task,state,candidate)['items'] if r['id']==unit_id]
    if not native or not all(r['passed'] for r in native) or not local or not all(r['passed'] for r in local):
        raise ValueError('Mother must meet its own frozen source geometry and local hard checks before copying')
    unit=state['quality']['units'][unit_id]
    payload={'schema':VERSION,'source_hash':state['source']['sha256'],'unit':unit_id,'original_roi':unit['roi'],
        'function':spec,'function_hash':identity(spec),'basis':'Independent frozen original feature function; actual instance quality remains mandatory'}
    payload.update(actual_native=candidate['pptx'],actual_preview=candidate['preview'],native_checks=native,source_local_checks=local)
    file=task/'source/repeats/mothers'/(identity(payload)+'.json');write_json(file,payload)
    return {'path':file.relative_to(task).as_posix(),'sha256':digest(file)}

def clone_function(task,state,mother_ref,unit_id,root_target,evidence,angle_degrees=0,source_anchor='roi_center'):
    """Return an executable source function, never a language drawing action."""
    from .source_feature_functions import construct
    if not evidence or not math.isfinite(angle_degrees):raise ValueError('Observed instance pose and semantic evidence required')
    file=safe_path(task,mother_ref['path'])
    if not mother_ref['path'].startswith('source/repeats/mothers/') or digest(file)!=mother_ref['sha256']:
        raise ValueError('Immutable local mother identity required')
    model=read_json(file)
    if model['source_hash']!=state['source']['sha256'] or identity(model['function'])!=model['function_hash']:
        raise ValueError('Mother belongs to another original or changed geometry')
    unit=state['quality']['units'][unit_id]
    if root_target not in unit['objects']:raise ValueError('Instance must stay inside its independent native source owner')
    source=model['original_roi'];target=unit['roi'];sx,sy=target[2]/source[2],target[3]/source[3]
    cx,cy=source[0]+source[2]/2,source[1]+source[3]/2;tx,ty=target[0]+target[2]/2,target[1]+target[3]/2
    co,si=math.cos(math.radians(angle_degrees)),math.sin(math.radians(angle_degrees))
    if angle_degrees:
        sx=sy=min(target[2]/(abs(co)*source[2]+abs(si)*source[3]),target[3]/(abs(si)*source[2]+abs(co)*source[3]))
    delta=[0.,0.]
    if source_anchor=='dark_centroid':
        from .appearance_metrics import canvas
        from .adaptive_detail import _box
        original=canvas(str(safe_path(task,state['source']['path'])),state['source']['sha256'],tuple(state['source_size']))
        def centroid(roi):
            x,y,r,b=_box(roi,state['source_size']);data=original[y:b,x:r].mean(2)
            weights=np.where(data<.6,1-data,0);support=weights>0
            if support.sum()<8:raise ValueError('Dark source anchor has insufficient independent original support')
            yy,xx=np.indices(weights.shape);return [float(((xx+x+.5)*weights).sum()/weights.sum()),float(((yy+y+.5)*weights).sum()/weights.sum())]
        first,last=centroid(source),centroid(target);xx,yy=(first[0]-cx)*sx,(first[1]-cy)*sy
        delta=[last[0]-(tx+co*xx-si*yy),last[1]-(ty+si*xx+co*yy)]
        if max(abs(v) for v in delta)>max(4,min(target[2:])*.4):raise ValueError('Source anchor correction requires a finer independent object window')
    elif source_anchor!='roi_center':raise ValueError('Use an implemented original-only source anchor')
    def point(p):
        x,y=(p[0]-cx)*sx,(p[1]-cy)*sy
        return [tx+co*x-si*y+delta[0],ty+si*x+co*y+delta[1]]
    def box(b):
        mid=point([b[0]+b[2]/2,b[1]+b[3]/2]);return [mid[0]-b[2]*sx/2,mid[1]-b[3]*sy/2,b[2]*sx,b[3]*sy]
    spec=copy.deepcopy(model['function']);spec.update(root_target=root_target,source_evidence=evidence)
    spec['bbox']=copy.deepcopy(target) if not spec.get('root_primitive') else box(spec['bbox'])
    for p in spec['parts']:
        p['source_evidence']=evidence
        if 'points' in p:p['points']=[point(v) for v in p['points']]
        if 'bbox' in p:
            old=p['bbox'];p['bbox']=box(old)
            if p['kind']=='compound_path' and angle_degrees:
                contours=[]
                for contour in p['contours']:
                    transformed=copy.deepcopy(contour)
                    if 'points' in contour:transformed['points']=[point([old[0]+q[0]*old[2],old[1]+q[1]*old[3]]) for q in contour['points']]
                    for command in transformed.get('commands',[]):command['points']=[point([old[0]+q[0]*old[2],old[1]+q[1]*old[3]]) for q in command.get('points',[])]
                    contours.append(transformed)
                pts=[q for c in contours for q in c.get('points',[])]+[q for c in contours for cmd in c.get('commands',[]) for q in cmd.get('points',[])];x=min(q[0] for q in pts);y=min(q[1] for q in pts);w=max(q[0] for q in pts)-x;h=max(q[1] for q in pts)-y
                p['bbox']=[x,y,w,h]
                for c in contours:
                    if 'points' in c:c['points']=[[(q[0]-x)/w,(q[1]-y)/h] for q in c['points']]
                    for command in c.get('commands',[]):command['points']=[[(q[0]-x)/w,(q[1]-y)/h] for q in command.get('points',[])]
                p['contours']=contours
            elif p['kind']=='rect' and angle_degrees:
                x,y,w,h=old;p.update(kind='polygon',points=[point(q) for q in ([x,y],[x+w,y],[x+w,y+h],[x,y+h])]);p.pop('bbox')
            elif p['kind']=='ellipse' and angle_degrees and abs(old[2]*sx-old[3]*sy)>.02:
                raise ValueError('An oriented ellipse needs its analytic curve model; do not approximate a pose silently')
        if p.get('kind')=='arc':
            if abs(sx-sy)>1e-8:raise ValueError('Arc mother needs uniform instance scaling')
            p['center']=point(p['center']);p['radii']=[v*sx for v in p['radii']];p['rotation']=p.get('rotation',0)+angle_degrees
        if p.get('style',{}).get('line_width') is not None:p['style']['line_width']*=math.sqrt(sx*sy)
    spec['repeat_instance']={'mother':mother_ref,'mother_unit':model['unit'],'instance_unit':unit_id,
        'original_roi':target,'angle_degrees':angle_degrees,'root_target':root_target,'evidence':evidence}
    spec['repeat_instance'].update(source_anchor=source_anchor,source_anchor_delta_px=delta)
    construct(task,state,{'id':root_target,'roi':unit['roi'],'semantic_class':unit['profile']},spec)
    return spec

def verify_instance(task,state,spec):
    record=spec.get('repeat_instance')
    if not record:return
    expected=clone_function(task,state,record['mother'],record['instance_unit'],record['root_target'],record['evidence'],record['angle_degrees'],record.get('source_anchor','roi_center'))
    if expected!=spec:raise ValueError('Repeat instance differs from immutable mother and source pose')

def report(task,state,candidate=None):
    scan=discover(task,state);known=state.get('source_repeat_decisions',{})
    pending=[p['id'] for p in scan['pairs'] if known.get(p['id'],{}).get('basis')!=scan['basis']]
    from .source_feature_functions import specifications
    from .semantic_composition import _scene_for
    scene=_scene_for(state,task);nodes={o['id']:o for o in scene['objects']}
    def primitives(uid):
        result=[]
        for name in state['quality']['units'][uid]['objects']:
            node=nodes.get(name)
            if not node or node['render_type']=='group':continue
            content=copy.deepcopy(node['content'])
            for key in ('native_snapshot','frame_clip','clip_geometry'):content.pop(key,None)
            # Native primitives already use one implemented constructor;
            # frame and paint are explicit instance parameters, checked by
            # their independent original geometry and appearance programs.
            if node['render_type']=='shape':key=identity({'type':'shape','preset':content.get('preset'),'adjustments':content.get('adjustments')})
            else:
                def canonical(v):
                    if isinstance(v,float):return round(v,9)
                    if isinstance(v,list):return [canonical(x) for x in v]
                    if isinstance(v,dict):return {k:canonical(x) for k,x in v.items()}
                    return v
                key=identity({'type':node['render_type'],'content':canonical(content),'role':node.get('semantic_type')})
            result.append(key)
        return result
    proofs=[]
    for pair in scan['pairs']:
        row=known.get(pair['id']);proof=True;common=[]
        if row and row.get('decision')!='distinct':
            a,b=pair['objects'];left,right=primitives(a),primitives(b);remaining=list(right)
            for key in left:
                if key in remaining:common.append(key);remaining.remove(key)
            proof=bool(common) and (row['decision']=='shared_with_variants' or len(common)==len(left)==len(right))
        proofs.append({'id':pair['id'],'passed':proof if row else False,'common_constructor_parts':len(common),
            'decision':row.get('decision') if row else None,'scope':'Program verifies a common native primitive/contour constructor; independent varying content and every instance remain mandatory. Similarity prose alone proves no reuse.'})
    reused=[];current_functions=specifications(task,state)
    from .source_feature_functions import report as native_function_report
    from .detail_contracts import checks_report
    native_checks=native_function_report(task,state,candidate)['items'] if candidate else []
    local_checks=checks_report(task,state,candidate)['items'] if candidate else []
    for uid,spec in current_functions.items():
        if not spec.get('repeat_instance'):continue
        verify_instance(task,state,spec);model=read_json(safe_path(task,spec['repeat_instance']['mother']['path']));master=model['unit']
        checks=[r['passed'] for r in native_checks if r['unit']==master]+[r['passed'] for r in local_checks if r['id']==master]
        mother_current=identity(current_functions.get(master))==model['function_hash'] and bool(checks) and all(checks)
        reused.append({'unit':uid,'mother':spec['repeat_instance']['mother'],'passed':mother_current,
            'pose':{'roi':spec['repeat_instance']['original_roi'],'angle_degrees':spec['repeat_instance']['angle_degrees']},
            'status':'IMMUTABLE_MOTHER_AND_SOURCE_POSE' if mother_current else 'MOTHER_REVISION_OR_LOCAL_RECHECK_REQUIRED','acceptance':'Independent instance source/native/connection checks remain mandatory'})
    passed=not pending and all(p['passed'] for p in proofs) and all(r['passed'] for r in reused)
    return {'schema':VERSION,'passed':passed,'status':'ORIGINAL_REPEAT_SURVEY_CURRENT' if passed else 'ORIGINAL_REPEAT_DECISIONS_OR_CONSTRUCTION_REQUIRED',
        'discovery_basis':scan['basis'],'screened_units':scan['screened_units'],'pending':pending,
        'decisions':[known[p['id']] for p in scan['pairs'] if p['id'] in known], 'construction_proofs':proofs,'instantiated_functions':reused,
        'limits':'A checked proposal is not automatic equality. Native natural-icon mother identities and instantiated source functions retain separate per-instance quality and rollback.'}

def command(task,operation,request=None):
    from . import agent_runtime as a
    from .common import writer
    task,state=a._state(task)
    if operation=='scan':return discover(task,state)
    if operation=='next':return packet(task,state)
    if operation=='report':return report(task,state,state.get('active_candidate') or state.get('selected'))
    if operation=='observe':
        with writer(task):
            result=bind(task,state,request);a._save(task,state);return result
    raise ValueError('Unknown original repeat operation')
