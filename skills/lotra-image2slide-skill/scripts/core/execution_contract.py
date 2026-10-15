"""Whole-drawing coverage and the single final acceptance receipt.

Write permission never restricts this inventory. Legacy flags, a smaller Scene,
and an unchanged defective subtree cannot remove a program obligation.
"""
import copy
from pathlib import Path
from lxml import etree as E
from .common import digest, identity, read_json, safe_path, write_json, ROOT
from .mathml import NS

VERSION='execution-contract-1'
MANDATORY=('source_part_quality','source_relative_layout','source_textbox_quality',
           'source_semantic_composition','source_feature_ledger','source_font_contract',
           'portable_editable_fonts','source_frame_plan','whole_quality_intent','source_contract_seals','all_neighbor_closure')


def policy(state):
    disabled=[k for k in MANDATORY if state.get('objectives',{}).get(k) is not True]
    if disabled or state.get('execution_contract')!=VERSION:
        raise ValueError('Whole-drawing execution policy required. Migrate/import the complete original/native task; '
                         'legacy scoped states cannot continue as accepted. Missing: '+repr(disabled))


def resource(task,ref):
    p=safe_path(task,ref['path'])
    if not p.is_file() or digest(p)!=ref['sha256']:raise ValueError('Execution dependency changed: '+ref['path'])
    return p


def inventory(task,state,candidate):
    from .boundary_geometry import saved_nodes
    from .table_slots import picture_candidates, slots
    pptx=resource(task,candidate['pptx']);scene=read_json(resource(task,candidate['scene']))
    nodes=saved_nodes(pptx,state['source_size'])
    parents={}
    for name,e in nodes.items():
        parents[name]=e['parent_name']
    from .native_connection_transaction import verify_anchor
    derived={n for n,e in nodes.items() if verify_anchor(e)}
    groups={n:sorted(v for v in nodes if v!=n and _descendant(v,n,parents) and nodes[v]['tag']!='grpSp' and v not in derived)
            for n,e in nodes.items() if e['tag']=='grpSp'}
    content=[];tables={}
    for n,e in nodes.items():
        preset=e['node'].find('p:spPr/a:prstGeom',NS)
        if e['tag']=='grpSp':continue
        if (e['tag']=='pic' or e['node'].find('.//a:tbl',NS) is not None or
                any((t.text or '').strip() for t in e['node'].findall('.//a:t',NS)+e['node'].findall('.//m:t',NS)) or
                preset is not None and preset.get('prst')=='ellipse'):
            content.append(n)
        if e['tag']=='graphicFrame' and e['node'].find('.//a:tbl',NS) is not None:
            try:tables[n]=slots(e)
            except ValueError as error:tables[n]={'status':'unmeasured','reason':str(error)}
    return {'pptx_sha256':digest(pptx),'scene_sha256':candidate['scene']['sha256'],
            'native_names':sorted(nodes),'parents':parents,'groups':groups,
            'compatibility_variants':{n:e['compatibility'] for n,e in nodes.items() if e.get('compatibility')},
            'content_candidates':sorted(content),'tables':tables,
            'table_picture_candidates':picture_candidates(nodes)},scene,nodes


def _descendant(name,root,parents):
    seen=set()
    while name is not None and name not in seen:
        if name==root:return True
        seen.add(name);name=parents.get(name)
    return False


