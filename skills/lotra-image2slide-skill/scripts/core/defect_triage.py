"""Bounded source/result residual proposals, separate from semantic judgement."""
import math

def hotspots(source, rendered, source_size, components, limit=6):
    import numpy as np
    from PIL import Image
    from scipy.ndimage import gaussian_filter, sobel, label, find_objects
    with Image.open(source) as im:
        width=min(1600,source_size[0])
        a=np.asarray(im.convert('RGB').resize((width,round(width*source_size[1]/source_size[0])),Image.Resampling.LANCZOS),float)
    with Image.open(rendered) as im:
        b=np.asarray(im.convert('RGB').resize((a.shape[1],a.shape[0]),Image.Resampling.LANCZOS),float)
    ga,gb=a.mean(2),b.mean(2)
    # Low-frequency colour/layout residual and contour residual propose ROIs.
    # No scalar can prove a missing road or a wrong scientific relation.
    colour=np.abs(gaussian_filter(a,(2,2,0))-gaussian_filter(b,(2,2,0))).mean(2)/255
    edge=np.abs(np.hypot(sobel(ga,0),sobel(ga,1))-np.hypot(sobel(gb,0),sobel(gb,1)))/2040
    score=.65*colour+.35*edge
    candidates=[]
    for iy in range(6):
        for ix in range(8):
            x0,x1=round(ix*a.shape[1]/8),round((ix+1)*a.shape[1]/8)
            y0,y1=round(iy*a.shape[0]/6),round((iy+1)*a.shape[0]/6)
            local=score[y0:y1,x0:x1]
            value=float(.6*np.quantile(local,.98)+.4*local.mean())
            roi=[ix*source_size[0]/8,iy*source_size[1]/6,source_size[0]/8,source_size[1]/6]
            owners=[c['id'] for c in components if c['roi'][0]<roi[0]+roi[2] and c['roi'][1]<roi[1]+roi[3] and c['roi'][0]+c['roi'][2]>roi[0] and c['roi'][1]+c['roi'][3]>roi[1]]
            candidates.append({'roi':roi,'residual':round(value,5),'owners':owners[:4],'kind':'coarse_context'})
    # Small, high residuals get their own windows and quota. They are never
    # averaged into a large panel's apparent satisfaction. No local alignment.
    threshold=max(.025,float(np.quantile(score,.92)))
    labels,count=label(score>threshold)
    for region in find_objects(labels):
        if region is None: continue
        yy,xx=region; height=yy.stop-yy.start; ww=xx.stop-xx.start
        if height*ww>.15*score.size: continue
        top=max(0,yy.start-3);left=max(0,xx.start-3);bottom=min(score.shape[0],yy.stop+3);right=min(score.shape[1],xx.stop+3)
        local=score[yy,xx];value=float(np.quantile(local,.9))
        roi=[left*source_size[0]/width,top*source_size[1]/score.shape[0],
             (right-left)*source_size[0]/width,(bottom-top)*source_size[1]/score.shape[0]]
        candidates.append({'roi':roi,'residual':round(value,5),'kind':'small_connected_residual'})
    for cells in (16,32):
        step=max(8,round(width/cells))
        for top in range(0,score.shape[0],step):
            for left in range(0,width,step):
                local=score[top:top+step,left:left+step];value=float(np.quantile(local,.95))
                if value<threshold: continue
                roi=[left*source_size[0]/width,top*source_size[1]/score.shape[0],
                     local.shape[1]*source_size[0]/width,local.shape[0]*source_size[1]/score.shape[0]]
                candidates.append({'roi':roi,'residual':round(value,5),'kind':'multiscale_detail'})
    result=[]; quotas={'coarse_context':max(1,limit//3),'small_connected_residual':max(1,limit//3),'multiscale_detail':max(1,limit//3)}
    for kind,quota in quotas.items():
        for row in sorted((r for r in candidates if r['kind']==kind),key=lambda r:r['residual'],reverse=True):
            x,y,w,h=row['roi']
            if any(abs(x-r['roi'][0])+abs(y-r['roi'][1])<max(3,min(w,h)/2) for r in result):continue
            row['owners']=[c['id'] for c in components if c['roi'][0]<x+w and c['roi'][1]<y+h and c['roi'][0]+c['roi'][2]>x and c['roi'][1]+c['roi'][3]>y][:4]
            result.append(row);quota-=1
            if not quota:break
    return result[:limit]


def diagnosis(task,state,issue):
    from .common import read_json,safe_path,identity,digest
    from .semantic_composition import _native
    selected=state.get('selected') or {}; facts=[];excluded=[];supported=[]
    if not selected:return {'facts':[], 'supported':[], 'excluded':[], 'status':'unresolved'}
    pptx=safe_path(task,selected['pptx']['path']);nodes,parents,_=_native(pptx)
    unit=state.get('quality',{}).get('units',{}).get(issue.get('quality_unit'),{})
    owners=set(unit.get('objects',[]))
    if not owners and issue.get('owner') in state.get('built',{}): owners={o['id'] for o in state['built'][issue['owner']]['objects']}
    missing=sorted(owners-set(nodes))
    if missing:
        facts.append({'fact':'bound_native_owner_absent','objects':missing,'artifact':selected['pptx']})
        supported.append('instance_geometry');excluded.append({'operator':'paint_order','reason':'Missing native content cannot be restored by reordering'})
    report=selected.get('semantic_composition_actual',{})
    if report.get('pptx_hash')==selected['pptx']['sha256']:
        for row in report.get('items',[]):
            if row['kind']=='order' and row['passed'] and owners&set(row['objects']):
                excluded.append({'operator':'paint_order','objects':row['objects'],'reason':'This exact saved pair already has the correct order'})
                facts.append({'fact':'correct_saved_pair_order','objects':row['objects'],'artifact':selected['pptx']})
    if issue.get('sampling_error'):
        supported.append('source_specification');excluded.append({'operator':'geometry','reason':'Correct the invalid original measurement frame before repainting'})
        facts.append({'fact':'source_measurement_invalid','detail':issue['sampling_error']})
    spec=state.get('quality',{}).get('specifications',{}).get(issue.get('owner'),{})
    basis={'issue':issue['id'],'property':issue['property'],'source_spec':identity(spec),'facts':facts}
    return {'key':identity(basis),'facts':facts,'supported':sorted(set(supported)),'excluded':excluded,
            'status':'supported_hypotheses' if supported else 'unresolved',
            'next':'Compare the earliest relevant intermediate artifacts. Unsupported hypotheses stay unresolved; no blanket root-cause claim.'}

def trace(issue, component, method, attempts):
    # Traceable hypotheses, not an asserted root cause from vague prose.
    prop=issue.get('property','').lower()
    if any(k in prop for k in ('spacing','text','formula','gap','layout')):
        stages=['source_layout','font_and_text_metrics','parent_transform','saved_renderer']
    elif any(k in prop for k in ('material','texture','blur','detail','volume')):
        stages=['source_evidence','representation_choice','asset_resolution','surface_geometry','saved_renderer']
    else:
        stages=['source_decomposition','part_geometry','z_order','parent_transform','saved_renderer']
    return {'hypotheses':stages,'required_evidence':'locate the earliest incorrect intermediate artifact; actual source and saved ROI bind the claim',
            'protected_scope':'all unrelated owners and satisfied properties',
            'stop':'accept measured local improvement; rollback regressions; change strategy after repeated ineffective actions',
            'failed_signatures':[a.get('signature') for a in attempts[-3:]]}


def part_hotspots(quality, limit=8):
    proposals=[]
    for uid, observation in quality.get('observations',{}).items():
        unit=quality['units'][uid]
        for metric in observation['diagnostic']['constraints']:
            if metric['status'] in ('below_minimum','required_unmeasured'):
                proposals.append({'unit':uid,'owner':unit['owner'],'roi':unit['roi'],
                    'metric':metric['id'],'value':metric['value'],'deficit':metric['deficit'],
                    'kind':'independent_part_deficit','priority':unit['priority']})
    priority={'critical':0,'major':1,'minor':2,'polish':3}
    return sorted(proposals,key=lambda x:(priority.get(x['priority'],1),
                  -(x['deficit'] or 0)))[:limit]
