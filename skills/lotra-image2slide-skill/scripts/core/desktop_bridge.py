"""Task-owned handoff between a Linux drawing workspace and a real editor.

The host agent operates the currently available official Computer Use tool.
This module prepares a bounded request and imports its saved result; it never
pretends to control PowerPoint or Illustrator from a headless Python process.
"""

from pathlib import Path
import time

from .common import digest, identity, read_json, safe_path, write_json
from .session import _lock


LEVELS = ('DISCOVERED', 'OBSERVABLE', 'CONTROLLABLE',
          'ROUNDTRIP_VERIFIED', 'TASK_VERIFIED')
EDITOR_OPERATIONS = {'native_edit', 'path_edit', 'picture_edit'}


def _task_file(workdir, relative):
    path = safe_path(workdir, relative)
    if not path.is_file():
        raise ValueError('Desktop action input must be a task-owned file')
    return path


def _frozen_ref(workdir, ref):
    if not isinstance(ref, dict) or not ref.get('path') or not ref.get('sha256'):
        raise ValueError('Desktop protection needs a frozen task file reference')
    file = _task_file(workdir, ref['path'])
    if digest(file) != ref['sha256']:
        raise ValueError('Desktop protection input changed before dispatch')
    return file


def _product_check(workdir, envelope, candidate_pptx):
    """Independently compute the authorized saved-PPT product difference."""
    protection = envelope['protection']
    baseline = _task_file(workdir, envelope['input_pptx'])
    if protection['kind'] == 'native_leaf':
        from .saved_ppt_diff import verify_local_change
        preparation = read_json(_frozen_ref(workdir, protection['preparation']))
        no_op = (_frozen_ref(workdir, protection['office_noop_pptx'])
                 if protection.get('office_noop_pptx') else None)
        return verify_local_change(baseline, candidate_pptx, preparation,
                                   office_noop_pptx=no_op)
    if protection['kind'] == 'picture_layer':
        from .saved_ppt_diff import verify_local_picture_change
        picture_request = read_json(_frozen_ref(workdir, protection['picture_request']))
        receipt = read_json(_frozen_ref(workdir, protection['replacement_receipt']))
        return verify_local_picture_change(baseline, candidate_pptx,
                                           picture_request, receipt)
    raise ValueError('Unknown desktop product protection route')


