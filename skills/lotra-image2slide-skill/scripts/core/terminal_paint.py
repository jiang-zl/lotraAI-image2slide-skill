"""Owner-supported terminal paint, independent of nearby disconnected ink."""
import math
import numpy as np
from scipy.ndimage import label
from .line_geometry import flatten

POLICY='terminal-paint-1.37.5'


def support(mask,origin,pixel_size,anchor,inward,depth,seed_radius):
    """Retain the connected terminal support, then separate its upstream shaft.

    The observation window is still the complete conservative saved ending
    window. Neither source marker dimensions nor a candidate crop can clip
    lateral/forward excess paint. No largest-component or glyph-area heuristic
    assigns a disconnected neighbor to the terminal.
    """
    components,count=label(mask,np.ones((3,3),dtype=int))
    yy,xx=np.nonzero(mask)
    if not len(xx):return None,{'reason':'NO_TERMINAL_COLOUR_SUPPORT'}
    points=np.column_stack((origin[0]+(xx+.5)*pixel_size[0],origin[1]+(yy+.5)*pixel_size[1]))
    distances=np.linalg.norm(points-np.asarray(anchor),axis=1)
    nearest=float(distances.min())
    if nearest>seed_radius:return None,{'reason':'NO_TERMINAL_ANCHOR_SUPPORT','nearest_source_px':nearest}
    # Use a small physical neighborhood of the closest supported anchor site.
    seeds=distances<=min(seed_radius,nearest+math.hypot(*pixel_size))
    ids=set(components[yy[seeds],xx[seeds]])-{0}
    if len(ids)!=1:return None,{'reason':'AMBIGUOUS_TERMINAL_COMPONENTS','components':len(ids)}
    selected=components[yy,xx]==next(iter(ids))
    along=(points-np.asarray(anchor))@np.asarray(inward)
    selected &= along<=depth
    output=np.zeros_like(mask);output[yy[selected],xx[selected]]=True
    return output,{'producer':POLICY,'pixels':int(selected.sum()),'anchor_nearest_source_px':nearest,
                   'upstream_cut_source_px':depth,'disconnected_pixels_excluded':int((~(components[yy,xx]==next(iter(ids)))).sum()),
                   'lateral_or_forward_candidate_clipping':False}


def partition(source,index):
    points,_=flatten(source['path']['segments'],max(1e-5,source['limits']['route']/64))
    anchor=source['ends'][index]['marker']['anchor']
    vector=points[1]-points[0] if index==0 else points[-2]-points[-1]
    length=float(np.linalg.norm(vector))
    if length<=1e-12:return None
    inward=vector/length
    depth=source['ends'][index]['marker']['length'][1]+source['limits']['marker']+2
    for kind in ('junctions','crossings','shared'):
        for item in source['topology'][kind]:
            delta=np.asarray(item['point'])-np.asarray(anchor)
            if np.linalg.norm(delta)<=depth+source['stroke']['width'][1]:
                return {'decision':'TERMINAL_JUNCTION_PARTITION_REQUIRED','point':item['point'],
                        'source_evidence':item['source_evidence']}
    return {'anchor':anchor,'inward':inward,'depth':depth,
            'seed_radius':source['limits']['endpoint']+math.sqrt(2)/2}


