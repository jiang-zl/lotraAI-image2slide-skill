"""Append measured experiments with per-module raw metrics and comparable deltas.

No hand-entered visual scores, zero-filled missing values, or inferred acceptance.
"""
import math
from pathlib import Path
from .common import digest, identity, read_json, write_json, writer
from .benchmark import environment_identity

VERSION = 'attempt-log-1.0.0'
METRICS = {
    'ssim': ('ssim', 'max'),
    'delta_e_2000': ('color_delta_e_2000.mean', 'min'),
    'boundary_f1': ('boundary.f1', 'max'),
    'internal_edge_f1': ('internal_edges.f1', 'max'),
    'residual_rgb_255': ('regional_residual_rgb_255.mean', 'min'),
    'low_contrast_edge_f1': ('low_contrast_edges.f1', 'max'),
    'luminance_std_abs_error': ('luminance_std_abs_error', 'min'),
}


def raw_values(measurements):
    result = {}
    for name, (path, direction) in METRICS.items():
        value = measurements
        for part in path.split('.'):
            value = value.get(part) if isinstance(value, dict) else None
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise ValueError('Nonfinite/non-numeric metric: '+name)
        result[name] = {'value': value, 'direction': direction,
                        'missing_reason': 'Not available in the fixed measurement protocol' if value is None else None}
    return result


def improvement(old, new):
    """Positive means improved; absent measurements remain unknown."""
    return {key: None if old[key]['value'] is None or item['value'] is None else
            (item['value']-old[key]['value'])*(1 if item['direction']=='max' else -1)
            for key, item in new.items()}


def append_attempt(metadata, measurements, pptx, preview, render_receipt, registry):
    measured = read_json(measurements)
    render = read_json(render_receipt)
    hashes = {'pptx_hash': digest(pptx), 'preview_hash': digest(preview)}
    for key, value in hashes.items():
        if measured.get(key) != value or render.get(key) != value:
            raise ValueError('Attempt requires measurements of this actual saved PPT and render')
    if measured.get('render_receipt_hash') != digest(render_receipt):
        raise ValueError('Measurement render receipt changed')
    for field in ('case', 'attempt', 'method', 'parameters', 'modules', 'selection', 'reason'):
        if field not in metadata:
            raise ValueError('Missing attempt field: '+field)
    if type(metadata['attempt']) is not int or metadata['attempt'] < 0 or not metadata['method'] or not metadata['reason']:
        raise ValueError('Invalid attempt identity/method/reason')
    if metadata['selection'] not in ('baseline', 'selected', 'rejected', 'candidate', 'tradeoff'):
        raise ValueError('Invalid candidate selection state')
    modules = metadata['modules']
    if not modules or len({m['id'] for m in modules}) != len(modules):
        raise ValueError('Empty/duplicate module experiment')
    for m in modules:
        if m['id'] not in measured['targets'] or not all(k in m for k in ('parent', 'children', 'representation', 'edit_operations')):
            raise ValueError('Every module needs measurements, decomposition and editing promises')
    renderer = render.get('backend') or render.get('renderer') or render.get('method')
    if not renderer:
        raise ValueError('Render backend identity missing')
    env=environment_identity(render,preview)
    implementation_hash=identity(measured['implementation']) if measured.get('implementation') else None
    registry = Path(registry)
    registry.parent.mkdir(parents=True, exist_ok=True)
    with writer(registry.parent):
        history = read_json(registry) if registry.exists() else {'version': VERSION, 'attempts': []}
        if history.get('version') != VERSION: raise ValueError('Unknown attempt registry')
        rows = history['attempts']
        if any(r['case']==metadata['case'] and r['attempt']==metadata['attempt'] for r in rows):
            raise ValueError('Immutable attempt already recorded')
        if any(r['case']==metadata['case'] and r['attempt']>=metadata['attempt'] for r in rows):
            raise ValueError('Attempt numbers must increase within each case')
        record = dict(metadata, **hashes, source_hash=measured['source_hash'], plan_hash=measured['plan_hash'],
                      metric_version=measured['metric_version'], renderer=renderer,environment=env,
                      environment_hash=env['identity'] if env['complete'] else None,implementation_hash=implementation_hash,
                      measurements_path=str(Path(measurements).resolve()), measurements_hash=digest(measurements), modules=[])
        for m in modules:
            values = raw_values(measured['targets'][m['id']]['measurements'])
            same = [r for r in rows if r['case']==record['case'] and all(record.get(k) is not None and r.get(k)==record[k] for k in
                    ('source_hash', 'plan_hash', 'metric_version', 'renderer','environment_hash','implementation_hash'))]
            comparable = [(r, next((n for n in r['modules'] if n['id']==m['id']), None)) for r in same]
            comparable = [(r,n) for r,n in comparable if n is not None]
            baseline = next(((r,n) for r,n in comparable if r['selection']=='baseline'), None)
            previous = comparable[-1] if comparable else None
            record['modules'].append(dict(m, metrics=values,
                previous_attempt=previous[0]['attempt'] if previous else None,
                baseline_attempt=baseline[0]['attempt'] if baseline else None,
                improvement_previous=improvement(previous[1]['metrics'], values) if previous else None,
                improvement_baseline=improvement(baseline[1]['metrics'], values) if baseline else None,
                comparison_status='COMPARABLE' if previous else 'NO_COMPARABLE_PRIOR_RENDER'))
        rows.append(record)
        write_json(registry, history)
    return {'attempt': record['attempt'], 'modules': len(record['modules']), 'status': 'RECORDED_NOT_ACCEPTANCE', 'registry': str(registry)}
