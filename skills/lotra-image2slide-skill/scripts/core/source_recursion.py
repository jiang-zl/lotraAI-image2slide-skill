"""Original-region worklist, typed leaf admission and saved-result closure.

The host interprets source meaning. This module supplies source-only structural
cues, owns every region's processing state and refuses unproved closure. Colour
or edge statistics alone do not certify semantic completeness.
"""
import copy
import math
import re
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from PIL import Image
from lxml import etree as E

from .common import digest, identity, read_json, write_json, safe_path

VERSION = 'source-recursion-1'
ROOT = 'source_root'
READY = frozenset(('SOURCE_LEAF_READY', 'SOURCE_PARTITION_REVIEWED', 'SURVEY_REVIEWED'))
ID = re.compile(r'^[A-Za-z][A-Za-z0-9_.:-]{0,190}$')


def policy():
    return read_json(Path(__file__).resolve().parents[2] / 'config/recursive-granularity.json')


def _ref(task, path):
    return {'path': path.relative_to(task).as_posix(), 'sha256': digest(path)}


def _resource(task, ref):
    path = safe_path(task, ref['path'])
    if digest(path) != ref['sha256']:
        raise ValueError('Original recursion evidence changed: ' + ref['path'])
    return path


def activate(task, state):
    state.setdefault('objectives', {})['source_recursion'] = True
    path = task / 'source/recursion/Activation.json'
    if not path.is_file():
        write_json(path, {'schema': VERSION, 'source_hash': state['source']['sha256'],
                         'policy_hash': identity(policy()), 'mandatory': True})
    verify_activation(task, state)


def verify_activation(task, state):
    file = task / 'source/recursion/Activation.json'
    if file.is_file():
        row = read_json(file)
        if row['source_hash'] != state['source']['sha256'] or not state.get('objectives', {}).get('source_recursion'):
            raise ValueError('Activated original recursion cannot be disabled or rebound')
        if row.get('policy_hash') != identity(policy()):
            raise ValueError('Recursion policy changed; explicitly migrate its original observations')


def _roi(value, size):
    if not isinstance(value, list) or len(value) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise ValueError('Four finite original-pixel coordinates required')
    x, y, w, h = value
    if min(x, y) < 0 or min(w, h) <= 0 or x+w > size[0]+1e-6 or y+h > size[1]+1e-6:
        raise ValueError('Source region outside original canvas')
    return list(value)


def _inside(child, parent):
    x, y, w, h = child
    a, b, c, d = parent
    return x >= a-1e-6 and y >= b-1e-6 and x+w <= a+c+1e-6 and y+h <= b+d+1e-6


def _intersection(a, b):
    x, y = max(a[0], b[0]), max(a[1], b[1])
    r, t = min(a[0]+a[2], b[0]+b[2]), min(a[1]+a[3], b[1]+b[3])
    return [x, y, r-x, t-y] if r > x and t > y else None


def _node(key, parent, roi, owner, role, **extra):
    return {'id': key, 'parent': parent, 'roi': list(roi), 'owner': owner,
            'role': role, 'status': 'OBSERVE', 'children': [], 'attempts': [],
            'critical_features': [], 'unexplained': [], **extra}


def _store(task, state, tree):
    from .source_contract import finite
    finite(tree, 'original_region_tree')
    tree['source_hash'] = state['source']['sha256']
    tree['policy_hash'] = identity(policy())
    tree['revision'] = tree.get('revision', 0)+1
    key = identity(tree)
    file = task / 'source/recursion/revisions' / (key+'.json')
    if not file.exists():
        write_json(file, tree)
    state['source_recursion'] = _ref(task, file)
    state.pop('acceptance', None)
    state.pop('quality_result', None)


