"""Source-owned editable colour partitions with analytic container clipping."""
import math
from .recipes import node, path
from .source_contract import finite
from .source_preset_fit import clip_plane_to_ellipse


def construct(task, state, component, spec):
    finite(spec, 'container_function')
    if spec.get('source_hash') != state['source']['sha256'] or not spec.get('source_evidence'):
        raise ValueError('Container partitions require the unchanged original and located evidence')
    if spec.get('preset') != 'ellipse':
        raise ValueError('Use an implemented analytic container; do not approximate unsupported shapes')
    bbox = spec['bbox']
    if len(bbox) != 4 or min(bbox[2:]) <= 0:
        raise ValueError('Positive source-coordinate container extent required')
    x, y, w, h = bbox
    roi = component['roi']
    if x < roi[0] or y < roi[1] or x+w > roi[0]+roi[2] or y+h > roi[1]+roi[3]:
        raise ValueError('Analytic container escaped its original owner')
    cid = component['id']
    out = [node(cid, 'group', bbox, semantic=component['semantic_class'])]
    out.append(node(cid+'.base', 'shape', bbox, {'preset':'ellipse'}, cid,
                    'semantic_fill', fill=spec['base_colour'], stroke=None))
    clip = {'preset':'ellipse', 'bbox':bbox, 'source_evidence':spec['source_evidence'],
            'semantic_role':'continuous_background_plane', 'precision_px':.01, 'inset_px':.005}
    seen = {cid, cid+'.base'}
    parts = spec.get('partitions', [])
    if not parts or len(parts) > 128:
        raise ValueError('Explicit source colour-region/road inventory required')
    for part in parts:
        pid = cid+'.'+part['id']
        points = part['points']
        if pid in seen or len(points) < 3 or not part.get('source_evidence'):
            raise ValueError('Distinct located partitions with closed polygons required')
        if any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in points):
            raise ValueError('Finite source-coordinate polygon required')
        shape = path(pid, points, cid, None, part['colour'], 0, True,
                     part.get('semantic_role', 'semantic_fill'))
        out.append(clip_plane_to_ellipse(shape, clip));seen.add(pid)
    out.append(node(cid+'.outline', 'shape', bbox, {'preset':'ellipse'}, cid,
                    'container_outline', fill=None, stroke=spec.get('stroke','000000'),
                    line_width=spec.get('line_width',1)))
    return out
