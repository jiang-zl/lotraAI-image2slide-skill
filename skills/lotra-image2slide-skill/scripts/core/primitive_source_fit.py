"""Finite original-only geometric fit after the host identifies a primitive.

Source softness is only a forward observation parameter during fitting.
The output remains a crisp editable native primitive with no blur filter.
"""
import math
import numpy as np
from .common import identity,safe_path

def fit(task,state,request):
    from .source_contract import finite
    from .adaptive_detail import _box
    from .appearance_metrics import canvas
    from scipy.optimize import minimize
    from scipy.ndimage import gaussian_filter
    from PIL import Image,ImageDraw
    finite(request,'primitive_source_fit')
    if request.get('source_hash')!=state['source']['sha256']:raise ValueError('Immutable original-only primitive fit required')
    rows=request.get('parts',[])
    if not rows or len(rows)>128 or len({r['id'] for r in rows})!=len(rows):raise ValueError('Distinct finite primitives required')
    original=canvas(str(safe_path(task,state['source']['path'])),state['source']['sha256'],tuple(state['source_size']));out=[]
    for r in rows:
        if r.get('preset') not in ('rect','ellipse','triangle','fold') or not r.get('source_evidence'):raise ValueError('Observed original primitive class required')
        x,y,u,v=_box(r['roi'],state['source_size']);data=original[y:v,x:u];h,w=data.shape[:2]
        if min(h,w)<5 or max(h,w)>128:raise ValueError('Use a resolved bounded original primitive window')
        sx,sy=r['seed']
        if not x<=sx<u or not y<=sy<v:raise ValueError('Original colour seed escaped its own primitive')
        colour=original[int(sy),int(sx)]
        similar=(np.linalg.norm(data-colour,axis=2)<.22)
        if r['preset']!='fold':similar &= data.max(axis=2)-data.min(axis=2)>.2
        if similar.sum()<4:raise ValueError('No resolved original fill support')
        colour=np.median(data[similar],axis=0);rgb=tuple(np.rint(colour*255).astype(int))
        yy,xx=np.nonzero(similar);initial=[max(0,float(xx.min())-1),max(0,float(yy.min())-2),float(xx.max()-xx.min()+3),float(yy.max()-yy.min()+4),1.4,.55]
        bounds=[(0,w-3),(0,h-3),(3,w),(3,h),(.5,2.5),(0,1.2)]
        def render(p):
            a,b,c,d,stroke,soft=p;scale=4
            im=Image.new('RGB',(w*scale,h*scale),'white');draw=ImageDraw.Draw(im);box=[a*scale,b*scale,(a+c)*scale,(b+d)*scale]
            if r['preset'] in ('triangle','fold'):
                apex=(box[0]+box[2])/2 if r['preset']=='triangle' else box[0]
                draw.polygon([apex,box[1],box[2],box[3],box[0],box[3]],fill=rgb);draw.line([apex,box[1],box[2],box[3],box[0],box[3],apex,box[1]],fill='black',width=max(1,round(stroke*scale)),joint='curve')
            else:getattr(draw,'rectangle' if r['preset']=='rect' else 'ellipse')(box,fill=rgb,outline='black',width=max(1,round(stroke*scale)))
            a=np.asarray(im.resize((w,h),Image.Resampling.LANCZOS),dtype=float)/255.
            return gaussian_filter(a,(soft,soft,0))
        def loss(p):
            overflow=max(0,p[0]+p[2]-w)+max(0,p[1]+p[3]-h)
            return float(np.mean((render(p)-data)**2))+overflow*.05
        initial=[min(hi,max(lo,z)) for z,(lo,hi) in zip(initial,bounds)]
        solved=minimize(loss,initial,bounds=bounds,method='Powell',options={'maxiter':80,'ftol':1e-7,'xtol':.01})
        a,b,c,d,stroke,soft=solved.x
        # PIL draws its border inside the supplied ink bounds; native Office
        # strokes are centred on the mathematical boundary.
        frame=[x+a+stroke/2,y+b+stroke/2,max(.1,c-stroke),max(.1,d-stroke)]
        if not np.isfinite(solved.x).all() or a+c>w+.5 or b+d>h+.5:raise ValueError('Original primitive fit escaped its frozen window')
        out.append({'id':r['id'],'preset':r['preset'],'bbox':frame,'fill':'%02X%02X%02X'%rgb,'line_width_source_px':float(stroke),
                    'source_forward_softness_px':float(soft),'output_blur':False,'source_fit_mse':loss(solved.x),'fit_basis':identity({'source':state['source'],'request':r})})
    return {'source_hash':state['source']['sha256'],'parts':out,'request_basis':identity(request)}

