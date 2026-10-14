"""Compact, deterministic next-action selection for a host-driven drawing task.

This module schedules existing plan actions; it never fabricates an image
observation, runs a desktop tool, or treats a saved artifact as accepted.
"""

from pathlib import Path
import time

from .common import identity, read_json
from .session import _exhausted, load


def next_action(workdir, plan):
    workdir = Path(workdir).resolve()
    session = load(workdir)
    from .visual_loop import dispatch, next_step
    visual = next_step(workdir) if (workdir / 'visual-loop.json').exists() else dispatch(workdir, 'start', {})
    if visual['status'] != 'DRAW_INITIAL':
        return visual
    if plan.get('schema_version') != 'drawing-plan-1':
        raise ValueError('A compiled drawing plan is required')
    plan_hash = identity(plan)
    journal_file = workdir / 'actions.json'
    journal = read_json(journal_file) if journal_file.is_file() else {'operations': []}
    records = [item for item in journal.get('operations', [])
               if item.get('plan_hash') == plan_hash]
    failed = [item for item in records if item.get('status') == 'FAILED_REPLAN_REQUIRED']
    if failed:
        item = failed[-1]
        return {'status': 'REPLAN_REQUIRED', 'plan_hash': plan_hash,
                'operation_id': item['operation_id'], 'action_id': item['action_id'],
                'failure_reason': item['failure_reason'],
                'on_failure': item.get('on_failure'),
                'next': 'Inspect the failed saved candidate, change the plan revision or inputs, and claim a new action only after that state change'}
    active = [item for item in records if item.get('status') in
              ('RUNNING', 'INTERRUPTED_REQUIRES_RECONCILIATION')]
    if active:
        item = active[-1]
        return {'status': 'RECONCILE_ACTION', 'plan_hash': plan_hash,
                'operation_id': item['operation_id'], 'action_id': item['action_id'],
                'action_status': item['status'],
                'next': 'Inspect frozen output targets; never repeat an uncertain desktop edit'}
    saved = [item for item in records if item.get('status') == 'OUTPUT_SAVED']
    if saved:
        item = saved[-1]
        return {'status': 'CHECK_SAVED_ACTION', 'plan_hash': plan_hash,
                'operation_id': item['operation_id'], 'action_id': item['action_id'],
                'outputs': item['outputs'],
                'next': 'Run the operation-specific check before starting another candidate'}
    verified = {item['action_id'] for item in records if item.get('status') == 'VERIFIED'}
    remaining = [item for item in plan['actions'] if item['id'] not in verified]
    if not remaining:
        return {'status': 'REGISTER_SAVED_RESULT', 'plan_hash': plan_hash,
                'next': 'Save/render the actual result and call visual-loop candidate; completed initial actions begin the observation/repair loop'}
    ready = [item for item in remaining if set(item.get('depends_on', [])) <= verified]
    if not ready:
        return {'status': 'BLOCKED_DEPENDENCY', 'plan_hash': plan_hash,
                'waiting_for': {item['id']: sorted(set(item.get('depends_on', [])) - verified)
                                for item in remaining}}
    action = ready[0]
    budget = session['budget']
    plan_budget = plan['budget']
    candidate = action['operation'] not in ('render', 'inspect', 'measure', 'verify')
    plan_candidates_used = sum(bool(item.get('candidate_slot_charged')) for item in records)
    elapsed = max(session['elapsed_wall_seconds'], time.time() - session['started_at'])
    seconds_left = min(budget['deadline'] - time.time(), budget['seconds'] - elapsed,
                       plan_budget['seconds'] - elapsed)
    candidates_left = min(budget['candidates'] - budget['candidates_used'],
                          plan_budget['candidates'] - plan_candidates_used)
    if (_exhausted(session, candidate=candidate) or seconds_left <= 0
            or (candidate and candidates_left <= 0)):
        return {'status': 'PAUSED_RESOURCE_LIMIT', 'plan_hash': plan_hash,
                'next_action_id': action['id'], 'budget': budget,
                'plan_budget': plan_budget, 'plan_candidates_used': plan_candidates_used}
    nodes = {item['id']: item for item in plan['nodes']}
    context = [{key: nodes[target].get(key) for key in
                ('id', 'parent', 'family_id', 'representation', 'texture_role',
                 'observation_note', 'objective', 'editable_parts', 'render_ids')}
               for target in action['targets']]
    return {'status': 'READY', 'plan_hash': plan_hash,
            'action': action, 'target_context': context,
            'budget_remaining': {'seconds': max(0, int(seconds_left)),
                                 'candidates': max(0, candidates_left)},
            'next': 'Claim this action with frozen inputs and output paths, then execute once'}
