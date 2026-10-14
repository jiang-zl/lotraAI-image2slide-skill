"""Finite source feature geometry, not an icon-name substitution catalog.

The host describes original parts and their observed coordinates. This program
constructs curves, faces and details and binds each feature to one native part.
Source uncertainty and authorized clarity/style improvements remain separate.
"""
import math,re
from .recipes import node,path,arc_shape
from .source_contract import finite

KINDS={'polygon','polyline','ellipse','rect','arc','compound_path'}

def sample_center(point,roi,sample_size=None):
    """Raster indices to continuous source geometry; Scene coordinates use edges."""
    size=sample_size or roi[2:]
    if len(point)!=2 or len(roi)!=4 or len(size)!=2 or min(list(roi[2:])+list(size))<=0 or any(not math.isfinite(v) for v in list(point)+list(roi)+list(size)):
        raise ValueError('Finite source ROI and raster sampling dimensions required')
    if any(not -.5<=v<=n-.5 for v,n in zip(point,size)):raise ValueError('Sample location escaped its source ROI')
    return [roi[i]+(point[i]+.5)*roi[i+2]/size[i] for i in (0,1)]

def expected_frame(obj,pose=None):
    """Independent source rectangle after its declared rotation and proved pose."""
    x,y,w,h=obj['bbox'];angle=math.radians(obj.get('style',{}).get('rotation',0))
    c,s=math.cos(angle),math.sin(angle);cx,cy=x+w/2,y+h/2
    points=[(cx+c*a-s*b,cy+s*a+c*b) for a,b in [(-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2)]]
    xs,ys=zip(*points);pose=pose or {'x':0,'y':0}
    return [min(xs)+pose['x'],min(ys)+pose['y'],max(xs)-min(xs),max(ys)-min(ys)]

def native_paint_checks(props,style):
    """Verify source-declared paint independently of the drawing compiler."""
    from .mathml import NS
    checks=[]
    def add(name,good):checks.append({'id':name,'passed':bool(good)})
    def colour(value):return value.lstrip('#').upper() if isinstance(value,str) else value
    if style.get('gradient'):
        grad=props.find('a:gradFill',NS);stops=[] if grad is None else grad.findall('a:gsLst/a:gs',NS)
        colors=style['gradient'];positions=style.get('gradient_positions',[i/(len(colors)-1) for i in range(len(colors))])
        actual=[(int(s.get('pos')),s.find('a:srgbClr',NS).get('val') if s.find('a:srgbClr',NS) is not None else None) for s in stops]
        add('gradient_stops',[(p,colour(c)) for p,c in actual]==[(round(p*100000),colour(c)) for p,c in zip(positions,colors)])
        if style.get('gradient_kind','linear')=='radial':
            path=None if grad is None else grad.find('a:path',NS);focus=style.get('gradient_focus',[.5,.5]);rect=None if path is None else path.find('a:fillToRect',NS)
            add('gradient_path',path is not None and path.get('path')==style.get('gradient_path','shape'))
            add('gradient_focus',rect is not None and all(int(rect.get(k))==round(v*100000) for k,v in zip(('l','t','r','b'),[focus[0],focus[1],1-focus[0],1-focus[1]])))
        else:
            lin=None if grad is None else grad.find('a:lin',NS)
            add('gradient_angle',lin is not None and int(lin.get('ang'))==round((style.get('gradient_angle',90)%360)*60000))
    elif style.get('fill'):
        paint=props.find('a:solidFill/a:srgbClr',NS)
        add('solid_fill',paint is not None and colour(paint.get('val'))==colour(style['fill']))
    if style.get('stroke') is None:
        add('explicit_no_outline',props.find('a:ln/a:noFill',NS) is not None)
    return checks

def semantic_root(unit,spec=None):
    # Existing source units may enumerate the root and all drawing descendants.
    # Do not confuse that complete ownership list with several semantic roots.
    if spec and spec.get('root_target'):
        if spec['root_target'] not in unit.get('objects',[]):raise ValueError('A source detail repair can target only its independently bound native part')
        return spec['root_target']
    root=unit.get('part')
    if root in unit.get('objects',[]) and all(n==root or n.startswith(root+'.') or n.startswith(root+'__') for n in unit['objects']):return root
    if len(unit.get('objects',[]))==1:return unit['objects'][0]
    raise ValueError('Explicit complete semantic-root ownership required')