def bind(task,state,request,candidate):
    from .semantic_composition import _original_view, contracts
    inv,scene,nodes=inventory(task,state,candidate)
    rows=request.get('roots',[])
    if not rows or len(rows)>32:raise ValueError('Bind 1..32 original root decisions per packet')
    ledger=state.setdefault('rule_coverage',{'roots':{},'history':[]})
    known_features={f['id'] for f in read_json(resource(task,state['source_features']))['features']} if state.get('source_features') else set()
    active={r['id']:r for r in contracts(task,state)}
    for row in rows:
        root=row.get('root')
        if (root not in inv['groups'] or row.get('source_hash')!=state['source']['sha256'] or
                row.get('nature') not in ('physical','layout','symbol','text_math') or
                not row.get('evidence') or not row.get('feature_ids') or
                not set(row['feature_ids'])<=known_features):
            raise ValueError('Every native group needs original features, identity and a typed root decision')
        _original_view(task,state,row['source_view'])
        from .source_placement import validate as validate_anchor
        for anchor in row.get('anchors',[]):
            validate_anchor(anchor,state['source_size'])
            if (anchor['source_feature'] not in row['feature_ids'] or anchor['object'] not in nodes or
                    not _descendant(anchor['object'],root,inv['parents'])):
                raise ValueError('A source placement anchor must belong to this original physical root')
        delegate=row.get('placement_parent')
        if delegate is not None:
            parent=delegate.get('root');parent_role=delegate.get('role')
            declaration=next((r for r in rows if r.get('root')==parent),ledger['roots'].get(parent,{}))
            role=next((r for r in declaration.get('roles',[]) if r.get('id')==parent_role),{})
            if (parent==root or not _descendant(root,parent,inv['parents']) or
                    not set(inv['groups'][root])<=set(role.get('objects',[])) or
                    not delegate.get('source_evidence')):
                raise ValueError('Nested placement may delegate only to its actual source-bound parent role covering all leaves')
        roles=row.get('roles',[])
        if row['nature']=='physical':
            names=[n for r in roles for n in r.get('objects',[])]
            if (not roles or len({r.get('id') for r in roles})!=len(roles) or
                    len(names)!=len(set(names)) or set(names)!=set(inv['groups'][root]) or
                    any(r.get('kind') not in ('rigid','mark','decoration') or not r.get('feature_ids') or
                        not set(r['feature_ids'])<=known_features for r in roles)):
                raise ValueError('Physical roles must partition all saved leaves and bind independent original parts')
            edges=row.get('interfaces',[])
            if any(k not in active or active[k]['kind']!='interface' or active[k]['root']!=root for k in edges):
                raise ValueError('Physical edges require actual executable interface contracts')
            from .native_relations import validate as validate_native_relation
            role_map={r['id']:r for r in roles}
            for relation in row.get('native_relations',[]):
                validate_native_relation(relation,role_map)
                if relation['kind']=='design_attachment':
                    from .quality_intent import _ref as approved_ref
                    from .boundary_geometry import saved_nodes
                    from .native_topology import attachment
                    approved=state.get('quality_intent',{}).get('approved',{})
                    basis=relation['design_basis']
                    if (basis['source_feature'] not in row['feature_ids'] or
                            basis['approved_native_sha256']!=approved.get('pptx',{}).get('sha256')):
                        raise ValueError('Inferred attachment must bind this original feature and the verified approved native design')
                    baseline_nodes=saved_nodes(approved_ref(task,approved['pptx']),state['source_size'])
                    baseline=attachment(relation,role_map,baseline_nodes)
                    if not baseline['passed']:raise ValueError('Attachment bound exceeds actual approved-design evidence')
        previous=ledger['roots'].get(root)
        if previous and previous!=row:
            correction=request.get('corrections',{}).get(root,{})
            fields=('anchors','interfaces','native_relations')
            core=lambda r:{k:v for k,v in r.items() if k not in fields}
            if (correction.get('prior_hash')!=identity(previous) or not correction.get('reason') or
                    core(previous)!=core(row) or any(any(old not in row.get(f,[]) for old in previous.get(f,[])) for f in fields)):
                # Source interpretation is fallible. A typed correction must
                # explain every replaced field on untouched original pixels;
                # it cannot hide a failing current result by deleting a rule.
                changed={k for k in set(previous)|set(row) if previous.get(k)!=row.get(k)}
                replacements=correction.get('replaced_fields',{})
                if (correction.get('kind')!='source_reading' or correction.get('prior_hash')!=identity(previous)
                        or not correction.get('reason') or set(replacements)!=changed
                        or row['source_hash']!=previous['source_hash'] or row['root']!=previous['root']
                        or not set(previous['feature_ids'])<=set(row['feature_ids'])):
                    raise ValueError('Frozen root constraints need an explicit original-only source-reading correction for every replaced field')
                _original_view(task,state,correction['source_view'])
                for key,value in replacements.items():
                    if (value.get('prior_value_hash')!=identity(previous.get(key)) or not value.get('source_evidence')
                            or value.get('cause') not in ('object_mismatch','topology_misreading','measurement_domain_mismatch')):
                        raise ValueError('Source correction must retain each prior field and identify the actual reading error')
                # Stable, unchanged measurement identities never get looser.
                old_anchors={(r['method'],r['object'],r['source_feature']):r for r in previous.get('anchors',[])}
                for r in row.get('anchors',[]):
                    old=old_anchors.get((r['method'],r['object'],r['source_feature']))
                    if old and r['tolerance_px']>old['tolerance_px']:raise ValueError('Do not loosen original placement uncertainty')
                old_relations={(r['kind'],tuple(r['roles'])):r for r in previous.get('native_relations',[])}
                for r in row.get('native_relations',[]):
                    old=old_relations.get((r['kind'],tuple(r['roles'])))
                    if old and (r.get('tolerance_px',0)>old.get('tolerance_px',0) or
                            r.get('distance_px',[0,0])[0]<old.get('distance_px',[0,0])[0] or
                            r.get('distance_px',[0,0])[1]>old.get('distance_px',[0,0])[1]):
                        raise ValueError('Source reading correction cannot relax an existing threshold')
                if row['nature']=='physical' and not (row.get('anchors') or row.get('placement_parent')):
                    raise ValueError('A physical original root still needs a measured placement or exact ancestor delegation')
            ledger['history'].append({'event':'original_root_reading_amended','root':root,
                'prior':copy.deepcopy(previous),'correction':copy.deepcopy(correction),'drawing_gain':False})
        ledger['roots'][root]=copy.deepcopy(row)
    ledger['history'].append({'event':'whole_native_roots_bound','roots':[r['root'] for r in rows],
                              'source_hash':state['source']['sha256'],'drawing_gain':False})
    state.pop('acceptance',None)
    return {'status':'ROOTS_BOUND','count':len(rows)}


