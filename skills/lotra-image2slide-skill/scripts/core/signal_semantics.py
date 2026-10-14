"""Source-bound schematic signal functions and auxiliary text relationships.

Strength is amplitude/energy, not a universal frequency ordering. This module
never synthesizes scientific observations. Actual saved renders are measured
at the common original-pixel scale, without separate amplitude normalization.
"""
import copy
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.interpolate import PchipInterpolator
from skimage.metrics import structural_similarity

from .common import digest, identity, read_json, write_json, safe_path

VERSION = 'signal-semantics-1'
SIGNAL = re.compile(r'(signal|wave|noise|波形|信号|噪声)', re.I)
RELATIONS = frozenset(('amplitude_greater', 'rms_greater', 'frequency_greater', 'frequency_lower', 'source_order'))


def _finite(value):
    from .source_contract import finite
    finite(value, 'signal_contract')


def _source(task, state):
    file = safe_path(task, state['source']['path'])
    if digest(file) != state['source']['sha256']:
        raise ValueError('Signal source changed')
    return file


def _points(values, roi):
    if not isinstance(values, list) or len(values) < 4:
        raise ValueError('At least four actually observed signal points required')
    _finite(values)
    data = np.asarray(values, dtype=float)
    if data.ndim != 2 or data.shape[1] != 2 or np.any(np.diff(data[:, 0]) <= 0):
        raise ValueError('A signal function needs strictly ordered finite x/y samples')
    x, y, w, h = roi
    if np.any(data[:, 0] < x) or np.any(data[:, 0] > x+w) or np.any(data[:, 1] < y) or np.any(data[:, 1] > y+h):
        raise ValueError('Observed signal points escaped the original source ROI')
    return data


def isolate(source, roi, colour='444444', tolerance=125, trace_mode='column_center'):
    x, y, w, h = map(int, roi)
    with Image.open(source) as image:
        rgb = np.asarray(image.convert('RGB').crop((x, y, x+w, y+h))).astype(float)
    target = np.array([int(colour[i:i+2], 16) for i in (0, 2, 4)])
    mask = np.linalg.norm(rgb-target, axis=2) <= tolerance
    if np.ptp(target) < 25:
        mask &= np.max(rgb, axis=2)-np.min(rgb, axis=2) < 40
        mask &= np.mean(rgb, axis=2) < min(205, float(target.mean())+100)
    if trace_mode not in ('column_center','envelope_extrema'):
        raise ValueError('Use a finite explicit schematic signal tracing method')
    visible=np.nonzero(mask)[0]
    baseline=float(np.median(visible)) if len(visible) else 0
    points = []
    for col in range(w):
        rows = np.flatnonzero(mask[:, col])
        if len(rows):
            centre=float(np.median(rows))
            if trace_mode=='envelope_extrema' and len(rows)>2:
                upper,lower=float(np.percentile(rows,10)),float(np.percentile(rows,90))
                if baseline-upper>lower-baseline+.5:centre=upper
                elif lower-baseline>baseline-upper+.5:centre=lower
            points.append([x+col+.5, y+centre+.5])
    if len(points) < 4:
        raise ValueError('Source signal not isolated; inspect the crop and provide observed points')
    return points


def function(spec):
    """Return global-coordinate samples from an explicit illustration function."""
    _finite(spec)
    if spec.get('purpose') != 'schematic_signal':
        raise ValueError('Signal synthesis is restricted to source-supported schematic icons')
    roi = spec['source_roi']
    family = spec.get('family')
    count = spec.get('samples', 160)
    if type(count) is not int or not 16 <= count <= 2048:
        raise ValueError('Bounded signal sampling count required')
    if family == 'observed_spline':
        data = _points(spec['observed_points'], roi)
        xx = np.linspace(data[0, 0], data[-1, 0], count)
        yy = PchipInterpolator(data[:, 0], data[:, 1])(xx)
    elif family in ('carrier_envelope', 'damped_pulse'):
        x, y, w, h = roi
        p = spec['parameters']
        baseline, amplitude = p['baseline_y'], p['amplitude_px']
        cycles, phase = p['cycles'], p.get('phase_radians', 0)
        if amplitude <= 0 or cycles <= 0 or not p.get('source_evidence'):
            raise ValueError('Observed amplitude/cycles and located original evidence required')
        t = np.linspace(0, 1, count)
        centre, spread = p.get('envelope_centre', .5), p.get('envelope_spread', .25)
        if not 0 <= centre <= 1 or spread <= 0:
            raise ValueError('Finite source-supported signal envelope required')
        envelope = np.exp(-.5*((t-centre)/spread)**2)
        if family == 'damped_pulse':
            envelope *= np.exp(-p.get('decay', 0)*np.maximum(t-centre, 0))
        xx = x+t*w
        yy = baseline+amplitude*envelope*np.sin(2*np.pi*cycles*t+phase)
        _points(np.column_stack((xx, yy)).tolist(), roi)
    else:
        raise ValueError('Unknown signal function family')
    return np.column_stack((xx, yy)).tolist()


