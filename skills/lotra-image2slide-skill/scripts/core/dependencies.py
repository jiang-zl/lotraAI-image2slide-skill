"""Facet- and region-specific read dependencies and post-change rechecks.

Ancestors receive composition checks without broadcasting to every child or
traversing the scientific graph's entire connected component.
"""
from collections import defaultdict
from .common import identity

FACET={'style':'style','bbox':'placement','parent':'structure','render_type':'structure',
       'content':'content','semantic_type':'content','z_order':'placement','component':'structure'}
ALL=('content','structure','style','placement')


def overlap(a,b):
    return min(a[0]+a[2],b[0]+b[2])>=max(a[0],b[0]) and min(a[1]+a[3],b[1]+b[3])>=max(a[1],b[1])


def expanded(box,halo):return [box[0]-halo,box[1]-halo,box[2]+2*halo,box[3]+2*halo]


def plan(scene,operations,new_scene=None):
    old={o['id']:o for o in scene['objects']};new={o['id']:o for o in (new_scene or scene)['objects']}
    reads=defaultdict(set);checks=defaultdict(set);regions=[];reasons=[];targets=set();relevant_relations={}
    geometry=set();topology=set();font=set()
    for op in operations:
        id=op['object_id'];targets.add(id);o=old[id];field=op['field'];facet=FACET[field]
        reads[id].update(ALL);checks[id].update(('structure','local_metrics'))
        if field=='style':
            changed={k for k in set(o['style'])|set(op['value']) if o['style'].get(k)!=op['value'].get(k)}
            if changed & {'font','font_size','bold','italic','char_spacing_pt','line_spacing','baseline_offset_pt'}:font.add(id)
            checks[id].update({'text_layout','regional_residual'} if id in font else {'color','stroke','regional_residual'})
        elif field in ('bbox','parent','z_order'):
            geometry.add(id);checks[id].update(('layout','occlusion','continuity'))
        elif field in ('content','render_type','semantic_type'):
            topology.add(id);checks[id].update(('semantic','parts','relations','native'))
        for objects,label in ((old,'old'),(new,'new')):
            value=objects[id]['bbox']
            if field=='bbox' and label=='new':value=op['value']
            halo=max(2.,float(objects[id]['style'].get('line_width',1.5))*2)
            if id in font:halo=max(halo,float(objects[id]['style'].get('font_size',16))*2)
            regions.append({'object_id':id,'phase':label,'bbox':expanded(value,halo),
                            'requires_actual_ink_expansion':id in font})
            parent=objects[id].get('parent');seen=set()
            while parent and parent not in seen:
                seen.add(parent);reads[parent].update(('structure','placement'));checks[parent].add('parent_composition')
                parent=objects[parent].get('parent')
    # Read only directly interacting geometry. Inclusion never starts another
    # spatial/graph expansion, so a large containing panel does not flood peers.
    for id,o in new.items():
        if id in targets:continue
        if any(overlap(o['bbox'],r['bbox']) for r in regions):
            reads[id].update(('placement','structure'));checks[id].add('local_composite')
            if font:checks[id].add('occlusion')
            reasons.append({'object_id':id,'reason':'old_or_new_affected_region'})
    for objects in (old,new):
        for id,o in objects.items():
            if o['render_type']=='connector':
                endpoints={o['content'].get(k) for k in ('source','target','source_anchor_object','target_anchor_object')}-{None}
                if endpoints & (geometry|topology) or id in geometry|topology:
                    reads[id].update(ALL);checks[id].update(('relations','endpoints','native','occlusion'))
                    for endpoint in endpoints:reads[endpoint].update(('placement','structure','content'))
                    relevant_relations['connector:'+id]=o['content']
            if o.get('prototype_id') and o['id'] in targets:
                # Instance changes do not mutate sibling instances.
                relevant_relations['prototype:'+id]=o['prototype_id']
        for relation in (new_scene or scene)['relations']:
            if {relation['source'],relation['target']} & targets:
                relevant_relations['relation:'+relation.get('id',identity(relation))]=relation
                typ=relation.get('type','unknown')
                if targets & (geometry|topology|font) or typ in ('labels','annotates','occludes','behind','touches','continuous_with'):
                    for endpoint in (relation['source'],relation['target']):
                        reads[endpoint].update(('placement','content','structure'));checks[endpoint].add('relations')
    result={'version':'field-spatial-1','read_facets':{k:sorted(v) for k,v in sorted(reads.items())},
            'checks':{k:sorted(v) for k,v in sorted(checks.items())},'regions':regions,'reasons':reasons,
            'relations':relevant_relations,'reference_hashes':{k:scene[k]['sha256'] for k in ('source','evidence','profile')},
            'post_render_rule':'expand affected regions with actual saved/rendered ink bounds, then recheck new overlaps'}
    result['signature']=identity({k:v for k,v in result.items() if k not in ('reasons',)})
    return result


def make_patch(scene,operations,task_id,new_scene=None):
    import copy
    if new_scene is None:
        new_scene=copy.deepcopy(scene);nodes={o['id']:o for o in new_scene['objects']}
        for op in operations:nodes[op['object_id']][op['field']]=copy.deepcopy(op['value'])
    p=plan(scene,operations,new_scene);objects={o['id']:o for o in scene['objects']}
    return {'task_id':task_id,'base_scene_revision':scene['revision'],'base_scene_hash':identity(scene),
            'dependency_mode':'field_spatial_v1','dependency_signature':p['signature'],
            'reference_hashes':p['reference_hashes'],
            'expected_facets':{id:{f:objects[id]['versions'][f] for f in facets} for id,facets in p['read_facets'].items()},
            'expected_versions':{},'operations':operations}
