"""Original-only connection observations and program-measured hypotheses.

This module never reads a candidate PPTX. Host observations select source
strokes, occluders and semantic owners; programs fit, enumerate and reconcile.
Absence of arrowheads is evidence, not a prerequisite for continuation.
"""
import copy, math
from pathlib import Path
import numpy as np
from .common import identity,digest,read_json,write_json,safe_path,writer

VERSION='source-connections-2'
MARKERS={'none','arrow','triangle','oval','diamond','stealth','hidden','uncertain'}
PROFILES={'boundary_touch','intentional_gap','circle_half_embedded','marker_center_on_boundary','inside_port','free','occlusion_cut','junction_cut'}

def _source(task,state):
    file=safe_path(task,state['source']['path'])
    if digest(file)!=state['source']['sha256']:raise ValueError('Original pixels changed')
    from PIL import Image
    with Image.open(file) as im:return np.asarray(im.convert('RGB'))

def survey(task,state):
    """Raw CPU line proposals; role/semantic decisions remain with the host."""
    import cv2
    rgb=_source(task,state);gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    found=cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(gray)[0]
    segments=[]
    for i,raw in enumerate([] if found is None else found.reshape(-1,4)):
        pts=raw.reshape(2,2);length=float(np.linalg.norm(pts[1]-pts[0]))
        if length>=6:segments.append({'id':'stroke-'+str(i),'points':pts.tolist(),'length_px':length})
    result={'schema':VERSION,'source_hash':state['source']['sha256'],'segments':segments,
            'scope':'Original raw pixels only. Text strokes, icon internals, table rules, curves and connectors must be classified through original recursive regions; LSD alone is not semantic completeness.'}
    path=task/'source/connections/survey'/ (identity(result)+'.json');write_json(path,result)
    return {'path':path.relative_to(task).as_posix(),'sha256':digest(path),'source_hash':state['source']['sha256']}

def _roi(roi,size):
    if len(roi)!=4 or any(not math.isfinite(float(v)) for v in roi):raise ValueError('Finite original ROI required')
    x,y,w,h=roi
    if min(x,y)<0 or min(w,h)<=0 or x+w>size[0]+.001 or y+h>size[1]+.001:raise ValueError('Original ROI outside source')
    return [float(v) for v in roi]

def fit_stroke(rgb,part):
    """Fit original ink within a host-selected stroke corridor, excluding tips."""
    hint=np.array(part['source_points'],float);d=hint[1]-hint[0];length=float(np.linalg.norm(d))
    if hint.shape!=(2,2) or length<1:raise ValueError('Two original stroke landmarks required')
    d/=length;normal=np.array([-d[1],d[0]])
    pixels=[];colour=np.array([int(part['colour'][i:i+2],16) for i in (0,2,4)])
    for roi in part.get('fit_rois',[]):
        x,y,w,h=roi;x0,y0=math.floor(x),math.floor(y);x1,y1=math.ceil(x+w),math.ceil(y+h)
        crop=rgb[y0:y1,x0:x1].astype(float)
        mask=(crop.max(axis=2)<200)&(np.ptp(crop,axis=2)<45) if colour.max()<50 else np.linalg.norm(crop-colour,axis=2)<=80
        yy,xx=np.nonzero(mask);pts=np.c_[xx+x0+.5,yy+y0+.5]
        # Hints locate original evidence; the result comes from actual ink.
        pts=pts[np.abs((pts-hint[0])@normal)<=part.get('corridor_px',4)]
        if len(pts):pixels.extend(pts.tolist())
    if len(pixels)<8:raise ValueError('Original stroke cannot be fitted: '+part['id'])
    pts=np.array(pixels);center=np.median(pts,axis=0)
    for _ in range(3):
        _,_,vh=np.linalg.svd(pts-center,full_matrices=False);axis=vh[0]
        if np.dot(axis,d)<0:axis=-axis
        residual=np.abs((pts-center)@np.array([-axis[1],axis[0]]))
        keep=residual<=max(1.2,float(np.quantile(residual,.8)))
        pts=pts[keep];center=pts.mean(0)
    points=[(center+np.dot(p-center,axis)*axis).tolist() for p in hint]
    bin_count=max(4,min(20,math.floor(length)))
    spans=np.floor(np.clip((pts-hint[0])@d/length,0,.999)*bin_count).astype(int)
    coverage=len(set(spans[(spans>=1)&(spans<=bin_count-2)]))/(bin_count-2)
    if coverage<.55:raise ValueError('Original straight shaft reobservation required; low full-stroke coverage: '+part['id'])
    return {'points':points,'origin':center.tolist(),'direction':axis.tolist(),'stroke_coverage':coverage,
            'ink_pixels':len(pts),'residual_rms_px':float(np.sqrt(np.mean(((pts-center)@np.array([-axis[1],axis[0]]))**2))),
            'method':'original_colour_corridor_robust_TLS','fit_rois':part['fit_rois']}

