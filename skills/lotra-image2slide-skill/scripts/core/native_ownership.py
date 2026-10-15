"""One ownership expansion for semantic owners and compiler-owned trace layers."""
from .common import read_json, safe_path, digest


def expanded(scene, base):
    result = {node['id']: node.get('parent') for node in scene['objects']}
    for node in scene['objects']:
        if node['render_type'] != 'trace':
            continue
        ref = node['content']['geometry_ref']
        file = safe_path(base, ref['path'])
        if digest(file) != ref['sha256']:
            raise ValueError('Trace geometry identity changed')
        geometry = read_json(file)
        for index, layer in enumerate(geometry['layers']):
            name = node['id'] + '.tone-' + str(index)
            if name in result:
                raise ValueError('Compiler trace layer collides with a semantic owner')
            result[name] = node['id']
    return result


def check(scene, base, native):
    expected = expanded(scene, base)
    wrong = [name for name in set(expected) & set(native)
             if native[name]['parent'] != expected[name]]
    return {'passed': set(expected) == set(native) and not wrong,
            'missing': sorted(set(expected) - set(native)),
            'unexpected': sorted(set(native) - set(expected)), 'wrong_parent': wrong,
            'native_objects': len(native)}
