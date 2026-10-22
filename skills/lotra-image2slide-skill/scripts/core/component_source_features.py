"""Independent original feature inventory, native correspondence and reviews.

Programs validate evidence identity and coverage; semantic truth remains an
explicit current host/human judgment. Fixed construction is not visual PASS.
"""
import copy
from .common import identity, read_json, write_json, safe_path, digest, writer

VERSION = 'source-features-1.34.0'
KINDS = {'silhouette','surface','internal_line','color_region','hole','symbol',
         'text','math','curve','band','detail','relation','texture'}
CAPABILITIES = {'editable','closed_contour','smooth_contour','corners','hole',
                'color_partition','variable_width','inner_wall','shared_edges',
                'surface_shading','projection','occlusion','text','math','independent_parts'}
TIERS = {'native_text':0,'native_math':0,'native_connector':0,'preset':1,
         'native_composite':2,'native_surface':2,'native_path':3,
         'native_cubic':3,'raster_exception':4}


def enabled(contract):
    return contract.get('workflow_version') in ('1.34.0', '1.35.0', '1.35.1','1.35.2')


def _box(roi, size):
    from .component_metrics import window
    window(roi, size)
    return roi


def validate_observation(value, source_hash, size):
    from .component_protocol import finite
    finite(value)
    if (value.get('schema') not in (VERSION, 'source-features-1.35.0', 'source-features-1.35.1') or value.get('source_hash') != source_hash or
            value.get('canvas') != list(size) or value.get('basis') != 'unchanged_original' or
            value.get('observer') not in ('host_model','human') or not value.get('observations')):
        raise ValueError('SOURCE_OBSERVATION_REQUIRED: independent located original observations')
    if any(k in value for k in ('pptx_hash','preview_hash','owners','feature_bindings','candidate')):
        raise ValueError('Original observation precedes native ownership and candidate judgments')
    units, features = value.get('units', []), value.get('features', [])
    if (not units or len(units) > 20000 or len({u.get('id') for u in units}) != len(units) or
            not features or len(features) > 50000 or len({f.get('id') for f in features}) != len(features)):
        raise ValueError('Distinct bounded original units and visible feature IDs required')
    by_unit = {u['id']:u for u in units}
    for unit in units:
        if not unit.get('id') or not unit.get('source_evidence'):
            raise ValueError('Every recursive source unit needs located evidence')
        _box(unit['roi'], size)
        seen = {unit['id']}; parent = unit.get('parent')
        while parent:
            if parent not in by_unit or parent in seen:
                raise ValueError('Original semantic hierarchy is missing a parent or cyclic')
            seen.add(parent); parent = by_unit[parent].get('parent')
        children = [u['id'] for u in units if u.get('parent') == unit['id']]
        stop = unit.get('decomposition', {})
        if stop.get('state') not in ('split','leaf','unresolved') or not stop.get('reason'):
            raise ValueError('Declare a source-supported recursive stop or unresolved boundary')
        if (stop['state']=='split') != bool(children):
            raise ValueError('Decomposition state must match actual source children')
    for feature in features:
        if (not feature.get('id') or feature.get('unit') not in by_unit or
                feature.get('kind') not in KINDS or not feature.get('source_evidence') or
                feature.get('observability') not in ('clear','partial','unresolved') or
                type(feature.get('required', True)) is not bool):
            raise ValueError('Located typed visible feature and explicit observability required')
        if any(k in feature for k in ('owners','component','representation','native_owner')):
            raise ValueError('Freeze original features before choosing native owners')
        _box(feature['roi'], size)
        if set(feature.get('requirements', []))-CAPABILITIES:
            raise ValueError('Unsupported source representation requirement')
        if not feature.get('required', True) and not feature.get('not_required_reason'):
            raise ValueError('Optional original features need an explicit source/scope reason')
        if not feature.get('required', True) and (feature['observability']=='clear' or feature['kind'] not in ('detail','texture')):
            raise ValueError('Visible structure/content cannot be made optional to waive coverage')
        if feature.get('metrics'):
            from .component_metric_adapters import validate_metrics
            validate_metrics({'metrics':feature['metrics']})
            if any(m.get('role') != 'target' or type(m.get('threshold')) not in (int,float)
                   for m in feature['metrics']):
                raise ValueError('Original feature probes need pre-frozen executable target bounds')
    for unit in units:
        if not any(f['unit']==unit['id'] for f in features):
            raise ValueError('Every observed source unit needs a feature, including assembly structure')
    if value['schema'] in ('source-features-1.35.0', 'source-features-1.35.1'):
        if value.get('spatial',{}).get('schema') != value['schema'].replace('source-features-','spatial-'):
            raise ValueError('Original observation and spatial policy revisions must match explicitly')
        from .spatial_frames import validate_observation as validate_spatial
        validate_spatial(value)
    return value


