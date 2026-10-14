"""Hash/version visible SVG rendering without a mandatory system Cairo install."""
import io,os
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=2)
def backend(mode=None):
    if mode!='portable':
        try:
            import cairosvg
            return {'png':'CairoSVG','pdf':'CairoSVG','version':cairosvg.__version__}
        except (ImportError,OSError):pass
    import resvg_py,pymupdf
    return {'png':'resvg_py','pdf':'MuPDF','version':resvg_py.__version__,
            'resvg':resvg_py.__resvg_version__,'mupdf':pymupdf.VersionBind}

def svg2png(bytestring,write_to=None,output_width=None,output_height=None,mode=None):
    selected=backend(mode)
    if selected['png']=='CairoSVG':
        import cairosvg
        data=cairosvg.svg2png(bytestring=bytestring,output_width=output_width,output_height=output_height)
    else:
        import resvg_py
        data=resvg_py.svg_to_bytes(svg_string=bytestring.decode('utf-8') if isinstance(bytestring,bytes) else bytestring,
            width=output_width,height=output_height,skip_system_fonts=False)
    if write_to is not None:Path(write_to).write_bytes(data)
    return data

def svg2pdf(bytestring,write_to=None,mode=None):
    if backend(mode)['pdf']=='CairoSVG':
        import cairosvg
        data=cairosvg.svg2pdf(bytestring=bytestring)
    else:
        import pymupdf as fitz
        with fitz.open(stream=bytestring,filetype='svg') as doc:data=doc.convert_to_pdf()
    if write_to is not None:Path(write_to).write_bytes(data)
    return data
