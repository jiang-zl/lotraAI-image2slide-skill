"""Immutable staging; only the existing full validators can seal a contract."""
import copy
import re
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from .common import read_json,write_json,identity,canonical,digest,writer
from .workflow_guard import enabled,require

SCHEMA='incremental-contract-1.37.0'
KEYS={'feature_bindings':'feature','spatial_bindings':'landmark','spatial_footprint_bindings':'footprint'}
_SEAL=ContextVar('lotra_incremental_seal',default=None)


def load(task,state):
    ref=state.get('incremental_contract')
    if not ref:return {'schema':SCHEMA,'source_hash':state['source']['sha256'],'generation':0,
        'outline':None,'source_chunks':{},'binding_chunks':{},'units':[],'features':[],
        'spatial':{'schema':'spatial-1.35.1','frames':[],'landmarks':[],'relations':[],'footprints':[]},
        'source_sealed':False,'binding_sealed':False,'scene':{},'contract':{}}
    from .component_workflow import _resource
    value=read_json(_resource(task,ref))
    if value.get('schema')!=SCHEMA or value.get('source_hash')!=state['source']['sha256']:
        raise ValueError('Incremental progress belongs to a different original/policy')
    return copy.deepcopy(value)


def counts(value):
    outline=(value.get('outline') or {}).get('units',[])
    observed={u['id'] for u in value['units']}
    bound={b['feature'] for b in value['contract'].get('feature_bindings',[])}
    return {'original_units':len(outline),'observed_units':len(observed),'features':len(value['features']),
        'bound_features':len(bound),'components':len(value['contract'].get('components',[])),
        'pending_units':[u['id'] for u in outline if u['id'] not in observed],
        'pending_features':[f['id'] for f in value['features'] if f['id'] not in bound],
        'source_sealed':value['source_sealed'],'binding_sealed':value['binding_sealed']}


def visible_counts(value):
    result=counts(value)
    for key in ('pending_units','pending_features'):
        result[key+'_count']=len(result[key]);result[key]=result[key][:16]
    result['continuation']='Select remaining IDs from the hash-bound checkpoint with packet_detail.py; no rows are omitted from sealing.'
    return result


def _snapshot(task,value):
    from . import agent_runtime as a
    value=copy.deepcopy(value);value['generation']+=1
    folder=task/'component-workflow/progress';folder.mkdir(parents=True,exist_ok=True)
    file=folder/('Checkpoint-'+identity(value)+'.json')
    if not file.exists():write_json(file,value)
    return value,a._file(task,file)


@contextmanager
def sealing(task,value,kind,*,correction=False):
    token=_SEAL.set({'task':Path(task).resolve(),'value':copy.deepcopy(value),'kind':kind,'correction':correction})
    try:yield
    finally:_SEAL.reset(token)


def source_correction_active(task):
    active=_SEAL.get() or {}
    return active.get('task')==Path(task).resolve() and active.get('kind')=='source' and active.get('correction') is True


def _observation(value,state):
    return {'schema':'source-features-1.35.1','source_hash':state['source']['sha256'],'canvas':list(state['source_size']),
        'basis':'unchanged_original','observer':value['outline']['observer'],
        'observations':'\n'.join([value['outline']['observations']]+[s for s in value.get('observations',[]) if s]),
        'units':value['units'],'features':value['features'],'spatial':value['spatial'],'source_views':value.get('source_views',[])}


def seal_state(task,state,kind):
    """Called inside the existing source/bind state commit, after full validation."""
    active=_SEAL.get()
    if not active:return
    if active['task']!=Path(task).resolve() or active['kind']!=kind:raise ValueError('Incremental seal task/phase mismatch')
    value=copy.deepcopy(active['value'])
    if kind=='source':value.update(source_sealed=True,source_observation=copy.deepcopy(state['source_feature_observation']))
    else:value.update(binding_sealed=True,sealed_contract=copy.deepcopy(state['component_workflow']['contract']))
    _,state['incremental_contract']=_snapshot(Path(task),value)


def _commit(task,value,event):
    from . import agent_runtime as a
    task,state=a._state(task);value,ref=_snapshot(task,value)
    with writer(task):
        state['incremental_contract']=ref;state['packet']=None
        a._save(task,state)
        a._event(task,event,{'checkpoint':ref,'counts':counts(value),'acceptance':False})
    return {'status':event.upper(),'checkpoint':ref,'coverage':counts(value),'acceptance':False}


