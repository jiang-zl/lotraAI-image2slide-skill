"""Copy qualified actual native mothers with source-bound affine placement."""
import copy,math,os
from zipfile import ZipFile,ZIP_DEFLATED
import numpy as np
from lxml import etree as E
from .common import read_json,write_json,writer,identity
from .mathml import NS


def instantiate(task,request):
    from . import agent_runtime as a,component_workflow as c
    from .native_core_inspect import inventory
    from .boundary_geometry import saved_nodes,_transform
    from .component_relations import evaluate
    task,state=a._state(task);contract,ledger=c._load(task,state);candidate=request.get('_candidate') or c._candidate(state)
    if not contract or not candidate:raise ValueError('Current source contract/candidate required')
    c.refresh(task,state,contract,ledger,candidate)
    if ledger.get('pending_transaction') and not request.get('_transaction'):
        raise ValueError('Recover the pending native transaction first')
    rows={row['id']:row for row in contract['components']};row=c.component_row(task,state,contract,request['component'])
    from .spatial_repair import guard_fields
    if state.get('spatial_source_decision') or ledger.get('pending_decision') or ledger.get('structural_grant'):
        raise ValueError('Resolve the pending source/measurement decision before instance copying')
    guard_fields(contract,ledger,[{'owner':owner,'field':[]} for owner in row['owners']])
    if ledger['components'][row['id']].get('user_locks'):raise ValueError('USER_LOCK_CONFLICT: instance body is protected')
    if row['route']!='instance' or ledger['components'][row['mother']]['status']!='QUALIFIED':
        raise ValueError('An instance must reference a qualified source mother')
    if ledger['components'][row['id']]['status']=='QUALIFIED':raise ValueError('Retain the qualified actual instance')
    if request.get('source_hash')!=state['source']['sha256'] or request.get('pptx_hash')!=candidate['pptx']['sha256']:
        raise ValueError('Current source/native binding required')
    transform=row['instance_transform'];mapping=transform['owner_map'];affine=np.asarray(transform['matrix'],float)
    if affine.shape!=(3,3) or not np.isfinite(affine).all() or not np.allclose(affine[2],[0,0,1]):raise ValueError('Finite source affine transform required')
    from .component_transactions import begin,phase,saved as journal_saved,release_local,differences,attempt_folder
    from .component_variants import variant_package,transform_policy,scale_style,expectation
    scene=read_json(c._resource(task,candidate['scene']))
    tx=request.get('_transaction') or begin(task,state,scene,candidate,
        {owner:['replace_native'] for owner in row['owners']},
        {'kind':'component_instance_copy','id':row['id'],'component_contract':identity(row)})
    number=tx['base_revision']+1;folder=request.get('_folder') or attempt_folder(task,tx)
    original_source=c._resource(task,candidate['pptx'])
    with ZipFile(original_source) as z:original_payload={info.filename:z.read(info.filename) for info in z.infolist()}
    original_root=E.fromstring(original_payload['ppt/slides/slide1.xml'])
    original_native,_=inventory(original_root)
    source=variant_package(task,state,candidate,row,folder)
    with ZipFile(source) as z:payload={info.filename:z.read(info.filename) for info in z.infolist()}
    style_scale=transform_policy(row,affine)
    root=E.fromstring(payload['ppt/slides/slide1.xml']);native,duplicate=inventory(root)
    frames=saved_nodes(source,state['source_size'])
    if duplicate or not set(mapping)<=set(native) or not set(mapping.values())<=set(native) or len(set(mapping.values()))!=len(mapping):
        raise ValueError('Exact one-to-one current native mother/instance mapping required')
    roots=[name for name in mapping if native[name]['parent'] not in mapping]
    if len(roots)!=1:raise ValueError('Use one qualified native group root per instance')
    mother=roots[0];target=mapping[mother]
    mother_desc={name for name in native if name==mother or native[name]['node'] in native[mother]['node'].iterdescendants()}
    target_desc={name for name in native if name==target or native[name]['node'] in native[target]['node'].iterdescendants()}
    if set(mapping)!=mother_desc or set(mapping.values())!=target_desc or not target_desc<=set(row['owners']):
        raise ValueError('Instance mapping must cover every actual descendant without changing another owner')
    from .component_font_instances import prepare as prepare_fonts,apply as apply_fonts,retain_intent
    font_donors,font_signature=prepare_fonts(task,state,candidate,row,folder)
    expected=expectation(task,candidate,row,source,original_native,native,style_scale,font_donors,font_signature)
    clone=copy.deepcopy(native[mother]['node'])
    scale_style(clone,style_scale)
    apply_fonts(clone,mapping,font_donors)
    if E.QName(clone).localname!='grpSp':raise ValueError('Group parts into a qualified mother before native instance copying')
    old_to_new={native[name]['id']:native[copy_name]['id'] for name,copy_name in mapping.items()}
    for props in clone.findall('.//p:cNvPr',NS):
        name=props.get('name');props.set('name',mapping[name]);props.set('id',native[mapping[name]]['id'])
    for connection in clone.xpath('.//a:stCxn|.//a:endCxn',namespaces=NS):
        if connection.get('id') not in old_to_new:raise ValueError('External mother connections need separate source instance interfaces')
        connection.set('id',old_to_new[connection.get('id')])
    desired=np.linalg.inv(frames[target]['parent_matrix'])@affine@frames[mother]['matrix']
    sx=np.linalg.norm(desired[:2,0]);sy=np.linalg.norm(desired[:2,1])
    if min(sx,sy)<=0 or abs(np.dot(desired[:2,0],desired[:2,1]))>1e-7*sx*sy:
        raise ValueError('Native group cannot represent a sheared instance; choose an original-supported model')
    xf=clone.find('p:grpSpPr/a:xfrm',NS);co=xf.find('a:chOff',NS);ce=xf.find('a:chExt',NS)
    cx,cy=float(co.get('x')),float(co.get('y'));cw,ch=float(ce.get('cx')),float(ce.get('cy'))
    ext=np.array([cw*sx,ch*sy]);center=(desired@np.array([cx+cw/2,cy+ch/2,1]))[:2]
    off=center-ext/2;angle=math.degrees(math.atan2(desired[1,0],desired[0,0]))
    for key in ('rot','flipH','flipV'):xf.attrib.pop(key,None)
    if abs(angle)>1e-9:xf.set('rot',str(round(angle*60000)))
    if np.linalg.det(desired[:2,:2])<0:xf.set('flipV','1')
    for tag,keys,values in (('off',('x','y'),off),('ext',('cx','cy'),ext)):
        for key,value in zip(keys,values):xf.find('a:'+tag,NS).set(key,str(round(value)))
    parent=native[target]['node'].getparent();parent.replace(native[target]['node'],clone)
    if row.get('variant'):
        # Keep the base mother byte-for-byte; derived fields live in the copy.
        parent_mother=native[mother]['node'].getparent()
        parent_mother.replace(native[mother]['node'],copy.deepcopy(original_native[mother]['node']))
    payload['ppt/slides/slide1.xml']=E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)
    output=folder/'drawing.pptx';staged=folder/'drawing.part.pptx'
    with ZipFile(staged,'w',compression=ZIP_DEFLATED) as z:
        for name,data in payload.items():z.writestr(name,data)
    os.replace(staged,output)
    expected_file=folder/'Expected-instance.json';write_json(expected_file,expected)
    actual={**candidate,'revision':number,'pptx':c._ref(task,output)}
    relation_ids=[r['id'] for r in contract['relations'] if r['kind']=='instance_of' and r['components'][1]==row['id']]
    checked=evaluate(task,state,actual,contract,relation_ids,expected_instances={row['id']:expected})
    if not relation_ids or not checked['passed']:raise ValueError('Saved native instance differs from the source transform: '+repr(checked))
    from .native_snapshot import snapshot
    scene=read_json(c._resource(task,candidate['scene']))
    imported=snapshot(task,state,output,scene)
    observed={n['id']:n for n in imported['objects']}
    source_nodes={n['id']:n for n in scene['objects']};reverse={v:k for k,v in mapping.items()}
    replacement={}
    for copy_name,mother_name in reverse.items():
        node=copy.deepcopy(source_nodes[mother_name]);node['id']=copy_name
        node['parent']=mapping.get(node.get('parent'),source_nodes[copy_name].get('parent'))
        for override in (row.get('variant') or {}).get('overrides',[]):
            if override['owner']!=mother_name:continue
            pointer=node;path=override['field']
            for key in path[:-1]:pointer=pointer[key]
            pointer[path[-1]]=copy.deepcopy(override['value'])
        if style_scale!=1:
            for field in ('line_width','font_size','char_spacing_pt','line_spacing_pt'):
                if type(node.get('style',{}).get(field)) in (int,float):node['style'][field]*=style_scale
        retain_intent(node,source_nodes[copy_name])
        node['bbox']=observed[copy_name]['bbox']
        for field in ('source','target','source_anchor_object','target_anchor_object'):
            if node['content'].get(field) in mapping:node['content'][field]=mapping[node['content'][field]]
        node['content']['native_snapshot']=observed[copy_name]['content']['native_snapshot']
        replacement[copy_name]=node
    scene['objects']=[replacement.get(n['id'],n) for n in scene['objects']]
    from .font_contract import bind_scene
    scene=bind_scene(task,state,scene)
    scene_file=folder/'scene.json';write_json(scene_file,scene)
    actual.update(scene=c._ref(task,scene_file),baseline=candidate['pptx']['sha256'],
        reason={'kind':'component_instance_copy','id':row['id']},allowed={target:['replace_component']})
    actual.pop('preview',None);actual.pop('render',None)
    before_nodes={n['id']:n for n in read_json(c._resource(task,candidate['scene']))['objects']}
    patches=[]
    for node in scene['objects']:
        if node['id'] in row['owners']:
            patches.extend(dict(p,owner=node['id']) for p in differences(before_nodes[node['id']],node))
    if request.get('_prepare'):
        return {'candidate':actual,'expectation':c._ref(task,expected_file),'checks':checked,'patches':patches}
    tx['patches']=patches;tx['planned_scene']=actual['scene'];tx['display_required']=True
    tx['instance_expectation']=c._ref(task,expected_file)
    tx['post_save']={'statuses':{row['id']:'INSTANCE_NATIVE_CONFIRMATION_REQUIRED'}}
    journal_saved(task,tx,actual)
    phase(task,tx,'DISPLAY_PENDING',candidate=actual)
    task,state=a._state(task);contract,ledger=c._load(task,state)
    state.update(active_candidate=actual,scene=actual['scene'],revision=number,stage='host_render',packet=None)
    ledger['components'][row['id']]['status']='INSTANCE_NATIVE_CONFIRMATION_REQUIRED'
    ledger['components'][row['id']]['instantiation']={'candidate':actual['pptx'],'mother':row['mother'],'checks':checked,'expectation':c._ref(task,expected_file)}
    with writer(task):c._save_ledger(task,state,ledger,'instance_copied',{'candidate':actual['pptx'],'mother':row['mother'],'checks':checked,'expectation':c._ref(task,expected_file)})
    return {'status':'INSTANCE_SAVED_ACTUAL_RENDER_REQUIRED','candidate':actual,'whole_audit_executed':False,'office_behavior_executed':False}