def observe(task, request):
    from .workflow_guard import require
    require(task,'original observation')
    from . import agent_runtime as a
    from .component_workflow import _ref, _load, _resource
    task, state = a._state(task)
    value = copy.deepcopy(request.get('observation', request))
    validate_observation(value, state['source']['sha256'], state['source_size'])
    from .line_contracts import validate_source
    validate_source(value,state)
    for ref in value.get('source_views', []): _resource(task, ref)
    prior = state.get('source_feature_observation')
    contract, ledger = _load(task, state) if state.get('component_workflow') else (None, None)
    if prior:
        old = read_json(_resource(task, prior))
        if old == value:
            return {'status':'SOURCE_OBSERVATION_RETAINED','observation':prior,'acceptance':False}
        if not request.get('revision_reason'):
            raise ValueError('Explain and retain an original-observation revision')
        from .spatial_frames import correction_guard
        correction_guard(old, value, request)
        old_features = {f['id']:f for f in old['features']}
        new_features = {f['id']:f for f in value['features']}
        removed = [key for key,f in old_features.items() if f.get('required', True) and key not in new_features]
        demoted = [key for key,f in old_features.items() if f.get('required', True) and
                   key in new_features and not new_features[key].get('required', True)]
        if (removed or demoted) and not request.get('source_corrections'):
            raise ValueError('Required features cannot disappear or become optional to clear a failure')
        # Existing quality bounds remain source-owned. Corrections need explicit
        # located evidence and retain both versions; a new model is not a reset.
        corrected = {c.get('feature'):c for c in request.get('source_corrections', [])}
        if any(not corrected.get(key, {}).get('source_evidence') for key in removed+demoted):
            raise ValueError('Each removed/demoted feature needs a located original-domain correction')
        for key in old_features.keys() & new_features.keys():
            before, after = old_features[key], new_features[key]
            weakened = (set(before.get('requirements',[]))-set(after.get('requirements',[])) or
                        before.get('metrics',[]) != after.get('metrics',[]) or
                        before.get('observability') == 'unresolved' and after.get('observability') != 'unresolved')
            if before.get('line') != after.get('line'):
                correction=corrected.get(key,{})
                if (correction.get('prior_line_hash')!=identity(before.get('line')) or
                        not correction.get('reason') or not correction.get('source_evidence')):
                    raise ValueError('LINE_SOURCE_REQUIRED: retain prior line facts with an explicit located prior_line_hash correction')
                if before.get('line') and after.get('line'):
                    if any(after['line']['limits'][name]>value for name,value in before['line']['limits'].items()
                           if type(value) in (int,float)):
                        raise ValueError('LINE_SOURCE_REQUIRED: source correction cannot widen frozen quality bounds')
                    pairs=[(before['line']['stroke'][field],after['line']['stroke'][field]) for field in ('width','opacity')]
                    for old_end,new_end in zip(before['line']['ends'],after['line']['ends']):
                        pairs.extend((old_end['marker'][field],new_end['marker'][field]) for field in ('width','length'))
                        pairs.append((old_end['attachment']['distance'],new_end['attachment']['distance']))
                    if any(b[1]-b[0]>a[1]-a[0]+1e-9 for a,b in pairs):
                        raise ValueError('LINE_SOURCE_REQUIRED: source correction cannot broaden frozen measurement intervals')
            if weakened and not corrected.get(key,{}).get('source_evidence'):
                raise ValueError('Retain frozen feature targets; a source correction needs located evidence')
    folder = task/'component-workflow'; folder.mkdir(exist_ok=True)
    if state.get('spatial_source_decision'):
        from .problem_control import reserve
        from .component_workflow import component_row
        token=identity({'spatial_observation':value})
        for component in state['spatial_source_decision']['components']:
            reserve(task,state,component_row(task,state,contract,component),'source_reads',token=token)
    file = folder/('Source-observation-'+identity(value)+'.json')
    if not file.exists(): write_json(file, value)
    with writer(task):
        if prior: state.setdefault('source_observation_history', []).append(prior)
        state['source_feature_observation'] = _ref(task, file)
        from .incremental_contract import seal_state
        seal_state(task,state,'source')
        state.pop('spatial_source_decision',None)
        if contract and enabled(contract):
            state['source_observation_rebind_required'] = True
            ledger['source_observation_dirty'] = True
            ledger['final_dirty'] = True
            ledger['final_result'] = None
        state['packet'] = None
        a._event(task, 'source_features_observed', {'observation':state['source_feature_observation']})
        if contract and enabled(contract):
            from .component_workflow import _save_ledger
            _save_ledger(task,state,ledger,'source_observation_changed',{'observation':state['source_feature_observation']})
        else:
            a._save(task, state)
    return {'status':'SOURCE_FEATURES_OBSERVED','observation':state['source_feature_observation'],
            'units':len(value['units']),'features':len(value['features']),'acceptance':False}


