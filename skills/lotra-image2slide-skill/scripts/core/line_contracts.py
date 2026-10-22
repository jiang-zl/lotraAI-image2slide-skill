"""Source-owned line obligations; applicability is compiled, never caller PASS.

This policy is separate from product/source workflow versions. Older tasks keep
their bindings. Line descriptors contain original facts, never native owners.
"""
import copy
import math
from .common import identity

POLICY = 'evidence-checks-1.37.2'
SCHEMA = 'source-line-1.37.2'
ROLES = {'relationship', 'leader', 'dimension', 'axis', 'data_curve', 'boundary', 'decoration', 'internal_edge'}
MARKERS = {'none', 'arrow', 'triangle', 'stealth', 'diamond', 'oval', 'bar', 'custom'}
CONTACTS = {'free', 'boundary_touch', 'intentional_gap', 'inside_port', 'marker_center_on_boundary', 'circle_half_embedded'}
DASHES = {'solid', 'dot', 'dash', 'lgDash', 'dashDot', 'lgDashDot', 'lgDashDotDot',
          'sysDash', 'sysDot', 'sysDashDot', 'sysDashDotDot', 'custom'}
COMPOUNDS = {'single', 'double', 'thickThin', 'thinThick', 'triple'}
CRITERIA = ('route', 'terminals', 'markers', 'stroke', 'topology', 'visibility')


def enabled(state):
    return state.get('verification_policy') == POLICY


def number(value, where, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or positive and value <= 0:
        raise ValueError('LINE_SOURCE_REQUIRED: finite '+where)
    return float(value)


def point(value, where):
    if (not isinstance(value, list) or len(value) != 2 or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in value)):
        raise ValueError('LINE_SOURCE_REQUIRED: located '+where)
    return list(value)


def interval(value, where, *, positive=False):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('LINE_SOURCE_REQUIRED: frozen '+where+' interval')
    a, b = [number(v, where, positive=positive) for v in value]
    if a > b: raise ValueError('LINE_SOURCE_REQUIRED: ordered '+where+' interval')
    return [a, b]


def segment_ends(segment):
    if segment['kind'] == 'arc':
        c = segment['center']; rx, ry = segment['radii']
        points = [[c[0]+rx*math.cos(math.radians(a)), c[1]+ry*math.sin(math.radians(a))]
                  for a in (segment['start_degrees'], segment['start_degrees']+segment['sweep_degrees'])]
        if segment.get('transform'):
            m=segment['transform']; points=[[sum(m[i][j]*[*p,1][j] for j in range(3)) for i in (0,1)] for p in points]
        return points
    return [segment['points'][0], segment['points'][-1]]