def fit_quadratic_stroke(rgb,part):
    """Fit the whole source shaft, with explicit support across its length.

    Source classification/landmarks belong to the model. Pixel selection,
    coverage, robust fit and residuals belong to the deterministic program.
    """
    from scipy.ndimage import label
    hint=np.array(part['source_points'],float);d=hint[1]-hint[0];length=float(np.linalg.norm(d))
    if hint.shape!=(2,2) or length<8:raise ValueError('Two separated original curve landmarks required')
    d/=length;normal=np.array([-d[1],d[0]]);pixels=[]
    colour=np.array([int(part['colour'][i:i+2],16) for i in (0,2,4)])
    for roi in part['fit_rois']:
        x,y,w,h=roi;x0,y0=math.floor(x),math.floor(y);crop=rgb[y0:math.ceil(y+h),x0:math.ceil(x+w)].astype(float)
        yy,xx=np.indices(crop.shape[:2]);coords=np.stack((xx+x0+.5,yy+y0+.5),axis=-1)
        t=(coords-hint[0])@d/length;n=(coords-hint[0])@normal
        ink=(crop.max(axis=2)<200)&(np.ptp(crop,axis=2)<45) if colour.max()<50 else np.linalg.norm(crop-colour,axis=2)<=80
        mask=ink&(t>=.06)&(t<=.85)&(np.abs(n)<=min(14,max(4,length*.18)))
        components,count=label(mask,np.ones((3,3)))
        supports=[]
        for k in range(1,count+1):
            pts=coords[components==k]
            if len(pts)>=4:supports.append((float(np.ptp((pts-hint[0])@d)),pts))
        if supports:pixels.extend(max(supports,key=lambda q:q[0])[1].tolist())
    if len(pixels)<12:raise ValueError('Original curve shaft support is insufficient: '+part['id'])
    pts=np.unique(np.array(pixels),axis=0);along=(pts-hint[0])@d/length;offset=(pts-hint[0])@normal
    bins=np.floor(along*length).astype(int);unique=np.unique(bins)
    ts=np.array([np.median(along[bins==b]) for b in unique]);ns=np.array([np.median(offset[bins==b]) for b in unique])
    coverage=len(unique)/max(1,math.floor(.79*length))
    if coverage<.60:raise ValueError('Source curve reobservation required: incomplete whole-shaft coverage '+part['id'])
    basis=2*ts*(1-ts);keep=np.ones(len(ts),bool)
    for _ in range(4):
        bend=float(np.dot(basis[keep],ns[keep])/np.dot(basis[keep],basis[keep]));residual=ns-basis*bend
        keep=np.abs(residual)<=max(1.5,float(np.quantile(np.abs(residual),.85)))
    rms=float(np.sqrt(np.mean(residual[keep]**2)))
    if rms>2:raise ValueError('Source curve requires a richer fit or clearer observation: '+part['id'])
    controls=[hint[0].tolist(),((hint[0]+hint[1])/2+normal*bend).tolist(),hint[1].tolist()]
    return {'points':hint.tolist(),'segments':[controls],'stroke_coverage':min(1.,coverage),
        'residual_rms_px':rms,'ink_pixels':len(pts),'supported_bins':len(unique),'minimum_coverage':.60,
        'method':'original_connected_shaft_bin_medians_quadratic_fit','fit_rois':part['fit_rois']}

def annotation_axis(segments,center,parameter=None):
    """Local tangent nearest an annotation; parameter is frozen from source."""
    from .connection_geometry import _sample
    points=np.array(_sample(segments),float)
    if len(points)<3:raise ValueError('Observed annotation path samples required')
    index=int(round(float(parameter)*(len(points)-1))) if parameter is not None else int(np.argmin(np.linalg.norm(points-np.array(center),axis=1)))
    index=max(1,min(len(points)-2,index));d=points[index+1]-points[index-1];d/=np.linalg.norm(d)
    return [points[index].tolist(),(points[index]+d).tolist()],index/(len(points)-1)

