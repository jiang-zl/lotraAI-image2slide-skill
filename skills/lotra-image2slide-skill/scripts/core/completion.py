"""Amodal asset contracts, exact observed-pixel preservation and honest metrics.

The host supplies masks, category observations and completion candidates. This
module neither segments arbitrary photographs nor invents their hidden truth.
Native icons should use geometry/prototypes rather than this raster adapter.
"""
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from .common import digest, identity, safe_path, read_json, write_json

VERSION = 'amodal-completion-1.3.0'
KINDS = {'illustrative_photo', 'environment', 'native_icon', 'scientific_image'}
METHODS = {'same_source_recovery', 'semantic_donor', 'model_assisted', 'geometry', 'prototype'}
RUBRIC = ('category', 'natural_parts', 'geometry', 'view_style', 'occluder_removed')
PHOTO_RUBRIC = ('whole_subject_continuity', 'no_extra_subject')


def _resource(base, ref):
    path = safe_path(base, ref['path'])
    if digest(path) != ref['sha256']:
        raise ValueError('Completion resource changed: '+ref['path'])
    return path


def _mask(path, size):
    with Image.open(path) as im:
        if im.size != size: raise ValueError('Completion mask canvas mismatch')
        a = np.asarray(im.convert('L'))
    if not np.isin(a, [0,255]).all():
        raise ValueError('Masks must be explicitly binary; use a separate boundary mask for uncertainty')
    return a > 0


def _observed_antialias(spec, base, source, visible, amodal):
    """Only explicit, already observed outer-edge alpha may remain fractional.

    This is not an exemption for unfilled inferred pixels, holes or interior
    transparency. An opaque photograph has no reason to declare this mask.
    """
    if not spec.get('observed_antialias_mask'):return np.zeros(amodal.shape,dtype=bool)
    mask=_mask(_resource(base,spec['observed_antialias_mask']),(amodal.shape[1],amodal.shape[0]))
    boundary=amodal & ~ndi.binary_erosion(amodal,structure=np.ones((3,3),dtype=bool))
    with Image.open(source) as im:alpha=np.asarray(im.convert('RGBA'))[...,3]
    if (mask & (~visible | ~boundary | (alpha==0) | (alpha>=254))).any():
        raise ValueError('Antialias exemption must be observed fractional outer-edge alpha, never a hidden or interior hole')
    return mask


def validate(spec, base):
    if spec.get('version') != 'completion-1': raise ValueError('Unknown completion contract')
    if spec.get('kind') not in KINDS or spec.get('method') not in METHODS:
        raise ValueError('Unknown content kind or completion method')
    for key in ('owner', 'category', 'reason'):
        if not spec.get(key): raise ValueError('Missing completion context: '+key)
    source = _resource(base, spec['source'])
    with Image.open(source) as im: size = im.size
    visible = _mask(_resource(base,spec['visible_mask']),size)
    if spec.get('visibility_provenance') == 'stack_geometry':
        if not spec.get('visible_mask_freeze_receipt') or not spec.get('baseline_pptx_hash') or type(spec.get('target_shape_id')) is not int:
            raise ValueError('Stack visibility needs frozen receipt, PPT hash and picture id')
        receipt=read_json(_resource(base,spec['visible_mask_freeze_receipt']))
        if (receipt.get('schema_version')!='photo-stack-visible-mask-1'
                or receipt.get('status')!='FROZEN_BEFORE_CANDIDATE'
                or receipt.get('mask_hash')!=spec['visible_mask']['sha256']
                or receipt.get('pptx_hash')!=spec['baseline_pptx_hash']
                or receipt.get('target_id')!=spec['target_shape_id']
                or receipt.get('target_media_hash')!=spec['source']['sha256']):
            raise ValueError('Stack visible mask is not bound to source picture and baseline PPT')
    amodal = _mask(_resource(base,spec['amodal_mask']),size)
    protected = _mask(_resource(base,spec['protected_mask']),size)
    if not visible.any() or not amodal.any(): raise ValueError('Empty completion mask')
    if (visible & ~amodal).any(): raise ValueError('Visible region is outside full component')
    _observed_antialias(spec,base,source,visible,amodal)
    hidden = amodal & ~visible
    if bool(spec.get('occluder_reference')) != bool(spec.get('occluder_mask')):
        raise ValueError('Occluder diagnostic needs both an aligned reference and a located mask')
    if spec.get('occluder_reference'):
        occluder=_resource(base,spec['occluder_reference'])
        with Image.open(occluder) as im:
            if im.size!=size:raise ValueError('Aligned occluder canvas mismatch')
        covered=_mask(_resource(base,spec['occluder_mask']),size)
        if not covered.any() or (covered & ~hidden).any() or not spec.get('occluder_evidence_refs'):
            raise ValueError('Occluder mask requires independently located hidden-only evidence')
    if (hidden & protected).any(): raise ValueError('Cannot infer protected scientific pixels')
    if spec['kind'] == 'scientific_image' and hidden.any() and spec['method'] != 'same_source_recovery':
        raise ValueError('Scientific image completion requires actual same-source recovery')
    if spec['method'] == 'same_source_recovery' and not spec.get('same_source_evidence'):
        raise ValueError('Same-source recovery needs independently located source evidence')
    if spec['method'] in ('semantic_donor','model_assisted','geometry','prototype') and hidden.any():
        if spec.get('hidden_status') != 'inferred': raise ValueError('Unobserved completion must remain inferred')
    if spec['method'] == 'model_assisted' and not spec.get('tool_identity'):
        raise ValueError('Record actual tool identity, or unknown')
    if spec.get('seam_blend_pixels') is not None:
        if (spec['kind'] != 'illustrative_photo' or spec['method'] != 'semantic_donor'
                or type(spec['seam_blend_pixels']) is not int or not 1 <= spec['seam_blend_pixels'] <= 32
                or spec.get('source_hidden_is_clean') is not True or not spec.get('source_hidden_clean_evidence')):
            raise ValueError('Seam blending requires a clean original illustrative asset and located evidence')
    if not isinstance(spec.get('evidence_refs'),list) or not spec['evidence_refs']:
        raise ValueError('Completion needs located source observations')
    return source, visible, amodal, protected