def load(task, state):
    verify_activation(task, state)
    ref = state.get('source_recursion')
    if not ref:
        return None
    tree = read_json(_resource(task, ref))
    if tree.get('schema') != VERSION or tree.get('source_hash') != state['source']['sha256'] or tree.get('policy_hash') != identity(policy()):
        raise ValueError('Original recursion tree identity mismatch')
    nodes = tree['nodes']
    for key, node in nodes.items():
        if node['id'] != key or not ID.fullmatch(key):
            raise ValueError('Unique portable source region required')
        _roi(node['roi'], state['source_size'])
        seen = {key}
        parent = node.get('parent')
        while parent:
            if parent in seen or parent not in nodes:
                raise ValueError('Source-region containment cycle or missing parent')
            seen.add(parent)
            parent = nodes[parent].get('parent')
        if node.get('parent') and not _inside(node['roi'], nodes[node['parent']]['roi']):
            raise ValueError('Original child escaped its parent')
        expected = {k for k, row in nodes.items() if row.get('parent') == key}
        if set(node['children']) != expected or len(node['children']) != len(expected):
            raise ValueError('Region child registry/worklist disagree')
        if node['status'] in READY and node.get('unexplained'):
            raise ValueError('Unexplained original content cannot be complete')
    return tree


def initialize(task, state):
    activate(task, state)
    if state.get('source_recursion'):
        return load(task, state)
    if not state.get('analysis'):
        return None
    size = state['source_size']
    nodes = {ROOT: _node(ROOT, None, [0, 0, *size], None, 'root', status='WAIT_CHILDREN')}
    # Survey every original pixel, independently of the host's initial inventory.
    tile = policy()['survey_tile_px']
    for y in range(0, size[1], tile):
        for x in range(0, size[0], tile):
            key = 'survey_%d_%d' % (x, y)
            nodes[key] = _node(key, ROOT, [x, y, min(tile, size[0]-x), min(tile, size[1]-y)], None, 'survey')
    for comp in state['analysis']['components']:
        key = 'component:'+comp['id']
        nodes[key] = _node(key, ROOT, comp['roi'], comp['id'], 'semantic',
                          source_parts=list(comp.get('parts', [])), semantic_class=comp['semantic_class'])
    nodes[ROOT]['children'] = [k for k in nodes if k != ROOT]
    tree = {'schema': VERSION, 'revision': 0, 'nodes': nodes,
            'source_interpretation_limit': 'Program processing coverage is not a proof of every possible semantic interpretation.'}
    _store(task, state, tree)
    return tree


