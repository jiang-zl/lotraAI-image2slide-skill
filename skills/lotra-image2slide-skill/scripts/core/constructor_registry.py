"""Typed constructors and original-only adapter routing."""
import copy
import math
from .common import identity, read_json, write_json

FIXED_TYPES = {'text','shape','equation','path','bezier','connector','table','photo','trace'}
SOURCE_ADAPTERS = {'primitive_source_fit','source_preset_fit','source_detail_fit',
                   'source_fit','source_feature_functions','semantic_curves'}


def select(row,nodes):
    owned=[nodes[owner] for owner in row['owners']]
    kinds=sorted({node['render_type'] for node in owned})
    if 'svg' in kinds:
        raise ValueError('SOURCE_DECISION_REQUIRED: expand SVG into native shape/path/Bezier owners before binding; SVG picture embedding is not an editable constructor')
    from .component_metric_adapters import validate_metrics
    validate_metrics(row)
    row['owner_types']=kinds
    model=row.setdefault('model',{'id':'native_scene','version':1})
    if model.get('source_adapter') and model['source_adapter'] not in SOURCE_ADAPTERS:
        raise ValueError('Unregistered source constructor')
    if row['route'] not in ('assembly','instance') and row.get('frozen_parameters') and not any(
            parameter.get('state')=='tunable' for parameter in row.get('parameters',{}).values()):
        if set(kinds)<=FIXED_TYPES: row['route']='fixed_parameters'
    if row['route']=='local_fit':
        targets=[m['id'] for m in row.get('metrics',[]) if m.get('role')=='target' and m.get('applicable',True)]
        links=row.setdefault('parameter_metric_map',{})
        bindings=row.get('fit',{}).get('bindings',{})
        for name,parameter in row.get('parameters',{}).items():
            if parameter.get('state')!='tunable' or name in links: continue
            binding=bindings.get(name,{})
            # Geometric native fields affect geometric metrics; paint diagnostics
            # never become optimization targets by this default association.
            if binding.get('field',[None])[0] in ('bbox','content','style'):
                geometric=[key for key in targets if key.startswith(('boundary_distance','keypoint','centerline','curve_distance','line_width','endpoint'))]
                if geometric: links[name]=geometric
    row.setdefault('model',model)
    return row


def work_units(row,operation):
    if operation in ('evaluate','instantiate'): return 1
    if operation=='fit':
        active=sum(p.get('state')=='tunable' for p in row.get('parameters',{}).values())
        return 1+math.ceil(min(active,6)/3)
    if operation=='qualify': return 1+math.ceil(len(row.get('required_relations',[]))/8)
    return 1+math.ceil(row.get('model',{}).get('segments',0)/8)


