"""Source-owned visible comparison domains, separate from hidden completion.

The host observes semantic membership. This program crops already located,
hash-bound source masks; it never masks against a candidate or accepts a draw.
"""
from pathlib import Path
import copy
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from .common import safe_path,digest,identity,read_json,write_json


def prepare(task,request):
    from .agent_runtime import _state
    task,state=_state(task);packet=state.get('packet') or {}
    baseline=state.get('active_candidate') or state.get('selected') or {}
    if baseline.get('pptx',{}).get('sha256')!=request.get('baseline_hash'):
        raise ValueError('Bind the current source observation and retained drawing')
    if request.get('source_view'):
        from .semantic_composition import _original_view
        _original_view(task,state,request['source_view'])
        if request.get('source_view_hash')!=request['source_view']['sha256']:
            raise ValueError('Bind the raw original observation before source-domain refinement')
    elif (packet.get('packet_id')!=request.get('packet_id') or
            request.get('source_view_hash') not in [v['sha256'] for v in packet.get('views',[]) if v['role']=='source']):
        raise ValueError('Observe the paired original before defining ownership')
    unit=state['quality']['units'][request['unit']]
    if unit['profile'] in ('relation','text','formula'):
        raise ValueError('Keep relation/glyph protocols separate from a visible material layer')
    if not request.get('reason') or not request.get('visible_features'):
        raise ValueError('Describe source ownership and keep its important visible features')
    if not set(request['visible_features'])<=set(f['id'] for f in unit['features']):
        raise ValueError('Use this independently bound source feature inventory')
    roi=unit['roi'];x,y,right,bottom=map(round,(roi[0],roi[1],roi[0]+roi[2],roi[1]+roi[3]));w,h=right-x,bottom-y;shape=(h,w)
    if request.get('original_selector'):
        request=copy.deepcopy(request)
        request.update(original_masks(task,state,unit,request['original_selector']))
    dependencies={'source':state['source']['sha256'],'unit':identity({k:v for k,v in unit.items() if k not in ('status','built_fingerprint')}),
        'request':{k:v for k,v in request.items() if k not in ('packet_id','baseline_hash','source_view_hash')},
        'implementation':digest(Path(__file__))}
    def local_mask(descriptor,fallback_roi=None):
        file=safe_path(task,descriptor['path'])
        if digest(file)!=descriptor.get('sha256'):raise ValueError('Original ownership mask changed')
        declared=descriptor.get('roi',fallback_roi)
        if declared is None:raise ValueError('Declare the mask source-canvas frame')
        mx,my,mright,mbottom=map(round,(declared[0],declared[1],declared[0]+declared[2],declared[1]+declared[3]));mw,mh=mright-mx,mbottom-my
        width,height=state['source_size']
        if min(mx,my)<0 or min(mw,mh)<=0 or mx+mw>width or my+mh>height:
            raise ValueError('Source ownership frame lies outside the original')
        data=np.asarray(Image.open(file).convert('L'))>0
        if data.shape!=(mh,mw):raise ValueError('Ownership mask dimensions must match its declared source frame')
        canvas=np.zeros((height,width),dtype=bool);canvas[my:my+mh,mx:mx+mw]=data
        return canvas[y:y+h,x:x+w]
    support=local_mask(request['support'])
    foreground=local_mask(request['foreground'])
    exclusions=np.zeros(shape,dtype=bool);occluders=[];refs={}
    padding=request.get('occluder_padding_px',0)
    if type(padding) is not int or not 0<=padding<=2:
        raise ValueError('Source-edge ownership padding is bounded to zero through two pixels')
    for uid in request.get('exclude_units',[]):
        other=state['quality']['units'].get(uid)
        if not other or uid==unit['id'] or not other.get('reference_mask'):
            raise ValueError('An upper source layer needs its independent original mask: '+str(uid))
        refs[uid]={'roi':other['roi'],'reference_mask':other['reference_mask']}
        mask=local_mask(other['reference_mask'],other['roi'])
        if padding:mask=ndi.binary_dilation(mask,iterations=padding)
        exclusions |= mask;occluders.append(uid)
    domain=support&~exclusions;foreground &= domain
    if not foreground.any() or not domain.any():
        raise ValueError('The observed layer needs visible source pixels and a nonempty comparison domain')
    dependencies['upper_source_units']=refs
    folder=task/'scratch/source-layer-domain'/identity(dependencies)[:24]
    folder.mkdir(parents=True,exist_ok=True)
    saved=folder/'proposal.json'
    if saved.is_file():return read_json(saved)
    def save_mask(name,mask):
        file=folder/name;Image.fromarray(mask.astype('uint8')*255).save(file)
        return {'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    ref=None
    prior=unit.get('reference_mask')
    if prior:
        original=safe_path(task,prior['path'])
        old=None
        if original.is_file():
            if digest(original)!=prior['sha256']:raise ValueError('Existing original foreground mask changed')
            old=np.asarray(Image.open(original).convert('L'))>0
        if old is not None and old.shape==foreground.shape and np.array_equal(old,foreground):
            # An exterior-domain correction is not a new foreground reading.
            # Keep the existing descriptor so unrelated original upper-layer
            # dependents do not acquire a false mask-path change.
            ref=copy.deepcopy(prior)
    if ref is None:ref=save_mask('visible-reference.png',foreground)
    evaluation=save_mask('fixed-evaluation.png',domain)
    protocol={'edge_scope':'owned_foreground','histogram_scope':'reference_foreground','edge_support_neighborhood':'sobel_3x3'}
    selector=request.get('foreground_selector')
    if selector:
        if (selector.get('mode')!='color' or not selector.get('colors_rgb')
                or not 0<float(selector.get('distance_rgb_255',0))<=100
                or any(len(c)!=3 or any(type(v) not in (int,float) or not 0<=v<=255 for v in c) for c in selector['colors_rgb'])):
            raise ValueError('Use a source-observed fixed colour selector, never a candidate-dependent threshold')
        protocol['foreground_selector']=copy.deepcopy(selector)
    manifest={'version':'source-layer-domain-1','source_hash':state['source']['sha256'],
        'unit':unit['id'],'roi':roi,'reference_mask':ref,'evaluation_mask':evaluation,
        'occluders':occluders,'upper_source_units':refs,'protocol':protocol,'source_view_hash':request['source_view_hash'],
        'reason':request['reason'],'visible_features':request['visible_features'],
        'source_inputs':{'support':request['support'],'foreground':request['foreground']},
        'occluder_padding_px':padding,'visible_pixels':int(foreground.sum()),'evaluation_pixels':int(domain.sum()),
        'limits':'Observed source-owned domain only. Hidden completion, visible endpoints, layer order and containment still need independent semantic/relation review. Excluded source context is not a drawing improvement.'}
    file=folder/'domain.json';write_json(file,manifest)
    layering={'role':'underlay','occluders':occluders,
        'source_domain':{'path':file.relative_to(task).as_posix(),'sha256':digest(file)}}
    result={'status':'SOURCE_VISIBLE_LAYER_DOMAIN_PROPOSAL','unit':unit['id'],'source_hash':state['source']['sha256'],
        'spec_fields':{'reference_mask':ref,'evaluation_mask':evaluation,'protocol':protocol,'layering':layering},
        'visible_pixels':manifest['visible_pixels'],'evaluation_pixels':manifest['evaluation_pixels'],
        'next':'Submit a measurement_domain source correction with the prior specification and paired source view. Recompute before/after on this same definition; unchanged targets remain mandatory.',
        'limits':manifest['limits']}
    write_json(saved,result);return result

def original_masks(task,state,unit,selector):
    """Finite original-only colour/contrast selection, with explicit components.

    Host decisions are source palette and ownership seeds. Every selected
    pixel comes from the original; no candidate, drawing alpha or hole fill.
    """
    source=safe_path(task,state['source']['path'])
    if digest(source)!=state['source']['sha256']:raise ValueError('Original pixels changed')
    x,y,r,b=map(round,(unit['roi'][0],unit['roi'][1],unit['roi'][0]+unit['roi'][2],unit['roi'][1]+unit['roi'][3]))
    image=np.asarray(Image.open(source).convert('RGB').crop((x,y,r,b)),dtype=float)
    mode=selector.get('mode')
    if mode=='color':
        colors=np.asarray(selector.get('colors_rgb',[]),dtype=float)
        limit=selector.get('distance_rgb_255')
        if (colors.ndim!=2 or colors.shape[1]!=3 or not len(colors) or not np.isfinite(colors).all()
                or np.any((colors<0)|(colors>255)) or type(limit) not in (int,float) or not 0<limit<=128):
            raise ValueError('Freeze a finite source palette and bounded colour distance')
        distance=np.min(np.linalg.norm(image[...,None,:]-colors,axis=3),axis=2);mask=distance<=limit
        if selector.get('background_colors_rgb'):
            backgrounds=np.asarray(selector['background_colors_rgb'],dtype=float);margin=selector.get('foreground_margin_rgb_255',0)
            if (backgrounds.ndim!=2 or backgrounds.shape[1]!=3 or not np.isfinite(backgrounds).all()
                    or np.any((backgrounds<0)|(backgrounds>255)) or not 0<=margin<=32):
                raise ValueError('Original contrast samples and margin are bounded')
            mask &= distance+margin<np.min(np.linalg.norm(image[...,None,:]-backgrounds,axis=3),axis=2)
    elif mode=='background':
        background=np.asarray(selector.get('background_rgb',[]),dtype=float);limit=selector.get('distance_rgb_255')
        if background.shape!=(3,) or not np.isfinite(background).all() or np.any((background<0)|(background>255)) or type(limit) not in (int,float) or not 0<limit<=128:
            raise ValueError('Freeze the observed original background and finite contrast distance')
        mask=np.linalg.norm(image-background,axis=2)>=limit
    else:raise ValueError('Use the finite original color/background selector')
    support=np.ones(mask.shape,bool)
    if selector.get('window'):
        window=selector['window']
        if (not isinstance(window,list) or len(window)!=4 or any(type(v) is not int for v in window)
                or min(window[2:])<=0 or window[0]<x or window[1]<y or window[0]+window[2]>r or window[1]+window[3]>b):
            raise ValueError('An owned source window must stay within its frozen original unit')
        support[:]=False;wx,wy,ww,wh=window;support[wy-y:wy-y+wh,wx-x:wx-x+ww]=True;mask &= support
    labels,_=ndi.label(mask)
    for action in ('retain_components_at','exclude_components_at'):
        seeds=selector.get(action,[]);owned=[]
        for point in seeds:
            if len(point)!=2 or any(type(v) is not int for v in point):raise ValueError('Original component seeds use integer source coordinates')
            xx,yy=point[0]-x,point[1]-y
            if not 0<=xx<r-x or not 0<=yy<b-y or labels[yy,xx]==0:raise ValueError('Original ownership seed is outside its selected paint')
            owned.append(labels[yy,xx])
        if owned:mask &= np.isin(labels,owned) if action=='retain_components_at' else ~np.isin(labels,owned)
    if not mask.any():raise ValueError('Source ownership selection is empty')
    folder=Path(task)/'source/owned-masks'/identity({'source':state['source'],'roi':unit['roi'],'selector':selector,'implementation':digest(Path(__file__))})
    folder.mkdir(parents=True,exist_ok=True);refs={}
    for name,values in (('foreground',mask),('support',support)):
        path=folder/(name+'.png');Image.fromarray(values.astype('uint8')*255).save(path)
        refs[name]={'path':path.relative_to(task).as_posix(),'sha256':digest(path),'roi':unit['roi']}
    write_json(folder/'Original-provenance.json',{'source':state['source'],'roi':unit['roi'],'selector':selector,
        'unit':unit['id'],'foreground_pixels':int(mask.sum()),'limits':'Original-only finite selector; host confirms semantic ownership; candidate never read.'})
    return refs


def debt(task,state,value):
    layering=value.get('layering')
    if not layering:return None
    if not value.get('reference_mask') or not value.get('evaluation_mask') or not layering.get('source_domain'):
        return 'SOURCE_VISIBLE_LAYER_DOMAIN_REQUIRED'
    descriptor=layering['source_domain'];file=safe_path(task,descriptor['path'])
    if digest(file)!=descriptor['sha256']:raise ValueError('Frozen source-layer domain changed')
    data=read_json(file)
    if (data.get('source_hash')!=state['source']['sha256'] or data.get('unit')!=value['id']
            or data.get('roi')!=value['roi'] or data.get('reference_mask')!=value['reference_mask']
            or data.get('evaluation_mask')!=value['evaluation_mask']
            or data.get('occluders')!=layering.get('occluders')):
        return 'SOURCE_VISIBLE_LAYER_DOMAIN_BINDING_MISMATCH'
    if data.get('protocol') and any(value['protocol'].get(k)!=v for k,v in data['protocol'].items()):
        return 'SOURCE_VISIBLE_LAYER_PROTOCOL_MISMATCH'
    for uid,prior in data.get('upper_source_units',{}).items():
        other=state['quality']['units'].get(uid,{})
        if prior!={'roi':other.get('roi'),'reference_mask':other.get('reference_mask')}:
            return 'UPPER_SOURCE_LAYER_READING_CHANGED'
    return None
