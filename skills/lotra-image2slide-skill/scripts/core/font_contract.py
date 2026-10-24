"""Source/user intent, private font resource and compiled run binding are distinct.

Every new native text owner goes through this module, including table cells and
math. No current-environment font is evidence of the original's exact family.
"""
import copy
import shutil
import unicodedata
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from .common import digest, identity, read_json, safe_path, write_json
from . import font_resources as resources
from . import font_resolution as resolution

VERSION = 'font-contract-1'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'


def script(char):
    from .font_collection import language
    return {'zh':'ea','en':'latin','unsupported':'cs'}[language(char)]


def payloads(scene):
    """Yield native owner, stable location, writable style and original literals."""
    from .mathml import math_node
    def math_literal(ast, style):
        nodes = math_node(ast, style.get('math_font', style.get('font', 'Cambria Math')),
                          style.get('font_size', 16), style.get('math_font_policy', 'native_math'))
        return ''.join(t for node in nodes for t in node.itertext())
    for obj in scene['objects']:
        content, style = obj['content'], obj['style']
        kind = obj['render_type']
        if kind == 'equation':
            effective=style
            yield obj, 'equation', style, math_literal(content['ast'], effective), True
        elif kind == 'text':
            paragraphs = content.get('paragraphs')
            if paragraphs is None:
                if 'runs' in content:
                    paragraphs = [content['runs']]
                else:
                    yield obj, 'text', style, content.get('text', ''), False
                    continue
            for pi, paragraph in enumerate(paragraphs):
                for ri, run in enumerate(paragraph):
                    effective = {**style, **run}
                    if 'ast' in run:
                        yield obj, 'p'+str(pi)+'.r'+str(ri), run, math_literal(run['ast'], effective), True
                    else:
                        yield obj, 'p'+str(pi)+'.r'+str(ri), run, run.get('text', ''), False
        elif kind == 'table':
            rows = content.get('rows', [])
            formats = content.get('cell_styles')
            if formats is None:formats=[[{} for _ in row] for row in rows]
            for ri, row in enumerate(rows):
                for ci, literal in enumerate(row):
                    yield obj, 'cell.'+str(ri)+'.'+str(ci), formats[ri][ci], literal, False


def requests(scene, state=None):
    if state is not None and state.get('task_id') and not resolution.enabled(state) and resolution.enabled(scene=scene):
        raise ValueError('FONT_POLICY_MIGRATION_REQUIRED: a Scene flag cannot migrate an existing task')
    result = []
    for obj, location, leaf, literal, math in payloads(scene):
        style = resolution.merge_style(obj['style'], leaf)
        groups = {'math': literal} if math else {}
        if math:
            from .font_collection import language
            if any(language(c)=='zh' for c in literal):
                raise ValueError('FONT_LANGUAGE_SPLIT_REQUIRED: expose Chinese formula annotations as explicitly bound Chinese text runs/owners; the mathematical font cannot bypass language classification')
            # The existing OMML isolated-comma operator intentionally names a
            # second real font. Bind/ship it rather than relying on fallback.
            ast=leaf.get('ast',obj['content'].get('ast'))
            if ast is not None and style.get('math_font_policy')=='isolated_script_comma':
                from .mathml import math_node
                primary=style.get('math_font',style.get('font','Cambria Math'))
                for node in math_node(ast,primary,style.get('font_size',16),'isolated_script_comma'):
                    for run in node.iter('{http://schemas.openxmlformats.org/officeDocument/2006/math}r'):
                        font=run.find('.//{'+A+'}latin')
                        if font is not None and font.get('typeface')!=primary:
                            role='math_aux:'+font.get('typeface')
                            groups[role]=groups.get(role,'')+''.join(run.itertext())
        if not math:
            for char in literal:
                if not char.isspace():
                    role = script(char)
                    groups[role] = groups.get(role, '')+char
        for role, characters in groups.items():
            if not characters.strip():
                continue
            default = 'Cambria Math' if math else 'DejaVu Sans'
            proposed = style.get('math_font', style.get('font', default)) if math else style.get('font', default)
            if role.startswith('math_aux:'):proposed=role.split(':',1)[1]
            token = {'owner': obj['id'], 'location': location, 'role': role}
            result.append({**token, 'id': identity(token), 'characters': ''.join(sorted(set(characters))),
                'literal_hash': identity(literal), 'proposed_family': proposed,
                'bold': False if role.startswith('math_aux:') else bool(style.get('bold', False)),
                'italic': role=='math_style:italic' if role.startswith('math_style:') else False if role.startswith('math_aux:') else bool(style.get('italic', False)),
                'roi': obj['bbox'], 'semantic_type': obj['semantic_type']})
            if resolution.enabled(state, scene):
                intent = style.get('font_intent', {})
                if not isinstance(intent, dict) or set(intent)-{'required_families','revision'}:
                    raise ValueError('Font intent accepts required_families and an explicit revision only')
                if 'revision' in intent and (not isinstance(intent['revision'],str) or not intent['revision'].strip() or len(intent['revision'])>240):
                    raise ValueError('Font intent revision needs a bounded nonempty source decision identity')
                required = intent.get('required_families', {})
                if not isinstance(required, dict) or set(required)-{'latin','ea','cs','math'} or any(not isinstance(v,str) or not v for v in required.values()):
                    raise ValueError('Exact font intent needs nonempty script-specific families')
                explicit = (state or {}).get('objectives', {}).get('font_requests', scene.get('font_plan', {}).get('user_font_requests', {}))
                owner = explicit.get(obj['id'], {})
                demanded = (owner.get(role) if isinstance(owner, dict) else None) or explicit.get(role) or required.get(role)
                overrides=(state or {}).get('font_intent_overrides',scene.get('font_plan',{}).get('intent_overrides',{}))
                demanded=overrides.get(result[-1]['id'],demanded)
                if role.startswith('math_aux:'):demanded=proposed
                result[-1].update(identity_policy=resolution.POLICY, required_family=demanded,
                    intent_revision=intent.get('revision'), proposed_faces=copy.deepcopy(style.get('font_faces',{})))
    return result


