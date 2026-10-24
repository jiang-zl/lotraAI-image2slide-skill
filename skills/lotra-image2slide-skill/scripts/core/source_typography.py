"""Source-only physical-font size model, before native mutation or page render.

Uses the existing isolated original glyph samples, or explicit equivalent Math
samples. FreeType measures the exact bound physical face. It does not invent a
point size from a photo's pixel height or call another language model.
"""
import copy
import re
import statistics
from pathlib import Path
import numpy as np
from PIL import Image, ImageFont
from .common import digest, identity, read_json, write_json, safe_path
from .typography_units import POLICY, points_per_pixel, half_point, canonicalize


class PreflightRequired(ValueError):
    """Retain a typed source diagnostic so next can offer a legal recovery."""
    def __init__(self, task, file, record):
        self.reference = {'path': file.relative_to(task).as_posix(), 'sha256': digest(file)}
        self.record = record
        super().__init__('TYPOGRAPHY_PREFLIGHT_REQUIRED: '+self.reference['path']+'; '+record['errors'][0]['reason'])


def _frames(scene, requests, bindings, targets):
    """Cheap horizontal-run advance screen; never a page-layout PASS."""
    from .font_contract import payloads, script
    grouped={};fonts={};errors=[];rows=[];cursors={}
    for request in requests:
        key=(request['owner'],request['location'])
        if request['id'] in bindings:
            grouped.setdefault(key,{})[request['role']]=bindings[request['id']]['resource']
    for obj,location,leaf,literal,is_math in payloads(scene):
        if obj['id'] not in targets:continue
        if is_math or obj['render_type']=='table' or obj['content'].get('text_layout',{}).get('direction','horizontal')!='horizontal':
            rows.append({'owner':obj['id'],'location':location,'status':'SPECIALIZED_LAYOUT_NOT_SCREENED',
                         'scope':'Size and native attributes still checked; formula/cell/vertical layout needs its native backend'})
            continue
        style={**obj['style'],**leaf};faces=grouped.get((obj['id'],location),{})
        if not faces:continue  # Missing font requests are diagnosed by font binding.
        # Plain-text newlines and explicit paragraph/run locations retain order.
        paragraph=location.split('.r')[0] if location.startswith('p') else location
        paragraph_key=(obj['id'],paragraph)
        start_line=cursors.get(paragraph_key,0)
        for line_index,line in enumerate(literal.split('\n')):
            key=(obj['id'],paragraph,start_line+line_index);record=next((r for r in rows if r.get('key')==key),None)
            if record is None:
                record={'key':key,'owner':obj['id'],'width_pt':0.,'ink_height_pt':0.,'characters':0,'status':'ADVANCE_ESTIMATE_ONLY'};rows.append(record)
            advance=0.;height=0.
            for char in line:
                if char.isspace():role=next(iter(faces))
                else:role=script(char)
                resource=faces.get(role)
                if resource is None:
                    record['status']='SCRIPT_LAYOUT_NOT_SCREENED';continue
                font_key=(resource['path'],resource['face_index'])
                if font_key not in fonts:fonts[font_key]=ImageFont.truetype(resource['path'],size=512,index=resource['face_index'])
                font=fonts[font_key];box=font.getbbox(char)
                advance+=float(font.getlength(char))*style['font_size']/512
                height=max(height,(box[3]-box[1])*style['font_size']/512)
            # Summed character advances are an early conservative model; native
            # shaping/ligatures, line wrapping and implicit Math remain separate.
            tracking=style.get('char_spacing_pt',0)
            advance+=tracking*max(0,len(line)-1+(1 if record['characters'] else 0))
            record['width_pt']+=advance;record['ink_height_pt']=max(record['ink_height_pt'],height)
            record['characters']+=len(line)
            record['wrap']=bool(style.get('wrap',False))
        cursors[paragraph_key]=start_line+literal.count('\n')
    objects={o['id']:o for o in scene['objects']};scale=points_per_pixel(scene)
    for row in rows:
        if 'width_pt' not in row:continue
        obj=objects[row['owner']];frame=[obj['bbox'][2]*scale,obj['bbox'][3]*scale]
        row['frame_pt']=frame
        if row.get('wrap'):
            row['status']='WRAPPED_LAYOUT_NOT_SCREENED'
        if (not row.get('wrap') and row['width_pt']>frame[0]+1) or row['ink_height_pt']>frame[1]+1:
            errors.append({'owner':row['owner'],'location':str(row['key']),
                           'reason':'TYPOGRAPHY_FRAME_MODEL_REVIEW_REQUIRED: estimated advances/ink exceed frame; resolve before native construction'})
    return rows,errors


