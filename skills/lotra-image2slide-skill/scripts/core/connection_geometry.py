"""Program-assisted connection hypotheses, canonical geometry and native docking.

Meaning/port selection belongs to the source interpreter. Geometry is measured
from saved world coordinates. Candidate evidence never automatically merges.
"""
import copy,math
import numpy as np
from .common import identity,digest,read_json,write_json,safe_path,writer
from .mathml import NS

VERSION='connection-geometry-2'

def line(entry,terminal_sites=None):
    if entry.get('error') or entry.get('matrix') is None:raise ValueError(entry.get('error') or 'Missing line transform')
    prop=entry['node'].find('.//p:cNvPr',NS)
    if prop is not None and prop.get('hidden','0') in ('1','true'):raise ValueError('Actual connection path is hidden')
    props=entry['node'].find('p:spPr',NS);prst=props.find('a:prstGeom',NS) if props is not None else None
    world_segments=[];kind='straight'
    if prst is not None and prst.get('prst')=='line':uv=[[0,0,1],[1,1,1]]
    elif prst is not None and prst.get('prst') in ('bentConnector2','bentConnector3','bentConnector4','bentConnector5'):
        # DrawingML preset path coordinates, before the saved parent/flip/rotation
        # transform. Adjustment handles can extend beyond the nominal frame.
        # Definitions: Apache POI's ECMA presetShapeDefinitions.xml.
        adj={name:.5 for name in ('adj1','adj2','adj3')}
        for guide in prst.findall('a:avLst/a:gd',NS):
            formula=(guide.get('fmla') or '').split()
            if len(formula)!=2 or formula[0]!='val':raise ValueError('Unresolved connector adjustment requires host geometry')
            value=float(formula[1])/100000
            if not math.isfinite(value):raise ValueError('Nonfinite connector adjustment')
            adj[guide.get('name')]=value
        x,y,z=adj['adj1'],adj['adj2'],adj['adj3']
        vertices={'bentConnector2':[[0,0,1],[1,0,1],[1,1,1]],
                  'bentConnector3':[[0,0,1],[x,0,1],[x,1,1],[1,1,1]],
                  'bentConnector4':[[0,0,1],[x,0,1],[x,y,1],[1,y,1],[1,1,1]],
                  'bentConnector5':[[0,0,1],[x,0,1],[x,y,1],[z,y,1],[z,1,1],[1,1,1]]}[prst.get('prst')]
        world=np.array(vertices)@entry['matrix'].T
        world_segments=[world[i:i+2,:2].tolist() for i in range(len(vertices)-1)]
        uv=[vertices[0],vertices[-1]];kind='polyline'
    elif prst is not None and 'Arrow' in prst.get('prst',''):
        direction=prst.get('prst');kind='filled_arrow'
        uv={'rightArrow':[[0,.5,1],[1,.5,1]],'leftArrow':[[1,.5,1],[0,.5,1]],
            'upArrow':[[.5,1,1],[.5,0,1]],'downArrow':[[.5,0,1],[.5,1,1]]}.get(direction)
        if uv is None:uv=[[0,0,1],[1,1,1]]
    else:
        geom=props.find('a:custGeom',NS) if props is not None else None
        paths=geom.findall('a:pathLst/a:path',NS) if geom is not None else []
        if len(paths)!=1:raise ValueError('Unsupported connection path; use actual path/host measurement')
        p=paths[0];w,h=float(p.get('w')),float(p.get('h'));uv=[];controls=[];current=None;first=None;closed=False
        for op in p:
            tag=op.tag.rsplit('}',1)[-1]
            pts=op.findall('a:pt',NS)
            values=[[float(q.get('x'))/w,float(q.get('y'))/h,1] for q in pts]
            if tag=='moveTo':
                if first is not None:raise ValueError('Multiple disjoint connection subpaths require separate owners')
                current=first=values[0]
            elif tag in ('lnTo','quadBezTo','cubicBezTo') and current is not None:
                controls.append([current]+values);current=values[-1]
            elif tag=='close':closed=True
            else:raise ValueError('Unsupported actual connection path: '+tag)
        if current is None or not controls:raise ValueError('Empty actual connection path')
        world_segments=[(np.array(ctrl)@entry['matrix'].T)[:,:2].tolist() for ctrl in controls]
        kind='filled_arrow' if closed else ('curve' if any(len(p)>2 for p in controls) else 'polyline' if len(controls)>1 else 'straight')
        uv=[first,current]
        if closed and terminal_sites:
            vertices=[first]+[c[-1] for c in controls]
            uv=[]
            for side in ('start','end'):
                site=terminal_sites[side]
                if 'vertex' in site:uv.append(vertices[site['vertex']])
                elif 'edge' in site:uv.append(np.mean([vertices[i] for i in site['edge']],axis=0).tolist())
                else:raise ValueError('Closed filled-arrow terminals require located polygon vertex/edge sites')
    points=np.array(uv)@entry['matrix'].T
    ln=props.find('a:ln',NS);markers={}
    for key in ('headEnd','tailEnd'):
        n=ln.find('a:'+key,NS) if ln is not None else None
        markers[key]=n.get('type','none') if n is not None else 'none'
    # In DrawingML headEnd marks the path start; tailEnd marks its end.
    colour=ln.find('a:solidFill/a:srgbClr',NS) if ln is not None else None
    dash=ln.find('a:prstDash',NS) if ln is not None else None
    return {'points':points[:,:2].tolist(),'path_kind':kind,'segments':world_segments,'markers':markers,'style':{'colour':colour.get('val') if colour is not None else None,
            'width_emu':int(ln.get('w',0)) if ln is not None else 0,'dash':dash.get('val') if dash is not None else 'solid'}}

