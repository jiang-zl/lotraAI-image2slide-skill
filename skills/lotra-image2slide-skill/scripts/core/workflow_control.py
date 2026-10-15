"""Source-bound repair agendas and native capability diagnosis, never PASS.

Original understanding and semantic ambiguity remain the current agent's job.
Diagnostic plans never grant writes. Finite advancement uses only existing
source-owned math contracts or already registered guarded repair plans.
"""
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
import re
from .common import ROOT,digest,identity,read_json,write_json,safe_path
from .task_transaction import guard

VERSION='workflow-control-2'
REFERENCE='references/workflow-optimization.md'


def _policy():
    value=read_json(ROOT/'config/workflow-policy.json')
    if value.get('schema')!='workflow-policy-1':raise ValueError('Unknown workflow policy')
    return value


def _binding(task,state):
    from .execution_contract import _implementation
    candidate=state.get('active_candidate')or state.get('selected')
    binding={'task_id':state['task_id'],'source_hash':state['source']['sha256'],
             'packet_id':(state.get('packet')or {}).get('packet_id'),
             'implementation':_implementation(),'policy':digest(ROOT/'config/workflow-policy.json')}
    for key in ('pptx','preview','render'):
        ref=(candidate or {}).get(key)
        binding[key]=None
        if ref:
            file=safe_path(task,ref['path'])
            if not file.is_file()or digest(file)!=ref['sha256']:raise ValueError('Current workflow resource changed: '+key)
            binding[key]=ref
    return binding,candidate


def _pagination(request):
    offset=request.get('offset',0);limit=request.get('limit',16)
    if type(offset)is not int or offset<0 or type(limit)is not int or not 1<=limit<=64:
        raise ValueError('Explicit bounded workflow pagination required')
    return offset,limit


def current_report(task,state,candidate=None):
    """Reuse only current immutable results for routing, never final acceptance."""
    from .execution_contract import resource,_basis,_implementation
    ref=state.get('quality_result');candidate=candidate or state.get('active_candidate') or state.get('selected')
    if not ref or not candidate:return None,[]
    report=read_json(resource(task,ref))
    for item in (state['source'],*(candidate[k] for k in ('pptx','preview','render') if candidate.get(k))):resource(task,item)
    expected={'source_hash':state['source']['sha256'],'pptx_hash':candidate['pptx']['sha256'],
              'preview_hash':candidate.get('preview',{}).get('sha256'),'implementation':_implementation(),'basis':_basis(state,candidate)}
    stale=[key for key,wanted in expected.items() if report.get(key)!=wanted]
    return (None if stale else report),stale


def _failure_rows(value,path,policy,units=None,inherited=None):
    """Locate explicit checker failures; do not infer semantics from prose."""
    result=[]
    if isinstance(value,dict):
        units=units or {};context=dict(inherited or {})
        uid=value.get('unit')
        if isinstance(uid,str):context['quality_unit']=uid
        names=[]
        for key in ('object','owner','component','native_owner','container'):
            if isinstance(value.get(key),str) and value[key]:names.append(value[key])
        if isinstance(value.get('objects'),list):names.extend(n for n in value['objects'] if isinstance(n,str) and n)
        if names:context['native_owners']=sorted(set(names))
        elif isinstance(uid,str) and uid in units:context['native_owners']=sorted(set(units[uid].get('objects',[])))
        failed=(value.get('passed')is False or value.get('critical_pass')is False or
                value.get('valid')is False or value.get('measurement_valid')is False or
                value.get('status')in policy['failure_statuses'] or bool(value.get('below_targets')))
        if failed:
            kind=('measurement_invalid' if value.get('valid')is False or value.get('measurement_valid')is False or value.get('status')=='MEASUREMENT_INVALID' else
                  'evidence_missing' if value.get('status') in policy.get('missing_evidence_statuses',[]) else 'artifact_or_contract_failure')
            owners=context.get('native_owners',[])
            result.append({'selector':path,'id':value.get('id',value.get('unit')),
                           'obligation_id':value.get('id'),'quality_unit':context.get('quality_unit'),
                           'native_owners':owners,'owner':owners[0] if len(owners)==1 else None,
                           'failure_kind':kind,'status':value.get('status'),'reason':str(value.get('reason',''))[:400]})
        for key,child in value.items():
            if isinstance(child,(dict,list)):result.extend(_failure_rows(child,path+[key],policy,units,context))
    elif isinstance(value,list):
        for i,child in enumerate(value):result.extend(_failure_rows(child,path+[i],policy,units,inherited))
    return result