def _ink(image, roi):
    x, y, w, h = roi
    if any(type(v) not in (int, float) or not np.isfinite(v) for v in roi) or min(w, h) < 2:
        raise ValueError('TYPOGRAPHY_SAMPLE_REQUIRED: finite isolated source glyph ROI')
    if x < 0 or y < 0 or x+w > image.width or y+h > image.height or max(w, h) > 256:
        raise ValueError('TYPOGRAPHY_SAMPLE_REQUIRED: bounded original glyph inside canvas')
    pixels = np.asarray(image.crop((int(x), int(y), int(np.ceil(x+w)), int(np.ceil(y+h)))).convert('RGB'), float)/255
    border = np.concatenate((pixels[0], pixels[-1], pixels[:, 0], pixels[:, -1]))
    background = np.median(border, axis=0)
    if np.quantile(np.linalg.norm(border-background, axis=1), .9) > .15:
        raise ValueError('TYPOGRAPHY_SAMPLE_ISOLATION_REQUIRED: unstable source background')
    mask = np.linalg.norm(pixels-background, axis=2) > .2
    yy, xx = np.nonzero(mask)
    if len(xx) < 4 or xx.min() == 0 or yy.min() == 0 or xx.max() == mask.shape[1]-1 or yy.max() == mask.shape[0]-1:
        raise ValueError('TYPOGRAPHY_SAMPLE_ISOLATION_REQUIRED: clipped or missing source ink')
    return [int(xx.max()-xx.min()+1), int(yy.max()-yy.min()+1)]


def _estimate(image, samples, resource, scale):
    from .source_font_size import fit
    return fit(image, samples, resource, scale)


def _supported_sizes(model):
    return set(model.get('group_plausible_sizes_pt', model.get('plausible_sizes_pt', [])))


def _construction_choice(models, declared=None):
    """Choose only measured support; identification uncertainty stays explicit.

    A low-resolution photograph cannot always identify a unique half-point.
    Retain a supported current estimate; otherwise rank the finite intersection.
    This is a construction decision, never original-size identification or paint
    acceptance. Empty/contradictory intervals cannot acquire a choice.
    """
    if not models or any(not _supported_sizes(model) for model in models):
        return None
    common = set.intersection(*(_supported_sizes(model) for model in models))
    selected = {model['group_selected_pt'] for model in models if model.get('group_selected_pt') is not None}
    if selected:
        common &= selected if len(selected) == 1 else set()
    if not common:
        return None
    if declared in common:
        return declared
    def score(size):
        rows = [next((row for row in model.get('candidates', []) if row['font_size_pt'] == size), None) for model in models]
        if any(row is None for row in rows):
            return (float('inf'), float('inf'), float('inf'), size)
        return (sum(row['extent_error_px'] for row in rows), sum(row['boundary_mean_px'] for row in rows),
                sum(row['ink_disagreement'] for row in rows), size)
    return min(common, key=score)