def inventory(task,state,candidate):
    from .boundary_geometry import saved_nodes
    nodes=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size'])
    scene=read_json(safe_path(task,candidate['scene']['path']))
    names={o['id'] for o in scene['objects'] if o['render_type']=='connector' or o.get('semantic_type')=='connector' or
           o.get('semantic_type','').endswith('_arrow') or 'Arrow' in o.get('content',{}).get('preset','')}
    names|={n for n,e in nodes.items() if e['tag']=='cxnSp' or
        e['node'].find('p:spPr/a:prstGeom',NS) is not None and e['node'].find('p:spPr/a:prstGeom',NS).get('prst')=='line'}
    names|={n for n,e in nodes.items() if any(v.get('type','none')!='none' for v in e['node'].findall('p:spPr/a:ln/a:headEnd',NS)+e['node'].findall('p:spPr/a:ln/a:tailEnd',NS))}
    # Source-registered unmarked native freeform curves remain connections
    # even if Office snapshots serialize them as ordinary editable shapes.
    if state.get('connection_contract'):
        from .execution_contract import resource
        known=read_json(resource(task,state['connection_contract']))
        names|={n for r in known['items'] for n in r['objects']}
    # A native math replacement can retain its predecessor's scene identity.
    # The archived, nonpainted strokes are not active semantic connectors.
    names={n for n in names if n not in nodes or not (
        nodes[n]['node'].find('.//m:oMath',NS) is not None or
        nodes[n]['node'].find('p:spPr/a:ln/a:noFill',NS) is not None or
        nodes[n]['node'].find('p:nvCxnSpPr/p:cNvPr',NS) is not None and
        nodes[n]['node'].find('p:nvCxnSpPr/p:cNvPr',NS).get('hidden','0') in ('1','true'))}
    return nodes,sorted(names)

def candidates(task,state,candidate):
    from .source_connections import load,packet
    graph=load(task,state)
    if graph is None:return {'schema':VERSION,'status':'ORIGINAL_CONNECTION_SURVEY_REQUIRED','packet':packet(task,state)}
    nodes,names=inventory(task,state,candidate) if candidate else ({},[])
    return {'schema':VERSION,'source_hash':state['source']['sha256'],'source_graph':state['source_connection_graph'],
        'objects':names,'source_parts':[p['id'] for p in graph['parts']],'candidates':graph['candidate_pairs'],
        'scope':'Candidates retained from independent original measurements; wrong reconstructed geometry cannot remove them.'}

def _legacy_output_proposals(task,state,candidate):
    nodes,names=inventory(task,state,candidate);lines={};errors=[]
    for name in names:
        try:lines[name]=line(nodes[name])
        except (ValueError,KeyError,TypeError) as error:errors.append({'object':name,'reason':str(error)})
    texts=[(n,e['frame']) for n,e in nodes.items() if e['frame'] and e['node'].find('.//a:t',NS) is not None]
    result=[]
    for i,a in enumerate(lines):
        for b in list(lines)[i+1:]:
            if lines[a]['path_kind']!='straight' or lines[b]['path_kind']!='straight':continue
            pa=np.array(lines[a]['points']);pb=np.array(lines[b]['points']);da=pa[1]-pa[0];db=pb[1]-pb[0]
            la,lb=np.linalg.norm(da),np.linalg.norm(db)
            if min(la,lb)<.001:continue
            direction=da/la;normal=np.array([-direction[1],direction[0]])
            offsets=np.abs((pb-pa[0])@normal);angle=abs(float(np.cross(da/la,db/lb)))
            if min(offsets)>5 or angle>.2:continue
            for text,frame in texts:
                x,y,w,h=frame;corners=np.array([[x,y],[x+w,y],[x,y+h],[x+w,y+h]]);pr=corners@direction;nr=corners@normal
                center=corners.mean(0);ma=(pa.mean(0)-center)@direction;mb=(pb.mean(0)-center)@direction
                near=min(np.linalg.norm(p-center) for p in [*pa,*pb])<=max(w,h)+20
                if not near or ma*mb>=0:continue
                crossings=bool(min(nr)-2<pa[0]@normal<max(nr)+2)
                if not crossings:continue
                markers=[*lines[a]['markers'].values(),*lines[b]['markers'].values()]
                arrow_count=sum(m not in ('none','oval','diamond') for m in markers)
                tail_count=sum(m in ('oval','diamond') for m in markers)
                result.append({'id':identity([a,b,text])[:20],'objects':[a,b],'occluder':text,
                    'direction_cross_abs':angle,'max_extension_offset_px':float(max(offsets)),
                    'opposite_text_sides':True,'styles_equal':lines[a]['style']==lines[b]['style'],
                    'marker_evidence':{'types':markers,'arrow_count':arrow_count,'tail_count':tail_count,
                                      'unknown_source_marker_visibility':'Host must distinguish absence from source occlusion'},
                    'hypotheses':['same_straight','same_curve','independent','branch','uncertain'],
                    'scope':'Proposal from current geometry; original views and source endpoint observations decide meaning'})
    return {'schema':VERSION,'source_hash':state['source']['sha256'],'candidate_hash':candidate['pptx']['sha256'],
            'objects':names,'candidates':result,'unmeasured_paths':errors}

