"""Sensitivity search. No runtime-cost or effect telemetry."""
import copy
import math
import numpy as np
from .common import identity
from .component_protocol import finite


def bounded_search(parameters, metrics, measure, settings, checkpoint=None):
    from .component_solver import assessment, protected_regression
    finite(parameters); finite(metrics); finite(settings)
    current = {key: row['value'] for key, row in parameters.items()}
    fixed = {key: row['value'] for key, row in parameters.items() if row['state'] == 'fixed'}
    variables = sorted(key for key, row in parameters.items() if row['state'] == 'tunable')
    maximum = settings.get('max_evaluations', 96); max_rounds = settings.get('max_rounds', 24)
    if type(maximum) is not int or not 1 <= maximum <= 4096 or type(max_rounds) is not int or not 1 <= max_rounds <= 256:
        raise ValueError('Finite evaluation and round budgets required')
    targets = {m['id']: m for m in metrics if m.get('role') == 'target' and m.get('applicable', True)}
    links = settings.get('parameter_metric_map', {})
    if any(not links.get(key) or not set(links[key]) <= set(targets) for key in variables):
        return dict(status='MODEL_RESELECT_REQUIRED', reason='Explicit parameter/target association required',
                    parameters=current, evaluations=0, rounds=0, history=[])
    steps = {}; minima = {}
    for key in variables:
        row = parameters[key]; low, high = row['bounds']; minimum = row.get('minimum_step')
        if not low < high or not low <= row['value'] <= high or type(minimum) not in (int,float) or minimum <= 0:
            raise ValueError('Source interval and positive minimum step required')
        minima[key] = minimum; steps[key] = row.get('initial_step', max(minimum, (high-low)/8))
        if steps[key] < minimum or not math.isfinite(steps[key]): raise ValueError('Invalid source step')
    history=copy.deepcopy(settings.get('resume_history',[]))
    cache={row['fingerprint']:row for row in history}
    resume=settings.get('resume_search_state',{})
    steps.update(resume.get('steps',{}))
    rounds=settings.get('resume_rounds',0);stable=resume.get('stable',{});invalid_trials=resume.get('invalid_trials',0);derivatives={}
    exhausted=set(resume.get('exhausted',[]))
    previous=[r for r in history if r.get('valid') and r.get('hard_pass')]
    if previous:current=copy.deepcopy(min(previous,key=lambda r:tuple(r['merit']))['parameters'])
    def persist():
        if checkpoint:checkpoint(history,rounds,{'steps':steps,'stable':stable,'exhausted':sorted(exhausted),
                                                 'current':current,'invalid_trials':invalid_trials})

    def evaluate(values, cause):
        nonlocal invalid_trials
        if any(values[key] != val for key, val in fixed.items()): raise ValueError('Fixed parameter changed')
        key = identity(values)
        if key in cache: return cache[key]
        if len(history) >= maximum: return None
        raw = measure(copy.deepcopy(values)); finite(raw); result = assessment(raw, metrics)
        result.update(parameters=copy.deepcopy(values), fingerprint=key, cause=cause)
        if not result['valid']: invalid_trials += 1
        cache[key] = result; history.append(result)
        persist()
        return result

    best = evaluate(current, 'source_initialized')
    if best is None:
        return dict(status='MODEL_RESELECT_REQUIRED',reason='Persistent search budget exhausted',parameters=current,evaluations=len(history),rounds=rounds,history=history)
    initial = copy.deepcopy(history[0] if history else best)

    def finish(status, reason=None):
        persist()
        return dict(status=status, parameters=current, best=best, initial=initial,
                    evaluations=len(history), rounds=rounds, history=history, reason=reason)

    if not best['valid'] or not best['hard_pass']: return finish(best['reason'])
    if best['passed']: return finish('TARGETS_MET')
    while rounds < max_rounds and len(history) < maximum:
        rounds += 1
        persist()
        violations = dict(zip(best['values'], best['violations']))
        failing = sorted((k for k,v in violations.items() if v > 0), key=lambda k: (-violations[k], k))
        relevant = [key for key in variables if key not in exhausted and any(k in links[key] for k in failing)]
        if not relevant: break
        relevant.sort(key=lambda key: (min(failing.index(k) for k in links[key] if k in failing), key))
        active = relevant[:min(6, settings.get('max_active_variables', 6))]
        candidates = []; derivatives = {}; sensitivities = {}
        for key in active:
            row = parameters[key]; low, high = row['bounds']
            if row.get('analytic_value') is not None:
                proposal = dict(current); proposal[key] = min(high, max(low, row['analytic_value']))
                trial = evaluate(proposal, {'analytic': key})
                if trial: candidates.append(trial)
            sides = []
            for direction in (-1, 1):
                value = min(high, max(low, current[key]+direction*steps[key]))
                if value == current[key]: sides.append(best); continue
                proposal = dict(current); proposal[key] = value
                trial = evaluate(proposal, {'parameter':key, 'direction':direction, 'step':steps[key]})
                sides.append(trial)
                if trial: candidates.append(trial)
            minus, plus = sides
            if not minus or not plus or not minus['valid'] or not plus['valid'] or not minus['hard_pass'] or not plus['hard_pass']:
                continue
            width = plus['parameters'][key]-minus['parameters'][key]
            if width <= 0: continue
            column = {}
            for target in targets:
                m = targets[target]; scale = m.get('normalization_scale', abs(m['threshold']) or 1.)
                derivative = (plus['values'][target]-minus['values'][target])/width
                column[target] = derivative/scale * (-1 if m['direction']=='higher' else 1)
            derivatives[key] = column
            sensitivities[key] = max(abs(column[k])*(high-low) for k in failing if k in links[key])
        chosen = sorted(derivatives, key=lambda key: (-sensitivities[key], key))[:3]
        candidates=[trial for trial in candidates if isinstance(trial['cause'],dict) and ('analytic' in trial['cause'] or trial['cause'].get('parameter') in chosen)]
        if len(chosen) > 1 and settings.get('coupled_update', True) and len(history) < maximum:
            matrix = np.array([[derivatives[key][target] for key in chosen] for target in failing], float)
            residual = np.array([violations[target] for target in failing], float)
            damping = settings.get('damping', 1e-3)*max(float(np.linalg.norm(matrix, ord='fro')**2), 1.)
            step = np.linalg.solve(matrix.T@matrix+damping*np.eye(len(chosen)), -matrix.T@residual)
            proposal = dict(current)
            for key, delta in zip(chosen, step):
                low, high = parameters[key]['bounds']
                proposal[key] = min(high, max(low, current[key]+float(np.clip(delta, -steps[key], steps[key]))))
            trial = evaluate(proposal, {'coupled':chosen, 'damping':damping})
            if trial: candidates.append(trial)
        permitted = [r for r in candidates if r['valid'] and r['hard_pass'] and
                     not protected_regression(best, r, metrics, settings.get('protected_regression_tolerance', 0.))]
        winner = min(permitted, key=lambda r:tuple(r['merit'])) if permitted else None
        if winner and tuple(winner['merit']) < tuple(best['merit']):
            previous = current; best = winner; current = dict(winner['parameters'])
            for key in active:
                delta = current[key]-previous[key]
                direction = 1 if delta > 0 else -1 if delta < 0 else 0
                last, count = stable.get(key, (0,0)); count = count+1 if direction and direction==last else int(bool(direction))
                stable[key] = (direction,count)
                if count >= 2:
                    low, high = parameters[key]['bounds']
                    steps[key] = max(minima[key], min(steps[key]*1.25, (high-low)/4))
            if best['passed']: return finish('TARGETS_MET')
        else:
            for key in active:
                stable[key] = (0,0)
                if steps[key] <= minima[key]: exhausted.add(key)
                else: steps[key] = max(minima[key], steps[key]*.5)
        persist()
    return finish('MEASUREMENT_DIAGNOSIS_REQUIRED' if invalid_trials and not derivatives else 'MODEL_RESELECT_REQUIRED',
                  'Evaluation/round/step limit reached; source targets remain frozen')


def rank_actions(actions, history=None):
    """The compatibility history argument is never used to learn cost or effect."""
    ranked = []
    for action in actions:
        if not action.get('legal') or action.get('writes_locked') or action.get('risk_tier') is None: continue
        work = action.get('static_work_units', 1); reuse = action.get('reuse_count', 0)
        reduction = action.get('immediate_violation_reduction')
        if type(work) not in (int,float) or work <= 0 or type(reuse) is not int or reuse < 0:
            raise ValueError('Positive static work and confirmed reuse required')
        if reduction is not None and (type(reduction) not in (int,float) or not math.isfinite(reduction)):
            raise ValueError('Finite immediate reduction or unknown required')
        probe_class = 1 if reduction is None else 0 if reduction > 0 else 2
        row = dict(action, decision_basis='current_state_source_and_static_work')
        row['_key'] = (row['stage_index'], -row.get('critical',0), row['risk_tier'], probe_class,
                       -(reduction or 0), row.get('source_distance',0), -(1+reuse)/work, row['id'])
        ranked.append(row)
    ranked.sort(key=lambda row: row['_key'])
    for row in ranked: row.pop('_key')
    return ranked