def _members(contract, row):
    members = {row['id']}
    if row['route'] == 'assembly':
        while True:
            added = members | {r['id'] for r in contract['components'] if r.get('parent') in members}
            if added == members: break
            members = added
    return members


def _capabilities(nodes):
    caps = set()
    native = all(n['render_type'] not in ('photo','svg','trace','unresolved') for n in nodes)
    if native: caps.add('editable')
    if len(nodes) > 1: caps.update(('independent_parts','occlusion'))
    fills = {identity(n.get('style',{}).get('fill')) for n in nodes if n.get('style',{}).get('fill')}
    for n in nodes:
        if n['render_type']=='table':
            fills.update(identity(s['fill']) for row in n.get('content',{}).get('cell_styles',[])
                         for s in row if s.get('fill'))
    if len(fills) > 1: caps.add('color_partition')
    for n in nodes:
        kind, c, style = n['render_type'], n.get('content',{}), n.get('style',{})
        if kind == 'text': caps.add('text')
        if kind == 'equation': caps.add('math')
        if kind == 'table':
            rows = c.get('rows',[])
            caps.update(('closed_contour','text'))
            cells=sum(len(r) for r in rows)-sum(rs*cs-1 for _,_,rs,cs in c.get('merges',[]))
            if cells>1:caps.add('independent_parts')
        if kind=='connector':
            points=c.get('points',[])
            if len(points)>2:
                for a,b,d in zip(points,points[1:],points[2:]):
                    u=[b[i]-a[i] for i in (0,1)];v=[d[i]-b[i] for i in (0,1)]
                    if abs(u[0]*v[1]-u[1]*v[0])>1e-8:
                        caps.add('corners');break
        if kind=='bezier' and (c.get('segments') or len(c.get('points',[]))>=3):
            caps.add('smooth_contour')
        if kind == 'shape':
            caps.add('closed_contour')
            if c.get('preset') in ('ellipse','roundRect'): caps.add('smooth_contour')
            if c.get('preset') != 'ellipse': caps.add('corners')
        if kind in ('path','bezier'):
            caps.add('projection')
            contours = c.get('contours', [])
            if any(p.get('closed') for p in contours): caps.update(('closed_contour','variable_width'))
            for contour in contours:
                if any(p.get('op') == 'cubicBezTo' for p in contour.get('commands', [])): caps.add('smooth_contour')
                if contour.get('points') or any(p.get('op') == 'lnTo' for p in contour.get('commands', [])): caps.add('corners')
        if style.get('gradient'): caps.add('surface_shading')
        surface = c.get('source_surface', {})
        if surface.get('version') in ('native-surfaces-1.34.0', 'native-surfaces-1.35.0'):
            caps.update(surface.get('capabilities', []))
    return caps


