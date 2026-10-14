"""Whole-result supervisor in the existing runtime, with typed honest evidence."""
import copy,shutil
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
from .common import digest,identity,read_json,write_json,safe_path,writer
from . import quality_intent as qi,quality_observations as qo

VERSION='whole-quality-loop-2'

def _candidate(state):
    candidate=state.get('active_candidate') or state.get('selected')
    if not candidate or not candidate.get('render'):raise ValueError('Whole quality checks need a complete actual saved render')
    return candidate

def _font_assets(file):
    import hashlib
    from .resource_facts import package_read
    with package_read(file) as z:
        return {n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()
            if n.startswith('ppt/fonts/') or n in ('ppt/_rels/presentation.xml.rels',)}

def _saved_font_references(file):
    from lxml import etree as E
    from .inspect import xml,inventory
    from .mathml import NS
    nodes,duplicates=inventory(xml(file));result={}
    if duplicates:raise ValueError('Ambiguous actual font owner')
    for name,row in nodes.items():
        if row['node'].tag.endswith('grpSp'):continue
        if row['node'].find('.//a:t',NS) is None and row['node'].find('.//m:t',NS) is None:continue
        families={k:sorted({n.get('typeface') for n in row['node'].findall('.//a:'+k,NS) if n.get('typeface')}) for k in ('latin','ea','cs')}
        if not any(families.values()):raise ValueError('Actual text has no explicit saved family reference: '+name)
        result[name]=families
    return result

def _specifications(task,state):
    from .source_contract import reconcile
    return reconcile(state,task)

def audit(task,state=None,candidate=None,persist=True):
    from .execution_context import session
    with session(task):
        return _audit(task,state,candidate,persist)

