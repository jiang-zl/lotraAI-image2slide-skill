"""Idempotent, budget-bound receipts for planned drawing and desktop actions.

Saved output, independently verified output and accepted result are distinct.
After an uncertain UI/tool failure the same operation cannot be blindly run
again; recovery requires inspecting the saved artifacts or a changed state.
"""

from pathlib import Path
import time

from .common import digest, identity, read_json, safe_path
from .session import _atomic_json, _exhausted, _lock, _save, load


def _journal(workdir):
    file = Path(workdir) / "actions.json"
    return read_json(file) if file.exists() else {"schema_version": "action-journal-1", "operations": []}


def _inside(workdir, path):
    path = Path(path).resolve()
    if not path.is_relative_to(Path(workdir).resolve()) or not path.is_file():
        raise ValueError("Action artifact must be an existing task-owned file")
    return {"path": path.relative_to(Path(workdir).resolve()).as_posix(), "sha256": digest(path)}


def _require_action(plan, action_id):
    matches = [a for a in plan.get("actions", []) if a.get("id") == action_id]
    if len(matches) != 1:
        raise ValueError("Action is absent or ambiguous in the frozen drawing plan")
    return matches[0]


def _fresh_extended_check(workdir, record):
    """Recompute non-PPT operations from sealed task inputs, never from a claim."""
    operation = record['operation']
    inputs, outputs = record['inputs'], record['outputs']

    def source(name):
        return safe_path(workdir, inputs[name]['path'])

    def product(name):
        return safe_path(workdir, outputs[name]['path'])

    if operation == 'raster_compare':
        from .raster_exception import compare
        contract = source('contract')
        actual = compare(read_json(contract), contract.parent,
                         source('vector_pptx'), source('vector_render_receipt'),
                         source('raster_pptx'), source('raster_render_receipt'))
        if actual != read_json(product('comparison.json')):
            raise ValueError('Saved raster comparison differs from fresh source-bound comparison')
        return actual['status']
    if operation == 'complete_hidden':
        from tempfile import TemporaryDirectory
        from .completion import compose, measure
        contract = source('contract')
        spec = read_json(contract)
        candidate_ref = read_json(source('candidate_ref'))
        with TemporaryDirectory(prefix='completion-check-') as temporary:
            trial = Path(temporary) / 'asset.png'
            expected = compose(spec, contract.parent, candidate_ref, trial)
            if (digest(trial) != digest(product('asset.png'))
                    or expected != read_json(product('completion.json'))):
                raise ValueError('Saved completion differs from a fresh hidden-only composition')
        review = source('semantic_review') if 'semantic_review' in inputs else None
        truth = read_json(source('ground_truth_ref')) if 'ground_truth_ref' in inputs else None
        actual = measure(spec, contract.parent, product('asset.png'), review, truth)
        if actual != read_json(product('measurement.json')):
            raise ValueError('Saved completion measurement differs from fresh semantic/support checks')
        return actual['status']
    if operation == 'measure':
        from tempfile import TemporaryDirectory
        from .typed_metrics import evaluate_images
        plan_file = source('metric_plan')
        with TemporaryDirectory(prefix='measure-check-') as temporary:
            actual = evaluate_images(read_json(plan_file), plan_file.parent,
                                     source('preview'), Path(temporary) / 'measurements.json',
                                     pptx=source('pptx') if 'pptx' in inputs else None,
                                     render_receipt=source('render_receipt') if 'render_receipt' in inputs else None)
        if actual != read_json(product('measurements.json')):
            raise ValueError('Saved metric report differs from fresh fixed-domain measurement')
        return 'MEASURED_NOT_ACCEPTED'
    raise ValueError('No independent audit route for this operation')


def _output_targets(workdir, action, output_targets):
    if output_targets is None:
        return None
    promised = set(action['expected_outputs'])
    optional = {'render.json', 'structure.json'}
    if not promised <= set(output_targets) or set(output_targets) - promised - optional:
        raise ValueError('Output targets must name every planned output and only supported verification artifacts')
    result = {}
    for key, target in sorted(output_targets.items()):
        target = Path(target).resolve()
        if not target.is_relative_to(Path(workdir).resolve()):
            raise ValueError('Action output target must remain in its task workspace')
        result[key] = target.relative_to(Path(workdir).resolve()).as_posix()
    if len(set(result.values())) != len(result):
        raise ValueError('Action outputs need distinct paths')
    return result


