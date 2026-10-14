"""Bottom-up source/part/relationship checks on the actual saved native tree."""
import math
from .common import ROOT,digest,identity,read_json,write_json
from .source_analysis import contract_gaps,type_render_route,validate,postorder
from .measure import measure
from .native_task import canonical_math
from .typed_metrics import inventory

NATIVE_TYPES={'T01':{'sp'},'T02':{'sp'},'T03':{'sp'},'T04':{'cxnSp'},'T05':{'sp'},
              'T06':{'graphicFrame'},'T07':{'grpSp'},'T08':{'grpSp'},'T09':{'pic'},'T10':{'grpSp'},'T11':{'sp','grpSp'}}


def union(boxes):
    if not boxes:return None
    x=min(b[0] for b in boxes);y=min(b[1] for b in boxes)
    return [x,y,max(b[0]+b[2] for b in boxes)-x,max(b[1]+b[3] for b in boxes)-y]


def point_to_polyline(point,points):
    if not points or len(points)<2:return None
    distances=[]
    for a,b in zip(points,points[1:]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=dx*dx+dy*dy
        t=max(0.,min(1.,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/length)) if length else 0.
        distances.append(math.dist(point,[a[0]+t*dx,a[1]+t*dy]))
    return min(distances)


def convex_enclosure_error(point,polygon):
    if len(polygon)<3:raise ValueError('Enclosure needs a convex polygon')
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    turns=[cross(polygon[i-1],polygon[i],polygon[(i+1)%len(polygon)]) for i in range(len(polygon))]
    if not (all(v>=0 for v in turns) or all(v<=0 for v in turns)):raise ValueError('Only explicit convex enclosure is implemented')
    edges=polygon+[polygon[0]];signs=[cross(a,b,point) for a,b in zip(edges,edges[1:])]
    if all(v>=0 for v in signs) or all(v<=0 for v in signs):return 0.
    return point_to_polyline(point,edges)


def evaluate(analysis,base,scene,pptx,output,native_report=None):
    from .inspect import inventory as native_inventory,xml
    from lxml import etree as E
    source=validate(analysis,base);measured=measure(scene,pptx);actual=measured['objects']
    type_cards={card['id']:card for card in read_json(ROOT/'config/contracts.json')['cards']
                if card['axis']=='object_type'}
    native_nodes,duplicates=native_inventory(xml(pptx));nodes=source['nodes'];owners=source['owners']
    extras=[]
    scene_objects={o['id']:o for o in scene['objects']}
    for id in actual:
        if id in owners:continue
        parent=native_nodes[id]['parent']
        if parent not in owners or scene_objects.get(parent,{}).get('render_type')!='trace':extras.append(id)
    def owner_of(id):return owners.get(id)
    def within(child,parent):
        while child:
            if child==parent:return True
            child=nodes[child].get('parent')
        return False
    boxes={}
    for id in postorder(analysis):
        node=nodes[id];rids=node.get('render_ids',[])
        boxes[id]=union([actual[r].get('semantic_bbox') or actual[r].get('route_bbox') or actual[r].get('geometry_bbox')
                         for r in rids if r in actual and (actual[r].get('semantic_bbox') or actual[r].get('route_bbox') or actual[r].get('geometry_bbox'))])
        if boxes[id] is None:boxes[id]=union([boxes[n['id']] for n in analysis['nodes'] if n.get('parent')==id and boxes.get(n['id']) is not None])
    order={id:i for i,id in enumerate(native_nodes)};node_checks={id:[] for id in nodes};relation_checks=[]
    def add(id,kind,result,detail):node_checks[id].append({'check':kind,'status':'PASS' if result is True else 'FAIL' if result is False else 'UNVERIFIED','detail':detail})
    for id in postorder(analysis):
        node=nodes[id]
        if node['status']!='observed':add(id,'source_observation',None,'Inferred/unresolved is not confirmed source truth')
        rids=node.get('render_ids',[])+node.get('wrapper_ids',[])
        missing=[r for r in rids if r not in actual]
        add(id,'mapped_objects',not missing,{'missing':missing})
        for r in node.get('render_ids',[]):
            if r not in native_nodes:continue
            kind=E.QName(native_nodes[r]['node']).localname
            expected_routes=type_cards[node['type']]['applies']['render_types']
            item=scene_objects.get(r,{})
            actual_route=item.get('render_type')
            route_evidence=type_render_route(node,item,expected_routes,analysis)
            native_match=(kind in NATIVE_TYPES[node['type']] or
                          route_evidence=='COMPLEX_RASTER_CANDIDATE_REQUIRES_MEASURED_EXCEPTION' and kind=='pic')
            add(id,'native_representation',native_match,
                {'id':r,'actual':kind,'type':node['type'],'route_evidence':route_evidence})
            add(id,'type_render_route',route_evidence is not None,
                {'id':r,'contract':node['type'],'allowed':expected_routes,
                 'actual':actual_route,'route_evidence':route_evidence})
        for r in node.get('wrapper_ids',[]):
            add(id,'native_wrapper',r in native_nodes and E.QName(native_nodes[r]['node']).localname=='grpSp',r)
        for rid,expected in node.get('expected_content',{}).items():
            value=actual.get(rid,{})
            if 'text' in expected:add(id,'text_content',value.get('text')==expected['text'],{'reference':expected['text'],'actual':value.get('text')})
            if 'ast' in expected:
                found=value.get('ast');add(id,'math_structure',found is not None and canonical_math(expected['ast'])==canonical_math(found),{'actual':found,'reference':expected['ast']})
            if 'table' in expected:add(id,'table_structure',value.get('table_cells')==expected['table'],{'actual':value.get('table_cells'),'reference':expected['table']})
        children=source['children'].get(id,[])
        gaps=contract_gaps(node,children,analysis.get('relations',[]))
        for gap in gaps:
            add(id,gap['check'],None,gap)
        if children:
            required=[c for c in children if nodes[c].get('required',True)]
            found=[c for c in required if boxes.get(c) is not None]
            add(id,'critical_parts',found==required,inventory(required,found))
        if node.get('landmarks') and boxes.get(id):
            b=boxes[id];errors={}
            for name,item in node['landmarks'].items():
                if 'anchor_uv' not in item:continue
                point=[b[0]+item['anchor_uv'][0]*b[2],b[1]+item['anchor_uv'][1]*b[3]]
                errors[name]=math.dist(point,item['point'])
            add(id,'landmarks',None,{'errors_px':errors,'note':'Raw distances; no universal threshold'})
    for rel in analysis.get('relations',[]):
        a,b=rel['source'],rel['target'];typ=rel['type'];p=rel.get('parameters',{});result=None;detail={}
        if rel['status']!='observed':detail={'reason':'Unresolved source relation'}
        elif typ in ('contains','part_of') and p.get('enclosure_polygon'):
            ids=p.get('path_ids',[]);polygon=p['enclosure_polygon'];bound=p.get('max_outside_px')
            child=b if typ=='contains' else a
            if any(r not in nodes[child].get('render_ids',[]) for r in ids):raise ValueError('Enclosure path lies outside declared child')
            errors={}
            for r in ids:
                points=actual.get(r,{}).get('route_points') or actual.get(r,{}).get('closed_polyline_points')
                errors[r]=max(convex_enclosure_error(point,polygon) for point in points) if points else None
            result=all(v<=bound for v in errors.values()) if errors and bound is not None and all(v is not None for v in errors.values()) else None
            detail={'outside_distance_px':errors,'max_outside_px':bound,'scope':'Actual open/closed native polyline vertices inside an observed convex boundary; not Bezier control points, pixel clipping or arbitrary silhouettes'}
        elif typ in ('contains','part_of'):result=True;detail={'reason':'Validated source containment, mapped part checks reported separately'}
        elif typ in ('connects','points_to'):
            checks=[]
            for rid in p.get('render_ids',[]):
                obj=actual.get(rid,{});anchors=obj.get('anchors',{});source_anchor=owner_of((anchors.get('source') or {}).get('object_id'));target_anchor=owner_of((anchors.get('target') or {}).get('object_id'))
                expected_source=p.get('anchor_source',a);expected_target=p.get('anchor_target',b)
                connected=within(source_anchor,expected_source) and within(target_anchor,expected_target)
                arrows=obj.get('arrows',{});direction=p.get('direction','end')
                directed=(arrows.get('end') not in (None,'none') and arrows.get('start') in (None,'none')) if direction=='end' else (arrows.get('start') not in (None,'none') and arrows.get('end') not in (None,'none')) if direction=='both' else arrows.get('start') in (None,'none') and arrows.get('end') in (None,'none')
                checks.append({'id':rid,'anchors_match':connected,'direction_match':directed})
            result=all(v['anchors_match'] and v['direction_match'] for v in checks) if checks else None;detail={'connections':checks}
        elif typ in ('occludes','behind'):
            front,back=(a,b) if typ=='occludes' else (b,a)
            pairs=p.get('render_pairs',[])
            if pairs:
                observed=[]
                for f,k in pairs:
                    if f not in actual or k not in actual:observed.append(False);continue
                    x,y=actual[f].get('geometry_bbox'),actual[k].get('geometry_bbox')
                    intersects=x and y and min(x[0]+x[2],y[0]+y[2])>max(x[0],y[0]) and min(x[1]+x[3],y[1]+y[3])>max(x[1],y[1])
                    observed.append(bool(intersects and order[f]>order[k] and within(owners.get(f),front) and within(owners.get(k),back)))
                result=all(observed);detail={'pair_results':observed,'scope':'Actual native ordering and overlapping frames; pixel witnesses remain required for complex holes/interleaving'}
        elif typ in ('touches','continuous_with') and p.get('contact_point') is not None:
            # Overlapping bounding boxes do not prove that two scientific
            # routes meet at the observed junction or conflict point.
            ids=p.get('path_ids',[]);point=p['contact_point'];bound=p.get('max_gap_px')
            if len(point)!=2 or not all(math.isfinite(v) for v in point):raise ValueError('Invalid observed contact point')
            if any(r not in nodes[a].get('render_ids',[])+nodes[b].get('render_ids',[]) for r in ids):raise ValueError('Contact paths are outside semantic relation')
            errors={r:point_to_polyline(point,actual.get(r,{}).get('route_points')) for r in ids}
            result=(all(v<=bound for v in errors.values()) if errors and bound is not None and all(v is not None for v in errors.values()) else None)
            detail={'path_contact_errors_px':errors,'source_contact_point':point,'source_requirement_max_gap_px':bound,
                    'scope':'Saved native polyline distance to the independently observed contact point; curves are UNVERIFIED'}
        elif typ in ('touches','continuous_with') and boxes.get(a) and boxes.get(b):
            x,y=boxes[a],boxes[b]
            dx=max(0,x[0]-y[0]-y[2],y[0]-x[0]-x[2]);dy=max(0,x[1]-y[1]-y[3],y[1]-x[1]-x[3]);gap=math.hypot(dx,dy)
            bound=p.get('max_gap_px');result=gap<=bound if bound is not None else None;detail={'gap_px':gap,'source_requirement_max_gap_px':bound,'scope':'Frame-contact predicate; curved boundary contacts need landmarks/pixel checking'}
        elif typ in ('aligned','spaced','labels','annotates'):
            detail={'source_box':boxes.get(a),'target_box':boxes.get(b),'reason':'Located layout remains a measured/rubric requirement, no default threshold'}
        record={'id':rel['id'],'type':typ,'required':rel.get('required',True),'status':'PASS' if result is True else 'FAIL' if result is False else 'UNVERIFIED','detail':detail}
        relation_checks.append(record)
        for id in (a,b):node_checks[id].append({'check':'relation:'+rel['id'],'status':record['status'],'required':record['required'],'detail':detail})
    outcomes={}
    for id in postorder(analysis):
        own=node_checks[id];children=source['children'].get(id,[])
        failures=[x for x in own if x['status']=='FAIL'];unknown=[x for x in own if x['status']=='UNVERIFIED']
        child_fail=any(outcomes[c]['hard_status']=='FAIL' for c in children)
        child_unknown=any(outcomes[c]['hard_status']=='UNVERIFIED' for c in children)
        # Raw landmark/visual measurements have no fabricated PASS threshold.
        hard_unknown=[x for x in unknown if x['check'] not in ('landmarks',) and x.get('required',True)]
        hard='FAIL' if failures or child_fail else 'UNVERIFIED' if hard_unknown or child_unknown or node_checks[id]==[] else 'PASS'
        outcomes[id]={'hard_status':hard,'checks':own,'children':children,'bbox':boxes.get(id),
                      'visual_status':'UNVERIFIED','native_operations':'UNVERIFIED'}
    if native_report is not None:
        proof=read_json(native_report)
        if proof.get('source_pptx_hash')!=digest(pptx):raise ValueError('Native evidence belongs to another saved candidate')
        for id,node in nodes.items():
            ids=set(node.get('render_ids',[])+node.get('wrapper_ids',[]));matched=[c for c in proof.get('checks',[]) if c['object_id'] in ids]
            if matched:outcomes[id]['native_operations']='RECORDED_REQUIRES_OPERATION_CHAIN' if all(c['status']=='PASS' for c in matched) else 'FAIL'
    record={'version':'hierarchy-check-0.2.0','analysis_hash':identity(analysis),'source_hash':analysis['source']['sha256'],
            'pptx_hash':digest(pptx),'scene_hash':identity(scene),'objects':outcomes,'relations':relation_checks,
            'unexpected_native_objects':extras,'duplicates':duplicates,
            'hard_status':'FAIL' if extras or duplicates or any(v['hard_status']=='FAIL' for v in outcomes.values()) else 'UNVERIFIED' if any(v['hard_status']=='UNVERIFIED' for v in outcomes.values()) else 'PASS',
            'status':'UNVERIFIED','reason':'Hierarchy/content constraints are separate from calibrated visual and complete native-operation acceptance'}
    write_json(output,record);return record
