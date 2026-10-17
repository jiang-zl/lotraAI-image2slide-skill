"""Fresh saved-native spatial measurements, separate from source/render truth."""
import math
import numpy as np
from .common import digest, safe_path
from .spatial_frames import frames, enabled, strict, PHASE


def _anchor(entry, binding):
    from .mathml import NS
    if entry.get('error') or entry.get('matrix') is None or entry['tag'] == 'grpSp':
        raise ValueError(entry.get('error') or 'Actual saved leaf transform required')
    props = entry['node'].find('p:spPr', NS)
    if props is not None and any(props.find('a:'+k, NS) is not None for k in ('scene3d', 'sp3d')):
        raise ValueError('Native 3D effects require a qualified geometry extractor; use editable projected surfaces')
    spec = binding['anchor']
    if spec['kind'] == 'frame_point':
        local = spec['point']
    else:
        paths = entry['node'].findall('p:spPr/a:custGeom/a:pathLst/a:path', NS)
        path = paths[spec['path']]
        command = list(path)[spec['command']]
        point = command.findall('a:pt', NS)[spec['point']]
        width, height = float(path.get('w', 0)), float(path.get('h', 0))
        if min(width, height) <= 0:
            raise ValueError('Positive saved path coordinate extents required')
        local = [float(point.get('x'))/width, float(point.get('y'))/height]
    actual = entry['matrix'] @ np.array([*local, 1.])
    if not np.isfinite(actual).all() or abs(actual[2]) < 1e-10:
        raise ValueError('Invalid actual native anchor')
    return actual[:2] / actual[2]


def _angle(a, b, directed=True):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if min(na, nb) < 1e-10:
        raise ValueError('Degenerate observable direction')
    cosine = float(np.dot(a, b)/(na*nb))
    if not directed:
        cosine = abs(cosine)
    return math.degrees(math.acos(max(-1., min(1., cosine))))


def _region_distance(points, polygon):
    from shapely.geometry import Point, Polygon
    region = Polygon(polygon)
    if not region.is_valid or region.is_empty or region.area <= 0:
        raise ValueError('Valid simple usable-face region required')
    return max(float(region.distance(Point(p))) for p in points)