def _rows(before,after,key='id',limit=512,*,corrections=None,section=''):
    if not isinstance(after,list) or len(after)>limit:raise ValueError('Use a bounded row batch')
    result=copy.deepcopy(before);indexed={r[key]:r for r in result};seen=set()
    for row in after:
        if not isinstance(row,dict) or not isinstance(row.get(key),str) or not row[key] or row[key] in seen:
            raise ValueError('Distinct nonempty row identities required: '+key)
        seen.add(row[key]);prior=indexed.get(row[key])
        if prior is not None and prior!=row:
            correction=(corrections or {}).get(section+'/'+row[key],{})
            if (correction.get('prior_hash')!=identity(prior) or not correction.get('reason') or not correction.get('source_evidence')):
                raise ValueError('Frozen row conflict: '+section+'/'+row[key]+'; submit a prior_hash, reason and located source_evidence correction')
            result[result.index(prior)]=copy.deepcopy(row);indexed[row[key]]=row
        if prior is None:result.append(copy.deepcopy(row));indexed[row[key]]=row
    return result


def _merge(before,after,*,corrections=None,section=''):
    result=copy.deepcopy(before)
    if not isinstance(after,dict):raise ValueError('A partial object is required')
    for key,value in after.items():
        if key not in result:
            result[key]=_rows([],value,KEYS.get(key,'id')) if isinstance(value,list) and value and all(isinstance(r,dict) for r in value) else copy.deepcopy(value)
            continue
        old=result[key]
        location=(section+'.'+key).strip('.')
        if isinstance(old,dict) and isinstance(value,dict):result[key]=_merge(old,value,corrections=corrections,section=location)
        elif isinstance(old,list) and isinstance(value,list):
            if all(isinstance(r,dict) for r in old+value):result[key]=_rows(old,value,KEYS.get(key,'id'),corrections=corrections,section=location)
            else:
                if any(isinstance(r,(dict,list)) for r in old+value):
                    if old!=value:raise ValueError('Frozen structured field conflict: '+key)
                else:result[key]=old+[copy.deepcopy(v) for v in value if v not in old]
        elif old!=value:
            correction=(corrections or {}).get(section+'/'+key,{})
            if correction.get('prior_hash')!=identity(old) or not correction.get('reason') or not correction.get('source_evidence'):
                raise ValueError('Frozen field conflict: '+section+'/'+key+'; use an explicit prior-bound source correction')
            result[key]=copy.deepcopy(value)
    return result


def _outline(value,state):
    if (not isinstance(value,dict) or value.get('source_hash')!=state['source']['sha256'] or
            value.get('canvas')!=list(state['source_size']) or value.get('observer') not in ('host_model','human') or
            value.get('complete_scope') is not True or not value.get('observations')):
        raise ValueError('Original outline requires current source/canvas, observer and explicit full scope')
    rows=value.get('units',[])
    if not rows or len(rows)>20000:raise ValueError('A nonempty complete original unit outline is required')
    _rows([],rows,limit=20000);by_id={u['id']:u for u in rows}
    from .component_metrics import window
    for unit in rows:
        if not unit.get('source_evidence'):raise ValueError('Outline units need located source evidence')
        window(unit['roi'],state['source_size']);seen={unit['id']};parent=unit.get('parent')
        while parent:
            if parent in seen or parent not in by_id:raise ValueError('Outline has a missing parent or cycle')
            seen.add(parent);parent=by_id[parent].get('parent')
    return copy.deepcopy(value)