def validate_line(line, feature, features):
    if not isinstance(line, dict) or line.get('schema') != SCHEMA or not line.get('source_evidence'):
        raise ValueError('LINE_SOURCE_REQUIRED: '+feature['id']+' needs an independent line descriptor')
    if any(k in line for k in ('owners', 'native_owner', 'candidate', 'preview_hash', 'representation', 'passed')):
        raise ValueError('LINE_SOURCE_REQUIRED: original lines precede native ownership')
    if line.get('role') not in ROLES or line.get('coordinate_space') != 'source_canvas':
        raise ValueError('LINE_SOURCE_REQUIRED: typed role and source_canvas coordinates')
    if line.get('direction') not in ('undirected', 'forward', 'reverse', 'both'):
        raise ValueError('LINE_SOURCE_REQUIRED: semantic direction separate from parameter order')
    path = line.get('path', {})
    if path.get('kind') not in ('straight', 'polyline', 'curve', 'closed', 'filled_arrow'):
        raise ValueError('LINE_SOURCE_REQUIRED: explicit route kind')
    segments = path.get('segments', [])
    if not segments or len(segments) > 1024:
        raise ValueError('LINE_SOURCE_REQUIRED: bounded complete source segments')
    previous = None
    for segment in segments:
        if 'transform' in segment:
            raise ValueError('LINE_SOURCE_REQUIRED: original routes are explicit source_canvas facts, not native transforms')
        kind = segment.get('kind')
        if kind == 'arc':
            point(segment.get('center'), 'arc center')
            radii = point(segment.get('radii'), 'arc radii')
            if min(radii) <= 0: raise ValueError('LINE_SOURCE_REQUIRED: positive arc radii')
            for key in ('start_degrees', 'sweep_degrees'):
                if type(segment.get(key)) not in (int, float) or not math.isfinite(segment[key]):
                    raise ValueError('LINE_SOURCE_REQUIRED: finite arc angle')
            if not 0 < abs(segment['sweep_degrees']) <= 360:
                raise ValueError('LINE_SOURCE_REQUIRED: bounded nonzero source arc')
        else:
            count = {'line':2, 'quadratic':3, 'cubic':4}.get(kind)
            if not count or len(segment.get('points', [])) != count:
                raise ValueError('LINE_SOURCE_REQUIRED: typed original line/Bezier controls')
            for p in segment['points']: point(p, 'path control')
        first, last = segment_ends(segment)
        if previous is not None and math.dist(previous, first) > 1e-5:
            raise ValueError('LINE_SOURCE_REQUIRED: ordered contiguous path, not an unordered point set')
        previous = last
    first, last = segment_ends(segments[0])[0], segment_ends(segments[-1])[-1]
    closed = path['kind'] == 'closed'
    if closed and math.dist(first, last) > 1e-5:
        raise ValueError('LINE_SOURCE_REQUIRED: explicitly closed route')
    if path['kind'] == 'straight' and (len(segments) != 1 or segments[0]['kind'] != 'line'):
        raise ValueError('LINE_SOURCE_REQUIRED: straight route is one source segment')
    if path['kind'] == 'polyline' and any(s['kind'] != 'line' for s in segments):
        raise ValueError('LINE_SOURCE_REQUIRED: polyline segments are straight')
    if path['kind'] == 'filled_arrow':
        contour=path.get('outline', [])
        if not 3<=len(contour)<=1024:
            raise ValueError('LINE_SOURCE_REQUIRED: filled arrows need their original body/head outline')
        for p in contour:point(p,'filled arrow outline')
    ends = line.get('ends', [])
    if len(ends) != (0 if closed else 2):
        raise ValueError('LINE_SOURCE_REQUIRED: both terminals, or no fictitious ends on a closed route')
    for index, end in enumerate(ends):
        p = point(end.get('point'), 'terminal')
        if math.dist(p, (first, last)[index]) > 1e-5:
            raise ValueError('LINE_SOURCE_REQUIRED: terminals retain the ordered source path ends')
        marker = end.get('marker', {})
        if marker.get('type') not in MARKERS or type(marker.get('filled')) is not bool:
            raise ValueError('LINE_SOURCE_REQUIRED: both original marker types/fills, including confirmed none')
        if marker.get('anchor_role') not in ('path_endpoint', 'tip', 'center'):
            raise ValueError('LINE_SOURCE_REQUIRED: distinguish path endpoint, marker tip and center')
        point(marker.get('anchor'), 'original marker anchor')
        interval(marker.get('width'), 'marker width')
        interval(marker.get('length'), 'marker length')
        if marker['type']!='none' and min(marker['width'][1],marker['length'][1])<=0:
            raise ValueError('LINE_SOURCE_REQUIRED: a visible marker has positive original dimensions')
        if marker['type'] == 'none' and (marker['width'] != [0, 0] or marker['length'] != [0, 0]):
            raise ValueError('LINE_SOURCE_REQUIRED: confirmed no marker has zero marker dimensions')
        if marker['type'] in ('bar', 'custom'):
            polygon = marker.get('contour', [])
            if len(polygon) < 2 or len(polygon) > 128:
                raise ValueError('LINE_SOURCE_REQUIRED: custom marker has a bounded original contour')
            for p in polygon: point(p, 'custom marker contour')
        attachment = end.get('attachment', {})
        if attachment.get('kind') not in CONTACTS or not attachment.get('source_evidence'):
            raise ValueError('LINE_SOURCE_REQUIRED: physical terminal association')
        if attachment['kind'] == 'free':
            if not attachment.get('reason') or line['role'] == 'relationship':
                raise ValueError('LINE_SOURCE_REQUIRED: a relationship cannot use unexplained free terminals')
        elif attachment.get('feature') not in features:
            raise ValueError('LINE_SOURCE_REQUIRED: terminal refers to an original target feature')
        interval(attachment.get('distance'), 'terminal contact distance')
    stroke = line.get('stroke', {})
    interval(stroke.get('width'), 'stroke width', positive=True)
    interval(stroke.get('opacity'), 'stroke opacity')
    if stroke['opacity'][1] > 1: raise ValueError('LINE_SOURCE_REQUIRED: normalized opacity')
    colour = stroke.get('colour')
    if not isinstance(colour, str) or len(colour) != 6 or any(v not in '0123456789abcdefABCDEF' for v in colour):
        raise ValueError('LINE_SOURCE_REQUIRED: original stroke RGB')
    paint=stroke.get('paint_colour',colour)
    if not isinstance(paint,str) or len(paint)!=6 or any(v not in '0123456789abcdefABCDEF' for v in paint):
        raise ValueError('LINE_SOURCE_REQUIRED: observed painted RGB')
    if stroke['opacity'][0]<1 and 'paint_colour' not in stroke:
        raise ValueError('LINE_SOURCE_REQUIRED: translucent strokes need independently observed paint_colour')
    if stroke.get('cap') not in ('flat', 'round', 'square') or stroke.get('join') not in ('round', 'bevel', 'miter'):
        raise ValueError('LINE_SOURCE_REQUIRED: explicit cap/join')
    if stroke.get('compound') not in COMPOUNDS or stroke.get('dash', {}).get('kind') not in DASHES:
        raise ValueError('LINE_SOURCE_REQUIRED: explicit compound/dash family')
    if stroke['dash']['kind'] != 'solid':
        pattern = stroke['dash'].get('pattern', [])
        if len(pattern) < 2 or len(pattern) > 32 or len(pattern) % 2:
            raise ValueError('LINE_SOURCE_REQUIRED: original on/off stroke pattern')
        for value in pattern: interval(value, 'dash/gap length', positive=True)
    limits = line.get('limits', {})
    for key in ('route', 'endpoint', 'marker', 'colour', 'width', 'angle_degrees'):
        number(limits.get(key), key+' tolerance', positive=key != 'angle_degrees')
    if limits['angle_degrees'] > 45 or limits['colour'] > 1:
        raise ValueError('LINE_SOURCE_REQUIRED: bounded angle/normalized colour uncertainty')
    if not limits.get('source_evidence'):
        raise ValueError('LINE_SOURCE_REQUIRED: uncertainty comes from the original, not a failed candidate')
    topology = line.get('topology')
    visibility = line.get('visibility')
    if not isinstance(topology, dict) or set(topology) != {'junctions', 'crossings', 'shared'}:
        raise ValueError('LINE_SOURCE_REQUIRED: complete junction/crossing/shared decisions')
    for kind in ('junctions', 'crossings', 'shared'):
        records = topology[kind]
        if not isinstance(records, list) or len(records) > 2048 or len({r.get('id') for r in records}) != len(records):
            raise ValueError('LINE_SOURCE_REQUIRED: distinct bounded topology identities')
        for record in records:
            if not record.get('id') or not record.get('source_evidence'):
                raise ValueError('LINE_SOURCE_REQUIRED: located topology evidence')
            point(record.get('point'), 'topology landmark')
            peers = record.get('features', [])
            if not peers or feature['id'] not in peers or not set(peers) <= set(features):
                raise ValueError('LINE_SOURCE_REQUIRED: exact source feature incidence')
            if kind == 'crossings' and record.get('kind') not in ('crossing', 'bridge', 'occlusion'):
                raise ValueError('LINE_SOURCE_REQUIRED: crossing is not automatically a junction')
    if not isinstance(visibility, dict) or set(visibility) != {'hidden'}:
        raise ValueError('LINE_SOURCE_REQUIRED: explicit visible/hidden path coverage')
    for hidden in visibility['hidden']:
        if (type(hidden.get('segment')) is not int or not 0 <= hidden['segment'] < len(segments) or
                hidden.get('occluder') not in features or not hidden.get('source_evidence')):
            raise ValueError('LINE_SOURCE_REQUIRED: source-owned occlusion interval')
        bounds = interval(hidden.get('range'), 'hidden parameter')
        if bounds[1] > 1 or bounds[0] == bounds[1]:
            raise ValueError('LINE_SOURCE_REQUIRED: nonempty hidden parameter interval')
    return line


