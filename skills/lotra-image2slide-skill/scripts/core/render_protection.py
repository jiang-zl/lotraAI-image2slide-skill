"""Frozen-mask rendered-page protection for an already approved baseline.

This is a noncompensating visual gate. A changed renderer/font/profile/no-op
control is UNVERIFIED, not a chance to loosen the comparison threshold.
"""

from pathlib import Path

import numpy as np
from PIL import Image

from .common import digest, identity, safe_path


def _rgba(path):
    with Image.open(path) as im:
        return np.asarray(im.convert("RGBA")).copy()


def _mask(path, size):
    with Image.open(path) as im:
        if im.mode != "L" or im.size != size:
            raise ValueError("Render protection needs an aligned grayscale mask")
        a = np.asarray(im)
    if not np.isin(a, [0, 255]).all():
        raise ValueError("Render protection mask must be binary and frozen")
    return a > 0


def compare_rendered(base, anchor_ref, noop_ref, candidate_ref, mask_ref,
                     baseline_receipt, noop_receipt, candidate_receipt):
    """Check outside the advance-frozen mask at one immutable render protocol."""
    refs = [anchor_ref, noop_ref, candidate_ref, mask_ref]
    for ref in refs:
        file = safe_path(base, ref["path"])
        if digest(file) != ref.get("sha256"):
            raise ValueError("Render protection reference changed")
    anchor, noop, candidate = [_rgba(safe_path(base, x["path"])) for x in refs[:3]]
    if anchor.shape != noop.shape or anchor.shape != candidate.shape:
        raise ValueError("Protected renders need identical canvases")
    allowed = _mask(safe_path(base, mask_ref["path"]), (anchor.shape[1], anchor.shape[0]))
    if not allowed.any():
        raise ValueError("Empty allowed change region")
    for receipt, ref in ((baseline_receipt, anchor_ref), (noop_receipt, noop_ref),
                         (candidate_receipt, candidate_ref)):
        if receipt.get("preview_hash") != ref["sha256"] or receipt.get("status") != "PASS":
            raise ValueError("Render receipt does not bind this actual preview")
    def context(item):
        env = item.get("environment") or item.get("current_environment") or {}
        pages = item.get("pages") or []
        width = pages[0].get("canvas", [None])[0] if pages else item.get("width")
        return {"backend": item.get("backend"),
                "backend_version": item.get("backend_version") or item.get("office_build"),
                "environment_hash": identity(env),
                "font_inventory_hash": item.get("font_inventory_hash") or env.get("font_inventory_hash"),
                "width": width, "fontconfig": item.get("fontconfig"),
                "renderer_config_hash": item.get("renderer_config_hash"),
                "profile_hash": item.get("profile_hash"),
                "mapping": item.get("mapping"), "executable": item.get("executable")}
    contexts = [context(item) for item in (baseline_receipt, noop_receipt, candidate_receipt)]
    if any(context["backend_version"] is None or context["width"] is None for context in contexts):
        return {"status": "UNVERIFIED_RENDER_PROTOCOL_INCOMPLETE", "contexts": contexts}
    if any(context != contexts[0] for context in contexts[1:]):
        return {"status": "UNVERIFIED_ENVIRONMENT_CHANGED", "contexts": contexts,
                "anchor_preview_hash": anchor_ref["sha256"], "candidate_preview_hash": candidate_ref["sha256"],
                "mask_hash": mask_ref["sha256"]}
    noop_changed = np.any(anchor != noop, axis=2)
    if noop_changed.any():
        return {"status": "UNVERIFIED_NOOP_DRIFT", "noop_changed_pixels": int(noop_changed.sum()),
                "outside_noop_changed_pixels": int((noop_changed & ~allowed).sum()),
                "anchor_preview_hash": anchor_ref["sha256"], "noop_preview_hash": noop_ref["sha256"],
                "mask_hash": mask_ref["sha256"], "context": contexts[0]}
    outside_diff = np.any(anchor != candidate, axis=2) & ~allowed
    inside_diff = np.any(anchor != candidate, axis=2) & allowed
    # The protected anchor is never replaced with the previous edit's preview.
    return {"status": "FAIL" if outside_diff.any() else "PASS_RENDER_PROTECTION_ONLY",
            "outside_changed_pixels": int(outside_diff.sum()), "inside_changed_pixels": int(inside_diff.sum()),
            "max_outside_channel_delta": int(np.abs(anchor.astype(np.int16)-candidate.astype(np.int16))[~allowed].max()) if (~allowed).any() else 0,
            "anchor_preview_hash": anchor_ref["sha256"], "candidate_preview_hash": candidate_ref["sha256"],
            "noop_preview_hash": noop_ref["sha256"], "mask_hash": mask_ref["sha256"],
            "context": contexts[0], "scope": "fixed-renderer pixel protection; semantic and native gates are separate"}
