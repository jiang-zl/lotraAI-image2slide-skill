"""Original-mask discrepancy inventory and explicit semantic ownership plans.

No image registration, source acceptance, native edit or quality score. The
host classifies original fragments; ordinary source correction owns adoption.
"""
from pathlib import Path
from .common import read_json,write_json,digest,identity,safe_path


def prepare(task,request):
    import numpy as np
    from PIL import Image,ImageDraw
    from scipy import ndimage as ndi
    from . import agent_runtime as a,source_quality as q
    task,state=a._state(task);unit=q.unit(state,request['unit'])
    if (request.get('source_hash')!=state['source']['sha256'] or not unit
            or unit['profile'] not in ('flat','structured','curve','detail','three_dimensional')
            or not unit.get('reference_mask')):
        raise ValueError('Inventory one original-bound natural material/icon with its existing source ownership; never text/math/full photography')
    evidence=request.get('source_palette_evidence') or {};file=safe_path(task,evidence['path'])
    if digest(file)!=evidence.get('sha256') or not request.get('source_reading'):
        raise ValueError('Retain hashed original foreground/background palette evidence and semantic reading')
    colors=np.asarray(request['colors_rgb'],float);backgrounds=np.asarray(request['background_colors_rgb'],float)
    for data in (colors,backgrounds):
        if data.ndim!=2 or data.shape[1]!=3 or not 1<=len(data)<=12 or not np.isfinite(data).all() or np.any((data<0)|(data>255)):
            raise ValueError('Use small finite original foreground/background palettes')
    cap=request.get('distance_rgb_255',100);margin=request.get('foreground_margin_rgb_255',3)
    if not 0<cap<=100 or not 0<=margin<=32:raise ValueError('Bound the original contrastive class')
    x,y,w,h=map(round,unit['roi'])
    if w*h>250000:raise ValueError('Recurse into the natural material before a bounded original inventory')
    dependencies={'source':state['source']['sha256'],'unit':unit['id'],'roi':unit['roi'],'reference_mask':unit['reference_mask'],
        'request':request,'operator':digest(Path(__file__))}
    folder=task/'scratch/source-fragments'/identity(dependencies)[:24];folder.mkdir(parents=True,exist_ok=True);manifest=folder/'inventory.json'
    if manifest.is_file():return read_json(manifest)
    image=Image.open(task/state['source']['path']).convert('RGB').crop((x,y,x+w,y+h));rgb=np.asarray(image,float);owned=q._mask(task,unit['reference_mask'])
    if owned.shape!=(h,w):raise ValueError('Keep exact original mask coordinate frame')
    df=np.linalg.norm(rgb[:,:,None,:]-colors,axis=3).min(2);db=np.linalg.norm(rgb[:,:,None,:]-backgrounds,axis=3).min(2)
    positive=(df<=cap)&(df+margin<db);entries=[];matrices={}
    for kind,mask in (('class_outside_owned',positive&~owned),('owned_outside_class',owned&~positive)):
        labels,n=ndi.label(mask,np.ones((3,3),bool))
        if len(entries)+n>256:raise ValueError('Too many original fragments; narrow the source material/ROI instead of guessing a whole scene')
        for label in range(1,n+1):
            data=labels==label;ys,xs=np.where(data);key=kind+'_'+str(label);file=folder/(key+'.png');Image.fromarray(data.astype('uint8')*255).save(file);matrices[key]=data
            entries.append({'id':key,'kind':kind,'source_xyxy':[int(x+xs.min()),int(y+ys.min()),int(x+xs.max()+1),int(y+ys.max()+1)],
                'source_pixels':int(data.sum()),'original_median_rgb':np.median(rgb[data],axis=0).tolist(),
                'mask':{'path':file.relative_to(task).as_posix(),'sha256':digest(file)},'semantic_ownership':'unresolved'})
    scale=min(8,600/max(w,h));size=(max(1,round(w*scale)),max(1,round(h*scale)));board=Image.new('RGB',(3*size[0],size[1]+35),'white');draw=ImageDraw.Draw(board)
    for col,(title,data,mask) in enumerate((('ORIGINAL COMPLETE',rgb,None),('DECLARED ORIGINAL OWNERSHIP',rgb,owned),('ORIGINAL DISCREPANCY FRAGMENTS',rgb,np.logical_or(positive&~owned,owned&~positive)))):
        tile=data.astype('uint8').copy()
        if mask is not None:tile[~mask]=255
        board.paste(Image.fromarray(tile).resize(size,Image.Resampling.NEAREST),(col*size[0],35));draw.text((col*size[0]+2,2),title,fill='black')
    board_file=folder/'source-fragments.png';board.save(board_file)
    record={'status':'ORIGINAL_FRAGMENT_OWNERSHIP_REQUIRES_HOST_READING','source_hash':state['source']['sha256'],'unit':unit['id'],
        'roi':unit['roi'],'reference_mask':unit['reference_mask'],'fragments':entries,
        'source_view':{'path':board_file.relative_to(task).as_posix(),'sha256':digest(board_file)},'source_palette_evidence':evidence,
        'request':request,'manifest_path':manifest.relative_to(task).as_posix(),
        'next':'Read complete original plus discrepancy fragments. Classify each as this natural source part, a separately named foreign owner, or uncertain. Colour/connectivity alone cannot decide ownership.',
        'limits':'No automatic mask changes, hole fill, target relaxation, native edit, new scores or satisfaction. Masks preserve original source coordinates; tiny punctuation/gaps and neighbouring outlines require independent semantic reading.'}
    write_json(manifest,record);return record


