"""Public full-artifact adoption into the same runtime and final gate."""
import copy, shutil
from pathlib import Path
from .common import digest, identity, read_json, write_json, writer
from . import agent_runtime as a, source_quality


def adopt(task,pptx,request):
    task,state=a._state(task)
    if state.get('objectives',{}).get('component_first'):
        from .component_import import adopt as import_component
        return import_component(task,pptx,request)
    if state.get('selected') or state.get('active_candidate') or not state.get('analysis'):
        raise ValueError('Import one full existing baseline after original analysis in a new task')
    pptx=Path(pptx).resolve()
    if digest(pptx)!=request.get('expected_pptx_sha256') or request.get('source_hash')!=state['source']['sha256']:
        raise ValueError('Bind both immutable original and exact complete native baseline')
    hints=request.get('scene_hints')
    if request.get('scene_hints_ref'):
        ref=request['scene_hints_ref'];p=a._path(task,ref['path'])
        if digest(p)!=ref['sha256']:raise ValueError('Historical hints changed')
        hints=read_json(p)
    with writer(task):
        revision=1
        folder=task/'versions'/('r'+str(revision).zfill(3))
        while folder.exists():
            revision+=1;folder=task/'versions'/('r'+str(revision).zfill(3))
        folder.mkdir()
        saved=folder/'drawing.pptx';shutil.copyfile(pptx,saved)
        from .native_snapshot import snapshot
        scene=snapshot(task,state,saved,hints)
        prior_ref=request.get('prior_source_state')
        if prior_ref:
            from .execution_contract import resource
            prior=read_json(resource(task,prior_ref))
            if prior['source']['sha256']!=state['source']['sha256']:
                raise ValueError('Historical requirements belong to another original')
            previous=prior.get('quality') or prior.get('source_quality')
            if not previous or not previous.get('units'):raise ValueError('Historical source requirements must be complete')
            state['quality']=copy.deepcopy(previous)
            state['quality']['historical_observations']=state['quality'].pop('observations',{})
            state['quality']['historical_usable_limits']=state['quality'].pop('usable_limits',{})
            state['quality']['historical_satisfactory_native_properties']=state['quality'].pop('satisfactory_native_properties',{})
            state['quality']['observations']={}
            for unit in state['quality']['units'].values():
                unit['historical_status']=unit['status'];unit['status']='required_unmeasured'
            state['quality']['source_queue']=[c['id'] for c in state['analysis']['components']]
            state['prior_source_requirements']={'state':prior_ref,'unit_ids':sorted(previous['units']),
                'status':'PRESERVED_REQUIRES_CURRENT_MEASUREMENT','thresholds_relaxed':False}
        names={o['id'] for o in scene['objects']};owners=request.get('owner_map',{})
        source_owners={c['id'] for c in state['analysis']['components']}
        if set(owners)!=names or not set(owners.values())<=source_owners or set(owners.values())!=source_owners:
            raise ValueError('Every actual native node must map to the complete independent source plan')
        for cid in source_owners:
            objects=[o for o in scene['objects'] if owners[o['id']]==cid]
            method={'recipe_state':'snapshot_only','coordinate_space':'source_px','objects':objects,
                    'native_baseline':a._file(task,saved),'source_hash':state['source']['sha256']}
            built={'method':method,'objects':objects,'fingerprint':identity(method)}
            state['methods'][cid]=method;state['built'][cid]=built
            if cid in state.get('quality',{}).get('specifications',{}):source_quality.bind_objects(state,cid,built)
        scene['revision']=revision
        scene_file=folder/'scene.json';write_json(scene_file,scene)
        candidate={'revision':revision,'scene':a._file(task,scene_file),'pptx':a._file(task,saved),
                   'snapshot':a.Library(state['project']).blob(saved),
                   'reason':{'kind':'complete_native_rebuild','source_hash':state['source']['sha256'],
                       'request':request.get('user_intent'),'baseline_hash':digest(pptx)},
                   'allowed':{},'baseline':None,'recipe_state':'snapshot_only'}
        state.update(revision=revision,selected=candidate,active_candidate=candidate,scene=candidate['scene'],
                     stage='host_render',packet=None)
        state['review_queue']=['whole']+source_quality.queue(state)+['scan-'+str(i) for i in range(6)]
        state['native_import']={'source_hash':state['source']['sha256'],'pptx_sha256':digest(pptx),
                                'native_count':len(names),'owner_map':copy.deepcopy(owners),'quality_inherited':False}
        a._event(task,'complete_native_working_baseline_imported',state['native_import'])
        a._save(task,state)
    return a.next_packet(task)