def report(task,state,candidate):
    from . import frame_plan, semantic_composition
    inv,scene,nodes=inventory(task,state,candidate);items=[]
    def check(key,passed,details):
        items.append({'id':key,'passed':bool(passed),'status':'PASS' if passed else 'REQUIRES_WORK','details':details})
    disabled=[k for k in MANDATORY if state.get('objectives',{}).get(k) is not True]
    check('mandatory_policy',not disabled and state.get('execution_contract')==VERSION,{'disabled':disabled,'version':state.get('execution_contract')})
    from .external_sync import actual_name
    mirrored={actual_name(state,o['id']) for o in scene['objects']}
    missing=sorted(set(inv['native_names'])-mirrored)
    extra=sorted(mirrored-set(inv['native_names']))
    wrong_parents=[o['id'] for o in scene['objects'] if o['id'] in inv['parents'] and o.get('parent')!=inv['parents'][o['id']]]
    check('whole_native_scene',not missing and not extra and not wrong_parents,{'missing_native_objects':missing,'phantom_scene_objects':extra,
        'wrong_semantic_parents':wrong_parents,'native_count':len(nodes),'scene_count':len(mirrored)})
    from .natural_owners import saved_inventory as natural_inventory
    natural_parts=natural_inventory(scene)
    check('natural_part_inventory',natural_parts['passed'],natural_parts)
    from .catalog_source import verify_frozen,verify_constructed
    try:
        verify_frozen(task,state)
        source_catalog=[verify_constructed(state,c['id'],scene['objects']) for c in state.get('analysis',{}).get('components',[])]
        check('original_catalog_instances',True,{'owners':source_catalog,'scope':'Frozen original anatomy and every independently constructed compatible instance'})
    except (ValueError,KeyError,OSError) as error:
        check('original_catalog_instances',False,{'reason':str(error)})
    plan=frame_plan.load(task,state['frame_plan']) if state.get('frame_plan') else None
    coverage={r['object']:r for r in plan['coverage']} if plan else {}
    missing_content=sorted(set(inv['content_candidates'])-set(coverage))
    check('whole_content_frames',not missing_content,{'uncovered_owners':missing_content})
    # A mechanism name is a delegation, not proof that the owner was bound.
    # Numeric satisfaction remains a separate final gate on all these units.
    for name,row in coverage.items():
        if row['mode']!='inherited':continue
        mechanism=row.get('mechanism');units=[]
        if mechanism=='source_part_quality':
            units=[u['id'] for u in state.get('quality',{}).get('units',{}).values()
                   if any(_descendant(name,n,inv['parents']) for n in u.get('objects',[]))]
        elif mechanism=='source_textbox_quality':
            from .textbox_quality import contracts as textbox_contracts
            units=[r['id'] for r in textbox_contracts(state) if r.get('object')==name]
        check('inherited_binding.'+name,bool(units),{'mechanism':mechanism,'actual_bound_units':units})
    table_frames={f['table']:f for f in plan['frames'] if f['kind']=='native_table'} if plan else {}
    for table,slots_ in inv['tables'].items():
        frame=table_frames.get(table)
        bound={m['object'] for m in frame.get('members',[])} if frame else set()
        found={r['object'] for r in inv['table_picture_candidates'] if r['table']==table and r.get('object')}
        check('native_table.'+table,frame is not None and found<=bound and slots_.get('status')!='unmeasured',
              {'picture_candidates':sorted(found),'unbound_pictures':sorted(found-bound),'actual_cell_count':len(slots_.get('slots',{}))})
    roots=state.get('rule_coverage',{}).get('roots',{})
    active={r['id']:r for r in semantic_composition.contracts(task,state)}
    from .source_placement import evaluate as evaluate_anchor
    def measure_anchor(anchor):
        response=None
        if anchor['method']=='native_painted_center':
            key=semantic_composition._capture_key({n:e['node'] for n,e in nodes.items()},inv['parents'],
                [anchor['object']],resource(task,candidate['pptx']),'paint_support')
            response=semantic_composition._response(task,state.get('semantic_composition',{}).get('captures',{}),
                key,state['source_size'],state,retain_native=True)
        return evaluate_anchor(anchor,nodes,state['source_size'],response=response)
    for root,leaves in inv['groups'].items():
        declaration=roots.get(root)
        check('semantic_root.'+root,declaration is not None,{'root':root,'leaf_count':len(leaves),'source_decision':declaration})
        if not declaration:continue
        for index,anchor in enumerate(declaration.get('anchors',[])):
            measured=measure_anchor(anchor)
            check('original_placement.'+root+'.'+str(index),measured['passed'],measured)
        if declaration['nature']!='physical':continue
        bound=bool(declaration.get('anchors'))
        delegated=declaration.get('placement_parent')
        if delegated:
            parent=roots.get(delegated['root'],{});role=next((r for r in parent.get('roles',[]) if r['id']==delegated['role']),{})
            measures=[measure_anchor(x) for x in parent.get('anchors',[])]
            bound=(bool(measures) and all(x['passed'] for x in measures) and
                set(leaves)<=set(role.get('objects',[])) and _descendant(root,delegated['root'],inv['parents']))
            check('original_placement_delegation.'+root,bound,{'parent':delegated,'parent_anchor_measurements':measures,
                'limits':'Delegates whole-assembly location only. Exact child geometry, source-part quality and interfaces remain independently required.'})
        check('original_placement_bound.'+root,bound,
              {'root':root,'status':'BOUND' if bound else 'REQUIRES_ORIGINAL_ANCHOR'})
        roles={r['id']:r for r in declaration['roles']}
        members=[n for r in roles.values() for n in r['objects']]
        exact=len(members)==len(set(members)) and set(members)==set(leaves)
        rigid={r['id'] for r in roles.values() if r['kind']=='rigid'}
        from .native_relations import connected
        for role in rigid:
            names=roles[role]['objects'];connection=connected(names,nodes)
            if roles[role].get('topology')=='stroke_graph':
                from .native_topology import stroke_connected
                try:connection=stroke_connected(names,nodes)
                except (ValueError,KeyError,TypeError) as error:
                    connection={'status':'required_unmeasured','passed':False,'reason':str(error)}
            if connection['status']=='required_unmeasured':
                # Reuse only current actual native-owner mattes, never an SVG
                # nominal rectangle or a candidate-derived substitute mask.
                from .native_relations import matte_connected
                key=semantic_composition._capture_key(
                    {n:e['node'] for n,e in nodes.items()},inv['parents'],names,resource(task,candidate['pptx']),'paint_support')
                response=semantic_composition._response(task,state.get('semantic_composition',{}).get('captures',{}),
                    key,state['source_size'],state,retain_native=True)
                if response is not None and response.shape[1]>=state['source_size'][0]*4 and response.shape[0]>=state['source_size'][1]*4:
                    connection={**matte_connected(response,state['source_size']),
                        'geometry_limit':connection.get('reason')}
            check('rigid_role_connectivity.'+root+'.'+role,connection['passed'],connection)
        graph={r:set() for r in rigid};edge_errors=[]
        for key in declaration.get('interfaces',[]):
            row=active.get(key)
            if not row or row['kind']!='interface' or row['root']!=root:
                edge_errors.append(key);continue
            a,b=row['source_roles']
            if a not in roles or b not in roles or row['part_sets']!=[roles[a]['objects'],roles[b]['objects']]:
                edge_errors.append(key);continue
            from .source_spacing import evaluate as evaluate_interface
            responses=[semantic_composition._response(task,state.get('semantic_composition',{}).get('captures',{}),
                semantic_composition._capture_key({n:e['node'] for n,e in nodes.items()},inv['parents'],g,
                    resource(task,candidate['pptx']),mode),state['source_size'],state,retain_native=True)
                for g,mode in semantic_composition._capture_groups(row,{n:e['node'] for n,e in nodes.items()},inv['parents'])]
            measured=evaluate_interface(task,state,row,responses,nodes,inv['parents'],state['source_size'])
            check('physical_interface_measurement.'+root+'.'+key,measured['passed'],measured)
            if measured['passed'] and a in graph and b in graph:graph[a].add(b);graph[b].add(a)
        from .native_relations import evaluate as evaluate_native_relation
        for index,row in enumerate(declaration.get('native_relations',[])):
            measured=evaluate_native_relation(row,roles,nodes)
            if row['kind'] in ('attached','adjacent','intentional_separation'):
                from .source_spacing import locate,prepare
                source,effective=prepare(task,state,locate(task,state,{'kind':'native_relation','root':root,'roles':row['roles']}))
                if effective is not None:
                    constrained=copy.deepcopy(row)
                    constrained['distance_px']=effective['limits']['distance_px']
                    measured=evaluate_native_relation(constrained,roles,nodes)
                measured={'status':measured['status'] if source['passed'] else source['status'],
                    'passed':bool(measured['passed'] and source['passed']),
                    'values':{'native':measured,'original_spacing':source}}
            check('native_relation.'+root+'.'+str(index),measured['passed'],measured)
            a,b=row['roles']
            if measured['passed'] and a in graph and b in graph:graph[a].add(b);graph[b].add(a)
        seen=set();todo=[next(iter(rigid))] if rigid else []
        while todo:
            name=todo.pop()
            if name in seen:continue
            seen.add(name);todo+=list(graph[name]-seen)
        check('physical_interfaces.'+root,exact and bool(rigid) and seen==rigid and not edge_errors,
              {'root':root,'partition_complete':exact,'unbound_rigid_roles':sorted(rigid-seen),'invalid_edges':edge_errors})
    result={'schema':VERSION,'source_hash':state['source']['sha256'],'pptx_hash':candidate['pptx']['sha256'],
            'inventory':inv,'items':items,'passed':all(i['passed'] for i in items),
            'limits':'Source meaning and completeness remain independently observed. This inventory cannot infer unseen source anatomy.'}
    write_json(resource(task,candidate['pptx']).parent/'execution-coverage.json',result)
    return result


