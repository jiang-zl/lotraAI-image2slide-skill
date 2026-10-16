"""Typed source-pixel probes on actual saved images, with no candidate alignment."""
import math
import numpy as np
from scipy.ndimage import binary_fill_holes, label, map_coordinates
from scipy.spatial import cKDTree

UNITS = {'edge_angle_error':'degree', 'ellipse_ratio_error':'ratio',
         'extent_ratio_error':'ratio', 'thickness_ratio_error':'ratio',
         'face_color_error':'normalized_rgb', 'face_lightness_error':'normalized_luminance',
         'gradient_profile_error':'normalized_rgb', 'occlusion_color_error':'normalized_rgb',
         'band_width_profile_error':'source_px', 'junction_error':'source_px',
         'hole_count_error':'count', 'feature_missing_fraction':'ratio'}


def validate(metric):
    spec = metric.get('measurement', {}); adapter = spec.get('adapter', metric['id'])
    if adapter not in UNITS: return False
    if (metric.get('unit') != UNITS[adapter] or spec.get('coordinate_space') != 'component_roi'
            or not spec.get('source_evidence')):
        raise ValueError('Surface probe needs registered units and independent original ROI evidence')
    windows = spec.get('windows', [spec.get('window')])
    for box in windows:
        if (not isinstance(box, list) or len(box) != 4 or min(box[:2]) < 0 or min(box[2:]) <= 0 or
                any(type(v) not in (int, float) or not math.isfinite(v) for v in box)):
            raise ValueError('Freeze nonempty original surface probe windows')
    if adapter in ('extent_ratio_error','thickness_ratio_error','face_lightness_error') and len(windows) != 2:
        raise ValueError('A relative face/thickness probe needs two independent original windows')
    if adapter not in ('face_color_error','face_lightness_error','gradient_profile_error','occlusion_color_error'):
        foreground = spec.get('foreground', {})
        _foreground(np.ones((2,2,3)), foreground)
    if adapter == 'band_width_profile_error':
        rays = spec.get('rays', [])
        if not 2 <= len(rays) <= 64 or any(len(r) != 2 for r in rays):
            raise ValueError('Use independent source normal rays across the variable-width band')
    if adapter == 'gradient_profile_error' and not 2 <= len(spec.get('points', [])) <= 64:
        raise ValueError('Freeze a bounded original material profile')
    if adapter == 'junction_error' and len(spec.get('point', [])) != 2:
        raise ValueError('A junction needs its own original-located point')
    return True


def _foreground(pixels, spec):
    threshold = spec.get('threshold')
    if type(threshold) not in (int, float) or not 0 < threshold <= 1:
        raise ValueError('Freeze a source-supported foreground threshold in (0,1]')
    if spec.get('mode') == 'dark': return pixels.mean(axis=2) < threshold
    rgb = spec.get('rgb')
    if (spec.get('mode') != 'color' or not isinstance(rgb, list) or len(rgb) != 3 or
            any(type(v) not in (int,float) or not 0 <= v <= 1 for v in rgb)):
        raise ValueError('Use a dark or explicit normalized source-color selector')
    return np.linalg.norm(pixels-np.asarray(rgb), axis=2) <= threshold


def _crop(data, box):
    x,y,w,h = box; a,b,c,d = math.floor(x),math.floor(y),math.ceil(x+w),math.ceil(y+h)
    if a < 0 or b < 0 or c > data.shape[1] or d > data.shape[0]:
        raise ValueError('Frozen source surface window escaped the actual component ROI')
    return data[b:d,a:c], np.array([a,b])


def _ink(data, box, spec):
    pixels, offset = _crop(data, box); ink = _foreground(pixels, spec['foreground'])
    yy,xx = np.nonzero(ink)
    if len(xx) < spec.get('min_pixels', 4): raise ValueError('Unresolved source/candidate surface support')
    return np.column_stack((xx+.5,yy+.5))+offset, ink


def _axes(points):
    values,vectors = np.linalg.eigh(np.cov(points.T))
    if values[-1] < 1e-8: raise ValueError('Degenerate source/candidate geometric support')
    return values,vectors


def _profile(data, points):
    points = np.asarray(points, float)
    if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
        raise ValueError('Finite source profile anchors required')
    samples = []
    for a,b in zip(points[:-1],points[1:]):
        n = min(4096,max(2,math.ceil(np.linalg.norm(b-a)*4)+1))
        samples.extend(np.linspace(a,b,n).tolist())
    if len(samples) > 4096: raise ValueError('Source profile sampling budget exceeded')
    q = np.asarray(samples)
    if (q[:,0].min() < 0 or q[:,1].min() < 0 or q[:,0].max() >= data.shape[1] or q[:,1].max() >= data.shape[0]):
        raise ValueError('Original profile escaped its source/candidate window')
    return np.column_stack([map_coordinates(data[:,:,i],[q[:,1]-.5,q[:,0]-.5],order=1,mode='nearest') for i in range(3)])


