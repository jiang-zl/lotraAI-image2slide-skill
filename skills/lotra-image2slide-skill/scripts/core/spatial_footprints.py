"""Complete native logical domains with bounded rational-curve flattening.

Footprints exclude shadows and upper bodies by explicit original feature
ownership, never by substituting an arbitrary point or page-aligned box.
"""
import math
import numpy as np
from lxml import etree as E
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union, polygonize
from .mathml import NS


def _polygon(points, maximum=512):
    value = np.asarray(points, float)
    if value.ndim != 2 or value.shape[1] != 2 or not 3 <= len(value) <= maximum or not np.isfinite(value).all():
        raise ValueError('Bounded finite semantic polygon required')
    result = Polygon(value)
    if result.is_empty or not result.is_valid or result.area <= 0:
        raise ValueError('Valid simple semantic footprint required')
    return result


def _split(control):
    rows = [control]
    while len(rows[-1]) > 1:
        rows.append((rows[-1][:-1]+rows[-1][1:])/2)
    return np.array([r[0] for r in rows]), np.array([r[-1] for r in rows[::-1]])


def _flatten(control, precision, budget):
    """Positive rational Beziers remain inside their dehomogenized control hull."""
    todo, result, error = [(np.asarray(control, float), 0)], [], 0.
    while todo:
        row, depth = todo.pop()
        if not np.isfinite(row).all() or np.any(np.abs(row[:, 2]) < 1e-12):
            raise ValueError('Footprint projects through infinity')
        if np.all(row[:, 2] < 0):row = -row
        if np.any(row[:, 2] <= 0):
            raise ValueError('A footprint curve crosses the projective horizon')
        local = row[:, :2]/row[:, 2:]
        line = LineString([local[0], local[-1]])
        distance = max(float(line.distance(Point(p))) for p in local)
        if distance <= precision or len(row) == 2:
            result.append(local[-1].tolist()); error = max(error, distance)
            budget[0] -= 1
            if budget[0] < 0:raise ValueError('Complete footprint exceeds finite curve resources')
        else:
            if depth >= 24:raise ValueError('Complete footprint precision is unresolved')
            left, right = _split(row)
            todo.extend(((right, depth+1), (left, depth+1)))
    return result, error


def _domain(rings, error):
    # DrawingML fill uses nonzero winding. Preserve holes and disconnected parts.
    polygons = [_polygon(r,16384) for r in rings]
    signs = [1 if np.sum(np.asarray(r)[:, 0]*np.roll(np.asarray(r)[:, 1], -1)-
                         np.roll(np.asarray(r)[:, 0], -1)*np.asarray(r)[:, 1]) > 0 else -1 for r in rings]
    edges = unary_union([LineString(list(p.exterior.coords)) for p in polygons])
    cells = [p for p in polygonize(edges) if sum(s for s, q in zip(signs, polygons)
                                               if q.covers(p.representative_point())) != 0]
    result = unary_union(cells)
    if result.is_empty or not result.is_valid or result.area <= 0:
        raise ValueError('Unresolved complete native fill domain')
    return {'geometry': result, 'error': error}


def _ellipse(center, radii):
    c, r = np.asarray(center, float), np.asarray(radii, float)
    if c.shape != (2,) or r.shape != (2,) or not np.isfinite([c, r]).all() or np.min(r) <= 0:
        raise ValueError('Finite positive ellipse dimensions required')
    w = math.sqrt(.5)
    anchors = [([1, 0], [1, 1], [0, 1]), ([0, 1], [-1, 1], [-1, 0]),
               ([-1, 0], [-1, -1], [0, -1]), ([0, -1], [1, -1], [1, 0])]
    return [[np.r_[c+r*np.array(p), 1.]*weight for p, weight in zip(triple, (1., w, 1.))]
            for triple in anchors]


def _commands(commands):
    current = start = None; curves = []; closed = False
    if not commands or len(commands) > 512:raise ValueError('Bounded semantic native contour required')
    for command in commands:
        op, pts = command['op'], command.get('points', [])
        if op == 'moveTo' and current is None:
            current = start = np.asarray(pts[0], float)
        elif op in ('lnTo', 'quadBezTo', 'cubicBezTo') and current is not None and not closed:
            if len(pts) != {'lnTo': 1, 'quadBezTo': 2, 'cubicBezTo': 3}[op]:
                raise ValueError('Native footprint command arity differs')
            row = np.asarray([current, *pts], float)
            if row.shape[1] != 2 or not np.isfinite(row).all():raise ValueError('Finite footprint controls required')
            curves.append(np.c_[row, np.ones(len(row))]); current = row[-1]
        elif op == 'close' and current is not None and not closed:
            if not np.array_equal(current, start):curves.append(np.c_[[current, start], np.ones(2)])
            closed = True
        else:raise ValueError('Unsupported/open semantic footprint contour')
    if not closed or not curves:raise ValueError('Complete logical domain must be closed')
    return curves


