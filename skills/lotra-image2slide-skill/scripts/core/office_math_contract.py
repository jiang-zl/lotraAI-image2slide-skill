"""Complete source prose/math classification and real structured math gates.

Content, representation and actual edit/save/reopen behavior are distinct.
Every actual text owner needs an original-only classification; program hints
cannot decide whether a scientific letter is a mathematical variable.
"""
import copy,re
from lxml import etree as E
from .common import identity,digest,read_json,write_json,safe_path,writer
from .mathml import NS,math_zone

VERSION='office-math-contract-1'

def owners(task,state,candidate):
    from .inspect import xml,inventory
    from .execution_contract import resource
    nodes,dups=inventory(xml(resource(task,candidate['pptx'])))
    if dups:raise ValueError('Ambiguous mathematical owner')
    return {n:r for n,r in nodes.items() if E.QName(r['node']).localname!='grpSp'
        and (r['node'].find('.//a:t',NS) is not None or r['node'].find('.//m:oMath',NS) is not None)}

def discover(task,state,candidate):
    rows=[]
    for name,row in owners(task,state,candidate).items():
        node=row['node'];text=''.join(node.xpath('.//a:t/text()',namespaces=NS))
        rows.append({'object':name,'native_text_hint':text,'actual_math_zones':len(node.findall('.//m:oMath',NS)),
            'suspect_not_semantic_decision':bool(re.search(r'[\u2070-\u209f\u1d00-\u1dff]|\b[QKVtKL]\b|[∑∏=±≤≥]|[A-Za-z]_[A-Za-z0-9]',text))})
    return {'kind':'office_math_source_classification','action':'office-math bind','source_hash':state['source']['sha256'],
        'items':rows,'graphic_candidates':[{'unit':u['id'],'objects':u['objects'],'roi':u['roi'],'features':u['features']} for u in state.get('quality',{}).get('units',{}).values() if u.get('profile') not in ('text','photo')],
        'return':'Classify every text/table owner and inspect original graphic candidates for mathematical operators drawn as strokes. Exact ordered prose/math segments, and optional graphical_carrier {members,source_bbox,font_size_pt}; one visible real equation replaces its complete glyph carriers. Ordinary illustrations remain graphic primitives. Single variables and inline spans are math; no candidate-derived expected AST.'}

def bind(task,state,candidate,request):
    from .recursive_containment import source_view
    if request.get('schema')!=VERSION or request.get('source_hash')!=state['source']['sha256']:raise ValueError('Original mathematical inventory required')
    source_view(task,state,request['source_view'])
    rows=request.get('owners',[]);required=set(owners(task,state,candidate))
    from .boundary_geometry import saved_nodes
    native=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size'])
    graphical={r['object'] for r in rows if r.get('graphical_carrier')}
    required|=graphical
    if len({r['object'] for r in rows})!=len(rows) or {r['object'] for r in rows}!=required:raise ValueError('Classify every text/table/math owner; a formula-only inventory omits inline/single variables')
    from .mathml import math_node
    from .math_typography import validate as validate_typography
    for r in rows:
        validate_typography(r.get('typography',{}))
        if not r.get('source_evidence') or not isinstance(r.get('paragraphs'),list) or not r['paragraphs']:raise ValueError('Exact original prose/math reading with paragraph order required')
        for p in r['paragraphs']:
            if not p:raise ValueError('Explicit paragraph segment inventory required')
            for s in p:
                if ('text' in s)==('ast' in s):raise ValueError('A segment is either ordinary prose or structured mathematical AST')
                if 'ast' in s:
                    validate_typography(s.get('typography',{}))
                    if not s.get('source_roi'):raise ValueError('Locate each original mathematical span, including single letters')
                    math_node(s['ast'])
                elif not isinstance(s['text'],str):raise ValueError('Exact prose string required')
        if r.get('graphical_carrier'):
            g=r['graphical_carrier'];names=g.get('members',[])
            if not names or r['object'] not in names or not set(names)<=set(native) or len(names)!=len(set(names)):
                raise ValueError('Bind every original graphic glyph carrier and one stable equation owner')
            if any(native[n]['tag']=='grpSp' for n in names):raise ValueError('Graphic conversion acts on explicit leaves, never an entire illustration group')
            if len(r['paragraphs'])!=1 or len(r['paragraphs'][0])!=1 or 'ast' not in r['paragraphs'][0][0]:raise ValueError('A graphic mathematical operator becomes exactly one real formula span')
            if len(g.get('source_bbox',[]))!=4 or not 4<=g.get('font_size_pt',0)<=96:raise ValueError('Original-only glyph box and bounded mathematical type size required')
        # A prose-only classification may not hide old independently bound
        # mathematical spans. Correct original readings by amendment, not by
        # convenient reclassification of an inconvenient native representation.
        old=[u for u in state.get('quality',{}).get('units',{}).values() if r['object'] in u.get('objects',[])]
        expected=sum(len(f.get('math_spans',[])) or bool(f.get('ast')) for u in old for f in u.get('features',[]) if f.get('category')=='content' and f.get('status')=='observed')
        if expected and not any('ast' in s for p in r['paragraphs'] for s in p):raise ValueError('Existing original math obligation cannot become ordinary prose')
    file=task/'source/office-math'/('contract-'+identity(request)+'.json');write_json(file,request)
    state.setdefault('office_math_history',[]).append(copy.deepcopy(state.get('office_math_contract')))
    state['office_math_contract']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    state.pop('acceptance',None);state.pop('quality_result',None)
    return {'status':'ORIGINAL_MATH_INVENTORY_BOUND','owners':len(rows),'spans':sum('ast' in s for r in rows for p in r['paragraphs'] for s in p),'quality_acceptance':False}

