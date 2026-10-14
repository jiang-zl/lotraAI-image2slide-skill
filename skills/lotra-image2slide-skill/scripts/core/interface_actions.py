"""Finite deterministic translations for a frozen source interface.

Predicted masks propose an action; only new actual saved/rendered captures can
accept it. The solver cannot widen a tolerance or move a different role.
"""
import math
import numpy as np
from . import semantic_composition as sc
from .semantic_interfaces import evaluate
from .boundary_geometry import saved_nodes


def propose(task,state,candidate,row):
    from .source_spacing import prepare
    source,effective=prepare(task,state,row)
    if effective is None:return {'status':source['status'],'contract':row['id'],'original_spacing':source}
    row=effective
    repair=row.get('repair',{})
    radius=repair.get('max_shift_px');step=repair.get('step_px',.25)
    if (repair.get('operator')!='translate_second_part' or type(radius) not in (int,float) or
            not math.isfinite(radius) or not 0<radius<=8 or step not in (.25,.5,1.)):
        return {'status':'SOURCE_REPAIR_DOMAIN_REQUIRED','contract':row['id']}
    pptx=sc._ref(task,candidate['pptx']);raw,parents,_=sc._native(pptx)
    nodes=saved_nodes(pptx,state['source_size'])
    groups=sc._capture_groups(row,raw,parents);cache=state.get('semantic_composition',{}).get('captures',{})
    responses=[sc._response(task,cache,sc._capture_key(raw,parents,g,pptx,mode),state['source_size'],state,retain_native=True) for g,mode in groups]
    current=evaluate(row,responses,nodes,parents,state['source_size'])
    if current['passed']:return {'status':'ALREADY_MET','contract':row['id'],'actual':current}
    if any(v is None for v in responses):return {'status':'ACTUAL_CAPTURE_REQUIRED','contract':row['id']}
    if any(nodes[n].get('error') or not nodes[n].get('axis_aligned') or nodes[n]['tag']=='grpSp' for n in row['part_sets'][1]):
        return {'status':'UNSUPPORTED_NATIVE_TRANSLATION','contract':row['id']}
    height,width=responses[0].shape;sx,sy=state['source_size'][0]/width,state['source_size'][1]/height
    # Exact discrete shifts: never interpolate a matte or infer solid contact
    # from a weak fringe. Search smallest displacements first and stop once
    # all equally small admissible alternatives have been considered.
    n=math.floor(radius/step)
    shifts=[(dx*step,dy*step) for dx in range(-n,n+1) for dy in range(-n,n+1)
            if 0 < math.hypot(dx*step,dy*step)<=radius+1e-9]
    shifts.sort(key=lambda p:(p[0]*p[0]+p[1]*p[1],abs(p[0]),p[1],p[0]))
    best=None;count=0;gray=responses[1]; shifted=np.empty_like(gray)
    for dx,dy in shifts:
        squared=dx*dx+dy*dy
        if best and squared>best[0][0]+1e-9:break
        ix,iy=round(dx/sx),round(dy/sy)
        if abs(ix*sx-dx)>1e-8 or abs(iy*sy-dy)>1e-8:continue
        shifted.fill(255)
        xa,xb=max(0,ix),min(width,width+ix);ya,yb=max(0,iy),min(height,height+iy)
        shifted[ya:yb,xa:xb]=gray[ya-iy:yb-iy,xa-ix:xb-ix]
        observed=evaluate(row,[responses[0],shifted],nodes,parents,state['source_size']);count+=1
        if observed['passed']:
            key=(squared,observed['values']['anchor_error_upper_px'],-observed['values']['solid_interface_width_lower_px'],dx,dy)
            if best is None or key<best[0]:best=(key,observed)
    if best is None:
        return {'status':'NO_ADMISSIBLE_FINITE_REPAIR','contract':row['id'],'evaluated':count,'actual':current,
                'next':'Return to the original part/port or shape construction; never enlarge the frozen tolerance'}
    dx,dy=best[0][-2:]
    return {'status':'PROPOSED_REQUIRES_ACTUAL_SAVE_RENDER','contract':row['id'],'evaluated':count,
            'objects':row['part_sets'][1],'translation_source_px':[dx,dy],'predicted':best[1],
            'actual_before':current,'limits':'A translated cached matte is only a finite proposal, never acceptance evidence'}