def construct(task, state, component, spec):
    from .recipes import node, path
    if spec.get('source_hash') != state['source']['sha256']:
        raise ValueError('Signal function must bind the unchanged original')
    _finite(spec)
    if spec.get('source_roi')!=component['roi']:
        raise ValueError('Signal constructor must use its exact frozen source unit ROI')
    _source(task, state)
    cid = component['id']
    if spec.get('family')=='observed_contours':
        return _contour_signal(task,state,component,spec)
    points = function(spec)
    curve_id = spec.get('curve_id', cid+'.curve')
    root = node(cid, 'group', component.get('bbox', component['roi']), semantic=component['semantic_class'])
    curve = path(curve_id, points, cid, spec.get('colour', '444444'), width=spec.get('line_width', .7), semantic='signal_wave')
    # Preserve the source-fitted PCHIP function as native cubic segments rather
    # than displaying a dense jagged polyline or smoothing scientific data.
    if spec['family'] == 'observed_spline':
        observed = _points(spec['observed_points'], spec['source_roi'])
        spline = PchipInterpolator(observed[:, 0], observed[:, 1])
        deriv = spline.derivative()
        commands = [{'op': 'moveTo', 'points': [observed[0].tolist()]}]
        for a, b in zip(observed[:-1], observed[1:]):
            d = (b[0]-a[0])/3
            commands.append({'op': 'cubicBezTo', 'points': [[a[0]+d, a[1]+float(deriv(a[0]))*d],
                [b[0]-d, b[1]-float(deriv(b[0]))*d], b.tolist()]})
        from .semantic_curves import contour_node
        curve = contour_node(curve_id, commands, cid, spec.get('colour', '444444'), None,
                             spec.get('line_width', .7), 'signal_wave', False)
    return [root, curve]


def _contour_signal(task,state,component,spec):
    """Editable source-supported signal silhouettes, never scientific data.

    A dense illustrated waveform can have several y values at one x pixel.
    A single centre-line would erase its oscillations. Thresholded original
    level sets retain the upper/lower peaks as bounded native closed curves.
    No raster is embedded and no output blur is generated.
    """
    from skimage.measure import find_contours
    from .recipes import node
    from .semantic_curves import contour_node
    if spec.get('purpose')!='schematic_signal' or not spec.get('source_evidence'):
        raise ValueError('Observed illustrated signal silhouette requires original evidence')
    x,y,w,h=spec['source_roi']
    if any(type(v) is not int for v in (x,y,w,h)) or not 4<=w<=1024 or not 3<=h<=256:
        raise ValueError('Bounded integer source signal silhouette ROI required')
    with Image.open(_source(task,state)) as im:
        rgb=np.asarray(im.convert('RGB').crop((x,y,x+w,y+h))).astype(float)
    neutral=np.ptp(rgb,axis=2)<40
    gray=rgb.mean(axis=2);gray[~neutral]=255
    levels=spec.get('levels',[224,192,160,128,96,64])
    if (not 3<=len(levels)<=12 or any(type(v) is not int or not 16<=v<=240 for v in levels)
            or levels!=sorted(set(levels),reverse=True)):
        raise ValueError('Freeze a finite distinct source-supported gray contour palette')
    cid=component['id'];out=[node(cid,'group',component.get('bbox',component['roi']),semantic=component['semantic_class'])]
    for level in levels:
        ink=gray<=level
        # Ignore isolated compression dots; their meaning is independently
        # reviewed in the original region, not inferred from this threshold.
        for i,contour in enumerate(find_contours(np.pad(ink,1).astype(float),.5)):
            if len(contour)<5:continue
            xx=contour[:,1]-1+x+.5;yy=contour[:,0]-1+y+.5
            if (xx.max()-xx.min())*(yy.max()-yy.min())<1:continue
            points=np.column_stack((xx,yy)).tolist()
            commands=[{'op':'moveTo','points':[points[0]]}]+[{'op':'lnTo','points':[p]} for p in points[1:]]+[{'op':'close','points':[]}]
            value=max(0,level-16);colour=f'{value:02X}'*3
            out.append(contour_node(f'{cid}.level_{level}_{i}',commands,cid,None,colour,0,'signal_wave',True))
            if len(out)>256:raise ValueError('Source signal silhouette too complex; reobserve rather than lose content')
    if len(out)==1:raise ValueError('No source waveform silhouette extracted')
    return out


