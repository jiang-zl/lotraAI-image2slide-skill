"""Measurement-derived repair phases inside the existing grant/journal flow."""
import copy
from .common import identity, write_json
from .component_fields import lookup
from .spatial_frames import PHASE


def failures(report):
    result = {}
    for channel, prefix in [('relations','spatial_relation:'), ('anchors','spatial_anchor:'), ('footprints','spatial_footprint:')]:
        for key, value in report.get(channel, {}).items():
            if not value['passed']:result[prefix+key] = value
    return result


def _retain_checks(task, report):
    from .component_workflow import _ref
    file=task/'component-workflow'/('Spatial-repair-checks-'+identity(report)+'.json')
    if not file.exists():write_json(file,report)
    return _ref(task,file)


def _targets(contract, report, row):
    units = set(row.get('spatial_context', {}).get('units', []))
    relations = {r['id']:r for r in contract['spatial']['relations']}
    points = {p['id']:p for p in contract['spatial']['landmarks']}
    footprints = {f['id']:f for f in contract['spatial']['footprints']}
    result = {}
    for failure, value in failures(report).items():
        prefix, key = failure.split(':',1)
        if prefix == 'spatial_relation':
            if not set(relations[key]['units']) & units:continue
            phase = PHASE[relations[key]['kind']]
        elif prefix == 'spatial_anchor':
            if points[key]['unit'] not in units:continue
            phase = min((PHASE[r['kind']] for r in relations.values() if key in r['landmarks']), default=1)
        else:
            if footprints[key]['unit'] not in units:continue
            phase = min((PHASE[r['kind']] for r in relations.values() if key in r.get('footprints', [])), default=2)
        result[failure] = phase
    return result


def guard_fields(contract, ledger, writes):
    """One authority for constructor, numeric, instance and rollback writes."""
    schedules = {name:r['spatial_repair_schedule'] for name,r in ledger['components'].items()
                 if r.get('spatial_repair_schedule')}
    if not schedules or not writes:return []
    if any(s.get('status')=='DECISION_REQUIRED' for s in schedules.values()):
        raise ValueError('Resolve the retained repair measurement/source decision before any native write')
    pending = [s for schedule in schedules.values() for s in schedule['stages'] if s['status']!='DONE']
    if not pending:raise ValueError('Close the current repair schedule before another native write')
    phase = min(s['phase'] for s in pending)
    rows = {owner:row['id'] for row in contract['components'] for owner in row['owners']}
    names = set()
    for item in writes:
        name = rows.get(item['owner']);record = ledger['components'].get(name,{})
        schedule = schedules.get(name,{})
        active = [s for s in schedule.get('stages',[]) if s['status']=='ACTIVE' and s['phase']==phase]
        if (schedule.get('status')=='DECISION_REQUIRED' or len(active)!=1 or not item['field'] or
                not any(g['owner']==item['owner'] and item['field'][:len(g['field'])]==g['field']
                        for g in record.get('repair_grant',[]))):
            raise ValueError('REPAIR_PHASE_AUTHORITY_REQUIRED: use the current active fields or submit a source decision and replan')
        names.add(name)
    return sorted(names)


def guard_scene(contract, ledger, before, after):
    from .component_fields import canonical_node, differences
    old = {n['id']:canonical_node(n) for n in before['objects']}
    new = {n['id']:canonical_node(n) for n in after['objects']}
    writes = [dict(p,owner=owner) for owner in set(old)|set(new)
              for p in differences(old.get(owner),new.get(owner),
                  before_exists=owner in old,after_exists=owner in new)]
    return guard_fields(contract,ledger,writes)


def _owner_phases(contract, targets, owner):
    points = {b['landmark']:b['owner'] for b in contract['spatial_bindings']}
    domains = {b['footprint']:set(b['owners']) for b in contract.get('spatial_footprint_bindings',[])}
    relations = {r['id']:r for r in contract['spatial']['relations']}
    coupled = {owner}
    for manifest in contract.get('construction_manifests',[]):
        parts = {p['owner'] for p in manifest['parts']}
        if owner in parts:coupled.update(parts)
    result = []
    for key, phase in targets.items():
        channel, name = key.split(':',1)
        if channel=='spatial_anchor':owners = {points[name]}
        elif channel=='spatial_footprint':owners = domains.get(name,set())
        else:
            relation=relations[name]
            owners={points[k] for k in relation['landmarks']}
            owners.update(o for k in relation.get('footprints',[]) for o in domains.get(k,set()))
        if owners & coupled:result.append(phase)
    return result


