"""Hash-bound enlarged original/current windows retaining semantic neighbors."""
import math
from .common import identity,read_json,safe_path,digest

def windows(task,state,candidate,contract,native):
    from .execution_contract import resource
    from . import agent_runtime as a
    if not candidate.get('render') or not candidate.get('preview'):
        return {'passed':False,'status':'required_unmeasured','next':'actual current render before contextual layout checks'}
    receipt=read_json(resource(task,candidate['render']));resource(task,candidate['preview'])
    if receipt.get('status')!='PASS' or receipt.get('pptx_hash')!=candidate['pptx']['sha256']:
        raise ValueError('Context magnification requires the actual current saved render')
    canvas=state['source_size'];es={e['id']:e for e in contract['elements']};cs={c['id']:c for c in contract['containers']};items=[]
    for row in contract['containers']:
        if not row['members']:continue
        x,y,w,h=row['source_bbox'];pad=max(12.,min(w,h)*.5)
        region=[max(0.,x-pad),max(0.,y-pad),min(canvas[0],x+w+pad),min(canvas[1],y+h+pad)]
        neighbors=[e for e in es.values() if e['source_bbox'][0]<region[2] and e['source_bbox'][0]+e['source_bbox'][2]>region[0] and e['source_bbox'][1]<region[3] and e['source_bbox'][1]+e['source_bbox'][3]>region[1]]
        names={n for e in neighbors for n in ([e['mathematical_owner']] if e.get('mathematical_owner') else e['objects'])}
        names.update(c['domain']['object'] for c in cs.values() if c['id']==row['id'] or c['id'] in row['members'] if c['domain'].get('object'))
        # Include the current owners as well: a displaced object must not fall
        # outside its original-only crop and disappear from contextual review.
        for name in names:
            if name not in native or native[name].get('frame') is None:continue
            a0,b0,c0,d0=native[name]['frame'];region=[min(region[0],max(0.,a0-4)),min(region[1],max(0.,b0-4)),max(region[2],min(canvas[0],a0+c0+4)),max(region[3],min(canvas[1],b0+d0+4))]
        roi=[region[0],region[1],region[2]-region[0],region[3]-region[1]]
        key='layout-context-'+identity({'source':state['source'],'preview':candidate['preview'],'roi':roi})[:20]
        views=a._preview(task,state,candidate,roi,key)
        if len(views)!=2 or any(digest(safe_path(task,v['path']))!=v['sha256'] for v in views):raise ValueError('Original/current enlarged context evidence changed')
        items.append({'container':row['id'],'neighbor_objects':sorted(names),'roi':roi,'views':views,
            'mapping':'same original coordinate window and display scale for both roles; no local registration',
            'comparison_unit':'source_px','passed':True})
    return {'passed':True,'status':'CURRENT_CONTEXT_WINDOWS_BOUND','pptx_hash':candidate['pptx']['sha256'],
        'preview_hash':candidate['preview']['sha256'],'source_hash':state['source']['sha256'],'items':items,
        'scope':'Deterministic coordinate/mapping and contextual evidence coverage; semantic interpretation remains the host task'}
