"""Source-bound natural icon parts compiled to the existing native Scene.

The model is data, not executable code. Geometry is shared in a local frame;
placement belongs to instances. Colour buckets are never natural-part models.
"""
import copy
import math
from .common import identity

VERSION = 'semantic-icons-1'
KINDS = frozenset(('round_rect', 'ellipse', 'polygon', 'smooth_path', 'elliptical_band', 'line'))
VEHICLE_ROLES = frozenset(('vehicle_body', 'front_window', 'rear_window', 'side_window',
                           'mirror', 'signal_band', 'light'))


def _numbers(values, length=None):
    if (not isinstance(values, (list, tuple)) or (length and len(values) != length)
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)):
        raise ValueError('Finite measured geometry required')
    return list(values)


def _box(values):
    box = _numbers(values, 4)
    if min(box[2:]) <= 0:
        raise ValueError('Natural part needs a positive extent')
    return box


def construction_parameters(parameters):
    """Same mother cache for different instance poses; no style simplification."""
    return {k: copy.deepcopy(v) for k, v in parameters.items()
            if k not in ('pose_degrees', 'fit', 'stroke_units', 'source_container', 'source_anchor')}

def mother_identity(model):
    """Shared construction identity excludes per-instance source locators."""
    return identity({'version':model['version'],'family':model.get('family'),'frame':model.get('frame'),
        'parts':[{k:p[k] for k in ('id','role','geometry','style') if k in p} for p in model['parts']],
        'relations':[{k:v for k,v in r.items() if k!='source_note'} for r in model.get('relations',[])]})


def route(component):
    """Short, conditional route, never infer a vehicle from a generic device."""
    semantic = component.get('semantic_class', '')
    if semantic not in ('wireless_vehicle', 'top_view_vehicle', 'vehicle_icon'):
        return None
    return {'recipe': 'wireless_vehicle', 'model_version': VERSION,
            'reference': 'references/natural-icon-models.md',
            'required': ['source_evidence', 'observed_parts', 'parts with one natural role each'],
            'review': ['body contour and stroke', 'each observed window', 'signal bands and gaps',
                       'source pose', 'repeated-instance mother', 'road/container relations'],
            'scope': 'Native natural parts or an explicit source-matched SVG/PPTX alternative; no combined colour-layer substitute'}


def _band(geometry):
    from .semantic_curves import arc
    center = _numbers(geometry['center'], 2)
    radii = _numbers(geometry['radii'], 2)
    thickness = float(geometry['thickness'])
    if not math.isfinite(thickness) or not 0 < thickness < 2 * min(radii):
        raise ValueError('Band needs positive constant thickness and distinct inner/outer radii')
    start, end = _numbers([geometry['start_degrees'], geometry['end_degrees']], 2)
    rotation = geometry.get('rotation', 0)
    outer = arc(center, [r + thickness / 2 for r in radii], start, end, rotation)
    inner = arc(center, [r - thickness / 2 for r in radii], end, start, rotation)
    return outer + [{'op': 'lnTo', 'points': inner[0]['points']}] + inner[1:] + [{'op': 'close', 'points': []}]