def original_domain(rgb,geometry):
    from shapely.geometry import Point,Polygon
    from shapely.affinity import scale,translate,rotate
    kind=geometry['kind'];proof={}
    if kind in ('rect','ellipse'):
        x,y,w,h=geometry['bbox'];domain=Polygon([[x,y],[x+w,y],[x+w,y+h],[x,y+h]]) if kind=='rect' else translate(scale(Point(0,0).buffer(1,resolution=256),w/2,h/2),x+w/2,y+h/2)
    elif kind=='polygon':domain=Polygon(geometry['points'])
    elif kind=='fitted_ellipse':
        import cv2
        x,y,w,h=geometry['bbox'];x,y=math.floor(x),math.floor(y);crop=rgb[y:math.ceil(y+h),x:math.ceil(x+w)]
        ink=(crop.max(axis=2)<90).astype('uint8')*255
        contours,_=cv2.findContours(ink,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
        contours=[c for c in contours if len(c)>=12]
        if not contours:raise ValueError('Original ellipse contour cannot be measured')
        points=max(contours,key=cv2.contourArea).reshape(-1,2).astype('float32')
        for _ in range(4):
            (cx,cy),(aw,ah),angle=cv2.fitEllipse(points.reshape(-1,1,2));theta=math.radians(angle)
            local=(points-[cx,cy])@np.array([[math.cos(theta),-math.sin(theta)],[math.sin(theta),math.cos(theta)]])
            radius=np.sqrt((local[:,0]/(aw/2))**2+(local[:,1]/(ah/2))**2)
            good=np.abs(radius-1)<=max(.025,float(np.quantile(np.abs(radius-1),.80)))
            if sum(good)<12:raise ValueError('Unstable original ellipse fit')
            points=points[good]
        domain=translate(rotate(scale(Point(0,0).buffer(1,resolution=512),aw/2,ah/2),angle,origin=(0,0)),x+cx,y+cy)
        proof={'method':'original_black_outer_contour_robust_ellipse_fit','center':[x+cx,y+cy],'axes':[aw,ah],'rotation_deg':angle,'contour_points':len(points)}
    else:raise ValueError('Finite observed original port contour required')
    if not domain.is_valid or domain.area<=0:raise ValueError('Invalid original physical contour')
    return domain,proof

def original_filled_bounds(task,state,part):
    """Original colour support, independently of legacy manual paint boxes."""
    from scipy.ndimage import label,find_objects
    rgb=_source(task,state);x,y,w,h=_roi(part['roi'],state['source_size']);x0,y0=math.floor(x),math.floor(y)
    crop=rgb[y0:math.ceil(y+h),x0:math.ceil(x+w)].astype(float)
    colour=np.array([int(part['colour'][i:i+2],16) for i in (0,2,4)])
    method='original_colour_connected_support'
    if part.get('colour_domain')=='hue_family':
        import cv2
        hsv=cv2.cvtColor(crop.astype('uint8'),cv2.COLOR_RGB2HSV)
        reference=cv2.cvtColor(colour.astype('uint8').reshape(1,1,3),cv2.COLOR_RGB2HSV)[0,0]
        if reference[1]<32:raise ValueError('Hue support requires an independently classified chromatic source owner')
        distance=np.abs(hsv[:,:,0].astype(float)-float(reference[0]));distance=np.minimum(distance,180-distance)
        ink=((distance<=18)&(hsv[:,:,1]>=32)&(hsv[:,:,2]>=35)).astype('uint8')
        method='original_hue_family_connected_support'
    elif part.get('colour_domain') not in (None,'rgb'):raise ValueError('Unknown original colour support domain')
    else:ink=(np.linalg.norm(crop-colour,axis=2)<=65).astype('uint8')
    appendage_radius=0
    if part.get('support_kind')=='closed_body':
        import cv2
        # A same-colour attached shaft must not enlarge its physical owner.
        # Opening identifies the area-bearing body; dilation restores its
        # boundary, within the recorded original localization uncertainty.
        appendage_radius=max(1,math.ceil(min(w,h)*.04))
        kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*appendage_radius+1,)*2)
        core=cv2.morphologyEx(ink,cv2.MORPH_OPEN,kernel)
        if not core.any():raise ValueError('Closed source body lacks stable area support; refine its source crop')
        ink=cv2.dilate(core,kernel)&ink
        method+=':area_body_without_thin_appendages'
    elif part.get('support_kind') is not None:raise ValueError('Unknown source support geometry class')
    labels,count=label(ink,structure=np.ones((3,3),dtype='uint8'))
    if count<1:raise ValueError('Original filled-connection colour support unavailable')
    areas=np.bincount(labels.ravel());index=1+int(np.argmax(areas[1:]));area=areas[index]
    yy,xx=find_objects(labels)[index-1];ww,hh=xx.stop-xx.start,yy.stop-yy.start;xx,yy=xx.start,yy.start
    if area<8:raise ValueError('Original filled-connection source support is too small')
    return {'bounds':[int(x0+xx),int(y0+yy),int(ww),int(hh)],'source_hash':state['source']['sha256'],
        'part':part['id'],'roi':part['roi'],'colour':part['colour'],'support_pixels':int(area),
        'method':method,'thin_appendage_radius_px':appendage_radius,'uncertainty_px':max(1,appendage_radius)}

