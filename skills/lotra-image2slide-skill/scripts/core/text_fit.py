"""Propose bounded font-size patches from actual PowerPoint text bounds."""
import copy
import math
from .common import digest,identity,read_json
from .state import closure


def propose(scene,pptx,bounds_file,object_ids,*,padding_points=0.5,minimum_scale=.7):
    report=read_json(bounds_file)
    if report.get('pptx_hash')!=digest(pptx):raise ValueError('Text bounds do not match saved PPTX')
    measured={o['id']:o for o in report['objects']};objects={o['id']:o for o in scene['objects']}
    operations=[];measurements=[]
    for id in object_ids:
        obj=objects[id];record=measured.get(id)
        if not record or record.get('status')!='MEASURED':raise ValueError('No real text bounds for '+id)
        frame,ink=record['frame'],record['ink']
        if any(not math.isfinite(x) for x in frame+ink) or min(ink[2:])<=0:raise ValueError('Invalid text measurement')
        factor=min(1,(frame[2]-padding_points)/ink[2],(frame[3]-padding_points)/ink[3])
        if factor<minimum_scale:raise ValueError('Required shrink exceeds allowed typography repair: '+id)
        measurements.append({'id':id,'measured_ink_pt':ink,'frame_pt':frame,'factor':factor})
        if factor<1:
            style=copy.deepcopy(obj['style']);style['font_size']=math.floor(style['font_size']*factor*100)/100
            operations.append({'object_id':id,'field':'style','value':style})
    if not operations:raise ValueError('No overflow repair required')
    ids={op['object_id'] for op in operations}
    patch={'task_id':'measured-text-fit','base_scene_revision':scene['revision'],'base_scene_hash':identity(scene),
           'expected_versions':{id:objects[id]['versions'] for id in closure(scene,ids) if id in objects},'operations':operations}
    grant={'task_id':patch['task_id'],'object_ids':sorted(ids),'allowed_fields':['style'],'role':'formula_worker'}
    return {'patch':patch,'grant':grant,'measurements':measurements,'scope':'font-size-only candidate; requires fresh actual rendering and reference review'}
