"""Native authority, source facts and quality approval remain separate."""
import copy
from collections import Counter
from .common import read_json, safe_path, write_json, digest
from .impact_graph import resolve


def actual_name(state, name):
    if not isinstance(name, str): return name
    base, sep, cell = name.partition('@cell:')
    return state.get('native_aliases', {}).get(base, base) + (sep + cell if sep else '')


def native_contract(state, row):
    row = copy.deepcopy(row)
    if 'object' in row: row['object'] = actual_name(state, row['object'])
    if 'objects' in row: row['objects'] = [actual_name(state, n) for n in row['objects']]
    if 'container_body' in row: row['container_body'] = actual_name(state, row['container_body'])
    if 'source_bounds' in row: row['source_bounds'] = {actual_name(state, n): v for n, v in row['source_bounds'].items()}
    if 'roles' in row and all(isinstance(v, dict) for v in row['roles'].values()):
        row['roles'] = {actual_name(state, n): {r: actual_name(state, v) for r, v in roles.items()} for n, roles in row['roles'].items()}
    return row


def migrate(task, state, old, candidate):
    from .saved_components import inventory
    from .source_property_protection import snapshot_satisfaction
    before = inventory(safe_path(task, old['pptx']['path'])); after = inventory(safe_path(task, candidate['pptx']['path']))
    left = {r['shape_id']: r for r in before['objects']}; right = {r['shape_id']: r for r in after['objects']}
    counts = Counter(r['name'] for r in after['objects'])
    aliases = {}; changed = set(); ambiguous = []; reparented = []
    for sid, row in left.items():
        new = right.get(sid)
        if not new or new['kind'] != row['kind'] or counts[new['name']] != 1:
            changed.add(row['name']); ambiguous.append({'shape_id': sid, 'old': row['name'], 'new': new}); continue
        if new['name'] != row['name']: aliases[row['name']] = new['name']
        if new['parent_id'] != row['parent_id']: reparented.append(new['name'])
        if new['xml_hash'] != row['xml_hash'] or new['parent_id'] != row['parent_id']: changed.add(new['name'])
    added = [r for sid, r in right.items() if sid not in left]; changed.update(r['name'] for r in added)
    prior = state.setdefault('native_aliases', {})
    for original, native in list(prior.items()): prior[original] = aliases.get(native, native)
    prior.update(aliases)
    satisfaction = snapshot_satisfaction(state)
    old_scene = read_json(safe_path(task, old['scene']['path'])); scene = copy.deepcopy(old_scene)
    parents = {r['name']: right[r['parent_id']]['name'] if r['parent_id'] in right else None for r in right.values()}
    rows = {r['name']: r for r in right.values()}; scale = state['source_size'][0] / after['canvas_emu'][0]
    def remap(obj):
        obj['id'] = aliases.get(obj['id'], obj['id']); obj['parent'] = aliases.get(obj.get('parent'), obj.get('parent'))
        if obj['id'] in rows:
            obj['parent'] = parents[obj['id']]; obj['bbox'] = [v * scale for v in rows[obj['id']]['bbox_emu']]
    for obj in scene['objects']: remap(obj)
    for built in state.get('built', {}).values():
        for obj in built.get('objects', []): remap(obj)
        bindings = built.get('method', {}).get('source_bindings', {})
        for part, names in bindings.items(): bindings[part] = [aliases.get(n, n) for n in names]
    for relation in scene.get('relations', []):
        for key in ('source', 'target'): relation[key] = aliases.get(relation[key], relation[key])
    folder = safe_path(task, candidate['pptx']['path']).parent; file = folder / 'native-authority-scene.json'; write_json(file, scene)
    candidate['scene'] = {'path': file.relative_to(task).as_posix(), 'sha256': digest(file)}
    for unit in state.get('quality', {}).get('units', {}).values(): unit['objects'] = [aliases.get(n, n) for n in unit.get('objects', [])]
    impact = resolve(state, {n: ['geometry', 'group_translate', 'replace_component'] for n in changed}, scenes=[old_scene, scene])
    from .source_quality import invalidate
    invalidate(state, impact['observe'])
    for uid in impact['units']: state.get('quality', {}).get('satisfactory_native_properties', {}).pop(uid, None)
    ledger = state.get('semantic_composition', {}); ledger['environment_epoch'] = ledger.get('environment_epoch', 0) + 1
    ledger.pop('actual_host_context', None); ledger.pop('actual_host_contexts',None)
    for field in ('semantic_composition_guard', 'semantic_composition_actual', 'relative_layout_guard', 'relative_layout_actual', 'textbox_guard', 'textbox_actual', 'adoption_gate'): candidate.pop(field, None)
    candidate['authority_status'] = 'USER_ADOPTED_QUALITY_PENDING'
    record = {'schema': 'native-sync-1', 'before': old['pptx'], 'before_candidate':old, 'after': candidate['pptx'], 'aliases': aliases,
              'changed': sorted(changed), 'added': added, 'ambiguous': ambiguous, 'reparented': reparented,
              'impact': impact, 'affected_units': impact['units'], 'satisfaction': satisfaction,
              'status': 'binding_pending' if ambiguous or added or reparented else 'intent_pending'}
    file = folder / 'sync-migration.json'; write_json(file, record)
    state['external_reconciliation'] = {'path': file.relative_to(task).as_posix(), 'sha256': digest(file)}
    return record


