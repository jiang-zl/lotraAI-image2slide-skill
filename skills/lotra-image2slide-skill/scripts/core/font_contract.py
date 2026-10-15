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


def requests(scene):
    result = []
    for obj, location, leaf, literal, math in payloads(scene):
        style = {**obj['style'], **leaf}
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
    return result


def _request_match(binding, request):
    value={k:request[k] for k in ('owner','location','role','characters','literal_hash','bold','italic','proposed_family')}
    # A native mirror may replace the author's hint by its already bound
    # canonical spelling. This is not a different family or a new font intent.
    if resources.matches(binding['resource'],value['proposed_family']):
        value['proposed_family']=binding['request']['proposed_family']
    return binding.get('request_hash') == identity(value)


def required(state):
    return state.get('objectives', {}).get('source_font_contract', True) is True


def missing(scene, state):
    bindings = state.get('font_contract', {}).get('bindings', {})
    from .font_collection import assert_language
    result=[]
    for r in requests(scene):
        bound=bindings.get(r['id'])
        if not bound or not _request_match(bound,r):result.append(r);continue
        try:assert_language(bound['resource'],r['role'])
        except ValueError:result.append(r)
    return result


def user_family(state,request):
    explicit=state['objectives'].get('font_requests',{})
    owner=explicit.get(request['owner'],{})
    role='math' if request['role'].startswith('math_style:') else request['role']
    return (owner.get(role) if isinstance(owner,dict) else None) or explicit.get(role)


