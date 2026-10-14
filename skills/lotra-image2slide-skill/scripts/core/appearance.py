"""Semantic HD reconstruction policy, distinct from literal pixel recovery."""

import math
from PIL import Image
from .common import digest, read_json, safe_path

POLICIES = {'source_faithful', 'semantic_hd_replace', 'preserve_approved'}
HD_CHECKS = ('semantic_match', 'key_parts', 'view_composition', 'clarity',
             'natural_texture', 'clean_boundary', 'complete_independent_layer')


def drawing_policy(choice, source_node):
    policy = choice.get('appearance_policy', 'source_faithful')
    if policy not in POLICIES:
        raise ValueError('Unknown appearance policy')
    if policy == 'semantic_hd_replace':
        if (source_node.get('scientific_content') is True or source_node.get('role') in ('R3', 'R4') or
                choice.get('texture_role') == 'semantic_mark'):
            raise ValueError('Scientific content and semantic marks cannot be generated replacements')
        if not choice.get('semantic_constraints') or not choice.get('target_reuse_inches'):
            raise ValueError('HD reconstruction needs meaning constraints and intended reuse size')
    return {k: choice[k] for k in ('appearance_policy', 'semantic_constraints', 'target_reuse_inches') if k in choice}


def _file(base, ref):
    path = safe_path(base, ref['path'])
    if digest(path) != ref['sha256']:
        raise ValueError('HD reconstruction asset changed')
    return path


def semantic_hd_asset(content, base):
    """Accept source-semantic replacement without enforcing blurry source pixels.

    Display PPI describes the generated payload, not recovered true information.
    The host must actually observe natural clarity and whole-object semantics.
    """
    spec = content.get('reconstruction', {})
    if spec.get('appearance_policy') != 'semantic_hd_replace':
        raise ValueError('Full semantic replacement needs an explicit appearance policy')
    if spec.get('scientific_content_excluded') is not True or not spec.get('semantic_constraints'):
        raise ValueError('HD replacement must preserve known meaning and exclude scientific evidence')
    generation = spec.get('generation', {})
    if (generation.get('method') not in ('host_image_generation', 'native_redraw', 'semantic_restoration') or
            not generation.get('tool') or not generation.get('prompt')):
        raise ValueError('Record actual reconstruction tool and source-conditioned instructions')
    size = spec.get('max_reuse_inches')
    minimum = spec.get('minimum_display_ppi', 200)
    if (not isinstance(size, list) or len(size) != 2 or
            any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in size) or
            type(minimum) not in (int, float) or not math.isfinite(minimum) or minimum < 200):
        raise ValueError('HD output needs declared positive reuse dimensions and at least 200 display PPI')
    if base is None:
        return {'status': 'HD_RECONSTRUCTION_REQUIRES_ACTUAL_ASSET'}
    original = _file(base, spec['source_asset'])
    asset = _file(base, content)
    if digest(original) == digest(asset):
        raise ValueError('Low-resolution source was reused without reconstruction')
    with Image.open(asset) as image:
        ppi = [image.width/size[0], image.height/size[1]]
        if min(ppi) < minimum:
            raise ValueError('Generated payload is too small at its declared reuse size')
    review = read_json(_file(base, spec['review']))
    if (review.get('source_sha256') != digest(original) or review.get('asset_sha256') != digest(asset) or
            review.get('reviewer', {}).get('kind') not in ('host_model', 'human')):
        raise ValueError('HD judgment must bind the actual source and generated full asset')
    for key in HD_CHECKS:
        item = review.get('checks', {}).get(key, {})
        if item.get('status') != 'PASS' or not item.get('note'):
            raise ValueError('HD reconstruction still needs visual improvement: ' + key)
    return {'status': 'PASS_SEMANTIC_HD_ASSET', 'source_sha256': digest(original),
            'asset_sha256': digest(asset), 'generated_display_ppi': ppi,
            'scope': 'source-compatible inferred illustration; not recovered experimental evidence',
            'pixel_fidelity_is_advisory': True}


def semantic_raster_comparison(contract, base, native_pptx, native_receipt, raster_pptx, raster_receipt):
    """Reuse saved-owner/context primitives for a generative appearance trial."""
    from .raster_exception import _owner_records, _same_context, _rendered
    from .common import identity
    if (contract.get('scientific_content_excluded') is not True or
            contract.get('native_internal_edit_required') is not False or
            contract.get('semantic_mark') is not False):
        raise ValueError('Native science, semantics and internal editing promises remain required')
    native, native_names = _owner_records(native_pptx, contract['vector_owner_path'])
    raster, raster_names = _owner_records(raster_pptx, contract['raster_owner_path'])
    if any(native['objects'][name]['shape_type'] == 'pic' for name in native_names):
        raise ValueError('Native comparator contains a flattened picture')
    if len(raster_names) != 1 or raster['objects'][raster_names[0]]['shape_type'] != 'pic':
        raise ValueError('Generated alternative must remain one independent picture owner')
    _same_context(native, raster, contract['vector_owner_path'], contract['raster_owner_path'])
    _rendered(native_pptx, native_receipt)
    _rendered(raster_pptx, raster_receipt)
    content = contract['generated_content']
    result = semantic_hd_asset(content, base)
    if raster['objects'][raster_names[0]]['media_sha256'] != content['sha256']:
        raise ValueError('Generated comparison asset is not the actual embedded picture')
    review = read_json(_file(base, contract['comparison_review']))
    if (review.get('native_pptx_hash') != digest(native_pptx) or review.get('raster_pptx_hash') != digest(raster_pptx) or
            review.get('reviewer', {}).get('kind') not in ('host_model', 'human')):
        raise ValueError('Compare the actual saved native and generated variants')
    if any(review.get(k, {}).get('status') != 'PASS' or not review[k].get('note')
           for k in ('semantic_match', 'clear_quality_gain', 'context_preserved')):
        raise ValueError('Generated raster has no observed clear advantage')
    return {'status': 'ELIGIBLE_FOR_SEMANTIC_AND_EDITOR_REVIEW', 'appearance_policy': 'semantic_hd_replace',
            'contract_hash': identity(contract), 'hd_asset': result,
            'scope': 'same-context native-first comparison; source pixel similarity is advisory'}