def _size_groups(rows, errors, measurement):
    """Only explicitly observed equal-size groups share a source-size decision."""
    grouped = {}
    for key, row in rows.items():
        if row.get('size_group'):
            grouped.setdefault(row['size_group'], []).append((key, row))
    result = []
    for name, members in grouped.items():
        if measurement['kind'] == 'projected_appearance':
            errors.append({'owner': name, 'reason': 'TYPOGRAPHY_SIZE_GROUP_PLANE_REQUIRED: equal original sizes need a common rectified/fronto-parallel plane'})
            continue
        common = set.intersection(*(set(row['model']['plausible_sizes_pt']) for _, row in members))
        if not common:
            errors.append({'owner': name, 'reason': 'TYPOGRAPHY_SIZE_GROUP_CONFLICT: original samples do not identify a shared size'})
            continue
        # Intersect valid observations; never widen one member's failed interval.
        declared = {row.get('font_size_pt') for _, row in members}
        selected = _construction_choice([row['model'] for _, row in members],
                                        next(iter(declared)) if len(declared) == 1 else None)
        result.append({'group': name, 'members': [key for key, _ in members], 'plausible_sizes_pt': sorted(common),
                       'construction_selected_pt': selected, 'historical_original_pt_identified': False})
        for _, row in members:
            row['model']['group_plausible_sizes_pt'] = sorted(common)
            row['model']['group_selected_pt'] = selected
            if len(common) == 1:
                row['model']['recommended_pt'] = next(iter(common))
                row['model']['status'] = 'IDENTIFIED_BY_SOURCE_GROUP'
    return result


def _alignment(scene, frozen, targets):
    """Source-bound native alignment intent; actual painted centering is separate."""
    expected={obj['id']:obj for obj in frozen['objects']};rows=[];errors=[]
    for obj in scene['objects']:
        if obj['id'] not in targets or obj['render_type'] not in ('text','equation','table'):continue
        prior=expected.get(obj['id'])
        if prior is None or prior['render_type']!=obj['render_type']:
            errors.append({'owner':obj['id'],'reason':'TYPOGRAPHY_ALIGNMENT_REBIND_REQUIRED: current frozen source owner required'});continue
        def intent(value):
            kind=value['render_type'];style=value['style']
            result={'align':style.get('align','center' if kind=='equation' else 'left'),
                    'valign':style.get('valign','middle' if kind=='table' else 'top'),
                    'rotation':style.get('rotation',0),'paragraph_layout':value['content'].get('paragraph_layout')}
            if kind=='table':
                result['padding']=style.get('padding',0)
                result['cell_styles']=[[{key:cell.get(key,style.get(key,default)) for key,default in
                    (('align','left'),('valign','middle'),('padding',0))} for cell in row]
                    for row in value['content'].get('cell_styles',[[{} for _ in row] for row in value['content']['rows']])]
            return result
        wanted= intent(prior);actual=intent(obj)
        rows.append({'owner':obj['id'],'expected_native_alignment':wanted,'actual_native_alignment':actual,
                     'status':'SOURCE_INTENT_MATCH' if wanted==actual else 'SOURCE_INTENT_MISMATCH',
                     'painted_centering':'PENDING_ACTUAL_RENDER; native frame/paragraph alignment alone is not ink centering'})
        if wanted!=actual:errors.append({'owner':obj['id'],'reason':'TYPOGRAPHY_ALIGNMENT_REBIND_REQUIRED: alignment/insets changed from frozen source intent'})
    return rows,errors


