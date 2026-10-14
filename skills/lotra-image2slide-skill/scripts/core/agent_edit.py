"""Explicit local user edits on the authoritative saved PPTX.

Freeze intent and property grants before tools run. Native fields are merged
onto that package; raster proposals are deterministically masked onto its
existing pixels. Review the affected neighbourhood, never restart whole QA.
"""
import copy
import math
import uuid
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
from .common import digest, identity, read_json, safe_path, write_json
from .mathml import NS
from .native_commit import _nodes, _sp

FIELDS={'text_content','text_body','equation','geometry','fill_color','line_color',
        'style.font_size','style.font','style.bold','style.italic','style.color',
        'style.line_width','style.rotation','bbox.left','bbox.top','bbox.width','bbox.height',
        'group_translate','connector'}
FIELDS.update({'style.line_spacing_pt','style.char_spacing_pt','style.align','style.valign'})
FIELDS.add('paint_order')


def _shape(task,state,name):
    from .saved_components import inventory
    pptx=safe_path(task,state['selected']['pptx']['path'])
    rows=[r for r in inventory(pptx)['objects'] if r['name']==name]
    if len(rows)!=1:raise ValueError('Select one actual saved shape name before editing')
    return pptx,rows[0]


def freeze(task,state,request):
    if not state.get('selected') or state.get('packet') or state.get('active_candidate'):
        raise ValueError('Finish the pending drawing action before a new user edit')
    if request.get('baseline_hash')!=state['selected']['pptx']['sha256']:
        raise ValueError('Local edit grant must bind the current authoritative PPTX')
    intent=request.get('user_intent',{})
    if not intent.get('reference') or not intent.get('text'):
        raise ValueError('Record the actual user request and reference before authorizing tools')
    grants=request.get('allowed_changes',{})
    raster=request.get('raster')
    if bool(grants)==bool(raster):raise ValueError('Choose one native or permitted picture edit')
    edit_id='edit-'+uuid.uuid4().hex[:12];folder=Path(task)/'scratch'/edit_id;folder.mkdir()
    names=list(grants) if grants else [raster['object_id']]
    boxes=[];descriptors=[]
    for name in names:
        pptx,row=_shape(task,state,name);boxes.append(row['bbox_emu']);descriptors.append(row)
        if grants:
            fields=grants[name]
            if not isinstance(fields,list) or not fields or len(fields)!=len(set(fields)) or not set(fields)<=FIELDS:
                raise ValueError('Use bounded exact property grants, never style/content wildcards')
    from pptx import Presentation
    deck=Presentation(pptx);scale=state['source_size'][0]/deck.slide_width
    x=min(b[0] for b in boxes)*scale;y=min(b[1] for b in boxes)*scale
    w=max((b[0]+b[2])*scale for b in boxes)-x;h=max((b[1]+b[3])*scale for b in boxes)-y
    size=state['source_size'];margin=12
    roi=[max(0,x-margin),max(0,y-margin),0,0]
    roi[2]=min(size[0],x+w+margin)-roi[0];roi[3]=min(size[1],y+h+margin)-roi[1]
    proof={'schema':'lotra-user-edit-1','id':edit_id,'baseline_hash':request['baseline_hash'],
           'user_intent':intent,'allowed_changes':grants,'check_roi':roi,
           'protection':'all other saved parts, owners and ungranted properties',
           'descriptors':descriptors,'attempts':0}
    if raster:
        if descriptors[0]['kind']!='pic' or raster.get('layer_kind') not in (
                'illustrative_photo','environment','permitted_raster_layer') or not raster.get('permission_reference'):
            raise ValueError('Raster edit is restricted to an explicitly permitted existing picture')
        from PIL import Image
        import io,numpy as np
        slide=deck.slides[0];element=_nodes(slide._element)[names[0]]
        blip=element.find('p:blipFill/a:blip',NS)
        part=slide.part.related_part(blip.get('{'+NS['r']+'}embed'))
        source=folder/'source.png'
        with Image.open(io.BytesIO(part.blob)) as image:image.convert('RGBA').save(source)
        mask=safe_path(task,raster['allowed_mask']['path'])
        if digest(mask)!=raster['allowed_mask']['sha256']:raise ValueError('Edit mask changed')
        frozen=folder/'allowed-mask.png';frozen.write_bytes(mask.read_bytes())
        with Image.open(frozen) as mask_image:
            with Image.open(source) as source_image:
                if mask_image.mode!='L' or mask_image.size!=source_image.size:
                    raise ValueError('Freeze a grayscale mask in this picture pixel canvas')
            values=np.asarray(mask_image)
            if not np.isin(values,[0,255]).all() or not values.any():raise ValueError('Nonempty binary edit mask required')
        proof['raster']={**raster,'source':{'path':source.relative_to(task).as_posix(),'sha256':digest(source)},
                         'allowed_mask':{'path':frozen.relative_to(task).as_posix(),'sha256':digest(frozen)}}
    file=folder/'authorization.json';write_json(file,proof)
    return {'path':file.relative_to(task).as_posix(),'sha256':digest(file),'id':edit_id,'check_roi':roi}


