"""Source-bound physical interfaces, measured on actual native owner mattes.

Names and source intent are observations. Distances, port location, solid width
and real parent membership are computed; neither a group box nor prose is PASS.
"""
import math
import numpy as np
from lxml import etree as E
from .mathml import NS

VERSION = 'semantic-interface-1'


def validate(row, size):
    sets = row.get('part_sets', [])
    if (len(sets) != 2 or any(not g for g in sets) or
            len(set(n for g in sets for n in g)) != sum(map(len, sets)) or
            set(n for g in sets for n in g) != set(row['objects'])):
        raise ValueError('An interface needs two complete distinct native part sets')
    if not row.get('root') or not row.get('source_roles') or len(row['source_roles']) != 2:
        raise ValueError('Bind the physical root and two independently observed source roles')
    if row.get('relationship') not in ('attached', 'adjacent', 'intentional_separation'):
        raise ValueError('Use a typed physical relation; common semantic identity is insufficient')
    box = row.get('source_root_frame', [])
    if len(box) != 4 or not all(math.isfinite(v) for v in box) or min(box[2:]) <= 0:
        raise ValueError('Freeze the observed original root frame')
    if min(box[:2])<0 or box[0]+box[2]>size[0] or box[1]+box[3]>size[1]:
        raise ValueError('Observed physical root frame must remain inside the original')
    port = row.get('port', {})
    domain = port.get('domain', [])
    anchor = port.get('anchor', [])
    tangent = port.get('tangent', [])
    if (len(domain) != 4 or min(domain[2:]) <= 0 or len(anchor) != 2 or
            len(tangent) != 2 or math.hypot(*tangent) < 1e-9 or
            not all(math.isfinite(v) for v in domain+anchor+tangent)):
        raise ValueError('Original interface domain, anchor and tangent are required')
    if min(domain[:2]) < 0 or domain[0]+domain[2] > 1 or domain[1]+domain[3] > 1:
        raise ValueError('Interface domain is normalized within its observed physical root')
    if not (domain[0] <= anchor[0] <= domain[0]+domain[2] and
            domain[1] <= anchor[1] <= domain[1]+domain[3]):
        raise ValueError('Source port anchor must lie inside the interface domain')
    limits = row.get('limits', {})
    interval = limits.get('distance_px', [])
    if (len(interval) != 2 or min(interval) < 0 or interval[1] < interval[0] or
            not all(math.isfinite(v) for v in interval) or
            not 0 <= limits.get('anchor_error_px', -1) <= max(size) or
            not math.isfinite(limits.get('anchor_error_px', float('nan')))):
        raise ValueError('Freeze a finite source-pixel interval and anchor tolerance')
    if row['relationship'] == 'attached':
        if interval[0] != 0 or interval[1] > 1 or not math.isfinite(limits.get('solid_width_px',float('nan'))) or limits.get('solid_width_px', 0) <= 0:
            raise ValueError('Physical attachment requires a solid interface; a visible gap cannot be waived')
    if not row.get('threshold_basis') or not row.get('source_evidence'):
        raise ValueError('Thresholds need original sampling/semantic evidence before drawing')
    return row


def root_map(entry):
    """Normalized root coordinates to saved world coordinates, with all transforms."""
    if entry.get('error') or entry['tag'] != 'grpSp':
        raise ValueError('Physical root must be an actual supported native group')
    xf = entry['node'].find('p:grpSpPr/a:xfrm', NS)
    offset, extent = xf.find('a:chOff', NS), xf.find('a:chExt', NS)
    co = [float(offset.get(k)) for k in ('x', 'y')]
    ce = [float(extent.get(k)) for k in ('cx', 'cy')]
    local = np.array([[ce[0], 0., co[0]], [0., ce[1], co[1]], [0., 0., 1.]])
    return entry['matrix'] @ local


def _within_root(name, root, parents):
    seen = set()
    while name is not None and name not in seen:
        if name == root:
            return True
        seen.add(name)
        name = parents.get(name)
    return False


