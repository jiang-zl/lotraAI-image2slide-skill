"""Exhaustive, independent unit best/convergence records in the production loop.

Artifact references are shared and immutable. Missing measurements and incompatible
contexts are not ranks. Program decisions, rather than a host's lock declaration,
own convergence; failed branches can never manufacture an accepted unit.
"""
import copy,math
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
from .common import identity,digest,read_json,write_json,safe_path,writer
from .mathml import NS

VERSION='independent-object-lifecycle-1'

def _config():
    from .global_aesthetic import configuration
    return configuration()['objects']

def owner_source_packet(task,state,candidate):
    """Every painted first-build owner needs an original frame and own review."""
    if state.get('quality_intent',{}).get('approved'):return None
    from .execution_contract import inventory
    from .native_connection_transaction import verify_anchor
    inv,_,nodes=inventory(task,state,candidate);bound=state.get('native_owner_source',{}).get('records',{})
    missing=[]
    for name,e in nodes.items():
        if e['tag']=='grpSp' or verify_anchor(e):continue
        if name not in bound:
            policies=[p for p in state['quality_intent']['items'] if name in p['objects']]
            precise=min(policies,key=lambda p:len(p['objects'])) if policies else None
            missing.append({'object':name,'source_policy':precise['id'] if precise else None,
                'source_window':precise['source_view'] if precise else state['source'],
                'instruction':'Locate this painted primitive in the original. Freeze its own original bounds, source features and reliability, not the candidate frame.'})
    if not missing:return None
    return {'kind':'native_owner_source','action':'object-loop bind-source','source_hash':state['source']['sha256'],
            'items':missing[:8],'remaining':len(missing),'instruction':'All painted saved descendants require independent source-bound measurements on a first reconstruction; a root policy cannot silently supply these.'}

def owner_item(state,name,policy):
    bound=state.get('native_owner_source',{}).get('records',{}).get(name)
    if not bound:raise ValueError('Painted first-build owner lacks its independent original frame: '+name)
    return {**policy,'id':'native-owner:'+name,'objects':[name],'roi':bound['roi'],'source_facts':bound['source_facts'],
            'source_view':bound['source_view'],'source_evidence':bound['evidence']}

def bind_owner_source(task,request):
    from . import agent_runtime as a
    from .execution_contract import inventory
    from .native_connection_transaction import verify_anchor
    from .quality_intent import source_view
    task,state=a._state(task);candidate=state.get('active_candidate') or state['selected'];inv,_,nodes=inventory(task,state,candidate)
    if request.get('source_hash')!=state['source']['sha256']:raise ValueError('First-build native targets need the exact original source')
    rows=request.get('items',[])
    if not rows or len({r.get('object') for r in rows})!=len(rows):raise ValueError('Distinct named native original observations required')
    ledger=copy.deepcopy(state.get('native_owner_source',{'schema':VERSION,'records':{},'history':[]}))
    size=state['source_size']
    for row in rows:
        name=row.get('object');roi=row.get('roi')
        if set(row)-{'object','roi','source_facts','evidence','reliability','revision_reason'} or name not in nodes or nodes[name]['tag']=='grpSp' or verify_anchor(nodes[name]):raise ValueError('Source binding must name a painted actual owner')
        if not roi or len(roi)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in roi) or min(roi[2:])<=0 or min(roi[:2])<0 or roi[0]+roi[2]>size[0] or roi[1]+roi[3]>size[1]:raise ValueError('Independent owner original ROI is outside the source')
        if not row.get('source_facts') or not row.get('evidence') or row.get('reliability') not in ('observed','approximate','inferred'):raise ValueError('Original primitive facts/evidence and explicit reliability required')
        previous=ledger['records'].get(name)
        if previous and not row.get('revision_reason'):raise ValueError('An original owner target revision needs located original correction evidence')
        if previous:ledger['history'].append(previous)
        # _view crops only the immutable original, with source-relative bounds.
        record={**copy.deepcopy(row),'source_hash':state['source']['sha256'],'source_view':source_view(task,state,roi)}
        ledger['records'][name]=record
    with writer(task):
        state['native_owner_source']=ledger;state.pop('quality_result',None);state.pop('acceptance',None)
        a._event(task,'individual_native_original_targets_frozen',{'owners':[r['object'] for r in rows]});a._save(task,state)
    return {'status':'INDIVIDUAL_NATIVE_SOURCE_BOUND','owners':[r['object'] for r in rows]}

