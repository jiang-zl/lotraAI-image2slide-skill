"""Compact source-conditioned 2.5D camera artwork; no bitmap or 3D dependency."""
import math
from pathlib import Path
from .common import identity, digest


def camera_svg(parameters):
    kind=parameters.get('kind', 'security_camera')
    if kind not in ('security_camera', 'ptz_sensor'):
        raise ValueError('Observed camera subtype is required')
    blue=parameters.get('tone')=='blue'
    radio=parameters.get('radio', True)
    mount=parameters.get('mount', 'pedestal' if blue else 'wall')
    if mount not in ('wall','pedestal'):
        raise ValueError('Observed mount type is required')
    body=('#95d7eb','#438ba8','#245669') if blue else ('#e4e9ea','#b0bec4','#87969f')
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="174" height="130" viewBox="0 0 174 130">',
      '<defs>',
      f'<linearGradient id="body" x1="0" y1="0" x2="0.7" y2="1"><stop stop-color="{body[0]}"/><stop offset=".5" stop-color="{body[1]}"/><stop offset="1" stop-color="{body[2]}"/></linearGradient>',
      '<linearGradient id="hood" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#eef2f2"/><stop offset="1" stop-color="#bac5c9"/></linearGradient>',
      '<linearGradient id="mount" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#c3ccd0"/><stop offset="1" stop-color="#778a96"/></linearGradient>',
      '<radialGradient id="glass" cx=".3" cy=".25" r=".8"><stop stop-color="#4d7f9b"/><stop offset=".5" stop-color="#132b3b"/><stop offset="1" stop-color="#050e15"/></radialGradient>',
      '<radialGradient id="sphere" cx=".3" cy=".15" r=".9"><stop stop-color="#f3f5f7"/><stop offset=".6" stop-color="#bac7d2"/><stop offset="1" stop-color="#667e92"/></radialGradient>',
      '</defs><g stroke-linejoin="round" stroke-linecap="round">']
    if kind=='security_camera':
        mounting = (
          '<g id="mount"><path d="M130 91Q131 87 136 88L151 90L151 128L137 128Q133 128 132 124Z" fill="url(#mount)"/>'
          '<path d="M69 107L141 100L141 118L76 124L70 118Z" fill="#899ca8"/><path d="M72 107L139 101L143 104L76 112Z" fill="#b6c2c8"/>'
          '<path d="M69 82L91 80L88 115Q85 122 75 121L70 118Z" fill="url(#mount)"/><ellipse cx="82" cy="104" rx="4.7" ry="6.3" fill="#73858c"/><ellipse cx="83" cy="103" rx="2.8" ry="4.4" fill="#bec6c8"/></g>'
          if mount=='wall' else
          '<g id="mount"><path d="M70 84L87 85L83 117L69 117Z" fill="url(#mount)"/><ellipse cx="77" cy="120" rx="25" ry="5" fill="#748b98"/><ellipse cx="77" cy="118" rx="24" ry="4" fill="#b8c6ce"/></g>')
        parts += [
          mounting,
          '<path id="housing" d="M31 18L112 18Q126 18 130 31L129 70Q124 89 111 94L58 97L34 80Z" fill="url(#body)"/>',
          '<path id="hood" d="M24 17Q30 10 45 11L111 11Q122 12 130 27L132 40L42 39L19 40Q17 27 24 17Z" fill="url(#hood)"/>',
          '<path d="M43 39L132 40L129 50L60 52Z" fill="#8e9ca5" opacity=".8"/>',
          '<ellipse id="front_rim" cx="37" cy="57" rx="25" ry="33" fill="#d3dee2" stroke="#a2b2bb" stroke-width="1.1"/>',
          '<ellipse id="dark_front" cx="37" cy="57" rx="20.8" ry="29" fill="#243947" stroke="#657c8d" stroke-width="1.1"/>']
        if not blue:
            for ring,count,rx,ry,r in [(0,16,16.4,23.8,2.1),(1,12,10.4,15.6,1.85)]:
                for i in range(count):
                    angle=i*math.tau/count
                    parts.append(f'<ellipse id="led_{ring}_{i}" cx="{37+rx*math.cos(angle):.2f}" cy="{57+ry*math.sin(angle):.2f}" rx="{r:.2f}" ry="{r*1.14:.2f}" fill="#c7e4f1"/>')
        parts += ['<ellipse id="lens" cx="37" cy="57" rx="6.8" ry="9.4" fill="url(#glass)" stroke="#778e9b" stroke-width=".8"/>',
                  '<ellipse cx="34.6" cy="53.5" rx="2" ry="2.7" fill="#81bfdc" opacity=".9"/>']
    else:
        parts += ['<g id="chassis"><path d="M28 59L111 59C111 85 92 113 70 113C46 113 28 86 28 59Z" fill="url(#sphere)" stroke="#526a7c" stroke-width="1"/>',
          '<ellipse cx="70" cy="58" rx="42" ry="5" fill="#dde3e8" stroke="#718796" stroke-width=".8"/>',
          '<ellipse id="upper_turret" cx="70" cy="37" rx="25" ry="24" fill="#529cc5" stroke="#386983" stroke-width="1"/>',
          '<ellipse cx="70" cy="38" rx="15" ry="15" fill="url(#glass)"/><ellipse cx="64" cy="32" rx="4.5" ry="3.8" fill="#82d7ed"/>',
          '<ellipse id="lower_lens" cx="69" cy="82" rx="22" ry="16.5" fill="#467799" stroke="#375973" stroke-width="1"/>',
          '<ellipse cx="69" cy="83" rx="13" ry="10.5" fill="url(#glass)"/><ellipse cx="64" cy="80" rx="4" ry="3" fill="#6fc2df"/></g>']
    if radio:
        parts.append('<g id="radio" fill="none" stroke="#1298ed" stroke-width="2.1">')
        cx,cy=147,35
        for radius in (9,15,21):
            parts.append(f'<path d="M{cx-radius*.71:.2f} {cy+radius*.71:.2f} A{radius} {radius} 0 1 1 {cx+radius*.71:.2f} {cy+radius*.71:.2f}"/>')
        parts.append('<path d="M147 35L147 65M141 66L153 66"/><circle cx="147" cy="35" r="2.5" fill="#1298ed"/></g>')
    parts.append('</g></svg>')
    return ''.join(parts)


def construct(task, component, parameters):
    from .vector_asset import preview
    from .recipes import node
    markup=camera_svg(parameters)
    box=component.get('bbox',component['roi']);ratio=box[2]/box[3]
    width,height=max(174,130*ratio),max(130,174/ratio)
    markup=markup.replace('viewBox="0 0 174 130"',f'viewBox="{(174-width)/2:.3f} {(130-height)/2:.3f} {width:.3f} {height:.3f}"')
    folder=Path(task)/'scratch'/('solid-'+identity({'svg':markup})[:16])
    folder.mkdir(parents=True,exist_ok=True)
    svg=folder/'camera.svg';svg.write_text(markup,encoding='utf-8')
    png=folder/'compatibility.png';info=preview(svg,png,width=960)
    content={'path':svg.relative_to(task).as_posix(),'sha256':digest(svg),
             'preview':{'path':png.relative_to(task).as_posix(),'sha256':digest(png)},
             'edit_level':'component','representation':'svg','source_parts':component['parts'],
             'material':'source-conditioned 2.5D gradients','cost':info}
    return [node(component['id'],'svg',component.get('bbox',component['roi']),content,
                 semantic=component['semantic_class'])]
