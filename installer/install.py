#!/usr/bin/env python3
"""Install an immutable lotraAI bundle offline, entirely inside one project."""
import argparse
import copy
import functools
import hashlib
import importlib.util
import json
import os
import platform
import posixpath
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import unicodedata
import uuid
import zipfile
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
VERSION = '1.37.3'
SCHEMA = 'lotra-offline-product-bundle-1'
DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.new-' + uuid.uuid4().hex)
    with temporary.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    os.replace(temporary, path)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def portable(name):
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise ValueError('Invalid resource name')
    p = PurePosixPath(name)
    if p.is_absolute() or any(s in ('', '.', '..') or ':' in s for s in p.parts) or str(p) != name:
        raise ValueError('Resource escapes its root: ' + name)
    return p


@functools.lru_cache(maxsize=32)
def resolved_root(text):
    return Path(text).resolve()


def within(root, name):
    # Reuse the canonical root within this finite invocation. Every live leaf
    # and ancestor is still checked for redirection before each access.
    root = resolved_root(str(root))
    value = root.joinpath(*portable(name).parts)
    for part in (value, *value.parents):
        if part == root.parent:
            break
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('Preserve a redirected install path: ' + str(part))
    if not value.is_relative_to(root):
        raise ValueError('Install resource escaped its root')
    return value


def same_bytes(path, record):
    return path.is_file() and path.stat().st_size == record['bytes'] and sha(path) == record['sha256']


def event(phase, **values):
    if globals().get('EVENT_LOG'):
        with EVENT_LOG.open('a',encoding='utf-8') as stream:stream.write(json.dumps({'phase':phase,**values},ensure_ascii=True)+'\n')


def extended_windows_path(path):
    text = str(path)
    if os.name != 'nt' or text.startswith('\\\\?\\'):
        return path
    return Path('\\\\?\\UNC\\' + text[2:] if text.startswith('\\\\') else '\\\\?\\' + text)


def readable_windows_path(path):
    text = str(path)
    if os.name == 'nt' and text.startswith('\\\\?\\UNC\\'):
        return Path('\\\\' + text[8:])
    if os.name == 'nt' and text.startswith('\\\\?\\'):
        return Path(text[4:])
    return path


def platform_key():
    system, machine = platform.system(), platform.machine().lower()
    if system == 'Windows':
        key = 'windows-' + ('amd64' if machine in ('amd64', 'x64', 'x86_64') else machine) + '-cp312'
    elif system == 'Darwin':
        key = 'macos-' + ('arm64' if machine == 'aarch64' else machine) + '-cp312'
        if tuple(int(n) for n in platform.mac_ver()[0].split('.')[:2]) < (13, 0):
            raise ValueError('The complete macOS dependency stack requires macOS 13 or later')
    elif system == 'Linux':
        key = 'linux-' + ('aarch64' if machine == 'arm64' else machine) + '-cp312'
        libc, version = platform.libc_ver()
        if libc != 'glibc' or tuple(int(n) for n in version.split('.')[:2]) < (2, 28):
            raise ValueError('The complete Linux dependency stack requires glibc 2.28 or later; musl is not supplied')
    else:
        raise ValueError('Unsupported operating system: ' + system)
    return key


def command(argv, log, timeout):
    event('RUN', program=Path(argv[0]).name, operation=Path(log).stem)
    started = time.monotonic()
    with Path(log).open('w', encoding='utf-8', newline='\n') as output:
        try:
            environment = {k: v for k, v in os.environ.items() if k.upper() not in ('PYTHONHOME', 'PYTHONPATH')}
            environment.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
                               PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1')
            done = subprocess.run([str(v) for v in argv], stdout=output, stderr=subprocess.STDOUT,
                                  timeout=timeout, env=environment)
        except subprocess.TimeoutExpired as error:
            raise ValueError('Timeout; preserve log: ' + str(log)) from error
    if done.returncode:
        raise ValueError('Operation failed; log ' + str(log) + ': ' +
                         Path(log).read_text(encoding='utf-8', errors='replace')[-1800:])
    event('DONE', operation=Path(log).stem, seconds=round(time.monotonic() - started, 2))


def check_zip(archive):
    seen = set()
    for entry in archive.infolist():
        name = entry.filename.rstrip('/') if entry.is_dir() else entry.filename
        portable(name)
        key = unicodedata.normalize('NFC', name).casefold()
        if key in seen or stat.S_ISLNK(entry.external_attr >> 16):
            raise ValueError('Duplicate or symlinked ZIP entry: ' + name)
        seen.add(key)


