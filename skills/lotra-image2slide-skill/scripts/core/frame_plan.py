"""Frame-first constraints, typed content windows and program-owned gates.

Source observations are immutable evidence; a user layout target has separate
authority. This module extends the existing runtime, builder and adoption loop.
"""
import copy
import math
from pathlib import Path
from zipfile import ZipFile
import posixpath
import hashlib
from lxml import etree as E
from .common import ROOT, digest, identity, read_json, safe_path, write_json, writer
from .mathml import NS

VERSION = 'frame-plan-1'
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
ASVG_NS = 'http://schemas.microsoft.com/office/drawing/2016/SVG/main'
MASTER_NS = 'https://lotra.ai/ns/vector-master/1'
CONTENT_TYPES = {'photo', 'svg', 'table', 'text', 'equation'}


def enabled(state):
    return state.get('objectives', {}).get('source_frame_plan') is True


def _resource(base, ref):
    file = safe_path(base, ref['path'])
    if not file.is_file() or digest(file) != ref['sha256']:
        raise ValueError('Frozen frame/content resource changed: '+ref['path'])
    return file


def _box(box):
    if len(box) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box) or min(box[2:]) <= 0:
        raise ValueError('Finite positive frame/content box required')


def required(scene):
    return sorted(o['id'] for o in scene['objects'] if o['render_type'] in CONTENT_TYPES or
                  o['render_type'] == 'shape' and o['content'].get('preset') == 'ellipse')


def discover(state, scene):
    from .source_grids import descriptors
    return {'schema': VERSION, 'source_hash': state['source']['sha256'],
            'source_grids':descriptors(state),
            'required_owners': required(scene),
            'grid_candidates': [{'object': o['id'], 'members': [c['id'] for c in scene['objects'] if c.get('parent') == o['id'] and c['render_type'] in ('photo', 'svg')]}
                                for o in scene['objects'] if o['render_type'] == 'group' and
                                sum(c.get('parent') == o['id'] and c['render_type'] in ('photo', 'svg') for c in scene['objects']) >= 4],
            'return': 'frame_plan matching schemas/frame-plan.json; source facts, semantic windows and user targets stay separate',
            'limits': 'Discovery does not prove original semantic completeness; retain original-feature and source-part review.'}