def discover(state):
    rows = []
    for uid, unit in state.get('quality', {}).get('units', {}).items():
        if unit.get('profile') == 'curve' and SIGNAL.search(uid+' '+str(unit.get('source_part', ''))):
            rows.append({'id': uid, 'owner': unit.get('owner'), 'roi': unit.get('roi'),
                         'objects': unit.get('objects', []), 'source_features': unit.get('features', [])})
    tree_ref = state.get('source_recursion')
    # Discovery from source units is independent of the candidate's ability to
    # paint the curve; every registered signal remains an obligation.
    return rows


def nearby_labels(state, signal):
    a=signal['roi'];limit=max(a[2],a[3])*2
    rows=[]
    for unit in state.get('quality',{}).get('units',{}).values():
        if unit.get('profile')!='text' or not unit.get('roi'):
            continue
        b=unit['roi'];dx=max(a[0]-b[0]-b[2],b[0]-a[0]-a[2],0);dy=max(a[1]-b[1]-b[3],b[1]-a[1]-a[3],0)
        gap=math.hypot(dx,dy)
        if gap<=limit:
            rows.append({'unit':unit['id'],'objects':unit.get('objects',[]),'roi':b,
                         'gap_original_px':gap,'source_features':unit.get('features',[])})
    return sorted(rows,key=lambda r:r['gap_original_px'])[:6]


def bind(task, state, request):
    if request.get('source_hash') != state['source']['sha256']:
        raise ValueError('Signal contract source mismatch')
    known = {r['id']: r for r in discover(state)}
    signals = request.get('signals', [])
    if not signals or len({r.get('id') for r in signals}) != len(signals):
        raise ValueError('Unique source signal contracts required')
    ledger = copy.deepcopy(state.get('signal_semantics', {'schema': VERSION, 'signals': {}, 'relations': {}, 'history': []}))
    for signal in signals:
        key = signal.get('id')
        if key not in known or signal.get('purpose') not in ('schematic_signal','radiating_bands') or not signal.get('evidence'):
            raise ValueError('A declared source signal and located visual evidence are required')
        if signal.get('roi') != known[key]['roi']:
            raise ValueError('Signal ROI differs from its frozen source unit')
        if signal['purpose']=='schematic_signal':_points(signal.get('source_points'), signal['roi'])
        else:
            if not signal.get('band_objects') or type(signal.get('source_band_count')) is not int or signal['source_band_count']!=len(signal['band_objects']):
                raise ValueError('Original radiating mark requires its observed bands and exact native owners')
        labels = signal.get('labels', [])
        if not isinstance(labels, list):
            raise ValueError('Explicit associated source text owners/literals required')
        for label in labels:
            if not label.get('owner') or not label.get('literal') or not label.get('source_evidence'):
                raise ValueError('Label relationship needs actual text and source evidence')
        if not labels and not signal.get('label_association_reason'):
            raise ValueError('No associated text requires an explicit original-based reason')
        constraints = signal.get('constraints', {})
        if any(k not in ('curve_error_px', 'ssim_min', 'psnr_min', 'amplitude_relative_error', 'envelope_relative_error') for k in constraints):
            raise ValueError('Unknown signal metric constraint')
        _finite(signal)
        if signal.get('confidence') == 'unresolved':
            raise ValueError('Unresolved signal reading must return to original observation')
        if key in ledger['signals'] and ledger['signals'][key] != signal:
            ledger['history'].append(ledger['signals'][key])
        ledger['signals'][key] = copy.deepcopy(signal)
    for relation in request.get('relations', []):
        a, b = relation.get('strong'), relation.get('weak')
        kind = relation.get('predicate')
        if (a not in ledger['signals'] or b not in ledger['signals'] or a == b or kind not in RELATIONS or not relation.get('source_evidence')
                or ledger['signals'][a]['purpose']!='schematic_signal' or ledger['signals'][b]['purpose']!='schematic_signal'):
            raise ValueError('Typed source/text signal relationship required')
        if kind.startswith('frequency_') and relation.get('frequency_basis') not in ('explicit_text', 'observed_source_order'):
            raise ValueError('Signal strength alone cannot imply frequency ordering')
        if kind == 'source_order' and relation.get('metric') not in ('peak_to_peak_px','rms_px','dominant_cycles_per_original_pixel'):
            raise ValueError('Source order must name an executable signal descriptor')
        key = relation.get('id')
        if not key:
            raise ValueError('Signal relation id required')
        ledger['relations'][key] = copy.deepcopy(relation)
    path = task / 'source/signals/contracts' / (identity(ledger)+'.json')
    write_json(path, ledger)
    state['signal_semantics'] = ledger
    state['signal_contract'] = {'path': path.relative_to(task).as_posix(), 'sha256': digest(path)}
    state.pop('acceptance', None)
    state.pop('quality_result', None)
    return {'status': 'SOURCE_SIGNAL_CONTRACT_BOUND', 'signals': len(ledger['signals']), 'relations': len(ledger['relations'])}


