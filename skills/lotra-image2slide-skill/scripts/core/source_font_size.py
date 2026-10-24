"""Bounded physical-font raster fitting on a half-point grid; no free rescaling."""
import math
import statistics
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_erosion, distance_transform_edt
from .common import digest
from .typography_units import half_point

VERSION = 'physical-face-finite-size-1.37.5'
MAX_CANDIDATES = 17
SUPERSAMPLE = 4


def source_ink(image, sample):
    roi = sample['roi']
    if (not isinstance(roi, (list, tuple)) or len(roi) != 4 or
            any(type(value) not in (int, float) or not np.isfinite(value) for value in roi)):
        raise ValueError('TYPOGRAPHY_SAMPLE_REQUIRED: finite isolated original ROI')
    x, y, w, h = roi
    if (x < 0 or y < 0 or min(w, h) < 2 or w > 2048 or h > 512 or
            w*h > 524288 or x+w > image.width or y+h > image.height):
        raise ValueError('TYPOGRAPHY_SAMPLE_REQUIRED: bounded original glyph/phrase inside the source')
    if sample.get('domain', 'task_source') != 'task_source':
        raise ValueError('TYPOGRAPHY_SAMPLE_DOMAIN_REQUIRED: use mapped task-source coordinates, never an OCR-normalized crop')
    pixels = np.asarray(image.crop((math.floor(x), math.floor(y), math.ceil(x+w), math.ceil(y+h))).convert('RGB'), float)/255
    height, width = pixels.shape[:2]
    yy, xx = np.indices((height, width))
    design = np.stack((np.ones_like(xx), xx/max(1, width-1), yy/max(1, height-1)), axis=-1)
    border = (xx == 0) | (yy == 0) | (xx == width-1) | (yy == height-1)
    # A plane handles gentle capture illumination without painting over source ink.
    coefficients = np.linalg.lstsq(design[border], pixels[border], rcond=None)[0]
    background = np.clip(design @ coefficients, 0, 1)
    difference = np.linalg.norm(pixels-background, axis=2)
    noise = float(np.quantile(difference[border], .9))
    if noise > .12:
        raise ValueError('TYPOGRAPHY_SAMPLE_ISOLATION_REQUIRED: source border is not stable enough to isolate ink')
    foreground = difference[difference > max(.08, noise*3)]
    if len(foreground) < 4:
        raise ValueError('TYPOGRAPHY_SAMPLE_ISOLATION_REQUIRED: source contrast does not identify ink')
    contrast = float(np.quantile(foreground, .9))
    threshold = max(noise*3+.02, contrast*.5)
    mask = difference > threshold
    ys, xs = np.nonzero(mask)
    if (len(xs) < 4 or xs.min() == 0 or ys.min() == 0 or
            xs.max() == width-1 or ys.max() == height-1):
        raise ValueError('TYPOGRAPHY_SAMPLE_ISOLATION_REQUIRED: clipped or missing original ink')
    box = [int(xs.min()), int(ys.min()), int(xs.max()+1), int(ys.max()+1)]
    return mask[box[1]:box[3], box[0]:box[2]], {'roi': list(roi), 'ink_box_in_roi': box,
            'ink_size_px': [box[2]-box[0], box[3]-box[1]], 'border_noise': noise, 'threshold': threshold}


