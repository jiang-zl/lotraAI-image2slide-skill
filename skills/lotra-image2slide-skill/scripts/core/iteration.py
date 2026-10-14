"""Candidate journals with noncompensating measured comparisons and evidence.

Provisional working best, local best, context best and accepted feasible output
are deliberately distinct. Legacy foreground IoU cannot promote a candidate.
"""
from pathlib import Path
import shutil
import math
from .common import digest,identity,read_json,write_json,writer
from .typed_metrics import dominance


def visual_working_selection(has_previous, issues, outcome, improvement_note):
    """Working progress can retain unresolved source defects; new damage cannot.

    Full delivery is decided later by the visual loop's result exit. This does
    not award complete legacy quality/Office acceptance to an intermediate.
    """
    if outcome == 'harmful':
        return {'keep': False, 'reason': 'Observed harmful result', 'improvement_credit': 0}
    if not has_previous:
        return {'keep': True, 'reason': 'Initial observed working baseline', 'improvement_credit': 0}
    introduced = [i['id'] for i in issues if i.get('introduced') and i['status'] == 'open'
                  and (i['kind'] != 'polish' or i['severity'] != 'minor')]
    if introduced or outcome != 'helped' or not improvement_note:
        return {'keep': False, 'reason': 'No supported improvement or new substantive damage',
                'introduced': introduced, 'improvement_credit': 0}
    return {'keep': True, 'reason': improvement_note, 'improvement_credit': 1,
            'scope': 'working candidate only; residual defects remain active'}


def pareto_front(candidates, directions):
    """Return all non-dominated candidate ids under one frozen objective vector.

    Equal vectors retain the earlier candidate. Missing or non-finite values
    never enter a front and cannot cause a smaller weight denominator.
    """
    if not directions or any(d not in ('min', 'max') for d in directions.values()):
        raise ValueError('A fixed min/max objective vector is required')
    checked=[]
    for candidate_id, vector in candidates:
        if any(type(vector.get(k)) not in (int,float) or not math.isfinite(vector[k]) for k in directions):
            raise ValueError('Pareto candidate has missing or non-finite metrics')
        checked.append((candidate_id,vector))
    front=[]
    for index,(candidate_id,vector) in enumerate(checked):
        dominated=False
        for other_index,(other_id,other) in enumerate(checked):
            if index==other_index:continue
            at_least_as_good=all((other[k]<=vector[k] if direction=='min' else other[k]>=vector[k])
                                 for k,direction in directions.items())
            strictly_better=any((other[k]<vector[k] if direction=='min' else other[k]>vector[k])
                                for k,direction in directions.items())
            equal_earlier=other_index<index and all(other[k]==vector[k] for k in directions)
            if at_least_as_good and (strictly_better or equal_earlier):
                dominated=True;break
        if not dominated:front.append(candidate_id)
    return front


def blocking_rules(hierarchy, object_id, limit=16):
    """Return a bounded repair queue from actual hard checks, including children."""
    objects=hierarchy.get('objects',{})
    pending=[object_id];seen=set();blocked=[]
    while pending:
        current=pending.pop(0)
        if current in seen or current not in objects:continue
        seen.add(current)
        record=objects[current]
        for check in record.get('checks',[]):
            if (check.get('status')!='PASS' and check.get('required',True)
                    and check.get('check')!='landmarks'):
                blocked.append({'object_id':current,'check':check.get('check'),
                                'status':check.get('status')})
        pending.extend(record.get('children',[]))
    return {'total':len(blocked),'items':blocked[:limit],
            'truncated':len(blocked)>limit}


