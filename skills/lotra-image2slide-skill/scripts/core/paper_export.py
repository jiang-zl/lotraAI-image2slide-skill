"""Office/native layout plus compact vector masters in its saved picture slots."""
import base64
import copy
import hashlib
import io
import posixpath
import re
import shutil
import subprocess
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
from .common import digest, write_json
from .mathml import NS



def _subset_used_fonts(document):
    """Compact actually embedded fonts; retain unsupported data without substitution."""
    def font_bytes():
        refs={r[0] for page in document for r in page.get_fonts(full=True) if r[0]>0}
        total=0
        for ref in refs:
            try:total+=len(document.extract_font(ref)[3])
            except RuntimeError:continue
        return total
    before=font_bytes()
    document.subset_fonts()
    after=font_bytes();mode="MuPDF native"
    # Some Office CFF streams cannot be parsed by the native subsetter.
    # A different parser is a bounded fallback, not a repeated native attempt.
    if before>262144 and after>=before:
        try:
            import fontTools
        except ImportError:
            mode="MuPDF native; unsupported large fonts retained"
        else:
            document.subset_fonts(fallback=True)
            after=font_bytes();mode="fontTools fallback "+fontTools.__version__
    return {"method":mode,"embedded_font_bytes_before":before,"embedded_font_bytes_after":after,
            "scope":"Only embedded used-glyph subsets; no font substitution, geometry or native PPT edit"}
def _canonical_gray_masks(root):
    """Keep grayscale-mask luminosity as white RGBA alpha across SVG renderers.

    PDF exporters may use opaque grayscale image masks. Alpha-only consumers
    otherwise fill an entire glyph rectangle. Geometry and ordinary images
    stay unchanged; unsupported coloured masks stay explicitly untouched.
    """
    import numpy as np
    from PIL import Image
    href_key="{http://www.w3.org/1999/xlink}href"
    nodes={n.get("id"):n for n in root.iter() if n.get("id")}
    copies={};changed=0
    svg_root=root.getroot() if hasattr(root,"getroot") else root
    defs=next((n for n in svg_root if isinstance(n.tag,str) and E.QName(n).localname=="defs"),None)
    if defs is None:
        defs=E.Element("{http://www.w3.org/2000/svg}defs");svg_root.insert(0,defs)
    for mask in root.xpath('//*[local-name()="mask"]'):
        if mask.get("mask-type")=="alpha" or "mask-type:alpha" in mask.get("style","").replace(" ",""):
            continue
        for node in list(mask.iter()):
            if not isinstance(node.tag,str):continue
            kind=E.QName(node).localname
            image=node
            if kind=="use":
                reference=node.get(href_key) or node.get("href","")
                image=nodes.get(reference[1:]) if reference.startswith("#") else None
            if image is None or E.QName(image).localname!="image":continue
            reference=image.get(href_key) or image.get("href","")
            if not reference.startswith("data:image/png;base64,"):continue
            rgba=np.array(Image.open(io.BytesIO(base64.b64decode(reference.split(",",1)[1]))).convert("RGBA"))
            if np.ptp(rgba[...,:3].astype(int),axis=2).max()>1:continue
            if np.all(rgba[...,:3]==255):continue  # already canonical/idempotent
            alpha=np.rint(rgba[...,0].astype(float)*rgba[...,3]/255).astype("uint8")
            canonical=np.full_like(rgba,255);canonical[...,3]=alpha
            out=io.BytesIO();Image.fromarray(canonical).save(out,format="PNG")
            uri="data:image/png;base64,"+base64.b64encode(out.getvalue()).decode("ascii")
            if kind=="use":
                original=image.get("id")
                if original not in copies:
                    cloned=copy.deepcopy(image);new_id="lotra_alpha_"+hashlib.sha256((uri+str(sorted(image.attrib.items()))).encode()).hexdigest()[:20]
                    cloned.set("id",new_id);cloned.set(href_key,uri);cloned.attrib.pop("href",None)
                    defs.append(cloned);copies[original]=new_id
                node.set(href_key,"#"+copies[original]);node.attrib.pop("href",None)
            else:
                # Preserve any external use of an identified original image.
                if image.get("id"):
                    retained=copy.deepcopy(image);defs.append(retained);nodes[image.get("id")]=retained;image.attrib.pop("id",None)
                image.set(href_key,uri);image.attrib.pop("href",None)
            changed+=1
    return changed
