"""Fresh saved-PPTX/core/renderer facts; never an image-reconstruction PASS."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--skill', type=Path, required=True)
p.add_argument('--project', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--skip-render', action='store_true')
a = p.parse_args()
sys.path.insert(0, str(a.skill.resolve() / 'scripts'))

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.shapes import MSO_SHAPE
from core.tool_router import capabilities, render_saved, route

out = a.out.resolve()
out.mkdir(parents=True, exist_ok=True)
pptx = out / 'Readiness-probe.pptx'
prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[6])
box = slide.shapes.add_textbox(Inches(.4), Inches(.4), Inches(6), Inches(.6))
box.text = 'lotraAI offline runtime'
box.text_frame.paragraphs[0].runs[0].font.size = Pt(24)
slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(.4), Inches(1.4), Inches(3), Inches(1.2))
prs.save(pptx)
reopened = Presentation(pptx)
if len(reopened.slides) != 1 or len(reopened.slides[0].shapes) != 2:
    raise ValueError('Minimal saved-native PPTX did not reopen')
source_sha = hashlib.sha256(pptx.read_bytes()).hexdigest()
result = {'status': 'CORE_AND_SAVED_PPTX_EXECUTED', 'saved_pptx_sha256': source_sha,
          'native_shapes': 2, 'saved_pptx_reopened': True, 'render_ready': False,
          'native_edit_ready': False, 'whole_drawing_acceptance': False,
          'render_probe_skipped': bool(a.skip_render), 'temporary_pdf_released': True}
try:
    caps = capabilities(project=a.project)
    chosen = route('render', {}, caps)
    result['route'] = chosen
    result['macos_office'] = caps.get('macos_office', {})
    result['windows_office_available'] = bool(caps.get('windows_office', {}).get('available'))
    if not a.skip_render and chosen.get('executor') in ('windows_office', 'libreoffice'):
        render_dir = out / 'render'
        def host_path(path):
            text = str(path)
            if os.name == 'nt' and text.startswith('\\\\?\\UNC\\'):
                return Path('\\\\' + text[8:])
            if os.name == 'nt' and text.startswith('\\\\?\\'):
                return Path(text[4:])
            return path
        result['actual_render'] = render_saved(host_path(pptx), host_path(render_dir), caps, 960)
        pdfs = list(render_dir.rglob('*.pdf'))
        if not pdfs:
            raise ValueError('Renderer did not return an actual PDF')
        import fitz
        facts = []
        for pdf in pdfs:
            with fitz.open(pdf) as document:
                if len(document) != 1:
                    raise ValueError('Minimal PDF page count mismatch')
                pix = document[0].get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
                if pix.width < 1 or pix.height < 1:
                    raise ValueError('PDF rasterization failed')
                facts.append({'sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
                              'pages': 1, 'independent_raster_size': [pix.width, pix.height]})
        result.update(render_ready=True, pdf_validation=facts)
    elif not a.skip_render:
        result['render_diagnostic'] = 'Bind an authorized host saved-PPTX renderer; installed Mac PowerPoint alone does not provide a program adapter.'
except Exception as error:
    result['render_diagnostic'] = str(error)[-2200:]
finally:
    # These PDFs are from this new source-free probe directory. All actual
    # validation consumers have closed their documents before release.
    for pdf in out.rglob('*.pdf'):
        if pdf.resolve().is_relative_to(out) and not pdf.is_symlink():
            pdf.unlink()
    result['temporary_pdf_released'] = not any(out.rglob('*.pdf'))
    (out / 'Result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: result[k] for k in ('status', 'render_ready', 'native_edit_ready', 'temporary_pdf_released')}))