def bind_task(task,request):
    from . import agent_runtime as a
    from .common import writer
    task,state=a._state(task)
    with writer(task):
        result=bind(task,state,request,state.get('active_candidate') or state['selected'])
        if (state.get('packet') or {}).get('kind')=='rule_coverage_source':state['packet']=None
        a._save(task,state)
    return result


def _source_owners(state,parents):
    """Resolve both production-built and imported current native owners."""
    from .external_sync import actual_name
    components={c['id'] for c in state.get('analysis',{}).get('components',[])}
    owners={}
    def add(name,owner):
        name=actual_name(state,name)
        if name not in parents:return
        if owner not in components:raise ValueError('A current native owner needs its original source component: '+name)
        if name in owners and owners[name]!=owner:
            raise ValueError('Conflicting original ownership for current native object: '+name)
        owners[name]=owner
    for name,owner in state.get('native_import',{}).get('owner_map',{}).items():add(name,owner)
    for owner,built in state.get('built',{}).items():
        for obj in built.get('objects',[]):add(obj['id'],owner)
    return owners


def packet(task,state,candidate):
    result=report(task,state,candidate)
    roots=[i['details']['root'] for i in result['items'] if i['id'].startswith('semantic_root.') and not i['passed']]
    # Missing source bindings need source work. Existing, bound but failed or
    # unsupported measurements need located repair/observation work, not an
    # endless request to resubmit the identical root declaration.
    measured_prefixes=('original_placement.','original_placement_delegation.',
        'physical_interfaces.','physical_interface_measurement.',
        'rigid_role_connectivity.','native_relation.')
    physical=[];other=[]
    declarations=state.get('rule_coverage',{}).get('roots',{})
    parents=result['inventory']['parents']
    owners=_source_owners(state,parents)
    components={c['id']:c for c in state.get('analysis',{}).get('components',[])}
    changed=False
    for item in result['items']:
        if item['passed'] or item['id'].startswith('semantic_root.'):continue
        bound_placement=False
        if item['id'].startswith('original_placement_bound.'):
            root=item['details']['root'];row=declarations.get(root,{})
            bound_placement=bool(row.get('anchors') or row.get('placement_parent'))
        if not item['id'].startswith(measured_prefixes) and not bound_placement:
            other.append(item);continue
        # Locate the native semantic owner through the actual full inventory.
        root=next((r for r in sorted(declarations,key=len,reverse=True)
            if '.'+r+'.' in item['id'] or item['id'].endswith('.'+r)),None)
        name=root
        visited=set()
        while name and name not in owners and name not in visited:
            visited.add(name);name=parents.get(name)
        owner=owners.get(name)
        if owner not in components:raise ValueError('A program finding needs an actual source owner: '+item['id'])
        iid='coverage-'+identity(item['id'])[:18]
        issue=next((r for r in state.setdefault('issues',[]) if r['id']==iid),None)
        value={'id':iid,'owner':owner,'roi':declarations[root]['source_view']['roi'],
            'property':'program_rule:'+item['id'],'severity':'major','status':'open',
            'expected':'Satisfy the frozen original-bound '+item['id'],
            'actual':item,'source':'program_execution_coverage','attempt_count':0,
            'evidence':{'candidate':candidate['pptx']['sha256'],'measurement':item['id']}}
        if issue:
            issue.update(actual=item,status='open',evidence=value['evidence'])
        else:state['issues'].append(value)
        physical.append(value)
        changed=True
    # Resolved measurements close only on the selected actual artifact. A
    # pending candidate records its result but cannot retire the old finding.
    passed={r['id']:r for r in result['items'] if r['passed']}
    for issue in state.get('issues',[]):
        target=issue.get('property','').removeprefix('program_rule:')
        if issue.get('source')!='program_execution_coverage' or target not in passed:continue
        resolution={'candidate':candidate['pptx']['sha256'],'measurement':passed[target]}
        if candidate['pptx']['sha256']==(state.get('selected') or {}).get('pptx',{}).get('sha256'):
            issue.update(status='resolved',resolution=resolution);issue.pop('pending_resolution',None)
        else:issue['pending_resolution']=resolution
        changed=True
    if changed:
        from . import agent_runtime as a
        a._save(task,state)
    if not roots and not physical and not other:return None
    return {'coverage_report':{'path':(resource(task,candidate['pptx']).parent/'execution-coverage.json').relative_to(task).as_posix(),
                               'sha256':digest(resource(task,candidate['pptx']).parent/'execution-coverage.json')},
            'roots':roots[:8],'remaining_roots':max(0,len(roots)-8),'physical':physical[:4],
            'remaining_physical':max(0,len(physical)-4),'other':other[:4],
            'return':'roots[{root,nature,source_hash,source_view,feature_ids,evidence,roles?,interfaces?}]. '
                     'Resolve missing whole native Scene/frame/table coverage through the existing source mechanisms; '
                     'bind physical interface contracts through semantic_composition_source. Missing is never not-applicable.'}


