"""Original-owned containment DAG and aggregate, per-level two-axis checks.

Native groups are coordinate owners, not source containment evidence. Direct
semantic members and logical references are separate. Actual geometry reuses
neighbor_geometry and its host capture route; no nominal-frame fallback.
"""
import copy, math
import numpy as np
from shapely.geometry import Polygon, box
from shapely.ops import unary_union
from shapely.affinity import translate
from .common import identity, digest, read_json, write_json, safe_path, writer

VERSION='recursive-containment-1'

def source_view(task,state,ref):
    from .execution_contract import resource
    if not ref or ref.get('source_hash')!=state['source']['sha256'] or not ref.get('roi'):
        raise ValueError('Independent original-only view and source hash required')
    resource(task,ref)
    # Prove pixels are the declared unchanged original crop, not a candidate
    # screenshot mislabeled as original evidence.
    from .resource_facts import image_region,image_copy
    roi=ref['roi'];box=(math.floor(roi[0]),math.floor(roi[1]),math.ceil(roi[0]+roi[2]),math.ceil(roi[1]+roi[3]))
    with image_region(resource(task,state['source']),[('crop',box)],state['source']['sha256']) as crop, image_copy(resource(task,ref),ref['sha256']) as actual:
        if actual.size!=crop.size or not np.array_equal(np.asarray(actual),np.asarray(crop)):
            raise ValueError('Source membership cannot be derived from a candidate or enhanced view')

def hierarchy_survey(contract):
    """Enumerate source-domain nesting candidates; never assign semantics.

    A model must decide each pair. Close containment, overlap or native group
    ancestry alone do not establish a semantic parent.
    """
    rows=contract.get('containers',[]);pairs=set()
    for outer in rows:
        x,y,w,h=outer['source_bbox'];pad=max(.5,min(w,h)*.005)
        for inner in rows:
            if outer['id']==inner['id']:continue
            a,b,c,d=inner['source_bbox']
            if (a>=x-pad and b>=y-pad and a+c<=x+w+pad and b+d<=y+h+pad
                    and (w*h>c*d*(1+1e-9) or inner['id'] in outer['members'])):
                pairs.add((outer['id'],inner['id']))
        pairs.update((outer['id'],m) for m in outer['members'] if any(r['id']==m for r in rows))
    return [{'parent':a,'child':b} for a,b in sorted(pairs)]

def _hierarchy(contract,cs,order):
    pairs=hierarchy_survey(contract);decisions=contract.get('hierarchy_decisions')
    if decisions is None:raise ValueError('Original hierarchy decisions required for every potential nested container pair')
    keyed={(r['parent'],r['child']):r for r in decisions}
    if len(keyed)!=len(decisions) or set(keyed)!={(r['parent'],r['child']) for r in pairs}:
        raise ValueError('Potential nested relation coverage incomplete; reobserve the original hierarchy')
    closure={}
    for n in order:
        direct={m for m in cs[n]['members'] if m in cs}
        closure[n]=direct|set().union(*(closure[m] for m in direct)) if direct else set()
    for (p,c),r in keyed.items():
        expected='direct' if c in cs[p]['members'] else 'ancestor' if c in closure[p] else 'independent'
        if r.get('decision')!=expected or not r.get('source_evidence'):
            raise ValueError('Original hierarchy decision does not match its complete DAG: '+p+' -> '+c)
    return {'potential_pairs':len(pairs),'decisions':len(decisions),'passed':True}