def _measure_curves(contours, matrix, precision):
    budget, rings, error = [16384], [], 0.
    for curves in contours:
        ring = []
        for curve in curves:
            control = np.asarray(curve) @ matrix.T
            if not ring:
                if abs(control[0, 2]) < 1e-12:raise ValueError('Footprint starts at infinity')
                ring.append((control[0, :2]/control[0, 2]).tolist())
            end, bound = _flatten(control, precision, budget)
            ring.extend(end); error = max(error, bound)
        if len(ring) > 16385:raise ValueError('Complete footprint vertex budget exceeded')
        # Source polygons have a tighter authoring bound; measured curves may
        # need more certified subdivision vertices, which are program produced.
        if len(ring) < 4 or not np.allclose(ring[0], ring[-1], atol=1e-8, rtol=0):
            raise ValueError('Saved logical domain is not closed')
        rings.append(ring[:-1])
    return _domain(rings, error)


def source_region(spec):
    geometry = spec.get('geometry', {})
    kind = geometry.get('kind')
    if kind == 'polygon':
        outer = _polygon(geometry['outer'])
        holes = [_polygon(p) for p in geometry.get('holes', [])]
        if any(not outer.covers(h) for h in holes):raise ValueError('Source hole escaped its footprint')
        result = outer.difference(unary_union(holes)) if holes else outer
        if not result.is_valid or result.is_empty:raise ValueError('Invalid source footprint holes')
        return {'geometry': result, 'error': 0.}
    if kind == 'ellipse':contours = [_ellipse(geometry['center'], geometry['radii'])]
    elif kind == 'path':contours = [_commands(c) for c in geometry['contours']]
    else:raise ValueError('Observe a compact polygon, ellipse or bounded curve footprint')
    return _measure_curves(contours, np.eye(3), spec['precision'])


def validate_bindings(contract, observed, scene):
    footprints = {f['id']: f for f in observed['spatial'].get('footprints', [])}
    bindings = contract.get('spatial_footprint_bindings', [])
    if len(bindings) != len({b.get('footprint') for b in bindings}) or {b.get('footprint') for b in bindings} != set(footprints):
        raise ValueError('Every complete original footprint needs one explicit native-domain binding')
    nodes = {n['id']: n for n in scene['objects']}
    features = {b['feature']: b for b in contract['feature_bindings']}
    for binding in bindings:
        spec = footprints[binding['footprint']]
        expected = {o for name in spec['features'] for o in features[name]['owners']}
        owners = binding.get('owners', [])
        if (not owners or len(owners) != len(set(owners)) or set(owners) != expected
                or not binding.get('source_evidence') or binding.get('method') not in ('native_domain', 'native_text_frame')):
            raise ValueError('Footprint binding must cover all owners of its independently identified domain features')
        if any(nodes[o]['render_type'] == 'group' for o in owners):
            raise ValueError('Bind actual native descendants, never a group envelope')
        if binding['method'] == 'native_text_frame' and any(nodes[o]['render_type'] not in ('text', 'equation', 'table') for o in owners):
            raise ValueError('Only native text/math/table logical frames may use text-frame footprints')


def _native_contours(entry, method):
    from .boundary_geometry import require_projected
    require_projected(entry)
    if entry.get('error') or entry.get('matrix') is None or entry['tag'] == 'grpSp':
        raise ValueError(entry.get('error') or 'Saved leaf footprint required')
    if method == 'native_text_frame':
        return [_commands([{'op': 'moveTo', 'points': [[0, 0]]},
            *[{'op': 'lnTo', 'points': [p]} for p in [[1, 0], [1, 1], [0, 1]]], {'op': 'close'}])]
    props = entry['node'].find('p:spPr', NS)
    if props is None or any(props.find('a:'+k, NS) is not None for k in ('scene3d', 'sp3d')):
        raise ValueError('Unsupported actual native footprint geometry')
    preset = props.find('a:prstGeom', NS)
    if preset is not None:
        name = preset.get('prst')
        if name == 'ellipse':return [_ellipse([.5, .5], [.5, .5])]
        polygons = {'rect': [[0, 0], [1, 0], [1, 1], [0, 1]],
            'triangle': [[.5, 0], [1, 1], [0, 1]], 'rtTriangle': [[0, 0], [1, 1], [0, 1]],
            'diamond': [[.5, 0], [1, .5], [.5, 1], [0, .5]]}
        if name not in polygons or len(preset.findall('a:avLst/a:gd', NS)):
            raise ValueError('This preset needs a qualified complete-domain extractor; no box substitution')
        p = polygons[name]
        return [_commands([{'op': 'moveTo', 'points': [p[0]]},
                           *[{'op': 'lnTo', 'points': [v]} for v in p[1:]], {'op': 'close'}])]
    contours = []
    for path in props.findall('a:custGeom/a:pathLst/a:path', NS):
        width, height = float(path.get('w', 0)), float(path.get('h', 0))
        if min(width, height) <= 0:raise ValueError('Unresolved native footprint path coordinates')
        commands = []
        for command in path:
            op = E.QName(command).localname
            if op == 'moveTo' and commands:
                contours.append(_commands(commands)); commands = []
            commands.append({'op': op, 'points': [[float(p.get('x'))/width, float(p.get('y'))/height]
                                                 for p in command.findall('a:pt', NS)]})
        if commands:contours.append(_commands(commands))
    if not contours:raise ValueError('No complete saved logical contour')
    return contours