def _request_match(binding, request):
    value=resolution.request_value(request)
    # A native mirror may replace the author's hint by its already bound
    # canonical spelling. This is not a different family or a new font intent.
    if request.get('identity_policy')!=resolution.POLICY and resources.matches(binding['resource'],value['proposed_family']):
        value['proposed_family']=binding['request']['proposed_family']
    return binding.get('request_hash') == identity(value)


def required(state):
    return state.get('objectives', {}).get('source_font_contract', True) is True


def missing(scene, state):
    bindings = state.get('font_contract', {}).get('bindings', {})
    from .font_collection import assert_language
    result=[]
    for r in requests(scene,state):
        bound=bindings.get(r['id'])
        if not bound or not _request_match(bound,r):result.append(r);continue
        try:assert_language(bound['resource'],r['role'])
        except ValueError:result.append(r)
        else:
            if resolution.enabled(state):
                from .font_selection import require_binding
                try:require_binding(state,r,bound['resource'],bound.get('origin'),bound.get('synthetic_style',False))
                except ValueError:result.append(r)
    return result


def user_family(state,request):
    explicit=state.get('objectives',{}).get('font_requests',{})
    owner=explicit.get(request['owner'],{})
    role='math' if request['role'].startswith('math_style:') else request['role']
    return (owner.get(role) if isinstance(owner,dict) else None) or explicit.get(role)


def requested_family(state,request):
    return user_family(state,request) or request.get('required_family')


def pending_state(state):
    """Binding decisions stay detached until the existing native journal saves."""
    pending=state.get('font_pending_candidate') or {}
    if not pending.get('staged_font_contract'):return state
    return {**state,'font_contract':copy.deepcopy(pending['staged_font_contract'])}


def revision_details(task,state,scene,request):
    prior=state.get('font_contract',{}).get('bindings',{}).get(request['id'])
    if not prior:return {'operation':'initial_binding'}
    pending=state.get('font_pending_candidate') or {}
    fields=(pending.get('allowed') or {}).get(request['owner'],[])
    node=next(n for n in scene['objects'] if n['id']==request['owner'])
    location=request['location']
    if location.startswith('p'):
        paragraph,run=map(int,location[1:].split('.r'))
        path=['content','paragraphs',paragraph,run,'font'] if 'paragraphs' in node['content'] else ['content','runs',run,'font']
    elif location.startswith('cell.'):
        row,column=map(int,location.split('.')[1:]);path=['content','cell_styles',row,column,'font']
    else:path=['style','math_font' if location=='equation' else 'font']
    candidates=[path,path[:-1]+['font_intent','required_families',request['role']],
                ['style','font_intent','required_families',request['role']],
                path[:-1]+['font_intent','revision'],['style','font_intent','revision']]
    if request.get('required_family') and not user_family(state,request):path=candidates[1]
    elif request.get('intent_revision'):path=candidates[3]
    grants=(pending.get('reason') or {}).get('font_revision_grants',[])
    semantic=any(g['owner']==request['owner'] and any(field[:len(g['field'])]==g['field'] for field in candidates) for g in grants)
    authorized='style.font' in fields or 'replace_component' in fields or 'add' in fields or semantic
    locked=False
    if state.get('component_workflow'):
        from . import component_workflow as c
        _,ledger=c._load(task,state)
        from .component_revision import overlap
        locks=[v for row in ledger['components'].values() for v in row.get('user_locks',[])]+ledger.get('orphan_user_locks',[])
        locked=any(v['owner']==request['owner'] and (overlap(v['field'],path) or
            overlap(v['field'],['style','font']) or overlap(v['field'],['style','font_faces'])) for v in locks)
    return {'operation':'revise_binding','prior_binding_hash':identity(prior),'prior_family':prior['family'],
        'native_fields':fields,'font_field':path,'authorized':authorized and not locked,
        'blocker':'USER_LOCK_CONFLICT' if locked else None if authorized else 'FONT_REVISION_GRANT_REQUIRED',
        'required_fields':['prior_binding_hash','revision_reason','comparison_ref'],
        'recovery':'Preserve the binding; return to the located source decision to authorize this font field.' if not authorized or locked else None}


