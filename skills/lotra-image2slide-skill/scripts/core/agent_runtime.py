"""Program-owned image-to-slide loop; host reasoning happens in bounded packets.

Uses the existing native builder/recipes/render/protection/component exporters.
No model API and no second rendering engine. Actual saved results drive review.
"""
import copy
import json
import math
import re
import shutil
import time
import uuid
from pathlib import Path
from .common import canonical, digest, identity, read_json, safe_path, write_json, writer
from .library_store import BUILD_DIR, Library
from .tool_router import capabilities, render_saved
from . import source_quality, semantic_composition, candidate_adoption, font_contract, frame_plan, execution_contract
from .task_transaction import transaction
from .execution_context import metrics as cached_metrics
from .context_control import library_scope
from .retry_context import checked_submit

SCHEMA = 'lotra-agent-1'
DIMENSIONS = ('semantics', 'geometry', 'appearance')
PRIORITY = {'critical': 0, 'major': 1, 'minor': 2, 'polish': 3}



def _located_issue(state, finding):
    """Keep co-located natural parts independent, without rewriting old IDs."""
    payload={k:finding.get(k) for k in ('owner','roi','property','expected')}
    legacy=identity(payload)[:14]
    if finding.get('quality_unit'):
        payload['quality_unit']=finding['quality_unit']
    iid=identity(payload)[:14]
    existing=next((i for i in state['issues'] if i['id']==iid),None)
    if existing is None:
        existing=next((i for i in state['issues'] if i['id']==legacy
                       and i.get('quality_unit')==finding.get('quality_unit')),None)
    return (existing['id'] if existing else iid),existing


def _same_issue_part(record, issue):
    # Unbound legacy findings stay conservative. An explicitly bound finding
    # from another natural part cannot keep this one open or resolve it.
    return record.get('quality_unit') in (None,issue.get('quality_unit'))


def _path(task, ref):
    return safe_path(task, ref)


class _StateSnapshot(dict):
    """Volatile read stamp is never part of the user/task JSON contract."""
    def __init__(self,value,stamp):
        super().__init__(value);self._read_stamp=stamp


def _read_state(path):
    import hashlib
    data=Path(path).read_bytes()
    value=read_json(path)
    from .state_repository import LazyDict
    if isinstance(value,LazyDict):
        value._read_stamp=hashlib.sha256(data).hexdigest()
        return value
    return _StateSnapshot(value,hashlib.sha256(data).hexdigest())


def _state(task):
    task = Path(task).resolve()
    state = _read_state(task / 'state.json')
    if state['schema'] != SCHEMA:
        raise ValueError('Unknown task state')
    if digest(_path(task, state['source']['path'])) != state['source']['sha256']:
        raise ValueError('Task source evidence changed')
    execution_contract.policy(state)
    if state.get('objectives',{}).get('component_first'):
        state['project']=str(task.parents[2])
        return task,state
    from .source_recursion import verify_activation
    verify_activation(task,state)
    from .source_contract import verify_seals
    verify_seals(task,state)
    from .catalog_source import verify_frozen
    verify_frozen(task,state)
    # Moving a project between OSes changes physical paths, not logical IDs.
    state['project'] = str(task.parents[2])
    return task, state


def _save(task, state):
    task=Path(task);file=task/'state.json';lock=task/'.writer.lock'
    if lock.exists():
        import os
        if read_json(lock).get('pid')!=os.getpid():raise ValueError('Concurrent task writer; reload after the owning transaction finishes')
        return _save_locked(task,state)
    with writer(task):return _save_locked(task,state)


def _save_locked(task,state):
    file=Path(task)/'state.json';stamp=getattr(state,'_read_stamp',None)
    if file.exists() and (stamp is None or digest(file)!=stamp):
        raise ValueError('Stale task state write rejected; reload the current task. Saved artifacts remain recoverable, but an old reader cannot overwrite new execution records.')
    if state.get('objectives',{}).get('component_first'):
        from .state_repository import store_document
        state['updated']=time.time()
        store_document(file,state,task=task)
        if hasattr(state,'_read_stamp'):state._read_stamp=digest(file)
        return
    from .source_recursion import verify_activation
    verify_activation(task,state)
    from .source_contract import seal_pending,verify_seals
    seal_pending(task,state)
    verify_seals(task,state)
    from .catalog_source import verify_frozen
    verify_frozen(task,state)
    from .candidate_cost import attach
    attach(task,state)
    from .dependency_context import record as record_dependencies
    dependency=record_dependencies(task,state)
    if dependency:state['context_dependencies']=dependency
    state['updated'] = time.time()
    write_json(file, state)
    if isinstance(state,_StateSnapshot):state._read_stamp=digest(file)
    from .context_control import checkpoint
    checkpoint(task, state)


def _event(task, kind, data):
    with (task / 'events.jsonl').open('ab') as file:
        file.write(canonical({'time': time.time(), 'kind': kind, **data}) + b'\n')


def _file(task, path):
    task=Path(task).resolve()
    path = Path(path).resolve()
    if not path.is_relative_to(task):
        raise ValueError('Runtime result must be inside this task')
    return {'path': path.relative_to(task).as_posix(), 'sha256': digest(path)}


def _roi(roi, size):
    if not isinstance(roi, list) or len(roi) != 4:
        raise ValueError('Located source ROI required')
    if not all(not isinstance(v,bool) and isinstance(v, (int, float)) and math.isfinite(v) for v in roi):
        raise ValueError('Finite ROI required')
    x, y, w, h = roi
    if min(x, y) < 0 or min(w, h) <= 0 or x+w > size[0]+.001 or y+h > size[1]+.001:
        raise ValueError('ROI outside source canvas')
    return roi


def start(source, project, *, name=None, objectives=None, configuration=None, pptx=None):
    from PIL import Image
    project = Path(project).expanduser().resolve()
    if not project.is_dir():
        raise ValueError('Existing project required')
    source = Path(source).expanduser().resolve()
    with Image.open(source) as image:size=list(image.size)
    name = name or source.stem + '-' + uuid.uuid4().hex[:8]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', name):
        raise ValueError('Portable task name required')
    task = project / BUILD_DIR / 'tasks' / name
    if task.exists():
        raise FileExistsError('Use next to resume existing task: ' + str(task))
    goals = {'vector_first': True, 'single_page': True, 'clear_at_reuse_size': True,
             'semantic_completion': True, 'minimum_edit_level': 'component', 'paper_export': True, 'quality_driven_representation': True, 'context_chars': 9000, 'review_view_width': 720,
             'render_width': max(1600, size[0]), 'max_actions': 640,
             'source_part_quality': True, 'source_relative_layout': True, 'source_textbox_quality': True, 'source_contract_seals':True, 'source_catalog_review':True, 'source_recursion':True,
              'source_semantic_composition': True, 'source_feature_ledger':True, 'source_font_contract':True,
               'portable_editable_fonts':True, 'source_frame_plan':True, 'whole_quality_intent':True, 'all_neighbor_closure':True, 'max_issue_repairs':12,
             'max_branch_failures':2, 'component_first':True, **(objectives or {})}
    if goals.get('component_first') is not True:
        raise ValueError('New tasks require the complete component workflow')
    if any(goals[key] is not True for key in ('source_part_quality','source_relative_layout','source_feature_ledger','source_contract_seals','source_catalog_review')):
        raise ValueError('New tasks require independent parts/layout/original features; no agent shortcuts')
    if (type(goals['max_issue_repairs']) is not int or not 1<=goals['max_issue_repairs']<=32
            or type(goals['max_branch_failures']) is not int or not 1<=goals['max_branch_failures']<=2):
        raise ValueError('Use a bounded issue budget and at most two ineffective branch attempts')
    if goals.get('source_recursion') is not True:
        raise ValueError('New tasks require executable original-region recursion and leaf closure')
    if goals['source_semantic_composition'] is not True:
        raise ValueError('New tasks require original-bound semantic composition; it is not an agent shortcut')
    if goals['source_frame_plan'] is not True:
        raise ValueError('New tasks require frame/content planning before native drawing')
    if goals['whole_quality_intent'] is not True:
        raise ValueError('New tasks require whole purpose-specific policies and structured observations')
    if goals['source_textbox_quality'] is not True:
        raise ValueError('New tasks require original-only textbox/math quality; it is not an optional agent shortcut')
    if goals['source_font_contract'] is not True or goals['portable_editable_fonts'] is not True:
        raise ValueError('Source font identity and editable font delivery cannot be disabled for new tasks')
    if not 2500 <= goals['context_chars'] <= 32000 or not 400 <= goals['review_view_width'] <= 1600:
        raise ValueError('Explicit bounded context/view configuration required')
    # Validate external prerequisites before reserving an immutable task name.
    # A font/configuration failure must not require manual folder renaming.
    authority=goals.get('layout_authority')
    original_request=frame_plan._resource(project,authority) if authority else None
    caps = capabilities(configuration,project)
    native_input=Path(pptx).expanduser().resolve() if pptx else None
    if native_input and not native_input.is_file():raise ValueError('Uploaded partial PPT input absent')
    task.mkdir(parents=True)
    for folder in ('source', 'versions', 'scratch', 'views', 'components'):
        (task / folder).mkdir()
    original = task / 'source' / ('original' + source.suffix.lower())
    shutil.copyfile(source, original)
    state = {'schema': SCHEMA, 'task_id': name, 'project': str(project), 'created': time.time(),
             'source': _file(task, original), 'source_stem':source.stem, 'source_size': size, 'objectives': goals,
             'capabilities': caps, 'execution_contract':execution_contract.VERSION,
             'execution_policy':__import__(__package__+'.workflow_guard',fromlist=['POLICY']).POLICY,
             'stage': 'source_observation', 'analysis': None,
             'methods': {}, 'built': {}, 'scene': None, 'selected': None, 'active_candidate': None,
             'reviews': {}, 'issues': [], 'protected': {}, 'packet': None,
             'actions': 0, 'attempts': [], 'revision': 0, 'external_versions': [],
              'telemetry': {'packet_chars': 0, 'program_seconds': 0, 'cache_hits': 0}}
    if native_input:
        retained_input=task/'source/input-presentation.pptx';shutil.copyfile(native_input,retained_input)
        state['input_pptx']=_file(task,retained_input)
    authority=goals.pop('layout_authority',None)
    if authority:
        frozen_request=task/'source'/('user-layout-'+authority['sha256']+'.txt')
        shutil.copyfile(original_request,frozen_request)
        state['frame_authorities']=[_file(task,frozen_request)]
    from .font_collection import prepare as prepare_font_collection
    prepare_font_collection(state)
    lib = Library(project, scope=library_scope(state))
    lib.put('evidence', name + ':source', {'semantic_class': 'source_image',
            'original': lib.blob(source), 'size': size, 'state': 'immutable_evidence'})
    write_json(task / 'source' / 'profile.json', {'method': 'source-specific priorities',
               'metrics': 'diagnostic, non-compensating semantics and preservation'})
    write_json(task / 'source' / 'evidence.json', {'source': state['source'], 'size': size})
    from .catalog_source import activate
    activate(task,state)
    from .source_recursion import activate as activate_recursion
    activate_recursion(task,state)
    _save(task, state)
    return {'task': str(task), **next_packet(task)}


def _scene(task, state, override=None):
    analysis = state['analysis']
    semantic_composition.validate_relations(analysis.get('scene_relations',[]),'analysis.scene_relations')
    canvas = {'width': state['source_size'][0], 'height': state['source_size'][1],
              'unit': 'px', 'target_width_inches': analysis.get('target_width_inches',
                                                              state['source_size'][0]/96),
              'background_rgb': analysis.get('background_rgb', [255, 255, 255])}
    objects = []
    built = {**state['built'], **(override or {})}
    for comp in sorted(analysis['components'], key=lambda c: c.get('z', 0)):
        if comp['id'] in built:
            objects.extend(copy.deepcopy(built[comp['id']]['objects']))
    aliases={}
    for cid,item in built.items():
        roots=[o for o in item['method'].get('objects',[]) if not o.get('parent')]
        if len(roots)==1 and roots[0]['render_type']=='group' and roots[0]['id']!=cid:
            previous=aliases.setdefault(roots[0]['id'],cid)
            if previous!=cid:raise ValueError('Ambiguous renamed native root')
    actual_ids={o['id'] for o in objects}
    for o in objects:
        if o['render_type']=='connector':
            for field in ('source','target','source_anchor_object','target_anchor_object'):
                value=o['content'].get(field)
                if value not in actual_ids and value in aliases:o['content'][field]=aliases[value]
    return {'schema_version': '0.1', 'revision': state['revision'], 'canvas': canvas,
            'source': state['source'], 'evidence': _file(task, task/'source/evidence.json'),
            'profile': _file(task, task/'source/profile.json'), 'objects': objects,
            'relations': analysis.get('scene_relations', []), 'prototypes': []}


def _component(state, target):
    return next(c for c in state['analysis']['components'] if c['id'] == target)


def _validate_method(method,where='method',depth=0):
    """Check host container types before cache, state or geometry operations."""
    if not isinstance(method,dict):raise ValueError(where+' must be an object; omit an unselected construction')
    if depth>8:raise ValueError(where+' exceeds the bounded recursive construction depth')
    for field in ('parameters','source_bindings','native_asset','hd_asset','solid_svg','svg_asset','tool_geometry'):
        if field in method and not isinstance(method[field],dict):raise ValueError(where+'.'+field+' must be an object')
    for part,names in method.get('source_bindings',{}).items():
        if not isinstance(names,list) or not all(isinstance(n,str) and n for n in names):
            raise ValueError(where+'.source_bindings.'+str(part)+' must be a list of object IDs')
    for name in ('objects','children','recipe_instances','source_photos'):
        if name not in method:continue
        values=method[name]
        if not isinstance(values,list):raise ValueError(where+'.'+name+' must be a list of objects')
        for index,value in enumerate(values):
            at=where+'.'+name+'['+str(index)+']'
            if not isinstance(value,dict):raise ValueError(at+' must be an object')
            if name in ('children','recipe_instances'):_validate_method(value.get('method'),at+'.method',depth+1)
    def finite(value,at):
        if isinstance(value,(int,float)) and not isinstance(value,bool):
            try:valid=math.isfinite(value)
            except OverflowError:valid=False
            if not valid:raise ValueError(at+' must be finite')
        elif isinstance(value,dict):
            for key,item in value.items():finite(item,at+'.'+str(key))
        elif isinstance(value,list):
            for index,item in enumerate(value):finite(item,at+'['+str(index)+']')
    finite(method,where)


