"""Finite source-declared 3D vertices compiled to editable native surfaces."""
import copy
import numpy as np
from .common import identity
from .spatial_frames import Frames

KINDS = {'spatial_prism', 'spatial_polyhedron'}


def canonical(spec):
    """Local anatomy is independent of projection and observed face subset."""
    keys = ('kind', 'footprint', 'depth', 'vertices', 'contour', 'center', 'radii',
            'inner_radii', 'start_degrees', 'end_degrees', 'rotation', 'levels', 'upper', 'lower', 'points')
    return identity({k: spec[k] for k in keys if k in spec})


def prepare(spec, spatial):
    result = copy.deepcopy(spec)
    if 'frame_ref' not in result:
        return result
    graph = Frames(spatial['frames'])
    frame = result['frame_ref']
    if frame not in graph.rows:
        raise ValueError('Construction frame must belong to the frozen original spatial graph')
    if result['kind'] not in KINDS:
        if graph.dimension(frame) != 2 or 'frame' in result:
            raise ValueError('Planar native construction needs one declared plane frame')
        result['frame'] = {'homography': graph.matrix(frame).tolist(),
                           'source_evidence': graph.rows[frame]['source_evidence']}
    return result


def construct(spec, spatial):
    from .recipes import path
    graph = Frames(spatial['frames'])
    frame = spec['frame_ref']
    if graph.dimension(frame) != 3:
        raise ValueError('Spatial solid construction needs an explicit rigid 3D frame')
    if spec['kind'] == 'spatial_prism':
        footprint = np.asarray(spec['footprint'], float)
        if footprint.ndim != 2 or footprint.shape[1] != 2 or not 3 <= len(footprint) <= 64:
            raise ValueError('Bounded semantic prism footprint required')
        depth = np.asarray(spec['depth'], float)
        if depth.shape != (3,) or not np.isfinite(depth).all() or abs(depth[2]) < 1e-10:
            raise ValueError('Prism depth must leave its local footprint plane')
        front = np.c_[footprint, np.zeros(len(footprint))]
        vertices = np.r_[front, front+depth]
        count = len(front)
        faces = [{'id': 'top', 'indices': list(range(count)), 'style': spec['top_style'], 'role': 'top_surface'}]
        if spec.get('base_style'):
            faces.append({'id': 'base', 'indices': list(range(count, 2*count)), 'style': spec['base_style'], 'role': 'base_surface'})
        for wall in spec.get('walls', []):
            i = wall['edge']
            if type(i) is not int or not 0 <= i < count:
                raise ValueError('Unknown source prism wall edge')
            j = (i+1) % count
            faces.append({'id': wall['id'], 'indices': [i, j, j+count, i+count],
                          'style': wall['style'], 'role': wall.get('role', 'side_surface')})
    else:
        vertices = np.asarray(spec['vertices'], float)
        faces = spec['faces']
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not 3 <= len(vertices) <= 128 or not np.isfinite(vertices).all():
        raise ValueError('Finite shared local 3D semantic vertices required')
    if not 1 <= len(faces) <= 128:
        raise ValueError('Bounded explicitly observed faces required')
    projected = [graph.project(frame, p) for p in vertices]
    objects, parts = [], []
    def append(name, indices, style, role, closed):
        if not name or name in {p['part'] for p in parts} or any(type(i) is not int or not 0 <= i < len(vertices) for i in indices):
            raise ValueError('Distinct native part and shared vertex references required')
        if not (3 if closed else 2) <= len(indices) <= 64 or len(indices) != len(set(indices)):
            raise ValueError('Compact face/edge indices required')
        if closed and not style.get('fill'):
            raise ValueError('Every observed native face needs explicit material')
        obj = path(spec['id']+'.'+name, [projected[i] for i in indices], spec.get('parent'),
                   style.get('stroke'), style.get('fill') if closed else None,
                   style.get('line_width', 0), closed, role)
        obj['style'].update(copy.deepcopy(style))
        caps = ['editable', 'projection', 'shared_edges']+(['closed_contour'] if closed else [])
        obj['content']['source_surface'] = {'version': 'native-surfaces-1.35.0', 'construction': spec['id'],
            'part': name, 'role': role, 'capabilities': caps, 'frame_ref': frame,
            'frame_basis': identity(graph.ancestors(frame)), 'canonical_geometry': canonical(spec)}
        objects.append(obj)
        parts.append({'owner': obj['id'], 'part': name, 'role': role, 'capabilities': caps})
    for face in faces:
        if not face.get('source_evidence', spec.get('source_evidence')):
            raise ValueError('Visible faces are source decisions, never back-face invention')
        indices = face['indices']
        if any(type(i) is not int or not 0 <= i < len(vertices) for i in indices):
            raise ValueError('Spatial face indices escaped shared vertices')
        coordinates = vertices[indices]
        if len(coordinates) < 3 or np.linalg.matrix_rank(coordinates[1:]-coordinates[0], tol=1e-8) != 2:
            raise ValueError('Each native face must be a nondegenerate planar source surface')
        append(face['id'], indices, face['style'], face.get('role', 'surface'), True)
    for edge in spec.get('visible_edges', []):
        append(edge['id'], edge['vertices'], edge['style'], 'visible_edge', False)
    order = spec.get('paint_order', [])
    if len(order) != len(parts) or set(order) != {p['part'] for p in parts}:
        raise ValueError('Explicit source paint order must cover every observed spatial face and edge')
    objects.sort(key=lambda o: order.index(o['content']['source_surface']['part']))
    for index, obj in enumerate(objects):
        obj['z_order'] = spec.get('z_order', 0)+index
    return objects, {'version': 'native-surfaces-1.35.0', 'id': spec['id'], 'kind': spec['kind'],
        'source_evidence': spec['source_evidence'], 'spec_hash': identity(spec), 'parts': parts,
        'canonical_geometry': canonical(spec), 'frame_basis': identity(graph.ancestors(frame)),
        'geometry_hash': identity(objects)}