def submit(task,request):
    from . import agent_runtime as a
    task,state=a._state(task);require(task,'incremental contract submission')
    if not enabled(state):raise ValueError('Incremental staging is for explicitly bound 1.37 execution tasks')
    from .component_protocol import finite
    finite(request)
    if len(canonical(request))>2_000_000:raise ValueError('Use smaller incremental chunks')
    value=load(task,state);operation=request.get('operation')
    correction=operation=='source_correction'
    if correction:
        if (not value['source_sealed'] or value['binding_sealed'] or state.get('component_workflow') or
                request.get('prior_checkpoint')!=state.get('incremental_contract') or
                request.get('prior_observation')!=state.get('source_feature_observation') or
                not request.get('revision_reason') or not request.get('corrections')):
            raise ValueError('Source correction requires open binding, exact current checkpoint/observation, row corrections and revision_reason')
        operation='source_chunk'
    if operation=='source_outline':
        if value['outline']:raise ValueError('Original outline is already frozen')
        value['outline']=_outline(request['outline'],state)
        return _commit(task,value,'source_outline_frozen')
    if not value['outline']:raise ValueError('Freeze the full original outline first')
    if operation in ('source_chunk','bind_chunk'):
        chunk=request.get('chunk_id')
        if not isinstance(chunk,str) or not re.fullmatch('[A-Za-z0-9_.-]{1,100}',chunk):raise ValueError('Stable chunk_id required')
        collection=value['source_chunks' if operation=='source_chunk' else 'binding_chunks']
        if chunk in collection:
            if collection[chunk]!=identity(request):raise ValueError('Chunk identity conflict; retained data cannot be replaced')
            state['packet']=None
            with writer(task):a._save(task,state)
            return {'status':'CHUNK_RETAINED','coverage':counts(value),'acceptance':False}
        if len(collection)>=2048:raise ValueError('Bounded incremental chunk limit reached; preserve the current checkpoint')
        corrections=request.get('corrections',{})
        if not isinstance(corrections,dict) or corrections and request.get('prior_checkpoint')!=state['incremental_contract']:
            raise ValueError('Corrections require the exact current checkpoint and explicit row addresses')
        if operation=='source_chunk':
            if value['source_sealed'] and not correction:raise ValueError('Original observation is sealed; use the explicit correction flow')
            patch=request['observation']
            if set(patch)-{'units','features','spatial','observations','source_views'}:raise ValueError('Source chunks contain original data only')
            if not any(patch.get(k) for k in ('units','features','spatial')):raise ValueError('Empty source chunk')
            known={u['id']:u for u in value['outline']['units']}
            units=patch.get('units',[])
            if len(units)>32 or len(patch.get('features',[]))>128:raise ValueError('Use at most 32 units / 128 features per chunk')
            from .component_metrics import window
            for unit in units:
                window(unit['roi'],state['source_size'])
                spatial=unit.get('spatial',{});stop=unit.get('decomposition',{})
                from .spatial_frames import MODES
                if (not unit.get('source_evidence') or stop.get('state') not in ('leaf','split','unresolved') or not stop.get('reason') or
                        spatial.get('mode') not in MODES or not spatial.get('frame') or not spatial.get('source_evidence') or
                        type(spatial.get('container')) is not bool or spatial.get('placement') not in ('standing','attached','free','annotation','unknown') or
                        spatial.get('observability') not in ('clear','partial','unresolved')):
                    raise ValueError('Original unit '+str(unit.get('id'))+' needs complete decomposition/spatial decisions; unknowns remain explicit')
                if unit['id'] in known:
                    original=known[unit['id']]
                    if unit.get('parent')!=original.get('parent') or unit['roi']!=original['roi']:
                        correction=corrections.get('outline/'+unit['id'],{})
                        if correction.get('prior_hash')!=identity(original) or not correction.get('reason') or not correction.get('source_evidence'):
                            raise ValueError('Source chunk cannot change the frozen outline without an explicit outline correction')
                        original.update(parent=unit.get('parent'),roi=copy.deepcopy(unit['roi']))
                else:
                    if unit.get('parent') not in known:raise ValueError('New descendants require a frozen original parent')
                    outline={k:copy.deepcopy(unit[k]) for k in ('id','parent','roi','source_evidence')}
                    value['outline']['units'].append(outline);known[unit['id']]=outline
            from .component_source_features import KINDS,CAPABILITIES
            for feature in patch.get('features',[]):
                if (feature.get('kind') not in KINDS or not feature.get('source_evidence') or
                        feature.get('observability') not in ('clear','partial','unresolved') or type(feature.get('required',True)) is not bool or
                        set(feature.get('requirements',[]))-CAPABILITIES or
                        any(k in feature for k in ('owners','component','representation','native_owner'))):
                    raise ValueError('Original feature '+str(feature.get('id'))+' needs located source fields before choosing native owners')
                window(feature['roi'],state['source_size'])
            value['units']=_rows(value['units'],units,corrections=corrections,section='units')
            value['features']=_rows(value['features'],patch.get('features',[]),limit=128,corrections=corrections,section='features')
            if any(f.get('unit') not in known for f in value['features']):raise ValueError('Source feature has no original outline unit')
            value['spatial']=_merge(value['spatial'],patch.get('spatial',{}),corrections=corrections,section='spatial')
            if set(value['spatial'])-{'schema','frames','landmarks','relations','footprints'}:raise ValueError('Unknown spatial staging section')
            value.setdefault('observations',[]).append(patch.get('observations',''))
            value['source_views']=_rows(value.get('source_views',[]),patch.get('source_views',[]),key='path')
            _outline(value['outline'],state)
        else:
            if not value['source_sealed'] or value['binding_sealed']:raise ValueError('Binding chunks require a sealed original and open binding phase')
            patch=request['binding']
            if set(patch)-{'scene','contract'}:raise ValueError('Binding chunk contains only scene/contract fields')
            scene=patch.get('scene',{});contract=patch.get('contract',{})
            if any(k in scene for k in ('source','evidence','profile','schema_version','revision')):
                raise ValueError('Program owns the bound Scene resource identities')
            if any(k in contract for k in ('schema','source_hash','workflow_version','design_revision','source_inventory','source_observation','policy','authority','source_scene','spatial','spatial_units','spatial_basis','verification_policy','line_verification')):
                raise ValueError('Program owns source policy/inventory; chunks cannot lower them')
            if len(scene.get('objects',[]))>128 or len(contract.get('components',[]))>32:raise ValueError('Use bounded binding chunks')
            value['scene']=_merge(value['scene'],scene,corrections=corrections,section='scene')
            value['contract']=_merge(value['contract'],contract,corrections=corrections,section='contract')
        collection[chunk]=identity(request)
        if correction:
            from .component_source_features import observe
            revised={key:copy.deepcopy(request[key]) for key in ('revision_reason','source_corrections','spatial_corrections') if key in request}
            revised['observation']=_observation(value,state)
            with sealing(task,value,'source',correction=True):outcome=observe(task,revised)
            current=a._state(task)[1]
            return {'status':'SOURCE_CORRECTION_SEALED','checkpoint':current['incremental_contract'],
                'observation':outcome['observation'],'coverage':visible_counts(load(task,current)),'acceptance':False}
        return _commit(task,value,operation+'_saved')
    if operation=='source_seal':
        if value['source_sealed']:raise ValueError('Original is already sealed')
        progress=counts(value)
        if progress['pending_units'] or not value['features']:raise ValueError('Every outlined original unit needs its full observation before sealing')
        observed=_observation(value,state)
        from .component_source_features import observe
        with sealing(task,value,'source'):observe(task,{'observation':observed})
        state=a._state(task)[1]
        return {'status':'SOURCE_OBSERVATION_SEALED','checkpoint':state['incremental_contract'],
            'coverage':visible_counts(load(task,state)),'acceptance':False}
    if operation=='bind_seal':
        if not value['source_sealed'] or value['binding_sealed']:raise ValueError('Original must be sealed and binding must be open')
        if counts(value)['pending_features']:raise ValueError('Every original feature requires a binding before contract seal')
        scene=copy.deepcopy(value['scene'])
        scene.update(schema_version='0.1',revision=0,source=copy.deepcopy(state['source']),
            evidence=a._file(task,task/'source/evidence.json'),profile=a._file(task,task/'source/profile.json'))
        scene.setdefault('canvas',{'width':state['source_size'][0],'height':state['source_size'][1],
            'unit':'px','target_width_inches':request.get('target_width_inches',10)})
        scene.setdefault('relations',[]);scene.setdefault('prototypes',[])
        contract=copy.deepcopy(value['contract'])
        contract.update(schema='component-protocol-1.32.0',workflow_version='1.35.2',design_revision=8,
            source_hash=state['source']['sha256'],source_inventory=copy.deepcopy(value['units']))
        contract.setdefault('relations',[]);contract.setdefault('spatial_bindings',[]);contract.setdefault('spatial_footprint_bindings',[])
        contract.setdefault('scope',{'excluded_checks':[]})
        folder=task/'component-workflow';file=folder/('Incremental-scene-'+identity(scene)+'.json')
        if not file.exists():write_json(file,scene)
        from .component_workflow import bind
        with sealing(task,value,'binding'):
            bind(task,{'source_scene':a._file(task,file),'authority':state['source_feature_observation'],'contract':contract})
        state=a._state(task)[1]
        return {'status':'COMPONENT_CONTRACT_SEALED','checkpoint':state['incremental_contract'],
            'coverage':visible_counts(load(task,state)),'acceptance':False}
    raise ValueError('Unknown incremental operation')


