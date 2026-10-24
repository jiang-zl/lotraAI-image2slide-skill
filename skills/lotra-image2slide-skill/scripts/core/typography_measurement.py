"""Source-bound measurement plane and physical scale, independent of font choice."""
from .common import digest, identity, read_json, safe_path
from .typography_units import points_per_pixel, number

VERSION = 'typography-measurement-1.37.5'


def context(task, state, scene, frozen):
    if scene.get('typography_measurement') != frozen.get('typography_measurement'):
        raise ValueError('TYPOGRAPHY_MEASUREMENT_REBIND_REQUIRED: retain the source measurement basis')
    from .capture_target import verify
    capture = verify(task, state)
    record = read_json(safe_path(task, state['reconstruction_target']['path'])) if capture.get('applicable', True) else None
    # A projectively rectified target already owns its aspect authority and H.
    if record and record['plan']['kind'] == 'slide_surface':
        kind = 'rectified_plane'
        uncertainty = max(.5, record['propagated_source_uncertainty_px'])
        evidence = state['reconstruction_target']
    else:
        basis = scene.get('typography_measurement', {})
        if not isinstance(basis, dict):
            raise ValueError('TYPOGRAPHY_MEASUREMENT_BASIS_REQUIRED: source-bound measurement object')
        kind = basis.get('kind')
        if kind not in ('fronto_parallel', 'projected_appearance'):
            raise ValueError('TYPOGRAPHY_MEASUREMENT_BASIS_REQUIRED: declare fronto_parallel or projected_appearance with original evidence; a semantic crop does not rectify perspective')
        evidence = basis.get('evidence', {})
        file = safe_path(task, evidence.get('path', ''))
        if not file.is_file() or digest(file) != evidence.get('sha256'):
            raise ValueError('TYPOGRAPHY_MEASUREMENT_EVIDENCE_REQUIRED: current task-local source observation')
        observed = read_json(file)
        if (not isinstance(observed, dict) or observed.get('source_hash') != state['source']['sha256'] or
                observed.get('observer') not in ('host_model', 'human') or
                not observed.get('observations') or observed.get('measurement_kind') != kind):
            raise ValueError('TYPOGRAPHY_MEASUREMENT_EVIDENCE_REQUIRED: observed source plane and kind must agree')
        uncertainty = float(number(basis.get('source_uncertainty_px', .5)))
        if not .5 <= uncertainty <= 8:
            raise ValueError('TYPOGRAPHY_MEASUREMENT_UNCERTAINTY_REQUIRED: bounded source raster uncertainty')
    value = {'schema': VERSION, 'source_hash': state['source']['sha256'],
             'source_size': list(state['source_size']), 'kind': kind,
             'points_per_source_pixel': points_per_pixel(scene),
             'source_uncertainty_px': uncertainty, 'evidence': evidence,
             'reconstruction_target': state.get('reconstruction_target'),
             'historical_original_pt_identified': False,
             'scope': 'Size in the frozen output canvas; projected_appearance retains local photographic scale, not a rectified original size'}
    value['identity'] = identity(value)
    return value


def propose_samples(task, state, request, literal):
    """Reuse only a current cached OCR locator; source confirmation still required."""
    file = safe_path(task, 'source/ocr-descriptor.json')
    if not file.is_file():
        return []
    descriptor = read_json(file)
    if (descriptor.get('status') != 'SOURCE_OCR_CANDIDATE_ANCHORS' or
            descriptor.get('source_hash') != state['source']['sha256']):
        return []
    ref = {'path': descriptor['path'], 'sha256': descriptor['sha256']}
    anchors_file = safe_path(task, ref['path'])
    if digest(anchors_file) != ref['sha256']:
        raise ValueError('TYPOGRAPHY_OCR_CHANGED: cached original locator bytes changed')
    from .source_ocr import normalized_anchors
    anchors = normalized_anchors(read_json(anchors_file), state['source']['sha256'])
    ox, oy, ow, oh = request['roi']; result = []
    for line in anchors['lines']:
        for word in line['words']:
            text = word['text']; x, y, w, h = word['roi']
            if (not 2 <= len(text) <= 32 or text not in literal or
                    any(not char.isspace() and char not in request['characters'] for char in text) or
                    x < ox or y < oy or x+w > ox+ow or y+h > oy+oh):
                continue
            # Pad only inside the frozen owner. A tight OCR box is not an ink mask.
            left, top = max(ox, x-3), max(oy, y-3)
            right, bottom = min(ox+ow, x+w+3), min(oy+oh, y+h+3)
            result.append({'text': text, 'roi': [left, top, right-left, bottom-top],
                           'domain': 'task_source', 'ocr_ref': ref,
                           'status': 'SOURCE_LITERAL_AND_OWNERSHIP_CONFIRMATION_REQUIRED'})
            if len(result) == 4:
                return result
    return result