def validate(plan, base, state=None, scene=None):
    import jsonschema
    jsonschema.validate(plan, read_json(ROOT/'schemas/frame-plan.json'))
    if state and plan['source_hash'] != state['source']['sha256']:
        raise ValueError('Frame plan belongs to another original')
    ids = [f['id'] for f in plan['frames']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate frame identity')
    coverage = {c['object']: c for c in plan['coverage']}
    if len(coverage) != len(plan['coverage']) or set(coverage) != set(plan['scope']):
        raise ValueError('Each scoped owner needs one explicit coverage decision')
    for entry in plan['coverage']:
        if entry['mode'] == 'frame' and entry.get('frame') not in ids:
            raise ValueError('Unknown coverage frame')
        if entry['mode'] == 'inherited' and (not entry.get('mechanism') or state and not state.get('objectives', {}).get(entry['mechanism'])):
            raise ValueError('Inherited coverage needs its enabled existing mechanism')
    owners = {o['id']: o for o in scene['objects']} if scene else None
    if state is not None and scene is not None:
        from .source_grids import validate_frames
        validate_frames(state,scene,plan['frames'])
    if owners is not None:
        if not set(plan['scope']) <= set(owners):
            raise ValueError('Unknown scoped frame owner')
        if not set(required(scene)) <= set(plan['scope']):
            raise ValueError('Drawing omits required frame/content owners; local writing cannot narrow checking')
        for name, entry in coverage.items():
            if owners[name]['render_type'] in CONTENT_TYPES and entry['mode'] == 'not_applicable':
                raise ValueError('Content-bearing owners need a frame or an existing mandatory quality mechanism')
    owned = {}
    for frame in plan['frames']:
        _box(frame['bbox'])
        evidence = [frame['evidence']]
        authority = frame['authority']
        if authority['kind'] == 'user_request':
            ref = authority.get('request')
            if not ref:
                raise ValueError('User layout targets need frozen user-request authority')
            _resource(base, ref)
            if state:
                authorities = state.get('frame_authorities', []) + ([state['user_edit']] if state.get('user_edit') else [])
                if not any(a.get('path') == ref['path'] and a.get('sha256') == ref['sha256'] for a in authorities):
                    raise ValueError('Model proposal cannot grant user layout authority')
        members = frame.get('members', [])
        names = [m['object'] for m in members]
        if frame['kind'] == 'container':
            if not frame.get('body') or not names:
                raise ValueError('Container needs an independent body and semantic fill owners')
            names.append(frame['body'])
            if any(m.get('operation') not in ('check_inside', 'clip_fill') for m in members):
                raise ValueError('Use a finite container operation')
        elif frame['kind'] == 'native_table':
            if not frame.get('table') or not frame.get('table_geometry') or not frame.get('cell_roles'):
                raise ValueError('Native table requires frozen actual tracks, merge anchors and every cell role')
            names.append(frame['table'])
            from .table_slots import planned_boxes
            planned_boxes(frame)
            image_cells={(v['row'],v['column']) for v in frame['cell_roles'] if v['role']=='image'}
            all_cells={(v[0],v[1]) for v in frame['table_geometry']['merges']}
            declared={(v['row'],v['column']) for v in frame['cell_roles']}
            if len(declared)!=len(frame['cell_roles']) or declared!=all_cells:
                raise ValueError('Native table cell-role coverage is incomplete')
            member_cells={(m.get('row'),m.get('column')) for m in members}
            if len(member_cells)!=len(members) or member_cells!=image_cells:
                raise ValueError('Every native image cell must have one full-content member')
            if any(m.get('operation')!='cover' or not m.get('content_window') for m in members):
                raise ValueError('Native table image slots require semantic full-content cover')
        elif frame['kind'] == 'grid':
            rows, cols = frame.get('rows', 0), frame.get('columns', 0)
            cells = {(m.get('row'), m.get('column')) for m in members}
            if len(cells) != len(members) or cells != {(r, c) for r in range(rows) for c in range(cols)}:
                raise ValueError('Grid must cover every declared cell once; no missing/duplicate/extra cells')
            for key, count in [('row_weights', rows), ('column_weights', cols)]:
                if key in frame and len(frame[key]) != count:
                    raise ValueError('Grid track weights mismatch')
            if any(m.get('operation') not in ('cover', 'frame_only') for m in members):
                raise ValueError('Use a finite grid operation')
            if any(m.get('operation') == 'cover' and not m.get('content_window') for m in members):
                raise ValueError('Full-bleed content requires a semantic valid-content window, not alpha/colour heuristics')
        elif frame['kind'] == 'content':
            if not frame.get('object'):
                raise ValueError('Content frame needs an owner')
            names.append(frame['object'])
        if len(names) != len(set(names)) or not set(names) <= set(plan['scope']):
            raise ValueError('Frame ownership expands scope or repeats an owner')
        for name in names:
            if name in owned:
                raise ValueError('Conflicting frames for one owner')
            owned[name] = frame['id']
        if not set(frame.get('palette', {})) <= set(names):
            raise ValueError('Palette rules must bind actual members of this frame')
        windows = [m['content_window'] for m in members if m.get('content_window')]
        if frame.get('content_window'):
            windows.append(frame['content_window'])
        for window in windows:
            _box(window['window']); _resource(base, window['asset'])
            if window['asset_sha256'] != window['asset']['sha256']:
                raise ValueError('Semantic window asset identity mismatch')
            if window.get('source_preview'):
                _resource(base, window['source_preview'])
            for box in window.get('preserve_regions', []):
                _box(box)
            evidence.append(window['evidence'])
        for item in evidence:
            _box(item['roi'])
            if item['source_hash'] != plan['source_hash'] or item['status'] == 'unresolved':
                raise ValueError('Resolve important semantic content/frame uncertainty before execution')
            if item['status'] == 'inferred' and not item.get('constraints'):
                raise ValueError('Inferred geometry needs explicit constraints')
            if state:
                x, y, w, h = item['roi']; sw, sh = state['source_size']
                if min(x, y) < 0 or x+w > sw+.001 or y+h > sh+.001:
                    raise ValueError('Frame evidence outside original')
    for name, item in coverage.items():
        if item['mode'] == 'frame' and owned.get(name) != item.get('frame'):
            raise ValueError('Coverage claim is not backed by actual frame membership')
    return plan


def load(base, ref):
    return read_json(_resource(base, ref))


def bind(task, state, result, scene=None):
    plan = result.get('frame_plan')
    if result.get('frame_plan_ref'):
        plan = load(task, result['frame_plan_ref'])
    if plan is None:
        raise ValueError('Structured frame plan required')
    validate(plan, task, state, scene)
    previous = state.get('frame_plan')
    if previous:
        old = load(task, previous)
        if identity(old) == identity(plan):
            return previous
        if not set(old['scope'])<=set(plan['scope']) or not {f['id'] for f in old['frames']}<={f['id'] for f in plan['frames']}:
            raise ValueError('A frame amendment cannot remove existing scope or frozen frame obligations')
        amendment = plan.get('amendment', {})
        changed = {f['id'] for f in old['frames']} | {f['id'] for f in plan['frames']}
        a, b = {f['id']: f for f in old['frames']}, {f['id']: f for f in plan['frames']}
        changed = {k for k in changed if a.get(k) != b.get(k)}
        if (amendment.get('previous_sha256') != previous['sha256'] or plan['revision'] != old['revision']+1
                or set(amendment.get('changed_frames', [])) != changed):
            raise ValueError('Frame changes need a versioned, exact amendment; never relax a failed target silently')
        for key in set(a) & set(b):
            if b[key].get('tolerance_px', .01) > a[key].get('tolerance_px', .01):
                raise ValueError('Do not widen a frozen geometry/frame tolerance after failure')
    path = Path(task)/'source'/('frame-plan-'+identity(plan)+'.json')
    if not path.exists():
        write_json(path, plan)
    ref = {'path': path.relative_to(Path(task)).as_posix(), 'sha256': digest(path)}
    state.setdefault('frame_plan_history', []).append({'previous': previous, 'current': ref})
    state['frame_plan'] = ref; state.setdefault('objectives', {})['source_frame_plan'] = True
    state.pop('final_frame_plan', None)
    state.pop('acceptance',None)
    return ref


def reconcile_original_palettes(task,state,unit_ids):
    """Compile exact paint from independently frozen original functions.

    A source reobservation may correct an old colour fact. This never derives
    a target from the candidate or widens a range; user paint remains fixed.
    """
    if not state.get('frame_plan'):return None
    from .source_feature_functions import specifications,construct,semantic_root
    previous=copy.deepcopy(state['frame_plan']);plan=copy.deepcopy(load(task,previous));specs=specifications(task,state);changes=[]
    for uid in unit_ids:
        spec=specs.get(uid);unit=state['quality']['units'].get(uid)
        if not spec or not unit:raise ValueError('Frozen original paint function and source owner required')
        objects={o['id']:o for o in construct(task,state,{'id':semantic_root(unit,spec),'roi':unit['roi'],'semantic_class':unit['profile']},spec)}
        for frame in plan['frames']:
            if frame['authority']['kind']!='source':continue
            for name,allowed in frame.get('palette',{}).items():
                if name not in objects:continue
                colour=objects[name]['style'].get('fill')
                if not isinstance(colour,str) or len(colour)!=6 or any(c not in '0123456789abcdefABCDEF' for c in colour):continue
                if colour.upper() in [c.upper() for c in allowed]:continue
                frame['palette'][name]=[colour.upper()]
                changes.append({'frame':frame['id'],'object':name,'unit':uid,'previous_palette':allowed,'original_function_palette':[colour.upper()],
                                'function_hash':identity(spec),'source_evidence':spec['source_evidence']})
    if not changes:return None
    plan['revision']+=1;plan['amendment']={'previous_sha256':previous['sha256'],'changed_frames':sorted({r['frame'] for r in changes}),
        'reason':'Exact original paint recompiled from frozen independent source functions; previous colours/history retained. No geometric or colour tolerance is broadened.'}
    ref=bind(task,state,{'frame_plan':plan})
    state.setdefault('source_palette_revisions',[]).append({'source_hash':state['source']['sha256'],'previous':previous,'current':ref,'changes':changes})
    state.pop('quality_result',None);return ref


def bind_task(task,request):
    from . import agent_runtime as a
    task,state=a._state(task)
    scene=read_json(_resource(task,state['scene'])) if state.get('scene') else a._scene(task,state)
    with writer(task):
        result=bind(task,state,request,scene)
        if (state.get('packet') or {}).get('kind')=='frame_plan_source':state['packet']=None
        a._save(task,state)
    return result


def source_packet(task, state, scene):
    if not enabled(state):
        return None
    if not state.get('frame_plan'):
        return discover(state, scene)
    plan=load(task,state['frame_plan'])
    if not set(required(scene)) <= set(plan['scope']):
        packet=discover(state,scene)
        packet.update(previous=state['frame_plan'],missing_owners=sorted(set(required(scene))-set(plan['scope'])),
                      return_amendment='Preserve previous observations; revision+1, previous hash and exact changed frame IDs required.')
        return packet
    validate(plan, task, state, scene)
    return None


def grid_boxes(frame, scale=1.):
    """Shared integer native boundaries; no per-cell rounding accumulation."""
    x, y, width, height = frame['bbox']; gx, gy = frame.get('gap', [0., 0.])
    def tracks(start, total, count, gap, weights):
        usable = total-gap*(count-1)
        if usable <= 0:
            raise ValueError('Grid gaps consume its frame')
        weights = weights or [1.]*count; denominator = sum(weights); offset = start; result = []
        for weight in weights:
            end = offset+usable*weight/denominator
            a, b = round(offset*scale)/scale, round(end*scale)/scale
            if b <= a:
                raise ValueError('Grid track disappears in native integer coordinates')
            result.append((a, b)); offset = end+gap
        return result
    columns = tracks(x, width, frame['columns'], gx, frame.get('column_weights'))
    rows = tracks(y, height, frame['rows'], gy, frame.get('row_weights'))
    return {m['object']: [columns[m['column']][0], rows[m['row']][0],
                           columns[m['column']][1]-columns[m['column']][0], rows[m['row']][1]-rows[m['row']][0]] for m in frame['members']}


def window_content(window):
    result = copy.deepcopy(window['asset'])
    if window.get('source_preview'):
        result['preview'] = copy.deepcopy(window['source_preview'])
    return result


def compile_scene(scene, base, allowed=None):
    """Compile the frozen framework before any native drawing."""
    ref = scene.get('frame_plan')
    if not ref:
        return scene
    plan = validate(load(base, ref), base, scene=scene)
    result = copy.deepcopy(scene); nodes = {o['id']: o for o in result['objects']}
    scale = round(scene['canvas']['target_width_inches']*914400)/scene['canvas']['width']
    def permit(name, fields):
        if allowed is not None and not set(fields) <= set(allowed.get(name, [])) and allowed.get(name) not in (['add'], ['replace_component']):
            raise ValueError('Frame compilation needs explicit leaf grants: '+name+' '+repr(fields))
    from .content_viewport import normalize
    for frame in plan['frames']:
        boxes = grid_boxes(frame, scale) if frame['kind'] == 'grid' else ({frame['object']: frame['bbox']} if frame['kind'] == 'content' else {})
        if frame['kind']=='native_table':
            from .table_slots import planned_boxes
            boxes=planned_boxes(frame)
        members = frame.get('members', []) if frame['kind'] != 'content' else [{'object': frame['object'], 'content_window': frame.get('content_window')}]
        for member in members:
            name = member['object']; obj = nodes[name]
            # Scoped commits inherit every ungranted field from the actual
            # baseline. Do not recompile an unrelated stored source recipe.
            fields = set(allowed.get(name, [])) if allowed is not None else None
            if fields is not None and not fields:
                continue
            if name in boxes and any(abs(a-b)>1e-10 for a,b in zip(obj['bbox'],boxes[name])):
                needed = {'bbox.left', 'bbox.top', 'bbox.width', 'bbox.height'}
                if fields is None or needed <= fields or fields & {'add','replace_component'}:
                    permit(name, sorted(needed)); obj['bbox'] = boxes[name]
            if member.get('content_window') and (fields is None or fields & {'media','add','replace_component'}):
                window = member['content_window']
                normalized = normalize(window_content(window), window['render_type'], window, obj['bbox'], base)
                obj['content'].update(normalized)
            if frame['kind'] == 'container' and member['operation'] == 'clip_fill' and (fields is None or fields & {'geometry','add','replace_component'}):
                permit(name, ['geometry'])
                fingerprint = identity({k:obj.get(k) for k in ('bbox','rotation')} | {'contours':obj['content'].get('contours')})
                marker = obj['content'].get('frame_clip')
                if marker == {'plan':identity(frame),'geometry':fingerprint}:
                    continue
                from .source_preset_fit import clip_plane_to_ellipse
                clipped = clip_plane_to_ellipse(obj, {'preset': 'ellipse', 'bbox': frame['bbox'], 'source_evidence': frame['evidence'],
                    'semantic_role': 'continuous_background_plane', 'precision_px': frame.get('clip_precision_px', .01), 'inset_px': frame.get('clip_inset_px', .02)})
                nodes[name].update(clipped)
                clipped['content']['frame_clip'] = {'plan':identity(frame),'geometry':identity({k:clipped.get(k) for k in ('bbox','rotation')} | {'contours':clipped['content'].get('contours')})}
    return result


def _media(z, node, vector=False):
    rels = E.fromstring(z.read('ppt/slides/_rels/slide1.xml.rels'))
    mapping = {r.get('Id'): r.get('Target') for r in rels if r.get('TargetMode') != 'External'}
    element = node.find('.//{'+ASVG_NS+'}svgBlip') if vector else node.find('.//a:blip', NS)
    rid = element.get('{'+R_NS+'}embed') if element is not None else None
    if rid not in mapping:
        return None
    target = (mapping[rid].lstrip('/') if mapping[rid].startswith('/') else
              posixpath.normpath(posixpath.join('ppt/slides', mapping[rid])))
    if target.startswith('../') or target not in z.namelist():
        return None
    return z.read(target)


def check(plan, base, pptx, size):
    """Read actual saved geometry, media and crops. No caller-supplied PASS."""
    validate(plan, base)
    from .boundary_geometry import saved_nodes, inside_ellipse
    from .content_viewport import normalize
    nodes = saved_nodes(pptx, size); items = []
    # Quantization is measured against the same slide-native coordinate scale.
    with ZipFile(pptx) as z:
        canvas = E.fromstring(z.read('ppt/presentation.xml')).find('p:sldSz', NS)
        scale = int(canvas.get('cx'))/size[0]
        for frame in plan['frames']:
            tolerance = frame.get('tolerance_px', .01)
            for name, palette in frame.get('palette', {}).items():
                entry = nodes.get(name, {}); colour = entry.get('node').find('p:spPr/a:solidFill/a:srgbClr', NS) if entry.get('node') is not None else None
                actual = colour.get('val').upper() if colour is not None else None
                items.append({'id': frame['id']+'.palette.'+name, 'status': 'PASS' if actual in [c.upper() for c in palette] else 'FAIL',
                              'passed': actual in [c.upper() for c in palette], 'actual_colour': actual})
            if frame['kind'] == 'container':
                body = nodes.get(frame['body'], {})
                if body.get('frame') is None or max(abs(a-b) for a, b in zip(body['frame'], frame['bbox'])) > tolerance:
                    items.append({'id': frame['id'], 'status': 'FAIL', 'passed': False, 'reason': 'Container frame differs from frozen target'})
                for member in frame['members']:
                    items.append({'id': frame['id']+'.'+member['object'], **inside_ellipse(nodes, frame['body'], member['object'], tolerance)})
                continue
            if frame['kind']=='native_table':
                from .table_slots import boxes as table_boxes
                try:
                    boxes=table_boxes(frame,nodes)
                    items.append({'id':frame['id']+'.native_tracks','kind':'native_table','passed':True,'status':'PASS'})
                except (ValueError,KeyError) as error:
                    items.append({'id':frame['id']+'.native_tracks','kind':'native_table','passed':False,'status':'UNMEASURED','reason':str(error)})
                    continue
            else:
                boxes = grid_boxes(frame, scale) if frame['kind'] == 'grid' else {frame['object']: frame['bbox']}
            members = frame.get('members', []) if frame['kind'] in ('grid','native_table') else [{'object': frame['object'], 'content_window': frame.get('content_window')}]
            for member in members:
                name = member['object']; entry = nodes.get(name, {}); expected = boxes[name]
                item = {'id': frame['id']+'.'+name, 'object': name, 'kind': frame['kind'], 'expected_frame': expected,
                        'actual_frame': entry.get('frame'), 'status': 'UNMEASURED', 'passed': False}
                if entry.get('error') or not entry.get('axis_aligned') or not entry.get('frame'):
                    item['reason'] = entry.get('error') or 'Unsupported rotated frame'; items.append(item); continue
                delta = max(abs(a-b) for a, b in zip(entry['frame'], expected))
                item.update(frame_error_source_px=delta, status='PASS' if delta <= tolerance else 'FAIL', passed=delta <= tolerance)
                if member.get('content_window'):
                    window = member['content_window']
                    fill = entry['node'].find('p:blipFill', NS)
                    stretch = fill.find('a:stretch', NS) if fill is not None else None
                    fill_rect = stretch.find('a:fillRect', NS) if stretch is not None else None
                    props = entry['node'].find('p:spPr', NS)
                    geom = props.find('a:prstGeom', NS) if props is not None else None
                    blip = fill.find('a:blip', NS) if fill is not None else None
                    paint_supported = (entry.get('tag') == 'pic' and stretch is not None and fill.find('a:tile', NS) is None
                        and fill_rect is not None and all(float(fill_rect.get(k,0)) == 0 for k in ('l','t','r','b'))
                        and geom is not None and geom.get('prst') == 'rect'
                        and not any(props.find('a:'+k, NS) is not None for k in ('effectDag','scene3d','sp3d'))
                        and not len(props.find('a:effectLst',NS) or [])
                        and blip is not None and all(E.QName(c).localname == 'extLst' for c in blip))
                    if not paint_supported:
                        item.update(status='UNMEASURED',passed=False,reason='Unsupported picture fill/geometry/effect; full content cannot be certified')
                        items.append(item); continue
                    vectors = entry['node'].findall('.//{'+ASVG_NS+'}svgBlip')
                    masters = entry['node'].findall('.//{'+MASTER_NS+'}vectorMaster')
                    if masters or len(vectors) != (1 if window['render_type']=='svg' else 0):
                        item.update(status='FAIL',passed=False,reason='Normalized media has conflicting/missing saved vector or paper-export authority')
                        items.append(item); continue
                    content = normalize(window_content(window), window['render_type'], window, expected, base)
                    actual = _media(z, entry['node'], window['render_type'] == 'svg')
                    actual_hash = hashlib.sha256(actual).hexdigest() if actual is not None else None
                    source_crop = entry['node'].find('.//a:srcRect', NS)
                    crop = [float(source_crop.get(k, 0))/100000 if source_crop is not None else 0. for k in ('l', 't', 'r', 'b')]
                    expected_crop = content['viewport']['native_crop']
                    media_pass = actual_hash == content['sha256']
                    if window['render_type'] == 'svg':
                        preview = _media(z, entry['node'])
                        preview_hash = hashlib.sha256(preview).hexdigest() if preview is not None else None
                        preview_pass = preview_hash == content['preview']['sha256']
                        item.update(compatibility_preview_sha256=preview_hash, compatibility_preview_pass=preview_pass)
                        media_pass = media_pass and preview_pass
                    if member.get('operation') == 'cover':
                        from PIL import Image
                        preview_file = content.get('preview', content)
                        with Image.open(safe_path(base,preview_file['path'])) as image:
                            alpha_min = image.convert('RGBA').getchannel('A').getextrema()[0]
                        item['normalized_full_rectangle_alpha_min'] = alpha_min
                        media_pass = media_pass and alpha_min == 255
                    crop_pass = max(abs(a-b) for a, b in zip(crop, expected_crop)) <= .00002
                    item.update(effective_content_media_sha256=actual_hash, expected_media_sha256=content['sha256'],
                                native_crop=crop, expected_crop=expected_crop, semantic_window=window['window'],
                                valid_content_pass=media_pass and crop_pass,
                                limits='Validity inherits the frozen source semantic observation; opaque background is not treated as valid merely by alpha.')
                    if not media_pass or not crop_pass:
                        item.update(status='FAIL', passed=False, reason='Saved media/crop is not the normalized semantic content')
                items.append(item)
    return {'schema': VERSION, 'plan_hash': identity(plan), 'pptx_sha256': digest(pptx), 'source_hash': plan['source_hash'],
            'status': 'PASS' if items and all(i['passed'] for i in items) else ('NOT_APPLICABLE' if not plan['frames'] else 'FAIL'),
            'passed': bool(items) and all(i['passed'] for i in items), 'items': items,
            'scope': plan['scope'], 'limits': 'Saved geometric/content checks; actual host render, original semantic review and protected properties are separate mandatory evidence.'}


def guard(task, state, candidate, strict=False, report_only=False):
    if not enabled(state):
        if strict:
            raise ValueError('Final frame/content acceptance requires bindings; LEGACY_UNBOUND cannot pass')
        return {'status': 'LEGACY_UNBOUND', 'passed': None}
    if not state.get('frame_plan'):
        raise ValueError('Bind the mandatory frame/content plan before controlled adoption/export')
    scene=read_json(_resource(task,candidate['scene']))
    plan = validate(load(task, state['frame_plan']), task, state, scene)
    pptx = _resource(task, candidate['pptx'])
    result = check(plan, task, pptx, state['source_size'])
    # A complete no-applicable decision still relies on the enabled inherited
    # quality mechanisms; it never becomes a geometric measurement PASS.
    if result['status'] == 'NOT_APPLICABLE':
        result['eligible'] = all(c['mode'] != 'frame' for c in plan['coverage'])
    else:
        result['eligible'] = result['passed']
    write_json(pptx.parent/'frame-plan-check.json', result)
    if strict and not result['eligible']:
        raise ValueError('Saved frame/content constraints failed; inspect '+str(pptx.parent/'frame-plan-check.json'))
    selected=state.get('selected')
    if not strict and selected and selected['pptx']['sha256']!=candidate['pptx']['sha256']:
        prior=check(plan,task,_resource(task,selected['pptx']),state['source_size'])
        previous={i['id']:i for i in prior['items']}
        regressed=[i['id'] for i in result['items'] if previous.get(i['id'],{}).get('passed') and not i['passed']]
        if regressed:
            if not report_only:raise ValueError('A previously satisfied frame/content rule regressed')
            result.update(passed=False,eligible=False,status='FAIL',previously_satisfied_regressions=regressed,
                next_action='Repair the regressed source frame/content rule or bind an explicit user layout amendment; regression remains failed')
            write_json(pptx.parent/'frame-plan-check.json',result)
    if strict:
        if not candidate.get('render') or not candidate.get('preview'):
            raise ValueError('Actual host render remains required before final frame acceptance')
        receipt=read_json(_resource(task,candidate['render']))
        preview=_resource(task,candidate['preview'])
        if receipt.get('pptx_hash')!=candidate['pptx']['sha256'] or receipt.get('preview_hash')!=digest(preview):
            raise ValueError('Actual render/preview must bind this saved candidate')
    return result


def register_failures(task, state, candidate):
    """Locate saved frame failures in the existing finite issue/repair queue."""
    if not enabled(state):
        return {'status':'LEGACY_UNBOUND','passed':None}
    if not state.get('frame_plan'):
        result={'status':'REQUIRES_SOURCE_BINDING','passed':False,'items':[]}
        candidate['frame_plan_actual']=result
        return result
    plan=validate(load(task,state['frame_plan']),task,state)
    result=check(plan,task,_resource(task,candidate['pptx']),state['source_size'])
    write_json(_resource(task,candidate['pptx']).parent/'frame-plan-check.json',result)
    scene=read_json(_resource(task,candidate['scene']))
    parents={o['id']:o.get('parent') for o in scene['objects']}
    components={c['id']:c for c in state.get('analysis',{}).get('components',[])}
    owners={o['id']:cid for cid,built in state.get('built',{}).items() for o in built.get('objects',[])}
    for item in result['items']:
        iid='frame-'+identity(item['id'])[:14]
        known=next((i for i in state.setdefault('issues',[]) if i['id']==iid),None)
        if item['passed']:
            if known:
                evidence={'candidate':candidate['pptx']['sha256'],'measurement':item}
                if candidate['pptx']['sha256']==(state.get('selected') or {}).get('pptx',{}).get('sha256'):
                    known.update(status='resolved',resolution=evidence);known.pop('pending_resolution',None)
                else:known['pending_resolution']=evidence
            continue
        frame=next(f for f in plan['frames'] if item['id']==f['id'] or item['id'].startswith(f['id']+'.'))
        name=item.get('object') or frame.get('body') or frame.get('object') or frame.get('table')
        while name not in owners and parents.get(name):name=parents[name]
        owner=owners.get(name,name)
        if owner not in components:
            raise ValueError('Frame failure needs its semantic component mapping: '+item['id'])
        finding={'id':iid,'owner':owner,'roi':frame['evidence']['roi'],'property':'frame:'+frame['kind'],
                 'severity':'major','status':'open','expected':'Frozen frame/content '+frame['id'],
                 'actual':item,'frame_contract':frame['id'],'source':'program_actual_saved_frame',
                 'attempt_count':0,'cause_hint':'frame:'+frame['id'],
                 'evidence':{'candidate':candidate['pptx']['sha256'],'measurement':item['id']}}
        if known:known.update(actual=item,status='open')
        else:state['issues'].append(finding)
    candidate['frame_plan_actual']=result
    return result


def mirror_saved(scene, pptx, plan, base, allowed):
    """Keep a frame edit's scene mirror tied to saved media/local geometry.

    The actual PPT snapshot remains authoritative; this never reconstructs
    unrelated typography or invents a new semantic component inventory.
    """
    from .relative_layout import mirror_native_positions
    from .boundary_geometry import saved_nodes
    from .content_viewport import normalize
    result=mirror_native_positions(scene,pptx,allowed)
    nodes=saved_nodes(pptx,[scene['canvas']['width'],scene['canvas']['height']])
    objects={o['id']:o for o in result['objects']}
    for frame in plan['frames']:
        members=frame.get('members',[]) if frame['kind']!='content' else [{'object':frame['object'],'content_window':frame.get('content_window')}]
        for member in members:
            name=member['object'];fields=set(allowed.get(name,[]))
            if not fields:continue
            obj=objects[name];entry=nodes[name]
            for index,field in enumerate(('bbox.left','bbox.top','bbox.width','bbox.height')):
                if field in fields:obj['bbox'][index]=entry['frame'][index]
            if member.get('content_window') and fields & {'media','replace_component'}:
                window=member['content_window']
                obj['content'].update(normalize(window_content(window),window['render_type'],window,entry['frame'],base))
                obj['render_type']=window['render_type']
            if frame['kind']=='container' and fields & {'geometry','replace_component'}:
                contours=[]
                for path in entry['node'].findall('p:spPr/a:custGeom/a:pathLst/a:path',NS):
                    width,height=float(path.get('w')),float(path.get('h'));commands=[]
                    for command in path:
                        commands.append({'op':E.QName(command).localname,'points':[[float(p.get('x'))/width,float(p.get('y'))/height] for p in command]})
                    contours.append({'closed':any(c['op']=='close' for c in commands),'commands':commands})
                if not contours:raise ValueError('Saved frame geometry cannot be mirrored')
                obj['content'].pop('geometry_ref',None);obj['content']['contours']=contours
                obj['content']['frame_clip']={'plan':identity(frame),'geometry':identity({k:obj.get(k) for k in ('bbox','rotation')} | {'contours':contours})}
    return result


def layout_target(task, state, pptx, row, frames):
    """A user-authorized full-content grid can supersede only its own gaps/anchors.

    Original observations and source error remain in the report. Neighbour
    relations and source-authority frames retain the existing source contract.
    """
    if not state.get('frame_plan') or row['kind'] not in ('separation','alignment'):
        return None
    plan=validate(load(task,state['frame_plan']),task,state)
    names=set(row['objects'])
    matches=[f for f in plan['frames'] if f['kind']=='grid' and f['authority']['kind']=='user_request' and
             names <= {m['object'] for m in f['members'] if m.get('operation')=='cover'}]
    if not matches:
        return None
    if len(matches)!=1:
        raise ValueError('Ambiguous user target for a source relation')
    frame=matches[0];checked=check(plan,task,pptx,state['source_size'])
    if not checked['passed']:
        return {'id':row['id'],'kind':row['kind'],'objects':row['objects'],'status':'required_unmeasured',
                'error':'User-target frame/content gate not satisfied'}
    from .relative_layout import measure
    with ZipFile(pptx) as z:
        canvas=E.fromstring(z.read('ppt/presentation.xml')).find('p:sldSz',NS)
    boxes=grid_boxes(frame,int(canvas.get('cx'))/state['source_size'][0])
    expected_frames={n:{'box':boxes[n],'frame':boxes[n],'error':None,'order':frames[n]['order']} for n in names}
    actual_frames={n:{'box':frames[n]['frame'],'frame':frames[n]['frame'],'error':None,'order':frames[n]['order']} for n in names}
    expected=measure(row,expected_frames)
    metric='gap_px' if row['kind']=='separation' else 'anchor_offset_px'
    target=expected['values'][metric];active=copy.deepcopy(row)
    epsilon=frame.get('tolerance_px',.01)*2
    active['interval']=[target-epsilon,target+epsilon]
    result=measure(active,actual_frames);actual=result['values'][metric];low,high=row['interval']
    result['values'].update(source_relative_error_px=abs(actual-(low+high)/2),
                            original_interval_violation_px=max(0.,low-actual,actual-high),
                            user_target_error_px=abs(actual-target))
    result.update(original_source_interval=row['interval'],target_authority=frame['authority'],
                  target_frame=frame['id'],measurement_domain='actual_saved_semantic_content_frame_user_target')
    return result
