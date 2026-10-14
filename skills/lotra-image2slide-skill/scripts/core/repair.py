"""Executed source-parameter fits and versioned local repair proposals.

Generation sampling choices are recorded separately from frozen evaluation.
No operation adds scientific facts or silently changes the reference plan.
"""
import copy
import time
import math
import numpy as np
from scipy.optimize import least_squares
from scipy import ndimage as ndi
from PIL import Image
from skimage.measure import find_contours
from skimage.measure import approximate_polygon
from skimage.morphology import skeletonize
from .common import digest,identity,read_json,write_json,safe_path
from .dependencies import make_patch
from .state import patch_scene,commit_patch
from .typed_metrics import rgb

VERSION='source-parameter-repair-0.2.0'


def visual_repair_brief(issue, scopes, frozen):
    """Open-ended host diagnosis with existing deterministic tools as options."""
    owner = issue.get('owner')
    scope = scopes.get(owner, {})
    return {'expected': issue['expected'], 'actual': issue['actual'], 'source_roi': issue['roi'],
            'render_ids': scope.get('ids', []), 'appearance_policy': scope.get('appearance_policy'),
            'needs_source_analysis_update': owner is None,
            'frozen_owner': owner in frozen if owner else False,
            'method_menu': ['native parameter/shape/path repair', 'add missing semantic part',
                            'restructure semantic layers', 'complete or regenerate full HD illustrative asset',
                            'local masked composition', 'actual available desktop editor'],
            'instruction': 'Choose a cause and the smallest useful change from the observed images. This menu is not an exhaustive defect classifier. Preserve frozen content; use a new hypothesis after failure.'}


def fit_circle(image,roi,selector):
    x,y,w,h=roi;rgba=np.asarray(image.convert('RGBA'))[y:y+h,x:x+w];data=rgba[...,:3].astype(float)
    color=np.asarray(selector['rgb']);mask=(np.linalg.norm(data-color,axis=2)<=selector['distance_rgb_255'])&(rgba[...,3]>=128)
    labels,count=ndi.label(mask)
    if not count:raise ValueError('No source-supported circle pixels')
    sizes=np.bincount(labels.ravel());sizes[0]=0;mask=labels==int(np.argmax(sizes))
    # Close ROI-edge components before finding the exterior. Without padding,
    # an attached arrow cuts the exterior into open arcs and the longest contour
    # can be an internal hole of an X/circle symbol, yielding a false tiny circle.
    contours=find_contours(np.pad(mask,1).astype(float),.5)
    if not contours:raise ValueError('No source-supported circle boundary')
    # The largest perimeter is the visible exterior, not an annulus interior.
    points=max(contours,key=len)[:,::-1]+[x-1,y-1]
    center=points.mean(axis=0);radius=np.mean(np.linalg.norm(points-center,axis=1))
    solved=least_squares(lambda p:np.linalg.norm(points-p[:2],axis=1)-p[2],[*center,radius],loss='soft_l1')
    cx,cy,r=map(float,solved.x)
    if r<=0 or not x<=cx<=x+w or not y<=cy<=y+h:raise ValueError('Circle fit leaves observed ROI')
    return {'bbox':[cx-r,cy-r,2*r,2*r],'center':[cx,cy],'radius':r,
            'fit_residual_px':float(np.mean(np.abs(solved.fun))),'source_points':len(points),
            'method':'visible connected component exterior + robust geometric circle fit'}


def fit_color(image,samples):
    data=np.asarray(image.convert('RGB'));values=[]
    for x,y in samples:
        if not 0<=x<data.shape[1] or not 0<=y<data.shape[0]:raise ValueError('Color sample outside source')
        values.append(data[y,x])
    if not values:raise ValueError('No source color samples')
    color=np.round(np.median(values,axis=0)).astype(int)
    return {'fill':''.join(f'{c:02X}' for c in color),'samples':len(values),'method':'median of explicit source sample locations'}


