"""Fixed-domain measurements; vector-valued evidence, never an inferred PASS.

Reference ROIs, alpha composition, masks, background and edge tolerances belong
to a frozen evaluation plan. Candidate-dependent registration/masking is absent.
"""
import math
import numpy as np
from scipy import ndimage as ndi
from skimage.color import rgb2lab, deltaE_ciede2000
from skimage.metrics import structural_similarity
from .common import digest, identity, read_json, safe_path, write_json
from .metrics import iou, cer

VERSION = 'typed-measurements-1.0.0'
IMAGE_IDS = {'mask_iou','boundary_f1','chamfer','hausdorff','color','ssim','psnr','regional_residual','texture'}


def rgb(image, background):
    from PIL import Image
    if image.mode in ('RGBA','LA') or 'transparency' in image.info:
        surface=Image.new('RGBA',image.size,tuple(background)+(255,))
        surface.alpha_composite(image.convert('RGBA'));image=surface.convert('RGB')
    return np.asarray(image.convert('RGB'),dtype=np.float64)/255


def edge_map(data, threshold):
    # Keep all channels: equally bright differently colored edges still matter.
    magnitude=np.sqrt(sum(ndi.sobel(data[...,c],axis=a,mode='nearest')**2
                          for c in range(3) for a in (0,1))) / 8
    return magnitude>=threshold


def contour(mask):
    return mask & ~ndi.binary_erosion(mask,border_value=0)


def boundary(a,b,tolerance):
    na,nb=int(a.sum()),int(b.sum())
    if not na or not nb:
        return {'precision':None if not nb else 0.,'recall':None if not na else 0.,
                'f1':0. if na!=nb else None,'chamfer_px':None,'hausdorff_px':None,
                'hd95_px':None,'reference_points':na,'candidate_points':nb}
    ba=ndi.distance_transform_edt(~a)[b];ab=ndi.distance_transform_edt(~b)[a]
    p=float(np.mean(ba<=tolerance));r=float(np.mean(ab<=tolerance))
    return {'precision':p,'recall':r,'f1':2*p*r/(p+r) if p+r else 0.,
            'chamfer_px':float((ab.mean()+ba.mean())/2),
            'hausdorff_px':float(max(ab.max(),ba.max())),
            'hd95_px':float(max(np.percentile(ab,95),np.percentile(ba,95))),
            'reference_points':na,'candidate_points':nb}


def _stats(values):
    if not values.size:return {'mean':None,'p95':None,'max':None}
    return {'mean':float(values.mean()),'p95':float(np.percentile(values,95)),'max':float(values.max())}


def ink_box(mask):
    yy,xx=np.where(mask)
    if not len(xx):return None
    return [int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)]


def color_histogram(samples,bins,mode='hard'):
    """Fixed RGB distribution; linear bin membership avoids boundary jumps.

    Bin count, membership rule and source domain are frozen before a draw.
    This is not per-candidate colour matching or image registration.
    """
    if mode=='hard':return np.histogramdd(samples,bins=bins,range=[(0,1)]*3)[0]
    if mode!='trilinear':raise ValueError('Unknown fixed colour histogram membership')
    positions=np.clip(np.asarray(samples)*bins-.5,0,bins-1)
    lower=np.floor(positions).astype(int);upper=np.minimum(lower+1,bins-1)
    fraction=positions-lower;result=np.zeros(bins**3,float)
    for rx in (0,1):
        for gy in (0,1):
            for bz in (0,1):
                choices=(rx,gy,bz)
                coords=np.column_stack([upper[:,i] if choice else lower[:,i] for i,choice in enumerate(choices)])
                weights=np.prod(np.column_stack([fraction[:,i] if choice else 1-fraction[:,i] for i,choice in enumerate(choices)]),axis=1)
                ids=coords[:,0]*bins*bins+coords[:,1]*bins+coords[:,2]
                result+=np.bincount(ids,weights=weights,minlength=bins**3)
    return result.reshape((bins,bins,bins))


