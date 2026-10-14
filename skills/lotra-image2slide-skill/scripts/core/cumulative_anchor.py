"""Compare every selected local edit with the original protected version.

The cumulative mask is the union of *previously frozen* edit masks and this
edit's predeclared mask. It is never enlarged from observed candidate errors.
"""

import os
from pathlib import Path

import numpy as np
from PIL import Image

from .common import digest, read_json
from .local_edit import check_scene_protection
from .render_protection import compare_rendered
from .saved_ppt_diff import PRODUCT_MAPPING, compare, snapshot


def _binary(path, size=None):
    with Image.open(path) as image:
        if image.mode != "L" or (size and image.size != size):
            raise ValueError("Cumulative protection needs aligned grayscale masks")
        pixels = np.asarray(image).copy()
        dimensions = image.size
    if not np.isin(pixels, [0, 255]).all():
        raise ValueError("Cumulative protection mask is not binary")
    return pixels, dimensions


def verify_cumulative(anchor, candidate_scene, candidate_pptx, candidate_preview,
                      noop_preview, noop_receipt, candidate_receipt,
                      previous_write_set, current_write_set,
                      previous_mask, current_mask, output_mask):
    """Recheck Scene, saved PPT, and fixed-renderer pixels against one anchor.

    `anchor` contains original saved artifact paths and their frozen hashes.
    This scoped result is not a full QA or native-editor acceptance decision.
    """
    for field in ("scene", "pptx", "preview", "render_receipt"):
        if digest(anchor[field]) != anchor[field + "_hash"]:
            raise ValueError("Original cumulative anchor changed: " + field)
    current_mask_pixels, size = _binary(current_mask)
    if previous_mask is None:
        union = current_mask_pixels
    else:
        previous_pixels, _ = _binary(previous_mask, size)
        union = np.maximum(previous_pixels, current_mask_pixels)
    output_mask = Path(output_mask)
    if output_mask.exists():
        raise ValueError("Cumulative mask output must be a new file")
    output_mask.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(union).save(output_mask)

    allowed = {(item["object_id"], item["path"])
               for item in previous_write_set + current_write_set}
    original_scene, latest_scene = read_json(anchor["scene"]), read_json(candidate_scene)
    scene_guard = check_scene_protection(original_scene, latest_scene, allowed)
    old, latest = snapshot(anchor["pptx"]), snapshot(candidate_pptx)
    ppt_allowed, unsupported = set(), []
    for object_id, path in sorted(allowed):
        matches = [key for key in old["objects"] if key.split("/")[-1] == object_id]
        property_name = PRODUCT_MAPPING.get(path)
        if len(matches) != 1 or property_name is None:
            unsupported.append({"object_id": object_id, "path": path})
        else:
            ppt_allowed.add((matches[0], property_name))
    saved_guard = compare(old, latest, ppt_allowed)
    files = [Path(anchor["preview"]), Path(noop_preview), Path(candidate_preview),
             output_mask, Path(previous_mask) if previous_mask is not None else Path(current_mask)]
    common = Path(os.path.commonpath([str(path.resolve()) for path in files]))
    refs = [{"path": path.resolve().relative_to(common).as_posix(), "sha256": digest(path)} for path in files]
    anchor_receipt = read_json(anchor["render_receipt"])
    # For a later edit, the current no-op render is the previous selected
    # version. It may legitimately differ from the original inside only the
    # *previously* authorized mask. The new candidate is compared separately
    # with the original under the frozen union mask.
    noop_guard = compare_rendered(common, refs[0], refs[0], refs[1], refs[4],
                                  anchor_receipt, anchor_receipt, read_json(noop_receipt))
    if (previous_mask is None and noop_guard["status"] == "PASS_RENDER_PROTECTION_ONLY"
            and noop_guard["inside_changed_pixels"]):
        noop_guard["status"] = "UNVERIFIED_NOOP_DRIFT"
    render_guard = compare_rendered(common, refs[0], refs[0], refs[2], refs[3],
                                    anchor_receipt, anchor_receipt, read_json(candidate_receipt))
    status = ("PASS_CUMULATIVE_ANCHOR_ONLY"
              if not unsupported and saved_guard["status"] == "PASS_SAVED_PRODUCT_ONLY"
              and noop_guard["status"] == "PASS_RENDER_PROTECTION_ONLY"
              and render_guard["status"] == "PASS_RENDER_PROTECTION_ONLY"
              else "FAIL" if (saved_guard["status"] == "FAIL" or noop_guard["status"] == "FAIL"
                              or render_guard["status"] == "FAIL")
              else "UNVERIFIED")
    return {"schema_version": "cumulative-anchor-check-1", "status": status,
            "anchor_pptx_hash": anchor["pptx_hash"], "candidate_pptx_hash": digest(candidate_pptx),
            "candidate_preview_hash": digest(candidate_preview), "union_mask_hash": digest(output_mask),
            "allowed_write_set": [{"object_id": obj, "path": path} for obj, path in sorted(allowed)],
            "unsupported_native_paths": unsupported, "scene_guard": scene_guard,
            "saved_guard": saved_guard, "noop_guard": noop_guard, "render_guard": render_guard,
            "scope": "original-anchor cumulative product protection; full QA separately required"}