def _audit(task,state=None,candidate=None,persist=True):
    from . import agent_runtime as a,execution_contract as ec,source_quality as sq
    from .appearance_metrics import measure,native_signatures
    from .source_reading import report as content_report
    from .frame_plan import guard as frame_guard
    from .semantic_composition import report as composition_report
    from .relative_layout import report as layout_report
    from .font_contract import guard_saved as font_guard
    if state is None:task,state=a._state(task)
    from .task_completion import initialize as initialize_completion
    if not state.get('task_completion'):initialize_completion(state)
    candidate=candidate or _candidate(state);plan=qi.validate(task,state,candidate)
    # Close the selected native bodies as one phase before their per-owner
    # adapters run. This does not rerender or enroll any icon descendants.
    from .native_core import contract as core_contract,check as core_check
    if core_contract(task):core_check(task,state,candidate)
    implementation=ec._implementation();before_source=digest(ec.resource(task,state['source']));before_native=digest(ec.resource(task,candidate['pptx']))
    receipt=read_json(ec.resource(task,candidate['render']))
    if receipt.get('pptx_hash')!=before_native or receipt.get('preview_hash')!=digest(ec.resource(task,candidate['preview'])):
        raise ValueError('Actual renderer evidence is stale or refers to different native bytes')
    coverage=ec.report(task,state,candidate);inv,scene,native_nodes=ec.inventory(task,state,candidate)
    frames=frame_guard(task,state,candidate,report_only=True);composition=composition_report(task,state,candidate);layout=layout_report(task,state,candidate)
    content=content_report(task,state,candidate);specs=_specifications(task,state)
    metric_context={'native_inventory':coverage['passed'], 'content':content['items'],
        'layout_integrity':float(frames.get('passed',False) and all(r.get('status')=='minimum_met' for r in layout.get('relations',[]))),
        'relation_integrity':float(coverage['passed'] and composition.get('critical_pass') is True)}
    from .approved_render import source_correction_protection
    render_protection=source_correction_protection(task,state,candidate,plan.get('approved'))
    metric_context['approved_source_correction_protection']=render_protection
    from .rule_actions import reflect_rules
    reflect_rules(state,candidate,frames.get('items',[])+composition.get('items',[]))
    for attempt in state.get('source_text_attempts',[]):
        if attempt['candidate']==candidate['pptx']['sha256']:
            actual=next((r for r in content['items'] if r['unit']==attempt['unit']),None)
            attempt['reflection']={'actual_content':actual,'gain':bool(actual and actual['passed']),
                'status':'SOURCE_CONTENT_MET' if actual and actual['passed'] else 'SOURCE_CONTENT_REQUIRES_DIAGNOSIS'}
    for attempt in state.get('source_layout_attempts',[]):
        if attempt['candidate']==candidate['pptx']['sha256']:
            actual=[r for r in layout.get('relations',[]) if r['id'] in attempt['source_contracts']]
            matched=len(actual)==len(attempt['source_contracts']) and all(r['status']=='minimum_met' for r in actual)
            attempt['reflection']={'actual_relations':actual,'gain':matched,
                'status':'SOURCE_LAYOUT_MET' if matched else 'SOURCE_LAYOUT_REQUIRES_DIAGNOSIS'}
    host=qo.host_status(task,state,candidate,plan);appearance=[];legacy=[]
    for item in plan['items']:
        try:measured=measure(task,state,candidate,item,plan,metric_context)
        except (ValueError,KeyError,FileNotFoundError,TypeError) as error:measured={'passed':False,'status':'UNMEASURED','reason':str(error)}
        row={'id':item['id'],'purpose':item['purpose'],'quality_units':item['quality_units'],**measured};appearance.append(row)
        qo.record_program(state,'appearance',item['id'],row,qo.observation_basis(task,state,candidate,item))
    # All original numbers remain available, including unavailable old domains.
    # They do not masquerade as current appearance failures or disappear.
    for unit in state.get('quality',{}).get('units',{}).values():
        binding=next((r for r in plan['items'] if unit['id'] in r['quality_units']),None)
        current_unit=unit
        if binding and binding.get('binding_migration'):
            current_unit=copy.deepcopy(unit)
            # A historical flattened carrier now has one complete current
            # semantic group. Preserve old aliases and bounds as history while
            # actually measuring the current group instead of a missing name.
            groups=[n for n in binding['objects'] if n in inv['groups']]
            current_unit['objects']=groups if len(groups)==1 else binding['objects']
        try:
            measured=sq.evaluate(task,state,candidate,current_unit)
            if current_unit is not unit:measured['current_binding_migration']=binding['binding_migration']
        except (ValueError,KeyError,FileNotFoundError,TypeError) as error:
            measured={'unit':unit['id'],'status':'required_unmeasured','reason':str(error),'values':{}}
        legacy.append(measured)
        qo.record_program(state,'source_correspondence',unit['id'],measured,
                          identity({'source':state['source'],'unit':unit,'candidate':candidate['pptx'],'implementation':implementation}))
    native=native_signatures(str(ec.resource(task,candidate['pptx'])),before_native)
    native_rows=[]
    baseline_nodes={}
    if plan.get('approved'):
        from .boundary_geometry import saved_nodes
        baseline_nodes=saved_nodes(qi._ref(task,plan['approved']['pptx']),state['source_size'])
    for name in inv['native_names']:
        applicable=[r for r in plan['items'] if name in r['objects']];policies=[r['id'] for r in applicable]
        row={'object':name,'passed':bool(policies) and name in native,'policies':policies,
             'native_signature':native.get(name),'parent':inv['parents'].get(name)}
        from .native_connection_transaction import PREFIX as port_prefix,derived_receipt
        if name.startswith(port_prefix):
            row['derived_port']=derived_receipt(task,state,candidate,name,native_nodes)
            row['passed']&=row['derived_port']['passed']
        elif applicable:
            owner_policy=min(applicable,key=lambda r:len(r['objects']))
            # Independent actual-size measurements for every saved leaf,
            # including fine inferred parts with no resolvable source mask.
            # The frame is frozen to the immutable earlier native artifact;
            # it is never searched/re-aligned to improve candidate scores.
            if native_nodes[name]['tag']!='grpSp':
                try:
                    if not plan.get('approved'):
                        from .object_lifecycle import owner_item as first_owner_item
                        owner_item=first_owner_item(state,name,owner_policy)
                        frame=owner_item['roi'];row['frame_basis']='Independently frozen original painted-owner target'
                    elif name in baseline_nodes:frame=baseline_nodes[name]['frame']
                    else:
                        # New descendants have no historical paint frame.
                        # A source constructor must prove their exact native
                        # bytes first; use its frozen original unit window,
                        # rather than searching the candidate for a good crop.
                        proof=render_protection.get('constructor',{})
                        if not proof.get('passed') or name not in proof.get('objects',[]):
                            raise ValueError('New native owner lacks an exact original-derived constructor')
                        frame=owner_policy['roi']
                        row['frame_basis']='Frozen source policy ROI with exact native source-function replay'
                    if frame is None:raise ValueError('Actual non-group owner has no measurable saved extent')
                    x,y,w,h=frame
                    if plan.get('approved'):owner_item={**owner_policy,'objects':[name],'roi':[x-1,y-1,max(w,1)+2,max(h,1)+2]}
                    actual=measure(task,state,candidate,owner_item,plan,metric_context);row['appearance']=actual;row['passed']&=actual['passed']
                    if not plan.get('approved'):
                        own=state.get('native_owner_observations',{}).get(name,{})
                        row['own_source_semantics']=own.get('basis')==qo.observation_basis(task,state,candidate,owner_item) and own.get('outcome')=='matched'
                        row['passed']&=row['own_source_semantics']
                except (ValueError,KeyError,TypeError) as error:row.update(passed=False,measurement_error=str(error))
            else:
                row['appearance']={'status':'NOT_APPLICABLE','reason':'A native group has no own paint; its transform is protected by the item policy and every actual descendant is checked independently.'}
        native_rows.append(row);qo.record_program(state,'native_owner',name,row,identity(row))
    fonts={'passed':False,'status':'UNMEASURED'}
    try:
        approved=plan.get('approved');assets=_font_assets(ec.resource(task,candidate['pptx']))
        if state.get('native_import') and approved:
            references=_saved_font_references(ec.resource(task,candidate['pptx']))
            prior_references=_saved_font_references(qi._ref(task,approved['pptx']))
            serialization={'status':'ACTUAL_IMPORTED_FONT_REFERENCES_PRESERVED','owners':len(references),
                'passed':references==prior_references,'references':references,
                'scope':'Actual saved script-specific family references compared to immutable earlier native result; no invented source metadata or portable rebuild binding'}
        else:serialization=font_guard(scene,ec.resource(task,candidate['pptx']))
        preserved=bool(approved) and assets==_font_assets(qi._ref(task,approved['pptx']))
        preserved=preserved and serialization.get('passed',True)
        fonts={'passed':preserved,'status':'APPROVED_FONT_ASSETS_PRESERVED' if preserved else 'FONT_DELIVERY_PROOF_REQUIRED',
            'serialization':serialization,'resource_parts':assets,
            'scope':'Saved native font references and unchanged approved embedded assets, plus actual host render. No claim of independently decoded compressed EOT or universal receiver portability.'}
        if not approved and candidate.get('font_delivery',{}).get('embedding',{}).get('status') in ('EMBEDDED_FULL_EDITABLE_FONTS','NO_TEXT_FONTS'):
            fonts.update(passed=True,status='FULL_EDITABLE_FONT_DELIVERY_VERIFIED',delivery=candidate['font_delivery'])
    except (ValueError,KeyError,TypeError) as error:fonts['reason']=str(error)
    from .source_recursion import initialize as initialize_recursion,report as recursion_report
    from .signal_semantics import report as signal_report
    initialize_recursion(task,state)
    relation_units={u['id'] for u in state.get('quality',{}).get('units',{}).values() if u.get('profile')=='relation'}
    recursion=recursion_report(task,state,candidate,{'composition':composition,'layout':layout,
        'source_relations':{'items':[{'id':r['unit'],'status':r['status']} for r in legacy if r['unit'] in relation_units]}})
    signals=signal_report(task,state,candidate)
    from .source_feature_functions import report as original_feature_report
    from .connection_geometry import report as connection_report
    from .recursive_obligations import report as obligations_report,process_report
    features=original_feature_report(task,state,candidate)
    connections=connection_report(task,state,candidate)
    from .detail_contracts import report as detail_report
    details=detail_report(task,state,candidate)
    from .source_repeat import report as repeat_report
    repeats=repeat_report(task,state,candidate)
    from .neighbor_contracts import report as neighbor_report
    from .folded_paper import report as coherent_paper_report
    neighbors=neighbor_report(task,state,candidate)
    coherent_paper=coherent_paper_report(task,state,candidate)
    from .recursive_containment import report as containment_report
    from .office_math_contract import report as structured_math_report
    from .icon_clarity import report as clarity_report
    containment=containment_report(task,state,candidate)
    office_math=structured_math_report(task,state,candidate)
    clarity=clarity_report(task,state,candidate,{'appearance':appearance,'native':native_rows,'host':host,'features':features})
    obligations=obligations_report(task,state,candidate,{'containment':containment,'office_math':office_math,'clarity':clarity,'recursion':recursion,'native':native_rows,
        'legacy':legacy,'appearance':appearance,'host':host,'features':features,'connections':connections,'details':details,'neighbors':neighbors,'coherent_paper':coherent_paper})
    process=process_report(task,state,candidate,obligations)
    from .retained_typography import report as retained_typography_report
    typography=retained_typography_report(task,state,candidate)
    if not typography['applicable']:
        from .textbox_quality import source_packet,report as textbox_report,native_rows as text_owners
        missing=source_packet(task,state,candidate)
        diagnostics=None;passed=False;status='SOURCE_TEXTBOX_READING_REQUIRED'
        if not text_owners(ec.resource(task,candidate['pptx'])):
            passed=True;status='NO_SAVED_TEXTBOX_OR_FORMULA'
        elif missing is None:
            try:
                diagnostics=textbox_report(task,state,candidate)
                passed=diagnostics.get('status')=='minimum_met'
                status='SOURCE_TEXTBOX_TARGETS_MET' if passed else 'SOURCE_TEXTBOX_TARGETS_REQUIRE_REPAIR'
            except (ValueError,KeyError,TypeError,FileNotFoundError) as error:
                diagnostics={'status':'UNMEASURED','reason':str(error)}
                status='SOURCE_TEXTBOX_MEASUREMENT_REQUIRED'
        typography={'passed':passed,'status':status,'pending':missing,'source_glyph_diagnostics':diagnostics}
    gates={
        'recursive_containment':containment,
        'structured_office_math':office_math,
        'icon_clarity':clarity,
        'all_neighbor_closure':neighbors,
        'coherent_paper_geometry':coherent_paper,
        'original_repeat_families':repeats,
        'original_adaptive_detail':details,
        'source_recursion':recursion,
        'recursive_result_closure':obligations,
        'executable_process':process,
        'original_feature_geometry':features,
        'connection_geometry':connections,
        'signal_semantics':signals,
        'whole_inventory':{'passed':coverage['passed'] and all(r['passed'] for r in native_rows),'native_count':len(native_rows),
            'failed_rules':[i for i in coverage['items'] if not i['passed']]},
        'original_requirements':specs,
        'source_measurement_coverage':{'passed':all(r['status']!='required_unmeasured' and not any(c.get('status')=='required_unmeasured' for c in r.get('constraints',[])) for r in legacy),
            'measured_units':sum(r['status']!='required_unmeasured' and not any(c.get('status')=='required_unmeasured' for c in r.get('constraints',[])) for r in legacy),
            'required_units':len(legacy),'unmeasured':[r['unit'] for r in legacy if r['status']=='required_unmeasured' or any(c.get('status')=='required_unmeasured' for c in r.get('constraints',[]))]},
        'frame':{'passed':frames.get('passed',frames.get('status') in ('PASS','FRAME_PLAN_MET')),'result':frames},
        'composition':{'passed':composition.get('critical_pass') is True,'result':composition},
        'layout':{'passed':all(r.get('status')=='minimum_met' for r in layout.get('relations',[])),'result':layout},
        'text_math':{'passed':content['passed'],'result':content},
        'source_typography':typography,
        'original_content_predicates':{'passed':all(c.get('status') in ('minimum_met','stretch_met') for r in legacy for c in r.get('constraints',[]) if c['id'] in ('native_text_match','math_ast_match','native_cell_format_match')),
            'failed':[{'unit':r['unit'],'predicate':c} for r in legacy for c in r.get('constraints',[]) if c['id'] in ('native_text_match','math_ast_match','native_cell_format_match') and c.get('status') not in ('minimum_met','stretch_met')]},
        'source_semantics':{'passed':bool(host) and all(r['passed'] for r in host),'items':host},
        'appearance':{'passed':bool(appearance) and all(r['passed'] for r in appearance)
            and (not render_protection['applicable'] or render_protection['passed']),
            'items':appearance,'approved_source_correction_protection':render_protection},
        'fonts':fonts,
        'external_user_intent':{'passed':state.get('external_reconciliation',{}).get('status') not in ('pending','user_intent_pending')},
        'actual_render':{'passed':True,'backend':receipt.get('backend'),'pptx_hash':before_native,'preview_hash':candidate['preview']['sha256']}}
    from .native_core import contract as native_core_contract,check as native_core_check
    if native_core_contract(task):
        final_native=native_core_check(task,state,candidate,force=True)
        gates['appearance']['native_core_final']=final_native
        gates['appearance']['passed'] &= final_native['passed']
    from .object_lifecycle import report as object_report
    from .global_aesthetic import evaluate as global_report
    gates['object_convergence']=object_report(task,state,candidate,plan,native_rows,appearance,legacy,host,gates)
    gates['global_aesthetic']=global_report(task,state,candidate,gates)
    from .global_layout_actions import reflect as reflect_global_layout,obligations as global_obligations
    reflect_global_layout(state,candidate,gates['global_aesthetic'],gates['object_convergence'],task=task)
    ineffective=global_obligations(state)
    if ineffective:
        gates['global_aesthetic']['passed']=False;gates['global_aesthetic']['status']='INEFFECTIVE_GLOBAL_CHANGE_REQUIRES_ROLLBACK'
        gates['global_aesthetic']['transaction_debts']=[{'attempt':r['branch'],'candidate':r['candidate'],'status':r.get('reflection',{}).get('status','ACTUAL_REFLECTION_REQUIRED')} for r in ineffective]
    for key,result in gates.items():qo.record_program(state,'gate',key,result,identity({'candidate':candidate['pptx'],'policy':plan['compiled_hash'],'implementation':implementation}))
    failures=[{'goal':k,'result':v} for k,v in gates.items() if not v['passed']]
    ledger=state['quality_observations'];result={'schema':VERSION,'status':'ACCEPTED' if not failures else 'WORK_REQUIRED',
        'source_hash':before_source,'pptx_hash':before_native,'preview_hash':candidate['preview']['sha256'],
        'render_backend':receipt.get('backend'),'implementation':implementation,'policy_hash':plan['compiled_hash'],
        'basis':ec._basis(state,candidate),
        'gates':gates,'failures':failures,'appearance':appearance,'native_owners':native_rows,
        'legacy_source_measurements':legacy,'legacy_summary':dict(Counter(r['status'] for r in legacy)),
        'observations':{'program':len(ledger['program']),'host':len(ledger['host']),
            'current_host_confirmed':sum(r['passed'] for r in host),'required_host':len(host)},
        'content_summary':{'texts':content['text_count'],'formulas':content['formula_count'],
            'passed':sum(r['passed'] for r in content['items']),'failed':sum(not r['passed'] for r in content['items'])},
        'limits':'General programs require a correct source interpretation. Original pixel similarity is reported independently; active purpose-specific hard gates and observations control acceptance.'}
    if ec._implementation()!=implementation or digest(ec.resource(task,state['source']))!=before_source or digest(ec.resource(task,candidate['pptx']))!=before_native:
        raise ValueError('Quality audit changed input bytes or ran across a code change')
    path=task/'audits'/('whole-quality-'+identity(result)+'.json');write_json(path,result)
    state['quality_result']={'path':path.relative_to(task).as_posix(),'sha256':digest(path)}
    if persist:
        with writer(task):
            a._event(task,'whole_quality_loop_measured',{'status':result['status'],'native_count':len(native_rows),
                'source_units':len(legacy),'observations':result['observations'],'failed_goals':[r['goal'] for r in failures]})
            a._save(task,state)
    return result