def _set(node,field,value):
    if field=='paint_order':
        if not isinstance(value,dict) or set(value) not in ({'before'},{'after'}):
            raise ValueError('Paint order needs one named saved sibling anchor')
        side=next(iter(value));parent=node.getparent()
        siblings=[n for n in parent if E.QName(n).localname in ('sp','grpSp','pic','cxnSp','graphicFrame')]
        anchors=[n for n in siblings if n.find('.//p:cNvPr',NS).get('name')==value[side]]
        if len(anchors)!=1 or anchors[0] is node:raise ValueError('A paint anchor is a distinct direct native sibling')
        anchor=anchors[0];parent.remove(node);parent.insert(parent.index(anchor)+(side=='after'),node)
        return
    if field in ('style.line_spacing_pt','style.char_spacing_pt'):
        if not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError('Finite source-supported text spacing required')
        if field=='style.char_spacing_pt':
            if not -10<=value<=20:raise ValueError('Bounded character spacing')
            for props in node.xpath('.//a:rPr | .//a:defRPr',namespaces=NS):props.set('spc',str(round(value*100)))
        else:
            if not 1<=value<=200:raise ValueError('Bounded exact paragraph pitch')
            for paragraph in node.findall('p:txBody/a:p',NS):
                props=paragraph.find('a:pPr',NS)
                if props is None:props=E.Element('{'+NS['a']+'}pPr');paragraph.insert(0,props)
                for spacing in props.findall('a:lnSpc',NS):props.remove(spacing)
                spacing=E.Element('{'+NS['a']+'}lnSpc');props.insert(0,spacing)
                E.SubElement(spacing,'{'+NS['a']+'}spcPts',val=str(round(value*100)))
        return
    if field=='style.align':
        if value not in ('left','center','right'):raise ValueError('Exact horizontal alignment required')
        for paragraph in node.findall('p:txBody/a:p',NS):
            props=paragraph.find('a:pPr',NS)
            if props is None:props=E.Element('{'+NS['a']+'}pPr');paragraph.insert(0,props)
            props.set('algn',{'left':'l','center':'ctr','right':'r'}[value])
        return
    if field=='style.valign':
        if value not in ('top','middle','bottom'):raise ValueError('Exact vertical alignment required')
        node.find('p:txBody/a:bodyPr',NS).set('anchor',{'top':'t','middle':'ctr','bottom':'b'}[value]);return
    if field in ('text_content','text_body','equation','geometry'):
        if field=='text_content':
            texts=node.findall('.//a:t',NS);values=value if isinstance(value,list) else [value]
            if len(texts)!=len(values) or any(not isinstance(v,str) for v in values):
                raise ValueError('Preserve run topology; use an explicit text_body grant for reflow')
            for text,new in zip(texts,values):text.text=new
            return
        if not isinstance(value,str) or len(value)>100000:raise ValueError('Bounded native XML data required')
        fresh=E.fromstring(value.encode(),E.XMLParser(resolve_entities=False,no_network=True))
        tag={'text_body':'txBody','equation':'m','geometry':'custGeom'}[field]
        if E.QName(fresh).localname!=tag or fresh.xpath('.//@r:embed | .//@r:link',namespaces=NS):
            raise ValueError('Native replacement cannot import unrelated resources')
        old=node.find('p:txBody',NS) if field=='text_body' else node.find('.//a14:m',NS) if field=='equation' else next((n for n in _sp(node) if E.QName(n).localname in ('prstGeom','custGeom')),None)
        if old is None:raise ValueError('Native field missing')
        old.getparent().replace(old,fresh);return
    if field in ('fill_color','line_color','style.color'):
        if not isinstance(value,str) or len(value)!=6 or any(c not in '0123456789abcdefABCDEF' for c in value):
            raise ValueError('Color is six hexadecimal RGB digits')
        nodes=node.findall('.//a:rPr/a:solidFill/a:srgbClr',NS) if field=='style.color' else [
              _sp(node).find('a:solidFill/a:srgbClr',NS) if field=='fill_color' else _sp(node).find('a:ln/a:solidFill/a:srgbClr',NS)]
        if not nodes or any(n is None for n in nodes):raise ValueError('Solid color field missing')
        for n in nodes:n.set('val',value.upper())
        return
    if field in ('style.font_size','style.font','style.bold','style.italic'):
        runs=node.xpath('.//a:rPr | .//a:defRPr',namespaces=NS)
        if not runs:raise ValueError('Native text runs missing')
        if field=='style.font_size':
            if not isinstance(value,(int,float)) or not math.isfinite(value) or not 1<=value<=400:raise ValueError('Bounded font size required')
            runs+=node.findall('.//a:endParaRPr',NS)
        for run in runs:
            if field=='style.font':
                if not isinstance(value,str) or not 1<=len(value)<=100:raise ValueError('Font family required')
                for script in ('latin','ea','cs'):
                    child=run.find('a:'+script,NS)
                    if child is None:child=E.SubElement(run,'{'+NS['a']+'}'+script)
                    child.set('typeface',value)
            else:
                attr={'style.font_size':'sz','style.bold':'b','style.italic':'i'}[field]
                if field!='style.font_size' and not isinstance(value,bool):raise ValueError('Boolean text style required')
                run.set(attr,str(round(value*100)) if field=='style.font_size' else '1' if value else '0')
        return
    if field=='style.line_width':
        if not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<value<=100:raise ValueError('Bounded positive line width required')
        _sp(node).find('a:ln',NS).set('w',str(round(value*12700)));return
    xf=_sp(node).find('a:xfrm',NS)
    if field=='style.rotation':
        if not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('Finite rotation required')
        xf.set('rot',str(round((value%360)*60000)));return
    if field=='group_translate':
        if E.QName(node).localname!='grpSp' or not isinstance(value,list) or len(value)!=2 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in value):
            raise ValueError('Group translation is an explicit EMU delta pair')
        off=xf.find('a:off',NS)
        for k,v in zip(('x','y'),value):off.set(k,str(int(off.get(k))+round(v)))
        return
    if field.startswith('bbox.'):
        if not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('Finite parent-coordinate EMU required')
        tag,attr={'bbox.left':('off','x'),'bbox.top':('off','y'),'bbox.width':('ext','cx'),'bbox.height':('ext','cy')}[field]
        if tag=='ext' and value<=0:raise ValueError('Positive extent required')
        xf.find('a:'+tag,NS).set(attr,str(round(value)));return
    raise ValueError('Use a named donor for this native field: '+field)


