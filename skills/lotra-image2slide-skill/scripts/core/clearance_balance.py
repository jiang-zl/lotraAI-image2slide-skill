"""Deterministic centering from actual containment and directional clearances.

No group-frame centers are used. The painted union is moved rigidly within the
effective interior; concave domains use the first collision, not a distant
feasible pocket. Source-supported asymmetric targets can remain asymmetric.
"""
import math
from shapely.affinity import translate

VERSION = 'directional-clearance-1'

def travel(content, interior, axis, direction, precision=.01):
    if axis not in (0, 1) or direction not in (-1, 1):
        raise ValueError('One axis and direction required')
    if content.is_empty or interior.is_empty or not content.is_valid or not interior.is_valid:
        raise ValueError('Complete valid painted content and interior required')
    if not interior.buffer(.025).covers(content):
        raise ValueError('Overflow must be resolved before clearance centering')
    bounds = interior.bounds
    extent = bounds[axis+2]-bounds[axis]
    if not math.isfinite(extent) or extent <= 0:
        raise ValueError('Finite positive interior span required')
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    domain=interior.buffer(.025)
    convex=domain.equals(domain.convex_hull)
    # Bound the first collision. The sweep prevents jumping over a hole into
    # another feasible pocket. Boundary strips give the exact segment sweep
    # for arbitrary polygonal painted unions, including holes.
    def swept_fits(distance):
        offset={'xoff' if axis == 0 else 'yoff': direction*distance}
        moved=translate(content,**offset)
        if not domain.covers(moved):return False
        if convex:return True
        shift=(direction*distance,0.) if axis==0 else (0.,direction*distance)
        pieces=list(content.geoms) if hasattr(content,'geoms') else [content]
        strips=[]
        for piece in pieces:
            if piece.geom_type!='Polygon':raise ValueError('Actual painted polygon coverage required')
            for ring in [piece.exterior,*piece.interiors]:
                points=list(ring.coords)
                for a,b in zip(points,points[1:]):
                    strip=Polygon([a,b,(b[0]+shift[0],b[1]+shift[1]),(a[0]+shift[0],a[1]+shift[1])])
                    if strip.area>1e-12:strips.append(strip)
        return domain.covers(unary_union([content,moved,*strips]))
    low, high = 0., extent
    for _ in range(32):
        if high-low <= precision:
            break
        middle = (low+high)/2
        if swept_fits(middle):
            low = middle
        else:
            high = middle
    return max(0., low-.025)

def measure(content, interior, target_asymmetry=(0., 0.)):
    if len(target_asymmetry) != 2 or any(not math.isfinite(float(v)) for v in target_asymmetry):
        raise ValueError('Freeze finite horizontal and vertical clearance targets')
    result = {}
    for axis, name in enumerate(('x','y')):
        before = travel(content, interior, axis, -1)
        after = travel(content, interior, axis, 1)
        asymmetry = before-after
        result[name] = {'negative_clearance_px': before, 'positive_clearance_px': after,
                        'asymmetry_px': asymmetry, 'target_asymmetry_px': float(target_asymmetry[axis]),
                        'actual': (asymmetry-float(target_asymmetry[axis]))/2,
                        'method': VERSION}
    return result
