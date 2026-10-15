"""One-shot partial PPT input, completed on the normal component construction path."""
import copy
import shutil
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from .common import read_json,write_json,digest,writer


def adopt(task,pptx,request):
    from . import agent_runtime as a,component_workflow as c
    from .native_snapshot import snapshot
    from .native_core_inspect import inventory
    from .native_input import single_slide,normalize_one_slide,scene_dimensions,same_canvas
    from .native_ownership import expanded
    from .font_contract import requests,compile_scene
    from .component_transactions import retain_native
    task,state=a._state(task);contract,ledger=c._load(task,state)
    if not contract or c._candidate(state):raise ValueError('Bind the image component contract, then import one partial PPT before construction')
    source=Path(pptx).resolve()
    if request.get('source_hash')!=state['source']['sha256'] or digest(source)!=request.get('expected_pptx_sha256'):
        raise ValueError('Partial PPT input must bind the exact image and native file')
    frozen=read_json(c._resource(task,contract['source_scene']))
    with ZipFile(source) as package:
        description=single_slide(package)
        if not same_canvas(description['canvas'],scene_dimensions(frozen)):
            raise ValueError('Match the image source canvas and uploaded PPT dimensions before one-shot import')
        native,duplicates=inventory(E.fromstring(package.read(description['part'])))
    expected=expanded(frozen,task)
    if duplicates or set(native)-set(expected):
        raise ValueError('Map every uploaded native owner by its actual name in the image source contract before import')
    base='input-pptx-'+state['component_workflow']['contract']['sha256'][:12]
    choices=[task/'versions'/(base+'-'+str(i)) for i in range(1,4)]
    folder=next((p for p in choices if not p.exists()),None)
    if folder is None:raise ValueError('Retained partial-PPT import attempts require a corrected source contract')
    folder.mkdir(exist_ok=False);saved=folder/'drawing.pptx'
    uploaded=folder/'uploaded.pptx';shutil.copyfile(source,uploaded)
    normalization=normalize_one_slide(uploaded,saved,description)
    imported=snapshot(task,state,saved,frozen)
    # Import and donor construction share the same frozen canvas quantization.
    imported['canvas']=copy.deepcopy(frozen['canvas'])
    original={n['id']:n for n in imported['objects']};source_nodes={n['id']:n for n in frozen['objects']}
    actual=[]
    for node in frozen['objects']:
        name=node['id']
        if name not in native:continue
        current=copy.deepcopy(original[name])
        if node['render_type']=='trace':
            current=copy.deepcopy(node);current['bbox']=original[name]['bbox']
            current['content']['native_snapshot']=original[name]['content']['native_snapshot']
        actual.append(current)
    imported['objects']=actual
    scene_file=folder/'scene.json';write_json(scene_file,imported)
    candidate={'revision':state['revision']+1,'scene':c._ref(task,scene_file),'pptx':c._ref(task,saved),
               'baseline':None,'allowed':{},'reason':{'kind':'partial_ppt_input'},'recipe_state':'snapshot_only'}
    retain_native(task,candidate)
    merged=copy.deepcopy(imported);merged['objects']=[]
    actual_by_id={n['id']:n for n in actual};missing=set(source_nodes)-set(actual_by_id)
    allowed={name:['add'] for name in set(expected)-set(native)}
    for node in frozen['objects']:
        name=node['id'];current=copy.deepcopy(actual_by_id.get(name,node))
        if name in actual_by_id and node['render_type'] in ('text','table','equation'):
            # Normalize these source-bound owners once, including arbitrary incoming run splits.
            current=copy.deepcopy(node)
            # Keep uploaded placement, but construct source text/body/grid extents.
            current['bbox']=[*actual_by_id[name]['bbox'][:2],*node['bbox'][2:]]
            current['parent']=actual_by_id[name].get('parent')
            current['content'].pop('native_snapshot',None)
            allowed[name]=['replace_component']
        if name in actual_by_id and node.get('parent') in missing:
            current['parent']=node['parent']
            if allowed.get(name)!=['replace_component']:allowed[name]=['reparent']
        if node['render_type']=='trace' and name in native:
            children={key for key,parent in expected.items() if parent==name}
            if children-set(native):
                allowed[name]=['replace_component']
                for child in children:allowed[child]=['replace_component'] if child in native else ['add']
        merged['objects'].append(current)
    # Bind all imported text through the existing language/font constructor path.
    for owner in {r['owner'] for r in requests(merged)}:
        if owner in actual_by_id and allowed.get(owner) not in (['add'],['replace_component']):
            allowed.setdefault(owner,[]).append('style.font')
    from .scene import validate
    validate(merged,task)
    state.update(active_candidate=candidate,scene=candidate['scene'],revision=candidate['revision'],
                 stage='review',packet=None)
    state['native_import']={'mode':'one_shot_partial_input','source_hash':state['source']['sha256'],
        'uploaded_pptx':c._ref(task,uploaded),'normalization':normalization,
        'pptx':candidate['pptx'],'missing_owners':sorted(missing),'quality_inherited':False}
    planned=folder/'completion-scene.json';write_json(planned,merged)
    state['component_import_pending']={'scene':c._ref(task,planned),'baseline':candidate,'allowed':allowed,
        'reason':{'kind':'partial_ppt_completion','post_save':{'complete_import':True}}}
    with writer(task):c._save_ledger(task,state,ledger,'partial_ppt_imported',state['native_import'])
    if not allowed:
        imported=compile_scene(imported);write_json(folder/'bound-scene.json',imported)
        candidate['scene']=c._ref(task,folder/'bound-scene.json')
        state.pop('component_import_pending',None)
        state.update(scene=candidate['scene'],stage='host_render',packet=None)
        with writer(task):a._save(task,state)
        return {'status':'PARTIAL_PPT_IMPORTED_ACTUAL_RENDER_REQUIRED','candidate':candidate,'acceptance':False}
    from .component_constructor import construct
    constructed=construct(task,state,merged,candidate,allowed,state['component_import_pending']['reason'])
    return {'status':'PARTIAL_PPT_COMPLETION_SAVED' if constructed else 'FONT_BINDING_REQUIRED',
            'candidate':constructed,'acceptance':False,'whole_audit_executed':False}