def render_ink(resource, text, size_pt, scale, *, bold=False, italic=False, tracking_pt=0, raster_scale=SUPERSAMPLE):
    em = max(1., size_pt/scale*raster_scale)
    font = ImageFont.truetype(resource['path'], size=em, index=resource['face_index'])
    box = font.getbbox(text)
    stroke = max(0, round(em*.02)) if bold and resource['weight'] < 600 else 0
    extra = max(0, math.ceil(abs(tracking_pt/scale)*raster_scale*max(0, len(text)-1)))
    width, height = box[2]-box[0]+16+2*stroke+extra, box[3]-box[1]+16+2*stroke
    if width > 16384 or height > 4096 or width*height > 16000000:
        raise ValueError('TYPOGRAPHY_RASTER_BOUND_REACHED: use a shorter independently observed phrase')
    image = Image.new('L', (max(raster_scale, math.ceil(width/raster_scale)*raster_scale),
                            max(raster_scale, math.ceil(height/raster_scale)*raster_scale)))
    draw = ImageDraw.Draw(image)
    if tracking_pt:
        # Preserve actual kerning where tracking is zero; explicit tracking is fixed.
        cursor = 8+stroke-box[0]
        for char in text:
            draw.text((cursor, 8+stroke-box[1]), char, font=font, fill=255, stroke_width=stroke)
            cursor += font.getlength(char)+tracking_pt/scale*raster_scale
    else:
        draw.text((8+stroke-box[0], 8+stroke-box[1]), text, font=font, fill=255, stroke_width=stroke)
    if italic and not resource['italic']:
        slant = .22; width = image.width+math.ceil(image.height*slant)
        image = image.transform((width, image.height), Image.Transform.AFFINE,
                                (1, -slant, image.height*slant, 0, 1, 0),
                                resample=Image.Resampling.BICUBIC)
    # Fixed physical scale for every candidate. No size-normalized glyph canvas.
    image = image.resize((max(1, round(image.width/raster_scale)),
                          max(1, round(image.height/raster_scale))), Image.Resampling.LANCZOS)
    mask = np.asarray(image) >= 128
    ys, xs = np.nonzero(mask)
    if len(xs) < 4:
        raise ValueError('TYPOGRAPHY_RASTER_UNRESOLVED: insufficient physical glyph pixels')
    return mask[ys.min():ys.max()+1, xs.min():xs.max()+1]


def compare(expected, actual):
    height = max(expected.shape[0], actual.shape[0])+4
    width = max(expected.shape[1], actual.shape[1])+4
    first = np.zeros((height, width), bool); second = first.copy()
    # Both use the independently observed ink top-left. Translation is not fitted.
    first[2:2+expected.shape[0], 2:2+expected.shape[1]] = expected
    second[2:2+actual.shape[0], 2:2+actual.shape[1]] = actual
    a = first & ~binary_erosion(first); b = second & ~binary_erosion(second)
    boundary = max(float(distance_transform_edt(~a)[b].mean()),
                   float(distance_transform_edt(~b)[a].mean()))
    mismatch = float(np.logical_xor(first, second).sum()/max(1, np.logical_or(first, second).sum()))
    dimensions = [abs(expected.shape[1]-actual.shape[1]), abs(expected.shape[0]-actual.shape[0])]
    return {'extent_error_px': dimensions, 'boundary_mean_px': boundary, 'ink_disagreement': mismatch}