def _implementation():
    # The public executor identity is independent of a mutable task state.
    paths=list((ROOT/'scripts/core').glob('*.py'))+list((ROOT/'scripts').glob('*.py'))
    paths+=list((ROOT/'schemas').glob('*.json'))+list((ROOT/'scripts').glob('*.ps1'))+list((ROOT/'config').glob('*.json'))
    return identity({p.relative_to(ROOT).as_posix():digest(p) for p in sorted(paths) if p.is_file()})


def _basis(state,candidate):
    return identity({'source':state['source'],'candidate':{k:candidate.get(k) for k in ('pptx','scene','preview','render','font_delivery')},
        'analysis':state['analysis'],'objectives':state['objectives'],'quality':state.get('quality'),
        'features':state.get('source_features'),'frame_plan':state.get('frame_plan'),
        'source_palette_revisions':state.get('source_palette_revisions'),
        'roots':state.get('rule_coverage'),'composition':state.get('semantic_composition'),
        'original_spacing':state.get('source_spacing'),
        'neighbor_source':state.get('neighbor_source'),
        'neighbor_registry':state.get('neighbor_registry'),
        'neighbor_mattes':state.get('neighbor_mattes'),
        'source_unit_archives':state.get('source_unit_archives'),
        'recursive_containment':state.get('recursive_containment'),
        'cell_mattes':state.get('cell_mattes'),
        'office_math_contract':state.get('office_math_contract'),
        'office_math_behavior':state.get('office_math_behavior'),
        'icon_clarity_contract':state.get('icon_clarity_contract'),
        'icon_detail_requirements':state.get('icon_detail_requirements'),
        'source_target_attempts':state.get('source_target_attempts'),
        'task_target':__import__(__package__+'.task_completion',fromlist=['target_basis']).target_basis(state),
        'coherent_paper_required':state.get('coherent_paper_required'),
        'source_recursion':state.get('source_recursion'),
        'signal_contract':state.get('signal_contract'),
        'textbox_quality':state.get('textbox_quality'),'relative_layout':state.get('relative_layout'),
        'external_reconciliation':state.get('external_reconciliation'),
        'quality_intent':state.get('quality_intent'),'source_readings':state.get('source_readings'),
        'source_layout_attempts':state.get('source_layout_attempts'),
        'source_structure_attempts':state.get('source_structure_attempts'),
        'neighbor_repair_attempts':state.get('neighbor_repair_attempts'),
        'neighbor_execution':state.get('neighbor_execution'),
        'connection_contract':state.get('connection_contract'),
        'source_connection_graph':state.get('source_connection_graph'),
        'original_feature_functions':state.get('original_feature_functions'),
        'source_detail_contracts':state.get('source_detail_contracts'),
        'source_detail_observations':state.get('source_detail'),
        'source_repeat_decisions':state.get('source_repeat_decisions'),
        'connection_attempts':state.get('connection_attempts'),
        'recursive_repair_plans':state.get('recursive_repair_plans'),
        'preview_resource_attempts':state.get('preview_resource_attempts'),
        'semantic_observations':state.get('quality_observations',{}).get('host'),
        'object_lifecycle':state.get('object_lifecycle_result'),
        'native_owner_source':state.get('native_owner_source'),
        'native_owner_observations':state.get('native_owner_observations'),
        'global_plan':state.get('global_aesthetic_plan'),
        'global_observations':state.get('global_aesthetic_observations'),
        'global_layout_attempts':state.get('global_layout_attempts'),
        'object_rollback_attempts':state.get('object_rollback_attempts'),
        'implementation':_implementation()})


