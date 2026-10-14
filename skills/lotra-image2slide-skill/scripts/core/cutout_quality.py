"""Fail-closed clarity and amodal checks for extracted complex-scene cutouts.

The image comparison is a diagnostic, not a claim that upsampling recovered
unknown historical detail. A bound visual review must also pass. If the route
cannot satisfy this contract, the owner must be rebuilt natively.
"""

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage as ndi

from .common import digest, read_json, safe_path


REVIEW_CHECKS = ("clarity_gain", "source_fidelity", "no_halos_or_noise", "style_consistency")


def refine_alpha_matte(source, output, *, max_hole_pixels=64):
    """Normalize a model-restored cutout's alpha without inventing its content.

    This prepares an asset for inspection; it does not prove semantic
    completion, source fidelity or a clarity gain. Large holes and substantial
    disconnected content fail so an editor/host must handle them explicitly.
    """
    source, output = Path(source), Path(output)
    if output.exists():
        raise FileExistsError(output)
    if type(max_hole_pixels) is not int or not 0 <= max_hole_pixels <= 4096:
        raise ValueError("max_hole_pixels must be an integer in 0..4096")
    with Image.open(source) as image:
        pixels = np.asarray(image.convert("RGBA")).copy()
    original_alpha = pixels[..., 3].copy()
    support = original_alpha > 0
    labels, count = ndi.label(support)
    if not count:
        raise ValueError("Cutout has no nontransparent pixels")
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    main = labels == sizes.argmax()
    disconnected = int((support & ~main).sum())
    if disconnected > max(8, int(support.sum() * .01)):
        raise ValueError("Substantial disconnected content requires separate semantic owners")
    holes = ndi.binary_fill_holes(main) & ~main
    hole_labels, hole_count = ndi.label(holes)
    hole_sizes = np.bincount(hole_labels.ravel())[1:]
    if hole_count and int(hole_sizes.max()) > max_hole_pixels:
        raise ValueError("Large interior hole requires semantic completion before matte refinement")
    final_support = main | holes
    if holes.any():
        _, nearest = ndi.distance_transform_edt(~main, return_indices=True)
        pixels[holes, :3] = pixels[nearest[0][holes], nearest[1][holes], :3]
    interior = ndi.binary_erosion(final_support, structure=np.ones((3, 3)))
    weak = interior & (original_alpha < 128)
    if weak.any():
        strong = interior & (original_alpha >= 128)
        if not strong.any():
            raise ValueError("No reliable interior color around weak-alpha pixels")
        _, nearest = ndi.distance_transform_edt(~strong, return_indices=True)
        pixels[weak, :3] = pixels[nearest[0][weak], nearest[1][weak], :3]
    pixels[interior, 3] = 255
    pixels[holes, 3] = 255
    pixels[~final_support, 3] = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(pixels).save(output)
    return {
        "status": "MATTE_REFINED_REQUIRES_VISUAL_AND_COMPLETION_REVIEW",
        "source_sha256": digest(source), "output_sha256": digest(output),
        "canvas": [int(pixels.shape[1]), int(pixels.shape[0])],
        "interior_pixels_normalized": int((interior & (original_alpha < 255)).sum()),
        "tiny_hole_pixels_filled": int(holes.sum()),
        "largest_hole_pixels": int(hole_sizes.max()) if hole_count else 0,
        "disconnected_pixels_dropped": disconnected,
        "limits": "Matte only; hidden objects, scientific content and visual quality remain unverified",
    }


def _resource(base, ref):
    if not isinstance(ref, dict) or not isinstance(ref.get("sha256"), str):
        raise ValueError("Cutout workflow needs hash-bound resources")
    path = safe_path(base, ref["path"])
    if digest(path) != ref["sha256"]:
        raise ValueError("Cutout workflow resource changed: " + ref["path"])
    return path


