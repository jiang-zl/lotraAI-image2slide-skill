"""Single bounded process controller for the bundled cross-platform editor."""
import os
from pathlib import Path
import subprocess
import time
import uuid
from .common import digest,write_json


def export_pdf(pptx,output,caps,timeout=120):
    from .math_editor import prepare
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    before=digest(pptx);prepare(pptx,output)
    runtime_root=next((p for p in output.resolve().parents if p.name=='.lotraAI-build'),output.parent)
    profile=runtime_root/'editor-profiles'/uuid.uuid4().hex;profile.mkdir(parents=True)
    connection='pipe,name=lotra'+uuid.uuid4().hex
    env=dict(os.environ)
    for variable in ('URE_BOOTSTRAP','UNO_PATH','PYTHONHOME'):env.pop(variable,None)
    if caps.get('fontconfig'):env['FONTCONFIG_FILE']=caps['fontconfig']
    args=[caps['executable'],'-env:UserInstallation='+profile.resolve().as_uri(),
          '--headless','--nologo','--nodefault','--norestore','--accept='+connection+';urp;']
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    begin=time.monotonic()
    with (output/'editor-server.log').open('wb') as log:
        process=subprocess.Popen(args,stdout=log,stderr=log,env=env,creationflags=flags,start_new_session=os.name!='nt')
        try:
            client=subprocess.run([caps['uno_python'],'-B',str(Path(__file__).with_name('uno_editor_client.py')),
                connection,str(output.resolve())],capture_output=True,timeout=timeout,env=env,creationflags=flags)
            (output/'editor-client.log').write_bytes(client.stdout+b'\n'+client.stderr)
            if client.returncode:raise RuntimeError('Native Math editor export failed: '+client.stderr.decode('utf-8','replace')[-1000:])
            if not (output/'Final.pdf').is_file():raise RuntimeError('Native editor produced no PDF')
        finally:
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Terminate only this task's owned process tree. No global kill.
                if os.name=='nt':
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=10,creationflags=flags)
                else:
                    import signal
                    try:os.killpg(process.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                process.wait(timeout=5)
    if digest(pptx)!=before:raise RuntimeError('Editor modified canonical PPTX')
    return {'seconds':time.monotonic()-begin,'pptx_hash':before}


def render(pptx,output,caps,width=1440,timeout=120):
    from pptx import Presentation
    from .render import rasterize_pdf
    result=export_pdf(pptx,output,caps,timeout);output=Path(output)
    prs=Presentation(pptx)
    pages=rasterize_pdf(output/'Final.pdf',output,width,len(prs.slides),round(width*prs.slide_height/prs.slide_width))
    receipt={'status':'PASS','scope':'alternative_render_only','backend':'LibreOffice',
        'backend_version':caps['version'],'executable':caps['executable'],'renderer_identity':caps['identity'],
        'target_powerpoint':'UNVERIFIED','pptx_hash':result['pptx_hash'],
        'pdf':{'status':'EXPORTED','path':'Final.pdf'},'pdf_hash':digest(output/'Final.pdf'),
        'preview_hash':pages[0]['sha256'],'pages':pages,'mapping':'fixed_canvas_native_math_editor',
        'math_editor_receipt_hash':digest(output/'math-editor.json'),'seconds':result['seconds']}
    write_json(output/'render.json',receipt)
    return receipt
