"""Portable task journals, bounded resumption, verified caches and output promotion.

The host still interprets the source and decides acceptance.  A completed stage,
cache hit or installed file never implies scientific or visual acceptance.
Budgets measure wall time from initialization, including interruptions; resume
cannot silently grant more time or candidates.  Environment snapshots must be
supplied from a current backend/font probe, not a previous rendering receipt.
"""

import contextlib
import hashlib
import math
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
import uuid

from PIL import Image, ImageOps

from . import VERSION
from .common import ROOT, canonical, digest, identity, read_json, safe_path


def _path(path):
    path = Path(os.path.abspath(os.path.expanduser(str(path))))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symlink paths are not permitted for task state or delivery")
    return path


def _file(path):
    path = _path(path)
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Expected a regular file: " + str(path))
    return path


def _atomic_json(path, value):
    path = _path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextlib.contextmanager
def _lock(path):
    """OS locks release on process death; never unlink a potentially held lock."""
    path = _path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            if path.stat().st_size == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise BlockingIOError("Another task writer holds " + str(path)) from exc
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def implementation_identity():
    """Hash the actual release whitelist, including runtime rules and profiles."""
    from package_skill import collect_source
    files = {name: hashlib.sha256(data).hexdigest()
             for name, data in collect_source(ROOT).items()}
    return {"version": VERSION, "files_sha256": identity(files)}


def initialize(source, workdir, output, *, seconds, candidates):
    """Freeze the exact input and a lossless, orientation-corrected working PNG."""
    if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds) or seconds <= 0
            or type(candidates) is not int or candidates <= 0):
        raise ValueError("Explicit positive time and candidate budgets are required")
    started = time.time()
    source, workdir, output = _file(source), _path(workdir), _path(output)
    if (workdir.is_relative_to(ROOT) or output.is_relative_to(ROOT)
            or output == source or output.suffix.lower() != ".pptx"):
        raise ValueError("Use a new workdir outside the Skill and an explicit .pptx output")
    output_hash = digest(_file(output)) if output.exists() else None
    source_hash = digest(source)
    with Image.open(source) as image:
        image_format = image.format
        if (image_format == "PNG" and source.suffix.lower() != ".png") or (image_format == "JPEG" and source.suffix.lower() not in (".jpg", ".jpeg")):
            raise ValueError("Input extension and PNG/JPEG content disagree")
        if image_format not in ("PNG", "JPEG"):
            raise ValueError("Task initialization requires PNG or JPEG input")
        original_size = list(image.size)
        image.verify()
    with Image.open(source) as image:
        orientation = image.getexif().get(274)
        icc_profile = image.info.get("icc_profile")
    workdir.parent.mkdir(parents=True, exist_ok=True)
    workdir.mkdir()  # Atomic reservation; never adopt existing user directories.
    original = workdir / "inputs" / ("source.png" if image_format == "PNG" else "original" + source.suffix.lower())
    original.parent.mkdir()
    with source.open("rb") as incoming, original.open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing)
    if digest(original) != source_hash or digest(source) != source_hash:
        raise ValueError("Source changed during initialization; partial workdir retained")
    original.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    if image_format == "PNG":
        frozen = original
        width, height = original_size
    else:
        frozen = workdir / "inputs" / "source.png"
        with Image.open(original) as image:
            image = ImageOps.exif_transpose(image)
            width, height = image.size
            save_options = {"icc_profile": icc_profile} if icc_profile else {}
            image.convert("RGB").save(frozen, format="PNG", **save_options)
        frozen.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    working_hash = digest(frozen)
    session = {
        "format_version": 1, "session_id": uuid.uuid4().hex,
        "implementation": implementation_identity(), "status": "WORKING",
        "source": {"path": "inputs/source.png", "sha256": working_hash,
                    "width": width, "height": height},
        "original_source": {"path": str(original.relative_to(workdir)), "sha256": source_hash,
                            "format": image_format, "size": original_size,
                            "exif_orientation": orientation,
                            "icc_sha256": hashlib.sha256(icc_profile).hexdigest() if icc_profile else None},
        "output": {"path": str(output), "expected_sha256": output_hash},
        "started_at": started, "updated_at": started,
        "budget": {"seconds": seconds, "candidates": candidates,
                   "deadline": started + seconds, "candidates_used": 0},
        "elapsed_wall_seconds": 0, "stages": [], "deliveries": [],
        "usage": {"tokens": None, "tokens_source": "Unavailable from deterministic runtime",
                  "cpu_seconds_scope": "Current Python process; excludes child Office processes"},
    }
    if _exhausted(session):
        session["status"] = "PAUSED_RESOURCE_LIMIT"
    _save(workdir, session)
    return session


