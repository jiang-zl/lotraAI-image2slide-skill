"""Pure SVG component resources, Office embedding, and bounded preview caching."""
import hashlib
import json
import re
from pathlib import Path
from lxml import etree as E
from .common import digest, safe_path, write_json

SVG_NS = 'http://www.w3.org/2000/svg'
ASVG_NS = 'http://schemas.microsoft.com/office/drawing/2016/SVG/main'
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
EXT_URI = '{96DAC541-7B7A-43D3-8B79-37D633B846F1}'
MASTER_NS = 'https://lotra.ai/ns/vector-master/1'
MASTER_EXT_URI = '{6F5CE5D9-A70B-4D54-91EF-62F1BF3B2C38}'
MASTER_REL = 'https://lotra.ai/relationships/vector-master/1'


def inspect_svg(path):
    data=path if isinstance(path,bytes) else Path(path).read_bytes()
    if len(data) > 32*1024*1024:
        raise ValueError('SVG component exceeds bounded resource size')
    root = E.fromstring(data, E.XMLParser(resolve_entities=False, no_network=True))
    if E.QName(root).localname != 'svg':
        raise ValueError('SVG root required')
    tags = {}; raster = 0; commands = 0
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        tag = E.QName(node).localname
        tags[tag] = tags.get(tag, 0) + 1
        if tag in ('script', 'foreignObject', 'animate', 'animateTransform', 'set'):
            raise ValueError('SVG component must be static artwork, not executable content')
        if any(E.QName(key).localname.lower().startswith('on') for key in node.attrib):
            raise ValueError('SVG event handlers are not component data')
        for key, value in node.attrib.items():
            if E.QName(key).localname == 'href' and not value.startswith(('#', 'data:image/')):
                raise ValueError('SVG external resources must be captured as local component data')
            for ref in re.findall(r'url\(\s*[\"\']?([^\)\"\']+)', value):
                if not ref.startswith('#'):
                    raise ValueError('External SVG CSS resources are not permitted')
        if tag == 'style':
            css = ''.join(node.itertext())
            if re.search(r'@import\b', css, re.I):
                raise ValueError('SVG CSS imports must be captured locally')
            if any(not value.strip().startswith('#') for value in
                   re.findall(r'url\(\s*[\"\']?([^\)\"\']+)', css)):
                raise ValueError('External SVG stylesheet resources are not permitted')
        if tag == 'image':
            raster += 1
        if tag == 'path':
            commands += len(re.findall('[MmLlHhVvCcSsQqTtAaZz]', node.get('d', '')))
    box = root.get('viewBox', '').replace(',', ' ').split()
    if len(box) != 4 or float(box[2]) <= 0 or float(box[3]) <= 0:
        raise ValueError('A positive SVG viewBox is required')
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'viewbox': list(map(float, box)), 'elements': tags, 'path_commands': commands,
            'representation': 'svg' if not raster else 'hybrid_svg', 'raster_images': raster,
            'effects': [key for key in tags if key.startswith('fe')]}


def preview(svg, destination, width=1200, height=None):
    """Version-bound local preview; the SVG stays authoritative vector data."""
    from . import svg_backend
    info = inspect_svg(svg)
    destination = Path(destination)
    binding = destination.with_suffix(destination.suffix+'.json')
    expected = {'svg': info['sha256'], 'width': width, 'adapter': svg_backend.backend()}
    if height is not None:expected['height']=height
    if destination.exists() and binding.exists():
        old = json.loads(binding.read_text())
        if all(old.get(k) == v for k, v in expected.items()) and old.get('png') == digest(destination):
            return info
    destination.parent.mkdir(parents=True, exist_ok=True)
    svg_backend.svg2png(bytestring=Path(svg).read_bytes(), write_to=str(destination), output_width=width,output_height=height)
    write_json(binding, {**expected, 'png': digest(destination)})
    return info


def validate(content, base):
    svg = safe_path(base, content['path'])
    if digest(svg) != content['sha256']:
        raise ValueError('SVG component resource changed')
    info = inspect_svg(svg)
    if info['raster_images']:
        raise ValueError('Pure SVG representation cannot conceal bitmap images; use a declared raster/hybrid route')
    fallback = safe_path(base, content['preview']['path'])
    if digest(fallback) != content['preview']['sha256']:
        raise ValueError('SVG compatibility preview changed')
    mode=content.get('office_display','svg')
    if mode not in ('svg','preview'):raise ValueError('Explicit Office display mode required')
    if mode=='preview':
        evidence=content.get('display_evidence') or {}
        if not content.get('display_reason') or not evidence.get('path') or not evidence.get('sha256'):
            raise ValueError('Compatibility display needs captured failure/quality evidence and a reason')
        if digest(safe_path(base,evidence['path']))!=evidence['sha256']:
            raise ValueError('Compatibility evidence changed')
    return svg, fallback, info


def master_bytes(blob, compression=None, expected=None):
    if compression in (None,'none'):data=blob
    elif compression=='gzip':
        import gzip,io
        with gzip.GzipFile(fileobj=io.BytesIO(blob)) as stream:data=stream.read(32*1024*1024+1)
    else:raise ValueError('Unknown vector-master compression')
    info=inspect_svg(data)
    if info['raster_images'] or expected and info['sha256']!=expected:
        raise ValueError('Pure vector-master payload/digest changed')
    return data


def embed(collection, svg, fallback, box, cache, *, content=None):
    from pptx.opc.package import Part
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    from pptx.oxml.xmlchemy import OxmlElement
    pic = collection.add_picture(str(fallback), *box)
    sha = digest(svg);mode=(content or {}).get('office_display','svg');key=(sha,mode)
    part = cache.get(key)
    if part is None:
        package = pic.part.package
        data=Path(svg).read_bytes()
        name,ctype=('/ppt/media/vector%d.svg','image/svg+xml') if mode=='svg' else ('/ppt/lotra/vector%d.svgz','application/gzip')
        if mode=='preview':
            import gzip
            data=gzip.compress(data,compresslevel=9,mtime=0)
        part = Part(package.next_partname(name),ctype,package,blob=data)
        cache[key] = part
    rid = pic.part.relate_to(part,RT.IMAGE if mode=='svg' else MASTER_REL)
    blip = pic._element.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}blip')
    extlst = blip.find('{http://schemas.openxmlformats.org/drawingml/2006/main}extLst')
    if extlst is None:
        extlst = OxmlElement('a:extLst'); blip.append(extlst)
    mode=(content or {}).get('office_display','svg')
    ext = OxmlElement('a:ext'); ext.set('uri', EXT_URI if mode=='svg' else MASTER_EXT_URI)
    if mode=='svg':
        vector=E.SubElement(ext,'{'+ASVG_NS+'}svgBlip',nsmap={'asvg':ASVG_NS})
    else:
        vector=E.SubElement(ext,'{'+MASTER_NS+'}vectorMaster',nsmap={'lotra':MASTER_NS})
        vector.set('sha256',sha);vector.set('display','compatibility_preview');vector.set('compression','gzip')
    vector.set('{'+R_NS+'}embed', rid); extlst.append(ext)
    description={'representation':'svg' if mode=='svg' else 'raster_preview_with_svg_master',
                 'sha256':sha,'edit_level':'component','paper_master':'pure_svg'}
    if mode=='preview':description.update(reason=content['display_reason'],evidence=content['display_evidence'])
    pic._element.find('.//{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr').set(
        'descr', json.dumps({'lotra':description}))
    return pic
