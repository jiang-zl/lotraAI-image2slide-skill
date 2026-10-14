"""One continuous native material band from visible source windows.

The host locates the natural road/material role, anchors and hidden constraints.
This is a bounded proposal, never an unknown-curve classifier or acceptance.
"""
from pathlib import Path
import copy,math
import numpy as np
from scipy.optimize import least_squares
from skimage.measure import find_contours,approximate_polygon
from .common import safe_path,read_json,digest,identity,write_json


def propose(task,request):
    from .agent_runtime import _state
    from .source_quality import _mask
    from .source_domains import debt
    task,state=_state(task);packet=state.get('packet') or {};baseline=state.get('selected') or {}
    if (packet.get('kind')!='repair' or packet.get('packet_id')!=request.get('packet_id')
            or baseline.get('pptx',{}).get('sha256')!=request.get('baseline_hash') or state.get('pending_built')):
        raise ValueError('Bind the current located repair and actual saved baseline')
    unit=state['quality']['units'][request['unit']]
    issue=next(i for i in state['issues'] if i['id']==packet['target'] and i['status']=='open')
    if issue.get('quality_unit')!=unit['id']:raise ValueError('Locate this independent source-band defect first')
    if request.get('semantic_role') not in ('road_band','decorative_material_band'):
        raise ValueError('This family fits natural material bands, never scientific graph/data curves')
    if not unit.get('layering') or debt(task,state,unit):
        raise ValueError('Define original visible layer ownership before fitting hidden continuity')
    if (request.get('source_view_hash') not in [v['sha256'] for v in packet.get('views',[]) if v['role']=='source']
            or not request.get('hidden_constraints') or not request.get('source_geometry_evidence')):
        raise ValueError('Use the original observation and concrete bounded hidden geometry')
    if len(unit['objects'])!=1:raise ValueError('Recurse to one independently editable native material path')
    owner=unit['owner'];objects=state['built'][owner]['objects']
    old=next(o for o in objects if o['id']==unit['objects'][0])
    if old['render_type'] not in ('shape','path','bezier'):raise ValueError('Keep existing native text/math/groups separate')
    x,y,rw,rh=unit['roi'];bx,by,right,bottom=map(round,(x,y,x+rw,y+rh));w,h=right-bx,bottom-by
    if min(w,h)<6 or max(w,h)>400 or w*h>60000:raise ValueError('Fit one source-located natural band, not a whole scene')
    anchors=np.asarray(request['center_anchors'],dtype=float)
    if (anchors.shape!=(3,2) or not np.isfinite(anchors).all() or not np.all(np.diff(anchors[:,0])>0)
            or (anchors[:,0]<x).any() or (anchors[:,0]>x+rw).any()
            or (anchors[:,1]<y).any() or (anchors[:,1]>y+rh).any()):
        raise ValueError('Declare three original source anchors for this monotone quadratic-band family')
    lo,hi=request['width_range_px'];delta=request.get('center_y_delta_px',2.)
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (lo,hi,delta)) or not 0<lo<=hi<=min(20.,min(w,h)/2) or not 0<delta<=4:
        raise ValueError('Use a source-measured narrow band and bounded centre adjustment')
    start,end=request['hidden_extent_x']
    if not x<=start<=anchors[0,0]<anchors[-1,0]<=end<=x+rw:raise ValueError('Hidden extent must remain inside source evidence')
    clip=request['clip_ellipse'];cx,cy,cw,ch=clip
    if (not all(isinstance(v,(int,float)) and math.isfinite(v) for v in clip) or min(cx,cy)<0
            or min(cw,ch)<=0 or cx+cw>state['source_size'][0] or cy+ch>state['source_size'][1]):
        raise ValueError('Bind the source ellipse clip inside the original canvas')
    colour=request['fill_rgb']
    if len(colour)!=3 or any(type(v) is not int or not 0<=v<=255 for v in colour):raise ValueError('Original material uses finite RGB source samples')
    ref=_mask(task,unit['reference_mask']);domain=_mask(task,unit['evaluation_mask'])
    if ref.shape!=(h,w) or domain.shape!=(h,w) or not (ref&domain).any():raise ValueError('Source-band masks must share this fixed visible canvas')
    dependencies={'source':state['source']['sha256'],'unit':identity({k:v for k,v in unit.items() if k not in ('status','built_fingerprint')}),
        'baseline':baseline['pptx']['sha256'],'request':{k:v for k,v in request.items() if k not in ('packet_id','source_view_hash')},'implementation':digest(Path(__file__))}
    folder=task/'scratch/source-occluded-band'/identity(dependencies)[:24];folder.mkdir(parents=True,exist_ok=True)
    saved=folder/'proposal.json'
    if saved.is_file():return read_json(saved)
    def model(params,xx,yy):
        poly=np.polyfit(anchors[:,0],params[:3],2);centre=np.polyval(poly,xx)
        tangent=np.polyval(np.polyder(poly),xx);distance=np.abs(yy-centre)/np.sqrt(1+tangent*tangent)
        support=((xx-(cx+cw/2))/(cw/2))**2+((yy-(cy+ch/2))/(ch/2))**2<=1
        return np.clip((params[3]/2-distance)/.7+.5,0,1)*support*(xx>=start)*(xx<=end)
    xx,yy=np.meshgrid(np.arange(w)+bx+.5,np.arange(h)+by+.5)
    def residual(params):return model(params,xx,yy)[domain]-ref[domain].astype(float)
    initial=np.r_[anchors[:,1],(lo+hi)/2]
    lower=np.r_[np.maximum(y,anchors[:,1]-delta),lo];upper=np.r_[np.minimum(y+rh,anchors[:,1]+delta),hi]
    if np.any(lower>=upper):raise ValueError('The fitting interval must retain an actual source-constrained degree of freedom')
    fit=least_squares(residual,initial,bounds=(lower,upper),max_nfev=70,diff_step=.001,
        ftol=1e-7,xtol=1e-7,gtol=1e-7)
    scale=6;hx,hy=np.meshgrid(np.arange(w*scale)/scale+bx+.5/scale,np.arange(h*scale)/scale+by+.5/scale)
    contours=find_contours(np.pad(model(fit.x,hx,hy),1),.5)
    if len(contours)!=1:raise ValueError('This family must yield one continuous source-clipped band; recurse a branching/disconnected case')
    points=approximate_polygon(contours[0],.18*scale)-.5
    coords=[[float(c)/(w*scale),float(r)/(h*scale)] for r,c in points]
    if np.allclose(coords[0],coords[-1]):coords.pop()
    if not 4<=len(coords)<=128:raise ValueError('Use a compact native contour for one natural band')
    commands=[{'op':'moveTo','points':[coords[0]]}]
    for i,a in enumerate(coords):
        previous=coords[(i-1)%len(coords)];b=coords[(i+1)%len(coords)];following=coords[(i+2)%len(coords)]
        c1=[a[k]+(b[k]-previous[k])*.1 for k in (0,1)];c2=[b[k]-(following[k]-a[k])*.1 for k in (0,1)]
        commands.append({'op':'cubicBezTo','points':[c1,c2,b]})
    commands.append({'op':'close','points':[]})
    node=copy.deepcopy(old);node['bbox']=[bx,by,w,h]
    node['content']={'contours':[{'closed':True,'commands':commands}]}
    node['style']['fill']=''.join(format(v,'02X') for v in colour)
    fields=['geometry']
    fields.extend('bbox.'+key for i,key in enumerate(('left','top','width','height')) if old['bbox'][i]!=node['bbox'][i])
    if old['style'].get('fill')!=node['style']['fill']:fields.append('style.fill')
    result={'status':'SOURCE_CONSTRAINED_NATIVE_BAND_PROPOSAL','unit':unit['id'],'source_hash':state['source']['sha256'],
        'baseline_hash':baseline['pptx']['sha256'],'object':node,'allowed_changes':{node['id']:fields},
        'program':{'role':request['semantic_role'],'source_domain':unit['layering']['source_domain'],
            'source_geometry_evidence':request['source_geometry_evidence'],'source_clip':clip,
            'initial_anchors':anchors.tolist(),'fitted_center_y':fit.x[:3].tolist(),
            'band_width_px':float(fit.x[3]),'width_range_px':[lo,hi],'hidden_constraints':request['hidden_constraints'],
            'estimated_residual_before':float(np.mean(residual(initial)**2)),
            'estimated_residual_after':float(np.mean(residual(fit.x)**2)),
            'native_closed_paths':1,'native_curve_segments':len(coords)},
        'next':'Compile this hashed local proposal through native-proposal-action, submit normally, then compare actual independent source parts and affected relations.',
        'limits':'Hidden band is constrained inference. Estimated source-mask residual is not actual Office quality or acceptance. Preserve original native identity, parent, z-order, styles outside the explicit grant, and all other components.'}
    write_json(saved,result);return result
