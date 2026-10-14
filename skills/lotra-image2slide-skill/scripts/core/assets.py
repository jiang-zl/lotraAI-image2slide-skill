"""Extract explicitly identified data plots; never infer scientific numerical data."""
from pathlib import Path
import time
import numpy as np
from PIL import Image, __version__ as PILLOW_VERSION
from .common import digest,write_json,safe_path

EXTRACTOR_VERSION = 'observed-assets-0.3.0'


def mask_contours(mask):
    """Trace pixel boundaries into editable filled paths, removing collinear vertices."""
    mask=np.asarray(mask,dtype=bool)
    edges={}
    h,w=mask.shape
    for y,x in np.argwhere(mask):
        x,y=int(x),int(y)
        segments=[]
        if y==0 or not mask[y-1,x]:segments.append(((x,y),(x+1,y)))
        if x==w-1 or not mask[y,x+1]:segments.append(((x+1,y),(x+1,y+1)))
        if y==h-1 or not mask[y+1,x]:segments.append(((x+1,y+1),(x,y+1)))
        if x==0 or not mask[y,x-1]:segments.append(((x,y+1),(x,y)))
        for a,b in segments:edges.setdefault(a,[]).append(b)
    paths=[]
    while edges:
        start=next(iter(edges));p=start;points=[p]
        while True:
            next_=edges[p].pop()
            if not edges[p]:del edges[p]
            p=next_
            if p==start:break
            points.append(p)
            if p not in edges:raise ValueError('Open contour in extracted mask')
        simple=[]
        for i,b in enumerate(points):
            a=points[i-1];c=points[(i+1)%len(points)]
            if (b[0]-a[0])*(c[1]-b[1])!=(b[1]-a[1])*(c[0]-b[0]):simple.append(b)
        if len(simple)>=3:paths.append({'closed':True,'points':[[x/w,y/h] for x,y in simple]})
    return paths


def _tone_layers(pixels, mask, channel, count, output, id, mode='dominant_channel'):
    """Partition a declared mask by source colors; never change its membership."""
    if type(count) is not int or not 1 <= count <= 16:
        raise ValueError('tone_layers must be an integer from 1 to 16')
    other=[i for i in range(3) if i!=channel]
    colors=pixels[mask]
    strengths=colors[:,channel]-colors[:,other].min(axis=1)
    labels=np.full(mask.shape,-1,dtype=np.int16)
    if mode=='compound_rgb':
        samples=Image.fromarray(colors.astype(np.uint8).reshape(1,-1,3))
        quantized=samples.quantize(colors=count,method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE)
        labels[mask]=np.asarray(quantized,dtype=np.int16).ravel()
        partition={'partition':'full observed RGB median-cut clusters; source row-major sample order',
                   'quantizer':'Pillow MEDIANCUT; RGB; no dithering','pillow_version':PILLOW_VERSION,
                   'layer_order':'ascending deterministic median-cut palette index'}
    else:
        boundaries=np.unique(np.quantile(strengths,np.arange(1,count)/count,method='linear'))
        labels[mask]=np.searchsorted(boundaries,strengths,side='right')
        partition={'partition':'dominant channel minus min(other channels); observed linear quantiles; equal strengths stay together',
                   'quantile_boundaries':boundaries.tolist(),'boundary_assignment':'searchsorted side=right',
                   'layer_order':'weak-to-strong observed chroma'}
    coverage=np.zeros(mask.shape,dtype=np.uint8)
    reconstruction=np.zeros(pixels.shape,dtype=np.int16)
    layers=[]
    for label in np.unique(labels[mask]):
        layer_mask=mask & (labels==label)
        median=np.median(pixels[layer_mask],axis=0)
        rgb=np.rint(median).astype(np.int16)
        contours=mask_contours(layer_mask)
        layer_strengths=strengths[labels[mask]==label]
        mask_file=output/(id+f'.tone-{len(layers):02d}.mask.png')
        Image.fromarray(layer_mask.astype('uint8')*255).save(mask_file)
        layers.append({'fill':''.join(f'{v:02X}' for v in rgb),'contours':contours,
                       'pixel_count':int(layer_mask.sum()),'median_rgb':median.tolist(),
                       'chroma_range':[int(layer_strengths.min()),int(layer_strengths.max())],
                       'mask_path':mask_file.name,'mask_sha256':digest(mask_file)})
        coverage+=layer_mask
        reconstruction[layer_mask]=rgb
    union_xor=int(np.count_nonzero((coverage>0)^mask))
    overlaps=int(np.count_nonzero(coverage>1))
    if union_xor or overlaps:
        raise ValueError('Tone layer masks must exactly partition the frozen foreground')
    one_color=np.rint(np.median(colors,axis=0)).astype(np.int16)
    measurements={'foreground_pixels':int(mask.sum()),'layer_union_pixels':int(np.count_nonzero(coverage)),
                  'union_xor_pixels':union_xor,'overlap_pixels':overlaps,
                  'single_median_rgb':one_color.tolist(),
                  'single_median_foreground_mae_rgb_255':float(np.abs(colors-one_color).mean()),
                  'layered_foreground_mae_rgb_255':float(np.abs(colors-reconstruction[mask]).mean()),
                  'scope':'fixed-mask color quantization diagnostic; not native-render acceptance'}
    protocol={'version':EXTRACTOR_VERSION,'requested_layers':count,'generated_layers':len(layers),
              **partition,
              'fill_estimator':'per-channel median of source RGB in layer; nearest integer, ties to even',
              'semantic_scope':'display layers of one observed waveform',
              'palette':[layer['fill'] for layer in layers]}
    return layers,protocol,measurements