def validate_source(observed, state):
    if not enabled(state): return
    features = {f['id']:f for f in observed['features']}
    for feature in features.values():
        if feature.get('kind') in ('internal_line', 'curve') and not feature.get('line'):
            raise ValueError('LINE_SOURCE_REQUIRED: '+feature['id']+' needs route/ends/style/topology before ownership')
        if feature.get('line'):
            if feature.get('required', True) is not True:
                raise ValueError('LINE_SOURCE_REQUIRED: visible line structure cannot be optional')
            validate_line(feature['line'], feature, features)


def is_line_node(node):
    kind = node.get('render_type'); content = node.get('content', {})
    if kind == 'connector': return True
    if kind == 'bezier': return not content.get('closed',False)
    if kind == 'path':
        contours = content.get('contours')
        return bool(contours and any(not c.get('closed', False) for c in contours))
    preset = content.get('preset', '')
    return (kind == 'shape' and (preset in ('line', 'lineInv') or 'arrow' in preset.lower() or
            node.get('semantic_type') in ('connector', 'line', 'arrow')))


def compile_contract(state, observed, contract, scene):
    if not enabled(state): return
    validate_source(observed, state)
    if contract.get('verification_policy', POLICY) != POLICY:
        raise ValueError('LINE_POLICY_REQUIRED: caller cannot lower the task evidence policy')
    contract['verification_policy'] = POLICY
    features = {f['id']:f for f in observed['features']}
    nodes = {n['id']:n for n in scene['objects']}
    lines = []; covered = set()
    for binding in contract['feature_bindings']:
        feature = features[binding['feature']]
        if not feature.get('line'): continue
        owners = binding['owners']; parts = binding.get('line_parts')
        if parts is None:
            if not owners or any(not is_line_node(nodes[name]) for name in owners):
                raise ValueError('LINE_BINDING_REQUIRED: composite shafts/markers need explicit line_parts')
            parts = [{'owner':name, 'role':'shaft'} for name in owners]
        if (len(parts) != len(owners) or len({p.get('owner') for p in parts}) != len(parts) or
                {p.get('owner') for p in parts} != set(owners) or
                any(p.get('role') not in ('shaft', 'start_marker', 'end_marker') for p in parts) or
                any(sum(p.get('role')==role for p in parts)>1 for role in ('start_marker','end_marker')) or
                not any(p['role'] == 'shaft' for p in parts)):
            raise ValueError('LINE_BINDING_REQUIRED: exact native shaft/marker coverage')
        for part in parts:
            node = nodes[part['owner']]
            if part['role'] == 'shaft' and not is_line_node(node):
                # A closed/filled native path can be a source-declared filled arrow.
                if feature['line']['path']['kind'] not in ('closed', 'filled_arrow') or node['render_type'] not in ('path', 'shape'):
                    raise ValueError('LINE_BINDING_REQUIRED: actual native shaft geometry')
            if node['render_type'] in ('photo', 'svg', 'trace', 'unresolved', 'text', 'equation', 'table', 'group'):
                raise ValueError('LINE_BINDING_REQUIRED: explicit editable native leaves, never flattened evidence')
        if feature['line']['path']['kind']=='closed' and any(p['role']!='shaft' for p in parts):
            raise ValueError('LINE_BINDING_REQUIRED: a closed route has no terminal marker owners')
        covered.update(owners)
        obligations = list(CRITERIA)
        lines.append({'id':feature['id'], 'unit':feature['unit'], 'roi':feature['roi'],
            'source':copy.deepcopy(feature['line']), 'parts':copy.deepcopy(parts),
            'terminal_sites':copy.deepcopy(binding.get('terminal_sites', {})),
            'component':binding['component'], 'criteria':obligations})
    native_lines = {n['id'] for n in scene['objects'] if is_line_node(n)}
    if native_lines-covered:
        raise ValueError('LINE_BINDING_REQUIRED: native strokes have no source line: '+','.join(sorted(native_lines-covered)[:12]))
    spec = {'policy':POLICY, 'source_hash':state['source']['sha256'], 'lines':lines,
            'native_line_owners':sorted(native_lines), 'source_line_ids':sorted(l['id'] for l in lines),
            'scope':'source feature lines plus all standalone editable native strokes; shape outlines retain contour gates'}
    spec['basis'] = identity(spec)
    contract['line_verification'] = spec


