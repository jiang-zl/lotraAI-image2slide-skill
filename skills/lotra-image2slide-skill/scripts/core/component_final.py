"""Deferred complete-page review and compact delivery for component tasks."""
import copy
from pathlib import Path
from .common import read_json,write_json,digest,identity,writer
from .component_protocol import ready_for_final

DIMENSIONS=('semantic_completeness','geometry','typography','relations','appearance','overall_clarity')


def observe(task,request):
    from . import agent_runtime as a,component_workflow as c
    task,state=a._state(task);contract,ledger=c._load(task,state);candidate=c._candidate(state)
    if not contract or not candidate: raise ValueError('Current source contract and candidate required')
    c.refresh(task,state,contract,ledger,candidate)
    readiness=ready_for_final(contract,ledger,state)
    if not readiness['ready']: return {'status':'FINAL_DEFERRED','readiness':readiness,'whole_audit_executed':False}
    from .component_fonts import current as font_review_current
    if not font_review_current(read_json(c._resource(task,candidate['scene'])),state,ledger):
        return {'status':'FINAL_FONT_REVIEW_REQUIRED','whole_audit_executed':False}
    evidence=request['evidence'];value=read_json(c._resource(task,evidence))
    c.actual_render(task,state,candidate)
    for key,expected in (('source_hash',state['source']['sha256']),('pptx_hash',candidate['pptx']['sha256']),('preview_hash',candidate['preview']['sha256'])):
        if value.get(key)!=expected: raise ValueError('Whole visual observation is stale: '+key)
    if value.get('observer') not in ('host_model','human'): raise ValueError('Actual observer required')
    dimensions=value.get('dimensions',{})
    if set(dimensions)!=set(DIMENSIONS) or any(type(v.get('passed')) is not bool or not v.get('observations') for v in dimensions.values()):
        raise ValueError('Six located visual judgments required; scores do not substitute for observations')
    ledger['final_visual']=evidence;ledger['final_dirty']=True;ledger['final_result']=None
    failed=[key for key,value in dimensions.items() if not value['passed']]
    from .component_source_features import final_review
    feature_review = final_review(task,contract,value)
    if not feature_review['passed']: failed.append('source_feature_correspondence')
    from .spatial_frames import review as spatial_review
    spatial = spatial_review(contract,value)
    if not spatial['passed']: failed.append('spatial_visual_correspondence')
    from .line_review import validate as validate_line_review
    line_review=validate_line_review(task,state,candidate,contract,ledger,value)
    ledger['line_issues']=line_review.get('issues',ledger.get('line_issues',{}))
    if not line_review['passed']:failed.append('line_evidence')
    if failed and (failed!=['line_evidence'] or line_review.get('program_failure') or line_review.get('visual_failure')):
        from .component_revision import queue_final_repair
        queue_final_repair(ledger,failed,evidence)
    with writer(task): c._save_ledger(task,state,ledger,'final_visual_observed',{'evidence':evidence})
    return {'status':'FINAL_VISUAL_RECORDED','passed':not failed,'feature_review':feature_review,'line_review':line_review,'acceptance':False}


def _visual(task,state,candidate,ledger,line_report=None):
    from . import component_workflow as c
    evidence=ledger.get('final_visual')
    if not evidence:return {'passed':False,'reason':'FINAL_VISUAL_OBSERVATION_REQUIRED'}
    value=read_json(c._resource(task,evidence))
    binding=(value.get('source_hash')==state['source']['sha256'] and value.get('pptx_hash')==candidate['pptx']['sha256'] and
             value.get('preview_hash')==candidate.get('preview',{}).get('sha256'))
    dims=value.get('dimensions',{})
    good=(binding and value.get('observer') in ('host_model','human') and set(dims)==set(DIMENSIONS) and
          all(v.get('passed') is True and v.get('observations') for v in dims.values()))
    from .component_source_features import final_review
    contract,_ = c._load(task,state)
    feature_review = final_review(task,contract,value)
    good = good and feature_review['passed']
    from .spatial_frames import review as spatial_review
    spatial = spatial_review(contract,value)
    good = good and spatial['passed']
    from .line_review import validate as validate_line_review
    try:line_review=validate_line_review(task,state,candidate,contract,ledger,value,report=line_report)
    except ValueError as error:
        # Reading an old accepted review is a readiness question. Preserve its
        # bytes/issues and return the current review packet; submission itself
        # still rejects stale or changed evidence instead of accepting it.
        line_review={'passed':False,'reason':str(error),'review_required':True,
                     'issues':ledger.get('line_issues',{})}
    good=good and line_review['passed']
    return {'passed':bool(good),'binding_current':binding,'evidence':evidence,'dimensions':dims,
            'source_feature_review':feature_review,
            'spatial_review':spatial,
            'line_review':line_review,
            'basis':'Explicit host/human original/current visual judgments; no program semantic-confidence claim'}


