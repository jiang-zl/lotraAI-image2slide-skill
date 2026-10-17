"""Saved DrawingML geometry in source coordinates; conservative containment.

The ellipse test certifies Bezier convex hulls after all ancestor transforms.
Unsupported geometry, effects or exhausted precision are explicitly unmeasured.
"""
import math
from zipfile import ZipFile
from lxml import etree as E
import numpy as np
from .mathml import NS
from .native_markup import active_children,semantic_parent,variants
from .execution_context import geometry

SHAPES = {'sp', 'grpSp', 'cxnSp', 'pic', 'graphicFrame'}


def _translation(x, y):
    return np.array([[1., 0., x], [0., 1., y], [0., 0., 1.]])


def _transform(xf, group=False, line=False):
    off, ext = xf.find('a:off', NS), xf.find('a:ext', NS)
    if off is None or ext is None:
        raise ValueError('Missing saved frame')
    x, y = float(off.get('x')), float(off.get('y'))
    w, h = float(ext.get('cx')), float(ext.get('cy'))
    if min(w, h) < 0 or (min(w, h) == 0 and (group or not line)) or max(w, h) == 0:
        raise ValueError('Nonpositive saved frame')
    if group:
        co, ce = xf.find('a:chOff', NS), xf.find('a:chExt', NS)
        if co is None or ce is None or min(float(ce.get('cx')), float(ce.get('cy'))) <= 0:
            raise ValueError('Missing saved child coordinates')
        scale = np.diag([w/float(ce.get('cx')), h/float(ce.get('cy')), 1.])
        base = _translation(x, y) @ scale @ _translation(-float(co.get('x')), -float(co.get('y')))
    else:
        base = _translation(x, y) @ np.diag([w, h, 1.])
    angle = math.radians(float(xf.get('rot', 0))/60000.)
    c, s = math.cos(angle), math.sin(angle)
    rotation = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    flip = np.diag([-1. if xf.get('flipH') in ('1', 'true') else 1.,
                    -1. if xf.get('flipV') in ('1', 'true') else 1., 1.])
    return _translation(x+w/2, y+h/2) @ rotation @ flip @ _translation(-x-w/2, -y-h/2) @ base


def require_projected(entry):
    """No 2D frame may certify unsupported shape, text or ancestor 3D effects."""
    current = entry['node']
    while current is not None:
        for path in ('p:spPr', 'p:grpSpPr', 'p:txBody/a:bodyPr'):
            props = current.find(path, NS)
            if props is not None and any(props.find('a:'+key, NS) is not None for key in ('scene3d','sp3d')):
                raise ValueError('MEASUREMENT_REQUIRED: native shape/text/ancestor 3D needs a qualified extractor; prefer projected native surfaces')
        current = current.getparent()


@geometry
def saved_nodes(pptx, size):
    """Actual leaf frames and geometry, preserving affine parent transforms."""
    from .resource_facts import xml_part
    tree = xml_part(pptx, 'ppt/slides/slide1.xml')
    canvas = xml_part(pptx, 'ppt/presentation.xml').find('p:sldSz', NS)
    scale = np.diag([size[0]/int(canvas.get('cx')), size[1]/int(canvas.get('cy')), 1.])
    result = {}
    def visit(parent, mapping, inherited_error=None):
        for node in active_children(parent):
            tag = E.QName(node).localname
            if tag not in SHAPES:
                continue
            props = node.find('p:grpSpPr' if tag == 'grpSp' else 'p:spPr', NS)
            xf = node.find('p:xfrm', NS) if tag == 'graphicFrame' else (props.find('a:xfrm', NS) if props is not None else None)
            name_node = node.find('.//p:cNvPr', NS)
            name = name_node.get('name')
            if name in result:
                raise ValueError('Ambiguous saved native name: '+name)
            entry = {'node': node, 'tag': tag, 'error': inherited_error, 'matrix': None, 'frame': None,
                     'parent_matrix': mapping, 'parent': parent}
            logical_parent=semantic_parent(node)
            meta=logical_parent.find('p:nvGrpSpPr/p:cNvPr',NS) if E.QName(logical_parent).localname=='grpSp' else None
            entry['parent_name']=meta.get('name') if meta is not None else None
            entry['compatibility']=variants(node)
            result[name] = entry
            try:
                require_projected(entry)
                if inherited_error or xf is None:
                    raise ValueError(inherited_error or 'Missing saved transform')
                preset = props.find('a:prstGeom', NS) if props is not None else None
                is_line = tag == 'cxnSp' or preset is not None and preset.get('prst') == 'line'
                entry['matrix'] = mapping @ _transform(xf, tag == 'grpSp', is_line)
                if tag != 'grpSp':
                    corners = np.array([[0., 0., 1.], [1., 0., 1.], [1., 1., 1.], [0., 1., 1.]]) @ entry['matrix'].T
                    lo, hi = corners[:, :2].min(0), corners[:, :2].max(0)
                    entry['frame'] = [*lo.tolist(), *(hi-lo).tolist()]
                    entry['axis_aligned'] = (abs(entry['matrix'][0, 1])+abs(entry['matrix'][1, 0]) < 1e-7)
            except (ValueError, TypeError, np.linalg.LinAlgError) as error:
                entry['error'] = str(error)
            if tag == 'grpSp':
                visit(node, entry['matrix'] if entry['matrix'] is not None else mapping, entry['error'])
    visit(tree.find('p:cSld/p:spTree', NS), scale)
    return result


