"""Promote a local edit only after rechecking saved objects, render and Office.

The selected pointer changes once, after all candidate files and evidence are
sealed. A failure leaves the previous selection intact and the draft available
for diagnosis. This is a task-local transaction, never a global Skill update.
"""

from pathlib import Path
import shutil
import tempfile
import uuid

from .common import digest, identity, read_json, safe_path
from .local_edit import _assets, check_scene_protection, prepare_leaf_edit
from .saved_ppt_diff import verify_local_change
from .session import _atomic_json, _lock


def _verify_render(pptx, preview, receipt_file):
    receipt = read_json(receipt_file)
    if receipt.get("backend") == "LibreOffice" or receipt.get("schema")=="presentation-backend-1.36.0":
        from .render import verify_alternative_render
        proof = verify_alternative_render(pptx, receipt_file)
    elif receipt.get("backend") == "PowerPoint":
        from .host_render import verify_render
        proof = verify_render(pptx, preview, receipt)
    else:
        raise ValueError("Unknown local-edit renderer")
    if receipt.get("preview_hash") != digest(preview):
        raise ValueError("Render receipt does not bind supplied preview")
    return receipt, proof


def verify_candidate(*, baseline, baseline_scene, candidate_scene, baseline_pptx,
                     candidate_pptx, baseline_preview, noop_preview, candidate_preview,
                     baseline_render_receipt, noop_render_receipt, candidate_render_receipt,
                     preparation, contract, authorization, visual_request, resources,
                     native_plan=None, native_office_dir=None):
    """Return scoped status; never turn alternative rendering into Office PASS."""
    from .inspect import check
    from .render_protection import compare_rendered
    base_scene, result_scene = read_json(baseline_scene), read_json(candidate_scene)
    if (baseline.get("schema_version") != "approved-baseline-1"
            or baseline.get("status") not in {"USER_CONFIRMED_NOT_FULL_QA",
                                               "SELECTED_FROM_USER_CONFIRMED_NOT_FULL_QA"}):
        raise ValueError("Selection requires the user-confirmed working baseline")
    if (baseline["scene_hash"] != identity(base_scene)
            or baseline["pptx_hash"] != digest(baseline_pptx)
            or baseline["preview_hash"] != digest(baseline_preview)
            or baseline["render_receipt_hash"] != digest(baseline_render_receipt)
            or baseline["assets_hash"] != identity(_assets(base_scene, Path(baseline_scene).parent))):
        raise ValueError("Approved baseline binding changed")
    reproduced_scene, reproduced_preparation = prepare_leaf_edit(
        base_scene, Path(baseline_scene).parent, baseline, baseline_pptx, contract, authorization)
    if reproduced_scene != result_scene or reproduced_preparation != preparation:
        raise ValueError("Candidate edit does not reproduce frozen user-intent leaf authorization")
    if (preparation.get("candidate_scene_hash") != identity(result_scene)
            or preparation.get("base_pptx_hash") != digest(baseline_pptx)):
        raise ValueError("Candidate is not the prepared local edit")
    allowed = {(x["object_id"], x["path"]) for x in preparation["write_set"]}
    scene_guard = check_scene_protection(base_scene, result_scene, allowed)
    native_structure = check(result_scene, Path(candidate_scene).parent, candidate_pptx)
    saved_guard = verify_local_change(baseline_pptx, candidate_pptx, preparation)
    old_receipt, old_proof = _verify_render(baseline_pptx, baseline_preview, baseline_render_receipt)
    noop_receipt, noop_proof = _verify_render(baseline_pptx, noop_preview, noop_render_receipt)
    new_receipt, new_proof = _verify_render(candidate_pptx, candidate_preview, candidate_render_receipt)
    q = visual_request
    image_guard = compare_rendered(resources,q["anchor_preview"],q["noop_preview"],
                                   q["candidate_preview"],q["allowed_mask"],
                                   q["anchor_receipt"],q["noop_receipt"],q["candidate_receipt"])
    if (q["anchor_preview"]["sha256"] != digest(baseline_preview)
            or q["noop_preview"]["sha256"] != digest(noop_preview)
            or q["candidate_preview"]["sha256"] != digest(candidate_preview)):
        raise ValueError("Visual protection uses other preview files")
    if (q["anchor_receipt"] != old_receipt or q["noop_receipt"] != noop_receipt
            or q["candidate_receipt"] != new_receipt):
        raise ValueError("Visual protection substituted a render protocol receipt")
    native_status = "UNVERIFIED"
    if native_plan is not None and native_office_dir is not None:
        from .native_task import verify
        with tempfile.TemporaryDirectory(prefix="lotraai-local-native-") as directory:
            native = verify(native_plan, native_office_dir, Path(directory) / "verification.json")
        if native.get("source_pptx_hash") != digest(candidate_pptx):
            raise ValueError("Native editor evidence is for another candidate")
        native_status = native["status"]
    gates = {"scene_protection": scene_guard["status"],
             "saved_ppt_protection": saved_guard["status"],
             "native_structure": native_structure["status"],
             "render_protection": image_guard["status"],
             "target_renderer": "PASS" if old_receipt["backend"] == noop_receipt["backend"] == new_receipt["backend"] == "PowerPoint" else "UNVERIFIED",
             "native_editor": native_status}
    status = ("FAIL" if any(v == "FAIL" for v in gates.values()) else
              "PASS_LOCAL_EDIT" if all(v in ("PASS", "PASS_SCENE_PRODUCT_ONLY", "PASS_SAVED_PRODUCT_ONLY", "PASS_RENDER_PROTECTION_ONLY") for v in gates.values()) else
              "UNVERIFIED")
    arguments = {"baseline": baseline, "baseline_scene": str(baseline_scene),
                 "candidate_scene": str(candidate_scene), "baseline_pptx": str(baseline_pptx),
                 "candidate_pptx": str(candidate_pptx), "baseline_preview": str(baseline_preview),
                 "noop_preview": str(noop_preview), "candidate_preview": str(candidate_preview),
                 "baseline_render_receipt": str(baseline_render_receipt),
                 "noop_render_receipt": str(noop_render_receipt),
                 "candidate_render_receipt": str(candidate_render_receipt),
                 "preparation": preparation, "contract": contract,
                 "authorization": authorization, "visual_request": visual_request,
                 "resources": str(resources), "native_plan": str(native_plan) if native_plan else None,
                 "native_office_dir": str(native_office_dir) if native_office_dir else None}
    return {"schema_version": "local-edit-verification-1", "status": status,
            "verification_arguments": arguments,
            "gates": gates, "baseline_scene_hash": identity(base_scene),
            "candidate_scene_hash": identity(result_scene),
            "baseline_pptx_hash": digest(baseline_pptx), "candidate_pptx_hash": digest(candidate_pptx),
            "candidate_preview_hash": digest(candidate_preview),
            "candidate_render_receipt_hash": digest(candidate_render_receipt),
            "preparation_hash": identity(preparation), "scene_guard": scene_guard,
            "saved_guard": saved_guard, "image_guard": image_guard,
            "scope": "one local edit only; full source-fidelity QA remains separate"}