def owner_observation_packet(task,state,candidate):
    if state.get('quality_intent',{}).get('approved'):return None
    from .execution_contract import inventory
    from .native_connection_transaction import verify_anchor
    from .quality_observations import candidate_view,observation_basis
    _,_,nodes=inventory(task,state,candidate);ledger=state.get('native_owner_observations',{})
    rows=[]
    for name,e in nodes.items():
        if e['tag']=='grpSp' or verify_anchor(e):continue
        policies=[p for p in state['quality_intent']['items'] if name in p['objects']]
        item=owner_item(state,name,min(policies,key=lambda p:len(p['objects'])))
        basis=observation_basis(task,state,candidate,item);old=ledger.get(name)
        if old and old.get('basis')==basis and old.get('outcome')=='matched':continue
        rows.append({'object':name,'basis':basis,'source_view':item['source_view'],'candidate_view':candidate_view(task,state,candidate,item),
            'source_facts':item['source_facts']})
    return {'kind':'native_owner_observation','action':'object-loop observe','source_hash':state['source']['sha256'],
        'candidate_hash':candidate['pptx']['sha256'],'items':rows[:8],'remaining':len(rows)} if rows else None

def bind_owner_observations(task,request):
    from . import agent_runtime as a
    from .quality_observations import candidate_view,observation_basis
    task,state=a._state(task);candidate=state.get('active_candidate') or state['selected']
    if request.get('source_hash')!=state['source']['sha256'] or request.get('candidate_hash')!=candidate['pptx']['sha256']:raise ValueError('Independent native observation refers to other original/current files')
    rows=request.get('items',[])
    if not rows or len({r.get('object') for r in rows})!=len(rows):raise ValueError('Independent native observations required')
    ledger=copy.deepcopy(state.get('native_owner_observations',{}))
    for row in rows:
        name=row.get('object');policies=[p for p in state['quality_intent']['items'] if name in p['objects']]
        if not policies:raise ValueError('Unknown individual native owner')
        item=owner_item(state,name,min(policies,key=lambda p:len(p['objects'])));view=candidate_view(task,state,candidate,item);basis=observation_basis(task,state,candidate,item)
        if row.get('basis')!=basis or row.get('source_view_sha256')!=item['source_view']['sha256'] or row.get('candidate_view_sha256')!=view['sha256'] or row.get('outcome') not in ('matched','issue','uncertain') or not row.get('actual_facts') or not row.get('evidence'):raise ValueError('Own actual view and concrete primitive observation required')
        if name in ledger and ledger[name]!=row:state.setdefault('native_owner_observation_history',[]).append(ledger[name])
        ledger[name]=copy.deepcopy(row)
    with writer(task):
        state['native_owner_observations']=ledger;state.pop('quality_result',None);state.pop('acceptance',None)
        a._event(task,'individual_native_actual_observations',{'owners':[r['object'] for r in rows]});a._save(task,state)
    return {'status':'INDIVIDUAL_NATIVE_OBSERVATIONS_RECORDED','owners':[r['object'] for r in rows]}