def _edge_strength(image, mask):
    gray = image.convert("RGB").convert("L")
    edge = np.asarray(gray.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    # The outermost pixel is an image-filter artifact, not object detail.
    usable = np.asarray(mask.convert("L")) > 0
    usable[[0, -1], :] = False
    usable[:, [0, -1]] = False
    if not usable.any():
        raise ValueError("Cutout detail mask contains no interior pixels")
    return float(edge[usable].mean())


def _review_evidence(base, ref, source, enhanced):
    parent = source if ref['role'] == 'source' else enhanced
    evidence = _resource(base, ref)
    if ref.get('roi') is None:
        if digest(evidence) != digest(parent):
            raise ValueError('Uncropped clarity evidence must be the bound source or enhanced asset')
        return
    roi = ref['roi']
    if (ref.get('parent_sha256') != digest(parent) or not isinstance(roi, list) or
            len(roi) != 4 or any(type(value) is not int for value in roi)):
        raise ValueError('Located clarity crop lacks its parent identity and integer ROI')
    x, y, width, height = roi
    with Image.open(parent) as full, Image.open(evidence) as crop:
        if min(x, y) < 0 or min(width, height) <= 0 or x + width > full.width or y + height > full.height:
            raise ValueError('Clarity evidence ROI is outside its parent asset')
        if crop.size != (width, height) or not np.array_equal(
                np.asarray(crop.convert('RGBA')),
                np.asarray(full.crop((x, y, x + width, y + height)).convert('RGBA'))):
            raise ValueError('Clarity evidence pixels do not match the declared parent ROI')


def validate_workflow(obj, scene, base):
    """Validate extracted -> enhanced -> completed ordering and saved payload."""
    if obj['content'].get('reconstruction', {}).get('appearance_policy') == 'semantic_hd_replace':
        from .appearance import semantic_hd_asset
        return semantic_hd_asset(obj['content'], base)
    workflow = obj["content"].get("cutout_workflow")
    if workflow is None:
        if scene.get("analysis"):
            raise ValueError("Analyzed complex raster must declare its cutout workflow")
        if base is not None:
            with Image.open(_resource(base, obj["content"])) as image:
                if image.convert("RGBA").getextrema()[-1][0] < 255:
                    raise ValueError("Transparent complex raster needs mandatory cutout refinement")
        return {"status": "LEGACY_UNVERIFIED"}
    if workflow.get("kind") not in ("cutout", "uncut"):
        raise ValueError("Complex raster cutout kind must be explicit")
    if workflow["kind"] == "uncut":
        if not workflow.get("reason") or not workflow.get("source_evidence_refs"):
            raise ValueError("Uncut claim needs a source-specific reason and evidence")
        if base is not None:
            with Image.open(_resource(base, obj["content"])) as image:
                if image.convert("RGBA").getextrema()[-1][0] < 255:
                    raise ValueError("Transparent complex raster cannot be declared uncut")
        return {"status": "UNCUT_DECLARED_REQUIRES_SOURCE_REVIEW"}
    required = ("source_asset", "enhanced_asset", "detail_mask", "enhancement_review",
                "completion_contract", "completion_review", "max_reuse_inches",
                "minimum_display_ppi", "minimum_clarity_gain", "occluded")
    if any(key not in workflow for key in required):
        raise ValueError("Cutout lacks mandatory enhancement/completion fields")
    reuse = workflow["max_reuse_inches"]
    ppi = workflow["minimum_display_ppi"]
    gain_floor = workflow["minimum_clarity_gain"]
    if (not isinstance(reuse, list) or len(reuse) != 2 or
            any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in reuse) or
            type(ppi) not in (int, float) or not math.isfinite(ppi) or ppi < 200 or
            type(gain_floor) not in (int, float) or not .01 <= gain_floor <= 1 or
            type(workflow["occluded"]) is not bool):
        raise ValueError("Invalid frozen cutout clarity/reuse contract")
    if base is None:
        return {"status": "CUTOUT_REQUIRES_SAVED_EVIDENCE"}
    source = _resource(base, workflow["source_asset"])
    enhanced = _resource(base, workflow["enhanced_asset"])
    final = _resource(base, obj["content"])
    mask_file = _resource(base, workflow["detail_mask"])
    if digest(source) == digest(enhanced):
        raise ValueError("Cutout enhancement is a no-op")
    with Image.open(source) as initial, Image.open(enhanced) as improved, Image.open(mask_file) as mask:
        source_dimensions = initial.size
        if (improved.width < initial.width or improved.height < initial.height or
                mask.size != improved.size):
            raise ValueError("Cutout enhancement lost pixels or detail-mask alignment")
        if min(improved.width / reuse[0], improved.height / reuse[1]) < ppi:
            raise ValueError("Enhanced cutout is too small at its intended reuse size")
        values = np.unique(np.asarray(mask.convert('L')))
        if not set(values.tolist()) <= {0, 255}:
            raise ValueError('Cutout detail mask must be binary')
        source_at_size = initial.resize(improved.size, Image.Resampling.LANCZOS)
        before = _edge_strength(source_at_size, mask)
        after = _edge_strength(improved, mask)
        if before <= 0 or after < before * (1 + gain_floor):
            raise ValueError("Cutout has no measured detail-edge clarity gain")
        dimensions = improved.size
    review = read_json(_resource(base, workflow["enhancement_review"]))
    if (review.get("schema_version") != "cutout-enhancement-review-1" or
            review.get("source_sha256") != digest(source) or
            review.get("enhanced_sha256") != digest(enhanced) or
            review.get("detail_mask_sha256") != digest(mask_file) or
            review.get("reviewer", {}).get("kind") not in ("human", "host_model")):
        raise ValueError("Cutout clarity review is unbound or has no real reviewer")
    for key in REVIEW_CHECKS:
        item = review.get("checks", {}).get(key, {})
        if item.get("status") != "PASS" or not item.get("note") or not item.get("evidence_refs"):
            raise ValueError("Cutout clarity review must pass with located evidence: " + key)
        if not all(isinstance(ref, dict) and ref.get("role") in ("source", "enhanced")
                   for ref in item["evidence_refs"]):
            raise ValueError("Invalid cutout clarity review evidence")
        if {ref["role"] for ref in item["evidence_refs"]} != {"source", "enhanced"}:
            raise ValueError("Clarity review must show both source and enhanced crops")
        for ref in item['evidence_refs']:
            _review_evidence(base, ref, source, enhanced)
    from .completion import measure, validate
    completion_file = _resource(base, workflow["completion_contract"])
    completion = read_json(completion_file)
    if completion.get("source", {}).get("sha256") != digest(enhanced):
        raise ValueError("Hidden completion must start from the enhanced cutout")
    _, visible, amodal, _ = validate(completion, completion_file.parent)
    if visible.shape != (dimensions[1], dimensions[0]):
        raise ValueError("Completion masks do not match the enhanced asset")
    if workflow["occluded"] and not (amodal & ~visible).any():
        raise ValueError("Occluded cutout has no completed hidden area")
    semantic_review = _resource(base, workflow["completion_review"])
    result = measure(completion, completion_file.parent, final, semantic_review=semantic_review)
    if result["status"] != "PASS_COMPONENT_COMPLETION":
        raise ValueError("Cutout hidden completion or semantic review did not pass")
    return {"status": "PASS_CUTOUT_ASSET", "source_sha256": digest(source),
            "enhanced_sha256": digest(enhanced), "final_sha256": digest(final),
            "source_information_ppi": [size / inches for size, inches in zip(source_dimensions, reuse)],
            "enhanced_display_ppi": [size / inches for size, inches in zip(dimensions, reuse)],
            "clarity_edge_gain": after / before - 1, "completion_status": result["status"]}
