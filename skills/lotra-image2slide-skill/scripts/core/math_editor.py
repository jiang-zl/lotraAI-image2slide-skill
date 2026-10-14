"""Saved OMML -> LibreOffice Math editor import contract (never plain-text math).

LibreOffice loses a14:m when it shares a paragraph with ordinary runs. A
private rendering copy separates those native spans before the ONE import.
Canonical PPTX bytes and their real OMML are never modified. The Math editor
imports the OMML structure; its own formula serialization is kept intact.
"""
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
from .mathml import NS
from .common import digest, write_json

VERSION='native-math-editor-1.31'


def _style(zone):
    runs=zone.findall('.//m:r/a:rPr',NS)
    if not runs:raise ValueError('Native formula has no explicit math run properties')
    sizes={float(p.get('sz','0'))/100 for p in runs}
    fonts={p.find('a:latin',NS).get('typeface') for p in runs if p.find('a:latin',NS) is not None}
    colors={p.find('a:solidFill/a:srgbClr',NS).get('val') for p in runs if p.find('a:solidFill/a:srgbClr',NS) is not None}
    if len(sizes)!=1 or min(sizes)<=0 or len(fonts)!=1 or len(colors)>1:
        raise ValueError('CAPABILITY_BLOCKED: mixed base fonts/sizes in one math zone require an explicit editor contract')
    return {'size':sizes.pop(),'font':fonts.pop(),'color':next(iter(colors),'17324D')}


def prepare(pptx, output):
    """Read every math zone from the actual ZIP, then create one transient input."""
    output=Path(output);groups=[];parts={}
    with ZipFile(pptx) as src:
        slides=sorted(n for n in src.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml'))
        for slide_name in slides:
            root=E.fromstring(src.read(slide_name))
            fresh_id=max([int(p.get('id','0')) for p in root.findall('.//p:cNvPr',NS)]+[1])+1
            for shape in list(root.findall('.//p:sp',NS)):
                if shape.find('.//m:oMath',NS) is None:continue
                owner=shape.find('p:nvSpPr/p:cNvPr',NS).get('name')
                xf=shape.find('p:spPr/a:xfrm',NS)
                if xf is None or any(int(xf.get(k,'0')) for k in ('rot','flipH','flipV')):
                    raise ValueError('CAPABILITY_BLOCKED: rotated math needs explicit editor layout support')
                body=shape.find('p:txBody',NS);bodypr=body.find('a:bodyPr',NS)
                paragraphs=body.findall('a:p',NS)
                mixed=any(p.find('a:r',NS) is not None for p in paragraphs) or len(paragraphs)>1
                group={'owner':owner,'slide':slide_name,'rows':[],'valign':bodypr.get('anchor','t'),
                       'margins':[int(bodypr.get(k,'0'))/360 for k in ('lIns','rIns','tIns','bIns')],
                       'mixed':mixed}
                parent=shape.getparent();index=parent.index(shape);replacement=[]
                for pi,para in enumerate(paragraphs):
                    pp=para.find('a:pPr',NS)
                    row={'align':pp.get('algn','l') if pp is not None else 'l','segments':[]}
                    for segment in para:
                        kind=E.QName(segment).localname
                        if kind in ('pPr','endParaRPr'):continue
                        if kind not in ('r','m'):raise ValueError('CAPABILITY_BLOCKED: unsupported mixed formula paragraph token '+kind)
                        name='__lotra_render_'+str(fresh_id)
                        clone=deepcopy(shape);props=clone.find('p:nvSpPr/p:cNvPr',NS)
                        props.set('name',name);props.set('id',str(fresh_id));fresh_id+=1
                        tx=clone.find('p:txBody',NS)
                        for child in list(tx):
                            if E.QName(child).localname=='p':tx.remove(child)
                        rowxml=E.SubElement(tx,'{'+NS['a']+'}p')
                        ppr=E.SubElement(rowxml,'{'+NS['a']+'}pPr');ppr.set('algn','l')
                        copied=deepcopy(segment)
                        # A pure native math shape is recognized by LO's editor.
                        rowxml.append(copied)
                        item={'name':name,'math':kind=='m'}
                        if item['math']:item.update(_style(segment))
                        else:
                            item['text']=''.join(segment.itertext())
                            pr=segment.find('a:rPr',NS)
                            if pr is None:raise ValueError('Mixed math text requires explicit native run style')
                            item.update(size=float(pr.get('sz'))/100,
                                fonts={s:pr.find('a:'+s,NS).get('typeface') for s in ('latin','ea','cs') if pr.find('a:'+s,NS) is not None},
                                bold=pr.get('b','0') in ('1','true'),italic=pr.get('i','0') in ('1','true'))
                        row['segments'].append(item);replacement.append(clone)
                    if not row['segments']:raise ValueError('Empty mixed math row is unsupported')
                    group['rows'].append(row)
                parent.remove(shape)
                for offset,clone in enumerate(replacement):parent.insert(index+offset,clone)
                groups.append(group)
            parts[slide_name]=E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
        target=output/'editor-input.pptx'
        with ZipFile(target,'w',ZIP_DEFLATED) as dst:
            for info in src.infolist():dst.writestr(info,parts.get(info.filename,src.read(info.filename)))
    plan={'version':VERSION,'canonical_pptx_hash':digest(pptx),'editor_input_hash':digest(target),'groups':groups}
    write_json(output/'editor-plan.json',plan)
    return target,plan
