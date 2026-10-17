"""One deferred font review, same-language expansion and journaled font-only writes."""
import copy
from .common import identity, read_json, writer
from . import font_collection as collection


def basis(scene,state):
    from .font_contract import requests
    return identity({'source':state['source']['sha256'],'requests':sorted(collection.request_key(r) for r in requests(scene)),
                     'policy':collection.policy(),'explicit':state['objectives'].get('font_requests',{})})


def current(scene,state,ledger):
    value=ledger.get('font_review') or {}
    return value.get('status')=='COMPLETE' and value.get('basis')==basis(scene,state)


def locked(contract,ledger,owner):
    from .component_revision import overlap
    locks=[lock for record in ledger['components'].values() for lock in record.get('user_locks',[])]
    locks+=ledger.get('orphan_user_locks',[])
    return any(v['owner']==owner and (overlap(v['field'],['style','font']) or
               overlap(v['field'],['style','font_faces']) or overlap(v['field'],['content'])) for v in locks)


def packet(task,state,contract,ledger,candidate):
    from . import component_workflow as c
    from .font_contract import requests,user_family
    scene=read_json(c._resource(task,candidate['scene']));key=basis(scene,state)
    intents=requests(scene)
    collection.prepare(state)
    context=identity({'preview':candidate.get('preview'),'renderer':state['capabilities'].get('fingerprint'),
        'selection':{r['id']:collection.selection_context(state,r,True) for r in intents
                     if collection.role_language(r['role']) in ('zh','en')},
        'protected':{r['id']:bool(user_family(state,r)) or locked(contract,ledger,r['owner']) for r in intents},
        'bindings':scene.get('font_plan',{}).get('bindings',{})})
    previous=ledger.get('font_review_plan',{})
    if (previous.get('basis')==key and previous.get('pptx_hash')==candidate['pptx']['sha256']
            and previous.get('context')==context):
        return previous
    rows=[]
    for request in intents:
        lang=collection.role_language(request['role'])
        if lang not in ('zh','en'):continue
        binding=scene['font_plan']['bindings'][request['id']]
        protected=bool(user_family(state,request)) or locked(contract,ledger,request['owner'])
        rank=None if protected else collection.ranking(task,state,request,extend=True)
        decision=rank if rank and rank.get('status')=='FONT_SELECTION_DECISION_REQUIRED' else None
        rows.append({'request':request,'language':lang,'binding':binding,'protected':protected,
                     'ranking':None if decision else rank,'selection_decision':decision,
                     'source_samples_required':not protected and rank is None})
    plan={'basis':key,'source_hash':state['source']['sha256'],'pptx_hash':candidate['pptx']['sha256'],
          'context':context,'preview':candidate.get('preview'),'requests':rows,'collection_revision':collection.load(state['project']).get('revision'),
          'return':'phase=prepare with font_samples or font_constraints if needed; then phase=complete, evidence, changes[{request_id,comparison_ref}], source_hash, pptx_hash',
          'rule':'Review once after parts and layout. Only a better eligible same-language font can replace a binding. Exact user requests and user locks are preserved; archive selected new fonts before native mutation.'}
    ledger['font_review_plan']=plan
    return plan


