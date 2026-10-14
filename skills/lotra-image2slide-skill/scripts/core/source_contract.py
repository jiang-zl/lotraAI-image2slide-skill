"""Canonical source/derived contract reconciliation, shared by every gate.

Facts come from the frozen source specification. Bindings and fingerprints
are recomputed with the public native binder. Observation status is checked
by the observation gate; it cannot modify either of those two domains.
"""
import copy
import math
from .common import identity,digest,safe_path,read_json,write_json

VERSION = 'source-contract-1'
SPEC_FIELDS = frozenset(('version', 'owner', 'source_hash', 'coverage_statement',
    'parts', 'relations', 'unassigned_features', 'coverage_bindings', 'layout_review','source_grid'))
PART_FIELDS = frozenset(('id', 'roi', 'profile', 'quality_intent', 'layering',
    'features', 'metrics', 'protocol', 'priority', 'objects', 'landmarks',
    'reference_mask', 'evaluation_mask', 'target_basis', 'source_feature_ids',
    'appearance_policy', 'source_word_anchor', 'source_glyph_colour_observation'))
METRIC_FIELDS = frozenset(('id', 'min', 'max', 'stretch', 'max_regression'))
OBSERVATION_FIELDS = frozenset(('status',))


def finite(value, path='contract'):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Nonfinite number: ' + path)
    if isinstance(value, dict):
        for key, child in value.items():
            finite(child, path + '.' + str(key))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            finite(child, path + '[' + str(index) + ']')


def fields(value, allowed, path):
    if not isinstance(value, dict):
        raise ValueError('Typed object required: ' + path)
    unknown = set(value) - allowed
    if unknown:
        raise ValueError('Unregistered fields in ' + path + ': ' + ','.join(sorted(unknown)))
    finite(value, path)