def construct(parameters, *, vehicle=False):
    from .recipes import node, path
    from .semantic_curves import contour_node, smooth_outline
    model = copy.deepcopy(parameters.get('model', {}))
    if model.get('version') != VERSION or not model.get('source_evidence'):
        raise ValueError('Natural icon model must bind observed source geometry and uncertainty')
    observed = model.get('observed_parts')
    parts = model.get('parts')
    if not isinstance(observed, list) or not observed or not isinstance(parts, list) or not parts:
        raise ValueError('Original-only natural-part inventory required')
    ids = [p.get('id') for p in parts]
    if (any(not isinstance(i, str) or not i or any(c not in
            'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in i) for i in ids)
            or len(ids) != len(set(ids)) or set(observed) != set(ids)):
        raise ValueError('Every observed part must have exactly one named drawing binding')
    if vehicle and model.get('family') != 'top_view_vehicle':
        raise ValueError('Vehicle recipe needs source-supported top-view subtype')
    out = [node('root', 'group', model.get('frame', [0, 0, 100, 100]),
                {'natural_icon': {'version': VERSION, 'family': model.get('family'),
                 'mother': mother_identity(model),
                 'parts': {p['id']: p['role'] for p in parts},
                 'source_evidence': model['source_evidence'],
                 'review_properties': ['contour_regularity', 'stroke_width', 'part_proportion',
                                       'negative_space', 'signal_band_width', 'pose_consistency']}},
                semantic='wireless_vehicle' if vehicle else model.get('family', 'natural_icon'))]
    roles = []
    for part in parts:
        role = part.get('role')
        if not isinstance(role, str) or not role or part.get('roles'):
            raise ValueError('One natural semantic role per part; split same-colour unrelated parts')
        if vehicle and role not in VEHICLE_ROLES:
            raise ValueError('Unsupported vehicle part: retain uncertainty instead of inventing anatomy')
        roles.append(role)
        geometry = part.get('geometry', {})
        kind = geometry.get('kind')
        if kind not in KINDS or not part.get('source_note'):
            raise ValueError('Natural part needs a supported geometry family and source note')
        if role == 'signal_band' and kind != 'elliptical_band':
            raise ValueError('A declared regular signal band requires shared analytic band geometry')
        style = copy.deepcopy(part.get('style', {}))
        style.setdefault('line_join', 'round')
        style.setdefault('line_cap', 'round')
        stroke = style.pop('stroke', None)
        fill = style.pop('fill', None)
        width = style.pop('line_width', 0)
        if type(width) not in (int, float) or not math.isfinite(width) or width < 0:
            raise ValueError('Measured nonnegative stroke width required')
        name = part['id']
        if kind in ('round_rect', 'ellipse'):
            box = _box(geometry['bbox'])
            content = {'preset': 'roundRect' if kind == 'round_rect' else 'ellipse'}
            if kind == 'round_rect':
                radius = geometry.get('radius')
                if type(radius) not in (int, float) or not 0 < radius <= min(box[2:]) / 2:
                    raise ValueError('Rounded part needs a measured feasible radius')
                content['adjustments'] = [radius / min(box[2:])]
            obj = node(name, 'shape', box, content, 'root', role,
                       stroke=stroke, fill=fill, line_width=width, **style)
        elif kind == 'elliptical_band':
            obj = contour_node(name, _band(geometry), 'root', stroke, fill, width, role, True)
            obj['style'].update(style)
        else:
            points = [_numbers(p, 2) for p in geometry.get('points', [])]
            if len(points) < (2 if kind == 'line' else 3):
                raise ValueError('Source-supported semantic anchors required')
            if kind == 'smooth_path':
                if 'corner_indices' not in geometry or len(points) > 24:
                    raise ValueError('Use bounded natural anchors and explicit real corners, not dense pixel tracing')
                obj = contour_node(name, smooth_outline(points, True, geometry['corner_indices']),
                                   'root', stroke, fill, width, role, True)
            else:
                obj = path(name, points, 'root', stroke, fill, width, kind != 'line', role)
            obj['style'].update(style)
        obj['content']['natural_part'] = {'role': role, 'geometry_family': kind,
            'source_note': part['source_note'], 'status': part.get('status', 'inferred_from_raster')}
        out.append(obj)
    if vehicle and roles.count('vehicle_body') != 1:
        raise ValueError('One continuous source-supported vehicle body required')
    _relations(model.get('relations', []), {p['id']: p for p in parts}, out)
    return out


def _relations(relations, parts, objects):
    """Construction coherence only; real rendered part quality stays observed."""
    boxes = {o['id']: o['bbox'] for o in objects}
    for relation in relations:
        names = relation.get('parts', [])
        if not names or any(n not in parts for n in names) or not relation.get('source_note'):
            raise ValueError('Natural relation needs named original-supported parts')
        kind = relation.get('kind')
        tolerance = float(relation.get('tolerance', .001))
        if not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError('Finite relation tolerance required')
        if kind == 'inside_body_frame':
            if len(names) != 2:
                raise ValueError('Containment requires child and body')
            a, b = (boxes[n] for n in names)
            valid = (a[0] >= b[0] - tolerance and a[1] >= b[1] - tolerance and
                     a[0]+a[2] <= b[0]+b[2]+tolerance and a[1]+a[3] <= b[1]+b[3]+tolerance)
        elif kind == 'equal_stroke':
            values = [next(o for o in objects if o['id'] == n)['style'].get('line_width', 0) for n in names]
            valid = max(values)-min(values) <= tolerance
        elif kind == 'concentric_bands':
            geometries = [parts[n]['geometry'] for n in names]
            if any(g['kind'] != 'elliptical_band' for g in geometries):
                raise ValueError('Concentricity requires analytic bands')
            values = [g['center'] for g in geometries]
            valid = all(math.dist(values[0], v) <= tolerance for v in values[1:])
        else:
            raise ValueError('Unsupported natural relation; use an existing source relation contract')
        if not valid:
            raise ValueError('Natural icon coherence violated: ' + kind + ':' + ','.join(names))


def wireless_vehicle(parameters):
    return construct(parameters, vehicle=True)


def natural_icon(parameters):
    return construct(parameters)


def bake_pose(objects, degrees):
    """Pose native leaves around one mother centre, retaining identity groups.

    Component replacement can therefore preserve the existing parent mapping;
    the pose is not an extra group rotation that would disturb peer geometry.
    """
    objects=copy.deepcopy(objects)
    root=objects[0]
    x,y,w,h=root['bbox'];cx,cy=x+w/2,y+h/2
    angle=math.radians(degrees);c,s=math.cos(angle),math.sin(angle)
    root['style'].pop('rotation',None)
    root['content']['natural_icon']['pose_degrees']=degrees
    for obj in objects[1:]:
        x,y,w,h=obj['bbox'];dx,dy=x+w/2-cx,y+h/2-cy
        px,py=cx+c*dx-s*dy,cy+s*dx+c*dy
        obj['bbox']=[px-w/2,py-h/2,w,h]
        obj['style']['rotation']=obj['style'].get('rotation',0)+degrees
    return objects


def native_ink_samples(objects, stroke_factor=96/72):
    """Convex native control hulls, including actual leaf poses and round stroke."""
    from .geometry import path_operations
    samples=[]
    for obj in objects[1:]:
        x,y,w,h=obj['bbox'];content=obj['content'];preset=content.get('preset')
        if obj['render_type']=='path':
            points=[p for command in content.get('contours', [])
                    for _, values in path_operations(command) for p in values]
        elif preset in ('roundRect','ellipse'):
            radius=min(w,h)/2 if preset=='ellipse' else min(w,h)*content['adjustments'][0]
            rx,ry=(w/2,h/2) if preset=='ellipse' else (radius,radius)
            k=.5522847498307936
            points=[]
            for center,signs in (((w-rx,h-ry),(1,1)),((rx,h-ry),(-1,1)),
                                 ((rx,ry),(-1,-1)),((w-rx,ry),(1,-1))):
                ux,uy=center;sx,sy=signs
                points.extend([[ux+sx*rx,uy],[ux+sx*rx,uy+sy*k*ry],
                               [ux+sx*k*rx,uy+sy*ry],[ux,uy+sy*ry]])
            points=[[u/w,v/h] for u,v in points]
        else:
            points=[[0,0],[1,0],[1,1],[0,1]]
        angle=math.radians(obj['style'].get('rotation',0));c,s=math.cos(angle),math.sin(angle)
        pad=obj['style'].get('line_width',0)*stroke_factor/2 if obj['style'].get('stroke') else 0
        for u,v in points:
            dx,dy=(u-.5)*w,(v-.5)*h
            samples.append((x+w/2+c*dx-s*dy,y+h/2+s*dx+c*dy,pad))
    if not samples:raise ValueError('Natural native ink is empty')
    return samples


def native_ink_extent(objects, stroke_factor=96/72):
    samples=native_ink_samples(objects,stroke_factor)
    x,y=min(px-pad for px,py,pad in samples),min(py-pad for px,py,pad in samples)
    return [x,y,max(px+pad for px,py,pad in samples)-x,max(py+pad for px,py,pad in samples)-y]


def fit_native_ink(objects, target, container=None, anchor=None):
    """Fit posed control hulls and round stroke in original source geometry.

    Scale one whole mother about the observed centre; never clip signal parts
    or move peer artwork. Construction constraint, not measured similarity.
    """
    objects=copy.deepcopy(objects)
    target=_box(target);cx,cy=target[0]+target[2]/2,target[1]+target[3]/2
    if anchor is not None:
        if (anchor.get('part') not in objects[0]['content']['natural_icon']['parts']
                or not anchor.get('source_note')):
            raise ValueError('Original-supported named natural-part anchor required')
        cx,cy=_numbers(anchor['center'],2)
        named=next(o for o in objects[1:] if o['id']==objects[0]['id']+'__'+anchor['part'])
        x,y,w,h=named['bbox'];dx,dy=cx-x-w/2,cy-y-h/2
        for obj in objects[1:]:obj['bbox'][0]+=dx;obj['bbox'][1]+=dy
    samples=native_ink_samples(objects)
    boundary=None
    if container is not None:
        if container.get('kind')!='ellipse' or not container.get('source_note'):
            raise ValueError('Original-supported ellipse containment needs geometry and a source note')
        ex,ey,ew,eh=_box(container['bbox']);margin=container.get('margin',0)
        _numbers([margin])
        if not 0<=margin<min(ew,eh)/2:raise ValueError('Feasible original boundary margin required')
        boundary=(ex+ew/2,ey+eh/2,ew/2-margin,eh/2-margin)
    def feasible(scale):
        for px,py,pad in samples:
            px,py=cx+(px-cx)*scale,cy+(py-cy)*scale;pad*=scale
            if (px-pad<target[0]-1e-7 or px+pad>target[0]+target[2]+1e-7 or
                    py-pad<target[1]-1e-7 or py+pad>target[1]+target[3]+1e-7):return False
            if boundary:
                ex,ey,rx,ry=boundary
                if math.hypot((px-ex)/rx,(py-ey)/ry)+pad/min(rx,ry)>1:return False
        return True
    if not feasible(0):raise ValueError('Observed icon centre lies outside its semantic container; revise the source plan')
    scale=1.0
    if not feasible(scale):
        lo,hi=0.0,1.0
        for _ in range(36):
            mid=(lo+hi)/2
            if feasible(mid):lo=mid
            else:hi=mid
        scale=lo
    if scale<.75:
        raise ValueError('Containment needs a material size change; refine original pose/frame instead of silently shrinking')
    for obj in objects[1:]:
        x,y,w,h=obj['bbox'];obj['bbox']=[cx+(x-cx)*scale,cy+(y-cy)*scale,w*scale,h*scale]
        if obj['style'].get('line_width'):obj['style']['line_width']*=scale
    objects[0]['bbox']=target
    objects[0]['content']['natural_icon']['instance_fit']={
        'ink_scale':scale,'target':target,'container':copy.deepcopy(container),'source_anchor':copy.deepcopy(anchor),
        'construction':'posed native control hull with round-stroke envelope; shared geometry and centre retained'}
    return objects