def _field_phase(grant, nodes, geometric_phase):
    path = grant['field']
    if not path or path in (['style'],):
        raise ValueError('Spatial phased repairs require explicit native fields, not whole-owner/style grants')
    if path[0] == 'z_order':return 4
    if path[0] == 'style':return 1 if path[1] == 'rotation' else 5
    if path[0] in ('parent','bbox'):return geometric_phase
    if path[0] == 'content':
        kind = nodes[grant['owner']]['render_type']
        return geometric_phase if kind in ('shape','path','bezier','connector','group') else 5
    raise ValueError('Classify this source/native field before phased repair')


def prepare_item(contract, report, row, item, candidate, scene):
    targets = _targets(contract,report,row)
    actual_relations = {k.split(':',1)[1] for k in targets if k.startswith('spatial_relation:')}
    if item.get('spatial_relations') is not None and set(item['spatial_relations']) != actual_relations:
        raise ValueError('Spatial repair relation IDs must equal the current measured failures for this component')
    if any(phase == 1 for phase in targets.values()):
        diagnosis = item.get('frame_pose_diagnosis')
        if diagnosis not in ('shared_frame','local_pose'):
            raise ValueError('Current pose failures require typed shared_frame/local_pose diagnosis')
        if diagnosis == 'shared_frame':
            raise ValueError('SPATIAL_SOURCE_DECISION_REQUIRED: revise the shared original frame, then rebind its consumers')
    nodes = {n['id']:n for n in scene['objects']}
    buckets = {}
    for grant in item['fields']:
        phases = [p for p in _owner_phases(contract,targets,grant['owner']) if p<=3]
        geometric_phase = min(phases,default=3)
        phase = _field_phase(grant,nodes,geometric_phase)
        if 'phase' in grant and grant['phase'] != phase:
            raise ValueError('Repair field phase conflicts with its measured dependency and native field type')
        buckets.setdefault(phase,[]).append(copy.deepcopy(grant))
    stages = []
    all_fields = [g for values in buckets.values() for g in values]
    from .component_revision import overlap
    for index, grant in enumerate(all_fields):
        if any(grant['owner']==other['owner'] and overlap(grant['field'],other['field']) for other in all_fields[index+1:]):
            raise ValueError('Repair schedule fields must be distinct and nonoverlapping')
    for phase, fields in sorted(buckets.items()):
        expected = [{'owner':g['owner'],'field':g['field'],'value':lookup(nodes[g['owner']],g['field'])} for g in fields]
        stages.append({'phase':phase,'fields':fields,'expected':expected,'status':'WAITING',
                       'targets':{k:v for k,v in targets.items() if v <= phase}})
    if targets and stages[0]['phase'] > min(targets.values()):
        raise ValueError('Earlier measured geometry/pose failures must be addressed before material/text changes')
    return {'source_hash':contract['source_hash'],'spatial_basis':contract['spatial_basis'],
            'planned_native':candidate['pptx'],'stages':stages,'measured_targets':targets,
            'failures':copy.deepcopy(item['failures'])}


def activate(ledger, candidate, scene, contract):
    if any(r.get('spatial_repair_schedule',{}).get('status')=='DECISION_REQUIRED' for r in ledger['components'].values()):
        return False
    pending = [(name, stage) for name, record in ledger['components'].items()
               for stage in record.get('spatial_repair_schedule',{}).get('stages',[]) if stage['status']!='DONE']
    if not pending:return False
    phase = min(stage['phase'] for _,stage in pending)
    nodes = {n['id']:n for n in scene['objects']}
    changed = False
    for name, stage in pending:
        if stage['phase'] != phase or stage['status'] != 'WAITING':continue
        record = ledger['components'][name]; schedule = record['spatial_repair_schedule']
        if schedule.get('status')=='DECISION_REQUIRED':continue
        if schedule['source_hash'] != contract['source_hash'] or schedule['spatial_basis'] != contract['spatial_basis']:
            record['status']='SOURCE_DECISION_REQUIRED';schedule['status']='DECISION_REQUIRED'
            record['source_decision']={'reason':'Repair schedule source/space context changed; replan current failures'}
            changed=True;continue
        conflict = False
        for expected in stage['expected']:
            exists, value = lookup(nodes.get(expected['owner']),expected['field'])
            if [exists,value] != list(expected['value']):
                record['status']='USER_INTENT_REQUIRED';schedule['status']='DECISION_REQUIRED'
                record['source_decision']={'reason':'Deferred repair field changed after its plan','field':expected}
                changed=True;conflict=True;break
        if conflict:continue
        record['repair_phase'] = phase
        record['repair_grant'] = copy.deepcopy(stage['fields'])
        record['repair_base'] = candidate['pptx']['sha256']
        record['repair_context'] = {'row':identity(next(r for r in contract['components'] if r['id']==name)),
            'source':contract['source_hash'],'native':candidate.get('retained_pptx',candidate['pptx'])}
        record['status'] = 'REPAIR_REQUIRED';stage['status'] = 'ACTIVE';changed = True
    return changed