def fit_triangle_outline(rgb,owned,foreground,background,family):
    """Fit an observed upright hollow triangle, independently of inner marks."""
    from scipy.optimize import least_squares
    from scipy.special import ndtr
    from .source_contract import finite
    finite(family,'triangle_outline')
    if family.get('semantic_shape')!='hollow_triangle' or not family.get('source_evidence'):
        raise ValueError('An independently observed hollow triangle is required')
    data=np.asarray(rgb,float);mask=np.asarray(owned,bool);paint=np.asarray(foreground,float);ground=np.asarray(background,float)
    h,w=mask.shape
    if data.shape!=(h,w,3) or min(h,w)<8 or max(h,w)>128 or mask.sum()<24 or paint.shape!=(3,) or ground.shape!=(3,) or not np.isfinite(data).all() or np.linalg.norm(paint-ground)<45:
        raise ValueError('Resolved original contour, ink, ground and independent ownership required')
    yy,xx=np.indices((h,w),float);xx+=.5;yy+=.5
    box=family['initial_box'];initial=np.array([*box,1.6,.65],float)
    lower=np.array([box[0]-3,box[1]-3,max(5,box[2]-6),max(5,box[3]-6),.5,.2])
    upper=np.array([box[0]+3,box[1]+3,min(w,box[2]+6),min(h,box[3]+6),3.5,1.6])
    if np.any(upper<=lower):raise ValueError('Source triangle window does not identify a finite fit')
    def points(p):
        x,y,a,b=p[:4];return np.array([[x+a/2,y],[x+a,y+b],[x,y+b]])
    def prediction(p):
        vertices=points(p);distance=np.full((h,w),np.inf)
        for first,last in zip(vertices,np.roll(vertices,-1,axis=0)):
            dx,dy=last-first;along=np.clip(((xx-first[0])*dx+(yy-first[1])*dy)/(dx*dx+dy*dy),0,1)
            distance=np.minimum(distance,np.hypot(xx-first[0]-along*dx,yy-first[1]-along*dy))
        return ground+(paint-ground)*ndtr((p[4]/2-distance)/p[5])[...,None]
    def residual(p):return ((prediction(p)-data)/255)[mask].ravel()
    result=least_squares(residual,np.clip(initial,lower+1e-6,upper-1e-6),bounds=(lower,upper),loss='soft_l1',f_scale=.06,max_nfev=140,x_scale='jac');p=result.x
    if not np.isfinite(p).all() or p[0]<-1 or p[1]<-1 or p[0]+p[2]>w+1 or p[1]+p[3]>h+1:
        raise ValueError('Original triangle fit left its frozen window')
    return {'points_local':points(p).tolist(),'line_width_source_px':float(p[4]),'source_forward_softness_px':float(p[5]),'output_blur':False,'source_fit_rms':float(np.sqrt(np.mean(residual(p)**2))),'source_evidence':family['source_evidence']}

def constrain_original_gap(task,state,unit_id,contract_id,point_source_scale,axis='y'):
    """Project a fitted rectangle end onto an independently measured source gap.

    This finite operator reads original functions and original-grid masks only.
    It never trains a target or relaxes limits using the current rendering.
    Other primitive classes need their own numerical boundary constructor.
    """
    import copy
    from .source_feature_functions import specifications,semantic_root
    from .source_spacing import targets,prepare
    if axis not in ('x','y') or not math.isfinite(point_source_scale) or point_source_scale<=0:
        raise ValueError('Finite source coordinate and stroke scale required')
    unit=state['quality']['units'][unit_id];spec=copy.deepcopy(specifications(task,state)[unit_id])
    rows=[v['row'] for v in targets(task,state) if v['row'].get('id')==contract_id]
    if len(rows)!=1:raise ValueError('An exact independent original interface is required')
    row=rows[0];source,effective=prepare(task,state,row)
    if not source['passed'] or effective is None or row['relationship']!='intentional_separation':
        raise ValueError('Original spacing must resolve intentional separation before projection')
    root=semantic_root(unit,spec);separator=spec.get('name_separator','.')
    parts={root+separator+p['id']:p for p in spec['parts']}
    if len(row['objects'])!=2 or any(n not in parts for n in row['objects']):
        raise ValueError('Source interface must identify two independent constructed parts')
    first,second=[parts[n] for n in row['objects']]
    if any(p['kind']!='rect' for p in (first,second)):
        raise ValueError('This source-gap constructor supports two resolved rectangle boundaries')
    k=0 if axis=='x' else 1
    target=source['values']['nearest_original_center_distance_px'];lo,hi=effective['limits']['distance_px']
    target=min(hi,max(lo,target))
    half=lambda p:float(p.get('style',{}).get('line_width',0))*point_source_scale/2
    before=copy.deepcopy(first['bbox']);ink_start=second['bbox'][k]-half(second)
    extent=ink_start-target-half(first)-first['bbox'][k]
    if not 3<=extent<=unit['roi'][k+2]:raise ValueError('Original gap projection escaped a resolved primitive')
    first['bbox'][k+2]=extent
    record={'source_hash':state['source']['sha256'],'original_interface':contract_id,
        'original_measurement':source['values'],'axis':axis,'target_gap_source_px':target,
        'before_original_fit':before,'constrained_original_fit':first['bbox'],'output_blur':False,
        'basis':'Frozen source primitive fit and original-grid spacing; no candidate pixel input or threshold change'}
    spec['source_evidence']+=' Original-grid interface constraints projected the first rectangle end; the other source features remain fixed.'
    return spec,record