def capability_preflight(binding, feature, nodes):
    representation = binding.get('representation', {})
    family = representation.get('family')
    if family not in TIERS: raise ValueError('REPRESENTATION_DECISION_REQUIRED: registered native family')
    if feature.get('kind') in ('text','math') and family != {'text':'native_text','math':'native_math'}[feature['kind']]:
        raise ValueError('Exact native text and genuine structured Office Math cannot become shape pictures')
    selected = [nodes[name] for name in binding['owners']]
    kinds = {n['render_type'] for n in selected}
    if family == 'preset' and (len(selected) != 1 or kinds != {'shape'}):
        raise ValueError('Preset representation must actually be one native preset')
    if family in ('native_path','native_cubic') and not kinds <= {'path','bezier'}:
        raise ValueError('Path representation must bind actual native paths')
    if family == 'native_surface' and not all(n.get('content',{}).get('source_surface') for n in selected):
        raise ValueError('Native surface family requires compiled source-owned faces')
    if family in ('native_text','native_math','native_connector'):
        expected = {'native_text':'text','native_math':'equation','native_connector':'connector'}[family]
        table_text = family=='native_text' and feature.get('kind')=='text' and kinds=={'table'} and len(selected)==1
        if table_text:
            cell=representation.get('table_cell')
            rows=selected[0]['content']['rows']
            if (not isinstance(cell,list) or len(cell)!=2 or any(type(i) is not int for i in cell) or
                    not 0<=cell[0]<len(rows) or not 0<=cell[1]<len(rows[0]) or
                    not isinstance(feature.get('text'),str) or feature['text']!=rows[cell[0]][cell[1]]):
                raise ValueError('Native table text needs an exact source literal and current row/column selector')
        elif kinds != {expected}: raise ValueError('Typed native representation differs from its actual owners')
    if family == 'raster_exception':
        if feature['kind'] != 'texture' or not representation.get('exception_reason') or not kinds <= {'photo'}:
            raise ValueError('Raster cannot silently replace a schematic/icon feature')
    elif kinds & {'photo','svg','trace','unresolved'}:
        raise ValueError('Native icon representation cannot hide flattened/pixel-layer output')
    if len(selected) > 128:
        raise ValueError('REPRESENTATION_DECISION_REQUIRED: split meaningful parts instead of pixel strips')
    if TIERS[family] > 1 and family != 'raster_exception':
        rejected = representation.get('simpler_options', [])
        required = {'preset'} | ({'native_composite'} if TIERS[family] > 2 else set())
        if not required <= {r.get('family') for r in rejected if r.get('source_evidence') and r.get('reason')}:
            raise ValueError('Explain the source-supported limitation of simpler native representations')
    capabilities = _capabilities(selected)
    missing = set(feature.get('requirements', []))-capabilities
    if missing:
        raise ValueError('REPRESENTATION_INSUFFICIENT: '+feature['id']+' requires '+','.join(sorted(missing)))
    return {'passed':True,'family':family,'capabilities':sorted(capabilities),'source_truth_claim':False}