def load(task,state):
    from .execution_contract import resource
    if not state.get('office_math_contract'):return None
    document=read_json(resource(task,state['office_math_contract']))
    if document['source_hash']!=state['source']['sha256']:raise ValueError('Different original math inventory')
    from .recursive_containment import source_view
    source_view(task,state,document['source_view']);return document

def _segments(node):
    from .inspect import parse_math_container
    rows=[]
    for p in node.findall('p:txBody/a:p',NS) or node.findall('.//a:tc/a:txBody/a:p',NS):
        segments=[]
        for child in p:
            if child.tag in ('{'+NS['a']+'}r','{'+NS['a']+'}fld'):
                t=''.join(v.text or '' for v in child.findall('.//a:t',NS))
                if segments and 'text' in segments[-1]:segments[-1]['text']+=t
                else:segments.append({'text':t})
            elif child.tag=='{'+NS['a14']+'}m':
                zones=child.findall('.//m:oMath',NS)
                if len(zones)!=1:raise ValueError('One real mathematical zone per source span')
                segments.append({'ast':parse_math_container(zones[0])})
            elif child.tag=='{'+NS['a']+'}br':segments.append({'text':'\v'})
        rows.append(segments)
    return rows

def _expected(row):
    # Adjacent ordinary runs may serialize with different typography pieces;
    # only ordinary-run segmentation is normalized, never mathematical spans.
    out=[]
    for p in row['paragraphs']:
        seg=[]
        for s in p:
            v={k:s[k] for k in ('ast','text') if k in s}
            if 'text' in v and not v['text']:continue
            if 'text' in v and seg and 'text' in seg[-1]:seg[-1]['text']+=v['text']
            else:seg.append(copy.deepcopy(v))
        out.append(seg)
    return out

def unit_evidence(task,state,candidate,unit):
    """Reuse the independently reread ordered source inventory for mixed math.

    Old flattened literals/runs remain diagnostics. They cannot require a
    genuine formula to serialize as plain text. Nonmath prose retains the
    existing text checker; a span-specific source unit retains its own AST.
    """
    if unit.get('protocol',{}).get('table_cell') is not None or unit.get('protocol',{}).get('math_span_index') is not None:return None
    contract=load(task,state)
    if not contract:return None
    row=next((r for r in contract['owners'] if unit.get('objects')==[r['object']] or r.get('graphical_carrier',{}).get('members') and set(unit.get('objects',[]))==set(r['graphical_carrier']['members'])),None)
    if not row or not any('ast' in s for p in row['paragraphs'] for s in p):return None
    from .inspect import xml,inventory
    from .execution_contract import resource
    from .source_reading import semantic_ast
    nodes,duplicates=inventory(xml(resource(task,candidate['pptx'])))
    expected=_expected(row);node=nodes[row['object']]['node'];actual=_segments(node)
    represented=len(node.findall('.//m:oMath',NS))==sum('ast' in v for p in expected for v in p) and not node.findall('.//{urn:lotraai:native-math-span:1}span')
    return {'passed':semantic_ast(expected)==semantic_ast(actual) and represented,'status':'MEASURED',
        'source_segments':expected,'native_segments':actual,'representation_match':represented,'source_view':contract['source_view'],
        'source_evidence':row['source_evidence'],'source_contract':state['office_math_contract'],
        'basis':'Independent original ordered prose/math inventory; compare actual OMML AST and exact prose, preserving historical flattened-source diagnostics'}

