"""Finite parameter search with separate hard targets and protected local bests."""
import copy
import math
from .common import identity
from .component_protocol import finite


def assessment(measured, metrics):
    values = {}; violations = []; objective = []
    hard = measured.get('hard_checks', {})
    if not hard or any(value is not True for value in hard.values()):
        return {'valid': True, 'hard_pass': False, 'passed': False,
                'merit': None, 'reason': 'HARD_CONSTRAINT_FAILED'}
    for metric in sorted(metrics, key=lambda m: m['id']):
        if metric.get('role') != 'target' or metric.get('applicable', True) is False: continue
        row = measured.get('metrics', {}).get(metric['id'])
        if not row or row.get('valid') is not True:
            return {'valid': False, 'hard_pass': True, 'passed': False,
                    'merit': None, 'reason': 'MEASUREMENT_INVALID', 'metric': metric['id']}
        value = row.get('value'); limit = metric.get('acceptable_threshold', metric.get('threshold'))
        if (not isinstance(value, (int, float)) or isinstance(value, bool) or
            not math.isfinite(value) or not isinstance(limit, (int, float)) or
            isinstance(limit, bool) or not math.isfinite(limit)):
            raise ValueError('Finite metric value and frozen target required')
        scale = metric.get('normalization_scale', abs(limit) or 1.)
        if not isinstance(scale, (int, float)) or not math.isfinite(scale) or scale <= 0:
            raise ValueError('Positive metric normalization scale required')
        direction = metric['direction']
        residual = value - limit if direction == 'lower' else limit - value if direction == 'higher' else abs(value - limit)
        oriented = value if direction == 'lower' else -value if direction == 'higher' else abs(value - limit)
        values[metric['id']] = value
        violations.append(max(0., residual / scale))
        objective.append(oriented / scale)
    if not values:
        raise ValueError('Search needs at least one applicable declared target')
    return {'valid': True, 'hard_pass': True, 'passed': all(v == 0 for v in violations),
            'merit': [max(violations), sum(violations), *objective],
            'values': values, 'violations': violations}


def protected_regression(before, after, metrics, tolerance):
    for metric in metrics:
        if not metric.get('protected'): continue
        key = metric['id']
        if key not in before.get('values', {}) or key not in after.get('values', {}): return True
        a, b = before['values'][key], after['values'][key]
        scale = metric.get('normalization_scale', abs(metric.get('threshold', 0)) or 1.)
        deterioration = b-a if metric['direction'] == 'lower' else a-b if metric['direction'] == 'higher' else abs(b-metric['threshold'])-abs(a-metric['threshold'])
        if deterioration / scale > tolerance: return True
    return False


from .component_search import bounded_search, rank_actions