def load(workdir):
    """Read state and verify frozen input; performs no acceptance decision."""
    workdir = _path(workdir)
    session = read_json(_file(workdir / "session.json"))
    if session.get("format_version") != 1:
        raise ValueError("Unsupported task journal version")
    source = _file(safe_path(workdir, session["source"]["path"]))
    if digest(source) != session["source"]["sha256"]:
        raise ValueError("Frozen source hash changed")
    if session.get("original_source"):
        original = session["original_source"]
        if digest(_file(safe_path(workdir, original["path"]))) != original["sha256"]:
            raise ValueError("Frozen original source hash changed")
    return session


def _save(workdir, session):
    now = time.time()
    session["updated_at"] = now
    session["elapsed_wall_seconds"] = max(session["elapsed_wall_seconds"], now - session["started_at"])
    _atomic_json(Path(workdir) / "session.json", session)


def _exhausted(session, candidate=False):
    budget = session["budget"]
    return (time.time() >= budget["deadline"]
            or session["elapsed_wall_seconds"] >= budget["seconds"]
            or (candidate and budget["candidates_used"] >= budget["candidates"]))


def resume(workdir):
    """Recover abandoned journal entries after acquiring the actual writer lock."""
    workdir = _path(workdir)
    with _lock(workdir / ".stage.lock"), _lock(workdir / ".session.lock"):
        session = load(workdir)
        for entry in session["stages"]:
            if entry["status"] == "RUNNING":
                entry.update(status="INTERRUPTED", recovered_at=time.time(),
                             elapsed_seconds=None, cpu_seconds=None,
                             reason="Process ended before stage completion; exact duration unavailable")
        for entry in session["deliveries"]:
            if entry["status"] != "PREPARED":
                continue
            output = _path(session["output"]["path"])
            actual = digest(_file(output)) if output.exists() else None
            backup = entry["backup"]
            backup_ok = backup is None or (Path(backup).is_file() and digest(_file(backup)) == entry["previous_sha256"])
            if actual == entry["sha256"] and backup_ok:
                entry["status"] = "INSTALLED_RECOVERED"
                session["output"]["expected_sha256"] = actual
            else:
                entry["status"] = "INTERRUPTED"
                entry["reason"] = "Inspect preserved backup/staging file before any external changes"
        if _exhausted(session):
            session["status"] = "PAUSED_RESOURCE_LIMIT"
        session["resumed_implementation"] = implementation_identity()
        _save(workdir, session)
        return session


