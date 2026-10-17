"""Source-bound local measurements with no candidate alignment or global run."""
import math
import numpy as np
from scipy.ndimage import distance_transform_edt
from .common import safe_path, digest


def window(roi, size):
    if len(roi) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in roi):
        raise ValueError('Finite original ROI required')
    x, y, w, h = roi
    if min(x, y) < 0 or min(w, h) <= 0 or x+w > size[0]+1 or y+h > size[1]+1:
        raise ValueError('Local ROI outside original')
    return [math.floor(x), math.floor(y), min(size[0], math.ceil(x+w)), min(size[1], math.ceil(y+h))]


def boundary_distances(source, actual, support=None):
    from .adaptive_detail import _edges
    a, b = _edges(source), _edges(actual)
    if support is not None: a &= support; b &= support
    if not a.any() or not b.any():
        return {'valid': False, 'reason': 'No independently measurable pair of boundaries'}
    distances = np.concatenate((distance_transform_edt(~b)[a], distance_transform_edt(~a)[b]))
    return {'valid': True, 'mean': float(np.mean(distances)),
            'p95': float(np.percentile(distances, 95)), 'max': float(np.max(distances)),
            'unit': 'source_px'}


def arrays(original, actual, mask=None):
    """Only supported pixels contribute; excluded context never earns credit."""
    from .appearance_metrics import image_values
    raw = image_values(original, actual)
    if mask is not None:
        from scipy.ndimage import binary_erosion, gaussian_filter, laplace
        from skimage.metrics import structural_similarity
        from .typed_metrics import color_histogram
        raw['mean_absolute_rgb_error'] = float(np.abs(original[mask]-actual[mask]).mean())
        for key, mode in (('color_histogram_tv','trilinear'), ('raw_hard_color_histogram_tv','hard')):
            hist = [color_histogram(data[mask],8,mode) for data in (original,actual)]
            hist = [h/max(1,h.sum()) for h in hist]
            raw[key] = float(np.abs(hist[0]-hist[1]).sum()/2)
        interior = binary_erosion(mask, iterations=3, border_value=0)
        if min(original.shape[:2]) >= 7 and interior.any():
            _, values = structural_similarity(original,actual,data_range=1.,channel_axis=2,win_size=7,full=True)
            raw['ssim'] = float(values[interior].mean())
        else: raw['ssim'] = None
        clarity = [float((laplace(gaussian_filter(data@np.array([.2126,.7152,.0722]),.35))**2)[mask].mean()) for data in (original,actual)]
        raw.update(clarity_first=clarity[0],clarity_second=clarity[1],
                   clarity_ratio=clarity[1]/clarity[0] if clarity[0]>1e-12 else None)
        # Full-window F1 has a different denominator and is not an owned metric.
        raw['boundary_f1'] = None
    boundary = boundary_distances(original,actual,mask)
    values = {key: {'valid': value is not None and isinstance(value,(int,float)) and math.isfinite(value),
                    'value':value} for key,value in raw.items() if isinstance(value,(int,float)) or value is None}
    for name in ('mean','p95','max'):
        values['boundary_distance_'+name]={'valid':boundary['valid'],'value':boundary.get(name)}
    values['ssim_loss']={'valid':raw.get('ssim') is not None,'value':1-raw['ssim'] if raw.get('ssim') is not None else None}
    return values,boundary


def measure(task, state, candidate, component):
    from .spatial_fit import is_spatial, measured
    if is_spatial(component):
        from .component_workflow import _load
        contract,_ = _load(task,state)
        return measured(task,state,candidate,contract,component)
    from .appearance_metrics import canvas
    source_ref, preview_ref = state['source'], candidate.get('preview')
    if not preview_ref: return {'hard_checks': {'actual_preview': False}, 'metrics': {}}
    size = tuple(state['source_size']); box = window(component['roi'], size)
    original = canvas(str(safe_path(task, source_ref['path'])), source_ref['sha256'], size)
    actual = canvas(str(safe_path(task, preview_ref['path'])), preview_ref['sha256'], size)
    x, y, r, b = box; original, actual = original[y:b, x:r], actual[y:b, x:r]
    support = component.get('support_mask'); mask = None
    if support:
        from PIL import Image
        file = safe_path(task, support['path'])
        if digest(file) != support['sha256']: raise ValueError('Original ownership mask changed')
        mask = np.asarray(Image.open(file).convert('L')) > 0
        if mask.shape != original.shape[:2] or mask.sum() < 16:
            raise ValueError('Independent nonempty original ownership support required')
    values,boundary=arrays(original,actual,mask)
    from .component_metric_adapters import geometric
    values.update(geometric(actual,component,mask,original))
    from .curve_functions import actual_checks
    hard={'actual_preview': True, 'source_bound_window': True,**actual_checks(actual,component)}
    return {'hard_checks': hard, 'metrics': values,
            'source_hash': source_ref['sha256'], 'preview_hash': preview_ref['sha256'],
            'roi': component['roi'], 'boundary': boundary,
            'limits': 'Local diagnostics/declared targets only; no semantic or whole acceptance claim.'}
