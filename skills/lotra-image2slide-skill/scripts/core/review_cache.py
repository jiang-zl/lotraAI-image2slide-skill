"""Reuse located visual observations only when their evidence is byte-identical.

This never reuses native-operation receipts, quality gates, or numeric scores.
Changed crops, object versions, topology, or rubric require another review.
"""
import copy
from .common import read_json, identity
from .review import import_review


def transfer(old_directory, old_observations, new_directory, fresh_binding):
    old = read_json(old_directory / 'review-manifest.json')
    new = read_json(new_directory / 'review-manifest.json')
    # Validate the historical evidence as historical, then the fresh crop plan.
    import_review(old, old_observations, current_binding=old['binding'], review_directory=old_directory)
    empty = {'binding': fresh_binding, 'manifest_hash': new['manifest_hash'],
             'evaluator': old_observations['evaluator'], 'observations': []}
    import_review(new, empty, current_binding=fresh_binding, review_directory=new_directory)
    old_targets = {t['id']: t for t in old['targets']}
    new_targets = {t['id']: t for t in new['targets']}
    invariant = all(old['binding'][k] == new['binding'][k]
                    for k in ('source_hash', 'evidence_hash', 'profile_hash', 'checker_version'))
    invariant = invariant and old['rubric'] == new['rubric']
    accepted = []
    for observation in old_observations['observations']:
        a, b = old_targets[observation['target_id']], new_targets.get(observation['target_id'])
        if not invariant or b is None or observation.get('level') is None:
            continue
        if any(a.get(k) != b.get(k) for k in ('kind', 'object_ids', 'core', 'context', 'required_criteria', 'object_measurements')):
            continue
        ids = a.get('object_ids', [])
        if any(i not in old['binding']['component_versions'] or i not in new['binding']['component_versions']
               or old['binding']['component_versions'][i] != new['binding']['component_versions'][i] for i in ids):
            continue
        if a['kind'] in ('corridor', 'global') and old['binding']['dependency_hash'] != new['binding']['dependency_hash']:
            continue
        if any(a['crops'][area][role]['sha256'] != b['crops'][area][role]['sha256']
               for area in ('core', 'context') for role in ('reference', 'candidate')):
            continue
        item = copy.deepcopy(observation)
        for index, ref in enumerate(item['evidence_refs']):
            area, role = next((area, role) for area in ('core', 'context') for role in ('reference', 'candidate')
                              if a['crops'][area][role] == ref)
            item['evidence_refs'][index] = b['crops'][area][role]
        item['reuse_evidence'] = {'historical_manifest_hash': old['manifest_hash'],
                                  'historical_review_hash': identity(old_observations),
                                  'rule': 'identical source, ROI, crop bytes, rubric, object versions and local measurements'}
        accepted.append(item)
    result = dict(empty, observations=accepted, scope='unchanged located visual observations only')
    import_review(new, result, current_binding=fresh_binding, review_directory=new_directory)
    return result
