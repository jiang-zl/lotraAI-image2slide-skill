"""Source-owned coordinate frames and observable spatial contracts.

Only this module converts local geometry to source pixels. A 2D observation
does not establish hidden 3D truth. No candidate-derived registration is used.
"""
import copy
import math
import numpy as np
from .common import identity

VERSION = 'spatial-1.35.0'
MODES = {'planar', 'surface', 'solid', 'mixed', 'uncertain'}
RELATIONS = {'center_in_plane', 'align_in_plane', 'contained_on_plane',
             'supported_by', 'attached_to_face', 'same_plane', 'axis_direction',
             'extent_ratio', 'pose_projection', 'shared_edge', 'occludes', 'volume_contains'}
PHASE = {'pose_projection': 1, 'axis_direction': 1, 'extent_ratio': 1,
         'supported_by': 2, 'attached_to_face': 2, 'center_in_plane': 2,
         'align_in_plane': 2, 'contained_on_plane': 2, 'same_plane': 2,
         'volume_contains': 2, 'shared_edge': 3, 'occludes': 4}


def enabled(contract):
    return contract.get('workflow_version') == '1.35.0'


def array(value, shape):
    raw = np.asarray(value)
    if raw.dtype.kind not in ('i', 'u', 'f'):
        raise ValueError('Spatial coordinates must be numeric, not strings or booleans')
    result = np.asarray(value, dtype=float)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError('Finite spatial coordinates with declared dimensions required')
    return result


def hom(matrix, point):
    result = matrix @ np.r_[point, 1.]
    if not np.isfinite(result).all() or abs(result[-1]) < 1e-10:
        raise ValueError('SPATIAL_MEASUREMENT_INVALID: point projects at infinity')
    return result[:-1] / result[-1]


def plane_from_corners(local, parent):
    """Derive a plane from four original correspondences, never candidate pixels."""
    local, parent = array(local, (4, 2)), array(parent, (4, 2))
    rows, target = [], []
    for (u, v), (x, y) in zip(local, parent):
        rows.extend(([u,v,1,0,0,0,-x*u,-x*v], [0,0,0,u,v,1,-y*u,-y*v]))
        target.extend((x, y))
    matrix = np.asarray(rows)
    if np.linalg.matrix_rank(matrix) != 8:
        raise ValueError('SPATIAL_SOURCE_DECISION_REQUIRED: degenerate original plane corners')
    return np.r_[np.linalg.solve(matrix, target), 1.].reshape(3, 3)


def rotation_matrix(row):
    if 'euler_degrees' not in row:
        return array(row['rotation'], (3, 3))
    if 'rotation' in row or row.get('rotation_order') != 'extrinsic_XYZ':
        raise ValueError('Use one rotation representation; Euler axes require explicit extrinsic_XYZ order')
    x, y, z = np.radians(array(row['euler_degrees'], (3,)))
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    rx = np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
    ry = np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])
    rz = np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])
    return rz @ ry @ rx