def _parts(task, state, component, method,depth=0,reusable=None):
    from .recipes import instantiate,RECIPES
    from .natural_owners import verify as verify_natural_owners
    _validate_method(method,depth=depth)
    cid = component['id']
    if depth>8:raise ValueError('Refine natural components within the bounded recursive depth')
    if method.get('recipe') in ('wireless_vehicle','natural_icon'):
        from .natural_catalog import validate_current
        validate_current(method.get('parameters',{}),state['source']['sha256'],state['source_size'],component['roi'])
    if depth==0 and cid in state['built']:
        before=state['built'][cid];nodes={o['id']:o for o in before['objects']};children={}
        for obj in before['objects']:children.setdefault(obj.get('parent'),[]).append(obj['id'])
        methods={cid:before['method']};components={cid:_component(state,cid)}
        def collect(method):
            for child in method.get('children',[]):
                methods[child['id']]=child['method'];components[child['id']]=child;collect(child['method'])
        collect(before['method']);reusable={'nodes':nodes,'children':children,'methods':methods,'components':components}
    def construction_context(comp):return {k:comp.get(k) for k in ('id','roi','bbox','rotation','semantic_class')}
    if reusable and cid in reusable['methods'] and identity(method)==identity(reusable['methods'][cid]) and construction_context(component)==construction_context(reusable['components'][cid]):
        pending=[cid];owned=set()
        while pending:
            name=pending.pop();owned.add(name);pending.extend(reusable['children'].get(name,[]))
        # A cache hit must preserve the retained native paint order. DFS
        # traversal reorders interleaved siblings from scoped native additions.
        kept=[copy.deepcopy(obj) for name,obj in reusable['nodes'].items() if name in owned]
        verify_natural_owners(kept,method,cid)
        if depth==0:
            from .catalog_source import verify_constructed
            verify_constructed(state,cid,kept)
        state['telemetry']['cache_hits']+=1
        return {'objects':kept,'method':copy.deepcopy(method),'fingerprint':identity(kept)}
    if method.get('asset_id'):
        lib=Library(state['project'], scope=library_scope(state));asset=lib.get(method['asset_id'])
        if asset is None or asset['kind']!='asset':raise ValueError('Unknown local component asset')
        payload=asset['payload']
        if payload['semantic_class']!=component['semantic_class'] or not set(component['parts'])<=set(payload['parts']):
            raise ValueError('Asset does not match the requested semantic class and parts')
        if payload.get('recipe_state')=='snapshot_only' or not payload.get('recipe'):
            if payload.get('representation') not in ('native','svg','mixed','raster') or not payload.get('root_name'):
                raise ValueError('Native asset needs a mapped saved group; refresh an unmapped user asset first')
            snapshot=lib.resolve(payload['pptx']);destination=task/'source'/('asset-'+payload['pptx']['sha256']+'.pptx')
            if not destination.exists():shutil.copyfile(snapshot,destination)
            method={'native_asset':{**_file(task,destination),'slide':payload.get('slide',1),'root_name':payload['root_name']},
                    'asset_id_used':method['asset_id'],'asset_revision':asset['revision']}
        else:method=read_json(lib.resolve(payload['recipe']))
        state['telemetry']['cache_hits']+=1
    if method.get('native_asset'):
        from .native_asset import load
        from .recipes import node
        load(task,method['native_asset'])
        objects=[node(cid,'group',component.get('bbox',component['roi']),
                      {'native_asset':method['native_asset']},semantic=component['semantic_class'])]
    elif method.get('hd_asset'):
        from .representation_trial import construct as construct_hd
        objects=construct_hd(task,state,component,method['hd_asset'])
    elif method.get('solid_svg'):
        from .solid_svg import construct
        objects=construct(task,component,method['solid_svg'])
    elif method.get('svg_asset'):
        from .vector_asset import validate as validate_svg
        from .recipes import node
        asset=method['svg_asset'];validate_svg(asset,task)
        objects=[node(cid,'svg',component.get('bbox',component['roi']),asset,semantic=component['semantic_class'])]
    elif method.get('children'):
        from .recipes import node
        children=method['children']
        if not 1<=len(children)<=128:raise ValueError('Bounded natural children required')
        objects=[node(cid,'group',component.get('bbox',component['roi']),semantic=component['semantic_class'])]
        seen={cid}
        for child in children:
            if not all(child.get(k) for k in ('id','semantic_class','source_note','parts','roi','method')):
                raise ValueError('Recursive child needs source meaning, extent and concrete method')
            _roi(child['roi'],state['source_size'])
            built=_parts(task,state,child,child['method'],depth+1,reusable)
            ids={o['id'] for o in built['objects']}
            if len(ids)!=len(built['objects']) or seen & ids:raise ValueError('Duplicate recursive native identity')
            seen |= ids;built['objects'][0]['parent']=cid;objects.extend(built['objects'])
    elif method.get('container_function'):
        from .container_functions import construct as construct_container
        objects=construct_container(task,state,component,method['container_function'])
    elif method.get('signal_function'):
        from .signal_semantics import construct as construct_signal
        objects=construct_signal(task,state,component,method['signal_function'])
    elif method.get('source_fit'):
        from .source_fit import construct
        objects=construct(task,state,component,method['source_fit'])
    elif method.get('measured_outline'):
        from .source_shapes import construct
        objects=construct(task,state,component,method['measured_outline'])
    elif method.get('paint'):
        from .paint_paths import construct
        objects=construct(task,state,component,method['paint'])
    elif method.get('recipe'):
        recipe=method['recipe'];parameters=method.get('parameters',{})
        if recipe not in RECIPES:raise ValueError('Unknown recipe: '+recipe)
        lib=Library(state['project'], scope=library_scope(state))
        import inspect
        recipe_source=Path(inspect.getsourcefile(RECIPES[recipe]))
        dependencies={'code:recipes':digest(Path(__file__).with_name('recipes.py')), 'code:recipe_owner':digest(recipe_source)}
        cache_parameters=parameters
        if recipe in ('wireless_vehicle','natural_icon'):
            from .semantic_icons import construction_parameters
            from .natural_catalog import parameters as resolve_default,validate_current
            validate_current(parameters,state['source']['sha256'],state['source_size'],component['roi'])
            parameters=resolve_default(parameters)
            cache_parameters=construction_parameters(parameters)
            dependencies['code:semantic_curves']=digest(Path(__file__).with_name('semantic_curves.py'))
            dependencies['code:natural_catalog']=digest(Path(__file__).with_name('natural_catalog.py'))
        key='recipe:'+identity({'recipe':recipe,'parameters':cache_parameters})
        local=lib.cache_get(key,dependencies)
        if local is None:
            local=RECIPES[recipe](parameters);lib.cache_put(key,local,dependencies)
        else:state['telemetry']['cache_hits']+=1
        objects = instantiate(recipe, parameters, cid,
                              component.get('bbox', component['roi']),
                              evidence_status=component.get('status', 'observed'),local_objects=local)
    else:
        if method.get('tool_geometry'):
            from .shape_provider import load_geometry
            raw=load_geometry(task,method['tool_geometry'],state['source']['sha256'])
            raw.extend(copy.deepcopy(method.get('objects',[])))
        else:raw = copy.deepcopy(method.get('objects', []))
        if not raw:
            raise ValueError('Native component needs a recipe or self-contained objects')
        # Source-coordinate mode allows connectors/OMML/path data without a
        # lossy generic SVG import. It is bounded by the existing Scene schema.
        if method.get('coordinate_space', 'source_px') != 'source_px':
            raise ValueError('Explicit source-pixel coordinates required')
        objects = raw
        roots = [o for o in objects if not o.get('parent')]
        if len(roots) == 1 and roots[0]['render_type'] == 'group':
            old_root = roots[0]['id']
            roots[0]['id'] = cid
            for obj in objects:
                if obj.get('parent') == old_root:
                    obj['parent'] = cid
                for field in ('source','target','source_anchor_object','target_anchor_object'):
                    if obj.get('content',{}).get(field)==old_root:obj['content'][field]=cid
        else:
            from .recipes import node
            objects.insert(0, node(cid, 'group', component.get('bbox', component['roi']),
                                   semantic=component['semantic_class']))
            for obj in objects[1:]:
                if not obj.get('parent'):
                    obj['parent'] = cid
        for obj in objects:
            obj.setdefault('versions', {k: 0 for k in ('content', 'structure', 'style', 'placement')})
            obj.setdefault('locks', {k: False for k in ('content', 'structure', 'style', 'placement')})
            obj.setdefault('evidence_status', component.get('status', 'observed'))
            obj.setdefault('style', {})
            obj.setdefault('content', {})
        instances=method.get('recipe_instances',[])
        if not isinstance(instances,list) or len(instances)>128:
            raise ValueError('Bounded typed recipe_instances required for a mixed scene')
        seen_instances=set()
        for row in instances:
            if (not isinstance(row,dict) or not all(row.get(k) for k in ('id','source_roi','source_note','parts','method'))
                    or row['id'] in seen_instances):
                raise ValueError('Each recipe instance needs a unique group, source ROI, anatomy and method')
            seen_instances.add(row['id']);nodes={o['id']:o for o in objects}
            target=nodes.get(row['id'])
            if not target or target['render_type']!='group' or target['id']==cid:
                raise ValueError('A mixed-scene recipe instance must replace its own existing child group')
            _roi(row['source_roi'],state['source_size'])
            x,y,w,h=row['source_roi'];ox,oy,ow,oh=component['roi']
            if x<ox or y<oy or x+w>ox+ow+.001 or y+h>oy+oh+.001:
                raise ValueError('Recipe instance source ROI must belong to its current source owner')
            if row['method'].get('recipe') not in ('wireless_vehicle','natural_icon'):
                raise ValueError('Use a supported executable natural recipe for a mixed-scene instance')
            child={'id':target['id'],'roi':row['source_roi'],'bbox':target['bbox'],
                   'semantic_class':target.get('semantic_type','natural_icon'),'parts':row['parts'],
                   'source_note':row['source_note']}
            replacement=_parts(task,state,child,row['method'],depth+1,reusable)['objects']
            replacement[0]['parent']=target.get('parent')
            owned={target['id']}
            while True:
                expanded=owned|{o['id'] for o in objects if o.get('parent') in owned}
                if expanded==owned:break
                owned=expanded
            kept_ids=set(nodes)-owned
            if kept_ids & {o['id'] for o in replacement}:
                raise ValueError('Recipe instance collides with another current native object')
            merged=[]
            for obj in objects:
                if obj['id']==target['id']:merged.extend(replacement)
                elif obj['id'] not in owned:merged.append(obj)
            objects=merged
        for obj in objects:
            if (obj['render_type']=='group' and obj.get('semantic_type') in ('wireless_vehicle','top_view_vehicle','vehicle_icon')
                    and not obj.get('content',{}).get('natural_icon')):
                raise ValueError('Declared natural vehicle '+obj['id']+' requires a source-bound natural model; use recursive children or recipe_instances, including compatible catalog source_traits. Raw generic parts cannot replace its observed anatomy.')
    # Canonical absence of an outline applies to raw methods as well as recipes.
    # Preserve the same native result during a later scoped owner reconstruction.
    for obj in objects:
        if obj['style'].get('stroke') is None and obj['style'].get('line_width')==0:
            obj['style'].pop('line_width')
    original_photos={}
    if method.get('source_photos'):
        from .source_photos import construct as construct_original_photos
        bindings=copy.deepcopy(method.get('source_bindings',{}))
        if not isinstance(bindings,dict):raise ValueError('Original photo source_bindings must be an object')
        for item in method['source_photos']:
            if item.get('part') in bindings and bindings[item['part']]!=[item.get('object')]:
                raise ValueError('Original photo binding conflicts with the declared part/owner')
        objects,original_photos=construct_original_photos(task,state,component,objects,method['source_photos'])
        for name,receipt in original_photos.items():bindings[receipt['part']]=[name]
        method={**method,'source_bindings':bindings}
    if any(o['render_type']=='photo' and o.get('semantic_type') not in ('data_image','experimental_image') and o['id'] not in original_photos for o in objects) and not method.get('hd_asset'):
        raise ValueError('New raster artwork needs a bound important-quality trial through hd_asset; do not bypass it with raw photo objects')
    if 'rotation' in component:
        objects[0]['style']['rotation'] = component['rotation']
    verify_natural_owners(objects,method,cid)
    if depth==0:
        from .catalog_source import verify_constructed
        verify_constructed(state,cid,objects)
    return {'objects': objects, 'method': method, 'fingerprint': identity(objects)}


def _preview(task, state, candidate, roi, key):
    """One source window/display grid; native resolution cannot alter scale."""
    from PIL import Image
    images = [('source', _path(task, state['source']['path']))]
    if candidate and candidate.get('preview'):
        images.append(('current', _path(task, candidate['preview']['path'])))
    canvas_w,canvas_h = state['source_size']
    x,y,w,h = roi
    window = (max(0,math.floor(x)),max(0,math.floor(y)),
              min(canvas_w,math.ceil(x+w)),min(canvas_h,math.ceil(y+h)))
    width,height = window[2]-window[0],window[3]-window[1]
    desired = state['objectives']['review_view_width']
    factor = min(4,desired/max(1,width))
    display_size = (max(1,round(width*factor)),max(1,round(height*factor)))
    output = []
    for role,path in images:
        ref=state['source'] if role=='source' else candidate['preview']
        if digest(path)!=ref['sha256']:raise ValueError('Observation input changed: '+role)
        from .resource_facts import image_dimensions,image_region
        image_w,image_h=image_dimensions(path,ref['sha256'])
        sx,sy=image_w/canvas_w,image_h/canvas_h
        # Same fractional sampling box, one pass; no local registration.
        box = (window[0]*sx,window[1]*sy,window[2]*sx,window[3]*sy)
        with image_region(path,[('resize',display_size,Image.Resampling.LANCZOS,box)],ref['sha256']) as crop:
            from .context_efficiency import crop_file
            target,reused=crop_file(task,crop)
            telemetry=state.setdefault('telemetry',{})
            telemetry['view_cache_hits']=telemetry.get('view_cache_hits',0)+int(reused)
            telemetry['view_cache_misses']=telemetry.get('view_cache_misses',0)+int(not reused)
        output.append({'role':role,**_file(task,target),'roi':roi,
                       'source_pixel_window':list(window),'display_size':list(display_size),
                       'mapping':'one fixed source-canvas window; no local registration',
                       'meaning':'observation enlargement, not reconstructed asset'})
    return output