def audit(task,state=None,candidate=None,persist=True):
    from . import agent_runtime as a,component_workflow as c
    if state is None:task,state=a._state(task)
    task=Path(task);candidate=candidate or c._candidate(state);contract,ledger=c._load(task,state)
    if not contract or not candidate:return {'status':'COMPONENT_CONTRACT_REQUIRED','whole_audit_executed':False}
    scene,_=c.refresh(task,state,contract,ledger,candidate);ready=ready_for_final(contract,ledger,state)
    if not ready['ready']:
        if persist:
            with writer(task):c._save_ledger(task,state,ledger,'final_deferred',ready)
        return {'status':'FINAL_DEFERRED','readiness':ready,'whole_audit_executed':False}
    from .component_fonts import current as font_review_current
    if not font_review_current(scene,state,ledger):return {'status':'FINAL_FONT_REVIEW_REQUIRED','whole_audit_executed':False}
    for row in contract['components']:c.component_row(task,state,contract,row['id'])
    before=c.implementation();source_sha=digest(c._resource(task,state['source']));pptx=c._resource(task,candidate['pptx'])
    from .native_core_checks import package_gate
    from .component_relations import evaluate,source_placement
    inventory=c._check_nonpaint(task,candidate,contract)
    package=package_gate(scene,pptx,task)
    from . import font_contract as fonts
    try:
        if fonts.missing(scene,state):raise ValueError('FONT_PREPARATION_REQUIRED: current original style/identity obligations are incomplete')
        fonts.compile_scene(scene)
        font_binding=fonts.guard_saved(scene,pptx)
        font_binding=dict(font_binding,passed=True)
    except ValueError as error:font_binding={'passed':False,'reason':str(error)}
    relations=evaluate(task,state,candidate,contract)
    receipt=c.actual_render(task,state,candidate,independent=True)
    from .line_verification import evaluate as evaluate_lines
    line_report=evaluate_lines(task,state,candidate,contract,render=True)
    visual=_visual(task,state,candidate,ledger,line_report=line_report)
    from .component_source_features import probes, source_check, enabled as features_enabled
    if features_enabled(contract):
        observation=read_json(c._resource(task,contract['source_observation']))
        feature_probes=probes(task,state,candidate,observation['features'])
        feature_basis={'passed':all(source_check(row)['passed'] for row in contract['components']),
            'source_observation':contract['source_observation'],'native_correspondence':identity(contract['feature_bindings'])}
    else:
        feature_probes={'passed':True,'applicable':False,'legacy_policy_retained':True}
        feature_basis={'passed':True,'applicable':False,'legacy_policy_retained':True}
    gates={'component_qualification':{'passed':ready['ready'],'components':len(ledger['components'])},
           'font_language_and_binding':font_binding,
           'ownership':inventory,'native_resources':{'passed':package['status']=='PASS','result':package},
           'assembly_and_layout':relations,'source_placement':source_placement(task,state,candidate,contract),
           'actual_render':{'passed':True,'backend':receipt['backend'],'receipt':candidate['render']},
           'source_feature_basis':feature_basis,'source_feature_probes':feature_probes,
           'final_visual':visual}
    from .line_contracts import enabled as evidence_enabled
    if evidence_enabled(state):gates['source_lines']=line_report
    from .capture_target import verify as verify_target
    if state.get('reconstruction_target'):
        try:gates['reconstruction_target']=verify_target(task,state)
        except ValueError as error:gates['reconstruction_target']={'passed':False,'reason':str(error)}
    from .source_preflight import enabled as source_review_enabled,require as source_review_gate
    if source_review_enabled(state):
        try:
            source_ref=source_review_gate(task,state,read_json(c._resource(task,contract['source_observation'])))
            gates['source_observation_support']={'passed':True,'evidence':source_ref,'independently_recomputed':True}
        except ValueError as error:
            gates['source_observation_support']={'passed':False,'reason':str(error)}
        from .text_appearance import evaluate as evaluate_text
        gates['whole_string_ink']=evaluate_text(task,state,candidate,observation['features'])
    if contract.get('workflow_version') in ('1.35.0', '1.35.1','1.35.2'):
        from .spatial_checks import evaluate as spatial_evaluate
        # Independent final gate recomputes from saved bytes, not local hits.
        gates['spatial_native'] = spatial_evaluate(task,state,candidate,contract)
    failures=[key for key,value in gates.items() if value.get('passed') is not True]
    exclusions=contract.get('scope',{}).get('excluded_checks',[])
    result={'schema':'component-final-1.32.0','status':'ACCEPTED' if not failures else 'WORK_REQUIRED',
        'source_hash':source_sha,'pptx_hash':candidate['pptx']['sha256'],'preview_hash':candidate['preview']['sha256'],
        'contract':state['component_workflow']['contract'],'implementation':before,
        'render_environment':state['capabilities']['fingerprint'],'font_review':ledger['font_review'],'gates':gates,'failures':failures,
        'excluded_checks':{key:'EXCLUDED_PER_USER_REQUEST' for key in exclusions},
        'office_behavior_executed':False,'whole_audit_executed':True,
        'component_results':copy.deepcopy(ledger['components']),
        'limits':'Parameter and native structure checks do not certify Office behavior. Visual semantics are explicit host/human observations.'}
    if before!=c.implementation() or digest(pptx)!=result['pptx_hash'] or digest(c._resource(task,state['source']))!=source_sha:
        raise ValueError('Inputs or implementation changed during final audit')
    file=task/'audits'/('component-final-'+identity(result)+'.json');write_json(file,result)
    ref=c._ref(task,file);state['quality_result']=ref;ledger['final_result']=ref;ledger['final_dirty']=bool(failures)
    if failures and not (failures==['final_visual'] and not visual.get('evidence')):
        if persist and any(value.get('valid') is False for value in gates.values()):
            c.failure_decision(task,state,contract,ledger,candidate,{key:gates[key] for key in failures})
            return result
        from .component_revision import queue_final_repair
        queue_final_repair(ledger,failures,ref)
    if persist:
        with writer(task):c._save_ledger(task,state,ledger,'final_audited',{'report':ref,'status':result['status']})
    return result


