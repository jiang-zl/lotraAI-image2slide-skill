"""Compute change impact from saved native facts and declared relationships.

The graph schedules work; it cannot close source/native coverage obligations.
Unknown changes invalidate globally. Final inventory is always complete.
"""
from collections import defaultdict, deque
from pathlib import Path
from .common import canonical, digest, identity, read_json, write_json, safe_path

VERSION='dependency-context-1'


def _facts(task,state,candidate):
    from .boundary_geometry import saved_nodes
    from .mathml import NS
    from lxml import etree as E
    nodes=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size'])
    result={}; parents={}
    for name,row in nodes.items():
        xml=E.tostring(row['node']).decode()
        if row['tag']=='grpSp':
            # A child's edit is a parent check, not a parent transform edit.
            # Group transform/style changes still invalidate every descendant.
            xml=''.join(E.tostring(child).decode() for child in row['node'] if E.QName(child).localname not in ('sp','grpSp','cxnSp','pic','graphicFrame'))
        result[name]=identity({'xml':xml,
                              'frame':row['frame'], 'matrix':row['matrix'].tolist() if row['matrix'] is not None else None,
                              'parent_matrix':row['parent_matrix'].tolist(), 'error':row['error']})
        if row.get('parent_name'):parents[name]=row['parent_name']
        table=row['node'].find('a:graphic/a:graphicData/a:tbl',NS)
        if table is not None:
            for ri,tr in enumerate(table.findall('a:tr',NS)):
                for ci,cell in enumerate(tr.findall('a:tc',NS)):
                    key=name+'/cell/'+str(ri)+'/'+str(ci)
                    result[key]=identity({'xml':E.tostring(cell).decode(),'table':result[name]})
                    parents[key]=name
    return result,parents


def graph(state,native_facts=None,native_parents=None):
    nodes=set((native_facts or {}).keys()); edges=defaultdict(set); members=defaultdict(set)
    def edge(dependency,consumer):
        if isinstance(dependency,str) and isinstance(consumer,str) and dependency and consumer:
            nodes.update((dependency,consumer));edges[dependency].add(consumer)
    for child,parent in (native_parents or {}).items():
        edge(child,parent);members[parent].add(child)
    for comp in (state.get('analysis') or {}).get('components',[]):
        owner=comp['id'];nodes.add(owner)
        for dep in comp.get('depends_on',[]):edge(dep,owner)
        for obj in state.get('built',{}).get(owner,{}).get('objects',[]):
            edge(obj['id'],owner);members[owner].add(obj['id'])
    for item in state.get('quality_intent',{}).get('items',[]):
        owner=item['id'];nodes.add(owner)
        for obj in item.get('objects',[]):edge(obj,owner);members[owner].add(obj)
        if item.get('semantic_parent'):
            edge(owner,item['semantic_parent']);members[item['semantic_parent']].add(owner)
        for unit in item.get('quality_units',[]):edge(unit,owner)
    for uid,unit in state.get('quality',{}).get('units',{}).items():
        nodes.add(uid)
        owner=unit.get('owner') or unit.get('component')
        if owner:edge(uid,owner)
        for obj in unit.get('objects',[]):edge(obj,uid)
    # Relationships, independently from the containment tree. Bind every
    # declared participant; unrecognized relation layouts force global work.
    unknown=False
    def relations(value):
        nonlocal unknown
        if isinstance(value,dict):
            if isinstance(value.get('kind'),str) or isinstance(value.get('type'),str):
                peers=[value[k] for k in ('source','target','from','to','a','b','left','right','container','child','owner','object','connector') if isinstance(value.get(k),str) and value[k] in nodes]
                peers+= [x for k in ('members','objects','participants') for x in value.get(k,[]) if isinstance(x,str) and x in nodes]
                if len(set(peers))>=2:
                    for a in set(peers):
                        for b in set(peers)-{a}:edge(a,b)
                elif any(k in value for k in ('participants','members','objects','source','target','from','to')):
                    unknown=True
            for child in value.values():relations(child)
        elif isinstance(value,list):
            for child in value:relations(child)
    for key in ('scene_relations','relative_layout','neighbor_contract','connection_contract','containment_contract'):
        relations(state.get(key,[]))
    relations((state.get('analysis') or {}).get('scene_relations',[]))
    return {'schema':VERSION,'nodes':sorted(nodes),'edges':{k:sorted(v) for k,v in edges.items()},
            'members':{k:sorted(v) for k,v in members.items()},'unknown_relations':unknown,
            'authority':'Change scheduling only; complete original/native/table-cell reconciliation remains mandatory.'}