def submit(task,request):
    from . import agent_runtime as a,component_workflow as c,font_contract as fonts
    from .component_protocol import ready_for_final,impact
    task,state=a._state(task);contract,ledger=c._load(task,state);candidate=c._candidate(state)
    if not ready_for_final(contract,ledger,state)['ready']:raise ValueError('Font review is deferred until parts and layout are ready')
    if request.get('source_hash')!=state['source']['sha256'] or request.get('pptx_hash')!=candidate['pptx']['sha256']:
        raise ValueError('Final font review must bind current original and native candidate')
    scene=read_json(c._resource(task,candidate['scene']))
    if current(scene,state,ledger):raise ValueError('This text intent already completed its one font review')
    if request.get('phase')=='prepare':
        collection.store_samples(task,state,scene,request.get('font_samples',{}))
        collection.store_constraints(task,state,scene,request.get('font_constraints',{}))
        ledger.pop('font_review_plan',None)
        with writer(task):c._save_ledger(task,state,ledger,'font_review_samples_prepared')
        return {'status':'FINAL_FONT_COMPARISONS_PREPARED','acceptance':False,'whole_audit_executed':False}
    if request.get('phase')!='complete':raise ValueError('Explicit final font review phase required')
    plan=packet(task,state,contract,ledger,candidate)
    if any(r.get('selection_decision') for r in plan['requests']):
        raise ValueError('Resolve the explicit font resource/narrowing decisions before completing the final review')
    if any(r['source_samples_required'] for r in plan['requests']):raise ValueError('Complete source glyph samples before the one final font decision')
    evidence=request['evidence'];observed=read_json(c._resource(task,evidence))
    if (observed.get('source_hash')!=state['source']['sha256'] or observed.get('pptx_hash')!=candidate['pptx']['sha256'] or
        observed.get('preview_hash')!=candidate.get('preview',{}).get('sha256') or
        observed.get('observer') not in ('host_model','human') or not observed.get('observations')):
        raise ValueError('Located original/current final typography observation required')
    by_id={r['request']['id']:r for r in plan['requests']};values=[];new_faces=[]
    changes=request.get('changes',[])
    if len({v['request_id'] for v in changes})!=len(changes):raise ValueError('Duplicate final font request')
    for change in changes:
        row=by_id[change['request_id']];intent=row['request'];prior=row['binding']
        if row['protected']:raise ValueError('Preserve user font authority and field locks')
        if change['comparison_ref']!=row['ranking']:raise ValueError('Use the prepared final font comparison')
        comparison=read_json(c._resource(task,row['ranking']))
        choices={f['id']:f for f in collection.eligible(state,intent,extend=True)}
        selected=choices[comparison['selected_resource']]
        collection.verify_choice(task,state,intent,selected,row['ranking'])
        scores={v['resource_id']:v['merit'] for v in comparison['candidates']}
        before=scores.get(prior['resource']['id']);after=scores[selected['id']]
        if selected['id']==prior['resource']['id']:raise ValueError('No font replacement was proposed')
        language_correction=False
        try:collection.assert_language(prior['resource'],intent['role'])
        except ValueError:language_correction=True
        if not language_correction:
            if before is None or not tuple(after)<tuple(before):raise ValueError('Final replacement must improve the same source-bound comparison')
            first=next((i for i,(x,y) in enumerate(zip(after,before)) if x!=y),None)
            if first is None or before[first]-after[first]<collection.policy()['minimum_improvement']:
                raise ValueError('Final font improvement is below the fixed comparison resolution')
        values.append({'request_id':intent['id'],'resource_id':selected['id'],'family':selected['family'],
            'origin':'raster_inference','status':'approximate','comparison_ref':row['ranking'],
            'alternatives':[v['family'] for v in comparison['candidates'] if v['resource_id']!=selected['id']][:4] or [prior['family']],
            'prior_binding_hash':identity(prior),'revision_reason':'One deferred source-bound font review',
            'synthetic_style':bool((intent['bold'] and selected['weight']<600) or intent['italic']!=selected['italic']),
            'evidence':{'source_hash':state['source']['sha256'],'roi':intent['roi'],
                        'description':observed['observations'],'style_description':'Original-bound final glyph comparison'}})
        new_faces.append(selected)
    # Existing used same-language faces also join the archive if an old task lacked them.
    used=[]
    for row in plan['requests']:
        try:collection.assert_language(row['binding']['resource'],row['request']['role'])
        except ValueError:
            if not any(v['request_id']==row['request']['id'] for v in values):
                raise ValueError('FONT_LANGUAGE_CONFLICT: explicitly reconcile a protected legacy font before final review')
        else:used.append(row['binding']['resource'])
    collection.archive(state['project'],used,'Retain all eligible fonts used at the final review')
    completed={'status':'COMPLETE','basis':plan['basis'],'evidence':evidence,'replacements':[v['request_id'] for v in values]}
    if not values:
        ledger['font_review']=completed
        with writer(task):c._save_ledger(task,state,ledger,'final_font_review_completed',{'replacements':0})
        return {'status':'FINAL_FONT_REVIEW_COMPLETE','native_write':False,'whole_audit_executed':False}
    collection.archive(state['project'],new_faces,'Better same-language fonts selected in the single final review')
    owners={by_id[v['request_id']]['request']['owner'] for v in values}
    allowed={owner:['style.font'] for owner in owners}
    # Build a detached binding plan; no active task binding changes before the native journal.
    keys=('project','source','objectives','capabilities','font_contract','font_samples','font_rankings',
          'font_constraints','source_font_metadata')
    working={key:copy.deepcopy(state[key]) for key in keys if key in state}
    working['font_pending_candidate']={'allowed':allowed}
    fonts.bind(task,working,scene,values,persist=False)
    updated=fonts.bind_scene(task,working,scene)
    changed={row['id']:['paint'] for row in contract['components'] if owners.intersection(row['owners'])}
    affected=impact(contract,changed)
    from .component_constructor import construct
    post={'font_review':completed,'state_updates':{key:working[key] for key in ('font_contract','font_collection')},
          'statuses':{name:'RECHECK_REQUIRED' for name in affected['components']},
          'drop_instantiation':affected['components'],'relations_remove':affected['relations'],'layout_dirty':True}
    saved=construct(task,state,updated,candidate,allowed,
        {'kind':'component_final_fonts','revision_components':sorted(changed),'post_save':post})
    return {'status':'FINAL_FONTS_SAVED_LOCAL_RECHECK_REQUIRED','candidate':saved,'whole_audit_executed':False}
