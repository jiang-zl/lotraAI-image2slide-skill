"""Source-bound low-dimensional functions -> bounded native cubic paths.

Samples are program evidence, never a request for the host to type pixels.
Numeric fit and encoding bounds do not qualify the saved slide appearance.
"""
import copy
import math
import numpy as np
from scipy.interpolate import PchipInterpolator, CubicSpline
from scipy.spatial import cKDTree
from .common import identity, read_json, write_json, digest, safe_path

VERSION = 'functional-curves-1'
FAMILIES = {'periodic': ('fourier', 'trend_envelope', 'piecewise_cubic'),
            'damped': ('damped', 'trend_envelope', 'piecewise_cubic'),
            'monotone': ('pchip', 'piecewise_cubic'),
            'pulse': ('pulse', 'piecewise_cubic'),
            'step': ('step', 'piecewise_cubic'),
            'unknown': ('piecewise_cubic', 'parametric_cubic'),
            'loop': ('parametric_cubic',)}


def tolerances(spec):
    u = float(spec['source_uncertainty_px']); q = float(spec.get('representation_precision_px', .05))
    separation = float(spec['critical_feature_separation_px'])
    if not all(math.isfinite(v) for v in (u, q, separation)) or min(u, q) < 0 or separation <= 0:
        raise ValueError('Source-bound finite curve uncertainty and critical separation required')
    preferred = min(1.5, max(.3, u + q))
    acceptable = min(3., preferred * 2, separation * .15)
    if u + q > acceptable or acceptable < preferred:
        raise ValueError('SOURCE_AMBIGUITY: curve uncertainty exceeds its semantic feature cap')
    return {'preferred_px': preferred, 'acceptable_px': acceptable, 'encoding_px': preferred / 4,
            'basis': 'original uncertainty + representation; capped by critical feature separation'}


def samples(task, spec):
    ref = spec.get('samples_ref')
    if not ref or not spec.get('source_evidence'):
        raise ValueError('Functional curve needs independent original samples_ref and located semantic evidence')
    file = safe_path(task, ref['path'])
    if digest(file) != ref['sha256']:
        raise ValueError('Original curve evidence changed')
    data = read_json(file)
    points = np.asarray(data['points'], float)
    if data.get('source_hash') != spec['source_hash'] or data.get('coordinate_space') != 'source_px':
        raise ValueError('Curve samples must bind the unchanged source in source_px')
    if points.ndim != 2 or points.shape[1] != 2 or not 4 <= len(points) <= 16384 or not np.isfinite(points).all():
        raise ValueError('Ordered finite source curve evidence required')
    return points


def _semantic(points, spec, error):
    """Only explicit source features are hard; unlabelled tiny wiggles are not."""
    checks = {'finite': bool(np.isfinite(points).all())}
    t = np.linspace(0, 1, len(points))
    for i, rule in enumerate(spec.get('constraints', [])):
        kind = rule['kind']; tol = float(rule.get('tolerance_px', error))
        if not rule.get('source_evidence'):
            raise ValueError('Each semantic constraint needs its original evidence')
        if kind == 'point':
            at = float(rule['t']); expected = np.asarray(rule['point'], float)
            actual = np.array([np.interp(at, t, points[:, j]) for j in (0, 1)])
            ok = np.linalg.norm(actual - expected) <= tol
        elif kind == 'monotone':
            axis = int(rule.get('axis', 1)); sign = int(rule['direction'])
            ok = np.all(np.diff(points[:, axis]) * sign >= -tol)
        elif kind == 'range':
            values = points[:, int(rule.get('axis', 1))]
            ok = values.min() >= rule['min'] - tol and values.max() <= rule['max'] + tol
        elif kind == 'closed':
            ok = np.linalg.norm(points[0] - points[-1]) <= tol
        elif kind == 'peak_count':
            from scipy.signal import find_peaks
            values = points[:, int(rule.get('axis', 1))] * int(rule.get('sign', 1))
            peaks = find_peaks(values, prominence=rule['prominence_px'])[0]
            ok = int(rule['min']) <= len(peaks) <= int(rule['max'])
        else:
            raise ValueError('Unsupported semantic curve constraint: ' + kind)
        checks[str(i) + ':' + kind] = bool(ok)
    return checks