def _chord(data, ray, spec):
    values = _profile(data, ray)
    ink = _foreground(values[None,:,:], spec['foreground'])[0]
    indices = np.flatnonzero(ink)
    if not len(indices): raise ValueError('Declared band is absent at a frozen source normal ray')
    starts = np.flatnonzero(np.diff(np.r_[False,ink,False].astype(int)) == 1)
    if len(starts) != 1 or ink[0] or ink[-1]:
        raise ValueError('Source band ray is clipped or crosses several unrelated strokes')
    return len(indices)*math.dist(*ray)/max(1,len(ink)-1)


def measure(original, actual, metric):
    spec = metric['measurement']; name = spec.get('adapter', metric['id'])
    try:
        windows = spec.get('windows',[spec.get('window')]); window = windows[0]
        def extent(data, box):
            points,_ = _ink(data, box, spec)
            axis = np.asarray(spec.get('axis_vector',[1,0]),float)
            if axis.shape != (2,) or not np.isfinite(axis).all() or np.linalg.norm(axis) < 1e-10:
                raise ValueError('Source extent needs a fixed nonzero axis')
            projected = points @ (axis/np.linalg.norm(axis))
            return float(np.ptp(projected)+1)
        def median(data, box): return np.median(_crop(data,box)[0].reshape(-1,3),axis=0)
        if name in ('face_color_error','occlusion_color_error'):
            value = float(np.linalg.norm(median(original,window)-median(actual,window))/math.sqrt(3))
        elif name == 'face_lightness_error':
            def difference(data):
                return float((median(data,windows[0])-median(data,windows[1])) @ np.array([.2126,.7152,.0722]))
            value = abs(difference(actual)-difference(original))
        elif name == 'gradient_profile_error':
            source = _profile(original,spec['points']); target = _profile(actual,spec['points'])
            value = float(np.max(np.linalg.norm(source-target,axis=1))/math.sqrt(3))
        elif name in ('extent_ratio_error','thickness_ratio_error'):
            def ratio(data): return extent(data,windows[0])/extent(data,windows[1])
            value = abs(ratio(actual)-ratio(original))
        elif name in ('edge_angle_error','ellipse_ratio_error'):
            measurements = []
            for data in (original,actual):
                points,_ = _ink(data,window,spec); values,vectors = _axes(points)
                if name == 'edge_angle_error':
                    if values[-1] < 2*max(values[0],1e-8):
                        raise ValueError('No stable independently measurable edge orientation')
                    measurements.append(math.degrees(math.atan2(vectors[1,-1],vectors[0,-1]))%180)
                else: measurements.append(math.sqrt(max(0,values[0])/values[-1]))
            value = abs(measurements[0]-measurements[1])
            if name == 'edge_angle_error': value = min(value,180-value)
        elif name == 'band_width_profile_error':
            value = max(abs(_chord(original,r,spec)-_chord(actual,r,spec)) for r in spec['rays'])
        elif name == 'hole_count_error':
            counts = []
            for data in (original,actual):
                _,ink = _ink(data,window,spec)
                holes = binary_fill_holes(ink)&~ink; labels,n = label(holes)
                counts.append(sum(np.count_nonzero(labels==i) >= spec.get('min_hole_pixels',4) for i in range(1,n+1)))
            value = abs(counts[0]-counts[1])
        elif name == 'feature_missing_fraction':
            source,_ = _ink(original,window,spec)
            try: target,_ = _ink(actual,window,spec)
            except ValueError: target = np.empty((0,2))
            radius = spec.get('support_radius_px',1)
            if not 0 <= radius <= 3: raise ValueError('Freeze bounded source boundary support precision')
            value = 1. if not len(target) else float(np.mean(cKDTree(target).query(source)[0] > radius))
        elif name == 'junction_error':
            point = np.asarray(spec['point'],float)
            if point.shape != (2,) or not np.isfinite(point).all(): raise ValueError('Finite located source junction required')
            source,_ = _ink(original,window,spec); target,_ = _ink(actual,window,spec)
            value = max(0,float(np.min(np.linalg.norm(target-point,axis=1))-np.min(np.linalg.norm(source-point,axis=1))))
        else: raise ValueError('Unsupported registered surface producer')
        if not math.isfinite(value): raise ValueError('Nonfinite surface measurement')
        return {'valid':True,'value':float(value),'unit':UNITS[name],
                'adapter':name,'coordinate_space':'component_roi','candidate_alignment':False}
    except (ValueError,IndexError,KeyError,TypeError) as error:
        return {'valid':False,'value':None,'unit':UNITS[name],'adapter':name,
                'reason':str(error),'candidate_alignment':False}
