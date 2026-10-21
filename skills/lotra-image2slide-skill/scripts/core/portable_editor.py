"""Single bounded process controller for the bundled cross-platform editor."""
import os
from pathlib import Path
import subprocess
import time
import uuid
from .common import digest,write_json


def export_pdf(pptx,output,caps,timeout=120):
    from .math_editor import prepare
    from .editor_backend import run
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    before=digest(pptx);prepare(pptx,output)
    begin=time.monotonic()
    run(caps,output,timeout=timeout)
    if digest(pptx)!=before:raise RuntimeError('Editor modified canonical PPTX')
    return {'seconds':time.monotonic()-begin,'pptx_hash':before}


def render(pptx,output,caps,width=1440,timeout=120):
    from pptx import Presentation
    from .render import rasterize_pdf
    if caps.get('backend') in ('PowerPoint','WPS'):
        from .presentation_backend import render as native_render
        return native_render(pptx,output,caps,width=width,timeout=timeout)
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