def _image_keys(data):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        return {hashlib.md5(image.convert(mode).tobytes()).digest() for mode in ('RGB', 'RGBA', 'L')}


def _masters(pptx, output):
    records, index = {}, []
    with ZipFile(pptx) as archive:
        for name in archive.namelist():
            if not name.startswith('ppt/slides/slide') or not name.endswith('.xml'):
                continue
            root = E.fromstring(archive.read(name))
            relname = 'ppt/slides/_rels/'+Path(name).name+'.rels'
            rels = {r.get('Id'): r.get('Target') for r in E.fromstring(archive.read(relname))}
            for picture in root.xpath('.//*[local-name()="pic"]'):
                blip = picture.find('.//{'+NS['a']+'}blip')
                svg = picture.xpath('.//*[local-name()="svgBlip" or (local-name()="vectorMaster" and namespace-uri()="https://lotra.ai/ns/vector-master/1")]')
                if blip is None or not svg:
                    continue
                def resource(rid):
                    return archive.read(posixpath.normpath(posixpath.join('ppt/slides', rels[rid])))
                bitmap = resource(blip.get('{'+NS['r']+'}embed'))
                from .vector_asset import master_bytes
                master = master_bytes(resource(svg[0].get('{'+NS['r']+'}embed')),svg[0].get('compression'),svg[0].get('sha256'))
                sha = hashlib.sha256(master).hexdigest()
                file = output/'SVG-components'/(sha+'.svg')
                file.parent.mkdir(exist_ok=True)
                file.write_bytes(master)
                owner = picture.find('.//{'+NS['p']+'}cNvPr').get('name')
                for key in _image_keys(bitmap):
                    records.setdefault(key, {})[sha] = master
                index.append({'owner': owner, 'sha256': sha, 'path': 'SVG-components/'+file.name})
    write_json(output/'SVG-components.json', index)
    return records, index


