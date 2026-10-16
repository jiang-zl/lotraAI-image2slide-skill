"""Per-consumer dependencies and source-region identities."""
from functools import lru_cache
from pathlib import Path
from .common import ROOT, digest, identity, safe_path


ROUTE_MODULES = {
    'fixed_parameters': ('component_constructor','constructor_registry','build','native_commit','native_input','native_core_checks','native_core_inspect'),
    'local_fit': ('component_fit','component_search','component_solver','component_metrics','component_calibration','constructor_registry','appearance_metrics','boundary_geometry'),
    'assembly': ('component_relations','native_core_inspect','boundary_geometry'),
    'instance': ('component_instances','component_variants','component_font_instances','font_contract','tables','native_input','component_relations','native_snapshot'),
    'specialist': ('component_relations','native_core_inspect'),
}
KIND_MODULES = {
    'shape': ('presets',), 'path': ('semantic_curves',), 'bezier': ('semantic_curves',),
    'text': ('font_contract','font_embedding'), 'equation': ('mathml','font_contract','font_embedding'),
    'trace': ('geometry','build','native_core_inspect'),
    'connector': ('component_relations','source_connections'), 'table': ('build','tables','font_contract','font_embedding'), 'photo': ('build',),
}
POLICY_KEYS = {
    'fixed_parameters': ('fixed_parameter_route','grouped_primitives','fixed_owner_types'),
    'local_fit': ('parameter_search','calibration_models'),
    'assembly': ('locking',), 'instance': ('instance_policy',), 'specialist': (),
}


@lru_cache(maxsize=256)
def _file_hash(file,size,mtime):
    return digest(Path(file))


def version(name):
    file=ROOT/'scripts/core'/(name+'.py')
    if not file.is_file(): raise ValueError('Unregistered implementation dependency: '+name)
    stat=file.stat()
    return _file_hash(str(file),stat.st_size,stat.st_mtime_ns)


def consumer(row,policy,state=None):
    modules=set(ROUTE_MODULES[row['route']])
    modules.update(('component_protocol','component_workflow','component_revision','component_transactions','component_batch',
                    'native_core_checks','native_core_inspect','component_metric_adapters','component_features','native_scope'))
    for kind in row.get('owner_types',[]): modules.update(KIND_MODULES.get(kind,()))
    modules.update(row.get('implementation_dependencies',[]))
    if row.get('problem_id'): modules.add('problem_control')
    if row.get('curve_spec_hash'): modules.add('curve_functions')
    if row.get('feature_basis'):
        modules.update(('component_source_features','native_surfaces','surface_metrics'))
    if row.get('route')=='assembly': modules.update(('knowledge','knowledge_flow'))
    source_adapter=row.get('model',{}).get('source_adapter')
    if source_adapter:
        from .constructor_registry import SOURCE_ADAPTERS
        if source_adapter not in SOURCE_ADAPTERS:raise ValueError('Unregistered source adapter')
        modules.update((source_adapter,'constructor_registry'))
    if any(metric.get('source_calibration') for metric in row.get('metrics',[])):
        modules.add('component_calibration')
    selected_policy={key:policy.get(key) for key in POLICY_KEYS[row['route']]}
    if 'calibration_models' in selected_policy:
        names={m.get('source_calibration',{}).get('model') for m in row.get('metrics',[])}
        selected_policy['calibration_models']={name:policy.get('calibration_models',{}).get(name) for name in names if name}
    modules.update(('component_fields','component_native_plan','native_ownership','native_input'))
    if set(row.get('owner_types',[]))&{'text','table','equation'}:
        modules.update(('font_collection','component_fonts','component_font_instances','font_resources','font_retention','tables'))
    environment=None if row['route']=='fixed_parameters' else (state or {}).get('capabilities',{}).get('fingerprint')
    return {'environment':environment,'font_policy':digest(ROOT/'config/font-collections.json'),
            'modules':{name:version(name) for name in sorted(modules)},
            'schema':digest(ROOT/'schemas/component-contract.schema.json'),
            'policy':selected_policy,
            'model':row.get('model'),'design_revision':8}


def source_region(task,state,row):
    from .appearance_metrics import canvas
    roi=row.get('roi')
    if not roi:
        return identity({'source_refs':row.get('source_refs'),'source_units':row.get('source_units'),
                         'source_evidence':row.get('source_evidence'),'canvas':state['source_size']})
    source=safe_path(task,state['source']['path'])
    x,y,w,h=roi
    import hashlib
    data=canvas(str(source),state['source']['sha256'],tuple(state['source_size']))
    crop=data[int(y):int(y+h+.999999),int(x):int(x+w+.999999)]
    pixels=hashlib.sha256(crop.tobytes()).hexdigest()
    return identity({'roi':roi,'pixels':pixels,'canvas':state['source_size'],
                     'support':row.get('support_mask')})


def changed_facets(previous,current):
    return {key for key in set(previous)|set(current) if previous.get(key)!=current.get(key)}