def reconcile(task,request):
    """Extend an imported working mirror after a traversal defect is located.

    No PPT write, no revision of historical Scene files, no acceptance or
    quality inheritance. Every newly discovered owner needs an original-plan
    binding. Current and selected mirrors are both rebuilt from exact bytes.
    """
    from . import execution_contract as ec,frame_plan
    from .native_snapshot import snapshot
    task,state=a._state(task);current=state.get('active_candidate') or state.get('selected')
    if not state.get('native_import') or not current or not current.get('render'):
        raise ValueError('Reconcile only an actual rendered complete-native working task')
    if (request.get('expected_pptx_sha256')!=current['pptx']['sha256'] or
            request.get('source_hash')!=state['source']['sha256'] or not request.get('source_evidence')):
        raise ValueError('Reconciliation requires the exact saved candidate, original and source binding evidence')
    owners={**state['native_import']['owner_map'],**request.get('additional_owner_map',{})}
    inv,old_current,_=ec.inventory(task,state,current)
    components={c['id'] for c in state['analysis']['components']}
    if set(owners)!=set(inv['native_names']) or not set(owners.values())<=components:
        raise ValueError('Every discovered active native owner needs one existing original-plan owner')
    missing=sorted(set(inv['native_names'])-{o['id'] for o in old_current['objects']})
    structural=[o['id'] for o in old_current['objects'] if o['id'] in inv['parents'] and o.get('parent')!=inv['parents'][o['id']]]
    compatibility=[o['id'] for o in old_current['objects'] if o['id'] in inv['compatibility_variants'] and
        o.get('content',{}).get('native_snapshot',{}).get('compatibility')!=inv['compatibility_variants'][o['id']]]
    source_hints=None
    if request.get('scene_hints_ref'):
        source_hints=read_json(ec.resource(task,request['scene_hints_ref']))
        if source_hints.get('source',{}).get('sha256')!=state['source']['sha256']:
            raise ValueError('Semantic hints must bind this unchanged original')
        if {o['id'] for o in source_hints['objects']}!=set(inv['native_names']):
            raise ValueError('Semantic hints must cover the exact saved native inventory')
    if not missing and not structural and not compatibility and source_hints is None:
        return {'status':'COMPLETE_NATIVE_MIRROR_CURRENT','added':[]}
    name_migration=None
    if request.get('resolve_identity_by_verified_names'):
        from .saved_components import inventory as saved_inventory
        prior_ref=state.get('external_reconciliation')
        if not prior_ref:raise ValueError('No unresolved external migration')
        prior_record=read_json(ec.resource(task,prior_ref))
        before=saved_inventory(ec.resource(task,prior_record['before']))
        after=saved_inventory(ec.resource(task,current['pptx']))
        def by_unique_name(value):
            rows={r['name']:r for r in value['objects']}
            if len(rows)!=len(value['objects']):raise ValueError('Ambiguous native names')
            ids={r['shape_id']:r['name'] for r in value['objects']}
            return rows,{n:ids.get(r['parent_id']) for n,r in rows.items()}
        left,left_parents=by_unique_name(before);right,right_parents=by_unique_name(after)
        if not set(left)<=set(right):raise ValueError('Deleted or renamed owner needs explicit binding')
        if any(left[n]['kind']!=right[n]['kind'] for n in left):
            raise ValueError('Native type changed; unique names cannot resolve representation')
        actual_added=sorted(set(right)-set(left))
        if any(n not in request.get('additional_owner_map',{}) for n in actual_added):
            raise ValueError('Every new native owner needs an original source owner binding')
        actual_reparented=[n for n in left if left_parents[n]!=right_parents[n]]
        name_migration=copy.deepcopy(prior_record)
        name_migration['prior_numeric_migration']=prior_ref
        name_migration['identity_resolution']={
            'mechanism':'unique_saved_native_names_and_actual_named_parents',
            'before_pptx_sha256':prior_record['before']['sha256'],
            'after_pptx_sha256':current['pptx']['sha256'],
            'old_owner_count':len(left),'new_owner_count':len(right),
            'source_bound_additions':{n:owners[n] for n in actual_added},
            'actual_reparented':actual_reparented,
            'numeric_id_changes':[n for n in left if left[n]['shape_id']!=right[n]['shape_id']],
            'quality_acceptance':False}
        name_migration['aliases']={};name_migration['ambiguous']=[]
        name_migration['added']=[];name_migration['reparented']=actual_reparented
        name_migration['changed']=sorted(set(actual_added)|{
            n for n in left if left[n]['xml_hash']!=right[n]['xml_hash'] or n in actual_reparented})
        name_migration['status']='binding_pending' if actual_reparented else 'intent_pending'
    with writer(task):
        folder=task/'source/native-reconciliation'/identity({'request':request,'implementation':ec._implementation()})
        folder.mkdir(parents=True,exist_ok=False);history=[]
        candidates=[('selected',state['selected'])]
        if state.get('active_candidate'):candidates.append(('active_candidate',state['active_candidate']))
        mirrors={}
        for kind,candidate in candidates:
            source=ec.resource(task,candidate['pptx']);before=digest(source)
            hints=source_hints or read_json(ec.resource(task,candidate['scene']));scene=snapshot(task,state,source,hints)
            scene['revision']=candidate['revision'];path=folder/(kind+'-scene.json');write_json(path,scene)
            history.append({'candidate':candidate['pptx'],'prior_scene':candidate['scene'],'current_scene':a._file(task,path)})
            candidate['scene']=a._file(task,path);mirrors[kind]=scene
            if digest(source)!=before:raise ValueError('Native reconciliation must never change saved PowerPoint bytes')
        selected=mirrors['selected'];active=mirrors.get('active_candidate',selected)
        state['scene']=(state.get('active_candidate') or state['selected'])['scene']
        for cid in components:
            built=copy.deepcopy(state['built'][cid]);built['objects']=[o for o in selected['objects'] if owners[o['id']]==cid]
            built['method']['objects']=copy.deepcopy(built['objects']);built['fingerprint']=identity(built['method'])
            state['built'][cid]=built;state['methods'][cid]=built['method'];source_quality.bind_objects(state,cid,built)
            if state.get('rule_pending_built') and any(owners[n]==cid for n in current.get('allowed',{})):
                pending=copy.deepcopy(built);pending['objects']=[o for o in active['objects'] if owners[o['id']]==cid]
                pending['method']['objects']=copy.deepcopy(pending['objects']);pending['fingerprint']=identity(pending['method'])
                state['rule_pending_built'][cid]=pending
        if state.get('frame_plan'):
            previous=state['frame_plan'];plan=copy.deepcopy(frame_plan.load(task,previous))
            additions=set(frame_plan.required(active))-set(plan['scope'])
            if additions:
                plan['scope']=sorted(set(plan['scope'])|additions)
                plan['coverage'] += [{'object':n,'mode':'inherited','mechanism':'source_part_quality',
                    'reason':'Complete native compatibility traversal; original quality binding is required independently of write scope.'} for n in sorted(additions)]
                plan['revision']+=1;plan['amendment']={'previous_sha256':previous['sha256'],'changed_frames':[],
                    'reason':'Extend logical owner coverage after a located native compatibility traversal omission; all previous frames and targets remain frozen.'}
                frame_plan.bind(task,state,{'frame_plan':plan},active)
        if name_migration is not None:
            # Exact names are unchanged; remove only proven erroneous aliases
            # introduced by the preserved numeric migration, not other history.
            for original,wrong in prior_record['aliases'].items():
                if state.get('native_aliases',{}).get(original)==wrong:
                    state['native_aliases'].pop(original)
            migration_path=folder/'verified-name-migration.json'
            write_json(migration_path,name_migration)
            state['external_reconciliation']=a._file(task,migration_path)
        state['native_import']['owner_map']=owners;state['native_import']['native_count']=len(owners)
        receipt={'status':'COMPLETE_NATIVE_MIRROR_RECONCILED','added':missing,'native_count':len(owners),
            'structural_parents_corrected':structural,'compatibility_records_corrected':compatibility,
            'source_evidence':request['source_evidence'],'history':history,'pptx_bytes_changed':False,'quality_acceptance':False}
        write_json(folder/'reconciliation.json',receipt)
        state.setdefault('native_reconciliation_history',[]).append(a._file(task,folder/'reconciliation.json'))
        state.pop('acceptance',None);state['packet']=None
        a._event(task,'complete_native_traversal_reconciled',receipt);a._save(task,state)
    return receipt