def original_function_boundary(task,state,reference,target,historical=False):
    """A refined original primitive can replace a coarse port boundary fact."""
    from .source_feature_functions import specifications,construct,semantic_root
    spec=specifications(task,state).get(reference.get('unit'));unit=state['quality']['units'].get(reference.get('unit'))
    if historical and (not spec or reference.get('function_hash')!=identity(spec)):
        from .source_feature_functions import function_versions
        spec=next((v for v in function_versions(task,state).get(reference.get('unit'),[]) if identity(v)==reference.get('function_hash')),None)
    if not spec or not unit or reference.get('function_hash')!=identity(spec) or target not in unit['objects']:
        raise ValueError('Current independent original function and physical owner required')
    objects={o['id']:o for o in construct(task,state,{'id':semantic_root(unit,spec),'roi':unit['roi'],'semantic_class':unit['profile']},spec)}
    owner=objects.get(target)
    if not owner or owner['render_type']!='shape' or owner['content'].get('preset') not in ('rect','ellipse') or owner.get('rotation',owner.get('style',{}).get('rotation',0)):
        raise ValueError('Refined port boundary needs an implemented axis-aligned original primitive; retain original contour evidence otherwise')
    return {'kind':owner['content']['preset'],'bbox':copy.deepcopy(owner['bbox'])}


