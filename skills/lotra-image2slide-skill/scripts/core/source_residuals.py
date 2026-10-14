"""Locate fixed-source icon discrepancies without inventing a semantic cause.

This is a bounded actual-drawing observation aid, not a new scoring protocol.
"""
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from scipy import ndimage as ndi
from .common import identity,digest,read_json,write_json,safe_path


def _foreground(rgb,protocol):
    selector=protocol.get('foreground_selector')
    if selector:
        if selector.get('mode')=='neutral_dark':
            mask=(rgb.mean(2)*255<selector['max_mean_rgb_255'])&((rgb.max(2)-rgb.min(2))*255<selector['max_chroma_rgb_255'])
        else:
            colours=np.asarray(selector['colors_rgb'])/255
            distance=np.linalg.norm(rgb[:,:,None,:]-colours[None,None,:,:],axis=3).min(2)
            mask=distance<=selector['distance_rgb_255']/255
            if selector.get('background_colors_rgb') is not None:
                backgrounds=np.asarray(selector['background_colors_rgb'])/255
                outside=np.linalg.norm(rgb[:,:,None,:]-backgrounds[None,None,:,:],axis=3).min(2)
                mask &= distance+selector.get('foreground_margin_rgb_255',0)/255<outside
    else:
        mask=np.linalg.norm(rgb-np.asarray(protocol['background_rgb'])/255,axis=2)>=protocol['foreground_distance_rgb']
    if protocol.get('component_seed'):
        sx,sy=protocol['component_seed'];labels,_=ndi.label(mask);label=labels[sy,sx]
        mask=labels==label if label else np.zeros(mask.shape,bool)
    return mask