def final_gate(task,state,candidate):
    """Called by acceptance AND export. This never trusts stage='accepted'."""
    policy(state)
    if state.get('objectives',{}).get('component_first'):
        from .component_workflow import accept_final
        return accept_final(task,state,candidate)
    from .source_contract import reconcile
    current_contract = reconcile(state,task)
    if not current_contract['passed']:
        raise ValueError('Current source contracts do not reconcile: ' + str(current_contract['errors'][:12]))
    if state.get('quality_intent'):
        from .quality_loop import final_gate as intent_gate
        return intent_gate(task,state,candidate)
    raise ValueError('Compile the whole quality intent and execute the complete quality-loop before acceptance/export; legacy partial gates cannot bypass current obligations')
    from . import source_quality, source_features, frame_plan, semantic_composition, font_contract
    coverage=report(task,state,candidate);failures=[]
    if not coverage['passed']:failures.append({'gate':'coverage','items':[i['id'] for i in coverage['items'] if not i['passed']]})
    for field in ('pptx','scene','preview','render'):resource(task,candidate[field])
    receipt=read_json(resource(task,candidate['render']))
    if receipt.get('pptx_hash')!=candidate['pptx']['sha256'] or receipt.get('preview_hash')!=candidate['preview']['sha256']:
        failures.append({'gate':'actual_saved_render','status':'STALE_OR_MISSING'})
    debt=source_quality.pending(state);features=source_features.pending(task,state)
    inherited=set(state.get('prior_source_requirements',{}).get('unit_ids',[]))
    missing_prior=sorted(inherited-set(state.get('quality',{}).get('units',{})))
    changed_prior=[]
    prior_ref=state.get('prior_source_requirements',{}).get('state')
    if prior_ref:
        historical=read_json(resource(task,prior_ref));old_quality=historical.get('quality') or historical.get('source_quality')
        for uid,old in old_quality['units'].items():
            current=state.get('quality',{}).get('units',{}).get(uid)
            if not current:continue
            old_features={f['id'] for f in old.get('features',[])}
            if not old_features<={f['id'] for f in current.get('features',[])}:changed_prior.append({'unit':uid,'reason':'original_property_deleted'})
            current_metrics={m['id']:m for m in current.get('metrics',[])}
            for metric in old.get('metrics',[]):
                actual=current_metrics.get(metric['id'])
                if (not actual or metric.get('min') is not None and (actual.get('min') is None or actual['min']<metric['min']) or
                        metric.get('max') is not None and (actual.get('max') is None or actual['max']>metric['max'])):
                    changed_prior.append({'unit':uid,'metric':metric['id'],'reason':'original_threshold_removed_or_relaxed'})
    if missing_prior or changed_prior:failures.append({'gate':'historical_source_requirements','missing':missing_prior,'weakened':changed_prior})
    # An imported compiled unit/status cannot substitute for the mandatory
    # original source specification or executable layout review. Re-run the
    # same compiler without modifying live state; unresolved migration stays
    # visible even if someone has changed every stored unit to minimum_met.
    if not debt['complete']:failures.append({'gate':'source_quality','debt':debt})
    if features:failures.append({'gate':'original_features','features':[r['id'] for r in features]})
    if state.get('external_reconciliation',{}).get('status') in ('pending','user_intent_pending'):
        failures.append({'gate':'external_user_intent','status':'PENDING'})
    gates={}
    for key,call in (
        ('frame',lambda:frame_plan.guard(task,state,candidate,strict=True)),
        ('composition',lambda:semantic_composition.retention_guard(task,state,candidate,strict=True))):
        try:gates[key]=call()
        except ValueError as error:failures.append({'gate':key,'reason':str(error)})
    from .relative_layout import report as layout_report
    gates['layout']=layout_report(task,state,candidate)
    if any(r['status']!='minimum_met' for r in gates['layout'].get('relations',[])):
        failures.append({'gate':'layout','status':'UNMET_OR_UNMEASURED'})
    from .textbox_quality import guard_saved as text_guard, report as text_report
    gates['text_native']=text_guard(task,state,resource(task,candidate['pptx']))
    if gates['text_native']['unbound']:failures.append({'gate':'text_bindings','owners':gates['text_native']['unbound']})
    if gates['text_native']['bound_count']:
        gates['text']=text_report(task,state,candidate)
        if any(not i.get('values') or i['values'].get('content_match')!=1 or i['values'].get('math_match')!=1 or
               any(z.get('status')!='measured' for z in i.get('zones',[])) for i in gates['text']['items']):
            failures.append({'gate':'text_math_original','status':'UNMET_OR_UNMEASURED'})
    scene=read_json(resource(task,candidate['scene']))
    if not scene.get('font_plan'):
        failures.append({'gate':'source_fonts','status':'UNBOUND'})
    else:
        try:gates['fonts']=font_contract.guard_saved(scene,resource(task,candidate['pptx']))
        except ValueError as error:failures.append({'gate':'source_fonts','reason':str(error)})
        if candidate.get('font_delivery',{}).get('embedding',{}).get('status') not in ('EMBEDDED_FULL_EDITABLE_FONTS','NO_TEXT_FONTS'):
            failures.append({'gate':'editable_fonts','status':'UNVERIFIED'})
    # Stored satisfaction is not numeric evidence. Reevaluate every claimed
    # minimum on current native content/pixels (dependency cache is allowed).
    numeric=[]
    for u in state.get('quality',{}).get('units',{}).values():
        if u['status']!='minimum_met':continue
        measured=source_quality.evaluate(task,state,candidate,u)
        numeric.append({'unit':u['id'],'status':measured['status']})
        observed=state['quality'].get('observations',{}).get(u['id'],{})
        if measured['status']!='numeric_minimum_met' or observed.get('candidate')!=candidate['pptx']['sha256']:
            failures.append({'gate':'actual_part_quality','unit':u['id'],'status':measured['status']})
    result={'schema':VERSION,'status':'ACCEPTED' if not failures else 'BLOCKED','failures':failures,
        'source_hash':state['source']['sha256'],'pptx_hash':candidate['pptx']['sha256'],
        'render_backend':receipt.get('backend'),'implementation':_implementation(),
        'coverage_hash':identity(coverage),'gates':gates,'numeric':numeric,
        'limits':[u['id'] for u in state.get('quality',{}).get('units',{}).values() if source_quality.has_usable_limit(state,u)]}
    result['basis']=_basis(state,candidate)
    path=resource(task,candidate['pptx']).parent/('acceptance-'+identity(result)+'.json')
    write_json(path,result)
    state['acceptance']={'path':path.relative_to(task).as_posix(),'sha256':digest(path)}
    if failures:raise ValueError('Whole-drawing final acceptance blocked; inspect '+str(path))
    return result


def verify_acceptance(task,state,candidate):
    if state.get('objectives',{}).get('component_first'):
        from .component_workflow import accept_final
        return accept_final(task,state,candidate)
    ref=state.get('acceptance')
    if not ref:raise ValueError('A formal delivery requires the program final acceptance receipt')
    value=read_json(resource(task,ref))
    if value.get('status')!='ACCEPTED' or value.get('basis')!=_basis(state,candidate):
        raise ValueError('Final acceptance is blocked/stale; rerun the single final gate')
    return value


def require_delivery(task,pptx):
    from . import agent_runtime as a
    if task is None:raise ValueError('Formal delivery requires the same complete runtime task, not a helper-only acceptance')
    task,state=a._state(task)
    if state['stage']!='accepted' or not state.get('selected') or digest(pptx)!=state['selected']['pptx']['sha256']:
        raise ValueError('Formal delivery must use the loop-selected accepted actual drawing')
    final_gate(task,state,state['selected'])
    value=verify_acceptance(task,state,state['selected']);a._save(task,state)
    return value