def final_gate(task,state,candidate,measured=None):
    from . import execution_contract as ec
    contracts=_specifications(task,state)
    if not contracts['passed']:raise ValueError('Full source contract reconciliation failed: '+repr(contracts['errors'][:6]))
    from .global_layout_actions import obligations as global_obligations
    if global_obligations(state):raise ValueError('Final acceptance cannot erase an outstanding actual global transaction')
    result=measured or audit(task,state,candidate,persist=False)
    if not {'recursive_containment','structured_office_math','icon_clarity','all_neighbor_closure','coherent_paper_geometry'}<=set(result.get('gates',{})):
        raise ValueError('Final acceptance requires all-neighbor and complete assembly checks')
    current_plan=qi.validate(task,state,candidate)
    from .object_lifecycle import verify_current
    verify_current(task,state,candidate,current_plan)
    if read_json(ec.resource(task,state['quality_result']))!=result:raise ValueError('Whole acceptance needs its exact immutable program result, not caller-supplied pass fields')
    if result.get('basis')!=ec._basis(state,candidate) or result['implementation']!=ec._implementation() or result['pptx_hash']!=digest(ec.resource(task,candidate['pptx'])) or result['preview_hash']!=digest(ec.resource(task,candidate['preview'])):
        raise ValueError('Whole-result acceptance requires the exact current implementation, state, native artifact and actual render')
    if result.get('status')=='ACCEPTED':
        from .execution_context import session
        with session(task,independent=True):
            fresh=audit(task,state,candidate,persist=False)
        if fresh.get('status')!='ACCEPTED' or not all(g.get('passed') is True for g in fresh['gates'].values()) or fresh.get('failures'):
            raise ValueError('Current executable full recheck rejected claimed acceptance; no caller PASS or removed failure can close obligations')
    acceptance={'schema':VERSION,'status':'ACCEPTED' if result['status']=='ACCEPTED' else 'BLOCKED',
        'source_hash':result['source_hash'],'pptx_hash':result['pptx_hash'],'implementation':result['implementation'],
        'basis':ec._basis(state,candidate),'whole_result':state['quality_result'],'failures':result['failures'],
        'gates':{k:{'passed':v['passed']} for k,v in result['gates'].items()},'render_backend':result['render_backend']}
    path=task/'audits'/('acceptance-'+identity(acceptance)+'.json');write_json(path,acceptance)
    state['acceptance']={'path':path.relative_to(task).as_posix(),'sha256':digest(path)}
    if acceptance['status']!='ACCEPTED':raise ValueError('Whole quality loop requires work: '+','.join(r['goal'] for r in result['failures']))
    return acceptance