def validate(contract,state):
    from .source_contract import finite
    finite(contract,'recursive_containment')
    if contract.get('schema')!=VERSION or contract.get('source_hash')!=state['source']['sha256'] or contract.get('canvas')!=state['source_size']:
        raise ValueError('Freeze original image identity and canvas')
    elements=contract.get('elements',[]);nodes=contract.get('containers',[])
    by={r['id']:r for r in elements};cs={r['id']:r for r in nodes}
    if len(by)!=len(elements) or len(cs)!=len(nodes) or set(by)&set(cs):raise ValueError('Distinct source semantic IDs required')
    expected=set(state.get('quality',{}).get('units',{}))
    declarations=contract.get('source_units',[])
    if len({r['id'] for r in declarations})!=len(declarations) or {r['id'] for r in declarations}!=expected:
        raise ValueError('Every existing original semantic unit must be explicitly accounted for')
    for d in declarations:
        if d.get('role') not in ('element','container','logical_reference','outside') or not d.get('source_evidence'):
            raise ValueError('Do not silently remove original units to close coverage')
        if d['role'] in ('element','container') and d.get('target') not in set(by)|set(cs):raise ValueError('Missing source unit ownership')
    for r in elements:
        if not r.get('objects') or not r.get('source_bbox') or not r.get('source_evidence'):raise ValueError('Source element needs native binding and original facts')
        if 'table_cell' in r and (len(r['objects'])!=1 or len(r['table_cell'])!=2 or any(type(v) is not int or v<0 for v in r['table_cell'])):
            raise ValueError('A cell glyph member needs its exact saved table and zero-based cell anchor')
    owned={};children={r['id']:[] for r in nodes}
    for r in nodes:
        direct=r.get('members');t=r.get('target',{});domain=r.get('domain',{})
        if direct is None or len(direct)!=len(set(direct)) or not set(direct)<=set(by)|set(cs):raise ValueError('Declare exact direct members, including explicit empty containers')
        body_parts=r.get('body_parts',[])
        if len(body_parts)!=len(set(body_parts)) or not set(body_parts)<=set(by) or set(body_parts)&set(direct):raise ValueError('Original borders/dividers are owned body parts, separately from content; all remain registered and checked')
        if set(r.get('logical_references',[]))&set(direct):raise ValueError('Logical reference is not direct ownership')
        if t.get('axes')!=['x','y'] or t.get('measurement_basis')!='direct_member_paint_union':
            raise ValueError('Both axes and the fixed complete painted union are mandatory')
        if t.get('center') not in ('domain_bbox_center','domain_centroid','directional_clearance') or not r.get('source_evidence'):
            raise ValueError('Declare a stable target center separately from original bias')
        if t.get('center')=='directional_clearance':
            asymmetry=t.get('target_asymmetry_px',[0.,0.])
            if len(asymmetry)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in asymmetry):
                raise ValueError('Freeze both directional gap targets before comparison')
        if not t.get('authorization') or not isinstance(t.get('source_uncertainty_px'),(int,float)) or t['source_uncertainty_px']<0:
            raise ValueError('Freeze authorized centering and source uncertainty before measurement')
        if domain.get('kind') not in ('native_body','native_table','native_cell','logical_polygon') or min(domain.get('padding_px',[0,0,0,0]))<0:
            raise ValueError('A semantic container needs its effective interior, padding and native/source domain')
        if domain['kind'] in ('native_body','native_table','native_cell') and not domain.get('object'):raise ValueError('Bind actual body independently of content/group extent')
        if domain['kind']=='logical_polygon':
            p=Polygon(domain.get('points',[]))
            if p.is_empty or not p.is_valid:raise ValueError('Explicit valid logical domain required')
        for m in direct+body_parts:
            if m in owned:raise ValueError('Two direct owners for '+m+'; use separate logical references')
            owned[m]=r['id']
            if m in cs:children[r['id']].append(m)
    pending=set(cs);order=[]
    while pending:
        ready=sorted(n for n in pending if not set(children[n])&pending)
        if not ready:raise ValueError('Cyclic recursive containment')
        order+=ready;pending-=set(ready)
    # No recursive depth cutoff: the iterative topological order covers DAG.
    spacing=contract.get('spacing_relations',[])
    known={n for e in elements for n in e['objects']}|{c['domain'].get('object') for c in nodes}
    if len({r.get('id') for r in spacing})!=len(spacing):raise ValueError('Unique source spacing relations required')
    for r in spacing:
        if (r.get('axis') not in ('x','y','normal') or not r.get('before') or not r.get('after') or
                set(r['before'])&set(r['after']) or not set(r['before']+r['after'])<=known or
                not r.get('source_evidence') or not r.get('rule') or not r.get('source_bounds')):
            raise ValueError('Spacing requires independently observed sides, native owners, source bounds and frozen rule')
        if not isinstance(r.get('minimum_gap_px'),(int,float)) or not math.isfinite(r['minimum_gap_px']) or r['minimum_gap_px']<0:
            raise ValueError('Finite nonnegative source/authorized spacing target required')
        if abs(r['minimum_gap_px']-spacing_target(r,state['source_size']))>1e-9:
            raise ValueError('Spacing target must be program-derived from original opposing bounds and the frozen readability rule')
    if 'hierarchy_decisions' in contract:_hierarchy(contract,cs,order)
    return by,cs,order

def discovery(task,state,candidate):
    from .boundary_geometry import saved_nodes
    from .mathml import NS
    nodes=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size'])
    candidates=[]
    for name,row in nodes.items():
        if row['tag']=='grpSp':continue
        from .native_connection_transaction import verify_anchor
        if verify_anchor(row):continue
        preset=row['node'].find('p:spPr/a:prstGeom',NS)
        if preset is not None and preset.get('prst') in ('rect','roundRect','ellipse') or row['node'].find('p:spPr/a:custGeom',NS) is not None or row['node'].find('.//a:tbl',NS) is not None:
            enclosed=[];frame=row.get('frame');props=row['node'].find('p:spPr',NS)
            # A transparent outline containing multiple independently mapped
            # leaves cannot silently be called an empty primitive. This is a
            # reobservation trigger, not an automatic semantic assignment.
            closed_outline=preset is not None or props is not None and props.find('a:custGeom/a:pathLst/a:path/a:close',NS) is not None
            if closed_outline and frame and props is not None and props.find('a:noFill',NS) is not None and props.find('a:ln/a:noFill',NS) is None:
                x,y,w,h=frame
                for child,other in nodes.items():
                    if child==name or other['tag']=='grpSp' or verify_anchor(other) or not other.get('frame'):continue
                    a,b,c,d=other['frame']
                    if c>0 and d>0 and a>=x and b>=y and a+c<=x+w and b+d<=y+h and c*d<w*h*.95:
                        enclosed.append(child)
            candidates.append({'object':name,'native_kind':row['tag'],'preset':preset.get('prst') if preset is not None else None,
                'nominal_frame_hint_only':frame,'enclosure_reobservation':sorted(enclosed) if len(enclosed)>1 else []})
    return {'kind':'recursive_containment_source','source_hash':state['source']['sha256'],
        'source_units':sorted(state.get('quality',{}).get('units',{})), 'candidate_owners':candidates,
        'action':'containment-check bind','return':'Original-only container/primitive decisions for every candidate owner, all source-unit ownership, direct member DAG, body/domain, padding, both axes and authorized target. Empty tokens explicitly have no members.'}

