"""Persistent original-problem budgets, independent of model and owner names.

These are finite operational limits, not execution-cost or effect telemetry.
"""
import copy
from .common import identity, read_json, write_json, writer

LIMITS = {'models': 3, 'evaluations': 96, 'source_reads': 2, 'native_confirmations': 2}


def enabled(contract):
    return contract.get('workflow_version') in ('1.33.0','1.34.0','1.35.0','1.35.1','1.35.2')


def _path(task):
    return task / 'component-workflow/Problems.json'


def _load(task, source):
    path = _path(task)
    db = read_json(path) if path.exists() else {'schema': 'original-problems-1', 'source': source, 'problems': {}, 'units': {}}
    if db['source'] != source:
        raise ValueError('Problem ledger belongs to another original; explicit source migration required')
    return db


def bind(task, state, contract, previous=None):
    if not enabled(contract):
        return
    old = {r['id']: r for r in (previous or {}).get('components', [])}
    current={r['id']:r for r in contract['components']}
    with writer(task / 'component-workflow/problem-writer'):
        db = _load(task, state['source']['sha256'])
        for row in contract['components']:
            if row['route'] not in ('local_fit', 'specialist'):
                continue
            units = sorted(row['source_units'])
            ancestors = {db['units'][u] for u in units if u in db['units']}
            roi = row.get('roi')
            if roi and not ancestors:
                x,y,w,h=roi
                for prior_key, prior_problem in db['problems'].items():
                    if prior_problem.get('semantic_class')!=row.get('semantic_class'):continue
                    for a,b,c,d in prior_problem.get('regions',[]):
                        intersection=max(0,min(x+w,a+c)-max(x,a))*max(0,min(y+h,b+d)-max(y,b))
                        if intersection / max(1e-9,max(w*h,c*d)) >= .98: ancestors.add(prior_key)
            if row['id'] in old and old[row['id']].get('problem_id'):
                ancestors.add(old[row['id']]['problem_id'])
            parent=row.get('parent');seen=set()
            while parent and parent not in seen:
                seen.add(parent)
                if old.get(parent,{}).get('problem_id'):ancestors.add(old[parent]['problem_id'])
                parent=current.get(parent,{}).get('parent')
            # Split/renamed units must name their original source-unit lineage.
            for unit in contract['source_inventory']:
                if unit['id'] in units:
                    ancestors.update(db['units'][u] for u in unit.get('derived_from', []) if u in db['units'])
            if len(ancestors) > 1:
                # A combined component cannot obtain a fresh shared budget.
                raise ValueError('SOURCE_DECISION_REQUIRED: keep independent original problems separate')
            key = next(iter(ancestors), identity({'source': db['source'], 'units': units}))
            if row.get('problem_id') not in (None, key):
                raise ValueError('Original problem identity cannot be reset by a model decision')
            row['problem_id'] = key
            item = db['problems'].setdefault(key, {'limits': copy.deepcopy(LIMITS), 'used': dict.fromkeys(LIMITS, 0), 'models': [], 'strategies': {}, 'targets': {}})
            item.setdefault('semantic_class',row.get('semantic_class'))
            if roi and roi not in item.setdefault('regions',[]): item['regions'].append(copy.deepcopy(roi))
            targets = {m['id']: {k: m.get(k) for k in ('threshold', 'acceptable_threshold', 'direction', 'unit')} for m in row.get('metrics', []) if m['role'] == 'target'}
            for name, value in targets.items():
                prior = item['targets'].get(name)
                if prior and prior != value:
                    raise ValueError('Frozen problem targets cannot be widened after an unsuccessful candidate')
                item['targets'][name] = value
            model = identity(row.get('model', {}))
            # Bounds/start values do not create an extra family.
            family = row.get('model', {}).get('family', row.get('model', {}).get('id', model))
            if (row.get('curve_profile') is None or row.get('model',{}).get('family')) and family not in item['models']:
                if len(item['models']) >= item['limits']['models']:
                    raise ValueError('PROBLEM_EXHAUSTED: original problem model budget reached')
                item['models'].append(family); item['used']['models'] = len(item['models'])
            for unit in units:
                db['units'][unit] = key
        write_json(_path(task), db)


def remaining(task, state, row, channel):
    if not row.get('problem_id'):
        return LIMITS[channel]
    item = _load(task, state['source']['sha256'])['problems'][row['problem_id']]
    return max(0, item['limits'][channel] - item['used'][channel])


def reserve(task, state, row, channel, token=None):
    if not row.get('problem_id'):
        return
    with writer(task / 'component-workflow/problem-writer'):
        db = _load(task, state['source']['sha256']); item = db['problems'][row['problem_id']]
        key = identity({'channel': channel, 'token': token}) if token is not None else None
        if key and key in item['strategies']:
            return  # Replaying an already reserved journal action is idempotent.
        if item['used'][channel] >= item['limits'][channel]:
            raise ValueError('PROBLEM_EXHAUSTED: ' + channel + '; retain best and return a focused unresolved diagnosis')
        item['used'][channel] += 1
        if key:
            item['strategies'][key] = {'channel': channel, 'status': 'RESERVED'}
        write_json(_path(task), db)


def strategy(task, state, row, signature, result=None):
    if not row.get('problem_id'):
        return None
    with writer(task / 'component-workflow/problem-writer'):
        db = _load(task, state['source']['sha256']); item = db['problems'][row['problem_id']]
        prior = item['strategies'].get(signature)
        if result is not None:
            item['strategies'][signature] = copy.deepcopy(result); write_json(_path(task), db)
        return prior