def require(task, state, scene, contract, allowed=None):
    if state.get('typography_policy') != POLICY:
        return scene
    from .font_contract import requests, payloads
    from .font_resolution import request_key
    scene = canonicalize(scene); task = Path(task)
    request_rows=requests(scene,state)
    if not request_rows:
        return scene
    frozen_file=safe_path(task,contract['source_scene']['path'])
    if digest(frozen_file)!=contract['source_scene']['sha256']:
        raise ValueError('TYPOGRAPHY_SOURCE_SCENE_CHANGED: frozen measurement/physical canvas needs a current binding')
    frozen=read_json(frozen_file)
    if any(scene['canvas'].get(key)!=frozen['canvas'].get(key) for key in ('width','height','unit','target_width_inches')):
        raise ValueError('TYPOGRAPHY_CANVAS_REBIND_REQUIRED: physical/source mapping changed after binding')
    original = safe_path(task, state['source']['path'])
    if digest(original) != state['source']['sha256']:
        raise ValueError('TYPOGRAPHY_SOURCE_CHANGED')
    bindings = scene.get('font_plan', {}).get('bindings', {})
    rows = {}; errors = []; targets = set(allowed) if allowed else {o['id'] for o in scene['objects']}
    alignment,alignment_errors=_alignment(scene,frozen,targets);errors.extend(alignment_errors)
    # Explicit equal-size peers are read dependencies, not extra native grants.
    active_groups = {sample.get('size_group') for obj in scene['objects'] if obj['id'] in targets
                     for sample in obj.get('typography_samples', {}).values() if sample.get('size_group')}
    read_targets = targets | {obj['id'] for obj in scene['objects']
        if any(sample.get('size_group') in active_groups for sample in obj.get('typography_samples', {}).values())}
    from .typography_measurement import context as measurement_context
    try:
        measurement = measurement_context(task, state, scene, frozen)
    except (ValueError, KeyError, OSError) as error:
        measurement = None
        errors.append({'owner': 'source', 'reason': str(error)})
    payload = {}
    for obj,loc,leaf,literal,is_math in payloads(scene):
        effective={**obj['style'],**leaf}
        if is_math and obj['render_type']=='text':
            effective['font_size']=effective.get('math_typography',{}).get('font_size_pt',effective['font_size'])
        payload[(obj['id'],loc)]={'style': effective, 'literal': literal}
    objects = {o['id']: o for o in scene['objects']}
    with Image.open(original) as image:
        for request in request_rows:
            if request['owner'] not in read_targets or request['role'].startswith(('math_aux:', 'math_style:')):
                continue
            key = request['id']; owner = request['owner']; location = request['location']
            try:
                binding = bindings[key]; sample_record = state.get('font_samples', {}).get(key, {})
                explicit = objects[owner].get('typography_samples', {}).get(location, {})
                recovered = state.get('typography_samples', {}).get(key, {})
                if recovered:
                    if recovered.get('request_hash') != request_key(request):
                        raise ValueError('TYPOGRAPHY_SAMPLE_CHANGED: recovered sample belongs to another font request')
                    explicit = recovered
                if explicit:
                    sample_record = explicit
                    if (sample_record.get('source_hash') != state['source']['sha256'] or
                            sample_record.get('observer') not in ('host_model', 'human') or
                            not sample_record.get('source_evidence')):
                        raise ValueError('TYPOGRAPHY_SAMPLE_REQUIRED: current original evidence for '+owner+'/'+location)
                    samples = sample_record.get('samples', [])
                elif (sample_record.get('source_hash') == state['source']['sha256'] and
                        sample_record.get('request_hash') == request_key(request)):
                    samples = sample_record['samples']
                else:
                    # Exact/user fonts and Math still need original size evidence.
                    sample_record = objects[owner].get('typography_samples', {}).get(location, {})
                    if (sample_record.get('source_hash') != state['source']['sha256'] or
                            sample_record.get('observer') not in ('host_model', 'human') or
                            not sample_record.get('source_evidence')):
                        raise ValueError('TYPOGRAPHY_SAMPLE_REQUIRED: '+owner+'/'+location)
                    samples = sample_record.get('samples', [])
                if not 1 <= len(samples) <= 12:
                    raise ValueError('TYPOGRAPHY_SAMPLE_REQUIRED: one to twelve original glyph/phrase samples')
                if sample_record.get('size_group') is not None and (
                        not isinstance(sample_record['size_group'], str) or
                        not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}',sample_record['size_group'])):
                    raise ValueError('TYPOGRAPHY_SIZE_GROUP_REQUIRED: bounded source-supported size-group ID')
                if request['role']=='math' and sample_record.get('math_level')!='base':
                    raise ValueError('TYPOGRAPHY_MATH_BASE_REQUIRED: identify an original base-level glyph, not a sub/superscript')
                ox, oy, ow, oh = objects[owner]['bbox']
                for sample in samples:
                    x, y, w, h = sample['roi']
                    literal = sample.get('text', sample.get('character', ''))
                    if (not literal or any(not char.isspace() and char not in request['characters'] for char in literal) or
                            len(literal)>1 and literal not in payload[(owner,location)]['literal'] or
                            x < ox or y < oy or x+w > ox+ow or y+h > oy+oh):
                        raise ValueError('TYPOGRAPHY_SAMPLE_OWNER_REQUIRED: glyph must belong to current owner/script')
                if measurement is None:
                    continue
                from .source_font_size import fit
                style = payload[(owner, location)]['style']
                model = fit(image, samples, binding['resource'], points_per_pixel(scene),
                            measurement['source_uncertainty_px'], style)
                rows[key] = {'owner': owner, 'location': location, 'font_size_pt': style['font_size'],
                             'size_group': sample_record.get('size_group'), 'model': model}
            except (ValueError, KeyError, OSError) as error:
                errors.append({'owner': owner, 'location': location, 'reason': str(error)})
    groups = _size_groups(rows, errors, measurement) if measurement else []
    for row in rows.values():
        model = row['model']; supported = _supported_sizes(model)
        choice = _construction_choice([model], row['font_size_pt'])
        row['construction_size_decision'] = {
            'font_size_pt': row['font_size_pt'], 'supported_sizes_pt': sorted(supported),
            'selected_pt': choice, 'source_identification_status': model['status'],
            'historical_original_pt_identified': False,
            'status': 'SUPPORTED_ESTIMATE' if choice == row['font_size_pt'] else 'DECISION_REQUIRED',
            'scope': 'Pre-render construction estimate within unchanged source-fit bounds; actual paint acceptance is still required'}
        if choice is None:
            errors.append({'owner': row['owner'], 'location': row['location'],
                           'reason': 'TYPOGRAPHY_SOURCE_SIZE_'+model['status']+': preserve the source uncertainty and resolve samples/plane before construction'})
        elif row['font_size_pt'] != choice:
            errors.append({'owner': row['owner'], 'location': row['location'],
                           'reason': 'TYPOGRAPHY_SIZE_MISMATCH: declared '+str(row['font_size_pt'])+' pt; supported finite construction estimate '+str(choice)+' pt'})
    frames,frame_errors=_frames(scene,request_rows,bindings,targets);errors.extend(frame_errors)
    record = {'policy': POLICY, 'source_hash': state['source']['sha256'], 'scene_hash': identity(scene),
              'model_implementation': {name: digest(Path(__file__).with_name(name+'.py'))
                  for name in ('source_typography','source_font_size','typography_measurement')},
              'points_per_source_pixel': points_per_pixel(scene), 'measurement': measurement,
              'native_write_owners': sorted(targets), 'source_read_owners': sorted(read_targets),
              'rows': rows, 'size_groups': groups, 'frame_screen':frames,'alignment_screen':alignment,'errors': errors, 'status': 'DECISION_REQUIRED' if errors else 'PRE_RENDER_SIZE_SCREENED',
              'actual_render_acceptance': False}
    file = task/'source'/('Typography-preflight-'+identity(record)+'.json'); write_json(file, record)
    if errors:
        raise PreflightRequired(task, file, record)
    return scene