def require_contract(state, contract):
    if not enabled(state): return None
    spec = contract.get('line_verification', {})
    if (contract.get('verification_policy') != POLICY or spec.get('policy') != POLICY or
            spec.get('source_hash') != state['source']['sha256'] or
            spec.get('basis') != identity({k:v for k,v in spec.items() if k != 'basis'}) or
            spec.get('source_line_ids') != sorted(l['id'] for l in spec.get('lines', [])) or
            any(row.get('criteria') != list(CRITERIA) for row in spec.get('lines', []))):
        raise ValueError('LINE_POLICY_REQUIRED: complete current compiled line obligations')
    return spec


def require_report(state,candidate,contract,report):
    """Delivery validates complete compiled obligations, not a top-level PASS."""
    spec=require_contract(state,contract)
    if (report.get('policy')!=POLICY or report.get('basis')!=spec['basis'] or report.get('passed') is not True or
            report.get('source_hash')!=state['source']['sha256'] or report.get('pptx_hash')!=candidate['pptx']['sha256'] or
            report.get('preview_hash')!=candidate['preview']['sha256'] or report.get('render_checked') is not True or
            set(report.get('lines',{}))!=set(spec['source_line_ids']) or report.get('census',{}).get('passed') is not True):
        raise ValueError('LINE_REPORT_REQUIRED: current complete native/render line evidence')
    for name,row in report['lines'].items():
        if row.get('passed') is not True or row.get('valid') is not True or set(row.get('checks',{}))!=set(CRITERIA):
            raise ValueError('LINE_REPORT_REQUIRED: complete per-line criteria '+name)
        if any(check.get('valid') is not True or check.get('passed') is not True for check in row['checks'].values()):
            raise ValueError('LINE_REPORT_REQUIRED: invalid or failed criterion '+name)
    return report