def claim(workdir, plan, action_id, operation_id, inputs, *, route, output_targets=None):
    """Reserve one action. Calling again returns its state, never repeats work."""
    workdir = Path(workdir).resolve()
    if not operation_id or not route:
        raise ValueError("Stable operation ID and observed execution route are required")
    action = _require_action(plan, action_id)
    targets = _output_targets(workdir, action, output_targets)
    with _lock(workdir / ".action.lock"), _lock(workdir / ".session.lock"):
        session = load(workdir)
        journal = _journal(workdir)
        existing = next((x for x in journal["operations"] if x["operation_id"] == operation_id), None)
        binding = {key: _inside(workdir, path) for key, path in sorted(inputs.items())}
        if existing:
            if (existing["plan_hash"] != identity(plan) or existing["action_id"] != action_id
                    or existing["inputs"] != binding or existing['route'] != route
                    or existing.get('output_targets') != targets):
                raise ValueError("Operation ID reused with different plan or files")
            return existing
        if any(x['plan_hash'] == identity(plan)
               and x['status'] in ('RUNNING', 'OUTPUT_SAVED', 'INTERRUPTED_REQUIRES_RECONCILIATION',
                                   'FAILED_REPLAN_REQUIRED')
               for x in journal['operations']):
            raise ValueError('Previous task action is unresolved; inspect and reconcile before a new operation ID')
        for dependency in action.get("depends_on", []):
            matches = [x for x in journal["operations"] if x["plan_hash"] == identity(plan)
                       and x["action_id"] == dependency and x["status"] == "VERIFIED"]
            if not matches:
                raise ValueError("Dependent action is not independently verified: " + dependency)
        candidate = action['operation'] not in ('render', 'inspect', 'measure', 'verify')
        plan_used = sum(bool(item.get('candidate_slot_charged')) for item in journal['operations']
                        if item.get('plan_hash') == identity(plan))
        elapsed = max(session['elapsed_wall_seconds'], time.time() - session['started_at'])
        if (_exhausted(session, candidate=candidate)
                or elapsed >= plan['budget']['seconds']
                or (candidate and plan_used >= plan['budget']['candidates'])):
            raise TimeoutError("PAUSED_RESOURCE_LIMIT; no new action may start")
        if targets and any((workdir / relative).exists() for relative in targets.values()):
            raise FileExistsError('Planned action output already exists; inspect before editing')
        if candidate:
            session['budget']['candidates_used'] += 1
            _save(workdir, session)
        record = {"operation_id": operation_id, "plan_hash": identity(plan), "action_id": action_id,
                  "operation": action["operation"], "route": route, "inputs": binding,
                  "expected_outputs": action["expected_outputs"], "required_checks": action["required_checks"],
                  "on_failure": action["on_failure"],
                  "output_targets": targets, "candidate_slot_charged": candidate,
                  "status": "RUNNING", "started_at": time.time(), "outputs": {}, "attempt": 1}
        journal["operations"].append(record)
        _atomic_json(workdir / "actions.json", journal)
        return record