def bind(task,state,candidate,contract):
    by,cs,order=validate(contract,state)
    _hierarchy(contract,cs,order)
    source_view(task,state,contract['source_view'])
    for relation in contract.get('spacing_relations',[]):
        if relation['axis']=='normal':
            from .source_connections import original_annotation_support
            measured=original_annotation_support(task,state,relation['source_observation'])
            if (relation.get('source_ink_geometry')!=measured['source_geometry'] or relation.get('source_line')!=measured['original_line']
                    or relation.get('source_support')!=measured):raise ValueError('Annotation spacing must bind its program-measured unchanged original ink and shaft')
    survey=discovery(task,state,candidate);required={r['object'] for r in survey['candidate_owners']}
    decisions=contract.get('owner_decisions',[])
    if len({r['object'] for r in decisions})!=len(decisions) or {r['object'] for r in decisions}!=required:
        raise ValueError('Every potential body/empty token/primitive needs an explicit original decision')
    for d in decisions:
        if d.get('kind') not in ('container','primitive','text_frame','table') or not d.get('source_evidence'):raise ValueError('Source semantic classification required')
        if d['kind']=='container' and d.get('container') not in cs:raise ValueError('Source container omitted from recursive DAG')
        proposal=next(r for r in survey['candidate_owners'] if r['object']==d['object'])
        enclosed=proposal.get('enclosure_reobservation',[])
        if enclosed and d['kind']=='primitive':
            review=d.get('enclosure_review',{})
            if (review.get('decision')!='independent_overlap' or not review.get('source_evidence')
                    or set(review.get('contained_objects',[]))!=set(enclosed)):
                raise ValueError('Transparent enclosing outline requires source reobservation and complete contained-object decision: '+d['object'])
    from .boundary_geometry import saved_nodes
    native=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size'])
    names={n for r in by.values() for n in r['objects']}|{r['domain']['object'] for r in cs.values() if r['domain']['kind'] in ('native_body','native_table','native_cell')}
    names|={r['domain']['coordinate_owner'] for r in cs.values() if r['domain'].get('coordinate_owner')}
    if not names<=set(native):raise ValueError('Missing actual object binding')
    from .office_math_contract import load as math_contract
    mathematical=math_contract(task,state)
    carriers={r['object']:set(r['graphical_carrier']['members']) for r in (mathematical or {}).get('owners',[]) if r.get('graphical_carrier')}
    for e in by.values():
        if e.get('mathematical_owner') and carriers.get(e['mathematical_owner'])!=set(e['objects']):raise ValueError('A mathematical paint union must bind its entire original graphic carrier and real equation inventory')
    from .native_connection_transaction import verify_anchor
    leaves={n for n,r in native.items() if r['tag']!='grpSp' and not verify_anchor(r)}
    if not leaves<=names:raise ValueError('Every saved leaf must have an original part/body decision: '+','.join(sorted(leaves-names)[:16]))
    from .table_slots import slots
    for name,entry in native.items():
        if entry['tag']!='graphicFrame' or entry['node'].find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}tbl') is None:continue
        tables=[r for r in cs.values() if r['domain']['kind']=='native_table' and r['domain']['object']==name]
        actual=slots(entry)
        cells=[r for r in cs.values() if r['domain']['kind']=='native_cell' and r['domain']['object']==name]
        anchors={str(r['domain']['row'])+':'+str(r['domain']['column']) for r in cells}
        if len(tables)!=1 or len(anchors)!=len(cells) or anchors!=set(actual['slots']):
            raise ValueError('Every actual table and merge anchor must participate in the recursive cell DAG: '+name)
        if {r['id'] for r in cells}!=set(tables[0]['members']):raise ValueError('Table direct members must be its complete source-classified cell set')
    for r in cs.values():
        # Tolerance is computed once from frozen source scale/uncertainty, not
        # widened after failure. Pixel size uncertainty has a strict scale cap.
        source=r['source_bbox'];scale=min(source[2:]);unc=r['target']['source_uncertainty_px']
        if r['target'].get('placement_intent') not in ('center_content','source_layout') or not r['target'].get('placement_evidence'):
            raise ValueError('Every containment level needs original-supported center-or-layout intent before measuring output')
        if unc>max(1.,scale*.03):raise ValueError('Excessive source uncertainty; reidentify the original before binding')
        r['compiled_tolerance_px']=max(.25,min(1.5,scale*.005))+unc
        from .centering_contract import decisions
        r['member_alignment']=decisions(r,by,cs)
    from .layout_tracks import compile_tracks
    contract['alignment_tracks']=compile_tracks(cs,by,(mathematical or {}).get('owners',[]),native)
    file=task/'source/containment'/('contract-'+identity(contract)+'.json');write_json(file,contract)
    state.setdefault('containment_history',[]).append(copy.deepcopy(state.get('recursive_containment')))
    state['recursive_containment']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    state.pop('quality_result',None);state.pop('acceptance',None)
    return {'status':'ORIGINAL_CONTAINMENT_DAG_BOUND','order':order,'containers':len(cs),'elements':len(by),'quality_acceptance':False}

def load(task,state):
    from .execution_contract import resource
    ref=state.get('recursive_containment')
    if not ref:return None
    contract=read_json(resource(task,ref));by,cs,order=validate(contract,state)
    if not state.get('_historical_target_replay'):_hierarchy(contract,cs,order)
    source_view(task,state,contract['source_view']);return contract

def _interior(row,native):
    from .neighbor_geometry import _paths,_stroke
    from .mathml import NS
    domain=row['domain'];padding=domain.get('padding_px',[0,0,0,0])
    if len(padding)!=4:raise ValueError('Four independent interior padding values required')
    if domain['kind']=='logical_polygon':
        points=domain['points']
        if domain.get('coordinate_owner'):
            entry=native[domain['coordinate_owner']];points=[(entry['matrix']@np.array([x,y,1.]))[:2].tolist() for x,y in points]
        g=Polygon(points);stroke=0.
    elif domain['kind'] in ('native_table','native_cell'):
        from .table_slots import slots
        table=slots(native[domain['object']]);frame=table['frame'] if domain['kind']=='native_table' else table['slots'][str(domain['row'])+':'+str(domain['column'])]['bbox']
        x,y,w,h=frame;g=box(x,y,x+w,y+h);stroke=0.
    else:
        entry=native[domain['object']];props=entry['node'].find('p:spPr',NS)
        paths=_paths(entry,props)
        pieces=[Polygon(points) for points,closed,fill in paths if closed and len(points)>=3]
        if len(pieces)!=1 or not pieces[0].is_valid:raise ValueError('Effective custom interior needs one valid closed body; use explicit source logical polygon or actual domain capture')
        stroke=_stroke(entry,props);g=pieces[0].buffer(-stroke/2)
    l,t,r,b=g.bounds;window=box(l+padding[0],t+padding[1],r-padding[2],b-padding[3])
    g=g.intersection(window)
    if g.is_empty or not g.is_valid:raise ValueError('Empty effective interior')
    return g,stroke