class Frames:
    """Acyclic canvas/plane/rigid-space graph; plane inverse is planar only."""
    def __init__(self, rows):
        if not rows or len(rows) > 2048 or len({r.get('id') for r in rows}) != len(rows):
            raise ValueError('Distinct bounded spatial frame IDs required')
        self.rows = {r['id']: r for r in rows}
        self.cache = {}
        for name in self.rows:
            self.matrix(name)
        if sum(r['kind'] == 'canvas' for r in rows) != 1:
            raise ValueError('Exactly one unchanged-source canvas frame required')

    def matrix(self, name, seen=None):
        if name in self.cache:
            return self.cache[name]
        if name not in self.rows or name in (seen or set()):
            raise ValueError('Missing/cyclic spatial reference frame')
        row = self.rows[name]
        if not row.get('source_evidence') or not row.get('units'):
            raise ValueError('Each spatial frame needs original evidence and units')
        kind = row.get('kind')
        if kind == 'canvas':
            if row.get('parent') or row['units'] != 'source_px':
                raise ValueError('Canvas is unchanged original pixel coordinates')
            result = np.eye(3)
        else:
            parent = self.rows.get(row.get('parent'))
            if parent is None:
                raise ValueError('Explicit parent frame required')
            base = self.matrix(parent['id'], (seen or set()) | {name})
            if kind == 'space3d':
                rotation = rotation_matrix(row)
                if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-7) or not math.isclose(float(np.linalg.det(rotation)), 1., abs_tol=1e-7):
                    raise ValueError('Right-handed orthonormal rotation matrix required')
                rigid = np.eye(4)
                rigid[:3, :3] = rotation
                rigid[:3, 3] = array(row['translation'], (3,))
                if parent['kind'] == 'space3d':
                    if 'projection' in row:
                        raise ValueError('Child rigid pose inherits its parent projection')
                    result = base @ rigid
                elif parent['kind'] == 'canvas':
                    if row.get('projection_type') not in ('orthographic', 'axonometric', 'perspective', 'stylized'):
                        raise ValueError('Source-supported spatial projection type required')
                    projection = array(row['projection'], (3, 4))
                    if np.linalg.matrix_rank(projection) != 3:
                        raise ValueError('Nondegenerate spatial projection required')
                    result = projection @ rigid
                else:
                    raise ValueError('A 3D space cannot inherit a 2D plane camera')
            elif kind == 'plane':
                if parent['kind'] == 'space3d':
                    origin, u, v = (array(row[k], (3,)) for k in ('origin', 'u', 'v'))
                    if np.linalg.norm(np.cross(u, v)) < 1e-10:
                        raise ValueError('Independent spatial plane axes required')
                    embedding = np.zeros((4, 3))
                    embedding[:3, :] = np.column_stack((u, v, origin))
                    embedding[3, 2] = 1.
                    result = base @ embedding
                else:
                    if 'local_corners' in row or 'parent_corners' in row:
                        if any(k in row for k in ('homography','origin','u','v')):
                            raise ValueError('Choose one source plane representation')
                        local = plane_from_corners(row['local_corners'], row['parent_corners'])
                    elif 'homography' in row:
                        local = array(row['homography'], (3, 3))
                    else:
                        local = np.eye(3)
                        local[:2, :] = np.column_stack([array(row[k], (2,)) for k in ('u', 'v', 'origin')])
                    result = base @ local
                if abs(float(np.linalg.det(result))) < 1e-12:
                    raise ValueError('SPATIAL_SOURCE_DECISION_REQUIRED: edge-on/singular plane')
            else:
                raise ValueError('Unknown spatial frame kind')
        self.cache[name] = result
        return result

    def dimension(self, name):
        return 3 if self.rows[name]['kind'] == 'space3d' else 2

    def project(self, name, point):
        return hom(self.matrix(name), array(point, (self.dimension(name),))).tolist()

    def inverse_plane(self, name, point):
        if self.dimension(name) != 2:
            raise ValueError('A single projected point has no unique 3D inverse')
        return hom(np.linalg.inv(self.matrix(name)), array(point, (2,))).tolist()

    def ancestors(self, name):
        result = []
        while name:
            result.append(copy.deepcopy(self.rows[name]))
            name = self.rows[name].get('parent')
        return result