def outputs_saved(workdir, operation_id, outputs):
    """Seal all promised files. An interrupted save must be reconciled first."""
    workdir = Path(workdir).resolve()
    with _lock(workdir / ".action.lock"):
        journal = _journal(workdir)
        record = next((x for x in journal["operations"] if x["operation_id"] == operation_id), None)
        if record is None:
            raise ValueError("Unclaimed operation")
        sealed = {key: _inside(workdir, path) for key, path in sorted(outputs.items())}
        if len({item['path'] for item in sealed.values()}) != len(sealed):
            raise ValueError('Saved action artifacts need distinct paths')
        if record.get('output_targets') and set(record['output_targets']) != set(sealed):
            raise ValueError('Saved outputs differ from the paths frozen before the action')
        for key, item in sealed.items():
            if record.get('output_targets') and key in record['output_targets'] and item['path'] != record['output_targets'][key]:
                raise ValueError('Saved output is not the path frozen before the action')
        missing = set(record["expected_outputs"]) - set(sealed)
        extra = set(sealed) - set(record["expected_outputs"])
        if missing or not extra <= {"render.json", "structure.json"}:
            raise ValueError("Missing planned output or unexpected verification artifact")
        if record["status"] in ("OUTPUT_SAVED", "VERIFIED"):
            if record["outputs"] != sealed:
                raise ValueError("Existing output receipt differs; do not repeat this operation")
            return record
        if record["status"] != "RUNNING":
            raise ValueError("Interrupted or failed operation requires explicit recovery")
        record.update(status="OUTPUT_SAVED", outputs=sealed, saved_at=time.time())
        _atomic_json(workdir / "actions.json", journal)
        return record


def verify(workdir, operation_id, evidence):
    """Bind independently checked evidence; text-only claims never yield PASS."""
    workdir = Path(workdir).resolve()
    with _lock(workdir / ".action.lock"):
        journal = _journal(workdir)
        record = next((x for x in journal["operations"] if x["operation_id"] == operation_id), None)
        if record is None or record["status"] not in ("OUTPUT_SAVED", "VERIFIED"):
            raise ValueError("Only sealed outputs can be verified")
        if record["status"] == "VERIFIED":
            return record
        for item in list(record["inputs"].values()) + list(record["outputs"].values()):
            if digest(safe_path(workdir, item["path"])) != item["sha256"]:
                raise ValueError("Action inputs or outputs changed after sealing")
        verification = read_json(evidence)
        if (verification.get("status") != "PASS"
                or verification.get("operation_id") != operation_id
                or verification.get("plan_hash") != record["plan_hash"]
                or verification.get("outputs") != record["outputs"]
                or not verification.get("verifier")):
            raise ValueError("Verification receipt does not bind the planned saved outputs")
        # Caller-supplied receipts are not trusted as independent quality proof.
        # Recompute the supported operation's actual saved evidence here.
        operation = record["operation"]
        if operation == "build":
            from .inspect import check
            scene_file = safe_path(workdir, record["inputs"]["scene"]["path"])
            pptx = safe_path(workdir, record["outputs"]["Candidate.pptx"]["path"])
            checked = check(read_json(scene_file), scene_file.parent, pptx)
            if checked["status"] != "PASS":
                raise ValueError("Saved build failed fresh native inspection")
        elif operation == "render":
            receipt = safe_path(workdir, record["outputs"]["render.json"]["path"])
            pptx = safe_path(workdir, record["inputs"]["pptx"]["path"])
            backend = read_json(receipt).get("backend")
            if backend == "LibreOffice":
                from .render import verify_alternative_render
                verify_alternative_render(pptx, receipt)
            elif backend == "PowerPoint":
                from .host_render import verify_render
                preview = safe_path(workdir, record["outputs"]["Final_preview.png"]["path"])
                verify_render(pptx, preview, read_json(receipt))
            else:
                raise ValueError("Unknown render backend")
        elif operation == "inspect":
            from .inspect import check
            scene_file = safe_path(workdir, record["inputs"]["scene"]["path"])
            pptx = safe_path(workdir, record["inputs"]["pptx"]["path"])
            actual = check(read_json(scene_file), scene_file.parent, pptx)
            reported = read_json(safe_path(workdir, record["outputs"]["structure.json"]["path"]))
            if actual != reported or actual["status"] != "PASS":
                raise ValueError("Saved structural report differs from fresh inspection")
        elif operation == "native_edit":
            from .desktop_bridge import audit_result
            result = safe_path(workdir, record["outputs"]["desktop-result.json"]["path"])
            pptx = safe_path(workdir, record["outputs"]["Candidate.pptx"]["path"])
            audited = audit_result(result)
            if (audited['operation_id'] != operation_id
                    or audited['plan_hash'] != record['plan_hash']
                    or audited['candidate_pptx_hash'] != digest(pptx)):
                raise ValueError('Desktop edit receipt belongs to another saved candidate')
        elif operation in ('raster_compare', 'complete_hidden', 'measure'):
            checked_status = _fresh_extended_check(workdir, record)
        else:
            raise ValueError("No deterministic independent verifier for this action; retain OUTPUT_SAVED")
        record.update(status="VERIFIED", verified_at=time.time(), verification=_inside(workdir, evidence),
                      checked_status=checked_status if operation in ('raster_compare', 'complete_hidden', 'measure') else 'PASS')
        _atomic_json(workdir / "actions.json", journal)
        return record