def update_records(previous,rows,profile,*,expected):
    config=_config();ledger=copy.deepcopy(previous) if previous else {
        'schema':VERSION,'profile':profile,'units':{},'retired':{},'revisions':[]}
    if ledger.get('profile')!=profile:
        ledger.setdefault('revisions',[]).append({'profile':ledger.get('profile'),'units':copy.deepcopy(ledger['units'])})
        ledger['units']={};ledger['profile']=profile
    ids=[r['id'] for r in rows]
    if len(set(ids))!=len(ids) or set(ids)-set(expected):raise ValueError('Unexpected or duplicate independently registered object')
    for old in set(ledger['units'])-set(expected):ledger.setdefault('retired',{})[old]=ledger['units'].pop(old)
    for row in rows:
        row=copy.deepcopy(row)
        score=row.get('score')
        if score is not None and (type(score) not in (int,float) or not math.isfinite(score) or not 0<=score<=1):
            raise ValueError('Independent normalized rank is invalid')
        measurable=score is not None or (row.get('comparator')=='structural' and bool(row.get('structural_proof')))
        eligible=row.get('hard_pass') is True and bool(row.get('hard_checks')) and all(row['hard_checks'].values()) and measurable
        key=identity(row);unit=ledger['units'].setdefault(row['id'],{'id':row['id'],'kind':row['kind'],
            'objects':row['objects'],'history':[],'best_local':None,'best_in_context':None,'locks':{}})
        if not any(h['receipt']==key for h in unit['history']):unit['history'].append({'receipt':key,**row,'eligible':eligible})
        current={'receipt':key,**row,'eligible':eligible};unit['current']=current
        prior=unit.get('best_in_context');local=unit.get('best_local')
        ruler_changed=bool(prior and prior['metric_profile']!=row['metric_profile'])
        if ruler_changed:
            archived=unit.setdefault('profile_bests',{}).setdefault(prior['metric_profile'],{})
            if local and local['metric_profile']==prior['metric_profile']:archived['best_local']=copy.deepcopy(local)
            archived['best_in_context']=copy.deepcopy(prior)
            local=unit['profile_bests'].get(row['metric_profile'],{}).get('best_local')
            unit['best_local']=local
        same=prior and prior['context']==row['context'] and prior['metric_profile']==row['metric_profile']
        status='HARD_TARGETS_UNMET' if not row['hard_pass'] else 'REQUIRED_MEASUREMENT_MISSING'
        comparison='INELIGIBLE';regression=bool(same and not eligible)
        if regression:status='REGRESSION_REQUIRES_LOCAL_ROLLBACK';comparison='PRIOR_SATISFIED_FACET_REGRESSED'
        if eligible:
            regression=regression or bool(same and score is not None and prior.get('score') is not None and score<prior['score']-config['regression_tolerance'])
            if regression:
                status='REGRESSION_REQUIRES_LOCAL_ROLLBACK';comparison='RETAINED_PREVIOUS_UNIT_BEST'
            else:
                if not same:
                    unit['best_in_context']=current;comparison='NEW_RULER_RECHECKED' if ruler_changed else 'NEW_CONTEXT_RECHECKED' if prior else 'FIRST_ELIGIBLE'
                elif score is None or prior.get('score') is None or score>=prior['score']:
                    unit['best_in_context']=current;comparison='GAIN' if score is not None and prior.get('score') is not None and score>prior['score']+config['gain_tolerance'] else 'TARGET_MET'
                else:
                    # A tiny numerical difference is explicitly retained; it
                    # does not replace the historical best or imply a gain.
                    comparison='WITHIN_FIXED_NUMERIC_TOLERANCE'
                if local is None or (local['context']==row['context'] and local['metric_profile']==row['metric_profile'] and
                    (score is None or local.get('score') is None or score>=local['score'])):
                    unit['best_local']=current
                status='LOCKED'
        unit.update(status=status,comparison=comparison,converged=status=='LOCKED',
            regression=regression,locks={f:row['intrinsic'] for f in config['lock_facets']} if status=='LOCKED' else unit.get('locks',{}) if regression else {},
            convergence_reason='DECLARED_TARGETS_MET_CURRENT_CONTEXT_BEST' if status=='LOCKED' else status)
    missing=sorted(set(expected)-set(ids));unclosed=[u['id'] for u in ledger['units'].values() if not u.get('converged')]
    return {'schema':VERSION,'passed':not missing and not unclosed,'status':'CONVERGED' if not missing and not unclosed else 'OBJECT_WORK_REQUIRED',
        'expected':sorted(expected),'missing':missing,'unclosed':sorted(unclosed),'ledger':ledger,
        'limits':'Independent declared-target convergence; structural comparisons carry no invented pixel score. Context changes require new evidence and never claim comparable improvement.'}

def native_facets(file):
    """Separate intrinsic content/paint/geometry from permitted layout transforms."""
    from .inspect import xml,inventory
    tree=xml(file);nodes,duplicates=inventory(tree)
    if duplicates:raise ValueError('Ambiguous native identities cannot have independent bests')
    result={}
    with ZipFile(file) as z:
        import posixpath,hashlib
        rels={r.get('Id'):posixpath.normpath(posixpath.join('ppt/slides',r.get('Target',''))) for r in E.fromstring(z.read('ppt/slides/_rels/slide1.xml.rels')) if r.get('TargetMode')!='External'}
        for name,entry in nodes.items():
            original=entry['node'];node=copy.deepcopy(original)
            if E.QName(node).localname=='grpSp':
                for child in list(node.iterdescendants()):
                    if E.QName(child).namespace==NS['p'] and E.QName(child).localname in ('sp','grpSp','pic','cxnSp','graphicFrame') and child.getparent() is not None:child.getparent().remove(child)
            # The separate placement signature still binds these properties.
            for transform in list(node.findall('.//a:xfrm',NS))+list(node.findall('p:xfrm',NS)):
                transform.getparent().remove(transform)
            media={rid:hashlib.sha256(z.read(path)).hexdigest() for rid,path in rels.items() if path in z.namelist() and any(e.get('{'+NS['r']+'}embed')==rid for e in original.iter())}
            transforms=[E.tostring(e,method='c14n',exclusive=True).decode() for e in original.findall('.//a:xfrm',NS)+original.findall('p:xfrm',NS)]
            result[name]={'intrinsic':identity({'native':E.tostring(node,method='c14n',exclusive=True).decode(),'media':media}),
                'placement':identity({'transforms':transforms,'parent':entry.get('parent')}),'parent':entry.get('parent')}
    return result

