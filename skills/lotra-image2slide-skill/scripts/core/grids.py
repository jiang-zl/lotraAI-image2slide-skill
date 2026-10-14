"""94 fixed-canvas windows. Halos are context only, never coverage credit."""

import math
import numpy as np


def windows(width, height, halo=.12):
    if width < 6 or height < 6:
        raise ValueError("Canvas too small for six-way grid")
    result = []
    for name, n, shift in [("coarse", 3, 0), ("fine", 6, 0), ("shifted_fine", 6, -.5)]:
        count = n + int(bool(shift))
        bx = [max(0, min(width, math.floor((i+shift)*width/n))) for i in range(count+1)]
        by = [max(0, min(height, math.floor((i+shift)*height/n))) for i in range(count+1)]
        bx[-1], by[-1] = width, height
        for row in range(count):
            for col in range(count):
                x0, x1, y0, y1 = bx[col], bx[col+1], by[row], by[row+1]
                if x1 <= x0 or y1 <= y0:
                    continue
                dx, dy = math.ceil(halo*width/n), math.ceil(halo*height/n)
                result.append({"id": f"{name}-{row}-{col}", "scheme": name, "core": [x0,y0,x1,y1],
                               "context": [max(0,x0-dx),max(0,y0-dy),min(width,x1+dx),min(height,y1+dy)]})
    return result


def coverage(tiles, width, height):
    if width*height > 40_000_000:
        raise TimeoutError("Grid coverage exceeds pixel budget")
    results = {}
    for scheme in ("coarse", "fine", "shifted_fine"):
        count = np.zeros((height, width), dtype=np.uint8)
        for tile in tiles:
            if tile["scheme"] != scheme:
                continue
            x0,y0,x1,y1 = tile["core"]
            if not 0 <= x0 < x1 <= width or not 0 <= y0 < y1 <= height:
                raise ValueError("Tile lies outside canvas")
            count[y0:y1,x0:x1] += 1
        results[scheme] = {"covered_pixels": int(np.count_nonzero(count)), "missing_pixels": int(np.count_nonzero(count == 0)),
                           "overlap_pixels": int(np.count_nonzero(count > 1)), "status": "PASS" if np.all(count == 1) else "FAIL"}
    return results