def accept(task,state,candidate,measured=None):
    from . import component_workflow as c
    contract,ledger=c._load(task,state)
    if not contract or not candidate: raise ValueError('Current component candidate required')
    c.refresh(task,state,contract,ledger,candidate)
    if not ready_for_final(contract,ledger,state)['ready'] or ledger['final_dirty'] or not ledger.get('final_result'):
        raise ValueError('Current components, layout and independent final audit required')
    stored=read_json(c._resource(task,ledger['final_result']))
    if measured is not None and measured!=stored: raise ValueError('Caller cannot replace the immutable final result')
    if (stored.get('status')!='ACCEPTED' or stored.get('render_environment')!=state['capabilities']['fingerprint'] or stored['implementation']!=c.implementation() or
        stored['pptx_hash']!=digest(c._resource(task,candidate['pptx'])) or
        stored['preview_hash']!=digest(c._resource(task,candidate['preview'])) or stored.get('failures') or
        not all(g.get('passed') is True for g in stored['gates'].values())):
        raise ValueError('Final result is incomplete or stale')
    acceptance={'schema':'component-acceptance-1.32.0','status':'ACCEPTED','source_hash':state['source']['sha256'],
                'pptx_hash':stored['pptx_hash'],'preview_hash':stored['preview_hash'],'implementation':stored['implementation'],
                'result':ledger['final_result'],'excluded_checks':stored['excluded_checks']}
    file=Path(task)/'audits'/('component-acceptance-'+identity(acceptance)+'.json');write_json(file,acceptance)
    state['acceptance']=c._ref(task,file)
    from .knowledge_flow import accepted
    accepted(task,state,contract,ledger,read_json(c._resource(task,candidate['scene'])),acceptance)
    return acceptance


def report(result,compact,render):
    lines=['# 重建结果报告','','状态：ACCEPTED。部件、组装与排版完成后执行最终整图验收。',
        '',f"原图 SHA-256：`{result['source_hash']}`",f"验收输入 PPTX SHA-256：`{result['pptx_hash']}`",
        f"交付 PPTX SHA-256：`{compact['output_sha256']}`",'',
        f"文件整理：{compact['before_bytes']} → {compact['after_bytes']} 字节；原生 XML 与完整字体保留。",
        f"实际显示验证：{render['status']}。该结论限于实际渲染与资源整理，不代表 Office 编辑行为测试。",'',
        '| 部件 | 路线与资格 | 实际指标及方向 |','|---|---|---|']
    for name,record in result['component_results'].items():
        current=record.get('current') or {};value=current.get('result',{})
        scores=[]
        for m in value.get('items',[]):
            if isinstance(m.get('value'),(int,float)):
                arrow={'lower':'↓','higher':'↑','exact':'='}.get(m.get('direction'),'')
                scores.append(f"{m['id']}{arrow} {m['value']:.5g}"+(f"（阈值 {m['threshold']}）" if m.get('threshold') is not None else ''))
        checks=value.get('native_parameters',{})
        if checks:scores.append('固定参数原生构造一致性 = '+str(sum(v['status']=='PASS' for v in checks.values()))+'/'+str(len(checks))+'；不适用像素追分')
        for key,check in current.get('program_checks',{}).items():scores.append(key+' = '+('PASS' if check['passed'] else 'FAIL'))
        if not scores:scores.append('资格由当前保存属性签名及所附原图/实际局部观察支持')
        lines.append('| '+name.replace('|','/')+' | '+value.get('route','assembly/instance/specialist')+'；QUALIFIED | '+'；'.join(scores)+' |')
    spatial=result['gates'].get('spatial_native')
    if spatial:
        lines.extend(['','| 空间关系 | 实测值 | 原图允许上限 | 结果 |','|---|---|---|---|'])
        for channel in ('anchors','footprints','relations'):
            for name,item in spatial.get(channel,{}).items():
                lines.append('| '+(channel+':'+name).replace('|','/')+' | '+str(item.get('value'))+' '+str(item.get('unit',''))+' | '+str(item.get('threshold'))+' | '+('PASS' if item['passed'] else 'FAIL')+' |')
        lines.extend(['','空间验收针对原图可观察的投影关系；未确定的隐藏三维几何不在已验证结论内。'])
    lines.extend(['','整图视觉判断：'])
    for key,value in result['gates']['final_visual'].get('dimensions',{}).items():
        lines.append('- '+key+'：'+('PASS' if value['passed'] else 'FAIL')+'；'+str(value['observations']))
    lines.extend(['','用户排除的检查（未执行，未计为通过）：'+', '.join(result['excluded_checks']),
        '部件详情、局部最佳、源图判断、渲染证据和事务记录保存在项目私有目录。',''])
    return '\n'.join(lines)


