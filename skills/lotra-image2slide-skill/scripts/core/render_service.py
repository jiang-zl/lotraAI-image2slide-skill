"""Finite filesystem requests to a separately authorized local render worker.

The client receives no shell, network or broader filesystem permission. The
worker has one fixed operation: actual LibreOffice rendering of a hash-bound
project PPTX. All semantic/quality/acceptance gates remain in the ordinary loop.
"""
import os,re,time,uuid
from pathlib import Path
from zipfile import ZipFile
from .common import digest,identity,read_json,safe_path,write_json

SCHEMA='lotra-local-render-1'

def validate(project,job):
    project=Path(project).resolve()
    fields={'schema','id','input','input_sha256','output','width','timeout','fontconfig','service_nonce'}
    if not isinstance(job,dict) or set(job)-fields or job.get('schema')!=SCHEMA:
        raise ValueError('Typed local render request required; arbitrary commands are forbidden')
    if not re.fullmatch('[0-9a-f]{32}',str(job.get('id',''))):raise ValueError('Invalid render request ID')
    for key in ('width','timeout'):
        value=job.get(key)
        lo,hi=(32,12000) if key=='width' else (1,180)
        if type(value) is not int or not lo<=value<=hi:raise ValueError('Invalid bounded render '+key)
    pptx=safe_path(project,job.get('input',''));output=safe_path(project,job.get('output',''))
    relative=output.relative_to(project)
    if not relative.parts or relative.parts[0] in ('.agents','.codex','.git','input'):
        raise ValueError('Render output must stay inside owned writable project work')
    if pptx.suffix.lower()!='.pptx' or not pptx.is_file() or digest(pptx)!=job.get('input_sha256'):
        raise ValueError('Actual immutable input PPTX hash is required')
    if output.exists():raise FileExistsError(output)
    if pptx.stat().st_size>512*1024*1024:raise ValueError('Render input budget exceeded')
    with ZipFile(pptx) as z:
        if sum(i.file_size for i in z.infolist())>2*1024**3:raise ValueError('Expanded native package budget exceeded')
        if 'ppt/presentation.xml' not in z.namelist():raise ValueError('Not an actual presentation package')
        # Clickable references do not fetch resources while rendering. Linked
        # external media/objects would; this worker never retrieves them.
        from lxml import etree as E
        for name in z.namelist():
            if not name.endswith('.rels'):continue
            for row in E.fromstring(z.read(name)):
                if row.get('TargetMode')=='External' and not row.get('Type','').endswith('/hyperlink'):
                    raise ValueError('External media/data are forbidden in the offline render worker')
    font=None
    if job.get('fontconfig') is not None:
        ref=job['fontconfig']
        if not isinstance(ref,dict) or set(ref)!={'path','sha256'}:raise ValueError('Typed local font resource required')
        font=safe_path(project,ref['path'])
        if not font.is_file() or digest(font)!=ref['sha256']:raise ValueError('Renderer font resource changed')
    return {'pptx':pptx,'output':output,'fontconfig':font}

def request(pptx,output,width,timeout,fontconfig,descriptor):
    descriptor=Path(descriptor).resolve()
    if descriptor.name!='local-render-service.json' or descriptor.parent.name!='toolchain' or descriptor.parent.parent.name!='.lotraAI-build':
        raise ValueError('Render service descriptor must be project-local')
    root=descriptor.parents[2];service=read_json(descriptor)
    if (service.get('schema')!=SCHEMA or service.get('script_sha256')!=digest(Path(__file__))
            or service.get('status')!='READY' or (time.time()-service.get('heartbeat_unix',0)>20 and time.time()>service.get('busy_until_unix',0))):
        raise RuntimeError('Current separately authorized local render service is not ready')
    token=uuid.uuid4().hex
    job={'schema':SCHEMA,'id':token,'input':Path(pptx).resolve().relative_to(root).as_posix(),
        'input_sha256':digest(pptx),'output':Path(output).resolve().relative_to(root).as_posix(),
        'width':width,'timeout':timeout,'fontconfig':None,'service_nonce':service['nonce']}
    if fontconfig:
        file=Path(fontconfig).resolve();job['fontconfig']={'path':file.relative_to(root).as_posix(),'sha256':digest(file)}
    validate(root,job)
    queue=root/'.lotraAI-build/toolchain/render-requests';folder=queue/token;folder.mkdir(parents=True,exist_ok=False)
    write_json(folder/'Request.json',job);expected_request=digest(folder/'Request.json');deadline=time.monotonic()+timeout+20
    try:
        while time.monotonic()<deadline:
            response=folder/'Response.json'
            if response.is_file():
                row=read_json(response)
                if row.get('request_sha256')!=expected_request or row.get('service_nonce')!=service['nonce']:
                    raise ValueError('Local render response belongs to another request')
                if row.get('status')!='RENDERED':raise RuntimeError('Actual local render failed: '+str(row.get('reason')))
                from .render import verify_alternative_render
                receipt=Path(output)/'render.json'
                if digest(receipt)!=row.get('receipt_sha256'):raise ValueError('Actual render receipt changed')
                verify_alternative_render(pptx,receipt)
                return read_json(receipt)
            time.sleep(.1)
        raise RuntimeError('Local render service deadline exceeded; preserve request and pending actual-render gate')
    except BaseException:
        write_json(folder/'Cancel.json',{'id':token,'service_nonce':service['nonce']})
        raise

