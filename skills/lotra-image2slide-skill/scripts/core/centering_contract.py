"""Source-bound alignment decisions for every direct containment edge.

Semantic ownership comes from the source parser. Geometry proposes the axes;
explicit source exceptions are frozen before measuring a candidate. Neither
an object's category nor a parent aggregate PASS exempts a nested child.
"""
import math
from .clearance_balance import measure

VERSION='direct-member-joint-centering-1'

def decisions(container,elements,containers):
    x,y,w,h=container['source_bbox'];unc=container['target']['source_uncertainty_px'];rows=[]
    for member in container['members']:
        child=(containers if member in containers else elements)[member]
        a,b,c,d=child['source_bbox'];offset=[a+c/2-x-w/2,b+d/2-y-h/2]
        threshold=[max(1.,span*.02)+unc for span in (w,h)]
        asymmetric=container['target'].get('target_asymmetry_px',[0.,0.])!=[0.,0.]
        # A grid/row's individual primitives are positioned members, not
        # independent symbols all destined for the parent center. A nested
        # semantic container can itself align; a leaf needs its frozen source
        # alignment intent or the unambiguous single-member rule.
        declared=child.get('centering_axes')
        if declared is not None and (not isinstance(declared,list) or len(set(declared))!=len(declared) or not set(declared)<={'x','y'}):
            raise ValueError('Original alignment intent uses distinct finite axes')
        source_layout=container['target'].get('placement_intent')=='source_layout'
        axes=[] if asymmetric else declared if declared is not None else [] if source_layout else ['x','y'] if len(container['members'])==1 else [axis for i,axis in enumerate(('x','y')) if abs(offset[i])<=threshold[i]] if member in containers else []
        rows.append({'member':member,'required_axes':axes,'source_offset_px':offset,
            'source_threshold_px':threshold,'decision':'center' if axes else 'retain_source_placement',
            'basis':'frozen_original_alignment_intent' if declared is not None else 'original_semantic_source_layout' if source_layout else 'authorized_single_member_center' if len(container['members'])==1 else 'original_nested_container_opposing_bounds' if member in containers else 'positioned_member_in_complete_layout_aggregate',
            'source_evidence':child['source_evidence']})
    return rows

def joint(content,interior,tolerance,asymmetry=(0.,0.),axes=('x','y'),center_offset=(0.,0.)):
    if tolerance<=0 or not math.isfinite(tolerance):raise ValueError('Frozen finite joint centering tolerance required')
    a,b,c,d=content.bounds;x,y,r,s=interior.bounds
    error=[(a+c-x-r)/2-center_offset[0],(b+d-y-s)/2-center_offset[1]]
    if not interior.buffer(.025).covers(content):
        return {'version':VERSION,'center_distance_px':math.hypot(*error),
            'axes':{axis:{'center_error_px':error[i],'clearance_error_px':None,'tolerance_px':tolerance,
                'required':axis in axes,'passed':False} for i,axis in enumerate(('x','y'))},
            'directional_clearances':None,'passed':False,'repair_delta_px':[-v for v in error],
            'next':'Measured overflow requires bounded geometry/layout repair before gap balancing'}
    gaps=measure(content,interior,asymmetry)
    checks={axis:{'center_error_px':error[i],'clearance_error_px':gaps[axis]['actual'],
        'tolerance_px':tolerance,'required':axis in axes,
        'passed':axis not in axes or max(abs(error[i]),abs(gaps[axis]['actual']))<=tolerance}
        for i,axis in enumerate(('x','y'))}
    return {'version':VERSION,'center_distance_px':math.hypot(*error),'axes':checks,
        'directional_clearances':gaps,'passed':all(row['passed'] for row in checks.values()),
        'repair_delta_px':[-(error[i]+gaps[axis]['actual'])/2 if axis in axes else 0. for i,axis in enumerate(('x','y'))]}
