"""Compile hash-bound native operator proposals into the current repair action."""
import copy
from .common import read_json,write_json,digest,identity,safe_path


def prepare(task,request):
    from . import agent_runtime as a,source_quality as q
    task,state=a._state(task);packet=state.get('packet') or {};selected=state.get('selected')
    if packet.get('kind')!='repair' or packet.get('packet_id')!=request.get('packet_id'):
        raise ValueError('Use the current repair packet; its target is the raw issue id')
    if state.get('pending_built') or not selected or request.get('baseline_hash')!=selected['pptx']['sha256']:
        raise ValueError('Finish the pending actual result and bind the saved selected baseline')
    issue=next(i for i in state['issues'] if i['id']==packet['target'] and i['status']=='open')
    if not request.get('expected_effect'):raise ValueError('Describe the source-specific expected effect')
    q.validate_cause(task,state,issue,request['cause'])
    descriptors=request.get('proposals',[])
    if not 1<=len(descriptors)<=16:raise ValueError('Compile at most16 bounded native proposals')
    methods={};allowed={};origins=[]
    def replace(method,node):
        found=0
        for i,old in enumerate(method.get('objects',[])):
            if old['id']==node['id']:method['objects'][i]=copy.deepcopy(node);found+=1
        for child in method.get('children',[]):found+=replace(child['method'],node)
        return found
    for descriptor in descriptors:
        file=safe_path(task,descriptor['path'])
        if digest(file)!=descriptor['sha256']:raise ValueError('Native operator proposal changed')
        proposal=read_json(file)
        if proposal.get('baseline_hash')!=selected['pptx']['sha256']:
            raise ValueError('A proposal from another saved version cannot enter this action')
        if proposal.get('source_hash',state['source']['sha256'])!=state['source']['sha256']:
            raise ValueError('A proposal from another original cannot enter this action')
        unit=q.unit(state,proposal['unit']);node=proposal['object'];grants=proposal['allowed_changes']
        bound=bool(unit and node['id'] in unit['objects'])
        if unit and not bound and set(grants.get(node['id'],[]))=={'style.fill'}:
            from .source_material_response import owned_leaf
            scene=read_json(safe_path(task,selected['scene']['path']))
            bound=owned_leaf(unit,{o['id']:o for o in scene['objects']},node['id'])
        if not bound or set(grants)!={node['id']}:
            raise ValueError('Native leaf proposal needs its independent bound original unit')
        if node['id'] in allowed:raise ValueError('Only one proposal per native object in an action')
        forbidden={'replace_component','add','remove','group','ungroup','bbox','style','content','structure'}
        if not grants[node['id']] or set(grants[node['id']])&forbidden:
            raise ValueError('This route applies explicit native leaf fields, not broad restructuring')
        from .native_commit import NATIVE_LEAF_FIELDS,_table_cell_field
        if any(field not in NATIVE_LEAF_FIELDS and _table_cell_field(field) is None for field in grants[node['id']]) or set(grants[node['id']])&{'replace_native','group_translate'}:
            raise ValueError('Compile only existing native leaf writer fields; metadata/inference remains in the proposal, not a native write grant')
        matching=[i for i in state['issues'] if i['status']=='open' and i['owner']==unit['owner']
                  and i.get('quality_unit')==unit['id'] and i['property']==issue['property']
                  and i.get('cause_hint')==issue.get('cause_hint')]
        if not matching:raise ValueError('Locate this exact source-unit defect before batching its proposal')
        owner=unit['owner'];method=methods.setdefault(owner,copy.deepcopy(state['methods'][owner]))
        count=replace(method,node)
        if count==0:
            # A recipe or native snapshot may not expose editable leaf data.
            # Keep its actual complete instantiated objects, not a fresh recipe
            # approximation. The existing submit guards compare every field.
            method={'objects':copy.deepcopy(state['built'][owner]['objects'])}
            for key in ('source_bindings','source_fit'):
                if key in state['methods'][owner]:method[key]=copy.deepcopy(state['methods'][owner][key])
            methods[owner]=method;count=replace(method,node)
        if count!=1:raise ValueError('Native proposal object must have exactly one method owner')
        allowed.update(grants);origins.append({'unit':unit['id'],'proposal':descriptor,'object':node['id']})
    if issue['owner'] not in methods:raise ValueError('Action must address its primary located owner')
    q.protect_scope(state,issue,allowed)
    # The regular submit path owns construction, exact native preservation,
    # shared-cause limits, actual rendering and independent retention gates.
    result={'packet_id':packet['packet_id'],'method':methods.pop(issue['owner']),
            'related_methods':methods,'allowed_changes':allowed,'cause':request['cause'],
            'expected_effect':request['expected_effect']}
    record={'status':'BOUNDED_NATIVE_ACTION_REQUIRES_REGULAR_SUBMIT','baseline_hash':selected['pptx']['sha256'],
            'source_hash':state['source']['sha256'],'origins':origins,'action':result,
            'limits':'This compiles proposals; it neither applies an edit nor accepts a result. Submit action through the current agent packet, then observe each changed part and affected relation.'}
    write_json(task/'scratch/native-proposal-action.json',record)
    return record
