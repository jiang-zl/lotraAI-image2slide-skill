"""Source-declared native faces and shared geometry; no inferred hidden anatomy.

All coordinates are continuous source pixels. Visibility, paint order and
material regions are explicit source decisions. Curves remain native cubics.
"""
import copy
import math
from .common import identity

VERSION = 'native-surfaces-1.34.0'
KINDS = {'prism', 'extruded_contour', 'elliptic_solid', 'annular_sector',
         'ellipse_stack', 'band', 'planar_detail'}


def vector(value, length=2):
    if (not isinstance(value, (list, tuple)) or len(value) != length or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in value)):
        raise ValueError('Finite source geometry required')
    return list(value)


def _add(a, b):
    return [a[i] + b[i] for i in (0, 1)]


def project(point, frame=None):
    """An explicit affine or projective plane, never a fitted candidate warp."""
    x, y = vector(point)
    if not frame:
        return [x, y]
    if 'homography' in frame:
        h = frame['homography']
        if len(h) != 3:
            raise ValueError('Source plane needs a finite 3 by 3 homography')
        h = [vector(row, 3) for row in h]
        d = h[2][0]*x + h[2][1]*y + h[2][2]
        if abs(d) < 1e-10:
            raise ValueError('SOURCE_DECISION_REQUIRED: singular source plane')
        return [(h[i][0]*x+h[i][1]*y+h[i][2])/d for i in (0, 1)]
    origin, u, v = [vector(frame[key]) for key in ('origin', 'u', 'v')]
    if abs(u[0]*v[1]-u[1]*v[0]) < 1e-10:
        raise ValueError('Source plane axes must be independent')
    return [origin[i]+x*u[i]+y*v[i] for i in (0, 1)]


def _commands(value):
    if not value or len(value) > 130 or value[0].get('op') != 'moveTo':
        raise ValueError('A bounded continuous source contour is required')
    result = []
    counts = {'moveTo': 1, 'lnTo': 1, 'cubicBezTo': 3, 'close': 0}
    for index, command in enumerate(value):
        op = command.get('op')
        if op not in counts or index and op == 'moveTo':
            raise ValueError('One continuous contour with native lines/cubics required')
        points = command.get('points', [])
        if len(points) != counts[op]:
            raise ValueError('Native curve command arity differs')
        result.append({'op': op, 'points': [vector(p) for p in points]})
    return result


def _poly(points, closed=True):
    if not 2 <= len(points) <= 64:
        raise ValueError('Use bounded semantic vertices, not pixel strips')
    result = [{'op': 'moveTo', 'points': [vector(points[0])]}]
    result += [{'op': 'lnTo', 'points': [vector(p)]} for p in points[1:]]
    if closed:
        result.append({'op': 'close', 'points': []})
    return result


def _segments(commands):
    start = current = commands[0]['points'][0]
    result = []
    for command in commands[1:]:
        if command['op'] == 'close':
            if current != start:
                result.append((current, {'op': 'lnTo', 'points': [start]}))
            break
        result.append((current, command))
        current = command['points'][-1]
    return result


def _reverse(segments, offset=(0, 0)):
    result = []
    for start, command in reversed(segments):
        points = ([command['points'][1], command['points'][0], start]
                  if command['op'] == 'cubicBezTo' else [start])
        result.append({'op': command['op'], 'points': [_add(p, offset) for p in points]})
    return result


def _wall(commands, depth):
    segments = _segments(commands)
    if not segments:
        raise ValueError('Observed wall span is empty')
    end = segments[-1][1]['points'][-1]
    return ([commands[0]]+[c for _, c in segments] +
            [{'op': 'lnTo', 'points': [_add(end, depth)]}] +
            _reverse(segments, depth) + [{'op': 'close', 'points': []}])


def _bezier(points, t):
    return [sum(math.comb(3, j)*(1-t)**(3-j)*t**j*points[j][i]
                for j in range(4)) for i in (0, 1)]


