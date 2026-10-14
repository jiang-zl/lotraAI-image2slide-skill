"""Mandatory source-child re-observation after icon quality regressions.

The host identifies source facts and atomicity. The program owns the failed
unit queue, original child views, construction coverage and result predicates.
It cannot certify that a model's interpretation is the only correct meaning.
"""
import copy
from .common import identity

VERSION = 'icon-source-detail-2'
LEAVES = {'primitive', 'continuous_surface', 'continuous_curve',
          'repeated_primitive', 'subpixel_detail', 'text', 'formula'}


def child_context(task,state,roi,candidate):
    from .adaptive_detail import _view
    x,y,w,h=roi;a=max(0,x-8);b=max(0,y-8)
    region=[a,b,min(state['source_size'][0],x+w+8)-a,min(state['source_size'][1],y+h+8)-b]
    return _view(task,state,region,True,candidate)


def child_views(task,state,candidate,request):
    from .adaptive_detail import _view,_box,source_units
    from .source_recursion import structure
    unit=source_units(state).get(request.get('unit'));children=request.get('children',[])
    if not unit or not children or len({p.get('id') for p in children})!=len(children):
        raise ValueError('Known original unit and distinct source-located child proposals required')
    rows=[];a,b,c,d=unit['roi']
    for child in children:
        roi=child['roi'];_box(roi,state['source_size']);x,y,w,h=roi
        if x<a-1 or y<b-1 or x+w>a+c+1 or y+h>b+d+1:
            raise ValueError('Child escaped original unit; independently correct a truncated source domain first')
        cues=structure(task,state,roi)
        rows.append({'id':child['id'],'roi':roi,'original_view':_view(task,state,roi,True,candidate),
            'neighbor_original_view':child_context(task,state,roi,candidate),'structure_cues':cues,'source_cues_hash':identity(cues)})
    return {'kind':'original_icon_child_views','source_hash':state['source']['sha256'],'unit':unit['id'],
        'parent_original_view':_view(task,state,unit['roi'],True,candidate),'items':rows,
        'scope':'Read original child and neighbors, establish complete physical extent and atomicity; cues do not certify semantic truth'}


def schedule(state, candidate, clarity, mandatory=False):
    ledger = state.setdefault('icon_detail_requirements', {'schema': VERSION, 'units': {}, 'history': []})
    units = state.get('quality', {}).get('units', {})
    for row in clarity.get('items', []):
        uid = row.get('unit')
        if uid not in units or (row.get('passed') and not mandatory) or row.get('category') in ('texture', 'photo', 'not_icon'):
            continue
        hd, preservation = row.get('hd', {}), row.get('preservation', {})
        if not mandatory and hd.get('measurement_valid') is False:
            # Diagnose invalid source/capture measurements before inferring
            # an artifact regression or requiring new anatomical decisions.
            continue
        # A pending comparative observation gets its own review packet. A
        # measured regression, missing anatomy or failed HD needs source facts.
        if not mandatory and hd.get('passed') and preservation.get('numeric_pass'):
            review = preservation.get('review', {})
            if not review.get('passed') and not any(v == 'regressed' for r in review.get('comparisons', []) for v in r.get('criteria', {}).values()):
                continue
        basis = identity({'schema':VERSION,'source': state['source']['sha256'], 'unit': uid,
                          'roi': units[uid]['roi'], 'candidate': candidate['pptx']['sha256']})
        old = ledger['units'].get(uid)
        if old and old.get('basis') == basis:
            continue
        if old:
            ledger['history'].append(copy.deepcopy(old))
        ledger['units'][uid] = {'basis': basis, 'unit': uid, 'roi': units[uid]['roi'],
            'source_hash': state['source']['sha256'], 'candidate_hash': candidate['pptx']['sha256'],
            'reason': 'Mandatory original-child decomposition before HD reconstruction' if mandatory else 'Independent icon clarity, preservation or structural gate failed',
            'failure': copy.deepcopy(row), 'status': 'SOURCE_CHILD_REOBSERVATION_REQUIRED'}
    return ledger


