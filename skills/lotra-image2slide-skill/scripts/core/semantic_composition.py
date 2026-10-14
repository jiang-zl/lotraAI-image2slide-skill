"""Source-bound composition in the existing draw/observe/repair loop.

The host interprets original ownership; programs compile paint order, measure
the saved native result and forbid critical regressions. A box is a discovery
hint, never proof of opaque coverage. Unknown source intent remains unresolved.
"""
import copy
import math
from collections import defaultdict
from functools import lru_cache,wraps
from contextvars import ContextVar
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from .common import digest, identity, read_json, safe_path, write_json
from .mathml import NS
from .native_markup import active_children

VERSION = "semantic-composition-1"
KINDS = {"order", "opaque_core", "opening", "join", "inside", "same_template", "interface"}
PAINT_TAGS = {"sp", "grpSp", "cxnSp", "pic", "graphicFrame"}
_resource_transaction=ContextVar('composition_verified_resources',default=None)

def verified_resources(function):
    @wraps(function)
    def execute(*args,**kwargs):
        # Repeated edges may cite the same original view. Verify each immutable
        # resource once within one operation; a new operation verifies again.
        # This avoids thousands of WSL/Windows path resolutions and reads.
        if _resource_transaction.get() is not None:return function(*args,**kwargs)
        token=_resource_transaction.set({})
        try:return function(*args,**kwargs)
        finally:_resource_transaction.reset(token)
    return execute


def enabled(state):
    return bool(state.get("objectives", {}).get("source_semantic_composition")
                or state.get("semantic_composition", {}).get("contracts"))


def _ref(task, value):
    cache=_resource_transaction.get();key=(str(task),value['path'],value['sha256'])
    if cache is not None and key in cache:return cache[key]
    path = safe_path(task, value["path"])
    if digest(path) != value["sha256"]:
        raise ValueError("Source composition evidence changed: " + value["path"])
    if cache is not None:cache[key]=path
    return path


def _native(pptx):
    with ZipFile(pptx) as z:
        root = E.fromstring(z.read("ppt/slides/slide1.xml"))
    nodes, parents, children = {}, {}, defaultdict(list)
    def visit(tree, parent=None):
        for node in active_children(tree):
            if E.QName(node).localname not in PAINT_TAGS:
                continue
            name = node.find(".//p:cNvPr", NS).get("name")
            if name in nodes:
                raise ValueError("Duplicate saved semantic name: " + name)
            nodes[name] = node; parents[name] = parent; children[parent].append(name)
            if E.QName(node).localname == "grpSp":
                visit(node, name)
    visit(root.find("p:cSld/p:spTree", NS))
    return nodes, parents, children


def _chain(name, parents):
    chain = [name]; seen = {name}
    while parents.get(chain[-1]) is not None:
        parent = parents[chain[-1]]
        if parent in seen:
            raise ValueError("Composition parent cycle")
        chain.append(parent); seen.add(parent)
    return list(reversed(chain))


def _branches(a, b, parents):
    aa, bb = _chain(a, parents), _chain(b, parents)
    at = 0
    while at < min(len(aa), len(bb)) and aa[at] == bb[at]:
        at += 1
    if at == min(len(aa), len(bb)):
        raise ValueError("An ancestor and its child need containment, not paint order")
    return (aa[at-1] if at else None), aa[at], bb[at]


def validate_relations(relations,where='relations'):
    """Accept typed Scene edges, never descriptive strings used as edges."""
    from .source_contract import finite
    if not isinstance(relations,list):raise ValueError(where+' must be a list of typed edges')
    for index,row in enumerate(relations):
        at=where+'['+str(index)+']'
        if not isinstance(row,dict):raise ValueError(at+' must be an object, not source prose')
        for name in ('type','source','target'):
            if not isinstance(row.get(name),str) or not row[name].strip():
                raise ValueError(at+'.'+name+' must be a nonempty string')
        finite(row,at)
    return relations


def compile_order(scene):
    """Stable sibling DAG at each lowest common ancestor; groups stay atomic."""
    validate_relations(scene.get('relations',[]))
    nodes = {o["id"]: o for o in scene["objects"]}
    parents = {n: o.get("parent") for n, o in nodes.items()}
    siblings = defaultdict(list)
    for i, obj in enumerate(scene["objects"]):
        siblings[obj.get("parent")].append((obj.get("z_order", i), i, obj["id"]))
    original = {p: [x[2] for x in sorted(rows)] for p, rows in siblings.items()}
    edges = defaultdict(set)
    for relation in scene.get("relations", []):
        kind = relation.get("type")
        if kind not in ("behind", "occludes", "paint_before"):
            continue
        a, b = relation["source"], relation["target"]
        if a not in nodes or b not in nodes:
            # A scoped donor deliberately omits unrelated relation endpoints.
            continue
        if kind == "occludes":
            a, b = b, a
        parent, left, right = _branches(a, b, parents)
        edges[parent].add((left, right))
    result = {}
    for parent, order in original.items():
        rank = {n: i for i, n in enumerate(order)}
        after = defaultdict(set); degree = {n: 0 for n in order}
        for a, b in edges[parent]:
            if b not in after[a]:
                after[a].add(b); degree[b] += 1
        ready = [n for n in order if not degree[n]]; desired = []
        while ready:
            ready.sort(key=rank.get); node = ready.pop(0); desired.append(node)
            for nxt in sorted(after[node], key=rank.get):
                degree[nxt] -= 1
                if degree[nxt] == 0:
                    ready.append(nxt)
        if len(desired) != len(order):
            conflict = [n for n in order if degree[n]]
            raise ValueError("Unrepresentable group paint cycle; refine source layers: " + repr(conflict))
        result[parent] = desired
    return result


def _validate(task, state, row):
    if (row.get("schema") != VERSION or row.get("kind") not in KINDS
            or row.get("source_hash") != state["source"]["sha256"]
            or row.get("canvas") != state["source_size"]
            or not row.get("id") or not row.get("source_evidence")):
        raise ValueError("Bind original identity, canvas and an independently observed semantic explanation")
    names = row.get("objects", [])
    required = 1 if row["kind"] in ("opaque_core", "opening") else 2
    if ((len(names) < 2 if row['kind'] in ('same_template', 'interface') else len(names) != required)
            or len(set(names)) != len(names)):
        raise ValueError("Distinct actual native owners are required")
    if row.get("critical", True) is not True:
        raise ValueError("Important composition constraints cannot be demoted by the drawing agent")
    _original_view(task, state, row["source_view"])
    if row['kind'] == 'interface':
        if row.get('original_spacing'):
            from .source_spacing import classified
            measured=classified(task,state,row,row['original_spacing'])['measurement']
            if measured['status']!='ORIGINAL_SPACING_CLASSIFIED':
                raise ValueError('Original spacing is ambiguous; refine original segmentation without drawing a presumed joint')
            if row.get('relationship','auto') not in ('auto',measured['classification']):
                raise ValueError('A desired semantic relationship cannot override measured original spacing')
            row['relationship']=measured['classification']
            limits=row.setdefault('limits',{});rule=measured['output_rule']
            prior=limits.get('distance_px',rule['distance_px'])
            limits['distance_px']=[max(prior[0],rule['distance_px'][0]),min(prior[1],rule['distance_px'][1])]
            limits['solid_width_px']=max(limits.get('solid_width_px',0.),rule['solid_width_px'])
        from .semantic_interfaces import validate
        validate(row, state['source_size'])
    if row["kind"] in ("opaque_core", "opening", "join"):
        from PIL import Image
        import numpy as np
        path = _ref(task, row["mask"])
        with Image.open(path) as image:
            if list(image.size) != state["source_size"]:
                raise ValueError("Owned source masks use the unchanged original canvas")
            mask = np.asarray(image.convert("L")) > 127
            count = int(mask.sum())
        x,y,w,h = row["source_view"]["roi"]
        inside = np.zeros(mask.shape,dtype=bool); inside[y:y+h,x:x+w] = True
        if (mask & ~inside).any():
            raise ValueError("Every source-domain pixel must lie inside the actually observed original window")
        if not count:
            raise ValueError("An empty core/opening/join mask cannot establish coverage")
        if row.get("mask_origin") != "original_observed":
            raise ValueError("Candidate-derived coverage domains are not source evidence")
    if row["kind"] == "inside":
        tolerance = row.get("tolerance_px", 0.)
        if type(tolerance) not in (int, float) or not math.isfinite(tolerance) or tolerance < 0 or tolerance > 2:
            raise ValueError("Freeze bounded original edge uncertainty; do not waive visible overflow")
    if row["kind"] == "same_template":
        if not row.get("roles") or set(row["roles"]) != set(names):
            raise ValueError("Every family instance needs the same named child-role mapping")
        role_sets = [set(v) for v in row["roles"].values()]
        if not role_sets[0] or any(v != role_sets[0] for v in role_sets):
            raise ValueError("Template role inventories must agree")
        mother = row.get("mother", {})
        _ref(task, mother)
        if not mother.get("group") or set(mother.get("roles", {})) != role_sets[0]:
            raise ValueError("Use an immutable approved native mother with the same semantic roles")
        native, parents, _ = _native(_ref(task, mother))
        root = mother['group']
        if root not in native or not all(n in native and n != root and root in _chain(n, parents)
                                        for n in mother['roles'].values()):
            raise ValueError('Mother roles must be real descendants of the immutable mother')
        covered = {n for n in native if any(role in _chain(n, parents) for role in mother['roles'].values())}
        leaves = {n for n in native if root in _chain(n, parents) and E.QName(native[n]).localname != 'grpSp'}
        if not leaves <= covered:
            raise ValueError('Mother roles omit native visual parts: ' + repr(sorted(leaves-covered)))
        if any(len(set(mapping.values())) != len(mapping) for mapping in row['roles'].values()):
            raise ValueError('Distinct semantic mother roles need distinct instance parts')
    return row