def prepare(workdir, plan, capabilities, request, output):
    """Bind one planned edit to an observed host/app and a fresh task copy."""
    workdir = Path(workdir).resolve()
    output = Path(output).resolve()
    if output.parent != workdir or output.exists():
        raise ValueError('Desktop envelope must be a new file at the task root')
    if plan.get('schema_version') != 'drawing-plan-1':
        raise ValueError('Desktop action needs a compiled drawing plan')
    if capabilities.get('schema_version') != 'host-capabilities-1':
        raise ValueError('Unknown host capability inventory')
    if request.get('schema_version') != 'desktop-action-request-1':
        raise ValueError('Unknown desktop action request')
    action_id, operation_id = request.get('action_id'), request.get('operation_id')
    actions = [action for action in plan['actions'] if action.get('id') == action_id]
    if len(actions) != 1 or actions[0]['operation'] != 'native_edit' or not operation_id:
        raise ValueError('Desktop request must target one planned native edit')
    edit_kind = request.get('edit_kind')
    if edit_kind not in EDITOR_OPERATIONS:
        raise ValueError('Unknown target-editor edit kind')
    source = _task_file(workdir, request.get('input_pptx'))
    if digest(source) != request.get('input_sha256'):
        raise ValueError('Desktop input differs from the frozen task PPT')
    scene_file = _task_file(workdir, request.get('input_scene'))
    if digest(scene_file) != request.get('input_scene_sha256'):
        raise ValueError('Desktop input Scene changed before dispatch')
    target = safe_path(workdir, request.get('output_pptx'))
    if target.exists() or target.suffix.lower() != '.pptx' or target == source:
        raise ValueError('Desktop output must be a new task-owned PPTX')
    if not request.get('target_owner') or not request.get('allowed_change') or not request.get('protected_scope'):
        raise ValueError('Desktop edit needs an owner, exact write scope and protected scope')
    if not request.get('expected_change') or not request.get('on_failure'):
        raise ValueError('Desktop edit needs an observable result and failure branch')
    hosts = [host for host in capabilities.get('hosts', [])
             if host.get('host_id') == request.get('host_id')]
    if len(hosts) != 1:
        raise ValueError('Selected desktop host is absent or ambiguous')
    host = hosts[0]
    route = host.get('operations', {}).get(edit_kind)
    if (not isinstance(route, dict) or route.get('level') not in LEVELS
            or LEVELS.index(route['level']) < LEVELS.index('CONTROLLABLE')
            or not route.get('app_id') or not route.get('tool')):
        raise ValueError('No currently controllable editor route for the requested operation')
    observed_at = host.get('observed_at')
    expires_at = host.get('expires_at')
    if (type(observed_at) not in (int, float) or type(expires_at) not in (int, float)
            or not observed_at <= time.time() < expires_at):
        raise ValueError('Desktop capability observation is stale')
    from .action_journal import _journal
    claims = [item for item in _journal(workdir)['operations']
              if item.get('operation_id') == operation_id]
    expected_route = '|'.join((host['host_id'], route['app_id'], route['tool']))
    if len(claims) != 1:
        raise ValueError('Desktop action must be claimed before host dispatch')
    claim = claims[0]
    targets = claim.get('output_targets') or {}
    if (claim.get('status') != 'RUNNING' or claim.get('plan_hash') != identity(plan)
            or claim.get('action_id') != action_id or claim.get('operation') != 'native_edit'
            or claim.get('route') != expected_route
            or claim.get('inputs', {}).get('pptx', {}).get('sha256') != digest(source)
            or claim.get('inputs', {}).get('scene', {}).get('sha256') != digest(scene_file)
            or targets.get('Candidate.pptx') != request['output_pptx']
            or not targets.get('desktop-result.json')):
        raise ValueError('Desktop host, saved inputs or frozen outputs differ from claimed action')
    protection = request.get('protection')
    if not isinstance(protection, dict) or protection.get('kind') not in ('native_leaf', 'picture_layer'):
        raise ValueError('Desktop action needs an executable saved-product protection contract')
    if protection['kind'] == 'native_leaf':
        preparation = read_json(_frozen_ref(workdir, protection.get('preparation')))
        write_set = preparation.get('write_set', [])
        if (edit_kind not in ('native_edit', 'path_edit')
                or not write_set or request['target_owner'] not in
                    {item.get('object_id') for item in write_set}
                or request['allowed_change'] != write_set
                or preparation.get('base_pptx_hash') != digest(source)):
            raise ValueError('Desktop native edit exceeds the prepared leaf-level write set')
        if protection.get('office_noop_pptx'):
            _frozen_ref(workdir, protection['office_noop_pptx'])
    else:
        picture_request = read_json(_frozen_ref(workdir, protection.get('picture_request')))
        _frozen_ref(workdir, protection.get('replacement_receipt'))
        replacements = picture_request.get('replacements', [])
        if (edit_kind != 'picture_edit' or len(replacements) != 1
                or replacements[0].get('layer_id') != request['target_owner']
                or picture_request.get('source_pptx_hash') != digest(source)
                or request['allowed_change'] != [
                    {'shape_id': replacements[0].get('shape_id'), 'property': 'media_sha256'}]):
            raise ValueError('Desktop picture edit exceeds the frozen layer replacement')
    envelope = {'schema_version': 'desktop-action-envelope-1',
                'operation_id': operation_id, 'action_id': action_id,
                'plan_hash': identity(plan), 'edit_kind': edit_kind,
                'host': {'host_id': host['host_id'], 'os': host.get('os'),
                         'session': host.get('session'), 'app_id': route['app_id'],
                         'tool': route['tool'], 'level_at_dispatch': route['level'],
                         'capabilities_hash': identity(capabilities)},
                'input_pptx': request['input_pptx'],
                'input_sha256': request['input_sha256'],
                'input_scene': request['input_scene'],
                'input_scene_sha256': request['input_scene_sha256'],
                'output_pptx': request['output_pptx'],
                'result_receipt_path': targets['desktop-result.json'],
                'host_input_path': request.get('host_input_path'),
                'host_output_path': request.get('host_output_path'),
                'target_owner': request['target_owner'],
                'allowed_change': request['allowed_change'],
                'protected_scope': request['protected_scope'],
                'protection': protection,
                'expected_change': request['expected_change'],
                'on_failure': request['on_failure'],
                'action_checks': actions[0]['required_checks'],
                'status': 'READY_FOR_HOST_ACTION'}
    write_json(output, envelope)
    return envelope


