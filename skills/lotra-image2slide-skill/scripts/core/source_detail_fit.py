"""Fit observed coloured rectangles and axis strokes in original-only windows.

The host supplies semantic roles, search windows and a source colour seed.
Programs calculate coordinates and palette; they never infer a hardware name.
"""
import math
import numpy as np
from scipy.ndimage import label,find_objects
from .common import safe_path,identity

def fit(task,state,request):
    from .appearance_metrics import canvas
    from .adaptive_detail import _box
    from skimage.color import rgb2lab,deltaE_ciede2000
    from .source_contract import finite
    finite(request,'source_detail_fit')
    if request.get('source_hash')!=state['source']['sha256']:raise ValueError('Original-only fit identity required')
    parts=request.get('parts',[])
    if not parts or len(parts)>256 or len({p.get('id') for p in parts})!=len(parts) or any(not p.get('id') for p in parts):
        raise ValueError('Bounded distinct original parts required')
    data=canvas(str(safe_path(task,state['source']['path'])),state['source']['sha256'],tuple(state['source_size']))
    result=[]
    for item in parts:
        box=_box(item['roi'],state['source_size']);x,y,u,v=box;patch=data[y:v,x:u]
        if not item.get('role') or not item.get('source_evidence'):raise ValueError('Observed semantic role and source location required')
        if item['kind']=='color_rect':
            sx,sy=item['seed']
            if not x<=sx<u or not y<=sy<v:raise ValueError('Original seed must lie inside its own search window')
            if not 0<=item.get('delta_e_max',20)<=100 or not 0<=item.get('outline_pad_source_px',.5)<=2:
                raise ValueError('Bounded colour and outline uncertainty required')
            if not 0<=item.get('minimum_source_support_fraction',0)<=1 or item.get('minimum_source_support_pixels',4)<1:
                raise ValueError('Finite positive original support required')
            seed=data[int(sy),int(sx)];lab=rgb2lab(patch)
            distance=deltaE_ciede2000(lab,rgb2lab(seed.reshape(1,1,3)),channel_axis=-1);mask=distance<=item.get('delta_e_max',20)
            # Explicit observed colour predicates can resolve a tiny blurred
            # patch whose seed lies in an anti-aliased transition. They are
            # finite numerical inputs, never an implicit semantic classifier.
            if item.get('channel_predicates'):
                mask=np.ones(patch.shape[:2],dtype=bool)
                for p in item['channel_predicates']:
                    if p.get('a') not in (0,1,2) or p.get('b',0) not in (0,1,2):raise ValueError('RGB channel index required')
                    if not ({'ratio_min','minimum'} & set(p)) or not 0<p.get('ratio_min',1)<=16 or not 0<=p.get('minimum',0)<=1:
                        raise ValueError('Finite bounded RGB predicate required')
                    if 'ratio_min' in p:mask &= patch[:,:,p['a']]>=patch[:,:,p['b']]*p['ratio_min']
                    if 'minimum' in p:mask &= patch[:,:,p['a']]>=p['minimum']
            ids,n=label(mask);seed_id=ids[int(sy)-y,int(sx)-x]
            if not seed_id:raise ValueError('Source colour seed has no connected support')
            sl=find_objects(ids)[seed_id-1];yy,xx=sl;selected=ids[sl]==seed_id
            if int(selected.sum())<item.get('minimum_source_support_pixels',4) or float(selected.sum())/patch.shape[0]/patch.shape[1]<item.get('minimum_source_support_fraction',0):
                raise ValueError('Colour seed lacks the declared original-region support; reobserve the seed/window')
            rgb=np.median(patch[sl][selected],axis=0);pad=item.get('outline_pad_source_px',.5)
            frame=[x+xx.start-pad,y+yy.start-pad,xx.stop-xx.start+2*pad,yy.stop-yy.start+2*pad]
            row={'id':item['id'],'kind':'rect','bbox':frame,'fill':'%02X%02X%02X'%tuple(np.rint(rgb*255).astype(int)),
                 'source_support_pixels':int(selected.sum())}
        elif item['kind']=='dark_contour':
            from skimage.measure import find_contours,approximate_polygon
            threshold=item.get('dark_threshold',.55);epsilon=item.get('simplify_source_px',.25)
            if not 0<threshold<1 or not 0<=epsilon<=1:raise ValueError('Bounded source contour extraction parameters required')
            mask=(patch@np.array([.2126,.7152,.0722]))<threshold
            ids,n=label(mask)
            if not n:raise ValueError('No original contour support')
            counts=np.bincount(ids.ravel());counts[0]=0;selected=ids==int(counts.argmax())
            if int(selected.sum())<4:raise ValueError('Unresolved original contour')
            contours=[]
            for curve in find_contours(np.pad(selected,1),.5):
                points=approximate_polygon(curve,tolerance=epsilon)-1
                contours.append({'closed':True,'points':[[float((q[1]+.5)/patch.shape[1]),float((q[0]+.5)/patch.shape[0])] for q in points]})
            row={'id':item['id'],'kind':'compound_path','bbox':[x,y,u-x,v-y],'contours':contours,'fill':'000000','source_support_pixels':int(selected.sum())}
        elif item['kind']=='visible_right_boundary':
            from scipy.optimize import least_squares
            sx,sy=item['seed']
            if not x<=sx<u or not y<=sy<v or not 0<item.get('delta_e_max',8)<=20:
                raise ValueError('A source-owned colour seed and tight original boundary contrast are required')
            colour=data[int(sy),int(sx)];lab=rgb2lab(patch)
            mask=deltaE_ciede2000(lab,rgb2lab(colour.reshape(1,1,3)),channel_axis=-1)<=item.get('delta_e_max',8)
            observations=[];column=int(sx)-x
            for yy in range(mask.shape[0]):
                if not mask[yy,column]:continue
                right=column
                while right+1<mask.shape[1] and mask[yy,right+1]:right+=1
                # A transverse lane or cropped boundary is not evidence of
                # this straight visible side; reject saturated rows.
                if right>=mask.shape[1]-2:continue
                observations.append([y+yy+.5,x+right+.5])
            if len(observations)<max(12,mask.shape[0]*.25):raise ValueError('Original visible boundary has insufficient independent rows')
            values=np.asarray(observations);middle=float(values[:,0].mean())
            def residual(p):return p[0]+p[1]*(values[:,0]-middle)-values[:,1]
            solution=least_squares(residual,[float(np.median(values[:,1])),0.],bounds=([x,-.35],[u,.35]),loss='soft_l1',f_scale=.65,max_nfev=80)
            intercept,slope=solution.x
            row={'id':item['id'],'kind':'visible_right_boundary','boundary_line':{'x_at_source_y':float(intercept),'source_y':middle,'dx_dy':float(slope)},
                 'source_support_rows':len(observations),'source_fit_rms':float(np.sqrt(np.mean(residual(solution.x)**2))),'fill':'%02X%02X%02X'%tuple(np.rint(colour*255).astype(int))}
        elif item['kind']=='axis_stroke':
            axis=item['axis']
            if axis not in ('x','y') or not 0<item.get('dark_threshold',.55)<1:raise ValueError('Source stroke axis and finite luminance threshold required')
            gray=patch@np.array([.2126,.7152,.0722]);mask=gray<item.get('dark_threshold',.55)
            counts=mask.sum(axis=1 if axis=='x' else 0);maximum=int(counts.max())
            if maximum<2:raise ValueError('No resolved original stroke support')
            eligible=np.flatnonzero(counts>=max(2,maximum*.85));weights=counts[eligible]
            center=float(np.average(eligible+.5,weights=weights));rgb=np.median(patch[mask],axis=0)
            points=[[x,y+center],[u,y+center]] if axis=='x' else [[x+center,y],[x+center,v]]
            row={'id':item['id'],'kind':'polyline','points':points,'stroke':'%02X%02X%02X'%tuple(np.rint(rgb*255).astype(int)),
                 'source_stroke_support':maximum,'source_thickness_px':int(len(eligible))}
        else:raise ValueError('Finite original rectangle, dark contour or axis-stroke fit required')
        row.update(role=item['role'],source_evidence=item['source_evidence'],fit_basis=identity({'source':state['source'],'request':item}))
        result.append(row)
    return {'source_hash':state['source']['sha256'],'parts':result,'request_basis':identity(request)}