def saved(ledger, names, candidate):
    for name in names:
        for stage in ledger['components'][name].get('spatial_repair_schedule',{}).get('stages',[]):
            if stage['status']=='ACTIVE':
                stage['status']='SAVED';stage['saved_native']=copy.deepcopy(candidate['pptx'])


def advance(task,state,candidate,contract,ledger,scene):
    """Advance only after current saved geometry certifies the earlier phase."""
    schedules = {k:r['spatial_repair_schedule'] for k,r in ledger['components'].items() if r.get('spatial_repair_schedule')}
    if not schedules:return False
    changed = False;report = None
    for name, schedule in schedules.items():
        record = ledger['components'][name]
        if schedule.get('status')=='DECISION_REQUIRED':continue
        for stage in schedule['stages']:
            if stage['status'] != 'SAVED':continue
            if stage['phase']==5:
                if record['status']!='QUALIFIED':continue
            else:
                if report is None:
                    from .spatial_checks import evaluate
                    report=evaluate(task,state,candidate,contract)
                if not report['valid']:
                    changed = changed or record['status']!='MEASUREMENT_DIAGNOSIS_REQUIRED'
                    changed = changed or schedule.get('status')!='DECISION_REQUIRED'
                    schedule['status']='DECISION_REQUIRED'
                    record['status']='MEASUREMENT_DIAGNOSIS_REQUIRED'
                    record['source_decision']={'reason':'Diagnose the current saved spatial measurement before repair',
                        'checks':_retain_checks(task,report),'source_hash':state['source']['sha256'],'pptx_hash':candidate['pptx']['sha256']}
                    continue
                current = failures(report)
                # A repaired phase cannot leave a new earlier-phase failure in
                # its unit scope while progressing to a later paint phase.
                row = next(r for r in contract['components'] if r['id']==name)
                unresolved = {k:v for k,v in _targets(contract,report,row).items() if v<=stage['phase']}
                if unresolved or any(k in current for k in stage['targets']):
                    changed = changed or record['status']!='SPATIAL_RELATIONS_UNMET'
                    changed = changed or schedule.get('status')!='DECISION_REQUIRED'
                    schedule['status']='DECISION_REQUIRED'
                    record['status']='SPATIAL_RELATIONS_UNMET'
                    record['source_decision']={'reason':'Saved repair phase failed; revise the located source/native decision and replan',
                        'checks':_retain_checks(task,report),'unresolved':unresolved,'source_hash':state['source']['sha256'],
                        'pptx_hash':candidate['pptx']['sha256']}
                    continue
            stage['status']='DONE';changed=True
            if any(s['status']=='WAITING' for s in schedule['stages']):record['status']='SPATIAL_REPAIR_WAITING'
        if all(s['status']=='DONE' for s in schedule['stages']):
            record['spatial_repair_completed']=copy.deepcopy(schedule)
            record.pop('spatial_repair_schedule',None)
            if record['status']=='SPATIAL_REPAIR_WAITING':record['status']='RECHECK_REQUIRED'
    pending = [s for record in ledger['components'].values()
               for s in record.get('spatial_repair_schedule',{}).get('stages',[]) if s['status']!='DONE']
    if any(r.get('spatial_repair_schedule',{}).get('status')=='DECISION_REQUIRED' for r in ledger['components'].values()):
        return changed
    if pending and any(s['status']=='WAITING' for s in pending):
        phase=min(s['phase'] for s in pending)
        if report is None:
            from .spatial_checks import evaluate
            report=evaluate(task,state,candidate,contract)
        blocked=False
        for row in contract['components']:
            record=ledger['components'][row['id']]
            if not record.get('spatial_repair_schedule'):continue
            earlier={k:v for k,v in _targets(contract,report,row).items() if v<phase}
            if not report['valid'] or earlier:
                record['status']='MEASUREMENT_DIAGNOSIS_REQUIRED' if not report['valid'] else 'SOURCE_DECISION_REQUIRED'
                record['spatial_repair_schedule']['status']='DECISION_REQUIRED'
                record['source_decision']={'reason':'Earlier measured obligations must pass before the next grant; replan missing repair phases',
                    'earlier_failures':earlier,'checks':_retain_checks(task,report),'source_hash':state['source']['sha256'],
                    'pptx_hash':candidate['pptx']['sha256']}
                blocked=True;changed=True
        if blocked:return changed
    return activate(ledger,candidate,scene,contract) or changed
