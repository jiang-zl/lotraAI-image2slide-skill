"""Compact vector packaging of actual source-conditioned colour boundaries.

Geometry stays on disk and becomes one semantic SVG component. Internal colour
patch edits are deliberately traded for size; the source/parts stay independent.
"""
from pathlib import Path
from xml.sax.saxutils import escape
from .common import read_json, digest, write_json, identity


def svg_from_layers(task, folder, layers, size, *, overlap=0., lineage=None,display_size=None,pixel_exact=False):
    from .vector_asset import preview
    width, height = size
    # Geometry reuse and rendered representation have different dependencies.
    # Never overwrite a selected asset when only seam/preview settings change.
    representation_key=identity({'layers':[{'sha256':i['sha256'],'fill':i['fill']} for i in layers],
        'size':size,'overlap':overlap,'display_size':display_size,
        'pixel_exact':pixel_exact,'lineage':lineage,'renderer':digest(Path(__file__)),
        'codec':digest(Path(__file__).with_name('representation_codec.py'))})[:16]
    folder=Path(folder)/('representation-'+representation_key)
    folder.mkdir(exist_ok=True)
    svg = folder/'artwork.svg'
    pieces = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
              f'viewBox="0 0 {width} {height}"><desc>{escape(str(lineage or {}))}</desc>']
    command_count = 0
    def number(value):
        return ('%.1f'%value).rstrip('0').rstrip('.')
    for item in layers:
        data = read_json(Path(task)/item['path'])
        sequences = []
        for contour in data['contours']:
            points = contour.get('points')
            if points is not None:
                if not points:
                    continue
                xy=[(x*width,y*height) for x,y in points]
                seq = 'M'+number(xy[0][0])+','+number(xy[0][1])
                rectangle=(len(xy)==4 and abs(xy[0][1]-xy[1][1])<1e-6 and abs(xy[1][0]-xy[2][0])<1e-6
                           and abs(xy[2][1]-xy[3][1])<1e-6 and abs(xy[3][0]-xy[0][0])<1e-6)
                if rectangle:
                    dx,dy=xy[1][0]-xy[0][0],xy[2][1]-xy[1][1]
                    seq+='h'+number(dx)+'v'+number(dy)+'h'+number(-dx)
                else:
                    seq += 'L'+' '.join(number(x)+','+number(y) for x,y in xy[1:])
                command_count += len(points)
            else:
                seq = ''
                from .geometry import path_operations
                for name,values in path_operations(contour):
                    op = {'moveTo':'M','lnTo':'L','quadBezTo':'Q','cubicBezTo':'C','close':'Z'}[name]
                    if op == 'Z':
                        seq += 'Z'
                    else:
                        seq += op + ' '.join(f'{p[0]*width:.3f},{p[1]*height:.3f}' for p in values if p)
                    command_count += 1
            if contour.get('closed'):
                seq += 'Z'
            sequences.append(seq)
        stroke = f' stroke="#{item["fill"]}" stroke-width="{overlap:.3f}" stroke-linejoin="round"' if overlap else ''
        rendering=' shape-rendering="crispEdges"' if pixel_exact else ''
        pieces.append(f'<path fill="#{item["fill"]}" fill-rule="evenodd"{stroke}{rendering} d="{" ".join(sequences)}"/>')
    pieces.append('</svg>')
    from .representation_codec import optimize
    encoded,encoding=optimize(''.join(pieces).encode('utf8'),'svg')
    svg.write_bytes(encoded)
    from .representation_codec import D_ATTR,PATH_TAG
    import re
    actual_commands=sum(len(re.findall(rb'[MmLlHhVvCcSsQqTtAaZz]',d))
        for tag in PATH_TAG.findall(encoded) for d in D_ATTR.findall(tag))
    png = Path(folder)/'compatibility.png'
    target_width=min(width*1.3,display_size[0]*2) if display_size else width*1.3
    info = preview(svg, png, width=max(128, min(1200, round(target_width))))
    result = {'path': svg.relative_to(task).as_posix(), 'sha256': digest(svg),
              'preview': {'path': png.relative_to(task).as_posix(), 'sha256': digest(png)},
              'representation': 'svg', 'edit_level': 'component', 'lineage': lineage,
              'encoding':encoding,'cost': {'svg_bytes': svg.stat().st_size, 'path_commands': actual_commands,'original_path_commands':command_count,
                       'layers': len(layers), 'compatibility_bytes': png.stat().st_size}}
    write_json(Path(folder)/'representation.json', result)
    return result