def collect(task,state,candidate,plan,native_rows,appearance,legacy,host,gates):
    from .execution_contract import inventory,resource
    inv,scene,nodes=inventory(task,state,candidate);facets=native_facets(resource(task,candidate['pptx']))
    apps={r['id']:r for r in appearance};seen={r['id']:r for r in host};owners={r['object']:r for r in native_rows}
    artifact={k:copy.deepcopy(candidate[k]) for k in ('pptx','scene','preview','render')}
    metric_profile=identity({'intent':plan['compiled_hash'],'settings':_config()})
    placement={n:v['placement'] for n,v in facets.items()}
    # Context binds actual layout/occlusion and neighbor identity, but not a
    # neighbor's internally improved paint: independent A/B optimization stays
    # comparable when B changes only its own intrinsic content.
    context=identity({'source':state['source'],'layout':placement,'composition':state.get('semantic_composition'),
                      'relations':state.get('relative_layout'),'frame':state.get('frame_plan')})
    rows=[]
    def append(uid,kind,names,checks,measurement,policy_ids):
        metrics=copy.deepcopy(measurement.get('score_dimensions',{}));score=measurement.get('weighted_score')
        # A nonpaint group/port, a table cell or a tiny actual owner has a
        # structural comparator with exact observed invariants, not SSIM=1.
        own_nonpaint=kind=='native' and all(nodes[n]['tag']=='grpSp' or owners.get(n,{}).get('derived_port') for n in names)
        tiny=measurement.get('source_correspondence',{}).get('ssim_applicability')=='too_few_pixels_native_construction_remains_required'
        exact=kind=='table_cell' or kind in ('policy','source') and any(k in checks for k in ('exact_content','native_text_match','math_ast_match','native_cell_format_match'))
        from .native_core import owned
        scoped_native=owned(task,names) and measurement.get('native_core',{}).get('passed') is True
        structural=score is None and bool(names) and all(n in facets for n in names) and all(checks.values()) and (own_nonpaint or tiny or exact or scoped_native)
        proof={'native':{n:facets[n] for n in names},'checks':checks,'metric_applicability':measurement.get('weighted_score_status',measurement.get('status'))} if structural else None
        rows.append({'id':uid,'kind':kind,'objects':names,'hard_pass':all(checks.values()),'hard_checks':checks,
            'metrics':metrics,'raw_source_metrics':measurement.get('source_correspondence'), 'score':score,
            'comparator':'structural' if structural else 'purpose_weighted','structural_proof':proof,
            'metric_profile':metric_profile+':'+identity({'policies':policy_ids,'selected':measurement.get('selected_dimensions'),
                'independent_original_rulers':{n:state.get('native_owner_source',{}).get('records',{}).get(n) for n in names}}),
            'context':context,'intrinsic':identity({n:facets[n]['intrinsic'] for n in names}), 'candidate':artifact,
            'dependencies':policy_ids,'source_correspondence_is_diagnostic':True})
    policies={r['id']:r for r in plan['items']}
    for item in plan['items']:
        measurement=apps[item['id']];names=item['objects']
        checks={'purpose_hard_constraints':measurement.get('passed') is True,'source_semantics':seen.get(item['id'],{}).get('passed') is True,
                'native_descendants':all(owners.get(n,{}).get('passed') is True for n in names)}
        if item['purpose'] in ('text','formula'):checks['exact_content']=gates['text_math']['passed'] and gates['original_content_predicates']['passed']
        if item['purpose']=='relation':checks['connections']=gates['connection_geometry']['passed']
        append('policy:'+item['id'],'policy',names,checks,measurement,[item['id']])
    for name in inv['native_names']:
        actual=owners[name];applicable=[policies[p] for p in actual['policies']];most_precise=min(applicable,key=lambda r:len(r['objects'])) if applicable else None
        checks={'saved_native_and_own_measurement':actual['passed'],
                'own_source_semantics':actual.get('own_source_semantics',bool(most_precise and seen.get(most_precise['id'],{}).get('passed')))}
        ancestry={name};parent=inv['parents'].get(name)
        while parent:
            ancestry.add(parent);parent=inv['parents'].get(parent)
        related_clarity=[r for r in gates.get('icon_clarity',{}).get('items',[]) if r.get('category') in ('clear_icon','blurred_icon') and
                         ancestry & set(state.get('quality',{}).get('units',{}).get(r.get('unit'),{}).get('objects',[]))]
        if related_clarity:checks['hd_owner_appearance_preserved']=all(r.get('passed') is True for r in related_clarity)
        if nodes[name]['tag']=='grpSp':
            children=[n for n in inv['native_names'] if inv['parents'].get(n)==name]
            checks['every_direct_child_checked']=all(owners[c]['passed'] for c in children)
        append('native:'+name,'native',[name],checks,actual.get('appearance',{}),actual['policies'])
    source_by_id={r['unit']:r for r in legacy}
    for uid,unit in state.get('quality',{}).get('units',{}).items():
        related=[r for r in plan['items'] if uid in r['quality_units']];precise=min(related,key=lambda r:len(r['objects'])) if related else None
        measured=source_by_id.get(uid,{});measurement=apps.get(precise['id'],{}) if precise else {}
        checks={'original_numeric_measurement':measured.get('status') not in (None,'required_unmeasured') and all(c.get('status')!='required_unmeasured' for c in measured.get('constraints',[])),
            'active_purpose_constraints':measurement.get('passed') is True,
            'individual_source_semantics':bool(precise and seen.get(precise['id'],{}).get('passed'))}
        clarity=next((r for r in gates.get('icon_clarity',{}).get('items',[]) if r.get('unit')==uid),None)
        if clarity and clarity.get('category') in ('clear_icon','blurred_icon'):
            checks['hd_and_non_regressed_appearance']=clarity.get('passed') is True
        for c in measured.get('constraints',[]):
            if c['id'] in ('native_text_match','math_ast_match','native_cell_format_match'):checks[c['id']]=c.get('status') in ('minimum_met','stretch_met')
        append('source:'+uid,'source',precise['objects'] if precise else unit.get('objects',[]),checks,measurement,[r['id'] for r in related])
    for name,node in nodes.items():
        for index,cell in enumerate(node['node'].findall('.//a:tbl/a:tr/a:tc',NS)):
            literal=''.join(cell.itertext());checks={'native_cell_saved':bool(cell.find('a:txBody',NS) is not None),'exact_table_content':gates['text_math']['passed'] and gates['original_content_predicates']['passed']}
            append('cell:'+name+':'+str(index),'table_cell',[name],checks,{},['native:'+name])
            rows[-1]['intrinsic']=identity(E.tostring(cell,method='c14n',exclusive=True).decode());rows[-1]['cell_index']=index
    return rows