def _compound_mask(pixels, channel):
    """Observe nonwhite RGB, assigning display ownership without unmixing signals."""
    if channel not in (0,2):
        raise ValueError('compound_rgb requires dominant_channel b or r as display allocation')
    delta=255-pixels.astype(np.int32)
    foreground=(delta*delta).sum(axis=2)>35**2
    blue=foreground & (pixels[:,:,2]>=pixels[:,:,0])
    red=foreground & (pixels[:,:,0]>pixels[:,:,2])
    counts=blue.astype(np.uint8)+red.astype(np.uint8)
    union_xor=int(np.count_nonzero((counts>0)^foreground))
    overlaps=int(np.count_nonzero(counts>1))
    if union_xor or overlaps:
        raise ValueError('Compound display allocations must partition all observed foreground')
    protocol={'version':EXTRACTOR_VERSION,'mode':'compound_rgb','background_rgb':[255,255,255],
              'foreground_definition':'Euclidean RGB distance from known white background > 35',
              'background_distance_threshold':35,'comparison':'strict greater-than; exact squared integer distance',
              'display_assignment':'b: B>=R; r: R>B; neutral overlap allocated to b; not physical signal attribution',
              'legacy_chroma_value_filters':'not applied in explicit compound_rgb mode',
              'observed_foreground_pixels':int(foreground.sum()),'blue_display_pixels':int(blue.sum()),
              'red_display_pixels':int(red.sum()),'display_union_xor_pixels':union_xor,
              'display_overlap_pixels':overlaps,'original_numeric_data':'unavailable'}
    return (blue if channel==2 else red),foreground,protocol


def extract(source,requests,output):
    started=time.monotonic()
    source_hash=digest(source)
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    image=Image.open(source).convert('RGB')
    entries=[]
    for request in requests:
        id=request['id'];roi=request['roi'];kind=request['kind']
        if not id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in id):raise ValueError('Unsafe asset id')
        x,y,w,h=roi
        if not all(isinstance(v,int) for v in roi) or not 0<=x<x+w<=image.width or not 0<=y<y+h<=image.height:raise ValueError('Invalid extraction ROI')
        crop=image.crop((x,y,x+w,y+h))
        record={'id':id,'kind':kind,'source_sha256':source_hash,'roi':roi,'meaning':request['meaning'],'original_numeric_data':'unavailable'}
        if kind=='data_image':
            file=output/(id+'.png');crop.save(file)
            record.update(path=file.name,sha256=digest(file))
        elif kind=='curve_path':
            pixels=np.asarray(crop,dtype=np.int16)
            channel={'r':0,'g':1,'b':2}[request['dominant_channel']]
            mode=request.get('mode','dominant_channel')
            extraction_protocol=None
            if mode=='compound_rgb':
                count=request.get('tone_layers',8)
                if type(count) is not int or count!=8:
                    raise ValueError('compound_rgb requires tone_layers=8 or omission of tone_layers')
                mask,observed,extraction_protocol=_compound_mask(pixels,channel)
                observed_file=output/(id+'.observed.mask.png')
                Image.fromarray(observed.astype('uint8')*255).save(observed_file)
                extraction_protocol['observed_mask_path']=observed_file.name
                extraction_protocol['observed_mask_sha256']=digest(observed_file)
            elif mode=='dominant_channel':
                other=[i for i in range(3) if i!=channel]
                chroma=int(request.get('min_chroma',35))
                mask=(pixels[:,:,channel]-pixels[:,:,other].min(axis=2)>=chroma)&(pixels[:,:,channel]>=request.get('min_value',100))
            else:
                raise ValueError('Unsupported curve extraction mode: '+str(mode))
            contours=mask_contours(mask)
            if not contours:raise ValueError('No curve foreground found: '+id)
            payload={'contours':contours,'source_sha256':source_hash,'roi':roi,'mask_parameters':request}
            if extraction_protocol is not None:
                payload['extraction_protocol']=extraction_protocol
                record['extraction_protocol']=extraction_protocol
            if 'tone_layers' in request or mode=='compound_rgb':
                layers,protocol,measurements=_tone_layers(pixels,mask,channel,request.get('tone_layers',8),output,id,mode)
                payload.update(layers=layers,tone_protocol=protocol,tone_measurements=measurements)
                record.update(tone_layer_count=len(layers),palette=protocol['palette'],tone_measurements=measurements)
            file=output/(id+'.paths.json');write_json(file,payload)
            Image.fromarray(mask.astype('uint8')*255).save(output/(id+'.mask.png'))
            record.update(path=file.name,sha256=digest(file),foreground_pixels=int(mask.sum()),contour_count=len(contours),point_count=sum(len(c['points']) for c in contours))
        else:raise ValueError('Only declared observed data-image/curve extraction is supported')
        entries.append(record)
    if digest(source)!=source_hash:raise ValueError('Source changed during asset extraction')
    manifest={'source_sha256':source_hash,'assets':entries,'scope':'observed plot appearance; no numerical data recovery',
              'extractor_version':EXTRACTOR_VERSION,'elapsed_seconds':time.monotonic()-started}
    write_json(output/'assets.json',manifest)
    return manifest
