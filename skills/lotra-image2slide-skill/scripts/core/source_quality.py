"""Source-bound part requirements and non-compensating actual-result quality.

This module owns coverage debt and fixed targets. The host still interprets
source meaning; image measurements never manufacture semantic observations.
Large specifications and geometry remain on disk, not in every work packet.
"""
import copy
import math
import hashlib
from pathlib import Path
from .common import digest, identity, read_json, safe_path, write_json

VERSION = 'source-quality-1'
STATUSES = {'observed', 'inferred', 'unresolved'}
SOURCE_CORRECTION_KINDS = ('source_reading','measurement_domain','additional_detail')
CAUSE_STAGES = ('source_specification','recipe','instance_geometry','z_order','parent_transform','font','render')
PROFILES = {
    'flat': {'mask_iou': (.98, None), 'boundary_f1': (.99, None),
             'internal_edge_f1': (.98, None)},
    'structured': {'boundary_f1': (.96, None), 'internal_edge_f1': (.96, None)},
    'curve': {'internal_edge_f1': (.97, None)},
    'text': {'internal_edge_f1': (.94, None)},
    'formula': {'internal_edge_f1': (.94, None)},
    'three_dimensional': {'internal_edge_f1': (.90, None)},
    'scene': {'internal_edge_f1': (.90, None)},
    'detail': {'boundary_f1': (.97,None), 'internal_edge_f1': (.98,None)},
    'illustration': {},
    'semantic_hd': {},
}
MANDATORY_DIMENSIONS = {
    'text': ('geometry','presence','weight'),
    'formula': ('geometry','presence','weight'),
    'flat': ('geometry','presence','style'),
    'structured': ('geometry','presence','style'),
    'curve': ('geometry','presence','style'),
    'detail': ('geometry','presence','weight'),
    'three_dimensional': ('geometry','presence','style'),
    'scene': ('geometry','presence','style'),
    'illustration': ('geometry','style'),
    'semantic_hd': ('geometry','style'),
}
METRIC_DIMENSIONS = {
    'geometry': {'mask_iou','boundary_f1','internal_edge_f1','internal_hd95','ssim','psnr_db'},
    'presence': {'foreground_f1','foreground_area_ratio'},
    'weight': {'foreground_mass_ratio','foreground_area_ratio'},
    'style': {'foreground_color_p95','color_histogram_tv','foreground_mass_ratio'},
}
PROFILE_COMPLEMENTS = {
    'presence': {'id':'foreground_f1','min':.95,'stretch':.995},
    'weight': {'id':'foreground_mass_ratio','min':.85,'max':1.2,'stretch':1.0},
    'style': {'id':'color_histogram_tv','max':.15,'stretch':0.0},
}
CATEGORIES = {
    'text': {'content', 'typography', 'placement'},
    'formula': {'content', 'typography', 'placement'},
    'semantic_hd': {'content', 'geometry', 'clarity'},
    'illustration': {'content', 'geometry', 'texture'},
}


def enabled(state):
    return state.get('objectives', {}).get('source_part_quality', False)


def _roi(value, size):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError('Source part needs a located ROI')
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise ValueError('Source ROI needs finite values')
    x, y, w, h = value
    if min(x, y) < 0 or min(w, h) <= 0 or x+w > size[0]+.01 or y+h > size[1]+.01:
        raise ValueError('Source part is outside its original canvas')
    return value


def _evidence(item, state):
    status = item.get('status')
    if status not in STATUSES:
        raise ValueError('State must be observed, inferred or unresolved; no default observation')
    evidence = item.get('evidence', {})
    if evidence.get('source_hash') != state['source']['sha256']:
        raise ValueError('Part/property evidence must bind the original source')
    _roi(evidence.get('roi'), state['source_size'])
    if not evidence.get('description'):
        raise ValueError('Evidence needs a concrete visible feature or bounded inference')
    if status == 'inferred' and not item.get('constraints'):
        raise ValueError('Hidden completion needs explicit semantic/geometric constraints')


def coverage_debt(state, component, spec, units=None):
    """Trace declared original semantic parts, independently of output names.

    Explicit source bindings avoid silently counting text inventories as a
    robot/road/scene inspection. Legacy observations remain intact, while
    absent bindings become located work rather than an implicit PASS.
    """
    declared = component.get('parts', [])
    names = [v if isinstance(v, str) else v['id'] for v in declared]
    if len(names) != len(set(names)):
        raise ValueError('Declared source semantic parts must have stable unique IDs')
    units = units if units is not None else {
        uid:u for uid,u in state.get('quality', {}).get('units', {}).items()
        if u['owner'] == component['id']}
    records = spec.get('coverage_bindings', [])
    bound = set();seen=set()
    for record in records:
        name = record.get('source_part')
        if name not in names or name in seen:
            raise ValueError('Coverage binds each declared source part once: '+str(name))
        seen.add(name)
        _evidence(record, state)
        role = record.get('role')
        if role not in ('visual', 'text', 'formula', 'relation'):
            raise ValueError('Coverage declares the original part role explicitly')
        refs = record.get('quality_units', [])
        if not refs or not set(refs) <= units.keys():
            raise ValueError('Coverage requires independent source quality units: '+str(name))
        profiles = {units[uid]['profile'] for uid in refs}
        if role == 'visual' and not profiles - {'text', 'formula', 'relation'}:
            raise ValueError('Text/formula/relation scores cannot cover a visual semantic part: '+name)
        if role in ('text', 'formula', 'relation') and role not in profiles:
            raise ValueError('Coverage needs its declared typed quality unit: '+name)
        if record['status'] != 'unresolved':
            bound.add(name)
    debt = copy.deepcopy(spec.get('unassigned_features', []))
    from .source_math import source_ast
    debt.extend({'quality_unit':uid,'roi':value['roi'],'description':'Read and record exact original mathematical AST; an equation label or correct-looking parent cannot prove scientific content.','kind':'original_formula_ast'} for uid,value in units.items() if value['profile']=='formula' and source_ast(value) is None)
    debt.extend(copy.deepcopy(state.get('quality',{}).get('representation_debt',{}).get(component['id'],[])))
    from .source_ocr import source_literal
    debt.extend({'quality_unit':uid,'roi':value['roi'],
                 'description':'Read and record the exact original text; a generic label/type is not a literal content guide.',
                 'kind':'original_text_literal'} for uid,value in units.items()
                if value['profile']=='text' and source_literal(value) is None)
    debt.extend({'source_part':name, 'roi':component['roi'],
                 'description':'Declared original semantic part lacks an independent source binding: '+name,
                 'kind':'semantic_part_coverage'} for name in names if name not in bound)
    # Natural models must return to the existing original-spec loop when a
    # body/window/band has only a parent or whole-colour score. No new QA loop.
    built=state.get('built',{}).get(component['id'],{})
    mapping=built.get('method',{}).get('source_bindings',{})
    for obj in built.get('objects',[]):
        part=obj.get('content',{}).get('natural_part')
        if not part:continue
        covered=any(u['profile'] not in ('text','formula','relation') and
                    mapping.get(u['part'],u.get('objects',[]))==[obj['id']]
                    for u in units.values())
        if not covered:
            debt.append({'source_part':obj['id'],'roi':component['roi'],
                         'kind':'natural_part_coverage',
                         'description':'Read the original '+part['role']+' independently; bind its named output and contour/stroke/proportion/negative-space properties. Parent scores cannot cover this part.'})
    return debt