def _member_name(element):
    if element.get('mathematical_owner'):return [element['mathematical_owner']]
    if 'table_cell' in element:
        return [element['objects'][0]+'@cell:'+':'.join(map(str,element['table_cell']))]
    return element['objects']

def evaluate(contract,state,paint,native):
    by,cs,order=validate(contract,state);rows=[];unions={};interiors={};measurements={}
    for key in order:
        c=cs[key];base={'id':key,'kind':'recursive_container','direct_members':c['members'],'axes':{},'passed':False,
            'source_bbox':c['source_bbox'],'source_evidence':c['source_evidence'],'measurement_basis':c['target']['measurement_basis']}
        try:
            interior,stroke=_interior(c,native);interiors[key]=interior
            pieces=[];missing=[];member_paint={}
            for m in c['members']:
                if m in cs:
                    # A child participates rigidly with its own body and all
                    # descendants; parent's success cannot close child's axes.
                    child=cs[m];parts=[]
                    if child['domain']['kind'] in ('native_body','native_table'):parts.append(paint[child['domain']['object']]['geometry'])
                    elif child['domain']['kind']=='native_cell':
                        # A real cell participates in its parent as its saved
                        # track/domain body as well as its glyphs. Parent table
                        # checks cannot move all glyphs off their own accepted
                        # cell centers to compensate for a short header row.
                        from .table_slots import slots
                        d=child['domain'];x,y,w,h=slots(native[d['object']])['slots'][str(d['row'])+':'+str(d['column'])]['bbox']
                        parts.append(box(x,y,x+w,y+h))
                    parts.extend(paint[n]['geometry'] for p in child.get('body_parts',[]) for n in by[p]['objects'])
                    if m in unions:parts.append(unions[m])
                    if m not in unions and child['members']:missing.append(m)
                    pieces.extend(parts);member_paint[m]=unary_union(parts) if parts else None
                else:
                    names=_member_name(by[m])
                    if any(n not in paint or paint[n].get('nonpaint') for n in names):missing.append(m)
                    else:
                        shapes=[paint[n]['geometry'] for n in names];pieces.extend(shapes);member_paint[m]=unary_union(shapes)
            if missing:raise ValueError('Unmeasured direct members: '+','.join(missing))
            body_missing=[p for p in c.get('body_parts',[]) if any(n not in paint or paint[n].get('nonpaint') for n in by[p]['objects'])]
            if body_missing:raise ValueError('Unmeasured original body parts: '+','.join(body_missing))
            if not c['members']:
                base.update(passed=True,status='EVIDENCED_NOT_APPLICABLE',reason='Original explicitly empty primitive/container',axes={a:{'id':key+':'+a,'passed':True,'status':'EVIDENCED_NOT_APPLICABLE','reason':'No original content'} for a in ('x','y')});rows.append(base);continue
            if not pieces:raise ValueError('No actual paint for required complete union')
            g=unary_union(pieces)
            if g.is_empty or not g.is_valid:raise ValueError('No nonempty actual painted content for this required member union')
            unions[key]=g;rect=g.bounds;l,t,r,b=rect;dl,dt,dr,db=interior.bounds
            center=np.array(interior.centroid.coords[0] if c['target']['center']=='domain_centroid' else [(dl+dr)/2,(dt+db)/2])
            actual=np.array([(l+r)/2,(t+b)/2]);delta=actual-center;tol=c['compiled_tolerance_px']
            directional=None
            if c['target']['center']=='directional_clearance':
                from .clearance_balance import measure
                directional=measure(g,interior,c['target'].get('target_asymmetry_px',[0.,0.]))
                delta=np.array([directional[a]['actual'] for a in ('x','y')])
            from .centering_contract import joint,decisions
            required=decisions(c,by,cs)
            if c.get('member_alignment')!=required:
                raise ValueError('Complete original direct-member centering decisions must be program-compiled and rebound')
            joint_result=joint(g,interior,tol,c['target'].get('target_asymmetry_px',[0.,0.]))
            member_checks=[]
            for decision in required:
                item=joint(member_paint[decision['member']],interior,tol,axes=decision['required_axes'])
                member_checks.append({**decision,**item})
            if c['target']['center']=='directional_clearance' and c['target'].get('target_asymmetry_px',[0.,0.])==[0.,0.]:
                delta=np.array(joint_result['repair_delta_px'])*-1
            axes={a:{'id':key+':'+a,'passed':abs(float(delta[i]))<=tol,'status':'MEASURED_PASS' if abs(float(delta[i]))<=tol else 'MEASURED_FAIL',
                'target':0.,'actual':float(delta[i]),'tolerance':tol,'unit':'source_px','kind':'directional_clearance_balance' if directional else 'aggregate_center','basis':c['target']['measurement_basis'],'next_action':'containment-check repair' if abs(float(delta[i]))>tol else None,
                **(directional[a] if directional else {})} for i,a in enumerate(('x','y'))}
            if c['target']['center']=='directional_clearance' and c['target'].get('target_asymmetry_px',[0.,0.])==[0.,0.]:
                for axis in ('x','y'):
                    axes[axis]['passed']=joint_result['axes'][axis]['passed']
                    axes[axis]['status']='MEASURED_PASS' if axes[axis]['passed'] else 'MEASURED_FAIL'
                    axes[axis]['center_error_px']=joint_result['axes'][axis]['center_error_px']
                    axes[axis]['actual']=-joint_result['repair_delta_px'][0 if axis=='x' else 1]
            if c['target'].get('placement_intent')=='source_layout':
                for axis in ('x','y'):
                    axes[axis].update(passed=True,status='EVIDENCED_NOT_APPLICABLE',
                        next_action=None,placement_decision='source_layout',placement_evidence=c['target']['placement_evidence'])
            spill=g.difference(interior.buffer(.025));intersection=g.intersection(interior)
            clearance=float(g.distance(interior.boundary)) if interior.covers(g) else -float(g.hausdorff_distance(intersection if not intersection.is_empty else interior))
            span_area=max(g.area,1e-12);overflow=float(spill.area/span_area)
            base.update(status='MEASURED_PASS' if all(v['passed'] for v in axes.values()) and spill.is_empty else 'MEASURED_FAIL',
                axes=axes,passed=all(v['passed'] for v in axes.values()) and spill.is_empty,
                content_union=[l,t,r-l,b-t],domain_bounds=[dl,dt,dr-dl,db-dt],target_center=center.tolist(),
                padding_px=[l-dl,t-dt,dr-r,db-b],net_clearance_px=clearance,stroke_px=stroke,
                overflow_fraction=overflow,whitespace_asymmetry_px=[(l-dl)-(dr-r),(t-dt)-(db-b)],
                source_bias_diagnostic=c.get('source_bias_diagnostic'),directional_clearances=directional,
                joint_center=joint_result,direct_member_centering=member_checks,placement_intent=c['target'].get('placement_intent'),
                measurement_methods=sorted({paint[n]['method'] for m in c['members'] if m in by for n in _member_name(by[m])}))
            if not all(item['passed'] for item in member_checks):
                base.update(passed=False,own_geometry_pass=False,status='MEASURED_FAIL',next_action='direct_member_layout_repair')
            measurements[key]=(delta,center,rect)
        except (ValueError,KeyError,TypeError) as exc:
            base.update(status='required_unmeasured',reason=str(exc),axes={a:{'id':key+':'+a,'passed':False,'status':'required_unmeasured','reason':str(exc)} for a in ('x','y')})
        rows.append(base)
    axes=[v for r in rows for v in r['axes'].values()]
    for row in rows:
        children=[next(v for v in rows if v['id']==m) for m in cs[row['id']]['members'] if m in cs]
        row['descendant_closure']=all(v['passed'] for v in children)
        row['own_geometry_pass']=row['passed']
        row['passed']&=row['descendant_closure']
    native_required={n for e in by.values() for n in e['objects']}|{c['domain']['object'] for c in cs.values() if c['domain'].get('object')}
    from .layout_tracks import report as lane_report
    lane=lane_report(contract.get('alignment_tracks',[]),cs,native,paint)
    return {'schema':VERSION,'passed':all(r['passed'] for r in rows) and lane['passed'],'status':'PASS' if all(r['passed'] for r in rows) and lane['passed'] else 'WORK_REQUIRED',
        'alignment_tracks':lane,
        'items':rows,'order':order,'containment_tree':{n:cs[n]['members'] for n in cs},
        'coverage':{'objects':{'observed':len({n for n in native_required if n in paint}),'required':len(native_required)},'declared_relations':{'observed':sum(len(r['members']) for r in cs.values()),'required':sum(len(r['members']) for r in cs.values())},
         'required_measurements':{'measured':sum(v['status'].startswith('MEASURED') or v['status']=='EVIDENCED_NOT_APPLICABLE' for v in axes),'required':2*len(cs)},
         'hard_pass':{'passed':sum(v['passed'] for v in axes),'required':len(axes)}},'quality_acceptance':False}

