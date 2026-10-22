"""Source-supported style groups and server-owned finite font preparation steps."""
import copy
import re
from pathlib import Path
from .common import identity, read_json
from .font_resolution import POLICY, enabled, request_key

STEPS = ('source_style', 'resource_decision', 'glyph_samples', 'family_choice', 'bind')


def constraint(state, request):
    row = state.get('font_constraints', {}).get(request['id'], {})
    return row if row.get('source_hash') == state['source']['sha256'] and row.get('request_hash') == request_key(request) else {}


def group_id(state, request, token=None):
    return identity({'source': state['source']['sha256'], 'role': request['role'],
                     'source_style_group': token or 'owner:'+request['owner']})


def group(state, request):
    key = constraint(state, request).get('group_id')
    value = state.get('font_groups', {}).get(key, {})
    return value if value.get('source_hash') == state['source']['sha256'] else {}


def apply_group(state, request, faces, extend=False):
    selected = group(state, request).get('family')
    if not selected or extend:
        return faces
    from .font_resources import matches
    return [face for face in faces if matches(face, selected)]


def required_step(state, request):
    from . import font_collection as collection
    from .font_contract import requested_family
    if request.get('identity_policy') != POLICY or collection.role_language(request['role']) not in ('zh','en'):
        return 'bind'
    demanded = requested_family(state, request)
    if not demanded and not constraint(state, request):
        return 'source_style'
    faces = collection.eligible(state, request, extend=bool(demanded))
    if demanded:
        from .font_resources import matches
        faces = [face for face in faces if matches(face, demanded)]
    if not faces:
        return 'resource_decision'
    if demanded:
        return 'bind'
    sample = state.get('font_samples', {}).get(request['id'], {})
    if sample.get('source_hash') != state['source']['sha256'] or sample.get('request_hash') != request_key(request):
        return 'glyph_samples'
    if not group(state, request).get('family') and len({f['family'] for f in faces}) > 1:
        return 'family_choice'
    return 'bind'


def validate_style(task, state, request, value, faces, observed, comparison_state=None):
    """Return a proposed constraint/group update without changing live state."""
    existing = constraint(state, request)
    token = value.get('style_group', existing.get('style_group', 'owner:'+request['owner']))
    if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}', token):
        raise ValueError('Use a bounded source-supported style_group identity')
    key = group_id(state, request, token)
    result = {**copy.deepcopy(existing), **copy.deepcopy(value), 'source_hash':state['source']['sha256'],
              'request_hash':request_key(request), 'request':copy.deepcopy(request), 'style_group':token, 'group_id':key}
    classes = result.get('style_classes', [])
    ids = result.get('resource_ids', [])
    if 'unknown' in classes and (not ids or not result.get('unknown_style_justification')):
        raise ValueError('Unknown font style needs an explicit resource set and an original glyph justification')
    if result.get('synthetic_style') and not result.get('style_description'):
        raise ValueError('Explicit synthetic style needs a separate original style_description')
    current = copy.deepcopy(state.get('font_groups', {}).get(key, {'id':key,
        'source_hash':state['source']['sha256'], 'role':request['role'], 'style_group':token, 'members':{}}))
    selected = value.get('family')
    if selected:
        from . import font_collection as collection
        from . import component_workflow as workflow
        ref = value.get('comparison_ref')
        registered = state.get('font_rankings', {}).get(request_key(request), {})
        if not ref or ref not in registered.values():
            raise ValueError('Family choice needs the current program glyph comparison')
        ranking = read_json(workflow._resource(Path(task),ref))
        if (ranking.get('source_hash') != state['source']['sha256'] or ranking.get('request_hash') != request_key(request)
                or ranking.get('selection_context') != collection.selection_context(comparison_state or state,request,ranking.get('extended',False))):
            raise ValueError('Family choice comparison is stale')
        eligible_ids = {face['id'] for face in faces if face['family'] == selected}
        if not eligible_ids or not any(row['resource_id'] in eligible_ids for row in ranking['candidates']):
            raise ValueError('Family choice must retain a currently ranked eligible resource')
        if current.get('family') and current['family'] != selected:
            raise ValueError('Retain the adopted style group; an evidenced new group identity is needed for its revision')
        for member in current['members'].values():
            if not any(face['family']==selected for face in collection.eligible(state,member,extend=True,ignore_family=True)):
                raise ValueError('Selected family has no feasible face for another source style-group member')
        current.update(family=selected, evidence=copy.deepcopy(value['evidence']),
                       comparison_ref=copy.deepcopy(ref), reason=value['reason'], certainty='approximate')
    current['members'][request['id']] = copy.deepcopy(request)
    result.pop('family',None)
    return result, current


