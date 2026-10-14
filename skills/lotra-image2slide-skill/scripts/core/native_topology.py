"""Paint-aware topology: certified solid attachments and open stroke graphs."""
import math
import numpy as np
from lxml import etree as E
from .mathml import NS
from .boundary_geometry import _split
from .native_relations import polygon,PRECISION
from .native_paint import color_alpha

def attachment(row,roles,nodes):
    from shapely.geometry import Polygon
    names=[roles[r]['objects'][0] for r in row['roles']]
    polys=[Polygon(polygon(nodes[n])) for n in names]
    if any(not p.is_valid or p.is_empty for p in polys):raise ValueError('Invalid attachment fill geometry')
    area=polys[0].intersection(polys[1]).area
    # Erode each side by its flattening uncertainty before certifying positive
    # overlap. Never use dilation or a near bounding box as physical contact.
    core=[p.buffer(-PRECISION) for p in polys]
    certified=core[0].intersection(core[1]).area
    minimum=row.get('min_overlap_area_px2')
    if type(minimum) not in (int,float) or not math.isfinite(minimum) or minimum<=0:
        raise ValueError('Design attachment needs a frozen positive overlap area')
    return {'status':'measured','passed':certified>=minimum,'solid_attachment_certified':certified>=minimum,
        'overlap_area_px2':area,'certified_overlap_area_px2':certified,'minimum_overlap_area_px2':minimum,
        'flatten_error_bound_px':PRECISION,'method':'eroded-saved-native-fill-intersection',
        'source_status':'inferred_detail_from_source_bound_approved_design'}

def _flatten(control):
    stack=[control];out=[control[0]]
    while stack:
        p=stack.pop();a,b=p[0],p[-1];v=b-a
        t=np.clip((p-a)@v/max(float(v@v),1e-30),0,1)
        if np.linalg.norm(p-(a+t[:,None]*v),axis=1).max()<=PRECISION:out.append(b)
        else:
            left,right=_split(p);stack.extend((right,left))
        if len(out)+len(stack)>100000:raise ValueError('Stroke precision budget exhausted')
    return np.asarray(out)

def stroke_geometry(entry):
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    if entry.get('error') or entry['tag'] not in ('sp','cxnSp'):raise ValueError('Supported saved stroked native owner required')
    props=entry['node'].find('p:spPr',NS);line=props.find('a:ln',NS)
    if line is None or line.find('a:solidFill',NS) is None or color_alpha(line.find('a:solidFill',NS))<1:
        raise ValueError('Stroke topology requires an explicit opaque stroke')
    if any(line.find('a:'+k,NS) is not None for k in ('prstDash','custDash','headEnd','tailEnd')):
        raise ValueError('Dashed/arrow strokes need a separate source topology contract')
    if any(props.find('a:'+k,NS) is not None for k in ('effectDag','scene3d','sp3d')) or len(props.find('a:effectLst',NS) or ()):
        raise ValueError('Stroke effects need an actual host observation')
    width=float(line.get('w',0));scale=float(np.linalg.svd(entry['parent_matrix'][:2,:2],compute_uv=False).min())
    radius=width*scale/2-PRECISION
    if radius<=0:raise ValueError('Stroke too thin for this analytic precision')
    preset=props.find('a:prstGeom',NS);raw=[];resolved_world=None
    if preset is not None:
        kind=preset.get('prst')
        if kind=='line':raw=[[[0.,0.],[1.,1.]]]
        elif kind=='rect':raw=[[[0.,0.],[1.,0.]],[[1.,0.],[1.,1.]],[[1.,1.],[0.,1.]],[[0.,1.],[0.,0.]]]
        elif kind in ('ellipse','roundRect'):
            # polygon() resolves these actual opaque native presets with the
            # same fixed analytical contour-error bound. Do not substitute a
            # frame or a presumed circle for unsupported unfilled presets.
            points=polygon(entry);resolved_world=[np.array([a,b]) for a,b in zip(points,np.roll(points,-1,axis=0))]
        else:raise ValueError('Unresolved preset stroke needs an actual native matte')
    else:
        geom=props.find('a:custGeom',NS)
        if geom is None:raise ValueError('Saved stroke path missing')
        for path in geom.findall('a:pathLst/a:path',NS):
            if path.get('stroke') in ('0','false'):continue
            w,h=float(path.get('w',0)),float(path.get('h',0))
            if min(w,h)<=0:raise ValueError('Unresolved native path dimensions')
            current=start=None
            for command in path:
                op=E.QName(command).localname
                pts=[[float(p.get('x'))/w,float(p.get('y'))/h] for p in command.findall('a:pt',NS)]
                if op=='moveTo':current=start=pts[0]
                elif op in ('lnTo','quadBezTo','cubicBezTo') and current is not None:
                    if len(pts)!={'lnTo':1,'quadBezTo':2,'cubicBezTo':3}[op]:raise ValueError('Malformed stroke')
                    raw.append([current]+pts);current=pts[-1]
                elif op=='close' and start is not None:raw.append([current,start]);current=start
                else:raise ValueError('Unresolved stroke operator')
    if not raw and resolved_world is None:raise ValueError('Empty stroke geometry')
    curves=resolved_world if resolved_world is not None else [(np.c_[p,np.ones(len(p))]@entry['matrix'].T)[:,:2] for p in map(np.asarray,raw)]
    cap={'flat':2,'rnd':1,'sq':3}.get(line.get('cap','flat'))
    if cap is None:raise ValueError('Unsupported stroke cap')
    geoms=[LineString(_flatten(c)).buffer(radius,cap_style=cap,join_style=2) for c in curves]
    return unary_union(geoms)

def stroke_connected(objects,nodes):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    geoms=[]
    for name in objects:
        entry=nodes[name]
        painted=[]
        try:painted.append(Polygon(polygon(entry)).buffer(-PRECISION))
        except ValueError:pass
        props=entry['node'].find('p:spPr',NS);line=props.find('a:ln',NS) if props is not None else None
        stroke=line.find('a:solidFill',NS) if line is not None else None
        if stroke is not None and color_alpha(stroke)>=1:
            painted.append(stroke_geometry(entry))
        elif not painted:raise ValueError('No certified opaque native paint: '+name)
        # A filled shape also paints its border. Excluding that border would
        # invent a gap between actually touching stroked faces. Both domains
        # remain conservative; never dilate across a positive unpainted gap.
        geom=unary_union(painted)
        if geom.is_empty or not geom.is_valid:raise ValueError('Invalid painted topology: '+name)
        geoms.append(geom)
    union=unary_union(geoms)
    # No small component is discarded and no positive gap is bridged.
    count=len(union.geoms) if hasattr(union,'geoms') else 1
    return {'status':'measured','passed':bool(geoms) and count==1,'painted_components':count,
            'method':'saved-native-stroke-and-fill-topology','native_owners':objects,
            'precision_px':PRECISION,'positive_gap_allowed_px':0.}