def report(task,state,candidate):
    contract=load(task,state)
    if contract is None:return {'schema':VERSION,'passed':False,'status':'SOURCE_BINDING_REQUIRED','items':[],'next':'containment-check discover'}
    from . import neighbor_geometry as ng
    from .boundary_geometry import saved_nodes
    paint,errors=ng.read(task,state,candidate,state.get('neighbor_mattes'))
    native=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size'])
    from .table_cell_capture import read as cell_paint
    for e in contract['elements']:
        if 'table_cell' not in e:continue
        name=_member_name(e)[0]
        try:paint[name]=cell_paint(task,state,candidate,name,native)
        except (ValueError,KeyError,FileNotFoundError) as exc:errors.append({'object':name,'reason':str(exc),'next':'containment-check capture'})
    result=evaluate(contract,state,paint,native);result.update(source_hash=state['source']['sha256'],pptx_hash=candidate['pptx']['sha256'],contract=state['recursive_containment'])
    result['spacing_items']=spacing_measurements(contract,paint,native)
    result['passed']&=all(r['passed'] for r in result['spacing_items'])
    result['status']='PASS' if result['passed'] else 'WORK_REQUIRED'
    involved={n for e in contract['elements'] for n in e['objects']}
    result['capture_required']=[r for r in errors if r['object'] in involved or '@cell:' in r['object']]
    from .contextual_layout import windows
    result['context_views']=windows(task,state,candidate,contract,native)
    result['passed']&=result['context_views']['passed']
    result['status']='PASS' if result['passed'] else 'WORK_REQUIRED'
    return result