@contextlib.contextmanager
def stage(workdir, name, *, candidate=False):
    """Run one writer stage and persist timings even when its operation raises.

    The yielded dict may receive JSON-serializable task notes.  A completed stage
    means execution only.  Subprocesses still need their own timeout guards.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Stage name is required")
    workdir = _path(workdir)
    with _lock(workdir / ".stage.lock"):
        with _lock(workdir / ".session.lock"):
            session = load(workdir)
            if any(s["status"] == "RUNNING" for s in session["stages"]):
                raise ValueError("Interrupted task requires resume before starting another stage")
            if _exhausted(session, candidate):
                session["status"] = "PAUSED_RESOURCE_LIMIT"
                _save(workdir, session)
                raise TimeoutError("PAUSED_RESOURCE_LIMIT")
            if candidate:
                session["budget"]["candidates_used"] += 1
            entry = {"id": uuid.uuid4().hex, "name": name, "status": "RUNNING",
                     "started_at": time.time(), "candidate": candidate, "pid": os.getpid(),
                     "implementation": implementation_identity()}
            session["stages"].append(entry)
            _save(workdir, session)
        started, cpu = time.monotonic(), time.process_time()
        notes, failed = {}, None
        try:
            yield notes
        except BaseException as exc:
            failed = exc
            raise
        finally:
            with _lock(workdir / ".session.lock"):
                session = load(workdir)
                current = next(s for s in session["stages"] if s["id"] == entry["id"])
                current.update(ended_at=time.time(), elapsed_seconds=time.monotonic() - started,
                               cpu_seconds=time.process_time() - cpu, notes=notes,
                               status="FAILED" if failed else "COMPLETED")
                if failed:
                    current["error"] = type(failed).__name__ + ": " + str(failed)
                if _exhausted(session):
                    session["status"] = "PAUSED_RESOURCE_LIMIT"
                _save(workdir, session)
        if _exhausted(session):
            raise TimeoutError("PAUSED_RESOURCE_LIMIT; completed stage artifacts retained")


def cache_binding(workdir, *, scene, backend, environment, inputs=None, options=None):
    """Build a fresh cache identity; inputs maps logical names to workdir files.

    The backend version, platform, and font identity must be measured by the
    caller. Missing environment evidence disables caching instead of assuming a
    match. Scene source/evidence/profile and referenced resources are included.
    """
    workdir = _path(workdir)
    session = load(workdir)
    scene_path = _file(scene)
    if not scene_path.is_relative_to(workdir):
        raise ValueError("Scene and cache inputs must be inside this workdir")
    scene_data = read_json(scene_path)
    if scene_data.get("source", {}).get("sha256") != session["source"]["sha256"]:
        raise ValueError("Scene does not reference the frozen input")
    files = {"scene": scene_path, "source": workdir / session["source"]["path"]}

    def resources(value, trail="scene"):
        if isinstance(value, dict):
            if "path" in value and isinstance(value["path"], str):
                resource = _file(safe_path(scene_path.parent, value["path"]))
                if "sha256" in value and digest(resource) != value["sha256"]:
                    raise ValueError("Frozen Scene resource changed: " + trail)
                files[trail] = resource
            for key, child in value.items():
                resources(child, trail + "/" + key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                resources(child, trail + "/" + str(index))
    resources(scene_data)
    for name, path in (inputs or {}).items():
        files["input/" + name] = _file(path)
    records = {}
    for name, path in files.items():
        if not path.is_relative_to(workdir):
            raise ValueError("Cache input escapes workdir")
        records[name] = {"path": path.relative_to(workdir).as_posix(), "sha256": digest(path)}
    env = dict(environment or {})
    known = bool(backend and env.get("backend_version") and (env.get("platform") or env.get("os"))
                 and (env.get("font_inventory_hash") or env.get("fonts")))
    return {"format_version": 1, "source_sha256": session["source"]["sha256"],
            "implementation": implementation_identity(), "backend": backend,
            "environment": env, "inputs": records, "options": options or {},
            "cacheable": known}


def _binding_current(workdir, binding):
    if (not binding.get("cacheable") or binding.get("implementation") != implementation_identity()
            or binding.get("source_sha256") != load(workdir)["source"]["sha256"]):
        return False
    try:
        return bool(binding["inputs"]) and all(
            digest(_file(safe_path(workdir, record["path"]))) == record["sha256"]
            for record in binding["inputs"].values())
    except (OSError, ValueError, KeyError):
        return False


def cache_store(workdir, binding, artifacts):
    """Seal nonempty existing outputs; no content/native quality status is added."""
    workdir = _path(workdir)
    with _lock(workdir / ".session.lock"):
        if not _binding_current(workdir, binding):
            raise ValueError("Cache binding is stale or backend/font environment is incomplete")
        if not artifacts:
            raise ValueError("An empty artifact set cannot form a cache entry")
        outputs = {}
        protected = {r["path"] for r in binding["inputs"].values()} | {"session.json"}
        for name, path in artifacts.items():
            path = _file(path)
            if not path.is_relative_to(workdir):
                raise ValueError("Cached output escapes workdir")
            relative = path.relative_to(workdir).as_posix()
            if relative in protected or path.stat().st_size == 0:
                raise ValueError("Cache outputs must be nonempty generated files, not frozen inputs")
            outputs[name] = {"path": relative, "sha256": digest(path), "bytes": path.stat().st_size}
        record = {"key": identity(binding), "binding": binding, "artifacts": outputs,
                  "created_at": time.time(), "scope": "artifact_integrity_only"}
        _atomic_json(workdir / "cache" / (record["key"] + ".json"), record)
        return record


def cache_lookup(workdir, binding):
    """Return verified artifact records or None; callers supply a fresh binding."""
    workdir = _path(workdir)
    if not _binding_current(workdir, binding):
        return None
    path = workdir / "cache" / (identity(binding) + ".json")
    if not path.exists():
        return None
    try:
        record = read_json(_file(path))
        if record["key"] != identity(binding) or record["binding"] != binding or not record["artifacts"]:
            return None
        protected = {r["path"] for r in binding["inputs"].values()} | {"session.json"}
        for artifact in record["artifacts"].values():
            if artifact["path"] in protected or artifact["bytes"] <= 0:
                return None
            output = _file(safe_path(workdir, artifact["path"]))
            if output.stat().st_size != artifact["bytes"] or digest(output) != artifact["sha256"]:
                return None
        return record
    except (OSError, ValueError, KeyError, TypeError):
        return None


def install_output(workdir, candidate, *, plan_conformance=None,runtime_task=None):
    """Copy one candidate to the initialized target, preserving an existing file.

    Only that exact target may be replaced, and only if it still has the hash
    observed at initialization or the prior promotion. Crash journals and
    exclusive backup files remain recoverable. This does not award acceptance.
    """
    workdir, candidate = _path(workdir), _file(candidate)
    from .execution_contract import require_delivery
    require_delivery(runtime_task,candidate)
    if not candidate.is_relative_to(workdir) or candidate.suffix.lower() != ".pptx":
        raise ValueError("Delivery candidate must be a .pptx inside this task workdir")
    plan_status='NOT_APPLICABLE_LEGACY_TASK'
    if (workdir/'visual-loop.json').is_file():
        from .visual_loop import accepted_output
        plan_status = accepted_output(workdir, candidate)['status']
    elif (workdir/'drawing-plan.json').is_file():
        report_file=_file(plan_conformance or workdir/'plan-conformance.json')
        if not report_file.is_relative_to(workdir):
            raise ValueError('Plan conformance receipt must belong to the task')
        report=read_json(report_file)
        if (report.get('plan_hash')!=identity(read_json(workdir/'drawing-plan.json'))
                or report.get('pptx_hash')!=digest(candidate)
                or report.get('status')=='FAIL'):
            raise ValueError('Delivery candidate lacks a matching non-failing drawing-plan receipt')
        plan_status=report['status']
    with _lock(workdir / ".session.lock"):
        session = load(workdir)
        output = _path(session["output"]["path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        lock = output.parent / (".sci-rebuild-" + identity(str(output))[:16] + ".lock")
        with _lock(lock):
            previous = digest(_file(output)) if output.exists() else None
            if previous != session["output"]["expected_sha256"]:
                raise ValueError("Output changed outside this task; refusing to overwrite user changes")
            incoming = digest(candidate)
            token = uuid.uuid4().hex
            backup = output.with_name(output.stem + ".backup-" + token + output.suffix) if previous else None
            staged = output.with_name("." + output.name + ".pending-" + token)
            entry = {"id": token, "status": "PREPARED", "sha256": incoming,
                     "previous_sha256": previous, "backup": str(backup) if backup else None,
                     "staging": str(staged), "candidate": candidate.relative_to(workdir).as_posix(),
                     "implementation": implementation_identity(), "started_at": time.time(),
                     "scope": "file_installation_only", "plan_status": plan_status}
            session["deliveries"].append(entry)
            _save(workdir, session)
            if backup:
                with output.open("rb") as src, backup.open("xb") as dst:
                    shutil.copyfileobj(src, dst)
                    dst.flush()
                    os.fsync(dst.fileno())
                if digest(backup) != previous:
                    raise ValueError("Output changed while backing up; original and backup retained")
            with candidate.open("rb") as src, staged.open("xb") as dst:
                shutil.copyfileobj(src, dst)
                dst.flush()
                os.fsync(dst.fileno())
            if digest(staged) != incoming or digest(candidate) != incoming:
                raise ValueError("Candidate changed during output installation")
            actual = digest(_file(output)) if output.exists() else None
            if actual != previous:
                raise ValueError("Output changed during installation; refusing replacement")
            os.replace(staged, output)
            entry.update(status="INSTALLED", ended_at=time.time())
            session["output"]["expected_sha256"] = incoming
            _save(workdir, session)
            return entry
