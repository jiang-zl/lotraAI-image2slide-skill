"""Independent saved native paint geometry; no nominal group-frame fallback.

Curve flattening is bounded. Unsupported native paint requires a measured host
matte; unknown/empty bounds are errors rather than infinitely distant objects.
"""
import math
import numpy as np
from shapely.geometry import Polygon,LineString,Point,box
from shapely.ops import unary_union
from .boundary_geometry import saved_nodes
from .mathml import NS
from .common import read_json,safe_path,digest

VERSION='saved-neighbor-geometry-1'
PRECISION=.025

def serial(geometry):
    if geometry.is_empty or not geometry.is_valid:raise ValueError('Empty or invalid visible geometry')
    return geometry.wkt

def box_xywh(g):
    a,b,c,d=g.bounds
    return [a,b,c-a,d-b]

def _stroke(entry,props):
    line=props.find('a:ln',NS)
    if line is None or line.find('a:noFill',NS) is not None:return 0.
    # A native 1pt default is applicable only when there is an explicit line
    # with no width attribute. Theme line inference is not silently accepted.
    emu=float(line.get('w',12700))
    parent=entry['parent_matrix'];scale=max(np.linalg.norm(parent[:2,i]) for i in (0,1))
    return emu*scale

def _point(entry,p):return (np.array([p[0],p[1],1.])@entry['matrix'].T)[:2].tolist()

def _flat(control,out,depth=0):
    chord=np.asarray(control[-1])-control[0];length=float(np.linalg.norm(chord))
    # Distance to the finite chord also catches collinear backtracking curves.
    err=max(float(Point(p).distance(LineString([control[0],control[-1]]))) if length else float(np.linalg.norm(np.asarray(p)-control[0])) for p in control)
    if err<=PRECISION:out.append(control[-1]);return
    if depth>=20:raise ValueError('Unresolved curve precision')
    levels=[np.asarray(control,float)]
    while len(levels[-1])>1:levels.append((levels[-1][:-1]+levels[-1][1:])/2)
    _flat([v[0].tolist() for v in levels],out,depth+1)
    _flat([v[-1].tolist() for v in reversed(levels)],out,depth+1)

def _paths(entry,props):
    geom=props.find('a:custGeom',NS);paths=[]
    if geom is not None:
        for path in geom.findall('a:pathLst/a:path',NS):
            w,h=float(path.get('w',0)),float(path.get('h',0))
            if min(w,h)<=0:raise ValueError('Unresolved native path guides')
            pts=[];closed=False
            for op in path:
                kind=op.tag.split('}')[-1]
                if kind=='moveTo':
                    if pts:paths.append((pts,closed,path.get('fill')!='none'))
                    pts=[_point(entry,[float(op[0].get('x'))/w,float(op[0].get('y'))/h])];closed=False
                elif kind=='lnTo':pts.append(_point(entry,[float(op[0].get('x'))/w,float(op[0].get('y'))/h]))
                elif kind in ('quadBezTo','cubicBezTo') and pts:
                    control=[pts[-1]]+[_point(entry,[float(p.get('x'))/w,float(p.get('y'))/h]) for p in op]
                    _flat(control,pts)
                elif kind=='close':closed=True
                else:raise ValueError('Native curve needs a bound actual matte: '+kind)
            if pts:paths.append((pts,closed,path.get('fill')!='none'))
        return paths
    preset=props.find('a:prstGeom',NS)
    kind=preset.get('prst') if preset is not None else None
    if kind in ('bentConnector2','bentConnector3','bentConnector4','bentConnector5'):
        from .connection_geometry import line
        segments=line(entry)['segments']
        return [([segments[0][0]]+[p[-1] for p in segments],False,False)]
    if kind in ('rect','line'):
        raw=[[0,0],[1,0],[1,1],[0,1]] if kind=='rect' else [[0,0],[1,1]]
    elif kind=='ellipse':
        # Circle polygon sagitta <= PRECISION after the actual transform.
        radius=max(np.linalg.norm(entry['matrix'][:2,i])/2 for i in (0,1))
        n=max(32,math.ceil(math.pi/math.acos(max(-1.,1-PRECISION/max(radius,PRECISION)))))
        raw=[[.5+.5*math.cos(i*2*math.pi/n),.5+.5*math.sin(i*2*math.pi/n)] for i in range(n)]
    elif kind=='roundRect':
        guides={v.get('name'):float(v.get('fmla').split()[1]) for v in props.findall('a:prstGeom/a:avLst/a:gd',NS) if v.get('fmla','').startswith('val ')}
        ratio=min(.5,max(0.,guides.get('adj',16667)/100000.));w=np.linalg.norm(entry['matrix'][:2,0]);h=np.linalg.norm(entry['matrix'][:2,1]);r=ratio*min(w,h)
        nx,ny=r/max(w,1e-12),r/max(h,1e-12);steps=max(8,math.ceil(math.pi/2/math.acos(max(-1.,1-PRECISION/max(r,PRECISION)))))
        raw=[]
        for cx,cy,start in [(1-nx,ny,-90),(1-nx,1-ny,0),(nx,1-ny,90),(nx,ny,180)]:
            raw.extend([[cx+nx*math.cos(math.radians(start)+i*math.pi/2/steps),cy+ny*math.sin(math.radians(start)+i*math.pi/2/steps)] for i in range(steps+1)])
    elif kind in ('triangle','rtTriangle','diamond','hexagon'):
        raw={'triangle':[[.5,0],[1,1],[0,1]],'rtTriangle':[[0,0],[1,1],[0,1]],'diamond':[[.5,0],[1,.5],[.5,1],[0,.5]],'hexagon':[[.25,0],[.75,0],[1,.5],[.75,1],[.25,1],[0,.5]]}[kind]
    else:raise ValueError('Preset needs a bound actual matte: '+str(kind))
    return [([_point(entry,p) for p in raw],kind!='line',True)]