def apply_native(task,baseline,proof,result,output):
    grants=proof['allowed_changes']
    if result.get('donor'):
        ref=result['donor'];donor=safe_path(task,ref['path'])
        if digest(donor)!=ref['sha256']:raise ValueError('Edited host donor changed')
    else:
        changes=result.get('changes',[]);seen=set()
        with ZipFile(baseline) as archive:
            parts={i.filename:archive.read(i.filename) for i in archive.infolist()}
        tree=E.fromstring(parts['ppt/slides/slide1.xml']);nodes=_nodes(tree)
        for change in changes:
            key=(change['object_id'],change['field'])
            if key in seen or key[1] not in grants.get(key[0],[]):raise ValueError('Change expands/repeats its frozen property grant')
            seen.add(key);_set(nodes[key[0]],key[1],change['value'])
        if seen!={(n,f) for n,fields in grants.items() for f in fields}:raise ValueError('Answer every authorized property explicitly')
        parts['ppt/slides/slide1.xml']=E.tostring(tree,xml_declaration=True,encoding='UTF-8',standalone=True)
        donor=Path(output).with_name('donor.pptx')
        with ZipFile(donor,'w',compression=ZIP_DEFLATED) as archive:
            for name,data in parts.items():archive.writestr(name,data)
    from .native_commit import merge_native
    return merge_native(baseline,donor,grants,output)


