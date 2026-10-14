"""Exact original identity photographs, constructed without a raster trial."""
import copy,io,math
from .common import digest,identity,safe_path

def construct(task,state,component,objects,items):
    if not isinstance(items,list) or not items or len(items)>128:
        raise ValueError('source_photos must be a bounded nonempty list of objects')
    spec=state.get('quality',{}).get('specifications',{}).get(component['id'],{})
    if spec.get('source_hash')!=state['source']['sha256']:
        raise ValueError('source_photos need a frozen specification for the current original')
    source=safe_path(task,state['source']['path'])
    if digest(source)!=state['source']['sha256']:raise ValueError('Current original photo source changed')
    parts={p['id']:p for p in spec.get('parts',[])};nodes={o['id']:o for o in objects}
    seen=set();seen_parts=set();prepared=[];total=0
    for index,item in enumerate(items):
        at='source_photos['+str(index)+']'
        if not isinstance(item,dict):raise ValueError(at+' must be an object')
        if set(item)-{'object','part','source_roi','source_note'}:raise ValueError(at+' has unknown fields')
        if not all(isinstance(item.get(k),str) and item[k].strip() for k in ('object','part','source_note')):
            raise ValueError(at+' needs an object, part and original source note')
        name=item['object'];part=parts.get(item['part']);obj=nodes.get(name)
        if name in seen or item['part'] in seen_parts:raise ValueError('Original photo owners and source parts must be unique')
        seen.add(name);seen_parts.add(item['part'])
        if not part:raise ValueError(at+' references an unknown frozen part')
        if part.get('quality_intent',{}).get('purpose')!='photo_identity':
            raise ValueError(at+' requires the preconstruction photo_identity purpose')
        if not obj or obj.get('render_type')!='photo' or obj.get('semantic_type')!='photo':
            raise ValueError(at+' must bind an independent native photo owner')
        roi=item.get('source_roi')
        if not isinstance(roi,list) or len(roi)!=4 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v!=int(v) for v in roi):
            raise ValueError(at+'.source_roi must use finite integer original pixels')
        x,y,w,h=map(int,roi);ox,oy,ow,oh=component['roi'];sw,sh=state['source_size']
        if (min(x,y)<0 or min(w,h)<=0 or x+w>sw or y+h>sh or
                x<ox or y<oy or x+w>ox+ow+.001 or y+h>oy+oh+.001 or part.get('roi')!=roi):
            raise ValueError(at+'.source_roi must equal its frozen part roi inside the original owner')
        total+=w*h
        if w*h>16_000_000 or total>64_000_000:raise ValueError('Original photo crop pixel budget exceeded')
        prepared.append((name,item['part'],[x,y,w,h]))
    result=copy.deepcopy(objects);result_nodes={o['id']:o for o in result};receipts={}
    from PIL import Image
    with Image.open(source) as image:
        if list(image.size)!=state['source_size']:raise ValueError('Current original photo canvas changed')
        for name,part,roi in prepared:
            x,y,w,h=roi;crop=image.crop((x,y,x+w,y+h))
            # Keep decoded original colour/alpha, without interpolation or enhancement.
            if crop.mode not in ('RGB','RGBA','L','LA','P'):crop=crop.convert('RGB')
            buffer=io.BytesIO();crop.save(buffer,format='PNG');raw=buffer.getvalue()
            import hashlib
            expected=hashlib.sha256(raw).hexdigest()
            file=task/'source/original-photos'/(identity({'source':state['source']['sha256'],'roi':roi})+'.png')
            if file.exists() and digest(file)!=expected:raise ValueError('Preserve changed original photo cache; do not overwrite it')
            if not file.exists():file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(raw)
            receipt={'source_hash':state['source']['sha256'],'source_roi':roi,'part':part,
                'constructor':'exact-original-photo-1','pixel_operation':'crop only; no scaling or enhancement'}
            result_nodes[name]['content']={'path':file.relative_to(task).as_posix(),'sha256':expected,
                'source_roi':roi,'purpose':'original identity photograph','source_photo':receipt}
            receipts[name]=receipt
    return result,receipts