def structure(task, state, roi):
    """Cheap CPU source-only evidence; never invent an object from these counts."""
    x, y, w, h = roi
    box = (math.floor(x), math.floor(y), math.ceil(x+w), math.ceil(y+h))
    from .resource_facts import image_region
    with image_region(_resource(task, state['source']), [('crop',box)], state['source']['sha256']) as crop:
        raw = np.asarray(crop).astype(np.float32)
    step = policy()['structural_diagnostics']['colour_step']
    palette, counts = np.unique((raw.astype(np.uint8)//step).reshape(-1, 3), axis=0, return_counts=True)
    order = np.argsort(counts)[::-1][:8]
    colours = [{'rgb_bin': (palette[i]*step).tolist(), 'pixels': int(counts[i])} for i in order]
    edge = np.zeros(raw.shape[:2], dtype=bool)
    delta = policy()['structural_diagnostics']['edge_delta_rgb']
    if raw.shape[1] > 1:
        edge[:, 1:] |= np.max(np.abs(raw[:, 1:]-raw[:, :-1]), axis=2) >= delta
    if raw.shape[0] > 1:
        edge[1:, :] |= np.max(np.abs(raw[1:]-raw[:-1]), axis=2) >= delta
    yy, xx = np.nonzero(edge)
    located = None if len(xx) == 0 else [int(box[0]+xx.min()), int(box[1]+yy.min()), int(xx.max()-xx.min()+1), int(yy.max()-yy.min()+1)]
    # One-pixel separation preserves nearby small marks that a coarse NMS
    # window merges. These are source attention cues, never semantic counts.
    from scipy.ndimage import gaussian_filter
    from skimage.feature import peak_local_max
    gray=raw.mean(2);contrast=gaussian_filter(gray,.25)-gaussian_filter(gray,1.3)
    extrema=[]
    for sign in (1,-1):
        peaks=peak_local_max(sign*contrast,min_distance=1,threshold_abs=12,exclude_border=False)
        for y,x in peaks:
            extrema.append({'point':[float(box[0]+x+.5),float(box[1]+y+.5)],
                'signed_contrast_rgb':round(float(contrast[y,x]),4)})
    extrema.sort(key=lambda p:(-abs(p['signed_contrast_rgb']),p['point']))
    return {'original_pixel_box': list(box), 'pixel_count': int(raw.shape[0]*raw.shape[1]),
            'colour_bins': len(palette), 'dominant_colour_bins': colours,
            'edge_pixels': int(edge.sum()), 'edge_fraction': float(edge.mean()),
            'edge_roi': located, 'rgb_range': float(np.max(np.ptp(raw.reshape(-1, 3), axis=0))),
            'contrast_extrema':extrema[:64],'contrast_extrema_total':len(extrema),
            'contrast_cue_policy':'source-only gray residual .25/1.3 px; magnitude >=12 RGB; NMS separation 1 px; at most 64 strongest locations',
            'meaning': 'Attention cues: background/atomicity requires grounded host evidence and typed contracts, not a low pixel count.'}


def original_view(task, state, node):
    x, y, w, h = node['roi']
    box = [math.floor(x), math.floor(y), math.ceil(x+w), math.ceil(y+h)]
    key = identity({'source': state['source'], 'pixel_box': box})
    file = task / 'source/recursion/views' / (key+'.png')
    if not file.is_file():
        file.parent.mkdir(parents=True, exist_ok=True)
        from .resource_facts import image_region
        with image_region(_resource(task, state['source']), [('crop',box)], state['source']['sha256'], mode=None) as crop:
            crop.save(file)
    return {**_ref(task, file), 'source_hash': state['source']['sha256'],
            'roi': [box[0], box[1], box[2]-box[0], box[3]-box[1]],
            'coordinate_mapping': 'original_px = crop_px + pixel_box_origin; no recursive resampling'}


def pending(task, state):
    tree = initialize(task, state)
    if tree is None:
        return []
    # Source specifications can discover more parts than the initial component
    # outline. Each independent measured unit receives its own original crop;
    # a previously closed component is reopened when new children appear.
    changed = False
    units = state.get('quality', {}).get('units', {})
    for uid, unit in units.items():
        parent_id = 'component:'+str(unit.get('owner'))
        if parent_id not in tree['nodes'] or not unit.get('roi') or not unit.get('part'):
            continue
        key = 'unit:'+uid
        unit_identity=identity({'roi':unit['roi'],'profile':unit.get('profile'),
                                'features':unit.get('features',[]),'part':unit['part']})
        if key in tree['nodes']:
            if tree['nodes'][key].get('source_unit_identity') != unit_identity:
                row=tree['nodes'][key]
                row.setdefault('source_correction_history',[]).append({
                    'roi':row['roi'],'critical_features':row['critical_features'],
                    'attempts':row['attempts'],'reason':'An explicitly revised original quality unit changed its observation window'})
                tree['nodes'][key]['roi'] = _roi(unit['roi'], state['source_size'])
                tree['nodes'][key]['status'] = 'REOBSERVE'
                tree['nodes'][key]['critical_features'] = []
                tree['nodes'][key]['attempts'] = []
                tree['nodes'][key]['source_unit_identity'] = unit_identity
                tree['nodes'][key]['source_requirements'] = copy.deepcopy(unit.get('features',[]))
                parent=tree['nodes'][parent_id]
                a,b=parent['roi'],unit['roi'];left,top=min(a[0],b[0]),min(a[1],b[1])
                parent['roi']=[left,top,max(a[0]+a[2],b[0]+b[2])-left,max(a[1]+a[3],b[1]+b[3])-top]
                tree['nodes'][parent_id]['status'] = 'WAIT_CHILDREN'
                tree['nodes'][ROOT]['status'] = 'WAIT_CHILDREN'
                changed = True
            continue
        parent = tree['nodes'][parent_id]
        roi = _roi(unit['roi'], state['source_size'])
        a, b = parent['roi'], roi
        left, top = min(a[0], b[0]), min(a[1], b[1])
        parent['roi'] = [left, top, max(a[0]+a[2], b[0]+b[2])-left, max(a[1]+a[3], b[1]+b[3])-top]
        tree['nodes'][key] = _node(key, parent_id, roi, unit['owner'], 'drawing',
            source_parts=[unit['part']], semantic_class=unit['profile'], source_unit=uid,
            source_unit_identity=unit_identity,
            source_requirements=copy.deepcopy(unit.get('features', [])))
        parent['children'].append(key)
        parent['status'] = 'WAIT_CHILDREN'
        tree['nodes'][ROOT]['status'] = 'WAIT_CHILDREN'
        changed = True
    if changed:
        _store(task, state, tree)
    nodes = tree['nodes']
    rows = []
    # Fair breadth ordering: every sibling gets an inspection before deep retries.
    def depth(key):
        result = 0
        while nodes[key].get('parent'):
            result += 1
            key = nodes[key]['parent']
        return result
    for key, node in nodes.items():
        if node['status'] in READY:
            continue
        if node['children'] and not all(nodes[c]['status'] in READY for c in node['children']):
            continue
        rows.append((len(node['attempts']), depth(key), key))
    return [nodes[k] for _, _, k in sorted(rows)]


def packet(task, state, limit=None):
    rows = pending(task, state)
    if not rows:
        return None
    tree = load(task, state)
    limit = limit or policy()['work_batch']
    result = []
    for node in rows[:limit]:
        parent = tree['nodes'].get(node.get('parent'))
        comp = next((c for c in state['analysis']['components'] if c['id'] == node.get('owner')), None)
        intersections = [c['id'] for c in state['analysis']['components'] if _intersection(c['roi'], node['roi'])]
        result.append({'region': node, 'original_view': original_view(task, state, node),
                       'parent_original_view': original_view(task, state, parent) if parent else None,
                       'structure': structure(task, state, node['roi']), 'known_intersecting_components': intersections,
                       'component': comp, 'children': [tree['nodes'][c] for c in node['children']]})
    return {'schema': VERSION, 'kind': 'source_recursion', 'source_hash': state['source']['sha256'],
            'tree_hash': identity(tree), 'remaining': len(rows), 'items': result,
            'return_contract': {'decisions': [{'id': 'region id', 'action': 'finite action from policy',
                'original_view_sha256': 'actually inspected original crop', 'observed_content': ['located visible facts'],
                'unexplained': [], 'critical_features': [{'id': 'portable unique name', 'role': 'evidence role',
                    'roi': 'absolute original ROI within node', 'source_part': 'existing/new owner part or explicit objects',
                    'objects': ['exact saved semantic object names when known'], 'internal_structure': True}],
                'children': 'for split: [{id,roi,role,source_parts,semantic_class?}]',
                'leaf_type': 'typed leaf for propose_leaf',
                'representation': {'kind': 'native|vector|complete_media', 'source_parts': ['mapped owner parts'],
                    'objects': ['exact semantic/native ids'], 'edit_scope': ['required editing abilities'],
                    'structure_explanation': 'how all visible structure will be represented'},
                'survey_components': ['all applicable intersecting original components for survey'],
                'background_evidence': 'located source facts for genuine background/non-figure UI',
                'reason': 'source-based explanation; no arbitrary recursion depth'}]},
            'policy': policy(), 'instruction': 'Interpret each original crop with its parent context. Distinguish semantic splitting, drawing parts and repair. Every child is program-scheduled. Generic root approval, selecting a bitmap, small area and resource limits cannot end recursion.'}


def _strings(values, name, allow_empty=False):
    if not isinstance(values, list) or (not values and not allow_empty) or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError('Explicit nonempty strings required: '+name)
    return values


def bind(task, state, request):
    frontier=pending(task,state)
    tree = copy.deepcopy(initialize(task, state))
    if request.get('source_hash') != state['source']['sha256'] or request.get('tree_hash') != identity(tree):
        raise ValueError('Source recursion submission is stale or uses another original')
    rows = request.get('decisions', [])
    if not rows or len({r.get('id') for r in rows}) != len(rows):
        raise ValueError('Unique region decisions required')
    eligible = {n['id'] for n in frontier}
    components = copy.deepcopy(state['analysis']['components'])
    changed_parts = {}
    for row in rows:
        key = row.get('id')
        if key not in eligible:
            raise ValueError('Region is not on the executable frontier: '+str(key))
        node = tree['nodes'][key]
        if row.get('action') not in policy()['actions'] or not row.get('reason'):
            raise ValueError('Typed source recursion action and grounded reason required')
        view = original_view(task, state, node)
        if row.get('original_view_sha256') != view['sha256']:
            raise ValueError('Each child decision needs its own original crop identity')
        _strings(row.get('observed_content'), 'observed_content')
        unexplained = row.get('unexplained', [])
        if not isinstance(unexplained, list):
            raise ValueError('Unexplained source regions require a structured list')
        for unknown in unexplained:
            if not isinstance(unknown, dict) or not unknown.get('reason') or not _inside(_roi(unknown.get('roi'), state['source_size']), node['roi']):
                raise ValueError('Locate unexplained content within the current original child')
        features = row.get('critical_features', [])
        if not isinstance(features, list) or len({f.get('id') for f in features}) != len(features):
            raise ValueError('Unique typed critical content features required')
        for feature in features:
            if not ID.fullmatch(str(feature.get('id', ''))) or feature.get('role') not in policy()['evidence_roles']:
                raise ValueError('Typed source feature required')
            if not _inside(_roi(feature.get('roi'), state['source_size']), node['roi']):
                raise ValueError('Critical feature escaped its original region')
            if feature.get('role') != 'relationship' and not feature.get('source_part') and not feature.get('objects'):
                raise ValueError('Every critical visual feature needs a construction/measurement binding')
            if feature.get('role') == 'relationship' and not feature.get('relation_id'):
                raise ValueError('A source relationship needs an executable measured relation identity')
            _strings(feature.get('objects', []), 'feature.objects', allow_empty=True)
        prior = {f['id']: f for f in node['critical_features']}
        current = {f['id']: f for f in features}
        if any(current.get(k) != v for k, v in prior.items()):
            raise ValueError('A later drawing decision cannot discard frozen observed content')
        action = row['action']
        if action in ('split_semantic', 'split_drawing'):
            children = row.get('children', [])
            if not children or node['children']:
                raise ValueError('Nonempty new children required; existing source children cannot be replaced')
            seen_regions = set()
            for child in children:
                child_id = child.get('id')
                if not ID.fullmatch(str(child_id or '')) or child_id in tree['nodes']:
                    raise ValueError('New unique original child id required')
                roi = _roi(child.get('roi'), state['source_size'])
                if not _inside(roi, node['roi']):
                    raise ValueError('Split child outside parent; retain external relationships separately')
                role = child.get('role')
                if role not in ('semantic', 'drawing'):
                    raise ValueError('Distinguish semantic child and drawing part')
                parts = _strings(child.get('source_parts'), 'child.source_parts')
                signature = identity({'roi': roi, 'role': role, 'parts': parts})
                if signature in seen_regions or roi == node['roi'] and parts == node.get('source_parts', []):
                    raise ValueError('Repeated crop/renaming without content or representation progress')
                seen_regions.add(signature)
                tree['nodes'][child_id] = _node(child_id, key, roi, node.get('owner'), role,
                    source_parts=parts, semantic_class=child.get('semantic_class', node.get('semantic_class')))
                node['children'].append(child_id)
            node['status'] = 'WAIT_CHILDREN'
        elif action == 'review_partition':
            if not node['children'] or not all(tree['nodes'][c]['status'] in READY for c in node['children']) or unexplained:
                raise ValueError('Parent closure requires every child and a fresh parent-region review')
            node['status'] = 'SOURCE_PARTITION_REVIEWED'
        elif action == 'propose_leaf':
            if node['children'] or unexplained:
                raise ValueError('Children or unexplained original content forbid leaf admission')
            if node['role'] == 'survey':
                observed = set(_strings(row.get('survey_components', []), 'survey_components', allow_empty=True))
                relevant = {c['id'] for c in components if _intersection(c['roi'], node['roi'])}
                if not relevant <= observed or not row.get('background_evidence'):
                    raise ValueError('Original tile survey must cover known intersections and located background evidence')
                node['status'] = 'SURVEY_REVIEWED'
            else:
                leaf = row.get('leaf_type')
                rep = row.get('representation', {})
                if leaf not in policy()['leaf_types'] or not isinstance(rep, dict) or not rep.get('structure_explanation'):
                    raise ValueError('Typed task-relative leaf and explicit complete representation required')
                _strings(rep.get('edit_scope'), 'required editing scope')
                _strings(rep.get('source_parts', []), 'representation.source_parts', allow_empty=True)
                _strings(rep.get('objects', []), 'representation.objects', allow_empty=True)
                if leaf != 'background' and not rep.get('source_parts') and not rep.get('objects'):
                    raise ValueError('Representable leaf lacks a construction binding')
                if leaf == 'complete_media' and rep.get('kind') != 'complete_media':
                    raise ValueError('Media leaf needs complete permitted content; selecting bitmap is insufficient')
                if leaf in ('primitive', 'background') and any(f.get('internal_structure') for f in features):
                    raise ValueError('A plain primitive/background cannot swallow observed internal structure; use drawing parts or a verified complete assembly')
                if node.get('source_parts') and not set(node['source_parts']) <= set(rep.get('source_parts', [])) and not rep.get('objects'):
                    raise ValueError('Declared source parts cannot disappear behind an atomic label')
                node['leaf_type'] = leaf
                node['representation'] = copy.deepcopy(rep)
                node['status'] = 'SOURCE_LEAF_READY'
        else:
            node['status'] = 'REOBSERVE' if action == 'reobserve' else 'REPAIR_REQUIRED'
        node['observed_content'] = copy.deepcopy(row['observed_content'])
        node['critical_features'] = copy.deepcopy(features)
        node['unexplained'] = copy.deepcopy(unexplained)
        node['attempts'].append({'action': action, 'reason': row['reason'], 'view': view,
                                 'submission_hash': identity(row)})
        owner = node.get('owner')
        if owner:
            comp = next(c for c in components if c['id'] == owner)
            additions = {f['source_part'] for f in features if f.get('source_part')}
            additions |= {p for c in node['children'] for p in tree['nodes'][c].get('source_parts', [])}
            new = sorted(additions-set(comp['parts']))
            if new:
                comp['parts'] += new
                changed_parts.setdefault(owner, []).extend(new)
    # Persist only after every row passes; partial split transactions never escape.
    state['analysis']['components'] = components
    _store(task, state, tree)
    state['packet']=None
    if changed_parts:
        # Discovering a child extends obligations; it must never recreate
        # the whole quality state and discard frozen readings/history or
        # bindings for unrelated owners.
        from .source_quality import coverage_debt
        quality=state['quality']
        for owner in changed_parts:
            comp=next(c for c in components if c['id']==owner)
            spec=quality['specifications'].get(owner)
            debt=coverage_debt(state,comp,spec) if spec else [{'reason':'ORIGINAL_SPECIFICATION_REQUIRED'}]
            quality.setdefault('coverage_debt',{})[owner]=debt
            if debt and owner not in quality.setdefault('source_queue',[]):quality['source_queue'].append(owner)
    return {'status': 'SOURCE_REGION_DECISIONS_RECORDED', 'regions': len(rows),
            'new_source_parts': changed_parts, 'remaining': len(pending(task, state)),
            'tree': state['source_recursion']}


def _native_names(file):
    names = set()
    from .resource_facts import package_read,xml_part
    with package_read(file) as z:
        for name in z.namelist():
            if re.fullmatch(r'ppt/slides/slide\d+\.xml', name):
                root = xml_part(file,name)
                names.update(root.xpath('//*[local-name()="cNvPr"]/@name'))
    return names


def _objects(state, node, feature=None):
    item = feature or node.get('representation', {})
    result = set(item.get('objects', []))
    parts = [item['source_part']] if item.get('source_part') else item.get('source_parts', [])
    units = state.get('quality', {}).get('units', {})
    owner = node.get('owner')
    for part in parts:
        result.update(units.get(str(owner)+':'+part, {}).get('objects', []))
    return sorted(result)


def _crop_pixels(file, roi, size):
    x, y, w, h = roi
    from .resource_facts import image_dimensions,image_region
    actual_size=list(image_dimensions(file))
    operations=[] if actual_size==size else [('resize',tuple(size),Image.Resampling.LANCZOS)]
    operations.append(('crop',(math.floor(x),math.floor(y),math.ceil(x+w),math.ceil(y+h))))
    with image_region(file,operations) as crop:
        return np.asarray(crop).astype(float)


def _interior_cue(source, actual):
    # Exclude boundary ink before looking for loss of source interior structure.
    h, w = source.shape[:2]
    yy, xx = np.mgrid[:h, :w]
    if min(w, h) < 3:
        return {'measured': False, 'reason': 'Insufficient source interior pixels; native content remains mandatory'}
    u = (xx+.5-w/2)/max(w/2, 1)
    v = (yy+.5-h/2)/max(h/2, 1)
    mask = u*u+v*v < .64
    a, b = source[mask], actual[mask]
    src_range = float(np.max(np.percentile(a, 95, axis=0)-np.percentile(a, 5, axis=0)))
    dst_range = float(np.max(np.percentile(b, 95, axis=0)-np.percentile(b, 5, axis=0)))
    uniform = policy()['structural_diagnostics']['uniform_range_rgb']
    return {'measured': True, 'source_interior_robust_range_rgb': src_range,
            'actual_interior_robust_range_rgb': dst_range,
            'source_structured_actual_uniform': src_range > 6*uniform and dst_range <= uniform,
            'scope': 'Loss-of-interior-structure guard for independently declared critical interior content, not aesthetic similarity'}


def report(task, state, candidate=None, measured_context=None):
    pending(task,state)
    tree = load(task, state)
    if tree is None:
        return {'passed': False, 'status': 'ORIGINAL_REGION_TREE_REQUIRED', 'items': [], 'registered': 0, 'processed': 0}
    candidate = candidate or state.get('active_candidate') or state.get('selected')
    original = _resource(task, state['source'])
    names = _native_names(_resource(task, candidate['pptx'])) if candidate else set()
    preview = _resource(task, candidate['preview']) if candidate and candidate.get('preview') else None
    relationship_results={}
    if candidate:
        context=measured_context
        if context is None:
            from .semantic_composition import report as composition_report
            from .relative_layout import report as layout_report
            context={'composition':composition_report(task,state,candidate),'layout':layout_report(task,state,candidate)}
            from .source_quality import evaluate
            legacy=[evaluate(task,state,candidate,u) for u in state.get('quality',{}).get('units',{}).values() if u.get('profile')=='relation']
            context['source_relations']={'items':[{'id':r['unit'],'status':r['status']} for r in legacy]}
        for observation in context.values():
            for row in observation.get('items',[])+observation.get('relations',[]):
                if row.get('id'):
                    relationship_results[row['id']]=row.get('passed') is True or row.get('status') in ('minimum_met','stretch_met','numeric_minimum_met')
    from .detail_contracts import checks_report as detail_checks
    details={r['id']:r for r in detail_checks(task,state,candidate)['items']} if candidate and preview else {}
    rows = []
    for key, node in tree['nodes'].items():
        ready = node['status'] in READY
        feature_rows = []
        for feature in node['critical_features']:
            objects = _objects(state, node, feature)
            visual = feature['role'] != 'relationship'
            present = bool(objects) and set(objects) <= names if visual else relationship_results.get(feature.get('relation_id')) is True
            feature_rows.append({'id': feature['id'], 'role': feature['role'], 'objects': objects,
                                 'passed': present, 'status': 'NATIVE_CONTENT_PRESENT' if present else 'INDEPENDENT_CONTENT_OR_RELATION_CHECK_REQUIRED'})
        source_binding = _objects(state, node)
        bound = node['role'] in ('root', 'survey') or node['children'] or node.get('leaf_type') == 'background' or bool(source_binding) and set(source_binding) <= names
        interior = []
        if preview:
            for feature in node['critical_features']:
                if feature.get('internal_structure'):
                    item = _interior_cue(_crop_pixels(original, feature['roi'], state['source_size']),
                                         _crop_pixels(preview, feature['roi'], state['source_size']))
                    item['feature'] = feature['id']
                    interior.append(item)
            if not node['children'] and node.get('leaf_type') not in ('complete_media','background','text','formula','continuous_curve'):
                item=_interior_cue(_crop_pixels(original,node['roi'],state['source_size']),
                                   _crop_pixels(preview,node['roi'],state['source_size']))
                item['feature']='program_independent_leaf_interior'
                interior.append(item)
        lost = any(i.get('source_structured_actual_uniform') for i in interior)
        passed = ready and bool(node.get('attempts')) and bound and all(f['passed'] for f in feature_rows) and not lost
        detail=details.get(key.removeprefix('unit:')) if key.startswith('unit:') else None
        if node.get('source_detail_contract'):passed &= bool(detail and detail['passed'])
        rows.append({'id': key, 'parent': node.get('parent'), 'role': node['role'], 'roi': node['roi'],
                     'source_status': node['status'], 'passed': passed, 'source_processed': ready,
                     'native_binding': source_binding, 'native_binding_present': bool(bound),
                     'critical_features': feature_rows, 'interior_structure': interior,
                     'unexplained': node['unexplained'], 'detail_checks':detail,
                     'stop_evidence': node['attempts'][-1] if node['attempts'] else None})
    # Child failures always propagate upward; a root's prose cannot waive them.
    by_id = {r['id']: r for r in rows}
    for row in rows:
        if not row['passed']:
            parent = row['parent']
            while parent:
                by_id[parent]['passed'] = False
                parent = by_id[parent]['parent']
    result = {'schema': VERSION, 'passed': bool(rows) and all(r['passed'] for r in rows),
              'status': 'SOURCE_RECURSION_AND_SAVED_CONTENT_VERIFIED' if rows and all(r['passed'] for r in rows) else 'SOURCE_RECURSION_OR_CONTENT_PENDING',
              'source_hash': state['source']['sha256'], 'tree_hash': identity(tree),
              'candidate_hash': candidate['pptx']['sha256'] if candidate else None,
              'preview_hash': candidate['preview']['sha256'] if preview else None,
              'registered': len(rows), 'processed': sum(r['source_processed'] for r in rows),
              'critical_feature_count': sum(len(r['critical_features']) for r in rows),
              'unexplained_count': sum(len(r['unexplained']) for r in rows), 'items': rows,
              'scope': 'All registered source regions, program-generated whole-source survey and independently declared required content. Semantic discovery still depends on original observations.'}
    return result


def command(task, action, request=None):
    from . import agent_runtime as a
    from .common import writer
    task, state = a._state(task)
    with writer(task):
        if action == 'bind':
            result = bind(task, state, request or {})
        elif action == 'next':
            result = packet(task, state) or {'status': 'ORIGINAL_REGION_DISCOVERY_COMPLETE'}
        elif action == 'verify':
            initialize(task, state)
            result = report(task, state)
            path = task / 'source/recursion/checks' / (identity(result)+'.json')
            write_json(path, result)
            state['source_recursion_result'] = _ref(task, path)
        else:
            raise ValueError('Unknown recursion action')
        a._save(task, state)
    return result
