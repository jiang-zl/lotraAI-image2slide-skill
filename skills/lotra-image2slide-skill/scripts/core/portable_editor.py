"""Single bounded process controller for the bundled cross-platform editor."""
import os
from pathlib import Path
import subprocess
import time
import uuid
from .common import digest,write_json


def export_pdf(pptx,output,caps,timeout=120,native_math_import=False):
    from .math_editor import prepare
    from .editor_backend import run
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    before=digest(pptx);prepare(pptx,output,native_math_import=native_math_import)
    begin=time.monotonic()
    run(caps,output,timeout=timeout)
    if digest(pptx)!=before:raise RuntimeError('Editor modified canonical PPTX')
    import json
    import pymupdf
    from .native_font_aliases import verify_pdf_families
    proof=json.loads((output/'math-editor.json').read_bytes())
    with pymupdf.open(output/'Final.pdf') as document:
        names={row[3] for page in document for row in page.get_fonts(full=True)}
    fonts=verify_pdf_families(proof['ordinary_fonts']['families'],names)
    write_json(output/'ordinary-font-render.json',fonts)
    return {'seconds':time.monotonic()-begin,'pptx_hash':before,'ordinary_fonts':fonts,
            'ordinary_font_receipt_hash':digest(output/'ordinary-font-render.json')}


def render(pptx,output,caps,width=1440,timeout=120,native_math_import=False):
    from pptx import Presentation
    from .render import rasterize_pdf
    if caps.get('backend') in ('PowerPoint','WPS'):
        from .presentation_backend import render as native_render
        return native_render(pptx,output,caps,width=width,timeout=timeout)
    result=export_pdf(pptx,output,caps,timeout,native_math_import=native_math_import);output=Path(output)
    prs=Presentation(pptx)
    pages=rasterize_pdf(output/'Final.pdf',output,width,len(prs.slides),round(width*prs.slide_height/prs.slide_width))
    receipt={'status':'PASS','scope':'alternative_render_only','backend':'LibreOffice',
        'backend_version':caps['version'],'executable':caps['executable'],'renderer_identity':caps['identity'],
        'target_powerpoint':'UNVERIFIED','pptx_hash':result['pptx_hash'],
        'pdf':{'status':'EXPORTED','path':'Final.pdf'},'pdf_hash':digest(output/'Final.pdf'),
        'preview_hash':pages[0]['sha256'],'pages':pages,'mapping':'fixed_canvas_native_math_editor',
        'math_editor_receipt_hash':digest(output/'math-editor.json'),'seconds':result['seconds']}
    receipt.update(ordinary_fonts=result['ordinary_fonts'],ordinary_font_receipt_hash=result['ordinary_font_receipt_hash'])
    write_json(output/'render.json',receipt)
    return receipt