def report(task,state,candidate,plan,native_rows,appearance,legacy,host,gates):
    prior_ref=state.get('object_lifecycle_result')
    if prior_ref and (digest(safe_path(task,prior_ref['path']))!=prior_ref['sha256'] or read_json(safe_path(task,prior_ref['path']))!=state.get('object_lifecycle')):
        raise ValueError('Independent object lifecycle differs from its immutable program receipt')
    rows=collect(task,state,candidate,plan,native_rows,appearance,legacy,host,gates)
    profile=identity({'source':state['source'],'policy':plan['compiled_hash'],'configuration':_config()})
    from .execution_contract import inventory
    inv,_,nodes=inventory(task,state,candidate)
    expected={'native:'+n for n in inv['native_names']}|{'policy:'+r['id'] for r in plan['items']}|{'source:'+uid for uid in state.get('quality',{}).get('units',{})}
    expected|={'cell:'+name+':'+str(i) for name,e in nodes.items() for i,c in enumerate(e['node'].findall('.//a:tbl/a:tr/a:tc',NS))}
    result=update_records(state.get('object_lifecycle',{}),rows,profile,expected=expected)
    state['object_lifecycle']=result.pop('ledger')
    path=task/'audits'/('object-lifecycle-'+identity(state['object_lifecycle'])+'.json');write_json(path,state['object_lifecycle'])
    state['object_lifecycle_result']={'path':path.relative_to(task).as_posix(),'sha256':digest(path)}
    result.update(records=state['object_lifecycle_result'],current_candidate=candidate['pptx']['sha256'],
        regressions=[u['id'] for u in state['object_lifecycle']['units'].values() if u['regression']],
        locked=[u['id'] for u in state['object_lifecycle']['units'].values() if u['converged']])
    return result