def _covers(name, owner, parents):
    return owner in _chain(name, parents)


def _binding_integrity(state, scene, rows, decisions, ownership):
    """References prove their exact participants, not merely an existing ID."""
    parents = {o['id']: o.get('parent') for o in scene['objects']}
    by_id = {r['id']: r for r in rows}
    kinds = {'ordered': {'order'}, 'contained': {'inside'},
             'joined': {'join','interface'}, 'intentional_opening': {'opening'}}
    for decision in decisions:
        from .external_sync import native_contract
        decision = native_contract(state, decision)
        choice = decision['decision']
        if choice not in kinds:
            continue
        a, b = decision['objects']
        selected = [by_id[c] for c in decision.get('contracts', []) if c in by_id]
        def matches(row):
            names = row['objects']
            if row['kind'] not in kinds[choice]:
                return False
            if row['kind']=='interface':
                first,second=row['part_sets']
                return ((any(_covers(n,a,parents) for n in first) and any(_covers(n,b,parents) for n in second)) or
                        (any(_covers(n,b,parents) for n in first) and any(_covers(n,a,parents) for n in second)))
            if choice == 'intentional_opening':
                return all(n == names[0] or _covers(n, names[0], parents)
                           or _covers(names[0], n, parents) for n in (a, b))
            normal = _covers(names[0], a, parents) and _covers(names[1], b, parents)
            reverse = _covers(names[0], b, parents) and _covers(names[1], a, parents)
            # Discovery pairs are unordered; ordered/contained roles must be
            # explicit when their executable contract reverses this pair.
            if choice in ('ordered', 'contained'):
                if not decision.get('roles'):
                    return normal or reverse  # Legacy pair is unordered; row defines its directed roles.
                expected = decision['roles']
                from .external_sync import actual_name
                expected = {k: actual_name(state, v) for k, v in expected.items()}
                return (_covers(names[0], expected.get('first'), parents)
                        and _covers(names[1], expected.get('second'), parents))
            return normal or reverse
        if not any(matches(row) for row in selected):
            raise ValueError('Interaction contract type/endpoints do not match: ' + decision['id'])
    for item in ownership:
        from .external_sync import actual_name
        owner = actual_name(state, item['owner'])
        if item['nature'] in ('transparent', 'text_math', 'unknown','container'):
            continue
        allowed = {'opening'} if item['nature'] == 'open' else {'opaque_core', 'join', 'inside'}
        selected = [by_id[c] for c in item.get('contracts', []) if c in by_id]
        if not any(r['kind'] in allowed and any(_covers(n, owner, parents) for n in r['objects']) for r in selected):
            raise ValueError('Ownership proof belongs to another object: ' + owner)


@lru_cache(maxsize=256)
def _original_pixels_match(source,source_hash,crop,crop_hash,roi):
    from PIL import Image
    import numpy as np
    # Callers verify both file hashes before every cached lookup. Reusing a
    # validated identical original view avoids decoding it for every DAG edge.
    x,y,w,h=roi
    with Image.open(source) as original,Image.open(crop) as image:
        expected=np.asarray(original.convert('RGB').crop((x,y,x+w,y+h)))
        actual=np.asarray(image.convert('RGB'))
        if actual.shape!=expected.shape or not np.array_equal(actual,expected):
            raise ValueError('Source decisions use unchanged original pixels, not candidate or enhanced references')
    return True

def _original_view(task, state, ref):
    path = _ref(task, ref); roi = ref.get("roi")
    if not isinstance(roi, list) or len(roi) != 4 or any(type(v) is not int for v in roi):
        raise ValueError("Use a raw original crop with integer original ROI")
    x,y,w,h = roi
    if min(x,y) < 0 or min(w,h) <= 0 or x+w > state["source_size"][0] or y+h > state["source_size"][1]:
        raise ValueError("Original view ROI is outside the unchanged source")
    source=_ref(task,state['source'])
    _original_pixels_match(str(source),state['source']['sha256'],str(path),ref['sha256'],tuple(roi))
    return path


def contracts(task, state):
    rows = []
    for ref in state.get("semantic_composition", {}).get("contracts", []):
        row=_validate(task, state, read_json(_ref(task, ref)))
        if row['id'] not in state.get('semantic_composition',{}).get('superseded',{}):
            from .external_sync import native_contract
            rows.append(native_contract(state, row))
    return rows


def _scene_for(state, task):
    candidate = state.get("active_candidate") or state.get("selected")
    if candidate:
        return read_json(_ref(task, candidate["scene"]))
    from .agent_runtime import _scene
    return _scene(task, state)


def discover(task, state, scene=None, scope=None):
    """Spatial buckets propose direct interactions, never a semantic verdict.

    Consider atomic semantic groups plus their direct parts. Very large panels
    are handled as parents, so they do not cause an all-page quadratic scan.
    """
    scene = scene or _scene_for(state, task)
    objects = {o["id"]: o for o in scene["objects"]}
    # Program-created connection sites have no material surface. They are
    # traversed and checked by native/terminal obligations, not interpreted
    # as new original icon parts or opaque physical overlaps.
    current=state.get('active_candidate') or state.get('selected')
    if current:
        from .boundary_geometry import saved_nodes
        from .native_connection_transaction import verify_anchor
        saved=saved_nodes(_ref(task,current['pptx']),state['source_size'])
        objects={n:o for n,o in objects.items() if n not in saved or not verify_anchor(saved[n])}
    focus = set(scope or objects)
    parents = {n: o.get("parent") for n, o in objects.items()}
    buckets = defaultdict(list); pairs = set()
    for n, obj in objects.items():
        x, y, w, h = obj["bbox"]
        if w * h > .4 * state["source_size"][0] * state["source_size"][1]:
            continue
        cells = [(ix, iy) for ix in range(math.floor((x-2)/64), math.floor((x+w+2)/64)+1)
                 for iy in range(math.floor((y-2)/64), math.floor((y+h+2)/64)+1)]
        for cell in cells:
            for peer in buckets[cell]:
                if n not in focus and peer not in focus:
                    continue
                if parents[n] != parents[peer] and parents[n] != peer and parents[peer] != n:
                    continue  # deeper interactions are handled at their atomic parents
                a, b = sorted((n, peer)); pairs.add((a, b))
            buckets[cell].append(n)
    from .physical_pairs import required as physical_required
    physical={pair:value for pair,value in physical_required(state,scene).items() if set(pair)<=set(objects)}
    pairs.update(physical)
    rows = [];hierarchy=[]
    for a, b in sorted(pairs):
        aa, bb = objects[a]["bbox"], objects[b]["bbox"]
        dx = min(aa[0]+aa[2], bb[0]+bb[2])-max(aa[0], bb[0])
        dy = min(aa[1]+aa[3], bb[1]+bb[3])-max(aa[1], bb[1])
        if min(dx, dy) < -2 and (a,b) not in physical:
            continue
        if parents[a]==b or parents[b]==a:
            parent,child=(b,a) if parents[a]==b else (a,b)
            hierarchy.append({'objects':[parent,child],'basis':'actual native coordinate ancestry; no painted physical join is inferred'})
            continue
        key = identity([state["source"]["sha256"], a, b])
        rows.append({"id": key, "objects": [a, b], "bounds": [aa, bb],
                     **({'requires_numeric_physical_check':True,'physical_root':physical[a,b],
                         'required':'Bind a source-classified interface or original interior/opening constraint; unrelated prose is insufficient.'} if (a,b) in physical else {}),
                     "hint": "parent_child" if parents[a] == b or parents[b] == a else "overlap_or_near",
                     "status": "requires_original_decision"})
    return {"schema": VERSION, "source_hash": state["source"]["sha256"],
            "scene_hash": identity(scene), "scope": sorted(focus), "interactions": rows,'program_hierarchy':hierarchy}


