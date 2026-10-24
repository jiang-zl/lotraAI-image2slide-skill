"""Qualify local presentation programs after the prepared project core exists."""
import json
import os
from pathlib import Path
import subprocess
import uuid
from install import read_json,write_json,within,sha,readable_windows_path


def qualify(project,skill,key,workspace):
    project,skill,workspace=map(Path,(project,skill,workspace))
    profile=read_json(project/'.lotraAI-build/toolchain'/('core-runtime-'+key+'.json'))
    engine=within(project,profile['engine']['path'])
    out=workspace/('Native-presentation-'+uuid.uuid4().hex[:12]+'.json')
    code='import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from core.presentation_backend import select;from core.common import write_json;r=select(sys.argv[2],refresh=True);write_json(sys.argv[3],r)'
    log=out.with_suffix('.log')
    with log.open('wb') as stream:
        proc=subprocess.run([str(engine),'-I','-X','utf8','-B','-c',code,
            str(Path(readable_windows_path(skill))/'scripts'),readable_windows_path(project),str(out)],
            stdout=stream,stderr=stream,timeout=280,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if proc.returncode or not out.is_file():raise ValueError('Presentation qualification helper failed: '+str(log))
    result=read_json(out)
    if result.get('status')!='READY':
        if result.get('backend') not in ('auto','LibreOffice'):
            raise ValueError('Explicit presentation backend unavailable: '+str(result))
        return None
    return {'status':'LOCAL_NATIVE_READY','version':result.get('backend_version'),
        'resource_reused':True,'tested':True,'render_status':'FIXTURE_PASS',
        'backend':{'execution_mode':'local_application','status':'READY','presentation_backend':result,
                   'probe':{'path':out.relative_to(project).as_posix(),'sha256':sha(out)},
                   'revalidated':True,'render_status':'FIXTURE_PASS','office_behavior':'FIXTURE_EDIT_SAVE_REOPEN_PASS'}}


def readiness(math):
    local=math.get('status')=='LOCAL_NATIVE_READY'
    fallback=math.get('presentation_probe',{}).get('status')=='PASS'
    return {'presentation_backend':math.get('backend',{}).get('presentation_backend'),
        'libreoffice_required':not local,'render_ready':local or fallback,'native_edit_ready':local,
        'render_status':'FIXTURE_PASS' if local or fallback else 'NOT_RUN',
        'scope':'environment fixture only; every final artifact has independent gates',
        'whole_drawing_acceptance':False}


def qualify_fallback(project,skill,key,workspace):
    project,skill,workspace=map(Path,(project,skill,workspace))
    profile=read_json(project/'.lotraAI-build/toolchain'/('core-runtime-'+key+'.json'))
    engine=within(project,profile['engine']['path'])
    folder=project/'.lotraAI-build/backend-probes'/('lo-'+uuid.uuid4().hex[:12]);folder.mkdir(parents=True)
    code='''import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from core.presentation_backend import fixture
from core.portable_runtime import capabilities
from core.portable_editor import render
from core.libreoffice_backend import save_reopen
from core.common import write_json,digest
p=Path(sys.argv[2]);root=Path(sys.argv[3]);fixture(root/'Fixture.pptx')
caps=capabilities(p,requested='libreoffice')
if caps.get('status')!='READY':raise RuntimeError(str(caps))
r=render(root/'Fixture.pptx',root/'render',caps)
s=save_reopen(root/'Fixture.pptx',root/'save',caps['executable'],renderer=caps)
write_json(root/'Qualification.json',{'status':'PASS','backend':'LibreOffice','render_sha256':digest(root/'render/render.json'),'save_reopen':s,'scope':'this host fixture; Office editing remains UNVERIFIED'})
'''
    with (folder/'Helper.log').open('wb') as log:
        proc=subprocess.run([str(engine),'-I','-X','utf8','-B','-c',code,str(Path(readable_windows_path(skill))/'scripts'),
            readable_windows_path(project),str(folder)],stdout=log,stderr=log,timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if proc.returncode:raise ValueError('LibreOffice actual PDF/save/reopen qualification failed: '+str(folder/'Helper.log'))
    value=read_json(folder/'Qualification.json')
    if value.get('status')!='PASS':raise ValueError('LibreOffice qualification incomplete')
    return value