def run(task):
    from . import agent_runtime as a
    task,state=a._state(task);candidate=_candidate(state);result=audit(task,state,candidate)
    if result['status']=='ACCEPTED':
        from .task_completion import checkpoint
        checkpoint(task,state,candidate,result,{'action':'quality-loop export'})
        final_gate(task,state,candidate,result)
        with writer(task):
            state['selected']=copy.deepcopy(candidate);state['active_candidate']=None;state['stage']='accepted';state['packet']=None
            a._event(task,'purpose_specific_whole_result_accepted',{'pptx_hash':candidate['pptx']['sha256'],'policy':state['quality_intent']['compiled_hash']})
            a._save(task,state)
        return {'status':'ACCEPTED','report':state['quality_result'],'acceptance':state['acceptance'],'summary':result['content_summary']}
    next_work=next_action(task,state,candidate,measured=result)
    from .task_completion import checkpoint
    progress=checkpoint(task,state,candidate,result,next_work)
    with writer(task):a._save(task,state)
    return {'status':'WORK_REQUIRED','report':state['quality_result'],'failed_goals':[r['goal'] for r in result['failures']],
            'task_completion':progress,'next':next_work}

def _measured_work(task,state,candidate,measured):
    from .icon_clarity import discover as clarity_discovery
    if measured:
        clarity=measured['gates'].get('icon_clarity',{})
        if any(r.get('hd',{}).get('measurement_valid') is False for r in clarity.get('items',[])):
            from .icon_clarity import probe_review
            return {'status':'WORK_PACKET','packet':probe_review(task,state,candidate,clarity)}
        cm=measured['gates']['recursive_containment'];mm=measured['gates']['structured_office_math']
        if cm.get('capture_required'):return {'status':'WORK_PACKET','packet':{'kind':'required_actual_owner_capture','action':'containment-check capture','items':cm['capture_required'],'next':'Rerun complete current audit after capture'}}
        failed_math=[r['object'] for r in mm.get('items',[]) if not r['passed']]
        if failed_math:return {'status':'WORK_PACKET','packet':{'kind':'source_structured_math_repair','action':'office-math repair','objects':failed_math[:16],'remaining':len(failed_math),'write_set':{n:['text_body'] for n in failed_math[:16]},'baseline_hash':candidate['pptx']['sha256'],'check_set':'whole current source/native/result','protected_set':'all properties outside source-owned math paragraph content'}}
        if not mm.get('edit_behavior',{}).get('passed',False):return {'status':'WORK_PACKET','packet':{'kind':'actual_math_edit_behavior','action':'office-math edit-probe','required':mm.get('edit_behavior')}}
        if not cm['passed']:return {'status':'WORK_PACKET','packet':{'kind':'recursive_container_repair','action':'containment-check repair','items':[r for r in cm.get('items',[]) if not r['passed']],'instruction':'Authorize only identified source-owned position fields; programs compute the deepest rigid aggregate move, then recheck both axes at every level and all external relationships'}}
        clarity=measured['gates'].get('icon_clarity',{})
        if not clarity.get('passed') and clarity.get('next')=='icon-clarity discover':
            return {'status':'WORK_PACKET','packet':clarity_discovery(task,state,candidate)}
        if clarity.get('items') and not clarity.get('passed'):
            from .icon_detail import schedule as schedule_icon_detail,packet as icon_detail_packet
            schedule_icon_detail(state,candidate,clarity)
            detail=icon_detail_packet(task,state,candidate)
            if detail:return {'status':'WORK_PACKET','packet':detail}
            style_pending=[r['unit'] for r in clarity['items'] if r.get('unit') and r.get('hd',{}).get('passed') and
                           r.get('preservation',{}).get('numeric_pass') and not r['preservation'].get('review',{}).get('passed')]
            if style_pending:
                from .icon_preservation import review_packet
                return {'status':'WORK_PACKET','packet':review_packet(task,state,candidate,style_pending)}
            return {'status':'WORK_PACKET','packet':{'kind':'original_icon_clarity_reconstruction','items':[r for r in clarity['items'] if not r['passed']],
                'action_families':['icon-clarity enhance','icon-clarity review/observe','source-detail scan/next/observe','source-feature bind','source-structure-repair execute','recursive-check plan / execute','native-field proposal','actual_rerender'],
                'instruction':'Inspect unchanged parent/neighbor context; diagnostic enhancement is not source truth. Bind missing anatomy and complete native-part relations, choose a finite editable constructor, then check current vector-PDF edges at every scale, supported smooth materials, structure and every affected relationship. Pictures, ringing, stale evidence or sharpness alone cannot pass.'}}
    return None


