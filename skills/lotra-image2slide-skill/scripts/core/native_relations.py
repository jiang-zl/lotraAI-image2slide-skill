"""Bounded distance/containment on supported saved opaque Bezier fills.

Adaptive de Casteljau subdivision supplies an explicit Hausdorff error bound.
No vertex-only containment or nominal bounding-box contact can award PASS.
SVGs, text, effects, open/multiple paths and non-solid fills require the actual
host-matte route instead. This is a geometry check, not semantic recognition.
"""
import math
import numpy as np
from .boundary_geometry import segments,_split
from .mathml import NS
from .native_paint import opaque_fill

PRECISION=.005


def polygon(entry):
    props=entry['node'].find('p:spPr',NS)
    opaque_fill(props)
    if entry.get('error') or entry['tag']!='sp':raise ValueError(entry.get('error') or 'Native solid shape required')
    if any(props.find('a:'+k,NS) is not None for k in ('effectDag','scene3d','sp3d')) or len(props.find('a:effectLst',NS) or ()):
        raise ValueError('Effects need an actual native matte')
    preset=props.find('a:prstGeom',NS)
    if preset is not None and preset.get('prst') in ('ellipse','roundRect'):
        matrix=entry['matrix'];kind=preset.get('prst')
        if kind=='ellipse':rx=ry=.5
        else:
            ext=props.find('a:xfrm/a:ext',NS);w,h=float(ext.get('cx')),float(ext.get('cy'))
            guides=preset.findall('a:avLst/a:gd',NS)
            if len(guides)>1 or any(g.get('name')!='adj' or not g.get('fmla','').startswith('val ') for g in guides):
                raise ValueError('Unresolved rounded-rectangle guide')
            ratio=float(guides[0].get('fmla').split()[1])/100000 if guides else 1/6
            if not 0<ratio<=.5:raise ValueError('Invalid rounded-rectangle radius')
            radius=min(w,h)*ratio;rx,ry=radius/w,radius/h
        radius=float(np.linalg.svd(matrix[:2,:2]@np.diag([rx,ry]),compute_uv=False).max())
        count=max(4,math.ceil(math.pi/2/(2*math.acos(max(-1.,1-PRECISION/max(radius,PRECISION))))))
        if count>4096:raise ValueError('Analytic arc precision budget exhausted')
        points=[]
        for center,angle in (((1-rx,1-ry),0),((rx,1-ry),90),((rx,ry),180),((1-rx,ry),270)):
            for degrees in np.linspace(angle,angle+90,count+1):
                theta=math.radians(float(degrees));p=matrix@np.array([center[0]+rx*math.cos(theta),center[1]+ry*math.sin(theta),1.])
                if not points or np.linalg.norm(p[:2]-points[-1])>1e-9:points.append(p[:2])
        if np.linalg.norm(points[-1]-points[0])<1e-9:points.pop()
        return np.array(points)
    custom=props.find('a:custGeom',NS)
    if custom is not None and (len(custom.findall('a:pathLst/a:path',NS))!=1 or len(custom.findall('.//a:moveTo',NS))!=1):
        raise ValueError('Multiple or compound fills need the actual matte route')
    curves=segments(entry);points=[curves[0][0]];last=points[0]
    for curve in curves:
        if np.linalg.norm(curve[0]-last)>1e-7:raise ValueError('One continuous closed native path required')
        stack=[curve]
        while stack:
            p=stack.pop();a,b=p[0],p[-1];v=b-a
            t=np.clip((p-a)@v/max(float(v@v),1e-30),0,1)
            error=float(np.linalg.norm(p-(a+t[:,None]*v),axis=1).max())
            if error<=PRECISION:
                if np.linalg.norm(b-points[-1])>1e-9:points.append(b)
            else:
                left,right=_split(p);stack.extend((right,left))
            if len(points)+len(stack)>100000:raise ValueError('Native distance precision budget exhausted')
        last=curve[-1]
    if np.linalg.norm(points[-1]-points[0])>1e-7:raise ValueError('Open fill cannot prove physical contact')
    p=np.array(points[:-1])
    if len(p)<3:raise ValueError('Empty/degenerate native fill')
    # A self-intersecting polygon has no single physical interior in this
    # operator; never guess a winding/fill rule from a sampled outline.
    examined=0
    for i,(a,b) in enumerate(zip(p,np.roll(p,-1,axis=0))):
        ids=np.arange(i+2,len(p));ids=ids[ids!=len(p)-1] if i==0 else ids
        if not len(ids):continue
        c=p[ids];d=p[(ids+1)%len(p)]
        overlap=np.all(np.maximum(np.minimum(a,b),np.minimum(c,d))<=np.minimum(np.maximum(a,b),np.maximum(c,d))+1e-10,axis=1)
        c,d=c[overlap],d[overlap];examined+=len(c)
        if examined>100000:raise ValueError('Simple-contour validation budget exhausted')
        def cross(v,w):return v[...,0]*w[...,1]-v[...,1]*w[...,0]
        one,two=cross(b-a,c-a),cross(b-a,d-a)
        three,four=cross(d-c,a-c),cross(d-c,b-c)
        if np.any((one*two<=1e-18)&(three*four<=1e-18)):
            raise ValueError('Self-intersecting/touching fill needs explicit source topology and actual matte')
    return p