def plan(task,request):
    import numpy as np
    from PIL import Image
    from . import agent_runtime as a,source_quality as q
    task,state=a._state(task);descriptor=request['inventory'];file=safe_path(task,descriptor['path'])
    if digest(file)!=descriptor['sha256']:raise ValueError('Original fragment inventory changed')
    inventory=read_json(file);unit=q.unit(state,inventory['unit'])
    if (inventory['source_hash']!=state['source']['sha256'] or not unit
            or inventory['roi']!=unit['roi'] or inventory['reference_mask']!=unit['reference_mask']):
        raise ValueError('Source ownership/coordinate frame changed; use its current bounded inventory')
    view=inventory['source_view']
    if request.get('source_view_hash')!=view['sha256'] or digest(safe_path(task,view['path']))!=view['sha256']:
        raise ValueError('Bind the actually read original fragment board')
    entries={f['id']:f for f in inventory['fragments']};decisions=request.get('decisions',[])
    if len(decisions)!=len(entries) or {d.get('fragment') for d in decisions}!=set(entries):raise ValueError('Every original fragment needs its own explicit decision')
    for item in decisions:
        if item.get('action') not in ('own','exclude','uncertain') or not item.get('reason') or not item.get('semantic_part'):
            raise ValueError('Use explicit original semantic owner/action/reason, never a colour-only PASS')
        if item['action']=='own' and item['semantic_part']!=unit['part']:raise ValueError('Own only this independently declared natural source part')
    record={'status':'SOURCE_OWNERSHIP_PLAN_REQUIRES_ORDINARY_CORRECTION','unit':unit['id'],'source_hash':state['source']['sha256'],
        'prior_reference_mask':unit['reference_mask'],'inventory':descriptor,'decisions':decisions,
        'limits':'Original host-read ownership proposal only. Keep prior mask/source history and fixed metrics. Adoption goes through ordinary source correction; reassess both actual drawings under the same corrected definition and propagate declared source-layer dependencies. Definition changes are not drawing gains.'}
    if any(d['action']=='uncertain' for d in decisions):record['status']='SOURCE_FRAGMENT_OWNERSHIP_UNRESOLVED';return record
    result=q._mask(task,unit['reference_mask']).copy()
    for item in decisions:
        mask=q._mask(task,entries[item['fragment']]['mask'])
        if item['action']=='own':result |= mask
        else:result &= ~mask
    if not result.any():raise ValueError('A natural source part cannot be erased by this proposal')
    folder=file.parent/'plans'/identity(request)[:24];folder.mkdir(parents=True,exist_ok=True);new=folder/'proposed-original-owned.png';Image.fromarray(result.astype('uint8')*255).save(new)
    record['spec_fields']={'reference_mask':{'path':new.relative_to(task).as_posix(),'sha256':digest(new)}}
    write_json(folder/'plan.json',record);return record
