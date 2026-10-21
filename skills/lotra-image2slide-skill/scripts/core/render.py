"""Render saved files on a declared canvas; alternate render is never Office proof."""
import os
import tempfile
from pathlib import Path
import shutil
from .common import digest, environment, run, write_json, identity, read_json


def font_environment(output, fontconfig=None):
    """Actual host files; disk identities amortize unchanged font hashing."""
    roots=[Path('/usr/share/fonts'),Path('/usr/local/share/fonts'),Path.home()/'.fonts',
           Path.home()/'.local/share/fonts',Path('/Library/Fonts'),Path('/System/Library/Fonts'),Path.home()/'Library/Fonts']
    if os.name=='nt':
        roots += [Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts',
                  Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'Microsoft/Windows/Fonts']
    if fontconfig and Path(fontconfig).is_file():
        from xml.etree import ElementTree as ET
        tree=ET.parse(fontconfig)
        roots += [Path(n.text).expanduser() for n in tree.findall('.//dir') if n.text]
    root=next((p for p in Path(output).resolve().parents if p.name=='.lotraAI-build'),Path(output).resolve())
    cache=root/'toolchain/font-identities.json'
    old=read_json(cache) if cache.is_file() else {};current={}
    for directory in dict.fromkeys(roots):
        if not directory.is_dir():continue
        for file in directory.rglob('*'):
            if file.suffix.lower() not in ('.ttf','.otf','.ttc') or not file.is_file():continue
            key=str(file.resolve());stat=file.stat();stamp=[stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns]
            entry=old.get(key,{})
            if entry.get('stamp')!=stamp:entry={'stamp':stamp,'sha256':digest(file)}
            current[key]=entry
    write_json(cache,current)
    return {'font_inventory_hash':identity({k:v['sha256'] for k,v in current.items()}),
            'font_identity_method':'Actual files with size/mtime/ctime based content-hash cache; explicit environment refresh retires observations'}


def rasterize_pdf(pdf, output, width, expected_pages=None, height=None):
    """One fixed slide-to-pixel transform for every comparison and gallery page."""
    import pymupdf as fitz
    from PIL import Image
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if not isinstance(width,int) or not 32<=width<=12000:
        raise ValueError('Preview width must be 32..12000 pixels')
    doc=fitz.open(pdf)
    if not len(doc) or expected_pages is not None and len(doc)!=expected_pages:
        raise ValueError('Rendered PDF page count differs from saved presentation')
    pages=[]
    for i,page in enumerate(doc):
        target_height=height if height is not None else round(width*page.rect.height/page.rect.width)
        if not isinstance(target_height,int) or not 1<=target_height<=12000:raise ValueError('Invalid declared canvas height')
        pix=page.get_pixmap(matrix=fitz.Matrix(width/page.rect.width,target_height/page.rect.height),alpha=False)
        image=Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
        # PDF rasterizer rounding only; no content-dependent alignment.
        if image.size!=(width,target_height):image=image.resize((width,target_height),Image.Resampling.LANCZOS)
        name='Final_preview.png' if i==0 else f'Page_{i+1}.png'
        path=output/name;image.save(path)
        pages.append({'page':i+1,'path':name,'sha256':digest(path),'canvas':[width,target_height]})
    doc.close()
    return pages