def packet(task, state):
    record = read_json(safe_path(task, state['external_reconciliation']['path']))
    return {'migration': state['external_reconciliation'], 'changed_native': record['changed'][:8],
            'remaining': max(0, len(record['changed'])-8), 'affected_units': record['affected_units'][:8],
            'unresolved_bindings': record['ambiguous'][:4], 'reparented': record['reparented'][:8],
            'return': 'intent_resolution:source_compatible|intent_changed|unresolved; user_intent{reference,text} when changed. Original source stays immutable; resolve changed semantic bindings explicitly.'}


def reconcile(task, state, result):
    record = read_json(safe_path(task, state['external_reconciliation']['path'])); choice = result.get('intent_resolution')
    if choice not in ('source_compatible', 'intent_changed', 'unresolved'): raise ValueError('State actual user intent; sync is not quality approval')
    if choice != 'source_compatible':
        intent = result.get('user_intent', {})
        if choice == 'intent_changed' and not all(intent.get(k) for k in ('reference', 'text')): raise ValueError('Record the actual user request before changing expectations')
        state.setdefault('user_intent_versions', []).append({'candidate': state['selected']['pptx'], 'intent': intent, 'resolution': choice})
        state['stage'] = 'user_intent_pending'; return
    if record['ambiguous'] or record['added'] or record['reparented']: raise ValueError('Resolve semantic/native bindings before source-compatible continuation')
    from .semantic_composition import guard_saved
    candidate = state['selected']; candidate['semantic_composition_guard'] = guard_saved(task, state, safe_path(task, candidate['pptx']['path']))
    candidate['reason']={'kind':'external_reconciled'}
    if candidate.get('preview'):
        from .source_quality import _actual_pixel_dependencies, invalidate
        from .source_property_protection import preserve_satisfaction
        dependencies=_actual_pixel_dependencies(task,state,record['before_candidate'],candidate,set(record['affected_units']))
        for uid in dependencies:
            state['quality']['units'][uid]['status']='required_unmeasured';state['quality']['observations'].pop(uid,None)
        record['affected_units']=sorted(set(record['affected_units'])|dependencies)
        preserve_satisfaction(task,state,record['before_candidate'],candidate,record['satisfaction'])
    state['active_candidate'] = candidate; state['review_queue'] = ['quality:' + uid for uid in record['affected_units']]
    state['stage'] = 'host_render' if candidate['semantic_composition_guard'].get('capture_request') else 'review'
    candidate['authority_status'] = 'USER_ADOPTED_MEASUREMENT_PENDING'
