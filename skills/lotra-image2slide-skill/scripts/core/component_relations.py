"""Executable assembly/placement relations on saved native geometry."""
import math
from .common import read_json, safe_path, digest, identity, read_json


def _source_frame_bounds(node, ranges):
    """Compare rotated frames in the same domain; keep frozen uncertainty."""
    from itertools import product
    # Imported snapshot boxes already use the saved world AABB. Generated
    # recipes use unrotated local frames; do not rotate an imported AABB twice.
    imported = bool(node.get('content',{}).get('native_snapshot'))
    angle = 0. if imported else math.radians(float(node.get('style', {}).get('rotation', 0)))
    cosine, sine = abs(math.cos(angle)), abs(math.sin(angle))
    def frame(box):
        x, y, width, height = box
        w, h = cosine*width+sine*height, sine*width+cosine*height
        return [x+(width-w)/2, y+(height-h)/2, w, h]
    target = frame(node['bbox'])
    corners = [frame(box) for box in product(*(ranges.get(i, (v, v)) for i, v in enumerate(node['bbox'])))]
    return target, [(min(c[i] for c in corners), max(c[i] for c in corners)) for i in range(4)]


def source_placement(task,state,candidate,contract):
    """Final layout compares actual leaf frames with the frozen source plan.

    A valid imported group transform is not proof of source placement. Tunable
    field intervals remain those frozen before fitting, never candidate-derived.
    """
    from .boundary_geometry import saved_nodes
    frames=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size'])
    source=read_json(safe_path(task,contract['source_scene']['path']))
    if digest(safe_path(task,contract['source_scene']['path']))!=contract['source_scene']['sha256']:
        raise ValueError('Original layout plan changed')
    expected={n['id']:n for n in source['objects']};rows=[]
    for component in contract['components']:
        tolerance=component.get('pose_tolerance_source_px',.5)
        if tolerance<0 or tolerance>1.5 or tolerance!=.5 and not component.get('pose_tolerance_evidence'):
            raise ValueError('Original-supported final placement tolerance required, within 1.5 source pixels')
        ranges={}
        for name,binding in component.get('fit',{}).get('bindings',{}).items():
            parameter=component.get('parameters',{}).get(name,{})
            if parameter.get('state')=='tunable' and binding['field'][0]=='bbox':
                ranges[(binding['owner'],binding['field'][1])]=parameter['bounds']
        for owner in component['owners']:
            if expected[owner]['render_type']=='group':continue
            actual=frames.get(owner,{}).get('frame');wanted=expected[owner]['bbox'];checks=[]
            intervals = None
            if contract.get('workflow_version') in ('1.35.0','1.35.1'):
                wanted, intervals = _source_frame_bounds(expected[owner], {i:v for (name,i),v in ranges.items() if name==owner})
            if actual is not None:
                for index,(observed,target) in enumerate(zip(actual,wanted)):
                    low,high=intervals[index] if intervals is not None else ranges.get((owner,index),(target,target))
                    checks.append(low-tolerance<=observed<=high+tolerance)
            rows.append({'owner':owner,'component':component['id'],'passed':bool(checks) and all(checks),
                         'actual_native_frame':actual,'original_frame':wanted,'tolerance_source_px':tolerance})
    return {'passed':bool(rows) and all(r['passed'] for r in rows),'items':rows,
            'measurement':'Actual transformed native frames in original coordinates; painted visibility is a separate final visual judgment'}


def _anchor(frame, axis, anchor):
    offset = 0 if axis == 'x' else 1
    return frame[offset] + {'min': 0., 'center': .5, 'max': 1.}[anchor] * frame[offset+2]