def clearance(points,poly):
    """Positive signed distance in a simple closed polygon; finite vertices."""
    points=np.atleast_2d(points);a=poly;b=np.roll(poly,-1,axis=0);v=b-a
    delta=points[:,None,:]-a[None,:,:]
    t=np.clip(np.sum(delta*v,axis=2)/np.maximum(np.sum(v*v,axis=1),1e-30),0,1)
    dist=np.linalg.norm(delta-t[:,:,None]*v,axis=2).min(1)
    py=points[:,1,None];px=points[:,0,None]
    crosses=(a[:,1]>py)!=(b[:,1]>py)
    dy=b[:,1]-a[:,1];safe_dy=np.where(abs(dy)>1e-30,dy,1.)
    intersection=(b[:,0]-a[:,0])*(py-a[:,1])/safe_dy+a[:,0]
    inside=np.sum(crosses & (px<intersection),axis=1)%2==1
    return np.where(inside,dist,-dist)


def fill_distance(first,second):
    uncertainty=2*PRECISION
    if np.max(clearance(first,second))>uncertainty or np.max(clearance(second,first))>uncertainty:
        return [0.,0.]
    # Closest points of disjoint line segments lie at an endpoint; detect
    # proper crossings explicitly before taking endpoint-to-segment distances.
    for a,b in zip(first,np.roll(first,-1,axis=0)):
        c=second;d=np.roll(second,-1,axis=0)
        def cross(v,w):return v[...,0]*w[...,1]-v[...,1]*w[...,0]
        one=cross(b-a,c-a);two=cross(b-a,d-a)
        three=cross(d-c,a-c);four=cross(d-c,b-c)
        if np.any((one*two<-1e-18)&(three*four<-1e-18)):return [0.,uncertainty]
    distance=min(float(np.abs(clearance(first,second)).min()),float(np.abs(clearance(second,first)).min()))
    return [max(0.,distance-uncertainty),distance+uncertainty]


def containment(parent,child,tolerance):
    uncertainty=2*PRECISION;upper=0.;examined=0
    stack=[(a,b) for a,b in zip(child,np.roll(child,-1,axis=0))]
    while stack:
        a,b=stack.pop();m=(a+b)/2;value=float(clearance(m,parent)[0]);half=float(np.linalg.norm(b-a))/2
        lower=max(0.,-value-uncertainty);bound=max(0.,half-value+uncertainty)
        examined+=1
        if lower>tolerance:return {'passed':False,'outside_lower_px':lower,'outside_upper_px':None,'examined':examined}
        if bound<=tolerance:upper=max(upper,bound);continue
        if examined>100000 or half<1e-7:
            return {'passed':False,'status':'required_unmeasured','reason':'Containment precision budget exhausted','examined':examined}
        stack.extend(((a,m),(m,b)))
    return {'passed':True,'outside_lower_px':0.,'outside_upper_px':upper,'examined':examined}


def validate(row,roles):
    pair=row.get('roles',[])
    if len(pair)!=2 or pair[0]==pair[1] or not set(pair)<=set(roles) or not row.get('source_evidence'):
        raise ValueError('Native relation needs two independent source roles and original evidence')
    if any(len(roles[r]['objects'])!=1 for r in pair):
        raise ValueError('Native geometry relation binds single fill owners; use actual interface mattes for assemblies')
    if row.get('kind')=='inside':
        if type(row.get('tolerance_px')) not in (int,float) or not .02<=row['tolerance_px']<=1:
            raise ValueError('Containment needs a bounded source-pixel edge uncertainty')
    elif row.get('kind')=='design_attachment':
        basis=row.get('design_basis',{})
        if (basis.get('status')!='inferred_detail' or not basis.get('source_feature') or
                not basis.get('approved_native_sha256') or not basis.get('reason') or
                type(row.get('min_overlap_area_px2')) not in (int,float) or row['min_overlap_area_px2']<=0):
            raise ValueError('Subpixel inferred attachment needs source-bound approved design and positive native overlap')
    elif row.get('kind') in ('attached','adjacent','intentional_separation'):
        interval=row.get('distance_px',[])
        if (len(interval)!=2 or not all(type(v) in (int,float) and math.isfinite(v) for v in interval)
                or min(interval)<0 or interval[1]<interval[0]):raise ValueError('Freeze a finite source-pixel boundary distance interval')
        if row['kind']=='attached' and (interval[0]!=0 or interval[1]>1):
            raise ValueError('Attachment cannot waive a visible gap')
    else:raise ValueError('Use a typed native physical relation')
    return row