def register(scene,base,object_id,pptx,preview,measurement_file,hierarchy_file,registry,*,directions,native_file=None,native_plan=None,native_directory=None,quality_file=None,score_profile_file=None,plan_conformance_file=None):
    from .inspect import check
    base,registry=Path(base),Path(registry);m=read_json(measurement_file);h=read_json(hierarchy_file)
    ph=digest(pptx)
    if m.get('pptx_hash')!=ph or m.get('preview_hash')!=digest(preview) or h.get('pptx_hash')!=ph or h.get('scene_hash')!=identity(scene):raise ValueError('Stale candidate evidence')
    if m['source_hash']!=scene['source']['sha256'] or h['source_hash']!=scene['source']['sha256']:raise ValueError('Candidate reference mismatch')
    if object_id not in m['targets'] or object_id not in h['objects']:raise ValueError('Candidate lacks required object/parent evidence')
    if not directions:raise ValueError('Empty candidate objective vector')
    structure=check(scene,base,pptx);native=read_json(native_file) if native_file else None
    if native and native.get('source_pptx_hash')!=ph:raise ValueError('Native operations are for another candidate')
    verified_native=None
    if native is not None and native_plan is not None and native_directory is not None:
        import tempfile
        from .native_task import verify
        with tempfile.TemporaryDirectory(prefix='sci-native-journal-') as temp:
            verified_native=verify(native_plan,native_directory,Path(temp)/'check.json')
        if verified_native!=native:raise ValueError('Native report differs from actual saved-operation verification')
    target=h['objects'][object_id];vector=m['targets'][object_id]['vector']
    missing=[k for k in directions if vector.get(k) is None]
    conformance=read_json(plan_conformance_file) if plan_conformance_file else None
    if conformance and (conformance.get('scene_hash')!=identity(scene) or conformance.get('pptx_hash')!=ph):
        raise ValueError('Plan conformance belongs to another saved candidate')
    quality=read_json(quality_file) if quality_file else None
    if quality and (quality.get('binding',{}).get('pptx_hash')!=ph or
                    quality.get('binding',{}).get('scene_hash')!=identity(scene)):
        raise ValueError('Stale complete-quality receipt')
    if scene.get('analysis') and quality:
        from .qa import verify_visual_closure
        visual_closure=verify_visual_closure(quality,base,scene,pptx,preview)
    else:
        visual_closure='UNVERIFIED' if scene.get('analysis') else 'LEGACY_NOT_ACCEPTABLE'
    score_profile=read_json(score_profile_file) if score_profile_file else None
    if score_profile and (score_profile.get('source_hash')!=scene['source']['sha256']
                          or score_profile.get('scope_id')!=object_id
                          or not set(score_profile.get('metrics',{}))<=set(directions)):
        raise ValueError('Score profile is not bound to this source and semantic target')
    record={'object_id':object_id,'scene_hash':identity(scene),'scene_revision':scene['revision'],'source_hash':scene['source']['sha256'],
            'pptx_hash':ph,'preview_hash':digest(preview),'plan_hash':m['plan_hash'],'directions':directions,
            'vector':vector,'missing_metrics':missing,'structure_status':structure['status'],'local_hard_status':target['hard_status'],
            'context_hard_status':h['hard_status'],'native_status':verified_native.get('status') if verified_native else 'UNVERIFIED',
            'measurement_hash':digest(measurement_file),'hierarchy_hash':digest(hierarchy_file),
            'score_profile_hash':digest(score_profile_file) if score_profile_file else None,
            'plan_conformance_hash':digest(plan_conformance_file) if plan_conformance_file else None,
            'plan_conformance_status':conformance['status'] if conformance else 'UNVERIFIED',
            'visual_closure_status':visual_closure,
            'visual_closure_gate_version':'visual-closure-1',
            'status':'UNVERIFIED'}
    id=identity(record)[:24]
    with writer(registry):
        index=read_json(registry/'index.json') if (registry/'index.json').exists() else {'objects':{},'best_working_scene':None,'best_feasible':None}
        item=index['objects'].setdefault(object_id,{'current':None,'local_best':None,'context_best':None,'pareto_front':[],'history':[]})
        folder=registry/id
        if not folder.exists():
            folder.mkdir()
            for src,name in [(pptx,'Candidate.pptx'),(preview,'preview.png'),(measurement_file,'measurements.json'),(hierarchy_file,'hierarchy.json')]:shutil.copyfile(src,folder/name)
            write_json(folder/'scene.json',scene)
        item['current']=id
        if id not in item['history']:item['history'].append(id)
        admissible=(structure['status']=='PASS' and target['hard_status']=='PASS' and
                    not missing and visual_closure=='PASS')
        prior=read_json(registry/item['local_best']/'candidate.json') if item['local_best'] else None
        if prior and (prior.get('visual_closure_status')!='PASS' or
                      prior.get('visual_closure_gate_version')!='visual-closure-1'):
            old_best=item['local_best']
            item['local_best']=None;item['context_best']=None;prior=None
            if index['best_working_scene']==old_best:index['best_working_scene']=None
            if index['best_feasible']==old_best:index['best_feasible']=None
        if not admissible:
            record['selection']={'result':'rejected' if (structure['status']=='FAIL' or
                                  target['hard_status']=='FAIL' or visual_closure=='FAIL') else 'unmeasured',
                                 'reason':'No candidate reward until source-to-output omissions are closed'
                                          if visual_closure!='PASS' else 'Hard or measurement gate incomplete'}
        elif prior is None:
            item['local_best']=id;record['selection']={'result':'initial_measured_baseline'}
        elif prior['plan_hash']!=record['plan_hash'] or prior['directions']!=directions:
            record['selection']={'result':'unmeasured','reason':'Evaluation changed: re-evaluate all comparison candidates; old best not silently replaced'}
        else:
            comparison=dominance(prior['vector'],vector,directions);record['selection']=comparison
            if score_profile:
                from .score_profiles import evaluate
                metric_names=set(score_profile['metrics'])
                batch={'schema_version':'score-batch-1','profile_hash':identity(score_profile),
                       'source_hash':scene['source']['sha256'],'scope_id':object_id,
                       'baseline':{'id':item['local_best'],
                                   'vector':{name:prior['vector'].get(name) for name in metric_names}},
                       'candidates':[{'id':id,'vector':{name:vector.get(name) for name in metric_names}}]}
                scored=evaluate(score_profile,batch)
                record['selection']['score_comparison']=scored
                record['selection']['score_profile_hash']=identity(score_profile)
                if scored['selected_score_candidate_id']==id:
                    item['local_best']=id
                    record['selection']['result']='helped_by_frozen_profile'
                else:
                    record['selection']['result']='not_selected_by_frozen_profile'
            elif comparison['result']=='helped':
                item['local_best']=id
        same_evaluation = admissible and (item['local_best']==id or (
            item['local_best'] is not None and
            record['plan_hash']==read_json(registry/item['local_best']/'candidate.json')['plan_hash']))
        if same_evaluation:
            eligible=[]
            for candidate_id in item['history']:
                candidate=record if candidate_id==id else read_json(registry/candidate_id/'candidate.json')
                if (candidate['plan_hash']==record['plan_hash'] and candidate['directions']==directions
                        and candidate['structure_status']=='PASS' and candidate['local_hard_status']=='PASS'
                        and candidate.get('visual_closure_status','UNVERIFIED')=='PASS'
                        and not candidate['missing_metrics']):
                    eligible.append((candidate_id,candidate['vector']))
            item['pareto_front']=pareto_front(eligible,directions)
            record['selection']['pareto_member']=id in item['pareto_front']
        context_ok=(admissible and h['hard_status']=='PASS' and verified_native is not None
                    and verified_native.get('status')=='PASS'
                    and (not scene.get('analysis') or conformance is not None and conformance.get('status')=='PASS'))
        if context_ok and item['local_best']==id:
            item['context_best']=id;index['best_working_scene']=id
        if quality is not None:
            q=quality
            from .common import safe_path
            from .qa import gate
            profile=read_json(safe_path(base,scene['profile']['path']))
            if (scene.get('analysis') and context_ok and q.get('status')=='ACCEPTED' and
                    gate(profile,q.get('channels',{}),q.get('binding',{}).get('profile_hash')==scene['profile']['sha256'])=='ACCEPTED'):
                index['best_feasible']=id
        record['selection']['gate_credit']=1 if admissible else 0
        record['selection']['improvement_credit']=1 if (admissible and prior is not None and
                                                         item['local_best']==id) else 0
        record['selection']['blocking_rules']=blocking_rules(h,object_id)
        write_json(folder/'candidate.json',record);write_json(registry/'index.json',index)
    return record|{'candidate_id':id,'local_best':item['local_best'],'context_best':item['context_best'],'best_feasible':index['best_feasible']}
