"""Explicit editing promises and bounded route selection for complex visuals.

This validates a representation contract, not the truth of host observations.
Scientific content still needs independent visual review of the saved render.
"""
from PIL import Image
from .common import digest, safe_path

VERSION = 'complex-assets-1.0.0'
RASTER_ROLES = {'environment_asset', 'illustration_asset'}
RASTER_OPERATIONS = {'move', 'resize', 'copy', 'replace', 'crop', 'hide'}
REPRESENTATIONS = {'native', 'native_group', 'hybrid_group', 'layered_raster', 'raster_module', 'svg_component'}

COMMON_OPERATIONS = {'move', 'resize', 'copy', 'hide'}
OPERATIONS_BY_RENDER_TYPE = {
    'photo': RASTER_OPERATIONS,
    'svg': COMMON_OPERATIONS | {'replace'},
    'group': COMMON_OPERATIONS | {'ungroup', 'reorder'},
    'text': COMMON_OPERATIONS | {'edit_text', 'style'},
    'equation': COMMON_OPERATIONS | {'edit_equation', 'style'},
    'table': COMMON_OPERATIONS | {'edit_cells', 'style'},
    'connector': COMMON_OPERATIONS | {'edit_endpoints', 'style'},
    'shape': COMMON_OPERATIONS | {'style', 'edit_adjustments'},
    'path': COMMON_OPERATIONS | {'style', 'edit_vector_nodes'},
    'bezier': COMMON_OPERATIONS | {'style', 'edit_vector_nodes'},
    'trace': COMMON_OPERATIONS | {'style', 'edit_vector_nodes', 'ungroup'},
}
OPERATION_ALIASES = {'edit_math': 'edit_equation'}
SCIENTIFIC_SEMANTICS = {
    'scientific_route', 'scientific_path', 'scientific_node', 'scientific_marker',
    'trajectory', 'goal_marker', 'data_node', 'graph_edge', 'plot_curve',
    'annotation', 'target_marker', 'scientific_foreground',
}


def supported_operations(obj):
    """Structural possibilities, not evidence of a successful Office edit."""
    unsupported = set(obj.get('edit_contract', {}).get('unsupported_operations', []))
    return OPERATIONS_BY_RENDER_TYPE.get(obj['render_type'], set()) - unsupported


def editing_gaps(node, objects):
    """A promise must apply to each owned fragment, never an unrelated child.

    Parts with different operations need their own semantic nodes. A parent
    cannot claim path editing merely because one descendant happens to be a path.
    """
    targets = node.get('render_ids', []) + node.get('wrapper_ids', [])
    missing = []
    for requested in node['edit_targets']:
        operation = OPERATION_ALIASES.get(requested, requested)
        # Moving/copying fragments is possible; ungrouping belongs to a wrapper.
        required = targets
        if operation in ('ungroup', 'reorder'):
            required = [rid for rid in targets if objects[rid]['render_type'] in ('group', 'trace')]
        if not required:
            missing.append({'operation': requested, 'render_id': None, 'reason': 'no editable owner'})
        for rid in required:
            if operation not in supported_operations(objects[rid]):
                missing.append({'operation': requested, 'render_id': rid,
                                'reason': 'unsupported by saved representation'})
    return missing


def is_scientific_foreground(obj):
    role = obj.get('protection_role')
    if role not in (None, 'scientific', 'decoration'):
        raise ValueError('Unknown foreground protection role')
    # Core scientific/text types cannot be opted out by a decoration flag.
    return (obj['render_type'] in ('text', 'equation', 'connector', 'table') or
            role == 'scientific' or obj.get('semantic_type') in SCIENTIFIC_SEMANTICS)