def compile_spec(state, component, spec):
    """Compile independent source evidence; never infer it from render objects."""
    from .source_contract import validate_spec
    validate_spec(spec)
    if spec.get('version') != VERSION or spec.get('owner') != component['id']:
        raise ValueError('Source specification must identify its owner and version')
    if spec.get('source_hash') != state['source']['sha256']:
        raise ValueError('Source specification refers to another image')
    if not spec.get('coverage_statement'):
        raise ValueError('Describe source-feature coverage, including unresolved features')
    from .source_grids import validate_source
    validate_source(state,component,spec)
    parts = spec.get('parts', [])
    if not parts:
        raise ValueError('Source specification has no natural parts')
    ids = [p['id'] for p in parts]
    if len(ids) != len(set(ids)):
        raise ValueError('Natural part identifiers must be unique')
    units = {}
    for part in parts:
        _roi(part.get('roi'), state['source_size'])
        profile = part.get('profile')
        if profile not in PROFILES:
            raise ValueError('Unknown part quality profile')
        intent=part.get('quality_intent')
        if state.get('objectives',{}).get('whole_quality_intent') and not state.get('native_import'):
            from .quality_intent import source_declaration
            source_declaration(intent,profile)
        layering=part.get('layering')
        if layering is not None:
            if (not isinstance(layering,dict) or layering.get('role') not in ('underlay','foreground','material')
                    or not isinstance(layering.get('occluders'),list)
                    or any(not isinstance(uid,str) or not uid for uid in layering['occluders'])
                    or len(layering['occluders'])!=len(set(layering['occluders']))):
                raise ValueError('Declare a typed source layer and unique upper quality-unit IDs')
        features = part.get('features', [])
        if not features:
            raise ValueError('Each natural part needs specific source properties')
        fids = [f['id'] for f in features]
        if len(fids) != len(set(fids)) or any(not f.get('expected') for f in features):
            raise ValueError('Unique property IDs and specific expectations required')
        for feature in features:
            _evidence(feature, state)
        required = CATEGORIES.get(profile, {'content', 'geometry', 'style'})
        if not required <= {f.get('category') for f in features}:
            raise ValueError('Important property categories are missing: ' +
                             ','.join(sorted(required - {f.get('category') for f in features})))
        # An uncertain silhouette must use a frozen, justified source tolerance.
        # It does not turn off clarity or completeness requirements.
        metrics = copy.deepcopy(part.get('metrics'))
        if metrics is None:
            metrics = [{'id': k, 'min': bounds[0], 'max': bounds[1],
                        'stretch': 1. if bounds[0] is not None else None}
                       for k, bounds in PROFILES[profile].items()]
        if not metrics and profile not in ('illustration', 'semantic_hd'):
            raise ValueError('Geometry-bearing part needs an objective measurement')
        names={m.get('id') for m in metrics}
        for dimension in MANDATORY_DIMENSIONS[profile]:
            if not names & METRIC_DIMENSIONS[dimension]:
                if dimension=='geometry':
                    raise ValueError('An illustration/HD part also needs its frozen geometry or perceptual target')
                complement=copy.deepcopy(PROFILE_COMPLEMENTS[dimension])
                metrics.append(complement);names.add(complement['id'])
        if any(f.get('ast') or f.get('math_spans') for f in features if f['category']=='content'):
            if 'math_ast_match' not in names:metrics.append({'id':'math_ast_match','min':1.,'max':1.})
        if profile=='text' and any(f.get('cell_format') for f in features if f['category']=='typography') and 'native_cell_format_match' not in names:
            metrics.append({'id':'native_cell_format_match','min':1.,'max':1.})
        if profile=='text' and 'native_text_match' not in names:
            metrics.append({'id':'native_text_match','min':1.,'max':1.})
        for metric in metrics:
            if not metric.get('id') or (metric.get('min') is None and metric.get('max') is None):
                raise ValueError('Metric needs an explicit frozen minimum or maximum')
            if any(metric.get(k) is not None and
                   (not isinstance(metric[k], (int, float)) or not math.isfinite(metric[k]))
                   for k in ('min', 'max', 'stretch', 'max_regression')):
                raise ValueError('Metric bounds must be finite')
        if part.get('metrics') is not None and not part.get('target_basis'):
            raise ValueError('Custom target needs its source/type/tolerance basis')
        from .typed_metrics import DEFAULT_PROTOCOL
        protocol = {**DEFAULT_PROTOCOL, **part.get('protocol', {})}
        uid = component['id'] + ':' + part['id']
        units[uid] = {'id': uid, 'owner': component['id'], 'part': part['id'],
                      'roi': part['roi'], 'profile': profile, 'features': features,
                      'metrics': metrics, 'protocol': protocol,
                      'priority': part.get('priority', 'major'),
                      'objects': part.get('objects', []),
                      'landmarks': part.get('landmarks', {}),
                      'reference_mask': part.get('reference_mask'),
                      'evaluation_mask': part.get('evaluation_mask'),
                      'target_basis': part.get('target_basis', 'clear geometry initial target'),
                      'source_feature_ids': part.get('source_feature_ids', fids),
                      'appearance_policy': part.get('appearance_policy', 'faithful'),
                      **({'quality_intent':copy.deepcopy(intent)} if intent else {}),
                      'source_word_anchor':copy.deepcopy(part.get('source_word_anchor')),
                      **({'layering':copy.deepcopy(part['layering'])} if part.get('layering') else {}),
                      'status': 'required_unmeasured'}
    if state.get('objectives',{}).get('source_relative_layout'):
        review=spec.get('layout_review') or {}
        if (review.get('source_hash')!=state['source']['sha256']
                or not review.get('evidence') or not review.get('scope')
                or not isinstance(review.get('important_relation_ids'),list)):
            raise ValueError('Complete the source-bound layout_review before constructing this owner')
        expected=set(review['important_relation_ids'])
        executable={r['id'] for r in spec.get('relations',[])
                    if r.get('measurement',{}).get('kind')=='relative_layout'}
        if not expected<=executable:
            raise ValueError('Every declared important layout relation needs its executable contract')
    for relation in spec.get('relations', []):
        if relation.get('measurement',{}).get('kind')=='relative_layout':
            from .relative_layout import validate
            validate(relation['measurement']['contract'],state)
            if not relation.get('metrics'):
                raise ValueError('Executable relative layout needs independent frozen metric limits')
        _evidence(relation, state)
        _roi(relation.get('roi'), state['source_size'])
        if not relation.get('id') or not relation.get('expected') or not relation.get('participants'):
            raise ValueError('Relation needs identity, participants and exact expectation')
        uid = component['id'] + ':relation.' + relation['id']
        if uid in units:
            raise ValueError('Duplicate relation requirement')
        units[uid] = {'id': uid, 'owner': component['id'], 'roi': relation['roi'],
                      'profile': 'relation', 'part': relation['id'],
                      'features': [{'id': relation['id'], 'category': 'relation',
                                    'expected': relation['expected'], 'status': relation['status'],
                                    'evidence': relation['evidence'],
                                    'constraints': relation.get('constraints')}],
                      'metrics': relation.get('metrics', []),
                      'protocol': copy.deepcopy(relation.get('protocol', {})),
                      'priority': 'critical', 'objects': relation.get('objects', []),
                      'participants': relation['participants'], 'relation': relation,
                      'status': 'required_unmeasured'}
    unresolved = spec.get('unassigned_features', [])
    if unresolved and any(not f.get('roi') or not f.get('description') for f in unresolved):
        raise ValueError('Unassigned source features need located descriptions')
    coverage_debt(state, component, spec, units)
    return units


def revise_spec(state, component, correction, source_views):
    """Correct a source reading/domain with source evidence, never a failing score."""
    q=state['quality'];owner=component['id'];old=q['specifications'][owner]
    if correction.get('prior_spec_hash')!=identity(old):
        raise ValueError('Source correction must name the immutable prior reading')
    if (not correction.get('reason') or correction.get('source_view_hash') not in source_views
            or correction.get('kind') not in SOURCE_CORRECTION_KINDS):
        raise ValueError('Use the paired original view and identify the epistemic correction')
    revised=correction['specification'];units=compile_spec(state,component,revised)
    previous={u['id']:u for u in q['units'].values() if u['owner']==owner}
    if not previous.keys()<=units.keys():
        raise ValueError('Correction cannot silently delete important parts/relationships')
    changed=[]
    for uid,before in previous.items():
        after=units[uid]
        if not {f['id'] for f in before['features']}<={f['id'] for f in after['features']}:
            raise ValueError('Keep the original source-property inventory and reading history')
        a={m['id']:m for m in before['metrics']};b={m['id']:m for m in after['metrics']}
        if not a.keys()<=b.keys():raise ValueError('Do not remove a failed objective')
        for name,rule in a.items():
            if ((rule.get('min') is not None and (b[name].get('min') is None or b[name]['min']<rule['min']))
                or (rule.get('max') is not None and (b[name].get('max') is None or b[name]['max']>rule['max']))):
                raise ValueError('Source correction cannot lower an objective to admit a candidate')
        mutable={'status','built_fingerprint'}
        if identity({k:v for k,v in before.items() if k not in mutable})==identity({k:v for k,v in after.items() if k not in mutable}):
            units[uid]=before
        else:changed.append(uid)
    changed.extend(uid for uid in units if uid not in previous)
    q.setdefault('source_history',[]).append({'owner':owner,'prior_spec_hash':identity(old),
        'source_view_hash':correction['source_view_hash'],'kind':correction['kind'],
        'reason':correction['reason'],'prior_specification':old,'changed':changed})
    q['specifications'][owner]=copy.deepcopy(revised);q['units'].update(units)
    if state.get('objectives',{}).get('source_contract_seals'):q.setdefault('_pending_source_seals',[]).append(owner)
    q['coverage_debt'][owner]=coverage_debt(state,component,revised,units)
    if owner in q.get('source_queue',[]):q['source_queue'].remove(owner)
    component['source_spec']=copy.deepcopy(revised)
    for uid in changed:q['observations'].pop(uid,None)
    return ['quality:'+uid for uid in changed]