def recovery(task, state, scene, error):
    """Expose bounded original-only sampling before any native bytes exist."""
    from .font_contract import requests, payloads
    from .typography_measurement import propose_samples
    pending = state['font_pending_candidate']
    pending['typography_preflight'] = error.reference
    failed = {(r['owner'], r.get('location')) for r in error.record['errors']}
    literals = {(o['id'], loc): text for o, loc, _, text, _ in payloads(scene)}
    scope = pending.get('allowed')
    rows = []
    for request in requests(scene, state):
        key = (request['owner'], request['location'])
        if scope is not None and request['owner'] not in scope:
            continue
        if key not in failed and not any(owner == request['owner'] and loc is None for owner, loc in failed):
            continue
        row = {k: request[k] for k in ('id', 'owner', 'location', 'role', 'roi', 'characters')}
        row.update(literal=literals[key], current_model=error.record['rows'].get(request['id'], {}).get('model'),
                   sample_suggestions=propose_samples(task, state, request, literals[key]),
                   prior_samples=state.get('typography_samples', {}).get(request['id']),
                   attempts=sum(request['id'] in r['requests'] for r in pending.get('typography_recovery_history', [])))
        # Candidate tables remain in the hash-bound report, not model context.
        if row['current_model']:
            row['current_model'] = {k: row['current_model'][k] for k in
                ('status', 'recommended_pt', 'plausible_sizes_pt', 'best_candidate_pt', 'scope')}
        rows.append(row)
        if len(rows) == 4:
            break
    return {'preflight': error.reference, 'pending_scene': pending['scene'], 'requests': rows,
            'remaining_failures': len(error.record['errors']), 'source_hash': state['source']['sha256'],
            'return': 'typography_changes:[{request_id,samples:[{text or character,roi,domain:task_source}],source_evidence}]. Confirm 1..12 original glyph/continuous phrase samples per request, at most 32 characters. Never use OCR-normalized pixels. Adopt only a half-point estimate in the intersection of supported source fits, retaining every ambiguity interval. Content, fonts, geometry, units, plane, alignment and frozen quality bounds are not editable in this packet.',
            'attempt_limit_per_request': 3, 'native_write_performed': False,
            'action_references': ['references/workflow-v1375.md']}


