"""Source-controlled typography on actual editable Office Math nodes."""
import math,re
from .mathml import NS,el

FIELDS={'font_size_pt','font_family','bold','italic','color'}

def validate(value):
    if not isinstance(value,dict) or set(value)-(FIELDS|{'source_evidence'}):raise ValueError('Unknown mathematical typography property')
    if 'source_evidence' in value and not isinstance(value['source_evidence'],str):raise ValueError('Typography provenance must remain text data')
    if 'font_size_pt' in value and (isinstance(value['font_size_pt'],bool) or not isinstance(value['font_size_pt'],(int,float)) or not math.isfinite(value['font_size_pt']) or not 4<=value['font_size_pt']<=96):
        raise ValueError('Finite bounded mathematical font size required')
    if 'font_family' in value and (not isinstance(value['font_family'],str) or not value['font_family'].strip()):raise ValueError('Exact mathematical font identity required')
    for field in ('bold','italic'):
        if field in value and type(value[field]) is not bool:raise ValueError('Boolean math style required')
    if 'color' in value and not re.fullmatch('[0-9A-Fa-f]{6}',value['color']):raise ValueError('RGB mathematical color required')
    return value

def apply(zone,typography):
    validate(typography)
    for run in zone.findall('.//m:r',NS):
        props=run.find('a:rPr',NS)
        if props is None:props=el('a:rPr');run.insert(0,props)
        if 'font_size_pt' in typography:props.set('sz',str(round(typography['font_size_pt']*100)))
        if 'font_family' in typography:
            for script in ('latin','ea','cs'):
                face=props.find('a:'+script,NS)
                if face is None:face=el('a:'+script);props.append(face)
                face.set('typeface',typography['font_family'])
        if 'color' in typography:
            for tag in ('solidFill','gradFill','noFill','pattFill'):
                for child in props.findall('a:'+tag,NS):props.remove(child)
            fill=el('a:solidFill');fill.append(el('a:srgbClr',val=typography['color'].upper()));props.insert(0,fill)
        if 'bold' in typography or 'italic' in typography:
            math_props=run.find('m:rPr',NS)
            if math_props is None:math_props=el('m:rPr');run.insert(0,math_props)
            old=math_props.find('m:sty',NS)
            style=old.get('{'+NS['m']+'}val','i') if old is not None else ('p' if math_props.find('m:nor',NS) is not None else 'i')
            bold=typography.get('bold',style in ('b','bi'))
            italic=typography.get('italic',style in ('i','bi'))
            if old is None:old=el('m:sty');math_props.append(old)
            old.set('{'+NS['m']+'}val','bi' if bold and italic else 'b' if bold else 'i' if italic else 'p')
            props.set('b','1' if bold else '0');props.set('i','1' if italic else '0')
    return zone

def check(zone,typography):
    validate(typography)
    runs=zone.findall('.//m:r',NS);failures=[]
    if typography and not runs:failures.append({'property':'math_runs','reason':'required_unmeasured'})
    for index,run in enumerate(runs):
        props=run.find('a:rPr',NS)
        normal=run.find('m:rPr/m:nor',NS)
        text=run.findtext('m:t',namespaces=NS) or ''
        if (normal is not None and normal.get('{'+NS['m']+'}val','1') in ('1','true','on')
                and re.fullmatch(r'[0-9., ]+',text)
                and run.xpath('ancestor::m:sub | ancestor::m:sup | ancestor::m:lim',namespaces=NS)):
            failures.append({'run':index,'property':'script_render_mode','reason':'upright_numeric_script_is_normal_text_not_mathematical_run'})
        for field,expected in typography.items():
            if field not in FIELDS:continue
            actual=None
            if props is not None:
                if field=='font_size_pt':actual=float(props.get('sz',0))/100
                elif field=='font_family':
                    face=props.find('a:latin',NS);actual=face.get('typeface') if face is not None else None
                elif field=='color':
                    color=props.find('a:solidFill/a:srgbClr',NS);actual=color.get('val') if color is not None else None;expected=expected.upper()
                elif field in ('bold','italic'):
                    style=run.find('m:rPr/m:sty',NS)
                    actual=style.get('{'+NS['m']+'}val') in (('b','bi') if field=='bold' else ('i','bi')) if style is not None else None
            good=abs(actual-expected)<=.02 if field=='font_size_pt' and actual is not None else actual==expected
            if not good:failures.append({'run':index,'property':field,'expected':expected,'actual':actual})
    return {'passed':not failures,'failures':failures,'scope':'Actual serialized OMML properties; visible layout remains independently rendered and checked'}