def _pair_candidates(parts,texts):
    proposals=[]
    straight=[p for p in parts if p['kind']=='straight']
    for i,a in enumerate(straight):
        for b in straight[i+1:]:
            pa=np.array(a['measurement']['points'],float);pb=np.array(b['measurement']['points'],float)
            da=pa[1]-pa[0];db=pb[1]-pb[0];da/=np.linalg.norm(da);db/=np.linalg.norm(db)
            cross=abs(float(da[0]*db[1]-da[1]*db[0]));n=np.array([-da[1],da[0]])
            offset=float(np.max(np.abs((pb-pa[0])@n)))
            # Source blur tolerance is separate from saved-path tolerance.
            if cross>.20 or offset>8:continue
            for text in texts:
                x,y,w,h=text['roi'];corners=np.array([[x,y],[x+w,y],[x+w,y+h],[x,y+h]])
                center=corners.mean(0);ma=float((pa.mean(0)-center)@da);mb=float((pb.mean(0)-center)@da)
                if ma*mb>=0:continue
                nr=corners@n;axis=float(pa[0]@n)
                if not nr.min()-3<=axis<=nr.max()+3:continue
                near_a=min(np.linalg.norm(p-center) for p in pa);near_b=min(np.linalg.norm(p-center) for p in pb)
                if max(near_a,near_b)>max(w,h)+20:continue
                proposals.append({'id':'pair-'+identity([a['id'],b['id'],text['id']])[:20],
                    'parts':[a['id'],b['id']],'occluder':text['id'],'opposite_text_sides':True,
                    'direction_cross_abs':cross,'extension_offset_px':offset,
                    'styles_compatible':a['colour']==b['colour'],
                    'marker_evidence':[a['markers'],b['markers']],
                    'scope':'Original-only candidate. Marker absence does not eliminate it; no automatic merge.'})
    return proposals

def original_annotation_support(task,state,observation):
    """Measure original annotation ink, excluding its observed line shaft."""
    from PIL import Image
    from .neighbor_geometry import _matte_pixels
    graph=load(task,state);part=next(p for p in graph['parts'] if p['id']==observation['part'])
    if part['kind'] not in ('straight','curve') or observation.get('side') not in (-1,1):raise ValueError('Original annotated edge and observed side required')
    rgb=_source(task,state);x,y,w,h=_roi(observation['roi'],state['source_size']);x,y=math.floor(x),math.floor(y)
    crop=rgb[y:math.ceil(y+h),x:math.ceil(x+w)];yy,xx=np.indices(crop.shape[:2]);points=np.array(part['measurement']['points'])
    parameter=None
    if part['kind']=='curve':
        from scipy.spatial import cKDTree
        from .connection_geometry import _sample
        axis,parameter=annotation_axis(part['source_segments'],[x+w/2,y+h/2]);points=np.array(axis)
        coords=np.c_[xx.ravel()+x+.5,yy.ravel()+y+.5]
        distances=cKDTree(_sample(part['source_segments'])).query(coords)[0].reshape(xx.shape)
    else:
        d=points[1]-points[0];normal=np.array([-d[1],d[0]])/np.linalg.norm(d)
        distances=(xx+x-points[0,0])*normal[0]+(yy+y-points[0,1])*normal[1]
    mask=((crop.max(axis=2)<150)&(np.abs(distances)>2.5)).astype('uint8')*255
    if np.count_nonzero(mask)<8:raise ValueError('Original annotation ink requires a clearer/tighter source crop')
    file=Path(task)/'source/annotations'/(identity({'source':state['source'],'graph':state['source_connection_graph'],'observation':observation,'mask':identity(mask.tolist())})+'.png')
    file.parent.mkdir(parents=True,exist_ok=True)
    if not file.exists():Image.fromarray(mask).save(file)
    from shapely.affinity import translate
    geometry=translate(_matte_pixels(str(file),digest(file),tuple(mask.shape[::-1])),xoff=x,yoff=y)
    bounds=geometry.bounds
    return {'source_hash':state['source']['sha256'],'source_graph':state['source_connection_graph'],'part':part['id'],
        'original_line':points.tolist(),'parameter':parameter,'source_geometry':geometry.wkt,'source_bounds':[bounds[0],bounds[1],bounds[2]-bounds[0],bounds[3]-bounds[1]],
        'mask':{'path':file.relative_to(task).as_posix(),'sha256':digest(file)},'method':'original_dark_annotation_ink_excluding_observed_shaft','observation':observation}

