"""Complete per-line gates with evidence-driven finite measurement depth.

All applicable lines are covered. Algorithms, not obligations, are conditional.
Raw package/image facts are shared inside one evaluation, never prior PASS.
"""
import math
from fractions import Fraction
from pathlib import Path
from zipfile import ZipFile
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, map_coordinates
from shapely.geometry import LineString, Point
from .common import read_json, identity, digest
from .line_contracts import POLICY, CRITERIA, enabled, require_contract
from .line_geometry import decode, flatten, native_checks, result, invalid, bounded
from .mathml import NS


def _summary(items):
    values=list(items)
    return {'passed':all(v.get('passed') is True for v in values),
            'valid':all(v.get('valid') is True for v in values), 'items':values}


def has_valid_failure(value):
    if isinstance(value,dict):
        if value.get('valid') is True and value.get('passed') is False:return True
        return any(has_valid_failure(v) for k,v in value.items() if k!='prior_inconclusive')
    if isinstance(value,list):return any(has_valid_failure(v) for v in value)
    return False


def _region(points, margin, size):
    lo=np.floor(np.min(points,axis=0)-margin).astype(int);hi=np.ceil(np.max(points,axis=0)+margin).astype(int)
    return [max(0,int(lo[0])),max(0,int(lo[1])),min(size[0],int(hi[0])+1),min(size[1],int(hi[1])+1)]


def _samples(segments, step, epsilon):
    points,offsets=flatten(segments,epsilon);all_points=[];labels=[];positions=[];offset=0.
    segment_index=0
    for i,(a,b) in enumerate(zip(points,points[1:])):
        while segment_index+1<len(offsets) and i>=offsets[segment_index+1]:segment_index+=1
        length=float(np.linalg.norm(b-a));count=max(2,math.ceil(length/step)+1)
        if len(all_points)+count>250000:raise ValueError('MEASUREMENT_REQUIRED: finite per-line pixel sampling exhausted')
        values=np.linspace(a,b,count)
        all_points.extend(values);labels.extend([segment_index]*count)
        positions.extend(offset+np.linspace(0,length,count));offset+=length
    return np.asarray(all_points),np.asarray(labels),np.asarray(positions)


def _mask(image, colour, tolerance):
    rgb=np.asarray([int(colour[i:i+2],16)/255 for i in (0,2,4)])
    return np.linalg.norm(image-rgb,axis=2)/math.sqrt(3)<=tolerance


def _read_images(task,state,candidate):
    from .component_workflow import _resource
    from .metrics import render_canvas_mapping
    source=_resource(task,state['source']);preview=_resource(task,candidate['preview'])
    from .resource_facts import image_region
    with image_region(source,[],state['source']['sha256'],mode='RGB_WHITE') as image:original=np.asarray(image,float)/255
    with image_region(preview,[],candidate['preview']['sha256'],mode='RGB_WHITE') as image:actual=np.asarray(image,float)/255
    if list(original.shape[1::-1])!=list(state['source_size']):raise ValueError('Source image canvas changed')
    mapping=render_canvas_mapping(state['source_size'],actual.shape[1::-1])
    return original,actual,mapping


def _run_lengths(profile,positions):
    if len(profile)<2:return []
    transitions=np.flatnonzero(profile[1:]!=profile[:-1])+1
    bounds=np.r_[0,transitions,len(profile)-1]
    return [{'ink':bool(profile[a]),'length':float(positions[b]-positions[a])}
            for a,b in zip(bounds,bounds[1:]) if b>a]


def _pattern_check(source_runs,actual_runs,pattern,error):
    # End runs can be partial; complete interior runs retain ordered on/off
    # correspondence. The original fixes the possible phase, never the candidate.
    original=source_runs[1:-1];actual=actual_runs[1:-1]
    if not original:return invalid('Too few complete source dash runs to qualify pattern lengths')
    def fits(runs,phase):
        return all((i+phase)%2==int(not run['ink']) and
                   pattern[(i+phase)%len(pattern)][0]-error<=run['length']<=pattern[(i+phase)%len(pattern)][1]+error
                   for i,run in enumerate(runs))
    phases=[i for i in range(len(pattern)) if fits(original,i)]
    if not phases:return invalid('Frozen dash/gap intervals do not explain original complete runs')
    good=len(actual)==len(original) and any(fits(actual,i) for i in phases)
    return result(good,source_phases=phases,source_complete_runs=original,actual_complete_runs=actual,sampling_error=error)


def _widths(mask,points,tangents,scale,width_limit):
    """Normal pixel-cell chords, separating stroke bands from the route axis."""
    sx,sy=scale;precision=.5/max(sx,sy);offsets=np.arange(-width_limit,width_limit+precision,precision)
    values=[];bands=[];sites=[]
    for site,(p,tangent) in enumerate(zip(points,tangents)):
        length=np.linalg.norm(tangent)
        if length<1e-9:continue
        normal=np.array([-tangent[1],tangent[0]])/length
        coordinates=p+offsets[:,None]*normal
        ink=map_coordinates(mask.astype(float),[coordinates[:,1]*sy-.5,coordinates[:,0]*sx-.5],order=0,mode='constant',cval=0)>0
        indexes=np.flatnonzero(ink)
        if not len(indexes):continue
        values.append(float(offsets[indexes[-1]]-offsets[indexes[0]]+precision))
        bands.append(int(np.sum(ink&~np.r_[False,ink[:-1]])))
        sites.append(site)
    return values,bands,precision,sites