def packet(task, state, scene):
    rows = missing(scene, state)
    if not rows:
        return None
    from . import font_collection as collection
    collection.prepare(state)
    from . import font_selection as selection
    modern=resolution.enabled(state,scene)
    steps={row['id']:selection.required_step(state,row) for row in rows} if modern else {}
    step=min(steps.values(),key=selection.STEPS.index) if modern else None
    selected = ([row for row in rows if steps[row['id']]==step] if modern else rows)[:4 if modern else 8]
    per_request={r['id']:collection.eligible(state,r) for r in selected}
    faces=list({f['id']:f for values in per_request.values() for f in values}.values())
    catalogue = Path(task)/'source/font-options.json'
    options = [{'id': f['id'], 'family': f['family'], 'aliases': f['aliases'], 'weight': f['weight'],
                'italic': f['italic'], 'hosts': f['hosts'], 'editable_embedding': f['editable_embedding'],
                'outline': f['outline'], 'variable': f['variable'],'style_class':f.get('style_class','unknown')} for f in faces]
    write_json(catalogue, {'environment_key': state['capabilities']['fonts']['environment_key'], 'faces': options})
    result={'reference': 'references/font-collections-v132.md', 'source_hash': state['source']['sha256'],
            'requests': [dict(r,binding_revision=revision_details(task,state,scene,r)) for r in selected], 'remaining': len(rows),
            'revision_recovery_return':'For a revision blocker: font_revision_decision{request_ids,reason,evidence:{path,sha256}} retains this plan and returns its owners to the source-decision packet; never remove locks or edit grants by hand.',
            'language_candidates':{key:[f['id'] for f in values] for key,values in per_request.items()},
            'font_collection':state['font_collection'],
            'source_glyph_rankings':{r['id']:collection.ranking(task,state,r) for r in selected if collection.role_language(r['role']) in ('zh','en')},
            'inferred_binding_evidence':{'required':['comparison_ref.path','comparison_ref.sha256'],
                'take_from':'this packet source_glyph_rankings[request_id]',
                'rule':'Raster inference requires the current registered ranking reference. proposed_resources are recipe-family hints, not the physical resource lookup used by bind.'},
            'sample_return':'font_samples{request_id:[{character,roi}]}; selection decisions accept font_constraints{request_id:{style_classes?,resource_ids?,reason,evidence}}; prepare before binding',
            'user_font_requests': state['objectives'].get('font_requests', {}),
            'resource_catalogue': {'path': catalogue.relative_to(task).as_posix(), 'sha256': digest(catalogue)},
            'exact_resources': {r['id']: [f for f in options if user_family(state,r)
                                  and f['id'] in {v['id'] for v in per_request[r['id']]}
                                  and resources.name_key(user_family(state,r)) in {resources.name_key(n) for n in f['aliases']}][:6] for r in selected},
            'proposed_resources': {r['id']: [f for f in options if f['id'] in {v['id'] for v in per_request[r['id']]} and resources.name_key(r['proposed_family'])
                                  in {resources.name_key(n) for n in f['aliases']}][:6] for r in selected},
            'source_reading': 'Use only language_candidates for this request. Submit independently isolated original font_samples first. The program returns a registered source-bound ranking of eligible real resources; inferred binding selects its closest face. Availability and proposed recipe families are not original identity evidence.',
            'return': 'font_bindings[{request_id,family,resource_id,origin:user|source_metadata|raster_inference,status:exact|approximate,evidence:{source_hash,roi,description},alternatives?,comparison_ref?,synthetic_style?,prior_binding_hash?,revision_reason?}]',
            'rule': 'Available fonts are resources, not source evidence. User-specified exact identity dominates scores. Raster inference needs original glyph evidence and alternatives; uncertain inference stays approximate. Never alias different typefaces or silently replace a missing family.'}
    if modern:
        result.update(selection.batch(selected,step,state))
        result['reference']='references/font-workflow-v1374.md'
        result['last_submission']=state.get('font_submission_receipt')
        result['source_style_groups']={key:copy.deepcopy(value) for key,value in state.get('font_groups',{}).items()
            if any(row['id'] in value.get('members',{}) for row in selected)}
        result['step_return']={
            'source_style':'font_constraints{request_id:{style_classes|resource_ids,style_group?,reason,evidence}}; observe the original style before selecting fonts. Colour changes alone do not split a group.',
            'resource_decision':'font_constraints with current eligible resource_ids or explicit synthetic_style:true and style_description plus original evidence. Preserve unavailable exact user fonts; never substitute another family.',
            'glyph_samples':'font_samples{request_id:[{character,roi}]}; samples belong to each current original text owner.',
            'family_choice':'font_constraints{request_id:{family,comparison_ref,reason,evidence}}; choose a source-supported family from the current comparison. The choice applies to its declared source style group; uncertainty remains approximate.',
            'bind':'font_bindings for the visible request_ids using the current prepared comparison and any prior_binding_hash. Adoption waits for the native save.'}[step]
        result['source_reading']=result['step_return']
        from . import font_family
        if font_family.enabled(state):
            result['family_gate']={'policy':font_family.POLICY,
                'reference':'references/font-family-gate-v1375.md',
                'rule':'Use Chinese display names for Chinese choices. One inferred visual family is sufficient; bind a real eligible face and keep it by default. Fine refinement is optional and deferred.'}
            result['display_candidates']={row['id']:[{'resource_id':face['id'],**font_family.labels(state,row,face)}
                for face in per_request[row['id']]] for row in selected if collection.role_language(row['role']) in ('zh','en')}
        if state.get('typography_policy'):
            from .typography_measurement import propose_samples
            literals={(obj['id'],loc):literal for obj,loc,leaf,literal,is_math in payloads(scene) if not is_math}
            result['size_sample_suggestions']={row['id']:propose_samples(task,state,row,literals.get((row['owner'],row['location']),''))
                for row in selected if collection.role_language(row['role']) in ('zh','en')}
    else:
        from .font_migration import offer
        result['font_policy_migration']=offer(task,state,scene)
    return result


def retain_revision_decision(task,state,scene,packet,request):
    """Exit an unauthorized binding packet through an evidenced source decision."""
    from . import component_workflow as c
    contract,ledger=c._load(task,state);pending=state['font_pending_candidate']
    ids=set(request.get('request_ids',[]));rows={r['id']:r for r in packet['requests']}
    if not ids or not ids<=set(rows) or not request.get('reason'):raise ValueError('Locate the current font revision requests and reason')
    if any(revision_details(task,state,scene,rows[key]).get('authorized',True) for key in ids):
        raise ValueError('Source redecision is for an explicit font revision blocker')
    observed=read_json(c._resource(task,request['evidence']))
    expected=(pending.get('baseline') or {}).get('pptx',{}).get('sha256')
    if (observed.get('source_hash')!=state['source']['sha256'] or observed.get('pptx_hash')!=expected or
            observed.get('observer') not in ('human','host_model') or not observed.get('observations')):
        raise ValueError('Font redecision needs current located original/native observations')
    retained={'pending':copy.deepcopy(pending),'decision':copy.deepcopy(request),'source_hash':state['source']['sha256']}
    file=Path(task)/'work'/('font-redecision-'+identity(retained)+'.json');write_json(file,retained)
    if ledger.get('pending_transaction'):
        from .component_transactions import recover
        recover(task,{'action':'retain_and_redecide','reason':request['reason'],'evidence':request['evidence']})
        from .agent_runtime import _state
        task,state=_state(task)
        contract,ledger=c._load(task,state)
    owners={rows[key]['owner'] for key in ids}
    structural=ledger.get('structural_grant')
    if structural and structural.get('pptx_hash')==expected and owners.intersection(v['owner'] for v in structural['fields']):
        owners.update(v['owner'] for v in structural['fields'])
        ledger.setdefault('retained_structural_grants',[]).append(copy.deepcopy(structural));ledger.pop('structural_grant',None)
    for row in contract['components']:
        if owners.intersection(row['owners']):ledger['components'][row['id']]['status']='SOURCE_DECISION_REQUIRED'
    ledger.setdefault('font_redecision_history',[]).append(c._ref(task,file))
    state.pop('font_pending_candidate',None);state.update(stage='review',packet=None)
    c._save_ledger(task,state,ledger,'font_revision_source_decision_required',{'retained':c._ref(task,file)})
    return {'status':'FONT_SOURCE_DECISION_REQUIRED','acceptance':False,'pending_plan_retained':True}