def source_phase(task,state):
    value=load(task,state)
    if not value['outline']:return 'source_outline',value
    if counts(value)['pending_units']:return 'source_chunk',value
    return 'source_seal',value


def template(task,state,packet):
    """Mechanical scaffolding only; unresolved semantic/numeric fields stay empty."""
    request={};kind=packet['kind'];target=packet['target']
    if kind=='component_contract_source' and target=='source_features' and not state.get('source_feature_observation'):
        phase,value=source_phase(task,state)
        request={'operation':phase}
        if phase=='source_outline':
            request['outline']={'source_hash':state['source']['sha256'],'canvas':list(state['source_size']),
                'observer':'host_model','complete_scope':True,'observations':'','units':[]}
        elif phase=='source_chunk':
            request.update(chunk_id='source-'+str(value['generation']+1),observation={'units':[],'features':[],
                'spatial':{'frames':[],'landmarks':[],'relations':[],'footprints':[]},'observations':''})
        packet['incremental']={'operation':phase,'allowed_operations':[phase,'source_chunk'] if phase=='source_seal' else [phase],
            'coverage':visible_counts(value),'checkpoint':state.get('incremental_contract'),
            'scope':'Persist complete source evidence in bounded chunks; partial progress is never acceptance.'}
    elif kind=='component_contract_source' and target=='component_contract' and not state.get('component_workflow'):
        value=load(task,state);pending=counts(value)['pending_features']
        phase='bind_chunk' if pending else 'bind_seal';request={'operation':phase}
        if phase=='bind_chunk':request.update(chunk_id='binding-'+str(value['generation']+1),binding={
            'scene':{'objects':[]},'contract':{'components':[],'feature_bindings':[],'spatial_bindings':[],'spatial_footprint_bindings':[]}})
        packet['incremental']={'operation':phase,'allowed_operations':([phase,'bind_chunk'] if phase=='bind_seal' else [phase])+['source_correction'],
            'coverage':visible_counts(value),'checkpoint':state.get('incremental_contract'),
            'source_correction':{'prior_observation':state.get('source_feature_observation'),
                'required':['operation:source_correction','chunk_id','prior_checkpoint','prior_observation','revision_reason','corrections','observation'],
                'rule':'Use bounded source_chunk observation rows and exact prior-hash row corrections. Retain all units/features, history and binding chunks. Existing source_corrections/spatial_corrections and quality guards still apply.'}}
    else:
        if kind in ('component_layout_work','component_final_visual','component_font_review'):
            request={'evidence':{'path':'','sha256':''}}
            if kind=='component_font_review':
                request.update(phase='complete',source_hash=state['source']['sha256'],
                    pptx_hash=(state.get('active_candidate') or state['selected'])['pptx']['sha256'],changes=[])
        elif kind=='component_final_audit':request={}
        elif packet.get('component_action'):request=copy.deepcopy(packet['component_action'])
        if kind=='component_local_work':
            scope=packet.get('component_batch',[target])
            request['component']=target
            if len(scope)>1:request['components']=scope
            request.setdefault('source_hash',state['source']['sha256'])
            candidate=state.get('active_candidate') or state.get('selected')
            if candidate:request.setdefault('pptx_hash',candidate['pptx']['sha256'])
            if packet.get('submit_operation')=='source_or_measurement_decision':
                packet['source_feature_correction']={'prior_observation':state.get('source_feature_observation'),
                    'return':'component_request.source_correction{prior_observation,features:[complete corrected rows],corrections:{features/ID:{prior_hash,reason,source_evidence}}}; include revision_reason, source_corrections for weakened/line facts and any prior_line_hash. Only this component subtree is authorized. Full original validation, history, bounds and explicit rebind remain mandatory.'}
    result={'packet_id':packet['packet_id']}
    if kind=='font_binding' and packet.get('required_step'):
        field={'source_style':'font_constraints','resource_decision':'font_constraints',
               'glyph_samples':'font_samples','family_choice':'font_constraints','bind':'font_bindings'}[packet['required_step']]
        result[field]=[] if field=='font_bindings' else {}
    if kind.startswith('component_'):result['component_request']=request
    if kind=='component_local_work':
        result['operation']=packet.get('submit_operation') or packet.get('component_action',{}).get('operation')
    folder=task/'packets';folder.mkdir(exist_ok=True)
    file=folder/('Submit-template-'+packet['packet_id']+'.json')
    write_json(file,result)
    filled=Path(task)/'scratch'/('Submit-'+packet['packet_id']+'.json')
    # Phase operations belong in the bound template, not in a legacy direct
    # component-workflow command that the current task guard rejects.
    packet['action']='submit'
    packet['submission_command']=['submit',str(Path(task).resolve()),str(filled.resolve())]
    packet['submission_template']={'path':file.relative_to(task).as_posix(),'sha256':digest(file),
        'copy_to':filled.relative_to(task).as_posix(),
        'instruction':'Copy this hash-bound template to copy_to, fill the current packet decisions and evidence, then run submission_command with the prepared launcher. Empty fields are not PASS.'}
    packet['completion_policy']={'accepted_export_required':True,'candidate_is_deliverable':False,
        'on_context_limit':'retain checkpoint and resume next','on_backend_failure':'retain explicit blocker; no direct-build fallback'}
    return packet