def image_measure(reference,candidate,protocol,reference_mask=None,evaluation_mask=None,candidate_mask=None):
    if reference.size!=candidate.size:raise ValueError('Fixed-domain images must have equal dimensions')
    bg=protocol['background_rgb'];a,b=rgb(reference,bg),rgb(candidate,bg)
    threshold=protocol['foreground_distance_rgb'];back=np.asarray(bg)/255
    def foreground(data):
        selector=protocol.get('foreground_selector')
        if selector:
            if selector.get('mode')=='neutral_dark':
                mask=(data.mean(2)*255<selector['max_mean_rgb_255']) & ((data.max(2)-data.min(2))*255<selector['max_chroma_rgb_255'])
            else:
                colors=np.asarray(selector['colors_rgb'])/255
                foreground_distance=np.min(np.linalg.norm(data[...,None,:]-colors,axis=3),axis=2)
                mask=foreground_distance<=selector['distance_rgb_255']/255
                backgrounds=selector.get('background_colors_rgb')
                if backgrounds is not None:
                    backgrounds=np.asarray(backgrounds,dtype=float)
                    margin=float(selector.get('foreground_margin_rgb_255',0))
                    if (backgrounds.ndim!=2 or backgrounds.shape[1]!=3 or not len(backgrounds)
                            or not np.isfinite(backgrounds).all() or np.any((backgrounds<0)|(backgrounds>255))
                            or not np.isfinite(margin) or not 0<=margin<=32):
                        raise ValueError('Contrastive foreground uses declared source-background colours and a bounded margin')
                    background_distance=np.min(np.linalg.norm(data[...,None,:]-backgrounds/255,axis=3),axis=2)
                    mask &= foreground_distance+margin/255<background_distance
        else:mask=np.linalg.norm(data-back,axis=2)>=threshold
        if protocol.get('component_seed'):
            sx,sy=protocol['component_seed'];labels,_=ndi.label(mask);label=labels[sy,sx]
            mask=labels==label if label else np.zeros(mask.shape,bool)
        return mask
    am,bm=foreground(a),foreground(b)
    if candidate_mask is not None:
        owned=np.asarray(candidate_mask,dtype=bool)
        if owned.shape!=b.shape[:2]:raise ValueError('Saved native glyph domain dimensions changed')
        bm &= owned
    if reference_mask is not None:
        am=np.asarray(reference_mask,dtype=bool)
        if am.shape!=a.shape[:2]:raise ValueError('Frozen mask dimensions changed')
    domain=np.ones(a.shape[:2],dtype=bool) if evaluation_mask is None else np.asarray(evaluation_mask,dtype=bool)
    if domain.shape!=a.shape[:2] or not domain.any():raise ValueError('Empty or mismatched evaluation domain')
    contour_domain=ndi.binary_erosion(domain) if evaluation_mask is not None else domain
    full_edge_domain=ndi.binary_erosion(domain,structure=np.ones((3,3),dtype=bool)) if evaluation_mask is not None else domain
    support=protocol.get('edge_support_neighborhood','legacy_cross')
    if support not in ('legacy_cross','sobel_3x3'):raise ValueError('Declare the source edge support neighborhood')
    edge_domain=full_edge_domain if support=='sobel_3x3' else contour_domain
    # Mask ownership before contour extraction. Excluded neighbours cannot
    # create/suppress an owner's boundary; erode the domain to discard the
    # artificial cut itself, just as for internal-edge measurements.
    outline=boundary(contour(am & domain)&contour_domain,
                     contour(bm & domain)&contour_domain,protocol['boundary_tolerance_px'])
    if protocol.get('edge_scope')=='owned_foreground':
        ae=edge_map(a,protocol['edge_threshold'])&edge_domain&ndi.binary_dilation(am,iterations=2)
        be=edge_map(b,protocol['edge_threshold'])&edge_domain&ndi.binary_dilation(bm,iterations=2)
    else:
        ae=edge_map(a,protocol['edge_threshold'])&edge_domain;be=edge_map(b,protocol['edge_threshold'])&edge_domain
    internal=boundary(ae,be,protocol['boundary_tolerance_px'])
    internal.update(support_neighborhood=support,owned_full_kernel_centers=int(full_edge_domain.sum()),
        source_points_with_excluded_kernel_context=int((ae&~full_edge_domain).sum()),
        candidate_points_with_excluded_kernel_context=int((be&~full_edge_domain).sum()))
    if support=='legacy_cross' and internal['source_points_with_excluded_kernel_context']:
        internal['measurement_warning']='Sobel3x3 reads excluded source context at some counted centres; correct the source domain/protocol before attributing that residual to this layer.'
    elif not internal['reference_points']:
        internal['missing_source_feature_reason']='No observed internal source edge has a complete declared kernel neighbourhood; retain unmeasured, never an automatic perfect match.'
    am,bm=am&domain,bm&domain
    de=deltaE_ciede2000(rgb2lab(a),rgb2lab(b))
    mse=float(np.mean(((a-b)**2)[domain]));mae=np.mean(np.abs(a-b),axis=2)*255
    win=protocol['ssim_window'];small=min(a.shape[:2])<win
    ssim_reason='ROI smaller than fixed window' if small else None
    ssim=None
    if not small:
        score,score_map=structural_similarity(a,b,channel_axis=2,data_range=1.,win_size=win,
                         gaussian_weights=False,use_sample_covariance=False,full=True)
        if evaluation_mask is None:ssim=float(score)
        else:
            centers=ndi.binary_erosion(domain,structure=np.ones((win,win),dtype=bool))
            if centers.any():ssim=float(score_map.mean(axis=2)[centers].mean())
            else:ssim_reason='Evaluation mask has no complete SSIM window'
    result={'mask_iou':iou(am,bm),'boundary':outline,'internal_edges':internal,
            'foreground_match':boundary(am,bm,protocol['boundary_tolerance_px']),
            'color_delta_e_2000':_stats(de[domain]),'color_delta_e_reference_foreground':_stats(de[am]),
            'regional_residual_rgb_255':_stats(mae[domain]),'ssim':ssim,
            'psnr_db':None if mse==0 else float(10*math.log10(1/mse)),
            'psnr_special_value':'positive_infinity' if mse==0 else None,'mse_rgb_01':mse,
            'reference_ink_bbox':ink_box(am),'candidate_ink_bbox':ink_box(bm),
            'reference_foreground_pixels':int(am.sum()),'candidate_foreground_pixels':int(bm.sum()),
            'missing_foreground_pixels':int((am&~bm).sum()),'extra_foreground_pixels':int((bm&~am).sum()),
            'ink_bbox_error_px':None,'ssim_missing_reason':ssim_reason,'evaluation_pixels':int(domain.sum()),
            'evaluation_scope':'fixed_mask' if evaluation_mask is not None else 'whole_roi'}
    if result['reference_ink_bbox'] and result['candidate_ink_bbox']:
        result['ink_bbox_error_px']=[abs(x-y) for x,y in zip(result['reference_ink_bbox'],result['candidate_ink_bbox'])]
    # Noncompensating presence/weight/topology evidence for the declared part.
    # Threshold and domain are fixed from source before candidates are ranked.
    ac,_=ndi.label(am);bc,_=ndi.label(bm)
    ah=ndi.binary_fill_holes(am)&~am;bh=ndi.binary_fill_holes(bm)&~bm
    _,nah=ndi.label(ah);_,nbh=ndi.label(bh)
    if protocol.get('foreground_mass_scope')=='foreground':
        aa=float(np.linalg.norm(a-back,axis=2)[am].sum())
        bb=float(np.linalg.norm(b-back,axis=2)[bm].sum())
    else:
        aa=float(np.linalg.norm(a-back,axis=2)[domain].sum())
        bb=float(np.linalg.norm(b-back,axis=2)[domain].sum())
    result['foreground_mass_ratio']=bb/aa if aa else None
    result['foreground_area_ratio']=float(bm.sum()/am.sum()) if am.any() else None
    result['topology']={'reference_components':int(ac.max()),'candidate_components':int(bc.max()),
        'reference_holes':nah,'candidate_holes':nbh,
        'component_count_error':int(abs(ac.max()-bc.max())),
        'hole_count_error':int(abs(nah-nbh))}
    # Style scope is fixed by source ownership, not changed per candidate.
    histogram_domain=domain & am if protocol.get('histogram_scope')=='reference_foreground' else domain
    # Raw color histogram total variation, with a predeclared bin count.
    bins=protocol['histogram_bins'];mode=protocol.get('histogram_mode','hard')
    ha=color_histogram(a[histogram_domain],bins,mode);hb=color_histogram(b[histogram_domain],bins,mode)
    result['texture_color_histogram_tv']=float(np.abs(ha/ha.sum()-hb/hb.sum()).sum()/2) if ha.sum() and hb.sum() else None
    result['color_histogram_membership']=mode
    if mode!='hard':
        ra=color_histogram(a[histogram_domain],bins);rb=color_histogram(b[histogram_domain],bins)
        result['raw_color_histogram_tv']=float(np.abs(ra/ra.sum()-rb/rb.sum()).sum()/2) if ra.sum() and rb.sum() else None
    # Optional fixed low-contrast protocol: never discard a faint background
    # through the normal foreground threshold, or choose a threshold per candidate.
    if 'low_contrast_edge_threshold' in protocol:
        low = protocol['low_contrast_edge_threshold']
        if not isinstance(low, (int, float)) or not 0 < low < 1:
            raise ValueError('Invalid fixed low-contrast edge threshold')
        result['low_contrast_edges'] = boundary(edge_map(a, low)&edge_domain, edge_map(b, low)&edge_domain, protocol['boundary_tolerance_px'])
        def relative_luminance(data):
            linear=np.where(data<=.04045,data/12.92,((data+.055)/1.055)**2.4)
            return (linear@np.array([.2126,.7152,.0722]))[domain]
        la, lb = relative_luminance(a),relative_luminance(b)
        result['luminance_definition']='linear sRGB relative luminance (D65); excludes pixels outside evaluation domain'
        result['luminance_std_reference'] = float(la.std())
        result['luminance_std_candidate'] = float(lb.std())
        result['luminance_std_abs_error'] = float(abs(la.std()-lb.std()))
    return result