def export(task,output=None,*,output_root=None,new_export=False):
    from . import agent_runtime as a,component_workflow as c
    from .export_destination import reserve,publish
    task,state=a._state(task);candidate=c._candidate(state)
    plan=reserve(state['project'],candidate['pptx'],output_root=output_root,exact=output,new=new_export)
    if plan['status']=='PUBLISHED':
        from .workflow_guard import enabled
        if enabled(state):
            from .workflow_delivery import verify as verify_workflow_delivery
            verify_workflow_delivery(task,directory=plan['final'])
        return publish(plan,None)
    delivered=publish(plan,_export_into(task,plan['stage']))
    # Publishing changes the receipt's destination/hash after the inner audit.
    current=a._read_state(task/'state.json')
    current['official_delivery']=c._ref(task,Path(delivered['audit_receipt']))
    with writer(task):a._save(task,current)
    return delivered


def _export_into(task,output):
    from . import agent_runtime as a,component_workflow as c
    from .delivery_size import optimize_pptx
    from .transient_export import validate
    from .user_delivery import verify
    task,state=a._state(task);candidate=c._candidate(state);acceptance=accept(task,state,candidate)
    result=read_json(c._resource(task,acceptance['result']))
    output=Path(output).resolve()
    if output.exists():raise FileExistsError('Preserve the prior delivery; choose a new output directory')
    audit_dir=task/'exports'/('component-'+identity({'candidate':candidate['pptx'],'output':str(output)})[:20])
    audit_dir.mkdir(parents=True,exist_ok=False);output.mkdir(parents=True)
    original=c._resource(task,candidate['pptx']);delivery=output/'Final_editable.pptx'
    compact=optimize_pptx(original,delivery,profile='storage')
    rendered=validate(original,delivery,audit_dir/'actual-equivalence',state['capabilities'],base_render=c._resource(task,candidate['render']))
    from .presentation_backend import validate_delivery
    native=validate_delivery(delivery,audit_dir,state['capabilities'],destination=output)
    (output/'Report.md').write_text(report(result,compact,rendered)+'\nNative application validation: '+native['status']+' ('+native['backend']+').\n',encoding='utf-8')
    receipt={'kind':'compact-user-delivery-2','status':'ACCEPTED','output':str(output),
        'files':{p.name:digest(p) for p in output.iterdir() if p.is_file()},'input_pptx':str(original),
        'pptx':compact,'pdf_validation':rendered,'acceptance':acceptance,'native_validation':native,
        'storage_attempts':[{'profile':'storage','status':'ACTUALLY_VERIFIED','after_bytes':compact['after_bytes']}]}
    from .workflow_delivery import binding as workflow_binding
    receipt['task_binding']=workflow_binding(task,state,candidate,acceptance)
    file=audit_dir/'Receipt.json';write_json(file,receipt);verify(output,file)
    index=task.parents[1]/'delivery-receipts'/(identity(str(output))+'.json')
    write_json(index,{'receipt':str(file),'sha256':digest(file)})
    state['official_delivery']=c._ref(task,file);state.update(stage='delivered',packet=None)
    with writer(task):a._save(task,state)
    return {'status':'ACCEPTED','output':str(output),'pptx':str(delivery),'report':str(output/'Report.md'),
            'audit_receipt':str(file),'office_behavior_executed':native['status']=='PASS','whole_audit_executed':False}
