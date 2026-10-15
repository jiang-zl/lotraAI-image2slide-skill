"""Compact continuous native curves; source blur is not output geometry.

Analytic icons use elliptical arcs/annular bands. Smooth observed illustration
outlines retain declared corners. Scientific polylines are never auto-smoothed.
"""
import copy
import math

VERSION='semantic-curves-1'
ARC_TYPES=frozenset(('signal_arc','radio_arc','radio_band_outline'))
SMOOTH_OUTLINES=frozenset(('terminal_glass','rounded_vehicle_body'))
SCIENTIFIC=frozenset(('observed_curve','signal_wave','scientific_curve','chart_curve','data_series'))


def arc(center,radii,start_degrees,end_degrees,rotation=0):
    cx,cy=center;rx,ry=radii
    values=[cx,cy,rx,ry,start_degrees,end_degrees,rotation]
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in values) or min(rx,ry)<=0 or not 0<abs(end_degrees-start_degrees)<=360:
        raise ValueError('Source-bound finite elliptical arc required')
    start,end=map(math.radians,(start_degrees,end_degrees))
    count=max(1,math.ceil(abs(end-start)/(math.pi/4)))
    tilt=math.radians(rotation);c,s=math.cos(tilt),math.sin(tilt)
    def point(t):return [cx+rx*math.cos(t)*c-ry*math.sin(t)*s,cy+rx*math.cos(t)*s+ry*math.sin(t)*c]
    def tangent(t):return [-rx*math.sin(t)*c-ry*math.cos(t)*s,-rx*math.sin(t)*s+ry*math.cos(t)*c]
    commands=[{'op':'moveTo','points':[point(start)]}]
    for i in range(count):
        a=start+(end-start)*i/count;b=start+(end-start)*(i+1)/count
        k=4/3*math.tan((b-a)/4);p,q=point(a),point(b);ta,tb=tangent(a),tangent(b)
        commands.append({'op':'cubicBezTo','points':[[p[j]+k*ta[j] for j in (0,1)],
                        [q[j]-k*tb[j] for j in (0,1)],q]})
    return commands


def annular_band(center,radius,thickness,start,end):
    if not 0<thickness<2*radius:raise ValueError('Signal band needs distinct positive inner/outer radii')
    outer=arc(center,[radius+thickness/2]*2,start,end)
    inner=arc(center,[radius-thickness/2]*2,end,start)
    return outer+[{'op':'lnTo','points':inner[0]['points']}]+inner[1:]+[{'op':'close','points':[]}]


def smooth_outline(points,closed=False,corners=()):
    points=[list(p) for p in points]
    if not points:raise ValueError('Observed outline is empty')
    if closed and points[0]==points[-1]:points.pop()
    count=len(points);corners=set(corners)
    if count<3 or any(type(i) is not int or not 0<=i<count for i in corners):raise ValueError('Observed smooth outline and valid natural corners required')
    if any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in points):raise ValueError('Nonfinite source outline')
    tangents=[]
    for i,p in enumerate(points):
        before=points[(i-1)%count] if closed or i else p
        after=points[(i+1)%count] if closed or i<count-1 else p
        left=math.dist(before,p);right=math.dist(p,after)
        if i in corners:vector=[0,0]
        elif not closed and i==0:vector=[after[j]-p[j] for j in (0,1)]
        elif not closed and i==count-1:vector=[p[j]-before[j] for j in (0,1)]
        else:
            span=max(math.dist(before,after),1e-12)
            length=min(left,right)
            vector=[(after[j]-before[j])*length/span for j in (0,1)]
        tangents.append(vector)
    commands=[{'op':'moveTo','points':[points[0]]}]
    for i in range(count if closed else count-1):
        n=(i+1)%count;p,q=points[i],points[n];length=math.dist(p,q)
        if length<1e-9:continue
        if i in corners and n in corners:
            commands.append({'op':'lnTo','points':[q]});continue
        # A declared corner uses the local segment direction on each side.
        ta=[q[j]-p[j] for j in (0,1)] if i in corners else tangents[i]
        tb=[q[j]-p[j] for j in (0,1)] if n in corners else tangents[n]
        commands.append({'op':'cubicBezTo','points':[[p[j]+ta[j]/3 for j in (0,1)],
                         [q[j]-tb[j]/3 for j in (0,1)],q]})
    if closed:commands.append({'op':'close','points':[]})
    return commands


def contour_node(cid,commands,parent,stroke,fill,width,semantic,closed=False):
    from .recipes import node
    points=[p for c in commands for p in c.get('points',[])]
    xs,ys=zip(*points);x,y=min(xs),min(ys);w,h=max(max(xs)-x,.001),max(max(ys)-y,.001)
    normalized=[{'op':c['op'],'points':[[(px-x)/w,(py-y)/h] for px,py in c.get('points',[])]} for c in commands]
    return node(cid,'path',[x,y,w,h],{'contours':[{'commands':normalized,'closed':closed}],
                'curve_compilation':{'version':VERSION,'method':'continuous_native_bezier','scientific_data_changed':False}},
                parent,semantic,stroke=stroke,fill=fill,line_width=width,line_cap='round',line_join='round')