def _project_commands(commands, frame, precision=.05):
    if not frame or 'homography' not in frame:
        return [{'op': c['op'], 'points': [project(p, frame) for p in c['points']]}
                for c in commands]
    # A projective cubic is rational. Fit bounded native cubics in source
    # coordinates instead of transforming control points as if affine.
    if not .001 <= precision <= .25:
        raise ValueError('Freeze a bounded source-pixel representation precision')
    result = [{'op': 'moveTo', 'points': [project(commands[0]['points'][0], frame)]}]
    for start, command in _segments(commands):
        if command['op'] == 'lnTo':
            result.append({'op': 'lnTo', 'points': [project(command['points'][0], frame)]})
            continue
        points = [start]+command['points']
        def sample(t):
            return project(_bezier(points, t), frame)
        def fit(a, b, level=0):
            p, q = sample(a), sample(b)
            eps = min(1e-5, (b-a)/100)
            ta = [(sample(a+eps)[i]-p[i])/eps for i in (0, 1)]
            tb = [(q[i]-sample(b-eps)[i])/eps for i in (0, 1)]
            controls = [p, [p[i]+ta[i]*(b-a)/3 for i in (0, 1)],
                        [q[i]-tb[i]*(b-a)/3 for i in (0, 1)], q]
            error = max(math.dist(sample(a+(b-a)*t), _bezier(controls, t))
                        for t in (.125, .25, .375, .5, .625, .75, .875))
            if error > precision:
                if level >= 10 or len(result) >= 126:
                    raise ValueError('REPRESENTATION_DECISION_REQUIRED: projective curve budget')
                fit(a, (a+b)/2, level+1)
                fit((a+b)/2, b, level+1)
            else:
                result.append({'op': 'cubicBezTo', 'points': controls[1:]})
        fit(0, 1)
    if commands[-1]['op'] == 'close':
        result.append({'op': 'close', 'points': []})
    if len(result) > 130:
        raise ValueError('Projective contour exceeds finite native encoding budget')
    return result