def _decisions_ready(task, state, scene, scope=None):
    proposed = discover(task, state, scene, scope)
    decisions = state.get("semantic_composition", {}).get("decisions", {})
    from .external_sync import native_contract
    decisions = {identity([state['source']['sha256']] + sorted(native_contract(state,d)['objects'])):
                 native_contract(state,d) for d in decisions.values()}
    bound = {r["id"] for r in contracts(task, state)}
    _binding_integrity(state, scene, contracts(task, state),
                       [d for d in decisions.values() if set(d.get('contracts', [])) <= bound],
                       [o for o in state.get('semantic_composition', {}).get('ownership', {}).values()
                        if set(o.get('contracts', [])) <= bound])
    from .physical_pairs import proven
    current_rows=contracts(task,state)
    unresolved = []
    from .connection_geometry import report as connection_report
    candidate=state.get('active_candidate') or state.get('selected')
    connections=connection_report(task,state,candidate) if candidate and state.get('connection_contract') else {'items':[]}
    from .connection_geometry import _load_contract,node_graph_items,line
    spec=_load_contract(task,state) if connections.get('source_integrity',{}).get('passed') else {'items':[]}
    closed={r['id'] for r in connections['items'] if r['passed']};program_decisions=[]
    from .boundary_geometry import saved_nodes
    pptx=_ref(task,candidate['pptx']) if candidate else None
    graph_nodes=saved_nodes(pptx,state['source_size']) if pptx else {}
    graph_rows=node_graph_items(spec,graph_nodes)
    graph_edges={r['objects'][0]:r for r in graph_rows if r['id'] in closed}
    native,parents,_=_native(pptx) if graph_rows else ({},{},{})
    graph_targets={p['target']:p['semantic_owner'] for r in graph_rows for p in r['ports']}
    cache=state.get('semantic_composition',{}).get('captures',{});paint={}
    def graph_paint(name):
        if name not in paint:
            paint[name]=_response(task,cache,_capture_key(native,parents,[name],pptx,'paint_support'),
                state['source_size'],state,retain_native=True)
        return paint[name]
    # New coherent native parts still participate in the older whole-scene
    # composition loop. A constructor proof alone is insufficient: consume
    # only the current independent expected-role/neighbor/actual-render closure.
    from . import neighbor_contracts as neighbor,folded_paper
    coherent=folded_paper.report(task,state,candidate) if candidate else {'items':[]}
    constructor_roots={r['root'] for r in coherent['items'] if r['passed']}
    assembly_pairs={}
    if constructor_roots and state.get('neighbor_source'):
        current=neighbor.current_result(task,state,candidate)
        if current:assembly_pairs=neighbor.closed_assembly_pairs(neighbor._load(task,state),current,constructor_roots)
    for pair in proposed["interactions"]:
        members=set(pair['objects']);matched=[]
        assembly=assembly_pairs.get(tuple(sorted(members)))
        if assembly:
            program_decisions.append({'id':pair['id'],'objects':pair['objects'],'basis':state['neighbor_result'],
                'mechanism':'coherent_saved_constructor_and_current_whole_assembly_relations',**assembly,'passed':True})
            continue
        for row in spec['items']:
            if row['id'] not in closed:continue
            if members<=set(row['objects']):matched.append(row['id']);continue
            if members&set(row['objects']) and members&set(row.get('occluders',[])):matched.append(row['id']);continue
            if any(members=={p['object'],p.get('target')} for p in row['ports']):matched.append(row['id'])
        if matched:
            program_decisions.append({'id':pair['id'],'objects':pair['objects'],'connections':sorted(set(matched)),
                'basis':state['connection_contract'],'mechanism':'original_connection_contract_and_actual_geometry','passed':True})
            continue
        edge_names=members&set(graph_edges)
        if len(edge_names)==2:
            a,b=sorted(edge_names);ra,rb=graph_edges[a],graph_edges[b]
            owners={p['semantic_owner'] for r in (ra,rb) for p in r['ports']}
            if len(owners)==1:
                from shapely.geometry import LineString
                intersection=LineString(line(graph_nodes[a])['points']).intersection(LineString(line(graph_nodes[b])['points']))
                program_decisions.append({'id':pair['id'],'objects':pair['objects'],'connections':[ra['id'],rb['id']],
                    'basis':state['connection_contract'],'mechanism':'original_binary_edges_with_distinct_terminal_bindings',
                    'source_parts':ra['source_parts']+rb['source_parts'],'actual_intersection_type':intersection.geom_type,
                    'same_intermediate_connection':False,'passed':True})
                continue
        if len(edge_names)==1:
            edge=next(iter(edge_names));other=next(iter(members-{edge}));row=graph_edges[edge]
            if other in graph_targets and other not in {p['target'] for p in row['ports']} and graph_targets[other]==row['ports'][0]['semantic_owner']:
                er,nr=graph_paint(edge),graph_paint(other)
                if er is not None and nr is not None and er.shape==nr.shape:
                    import numpy as np
                    overlap=int(np.count_nonzero((er<255)&(nr<255)))
                    if overlap==0:
                        program_decisions.append({'id':pair['id'],'objects':pair['objects'],'connections':[row['id']],
                            'basis':state['connection_contract'],'mechanism':'original_nonincident_node_and_actual_host_disjoint_paint',
                            'actual_paint_overlap_pixels_4x':overlap,'passed':True})
                        continue
        d = decisions.get(pair["id"])
        if (not d or d.get("decision") == "unresolved" or not d.get("evidence")
                or any(c not in bound for c in d.get("contracts", []))
                or pair.get('requires_numeric_physical_check') and not proven(pair,d,current_rows,scene)):
            unresolved.append(pair)
    proposed['program_connection_decisions']=program_decisions
    return proposed, unresolved


def _ownership_missing(task, state):
    ledger = state.get("semantic_composition", {})
    declared = ledger.get("ownership", {})
    active={r['id'] for r in contracts(task,state)}
    return [{k: c.get(k) for k in ("id", "semantic_class", "roi", "parts")}
            for c in state["analysis"]["components"]
            if c["id"] not in declared or declared[c["id"]].get("nature") == "unknown"
            or not set(declared[c['id']].get('contracts',[])) <= active]


def source_packet(task, state, scene, scope=None):
    if not state.get("objectives", {}).get("source_semantic_composition"):
        return None
    proposal, unresolved = _decisions_ready(task, state, scene, scope)
    missing = _ownership_missing(task, state)
    if not unresolved and not missing:
        return None
    folder = task / "source" / "composition"; folder.mkdir(exist_ok=True)
    path = folder / ("discovery-" + identity(proposal) + ".json"); write_json(path, proposal)
    return {"kind": "semantic_composition_source", "source": state["source"],
            "discovery": {"path": path.relative_to(task).as_posix(), "sha256": digest(path)},
            "interactions": unresolved[:8], "remaining": len(unresolved), "owners": missing[:8], "remaining_owners": len(missing),
            'declaration_types':{'decisions':['ordered','contained','joined','intentional_opening','disjoint','unrelated','unresolved'],
                'ownership':{'opaque':'independent opaque_core/join/inside contract required',
                    'open':'independent original opening contract required','layered':'independent coverage/interior contracts required',
                    'transparent':'visible independent marks with no material core','text_math':'text/math content owner',
                    'container':'actual coordinate group; every painted descendant remains subject to the mandatory final whole policy',
                    'unknown':'pending source interpretation, never completed ownership'},
                'physical_pairs':'All direct painted roles in a classified raw physical icon are program-discovered even when far apart. Bind an original_spacing interface (auto classification), a real source join mask or a bounded actual container interior. unrelated/disjoint prose alone cannot close these pairs. Read references/semantic-composition.md for the complete input grammar.',
                'source_view':'Use packet.original_view, the unchanged raw original locator. Display views are inspection enlargements.'},
            "required": "Observe original parts/layers; bind order, opaque cores, true openings, joins and interiors where important. Explain false bbox overlaps. Unknown is unresolved, not pass.",
            "submit": {"kind": "semantic_composition_source", "contracts": [], "decisions": [], "ownership": []}}


def _validate_bind_request(request):
    from .source_contract import finite
    if not isinstance(request,dict):raise ValueError('composition request must be an object')
    finite(request,'composition')
    def refs(value,at):
        if not isinstance(value,dict) or any(not isinstance(value.get(k),str) or not value[k] for k in ('path','sha256')):
            raise ValueError(at+' must bind a resource path and sha256')
    def names(value,at):
        if not isinstance(value,list) or not all(isinstance(v,str) and v for v in value):
            raise ValueError(at+' must be a list of nonempty IDs')
    for field in ('contracts','decisions','ownership'):
        values=request.get(field,[])
        if not isinstance(values,list):raise ValueError('composition.'+field+' must be a list of objects')
        for index,row in enumerate(values):
            at='composition.'+field+'['+str(index)+']'
            if not isinstance(row,dict):raise ValueError(at+' must be an object')
            for name in ('objects','contracts','source_roles'):
                if name in row:names(row[name],at+'.'+name)
            for name in ('source_view','mask','mother'):
                if name in row:refs(row[name],at+'.'+name)
            if 'part_sets' in row:
                if not isinstance(row['part_sets'],list):raise ValueError(at+'.part_sets must be a list of owner sets')
                for group in row['part_sets']:names(group,at+'.part_sets')
            for name in ('port','limits','roles','original_spacing'):
                if name in row and not isinstance(row[name],dict):raise ValueError(at+'.'+name+' must be an object')
            for name in ('source_root_frame','canvas'):
                if name in row and (not isinstance(row[name],list) or any(type(v) not in (int,float) for v in row[name])):
                    raise ValueError(at+'.'+name+' must contain finite coordinates')
            for key,value in row.get('port',{}).items():
                if key in ('domain','anchor','tangent') and (not isinstance(value,list) or any(type(v) not in (int,float) for v in value)):
                    raise ValueError(at+'.port.'+key+' must contain finite coordinates')
            spacing=row.get('original_spacing')
            if spacing is not None:
                if 'source_view' in spacing:refs(spacing['source_view'],at+'.original_spacing.source_view')
                for name in ('masks','segmentation'):
                    value=spacing.get(name,[])
                    if not isinstance(value,list) or not all(isinstance(v,dict) for v in value):
                        raise ValueError(at+'.original_spacing.'+name+' must be a list of objects')
                for ref in spacing.get('masks',[]):refs(ref,at+'.original_spacing.masks')


def _bind(task, state, request):
    """Install a complete validated binding transaction, never partial state."""
    _validate_bind_request(request)
    working=copy.deepcopy(state)
    result=_bind_validated(task,working,copy.deepcopy(request))
    state.clear();state.update(working)
    return result