def compile_observation(task,state,request):
    from .source_contract import finite
    finite(request,'original_connections')
    if request.get('source_hash')!=state['source']['sha256']:raise ValueError('Original connection identity mismatch')
    if not request.get('region_coverage') or not request.get('source_recursion_hash'):raise ValueError('Original recursive region coverage is required, including regions without connections')
    from .source_recursion import load
    tree=load(task,state)
    if not tree or request['source_recursion_hash']!=identity(tree):raise ValueError('Connection survey must bind the independently discovered original tree')
    coverage=request['region_coverage'];regions={r['region'] for r in coverage}
    if regions!=set(tree['nodes']) or len(regions)!=len(coverage):raise ValueError('Every original recursive region needs one located connection survey decision')
    if any(r.get('decision') not in ('connections','no_connections','delegated') or not r.get('evidence') for r in coverage):raise ValueError('Explicit original region decisions required')
    rgb=_source(task,state);parts=copy.deepcopy(request.get('parts',[]));texts=copy.deepcopy(request.get('texts',[]))
    ids=[p.get('id') for p in parts]
    if len(ids)!=len(set(ids)):raise ValueError('Unique original primitive identities required')
    for p in parts:
        _roi(p['roi'],state['source_size'])
        if p.get('region') not in regions or p.get('kind') not in ('straight','curve','polyline','filled_arrow') or not p.get('evidence'):
            raise ValueError('Located original primitive and semantic reading required')
        relation=p.get('relation')
        if relation and (not relation.get('role') or relation.get('source_region') not in regions or relation.get('target_region') not in regions):raise ValueError('An original semantic relation must reference observed source regions')
        if set(p.get('markers',{}))!={'headEnd','tailEnd'} or any(v not in MARKERS for v in p['markers'].values()):raise ValueError('Both original marker visibility states required')
        if any(v in ('hidden','uncertain') for v in p['markers'].values()):raise ValueError('Uncertain/hidden terminal marker needs further original observation before freezing')
        if p['kind']=='curve' and p.get('source_fit',{}).get('kind')=='original_quadratic_stroke':
            for roi in p.get('fit_rois',[]):_roi(roi,state['source_size'])
            p['measurement']=fit_quadratic_stroke(rgb,p);p['source_segments']=p['measurement']['segments']
        if p['kind'] in ('curve','polyline'):
            controls=[]
            for segment in p.get('source_segments',[]):
                values=segment.get('points') if isinstance(segment,dict) else segment
                if (not isinstance(values,list) or len(values) not in ((2,) if p['kind']=='polyline' else (2,3,4))
                        or any(not isinstance(q,list) or len(q)!=2 for q in values)):
                    raise ValueError('Typed original linear/Bezier control points required')
                controls.append(copy.deepcopy(values))
            p['source_segments']=controls
        for refinement in p.get('terminal_refinements',[]):
            from shapely.geometry import Point,LineString
            end=refinement.get('end')
            if (end not in (0,1) or p['markers']['headEnd' if end==0 else 'tailEnd']!='none' or
                    refinement.get('rule')!='unmarked_shaft_at_observed_owner_boundary' or not refinement.get('source_evidence')):
                raise ValueError('Source-terminal refinement requires an unmarked observed physical owner association')
            domain,proof=original_domain(rgb,refinement['source_boundary'])
            edge=(p['source_segments'][0] if end==0 else p['source_segments'][-1]) if p['kind']=='polyline' else p['source_points']
            if len(edge)!=2:raise ValueError('Source terminal refinement requires its observed incident straight segment')
            origin=np.array(edge[0 if end==0 else -1]);depth=Point(origin).distance(domain.boundary)
            bounds=domain.bounds;budget=max(2.,min(bounds[2]-bounds[0],bounds[3]-bounds[1])*.15)
            if not domain.covers(Point(origin)) or depth>budget:raise ValueError('Source shaft is not locally merged into its observed owner; refine the original crop')
            cuts=LineString(edge).intersection(domain.boundary)
            candidates=list(cuts.geoms) if hasattr(cuts,'geoms') else [cuts]
            points=[v for v in candidates if v.geom_type=='Point']
            if not points:raise ValueError('Observed source incident shaft does not cross its associated owner boundary')
            measured=min(points,key=lambda v:v.distance(Point(origin)));located=list(measured.coords[0])
            p['source_points'][end]=located
            if p['kind']=='polyline':edge[0 if end==0 else -1]=located
            refinement['measurement']={'original_landmark':origin.tolist(),'boundary_landmark':located,'displacement_px':depth,
                'method':'original_incident_segment_intersection_with_original_owner','contour':proof}
        if p['kind']=='straight':
            for roi in p.get('fit_rois',[]):_roi(roi,state['source_size'])
            p['measurement']=fit_stroke(rgb,p)
        else:
            if not p.get('source_points') or len(p['source_points'])!=2:raise ValueError('Original endpoints required for each non-straight primitive')
            if p.get('source_fit',{}).get('kind')!='original_quadratic_stroke':
                p['measurement']={'points':p['source_points'],'method':'located_original_landmarks','source_evidence':p['evidence']}
            if p['kind'] in ('curve','polyline') and not p.get('source_segments'):raise ValueError('Original function/path controls required; no straight replacement')
    if len({t['id'] for t in texts})!=len(texts):raise ValueError('Unique original occluders required')
    for t in texts:
        _roi(t['roi'],state['source_size'])
        if not t.get('evidence') or t.get('kind') not in ('text','opaque_container'):raise ValueError('Original occluder meaning required')
    result={'schema':VERSION,'source_hash':state['source']['sha256'],'source_recursion_hash':identity(tree),
            'region_coverage':coverage,'parts':parts,'texts':texts,'candidate_pairs':_pair_candidates(parts,texts),
            'raw_survey':survey(task,state),'original_observation':copy.deepcopy(request)}
    return result

