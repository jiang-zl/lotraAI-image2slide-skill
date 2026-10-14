"""Quality-driven raster eligibility from a bound actual paired drawing.

The scalar comparison cannot certify semantic fidelity. The host supplies
specific observed critical properties bound to the two saved-file views.
"""
from pathlib import Path
from .common import digest,safe_path,read_json,write_json

def compare(contract,base):
    from .raster_exception import _rendered, _same_context
    from .saved_ppt_diff import snapshot
    from .quality_policy import compare as arithmetic
    from PIL import Image
    if contract.get('schema')!='representation-trial-1':raise ValueError('Unknown representation trial')
    if contract.get('scientific_content_excluded') is not True or contract.get('edit_level')!='component':
        raise ValueError('Raster trial cannot flatten scientific content or promise internal vector edits')
    refs={}
    for key in ('source','vector_pptx','vector_render','raster_pptx','raster_render','asset'):
        ref=contract[key];path=safe_path(base,ref['path'])
        if digest(path)!=ref['sha256']:raise ValueError('Representation trial input changed: '+key)
        refs[key]=path
    vector_snapshot,raster_snapshot=snapshot(refs['vector_pptx']),snapshot(refs['raster_pptx'])
    vector_owner,raster_owner=contract['vector_owner_path'],contract['raster_owner_path']
    if vector_owner!=raster_owner or vector_owner not in vector_snapshot['objects'] or raster_owner not in raster_snapshot['objects']:
        raise ValueError('Representation comparison must keep the same actual semantic owner')
    _same_context(vector_snapshot,raster_snapshot,vector_owner,raster_owner)
    _,vector=_rendered(refs['vector_pptx'],refs['vector_render'])
    _,raster=_rendered(refs['raster_pptx'],refs['raster_render'])
    actual_hashes={digest(vector),digest(raster)}
    evidence=contract.get('observations',[])
    if not evidence or any(not all(o.get(k) for k in ('property','expected','vector_actual','raster_actual')) or
                           set(o.get('view_hashes',[]))!=actual_hashes for o in evidence):
        raise ValueError('Important quality observations must bind both actually rendered views')
    if any(o.get('critical') and o.get('raster_outcome')!='matched' for o in evidence):
        raise ValueError('A weighted total cannot compensate an incorrect critical property')
    reuse=contract.get('max_reuse_inches')
    if not isinstance(reuse,list) or len(reuse)!=2 or min(reuse)<=0:
        raise ValueError('Raster must declare an intended reuse size')
    with Image.open(refs['asset']) as im:
        ppi=[im.size[i]/reuse[i] for i in (0,1)]
    if min(ppi)<contract.get('minimum_ppi',250):raise ValueError('Raster is not clear at its intended reuse size')
    quality=arithmetic(contract['vector_scores'],contract['raster_scores'],contract['weights'],
                       protected=contract.get('protected_metrics',[]),min_gain=contract.get('minimum_gain',.06))
    return {'schema':'representation-decision-1','eligible':quality['decision']=='substantial_gain',
            'quality':quality,'effective_ppi':ppi,'source_sha256':digest(refs['source']),
            'asset_sha256':digest(refs['asset']),
            'evidence':evidence,'limits':'Actual paired quality evidence, not a universal beauty score. Independently preserve unrelated shapes and scientific meaning.'}

def write_decision(contract_file,output):
    contract_file=Path(contract_file);result=compare(read_json(contract_file),contract_file.parent)
    result['comparison_hash']=digest(contract_file);write_json(output,result);return result

def construct(task,state,component,spec):
    from .recipes import node
    ref=spec['comparison'];file=safe_path(task,ref['path'])
    if digest(file)!=ref['sha256']:raise ValueError('Frozen representation comparison changed')
    contract=read_json(file);decision=compare(contract,file.parent);content=spec['content']
    if (not decision['eligible'] or decision['source_sha256']!=state['source']['sha256']
            or decision['asset_sha256']!=content['sha256'] or contract.get('roi')!=component['roi']):
        raise ValueError('Raster cannot be promoted without this source/owner actual important quality gain')
    content={**content,'source_roi':component['roi'],'quality_comparison':ref,'source_semantic':component['semantic_class']}
    obj=node(component['id'],'photo',component.get('bbox',component['roi']),content,semantic='illustration_asset')
    obj['edit_contract']={'representation':'raster_module','required_operations':['move','resize','copy','replace'],
                         'unsupported_operations':['edit_pixels_in_ppt','edit_vector_nodes'],
                         'reason':'Selected after bound actual important quality gain; the semantic component remains independent.'}
    obj['evidence_status']='inferred' if content.get('provenance',{}).get('method')=='model_assisted' else 'observed'
    return [obj]