def _bind_validated(task, state, request):
    rows = request.get("contracts", []); decisions = request.get("decisions", []); ownership = request.get("ownership", [])
    if not rows and not decisions and not ownership:
        raise ValueError("Bind actual original constraints or explained interaction decisions")
    if len(rows) > 16 or len(decisions) > 128:
        raise ValueError("Use bounded semantic packets; keep masks and full evidence on disk")
    scene = _scene_for(state, task); owners = {o["id"] for o in scene["objects"]}
    # Reject unsupported physical decisions before any ledger/file mutation.
    from .physical_pairs import required as physical_required,proven
    physical=physical_required(state,scene)
    active_rows=contracts(task,state)
    for decision in decisions:
        pair=tuple(sorted(decision.get('objects',[])))
        if pair in physical and not proven({'objects':list(pair),'physical_root':physical[pair]},decision,active_rows+rows,scene):
            raise ValueError('Same-root physical parts require executable original spacing or interior/opening evidence: '+repr(pair))
    ledger = state.setdefault("semantic_composition", {"contracts": [], "decisions": {}, "history": []})
    known = {r["id"] for r in contracts(task, state)}
    folder = task / "source" / "composition"; folder.mkdir(exist_ok=True)
    for row in rows:
        _validate(task, state, row)
        if row["id"] in known or not set(row["objects"]) <= owners:
            raise ValueError("Use new immutable contract identity and real native owners")
        path = folder / (identity(row) + ".json"); write_json(path, row)
        ledger["contracts"].append({"path": path.relative_to(task).as_posix(), "sha256": digest(path)})
        known.add(row["id"])
        old_id=row.get('replaces')
        if old_id:
            correction=row.get('source_correction',{})
            if (old_id not in known or old_id==row['id'] or not correction.get('reason')
                    or correction.get('kind')!='original_interpretation' or not correction.get('evidence')):
                raise ValueError('A source correction needs its prior identity and new original-only ownership/intent evidence')
            previous=next(r for r in contracts(task,state) if r['id']==old_id)
            if previous['kind']=='interface' and row['kind']=='interface':
                from .source_spacing import binding,prepare
                if binding(previous)==binding(row):
                    before,after=previous['limits'],row['limits']
                    if (after['distance_px'][0]<before['distance_px'][0] or after['distance_px'][1]>before['distance_px'][1]
                            or after.get('solid_width_px',0)<before.get('solid_width_px',0)
                            or after['anchor_error_px']>before['anchor_error_px']):
                        raise ValueError('A new interface ID/source prose cannot relax the same frozen measurement')
                if previous['relationship']!=row['relationship'] and prepare(task,state,row)[1] is None:
                    raise ValueError('Correcting contact/separation requires program-classified original masks')
            ledger.setdefault('superseded',{})[old_id]={'by':row['id'],'correction':correction,'drawing_gain':False}
            ledger['history'].append({'event':'source_interpretation_corrected','prior':old_id,'new':row['id'],'evidence':correction,'drawing_gain':False})
            for issue in state.get('issues',[]):
                if issue.get('composition_contract')==old_id:
                    issue.update(status='resolved',resolution={'kind':'source_interpretation_superseded','new_contract':row['id'],'drawing_gain':False})
    valid_decisions = {"ordered", "contained", "joined", "intentional_opening", "disjoint", "unrelated", "unresolved", "hierarchy"}
    for decision in decisions:
        if (decision.get("decision") not in valid_decisions or not decision.get("evidence")
                or decision.get("source_hash") != state["source"]["sha256"]
                or not set(decision.get("contracts", [])) <= known):
            raise ValueError("Explain original interaction; bind declared constraints before deciding")
        if decision["decision"] not in ("disjoint", "unrelated", "unresolved", "hierarchy") and not decision.get("contracts"):
            raise ValueError("A real interaction needs executable constraints, not prose alone")
        _original_view(task, state, decision["source_view"])
        pair = decision.get("objects", [])
        if len(pair) != 2 or not set(pair) <= owners:
            raise ValueError("Decision must identify the proposed pair")
        if decision['decision']=='hierarchy':
            parents={o['id']:o.get('parent') for o in scene['objects']}
            if not (_covers(pair[0],pair[1],parents) or _covers(pair[1],pair[0],parents)):
                raise ValueError('Hierarchy decisions require actual ancestor membership; they do not prove physical joins')
        expected = identity([state["source"]["sha256"]] + sorted(pair))
        if decision.get("id") != expected:
            raise ValueError("Decision identity must match its source-bound pair")
        ledger["decisions"][expected] = copy.deepcopy(decision)
    current_rows=contracts(task,state)
    for owner in ownership:
        from .external_sync import actual_name
        if (actual_name(state, owner.get("owner")) not in owners or not owner.get("evidence")
                or owner.get("source_hash") != state["source"]["sha256"]
                or owner.get("nature") not in ("opaque", "open", "layered", "transparent", "text_math", "unknown","container")
                or not set(owner.get("contracts", [])) <= known):
            raise ValueError("Declare source owner nature and executable important domains")
        _original_view(task, state, owner["source_view"])
        if owner['nature']=='container':
            # A group has no own material surface. This explicit nature must
            # never exempt a painted leaf or imply a physical child joint.
            name=actual_name(state,owner['owner']);item=next(o for o in scene['objects'] if o['id']==name)
            if item['render_type']!='group':raise ValueError('Container ownership is restricted to actual native groups')
            descendants=[o['id'] for o in scene['objects'] if name in _chain(o['id'],{o['id']:o.get('parent') for o in scene['objects']}) and o['id']!=name]
            covered={n for r in state.get('quality_intent',{}).get('items',[]) for n in r['objects']}
            if not descendants:raise ValueError('Every container descendant needs its independent quality policy')
            if not set(descendants)<=covered:
                if state.get('active_candidate') or state.get('selected') or not state.get('objectives',{}).get('whole_quality_intent'):
                    raise ValueError('Every container descendant needs its independent quality policy')
                owner['verification']='FINAL_WHOLE_POLICY_REQUIRED'
        selected = [r for r in current_rows if r["id"] in owner.get("contracts", [])]
        if owner["nature"] in ("opaque", "layered") and not any(r["kind"] in ("opaque_core", "join", "inside") for r in selected):
            raise ValueError("Opaque/layered semantic owners require independently observed coverage/interior domains")
        if owner["nature"] == "open" and not any(r["kind"] == "opening" for r in selected):
            raise ValueError("Preserve an open semantic owner with an original opening domain")
        ledger.setdefault("ownership", {})[owner["owner"]] = copy.deepcopy(owner)
    _binding_integrity(state, scene, current_rows,
                       list(ledger['decisions'].values()), list(ledger.get('ownership', {}).values()))
    ledger["history"].append({"event": "original_bound", "contracts": [r["id"] for r in rows],
                              "decisions": len(decisions), "source_hash": state["source"]["sha256"]})
    return {"status": "SOURCE_BOUND", "contracts": len(ledger["contracts"]), "decisions": len(ledger["decisions"])}


@verified_resources
def bind(task, request):
    from . import agent_runtime as a
    with a.writer(Path(task).resolve()):
        task, state = a._state(task)
        if (state.get('active_candidate') and not state['active_candidate'].get('preview')):
            raise ValueError('Render the saved working baseline before amending its original composition facts')
        if (state.get('packet') or {}).get('kind') not in (None,'semantic_composition_source','frame_plan_source','rule_coverage_source','textbox_source','source_spec'):
            raise ValueError('Bind source intent between drawing actions or in a source observation packet')
        result = _bind(task, state, request)
        state.pop('acceptance',None)
        if (state.get('packet') or {}).get('kind')=='semantic_composition_source':state['packet']=None
        a._save(task, state)
        return result


def prepare_scene(task, state, scene, baseline=None, allowed=None):
    if not enabled(state):
        return scene
    scene = copy.deepcopy(scene)
    # Generated relations must reflect the active immutable contracts once.
    # Retaining a superseded coarse layer edge can reverse a newly observed
    # fine-grained source fact even when the new Scene order is correct.
    scene['relations']=[r for r in scene['relations'] if not r.get('id','').startswith('composition:')]
    for row in contracts(task, state):
        if row["kind"] == "order":
            scene["relations"].append({"id": "composition:"+row["id"], "type": "behind",
                                      "source": row["objects"][0], "target": row["objects"][1]})
    desired = compile_order(scene)
    if baseline:
        _, parents, actual = _native(_ref(task, baseline["pptx"]))
        # Compilation is never implicit authority to move protected siblings.
        for parent, names in desired.items():
            present = [n for n in names if n in actual.get(parent, [])]
            before = [n for n in actual.get(parent, []) if n in present]
            if before != present:
                movable = {n for n, fields in (allowed or {}).items() if "paint_order" in fields or fields == ["replace_component"]}
                replacement_roots={n for n,fields in (allowed or {}).items() if fields==['replace_component']}
                # A subtree replacement owns its internal part order. Root
                # grants never authorize moving neighbouring roots/siblings.
                movable|={n for n in before if replacement_roots.intersection(_chain(n,parents))}
                # Moving one granted sibling shifts others' indices, but must
                # not change the relative order of protected siblings.
                if [n for n in before if n not in movable] != [n for n in present if n not in movable]:
                    raise ValueError("Source order repair cannot reorder protected siblings; grant only the intended movable owner")
    return scene


@lru_cache(maxsize=16)
def _resources(pptx, pptx_hash):
    with ZipFile(pptx) as z:
        return identity({p: __import__('hashlib').sha256(z.read(p)).hexdigest() for p in z.namelist()
                         if p.startswith(("ppt/media/", "ppt/theme/")) or p == "ppt/slides/_rels/slide1.xml.rels"})


def _owner_key(nodes, parents, names, pptx, resource_hash=None):
    """Owner subtrees + composed parents + media/theme protect scoped reuse."""
    native = {}
    for name in names:
        if name not in nodes:
            raise ValueError("Missing saved composition owner: " + name)
        native[name] = E.tostring(nodes[name]).hex()
        for parent in _chain(name, parents)[:-1]:
            props = nodes[parent].find("p:grpSpPr", NS)
            native["parent:"+parent] = E.tostring(props).hex()
    included={int(p.get('id')) for name in names for p in nodes[name].iter('{'+NS['p']+'}cNvPr')}
    by_id={int(node.find('.//p:cNvPr',NS).get('id')):name for name,node in nodes.items()}
    dependency_ids={int(p.get('id')) for name in names for p in nodes[name].iter()
                    if E.QName(p).localname in ('stCxn','endCxn')}-included
    for native_id in sorted(dependency_ids):
        if native_id not in by_id:raise ValueError('Missing actual native connection dependency')
        name=by_id[native_id]
        native['binding_dependency:'+name]=E.tostring(nodes[name]).hex()
        for parent in _chain(name,parents)[:-1]:
            native['parent:'+parent]=E.tostring(nodes[parent].find('p:grpSpPr',NS)).hex()
    resources = _scoped_resources(pptx, [nodes[n] for n in names])
    return identity({"owners": native, "resources": resources})


