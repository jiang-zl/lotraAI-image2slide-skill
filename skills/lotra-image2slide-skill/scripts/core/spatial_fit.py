"""Finite coupled spatial parameters on the existing search/commit journal.

The original graph and targets are immutable. Trial frames are constructor
inputs only; metrics always use the original graph and original observations.
"""
import copy
import math
from .common import identity
from .spatial_frames import frames, strict


def is_spatial(row):
    return row.get('fit', {}).get('adapter') == 'spatial_parameters'


def writes(row):
    return [{'owner': owner, 'field': field} for owner in row['owners']
            for field in (['bbox'], ['content'])]


def _resources(contract):
    return {'frames': {r['id']: r for r in contract['spatial']['frames']},
            'constructions': {r['id']: r for r in contract.get('native_constructions', [])}}


def prepare(contract, row, scene, previous=None):
    if not is_spatial(row):return
    if not strict(contract) or row['route'] != 'local_fit':
        raise ValueError('Coupled spatial fitting requires a new spatial local-fit contract')
    spec = row.get('spatial_fit', {})
    names = spec.get('construction_ids', [])
    resources = _resources(contract)
    manifests = {m['id']: m for m in contract['construction_manifests']}
    if not names or len(names) != len(set(names)) or not set(names) <= set(manifests):
        raise ValueError('Spatial fitting needs distinct registered local constructors')
    owners = {p['owner'] for name in names for p in manifests[name]['parts']}
    if owners != set(row['owners']):
        raise ValueError('One spatial numeric resource group must own all and only its compiled native parts')
    bindings = spec.get('bindings', {})
    if set(bindings) != set(row.get('parameters', {})):
        raise ValueError('Every spatial parameter needs one explicit original resource binding')
    if not any(p.get('state')=='tunable' for p in row['parameters'].values()):
        raise ValueError('Determined spatial parameters use fixed native construction, not numeric search')
    addresses=[(b.get('resource'),b.get('id'),b.get('field')) for b in bindings.values()]
    from .component_revision import overlap
    for index,(kind,resource,path) in enumerate(addresses):
        if isinstance(path,list) and any(k==kind and r==resource and isinstance(p,list) and overlap(path,p)
                                         for k,r,p in addresses[index+1:]):
            raise ValueError('Spatial parameter resource addresses must be nonoverlapping')
    graph = frames(contract['spatial'])
    permitted_fields = {'frames': {'euler_degrees', 'translation', 'projection', 'origin', 'u', 'v', 'local_corners', 'parent_corners'},
        'constructions': {'footprint', 'depth', 'vertices', 'contour', 'center', 'radii', 'inner_radii',
                          'start_degrees', 'end_degrees', 'rotation', 'points', 'upper', 'lower', 'levels'}}
    for name, binding in bindings.items():
        kind, resource, path = binding.get('resource'), binding.get('id'), binding.get('field')
        if kind not in resources or resource not in resources[kind] or not isinstance(path, list) or not path or path[0] not in permitted_fields[kind]:
            raise ValueError('Bind finite numeric spatial fields, never visibility/topology/material decisions')
        if any(key in ('style','id','role','op','source_evidence') for key in path):
            raise ValueError('Spatial search cannot edit source semantics, operators or paint')
        pointer = resources[kind][resource]
        for key in path:pointer = pointer[key]
        parameter = row['parameters'][name]
        if type(pointer) not in (int, float) or not math.isfinite(pointer) or parameter['value'] != pointer:
            raise ValueError('Spatial initial parameter must equal its frozen original constructor input')
        if parameter.get('coordinate_space') != resource or not parameter.get('source_evidence'):
            raise ValueError('Every spatial parameter declares its resource coordinate domain and original evidence')
        if kind == 'frames':
            frame = resources[kind][resource]
            parent_unit = graph.rows[frame['parent']]['units'] if frame.get('parent') else frame['units']
            unit = ('degree' if path[0] == 'euler_degrees' else
                    'projection_coefficient' if path[0] == 'projection' else
                    frame['units'] if frame['kind']=='space3d' and path[0]=='translation' else
                    frame['units'] if path[0]=='local_corners' else
                    parent_unit+'/'+frame['units'] if path[0] in ('u','v') else parent_unit)
            # A shared camera/plane cannot be fitted as an isolated child patch.
            consumers = [s['id'] for s in contract.get('native_constructions', [])
                         if s.get('frame_ref') and resource in {f['id'] for f in graph.ancestors(s['frame_ref'])}]
            if not set(consumers) <= set(names):
                raise ValueError('SPATIAL_SOURCE_DECISION_REQUIRED: shared frame consumers require one explicit resource group')
        else:
            if resource not in names:raise ValueError('Spatial parameter escaped its registered constructors')
            construction = resources[kind][resource]
            if construction.get('frame_ref') not in graph.rows:
                raise ValueError('Spatial parameter constructors need an explicit source frame_ref')
            unit = 'degree' if any(key in ('rotation','start_degrees','end_degrees') for key in path) else graph.rows[construction['frame_ref']]['units']
        if parameter.get('unit') != unit:
            raise ValueError('Spatial numeric parameter unit conflicts with its constructor/frame coordinates')
    metrics = []
    points = [p for p in contract['spatial']['landmarks'] if p['unit'] in row['spatial_context']['units']]
    footprint_specs = [p for p in contract['spatial']['footprints'] if p['unit'] in row['spatial_context']['units']]
    relations = [r for r in contract['spatial']['relations'] if set(r['units']) <= set(row['spatial_context']['units'])]
    for channel, records, bound in [('anchors', points, 'tolerance_source_px'), ('footprints', footprint_specs, 'tolerance'),
                                     ('relations', relations, 'tolerance')]:
        for record in records:
            unit = 'source_px' if channel == 'anchors' else record['unit'] if channel == 'relations' else graph.rows[record['frame']]['units']
            metrics.append({'id': 'spatial.'+channel+'.'+record['id'], 'role':'target', 'direction':'lower',
                'threshold':record[bound], 'unit':unit, 'measurement_domain':'analytic',
                'measurement':{'adapter':'spatial_constraint','channel':channel,'target':record['id'],
                    'spatial_basis':row['spatial_basis'],'source_evidence':record['source_evidence']}})
    if not metrics:raise ValueError('Spatial search needs independently observed original targets')
    existing = row.get('metrics', [])
    if any(m.get('measurement', {}).get('adapter') != 'spatial_constraint' for m in existing):
        raise ValueError('Spatial parameter search uses spatial hard targets; visual/feature gates remain separate')
    if existing and existing != metrics and existing != (previous or {}).get('metrics'):
        raise ValueError('Callers cannot replace or loosen program-derived original spatial targets')
    row['metrics'] = metrics
    row['fit']['bindings'] = {name:{'owner':row['owners'][0],'field':['content']} for name in bindings}
    row['parameter_metric_map'] = {name:[m['id'] for m in metrics] for name in bindings}
    row['spatial_fit']['source_basis'] = identity({'spatial_basis':row['spatial_basis'], 'constructors':
        [resources['constructions'][name] for name in names], 'bindings':bindings})