def _model(points, family, complexity, spec):
    parametric = family == 'parametric_cubic'
    if parametric:
        step = np.linalg.norm(np.diff(points, axis=0), axis=1)
        if step.sum() <= 0:
            raise ValueError('Degenerate source curve')
        t = np.r_[0, np.cumsum(step)] / step.sum()
        keep = np.r_[True, np.diff(t) > 1e-10]; t, points = t[keep], points[keep]
    else:
        if not np.all(np.diff(points[:, 0]) > 0):
            raise ValueError('NON_SINGLE_VALUED: use an ordered parametric curve')
        t = (points[:, 0] - points[0, 0]) / (points[-1, 0] - points[0, 0])
    lo, hi = points[0, 0], points[-1, 0]
    def x(u): return lo + np.asarray(u) * (hi - lo)
    detail = {'family': family, 'complexity': complexity}
    if family in ('pchip', 'piecewise_cubic', 'parametric_cubic'):
        knots = np.linspace(0, 1, min(len(points), complexity + 1))
        values = np.column_stack([np.interp(knots, t, points[:, j]) for j in (0, 1)])
        constructor = PchipInterpolator if family == 'pchip' else CubicSpline
        curves = [constructor(knots, values[:, j]) for j in (0, 1)]
        detail.update(knots=knots.tolist(), values=values.tolist())
        def fn(u): return np.column_stack([c(u) for c in curves])
        def derivative(u): return np.column_stack([c(u, 1) for c in curves])
        return fn, derivative, detail, knots
    frequency = float(spec.get('cycles', 1))
    if family in ('fourier','trend_envelope','damped') and 'cycles' not in spec:
        raise ValueError('Declare source-observed cycles before selecting an oscillation family')
    if not 0 < frequency <= 128:
        raise ValueError('Freeze source-observed relative cycle count; no invented physical frequency')
    if family in ('fourier','trend_envelope','damped') and frequency*complexity>min(64,(len(points)-1)/4):
        raise ValueError('Source sampling and native complexity cannot identify this many harmonics')
    damping = float(spec.get('damping', 1))
    def design(u):
        u = np.asarray(u); columns = [np.ones_like(u), u]
        if family == 'step':
            columns += [(u >= float(at)).astype(float) for at in spec.get('transition_t', [])]
        elif family == 'pulse':
            columns += [np.exp(-.5 * ((u - float(p['center_t'])) / float(p['width_t'])) ** 2) for p in spec.get('pulses', []) if 0 < float(p['width_t']) <= 1]
        else:
            envelope = np.exp(-damping * u) if family == 'damped' else np.ones_like(u)
            for k in range(1, complexity + 1):
                for trig in (np.sin, np.cos):
                    wave = envelope * trig(2 * np.pi * frequency * k * u)
                    columns.append(wave)
                    if family == 'trend_envelope': columns.append(u * wave)
        return np.column_stack(columns)
    if family in ('step', 'pulse') and len(design(t)[0]) == 2:
        raise ValueError('Source-observed transitions/pulses required')
    coefficients = np.linalg.lstsq(design(t), points[:, 1], rcond=None)[0]
    detail.update(coefficients=coefficients.tolist(), cycles=frequency, damping=damping)
    def fn(u): return np.column_stack((x(u), design(u) @ coefficients))
    def derivative(u):
        if family=='step':return np.column_stack((np.full_like(np.asarray(u),hi-lo),np.full_like(np.asarray(u),coefficients[1])))
        u = np.asarray(u); a = np.maximum(0, u - 1e-5); b = np.minimum(1, u + 1e-5)
        return (fn(b) - fn(a)) / (b - a)[:, None]
    # Discontinuous steps are encoded as separate pieces, never a smoothed bridge.
    transitions=spec.get('transition_t', [])
    if any(not 0<float(v)<1 for v in transitions):raise ValueError('Observed transitions must lie inside the curve domain')
    count=max(2,math.ceil(complexity*frequency*4)) if family in ('fourier','trend_envelope','damped') else 2
    knots = np.unique(np.r_[np.linspace(0, 1, count + 1), transitions])
    return fn, derivative, detail, knots