def render(pptx, output, timeout=120, width=1440, executable=None,fontconfig=None,_service=True):
    from pptx import Presentation
    pptx,output=Path(pptx).resolve(),Path(output).resolve()
    if output.exists():raise FileExistsError(output)
    if _service and os.environ.get('LOTRAAI_LOCAL_RENDER_SERVICE'):
        from .render_service import request
        return request(pptx,output,width,timeout,fontconfig,os.environ['LOTRAAI_LOCAL_RENDER_SERVICE'])
    exe=executable or os.environ.get('LOTRAAI_SOFFICE')
    if not exe:
        # Desktop must supply its bundled executable, not the user's GUI app.
        import platform
        exe=shutil.which('soffice') if platform.system()!='Darwin' else None
    if not exe or not Path(exe).is_file():
        raise RuntimeError('Bundled LibreOffice required: set LOTRAAI_SOFFICE to the runtime-provided absolute executable')
    output.mkdir(parents=True);before=digest(pptx)
    render_env=dict(os.environ)
    if fontconfig:
        if not Path(fontconfig).is_file():raise ValueError('Configured renderer font discovery file is missing')
        render_env['FONTCONFIG_FILE']=str(Path(fontconfig).resolve())
    with tempfile.TemporaryDirectory(prefix='lotraai-lo-',dir=output) as profile:
        import subprocess
        render_env.update(TEMP=profile,TMP=profile,TMPDIR=profile,XDG_CACHE_HOME=profile,XDG_CONFIG_HOME=profile,XDG_RUNTIME_DIR=profile,
            GSETTINGS_BACKEND='memory',SAL_USE_VCLPLUGIN='svp')
        try:
            proc=subprocess.run([exe,'-env:UserInstallation='+Path(profile).as_uri(),'--headless','--convert-to','pdf','--outdir',str(output),str(pptx)],
                            timeout=timeout,check=False,capture_output=True,text=True,env=render_env)
        except (OSError,subprocess.TimeoutExpired) as error:
            write_json(output/'render-failure.json',{'status':'ACTUAL_RENDER_FAILED','backend':'LibreOffice',
                'stage':'pdf-export','pptx_hash':before,'reason':str(error),'timeout':isinstance(error,subprocess.TimeoutExpired),
                'temporary_directory':profile,'drawing_bytes_changed':digest(pptx)!=before})
            raise
        if proc.returncode:
            write_json(output/'render-failure.json',{'status':'ACTUAL_RENDER_FAILED','backend':'LibreOffice',
                'pptx_hash':before,'exit_code':proc.returncode,'stdout':proc.stdout[-2500:],
                'stderr':proc.stderr[-2500:],'drawing_bytes_changed':digest(pptx)!=before,
                'scope':'Captured actual export failure; no acceptance or substitute preview'})
            raise RuntimeError('Actual LibreOffice render failed: '+proc.stderr[-600:])
        stdout=proc.stdout
    generated=output/(pptx.stem+'.pdf')
    if not generated.is_file() or not generated.stat().st_size:
        write_json(output/'render-failure.json',{'status':'ACTUAL_RENDER_FAILED','backend':'LibreOffice',
            'stage':'pdf-output','pptx_hash':before,'exit_code':proc.returncode,'stdout':stdout[-2500:],
            'stderr':proc.stderr[-2500:],'reason':'No nonempty PDF; PNG is not a substitute'})
        raise RuntimeError('Renderer produced no PDF: '+stdout)
    final=output/'Final.pdf'
    if generated!=final:generated.rename(final)
    prs=Presentation(pptx)
    pages=rasterize_pdf(final,output,width,len(prs.slides),round(width*prs.slide_height/prs.slide_width))
    if digest(pptx)!=before:raise RuntimeError('Renderer changed input PPTX')
    receipt={'status':'PASS','scope':'alternative_render_only','backend':'LibreOffice',
             'backend_version':subprocess.run([exe,'--version'],capture_output=True,text=True,timeout=15,env=render_env).stdout.strip(),'executable':str(exe),
             'target_powerpoint':'UNVERIFIED','pptx_hash':before,'pdf':{'status':'EXPORTED','path':'Final.pdf'},'pdf_hash':digest(final),
             'preview_hash':pages[0]['sha256'],'pages':pages,'environment':environment(),
             'mapping':'fixed_canvas_no_content_registration'}
    fontconfig=fontconfig or os.environ.get('FONTCONFIG_FILE')
    if fontconfig:
        path=Path(fontconfig).resolve()
        receipt['fontconfig']={'path':str(path),'sha256':digest(path),
                              'scope':'explicit process-local font discovery; inspect PDF for actual font use'}
    receipt.update(font_environment(output,fontconfig))
    receipt['renderer_script_hash']=digest(Path(__file__))
    write_json(output/'render.json',receipt)
    from .transient_export import register
    register(output,pptx,receipt)
    return receipt


def verify_alternative_render(pptx, receipt_file):
    """Verify saved LibreOffice artifacts by an independent PDF rasterization.

    This establishes consistency of the saved PPT, PDF and preview. It does not
    claim PowerPoint fidelity or a native editing operation.
    """
    from pptx import Presentation
    from .common import read_json
    pptx,receipt_file=Path(pptx),Path(receipt_file)
    receipt=read_json(receipt_file);directory=receipt_file.parent
    if receipt.get('schema')=='presentation-backend-1.36.0':
        from .presentation_backend import verify_render
        return verify_render(pptx,receipt_file)
    if (receipt.get('status')!='PASS' or receipt.get('backend')!='LibreOffice'
            or receipt.get('scope')!='alternative_render_only'
            or receipt.get('target_powerpoint')!='UNVERIFIED'
            or receipt.get('pptx_hash')!=digest(pptx)):
        raise ValueError('Unsupported or stale alternate renderer receipt')
    pdf=directory/'Final.pdf';preview=directory/'Final_preview.png'
    if (not pdf.is_file() or not preview.is_file() or
            digest(pdf)!=receipt.get('pdf_hash') or digest(preview)!=receipt.get('preview_hash')):
        raise ValueError('Alternate-render artifacts changed or are missing')
    pages=receipt.get('pages')
    if not isinstance(pages,list) or not pages or pages[0].get('sha256')!=digest(preview):
        raise ValueError('Alternate-render page manifest changed')
    prs=Presentation(pptx);width=pages[0]['canvas'][0]
    with tempfile.TemporaryDirectory(prefix='lotraai-alt-render-check-') as temporary:
        fresh=rasterize_pdf(pdf,temporary,width,len(prs.slides),
                            round(width*prs.slide_height/prs.slide_width))
    if fresh!=pages:
        raise ValueError('Alternate preview differs from fresh PDF rasterization')
    return {'status':'PASS','scope':'saved_alternate_render_only','target_powerpoint':'UNVERIFIED'}