def rollback_plan(state,requested=None):
    """Project aggregate debt onto actual regressed native owners.

    A policy/group's changed pixel score never grants replacement of every
    child. Restore a parent only if its own properties regressed and none of
    its descendants have independently retained improvements.
    """
    units=state.get('object_lifecycle',{}).get('units',{});requested=set(requested or units)
    scopes=set(n for uid in requested if uid in units for n in units[uid]['objects'])
    selected=[];blocked=[]
    for uid,unit in units.items():
        if unit['kind']!='native' or unit.get('status')!='REGRESSION_REQUIRES_LOCAL_ROLLBACK' or not unit.get('best_in_context'):continue
        name=unit['objects'][0]
        if uid not in requested and name not in scopes:continue
        best=unit['best_in_context'];now=unit['current']
        if now['intrinsic']==best['intrinsic']:
            # Context-pixel deterioration on an unchanged primitive is a
            # neighbor/layout debt, not permission to rewrite this object.
            continue
        proof=now.get('structural_proof') or {};kind=proof.get('native',{}).get(name,{})
        selected.append(uid)
    return {'units':sorted(selected),'aggregate_debts':sorted(uid for uid in requested if uid in units and units[uid].get('regression') and units[uid]['kind']!='native'),
        'instruction':'Only actual regressed native payloads may roll back. Aggregate/context conflicts remain located repair obligations; unrelated best children are protected.'}

def adoption_guard(task,state,candidate,grants):
    """Locks are real: unauthorized intrinsic changes cannot silently adopt."""
    if not state.get('object_lifecycle'):return {'passed':True,'blocking':[],'status':'LIFECYCLE_NOT_YET_MEASURED'}
    from .execution_contract import resource
    actual=native_facets(resource(task,candidate['pptx']));allowed=set(grants or {})
    # Existing grant dictionaries are target->fields. Quality aliases are
    # resolved to their exact bound owners, never all siblings.
    for target in list(allowed):
        unit=state.get('quality',{}).get('units',{}).get(target.removeprefix('quality:'))
        if unit:allowed.update(unit.get('objects',[]))
        if target in state.get('built',{}):allowed.update(o['id'] for o in state['built'][target].get('objects',[]))
    while True:
        children={n for n,v in actual.items() if v['parent'] in allowed}-allowed
        if not children:break
        allowed|=children
    blocking=[]
    for uid,unit in state['object_lifecycle']['units'].items():
        if unit['kind']!='native' or not unit.get('locks'):continue
        name=unit['objects'][0];prior=unit['current'].get('structural_proof',{} ) or {}
        prior_intrinsic=unit['current']['intrinsic'];value=identity({name:actual.get(name,{}).get('intrinsic')})
        if value!=prior_intrinsic and name not in allowed:blocking.append(uid)
    return {'passed':not blocking,'blocking':blocking,'status':'INTRINSIC_LOCKS_PRESERVED' if not blocking else 'LOCKED_OBJECT_OUTSIDE_WRITE_GRANTS'}

def checkpoint(task,state,candidate):
    """Measure every available unit before a finite action, retain failed history."""
    if not state.get('quality_intent') or not candidate or not candidate.get('render'):return None
    from .quality_loop import audit
    return audit(task,state,candidate,persist=False)['gates']['object_convergence']