def amend_task(task,request):
    """Original-only source refinement of a saved, completely imported task.

    The same compiler, immutable prior hash and non-relaxation checks serve
    ordinary packets and this public continuation. No native drawing is
    rebuilt and no observed/accepted status is manufactured.
    """
    from . import agent_runtime as a,execution_contract as ec
    from .semantic_composition import _original_view
    from .common import writer
    task,state=a._state(task);ec.policy(state)
    candidate=state.get('active_candidate') or state.get('selected')
    if (not candidate or request.get('source_hash')!=state['source']['sha256'] or
            request.get('expected_pptx_sha256')!=candidate['pptx']['sha256']):
        raise ValueError('Source refinement requires the exact original and current saved drawing')
    view=request['source_view'];_original_view(task,state,view)
    correction=request['correction']
    if correction.get('source_view_hash')!=view['sha256']:raise ValueError('Use the verified raw original view')
    owner=correction['specification']['owner']
    component=next((c for c in state['analysis']['components'] if c['id']==owner),None)
    if component is None or owner not in state.get('built',{}):raise ValueError('Refine one existing original owner')
    native=ec.inventory(task,state,candidate)[0]
    old_parts={p['id'] for p in state['quality']['specifications'][owner]['parts']}
    for part in correction['specification']['parts']:
        for name in part.get('objects',[]):
            if part['id'] not in old_parts and state.get('native_import',{}).get('owner_map',{}).get(name)!=owner:
                raise ValueError('A new original part cannot claim a different semantic owner')
            if name not in native['native_names']:
                # Historical subspan names are compiled by the native math/
                # table mechanisms; a newly added visual owner must exist.
                if part['id'] not in old_parts:
                    raise ValueError('A new original part needs its actual saved native owner')
    before=digest(ec.resource(task,candidate['pptx']))
    with writer(task):
        # Historical constructor replay must use its original frozen unit
        # snapshot, while the final candidate must satisfy the latest unit.
        archive={'schema':'source-unit-snapshot-1','source_hash':state['source']['sha256'],
                 'units':copy.deepcopy(state['quality']['units']),
                 'specifications':copy.deepcopy(state['quality']['specifications'])}
        from .common import write_json,safe_path
        archive_file=task/'source/contracts/unit-snapshots'/(identity(archive)+'.json')
        if not archive_file.exists():write_json(archive_file,archive)
        ref={'path':archive_file.relative_to(task).as_posix(),'sha256':digest(archive_file)}
        if ref not in state.setdefault('source_unit_archives',[]):state['source_unit_archives'].append(ref)
        affected=revise_spec(state,component,correction,{view['sha256']})
        bind_objects(state,owner,state['built'][owner])
        state['review_queue']+= [x for x in affected if x not in state['review_queue']]
        state['packet']=None;state.pop('acceptance',None)
        if digest(ec.resource(task,candidate['pptx']))!=before:raise ValueError('Source refinement unexpectedly changed native drawing bytes')
        a._event(task,'original_saved_source_refined',{'owner':owner,'affected':affected,
            'source_view':view,'drawing_gain':False,'pptx_unchanged':before})
        a._save(task,state)
    return {'status':'ORIGINAL_SOURCE_REFINED_QUALITY_PENDING','owner':owner,'affected':affected,'pptx_sha256':before}


def initialize(state):
    state['quality'] = {'version': VERSION, 'units': {}, 'specifications': {},
                        'source_queue': [c['id'] for c in state['analysis']['components']],
                        'coverage_debt': {}, 'observations': {}, 'generation': 1}
    for comp in state['analysis']['components']:
        spec = comp.get('source_spec')
        if spec:
            accept_spec(state, comp, spec)


def accept_spec(state, component, spec):
    quality = state['quality']
    owner = component['id']
    units = compile_spec(state, component, spec)
    old = quality['specifications'].get(owner)
    if old and identity(old) != identity(spec):
        raise ValueError('Use a source correction with visible evidence to revise a frozen specification')
    quality['specifications'][owner] = copy.deepcopy(spec)
    if state.get('objectives',{}).get('source_contract_seals'):quality.setdefault('_pending_source_seals',[]).append(owner)
    quality['units'].update(units)
    quality['coverage_debt'][owner] = coverage_debt(state,component,spec,units)
    if owner in quality['source_queue']:
        quality['source_queue'].remove(owner)
    component['status'] = ('observed' if all(f['status']=='observed' for u in units.values() for f in u['features']) else 'inferred')
    component['source_spec'] = copy.deepcopy(spec)


def refinement(state):
    q = state.get('quality', {})
    if q.get('source_queue'):
        return q['source_queue'][0]
    for component in (state.get('analysis') or {}).get('components',[]):
        owner=component['id'];spec=q.get('specifications',{}).get(owner)
        if spec is None:continue
        q.setdefault('coverage_debt',{})[owner]=coverage_debt(state,component,spec)
        if q['coverage_debt'][owner]:return owner
    return None


def unit(state, target):
    return state.get('quality', {}).get('units', {}).get(target.removeprefix('quality:'))


def bind_objects(state, owner, built):
    """Bind all requirements to executable output; no 'parts' prose shortcut."""
    q = state.get('quality', {})
    objects = {obj['id']: obj for obj in built['objects']}
    from .source_math import representation_debt
    q.setdefault('representation_debt',{})[owner]=representation_debt(built['objects'],q.get('units',{}))
    mapping = built.get('method', {}).get('source_bindings', {})
    for value in q.get('units', {}).values():
        if value['owner'] != owner:
            continue
        names = mapping.get(value['part'], value.get('objects', []))
        roots=[o for o in built.get('method',{}).get('objects',[]) if not o.get('parent')]
        aliases={roots[0]['id']:owner} if len(roots)==1 and roots[0]['render_type']=='group' and owner in objects else {}
        from .external_sync import actual_name
        original_names=list(names);names=[actual_name(state, name if name in objects else aliases.get(name,name)) for name in names]
        if names!=original_names:value['source_object_aliases']={a:b for a,b in zip(original_names,names) if a!=b}
        if not names:raise ValueError('Name the required source-part output: '+value['id'])
        missing=sorted(set(names)-objects.keys())
        value['objects']=sorted(set(names))
        if missing:
            value['missing_output_bindings']=missing
            value['status']='required_unmeasured'
            q.get('observations',{}).pop(value['id'],None)
        else:value.pop('missing_output_bindings',None)
        value['built_fingerprint']=identity([objects[name] for name in value['objects'] if name in objects])
    from .source_grids import validate_bound
    validate_bound(state,owner,built)


def queue(state):
    return ['quality:' + u['id'] for u in state.get('quality', {}).get('units', {}).values()]



def _canvas(path, width, height):
    from PIL import Image
    from .resource_facts import image_dimensions,image_region
    operations=[] if image_dimensions(path)==(width,height) else [('resize',(width,height),Image.Resampling.LANCZOS)]
    return image_region(path,operations)


def source_pixel_box(roi):
    """One existing fixed-canvas rounding rule for crops and original masks."""
    x,y,w,h=roi
    return tuple(map(round,(x,y,x+w,y+h)))


def _sampling_debt(task,state,candidate,value,reason,details):
    values={}
    spans=any(f.get('math_spans') for f in value['features'] if f.get('category')=='content' and f.get('status')=='observed')
    if value['profile']=='formula' or spans:
        from .source_math import semantic_measure
        values['math_ast_match']=semantic_measure(task,candidate,value)
    if value['profile']=='text':
        from .source_ocr import semantic_measure,cell_format_measure
        values['native_text_match']=semantic_measure(task,candidate,value,state)
        if value['protocol'].get('table_cell') is not None:
            values['native_cell_format_match']=cell_format_measure(task,candidate,value)
    constraints=assess(values,value['metrics'])
    if value['profile']=='text' and not any(c['id']=='native_text_match' for c in constraints):
        constraints+=assess(values,[{'id':'native_text_match','min':1.,'max':1.}])
    x,y,w,h=value['roi'];sw,sh=state['source_size']
    left=max(0,x-3);top=max(0,y-3)
    roi=[left,top,min(sw,x+w+3)-left,min(sh,y+h+3)-top]
    return {'unit':value['id'],'roi':value['roi'],'issue_roi':roi,'values':values,
        'measurements':{},'constraints':constraints,'target_basis':value.get('target_basis'),
        'status':'below_minimum' if any(c['status']=='below_minimum' for c in constraints) else 'required_unmeasured',
        'measurement_error':'SOURCE_SAMPLING_DOMAIN_INVALID','sampling_error':reason,
        'sampling_details':{'source_pixel_box':source_pixel_box(value['roi']),**details},
        'limits':'Correct the original sampling frame/mask/background after source observation. Fixed targets and native scientific content remain independent; do not redraw or resize a mask to hide this input error.',
        'candidate_hash':candidate['pptx']['sha256'],'preview_hash':candidate['preview']['sha256']}


def _crop_images(task,state,candidate,roi):
    from PIL import Image
    from .resource_facts import image_dimensions,image_region
    box=source_pixel_box(roi)
    width,height=state['source_size']
    def crop(ref):
        path=safe_path(task,ref['path'])
        operations=[] if image_dimensions(path,ref['sha256'])==(width,height) else [('resize',(width,height),Image.Resampling.LANCZOS)]
        return image_region(path,[*operations,('crop',box)],ref['sha256'])
    return crop(state['source']),crop(candidate['preview'])


def _mask(task, descriptor):
    if not descriptor:
        return None
    import numpy as np
    from PIL import Image
    path = safe_path(task, descriptor['path'])
    if digest(path) != descriptor['sha256']:
        raise ValueError('Frozen part mask changed')
    from .resource_facts import image_copy
    with image_copy(path,descriptor['sha256'],mode='L') as image:
        return np.asarray(image) > 0


