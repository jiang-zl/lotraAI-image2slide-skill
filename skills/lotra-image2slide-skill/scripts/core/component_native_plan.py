"""Shared preflight and typed native plan for image source decisions and icon repairs."""
import copy
from .component_fields import differences, native_fields


def prepare(task, state, before, proposed, grants, rebuild_owners=()):
    from .scene import validate
    from .component_revision import guard_user_locks
    from .native_ownership import expanded
    from .native_commit import NATIVE_LEAF_FIELDS, _table_cell_field
    from .tables import normalize_scene
    before=normalize_scene(before);scene=normalize_scene(proposed)
    validate(scene,task)
    if any(before.get(k)!=scene.get(k) for k in set(before)|set(scene)
           if k not in ('objects','relations','font_plan')):
        raise ValueError('Local native plan cannot change the original canvas or global source facts')
    if scene['source']['sha256']!=state['source']['sha256']:
        raise ValueError('Native plan belongs to another original')
    guard_user_locks(task,state,scene)
    old={n['id']:n for n in before['objects']};new={n['id']:n for n in scene['objects']}
    allowed={};patches=[]
    for owner in sorted(set(old)|set(new)):
        changes=list(differences(old.get(owner),new.get(owner),before_exists=owner in old,after_exists=owner in new))
        for patch in changes:
            if not any(g['owner']==owner and patch['field'][:len(g['field'])]==g['field'] for g in grants):
                raise ValueError('Native plan escaped its approved fields: '+owner+' '+repr(patch['field']))
        if changes:
            fields=native_fields(old.get(owner),new.get(owner),changes,
                                any(g['owner']==owner and not g['field'] for g in grants))
            if fields:allowed[owner]=fields
            patches.extend(dict(p,owner=owner) for p in changes)
    for owner in rebuild_owners:
        if owner not in new or not any(g['owner']==owner and not g['field'] for g in grants):
            raise ValueError('Native reconstruction requires a whole-owner grant')
        allowed[owner]=['replace_component']
    old_native=expanded(before,task);new_native=expanded(scene,task)
    from . import component_workflow as c
    _,ledger=c._load(task,state)
    for owner,fields in list(allowed.items()):
        if fields not in (['replace_component'],['remove'],['add']):continue
        members={owner}
        while True:
            more=members|{key for mapping in (old_native,new_native)
                          for key,parent in mapping.items() if parent in members}
            if more==members:break
            members=more
        for child in members-{owner}:
            generated=child not in old and child not in new
            if not generated and not any(g['owner']==child and not g['field'] for g in grants):
                raise ValueError('Atomic subtree operation needs every semantic descendant grant')
            if any(lock['owner']==child for lock in ledger.get('orphan_user_locks',[])):
                raise ValueError('USER_LOCK_CONFLICT: retained native descendant')
            allowed[child]=['remove'] if child not in new_native else ['add'] if child not in old_native else ['replace_component']
    special={'add','remove','replace_component','reparent','paint_order','photo_resource'}
    for fields in allowed.values():
        for field in fields:
            if field not in special and field not in NATIVE_LEAF_FIELDS and _table_cell_field(field) is None:
                raise ValueError('Unsupported typed native field: '+field)
    return scene,allowed,patches