def next_action(task,state,candidate,measured=None):
    if measured is None:
        from .workflow_control import current_report
        measured,_=current_report(task,state,candidate)
    from . import agent_runtime as recursion_agent
    from .recursive_containment import discovery as containment_discovery
    from .office_math_contract import discover as math_discovery
    from .icon_clarity import discover as clarity_discovery,eligible as clarity_eligible
    for missing,discover in ((not state.get('recursive_containment'),containment_discovery),
                             (not state.get('office_math_contract'),math_discovery),
                             (bool(clarity_eligible(state)) and not state.get('icon_clarity_contract'),clarity_discovery)):
        if missing:return {'status':'WORK_PACKET','packet':discover(task,state,candidate)}
    routed=_measured_work(task,state,candidate,measured)
    if routed:return routed
    from .source_recursion import packet as recursion_packet
    from .signal_semantics import packet as signal_packet
    regions=recursion_packet(task,state)
    if regions:
        work=recursion_agent._packet(task,state,'source_recursion','original_region_frontier',
            'Inspect and close every original child using executable leaf/partition conditions.',extra=regions)
        return {'status':'WORK_PACKET','task':str(task),'packet':work}
    signals=signal_packet(task,state)
    if signals:
        work=recursion_agent._packet(task,state,'signal_source','original_signal_relationships',
            'Bind actual source waveform and associated text contracts; strength does not imply frequency.',extra=signals)
        return {'status':'WORK_PACKET','task':str(task),'packet':work}
    from .neighbor_contracts import repair_packet as neighbor_packet
    neighbor_work=neighbor_packet(task,state,candidate)
    if neighbor_work:
        return {'status':'WORK_PACKET','packet':neighbor_work}
    from .source_reading import discover as readings
    if not state.get('quality_intent'):
        return {'status':'WORK_PACKET','packet':{'kind':'quality_intent','inventory':qi.discover(task,state,candidate)}}
    reading_index=readings(task,state);known=state.get('source_readings',{}).get('records',{})
    if reading_index.get('unbound_native_content'):
        return {'status':'WORK_PACKET','packet':{'kind':'source_content_binding','items':reading_index['unbound_native_content'][:8],
            'remaining':len(reading_index['unbound_native_content']),
            'action_family':'amend-source-spec with independent original views; retain every prior unit and threshold',
            'instruction':'Locate these actual saved native owners/cells in the original. Add independent source units and exact content/AST; a panel-level description cannot close them.'}}
    missing=[r for r in reading_index['items'] if r['unit'] not in known
        or r.get('needs_formatted_runs') and 'formatted_runs' not in known[r['unit']]]
    if missing:return {'status':'WORK_PACKET','packet':{'kind':'source_reading','remaining':len(missing),'items':missing[:8]}}
    # The whole-loop entry must route the same mandatory original typography
    # and root obligations as the construction/import entry. Its early return
    # in next_packet must never hide those source packets behind a generic
    # failed-goal report that leaves the host to discover another API.
    from . import agent_runtime as a,execution_contract as ec
    from .textbox_quality import source_packet as text_source_packet
    if state.get('objectives',{}).get('source_textbox_quality'):
        from .retained_typography import report as retained_typography_report
        retained=retained_typography_report(task,state,candidate)
        typography=None if retained.get('applicable') and retained['passed'] else text_source_packet(task,state,candidate)
        if typography:
            packet=a._packet(task,state,'textbox_source','source_textboxes',
                'Read the original-only owner views; freeze exact text/math, glyph ownership and visible typography.',
                extra=typography)
            return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    # A geometry check may need fresh actual owner pixels after code/context
    # changes. Route that executable capture before asking for new source
    # interpretation or another drawing action; an old guard is not evidence.
    from .semantic_composition import guard_saved as current_owner_guard
    guard=current_owner_guard(task,state,ec.resource(task,candidate['pptx']))
    if guard.get('capture_request'):
        candidate['semantic_composition_guard']=guard;candidate['capture_pending']=True
        with a.writer(task):a._save(task,state)
        return {'status':'WORK_PACKET','packet':{'kind':'actual_native_owner_capture','action':'composition capture',
                'request':guard['capture_request'],'remaining':guard.get('remaining_captures',0),
                'scope':'Current actual owner pixels required by the original-bound whole inventory, composition or layout checks'}}
    coverage=ec.packet(task,state,candidate)
    if coverage and (coverage.get('roots') or coverage.get('other')):
        packet=a._packet(task,state,'rule_coverage_source','whole_drawing_rules',
            'Bind every missing current native root to original features and executable source mechanisms.',
            extra=coverage)
        return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    from .source_connections import packet as original_connection_packet
    connection_source=original_connection_packet(task,state)
    if connection_source:return {'status':'WORK_PACKET','packet':connection_source}
    from .source_repeat import packet as repeat_packet
    repeats=repeat_packet(task,state)
    if repeats:
        return {'status':'WORK_PACKET','packet':a._packet(task,state,'source_repeat_observation','original_repeat_families',
            'Identify shared anatomy and independent variant roles before repeated construction; programs freeze and instantiate the mother.',extra=repeats)}
    from .adaptive_detail import packet as detail_packet
    detail_work=detail_packet(task,state,candidate)
    if detail_work:
        packet=a._packet(task,state,'adaptive_source_detail','source_detail_context',
            'Inspect the unchanged original and its context; retained failing predicates require a typed local repair and actual recheck.',extra=detail_work)
        return {'status':'WORK_PACKET','task':str(task),'packet':packet}
    from .connection_geometry import report as actual_connection_report,candidates as connection_candidates
    connection_check=actual_connection_report(task,state,candidate)
    if connection_check.get('status') in ('ORIGINAL_CONNECTION_BINDINGS_REQUIRED','SOURCE_CONNECTION_BINDINGS_REQUIRED'):
        return {'status':'WORK_PACKET','packet':{'kind':'source_connections','analysis':connection_candidates(task,state,candidate),
            'action':'connection-geometry bind','instruction':'Compile original decisions for every source primitive, retained pair candidate and true terminal, even when legacy contracts exist.'}}
    if state.get('connection_attempts') and state.get('quality_intent',{}).get('approved'):
        from .approved_render import source_correction_protection
        protection=source_correction_protection(task,state,candidate,state['quality_intent']['approved'])
        if protection.get('reason','').startswith('Actual program-owned paint capture required'):
            return {'status':'WORK_PACKET','packet':{'kind':'actual_owned_paint','action':'composition capture',
                'reason':protection['reason'],'scope':'Program-owned arrowheads, strokes and effects must be rendered before context-pixel protection can close.'}}
    from .object_lifecycle import owner_source_packet,owner_observation_packet
    first_source=owner_source_packet(task,state,candidate)
    if first_source:return {'status':'WORK_PACKET','packet':first_source}
    first_observation=owner_observation_packet(task,state,candidate)
    if first_observation:return {'status':'WORK_PACKET','packet':first_observation}
    from .global_aesthetic import packet as global_packet
    global_work=global_packet(task,state,candidate)
    if global_work:
        global_work['action']='global-quality bind' if global_work['kind']=='global_aesthetic_source' else 'global-quality observe'
        return {'status':'WORK_PACKET','packet':global_work}
    host=qo.packet(task,state,candidate)
    if host['remaining']:return {'status':'WORK_PACKET','packet':host}
    result=measured or audit(task,state,candidate)
    routed=_measured_work(task,state,candidate,result)
    if routed:return routed
    if not result['gates']['connection_geometry']['passed'] and not state.get('connection_contract'):
        from .connection_geometry import candidates
        return {'status':'WORK_PACKET','packet':{'kind':'source_connections','analysis':candidates(task,state,candidate),
            'action':'connection-geometry bind','instruction':'Inspect the original and bind every connector, endpoint and proposed text-occluded path. Geometry evidence proposes; source interpretation decides.'}}
    if result['status']=='ACCEPTED':return {'status':'READY_FOR_PROGRAM_ACCEPTANCE','action':'quality-loop run'}
    from .global_layout_actions import obligations as global_obligations
    debts=global_obligations(state)
    ineffective=next((r for r in reversed(debts) if r['candidate']==candidate['pptx']['sha256'] and r.get('reflection',{}).get('status')=='NO_ACTUAL_GAIN'),None)
    if ineffective:return {'status':'WORK_PACKET','packet':{'kind':'global_layout_rollback','action':'global-quality rollback',
        'expected_baseline_sha256':candidate['pptx']['sha256'],'attempt':ineffective['branch'],
        'instruction':'Actual global optimization gave no acceptable gain; the program restores its exact immediate pre-layout composition, retaining all earlier independent local improvements.'}}
    if debts:return {'status':'WORK_PACKET','packet':{'kind':'global_transaction_debt','action_family':'restore exact pending candidate and reflect or rollback without overwriting later intrinsic gains',
        'items':[{'attempt':r['branch'],'candidate':r['candidate'],'reflection':r.get('reflection')} for r in debts],
        'instruction':'A candidate change or a different strategy cannot erase an earlier unclosed actual global transaction. Diagnose its exact artifact and dependencies before another layout action.'}}
    from .object_lifecycle import rollback_plan
    rollback_work=rollback_plan(state,result['gates']['object_convergence'].get('regressions',[]))
    if rollback_work['units']:
        return {'status':'WORK_PACKET','packet':{'kind':'object_local_rollback','action':'object-loop rollback',
            'expected_baseline_sha256':candidate['pptx']['sha256'],'units':rollback_work['units'],
            'instruction':'Programs retain each previous best. Restore only these registered unit payloads, rerender and check all current context; unrelated improved units remain retained.'}}
    # Programs locate failures; the host chooses a finite existing action.
    # A descriptive instruction is never executed as coordinates or code.
    causes=[]
    for failure in result['failures']:
        goal=failure['goal'];causes.append({'goal':goal,'action_families':
            ['source_reading','native_text_or_math_patch'] if goal=='text_math' else
            ['global-quality optimize','actual_rerender','global-quality observe'] if goal=='global_aesthetic' else
            ['object-loop rollback','native_field_patch','actual_rerender'] if goal=='object_convergence' else
            ['frame_plan','normalized-preview-repair','semantic_interface','native_field_patch','actual_rerender'] if goal in ('frame','composition','layout','whole_inventory') else
            ['source_policy_correction','native_field_patch','actual_rerender'],
            'write_authority':'Existing bounded grants/actions; check scope remains the complete result',
            'branch_budget':2,'failure_evidence':failure['result']})
    return {'status':'WORK_PACKET','packet':{'kind':'whole_quality_repair','causes':causes[:8],
        'recursive_report':state.get('recursive_obligations_result'),'unclosed':result['gates']['recursive_result_closure']['unclosed'],
        'executable_plan_route':'workflow-control advance executes current source-bound math or a registered recursive plan; otherwise recursive-check plan / execute with registered obligation IDs',
        'failure_agenda_route':'workflow-control plan; explicit native owners, quality units and obligation IDs are distinct',
        'instruction':'Analyze evidence, choose a typed bounded program action, rerender if drawing changed, then rerun the whole quality loop. Two ineffective attempts prune a branch without accepting unresolved hard failures.'}}