def evaluate(task, state, candidate, value):
    from .native_core import source_result
    native=source_result(task,state,candidate,value)
    if native is not None:return native
    from .typed_metrics import image_measure, scalar_vector, landmarks
    from .resource_facts import resource_library
    from .source_domains import debt as layer_domain_debt
    missing=[]
    def check_resource(item):
        if isinstance(item,dict):
            if set(('path','sha256'))<=set(item):
                file=safe_path(task,item['path'])
                if not file.is_file() or digest(file)!=item['sha256']:missing.append(item)
            for child in item.values():check_resource(child)
        elif isinstance(item,list):
            for child in item:check_resource(child)
    check_resource(value)
    if missing:
        return {'unit':value['id'],'roi':value['roi'],'values':{},'measurements':{},
            'constraints':assess({},value['metrics']),'status':'required_unmeasured',
            'measurement_error':{'kind':'UNAVAILABLE_FROZEN_SOURCE_RESOURCES','resources':missing},
            'limits':'Preserve the original requirement and thresholds; restore exact evidence or correct its source domain through the original-only source loop. No invented measurement.',
            'candidate_hash':candidate['pptx']['sha256'],'preview_hash':candidate['preview']['sha256']}
    layer_debt=layer_domain_debt(task,state,value)
    if layer_debt:
        return {'unit':value['id'],'roi':value['roi'],'values':{},'measurements':{},
            'constraints':assess({},value['metrics']),'status':'required_unmeasured',
            'measurement_error':layer_debt,
            'limits':'Define the visible original layer and upper occlusions before measuring this part; a full ROI cannot stand in for ownership.',
            'candidate_hash':candidate['pptx']['sha256'],'preview_hash':candidate['preview']['sha256']}
    a, b = _crop_images(task, state, candidate, value['roi'])
    frozen = {k:v for k,v in value.items() if k not in ('status','built_fingerprint')}
    dependencies = {'source': state['source']['sha256'], 'spec': identity(frozen),
                    'frame_plan':state.get('frame_plan'),
                    'pixels': hashlib.sha256(b.tobytes()).hexdigest(),
                    'implementation': identity({'quality':digest(Path(__file__)),
                         'typed':digest(Path(__file__).with_name('typed_metrics.py'))})}
    if value['profile']=='relation':
        dependencies['saved_relation_candidate']=candidate['pptx']['sha256']
        dependencies['frame_implementation']=digest(Path(__file__).with_name('frame_plan.py'))
        dependencies['relative_layout_implementation']=digest(Path(__file__).with_name('relative_layout.py'))
        dependencies['ink_implementation']=digest(Path(__file__).with_name('layout_ink.py'))
        dependencies['actual_relation_render']=candidate.get('render')
        dependencies['actual_relation_captures']=identity(state.get('semantic_composition',{}).get('captures',{}))
    math_spans=next((f['math_spans'] for f in value['features'] if f.get('category')=='content' and f.get('status')=='observed' and f.get('math_spans')),None)
    if math_spans or (value['profile']=='formula' and any(f.get('ast') for f in value['features'] if f['category']=='content')):
        from .source_math import actual_ast
        actual_math=[actual_ast(task,candidate,{**value,'protocol':{**value['protocol'],'math_span_index':i}}) for i in range(len(math_spans))] if math_spans else actual_ast(task,candidate,value)
        dependencies['actual_math_ast']=identity(actual_math)
        dependencies['saved_math_owner']=candidate['pptx']['sha256'] if math_spans else None
        dependencies['math_implementation']=identity({'source_math':digest(Path(__file__).with_name('source_math.py')),
            'serialization':digest(Path(__file__).with_name('mathml.py')),
            'saved_parser':digest(Path(__file__).with_name('inspect.py'))})
    native_domain=None
    if value['profile']=='text':
        from .source_ocr import actual_text
        dependencies['actual_native_text']=identity(actual_text(task,candidate,value))
        dependencies['native_text_implementation']=digest(Path(__file__).with_name('source_ocr.py'))
        dependencies['independent_source_reading']=identity(state.get('source_readings',{}))
        dependencies['source_reading_implementation']=digest(Path(__file__).with_name('source_reading.py'))
        if value['protocol'].get('table_cell') is not None:
            from .source_ocr import actual_cell
            dependencies['actual_native_cell']=identity(actual_cell(task,candidate,value))
    if value['protocol'].get('candidate_native_text_domain'):
        import numpy as np
        from .component_report import _native_ink
        bounds=safe_path(task,candidate['render']['path']).parent/'text-bounds.json'
        if (value['profile'] not in ('text','formula') or len(value['objects'])!=1 or not bounds.is_file()
                or read_json(bounds).get('pptx_hash')!=candidate['pptx']['sha256']):
            raise ValueError('Bind actual native text ownership to its saved PowerPoint render')
        boxes=_native_ink(safe_path(task,candidate['pptx']['path']),bounds,state['source_size'])
        box=boxes.get(value['objects'][0])
        if not box:raise ValueError('Actual saved native text bounds are unavailable')
        xx,yy=np.meshgrid(np.arange(b.width)+round(value['roi'][0])+.5,
                            np.arange(b.height)+round(value['roi'][1])+.5)
        # Advance bounds locate this saved text owner; actual pixel masks still
        # establish glyph ink and weight. No translation/registration occurs.
        native_domain=(xx>=box[0]-1)&(xx<=box[0]+box[2]+1)&(yy>=box[1]-1)&(yy<=box[1]+box[3]+1)
        dependencies['native_owner_bounds']=digest(bounds)
    binding_debt=[]
    if value.get('missing_output_bindings'):
        names=_saved_native_names(str(safe_path(task,candidate['pptx']['path'])),candidate['pptx']['sha256'])
        binding_debt=[name for name in value['objects'] if names.get(name,0)!=1]
        dependencies['pending_output_binding']=identity({name:names.get(name,0) for name in value['objects']})
    library = resource_library(state['project'])
    key = 'part-quality:' + identity(dependencies)
    result = library.cache_get(key, dependencies)
    if result is not None:
        state['telemetry']['cache_hits'] += 1
        result=copy.deepcopy(result)
        result['cache_origin_candidate']=result.get('candidate_hash')
        result.update(candidate_hash=candidate['pptx']['sha256'],preview_hash=candidate['preview']['sha256'])
        return result
    values, measured = {}, {}
    if value['profile'] != 'relation':
        reference_mask=_mask(task,value.get('reference_mask'))
        evaluation_mask=_mask(task,value.get('evaluation_mask'))
        expected=(a.height,a.width)
        if min(expected)<=0:
            return _sampling_debt(task,state,candidate,value,'EMPTY_ROUNDED_SOURCE_WINDOW',{'crop_shape':expected})
        bg=value['protocol'].get('background_rgb')
        if (not isinstance(bg,(list,tuple)) or len(bg)!=3 or
                any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=255 for v in bg)):
            return _sampling_debt(task,state,candidate,value,'INVALID_ORIGINAL_BACKGROUND',{'background_rgb':bg})
        for name,mask in (('reference_mask',reference_mask),('evaluation_mask',evaluation_mask)):
            if mask is not None and (mask.shape!=expected or not mask.any()):
                return _sampling_debt(task,state,candidate,value,'INVALID_FROZEN_SOURCE_MASK',
                    {'field':name,'crop_shape':expected,'mask_shape':mask.shape,'owned_pixels':int(mask.sum())})
        if reference_mask is not None and not reference_mask.any():
            return {'unit':value['id'],'roi':value['roi'],'values':{},
                    'measurements':{},'constraints':assess({},value['metrics']),
                    'status':'required_unmeasured','measurement_error':'EMPTY_SOURCE_FOREGROUND',
                    'limits':'Correct the source-owned mask; do not repair a drawing against an empty reference.',
                    'candidate_hash':candidate['pptx']['sha256'],'preview_hash':candidate['preview']['sha256']}
        measured = image_measure(a,b,value['protocol'],reference_mask,
                                 evaluation_mask,native_domain)
        values = scalar_vector(measured)
        values.update(color_histogram_tv=measured['texture_color_histogram_tv'],
                      foreground_color_p95=measured['color_delta_e_reference_foreground']['p95'],
                      foreground_mass_ratio=measured['foreground_mass_ratio'],
                      foreground_area_ratio=measured['foreground_area_ratio'],
                      component_count_error=measured['topology']['component_count_error'],
                      hole_count_error=measured['topology']['hole_count_error'],
                      foreground_f1=measured['foreground_match']['f1'],
                      foreground_reference_pixels=measured['reference_foreground_pixels'],
                      foreground_candidate_pixels=measured['candidate_foreground_pixels'],
                      ssim=measured['ssim'], psnr_db=measured['psnr_db'],
                      color_p95=measured['color_delta_e_2000']['p95'],
                      internal_hd95=measured['internal_edges']['hd95_px'])
    else:
        # Relations measured from saved geometry or actual Office ink bounds.
        # Without a declared executable measurement, remain host-observed.
        relation = value['relation']
        if relation.get('measurement'):
            values = relation_values(task, state, candidate, relation['measurement'])
    if value['profile']=='formula' or math_spans:
        from .source_math import semantic_measure
        values['math_ast_match']=semantic_measure(task,candidate,value)
    if value['profile']=='text':
        from .source_ocr import semantic_measure
        values['native_text_match']=semantic_measure(task,candidate,value,state)
        if value['protocol'].get('table_cell') is not None:
            from .source_ocr import cell_format_measure
            values['native_cell_format_match']=cell_format_measure(task,candidate,value)
    constraints = assess(values, value['metrics'])
    authorized_layout=None
    if value['profile']=='relation' and value.get('relation',{}).get('measurement',{}).get('kind')=='relative_layout':
        from .relative_layout import evaluate_contract
        authorized_layout=evaluate_contract(task,state,candidate,value['relation']['measurement']['contract'])
        if authorized_layout.get('target_authority'):
            # Keep original metrics/values immutable. Compile only the exact
            # authorized layout predicates into separate active constraints.
            active=[]
            for rule in value['metrics']:
                key=rule['id']
                if key in ('source_relative_error_px','interval_violation_px'):
                    compiled={'id':'interval_violation_px','min':0.,'max':0.}
                elif key in ('gap_px','anchor_offset_px'):
                    compiled={'id':key,'min':authorized_layout['interval'][0],'max':authorized_layout['interval'][1]}
                else:
                    active+=assess(values,[rule]);continue
                measured_rule=assess(values,[compiled])[0]
                measured_rule.update(original_source_rule=rule,original_source_value=values.get(key),
                                     target_authority=authorized_layout['target_authority'],target_frame=authorized_layout['target_frame'])
                active.append(measured_rule)
            constraints=active
    if value['profile']=='text' and not any(c['id']=='native_text_match' for c in constraints):
        constraints+=assess(values,[{'id':'native_text_match','min':1.,'max':1.}])
    result = {'unit': value['id'], 'roi': value['roi'], 'values': values,
              'measurements': measured, 'constraints': constraints,
              'target_basis': value.get('target_basis'),
              'status': 'below_minimum' if any(c['status'] == 'below_minimum' for c in constraints)
                        else 'required_unmeasured' if any(c['status'] == 'required_unmeasured' for c in constraints)
                        else 'numeric_minimum_met',
              'limits': 'Independent source-property observation and output trace are still required',
              'candidate_hash': candidate['pptx']['sha256'],
              'preview_hash': candidate['preview']['sha256']}
    if authorized_layout and authorized_layout.get('target_authority'):
        result['authorized_layout_target']=authorized_layout
        result['target_basis']={'kind':'authorized_user_frame','authority':authorized_layout['target_authority'],
                                'original_source_target_basis':value.get('target_basis')}
    if binding_debt:
        result.update(status='required_unmeasured',missing_output_bindings=binding_debt,
            measurement_error='SOURCE_PART_OUTPUT_NOT_PRESENT',
            limits='A declared source part lacks unique saved native output; neighbouring pixels cannot satisfy it.')
    library.cache_put(key, result, dependencies)
    return result


