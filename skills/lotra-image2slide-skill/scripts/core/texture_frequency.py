"""Fixed-protocol spatial/frequency diagnostics for an observed image ROI.

FFT amplitude loses phase and semantic placement; these numbers never alone
authorize a bitmap exception or mark an icon/illustration as acceptable.
"""

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from skimage.metrics import structural_similarity

VERSION = "texture-frequency-1"


def _luminance(image, roi):
    with Image.open(image) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0
    if roi is not None:
        x, y, w, h = roi
        if min(x, y) < 0 or min(w, h) < 16 or y+h > rgb.shape[0] or x+w > rgb.shape[1]:
            raise ValueError("Texture ROI must be fixed, in bounds and at least 16 pixels per side")
        rgb = rgb[y:y+h, x:x+w]
    return np.clip(rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722, 0, 1)


def features(image, roi=None):
    gray = _luminance(image, roi)
    if min(gray.shape) < 16:
        raise ValueError("Texture analysis needs a nontrivial fixed ROI")
    centered = gray - gray.mean()
    window = np.outer(np.hanning(gray.shape[0]), np.hanning(gray.shape[1]))
    power = np.abs(np.fft.fftshift(np.fft.fft2(centered * window))) ** 2
    fy = np.fft.fftshift(np.fft.fftfreq(gray.shape[0]))[:, None]
    fx = np.fft.fftshift(np.fft.fftfreq(gray.shape[1]))[None, :]
    radius = np.sqrt(fx*fx + fy*fy)
    bands = ((0.0, 0.04), (0.04, 0.12), (0.12, 0.25), (0.25, 0.5))
    total = max(float(power[(radius > 0) & (radius <= 0.5)].sum()), 1e-30)
    fractions = [float(power[(radius > lo) & (radius <= hi)].sum() / total) for lo, hi in bands]
    theta = np.arctan2(fy, fx)
    orientation = []
    active = (radius >= 0.04) & (radius <= 0.45)
    directional_total = max(float(power[active].sum()), 1e-30)
    for start in np.linspace(-np.pi, np.pi, 8, endpoint=False):
        delta = (theta - start + np.pi) % (2*np.pi) - np.pi
        orientation.append(float(power[active & (delta >= 0) & (delta < np.pi/4)].sum()/directional_total))
    weights = power[active].ravel()
    weights = weights / max(weights.sum(), 1e-30)
    spectral_entropy = float(-(weights * np.log(np.maximum(weights, 1e-30))).sum() / np.log(max(2, weights.size)))
    gx, gy = np.gradient(gray)
    magnitude = np.hypot(gx, gy)
    gxx, gyy, gxy = (ndi.gaussian_filter(gx*gx, 2), ndi.gaussian_filter(gy*gy, 2),
                    ndi.gaussian_filter(gx*gy, 2))
    coherence = np.sqrt((gxx-gyy)**2 + 4*gxy**2) / np.maximum(gxx+gyy, 1e-9)
    multiscale = [float(np.mean(np.abs(gray-ndi.gaussian_filter(gray, sigma)))) for sigma in (1, 2, 4)]
    return {"version": VERSION, "roi": list(roi) if roi else None,
            "protocol": {"color": "sRGB-derived Rec.709 luminance", "mean": "subtracted",
                         "window": "separable Hann", "padding": "none", "mask": "rectangular ROI only",
                         "frequency_units": "cycles per pixel", "bands": [list(x) for x in bands]},
            "band_energy_fraction": fractions, "orientation_fraction": orientation,
            "spectral_entropy": spectral_entropy, "edge_density": float((magnitude > 0.06).mean()),
            "mean_structure_coherence": float(coherence.mean()),
            "multiscale_residual": multiscale, "gray": gray}


def compare(reference, candidate, roi=None):
    a, b = features(reference, roi), features(candidate, roi)
    if a["gray"].shape != b["gray"].shape:
        raise ValueError("Texture comparison requires the same fixed ROI and canvas")
    source, result = a.pop("gray"), b.pop("gray")
    return {"version": VERSION, "roi": list(roi) if roi else None,
            "source": a, "candidate": b,
            "band_l1": float(np.abs(np.array(a["band_energy_fraction"])-np.array(b["band_energy_fraction"])).sum()),
            "orientation_l1": float(np.abs(np.array(a["orientation_fraction"])-np.array(b["orientation_fraction"])).sum()),
            "multiscale_residual_l1": float(np.abs(np.array(a["multiscale_residual"])-np.array(b["multiscale_residual"])).sum()),
            "spatial_ssim": float(structural_similarity(source, result, data_range=1.0)),
            "status": "DIAGNOSTIC_ONLY_REQUIRES_SEMANTIC_AND_SPATIAL_REVIEW",
            "reason": "Equal FFT power can hide scrambled phase, missing landmarks or wrong ownership"}