def plan(task,state,request):
    from .context_control import authorize,register_output
    from .execution_contract import _basis
    binding,candidate=_binding(task,state);policy=_policy();offset,limit=_pagination(request)
    report_ref=state.get('quality_result');report=None;stale=[]
    if request.get('report')is not None and request['report']!=report_ref:
        raise ValueError('Agenda must use the current registered quality report')
    if report_ref:
        report=read_json(authorize(task,report_ref,state=state))
        expected={'source_hash':binding['source_hash'],'pptx_hash':binding['pptx']['sha256']if binding['pptx']else None,
                  'preview_hash':binding['preview']['sha256']if binding['preview']else None,'implementation':binding['implementation']}
        stale=[k for k,v in expected.items()if report.get(k)!=v]
        if candidate and report.get('basis')!=_basis(state,candidate):stale.append('basis')
    groups=[];rows=[]
    if report and not stale:
        for name,value in report.get('gates',{}).items():
            if value.get('passed')is True:continue
            phase=policy['gate_phases'].get(name,'unclassified')
            located=_failure_rows(value,['gates',name],policy,state.get('quality',{}).get('units',{}))
            if not located:located=[{'selector':['gates',name],'id':None,'owner':None,'status':value.get('status'),'reason':'Failed gate needs agent inspection of its exact current contract'}]
            groups.append({'gate':name,'phase':phase,'located_records':len(located),
                           'route':policy['phases'].get(phase,policy['phases']['unclassified'])})
            rows.extend({'gate':name,'phase':'measurement' if row.get('failure_kind')=='measurement_invalid' else phase,
                         'execution_route':policy.get('gate_routes',{}).get(name),**row}for row in located)
    order={name:i for i,name in enumerate(policy['phase_order'])}
    groups.sort(key=lambda x:order.get(x['phase'],len(order)))
    for row in rows:
        owners=row.get('native_owners',[])
        row['resource_group']=identity({'source':binding['source_hash'],'candidate':binding['pptx'],
            'explicit_owners':owners}) if owners else None
    rows.sort(key=lambda x:(order.get(x['phase'],len(order)),x['resource_group'] or '~'+x['gate'],x['gate']))
    locality={'order':'dependency phase, then explicit owner resource group',
              'scope':'current original/candidate only',
              'execution':'Prepare adjacent same-resource finite actions where current contracts permit; batches retain caller order.',
              'authority':'Grouping is a locality hint, not semantic identity, mutation independence or reduced coverage.'}
    dependency={'current':False,'mode':'complete','reason':'No current dependency evidence',
                'authority':'Order and diagnostic explanation only; no reduction of complete coverage or final gates.'}
    ref=state.get('context_dependencies')
    if ref:
        data=read_json(authorize(task,ref,state=state))
        from . import dependency_context,boundary_geometry,native_markup,mathml
        code=identity({name:digest(module.__file__)for name,module in
                       (('graph',dependency_context),('geometry',boundary_geometry),('markup',native_markup),('math',mathml))})
        valid=(data.get('source_hash')==binding['source_hash']and
               data.get('pptx_hash')==(binding['pptx']or {}).get('sha256')and data.get('implementation')==code)
        reason=('Changed original/native/dependency implementation; complete current work remains required'if not valid
                else 'Unknown relations require conservative complete work'if data.get('unknown_relations')
                else data.get('impact',{}).get('reason'))
        dependency={'reference':ref,'current':valid,'mode':'complete'if not valid or data.get('unknown_relations')else 'affected_first',
                    'changed_native':len(data.get('changed_native',[])),'affected_objects':len(data.get('impact',{}).get('objects',[])),
                    'global_check':not valid or data.get('impact',{}).get('global',True),'reason':reason,
                    'authority':'Order and diagnostic explanation only; no reduction of complete coverage or final gates.'}
    full={'schema':VERSION,'binding':binding,'report':report_ref,'stale_report_fields':stale,
          'groups':groups,'records':rows,'dependency_scope':dependency,'resource_locality':locality,
          'current_packet':{'kind':(state.get('packet')or {}).get('kind'),'target':(state.get('packet')or {}).get('target')},
          'authority':'Current next/submit contracts remain authoritative. This agenda cannot accept, close or rebase any obligation.'}
    file=safe_path(task,'context/workflows/Agenda-'+identity(full)+'.json')
    if file.exists()and read_json(file)!=full:raise ValueError('Immutable workflow agenda collision')
    if not file.exists():write_json(file,full)
    retained=register_output(task,file)
    return {'schema':VERSION,'status':'STALE_REPORT_REQUIRES_CURRENT_CHECK'if stale else 'REPAIR_AGENDA'if rows else 'FOLLOW_CURRENT_PACKET',
            'binding':binding,'agenda':retained,'stale_report_fields':stale,'groups':groups,'dependency_scope':dependency,'resource_locality':locality,
            'total':len(rows),'offset':offset,'count':len(rows[offset:offset+limit]),'records':rows[offset:offset+limit],
            'next_offset':offset+limit if offset+limit<len(rows)else None,'action_references':[REFERENCE],
            'authority':full['authority']}


