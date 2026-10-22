"""Source-bound font variants applied after copying a qualified native mother."""
import copy
from zipfile import ZipFile
from lxml import etree as E
from .common import identity, read_json
from .mathml import NS


def variant_requests(scene,row):
    """A declared text/style variant must match its target's frozen font intent."""
    from .font_contract import requests
    mapping=row['instance_transform']['owner_map']
    rows=requests(scene);by_id={request['id']:request for request in rows};pairs=[];targets=set()
    from .font_resolution import POLICY,request_key
    fields=('location','role','characters','literal_hash','bold','italic')
    for request in rows:
        if request['owner'] not in mapping:continue
        target_id=identity({'owner':mapping[request['owner']],
                            'location':request['location'],'role':request['role']})
        target=by_id.get(target_id)
        intent_fields=('required_family','intent_revision') if request.get('identity_policy')==POLICY else ('proposed_family',)
        if not target or any(request.get(k)!=target.get(k) for k in fields+intent_fields):
            raise ValueError('SOURCE_DECISION_REQUIRED: declare matching target literals, run topology and bold/italic before variant construction')
        pairs.append((request,target));targets.add(target_id)
    if targets!={r['id'] for r in rows if r['owner'] in set(mapping.values())}:
        raise ValueError('SOURCE_DECISION_REQUIRED: variant target font requests differ from its declared mother copy')
    return pairs


def bind_variant_scene(scene,row):
    """Rekey already bound target resources; do not make a new font choice."""
    from .font_contract import _request_match,compile_scene
    scene=copy.deepcopy(scene);bindings=scene.get('font_plan',{}).get('bindings',{})
    for request,target in variant_requests(scene,row):
        bound=bindings.get(target['id'])
        if not bound or not _request_match(bound,target):
            raise ValueError('FONT_BINDING_REQUIRED: bind the source target before constructing its text/style variant')
        copied=copy.deepcopy(bound);copied['request']=copy.deepcopy(request)
        from .font_resolution import request_key
        copied['request_hash']=request_key(request)
        copied['variant_target_request']=target['id'];bindings[request['id']]=copied
    return compile_scene(scene)


def signature(scene,row):
    owners=set(row['instance_transform']['owner_map'].values())
    return identity({key:{'request_hash':b['request_hash'],'family':b['family'],
        'resource':b['resource']['id'],'synthetic_style':b.get('synthetic_style',False)}
        for key,b in scene.get('font_plan',{}).get('bindings',{}).items() if b['request']['owner'] in owners})


def prepare(task,state,candidate,row,folder):
    from . import component_workflow as c
    from .font_contract import compile_scene,requests
    from .build import build
    from .native_commit import donor_scene,_nodes
    scene=compile_scene(read_json(c._resource(task,candidate['scene'])))
    owners=set(row['instance_transform']['owner_map'].values())
    selected={r['owner'] for r in requests(scene) if r['owner'] in owners}
    if not selected:return {},signature(scene,row)
    file=folder/'instance-font-donor.pptx'
    build(donor_scene(scene,{owner:['style.font'] for owner in selected}),task,file)
    with ZipFile(file) as package:nodes=_nodes(E.fromstring(package.read('ppt/slides/slide1.xml')))
    return {owner:nodes[owner] for owner in selected},signature(scene,row)


def apply(node,mapping,donors):
    """Only native font slots change; anatomy, size and placement remain inherited."""
    from .native_commit import _nodes,_field
    nodes=_nodes(node)
    for mother,instance in mapping.items():
        if mother in nodes and instance in donors:
            _field(nodes[mother],donors[instance],'style.font')


def retain_intent(node,hint):
    """Keep the target's source font hints when mirroring the copied geometry."""
    def fonts(left,right):
        if isinstance(left,dict) and isinstance(right,dict):
            for key in ('font','math_font','font_faces'):
                if key in right:left[key]=copy.deepcopy(right[key])
                else:left.pop(key,None)
            for key in set(left)&set(right):
                if key not in ('font','math_font','font_faces'):fonts(left[key],right[key])
        elif isinstance(left,list) and isinstance(right,list) and len(left)==len(right):
            for a,b in zip(left,right):fonts(a,b)
    fonts(node,hint)
    return node