def bind(task, state, scene, values, *, persist=True):
    resolution.verify_source_spans(task,state,scene)
    rows = {r['id']: r for r in requests(scene,state)}
    from . import font_collection as collection
    collection.prepare(state)
    faces = {f['id']: f for f in resources.available(state['capabilities'])}
    faces.update(collection.load(state['project'])['faces'])
    ledger = copy.deepcopy(state.get('font_contract') or {'version': VERSION, 'bindings': {}, 'history': []})
    if not isinstance(values, list) or not values:
        raise ValueError('Answer the current source font requests')
    accepted = {};archive_faces=[]
    for value in values:
        request = rows.get(value.get('request_id'))
        face = faces.get(value.get('resource_id'))
        if request is None or face is None or not resources.matches(face, value.get('family', '')):
            raise ValueError('Bind an exact current request and a real matching font resource')
        collection.assert_language(face,request['role'])
        language=collection.role_language(request['role'])
        origin, status = value.get('origin'), value.get('status')
        if origin not in ('user', 'source_metadata', 'raster_inference','compiler') or status not in ('exact', 'approximate'):
            raise ValueError('Separate font provenance from identity certainty')
        evidence = value.get('evidence', {})
        if evidence.get('source_hash') != state['source']['sha256'] or not evidence.get('description') or not evidence.get('roi'):
            raise ValueError('Font choice needs original-bound evidence')
        demanded = requested_family(state,request)
        if demanded and (not resources.matches(face, demanded) or status != 'exact'):
            raise ValueError('A requested exact font cannot be replaced by a better-scoring style peer')
        if origin == 'user' and not user_family(state,request):
            raise ValueError('User-font provenance must match the frozen task font_requests')
        if origin=='compiler' and (not request['role'].startswith('math_aux:') or not resources.matches(face,request['proposed_family'])):
            raise ValueError('Compiler font provenance is restricted to a real existing OMML auxiliary run')
        if origin == 'source_metadata':
            ref = value.get('source_metadata_ref', {})
            if not ref or ref not in state.get('source_font_metadata', []):
                raise ValueError('Raster input has no exact font metadata; bind a separately supplied source metadata resource')
        if origin == 'raster_inference':
            if status != 'approximate':
                raise ValueError('Raster-selected font identity remains inferred; do not invent exact font metadata')
            ref = value.get('comparison_ref') or {}
            if not isinstance(ref,dict) or not ref.get('path') or not ref.get('sha256'):
                raise ValueError('FONT_COMPARISON_REFERENCE_REQUIRED: '+request['id']+' needs comparison_ref {path,sha256} from current source_glyph_rankings[request_id]; recipe proposed_resources do not resolve this evidence')
            comparison_file = safe_path(task,ref.get('path', ''))
            if not comparison_file.resolve().is_relative_to(Path(task).resolve()) or not comparison_file.is_file() or digest(comparison_file) != ref.get('sha256'):
                raise ValueError('Inferred font needs a task-local source-bound font-gallery ranking')
            comparison = read_json(comparison_file)
            if language in ('zh','en'):collection.verify_choice(task,state,request,face,ref)
            if not value.get('alternatives') and not (comparison.get('schema')=='language-font-ranking-1' and len(comparison.get('candidates',[]))==1):
                raise ValueError('Retain actual alternatives, or the program proof that only one eligible face exists')
            selected = comparison.get('selected_style', {})
            if comparison.get('source_hash') != state['source']['sha256'] or not resources.matches(face, selected.get('font', '')):
                raise ValueError('Font-gallery choice belongs to another original/family')
        if face['variable'] or not face['editable_embedding']:
            raise ValueError('Chosen font needs a static resource allowing editable embedding; do not silently substitute')
        missing_glyphs = resources.coverage(face, request['characters'])
        if missing_glyphs:
            raise ValueError('Bound font is missing glyphs: '+repr(missing_glyphs))
        synthetic = bool(value.get('synthetic_style'))
        from .font_selection import require_binding, adopt_visual_family
        require_binding(state,request,face,origin,synthetic)
        if (not request['bold'] and face['weight']>=600) or (not request['italic'] and face['italic']):
            raise ValueError('A bold/italic-only resource cannot pretend to be the regular upright face')
        if synthetic and not evidence.get('style_description') and origin not in ('user','compiler'):
            raise ValueError('Synthetic weight/slant needs separate original style evidence')
        if ((request['bold'] and face['weight'] < 600) or request['italic'] != face['italic']) and not synthetic:
            raise ValueError('Weight/italic needs the real face, or explicitly source-supported synthetic_style')
        if not resolution.style_feasible(face,request,synthetic):
            raise ValueError('Font resource does not satisfy the current native style plan')
        if request['role'].startswith('math_style:'):
            primary_id=identity({'owner':request['owner'],'location':request['location'],'role':'math'})
            primary=accepted.get(primary_id) or ledger['bindings'].get(primary_id)
            if primary is None or primary['family']!=face['family']:
                raise ValueError('A native math style must use the already selected primary family')
        # Retain only a used private resource. This is not an OS font install.
        snapshot = Path(state['project'])/'.lotraAI-build/toolchain/font-snapshots'/(face['file_sha256']+Path(face['path']).suffix.lower())
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        if not snapshot.exists():
            shutil.copyfile(face['path'], snapshot)
        if digest(snapshot) != face['file_sha256']:
            raise ValueError('Private font snapshot identity differs')
        face = {**face, 'snapshot': {'path': snapshot.relative_to(state['project']).as_posix(), 'sha256': face['file_sha256']},
                'path': str(snapshot)}
        record = {'request': request, 'request_hash': resolution.request_key(request),
                  'family': face['family'], 'resource': face, 'origin': origin, 'status': status,
                  'evidence': copy.deepcopy(evidence), 'alternatives': value.get('alternatives', []),
                  'synthetic_style': synthetic,'comparison_ref':copy.deepcopy(value.get('comparison_ref')),
                  'source_metadata_ref':copy.deepcopy(value.get('source_metadata_ref')),
                  'environment_key': state['capabilities']['fonts']['environment_key']}
        if language in ('zh','en'):
            from .font_family import labels
            record.update(labels(state,request,face))
        prior = ledger['bindings'].get(request['id'])
        changed=prior and (prior['family'] != record['family'] or request.get('identity_policy')==resolution.POLICY and
            (prior['request_hash']!=record['request_hash'] or prior['resource']['id']!=record['resource']['id'] or
             prior.get('synthetic_style',False)!=record['synthetic_style']))
        if changed:
            revision=revision_details(task,state,scene,request)
            if not revision['authorized']:raise ValueError(revision['blocker']+': '+request['owner']+'/'+request['location'])
            if value.get('prior_binding_hash')!=identity(prior):raise ValueError('FONT_REVISION_STALE_BINDING: use this packet\'s prior_binding_hash')
            allowed_origins=('raster_inference','user','source_metadata','compiler') if request.get('identity_policy')==resolution.POLICY else ('raster_inference',)
            if not value.get('revision_reason') or origin not in allowed_origins:
                raise ValueError('FONT_REVISION_EVIDENCE_REQUIRED: explicit original-bound reason and valid source provenance required')
            ledger['history'].append({'prior':prior,'request':request['id'],'reason':value['revision_reason']})
        accepted[request['id']] = record
        if language in ('zh','en'):archive_faces.append(face)
    # Adopt implicit one-family decisions only after every submitted comparison
    # has been checked against the same pre-batch state.
    for bound in accepted.values():
        adopt_visual_family(state,bound['request'],bound['resource'],bound['origin'])
    from .font_selection import check_group_bindings
    check_group_bindings(state,{**ledger['bindings'],**accepted})
    collection.archive(state['project'],archive_faces,'Bind source-qualified eligible language fonts')
    ledger['bindings'].update(accepted)
    ledger['history'].append({'source_hash': state['source']['sha256'], 'accepted': sorted(accepted)})
    if persist:write_json(Path(task)/'source/font-bindings.json', ledger)
    state['font_contract']=ledger