def _scoped_resources(pptx, owners):
    import hashlib, posixpath
    values = {}
    with ZipFile(pptx) as archive:
        def relationships(part):
            path = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
            if path not in archive.namelist():
                return {}
            return {r.get('Id'): r for r in E.fromstring(archive.read(path))}
        def add(part):
            if part in values:
                return
            if part not in archive.namelist():
                raise ValueError('Missing owner resource: ' + part)
            data = archive.read(part); values[part] = hashlib.sha256(data).hexdigest()
            if part.endswith('.xml'):
                tree = E.fromstring(data)
                used = {v for n in tree.iter() for k, v in n.attrib.items() if k.startswith('{' + NS['r'] + '}')}
                for rid, relation in relationships(part).items():
                    if rid in used or relation.get('Type', '').endswith(('/theme', '/slideMaster', '/slideLayout')):
                        follow(part, relation)
        def follow(part, relation):
            target = relation.get('Target', '')
            if relation.get('TargetMode') == 'External':
                values['external:' + target] = identity(dict(relation.attrib)); return
            add(posixpath.normpath(posixpath.join(posixpath.dirname(part), target)))
        part = 'ppt/slides/slide1.xml'; rels = relationships(part)
        used = {v for owner in owners for n in owner.iter() for k, v in n.attrib.items()
                if k.startswith('{' + NS['r'] + '}')}
        for rid in used:
            if rid not in rels:
                raise ValueError('Missing native owner relationship: ' + rid)
            follow(part, rels[rid])
        for relation in rels.values():
            if relation.get('Type', '').endswith(('/theme', '/slideLayout')):
                follow(part, relation)
    return identity(values)


def _capture_groups(row, nodes, parents):
    names = row['objects']
    if row['kind'] == 'interface':
        return [(group, 'paint_support') for group in row['part_sets']]
    if row['kind'] != 'inside':
        return [(names, 'paint_support')]
    parent, child = names
    body = row.get('container_body', parent)
    if body not in nodes or not _covers(body, parent, parents):
        raise ValueError('Inside needs a real body within its parent: ' + row['id'])
    if E.QName(nodes[body]).localname != 'sp' or child in _chain(body, parents):
        raise ValueError('Select one independent closed native container_body, not a group containing the child')
    geometry = nodes[body].find('p:spPr', NS)
    preset = geometry.find('a:prstGeom', NS) if geometry is not None else None
    custom = geometry.find('a:custGeom', NS) if geometry is not None else None
    if (preset is not None and preset.get('prst') in ('line', 'arc', 'bracePair', 'bracketPair')) or (
            preset is None and (custom is None or not custom.findall('.//a:path/a:close', NS))):
        raise ValueError('Container interior needs a closed contour; do not substitute a frame/line')
    return [([body], 'container_interior'), ([child], 'paint_support')]


def _capture_key(nodes, parents, names, pptx, mode):
    return identity({'owner': _owner_key(nodes, parents, names, pptx),
                     'measurement': mode, 'protocol': 'native-owner-lattice-4x-v3'})


@verified_resources
def guard_saved(task, state, pptx, baseline=None, allowed=None):
    from .layout_ink import required_owners
    layout_owners=required_owners(task,state,pptx)
    if not enabled(state) and not layout_owners:
        return {"status": "LEGACY_UNBOUND", "critical_pass": None}
    rows = contracts(task, state) if enabled(state) else []
    nodes, parents, children = _native(pptx)
    resource_hash = _resources(str(pptx), digest(pptx))
    failures = []; orders = []; captures = {}
    def add_capture(group,mode):
        key = _capture_key(nodes, parents, group, pptx, mode)
        leaves = [n for n, node in nodes.items() if E.QName(node).localname != 'grpSp'
                  and any(owner in _chain(n, parents) for owner in group)]
        if not leaves:raise ValueError('A required actual owner capture has no saved leaves')
        captures[key] = {'id':key,'objects':group,'owner_hash':key,'measurement':mode,
            'depends_on_fonts':mode!='container_interior' and any(
                any((t.text or '').strip() for t in nodes[n].findall('.//a:t',NS)) or bool(nodes[n].findall('.//m:t',NS)) for n in leaves),
            'native_ids':[int(nodes[n].find('.//p:cNvPr',NS).get('id')) for n in leaves],'leaf_objects':leaves}
    for row in rows:
        names = row["objects"]
        if not set(names) <= set(nodes):
            failures.append({"id": row["id"], "status": "missing_owner", "objects": names}); continue
        if row["kind"] == "order":
            parent, a, b = _branches(*names[:2], parents)
            passed = children[parent].index(a) < children[parent].index(b)
            item = {"id": row["id"], "status": "measured", "kind": "order", "passed": passed,
                    "objects": names, "native_branches": [a, b], "parent": parent}
            orders.append(item)
            if not passed:
                failures.append(item)
        elif row["kind"] != "same_template":
            for group, mode in _capture_groups(row, nodes, parents):
                add_capture(group,mode)
    # The full root inventory also owns obligations. Unsupported compound,
    # gradient, SVG and stroke geometry must be observed by the actual host.
    from .boundary_geometry import saved_nodes
    from .native_relations import connected
    geometry=saved_nodes(pptx,state['source_size'])
    for root in state.get('rule_coverage',{}).get('roots',{}).values():
        for anchor in root.get('anchors',[]):
            if anchor['method']=='native_painted_center':add_capture([anchor['object']],'paint_support')
        for role in root.get('roles',[]):
            group=role.get('objects',[])
            if role.get('kind')=='rigid' and connected(group,geometry)['status']=='required_unmeasured':
                add_capture(group,'paint_support')
    for name in layout_owners:
        add_capture([name],'paint_support')
    # Explicit scientific node graphs need actual edge/node paint to distinguish
    # a false bounding-box overlap from a real intrusion into a nonincident node.
    if state.get('connection_contract'):
        from .connection_geometry import _load_contract,node_graph_items
        for row in node_graph_items(_load_contract(task,state),geometry):
            for name in set(row['objects'])|{p['target'] for p in row['ports']}:
                add_capture([name],'paint_support')
    # Cache immutable actual mattes by native scope and renderer. A changed
    # backdrop object/order alone does not invalidate an isolated owner matte.
    cache = state.get("semantic_composition", {}).get("captures", {})
    pending = [r for key, r in captures.items() if key not in cache or not _cached_capture(task, cache[key], state)]
    request = {"schema": "office-composition-capture-1", "pptx_hash": digest(pptx),
               "canvas": state["source_size"], "sampling_scale":4, "captures": pending[:16], "remaining": max(0, len(pending)-16),
               "limits": "Isolate native owner subtrees on black/white in private copies. No original save, no group flattening, no bounding-box opacity inference."}
    path = Path(pptx).parent / "semantic-composition-capture.json"
    if pending:
        write_json(path, request)
    if failures:
        write_json(Path(pptx).parent/"semantic-composition-native-failure.json", {"failures": failures})
        raise ValueError("Saved semantic composition failed: " + repr(failures[:4]))
    return {"status": "NATIVE_ORDER_MEASURED_COVERAGE_PENDING" if captures else "MEASURED",
            "orders": orders, "capture_request": {"path": path.relative_to(task).as_posix(), "sha256": digest(path)} if pending else None,
            "capture_keys": list(captures), "remaining_captures": max(0,len(pending)-16), "bound_count": len(rows)}


def continue_capture(task, state, candidate):
    """Continue only missing owner batches on the same saved drawing."""
    guard = candidate.get("semantic_composition_guard", {})
    ingest_capture(task,state,candidate)
    pptx = _ref(task,candidate["pptx"])
    # Keep each source request immutable because the host receipt hashes it.
    request = Path(pptx).parent/"semantic-composition-capture.json"
    if request.exists():
        archive = request.with_name("semantic-composition-capture-"+digest(request)+".json")
        if not archive.exists():
            __import__('shutil').copyfile(request,archive)
        guard["capture_request"] = {"path": archive.relative_to(task).as_posix(), "sha256": digest(archive)}
    candidate["semantic_composition_guard"] = guard_saved(task,state,pptx)
    if not candidate["semantic_composition_guard"]["capture_request"]:
        return False
    # The page render is independently verified evidence. Missing owner
    # batches cannot erase it or force the full page to be exported again.
    candidate['capture_pending']=True
    return True


def _host_context(state, receipt, fonts=False):
    fields = ('backend', 'backend_version', 'office_build', 'environment')
    if fonts: fields += ('font_inventory_hash', 'fontconfig')
    return identity({'actual': {k: receipt.get(k) for k in fields},
                     'route': state.get('capabilities', {}).get('fingerprint'),
                     'epoch': state.get('semantic_composition', {}).get('environment_epoch', 0),
                     'sampling': 'native-owner-lattice-4x-v3'})


def capture_provider_current(row):
    expected=(portable_capture_hash() if row.get('provider')=='portable_native_batch' else
              digest(Path(__file__)) if row.get('provider')=='portable_native_copy' else
              digest(Path(__file__).resolve().parent.parent/'render_office.ps1'))
    return row.get('provider_script_hash',row.get('renderer_script_hash'))==expected


def _cached_capture(task, row, state=None):
    try:
        for key in ("black", "white"):
            _ref(task, row[key])
            if state and state.get('source_size'):
                from PIL import Image
                with Image.open(_ref(task,row[key])) as pixels:
                    if pixels.width<state['source_size'][0]*4 or pixels.height<state['source_size'][1]*4:return False
        current = Path(__file__).resolve().parent.parent / "render_office.ps1"
        expected = (portable_capture_hash() if row.get('provider')=='portable_native_batch' else
            digest(Path(__file__)) if row.get("provider") == "portable_native_copy" else digest(current))
        context_kind='text' if row.get('depends_on_fonts') else 'geometry'
        current_context = (state or {}).get('semantic_composition', {}).get('actual_host_contexts',{}).get(context_kind)
        return (row.get("provider_script_hash", row.get("renderer_script_hash")) == expected
                and bool(row.get("backend")) and bool(current_context)
                and row.get('host_context') == current_context
                and row.get('route_fingerprint') == (state or {}).get('capabilities', {}).get('fingerprint')
                and row.get('environment_epoch') == (state or {}).get('semantic_composition', {}).get('environment_epoch', 0))
    except (KeyError, ValueError, FileNotFoundError):
        return False