def fit(image, samples, resource, scale, uncertainty_px=.5, style=None):
    style = style or {}
    path = Path(resource['path'])
    if digest(path) != resource['file_sha256']:
        raise ValueError('TYPOGRAPHY_FONT_CHANGED: physical face needs rebinding')
    if not 1 <= len(samples) <= 12 or not np.isfinite(scale) or scale <= 0:
        raise ValueError('TYPOGRAPHY_SAMPLE_REQUIRED: one to twelve bounded source samples and physical scale')
    rows = []; estimates = []
    for sample in samples:
        text = sample.get('text', sample.get('character', ''))
        if not isinstance(text, str) or not text.strip() or len(text) > 32 or '\n' in text:
            raise ValueError('TYPOGRAPHY_SAMPLE_REQUIRED: one glyph or a single-line phrase up to 32 characters')
        mask, observation = source_ink(image, sample)
        # Both sides use actual painted ink. getbbox() may include advance or
        # bearings and cannot be compared directly with a tight source mask.
        seed = render_ink(resource, text, 256*scale, scale, raster_scale=1,
                          bold=bool(style.get('bold')), italic=bool(style.get('italic')))
        approx = [mask.shape[1]*256/seed.shape[1]*scale,
                  mask.shape[0]*256/seed.shape[0]*scale]
        estimates.extend(approx[1:] if style.get('char_spacing_pt') else approx)
        rows.append({'text': text, 'observation': observation, 'initial_estimates_pt': approx, 'mask': mask})
    center = half_point(statistics.median(estimates))
    if not .5 <= center <= 256:
        raise ValueError('TYPOGRAPHY_SIZE_DOMAIN_REQUIRED: supported source size is 0.5..256 pt')
    sizes = [center+step*.5 for step in range(-8, 9) if .5 <= center+step*.5 <= 256]
    candidates = []; rejected_modes = []
    for size in sizes:
        modes = []
        for raster_scale in (1, SUPERSAMPLE):
            metrics = []
            for row in rows:
                try:
                    ink = render_ink(resource, row['text'], size, scale, bold=bool(style.get('bold')),
                                     italic=bool(style.get('italic')), tracking_pt=style.get('char_spacing_pt', 0),
                                     raster_scale=raster_scale)
                except ValueError as error:
                    if not str(error).startswith(('TYPOGRAPHY_RASTER_UNRESOLVED', 'TYPOGRAPHY_RASTER_BOUND_REACHED')):
                        raise
                    rejected_modes.append({'font_size_pt': size, 'raster_scale': raster_scale, 'reason': str(error)})
                    metrics = []; break
                metrics.append(compare(row['mask'], ink))
            if not metrics: continue
            # One raster mode serves all samples; no per-glyph model shopping.
            error = max(max(metric['extent_error_px']) for metric in metrics)
            boundary = max(metric['boundary_mean_px'] for metric in metrics)
            mismatch = statistics.mean(metric['ink_disagreement'] for metric in metrics)
            modes.append({'font_size_pt': size, 'extent_error_px': error,
                          'boundary_mean_px': boundary, 'ink_disagreement': mismatch,
                          'raster_scale': raster_scale, 'samples': metrics})
        if modes:
            candidates.append(min(modes, key=lambda row: (row['extent_error_px'], row['boundary_mean_px'], row['ink_disagreement'])))
    if not candidates:
        raise ValueError('TYPOGRAPHY_RASTER_UNRESOLVED: no finite physical-size candidate has measurable ink')
    candidates.sort(key=lambda row: (row['extent_error_px'], row['boundary_mean_px'], row['ink_disagreement'], row['font_size_pt']))
    best = candidates[0]
    # This screen diagnoses ambiguity; it does not calibrate a statistical confidence.
    resolution = max(.5, float(uncertainty_px))
    # Source uncertainty describes one mapped edge, not a two-edge extent.
    # Candidate raster bounds add a half-pixel quantization at each edge.
    # Propagate the two intervals; do not substitute this screening budget for
    # any frozen original/native appearance limit.
    edge_budget = resolution+.5
    extent_budget = 2*edge_budget
    plausible = [row['font_size_pt'] for row in candidates
                 if row['extent_error_px'] <= extent_budget and row['boundary_mean_px'] <= edge_budget]
    status = 'IDENTIFIED' if len(plausible) == 1 else 'AMBIGUOUS' if plausible else 'NO_SUPPORTED_SIZE'
    if best['font_size_pt'] in (sizes[0], sizes[-1]) and status == 'NO_SUPPORTED_SIZE':
        status = 'SEARCH_BOUND_REACHED'
    for row in rows:
        row.pop('mask')
    return {'model': VERSION, 'font_sha256': resource['file_sha256'], 'face_index': resource['face_index'],
            'samples': rows, 'points_per_source_pixel': scale, 'source_uncertainty_px': resolution,
            'measurement_error_budget': {'source_edge_px': resolution, 'candidate_edge_quantization_px': .5,
                'extent_two_edges_px': extent_budget, 'boundary_px': edge_budget,
                'scope': 'Propagated interval for this size screen; no original appearance tolerance is changed'},
            'candidate_count': len(candidates), 'candidate_limit': MAX_CANDIDATES,
            'raster_scale_candidates': [1, SUPERSAMPLE],
            'rejected_raster_modes': rejected_modes,
            'candidates': candidates, 'plausible_sizes_pt': sorted(plausible), 'status': status,
            'recommended_pt': plausible[0] if status == 'IDENTIFIED' else None,
            'best_candidate_pt': best['font_size_pt'], 'initial_pt': center,
            'uncertainty_pt': (max(plausible)-min(plausible))/2 if plausible else None,
            'scope': 'Fixed-scale source-ink screening; no exact source-family, calibrated probability or native page-paint acceptance'}