def axis_cell_width_bound(first,second,points,tangents,origins,pixel_sizes,width_limit,tolerance,wanted):
    """Exact axis-normal chords through the same closed occupied raster cells.

    This finite fallback has no source-pixel sampling floor. It does not infer
    subpixel outlines or align a candidate. Non-axis tangents, clipped windows,
    absent sites and unsupported original bands remain explicitly INVALID.
    """
    rational=lambda value:value if isinstance(value,Fraction) else Fraction(str(value))
    domains=[];total=0
    if len(points)!=len(tangents) or not len(points) or len(points)>256:
        return invalid('MEASUREMENT_REQUIRED: finite paired chord-site budget or correspondence unavailable')
    for mask,origin,size in zip((first,second),origins,pixel_sizes):
        values=[];bands=[]
        ox,oy=map(rational,origin);pw,ph=map(rational,size)
        if pw<=0 or ph<=0:return invalid('Non-positive raster-cell dimensions')
        for site,(p,tangent) in enumerate(zip(points,tangents)):
            tx,ty=map(float,tangent)
            if ty==0 and tx!=0:
                along=(rational(p[0])-ox)/pw;centre=rational(p[1]);start=oy;step=ph;profile_axis=0
            elif tx==0 and ty!=0:
                along=(rational(p[1])-oy)/ph;centre=rational(p[0]);start=ox;step=pw;profile_axis=1
            else:return invalid('Axis-cell chord refinement requires an exactly axis-aligned tangent',site=site)
            # A chord on a closed-cell boundary intersects both adjacent cells.
            indexes=[math.floor(along)]
            if along.denominator==1:indexes.append(indexes[0]-1)
            along_size=mask.shape[1-profile_axis]
            if any(i<0 or i>=along_size for i in indexes):
                return invalid('Paired raster chord falls outside the complete measurement crop',site=site)
            lower=max(0,math.floor((centre-rational(width_limit)-start)/step))
            upper=min(mask.shape[profile_axis]-1,math.ceil((centre+rational(width_limit)-start)/step))
            if lower>upper:return invalid('Paired raster chord lies outside its frozen measurement crop',site=site)
            total+=len(indexes)*(upper-lower+1)
            if total>250000:return invalid('MEASUREMENT_REQUIRED: finite paired raster-cell budget exhausted')
            if profile_axis==0:ink=np.any(mask[lower:upper+1,indexes],axis=1)
            else:ink=np.any(mask[indexes,lower:upper+1],axis=0)
            occupied=np.flatnonzero(ink)
            if not len(occupied):return invalid('Original/render chord has an absent corresponding site',site=site)
            # The fixed ROI may be narrower than the search window. Empty
            # guard cells prove all observed chord support is still enclosed;
            # painted crop/window edges remain INVALID, never assumed absent.
            if occupied[0]==0 or occupied[-1]==len(ink)-1:
                return invalid('Paired raster chord support reaches the finite window boundary',site=site)
            values.append((int(occupied[-1])-int(occupied[0])+1)*step)
            bands.append(int(np.sum(ink&~np.r_[False,ink[:-1]])))
        domains.append((values,bands))
    source,actual=domains
    details={'method':'paired_axis_raster_cell_chords','unit':'source_px','sites':list(range(len(points))),
        'source_widths':[float(v) for v in source[0]],'actual_widths':[float(v) for v in actual[0]],
        'source_bands':source[1],'actual_bands':actual[1],'expected_bands':wanted,
        'candidate_alignment':False,'target':'unchanged occupied pixel-cell chords at every original site'}
    if any(v!=wanted for v in source[1]):return invalid('Original raster chords do not support the frozen compound bands',**details)
    if any(v!=wanted for v in actual[1]):return result(False,reason='Actual raster chord band count differs from the original',**details)
    delta=max(abs(a-b) for a,b in zip(source[0],actual[0]));value=float(delta)
    error=0. if Fraction(value)==delta else math.ulp(value)
    return bounded(value,error,tolerance,exact_difference=[delta.numerator,delta.denominator],numeric_error=error,**details)


