"""Optional Windows/WSL API bridge; raw operations are never final PASS receipts."""

import platform
import shutil
import subprocess
import tempfile
import time
import json
import contextlib
import base64
from pathlib import Path
from .common import ROOT, digest, read_json, write_json, writer

def decode_native_output(value):
    if value is None:return ''
    if isinstance(value,str):return value
    try:return value.decode('utf-8')
    except UnicodeDecodeError:
        if platform.system()=='Windows':
            import ctypes
            codepage=ctypes.windll.kernel32.GetACP()
            return value.decode('cp'+str(codepage),errors='backslashreplace')
        return value.decode('utf-8',errors='backslashreplace')


@contextlib.contextmanager
def office_turn(wait_seconds=300):
    directory=Path(tempfile.gettempdir())/'sci-rebuild-office-session'
    deadline=time.monotonic()+wait_seconds
    while True:
        manager=writer(directory)
        try:manager.__enter__()
        except FileExistsError:
            if time.monotonic()>=deadline:raise TimeoutError('Office writer queue exceeded resource guard; no document was changed')
            time.sleep(.5)
            continue
        break
    try:
        if (directory/'needs-inspection.json').exists():raise RuntimeError('Prior Office timeout requires explicit session inspection')
        yield
    finally:manager.__exit__(None,None,None)


def probe(pptx, output, timeout=300, equation_editor=False, render_only=False, component_assets=False, preview_width=1440, task_plan=None, saved_components=False):
    if sum(bool(v) for v in (equation_editor,render_only,component_assets,task_plan,saved_components))>1:
        raise ValueError('Choose one Office operation mode per writer turn')
    pptx, output = Path(pptx).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    exe = shutil.which("powershell.exe") or shutil.which("powershell")
    if not exe:
        raise RuntimeError("BLOCKED: Windows PowerShell bridge unavailable; use host native-operation protocol on macOS")
    staged = bool(task_plan or render_only or saved_components)
    script = ROOT / "scripts" / ("run_office_job.ps1" if staged else "export_component_assets.ps1" if component_assets else "probe_equation_editor.ps1" if equation_editor else "probe_office.ps1")
    from .office_bridge import _host_path as native
    # Resolve resources locally first. The shared bridge converts a native
    # path exactly once and handles an output whose final component is new.
    output.parent.mkdir(parents=True, exist_ok=True)
    out_native = native(output)
    args = [exe,"-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",native(script),
            "-InputPptx",native(pptx),"-OutDir",out_native]
    if staged:
        if not 30<=timeout<=1800:raise ValueError('Staged Office operation timeout must be between 30 and 1800 seconds')
        args.extend(['-Kind','native' if task_plan else 'components' if saved_components else 'render','-TimeoutSeconds',str(timeout)])
    if render_only:args.extend(['-PreviewWidth',str(preview_width)])
    if task_plan:args.extend(['-PlanPath',native(Path(task_plan).resolve())])
    before = digest(pptx)
    started=time.monotonic()
    session_directory=Path(tempfile.gettempdir())/"sci-rebuild-office-session"
    with office_turn():
        if (session_directory/"needs-inspection.json").exists():
            raise RuntimeError("BLOCKED: prior Office timeout requires session inspection before another writer")
        try:
            # The helper bounds Office itself. Allow separately declared time for
            # byte-identical staging/copying across WSL; it is not quality time.
            result = subprocess.run(args,capture_output=True,timeout=timeout+(300 if staged else 0))
        except subprocess.TimeoutExpired as exc:
            write_json(session_directory/"needs-inspection.json",{"input":str(pptx),"output":str(output),"reason":"Office timeout; do not auto-clear or close other documents"})
            write_json(output.parent / (output.name + "-timeout.json"), {"status":"PAUSED_RESOURCE_LIMIT","timeout_seconds":timeout,
                       "reason":"Office process exceeded guard; inspect probe session before retrying; never close other documents"})
            raise TimeoutError("Office probe exceeded guard; session requires inspection") from exc
    if digest(pptx) != before:
        raise RuntimeError("Office bridge modified original input")
    stdout=decode_native_output(result.stdout);stderr=decode_native_output(result.stderr)
    write_json(output.parent / (output.name + "-process.json"), {"returncode":result.returncode,"stdout":stdout,"stderr":stderr,
                                                              "stdout_raw_base64":base64.b64encode(result.stdout or b'').decode('ascii'),"stderr_raw_base64":base64.b64encode(result.stderr or b'').decode('ascii'),
                                                              "input_sha256":before,"timeout_seconds":timeout,"staging_transport_allowance_seconds":300 if staged else 0,
                                                              "elapsed_seconds":time.monotonic()-started})
    if result.returncode:
        raise RuntimeError("BLOCKED: Office probe failed: " + stderr)
    if task_plan:
        from .native_task import complete_render
        complete_render(Path(task_plan),output)
    return read_json(output / ('probe.json' if saved_components else "assets.json" if component_assets else "render.json" if render_only else "operations.json"))


def inspect_environment(timeout=60):
    exe=shutil.which('powershell.exe') or shutil.which('powershell')
    if not exe:raise RuntimeError('PowerShell bridge unavailable; install/use Windows PowerPoint for native backend')
    script=ROOT/'scripts/office_environment.ps1'
    native=str(script) if platform.system()=='Windows' else subprocess.check_output(['wslpath','-w',str(script)],text=True).strip()
    try:
        with office_turn():
            result=subprocess.run([exe,'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',native],capture_output=True,timeout=timeout)
    except subprocess.TimeoutExpired as exc:raise TimeoutError('PowerPoint environment probe exceeded '+str(timeout)+' seconds; no capability PASS recorded') from exc
    if result.returncode:raise RuntimeError('PowerPoint environment probe failed: '+decode_native_output(result.stderr))
    return json.loads(decode_native_output(result.stdout).lstrip('\ufeff'))
