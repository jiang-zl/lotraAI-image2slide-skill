#!/usr/bin/env python3
"""Build, verify, install, and remove an isolated lotraAI Image2Slide package.

SHA-256 checks detect package/install changes; they are not publisher signatures.
Existing directories are never upgraded in place. Choose a new versioned target.
This file uses only the Python standard library and locates source beside itself.
"""

import argparse
import fnmatch
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import unicodedata
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo


NAME = "lotra-image2slide-skill"
VERSION = "1.34.0"
SOURCE = Path(__file__).resolve().parents[1]
MANIFEST = "MANIFEST.json"
RECEIPT = ".lotraai-image2slide-install.json"
REQUIRED = {"SKILL.md", "README.md", "requirements.txt", "scripts/package_skill.py", "scripts/sci_rebuild.py",
            "config/natural-components.json", "config/customer-package.json", "config/context-policy.json",
            "references/execution-interface.md", "scripts/core/context_control.py",
            "references/workflow-optimization.md", "config/workflow-policy.json",
            "scripts/core/batch_plan.py", "scripts/core/workflow_control.py", "scripts/core/workflow_profile.py",
            "schemas/workflow-request.schema.json", "scripts/core/resource_facts.py",
            "references/resource-locality.md"}
MAX_FILES = 5000
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.IGNORECASE)
EXCLUDED_PARTS = {"design", "materials", "tests", "__pycache__", "agents.md", "agents.override.md"}


class PackageError(ValueError):
    """A package or requested filesystem operation violates the install contract."""


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def portable_name(name):
    if not isinstance(name, str) or not name or "\\" in name or name.startswith("/"):
        raise PackageError("Invalid portable package path")
    parts = name.split("/")
    for part in parts:
        if (part in ("", ".", "..") or part.endswith((".", " "))
                or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
                or RESERVED.match(part)):
            raise PackageError("Unsafe or platform-specific package path: " + name)
    return PurePosixPath(name)


def allowed(name):
    path = portable_name(name)
    parts = path.parts
    if any(part.startswith(".") or part.casefold() in EXCLUDED_PARTS for part in parts):
        return False
    if len(parts) == 1:
        return name in ("SKILL.md", "README.md", "README.zh-CN.md") or fnmatch.fnmatchcase(name, "requirements*.txt")
    if parts[0] == "scripts":
        if parts[-1].startswith('regression_') and name!='scripts/regression_contracts.py':
            return False
        return path.suffix in (".py", ".ps1", ".sh", ".mjs")
    if parts[0] == "references":
        if name=='references/release-notes.md':return False
        return path.suffix in (".md", ".json")
    if parts[0] == "agents":
        return name == "agents/openai.yaml"
    if parts[0] == 'assets':
        return False  # Personal component models are private, never distribution seeds.
    return len(parts) == 2 and parts[0] in ("schemas", "config") and path.suffix == ".json"


def check_names(names):
    seen = set()
    for name in names:
        portable_name(name)
        key = unicodedata.normalize("NFC", name).casefold()
        if key in seen:
            raise PackageError("Duplicate or nonportable case/Unicode collision: " + name)
        seen.add(key)
    files = set(names)
    for name in files:
        if any(str(parent) in files for parent in PurePosixPath(name).parents if str(parent) != "."):
            raise PackageError("Package file is also used as a directory: " + name)


def no_symlink_path(path):
    """Reject symlinks without first resolving them to a different location."""
    path = Path(os.path.abspath(os.path.expanduser(str(path))))
    # macOS exposes its system temporary directory through /var -> /private/var.
    # Canonicalize only these root-owned OS aliases, never caller-created links.
    if sys.platform == 'darwin':
        for alias, destination in (('/var', '/private/var'), ('/tmp', '/private/tmp')):
            root = Path(alias)
            if (path == root or root in path.parents) and root.is_symlink():
                if root.lstat().st_uid == 0 and os.path.normpath(os.path.join('/',os.readlink(root))) == destination:
                    path = Path(destination) / path.relative_to(root)
    for part in (path, *path.parents):
        if part.is_symlink():
            raise PackageError("Symlink paths are not allowed: " + str(part))
    return path