def paint_cell_bound(first,second,origins,pixel_sizes,tolerance,*,bidirectional=True):
    """Same frozen raster paint sets, with tighter finite cell-union bounds.

    Normal centre/radius bounds and this producer measure the same occupied
    pixel-cell unions. This does not infer a latent subpixel source curve.
    Full interiors are sampled too: boundary-only tests miss filled holes.
    """
    from shapely.geometry import box
    from shapely.ops import unary_union
    from shapely import points as point_array,distance as geometry_distance
    domains=[];rectangles=[]
    for mask,origin,size in zip((first,second),origins,pixel_sizes):
        runs=[];ox,oy=origin;pw,ph=size
        for y in range(mask.shape[0]):
            xs=np.flatnonzero(mask[y])
            if not len(xs):continue
            starts=np.r_[0,np.flatnonzero(np.diff(xs)>1)+1];ends=np.r_[starts[1:]-1,len(xs)-1]
            for a,b in zip(starts,ends):runs.append((ox+xs[a]*pw,oy+y*ph,ox+(xs[b]+1)*pw,oy+(y+1)*ph))
        if not runs:return invalid('No independently extractable raster paint-cell pair')
        if len(runs)>20000:return invalid('MEASUREMENT_REQUIRED: finite paint-cell union budget exhausted')
        rectangles.append(runs);domains.append(unary_union([box(*r) for r in runs]))
    for refinement in range(4):
        step=min(.25,tolerance/8)/(2**refinement);maximum=0.;error=0.;count=0
        pairs=zip(rectangles,reversed(domains)) if bidirectional else ((rectangles[0],domains[1]),)
        for runs,target in pairs:
            for x,y,r,b in runs:
                nx=max(1,math.ceil((r-x)/step));ny=max(1,math.ceil((b-y)/step))
                count+=(nx+1)*(ny+1)
                if count>500000:return invalid('MEASUREMENT_REQUIRED: finite paint-cell sampling budget exhausted')
                xx,yy=np.meshgrid(np.linspace(x,r,nx+1),np.linspace(y,b,ny+1))
                distances=geometry_distance(point_array(xx.ravel(),yy.ravel()),target)
                maximum=max(maximum,float(np.max(distances)))
                error=max(error,math.hypot((r-x)/nx,(b-y)/ny)/2)
        check=bounded(maximum,error,tolerance,method='refined_fixed_raster_cell_bound',unit='source_px',
            samples=count,refinements=refinement,target='unchanged foreground pixel-cell unions, including interiors',
            directions='both' if bidirectional else 'original_to_render',candidate_alignment=False)
        if check['valid']:return check
    return check


def marker_pixels(row,original,actual,geometry,*,deep=False,joint_result=None):
    source=row['source'];limits=source['limits'];sx=actual.shape[1]/original.shape[1];sy=actual.shape[0]/original.shape[0]
    checks=[]
    for index,end in enumerate(source['ends']):
        marker=end['marker']
        if marker['type']=='none':
            checks.append({'passed':True,'valid':True,'applicable':False,'scope':'native and descendant census proves confirmed no marker'});continue
        # Include the native ending's conservative painted extent as well as
        # the original extent. An enlarged/wrong marker must not be crop-clipped.
        q=geometry['oriented'][0 if index==0 else -1]
        native_extent=q['native']['style']['width_source_bounds'][1]*30
        crop_basis={'method':'conservative_native_ending_envelope','shaft_width_multiplier':30}
        custom=[part['owner'] for part in row.get('parts',[]) if part['role']==('start_marker' if index==0 else 'end_marker')]
        extent=geometry.get('marker_paint_extents',{}).get(str(index))
        if len(custom)==1 and extent is not None and extent['owner']==custom[0]:
            native_extent=extent['radius_from_source_anchor']
            crop_basis={'method':'separate_saved_native_marker_paint','native_marker':extent}
        radius=max(marker['width'][1],marker['length'][1],native_extent)+limits['marker']+2
        x,y,r,b=_region(np.asarray([marker['anchor']]),radius,original.shape[1::-1])
        paint=marker.get('paint_colour',source['stroke'].get('paint_colour',source['stroke']['colour']))
        a=_mask(original[y:b,x:r],paint,limits['colour'])
        left,top,right,bottom=math.floor(x*sx),math.floor(y*sy),math.ceil(r*sx),math.ceil(b*sy)
        c=_mask(actual[top:bottom,left:right],paint,limits['colour'])
        ownership=None
        if not custom:
            from .terminal_paint import partition,support
            domain=partition(source,index)
            if domain is None or domain.get('decision'):
                if joint_result is not None:
                    checks.append({**joint_result,'end':index,'terminal_joint_obligation':True});continue
                checks.append(invalid('MEASUREMENT_DECISION_REQUIRED: terminal junction/route ownership needs a qualified local producer',
                                      end=index,ownership=domain));continue
            a,source_owner=support(a,(x,y),(1.,1.),**domain)
            c,render_owner=support(c,(left/sx,top/sy),(1/sx,1/sy),**domain)
            if a is None:
                checks.append(invalid('SOURCE_TERMINAL_SUPPORT_REQUIRED: '+source_owner['reason'],end=index,ownership=source_owner));continue
            if c is None:
                if render_owner['reason']=='NO_TERMINAL_ANCHOR_SUPPORT':
                    checks.append(result(False,reason='Actual terminal has no paint at the source anchor',end=index,ownership=render_owner))
                else:checks.append(invalid('MEASUREMENT_DECISION_REQUIRED: '+render_owner['reason'],end=index,ownership=render_owner))
                continue
            ownership={'source':source_owner,'render':render_owner,'observation_window_is_not_owner_mask':True}
        if not a.any() or not c.any():
            checks.append(invalid('Marker source/render colour support is absent',end=index));continue
        ya,xa=np.nonzero(a);yc,xc=np.nonzero(c)
        points_a=np.column_stack((xa+x+.5,ya+y+.5));points_c=np.column_stack(((xc+left+.5)/sx,(yc+top+.5)/sy))
        from scipy.spatial import cKDTree
        ca,ca_index=cKDTree(points_a).query(points_c);ac,ac_index=cKDTree(points_c).query(points_a)
        distance=max(float(ca.max()),float(ac.max()))
        if ca.max()>=ac.max():
            site=int(np.argmax(ca));witness={'direction':'render_to_original','render':points_c[site].tolist(),'original':points_a[ca_index[site]].tolist()}
        else:
            site=int(np.argmax(ac));witness={'direction':'original_to_render','original':points_a[site].tolist(),'render':points_c[ac_index[site]].tolist()}
        error=math.sqrt(2)/2+math.sqrt((1/sx)**2+(1/sy)**2)/2
        # The complete local painted comparison includes both wings, hollow
        # interiors and neighboring contact context; native checks supply type,
        # endpoint identity and separate-marker ownership.
        check=bounded(distance,error,limits['marker'],end=index,unit='source_px',method='current_marker_paint_both_directions',roi=[x,y,r-x,b-y])
        if deep and not check['valid']:
            refined=paint_cell_bound(a,c,((x,y),(left/sx,top/sy)),((1.,1.),(1/sx,1/sy)),limits['marker'])
            refined.update(end=index,roi=[x,y,r-x,b-y],prior_inconclusive=check)
            check=refined
        check['scope']='fixed original/render terminal crop, including contact context; never plan-derived text'
        check['center_distance_witness']={**witness,'distance_source_px':distance,'owner_supported':bool(ownership) or bool(custom)}
        if ownership:check['ownership']=ownership
        check['crop_basis']={**crop_basis,'source_marker_width':marker['width'],'source_marker_length':marker['length'],
                             'source_tolerance':limits['marker'],'contact_guard_source_px':2}
        checks.append(check)
    return _summary(checks)


