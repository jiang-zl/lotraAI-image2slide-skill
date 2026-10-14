"""Fit an independently observed hollow right-arrow to one native preset.

Only original source pixels set box, head, shaft and stroke parameters. Source
blur is a fitted nuisance, never a raster blur applied to the native shape.
The same program works for arbitrary bounded source arrows of this family;
actual saved native part quality and protected context decide adoption.
"""
import numpy as np
from scipy.optimize import least_squares
from scipy.special import ndtr


def fit_hollow_right_arrow(rgb, owned, foreground, background, family):
    if (family.get('semantic_shape')!='hollow_right_arrow' or family.get('direction')!='right'
            or family.get('head_count')!=1 or not family.get('source_evidence')):
        raise ValueError('Observe one hollow right-arrow and its source head/shaft before preset fitting')
    data=np.asarray(rgb,float);mask=np.asarray(owned,bool);paint=np.asarray(foreground,float);paper=np.asarray(background,float)
    h,w=mask.shape
    if (data.shape!=(h,w,3) or min(h,w)<8 or max(h,w)>300 or mask.sum()<30
            or paint.shape!=(3,) or paper.shape!=(3,) or not np.isfinite(data).all()):
        raise ValueError('One bounded original arrow with explicit ink/ground samples is required')
    yy,xx=np.indices((h,w),float);xx+=.5;yy+=.5
    sy,sx=np.where(mask);left=float(sx.min()+1);top=float(sy.min()+1)
    width=float(sx.max()-sx.min()-1);height=float(sy.max()-sy.min()-1)
    if min(height,width)<8 or width<height:raise ValueError('Original support does not establish this horizontal preset')
    initial=np.array([left,top,width,height,.46,.75,2.,.65])
    lower=[left-3,top-3,width-6,height-6,.20,.22,.65,.25]
    upper=[left+3,top+3,width+6,height+6,.85,min(1.3,width/height-.1),4.2,1.6]
    initial=np.clip(initial,np.array(lower)+1e-6,np.array(upper)-1e-6)
    def polygon(p):
        x,y,ww,hh,shaft,head,stroke,sigma=p;cx=x+ww-hh*head;mid=y+hh/2;half=hh*shaft/2
        return np.array([[x,mid-half],[cx,mid-half],[cx,y],[x+ww,mid],
                         [cx,y+hh],[cx,mid+half],[x,mid+half]])
    def prediction(p):
        points=polygon(p);distance=np.full((h,w),np.inf)
        for first,last in zip(points,np.roll(points,-1,axis=0)):
            dx,dy=last-first;denom=dx*dx+dy*dy
            if denom<1e-10:return np.full(data.shape,255.)
            along=np.clip(((xx-first[0])*dx+(yy-first[1])*dy)/denom,0,1)
            distance=np.minimum(distance,np.hypot(xx-first[0]-along*dx,yy-first[1]-along*dy))
        alpha=ndtr((p[6]/2-distance)/p[7]);return paper+(paint-paper)*alpha[...,None]
    def residual(p):return ((prediction(p)-data)/255).ravel()
    solution=least_squares(residual,initial,bounds=(lower,upper),loss='soft_l1',f_scale=.06,max_nfev=120,x_scale='jac')
    p=solution.x
    if (not np.isfinite(p).all() or p[2]<=p[3]*p[5]+2 or p[0]<-2 or p[1]<-2
            or p[0]+p[2]>w+2 or p[1]+p[3]>h+2):
        raise ValueError('Original fit leaves the bounded source arrow frame')
    return {'bbox_local':p[:4].tolist(),'adjustments':p[4:6].tolist(),'line_width':float(p[6]),
        'audit':{'family':'one_native_hollow_right_arrow','source_evidence':family['source_evidence'],
            'source_owned_samples':int(mask.sum()),'parameters':p.tolist(),
            'parameter_names':['left','top','width','height','shaft_fraction','head_fraction_of_short_side','stroke_width','source_blur_sigma'],
            'original_rgb_rms':float(np.sqrt(np.mean(residual(p)**2))),
            'native_representation':'One editable rightArrow preset with source-fitted adjustments and dark contour; no fragments or raster display.',
            'limits':'Bounded original proposal only; actual saved native own-unit and relation/context effects decide adoption. Source blur is not applied to the native shape.'}}


