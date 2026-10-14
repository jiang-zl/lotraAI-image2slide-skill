"""Host-authored observations, semantic hierarchy and explicit rendering owners.

No model call is made here. A validation result means the observation contract
is consistent, not that an inference has become ground truth.
"""
from collections import defaultdict
import math
from .common import digest, identity, safe_path

VERSION='source-analysis-1.0.0'
LEVELS={'S0','S1','S2','S3','S4'}
TYPES={'T%02d'%i for i in range(1,12)}
ROLES={'R%d'%i for i in range(5)}
RELATIONS={'contains','part_of','connects','points_to','labels','annotates','aligned','spaced',
           'occludes','behind','repeats','instance_of','touches','continuous_with'}
SINGLE_OUTLINE_CLASSES={'callout','speech_bubble','category_bubble','annotation_bubble'}


def contract_gaps(node, children=(), relations=()):
    """Source evidence missing for a type card; leave the task incomplete."""
    if node.get('status')!='observed':
        return []
    gaps=[]
    required={'T01':'text','T02':'ast','T06':'table'}.get(node['type'])
    if required:
        for rid in node.get('render_ids',[]):
            if required not in node.get('expected_content',{}).get(rid,{}):
                gaps.append({'check':'source_content_contract','type':node['type'],
                             'render_id':rid,'required':required})
    raster_background_unit=(node.get('asset_role') in ('environment_asset','illustration_asset')
                            and node.get('decomposition',{}).get('decision')=='no_independent_edit_value')
    if node['type'] in ('T07','T08') and not children and not raster_background_unit:
        gaps.append({'check':'critical_parts','type':node['type'],
                     'reason':'No independently observed child parts'})
    if node['type']=='T04' and node.get('facts',{}).get('connection_scope') not in ('axis_annotation','decorative'):
        witnessed={rid for relation in relations
                   if relation.get('type') in ('connects','points_to') and relation.get('status')=='observed'
                   for rid in relation.get('parameters',{}).get('render_ids',[])}
        for rid in node.get('render_ids',[]):
            if rid not in witnessed:
                gaps.append({'check':'directed_connection_source','type':'T04',
                             'render_id':rid,'reason':'No observed relation binds this connector'})
    return gaps


def type_render_route(node, obj, allowed, analysis):
    """Default card route or a source-bound complex-raster *candidate* route.

    This checks classification consistency only. A raster candidate still needs
    the measured native-first exception and cutout/quality gates elsewhere.
    """
    route=obj['render_type']
    if route in allowed:
        return 'CARD_ROUTE'
    from .complex_assets import RASTER_ROLES
    role=obj.get('semantic_type')
    if (route=='photo' and role in RASTER_ROLES and node.get('asset_role')==role
            and node.get('role') not in ('R3','R4')
            and analysis.get('user_constraints',{}).get('allow_complex_raster') is True
            and obj.get('edit_contract',{}).get('representation')=='raster_module'):
        return 'COMPLEX_RASTER_CANDIDATE_REQUIRES_MEASURED_EXCEPTION'
    return None


