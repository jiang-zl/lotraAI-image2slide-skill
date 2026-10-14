"""Component-level editability and stable, typed quality priorities.

Profiles are decision aids, not calibrated claims of perceptual correctness.
Actual source/result observations and protected properties remain mandatory.
"""
import math

VERSION = 'quality-policy-1'
LEVELS = {'component': 1, 'parts': 2, 'geometry': 3}
REPRESENTATIONS = {'native', 'svg', 'raster'}
FAMILY_METRICS = {
    'solid_icon': ['foreground_iou', 'edge_chamfer', 'colour_error', 'material_contrast', 'ssim'],
    'illustration': ['ssim', 'edge_chamfer', 'gradient_continuity', 'colour_error', 'texture_energy'],
    'scene': ['foreground_iou', 'edge_chamfer', 'colour_error', 'ssim', 'texture_energy'],
    'academic': ['edge_chamfer', 'foreground_iou', 'ssim'],
}


def profile(component):
    kind = component.get('semantic_class', '').lower()
    role = component.get('paint_role', '')
    if any(k in kind for k in ('timeline','architecture','federated','warning_explanation','caption','record_database','conflict','planner','prediction')):
        family = 'academic'
    elif any(k in kind for k in ('camera', 'server', 'vehicle', 'terminal', 'sensor', 'uav', 'device')):
        family = 'solid_icon'
    elif role == 'illustration' or any(k in kind for k in ('portrait', 'artwork', 'painting', 'face')):
        family = 'illustration'
    elif role == 'background' or any(k in kind for k in ('terrain', 'city', 'scene', 'landscape')):
        family = 'scene'
    else:
        family = 'academic'
    requested = component.get('quality_profile', {})
    level = requested.get('edit_level', 'component')
    if level not in LEVELS:
        raise ValueError('Unknown semantic edit level')
    focus = requested.get('metric_focus', FAMILY_METRICS[family])
    if not isinstance(focus, list) or not focus or len(focus) > 10:
        raise ValueError('A bounded component metric focus is required')
    important = requested.get('important_properties', component.get('parts', []))
    return {'version': VERSION, 'family': family, 'edit_level': level,
            'metric_focus': focus, 'important_properties': important,
            'hard_gates': ['scientific_meaning', 'semantic_component_independence', 'authorized_preservation'],
            'selection': 'important observed quality gain; near-ties prefer vector and then finer edits and lower cost',
            'raster_requires': 'bound local comparison with substantial important quality gain and no key regression',
            'cost_focus':['zip_bytes','uncompressed_slide_bytes','path_commands','preview_bytes','program_seconds'],
            'calibration': 'source-specific diagnostic profile; no universal pass score'}


def compare(baseline, candidate, weights, *, protected=(), min_gain=.06, tolerance=.015):
    """Compare same-profile observed scores; missing metrics never become zero/full.

    Host semantic scores must be accompanied by the bound actual observations at
    the caller. This function only makes their non-compensating arithmetic.
    """
    if not weights or any(k not in baseline or k not in candidate for k in weights):
        return {'decision': 'unmeasured', 'reason': 'required paired measurements missing'}
    for record in (baseline, candidate):
        if any(not isinstance(record[k], (int, float)) or not math.isfinite(record[k])
               or not 0 <= record[k] <= 1 for k in weights):
            raise ValueError('Comparable quality scores must be finite in [0,1]')
    total = sum(weights.values())
    if total <= 0 or any(v <= 0 for v in weights.values()):
        raise ValueError('Positive stable quality weights required')
    delta = {k: candidate[k] - baseline[k] for k in weights}
    regressions = [k for k in protected if k not in delta or delta[k] < -tolerance]
    gain = sum(weights[k]*delta[k] for k in weights)/total
    return {'decision': 'reject' if regressions else 'substantial_gain' if gain >= min_gain
            else 'gain' if gain > tolerance else 'near_tie' if gain >= -tolerance else 'reject',
            'weighted_delta': gain, 'deltas': delta, 'regressions': regressions,
            'thresholds': {'substantial_gain': min_gain, 'tolerance': tolerance},
            'limits': 'profile thresholds are task choices; semantic and protection gates are separate'}


def measure(reference, output):
    """Cheap ROI diagnostics, at registered size; not aesthetic/semantic ground truth."""
    import numpy as np
    from scipy.ndimage import sobel, distance_transform_edt, gaussian_filter
    a, b = np.asarray(reference.convert('RGB'), dtype=float), np.asarray(output.convert('RGB'), dtype=float)
    if a.shape != b.shape:
        raise ValueError('ROI comparison requires registered image sizes')
    ga, gb = a.mean(2), b.mean(2)
    ea = np.hypot(sobel(ga, 0)/8, sobel(ga, 1)/8)
    eb = np.hypot(sobel(gb, 0)/8, sobel(gb, 1)/8)
    threshold = max(8., float(np.percentile(ea, 75)))
    ma, mb = ea > threshold, eb > threshold
    diagonal = max(1., math.hypot(*ga.shape))
    chamfer = None
    if ma.any() and mb.any():
        chamfer = float((distance_transform_edt(~mb)[ma].mean()
                         + distance_transform_edt(~ma)[mb].mean())/(2*diagonal))
    # A near-white reference canvas is a useful icon mask, not a scene segmenter.
    fa, fb = np.min(a, 2) < 245, np.min(b, 2) < 245
    union = np.count_nonzero(fa | fb)
    smoothed = gaussian_filter(gb, 1.)
    curvature = np.hypot(sobel(sobel(smoothed, 0), 0), sobel(sobel(smoothed, 1), 1))
    def spectrum(gray):
        fy=np.fft.fftfreq(gray.shape[0])[:,None];fx=np.fft.rfftfreq(gray.shape[1])[None,:]
        radius=np.hypot(fy,fx);power=np.abs(np.fft.rfft2(gray-gray.mean()))**2
        total=max(1.,float(power.sum()))
        return [float(power[(radius>=lo)&(radius<hi)].sum()/total) for lo,hi in ((0,.08),(.08,.2),(.2,.72))]
    return {'foreground_iou': float(np.count_nonzero(fa & fb)/union) if union else None,
            'edge_chamfer': chamfer,
            'colour_error': float(np.abs(a.mean((0, 1))-b.mean((0, 1))).mean()/255),
            'material_contrast': {'source': float(ga.std()/255), 'output': float(gb.std()/255)},
            'texture_energy': {'source': float(ea.mean()), 'output': float(eb.mean())},
            'gradient_continuity': float(np.mean(curvature)),
            'frequency_energy':{'source':spectrum(ga),'output':spectrum(gb),'bands_cycles_per_pixel':[.08,.2,.72]},
            'limits': 'white-mask IoU is conditional; curvature/contrast/texture are descriptive, not monotonic quality'}