def import_result(envelope_file, observation_file, candidate_pptx, output,
                  *, candidate_scene=None):
    """Import a saved editor result without silently blessing a stale Scene."""
    envelope_file = Path(envelope_file).resolve()
    workdir = envelope_file.parent
    envelope = read_json(envelope_file)
    if envelope.get('schema_version') != 'desktop-action-envelope-1':
        raise ValueError('Unknown desktop action envelope')
    source = _task_file(workdir, envelope['input_pptx'])
    if digest(source) != envelope['input_sha256']:
        raise ValueError('Desktop action source changed during editing')
    scene_before = _task_file(workdir, envelope['input_scene'])
    if digest(scene_before) != envelope['input_scene_sha256']:
        raise ValueError('Desktop action Scene changed during editing')
    candidate_pptx = Path(candidate_pptx).resolve()
    if candidate_pptx != safe_path(workdir, envelope['output_pptx']) or not candidate_pptx.is_file():
        raise ValueError('Desktop result is not the frozen task output')
    observation_file = Path(observation_file).resolve()
    if not observation_file.is_relative_to(workdir):
        raise ValueError('Desktop observation must be task-owned')
    observation = read_json(observation_file)
    events = observation.get('events', [])
    required = ('TASK_COPY_OPENED', 'EDIT_OCCURRED', 'SAVED', 'REOPENED')
    if (observation.get('schema_version') != 'desktop-observation-1'
            or observation.get('operation_id') != envelope['operation_id']
            or observation.get('plan_hash') != envelope['plan_hash']
            or observation.get('host_id') != envelope['host']['host_id']
            or observation.get('app_id') != envelope['host']['app_id']
            or observation.get('tool') != envelope['host']['tool']
            or not isinstance(events, list)
            or any(event not in events for event in required)
            or [events.index(event) for event in required] != sorted(events.index(event) for event in required)
            or observation.get('output_sha256') != digest(candidate_pptx)):
        raise ValueError('Desktop observation does not bind the open/edit/save/reopen result')
    if not observation.get('window_observations') or not observation.get('target_after'):
        raise ValueError('Desktop result lacks current window and target observations')
    product_ref = observation.get('product_check')
    if not isinstance(product_ref, dict) or not product_ref.get('path') or not product_ref.get('sha256'):
        raise ValueError('Desktop result needs a saved-product check file reference')
    product_file = _task_file(workdir, product_ref['path'])
    product = read_json(product_file)
    fresh_product = _product_check(workdir, envelope, candidate_pptx)
    if (digest(product_file) != product_ref['sha256']
            or product.get('status') != 'PASS_SAVED_PRODUCT_ONLY'
            or product.get('baseline_pptx_hash') != digest(source)
            or product.get('candidate_pptx_hash') != digest(candidate_pptx)
            or product != fresh_product):
        raise ValueError('Saved-product check does not belong to this editor output')
    scene_state = 'SAVED_PPT_AUTHORITATIVE_SCENE_SYNC_REQUIRED'
    scene_ref = None
    if candidate_scene is not None:
        from .inspect import check
        candidate_scene = Path(candidate_scene).resolve()
        if not candidate_scene.is_relative_to(workdir):
            raise ValueError('Reconciled Scene must be task-owned')
        scene = read_json(candidate_scene)
        report = check(scene, candidate_scene.parent, candidate_pptx)
        if report['status'] != 'PASS':
            raise ValueError('Edited PPT does not match the proposed reconciled Scene')
        scene_state = 'SCENE_RECONCILED_TO_SAVED_PPT'
        scene_ref = {'path': candidate_scene.relative_to(workdir).as_posix(),
                     'sha256': digest(candidate_scene)}
    output = Path(output).resolve()
    if output != safe_path(workdir, envelope['result_receipt_path']) or output.exists():
        raise ValueError('Desktop result receipt differs from the frozen action output target')
    if output.parent != workdir:
        raise ValueError('Desktop result receipt must be at the task root')
    result = {'schema_version': 'desktop-action-result-1',
              'status': 'SAVED_REOPENED_REQUIRES_SELECTION',
              'operation_id': envelope['operation_id'],
              'plan_hash': envelope['plan_hash'],
              'envelope': {'path': envelope_file.relative_to(workdir).as_posix(),
                           'sha256': digest(envelope_file)},
              'observation': {'path': observation_file.relative_to(workdir).as_posix(),
                              'sha256': digest(observation_file)},
              'product_check': product_ref,
              'candidate_pptx': {'path': candidate_pptx.relative_to(workdir).as_posix(),
                                 'sha256': digest(candidate_pptx)},
              'scene_state': scene_state, 'candidate_scene': scene_ref,
              'next': ('Use the saved PPT as the authoritative candidate; do not rebuild from an old Scene'
                       if scene_ref is None else 'Use the reconciled Scene only with this exact saved PPT')}
    with _lock(workdir / '.desktop-state.lock'):
        current_file = workdir / 'desktop-pending.json'
        if current_file.exists():
            current = read_json(current_file)
            if (current.get('scene_state') == 'SAVED_PPT_AUTHORITATIVE_SCENE_SYNC_REQUIRED'
                    and current.get('candidate_pptx') != result['candidate_pptx']):
                raise ValueError('Another unsynchronized desktop result needs reconciliation first')
        write_json(output, result)
        pending = {'schema_version': 'desktop-pending-1',
                   'result': {'path': output.relative_to(workdir).as_posix(),
                              'sha256': digest(output)},
                   'scene_state': scene_state, 'candidate_scene': scene_ref,
                   'candidate_pptx': result['candidate_pptx']}
        write_json(current_file, pending)
    return result


