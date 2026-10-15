"""Stable field addresses shared by grants, journals, locks and native planning."""
import copy


def differences(before, after, path=(), *, before_exists=True, after_exists=True):
    """Presence is independent of value, including explicit JSON nulls."""
    if not before_exists or not after_exists:
        if before_exists != after_exists:
            yield {'field':list(path),'before_exists':before_exists,'after_exists':after_exists,
                   'before':before,'after':after}
        return
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            if key not in before or key not in after:
                yield {'field': list(path+(key,)), 'before_exists': key in before,
                       'after_exists': key in after, 'before': before.get(key), 'after': after.get(key)}
            else:
                yield from differences(before[key], after[key], path+(key,))
    elif isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        for index, (a, b) in enumerate(zip(before, after)):
            yield from differences(a, b, path+(index,))
    elif before != after:
        yield {'field': list(path), 'before_exists': True,
               'after_exists': True, 'before': before, 'after': after}


def contains(grant, field):
    return field[:len(grant)] == grant


def lookup(node, path):
    try:
        for key in path:node = node[key]
        return True, node
    except (KeyError, IndexError, TypeError):
        return False, None


def native_fields(before, after, patches, whole=False):
    if before is None:return ['add']
    if after is None:return ['remove']
    if before['render_type'] != after['render_type']:
        if not whole:raise ValueError('Type replacement needs a whole-owner grant')
        return ['replace_component']
    kind = after['render_type']; result = set()
    for patch in patches:
        path = patch['field']
        if not path:
            if not whole:raise ValueError('Whole-owner reconstruction needs a whole-owner grant')
            return ['replace_component']
        if path[0] == 'bbox' and len(path) == 2:
            result.add(['bbox.left', 'bbox.top', 'bbox.width', 'bbox.height'][path[1]])
        elif path[0] == 'parent':result.add('reparent')
        elif path[0] == 'z_order':result.add('paint_order')
        elif path[0] == 'style' and len(path) >= 2:
            result.add('style.font' if path[1] == 'font_faces' else 'style.'+path[1])
        elif path[0] == 'content':
            if path[1:2] == ['native_snapshot']:continue
            if kind == 'text':
                if len(path) >= 2 and path[1] == 'text':result.add('text_content')
                else:result.add('text_body')
            elif kind == 'equation':result.add('equation')
            elif kind == 'connector':result.add('connector')
            elif kind in ('shape', 'path', 'bezier'):result.add('geometry')
            elif kind == 'photo':result.add('photo_resource')
            elif kind == 'trace':return ['replace_component']
            elif kind == 'table' and path[1:2] == ['rows']:result.add('table_text')
            elif kind == 'table' and path[1:2] == ['cell_styles']:
                if len(path) >= 4:result.add('table_cell_format.'+str(path[2])+'.'+str(path[3]))
                elif whole:return ['replace_component']
                else:raise ValueError('Locate native cell formatting before repair')
            elif whole:return ['replace_component']
            else:raise ValueError('Dedicated whole-component authority required')
        elif path[0] in ('semantic_type',):continue
        elif whole:return ['replace_component']
        else:raise ValueError('Unsupported scoped native field: '+repr(path))
    return sorted(result)


def canonical_node(node):
    """Compiled font faces and snapshot receipts are resources, not source hints."""
    from .tables import normalize_node
    node = normalize_node(node)
    node.get('content', {}).pop('native_snapshot', None)
    def clean(value):
        if isinstance(value, dict):
            value.pop('font_faces', None)
            for item in value.values():clean(item)
        elif isinstance(value, list):
            for item in value:clean(item)
    clean(node)
    return node
