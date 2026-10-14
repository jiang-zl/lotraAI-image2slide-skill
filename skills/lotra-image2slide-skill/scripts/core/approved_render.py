"""Actual context preservation for exact finite original-derived corrections.

A fixed ROI may include a legitimately changed neighbour. Keep its raw SSIM
and clarity observations, but establish preservation with the complete native
constructor and actual same-host pixels outside the program-owned paint frames.
No caller supplies masks, coordinates, acceptance thresholds or replacement
scores. The finite original content/layout checks remain independently required.
"""
import math
from .common import digest,safe_path,read_json

EDGE_MARGIN_SOURCE_PX=2

def source_correction_protection(task,state,candidate,approved):
    if not approved:return {'applicable':False,'passed':None}
    records=state.get('source_target_attempts',[])+state.get('source_layout_attempts',[])+state.get('source_text_attempts',[])+state.get('source_structure_attempts',[])+state.get('preview_resource_attempts',[])+state.get('connection_attempts',[])+state.get('global_layout_attempts',[])+state.get('object_rollback_attempts',[])+state.get('neighbor_repair_attempts',[])
    if not any(r.get('candidate')==candidate['pptx']['sha256'] for r in records):
        return {'applicable':False,'passed':None}
    result={'applicable':True,'passed':False,'method':'exact_complete_source_constructor_and_actual_context_pixels',
            'edge_margin_source_px':EDGE_MARGIN_SOURCE_PX,'registration':'none'}
    try:
        from .source_layout_actions import guard
        constructor=guard(task,state,candidate,approved);result['constructor']=constructor
        if not constructor['passed']:raise ValueError('The complete original-derived native constructor did not match')
        refs=[];receipts=[]
        for artifact in (approved,candidate):
            values={k:safe_path(task,artifact[k]['path']) for k in ('pptx','preview','render')}
            if any(digest(values[k])!=artifact[k]['sha256'] for k in values):raise ValueError('Protected actual render input changed')
            receipt=read_json(values['render'])
            if receipt.get('pptx_hash')!=artifact['pptx']['sha256'] or receipt.get('preview_hash')!=artifact['preview']['sha256']:
                raise ValueError('Actual context render receipt refers to other native or preview bytes')
            refs.append(values);receipts.append(receipt)
        if not receipts[0].get('backend') or receipts[0]['backend']!=receipts[1].get('backend'):
            raise ValueError('Protected context requires the same actual renderer')
        import numpy as np
        from PIL import Image
        with Image.open(refs[0]['preview']) as a,Image.open(refs[1]['preview']) as b:
            if a.size!=b.size:raise ValueError('Protected actual previews need the same complete canvas')
            before=np.asarray(a.convert('RGB'));after=np.asarray(b.convert('RGB'))
        sw,sh=state['source_size'];sx,sy=before.shape[1]/sw,before.shape[0]/sh
        if abs(sx-sy)>1e-9 or sx<1:raise ValueError('Actual context preview changed source aspect or undersampled the complete canvas')
        from .boundary_geometry import saved_nodes
        permitted=np.zeros(before.shape[:2],bool);names=constructor['objects']
        inventories=[saved_nodes(ref['pptx'],state['source_size']) for ref in refs]
        relevant=[n for n in names if any(n in inventory for inventory in inventories)]
        # Exact replay proves additions/deletions. A new descendant cannot
        # have a pre-repair frame; mask its actual frame in the corresponding
        # before/after snapshot, without inventing a historical one.
        for nodes in inventories:
            # Native groups are coordinate owners and have no own paint.
            # Expand corrected groups to their actual painted descendants;
            # a missing group frame must not mask or waive any leaf pixels.
            owned=set(relevant)
            while True:
                children={n for n,e in nodes.items() if e.get('parent_name') in owned}-owned
                if not children:break
                owned|=children
            for name in owned:
                if name not in nodes:continue
                if nodes[name]['tag']=='grpSp':continue
                if nodes[name].get('frame') is None:raise ValueError('Finite correction has no saved native paint frame')
                x,y,w,h=nodes[name]['frame'];margin=EDGE_MARGIN_SOURCE_PX
                left=max(0,math.floor((x-margin)*sx));top=max(0,math.floor((y-margin)*sy))
                right=min(before.shape[1],math.ceil((x+w+margin)*sx));bottom=min(before.shape[0],math.ceil((y+h+margin)*sy))
                permitted[top:bottom,left:right]=True
        # Source repairs can follow an earlier connector transaction. The
        # composed constructor still owns those arrowheads, whose painted
        # extent is larger than a line's coordinate frame.
        arrow_owned=any(name in nodes and nodes[name]['node'].find('.//a:'+end,__import__(__package__+'.mathml',fromlist=['NS']).NS) is not None
                        for nodes in inventories for name in names for end in ('headEnd','tailEnd'))
        if arrow_owned:
            from .owned_paint import mask
            paint,paint_receipt=mask(task,state,candidate,approved,constructor,before.shape[:2])
            permitted|=paint;result['actual_owner_paint']=paint_receipt
        changed=np.any(before!=after,axis=2);outside=int(np.count_nonzero(changed&~permitted))
        result.update(passed=outside==0,backend=receipts[0]['backend'],native_objects=names,
            changed_render_pixels=int(changed.sum()),changed_pixels_outside_program_owned_frames=outside,
            approved_preview_hash=approved['preview']['sha256'],preview_hash=candidate['preview']['sha256'],
            scope='Only the exact finite original-derived content/layout constructor may change native bytes. Actual pixels outside its before/after saved owner frames plus the fixed edge margin must remain identical. Raw fixed-ROI appearance metrics are retained, including changed neighbour context.')
    except (ValueError,KeyError,TypeError,FileNotFoundError) as error:result['reason']=str(error)
    return result
