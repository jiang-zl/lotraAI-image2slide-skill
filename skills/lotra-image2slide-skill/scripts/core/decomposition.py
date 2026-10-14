"""Executable representation transactions preserving the source inventory.

This is the deterministic coordinator, not an image recognizer. Structural
candidates are isolated from the selected scene until actual checks are supplied.
"""
import copy
import time
from pathlib import Path
from .common import identity, read_json, write_json, writer, digest
from .source_analysis import validate as validate_analysis, postorder
from .scene import validate as validate_scene
from .dependencies import overlap

VERSION='recursive-workflow-1.0.0'
ACTIONS={'split','merge','replace_representation','complete_occlusion'}
OBSERVED_FIELDS=('id','parent','semantic_class','view','style_tags','status','evidence_refs','edit_targets','facts','required')


def descendants(objects,root):
    result={root}
    while True:
        more=result|{o['id'] for o in objects if o.get('parent') in result}
        if more==result:return result
        result=more


def preserve_inventory(before,after):
    """Rendering changes cannot erase observations or weaken requested edits."""
    for field in ('source','canvas','user_constraints','scientific_theme'):
        if before[field]!=after[field]:raise ValueError('Structural transaction changed frozen '+field)
    for field in ('observations','relations'):
        old={x['id']:x for x in before.get(field,[])};new={x['id']:x for x in after.get(field,[])}
        if any(new.get(k)!=v for k,v in old.items()):raise ValueError('Source inventory lost or changed: '+field)
    new={n['id']:n for n in after['nodes']}
    for n in before['nodes']:
        if n['id'] not in new:raise ValueError('Source semantic node was discarded: '+n['id'])
        for field in OBSERVED_FIELDS:
            if n.get(field)!=new[n['id']].get(field):
                raise ValueError('Representation cannot rewrite source fact/edit target: '+n['id']+'.'+field)


def propose(scene,analysis,base,request,new_analysis):
    """Replace an authorized rendering subtree; return an isolated candidate.

    External scientific endpoints must keep their IDs. Moving to a different
    endpoint is a content edit and uses the separately authorized patch workflow.
    """
    if request.get('action') not in ACTIONS:raise ValueError('Unknown structural action')
    if request.get('scene_hash')!=identity(scene) or request.get('analysis_hash')!=identity(analysis):
        raise ValueError('Stale structural request')
    if not request.get('reason') or not request.get('evidence_refs'):
        raise ValueError('A structural change needs a located reason')
    parsed=validate_analysis(analysis,base,scene)
    if not set(request['evidence_refs'])<=parsed['observations'].keys():raise ValueError('Unknown structural evidence')
    preserve_inventory(analysis,new_analysis)
    objects={o['id']:o for o in scene['objects']};root=request['root_render_id']
    if root not in objects:raise ValueError('Missing structural root')
    affected=descendants(scene['objects'],root)
    if affected!=set(request.get('authorized_render_ids',[])):raise ValueError('Explicit subtree authorization required')
    if any(objects[k]['locks']['structure'] for k in affected):raise ValueError('Structural lock')
    added=copy.deepcopy(request['objects']);new_ids={o['id'] for o in added}
    if len(new_ids)!=len(added) or new_ids & (objects.keys()-affected):raise ValueError('Duplicate/colliding replacement IDs')
    if root not in new_ids:raise ValueError('Stable component root must survive')
    new_root=next(o for o in added if o['id']==root)
    if new_root.get('parent')!=objects[root].get('parent'):raise ValueError('Cannot silently move component to another parent')
    if descendants(added,root)!=new_ids:raise ValueError('Replacement escaped authorized component')
    candidate=copy.deepcopy(scene)
    # Retain the root's authored paint position. Appending a repaired subtree
    # would silently move it above unrelated scientific labels and occluders.
    root_index=next(i for i,o in enumerate(scene['objects']) if o['id']==root)
    insertion=sum(o['id'] not in affected for o in scene['objects'][:root_index])
    kept=[o for o in candidate['objects'] if o['id'] not in affected]
    candidate['objects']=kept[:insertion]+added+kept[insertion:]
    candidate['revision']+=1
    combined={**objects,**{o['id']:o for o in added}}
    for obj in added:
        if obj['id'] in objects:
            previous=objects[obj['id']]
            if obj['locks']!=previous['locks']:raise ValueError('Replacement cannot unlock an existing object')
            fields={'content':('content','semantic_type'),'style':('style',),
                    'placement':('bbox','z_order'),'structure':('parent','render_type','component')}
            for facet,names in fields.items():
                if previous['locks'][facet] and any(previous.get(k)!=obj.get(k) for k in names):
                    raise ValueError('Replacement violates an existing object lock')
            obj['versions']={f:previous['versions'][f]+1 for f in previous['versions']}
    # References are rebound to immutable new files by stage(); no stale analysis
    # is read while validating the in-memory candidate.
    candidate.pop('analysis',None)
    validate_scene(candidate,base)
    validate_analysis(new_analysis,base,candidate)
    touched=affected|new_ids
    boxes=[objects[k]['bbox'] for k in affected]+[o['bbox'] for o in added]
    recheck=set(touched)
    for o in scene['objects']+candidate['objects']:
        if any(overlap(o['bbox'],b) for b in boxes):recheck.add(o['id'])
        if o['render_type']=='connector' and any(o['content'].get(k) in touched for k in
            ('source','target','source_anchor_object','target_anchor_object')):recheck.add(o['id'])
    for rid in list(touched):
        parent=(objects.get(rid) or next(o for o in added if o['id']==rid)).get('parent')
        while parent:
            recheck.add(parent);parent=combined[parent].get('parent')
    return {'version':VERSION,'action':request['action'],'scene':candidate,'analysis':new_analysis,
            'base_scene_hash':identity(scene),'request_hash':identity(request),
            'source_inventory_hash':identity([{f:n.get(f) for f in OBSERVED_FIELDS} for n in analysis['nodes']]),
            'recheck':sorted(recheck),'status':'CANDIDATE_REQUIRES_RENDER_CONTEXT_NATIVE'}


