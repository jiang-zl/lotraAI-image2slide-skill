"""Fixed in-application Math worker; loaded by LibreOffice's Python provider."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import traceback
import uno


def digest(file):
    h = hashlib.sha256()
    with Path(file).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run(*unused):
    context = XSCRIPTCONTEXT.getComponentContext()
    substitution=context.ServiceManager.createInstanceWithContext('com.sun.star.util.PathSubstitution',context)
    profile=Path(uno.fileUrlToSystemPath(substitution.substituteVariables('$(user)',True))).resolve().parent
    request_file = profile / 'job.json'
    if request_file.stat().st_size > 65536:
        raise ValueError('Math job exceeds byte limit')
    request = json.loads(request_file.read_bytes())
    result = {'schema': 'lotra-editor-job-result-1', 'job_id': request.get('job_id'),
              'operation': request.get('operation'), 'request_sha256': digest(request_file), 'status': 'FAILED'}
    desktop = context.ServiceManager.createInstanceWithContext('com.sun.star.frame.Desktop', context)
    try:
        if request.get('schema') != 'lotra-editor-job-1' or request.get('job_id') != profile.name:
            raise ValueError('Math job identity differs from its private profile')
        operation = request.get('operation')
        if operation not in ('probe', 'export'):
            raise ValueError('Unknown hosted Math operation')
        directory = Path(request['directory']).resolve(strict=True)
        if not directory.is_relative_to(profile.parent.parent):
            raise ValueError('Hosted Math job escaped its private workspace')
        client_file = profile/'user/Scripts/python/lotra_client.py'
        if digest(client_file) != request['client_sha256']:
            raise ValueError('Hosted Math client differs from the prepared code')
        expected = {'editor-input.pptx', 'editor-plan.json'} if operation == 'export' else set()
        if set(request.get('inputs', {})) != expected:
            raise ValueError('Unexpected hosted Math inputs')
        for name, sha in request.get('inputs', {}).items():
            file = directory / name
            if file.is_symlink() or digest(file) != sha:
                raise ValueError('Hosted Math input identity changed')
        outputs=('Final.pdf','math-editor.json') if operation=='export' else ('math-probe.json',)
        if any((directory/name).exists() or (directory/name).is_symlink() for name in outputs):
            raise ValueError('Preserve existing Math job output')
        spec = importlib.util.spec_from_file_location('lotra_fixed_math_client', client_file)
        client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(client)
        client.main(None, str(directory), context=context, probe=operation == 'probe', terminate=False)
        result['status'] = 'PASS'
    except Exception as error:
        result.update(reason=str(error), error_type=type(error).__name__, traceback=traceback.format_exc()[-8000:])
    finally:
        temporary = profile / 'result.json.part'
        temporary.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
        os.replace(temporary, profile / 'result.json')
        desktop.terminate()


g_exportedScripts = (run,)