def compile_scene(scene, state=None):
    from .tables import normalize_scene
    scene = normalize_scene(scene)
    from .typography_units import canonicalize as canonical_typography
    scene = canonical_typography(scene)
    if state is not None:
        bindings = state.get('font_contract', {}).get('bindings', {})
    else:
        plan = scene.get('font_plan', {})
        if plan.get('version') != VERSION and requests(scene):
            raise ValueError('FONT_BINDING_REQUIRED: native text/math/table must have a source/user font plan before build')
        bindings = plan.get('bindings', {})
    request_rows = {r['id']: r for r in requests(scene,state)}
    verified={}
    for key, request in request_rows.items():
        bound = bindings.get(key)
        if not bound or not _request_match(bound, request):
            raise ValueError('FONT_BINDING_REQUIRED: '+request['owner']+'/'+request['location']+'/'+request['role'])
        bound = copy.deepcopy(bound)
        if state is not None and bound['resource'].get('snapshot'):
            from .common import safe_path
            bound['resource']['path'] = str(safe_path(state['project'], bound['resource']['snapshot']['path']))
            bindings = {**bindings, key: bound}
        resource=bound['resource']
        from .font_collection import assert_language
        assert_language(resource,request['role'])
        key=(resource['path'],resource['face_index'])
        if key not in verified:
            file_hash=digest(resource['path'])
            if file_hash!=resource['file_sha256']:raise ValueError('Bound font bytes changed')
            verified[key]=resources.describe(resource['path'],resource['face_index'],file_hash)
        if not resources.matches_bound(verified[key],resource):
            raise ValueError('Bound font identity changed; refresh resources without changing the source intent')
    resources.require_embedding_slots(bindings[key] for key in request_rows)
    owner_faces={};resolved_runs={}
    for request in request_rows.values():
        owner_faces.setdefault(request['owner'],{}).setdefault(request['role'],set()).add(bindings[request['id']]['family'])
    owner_defaults={owner:{role:next(iter(names)) for role,names in roles.items() if len(names)==1}
                    for owner,roles in owner_faces.items()}
    previous=scene.get('font_plan',{})
    declared_faces=copy.deepcopy(previous.get('declared_faces',{}))
    for obj, location, style, literal, math in payloads(scene):
        location_id=identity({'owner':obj['id'],'location':location})
        declared_faces.setdefault(location_id,copy.deepcopy(resolution.merge_style(obj['style'],style).get('font_faces',{})))
        style.pop('font_faces', None)
        choices = {r['role']: bindings[r['id']]['family'] for r in request_rows.values() if r['owner'] == obj['id'] and r['location'] == location}
        if choices:
            located=[bindings[r['id']] for r in request_rows.values() if r['owner']==obj['id'] and r['location']==location]
            if not math:
                role_flags={b['request']['role']:(bool(b['request']['bold'] and
                             (b['resource'].get('style_link_bold',True) or b['resource']['weight']<600)),
                        bool(b['request']['italic'] and (b['resource'].get('style_link_italic',True) or not b['resource']['italic']))) for b in located}
                flags=set(role_flags.values())
                if len(flags)>1:
                    style['native_script_styles']={role:{'bold':value[0],'italic':value[1]} for role,value in role_flags.items()}
                    style.pop('native_bold',None);style.pop('native_italic',None)
                else:
                    style.pop('native_script_styles',None)
                if len(flags)==1:
                    native_bold,native_italic=next(iter(flags))
                    for flag,value in (('bold',native_bold),('italic',native_italic)):
                        effective=resolution.merge_style(obj['style'],style)
                        if value!=bool(effective.get(flag,False)):style['native_'+flag]=value
                        else:style.pop('native_'+flag,None)
            style['font_faces'] = choices if math else resolution.resolve_faces(
                {'font':style.get('font',obj['style'].get('font','DejaVu Sans')),'font_faces':owner_defaults.get(obj['id'],{})},
                {'font_faces':choices})
            resolved_runs[location_id]={'owner':obj['id'],'location':location,'faces':copy.deepcopy(style['font_faces']),
                'bound_roles':sorted(choices),'bindings':sorted(r['id'] for r in request_rows.values() if r['owner']==obj['id'] and r['location']==location),
                'fallback':'latin, then ea, then cs; unused slots use the selected primary'}
    for obj in scene['objects']:
        choices={role:next(iter(names)) for role,names in owner_faces.get(obj['id'],{}).items() if len(names)==1}
        if choices:
            obj['style']['font_faces']=choices if obj['render_type']=='equation' or not set(choices)&set(resolution.SLOTS) else resolution.resolve_faces({'font':obj['style'].get('font','DejaVu Sans'),'font_faces':choices})
    scene['font_plan'] = {'version': VERSION, 'bindings': {k: copy.deepcopy(bindings[k]) for k in request_rows},
                          'embedding': 'full_editable', 'source_hash': scene['source']['sha256'],
                          'resolved_runs':resolved_runs,'declared_faces':declared_faces,
                          'source_spans':resolution.source_spans(scene),
                          'native_spans':resolution.source_spans(scene,native=True)}
    if resolution.enabled(state,scene) or resolution.enabled(scene={'font_plan':previous}):
        scene['font_plan']['policy']=resolution.POLICY
        scene['font_plan']['user_font_requests']=copy.deepcopy((state or {}).get('objectives',{}).get('font_requests',previous.get('user_font_requests',{})))
        scene['font_plan']['intent_overrides']=copy.deepcopy((state or {}).get('font_intent_overrides',previous.get('intent_overrides',{})))
    return scene