def fit_gradient(image,roi,selector,angle=90):
    x,y,w,h=roi;data=np.asarray(image.convert('RGB'))[y:y+h,x:x+w].astype(float)
    mask=np.linalg.norm(data-np.asarray(selector['rgb']),axis=2)<=selector['distance_rgb_255']
    yy,xx=np.where(mask)
    if len(xx)<20:raise ValueError('Insufficient source fill samples')
    theta=math.radians(angle);projection=(xx/(max(w-1,1)))*math.cos(theta)+(yy/max(h-1,1))*math.sin(theta)
    corners=np.array([0,math.cos(theta),math.sin(theta),math.cos(theta)+math.sin(theta)])
    low,high=float(corners.min()),float(corners.max());t=(projection-low)/(high-low)
    design=np.column_stack([np.ones(len(t)),t]);coeff=np.linalg.lstsq(design,data[yy,xx],rcond=None)[0]
    colors=np.clip(np.round([coeff[0],coeff.sum(axis=0)]),0,255).astype(int)
    return {'gradient':[''.join(f'{c:02X}' for c in row) for row in colors],'gradient_angle':angle,
            'source_pixels':len(t),'fit_rgb_mae':float(np.abs(design@coeff-data[yy,xx]).mean()),
            'method':'fixed-axis linear RGB least-squares on explicitly selected source fill'}


def sample_polyline(points,count=128):
    p=np.asarray(points,float);length=np.linalg.norm(np.diff(p,axis=0),axis=1);distance=np.r_[0,np.cumsum(length)]
    if not distance[-1]:raise ValueError('Zero length path')
    t=np.linspace(0,distance[-1],count)
    return np.column_stack([np.interp(t,distance,p[:,i]) for i in (0,1)])


def fit_path(image,obj,settings):
    from .geometry import path_operations
    if obj['render_type']!='path' or len(obj['content'].get('contours',[]))!=1:raise ValueError('Curve parameter fitting needs one explicit semantic path')
    contour=obj['content']['contours'][0];commands=path_operations(contour)
    coords=np.array([p for _,points in commands for p in points],float)
    x,y,w,h=obj['bbox'];original=coords*[w,h]+[x,y]
    rgba=np.asarray(image.convert('RGBA'));selector=settings['selector'];mask=(np.linalg.norm(rgba[...,:3].astype(float)-selector['rgb'],axis=2)<=selector['distance_rgb_255'])&(rgba[...,3]>=128)
    rx,ry,rw,rh=settings['roi'];bounded=np.zeros(mask.shape,bool);bounded[ry:ry+rh,rx:rx+rw]=True;mask&=bounded
    skel=skeletonize(mask)
    if not skel.any():raise ValueError('No observed source stroke for fitting')
    distance=ndi.distance_transform_edt(~skel);offsets=[];index=0
    for kind,points in commands:offsets.append((kind,index,len(points)));index+=len(points)
    def sampled(values):
        start=None;current=None;result=[]
        for kind,index,count in offsets:
            p=values[index:index+count]
            if kind=='moveTo':current=p[0];start=current;continue
            t=np.linspace(0,1,33)[:,None]
            if kind=='lnTo':segment=current*(1-t)+p[0]*t;current=p[0]
            elif kind=='cubicBezTo':segment=current*(1-t)**3+3*p[0]*t*(1-t)**2+3*p[1]*t*t*(1-t)+p[2]*t**3;current=p[2]
            elif kind=='quadBezTo':segment=current*(1-t)**2+2*p[0]*t*(1-t)+p[1]*t*t;current=p[1]
            else:segment=current*(1-t)+start*t;current=start
            result.extend(segment)
        return np.asarray(result)
    fixed=set(settings.get('fixed_point_indices',[0,len(original)-1]));free=[i for i in range(len(original)) if i not in fixed]
    limit=float(settings['maximum_displacement_px'])
    if not 0<limit<=50:raise ValueError('Path fitting requires a bounded local displacement')
    def residual(vector):
        value=original.copy();value[free]=vector.reshape(-1,2);points=sampled(value)
        distances=ndi.map_coordinates(distance,[points[:,1],points[:,0]],order=1,mode='constant',cval=limit*2)
        return np.r_[distances,.01*(value-original).ravel()]
    # A rectangular two-coordinate bound permits sqrt(2)*limit movement. Use
    # the inscribed square so the declared Euclidean safety bound is true.
    coordinate_limit=limit/math.sqrt(2)
    solution=least_squares(residual,original[free].ravel(),bounds=((original[free]-coordinate_limit).ravel(),(original[free]+coordinate_limit).ravel()),max_nfev=80)
    result=original.copy();result[free]=solution.x.reshape(-1,2);normalized=(result-[x,y])/[w,h];new=[]
    for kind,index,count in offsets:new.append({'op':kind,'points':normalized[index:index+count].tolist()})
    return {'contours':[{'commands':new}], 'before_centerline_distance_px':float(residual(original[free].ravel())[:len(sampled(original))].mean()),
            'after_centerline_distance_px':float(residual(solution.x)[:len(sampled(result))].mean()),
            'max_control_displacement_px':float(np.max(np.linalg.norm(result-original,axis=1))),
            'source_skeleton_pixels':int(skel.sum()),'optimizer_evaluations':solution.nfev,
            'method':'bounded control-point fit to observed stroke skeleton; topology and fixed landmarks preserved'}


