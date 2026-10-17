"""Component contracts, facet dependencies and phase guards for v1.32.

Source decisions are inputs. Fixed parameters do not become repeated raster
tests merely because they belong to a group. Qualification is separate from
page placement and final visual acceptance.
"""
import copy
import math
from collections import defaultdict, deque
from .common import identity, read_json, write_json, ROOT

VERSION = 'component-protocol-1.32.0'
FACETS = ('content', 'paint', 'geometry', 'assembly', 'pose')
ROUTES = {'fixed_parameters', 'local_fit', 'assembly', 'instance', 'specialist'}
KINDS = {'text', 'shape', 'equation', 'connector', 'path', 'bezier', 'group',
         'table', 'photo', 'trace', 'svg'}
RELATIONS = {'contains', 'contact', 'gap', 'align_x', 'align_y', 'layer_before',
             'connects', 'label_for', 'instance_of', 'intentional_overlap'}


def policy():
    return read_json(ROOT / 'config/component-workflow.json')


def finite(value, location='value'):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Nonfinite component parameter: ' + location)
    if isinstance(value, dict):
        for key, child in value.items(): finite(child, location + '.' + str(key))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value): finite(child, location + '.' + str(index))


def source_content(content):
    value = copy.deepcopy(content)
    for key in ('native_snapshot', 'native_snapshot_math', 'native_snapshot_table'):
        value.pop(key, None)
    return value


def facets(node):
    """Own intrinsic geometry excludes global translation and parent pose."""
    content = source_content(node.get('content', {}))
    bbox = node.get('bbox', [0, 0, 0, 0])
    geometry_keys = {'points', 'commands', 'paths', 'preset', 'adjustments',
                     'geometry_ref', 'closed', 'radius', 'contours', 'ports'}
    geometry = {key: value for key, value in content.items() if key in geometry_keys}
    # Scene path coordinates are absolute source coordinates. Translation must
    # not invalidate intrinsic path shape; preserve the frozen local contour.
    if 'points' in geometry and node['render_type']=='connector':
        geometry['points'] = [[round(p[0]-bbox[0], 11), round(p[1]-bbox[1], 11)]
                              for p in geometry['points']]
    text = {key: value for key, value in content.items() if key not in geometry_keys}
    style = copy.deepcopy(node.get('style', {}))
    rotation = style.pop('rotation', 0)
    return {
        'content': identity({'kind': node['render_type'], 'content': text}),
        'paint': identity(style),
        'geometry': identity({'kind': node['render_type'], 'size': None if node['render_type']=='group' else bbox[2:], 'geometry': geometry}),
        'assembly': identity({'parent': node.get('parent'), 'order': node.get('z_order')}),
        'pose': identity({'position': bbox[:2], 'rotation': rotation,
                          'group_extent':bbox[2:] if node['render_type']=='group' else None}),
    }