def ingest_capture(task, state, candidate):
    render = safe_path(task, candidate["render"]["path"])
    actual = read_json(_ref(task, candidate['render']))
    ledger = state.setdefault('semantic_composition', {'contracts': [], 'decisions': {}, 'history': []})
    if candidate.get('revision', 0) < ledger.get('actual_host_revision', -1):
        return  # Historical comparisons cannot roll back the current host.
    ledger['actual_host_context'] = _host_context(state, actual)
    ledger['actual_host_contexts'] = {'geometry':_host_context(state,actual), 'text':_host_context(state,actual,True)}
    ledger['actual_host_revision'] = candidate.get('revision', 0)
    receipt = render.parent/"composition-capture.json"
    if not receipt.is_file():
        return
    data = read_json(receipt)
    if data.get('pptx_hash') != candidate['pptx']['sha256']:
        raise ValueError('Composition receipt belongs to a different saved drawing')
    receipt_hash=digest(receipt)
    if receipt_hash in ledger.get('ingested_capture_receipts',[]):
        # Report/continuation can reread an already adopted batch after the
        # request has been retired. Current host context still invalidates
        # old mattes when the environment changes.
        return
    request_ref = candidate.get("semantic_composition_guard", {}).get("capture_request")
    if not request_ref:
        raise ValueError("Unrequested composition observations cannot be adopted")
    request = read_json(_ref(task, request_ref))
    if (data.get("schema") != "office-composition-observation-1" or data.get("pptx_hash") != candidate["pptx"]["sha256"]
            or data.get("request_hash") != request_ref["sha256"] or data.get("canvas") != state["source_size"]):
        raise ValueError("Bind actual host mattes to this saved drawing and capture request")
    expected = {r["id"]: r for r in request["captures"]}
    accepted = {}
    for row in data.get("captures", []):
        if (row.get("id") not in expected or row.get("objects") != expected[row["id"]]["objects"]
                or row.get("owner_hash") != expected[row["id"]]["owner_hash"]):
            raise ValueError("Observed owner scope differs from the bound request")
        native = expected[row["id"]]
        if row.get('provider')=='portable_native_batch':
            from .native_capture_batch import verify_record
            verify_record(task,state,candidate,native,row,render.parent)
        observed = [(int(b["id"]), b["name"]) for b in row.get("native_bindings", [])]
        wanted = list(zip(native["native_ids"],native["leaf_objects"]))
        if observed != wanted:
            raise ValueError("Actual host native leaf identity does not match the original saved scope")
        record = {k: row[k] for k in ("id", "objects", "backend", "renderer_script_hash", "owner_hash")}
        for extra in ("provider", "provider_script_hash", "backend_version", "office_build", "font_inventory_hash", "isolated_artifacts"):
            if extra in row: record[extra] = row[extra]
        record["pptx_hash"] = candidate["pptx"]["sha256"]
        if row.get('backend') != actual.get('backend') or row.get('backend_version') != actual.get('backend_version'):
            raise ValueError('Owner observation backend differs from its actual page renderer')
        fonts=native.get('depends_on_fonts',False)
        record.update(host_context=ledger['actual_host_contexts']['text' if fonts else 'geometry'],depends_on_fonts=fonts,
                      route_fingerprint=state.get('capabilities', {}).get('fingerprint'),
                      environment_epoch=ledger.get('environment_epoch', 0),
                      measurement=native.get('measurement', 'paint_support'))
        if record['measurement'] == 'container_interior' and row.get('measurement') != 'container_interior':
            raise ValueError('Container interior needs its explicit independent native geometry observation')
        for kind in ("black", "white"):
            ref = row[kind]; path = render.parent/ref["path"]
            if digest(path) != ref["sha256"]:
                raise ValueError("Actual owner matte changed")
            record[kind] = {"path": path.relative_to(task).as_posix(), "sha256": ref["sha256"]}
        accepted[row["id"]] = record
    ledger.setdefault('captures',{}).update(accepted)
    ledger.setdefault('ingested_capture_receipts',[]).append(receipt_hash)


def capture_portable(task, state, candidate):
    """Finish bounded capture batches without another drawing or page render."""
    bound=max(1,len(candidate.get('semantic_composition_guard',{}).get('capture_keys',[]))+1)
    seen=set();result={'status':'NO_MISSING_OWNERS'}
    for _ in range(bound):
        guard=candidate.get('semantic_composition_guard',{})
        if not guard.get('capture_request'):return result
        signature=identity(guard['capture_request'])
        if signature in seen:raise ValueError('Owner capture made no bounded progress; preserve evidence and diagnose the pending request')
        seen.add(signature)
        result = _capture_portable_batch(task,state,candidate)
        request = _ref(task,candidate['semantic_composition_guard']['capture_request'])
        preserved = request.with_name('semantic-composition-capture-'+digest(request)+'.json')
        if not preserved.exists():
            __import__('shutil').copyfile(request,preserved)
        new_guard = guard_saved(task,state,_ref(task,candidate['pptx']))
        if not new_guard['capture_request']:
            candidate['semantic_composition_guard']=new_guard
            candidate.pop('capture_pending',None)
            return result
        candidate['semantic_composition_guard'] = new_guard
    raise ValueError('Owner capture exhausted its bounded progress budget; preserve the pending evidence')


def capture_task(task):
    """Capture missing actual owners without manufacturing a new acceptance."""
    from . import agent_runtime as a
    task,state=a._state(task)
    with a.writer(task):
        candidate=state.get('active_candidate') or state.get('selected')
        if not candidate or not candidate.get('render'):raise ValueError('Bind an actual full saved-file render first')
        candidate['semantic_composition_guard']=guard_saved(task,state,_ref(task,candidate['pptx']))
        try:
            capture_portable(task,state,candidate)
            result=register_failures(task,state,candidate)
            if state.get('connection_attempts') and state.get('quality_intent',{}).get('approved'):
                from .owned_paint import capture
                result['source_correction_paint']=capture(task,state,candidate,state['quality_intent']['approved'])
        finally:
            # Each complete owner is ingested separately below. A later
            # failed owner preserves those verified observations for resume.
            a._save(task,state)
    return result


def portable_capture_hash():
    return identity({name:digest(Path(__file__).with_name(name)) for name in
        ('semantic_composition.py','native_capture_batch.py','native_markup.py','render.py')})

def isolated_parts(parts,original_tree,item,colour):
    """One native constructor preserves parent frames in both capture routes."""
    kept=set(item['leaf_objects']);keep_ids=set(item['native_ids'])
    tree=copy.deepcopy(original_tree);tree.set("showMasterSp","0")
    indexed={int(n.find('.//p:cNvPr',NS).get('id')):n for n in tree.iter()
             if E.QName(n).localname in PAINT_TAGS and n.find('.//p:cNvPr',NS) is not None}
    dependency_ids={int(c.get('id')) for n in indexed.values()
                    if int(n.find('.//p:cNvPr',NS).get('id')) in keep_ids
                    for c in n.findall('.//a:stCxn',NS)+n.findall('.//a:endCxn',NS)}-keep_ids
    for native_id in dependency_ids:
        node=indexed.get(native_id)
        if node is None or E.QName(node).localname!='sp':
            raise ValueError('Actual owner isolation requires a located native shape dependency')
        props=node.find('p:spPr',NS)
        if props is None:raise ValueError('Connection dependency has no saved shape geometry')
        for paint in list(props):
            if E.QName(paint).localname in ('solidFill','noFill','gradFill','blipFill','pattFill','grpFill','ln','effectLst','effectDag'):
                props.remove(paint)
        E.SubElement(props,'{'+NS['a']+'}noFill')
        ln=E.SubElement(props,'{'+NS['a']+'}ln');E.SubElement(ln,'{'+NS['a']+'}noFill')
        E.SubElement(props,'{'+NS['a']+'}effectLst')
        text=node.find('p:txBody',NS)
        if text is not None:node.remove(text)
    keep_ids|=dependency_ids
    from .native_markup import prune_owners
    prune_owners(tree.find("p:cSld/p:spTree",NS),keep_ids)
    for node in tree.iter('{'+NS['p']+'}cxnSp'):
        if any(int(c.get('id')) not in keep_ids for c in node.findall('.//a:stCxn',NS)+node.findall('.//a:endCxn',NS)):
            raise ValueError('Actual portable matte requires a host for outside connector dependencies')
    if item.get('measurement') == 'container_interior':
        body = next(n for n in tree.iter() if E.QName(n).localname == 'sp'
                    and n.find('.//p:cNvPr', NS).get('name') in kept)
        props = body.find('p:spPr', NS)
        for paint in list(props):
            if E.QName(paint).localname in ('solidFill','noFill','gradFill','blipFill','pattFill','grpFill','ln','effectLst','effectDag'):
                props.remove(paint)
        fill = E.SubElement(props, '{'+NS['a']+'}solidFill')
        E.SubElement(fill, '{'+NS['a']+'}srgbClr', val='000000')
        line = E.SubElement(props, '{'+NS['a']+'}ln'); E.SubElement(line, '{'+NS['a']+'}noFill')
        text = body.find('p:txBody', NS)
        if text is not None: body.remove(text)
    slide=tree.find("p:cSld",NS);old=slide.find("p:bg",NS)
    if old is not None:slide.remove(old)
    bg=E.Element("{"+NS['p']+"}bg");slide.insert(0,bg)
    props=E.SubElement(bg,"{"+NS['p']+"}bgPr");fill=E.SubElement(props,"{"+NS['a']+"}solidFill")
    E.SubElement(fill,"{"+NS['a']+"}srgbClr",val="000000" if colour=="black" else "FFFFFF")
    payload=dict(parts)
    payload['ppt/slides/slide1.xml']=E.tostring(tree,xml_declaration=True,encoding="UTF-8",standalone=True)
    return payload