def report(task,state,candidate):
    contract=load(task,state)
    if not contract:return {'schema':VERSION,'passed':False,'status':'SOURCE_BINDING_REQUIRED','items':[],'next':'office-math discover'}
    actual=owners(task,state,candidate);rows=[];classified={r['object'] for r in contract['owners']}
    from .source_reading import semantic_ast
    for r in contract['owners']:
        name=r['object'];spans=[s['ast'] for p in r['paragraphs'] for s in p if 'ast' in s]
        row={'id':'math-owner:'+name,'object':name,'expected_spans':len(spans),'passed':False,'source_evidence':r['source_evidence']}
        try:
            node=actual[name]['node'];measured=_segments(node);expected=_expected(r)
            row.update(actual_segments=measured,source_segments=expected,
                content_match=semantic_ast(expected)==semantic_ast(measured),
                representation_match=len(node.findall('.//m:oMath',NS))==len(spans) and not node.findall('.//{urn:lotraai:native-math-span:1}span'))
            row['passed']=row['content_match'] and row['representation_match'];row['status']='MEASURED_PASS' if row['passed'] else 'MEASURED_FAIL'
            from .math_typography import check as typography_check
            source_spans=[s for p in r['paragraphs'] for s in p if 'ast' in s]
            zones=node.findall('.//m:oMath',NS)
            row['typography_checks']=[typography_check(zones[i],{**r.get('typography',{}),**s.get('typography',{})})
                if i<len(zones) else {'passed':False,'failures':[{'reason':'Missing actual math span'}]}
                for i,s in enumerate(source_spans)]
            row['passed']&=all(v['passed'] for v in row['typography_checks'])
            row['status']='MEASURED_PASS' if row['passed'] else 'MEASURED_FAIL'
            measured_spans=[s['ast'] for p in measured for s in p if 'ast' in s]
            row['span_checks']=[]
            for i,ast in enumerate(spans):
                value=measured_spans[i] if i<len(measured_spans) else None
                passed=value is not None and semantic_ast(ast)==semantic_ast(value) and not node.findall('.//{urn:lotraai:native-math-span:1}span')
                row['span_checks'].append({'id':name+':math:'+str(i),'kind':'math_span','passed':passed,'expected_ast':ast,'actual_ast':value,
                    'representation':'real_OMML_required','status':'MEASURED_PASS' if passed else 'MEASURED_FAIL','next_action':'office-math repair' if not passed else None})
            if r.get('graphical_carrier'):
                from .neighbor_geometry import read as actual_paint
                paint,errors=actual_paint(task,state,candidate,state.get('neighbor_mattes'))
                retired=set(r['graphical_carrier']['members'])-{name}
                row['retired_graphic_carriers']={'passed':all(paint.get(n,{}).get('nonpaint') is True for n in retired),'objects':sorted(retired),'purpose':'Original vector-glyph carriers are archived in the source and retained as nonpainting lineage; all visible mathematical ink comes from the real equation'}
                row['passed']&=row['retired_graphic_carriers']['passed']
        except (ValueError,KeyError,TypeError,AttributeError) as exc:row.update(status='required_unmeasured',reason=str(exc))
        rows.append(row)
    missing=sorted(set(actual)-classified)
    edit=behavior_report(task,state,candidate,contract)
    return {'schema':VERSION,'passed':not missing and all(r['passed'] for r in rows) and edit['passed'],
        'status':'PASS' if not missing and all(r['passed'] for r in rows) and edit['passed'] else 'WORK_REQUIRED',
        'items':rows,'unclassified':missing,'source_contract':state['office_math_contract'],'pptx_hash':candidate['pptx']['sha256'],
        'edit_behavior':edit,'coverage':{'owners':{'classified':len(classified&set(actual)),'required':len(actual)},
            'spans':{'required':sum(r['expected_spans'] for r in rows),'measured':sum(len(r.get('span_checks',[])) for r in rows)}}}

def repair_plan(task,state,candidate,request):
    contract=load(task,state);selected=request.get('objects',[]);by={r['object']:r for r in contract['owners']}
    if not selected or len(selected)>16 or not set(selected)<=set(by):raise ValueError('Bound 1..16 original mathematical owners per finite action')
    if any('text_body' not in request.get('write_set',{}).get(n,[]) for n in selected):raise ValueError('Explicit mathematical content/representation write required')
    changes={}
    for n in selected:
        changes[n]={'paragraphs':copy.deepcopy(by[n]['paragraphs']),'math_font_policy':'native_math'}
        if by[n].get('graphical_carrier'):changes[n]['graphical_carrier']=copy.deepcopy(by[n]['graphical_carrier'])
        if by[n].get('typography'):changes[n]['typography']=copy.deepcopy(by[n]['typography'])
    writes={n:['text_body'] for n in selected}
    for n in selected:
        if by[n].get('graphical_carrier'):
            for member in by[n]['graphical_carrier']['members']:
                if 'math_representation' not in request.get('write_set',{}).get(member,[]):raise ValueError('Converting every original mathematical graphic carrier requires an explicit representation grant')
                writes[member]=sorted(set(writes.get(member,[]))|{'math_representation'})
    return {'kind':VERSION,'source_contract':state['office_math_contract'],'math_bodies':changes,
        'write_set':writes,'check_set':list(by),'protected_set':sorted(set(by)-set(selected)),
        'next':'Actual Office render, AST/prose comparison, isolated real edit/save/reopen probe; no text/image fallback'}