def check_saved_action(workdir, operation_id, output):
    """Create the standard receipt and run the fresh operation-specific check."""
    workdir = Path(workdir).resolve()
    output = Path(output).resolve()
    if not output.is_relative_to(workdir) or output.exists():
        raise ValueError('Action check receipt must be a new task-owned file')
    journal = _journal(workdir)
    matches = [item for item in journal['operations'] if item['operation_id'] == operation_id]
    if len(matches) != 1 or matches[0]['status'] != 'OUTPUT_SAVED':
        raise ValueError('Only one sealed, not-yet-verified action can be checked')
    record = matches[0]
    receipt = {'status': 'PASS', 'operation_id': operation_id,
               'plan_hash': record['plan_hash'], 'outputs': record['outputs'],
               'verifier': 'lotraai-fresh-action-check-v1'}
    _atomic_json(output, receipt)
    try:
        return verify(workdir, operation_id, output)
    except Exception as exc:
        output.unlink(missing_ok=True)
        mark_failed(workdir, operation_id, type(exc).__name__ + ': ' + str(exc))
        raise


def mark_failed(workdir, operation_id, reason):
    """Freeze a failed saved check; a revised plan is needed before more work."""
    workdir = Path(workdir).resolve()
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('Failed action needs a concrete diagnostic')
    with _lock(workdir / '.action.lock'):
        journal = _journal(workdir)
        record = next((item for item in journal['operations']
                       if item['operation_id'] == operation_id), None)
        if record is None or record['status'] != 'OUTPUT_SAVED':
            raise ValueError('Only a saved action with a failed check can be marked failed')
        record.update(status='FAILED_REPLAN_REQUIRED', failed_at=time.time(),
                      failure_reason=reason, next=record.get('on_failure'))
        _atomic_json(workdir / 'actions.json', journal)
        return record


def recover(workdir):
    """Stop uncertain actions. Never automatically issue the same edit twice."""
    workdir = Path(workdir).resolve()
    with _lock(workdir / ".action.lock"):
        journal = _journal(workdir)
        for record in journal["operations"]:
            if record["status"] == "RUNNING":
                record.update(status="INTERRUPTED_REQUIRES_RECONCILIATION", interrupted_at=time.time())
        _atomic_json(workdir / "actions.json", journal)
        return journal


def reconcile_interrupted(workdir, operation_id, observed_outputs=None):
    """Inspect frozen targets after a crash; never grant a blind retry.

    With no output, mark the attempt abandoned so a fresh operation ID can be
    claimed. With all outputs, seal their actual hashes for independent verify.
    A partial save stays blocked for manual inspection and repair.
    """
    workdir = Path(workdir).resolve()
    with _lock(workdir / '.action.lock'):
        journal = _journal(workdir)
        record = next((x for x in journal['operations'] if x['operation_id'] == operation_id), None)
        if record is None or record['status'] != 'INTERRUPTED_REQUIRES_RECONCILIATION':
            raise ValueError('Only a recorded interrupted operation can be reconciled')
        targets = record.get('output_targets')
        if not targets:
            raise ValueError('Interrupted operation has no frozen output paths; inspect manually')
        present = {key: (workdir / relative).is_file() for key, relative in targets.items()}
        if observed_outputs is None:
            if any(present.values()):
                raise ValueError('Saved or partial output exists; inspect and seal it before retrying')
            record.update(status='ABANDONED_AFTER_NO_OUTPUT_INSPECTION',
                          reconciled_at=time.time(), observed_output_presence=present)
        else:
            optional = {'render.json', 'structure.json'}
            if (not set(targets) <= set(observed_outputs)
                    or set(observed_outputs) - set(targets) - optional
                    or not all(present.values())):
                raise ValueError('Partial output cannot be sealed as a complete action')
            sealed = {key: _inside(workdir, path) for key, path in sorted(observed_outputs.items())}
            if len({item['path'] for item in sealed.values()}) != len(sealed):
                raise ValueError('Observed action artifacts need distinct paths')
            if any(sealed[key]['path'] != targets[key] for key in targets):
                raise ValueError('Observed output differs from the frozen action target')
            if any(digest(safe_path(workdir, item['path'])) != item['sha256'] for item in record['inputs'].values()):
                raise ValueError('Action input changed before interrupted output reconciliation')
            record.update(status='OUTPUT_SAVED', outputs=sealed, saved_at=time.time(),
                          reconciled_at=time.time(), observed_output_presence=present)
        _atomic_json(workdir / 'actions.json', journal)
        return record