def _math_request(task,state,candidate,packet):
    from .office_math_contract import load
    checked,stale=current_report(task,state,candidate)
    if stale or checked is None:return None
    measured={r['object']:r for r in checked['gates']['structured_office_math'].get('items',[])}
    contract=load(task,state);bound={r['object']:r for r in (contract or {}).get('owners',[])}
    names=[n for n in packet.get('objects',[]) if n in bound and not bound[n].get('graphical_carrier')
           and measured.get(n,{}).get('expected_spans',0)>0 and
           (measured[n].get('representation_match') is False or any(v.get('passed') is False for v in measured[n].get('span_checks',[])))]
    if not names:return None
    return {'source_hash':state['source']['sha256'],'baseline_hash':candidate['pptx']['sha256'],
            'objects':names[:16],'write_set':{n:['text_body'] for n in names[:16]},
            'reason':'Current source-bound AST/OMML content failure; existing exact native replay protects all out-of-scope properties'}


def _registered_action(task,state,candidate):
    from .execution_contract import resource
    from .recursive_obligations import current_basis
    for entry in state.get('recursive_repair_plans',[]):
        if entry.get('superseded_by'):continue
        plan=read_json(resource(task,entry['plan']))
        if plan['baseline']!=candidate['pptx']:continue
        check=read_json(resource(task,plan['check_report']))
        if check.get('basis')!=current_basis(task,state,candidate):continue
        for row in plan['actions']:
            history=[r for r in entry['executions'] if r['action']==row['id']]
            if any(r['status']=='EXECUTED_REQUIRES_CURRENT_WHOLE_CHECK' for r in history):continue
            if sum(r['status']=='EXECUTION_FAILED' for r in history)>=2:continue
            return {'plan':entry['plan'],'action':row['id']}
    return None