def segments(entry):
    """Closed solid fill boundaries as Bezier control polygons in source px."""
    if entry['error'] or entry['tag'] != 'sp':
        raise ValueError(entry['error'] or 'Unsupported fill owner')
    props = entry['node'].find('p:spPr', NS)
    if any(props.find('a:'+key, NS) is not None for key in ('effectDag', 'scene3d', 'sp3d')):
        raise ValueError('Unsupported effect geometry')
    effects = props.find('a:effectLst', NS)
    if effects is not None and len(effects):
        raise ValueError('Effect paint needs independent actual coverage')
    if not any(props.find('a:'+key, NS) is not None for key in ('solidFill', 'gradFill', 'pattFill')):
        raise ValueError('Missing actual fill')
    preset = props.find('a:prstGeom', NS)
    if preset is not None:
        if preset.get('prst') != 'rect':
            raise ValueError('Unsupported child preset; do not substitute its bounding box')
        points = [[0., 0.], [1., 0.], [1., 1.], [0., 1.], [0., 0.]]
        raw = [np.array([a, b]) for a, b in zip(points, points[1:])]
    else:
        geometry = props.find('a:custGeom', NS)
        if geometry is None:
            raise ValueError('Missing saved fill geometry')
        raw = []
        for path in geometry.findall('a:pathLst/a:path', NS):
            if path.get('fill') == 'none':
                continue
            width, height = float(path.get('w', 0)), float(path.get('h', 0))
            if min(width, height) <= 0:
                raise ValueError('Unresolved saved path dimensions')
            current = start = None
            closed = False
            for command in path:
                op = E.QName(command).localname
                pts = [[float(p.get('x'))/width, float(p.get('y'))/height] for p in command.findall('a:pt', NS)]
                if op == 'moveTo':
                    if current is not None and not closed:
                        raise ValueError('Open filled subpath')
                    current = start = pts[0]; closed = False
                elif op in ('lnTo', 'quadBezTo', 'cubicBezTo') and current is not None:
                    expected = {'lnTo': 1, 'quadBezTo': 2, 'cubicBezTo': 3}[op]
                    if len(pts) != expected:
                        raise ValueError('Malformed saved path')
                    raw.append(np.array([current]+pts)); current = pts[-1]
                elif op == 'close' and start is not None:
                    raw.append(np.array([current, start])); current = start; closed = True
                else:
                    raise ValueError('Unsupported saved path operator: '+op)
            if not closed:
                raise ValueError('Open fill cannot certify a closed semantic domain')
    if not raw:
        raise ValueError('Empty fill boundary')
    return [(np.c_[row, np.ones(len(row))] @ entry['matrix'].T)[:, :2] for row in raw]


def _split(points):
    rows = [points]
    while len(rows[-1]) > 1:
        rows.append((rows[-1][:-1]+rows[-1][1:])/2)
    return np.array([row[0] for row in rows]), np.array([row[-1] for row in rows[::-1]])


