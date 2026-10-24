"""Finite editable shape shadow/soft-edge parameters; no inferred 3D truth."""
import math
import re
from lxml import etree as E
from .mathml import NS


def validate(style):
    shadow=style.get('shadow_effect')
    if shadow is not None:
        if (not isinstance(shadow,dict) or set(shadow)-{'colour','opacity','blur_pt','offset_pt','rotate_with_shape'} or
                not re.fullmatch('[0-9A-Fa-f]{6}',shadow.get('colour',''))):
            raise ValueError('Native shadow needs colour, opacity, blur_pt and offset_pt')
        if type(shadow.get('opacity')) not in (int,float) or not 0<=shadow['opacity']<=1:
            raise ValueError('Bounded native shadow opacity required')
        if type(shadow.get('blur_pt')) not in (int,float) or not 0<=shadow['blur_pt']<=36:
            raise ValueError('Bounded native shadow blur required')
        offset=shadow.get('offset_pt')
        if not isinstance(offset,list) or len(offset)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>72 for v in offset):
            raise ValueError('Bounded two-axis native shadow offset required')
        if 'rotate_with_shape' in shadow and type(shadow['rotate_with_shape']) is not bool:
            raise ValueError('Explicit native shadow rotation flag required')
    if 'soft_edge_pt' in style and (type(style['soft_edge_pt']) not in (int,float) or not 0<=style['soft_edge_pt']<=6):
        raise ValueError('Soft edge must preserve the observed shape within 0..6 points')


def apply(shape,style):
    if not style.get('shadow_effect') and 'soft_edge_pt' not in style:return
    validate(style);props=shape._element.find('p:spPr',NS)
    if props is None:raise ValueError('Native material effects require editable shape properties')
    effects=props.find('a:effectLst',NS)
    if effects is None:
        effects=E.Element('{'+NS['a']+'}effectLst')
        before=next((i for i,item in enumerate(props) if E.QName(item).localname in ('scene3d','sp3d','extLst')),len(props))
        props.insert(before,effects)
    shadow=style.get('shadow_effect')
    if shadow:
        for old in effects.findall('a:outerShdw',NS):effects.remove(old)
        dx,dy=shadow['offset_pt']
        node=E.SubElement(effects,'{'+NS['a']+'}outerShdw',blurRad=str(round(shadow['blur_pt']*12700)),
                          dist=str(round(math.hypot(dx,dy)*12700)),dir=str(round((math.degrees(math.atan2(dy,dx))%360)*60000)),
                          algn='ctr',rotWithShape='1' if shadow.get('rotate_with_shape',True) else '0')
        colour=E.SubElement(node,'{'+NS['a']+'}srgbClr',val=shadow['colour'].upper())
        E.SubElement(colour,'{'+NS['a']+'}alpha',val=str(round(shadow['opacity']*100000)))
    if 'soft_edge_pt' in style:
        for old in effects.findall('a:softEdge',NS):effects.remove(old)
        E.SubElement(effects,'{'+NS['a']+'}softEdge',rad=str(round(style['soft_edge_pt']*12700)))
    order={'blur':0,'fillOverlay':1,'glow':2,'innerShdw':3,'outerShdw':4,'prstShdw':5,'reflection':6,'softEdge':7}
    effects[:]=sorted(effects,key=lambda item:order.get(E.QName(item).localname,99))