def compose(spec, base, candidate_ref, output):
    """Composite a supplied full candidate ONLY into unknown pixels.

    The candidate may come from the host's image tool or a verified same-source
    asset. No generation, random texture, resizing or registration is hidden here.
    """
    source, visible, amodal, _ = validate(spec,base)
    candidate = _resource(base,candidate_ref)
    with Image.open(source) as im:
        original_mode = im.mode
        observed = np.asarray(im.convert('RGBA')).copy()
    with Image.open(candidate) as im: full = np.asarray(im.convert('RGBA')).copy()
    if full.shape != observed.shape: raise ValueError('Candidate must use the fixed component canvas')
    if spec.get('seam_blend_pixels'):
        hidden = amodal & ~visible
        distance = ndi.distance_transform_edt(~visible)
        blend = np.clip(distance / spec['seam_blend_pixels'], 0, 1)
        for channel in range(3):
            full[..., channel][hidden] = np.rint(
                observed[..., channel][hidden] * (1 - blend[hidden])
                + full[..., channel][hidden] * blend[hidden]).astype(np.uint8)
    full[visible] = observed[visible]
    full[~amodal,3] = 0
    output = Path(output)
    if output.exists(): raise FileExistsError(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    # An opaque RGB thumbnail must remain an opaque RGB PNG. Converting its
    # storage to RGBA can change interpolation in slide renderers even when
    # every exposed source RGB pixel is numerically identical.
    if original_mode == 'RGB' and np.all(full[..., 3] == 255):
        Image.fromarray(full[..., :3]).save(output)
    else:
        Image.fromarray(full).save(output)
    receipt = {'version':VERSION,'owner':spec['owner'],'contract_hash':identity(spec),
               'source_hash':digest(source),'candidate_hash':digest(candidate),'output_hash':digest(output),
               'inferred_pixels':int((amodal & ~visible).sum()),'visible_pixels':int(visible.sum()),
               'method':spec['method'],'hidden_status':spec.get('hidden_status'),
               'status':'COMPOSED_REQUIRES_COMPLETENESS_AND_SEMANTIC_REVIEW'}
    write_json(output.with_suffix('.completion.json'),receipt)
    return receipt


def measure(spec, base, completed, semantic_review=None, ground_truth=None):
    source, visible, amodal, _ = validate(spec,base)
    with Image.open(source) as im: a = np.asarray(im.convert('RGBA')).astype(float)
    with Image.open(completed) as im: b = np.asarray(im.convert('RGBA')).astype(float)
    if a.shape != b.shape: raise ValueError('Completion output canvas changed')
    hidden = amodal & ~visible
    diff = np.abs(a-b)
    alpha = b[...,3] > 0
    # Inferred support must be opaque. Fractional observed outer-edge pixels
    # are allowed only by a separately frozen, validated antialias mask.
    antialias=_observed_antialias(spec,base,source,visible,amodal)
    holes = amodal & ~antialias & (b[...,3] < 254)
    boundary = hidden & ndi.binary_dilation(visible)
    # Nearest observed pixel on the seam; a diagnostic, not a realism score.
    _, nearest = ndi.distance_transform_edt(~visible,return_indices=True)
    seam = np.abs(b[...,:3]-b[nearest[0],nearest[1],:3]).mean(axis=2)[boundary]
    checks = {
        'observed_pixels_unchanged':bool((diff[visible] == 0).all()),
        'complete_alpha_support':bool(not holes.any()),
        'no_external_leakage':bool(not (alpha & ~amodal).any()),
    }
    values = {'observed_antialias_pixels':int(antialias.sum()),
              'visible_mae_rgba_255':float(diff[visible].mean()),
              'visible_max_channel_error_255':float(diff[visible].max()),
              'visible_changed_fraction':float((diff[visible].max(axis=1)>0).mean()),
              'amodal_missing_fraction':float(holes.sum()/amodal.sum()),
              'hidden_pixel_count':int(hidden.sum()),
              'seam_rgb_difference_mean_255':float(seam.mean()) if seam.size else None,
              'seam_pixel_count':int(seam.size),
              'hidden_ground_truth_mae_rgb_255':None,
              'hidden_ground_truth_iou':None}
    if spec.get('occluder_reference'):
        with Image.open(_resource(base,spec['occluder_reference'])) as im:
            occluder=np.asarray(im.convert('RGB')).astype(float)
        covered=_mask(_resource(base,spec['occluder_mask']),(a.shape[1],a.shape[0]))
        residual=np.abs(b[...,:3]-occluder).mean(axis=2)[covered]
        values.update(occluder_diagnostic_pixels=int(covered.sum()),
                      occluder_rgb_mae_255=float(residual.mean()),
                      occluder_match_fraction_l1_le_2=float((residual<=2).mean()))
    else:
        values.update(occluder_diagnostic_pixels=None,occluder_rgb_mae_255=None,occluder_match_fraction_l1_le_2=None)
    truth_hash = None
    if ground_truth:
        truth = _resource(base,ground_truth)
        with Image.open(truth) as im: gt=np.asarray(im.convert('RGBA')).astype(float)
        if gt.shape != b.shape: raise ValueError('Ground truth canvas mismatch')
        truth_hash=digest(truth)
        if hidden.any(): values['hidden_ground_truth_mae_rgb_255']=float(np.abs(gt[...,:3]-b[...,:3])[hidden].mean())
        gt_hidden=(gt[...,3]>0)&~visible;pred_hidden=alpha&~visible
        union=(gt_hidden|pred_hidden).sum()
        values['hidden_ground_truth_iou']=float((gt_hidden&pred_hidden).sum()/union) if union else None
    semantic_status='UNVERIFIED';review_hash=None
    if semantic_review:
        review=read_json(semantic_review)
        if (review.get('output_hash') != digest(completed) or
            review.get('contract_hash') != identity(spec)):
            raise ValueError('Semantic review is for a different completion')
        if review.get('reviewer',{}).get('kind') not in ('human','host_model'):
            raise ValueError('Semantic plausibility requires a real observer')
        results=[]
        required_checks = RUBRIC + (PHOTO_RUBRIC if spec['kind'] == 'illustrative_photo' else ())
        for key in required_checks:
            check=review.get('checks',{}).get(key,{})
            if check.get('status') not in ('PASS','FAIL','UNVERIFIED') or not check.get('evidence'):
                raise ValueError('Incomplete semantic rubric: '+key)
            results.append(check['status'])
        semantic_status='FAIL' if 'FAIL' in results else 'UNVERIFIED' if 'UNVERIFIED' in results else 'PASS'
        review_hash=digest(semantic_review)
    hard='PASS' if all(checks.values()) else 'FAIL'
    return {'version':VERSION,'contract_hash':identity(spec),'output_hash':digest(completed),
            'checks':checks,'measurements':values,'hard_status':hard,'semantic_status':semantic_status,
            'semantic_review_hash':review_hash,'ground_truth_hash':truth_hash,
            'status':'FAIL' if hard=='FAIL' or semantic_status=='FAIL' else
                     'PASS_COMPONENT_COMPLETION' if semantic_status=='PASS' else 'UNVERIFIED',
            'scope':'Asset integrity and observed plausibility; PPT reuse and page composition remain separate'}