def clip_polygon(curves, center, axes, precision_px=.01, inset_px=.02):
    """Bounded curve flattening and an inscribed convex ellipse clip.

    Only one source-declared continuous simple plane is eligible. Holes and
    disconnected results are refused, rather than silently joined/flattened.
    """
    if not 0.001 <= precision_px <= .025 or not 0 <= inset_px <= .05:
        raise ValueError('Bounded source-pixel clip precision required')
    radii = np.linalg.svd(axes, compute_uv=False)
    if min(radii) <= inset_px:
        raise ValueError('Container would disappear under the numeric inset')
    vertices = [curves[0][0]]
    for curve in curves:
        pending = [curve]
        while pending:
            row = pending.pop(); a, b = row[0], row[-1]; delta = b-a
            t = np.clip(((row-a) @ delta)/max(float(delta @ delta), 1e-30), 0, 1)
            error = float(np.linalg.norm(row-(a+t[:, None]*delta), axis=1).max())
            if error <= precision_px:
                vertices.append(b)
            else:
                left, right = _split(row); pending.extend((right, left))
            if len(vertices)+len(pending) > 200000:
                raise ValueError('Clip precision exceeds bounded geometry resources')
    if np.linalg.norm(vertices[-1]-vertices[0]) > 1e-7:
        raise ValueError('One continuous closed source plane required')
    vertices = np.array(vertices[:-1])
    # A uniform conservative inset remains valid under affine ellipse maps.
    axes = axes*(1-inset_px/min(radii)); radius = float(np.linalg.svd(axes, compute_uv=False).max())
    count = max(64, math.ceil(math.pi/math.acos(max(-1., 1-precision_px/radius))))
    if count > 4096:
        raise ValueError('Ellipse precision exceeds bounded clip polygon resources')
    angles = np.arange(count)*2*math.pi/count
    clip = np.c_[np.cos(angles), np.sin(angles)] @ axes.T + center
    if np.linalg.det(axes) < 0:
        clip = clip[::-1]
    def side(a, b, points):
        delta = b-a; offset = points-a
        return delta[0]*offset[..., 1]-delta[1]*offset[..., 0]
    for a, b in zip(clip, np.roll(clip, -1, axis=0)):
        if len(vertices) < 3:
            raise ValueError('Clipping would erase the semantic plane')
        output = []; previous = vertices[-1]; ps = side(a, b, previous)
        for current in vertices:
            cs = side(a, b, current)
            if (cs >= 0) != (ps >= 0):
                output.append(previous+ps/(ps-cs)*(current-previous))
            if cs >= 0:
                output.append(current)
            previous, ps = current, cs
        vertices = np.array(output)
    compact = []
    for point in vertices:
        if not compact or np.linalg.norm(point-compact[-1]) > 1e-8:
            compact.append(point)
    if len(compact) > 1 and np.linalg.norm(compact[0]-compact[-1]) < 1e-8:
        compact.pop()
    vertices = np.array(compact)
    if not 3 <= len(vertices) <= 8000:
        raise ValueError('Invalid/over-budget clipped plane')
    # Proper crossings or repeated non-neighbour vertices indicate topology
    # outside this operator's single simple-plane contract.
    for i, a in enumerate(vertices):
        for j in range(i+2, len(vertices)):
            if i == 0 and j == len(vertices)-1:
                continue
            if np.linalg.norm(a-vertices[j]) < 1e-8:
                raise ValueError('Disconnected/touching clipped topology requires a new semantic plan')
        b = vertices[(i+1) % len(vertices)]
        ids = [j for j in range(i+2, len(vertices)) if not (i == 0 and j == len(vertices)-1)]
        if not ids:
            continue
        c, d = vertices[ids], vertices[(np.array(ids)+1) % len(vertices)]
        if np.any((side(a, b, c)*side(a, b, d) < -1e-12) & (np.array([side(p, q, a) for p, q in zip(c, d)])*np.array([side(p, q, b) for p, q in zip(c, d)]) < -1e-12)):
            raise ValueError('Self-crossing clipped topology requires a new semantic plan')
    return vertices, {'flatten_error_bound_source_px': precision_px, 'ellipse_chord_error_bound_source_px': radius*(1-math.cos(math.pi/count)),
                      'inset_source_px': inset_px, 'ellipse_polygon_vertices': count, 'output_vertices': len(vertices)}


def inside_ellipse(nodes, container, child, tolerance_px=.01):
    """Certify the whole fill, not sampled vertices or colour similarity."""
    result = {'container': container, 'object': child, 'status': 'UNMEASURED', 'passed': False,
              'tolerance_source_px': tolerance_px, 'method': 'saved-affine-bezier-convex-hull'}
    try:
        body, item = nodes[container], nodes[child]
        if body['error'] or body['tag'] != 'sp':
            raise ValueError(body['error'] or 'Select an independent ellipse body')
        preset = body['node'].find('p:spPr/a:prstGeom', NS)
        if preset is None or preset.get('prst') != 'ellipse':
            raise ValueError('Analytic ellipse body required')
        matrix = body['matrix']; axes = matrix[:2, :2]/2
        center = (matrix @ np.array([.5, .5, 1.]))[:2]
        inverse = np.linalg.inv(axes)
        radii = np.linalg.svd(axes, compute_uv=False)
        radius, min_radius = float(radii.max()), float(radii.min())
        pending = [(row-center) @ inverse.T for row in segments(item)]
        lower = upper = 0.; examined = 0; uncertain = False
        while pending:
            control = pending.pop(); examined += 1
            endpoint_max = float(np.linalg.norm(control[[0, -1]], axis=1).max())
            bound = float(np.linalg.norm(control, axis=1).max())
            lower = max(lower, max(0., endpoint_max-1)*min_radius)
            if lower > tolerance_px:
                result.update(status='FAIL', reason='Actual fill boundary outside container',
                              outside_distance_lower_px=lower, examined_intervals=examined)
                return result
            if bound <= 1+tolerance_px/radius:
                upper = max(upper, max(0., bound-1)*radius)
                continue
            if examined > 200000 or np.ptp(control, axis=0).max()*radius < 1e-9:
                uncertain = True; break
            a, b = _split(control); pending.extend((a, b))
        result.update(status='UNMEASURED' if uncertain else 'PASS', passed=not uncertain,
                      outside_distance_upper_px=None if uncertain else upper,
                      outside_distance_lower_px=lower, examined_intervals=examined)
        if uncertain:
            result['reason'] = 'Precision/resource bound exhausted; no sampled PASS'
    except (ValueError, KeyError, TypeError, np.linalg.LinAlgError) as error:
        result['reason'] = str(error)
    return result