def _matte(task,ref,size):
    from PIL import Image
    f=safe_path(task,ref['path'])
    if digest(f)!=ref['sha256']:raise ValueError('Actual owner matte changed')
    from shapely.affinity import affine_transform
    local=_matte_pixels(str(f),ref['sha256'],tuple(ref['pixel_size']))
    x,y,w,h=ref['roi']
    return affine_transform(local,[w/ref['pixel_size'][0],0,0,h/ref['pixel_size'][1],x,y])

from functools import lru_cache
@lru_cache(maxsize=256)
def _matte_pixels(file,sha256,pixel_size):
    from PIL import Image
    mask=np.asarray(Image.open(file).convert('L'))>=128
    if list(mask.shape[::-1])!=list(pixel_size):raise ValueError('Owner matte sampling mismatch')
    sy,sx=np.where(mask)
    if not len(sx):raise ValueError('Required owner matte is empty')
    # Exact union of occupied sample cells, not their bounding rectangle.
    pieces=[]
    for row in np.unique(sy):
        cols=np.where(mask[row])[0];starts=np.r_[0,np.where(np.diff(cols)>1)[0]+1];ends=np.r_[starts[1:]-1,len(cols)-1]
        pieces.extend(box(cols[a],row,cols[b]+1,row+1) for a,b in zip(starts,ends))
    return unary_union(pieces)