def evaluate(task, state, candidate, contract, relation_ids=None, expected_instances=None):
    from .boundary_geometry import saved_nodes
    from .native_core_inspect import xml, inventory
    from .mathml import NS
    source = safe_path(task, candidate['pptx']['path'])
    if digest(source) != candidate['pptx']['sha256']: raise ValueError('Relation input changed')
    frames = saved_nodes(source, state['source_size'])
    native, duplicate = inventory(xml(source))
    if duplicate: raise ValueError('Ambiguous native relationship owner')
    # Group envelopes are explicitly native-frame measurements. Painted
    # containment uses descendant paint below and cannot use these envelopes.
    for owner, entry in reversed(list(frames.items())):
        if entry['tag'] != 'grpSp': continue
        children = [v['frame'] for v in frames.values() if v.get('parent_name') == owner and v.get('frame') is not None]
        if children:
            x = min(f[0] for f in children); y = min(f[1] for f in children)
            entry['frame'] = [x, y, max(f[0]+f[2] for f in children)-x,
                              max(f[1]+f[3] for f in children)-y]
    components = {row['id']: row for row in contract['components']}
    relations = contract.get('relations', [])
    if relation_ids is not None:
        selected = set(relation_ids)
        if selected - {row['id'] for row in relations}: raise ValueError('Unknown relation selection')
        relations = [row for row in relations if row['id'] in selected]
    paint = None; rows = {}; connection_report = None
    for relation in relations:
        key = relation['id']; kind = relation['kind']
        if kind == 'instance_of' and components[relation['components'][1]].get('spatial_instance',{}).get('route') == 'reproject_constructor':
            from .spatial_constructors import instance_check
            rows[key] = instance_check(task,state,candidate,contract,components[relation['components'][1]])
            continue
        owners = relation.get('owners')
        if owners is None:
            owners = [components[name]['owners'][0] for name in relation['components']]
        if len(owners) != 2 or any(owner not in frames for owner in owners):
            rows[key] = {'passed': False, 'valid': False, 'reason': 'Exact two native owners required'}; continue
        a, b = owners; values = {}; valid = True; good = False
        measurement = relation.get('measurement', 'native_frame')
        fa, fb = frames[a].get('frame'), frames[b].get('frame')
        if kind in ('contains', 'contact') and measurement == 'painted':
            if paint is None:
                from .neighbor_geometry import read
                paint, paint_errors = read(task, state, candidate)
            pa, pb = paint.get(a, {}), paint.get(b, {})
            ga, gb = pa.get('geometry'), pb.get('geometry')
            if ga is None or gb is None or ga.is_empty or gb.is_empty:
                valid = False; values = {'reason': 'Actual painted geometry required'}
            elif kind == 'contains':
                tolerance = relation.get('tolerance_source_px', .5)
                outside = gb.difference(ga.buffer(tolerance)).area / max(gb.area, 1e-12)
                good = outside <= relation.get('maximum_outside_fraction', 0.)
                values = {'outside_fraction': outside, 'tolerance_source_px': tolerance}
            else:
                distance = ga.distance(gb); good = distance <= relation.get('tolerance_source_px', .5)
                values = {'distance_source_px': distance}
        elif kind in ('contains', 'contact', 'gap', 'align_x', 'align_y'):
            if fa is None or fb is None or frames[a].get('error') or frames[b].get('error'):
                valid = False; values = {'reason': 'Saved frame unavailable'}
            else:
                tolerance = relation.get('tolerance_source_px', .5)
                if kind == 'contains':
                    x,y,w,h=fa;u,v,s,t=fb
                    good = u >= x-tolerance and v >= y-tolerance and u+s <= x+w+tolerance and v+t <= y+h+tolerance
                    values = {'outer_native_frame': fa, 'inner_native_frame': fb}
                elif kind in ('align_x', 'align_y'):
                    axis = kind[-1]
                    delta = _anchor(fa, axis, relation.get('a_anchor','center')) - _anchor(fb,axis,relation.get('b_anchor','center'))
                    error = abs(delta-relation.get('expected_offset',0.))
                    good = error <= tolerance; values = {'anchor_error_source_px': error}
                else:
                    axis = relation.get('axis')
                    if axis not in ('x','y'): raise ValueError('Gap/contact requires an original-supported axis')
                    gap = _anchor(fb, axis, relation.get('b_anchor','min')) - _anchor(fa, axis, relation.get('a_anchor','max'))
                    low = relation.get('min', -tolerance if kind=='contact' else None)
                    high = relation.get('max', tolerance if kind=='contact' else None)
                    if low is None or high is None: raise ValueError('Freeze source gap interval')
                    good = low <= gap <= high; values = {'gap_source_px': gap, 'min': low, 'max': high}
        elif kind == 'layer_before':
            sequence = list(native); good = sequence.index(a) < sequence.index(b)
            values = {'behind': sequence.index(a), 'front': sequence.index(b)}
        elif kind == 'connects':
            connector = relation.get('connector')
            node = native.get(connector, {}).get('node')
            if node is None:
                valid = False; values = {'reason': 'Actual connector absent'}
            else:
                endpoints = [node.find('.//a:'+tag, NS) for tag in ('stCxn','endCxn')]
                expected = [native[owner]['id'] for owner in owners]
                observed = [end.get('id') if end is not None else None for end in endpoints]
                good = observed == expected; values = {'expected_ids': expected, 'saved_ids': observed}
                if state.get('connection_contract'):
                    if connection_report is None:
                        from .connection_geometry import report
                        connection_report=report(task,state,candidate)
                    matched=[r for r in connection_report['items'] if connector in r['objects']]
                    actual_geometry=bool(matched) and all(r['passed'] for r in matched) and connection_report.get('source_integrity',{}).get('passed') is True
                    good=good and actual_geometry;values['actual_connection_checks']=matched
                elif relation.get('source_endpoints'):
                    import numpy as np
                    from .connection_geometry import line
                    observed_points=np.array(line(frames[connector])['points'])[[0,-1]]
                    expected_points=np.asarray(relation['source_endpoints'],float)
                    if expected_points.shape!=(2,2):raise ValueError('Freeze exactly two original endpoint coordinates')
                    error=float(np.linalg.norm(observed_points-expected_points,axis=1).max())
                    good=good and error<=relation.get('tolerance_source_px',.5)
                    values['endpoint_error_source_px']=error
                else:
                    valid=False;values['reason']='Actual endpoint/physical geometry requires frozen source endpoints or the established connection contract'
        elif kind == 'instance_of':
            instance = components[relation['components'][1]]
            transform = instance.get('instance_transform', {})
            mapping = transform.get('owner_map', {})
            import numpy as np
            from copy import deepcopy
            from lxml import etree as E
            matrix = np.asarray(transform.get('matrix', []), dtype=float)
            if matrix.shape != (3, 3) or not np.isfinite(matrix).all() or not mapping or not np.allclose(matrix[2], [0,0,1]):
                valid = False; values = {'reason': 'Complete mother/instance owner map and source affine transform required'}
            else:
                mother_root,copy_root=owners
                mother_members={name for name in native if name==mother_root or native[name]['node'] in native[mother_root]['node'].iterdescendants()}
                copy_members={name for name in native if name==copy_root or native[name]['node'] in native[copy_root]['node'].iterdescendants()}
                if set(mapping)!=mother_members or set(mapping.values())!=copy_members or len(set(mapping.values()))!=len(mapping):
                    valid=False
                expected=(expected_instances or {}).get(instance['id'])
                if expected is None:
                    from . import component_workflow as c
                    _,instance_ledger=c._load(task,state)
                    ref=instance_ledger['components'][instance['id']].get('instantiation',{}).get('expectation')
                    if ref:expected=read_json(c._resource(task,ref))
                reference_frames=frames
                if expected:
                    from .component_variants import native_body
                    from . import component_workflow as c
                    if expected.get('component_contract')!=identity(instance):valid=False
                    if expected.get('font_binding_signature') is not None:
                        from .component_font_instances import signature as font_signature
                        if expected['font_binding_signature']!=font_signature(read_json(c._resource(task,candidate['scene'])),instance):valid=False
                    if any(native_body(native[name]['node'])!=value for name,value in expected['original_bodies'].items()):valid=False
                    reference_frames=saved_nodes(c._resource(task,expected['source_package']),state['source_size'])
                elif instance.get('variant') or instance.get('scale_policy')=='scale_with_geometry':
                    valid=False
                def body(name):
                    n = deepcopy(native[name]['node'])
                    for child in list(n):
                        if E.QName(child).localname in ('sp','grpSp','cxnSp','pic','graphicFrame'): n.remove(child)
                    for xf in n.xpath('.//a:xfrm|./p:xfrm', namespaces=NS): xf.getparent().remove(xf)
                    for pr in n.xpath('.//p:cNvPr', namespaces=NS):
                        pr.attrib.pop('id', None); pr.attrib.pop('name', None)
                    return E.tostring(n, method='c14n')
                errors = []; mismatches = []; corners = np.array([[0,0,1],[1,0,1],[1,1,1],[0,1,1]]).T
                for mother_owner, copy_owner in mapping.items():
                    if mother_owner not in frames or copy_owner not in frames:
                        valid = False; continue
                    expected_body=expected['expected_bodies'][mother_owner] if expected else body(mother_owner)
                    actual_body=native_body(native[copy_owner]['node']) if expected else body(copy_owner)
                    if expected_body!=actual_body:mismatches.append(copy_owner)
                    fm, fc = reference_frames[mother_owner], frames[copy_owner]
                    if fm['matrix'] is None or fc['matrix'] is None: valid = False; continue
                    if fm['tag'] != 'grpSp':
                        errors.extend(np.linalg.norm(((fc['matrix']-matrix@fm['matrix'])@corners)[:2],axis=0).tolist())
                tolerance = transform.get('tolerance_source_px', .5)
                good = (instance.get('mother') == relation['components'][0] and not mismatches and
                        bool(errors) and max(errors) <= tolerance)
                values = {'mother': instance.get('mother'), 'body_mismatches': mismatches,
                          'maximum_transform_error_source_px': max(errors) if errors else None,
                          'tolerance_source_px': tolerance}
        elif kind == 'label_for':
            literal = ''.join(native[a]['node'].xpath('.//a:t/text()',namespaces=NS))
            expected = relation.get('text')
            if expected is None: raise ValueError('Freeze source label literal')
            good = literal == expected; values = {'actual_text': literal, 'expected_text': expected}
        elif kind == 'intentional_overlap':
            if fa is None or fb is None: valid = False
            else:
                x,y,w,h=fa;u,v,s,t=fb
                good = min(x+w,u+s) >= max(x,u) and min(y+h,v+t) >= max(y,v)
                values = {'first_frame': fa, 'second_frame': fb}
        else: raise ValueError('Unsupported relation '+kind)
        rows[key] = {'passed': bool(valid and good), 'valid': valid, 'kind': kind,
                     'measurement': measurement, 'owners': owners, **values}
    return {'passed': all(row['passed'] for row in rows.values()), 'items': rows,
            'source_hash': state['source']['sha256'], 'pptx_hash': candidate['pptx']['sha256'],
            'basis': identity({'relations': relations, 'candidate': candidate['pptx']})}
