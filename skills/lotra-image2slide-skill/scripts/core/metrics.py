"""Raw, deterministic metrics. No calibration is inferred from current candidates."""

import math
import numpy as np


def cer(reference, candidate):
    if reference is None or candidate is None:
        return None
    if not reference:
        return None
    last = list(range(len(candidate)+1))
    for i, a in enumerate(reference, 1):
        current = [i]
        for j, b in enumerate(candidate, 1):
            current.append(min(current[-1]+1, last[j]+1, last[j-1]+(a != b)))
        last = current
    return last[-1] / len(reference)


def iou(a, b):
    a, b = np.asarray(a, dtype=bool), np.asarray(b, dtype=bool)
    if a.shape != b.shape or not a.size:
        raise ValueError("Metric inputs need identical nonempty dimensions")
    union = np.count_nonzero(a | b)
    return float(np.count_nonzero(a & b) / union) if union else None


def foreground(image, threshold=245):
    data = np.asarray(image.convert("RGB"))
    return np.any(data < threshold, axis=2)


def chamfer(a, b, reference_diagonal):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if not len(a) or not len(b):
        return None
    if a.ndim != 2 or b.ndim != 2 or a.shape[1] != 2 or b.shape[1] != 2 or reference_diagonal <= 0:
        raise ValueError("Invalid boundary points/reference diagonal")
    if len(a)*len(b) > 40_000_000:
        raise TimeoutError("Chamfer pairwise work exceeds deterministic resource guard")
    def mean_nearest(x, y):
        return sum(float(np.sqrt(((x[i:i+128, None]-y[None])**2).sum(axis=2)).min(axis=1).sum()) for i in range(0, len(x), 128)) / len(x)
    return (mean_nearest(a, b)+mean_nearest(b, a))/(2*reference_diagonal)


def layout(reference, candidate, relations, width, height):
    if not reference or set(reference) != set(candidate):
        return {"absolute_center_error": None, "relative_error": None, "missing_objects": sorted(set(reference)-set(candidate))}
    def center(box):
        return np.array([(box[0]+box[2]/2)/width, (box[1]+box[3]/2)/height])
    ref, cand = {k:center(v) for k,v in reference.items()}, {k:center(v) for k,v in candidate.items()}
    absolute = float(np.mean([np.linalg.norm(ref[k]-cand[k]) for k in ref]))
    relative = float(np.mean([np.linalg.norm((ref[a]-ref[b])-(cand[a]-cand[b])) for a,b in relations])) if relations else None
    return {"absolute_center_error": absolute, "relative_error": relative}


def balance(image):
    contrast = 1 - np.asarray(image.convert("RGB"), dtype=float).mean(axis=2)/255
    mass = contrast.sum()
    if not mass:
        return None
    h, w = contrast.shape
    return [float((contrast.sum(axis=0)*((np.arange(w)+.5)/w)).sum()/mass),
            float((contrast.sum(axis=1)*((np.arange(h)+.5)/h)).sum()/mass)]


def render_canvas_mapping(source_size, render_size):
    """Allow only adjacent-integer quantization of width-fixed raster exports.

    A 1280 x 594 slide exported at width 1600 has ideal height 742.5;
    Office legitimately produces 743 pixels. A measured 767 x 599 source also
    exported as 1600 x 1249 (ideal 1249.5437), despite the bridge requesting a
    rounded height. Thus the actual renderer may choose floor or ceiling.
    Exact aspect equality would reject these renders. This permits no padding,
    extra full pixel, registration, arbitrary
    aspect tolerances, or resizing separate objects to hide placement errors.
    """
    if any(type(v) is not int or v <= 0 for v in (*source_size, *render_size)):
        raise ValueError('Canvas dimensions must be positive integer pixels')
    if len(source_size) != 2 or len(render_size) != 2:
        raise ValueError('Canvas dimensions must have width and height')
    width, height = source_size
    actual_width, actual_height = render_size
    ideal_height = actual_width * height / width
    residual = actual_height - ideal_height
    import math
    adjacent={math.floor(ideal_height),math.ceil(ideal_height)}
    if actual_height not in adjacent:
        raise ValueError('Source/render canvas mismatch beyond raster rounding')
    return {'source_pixels': list(source_size), 'render_pixels': list(render_size),
            'ideal_render_height': ideal_height, 'height_rounding_pixels': residual,
            'allowed_render_heights':sorted(adjacent),
            'quantization':'adjacent_integer_only', 'local_registration': 'none'}


def aesthetic(profile, dimensions):
    weights = profile["global_aesthetic"]["weights"]
    if weights != {"layout":.25,"visual_balance":.15,"alignment_spacing":.20,"layer_occlusion":.10,"color_style":.10,"readability":.20}:
        raise ValueError("User's six global weights changed")
    if any(dimensions.get(k) is None for k in weights):
        return {"score": None, "status": "UNVERIFIED", "reason": "Missing dimension measurement"}
    if any(not math.isfinite(dimensions[k]) or not 0 <= dimensions[k] <= 1 for k in weights):
        raise ValueError("Invalid normalized dimension")
    score = sum(weights[k]*dimensions[k] for k in weights)
    config = profile["global_aesthetic"]
    if profile["status"] != "calibrated" or config["overall_threshold"] is None or any(v is None for v in config["dimension_floors"].values()):
        return {"score": score, "status": "UNVERIFIED", "reason": "Uncalibrated; exploratory score only"}
    passed = score >= config["overall_threshold"] and all(dimensions[k] >= config["dimension_floors"][k] for k in weights)
    return {"score": score, "status": "PASS" if passed else "FAIL"}