def _capture_portable_batch(task, state, candidate):
    """Native OOXML copies + existing actual renderer for Linux/macOS hosts.

    Kept groups retain their original coordinate frames. Unsupported outside
    connector dependencies are explicit rather than replaced by shape boxes.
    Windows normally uses its cheaper single-session Office capture instead.
    """
    from .tool_router import render_saved
    import shutil
    request_ref = candidate.get("semantic_composition_guard", {}).get("capture_request")
    if not request_ref:
        return {"status": "NO_MISSING_OWNERS"}
    request = read_json(_ref(task, request_ref)); original = _ref(task, candidate["pptx"])
    folder = Path(candidate["render"]["path"]).parent
    render_folder = safe_path(task,folder.as_posix())
    receipt_path=render_folder/"composition-capture.json"
    records=[]
    if receipt_path.is_file():
        prior=read_json(receipt_path)
        if prior.get('request_hash')==request_ref['sha256']:
            if all(capture_provider_current(r) for r in prior.get('captures',[])):
                ingest_capture(task,state,candidate)
            cache=state.get('semantic_composition',{}).get('captures',{})
            records=[r for r in prior.get('captures',[]) if r['id'] in cache and _cached_capture(task,cache[r['id']],state)]
            if {r['id'] for r in records}=={r['id'] for r in request['captures']}:
                return {"status": "ACTUAL_NATIVE_HOST_CAPTURE"}
        preserved=receipt_path.with_name('composition-capture-'+digest(receipt_path)+'.json')
        if not preserved.exists():shutil.copyfile(receipt_path,preserved)
    directory = render_folder/"owner-captures";directory.mkdir(exist_ok=True)
    with ZipFile(original) as z:
        parts={n:z.read(n) for n in z.namelist()}
    original_tree=E.fromstring(parts["ppt/slides/slide1.xml"])
    capabilities=copy.deepcopy(state['capabilities'])
    main=read_json(_ref(task,candidate['render']))
    if str(main.get('backend','')).lower()=='libreoffice':capabilities['render_preference']='libreoffice'
    elif state.get('render_dispatch',{}).get('mode')=='native_host_tool':
        raise ValueError('This native host must execute the bound composition request; do not repeat failed WSL transport')
    if str(main.get('backend','')).lower() in ('libreoffice','powerpoint'):
        from .native_capture_batch import capture
        return capture(task,state,candidate,request_ref,request,parts,original_tree,capabilities,records)
    for item in request["captures"]:
        if item['id'] in {r['id'] for r in records}:continue
        kept=set(item["leaf_objects"]);keep_ids=set(item["native_ids"])
        path=directory/item["id"];path.mkdir(exist_ok=True)
        isolated=[];views={};host=None
        for colour in ("black","white"):
            pptx=path/(colour+".pptx")
            payload=isolated_parts(parts,original_tree,item,colour)
            from zipfile import ZIP_DEFLATED
            if pptx.exists():
                with ZipFile(pptx) as z:
                    if {n:z.read(n) for n in z.namelist()}!=payload:
                        raise ValueError("Existing isolated native copy differs; preserve it and resume from its cause")
            else:
                with ZipFile(pptx,"x",compression=ZIP_DEFLATED) as z:
                    for name,data in payload.items():z.writestr(name,data)
            output=path/(colour+"-render")
            saved=output/'render.json'
            if saved.is_file():
                host=read_json(saved)
                if host.get('pptx_hash')!=digest(pptx) or host.get('preview_hash')!=digest(output/'Final_preview.png'):
                    raise ValueError('Existing owner capture does not bind its native copy and actual image')
            else:
                if output.exists():
                    serial=1
                    while output.with_name(output.name+'-resume-'+str(serial)).exists():serial+=1
                    output=output.with_name(output.name+'-resume-'+str(serial))
                host=render_saved(pptx,output,capabilities,state['source_size'][0]*4)
            actual=output/"Final_preview.png"
            views[colour]={"path":actual.relative_to(render_folder).as_posix(),"sha256":digest(actual)}
            isolated.append({"path":pptx.relative_to(task).as_posix(),"sha256":digest(pptx),"render":{"path":(output/"render.json").relative_to(task).as_posix(),"sha256":digest(output/"render.json")}})
        records.append({**{k:item[k] for k in ("id","objects","owner_hash")},**views,
                        'measurement': item.get('measurement', 'paint_support'),
                        "native_bindings":[{"id":i,"name":n} for i,n in zip(item['native_ids'],item['leaf_objects'])],
                        "backend":host.get("backend","actual_saved_renderer"),"backend_version":host.get("backend_version"),
                        "provider":"portable_native_copy","provider_script_hash":digest(Path(__file__)),
                        "renderer_script_hash":host.get("renderer_script_hash",digest(Path(__file__))),"isolated_artifacts":isolated})
        partial={"schema":"office-composition-observation-1","pptx_hash":digest(original),"canvas":state['source_size'],
                 "request_hash":request_ref['sha256'],"captures":records,"status":"PARTIAL_VERIFIED_OWNER_BATCH"}
        write_json(render_folder/"composition-capture.json",partial)
        ingest_capture(task,state,candidate)
    receipt={"schema":"office-composition-observation-1","pptx_hash":digest(original),"canvas":state['source_size'],
             "request_hash":request_ref['sha256'],"captures":records,"limits":"Actual alternative renderer; group transforms retained; no Windows Office equivalence inferred"}
    write_json(render_folder/"composition-capture.json",receipt);ingest_capture(task,state,candidate)
    return {"status":"ACTUAL_PORTABLE_CAPTURE","owners":len(records)}


def _response(task, cache, key, size, state=None, retain_native=False):
    from PIL import Image
    import numpy as np
    if key not in cache or not _cached_capture(task, cache[key], state):
        return None
    images = []
    for kind in ("black", "white"):
        with Image.open(_ref(task, cache[key][kind])) as image:
            if retain_native:
                if image.width < size[0]*4 or image.height < size[1]*4:
                    return None
                observed=image.convert('RGB')
            else:
                observed=image.convert('RGB').resize(tuple(size),Image.Resampling.NEAREST)
            images.append(np.asarray(observed,dtype=np.int16))
    if images[0].shape!=images[1].shape:
        return None
    return np.max(np.abs(images[1]-images[0]), axis=2)


def _template(nodes, parent, role, owner, pptx=None):
    node = nodes[owner]; root = nodes[parent]
    cursor = node.getparent()
    while cursor is not None and cursor is not root:
        cursor = cursor.getparent()
    if cursor is None or node is root:
        raise ValueError('A mother role must belong to that instance subtree: ' + owner)
    xf = root.find("p:grpSpPr/a:xfrm", NS)
    if xf is None:
        raise ValueError("Template comparison requires native groups")
    co, ce = xf.find("a:chOff", NS), xf.find("a:chExt", NS)
    ox, oy = float(co.get("x")), float(co.get("y")); w, h = float(ce.get("cx")), float(ce.get("cy"))
    props = copy.deepcopy(node.find("p:spPr", NS) if E.QName(node).localname != 'grpSp' else node.find('p:grpSpPr', NS))
    if props is None:
        raise ValueError("Unsupported template child: " + owner)
    child = props.find("a:xfrm", NS)
    if child is not None:
        off, ext = child.find("a:off", NS), child.find("a:ext", NS)
        for element, key, value in ((off,"x",(float(off.get("x"))-ox)/w), (off,"y",(float(off.get("y"))-oy)/h),
                                    (ext,"cx",float(ext.get("cx"))/w), (ext,"cy",float(ext.get("cy"))/h)):
            element.set(key, str(round(value, 4)))
    # Bind all visual data, not just spPr: styles, text, SVG/image payloads and
    # nested natural parts are part of a reusable mother. Identity labels are
    # instance metadata; actual resource bytes replace local relationship IDs.
    visual = copy.deepcopy(node)
    for item in visual.iter():
        if E.QName(item).localname == 'cNvPr':
            item.attrib.pop('id', None); item.attrib.pop('name', None)
    original_props = visual.find('p:spPr', NS) if E.QName(visual).localname != 'grpSp' else visual.find('p:grpSpPr', NS)
    visual.replace(original_props, props)
    if pptx:
        import hashlib, posixpath
        with ZipFile(pptx) as archive:
            relpath='ppt/slides/_rels/slide1.xml.rels'
            rels={r.get('Id'):r for r in E.fromstring(archive.read(relpath))} if relpath in archive.namelist() else {}
            for item in visual.iter():
                for attr, rid in list(item.attrib.items()):
                    if not attr.startswith('{'+NS['r']+'}'): continue
                    relation=rels.get(rid)
                    if relation is None: raise ValueError('Mother visual resource is unresolved')
                    target=relation.get('Target')
                    if relation.get('TargetMode')=='External': item.set(attr, 'external:'+target)
                    else: item.set(attr, hashlib.sha256(archive.read(posixpath.normpath(posixpath.join('ppt/slides',target)))).hexdigest())
    return {"role": role, "geometry_paint": E.tostring(visual, method='c14n').decode(),
            'resource_context':_scoped_resources(pptx,[node]) if pptx else None}