def packet(task, state, scene):
    rows = missing(scene, state)
    if not rows:
        return None
    from . import font_collection as collection
    collection.prepare(state)
    selected = rows[:8]
    per_request={r['id']:collection.eligible(state,r) for r in selected}
    faces=list({f['id']:f for values in per_request.values() for f in values}.values())
    catalogue = Path(task)/'source/font-options.json'
    options = [{'id': f['id'], 'family': f['family'], 'aliases': f['aliases'], 'weight': f['weight'],
                'italic': f['italic'], 'hosts': f['hosts'], 'editable_embedding': f['editable_embedding'],
                'outline': f['outline'], 'variable': f['variable'],'style_class':f.get('style_class','unknown')} for f in faces]
    write_json(catalogue, {'environment_key': state['capabilities']['fonts']['environment_key'], 'faces': options})
    return {'reference': 'references/font-collections-v132.md', 'source_hash': state['source']['sha256'],
            'requests': selected, 'remaining': len(rows),
            'language_candidates':{key:[f['id'] for f in values] for key,values in per_request.items()},
            'font_collection':state['font_collection'],
            'source_glyph_rankings':{r['id']:collection.ranking(task,state,r) for r in selected if collection.role_language(r['role']) in ('zh','en')},
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


def bind(task, state, scene, values, *, persist=True):
    rows = {r['id']: r for r in requests(scene)}
    from . import font_collection as collection
    collection.prepare(state)
    faces = {f['id']: f for f in resources.available(state['capabilities'])}
    faces.update(collection.load(state['project'])['faces'])
    ledger = state.setdefault('font_contract', {'version': VERSION, 'bindings': {}, 'history': []})
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
        demanded = user_family(state,request)
        if demanded and (not resources.matches(face, demanded) or status != 'exact'):
            raise ValueError('A requested exact font cannot be replaced by a better-scoring style peer')
        if origin == 'user' and not demanded:
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
        if (not request['bold'] and face['weight']>=600) or (not request['italic'] and face['italic']):
            raise ValueError('A bold/italic-only resource cannot pretend to be the regular upright face')
        if synthetic and not evidence.get('style_description') and origin not in ('user','compiler'):
            raise ValueError('Synthetic weight/slant needs separate original style evidence')
        if ((request['bold'] and face['weight'] < 600) or request['italic'] != face['italic']) and not synthetic:
            raise ValueError('Weight/italic needs the real face, or explicitly source-supported synthetic_style')
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
        record = {'request': request, 'request_hash': identity({k: request[k] for k in ('owner', 'location', 'role', 'characters', 'literal_hash', 'bold', 'italic', 'proposed_family')}),
                  'family': face['family'], 'resource': face, 'origin': origin, 'status': status,
                  'evidence': copy.deepcopy(evidence), 'alternatives': value.get('alternatives', []),
                  'synthetic_style': synthetic,'comparison_ref':copy.deepcopy(value.get('comparison_ref')),
                  'source_metadata_ref':copy.deepcopy(value.get('source_metadata_ref')),
                  'environment_key': state['capabilities']['fonts']['environment_key']}
        prior = ledger['bindings'].get(request['id'])
        if prior and prior['family'] != record['family']:
            grant=state.get('font_pending_candidate',{}).get('allowed') or {}
            if ('style.font' not in grant.get(request['owner'],[]) or value.get('prior_binding_hash')!=identity(prior)
                    or not value.get('revision_reason') or origin!='raster_inference'):
                raise ValueError('A bound family needs an explicit source revision and the existing native font grant')
            ledger['history'].append({'prior':prior,'request':request['id'],'reason':value['revision_reason']})
        accepted[request['id']] = record
        if language in ('zh','en'):archive_faces.append(face)
    collection.archive(state['project'],archive_faces,'Bind source-qualified eligible language fonts')
    ledger['bindings'].update(accepted)
    ledger['history'].append({'source_hash': state['source']['sha256'], 'accepted': sorted(accepted)})
    if persist:write_json(Path(task)/'source/font-bindings.json', ledger)


def compile_scene(scene, state=None):
    from .tables import normalize_scene
    scene = normalize_scene(scene)
    if state is not None:
        bindings = state.get('font_contract', {}).get('bindings', {})
    else:
        plan = scene.get('font_plan', {})
        if plan.get('version') != VERSION and requests(scene):
            raise ValueError('FONT_BINDING_REQUIRED: native text/math/table must have a source/user font plan before build')
        bindings = plan.get('bindings', {})
    request_rows = {r['id']: r for r in requests(scene)}
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
        if not resources.matches(verified[key], bound['family']):
            raise ValueError('Bound font identity changed; refresh resources without changing the source intent')
    owner_faces={}
    for obj, location, style, literal, math in payloads(scene):
        style.pop('font_faces', None)
        choices = {r['role']: bindings[r['id']]['family'] for r in request_rows.values() if r['owner'] == obj['id'] and r['location'] == location}
        if choices:
            style['font_faces'] = choices
            for role,family in choices.items():owner_faces.setdefault(obj['id'],{}).setdefault(role,set()).add(family)
    for obj in scene['objects']:
        choices={role:next(iter(names)) for role,names in owner_faces.get(obj['id'],{}).items() if len(names)==1}
        if choices:obj['style']['font_faces']=choices
    scene['font_plan'] = {'version': VERSION, 'bindings': {k: copy.deepcopy(bindings[k]) for k in request_rows},
                          'embedding': 'full_editable', 'source_hash': scene['source']['sha256']}
    return scene


def bind_scene(task, state, scene):
    if not required(state):
        # Legacy artwork is preserved; new builds still need explicit bindings.
        return compile_scene(scene)
    return compile_scene(scene, state)


def auto_bind(task,state,scene):
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
        values.append({'request_id':row['id'],'family':family,'resource_id':face['id'],'origin':'compiler' if compiler else 'user','status':'exact',
                       'synthetic_style':(row['bold'] and face['weight']<600) or row['italic']!=face['italic'],
                       'evidence':{'source_hash':state['source']['sha256'],'roi':row['roi'],
                                   'description':'Explicit task font_requests, not raster font metadata'}})
    if values:bind(task,state,scene,values)


def current_bindings(scene):
    return list(scene.get('font_plan', {}).get('bindings', {}).values())


def guard_saved(scene, pptx):
    """Serialization evidence only; actual glyph appearance stays independent."""
    bindings = current_bindings(scene)
    owners = {}
    for binding in bindings:
        key = binding['request']['owner']
        owners.setdefault(key, {}).setdefault(binding['request']['role'], set()).add(binding['family'])
    found = set();unbound=[]
    from .resource_facts import package_read,xml_part
    with package_read(pptx) as archive:
        for name in archive.namelist():
            if not name.startswith('ppt/slides/slide') or not name.endswith('.xml'):
                continue
            root = xml_part(pptx,name)
            for shape in root.findall('.//{'+P+'}sp')+root.findall('.//{'+P+'}graphicFrame'):
                nv = shape.find('.//{'+P+'}cNvPr')
                owner = nv.get('name') if nv is not None else None
                if owner not in owners:
                    literal=''.join(shape.itertext()) if shape.find('.//{'+A+'}t') is not None or shape.find('.//{http://schemas.openxmlformats.org/officeDocument/2006/math}t') is not None else ''
                    if literal.strip():unbound.append(owner)
                    continue
                found.add(owner)
                faces = {role: {n.get('typeface') for n in shape.findall('.//{'+A+'}'+role)} for role in ('latin', 'ea', 'cs')}
                for role, expected in owners[owner].items():
                    actual = faces['latin' if role == 'math' or role.startswith(('math_aux:','math_style:')) else role]
                    if not expected <= actual:
                        raise ValueError('Saved native font binding missing: '+owner+'/'+role)
    if set(owners)-found:
        raise ValueError('Saved native font owners missing: '+repr(sorted(set(owners)-found)))
    if unbound:
        raise ValueError('FONT_ASSET_BINDING_REQUIRED: expose imported native text/math as independently bound Scene owners before portable build: '+repr(sorted(unbound,key=str)))
    return {'status': 'SOURCE_FONT_BINDINGS_SERIALIZED', 'owners': len(owners), 'bindings': len(bindings),
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
    rows = requests(scene)
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