def bind(task,request):
    from . import agent_runtime as a
    from .source_contract import finite
    task,state=a._state(task);candidate=state.get('active_candidate') or state['selected'];nodes,names=inventory(task,state,candidate)
    if request.get('source_hash')!=state['source']['sha256']:raise ValueError('Original connection identity mismatch')
    from . import source_connections as sc
    graph=sc.load(task,state)
    if graph is None or request.get('source_graph')!=state.get('source_connection_graph'):raise ValueError('Bind the current independently frozen original connection graph')
    rows=copy.deepcopy(request.get('items',[]));covered=[n for r in rows for n in r.get('objects',[])]
    if set(covered)!=set(names) or len(covered)!=len(set(covered)):raise ValueError('Every saved connector needs exactly one source connection contract')
    if len({r.get('id') for r in rows})!=len(rows):raise ValueError('Unique source connection identities required')
    from .source_feature_functions import specifications,construct,semantic_root
    refined={}
    for uid,fn in specifications(task,state).items():
        unit=state['quality']['units'][uid]
        for owner in construct(task,state,{'id':semantic_root(unit,fn),'roi':unit['roi'],'semantic_class':unit['profile']},fn):
            if owner['render_type']=='shape' and owner['content'].get('preset') in ('rect','ellipse'):
                refined.setdefault(owner['id'],[]).append({'unit':uid,'function_hash':identity(fn)})
    for row in rows:
        finite(row,'connection_contract')
        if row.get('mode') not in ('independent','same_straight','same_curve','branch') or not row.get('source_evidence') or not row.get('source_roi'):
            raise ValueError('Source-decided connection mode and located evidence required')
        if row['mode']=='same_straight' and len(row['objects'])<2:raise ValueError('All original visible fragments required')
        if row.get('canonical_points') or row.get('expected_markers'):raise ValueError('Canonical straight coordinates and marker contracts are program-derived from original observations')
        if row['mode']=='same_curve' and not row.get('canonical_curve'):raise ValueError('Explicit common curve required; no straight-line substitution')
        for occluder in row.get('occluders',[]):
            if occluder not in nodes or nodes[occluder]['node'].find('.//a:t',NS) is None:
                raise ValueError('An occluded common path must bind actual source-associated text owners')
        ports=row.get('ports',[]);port_keys=[(p.get('object',row['objects'][0]),p.get('end')) for p in ports]
        if set(port_keys)!={(n,i) for n in row['objects'] for i in (0,1)} or len(port_keys)!=len(set(port_keys)):
            raise ValueError('Every connection end needs exactly one source-decided endpoint profile')
        for port in row.get('ports',[]):
            references=refined.get(port.get('target'),[])
            if not port.get('source_function_boundary') and port.get('source_boundary',{}).get('kind') in ('rect','ellipse') and len(references)==1:
                port['source_function_boundary']=references[0]
            if port.get('source_function_boundary'):
                port['source_boundary']=original_function_boundary(task,state,port['source_function_boundary'],port['target'])
            if not port.get('source_evidence'):raise ValueError('Original evidence is required even for a free endpoint')
            if port.get('profile') not in sc.PROFILES or port.get('end') not in (0,1):raise ValueError('Finite endpoint profile required')
            if port['profile']=='free':
                if port.get('free_reason') not in ('legend','axis','timeline','annotation','standalone_layer_indicator','original_detached'):
                    raise ValueError('A free endpoint requires a specific original semantic context, not a generic default')
            elif port['profile']=='junction_cut':
                if row['mode']!='branch':raise ValueError('Junction profile requires a source-observed branch')
            elif port['profile']=='occlusion_cut':
                if port.get('occluder') not in row.get('occluders',[]):raise ValueError('Occlusion cut must bind an actual original-associated text mask')
            elif port.get('target') not in nodes or port.get('semantic_owner') not in nodes:
                raise ValueError('Separate observed semantic owner and physical port owner required')
            elif not port.get('source_boundary'):
                raise ValueError('Original physical boundary observation required to calculate contact/gap')
            if port['profile'] not in ('free','occlusion_cut','junction_cut'):
                from .execution_contract import _descendant
                if not _descendant(port['target'],port['semantic_owner'],{n:v['parent_name'] for n,v in nodes.items()}):raise ValueError('Physical port must belong to the independently selected semantic owner')
            if port['profile']=='circle_half_embedded':
                if not port.get('radius_px') or port.get('marker_object') not in nodes:
                    raise ValueError('Half-embedded circle requires its actual native circle owner and declared radius, not an inferred proxy disk')
                _circle_marker(nodes[port['marker_object']],port['radius_px'])
    terminals=sc.reconcile(graph,rows,request.get('candidate_decisions',[]))
    from shapely.geometry import Point
    rgb=sc._source(task,state)
    for port in terminals:
        if port['profile']=='free':continue
        geometry=port['source_boundary'];domain,contour_proof=sc.original_domain(rgb,geometry)
        point=Point(port['source_point']);gap=float(point.distance(domain));signed=float(point.distance(domain.boundary))*(-1 if domain.contains(point) else 1)
        port['source_measurement']={'signed_boundary_distance_px':signed,'gap_px':gap,'source_uncertainty_px':2.0,'original_contour':contour_proof}
        actual=next(p for r in rows for p in r['ports'] if p['object']==port['object'] and p['end']==port['end'])
        actual['source_measurement']=port['source_measurement']
        # A line can enter an enclosing module from its boundary and terminate
        # at an internal operator. Infer that side from original physical
        # domains, never from a generic 'connected' label or current overlap.
        row=next(r for r in rows if port['object'] in r['objects'])
        peer=next((p for p in row['ports'] if p['object']==port['object'] and p['end']!=port['end']),None)
        actual['source_incident_side']='exterior'
        if (port['end']==0 and port.get('marker')=='none' and peer and peer.get('source_boundary') and
                peer.get('semantic_owner')==port.get('semantic_owner')):
            peer_domain,_=sc.original_domain(rgb,peer['source_boundary'])
            if domain.buffer(.025).covers(peer_domain):
                actual['source_incident_side']='interior'
                actual['source_internal_target']=peer['target']
        if port['profile']=='intentional_gap':
            if gap<=2:raise ValueError('Intentional separation requires original gap above source uncertainty; do not hide a contact error')
            actual['gap_interval']=[max(.25,gap-1.5),gap+1.5];port['gap_interval']=actual['gap_interval']
        elif port['profile']=='inside_port':
            if signed>=-2:raise ValueError('Inside port requires source-observed penetration')
            actual['depth_interval']=[-signed-1.5,-signed+1.5];port['depth_interval']=actual['depth_interval']
        elif abs(signed)>3:
            bounds=domain.bounds;budget=max(3.,min(bounds[2]-bounds[0],bounds[3]-bounds[1])*.05)
            normalize=(port.get('source_normalization')=='project_original_penetration_to_boundary'
                and port['profile']=='boundary_touch' and -budget<=signed<-3.)
            if not normalize:raise ValueError('Original observation does not support near-boundary contact: '+port['object']+':'+str(port['end'])+' distance='+str(signed))
            actual['source_measurement']['normalization']={'rule':'project_original_penetration_to_boundary','observed_depth_px':-signed,'maximum_source_neighborhood_px':budget}
    contract={'schema':VERSION,'source_hash':state['source']['sha256'],'source_graph':state['source_connection_graph'],
        'items':rows,'terminals':terminals,'candidate_decisions':copy.deepcopy(request.get('candidate_decisions',[])),
        'candidate_proposals':candidates(task,state,candidate)}
    path=task/'source/connections'/(identity(contract)+'.json');write_json(path,contract)
    with writer(task):
        old=state.get('connection_contract')
        if old:state.setdefault('connection_contract_history',[]).append(old)
        state['connection_contract']=a._file(task,path);state.pop('acceptance',None);a._save(task,state)
    return {'status':'ORIGINAL_CONNECTION_CONTRACTS_FROZEN','contract':a._file(task,path)}