def validate_observation(observed):
    """Spatial recognition and targets are frozen before native ownership."""
    value = observed.get('spatial', {})
    if value.get('schema') != VERSION:
        raise ValueError('SPATIAL_SOURCE_DECISION_REQUIRED: hierarchical spatial observation')
    frames = Frames(value.get('frames', []))
    units = {u['id']: u for u in observed['units']}
    landmarks = value.get('landmarks', [])
    if len(landmarks) > 50000 or len({p.get('id') for p in landmarks}) != len(landmarks):
        raise ValueError('Distinct bounded source landmarks required')
    points = {p['id']: p for p in landmarks}
    for unit in units.values():
        spatial = unit.get('spatial', {})
        if (spatial.get('mode') not in MODES or spatial.get('frame') not in frames.rows or
                not spatial.get('source_evidence') or type(spatial.get('container')) is not bool or
                spatial.get('placement') not in ('standing', 'attached', 'free', 'annotation', 'unknown') or
                spatial.get('observability') not in ('clear', 'partial', 'unresolved')):
            raise ValueError('Every original unit needs spatial mode, frame, placement and container recognition')
        if spatial.get('mode') == 'uncertain' and not spatial.get('uncertainty'):
            raise ValueError('Uncertain spatial interpretation needs located uncertainty')
        if spatial.get('unobservable_axes') and not spatial.get('symmetry_evidence'):
            raise ValueError('Unobservable rotations require source-supported symmetry/ambiguity')
    for point in landmarks:
        if (point.get('unit') not in units or point.get('frame') not in frames.rows or
                not point.get('source_evidence') or not point.get('role') or
                point.get('observability') not in ('clear', 'partial') or
                type(point.get('tolerance_source_px')) not in (int, float) or point['tolerance_source_px'] < 0):
            raise ValueError('Located observable landmark with frozen source-pixel bound required')
        projected = np.asarray(frames.project(point['frame'], point['point']))
        original = array(point['source_point'], (2,))
        if np.linalg.norm(projected-original) > point['tolerance_source_px']:
            raise ValueError('SPATIAL_FRAME_DECISION_REQUIRED: declared projection disagrees with independently observed original landmark')
    relations = value.get('relations', [])
    if len(relations) > 20000 or len({r.get('id') for r in relations}) != len(relations):
        raise ValueError('Distinct bounded source spatial relations required')
    for row in relations:
        names = row.get('landmarks', [])
        if (row.get('kind') not in RELATIONS or not row.get('source_evidence') or
                not row.get('units') or not set(row['units']) <= set(units) or
                not names or len(names) != len(set(names)) or not set(names) <= set(points) or
                not {points[p]['unit'] for p in names} <= set(row['units']) or
                row.get('frame') not in frames.rows or type(row.get('tolerance')) not in (int, float) or row['tolerance'] < 0):
            raise ValueError('Located typed spatial relation with frozen bound and complete source landmarks required')
        kind = row['kind']
        domain = 'degree' if kind in ('axis_direction', 'pose_projection') else 'ratio' if kind == 'extent_ratio' else 'source_px' if kind in ('shared_edge', 'occludes') else frames.rows[row['frame']]['units']
        if row.get('unit') != domain:
            raise ValueError('Spatial relation tolerance unit conflicts with measurement coordinates')
        if kind in ('axis_direction', 'occludes') and len(names) != 2 or kind in ('extent_ratio', 'shared_edge') and len(names) != 4:
            raise ValueError('Spatial relation landmark arity differs')
        if kind == 'pose_projection' and len(names) < 3:
            raise ValueError('Pose needs at least three observable landmarks')
        if kind in ('center_in_plane', 'align_in_plane', 'contained_on_plane', 'supported_by', 'attached_to_face', 'same_plane') and frames.dimension(row['frame']) != 2:
            raise ValueError('Face-local relation requires an invertible plane, not a 3D inverse')
        if kind == 'center_in_plane':
            array(row['target'], (2,))
            if not row.get('aggregate_basis') == 'logical_footprint':
                raise ValueError('Center the direct-content logical footprint, excluding shadow and protruding body')
            content = set(row.get('content_units', []))
            if not content or not content <= set(row['units']):
                raise ValueError('Centering content units must belong to the measured relation')
        if kind == 'align_in_plane' and row.get('axis') not in (0, 1):
            raise ValueError('Explicit plane-local alignment axis required')
        if kind == 'axis_direction' and type(row.get('directed', True)) is not bool:
            raise ValueError('Explicit boolean orientation sense required')
        if kind == 'axis_direction' and row.get('directed') is False and not row.get('symmetry_evidence'):
            raise ValueError('An undirected axis needs original symmetry evidence')
        if kind in ('contained_on_plane', 'supported_by', 'attached_to_face'):
            region = np.asarray(row.get('region'), float)
            if region.ndim != 2 or region.shape[1] != 2 or not 3 <= len(region) <= 128 or not np.isfinite(region).all():
                raise ValueError('Finite explicit usable-face region required')
        if kind == 'volume_contains':
            if frames.dimension(row['frame']) != 3 or row.get('claim') != 'visible_projection_only':
                raise ValueError('Single-image volume checks must declare their visible-projection scope')
            array(row['bounds'], (2, 3))
    for unit in units.values():
        spatial = unit['spatial']
        own = [r for r in relations if unit['id'] in r['units']]
        if spatial['mode'] in ('surface', 'solid') and not any(r['kind'] in ('pose_projection', 'axis_direction') for r in own):
            raise ValueError('Every spatial surface/solid needs observable orientation constraints')
        required = 'supported_by' if spatial['placement'] == 'standing' else 'attached_to_face' if spatial['placement'] == 'attached' else None
        if required and not any(r['kind'] == required for r in own):
            raise ValueError('Standing/attached content needs a typed source support relation')
        children = {u['id'] for u in units.values() if u.get('parent') == unit['id']}
        if children and spatial['container']:
            centers = [r for r in own if r['kind'] == 'center_in_plane' and r.get('container') == unit['id']]
            if len(centers) != 1 or set(centers[0].get('content_units', [])) != children:
                raise ValueError('Each semantic container needs one two-axis aggregate-centering target covering all direct children')
            represented = {points[p]['unit'] for p in centers[0]['landmarks']}
            if not children <= represented or not centers[0].get('target_evidence'):
                raise ValueError('Every direct child contributes its logical footprint; freeze centered or source-offset target')
    return value


