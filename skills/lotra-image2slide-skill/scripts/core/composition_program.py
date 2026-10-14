"""Expand host source-layer decisions into bounded executable pair contracts."""
from .common import identity,read_json,safe_path

def bind(task,request):
    from . import agent_runtime as a,semantic_composition as sc
    from .external_sync import actual_name
    task,state=a._state(task);candidate=state.get('active_candidate') or state.get('selected')
    if request.get('source_hash')!=state['source']['sha256'] or request.get('baseline_hash')!=candidate['pptx']['sha256']:
        raise ValueError('Source layer decisions require current immutable source and actual native baseline')
    scene=read_json(safe_path(task,candidate['scene']['path']));nodes={o['id']:o for o in scene['objects']}
    parents={n:o.get('parent') for n,o in nodes.items()};layers={r['parent']:r for r in request.get('layers',[])}
    if len(layers)!=len(request.get('layers',[])):raise ValueError('One complete layer decision per parent')
    for parent,row in layers.items():
        expected={n for n,p in parents.items() if p==parent}
        if set(row.get('back_to_front',[]))!=expected or len(row['back_to_front'])!=len(expected):
            raise ValueError('Layer decision must include each actual direct sibling exactly once')
        if not row.get('source_evidence') or row.get('reliability') not in ('observed','inferred_approved_design'):
            raise ValueError('Agent must explain the source reading or approved-design inference')
        sc._original_view(task,state,row['source_view'])
        if row['reliability']=='inferred_approved_design' and row.get('approved_native_sha256')!=state.get('quality_intent',{}).get('approved',{}).get('pptx',{}).get('sha256'):
            raise ValueError('Fine inferred layers require the frozen source-bound approved artifact')
    _,pairs=sc._decisions_ready(task,state,scene);contracts=[];decisions=[]
    for pair in pairs:
        aa,bb=pair['objects'];base={'id':pair['id'],'objects':pair['objects'],'source_hash':state['source']['sha256']}
        if parents[aa]==bb or parents[bb]==aa:
            parent=bb if parents[aa]==bb else aa
            row=layers.get(parent)
            if not row:raise ValueError('Missing source group layer declaration: '+parent)
            decisions.append({**base,'decision':'hierarchy','contracts':[],'source_view':row['source_view'],
                'evidence':'Actual group membership only; physical contact remains independently checked. '+row['source_evidence']})
        else:
            parent=parents[aa]
            if parents[bb]!=parent:raise ValueError('Unsupported direct interaction discovery')
            row=layers.get(parent)
            if not row:raise ValueError('Missing source sibling layer declaration: '+str(parent))
            order=row['back_to_front'];back,front=sorted((aa,bb),key=order.index)
            cid='source-layer-'+identity({'source':state['source']['sha256'],'parent':parent,'back':back,'front':front})[:24]
            contracts.append({'schema':sc.VERSION,'kind':'order','id':cid,'source_hash':state['source']['sha256'],
                'canvas':state['source_size'],'objects':[back,front],'critical':True,'source_view':row['source_view'],
                'source_evidence':row['source_evidence'],'interpretation_reliability':row['reliability']})
            decisions.append({**base,'decision':'ordered','contracts':[cid],'source_view':row['source_view'],
                'evidence':'Program expansion of the host-declared source layer sequence. This order says nothing about physical contact.'})
    # Resume an interrupted compiler without duplicating immutable constraints.
    existing={r['id']:r for r in sc.contracts(task,state)};fresh=[]
    for row in contracts:
        if row['id'] in existing:
            if identity(existing[row['id']])!=identity(row):raise ValueError('Existing source-layer constraint differs; use explicit source correction')
        else:fresh.append(row)
    contracts=fresh
    # Public binder enforces limits and participant identities on every batch.
    for start in range(0,len(contracts),16):sc.bind(task,{'contracts':contracts[start:start+16]})
    for start in range(0,len(decisions),128):sc.bind(task,{'decisions':decisions[start:start+128]})
    ownership=[]
    for comp in state['analysis']['components']:
        name=actual_name(state,comp['id']);row=layers.get(name)
        if name in nodes and nodes[name]['render_type']=='group' and row:
            ownership.append({'owner':comp['id'],'nature':'container','contracts':[],
                'source_hash':state['source']['sha256'],'source_view':row['source_view'],
                'evidence':'Semantic container with no own native paint. Every descendant remains independently covered by quality, native, frame and interface programs. '+row['source_evidence']})
    if ownership:sc.bind(task,{'ownership':ownership})
    return {'status':'SOURCE_LAYER_PROGRAM_BOUND','generated_order_contracts':len(contracts),'interaction_decisions':len(decisions),'container_owners':len(ownership)}