def apply_raster(task,baseline,proof,result,output):
    from .local_raster import compose
    raster=proof['raster'];name=raster['object_id']
    spec={'schema_version':'local-raster-edit-1','layer_kind':raster['layer_kind'],
          'instance_id':proof['id'],'layer_id':name,'intent':proof['user_intent']['text'],
          'baseline_pptx_hash':proof['baseline_hash'],'authorization_hash':identity(proof),
          'source':raster['source'],'allowed_mask':raster['allowed_mask']}
    proposal={**result['candidate'],'contract_hash':identity(spec)}
    asset=Path(output).with_name('composed.png');receipt=compose(spec,task,proposal,asset)
    with ZipFile(baseline) as archive:parts={i.filename:archive.read(i.filename) for i in archive.infolist()}
    tree=E.fromstring(parts['ppt/slides/slide1.xml']);node=_nodes(tree)[name]
    rel_file='ppt/slides/_rels/slide1.xml.rels';rels=E.fromstring(parts[rel_file])
    rid='rId'+str(max([int(r.get('Id')[3:]) for r in rels if r.get('Id','').startswith('rId')]+[0])+1)
    media='ppt/media/lotra-'+digest(asset)+'.png'
    E.SubElement(rels,'{http://schemas.openxmlformats.org/package/2006/relationships}Relationship',
                 Id=rid,Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/image',Target='../media/'+Path(media).name)
    node.find('p:blipFill/a:blip',NS).set('{'+NS['r']+'}embed',rid)
    parts['ppt/slides/slide1.xml']=E.tostring(tree,xml_declaration=True,encoding='UTF-8',standalone=True)
    parts[rel_file]=E.tostring(rels,xml_declaration=True,encoding='UTF-8',standalone=True)
    types=E.fromstring(parts['[Content_Types].xml'])
    if not any(n.get('Extension')=='png' for n in types):
        E.SubElement(types,'{http://schemas.openxmlformats.org/package/2006/content-types}Default',Extension='png',ContentType='image/png')
        parts['[Content_Types].xml']=E.tostring(types,xml_declaration=True,encoding='UTF-8',standalone=True)
    parts[media]=asset.read_bytes()
    with ZipFile(output,'w',compression=ZIP_DEFLATED) as archive:
        for key,data in parts.items():archive.writestr(key,data)
    return {'status':'FROZEN_MASK_PICTURE_EDIT','pixel_protection':receipt,
            'preservation':'original ZIP parts retained except named picture reference and new private media relationship'}