def observe(task,request):
    from . import agent_runtime as a
    task,state=a._state(task);graph=compile_observation(task,state,request)
    path=task/'source/connections/original'/(identity(graph)+'.json');write_json(path,graph)
    with writer(task):
        old=state.get('source_connection_graph')
        if old:state.setdefault('source_connection_graph_history',[]).append(old)
        state['source_connection_graph']=a._file(task,path);state.pop('acceptance',None);state.pop('quality_result',None);a._save(task,state)
    return {'status':'ORIGINAL_CONNECTION_GRAPH_FROZEN','graph':a._file(task,path),'candidates':graph['candidate_pairs']}

def refinement_coverage(task,state,graph,tree):
    """Preserve frozen scientific edges across audited icon-internal refinement.

    No source ROI, prior fact or scientific primitive may be changed by this
    bridge. Newly found scientific/uncertain lines reopen source observation.
    Only located, explicitly classified anatomy with executable detail facts
    can inherit the earlier original-only survey. Immutable native anchors and
    physical terminal checks still run against the current saved result.
    """
    file=task/'source/recursion/revisions'/(graph['source_recursion_hash']+'.json')
    if not file.is_file():return {'passed':False,'reason':'Earlier independent original tree unavailable'}
    old=read_json(file)
    if identity(old)!=graph['source_recursion_hash']:return {'passed':False,'reason':'Earlier original tree changed'}
    facts=state.get('source_detail_contracts',{}).get('units',{})
    if set(old['nodes'])-set(tree['nodes']):return {'passed':False,'reason':'Earlier original region was removed'}
    rows=[]
    protected=('id','parent','roi','owner','role','source_parts','semantic_class','observed_content','representation','leaf_type')
    for key,previous in old['nodes'].items():
        current=tree['nodes'][key]
        if any(current.get(k)!=previous.get(k) for k in protected):return {'passed':False,'reason':'Original region structure/content changed: '+key}
        if not set(previous['children'])<=set(current['children']):return {'passed':False,'reason':'Original source child removed: '+key}
        retained=[f for f in current['critical_features'] if not f.get('source_detail')]
        if retained!=previous['critical_features']:return {'passed':False,'reason':'Original feature changed: '+key}
    for key in sorted(set(tree['nodes'])-set(old['nodes'])):
        node=tree['nodes'][key];uid=node.get('source_detail_parent');part=node.get('source_detail_part')
        finding=next((p for p in facts.get(uid,{}).get('observed_parts',[]) if p['id']==part),None)
        good=bool(finding and finding.get('connection_role') in ('none','internal_geometry')
                  and finding['roi']==node['roi'] and node['parent']=='unit:'+uid
                  and finding['objects']==node['representation']['objects'] and facts[uid]['checks'])
        rows.append({'region':key,'passed':good,'source_parent':uid,'connection_role':finding.get('connection_role') if finding else None})
    # Re-observation can add facts without another source child (same-size ROI).
    for uid,c in facts.items():
        if any(p.get('connection_role') not in ('none','internal_geometry') for p in c['observed_parts']):
            return {'passed':False,'reason':'New scientific/uncertain connection requires original survey: '+uid,'items':rows}
    return {'passed':all(r['passed'] for r in rows),'items':rows,'scope':'Unchanged original scientific graph, explicit internal-detail facts, exact retained region ancestry'}