def advance(task,request):
    """Finite deterministic actions, then return the next real contract."""
    from .component_workflow import enabled as component_enabled, advance as component_advance
    from .agent_runtime import _state
    task,state=_state(task)
    if component_enabled(state):return component_advance(task,request)
    from . import agent_runtime as a
    maximum=request.get('max_actions',4)
    if type(maximum)is not int or not 1<=maximum<=8:raise ValueError('Advance needs a finite 1..8 action bound')
    executions=[];stop='FINITE_ACTION_BOUND';work=None
    for _ in range(maximum):
        task,state=a._state(task)
        if request.get('source_hash',state['source']['sha256'])!=state['source']['sha256']:raise ValueError('Advance belongs to another original')
        work=a.next_packet(task);packet=work.get('packet')or {}
        task,state=a._state(task);candidate=state.get('active_candidate')or state.get('selected')
        if work.get('status')!='WORK_PACKET' or not candidate:
            stop='FOLLOW_CURRENT_CONTRACT';break
        if packet.get('kind')=='source_structured_math_repair':
            payload=_math_request(task,state,candidate,packet)
            if payload:
                from .office_math_contract import dispatch as math_dispatch
                result=math_dispatch(task,'repair',payload)
                executions.append({'action':'office-math repair','objects':payload['objects'],'baseline_hash':payload['baseline_hash'],'result':result})
                continue
        # Registered finite plans carry the agent's explicit operator choice.
        # Neither a prose failure nor an arbitrary native ID grants an edit.
        if packet.get('kind')=='whole_quality_repair':
            action=_registered_action(task,state,candidate)
            if action:
                from .recursive_obligations import execute_plan
                result=execute_plan(task,action);executions.append({'action':'recursive-check execute','request':action,'result':result})
                continue
        stop='MEASUREMENT_DIAGNOSIS_REQUIRED' if packet.get('kind')=='icon_edge_measurement_diagnosis' else 'FOLLOW_CURRENT_CONTRACT'
        break
    if stop=='FINITE_ACTION_BOUND':work=a.next_packet(task)
    return {'schema':VERSION,'status':'ADVANCED_REQUIRES_CURRENT_CHECKS' if executions else 'FOLLOW_CURRENT_PACKET',
            'executions':executions,'count':len(executions),'stop_reason':stop,'next':work,
            'action_references':[REFERENCE],
            'authority':'Existing source-bound native executors only; no automatic source interpretation, rebase, render waiver or acceptance. Host/font/semantic work returns its current packet.'}


