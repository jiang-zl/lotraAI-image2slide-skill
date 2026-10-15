"""Source-bound variant fields and explicit native instance style scaling."""
import copy
import math
from zipfile import ZipFile
import numpy as np
from lxml import etree as E
from .common import read_json,write_json,identity
from .mathml import NS


def native_body(node):
    node=copy.deepcopy(node)
    for child in list(node):
        if E.QName(child).localname in ('sp','grpSp','cxnSp','pic','graphicFrame'):node.remove(child)
    for xf in node.xpath('.//a:xfrm|./p:xfrm',namespaces=NS):xf.getparent().remove(xf)
    for props in node.xpath('.//p:cNvPr',namespaces=NS):
        props.attrib.pop('id',None);props.attrib.pop('name',None)
    return E.tostring(node,method='c14n').decode()


def transform_policy(row,matrix):
    linear=np.asarray(matrix,float)[:2,:2]
    sx=float(np.linalg.norm(linear[:,0]));sy=float(np.linalg.norm(linear[:,1]))
    if min(sx,sy)<=0:raise ValueError('Positive source instance scale required')
    anisotropic=abs(sx-sy)>1e-7*max(sx,sy)
    mirrored=np.linalg.det(linear)<0
    declared=row.get('transform_policy',{})
    if anisotropic and not (declared.get('allow_non_uniform') and declared.get('source_evidence')):
        raise ValueError('Nonuniform instance scale needs explicit original evidence')
    if mirrored and not (declared.get('allow_reflection') and declared.get('source_evidence')):
        raise ValueError('Reflected instance needs explicit original evidence')
    policy=row.get('scale_policy','preserve_absolute_style')
    if policy not in ('scale_with_geometry','preserve_absolute_style'):raise ValueError('Explicit native style scale policy required')
    if policy=='preserve_absolute_style':return 1.
    factor=declared.get('style_scale') if anisotropic else sx
    if type(factor) not in (int,float) or not math.isfinite(factor) or factor<=0:
        raise ValueError('Anisotropic style scaling needs a positive source-declared scale')
    return factor


def scale_style(clone,factor):
    if factor==1:return
    for line in clone.xpath('.//a:ln[@w]',namespaces=NS):
        line.set('w',str(max(1,round(int(line.get('w'))*factor))))
    for props in clone.xpath('.//a:rPr|.//a:defRPr|.//a:endParaRPr',namespaces=NS):
        for attr in ('sz','spc'):
            if props.get(attr) is not None:props.set(attr,str(round(int(props.get(attr))*factor)))
    for spacing in clone.xpath('.//a:spcPts',namespaces=NS):
        spacing.set('val',str(round(int(spacing.get('val'))*factor)))


def variant_scene(scene,row):
    """Shared source preflight and private donor preparation for declared fields."""
    variant=row.get('variant')
    scene=copy.deepcopy(scene)
    if not variant:return scene,{}
    if variant.get('mother')!=row['mother'] or not variant.get('source_evidence'):
        raise ValueError('Variant must reference this original-supported mother')
    overrides=variant.get('overrides',[])
    if not overrides:raise ValueError('A variant needs explicit field overrides')
    mapping=row['instance_transform']['owner_map']
    nodes={n['id']:n for n in scene['objects']};allowed={}
    for override in overrides:
        owner=override['owner'];path=override['field']
        if owner not in mapping or not path or path[0] not in ('bbox','content','style'):
            raise ValueError('Variant override escaped the existing mother topology')
        if path[:2] in (['style','font'],['style','math_font'],['style','font_faces']):
            continue  # The target's independently bound font plan is applied after copying.
        node=nodes[owner];pointer=node
        for key in path[:-1]:pointer=pointer[key]
        pointer[path[-1]]=copy.deepcopy(override['value'])
        if node['render_type'] in ('text','table','equation'):
            # Reconstruct this private text owner, including any changed run topology.
            field='replace_component'
        elif path[0]=='bbox':field=['bbox.left','bbox.top','bbox.width','bbox.height'][path[1]]
        elif path[0]=='style':field='style.'+path[1]
        elif path[:2]==['content','text']:field='text_content'
        elif path[0]=='content' and path[1] in ('source','target','source_anchor_object','target_anchor_object'):
            raise ValueError('Variant cannot redefine scientific or external port topology')
        else:field='geometry'
        if field=='replace_component':allowed[owner]=['replace_component']
        elif allowed.get(owner)!=['replace_component']:allowed.setdefault(owner,[]).append(field)
        node['content'].pop('native_snapshot',None)
    from .component_font_instances import retain_intent
    for owner,target in mapping.items():
        retain_intent(nodes[owner],nodes[target])
    return scene,allowed


def variant_package(task,state,candidate,row,folder):
    """Build a private variant with exact target font bindings before the donor."""
    from . import component_workflow as c
    from .build import build
    from .native_commit import donor_scene,merge_native
    if not row.get('variant'):return c._resource(task,candidate['pptx'])
    scene,allowed=variant_scene(read_json(c._resource(task,candidate['scene'])),row)
    from .component_font_instances import bind_variant_scene
    scene=bind_variant_scene(scene,row)
    if not allowed:return c._resource(task,candidate['pptx'])
    donor=folder/'variant-donor.pptx';output=folder/'variant-source.pptx'
    build(donor_scene(scene,allowed),task,donor)
    merge_native(c._resource(task,candidate['pptx']),donor,allowed,output)
    return output


def expectation(task,candidate,row,source_file,original_native,variant_native,style_scale,font_donors=None,font_signature=None):
    from . import component_workflow as c
    mapping=row['instance_transform']['owner_map'];bodies={}
    for owner in mapping:
        node=copy.deepcopy(variant_native[owner]['node']);scale_style(node,style_scale)
        if font_donors:
            from .component_font_instances import apply as apply_fonts
            apply_fonts(node,mapping,font_donors)
        ids={original_native[k]['id']:original_native[v]['id'] for k,v in mapping.items()}
        for connection in node.xpath('.//a:stCxn|.//a:endCxn',namespaces=NS):
            if connection.get('id') in ids:connection.set('id',ids[connection.get('id')])
        bodies[owner]=native_body(node)
    return {'component_contract':identity(row),'original_bodies':{name:native_body(original_native[name]['node']) for name in mapping},
            'expected_bodies':bodies,'source_package':c._ref(task,source_file),
            'variant':row.get('variant'),'scale_policy':row.get('scale_policy','preserve_absolute_style'),
            'style_scale':style_scale,'font_binding_signature':font_signature,
            'font_variant_basis':'Exact target source bindings; only native typeface slots are overridden'}