def fit_boundary_segment(image,obj,settings):
    """Trace one observed part-boundary segment, never the full figure."""
    from .geometry import path_operations
    if obj['render_type']!='path' or len(obj['content'].get('contours',[]))!=1:raise ValueError('Boundary segment needs one mapped natural-part path')
    x,y,w,h=settings['roi'];data=np.asarray(image.convert('RGBA'))[y:y+h,x:x+w]
    selector=settings['selector'];mask=(np.linalg.norm(data[...,:3].astype(float)-selector['rgb'],axis=2)<=selector['distance_rgb_255'])&(data[...,3]>=128)
    side=settings['side'];points=[]
    if side not in ('left','right','top','bottom'):raise ValueError('Boundary side must be explicit')
    for index in range(h if side in ('left','right') else w):
        positions=np.flatnonzero(mask[index] if side in ('left','right') else mask[:,index])
        if len(positions):
            v=int(positions.min() if side in ('left','top') else positions.max())
            points.append([x+v,y+index] if side in ('left','right') else [x+index,y+v])
    if len(points)<3:raise ValueError('No sufficiently observed boundary segment')
    points=approximate_polygon(np.asarray(points,float),tolerance=settings['simplification_px'])
    old=path_operations(obj['content']['contours'][0]);start,end=settings['replace_commands']
    if not 1<=start<end<=len(old):raise ValueError('Replacement may not discard the contour origin or arbitrary paths')
    bx,by,bw,bh=obj['bbox'];normalized=[[(px-bx)/bw,(py-by)/bh] for px,py in points]
    commands=[{'op':k,'points':p} for k,p in old[:start]]+[{'op':'lnTo','points':[p]} for p in normalized]+[{'op':k,'points':p} for k,p in old[end:]]
    return {'contours':[{'commands':commands}],'source_boundary_points':points.tolist(),'source_pixels':int(mask.sum()),
            'method':'observed color-boundary extremum per scanline, fixed simplification; retained surrounding semantic path'}