def load(task,state):
    ref=state.get('source_connection_graph')
    if not ref:return None
    path=safe_path(task,ref['path'])
    if digest(path)!=ref['sha256']:raise ValueError('Frozen original connection graph changed')
    graph=read_json(path)
    from .source_recursion import load as recursion
    tree=recursion(task,state)
    compatible=bool(tree and (graph['source_recursion_hash']==identity(tree) or refinement_coverage(task,state,graph,tree)['passed']))
    if graph.get('schema')!=VERSION or graph['source_hash']!=state['source']['sha256'] or not compatible:
        raise ValueError('Original connection graph is stale; repeat independent source survey')
    return graph

def packet(task,state):
    try:graph=load(task,state)
    except (ValueError,KeyError):graph=None
    if graph:return None
    from .source_recursion import load as recursion
    tree=recursion(task,state)
    if not tree:return None
    from .quality_intent import source_view
    return {'kind':'source_connection_observation','source_hash':state['source']['sha256'],
        'source_recursion_hash':identity(tree),'raw_survey':survey(task,state),
        'regions':[{'region':k,'roi':v['roi'],'view':source_view(task,state,v['roi'])} for k,v in tree['nodes'].items()],
        'action':'connection-geometry observe-source',
        'return':'source_hash, source_recursion_hash, region_coverage[{region,decision,evidence}], parts[{id,region,roi,kind,colour,source_points,fit_rois,markers{headEnd,tailEnd},evidence,source_segments?}], texts[{id,roi,kind,evidence}]',
        'scope':'Read original child views. Connections include plain unmarked lines, paths behind multiple texts, curves, branches and internal scientific edges. Every region must be classified, not only changed parts.'}