def affected(model,changed):
    known=set(model['nodes']);changed=set(changed)
    if changed-known or model.get('unknown_relations'):
        return {'objects':sorted(known),'global':True,'reason':'unknown change/dependency: conservative complete scope'}
    descendants=set(changed);queue=deque(changed)
    # Explicitly changed containers may move all their descendants. Derived
    # parent checks alone do not mark every unchanged sibling for re-reading.
    while queue:
        name=queue.popleft()
        for child in model.get('members',{}).get(name,[]):
            if child not in descendants:descendants.add(child);queue.append(child)
    queue=deque(descendants);seen=set(descendants)
    while queue:
        name=queue.popleft()
        if name not in seen:seen.add(name)
        for dep in model.get('edges',{}).get(name,[]):
            if dep not in seen:seen.add(dep);queue.append(dep)
    return {'objects':sorted(seen),'global':bool(changed),'reason':'saved changes and relationship closure'}


def schedule(task,state,candidate,items):
    """Prioritize affected observations without dropping any outstanding unit."""
    reference=state.get('context_dependencies')
    if not reference:return list(items),{'mode':'complete','reason':'No current dependency evidence'}
    file=safe_path(task,reference['path'])
    if digest(file)!=reference['sha256']:raise ValueError('Dependency scheduling evidence changed')
    model=read_json(file)
    if model.get('source_hash')!=state['source']['sha256'] or model.get('pptx_hash')!=candidate['pptx']['sha256']:
        return list(items),{'mode':'complete','reason':'Changed original/native dependency identity'}
    if model.get('unknown_relations'):
        return list(items),{'mode':'complete','reason':'Unknown relations require conservative complete work'}
    impacted=set(model['impact']['objects'])
    first=[];remaining=[]
    for item in items:
        target=first if item['id'] in impacted or set(item.get('objects',[]))&impacted or item.get('semantic_parent') in impacted else remaining
        target.append(item)
    return first+remaining,{'mode':'affected_first','prioritized':len(first),'all_units_retained':len(items),
                             'authority':'Order only; each stale/missing unit still needs its own checks'}


def record(task,state):
    candidate=state.get('active_candidate') or state.get('selected')
    if not candidate or not candidate.get('pptx'):return None
    file=safe_path(task,candidate['pptx']['path'])
    current_hash=digest(file)
    if current_hash!=candidate['pptx']['sha256']:raise ValueError('Cannot schedule stale native bytes')
    previous_file=safe_path(task,'context/Native-facts.json')
    before=read_json(previous_file) if previous_file.is_file() else None
    if before and before.get('hash')!=identity(before.get('data')):raise ValueError('Stored dependency facts changed')
    from . import boundary_geometry, native_markup, mathml
    code=identity({name:digest(module.__file__) for name,module in
                   (('graph',__import__(__name__,fromlist=['VERSION'])),('geometry',boundary_geometry),('markup',native_markup),('math',mathml))})
    discovery_error=None
    if before and before['data'].get('pptx_hash')==current_hash and before['data'].get('implementation')==code:
        facts=before['data']['facts'];parents=before['data']['parents']
        discovery_error=before['data'].get('discovery_error')
    else:
        try:facts,parents=_facts(task,state,candidate)
        except (ValueError,KeyError,TypeError) as error:
            # Retain invalid intermediate files for the repair loop. Discovery
            # failure can never authorize an incremental-only check scope.
            facts,parents={},{}
            discovery_error={'type':type(error).__name__,'reason':str(error)}
    source_policy=identity({k:state.get(k) for k in ('source','analysis','source_specs','quality','quality_intent','execution_contract','objectives','library_lineage','scene_relations','relative_layout','neighbor_contract','connection_contract','containment_contract')})
    changed=sorted(k for k in set(facts)|(set(before['data']['facts']) if before else set())
                   if not before or facts.get(k)!=before['data']['facts'].get(k))
    model=graph(state,facts,parents)
    if not facts:model['unknown_relations']=True
    impact=affected(model,changed)
    if not before or before['data'].get('source_policy')!=source_policy or before['data'].get('preview')!=candidate.get('preview'):
        impact={'objects':model['nodes'],'global':True,'reason':'new/changed source facts, policies or authorized constraints'}
    data={'pptx_hash':current_hash,'preview':candidate.get('preview'),'facts':facts,'parents':parents,'source_policy':source_policy,'implementation':code,'discovery_error':discovery_error}
    write_json(previous_file,{'data':data,'hash':identity(data)})
    result={**model,'source_hash':state['source']['sha256'],'pptx_hash':current_hash,
            'changed_native':changed,'impact':impact,'implementation':code,'discovery_error':discovery_error}
    target=safe_path(task,'context/Dependencies.json');write_json(target,result)
    return {'path':'context/Dependencies.json','sha256':digest(target),
            'changed_native':len(changed),'affected_objects':len(impact['objects']),'global_check':impact['global']}