def read_regular(path, limit=MAX_FILE_BYTES):
    path = no_symlink_path(path)
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise PackageError("Expected a regular file: " + str(path))
    if metadata.st_size > limit:
        raise PackageError("File exceeds the package resource budget: " + str(path))
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise PackageError("File exceeds the package resource budget: " + str(path))
    return data


def collect_source(source=SOURCE):
    source = no_symlink_path(source)
    if not source.is_dir():
        raise PackageError("Skill source directory is missing")
    policy = customer_policy(read_regular(source/'config/customer-package.json'))
    included = set(policy['included_paths'])
    payload = {}
    for directory, directories, files in os.walk(source, followlinks=False):
        parent = Path(directory)
        if parent == source:
            directories[:] = [d for d in directories if d in ("scripts", "references", "schemas", "config", "agents", "assets")]
        else:
            directories[:] = [d for d in directories if not d.startswith(".") and d.casefold() not in EXCLUDED_PARTS]
        for child in directories:
            if (parent / child).is_symlink():
                raise PackageError("Symlink in package source: " + str(parent / child))
        for filename in sorted(files):
            path = parent / filename
            relative = path.relative_to(source).as_posix()
            if allowed(relative) and relative in included:
                payload[relative] = read_regular(path)
    check_payload(payload)
    return payload


def customer_policy(raw):
    try:
        value=json.loads(raw)
        paths=value['included_paths']
        if value.get('schema')!='lotra-customer-package-1' or value.get('version')!=VERSION:
            raise PackageError('Customer inventory must match this implementation version')
        if not isinstance(paths,list) or len(paths)!=len(set(paths)) or not REQUIRED<=set(paths):
            raise PackageError('Complete unique customer inventory required')
        check_names(paths)
        if any(not allowed(name) for name in paths):raise PackageError('Customer inventory includes development/private paths')
        return value
    except (KeyError,TypeError,ValueError) as error:
        if isinstance(error,PackageError):raise
        raise PackageError('Invalid customer package inventory') from error


def check_payload(payload):
    if not REQUIRED <= set(payload):
        raise PackageError("Missing required Skill files: " + ", ".join(sorted(REQUIRED - set(payload))))
    if len(payload) > MAX_FILES or sum(len(data) for data in payload.values()) > MAX_TOTAL_BYTES:
        raise PackageError("Package exceeds file count or total byte budget")
    check_names(payload)
    for name, data in payload.items():
        if not allowed(name):
            raise PackageError("File is outside the release whitelist: " + name)
        if len(data) > MAX_FILE_BYTES:
            raise PackageError("Package file exceeds byte budget: " + name)
    if any(not payload[name].strip() for name in REQUIRED):
        raise PackageError("Required Skill files must not be empty")
    policy=customer_policy(payload['config/customer-package.json'])
    if set(policy['included_paths'])!=set(payload):
        raise PackageError('Customer payload differs from its exact required inventory')
    try:
        catalog=json.loads(payload['config/natural-components.json'])
        if catalog.get('schema')!='natural-component-catalog-1' or not isinstance(catalog.get('items'),list):
            raise PackageError('Typed natural construction catalog is required')
        if catalog['items']:
            raise PackageError('A public skill must start with an empty personal component catalog')
        seen=set()
        for row in catalog['items']:
            name=row['path'];portable_name(name)
            if not name.startswith('assets/natural-components/') or not allowed(name) or name not in payload:
                raise PackageError('Catalog construction asset is absent or outside its release domain: '+name)
            if sha256(payload[name])!=row['sha256']:raise PackageError('Catalog asset hash mismatch: '+name)
            if row['id'] in seen:raise PackageError('Duplicate natural construction catalog ID')
            seen.add(row['id'])
    except (ValueError,KeyError,TypeError) as error:
        if isinstance(error,PackageError):raise
        raise PackageError('Invalid natural construction catalog') from error


def manifest_for(payload):
    return {"format_version": 1, "name": NAME, "version": VERSION,
            "files": {name: {"size": len(data), "sha256": sha256(data)} for name, data in sorted(payload.items())}}