def user_report(result):
    gates=result['gates']
    signal_detail=('以函数绘制曲线，检查共同尺度的形状、振幅、包络及相关文字；频率依据原图或明确文字' if gates['signal_semantics'].get('items') else '本图未发现适用的信号曲线；其他图标仍按各自用途检查')
    rows=[('递归容器逐层双轴居中',gates['recursive_containment']['passed'],'原图所有权 DAG；直接内容整体的横纵偏移、四边净距和溢出分别检查，父级不能代替子级'),
          ('真实数学对象与实际编辑',gates['structured_office_math']['passed'],'全部文字所有者先做原图数学/普通文字分类；逐片段核对 AST 与顺序，并在隔离副本执行 Office 编辑、保存、重开和渲染'),
          ('低清晰度图标诊断与重建',gates['icon_clarity']['passed'],'增强图仅供辨认；清晰输出、结构关系、可编辑性与原图像素指标分别检查'),
          ('全近邻覆盖与约束执行',gates['all_neighbor_closure']['passed'],'整图范围查询与独立全对象对枚举交叉核对；跨组合、不同类型和已锁定对象均纳入，漏对、漏谓词、缺测或旧结果会阻止验收'),
          ('纸张折角与完整组合',gates['coherent_paper_geometry']['passed'] and gates['all_neighbor_closure'].get('assemblies',{}).get('passed',False),'纸张和折角共享顶点及唯一描边；组合预期角色独立于构造器定义，局部成功不能代替整个组合检查'),
          ('重复部件与母部件复用',gates['original_repeat_families']['passed'],'原图程序筛选相似实例，模型确认共同结构和独立差异；冻结母部件后程序复制、定位、缩放与旋转，各实例仍单独检查'),
          ('每个递归部件都重建并检查',all(gates[k]['passed'] for k in ('source_recursion','recursive_result_closure','whole_inventory','source_measurement_coverage')),'核对原图语义集合与实际保存图层集合；每个子部件需要当前检查结果，缺件、漏检或失败均阻止父级关闭'),
          ('修改计划按程序执行',gates['executable_process']['passed'],'计划绑定原图、当前文件和检查结果；有限操作执行后重新核对目标部件，保留失败与修订记录'),
          ('信号函数与文字关联',gates['signal_semantics']['passed'],signal_detail),
          ('原图内容与图标结构',all(gates[k]['passed'] for k in ('original_requirements','original_feature_geometry','external_user_intent')),'每个适用原图特征单独核对；已绑定的原图绘制函数另核对实际保存几何，不能用整个图标的平均分代替'),
          ('框架、填满、边界与间距',all(gates[k]['passed'] for k in ('frame','composition','layout')),'程序检查单元格、语义容器、物理接合和有意分离'),
          ('连接线与端部位置',gates['connection_geometry']['passed'],'程序遍历实际连接路径；按原图确认的关系检查共同直线或曲线、端部位置和物理边界'),
          ('文字与公式',all(gates[k]['passed'] for k in ('text_math','original_content_predicates','source_typography')),'原图文字和公式独立读取后与原生内容核对；字体、字形和排版另行检查'),
          ('图标效果与已认可结果',gates['appearance']['passed'],'按用途评价；原图 SSIM 单列，已认可外观与实际大小清晰度独立保护'),
          ('每个对象独立选优、收敛与锁定',gates['object_convergence']['passed'],'分别保留部件自己的候选、当前环境最佳和历史最佳；退化只回滚对应部件，缺测或未达硬目标不能锁定'),
          ('整图六维美观与受限排版',gates['global_aesthetic']['passed'],'布局、平衡、对齐间距、遮挡层级、颜色风格和可读性独立评分；只允许程序调整排版，已通过的内容和图标结构保持'),
          ('观测、真实渲染与字体',all(gates[k]['passed'] for k in ('source_semantics','actual_render','fonts')),
           f"结构化程序结果与实际原图/输出复核共同绑定当前文件；实际渲染宿主：{result['render_backend']}")]
    lines=['# 重建结果报告','',f"结果：**{'当前程序检查闭合，视觉效果待用户查看' if result['status']=='ACCEPTED' else '检查发现实际问题，继续修改'}**",'',
           '| 目标 | 结果 | 实际检查 |','|---|---|---|']
    lines += [f"| {title} | {'通过' if passed else '需处理'} | {detail} |" for title,passed,detail in rows]
    global_quality=gates['global_aesthetic']
    labels={'layout':'布局','visual_balance':'视觉平衡','alignment_spacing':'对齐与间距','layer_occlusion':'层级与遮挡','color_style':'颜色与风格','readability':'科研可读性'}
    if global_quality.get('dimensions'):
        score=global_quality.get('score')
        lines+=['',f"整图美观综合分：**{score:.3f} / 1.000**，通过线 {global_quality['threshold']:.2f}。分数越高越好；这是一套明确的工程评价规则，不是人类审美准确率。" if score is not None else '整图美观：存在缺测，不能验收。',
            '', '| 维度 | 当前分 | 最低要求 |','|---|---:|---:|']
        lines += [f"| {labels[k]} | {v:.3f} | {global_quality['dimension_floors'][k]:.2f} |" if v is not None else f"| {labels[k]} | 缺测 | — |" for k,v in global_quality['dimensions'].items()]
    lines+=['','请先查看 Preview.png 和 Final_editable.pptx，按重建结果验收。原图像素指标、用途化指标及每个部件的检查依据保存在 Evidence 中；检查数量不代表视觉质量。',
            '','程序保证已发现的原图部件与实际绘制部件逐一核对，原图语义识别仍由模型承担。缺件、错误关系或越界不能被综合分抵消；程序闭合不代替用户对视觉效果的批复。']
    return '\n'.join(lines)+'\n'

