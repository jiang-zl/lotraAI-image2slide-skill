"""One bounded native material proposal from a saved actual rendering.

Fixed source ownership, source palette and native pose are retained. Numerical
response fitting is a proposal, never an acceptance or a new measurement mask.
"""
from pathlib import Path
import copy
from .common import read_json,write_json,digest,identity,safe_path


def owned_leaf(unit,objects,ident):
    """Resolve an existing leaf within this independently bound native owner."""
    if ident not in objects or objects[ident]['render_type'] not in ('shape','path'):
        return False
    seen=set();cursor=ident
    while cursor in objects and cursor not in seen:
        if cursor in unit['objects']:return True
        seen.add(cursor);cursor=objects[cursor].get('parent')
    return False


def propose(task,request):
    import numpy as np
    from scipy.optimize import differential_evolution
    from . import agent_runtime as a,source_quality as q
    from .typed_metrics import color_histogram
    task,state=a._state(task);selected=state.get('selected')
    if not selected or request.get('baseline_hash')!=selected['pptx']['sha256']:
        raise ValueError('Bind the observed actual saved native baseline')
    if request.get('source_hash')!=state['source']['sha256'] or not request.get('source_evidence'):
        raise ValueError('Bind original material/background evidence; a selector palette is not paint evidence')
    unit=q.unit(state,request['unit'])
    if unit['profile'] not in ('flat','structured','curve','detail','three_dimensional'):
        raise ValueError('Use one identified icon material, never native text/math or rich scientific photography')
    scene=read_json(safe_path(task,selected['scene']['path']));objects={o['id']:o for o in scene['objects']}
    ident=request['object_id']
    if not owned_leaf(unit,objects,ident):raise ValueError('Resolve one existing native filled leaf inside this source owner')
    node=objects[ident];style=node.get('style',{});fill=style.get('fill')
    if not isinstance(fill,str) or len(fill)!=6 or style.get('gradient') or style.get('fill_opacity',1)!=1:
        raise ValueError('This response model requires one uniform opaque native paint; use a surface operator for gradients')
    native=np.array([int(fill[i:i+2],16) for i in (0,2,4)],float)
    anchor=np.array(request['original_paint_rgb'],float);backgrounds=np.array(request['background_colors_rgb'],float)
    bound=request.get('maximum_source_shift_rgb',8)
    if anchor.shape!=(3,) or backgrounds.ndim!=2 or backgrounds.shape[1]!=3 or not 1<=len(backgrounds)<=12 or not 0<bound<=8:
        raise ValueError('Use bounded original colour uncertainty and independently observed neighbouring planes')
    if not (np.isfinite(anchor).all() and np.isfinite(backgrounds).all() and (anchor>=0).all() and (anchor<=255).all() and (backgrounds>=0).all() and (backgrounds<=255).all()):
        raise ValueError('Original RGB evidence must be finite and bounded')
    mode=unit['protocol'].get('histogram_mode','hard')
    scope=unit['protocol'].get('histogram_scope')
    if scope not in (None,'evaluation_domain','reference_foreground') or mode not in ('hard','trilinear'):
        raise ValueError('Use the previously declared fixed original evaluation/foreground histogram, never a replacement scoring definition')
    ref,cur=q._crop_images(task,state,selected,unit['roi']);r=np.asarray(ref,float);b=np.asarray(cur,float)
    owned=q._mask(task,unit.get('reference_mask'));domain=q._mask(task,unit.get('evaluation_mask'))
    if owned is None or domain is None or owned.shape!=r.shape[:2] or domain.shape!=owned.shape:
        raise ValueError('Bind immutable original ownership and evaluation masks')
    owned=owned & domain
    if owned.sum()<40:raise ValueError('Insufficient original paint support; retain uncertainty instead of guessing a fit')
    dependencies={'original':state['source']['sha256'],'baseline':selected['pptx']['sha256'],
        'preview':selected['preview']['sha256'],'unit':identity({k:v for k,v in unit.items() if k not in ('status','built_fingerprint')}),
        'request':request,'operator':digest(Path(__file__))}
    folder=Path(task)/'scratch/source-material-response'/identity(dependencies)[:24];folder.mkdir(parents=True,exist_ok=True)
    record_file=folder/'response.json'
    if record_file.exists():return read_json(record_file)
    direction=native-backgrounds;norm=np.square(direction).sum(1)
    if np.min(norm)<2500:raise ValueError('Native paint/background contrast does not identify a reliable response')
    alpha=np.clip(((b[:,:,None,:]-backgrounds)*direction).sum(3)/norm,0,1)
    residual=np.linalg.norm(b[:,:,None,:]-(backgrounds+alpha[:,:,:,None]*direction),axis=3)
    index=residual.argmin(2)[...,None]
    weight=np.take_along_axis(alpha,index,2)[...,0]
    weight*=np.take_along_axis(residual,index,2)[...,0]<=24
    response_samples=int(np.count_nonzero((weight>.05)&owned))
    if response_samples<.60*int(owned.sum()):raise ValueError('Fix missing geometry/ownership or multiple native materials before this uniform paint correction')
    bins=unit['protocol']['histogram_bins'];histogram_domain=owned if scope=='reference_foreground' else domain
    source_hist=color_histogram(r[histogram_domain]/255,bins,mode);source_hist/=source_hist.sum()
    def predicted(paint):
        pixels=np.clip(b+weight[...,None]*(paint-native),0,255)
        hist=color_histogram(pixels[histogram_domain]/255,bins,mode);hist/=hist.sum()
        return float(np.abs(hist-source_hist).sum()/2)
    def loss(paint):return predicted(paint)+.00004*np.square(paint-anchor).sum()
    bounds=[(max(0,v-bound),min(255,v+bound)) for v in anchor]
    if mode=='hard':
        # A discrete original histogram has plateaus. Search its finite
        # source-supported integer paint box, retaining original ownership,
        # bins and floors rather than replacing the scoring definition.
        from itertools import product
        grids=[range(int(np.ceil(lo)),int(np.floor(hi))+1) for lo,hi in bounds]
        points=(np.asarray(v,dtype=int) for v in product(*grids))
        paint=min(points,key=lambda v:(loss(v),float(np.square(v-anchor).sum()),tuple(v)))
    else:
        fit=differential_evolution(loss,bounds,seed=0,popsize=8,maxiter=50,polish=True)
        paint=np.rint(fit.x).astype(int)
    updated=copy.deepcopy(node);updated['style']['fill']=''.join(f'{v:02X}' for v in paint)
    proposal={'baseline_hash':selected['pptx']['sha256'],'source_hash':state['source']['sha256'],
        'unit':unit['id'],'object':updated,'allowed_changes':{ident:['style.fill']},
        'cause':request.get('cause','Source-native uniform material differs in its saved actual response'),
        'original_evidence':request['source_evidence']}
    file=folder/'native-proposal.json';write_json(file,proposal)
    record={'status':'BOUNDED_NATIVE_MATERIAL_REQUIRES_ACTUAL_DRAWING','unit':unit['id'],
        'baseline_hash':selected['pptx']['sha256'],'source_hash':state['source']['sha256'],
        'proposal':{'path':file.relative_to(task).as_posix(),'sha256':digest(file)},
        'fixed_histogram_mode':mode,'fixed_histogram_scope':scope or 'evaluation_domain','paint_search':'finite_source_integer_box' if mode=='hard' else 'bounded_continuous_response','original_paint_rgb':anchor.tolist(),'old_native_paint_rgb':native.tolist(),'proposed_native_paint_rgb':paint.tolist(),
        'actual_before_tv':predicted(native),'predicted_only_after_tv':predicted(paint),
        'response_samples':response_samples,'fixed_original_samples':int(owned.sum()),
        'next':'Compile the hashed proposal with native-proposal-action; submit through the current located repair and observe each changed part/affected relation.',
        'preserved':'Source masks/targets, content, contour, pose, native group frames and every other object',
        'limits':'Prediction is not a saved drawing score. No candidate-dependent metric masking, blur imitation, geometry repair, semantic acceptance or global retry.'}
    write_json(record_file,record);return record