def apply(scene, row, values, contract):
    if contract is None:raise ValueError('Current frozen spatial contract required by the shared fit/commit path')
    from .native_surfaces import compile_spec
    if set(values) != set(row['parameters']):raise ValueError('Complete spatial parameter vector required')
    trial = copy.deepcopy(contract)
    resources = _resources(trial)
    for name, binding in row['spatial_fit']['bindings'].items():
        value, parameter = values[name], row['parameters'][name]
        if type(value) not in (int, float) or not math.isfinite(value):raise ValueError('Finite spatial trial required')
        if parameter['state'] == 'fixed' and value != parameter['value']:raise ValueError('Fixed spatial field changed')
        if parameter['state'] == 'tunable' and not parameter['bounds'][0] <= value <= parameter['bounds'][1]:
            raise ValueError('Spatial trial escaped its frozen original interval')
        pointer = resources[binding['resource']][binding['id']]
        for key in binding['field'][:-1]:pointer = pointer[key]
        pointer[binding['field'][-1]] = value
    frames(trial['spatial'])
    objects = []
    for name in row['spatial_fit']['construction_ids']:
        objects.extend(compile_spec(resources['constructions'][name], trial['spatial'])[0])
    changed = {o['id']: o for o in objects}
    if set(changed) != set(row['owners']):raise ValueError('Numeric fitting cannot change native topology/ownership')
    current = {o['id']: o for o in scene['objects']}
    for owner, node in changed.items():
        if node['style'] != current[owner]['style'] or node.get('parent') != current[owner].get('parent') or node.get('z_order') != current[owner].get('z_order'):
            raise ValueError('Spatial trials preserve fixed paint, parent and painter order')
    result = copy.deepcopy(scene)
    result['objects'] = [copy.deepcopy(changed.get(o['id'], o)) for o in result['objects']]
    return result, {owner:['geometry','bbox.left','bbox.top','bbox.width','bbox.height'] for owner in row['owners']}


def metrics(report, row):
    values = {}
    for metric in row['metrics']:
        spec = metric['measurement']
        item = report.get(spec['channel'], {}).get(spec['target'], {})
        values[metric['id']] = {'valid':item.get('valid') is True,'value':item.get('value'), 'unit':metric['unit']}
    return values


def measured(task, state, candidate, contract, row, scene=None):
    from .spatial_checks import evaluate
    report = evaluate(task,state,candidate,contract,row,scene_override=scene,override_owners=row['owners'] if scene else ())
    return {'metrics':metrics(report,row), 'hard_checks':{'original_spatial_targets_frozen':True},
            'spatial':report, 'source_hash':state['source']['sha256'],
            'limits':'Numeric surrogate is not qualification; actual saved native and render gates remain required.'}