def validate_spec(spec):
    fields(spec, SPEC_FIELDS, 'source_specification')
    if 'source_grid' in spec and not isinstance(spec['source_grid'],dict):
        raise ValueError('Typed object required: source_specification.source_grid')
    def records(value, path):
        if not isinstance(value, list):
            raise ValueError('Typed list required: ' + path)
        for index, child in enumerate(value):
            if not isinstance(child, dict):
                raise ValueError('Typed object required: ' + path + '[' + str(index) + ']')
        return value
    def protocol(record, path):
        if 'protocol' in record and not isinstance(record['protocol'], dict):
            raise ValueError('Typed object required: ' + path + '.protocol; use {} for the fixed default protocol')
    def object_field(record, name, path, optional=False):
        if name not in record:return None
        value=record[name]
        if optional and value is None:return None
        if not isinstance(value,dict):raise ValueError('Typed object required: '+path+'.'+name)
        return value
    def strings(record, name, path):
        if name in record and (not isinstance(record[name],list)
                or any(not isinstance(v,str) or not v for v in record[name])):
            raise ValueError('Typed string list required: '+path+'.'+name)
    def text_field(record, name, path):
        if name in record and not isinstance(record[name],str):
            raise ValueError('Typed string required: '+path+'.'+name)
    def roi(record, path):
        if 'roi' in record:
            value=record['roi']
            if (not isinstance(value,list) or len(value)!=4
                    or any(type(v) not in (int,float) or not math.isfinite(v) for v in value)):
                raise ValueError('Four finite source coordinates required: '+path+'.roi')
    def evidence(record, path):
        value=object_field(record,'evidence',path)
        if value is not None:
            roi(value,path+'.evidence')
            for name in ('source_hash','description'):text_field(value,name,path+'.evidence')
    def quality_intent(record,path):
        value=object_field(record,'quality_intent',path,optional=True)
        if value is None:return
        own=path+'.quality_intent'
        object_field(value,'source_reliability',own)
        object_field(value,'approved_reference',own)
        if 'source_constraints' in value:records(value['source_constraints'],own+'.source_constraints')
        design=object_field(value,'design_contract',own)
        if design is not None and 'constraints' in design:records(design['constraints'],own+'.design_contract.constraints')
    for name in ('parts', 'relations', 'coverage_bindings', 'unassigned_features'):
        records(spec.get(name, []), 'source_specification.' + name)
    for index,part in enumerate(spec.get('parts', [])):
        path = 'source_part.' + str(part.get('id'))
        fields(part, PART_FIELDS, path)
        protocol(part, path)
        records(part.get('features', []), path + '.features')
        path='source_specification.parts['+str(index)+']'
        roi(part,path);strings(part,'objects',path);strings(part,'source_feature_ids',path)
        for name in ('id','profile','priority','appearance_policy'):text_field(part,name,path)
        for name in ('landmarks','layering','reference_mask','evaluation_mask','source_word_anchor'):
            object_field(part,name,path,optional=True)
        quality_intent(part,path)
        for feature_index,feature in enumerate(part.get('features',[])):
            own=path+'.features['+str(feature_index)+']';evidence(feature,own)
            for name in ('id','category','status','literal'):text_field(feature,name,own)
            for name in ('ast','cell_format'):object_field(feature,name,own)
            if 'math_spans' in feature:records(feature['math_spans'],own+'.math_spans')
        metrics = part.get('metrics')
        if metrics is not None:
            validate_metrics(metrics)
    for index,relation in enumerate(spec.get('relations', [])):
        protocol(relation, 'source_relation.' + str(relation.get('id')))
        validate_metrics(relation.get('metrics', []))
        path='source_specification.relations['+str(index)+']'
        evidence(relation,path);roi(relation,path)
        for name in ('participants','objects'):strings(relation,name,path)
        for name in ('id','status'):text_field(relation,name,path)
        measurement=object_field(relation,'measurement',path)
        if measurement is not None:object_field(measurement,'contract',path+'.measurement')
    for index,record in enumerate(spec.get('coverage_bindings',[])):
        path='source_specification.coverage_bindings['+str(index)+']'
        evidence(record,path);strings(record,'quality_units',path)
        for name in ('source_part','role','status'):text_field(record,name,path)
    for index,record in enumerate(spec.get('unassigned_features',[])):
        path='source_specification.unassigned_features['+str(index)+']'
        roi(record,path);text_field(record,'description',path)
    review=object_field(spec,'layout_review','source_specification')
    if review is not None:strings(review,'important_relation_ids','source_specification.layout_review')