def construct(task,state,component,spec):
    finite(spec,'feature_function')
    if spec.get('source_hash')!=state['source']['sha256'] or not spec.get('source_evidence'):
        raise ValueError('Independent original feature evidence required')
    if spec.get('schema')!='source-feature-function-1':raise ValueError('Unknown feature function')
    bbox=spec.get('bbox');roi=component['roi']
    if not isinstance(bbox,list) or len(bbox)!=4 or min(bbox[2:])<=0:
        raise ValueError('Positive original feature frame required')
    if bbox[0]<roi[0]-1 or bbox[1]<roi[1]-1 or bbox[0]+bbox[2]>roi[0]+roi[2]+1 or bbox[1]+bbox[3]>roi[1]+roi[3]+1:
        raise ValueError('Original feature frame escaped its frozen source unit')
    parts=spec.get('parts',[]);features=spec.get('features',[])
    if not parts or len(parts)>256 or not features:raise ValueError('Explicit parts and original feature ledger required')
    ids=[p.get('id') for p in parts]
    if len(set(ids))!=len(ids) or any(not isinstance(i,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+',i) for i in ids):
        raise ValueError('Distinct portable feature part IDs required')
    if any(not f.get('id') or not f.get('observed') or not f.get('parts') or not set(f['parts'])<=set(ids) for f in features):
        raise ValueError('Every original feature must bind explicit constructed parts')
    if set(ids)!={p for f in features for p in f['parts']}:raise ValueError('No unaccounted drawing part may escape feature checks')
    separator=spec.get('name_separator','.')
    if separator not in ('.','_','__'):raise ValueError('Finite stable native name separator required')
    single=spec.get('root_primitive',False)
    if single and (len(parts)!=1 or parts[0]['kind'] not in ('rect','ellipse','polygon','polyline','compound_path')):
        raise ValueError('A primitive source leaf requires exactly one implemented geometry')
    cid=component['id'];out=[] if single else [node(cid,'group',bbox,semantic=component['semantic_class'])]
    for p in parts:
        kind=p.get('kind');style=p.get('style',{});name=cid if single else cid+separator+p['id']
        if kind not in KINDS or not p.get('source_evidence'):raise ValueError('Implemented source-located geometry required')
        if kind in ('polygon','polyline'):
            pts=p.get('points',[])
            if len(pts)<(3 if kind=='polygon' else 2) or any(len(q)!=2 for q in pts):raise ValueError('Malformed feature path')
            obj=path(name,pts,cid,style.get('stroke'),style.get('fill'),style.get('line_width',.6),kind=='polygon',p['role'])
        elif kind=='compound_path':
            if not p.get('contours') or len(p['bbox'])!=4 or min(p['bbox'][2:])<=0:raise ValueError('Explicit source contours and frame required')
            for contour in p['contours']:
                points=contour.get('points');commands=contour.get('commands')
                valid_points=isinstance(points,list) and len(points)>=3 and all(len(q)==2 for q in points)
                arities={'moveTo':1,'lnTo':1,'quadBezTo':2,'cubicBezTo':3,'close':0}
                valid_commands=(isinstance(commands,list) and bool(commands) and commands[0].get('op')=='moveTo'
                    and all(c.get('op') in arities and len(c.get('points',[]))==arities[c['op']] and all(len(q)==2 for q in c.get('points',[])) for c in commands))
                if not (valid_points or valid_commands):
                    raise ValueError('Finite closed source contour required')
                from .geometry import path_operations
                path_operations(contour)
            obj=node(name,'path',p['bbox'],{'contours':p['contours']},cid,p['role'],**style)
        elif kind=='arc':
            if min(p['radii'])<=0 or not 0<abs(p['end']-p['start'])<=360:raise ValueError('Invalid source arc')
            obj=arc_shape(name,p['center'],p['radii'],p['start'],p['end'],cid,style.get('stroke'),style.get('line_width',.6),p['role'],p.get('rotation',0))
        else:
            if len(p['bbox'])!=4 or min(p['bbox'][2:])<=0:raise ValueError('Positive source detail extent required')
            obj=node(name,'shape',p['bbox'],{'preset':kind},cid,p['role'],**style)
        obj['style'].update(style);obj['evidence_status']='observed'
        if single:obj.pop('parent',None)
        out.append(obj)
    if spec.get('assembly_function'):
        from .folded_paper import VERSION as paper_version,ROLES
        from .common import identity
        meta=spec['assembly_function']
        if meta.get('version')!=paper_version or meta.get('scope')!='assembly' or set(meta.get('covered_roles',[]))!=set(ROLES):
            raise ValueError('Whole paper assembly must provide every required role')
        retained=spec.get('retained_objects',[])
        if retained:
            frozen=spec.get('retained_source')
            if not frozen or frozen.get('objects_hash')!=identity(retained) or not frozen.get('baseline_native_hash') or not frozen.get('source_evidence'):
                raise ValueError('Inherited paper content needs exact prior native/source binding')
            owned={cid};remaining=list(retained)
            while remaining:
                ready=[o for o in remaining if o.get('parent') in owned]
                if not ready:raise ValueError('Inherited paper content must stay inside the complete semantic root')
                for o in ready:
                    if o['id'] in {n['id'] for n in out} or o['render_type'] not in ('group','path','shape','text','equation'):
                        raise ValueError('Do not replace paper roles or import a flattened illustration')
                    owned.add(o['id']);remaining.remove(o)
            import copy
            outlines=[o for o in out if o['id'] in (cid+'__outer',cid+'__crease')]
            out=[o for o in out if o not in outlines]+copy.deepcopy(retained)+outlines
    return out

def compound_serialization_repair(before,after):
    """Only declare already-closed subpaths; no original fact/control changes."""
    import copy
    from .geometry import path_operations
    old=copy.deepcopy(before);new=copy.deepcopy(after);repaired=False
    for p,q in zip(old.get('parts',[]),new.get('parts',[])):
        for a,b in zip(p.get('contours',[]),q.get('contours',[])):
            if a==b:continue
            try:path_operations(a)
            except ValueError as exc:
                if str(exc)!='Contour requires exactly one initial move':return False
            else:return False
            if b.get('compound') is not True:return False
            try:path_operations(b)
            except ValueError:return False
            b.pop('compound');repaired=True
    return repaired and old==new

def function_versions(task,state):
    from .common import safe_path,read_json,digest
    versions={}
    refs=state.get('original_feature_functions_history',[])+([state['original_feature_functions']] if state.get('original_feature_functions') else [])
    for ref in refs:
        file=safe_path(task,ref['path'])
        if digest(file)!=ref['sha256']:raise ValueError('Independent original function history changed')
        for uid,spec in read_json(file)['units'].items():versions.setdefault(uid,[]).append(spec)
    return versions

def specifications(task,state):
    """Latest retained function for each source unit; old contracts stay immutable."""
    from .common import safe_path,read_json,digest
    result={}
    if state.get('original_feature_functions'):
        ref=state['original_feature_functions'];file=safe_path(task,ref['path'])
        if digest(file)!=ref['sha256']:raise ValueError('Independent original feature functions changed')
        result.update(read_json(file)['units'])
    for record in state.get('source_structure_attempts',[]):
        ref=record['contract'];file=safe_path(task,ref['path'])
        if digest(file)!=ref['sha256']:raise ValueError('Feature construction contract changed')
        for row in read_json(file)['items']:
            if 'feature_function' in row['method']:
                prior=result.get(row['unit']);spec=row['method']['feature_function']
                if prior is not None and prior!=spec and spec not in function_versions(task,state).get(row['unit'],[]):
                    raise ValueError('Constructor differs from retained independent original feature functions')
                if prior is None:result[row['unit']]=spec
    return result

def bind(task,request):
    from . import agent_runtime as a
    from .common import identity,write_json,writer
    task,state=a._state(task)
    if request.get('source_hash')!=state['source']['sha256'] or not request.get('units'):raise ValueError('Original feature units required')
    current=specifications(task,state);merged=current.copy()
    for uid,spec in request['units'].items():
        unit=state['quality']['units'].get(uid)
        if not unit:raise ValueError('Explicit source semantic root required')
        if spec.get('repeat_instance'):
            from .source_repeat import verify_instance
            verify_instance(task,state,spec)
        construct(task,state,{'id':semantic_root(unit,spec),'roi':unit['roi'],'semantic_class':unit['profile']},spec)
        if uid in current and current[uid]!=spec:
            revision=request.get('revisions',{}).get(uid,{})
            detail=state.get('source_detail_contracts',{}).get('units',{}).get(uid)
            serialization=(revision.get('kind')=='native_compound_serialization' and revision.get('reason') and
                revision.get('previous_function_hash')==identity(current[uid]) and compound_serialization_repair(current[uid],spec))
            if (not detail or not revision.get('reason') or revision.get('previous_function_hash')!=identity(current[uid])
                    or revision.get('source_detail_contract_hash')!=identity(detail)) and not serialization:
                raise ValueError('Revise this function through a located retained source finding and exact predecessor')
        merged[uid]=spec
    contract={'schema':'original-feature-functions-1','source_hash':state['source']['sha256'],'units':merged,'revisions':request.get('revisions',{})}
    file=task/'source/features/functions'/(identity(contract)+'.json');write_json(file,contract)
    with writer(task):
        old=state.get('original_feature_functions')
        if old and old!=a._file(task,file):state.setdefault('original_feature_functions_history',[]).append(old)
        state['original_feature_functions']=a._file(task,file)
        from .frame_plan import reconcile_original_palettes
        reconcile_original_palettes(task,state,request['units'])
        state.pop('acceptance',None);state.pop('quality_result',None);a._save(task,state)
    return {'status':'INDEPENDENT_ORIGINAL_FEATURE_FUNCTIONS_FROZEN','contract':a._file(task,file)}

def report(task,state,candidate):
    from .common import safe_path,identity
    from .boundary_geometry import saved_nodes
    from .mathml import NS
    specs=specifications(task,state);nodes=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size']);rows=[]
    for uid,spec in specs.items():
        if spec.get('repeat_instance'):
            from .source_repeat import verify_instance
            verify_instance(task,state,spec)
        component={'id':semantic_root(state['quality']['units'][uid],spec),'roi':state['quality']['units'][uid]['roi'],'semantic_class':'structured'}
        expected=construct(task,state,component,spec);by_id={o['id']:o for o in expected}
        for f in spec['features']:
            checks=[]
            for part in f['parts']:
                name=component['id'] if spec.get('root_primitive') else component['id']+spec.get('name_separator','.')+part;e=nodes.get(name);wanted=by_id[name];details={}
                good=bool(e and not e['error'] and e['frame'])
                if good:
                    # Extents include ancestor transforms. Native serialization
                    # precision is separate from uncertain original tracing.
                    from .neighbor_actions import verified_pose
                    pose=verified_pose(task,state,candidate,name,nodes)
                    target=expected_frame(wanted,pose)
                    frame_error=max(abs(a-b) for a,b in zip(e['frame'],target))
                    props=e['node'].find('p:spPr',NS)
                    paint=props is not None and (props.find('a:ln',NS) is not None or any(props.find('a:'+k,NS) is not None for k in ('solidFill','gradFill')))
                    paint_checks=native_paint_checks(props,wanted['style']) if props is not None else []
                    good=frame_error<=.03 and paint and all(c['passed'] for c in paint_checks)
                    details={'frame_error_px':frame_error,'paint_declared':paint,'saved_frame':e['frame'],'source_function_frame':wanted['bbox'],
                             'verified_original_relation_pose':pose,'posed_constructor_frame':target,'paint_parameter_checks':paint_checks}
                checks.append({'object':name,'passed':bool(good),**details})
            rows.append({'id':uid+':'+f['id'],'unit':uid,'source_feature':f['observed'],'passed':all(c['passed'] for c in checks),
                         'parts':checks,'source_contract_hash':identity(spec),'scope':'Every feature part actual saved extent/paint plus independent complete native constructor replay'})
    return {'passed':all(r['passed'] for r in rows),'items':rows,'applicable':bool(specs)}