def build(out):
    payload = collect_source()
    manifest = canonical(manifest_for(payload))
    archive = io.BytesIO()
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as z:
        for name, data in sorted({**payload, MANIFEST: manifest}.items()):
            item = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.external_attr = (stat.S_IFREG | 0o644) << 16
            item.compress_type = ZIP_DEFLATED
            z.writestr(item, data)
    out = no_symlink_path(out)
    if out.suffix.lower() != ".zip":
        raise PackageError("Build output must use a .zip filename")
    out.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects against an output appearing during the build.
    with out.open("xb") as handle:
        handle.write(archive.getvalue())
    return {"status": "PACKAGED", "name": NAME, "version": VERSION, "archive": str(out),
            "files": len(payload), "sha256": sha256(archive.getvalue()), "scope": "package_integrity_only"}


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PackageError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def parse_manifest(raw):
    if len(raw) > MAX_MANIFEST_BYTES:
        raise PackageError("Manifest exceeds byte budget")
    try:
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PackageError("Invalid UTF-8 JSON manifest") from exc
    if (not isinstance(manifest, dict) or set(manifest) != {"format_version", "name", "version", "files"}
            or type(manifest["format_version"]) is not int or manifest["format_version"] != 1
            or manifest["name"] != NAME or manifest["version"] != VERSION
            or not isinstance(manifest["files"], dict)):
        raise PackageError("Unsupported package identity, version, or manifest format")
    entries = manifest["files"]
    if not REQUIRED <= set(entries) or not entries or len(entries) > MAX_FILES:
        raise PackageError("Manifest has missing required files or exceeds file count budget")
    check_names(entries)
    total = 0
    for name, record in entries.items():
        if not allowed(name):
            raise PackageError("Manifest path is outside release whitelist: " + name)
        if (not isinstance(record, dict) or set(record) != {"size", "sha256"}
                or type(record["size"]) is not int or not 0 <= record["size"] <= MAX_FILE_BYTES
                or not isinstance(record["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])):
            raise PackageError("Invalid file record in manifest: " + name)
        total += record["size"]
    if total > MAX_TOTAL_BYTES:
        raise PackageError("Manifest exceeds total byte budget")
    return manifest


def verify_archive(archive):
    archive = no_symlink_path(archive)
    if archive.stat().st_size > MAX_TOTAL_BYTES + MAX_MANIFEST_BYTES:
        raise PackageError("ZIP exceeds package byte budget")
    with ZipFile(archive) as z:
        members = z.infolist()
        if len(members) > MAX_FILES + 1:
            raise PackageError("ZIP exceeds file count budget")
        check_names([entry.filename for entry in members])
        for entry in members:
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if entry.is_dir() or mode not in (0, stat.S_IFREG) or entry.flag_bits & 1:
                raise PackageError("ZIP contains a directory, symlink, special file, or encrypted entry")
            bound = MAX_MANIFEST_BYTES if entry.filename == MANIFEST else MAX_FILE_BYTES
            if entry.file_size > bound:
                raise PackageError("ZIP entry exceeds byte budget")
        if MANIFEST not in z.namelist():
            raise PackageError("Package manifest is missing")
        raw_manifest = z.read(MANIFEST)
        manifest = parse_manifest(raw_manifest)
        if set(z.namelist()) != set(manifest["files"]) | {MANIFEST}:
            raise PackageError("ZIP contents do not exactly match the manifest")
        payload = {}
        for name, record in manifest["files"].items():
            if z.getinfo(name).file_size != record["size"]:
                raise PackageError("Manifest size mismatch: " + name)
            data = z.read(name)
            if len(data) != record["size"] or sha256(data) != record["sha256"]:
                raise PackageError("Manifest SHA-256/size mismatch: " + name)
            payload[name] = data
    check_payload(payload)
    return payload, raw_manifest, manifest


def receipt_for(raw_manifest):
    return canonical({"format_version": 1, "name": NAME, "version": VERSION,
                      "manifest_sha256": sha256(raw_manifest), "installer": "package_skill.py"})


def project_target(target):
    """Keep this release in a project's own agent-skill directory."""
    target = no_symlink_path(target)
    if (target.parent.name != 'skills' or target.parent.parent.name != '.agents'
            or target.name not in (NAME, NAME + '-v' + VERSION)):
        raise PackageError('Installation must target PROJECT/.agents/skills/' + NAME + '[-v' + VERSION + ']')
    project = target.parent.parent.parent
    if (not project.is_dir() or project == Path.home()
            or project == Path(project.anchor)):
        raise PackageError('Skill target needs an existing project directory, not a user/global root')
    return target


def install(archive, target):
    payload, raw_manifest, manifest = verify_archive(archive)
    target = project_target(target)
    if os.path.lexists(target):
        raise PackageError("Target already exists; in-place upgrade is disabled. Choose a new versioned directory.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()  # Atomic reservation; no existing empty directory is accepted.
    contents = {**payload, MANIFEST: raw_manifest}
    for name, data in sorted(contents.items()):
        destination = target.joinpath(*PurePosixPath(name).parts)
        no_symlink_path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as handle:
            handle.write(data)
    # A failed installation intentionally leaves its directory for inspection.
    # The ownership marker is written only after every payload file was saved.
    with (target / RECEIPT).open("xb") as handle:
        handle.write(receipt_for(raw_manifest))
    verify_installation(target)
    return {"status": "INSTALLED", "name": NAME, "version": manifest["version"], "target": str(target),
            "files": len(payload), "manifest_sha256": sha256(raw_manifest), "scope": "package_integrity_only"}


def expected_directories(files):
    return {str(parent) for name in files for parent in PurePosixPath(name).parents if str(parent) != "."}


def verify_installation(target):
    target = no_symlink_path(target)
    if not target.is_dir():
        raise PackageError("Installed Skill directory is missing")
    raw_manifest = read_regular(target / MANIFEST, MAX_MANIFEST_BYTES)
    manifest = parse_manifest(raw_manifest)
    marker = read_regular(target / RECEIPT, MAX_MANIFEST_BYTES)
    if marker != receipt_for(raw_manifest):
        raise PackageError("Installation ownership marker or manifest changed")
    expected = set(manifest["files"]) | {MANIFEST, RECEIPT}
    found, directories = set(), set()
    for parent, dirs, files in os.walk(target, followlinks=False):
        parent = Path(parent)
        for filename in dirs + files:
            path = parent / filename
            if path.is_symlink():
                raise PackageError("Installed Skill contains a symlink; refusing removal")
        directories.update((parent / name).relative_to(target).as_posix() for name in dirs)
        found.update((parent / name).relative_to(target).as_posix() for name in files)
    if found != expected or directories != expected_directories(expected):
        raise PackageError("Installed Skill has added or missing files/directories; preserve user data and refuse removal")
    for name, record in manifest["files"].items():
        data = read_regular(target.joinpath(*PurePosixPath(name).parts))
        if len(data) != record["size"] or sha256(data) != record["sha256"]:
            raise PackageError("Installed file changed; refusing removal: " + name)
    return target, manifest, raw_manifest


def uninstall(target):
    target = project_target(target)
    target, manifest, raw_manifest = verify_installation(target)
    # Remove only the exact verified files. Never recursively delete a user tree.
    for name, record in manifest["files"].items():
        path = target.joinpath(*PurePosixPath(name).parts)
        if sha256(read_regular(path)) != record["sha256"]:
            raise PackageError("Installed file changed during removal: " + name)
        path.unlink()
    if read_regular(target / MANIFEST, MAX_MANIFEST_BYTES) != raw_manifest:
        raise PackageError("Manifest changed during removal")
    if read_regular(target / RECEIPT, MAX_MANIFEST_BYTES) != receipt_for(raw_manifest):
        raise PackageError("Ownership marker changed during removal")
    (target / MANIFEST).unlink()
    (target / RECEIPT).unlink()
    for directory in sorted(expected_directories(manifest["files"]), key=lambda name: len(PurePosixPath(name).parts), reverse=True):
        no_symlink_path(target / directory).rmdir()
    target.rmdir()
    return {"status": "REMOVED", "name": NAME, "version": manifest["version"], "target": str(target)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Isolated sci-rebuild package installer; upgrades require a new directory")
    commands = parser.add_subparsers(dest="command", required=True)
    package = commands.add_parser("build", help="Package the Skill containing this script")
    package.add_argument("--out", type=Path, required=True)
    add = commands.add_parser("install", help="Verify ZIP and install into a new Skill body directory")
    add.add_argument("archive", type=Path)
    add.add_argument("--target", type=Path, required=True)
    remove = commands.add_parser("uninstall", help="Remove an unchanged owned install; refuse user files")
    remove.add_argument("target", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build(args.out)
        elif args.command == "install":
            result = install(args.archive, args.target)
        else:
            result = uninstall(args.target)
    except (PackageError, OSError, BadZipFile, RuntimeError, NotImplementedError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
