"""One dependency closure; observing a dependency never grants writing it."""
from collections import defaultdict


TRANSFORMS = {'bbox', 'position', 'size', 'rotation', 'style.rotation',
              'bbox.left', 'bbox.top', 'bbox.width', 'bbox.height',
              'group_translate', 'replace_component', 'remove', 'geometry'}


def resolve(state, grants, *, scenes=(), parents=None):
    nodes = {o['id']: o for b in state.get('built', {}).values() for o in b.get('objects', [])}
    for scene in scenes:
        nodes.update({o['id']: o for o in scene.get('objects', [])})
    lineage = {n: o.get('parent') for n, o in nodes.items()}
    if parents is not None:
        lineage.update(parents)
    children = defaultdict(set)
    for name, parent in lineage.items():
        if parent:
            children[parent].add(name)
    direct = set(grants)
    subtree = set(direct)
    queue = [n for n in direct if set(grants[n]) & TRANSFORMS]
    while queue:
        for child in children[queue.pop()]:
            if child not in subtree:
                subtree.add(child); queue.append(child)
    ancestors = set()
    for name in subtree:
        seen = {name}; parent = lineage.get(name)
        while parent:
            if parent in seen:
                raise ValueError('Impact parent cycle: ' + name)
            seen.add(parent); ancestors.add(parent); parent = lineage.get(parent)
    observed = subtree | ancestors
    units = state.get('quality', {}).get('units', {})
    affected = {uid for uid, u in units.items() if observed & set(u.get('objects', []))}
    queue = list(affected)
    while queue:
        uid = queue.pop()
        owned = set(units[uid].get('objects', []))
        for peer, unit in units.items():
            links = set((unit.get('layering') or {}).get('occluders', []))
            links |= set((unit.get('relation') or {}).get('participants', []))
            reverse = set((units[uid].get('layering') or {}).get('occluders', []))
            if peer not in affected and (links & ({uid} | owned) or peer in reverse):
                affected.add(peer); queue.append(peer)
    return {'write': sorted(direct), 'direct': sorted(direct),
            'subtree': sorted(subtree), 'ancestors': sorted(ancestors),
            'observe': sorted(observed), 'units': sorted(affected)}


def touches(names, impact):
    return bool(set(names) & set(impact['observe']))