def packet(task, state):
    known = discover(state)
    bound = state.get('signal_semantics', {}).get('signals', {})
    missing = [r for r in known if r['id'] not in bound]
    if not missing:
        return None
    return {'kind': 'signal_source', 'source_hash': state['source']['sha256'],
            'items':[{**r,'nearby_source_text_candidates':nearby_labels(state,r)} for r in missing],
            'instruction': 'Inspect each original signal and associated original text. Bind schematic purpose, ROI, observed source_points, actual label owner/literal/source_evidence, evidence, source-supported metric constraints and typed amplitude/RMS relationships. Frequency needs explicit text or observed source order. Do not generate scientific data.',
            'source_kinds':['schematic_signal','radiating_bands'],
            'function_families': ['observed_spline', 'observed_contours', 'carrier_envelope', 'damped_pulse']}


def descriptors(points):
    p = np.asarray(points, dtype=float)
    xx = np.linspace(p[0, 0], p[-1, 0], 128)
    yy = np.interp(xx, p[:, 0], p[:, 1])
    baseline = float(np.median(yy))
    centred = yy-baseline
    fft = np.abs(np.fft.rfft(centred))
    peaks = int(np.count_nonzero((yy[1:-1] > yy[:-2]) & (yy[1:-1] >= yy[2:])))
    return {'baseline_y_px': baseline, 'peak_to_peak_px': float(np.ptp(yy)),
            'rms_px': float(np.sqrt(np.mean(centred**2))), 'peak_count': peaks,
            'dominant_cycles_per_icon': int(np.argmax(fft[1:])+1) if fft.size > 1 and np.max(fft[1:]) > 1e-9 else 0,
            'dominant_cycles_per_original_pixel':float(np.argmax(fft[1:])+1)/max(float(p[-1,0]-p[0,0]),1) if fft.size>1 and np.max(fft[1:])>1e-9 else 0,
            'envelope_bins_px': [float(np.max(np.abs(v))) for v in np.array_split(centred, 8)],
            'frequency_unit': 'cycles per icon and per original x pixel; no physical Hz inferred'}


def _native_texts(file):
    from zipfile import ZipFile
    from lxml import etree as E
    values={}
    with ZipFile(file) as z:
        for name in z.namelist():
            if re.fullmatch(r'ppt/slides/slide\d+\.xml',name):
                root=E.fromstring(z.read(name))
                for shape in root.xpath('//*[local-name()="sp"]'):
                    names=shape.xpath('./*[local-name()="nvSpPr"]/*[local-name()="cNvPr"]/@name')
                    if names:
                        values[names[0]]=''.join(shape.xpath('./*[local-name()="txBody"]//*[local-name()="t"]/text()'))
    return values