def receive_recovery(task, state, packet, result):
    """Record source samples and adopt supported estimates without false identity."""
    from . import font_contract, component_workflow as c
    from .font_resolution import request_key
    task = Path(task); pending = state['font_pending_candidate']
    if pending['scene'] != packet['pending_scene'] or pending.get('typography_preflight') != packet['preflight']:
        raise ValueError('TYPOGRAPHY_RECOVERY_CHANGED: request a current packet')
    for ref in (packet['pending_scene'], packet['preflight']):
        if digest(safe_path(task, ref['path'])) != ref['sha256']:
            raise ValueError('TYPOGRAPHY_RECOVERY_CHANGED: retained scene/diagnostic bytes changed')
    if set(result)-{'packet_id','typography_changes'}:
        raise ValueError('Typography recovery accepts located samples only')
    changes = result.get('typography_changes', [])
    eligible = {r['id']: r for r in packet['requests']}
    if (not 1 <= len(changes) <= 4 or any(not isinstance(v, dict) for v in changes) or
            len({v.get('request_id') for v in changes}) != len(changes)):
        raise ValueError('TYPOGRAPHY_SAMPLE_REQUIRED: one to four distinct current requests')
    scene = read_json(safe_path(task, pending['scene']['path']))
    requests = {r['id']: r for r in font_contract.requests(scene, state)}
    literals = {(o['id'], loc): text for o, loc, _, text, _ in font_contract.payloads(scene)}
    samples = copy.deepcopy(state.get('typography_samples', {}))
    for change in changes:
        key = change.get('request_id'); request = requests.get(key)
        if key not in eligible or eligible[key]['attempts'] >= 3:
            raise ValueError('TYPOGRAPHY_SOURCE_REVIEW_REQUIRED: request is outside this batch or its retained sample limit')
        if set(change)-{'request_id','samples','source_evidence'} or not change.get('source_evidence'):
            raise ValueError('Typography recovery cannot edit native attributes or omit original evidence')
        values = change.get('samples', []); ox, oy, ow, oh = request['roi']
        if not isinstance(values, list) or not 1 <= len(values) <= 12:
            raise ValueError('TYPOGRAPHY_SAMPLE_REQUIRED: one to twelve original samples')
        for sample in values:
            if not isinstance(sample, dict) or set(sample)-{'text','character','roi','domain'}:
                raise ValueError('TYPOGRAPHY_SAMPLE_REQUIRED: bounded literal/ROI/domain only')
            literal = sample.get('text', sample.get('character', '')); roi = sample.get('roi', [])
            if (not isinstance(literal, str) or not 1 <= len(literal) <= 32 or '\n' in literal or
                    literal not in literals[(request['owner'], request['location'])] or
                    any(not ch.isspace() and ch not in request['characters'] for ch in literal) or
                    sample.get('domain', 'task_source') != 'task_source' or len(roi) != 4 or
                    any(type(v) not in (int, float) or not np.isfinite(v) for v in roi)):
                raise ValueError('TYPOGRAPHY_SAMPLE_OWNER_REQUIRED: current source literal, script and finite ROI')
            x, y, w, h = roi
            if min(w, h) < 2 or x < ox or y < oy or x+w > ox+ow or y+h > oy+oh:
                raise ValueError('TYPOGRAPHY_SAMPLE_OWNER_REQUIRED: sample escaped the frozen owner')
        samples[key] = {'source_hash': state['source']['sha256'], 'request_hash': request_key(request),
            'observer': 'host_model', 'source_evidence': copy.deepcopy(change['source_evidence']), 'samples': copy.deepcopy(values)}
    working = {**state, 'typography_samples': samples}
    contract, _ = c._load(task, state)
    bound = font_contract.bind_scene(task, font_contract.pending_state(working), scene)
    try:
        require(task, working, bound, contract, pending.get('allowed'))
    except PreflightRequired as error:
        measured = error.record
    else:
        measured = None
    selected = {(requests[v['request_id']]['owner'], requests[v['request_id']]['location']) for v in changes}
    adopted = []
    if measured:
        for obj, loc, leaf, _, _ in font_contract.payloads(scene):
            if (obj['id'], loc) not in selected:
                continue
            peers = [r for r in requests.values() if r['owner'] == obj['id'] and r['location'] == loc
                     and not r['role'].startswith(('math_aux:', 'math_style:'))]
            models = [measured['rows'].get(r['id'], {}).get('model', {}) for r in peers]
            size = _construction_choice(models, {**obj['style'], **leaf}['font_size'])
            if size is not None:
                leaf['font_size'] = half_point(size)
                adopted.append({'owner': obj['id'], 'location': loc, 'font_size_pt': size,
                    'supported_sizes_pt': sorted(set.intersection(*(_supported_sizes(model) for model in models))),
                    'source_identification_statuses': [model['status'] for model in models],
                    'historical_original_pt_identified': False})
    if pending.get('baseline'):
        c.guard_changes(task, state, scene, pending['allowed'], (pending.get('reason') or {}).get('revision_components', ()))
    file = task/'scratch'/('typography-recovered-'+identity(scene)+'.json'); write_json(file, scene)
    ref = {'path': file.relative_to(task).as_posix(), 'sha256': digest(file)}
    receipt = {'source_hash': state['source']['sha256'], 'prior_scene': pending['scene'], 'scene': ref,
               'preflight': packet['preflight'], 'requests': [v['request_id'] for v in changes],
               'samples_hash': identity(samples), 'adopted_sizes': adopted, 'native_write_performed': False}
    if pending.get('transaction_path'):
        from .component_transactions import phase
        tx = read_json(safe_path(task, pending['transaction_path']))
        if tx['phase'] not in ('PLANNED','STAGED') or tx.get('candidate') or tx.get('font_commit_pending'):
            raise ValueError('TYPOGRAPHY_RECOVERY_PHASE_REQUIRED: preserve already saved native work')
        phase(task, tx, tx['phase'], planned_scene=ref,
              typography_revisions=tx.get('typography_revisions', [])+[receipt])
    state['typography_samples'] = samples
    pending['scene'] = ref; pending.setdefault('typography_recovery_history', []).append(receipt)
    return receipt
