"""Typed, content-addressed program and host observations; no empty success."""
import copy,math
from .common import digest,identity,read_json,write_json,safe_path,writer

VERSION='quality-observation-ledger-1'

def context_roi(state,item):
    """Local context includes nearby peers and bounded parent boundary facts."""
    x,y,w,h=item['roi'];cw,ch=state['source_size']
    pad=max(8.,.08*max(w,h))
    left,top,right,bottom=max(0,x-pad),max(0,y-pad),min(cw,x+w+pad),min(ch,y+h+pad)
    peers=[]
    for row in state.get('quality_intent',{}).get('items',[]):
        if row['id']==item['id'] or not row.get('roi'):continue
        rx,ry,rw,rh=row['roi']
        if rw*rh>4*w*h:continue # Large ancestors retain numeric/semantic context.
        if rx<right and rx+rw>left and ry<bottom and ry+rh>top:
            peers.append(row)
    if peers:
        left=max(0,min([left]+[r['roi'][0] for r in peers]))
        top=max(0,min([top]+[r['roi'][1] for r in peers]))
        right=min(cw,max([right]+[r['roi'][0]+r['roi'][2] for r in peers]))
        bottom=min(ch,max([bottom]+[r['roi'][1]+r['roi'][3] for r in peers]))
    return [left,top,right-left,bottom-top],peers

def source_context_view(task,state,item):
    from .resource_facts import image_region
    from .context_efficiency import crop_file
    from PIL import Image
    roi,_=context_roi(state,item);x,y,w,h=roi
    box=(max(0,math.floor(x)),max(0,math.floor(y)),min(state['source_size'][0],math.ceil(x+w)),min(state['source_size'][1],math.ceil(y+h)))
    source=safe_path(task,state['source']['path'])
    with image_region(source,[('crop',box),('resize',((box[2]-box[0])*2,(box[3]-box[1])*2),Image.Resampling.LANCZOS)],state['source']['sha256']) as crop:
        file,_=crop_file(task,crop)
    return {'path':file.relative_to(task).as_posix(),'sha256':digest(file),'roi':[box[0],box[1],box[2]-box[0],box[3]-box[1]],'scale':2,'role':'unchanged_original_context'}

def candidate_view(task,state,candidate,item):
    from PIL import Image
    roi,_=context_roi(state,item)
    x,y,w,h=roi;size=state['source_size']
    box=(max(0,math.floor(x)),max(0,math.floor(y)),min(size[0],math.ceil(x+w)),min(size[1],math.ceil(y+h)))
    preview=safe_path(task,candidate['preview']['path'])
    if digest(preview)!=candidate['preview']['sha256']:raise ValueError('Actual semantic observation preview changed')
    key=identity({'preview':candidate['preview'],'source_canvas':size,'box':box,'scale':2,'implementation':digest(__file__)})
    path=task/'observations/views'/(key+'.png')
    if not path.is_file():
        path.parent.mkdir(parents=True,exist_ok=True)
        from .resource_facts import image_region
        with image_region(preview,[('resize',size,Image.Resampling.LANCZOS),('crop',box),
            ('resize',(max(1,(box[2]-box[0])*2),max(1,(box[3]-box[1])*2)),Image.Resampling.LANCZOS)],candidate['preview']['sha256']) as crop:
            from .context_efficiency import crop_file
            cached,_=crop_file(task,crop)
            import shutil
            shutil.copyfile(cached,path)
        write_json(path.with_suffix('.json'),{'sha256':digest(path),'key':key})
    else:
        receipt=read_json(path.with_suffix('.json'))
        if receipt.get('key')!=key or digest(path)!=receipt['sha256']:raise ValueError('Retained semantic observation crop changed')
    return {'path':path.relative_to(task).as_posix(),'sha256':digest(path),'preview_hash':candidate['preview']['sha256'],
            'roi':[box[0],box[1],box[2]-box[0],box[3]-box[1]],'scale':2}

def observation_basis(task,state,candidate,item):
    from .appearance_metrics import native_signatures
    native=safe_path(task,candidate['pptx']['path'])
    if digest(native)!=candidate['pptx']['sha256']:raise ValueError('Actual semantic observation native file changed')
    signatures=native_signatures(str(native),candidate['pptx']['sha256'])
    view=candidate_view(task,state,candidate,item)
    # Other objects may change without invalidating an unchanged local source,
    # policy, native dependency and fixed-view pixel observation.
    children=[r for r in state.get('quality_intent',{}).get('items',[]) if r.get('semantic_parent')==item['id']]
    units=state.get('quality',{}).get('units',{})
    semantics={uid:units[uid]['features'] for row in [item]+children for uid in row.get('quality_units',[]) if uid in units}
    roi,peers=context_roi(state,item)
    original_context=source_context_view(task,state,item)
    parents=[r for r in state.get('quality_intent',{}).get('items',[]) if r['id']==item.get('semantic_parent')]
    return identity({'source':state['source'],'policy_item':item,'semantic_children':children,'source_properties':semantics,
        'context_roi':roi,'peers':peers,'parent_facts':[{k:r.get(k) for k in ('id','roi','purpose','source_facts')} for r in parents],
        'source_context':original_context['sha256'],
        'peer_native':{n:signatures.get(n) for row in peers for n in row.get('objects',[])},'implementation':digest(__file__),
        'native':{n:signatures.get(n) for n in item['objects']},'view_pixels':view['sha256']})