def relation_values(task, state, candidate, measurement):
    scene = read_json(safe_path(task, candidate['scene']['path']))
    by_id = {o['id']: o for o in scene['objects']}
    kind = measurement.get('kind')
    if kind == 'relative_layout':
        from .relative_layout import evaluate_contract
        result=evaluate_contract(task,state,candidate,measurement['contract'])
        return result.get('values',{})
    if kind=='directed_native_edges':
        import math
        expected=measurement['edges'];owned=measurement['connector_ids']
        nodes=measurement['nodes'];tolerance=measurement.get('endpoint_tolerance_px',2.)
        missing=0;wrong=0;arrows=0
        # Measure the actually saved native arrow declaration; the scene
        # author uses DrawingML types, not an invented end/both enum.
        from .resource_facts import xml_part
        ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
            'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
        saved_arrows={}
        slide=xml_part(safe_path(task,candidate['pptx']['path']),'ppt/slides/slide1.xml',candidate['pptx']['sha256'])
        for shape in slide.findall('.//p:cxnSp',ns):
            name=shape.find('p:nvCxnSpPr/p:cNvPr',ns)
            tail=shape.find('p:spPr/a:ln/a:tailEnd',ns)
            if name is not None:saved_arrows[name.get('name')]=tail.get('type') if tail is not None else 'none'
        def nearest(point):
            choices=[]
            for name in nodes:
                obj=by_id.get(name)
                if obj is None:continue
                x,y,w,h=obj['bbox'];cx,cy=x+w/2,y+h/2
                distance=math.hypot(point[0]-cx,point[1]-cy)
                choices.append((max(0.,distance-max(w,h)/2),distance,name))
            choices.sort()
            return choices[0][2] if choices and choices[0][0]<=tolerance else None
        for edge in expected:
            obj=by_id.get(edge['id'])
            if not obj or obj['render_type']!='connector':missing+=1;continue
            points=obj['content'].get('points',[])
            if len(points)!=2 or obj['content'].get('coordinate_space')!='canvas':wrong+=1;continue
            if [nearest(points[0]),nearest(points[-1])]!=[edge['from'],edge['to']]:wrong+=1
            if edge.get('arrow',True) and saved_arrows.get(edge['id']) not in ('triangle','arrow','stealth'):arrows+=1
        wanted={e['id'] for e in expected}
        extra=sum(name in by_id and by_id[name]['render_type']=='connector' for name in owned if name not in wanted)
        return {'missing_edge_count':missing,'wrong_endpoint_count':wrong,
                'missing_arrow_count':arrows,'extra_edge_count':extra}
    if kind == 'native_gap':
        first, second = measurement['objects']
        if first not in by_id or second not in by_id:
            return {}
        a, b = by_id[first]['bbox'], by_id[second]['bbox']
        if measurement.get('axis') == 'y':
            gap = b[1] - a[1] - a[3]
        else:
            gap = b[0] - a[0] - a[2]
        return {'gap_px': gap}
    if kind == 'paint_order':
        first,second=measurement['objects'];order={o['id']:i for i,o in enumerate(scene['objects'])}
        return {'correct_order':int(order[first]<order[second])} if first in order and second in order else {}
    if kind=='visible_ink_native_gap':
        # Fixed source-owned windows disambiguate a glyph from its neighbour.
        # PDF text extents include advance/overhang; they are not visible ink.
        import numpy as np
        from PIL import Image
        from .typed_metrics import ink_box
        from .resource_facts import image_region
        preview_path=safe_path(task,candidate['preview']['path'])
        boxes={}
        for name in measurement['objects']:
            if name not in by_id:return {}
            if by_id[name]['render_type'] not in ('text','equation'):
                boxes[name]=by_id[name]['bbox'];continue
            roi=measurement.get('visible_rois',{}).get(name)
            if not roi:return {}
            x,y,w,h=map(round,roi)
            with image_region(preview_path,[('resize',tuple(state['source_size']),Image.Resampling.LANCZOS),
                ('crop',(x,y,x+w,y+h))],candidate['preview']['sha256']) as crop:
                pixels=np.asarray(crop,float)
            color=measurement.get('colors_rgb',{}).get(name,[0,0,0])
            mask=np.linalg.norm(pixels-np.asarray(color),axis=2)<=measurement.get('ink_distance_rgb_255',190)
            box=ink_box(mask)
            if not box:return {}
            # A clipped glyph cannot masquerade as a good spacing result.
            if box[0]<=0 or box[2]>=w:return {}
            boxes[name]=[x+box[0],y+box[1],box[2]-box[0],box[3]-box[1]]
        a,b=[boxes[n] for n in measurement['objects']]
        return {'gap_px':b[0]-a[0]-a[2] if measurement.get('axis')!='y' else b[1]-a[1]-a[3]}
    if kind in ('office_ink_gap','ink_native_gap'):
        receipt = candidate.get('render')
        if not receipt:
            return {}
        bounds = safe_path(task, receipt['path']).parent / 'text-bounds.json'
        if not bounds.exists():
            return {}
        from .component_report import _native_ink
        ink = _native_ink(safe_path(task, candidate['pptx']['path']), bounds, state['source_size'])
        first, second = measurement['objects']
        if kind=='ink_native_gap':
            for name in (first,second):
                if name not in ink and name in by_id:ink[name]=by_id[name]['bbox']
        if first not in ink or second not in ink:
            return {}
        a, b = ink[first], ink[second]
        return {'gap_px': b[0]-a[0]-a[2] if measurement.get('axis') != 'y'
                else b[1]-a[1]-a[3]}
    return {}


def assess(values, metrics):
    result = []
    for rule in metrics:
        measured = values.get(rule['id'])
        if measured is not None and not math.isfinite(measured):measured=None
        below = measured is not None and (
            rule.get('min') is not None and measured < rule['min'] or
            rule.get('max') is not None and measured > rule['max'])
        scale = max(abs(rule.get('min') or rule.get('max') or 1), 1e-8)
        deficit = (max((rule.get('min') or measured)-measured, 0,
                       measured-(rule.get('max') if rule.get('max') is not None else measured))/scale
                   if measured is not None else None)
        stretch = rule.get('stretch')
        achieved_stretch = (measured is not None and stretch is not None and
                            (measured >= stretch if rule.get('min') is not None else measured <= stretch))
        result.append({**rule, 'value': measured, 'deficit': deficit,
                       'status': 'required_unmeasured' if measured is None else
                                 'below_minimum' if below else
                                 'stretch_met' if achieved_stretch else 'minimum_met'})
    return result


def observation_contract(value):
    generic={'text','caption','table_label','title','label','paragraph','textbox','text_box','equation','formula','math'}
    records=[]
    for f in value['features']:
        status=f['status']
        if (value['profile'] in ('text','formula') and f['category']=='content'
                and not f.get('literal') and not f.get('ast') and str(f['expected']).strip().lower() in generic):
            status='unresolved'
        records.append({'requirement':value['id']+'/'+f['id'],'property':f['category'],
            'expected':f['expected'],'source_status':status})
    return records


def record_observation(state, value, observations, evidence, diagnostic):
    expected = {x['requirement']: x for x in observation_contract(value)}
    actual = {o.get('requirement'): o for o in observations}
    missing = set(expected) - set(actual)
    if missing:
        raise ValueError('Observe all named source properties: ' + ','.join(sorted(missing)))
    for name, requirement in expected.items():
        item = actual[name]
        if item.get('expected') != requirement['expected']:
            raise ValueError('Do not rewrite source expectations to match a drawing')
        if requirement['source_status'] == 'unresolved' and item['outcome'] == 'matched':
            raise ValueError('Resolve the source uncertainty with evidence before satisfaction')
    matched = all(actual[k]['outcome'] == 'matched' for k in expected)
    minimum = diagnostic['status'] == 'numeric_minimum_met'
    record = {'candidate': evidence['candidate'], 'views': evidence['views'],
              'observations': [actual[k] for k in expected], 'diagnostic': diagnostic,
              'built_fingerprint': value.get('built_fingerprint'),
              'status': 'minimum_met' if matched and minimum else 'below_minimum' if matched else 'semantic_issue'}
    state['quality']['observations'][value['id']] = record
    value['status'] = record['status']
    return record



def _usable_basis(value):
    return identity({k:v for k,v in value.items() if k not in
                     ('status','diagnostic','observations','last_review','actual')})