def export(task,output):
    from . import agent_runtime as a,execution_contract as ec
    from .appearance_metrics import native_signatures
    task,state=a._state(task);candidate=_candidate(state)
    final_gate(task,state,candidate);result=read_json(ec.resource(task,state['quality_result']))
    user_output=Path(output).resolve()
    if user_output.exists():raise FileExistsError('Preserve existing output; choose a new delivery directory')
    output=task/'exports'/('quality-internal-'+identity({'pptx':candidate['pptx'],'destination':str(user_output)})[:24])
    if output.exists():raise FileExistsError('Inspect existing internal export before retry')
    output.mkdir(parents=True)
    for key,name in (('pptx','Final_editable.pptx'),('preview','Preview.png'),('scene','Scene.json')):
        shutil.copyfile(ec.resource(task,candidate[key]),output/name)
    receipt=read_json(ec.resource(task,candidate['render']))
    paper={'status':'VALIDATION_ONLY','user_deliverables':['PPTX','Report'],'pdf_lifecycle':'released after all checks'}
    # Reuse the exact accepted native groups in the original deck. This keeps
    # font resources, nested transforms and media intact and avoids creating a
    # second deck whose cross-file editing behaviour was never observed.
    inv,_,nodes=ec.inventory(task,state,candidate);components=[]
    saved_signatures=native_signatures(str(output/'Final_editable.pptx'),candidate['pptx']['sha256'])
    for item in state['quality_intent']['items']:
        if item.get('semantic_parent'):continue
        selected=set(item['objects']);roots=[n for n in item['objects'] if inv['parents'].get(n) not in selected]
        components.append({'id':item['id'],'purpose':item['purpose'],'root_names':roots,
            'native_objects':item['objects'],'quality_units':item['quality_units'],
            'representation':item['representation'],'source_facts':item['source_facts'],
            'source_artwork_hash':identity({n:saved_signatures.get(n) for n in item['objects']}),
            'reuse':'Select/copy the exact named native root(s) in Final_editable.pptx; retain their ancestor transforms and declared external relations.'})
    write_json(output/'Components-index.json',{'schema':'accepted-native-reuse-index-1','status':'ACCEPTED_WHOLE_ARTWORK',
        'pptx_hash':candidate['pptx']['sha256'],'components':components,
        'limits':'Named native components remain editable in the actual saved deck. Cross-file Office editing behaviour is not inferred from XML or this reuse index.'})
    evidence=output/'Evidence';evidence.mkdir()
    for name,value in (('Whole-result',result),('Adaptive-source-detail',result['gates']['original_adaptive_detail']),
                       ('Original-repeat-families',result['gates']['original_repeat_families']),
                       ('Source-detail-contracts',state.get('source_detail_contracts',{})),('Source-detail-observations',state.get('source_detail',{})),
                       ('Observation-ledger',state['quality_observations']),
                       ('Quality-intent',state['quality_intent']),('Source-readings',state['source_readings']),('Actual-render',receipt),
                       ('Object-lifecycle',state['object_lifecycle']),('Global-plan',state['global_aesthetic_plan']),
                       ('Global-observations',state['global_aesthetic_observations']),('Global-aesthetic',result['gates']['global_aesthetic']),
                       ('Object-global-actions',{'global':state.get('global_layout_attempts',[]),'local_rollback':state.get('object_rollback_attempts',[])}),
                       ('Paper-export',paper),('Execution-coverage',ec.report(task,state,candidate)),
                       ('Source-contracts',{k:state.get(k) for k in ('source','source_size','quality','source_features','frame_plan','semantic_composition','relative_layout','source_recursion','connection_contract','original_feature_functions')})):
        write_json(evidence/(name+'.json'),value)
    from .source_repeat import report as repeat_report
    mothers={r['mother']['sha256']:read_json(ec.resource(task,r['mother']))
        for r in repeat_report(task,state,candidate)['instantiated_functions']}
    write_json(evidence/'Repeat-mother-models.json',{'models':mothers,'basis':'Exact original-bound immutable mother functions used for the saved native instances'})
    for key,name in (('recursive_obligations_result','Recursive-obligations'),
                     ('original_feature_functions','Original-feature-functions'),('connection_contract','Original-connections'),
                     ('source_connection_graph','Original-connection-graph'),('neighbor_source','Original-neighbor-roles'),
                     ('neighbor_registry','Neighbor-predicates'),('neighbor_result','Actual-neighbor-audit'),('neighbor_execution','Current-assembly-execution')):
        if state.get(key):write_json(evidence/(name+'.json'),read_json(ec.resource(task,state[key])))
    from .source_recursion import load as recursion_tree
    write_json(evidence/'Original-recursion-tree.json',recursion_tree(task,state))
    write_json(evidence/'Executable-repair-history.json',[
        {**entry,'compiled_plan':read_json(ec.resource(task,entry['plan']))} for entry in state.get('recursive_repair_plans',[])])
    shutil.copyfile(ec.resource(task,state['acceptance']),evidence/'Acceptance.json')
    (output/'Result.zh-CN.md').write_text(user_report(result),encoding='utf-8')
    (output/'Editing.zh-CN.md').write_text('用户获得 PPTX 与部件指标报告。原生部件按语义名称编辑，PDF 仅用于实际导出与质量验证，完成依赖后释放。复制组合应保留父级变换和声明的外部关系。\n',encoding='utf-8')
    from .component_report import generate
    from .user_delivery import expose
    details=generate(task,output/'Metrics',office_bounds=ec.resource(task,candidate['render']).parent/'text-bounds.json')
    delivery=expose(output/'Final_editable.pptx',None,details,user_output,output/'compact-audit',status='ACCEPTED',
        acceptance=ec.verify_acceptance(task,state,candidate),caps=state['capabilities'],base_render=ec.resource(task,candidate['render']))
    write_json(output/'User-delivery.json',delivery)
    manifest={'schema':'quality-delivery-1','status':'ACCEPTED','source_hash':state['source']['sha256'],
        'pptx_hash':candidate['pptx']['sha256'],'implementation':ec._implementation(),
        'target_basis':__import__(__package__+'.task_completion',fromlist=['target_basis']).target_basis(state),'output':str(output),
        'user_delivery':{'directory':str(user_output),'receipt':delivery['audit_receipt'],'receipt_sha256':digest(delivery['audit_receipt'])},
        'files':{p.relative_to(output).as_posix():{'sha256':digest(p),'bytes':p.stat().st_size} for p in sorted(output.rglob('*')) if p.is_file()}}
    write_json(output/'Manifest.json',manifest)
    official=task/'audits/official-delivery'/('manifest-'+digest(output/'Manifest.json')+'.json')
    write_json(official,manifest);state['official_delivery']={'path':official.relative_to(task).as_posix(),'sha256':digest(official)}
    from .task_completion import stop_report
    from .task_completion import checkpoint
    checkpoint(task,state,candidate,result,{'action':'verify official export and complete'})
    completion=stop_report(task,state,candidate,{'reason':'complete','delivery':state['official_delivery']})
    from .transient_export import release_task_pdfs
    state['pdf_disposal']=release_task_pdfs(task)
    from .projection_gc import dispose
    state['projection_disposal']=dispose(task)
    with writer(task):a._save(task,state)
    return {**delivery,'output':str(user_output),'task_completion':completion}