def audit_result(result_file):
    """Re-read the saved return path and its product protection binding."""
    result_file = Path(result_file).resolve()
    workdir = result_file.parent
    result = read_json(result_file)
    if result.get('schema_version') != 'desktop-action-result-1':
        raise ValueError('Unknown desktop result receipt')
    files = {}
    for key in ('envelope', 'observation', 'candidate_pptx', 'product_check'):
        ref = result.get(key)
        if not isinstance(ref, dict) or not ref.get('path') or not ref.get('sha256'):
            raise ValueError('Incomplete desktop result reference: ' + key)
        files[key] = _task_file(workdir, ref['path'])
        if digest(files[key]) != ref['sha256']:
            raise ValueError('Desktop result artifact changed: ' + key)
    envelope, observation = read_json(files['envelope']), read_json(files['observation'])
    product = read_json(files['product_check'])
    from .action_journal import _journal
    claims = [item for item in _journal(workdir)['operations']
              if item.get('operation_id') == result.get('operation_id')]
    if len(claims) != 1:
        raise ValueError('Desktop result lost its unique claimed task action')
    claim = claims[0]
    expected_route = '|'.join((envelope['host']['host_id'],
                               envelope['host']['app_id'], envelope['host']['tool']))
    if (claim.get('plan_hash') != envelope.get('plan_hash')
            or claim.get('action_id') != envelope.get('action_id')
            or claim.get('route') != expected_route
            or claim.get('status') not in ('OUTPUT_SAVED', 'VERIFIED')
            or claim.get('inputs', {}).get('pptx', {}).get('sha256') != envelope['input_sha256']
            or claim.get('inputs', {}).get('scene', {}).get('sha256') != envelope['input_scene_sha256']
            or claim.get('output_targets', {}).get('Candidate.pptx') != envelope['output_pptx']
            or claim.get('output_targets', {}).get('desktop-result.json') != envelope['result_receipt_path']):
        raise ValueError('Desktop result differs from the frozen action claim')
    events = observation.get('events', [])
    required = ('TASK_COPY_OPENED', 'EDIT_OCCURRED', 'SAVED', 'REOPENED')
    if (result.get('operation_id') != envelope.get('operation_id')
            or result.get('plan_hash') != envelope.get('plan_hash')
            or observation.get('operation_id') != envelope.get('operation_id')
            or observation.get('plan_hash') != envelope.get('plan_hash')
            or observation.get('host_id') != envelope.get('host', {}).get('host_id')
            or observation.get('app_id') != envelope.get('host', {}).get('app_id')
            or observation.get('tool') != envelope.get('host', {}).get('tool')
            or observation.get('product_check') != result.get('product_check')
            or not isinstance(events, list)
            or any(event not in events for event in required)
            or [events.index(event) for event in required] != sorted(events.index(event) for event in required)
            or observation.get('output_sha256') != digest(files['candidate_pptx'])
            or files['candidate_pptx'] != safe_path(workdir, envelope['output_pptx'])
            or result_file != safe_path(workdir, envelope['result_receipt_path'])
            or digest(_task_file(workdir, envelope['input_pptx'])) != envelope['input_sha256']
            or digest(_task_file(workdir, envelope['input_scene'])) != envelope['input_scene_sha256']
            or product.get('status') != 'PASS_SAVED_PRODUCT_ONLY'
            or product.get('baseline_pptx_hash') != envelope['input_sha256']
            or product.get('candidate_pptx_hash') != digest(files['candidate_pptx'])
            or product != _product_check(workdir, envelope, files['candidate_pptx'])):
        raise ValueError('Desktop result no longer binds the saved output')
    scene_ref = result.get('candidate_scene')
    if scene_ref is None:
        if result.get('scene_state') != 'SAVED_PPT_AUTHORITATIVE_SCENE_SYNC_REQUIRED':
            raise ValueError('Unsynchronized editor result was mislabeled')
    else:
        from .inspect import check
        scene_file = _task_file(workdir, scene_ref['path'])
        if digest(scene_file) != scene_ref['sha256']:
            raise ValueError('Reconciled Scene changed')
        if check(read_json(scene_file), scene_file.parent, files['candidate_pptx'])['status'] != 'PASS':
            raise ValueError('Saved editor output no longer matches reconciled Scene')
    return {'status': 'PASS_SAVED_EDITOR_RETURN',
            'operation_id': result['operation_id'],
            'plan_hash': result['plan_hash'],
            'candidate_pptx_hash': digest(files['candidate_pptx']),
            'scene_state': result['scene_state'],
            'scope': 'task-owned saved output and host observation; separate render and human visual review remain distinct'}


