"""Conservative explicit native opacity; no empty/transparent fill oracle."""
import math,re
from .mathml import NS

COLORS={'srgbClr','scrgbClr','hslClr','sysClr','schemeClr','prstClr'}


def color_alpha(container):
    colors=[c for c in container if c.tag.split('}')[-1] in COLORS]
    if len(colors)!=1:raise ValueError('A native fill needs one explicit resolved color declaration')
    color=colors[0];kind=color.tag.split('}')[-1]
    if kind=='srgbClr' and re.fullmatch('[0-9a-fA-F]{6}',color.get('val','')) is None:
        raise ValueError('Invalid native RGB fill')
    if kind=='sysClr' and re.fullmatch('[0-9a-fA-F]{6}',color.get('lastClr','')) is None:
        raise ValueError('Unresolved native system color')
    if kind in ('schemeClr','prstClr') and not color.get('val'):raise ValueError('Unresolved native color')
    if kind=='schemeClr':raise ValueError('Theme-dependent opacity needs actual resource resolution or a host matte')
    if kind in ('scrgbClr','hslClr') and not color.attrib:raise ValueError('Empty native color')
    alpha=100000.
    for child in color:
        op=child.tag.split('}')[-1]
        if op.startswith('alpha') and op not in ('alpha','alphaMod','alphaOff'):
            raise ValueError('Unsupported native opacity transform needs a host observation')
        if op not in ('alpha','alphaMod','alphaOff'):continue
        try:value=float(child.get('val'))
        except (TypeError,ValueError):raise ValueError('Unresolved native opacity transform')
        if not math.isfinite(value):raise ValueError('Nonfinite native opacity transform')
        if op=='alpha':alpha=value
        elif op=='alphaMod':alpha*=value/100000.
        else:alpha+=value
        alpha=max(0.,min(100000.,alpha))
    return alpha/100000.


def opaque_fill(props,gradient=False):
    fill=props.find('a:solidFill',NS) if props is not None else None
    if fill is not None:
        if color_alpha(fill)<1.-1e-12:raise ValueError('Transparent native fill cannot certify opaque physical geometry')
        return 'solid'
    fill=props.find('a:gradFill',NS) if props is not None and gradient else None
    if fill is not None:
        stops=fill.findall('a:gsLst/a:gs',NS)
        if len(stops)<2 or any(color_alpha(stop)<1.-1e-12 for stop in stops):
            raise ValueError('Gradient anchor needs explicit opaque stops')
        return 'gradient'
    raise ValueError('Explicit opaque native fill required; unsupported paint needs an actual owner matte')