def audit_verified(workdir, record):
    """Fresh read-only recheck so a copied/edited journal cannot prove action PASS."""
    workdir = Path(workdir).resolve()
    if record.get("status") != "VERIFIED" or not record.get("verification"):
        raise ValueError("Action is not independently verified")
    for item in list(record["inputs"].values()) + list(record["outputs"].values()) + [record["verification"]]:
        if digest(safe_path(workdir, item["path"])) != item["sha256"]:
            raise ValueError("Journal artifacts changed after verification")
    evidence = read_json(safe_path(workdir, record["verification"]["path"]))
    if (evidence.get("status") != "PASS" or evidence.get("operation_id") != record["operation_id"]
            or evidence.get("plan_hash") != record["plan_hash"]
            or evidence.get("outputs") != record["outputs"]):
        raise ValueError("Action verifier receipt no longer matches saved result")
    operation = record["operation"]
    if operation in ("build", "inspect"):
        from .inspect import check
        scene_file = safe_path(workdir, record["inputs"]["scene"]["path"])
        pptx_item = (record["outputs"]["Candidate.pptx"] if operation == "build"
                     else record["inputs"]["pptx"])
        pptx = safe_path(workdir, pptx_item["path"])
        fresh = check(read_json(scene_file), scene_file.parent, pptx)
        if fresh["status"] != "PASS":
            raise ValueError("Fresh saved-PPT inspection failed")
        if operation == "inspect":
            reported = read_json(safe_path(workdir, record["outputs"]["structure.json"]["path"]))
            if reported != fresh:
                raise ValueError("Saved inspection report is stale")
    elif operation == "render":
        receipt_file = safe_path(workdir, record["outputs"]["render.json"]["path"])
        pptx = safe_path(workdir, record["inputs"]["pptx"]["path"])
        receipt = read_json(receipt_file)
        if receipt.get("backend") == "LibreOffice":
            from .render import verify_alternative_render
            verify_alternative_render(pptx, receipt_file)
        elif receipt.get("backend") == "PowerPoint":
            from .host_render import verify_render
            preview = safe_path(workdir, record["outputs"]["Final_preview.png"]["path"])
            verify_render(pptx, preview, receipt)
        else:
            raise ValueError("Unknown action renderer")
    elif operation == "native_edit":
        from .desktop_bridge import audit_result
        result = safe_path(workdir, record["outputs"]["desktop-result.json"]["path"])
        pptx = safe_path(workdir, record["outputs"]["Candidate.pptx"]["path"])
        audited = audit_result(result)
        if (audited['operation_id'] != record['operation_id']
                or audited['plan_hash'] != record['plan_hash']
                or audited['candidate_pptx_hash'] != digest(pptx)):
            raise ValueError('Desktop edit receipt no longer matches the journal')
    elif operation in ('raster_compare', 'complete_hidden', 'measure'):
        if _fresh_extended_check(workdir, record) != record.get('checked_status'):
            raise ValueError('Saved action decision changed after verification')
    else:
        raise ValueError("No independent audit route for this operation")
    return True