def _curve_metrics(source, actual):
    a, b = np.asarray(source), np.asarray(actual)
    left, right = max(a[0, 0], b[0, 0]), min(a[-1, 0], b[-1, 0])
    if right <= left:
        raise ValueError('Original and saved signal domains do not overlap')
    x = np.linspace(left, right, 128)
    y, z = np.interp(x, a[:, 0], a[:, 1]), np.interp(x, b[:, 0], b[:, 1])
    distance = np.linalg.norm(a[:, None, :]-b[None, :, :], axis=2)
    return {'curve_rmse_px': float(np.sqrt(np.mean((y-z)**2))),
            'curve_max_vertical_error_px': float(np.max(np.abs(y-z))),
            'symmetric_chamfer_px': float((distance.min(axis=0).mean()+distance.min(axis=1).mean())/2),
            'hausdorff_px': float(max(distance.min(axis=0).max(), distance.min(axis=1).max())),
            'source': descriptors(source), 'actual': descriptors(actual)}


def report(task, state, candidate):
    known = discover(state)
    if not known:
        return {'schema': VERSION, 'passed': True, 'applicable': False, 'status': 'NO_DECLARED_SOURCE_SIGNALS', 'items': [], 'relations': []}
    ledger = state.get('signal_semantics', {})
    if state.get('signal_contract'):
        file = safe_path(task, state['signal_contract']['path'])
        if digest(file) != state['signal_contract']['sha256'] or read_json(file) != ledger:
            raise ValueError('Frozen signal semantics changed')
    original = _source(task, state)
    actual_file = safe_path(task, candidate['preview']['path'])
    if digest(actual_file) != candidate['preview']['sha256']:
        raise ValueError('Signal observation uses another saved-render preview')
    size = state['source_size']
    with Image.open(actual_file) as image:
        aligned = image.convert('RGB').resize(tuple(size), Image.Resampling.LANCZOS)
    aligned_file = task / 'source/signals/views' / (candidate['preview']['sha256']+'.png')
    if not aligned_file.is_file():
        aligned_file.parent.mkdir(parents=True, exist_ok=True)
        aligned.save(aligned_file)
    from .source_recursion import _native_names
    names = _native_names(safe_path(task, candidate['pptx']['path']))
    texts = _native_texts(safe_path(task,candidate['pptx']['path']))
    from .boundary_geometry import saved_nodes
    native=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size'])
    rows, measured = [], {}
    for raw in known:
        spec = ledger.get('signals', {}).get(raw['id'])
        if not spec:
            rows.append({'id': raw['id'], 'passed': False, 'status': 'ORIGINAL_SIGNAL_CONTRACT_REQUIRED'})
            continue
        try:
            if spec['purpose']=='radiating_bands':
                checks={'native_mark_present':bool(raw['objects']) and set(raw['objects'])<=names,
                    'source_band_count':len(spec['band_objects'])==spec['source_band_count'],
                    'closed_native_bands':all(n in native and bool(native[n]['node'].xpath('.//*[local-name()="close"]')) for n in spec['band_objects'])}
                rows.append({'id':raw['id'],'passed':all(checks.values()),'status':'RADIATING_BAND_GEOMETRY_MEASURED',
                    'kind':'radiating_bands','checks':checks,'source_band_count':spec['source_band_count'],
                    'waveform_metrics':'NOT_APPLICABLE: source is a radio mark, not an amplitude-versus-position waveform',
                    'evidence':spec['evidence']})
                continue
            points = isolate(aligned_file, spec['roi'], spec.get('colour', '444444'), spec.get('tolerance', 125),spec.get('trace_mode','column_center'))
            metrics = _curve_metrics(spec['source_points'], points)
            x, y, w, h = map(int, spec['roi'])
            with Image.open(original) as image:
                a = np.asarray(image.convert('RGB').crop((x, y, x+w, y+h))).astype(float)
            b = np.asarray(aligned.crop((x, y, x+w, y+h))).astype(float)
            mse = float(np.mean((a-b)**2))
            ssim = float(structural_similarity(a, b, data_range=255, channel_axis=2, win_size=min(7, min(a.shape[:2])//2*2-1))) if min(a.shape[:2]) >= 3 else None
            metrics.update(ssim=ssim, psnr_db=10*math.log10(255**2/mse) if mse > 0 else None, pixel_identical=mse == 0,
                           common_coordinate_scale='original pixels; amplitude never normalized per icon')
            c = spec.get('constraints', {})
            checks = {'curve_error': metrics['curve_rmse_px'] <= c.get('curve_error_px', 2.0),
                      'native_curve_present': bool(raw['objects']) and set(raw['objects']) <= names}
            for label in spec['labels']:
                checks['label:'+label['owner']]=texts.get(label['owner'])==label['literal']
            for key, metric in (('ssim_min', 'ssim'), ('psnr_min', 'psnr_db')):
                if key in c:
                    checks[key] = metrics[metric] is not None and metrics[metric] >= c[key] or key == 'psnr_min' and metrics['pixel_identical']
            for key, metric in (('amplitude_relative_error', 'peak_to_peak_px'), ('envelope_relative_error', 'envelope_bins_px')):
                if key in c:
                    aa, bb = np.asarray(metrics['source'][metric]), np.asarray(metrics['actual'][metric])
                    checks[key] = float(np.max(np.abs(aa-bb))/max(float(np.max(np.abs(aa))), 1)) <= c[key]
            measured[raw['id']] = metrics
            rows.append({'id': raw['id'], 'passed': all(checks.values()), 'status': 'SIGNAL_METRICS_MEASURED',
                         'metrics': metrics, 'checks': checks, 'labels': spec['labels']})
        except (ValueError, KeyError) as error:
            rows.append({'id': raw['id'], 'passed': False, 'status': 'SIGNAL_REOBSERVATION_REQUIRED', 'reason': str(error)})
    relations = []
    for rel in ledger.get('relations', {}).values():
        a, b = measured.get(rel['strong']), measured.get(rel['weak'])
        metric = {'amplitude_greater': 'peak_to_peak_px', 'rms_greater': 'rms_px',
                  'frequency_greater': 'dominant_cycles_per_original_pixel', 'frequency_lower': 'dominant_cycles_per_original_pixel'}.get(rel['predicate'])
        passed = False
        if a and b and metric:
            src = a['source'][metric] > b['source'][metric]
            dst = a['actual'][metric] > b['actual'][metric]
            if rel['predicate'] == 'frequency_lower':
                src = a['source'][metric] < b['source'][metric]
                dst = a['actual'][metric] < b['actual'][metric]
            passed = bool(src and dst)
        elif a and b and rel['predicate'] == 'source_order':
            metric = rel['metric']
            source_delta = a['source'][metric]-b['source'][metric]
            actual_delta = a['actual'][metric]-b['actual'][metric]
            passed = bool(source_delta*actual_delta > 0 or source_delta == actual_delta == 0)
        relations.append({'id': rel['id'], 'predicate': rel['predicate'], 'passed': passed,
                          'status': 'SOURCE_AND_TEXT_ORDER_PRESERVED' if passed else 'SOURCE_TEXT_OR_SAVED_SIGNAL_CONFLICT',
                          'evidence': rel['source_evidence']})
    return {'schema': VERSION, 'passed': bool(rows) and all(r['passed'] for r in rows) and all(r['passed'] for r in relations),
            'applicable': True, 'source_hash': state['source']['sha256'], 'candidate_hash': candidate['pptx']['sha256'],
            'preview_hash': candidate['preview']['sha256'], 'items': rows, 'relations': relations}


def command(task, action, request=None):
    from . import agent_runtime as a
    from .common import writer
    task, state = a._state(task)
    with writer(task):
        if action == 'bind':
            result = bind(task, state, request or {})
        elif action == 'next':
            result = packet(task, state) or {'status': 'SOURCE_SIGNALS_BOUND_OR_NOT_APPLICABLE'}
        elif action == 'verify':
            result = report(task, state, state.get('active_candidate') or state['selected'])
        else:
            raise ValueError('Unknown signal semantics action')
        a._save(task, state)
    return result