def has_usable_limit(state,value):
    record=state.get('quality',{}).get('usable_limits',{}).get(value['id'])
    if not (record and state.get('selected') and
        record['candidate']==state['selected']['pptx']['sha256'] and
        record['source_basis']==_usable_basis(value)):return False
    # A later located major defect revokes a cosmetic stop, even on the same
    # saved file. Preserve explicit old residuals without hiding new evidence.
    for issue in state.get('issues',[]):
        if (issue['status']=='open' and issue.get('quality_unit')==value['id'] and
                issue['severity'] in ('critical','major')):
            stamp=identity({k:issue.get(k) for k in ('id','property','expected','actual','evidence','metric')})
            if record.get('known_findings',{}).get(issue['id'])!=stamp:return False
    return True


def _owned_native_basis(nodes,value):
    names=set(value.get('objects',[]));again=True
    while again:
        added={o['id'] for o in nodes.values() if o.get('parent') in names}-names
        again=bool(added);names.update(added)
    descendants=set(names)
    for oid in list(descendants):
        current=nodes.get(oid)
        while current and current.get('parent'):
            oid=current['parent'];names.add(oid);current=nodes.get(oid)
    if not descendants or not names<=nodes.keys():return None
    return identity([nodes[n] for n in nodes if n in names])


def native_typography_limit(value,diagnostic,item):
    """Explicit actual usable text; exact content/format never becomes cosmetic.

    Fixed pixel targets and residuals are retained. This is unavailable for
    missing measures, unknown original symbols, relationships or unreadable
    content; the host must independently observe every original text property.
    """
    if (not item or item.get('kind')!='native_typography' or value['profile'] not in ('text','formula')
            or not item.get('limitation') or not item.get('improvement')):return False
    required=[r for r in diagnostic.get('constraints',[]) if r['id'] in
        ('native_text_match','math_ast_match','native_cell_format_match')]
    if not required or any(r['status'] not in ('minimum_met','stretch_met') for r in required):return False
    if value['profile']=='formula' and not any(r['id']=='math_ast_match' for r in required):return False
    if value['profile']=='text' and not any(r['id']=='native_text_match' for r in required):return False
    failed=[r for r in diagnostic.get('constraints',[]) if r['status'] in ('below_minimum','required_unmeasured')]
    if not failed or any(r['status']!='below_minimum' or r['id'] not in
        ('internal_edge_f1','foreground_f1','foreground_mass_ratio') for r in failed):return False
    observations=item.get('critical_observations',[])
    for rule in observation_contract(value):
        if rule['source_status']!='observed' or not any(o.get('property')==rule['property'] and
            o.get('expected')==rule['expected'] and o.get('outcome')=='matched' and o.get('actual') for o in observations):return False
    return True


def scoped_cosmetic_acceptance(task,state,before,after,scope,request,observations):
    """Keep a visibly improved result without claiming its colour debt passed.

    Only explicit independently observed appearance limits qualify. Scientific
    content, meaningful geometry, missing measures and frozen paint stay hard.
    Unowned context-ROI scores cannot veto an unchanged native context owner.
    """
    if not request:return scope
    if (not isinstance(request,dict) or not request.get('reason') or
            request.get('source')!=state['source'] or request.get('actual_preview')!=after['preview'] or
            not request.get('substantive_gain')):
        raise ValueError('Bind explicit usable-result evidence to original/actual saved render')
    context=request.get('context_observations',[])
    required={'content','layout','clarity','protected_content','reusable_components'}
    if {o.get('property') for o in context}!=required or any(
            o.get('outcome')!='matched' or not o.get('actual') or not o.get('expected') for o in context):
        raise ValueError('Observe actual source/current context critical properties independently')
    old_nodes={o['id']:o for o in read_json(safe_path(task,before['scene']['path']))['objects']}
    new_nodes={o['id']:o for o in read_json(safe_path(task,after['scene']['path']))['objects']}
    limited={v['unit']:v for v in request.get('parts',[])}
    if len(limited)!=len(request.get('parts',[])):raise ValueError('No duplicate appearance limits')
    final=copy.deepcopy(scope);decisions=[]
    if any(not p['eligible'] for p in final.get('retained_material_properties',[])):
        raise ValueError('Usable-result limits cannot release a frozen material property')
    for row in final['changed_units']:
        u=state['quality']['units'][row['unit']];item=limited.get(u['id'])
        if row['eligible'] and not item:continue
        if item:
            failed=[v for v in row['after']['constraints'] if v['status'] in ('below_minimum','required_unmeasured')]
            native_limit=native_typography_limit(u,row['after'],item)
            if not native_limit and (not failed or any(v['id']!='color_histogram_tv' or v['status']!='below_minimum' for v in failed)
                    or u['profile'] in ('text','formula') or not item.get('limitation') or not item.get('improvement')):
                raise ValueError('Only measured minor colour or explicitly observed exact-content native glyph residuals may be limited')
            obs=item.get('critical_observations',[])
            rules=[v for v in observation_contract(u) if v['property']!='style']
            if any(not any(o.get('property')==v['property'] and o.get('expected')==v['expected']
                    and o.get('outcome')=='matched' and o.get('actual') for o in obs) for v in rules):
                raise ValueError('Every important part retains exact independently observed content/geometry')
            row['eligible']=True;row['usable_disposition']='observed_minor_native_glyph_residual' if native_limit else 'observed_minor_colour_residual'
            decisions.append({'unit':u['id'],'kind':row['usable_disposition'],
                'source_basis':_usable_basis(u),'limitation':item['limitation'],'improvement':item['improvement'],
                'critical_observations':obs,'raw_after_status':row['after']['status']})
        elif (row['scope_role']=='actual_changed_source_domain' and not u.get('reference_mask')
                and not u.get('relation') and
                _owned_native_basis(old_nodes,u) is not None and
                _owned_native_basis(old_nodes,u)==_owned_native_basis(new_nodes,u)):
            owned=set(u.get('objects',[]));again=True
            while again:
                added={o['id'] for o in old_nodes.values() if o.get('parent') in owned}-owned
                again=bool(added);owned.update(added)
            if any(old_nodes[o]['render_type'] not in ('group','shape','path','bezier','connector') for o in owned):
                raise ValueError('Do not infer unchanged font/media rendering from a scene alone')
            row['eligible']=True;row['usable_disposition']='unchanged_native_context_unowned_roi_diagnostic'
            decisions.append({'unit':u['id'],'kind':row['usable_disposition'],
                'source_basis':_usable_basis(u),'limitation':'Original unmasked context ROI includes changed pixels owned by the explicitly authorised foreground component. Its fixed ROI scores remain diagnostics; unchanged native subtree/ancestor fields and actual context observation preserve this context, without inventing an owner-specific metric.',
                'raw_after_status':row['after']['status'],'critical_observations':context})
    if not set(limited)<=set(v['unit'] for v in decisions)|{v['unit'] for v in final['changed_units'] if v['eligible']}:
        raise ValueError('Appearance limits must correspond to an actually changed independently blocked unit')
    final['raw_eligible']=scope['eligible'];final['raw_blocking_units']=scope['blocking_units']
    final['blocking_units']=[v['unit'] for v in final['changed_units'] if not v['eligible']]
    final['eligible']=not final['blocking_units'];final['usable_limits']=decisions
    final['selection']='Observed substantive gain; each part retains content/geometry. Explicit minor colour/native-glyph limits and unchanged unowned context diagnostics remain reported. Fixed metrics/targets are unchanged; no minimum_met claim.'
    return final


def record_scoped_observations(task,state,candidate,packet,scope,entries):
    """One viewed complete icon can independently cover its actual parts."""
    covered={v['unit'] for v in scope['changed_units']};seen=set()
    views=packet['views'];x,y,w,h=views[0]['roi']
    for entry in entries or []:
        uid=entry.get('unit');u=state['quality']['units'].get(uid)
        if uid in seen or uid not in covered or not u:raise ValueError('Observe only distinct affected source units')
        ux,uy,uw,uh=u['roi']
        if ux<x or uy<y or ux+uw>x+w+.001 or uy+uh>y+h+.001:
            raise ValueError('Natural part observation must fit its actual paired icon view')
        current=next(v for v in views if v['role']=='current')
        scale=current['display_size'][0]/w
        if min(uw,uh)*scale<24:raise ValueError('Important tiny parts require an enlarged independent view')
        obs=entry.get('observations',[])
        if any(not any(o.get('property')==r['property'] and o.get('expected')==r['expected']
                and o.get('actual') and o.get('outcome') in ('matched','issue','uncertain') for o in obs)
               for r in observation_contract(u)):
            raise ValueError('Observe every exact source property of each natural part')
        record_observation(state,u,obs,{'candidate':candidate['pptx']['sha256'],
            'views':sorted(v['sha256'] for v in views),'scoped_actual_part':True},evaluate(task,state,candidate,u))
        seen.add(uid)


def record_usable_limits(task,state,candidate,scope):
    nodes={o['id']:o for o in read_json(safe_path(task,candidate['scene']['path']))['objects']}
    for decision in scope.get('usable_limits',[]):
        u=state['quality']['units'][decision['unit']]
        _,actual=_crop_images(task,state,candidate,u['roi'])
        record={**decision,'candidate':candidate['pptx']['sha256'],'source_basis':_usable_basis(u),
            'native_basis':_owned_native_basis(nodes,u),'actual_pixels':hashlib.sha256(actual.tobytes()).hexdigest(),
            'known_findings':{i['id']:identity({k:i.get(k) for k in ('id','property','expected','actual','evidence','metric')})
                for i in state['issues'] if i['status']=='open' and i.get('quality_unit')==u['id']}}
        state['quality'].setdefault('usable_limits',{})[u['id']]=record
        for issue in state['issues']:
            if (issue['status']=='open' and issue.get('quality_unit')==u['id'] and
                    issue.get('metric')=='color_histogram_tv' and decision['kind']=='observed_minor_colour_residual'):
                issue['status']='deferred_cosmetic';issue['disposition']=record