def validate_contract(value, scene, source_hash):
    finite(value)
    if value.get('design_revision',8)!=8: raise ValueError('Unsupported component design revision; migrate explicitly')
    import jsonschema
    try:jsonschema.validate(value,read_json(ROOT/'schemas/component-contract.schema.json'))
    except jsonschema.ValidationError as error:raise ValueError('Invalid component contract: '+error.message) from error
    if value.get('schema') != VERSION or value.get('source_hash') != source_hash:
        raise ValueError('Component contract requires this original and schema')
    nodes = {node['id']: node for node in scene['objects']}
    if len(nodes) != len(scene['objects']): raise ValueError('Duplicate Scene owner')
    components = value.get('components', [])
    if not components or len({row['id'] for row in components}) != len(components):
        raise ValueError('Distinct nonempty component IDs required')
    ids = {row['id'] for row in components}
    source_units=value.get('source_inventory',[])
    if not source_units or len({r['id'] for r in source_units})!=len(source_units):
        raise ValueError('Freeze an independent original semantic inventory before native ownership')
    if any(not r.get('source_evidence') for r in source_units):raise ValueError('Every original unit needs located evidence')
    required_units={r['id'] for r in source_units if not r.get('excluded_reason')}
    covered_units={name for row in components for name in row.get('source_units',[])}
    if required_units!=covered_units:raise ValueError('Complete source-unit/component reconciliation required')
    coverage = defaultdict(list)
    for row in components:
        if value.get('workflow_version') in ('1.33.0','1.34.0','1.35.0') and row.get('route')=='assembly' and (not row.get('semantic_class') or not row.get('view')):
            raise ValueError('SOURCE_DECISION_REQUIRED: freeze assembly semantic_class and observed view for the private method lifecycle')
        if row.get('route') not in ROUTES: raise ValueError('Unsupported component route')
        if not row.get('source_evidence') or not row.get('source_refs'):
            raise ValueError('Independent original evidence required: ' + row['id'])
        owners = row.get('owners', [])
        if not owners or len(owners) != len(set(owners)) or not set(owners) <= set(nodes):
            raise ValueError('Exact unique native owners required: ' + row['id'])
        if row.get('parent') and row['parent'] not in ids:
            raise ValueError('Unknown component parent')
        if row.get('mother'):
            if row['mother'] not in ids or row['mother'] == row['id']:
                raise ValueError('Unknown or cyclic mother')
            if row['route'] != 'instance' or not (row.get('instance_transform') or row.get('spatial_instance',{}).get('route')=='reproject_constructor'):
                raise ValueError('Instances require an explicit original-supported transform')
        if row.get('variant'):
            variant=row['variant']
            if row['route']!='instance' or variant.get('mother')!=row.get('mother') or not variant.get('source_evidence'):
                raise ValueError('A derived variant must reference its qualified base mother')
            for override in variant.get('overrides',[]):
                if override.get('owner') not in row.get('instance_transform',{}).get('owner_map',{}):
                    raise ValueError('Variant ownership escaped its base mother')
                path=override.get('field',[])
                if path[:2] in (['style','font'],['style','math_font'],['style','font_faces']):
                    target=row['instance_transform']['owner_map'][override['owner']]
                    from .component_fields import lookup
                    exists,hint=lookup(nodes.get(target),path)
                    from .font_resources import name_key
                    equal=(name_key(hint)==name_key(override['value']) if isinstance(hint,str) and isinstance(override['value'],str)
                           else hint==override['value'])
                    if not exists or not equal:
                        raise ValueError('Declare a font variant in its target source Scene before language-restricted binding')
            from .component_variants import variant_scene
            from .component_font_instances import variant_requests
            prepared,_=variant_scene(scene,row)
            variant_requests(prepared,row)
        if row.get('route') == 'fixed_parameters':
            if any(nodes[n]['render_type'] not in ('text','shape','equation','path','bezier','connector','table','photo','trace') for n in owners):
                raise ValueError('Fixed route requires a supported deterministic native owner')
            if not row.get('frozen_parameters'):
                raise ValueError('Freeze original-read parameters before primitive construction')
        parameters = row.get('parameters', {})
        for name, parameter in parameters.items():
            if parameter.get('state') not in ('fixed', 'tunable'):
                raise ValueError('Explicit fixed/tunable parameter required: ' + name)
            if parameter['state'] == 'tunable':
                bounds = parameter.get('bounds')
                if (not isinstance(bounds, list) or len(bounds) != 2 or
                    not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in bounds) or
                    bounds[0] >= bounds[1] or not bounds[0] <= parameter['value'] <= bounds[1]):
                    raise ValueError('Finite original-bound parameter range required')
                if not parameter.get('source_evidence'):
                    raise ValueError('Tunable range requires source evidence')
        metrics = row.get('metrics', [])
        for metric in metrics:
            if metric.get('role') not in ('target', 'diagnostic', 'trigger', 'stagnation'):
                raise ValueError('Metric must declare its role')
            if metric.get('direction') not in ('lower', 'higher', 'exact'):
                raise ValueError('Metric direction required')
            if metric['role'] == 'target' and metric.get('threshold') is None:
                raise ValueError('A missing target remains a source decision, never PASS')
            if metric.get('threshold') is not None and (isinstance(metric['threshold'], bool) or not isinstance(metric['threshold'], (int, float))):
                raise ValueError('Metric threshold must be numeric')
        if row['route'] == 'local_fit' and not any(m['role'] == 'target' and m.get('applicable', True) for m in metrics):
            raise ValueError('Local fitting requires an applicable frozen target')
        for owner in owners: coverage[owner].append(row['id'])
        ancestors = {row['id']}; parent = row.get('parent')
        while parent:
            if parent in ancestors: raise ValueError('Component containment cycle')
            ancestors.add(parent)
            parent = next(c.get('parent') for c in components if c['id'] == parent)
    excluded = value.get('nonpaint_owners', [])
    if set(excluded) - set(nodes): raise ValueError('Unknown nonpaint owner')
    if set(excluded) & set(coverage): raise ValueError('Nonpaint declarations cannot overlap component ownership')
    if any(len(owners) != 1 for owners in coverage.values()):
        raise ValueError('Each native owner belongs to exactly one component; assemblies own their group roots')
    if set(nodes) - set(coverage) - set(excluded):
        raise ValueError('Incomplete component ownership coverage')
    relations = value.get('relations', [])
    if len({r['id'] for r in relations}) != len(relations): raise ValueError('Duplicate relation ID')
    for row in components:
        seen = {row['id']}; next_id = row.get('mother')
        while next_id:
            if next_id in seen: raise ValueError('Mother dependency cycle')
            seen.add(next_id)
            next_id = next(c.get('mother') for c in components if c['id'] == next_id)
    by_id={row['id']:row for row in components}
    def visit(name,ancestors):
        if name in ancestors:raise ValueError('Combined assembly/mother dependency cycle')
        row=by_id[name]
        for next_id in (row.get('parent'),row.get('mother')):
            if next_id:visit(next_id,ancestors|{name})
    for name in by_id:visit(name,set())
    for relation in relations:
        if (relation.get('kind') not in RELATIONS or not relation.get('source_evidence') or
            not set(relation.get('components', [])) <= ids or len(relation.get('components', [])) < 2):
            raise ValueError('Located source-supported relation required')
    excluded_checks = value.get('scope', {}).get('excluded_checks', [])
    permitted = {'office_open', 'office_edit', 'office_save_reopen'}
    if set(excluded_checks) - permitted: raise ValueError('Unsupported user exclusion')
    for row in components:
        qualification_relations(value,row)
    return value