def evaluate(task, state, candidate, contract, row=None, *, scene_override=None, override_owners=()):
    """Never substitutes expected source points for missing native anchors.

    Every observable landmark is independently compared in unchanged source
    pixels. Plane relations additionally use inverse face coordinates. Latent
    rotations/volumes remain plan consistency, not recovered hidden 3D proof.
    """
    if not enabled(contract):
        return {'passed': True, 'applicable': False, 'legacy_policy_retained': True}
    from .boundary_geometry import saved_nodes
    file = safe_path(task, candidate['pptx']['path'])
    if digest(file) != candidate['pptx']['sha256']:
        raise ValueError('Spatial measurement belongs to changed native bytes')
    graph = frames(contract['spatial'])
    all_points = {p['id']: p for p in contract['spatial']['landmarks']}
    units = set(row['spatial_context']['units']) if row else set(contract['spatial_units'])
    points = {k: p for k, p in all_points.items() if p['unit'] in units}
    bindings = {b['landmark']: b for b in contract['spatial_bindings']}
    native = saved_nodes(file, state['source_size'])
    if scene_override is not None:
        from .spatial_footprints import scene_entries
        native = scene_entries(scene_override, set(override_owners), native)
    actual, expected, anchors, results = {}, {}, {}, {}
    for name, point in points.items():
        try:
            binding = bindings[name]
            measured = _anchor(native[binding['owner']], binding)
            wanted = np.asarray(point['source_point'],float)
            error = float(np.linalg.norm(measured-wanted))
            actual[name], expected[name] = measured, wanted
            anchors[name] = {'passed': error <= point['tolerance_source_px'], 'valid': True,
                'value': error, 'unit': 'source_px', 'threshold': point['tolerance_source_px'],
                'actual': measured.tolist(), 'expected': wanted.tolist(), 'owner': binding['owner'],
                'declared_projection':graph.project(point['frame'],point['point'])}
        except (ValueError, KeyError, IndexError, TypeError, np.linalg.LinAlgError) as error:
            anchors[name] = {'passed': False, 'valid': False, 'reason': str(error), 'status': 'MEASUREMENT_REQUIRED'}
    footprint_geometry, footprints = {}, {}
    if strict(contract):
        from .spatial_footprints import measure as measure_footprint
        footprint_bindings = {b['footprint']: b for b in contract['spatial_footprint_bindings']}
        for spec in contract['spatial']['footprints']:
            if spec['unit'] not in units:continue
            try:
                measured = measure_footprint(spec, footprint_bindings[spec['id']], native, graph)
                footprint_geometry[spec['id']] = measured
                footprints[spec['id']] = {k: v for k, v in measured.items() if k != 'geometry'}
            except (ValueError, KeyError, IndexError, TypeError, np.linalg.LinAlgError) as error:
                footprints[spec['id']] = {'passed': False, 'valid': False, 'status': 'MEASUREMENT_REQUIRED', 'reason': str(error)}
    paint = None
    for relation in contract['spatial']['relations']:
        if not set(relation['units']) <= units:
            continue
        key, kind = relation['id'], relation['kind']
        names = relation['landmarks']
        try:
            if any(p not in actual for p in names):
                raise ValueError('Missing actual spatial landmark; diagnose measurement first')
            screen = np.asarray([actual[p] for p in names])
            source = np.asarray([expected[p] for p in names])
            values = {}
            if kind == 'axis_direction':
                error = _angle(screen[1]-screen[0], source[1]-source[0], relation.get('directed', True))
            elif kind == 'pose_projection':
                a, b = screen[1]-screen[0], screen[2]-screen[0]
                sa, sb = source[1]-source[0], source[2]-source[0]
                cross = lambda x, y: float(x[0]*y[1]-x[1]*y[0])
                if min(abs(cross(a, b)), abs(cross(sa, sb))) < 1e-10:
                    raise ValueError('Pose landmarks must resolve handedness')
                error = max(_angle(a, sa), _angle(b, sb))
                values['handedness_matches'] = cross(a, b)*cross(sa, sb) > 0
                if not values['handedness_matches']:
                    error = 180.
            elif kind == 'extent_ratio':
                lengths = [float(np.linalg.norm(p[1]-p[0])) for p in (screen[:2], screen[2:], source[:2], source[2:])]
                if min(lengths) < 1e-10:
                    raise ValueError('Projected ratio needs nonzero axes')
                error = abs(lengths[0]/lengths[1]-lengths[2]/lengths[3])
            elif kind == 'shared_edge':
                error = max(float(np.linalg.norm(screen[0]-screen[2])), float(np.linalg.norm(screen[1]-screen[3])))
            elif kind == 'occludes':
                if paint is None:
                    from .neighbor_geometry import read
                    paint, _ = read(task, state, candidate)
                    if scene_override is not None:
                        paint = dict(paint)
                        from .spatial_footprints import _native_contours, _measure_curves
                        for obj in scene_override['objects']:
                            if obj['id'] not in override_owners:continue
                            if not obj.get('style',{}).get('fill'):
                                # An edge cannot claim the area of a filled face.
                                paint[obj['id']]={'geometry':None}
                                continue
                            entry=native[obj['id']]
                            region=_measure_curves(_native_contours(entry,'native_domain'),entry['matrix'],.01)
                            paint[obj['id']]={'geometry':region['geometry'].buffer(-region['error'])}
                front, back = [bindings[p]['owner'] for p in names]
                if front == back:
                    raise ValueError('Occlusion requires independent actual native parts')
                from shapely.geometry import Point
                probe = (source[0]+source[1])/2
                for owner in (front, back):
                    geometry = paint.get(owner, {}).get('geometry')
                    if geometry is None or geometry.is_empty or not geometry.covers(Point(probe)):
                        raise ValueError('Actual front/back painted coverage at the frozen occlusion probe required')
                order = {name: index for index, name in enumerate(native)}
                good_order = order[front] > order[back]
                error = max(float(np.linalg.norm(screen[0]-screen[1])), float(np.linalg.norm(source[0]-source[1])))
                values['actual_paint_order_matches'] = good_order
                if not good_order:
                    error = max(error, relation['tolerance']+1.)
            elif kind == 'volume_contains':
                # Source 3D structure is checked in its own coordinates. Saved
                # 2D anchors can verify only its observed projection.
                if any(all_points[p]['frame'] != relation['frame'] for p in names):
                    raise ValueError('Volume landmarks need the same explicit 3D frame')
                low, high = np.asarray(relation['bounds'], float)
                if np.any(low > high):
                    raise ValueError('Invalid source volume bounds')
                local = np.asarray([all_points[p]['point'] for p in names], float)
                error = float(np.maximum(np.maximum(low-local, local-high), 0).max())
                values['claim'] = 'visible_projection_only'
                values['hidden_volume_verified'] = False
            else:
                local = np.asarray([graph.inverse_plane(relation['frame'], p) for p in screen])
                complete = []
                if strict(contract) and kind in ('center_in_plane', 'align_in_plane', 'contained_on_plane', 'supported_by', 'attached_to_face'):
                    keys = relation['footprints']
                    if any(k not in footprint_geometry for k in keys):
                        raise ValueError('Missing complete actual subject footprint')
                    complete = [footprint_geometry[k] for k in keys]
                    if any(not f['valid'] for f in complete):raise ValueError('Invalid complete footprint')
                    from shapely.ops import unary_union
                    domain = unary_union([f['geometry'] for f in complete])
                    precision = max(f['error'] for f in complete)
                    if precision > relation['tolerance']:
                        raise ValueError('Frozen footprint precision cannot certify this relation tolerance')
                if kind == 'center_in_plane' and complete:
                    bounds = domain.bounds
                    center = np.array([(bounds[0]+bounds[2])/2, (bounds[1]+bounds[3])/2])
                    delta = center-np.asarray(relation['target'])
                    error = float(np.max(np.abs(delta)))+precision
                    values.update(actual_center=center.tolist(), two_axis_error=delta.tolist(),
                        precision_bound=precision, coverage='complete_direct_content_union',
                        projected_target=graph.project(relation['frame'], relation['target']))
                elif kind == 'center_in_plane':
                    content = np.asarray([p for p, name in zip(local, names) if all_points[name]['unit'] in relation['content_units']])
                    if not len(content):
                        raise ValueError('Actual direct-content footprint required for aggregate centering')
                    center = (content.min(0)+content.max(0))/2
                    delta = center-np.asarray(relation['target'])
                    error = float(np.max(np.abs(delta)))
                    values.update(actual_center=center.tolist(), two_axis_error=delta.tolist(),
                        projected_target=graph.project(relation['frame'], relation['target']))
                elif kind == 'align_in_plane' and complete:
                    axis = relation['axis']; mode = relation['alignment_anchor']
                    coordinates = []
                    source_footprints = {f['id']: f for f in contract['spatial']['footprints']}
                    for unit in relation['subjects']:
                        member = unary_union([footprint_geometry[k]['geometry'] for k in relation['footprints']
                                              if source_footprints[k]['unit'] == unit])
                        b = member.bounds
                        coordinates.append(b[axis] if mode == 'min' else b[axis+2] if mode == 'max' else (b[axis]+b[axis+2])/2)
                    error = float(np.ptp(coordinates))+2*precision
                    values.update(coverage='complete_subject_footprints', precision_bound=2*precision)
                elif kind == 'align_in_plane':
                    error = float(np.ptp(local[:, relation['axis']]))
                elif kind in ('contained_on_plane', 'supported_by', 'attached_to_face'):
                    if complete:
                        from .spatial_footprints import _polygon
                        usable = _polygon(relation['region'])
                        holes=[_polygon(h) for h in relation.get('region_holes',[])]
                        if holes:usable=usable.difference(unary_union(holes))
                        allowed = usable.buffer(relation['tolerance']-precision)
                        covered = allowed.covers(domain)
                        outside = domain.difference(allowed)
                        error = 0. if covered else relation['tolerance']+max(math.sqrt(outside.area), outside.length/2, 1e-10)
                        values.update(complete_coverage=covered, precision_bound=precision,
                            coverage='complete_subject_domain_in_usable_face',
                            basis='saved_native_contact_or_attached_domain',
                            value_definition='zero if conservative complete coverage holds; otherwise positive coverage violation above tolerance')
                    else:
                        error = _region_distance(local, relation['region'])
                        values['basis'] = 'actual_contact_or_surface_landmarks_in_usable_face'
                        values['coverage'] = 'legacy_declared_visible_landmarks'
                elif kind == 'same_plane':
                    # Coplanarity is source-declared. Reprojection verifies its
                    # visible native realization; no 3D inverse is manufactured.
                    wanted = np.asarray([graph.inverse_plane(relation['frame'], p) for p in source])
                    error = float(np.max(np.linalg.norm(local-wanted, axis=1)))
                    values['claim'] = 'declared_plane_projection_consistency'
                else:
                    raise ValueError('Unsupported spatial relation')
                values['actual_face_coordinates'] = local.tolist()
            anchor_pass = all(anchors[p]['passed'] for p in names)
            footprint_pass = all(footprints[k]['passed'] for k in relation.get('footprints', [])) if strict(contract) else True
            results[key] = {'passed': bool(error <= relation['tolerance'] and anchor_pass), 'valid': True,
                'kind': kind, 'value': error, 'threshold': relation['tolerance'], 'unit': relation['unit'],
                'phase': PHASE[kind], 'landmarks_current': anchor_pass, **values}
            results[key]['passed'] = results[key]['passed'] and footprint_pass
        except (ValueError, KeyError, IndexError, TypeError, np.linalg.LinAlgError) as error:
            results[key] = {'passed': False, 'valid': False, 'kind': kind, 'phase': PHASE[kind],
                'reason': str(error), 'status': 'MEASUREMENT_REQUIRED'}
    valid = all(r.get('valid') for r in [*anchors.values(), *footprints.values(), *results.values()])
    failed = [k for k, r in results.items() if not r['passed']]
    return {'passed': all(r['passed'] for r in [*anchors.values(), *footprints.values(), *results.values()]),
        'valid': valid, 'status': 'SPATIAL_CHECKED' if valid else 'MEASUREMENT_REQUIRED',
        'anchors': anchors, 'footprints': footprints, 'relations': results, 'spatial_basis': (row or contract)['spatial_basis'],
        'pptx_hash': candidate['pptx']['sha256'], 'source_hash': state['source']['sha256'],
        'repair_order': sorted(failed, key=lambda k: (results[k]['phase'], k)),
        'claim': 'declared_numeric_surrogate' if scene_override is not None else 'saved_native_observable_projection',
        'hidden_3d_verified': False}


def instance_policy(row, mother):
    """A single affine copy cannot enact a new perspective or solid viewpoint."""
    if not row.get('spatial_context'):
        return {'route': 'native_affine_copy'}
    mode = row.get('spatial_instance', {})
    route = mode.get('route')
    if route not in ('native_affine_copy', 'reproject_constructor') or not mode.get('source_evidence'):
        raise ValueError('Choose a source-supported spatial instance route')
    if route == 'native_affine_copy':
        if not mode.get('projection_equivalence_evidence'):
            raise ValueError('Affine native reuse needs evidence that view, visible faces and occlusion are equivalent')
        return mode
    if not mode.get('construction_ids') or not mother.get('spatial_basis'):
        raise ValueError('Changed view reuses qualified local constructor geometry, not flattened screen polygons')
    return mode
