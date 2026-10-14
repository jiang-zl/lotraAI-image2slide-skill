"""Fine native colour contours inside an observed semantic owner's mask.

This is a vector appearance method, not semantic understanding or HD recovery.
The host must supply natural owners and part boundaries first. No text, math,
connector or feasible schematic icon may be flattened through this method.
"""
import math
from pathlib import Path
import numpy as np
from PIL import Image
from skimage.measure import find_contours,approximate_polygon
from .common import digest,identity,safe_path,write_json,read_json
from .library_store import Library
from .recipes import node


def construct(task,state,component,spec):
    if component.get('paint_role') not in ('illustration','scientific_display_texture','background'):
        raise ValueError('Native colour contours require an explicitly observed appearance owner')
    if not component.get('source_note') or not component.get('parts'):
        raise ValueError('Locate semantic parts before tracing their appearance')
    colors=spec.get('colors',256);epsilon=spec.get('epsilon',.05)
    representative=spec.get('palette_representative','median')
    if representative not in ('median','mean'):raise ValueError('Source palette representative must be median or mean')
    if type(colors) is not int or not 32<=colors<=256 or not 0<=epsilon<=1.5:
        raise ValueError('Bounded fine appearance parameters required')
    overlap=spec.get('edge_overlap_px',0)
    if not isinstance(overlap,(int,float)) or not 0<=overlap<=.2:
        raise ValueError('Only bounded subpixel contour overlap is permitted')
    contour_method=spec.get('contour_method','marching')
    if contour_method not in ('marching','cell_runs','row_gradients'):raise ValueError('Unknown native surface contour method')
    from .contour_registration import prepare,transform
    registration=prepare(component,spec)
    roi=list(map(int,component['roi']));x,y,w,h=roi
    source=safe_path(task,state['source']['path'])
    mask_file=safe_path(task,spec['mask'])
    with Image.open(mask_file) as image:
        if image.size!=tuple(state['source_size']) or image.mode!='L':
            raise ValueError('Semantic mask must use the immutable source canvas')
        mask=np.asarray(image)[y:y+h,x:x+w]>0
    if not mask.any():raise ValueError('Empty appearance owner')
    deps={'source':digest(source),'mask':digest(mask_file),'code:paint_paths':digest(Path(__file__)),'code:registration':digest(Path(__file__).with_name('contour_registration.py'))}
    reconstructed=spec.get('reconstructed')
    asset_rgb=None
    if reconstructed:
        if component['paint_role']=='scientific_display_texture':
            raise ValueError('Generated detail cannot substitute for observed scientific measurements')
        required=('path','sha256','source_hash','disclosure','semantic_constraints','method')
        if not all(reconstructed.get(k) for k in required) or reconstructed['source_hash']!=state['source']['sha256']:
            raise ValueError('Semantic HD artwork needs source-bound lineage and disclosure')
        asset=safe_path(task,reconstructed['path'])
        if digest(asset)!=reconstructed['sha256']:raise ValueError('Reconstructed artwork changed')
        max_side=reconstructed.get('max_side',768)
        if type(max_side) is not int or not 384<=max_side<=1600:raise ValueError('Bounded high-definition vector sampling required')
        with Image.open(asset) as image:
            image=image.convert('RGB')
            if max(image.size)>max_side:
                scale=max_side/max(image.size);image=image.resize(tuple(max(1,round(v*scale)) for v in image.size),Image.Resampling.LANCZOS)
            asset_rgb=np.asarray(image)
        asset_size=(asset_rgb.shape[1],asset_rgb.shape[0])
        mask=np.asarray(Image.fromarray(mask.astype('uint8')*255).resize(asset_size,Image.Resampling.NEAREST))>0
        if reconstructed.get('asset_mask'):
            mf=safe_path(task,reconstructed['asset_mask'])
            with Image.open(mf) as image:mask &= np.asarray(image.convert('L').resize(asset_size,Image.Resampling.NEAREST))>0
            deps['asset_mask']=digest(mf)
        deps['reconstructed']=digest(asset)
        if not mask.any():raise ValueError('Reconstructed semantic owner is empty')
    complete=mask
    if spec.get('complete_mask'):
        complete_file=safe_path(task,spec['complete_mask'])
        with Image.open(complete_file) as image:
            if image.size!=tuple(state['source_size']) or image.mode!='L':raise ValueError('Completion support needs source canvas')
            complete=np.asarray(image)[y:y+h,x:x+w]>0
        if asset_rgb is not None:
            complete=np.asarray(Image.fromarray(complete.astype('uint8')*255).resize(asset_size,Image.Resampling.NEAREST))>0
        if np.any(mask & ~complete):raise ValueError('Completion support cannot drop visible owner evidence')
        deps['complete_mask']=digest(complete_file)
    if contour_method=='row_gradients':
        if spec.get('representation')!='svg':raise ValueError('Continuous colour gradients use one independent semantic SVG')
        if asset_rgb is None:
            with Image.open(source) as image:rgb=np.asarray(image.convert('RGB').crop((x,y,x+w,y+h)))
        else:rgb=asset_rgb
        from .source_gradients import construct as gradients
        return gradients(task,state,component,spec,rgb,mask,complete,deps)
    geometry_deps=deps
    if reconstructed:
        import hashlib
        # Generated artwork is already source-bound above. Its normalized
        # colour geometry depends on the asset and local masks, not the same
        # owner's position in another photo stack. Keep lineage separately.
        geometry_deps={'reconstructed':deps['reconstructed'],'code:paint_paths':deps['code:paint_paths'],'code:registration':deps['code:registration'],
                       'mask':hashlib.sha256(mask.tobytes()).hexdigest(),
                       'complete_mask':hashlib.sha256(complete.tobytes()).hexdigest()}
    key='paint:'+identity({'roi':None if reconstructed else roi,'colors':colors,'epsilon':epsilon,
                           'contour_method':contour_method,'palette_representative':representative,'completion_fill':spec.get('completion_fill'),
                           'sampling':reconstructed.get('max_side',768) if reconstructed else None,'registration':spec.get('registration'),**geometry_deps})
    lib=Library(state['project']);cached=lib.cache_get(key,geometry_deps)
    folder=Path(task)/'scratch'/('paint-'+component['id']+'-'+key.split(':')[1][:12]);folder.mkdir(exist_ok=True)
    if cached:
        state['telemetry']['cache_hits']+=1
        # Content-addressed geometry is restored into the current task; a
        # cached reference never depends on another task's physical directory.
        layers=[]
        for item in cached['layers']:
            file=folder/(item['id']+'.json')
            file.write_bytes(lib.resolve(item['geometry']).read_bytes())
            layers.append({**item,'path':file.relative_to(task).as_posix(),'sha256':digest(file)})
    else:
        if asset_rgb is None:
            with Image.open(source) as image:rgb=np.asarray(image.convert('RGB').crop((x,y,x+w,y+h)))
        else:rgb=asset_rgb
        ph,pw=rgb.shape[:2]
        samples=Image.fromarray(rgb[mask].reshape(1,-1,3))
        q=samples.quantize(colors=colors,method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE)
        labels=np.full(mask.shape,-1,np.int16);labels[mask]=np.asarray(q).ravel()
        layers=[]
        def contours(binary):
            if contour_method=='cell_runs':
                # Exact source-cell coverage, merged across identical row runs.
                # Each colour remains one compound native path; no coarse tiles
                # and no million-object PowerPoint rectangle grid are created.
                active={};rectangles=[]
                for row,line in enumerate(binary):
                    edges=np.flatnonzero(np.diff(np.pad(line.astype(np.int8),(1,1))))
                    runs={(int(a),int(b)) for a,b in edges.reshape(-1,2)}
                    for run in list(active):
                        if run not in runs:
                            rectangles.append((*run,active.pop(run),row))
                    for run in runs:active.setdefault(run,row)
                rectangles.extend((*run,top,binary.shape[0]) for run,top in active.items())
                return [{'closed':True,'points':[[a/pw,top/ph],[b/pw,top/ph],[b/pw,bottom/ph],[a/pw,bottom/ph]]}
                        for a,b,top,bottom in rectangles]
            out=[]
            for pts in find_contours(np.pad(binary.astype(float),1),.5,fully_connected='high'):
                if epsilon:pts=approximate_polygon(pts,epsilon)
                if len(pts)<4:continue
                # Padded marching squares stays within the half-pixel boundary.
                # Holes retain opposing winding in a compound native fill.
                out.append({'closed':True,'points':[[float(px-.5)/pw,float(py-.5)/ph] for py,px in pts[:-1]]})
            return out
        for index,label in enumerate([-2]+np.unique(labels[mask]).tolist()):
            selected=complete if label==-2 else mask & (labels==label)
            population=rgb[mask if label==-2 else selected]
            # Both values are derived solely from the immutable original
            # population. Mean retains sampled colour energy in smooth fields.
            fill=np.rint((np.mean if representative=='mean' else np.median)(population,axis=0)).astype(np.uint8)
            if label==-2 and spec.get('completion_fill'):
                fill=np.array([int(spec['completion_fill'][i:i+2],16) for i in (0,2,4)],np.uint8)
            file=folder/('layer-'+str(index).zfill(3)+'.json')
            data=transform(contours(selected),registration)
            if not data:continue
            write_json(file,{'contours':data})
            layers.append({'id':'layer_'+str(index),'fill':''.join(f'{v:02X}' for v in fill),
                           'geometry':lib.blob(file),'path':file.relative_to(task).as_posix(),
                           'sha256':digest(file),'pixels':int(selected.sum())})
        lib.cache_put(key,{'layers':[{k:v for k,v in item.items() if k not in ('path','sha256')} for item in layers]},geometry_deps)
    cid=component['id']
    if spec.get('representation')=='svg':
        from .compact_artwork import svg_from_layers
        asset=svg_from_layers(task,folder,layers,(pw,ph) if not cached else asset_size if reconstructed else (w,h),
              overlap=overlap,display_size=roi[2:],pixel_exact=bool(spec.get('pixel_exact')),lineage={'source':deps['source'],'role':component['paint_role'],'reconstructed':bool(reconstructed)})
        if spec.get('connection_sites'):asset['connection_sites']=spec['connection_sites']
        return [node(cid,'svg',roi,asset,semantic=component['semantic_class'])]
    objects=[node(cid,'group',roi,semantic=component['semantic_class'])]
    if spec.get('connection_sites'):
        objects.append(node(cid+'__ports','shape',roi,{'preset':'rect','connection_sites':spec['connection_sites']},cid,
                            'semantic_connection_anchor',fill=None,stroke=None))
    for item in layers:
        line_points=overlap*(state.get('analysis') or {}).get('target_width_inches',state['source_size'][0]/96)*72/state['source_size'][0]
        objects.append(node(cid+'__'+item['id'],'path',roi,
            {'geometry_ref':{'path':item['path'],'sha256':item['sha256']}},cid,'native_colour_contour',
            fill=item['fill'],stroke=item['fill'] if overlap else None,**({'line_width':line_points} if overlap else {})))
    write_json(folder/'provenance.json',{'source_hash':deps['source'],'mask_hash':deps['mask'],
               'parameters':{'colors':colors,'palette_representative':representative,'epsilon':epsilon,'edge_overlap_px':overlap,'contour_method':contour_method,'registration':spec.get('registration')},'layers':len(layers),
               'role':component['paint_role'],'semantic_owner':cid,
               'reconstructed':reconstructed,
               'inferred_underlay_pixels':int(np.count_nonzero(complete & ~mask)),
               'scope':'disclosed semantic HD reconstruction as native paths' if reconstructed else
                       'observed colour reconstruction as editable native paths; no generated scientific facts or recovered HD claimed'})
    return objects
