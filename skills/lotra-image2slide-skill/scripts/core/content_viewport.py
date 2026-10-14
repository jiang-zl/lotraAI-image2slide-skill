"""Derive clean, immutable media from an evidenced semantic content window.

No background-colour or alpha heuristic decides which source pixels belong.
"""
import copy
import math
from pathlib import Path
from lxml import etree as E
from .common import digest, identity, safe_path, write_json

SVG = 'http://www.w3.org/2000/svg'


def cover_window(window, aspect, preserve=()):
    x, y, w, h = map(float, window)
    if not all(math.isfinite(v) for v in (x, y, w, h, aspect)) or min(w, h, aspect) <= 0:
        raise ValueError('Finite positive content window/aspect required')
    cw, ch = min(w, h*aspect), min(h, w/aspect)
    crop = [x+(w-cw)/2, y+(h-ch)/2, cw, ch]
    for box in preserve:
        if (box[0] < crop[0]-1e-8 or box[1] < crop[1]-1e-8 or
                box[0]+box[2] > crop[0]+crop[2]+1e-8 or box[1]+box[3] > crop[1]+crop[3]+1e-8):
            raise ValueError('Cover would cut protected semantic content; revise the frame/plan')
    return crop


def normalize(content, kind, declaration, box, base):
    """Return a new media declaration; originals are never changed in place."""
    from PIL import Image
    source = safe_path(base, content['path'])
    if digest(source) != content['sha256'] or declaration['asset_sha256'] != content['sha256']:
        raise ValueError('Content window must bind the actual immutable source asset')
    # Equivalent integer-native frames can arrive through two affine paths.
    # Canonical decimal precision is far below one native unit; it prevents
    # different immutable SVG identities from binary floating-point tails.
    window = declaration['window']; aspect = float(format(box[2]/box[3], '.12g'))
    crop = cover_window(window, aspect, declaration.get('preserve_regions', []))
    if kind == 'svg':
        from .vector_asset import inspect_svg, preview
        info = inspect_svg(source)
        tree = E.fromstring(source.read_bytes())
        view = [float(v) for v in tree.get('viewBox', '').replace(',', ' ').split()]
        if len(view) != 4:
            raise ValueError('Semantic SVG crop requires an explicit viewBox')
    elif kind == 'photo':
        with Image.open(source) as image:
            view = [0., 0., float(image.width), float(image.height)]
    else:
        raise ValueError('Content windows apply only to independent SVG/photo owners')
    if (window[0] < view[0] or window[1] < view[1] or window[0]+window[2] > view[0]+view[2]+1e-8
            or window[1]+window[3] > view[1]+view[3]+1e-8):
        raise ValueError('Semantic content window outside the source asset')
    recipe = {'source': content['sha256'], 'kind': kind, 'window': window, 'crop': crop,
              'aspect': aspect, 'operator': 'content-viewport-1', 'code': digest(Path(__file__))}
    key = identity(recipe); directory = safe_path(base, 'scratch/content-viewports/'+key)
    directory.mkdir(parents=True, exist_ok=True)
    result = copy.deepcopy(content)
    if kind == 'svg':
        svg = directory/'content.svg'
        # Explicit clip survives consumers that unwrap the root SVG viewBox.
        clean = copy.deepcopy(tree); children = list(clean)
        for child in children:
            clean.remove(child)
        clean.set('viewBox', ' '.join(format(v, '.12g') for v in crop))
        clean.set('width', format(crop[2], '.12g')); clean.set('height', format(crop[3], '.12g'))
        # The cover crop already has the exact target aspect. A second SVG
        # meet operation can add a fractional transparent strip when the
        # compatibility raster's integer height is rounded by Cairo/Office.
        # Map this proven crop to the complete viewport; do not letterbox it.
        clean.set('preserveAspectRatio', 'none'); clean.set('overflow', 'hidden')
        defs = E.SubElement(clean, '{'+SVG+'}defs')
        clip = E.SubElement(defs, '{'+SVG+'}clipPath', id='lotra-content-'+key[:20], clipPathUnits='userSpaceOnUse')
        E.SubElement(clip, '{'+SVG+'}rect', x=str(crop[0]), y=str(crop[1]), width=str(crop[2]), height=str(crop[3]))
        group = E.SubElement(clean, '{'+SVG+'}g', {'clip-path': 'url(#lotra-content-'+key[:20]+')'})
        for child in children:
            group.append(child)
        data = E.tostring(clean, xml_declaration=True, encoding='UTF-8')
        if svg.exists() and svg.read_bytes() != data:
            raise ValueError('Immutable normalized SVG changed')
        if not svg.exists():
            svg.write_bytes(data)
        png = directory/'content.png'
        sample_width=max(384,min(1200,math.ceil(box[2]*4)))
        sample_height=max(1,math.ceil(sample_width/aspect))
        if sample_width*sample_height>64000000:raise ValueError('Normalized content preview exceeds bounded sampling resources')
        # Both integer raster axes must be explicit. Width-only Cairo output
        # allocates ceil(height) pixels but clips at fractional height, leaving
        # the final row partially transparent even for a solid source window.
        preview(svg,png,width=sample_width,height=sample_height)
        result.update(path=svg.relative_to(Path(base)).as_posix(), sha256=digest(svg),
                      preview={'path': png.relative_to(Path(base)).as_posix(), 'sha256': digest(png)})
        native_crop = [0., 0., 0., 0.]
    else:
        # Integer crop removes the semantic gutter losslessly. Native cover
        # then preserves aspect without inventing image detail by resampling.
        x0, y0 = math.ceil(window[0]), math.ceil(window[1])
        x1, y1 = math.floor(window[0]+window[2]), math.floor(window[1]+window[3])
        if min(x1-x0, y1-y0) < 1:
            raise ValueError('No complete observed pixel remains in the content window')
        image_path = directory/'content.png'
        with Image.open(source) as image:
            image.crop((x0, y0, x1, y1)).save(image_path)
        adjusted = cover_window([0., 0., x1-x0, y1-y0], aspect,
                                [[p[0]-x0, p[1]-y0, p[2], p[3]] for p in declaration.get('preserve_regions', [])])
        native_crop = [adjusted[0]/(x1-x0), adjusted[1]/(y1-y0),
                       1-(adjusted[0]+adjusted[2])/(x1-x0), 1-(adjusted[1]+adjusted[3])/(y1-y0)]
        result.update(path=image_path.relative_to(Path(base)).as_posix(), sha256=digest(image_path))
    result['viewport'] = {'schema': 'content-viewport-1', **recipe, 'native_crop': native_crop,
                          'normalized_sha256': result['sha256'], 'semantic_evidence': declaration['evidence']}
    write_json(directory/'derivation.json', result['viewport'])
    return result


def apply_crop(picture, content):
    crop = content.get('viewport', {}).get('native_crop')
    if crop is not None:
        picture.crop_left, picture.crop_top, picture.crop_right, picture.crop_bottom = crop