@cached_metrics
def _metrics(task, state, candidate, roi):
    """Local raw diagnostics; no threshold or semantic pass inferred."""
    import numpy as np
    from PIL import Image
    from skimage.metrics import structural_similarity
    from scipy.ndimage import sobel
    from .resource_facts import image_dimensions,image_region,resource_library
    library=resource_library(state['project'])
    if digest(_path(task,state['source']['path']))!=state['source']['sha256'] or digest(_path(task,candidate['preview']['path']))!=candidate['preview']['sha256']:
        raise ValueError('Raw metric source/preview changed')
    x, y, w, h = roi
    box = tuple(map(round, (x, y, x+w, y+h)))
    reference = image_region(_path(task,state['source']['path']),[('crop',box)],state['source']['sha256'])
    output_w,output_h=image_dimensions(_path(task,candidate['preview']['path']),candidate['preview']['sha256'])
    sx,sy=output_w/state['source_size'][0],output_h/state['source_size'][1]
    crop = image_region(_path(task,candidate['preview']['path']),[('crop',tuple(map(round,(x*sx,y*sy,(x+w)*sx,(y+h)*sy)))),
        ('resize',reference.size,Image.Resampling.LANCZOS)],candidate['preview']['sha256'])
    import hashlib,platform,scipy,skimage,PIL
    policy=__import__(__package__+'.quality_policy',fromlist=['measure'])
    dependencies={'source':state['source']['sha256'],'source_pixels':hashlib.sha256(reference.tobytes()).hexdigest(),
        'candidate_pixels':hashlib.sha256(crop.tobytes()).hexdigest(),'sampling':identity({'roi':roi,'canvas':state['source_size'],'reference_size':list(reference.size),'rule':'registered-round-crop-lanczos'}),
        'code':identity(__import__('inspect').getsource(_metrics)),'quality_policy':digest(policy.__file__),
        'libraries':identity({'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__,'skimage':skimage.__version__,'pillow':PIL.__version__})}
    key='roi-metrics:'+identity(dependencies)
    previous=library.cache_get(key,dependencies)
    if previous is not None:
        state['telemetry']['cache_hits']=state['telemetry'].get('cache_hits',0)+1
        state['telemetry']['metric_cache_hits']=state['telemetry'].get('metric_cache_hits',0)+1
        return previous
    state['telemetry']['metric_cache_misses']=state['telemetry'].get('metric_cache_misses',0)+1
    a, b = np.asarray(reference).astype(float), np.asarray(crop).astype(float)
    mse = float(np.mean((a-b)**2))
    metrics = {'mae': float(np.abs(a-b).mean()), 'psnr': 10*math.log10(255**2/mse) if mse else None,
               'ssim': float(structural_similarity(a, b, data_range=255, channel_axis=2))
                       if min(a.shape[:2]) >= 7 else None,
               'source_edge_energy': float(np.abs(sobel(a.mean(2))).mean()),
               'output_edge_energy': float(np.abs(sobel(b.mean(2))).mean())}
    ea=np.abs(sobel(a.mean(2)));eb=np.abs(sobel(b.mean(2)))
    am=ea>max(15,float(np.percentile(ea,75)));bm=eb>max(15,float(np.percentile(eb,75)))
    metrics['edge_iou']=float(np.count_nonzero(am&bm)/max(1,np.count_nonzero(am|bm)))
    from .quality_policy import measure
    metrics.update(measure(reference,crop))
    result={'values': metrics, 'scope': roi, 'status': 'DIAGNOSTIC_NOT_SEMANTIC_ACCEPTANCE',
            'limits':'Pixel/edge measures do not judge scientific truth, native editability, inferred HD artwork or protected attributes'}
    library.cache_put(key,result,dependencies)
    return result


def _priorities(component):
    """Source-class defaults; measured metrics never compensate semantic gates."""
    role=component.get('paint_role');cls=component.get('semantic_class','')
    if role=='scientific_display_texture' or 'scientific' in cls:
        weights={'semantics':.50,'geometry':.35,'appearance':.15}
    elif role in ('illustration','background'):
        weights={'semantics':.30,'geometry':.20,'appearance':.50}
    else:weights={'semantics':.40,'geometry':.40,'appearance':.20}
    custom=component.get('dimension_weights')
    if custom:
        if set(custom)!=set(DIMENSIONS) or any(not isinstance(v,(int,float)) or not 0<v<=1 for v in custom.values()):
            raise ValueError('Source-specific dimension weights must cover all three positive dimensions')
        total=sum(custom.values());weights={k:v/total for k,v in custom.items()}
    from .quality_policy import profile
    typed=profile(component)
    return {'weights':weights,'typed_profile':typed,'hard_gates':typed['hard_gates'],
            'focus':component.get('metric_focus',['edge_iou','ssim','psnr']),
            'aggregation':'Only host-observed dimension scores with reasons may form a composite; raw pixel similarity is diagnostic'}


def _packet(task, state, kind, target, objective, roi=None, extra=None):
    baseline = state['selected']['pptx']['sha256'] if state['selected'] else None
    packet_id = kind + '-' + str(state['revision']) + '-' + uuid.uuid4().hex[:10]
    extra=copy.deepcopy(extra or {})
    if 'source' in extra:
        source=extra.pop('source')
        if source==state['source']:extra['source_image']=source
        elif source!=state['source']['sha256']:
            raise ValueError('Source payload cannot override the immutable work-packet identity')
    packet = {'packet_id': packet_id, 'kind': kind, 'target': target,
              'objective': objective, 'baseline': baseline, 'source': state['source']['sha256'],
              'original_view':{**state['source'],'roi':[0,0,*state['source_size']]},
              'revision': state['revision'], 'views': _preview(task, state,
              None if kind in ('source_inventory','font_binding') else state['active_candidate'] or state['selected'],
              roi or [0,0,*state['source_size']], packet_id), **(extra or {})}
    candidate=state.get('active_candidate') or state.get('selected')
    if candidate and candidate.get('render') and roi:
        bounds=_path(task,candidate['render']['path']).parent/'text-bounds.json'
        if bounds.is_file():
            from .component_report import _native_ink
            ink=_native_ink(_path(task,candidate['pptx']['path']),bounds,state['source_size'])
            x,y,w,h=roi
            located=[{'id':name,'ink_source_px':box} for name,box in ink.items()
                     if box[0]<x+w and box[0]+box[2]>x and box[1]<y+h and box[1]+box[3]>y]
            located.sort(key=lambda item:abs(item['ink_source_px'][0]+item['ink_source_px'][2]/2-x-w/2)
                         +abs(item['ink_source_px'][1]+item['ink_source_px'][3]/2-y-h/2))
            packet['office_ink']={'items':located[:8],'file':_file(task,bounds),
                   'meaning':'actual Office text/equation ink bounds in source pixels, not a visible-contour overlap verdict'}
    if kind in ('observation','source_spec','review'):
        from .source_ocr import packet_anchors
        packet['original_word_anchors']=packet_anchors(task,state,roi or [0,0,*state['source_size']])
    if kind in ('source_spec','review'):
        from .source_quality import SOURCE_CORRECTION_KINDS
        packet['source_correction_kinds']=list(SOURCE_CORRECTION_KINDS)
        if kind=='review' and candidate and roi:
            from .textbox_quality import packet_diagnostics
            packet['textbox_diagnostics']=packet_diagnostics(task,state,candidate,roi)
    elif kind=='repair':
        from .source_quality import CAUSE_STAGES
        packet['allowed_cause_stages']=list(CAUSE_STAGES)
    if state.get('objectives',{}).get('component_first'):
        from .component_workflow import implementation
        packet['component_implementation']=implementation()
    from .packet_compaction import compact
    if not state.get('objectives',{}).get('component_first'):
        from .candidate_cost import attach
        cost=attach(task,state)
        if cost:packet['file_cost']=cost
    from .context_control import view_requests
    packet['view_requests']=view_requests(task,state,packet['views'],owner=target,rubric=kind)
    from .workflow_guard import enabled as controlled
    if controlled(state):
        from .incremental_contract import template
        packet=template(task,state,packet)
    full_packet=packet
    packet=compact(task,packet,min(8000,state['objectives']['context_chars']) if state.get('objectives',{}).get('component_first') else state['objectives']['context_chars'])
    if len(canonical(packet).decode('utf-8')) > state['objectives']['context_chars']:
        # Large geometric data stays available by reference; do not silently
        # truncate evidence, grants or the result contract.
        raise ValueError('Work packet exceeds the context budget; narrow it or reference geometric data')
    state['packet'] = packet
    if not state.get('objectives',{}).get('component_first'):
        from .context_efficiency import telemetry
        telemetry(state,full_packet,packet)
    _save(task, state)
    write_json(task/'current-packet.json', packet)
    return packet


def _accept_analysis(task, state, analysis):
    if not isinstance(analysis,dict):raise ValueError('analysis must be an object')
    if analysis.get('source_hash') != state['source']['sha256']:
        raise ValueError('Analysis must reference the actually observed original')
    if not analysis.get('theme') or not analysis.get('components'):
        raise ValueError('Independent source theme and natural components required')
    semantic_composition.validate_relations(analysis.get('scene_relations',[]),'analysis.scene_relations')
    components = analysis['components']
    if not isinstance(components,list) or not all(isinstance(c,dict) for c in components):
        raise ValueError('analysis.components must be a list of objects')
    # Validate every declaration before popping methods or changing any state.
    for index,comp in enumerate(components):
        at='analysis.components['+str(index)+']'
        if not isinstance(comp.get('id'),str):raise ValueError(at+'.id must be a portable string')
        _roi(comp.get('roi'),state['source_size'])
        for field in ('semantic_class','source_note'):
            if not isinstance(comp.get(field),str) or not comp[field].strip():
                raise ValueError(at+'.'+field+' must be a nonempty string')
        for field in ('parts','depends_on'):
            values=comp.get(field,[])
            if not isinstance(values,list) or not all(isinstance(v,str) and v.strip() for v in values):
                raise ValueError(at+'.'+field+' must be a list of nonempty strings')
        if comp.get('method') is not None:_validate_method(comp['method'],at+'.method')
    ids = [c['id'] for c in components]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]*', i) for i in ids):
        raise ValueError('Unique portable component IDs required')
    catalog_review=None
    if state.get('objectives',{}).get('source_catalog_review'):
        from .catalog_source import compile_review
        catalog_review=compile_review(state,analysis.get('catalog_review'),components)
    for comp in components:
        _roi(comp['roi'], state['source_size'])
        if not comp.get('semantic_class') or not comp.get('source_note') or not comp.get('parts'):
            raise ValueError('Source-grounded class, note and natural parts required: ' + comp['id'])
        if not set(comp.get('depends_on', [])) <= set(ids):
            raise ValueError('Unknown component dependency')
        comp.setdefault('status', 'requires_source_spec' if source_quality.enabled(state) else 'unresolved')
        comp.setdefault('view', 'source_view')
        comp.setdefault('review_unit', True)
        comp.setdefault('edit_targets', ['move', 'resize', 'copy'])
        from .quality_policy import profile
        comp['quality_profile']=profile(comp)
        comp.setdefault('style_tags', [])
        if comp.get('method'):
            state['methods'][comp['id']] = comp.pop('method')
    # Reject dependency cycles now, rather than silently finishing an empty queue.
    pending, done = set(ids), set()
    while pending:
        ready = {c['id'] for c in components if c['id'] in pending and
                 set(c.get('depends_on', [])) <= done}
        if not ready:
            raise ValueError('Source plan contains a dependency cycle')
        done |= ready; pending -= ready
    state['analysis'] = analysis
    if catalog_review is not None:
        from .catalog_source import bind
        bind(task,state,catalog_review)
    inventory=analysis.get('source_inventory')
    if analysis.get('source_inventory_ref'):
        ref=analysis['source_inventory_ref']
        if digest(_path(task,ref['path']))!=ref['sha256']:raise ValueError('Source inventory reference changed')
        inventory=read_json(_path(task,ref['path']))
    if inventory:
        from .source_features import bind
        bind(task,state,inventory)
    if source_quality.enabled(state):
        source_quality.initialize(state)
    state['stage'] = 'source_refinement' if source_quality.refinement(state) else 'construction'
    from .source_recursion import initialize as initialize_recursion
    initialize_recursion(task,state)
    write_json(task/'source/analysis.json', analysis)
    Library(state['project'], scope=library_scope(state)).put('task', state['task_id'] + ':analysis',
            {'semantic_class': 'source_plan', 'analysis': analysis, 'state': 'source_observed'},
            {state['task_id']+':source': state['source']['sha256']})


def _candidate(task, state, scene, *, baseline=None, allowed=None, reason=None, transaction=None):
    if state.get('component_workflow') and state.get('objectives',{}).get('component_first'):
        from .component_constructor import construct
        return construct(task,state,scene,baseline,allowed,reason,transaction=transaction)
    if baseline and state.get('component_workflow'):
        from .component_workflow import guard_changes
        guard_changes(task,state,scene,allowed)
    from .build import build
    from .semantic_curves import compile_scene as compile_curves
    scene=compile_curves(scene,allowed)
    if allowed is not None:scene['curve_write_scope']=allowed
    font_scene=scene
    if baseline:
        from .native_commit import donor_scene
        font_scene=donor_scene(scene,allowed)
    font_contract.auto_bind(task,state,font_scene)
    if font_contract.missing(font_scene,state):
        frozen=task/'scratch'/('font-pending-'+identity(scene)[:16]+'.json')
        write_json(frozen,scene)
        state['font_pending_candidate']={'scene':_file(task,frozen),'baseline':baseline,'allowed':allowed,'reason':reason}
        state['stage']='font_binding';state['packet']=None
        _save(task,state)
        return None
    if baseline:
        bound=font_contract.bind_scene(task,state,font_scene)
        bound_nodes={o['id']:o for o in bound['objects']}
        for i,original in enumerate(scene['objects']):
            if original['id'] in bound_nodes:scene['objects'][i]=bound_nodes[original['id']]
        font_scene=bound
    else:scene=font_contract.bind_scene(task,state,scene)
    if source_quality.enabled(state) and not baseline:
        for owner,built in state['built'].items():
            source_quality.bind_objects(state,owner,built)
    scene = semantic_composition.prepare_scene(task,state,scene,baseline,allowed)
    if frame_plan.enabled(state):
        if not state.get('frame_plan'):
            raise ValueError('Freeze frame/content plan before drawing')
        scene['frame_plan']=state['frame_plan']
        scene=frame_plan.compile_scene(scene,task,allowed)
    number = state['revision'] + 1
    folder = task/'versions'/('r' + str(number).zfill(3))
    while folder.exists():
        # Preserve an interrupted/failed tool attempt without reusing its path.
        number+=1
        folder=task/'versions'/('r'+str(number).zfill(3))
    folder.mkdir()
    scene_file = folder/'scene.json'
    write_json(scene_file, scene)
    begin = time.monotonic()
    pptx = folder/'drawing.pptx'
    if baseline:
        from .native_commit import merge_native,donor_scene
        donor = folder/'donor.pptx'
        build(donor_scene(scene,allowed), task, donor)
        if any(fields==['replace_component'] for fields in allowed.values()):
            from .scoped_asset_commit import merge as merge_component
            components={key:fields for key,fields in allowed.items() if fields==['replace_component']}
            leaves={key:fields for key,fields in allowed.items() if fields!=['replace_component']}
            if leaves:
                nodes={o['id']:o for o in scene['objects']}
                for key in leaves:
                    parent=key
                    while parent in nodes:
                        if parent in components:raise ValueError('A subtree replacement cannot mix a child property grant')
                        parent=nodes[parent].get('parent')
                intermediate=folder/'component-stage.pptx'
                merge_component(_path(task,baseline['pptx']['path']),donor,components,intermediate)
                merge_native(intermediate,donor,leaves,pptx)
            else:
                merge_component(_path(task,baseline['pptx']['path']),donor,components,pptx)
        else:
            merge_native(_path(task, baseline['pptx']['path']), donor, allowed, pptx)
    else:
        construction=build(scene, task, pptx)
    if baseline and not font_contract.requests(font_scene):
        from .saved_font_retention import verify as verify_saved_fonts
        font_delivery=verify_saved_fonts(_path(task,baseline['pptx']['path']),pptx)
    else:font_delivery=font_contract.finalize(scene,pptx) if baseline else construction['font_delivery']
    if font_delivery['embedding']['status']=='FONT_EMBEDDING_PROVIDER_REQUIRED' and state['capabilities'].get('windows_office',{}).get('available'):
        try:
            font_delivery=font_contract.deliver_with_provider(font_scene,pptx,state['capabilities'],folder/'font-provider')
        except (ValueError,RuntimeError,OSError,__import__('subprocess').TimeoutExpired) as error:
            font_delivery['provider_failure']={'reason':str(error),'scope':'staged font save; no source or selected baseline changed'}
    from .relative_layout import guard_saved
    layout_guard = guard_saved(task, state, pptx, baseline, allowed)
    from .textbox_quality import guard_saved as text_guard
    typography_guard = text_guard(task,state,pptx,baseline,allowed)
    composition_guard = semantic_composition.guard_saved(task,state,pptx,baseline,allowed)
    state['telemetry']['program_seconds'] += time.monotonic()-begin
    candidate = {'revision': number, 'scene': _file(task, scene_file),
                 'pptx': _file(task, pptx), 'reason': reason, 'allowed': allowed,
                 'baseline': baseline['pptx']['sha256'] if baseline else None,
                  'relative_layout_guard': layout_guard, 'textbox_guard':typography_guard,
                  'semantic_composition_guard':composition_guard,'font_delivery':font_delivery}
    lib = Library(state['project'], scope=library_scope(state))
    candidate['snapshot'] = lib.blob(pptx)
    # Persist this real saved drawing before a host export can fail. The
    # selected baseline and pending replacement methods remain distinct.
    state['revision']=number;state['active_candidate']=candidate
    state['scene']=candidate['scene'];state['stage']='host_render'
    # The exact prebuild Scene is recoverable until native bytes have actually
    # been saved. A failed build keeps it; an export failure resumes this saved
    # candidate instead of rebuilding or measuring a nonexistent preview.
    state.pop('font_pending_candidate',None)
    state['packet']=None  # The prebuild repair packet belongs to the old revision.
    if baseline:state['review_queue']=['repair:'+reason['id']]
    _save(task,state)
    write_json(folder/'construction.json',{'candidate':candidate,
               'scope':'Saved actual native drawing; render and quality observation remain pending'})
    if font_delivery['embedding']['status']=='FONT_EMBEDDING_PROVIDER_REQUIRED':
        state['stage']='font_delivery'
        if not baseline:
            state['review_queue']=['whole']+source_quality.queue(state)+['scan-'+str(i) for i in range(6)]
            state['reviews']={}
        _save(task,state)
        return candidate
    if (state['capabilities'].get('saved_render_available') or state['capabilities']['libreoffice']['available']) and state.get('render_dispatch',{}).get('mode')!='native_host_tool':
        begin = time.monotonic()
        render_saved(pptx, folder/'render', state['capabilities'], state['objectives']['render_width'])
        state['telemetry']['program_seconds'] += time.monotonic()-begin
        candidate['preview'] = _file(task, folder/'render/Final_preview.png')
        candidate['render'] = _file(task, folder/'render/render.json')
        _save(task,state)
        if semantic_composition.enabled(state):
            semantic_composition.capture_portable(task,state,candidate)
            frame_plan.register_failures(task,state,candidate)
            semantic_composition.register_failures(task,state,candidate)
    state['revision'] = number
    state['active_candidate'] = candidate
    state['scene'] = candidate['scene']
    state['stage'] = 'review' if candidate.get('preview') else 'host_render'
    if not baseline and source_quality.enabled(state):
        for owner, built in state['built'].items():
            source_quality.bind_objects(state, owner, built)
        state['review_queue'] = ['whole'] + source_quality.queue(state) + ['scan-'+str(i) for i in range(6)]
        state['reviews'] = {}
    elif not baseline:
        units = [c['id'] for c in state['analysis']['components'] if c.get('review_unit')]
        # Independent source coverage is spatial, not a rendering-node inventory.
        state['review_queue'] = ['whole'] + units + ['scan-'+str(i) for i in range(6)]
        state['reviews'] = {}
    else:
        state['review_queue'] = ['repair:' + reason['id']]
    _event(task, 'candidate', {'revision': number, 'pptx': candidate['pptx'], 'reason': reason})
    return candidate


def _review_roi(state, target):
    width, height = state['source_size']
    value = source_quality.unit(state, target)
    if value is not None:
        return value['roi']
    if target == 'whole':
        return [0, 0, width, height]
    if target.startswith('scan-'):
        i = int(target.split('-')[-1]); x, y = i%3, i//3
        return [x*width/3, y*height/2, width/3, height/2]
    if target.startswith('repair:'):
        candidate = state.get('active_candidate')
        if candidate and candidate.get('reason',{}).get('check_roi'):
            return candidate['reason']['check_roi']
        return next(i['roi'] for i in state['issues'] if i['id'] == target.split(':',1)[1])
    if target.startswith('local-edit:'):return state['user_edit']['check_roi']
    if target.startswith('followup:'):return state['followup'][target]['roi']
    return _component(state, target)['roi']


@transaction
def prioritize(task,request):
    """Choose an already observed issue; never suppress its peers or targets."""
    task,state=_state(task);packet=state.get('packet') or {}
    if (state.get('pending_built') or packet.get('kind') not in (None,'repair')
        or state.get('active_candidate') and state['active_candidate']['pptx']['sha256']!=state['selected']['pptx']['sha256']):
        raise ValueError('Observe the pending saved result before scheduling another repair')
    if request.get('baseline_hash')!=state['selected']['pptx']['sha256'] or not request.get('reason'):
        raise ValueError('Prioritization must bind the saved best and explain expected information/gain')
    issue=next(i for i in state['issues'] if i['id']==request['issue_id'] and i['status']=='open')
    state['packet']=None;state['active_candidate']=None;state['repair_priority']=request
    state.setdefault('deferred_review_queue',[]).extend(v for v in state.get('review_queue',[])
        if v not in state.get('deferred_review_queue',[]))
    state['review_queue']=[];_save(task,state);_event(task,'located_repair_prioritized',request)
    return next_packet(task)


@transaction
def revisit(task, request):
    """Observe one new discrepancy on the saved best; never rebuild the page."""
    task,state=_state(task)
    selected=state['selected']
    packet=state.get('packet') or {};active=state.get('active_candidate')
    if (state.get('pending_built') or packet and packet.get('kind')!='repair'
            or active and (not selected or active['pptx']['sha256']!=selected['pptx']['sha256'])):
        raise ValueError('Finish the pending actual-result work packet first')
    if packet:_event(task,'repair_packet_deferred_for_source_observation',{'packet':packet['packet_id']})
    state['packet']=None
    if not selected or request.get('baseline_hash')!=selected['pptx']['sha256']:
        raise ValueError('Revisit must bind the actual selected PPTX')
    _roi(request.get('roi'),state['source_size'])
    if not request.get('reason'):raise ValueError('Located new observation reason required')
    target='followup:'+uuid.uuid4().hex[:12]
    state.setdefault('followup',{})[target]={'roi':request['roi'],'reason':request['reason']}
    state['review_queue']=[target]+[v for v in state.get('review_queue',[]) if v!=target];state['stage']='review';state['active_candidate']=selected
    _save(task,state);_event(task,'revisit',{'target':target,**state['followup'][target]})
    return next_packet(task)


@transaction
def refresh_render(task, configuration=None,*,issue=None,cause=None,strategy_branch=None):
    """Re-render the unchanged saved PPTX after a real host/font change."""
    task,state=_state(task)
    if state.get('pending_built') or state.get('rule_pending_built') or (state['packet'] and not (issue and state['packet']['kind']=='repair')):
        raise ValueError('Finish pending local work before refreshing its renderer')
    chosen=state['selected'] or state['active_candidate']
    if not chosen:raise ValueError('Saved native work is required')
    if configuration:state['capabilities']=capabilities(configuration,state['project'])
    number=state['revision']+1;folder=task/'versions'/('render-'+str(number).zfill(3))
    while folder.exists():number+=1;folder=task/'versions'/('render-'+str(number).zfill(3))
    folder.mkdir();pptx=folder/'drawing.pptx';shutil.copyfile(_path(task,chosen['pptx']['path']),pptx)
    composition_guard=semantic_composition.guard_saved(task,state,pptx,chosen,{})
    render_saved(pptx,folder/'render',state['capabilities'],state['objectives']['render_width'])
    candidate={**chosen,'revision':number,'pptx':_file(task,pptx),'preview':_file(task,folder/'render/Final_preview.png'),
               'render':_file(task,folder/'render/render.json'),'reason':{'kind':'render_refresh','previous_render':chosen.get('render')}}
    candidate['semantic_composition_guard']=composition_guard
    if semantic_composition.enabled(state):
        semantic_composition.capture_portable(task,state,candidate)
    frame_plan.register_failures(task,state,candidate)
    semantic_composition.register_failures(task,state,candidate)
    state['revision']=number;state['active_candidate']=candidate;state['stage']='review';state['packet']=None
    if issue:
        actual_issue=next(i for i in state['issues'] if i['id']==issue['id'])
        actual_issue['attempt_count']=actual_issue.get('attempt_count',0)+1
        related=[i['id'] for i in state['issues'] if i['status']=='open' and i['id']!=issue['id'] and
                 i['property']==issue['property'] and i.get('cause_hint')==issue.get('cause_hint')]
        candidate['reason'].update(id=issue['id'],related_issues=related,cause=cause,check_roi=[0,0,*state['source_size']],
            strategy_branch=strategy_branch,signature=identity({'source':state['source']['sha256'],'renderer':state['capabilities']['fingerprint'],'cause_stage':(cause or {}).get('stage')}))
        state['review_queue']=['repair:'+issue['id']];state['pending_built']={}
    else:state['review_queue']=['whole']
    _save(task,state);_event(task,'render_refresh',{'revision':number,'pptx_hash':digest(pptx),'capabilities':state['capabilities']['fingerprint']})
    return next_packet(task)


@transaction
def authorize_edit(task,request):
    """Translate an actual user request into immutable, narrow tool authority."""
    from .agent_edit import freeze
    task,state=_state(task)
    if state['selected'] and digest(_path(task,state['selected']['pptx']['path']))!=state['selected']['pptx']['sha256']:
        raise ValueError('Adopt the user-edited file with sync before a local edit')
    with writer(task):
        grant=freeze(task,state,request);state['user_edit']=grant
        state['stage']='local_edit';_save(task,state)
    return next_packet(task)


def _user_edit_candidate(task,state,result):
    from .agent_edit import apply_native,apply_raster
    grant=state['user_edit'];proof_file=_path(task,grant['path'])
    if digest(proof_file)!=grant['sha256']:raise ValueError('Frozen user authority changed')
    proof=read_json(proof_file);baseline=state['selected']
    if proof['baseline_hash']!=baseline['pptx']['sha256'] or result.get('authorization_hash')!=grant['sha256']:
        raise ValueError('Edit proposal must bind this frozen request and current PPTX')
    number=state['revision']+1;folder=task/'versions'/('edit-'+str(number).zfill(3))
    while folder.exists():number+=1;folder=task/'versions'/('edit-'+str(number).zfill(3))
    folder.mkdir();output=folder/'drawing.pptx';begin=time.monotonic()
    fn=apply_raster if proof.get('raster') else apply_native
    if result.get('operation')=='frame_plan':
        from .frame_actions import apply as apply_frames
        plan=frame_plan.validate(frame_plan.load(task,state['frame_plan']),task,state)
        receipt=apply_frames(plan,task,_path(task,baseline['pptx']['path']),output,state['source_size'],
                            {'expected_baseline_sha256':proof['baseline_hash'],'allowed_changes':proof['allowed_changes']})
    else:
        receipt=fn(task,_path(task,baseline['pptx']['path']),proof,result,output)
    from .relative_layout import guard_saved
    layout_guard = guard_saved(task, state, output, baseline, proof['allowed_changes'])
    from .textbox_quality import guard_saved as text_guard
    typography_guard = text_guard(task,state,output,baseline,proof['allowed_changes'])
    composition_guard = semantic_composition.guard_saved(task,state,output,baseline,proof['allowed_changes'])
    write_json(folder/'edit-receipt.json',receipt)
    candidate={**baseline,'revision':number,'pptx':_file(task,output),
               'snapshot':Library(state['project'], scope=library_scope(state)).blob(output),'baseline':proof['baseline_hash'],
               'reason':{'kind':'user_edit','id':grant['id'],'check_roi':grant['check_roi']},
               'native_authority':'user_grant','recipe_state':'snapshot_only','allowed':proof['allowed_changes'],
               'relative_layout_guard':layout_guard,'textbox_guard':typography_guard,'semantic_composition_guard':composition_guard}
    candidate.pop('preview',None);candidate.pop('render',None)
    if not proof.get('raster'):
        from .textbox_quality import mirror
        if result.get('operation')=='frame_plan':
            mirrored=frame_plan.mirror_saved(read_json(_path(task,baseline['scene']['path'])),output,plan,task,proof['allowed_changes'])
            mirrored['frame_plan']=state['frame_plan']
        else:
            mirrored=mirror(read_json(_path(task,baseline['scene']['path'])),output,proof['allowed_changes'])
        if mirrored.get('font_plan') and result.get('operation')!='frame_plan':
            mirrored=font_contract.apply_user_intent(task,state,mirrored,proof,result)
            candidate['font_delivery']=font_contract.finalize(mirrored,output)
            if candidate['font_delivery']['embedding']['status']=='FONT_EMBEDDING_PROVIDER_REQUIRED' and state['capabilities'].get('windows_office',{}).get('available'):
                try:
                    candidate['font_delivery']=font_contract.deliver_with_provider(mirrored,output,state['capabilities'],folder/'font-provider')
                except (ValueError,RuntimeError,OSError,__import__('subprocess').TimeoutExpired) as error:
                    candidate['font_delivery']['provider_failure']={'reason':str(error),'scope':'Staged font save only; selected user baseline retained'}
            candidate['pptx']=_file(task,output)
            candidate['snapshot']=Library(state['project'], scope=library_scope(state)).blob(output)
        scene_file=folder/'scene.json';write_json(scene_file,mirrored)
        candidate['scene']=_file(task,scene_file)
    font_pending=candidate.get('font_delivery',{}).get('embedding',{}).get('status')=='FONT_EMBEDDING_PROVIDER_REQUIRED'
    if not font_pending and (state['capabilities'].get('saved_render_available') or state['capabilities']['libreoffice']['available']) and state.get('render_dispatch',{}).get('mode')!='native_host_tool':
        render_saved(output,folder/'render',state['capabilities'],state['objectives']['render_width'])
        candidate['preview']=_file(task,folder/'render/Final_preview.png')
        candidate['render']=_file(task,folder/'render/render.json')
        if semantic_composition.enabled(state):
            semantic_composition.capture_portable(task,state,candidate)
            frame_plan.register_failures(task,state,candidate)
            semantic_composition.register_failures(task,state,candidate)
    state['telemetry']['program_seconds']+=time.monotonic()-begin
    state['revision']=number;state['active_candidate']=candidate
    state['review_queue']=['local-edit:'+grant['id']]
    state['stage']='font_delivery' if font_pending else 'review' if candidate.get('preview') else 'host_render'
    _event(task,'scoped_user_edit',{'authorization':grant['sha256'],'candidate':candidate['pptx'],'receipt':receipt['status']})


def _adopt_native_owners(state,names,revision,reason,lib):
    """Invalidate only derived recipes whose real saved objects changed."""
    touched=[]
    for comp in state['analysis']['components']:
        own={o['id'] for o in state['built'].get(comp['id'],{}).get('objects',[])}
        if not own & set(names):continue
        cid=comp['id'];touched.append(cid)
        state['methods'][cid]['recipe_state']='snapshot_only'
        state['built'][cid]['method']['recipe_state']='snapshot_only'
        state['reviews'].pop(cid,None)
        state['protected'][cid]={'authority':'user','revision':revision,'reason':reason,'mapped':True}
        lib.invalidate([cid,state['task_id']+':'+cid])
    return touched


def _host_render_work(task,state):
    packet = _packet(task, state, 'tool_render', 'saved_pptx',
        'Render the actual saved task PPTX using an available host tool; return staged preview '
        'and render receipt tied to this PPTX. Do not replace a render by a generated illustration.',
        extra={'pptx':state['active_candidate']['pptx'],'render_dispatch':state.get('render_dispatch'),
               'composition_capture':state['active_candidate'].get('semantic_composition_guard',{}).get('capture_request'),
               'return':'preview and render paths, or render_failure:{path,sha256} plus operation:keep_baseline after a captured actual export failure'})
    return {'status':'WORK_PACKET','task':str(task),'packet':packet}


@transaction
def next_packet(task, configuration=None):
    task, state = _state(task)
    prior_route=state['capabilities'].get('fingerprint')
    if state.get('analysis'):
        try:semantic_composition.validate_relations(state['analysis'].get('scene_relations',[]),'analysis.scene_relations')
        except ValueError as error:
            if (state.get('packet') or {}).get('kind')=='source_scene_relations':
                return {'status':'WORK_PACKET','task':str(task),'packet':state['packet']}
            packet=_packet(task,state,'source_scene_relations','scene_relations',
                'Correct only the malformed Scene edge field from the unchanged original. Source prose belongs in source_note/reconstruction_notes, not executable edges.',
                extra={'diagnostic':str(error),'rejected_value':state['analysis'].get('scene_relations'),
                       'return':'scene_relations[{type,source,target}] or [] when no explicit paint/connection edges are needed; retain every other source declaration'})
            return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    if configuration:
        state['capabilities'] = capabilities(configuration,state['project'])
        _save(task,state)
    elif __import__(__package__+'.tool_router',fromlist=['environment_changed']).environment_changed(state['capabilities'],state['project']):
        prior_config=state['capabilities'].get('fonts',{}).get('font_config') if state['capabilities'].get('configuration_mode')=='explicit' else None
        state['capabilities'] = capabilities(prior_config,project=state['project'])
        _save(task,state)
    if state['capabilities'].get('fingerprint') != prior_route:
        ledger=state.setdefault('semantic_composition', {'contracts': [], 'decisions': {}, 'history': []})
        ledger['environment_epoch']=ledger.get('environment_epoch',0)+1
        ledger.pop('actual_host_context',None)
        ledger.pop('actual_host_contexts',None)
        state['packet']=None
        if state.get('objectives',{}).get('component_first'):
            current=state.get('active_candidate') or state.get('selected')
            if current:
                current.pop('preview',None);current.pop('render',None);current.pop('render_environment',None)
                state.update(active_candidate=current,stage='host_render')
            if state.get('component_workflow'):
                from .component_workflow import _load as load_components,_save_ledger as save_components,refresh as refresh_components
                contract,component_ledger=load_components(task,state)
                refresh_components(task,state,contract,component_ledger,current)
                component_ledger.update(layout_ready=False,final_dirty=True,final_result=None)
                with writer(task):save_components(task,state,component_ledger,'render_environment_changed')
        _event(task,'render_environment_changed',{'prior':prior_route,'current':state['capabilities'].get('fingerprint'),
            'effect':'Owner captures remain historical; current environment observations are required'})
        _save(task,state)
    if state['selected'] and digest(_path(task, state['selected']['pptx']['path'])) != state['selected']['pptx']['sha256']:
        return {'status': 'USER_FILE_CHANGED', 'action': 'sync the edited PPTX before continuing'}
    candidate=state.get('active_candidate') or state.get('selected')
    if not candidate and state.get('objectives',{}).get('component_first') and not state.get('font_pending_candidate'):
        from .workflow_guard import enabled as controlled
        from .component_workflow import implementation as component_implementation
        if controlled(state) and state.get('packet') and state['packet'].get('component_implementation')==component_implementation():
            return {'status':'WORK_PACKET','task':str(task),'packet':state['packet']}
        from .component_workflow import next_action as component_next
        return component_next(task,state)
    if not candidate and state.get('analysis') and not state.get('global_aesthetic_plan'):
        from .global_aesthetic import discover as global_source_plan
        return {'status':'WORK_PACKET','task':str(task),'packet':{
            **global_source_plan(task,state),'action':'global-quality bind',
            'instruction':'Freeze original global regions and intended layout now. Programs bind source-owned policy roots to actual native owners after construction; no candidate can redefine original bounds.'}}
    satisfied={uid for uid,u in state.get('quality',{}).get('units',{}).items()
               if (u['status']=='minimum_met' or source_quality.has_usable_limit(state,u)) and candidate and
               (state['quality'].get('observations',{}).get(uid,{}).get('candidate')==candidate['pptx']['sha256'] or source_quality.has_usable_limit(state,u))}
    before=list(state.get('review_queue',[]))
    state['review_queue']=[target for target in before
                          if not (source_quality.unit(state,target) or {}).get('id') in satisfied]
    packet=state.get('packet') or {}
    if packet.get('kind')=='review' and (source_quality.unit(state,packet['target']) or {}).get('id') in satisfied:
        state['packet']=None
    if state['review_queue']!=before:
        _save(task,state);_event(task,'satisfied_review_aliases_pruned',{'count':len(before)-len(state['review_queue']),
            'candidate':candidate['pptx']['sha256']})
    if (state['stage']=='host_render' and state.get('active_candidate') and state.get('packet')
            and state['packet']['revision']!=state['revision']):
        _event(task,'saved_construction_packet_superseded',{'prior_packet':state['packet']['packet_id'],
            'saved_revision':state['revision'],'pptx':state['active_candidate']['pptx']})
        state['packet']=None;_save(task,state)
    if state['packet'] and state.get('objectives',{}).get('component_first'):
        from .component_workflow import implementation
        if state['packet'].get('component_implementation')!=implementation():
            state['packet']=None;_save(task,state)
    if state['packet']:
        return {'status': 'WORK_PACKET', 'task': str(task), 'packet': state['packet']}
    if state.get('font_pending_candidate'):
        pending=state['font_pending_candidate'];ref=pending['scene']
        if digest(_path(task,ref['path']))!=ref['sha256']:raise ValueError('Pending source font scene changed')
        scene=read_json(_path(task,ref['path']))
        font_contract.auto_bind(task,state,scene)
        _save(task,state)
        reading=font_contract.packet(task,state,scene)
        if reading:
            packet=_packet(task,state,'font_binding','source_fonts',
                'Bind original/user font intent to real resources before drawing; do not replace an exact family with an available style peer.',extra=reading)
            return {'status':'WORK_PACKET','task':str(task),'packet':packet}
        from .workflow_guard import finite_writer
        with finite_writer(task):
            _candidate(task,state,scene,baseline=pending['baseline'],allowed=pending['allowed'],reason=pending['reason'],
                       transaction=read_json(_path(task,pending['transaction_path'])) if pending.get('transaction_path') else None)
        if not state.get('objectives',{}).get('component_first'):_save(task,state)
        # Component constructor owns its repository CAS; reload on the recursive next call.
        return next_packet(task)
    if state['stage']=='font_delivery':
        candidate=state['active_candidate']
        if state.get('component_workflow') and state.get('objectives',{}).get('component_first'):
            from .component_workflow import _load as load_components
            font_contract_value,font_ledger=load_components(task,state)
            pending_tx=font_ledger.get('pending_transaction')
            transaction=read_json(_path(task,pending_tx['path'])) if pending_tx else {}
            if len(transaction.get('font_provider_attempts',[]))>=font_contract_value['policy'].get('recovery_attempt_limit',3):
                packet=_packet(task,state,'component_recovery_work','font_provider_recovery',
                    'Bounded font provider attempts are retained. Inspect the exact font capability or submit a located source-font redecision.',
                    extra={'transaction':pending_tx,'return':'component_request{action:retain_font_candidate_and_redecide,reason,evidence}','whole_audit_allowed':False})
                return {'status':'WORK_PACKET','packet':packet}
        packet=_packet(task,state,'tool_font_embedding','saved_fonts',
            'On a staged copy use an existing compatible Office/font provider to embed every requested face fully. Return that copy; the program transfers font parts only.',
            extra={'reference':'references/font-portability.md','pptx':candidate['pptx'],
                   'font_delivery':candidate['font_delivery'],
                   'return':'font_provider{path,sha256,input_sha256}; preserve any failed provider attempt; never install fonts/software or replace native slide contents'})
        return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    if state['stage']=='user_intent_pending':
        return {'status':'USER_INTENT_PENDING','selected':state['selected'],
                'migration':state.get('external_reconciliation'),
                'next':'Keep the user file; explicitly revise changed target expectations/bindings before quality acceptance or automatic repair.'}
    if state['stage']=='external_edit_pending':
        from .external_sync import packet as sync_packet
        packet=_packet(task,state,'external_edit','user_native_version',
            'Separate user authority from source-quality approval. Observe only changed bindings/intent; do not undo user artwork.',
            extra=sync_packet(task,state))
        return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    if state['stage']=='host_render' and state.get('active_candidate'):
        # Observe an already saved bounded transaction before further planning.
        # Original recursion/relations remain mandatory after the render; this
        # changes scheduling only, never their closure or acceptance status.
        return _host_render_work(task,state)
    # An older render cannot supersede pending construction/font/host work,
    # the current packet or an external user edit awaiting explicit closure.
    from .component_workflow import enabled as component_enabled, next_action as component_next
    if candidate and component_enabled(state) and not state.get('rule_pending_built'):
        component_work=component_next(task,state,candidate)
        if component_work:return component_work
    if candidate and candidate.get('render') and (state.get('quality_intent') or state.get('objectives',{}).get('whole_quality_intent')) and not state.get('rule_pending_built'):
        from .quality_loop import next_action as quality_next
        return quality_next(task,state,candidate)
    if candidate and candidate.get('preview') and state['stage'] not in ('host_render','font_delivery','external_edit_pending','user_intent_pending'):
        from .source_spacing import packet as spacing_packet
        spacing=spacing_packet(task,state)
        if spacing:
            packet=_packet(task,state,'source_spacing_source','original_part_spacing',
                'Segment original same-root parts; the program classifies contact/separation and compiles output constraints.',extra=spacing)
            return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    if state['objectives'].get('source_textbox_quality') and candidate and candidate.get('preview'):
        from .textbox_quality import source_packet
        from .retained_typography import report as retained_typography_report
        retained=retained_typography_report(task,state,candidate)
        reading=None if retained.get('applicable') and retained['passed'] else source_packet(task,state,candidate)
        if reading:
            packet=_packet(task,state,'textbox_source','source_textboxes',
                'Read original-only text/math crops independently of saved strings; freeze exact contents, glyph ownership and visible typography.',
                extra=reading)
            return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    if candidate and candidate.get('preview') and state['stage'] not in ('host_render','font_delivery','external_edit_pending','user_intent_pending'):
        coverage_work=execution_contract.packet(task,state,candidate)
        if coverage_work:
            packet=_packet(task,state,'rule_coverage_source','whole_drawing_rules',
                'Resolve the complete actual native inventory and original physical roots. '
                'Checking is global; write grants remain local. Bind executable source interfaces before accepting.',
                extra=coverage_work)
            return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    if state.get('quality',{}).get('units') and state['stage'] not in ('host_render','font_delivery','external_edit_pending','user_intent_pending'):
        from .source_repeat import packet as repeat_packet
        repeat_work=repeat_packet(task,state)
        if repeat_work:
            packet=_packet(task,state,'source_repeat_observation','original_repeat_families',
                'Confirm common anatomy and varying roles from original-only pairs; freeze one mother and use program instance transforms.',extra=repeat_work)
            _save(task,state)
            return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    if candidate and candidate.get('preview') and state['stage'] not in ('host_render','font_delivery','external_edit_pending','user_intent_pending'):
        from .adaptive_detail import packet as detail_packet
        detail=detail_packet(task,state,candidate)
        if detail:
            packet=_packet(task,state,'adaptive_source_detail','source_detail_context',
                'Inspect the original local discrepancy with its parent and related owners. Retain newly discovered source parts/relationships and bind executable checks before closure.',extra=detail)
            _save(task,state)
            return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    if state['stage']=='accepted':
        execution_contract.verify_acceptance(task,state,state['selected'])
    if state['stage'] in ('accepted', 'stalled', 'resource_limit'):
        return {'status': state['stage'].upper(), 'selected': state['selected'],
                'open_issues': [i for i in state['issues'] if i['status'] != 'resolved']}
    if state['actions'] >= state['objectives']['max_actions']:
        state['stage'] = 'resource_limit'; _save(task, state)
        return {'status': 'RESOURCE_LIMIT', 'selected': state['selected']}
    if state['stage']=='local_edit':
        grant=state['user_edit'];proof=read_json(_path(task,grant['path']))
        packet=_packet(task,state,'local_edit',grant['id'],
            'Execute only the frozen user request on the actual saved PPTX. Return explicit native '
            'leaf values or a host donor; for a permitted picture return its same-canvas proposal. '
            'The program preserves all other properties and pixels.',grant['check_roi'],
            {'authorization':grant,'user_intent':proof['user_intent'],'allowed_changes':proof['allowed_changes'],
             'raster':proof.get('raster'),
             'native_targets':[{k:row.get(k) for k in ('name','kind','shape_id','bbox_emu','parent','slide')} for row in proof['descriptors']],
             'native_targets_file':grant,
             'units':'native bbox/group translation uses parent-coordinate EMU; font/line uses points',
             'return':'authorization_hash, changes[{object_id,field,value}], or donor{path,sha256}, or candidate{path,sha256}'})
        return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    if state['analysis'] is None:
        from .catalog_source import guide
        catalog_guide=guide(task,state) if state.get('objectives',{}).get('source_catalog_review') else None
        packet = _packet(task, state, 'observation', 'source',
            'Understand this original independently of future render objects. Record natural components, '
            'exact text/math, layers, pose, spacing, relations and uncertainty; omit only identified non-figure UI.',
            extra={'visual_catalog_comparison':catalog_guide,
                   'return': {'analysis': 'source_hash, theme, catalog_review only if visual_catalog_comparison contains items, components[{id, semantic_class, roi, '
                   'source_note, parts, view, dependencies, review_unit, optional method}], relations, '
                   'optional scene_relations[{type,source,target}] (typed native edges only; source prose belongs in notes), '
                   'source_inventory{source_hash,features[{id,roi,kind,status,evidence,owner,source_part,importance,quality_property,constraints?}]} (or source_inventory_ref); important features need an independent quality_property; inferred illustration needs constraints'},
                   'method_declaration': {'optional':True,'type':'object','examples':[{'recipe':'KNOWN_RECIPE','parameters':{}},{'coordinate_space':'source_px','objects':[]}],
                       'rule':'Omit an unselected method; a descriptive string such as native or svg is not an executable construction.'},
                   'constraints': ['quality-driven native/SVG/declared-HD representation; independent semantic components', 'one continuous contour when expressible',
                                   'complete reusable hidden parts', 'clear at reuse size']})
        return {'status': 'WORK_PACKET', 'task': str(task), 'packet': packet}
    from . import source_features
    if source_features.required(state) and not state.get('source_features'):
        packet=_packet(task,state,'source_inventory','original_features',
            'Record original-only fine lines, small repeated parts, scientific text/relations and unexplained evidence independently of output objects.',
            extra=source_features.packet(task,state))
        return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    from .source_recursion import packet as recursion_packet
    original_regions=recursion_packet(task,state)
    if original_regions:
        packet=_packet(task,state,'source_recursion','original_region_frontier',
            'Inspect every program-issued original child; submit typed split/leaf/repair decisions. Parent agreement cannot close a child.',
            extra=original_regions)
        return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    from .source_connections import packet as original_connection_packet
    connection_source=original_connection_packet(task,state)
    if connection_source:
        packet=_packet(task,state,'source_connection_observation','original_connections',
            'Observe every original recursive child for connection primitives and occluders before construction.',extra=connection_source)
        return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    # Source coverage refinement cannot retire an unobserved real candidate
    # or the host's explicit located follow-up/repair. It remains required
    # debt before completion and is scheduled as soon as that work finishes.
    active=state.get('active_candidate');selected=state.get('selected')
    pending_actual=bool(state.get('pending_built') or state.get('rule_pending_built') or active and
        (not active.get('preview') or not selected or active['pptx']['sha256']!=selected['pptx']['sha256']))
    located_work=bool(state.get('repair_priority') or
        any(v.startswith('followup:') for v in state.get('review_queue',[])))
    original_refinement_safe=bool(active and active.get('preview') and active.get('render') and
        active.get('reason',{}).get('kind')=='program_all_applicable_rule_repair')
    owner = None if located_work or pending_actual and not original_refinement_safe else source_quality.refinement(state)
    if owner:
        comp = _component(state, owner)
        packet = _packet(task, state, 'source_spec', owner,
            'Observe this source independently. Recursively identify each natural icon and important '
            'part, including thin lines, occluded continuations and small adjacent marks. Name unknown '
            'features by geometry rather than deleting them. Compile separate content/geometry/style '
            'requirements; text/math also need content/typography/placement. Do not infer source '
            'observations from a recipe or future output. Keep uncertainty explicit.', comp['roi'],
            {'component': {k:v for k,v in comp.items() if k not in ('method','source_spec')},
             'source_spec_version': source_quality.VERSION,
             'source_grid_contract':__import__(__package__+'.source_grids',fromlist=['declaration']).declaration(comp),
             'layout_review_contract': 'New specs require layout_review{source_hash,evidence,scope,important_relation_ids}; every important relation ID has an executable relative_layout measurement. Concrete source evidence must justify an empty list.',
             'prior_spec_hash':identity(state['quality']['specifications'][owner]) if owner in state['quality'].get('specifications',{}) else None,
             'coverage_debt':state['quality'].get('coverage_debt',{}).get(owner,[]),
             'profiles': list(source_quality.PROFILES),
             'declaration_types': {
                 'protocol': {'type':'object','default':{},'meaning':'Fixed measurement settings; never a descriptive string'},
                 'features': {'type':'list_of_objects','text_literal_field':'literal','formula_ast_field':'ast'},
                 'coverage_bindings': {'type':'list_of_objects','quality_units':'Exact owner:part IDs; each binding role must match its unit profile'},
                 'required_categories_by_profile': {name:sorted(source_quality.CATEGORIES.get(name,{'content','geometry','style'})) for name in source_quality.PROFILES},
                 'quality_intent_required':bool(state.get('objectives',{}).get('whole_quality_intent') and not state.get('native_import')),
                 'quality_intent_fields':['purpose','appearance_target','basis','source_reliability','source_constraints or design_contract as appropriate'],
                 'original_text':'An observed content feature carries the exact literal string. expected is a property description and cannot replace literal.'},
             'relative_layout': 'Important source sibling gaps/container interiors/anchors/intentional overlap need typed relative_layout relations; use relative-layout discover to select bounded original pairs. No group-frame or whole-page compensation. Load references/relative-layout.md for this step only.',
             'return': 'source_spec{version,owner,source_hash,coverage_statement,parts['
                       '{id,roi,profile,quality_intent,features[{id,category,expected,status:observed|inferred|unresolved,'
                       'evidence:{source_hash,roi,description},constraints?}],objects?,protocol?,metrics?,'
                       'target_basis?}],coverage_bindings[{source_part,role,quality_units,status,evidence,constraints?}],relations[{id,roi,participants,expected,status,evidence,'
                       'measurement?,metrics?,objects?}],unassigned_features[]}',
             'rule': 'Each semantic icon/important part is independent; no whole-region score can '
                      'compensate its missing content or a below-target property. Source-supported rounded illustration outlines need clean output curvature independently of source blur; preserve genuine corners/openings, and do not smooth scientific curves. Explicitly bind every declared component.parts entry; a visual robot/road cannot be covered by text scores. On an existing specification, return prior_spec_hash plus source_correction_kind and source_correction_reason. Preserve prior units, bounds and satisfactory observations. Save detailed specs on disk.'})
        return {'status': 'WORK_PACKET', 'task': str(task), 'packet': packet}
    from .signal_semantics import packet as signal_packet
    original_signals=signal_packet(task,state)
    if original_signals:
        packet=_packet(task,state,'signal_source','original_signal_relationships',
            'Bind source-fitted schematic waveforms and actual associated text. Frequency ordering requires independent source/text evidence.',
            extra=original_signals)
        return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    if state['stage'] == 'construction':
        lib = Library(state['project'], scope=library_scope(state))
        for comp in sorted(state['analysis']['components'], key=lambda c: (c.get('z',0), c['id'])):
            cid = comp['id']
            if cid in state['built'] or not set(comp.get('depends_on', [])) <= state['built'].keys():
                continue
            if cid in state['methods']:
                try:_validate_method(state['methods'][cid])
                except ValueError as error:
                    rejected=state['methods'].pop(cid)
                    state.setdefault('method_rejections',[]).append({'owner':cid,'method':rejected,
                        'reason':str(error),'stage':'construction','effect':'A new typed method packet is required; original specifications and prior artwork are preserved.'})
                    _event(task,'invalid_legacy_method_rejected',{'owner':cid,'reason':str(error)})
                    _save(task,state)
            if cid in state['methods']:
                begin=time.monotonic()
                state['built'][cid] = _parts(task, state, comp, state['methods'][cid])
                if source_quality.enabled(state):source_quality.bind_objects(state,cid,state['built'][cid])
                state['telemetry']['program_seconds']+=time.monotonic()-begin
                state['actions'] += 1
                _event(task, 'instantiate', {'component': cid, 'method': state['methods'][cid].get('recipe'),
                                            'fingerprint': state['built'][cid]['fingerprint']})
                _save(task,state)
                continue
            choices = lib.find('asset', {**comp, 'required_parts': comp['parts'], 'allowed_representations': ['native','svg']})
            from .semantic_icons import route as natural_icon_route
            from .natural_catalog import packet as natural_catalog_packet
            packet = _packet(task, state, 'method', cid,
                    'Choose a source-matched construction: native recipe/PPTX, pure SVG component, or quality-justified HD asset; '
                    'use a known recipe or source-coordinate native parts. Preserve observed parts and pose.',
                    comp['roi'], {'component': {k:v for k,v in comp.items() if k != 'method'},
                                  'assets': choices, 'natural_geometry_route':natural_icon_route(comp),
                                  'shipped_natural_components':natural_catalog_packet(comp),
                                  'required_original_catalog_instances':[{k:r[k] for k in ('id','source_traits','method')}
                                      for r in state.get('source_catalog_data',{}).get('instances',[]) if r['owner']==cid],
                                  'original_photo_constructor':{'method_field':'source_photos','items':[{'object':'NATIVE_PHOTO_ID','part':'FROZEN_PART_ID','source_roi':[0,0,1,1],'source_note':'Original-only semantic photo window.'}],
                                      'requirements':'Each independent photo_identity source part has its own frozen integer ROI. The program crops the unchanged original and derives the source binding; generated artwork still requires its actual quality trial.'},
                                  'available_recipes':sorted(__import__(__package__+'.recipes',fromlist=['RECIPES']).RECIPES),
                                  'available_presets':sorted(__import__(__package__+'.presets',fromlist=['PRESETS']).PRESETS),
                                  'quality_profile': __import__(__package__+'.quality_policy',fromlist=['profile']).profile(comp),
                                   'return': 'method{recipe,parameters}, method{asset_id}, method{svg_asset:{path,sha256,preview}}, or '
                                  'method{coordinate_space:source_px,objects:[native objects]}'})
            return {'status': 'WORK_PACKET', 'task': str(task), 'packet': packet}
        if len(state['built']) != len(state['analysis']['components']):
            raise ValueError('Unresolved construction dependencies')
        prepared=_scene(task,state)
        frame_reading=frame_plan.source_packet(task,state,prepared)
        if frame_reading:
            packet=_packet(task,state,'frame_plan_source','source_frames',
                'Freeze source-supported frames, semantic content windows and separately authorized layout targets before drawing. Read references/frame-planning.md.',extra=frame_reading)
            return {'status':'WORK_PACKET','task':str(task),'packet':packet}
        reading=semantic_composition.source_packet(task,state,prepared)
        if reading:
            packet=_packet(task,state,'semantic_composition_source','source_composition',
                'Read the original semantic interactions; freeze executable coverage/order/interior constraints before drawing.',extra=reading)
            return {'status':'WORK_PACKET','task':str(task),'packet':packet}
        from .source_spacing import packet as spacing_packet
        spacing=spacing_packet(task,state)
        if spacing:
            packet=_packet(task,state,'source_spacing_source','original_part_spacing',
                'Compute original same-root spacing before the first saved drawing; missing or ambiguous masks cannot be bypassed.',extra=spacing)
            return {'status':'WORK_PACKET','task':str(task),'packet':packet}
        _candidate(task, state, prepared)
        _save(task, state)
        if state.get('font_pending_candidate') or state['stage']=='font_delivery':
            return next_packet(task)
    if state['stage'] == 'host_render':
        return _host_render_work(task,state)
    urgent=[i for i in state['issues'] if i['status']=='open' and i['severity'] in ('critical','major')]
    if (source_quality.enabled(state) and urgent and state.get('selected')
            and not any(t.startswith('followup:') for t in state.get('review_queue',[]))
            and not state.get('pending_built') and (state.get('active_candidate') or {}).get('pptx',{}).get('sha256')==state['selected']['pptx']['sha256']):
        state.setdefault('deferred_review_queue',[]).extend(
            t for t in state.get('review_queue',[]) if t not in state.get('deferred_review_queue',[]))
        state['review_queue']=[]
        state['active_candidate']=None
    if state.get('review_queue'):
        target = state['review_queue'][0]
        roi = _review_roi(state, target)
        candidate = state['active_candidate'] or state['selected']
        # These source requirements are independent of instantiated render
        # nodes. Small models receive useful cues without reopening full docs.
        x,y,w,h=roi
        reference=[{k:c.get(k) for k in ('id','semantic_class','source_note','parts')}
                   for c in state['analysis']['components']
                   if c['roi'][0]<x+w and c['roi'][1]<y+h
                   and c['roi'][0]+c['roi'][2]>x and c['roi'][1]+c['roi'][3]>y]
        if target in state['built']:reference=[r for r in reference if r['id']==target]
        reference=reference[:4]
        quality_unit = source_quality.unit(state, target)
        repair_feedback = None
        if target.startswith('repair:'):
            issue = next(i for i in state['issues'] if i['id']==target.split(':',1)[1])
            quality_unit = source_quality.unit(state, issue.get('quality_unit') or '')
        diagnostic = (source_quality.evaluate(task, state, candidate, quality_unit)
                      if quality_unit else _metrics(task, state, candidate, roi))
        if target.startswith('repair:') and quality_unit and state.get('selected'):
            previous = source_quality.evaluate(task,state,state['selected'],quality_unit)
            benefit = source_quality.effect(previous,diagnostic,quality_unit)
            below = diagnostic['status']!='numeric_minimum_met'
            own_progress = (benefit['result']=='helped'
                            or benefit.get('floor_preserving_deficit_progress',False)
                            or benefit.get('source_observability_limited_progress',False))
            repair_feedback = {
                'unit':quality_unit['id'], 'status':diagnostic['status'],
                'effect':benefit,
                'numeric_option':('partial' if own_progress else 'ineffective|harmful|uncertain')
                                  if below else 'improved if target observed matched and preserved',
                'partial_requires':['outcome: partial','preserved: true',
                    'progress_observations: own matched gain',
                    'findings: located remaining issue with quality_unit'],
                'scope':'Every changed peer and protected dependency is gated separately. '
                        'Eligibility is retention progress, not satisfaction. '
                        'View actual geometry/content/material before deciding; do not copy this numerical option as a visual verdict.'}
        packet = _packet(task, state, 'review', target,
                'Compare these actual saved results with source evidence. Locate missing/extra parts, '
                'wrong relations, pose/outline/spacing, text/math, blur, seams and reusable-layer problems. '
                'Discover discrepancies beyond the plan. Return specific observations, not a blanket pass.', roi,
                {'source_requirements':reference,'diagnostics': diagnostic,
                 'repair_result_contract':repair_feedback,
                 'required_observations': source_quality.observation_contract(quality_unit) if quality_unit else [],
                 'source_trace': {'unit':quality_unit['id'], 'objects':quality_unit['objects']} if quality_unit else None,
                 'return': 'observations[{property,expected,actual,outcome:matched|issue|uncertain}], '
                           'findings[{owner,roi,property,expected,actual,severity,cause_hint}], optional outcome',
                 'candidate_hash': candidate['pptx']['sha256'],
                 'priorities':{identity(_priorities(c))[:8]:_priorities(c) for c in state['analysis']['components']
                               if c['id'] in {r['id'] for r in reference}},
                 'part_hotspots':__import__(__package__+'.defect_triage',fromlist=['part_hotspots']).part_hotspots(state.get('quality',{})) if target=='whole' else [],
                 'dimensions': list(DIMENSIONS),
                 'review_targets':[{'id':c['id'],'class':c['semantic_class'],'roi':c['roi']} for c in state['analysis']['components']][:32] if target=='whole' else [],
                 'hotspots': __import__(__package__+'.defect_triage',fromlist=['hotspots']).hotspots(_path(task,state['source']['path']),_path(task,candidate['preview']['path']),state['source_size'],state['analysis']['components']) if target=='whole' else []})
        return {'status': 'WORK_PACKET', 'task': str(task), 'packet': packet}
    open_issues = [i for i in state['issues'] if i['status'] not in ('resolved','deferred_minor')]
    if open_issues:
        from . import repair_strategy
        runnable=[i for i in open_issues if not i.get('strategy_exhausted') and
                  i.get('attempt_count',0)<state['objectives'].get('max_issue_repairs',12)]
        if not runnable:
            state['stage']='stalled';_save(task,state)
            return {'status':'STALLED','selected':state['selected'],'open_issues':open_issues,
                    'reason':'All remaining repair branches lack a useful evidenced route or reached their budget; no quality waiver'}
        requested=state.pop('repair_priority',None)
        issue = next((i for i in runnable if requested and i['id']==requested['issue_id']),None) or sorted(runnable, key=lambda i:(PRIORITY[i['severity']],i.get('attempt_count',0),-(i.get('metric_deficit') or 0)))[0]
        if issue.get('needs_strategy') or issue.get('non_improving_count',0)>=2 and not issue.get('strategies'):
            from .defect_triage import diagnosis
            packet=_packet(task,state,'strategy',issue['id'],
                'Prune the ineffective branch. Select a distinct evidence-supported operation or stop this issue; preserve the best and continue independent work.',
                issue['roi'],{'diagnosis':diagnosis(task,state,issue),'branches':issue.get('strategies',{}),
                'return':'strategy{action:select|stop, operator, cause{stage,evidence{artifact,contrast_artifact?,expected,observed,unit?}}, reason}'})
            return {'status':'WORK_PACKET','task':str(task),'packet':packet}
        owner = issue.get('owner')
        if owner not in state['built']:
            packet = _packet(task, state, 'source_gap', issue['id'],
                'This located discrepancy has no source-plan owner. Add the missing component/relations '
                'from original evidence without rebuilding satisfied components.', issue['roi'],
                {'issue': issue, 'return': 'component and native method'})
        else:
            stored_method=state['methods'].get(owner,{})
            def method_summary(method):
                summary={k:v for k,v in method.items() if k not in ('objects','children','source_bindings')}
                if method.get('source_bindings'):summary['source_binding_count']=len(method['source_bindings'])
                if method.get('objects'):
                    summary['native_object_count']=len(method['objects'])
                if method.get('children'):
                    children=method['children'];summary['child_count']=len(children)
                    summary['children']=[{'id':c['id'],'class':c['semantic_class'],
                        'method_kind':'recursive' if c['method'].get('children') else
                        'recipe:'+c['method']['recipe'] if c['method'].get('recipe') else
                        'paint' if c['method'].get('paint') else 'native'} for c in children[:16]]
                return summary
            component = _component(state, owner)
            source_component_file=task/'scratch'/'repair-source-component.json'
            write_json(source_component_file,component)
            trace = {'component': {k:v for k,v in component.items() if k not in ('method','source_spec')},
                     'source_component': {'path':'scratch/repair-source-component.json',
                         'sha256':digest(source_component_file)},
                     'method_summary':method_summary(stored_method),
                     'object_ids': [o['id'] for o in state['built'][owner]['objects']][:24],
                     'object_count':len(state['built'][owner]['objects']),
                     'recent_failed_actions': [a for a in state['attempts'] if a['issue']==issue['id']][-3:]}
            trace['source_artifact_chain']=source_quality.trace(state,issue)
            trace['operator_route']=__import__(__package__+'.source_routes',fromlist=['route']).route(state,issue)
            trace['root_cause_work']=__import__(__package__+'.defect_triage',fromlist=['trace']).trace(issue,_component(state,owner),stored_method,state['attempts'])
            trace['diagnosis']=__import__(__package__+'.defect_triage',fromlist=['diagnosis']).diagnosis(task,state,issue)
            trace['selected_strategy']=issue.get('proposed_strategy')
            trace['applicable_experience']=Library(state['project'], scope=library_scope(state)).find('experience',
                {'semantic_class':_component(state,owner)['semantic_class'],'property':issue['property']},
                limit=2,max_chars=1800)
            # Geometry payloads stay on disk rather than expanding every packet.
            write_json(task/'scratch'/'repair-input.json', state['built'][owner])
            packet = _packet(task, state, 'repair', issue['id'],
                'Trace the located issue back to source/recipe/geometry/layer/render. Propose the '
                'smallest explicit native change. Preserve every other owner and protected attribute.',
                issue['roi'], {'issue': issue, 'trace': trace, 'native_data': 'scratch/repair-input.json',
                               'return': 'cause{stage,evidence}, method, allowed_changes{object_id:[fields]}, '
                                         'expected_effect; or compile hashed local operator proposals through native-proposal-action. Repair target is the raw issue id. No widening by tools'})
        return {'status': 'WORK_PACKET', 'task': str(task), 'packet': packet}
    if state.get('deferred_review_queue'):
        pending=state.pop('deferred_review_queue')
        state['review_queue']=[v for v in dict.fromkeys(pending)
                               if v not in state.get('reviews',{}) or
                               v.startswith('quality:') and source_quality.unit(state,v)['status']!='minimum_met']
        if state['review_queue']:
            state['active_candidate']=state['selected'];_save(task,state)
            return next_packet(task)
    if source_quality.enabled(state):
        debt = source_quality.pending(state)
        if not debt['complete']:
            pending_targets = ['quality:' + uid for uid in debt['units']]
            state['review_queue'] = pending_targets
            if pending_targets:
                _save(task,state)
                return next_packet(task)
            state['stage'] = 'source_refinement'
            _save(task,state)
            return {'status':'SOURCE_DEBT', 'debt':debt, 'selected':state['selected']}
    feature_debt=source_features.pending(task,state)
    if feature_debt:
        packet=_packet(task,state,'source_inventory','original_features',
            'Resolve independent original features still lacking typed part coverage. Extend the specific source plan; preserve satisfactory drawings.',
            feature_debt[0]['roi'],source_features.packet(task,state))
        return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    semantic_composition.retention_guard(task,state,state['selected'],strict=True)
    frame_plan.guard(task,state,state['selected'],strict=True)
    execution_contract.final_gate(task,state,state['selected'])
    state['stage'] = 'accepted'
    state['active_candidate'] = None
    _save(task, state)
    return {'status': 'ACCEPTED', 'selected': state['selected'], 'telemetry': state['telemetry']}


def _observe(task, state, packet, result):
    candidate = state['active_candidate'] or state['selected']
    if result.get('candidate_hash') != candidate['pptx']['sha256']:
        raise ValueError('Observation is not bound to the current saved candidate')
    hashes = {v['sha256'] for v in packet['views']}
    if not hashes <= set(result.get('view_hashes', [])):
        raise ValueError('Observation must identify the actual paired views it used')
    observations = result.get('observations', [])
    if not observations or any(not all(o.get(k) for k in ('property','expected','actual','outcome'))
                               for o in observations):
        raise ValueError('Located property observations with expected/actual are required')
    if any(o['outcome'] not in ('matched','issue','uncertain') for o in observations):
        raise ValueError('Unknown observation outcome')
    findings = result.get('findings', [])
    if any(o['outcome'] != 'matched' for o in observations) and not findings:
        raise ValueError('Unmatched/uncertain observations need actionable located findings')
    quality_unit = source_quality.unit(state, packet['target'])
    if quality_unit:
        diagnostic = source_quality.evaluate(task,state,candidate,quality_unit)
        source_quality.record_observation(state,quality_unit,observations,
            {'candidate':candidate['pptx']['sha256'],'views':sorted(hashes)},diagnostic)
        findings = list(findings) + list(source_quality.defects(quality_unit,diagnostic))
    created = []
    reported = []
    for finding in findings:
        _roi(finding.get('roi'), state['source_size'])
        if not all(finding.get(k) for k in ('property','expected','actual','severity')):
            raise ValueError('Finding needs a property, expected/actual and severity')
        if finding['severity'] not in PRIORITY:
            raise ValueError('Unknown finding severity')
        px,py,pw,ph=packet['views'][0]['roi'];fx,fy,fw,fh=finding['roi']
        if fx<px or fy<py or fx+fw>px+pw+.001 or fy+fh>py+ph+.001:
            raise ValueError('View the located region with revisit before reporting a distant discrepancy')
        if packet['target'].startswith('local-edit:'):
            state['user_edit']['last_findings']=findings
            continue
        iid,existing = _located_issue(state,finding)
        reported.append(iid)
        if existing:
            existing.update(actual=finding['actual'], status='open',
                            evidence={'candidate':candidate['pptx']['sha256'], 'views':sorted(hashes)})
            existing.pop('resolution', None)
        else:
            item = {**finding, 'id':iid, 'status':'open', 'discovered_revision':state['revision'],
                    'attempt_count':0, 'evidence':{'candidate':candidate['pptx']['sha256'],
                                                'views':sorted(hashes)}}
            state['issues'].append(item); created.append(iid)
    target = packet['target']
    stop=result.get('accept_limits')
    if stop:
        if not stop.get('reason') or not stop.get('limits') or not any(o.get('critical') for o in observations) or any(o['outcome']!='matched' for o in observations if o.get('critical')):
            raise ValueError('Usable exit needs an explicit reason, limitations and satisfied critical properties')
        for iid in stop.get('issues',[]):
            issue=next(i for i in state['issues'] if i['id']==iid);x,y,w,h=packet['views'][0]['roi'];ix,iy,iw,ih=issue['roi']
            if issue['severity'] not in ('minor','polish') or ix<x or iy<y or ix+iw>x+w+.001 or iy+ih>y+h+.001:
                raise ValueError('A usable exit cannot hide an unobserved or substantive defect')
            issue['status']='deferred_minor';issue['disposition']=stop
    state['reviews'][target] = {'candidate':candidate['pptx']['sha256'], 'views': sorted(hashes),
                               'observations':observations, 'findings':reported}
    # One actually viewed high-resolution whole image can cover several
    # clearly visible natural units. Require an explicit property observation
    # per unit; never infer satisfaction from an object inventory or a bool.
    if not target.startswith('repair:'):
        coverage=result.get('coverage',[]);px,py,pw,ph=_review_roi(state,target)
        seen=set()
        for entry in coverage:
            unit=entry.get('target');obs=entry.get('observations',[])
            if unit in seen or unit not in state['review_queue'] or unit==target:
                raise ValueError('Coverage must name a pending independent review unit once')
            seen.add(unit);x,y,w,h=_review_roi(state,unit)
            if x<px or y<py or x+w>px+pw+.001 or y+h>py+ph+.001:
                raise ValueError('Coverage unit lies outside the actually viewed region')
            quality_value = source_quality.unit(state,unit)
            if source_quality.enabled(state) and quality_value is None and unit in state['built']:
                raise ValueError('Whole-component coverage cannot replace independent source-part review')
            if quality_value:
                from PIL import Image
                actual_view = next(v for v in packet['views'] if v['role']=='current')
                with Image.open(_path(task,actual_view['path'])) as image:
                    scale = min(image.width/pw,image.height/ph)
                own=[v for v in packet.get('part_views',[]) if v['unit']==unit]
                if own:
                    if {v['role'] for v in own}!={'source','current'}:
                        raise ValueError('Independent batch parts need paired source and current views')
                    for view in own:
                        if digest(_path(task,view['path']))!=view['sha256']:
                            raise ValueError('Independent part view changed')
                    if min(next(v['display_size'] for v in own if v['role']=='current'))<24:
                        raise ValueError('Independent part view is too small')
                elif min(quality_value['roi'][2:])*scale < 24:
                    raise ValueError('Small source parts need their own enlarged paired observation')
                local_diagnostic = source_quality.evaluate(task,state,candidate,quality_value)
                source_quality.record_observation(state,quality_value,obs,
                    {'candidate':candidate['pptx']['sha256'],'views':sorted(hashes)},local_diagnostic)
                for finding in source_quality.defects(quality_value,local_diagnostic):
                    iid,existing=_located_issue(state,finding)
                    if existing:
                        existing.update(actual=finding['actual'],status='open',metric_deficit=finding['metric_deficit'])
                    else:
                        state['issues'].append({**finding,'id':iid,'status':'open','attempt_count':0,
                            'evidence':{'candidate':candidate['pptx']['sha256'],'views':sorted(hashes)}})
            if len(obs)<(len(source_quality.observation_contract(quality_value)) if quality_value else 2) or any(not all(o.get(k) for k in ('property','expected','actual','outcome')) for o in obs):
                raise ValueError('Each covered unit needs specific observed source/result properties')
            if any(o['outcome'] not in ('matched','issue','uncertain') for o in obs):raise ValueError('Unknown coverage outcome')
            if any(o['outcome']!='matched' for o in obs) and not any(
                    f.get('quality_unit')==quality_value['id'] if quality_value else f.get('owner')==unit
                    for f in findings):
                raise ValueError('Unmatched unit needs its own located finding')
            state['reviews'][unit]={'candidate':candidate['pptx']['sha256'],'views':sorted(hashes),
                'observations':obs,'covered_in':target,'findings':[i['id'] for i in state['issues'] if i.get('owner')==unit and i['status']=='open']}
            state['review_queue'].remove(unit)
            if unit in state['built'] and all(o['outcome']=='matched' for o in obs):
                state['protected'][unit]={'authority':'agent','revision':state['revision'],
                    'fingerprint':state['built'][unit]['fingerprint'],'observations':obs}
    # A selected local patch may already solve another observed property.
    # Close only explicitly re-viewed owner/property matches; never rebuild a
    # correct result solely to manufacture another changed candidate hash.
    for iid in result.get('observed_resolutions',[]):
        related=next((i for i in state['issues'] if i['id']==iid),None)
        if related is None or related['status']!='open' or target.startswith('repair:'):
            raise ValueError('Observed resolution needs an open issue and a located revisit')
        ix,iy,iw,ih=related['roi'];px,py,pw,ph=packet['views'][0]['roi']
        matches=[o for o in observations if o.get('owner')==related['owner']
                 and o['property']==related['property'] and o['expected']==related['expected']]
        if (not matches or any(o['outcome']!='matched' or not o.get('critical') for o in matches)
                or candidate['pptx']['sha256']==related['evidence']['candidate']
                or not state['selected'] or candidate['pptx']['sha256']!=state['selected']['pptx']['sha256']
                or ix<px or iy<py or ix+iw>px+pw or iy+ih>py+ph
                or any(f.get('owner')==related['owner'] and f['property']==related['property'] and _same_issue_part(f,related) for f in findings)):
            raise ValueError('Resolution needs a changed selected artifact, paired source views and exact critical property evidence')
        related['status']='resolved'
        related['resolution']={'revision':state['revision'],'candidate':candidate['pptx']['sha256'],
                'views':sorted(hashes),'observations':matches,'mode':'already_solved_by_selected_scoped_change'}
    if target.startswith('local-edit:'):
        improved=result.get('outcome')=='improved' and result.get('preserved') is True and all(o['outcome']=='matched' for o in observations) and not findings
        grant=state['user_edit'];proof=read_json(_path(task,grant['path']))
        incremental=None
        if result.get('outcome')=='partial' and result.get('preserved') is True and semantic_composition.enabled(state):
            incremental=semantic_composition.partial_progress(task,state,candidate,proof['allowed_changes'])
            if not incremental['gains']:raise ValueError('A partial local composition result needs independently measured improvement')
            if not incremental['remaining_changes']:raise ValueError('Declare completion when no permitted failed composition field remains')
        if improved or incremental:
            native_grants=proof['allowed_changes'] or {proof['raster']['object_id']: ['raster_pixels']}
            adoption=candidate_adoption.prepare(task,state,candidate,native_grants,
                mode='local_edit',observations=observations,result=result)
            if not adoption['eligible']:
                improved=False;incremental=None
        if improved or incremental:
            candidate_adoption.retain(task,state,candidate,adoption,packet=packet,result=result)
            frame_plan.register_failures(task,state,candidate)
            semantic_composition.register_failures(task,state,candidate)
            names=list(proof['allowed_changes']) or [proof['raster']['object_id']]
            mirrored={o['id']:o for o in read_json(_path(task,candidate['scene']['path']))['objects']}
            for built in state['built'].values():
                for obj in built['objects']:
                    if obj['id'] in names and obj['id'] in mirrored:
                        obj['bbox']=copy.deepcopy(mirrored[obj['id']]['bbox'])
            _adopt_native_owners(state,names,state['revision'],'observed local user edit',Library(state['project'], scope=library_scope(state)))
            state['native_overlay']=__import__(__package__+'.saved_components',fromlist=['inventory']).inventory(_path(task,candidate['pptx']['path']))
            state['external_versions'].append({'revision':state['revision'],'authorization':grant['sha256'],
                    'changed_names':names,'snapshot':candidate['snapshot']})
            grant['outcome']='observed_improvement'
            if incremental:
                # Adopt measured working gains, then mechanically remove solved
                # fields from the next write set. Original authorization and
                # source contracts remain immutable; no wider edit permission.
                from .agent_edit import freeze
                state['packet']=None;state['active_candidate']=None
                continuation={'baseline_hash':candidate['pptx']['sha256'],'user_intent':proof['user_intent'],
                              'allowed_changes':incremental['remaining_changes']}
                derived=freeze(task,state,continuation)
                state['user_edit']={**derived,'parent_authorization':{'path':grant['path'],'sha256':grant['sha256']},
                                    'program_retained_gains':incremental['gains']}
                state['stage']='local_edit'
                _event(task,'partial_local_composition_frozen',{'selected':candidate['pptx'],
                       'gains':incremental['gains'],'remaining':incremental['remaining_changes'],
                       'prior_authorization':grant['sha256'],'continuation':derived})
        else:
            grant['attempts']=grant.get('attempts',0)+1
            # Keep the pre-edit authoritative best; no broad source replanning.
            state['stage']='local_edit' if grant['attempts']<2 else 'stalled'
            grant['last_observations']=observations
        state['active_candidate']=None
    elif target.startswith('repair:'):
        issue = next(i for i in state['issues'] if i['id'] == target.split(':',1)[1])
        correction=result.get('expected_correction')
        if correction:
            # New source observation can correct an earlier model reading.
            # Preserve that reading and its provenance rather than silently
            # rewriting history or insisting on an incorrect original plan.
            source_hashes={v['sha256'] for v in packet['views'] if v['role']=='source'}
            if (correction.get('prior_expected')!=issue['expected']
                    or not correction.get('expected') or not correction.get('basis')
                    or correction.get('source_view_hash') not in source_hashes
                    or not any(o['property']==issue['property']
                               and o['expected']==correction['expected'] for o in observations)):
                raise ValueError('Source expectation correction needs the prior reading, actual source view and explicit new observation')
            issue.setdefault('source_reading_history',[]).append({
                'expected':issue['expected'],'revision':state['revision'],
                'basis':correction['basis'],'source_view_hash':correction['source_view_hash']})
            issue['expected']=correction['expected']
            part_corrections=correction.get('part_corrections',{})
            if part_corrections:
                comp=_component(state,issue['owner'])
                if (not isinstance(part_corrections,dict)
                        or any(k not in comp['parts'] or not isinstance(v,str) or not v.strip()
                               or len(v)>160 for k,v in part_corrections.items())):
                    raise ValueError('Correct only observed named parts of the target source owner')
                new_parts=[part_corrections.get(v,v) for v in comp['parts']]
                if len(set(new_parts))!=len(new_parts):
                    raise ValueError('Source part correction cannot collapse distinct natural parts')
                comp.setdefault('source_reading_history',[]).append({
                    'parts':comp['parts'],'revision':state['revision'],
                    'basis':correction['basis'],'source_view_hash':correction['source_view_hash']})
                comp['parts']=new_parts
                comp['edit_targets']=[part_corrections.get(v,v) for v in comp['edit_targets']]
            _event(task,'source_expectation_corrected',{'issue':issue['id'],**correction})
        # The target property can be solved while a new independent minor
        # discrepancy is discovered. Keep real gains; never demand global
        # perfection to accept a scoped repair.
        target_observations=[o for o in observations if o['property']==issue['property']
                             and o.get('owner') in (None,issue['owner']) and _same_issue_part(o,issue)]
        target_still_reported=any(f.get('owner')==issue['owner']
                                 and f['property']==issue['property'] and _same_issue_part(f,issue) for f in findings)
        preserved=result.get('preserved', False)
        changed=(candidate['pptx']['sha256']!=state['selected']['pptx']['sha256']
                 or candidate['preview']['sha256']!=state['selected']['preview']['sha256'])
        improved = (result.get('outcome')=='improved' and preserved and changed
                    and not target_still_reported
                    and target_observations and all(o['outcome']=='matched' for o in target_observations))
        progress=result.get('progress_observations',[])
        partial=(result.get('outcome')=='partial' and preserved and changed and progress
                 and all(o.get('property') and o.get('expected') and o.get('actual')
                         and o.get('outcome')=='matched' for o in progress)
                 and findings)
        metric_gate = True
        if source_quality.enabled(state) and issue.get('quality_unit'):
            quality_value = state['quality']['units'][issue['quality_unit']]
            actual_metric = source_quality.evaluate(task,state,candidate,quality_value)
            metric_gate = actual_metric['status']=='numeric_minimum_met'
            previous_metric = source_quality.evaluate(task,state,state['selected'],quality_value)
            from .typed_metrics import dominance
            directions={m['id']:('min' if m.get('max') is not None and m.get('min') is None else 'max')
                        for m in quality_value['metrics']}
            benefit=source_quality.effect(previous_metric,actual_metric,quality_value)
            if not metric_gate:
                limit_request=result.get('cosmetic_limits') or {}
                part_limit=next((v for v in limit_request.get('parts',[]) if v.get('unit')==quality_value['id']),None)
                failed=[r for r in actual_metric.get('constraints',[]) if r['status'] in ('below_minimum','required_unmeasured')]
                own_colour_exit=bool(part_limit and part_limit.get('kind')=='minor_colour'
                    and quality_value['profile'] in ('flat','structured','curve','detail')
                    and failed and all(r['id']=='color_histogram_tv' and r['status']=='below_minimum' for r in failed)
                    and all(rule['source_status']=='observed' and any(o.get('property')==rule['property']
                        and o.get('expected')==rule['expected'] and o.get('outcome')=='matched' and o.get('actual')
                        for o in part_limit.get('critical_observations',[]))
                        for rule in source_quality.observation_contract(quality_value)))
                # This only admits the request to the existing independently
                # validated scoped gate below. No candidate can be retained
                # before context/source/preview/geometry/protection checks.
                exact_native_exit=bool(limit_request.get('source')==state['source'] and limit_request.get('actual_preview')==candidate['preview']
                    and (source_quality.native_typography_limit(quality_value,actual_metric,part_limit) or own_colour_exit))
                partial = (partial and (benefit['result']=='helped' or benefit.get('floor_preserving_deficit_progress',False)
                                        or benefit.get('source_observability_limited_progress',False)))
                improved = improved and exact_native_exit
        if improved or partial:
            adoption=candidate_adoption.prepare(task,state,candidate,candidate.get('allowed') or {},
                mode='repair',observations=observations,result=result)
            scope_effect=adoption['scope_effect']
            write_json(_path(task,candidate['pptx']['path']).parent/'repair-scope-effect.json',scope_effect)
            _event(task,'independent_changed_peer_effect',{'candidate':candidate['pptx']['sha256'],
                'eligible':scope_effect['eligible'],'blocking_units':scope_effect['blocking_units'],
                'changed_units':len(scope_effect['changed_units'])})
            improved=improved and scope_effect['eligible'];partial=partial and scope_effect['eligible']
        if improved or partial:
            issue['status'] = 'resolved' if improved else 'open'
            issue.setdefault('progress',[]).append({'revision':state['revision'],'observations':progress or observations})
            if improved:issue['resolution'] = {'revision':state['revision'], 'observations':observations}
            pending=state.pop('pending_built')
            frame_plan.register_failures(task,state,candidate)
            semantic_composition.register_failures(task,state,candidate)
            updates=pending if 'objects' not in pending else {issue['owner']:pending}
            for owner,built in updates.items():
                state['built'][owner]=built
                state['methods'][owner]=built['method']
                owner_observations=[o for o in observations if o.get('owner') in (None,owner)]
                previous=state['reviews'].get(owner,{}).get('observations',[])
                fixed={o['property'] for o in owner_observations}
                state['reviews'][owner]={'candidate':candidate['pptx']['sha256'],'views':sorted(hashes),
                    'observations':[o for o in previous if o['property'] not in fixed]+owner_observations,
                    'findings':[i['id'] for i in state['issues'] if i.get('owner')==owner
                                and i['status']=='open'],'scoped_repair':issue['id']}
            for iid in candidate['reason'].get('related_issues',[]):
                related=next(i for i in state['issues'] if i['id']==iid)
                related_observations=[o for o in observations if o.get('owner')==related['owner']
                                      and o['property']==related['property'] and _same_issue_part(o,related)]
                still_reported=any(f.get('owner')==related['owner']
                                   and f['property']==related['property'] and _same_issue_part(f,related) for f in findings)
                related_gate=True
                if source_quality.enabled(state) and related.get('quality_unit'):
                    related_unit=state['quality']['units'][related['quality_unit']]
                    related_gate=(source_quality.evaluate(task,state,candidate,related_unit)['status']=='numeric_minimum_met' or any(v['unit']==related_unit['id'] for v in scope_effect.get('usable_limits',[])))
                if (improved and related_gate and iid not in reported and not still_reported and related_observations
                        and all(o['outcome']=='matched' for o in related_observations)):
                    related['status']='resolved'
                    related['resolution']={'revision':state['revision'],'observations':related_observations}
            if source_quality.enabled(state):
                retention=candidate_adoption.retain(task,state,candidate,adoption,
                    updates=updates,packet=packet,result=result)
                affected=retention['affected'];inherited=retention['inherited']
                eligible_units={row['unit'] for row in scope_effect['changed_units'] if row['eligible']}
                for sibling in state['issues']:
                    if (sibling['status']!='open' or sibling.get('owner') not in updates or sibling.get('quality_unit') not in eligible_units
                            or sibling.get('property')!=issue.get('property') or sibling.get('cause_hint')!=issue.get('cause_hint')):continue
                    own=[o for o in observations if o.get('owner')==sibling['owner'] and o.get('quality_unit')==sibling.get('quality_unit') and o.get('property')==sibling['property'] and o.get('expected')==sibling['expected']]
                    still=any(f.get('owner')==sibling['owner'] and f.get('property')==sibling['property'] and _same_issue_part(f,sibling) for f in findings)
                    unit=state['quality']['units'][sibling['quality_unit']]
                    accepted=(source_quality.evaluate(task,state,candidate,unit)['status']=='numeric_minimum_met' or source_quality.has_usable_limit(state,unit))
                    if accepted and own and all(o.get('outcome')=='matched' for o in own) and not still:
                        sibling['status']='resolved';sibling['resolution']={'revision':state['revision'],'observations':own,'basis':'Explicit same-root per-unit actual observations and independent eligible scope; raw residuals remain in any usable limit.'}
                inherited=list(set(inherited)|{v['unit'] for v in scope_effect.get('usable_limits',[])})
                preserved_targets={'quality:'+uid for uid in inherited}
                affected=[target for target in affected if target not in preserved_targets]
                state['review_queue']=[target for target in state['review_queue'] if target not in preserved_targets]
                state['review_queue'] += [target for target in affected if target not in state['review_queue']]
                if inherited:_event(task,'satisfied_source_result_inherited',{'count':len(inherited),'units':inherited,
                    'candidate':candidate['pptx']['sha256'],'basis':'Exact source/native/resource/transform/owned actual RGB invariance; no new observation or metric run'})
            else:
                candidate_adoption.retain(task,state,candidate,adoption,updates=updates)
            for owner in updates:
                state['reviews'][owner]['findings']=[i['id'] for i in state['issues']
                    if i.get('owner')==owner and i['status']=='open']
            issue['non_improving_count']=0
            from .repair_strategy import record as record_strategy
            record_strategy(state,issue,candidate,gain=True,
                meaningful=bool(improved or progress))
            Library(state['project'], scope=library_scope(state)).outcome(issue['owner'], candidate['pptx']['sha256'],
                     'improved' if improved else 'partial', {'issue':issue['id'], 'cause':candidate['reason'].get('cause'),
                                  'diagnostics':packet.get('diagnostics')})
            cause=candidate['reason'].get('cause') or {}
            if cause.get('stage'):
                comp=_component(state,issue['owner']);lib=Library(state['project'], scope=library_scope(state))
                lib.put('experience',state['task_id']+':'+issue['id'],
                    {'semantic_class':comp['semantic_class'],'state':'task_useful',
                     'property':issue['property'],'stage':cause['stage'],
                     'conditions':{'property':[issue['property']]},
                     'expected':issue['expected'][:500],'root_evidence':str(cause.get('evidence',''))[:1000],
                     'outcome':'improved' if improved else 'partial',
                     'successful_effect':str(candidate['reason']['expected_effect'])[:700] if improved else '',
                     'progress_effect':progress[:4] if partial else [],
                     'observed_result':observations[:4],'pptx':candidate['snapshot'],
                     'limits':['One observed context; assess applicability to the new source before reuse']})
        else:
            outcome = result.get('outcome', 'uncertain')
            if outcome not in ('ineffective','harmful','uncertain'):
                outcome = 'uncertain'
            issue['status'] = 'open'
            issue['non_improving_count']=issue.get('non_improving_count',0)+1
            from .repair_strategy import record as record_strategy
            record_strategy(state,issue,candidate,gain=False)
            state.pop('pending_built', None)
            state['attempts'].append({'issue':issue['id'], 'signature':candidate['reason']['signature'],
                                      'outcome':outcome, 'revision':state['revision']})
            Library(state['project'], scope=library_scope(state)).outcome(issue.get('owner'), candidate['pptx']['sha256'],
                       outcome, {'issue':issue['id'], 'cause':candidate['reason'].get('cause')})
        state['active_candidate'] = None
    elif (candidate.get('reason') or {}).get('kind')=='render_refresh':
        # Native content is byte-identical; this adopts its actually observed
        # current representation, not an invented quality improvement.
        adoption=candidate_adoption.prepare(task,state,candidate,{},mode='render_refresh',observations=observations,result=result)
        candidate_adoption.retain(task,state,candidate,adoption,packet=packet,result=result)
    elif not state['selected']:
        # This is retained working progress, not final quality acceptance.
        adoption=candidate_adoption.prepare(task,state,candidate,{},mode='working_baseline',observations=observations,result=result)
        candidate_adoption.retain(task,state,candidate,adoption)
    if target in state['built'] and not findings and all(o['outcome']=='matched' for o in observations):
        state['protected'][target] = {'authority':'agent', 'revision':state['revision'],
                'fingerprint':state['built'][target]['fingerprint'], 'observations':observations}
    state['review_queue'].remove(target)
    if not state['review_queue']:
        state['active_candidate'] = None
    _event(task, 'observed', {'target':target, 'candidate':candidate['pptx']['sha256'],
                            'findings':reported, 'new_findings':created, 'observation_count':len(observations)})


@transaction
def use_native_host_render(task, request):
    """Defer saved drawings to a real host tool after evidenced WSL transport failure.

    This does not change installed capabilities or bypass actual rendering.
    The existing tool_render result must bind the saved PPTX and native receipt.
    """
    task,state=_state(task)
    failure=request.get('transport_failure',{});file=_path(task,failure['path'])
    if digest(file)!=failure.get('sha256'):raise ValueError('Exact actual bridge failure required')
    receipt=read_json(file)
    if (receipt.get('exit_code',0)==0 or 'UtilAcceptVsock' not in receipt.get('stderr','')
            or receipt.get('stdout') or not state['capabilities'].get('windows_office',{}).get('available')
            or request.get('host')!='windows' or not request.get('host_tool_available')
            or not request.get('reason')):
        raise ValueError('Use the actual native Windows host only for an observed pre-job WSL transport failure with an available host tool')
    from .office_bridge import _host_path
    script=Path(__file__).resolve().parent.parent/'run_office_job.ps1'
    state['render_dispatch']={'mode':'native_host_tool','host':'windows','transport_failure':failure,
        'reason':request['reason'],'wrapper_path':_host_path(script),'wrapper_hash':digest(script),
        'native_command':'powershell.exe -NoProfile -ExecutionPolicy Bypass -File <wrapper> -Kind render -InputPptx <saved candidate Windows path> -OutDir <new task-local Windows output> -PreviewWidth <fixed render width>',
        'acceptance':'Existing tool_render hash-bound actual preview/render receipt; no unrendered score or capability substitution.',
        'limits':'Task-local route. Use only while a Windows host tool is actually available; new environments must choose their actual available native renderer.'}
    _save(task,state)
    return state['render_dispatch']


def _allowed_delta(old, new, grants):
    """Enforce the same leaf grant on planned data and the saved native patch."""
    before={o['id']:o for o in old['objects']}; after={o['id']:o for o in new['objects']}
    def covered(oid, action, mapping):
        while oid in mapping:
            if grants.get(oid)==[action]:
                return True
            oid=mapping[oid].get('parent')
        return False
    replacements={oid for oid,fields in grants.items() if fields==['replace_component']
                  and (oid in before or oid in after)}
    def replaced(oid,mapping):
        while oid in mapping:
            if oid in replacements:return True
            oid=mapping[oid].get('parent')
        return False
    # A replaced artwork subtree owns its internal material order. Keep the
    # replacement root and every outside object's relative order protected.
    fixed={oid for oid in before.keys() & after.keys()
           if 'paint_order' not in grants.get(oid,[]) and
           (oid in replacements or not (replaced(oid,before) or replaced(oid,after)))}
    if [o['id'] for o in old['objects'] if o['id'] in fixed]!=[o['id'] for o in new['objects'] if o['id'] in fixed]:
        raise ValueError('Unapproved relative paint order change')
    for rid in replacements:
        if rid not in before or rid not in after or before[rid].get('parent')!=after[rid].get('parent') or before[rid]['bbox']!=after[rid]['bbox']:
            raise ValueError('Artwork replacement preserves its owner, parent and observed extent: '+rid)
        if any(replaced(oid,before) and item['render_type'] in ('text','equation','connector','table') for oid,item in before.items()):
            raise ValueError('Artwork replacement cannot flatten independent scientific content')
    for oid in before.keys() | after.keys():
        if replaced(oid,before) or replaced(oid,after):continue
        if oid not in before:
            if not covered(oid,'add',after):
                raise ValueError('Ungrant-ed new native part: '+oid)
            continue
        if oid not in after:
            if not covered(oid,'remove',before):
                raise ValueError('Ungrant-ed removed native part: '+oid)
            continue
        a,b=before[oid],after[oid]
        fields=set(grants.get(oid,[]))
        if fields=={'replace_native'}:
            if a['render_type'] not in ('shape','path','bezier','connector') or b['render_type'] not in ('shape','path','bezier','connector'):
                raise ValueError('Native whole-part change cannot flatten text/math/group')
            continue
        for key in ('parent','render_type','semantic_type'):
            if a.get(key)!=b.get(key):
                enclosing=after.get(b.get('parent'),{})
                regroup=(key=='parent' and 'reparent' in fields and
                         grants.get(b.get('parent'))==['add'] and
                         enclosing.get('render_type')=='group' and
                         enclosing.get('parent')==a.get('parent'))
                if not regroup:raise ValueError('Unapproved structural change: '+oid+'.'+key)
        if a.get('z_order')!=b.get('z_order') and 'paint_order' not in fields:
            raise ValueError('Unapproved paint order change: '+oid)
        def content_value(value):
            value=copy.deepcopy(value)
            if value.get('geometry_ref'):
                # Identical content-addressed geometry can live in another
                # task-local cache directory after an implementation change.
                # Builder still binds and reads the actual bytes by SHA256.
                value['geometry_ref'].pop('path',None)
            return value
        table_format_change=False
        if a['render_type']=='table' and content_value(a['content'])!=content_value(b['content']):
            from .native_commit import _table_cell_field
            ac,bc=copy.deepcopy(a['content']),copy.deepcopy(b['content']);ast=ac.pop('cell_styles',None);bst=bc.pop('cell_styles',None)
            if ac!=bc:raise ValueError('Cell formatting preserves native grid, source text and merge structure')
            rows=ac['rows'];ast=ast or [[{} for _ in row] for row in rows];bst=bst or [[{} for _ in row] for row in rows]
            changed={(i,j) for i,row in enumerate(rows) for j in range(len(row)) if ast[i][j]!=bst[i][j]}
            granted={v for f in fields if (v:=_table_cell_field(f)) is not None}
            if not changed or not changed<=granted:raise ValueError('Grant each actually changed native table cell format')
            table_format_change=True
        if content_value(a['content'])!=content_value(b['content']) and not table_format_change:
            permit = {'geometry'} if a['render_type'] in ('shape','path','bezier') else (
                     {'equation'} if a['render_type']=='equation' else {'text_content','text_body'}
                     if a['render_type']=='text' else {'geometry','connector'} if a['render_type']=='connector' else set())
            if not fields & permit:
                raise ValueError('Unapproved content change: '+oid)
        for key in a['style'].keys() | b['style'].keys():
            if a['style'].get(key)==b['style'].get(key):
                continue
            aliases={'fill':{'fill','fill_color'},'stroke':{'line','line_color'},
                     'line_width':{'line'},'rotation':{'rotation'}}
            if 'style.'+key not in fields and not fields & aliases.get(key,set()):
                raise ValueError('Unapproved style change: '+oid+'.'+key)
        for index,key in enumerate(('left','top','width','height')):
            if a['bbox'][index]!=b['bbox'][index] and 'bbox.'+key not in fields:
                raise ValueError('Unapproved placement change: '+oid+'.bbox.'+key)


def _impact(state, old, new, grants, roi):
    boxes=[roi]
    for built in (old,new):
        boxes.extend(o['bbox'] for o in built['objects'] if o['id'] in grants)
    x=max(0,min(b[0] for b in boxes)-10);y=max(0,min(b[1] for b in boxes)-10)
    right=min(state['source_size'][0],max(b[0]+b[2] for b in boxes)+10)
    bottom=min(state['source_size'][1],max(b[1]+b[3] for b in boxes)+10)
    return [x,y,right-x,bottom-y]


@transaction
@checked_submit
def submit(task, result):
    task, state = _state(task)
    packet = state['packet']
    if packet:
        from .packet_compaction import restore
        packet=restore(task,packet)
        state['packet']=packet
    if not packet or result.get('packet_id') != packet['packet_id']:
        raise ValueError('Result must answer the current work packet')
    if packet['source'] != state['source']['sha256'] or packet['revision'] != state['revision']:
        raise ValueError('Stale work packet')
    if state['selected'] and digest(_path(task, state['selected']['pptx']['path'])) != state['selected']['pptx']['sha256']:
        raise ValueError('User edited the baseline: sync before committing')
    for view in packet['views']:
        if digest(_path(task, view['path'])) != view['sha256']:
            raise ValueError('Observation view changed')
    if state.get('objectives',{}).get('component_first'):
        from .component_workflow import implementation
        if packet.get('component_implementation')!=implementation():raise ValueError('Component implementation changed; request a current next packet')
    from .workflow_guard import packet_writer
    with packet_writer(task,state,packet):return _submit_current(task,state,packet,result)


def _submit_current(task,state,packet,result):
    if packet['kind'] in ('component_contract_source','component_build_work','component_local_work','component_layout_work','component_final_visual','component_recovery_work','component_repair_work','component_user_mapping','component_font_review','component_final_audit'):
        from .component_workflow import submit_result
        from .workflow_guard import packet_writer
        with packet_writer(task,state,packet):return submit_result(task,result,packet)
    if packet['kind']=='tool_render' and result.get('render_failure') and state.get('objectives',{}).get('component_first'):
        from .component_constructor import retain_render_failure
        return retain_render_failure(task,result)
    if packet['kind']=='tool_font_embedding' and state.get('objectives',{}).get('component_first'):
        from .component_constructor import accept_font_provider
        return accept_font_provider(task,result)
    with writer(task):
        kind = packet['kind']
        if kind=='source_scene_relations':
            if state.get('active_candidate') or state.get('selected'):
                raise ValueError('Repair saved Scene edges through a bounded source/native edit')
            corrected=result.get('scene_relations')
            semantic_composition.validate_relations(corrected,'scene_relations')
            previous=copy.deepcopy(state['analysis'].get('scene_relations',[]))
            state.setdefault('scene_relation_history',[]).append({'prior':previous,'corrected':copy.deepcopy(corrected),
                'source_hash':state['source']['sha256'],'kind':'typed_original_edge_correction'})
            state['analysis']['scene_relations']=copy.deepcopy(corrected)
            if state.get('font_pending_candidate'):
                ref=state['font_pending_candidate']['scene']
                if digest(_path(task,ref['path']))!=ref['sha256']:raise ValueError('Pending Scene changed')
                pending=read_json(_path(task,ref['path']));pending['relations']=copy.deepcopy(corrected)
                file=task/'work'/('corrected-scene-'+identity(pending)+'.json');write_json(file,pending)
                state['font_pending_candidate']['scene']=_file(task,file)
            _event(task,'source_scene_edges_corrected',{'prior':previous,'new':corrected})
        elif kind=='tool_font_embedding':
            candidate=state['active_candidate'];provider=result.get('font_provider',{})
            file=_path(task,provider.get('path',''))
            original=_path(task,candidate['pptx']['path'])
            if (provider.get('input_sha256')!=candidate['pptx']['sha256'] or digest(original)!=candidate['pptx']['sha256']
                    or not file.is_file() or digest(file)!=provider.get('sha256') or file.resolve()==original.resolve()):
                raise ValueError('Font provider must bind this immutable input and a separate staged output')
            scene=read_json(_path(task,candidate['scene']['path']))
            from .font_embedding import transfer_provider
            embedded=transfer_provider(original,file,font_contract.current_bindings(scene))
            candidate['font_delivery']={'binding':font_contract.guard_saved(scene,original),'embedding':embedded}
            candidate['pptx']=_file(task,original);candidate['snapshot']=Library(state['project'], scope=library_scope(state)).blob(original)
            state['scene']=candidate['scene'];state['stage']='host_render'
        elif kind == 'font_binding':
            pending=state['font_pending_candidate'];ref=pending['scene']
            if digest(_path(task,ref['path']))!=ref['sha256']:raise ValueError('Pending source font scene changed')
            scene=read_json(_path(task,ref['path']))
            requested={r['id'] for r in packet['requests']}
            if any(v.get('request_id') not in requested for v in result.get('font_bindings',[])):
                raise ValueError('Font response expands beyond this bounded work packet')
            if result.get('font_samples'):
                from .font_collection import store_samples
                store_samples(task,state,scene,result['font_samples'])
            if result.get('font_constraints'):
                from .font_collection import store_constraints
                if set(result['font_constraints'])-requested:raise ValueError('Font narrowing escaped the current request batch')
                store_constraints(task,state,scene,result['font_constraints'])
            if result.get('font_bindings'):font_contract.bind(task,state,scene,result['font_bindings'])
            elif not (result.get('font_samples') or result.get('font_constraints')):
                raise ValueError('Submit original glyph samples, source-supported narrowing or explicit font bindings')
        elif kind == 'rule_coverage_source':
            execution_contract.bind(task,state,result,state.get('active_candidate') or state['selected'])
        elif kind == 'source_spacing_source':
            from .source_spacing import bind as bind_spacing
            if set(result)-{'packet_id','kind','entries'}:
                raise ValueError('Original spacing responses contain packet_id, kind and segmentation entries only')
            bind_spacing(task,state,{'entries':result.get('entries',[])})
        elif kind == 'frame_plan_source':
            frame_plan.bind(task,state,result,_scene(task,state))
        elif kind == 'semantic_composition_source':
            semantic_composition._bind(task,state,result)
        elif kind == 'source_repeat_observation':
            from .source_repeat import bind as bind_repeats
            bind_repeats(task,state,{**result,'source_hash':state['source']['sha256']})
        elif kind == 'external_edit':
            if result.get('candidate_hash')!=state['selected']['pptx']['sha256']:
                raise ValueError('Reconcile the actual adopted user version')
            if not {v['sha256'] for v in packet['views']} <= set(result.get('view_hashes', [])):
                raise ValueError('User-intent reconciliation needs its actual original/user-version views')
            from .external_sync import reconcile
            reconcile(task,state,result)
        elif kind == 'textbox_source':
            from .textbox_quality import _bind
            _bind(task,state,{**result,'source_hash':packet['source_hash'],'baseline_hash':packet['baseline_hash']})
        elif kind == 'observation':
            _accept_analysis(task, state, copy.deepcopy(result['analysis']))
        elif kind == 'source_recursion':
            from .source_recursion import bind as bind_recursion
            bind_recursion(task,state,{**result,'source_hash':state['source']['sha256']})
        elif kind == 'adaptive_source_detail':
            from .adaptive_detail import bind as bind_detail
            bind_detail(task,{**result,'source_hash':state['source']['sha256'],
                'candidate_hash':(state.get('active_candidate') or state['selected'])['pptx']['sha256']},_state=state)
        elif kind == 'source_connection_observation':
            from .source_connections import compile_observation
            graph=compile_observation(task,state,{**result,'source_hash':state['source']['sha256']})
            path=task/'source/connections/original'/(identity(graph)+'.json');write_json(path,graph)
            prior=state.get('source_connection_graph')
            if prior:state.setdefault('source_connection_graph_history',[]).append(prior)
            state['source_connection_graph']=_file(task,path);state.pop('acceptance',None)
        elif kind == 'signal_source':
            from .signal_semantics import bind as bind_signal
            bind_signal(task,state,{**result,'source_hash':state['source']['sha256']})
        elif kind == 'source_inventory':
            from .source_features import bind
            value=result.get('source_inventory')
            if result.get('source_inventory_ref'):
                ref=result['source_inventory_ref']
                if digest(_path(task,ref['path']))!=ref['sha256']:raise ValueError('Source inventory reference changed')
                value=read_json(_path(task,ref['path']))
            bind(task,state,value or {})
        elif kind == 'strategy':
            from .repair_strategy import choose
            issue=next(i for i in state['issues'] if i['id']==packet['target'])
            choose(task,state,issue,result)
        elif kind == 'source_spec':
            comp = _component(state,packet['target'])
            spec=copy.deepcopy(result['source_spec'])
            prior=state['quality'].get('specifications',{}).get(comp['id'])
            if prior and identity(prior)!=identity(spec):
                source_views={v['sha256'] for v in packet['views'] if v['role']=='source'}
                correction={'prior_spec_hash':result.get('prior_spec_hash'),
                            'source_view_hash':result.get('source_view_hash'),
                            'kind':result.get('source_correction_kind'),
                            'reason':result.get('source_correction_reason'),
                            'specification':spec}
                affected=source_quality.revise_spec(state,comp,correction,source_views)
                if comp['id'] in state['built']:
                    source_quality.bind_objects(state,comp['id'],state['built'][comp['id']])
                state['review_queue'] += [x for x in affected if x not in state['review_queue']]
                _event(task,'source_specification_corrected',{'owner':comp['id'],'affected':affected})
            else:
                source_quality.accept_spec(state,comp,spec)
            write_json(task/'source'/'specifications.json',state['quality'])
            # Revising the source guide is not authorization to rebuild a
            # saved page. Preserve its actual candidate and scoped review.
            if state.get('built') and (state.get('selected') or state.get('active_candidate')):
                state['stage']='review'
            else:
                state['stage'] = 'source_refinement' if source_quality.refinement(state) else 'construction'
        elif kind=='local_edit':
            _user_edit_candidate(task,state,result)
        elif kind == 'method':
            comp = _component(state, packet['target'])
            state['built'][comp['id']] = _parts(task, state, comp, result['method'])
            state['methods'][comp['id']] = result['method']
            if source_quality.enabled(state):source_quality.bind_objects(state,comp['id'],state['built'][comp['id']])
        elif kind == 'tool_render' and result.get('render_failure'):
            candidate=state['active_candidate'];failure=result['render_failure']
            file=_path(task,failure['path']);receipt=read_json(file)
            if (not state.get('selected') or candidate.get('preview') or state['stage']!='host_render'
                    or failure.get('sha256')!=digest(file)
                    or receipt.get('pptx_hash')!=candidate['pptx']['sha256'] or receipt.get('exit_code',0)==0
                    or result.get('operation')!='keep_baseline'):
                raise ValueError('Retire only a bound failed actual host export; keep saved construction and selected baseline')
            retained={'candidate':candidate,'failure':failure,'pending_methods':state.get('pending_built'),
                      'quality':'UNMEASURED_NO_ACTUAL_PREVIEW','next':'Use a distinct source-supported representation; never repeat the failed bytes unchanged'}
            write_json(_path(task,candidate['pptx']['path']).parent/'retained-render-failure.json',retained)
            state.setdefault('render_failures',[]).append({'revision':state['revision'],'pptx':candidate['pptx'],'failure':failure})
            reason=candidate.get('reason') or {};issue_id=reason.get('id')
            if issue_id:
                state['attempts'].append({'issue':issue_id,'signature':reason['signature'],'outcome':'render_failed','revision':state['revision']})
                from .repair_strategy import record as record_strategy
                actual_issue=next(i for i in state['issues'] if i['id']==issue_id)
                record_strategy(state,actual_issue,candidate,gain=False)
            state['review_queue']=[v for v in state['review_queue'] if v!='repair:'+str(issue_id)]
            state['active_candidate']=None;state.pop('pending_built',None);state['stage']='review'
            _event(task,'failed_host_render_retained',{'pptx':candidate['pptx'],'failure':failure,'baseline':state['selected']['pptx'],'quality':'unmeasured'})
        elif kind == 'tool_render':
            from PIL import Image
            candidate = state['active_candidate']
            preview = _path(task, result['preview'])
            receipt = _path(task, result['render'])
            actual = read_json(receipt)
            if actual.get('pptx_hash') != candidate['pptx']['sha256'] or actual.get('preview_hash') != digest(preview):
                raise ValueError('Host render must bind the actual saved PPTX and preview')
            size = Image.open(preview).size
            if abs(size[1]-size[0]*state['source_size'][1]/state['source_size'][0]) > 1.01:
                raise ValueError('Host render does not use the fixed source canvas')
            candidate.update(preview=_file(task, preview), render=_file(task, receipt))
            if state.get('component_workflow') and state.get('objectives',{}).get('component_first'):
                candidate['render_environment']=state['capabilities']['fingerprint']
                state.update(stage='review',packet=None);state['actions']+=1
                _save(task,state)
                return {'status':'ACTUAL_RENDER_RECORDED','next':'next '+str(task),'whole_audit_executed':False}
            _save(task,state)
            if ((candidate.get('reason') or {}).get('kind')=='complete_native_rebuild'
                    and state.get('selected',{}).get('pptx',{}).get('sha256')==candidate['pptx']['sha256']):
                # The imported working baseline has identical bytes. Keep its
                # real render identity together; this confers no acceptance.
                state['selected']=copy.deepcopy(candidate)
            if (candidate.get('reason') or {}).get('kind')=='external_sync':
                state['selected']=candidate;state['active_candidate']=None
                state['stage']='external_edit_pending';state['packet']=None
                state['actions']+=1;_save(task,state)
                return {'status':'USER_ADOPTED_QUALITY_PENDING','next':'next '+str(task)}
            if (semantic_composition.enabled(state) and candidate.get('semantic_composition_guard',{}).get('capture_request')
                    and not (receipt.parent/'composition-capture.json').is_file()
                    and str(actual.get('backend','')).lower()=='libreoffice'):
                semantic_composition.capture_portable(task,state,candidate)
            if semantic_composition.continue_capture(task,state,candidate):
                state['stage']='host_render'
            else:
                frame_plan.register_failures(task,state,candidate)
                semantic_composition.register_failures(task,state,candidate)
                state['stage'] = 'review'
        elif kind == 'review':
            if result.get('source_correction'):
                owner=result['source_correction']['specification']['owner']
                comp=_component(state,owner)
                source_views={v['sha256'] for v in packet['views'] if v['role']=='source'}
                affected=source_quality.revise_spec(state,comp,result['source_correction'],source_views)
                if owner in state['built']:source_quality.bind_objects(state,owner,state['built'][owner])
                state['review_queue'] += [x for x in affected if x not in state['review_queue']]
                write_json(task/'source'/'specifications.json',state['quality'])
                _event(task,'source_specification_corrected',{'owner':owner,'affected':affected})
            else:
                _observe(task, state, packet, result)
        elif kind == 'repair':
            issue = next(i for i in state['issues'] if i['id'] == packet['target'])
            if not result.get('cause', {}).get('stage') or not result['cause'].get('evidence') or not result.get('expected_effect'):
                raise ValueError('Repair needs a located cause hypothesis and expected effect')
            source_quality.validate_cause(task,state,issue,result['cause'])
            from .repair_strategy import authorize as authorize_strategy
            branch=authorize_strategy(state,issue,result['cause'],result.get('allowed_changes',{}),result.get('method'))
            if result.get('render_configuration'):
                if result['cause']['stage'] not in ('font','render'):
                    raise ValueError('Renderer refresh must target an observed font/render cause')
                _save(task,state)
                q=refresh_render(task,_path(task,result['render_configuration']),issue=issue,cause=result['cause'],strategy_branch=branch)
                return {'status':'RESULT_RECORDED','stage':'review','next':'next '+str(task)}
            if state['protected'].get(issue['owner'],{}).get('authority') == 'user':
                raise ValueError('User-frozen owner requires a new explicit user grant')
            allowed = result.get('allowed_changes', {})
            if not allowed:
                raise ValueError('Explicit leaf/native changes required')
            allowed_ids = set(allowed)
            if source_quality.enabled(state):
                source_quality.protect_scope(state,issue,allowed)
            owner = issue['owner']
            replacement = _parts(task, state, _component(state, owner), result['method'])
            updates={owner:replacement}
            related=[]
            for extra_owner,method in result.get('related_methods',{}).items():
                # Shared-root-cause batching is limited to already located
                # open issues, never a free grant to unrelated satisfied parts.
                matching=[i for i in state['issues'] if i['status']=='open' and i['owner']==extra_owner
                          and i['property']==issue['property'] and i.get('cause_hint')==issue.get('cause_hint')]
                if not issue.get('cause_hint') or not matching:
                    raise ValueError('Related repair needs the same located root cause and property')
                if state['protected'].get(extra_owner,{}).get('authority')=='user':
                    raise ValueError('Shared repair cannot touch user-frozen owner')
                updates[extra_owner]=_parts(task,state,_component(state,extra_owner),method)
                related.extend(i['id'] for i in matching)
            owner_ids = {o['id'] for cid,built in updates.items()
                         for o in state['built'][cid]['objects']+built['objects']}
            if not allowed_ids <= owner_ids:
                raise ValueError('Repair expands beyond the located owner')
            for cid,built in updates.items():
                _allowed_delta(state['built'][cid],built,allowed)
            from .source_property_protection import guard as protect_satisfactory_properties
            protect_satisfactory_properties(state,updates)
            from . import VERSION
            signature = identity({'runtime_version':VERSION,'methods':{cid:b['method'] for cid,b in updates.items()},'cause':result['cause'],
                                  'baseline':state['selected']['pptx']['sha256']})
            if any(a['signature']==signature and a['outcome']!='improved' for a in state['attempts']):
                raise ValueError('Unchanged failed action must not be repeated')
            issue['attempt_count'] += 1
            impacted=_impact(state,state['built'][owner],replacement,allowed,issue['roi'])
            for cid,built in updates.items():
                impacted=_impact(state,state['built'][cid],built,allowed,impacted)
            regions=[]
            for cid,built in updates.items():
                for obj in state['built'][cid]['objects']+built['objects']:
                    if obj['id'] not in allowed:continue
                    x,y,w,h=obj['bbox']
                    pad=1.0
                    left=max(0,x-pad);top=max(0,y-pad)
                    right=min(state['source_size'][0],x+w+pad);bottom=min(state['source_size'][1],y+h+pad)
                    box=[left,top,right-left,bottom-top]
                    if box not in regions:regions.append(box)
            reason = {'id':issue['id'], 'signature':signature, 'cause':result['cause'],
                      'strategy_branch':branch,
                      'related_issues':related,
                      'expected_effect':result['expected_effect'],
                      'check_roi':impacted,'check_regions':regions}
            state['pending_built'] = updates
            _candidate(task, state, _scene(task,state,updates), baseline=state['selected'],
                       allowed=allowed, reason=reason)
        elif kind == 'source_gap':
            issue = next(i for i in state['issues'] if i['id']==packet['target'])
            comp = result['component']
            _roi(comp['roi'], state['source_size'])
            if any(c['id']==comp['id'] for c in state['analysis']['components']):
                raise ValueError('New source owner needs a new identity')
            if not comp.get('source_note') or not comp.get('parts'):
                raise ValueError('Located source-grounded parts required')
            comp.setdefault('review_unit',True)
            state['analysis']['components'].append(comp)
            if source_quality.enabled(state):
                if comp.get('source_spec'):
                    source_quality.accept_spec(state,comp,comp['source_spec'])
                else:
                    state['quality']['source_queue'].append(comp['id'])
            issue['owner']=comp['id']
            if issue.get('source_feature') and state.get('source_features'):
                from .source_features import bind
                features=read_json(_path(task,state['source_features']['path']))
                for feature in features['features']:
                    if feature['id']==issue['source_feature']:
                        feature['owner']=comp['id'];part=comp['parts'][0]
                        feature['source_part']=part if isinstance(part,str) else part['id']
                bind(task,state,features)
            state['methods'][comp['id']]=result['method']
            # The first missing component is an explicit addition, not a broad rebuild.
            state['built'][comp['id']]={'objects':[], 'method':{}, 'fingerprint':identity([])}
        else:
            raise ValueError('Unknown packet type')
        state['actions'] += 1
        state['packet'] = None
        if source_quality.enabled(state):
            from .source_property_protection import capture as preserve_satisfactory_properties
            preserve_satisfactory_properties(state)
        _save(task, state)
    return {'status':'RESULT_RECORDED', 'stage':state['stage'], 'next':'next ' + str(task)}


@transaction
def export(task,output=None,*,output_root=None,new_export=False):
    task,state=_state(task)
    if state.get('objectives',{}).get('component_first'):
        from .component_final import export as component_export
        return component_export(task,output,output_root=output_root,new_export=new_export)
    from .export_destination import reserve,publish
    plan=reserve(state['project'],state.get('selected'),output_root=output_root,exact=output,new=new_export)
    if plan['status']=='PUBLISHED':return publish(plan,None)
    return publish(plan,_export_into(task,plan['stage']))


def _export_into(task, output):
    task, state = _state(task)
    if state.get('objectives',{}).get('component_first'):
        from .component_workflow import export as component_export
        return component_export(task,output)
    if state['stage'] != 'accepted' or not state['selected']:
        raise ValueError('Export requires an accepted actual drawing; preserve progress otherwise')
    selected = state['selected']
    execution_contract.final_gate(task,state,selected)
    execution_contract.verify_acceptance(task,state,selected)
    _save(task,state)
    selected_scene=read_json(_path(task,selected['scene']['path']))
    if state['objectives'].get('source_font_contract') and not selected_scene.get('font_plan'):
        raise ValueError('Source/user fonts need explicit bindings before portable export')
    if selected_scene.get('font_plan'):
        final_fonts=font_contract.guard_saved(selected_scene,_path(task,selected['pptx']['path']))
        delivery=selected.get('font_delivery',{}).get('embedding',{})
        if delivery.get('status') not in ('EMBEDDED_FULL_EDITABLE_FONTS','NO_TEXT_FONTS'):
            raise ValueError('Complete correct editable font embedding before portable PPTX delivery')
        state['final_font_delivery']={**final_fonts,'embedding':delivery}
    from .source_features import pending as feature_pending
    if feature_pending(task,state):raise ValueError('Resolve independent original feature debt before export')
    state['final_semantic_composition']=semantic_composition.retention_guard(task,state,selected,strict=True)
    state['final_frame_plan']=frame_plan.guard(task,state,selected,strict=True)
    from .textbox_quality import guard_saved as text_guard,report as text_report
    typography=text_guard(task,state,_path(task,selected['pptx']['path']))
    if state['objectives'].get('source_textbox_quality') and typography['unbound']:
        raise ValueError('Bind each original-only text/math owner before export')
    if typography['bound_count']:
        final_typography=text_report(task,state,selected)
        if any(not item.get('values') or item['values'].get('content_match')!=1 or item['values'].get('math_match')!=1
                for item in final_typography['items']):
            raise ValueError('Resolve source contents/structure and missing glyph measures before export')
        if any(zone.get('status')!='measured' for item in final_typography['items'] for zone in item.get('zones',[])):
            raise ValueError('Observe every required original math/glyph role before export; parent similarity cannot waive missing zones')
        state['final_textbox_quality']=final_typography
    for field in ('pptx','preview','render'):
        if digest(_path(task, selected[field]['path'])) != selected[field]['sha256']:
            raise ValueError('Selected artifact changed')
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('Versioned output must be new')
    user_output=output
    output=task/'exports'/('internal-'+identity({'candidate':selected['pptx'],'destination':str(user_output)})[:24])
    if output.exists():raise FileExistsError('Inspect the retained internal export before retry')
    output.mkdir(parents=True)
    from . import VERSION
    pptx = output/(state.get('source_stem',state['task_id']) + '-v' + VERSION + '.pptx')
    shutil.copyfile(_path(task,selected['pptx']['path']),pptx)
    shutil.copyfile(_path(task,selected['preview']['path']),output/'Preview.png')
    render = _path(task, selected['render']['path'])
    from .saved_components import inventory, export_owners
    inv = inventory(pptx)
    by_name = {o['name']:o['shape_id'] for o in inv['objects']}
    owners = [{'id':c['id'],'shape_ids':[by_name[c['id']]],'slide':1}
              for c in state['analysis']['components'] if c['id'] in by_name]
    manifest = {'version':'semantic-owners-1','pptx_hash':digest(pptx),'components':owners}
    if owners:
        component_index=export_owners(pptx,manifest,output/'Components',inventories={1:inv})
        __import__('gc').collect()
        # Store original bitmap evidence and actual editable PPTX, plus a
        # bounded data recipe. Public packages never include this private lib.
        lib=Library(state['project'], scope=library_scope(state))
        from PIL import Image
        with Image.open(_path(task,state['source']['path'])) as original:
            owner_slides={owner['semantic_id']:owner['slide'] for owner in component_index['components']}
            for comp in state['analysis']['components']:
                cid=comp['id']
                if cid not in by_name:continue
                x,y,w,h=comp['roi']
                crop=task/'components'/(cid+'-source.png')
                original.crop(tuple(map(round,(x,y,x+w,y+h)))).save(crop)
                preview=_preview(task,state,selected,comp['roi'],'library-'+cid)[1]
                built=state['built'][cid]['objects']
                recipe=None
                object_ids={o['id'] for o in built}
                external_connections=any(o['content'].get(field) not in object_ids
                    for o in built for field in ('source','target','source_anchor_object','target_anchor_object')
                    if o['content'].get(field))
                if state['methods'][cid].get('recipe_state')!='snapshot_only' and 2<=len(built)<=128 and all(o['render_type'] in ('group','shape','path','text','equation','connector')
                                            and 'geometry_ref' not in o['content'] and 'native_asset' not in o['content'] for o in built) and not external_connections:
                    ids={o['id']:'root' if o['id']==cid else 'part_'+str(i) for i,o in enumerate(built)}
                    raw=[]
                    for obj in built:
                        item={k:copy.deepcopy(obj.get(k)) for k in ('id','render_type','semantic_type','parent','bbox','content','style')}
                        item['id']=ids[obj['id']];item['parent']=ids.get(obj.get('parent'))
                        for field in ('source','target','source_anchor_object','target_anchor_object'):
                            if item['content'].get(field):item['content'][field]=ids[item['content'][field]]
                        raw.append(item)
                    payload={'recipe':'native_template','parameters':{'objects':raw}}
                    if len(canonical(payload))<28000:
                        file=task/'components'/(cid+'-recipe.json');write_json(file,payload);recipe=lib.blob(file)
                lib.capture_asset(state['task_id']+':'+cid,output/'Components/Components_editable.pptx',
                    {'semantic_class':comp['semantic_class'],'view':comp['view'],'parts':comp['parts'],
                     'edit_targets':comp['edit_targets'],'style_tags':comp['style_tags'],
                     'representation':'mixed' if any(o['render_type']=='photo' for o in built) else 'svg' if any(o['render_type']=='svg' for o in built) else 'native',
                     'component_id':cid,'root_name':cid,'slide':owner_slides[cid],'recipe_state':'current' if recipe else 'snapshot_only',
                     'observation':state['reviews'].get(cid),'source_task':state['task_id'],
                     'limits':['Actual result observed; desktop editing behaviour not inferred from structure']
                         + (['External connection endpoints are not hidden recipe dependencies; reconnect through declared source relations'] if external_connections else [])},
                    preview=_path(task,preview['path']),source=crop,recipe=recipe)
                # Reusable natural leaves share the immutable full PPTX blob;
                # their exact saved group is the symbol. No large geometry JSON
                # enters host context and no duplicate media file is stored.
                def capture_children(children):
                    for child in children:
                        name=child['id']
                        if name in by_name:
                            x,y,w,h=child['roi'];file=task/'components'/(name+'-source.png')
                            original.crop(tuple(map(round,(x,y,x+w,y+h)))).save(file)
                            _,view=_preview(task,state,selected,child['roi'],'library-'+name)
                            lib.capture_asset(state['task_id']+':'+name,pptx,
                                {'semantic_class':child['semantic_class'],'view':child.get('view','any'),
                                 'parts':child['parts'],'edit_targets':child.get('edit_targets',child['parts']),
                                 'style_tags':child.get('style_tags',[]),'representation':'svg' if next((r.get('representation') for r in inv['objects'] if r['name']==name),None)=='svg' else 'native',
                                 'root_name':name,'slide':1,'recipe_state':'snapshot_only',
                                 'source_task':state['task_id'],'observation':state['reviews'].get(cid),
                                 'limits':['Native snapshot; external connections cannot be imported as hidden dependencies']},
                                preview=_path(task,view['path']),source=file)
                        capture_children(child['method'].get('children',[]))
                capture_children(state['methods'][cid].get('children',[]))
    report = {'version':VERSION,'source':state['source'],'pptx_sha256':digest(pptx),
              'telemetry':state['telemetry'],'issues':state['issues'],'reviews':state['reviews'],
              'provenance':state['analysis'].get('reconstruction_notes',[]),
              'font_delivery':state.get('final_font_delivery',{'status':'LEGACY_PORTABILITY_UNMEASURED'}),
              'render_scope':read_json(render).get('scope'),
              'native_objects':len(inv['objects']),
              'raster_objects':sum(o.get('representation')=='raster' for o in inv['objects']),
              'svg_objects':sum(o.get('representation')=='svg' for o in inv['objects']),
              'equation_editing':{
                  'office_math_objects':sum(o.get('equation_editing')=='office_math' for o in inv['objects']),
                  'native_formatted_text_objects':sum(o.get('equation_editing')=='native_formatted_text' for o in inv['objects']),
                  'native_formatted_text_names':[o['name'] for o in inv['objects'] if o.get('equation_editing')=='native_formatted_text'],
                  'limits':'Native formatted formulas use editable text/script controls, not the Office equation editor. Complex math remains Office Math. Editing modes are derived from the saved file, not inferred from vector appearance.'},
              'whole_diagnostics':_metrics(task,state,selected,[0,0,*state['source_size']]),
              'metric_limits':'Raw fixed-canvas source comparison; semantic redraws and excluded UI can lower pixel similarity. No perfect quality or native desktop behaviour inferred.'}
    report['paper_export']={'status':'VALIDATION_ONLY','user_deliverables':['PPTX','Report']}
    from .component_report import generate as component_metrics
    details=component_metrics(task,output/'Metrics',office_bounds=render.parent/'text-bounds.json')
    report['component_metrics']={'path':'Metrics/Component-metrics.json','components':details['component_count'],
        'spacing_pairs':len(details['spacing_pairs']),'scope':'raw source-relative ROI and declared envelope/Office ink diagnostics'}
    if selected_scene.get('font_plan'):
        font_report={**state['final_font_delivery'],'font_choices':[{
            'owner':b['request']['owner'],'location':b['request']['location'],'role':b['request']['role'],
            'family':b['family'],'origin':b['origin'],'identity_status':b['status'],
            'file_sha256':b['resource']['file_sha256'],'face_index':b['resource']['face_index'],
            'synthetic_style':b['synthetic_style']} for b in font_contract.current_bindings(selected_scene)],
            'limits':'Embedded editable fonts target supporting PowerPoint versions; other readers may ignore font parts. Raster-inferred identity remains approximate, not exact original metadata.'}
        write_json(output/'Fonts.json',font_report)
        report['font_report']='Fonts.json'
    write_json(output/'Result.json',report)
    write_json(output/'Acceptance.json',execution_contract.verify_acceptance(task,state,selected))
    write_json(output/'Execution-coverage.json',execution_contract.report(task,state,selected))
    _event(task,'export',{'output':str(output),'pptx_sha256':digest(pptx)})
    from .user_delivery import expose
    result=expose(pptx,None,details,user_output,output/'compact-audit',status='EXPORTED',
        acceptance=execution_contract.verify_acceptance(task,state,selected),caps=state['capabilities'],base_render=render)
    from .transient_export import release_task_pdfs
    state['pdf_disposal']=release_task_pdfs(task)
    from .projection_gc import dispose
    state['projection_disposal']=dispose(task)
    _save(task,state)
    return result


def _baseline_file(task, candidate, library):
    """Recover only independently retained or exact unchanged native bytes."""
    if candidate.get('snapshot'):
        return library.resolve(candidate['snapshot'])
    ref=candidate.get('pptx') or {}
    file=_path(task,ref['path']) if ref.get('path') else None
    if file is None or not file.is_file() or digest(file)!=ref.get('sha256'):
        raise ValueError('Retained baseline is missing or changed; restore its immutable original before external sync')
    return file


@transaction
def sync(task, edited_pptx):
    """Explicit user-file adoption. Originals and old selected snapshots survive."""
    task,state=_state(task)
    if state.get('objectives',{}).get('component_first'):
        from .component_user_sync import sync as component_sync
        return component_sync(task,state,edited_pptx)
    edited_pptx=Path(edited_pptx).resolve()
    from .saved_ppt_diff import snapshot
    from .saved_components import inventory
    lib=Library(state['project'], scope=library_scope(state))
    old=state['selected']
    if not old:
        raise ValueError('A selected baseline is needed to adopt external edits')
    original=_baseline_file(task,old,lib)
    before,after=snapshot(original),snapshot(edited_pptx)
    changed=[key for key in before['objects'].keys() | after['objects'].keys()
             if before['objects'].get(key)!=after['objects'].get(key)]
    revision=state['revision']+1
    folder=task/'versions'/('user-'+str(revision).zfill(3));folder.mkdir()
    retained=folder/'drawing.pptx';shutil.copyfile(edited_pptx,retained)
    candidate={**old,'revision':revision,'pptx':_file(task,retained),
               'snapshot':lib.blob(retained),'native_authority':'user_edit',
               'recipe_state':'snapshot_only','changed_properties':changed}
    candidate.pop('preview',None);candidate.pop('render',None)
    candidate['reason']={'kind':'external_sync'}
    from .external_sync import migrate
    migration=migrate(task,state,old,candidate)
    inv=inventory(retained)
    state['native_overlay']=inv
    names=set(migration['changed']) | set(migration['aliases']) | set(migration['aliases'].values())
    touched=_adopt_native_owners(state,names,revision,'explicitly adopted edited PPTX',lib)
    state['external_versions'].append({'revision':revision,'changes':changed,'snapshot':candidate['snapshot']})
    state['revision']=revision;state['selected']=candidate;state['active_candidate']=None
    state['packet']=None;state['stage']='external_edit_pending';state['review_queue']=[]
    candidate['adoption_scope']='user-authoritative snapshot; semantic quality not automatically approved'
    if state['capabilities']['libreoffice']['available']:
        render_saved(retained,folder/'render',state['capabilities'],state['objectives']['render_width'])
        candidate['preview']=_file(task,folder/'render/Final_preview.png')
        candidate['render']=_file(task,folder/'render/render.json')
    else:
        state['active_candidate']=candidate;state['stage']='host_render'
    candidate['touched_owners']=touched
    _save(task,state)
    return {'status':'USER_ADOPTED_QUALITY_PENDING','revision':revision,'changed_objects':changed,
            'migration':state['external_reconciliation'],'next':'next '+str(task)}