def validate_contract(obj, scene, base=None):
    contract = obj.get('edit_contract')
    complex_raster = obj['render_type'] == 'photo' and obj['semantic_type'] in RASTER_ROLES
    if not contract:
        if complex_raster:
            raise ValueError('Complex raster requires an explicit edit contract')
        return
    representation = contract.get('representation')
    required = contract.get('required_operations')
    unsupported = contract.get('unsupported_operations')
    if representation not in REPRESENTATIONS or not isinstance(required, list) or not required:
        raise ValueError('Editing representation and nonempty operations are required')
    if not isinstance(unsupported, list) or set(required) & set(unsupported):
        raise ValueError('Editing promises contradict unsupported operations')
    if not contract.get('reason'):
        raise ValueError('Editing boundary needs a user-facing reason')
    kind = obj['render_type']
    if not set(required) <= OPERATIONS_BY_RENDER_TYPE.get(kind, set()):
        raise ValueError('Requested editing operation is not supported by this representation')
    if representation == 'svg_component' and kind != 'svg':
        raise ValueError('SVG component must retain its actual vector resource')
    if representation == 'raster_module' and kind != 'photo':
        raise ValueError('Raster contract must map to an actual picture')
    if representation in ('layered_raster', 'native_group', 'hybrid_group') and kind != 'group':
        raise ValueError('Layered representation must have a real group')
    if kind == 'photo' and (representation != 'raster_module' or not set(required) <= RASTER_OPERATIONS):
        raise ValueError('A raster cannot promise native internal edits')
    if representation == 'native' and kind in ('photo', 'group'):
        raise ValueError('Native unit representation does not match object')
    if kind == 'group':
        objects = {o['id']: o for o in scene['objects']}
        descendants = []
        for member in objects.values():
            parent = member.get('parent');seen = set()
            while parent and parent not in seen and parent in objects:
                if parent == obj['id']:
                    descendants.append(member);break
                seen.add(parent);parent = objects[parent].get('parent')
        raster_count = sum(member['render_type'] == 'photo' for member in descendants)
        if representation == 'native_group' and raster_count:
            raise ValueError('Native group cannot disguise raster descendants; use hybrid_group')
        if representation == 'layered_raster' and raster_count < 2:
            raise ValueError('Layered raster promise requires at least two independently saved picture layers')
        if representation == 'hybrid_group' and not raster_count:
            raise ValueError('Hybrid group needs an actual raster descendant')
    if not complex_raster:
        return
    if not {'edit_pixels_in_ppt', 'edit_vector_nodes'} <= set(unsupported):
        raise ValueError('Raster limitations must explicitly disclose pixel/path editing')
    provenance = obj['content'].get('provenance', {})
    if provenance.get('method') not in {'source_extraction', 'editor_cleanup', 'model_assisted', 'external_asset'}:
        raise ValueError('Complex asset needs a known provenance method')
    if provenance.get('source_sha256') != scene['source']['sha256']:
        raise ValueError('Complex asset provenance uses another source')
    if not provenance.get('record') or provenance.get('scientific_content') != 'excluded':
        raise ValueError('Provenance record and scientific-content exclusion are required')
    if obj['evidence_status'] == 'observed' and provenance['method'] == 'model_assisted':
        raise ValueError('Generated reconstruction cannot silently become observed')
    if provenance['method'] == 'model_assisted' and not provenance.get('model_identity'):
        raise ValueError('Record actual model identity or unknown, never guess')
    roi = obj['content'].get('source_roi')
    if not roi or len(roi) != 4:
        raise ValueError('Complex asset needs its source ROI')
    x, y, w, h = roi
    if min(x, y) < 0 or min(w, h) <= 0 or x+w > scene['canvas']['width'] or y+h > scene['canvas']['height']:
        raise ValueError('Asset ROI outside frozen canvas')
    protected = obj['content'].get('protected_objects')
    if not isinstance(protected, list):
        raise ValueError('Explicit scientific foreground protection list required')
    objects = {o['id']: o for o in scene['objects']}
    for key in protected:
        if key not in objects or objects[key]['render_type'] in ('photo', 'group'):
            raise ValueError('Protected object must be a real scientific foreground leaf')
    if base is not None:
        record = provenance['record']
        if digest(safe_path(base, record['path'])) != record['sha256']:
            raise ValueError('Asset method record changed')
        file = safe_path(base, obj['content']['path'])
        if digest(file) != obj['content']['sha256']:
            raise ValueError('Complex asset payload changed')
        with Image.open(file) as image:
            if image.width < 1 or image.height < 1:
                raise ValueError('Empty complex asset')
    from .cutout_quality import validate_workflow
    validate_workflow(obj, scene, base)


def drawing_order(scene):
    """Match build's recursive z order, including different group ancestors."""
    children = {}
    for o in scene['objects']:
        children.setdefault(o.get('parent'), []).append(o)
    result = []
    indexes = {o['id']: i for i, o in enumerate(scene['objects'])}
    def visit(parent):
        for o in sorted(children.get(parent, []), key=lambda item: item.get('z_order', indexes[item['id']])):
            result.append(o['id'])
            if o['render_type'] == 'group':
                visit(o['id'])
    visit(None)
    return {key: i for i, key in enumerate(result)}


def validate_foreground(scene, scientific_ids=()):
    order = drawing_order(scene)
    objects = {o['id']: o for o in scene['objects']}
    for asset in objects.values():
        if asset['render_type'] != 'photo' or asset['semantic_type'] not in RASTER_ROLES:
            continue
        ax, ay, aw, ah = asset['bbox']
        required = set(asset['content']['protected_objects'])
        for obj in objects.values():
            if obj['render_type'] in ('group','photo'):
                continue
            if not is_scientific_foreground(obj) and obj['id'] not in required and obj['id'] not in scientific_ids:
                continue
            x, y, w, h = obj['bbox']
            if min(ax+aw, x+w) > max(ax, x) and min(ay+ah, y+h) > max(ay, y):
                if obj['id'] not in required or order[asset['id']] >= order[obj['id']]:
                    raise ValueError('Complex asset must declare and remain behind overlapping scientific foreground: '+obj['id'])


def plan_routes(analysis, capabilities):
    """Routes are candidates to test, never proof of quality/tool availability."""
    available = {k for k, v in capabilities.items() if v is True}
    nodes = {n['id']: n for n in analysis['nodes']}
    children = {k: [] for k in nodes}
    for n in nodes.values():
        if n.get('parent'):
            children[n['parent']].append(n['id'])
    result = []
    for n in nodes.values():
        complex_role = n.get('asset_role') in RASTER_ROLES
        routes = ['native_reconstruction']
        if complex_role:
            routes += ['source_extraction']
            if 'professional_editor' in available: routes += ['editor_cleanup', 'local_trace_trial']
            if 'image_generation' in available: routes += ['model_assisted']
        required = n.get('edit_targets', [])
        if complex_role and any(k in required for k in ('edit_vector_nodes', 'edit_pixels_in_ppt')):
            routes = [r for r in routes if r not in ('source_extraction', 'editor_cleanup', 'model_assisted')]
        result.append({'module': n['id'], 'parent': n.get('parent'), 'children': children[n['id']],
                       'routes': routes, 'required_operations': required,
                       'stop_reason': n.get('decomposition', {}).get('reason'),
                       'status': 'CANDIDATES_REQUIRE_ACTUAL_RENDER_AND_EDIT_VERIFICATION'})
    return {'version': VERSION, 'modules': result, 'capabilities': capabilities,
            'selection': 'Compare fixed reference metrics and editing gates; retain Pareto tradeoffs, no invented total score'}
