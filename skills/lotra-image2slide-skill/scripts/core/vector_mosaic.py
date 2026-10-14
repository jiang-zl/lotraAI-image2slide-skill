"""Bounded native rectangle reconstruction from observed pixels and owner masks.

This is a vector appearance method, not semantic segmentation. The host supplies
the semantic owner and fixed mask; every output is a PowerPoint-native shape.
At a resource limit the function fails rather than silently omitting pixels or
substituting a disguised raster.
"""

import heapq
from pathlib import Path

import numpy as np
from PIL import Image

from .scene import FACETS


def _split(tile):
    x, y, w, h = tile
    if w == 1 and h == 1:
        return []
    wx, hy = max(1, w // 2), max(1, h // 2)
    parts = [(x, y, wx, hy), (x+wx, y, w-wx, hy),
             (x, y+hy, wx, h-hy), (x+wx, y+hy, w-wx, h-hy)]
    return [p for p in parts if p[2] > 0 and p[3] > 0]


def _tile_stats(rgb, tile):
    x, y, w, h = tile
    region = rgb[y:y+h, x:x+w].astype(np.float32)
    mean = region.mean(axis=(0, 1))
    error = float(np.square(region - mean).sum())
    return mean, error


def _mask_underlay_rectangles(inside, x0, y0):
    """Cover only owner pixels with merged row runs beneath native tiles.

    PowerPoint/LibreOffice antialias each tile boundary against what is behind
    it. A white canvas can therefore show through a dense dark mosaic even
    when the tiles cover every source pixel geometrically.
    """
    rectangles = []
    active = {}
    for y, row in enumerate(inside):
        edges = np.flatnonzero(np.diff(np.r_[False, row, False].astype(np.int8)))
        runs = [(int(left), int(right - left)) for left, right in edges.reshape(-1, 2)]
        following = {}
        for left, width in runs:
            key = (left, width)
            if key in active:
                rectangle = active[key]
                rectangle[3] += 1
            else:
                rectangle = [x0 + left, y0 + y, width, 1]
                rectangles.append(rectangle)
            following[key] = rectangle
        active = following
    return rectangles


def adaptive_tiles(image, mask, *, roi=None, max_shapes=5000, min_tile=1,
                   error_floor=0.0, quantization=1):
    """Return exact-mask native rectangles with deterministic max-error splits."""
    if not 1 <= max_shapes <= 200000 or not 1 <= min_tile <= 32 or not 1 <= quantization <= 64:
        raise ValueError("Explicit, finite vector detail/resource limits are required")
    with Image.open(image) as im:
        rgb_all = np.asarray(im.convert("RGB"), dtype=np.uint8)
    with Image.open(mask) as im:
        if im.mode != "L" or im.size != (rgb_all.shape[1], rgb_all.shape[0]):
            raise ValueError("Owner mask must be a full-canvas grayscale image")
        mask_all = np.asarray(im)
    if not np.isin(mask_all, [0, 255]).all():
        raise ValueError("Owner mask must be binary")
    if roi is None:
        x0, y0, width, height = 0, 0, rgb_all.shape[1], rgb_all.shape[0]
    else:
        x0, y0, width, height = roi
    if min(x0, y0) < 0 or min(width, height) < 1 or x0+width > rgb_all.shape[1] or y0+height > rgb_all.shape[0]:
        raise ValueError("Vector mosaic ROI is outside the source")
    rgb = rgb_all[y0:y0+height, x0:x0+width]
    inside = mask_all[y0:y0+height, x0:x0+width] > 0
    if not inside.any():
        raise ValueError("Empty semantic owner mask in ROI")
    underlay_rectangles = _mask_underlay_rectangles(inside, x0, y0)
    tile_budget = max_shapes - len(underlay_rectangles)
    if tile_budget < 1:
        raise ValueError("Owner boundary exceeds vector shape budget including seam underlay")
    underlay_color = np.rint(rgb[inside].mean(axis=0)).astype(np.uint8)
    # Mandatory boundary subdivision preserves exact owner support.
    waiting = [(0, 0, width, height)]
    leaves = []
    while waiting:
        tile = waiting.pop()
        x, y, w, h = tile
        coverage = inside[y:y+h, x:x+w]
        if not coverage.any():
            continue
        if coverage.all():
            leaves.append(tile)
            if len(leaves) > tile_budget:
                raise ValueError("Owner boundary exceeds vector shape budget; no incomplete output emitted")
        else:
            waiting.extend(_split(tile))
    queue = []
    active = {index: tile for index, tile in enumerate(leaves)}
    for index, tile in active.items():
        _, error = _tile_stats(rgb, tile)
        heapq.heappush(queue, (-error, index, tile))
    next_index = len(leaves)
    while queue:
        negative_error, index, tile = heapq.heappop(queue)
        parts = _split(tile)
        if (-negative_error <= error_floor or not parts
                or max(tile[2], tile[3]) <= min_tile
                or len(active) + len(parts) - 1 > tile_budget):
            continue
        del active[index]
        for part in parts:
            _, error = _tile_stats(rgb, part)
            active[next_index] = part
            heapq.heappush(queue, (-error, next_index, part))
            next_index += 1
    tiles = []
    covered = np.zeros(inside.shape, dtype=bool)
    for tile in active.values():
        x, y, w, h = tile
        mean, _ = _tile_stats(rgb, tile)
        color = np.clip(np.rint(mean / quantization) * quantization, 0, 255).astype(np.uint8)
        tiles.append({"bbox": [x0+x, y0+y, w, h], "fill": "".join(f"{int(c):02X}" for c in color)})
        covered[y:y+h, x:x+w] = True
    if not np.array_equal(covered, inside):
        raise RuntimeError("Vector mosaic omitted or escaped semantic owner pixels")
    tiles.sort(key=lambda t: (t["bbox"][1], t["bbox"][3], t["fill"], t["bbox"][0]))
    merged = []
    for tile in tiles:
        if (merged and merged[-1]["fill"] == tile["fill"]
                and merged[-1]["bbox"][1] == tile["bbox"][1]
                and merged[-1]["bbox"][3] == tile["bbox"][3]
                and merged[-1]["bbox"][0] + merged[-1]["bbox"][2] == tile["bbox"][0]):
            merged[-1]["bbox"][2] += tile["bbox"][2]
        else:
            merged.append(tile)
    return {"method": "adaptive_native_rectangles-1", "roi": list(roi) if roi else [0,0,width,height],
            "source_size": [rgb_all.shape[1], rgb_all.shape[0]],
            "owner_pixels": int(inside.sum()), "shapes_before_merge": len(tiles),
            "shapes_after_merge": len(merged), "max_shapes": max_shapes,
            "seam_underlay": {"fill": "".join(f"{int(c):02X}" for c in underlay_color),
                               "rectangles": underlay_rectangles,
                               "reason": "Protect dense native tile edges from unrelated canvas color"},
            "tiles": merged, "status": "NATIVE_TILE_PLAN_NOT_YET_BUILT_OR_RENDERED"}


def scene_objects(tile_plan, owner_id, *, parent=None, semantic_type="illustration_region"):
    """Convert the bounded tile plan into existing native Scene group/shape types."""
    x, y, w, h = tile_plan["roi"]
    metadata = {"versions": {key: 0 for key in FACETS},
                "locks": {key: False for key in FACETS}, "evidence_status": "inferred"}
    owner = {"id": owner_id, "semantic_type": semantic_type, "render_type": "group",
             "parent": parent, "bbox": [x, y, w, h], "content": {}, "style": {}, **metadata}
    objects = [owner]
    underlay = tile_plan.get("seam_underlay")
    if underlay:
        for index, rectangle in enumerate(underlay["rectangles"]):
            objects.append({"id": f"{owner_id}__seam_underlay_{index}",
                            "semantic_type": "native_color_patch", "render_type": "shape",
                            "parent": owner_id, "bbox": rectangle,
                            "content": {"preset": "rect"},
                            "style": {"fill": underlay["fill"], "stroke": None},
                            "versions": dict(metadata["versions"]), "locks": dict(metadata["locks"]),
                            "evidence_status": "inferred"})
    for index, tile in enumerate(tile_plan["tiles"]):
        objects.append({"id": f"{owner_id}__pixel_{index}", "semantic_type": "native_color_patch",
                        "render_type": "shape", "parent": owner_id, "bbox": tile["bbox"],
                        "content": {"preset": "rect"}, "style": {"fill": tile["fill"], "stroke": None},
                        "versions": dict(metadata["versions"]), "locks": dict(metadata["locks"]),
                        "evidence_status": "inferred"})
    return objects