def _check_single_outline(node, objects, base):
    """One observed exterior has one native contour owner, not stitched seams."""
    outline=node.get('continuous_outline')
    semantic_class=node['semantic_class'].lower().replace('-','_').replace(' ','_')
    required=any(label in semantic_class for label in SINGLE_OUTLINE_CLASSES)
    if not required and outline is None:
        return
    if not isinstance(outline,dict) or outline.get('kind')!='single':
        raise ValueError('Continuous exterior needs one native outline: '+node['id'])
    owner=outline.get('render_id')
    if (owner not in node.get('render_ids',[]) or owner not in objects or
            not outline.get('source_evidence_refs') or
            not set(outline['source_evidence_refs'])<=set(node['evidence_refs'])):
        raise ValueError('Single outline needs a source-bound rendering owner: '+node['id'])
    outline_parts=[rid for rid in node.get('render_ids',[])
                   if objects[rid]['render_type'] in ('shape','path','bezier','trace')]
    if outline_parts != [owner]:
        raise ValueError('A continuous exterior cannot use stitched outline fragments: '+node['id'])
    item=objects[owner]
    if item['render_type']=='shape':
        if required and item['content'].get('preset')!='wedgeRoundRectCallout':
            raise ValueError('Callout exterior needs one matching callout preset or closed path: '+node['id'])
    elif item['render_type']=='path':
        assessment=outline.get('preset_assessment')
        if (not isinstance(assessment,dict) or assessment.get('status')!='REJECTED' or
                not assessment.get('candidate') or not assessment.get('reason') or
                not assessment.get('evidence_refs') or
                not set(assessment['evidence_refs'])<=set(node['evidence_refs'])):
            raise ValueError('Custom exterior path needs source-bound preset rejection: '+node['id'])
        contours=item['content'].get('contours')
        if contours is None and base is not None:
            from .common import read_json
            contours=read_json(safe_path(base,item['content']['geometry_ref']['path']))['contours']
        if contours is not None and (len(contours)!=1 or contours[0].get('closed') is not True):
            raise ValueError('Single exterior path must have exactly one closed contour: '+node['id'])
    else:
        raise ValueError('Continuous exterior must use one preset or closed native path: '+node['id'])