def metric_result(contract, measured):
    """Missing or invalid measurements never supply a passing number."""
    rows = []
    for metric in contract.get('metrics', []):
        result = measured.get(metric['id'])
        applicable = metric.get('applicable', True)
        if not applicable:
            if not metric.get('not_applicable_reason'):
                raise ValueError('Inapplicable metric requires a reason')
            rows.append({'id': metric['id'], 'status': 'NOT_APPLICABLE', 'role': metric['role']})
            continue
        valid = isinstance(result, dict) and result.get('valid') is True
        number = result.get('value') if valid else None
        if not valid or not isinstance(number, (int, float)) or isinstance(number, bool) or not math.isfinite(number):
            rows.append({'id': metric['id'], 'status': 'MEASUREMENT_REQUIRED', 'role': metric['role']})
            continue
        threshold = metric.get('threshold')
        preferred = (number <= threshold if metric['direction'] == 'lower' else
                  number >= threshold if metric['direction'] == 'higher' else number == threshold) if threshold is not None else None
        acceptable = metric.get('acceptable_threshold',threshold)
        if metric.get('acceptable_threshold') is not None and (metric['direction']!='lower' or acceptable < threshold):
            raise ValueError('Acceptable tier requires a pre-frozen lower-is-better bound')
        passed = (number <= acceptable) if acceptable is not None and metric['direction']=='lower' else preferred
        rows.append({'id': metric['id'], 'role': metric['role'], 'value': number,
                     'threshold': threshold, 'direction': metric['direction'],
                     'quality_tier': 'preferred' if preferred else 'acceptable' if passed else None,
                     'acceptable_threshold':acceptable,
                     'status': 'PASS' if passed else 'FAIL' if passed is False else 'DIAGNOSTIC'})
    targets = [row for row in rows if row['role'] == 'target' and row['status'] != 'NOT_APPLICABLE']
    return {'passed': bool(targets) and all(row['status'] == 'PASS' for row in targets), 'items': rows,
            'quality_tier':'acceptable' if any(row.get('quality_tier')=='acceptable' for row in targets) else 'preferred'}


def dependency_graph(contract):
    result = defaultdict(set)
    for row in contract['components']:
        if row.get('parent'): result[row['id']].add(row['parent'])
    for relation in contract.get('relations', []):
        for owner in relation['components']:
            result[owner].add('relation:' + relation['id'])
    return {key: sorted(value) for key, value in result.items()}