def _load_contract(task,state,historical_ref=None):
    from .source_connections import load
    graph=None if historical_ref else load(task,state);ref=historical_ref or state.get('connection_contract')
    if historical_ref and historical_ref not in [state.get('connection_contract'),*state.get('connection_contract_history',[])]:
        raise ValueError('Historical solver replay needs its exact retained immutable connection contract')
    if not ref or not historical_ref and graph is None:raise ValueError('Original graph and compiled connection contracts required')
    path=safe_path(task,ref['path'])
    if digest(path)!=ref['sha256']:raise ValueError('Connection contract changed')
    spec=read_json(path)
    if historical_ref:
        original=spec.get('source_graph')
        if original not in [state.get('source_connection_graph'),*state.get('source_connection_graph_history',[])]:
            raise ValueError('Historical connection graph lacks retained immutable provenance')
        file=safe_path(task,original['path'])
        if digest(file)!=original['sha256']:raise ValueError('Historical original graph changed')
        graph=read_json(file)
        tree=safe_path(task,'source/recursion/revisions/'+graph['source_recursion_hash']+'.json')
        from .source_connections import VERSION as original_graph_version
        if graph.get('schema')!=original_graph_version or graph.get('source_hash')!=state['source']['sha256'] or not tree.is_file() or identity(read_json(tree))!=graph['source_recursion_hash']:
            raise ValueError('Historical original graph/tree identity changed')
    elif spec.get('source_graph')!=state['source_connection_graph']:
        raise ValueError('Recompile legacy/stale connection contracts; defaults cannot be grandfathered')
    if spec.get('schema')!=VERSION or spec.get('source_hash')!=state['source']['sha256']:raise ValueError('Unsupported or wrong-original connection contract')
    for row in spec['items']:
        for port in row['ports']:
            if port.get('source_function_boundary') and original_function_boundary(task,state,port['source_function_boundary'],port['target'],historical=bool(historical_ref))!=port['source_boundary']:
                raise ValueError('Refined original physical port boundary changed; recompile its unchanged-source evidence')
    return spec

def _boundary(entry):
    from shapely.geometry import Point,Polygon
    from shapely.affinity import affine_transform
    from .boundary_geometry import segments
    props=entry['node'].find('p:spPr',NS);p=props.find('a:prstGeom',NS) if props is not None else None
    if p is not None and p.get('prst')=='ellipse':
        m=entry['matrix'];shape=Point(.5,.5).buffer(.5,resolution=256)
        return affine_transform(shape,[m[0,0],m[0,1],m[1,0],m[1,1],m[0,2],m[1,2]])
    if p is not None and p.get('prst')=='rect':
        m=entry['matrix'];corners=np.array([[0,0,1],[1,0,1],[1,1,1],[0,1,1]])@m.T
        return Polygon(corners[:,:2])
    from .neighbor_geometry import _paths
    paths=_paths(entry,props)
    bodies=[Polygon(points) for points,closed,_ in paths if closed and len(points)>=3]
    if len(bodies)!=1:raise ValueError('Physical port needs one observed closed contour')
    shape=bodies[0]
    if not shape.is_valid or shape.area<=0:raise ValueError('Unsupported port topology; use explicit actual contour measurement')
    return shape

def _circle_marker(entry,radius):
    """Measure a native circle in saved world coordinates, not a nominal marker."""
    props=entry['node'].find('p:spPr',NS)
    preset=props.find('a:prstGeom',NS) if props is not None else None
    if preset is None or preset.get('prst')!='ellipse':raise ValueError('An actual native circular marker is required')
    matrix=entry['matrix'];x,y=matrix[:2,0],matrix[:2,1]
    a,b=float(np.linalg.norm(x)),float(np.linalg.norm(y))
    measured=(a+b)/4
    if min(a,b)<=0 or abs(a-b)>.001 or abs(float(np.dot(x,y)))>1e-6*a*b or abs(measured-radius)>.01:
        raise ValueError('Actual marker must be circular and match the frozen radius')
    return (matrix@np.array([.5,.5,1]))[:2],measured