def bind(task, state, contract, scene):
    if not enabled(contract): return
    from .component_workflow import _resource
    ref = state.get('source_feature_observation')
    if not ref: raise ValueError('SOURCE_OBSERVATION_REQUIRED: observe this original before native binding')
    observed = read_json(_resource(task, ref))
    validate_observation(observed, state['source']['sha256'], state['source_size'])
    units = {u['id']:u for u in observed['units']}
    declared = {u['id']:u for u in contract['source_inventory']}
    if set(units) != set(declared) or any(any(declared[k].get(f) != units[k].get(f)
            for f in (('parent','roi','decomposition','source_evidence','spatial') if contract.get('workflow_version') in ('1.35.0','1.35.1','1.35.2') else ('parent','roi','decomposition','source_evidence'))) for k in units):
        raise ValueError('Source inventory must retain the independent recursive observation')
    features = {f['id']:f for f in observed['features']}
    bindings = contract.get('feature_bindings', [])
    if len(bindings) != len({b.get('feature') for b in bindings}) or set(features) != {b.get('feature') for b in bindings}:
        raise ValueError('Every original feature needs one explicit correspondence, including unresolved features')
    nodes = {n['id']:n for n in scene['objects']}
    compiled = {part['owner'] for manifest in contract.get('construction_manifests',[]) for part in manifest['parts']}
    if any(n.get('content',{}).get('source_surface') and n['id'] not in compiled for n in scene['objects']):
        raise ValueError('Source surface capabilities must come from registered current constructions')
    rows = {r['id']:r for r in contract['components']}; all_bound = set()
    for binding in bindings:
        if binding.get('component') not in rows:
            raise ValueError('Feature correspondence has an unknown component')
        owner_list = binding.get('owners', [])
        if not owner_list or len(owner_list) != len(set(owner_list)) or not set(owner_list) <= set(nodes):
            raise ValueError('Feature correspondence needs current native owners')
        members = _members(contract, rows[binding['component']])
        permitted = {o for r in contract['components'] if r['id'] in members for o in r['owners']}
        if not set(owner_list) <= permitted:
            raise ValueError('Feature correspondence escaped its component or actual descendants')
        binding['capability_check'] = capability_preflight(binding, features[binding['feature']], nodes)
        all_bound.update(owner_list)
    painted = {n['id'] for n in scene['objects'] if n['render_type'] != 'group'}
    if painted-all_bound:
        raise ValueError('Native paint has no original feature correspondence: '+','.join(sorted(painted-all_bound)[:8]))
    # A native table is one paint owner, but its populated cells remain distinct
    # source text obligations rather than disappearing inside that owner.
    for node in scene['objects']:
        if node['render_type']!='table':continue
        covered={tuple(b['representation']['table_cell']) for b in bindings
                 if node['id'] in b['owners'] and b['representation'].get('family')=='native_text'
                 and isinstance(b['representation'].get('table_cell'),list)}
        missing=[(r,c) for r,row in enumerate(node['content']['rows']) for c,text in enumerate(row)
                 if text and (r,c) not in covered]
        if missing:raise ValueError('Every populated native table cell needs source text correspondence: '+str(missing[:8]))
    contract['source_observation'] = ref
    contract['source_feature_count'] = len(features)
    for row in contract['components']:
        members = _members(contract, row)
        selected = [b for b in bindings if b['component'] in members or set(b['owners']) & set(row['owners'])]
        row['source_features'] = [copy.deepcopy(features[b['feature']]) for b in selected]
        row['feature_bindings'] = copy.deepcopy(selected)
        row['feature_basis'] = identity({'features':row['source_features'],'bindings':selected,
            'units':{f['unit']:units[f['unit']] for f in row['source_features']}})
        row['unresolved_source_units'] = sorted({f['unit'] for f in row['source_features']
            if units[f['unit']]['decomposition']['state']=='unresolved'})
    from .spatial_frames import bind as bind_spatial
    bind_spatial(contract, observed, scene)
    from .line_contracts import compile_contract
    compile_contract(state,observed,contract,scene)


def source_check(row):
    features = row.get('source_features', [])
    unresolved = [f['id'] for f in features if f.get('required', True) and f['observability']=='unresolved']
    unresolved += row.get('unresolved_source_units', [])
    from .spatial_frames import source_check as spatial_source
    spatial = spatial_source(row)
    return {'passed':not unresolved and spatial['passed'],'status':'SOURCE_AMBIGUITY_REQUIRED' if unresolved else spatial['status'] if not spatial['passed'] else 'SOURCE_BASIS_CHECKED',
            'unresolved_features':unresolved,'feature_basis':row.get('feature_basis'),
            'spatial': spatial,
            'basis':'Host/human located original decisions; not program proof of semantic truth'}


def local_review(row, evidence):
    required = {f['id'] for f in row.get('source_features', []) if f.get('required', True)}
    records = evidence.get('feature_checks', [])
    checks = {r.get('feature'):r for r in records}
    if len(records) != len(checks) or not required <= set(checks):
        raise ValueError('FEATURE_REVIEW_REQUIRED: every required current feature needs a located comparison')
    failed = [key for key in required if checks[key].get('verdict') != 'PASS' or not checks[key].get('observations')]
    if evidence.get('feature_basis') != row.get('feature_basis'):
        raise ValueError('Feature review belongs to a different source/representation decision')
    spatial = {'passed': True, 'applicable': False}
    if row.get('spatial_basis'):
        from .spatial_frames import review as spatial_review
        spatial = spatial_review({'workflow_version':'1.35.0','spatial':{'relations':row['spatial_context']['relations']}}, evidence, row)
    return {'passed':not failed and spatial['passed'],'spatial':spatial,'failed_features':sorted(failed),'checked_features':sorted(required),
            'feature_basis':row.get('feature_basis'),'observer':evidence.get('observer')}