def _encode(fn, derivative, knots, tolerance, max_segments=128, breaks=()):
    commands = []; segments = 0; maximum = 0.
    def segment(a, b, depth=0):
        nonlocal segments, maximum
        p, q = fn(np.array([a, b])); da, db = derivative(np.array([a, b]))
        controls = np.array([p, p + da * (b-a)/3, q - db * (b-a)/3, q])
        u = np.linspace(0, 1, 17)
        encoded = sum(math.comb(3, i) * (1-u)[:, None] ** (3-i) * u[:, None] ** i * controls[i] for i in range(4))
        error = float(np.max(np.linalg.norm(encoded - fn(a + u*(b-a)), axis=1)))
        if error > tolerance:
            if depth >= 12 or segments >= max_segments-1:
                raise ValueError('NATIVE_ENCODING_LIMIT: function needs too many native segments')
            segment(a, (a+b)/2, depth+1); segment((a+b)/2, b, depth+1); return
        if segments >= max_segments:
            raise ValueError('NATIVE_ENCODING_LIMIT: segment budget reached')
        segments += 1; maximum = max(maximum, error)
        commands.append({'op': 'cubicBezTo', 'points': controls[1:].tolist()})
    for a, b in zip(knots[:-1], knots[1:]):
        left = float(a); right = float(b)
        if left in breaks: left = np.nextafter(left, right)
        if right in breaks: right = np.nextafter(right, left)
        if not commands or float(a) in breaks:
            commands.append({'op': 'moveTo', 'points': fn(np.array([left])).tolist()})
        segment(left, right)
    return commands, {'segments': segments, 'encoding_max_px': maximum}