def prepare(task,request):
    from . import agent_runtime as a,source_quality as q,typed_metrics as tm
    task,state=a._state(task);candidate=state.get('selected') or {}
    if (request.get('baseline_hash')!=candidate.get('pptx',{}).get('sha256')
            or request.get('source_hash')!=state['source']['sha256']):
        raise ValueError('Bind the selected actual drawing and unchanged original')
    unit=q.unit(state,request['unit'])
    if unit['profile'] in ('text','formula','relation') or not unit.get('reference_mask'):
        raise ValueError('Use independent glyph/relation operators; this route requires a masked visual part')
    if not candidate.get('render') or not candidate.get('preview'):
        raise ValueError('A saved actual drawing/renderer receipt is required')
    for descriptor in (state['source'],candidate['pptx'],candidate['preview']):
        if digest(safe_path(task,descriptor['path']))!=descriptor['sha256']:
            raise ValueError('Saved actual/source bytes changed')
    original,current=q._crop_images(task,state,candidate,unit['roi'])
    if max(original.size)>400 or original.width*original.height>60000:
        raise ValueError('Recurse to one bounded natural part before spatial diagnosis')
    frozen={k:v for k,v in unit.items() if k not in ('status','built_fingerprint')}
    key=identity({'source':state['source']['sha256'],'candidate':candidate['pptx']['sha256'],
        'preview':candidate['preview']['sha256'],'unit':frozen,'program':digest(Path(__file__)),
        'typed':digest(Path(tm.__file__))})[:24]
    folder=task/'scratch/source-residuals'/key;folder.mkdir(parents=True,exist_ok=True)
    saved=folder/'proposal.json'
    if saved.is_file():return read_json(saved)
    protocol=unit['protocol'];aa,bb=tm.rgb(original,protocol['background_rgb']),tm.rgb(current,protocol['background_rgb'])
    owned=q._mask(task,unit['reference_mask']);domain=q._mask(task,unit.get('evaluation_mask'))
    if owned.shape!=aa.shape[:2] or (domain is not None and domain.shape!=owned.shape):
        raise ValueError('Original mask and fixed source frame must agree')
    has_domain=domain is not None
    if domain is None:domain=np.ones(owned.shape,bool)
    candidate_foreground=_foreground(bb,protocol)
    full=ndi.binary_erosion(domain,structure=np.ones((3,3),bool)) if has_domain else domain
    support=protocol.get('edge_support_neighborhood','legacy_cross')
    edge_domain=full if support=='sobel_3x3' else ndi.binary_erosion(domain) if has_domain else domain
    ae=tm.edge_map(aa,protocol['edge_threshold'])&edge_domain
    be=tm.edge_map(bb,protocol['edge_threshold'])&edge_domain
    if protocol.get('edge_scope')=='owned_foreground':
        ae &= ndi.binary_dilation(owned,iterations=2)
        be &= ndi.binary_dilation(candidate_foreground,iterations=2)
    tolerance=protocol['boundary_tolerance_px']
    source_distance=ndi.distance_transform_edt(~ae) if ae.any() else np.full(owned.shape,np.inf)
    candidate_distance=ndi.distance_transform_edt(~be) if be.any() else np.full(owned.shape,np.inf)
    fields={'missing_edge':ae&(candidate_distance>tolerance),
        'extra_edge':be&(source_distance>tolerance),
        'missing_foreground':owned&domain&~candidate_foreground,
        'extra_foreground':candidate_foreground&domain&~owned}
    original_neighborhood=ndi.binary_dilation(owned,iterations=2)
    def descriptor(file):return {'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    evidence=[]
    for name,mask in fields.items():
        file=folder/(name+'.png');Image.fromarray(mask.astype('uint8')*255).save(file)
        labels,n=ndi.label(mask,np.ones((3,3),bool));regions=[]
        for label in range(1,n+1):
            yy,xx=np.where(labels==label);local=labels==label
            regions.append({'samples':len(xx),'source_bbox':[int(xx.min()+unit['roi'][0]),int(yy.min()+unit['roi'][1]),int(xx.max()+unit['roi'][0]+1),int(yy.max()+unit['roi'][1]+1)],
                'outside_original_owner_2px':int((local&~original_neighborhood).sum())})
        regions.sort(key=lambda r:r['samples'],reverse=True)
        evidence.append({'kind':name,'samples':int(mask.sum()),'outside_original_owner_2px':int((mask&~original_neighborhood).sum()),
            'mask':descriptor(file),'regions':regions[:256],'remaining_fragments':max(0,len(regions)-256)})
    overlay=np.asarray(current).copy();overlay[fields['missing_edge']]=[255,0,180];overlay[fields['extra_edge']]=[0,160,255]
    ink=np.asarray(current).copy();ink[fields['missing_foreground']]=[255,0,180];ink[fields['extra_foreground']]=[0,160,255]
    colour=np.linalg.norm(aa-bb,axis=2)*255;colour[~(owned&domain)]=0
    heat=np.zeros_like(overlay);heat[:,:,0]=np.clip(colour*2,0,255).astype('uint8');heat[:,:,2]=heat[:,:,0]//2
    panels=[('ORIGINAL',original),('ACTUAL SAVED',current),('ORIGINAL OWNERSHIP',Image.fromarray(owned.astype('uint8')*255).convert('RGB')),('FIXED EVALUATION',Image.fromarray(domain.astype('uint8')*255).convert('RGB')),
        ('SOURCE/ACTUAL EDGES',Image.fromarray(np.stack((ae.astype('uint8')*255,be.astype('uint8')*255,np.zeros_like(ae,'uint8')),2))),('EDGE MISS magenta / EXTRA cyan',Image.fromarray(overlay)),('INK MISS magenta / EXTRA cyan',Image.fromarray(ink)),('OWNED RGB RESIDUAL',Image.fromarray(heat))]
    board=Image.new('RGB',(1440,620),'white');draw=ImageDraw.Draw(board)
    for index,(label,image) in enumerate(panels):
        x,y=(index%4)*360,(index//4)*310;factor=min(350/image.width,270/image.height)
        size=(round(image.width*factor),round(image.height*factor));draw.text((x+3,y+3),label,fill='black')
        board.paste(image.resize(size,Image.Resampling.LANCZOS if index<2 else Image.Resampling.NEAREST),(x+3,y+30))
    view=folder/'fixed-source-actual.png';board.save(view)
    record={'source_hash':state['source']['sha256'],'selected':candidate['pptx'],'actual_preview':candidate['preview'],'unit':unit['id'],'roi':unit['roi'],
        'reference_mask':unit['reference_mask'],'evaluation_mask':unit.get('evaluation_mask'),'protocol':protocol,'fixed_targets':unit['metrics'],
        'diagnostic':q.evaluate(task,state,candidate,unit),'spatial_residuals':evidence,
        'ownership_context':{'original_foreground_pixels':int((owned&domain).sum()),'candidate_foreground_pixels':int((candidate_foreground&domain).sum()),
            'evaluation_pixels':int(domain.sum()),'original_edges':int(ae.sum()),'actual_edges':int(be.sum())},
        'limits':'Fixed source coordinates and existing measurement protocol. Spatial residuals are locations, not semantic defects or proven causes. Original context/other-layer ownership must be read before attributing a residual to this icon. No source/target/drawing mutation, registration, acceptance or invented observation.'}
    file=folder/'residuals.json';write_json(file,record)
    result={'status':'SOURCE_ACTUAL_SPATIAL_RESIDUALS','unit':unit['id'],'source_hash':state['source']['sha256'],'baseline_hash':candidate['pptx']['sha256'],
        'view':descriptor(view),'record':descriptor(file),
        'summary':[{'kind':r['kind'],'samples':r['samples'],'outside_original_owner_2px':r['outside_original_owner_2px'],'largest_regions':r['regions'][:6],'remaining_fragments':r['remaining_fragments']} for r in evidence],
        'next':'View the source/actual board and exact locations. Trace original ownership/domain, source program/geometry, parent transform or actual host rendering before the smallest new repair. For a confirmed foreign layer amend only the original domain through source correction; retain old definitions and score both saved drawings equally. Never infer a cause or change a target from a residual count.',
        'limits':record['limits']}
    write_json(saved,result);return result