def report(task,state,candidate):
    from shapely.geometry import Point,LineString,Polygon
    from shapely.ops import unary_union
    nodes,names=inventory(task,state,candidate);ref=state.get('connection_contract')
    if not ref:return {'passed':False,'items':[],'missing':names,'status':'SOURCE_CONNECTION_BINDINGS_REQUIRED','source_integrity':{'passed':False,'status':'ORIGINAL_GRAPH_AND_COMPILED_CONTRACT_REQUIRED'}}
    try:spec=_load_contract(task,state)
    except (ValueError,KeyError,TypeError) as error:return {'passed':False,'items':[],'missing':names,'status':'ORIGINAL_CONNECTION_BINDINGS_REQUIRED','reason':str(error)}
    covered={n for r in spec['items'] for n in r['objects']};rows=[];terminal_rows=[]
    for r in spec['items']:
        checks=[];lines={}
        for name in r['objects']:
            try:lines[name]=line(nodes[name],r.get('terminal_sites',{}).get(name));checks.append({'id':'actual_path:'+name,'passed':True,'result':lines[name]})
            except (ValueError,KeyError,TypeError) as error:checks.append({'id':'actual_path:'+name,'passed':False,'reason':str(error)})
        occluders=[]
        for name in r.get('occluders',[]):
            try:
                entry=nodes[name]
                if entry['node'].find('.//a:t',NS) is None:raise ValueError('Occluding text owner missing')
                corners=np.array([[0,0,1],[1,0,1],[1,1,1],[0,1,1]])@entry['matrix'].T
                occluders.append(Polygon(corners[:,:2]))
            except (ValueError,KeyError,TypeError) as error:checks.append({'id':'occluder:'+name,'passed':False,'reason':str(error)})
        hidden=unary_union(occluders)
        if r['mode']=='same_straight' and lines:
            start,end=np.array(r['canonical_points']);d=end-start;length=np.linalg.norm(d)
            for name,q in lines.items():
                pts=np.array(q['points']);v=pts[1]-pts[0]
                deviation=max(abs(np.cross(d/length,p-start)) for p in pts) if length>0 else float('inf')
                cross=abs(np.cross(d/length,v/max(np.linalg.norm(v),.001))) if length>0 else float('inf')
                checks.append({'id':'canonical_straight:'+name,'passed':bool(deviation<=.15 and cross<=.002),
                               'extension_offset_px':float(deviation),'normalized_direction_cross':float(cross)})
            if length>0:
                all_points=np.concatenate([np.array(q['points']) for q in lines.values()]);axis=d/length;ts=(all_points-start)@axis
                wanted_path=LineString([start+ts.min()*axis,start+ts.max()*axis]).difference(hidden)
                actual_path=unary_union([LineString(q['points']) for q in lines.values()]).difference(hidden)
                missing=wanted_path.difference(actual_path.buffer(.2)).length
                extra=actual_path.difference(wanted_path.buffer(.2)).length
                checks.append({'id':'common_visible_straight_coverage','passed':missing<=.001 and extra<=.001,
                               'missing_visible_length_px':float(missing),'extra_visible_length_px':float(extra),
                               'occluders':r.get('occluders',[]),'scope':'Only source-confirmed text masks excuse a gap; collinearity alone is insufficient'})
        if r.get('canonical_curve'):
            expected_points=_sample(r['canonical_curve']['segments'])
            actual_curves=[]
            for name,q in lines.items():
                actual_points=_sample(q['segments'])
                if len(actual_points)<2:
                    checks.append({'id':'canonical_curve:'+name,'passed':False,'status':'CURVE_SEGMENTS_REQUIRED'})
                else:actual_curves.append(LineString(actual_points))
            if len(expected_points)>=2 and actual_curves:
                expected=LineString(expected_points).difference(hidden)
                actual=unary_union(actual_curves).difference(hidden)
                error=float(expected.hausdorff_distance(actual)) if not expected.is_empty and not actual.is_empty else float('inf')
                # A source-confirmed physical terminal may extend/trim along
                # its observed terminal segment to dock to the current owner.
                # Interior bends and both terminal axes remain fixed; their
                # equality is checked independently of the attachment checks.
                docked_polyline=None
                if len(lines)==1 and r['mode']=='independent' and len(r['canonical_curve']['segments'])==1 and len(r['canonical_curve']['segments'][0]) in (3,4):
                    name,q=next(iter(lines.items()));es=np.array(r['canonical_curve']['segments'][0]);ats=q['segments']
                    if len(ats)==1 and len(ats[0])==len(es):
                        aa=np.array(ats[0]);interior=float(np.max(np.linalg.norm(es[1:-1]-aa[1:-1],axis=1)));axes=[];free_errors=[]
                        for end,si,ci in ((0,0,1),(1,-1,-2)):
                            ed=es[ci]-es[si];ad=aa[ci]-aa[si]
                            axes.append(float(abs(np.cross(ed,ad))/max(np.linalg.norm(ed)*np.linalg.norm(ad),1e-9)))
                            if next(p for p in r['ports'] if p['object']==name and p['end']==end)['profile']=='free':free_errors.append(float(np.linalg.norm(es[si]-aa[si])))
                        docked_polyline={'interior_control_error_px':interior,'terminal_axis_error':max(axes),'free_terminal_error_px':max(free_errors,default=0.),
                            'passed':interior<=.2 and max(axes)<=.002 and max(free_errors,default=0.)<=.2,
                            'scope':'Native Bezier controls fixed; contact endpoints dock along original incident tangents'}
                if len(lines)==1 and r['mode']=='independent' and all(len(p)==2 for p in r['canonical_curve']['segments']):
                    name,q=next(iter(lines.items()));es=r['canonical_curve']['segments'];ats=q['segments']
                    if len(ats)==len(es) and all(len(p)==2 for p in ats):
                        interior=max((np.linalg.norm(np.array(a[-1])-np.array(b[-1])) for a,b in zip(es[:-1],ats[:-1])),default=0.)
                        axes=[];free_errors=[]
                        for end,seg_index,point_index in ((0,0,0),(1,-1,-1)):
                            ea=np.array(es[seg_index]);aa=np.array(ats[seg_index]);ed=ea[-1]-ea[0];ad=aa[-1]-aa[0]
                            axes.append(float(abs(np.cross(ed,ad))/max(np.linalg.norm(ed)*np.linalg.norm(ad),1e-9)))
                            port=next(p for p in r['ports'] if p['object']==name and p['end']==end)
                            if port['profile']=='free':free_errors.append(float(np.linalg.norm(ea[point_index]-aa[point_index])))
                        docked_polyline={'interior_vertex_error_px':float(interior),'terminal_axis_error':max(axes),
                            'free_terminal_error_px':max(free_errors,default=0.),'scope':'Contact endpoints alone may trim or extend along their observed axes; physical attachment is checked separately'}
                        docked_polyline['passed']=interior<=.2 and max(axes)<=.002 and max(free_errors,default=0.)<=.2
                checks.append({'id':'common_visible_curve','passed':math.isfinite(error) and error<=.2,
                               'bidirectional_curve_distance_px':error if math.isfinite(error) else None,'occluders':r.get('occluders',[])})
                if docked_polyline is not None:
                    checks[-1]['terminal_docking']=docked_polyline
                    checks[-1]['passed']=bool(checks[-1]['passed'] or docked_polyline['passed'])
            else:checks.append({'id':'common_visible_curve','passed':False,'status':'CURVE_SEGMENTS_REQUIRED'})
        for name,wanted in r.get('expected_markers',{}).items():
            checks.append({'id':'source_markers:'+name,'passed':name in lines and lines[name]['markers']==wanted,
                           'expected':wanted,'actual':lines.get(name,{}).get('markers')})
        for junction in r.get('junctions',[]):
            points=[np.array(lines[p['object']]['points'][p['end']]) for p in junction['ends'] if p['object'] in lines]
            error=max((float(np.linalg.norm(p-np.array(junction['source_point']))) for p in points),default=float('inf'))
            checks.append({'id':'branch_junction:'+junction['id'],'passed':len(points)==len(junction['ends']) and error<=.2,'junction_error_px':error if math.isfinite(error) else None})
        for port in r.get('ports',[]):
            name=port.get('object',r['objects'][0]);q=lines.get(name)
            try:
                if q is None:raise ValueError('Port path missing')
                pt=Point(q['points'][port['end']]);profile=port['profile'];details={}
                if profile=='free':
                    distance=float(np.linalg.norm(np.array(q['points'][port['end']])-np.array(port['source_point'])))
                    good=distance<=3;details={'original_endpoint_distance_px':distance,'free_reason':port['free_reason']}
                elif profile=='junction_cut':
                    junction=next(j for j in r['junctions'] if j['id']==port['junction']);distance=float(pt.distance(Point(junction['source_point'])))
                    good=distance<=.2;details={'junction':junction['id'],'junction_distance_px':distance,'true_terminal':False}
                elif profile=='occlusion_cut':
                    domain=_boundary(nodes[port['occluder']]);distance=float(pt.distance(domain.boundary));good=distance<=.2
                    details={'occluder':port['occluder'],'cut_boundary_distance_px':distance,'true_terminal':False}
                else:
                    domain=_boundary(nodes[port['target']]);distance=pt.distance(domain.boundary)
                    if profile in ('boundary_touch','marker_center_on_boundary'):good=distance<=.2;details={'boundary_distance_px':distance,'contact_basis':'path terminal or explicitly observed symmetric marker center'}
                    elif profile=='intentional_gap':gap=pt.distance(domain);good=not domain.contains(pt) and port['gap_interval'][0]<=gap<=port['gap_interval'][1];details={'gap_px':gap,'expected_gap_interval':port['gap_interval']}
                    elif profile=='inside_port':good=domain.contains(pt) and port['depth_interval'][0]<=distance<=port['depth_interval'][1];details={'depth_px':distance}
                    elif profile=='circle_half_embedded':
                        center,radius=_circle_marker(nodes[port['marker_object']],port['radius_px'])
                        disk=Point(center).buffer(radius,resolution=256);ratio=disk.intersection(domain).area/disk.area
                        error=float(np.linalg.norm(center-np.array(pt.coords[0])))
                        good=.46<=ratio<=.54 and error<=.1
                        details={'embedded_area_ratio':ratio,'actual_marker_radius_px':radius,'marker_endpoint_error_px':error}
                    if profile in ('boundary_touch','marker_center_on_boundary') and q['path_kind'] in ('straight','polyline','curve'):
                        path_points=_sample(q['segments']) if q['segments'] else q['points']
                        inside_length=LineString(path_points).intersection(domain.buffer(-.01)).length
                        details['line_inside_connected_owner_px']=float(inside_length)
                        if port.get('source_incident_side')=='interior':
                            inner=_boundary(nodes[port['source_internal_target']])
                            expected_inside=domain.buffer(.025).covers(inner)
                            details['source_incident_side']='interior';details['internal_target_still_contained']=bool(expected_inside)
                            good&=expected_inside and inside_length>.2
                        else:good&=inside_length<=.2
                    if nodes[name]['tag']=='cxnSp':
                        from .native_connection_transaction import anchor_name,verify_anchor,anchor_center
                        key='stCxn' if port['end']==0 else 'endCxn';binding=nodes[name]['node'].find('p:nvCxnSpPr/p:cNvCxnSpPr/a:'+key,NS)
                        anchor=anchor_name(r['id'],port);owner=nodes.get(anchor);owner_prop=owner['node'].find('p:nvSpPr/p:cNvPr',NS) if owner else None
                        native_bound=bool(owner and verify_anchor(owner) and binding is not None and binding.get('id')==owner_prop.get('id') and binding.get('idx')=='0' and owner['parent_name']==nodes[port['target']]['parent_name'])
                        anchor_error=float(np.linalg.norm(anchor_center(owner)-np.array(pt.coords[0]))) if native_bound else None
                        native_bound&=anchor_error is not None and anchor_error<=.15
                        details.update(native_binding_passed=bool(native_bound),native_port=anchor,native_port_endpoint_error_px=anchor_error,
                            semantic_owner=port['semantic_owner'],physical_owner=port['target'])
                        good&=native_bound
                    else:details['native_binding']='native freeform/filled shape: geometry association checked; no Office connector binding claim'
                checks.append({'id':'port:'+name+':'+str(port['end']),'passed':bool(good),'profile':profile,**details})
                if profile not in ('occlusion_cut','junction_cut'):terminal_rows.append({'id':r['id']+':'+name+':'+str(port['end']),'connection':r['id'],'object':name,'end':port['end'],'passed':bool(good),'profile':profile,**details})
            except (ValueError,KeyError,TypeError) as error:checks.append({'id':'port:'+name,'passed':False,'reason':str(error)})
        rows.append({'id':r['id'],'objects':r['objects'],'mode':r['mode'],'passed':bool(checks) and all(c['passed'] for c in checks),'checks':checks})
    expected={p['id'] for p in spec['terminals']};actual={p['id'] for p in terminal_rows}
    from .source_connections import source_integrity
    integrity=source_integrity(task,state)
    from .source_connections import load as original_graph
    graph=original_graph(task,state);by_part={p:(r,n) for r in spec['items'] for p,n in zip(r['source_parts'],r['objects'])};by_row={r['id']:r for r in rows}
    primitives=[{'id':p['id'],'region':p['region'],'object':by_part[p['id']][1],'connection':by_part[p['id']][0]['id'],
        'passed':by_row[by_part[p['id']][0]['id']]['passed'],'source_measurement':p['measurement'],'source_kind':p['kind']} for p in graph['parts']]
    return {'passed':integrity['passed'] and covered==set(names) and expected==actual and all(r['passed'] for r in rows),'items':rows,
            'terminals':terminal_rows,'primitives':primitives,'source_integrity':integrity,'candidate_decisions':spec['candidate_decisions'],
            'terminal_coverage':{'passed':expected==actual,'missing':sorted(expected-actual),'unexpected':sorted(actual-expected)},
            'missing':sorted(set(names)-covered),'unexpected':sorted(covered-set(names)),'source_hash':spec['source_hash'],'contract':ref}