def landmarks(reference,candidate):
    missing=sorted(set(reference)-set(candidate));extra=sorted(set(candidate)-set(reference));errors={}
    for k in sorted(set(reference)&set(candidate)):
        a,b=np.asarray(reference[k],float),np.asarray(candidate[k],float)
        if a.shape!=(2,) or b.shape!=(2,) or not np.isfinite([*a,*b]).all():raise ValueError('Invalid landmark')
        errors[k]=float(np.linalg.norm(a-b))
    values=np.asarray(list(errors.values()))
    return {'errors_px':errors,'mean_px':float(values.mean()) if len(values) and not missing else None,
            'max_px':float(values.max()) if len(values) and not missing else None,'missing':missing,'extra':extra}


def inventory(reference,candidate,key=lambda value: value):
    # Multisets: repeated labels/parts must not collapse into a single set entry.
    from collections import Counter
    a,b=Counter(map(key,reference)),Counter(map(key,candidate));tp=sum((a&b).values())
    p=tp/sum(b.values()) if b else None;r=tp/sum(a.values()) if a else None
    return {'tp':tp,'fp':sum((b-a).values()),'fn':sum((a-b).values()),
            'precision':p,'recall':r,'f1':2*p*r/(p+r) if p is not None and r is not None and p+r else (0. if p is not None and r is not None else None),
            'missing':list((a-b).elements()),'extra':list((b-a).elements())}