def evaluate(row, responses, nodes, parents, size):
    """Euclidean distance interval plus tangent width at the correct native port.

    Conservative discretization bounds use both half-pixel diagonals. Opaque
    core is backdrop delta <= 2 (not weak alpha fringes). Thresholds are frozen
    in original pixels; rendering resolution never changes the rule.
    """
    from scipy.ndimage import distance_transform_edt, label
    from PIL import Image, ImageDraw
    validate(row, size)
    if row['root'] not in nodes or any(not _within_root(n, row['root'], parents) for n in row['objects']):
        return {'status': 'wrong_native_root', 'passed': False, 'values': {}}
    if any(v is None for v in responses) or responses[0].shape != responses[1].shape:
        return {'status': 'required_unmeasured', 'passed': False, 'values': {}}
    height, width = responses[0].shape
    sx, sy = size[0]/width, size[1]/height
    if max(sx, sy) > .250001:
        return {'status': 'insufficient_sampling', 'passed': False, 'values': {}}
    matrix = root_map(nodes[row['root']])
    def world(point):
        return (matrix @ np.array([*point, 1.]))[:2]
    x, y, w, h = row['port']['domain']
    corners = [world(p) for p in ((x,y), (x+w,y), (x+w,y+h), (x,y+h))]
    left=max(0,math.floor(min(p[0] for p in corners)/sx)-1)
    top=max(0,math.floor(min(p[1] for p in corners)/sy)-1)
    right=min(width,math.ceil(max(p[0] for p in corners)/sx)+1)
    bottom=min(height,math.ceil(max(p[1] for p in corners)/sy)+1)
    if right<=left or bottom<=top:
        return {'status':'port_outside_canvas','passed':False,'values':{}}
    roi_image = Image.new('1', (right-left,bottom-top))
    ImageDraw.Draw(roi_image).polygon([(float(p[0]/sx-.5-left), float(p[1]/sy-.5-top)) for p in corners], fill=1)
    domain = np.asarray(roi_image, dtype=bool)
    a, b = [(v[top:bottom,left:right] <= 2) & domain for v in responses]
    values = {'measurement_grid': [width, height], 'distance_unit': 'source_px',
              'core_threshold': 2, 'source_px_per_capture_pixel': [sx, sy],
              'core_pixels_in_port': [int(a.sum()), int(b.sum())],
              'root': row['root'], 'limits': row['limits']}
    if not a.any() or not b.any():
        return {'status': 'missing_solid_port', 'passed': False, 'values': values}
    da = distance_transform_edt(~a, sampling=(sy,sx))
    db = distance_transform_edt(~b, sampling=(sy,sx))
    overlap = a & b
    center_distance = float(db[a].min())
    uncertainty = math.hypot(sx, sy)
    distance_interval = [0., 0.] if overlap.any() else [max(0.,center_distance-uncertainty),center_distance+uncertainty]
    lower, upper = row['limits']['distance_px']
    distance_pass = distance_interval[0] >= lower and distance_interval[1] <= upper
    # Near pixels must be solid in one owner and close to the other within the
    # frozen interval. The calculation does not dilate artwork or repair it.
    near = (a & (db <= upper)) | (b & (da <= upper))
    anchor = world(row['port']['anchor'])
    direction = np.asarray(row['port']['tangent'],dtype=float)
    direction = matrix[:2,:2] @ direction
    direction /= np.linalg.norm(direction)
    yy, xx = np.where(near)
    if len(xx):
        points = np.column_stack(((xx+left+.5)*sx, (yy+top+.5)*sy))
        projected = points @ direction
        # Split disconnected contacts. Two isolated end points may not claim
        # the width of the large empty interval between them.
        components, count = label(near, structure=np.array([[0,1,0],[1,1,1],[0,1,0]],dtype=int))
        contacts=[]
        for k in range(1,count+1):
            own=components[yy,xx]==k
            if row['relationship']=='attached' and not (
                    np.any(a & (components==k)) and np.any(b & (components==k))):
                continue
            pts=projected[own]
            span=max(0.,float(pts.max()-pts.min())-uncertainty)
            error=max(0.,float(np.linalg.norm(points[own]-anchor,axis=1).min())-uncertainty/2)
            contacts.append({'component':k,'solid_width_lower_px':span,'anchor_error_upper_px':error+uncertainty})
        # Width and anchor must be certified by the SAME connected contact.
        eligible=[c for c in contacts if c['anchor_error_upper_px']<=row['limits']['anchor_error_px']]
        best=max(eligible,key=lambda c:c['solid_width_lower_px'],default=None)
        solid_width=best['solid_width_lower_px'] if best else 0.
        anchor_error=best['anchor_error_upper_px']-uncertainty if best else None
        values['contact_components']=contacts
        values['certifying_component']=best['component'] if best else None
    else:
        solid_width=0.;anchor_error=None
    width_pass = solid_width >= row['limits'].get('solid_width_px', 0.)
    anchor_pass = anchor_error is not None and anchor_error <= row['limits']['anchor_error_px']
    values.update(nearest_center_distance_px=center_distance, distance_interval_px=distance_interval,
                  sampling_uncertainty_px=uncertainty, solid_overlap_pixels=int(overlap.sum()),
                  solid_interface_width_lower_px=solid_width, anchor_error_lower_px=anchor_error,
                  distance_pass=distance_pass, width_pass=width_pass, anchor_pass=anchor_pass,
                  interface_quad=[p.tolist() for p in corners])
    # Use an upper bound for anchor acceptance too. A lower-bound-only check
    # would falsely pass a point that lies just outside the permitted radius.
    if anchor_error is not None:
        values['anchor_error_upper_px']=anchor_error+uncertainty
        anchor_pass=values['anchor_error_upper_px'] <= row['limits']['anchor_error_px']
        values['anchor_pass']=anchor_pass
    return {'status':'measured','passed':bool(distance_pass and width_pass and anchor_pass),'values':values}