@verified_resources
def report(task, state, candidate, scope=None):
    if not enabled(state):
        return {"status": "LEGACY_UNBOUND", "critical_pass": None, "items": []}
    if candidate.get("render"):
        ingest_capture(task, state, candidate)
    import numpy as np
    from PIL import Image
    pptx = _ref(task, candidate["pptx"]); nodes, parents, children = _native(pptx)
    resource_hash = _resources(str(pptx), digest(pptx))
    cache = state.get("semantic_composition",{}).get("captures", {}); items = []
    for row in contracts(task, state):
        if scope and not set(row["objects"]) & set(scope):
            continue
        item = {"id": row["id"], "kind": row["kind"], "objects": row["objects"],
                "critical": row.get("critical", True), "status": "required_unmeasured", "passed": False}
        names = row["objects"]
        if not set(names) <= set(nodes):
            item["status"] = "missing_owner"; items.append(item); continue
        if row["kind"] == "order":
            parent, a, b = _branches(*names[:2], parents)
            item.update(status="measured", passed=children[parent].index(a)<children[parent].index(b),
                        values={"saved_back_index": children[parent].index(a), "saved_front_index": children[parent].index(b)})
        elif row["kind"] == "same_template":
            templates = []
            for parent in names:
                mapping = row["roles"][parent]
                templates.append([_template(nodes, parent, role, mapping[role], pptx) for role in sorted(mapping)])
            # Floating native coordinates round to original-equivalent 1e-4
            # fractions; source-supported aspect/pose differences are allowed.
            hashes = [identity(t) for t in templates]
            mother = row["mother"]; mother_nodes, _, _ = _native(_ref(task,mother))
            expected = identity([_template(mother_nodes,mother["group"],role,mother["roles"][role],_ref(task,mother)) for role in sorted(mother["roles"])])
            item.update(status="measured", passed=all(h==expected for h in hashes),
                        values={"normalized_template_hashes": hashes, "immutable_mother_template_hash": expected})
        else:
            groups = _capture_groups(row, nodes, parents)
            responses = [_response(task, cache, _capture_key(nodes, parents, g, pptx, mode), state["source_size"], state,
                                   retain_native=row['kind'] in ('inside','interface')) for g, mode in groups]
            if row['kind'] in ('inside','interface') and all(v is not None for v in responses) and responses[0].shape!=responses[1].shape:
                responses=[None,None]
            if all(v is not None for v in responses):
                if row['kind'] == 'interface':
                    from .source_spacing import evaluate
                    from .boundary_geometry import saved_nodes
                    item.update(evaluate(task,state,row,responses,saved_nodes(pptx,state['source_size']),parents,state['source_size']))
                    items.append(item)
                    continue
                elif row["kind"] == "inside":
                    from scipy.ndimage import distance_transform_edt
                    parent_support = responses[0] < 253; child_core = responses[1] < 253
                    sampling=(state['source_size'][1]/parent_support.shape[0],state['source_size'][0]/parent_support.shape[1])
                    distance = distance_transform_edt(~parent_support,sampling=sampling)
                    bad = child_core & (distance > row.get("tolerance_px", 0.))
                    values = {"child_core_pixels": int(child_core.sum()), "outside_pixels": int(bad.sum()),
                               "max_outside_distance_px": float(distance[child_core].max()) if child_core.any() else None,
                               "measurement_grid":[parent_support.shape[1],parent_support.shape[0]],
                               "distance_unit":"source_px","count_unit":"native_capture_pixel","source_px_per_capture_pixel":list(sampling)}
                    passed = bool(child_core.any()) and not bad.any()
                else:
                    with Image.open(_ref(task, row["mask"])) as image:
                        mask = np.asarray(image.convert("L")) > 127
                    bad = mask & ((responses[0] < 253) if row["kind"] == "opening" else (responses[0] > 2))
                    values = {"original_domain_pixels": int(mask.sum()), "violating_pixels": int(bad.sum()),
                              "coverage": float(1-bad.sum()/mask.sum())}
                    passed = not bad.any()
                yy, xx = np.where(bad)
                roi = [int(xx.min()),int(yy.min()),int(xx.max()-xx.min()+1),int(yy.max()-yy.min()+1)] if len(xx) else None
                item.update(status="measured", passed=bool(passed), values=values, failure_roi=roi)
                if len(xx):
                    folder = Path(pptx).parent/"composition"; folder.mkdir(exist_ok=True)
                    path = folder/(identity(row)+"-residual.png"); Image.fromarray(bad.astype("uint8")*255).save(path)
                    item["residual"] = {"path": path.relative_to(task).as_posix(), "sha256": digest(path)}
        if not item["passed"]:
            item["repair"] = {"cause_candidates": ["source_specification", "recipe", "instance_geometry", "parent_transform", "z_order", "render"],
                              "read_set": names, "write_set_requires_explicit_grant": names,
                              "check_set": [row["id"]], "protected": "All other native fields and approved owners"}
        items.append(item)
    source_ready=True;unresolved=[];missing_ownership=[]
    if state.get('objectives',{}).get('source_semantic_composition'):
        current_scene=read_json(_ref(task,candidate['scene']))
        _,unresolved=_decisions_ready(task,state,current_scene)
        missing_ownership=_ownership_missing(task,state)
        source_ready=not unresolved and not missing_ownership
    critical_pass = source_ready and all(i["passed"] for i in items if i["critical"])
    result = {"schema": VERSION, "pptx_hash": digest(pptx), "source_hash": state["source"]["sha256"],
              "critical_pass": critical_pass, "items": items,
              "source_requirements": {"ready":source_ready,
                  "unresolved_interactions":[p['id'] for p in unresolved],
                  "missing_ownership":[p['id'] for p in missing_ownership]},
              "limits": "Contracts encode observed source intent, not universal semantic truth. Black/white response measures backdrop leakage, not source RGB fidelity; original per-part quality remains independent."}
    write_json(Path(pptx).parent/"semantic-composition-report.json", result)
    return result


def retention_guard(task, state, candidate, allowed=None, strict=False):
    result = report(task, state, candidate)
    if not enabled(state):
        if strict:
            raise ValueError('Final semantic composition requires source bindings; LEGACY_UNBOUND is not acceptance')
        return result
    selected = state.get("selected")
    prior = report(task, state, selected) if selected and selected["pptx"]["sha256"] != candidate["pptx"]["sha256"] else None
    regressions = []
    from .impact_graph import resolve, touches
    _, parents, _ = _native(_ref(task, candidate['pptx']))
    impact = resolve(state, allowed or {}, parents=parents)
    if prior:
        previous = {i["id"]: i for i in prior["items"]}
        for item in result["items"]:
            old = previous.get(item["id"])
            if not old:
                continue
            touched = touches(item['objects'], impact)
            if old["passed"] and not item["passed"]:
                regressions.append(item["id"])
            elif touched and item["status"] != "measured":
                regressions.append(item["id"])
            elif touched and old["status"] == "measured" and not old["passed"]:
                key = "outside_pixels" if item["kind"] == "inside" else "violating_pixels"
                if item.get("values", {}).get(key, 0) > old.get("values", {}).get(key, 0):
                    regressions.append(item["id"])
                if item["kind"] == "inside":
                    now=item.get("values",{}).get("max_outside_distance_px")
                    earlier=old.get("values",{}).get("max_outside_distance_px")
                    if now is not None and earlier is not None and now > earlier:
                        regressions.append(item["id"])
    if regressions or strict and not result["critical_pass"]:
        failed = [{k: i.get(k) for k in ("id", "kind", "status", "failure_roi", "values")} for i in result["items"] if i["critical"] and not i["passed"]]
        raise ValueError("Critical semantic composition cannot regress/be averaged/waived: " + repr(failed[:6]))
    return result


def partial_progress(task, state, candidate, allowed):
    """Machine evidence for an increment; no prose-only partial success."""
    after=retention_guard(task,state,candidate,allowed)
    before=report(task,state,state['selected']);previous={i['id']:i for i in before['items']}
    gains=[];failed=set()
    for item in after['items']:
        if item['critical'] and not item['passed']:failed.update(item['objects'])
        old=previous.get(item['id'])
        if not old or item['status']!='measured':continue
        if item['passed'] and not old['passed']:gains.append(item['id']);continue
        key='outside_pixels' if item['kind']=='inside' else 'violating_pixels'
        if old['status']=='measured' and item.get('values',{}).get(key,0)<old.get('values',{}).get(key,0):gains.append(item['id'])
    nodes,parents,_=_native(_ref(task,candidate['pptx']))
    from .impact_graph import resolve, touches
    remaining={n:fields for n,fields in allowed.items()
               if touches(failed, resolve(state, {n:fields}, parents=parents))}
    return {'gains':gains,'remaining_changes':remaining,'failed_objects':sorted(failed),'actual':after}


def register_failures(task, state, candidate):
    """Feed located program findings into the ordinary repair queue, no new loop."""
    result = report(task, state, candidate)
    if not enabled(state):
        return result
    scene = read_json(_ref(task, candidate["scene"])); mapping = {o["id"]: o for o in scene["objects"]}
    owners = {c["id"]: c for c in state["analysis"]["components"]}
    from .external_sync import actual_name
    native_owners = {actual_name(state,cid):cid for cid in owners}
    for item in result["items"]:
        iid = "composition-" + identity(item["id"])[:14]
        known = next((i for i in state["issues"] if i["id"] == iid), None)
        if item["passed"]:
            if known:
                evidence = {"candidate": candidate["pptx"]["sha256"], "measurement": item}
                if candidate["pptx"]["sha256"] == (state.get("selected") or {}).get("pptx", {}).get("sha256"):
                    known["status"] = "resolved"; known["resolution"] = evidence
                    known.pop("pending_resolution",None)
                else:
                    known["pending_resolution"] = evidence
            continue
        name = item["objects"][0]
        while name not in native_owners and mapping.get(name, {}).get("parent"):
            name = mapping[name]["parent"]
        name=native_owners.get(name,name)
        if name not in owners:
            raise ValueError("A composition finding must trace to its semantic component")
        found = {"id": iid, "owner": name, "roi": item.get("failure_roi") or owners[name]["roi"],
                 "property": "composition:"+item["kind"], "severity": "major", "status": "open",
                 "expected": "Original-bound contract " + item["id"], "actual": item,
                 "composition_contract": item["id"], "source": "program_actual_native_composition", "attempt_count": 0,
                 "evidence": {"candidate": candidate["pptx"]["sha256"], "measurement": item["id"]}}
        if known:
            known.update(actual=item, status="open")
        else:
            state["issues"].append(found)
    candidate["semantic_composition_actual"] = result
    return result