def _circle_fit(points,tolerance):
    import numpy as np
    data=np.asarray(points,dtype=float)
    origin=data.mean(axis=0);centered=data-origin
    design=np.column_stack((2*centered[:,0],2*centered[:,1],np.ones(len(points))))
    values=np.sum(centered**2,axis=1)
    fit,residuals,rank,singular=np.linalg.lstsq(design,values,rcond=None)
    if rank!=3 or singular[-1]<=1e-8*singular[0]:raise ValueError('Arc source is insufficient to identify a stable circle')
    center=fit[:2]+origin;radius=math.sqrt(max(0,fit[2]+sum(fit[:2]**2)))
    if radius<=0:raise ValueError('Invalid observed arc radius')
    deviation=float(np.max(np.abs(np.linalg.norm(data-center,axis=1)-radius)))
    if deviation>tolerance:raise ValueError('Source is not a supported circular arc; declare its elliptical/smooth model instead of flattening it')
    angles=np.unwrap(np.arctan2(data[:,1]-center[1],data[:,0]-center[0]))
    differences=np.diff(angles)
    if not (np.all(differences>=-1e-6) or np.all(differences<=1e-6)) or abs(angles[-1]-angles[0])<math.radians(10):
        raise ValueError('Observed arc ordering/span is ambiguous')
    return arc(center.tolist(),[radius,radius],math.degrees(angles[0]),math.degrees(angles[-1])),deviation


def compile_scene(scene,allowed=None):
    scene=copy.deepcopy(scene);objects={o['id']:o for o in scene['objects']}
    records=[r for r in scene.get('curve_plan',{}).get('compiled',[]) if r['owner'] in objects
             and objects[r['owner']]['content'].get('curve_compilation',{}).get('version')==VERSION]
    for obj in scene['objects']:
        if obj['render_type']!='path':continue
        if allowed is not None:
            editable=any(f in ('geometry','content','content.contours','replace_component','add') for f in allowed.get(obj['id'],[]))
            ancestor=obj.get('parent')
            while ancestor and not editable:
                editable=any(f in ('replace_component','add') for f in allowed.get(ancestor,[]))
                ancestor=objects[ancestor].get('parent')
            if not editable:continue  # Observation/read dependency is not a write grant.
        content=obj['content'];semantic=obj['semantic_type'];model=content.get('curve_model')
        if content.get('function_spec'):
            if content.get('curve_compilation',{}).get('version')!='functional-curves-1':
                raise ValueError('Compile source-bound function_spec through the normal v1.33 contract before building')
            continue
        if semantic in SCIENTIFIC:
            if model:raise ValueError('Use source-bound function_spec, not an illustration curve model, for scientific curves')
            continue  # Retained legacy tasks are not silently redrawn.
        contours=content.get('contours',[])
        if not model and semantic not in ARC_TYPES|SMOOTH_OUTLINES:continue
        if content.get('curve_compilation',{}).get('version')==VERSION:continue
        bbox=obj['bbox'];x,y,w,h=bbox;converted=[]
        for contour in contours:
            if 'commands' in contour:
                converted.append(contour);continue
            points=[[x+u*w,y+v*h] for u,v in contour['points']]
            if len(points)<3:raise ValueError('Smooth semantic curve needs sufficient observed support')
            if model and model.get('kind')=='ellipse_arc':
                if not model.get('source_evidence'):raise ValueError('An elliptical source model needs observed geometry evidence')
                center=[x+model['center'][0]*w,y+model['center'][1]*h]
                radii=[model['radii'][0]*w,model['radii'][1]*h]
                commands=arc(center,radii,model['start_degrees'],model['end_degrees'],model.get('rotation',0));deviation=None
            elif semantic in ARC_TYPES:
                commands,deviation=_circle_fit(points,(model or {}).get('max_deviation_source_px',.6))
            else:
                if semantic not in SMOOTH_OUTLINES and not (model and model.get('kind')=='smooth_outline' and model.get('source_evidence')):
                    raise ValueError('Do not smooth a polygon without source-supported rounded semantics')
                corners=(model or {}).get('corner_indices',[])
                if semantic not in SMOOTH_OUTLINES and 'corner_indices' not in model:
                    raise ValueError('Declare actual corners, including an explicit empty list for a fully rounded outline')
                commands=smooth_outline(points,contour.get('closed',False),corners);deviation=None
            normalized=[{'op':c['op'],'points':[[(px-x)/w,(py-y)/h] for px,py in c.get('points',[])]} for c in commands]
            converted.append({'commands':normalized,'closed':contour.get('closed',False)})
            records.append({'owner':obj['id'],'semantic_type':semantic,'fit_max_deviation_source_px':deviation,
                            'basis':'Source bounded illustration geometry; not an actual-render quality score'})
        if converted:
            content['contours']=converted
            content['curve_compilation']={'version':VERSION,'method':'bounded_semantic_bezier','scientific_data_changed':False}
    scene['curve_plan']={'version':VERSION,'compiled':records,'scope':'Geometry construction only; actual appearance remains source-part loop work'}
    return scene


def tangent_diagnostics(contour):
    """Independent geometric join diagnostic, never a saved-image quality PASS."""
    previous=None;jumps=[]
    for command in contour.get('commands',[]):
        points=command.get('points',[])
        if command['op']=='moveTo':position=points[0];previous=None;continue
        if command['op']!='cubicBezTo':
            if points:position=points[-1]
            previous=None;continue
        first=[points[0][j]-position[j] for j in (0,1)]
        last=[points[2][j]-points[1][j] for j in (0,1)]
        if previous and math.hypot(*previous)>1e-10 and math.hypot(*first)>1e-10:
            ratio=sum(previous[j]*first[j] for j in (0,1))/(math.hypot(*previous)*math.hypot(*first))
            jumps.append(math.degrees(math.acos(max(-1,min(1,ratio)))))
        previous=last;position=points[2]
    return {'join_tangent_max_degrees':max(jumps,default=0),'join_count':len(jumps),'evidence':'constructed_control_points_only'}