def require_binding(state, request, face, origin, synthetic):
    if request.get('identity_policy') != POLICY or origin != 'raster_inference':
        return
    step = required_step(state,request)
    if step != 'bind':
        raise ValueError('FONT_STEP_REQUIRED: '+step+' for '+request['id'])
    from . import font_collection as collection
    if face['id'] not in {f['id'] for f in collection.eligible(state,request)}:
        raise ValueError('FONT_RESOURCE_INELIGIBLE: current source group/style requires another resource')
    if synthetic and not constraint(state,request).get('synthetic_style'):
        raise ValueError('FONT_SYNTHETIC_DECISION_REQUIRED: preserve the explicit source style decision')


def check_group_bindings(state, bindings):
    families = {}
    for bound in bindings.values():
        request = bound['request']
        if request.get('identity_policy') != POLICY:
            continue
        key = constraint(state,request).get('group_id')
        if not key:
            continue
        # A prior face can remain staged while a bounded group revision spans
        # several packets. It is not adopted under the new group; missing()
        # still blocks native save until every member is currently feasible.
        if bound.get('origin')=='raster_inference':
            try:require_binding(state,request,bound['resource'],bound['origin'],bound.get('synthetic_style',False))
            except ValueError:continue
        families.setdefault(key,set()).add(bound['family'])
    if any(len(values)>1 for values in families.values()):
        raise ValueError('FONT_GROUP_CONFLICT: preserve a source-supported family across the complete style group')


def batch(rows, step, state):
    ids = [row['id'] for row in rows]
    return {'batch_id':identity({'source':state['source']['sha256'], 'step':step,
        'requests':{row['id']:request_key(row) for row in rows}}),
        'request_ids':ids, 'required_step':step,
        'font_batch_scope':{'source_hash':state['source']['sha256'],'requests':len(ids),
            'group_ids':sorted({constraint(state,row).get('group_id') for row in rows if constraint(state,row).get('group_id')})}}


def receive(task, state, scene, packet, result):
    """Prepare all changes on a copy; a failed submission adopts no partial state."""
    from . import font_contract as fonts, font_collection as collection
    requested = set(packet['request_ids'])
    payloads = {key for key in ('font_samples','font_constraints','font_bindings') if result.get(key)}
    if len(payloads)!=1:
        raise ValueError('Submit exactly one current font preparation step')
    key = next(iter(payloads));values = result[key]
    ids = [v.get('request_id') for v in values] if key=='font_bindings' else list(values)
    if not ids or len(ids)!=len(set(ids)) or set(ids)-requested:
        raise ValueError('FONT_BATCH_SCOPE: use only the visible current request_ids')
    step = packet['required_step']
    allowed = {'source_style':'font_constraints','resource_decision':'font_constraints',
               'glyph_samples':'font_samples','family_choice':'font_constraints','bind':'font_bindings'}
    if allowed[step]!=key:
        raise ValueError('FONT_STEP_REQUIRED: '+step)
    if step=='family_choice' and any(not value.get('family') for value in values.values()):
        raise ValueError('Current family_choice needs an evidenced family and comparison_ref')
    working = copy.deepcopy(state)
    if key=='font_samples':collection.store_samples(task,working,scene,values)
    elif key=='font_constraints':collection.store_constraints(task,working,scene,values)
    else:
        working = {**fonts.pending_state(working), 'font_contract':copy.deepcopy(fonts.pending_state(working).get('font_contract',{}))}
        fonts.bind(task,working,scene,values,persist=False)
        working['font_pending_candidate']['staged_font_contract'] = copy.deepcopy(working['font_contract'])
        # The active binding remains owned by the existing saved-native journal.
        if 'font_contract' in state:working['font_contract']=copy.deepcopy(state['font_contract'])
        else:working.pop('font_contract',None)
    receipt = {'schema':'font-submission-1','batch_id':packet['batch_id'],'required_step':step,
        'source_hash':state['source']['sha256'],'applied':True,'accepted':sorted(ids),'rejected':[],
        'state':'staged' if key=='font_bindings' else 'recorded','packet_id':packet['packet_id'],
        'response_hash':identity(result)}
    working['font_submission_receipt']=receipt
    working['font_submission_history']=(working.get('font_submission_history',[])+[copy.deepcopy(receipt)])[-64:]
    return working, receipt


def previous_submission(state, result):
    """An exact reply retry reads a receipt; it never repeats a mutation."""
    for receipt in reversed(state.get('font_submission_history',[])):
        if (receipt.get('applied') is True and receipt.get('packet_id')==result.get('packet_id')
                and receipt.get('source_hash')==state['source']['sha256'] and receipt.get('response_hash')==identity(result)):
            return copy.deepcopy(receipt)
    return None