def stage(proposal,base,output):
    output=Path(output).resolve();base=Path(base).resolve()
    if output.exists():raise FileExistsError(output)
    if not output.is_relative_to(base):raise ValueError('Candidate directory must be inside task base')
    with writer(output):
        analysis_path=output/'analysis.json';write_json(analysis_path,proposal['analysis'])
        scene=copy.deepcopy(proposal['scene'])
        scene['analysis']={'path':analysis_path.relative_to(base).as_posix(),'sha256':digest(analysis_path)}
        validate_scene(scene,base)
        write_json(output/'scene.json',scene)
        receipt={k:v for k,v in proposal.items() if k not in ('scene','analysis')}
        receipt.update(scene_hash=identity(scene),analysis_hash=identity(proposal['analysis']))
        write_json(output/'transaction.json',receipt)
    return receipt


def work_queue(analysis,*,max_candidates=6):
    if type(max_candidates) is not int or max_candidates<1:raise ValueError('Positive candidate batch required')
    nodes={n['id']:n for n in analysis['nodes']}
    return {'version':VERSION,'analysis_hash':identity(analysis),'max_candidates_per_batch':max_candidates,
            'items':[{'id':k,'parent':nodes[k].get('parent'),'state':'OBSERVE',
                      'attempts':[],'best_local':None,'best_context':None,'unresolved':[]}
                     for k in postorder(analysis)],'status':'IN_PROGRESS'}


def record_check(queue,object_id,candidate,checks,*,changed_decision):
    """Advance the task using bound artifacts; does not replace final QA gate."""
    if not changed_decision:raise ValueError('Do not log no-op improvement attempts')
    item=next(x for x in queue['items'] if x['id']==object_id)
    if len(item['attempts'])>=queue['max_candidates_per_batch']:
        item['state']='PAUSED_RESOURCE_LIMIT';return item
    if not candidate.get('scene_hash') or not candidate.get('pptx_hash') or not candidate.get('preview_hash'):
        raise ValueError('Candidate must have actual saved/rendered identities')
    required=('structure','local','context','native')
    for key in required:
        c=checks.get(key,{})
        if c.get('status') not in ('PASS','FAIL','UNVERIFIED') or not c.get('evidence_hash'):
            raise ValueError('Missing bound check: '+key)
        if c.get('pptx_hash')!=candidate['pptx_hash']:raise ValueError('Check belongs to another PPT')
    record={'candidate':candidate,'checks':checks,'changed_decision':changed_decision,'recorded_at':time.time()}
    item['attempts'].append(record)
    local=all(checks[k]['status']=='PASS' for k in ('structure','local'))
    # Quality vector comparison stays in iteration.register; these are stage flags.
    if local:item['state']='CHECK_CONTEXT'
    if checks['context']['status']=='FAIL':item['state']='REPAIR'
    elif any(c['status']=='FAIL' for c in checks.values()):item['state']='REPAIR'
    elif all(checks[k]['status']=='PASS' for k in required):item['state']='CHECKED_CANDIDATE'
    else:item['state']='CHECK_NATIVE' if local else 'CHECK_LOCAL'
    item['unresolved']=[k for k in required if checks[k]['status']!='PASS']
    return item


def compact_order(analysis,object_id,*,max_chars=12000):
    """Bounded context for small models; never truncate facts silently."""
    if type(max_chars) is not int or max_chars < 1:
        raise ValueError('Positive context budget required')
    nodes={n['id']:n for n in analysis['nodes']};node=nodes[object_id]
    relevant=[node]+[n for n in analysis['nodes'] if n.get('parent')==object_id]
    scope={n['id'] for n in relevant}
    relations=[r for r in analysis.get('relations',[]) if scope.intersection((r['source'],r['target']))]
    neighbor_ids={r[k] for r in relations for k in ('source','target')}-scope
    parent=nodes.get(node.get('parent'))
    if parent:neighbor_ids.discard(parent['id'])
    neighbors=[nodes[k] for k in sorted(neighbor_ids)]
    observations={o['id']:o for o in analysis['observations']}
    refs={r for n in relevant+neighbors+([parent] if parent else []) for r in n['evidence_refs']}
    refs.update(r for relation in relations for r in relation.get('evidence_refs',[]))
    result={'version':VERSION,'source':analysis['source'],'analysis_hash':identity(analysis),
            'object':node,'parent':parent,'neighbors':neighbors,
            'children':[n for n in relevant if n['id']!=object_id],
            'observations':[observations[k] for k in sorted(refs)],
            'relations':relations,
            'allowed_actions':sorted(ACTIONS),'next':'Observe this crop, choose representation, then build and check parent context'}
    from .common import canonical
    result['context_accounting']={'characters':0,'tokens':None,'token_reason':'Host usage unavailable; characters are not tokens'}
    # Include the accounting envelope itself in the advertised hard budget.
    while True:
        size=len(canonical(result).decode('utf-8'))
        if size==result['context_accounting']['characters']:break
        result['context_accounting']['characters']=size
    if size>max_chars:raise ValueError('Work order exceeds context budget; split the semantic task, do not omit evidence')
    return result