def validate_metrics(metrics):
    if not isinstance(metrics, list):
        raise ValueError('Metrics must be a list')
    ids = []
    for metric in metrics:
        fields(metric, METRIC_FIELDS, 'metric')
        if not isinstance(metric.get('id'), str) or not metric['id']:
            raise ValueError('Nonempty string required: metric.id')
        for name in ('min', 'max', 'stretch', 'max_regression'):
            value = metric.get(name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise ValueError('Finite number required: metric.' + name)
        ids.append(metric.get('id'))
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate metric IDs')


def seal_pending(task,state):
    quality=state.get('quality',{})
    activation=task/'source/contracts/Activation.json'
    if state.get('objectives',{}).get('source_contract_seals') and not activation.exists():
        write_json(activation,{'schema':VERSION,'source_hash':state.get('source',{}).get('sha256'),
            'required':'All original specifications must retain independent frozen records'})
    pending=quality.pop('_pending_source_seals',[])
    for owner in sorted(set(pending)):
        spec=quality['specifications'][owner];sha=identity(spec)
        file=task/'source/contracts'/(sha+'.json')
        if file.is_file():
            if identity(read_json(file))!=sha:raise ValueError('Frozen source contract changed')
        else:write_json(file,spec)
        old=quality.setdefault('frozen_specifications',{}).get(owner)
        ref={'path':file.relative_to(task).as_posix(),'sha256':digest(file),'spec_identity':sha}
        if old and old!=ref:quality.setdefault('contract_history',[]).append({'owner':owner,'previous':old,'current':ref})
        quality['frozen_specifications'][owner]=ref

def verify_seals(task,state):
    quality=state.get('quality',{})
    activation=task/'source/contracts/Activation.json'
    active=state.get('objectives',{}).get('source_contract_seals')
    if activation.exists():
        if not active:raise ValueError('The activated source contract cannot be disabled in mutable task state')
        if read_json(activation).get('source_hash')!=state.get('source',{}).get('sha256'):
            raise ValueError('Source contract activation belongs to another original')
    elif not active:return
    for owner,spec in quality.get('specifications',{}).items():
        ref=quality.get('frozen_specifications',{}).get(owner)
        if not ref:raise ValueError('Source contract lacks its independent frozen record: '+owner)
        file=safe_path(task,ref['path'])
        if digest(file)!=ref['sha256'] or identity(read_json(file))!=identity(spec) or identity(spec)!=ref['spec_identity']:
            raise ValueError('Source facts differ from the frozen contract: '+owner)

def reconcile(state,task=None):
    from .source_quality import compile_spec, bind_objects
    quality = state.get('quality', {})
    actual = quality.get('units', {})
    expected, errors = {}, []
    try:
        from .catalog_source import verify_frozen
        if task is not None:verify_frozen(task,state)
    except (ValueError,KeyError,OSError) as error:
        errors.append({'field':'original_catalog_review','reason':str(error)})
    if state.get('objectives',{}).get('source_contract_seals') or task is not None and (task/'source/contracts/Activation.json').exists():
        try:
            if task is None:raise ValueError('Source contract verification requires its task resource base')
            verify_seals(task,state)
        except (ValueError,KeyError,OSError) as error:errors.append({'field':'frozen_source_contracts','reason':str(error)})
    for component in state.get('analysis', {}).get('components', []):
        owner = component['id']
        spec = quality.get('specifications', {}).get(owner)
        if not spec:
            errors.append({'owner': owner, 'reason': 'ORIGINAL_SPECIFICATION_MISSING'})
            continue
        try:
            compiled = compile_spec(state, component, spec)
            validation = dict(state)
            validation['quality'] = {**quality, 'units': compiled,
                'representation_debt': copy.deepcopy(quality.get('representation_debt', {})),
                'observations': dict(quality.get('observations', {}))}
            built = state.get('built', {}).get(owner)
            if built:
                bind_objects(validation, owner, built)
            overlap = set(expected) & set(compiled)
            if overlap:
                raise ValueError('Duplicate compiled source units: ' + ','.join(sorted(overlap)))
            expected.update(compiled)
        except (ValueError, KeyError, TypeError) as error:
            errors.append({'owner': owner, 'reason': str(error)})
    if set(actual) != set(expected):
        errors.append({'field': 'unit_ids', 'missing': sorted(set(expected) - set(actual)),
                       'unexpected': sorted(set(actual) - set(expected))})
    inherited = set(state.get('prior_source_requirements', {}).get('unit_ids', []))
    if inherited - set(actual):
        errors.append({'field': 'historical_unit_ids', 'missing': sorted(inherited - set(actual))})
    for uid in sorted(set(expected) & set(actual)):
        want, got = expected[uid], actual[uid]
        try:
            finite(got, uid)
            validate_metrics(got.get('metrics', []))
            # Union is deliberate: additions require a registered compiler
            # definition, rather than being ignored by an old field subset.
            for key in sorted((set(want) | set(got)) - OBSERVATION_FIELDS):
                a, b = want.get(key), got.get(key)
                if key == 'objects':
                    a, b = sorted(set(a or [])), sorted(set(b or []))
                if identity(a) != identity(b) or (key in want) != (key in got):
                    errors.append({'unit': uid, 'field': key, 'reason': 'COMPILED_CONTRACT_MISMATCH'})
        except (ValueError, KeyError, TypeError) as error:
            errors.append({'unit': uid, 'reason': str(error)})
    return {'schema': VERSION, 'passed': not errors, 'errors': errors,
            'source_units': len(actual), 'compiled_units': len(expected)}