def preserve_unwritten_nodes(scene, before, allowed):
    """Keep compiler-only map expansion outside a native grant out of its journal.

    Effective slots and resource identities must already agree. A real change
    still needs a focused native font revision; it cannot hide as compilation.
    """
    from .component_fields import canonical_node
    scene=copy.deepcopy(scene);old={node['id']:node for node in before['objects']}
    untouched=set(old)-set(allowed or {})
    def slots(value):
        return {(obj['id'],location):resolution.resolve_faces(obj['style'],style)
                for obj,location,style,_,_ in payloads(value) if obj['id'] in untouched}
    if slots(before)!=slots(scene):
        raise ValueError('FONT_SCOPE_REVISION_REQUIRED: effective font slots changed outside the current native grant')
    def resources_by_owner(value):
        return {key:(row['family'],row['resource']['file_sha256'],row['resource']['face_index'],
                     bool(row.get('synthetic_style')),row['request']['bold'],row['request']['italic'])
                for key,row in value.get('font_plan',{}).get('bindings',{}).items()
                if row['request']['owner'] in untouched}
    if resources_by_owner(before)!=resources_by_owner(scene):
        raise ValueError('FONT_SCOPE_REVISION_REQUIRED: bound resource changed outside the current native grant')
    for index,node in enumerate(scene['objects']):
        if node['id'] not in untouched:continue
        if canonical_node(node)!=canonical_node(old[node['id']]):
            raise ValueError('Transaction escaped declared native owner scope: '+node['id'])
        scene['objects'][index]=copy.deepcopy(old[node['id']])
    return scene


def bind_scene(task, state, scene):
    resolution.verify_source_spans(task,state,scene)
    if resolution.enabled(state) and missing(scene,state):
        raise ValueError('FONT_BINDING_REQUIRED: complete the current source-style/group preparation for every pending face before native adoption')
    if not required(state):
        # Legacy artwork is preserved; new builds still need explicit bindings.
        return compile_scene(scene)
    return compile_scene(scene, state)