def _carrier(pptx, destination, records):
    """Only SVG activation is removed; saved native layout and PNG slots remain."""
    from PIL import Image
    changes, markers, extras = [], {}, {}
    with ZipFile(pptx) as source, ZipFile(destination, 'w', ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == '[Content_Types].xml':
                types=E.fromstring(data)
                if not any(n.tag.endswith('Default') and n.get('Extension','').lower()=='png' for n in types):
                    namespace=types.tag.split('}')[0]+'}'
                    entry=E.SubElement(types,namespace+'Default')
                    entry.set('Extension','png');entry.set('ContentType','image/png')
                    data=E.tostring(types,xml_declaration=True,encoding='UTF-8',standalone=True)
            if info.filename.startswith('ppt/slides/slide') and info.filename.endswith('.xml'):
                root = E.fromstring(data)
                relname = 'ppt/slides/_rels/'+Path(info.filename).name+'.rels'
                relations = E.fromstring(source.read(relname))
                known = {r.get('Id'): r.get('Target') for r in relations}
                for svg in root.xpath('.//*[local-name()="svgBlip" or (local-name()="vectorMaster" and namespace-uri()="https://lotra.ai/ns/vector-master/1")]'):
                    svg_part = posixpath.normpath(posixpath.join('ppt/slides', known[svg.get('{'+NS['r']+'}embed')]))
                    from .vector_asset import master_bytes
                    blob = master_bytes(source.read(svg_part),svg.get('compression'),svg.get('sha256'))
                    sha = hashlib.sha256(blob).hexdigest()
                    if sha not in markers:
                        n = len(markers)
                        if n >= 3375:
                            raise ValueError('Split paper export: bounded marker palette exhausted')
                        rgb = tuple(16+16*((n//(15**i))%15) for i in range(3))
                        payload = io.BytesIO()
                        Image.new('RGB', (4, 4), rgb).save(payload, format='PNG')
                        part = 'ppt/media/lotra-slot-'+sha+'.png'
                        extras[part] = payload.getvalue()
                        markers[sha] = {'rgb': rgb, 'part': part, 'svg': blob}
                    marker = markers[sha]
                    rid = 'rIdLotra'+sha[:16]
                    if rid not in known:
                        node = E.SubElement(relations, '{http://schemas.openxmlformats.org/package/2006/relationships}Relationship')
                        node.set('Id', rid)
                        node.set('Type', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image')
                        node.set('Target', '../media/'+Path(marker['part']).name)
                        known[rid] = node.get('Target')
                    blip = svg.getparent().getparent().getparent()
                    blip.set('{'+NS['r']+'}embed', rid)
                    ext = svg.getparent()
                    ext.getparent().remove(ext)
                    changes.append(info.filename)
                if info.filename in changes:
                    data = E.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
                    extras[relname] = E.tostring(relations, xml_declaration=True, encoding='UTF-8', standalone=True)
            if info.filename in extras:
                data = extras.pop(info.filename)
            target.writestr(info, data)
        for name, data in extras.items():
            target.writestr(name, data)
    return {'source_sha256': digest(pptx), 'carrier_sha256': digest(destination),
            'changed_slide_parts': sorted(set(changes)),
            'scope': 'paper export carrier only; original PPTX never changed'}, markers


def _choice(records, keys):
    candidates = {}
    for key in keys:
        candidates.update(records.get(key, {}))
    return next(iter(candidates.items())) if len(candidates) == 1 else None


def _payload_choice(data, records, markers):
    from PIL import Image, ImageStat
    exact = _choice(records, _image_keys(data))
    if exact:
        return exact
    # Office may reencode/downsample previews. Tiny uniform, widely separated
    # slot colours bind identity without guessing similarity of real artwork.
    with Image.open(io.BytesIO(data)) as image:
        if max(image.size) > 32:
            return None
        stats = ImageStat.Stat(image.convert('RGB'))
    if max(stats.stddev) > .25:
        return None
    candidates = [(sha, item['svg']) for sha, item in markers.items()
                  if max(abs(a-b) for a,b in zip(stats.mean, item['rgb'])) <= 4]
    return candidates[0] if len(candidates) == 1 else None


def _vector_svg(pdf, target, records, markers):
    executable = shutil.which('pdftocairo')
    if executable:
        process = subprocess.run([executable, '-svg', str(pdf), str(target)], capture_output=True, text=True)
        if process.returncode:
            raise RuntimeError('Saved PDF to SVG export failed: '+process.stderr[-1000:])
    else:
        import pymupdf as fitz
        with fitz.open(pdf) as document:
            target.write_text(document[0].get_svg_image(text_as_path=True),encoding='utf-8')
    root = E.parse(str(target), E.XMLParser(huge_tree=True))
    promoted, matched = 0, set()
    for image in list(root.xpath('//*[local-name()="image"]')):
        href = image.get('{http://www.w3.org/1999/xlink}href') or image.get('href', '')
        if not href.startswith('data:') or ';base64,' not in href:
            continue
        match = _payload_choice(base64.b64decode(href.split(',', 1)[1]), records, markers)
        if not match:
            continue
        sha, data = match
        matched.add(sha)
        master = E.fromstring(data)
        prefix = 'v'+sha[:12]+'_'+str(promoted)+'_'
        names = {n.get('id'): prefix+n.get('id') for n in master.iter() if n.get('id')}
        for node in master.iter():
            if node.get('id'):
                node.set('id', names[node.get('id')])
            for key, value in list(node.attrib.items()):
                if key == 'id':
                    continue
                if value.startswith('#') and value[1:] in names:
                    value = '#'+names[value[1:]]
                value = re.sub(r'url\(#([^)]*)\)', lambda m: 'url(#'+names.get(m[1], m[1])+')', value)
                node.set(key, value)
        nested = E.Element('{http://www.w3.org/2000/svg}svg')
        for key, value in image.attrib.items():
            if not key.endswith('href'):
                nested.set(key, value)
        view_box = master.get('viewBox')
        if not view_box:
            width, height = master.get('width'), master.get('height')
            if not width or not height:
                raise ValueError('Vector master needs its real viewBox or explicit width/height; preserve the saved master and drawing')
            view_box = '0 0 '+width+' '+height
        nested.set('viewBox', view_box)
        nested.set('preserveAspectRatio', 'none')
        for child in master:
            nested.append(copy.deepcopy(child))
        image.getparent().replace(image, nested)
        promoted += 1
    canonical_masks = _canonical_gray_masks(root)
    root.write(str(target), encoding='UTF-8', xml_declaration=True)
    if set(markers)-matched:
        raise RuntimeError('Paper SVG slot identity unresolved; keep staging, never publish placeholder artwork')
    return {'path': 'Paper/Figure.svg', 'sha256': digest(target), 'bytes': target.stat().st_size,
            'promoted_image_definitions': promoted,
            'canonical_grayscale_masks': canonical_masks,
            'embedded_raster_images': len(root.xpath('//*[local-name()="image"]'))}


def render_source_canvas(pdf, output, source_size):
    """Render one saved paper figure directly on the fixed original grid.

    A display preview subsequently resized by Pillow loses high-frequency
    source detail. Keep it separate from this declared measurement render.
    This neither registers components nor changes the vector mother.
    """
    import pymupdf as fitz
    if (not isinstance(source_size,(list,tuple)) or len(source_size)!=2
            or any(isinstance(v,bool) or int(v)!=v or v<=0 for v in source_size)):
        raise ValueError('Use the actual original integer canvas dimensions')
    width,height=map(int,source_size);output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with fitz.open(pdf) as doc:
        page=doc[0]
        if abs(height-width*page.rect.height/page.rect.width)>1.01:
            raise ValueError('Paper figure and original canvas aspect ratios disagree; no registration/stretching')
        pix=page.get_pixmap(matrix=fitz.Matrix(width/page.rect.width,height/page.rect.height),alpha=False)
        if (pix.width,pix.height)!=(width,height):
            raise ValueError('Keep exact source-grid sampling; do not resize this measurement render')
        pix.save(output)
    return {'path':output.name,'sha256':digest(output),'size':[width,height],
        'pdf_sha256':digest(pdf),'page':0,'sampling':'direct_saved_pdf_at_fixed_original_canvas',
        'limits':'Measurement/render protocol only; not a drawing gain, native-editing claim or per-component registration.'}


def export(pptx, output, caps, width=2000, base_render=None, source_canvas=None):
    from .tool_router import render_saved
    from .office_bridge import discover
    import pymupdf as fitz
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    caps = dict(caps)
    caps['windows_office'] = caps.get('windows_office') or discover()
    records, index = _masters(pptx, output)
    carrier_receipt, markers = None, {}
    backend = 'saved_host_pdf'
    if index:
        from .common import read_json
        import platform
        carrier = output/'Layout-carrier.pptx'
        planned = output/'Layout-carrier-planned.pptx'
        carrier_receipt, markers = _carrier(pptx, planned, records)
        def payload_key(file):
            with ZipFile(file) as archive:
                return tuple((name,hashlib.sha256(archive.read(name)).hexdigest())
                             for name in sorted(archive.namelist()))
        choices = []
        cached_pdf = output/'layout-render/Final.pdf'
        cached_receipt = output/'layout-render/render.json'
        if cached_pdf.is_file() and cached_receipt.is_file():
            receipt = read_json(cached_receipt)
            cached_carrier = carrier
            if not cached_carrier.is_file() or digest(cached_carrier)!=receipt.get('pptx_hash'):
                job_file = output/'layout-render/job-receipt.json'
                if job_file.is_file():
                    job = read_json(job_file);staging = job.get('staging_directory')
                    if staging:
                        if platform.system()!='Windows' and (':' in staging or staging.startswith('\\')):
                            staging=subprocess.run(['wslpath','-u',staging],check=True,
                                capture_output=True,text=True,stdin=subprocess.DEVNULL).stdout.strip()
                        preserved = Path(staging)/'Input.pptx'
                        if preserved.is_file() and digest(preserved)==receipt.get('pptx_hash'):
                            cached_carrier = output/('Saved-layout-carrier-'+receipt['pptx_hash'][:16]+'.pptx')
                            if not cached_carrier.exists():shutil.copyfile(preserved,cached_carrier)
            choices.append((cached_pdf,cached_carrier,receipt))
        if base_render is not None:
            previous=Path(base_render);prior_carrier=previous.parent.parent/'Layout-carrier.pptx'
            receipt_file=previous.parent/'render.json'
            if previous.is_file() and prior_carrier.is_file() and receipt_file.is_file():
                choices.append((previous,prior_carrier,read_json(receipt_file)))
        reused=None
        for previous,prior_carrier,receipt in choices:
            if (prior_carrier.is_file() and receipt.get('pptx_hash')==digest(prior_carrier)
                    and receipt.get('pdf_hash')==digest(previous)
                    and payload_key(prior_carrier)==payload_key(planned)):
                reused=receipt;base_render=previous
                carrier_receipt['reused_actual_layout']={'pdf_hash':receipt['pdf_hash'],
                    'carrier_sha256':receipt['pptx_hash'],'path':str(prior_carrier),
                    'basis':'Exact hash-bound saved Office PDF and identical named ZIP payloads; timestamps ignored',
                    'scope':'Resume only paper vector conversion. The source drawing, mother, failed records and actual layout remain unchanged.'}
                break
        if reused is None:
            if carrier.exists():
                preserved=output/('Saved-layout-carrier-'+digest(carrier)[:16]+'.pptx')
                if not preserved.exists():shutil.copyfile(carrier,preserved)
            planned.replace(carrier)
            render_folder=output/'layout-render'
            if render_folder.exists():
                render_folder=output/('layout-render-'+digest(carrier)[:16])
                number=1
                while render_folder.exists():
                    render_folder=output/('layout-render-'+digest(carrier)[:16]+'-'+str(number));number+=1
            rendered=render_saved(carrier,render_folder,caps,width)
            base_render=render_folder/'Final.pdf'
        else:rendered=reused
        backend=rendered.get('backend','declared_renderer')
    elif base_render is None:
        rendered = render_saved(pptx, output/'layout-render', caps, width)
        base_render = output/'layout-render/Final.pdf'
        backend = rendered.get('backend', 'declared_renderer')
    else:
        receipt_file = Path(base_render).parent/'render.json'
        if receipt_file.is_file():
            from .common import read_json
            backend = read_json(receipt_file).get('backend', backend)
    pdf = output/'Figure.pdf'
    promoted, ambiguous, matched = 0, 0, set()
    vector_backends = set()
    with fitz.open(base_render) as doc:
        work, seen = [], set()
        for page in doc:
            for item in page.get_image_info(hashes=True, xrefs=True):
                xref = item.get('xref')
                if not xref or xref in seen:
                    continue
                seen.add(xref)
                match = _payload_choice(doc.extract_image(xref)['image'], records, markers)
                if not match:
                    continue
                sha, blob = match
                work.append((xref, sha, blob))
        cache = {}
        for xref, sha, blob in work:
            if sha not in cache:
                from .source_gradients import bounded_pdf_gradients
                pdf_blob, gradient_receipt = bounded_pdf_gradients(blob)
                try:
                    import cairosvg
                except (ImportError, OSError):
                    with fitz.open(stream=pdf_blob,filetype='svg') as vector_document:
                        content = vector_document.convert_to_pdf()
                    vector_backends.add('MuPDF')
                else:
                    from .source_mesh import carrier_svg, restore_mesh
                    mesh_blob, mesh_plan = carrier_svg(blob)
                    content = cairosvg.svg2pdf(bytestring=mesh_blob if mesh_plan else pdf_blob)
                    if mesh_plan:
                        with fitz.open(stream=content, filetype='pdf') as mesh_pdf:
                            mesh_receipt = restore_mesh(mesh_pdf, mesh_plan)
                            content = mesh_pdf.tobytes(garbage=2, deflate=True)
                        vector_backends.add('source_RGB_vector_mesh')
                    vector_backends.add('CairoSVG')
                with fitz.open(stream=content, filetype='pdf') as master_pdf:
                    box = master_pdf[0].rect
                    temp = doc.new_page(width=box.width, height=box.height)
                    form = temp.show_pdf_page(temp.rect, master_pdf, 0)
                    cache[sha] = (form, box.width, box.height)
                    doc.delete_page(len(doc)-1)
            form, w, h = cache[sha]
            doc.update_object(xref, f'<< /Type /XObject /Subtype /Form /FormType 1 /BBox [0 0 1 1] /Resources << /XObject << /VEC {form} 0 R >> >> >>')
            doc.update_stream(xref, f'q {1/w:.12g} 0 0 {1/h:.12g} 0 0 cm /VEC Do Q'.encode())
            promoted += 1
            matched.add(sha)
        if set(markers)-matched:
            raise RuntimeError('Paper PDF slot identity unresolved; keep staging, never publish placeholder artwork')
        # Dense source gradients create many small PDF function objects.
        # Remove unused objects and compact xrefs without quadratic duplicate
        # comparisons. Serialization does not change the vector content.
        staging_pdf = pdf.with_name(pdf.stem + '.writing.pdf')
        # Office can embed entire CJK families. Preserve used native glyphs
        # through MuPDF's subsetter; no font replacement or text relayout.
        font_subset = _subset_used_fonts(doc)
        doc.save(staging_pdf, garbage=2, deflate=True)
        staging_pdf.replace(pdf)
    with fitz.open(pdf) as doc:
        raster_images = sum(len(page.get_images()) for page in doc)
        page = doc[0]
        page.get_pixmap(matrix=fitz.Matrix(width/page.rect.width, width/page.rect.width)).save(output/'Preview.png')
    source_preview=(render_source_canvas(pdf,output/'Preview-source-canvas.png',source_canvas)
                    if source_canvas is not None else None)
    # Convert the small carrier, then replace its reusable image definitions;
    # avoid expanding every colour run through PDF -> SVG again.
    svg = _vector_svg(base_render, output/'Figure.svg', records, markers)
    result = {'status': 'EXPORTED_SAVED_ARTWORK', 'source_pptx_sha256': digest(pptx),
              'svg_masters': len(index), 'promoted_image_resources': promoted,
              'pdf': {'path': 'Paper/Figure.pdf', 'sha256': digest(pdf), 'bytes': pdf.stat().st_size,
                      'embedded_raster_images': raster_images}, 'svg': svg,
              'renderer': backend+' saved layout plus compact SVG vector masters',
              'carrier': carrier_receipt, 'ambiguous_image_resources': ambiguous,
              'vector_resource_backends': sorted(vector_backends),
              'source_canvas_preview':source_preview,
              'font_embedding':font_subset,
              'limits': 'Native saved layout/image transforms and paint order retained. Unmatched or ambiguous images remain raster and are counted. Export is not a native editing-operation claim.'}
    write_json(output/'Export.json', result)
    return result