def reconcile(graph,rows,decisions):
    """Exact equality of original primitive set and all proposed pair decisions."""
    parts={p['id']:p for p in graph['parts']};bound=[p for r in rows for p in r.get('source_parts',[])]
    if set(bound)!=set(parts) or len(bound)!=len(set(bound)):raise ValueError('Every original connection primitive must map once; output-only coverage cannot substitute')
    expected={c['id'] for c in graph['candidate_pairs']};actual={d.get('candidate') for d in decisions}
    if expected!=actual or len(actual)!=len(decisions):raise ValueError('Every original continuation candidate requires one explicit source decision')
    by_part={p:r for r in rows for p in r['source_parts']}
    for decision in decisions:
        c=next(c for c in graph['candidate_pairs'] if c['id']==decision['candidate'])
        if decision.get('mode') not in ('same_straight','same_curve','independent','branch') or not decision.get('reason') or not decision.get('evidence_rois'):
            raise ValueError('Located original reasoning required for every continuation decision')
        ra,rb=[by_part[p] for p in c['parts']]
        if decision['mode']=='independent':
            facts=decision.get('distinguishing_facts',[])
            if ra['id']==rb['id'] or not facts:raise ValueError('Independent rejection needs distinct source paths and specific distinguishing facts')
            pp=[parts[p] for p in c['parts']];verified=[]
            for fact in facts:
                if not isinstance(fact,dict):raise ValueError('Independent rejection requires typed, program-verifiable original facts; boilerplate strings cannot close it')
                kind=fact.get('kind')
                if kind=='original_style_difference':verified.append(pp[0]['colour']!=pp[1]['colour'])
                elif kind=='source_relation_difference':verified.append(all(p.get('relation') for p in pp) and pp[0]['relation']!=pp[1]['relation'])
                elif kind=='interior_terminal_mark':
                    text=next(t for t in graph['texts'] if t['id']==c['occluder']);x,y,w,h=text['roi'];center=np.array([x+w/2,y+h/2])
                    p=next((p for p in pp if p['id']==fact.get('part')),None)
                    if p is None:verified.append(False);continue
                    index=int(np.argmin([np.linalg.norm(np.array(q)-center) for q in p['measurement']['points']]))
                    verified.append(p['markers']['headEnd' if index==0 else 'tailEnd'] not in ('none','hidden','uncertain'))
                else:raise ValueError('Unregistered independent source fact')
            if not all(verified):raise ValueError('Independent rejection contradicts original program evidence')
        elif ra['id']!=rb['id'] or ra['mode']!=decision['mode']:raise ValueError('Source pair decision and logical connection disagree')
    terminals=[]
    for row in rows:
        pp=[parts[p] for p in row['source_parts']]
        if len(pp)!=len(row['objects']):raise ValueError('Each saved fragment maps to one original primitive')
        if row['mode']=='same_straight':
            points=np.concatenate([np.array(p['measurement']['points']) for p in pp])
            center=points.mean(0);_,_,vh=np.linalg.svd(points-center,full_matrices=False);d=vh[0]
            ts=(points-center)@d
            row['canonical_points']=[(center+ts.min()*d).tolist(),(center+ts.max()*d).tolist()]
        row['expected_markers']={name:p['markers'] for name,p in zip(row['objects'],pp)}
        row['terminal_sites']={name:p['terminal_sites'] for name,p in zip(row['objects'],pp) if p.get('terminal_sites')}
        row['source_paths']={name:p['measurement']['points'] for name,p in zip(row['objects'],pp)}
        curves=[p for p in pp if p['kind'] in ('curve','polyline')]
        if curves:
            controls=[segment for p in curves for segment in p['source_segments']]
            if row.get('canonical_curve') and row['canonical_curve']['segments']!=controls:raise ValueError('Curve controls disagree with independently frozen original functions')
            row['canonical_curve']={'segments':copy.deepcopy(controls),'source_basis':[p['id'] for p in curves]}
        if row['mode']=='branch':
            if len(pp)<3 or not row.get('junctions'):raise ValueError('A branch requires located original junctions, not just a label')
            junctions=row['junctions'];keys=[j.get('id') for j in junctions]
            if len(keys)!=len(set(keys)):raise ValueError('Unique original junction identities required')
            for j in junctions:
                if not j.get('source_evidence') or len(j.get('ends',[]))<3:raise ValueError('Original junction requires at least three observed arms')
                for endpoint in j['ends']:
                    name,end=endpoint['object'],endpoint['end']
                    p=next(p for p in pp if row['objects'][pp.index(p)]==name)
                    if np.linalg.norm(np.array(p['source_points'][end])-np.array(j['source_point']))>3:raise ValueError('Original branch arm does not reach its observed junction')
        cuts=[]
        for port in row['ports']:
            name=port['object'];end=port['end'];part=pp[row['objects'].index(name)]
            # Tip/marker center is an independent original landmark. A shaft
            # fit must not silently relocate it, especially at graph crossings.
            port['source_point']=part['source_points'][end]
            if port['profile']=='junction_cut':
                if row['mode']!='branch' or not any(j['id']==port.get('junction') and {'object':name,'end':end} in j['ends'] for j in row['junctions']):raise ValueError('Interior branch cut needs its observed logical junction')
                if part['markers']['headEnd' if end==0 else 'tailEnd']!='none':raise ValueError('A branch interior cannot hide an original terminal marker')
            elif port['profile']=='occlusion_cut':
                cuts.append(port)
                if port.get('occluder') not in row.get('occluders',[]) or part['markers']['headEnd' if end==0 else 'tailEnd']!='none':raise ValueError('Occlusion cut is not a free terminal or a marked endpoint')
            else:
                marker=part['markers']['headEnd' if end==0 else 'tailEnd']
                port['marker']=marker;terminals.append({'id':row['id']+':'+name+':'+str(end),'connection':row['id'],**port})
        if row['mode'] in ('same_straight','same_curve') and len(cuts)!=2*(len(pp)-1):raise ValueError('Logical path needs exactly two true ends and explicit interior occlusion cuts')
        if row['mode']=='branch':
            expected={(j['id'],p['object'],p['end']) for j in row['junctions'] for p in j['ends']}
            actual={(p['junction'],p['object'],p['end']) for p in row['ports'] if p['profile']=='junction_cut'}
            if expected!=actual:raise ValueError('Every source junction arm needs exactly one interior junction profile')
    return terminals

def source_integrity(task,state):
    try:
        graph=load(task,state)
        if graph is None:return {'passed':False,'status':'ORIGINAL_CONNECTION_SURVEY_REQUIRED'}
        return {'passed':True,'source_graph':state['source_connection_graph'],'regions':[r['region'] for r in graph['region_coverage']],
                'source_parts':[p['id'] for p in graph['parts']],'candidate_ids':[c['id'] for c in graph['candidate_pairs']],
                'internal_refinement':refinement_coverage(task,state,graph,__import__(__package__+'.source_recursion',fromlist=['load']).load(task,state))}
    except (ValueError,KeyError,TypeError) as error:return {'passed':False,'status':'STALE_ORIGINAL_CONNECTION_SURVEY','reason':str(error)}