def verify_current(task,state,candidate,plan):
    from .execution_contract import resource,inventory
    reference=state.get('object_lifecycle_result')
    if not reference or read_json(resource(task,reference))!=state.get('object_lifecycle'):raise ValueError('Current independent lifecycle is missing or differs from its immutable receipt')
    inv,_,nodes=inventory(task,state,candidate)
    expected={'native:'+n for n in inv['native_names']}|{'policy:'+p['id'] for p in plan['items']}|{'source:'+uid for uid in state.get('quality',{}).get('units',{})}
    expected|={'cell:'+name+':'+str(i) for name,e in nodes.items() for i,_ in enumerate(e['node'].findall('.//a:tbl/a:tr/a:tc',NS))}
    units=state['object_lifecycle']['units']
    if set(units)!=expected:raise ValueError('Final independent object set omits/duplicates a current semantic/native/cell obligation')
    for uid,unit in units.items():
        current=unit.get('current',{});best=unit.get('best_in_context')
        if not unit.get('converged') or unit.get('status')!='LOCKED' or not current.get('eligible') or not unit.get('locks') or not best or best['context']!=current['context'] or best['metric_profile']!=current['metric_profile']:
            raise ValueError('Final independent object is not converged with its current context best: '+uid)
        if any(current.get('candidate',{}).get(k)!=candidate.get(k) for k in ('pptx','scene','preview','render')):raise ValueError('An independent object record belongs to another current native/render context: '+uid)
    return {'passed':True,'expected':sorted(expected),'scope':'Exact set and current locked receipts, not an acceptance count'}

def rollback(task,request):
    """Restore only recorded local best payloads; do not discard other gains."""
    from . import agent_runtime as a
    from .execution_contract import resource
    from .inspect import xml,inventory
    from .native_snapshot import snapshot
    task,state=a._state(task);baseline=state.get('active_candidate') or state['selected'];before=identity(state)
    if set(request)-{'expected_baseline_sha256','units'} or request.get('expected_baseline_sha256')!=baseline['pptx']['sha256']:
        raise ValueError('Rollback needs current immutable candidate, not coordinates or XML')
    ids=request.get('units',[]);ledger=state.get('object_lifecycle',{}).get('units',{})
    if not ids or len(ids)!=len(set(ids)) or any(uid not in ledger for uid in ids):raise ValueError('Select existing independent unit records')
    projection=rollback_plan(state,ids);ids=projection['units']
    if not ids:raise ValueError('No intrinsically regressed native payload can safely roll back; repair the reported aggregate/context conflict')
    file=resource(task,baseline['pptx']);tree=xml(file);nodes,duplicates=inventory(tree)
    if duplicates:raise ValueError('Ambiguous rollback owner')
    replacements={};best_refs={};sources={}
    for uid in ids:
        unit=ledger[uid];best=unit.get('best_in_context')
        if not best or unit.get('status')!='REGRESSION_REQUIRES_LOCAL_ROLLBACK':raise ValueError('Rollback requires a measured regression and its independent context best')
        for name in unit['objects']:
            if name in best_refs and best_refs[name]!=best['candidate']['pptx']:raise ValueError('Conflicting independent context bests require dependency repair')
            best_refs[name]=best['candidate']['pptx']
    # Parent restore already restores its descendants; avoid double replacement.
    selected=set(best_refs)
    for name in sorted(selected):
        parent=nodes[name].get('parent')
        while parent and parent not in selected:parent=nodes[parent].get('parent')
        if parent:continue
        ref=best_refs[name];source=resource(task,ref);old,dup=inventory(xml(source))
        if dup or name not in old or old[name].get('parent')!=nodes[name].get('parent'):raise ValueError('Best payload moved to an incompatible parent; local context repair required')
        descendants={n for n in nodes if n!=name and _is_descendant(n,name,nodes)}
        if descendants:
            if any(n not in selected and nodes[n]['node'] is not None and E.tostring(nodes[n]['node'],method='c14n',exclusive=True)!=E.tostring(old[n]['node'],method='c14n',exclusive=True) for n in descendants):
                raise ValueError('Parent rollback would overwrite independently changed children; restore only its own properties or repair the context')
        # Relations/fonts/media must share exact identities; unsupported
        # resource rebinding stays diagnosed, never guessed or overwritten.
        with ZipFile(file) as current,ZipFile(source) as best_zip:
            if sorted(current.namelist())!=sorted(best_zip.namelist()) or any(current.read(n)!=best_zip.read(n) for n in current.namelist() if n!='ppt/slides/slide1.xml'):
                raise ValueError('Local rollback resource context differs; use the bound native-resource operator')
        replacements[name]=copy.deepcopy(old[name]['node']);sources[name]=ref
    for name,node in replacements.items():nodes[name]['node'].getparent().replace(nodes[name]['node'],node)
    output_dir=task/'versions'/('object-rollback-'+identity({'baseline':baseline['pptx'],'bests':sources})[:18]);output_dir.mkdir(exist_ok=True)
    output=output_dir/'drawing.pptx';payload=E.tostring(tree,encoding='utf-8',xml_declaration=True,standalone=True)
    if output.exists():
        with ZipFile(output) as z:
            if z.read('ppt/slides/slide1.xml')!=payload:raise ValueError('Existing rollback artifact differs; preserve it')
    else:
        with ZipFile(file) as z,ZipFile(output,'x',ZIP_DEFLATED,compresslevel=9) as out:
            for info in z.infolist():out.writestr(info,payload if info.filename=='ppt/slides/slide1.xml' else z.read(info.filename))
    scene=snapshot(task,state,output,read_json(resource(task,baseline['scene'])));scene_file=output_dir/'scene.json';write_json(scene_file,scene)
    candidate=copy.deepcopy(baseline);candidate.update(pptx={'path':output.relative_to(task).as_posix(),'sha256':digest(output)},scene={'path':scene_file.relative_to(task).as_posix(),'sha256':digest(scene_file)},allowed={n:['local_best_payload'] for n in replacements})
    candidate['prior_render']=candidate.pop('render');candidate.pop('preview',None);candidate['reason']={'kind':'independent_object_rollback','units':ids}
    record={'baseline':baseline['pptx']['sha256'],'baseline_artifact':{k:baseline[k] for k in ('pptx','scene','preview','render')},'candidate':candidate['pptx']['sha256'],'output':candidate['pptx'],'units':ids,'objects':sorted(replacements),'bests':sources,'status':'SAVED_REQUIRES_ACTUAL_RENDER'}
    with writer(task):
        if identity(a._state(task)[1])!=before:raise ValueError('Task changed while constructing local rollback')
        state.setdefault('object_rollback_attempts',[]).append(record);state['active_candidate']=candidate;state.update(scene=candidate['scene'],stage='host_render',packet=None)
        state.pop('acceptance',None);state.pop('quality_result',None);a._event(task,'independent_unit_rollback_saved',record);a._save(task,state)
    return record

