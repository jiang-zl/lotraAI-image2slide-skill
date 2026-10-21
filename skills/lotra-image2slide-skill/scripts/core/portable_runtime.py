"""Qualified local application first; bounded declared LibreOffice fallback.

Render keys bind the exact application, generator, fonts and saved input.
"""
from copy import deepcopy
import os
import json
from pathlib import Path
import platform
import shutil
import subprocess
import time
from .common import digest, identity, read_json, write_json, writer

VERSION = 'portable-runtime-1.31'


def capabilities(project, configuration=None,requested=None):
    from .editor_backend import execution_mode, identity as backend_identity
    project = Path(project).resolve()
    from .presentation_backend import select
    native=select(project,requested)
    if native.get('status')=='READY':
        return {**native,'project':str(project),'identity':identity(native),'executable_sha256':digest(native['executable'])}
    if native.get('backend') not in ('auto','LibreOffice'):
        return native
    config_path = project/'.lotraAI-build/Portable-renderer.json'
    config = configuration or (read_json(config_path) if config_path.is_file() else {})
    configured = config.get('platforms', {}).get(platform.system(), config)
    exe = configured.get('executable') or os.environ.get('LOTRAAI_SOFFICE')
    if exe and not Path(exe).is_absolute():
        exe = str(project/exe)
    if not exe:
        exe = shutil.which('soffice')
    if not exe or not Path(exe).is_file():
        return {'status': 'CAPABILITY_BLOCKED', 'policy': VERSION, 'backend': 'LibreOffice',
                'reason': 'Declared portable renderer missing', 'fallback_attempts': 0,
                'office_interactive_edit_verified': 'not_run'}
    uno_python=configured.get('uno_python') or str(Path(exe).parent/('python.exe' if os.name=='nt' else 'python'))
    if not Path(uno_python).is_absolute():uno_python=str(project/uno_python)
    mode=execution_mode(configured)
    if mode=='subprocess_uno' and not Path(uno_python).is_file():
        return {'status':'CAPABILITY_BLOCKED','backend':'LibreOffice','policy':VERSION,
                'reason':'Bundled native Math editor Python missing','fallback_attempts':0}
    try:
        version = subprocess.run([exe, '--version'], capture_output=True, text=True,
                                 timeout=15, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        return {'status': 'CAPABILITY_BLOCKED', 'policy': VERSION, 'backend': 'LibreOffice',
                'reason': str(error), 'fallback_attempts': 0}
    if 'LibreOffice' not in version:
        raise ValueError('Configured executable did not identify LibreOffice')
    result = {'status': 'READY', 'policy': VERSION, 'backend': 'LibreOffice',
              'executable': str(Path(exe).resolve()), 'executable_sha256': digest(exe),
              'version': version, 'platform': platform.system(),
              'fontconfig': configured.get('fontconfig'),
              'execution_mode':mode,'uno_python':str(Path(uno_python).resolve()),
              'office_interactive_edit_verified': 'not_run', 'fallback_attempts': 0}
    if Path(uno_python).is_file():result['uno_python_sha256']=digest(uno_python)
    result['backend_identity']=backend_identity(result)
    result['core_libraries']={str(p):digest(p) for name in
        ('soffice.bin','mergedlo.dll','smlo.dll','libmergedlo.so','libsmlo.so','libsmlo.dylib')
        if (p:=Path(exe).parent/name).is_file()}
    if result['fontconfig']:
        path = Path(result['fontconfig'])
        if not path.is_absolute(): path = project/path
        if not path.is_file(): raise ValueError('Configured font discovery file missing')
        result['fontconfig'] = str(path.resolve())
        result['fontconfig_sha256'] = digest(path)
    result['identity'] = identity(result)
    return result


def font_plan(scene, selections):
    """One explicit face per script/style; no appearance-fitting font search.

    A selection records source-class inference separately from the exact saved
    resource. Native embedding is limited to capable resources up front.
    """
    from .font_contract import requests, compile_scene, VERSION as FONT_VERSION
    from .font_resources import describe, matches, coverage
    # Public JSON scenes have value semantics. Detach shared Python dictionaries
    # too, so compiling one owner's script face cannot mutate another owner.
    value = json.loads(json.dumps(scene,ensure_ascii=False,allow_nan=False))
    bindings, faces = {}, {}
    for request in requests(value):
        family = request['proposed_family']
        selection = selections.get(family)
        if not selection:
            raise ValueError('FONT_SELECTION_REQUIRED: '+family)
        key = (str(Path(selection['path']).resolve()), selection.get('face_index', 0))
        if key not in faces:
            faces[key] = describe(*key)
            faces[key]['id'] = identity([faces[key]['file_sha256'], key[1]])
        face = faces[key]
        if not matches(face, family):
            raise ValueError('Font family and actual resource differ: '+family)
        if face['outline'] != 'truetype' or face['variable'] or not face['editable_embedding']:
            raise ValueError('CAPABILITY_BLOCKED: chosen font cannot use the portable editable embedding route')
        coverage_result = coverage(face, request['characters'])
        if coverage_result:
            raise ValueError('CAPABILITY_BLOCKED: selected font lacks required characters')
        if selection.get('class') not in ('song', 'serif', 'sans', 'hei', 'kai', 'fangsong', 'mono', 'math', 'other'):
            raise ValueError('Explicit font class required')
        request_value = {k: request[k] for k in ('owner','location','role','characters','literal_hash','bold','italic','proposed_family')}
        bindings[request['id']] = {'request': request, 'request_hash': identity(request_value),
            'family': face['family'], 'resource': face, 'origin': 'source_contract',
            'status': selection.get('source_identity', 'approximate'),
            'font_class': selection['class'],
            'synthetic_style': (request['bold'] and face['weight'] < 600) or request['italic'] != face['italic'],
            'evidence': {'source_hash': value['source']['sha256'], 'roi': request['roi'],
                         'description': selection.get('description', 'Frozen source-class representative')}}
    value['font_plan'] = {'version': FONT_VERSION, 'bindings': bindings}
    return compile_scene(value)


def render_key(pptx, caps, scene, width):
    fonts = sorted({b['resource']['file_sha256'] for b in scene.get('font_plan', {}).get('bindings', {}).values()})
    for b in scene.get('font_plan', {}).get('bindings', {}).values():
        if digest(b['resource']['path']) != b['resource']['file_sha256']:
            raise ValueError('Font resource changed after freezing')
    if digest(caps['executable']) != caps['executable_sha256']:
        raise ValueError('Renderer changed after preflight')
    if caps.get('uno_python_sha256') and digest(caps['uno_python']) != caps['uno_python_sha256']:
        raise ValueError('Math editor client runtime changed after preflight')
    if caps.get('backend') in ('PowerPoint','WPS'):
        from .presentation_backend import _code
        return identity({'pptx':digest(pptx),'application':caps,'code':_code(),'fonts':fonts,
            'width':width,'canvas':scene['canvas'],'policy':VERSION})
    from .editor_backend import identity as backend_identity
    if caps.get('backend_identity') != backend_identity(caps):
        raise ValueError('Math execution mode, worker or native resources changed after preflight')
    if any(digest(path)!=sha for path,sha in caps.get('core_libraries',{}).items()):
        raise ValueError('Declared editor library changed after preflight')
    return identity({'pptx': digest(pptx), 'renderer': caps['identity'], 'fonts': fonts,
                     'width': width, 'canvas': scene['canvas'], 'policy': VERSION,
                     'renderer_code': [digest(Path(__file__).with_name(f)) for f in
                                       ('render.py','portable_editor.py','math_editor.py','uno_editor_client.py',
                                        'editor_backend.py','uno_host_worker.py')]})


def shared_render(task, pptx, caps, scene, width=1440, independent=False):
    if caps.get('status') != 'READY':
        return {'status': 'CAPABILITY_BLOCKED', 'reason': caps.get('reason'), 'fallback_attempts': 0}
    from .render import verify_alternative_render
    from .portable_editor import render
    key = render_key(pptx, caps, scene, width)
    root = Path(task)/'render-cache'/key
    root.mkdir(parents=True, exist_ok=True)
    # All consumers serialize the same content key. Successful artifacts are
    # recovered even if a caller died before writing the summary receipt.
    with writer(root):
        ledger_file = root/'attempts.json'
        ledger = read_json(ledger_file) if ledger_file.is_file() else {'attempts': [], 'success': None}
        for attempt in ledger['attempts']:
            receipt_file = root/attempt['directory']/'render.json'
            if receipt_file.is_file():
                receipt = read_json(receipt_file)
                directory = receipt_file.parent
                page = directory/'Final_preview.png'
                if receipt['pptx_hash'] != digest(pptx) or not page.is_file() or digest(page) != receipt['preview_hash']:
                    raise ValueError('Saved render cache was modified')
                if independent:
                    released=directory/'pdf-release.json'
                    if released.is_file():
                        proof=read_json(released)
                        if proof.get('receipt_sha256')!=digest(receipt_file) or proof.get('preview_sha256')!=digest(page) or proof.get('status')!='VALIDATED_AND_RELEASED':
                            raise ValueError('Released render evidence changed')
                    else:verify_alternative_render(pptx, receipt_file)
                return {'status': 'PASS', 'key': key, 'cache_hit': True,
                        'receipt': str(receipt_file), 'preview': str(page),
                        'portable_render_verified': True, 'office_interactive_edit_verified': 'not_run'}
        if len(ledger['attempts']) >= 2:
            return {'status': 'CAPABILITY_BLOCKED', 'key': key, 'reason': 'Finite render attempts exhausted', 'fallback_attempts': 0}
        # Only a classified transient failure may receive one retry. A reserved
        # interrupted attempt remains a decision instead of an invisible retry.
        if ledger['attempts'] and ledger['attempts'][-1]['status'] != 'TRANSIENT_FAILURE':
            return {'status': 'NEEDS_DECISION', 'reason': 'Prior render outcome unresolved', 'key': key}
        attempt = {'directory': 'attempt-'+str(len(ledger['attempts'])+1), 'status': 'RESERVED'}
        ledger['attempts'].append(attempt)
        write_json(ledger_file, ledger)
        begin = time.monotonic()
        try:
            if caps.get('backend') in ('PowerPoint','WPS'):
                from .tool_router import capabilities as routed_capabilities,render_saved
                routed=routed_capabilities(project=caps['project'])
                if routed.get('presentation_backend',{}).get('backend')!=caps['backend']:
                    raise ValueError('Native application selection changed after preflight')
                render_saved(pptx,root/attempt['directory'],routed,width)
            else:render(pptx, root/attempt['directory'], caps, width=width)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            attempt['status'] = 'TRANSIENT_FAILURE' if isinstance(error, (TimeoutError, subprocess.TimeoutExpired)) else 'FAILED'
            attempt['error'] = str(error)[-1000:]
            attempt['seconds'] = time.monotonic()-begin
            write_json(ledger_file, ledger)
            return {'status': 'CAPABILITY_BLOCKED', 'key': key, 'reason': attempt['error'],
                    'retry_allowed': attempt['status'] == 'TRANSIENT_FAILURE' and len(ledger['attempts']) < 2,
                    'seconds':attempt['seconds'],'attempts_used':1,
                    'fallback_attempts': 0}
        attempt.update(status='PASS', seconds=time.monotonic()-begin)
        ledger['success'] = attempt['directory']
        write_json(ledger_file, ledger)
        receipt_file = root/attempt['directory']/'render.json'
        receipt = read_json(receipt_file)
        return {'status': 'PASS', 'key': key, 'cache_hit': False, 'receipt': str(receipt_file),
                'preview': str(receipt_file.parent/'Final_preview.png'),
                'seconds': attempt['seconds'],'attempts_used':1, 'portable_render_verified': True,
                'office_interactive_edit_verified': 'not_run'}


def release_pdf(pptx,receipt_file):
    """All consumers have finished; retain hash-bound proof without re-rendering."""
    from .render import verify_alternative_render
    receipt_file=Path(receipt_file);directory=receipt_file.parent
    proof_file=directory/'pdf-release.json'
    if proof_file.exists():return read_json(proof_file)
    proof=verify_alternative_render(pptx,receipt_file)
    receipt=read_json(receipt_file)
    result={'status':'VALIDATED_AND_RELEASED','validation':proof,'receipt_sha256':digest(receipt_file),
            'pdf_sha256':receipt['pdf_hash'],'preview_sha256':receipt['preview_hash'],'pptx_sha256':digest(pptx)}
    # Only exact task-owned intermediate artifacts, after consistency validation.
    for name in ('Final.pdf','editor-input.pptx'):
        target=(directory/name).resolve()
        if target.parent!=directory.resolve():raise ValueError('Intermediate path escaped render directory')
        if target.is_file():target.unlink()
    write_json(proof_file,result)
    return result
