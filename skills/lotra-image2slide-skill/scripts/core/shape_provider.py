"""Convert a bounded provider result to the existing native Scene contract."""
from zipfile import ZipFile
from lxml import etree as E
from .common import read_json,safe_path,digest
from .mathml import NS
from .recipes import node
from .presets import PRESETS


def load_geometry(task,spec,source_hash):
    request_file=safe_path(task,spec['request'])
    pptx=safe_path(task,spec['pptx']);receipt=read_json(safe_path(task,spec['receipt']))
    request=read_json(request_file)
    if (receipt.get('provider')!='official_artifact_tool' or receipt.get('scope')!='declared_native_geometry_only'
        or receipt.get('request_hash')!=digest(request_file) or receipt.get('pptx_hash')!=digest(pptx)
        or receipt.get('source_hash')!=source_hash or request.get('source_hash')!=source_hash):
        raise ValueError('Geometry provider result must bind this source, request and saved PPTX')
    with ZipFile(pptx) as package:
        tree=E.fromstring(package.read('ppt/slides/slide1.xml'))
        sp_tree=tree.find('p:cSld/p:spTree',NS)
        shapes=sp_tree.findall('p:sp',NS)
        if any(E.QName(n).localname not in ('nvGrpSpPr','grpSpPr','sp','extLst') for n in sp_tree):
            raise ValueError('Provider cannot replace declared geometry by a picture/group/foreign object')
        if len(shapes)!=len(request['shapes']):raise ValueError('Provider changed native shape count')
        out=[]
        for element,item in zip(shapes,request['shapes']):
            geom=element.find('p:spPr/a:prstGeom',NS)
            if geom is None or geom.get('prst') not in PRESETS or geom.get('prst')!=item['preset']:
                raise ValueError('Unsupported or different actual provider geometry')
            xf=element.find('p:spPr/a:xfrm',NS)
            if xf is None or xf.get('rot') or xf.get('flipH') or xf.get('flipV'):
                raise ValueError('Provider changed declared source orientation')
            off,ext=xf.find('a:off',NS),xf.find('a:ext',NS)
            box=[int(off.get('x'))/9525,int(off.get('y'))/9525,int(ext.get('cx'))/9525,int(ext.get('cy'))/9525]
            if max(abs(a-b) for a,b in zip(box,item['bbox']))>.002:
                raise ValueError('Provider changed measured source coordinates')
            values=[]
            for guide in geom.findall('a:avLst/a:gd',NS):
                formula=guide.get('fmla','').split()
                if len(formula)!=2 or formula[0]!='val':raise ValueError('Unsupported provider adjustment')
                values.append(float(formula[1])/100000)
            out.append(node(item['id'],'shape',box,{'preset':geom.get('prst'),'adjustments':values},
                            semantic=item.get('semantic_type','shape'),**item.get('style',{})))
    selected=spec.get('shape_ids')
    if selected is not None:
        if not selected or len(selected)!=len(set(selected)) or not set(selected)<={o['id'] for o in out}:
            raise ValueError('Provider subset must name unique declared native shapes')
        out=[o for o in out if o['id'] in selected]
    return out