def pending(state):
    return [u for u, r in state.get('icon_detail_requirements', {}).get('units', {}).items()
            if r.get('status') == 'SOURCE_CHILD_REOBSERVATION_REQUIRED']


def validate_children(task, state, item, row):
    """No generic whole-icon statement may admit its differently typed parts."""
    from .adaptive_detail import _view
    from .source_recursion import structure
    candidate = state.get('active_candidate') or state['selected']
    requirement = state.get('icon_detail_requirements', {}).get('units', {}).get(item['id'])
    if not requirement:
        return
    if requirement['source_hash'] != state['source']['sha256']:
        raise ValueError('Icon detail requirement belongs to another original')
    parts = row['observed_parts']
    if len({p['id'] for p in parts}) != len(parts):
        raise ValueError('Distinct original semantic child identities required')
    for part in parts:
        view = _view(task, state, part['roi'], True, candidate)
        if part.get('original_view_sha256') != view['sha256']:
            raise ValueError('Inspect every original child crop with parent context: ' + part['id'])
        context=child_context(task,state,part['roi'],candidate)
        if part.get('context_view_sha256')!=context['sha256'] or not part.get('context_facts'):
            raise ValueError('Original child needs a fresh program-defined neighbor context, including content outside the old frame: '+part['id'])
        if part.get('source_cues_hash')!=identity(structure(task,state,part['roi'])):
            raise ValueError('Review the current original child structural cues; coarse peak counts cannot establish atomicity: '+part['id'])
        leaf = part.get('leaf', {})
        if leaf.get('kind') not in LEAVES or not leaf.get('reason'):
            raise ValueError('Typed, source-grounded atomicity reason required for every icon child')
        names = part['objects']
        if len(set(names)) != len(names):
            raise ValueError('Duplicate semantic child construction ownership')
        if len(names) > 1:
            if leaf['kind'] != 'repeated_primitive' or leaf.get('count') != len(names) or not leaf.get('shared_geometry_role'):
                raise ValueError('Several unlike parts cannot hide behind one generic assembly feature')
        if leaf['kind'] == 'subpixel_detail' and (min(part['roi'][2:]) > 8 or part['roi'][2]*part['roi'][3] > 64):
            raise ValueError('Subpixel atomicity needs a genuinely small original child')
    names = [n for p in parts for n in p['objects']]
    if len(names) != len(set(names)):
        raise ValueError('A constructed part needs one unambiguous source-child owner')
    checked = {n for c in row['checks'] for n in c.get('objects', [])} | {
        c[k] for c in row['checks'] for k in ('object', 'a', 'b') if k in c}
    if set(names) - checked:
        raise ValueError('Every re-observed child needs an executable result predicate')


def record(state, rows):
    ledger = state.get('icon_detail_requirements', {})
    for row in rows:
        requirement = ledger.get('units', {}).get(row['id'])
        if requirement:
            requirement.update(status='SOURCE_CHILD_FACTS_BOUND', observation_hash=identity(row),
                source_cues_version=VERSION,
                observed_parts=copy.deepcopy(row['observed_parts']), checks=copy.deepcopy(row['checks']))