def final_review(task, contract, evidence):
    if not enabled(contract): return {'passed':True,'applicable':False,'legacy_policy_retained':True}
    ref = contract['source_observation']; file = safe_path(task, ref['path'])
    if digest(file) != ref['sha256']: raise ValueError('Independent original observation changed')
    observed = read_json(file)
    review = evidence.get('source_feature_review', {})
    if (review.get('source_observation_hash') != ref['sha256'] or
            review.get('bindings_hash') != identity(contract['feature_bindings']) or
            review.get('basis') != 'original_to_output' or not review.get('observations')):
        return {'passed':False,'reason':'INDEPENDENT_ORIGINAL_TO_OUTPUT_REVIEW_REQUIRED'}
    checks = review.get('feature_checks', [])
    by_id = {r.get('feature'):r for r in checks}
    required = {f['id'] for f in observed['features'] if f.get('required', True)}
    missing = sorted(required-set(by_id))
    failed = sorted(k for k in required & set(by_id) if by_id[k].get('verdict') != 'PASS' or not by_id[k].get('observations'))
    units = review.get('omission_checks', [])
    by_unit = {r.get('unit'):r for r in units}
    expected = {u['id'] for u in observed['units']}
    unit_missing = sorted(expected-set(by_unit))
    unit_failed = sorted(k for k in expected & set(by_unit) if by_unit[k].get('verdict') != 'PASS' or not by_unit[k].get('observations'))
    unresolved = [f['id'] for f in observed['features'] if f.get('required', True) and f['observability']=='unresolved']
    unmapped = review.get('unmapped_features', [])
    passed = (len(checks)==len(by_id) and len(units)==len(by_unit) and not
              (missing or failed or unit_missing or unit_failed or unresolved or unmapped))
    return {'passed':bool(passed),'missing_features':missing,'failed_features':failed,
            'omission_units_missing':unit_missing,'omission_units_failed':unit_failed,
            'unresolved_features':unresolved,'unmapped_features':unmapped,
            'source_observation_hash':ref['sha256'],'source_truth_claim':False}


def probes(task, state, candidate, features):
    """Registered original probes measure saved pixels, not donor parameters."""
    from .component_metrics import measure
    from .component_protocol import metric_result
    checks = {}
    for feature in features:
        if not feature.get('metrics'): continue
        component = {'roi':feature['roi'],'metrics':feature['metrics']}
        measured = measure(task,state,candidate,component)
        result = metric_result(component,measured['metrics'])
        result['passed'] = result['passed'] and all(measured['hard_checks'].values())
        checks[feature['id']] = result
    return {'passed':all(c['passed'] for c in checks.values()),'features':checks,
            'scope':'Declared source probes only; semantic coverage needs host/human comparison'}


def diagnostics(task, state, candidate, contract):
    """Located source-edge suspicions guide, but cannot replace, omission review."""
    from .component_workflow import _resource, _ref
    from .appearance_metrics import canvas
    from .adaptive_detail import _edges
    from scipy.ndimage import distance_transform_edt
    from .component_metrics import window
    import numpy as np
    basis = {'source':state['source']['sha256'],'pptx':candidate['pptx']['sha256'],
             'preview':candidate['preview']['sha256'],'observation':contract['source_observation'],
             'version':VERSION,'bindings':identity(contract['feature_bindings'])}
    file = task/'component-workflow'/('Feature-diagnostics-'+identity(basis)+'.json')
    if file.exists(): return _ref(task,file)
    original = canvas(str(_resource(task,state['source'])),state['source']['sha256'],tuple(state['source_size']))
    actual = canvas(str(_resource(task,candidate['preview'])),candidate['preview']['sha256'],tuple(state['source_size']))
    observed = read_json(_resource(task,contract['source_observation'])); rows = []
    for unit in observed['units']:
        x,y,r,b = window(unit['roi'],state['source_size'])
        source_edges,target_edges = _edges(original[y:b,x:r]),_edges(actual[y:b,x:r])
        valid = bool(source_edges.any())
        distance = distance_transform_edt(~target_edges) if target_edges.any() else np.full(source_edges.shape,float('inf'))
        # This is a diagnostic sampling scale, never an acceptance threshold.
        fraction = float(np.mean(distance[source_edges] > 2)) if valid else None
        rows.append({'unit':unit['id'],'roi':unit['roi'],'valid':valid,
                     'unexplained_source_edge_fraction':fraction,'semantic_verdict':'REVIEW_REQUIRED'})
    write_json(file,{'basis':basis,'units':rows,'acceptance':False,
                     'limits':'Low-contrast/noisy/occluded edges may be missed; review every original unit independently.'})
    return _ref(task,file)