def impact(contract, changed):
    """Intrinsic changes propagate upward, not through unchanged siblings."""
    components = {row['id']: row for row in contract['components']}
    graph = dependency_graph(contract)
    affected = set(); relations = set(); queue = deque()
    for name, changed_facets in changed.items():
        if name not in components: raise ValueError('Unknown changed component')
        if set(changed_facets) - set(FACETS): raise ValueError('Unknown changed facet')
        affected.add(name)
        queue.append((name, bool(set(changed_facets) & {'content', 'paint', 'geometry', 'assembly'})))
    visited = set()
    while queue:
        owner, intrinsic = queue.popleft()
        if (owner, intrinsic) in visited: continue
        visited.add((owner, intrinsic))
        if intrinsic:
            for row in contract['components']:
                if row.get('mother') == owner:
                    affected.add(row['id']); queue.append((row['id'], True))
        for related in graph.get(owner, []):
            if related.startswith('relation:'): relations.add(related[9:])
            else:
                affected.add(related)
                # Moving a child changes its parent's internal assembly.
                queue.append((related, True))
    if contract.get('workflow_version') == '1.35.0':
        # Typed spatial neighbours share placement/occlusion dependencies, not
        # intrinsic mother anatomy. Their native checks must be refreshed.
        unit_components = defaultdict(set)
        for row in components.values():
            for unit in row.get('spatial_context', {}).get('units', []):
                unit_components[unit].add(row['id'])
        seeds = set(affected)
        for relation in contract.get('spatial', {}).get('relations', []):
            neighbours = set().union(*(unit_components[u] for u in relation['units']))
            if neighbours & seeds:
                affected.update(neighbours)
                relations.add('spatial:'+relation['id'])
        # A newly affected child also dirties containing assemblies and copies;
        # unrelated sibling anatomy and its retained best remain untouched.
        pending = deque(affected-seeds)
        seen = set()
        while pending:
            owner = pending.popleft()
            if owner in seen:continue
            seen.add(owner)
            parent = components[owner].get('parent')
            if parent:
                affected.add(parent);pending.append(parent)
                for copy_row in components.values():
                    if copy_row.get('mother') == parent:
                        affected.add(copy_row['id']);pending.append(copy_row['id'])
    return {'components': sorted(affected), 'relations': sorted(relations),
            'final_dirty': bool(changed), 'run_final_now': False}


def ready_for_final(contract, ledger):
    required = [row['id'] for row in contract['components']]
    pending = [name for name in required if ledger.get('components', {}).get(name, {}).get('status') != 'QUALIFIED']
    relation_pending = [r['id'] for r in contract.get('relations', [])
                        if ledger.get('relations', {}).get(r['id'], {}).get('status') != 'QUALIFIED']
    return {'ready': not pending and not relation_pending and ledger.get('layout_ready') is True and
                    not ledger.get('pending_transaction') and not ledger.get('user_reconciliation') and
                    not ledger.get('source_observation_dirty') and
                    (ledger.get('repair_batch') or {}).get('status')!='PLAN_REQUIRED',
            'components_pending': pending, 'relations_pending': relation_pending,
            'layout_ready': ledger.get('layout_ready') is True}


def qualification_identity(component, signatures, source_hash, policy_version):
    return identity({'source': source_hash, 'component': component,
                     'own_facets': signatures, 'policy_version': policy_version})


def qualification_relations(contract,row):
    """Mother qualification owns internal relations, never future copies."""
    members={row['id']}
    if row['route']=='assembly':
        while True:
            extended=members|{c['id'] for c in contract['components'] if c.get('parent') in members}
            if extended==members:break
            members=extended
    permitted=[r['id'] for r in contract.get('relations',[]) if
        (r['kind']!='instance_of' and set(r['components'])<=members if row['route']=='assembly'
         else r['kind']=='instance_of' and r['components'][1]==row['id'] if row['route']=='instance'
         else row['id'] in r['components'] and r['kind']!='instance_of')]
    explicit=row.get('required_relations')
    if explicit is not None and not set(explicit)<=set(permitted):
        raise ValueError('Qualification relations must belong to this phase; external relations belong to layout')
    return explicit if explicit is not None else permitted