def spacing_target(relation,canvas):
    if relation.get('axis')=='normal':
        if relation['rule']!='source_line_annotation_clearance' or relation.get('side') not in (-1,1):raise ValueError('Original annotation side and rule required')
        points=np.array(relation.get('source_line'),float)
        if points.shape!=(2,2) or not np.isfinite(points).all() or np.linalg.norm(points[1]-points[0])<.001:raise ValueError('Finite original incident annotation line required')
        b=relation['source_bounds']['after'];x,y,w,h=b
        d=points[1]-points[0];normal=np.array([-d[1],d[0]])/np.linalg.norm(d)*relation['side']
        if relation.get('source_ink_geometry'):
            from shapely import wkt
            from shapely.affinity import affine_transform
            g=wkt.loads(relation['source_ink_geometry'])
            if g.is_empty or not g.is_valid:raise ValueError('Original annotation ink geometry is invalid')
            gap=float(affine_transform(g,[normal[0],normal[1],-normal[1],normal[0],-float(points[0]@normal),0]).bounds[0])
        else:gap=float(min((np.array([x+dx*w,y+dy*h])-points[0])@normal for dx,dy in ((0,0),(1,0),(1,1),(0,1))))
        if gap<0:raise ValueError('Original annotation envelope crosses its claimed side; refine the source reading')
        return max(gap,float(max(1,round(max(canvas)*.002))))
    if relation['rule']!='source_gap_with_readability_floor':raise ValueError('Unsupported deterministic spacing rule')
    a,b=relation['source_bounds']['before'],relation['source_bounds']['after']
    if any(len(v)!=4 or min(v[2:])<=0 or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in v) for v in (a,b)):
        raise ValueError('Independent finite original painted envelopes required')
    axis=0 if relation['axis']=='x' else 1
    return max(0.,b[axis]-a[axis]-a[axis+2],float(max(1,round(max(canvas)*.002))))

def spacing_measurements(contract,paint,native=None):
    rows=[]
    for relation in contract.get('spacing_relations',[]):
        row={'id':relation['id'],'passed':False,'axis':relation['axis'],'minimum_gap_px':relation['minimum_gap_px']}
        try:
            before=unary_union([paint[n]['geometry'] for n in relation['before']]);after=unary_union([paint[n]['geometry'] for n in relation['after']])
            if before.is_empty or after.is_empty:raise ValueError('Spacing requires actual visible ink on both sides')
            normal=None
            if relation['axis']=='normal':
                from .connection_geometry import line
                if native is None or len(relation['before'])!=1:raise ValueError('One measured native incident path required')
                path=line(native[relation['before'][0]])
                points=np.array(path['segments'][relation.get('segment',0)] if path['segments'] else path['points'])
                if points.shape in ((3,2),(4,2)):
                    from .source_connections import annotation_axis
                    points=np.array(annotation_axis(path['segments'],[0,0],relation['source_support']['parameter'])[0])
                if points.shape!=(2,2):raise ValueError('Annotation normal needs a registered straight incident segment')
                d=points[1]-points[0];normal=np.array([-d[1],d[0]])/np.linalg.norm(d)*relation['side']
                from shapely.affinity import affine_transform
                gap=float(affine_transform(after,[normal[0],normal[1],-normal[1],normal[0],-float(points[0]@normal),0]).bounds[0])
                row['normal']=normal.tolist()
            else:
                axis=0 if relation['axis']=='x' else 1
                gap=after.bounds[axis]-before.bounds[axis+2]
            row.update(actual_gap_px=gap,euclidean_boundary_distance_px=before.distance(after),
                overlap_area_px2=before.intersection(after).area,passed=gap>=relation['minimum_gap_px']-.025,status='MEASURED')
        except (KeyError,ValueError) as error:row.update(status='required_unmeasured',reason=str(error))
        rows.append(row)
    return rows

def spacing_plan(task,state,candidate,request):
    from .boundary_geometry import saved_nodes
    from . import neighbor_geometry as ng
    contract=load(task,state);native=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size'])
    paint,errors=ng.read(task,state,candidate,state.get('neighbor_mattes'));by={r['id']:r for r in contract.get('spacing_relations',[])}
    requested=request.get('spacing_relations',[])
    if not requested or len(set(requested))!=len(requested) or not set(requested)<=set(by):raise ValueError('Exact current original spacing relation selection required')
    measurements={r['id']:r for r in spacing_measurements(contract,paint,native)};translations={};grants=request.get('write_set',{})
    for key in requested:
        r=by[key];m=measurements[key];axis=r['axis']
        if m['status']!='MEASURED':raise ValueError('Capture complete current owner ink before spacing repair')
        delta=max(0.,r['minimum_gap_px']-m['actual_gap_px'])
        if delta>request.get('max_translation_px',0):raise ValueError('Spacing correction exceeds authorized movement')
        for n in r['after']:
            required=['position.x','position.y'] if axis=='normal' else ['position.'+axis]
            if not set(required)<=set(grants.get(n,[])):raise ValueError('Spacing repair lacks narrow placement grant')
            if n in translations:raise ValueError('Shared spacing owner requires a coupled layout solver')
            translations[n]={'x':delta*m['normal'][0],'y':delta*m['normal'][1]} if axis=='normal' else {'x':delta if axis=='x' else 0.,'y':delta if axis=='y' else 0.}
    if not any(max(abs(v) for v in d.values())>.025 for d in translations.values()):raise ValueError('No effective spacing repair')
    # Prevent solving one gap by introducing a fresh overlap anywhere else.
    for name,d in translations.items():
        original=paint[name]['geometry'];predicted=translate(original,xoff=d['x'],yoff=d['y'])
        for other,row in paint.items():
            if other==name or row.get('nonpaint') or row['geometry'].is_empty:continue
            od=translations.get(other,{'x':0.,'y':0.})
            target=translate(row['geometry'],xoff=od['x'],yoff=od['y'])
            if predicted.intersection(target).area>original.intersection(row['geometry']).area+.1:
                raise ValueError('Spacing creates a new overlap with '+other+'; coupled/source layout decision required')
    return {'kind':VERSION,'source_contract':state['recursive_containment'],'spacing_relations':requested,
        'translations':translations,'write_set':{n:['position.'+axis for axis in ('x','y') if translations[n][axis]!=0.] for n in translations},
        'check_set':[r['id'] for r in contract['containers']]+sorted(by),'protected_set':sorted(set(native)-set(translations)),
        'solver':'Original-associated opposing painted boundaries; rigid movement only', 'before_check':list(measurements.values())}