def behavior_report(task,state,candidate,contract):
    needed={r['object']:sum('ast' in s for p in r['paragraphs'] for s in p) for r in contract['owners']}
    needed={n:c for n,c in needed.items() if c}
    if not needed:return {'passed':True,'status':'EVIDENCED_NOT_APPLICABLE','reason':'Independent original inventory contains no mathematical spans'}
    ref=state.get('office_math_behavior')
    if not ref:return {'passed':False,'status':'required_unmeasured','required':needed,'next':'office-math edit-probe'}
    from .execution_contract import resource,_implementation
    try:
        record=read_json(resource(task,ref))
        if record.get('kind')=='native_math_roundtrip_1':
            from .math_roundtrip import verify
            return verify(task,state,candidate,record,needed)
        if record['pptx_hash']!=candidate['pptx']['sha256'] or record['implementation']!=_implementation():raise ValueError('Stale actual equation edit behavior')
        # Verify evidence from saved, independently parsed edited bytes again.
        from .native_task import verify
        checked=verify(resource(task,record['plan']),safe_path(task,record['office_directory']),safe_path(task,record['independent_check']['path']))
        math=[r for r in checked['checks'] if r.get('action')=='math']
        counts={n:sum(r.get('object_id')==n and r.get('status')=='PASS' for r in math) for n in needed}
        passed=counts==needed and checked.get('status')=='PASS' and checked.get('actual_host_job_verified') is True
        return {'passed':passed,'status':'MEASURED_PASS' if passed else 'MEASURED_FAIL','required':needed,'verified':counts,'receipt':ref,'result':checked}
    except (ValueError,KeyError,TypeError,FileNotFoundError) as exc:return {'passed':False,'status':'required_unmeasured','reason':str(exc),'next':'office-math edit-probe'}

def edit_probe(task,state,candidate):
    from .native_task import plan_saved_equations,verify
    from .office import probe
    from .execution_contract import resource,_implementation
    contract=load(task,state)
    if not contract:raise ValueError('Classify every original mathematical span before editing verification')
    folder=task/'audits/office-math-edit'/identity({'pptx':candidate['pptx'],'contract':state['office_math_contract'],'implementation':_implementation()})
    folder.mkdir(parents=True,exist_ok=True);plan=folder/'Plan.json'
    if not plan.exists():plan_saved_equations(resource(task,candidate['pptx']),plan,before_render=resource(task,candidate['render']) if candidate.get('render') else None)
    out=folder/'Actual-Office'
    if not (out/'operations.json').exists():probe(resource(task,candidate['pptx']),out,task_plan=plan,timeout=600)
    result=verify(plan,out,folder/'Independent-check.json')
    record={'pptx_hash':candidate['pptx']['sha256'],'implementation':_implementation(),
        'plan':{'path':plan.relative_to(task).as_posix(),'sha256':digest(plan)},'office_directory':out.relative_to(task).as_posix(),
        'independent_check':{'path':(folder/'Independent-check.json').relative_to(task).as_posix(),'sha256':digest(folder/'Independent-check.json')},
        'result':result}
    file=folder/'Receipt.json';write_json(file,record);state['office_math_behavior']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    return behavior_report(task,state,candidate,contract)

def dispatch(task,operation,request=None):
    from . import agent_runtime as a
    task,state=a._state(task);candidate=state.get('active_candidate') or state.get('selected');request=request or {}
    if operation=='discover':return discover(task,state,candidate)
    if operation=='report':return report(task,state,candidate)
    if operation=='repair':
        if request.get('baseline_hash')!=candidate['pptx']['sha256']:raise ValueError('Current native math repair basis required')
        from .target_actions import execute
        return execute(task,state,candidate,repair_plan(task,state,candidate,request),request)
    if operation=='bind':result=bind(task,state,candidate,copy.deepcopy(request))
    elif operation=='edit-probe':result=edit_probe(task,state,candidate)
    elif operation=='roundtrip-probe':
        from .math_roundtrip import probe
        contract=load(task,state)
        if not contract:raise ValueError('Original native math inventory required')
        needed={r['object']:sum('ast' in s for p in r['paragraphs'] for s in p) for r in contract['owners']}
        result=probe(task,state,candidate,{n:c for n,c in needed.items() if c})
    else:raise ValueError('Unknown Office Math operation')
    with writer(task):a._save(task,state)
    return result