def verify_constructor(task, state, unit, objects):
    """Execution cannot skip the required original-child contract."""
    from .source_feature_functions import expected_frame
    root = unit.get('part') or unit['objects'][0]
    parents={o['id']:o.get('parent') for o in objects}
    candidate=state.get('active_candidate') or state.get('selected')
    if candidate and candidate.get('pptx'):
        from .boundary_geometry import saved_nodes
        from .common import safe_path
        for name,node in saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size']).items():
            parents.setdefault(name,node.get('parent_name'))
    def within(child,parent):
        seen=set();current=child
        while current and current not in seen:
            if current==parent:return True
            seen.add(current);current=parents.get(current)
        # Source function namespaces also cover new, not-yet-saved children.
        return child.startswith(parent+'.') or child.startswith(parent+'_')
    for uid, req in state.get('icon_detail_requirements', {}).get('units', {}).items():
        required = state['quality']['units'][uid]
        child_scope = any(n!=root and within(n,root) for n in required.get('objects', []))
        related = uid == unit['id'] or child_scope or any(within(root,n)
            for n in required.get('objects', []))
        if not related:
            continue
        if req.get('status') != 'SOURCE_CHILD_FACTS_BOUND':
            raise ValueError('Mandatory original icon-child re-observation must precede further construction: '+uid)
        bound = {n: p for p in req['observed_parts'] for n in p['objects']}
        scoped = objects
        if child_scope:
            scoped = [o for o in objects if o['id'] in bound or any(within(o['id'],n)
                for n in required.get('objects', []))]
            if not scoped or not any(o['render_type']!='group' for o in scoped):
                raise ValueError('Replacing a parent icon cannot discard its mandatory original child scope: '+uid)
        for obj in scoped:
            if obj['render_type'] == 'group':
                continue
            name = obj['id']
            if name not in bound:
                raise ValueError('Constructed icon part has no independently re-observed original child: '+name)
            x,y,w,h = expected_frame(obj); a,b,c,d = bound[name]['roi']
            if x<a-1.5 or y<b-1.5 or x+w>a+c+1.5 or y+h>b+d+1.5:
                raise ValueError('Constructed part escaped its own original child window: '+name)


def packet(task, state, candidate):
    from .adaptive_detail import packet as detail_packet
    queue = pending(state)
    if not queue:
        return None
    result = detail_packet(task, state, candidate, force_units=queue)
    if result:
        result['kind'] = 'mandatory_icon_source_children'
        result['atomicity_contract'] = {'allowed_leaf_types': sorted(LEAVES),
            'each_child': 'own unchanged original_view_sha256; context_view_sha256 from child_context (8 original pixels of neighbors), context_facts and current source_cues_hash; leaf.kind/reason; exact constructed objects and executable checks',
            'repeated_primitive': 'count and shared_geometry_role; unlike mechanical/optical parts require separate child facts'}
        result['required_before'] = 'source-bound constructors; generic feature coverage or fitting the old coarse geometry cannot discharge this queue'
        result['child_view_action']='source-detail TASK children --request JSON{unit,children:[{id,roi}]} returns program-owned original/neighbor hashes and source-only structural cues'
    return result


def report(task, state, candidate, nodes):
    from .detail_contracts import checks_report
    from .icon_hd import closure
    required = state.get('icon_detail_requirements', {}).get('units', {})
    if not required:
        return {'passed': True, 'items': [], 'scope': 'No triggered original-child debt; other complete source-recursion gates remain mandatory'}
    checks = {r['id']: r for r in checks_report(task,state,candidate)['items']}
    rows = []
    for uid, req in required.items():
        unit = state['quality']['units'].get(uid)
        mapped = {n for p in req.get('observed_parts', []) for n in p['objects']}
        try:
            leaves = {n for n in closure(nodes, unit['objects']) if nodes[n]['tag'] != 'grpSp'}
        except (KeyError,ValueError,TypeError):
            leaves = set(); missing_owner = True
        else:
            missing_owner = False
        good = req.get('status') == 'SOURCE_CHILD_FACTS_BOUND' and req.get('source_cues_version')==VERSION and req['source_hash'] == state['source']['sha256']
        good = good and not missing_owner and bool(leaves) and leaves == mapped and checks.get(uid,{}).get('passed') is True
        rows.append({'unit':uid,'passed':bool(good),'unbound_actual_children':sorted(leaves-mapped),
            'missing_constructed_children':sorted(mapped-leaves),
            'facts_status':req.get('status'),'actual_predicates':checks.get(uid),
            'scope':'Original child views and atomicity are source facts; every current saved child must have a current executable result check'})
    return {'passed':all(r['passed'] for r in rows),'items':rows}
