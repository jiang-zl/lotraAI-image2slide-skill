"""Explicit source-pixel to saved native-point style proposals."""
import copy
from zipfile import ZipFile
from lxml import etree
from .common import read_json,safe_path,digest



def planned_points_per_source_pixel(state):
    """Same explicit planned canvas/rounding as the existing native builder."""
    import math
    width=state['source_size'][0];inches=state['analysis'].get('target_width_inches',width/96)
    if not isinstance(inches,(int,float)) or not math.isfinite(inches) or inches<=0 or width<=0:
        raise ValueError('Native source style fitting needs a valid explicit planned canvas')
    return round(inches*914400)/12700/width


def points_per_source_pixel(task,state,candidate):
    file=safe_path(task,candidate['pptx']['path'])
    if digest(file)!=candidate['pptx']['sha256']:raise ValueError('Saved native canvas changed')
    from .resource_facts import xml_part
    root=xml_part(file,'ppt/presentation.xml',candidate['pptx']['sha256'])
    size=root.find('{http://schemas.openxmlformats.org/presentationml/2006/main}sldSz')
    x=int(size.get('cx'))/12700/state['source_size'][0]
    y=int(size.get('cy'))/12700/state['source_size'][1]
    if abs(x-y)>max(x,y)*1e-4:raise ValueError('Anisotropic canvas needs a source-specific native style plan')
    return x


def outline_proposal(task,state,candidate,unit,object_id,source_width_px,source_evidence):
    if not 0<source_width_px<=12 or not source_evidence:raise ValueError('Bind an observed source outline in source pixels')
    scene=read_json(safe_path(task,candidate['scene']['path']));objects={o['id']:o for o in scene['objects']}
    if object_id not in unit['objects'] or object_id not in objects or objects[object_id]['render_type'] not in ('shape','path','connector'):
        raise ValueError('Use this exact existing independently bound native outline')
    obj=copy.deepcopy(objects[object_id]);ratio=points_per_source_pixel(task,state,candidate)
    obj['style']['line_width']=float(source_width_px*ratio)
    return {'baseline_hash':candidate['pptx']['sha256'],'source_hash':state['source']['sha256'],
        'unit':unit['id'],'object':obj,'allowed_changes':{object_id:['style.line_width']},
        'cause':'Original measured source-pixel line weight must be converted to saved native points',
        'calibration':{'source_width_px':source_width_px,'points_per_source_pixel':ratio,'native_width_points':obj['style']['line_width'],'source_evidence':source_evidence},
        'limits':'Unit conversion proposal only; native contour/pose/material and all other objects remain unchanged. Actual protected drawing decides effect.'}