def read(task,state,candidate,mattes=None):
    pptx=safe_path(task,candidate['pptx']['path'])
    if digest(pptx)!=candidate['pptx']['sha256']:raise ValueError('Saved native artifact changed')
    nodes=saved_nodes(pptx,state['source_size']);rows={};errors=[];mattes=mattes or {}
    from .component_report import _native_ink
    ink=_native_ink(pptx,safe_path(task,candidate['render']['path']).parent/'text-bounds.json',state['source_size']) if candidate.get('render') else {}
    for name,entry in nodes.items():
        if entry['tag']=='grpSp':continue
        try:
            if entry.get('error'):raise ValueError(entry['error'])
            props=entry['node'].find('p:spPr',NS)
            has_text=bool(entry['node'].findall('.//a:t',NS) or entry['node'].findall('.//m:oMath',NS))
            ref=mattes.get(name)
            if ref:
                from .neighbor_capture import verify_transport
                verify_transport(task,candidate,name,ref)
                from .common import identity
                from lxml import etree as E
                signature=identity({'xml':E.tostring(entry['node'],method='c14n',exclusive=True).decode('utf-8'),'matrix':entry['matrix'].tolist()})
                if ref.get('pptx_hash')!=candidate['pptx']['sha256'] or ref.get('owner')!=name or ref.get('owner_native_signature')!=signature:raise ValueError('Stale or wrongly bound owner matte')
                for key in ('capture_pptx','host_render'):
                    dependency=ref.get(key)
                    if not dependency or digest(safe_path(task,dependency['path']))!=dependency['sha256']:raise ValueError('Missing or stale matte execution evidence')
                receipt=read_json(safe_path(task,ref['host_render']['path']))
                if receipt.get('pptx_hash')!=ref['capture_pptx']['sha256'] or receipt.get('backend')!=ref.get('backend'):raise ValueError('Matte does not refer to the executed host capture')
                g=_matte(task,ref,state['source_size']);width=float(ref.get('stroke_upper_px',0));method='ACTUAL_HOST_OWNER_MATTE'
            elif has_text:
                # Office TextRange Bounds are layout envelopes. They can be
                # centered while the painted equation/glyph remains off-center.
                # Existing actual owner capture is the authoritative geometry.
                raise ValueError('Actual owner glyph matte required; Office text-range envelope cannot establish visible centering')
            elif entry['tag'] in ('pic','graphicFrame'):
                raise ValueError('Picture/table needs a bound actual owner matte')
            else:
                if any(v.get('type','none')!='none' for v in props.findall('a:ln/a:headEnd',NS)+props.findall('a:ln/a:tailEnd',NS)):
                    raise ValueError('Arrowhead or tail paint needs a bound actual matte')
                if any(len(v) for v in props.findall('a:effectLst',NS)+props.findall('a:effectDag',NS)):
                    raise ValueError('Visible native effects need a bound actual matte')
                if any(float(v.get('val',100000))<100000 for v in props.findall('.//a:alpha',NS)):
                    raise ValueError('Transparent paint needs a bound actual matte')
                width=_stroke(entry,props);fill=any(props.find('a:'+k,NS) is not None for k in ('solidFill','gradFill','pattFill'))
                if not fill and width==0:
                    rows[name]={'id':name,'nonpaint':True,'reason':'Saved native explicit no fill and no line','parent':entry['parent_name']};continue
                paths=_paths(entry,props);pieces=[]
                if fill and sum(closed and paintfill and len(pts)>=3 for pts,closed,paintfill in paths)>1:
                    raise ValueError('Compound fill winding needs a bound actual matte')
                for pts,closed,paintfill in paths:
                    if len(pts)<2:raise ValueError('Empty native paint path')
                    if fill and closed and paintfill and len(pts)>=3:
                        poly=Polygon(pts)
                        if not poly.is_valid:poly=poly.buffer(0)
                        pieces.append(poly)
                    if width:
                        line=LineString(pts+[pts[0]] if closed else pts)
                        pieces.append(line.buffer(width/2,resolution=16,cap_style=1,join_style=1))
                g=unary_union(pieces);method='SAVED_NATIVE_CONTOUR_BOUNDED_FLATTENING'
            serial(g)
            rows[name]={'id':name,'box':box_xywh(g),'stroke':width,'geometry':g,'parent':entry['parent_name'],'order':list(nodes).index(name),'method':method,'precision_px':float(ref['sampling_error_px']) if ref else PRECISION}
        except (ValueError,TypeError,KeyError,AttributeError) as exc:errors.append({'object':name,'reason':str(exc)})
    # Logical groups use the union of descendants' actual paint. No group frame.
    for name,entry in reversed(list(nodes.items())):
        if entry['tag']!='grpSp':continue
        children=[r for r in rows.values() if r.get('parent')==name and not r.get('nonpaint')]
        if not children:
            errors.append({'object':name,'reason':'Group has no measured painted descendants'});continue
        g=unary_union([r['geometry'] for r in children]);rows[name]={'id':name,'box':box_xywh(g),'stroke':max(r['stroke'] for r in children),'geometry':g,'parent':entry['parent_name'],'order':list(nodes).index(name),'method':'DESCENDANT_PAINT_UNION','precision_px':PRECISION}
    return rows,errors