def auto_bind(task,state,scene,*,persist=True):
    """Explicit user identities do not need repeated model font-selection work."""
    demands=state['objectives'].get('font_requests',{})
    from .font_collection import prepare,eligible
    prepare(state);values=[]
    for row in missing(scene,state):
        faces=eligible(state,row,extend=bool(user_family(state,row)))
        family=user_family(state,row)
        compiler=row['role'].startswith('math_aux:')
        if compiler:family=row['proposed_family']
        if row['role'].startswith('math_style:') and not family:
            primary=next((b for b in state.get('font_contract',{}).get('bindings',{}).values()
                          if b['request']['owner']==row['owner'] and b['request']['location']==row['location'] and b['request']['role']=='math'),None)
            if primary:
                # A real alternate face of the chosen family, not a new raster
                # identity guess. It shares the original primary evidence.
                candidates=[f for f in faces if resources.matches(f,primary['family']) and f['editable_embedding'] and not f['variable']
                            and (not f['italic'] or row['italic']) and (f['weight']<600 or row['bold'])]
                if candidates:
                    face=min(candidates,key=lambda f:(f['italic']!=row['italic'],abs(f['weight']-(700 if row['bold'] else 400)),f['id']))
                    synthetic=(row['bold'] and face['weight']<600) or row['italic']!=face['italic']
                    evidence={**primary['evidence'],'style_description':'Bound native mathematical run uses the AST-declared italic/upright style; synthetic styling is disclosed when the exact family lacks that face'}
                    value={'request_id':row['id'],'family':primary['family'],'resource_id':face['id'],
                           'origin':primary['origin'],'status':primary['status'],'evidence':evidence,'synthetic_style':synthetic,
                           'alternatives':primary.get('alternatives',[]),'comparison_ref':primary.get('comparison_ref')}
                    if primary.get('source_metadata_ref'):value['source_metadata_ref']=primary['source_metadata_ref']
                    values.append(value)
                continue
        if not isinstance(family,str):continue
        candidates=[f for f in faces if resources.matches(f,family) and f['editable_embedding'] and not f['variable']
                    and (not f['italic'] or row['italic']) and (f['weight']<600 or row['bold'])]
        if not candidates:continue
        face=min(candidates,key=lambda f:(f['italic']!=row['italic'],abs(f['weight']-(700 if row['bold'] else 400)),f['id']))
        value={'request_id':row['id'],'family':family,'resource_id':face['id'],'origin':'compiler' if compiler else 'user','status':'exact',
                       'synthetic_style':(row['bold'] and face['weight']<600) or row['italic']!=face['italic'],
                       'evidence':{'source_hash':state['source']['sha256'],'roi':row['roi'],
                                   'description':'Explicit task font_requests, not raster font metadata'}}
        prior=state.get('font_contract',{}).get('bindings',{}).get(row['id'])
        if row.get('identity_policy')==resolution.POLICY and prior:
            if not revision_details(task,state,scene,row)['authorized']:continue
            value.update(prior_binding_hash=identity(prior),revision_reason='Frozen exact user or compiler intent revised in the current source scope')
        values.append(value)
    if values:bind(task,state,scene,values,persist=persist)


def current_bindings(scene):
    return list(scene.get('font_plan', {}).get('bindings', {}).values())


def guard_saved(scene, pptx):
    """Check each frozen owner/location/script against its actual saved runs."""
    from .typography_units import guard_saved as guard_typography
    guard_typography(scene,pptx)
    bindings=current_bindings(scene);owners={};saved={};unbound=[];checked=[]
    for binding in bindings:owners.setdefault(binding['request']['owner'],[]).append(binding)
    M='http://schemas.openxmlformats.org/officeDocument/2006/math'
    from .native_markup import active_children
    def shapes(node):
        for child in active_children(node):
            if child.tag=='{'+P+'}grpSp':yield from shapes(child)
            elif child.tag in ('{'+P+'}sp','{'+P+'}graphicFrame'):yield child
    def literal(node,math=False):return ''.join(node.itertext('{'+(M if math else A)+'}t'))
    from .resource_facts import package_read,xml_part
    with package_read(pptx) as archive:
        for name in archive.namelist():
            if not name.startswith('ppt/slides/slide') or not name.endswith('.xml'):continue
            tree=xml_part(pptx,name).find('./{'+P+'}cSld/{'+P+'}spTree')
            if tree is None:raise ValueError('Saved slide shape tree missing')
            for shape in shapes(tree):
                nv=shape.find('.//{'+P+'}cNvPr');owner=nv.get('name') if nv is not None else None
                if not (literal(shape)+literal(shape,True)).strip():continue
                if owner in saved:raise ValueError('Ambiguous saved font owner: '+str(owner))
                saved[owner]=shape
                if owner not in owners:unbound.append(owner)
    if set(owners)-set(saved):raise ValueError('Saved native font owners missing: '+repr(sorted(set(owners)-set(saved))))
    if unbound:raise ValueError('FONT_ASSET_BINDING_REQUIRED: expose imported native text/math as independently bound Scene owners before portable build: '+repr(sorted(unbound,key=str)))
    for owner,values in owners.items():
        shape=saved[owner];covered=set()
        expected_spans=scene.get('font_plan',{}).get('native_spans',scene.get('font_plan',{}).get('source_spans',{})).get(owner)
        if expected_spans is not None:
            kind=next(o['render_type'] for o in scene['objects'] if o['id']==owner)
            if resolution.saved_spans(shape,kind)!=expected_spans:
                raise ValueError('FONT_TEXT_STYLE_CHANGE: saved text or colour/emphasis intervals changed: '+owner)
        for binding in values:
            request=binding['request'];location=request['location'];role=request['role'];math=role=='math' or role.startswith(('math_aux:','math_style:'))
            try:
                if location.startswith('p'):
                    pi,ri=map(int,location[1:].split('.r'))
                    paragraph=shape.findall('./{'+P+'}txBody/{'+A+'}p')[pi]
                    runs=[n for n in paragraph if E.QName(n).localname in ('r','m')]
                    # Physical script/style subdivision does not change the
                    # stable logical source run location. Select its exact
                    # character interval, with no partial native run borrowing.
                    obj=next(o for o in scene['objects'] if o['id']==owner)
                    wanted=obj['content'].get('paragraphs',[obj['content'].get('runs',[])])[pi]
                    lengths=[1 if 'ast' in r else len(r.get('text','')) for r in wanted]
                    start=sum(lengths[:ri]);end=start+lengths[ri];offset=0;selected=[]
                    for run in runs:
                        length=1 if E.QName(run).localname=='m' else len(literal(run))
                        if offset<end and offset+length>start:
                            if offset<start or offset+length>end:raise ValueError('native run crosses a frozen logical location')
                            selected.append(run)
                        offset+=length
                    actual_literal=''.join(literal(n,math) for n in selected)
                else:
                    body=shape
                    if location.startswith('cell.'):
                        row,column=map(int,location.split('.')[1:])
                        body=shape.find('.//{'+A+'}tbl').findall('{'+A+'}tr')[row].findall('{'+A+'}tc')[column]
                    selected=[body]
                    if math:actual_literal=literal(body,True)
                    else:actual_literal='\n'.join(literal(p) for p in body.findall('.//{'+A+'}txBody/{'+A+'}p')+body.findall('./{'+P+'}txBody/{'+A+'}p'))
                runs=[n for region in selected for n in region.iter('{'+(M if math else A)+'}r')]
                relevant=[]
                planned=scene.get('font_plan',{}).get('resolved_runs',{}).get(identity({'owner':owner,'location':location}))
                auxiliary={v['family'] for v in values if v['request']['location']==location and v['request']['role'].startswith('math_aux:')}
                for run in runs:
                    text=literal(run,math)
                    if not text.strip():continue
                    props=run.find('{'+A+'}rPr')
                    if not math and planned:
                        for slot in resolution.SLOTS:
                            actual_face=props.find('{'+A+'}'+slot) if props is not None else None
                            if actual_face is None or actual_face.get('typeface')!=planned['faces'][slot]:
                                raise ValueError('saved slot differs from the complete font plan: '+slot)
                    face=props.find('{'+A+'}'+('latin' if math else role)) if props is not None else None
                    actual=face.get('typeface') if face is not None else None
                    if not math and not any(not c.isspace() and script(c)==role for c in text):continue
                    if math and role.startswith('math_aux:') and actual!=role.split(':',1)[1]:continue
                    if math and role=='math' and actual in auxiliary:continue
                    relevant.append(run);covered.add(run)
                    if actual!=binding['family']:raise ValueError('saved run has another font family')
                if not relevant:raise ValueError('no saved run covers this script/font request')
                if role.startswith('math_aux:'):actual_literal=''.join(literal(run,True) for run in relevant)
                if request.get('literal_hash') and identity(actual_literal)!=request['literal_hash']:
                    raise ValueError('saved literal or run topology changed')
            except (IndexError,AttributeError,ValueError) as error:
                raise ValueError('Saved native font binding missing: '+owner+'/'+location+'/'+role+'; '+str(error)) from error
            checked.append({'owner':owner,'location':location,'role':role,'family':binding['family']})
        actual_runs=[n for n in shape.iter() if n.tag in ('{'+A+'}r','{'+M+'}r') and (literal(n)+literal(n,True)).strip()]
        if any(n not in covered for n in actual_runs):raise ValueError('Saved native text run lacks a location-bound font request: '+owner)
    return {'status': 'SOURCE_FONT_BINDINGS_SERIALIZED', 'owners': len(owners), 'bindings': len(bindings),
            'checked_locations':checked,
            'source_identity_approximate': [b['request']['owner'] for b in bindings if b['status'] == 'approximate'],
            'scope': 'Native font references only; actual renderer glyph/family evidence is separate'}