def inherit_usable_limits(task,state,before,after):
    nodes={o['id']:o for o in read_json(safe_path(task,after['scene']['path']))['objects']}
    inherited=[]
    for uid,record in state.get('quality',{}).get('usable_limits',{}).items():
        u=state['quality']['units'].get(uid)
        if (not u or record['candidate']!=before['pptx']['sha256'] or record['source_basis']!=_usable_basis(u)
                or record['native_basis']!=_owned_native_basis(nodes,u)):continue
        _,actual=_crop_images(task,state,after,u['roi'])
        if hashlib.sha256(actual.tobytes()).hexdigest()!=record['actual_pixels']:continue
        record['candidate']=after['pptx']['sha256'];inherited.append(uid)
    return inherited


def pending(state):
    q = state.get('quality', {})
    for component in (state.get('analysis') or {}).get('components',[]):
        spec=q.get('specifications',{}).get(component['id'])
        if spec is not None:
            q.setdefault('coverage_debt',{})[component['id']]=coverage_debt(state,component,spec)
    debt = [{'owner': owner, 'kind': 'unassigned_source_feature', 'features': values}
            for owner, values in q.get('coverage_debt', {}).items() if values]
    incomplete = [u for u in q.get('units', {}).values() if u['status'] != 'minimum_met' and not has_usable_limit(state,u)]
    return {'source_owners': q.get('source_queue', []), 'coverage_debt': debt,
            'units': [u['id'] for u in incomplete], 'complete': not (
                q.get('source_queue') or debt or incomplete)}


def defects(value, diagnostic):
    """Metric debt is actionable and cannot be diluted by a parent's score."""
    sampling_error=diagnostic.get('measurement_error')=='SOURCE_SAMPLING_DOMAIN_INVALID'
    if sampling_error:
        yield {'owner':value['owner'],'quality_unit':value['id'],'roi':diagnostic['issue_roi'],
            'property':value['id']+'/source_measurement_domain',
            'expected':'Valid original pixel window, owned masks and finite source background; preserve the actual drawing and every fixed target.',
            'actual':diagnostic['sampling_error']+': '+str(diagnostic['sampling_details']),
            'severity':'major','cause_hint':'source_specification: observe and correct the original measurement frame/mask before any drawing action',
            'metric_deficit':None,'sampling_error':diagnostic['sampling_error']}
    for constraint in diagnostic['constraints']:
        if sampling_error and constraint['id'] not in ('native_text_match','math_ast_match','native_cell_format_match'):
            continue
        if constraint['status'] in ('below_minimum', 'required_unmeasured'):
            yield {'owner': value['owner'], 'quality_unit': value['id'], 'roi': value['roi'],
                   'property': value['id'] + '/' + constraint['id'],
                   'expected': 'Fixed target ' + str({k: constraint.get(k) for k in ('min','max')}),
                   'actual': 'Measured ' + str(constraint['value']),
                   'severity': value['priority'],
                   'cause_hint': 'Follow source property -> plan -> bound objects -> actual render',
                   'metric_deficit': constraint['deficit'],
                   'metric': constraint['id']}


def invalidate(state, changed_objects, visual_roi=None):
    """Keep satisfied unrelated units; only follow declared geometry/relations."""
    changed_objects = set(changed_objects)
    from .impact_graph import resolve
    affected_units = set(resolve(state, {n: [] for n in changed_objects})['units'])
    affected = []
    for u in state.get('quality', {}).get('units', {}).values():
        overlaps=False
        if visual_roi:
            regions=[visual_roi] if isinstance(visual_roi[0],(int,float)) else visual_roi
            ux,uy,uw,uh=u['roi']
            for region in regions:
                x,y,w,h=region
                overlaps=overlaps or (ux<x+w and uy<y+h and ux+uw>x and uy+uh>y)
        if u['id'] in affected_units or overlaps:
            u['status'] = 'required_unmeasured'
            state['quality']['observations'].pop(u['id'], None)
            affected.append('quality:' + u['id'])
    return affected


def trace(state, issue):
    value = state.get('quality', {}).get('units', {}).get(issue.get('quality_unit'))
    if not value:
        return {}
    owner = value['owner']
    method = state['methods'].get(owner, {})
    objects = {o['id']: o for o in state['built'].get(owner, {}).get('objects', [])}
    absent = [name for name in value['objects'] if name not in objects]
    return {'source_unit': value['id'], 'source_features': value['features'],
            'bound_objects': value['objects'], 'absent_objects': absent,
            'metric': issue.get('metric'), 'source_spec_hash': identity(
                state['quality']['specifications'][owner]),
            'ordered_artifacts': ['original source ROI', 'frozen source specification',
                                  'recipe and source_bindings', 'instance native geometry',
                                  'saved PPTX objects', 'actual rendered ROI'],
            'next_evidence': 'Find the earliest artifact that violates this exact property; '
                             'a hypothesis is not a confirmed root cause',
            'repair_routes': {'source_missing': 'evidence-bound source correction',
                              'recipe_missing': 'fit/add the missing natural part',
                              'instance_wrong': 'change only bound geometry/style fields',
                              'render_missing': 'repair serialization/font/crop/z-order'},
            'preserve': 'all unrelated requirements and satisfied native properties'}


def changed_closure(state, grants):
    from .impact_graph import resolve
    return set(resolve(state, grants)['observe'])


def protect_scope(state, issue, grants):
    """The repair cannot grant itself permission over other satisfied units."""
    changed=changed_closure(state,grants)
    for value in state.get('quality',{}).get('units',{}).values():
        if value['status']!='minimum_met' or value['id']==issue.get('quality_unit'):
            continue
        if changed.intersection(value.get('objects',[])):
            raise ValueError('Repair would alter a satisfied source unit: '+value['id']+
                             '; first locate a genuine dependent defect or obtain a user change grant')
    return changed


def validate_cause(task,state,issue,cause):
    if not enabled(state):return
    if cause.get('stage') not in CAUSE_STAGES:
        raise ValueError('Choose a concrete source/recipe/instance/layer/font/render cause')
    evidence=cause.get('evidence')
    if not isinstance(evidence,dict) or not evidence.get('expected') or not evidence.get('observed'):
        raise ValueError('Cause needs structured expected/observed artifact evidence')
    artifact=evidence.get('artifact',{})
    path=safe_path(task,artifact['path'])
    if digest(path)!=artifact.get('sha256'):
        raise ValueError('Root-cause artifact is stale')
    value=state.get('quality',{}).get('units',{}).get(issue.get('quality_unit'))
    if value and evidence.get('unit')!=value['id']:
        raise ValueError('Root cause must identify the affected source part')
    if evidence.get('object_id') and value and evidence['object_id'] not in value['objects']:
        raise ValueError('Root cause expanded beyond its bound output objects')
    from .defect_triage import diagnosis
    current=diagnosis(task,state,issue)
    participants=set(evidence.get('participants', []))
    if cause['stage']=='z_order' and len(participants)!=2:
        raise ValueError('Layer diagnosis must identify the exact two saved participants')
    for exclusion in current['excluded']:
        if cause['stage']=='z_order' and exclusion['operator']=='paint_order':
            pair=set(exclusion.get('objects', []))
            if not pair or pair==participants:
                raise ValueError('The saved evidence excludes this paint-order repair: '+exclusion['reason'])
        if issue.get('sampling_error') and cause['stage']!='source_specification':
            raise ValueError('Resolve the invalid original measurement domain before repainting')
    cause['diagnosis_key']=current.get('key')
    cause['confidence']='supported' if cause['stage'] in current['supported'] else 'hypothesis'