def _is_descendant(name,parent,nodes):
    cursor=nodes[name].get('parent')
    while cursor:
        if cursor==parent:return True
        cursor=nodes[cursor].get('parent')
    return False

def rollback_guard(task,state,candidate,approved):
    from .source_layout_actions import _xml,guard as source_guard
    records={r['candidate']:r for r in state.get('object_rollback_attempts',[])};record=records.get(candidate['pptx']['sha256'])
    if not record:return {'passed':False,'objects':[]}
    before=record['baseline_artifact'];file=safe_path(task,before['pptx']['path']);tree,nodes=_xml(file)
    prior={'passed':True,'objects':[]} if before['pptx']==approved['pptx'] else source_guard(task,state,before,approved)
    # A regressed unit is the only authorized difference in the predecessor;
    # replay the resulting complete artwork and independently verify retained
    # intrinsic owners below. A bad predecessor cannot grant other edits.
    for name,ref in record['bests'].items():
        best=safe_path(task,ref['path'])
        if digest(best)!=ref['sha256']:raise ValueError('Recorded independent object best changed')
        _,old=_xml(best);replacement=copy.deepcopy(old[name]);nodes[name].getparent().replace(nodes[name],replacement)
    new=safe_path(task,candidate['pptx']['path']);actual,_=_xml(new)
    passed=E.tostring(tree,method='c14n',exclusive=True)==E.tostring(actual,method='c14n',exclusive=True)
    with ZipFile(file) as a,ZipFile(new) as b:passed &= sorted(a.namelist())==sorted(b.namelist()) and all(a.read(n)==b.read(n) for n in a.namelist() if n!='ppt/slides/slide1.xml')
    if not prior['passed']:
        old=native_facets(safe_path(task,approved['pptx']['path']));current=native_facets(new);names=set(record['objects'])
        # Preserve approved intrinsic properties of every other owner. Any
        # independent gain still needs its own explicit approved/source policy.
        passed &= all(current.get(n)==v for n,v in old.items() if n not in names)
    return {'passed':bool(passed),'objects':sorted(set(prior['objects'])|set(record['objects'])),'method':'exact_independent_unit_best_payload_replay','protected':'Complete native replay and unchanged resources; non-target owners retain their actual payloads.'}