def dominance(before,after,directions):
    """No missing-value renormalization or uncalibrated weighted score."""
    if not directions:return {'result':'unmeasured','reason':'No fixed objective vector'}
    improved=[];regressed=[];missing=[]
    for key,direction in directions.items():
        x,y=before.get(key),after.get(key)
        if x is None or y is None or not np.isfinite([x,y]).all():missing.append(key);continue
        if direction not in ('min','max'):raise ValueError('Unknown metric direction')
        delta=(y-x)*(1 if direction=='min' else -1)
        if delta>0:regressed.append(key)
        elif delta<0:improved.append(key)
    verdict='unmeasured' if missing else 'harmful' if regressed and not improved else 'tradeoff' if regressed else 'helped' if improved else 'neutral'
    return {'result':verdict,'improved':improved,'regressed':regressed,'missing':missing}


def scalar_vector(measured):
    return {'color':measured['color_delta_e_2000']['mean'],
            'residual':measured['regional_residual_rgb_255']['mean'],
            'boundary_f1':measured['boundary']['f1'],'internal_edge_f1':measured['internal_edges']['f1'],
            'chamfer':measured['boundary']['chamfer_px'],'mask_iou':measured['mask_iou'],
            'ink_bbox':max(measured['ink_bbox_error_px']) if measured['ink_bbox_error_px'] is not None else None}


