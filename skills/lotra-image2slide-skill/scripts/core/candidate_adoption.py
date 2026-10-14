"""Shared gates and satisfaction maintenance for every controlled adoption.

The native writer still enforces grants. This layer does not widen permissions,
invent observations or turn retained working progress into final acceptance.
"""
from .common import read_json, safe_path, write_json
from . import source_quality, semantic_composition, impact_graph


def prepare(task, state, candidate, grants, *, mode, observations=(), result=None):
    from .execution_contract import policy, report as execution_report
    policy(state)
    from .relative_layout import retention_guard as layout_guard
    from .textbox_quality import retention_guard as text_guard
    from .source_property_protection import snapshot_satisfaction
    before = state.get('selected')
    from .object_lifecycle import checkpoint
    # Record independent before/after evidence on every controlled adoption,
    # including rejected candidates; global failure cannot erase local history.
    if state.get('quality_intent'):
        checkpoint(task,state,before)
    from .frame_plan import guard as frame_guard
    candidate['frame_plan_actual'] = frame_guard(task,state,candidate)
    candidate['relative_layout_actual'] = layout_guard(task, state, candidate, grants)
    candidate['textbox_actual'] = text_guard(task, state, candidate, grants)
    candidate['semantic_composition_actual'] = (
        semantic_composition.retention_guard(task, state, candidate, grants)
        if before else semantic_composition.report(task, state, candidate))
    candidate['execution_coverage']=execution_report(task,state,candidate)
    scenes = [read_json(safe_path(task, candidate['scene']['path']))]
    if before:
        scenes.append(read_json(safe_path(task, before['scene']['path'])))
    impact = impact_graph.resolve(state, grants or {}, scenes=scenes)
    scope = {'eligible': True, 'changed_units': [], 'blocking_units': []}
    if before and source_quality.enabled(state):
        scope = source_quality.repair_scope_effect(task, state, before, candidate, grants or {})
        # The existing bounded cosmetic policy is identical on all routes.
        scope = source_quality.scoped_cosmetic_acceptance(
            task, state, before, candidate, scope,
            (result or {}).get('cosmetic_limits'), observations)
        write_json(safe_path(task, candidate['pptx']['path']).parent / 'adoption-scope-effect.json', scope)
    from .object_lifecycle import adoption_guard
    lifecycle_guard=adoption_guard(task,state,candidate,grants)
    lifecycle_measurement=checkpoint(task,state,candidate) if state.get('quality_intent') and candidate.get('render') else None
    if lifecycle_measurement and lifecycle_measurement.get('regressions'):
        lifecycle_guard['passed']=False;lifecycle_guard['blocking']+=lifecycle_measurement['regressions']
    if not lifecycle_guard['passed']:
        scope['eligible']=False;scope['blocking_units']+=lifecycle_guard['blocking']
    candidate['object_lifecycle_adoption']=lifecycle_guard
    ticket = {'mode': mode, 'before': before, 'impact': impact, 'scope_effect': scope,
              'satisfaction': snapshot_satisfaction(state), 'eligible': scope['eligible']}
    candidate['adoption_gate'] = {'mode': mode, 'impact': impact,
                                 'eligible': scope['eligible'], 'blocking_units': scope['blocking_units']}
    return ticket


def retain(task, state, candidate, ticket, *, updates=None, packet=None, result=None):
    from .source_property_protection import preserve_satisfaction
    if not ticket['eligible']:
        raise ValueError('Changed/dependent source properties block adoption: ' + repr(ticket['scope_effect']['blocking_units']))
    before = ticket['before']
    state['selected'] = candidate
    state.pop('acceptance',None)
    from .frame_plan import register_failures as frame_findings
    frame_findings(task,state,candidate)
    if not before or not source_quality.enabled(state):
        return {'affected': [], 'inherited': []}
    affected = source_quality.invalidate(state, ticket['impact']['observe'])
    # Pixel dependencies are discovered by the existing actual scoped gate;
    # they remain read/check dependencies even when native fields are equal.
    for uid in ticket['scope_effect'].get('actual_pixel_dependent_units', []):
        unit = state['quality']['units'][uid]
        unit['status'] = 'required_unmeasured'
        state['quality']['observations'].pop(uid, None)
        if 'quality:' + uid not in affected:
            affected.append('quality:' + uid)
    for owner, built in (updates or {}).items():
        source_quality.bind_objects(state, owner, built)
    inherited = preserve_satisfaction(task, state, before, candidate, ticket['satisfaction'])
    inherited += source_quality.inherit_usable_limits(task, state, before, candidate)
    if packet is not None:
        source_quality.record_scoped_observations(
            task, state, candidate, packet, ticket['scope_effect'],
            (result or {}).get('source_unit_observations'))
    source_quality.record_usable_limits(task, state, candidate, ticket['scope_effect'])
    inherited = set(inherited) | {v['unit'] for v in ticket['scope_effect'].get('usable_limits', [])}
    preserved = {'quality:' + uid for uid in inherited}
    affected = [t for t in affected if t not in preserved]
    state['review_queue'] = [t for t in state.get('review_queue', []) if t not in preserved]
    state['review_queue'] += [t for t in affected if t not in state['review_queue']]
    return {'affected': affected, 'inherited': sorted(inherited)}