def render_check(row,geometry,original,actual,*,deep=False,rows=None,geometries=None):
    """Measure all source segments; low support/ambiguity is explicit INVALID.

    The normal route uses direct colour corridors. Refinement uses the same
    source protocol with denser sampling and tighter sampling-error bounds. Neither changes
    source geometry, thresholds, visibility or ownership after a failure.
    """
    source=row['source'];limits=source['limits'];width=source['stroke']['width'];sx=actual.shape[1]/original.shape[1];sy=actual.shape[0]/original.shape[0]
    scale=(sx,sy);epsilon=max(1e-5,limits['route']/64)
    points,labels,positions=_samples(source['path']['segments'],.25 if deep else .75,epsilon)
    margin=width[1]/2+max(limits['route'],limits['marker'])+2
    expected=geometry['expected'];native_points=np.concatenate([q['points'] for q in geometry['oriented']])
    x,y,r,b=_region(np.vstack((expected,native_points)),margin,original.shape[1::-1])
    if r<=x or b<=y:return invalid('No source-owned line measurement domain')
    colour=source['stroke'].get('paint_colour',source['stroke']['colour']);tolerance=limits['colour']
    source_ink=_mask(original[y:b,x:r],colour,tolerance)
    ax,ay,ar,ab=math.floor(x*sx),math.floor(y*sy),math.ceil(r*sx),math.ceil(b*sy)
    actual_ink=_mask(actual[ay:ab,ax:ar],colour,tolerance)
    if not source_ink.any() or not actual_ink.any():
        return invalid('No independently extractable source/render stroke colour',method='per_line_colour_corridor')
    source_distance=distance_transform_edt(~source_ink)
    actual_distance=distance_transform_edt(~actual_ink,sampling=(1/sy,1/sx))
    src=map_coordinates(source_distance,[points[:,1]-y-.5,points[:,0]-x-.5],order=1,mode='constant',cval=np.inf)
    dst=map_coordinates(actual_distance,[points[:,1]*sy-ay-.5,points[:,0]*sx-ax-.5],order=1,mode='constant',cval=np.inf)
    visible=np.ones(len(points),bool)
    for hidden in source['visibility']['hidden']:
        selected=np.flatnonzero(labels==hidden['segment'])
        if not len(selected):continue
        normalized=(positions[selected]-positions[selected[0]])/max(positions[selected[-1]]-positions[selected[0]],1e-12)
        visible[selected[(normalized>=hidden['range'][0])&(normalized<=hidden['range'][1])]]=False
    # Markers have independent checks. Exclude their declared painted extents,
    # never an arbitrary caller mask, from shaft width/phase estimation.
    shaft=visible.copy()
    for end in source['ends']:
        radius=max(end['marker']['width'][1],end['marker']['length'][1])+limits['marker']
        if end['marker']['type']!='none':shaft &= np.linalg.norm(points-np.asarray(end['marker']['anchor']),axis=1)>radius
    segments=[];solid=source['stroke']['dash']['kind']=='solid'
    for index in range(len(source['path']['segments'])):
        selected=(labels==index)&visible
        if not selected.any():
            segments.append({'segment':index,'passed':True,'valid':True,'applicable':False,'scope':'source-confirmed fully occluded interval'});continue
        source_support=src[selected]<=width[1]/2+limits['route']+math.sqrt(2)/2
        if solid and not source_support.all():
            segments.append(invalid('Original route/colour extraction is not supported over this segment',segment=index,missing_samples=int((~source_support).sum())));continue
        if solid:
            allowed=width[1]/2+limits['route']+math.sqrt((1/sx)**2+(1/sy)**2)/2
            segments.append(result(bool((dst[selected]<=allowed).all()),segment=index,
                max_axis_to_ink_distance=float(np.max(dst[selected])),allowed=allowed,samples=int(selected.sum()),unit='source_px'))
        else:
            # Dash gaps are not missing terminals. Match the source on/off support
            # along the same route instead of assuming a solid centreline.
            segment_positions=positions[selected];source_profile=src[selected]<=width[1]/2+.5
            actual_profile=dst[selected]<=width[1]/2+.5/max(sx,sy)
            if not source_profile.any() or not (~source_profile).any():
                segments.append(invalid('Source dash phase/spacing is not independently measurable',segment=index));continue
            a=segment_positions[source_profile,None];c=segment_positions[actual_profile,None]
            if not len(c):segments.append(result(False,segment=index,reason='Dash strokes absent'));continue
            from scipy.spatial import cKDTree
            distance=max(float(cKDTree(a).query(c)[0].max()),float(cKDTree(c).query(a)[0].max()))
            source_runs=_run_lengths(source_profile,segment_positions);actual_runs=_run_lengths(actual_profile,segment_positions)
            pattern=_pattern_check(source_runs,actual_runs,source['stroke']['dash']['pattern'],.5 if deep else 1.)
            phase=bounded(distance,.5 if deep else .75,limits['route'],segment=index,source_runs=source_runs,actual_runs=actual_runs)
            segments.append({**_summary([phase,pattern]),'segment':index,'phase':phase,'pattern':pattern})
    # Axis-to-ink checks alone may let a very short missing arm borrow the
    # neighboring long arm's paint. Compare every owned original ink pixel to
    # the current render too, with a conservative pixel-cell uncertainty bound.
    # Tiny unresolved evidence stays INVALID; increased sampling cannot erase it.
    yy,xx=np.nonzero(source_ink)
    original_pixels=np.column_stack((xx+x+.5,yy+y+.5))
    from scipy.spatial import cKDTree
    visible_points=points[shaft]
    if len(visible_points):
        owned=cKDTree(visible_points).query(original_pixels)[0]<=width[1]/2+math.sqrt(2)/2
        if owned.any():
            locations=original_pixels[owned]
            distances=map_coordinates(actual_distance,[locations[:,1]*sy-ay-.5,locations[:,0]*sx-ax-.5],order=1,mode='constant',cval=np.inf)
            pixel_error=math.sqrt(2)/2+math.sqrt((1/sx)**2+(1/sy)**2)/2
            coverage=bounded(float(distances.max()),pixel_error,limits['route'],method='every_original_shaft_pixel_coverage',samples=int(owned.sum()),unit='source_px')
            if not coverage['valid']:
                fixed_owned=np.zeros_like(source_ink);fixed_owned[yy[owned],xx[owned]]=True
                refined=paint_cell_bound(fixed_owned,actual_ink,((x,y),(ax/sx,ay/sy)),
                    ((1.,1.),(1/sx,1/sy)),limits['route'],bidirectional=False)
                refined.update(prior_inconclusive=coverage,owned_source_cells=int(owned.sum()))
                coverage=refined
            segments.append(coverage)
    # Width/band checks sample each source segment interior. No long-segment
    # weighting can hide a missing short arm because segment support is separate.
    chosen=[];tangents=[]
    for index in range(len(source['path']['segments'])):
        ids=np.flatnonzero((labels==index)&shaft)
        if not len(ids):continue
        # Corners/junctions are covered by route/visibility, not mistaken for a
        # wider shaft. Short arms remain mandatory visibility obligations.
        start,end=points[ids[0]],points[ids[-1]]
        margin=width[1]+limits['width']+1
        ids=ids[(np.linalg.norm(points[ids]-start,axis=1)>margin)&(np.linalg.norm(points[ids]-end,axis=1)>margin)]
        for kind in ('junctions','crossings','shared'):
            for landmark in source['topology'][kind]:
                ids=ids[np.linalg.norm(points[ids]-np.asarray(landmark['point']),axis=1)>margin]
        if not len(ids):continue
        for loc in np.linspace(0,len(ids)-1,min(9,len(ids)),dtype=int):
            j=ids[loc];lo=max(0,j-1);hi=min(len(points)-1,j+1)
            if hi>lo:chosen.append(points[j]);tangents.append(points[hi]-points[lo])
    if chosen:
        local=np.asarray(chosen)-np.array([ax/sx,ay/sy])
        chord_limit=width[1]+2*limits['width']+2
        widths,bands,pixel_error,actual_sites=_widths(actual_ink,local,np.asarray(tangents),scale,chord_limit)
        if not widths:width_result=invalid('No isolated native/render stroke-width chords')
        else:
            lo,hi=width;good=all(lo-limits['width']-pixel_error<=v<=hi+limits['width']+pixel_error for v in widths)
            # Dash gaps can remove some chords; existing chords still retain
            # actual band count rather than flattening compound lines.
            wanted={'single':1,'double':2,'thickThin':2,'thinThick':2,'triple':3}[source['stroke']['compound']]
            band_good=all(v==wanted for v in bands)
            width_result=result(good and band_good,widths=widths,bands=bands,expected_bands=wanted,pixel_error=pixel_error,unit='source_px')
            source_widths,source_bands,source_error,source_sites=_widths(source_ink,np.asarray(chosen)-np.array([x,y]),np.asarray(tangents),(1.,1.),chord_limit)
            if source_sites!=actual_sites or any(v!=wanted for v in source_bands):
                paired=invalid('Original/render width chords lack one-to-one visible band support',source_chords=len(source_widths),actual_chords=len(widths))
            else:
                # Exact same source sites, tangent and pixel-cell estimator.
                # A wide source interval cannot hide a systematically thicker
                # candidate; uncertainties remain explicit in the bound.
                distances=[abs(a-b) for a,b in zip(source_widths,widths)]
                paired=bounded(max(distances,default=0.),source_error+pixel_error,limits['width'],
                    source_widths=source_widths,actual_widths=widths,method='paired_original_render_normal_chords',unit='source_px')
            if not paired['valid']:
                pw=Fraction(original.shape[1],actual.shape[1]);ph=Fraction(original.shape[0],actual.shape[0])
                refined=axis_cell_width_bound(source_ink,actual_ink,chosen,tangents,((x,y),(ax*pw,ay*ph)),
                    ((1,1),(pw,ph)),chord_limit,limits['width'],wanted)
                refined['prior_inconclusive']=paired;paired=refined
            width_result={**_summary([width_result,paired]),'declared_interval':width_result,'paired_original':paired}
    else:width_result=invalid('No visible source shaft away from markers; requires a qualified local producer')
    joint_result=None
    from .terminal_paint import partition,joint
    needs_joint=not chosen or any(partition(source,index).get('decision') for index,end in enumerate(source['ends'])
                                  if end['marker']['type']!='none' and partition(source,index) is not None)
    if needs_joint and rows is not None and geometries is not None:
        joint_result=joint(row,rows,geometries,original,actual)
        # A joint painted-envelope check is explicitly a different producer;
        # no invalid isolated-width claim or old FAIL is relabeled as PASS.
        if not chosen:width_result={**joint_result,'isolated_shaft_width_applicable':False}
    marker_result=marker_pixels(row,original,actual,geometry,deep=deep,joint_result=joint_result)
    checks=_summary(segments+[width_result,marker_result]);checks.update(method='refined_line_pixels' if deep else 'normal_line_pixels',
        depth='deep' if deep else 'normal',segments=segments,width=width_result,roi=[x,y,r-x,b-y],
        markers=marker_result,actual_scale=[sx,sy],source_sampling_step=.25 if deep else .75,source_alignment='fixed_no_candidate_alignment')
    return checks