def owned(root, identity):
    marker = root / 'Install-intent.json'
    if root.exists():
        if not marker.is_file() or read_json(marker) != identity:
            raise ValueError('Preserve a directory without this exact install ownership: ' + str(root))
    else:
        root.mkdir(parents=True)
        write_json(marker, identity)
    return root


def acquire_lock(path, identity):
    handle = path.open('a+b')
    if path.stat().st_size == 0:
        handle.write(b' ')
        handle.flush()
    handle.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        handle.close()
        raise ValueError('Another installer is still running for this bundle/platform') from error
    handle.seek(0)
    raw = handle.read().strip()
    if raw:
        try:
            old = json.loads(raw)
        except Exception:
            handle.close()
            raise
        if old.get('bundle_id') != identity['bundle_id'] or old.get('environment') != identity['environment']:
            handle.close()
            raise ValueError('Preserve a foreign installation lock record')
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps({**identity, 'pid': os.getpid()}).encode())
    handle.flush()
    return handle


def prepare_engine(root, project, manifest, key, state, force_bundled):
    record = manifest['engines'][key]
    if not force_bundled and sys.version_info[:2] == (3, 12) and sys.maxsize > 2 ** 32:
        executable = Path(sys.executable).resolve()
        event('ENGINE', mode='existing-compatible-interpreter')
        return executable, {'mode': 'existing-compatible-interpreter', 'path': str(executable), 'sha256': sha(executable)}
    archive_path = within(root, record['path'])
    if not same_bytes(archive_path, record):
        raise ValueError('Bundled interpreter archive hash mismatch')
    inventory = read_json(within(root, record['inventory']))
    if inventory['archive_sha256'] != record['sha256'] or inventory['environment'] != key:
        raise ValueError('Interpreter inventory mismatch')
    base = within(project, '.lotraAI-build/toolchain/python-' + record['version'] + '-' + key + '-' + record['sha256'][:12])
    owned(base, {'archive_sha256': record['sha256'], 'environment': key})
    if key.startswith('linux'):
        probe_name = 'case-check-' + uuid.uuid4().hex + '-a'
        probe = base / probe_name
        with probe.open('xb') as case_check:
            case_check.write(b'filesystem-case-check')
        try:
            if probe.with_name(probe_name.upper()).exists():
                raise ValueError('The Linux interpreter requires a case-sensitive filesystem. Choose a Linux project directory or an explicitly case-sensitive WSL directory; existing resources were preserved.')
        finally:
            probe.unlink()
    all_files = inventory['files']
    event('ENGINE', mode='bundled', files=len(all_files))
    def put(name, source_factory):
        entry = all_files[name]
        destination = within(base, name)
        if destination.exists():
            if not same_bytes(destination, entry):
                raise ValueError('Preserve a changed interpreter file: ' + str(destination))
            return
        source = source_factory()
        if source is None:
            raise ValueError('Missing interpreter bytes: ' + name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source, destination.open('xb') as target:
            shutil.copyfileobj(source, target, 1048576)
        if os.name != 'nt':
            destination.chmod(entry['mode'] & 0o777)
        if not same_bytes(destination, entry):
            raise ValueError('Interpreter extraction digest mismatch')
    with (zipfile.ZipFile(archive_path) if archive_path.suffix == '.zip' else tarfile.open(archive_path, 'r|gz')) as archive:
        is_zip = isinstance(archive, zipfile.ZipFile)
        if is_zip:
            check_zip(archive)
            if {e.filename for e in archive.infolist() if not e.is_dir()} != set(all_files):
                raise ValueError('Interpreter ZIP differs from its inventory')
            for name in all_files:
                put(name, lambda name=name: archive.open(name))
        else:
            seen, links = set(), {}
            for member in archive:
                portable(member.name)
                if member.isdir():
                    continue
                if member.name in seen or member.name not in all_files:
                    raise ValueError('Unexpected or duplicate interpreter TAR entry')
                seen.add(member.name)
                if member.isfile():
                    if 'link_target' in all_files[member.name]:
                        raise ValueError('Interpreter TAR member type changed')
                    put(member.name, lambda member=member: archive.extractfile(member))
                elif member.issym() or member.islnk():
                    if '\\' in member.linkname or member.linkname.startswith('/'):
                        raise ValueError('Unsafe interpreter link')
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(member.name), member.linkname)
                                               if member.issym() else member.linkname)
                    portable(target)
                    if not target.startswith('python/'):
                        raise ValueError('Interpreter link escaped its root')
                    links[member.name] = target
                else:
                    raise ValueError('Unsupported interpreter TAR member')
            if seen != set(all_files):
                raise ValueError('Interpreter TAR differs from its inventory')
            for name in links:
                target, chain = name, set()
                while target in links:
                    if target in chain:
                        raise ValueError('Interpreter link cycle')
                    chain.add(target)
                    target = links[target]
                if target not in seen or all_files[name].get('link_target') != target:
                    raise ValueError('Interpreter link inventory differs')
                put(name, lambda target=target: within(base, target).open('rb'))
    write_json(base / 'Engine-complete.json', {'archive_sha256': record['sha256'], 'environment': key,
                                             'verified_files': len(all_files)})
    executable = within(base, record['executable'])
    if not same_bytes(executable, all_files[record['executable']]):
        raise ValueError('Prepared interpreter changed')
    return executable, {'mode': 'bundled', 'path': str(executable), 'sha256': sha(executable),
                        'archive_sha256': record['sha256'], 'files': len(all_files)}


