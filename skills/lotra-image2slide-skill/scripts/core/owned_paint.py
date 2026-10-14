"""Actual owner paint support for exact replayed source corrections.

Native coordinates do not bound arrowheads, strokes or effects. Four isolated
pages preserve all native transforms and compare black/white backdrops in the
same renderer. Neither callers nor the semantic host supply a permission mask.
"""
import copy
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from .common import digest,identity,read_json,write_json,safe_path
from .mathml import NS

def _plan(task,state,candidate,approved,constructor):
    if not constructor.get('passed'):raise ValueError('Exact source constructor required before owner-paint capture')
    record=next((r for r in reversed(state.get('connection_attempts',[])) if r['candidate']==candidate['pptx']['sha256']),None)
    before=record['baseline']['pptx'] if record else approved['pptx']
    return {'schema':'source-correction-owned-paint-2','source':state['source'],'approved_context':approved['pptx'],
        'before':before,'after':candidate['pptx'],'owners':sorted(constructor['objects']),
        'basis':'Exact immediate constructor snapshots; all prior changes independently replay and pass their own pixel protection before this guard succeeds.',
        'canvas':state['source_size'],'implementation':digest(Path(__file__))}

def _payload(task,plan):
    from .inspect import inventory
    from .semantic_composition import isolated_parts
    from .native_capture_batch import package
    pages=[];base=None;members=[]
    for key in ('before','after'):
        ref=plan[key];file=safe_path(task,ref['path'])
        if digest(file)!=ref['sha256']:raise ValueError('Owned-paint source native bytes changed')
        with ZipFile(file) as z:parts={n:z.read(n) for n in z.namelist()}
        tree=E.fromstring(parts['ppt/slides/slide1.xml']);nodes,duplicates=inventory(tree)
        if duplicates:raise ValueError('Unique saved paint-owner identities required')
        parents={n:v['parent'] for n,v in nodes.items()}
        owned=set(plan['owners'])&set(nodes)
        while True:
            more={n for n,p in parents.items() if p in owned}-owned
            if not more:break
            owned|=more
        leaves=sorted(n for n in owned if E.QName(nodes[n]['node']).localname!='grpSp')
        ids=[int(nodes[n]['id']) for n in leaves]
        item={'leaf_objects':leaves,'native_ids':ids,'measurement':'paint_support'}
        pages.extend(isolated_parts(parts,tree,item,c)['ppt/slides/slide1.xml'] for c in ('black','white'))
        members.append({'snapshot':key,'native_ids':ids,'objects':leaves})
        resources={n:b for n,b in parts.items() if n!='ppt/slides/slide1.xml'}
        if base is not None and resources!={n:b for n,b in base.items() if n!='ppt/slides/slide1.xml'}:
            raise ValueError('Owner-paint batch requires unchanged source-constructor resources')
        base=parts
    return package(base,pages),members

def capture(task,state,candidate,approved,_seen=None):
    if not approved:return {'status':'NO_APPROVED_NATIVE_CONTEXT'}
    seen=set(_seen or ());key=candidate['pptx']['sha256']
    if key in seen:raise ValueError('Cyclic source constructor history')
    seen.add(key)
    stage=next((r for r in reversed(state.get('connection_attempts',[])) if r['candidate']==key),None)
    if stage and any(r['candidate']==stage['baseline']['pptx']['sha256'] for r in state.get('connection_attempts',[])):
        prior=capture(task,state,stage['baseline'],approved,seen)
        if not prior.get('receipt'):return {'status':'PRIOR_EXACT_OWNED_PAINT_REQUIRED','prior':prior}
    from .source_layout_actions import guard
    proof=guard(task,state,candidate,approved)
    if not proof.get('passed'):return {'status':'EXACT_SOURCE_CONSTRUCTOR_REQUIRED'}
    plan=_plan(task,state,candidate,approved,proof);directory=task/'observations/owned-paint'/identity(plan)
    record=directory/'Receipt.json'
    if record.is_file():return {'status':'EXISTING_OWNED_PAINT','receipt':{'path':record.relative_to(task).as_posix(),'sha256':digest(record)}}
    payload,members=_payload(task,plan);directory.mkdir(parents=True,exist_ok=True)
    from .native_capture_batch import save_immutable
    file=directory/'Owners.pptx';save_immutable(file,payload)
    from .tool_router import render_saved
    main=read_json(safe_path(task,candidate['render']['path']));caps=copy.deepcopy(state['capabilities'])
    if main['backend']=='LibreOffice':caps['render_preference']='libreoffice'
    output=directory/'render'
    if (output/'render.json').is_file():host=read_json(output/'render.json')
    else:host=render_saved(file,output,caps,state['source_size'][0]*2)
    if host['backend']!=main['backend'] or len(host.get('pages',[]))!=4:raise ValueError('Same actual renderer and all four owner-support pages required')
    receipt={'plan':plan,'members':members,'batch':{'path':file.relative_to(task).as_posix(),'sha256':digest(file)},
        'render':{'path':(output/'render.json').relative_to(task).as_posix(),'sha256':digest(output/'render.json')}}
    write_json(record,receipt)
    return {'status':'ACTUAL_OWNED_PAINT_CAPTURED','backend':host['backend'],'receipt':{'path':record.relative_to(task).as_posix(),'sha256':digest(record)}}