def topology_checks(rows,geometries,nodes):
    by_id={r['id']:r for r in rows};results={r['id']:[] for r in rows}
    for row in rows:
        tolerance=row['source']['limits']['route']
        for kind in ('junctions','crossings','shared'):
            for item in row['source']['topology'][kind]:
                point=Point(item['point']);peers=item['features'];checks=[]
                for peer in peers:
                    if peer not in geometries:
                        checks.append(invalid('Source topology peer has no current native path',peer=peer));continue
                    paths=geometries[peer]['paths'];distance=min(point.distance(p) for p in paths)
                    original=LineString(geometries[peer]['expected'])
                    expected_distance=point.distance(original)
                    # Bridges and occlusions may intentionally leave the crossing
                    # centre. Compare to the original distance, never force a
                    # bridge to become a junction.
                    checks.append(result(abs(distance-expected_distance)<=tolerance,peer=peer,distance=distance,source_distance=expected_distance))
                    other=by_id[peer]['source']['topology'][kind]
                    checks.append(result(any(v==item for v in other),peer=peer,scope='reciprocal frozen topology'))
                results[row['id']].append({'kind':kind,'id':item['id'],**_summary(checks)})
    # A source crossing/overlap must have a semantic decision. Swept bounding
    # boxes avoid comparing every disjoint pair. The pair budget cannot waive work.
    boxes=sorted((g['expected'][:,0].min(),g['expected'][:,0].max(),g['expected'][:,1].min(),g['expected'][:,1].max(),name) for name,g in geometries.items())
    active=[];comparisons=0
    for left,right,top,bottom,name in boxes:
        active=[v for v in active if v[1]>=left]
        for other in active:
            if other[3]<top or bottom<other[2]:continue
            comparisons+=1
            if comparisons>200000:
                for values in results.values():values.append(invalid('MEASUREMENT_REQUIRED: bounded topology work exhausted'))
                return {k:_summary(v) for k,v in results.items()}
            a=LineString(geometries[name]['expected']);b=LineString(geometries[other[4]]['expected']);intersection=a.intersection(b)
            if intersection.is_empty:continue
            peers={name,other[4]};declared=[]
            for kind in ('junctions','crossings','shared'):
                declared.extend(v for v in by_id[name]['source']['topology'][kind] if peers<=set(v['features']))
            # Two independent connections can terminate on the same observed
            # target without declaring a shaft-to-shaft junction inside that body.
            common_targets={e['attachment'].get('feature') for e in by_id[name]['source']['ends']} & {e['attachment'].get('feature') for e in by_id[other[4]]['source']['ends']}
            common_targets.discard(None)
            terminal_only=intersection.geom_type=='Point' and any(math.dist(intersection.coords[0],e['point'])<=1e-5 for e in by_id[name]['source']['ends']) and any(math.dist(intersection.coords[0],e['point'])<=1e-5 for e in by_id[other[4]]['source']['ends'])
            valid=bool(declared or common_targets and terminal_only)
            check=result(valid,peers=sorted(peers),scope='source intersections require explicit crossing/junction/shared semantics')
            results[name].append(check);results[other[4]].append(check)
        active.append((left,right,top,bottom,name))
    # New saved intersections must be accounted for even if the original pair
    # was disjoint. Source-only bounding boxes cannot detect a false branch.
    from shapely.ops import unary_union
    actual={name:unary_union(value['paths']) for name,value in geometries.items()}
    boxes=sorted((*path.bounds,name) for name,path in actual.items())
    active=[]
    for left,top,right,bottom,name in boxes:
        active=[v for v in active if v[2]>=left]
        for item in active:
            if item[3]<top or bottom<item[1]:continue
            comparisons+=1
            if comparisons>200000:
                for values in results.values():values.append(invalid('MEASUREMENT_REQUIRED: bounded topology work exhausted'))
                return {k:_summary(v) for k,v in results.items()}
            peer=item[4];intersection=actual[name].intersection(actual[peer])
            if intersection.is_empty:continue
            expected=LineString(geometries[name]['expected']).intersection(LineString(geometries[peer]['expected']))
            tolerance=max(by_id[name]['source']['limits']['route'],by_id[peer]['source']['limits']['route'])
            good=not expected.is_empty and intersection.difference(expected.buffer(tolerance)).is_empty
            check=result(good,peers=[name,peer],scope='no extra saved shaft intersections outside original intersection bounds')
            results[name].append(check);results[peer].append(check)
        active.append((left,top,right,bottom,name))
    return {k:{**_summary(v),'scope':'all declared source topology and source-intersection decisions','applicable':bool(v)} for k,v in results.items()}