def prepare_skill(root, project, manifest, state_dir, state):
    from installer_publication import stage_skill
    return stage_skill(root, project, manifest, state_dir, state)


def prepare_companion(root, project, manifest, key, state):
    selected=manifest.get('runtime_platforms',{}).get(key)
    record = selected if selected and (root/selected['path']).is_file() else manifest['payloads']['runtime']
    archive_path = within(root, record['path'])
    event('RUNTIME', status='verifying-original-payload', bytes=record['bytes'])
    if not same_bytes(archive_path, record):
        raise ValueError('Runtime ZIP changed')
    destination = within(project, '.lotraAI-build/toolchain/companion-' + record['version'] + '-' + key + '-' + record['sha256'][:12])
    owned(destination, {'runtime_sha256': record['sha256'], 'environment': key})
    with zipfile.ZipFile(archive_path) as archive:
        check_zip(archive)
        raw = archive.read('Manifest.json')
        original = json.loads(raw)
        if hashlib.sha256(raw).hexdigest() != record['manifest_sha256']:
            raise ValueError('Runtime source manifest mismatch')
        if original.get('schema') != 'lotra-runtime-companion-2' or original.get('version') != record['version']:
            raise ValueError('Runtime identity mismatch')
        if {e.filename for e in archive.infolist() if not e.is_dir()} != set(original['files']) | {'Manifest.json'}:
            raise ValueError('Runtime ZIP inventory mismatch')
        environment = original['environments'][key]
        selected = {name: copy.deepcopy(ref) for name, ref in original['files'].items()
                    if not name.startswith('wheels/') or name.startswith(environment['wheels'] + '/')}
        derived = copy.deepcopy(original)
        derived['files'], derived['environments'] = selected, {key: environment}
        derived['distribution_provenance'] = {'parent_archive_sha256': record['sha256'],
                                              'parent_manifest_sha256': record['manifest_sha256'],
                                              'selected_environment': key,
                                              'derivation': 'exact platform and all common models/licences/probe'}
        for name, ref in selected.items():
            path = within(destination, name)
            fact = {'bytes': ref.get('bytes', ref.get('size', archive.getinfo(name).file_size)), 'sha256': ref['sha256']}
            if path.exists():
                if not same_bytes(path, fact):
                    raise ValueError('Preserve a changed companion resource: ' + str(path))
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, path.open('xb') as output:
                shutil.copyfileobj(source, output, 1048576)
            if not same_bytes(path, fact):
                raise ValueError('Companion extraction mismatch')
        expected = json.dumps(derived, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
        path = destination / 'Manifest.json'
        if path.exists() and path.read_text(encoding='utf-8') != expected:
            raise ValueError('Preserve a different derived companion manifest')
        if not path.exists():
            path.write_text(expected, encoding='utf-8', newline='\n')
    event('RUNTIME', status='platform-prepared', environment=key, files=len(selected), unused_platforms_extracted=False)
    return destination


def register(project, skill, manifest, harness, result):
    if harness == 'auto':
        harness = 'claude' if os.environ.get('CLAUDECODE') else 'codex' if os.environ.get('CODEX_THREAD_ID') or os.environ.get('CODEX_HOME') else 'generic'
    active = within(project, '.lotraAI-build/Active-skill.json')
    try:
        selected_entry = '../' + skill.relative_to(project).as_posix() + '/SKILL.md'
    except ValueError:
        selected_entry = str(readable_windows_path(skill / 'SKILL.md'))
    new = {'name': 'lotra-image2slide-skill', 'version': VERSION,
           'bundle_id':result['bundle_id'],'design_revision':8,'workflow_version':manifest.get('workflow_version','1.35.2'),
           'skill': selected_entry,
           'package_sha256': manifest['payloads']['skill']['sha256'], 'global_skills': 'preserved'}
    if active.exists() and read_json(active) != new:
        old = read_json(active)
        if old.get('name') != new['name'] or not (old.get('skill', '').startswith('../.agents/skills/lotra-image2slide-skill') or old.get('skill') == selected_entry):
            raise ValueError('Preserve an unrelated active skill descriptor')
        backup = active.with_name('Active-skill.before-bundle-' + result['bundle_id'][:12] + '.json')
        if not backup.exists():
            backup.write_bytes(active.read_bytes())
    begin, end = '<!-- lotraAI-bundle-entry:start -->', '<!-- lotraAI-bundle-entry:end -->'
    block = begin + '\nUse ' + selected_entry.removeprefix('../') + ' for lotraAI image-to-slide work. Read .lotraAI-build/Active-skill.json for the selected entry and .lotraAI-build/Bundle-install.json for actual capability facts. Keep the current model/reasoning and use the prepared project launcher. Preserve existing project instructions and global skills.\n' + end
    agent_file = within(project, 'AGENTS.md')
    previous_bytes = agent_file.read_bytes() if agent_file.exists() else b''
    previous = re.sub(r'\.agents/skills/lotra-image2slide-skill-v[0-9.]+', '.agents/skills/lotra-image2slide-skill', previous_bytes.decode('utf-8'))
    if begin in previous or end in previous:
        if previous.count(begin) != 1 or previous.count(end) != 1 or previous.index(begin) >= previous.index(end):
            raise ValueError('Preserve ambiguous managed entry blocks')
        replacement = re.sub(re.escape(begin) + r'.*?' + re.escape(end), lambda unused: block, previous, flags=re.S)
    else:
        replacement = previous + ('\n\n' if previous and not previous.endswith('\n\n') else '') + block + '\n'
    policy_begin,policy_end='<!-- lotraAI-release-policy:start -->','<!-- lotraAI-release-policy:end -->'
    policy_block=policy_begin+'\nSelected lotraAI release is '+VERSION+'. Use the selected SKILL.md. This installation patch retains workflow_version 1.35.2, references/workflow-v1352.md and design_revision 8. Preserve old bound tasks, source files, private knowledge/fonts/tasks, current model/reasoning and global skills. No Setup skill. Use Bundle-install.json for actual host capabilities; publication is not artwork acceptance.\n'+policy_end
    if policy_begin in replacement or policy_end in replacement:
        if replacement.count(policy_begin)!=1 or replacement.count(policy_end)!=1 or replacement.index(policy_begin)>=replacement.index(policy_end):raise ValueError('Preserve ambiguous release policy block')
        replacement=re.sub(re.escape(policy_begin)+r'.*?'+re.escape(policy_end),lambda unused:policy_block,replacement,flags=re.S)
    else:replacement+='\n'+policy_block+'\n'
    from installer_publication import discoverable_bundle
    if harness == 'claude' and not discoverable_bundle(skill):
        folder = within(project, '.claude/skills/lotra-image2slide-skill')
        owner = folder / 'lotraAI-adapter.json'
        if folder.exists() and (not owner.is_file() or read_json(owner).get('owner') != 'lotraAI-bundle'):
            raise ValueError('Preserve an existing unowned Claude skill')
        entry = folder / 'SKILL.md'
        adapter_bytes = ('---\nname: lotra-image2slide-skill\ndescription: Reconstruct scientific reference images as faithful native editable PowerPoint in the current project.\n---\n\nRead the project .lotraAI-build/Active-skill.json and its selected SKILL.md. Use the prepared project runtime and actual capability report. Keep the current model/reasoning; no extra API key. All source/native-child, Office Math, font, fidelity, relationship and final acceptance requirements in that entry apply.\n').encode('utf-8')
        if entry.exists():
            prior = read_json(owner)
            expected = prior.get('entry_sha256')
            if (expected and sha(entry) != expected) or (not expected and entry.read_bytes() != adapter_bytes):
                raise ValueError('Preserve a user-modified Claude skill adapter')
        folder.mkdir(parents=True, exist_ok=True)
        if not entry.exists() or entry.read_bytes() != adapter_bytes:
            entry.write_bytes(adapter_bytes)
        write_json(owner, {'owner': 'lotraAI-bundle', 'bundle_id': result['bundle_id'],
                           'entry_sha256': hashlib.sha256(adapter_bytes).hexdigest()})
    if replacement != previous:
        if agent_file.exists():
            backup = within(project, '.lotraAI-build/bundle-install/' + result['bundle_id'][:16] + '-' + result['environment'] + '/AGENTS.before-registration.md')
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                backup.write_bytes(previous_bytes)
        agent_file.write_bytes(replacement.encode('utf-8'))
    write_json(active, new)
    result.update(harness=harness, skill_entry=str(readable_windows_path(skill / 'SKILL.md')),
                  discovery='project .agents/skills' if harness == 'codex' else 'project .claude/skills adapter' if harness == 'claude' else 'explicit selected SKILL.md and project AGENTS.md')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--harness', choices=('auto', 'codex', 'claude', 'generic'), default='auto')
    p.add_argument('--bundle-root', type=Path, default=DEFAULT_ROOT)
    p.add_argument('--bundled-engine', action='store_true')
    p.add_argument('--reuse-companion', type=Path)
    p.add_argument('--skip-render-probe', action='store_true', help='Explicitly report render as unverified')
    args = p.parse_args()
    root, requested_project = args.bundle_root.resolve(), args.project.resolve()
    if (root / 'Differential-manifest.json').is_file():
        from differential import install as differential_install
        differential_install(requested_project, read_json(root / 'Differential-manifest.json'), root / 'installer', args.harness)
        return 0
    if not requested_project.is_dir() or requested_project == Path.home().resolve() or requested_project == Path(requested_project.anchor):
        raise ValueError('Choose an existing project directory, not a user home or drive root')
    project = extended_windows_path(requested_project)
    manifest_path = root / 'Bundle-manifest.json'
    manifest = read_json(manifest_path)
    if manifest.get('schema') != SCHEMA or manifest.get('version') != VERSION:
        raise ValueError('Unsupported product bundle')
    bundle_id, key = sha(manifest_path), platform_key()
    if key not in manifest['engines']:
        raise ValueError('This platform is not supplied: ' + key)
    for name, record in manifest['files'].items():
        if name.startswith(('payload/', 'engines/','renderers/')) and name != manifest['engines'][key]['inventory']:
            continue
        if not same_bytes(within(root, name), record):
            raise ValueError('Product entry/resource changed: ' + name)
    state_dir = owned(within(project, '.lotraAI-build/bundle-install/' + bundle_id[:16] + '-' + key),
                      {'bundle_id': bundle_id, 'environment': key, 'version': VERSION})
    state_path = state_dir / 'Install-state.json'
    global EVENT_LOG
    EVENT_LOG=state_dir/'Events.jsonl'
    identity = {'bundle_id': bundle_id, 'environment': key, 'version': VERSION}
    state = read_json(state_path) if state_path.exists() else dict(identity)
    if any(state.get(k) != v for k, v in identity.items()):
        raise ValueError('Preserve a foreign install state')
    lock_handle = acquire_lock(state_dir / 'Running.lock', identity)
    result = {'schema': 'lotra-product-install-result-1', 'version': VERSION, 'bundle_id': bundle_id,
              'environment': key, 'project': str(requested_project), 'global_skills': 'preserved',
              'acquisition':'local hash-bound resources; online coordinator may have downloaded missing assets', 'global_packages_changed': False, 'whole_drawing_acceptance': False}
    try:
        event('START', version=VERSION, environment=key, project=str(project))
        engine, result['engine'] = prepare_engine(root, project, manifest, key, state, args.bundled_engine)
        skill = prepare_skill(root, project, manifest, state_dir, state)
        script_skill = readable_windows_path(skill)
        if args.reuse_companion:
            from online import companion as compatible_companion
            companion=compatible_companion(readable_windows_path(project),manifest,key)
            if companion is None or companion.resolve()!=args.reuse_companion.resolve():raise ValueError('Prepared companion compatibility changed')
        else:companion = prepare_companion(root, project, manifest, key, state)
        readiness = state_dir / 'Runtime-readiness.json'
        command([engine, '-I', '-X', 'utf8', '-B', root / 'installer/bootstrap.py',
                 '--skill', script_skill, '--project', project, '--companion', companion,
                 '--out', readiness], state_dir / 'runtime-bootstrap.log', 1440)
        result['runtime'] = read_json(readiness)
        result['core_ready'] = result['runtime'].get('status') == 'OFFLINE_RUNTIME_READY'
        if not result['core_ready']:
            raise ValueError('Runtime bootstrap did not confirm actual core readiness')
        from presentation_install import qualify,qualify_fallback,readiness as presentation_readiness
        math=qualify(Path(readable_windows_path(project)),Path(script_skill),key,Path(readable_windows_path(state_dir)))
        if math is None:
            from renderer_install import install_renderer
            math=install_renderer(root,project,manifest,key)
        result['math_renderer']=math
        if math.get('status') not in ('INSTALLED_NOT_TESTED','LOCAL_NATIVE_READY'):
            raise ValueError('Required Math runtime is not supplied for this platform; skill has not been published')
        # Import readiness is distinct from opening/editing/rendering a document.
        from renderer_install import verify_backend
        math_backend=math['backend'] if math.get('status')=='LOCAL_NATIVE_READY' else verify_backend(
            Path(readable_windows_path(project)),Path(script_skill),Path(readable_windows_path(state_dir)),key)
        result['math_renderer']['backend']=math_backend
        if math.get('status')!='LOCAL_NATIVE_READY':
            math['presentation_probe']=qualify_fallback(Path(readable_windows_path(project)),Path(script_skill),key,Path(readable_windows_path(state_dir)))
        result['math_backend_ready']=True
        result['math_execution_mode']=math_backend['execution_mode']
        result['math_import_ready']=None if math.get('status')=='LOCAL_NATIVE_READY' else True
        from installer_publication import publish_skill
        skill = publish_skill(root, project, manifest, state_dir, state)
        script_skill = readable_windows_path(skill)
        descriptor = read_json(project / '.lotraAI-build/toolchain' / ('core-runtime-' + key + '.json'))
        runtime_engine = within(project, descriptor['engine']['path'])
        result['capabilities'] = presentation_readiness(math)
        result.update(status='INSTALLED_READY_SINGLE_SKILL', runtime_python=str(runtime_engine),
                      command_prefix=[str(runtime_engine), '-I', '-X', 'utf8', '-B', str(script_skill / 'scripts/run_lotra.py'), '--project', str(project)],
                      render_ready=result['capabilities']['render_ready'], native_edit_ready=result['capabilities']['native_edit_ready'])
        result['command_text'] = subprocess.list2cmdline(result['command_prefix']) if os.name == 'nt' else shlex.join(result['command_prefix'])
        result['installed_skill_count'] = 1
        result['setup_skill_registered'] = False
        result['runtime_prepared_at_install'] = True
        result['next_action'] = 'Use lotra-image2slide-skill directly. Python, OCR models and Math runtime are installed; actual document rendering remains a task check.'
        register(project, skill, manifest, args.harness, result)
        state['status'] = 'COMPLETE'
        write_json(state_path, state)
        write_json(project / '.lotraAI-build/Bundle-install.json', result)
        write_json(state_dir / 'Result.json', result)
        publication_journal=state_dir/'Publication-rollback.json'
        if publication_journal.exists():
            completed=read_json(publication_journal);completed['status']='COMPLETE';write_json(publication_journal,completed)
        print(json.dumps({'status':'INSTALLED_READY_SINGLE_SKILL','version':VERSION,'core_ready':True,'math_import_ready':result['math_import_ready'],
            'render_status':result['capabilities']['render_status'],'skill_entry':'.agents/skills/lotra-image2slide-skill/SKILL.md',
            'report':'.lotraAI-build/Bundle-install.json','global_skills':'preserved'},ensure_ascii=True))
        return 0
    except Exception as error:
        result.update(status='INSTALL_FAILED', reason=str(error), next_action='Resolve this exact diagnostic, then resume the same bundle. Preserve foreign or changed resources.')
        write_json(state_dir / 'Failure.json', result)
        from installer_publication import rollback_publication
        rollback_publication(project,state_dir)
        print(json.dumps({'status':'INSTALL_FAILED','phase':'INSTALL','reason':str(error)[:320],
            'report':str((state_dir/'Failure.json').relative_to(project))},ensure_ascii=True))
        return 1
    finally:
        lock_handle.close()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status':'INSTALL_FAILED','reason':str(error)[:320]},ensure_ascii=True))
        raise SystemExit(1)
