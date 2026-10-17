"""Typed subjects and complete footprint obligations for new spatial contracts."""
import numpy as np
from .spatial_frames import array


def validate(observed, graph):
    spatial = observed['spatial']
    units = {u['id']: u for u in observed['units']}
    points = {p['id']: p for p in spatial['landmarks']}
    features = {f['id']: f for f in observed['features']}
    footprints = spatial.get('footprints', [])
    if len(footprints) > 20000 or len({f.get('id') for f in footprints}) != len(footprints):
        raise ValueError('Distinct bounded logical footprint IDs required')
    footprints = {f['id']: f for f in footprints}
    for frame in graph.rows.values():
        if frame.get('owner_unit') not in units:
            raise ValueError('Each spatial frame needs its explicit original owner_unit')
    for footprint in footprints.values():
        frame = footprint.get('frame')
        if (footprint.get('unit') not in units or frame not in graph.rows or graph.dimension(frame) != 2
                or footprint.get('role') not in ('logical', 'contact', 'attached')
                or not footprint.get('source_evidence') or footprint.get('coverage') != 'complete_logical_domain'
                or type(footprint.get('precision')) not in (int, float) or footprint['precision'] <= 0):
            raise ValueError('Complete source-supported plane footprint with frozen precision required')
        names = footprint.get('features', [])
        if (not names or len(set(names)) != len(names) or not set(names) <= set(features)
                or any(features[k]['unit'] != footprint['unit'] for k in names)):
            raise ValueError('Footprint features must cover its own original logical/contact domain')
        # Geometry is independently observed, not copied from the native plan.
        from .spatial_footprints import source_region
        source_region(footprint)
        if type(footprint.get('tolerance')) not in (int, float) or footprint['tolerance'] < 0:
            raise ValueError('Freeze the original footprint discrepancy bound')
    for relation in spatial['relations']:
        kind, names = relation['kind'], relation['landmarks']
        own_points = {points[k]['unit'] for k in names}
        if kind in ('axis_direction', 'pose_projection', 'extent_ratio'):
            subject = relation.get('subject')
            if subject not in relation['units'] or own_points != {subject}:
                raise ValueError('A pose/axis/ratio relation must measure its named subject')
            if kind == 'pose_projection':
                roles=[points[k]['role'] for k in names[:3]]
                if roles[0]!='pose_origin' or len(set(roles))!=3 or not set(roles[1:]) <= {'pose_u','pose_v','pose_w'}:
                    raise ValueError('Pose uses an explicit origin and two distinct observable local axes')
                triangle = np.asarray([points[k]['source_point'] for k in names[:3]])
                if abs(float(np.linalg.det(np.c_[triangle, np.ones(3)]))) < 1e-10:
                    raise ValueError('Observable pose landmarks must be noncollinear in the original')
        elif kind in ('shared_edge', 'occludes'):
            subjects = relation.get('subjects', [])
            if len(subjects) != 2 or len(set(subjects)) != 2 or set(subjects) != set(relation['units']):
                raise ValueError('Shared edges/occlusion need two ordered original subjects')
            expected = [subjects[0], subjects[1]] if kind == 'occludes' else [subjects[0]]*2+[subjects[1]]*2
            if [points[k]['unit'] for k in names] != expected:
                raise ValueError('Spatial junction landmarks do not belong to their ordered subjects')
        elif kind in ('supported_by', 'attached_to_face', 'contained_on_plane'):
            subject, reference = relation.get('subject'), relation.get('reference')
            if (subject == reference or {subject, reference} != set(relation['units']) or own_points != {subject}
                    or graph.rows[relation['frame']]['owner_unit'] != reference):
                raise ValueError('Support/attachment must bind the subject to its explicit reference face')
            role = 'contact_vertex' if kind == 'supported_by' else 'surface_vertex'
            if any(points[k]['role'] != role for k in names):
                raise ValueError('Use actual contact/surface vertices for this typed relationship')
        elif kind == 'center_in_plane':
            if (set(relation['units']) != set(relation['content_units']) | {relation.get('container')}
                    or graph.rows[relation['frame']]['owner_unit'] != relation.get('container')):
                raise ValueError('Centering reference must be the semantic container usable face')
        elif kind in ('align_in_plane', 'same_plane', 'volume_contains'):
            subjects = relation.get('subjects', [])
            if not subjects or set(subjects) != own_points or not set(subjects) <= set(relation['units']):
                raise ValueError('Every declared measured subject needs its own actual landmarks')
        if kind in ('center_in_plane', 'align_in_plane', 'contained_on_plane', 'supported_by', 'attached_to_face'):
            if kind=='align_in_plane' and relation.get('alignment_anchor') not in ('min','center','max'):
                raise ValueError('Choose the complete footprint edge/center used by face-local alignment')
            if kind in ('contained_on_plane','supported_by','attached_to_face'):
                from .spatial_footprints import _polygon
                usable=_polygon(relation['region'])
                holes=relation.get('region_holes',[])
                if len(holes)>64 or any(not usable.covers(_polygon(h)) for h in holes):
                    raise ValueError('Usable-face holes must be bounded original regions inside that face')
            selected = relation.get('footprints', [])
            expected = set(relation['content_units']) if kind == 'center_in_plane' else set(relation.get('subjects', [relation.get('subject')]))
            if (not selected or len(selected) != len(set(selected)) or not set(selected) <= set(footprints)
                    or {footprints[k]['unit'] for k in selected} != expected
                    or any(footprints[k]['frame'] != relation['frame'] for k in selected)):
                raise ValueError('Face layout must measure complete subject footprints in one declared plane')
            for key in selected:
                footprint = footprints[key]
                placement = units[footprint['unit']]['spatial']['placement']
                role = 'contact' if placement == 'standing' else 'attached' if placement == 'attached' else 'logical'
                if footprint['role'] != role:
                    raise ValueError('Standing/attached content uses its actual contact/attached footprint')
    for unit in units.values():
        value = unit['spatial']
        own = [r for r in spatial['relations'] if r.get('subject') == unit['id']]
        poses = [r for r in own if r['kind'] in ('axis_direction', 'pose_projection')]
        if value['mode'] in ('surface','solid') and not poses:
            raise ValueError('A spatial unit needs its own measured observable pose')
        if value['placement'] in ('standing', 'attached'):
            kind = 'supported_by' if value['placement'] == 'standing' else 'attached_to_face'
            if not any(r['kind'] == kind for r in own):
                raise ValueError('The spatial subject itself needs its measured support/attachment')