def _sample(segments):
    points=[]
    for controls in segments:
        if len(controls) not in (2,3,4):raise ValueError('Finite linear/quadratic/cubic path required')
        for t in np.linspace(0,1,257):
            p=np.array(controls,float)
            while len(p)>1:p=p[:-1]*(1-t)+p[1:]*t
            points.append(p[0].tolist())
    return points

def execute(task,request):
    from .native_connection_transaction import execute as native_execute
    return native_execute(task,request)


def guard(task,state,candidate,approved,_chain_only=False):
    from .native_connection_transaction import replay
    record=next((r for r in reversed(state.get('connection_attempts',[])) if r['candidate']==candidate['pptx']['sha256']),None)
    if record is None or not record.get('proof'):return {'passed':False,'objects':[],'reason':'No exact original-derived connection transaction'}
    prior=record['baseline']
    if prior['pptx']!=approved['pptx']:
        from .source_layout_actions import guard as predecessor_guard
        previous=predecessor_guard(task,state,prior,approved,_chain_only=True)
        proof={'passed':previous['passed'],'constructor':previous}
        if not previous['passed']:return {'passed':False,'objects':[],'reason':'Prior source constructor replay failed','predecessor_result':previous}
    else:proof={'constructor':{'objects':[]}}
    good=replay(task,state,candidate,record)
    measured={'items':[]} if _chain_only else report(task,state,candidate)
    targeted=[r for r in measured.get('items',[]) if r['id'] in record['connections']]
    return {'passed':good,'targeted_geometry_passed':len(targeted)==len(record['connections']) and all(r['passed'] for r in targeted),
        'objects':sorted(set(record['allowed'])|set(proof.get('constructor',{}).get('objects',[]))),
        'method':'deterministic_native_connection_replay','resources_unchanged':record['proof']['protected_resources'],
        'scope':'Exact constructor replay protects native/pixel changes. Current geometry and all obligations independently gate acceptance; historical solver replay is not current quality approval.'}

def node_graph_items(contract,nodes):
    """Explicit source-normalized binary scientific edges, never icon names."""
    rows=[]
    for row in contract.get('items',[]):
        ports=row.get('ports',[])
        if row.get('axis_policy')!='between_physical_ports' or len(row['objects'])!=1 or len(ports)!=2:continue
        if row['mode']!='independent' or any(p['profile']!='boundary_touch' for p in ports) or len({p['semantic_owner'] for p in ports})!=1:continue
        if all(nodes.get(p['target'],{}).get('node') is not None and nodes[p['target']]['node'].find('p:spPr/a:prstGeom',NS) is not None and nodes[p['target']]['node'].find('p:spPr/a:prstGeom',NS).get('prst')=='ellipse' for p in ports):rows.append(row)
    return rows
