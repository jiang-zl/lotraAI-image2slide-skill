"""Source-grounded discrepancy disposition; a clear low-score part cannot pass.

The host interprets recoverability from original pixels and parent context.
Programs reject unsupported exits and apply fixed, disclosed red bands.
Enhancement is a display aid, never an independent source of new facts.
"""
import math
from .common import identity,safe_path

KINDS={'clear_structure','blurred_illustration','stochastic_texture','subpixel_detail','unresolved'}
POLICY={'schema':'source-observability-1','clear_ssim_red_below':.45,
        'clear_psnr_red_below_db':9.,'psnr_joint_edge_f1_below':.65,
        'subpixel_max_short_side':8.,'subpixel_max_area':64.,
        'scope':'Engineering red bands schedule local repairs; neither universal image-quality thresholds nor semantic truth from scores.'}

def validate(row,item,nodes,state):
    o=row.get('source_observability',{})
    if o.get('kind') not in KINDS or not o.get('source_evidence'):
        raise ValueError('Classify recoverability from original detail, not from low candidate scores')
    if o['kind'] in ('blurred_illustration','stochastic_texture','unresolved') and not o.get('uncertainty_regions'):
        raise ValueError('Locate the original blur, stochastic texture or unresolved evidence')
    parts=row['observed_parts'];checks=row['checks']
    structural={c.get('object') for c in checks if c['type'] in ('native_frame','source_function_frame')} | {c[k] for c in checks if c['type'] in ('join','contains','layer') for k in ('a','b')}
    names={n for p in parts for n in p['objects']}
    if o['kind']!='stochastic_texture' and names-structural:
        raise ValueError('Presence/type alone cannot close a suspect semantic part; located geometry/relationships required')
    groups=[n for n in item.get('objects',[]) if nodes.get(n,{}).get('tag')=='grpSp']
    owned=set(groups)
    while True:
        added={n for n,e in nodes.items() if e.get('parent_name') in owned}-owned
        if not added:break
        owned |= added
    leaves={n for n in owned if nodes[n]['tag']!='grpSp' and not n.startswith('connection_port__')}
    if groups and (len(leaves)>1 and len(parts)<2 or leaves-names):
        raise ValueError('A coarse native group requires complete actual child-part observations; a whole-group or omitted-child waiver is forbidden: '+item['id']+' missing='+repr(sorted(leaves-names)))
    if o['kind']=='stochastic_texture':
        from .adaptive_detail import profile
        if profile(state,item)!='texture':raise ValueError('A structured icon cannot be waived as stochastic texture')
        if not any(c['type']=='source_patch' for c in checks):raise ValueError('Texture disposition requires its own measured source patch')
    if o['kind']=='subpixel_detail':
        w,h=item['roi'][2:]
        if min(w,h)>POLICY['subpixel_max_short_side'] or w*h>POLICY['subpixel_max_area'] or not item.get('parent_source_unit'):
            raise ValueError('Subpixel exit is restricted to a located original child with typed geometric checks')
    if o.get('context_exclusions'):
        from .adaptive_detail import source_units
        units=source_units(state)
        if len(set(o['context_exclusions']))!=len(o['context_exclusions']):raise ValueError('Distinct original context exclusions required')
        for uid in o['context_exclusions']:
            if uid==item['id'] or uid not in units or set(units[uid]['objects']) & set(item['objects']):
                raise ValueError('Exclude only independently observed foreign source objects, never the suspect object itself')
        if not o.get('context_evidence'):raise ValueError('Explain which independently bound neighbouring source objects occupy the comparison window')
    if row['resolution']=='appearance_only' and o['kind']=='clear_structure' and not o.get('context_exclusions'):
        result=report_one(o,item['metrics'])
        if not result['passed']:raise ValueError('A clear original structure with very low source agreement must enter local reconstruction')

def comparison_values(state,unit,observability,original,actual):
    """Pool a fixed SSIM map only over independently source-owned context.

    Foreign ROIs come from the original semantic registry, never from searching
    candidate pixels. Excluding the subject or most of the ROI is forbidden.
    Full raw values stay in the main scan alongside this contextual observation.
    """
    from .adaptive_detail import _box,metrics,source_units,_edges
    from scipy.ndimage import binary_dilation,distance_transform_edt
    from skimage.metrics import structural_similarity
    import numpy as np
    x,y,u,v=_box(unit['roi'],state['source_size']);a=original[y:v,x:u];b=actual[y:v,x:u]
    values=metrics(a,b)[0];excluded=observability.get('context_exclusions',[])
    if not excluded:return values
    foreign=np.zeros(a.shape[:2],bool);units=source_units(state)
    for uid in excluded:
        p,q,r,s=_box(units[uid]['roi'],state['source_size'])
        left=max(x,p);top=max(y,q);right=min(u,r);bottom=min(v,s)
        if left<right and top<bottom:foreign[top-y:bottom-y,left-x:right-x]=True
    win=min(7,min(a.shape[:2]) if min(a.shape[:2])%2 else min(a.shape[:2])-1)
    valid=~binary_dilation(foreign,iterations=max(1,win//2));support=int(valid.sum())
    if support<16 or support<valid.size*.35:raise ValueError('Source-owned comparison support is too small; refine the object and locate its own original pixels')
    if win>=3:
        _,score_map=structural_similarity(a,b,data_range=1.,channel_axis=2,win_size=win,full=True)
        values['ssim']=float(score_map[valid].mean())
    mse=float(np.mean((a[valid]-b[valid])**2));values['psnr_db']=-10*math.log10(mse) if mse>0 else None
    ea,eb=_edges(a)&valid,_edges(b)&valid
    recall=float((distance_transform_edt(~eb)[ea]<=1.5).mean()) if ea.any() else float(not eb.any())
    precision=float((distance_transform_edt(~ea)[eb]<=1.5).mean()) if eb.any() else float(not ea.any())
    values['edge_f1']=2*recall*precision/max(recall+precision,1e-12)
    values['comparison_context']={'original_unit':unit['id'],'excluded_source_units':excluded,'valid_source_pixels':support,
        'total_roi_pixels':valid.size,'method':'fixed original foreign ROI exclusion plus SSIM window halo; pool unmodified full SSIM map over valid original pixels'}
    return values

def report_one(observability,values):
    kind=observability.get('kind');checks=[]
    if kind=='clear_structure':
        ssim=values.get('ssim');psnr=values.get('psnr_db');edge=values.get('edge_f1')
        checks.append({'id':'clear_original_ssim_red_band','value':ssim,'minimum':POLICY['clear_ssim_red_below'],
                       'passed':ssim is None or ssim>=POLICY['clear_ssim_red_below'],
                       'applicability':values.get('ssim_applicability')})
        low_psnr=psnr is not None and psnr<POLICY['clear_psnr_red_below_db']
        bad_edges=edge is not None and edge<POLICY['psnr_joint_edge_f1_below']
        checks.append({'id':'clear_original_psnr_and_structural_edge_red_band','psnr_db':psnr,'edge_f1':edge,
                       'passed':not(low_psnr and bad_edges)})
    else:checks.append({'id':'declared_source_recoverability','kind':kind,'passed':kind in KINDS-{'unresolved'}})
    return {'passed':bool(checks) and all(c['passed'] for c in checks),'kind':kind,'checks':checks,'policy':POLICY,
            'route':'LOCAL_SOURCE_RECONSTRUCTION_REQUIRED' if not all(c['passed'] for c in checks) else 'TYPED_SOURCE_PART_CHECKS_STILL_REQUIRED'}