def effect(before,after,unit):
    """Compare frozen one/two-sided requirements at source sampling precision.

    A ratio is not always better when larger. Crossing a satisfied floor is
    never noise; a below-floor gain never closes the requirement. Independent
    tiny sampling changes are recorded, not hidden in a composite reward.
    """
    improved=[];regressed=[];missing=[];noise=[]
    for rule in unit['metrics']:
        name=rule['id'];x=before['values'].get(name);y=after['values'].get(name)
        if x is None or y is None or not math.isfinite(x) or not math.isfinite(y):missing.append(name);continue
        lo,hi=rule.get('min'),rule.get('max')
        def loss(v):
            if lo is not None and hi is not None:
                target=rule.get('stretch', (lo+hi)/2)
                return max(lo-v,v-hi,0),abs(v-target)
            return (0,-v) if lo is not None else (0,v)
        a,b=loss(x),loss(y)
        # Each source part contains a finite number of support/edge samples.
        # One sample is a declared resolution unit, not an adjustable reward.
        tolerance=0.0
        if name in ('internal_edge_f1','boundary_f1','foreground_f1'):
            field={'internal_edge_f1':'internal_edges','boundary_f1':'boundary','foreground_f1':'foreground_match'}[name]
            count=before['measurements'].get(field,{}).get('reference_points',0)
            tolerance=1/max(count,1) if count else 0
        crossed=((lo is not None and x>=lo and y<lo) or (hi is not None and x<=hi and y>hi))
        delta=b[1]-a[1] if b[0]==a[0] else b[0]-a[0]
        if crossed or delta>tolerance:regressed.append(name)
        elif delta<-tolerance:improved.append(name)
        elif x!=y:noise.append({'metric':name,'delta':y-x,'source_resolution':tolerance})
    verdict='unmeasured' if missing else 'tradeoff' if regressed and improved else 'harmful' if regressed else 'helped' if improved else 'neutral'
    # Retain a source-observed partial repair of an unsatisfied unit when its
    # actual deficit improves and every scalar tradeoff stays inside an already
    # satisfied interval. Do not demand monotonicity of all in-range scores;
    # keep their full vectors and tradeoff verdict. A failed objective, a newly
    # crossed floor, unmeasured requirement or harmful semantic review cannot
    # be compensated. This does not establish final source satisfaction.
    old_rules={v['id']:v for v in before['constraints']}
    new_rules={v['id']:v for v in after['constraints']}
    satisfied={'minimum_met','stretch_met'}
    deficit_improved=[name for name in improved if
        old_rules[name]['status']=='below_minimum' and
        new_rules[name].get('deficit') is not None and
        old_rules[name].get('deficit') is not None and
        new_rules[name]['deficit']<old_rules[name]['deficit']]
    safe_tradeoff=bool(not missing and deficit_improved and regressed and
        all(old_rules[name]['status'] in satisfied and
            new_rules[name]['status'] in satisfied for name in regressed))
    # Keep this very narrow source-resolution case separate from acceptance.
    # A tiny original visible face can have colour/foreground samples but no
    # complete Sobel neighbourhood. Its own measured material improvement is
    # useful even though its unobservable edge requirement remains open.
    # Missing output, an empty source mask, renderer failure or another missing
    # metric never enters this route. No other unit can compensate this one.
    source_limited=False
    if missing==['internal_edge_f1'] and deficit_improved and unit.get('reference_mask') and unit.get('evaluation_mask'):
        bm,am=before.get('measurements',{}),after.get('measurements',{})
        be,ae=bm.get('internal_edges',{}),am.get('internal_edges',{})
        source_limited=bool(
            not before.get('measurement_error') and not after.get('measurement_error') and
            not before.get('missing_output_bindings') and not after.get('missing_output_bindings') and
            be.get('support_neighborhood')==ae.get('support_neighborhood')=='sobel_3x3' and
            be.get('reference_points')==ae.get('reference_points')==0 and
            be.get('source_points_with_excluded_kernel_context')==ae.get('source_points_with_excluded_kernel_context')==0 and
            be.get('missing_source_feature_reason') and ae.get('missing_source_feature_reason') and
            bm.get('reference_foreground_pixels',0)>0 and
            bm.get('reference_foreground_pixels')==am.get('reference_foreground_pixels') and
            bm.get('evaluation_pixels',0)>0 and bm.get('evaluation_pixels')==am.get('evaluation_pixels') and
            am.get('candidate_foreground_pixels',0)>0 and
            all(old_rules[name]['status'] in satisfied and new_rules[name]['status'] in satisfied for name in regressed))
    return {'result':verdict,'improved':improved,'regressed':regressed,'missing':missing,'sampling_changes':noise,
            'floor_preserving_deficit_progress':safe_tradeoff,'independent_deficit_improvements':deficit_improved,
            'source_observability_limited_progress':source_limited,
            'source_unobservable_requirements':missing if source_limited else []}



def _actual_pixel_dependencies(task,state,before,after,direct):
    """Find affected source domains once; do not re-score an unchanged page."""
    import numpy as np
    from scipy import ndimage as ndi
    width,height=state['source_size']
    old=np.asarray(_canvas(str(safe_path(task,before['preview']['path'])),width,height))
    new=np.asarray(_canvas(str(safe_path(task,after['preview']['path'])),width,height))
    delta=np.any(old!=new,axis=2);affected=set()
    if not delta.any():return affected
    for uid,value in state.get('quality',{}).get('units',{}).items():
        if uid in direct:continue
        x,y,w,h=value['roi'];left,top,right,bottom=map(round,(x,y,x+w,y+h))
        local=delta[top:bottom,left:right]
        if not local.any():continue
        support=_mask(task,value.get('reference_mask'))
        if support is None:support=np.ones(local.shape,bool)
        elif support.shape!=local.shape:
            raise ValueError('Actual dependency and original source ownership use one fixed frame')
        # A changed neighbour contributes to the original Sobel neighbourhood.
        support=ndi.binary_dilation(support,structure=np.ones((3,3),bool))
        domain=_mask(task,value.get('evaluation_mask'))
        if domain is not None:
            if domain.shape!=local.shape:raise ValueError('Original evaluation domain frame changed')
            support &= domain
        if np.any(local&support):affected.add(uid)
    return affected


def repair_scope_effect(task,state,before,after,grants):
    """No successful target can carry a regressing changed peer into adoption.

    Score only actually changed bound source units, not a whole-page campaign.
    The fixed original definitions/intervals and complete vectors are retained.
    Unrelated units are pruned by the actual native write-set closure.
    """
    changed=changed_closure(state,grants);rows=[];blocking=[]
    units=state.get('quality',{}).get('units',{})
    direct={uid for uid,value in units.items() if changed.intersection(value.get('objects',[]))}
    owned={name for ident in direct for name in units[ident].get('objects',[])}
    dependent=set()
    render_context=set()
    # Office can change displayed SVG siblings after a resource replacement
    # even when their native nodes/bytes are protected. Preserve appearance as
    # well as XML: this shared renderer cohort is an actual dependent view,
    # not a whole-page review or permission to write to those siblings.
    prior_scene=read_json(safe_path(task,before['scene']['path']))
    actual_scene=read_json(safe_path(task,after['scene']['path']))
    prior_nodes={o['id']:o for o in prior_scene['objects']}
    actual_nodes={o['id']:o for o in actual_scene['objects']}
    replacements={oid for oid,fields in grants.items() if fields==['replace_component']}
    def replaced_svg(nodes,obj):
        if obj.get('render_type')!='svg':return False
        oid=obj['id']
        while oid in nodes:
            if oid in replacements:return True
            oid=nodes[oid].get('parent')
        return False
    # New replacement children may not occur in the baseline built-ID closure.
    # Read both saved ownership trees rather than ignoring incoming resources.
    svg_change=bool(replacements and any(replaced_svg(nodes,obj)
                     for nodes in (prior_nodes,actual_nodes) for obj in nodes.values()))
    if svg_change:
        for uid,value in units.items():
            if uid in direct:continue
            if any((prior_nodes.get(oid) or {}).get('render_type')=='svg' for oid in value.get('objects',[])):
                render_context.add(uid)
        dependent.update(render_context)
    for uid,value in units.items():
        upper=set((value.get('layering') or {}).get('occluders',[]))
        if uid in direct:dependent.update(upper)
        if upper&direct:dependent.add(uid)
        participants=set((value.get('relation') or {}).get('participants',[]))
        if participants&(direct|owned):dependent.add(uid)
    pixel_dependencies=_actual_pixel_dependencies(task,state,before,after,direct)
    dependent.update(pixel_dependencies)
    for value in units.values():
        if value['id'] not in direct|dependent:continue
        old=evaluate(task,state,before,value);new=evaluate(task,state,after,value)
        gain=effect(old,new,value)
        eligible=(new['status']=='numeric_minimum_met' or gain['result'] in ('helped','neutral')
                  or gain.get('floor_preserving_deficit_progress',False))
        unchanged=False
        if value['id'] not in direct:
            _,old_view=_crop_images(task,state,before,value['roi'])
            _,new_view=_crop_images(task,state,after,value['roi'])
            unchanged=old_view.tobytes()==new_view.tobytes()
        if new['status']=='required_unmeasured' or gain['missing']:
            eligible=unchanged or gain.get('source_observability_limited_progress',False)
        row={'unit':value['id'],'before':old,'after':new,'effect':gain,'eligible':eligible,
             'scope_role':'changed' if value['id'] in direct else 'unchanged_svg_render_context' if value['id'] in render_context else 'actual_changed_source_domain' if value['id'] in pixel_dependencies else 'source_layer_or_relation_dependency',
             'unchanged_saved_dependency_view':unchanged}
        rows.append(row)
        if not eligible:blocking.append(value['id'])
    from .source_property_protection import retained_material_effects
    retained=retained_material_effects(task,state,before,after)
    for property_row in retained:
        if not property_row['eligible'] and property_row['unit'] not in blocking:
            blocking.append(property_row['unit'])
    return {'eligible':not blocking,'changed_units':rows,'blocking_units':blocking,
            'retained_material_properties':retained,
            'svg_render_context_units':sorted(render_context),
            'actual_pixel_dependent_units':sorted(pixel_dependencies),
            'selection':'Each changed peer independently meets its fixed floors or has bounded deficit progress. A source-unobservable internal edge may retain only that same unit\'s measured progress; its missing edge and fixed targets stay open. No averaging or target compensation.'}


def _saved_native_names(path, bound_hash):
    """Only a newly discovered missing part needs this saved-output binding.

    The single source canvas is slide1. No redraw or host call is performed.
    Name presence never substitutes for independent source ROI or semantics.
    """
    from .resource_facts import derived_value
    return derived_value(path,bound_hash,{'saved_native_names':digest(__file__)},
                         lambda: _count_saved_native_names(path,bound_hash))

def _count_saved_native_names(path, bound_hash):
    from collections import Counter
    from .resource_facts import xml_part
    if digest(path)!=bound_hash:raise ValueError('Saved source output changed')
    slide=xml_part(path,'ppt/slides/slide1.xml',bound_hash)
    return dict(Counter(node.get('name') for node in slide.iter(
        '{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr') if node.get('name')))