def _single_repair_plan(task,state,candidate,request,_context=None):
    """One deepest failing container per actual iteration; rigid subtree move."""
    contract=load(task,state);check=_context[0] if _context else report(task,state,candidate);by,cs,order=validate(contract,state)
    actual={r['id']:r for r in check['items']}
    eligible=[k for k in order if not actual[k]['own_geometry_pass'] and not any(m in cs and not actual[m]['passed'] for m in cs[k]['members'])]
    key=request.get('container') or next(iter(eligible),None)
    if key is None:raise ValueError('All containers already centered; no zero-action rewrite')
    if key not in eligible:raise ValueError('Repair a current failing inner-ready container before its unresolved ancestors')
    row=next(r for r in check['items'] if r['id']==key)
    if row['status']=='required_unmeasured':raise ValueError('Missing effective interior/member measurement must be resolved first')
    delta={a:-row['axes'][a]['actual'] for a in ('x','y')}
    roots=set();cell_members={}
    def members(k):
        pending=[k];seen=set()
        while pending:
            u=pending.pop()
            if u in seen:continue
            seen.add(u)
            for m in cs[u]['members']:
                if m in cs:
                    if cs[m]['domain']['kind'] in ('native_body','native_table'):roots.add(cs[m]['domain']['object'])
                    roots.update(n for p in cs[m].get('body_parts',[]) for n in by[p]['objects'])
                    pending.append(m)
                else:
                    if 'table_cell' in by[m]:cell_members[m]=by[m]
                    else:roots.update(_member_name(by[m]))
    failing_member=next((v for v in row.get('direct_member_centering',[]) if not v['passed']),None)
    if failing_member:
        selected=failing_member['member'];delta=dict(zip(('x','y'),failing_member['repair_delta_px']))
        if selected in cs:
            if cs[selected]['domain']['kind'] in ('native_body','native_table'):roots.add(cs[selected]['domain']['object'])
            roots.update(n for p in cs[selected].get('body_parts',[]) for n in by[p]['objects'])
            members(selected)
        elif 'table_cell' in by[selected]:cell_members[selected]=by[selected]
        else:roots.update(_member_name(by[selected]))
    else:members(key)
    required_cells={_member_name(e)[0] for e in cell_members.values()}
    cell_members={m:e for m,e in cell_members.items() if e['objects'][0] not in roots}
    from .boundary_geometry import saved_nodes
    native=_context[2] if _context else saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size'])
    # Avoid double moving descendants of an already selected native group.
    def under(n):
        p=native[n]['parent_name']
        while p:
            if p in roots:return True
            p=native[p]['parent_name']
        return False
    roots={n for n in roots if not under(n)}
    # Missing evidence in an independent subtree must not block this branch.
    # Every native descendant of a moving owner is still a prerequisite; a
    # partially measured group union cannot authorize moving that group.
    relevant=set(roots)|required_cells
    for name,entry in native.items():
        parent=name
        while parent:
            if parent in roots:relevant.add(name);break
            parent=native[parent]['parent_name']
    if any(r['object'] in relevant for r in check['capture_required']):
        raise ValueError('Execute actual owner capture for this complete moving subtree before computing centering')
    grant=request.get('write_set',{})
    if any(not {'position.x','position.y'}<=set(grant.get(n,[])) for n in roots):raise ValueError('Related/check scope does not grant every subtree position write')
    if any('cell_content_offset' not in grant.get(_member_name(e)[0],[]) for e in cell_members.values()):raise ValueError('Every native cell glyph movement requires an explicit cell_content_offset grant')
    if max(abs(v) for v in delta.values())>request.get('max_translation_px',0):raise ValueError('Source-derived shift exceeds explicit authorized movement budget')
    # Evaluate the actual nonrectangular interior, not its bounding box.
    from . import neighbor_geometry as ng
    paint=_context[1] if _context else ng.read(task,state,candidate,state.get('neighbor_mattes'))[0]
    geometry=[]
    for n in roots:
        if n not in paint or paint[n].get('nonpaint'):raise ValueError('Missing complete moving owner paint: '+n)
        geometry.append(paint[n]['geometry'])
    if cell_members:
        from .table_cell_capture import read as cell_paint
        for e in cell_members.values():
            geometry.append(cell_paint(task,state,candidate,_member_name(e)[0],native)['geometry'])
    interior,_=_interior(cs[key],native)
    predicted=translate(unary_union(geometry),xoff=delta['x'],yoff=delta['y'])
    if not interior.buffer(.025).covers(predicted):raise ValueError('Rigid centering cannot cure overflow in the actual interior; bounded sizing/layout repair required')
    l,t,w,h=row['content_union'];dl,dt,dw,dh=row['domain_bounds']
    if l+delta['x']<dl-.025 or t+delta['y']<dt-.025 or l+w+delta['x']>dl+dw+.025 or t+h+delta['y']>dt+dh+.025:
        raise ValueError('Rigid centering cannot cure oversized content; bounded scaling/layout repair required')
    return {'kind':VERSION,'container':key,'source_contract':state['recursive_containment'],'translations':{n:delta for n in sorted(roots)},
        'cell_offsets':{_member_name(e)[0]:{'object':e['objects'][0],'cell':e['table_cell'],'delta':delta,
            'content_size_px':[cell_paint(task,state,candidate,_member_name(e)[0],native)['geometry'].bounds[2]-cell_paint(task,state,candidate,_member_name(e)[0],native)['geometry'].bounds[0],
                               cell_paint(task,state,candidate,_member_name(e)[0],native)['geometry'].bounds[3]-cell_paint(task,state,candidate,_member_name(e)[0],native)['geometry'].bounds[1]],
            'margin_policy':'minimal_nonnegative_envelope'} for e in cell_members.values()},
        'write_set':{**{n:['position.x','position.y'] for n in roots},**{_member_name(e)[0]:['cell_content_offset'] for e in cell_members.values()}},'check_set':order,'protected_set':sorted(set(native)-roots-{e['objects'][0] for e in cell_members.values()}),
        'before_check':check,'next':'actual render; capture current owner ink; recheck every level and external relationships'}