def bind(contract, observed, scene):
    if not enabled(contract):
        return
    value = validate_observation(observed)
    points = {p['id']: p for p in value['landmarks']}
    bindings = contract.get('spatial_bindings', [])
    if len(bindings) != len({b.get('landmark') for b in bindings}) or {b.get('landmark') for b in bindings} != set(points):
        raise ValueError('Every observable spatial landmark needs one saved-native anchor binding')
    nodes = {n['id']: n for n in scene['objects']}
    feature_units = {f['id']: f['unit'] for f in observed['features']}
    unit_owners = {}
    for binding in contract['feature_bindings']:
        unit_owners.setdefault(feature_units[binding['feature']], set()).update(binding['owners'])
    for binding in bindings:
        owner = binding.get('owner')
        anchor = binding.get('anchor', {})
        if owner not in unit_owners.get(points[binding['landmark']]['unit'], set()) or nodes[owner]['render_type'] == 'group':
            raise ValueError('Spatial anchor must bind an actual leaf corresponding to its original unit')
        if anchor.get('kind') == 'frame_point':
            p = array(anchor['point'], (2,))
            if np.any(p < 0) or np.any(p > 1):
                raise ValueError('Frame anchors are normalized saved-local points, never source pixels')
        elif anchor.get('kind') == 'path_point':
            if any(type(anchor.get(k)) is not int or anchor[k] < 0 for k in ('path', 'command', 'point')):
                raise ValueError('Saved path anchors need explicit path/command/control-point indices')
        else:
            raise ValueError('Use an actual saved-local frame or native-path anchor')
        if not binding.get('source_evidence'):
            raise ValueError('Explain the semantic/native anchor correspondence')
    contract['spatial'] = copy.deepcopy(value)
    contract['spatial_units'] = {u['id']: copy.deepcopy(u['spatial']) for u in observed['units']}
    contract['spatial_basis'] = identity({'spatial': value, 'bindings': bindings,
        'units': {u['id']: u['spatial'] for u in observed['units']}})
    frames = Frames(value['frames'])
    for row in contract['components']:
        units = {feature_units[b['feature']] for b in row.get('feature_bindings', [])}
        selected = [p for p in value['landmarks'] if p['unit'] in units]
        used = {p['frame'] for p in selected} | {u['spatial']['frame'] for u in observed['units'] if u['id'] in units}
        relations = [r for r in value['relations'] if set(r['units']) & units]
        used.update(r['frame'] for r in relations)
        dependencies = {f['id']: f for name in used for f in frames.ancestors(name)}
        row['spatial_context'] = {'units': sorted(units), 'frames': dependencies,
            'landmarks': selected, 'relations': relations,
            'classifications': {u['id']: u['spatial'] for u in observed['units'] if u['id'] in units},
            'bindings': [b for b in bindings if b['landmark'] in {p['id'] for p in selected}]}
        row['spatial_basis'] = identity(row['spatial_context'])


