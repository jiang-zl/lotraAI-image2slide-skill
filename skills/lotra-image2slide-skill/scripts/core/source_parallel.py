"""Original-observed parallel curved bands with clear native rounded ends.

This conditional family is not a named-icon substitution. It consumes two
independently owned original colour masks, a natural-part domain and observed
paints/backgrounds. Source blur is fitted only as a nuisance parameter; native
geometry is continuous. Saved Office outcomes still decide acceptance.
"""
import numpy as np
from scipy.optimize import least_squares
from scipy.special import ndtr
from skimage.measure import find_contours, approximate_polygon


def fit_parallel(rgb, owned, material_masks, paints, backgrounds, family):
    if (family.get('band_count') != 2 or family.get('central_mast') is not False
            or family.get('rounded_caps') is not True or not family.get('source_evidence')):
        raise ValueError('Independently observe two parallel curved bands and rounded caps without a mast')
    data=np.asarray(rgb,float);owned=np.asarray(owned,bool)
    masks=[np.asarray(v,bool) for v in material_masks]
    colours=np.asarray(paints,float);backgrounds=np.asarray(backgrounds,float)
    h,w=owned.shape
    if (data.shape!=(h,w,3) or len(masks)!=2 or any(m.shape!=owned.shape for m in masks)
            or any(np.count_nonzero(m&owned)<6 for m in masks)
            or colours.shape!=(3,3) or backgrounds.ndim!=2 or backgrounds.shape[1]!=3
            or not 1<=len(backgrounds)<=12 or max(h,w)>100):
        raise ValueError('Bind one bounded natural curved pair with rim/inner/outer source paints and two owned colour masks')
    if any(np.any(m&~owned) for m in masks) or np.any(masks[0]&masks[1]):
        raise ValueError('Natural band material ownership is disjoint and stays inside its original owner')
    yy,xx=np.indices((h,w),dtype=float);xx+=.5;yy+=.5
    cloud=np.column_stack((xx[masks[0]|masks[1]],yy[masks[0]|masks[1]]))
    origin=cloud.mean(axis=0);_,axes=np.linalg.eigh(np.cov(cloud.T));direction=axes[:,-1]
    if direction[0]<0:direction=-direction
    normal=np.array([-direction[1],direction[0]])
    def frame(x,y):
        dx,dy=x-origin[0],y-origin[1]
        return dx*direction[0]+dy*direction[1],dx*normal[0]+dy*normal[1]
    uu,vv=frame(xx,yy);initial=[];lower=[];upper=[]
    for mask in masks:
        u,v=uu[mask],vv[mask]
        # Original column medians constrain the natural centreline, not a
        # hard colour-membership polygon. Endpoint support includes source AA.
        bins=np.rint(u).astype(int);us=[];vs=[];widths=[]
        for b in sorted(set(bins)):
            selected=bins==b;us.append(float(np.median(u[selected])));vs.append(float(np.median(v[selected])))
            widths.append(float(np.ptp(v[selected])+1))
        if len(us)<5:raise ValueError('A short ambiguous mark does not establish a curved-band family')
        quadratic=np.polyfit(us,vs,2);a,b,c=quadratic
        width=float(np.clip(np.median(widths),.8,3.4))
        lo=float(np.quantile(u,.015)+width*.25);hi=float(np.quantile(u,.985)-width*.25)
        if hi-lo<5:raise ValueError('Read independently observable curved endpoints')
        initial.extend([lo,hi,c,b,a,width])
        lower.extend([lo-1.1,hi-1.1,c-1.3,b-.22,a-.025,.55])
        upper.extend([lo+1.1,hi+1.1,c+1.3,b+.22,a+.025,4.0])
    initial.extend([.65,.65]);lower.extend([.28,.25]);upper.extend([1.15,1.3])
    initial=np.clip(initial,np.array(lower)+1e-5,np.array(upper)-1e-5)
    # Original-only neighboring-owner exclusions can be supplied separately.
    domain=np.asarray(family.get('evaluation_mask',np.ones((h,w),bool)),bool)
    if domain.shape!=owned.shape or np.any(owned&~domain):raise ValueError('Keep all owned original support inside the fitting domain')
    dist=np.linalg.norm(data[:,:,None,:]-backgrounds,axis=3)
    bg=backgrounds[dist.argmin(axis=2)]
    def distance(p,u,v,extra=0.):
        lo,hi,c,b,a,width=p;along=np.clip(u,lo,hi);centre=c+b*along+a*along*along
        slope=b+2*a*along
        inside=np.abs(v-centre)/np.sqrt(1+slope*slope)
        ends=np.hypot(u-along,v-centre)
        return np.where((u>=lo)&(u<=hi),inside,ends)-(width+extra)/2
    def prediction(p):
        d0=distance(p[:6],uu,vv);d1=distance(p[6:12],uu,vv)
        rim=np.minimum(distance(p[:6],uu,vv,2*p[12]),distance(p[6:12],uu,vv,2*p[12]))
        alpha=ndtr(-rim/p[13]);result=bg*(1-alpha[:,:,None])+colours[0]*alpha[:,:,None]
        for d,paint in ((d0,colours[1]),(d1,colours[2])):
            alpha=ndtr(-d/p[13]);result=result*(1-alpha[:,:,None])+paint*alpha[:,:,None]
        return result
    def residual(p):
        value=(prediction(p)-data)/255
        return value[domain].ravel()
    solution=least_squares(residual,initial,bounds=(lower,upper),loss='soft_l1',f_scale=.08,max_nfev=110,x_scale='jac')
    p=solution.x
    if not np.isfinite(p).all() or any(p[j+1]-p[j]<5 for j in (0,6)):
        raise ValueError('The original does not support the declared continuous band span')
    scale=8;hy,hx=np.indices((h*scale,w*scale),dtype=float);hx=(hx+.5)/scale;hy=(hy+.5)/scale
    hu,hv=frame(hx,hy)
    surfaces=[np.minimum(distance(p[:6],hu,hv,2*p[12]),distance(p[6:12],hu,hv,2*p[12])),distance(p[:6],hu,hv),distance(p[6:12],hu,hv)]
    layers=[]
    for field in surfaces:
        paths=[]
        for raw in find_contours(np.pad(field<0,1),.5):
            points=(approximate_polygon(raw,.12*scale)-1+.5)/scale
            xy=np.column_stack((points[:,1]/w,points[:,0]/h))
            if np.linalg.norm(xy[0]-xy[-1])<1e-8:xy=xy[:-1]
            if len(xy)<4:continue
            commands=[{'op':'moveTo','points':[xy[0].tolist()]}]
            for k in range(len(xy)):
                prev,start,end,nxt=xy[(k-1)%len(xy)],xy[k],xy[(k+1)%len(xy)],xy[(k+2)%len(xy)]
                commands.append({'op':'cubicBezTo','points':[(start+(end-prev)/6).tolist(),(end-(nxt-start)/6).tolist(),end.tolist()]})
            commands.append({'op':'close','points':[]});paths.append({'closed':True,'commands':commands})
        if not 1<=len(paths)<=2:raise ValueError('A natural parallel pair has one or two continuous native contours per material')
        layers.append(paths)
    audit={'family':'parallel_curved_colour_bands_without_mast','source_evidence':family['source_evidence'],
        'original_owned_samples':int(owned.sum()),'original_material_samples':[int(m.sum()) for m in masks],
        'original_basis':{'origin':origin.tolist(),'tangent':direction.tolist(),'normal':normal.tolist()},
        'parameters':p.tolist(),'parameter_names':['inner_start','inner_end','inner_offset','inner_slope','inner_quadratic','inner_width','outer_start','outer_end','outer_offset','outer_slope','outer_quadratic','outer_width','rim_width','source_blur_sigma'],
        'source_rgb_rms':float(np.sqrt(np.mean(residual(p)**2))),'paints':colours.tolist(),'background_planes':backgrounds.tolist(),
        'native_geometry':'Clear continuous quadratic tubes with rounded endpoint caps; source blur is not applied to native paths.',
        'limits':'Bounded original proposal only. Saved actual Office drawing, independent natural-band and ancestor/dependency metrics, semantic cap/gap/style review and protection are still required.'}
    return layers,audit