def evaluate_images(plan,base,preview,output,pptx=None,render_receipt=None):
    from PIL import Image
    if plan.get('version')!='typed-plan-1':raise ValueError('Unsupported evaluation plan')
    source=safe_path(base,plan['source']['path'])
    if digest(source)!=plan['source']['sha256']:raise ValueError('Frozen reference changed')
    ref=Image.open(source);actual=Image.open(preview)
    if ref.size!=actual.size or list(ref.size)!=plan['canvas']:raise ValueError('No candidate-dependent resize/registration')
    if pptx is not None:
        rr=read_json(render_receipt)
        if rr.get('pptx_hash')!=digest(pptx) or rr.get('preview_hash')!=digest(preview):raise ValueError('Stale actual render')
    results={}
    for target in plan['targets']:
        box=target['roi'];x,y,w,h=box
        if not all(isinstance(v,int) for v in box) or not 0<=x<x+w<=ref.width or not 0<=y<y+h<=ref.height:raise ValueError('Invalid fixed ROI')
        mask=None
        if target.get('mask'):
            f=safe_path(base,target['mask']['path'])
            if digest(f)!=target['mask']['sha256']:raise ValueError('Frozen reference mask changed')
            mask=np.asarray(Image.open(f).convert('L'))>0
        domain=None
        if target.get('evaluation_mask'):
            f=safe_path(base,target['evaluation_mask']['path'])
            if digest(f)!=target['evaluation_mask']['sha256']:raise ValueError('Frozen evaluation mask changed')
            domain=np.asarray(Image.open(f).convert('L'))>0
        result=image_measure(ref.crop((x,y,x+w,y+h)),actual.crop((x,y,x+w,y+h)),target['protocol'],mask,domain)
        protected={}
        for region in target.get('protected_regions',[]):
            a,b,c,d=region['roi']
            if not x<=a<a+c<=x+w or not y<=b<b+d<=y+h:raise ValueError('Protected region outside target')
            protected[region['id']]=image_measure(ref.crop((a,b,a+c,b+d)),actual.crop((a,b,a+c,b+d)),target['protocol'])
        results[target['id']]={'measurements':result,'vector':scalar_vector(result),'protected_regions':protected,
                               'status':'UNVERIFIED','reason':'Raw measurements; semantic/native requirements and calibration remain separate'}
    report={'metric_version':VERSION,'plan_hash':identity(plan),'source_hash':digest(source),'preview_hash':digest(preview),
            'pptx_hash':digest(pptx) if pptx else None,'render_receipt_hash':digest(render_receipt) if render_receipt else None,
            'targets':results,'status':'UNVERIFIED','scope':'fixed-domain actual pixels, not semantic/native acceptance'}
    from .session import implementation_identity
    report['implementation']=implementation_identity()
    write_json(output,report);return report


DEFAULT_PROTOCOL={'background_rgb':[255,255,255],'foreground_distance_rgb':0.08,
                  'edge_threshold':0.04,'boundary_tolerance_px':1.5,'ssim_window':7,'histogram_bins':8,
                  'scope':'explicit diagnostic preprocessing defaults; not calibrated quality thresholds'}