def execute(project,request_file):
    job=read_json(request_file);files=validate(project,job)
    from .render import render
    receipt=render(files['pptx'],files['output'],width=job['width'],timeout=job['timeout'],
        fontconfig=files['fontconfig'],_service=False)
    if receipt['pptx_hash']!=job['input_sha256']:raise ValueError('Actual render input changed')
    return {'status':'RENDERED','receipt_sha256':digest(files['output']/'render.json')}

def serve(project,seconds=7200):
    project=Path(project).resolve();toolchain=project/'.lotraAI-build/toolchain';toolchain.mkdir(parents=True,exist_ok=True)
    queue=toolchain/'render-requests';queue.mkdir(exist_ok=True)
    descriptor=toolchain/'local-render-service.json';nonce=uuid.uuid4().hex;started=time.monotonic()
    script=Path(__file__).resolve().parents[1]/'local_render_service.py';handled=set()
    from .worker_process import run
    record={'schema':SCHEMA,'status':'READY','nonce':nonce,'script_sha256':digest(Path(__file__)),
        'operation':'actual_saved_pptx_render_only','arbitrary_commands':False,'semantic_decisions':False,
        'network_code':False,'pid':os.getpid()}
    try:
        while time.monotonic()-started<seconds and not (toolchain/('stop-render-service-'+nonce)).exists():
            record['heartbeat_unix']=time.time();write_json(descriptor,record)
            for file in sorted(queue.glob('*/Request.json')):
                if file.parent.name in handled:continue
                job=None
                try:
                    if file.stat().st_size>16384:raise ValueError('Bounded local request required')
                    job=read_json(file)
                    if not isinstance(job,dict):raise ValueError('Typed local request required')
                    if job.get('service_nonce')!=nonce:continue
                    if file.parent.name!=job.get('id'):raise ValueError('Wrong local request directory')
                    if (file.parent/'Cancel.json').exists():raise RuntimeError('Owned render request cancelled before execution')
                    validate(project,job)
                    record.update(busy_until_unix=time.time()+job['timeout']+12,heartbeat_unix=time.time());write_json(descriptor,record)
                    result=run([__import__('sys').executable,'-B',str(script),'job','--project',str(project),
                        '--request',str(file)],job['timeout']+8)
                    if result.returncode:raise RuntimeError((result.stderr or result.stdout)[-1800:])
                    receipt=safe_path(project,job['output'])/'render.json'
                    if digest(safe_path(project,job['input']))!=job['input_sha256']:raise ValueError('Native input changed during render')
                    response={'status':'RENDERED','receipt_sha256':digest(receipt)}
                except (ValueError,OSError,RuntimeError,__import__('subprocess').TimeoutExpired) as error:
                    response={'status':'ACTUAL_RENDER_FAILED','reason':str(error)}
                response.update(request_sha256=digest(file),service_nonce=nonce)
                write_json(file.parent/'Response.json',response)
                handled.add(file.parent.name)
            time.sleep(.1)
    finally:
        record.update(status='STOPPED',heartbeat_unix=time.time());write_json(descriptor,record)
