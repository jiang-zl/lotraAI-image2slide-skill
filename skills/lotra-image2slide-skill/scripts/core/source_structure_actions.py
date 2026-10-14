"""Finite source-function restoration with exact complete native replay.

Original-only contracts are frozen before construction. The guarded replay
inherits every unrelated native subtree and resource; it cannot waive the
independent recursion, content, signal, frame or source appearance gates.
"""
import copy
import math
import numbers
from pathlib import Path
from zipfile import ZipFile
from .common import digest,identity,read_json,write_json,safe_path,writer

def _same_function_value(a,b):
    # Source px/normalized controls can differ by one floating-point ULP
    # across host math libraries. This fixed sub-EMU construction tolerance
    # never relaxes source targets or complete saved-native replay.
    if isinstance(a,numbers.Real) and isinstance(b,numbers.Real) and not isinstance(a,bool) and not isinstance(b,bool):
        return math.isfinite(a) and math.isfinite(b) and abs(a-b)<=1e-11
    if isinstance(a,dict) and isinstance(b,dict):return set(a)==set(b) and all(_same_function_value(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(_same_function_value(x,y) for x,y in zip(a,b))
    return type(a)==type(b) and a==b


def _source_identity(unit):
    # Observation status and the current drawing fingerprint are derived
    # data. Original evidence, predicates, ROI and bindings remain frozen.
    return identity({k:v for k,v in unit.items() if k not in ('status','built_fingerprint')})


def _historical_units(task,state,contract):
    """Only predecessor replay may read retained immutable original units."""
    for ref in state.get('source_unit_archives',[]):
        file=safe_path(task,ref['path'])
        if digest(file)!=ref['sha256']:raise ValueError('Historical source unit archive changed')
        data=read_json(file)
        if data.get('schema')!='source-unit-snapshot-1' or data.get('source_hash')!=state['source']['sha256']:
            raise ValueError('Historical source unit archive belongs to another original')
        if all(u in data['units'] and _source_identity(data['units'][u])==h for u,h in contract['source_units'].items()):
            return data['units']
    return None


def _verify_source_units(state,contract,task=None,historical=False):
    if contract.get('schema')=='source-structure-function-2':
        current=all(_source_identity(state['quality']['units'][u])==h for u,h in contract['source_units'].items())
        return current or bool(historical and task is not None and _historical_units(task,state,contract))
    # Exact compatibility proof for earlier records: reconstruct only the
    # compiler's finite mutable metadata; never accept a changed source fact.
    from .source_quality import bind_objects
    check=copy.deepcopy(state)
    for owner in {state['quality']['units'][u]['owner'] for u in contract['source_units']}:
        bind_objects(check,owner,check['built'][owner])
    for uid,wanted in contract['source_units'].items():
        current=state['quality']['units'][uid]; rebound=check['quality']['units'][uid]
        if _source_identity(current)!=_source_identity(rebound):return False
        matched=False
        for variant in (current,rebound):
            for status in ('required_unmeasured','minimum_met','below_minimum','semantic_issue'):
                old=copy.deepcopy(variant);old['status']=status
                matched |= identity(old)==wanted
        if not matched:return False
    return True


def _objects(task,state,unit,method,historical=False):
    from .source_feature_functions import semantic_root
    name=semantic_root(unit,method.get('feature_function'))
    component={'id':name,'roi':unit['roi'],'bbox':unit['roi'],'semantic_class':unit['profile']}
    if set(method)=={'container_function'}:
        from .container_functions import construct
        objects=construct(task,state,component,method['container_function'])
    elif set(method)=={'signal_function'}:
        from .signal_semantics import construct
        objects=construct(task,state,component,method['signal_function'])
    elif set(method)=={'feature_function'}:
        from .source_feature_functions import construct,specifications,function_versions
        accepted=specifications(task,state).get(unit['id'])==method['feature_function']
        if historical:accepted |= method['feature_function'] in function_versions(task,state).get(unit['id'],[])
        if not accepted:
            raise ValueError('Freeze the independent original feature function before constructing')
        objects=construct(task,state,component,method['feature_function'])
    else:
        raise ValueError('Use an implemented source-bound container, signal or original-feature function')
    if not historical:
        from .icon_detail import verify_constructor
        verify_constructor(task,state,unit,objects)
    return objects


def execute(task,request):
    from . import agent_runtime as a
    from .quality_intent import source_view
    task,state=a._state(task);baseline=state.get('active_candidate') or state.get('selected')
    if baseline and baseline.get('reason',{}).get('kind')=='source_structure_function' and baseline['pptx']['sha256']!=request.get('expected_baseline_sha256'):
        ref=baseline['reason']['contract'];file=safe_path(task,ref['path'])
        if digest(file)!=ref['sha256']:raise ValueError('Saved original function contract changed')
        frozen=read_json(file)
        if (frozen['source_hash']!=request.get('source_hash') or frozen['baseline']['pptx']['sha256']!=request.get('expected_baseline_sha256')
                or frozen['items']!=request.get('items')):raise ValueError('Existing candidate belongs to another source-function transaction')
        donor=safe_path(task,baseline['pptx']['path']).parent/'donor.pptx'
        if not any(r['candidate']==baseline['pptx']['sha256'] for r in state.get('source_structure_attempts',[])):
            record={'candidate':baseline['pptx']['sha256'],'baseline':frozen['baseline']['pptx']['sha256'],
                'source_hash':state['source']['sha256'],'contract':ref,'donor':a._file(task,donor),
                'scene':baseline['scene'],'allowed':baseline['allowed'],'status':'SAVED_NATIVE_TRANSACTION_RECOVERED'}
            with writer(task):
                state.setdefault('source_structure_attempts',[]).append(record);a._save(task,state)
        return {'status':'EXISTING_SAVED_NATIVE_CONSTRUCTION_RECOVERED','candidate':baseline['pptx'],'owners':sorted(baseline['allowed'])}
    if baseline and not baseline.get('render'):
        selected=state.get('selected')
        if selected and selected.get('render') and selected['pptx']==baseline['pptx']:
            state.setdefault('render_preparation_history',[]).append(copy.deepcopy(baseline));baseline=selected
    if (not baseline or not baseline.get('render') or request.get('source_hash')!=state['source']['sha256']
            or request.get('expected_baseline_sha256')!=baseline['pptx']['sha256']):
        raise ValueError('Restore from the exact actually rendered native baseline and original')
    rows=request.get('items',[])
    if not rows or len(rows)>16 or len({r['unit'] for r in rows})!=len(rows):
        raise ValueError('Bounded distinct original unit restoration required')
    if state.get('source_connection_graph') or state.get('connection_contract'):
        from . import source_connections as sc,connection_geometry as cg
        try:
            sc.load(task,state)
            if state.get('connection_contract'):cg._load_contract(task,state)
        except (ValueError,KeyError,FileNotFoundError) as exc:
            packet=sc.packet(task,state)
            if not packet:packet={'kind':'source_connection_recompile','action':'connection-geometry bind',
                'source_graph':state.get('source_connection_graph'),'prior_contract':state.get('connection_contract'),
                'scope':'Recompute the complete original-bound connector contract before native construction; retain predecessor'}
            return {'status':'WORK_PACKET','packet':packet,'drawn':False,'reason':str(exc)}
    scene=read_json(safe_path(task,baseline['scene']['path']));allowed={};source_units={};replaced_descendants=set()
    for row in rows:
        unit=state['quality']['units'][row['unit']]
        if unit['profile'] in ('text','formula','relation') or not row.get('evidence'):
            raise ValueError('Use the separate exact text/math/relation constructors')
        from .quality_intent import _bounds
        _bounds(row.get('source_constraints'))
        view=source_view(task,state,unit['roi'],2)
        if row.get('source_view')!=view:raise ValueError('Restoration needs the exact original-only view')
        out=_objects(task,state,unit,row['method'])
        from .source_feature_functions import semantic_root
        name=semantic_root(unit,row['method'].get('feature_function'))
        old=next(o for o in scene['objects'] if o['id']==name)
        if old['render_type'] in ('text','math','table','connector'):
            raise ValueError('A source-function illustration repair cannot replace text or scientific relations')
        descendants={name}
        while True:
            added={o['id'] for o in scene['objects'] if o.get('parent') in descendants}-descendants
            if not added:break
            descendants |= added
        # Non-painted endpoint anchors belong to the independent connection
        # contract, not the icon anatomy being restored. Retain their exact
        # source-supported coordinates; the connection gate checks them again.
        from .native_connection_transaction import PREFIX as port_prefix
        out += [copy.deepcopy(o) for o in scene['objects'] if o['id'] in descendants and o['id'].startswith(port_prefix)]
        for o in out:
            if o['id'].startswith(port_prefix):
                o['style'].update(fill=None,stroke=None);o['style'].pop('line_width',None)
        replaced_descendants |= descendants-{name}
        position=next(i for i,o in enumerate(scene['objects']) if o['id']==name)
        scene['objects']=[o for o in scene['objects'] if o['id'] not in descendants]
        out[0]['parent']=old.get('parent');scene['objects'][position:position]=out
        allowed[name]=['replace_component'];source_units[row['unit']]=_source_identity(unit)
    if state.get('frame_plan'):
        from . import frame_plan as fp
        previous=copy.deepcopy(state['frame_plan']);plan=copy.deepcopy(fp.load(task,previous))
        current_names={o['id'] for o in scene['objects']}
        retired=replaced_descendants-current_names
        # Explicit semantic-root replacement retires only its old drawing
        # parts. Preserve the historical plan; never retire another owner.
        plan['scope']=[n for n in plan['scope'] if n not in retired]
        plan['coverage']=[r for r in plan['coverage'] if r['object'] not in retired]
        extra=sorted(set(fp.required(scene))-set(plan['scope']))
        for name in extra:
            plan['scope'].append(name)
            plan['coverage'].append({'object':name,'mode':'inherited','mechanism':'source_part_quality',
                'reason':'Source-function child: exact analytic clipping/native replay, independent original-region content and source appearance checks remain mandatory.'})
        if extra or retired:
            plan['revision']+=1;fp.validate(plan,task,state,scene)
            p=task/'source/structure-functions/frames'/(identity(plan)+'.json');write_json(p,plan)
            state.setdefault('frame_plan_history',[]).append(previous);state['frame_plan']=a._file(task,p)
    contract={'schema':'source-structure-function-2','source_hash':state['source']['sha256'],
              'baseline':copy.deepcopy(baseline),'items':copy.deepcopy(rows),'source_units':source_units}
    file=task/'source/structure-functions'/(identity(contract)+'.json');write_json(file,contract)
    with writer(task):
        candidate=a._candidate(task,state,scene,baseline=baseline,allowed=allowed,
            reason={'id':identity(contract)[:16],'kind':'source_structure_function','contract':a._file(task,file)})
        if candidate is None:return {'status':'FONT_BINDING_REQUIRED_BEFORE_RESTORATION'}
        donor=safe_path(task,candidate['pptx']['path']).parent/'donor.pptx'
        record={'candidate':candidate['pptx']['sha256'],'baseline':baseline['pptx']['sha256'],
            'source_hash':state['source']['sha256'],'contract':a._file(task,file),'donor':a._file(task,donor),
            'scene':candidate['scene'],'allowed':allowed,'status':'SAVED_REQUIRES_ACTUAL_RENDER'}
        state.setdefault('source_structure_attempts',[]).append(record);a._save(task,state)
    return {'status':record['status'],'candidate':candidate['pptx'],'contract':record['contract'],'owners':sorted(allowed)}


def guard(task,state,candidate,approved,_chain_only=False):
    from .source_layout_actions import guard as predecessor_guard
    record=next((r for r in state.get('source_structure_attempts',[]) if r['candidate']==candidate['pptx']['sha256']),None)
    if not record:return {'passed':False,'objects':[],'method':'source_structure_function'}
    contract_file=safe_path(task,record['contract']['path']);donor=safe_path(task,record['donor']['path'])
    if digest(contract_file)!=record['contract']['sha256'] or digest(donor)!=record['donor']['sha256']:
        raise ValueError('Frozen source constructor evidence changed')
    contract=read_json(contract_file);baseline=contract['baseline']
    if contract['source_hash']!=state['source']['sha256'] or not _verify_source_units(state,contract,task,historical=_chain_only):
        raise ValueError('Source-function restoration no longer matches its frozen original unit')
    if baseline['pptx']['sha256']!=approved['pptx']['sha256']:
        if any(r['candidate']==baseline['pptx']['sha256'] for r in state.get('source_structure_attempts',[])):
            prior=guard(task,state,baseline,approved,_chain_only=True)
        else:prior=predecessor_guard(task,state,baseline,approved,_chain_only=True)
        if not prior['passed']:return {'passed':False,'objects':[],'reason':'Restoration predecessor is not the protected actual artwork','predecessor_result':prior}
    else:prior={'objects':[]}
    scene=read_json(safe_path(task,record['scene']['path']));nodes={o['id']:o for o in scene['objects']}
    for row in contract['items']:
        expected_objects=_objects(task,state,state['quality']['units'][row['unit']],row['method'],historical=True)
        # Replay the saved framework compiler too. A source path may be
        # deterministically clipped to its original container after the
        # primitive constructor. Its clipping evidence must be recomputed,
        # rather than ignored or compared to an unclipped constructor.
        if scene.get('frame_plan'):
            from .frame_plan import compile_scene
            replay_scene=copy.deepcopy(scene)
            replacements={o['id']:copy.deepcopy(o) for o in expected_objects}
            for name,obj in replacements.items():obj['parent']=nodes[name]['parent']
            replay_scene['objects']=[replacements.get(o['id'],o) for o in replay_scene['objects']]
            compiled=compile_scene(replay_scene,task,record['allowed'])
            compiled_nodes={o['id']:o for o in compiled['objects']}
            expected_objects=[compiled_nodes[o['id']] for o in expected_objects]
        for expected in expected_objects:
            actual=copy.deepcopy(nodes[expected['id']]);expected=copy.deepcopy(expected)
            # Parent attachment is inherited from the saved owner; all
            # geometry/content/paint from the frozen source function remains.
            expected['parent']=actual['parent']
            for key in ('versions','locks','evidence_status'):actual.pop(key,None);expected.pop(key,None)
            if not _same_function_value(actual,expected):raise ValueError('Saved scene differs from the frozen source function: '+expected['id'])
    baseline_file=safe_path(task,baseline['pptx']['path']);output=safe_path(task,candidate['pptx']['path'])
    if digest(baseline_file)!=baseline['pptx']['sha256'] or digest(output)!=candidate['pptx']['sha256']:
        raise ValueError('Source constructor native input changed')
    order=[state['quality']['units'][r['unit']]['objects'][0] for r in contract['items']] if contract['schema']=='source-structure-function-1' else None
    replay=task/'audits/structure-replay'/(identity({'record':record,'operator_order':order,'version':2})+'.pptx')
    if not replay.exists():
        replay.parent.mkdir(parents=True,exist_ok=True)
        from .scoped_asset_commit import merge
        merge(baseline_file,donor,record['allowed'],replay,_legacy_order=order)
    with ZipFile(replay) as a,ZipFile(output) as b:
        passed=sorted(a.namelist())==sorted(b.namelist()) and all(a.read(n)==b.read(n) for n in a.namelist())
    # Intermediate candidates may fail appearance: a later source repair is
    # allowed to correct them. Replay their exact bytes, but measure every
    # latest frozen source objective on the final current render only.
    inherited={r['unit']:r for r in prior.get('source_function_items',[])}
    inherited.update({r['unit']:r for r in contract['items']})
    appearance=[]
    if not _chain_only and not candidate.get('preview'):passed=False
    elif not _chain_only:
        from .appearance_metrics import image_values,canvas
        import math
        size=tuple(state['source_size'])
        original=canvas(str(safe_path(task,state['source']['path'])),state['source']['sha256'],size)
        actual=canvas(str(safe_path(task,candidate['preview']['path'])),candidate['preview']['sha256'],size)
        for row in inherited.values():
            x,y,w,h=state['quality']['units'][row['unit']]['roi']
            box=(math.floor(x),math.floor(y),math.ceil(x+w),math.ceil(y+h))
            values=image_values(original[box[1]:box[3],box[0]:box[2]],actual[box[1]:box[3],box[0]:box[2]])
            checks=[{'id':r['id'],'value':values.get(r['id']),
                'passed':values.get(r['id']) is not None and (r.get('min') is None or values[r['id']]>=r['min'])
                    and (r.get('max') is None or values[r['id']]<=r['max'])} for r in row['source_constraints']]
            passed &= all(c['passed'] for c in checks)
            appearance.append({'unit':row['unit'],'checks':checks,'source_values':values})
    restored=set(record['allowed'])
    while True:
        added={n for n,o in nodes.items() if o.get('parent') in restored}-restored
        if not added:break
        restored |= added
    result={'passed':bool(passed),'objects':sorted(set(prior['objects'])|restored),
            'method':'exact_frozen_source_function_and_complete_native_replay',
            'contract':record['contract'],'protected':'Every unrelated native subtree/resource must equal the deterministic replay',
            'source_appearance_checks':appearance}
    if _chain_only:result['source_function_items']=list(inherited.values())
    return result