def reconcile_scene(workdir, result_file, candidate_scene, output):
    """Bind a later Scene to the authoritative saved editor result immutably."""
    from .inspect import check
    workdir = Path(workdir).resolve()
    result_file = Path(result_file).resolve()
    candidate_scene = Path(candidate_scene).resolve()
    output = Path(output).resolve()
    if (result_file.parent != workdir or not candidate_scene.is_relative_to(workdir)
            or output.parent != workdir or output.exists()):
        raise ValueError('Desktop Scene reconciliation must use new task-owned files')
    audited = audit_result(result_file)
    result = read_json(result_file)
    pptx = _task_file(workdir, result['candidate_pptx']['path'])
    if (audited['candidate_pptx_hash'] != digest(pptx)
            or check(read_json(candidate_scene), candidate_scene.parent, pptx)['status'] != 'PASS'):
        raise ValueError('Reconciled Scene does not represent the saved editor product')
    scene_ref = {'path': candidate_scene.relative_to(workdir).as_posix(),
                 'sha256': digest(candidate_scene)}
    report = {'schema_version': 'desktop-scene-reconciliation-1',
              'status': 'SCENE_RECONCILED_TO_SAVED_PPT',
              'source_result': {'path': result_file.relative_to(workdir).as_posix(),
                                'sha256': digest(result_file)},
              'candidate_pptx': result['candidate_pptx'], 'candidate_scene': scene_ref,
              'next': 'Compile a revised drawing plan against this Scene before further drawing'}
    with _lock(workdir / '.desktop-state.lock'):
        pending_file = workdir / 'desktop-pending.json'
        pending = read_json(pending_file)
        if (pending.get('result', {}).get('sha256') != digest(result_file)
                or pending.get('candidate_pptx') != result['candidate_pptx']):
            raise ValueError('Another desktop edit became authoritative before reconciliation')
        write_json(output, report)
        pending.update(scene_state='SCENE_RECONCILED_TO_SAVED_PPT',
                       candidate_scene=scene_ref,
                       reconciliation={'path': output.relative_to(workdir).as_posix(),
                                       'sha256': digest(output)})
        write_json(pending_file, pending)
    return report