def validate(analysis,base,scene=None):
    if analysis.get('schema_version')!='source-analysis-1':raise ValueError('Unknown Source Analysis version')
    if analysis.get('author',{}).get('kind') not in ('host_model','human'):raise ValueError('Source Analysis needs a real host/human author')
    source=analysis['source'];path=safe_path(base,source['path'])
    if digest(path)!=source['sha256']:raise ValueError('Source Analysis image changed')
    from PIL import Image
    image=Image.open(path)
    if list(image.size)!=analysis['canvas']['source_size']:raise ValueError('Source canvas mismatch')
    if analysis['canvas'].get('mapping')!='identity_px':raise ValueError('Only explicit identity pixel canvas supported')
    if not analysis.get('scientific_theme') or not isinstance(analysis.get('user_constraints'),dict):raise ValueError('Task context/constraints missing')
    observations={o['id']:o for o in analysis.get('observations',[])}
    nodes={n['id']:n for n in analysis.get('nodes',[])}
    if not nodes or len(nodes)!=len(analysis['nodes']):raise ValueError('Empty/duplicate semantic inventory')
    if not observations or len(observations)!=len(analysis['observations']):raise ValueError('Empty/duplicate observations')
    for o in observations.values():
        if o.get('status') not in ('observed','inferred','unresolved'):raise ValueError('Unknown observation status')
        if not o.get('note') or o.get('source_hash')!=source['sha256']:raise ValueError('Observation lacks source identity/note')
        roi=o.get('roi')
        if not roi or len(roi)!=4 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in roi):raise ValueError('Observation needs located ROI')
        x,y,w,h=roi
        if min(x,y)<0 or min(w,h)<=0 or x+w>image.width or y+h>image.height:raise ValueError('Observation outside source canvas')
    owners={};children=defaultdict(list)
    for n in nodes.values():
        if n['level'] not in LEVELS or n['type'] not in TYPES or n['role'] not in ROLES:raise ValueError('Unknown semantic/type/role card')
        if n.get('status') not in ('observed','inferred','unresolved'):raise ValueError('Unknown node evidence status')
        refs=n.get('evidence_refs',[])
        if not refs or not set(refs)<=observations.keys():raise ValueError('Node needs independent source observations')
        if n['status']=='observed' and any(observations[k]['status']!='observed' for k in refs):raise ValueError('Inferred evidence cannot silently become observed')
        if not n.get('semantic_class') or not n.get('view') or not n.get('style_tags'):raise ValueError('Object class/view/style required for method selection')
        if not isinstance(n.get('edit_targets'),list) or not n['edit_targets']:raise ValueError('Required editing scope must be explicit')
        if n.get('parent'):
            if n['parent'] not in nodes:raise ValueError('Missing semantic parent')
            children[n['parent']].append(n['id'])
        seen={n['id']};parent=n.get('parent')
        while parent:
            if parent in seen:raise ValueError('Semantic containment cycle')
            seen.add(parent);parent=nodes[parent].get('parent')
        for rid in n.get('render_ids',[])+n.get('wrapper_ids',[]):
            if rid in owners:raise ValueError('One rendering fragment must have one semantic owner')
            owners[rid]=n['id']
    for n in nodes.values():
        stop=n.get('decomposition',{})
        if not stop.get('reason') or not stop.get('evidence_refs') or not set(stop['evidence_refs'])<=observations.keys():raise ValueError('Decomposition/stop needs evidence and reason')
        if children[n['id']]:
            if stop.get('decision')!='split':raise ValueError('Parent children contradict stop decision')
        elif stop.get('decision') not in ('native_unit','no_independent_edit_value','unresolved','resource_stop'):
            raise ValueError('Leaf stop needs a semantic/editability reason, not an arbitrary depth')
        if stop.get('decision') in ('native_unit','no_independent_edit_value') and not n.get('render_ids'):
            raise ValueError('Representable leaf has no native mapping')
    relation_ids=set()
    for r in analysis.get('relations',[]):
        if r['id'] in relation_ids:raise ValueError('Duplicate relation')
        relation_ids.add(r['id'])
        if r['type'] not in RELATIONS or r['source'] not in nodes or r['target'] not in nodes:raise ValueError('Invalid semantic relation')
        if r.get('status') not in ('observed','inferred','unresolved') or not r.get('evidence_refs') or not set(r['evidence_refs'])<=observations.keys():raise ValueError('Relation needs located source evidence')
        if r['type'] in ('contains','part_of'):
            child,parent=(r['target'],r['source']) if r['type']=='contains' else (r['source'],r['target'])
            if nodes[child].get('parent')!=parent:raise ValueError('Containment edge disagrees with semantic tree')
        # Scientific connects/points_to cycles are deliberately not rejected.
    if scene is not None:
        ids={o['id'] for o in scene['objects']}
        if set(owners)!=ids:raise ValueError('Explicit semantic/render mapping must cover every saved object without extras')
        if scene['source']['sha256']!=source['sha256']:raise ValueError('Scene uses a different source')
        from .complex_assets import RASTER_ROLES, editing_gaps, validate_foreground
        objects={o['id']:o for o in scene['objects']}
        for node in nodes.values():
            _check_single_outline(node,objects,base)
        for node in nodes.values():
            if node['decomposition']['decision'] in ('unresolved','resource_stop'):
                continue
            gaps=editing_gaps(node,objects)
            if gaps:
                raise ValueError('Unmet editing requirement for '+node['id']+': '+str(gaps))
        for obj in scene['objects']:
            if obj['render_type'] == 'photo':
                flag = 'allow_complex_raster' if obj['semantic_type'] in RASTER_ROLES else 'allow_data_raster'
                if not analysis['user_constraints'].get(flag, False):raise ValueError('Task does not permit this raster scope: '+flag)
        scientific_ids={rid for node in nodes.values() if node['role'] in ('R3','R4') or node.get('scientific_content') is True
                        for rid in node.get('render_ids',[])}
        validate_foreground(scene,scientific_ids)
    return {'nodes':nodes,'observations':observations,'owners':owners,'children':dict(children),
            'analysis_hash':identity(analysis),'status':'CONSISTENT_NOT_GROUND_TRUTH'}


def postorder(analysis):
    nodes={n['id']:n for n in analysis['nodes']};result=[];active=set();done=set()
    def visit(id):
        if id in active:raise ValueError('Containment cycle')
        if id in done:return
        active.add(id)
        for n in analysis['nodes']:
            if n.get('parent')==id:visit(n['id'])
        active.remove(id);done.add(id);result.append(id)
    for id in nodes:visit(id)
    return result