def compile_node(task, state, row, node):
    spec = copy.deepcopy(node['content']['function_spec'])
    spec['source_hash'] = state['source']['sha256']
    profile = tolerances(spec); points = samples(task, spec)
    if spec.get('semantics','unknown')!='unknown' and not spec.get('constraints'):
        raise ValueError('SEMANTIC_FEATURES_REQUIRED: declare source-supported trend/peaks/range/closure constraints')
    spec.setdefault('constraints',[])
    for t,point in ((0,points[0]),(1,points[-1])):
        spec['constraints'].append({'kind':'point','t':t,'point':point.tolist(),'tolerance_px':profile['preferred_px'],'source_evidence':spec['source_evidence']})
    signature = identity({'spec': spec, 'profile': profile, 'compiler': digest(__file__)})
    folder = task / 'component-workflow/curves'; folder.mkdir(parents=True, exist_ok=True)
    file = folder / (signature + '.json')
    if file.exists():
        report = read_json(file)
    else:
        from . import problem_control as pc
        families = FAMILIES.get(spec.get('semantics', 'unknown'))
        if not families: raise ValueError('Unsupported curve semantic class')
        best = None; preferred = None; failures = []
        for family in families:
            # Model-family reservation shares the very same original problem.
            family_row = copy.deepcopy(row); family_row['model'] = {'id': family, 'family': family}
            shadow = {'workflow_version': '1.33.0', 'components': [family_row], 'source_inventory': []}
            try: pc.bind(task, state, shadow)
            except ValueError as error: failures.append(str(error)); break
            for complexity in (2, 4, 8, 16, 32):
                if pc.remaining(task, state, row, 'evaluations') <= 0: break
                pc.reserve(task, state, row, 'evaluations')
                try:
                    fn, derivative, model, knots = _model(points, family, complexity, spec)
                    actual = fn(np.linspace(0, 1, max(1025, min(8193, len(points)*4))))
                    length=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
                    support=np.column_stack([np.interp(np.linspace(0,length[-1],8193),length,points[:,j]) for j in (0,1)])
                    distances = np.r_[cKDTree(actual).query(support)[0], cKDTree(support).query(actual)[0]]
                    # Source sampling spacing is an evidence uncertainty, not a candidate-derived allowance.
                    error = float(np.max(distances)); checks = _semantic(actual, spec, profile['preferred_px'])
                    if not all(checks.values()) or error > profile['acceptable_px']: continue
                    commands, encoding = _encode(fn, derivative, knots, profile['encoding_px'], breaks=spec.get('transition_t', []) if family == 'step' else ())
                    item = {'model': model, 'commands': commands, 'fit_max_px': error, 'semantic_checks': checks, **encoding,
                            'quality_tier': 'preferred' if error <= profile['preferred_px'] else 'acceptable'}
                    if best is None or (item['segments'], error) < (best['segments'], best['fit_max_px']): best = item
                    if item['quality_tier'] == 'preferred': preferred = item; break
                except (ValueError, np.linalg.LinAlgError) as error: failures.append(family + ': ' + str(error))
            if preferred or best: break  # Acceptable is a valid terminal tier; do not chase pixel detail.
        report = {'schema': VERSION, 'source_hash': spec['source_hash'], 'spec_hash': identity(spec), 'profile': profile,
                  'result': preferred or best, 'failures': failures[-6:], 'acceptance': False}
        write_json(file, report)
    if not report['result']:
        raise ValueError('CURVE_DECISION_REQUIRED: no semantic-preserving function within frozen tolerance; report=' + file.relative_to(task).as_posix())
    x, y, w, h = node['bbox']; chosen = report['result']
    commands = [{'op': c['op'], 'points': [[(p[0]-x)/w, (p[1]-y)/h] for p in c['points']]} for c in chosen['commands']]
    node['content']['contours'] = [{'commands': commands, 'closed': bool(spec.get('closed', False))}]
    node['content']['function_report'] = {'path': file.relative_to(task).as_posix(), 'sha256': digest(file)}
    node['content']['curve_compilation'] = {'version': VERSION, 'method': 'function_native_cubic', 'quality_tier': chosen['quality_tier']}
    row['curve_profile'] = profile; row['curve_spec_hash'] = identity(spec);row['curve_semantics']=spec.get('semantics','unknown')
    row['curve_parametric']=chosen['model']['family']=='parametric_cubic'
    row['curve_evidence'] = {'samples_ref': spec['samples_ref'], 'source_evidence': spec['source_evidence'], 'constraints': spec.get('constraints', [])}
    return node