def evaluate(task,state,candidate,contract,*,render=True,feature_ids=None):
    if not enabled(state):return {'passed':True,'applicable':False,'legacy_policy_retained':True}
    spec=require_contract(state,contract)
    from .component_workflow import _resource
    from .boundary_geometry import saved_nodes
    pptx=_resource(task,candidate['pptx']);scene=read_json(_resource(task,candidate['scene']))
    from .line_contracts import is_line_node
    actual_nodes=saved_nodes(pptx,state['source_size']);expected_owners=set(spec['native_line_owners'])
    saved_lines=set()
    for name,entry in actual_nodes.items():
        props=entry['node'].find('p:spPr',NS)
        if props is None:continue
        preset=props.find('a:prstGeom',NS);custom=props.find('a:custGeom',NS)
        if entry['tag']=='cxnSp' or preset is not None and (preset.get('prst') in ('line','lineInv','straightConnector1') or 'arrow' in preset.get('prst','').lower()):
            saved_lines.add(name)
        elif custom is not None:
            for path in custom.findall('a:pathLst/a:path',NS):
                if path.find('a:close',NS) is None:saved_lines.add(name)
    scene_lines={n['id'] for n in scene['objects'] if is_line_node(n)}
    known_owners={part['owner'] for row in spec['lines'] for part in row['parts']}
    census=result(expected_owners==scene_lines and saved_lines<=known_owners and expected_owners<=set(actual_nodes),
        expected=sorted(expected_owners),actual=sorted(saved_lines),unmapped_saved=sorted(saved_lines-known_owners),source_lines=spec['source_line_ids'])
    selected=[r for r in spec['lines'] if feature_ids is None or r['id'] in feature_ids]
    if not spec['lines']:
        return {'passed':census['passed'],'valid':True,'applicable':False,'policy':POLICY,'basis':spec['basis'],
                'source_hash':state['source']['sha256'],'pptx_hash':candidate['pptx']['sha256'],
                'preview_hash':candidate.get('preview',{}).get('sha256') if render else None,'render_checked':render,
                'census':census,'lines':{},'scope':'source inventory and saved-native census independently establish no applicable standalone lines'}
    # Topology can depend on a peer outside a locally selected component. Decode
    # the full line graph once; filter only returned local obligations afterwards.
    from .resource_facts import package_read,derived_value
    with package_read(pptx,candidate['pptx']['sha256']) as z:parts={n:z.read(n) for n in z.namelist() if n.endswith(('.xml','.rels'))}
    bindings={b['feature']:b for b in contract['feature_bindings']}
    decoded={};decode_errors={};geometries={};checks={};methods={}
    for row in spec['lines']:
        for part in row['parts']:
            name=part['owner']
            if part['role']!='shaft' or name in decoded or name in decode_errors:continue
            try:
                sites=row.get('terminal_sites',{}).get(name)
                decoded[name]=derived_value(pptx,candidate['pptx']['sha256'],
                    {'line_decode':digest(__file__),'geometry':digest(Path(__file__).with_name('line_geometry.py')),'canvas':state['source_size'],'owner':name,'sites':sites},
                    lambda:decode(actual_nodes[name],parts,sites))
            except (ValueError,KeyError,TypeError,IndexError) as error:decode_errors[name]=str(error)
    for row in spec['lines']:
        errors=[decode_errors[p['owner']] for p in row['parts'] if p['owner'] in decode_errors]
        if errors:
            checks[row['id']]={key:invalid('; '.join(errors)) for key in CRITERIA};continue
        value=None
        for refinement in range(6):
            epsilon=max(1e-7,row['source']['limits']['route']/32/(4**refinement))
            try:value=native_checks(row,decoded,actual_nodes,bindings,epsilon)
            except (ValueError,KeyError,TypeError,IndexError) as error:
                value={key:invalid(str(error)) for key in ('route','terminals','markers','stroke')};break
            if value['route']['valid'] or value['route'].get('status')=='FAIL':break
        methods[row['id']]={'native_refinements':refinement,'native_method':'independent_saved_geometry','render_method':'not_selected'}
        if 'paths' in value:geometries[row['id']]=value
        checks[row['id']]={key:value[key] for key in ('route','terminals','markers','stroke')}
    topology=topology_checks(spec['lines'],geometries,actual_nodes)
    images=None
    if render:
        from .component_workflow import actual_render
        actual_render(task,state,candidate,independent=True)
        images=_read_images(task,state,candidate)
    for row in spec['lines']:
        values=checks[row['id']]
        values['topology']=topology.get(row['id'],invalid('Missing topology result'))
        if not render:
            hidden=geometries.get(row['id'],{}).get('visibility_native')
            values['visibility']=hidden if hidden and not hidden['passed'] else {'passed':True,'valid':True,'applicable':False,'status':'DEFERRED_TO_FINAL_RENDER','scope':'native-only local qualification; final render remains mandatory'}
        elif row['id'] not in geometries or not all(values[k].get('passed') is True for k in ('route','terminals','markers','stroke','topology')):
            values['visibility']=invalid('Native/source failure must be resolved before render refinement')
        else:
            try:
                normal=render_check(row,geometries[row['id']],images[0],images[1],rows=spec['lines'],geometries=geometries)
                methods[row['id']]['render_method']=normal['method'] if 'method' in normal else 'normal_line_pixels'
                # A valid FAIL is never erased by a weaker alternative. Only an
                # inconclusive producer is eligible for bounded refinement.
                if not normal['valid'] and not has_valid_failure(normal):
                    refined=render_check(row,geometries[row['id']],images[0],images[1],deep=True,rows=spec['lines'],geometries=geometries)
                    refined['prior_inconclusive']=normal;normal=refined
                    methods[row['id']]['render_method']='refined_line_pixels'
                hidden=geometries[row['id']]['visibility_native']
                values['visibility']={**_summary([normal,hidden]),'render':normal,'native_occlusion':hidden,'method':normal.get('method')}
            except (ValueError,KeyError,TypeError,IndexError) as error:values['visibility']=invalid(str(error))
    rows={row['id']:{'passed':all(checks[row['id']][k].get('passed') is True for k in CRITERIA),
          'valid':all(checks[row['id']][k].get('valid') is True for k in CRITERIA),
          'checks':checks[row['id']],'methods':methods.get(row['id'],{}),'owners':[p['owner'] for p in row['parts']]}
          for row in selected}
    return {'passed':census['passed'] and all(v['passed'] for v in rows.values()),'valid':all(v['valid'] for v in rows.values()),
        'policy':POLICY,'basis':spec['basis'],'census':census,'lines':rows,'source_hash':state['source']['sha256'],
        'pptx_hash':candidate['pptx']['sha256'],'preview_hash':candidate.get('preview',{}).get('sha256') if render else None,
        'scope':'All compiled obligations; bounded method selection, no candidate alignment or model identity',
        'render_checked':render,'method_counts':{'normal':sum(v.get('render_method')=='normal_line_pixels' for k,v in methods.items() if k in rows),
            'deep':sum(v.get('render_method')=='refined_line_pixels' for k,v in methods.items() if k in rows)}}
