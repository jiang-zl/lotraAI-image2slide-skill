"""Owned LibreOffice save/reopen checks; canonical PPTX is never roundtripped."""
import os
from pathlib import Path
import subprocess
import uuid
from .common import digest,write_json


def save_reopen(pptx,output,executable,timeout=120):
    from pptx import Presentation
    from .render import render
    from .office_compatibility import validate
    pptx=Path(pptx).resolve(strict=True);output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    before=digest(pptx);profile=output/'profile';temp=output/'temp';saved=output/'saved'
    for path in (profile,temp,saved):path.mkdir()
    env=dict(os.environ)
    env.update({k:str(temp) for k in ('TEMP','TMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_RUNTIME_DIR')})
    env.update(SAL_USE_VCLPLUGIN='svp',GSETTINGS_BACKEND='memory')
    command=[str(executable),'-env:UserInstallation='+profile.as_uri(),'--headless','--norestore',
        '--convert-to','pptx:Impress MS PowerPoint 2007 XML','--outdir',str(saved),str(pptx)]
    try:
        with (output/'Save.log').open('wb') as log:
            process=subprocess.Popen(command,stdout=log,stderr=log,env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,start_new_session=os.name!='nt')
            try:process.wait(timeout=timeout)
            finally:
                from .editor_backend import _stop
                _stop(process)
        target=saved/pptx.name
        if process.returncode or not target.is_file() or not target.stat().st_size:
            raise RuntimeError('LibreOffice PPTX save failed: '+(output/'Save.log').read_text(encoding='utf-8',errors='replace')[-2000:])
        validate(target)
        if len(Presentation(target).slides)!=len(Presentation(pptx).slides):raise ValueError('Saved slide count changed')
        # Open the application-saved PPTX again through the actual application.
        receipt=render(target,output/'reopen-render',executable=executable,timeout=timeout)
        if digest(pptx)!=before:raise ValueError('LibreOffice modified canonical input')
        result={'status':'PASS','backend':'LibreOffice','input_sha256':before,'saved_sha256':digest(target),
            'pdf_sha256':receipt['pdf_hash'],'scope':'LibreOffice save and actual reopen export of owned copy; PowerPoint/WPS editing UNVERIFIED',
            'canonical_input_unchanged':True,'target_powerpoint':'UNVERIFIED','temporary_directory':str(temp)}
        write_json(output/'Save-reopen.json',result);return result
    except Exception as error:
        write_json(output/'Backend-failure.json',{'status':'FAILED','backend':'LibreOffice','stage':'save-reopen',
            'input_sha256':before,'reason':str(error),'canonical_input_unchanged':digest(pptx)==before})
        raise