def prepare_binding(task, state, contract):
    if not enabled(contract):
        return
    from .common import read_json
    from .component_workflow import _resource
    ref = state.get('source_feature_observation')
    if not ref:
        raise ValueError('SPATIAL_SOURCE_DECISION_REQUIRED: observe frames before native construction')
    observed = read_json(_resource(task, ref))
    if observed.get('schema') != 'source-features-1.35.0':
        raise ValueError('Explicitly migrate the original observation to v1.35 spatial semantics')
    contract['spatial'] = copy.deepcopy(validate_observation(observed))


def source_check(row):
    context = row.get('spatial_context')
    if context is None:
        return {'passed': True, 'applicable': False}
    unresolved = [k for k, v in context['classifications'].items() if v['observability'] == 'unresolved' or v['mode'] == 'uncertain']
    return {'passed': not unresolved, 'unresolved_units': unresolved,
            'status': 'SPATIAL_SOURCE_DECISION_REQUIRED' if unresolved else 'SPATIAL_SOURCE_BOUND',
            'spatial_basis': row['spatial_basis'], 'hidden_3d_verified': False}


def review(contract, evidence, row=None):
    if not enabled(contract):
        return {'passed': True, 'applicable': False}
    context = row.get('spatial_context', {}) if row else None
    units = set(context['units']) if row else set(contract['spatial_units'])
    relations = {r['id'] for r in contract['spatial']['relations'] if set(r['units']) <= units}
    value = evidence.get('spatial_review', {})
    basis = row['spatial_basis'] if row else contract['spatial_basis']
    checks = value.get('unit_checks', [])
    links = value.get('relation_checks', [])
    by_unit = {r.get('unit'): r for r in checks}
    by_relation = {r.get('relation'): r for r in links}
    failed_units = [k for k in units if by_unit.get(k, {}).get('verdict') != 'PASS' or not by_unit.get(k, {}).get('observations')]
    failed_relations = [k for k in relations if by_relation.get(k, {}).get('verdict') != 'PASS' or not by_relation.get(k, {}).get('observations')]
    passed = (value.get('spatial_basis') == basis and value.get('basis') == 'original_to_saved_render' and
        evidence.get('observer') in ('host_model', 'human') and len(checks) == len(by_unit) and len(links) == len(by_relation) and
        not failed_units and not failed_relations)
    return {'passed': bool(passed), 'failed_units': sorted(failed_units), 'failed_relations': sorted(failed_relations),
            'spatial_basis': basis, 'claim': 'observable_projection_fidelity', 'hidden_3d_verified': False}


def packet(contract=None, row=None):
    return {'schema': VERSION, 'reference': 'references/workflow-v135.md',
        'spatial_basis': (row or contract or {}).get('spatial_basis'),
        'recognition': 'Classify every source unit; shared parent frames do not force identical child orientation.',
        'alignment': 'Canvas, face-local content aggregate, and standing-object contact footprint are distinct anchors.',
        'pose': 'Use observable projected axes/faces and symmetry; unknown hidden 3D is not a measured PASS.',
        'review': 'Bind spatial_review to current source/native/render and every unit/relation; invalid probes precede drawing repair.',
        'repair_order': ['frame/projection', 'local_pose', 'support/face_alignment', 'shared_geometry', 'occlusion', 'material/text'],
        'context': {'units':(row or {}).get('spatial_context',{}).get('units',[]),
                    'frames':sorted((row or {}).get('spatial_context',{}).get('frames',{})),
                    'relation_ids':[r['id'] for r in (row or {}).get('spatial_context',{}).get('relations',[])]}}


def correction_guard(before, after, request):
    """Frame/pose/target changes cannot silently loosen a failed measurement."""
    def inventory(value):
        result = {'unit:'+u['id']: u.get('spatial') for u in value['units']}
        for kind in ('frames', 'landmarks', 'relations'):
            result.update({kind+':'+r['id']: r for r in value.get('spatial', {}).get(kind, [])})
        return result
    old, new = inventory(before), inventory(after)
    changed = {k for k in set(old) | set(new) if old.get(k) != new.get(k)}
    if not changed:
        return
    corrections = {r.get('resource'): r for r in request.get('spatial_corrections', [])}
    if any(not corrections.get(k, {}).get('source_evidence') or not corrections[k].get('reason') for k in changed):
        raise ValueError('Each changed spatial frame/unit/landmark/relation needs a retained original-domain correction')