def source_prepare(task,request):
    """Run a registered source adapter; return facts/proposal, never qualification."""
    from . import agent_runtime as a,component_workflow as c
    task,state=a._state(task);contract,ledger=c._load(task,state)
    row=c.component_row(task,state,contract,request['component'])
    if request.get('source_hash')!=state['source']['sha256']: raise ValueError('Original revision required')
    model=row.get('model',{}); name=model.get('source_adapter')
    spec=copy.deepcopy(request.get('source_request',model.get('source_request',{})))
    if name not in SOURCE_ADAPTERS or not spec: raise ValueError('Located typed source request required')
    spec['source_hash']=state['source']['sha256']
    cache_request={key:value for key,value in spec.items() if key!='source_hash'}
    from .component_dependencies import version
    cache_basis={'region':row.get('source_region_key'),'component':row['id'],'adapter':name,'request':cache_request,
                 'adapter_version':version(name),'registry_version':version('constructor_registry')}
    if name=='semantic_curves':cache_basis['source_scene']=contract['source_scene']
    cached=task/'component-workflow'/('Source-adapter-'+identity(cache_basis)+'.json')
    if cached.exists():
        result=read_json(cached)
        current_basis={'cached':c._ref(task,cached),'source_hash':state['source']['sha256'],
                       'component':row['id'],'region':row.get('source_region_key')}
        proposal=task/'component-workflow'/('Source-proposal-'+identity(current_basis)+'.json')
        if not proposal.exists():
            result.update(source_hash=state['source']['sha256'],component=row['id'],
                          acceptance=False,derivation=current_basis)
            write_json(proposal,result)
        record=ledger['components'][row['id']]
        record['source_proposal']=c._ref(task,proposal);record['status']='SOURCE_DECISION_REQUIRED'
        from .common import writer
        with writer(task):c._save_ledger(task,state,ledger,'source_parameters_available',{'component':row['id']})
        return {'status':'SOURCE_DECISION_REQUIRED','proposal':c._ref(task,proposal),'acceptance':False}
    component={'id':row['id'],'roi':row['roi'],'semantic_class':row.get('semantic_class','source_part')}
    if name=='primitive_source_fit':
        from .primitive_source_fit import fit
        result=fit(task,state,spec)
    elif name=='source_fit':
        from .source_fit import construct
        result={'objects':construct(task,state,component,spec)}
    elif name=='source_feature_functions':
        from .source_feature_functions import construct
        result={'objects':construct(task,state,component,spec)}
    elif name=='source_preset_fit':
        from .source_preset_fit import fit_hollow_right_arrow,fit_flat_mark
        from .common import safe_path,digest
        from PIL import Image
        import numpy as np
        x,y,w,h=spec['roi']
        with Image.open(safe_path(task,state['source']['path'])) as im:
            rgb=np.asarray(im.convert('RGB').crop((x,y,x+w,y+h)),float)
        mask_ref=spec['support_mask'];mask_path=safe_path(task,mask_ref['path'])
        if digest(mask_path)!=mask_ref['sha256']:raise ValueError('Source mask changed')
        with Image.open(mask_path) as im:owned=np.asarray(im.convert('L'))>0
        family=spec['family']
        function=fit_hollow_right_arrow if family.get('semantic_shape')=='hollow_right_arrow' else fit_flat_mark
        result=function(rgb,owned,spec['foreground_rgb'],spec['background_rgb'],family)
    elif name=='source_detail_fit':
        from .source_detail_fit import fit
        result=fit(task,state,spec)
    else:
        # Semantic curves are compiled from a source-declared Scene by the
        # existing native constructor. No guessed alternate API is invoked.
        result={'source_scene':contract['source_scene'],'semantic_curve_specification':spec,
                'next':'bind the declared finite curves to source_scene owners'}
    result.update(source_hash=state['source']['sha256'],component=row['id'],acceptance=False)
    file=cached
    write_json(file,result)
    record=ledger['components'][row['id']]
    record['source_proposal']=c._ref(task,file); record['status']='SOURCE_DECISION_REQUIRED'
    from .common import writer
    with writer(task): c._save_ledger(task,state,ledger,'source_parameters_prepared',{'component':row['id']})
    return {'status':'SOURCE_DECISION_REQUIRED','proposal':c._ref(task,file),
            'reason':'Bind original-derived facts or revise the declared model; proposal is not local acceptance'}


def precision_inputs(metric,row,scene):
    """Derive measurement precision from the actual coordinate and source facts."""
    calibration=copy.deepcopy(metric['source_calibration'])
    facts=row.get('source_facts',[])
    if calibration.get('uncertainty') is None:
        selected=[fact for fact in facts if fact.get('id') in metric.get('source_fact_ids',[])]
        if not selected or any(not f.get('evidence') or not f.get('interval') for f in selected):
            raise ValueError('SOURCE_DECISION_REQUIRED: located source intervals required')
        if any(f.get('unit')!=metric.get('unit') or len(f['interval'])!=2 or f['interval'][0]>f['interval'][1] for f in selected):
            raise ValueError('SOURCE_DECISION_REQUIRED: matching source interval units required')
        calibration['uncertainty']=max((f['interval'][1]-f['interval'][0])/2 for f in selected)
    if calibration.get('quantization') is None:
        from .native_input import scene_dimensions
        canvas=scene['canvas']; emu_per_px=scene_dimensions(scene)[0]/canvas['width']
        native=.5/emu_per_px
        curve=row.get('model',{}).get('curve_precision_source_px',0)
        sampling_scale=metric.get('sampling_scale',1)
        if type(sampling_scale) not in (int,float) or sampling_scale<=0:raise ValueError('Positive sampling scale required')
        sampling=0 if metric.get('measurement_domain')=='analytic' else .5/sampling_scale
        calibration['quantization']=native+curve+sampling
        metric['precision_terms']={'native':native,'curve':curve,'sampling':sampling}
    return calibration

