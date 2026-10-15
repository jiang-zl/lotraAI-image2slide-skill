"""The sole action generator used by next and advance."""
from .constructor_registry import work_units


DECISIONS = {'MODEL_OR_SOURCE_DECISION_REQUIRED','SEARCH_BOUND_REACHED','MODEL_RESELECT_REQUIRED',
             'SOURCE_DECISION_REQUIRED','MEASUREMENT_DIAGNOSIS_REQUIRED'}


def available(contract,ledger,candidate):
    order={name:index for index,name in enumerate(contract['policy']['stage_order'])}
    rows={r['id']:r for r in contract['components']}; actions=[]
    repairs=sorted(key for key,record in ledger['components'].items()
        if record['status'] in ('REPAIR_REQUIRED','SOURCE_DECISION_APPLY_REQUIRED') and record.get('repair_grant'))
    structural=ledger.get('structural_grant') or {}
    applying=[key for key in repairs if key in structural.get('components',[])
              and ledger['components'][key]['status']=='SOURCE_DECISION_APPLY_REQUIRED']
    if applying:repairs=applying
    for row in rows.values():
        record=ledger['components'][row['id']]; status=record['status']; route=row['route']
        if status=='QUALIFIED': continue
        children=[r['id'] for r in rows.values() if r.get('parent')==row['id']]
        repairing=row['id'] in repairs
        # Finish the retained source-apply scope before offering a different repair batch.
        if status in ('REPAIR_REQUIRED','SOURCE_DECISION_APPLY_REQUIRED') and not repairing:continue
        if repairing and row['id']!=repairs[0]:continue
        if not repairing:
            if route=='assembly' and any(ledger['components'][key]['status']!='QUALIFIED' for key in children): continue
            if row.get('mother') and ledger['components'][row['mother']]['status']!='QUALIFIED': continue
        stage='assembly' if route=='assembly' else 'instance' if route=='instance' else 'fit'
        operation='qualify'; automatic=False; write_set=[]
        if status in ('REPAIR_REQUIRED','SOURCE_DECISION_APPLY_REQUIRED'):
            operation='edit';stage='structure'
            write_set=[g for key in repairs for g in ledger['components'][key].get('repair_grant',[])]
        elif status=='USER_INTENT_REQUIRED':
            operation='source_or_measurement_decision';stage='source'
        elif status in ('MEASUREMENT_INVALID','MEASUREMENT_REQUIRED','MEASUREMENT_DIAGNOSIS_REQUIRED'):
            stage='measurement'; operation='source_or_measurement_decision'
        elif status in DECISIONS:
            stage='source'; operation='source_or_measurement_decision'
        elif status=='HARD_CONSTRAINT_FAILED':
            stage='structure'; operation='source_or_measurement_decision'
        elif row.get('model',{}).get('source_adapter') and not record.get('source_proposal') and route=='local_fit':
            stage='source'; operation='source_prepare'; automatic=bool(row['model'].get('source_request'))
        elif route=='fixed_parameters' or route=='local_fit' and status in ('PENDING','RECHECK_REQUIRED','ACTUAL_NATIVE_CONFIRMATION_REQUIRED'):
            operation='evaluate'; automatic=route=='fixed_parameters' or bool(candidate.get('preview'))
        elif route=='local_fit' and status=='NUMERIC_READY':
            operation='commit';automatic=True
            write_set=[{'owner':v['owner'],'field':v['field']} for k,v in row['fit']['bindings'].items() if row['parameters'][k]['state']=='tunable']
        elif route=='local_fit' and status=='LOCAL_TARGETS_UNMET':
            operation='source_or_measurement_decision' if row.get('curve_spec_hash') else 'fit'
            automatic=not row.get('curve_spec_hash') and row.get('fit',{}).get('adapter')=='native_geometry' and bool(candidate.get('preview'))
            for name,binding in row.get('fit',{}).get('bindings',{}).items():
                if row['parameters'][name]['state']=='tunable':
                    write_set.append({'owner':binding['owner'],'field':binding['field']})
        elif route=='instance' and status in ('PENDING','RECHECK_REQUIRED'):
            operation='instantiate'; automatic=True
            write_set=[{'owner':owner,'field':[]} for owner in row['owners']]
        reuse=sum(part.get('mother')==row['id'] for part in rows.values())
        dependency_unknown=bool(row.get('unresolved_dependencies'))
        locked_fields=([lock for key in repairs for lock in ledger['components'][key].get('user_locks',[])]
                       if repairing else record.get('user_locks',[]))
        from .component_revision import overlap
        conflict=any(item['owner']==lock['owner'] and overlap(item['field'],lock['field'])
                     for item in write_set for lock in locked_fields)
        if dependency_unknown or conflict:
            operation='source_or_measurement_decision'; automatic=False; stage='source'; write_set=[]
        probe=record.get('immediate_probe')
        # Probe only has authority for this exact component signature.
        reduction=(probe.get('violation_reduction') if probe and probe.get('signature') is not None and
                   probe.get('signature')==record.get('observed_measurement_signature') and
                   probe.get('context')==record.get('probe_context') else None)
        actions.append({'id':row['id'],'operator':operation,'operation':operation,
            'stage_index':order[stage],'stage':stage,'critical':int(row.get('critical',False)),
            'legal':True,'risk_tier':2 if reuse else 1 if row.get('required_relations') or route=='instance' else 0,
            'reuse_count':reuse,'source_distance':0 if row.get('source_facts') else 1,
            'static_work_units':work_units(row,operation),'immediate_violation_reduction':reduction,
            'read_set':row.get('dependency_refs',[]),'write_set':write_set,'executable':automatic,
            'component':row,'status':status,'repair_components':repairs if repairing and operation=='edit' else [],
            'decided_scene':structural.get('scene') if repairing and applying else None,
            'rebuild_owners':structural.get('rebuild_owners',[]) if repairing and applying else [],
            'decision_reason':'dependency_or_user_lock' if dependency_unknown or conflict else None})
    return actions