def evaluate(row,roles,nodes):
    validate(row,roles)
    try:
        if row['kind']=='design_attachment':
            from .native_topology import attachment
            return attachment(row,roles,nodes)
        first,second=[polygon(nodes[roles[r]['objects'][0]]) for r in row['roles']]
        if row['kind']=='inside':
            result=containment(first,second,row['tolerance_px'])
            return {'status':'measured',**result,'flatten_error_bound_px':PRECISION}
        interval=fill_distance(first,second);lower,upper=row['distance_px']
        return {'status':'distance_measured_requires_solid_port' if row['kind']=='attached' else 'measured',
                'passed':row['kind']!='attached' and interval[0]>=lower and interval[1]<=upper,
                'distance_pass':interval[0]>=lower and interval[1]<=upper,
                'solid_attachment_certified':False if row['kind']=='attached' else None,
                'distance_interval_px':interval,'limits':row['distance_px'],'flatten_error_bound_px':PRECISION}
    except (ValueError,KeyError,TypeError,np.linalg.LinAlgError) as error:
        return {'status':'required_unmeasured','passed':False,'reason':str(error)}


def connected(objects,nodes):
    """A multi-leaf rigid role cannot hide disconnected body pieces."""
    try:
        polys=[polygon(nodes[n]) for n in objects]
        graph={i:set() for i in range(len(polys))}
        for i in graph:
            for j in range(i+1,len(polys)):
                # A known vector gap is real, however small. Raster edge
                # uncertainty cannot be used to bridge separate native fills.
                certified=(float(clearance(polys[i],polys[j]).max())>2*PRECISION or
                           float(clearance(polys[j],polys[i]).max())>2*PRECISION)
                if not certified:
                    # Exact polygons may share a positive-length edge. A
                    # single point or merely near edges do not prove a body.
                    from .boundary_geometry import segments
                    first,second=nodes[objects[i]],nodes[objects[j]]
                    exact=all(len(c)==2 for e in (first,second) for c in segments(e))
                    if exact:
                        for a,b in zip(polys[i],np.roll(polys[i],-1,axis=0)):
                            v=b-a;length=float(np.linalg.norm(v))
                            if length<1e-10:continue
                            for c,d in zip(polys[j],np.roll(polys[j],-1,axis=0)):
                                cross=lambda p,q:p[0]*q[1]-p[1]*q[0]
                                if (cross(v,c-a)*cross(v,d-a)<-1e-18 and
                                        cross(d-c,a-c)*cross(d-c,b-c)<-1e-18):certified=True
                                if abs(cross(v,c-a))>1e-9 or abs(cross(v,d-a))>1e-9:continue
                                t=sorted((float((c-a)@v/(v@v)),float((d-a)@v/(v@v))))
                                if min(1.,t[1])-max(0.,t[0])>1e-7:certified=True
                if certified:graph[i].add(j);graph[j].add(i)
        seen=set();todo=[0] if polys else []
        while todo:
            i=todo.pop()
            if i in seen:continue
            seen.add(i);todo.extend(graph[i]-seen)
        return {'status':'measured','passed':bool(polys) and len(seen)==len(polys),
            'disconnected_native_owners':[objects[i] for i in graph if i not in seen],
            'method':'certified-opaque-fill-continuity','positive_native_gap_allowed_px':0.}
    except (ValueError,KeyError,TypeError,np.linalg.LinAlgError) as error:
        return {'status':'required_unmeasured','passed':False,'reason':str(error)}


def matte_connected(response,size):
    """Actual opaque-core connectivity without discarding or bridging islands.

    Antialiasing can split thin strokes into opaque-core islands; that needs
    native stroke/topology evidence or finer observations and stays pending.
    This certifies sampled role continuity, never a solid interface width.
    """
    from scipy.ndimage import label
    sy,sx=size[1]/response.shape[0],size[0]/response.shape[1]
    if max(sx,sy)>.250001:return {'status':'required_unmeasured','passed':False,'reason':'Actual role capture needs at least 4x sampling'}
    mask=response<=2;yy,xx=np.where(mask)
    if not len(xx):return {'status':'measured','passed':False,'solid_components':0,'reason':'No opaque native role support'}
    core=mask[yy.min():yy.max()+1,xx.min():xx.max()+1]
    # Diagonal corner contact is not a physical bridge.
    labels,count=label(core)
    return {'status':'measured' if count==1 else 'required_unmeasured','passed':count==1,'solid_components':count,
        'method':'actual-host-4x-opaque-owner-union','sampling_uncertainty_px':math.hypot(sx,sy),
        'reason':None if count==1 else 'Disconnected opaque cores need a native stroke/topology explanation or finer actual observations',
        'limits':'No islands discarded; no artificial gap bridging or artwork dilation; solid port width remains a separate obligation.'}