def _body_fit_plan(task,state,candidate,request):
    contract=load(task,state);by,cs,order=validate(contract,state);key=request['container'];child=cs[key]
    parents=[p for p,c in cs.items() if key in c['members']]
    if len(parents)!=1 or child['domain']['kind']!='native_body':raise ValueError('Body fit needs one original direct parent and one editable physical body')
    name=child['domain']['object']
    if not {'geometry.width','geometry.height','position.x','position.y'}<=set(request.get('write_set',{}).get(name,[])):
        raise ValueError('A geometry diagnosis does not grant body resizing; explicit narrow body dimensions/position grant required')
    loss=request.get('max_scale_loss',0)
    if not 0<loss<=.1:raise ValueError('Freeze a bounded body fitting scale loss before execution')
    from .boundary_geometry import saved_nodes
    from . import neighbor_geometry as ng
    native=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size']);entry=native[name]
    if abs(entry['matrix'][0,1])+abs(entry['matrix'][1,0])>1e-12 or entry['tag']!='sp':raise ValueError('Rotated/custom bodies require the established pose/actual domain solver; no nominal-frame substitution')
    interior,_=_interior(cs[parents[0]],native);_,stroke=_interior(child,native);dl,dt,dr,db=interior.bounds
    x,y,w,h=entry['frame'];width=min(w,dr-dl-stroke-.1);height=min(h,db-dt-stroke-.1)
    if min(width/w,height/h)<1-loss:raise ValueError('Required body shrink exceeds its explicit bounded grant')
    if width==w and height==h:raise ValueError('No body fit is needed; resolve membership/other geometry before resizing')
    frame=[x+(w-width)/2,y+(h-height)/2,width,height]
    return {'kind':VERSION,'container':key,'source_contract':state['recursive_containment'],'body_sizes':{name:frame},'translations':{},'cell_offsets':{},
      'write_set':{name:['geometry.width','geometry.height','position.x','position.y']},'check_set':order,'protected_set':sorted(set(native)-{name}),
      'source_parent':parents[0],'next':'Save/render; recheck this body, full contents and both ancestor/descendant axes; no acceptance from a predicted fit'}

def repair_plan(task,state,candidate,request):
    if request.get('operation')=='align_tracks':
        from .layout_tracks import repair_plan as tracks_plan
        from .boundary_geometry import saved_nodes
        return tracks_plan(task,state,candidate,request,load(task,state),saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size']))
    if request.get('operation')=='fit_child_body':return _body_fit_plan(task,state,candidate,request)
    keys=request.get('containers')
    if keys is None:return _single_repair_plan(task,state,candidate,request)
    if not keys or len(keys)>16 or len(keys)!=len(set(keys)):
        raise ValueError('A finite parallel layout batch contains 1..16 distinct inner-ready containers')
    from . import neighbor_geometry as ng
    from .boundary_geometry import saved_nodes
    context=(report(task,state,candidate),ng.read(task,state,candidate,state.get('neighbor_mattes'))[0],
             saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size']))
    plans=[_single_repair_plan(task,state,candidate,{**request,'container':key},context) for key in keys]
    translations={};cells={};writes={}
    for plan in plans:
        if set(translations)&set(plan['translations']) or set(cells)&set(plan['cell_offsets']):
            raise ValueError('Batch containers share movable members; use one coupled bounded layout transaction')
        translations.update(plan['translations']);cells.update(plan['cell_offsets']);writes.update(plan['write_set'])
    table_owners={r['object'] for r in cells.values()}
    if table_owners&set(translations):raise ValueError('Do not double-move table bodies and their cell glyphs in one batch')
    return {**plans[0],'containers':keys,'container':None,'translations':translations,'cell_offsets':cells,'write_set':writes,
        'protected_set':sorted(set(plans[0]['protected_set'])&set.intersection(*(set(p['protected_set']) for p in plans))),
        'solver':'Exact independent inner-ready rigid translations; shared-owner and ancestor batches rejected'}

def capture_current(task,state,candidate):
    from .neighbor_capture import capture_missing
    result=capture_missing(task,state,candidate)
    check=report(task,state,candidate)
    cells=sorted({r['object'] for r in check.get('capture_required',[]) if '@cell:' in r['object']})
    if cells:
        from .table_cell_capture import capture
        table=cells[0].split('@cell:')[0]
        result['cell_capture']=capture(task,state,candidate,[c for c in cells if c.split('@cell:')[0]==table][:12])
    return result

def dispatch(task,operation,request=None):
    from . import agent_runtime as a
    task,state=a._state(task);candidate=state.get('active_candidate') or state.get('selected');request=request or {}
    if operation=='discover':return discovery(task,state,candidate)
    if operation=='report':return report(task,state,candidate)
    if operation=='repair':
        if request.get('baseline_hash')!=candidate['pptx']['sha256']:raise ValueError('Bind exact current native result')
        plan=spacing_plan(task,state,candidate,request) if request.get('spacing_relations') else repair_plan(task,state,candidate,request)
        from .target_actions import execute
        return execute(task,state,candidate,plan,request)
    if operation=='capture':
        result=capture_current(task,state,candidate)
    elif operation=='bind':result=bind(task,state,candidate,copy.deepcopy(request))
    else:raise ValueError('Unknown containment operation')
    with writer(task):a._save(task,state)
    return result