def measure(spec, binding, native, graph):
    inverse = np.linalg.inv(graph.matrix(spec['frame']))
    pieces = []
    for owner in binding['owners']:
        entry = native[owner]
        pieces.append(_measure_curves(_native_contours(entry, binding['method']), inverse @ entry['matrix'], spec['precision']))
    geometry = unary_union([p['geometry'] for p in pieces])
    error = max(p['error'] for p in pieces)
    wanted = source_region(spec)
    margin = spec['tolerance']-error-wanted['error']
    if margin < 0:
        raise ValueError('Frozen curve precision cannot certify the original complete-footprint tolerance')
    original = wanted['geometry']
    actual_outside = geometry.difference(original.buffer(margin))
    original_outside = original.difference(geometry.buffer(margin))
    covered = actual_outside.is_empty and original_outside.is_empty
    discrepancy = 0. if covered else spec['tolerance']+max(math.sqrt(actual_outside.area+original_outside.area),
        (actual_outside.length+original_outside.length)/2,1e-10)
    return {'geometry': geometry, 'error': error, 'passed': covered,
            'valid': True, 'value': discrepancy, 'threshold': spec['tolerance'],
            'unit': graph.rows[spec['frame']]['units'], 'coverage': 'complete_logical_domain',
            'owners': binding['owners'], 'precision_bound': error,
            'complete_mutual_coverage':covered,
            'value_definition':'zero if conservative mutual complete-domain coverage holds; otherwise a positive violation above tolerance'}


def scene_entries(scene, owners, native):
    """Bounded numeric surrogate uses the native coordinate compiler and parent map.

    It is never native or render evidence. The normal save/inspect gate follows.
    """
    from .geometry import path_operations
    from .boundary_geometry import _transform
    result = dict(native)
    scale = scene['canvas']['target_width_inches']*914400/scene['canvas']['width']
    for obj in scene['objects']:
        if obj['id'] not in owners:continue
        if obj['render_type'] not in ('path', 'shape', 'bezier') or obj.get('content', {}).get('native_snapshot'):
            raise ValueError('Spatial trials require compiled native geometry, not imported/effect owners')
        original = native[obj['id']]
        if original.get('error') or original.get('matrix') is None:
            raise ValueError('Actual trial parent mapping is unresolved')
        root = E.Element('{'+NS['p']+'}sp'); props = E.SubElement(root, '{'+NS['p']+'}spPr')
        xf = E.SubElement(props, '{'+NS['a']+'}xfrm', rot=str(round(obj.get('style', {}).get('rotation', 0)*60000)))
        x, y, w, h = obj['bbox']
        E.SubElement(xf, '{'+NS['a']+'}off', x=str(round(x*scale)), y=str(round(y*scale)))
        E.SubElement(xf, '{'+NS['a']+'}ext', cx=str(round(w*scale)), cy=str(round(h*scale)))
        if obj['render_type'] == 'shape':
            E.SubElement(props, '{'+NS['a']+'}prstGeom', prst=obj['content'].get('preset', 'rect'))
        else:
            geom = E.SubElement(props, '{'+NS['a']+'}custGeom')
            paths = E.SubElement(geom, '{'+NS['a']+'}pathLst')
            path = E.SubElement(paths, '{'+NS['a']+'}path', w='100000', h='100000')
            contours = obj['content'].get('contours', [])
            if not contours:raise ValueError('Spatial trials need compiled bounded path contours')
            for contour in contours:
                for name, points in path_operations(contour):
                    command = E.SubElement(path, '{'+NS['a']+'}'+name)
                    for u, v in points:E.SubElement(command, '{'+NS['a']+'}pt', x=str(round(u*100000)), y=str(round(v*100000)))
        result[obj['id']] = dict(original, node=root, tag='sp', matrix=original['parent_matrix'] @ _transform(xf))
    return result