"""Fit one original, independently located flat mark to one native primitive.

The host declares circle or round vertical stroke, original ink and uniform
ground. Source blur is a fitting nuisance; the native result stays sharp.
"""
def fit_flat_mark(rgb,owned,foreground,background,family):
    import numpy as np
    from scipy.optimize import least_squares
    from scipy.special import ndtr
    kind=family.get('semantic_shape')
    if kind not in ('filled_circle','round_vertical_stroke') or not family.get('source_evidence'):
        raise ValueError('Locate and independently observe one circle or round vertical stroke first')
    data=np.asarray(rgb,float);mask=np.asarray(owned,bool);paint=np.asarray(foreground,float);ground=np.asarray(background,float)
    h,w=mask.shape
    if data.shape!=(h,w,3) or min(h,w)<3 or max(h,w)>72 or mask.sum()<3 or paint.shape!=(3,) or ground.shape!=(3,) or np.linalg.norm(paint-ground)<45 or not np.isfinite(data).all():
        raise ValueError('Use one small source-isolated mark with explicit original ink/ground contrast')
    yy,xx=np.indices((h,w),float);xx+=.5;yy+=.5
    contrast=ground-paint
    alpha=np.clip(((data-ground)*(-contrast)).sum(2)/np.square(contrast).sum(),0,1)
    weight=alpha*mask;total=weight.sum()
    if total<1:raise ValueError('The original mark is not identified by its declared ink and ground')
    cx=float((xx*weight).sum()/total);cy=float((yy*weight).sum()/total)
    sy,sx=np.where(mask)
    if kind=='filled_circle':
        radius=max(.6,min(float(np.ptp(sx)+1),float(np.ptp(sy)+1))/2-.3)
        initial=[cx,cy,radius,.65]
        lower=[max(.2,cx-1.5),max(.2,cy-1.5),.45,.20]
        upper=[min(w-.2,cx+1.5),min(h-.2,cy+1.5),min(w,h)/2,1.5]
        def coverage(p):return ndtr((p[2]-np.hypot(xx-p[0],yy-p[1]))/p[3])
        names=['center_x','center_y','radius','source_blur_sigma']
    else:
        width=max(.65,float(np.ptp(sx)+1)-.6);length=max(1.,float(np.ptp(sy)+1)-width)
        initial=[cx,cy,length,width,.65]
        lower=[max(.2,cx-1.5),max(.2,cy-2),max(.5,length-3),.5,.20]
        upper=[min(w-.2,cx+1.5),min(h-.2,cy+2),min(h-1,length+3),min(4.,w-1),1.5]
        def coverage(p):
            distance=np.hypot(xx-p[0],np.maximum(np.abs(yy-p[1])-p[2]/2,0))
            return ndtr((p[3]/2-distance)/p[4])
        names=['center_x','center_y','centerline_length','stroke_width','source_blur_sigma']
    lower=np.asarray(lower);upper=np.asarray(upper)
    if np.any(upper<=lower):raise ValueError('Original mark extent does not identify this declared primitive')
    initial=np.clip(initial,lower+1e-6,upper-1e-6)
    def residual(p):return ((ground+(paint-ground)*coverage(p)[...,None]-data)/255)[mask].ravel()
    solution=least_squares(residual,initial,bounds=(lower,upper),loss='soft_l1',f_scale=.055,max_nfev=90,x_scale='jac');p=solution.x
    if not np.isfinite(p).all():raise ValueError('Original mark fit must remain finite')
    if kind=='filled_circle':
        bbox=[p[0]-p[2],p[1]-p[2],2*p[2],2*p[2]];style={'fill':''.join(f'{int(v):02X}' for v in paint),'stroke':None};content={'preset':'ellipse'};render_type='shape'
    else:
        bbox=[p[0],p[1]-p[2]/2,.001,p[2]];style={'fill':None,'stroke':''.join(f'{int(v):02X}' for v in paint),'source_line_width':float(p[3]),'line_cap':'round'};content={'contours':[{'closed':False,'points':[[0.,0.],[0.,1.]]}]};render_type='path'
    if bbox[0]<-1 or bbox[1]<-1 or bbox[0]+bbox[2]>w+1 or bbox[1]+bbox[3]>h+1:
        raise ValueError('Fitted mark leaves its original bounded owner window')
    return {'bbox_local':list(map(float,bbox)),'style':style,'content':content,'render_type':render_type,'audit':{'family':'one_native_'+kind,'source_evidence':family['source_evidence'],'source_owned_samples':int(mask.sum()),'parameter_names':names,'parameters':p.tolist(),'original_rgb_rms':float(np.sqrt(np.mean(residual(p)**2))),'limits':'Original geometric proposal only. Preserve true source coordinate/frame and native point units. Source blur is never drawn; actual saved own part and protected context determine adoption.'}}


def clip_plane_to_ellipse(node, container):
    """One continuous flat native plane inside an evidenced convex container."""
    import copy,math
    import numpy as np
    if (node.get('render_type')!='path' or container.get('preset')!='ellipse'
            or not container.get('source_evidence')
            or container.get('semantic_role')!='continuous_background_plane'):
        raise ValueError('Clip only an explicitly source-owned continuous background plane')
    contours=node['content']['contours']
    if len(contours)!=1 or not contours[0].get('closed'):
        raise ValueError('Do not flatten separate parts or natural holes into one plane')
    x,y,w,h=map(float,node['bbox']);cx,cy,cw,ch=map(float,container['bbox'])
    if min(w,h,cw,ch)<=0:raise ValueError('Native source-coordinate extents must be positive')
    if node.get('rotation',node.get('style',{}).get('rotation',0)):
        raise ValueError('Use saved-affine clipping for an already rotated source plane')
    def point(p):return np.array([x+p[0]*w,y+p[1]*h],float)
    contour=contours[0];curves=[]
    if contour.get('commands'):
        current=None;start=None
        for command in contour['commands']:
            op=command['op'];pts=[point(p) for p in command.get('points',[])]
            if op=='moveTo':current=start=pts[0]
            elif op=='lnTo':curves.append(np.array([current,pts[0]]));current=pts[0]
            elif op in ('cubicBezTo','quadBezTo'):
                curves.append(np.array([current]+pts))
                current=pts[-1]
            elif op=='close':curves.append(np.array([current,start]));current=start
            else:raise ValueError('Preserve unsupported path semantics instead of guessing a clip')
    else:
        points=[point(p) for p in contour['points']]
        curves=[np.array([a,b]) for a,b in zip(points,points[1:]+points[:1])]
    from .boundary_geometry import clip_polygon
    compact,proof=clip_polygon(curves,np.array([cx+cw/2,cy+ch/2]),np.diag([cw/2,ch/2]),
        container.get('precision_px',.01),container.get('inset_px',.02))
    result=copy.deepcopy(node)
    result['content']['contours']=[{'closed':True,'points':[[(float(p[0])-x)/w,(float(p[1])-y)/h] for p in compact]}]
    result['content']['clip_geometry']=proof
    return result