def joint(row,rows,geometries,original,actual):
    """Compare a complete declared connected line group when shafts overlap.

    This producer neither discards a short arm nor invents an isolated chord.
    The full connected paint must belong to the frozen source graph. An attached
    box/glyph outside that graph is a source ownership decision, not a mask.
    """
    from .line_verification import _mask,_region,paint_cell_bound,invalid,result
    from scipy.spatial import cKDTree
    lookup={r['id']:r for r in rows};members={row['id']};pending=list(members)
    while pending:
        current=lookup[pending.pop()]
        for kind in ('junctions','crossings','shared'):
            for item in current['source']['topology'][kind]:
                peers=set(item.get('features',[]))
                if not peers or not peers<=set(lookup):return invalid('JOINT_SOURCE_GRAPH_REQUIRED: complete source peers')
                for name in peers-members:members.add(name);pending.append(name)
        if len(members)>64:return invalid('MEASUREMENT_REQUIRED: finite joint graph budget exhausted')
    group=[lookup[name] for name in sorted(members)];source=row['source'];limits=source['limits']
    paint=source['stroke'].get('paint_colour',source['stroke']['colour'])
    if any(r['source']['stroke'].get('paint_colour',r['source']['stroke']['colour'])!=paint or
           r['source']['stroke']['dash']['kind']!='solid' for r in group):
        return invalid('JOINT_PAINT_SOURCE_DECISION_REQUIRED: separate colour/dash support')
    if not members<=set(geometries):return invalid('JOINT_NATIVE_GRAPH_REQUIRED: every source peer needs current decoded native geometry')
    paths=[];envelopes=[];actual_paths=[];native_extent=0
    for r in group:
        points,_=flatten(r['source']['path']['segments'],max(1e-5,r['source']['limits']['route']/64))
        # Dense source sampling bounds owner support without using candidate ink.
        samples=[]
        for a,b in zip(points[:-1],points[1:]):
            count=max(1,math.ceil(float(np.linalg.norm(b-a))/.5));samples.extend(np.linspace(a,b,count+1))
        samples=np.asarray(samples);paths.append(samples)
        marker=max((max(e['marker']['width'][1],e['marker']['length'][1]) for e in r['source']['ends']),default=0)
        envelopes.append(max(marker,r['source']['stroke']['width'][1]/2)+r['source']['limits']['route']+2)
        for q in geometries[r['id']]['oriented']:
            actual_paths.append(q['points']);native_extent=max(native_extent,q['native']['style']['width_source_bounds'][1]*30)
    route=np.concatenate(paths);radius=max(max(envelopes),native_extent)+limits['marker']+2
    x,y,r,b=_region(np.vstack([route,*actual_paths]),radius,original.shape[1::-1])
    if (r-x)*(b-y)>2000000:return invalid('MEASUREMENT_REQUIRED: finite joint raster budget exhausted')
    sx=actual.shape[1]/original.shape[1];sy=actual.shape[0]/original.shape[0]
    left,top,right,bottom=math.floor(x*sx),math.floor(y*sy),math.ceil(r*sx),math.ceil(b*sy)
    masks=[_mask(original[y:b,x:r],paint,limits['colour']),_mask(actual[top:bottom,left:right],paint,limits['colour'])]
    domains=[((x,y),(1.,1.)),((left/sx,top/sy),(1/sx,1/sy))];owned=[];details=[]
    for index,(mask,(origin,size)) in enumerate(zip(masks,domains)):
        components,_=label(mask,np.ones((3,3),dtype=int));yy,xx=np.nonzero(mask)
        if not len(xx):return invalid('JOINT_SOURCE_PAINT_REQUIRED') if index==0 else result(False,reason='Joint actual paint absent')
        points=np.column_stack((origin[0]+(xx+.5)*size[0],origin[1]+(yy+.5)*size[1]))
        distance,nearest=cKDTree(points).query(route);seed_radius=limits['endpoint']+math.hypot(*size)/2
        ids=set(components[yy[nearest[distance<=seed_radius]],xx[nearest[distance<=seed_radius]]])-{0}
        if not ids:return invalid('JOINT_SOURCE_SUPPORT_REQUIRED') if index==0 else result(False,reason='Joint actual source-route support absent')
        selected=np.isin(components[yy,xx],list(ids));sites=points[selected]
        outside=np.ones(len(sites),bool)
        for path,envelope in zip(paths,envelopes):outside &= cKDTree(path).query(sites)[0]>envelope+math.hypot(*size)/2
        if outside.any():
            info={'members':sorted(members),'unowned_pixels':int(outside.sum()),'witness_source_px':sites[np.flatnonzero(outside)[0]].tolist()}
            return invalid('JOINT_SOURCE_OWNERSHIP_REQUIRED: connected original paint leaves declared graph',**info) if index==0 else result(False,reason='Extra connected render paint leaves source graph',**info)
        fixed=np.zeros_like(mask);fixed[yy[selected],xx[selected]]=True;owned.append(fixed)
        details.append({'pixels':int(selected.sum()),'disconnected_pixels_excluded':int((~selected).sum())})
    tolerance=min(limits['route'],limits['marker'],limits['width'])
    measured=paint_cell_bound(*owned,tuple(v[0] for v in domains),tuple(v[1] for v in domains),tolerance)
    measured.update(method='complete_source_graph_joint_paint',members=sorted(members),ownership=details,
                    roi=[x,y,r-x,b-y],shaft_width='joint painted envelope; no isolated chord claimed',
                    tolerance_source='unchanged minimum original route/marker/width bounds',
                    every_short_arm_retained=True,candidate_alignment=False)
    return measured