def prepare(task, state, contract, scene, execute=True):
    """Called before native construction. Saved appearance still uses evaluate."""
    if contract.get('workflow_version') not in ('1.33.0','1.34.0','1.35.0','1.35.1'): return scene
    from .problem_control import bind
    nodes = {o['id']: o for o in scene['objects']}
    for row in contract['components']:
        curves=[nodes[o] for o in row['owners'] if nodes[o]['content'].get('function_spec')]
        # New scientific/unknown curves must choose functions rather than dense host-authored pixels.
        from .semantic_curves import SCIENTIFIC
        if any(nodes[o]['semantic_type'] in SCIENTIFIC and not nodes[o]['content'].get('function_spec') for o in row['owners']):
            raise ValueError('FUNCTION_SPEC_REQUIRED: retain program source samples and declare semantic function constraints')
        for node in curves:
            if len(curves)>1 or row['route']!='local_fit' or not row.get('roi'):
                raise ValueError('Each functional curve requires its own original-bound local_fit part/ROI')
            if not any(m['role']=='target' and m.get('measurement',{}).get('adapter')=='curve_distance' for m in row.get('metrics',[])):
                raise ValueError('Independent actual curve_distance target required before function fitting')
            row['curve_profile']=tolerances(node['content']['function_spec'])
            row['model']={'id':'functional_curve','version':1,'curve_precision_source_px':row['curve_profile']['encoding_px']}
            row['fit']={'adapter':'function_native','bindings':{}}
            original_spec={**node['content']['function_spec'],'source_hash':state['source']['sha256']}
            original_points=samples(task,original_spec)
            for metric in row.get('metrics',[]):
                if metric.get('measurement',{}).get('adapter')=='curve_distance':
                    metric['threshold']=row['curve_profile']['preferred_px']
                    metric['acceptable_threshold']=row['curve_profile']['acceptable_px']
                    # Materialize independent evidence inside the program;
                    # the host submits one samples_ref, never a second point list.
                    measurement=metric['measurement']
                    if not measurement.get('source_points'):
                        selected=np.linspace(0,len(original_points)-1,min(4096,len(original_points))).round().astype(int)
                        measurement['source_points']=(original_points[selected]-np.array(row['roi'][:2])).tolist()
                        measurement['source_samples_ref']=original_spec['samples_ref']
                    measurement.setdefault('source_evidence',original_spec['source_evidence'])
    if not execute:return scene
    bind(task, state, contract)
    for row in contract['components']:
        curves = [nodes[o] for o in row['owners'] if nodes[o]['content'].get('function_spec')]
        if len(curves) > 1: raise ValueError('Give each uncertain functional curve its own part/problem')
        for node in curves:
            compile_node(task, state, row, node)
            if row['route'] != 'local_fit' or not any(m['role'] == 'target' and m.get('measurement', {}).get('adapter') == 'curve_distance' for m in row.get('metrics', [])):
                raise ValueError('Functional curves require local_fit and independent actual curve_distance target')
            for metric in row['metrics']:
                if metric.get('measurement', {}).get('adapter') == 'curve_distance':
                    metric['threshold'] = row['curve_profile']['preferred_px']
                    metric['acceptable_threshold'] = row['curve_profile']['acceptable_px']
    return scene


def actual_checks(actual, row):
    evidence=row.get('curve_evidence')
    if not evidence: return {}
    metric=next(m for m in row['metrics'] if m.get('measurement',{}).get('adapter')=='curve_distance')
    from .component_features import foreground
    spec=metric['measurement']; ink=foreground(actual,spec['foreground'])
    x,y,w,h=spec['window']; gate=np.zeros_like(ink);gate[int(y):math.ceil(y+h),int(x):math.ceil(x+w)]=True
    yy,xx=np.nonzero(ink & gate)
    if not len(xx): return {'curve_semantics':False}
    # Order only an x-valued waveform. Non-single-valued shapes use range/closure/point gates plus current local visual review.
    points=np.array([[u+.5,float(np.median(yy[xx==u]))+.5] for u in sorted(set(xx))])
    points+=np.array(row['roi'][:2])
    rules=evidence['constraints']
    if row.get('curve_semantics')=='loop' or row.get('curve_parametric'):
        from scipy.ndimage import label,convolve
        from skimage.morphology import skeletonize
        skeleton=skeletonize(ink & gate);degree=convolve(skeleton.astype(int),np.ones((3,3),int),mode='constant')-skeleton
        checks={'loop_connected':label(skeleton,np.ones((3,3),int))[1]==1}
        if any(r['kind']=='closed' for r in rules):checks['loop_closed']=not bool(np.any(skeleton & (degree==1)))
        cloud=np.column_stack((xx+.5,yy+.5))+np.array(row['roi'][:2])
        for i,rule in enumerate(rules):
            if rule['kind']=='point':checks['point_'+str(i)]=float(cKDTree(cloud).query(rule['point'])[0])<=rule.get('tolerance_px',row['curve_profile']['preferred_px'])
            elif rule['kind']=='range':
                values=cloud[:,int(rule.get('axis',1))];tol=rule.get('tolerance_px',row['curve_profile']['preferred_px'])
                checks['range_'+str(i)]=bool(values.min()>=rule['min']-tol and values.max()<=rule['max']+tol)
        return {'curve_semantic_'+k:bool(v) for k,v in checks.items()}
    return {'curve_semantic_'+k:v for k,v in _semantic(points,{'constraints':rules},row['curve_profile']['preferred_px']).items()}