def validate_instances(contract):
    from .spatial_checks import instance_policy
    rows = {r['id']: r for r in contract['components']}
    specs = {s['id']: s for s in contract.get('native_constructions', [])}
    manifests = {m['id']: m for m in contract.get('construction_manifests', [])}
    for row in rows.values():
        if row['route'] != 'instance':
            continue
        mode = instance_policy(row, rows[row['mother']])
        if mode['route'] != 'reproject_constructor':
            continue
        mapping = mode.get('constructor_map', {})
        if not mapping or set(mapping.values()) != set(mode['construction_ids']):
            raise ValueError('Source-declared canonical mother/instance constructor map required')
        members = {row['mother']}
        while True:
            more = members | {r['id'] for r in rows.values() if r.get('parent') in members}
            if more == members:
                break
            members = more
        mother_owners = {o for r in rows.values() if r['id'] in members for o in r['owners']}
        target_owners = set()
        for source, target in mapping.items():
            if source not in specs or target not in specs or canonical(specs[source]) != canonical(specs[target]):
                raise ValueError('Reprojected instance must retain qualified mother local anatomy')
            if not {p['owner'] for p in manifests[source]['parts']} <= mother_owners:
                raise ValueError('Canonical constructor escaped the qualified mother')
            target_owners.update(p['owner'] for p in manifests[target]['parts'])
        if not target_owners <= set(row['owners']):
            raise ValueError('Reprojected parts escaped actual instance ownership')
        if row.get('variant'):
            raise ValueError('Declare a source-supported constructor variant separately before reprojecting')