def mask(task,state,candidate,approved,constructor,shape,_seen=None):
    import numpy as np
    from PIL import Image
    from scipy.ndimage import maximum_filter
    seen=set(_seen or ());key=candidate['pptx']['sha256']
    if key in seen:raise ValueError('Cyclic source constructor paint chain')
    seen.add(key)
    plan=_plan(task,state,candidate,approved,constructor);record=task/'observations/owned-paint'/identity(plan)/'Receipt.json'
    if not record.is_file():raise ValueError('Actual program-owned paint capture required; use observe-rules or composition capture')
    receipt=read_json(record)
    if receipt['plan']!=plan:raise ValueError('Owned-paint receipt changed')
    payload,members=_payload(task,plan);file=safe_path(task,receipt['batch']['path'])
    if digest(file)!=receipt['batch']['sha256'] or receipt['members']!=members:raise ValueError('Owned-paint native ownership changed')
    with ZipFile(file) as z:
        if {n:z.read(n) for n in z.namelist()}!=payload:raise ValueError('Isolated owner batch differs from exact native constructor')
    render=safe_path(task,receipt['render']['path'])
    if digest(render)!=receipt['render']['sha256']:raise ValueError('Owned-paint actual renderer receipt changed')
    host=read_json(render);main=read_json(safe_path(task,candidate['render']['path']))
    if host['pptx_hash']!=digest(file) or host['backend']!=main['backend'] or len(host['pages'])!=4:raise ValueError('Owned paint belongs to another renderer/native file')
    images=[]
    for page in host['pages']:
        image=render.parent/page['path']
        if digest(image)!=page['sha256']:raise ValueError('Owned-paint actual page changed')
        with Image.open(image) as im:images.append(np.asarray(im.convert('RGB'),dtype=np.int16))
    if any(im.shape[:2]!=shape for im in images):raise ValueError('Owned paint requires the same complete preview sampling grid')
    support=np.zeros(shape,bool)
    for i in (0,2):support|=np.max(np.abs(images[i+1]-images[i]),axis=2)<255
    radius=int(np.ceil(2*shape[1]/state['source_size'][0]))
    support=maximum_filter(support,size=2*radius+1)
    proof={'path':record.relative_to(task).as_posix(),'sha256':digest(record),'method':'same_renderer_exact_owned_native_paint_on_two_backdrops','margin_source_px':2}
    stage=next((r for r in reversed(state.get('connection_attempts',[])) if r['candidate']==key),None)
    if stage and any(r['candidate']==stage['baseline']['pptx']['sha256'] for r in state.get('connection_attempts',[])):
        from .source_layout_actions import guard
        prior=stage['baseline'];prior_constructor=guard(task,state,prior,approved)
        if not prior_constructor.get('passed'):raise ValueError('Prior source constructor paint chain is unproved')
        prior_mask,prior_receipt=mask(task,state,prior,approved,prior_constructor,shape,seen)
        support|=prior_mask
        proof['prior_verified_paint']=prior_receipt
    return support,proof