def promote(workdir, expected_selected_hash, verification, candidate_scene,
            candidate_pptx, candidate_preview, candidate_render_receipt):
    """CAS the task-local selected pointer only for a fully verified candidate."""
    workdir = Path(workdir).resolve()
    if verification.get("status") != "PASS_LOCAL_EDIT":
        raise ValueError("Unverified or failed local edit cannot replace the selected version")
    arguments = verification.get("verification_arguments")
    if not isinstance(arguments, dict) or verify_candidate(**arguments) != verification:
        raise ValueError("Local edit verification cannot be freshly reproduced")
    expected = {"candidate_scene_hash": identity(read_json(candidate_scene)),
                "candidate_pptx_hash": digest(candidate_pptx),
                "candidate_preview_hash": digest(candidate_preview),
                "candidate_render_receipt_hash": digest(candidate_render_receipt)}
    if any(verification.get(key) != value for key, value in expected.items()):
        raise ValueError("Selection evidence belongs to another candidate")
    with _lock(workdir / ".selected.lock"):
        pointer = workdir / "selected.json"
        current = read_json(pointer) if pointer.exists() else None
        if (identity(current) if current else None) != expected_selected_hash:
            raise ValueError("Selected version changed; reconcile external or concurrent edits")
        arguments = verification["verification_arguments"]
        if current:
            if any(verification.get(key) != current.get(previous) for key, previous in
                   (("baseline_scene_hash", "candidate_scene_hash"),
                    ("baseline_pptx_hash", "candidate_pptx_hash"))):
                raise ValueError("Repeated edit does not start from selected Scene and PPT")
            manifest = workdir / "local-versions" / current["version_id"] / "manifest.json"
            previous_manifest = read_json(manifest) if manifest.is_file() else None
            if (previous_manifest is None or identity(previous_manifest) != current["manifest_hash"]
                    or previous_manifest.get("root_anchor") != current.get("root_anchor")
                    or previous_manifest.get("cumulative", {}).get("allowed_write_set") != current.get("cumulative_write_set")):
                raise ValueError("Selected version manifest changed")
            root_anchor = current["root_anchor"]
            previous_writes = current["cumulative_write_set"]
            previous_mask = safe_path(workdir, current["cumulative_mask_path"])
            if digest(previous_mask) != current["cumulative_mask_hash"]:
                raise ValueError("Previous cumulative mask changed")
        else:
            root_anchor = {field: str(arguments[path]) for field, path in
                           (("scene", "baseline_scene"), ("pptx", "baseline_pptx"),
                            ("preview", "baseline_preview"),
                            ("render_receipt", "baseline_render_receipt"))}
            root_anchor.update({field + "_hash": digest(path) for field, path in root_anchor.items()})
            root_anchor["approved_baseline_hash"] = identity(arguments["baseline"])
            previous_writes, previous_mask = [], None
        from .cumulative_anchor import verify_cumulative
        q = arguments["visual_request"]
        current_mask = safe_path(arguments["resources"], q["allowed_mask"]["path"])
        staged = workdir / "local-candidates" / uuid.uuid4().hex
        cumulative_mask = staged / "cumulative-mask.png"
        cumulative = verify_cumulative(root_anchor, candidate_scene, candidate_pptx,
                                       candidate_preview, arguments["noop_preview"],
                                       arguments["noop_render_receipt"], candidate_render_receipt,
                                       previous_writes, arguments["preparation"]["write_set"],
                                       previous_mask, current_mask, cumulative_mask)
        _atomic_json(staged / "cumulative.json", cumulative)
        if cumulative["status"] != "PASS_CUMULATIVE_ANCHOR_ONLY":
            raise ValueError("Cumulative original-anchor protection failed; selected version preserved")
        package = {"schema_version": "local-selected-version-1", "verification": verification,
                   "parent_selected_hash": expected_selected_hash, "artifacts": expected,
                   "cumulative": cumulative, "root_anchor": root_anchor}
        version_id = identity(package)[:24]
        directory = workdir / "local-versions" / version_id
        if directory.exists():
            stored = read_json(directory / "manifest.json")
            if stored != package:
                raise ValueError("Version ID collision or modified immutable candidate")
        else:
            for source, name in ((candidate_scene, "scene.json"), (candidate_pptx, "Candidate.pptx"),
                                 (candidate_preview, "Final_preview.png"),
                                 (candidate_render_receipt, "render.json")):
                shutil.copyfile(source, staged / name)
            for ref in _assets(read_json(candidate_scene), Path(candidate_scene).parent).values():
                source = safe_path(Path(candidate_scene).parent, ref["path"])
                target = staged / ref["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            receipt = read_json(candidate_render_receipt)
            pdf = (Path(receipt["pdf_path"]) if receipt.get("pdf_path") else Path(candidate_render_receipt).parent / "Final.pdf")
            if pdf.is_file():
                shutil.copyfile(pdf, staged / "Final.pdf")
            _atomic_json(staged / "manifest.json", package)
            for name, key in (("scene.json", "candidate_scene_hash"), ("Candidate.pptx", "candidate_pptx_hash"),
                              ("Final_preview.png", "candidate_preview_hash"),
                              ("render.json", "candidate_render_receipt_hash")):
                observed = identity(read_json(staged / name)) if name == "scene.json" else digest(staged / name)
                if observed != expected[key]:
                    raise ValueError("Incomplete local candidate retained without activation")
            if digest(staged / "cumulative-mask.png") != cumulative["union_mask_hash"]:
                raise ValueError("Incomplete cumulative mask retained without activation")
            # A crash can leave `staged` inactive, but never a half-populated
            # selected version. Rename one complete directory before the CAS.
            directory.parent.mkdir(parents=True, exist_ok=True)
            staged.rename(directory)
        for name, key in (("scene.json", "candidate_scene_hash"), ("Candidate.pptx", "candidate_pptx_hash"),
                          ("Final_preview.png", "candidate_preview_hash"),
                          ("render.json", "candidate_render_receipt_hash")):
            observed = identity(read_json(directory / name)) if name == "scene.json" else digest(directory / name)
            if observed != expected[key]:
                raise ValueError("Staged candidate changed before pointer update")
        if digest(directory / "cumulative-mask.png") != cumulative["union_mask_hash"]:
            raise ValueError("Staged cumulative protection mask changed")
        selected = {"schema_version": "local-selected-pointer-1", "version_id": version_id,
                    "manifest_hash": identity(package), "candidate_pptx_hash": expected["candidate_pptx_hash"],
                    "candidate_scene_hash": expected["candidate_scene_hash"],
                    "candidate_preview_hash": expected["candidate_preview_hash"],
                    "candidate_render_receipt_hash": expected["candidate_render_receipt_hash"],
                    "root_anchor": root_anchor, "cumulative_write_set": cumulative["allowed_write_set"],
                    "cumulative_mask_path": str((directory / "cumulative-mask.png").relative_to(workdir)),
                    "cumulative_mask_hash": cumulative["union_mask_hash"],
                    "status": "PASS_LOCAL_EDIT_NOT_FULL_QA"}
        _atomic_json(pointer, selected)
        return selected


def selected_baseline(workdir):
    """Bind the selected version for the next small edit without claiming new QA."""
    workdir = Path(workdir).resolve()
    selected = read_json(workdir / "selected.json")
    directory = safe_path(workdir, "local-versions/" + selected["version_id"])
    manifest = read_json(directory / "manifest.json")
    if identity(manifest) != selected["manifest_hash"]:
        raise ValueError("Selected version manifest changed")
    if (manifest.get("root_anchor") != selected.get("root_anchor")
            or manifest.get("cumulative", {}).get("allowed_write_set") != selected.get("cumulative_write_set")):
        raise ValueError("Selected version cumulative anchor changed")
    scene_file, pptx, preview, receipt_file = [directory / name for name in
                                               ("scene.json", "Candidate.pptx", "Final_preview.png", "render.json")]
    bindings = {"scene_hash": identity(read_json(scene_file)), "pptx_hash": digest(pptx),
                "preview_hash": digest(preview), "render_receipt_hash": digest(receipt_file)}
    if any(bindings[key] != selected["candidate_" + key] for key in bindings):
        raise ValueError("Selected version artifact changed")
    receipt, _ = _verify_render(pptx, preview, receipt_file)
    scene = read_json(scene_file)
    assets = _assets(scene, directory)
    root = selected["root_anchor"]
    for field in ("scene", "pptx", "preview", "render_receipt"):
        if digest(root[field]) != root[field + "_hash"]:
            raise ValueError("Original approved protection anchor changed")
    return {"schema_version": "approved-baseline-1",
            "status": "SELECTED_FROM_USER_CONFIRMED_NOT_FULL_QA",
            "approval": {"kind": "inherited_from_user_confirmed",
                         "original_approved_baseline_hash": root["approved_baseline_hash"]},
            **bindings, "assets_hash": identity(assets), "assets": assets,
            "environment": receipt.get("environment") or receipt.get("current_environment") or {},
            "source_reference_hash": scene["source"]["sha256"],
            "protected_anchor_scene_hash": identity(read_json(root["scene"]))}
