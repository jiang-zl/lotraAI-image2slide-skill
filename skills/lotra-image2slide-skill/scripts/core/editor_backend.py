"""Bounded native Math jobs, shared by installation and document export.

Only the standard library is imported here: the installer loads this module
before preparing the project's numeric/OCR environment. On macOS the signed
LibreOffice application hosts Python; its constrained interpreter is never
spawned by the project process.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import time
import uuid

VERSION = 'native-math-backend-1.35.3'
MODES = ('subprocess_uno', 'libreoffice_hosted')
FILES = ('editor_backend.py', 'uno_editor_client.py', 'uno_host_worker.py')


def digest(file):
    h = hashlib.sha256()
    with Path(file).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(file, value):
    file = Path(file)
    temporary = file.with_name(file.name + '.part')
    with temporary.open('xb') as stream:
        stream.write((json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8'))
    os.replace(temporary, file)


def execution_mode(config):
    mode = config.get('execution_mode', 'libreoffice_hosted' if platform.system() == 'Darwin' else 'subprocess_uno')
    if mode not in MODES:
        raise ValueError('Unsupported declared Math execution mode')
    if platform.system() == 'Darwin' and mode != 'libreoffice_hosted':
        raise ValueError('macOS Math requires the LibreOffice-hosted execution mode')
    return mode


def identity(config, client_file=None):
    client_file = Path(client_file or Path(__file__).with_name('uno_editor_client.py')).resolve()
    mode = execution_mode(config)
    value = {'policy': VERSION, 'execution_mode': mode,
             'host': {'system': platform.system(), 'machine': platform.machine(), 'release': platform.release()},
             'executable_sha256': digest(config['executable']),
             'code': {name: digest(client_file.with_name(name)) for name in FILES}}
    if mode == 'subprocess_uno':
        value['uno_python_sha256'] = digest(config['uno_python'])
    # These native libraries are present in different layouts on each platform.
    executable = Path(config['executable']).resolve()
    locations = (executable.parent, executable.parent.parent / 'Frameworks',
                 executable.parent.parent / 'Resources')
    value['libraries'] = {str(file): digest(file) for folder in locations
                          for name in ('libpyuno.so', 'pyuno.so', 'pyuno.pyd', 'libmergedlo.dylib',
                                       'libsmlo.dylib', 'mergedlo.dll', 'smlo.dll', 'libmergedlo.so', 'libsmlo.so')
                          if (file := folder / name).is_file()}
    value['sha256'] = hashlib.sha256(json.dumps(value, sort_keys=True).encode('utf-8')).hexdigest()
    return value


class BackendError(RuntimeError):
    def __init__(self, reason, facts):
        super().__init__(reason)
        self.facts = facts


def _stop(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                       timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == 'nt':
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=5)


_BASIC = '''<?xml version="1.0" encoding="UTF-8"?>
<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Main" script:language="StarBasic"><![CDATA[
Sub Run
    On Error GoTo Failed
    Dim factory As Object, provider As Object, entry As Object
    factory = CreateUnoService("com.sun.star.script.provider.MasterScriptProviderFactory")
    provider = factory.createScriptProvider("")
    entry = provider.getScript("vnd.sun.star.script:lotra_worker.py$run?language=Python&location=user")
    entry.invoke(Array(), Array(), Array())
    Exit Sub
Failed:
    Dim userURL As String, handle As Integer
    userURL = CreateUnoService("com.sun.star.util.PathSubstitution").substituteVariables("$(user)", True)
    handle = FreeFile
    Open ConvertFromURL(userURL & "/lotra-basic-error.txt") For Output As #handle
    Print #handle, "Basic bridge error " & Err & ": " & Error$
    Close #handle
    StarDesktop.terminate()
End Sub
]]></script:module>
'''


def _hosted_profile(profile, request, client_file):
    scripts = profile / 'user/Scripts/python'
    library = profile / 'user/basic/LotraAI'
    scripts.mkdir(parents=True,exist_ok=True)
    library.mkdir(parents=True,exist_ok=True)
    (scripts / 'lotra_worker.py').write_bytes(client_file.with_name('uno_host_worker.py').read_bytes())
    (scripts / 'lotra_client.py').write_bytes(client_file.read_bytes())
    basic = profile / 'user/basic'
    (basic / 'script.xlc').write_text('''<?xml version="1.0" encoding="UTF-8"?>
<library:libraries xmlns:library="http://openoffice.org/2000/library" xmlns:xlink="http://www.w3.org/1999/xlink"><library:library library:name="Standard" xlink:href="$(USER)/basic/Standard/script.xlb/" xlink:type="simple" library:link="false"/><library:library library:name="LotraAI" xlink:href="$(USER)/basic/LotraAI/script.xlb/" xlink:type="simple" library:link="false"/></library:libraries>
''', encoding='utf-8')
    (library / 'script.xlb').write_text('''<?xml version="1.0" encoding="UTF-8"?>
<library:library xmlns:library="http://openoffice.org/2000/library" library:name="LotraAI" library:readonly="false" library:passwordprotected="false"><library:element library:name="Main"/></library:library>
''', encoding='utf-8')
    (library / 'Main.xba').write_text(_BASIC, encoding='utf-8')
    write_json(profile / 'job.json', request)


def run(config, directory, operation='export', timeout=120, client_file=None):
    if operation not in ('probe', 'export') or not 1 <= timeout <= 300:
        raise ValueError('Unknown or unbounded Math operation')
    directory = Path(directory).resolve(strict=True)
    client_file = Path(client_file or Path(__file__).with_name('uno_editor_client.py')).resolve(strict=True)
    before = identity(config, client_file)
    root = next((p for p in (directory, *directory.parents) if p.name == '.lotraAI-build'), directory.parent)
    profile = root / 'editor-profiles' / uuid.uuid4().hex
    profile.mkdir(parents=True, exist_ok=False)
    job = {'schema': 'lotra-editor-job-1', 'job_id': profile.name, 'operation': operation,
           'directory': str(directory), 'client_sha256': digest(client_file)}
    if operation == 'export':
        job['inputs'] = {name: digest(directory / name) for name in ('editor-input.pptx', 'editor-plan.json')}
    mode = before['execution_mode']
    connection = 'pipe,name=lotra' + uuid.uuid4().hex
    args = [str(config['executable']), '-env:UserInstallation=' + profile.as_uri(),
            '--headless', '--nologo', '--nodefault', '--norestore']
    if mode == 'libreoffice_hosted':
        args.append('macro:///LotraAI.Main.Run')
    else:
        args.append('--accept=' + connection + ';urp;')
    env = dict(os.environ)
    for name in ('URE_BOOTSTRAP', 'UNO_PATH', 'PYTHONHOME', 'PYTHONPATH',
                 'PYTHONEXECUTABLE', '__PYVENV_LAUNCHER__'):
        env.pop(name, None)
    if config.get('fontconfig'):
        env['FONTCONFIG_FILE'] = config['fontconfig']
    temporary=directory/'backend-temp'
    temporary.mkdir(exist_ok=False)
    for name in ('TEMP','TMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_RUNTIME_DIR'):
        env[name]=str(temporary)
    env.update(GSETTINGS_BACKEND='memory',SAL_USE_VCLPLUGIN='svp')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    facts = {'policy': VERSION, 'operation': operation, 'execution_mode': mode,
             'backend_identity': before['sha256'], 'profile': str(profile),
             'command': args, 'host': before['host'], 'temporary_directory':str(temporary), 'status': 'FAILED'}
    process = None
    deadline=time.monotonic()+timeout
    try:
        if mode=='libreoffice_hosted':
            # LibreOffice initializes a fresh profile from its template. Let
            # that finish before registering the fixed private library.
            with (directory/'editor-profile-init.log').open('wb') as init_log:
                init_args=args[:-1]+['--terminate_after_init']
                initial=subprocess.Popen(init_args,stdout=init_log,stderr=init_log,env=env,
                    creationflags=flags,start_new_session=os.name!='nt')
                try:
                    initial.wait(timeout=max(.1,deadline-time.monotonic()))
                    if initial.returncode:raise RuntimeError('Private Math profile initialization failed')
                finally:_stop(initial)
            _hosted_profile(profile,job,client_file)
        with (directory / 'editor-server.log').open('wb') as log:
            process = subprocess.Popen(args, stdout=log, stderr=log, env=env,
                                       creationflags=flags, start_new_session=os.name != 'nt')
            if mode == 'libreoffice_hosted':
                end = deadline
                reply = profile / 'result.json'
                while not reply.is_file():
                    basic_error = profile / 'user/lotra-basic-error.txt'
                    if basic_error.is_file():
                        raise RuntimeError(basic_error.read_text(encoding='utf-8', errors='replace')[-4000:])
                    if process.poll() is not None:
                        raise RuntimeError('LibreOffice exited before its hosted Math result')
                    if time.monotonic() >= end:
                        raise subprocess.TimeoutExpired(args, timeout)
                    time.sleep(.05)
                if reply.stat().st_size > 131072:
                    raise ValueError('Hosted Math result exceeds byte limit')
                result = json.loads(reply.read_bytes())
                expected = {'schema': 'lotra-editor-job-result-1', 'job_id': job['job_id'],
                            'operation': operation, 'request_sha256': digest(profile / 'job.json')}
                if any(result.get(k) != v for k, v in expected.items()):
                    raise ValueError('Hosted Math result does not match this request')
                if result.get('status') != 'PASS':
                    raise RuntimeError(result.get('reason', 'Hosted Math operation failed'))
            else:
                command = [str(config['uno_python']), '-B', str(client_file), connection, str(directory)]
                if operation == 'probe':
                    command.append('--probe')
                facts['client_command'] = command
                # Framework/embedded launchers can spawn descendants that keep
                # inherited PIPE handles open after their parent is killed.
                # File-backed logs and an owned process tree keep cancellation
                # finite even for those launchers.
                client_log=directory / 'editor-client.log'
                with client_log.open('wb') as stream:
                    client=subprocess.Popen(command,stdout=stream,stderr=stream,env=env,
                        creationflags=flags,start_new_session=os.name!='nt')
                    try:
                        client.wait(timeout=max(.1,deadline-time.monotonic()))
                    finally:
                        _stop(client)
                        facts['client_returncode'] = client.returncode
                if client.returncode:
                    raise RuntimeError('Native Math client failed: ' + client_log.read_text(encoding='utf-8', errors='replace')[-4000:])
            if operation == 'export' and not all((directory / name).is_file() for name in ('Final.pdf', 'math-editor.json')):
                raise RuntimeError('Native Math export did not produce its required artifacts')
            if operation == 'probe':
                proof = json.loads((directory / 'math-probe.json').read_bytes())
                if proof.get('status') != 'PASS' or proof.get('native_math_service') is not True:
                    raise ValueError('Math service readiness was not demonstrated')
            if any(digest(directory / name) != sha for name, sha in job.get('inputs', {}).items()):
                raise RuntimeError('Math backend modified its immutable input')
            if identity(config, client_file) != before:
                raise RuntimeError('Math backend changed during the operation')
            facts['status'] = 'PASS'
    except Exception as error:
        facts.update(reason=str(error), error_type=type(error).__name__,
                     timed_out=isinstance(error, subprocess.TimeoutExpired))
        if process is not None:
            facts['server_returncode'] = process.poll()
        raise BackendError('Math backend unavailable: ' + str(error), facts) from error
    finally:
        if process is not None:
            if facts['status']=='PASS':
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:pass
            _stop(process)
            facts['server_returncode'] = process.poll()
        write_json(directory / 'backend-result.json', facts)
    return facts