def propose(scene,base,work_order,action_id,*,defect=None):
    if work_order['work_order_hash']!=identity({k:v for k,v in work_order.items() if k!='work_order_hash'}):raise ValueError('Work order changed')
    if work_order['source_hash']!=scene['source']['sha256']:raise ValueError('Work order uses another source')
    source=safe_path(base,scene['source']['path'])
    if digest(source)!=scene['source']['sha256']:raise ValueError('Frozen source changed')
    action=work_order['actions'][action_id];objects={o['id']:o for o in scene['objects']};outputs=[];operations=[]
    if not set(action['targets'])<=set(work_order['render_ids']):raise ValueError('Cross-object repair')
    image=Image.open(source);start=time.monotonic()
    for target in action['targets']:
        obj=objects[target];params=action.get('parameters',{});observation=action.get('source_fit',{})
        if action['op']=='fit_circle':
            fit=fit_circle(image,observation['roi'],observation['selector'])
            if observation.get('boundary')=='outer_stroke':
                stroke=float(observation['stroke_width_px'])
                if not 0<=stroke<2*fit['radius']:raise ValueError('Invalid observed stroke width')
                fit['observed_outer_bbox']=list(fit['bbox']);fit['stroke_inset_px']=stroke/2
                x,y,w,h=fit['bbox'];fit['bbox']=[x+stroke/2,y+stroke/2,w-stroke,h-stroke]
                fit['method']+='; inset observed outer stroke to native ellipse centerline'
            operations.append({'object_id':target,'field':'bbox','value':fit['bbox']})
            if obj['render_type']!='shape' or obj['content'].get('preset')!='ellipse':
                content=copy.deepcopy(obj['content']);content['preset']='ellipse';content.pop('contours',None)
                operations.extend([{'object_id':target,'field':'content','value':content},{'object_id':target,'field':'render_type','value':'shape'}])
        elif action['op'] in ('fit_color','fit_linear_gradient'):
            fit=fit_color(image,observation['samples']) if action['op']=='fit_color' else fit_gradient(image,observation['roi'],observation['selector'],observation.get('angle',90))
            style=copy.deepcopy(obj['style']);style.update({k:fit[k] for k in ('fill','gradient','gradient_angle') if k in fit})
            if action['op']=='fit_color':
                # A stale gradient otherwise silently wins over the fitted fill.
                style.pop('gradient',None);style.pop('gradient_angle',None)
            operations.append({'object_id':target,'field':'style','value':style})
        elif action['op']=='fit_path':
            fit=fit_path(image,obj,observation);content=copy.deepcopy(obj['content']);content['contours']=fit['contours']
            operations.append({'object_id':target,'field':'content','value':content})
            for coupled in action.get('coupled',[]):
                other=objects[coupled['target']]
                if other['id'] not in work_order['render_ids'] or other['bbox']!=obj['bbox']:raise ValueError('Coupled path must be authorized in the same coordinate frame')
                if other['render_type']!='path':raise ValueError('Coupled geometry is not a path')
                from .geometry import path_operations
                old=path_operations(other['content']['contours'][0]);count=coupled['prefix_commands']
                if count>len(fit['contours'][0]['commands']) or count>len(old):raise ValueError('Invalid shared curve prefix')
                commands=copy.deepcopy(fit['contours'][0]['commands'][:count])+[{'op':k,'points':p} for k,p in old[count:]]
                updated=copy.deepcopy(other['content']);updated['contours']=[{'commands':commands}]
                operations.append({'object_id':other['id'],'field':'content','value':updated})
        elif action['op']=='fit_boundary_segment':
            fit=fit_boundary_segment(image,obj,observation);content=copy.deepcopy(obj['content']);content['contours']=fit['contours']
            operations.append({'object_id':target,'field':'content','value':content})
        elif action['op']=='set_parameters':
            fit={'parameters':params};style=copy.deepcopy(obj['style']);content=copy.deepcopy(obj['content'])
            for key,value in params.items():
                if key=='bbox':operations.append({'object_id':target,'field':'bbox','value':value})
                elif key in ('preset','adjustments','radius_px','contours','arrow_width','arrow_length','row_heights','column_widths','merges'):
                    content[key]=value
                elif key=='route_points':
                    if obj['render_type']!='connector':raise ValueError('route_points requires a connector')
                    content['points']=value;content['coordinate_space']='canvas'
                elif key=='path_points':
                    if obj['render_type']!='path' or len(content.get('contours',[]))!=1:raise ValueError('path_points requires one explicit path')
                    content['contours']=[{'points':value,'closed':content['contours'][0].get('closed',False)}]
                elif key in ('z_order','component'):operations.append({'object_id':target,'field':key,'value':value})
                elif key in ('fill','gradient','gradient_angle','line_width','font','font_size','bold','char_spacing_pt','baseline_offset_pt','padding'):
                    style[key]=value
                else:raise ValueError('Parameter has no implemented destination: '+key)
            if style!=obj['style']:operations.append({'object_id':target,'field':'style','value':style})
            if content!=obj['content']:operations.append({'object_id':target,'field':'content','value':content})
        else:raise ValueError('This operation needs explicit host/parameter candidate generation: '+action['op'])
        outputs.append({'target':target,'fit':fit})
    operations=[op for op in operations if objects[op['object_id']].get(op['field'])!=op['value']]
    if not operations:raise ValueError('No changed drawing decision')
    task_id='repair-'+work_order['object_id']+'-'+str(action_id)
    patch=make_patch(scene,operations,task_id)
    translation=max([abs(op['value'][i]-objects[op['object_id']]['bbox'][i]) for op in operations if op['field']=='bbox' for i in (0,1)]+[0.])
    grant={'task_id':task_id,'object_ids':sorted({op['object_id'] for op in operations}),
           'allowed_fields':sorted({op['field'] for op in operations}),'role':'geometry_worker',
           'max_translation_px':translation,'allow_uniform_scale':True}
    # These grants are proposals; the coordinator must authorize them separately.
    return {'version':VERSION,'work_order_hash':work_order['work_order_hash'],'knowledge_id':action['knowledge_id'],
            'executed_action':action,'fits':outputs,'patch':patch,'proposed_grant':grant,'defect':defect,
            'source_hash':digest(source),'elapsed_seconds':time.monotonic()-start,'status':'PROPOSED_NOT_COMMITTED',
            'scope':'Fit executed; candidate drawing/rendering and improvement not yet verified'}


def execute(scene,base,work_order,action_id,state_directory,grant,output,defect=None):
    result=propose(scene,base,work_order,action_id,defect=defect)
    commit=commit_patch(state_directory,result['patch'],grant,base)
    result.update(commit=commit,status='COMMITTED_REQUIRES_RENDER_AND_EVALUATION')
    write_json(output,result);return result