def instance_check(task, state, candidate, contract, row):
    from .component_workflow import _resource
    from .native_core_inspect import check
    from .common import read_json
    validate_instances(contract)
    source = read_json(_resource(task, contract['source_scene']))
    mother_parts = {p['owner'] for m in contract['construction_manifests']
                    if m['id'] in row['spatial_instance']['constructor_map'] for p in m['parts']}
    mother = check(source,task,_resource(task,candidate['pptx']),sorted(mother_parts),'body')
    result = check(source, task, _resource(task, candidate['pptx']), row['owners'], 'body')
    from .spatial_checks import evaluate
    spatial = evaluate(task, state, candidate, contract, row)
    return {'passed': mother['status']=='PASS' and result['status'] == 'PASS' and spatial['passed'], 'valid': spatial.get('valid', True),
        'kind': 'instance_of', 'route': 'reproject_constructor', 'native': result, 'spatial': spatial,
        'actual_qualified_mother':mother,
        'canonical_geometry_reused': True, 'hidden_3d_verified': False}


def reproject(task, request):
    from . import agent_runtime as a, component_workflow as c
    from .common import read_json, writer
    from .component_constructor import construct as save_native
    task, state = a._state(task)
    contract, ledger = c._load(task, state)
    candidate = c._candidate(state)
    row = c.component_row(task, state, contract, request['component'])
    if (request.get('source_hash') != state['source']['sha256'] or request.get('pptx_hash') != candidate['pptx']['sha256'] or
            row['route'] != 'instance' or row.get('spatial_instance', {}).get('route') != 'reproject_constructor'):
        raise ValueError('Current source-bound spatial constructor instance required')
    c.refresh(task, state, contract, ledger, candidate)
    if ledger['components'][row['mother']]['status'] != 'QUALIFIED' or ledger['components'][row['id']]['status'] == 'QUALIFIED':
        raise ValueError('Preserve a qualified instance; qualify its local mother before reuse')
    validate_instances(contract)
    original = read_json(c._resource(task, contract['source_scene']))
    from .native_core_inspect import check
    mother_parts = {p['owner'] for m in contract['construction_manifests']
                    if m['id'] in row['spatial_instance']['constructor_map'] for p in m['parts']}
    mother_native = check(original,task,c._resource(task,candidate['pptx']),sorted(mother_parts),'body')
    if mother_native['status'] != 'PASS':
        return {'status':'SOURCE_DECISION_REQUIRED','reason':'Retain the actual qualified mother and recapture its current local constructor before reprojecting; do not revert to an older planned anatomy.',
                'mother_native':mother_native,'best_retained':True,'acceptance':False}
    actual = read_json(c._resource(task, candidate['scene']))
    targets = {n['id']: n for n in original['objects'] if n['id'] in row['owners']}
    actual['objects'] = [copy.deepcopy(targets.get(n['id'], n)) for n in actual['objects']]
    allowed = {owner: ['replace_component'] for owner in row['owners']}
    reason = {'kind': 'spatial_constructor_instance', 'components': [row['id']],
              'post_save': {'statuses': {row['id']: 'INSTANCE_NATIVE_CONFIRMATION_REQUIRED'}}}
    saved = save_native(task, state, actual, candidate, allowed, reason)
    if saved is None:
        return {'status': 'FONT_BINDING_REQUIRED', 'component': row['id']}
    task, state = a._state(task)
    _, ledger = c._load(task, state)
    record = ledger['components'][row['id']]
    record['status'] = 'INSTANCE_NATIVE_CONFIRMATION_REQUIRED'
    record['instantiation'] = {'candidate': saved['pptx'], 'mother': row['mother'],
                               'route': 'reproject_constructor', 'spatial_basis': row['spatial_basis']}
    with writer(task):
        c._save_ledger(task, state, ledger, 'spatial_instance_reprojected', {'component': row['id'], 'candidate': saved['pptx']})
    return {'status': 'INSTANCE_SAVED_ACTUAL_RENDER_REQUIRED', 'candidate': saved, 'acceptance': False}