def preflight(task,state,request):
    from lxml import etree as E
    from .mathml import NS
    from .native_markup import active_children
    from .boundary_geometry import saved_nodes
    from .connection_geometry import line,_boundary
    binding,candidate=_binding(task,state)
    if not candidate or not binding['pptx']:
        return {'schema':VERSION,'status':'NATIVE_PREFLIGHT_PENDING','binding':binding,
                'reason':'No saved current native candidate; use registered host readiness and current source/planned-construction contracts first.',
                'action_references':[REFERENCE],'quality_pass':None}
    file=safe_path(task,binding['pptx']['path']);rows=[];discovery_error=None
    try:nodes=saved_nodes(file,state['source_size'])
    except (ValueError,KeyError,TypeError,AttributeError)as exc:
        nodes={};discovery_error=type(exc).__name__+': '+str(exc)
    from .resource_facts import package_read,xml_part
    with package_read(file,binding['pptx']['sha256'])as z:
        slides=sorted(n for n in z.namelist()if re.fullmatch(r'ppt/slides/slide[0-9]+\.xml',n))
        font_resources=[n for n in z.namelist()if n.startswith('ppt/fonts/')]
        for part in slides:
            tree=xml_part(file,part,binding['pptx']['sha256']);root=tree.find('p:cSld/p:spTree',NS)
            if root is None:raise ValueError('Missing native shape tree: '+part)
            native=[]
            def visit(parent):
                for node in active_children(parent):
                    tag=E.QName(node).localname
                    if tag not in {'sp','grpSp','cxnSp','pic','graphicFrame'}:continue
                    native.append(node)
                    if tag=='grpSp':visit(node)
            visit(root)
            for node in native:
                meta=node.find('.//p:cNvPr',NS);name=meta.get('name')if meta is not None else None
                row={'slide':part,'owner':name,'native_type':E.QName(node).localname,
                     'status':'INVENTORIED','geometry':'NOT_APPLICABLE','font_reference':'NOT_APPLICABLE'}
                entry=nodes.get(name)if part=='ppt/slides/slide1.xml'else None
                if not entry:row.update(status='REQUIRES_DIAGNOSIS',geometry=discovery_error or 'Saved geometry decoder is scoped to the first diagram slide; extra-slide coverage remains pending')
                elif entry.get('error'):row.update(status='REQUIRES_DIAGNOSIS',geometry=entry['error'])
                elif entry['tag']in ('sp','cxnSp'):
                    props=node.find('p:spPr',NS);preset=props.find('a:prstGeom',NS)if props is not None else None
                    custom=props.find('a:custGeom',NS)if props is not None else None
                    if preset is not None or custom is not None:
                        kind=preset.get('prst','')if preset is not None else ''
                        filled=props is not None and any(props.find('a:'+k,NS)is not None for k in ('solidFill','gradFill','pattFill'))
                        try:
                            if entry['tag']=='cxnSp'or kind=='line'or kind.startswith('bentConnector')or not filled and custom is not None:line(entry)
                            else:_boundary(entry)
                            row['geometry']='DECODED_CURRENT_NATIVE'
                        except (ValueError,KeyError,TypeError,AttributeError)as exc:
                            row.update(status='REQUIRES_DIAGNOSIS',geometry=type(exc).__name__+': '+str(exc))
                text=node.findall('p:txBody//a:t',NS)
                if text:
                    families=sorted({n.get('typeface')for k in ('latin','ea','cs')for n in node.findall('p:txBody//a:'+k,NS)if n.get('typeface')})
                    row['font_reference']=families or 'MISSING_EXPLICIT_REFERENCE'
                    if not families:row['status']='REQUIRES_DIAGNOSIS'
                row['office_math_nodes']=len(node.findall('p:txBody//m:oMath',NS))
                rows.append(row)
                for ri,tr in enumerate(node.findall('a:graphic/a:graphicData/a:tbl/a:tr',NS)):
                    for ci,cell in enumerate(tr.findall('a:tc',NS)):
                        rows.append({'slide':part,'owner':str(name)+'/cell/'+str(ri)+'/'+str(ci),
                                     'native_type':'table_cell','status':'INVENTORIED','geometry':'INHERITS_TABLE_REQUIRES_CELL_CHECK',
                                     'office_math_nodes':len(cell.findall('.//m:oMath',NS)),
                                     'authority':'A native cell inventory is not its content/layout/editability PASS.'})
    if digest(file)!=binding['pptx']['sha256']:raise ValueError('Native preflight bytes changed')
    return {'schema':VERSION,'status':'PREFLIGHT_REQUIRES_DIAGNOSIS'if any(r['status']=='REQUIRES_DIAGNOSIS'for r in rows)else 'PREFLIGHT_INVENTORIED',
            'binding':binding,'slides':len(slides),'counts':dict(Counter(r['native_type']for r in rows)),
            'font_resources':len(font_resources),'records':rows,'discovery_error':discovery_error,'quality_pass':None,
            'action_references':[REFERENCE],
            'authority':'Actual saved parsing/inventory only. Source semantics, cells, fonts, Office editing, renders, HD multi-scale/material and final local/global predicates all remain mandatory.'}


def dispatch(task,operation,request=None):
    from . import agent_runtime as a
    with guard(task):
        task,state=a._state(task);request={}if request is None else request
        if not isinstance(request,dict)or set(request)-{'source_hash','report','offset','limit','max_actions'}:
            raise ValueError('Explicit bounded workflow request required')
        if request.get('source_hash',state['source']['sha256'])!=state['source']['sha256']:
            raise ValueError('Workflow request belongs to another original')
        if operation=='advance':
            if set(request)-{'source_hash','max_actions'}:raise ValueError('Advance uses its current packet; no caller report or rebase')
            return advance(task,request)
        if 'max_actions'in request:raise ValueError('Action bounds apply only to finite advance')
        if operation=='plan':return plan(task,state,request)
        if operation=='preflight':return preflight(task,state,request)
        if operation=='profile':
            from .workflow_profile import report
            return {**report(task,request),'task_id':state['task_id'],'source_hash':state['source']['sha256']}
        raise ValueError('Unknown workflow operation')