def construct(spec):
    """Return ordinary Scene owners and an immutable construction manifest."""
    from .recipes import node
    from .semantic_curves import arc, contour_node
    cid, kind = spec.get('id'), spec.get('kind')
    if (not isinstance(cid, str) or not cid or kind not in KINDS or
            not spec.get('source_evidence')):
        raise ValueError('Source-owned registered native construction required')
    frame = spec.get('frame')
    if frame and not frame.get('source_evidence'):
        raise ValueError('Source plane needs independent source evidence')
    objects, parts, edges = [], [], {}
    parent = spec.get('parent')
    precision = spec.get('precision_source_px', .05)
    def face(name, commands, style, role, capabilities=(), holes=()):
        if not isinstance(style, dict) or not style.get('fill'):
            raise ValueError('Each observed face needs an explicit material fill')
        if name in {p['part'] for p in parts}:
            raise ValueError('Duplicate face or boundary identity')
        projected = _project_commands(_commands(commands), frame, precision)
        obj = contour_node(cid+'.'+name, projected, parent, style.get('stroke'),
                           style['fill'], style.get('line_width', 0), role, True)
        # Closed holes are disjoint subpaths with opposite winding. Connecting
        # them with a bridge would draw an unsupported radial seam when stroked.
        x,y,w,h = obj['bbox']
        for hole in holes:
            inner = _project_commands(_commands(hole), frame, precision)
            obj['content']['contours'].append({'commands':[
                {'op':c['op'],'points':[[(px-x)/w,(py-y)/h] for px,py in c.get('points',[])]}
                for c in inner], 'closed':True})
        obj['style'].update(copy.deepcopy(style))
        caps = {'editable', 'closed_contour', *capabilities}
        if any(c['op'] == 'cubicBezTo' for c in projected): caps.add('smooth_contour')
        if style.get('gradient'): caps.add('surface_shading')
        if frame: caps.add('projection')
        obj['content']['source_surface'] = {'construction': cid, 'part': name, 'role': role,
                                            'version': VERSION, 'capabilities': sorted(caps)}
        objects.append(obj)
        parts.append({'owner': obj['id'], 'part': name, 'role': role, 'capabilities': sorted(caps)})
        return obj
    def remember_edges(prefix, points):
        for i, p in enumerate(points): edges[prefix+str(i)] = [p, points[(i+1)%len(points)]]
    if kind == 'prism':
        polygon = [vector(p) for p in spec['footprint']]
        if len(polygon) < 3: raise ValueError('A prism requires a source footprint')
        depth = vector(spec['depth'])
        if math.hypot(*depth) <= 0: raise ValueError('Observed thickness must be positive')
        remember_edges('top.', polygon)
        lower = [_add(p, depth) for p in polygon]; remember_edges('bottom.', lower)
        for wall in spec.get('walls', []):
            i = wall['edge']
            if type(i) is not int or not 0 <= i < len(polygon): raise ValueError('Unknown source wall edge')
            j = (i+1)%len(polygon)
            face(wall['id'], _poly([polygon[i], polygon[j], lower[j], lower[i]]),
                 wall['style'], wall.get('role', 'outer_wall'), ('shared_edges', 'projection'))
        face('top', _poly(polygon), spec['top_style'], 'top_surface', ('shared_edges', 'projection'))
    elif kind == 'extruded_contour':
        contour = _commands(spec['contour']); depth = vector(spec['depth'])
        segments = _segments(contour)
        if contour[-1]['op'] != 'close' or math.hypot(*depth) <= 0:
            raise ValueError('Extruded outline needs closed source geometry and thickness')
        for wall in spec.get('walls', []):
            first, count = wall['first_segment'], wall['segment_count']
            if type(first) is not int or type(count) is not int or first < 0 or count <= 0 or first+count > len(segments):
                raise ValueError('Visible side span escaped its source contour')
            span = [{'op': 'moveTo', 'points': [segments[first][0]]}]+[c for _, c in segments[first:first+count]]
            face(wall['id'], _wall(span, depth), wall['style'], wall.get('role', 'side_surface'), ('shared_edges',))
        face('front', contour, spec['front_style'], 'front_surface', ('shared_edges',))
    elif kind in ('elliptic_solid', 'annular_sector'):
        center, radii, depth = vector(spec['center']), vector(spec['radii']), vector(spec['depth'])
        start, end = spec.get('start_degrees', 0), spec.get('end_degrees', 360)
        if min(radii) <= 0 or not 0 < abs(end-start) <= 360 or math.hypot(*depth) <= 0:
            raise ValueError('Observed elliptic extents/span/thickness required')
        inner = vector(spec['inner_radii']) if kind == 'annular_sector' else None
        if inner and any(not 0 < inner[i] < radii[i] for i in (0, 1)):
            raise ValueError('Inner wall must preserve a positive source hole')
        rotation = spec.get('rotation', 0)
        for wall in spec.get('walls', []):
            role = wall.get('role', 'outer_wall')
            if role not in ('inner_wall', 'outer_wall') or role == 'inner_wall' and not inner:
                raise ValueError('Wall role must match the observed elliptic structure')
            span = vector(wall['span'])
            if not min(start, end) <= min(span) < max(span) <= max(start, end):
                raise ValueError('Visible wall span escaped the source arc')
            curve = arc(center, inner if role == 'inner_wall' else radii, *span, rotation)
            face(wall['id'], _wall(curve, depth), wall['style'], role,
                 ('shared_edges', 'inner_wall') if role == 'inner_wall' else ('shared_edges',))
        outer = arc(center, radii, start, end, rotation)
        holes = []
        if inner and abs(end-start) == 360:
            contour = outer+[{'op':'close','points':[]}]
            holes = [arc(center,inner,end,start,rotation)+[{'op':'close','points':[]}]]
        elif inner:
            inside = arc(center, inner, end, start, rotation)
            contour = outer+[{'op': 'lnTo', 'points': inside[0]['points']}]+inside[1:]+[{'op': 'close', 'points': []}]
        else:
            contour = outer+([{'op': 'lnTo', 'points': [center]}] if abs(end-start) < 360 else [])+[{'op': 'close', 'points': []}]
        face('top', contour, spec['top_style'], 'top_surface', ('hole', 'shared_edges') if inner else ('shared_edges',), holes)
        # Radial end caps are only generated when explicitly observed.
        for cap in spec.get('end_caps', []):
            if not inner or cap['at'] not in ('start', 'end'):
                raise ValueError('Observed annular end cap requires a located endpoint')
            angle = start if cap['at'] == 'start' else end
            a = arc(center, radii, angle, angle+.001, rotation)[0]['points'][0]
            b = arc(center, inner, angle, angle+.001, rotation)[0]['points'][0]
            face(cap['id'], _poly([a, b, _add(b, depth), _add(a, depth)]), cap['style'], 'end_cap', ('shared_edges',))
    elif kind == 'ellipse_stack':
        levels = spec.get('levels', [])
        if not 1 <= len(levels) <= 32: raise ValueError('Bounded observed ellipse levels required')
        for level in levels:
            center, radii = vector(level['center']), vector(level['radii'])
            if min(radii) <= 0: raise ValueError('Positive source ellipse required')
            face(level['id'], arc(center, radii, 0, 360, level.get('rotation', 0))+[{'op':'close','points':[]}],
                 level['style'], level.get('role', 'elliptic_surface'))
    elif kind == 'band':
        upper, lower = _commands(spec['upper']), _commands(spec['lower'])
        if upper[-1]['op'] == 'close' or lower[-1]['op'] == 'close':
            raise ValueError('A band has independently observed open upper/lower boundaries')
        contour = upper+[{'op': 'lnTo', 'points': [lower[-1]['points'][-1]]}]+_reverse(_segments(lower))+[{'op':'close','points':[]}]
        face('band', contour, spec['style'], 'variable_width_band', ('variable_width',))
    else:
        contour = _commands(spec['contour']) if 'contour' in spec else _poly(spec['points'])
        face('detail', contour, spec['style'], spec.get('role', 'planar_detail'), ('projection',) if frame else ())
    for edge in spec.get('visible_edges', []):
        key = edge['edge']
        if key not in edges: raise ValueError('Visible edge must reference shared constructed vertices')
        from .recipes import path
        points = [project(p, frame) for p in edges[key]]
        style = edge['style']
        obj = path(cid+'.'+edge['id'], points, parent, style['stroke'], None, style['line_width'], False, 'visible_edge')
        obj['content']['source_surface'] = {'construction': cid, 'part': edge['id'], 'role': 'visible_edge',
                                            'version': VERSION, 'capabilities': ['editable', 'shared_edges']}
        objects.append(obj); parts.append({'owner':obj['id'],'part':edge['id'],'role':'visible_edge','capabilities':['editable','shared_edges']})
    if spec.get('paint_order'):
        if set(spec['paint_order']) != {p['part'] for p in parts} or len(spec['paint_order']) != len(parts):
            raise ValueError('Paint order must cover every observed face and edge once')
        order = {name:i for i,name in enumerate(spec['paint_order'])}
        objects.sort(key=lambda o:order[o['content']['source_surface']['part']])
    if len(objects) > 128: raise ValueError('Native construction exceeds its finite part budget')
    for i, obj in enumerate(objects): obj['z_order'] = spec.get('z_order', 0)+i
    manifest = {'version': VERSION, 'id': cid, 'kind': kind, 'source_evidence': spec['source_evidence'],
                'spec_hash': identity(spec), 'parts': parts,
                'geometry_hash': identity([{k:o[k] for k in ('id','render_type','bbox','content','style','parent','z_order')} for o in objects])}
    return objects, manifest


def expand(scene, contract):
    result = copy.deepcopy(scene); manifests = []
    specs = contract.get('native_constructions', [])
    if len(specs) > 512 or len({s.get('id') for s in specs}) != len(specs):
        raise ValueError('Distinct bounded native construction declarations required')
    owners = {o['id']:o for o in result['objects']}
    for spec in specs:
        objects, manifest = construct(spec)
        for obj in objects:
            if obj['id'] in owners:
                existing = owners[obj['id']]
                if any(existing.get(k) != obj.get(k) for k in ('render_type','bbox','content','style','parent','z_order')):
                    raise ValueError('SOURCE_DECISION_REQUIRED: construction collides with an existing owner')
            else:
                owners[obj['id']] = obj; result['objects'].append(obj)
        manifests.append(manifest)
    contract['construction_manifests'] = manifests
    return result
