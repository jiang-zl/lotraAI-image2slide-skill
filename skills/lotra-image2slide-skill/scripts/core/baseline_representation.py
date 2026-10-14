"""Source-bound veto for replacing an editable historical owner with pictures.

This is a saved-PPT representation floor, not a visual-quality comparison.
The host identifies corresponding semantic owners; object names or pictures
alone cannot establish semantic fidelity. Raster exceptions remain a separate,
measured and editor-reviewed decision.
"""

from pathlib import Path

from pptx import Presentation

from .common import digest, read_json, safe_path, write_json
from .saved_ppt_diff import snapshot


def _owner_leaves(objects, selectors):
    if not isinstance(selectors, list) or not selectors or any(
            not isinstance(item, str) or not item.startswith("slide-") or
            not item.strip() for item in selectors):
        raise ValueError("Frozen semantic owner selectors must be saved-PPT paths")
    def matches(key, selector):
        if selector.endswith("*"):
            return key.startswith(selector[:-1])
        return key == selector or key.startswith(selector + "/")
    selected = {}
    for key, record in objects.items():
        if any(matches(key, item) for item in selectors):
            selected[key] = record
    for item in selectors:
        if not any(matches(key, item) for key in selected):
            raise ValueError("Declared semantic owner absent from saved PPT: " + item)
    # A selected group includes descendants through the path prefix. Flat
    # historical slides can instead select several source-named prefixes.
    leaves = {key: value for key, value in selected.items()
              if value["shape_type"] != "grpSp"}
    return {"selected_paths": sorted(selected), "native_leaf_paths": sorted(
                key for key, value in leaves.items() if value["shape_type"] != "pic"),
            "picture_leaf_paths": sorted(
                key for key, value in leaves.items() if value["shape_type"] == "pic")}


def _roi_alignment(pptx, objects, owner, roi, source_size):
    deck = Presentation(pptx)
    x, y, width, height = roi
    source_width, source_height = source_size
    area = [x / source_width * deck.slide_width,
            y / source_height * deck.slide_height,
            (x + width) / source_width * deck.slide_width,
            (y + height) / source_height * deck.slide_height]
    leaves = owner["native_leaf_paths"] + owner["picture_leaf_paths"]
    hits = 0
    for key in leaves:
        record = objects[key]
        left, top = record["bbox.left"], record["bbox.top"]
        right, bottom = left + record["bbox.width"], top + record["bbox.height"]
        if left <= area[2] and right >= area[0] and top <= area[3] and bottom >= area[1]:
            hits += 1
    fraction = hits / len(leaves) if leaves else 0
    if fraction < .8:
        raise ValueError("Saved semantic owner selection does not align with frozen source ROI")
    return {"selected_leaves": len(leaves), "intersecting_leaves": hits,
            "fraction": fraction}


def audit(contract, base, baseline_pptx, candidate_pptx):
    if contract.get("schema_version") != "baseline-representation-1":
        raise ValueError("Unknown baseline representation contract")
    source = safe_path(base, contract["source"]["path"])
    if digest(source) != contract["source"]["sha256"]:
        raise ValueError("Source image differs from frozen baseline contract")
    baseline_pptx, candidate_pptx = Path(baseline_pptx), Path(candidate_pptx)
    if digest(baseline_pptx) != contract.get("baseline_pptx_sha256"):
        raise ValueError("Historical baseline PPT differs from frozen contract")
    minimum = contract.get("minimum_candidate_native_leaves")
    if type(minimum) is not int or minimum < 1:
        raise ValueError("A predeclared minimum native detail floor is required")
    roi = contract.get("source_roi")
    from PIL import Image
    with Image.open(source) as image:
        source_size = image.size
        if (not isinstance(roi, list) or len(roi) != 4 or
                any(type(value) is not int for value in roi)):
            raise ValueError("Source ROI needs four integer pixels")
        x, y, width, height = roi
        if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > image.width or y + height > image.height:
            raise ValueError("Source ROI outside reference image")
    baseline = snapshot(baseline_pptx)
    candidate = snapshot(candidate_pptx)
    if baseline["slide_count"] != 1 or candidate["slide_count"] != 1:
        raise ValueError("This bounded representation audit requires one-slide PPTs")
    before = _owner_leaves(baseline["objects"], contract.get("baseline_owners"))
    after = _owner_leaves(candidate["objects"], contract.get("candidate_owners"))
    alignment = {"baseline": _roi_alignment(baseline_pptx, baseline["objects"], before, roi, source_size),
                 "candidate": _roi_alignment(candidate_pptx, candidate["objects"], after, roi, source_size)}
    if len(before["native_leaf_paths"]) < minimum or before["picture_leaf_paths"]:
        raise ValueError("Historical owner is not the declared native baseline")
    findings = []
    if after["picture_leaf_paths"]:
        findings.append("NATIVE_HISTORICAL_OWNER_REPLACED_OR_MIXED_WITH_PICTURE")
    if len(after["native_leaf_paths"]) < minimum:
        findings.append("CANDIDATE_NATIVE_DETAIL_BELOW_FROZEN_FLOOR")
    return {"schema_version": "baseline-representation-audit-1",
            "status": "FAIL_REPRESENTATION_REGRESSION" if findings else "PASS_REPRESENTATION_FLOOR_ONLY",
            "findings": findings, "source_hash": digest(source), "source_roi": roi,
            "baseline_pptx_hash": baseline["pptx_hash"],
            "candidate_pptx_hash": candidate["pptx_hash"],
            "minimum_candidate_native_leaves": minimum,
            "baseline": before, "candidate": after, "roi_alignment": alignment,
            "scope": "saved-PPT semantic-owner representation and native detail floor only; no visual or editor acceptance"}


def audit_file(contract_file, baseline_pptx, candidate_pptx, output):
    contract_file = Path(contract_file)
    result = audit(read_json(contract_file), contract_file.parent,
                   baseline_pptx, candidate_pptx)
    write_json(output, result)
    return result