def packet(task,state,candidate,limit=8):
    from .quality_intent import validate
    plan=validate(task,state,candidate);observations=state.get('quality_observations',{}).get('host',{})
    from .dependency_context import schedule
    ordered,scheduling=schedule(task,state,candidate,plan['items'])
    missing=[]
    for item in ordered:
        # Every named child has an independent source/current observation.
        basis=observation_basis(task,state,candidate,item);old=observations.get(item['id'])
        if not old or old.get('basis')!=basis or old.get('outcome')!='matched':
            missing.append({'id':item['id'],'purpose':item['purpose'],'source_facts':item['source_facts'],
                'covered_policies':[{'id':r['id'],'source_facts':r['source_facts'],'quality_units':r['quality_units']} for r in plan['items'] if r.get('semantic_parent')==item['id']],
                'source_view':item['source_view'],'candidate_view':candidate_view(task,state,candidate,item),
                'source_context_view':source_context_view(task,state,item),
                'context':{'roi':context_roi(state,item)[0],'nearby_policies':[r['id'] for r in context_roi(state,item)[1]],'parent':item.get('semantic_parent')},
                'basis':basis,'prior_outcome':old.get('outcome') if old else None})
    return {'schema':VERSION,'kind':'quality_semantic_observation','source_hash':state['source']['sha256'],
        'candidate_hash':candidate['pptx']['sha256'],'remaining':len(missing),'items':missing[:limit],'scheduling':scheduling,
        'instruction':'Observe source and actual result; report concrete semantic facts/defects. Programs measure numbers separately. No inferred numeric success or copied candidate-as-source.'}

def bind_host(task,request):
    from . import agent_runtime as a
    from .quality_intent import validate
    task,state=a._state(task);candidate=state.get('active_candidate') or state['selected'];plan=validate(task,state,candidate)
    items={r['id']:r for r in plan['items']}
    if request.get('source_hash')!=state['source']['sha256'] or request.get('candidate_hash')!=candidate['pptx']['sha256']:
        raise ValueError('Host observation source/candidate identity mismatch')
    rows=request.get('items',[])
    if not rows or len({r.get('id') for r in rows})!=len(rows):raise ValueError('Unique actual host observations required')
    ledger=copy.deepcopy(state.get('quality_observations',{'schema':VERSION,'host':{},'program':{},'history':[]}))
    for row in rows:
        item=items.get(row.get('id'))
        if not item or row.get('outcome') not in ('matched','issue','uncertain') or not row.get('actual_facts') or not row.get('evidence'):
            raise ValueError('Describe actual seen facts and a truthful outcome for each named policy item')
        view=candidate_view(task,state,candidate,item);basis=observation_basis(task,state,candidate,item)
        original_context=source_context_view(task,state,item)
        if row.get('basis')!=basis or row.get('source_view_sha256')!=item['source_view']['sha256'] or row.get('candidate_view_sha256')!=view['sha256']:
            raise ValueError('Observation views/dependencies are stale or belong to another item')
        if row.get('source_context_view_sha256')!=original_context['sha256']:
            raise ValueError('Original/current semantic observation requires the same nearby context')
        record={**copy.deepcopy(row),'kind':'host_semantic','source_hash':state['source']['sha256'],
                'candidate_hash_at_observation':candidate['pptx']['sha256'],'views':[item['source_view'],original_context,view]}
        previous=ledger['host'].get(row['id'])
        if previous and previous!=record:ledger['history'].append(previous)
        ledger['host'][row['id']]=record
    with writer(task):
        state['quality_observations']=ledger;state.pop('quality_result',None);state.pop('acceptance',None)
        a._event(task,'actual_semantic_observations_recorded',{'count':len(rows),'candidate':candidate['pptx']['sha256']})
        a._save(task,state)
    return {'status':'HOST_OBSERVATIONS_RECORDED','recorded':len(rows),'total':len(ledger['host'])}

def record_program(state,kind,object_id,result,basis):
    if not isinstance(result,dict) or not result:raise ValueError('A program observation needs actual structured results')
    ledger=state.setdefault('quality_observations',{'schema':VERSION,'host':{},'program':{},'history':[]})
    key=kind+':'+object_id
    record={'id':key,'kind':'program_'+kind,'object':object_id,'basis':basis,'result':copy.deepcopy(result)}
    old=ledger['program'].get(key)
    if old and old!=record:ledger['history'].append(old)
    ledger['program'][key]=record
    return record

def host_status(task,state,candidate,plan):
    rows=[];ledger=state.get('quality_observations',{}).get('host',{})
    policies={r['id']:r for r in plan['items']}
    for item in plan['items']:
        reviewed=item
        row=ledger.get(reviewed['id']);basis=observation_basis(task,state,candidate,reviewed)
        valid=bool(row and row.get('basis')==basis and row.get('outcome')=='matched')
        rows.append({'id':item['id'],'passed':valid,'status':'CONFIRMED' if valid else 'OBSERVATION_REQUIRED',
                     'reviewed_root':reviewed['id'],'scope':'individual_source_region',
                     'actual_facts':row.get('actual_facts') if row else None})
    return rows