def finalize(scene, pptx):
    bindings = current_bindings(scene)
    guard = guard_saved(scene, pptx)
    from .font_embedding import embed
    embedded = embed(pptx, bindings)
    return {'binding': guard, 'embedding': embedded}


def deliver_with_provider(scene,pptx,caps,output):
    from .font_embedding import windows_provider,transfer_provider
    bindings=current_bindings(scene)
    provider=windows_provider(pptx,output,caps,bindings)
    embedded=transfer_provider(pptx,provider,bindings)
    return {'binding':guard_saved(scene,pptx),'embedding':embedded}


def apply_user_intent(task, state, scene, proof, result):
    """Revise only font fields explicitly named in the frozen native user grant."""
    changes = [c for c in result.get('changes', []) if c['field'] in ('style.font', 'style.bold', 'style.italic')]
    if not changes:
        return compile_scene(scene, state)
    rows = requests(scene,state)
    faces = resources.available(state['capabilities'])
    ledger = state.setdefault('font_contract', {'version': VERSION, 'bindings': {}, 'history': []})
    values = []
    for change in changes:
        owner, field = change['object_id'], change['field']
        if field not in proof['allowed_changes'].get(owner, []):
            raise ValueError('A font change does not have native user authority')
        for row in rows:
            if row['owner'] != owner:
                continue
            prior = ledger['bindings'].get(row['id'])
            family = change['value'] if field == 'style.font' else prior['family'] if prior else row['proposed_family']
            candidates = [f for f in faces if resources.matches(f, family) and f['editable_embedding'] and not f['variable']
                          and (not f['italic'] or row['italic']) and (f['weight']<600 or row['bold'])]
            if not candidates:
                raise ValueError('Requested native font is unavailable; retain the user baseline and select an existing compatible host')
            face = min(candidates, key=lambda f: (f['italic'] != row['italic'], abs(f['weight']-(700 if row['bold'] else 400)), f['id']))
            demanded = state['objectives'].setdefault('font_requests', {}).setdefault(owner, {})
            if not isinstance(demanded, dict):
                raise ValueError('Per-owner font roles must be explicit')
            demanded[row['role']] = family
            previous = ledger['bindings'].pop(row['id'], None)
            if previous:
                ledger['history'].append({'native_user_authorization': proof['id'], 'prior': previous, 'request': row['id']})
            values.append({'request_id': row['id'], 'family': family, 'resource_id': face['id'], 'origin': 'user', 'status': 'exact',
                'synthetic_style': row['bold'] and face['weight'] < 600 or row['italic'] != face['italic'],
                'evidence': {'source_hash': state['source']['sha256'], 'roi': row['roi'],
                             'description': 'Frozen native user font edit '+proof['id']}})
    # A single request may include font and weight. Last value has the same intent.
    bind(task, state, scene, list({v['request_id']: v for v in values}.values()))
    return compile_scene(scene, state)


def resolved_source_node(expected,actual):
    """Hydrate only compiler font resources; preserve every source style parameter."""
    from .tables import normalize_node
    result=normalize_node(expected);actual=normalize_node(actual)
    def hydrate(left,right):
        if isinstance(left,dict) and isinstance(right,dict):
            if 'font_faces' in right:left['font_faces']=copy.deepcopy(right['font_faces'])
            for key in set(left)&set(right):
                if key!='font_faces':hydrate(left[key],right[key])
        elif isinstance(left,list) and isinstance(right,list) and len(left)==len(right):
            for a,b in zip(left,right):hydrate(a,b)
    hydrate(result,actual)
    return result
