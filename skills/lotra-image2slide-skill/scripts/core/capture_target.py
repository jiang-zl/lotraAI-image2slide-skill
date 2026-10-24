"""Explicit reconstruction target; preserve raw capture and immutable mapping."""
import copy,math,shutil
from pathlib import Path
import numpy as np
from PIL import Image
from .common import digest,identity,read_json,write_json,safe_path

POLICY='capture-target-1.37.5'


def homography(source,target):
    rows=[];values=[]
    for (x,y),(u,v) in zip(source,target):
        rows.extend(([x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]));values.extend((u,v))
    matrix=np.r_[np.linalg.solve(np.asarray(rows,float),np.asarray(values,float)),1].reshape(3,3)
    if not np.isfinite(matrix).all() or abs(np.linalg.det(matrix))<1e-12:raise ValueError('CAPTURE_MAPPING_REQUIRED: singular target plane')
    return matrix


def transform(points,matrix):
    p=np.column_stack((np.asarray(points,float),np.ones(len(points))))@np.asarray(matrix).T
    if np.any(abs(p[:,2])<1e-10):raise ValueError('CAPTURE_MAPPING_REQUIRED: projective horizon intersects the target')
    return p[:,:2]/p[:,2,None]


def validate(plan,size,raw_hash,project=None):
    if plan is None:return {'schema':POLICY,'kind':'source_projection','raw_source_hash':raw_hash,
                           'source_evidence':'Default: preserve the complete unchanged original projection'}
    plan=copy.deepcopy(plan)
    if (plan.get('schema')!=POLICY or plan.get('raw_source_hash')!=raw_hash or
        plan.get('kind') not in ('source_projection','slide_surface','semantic_region') or not plan.get('source_evidence')):
        raise ValueError('CAPTURE_TARGET_REQUIRED: explicit raw-bound target and evidence')
    if plan['kind']=='source_projection':
        if set(plan)-{'schema','kind','raw_source_hash','source_evidence'}:
            raise ValueError('Full source projection cannot silently crop, deskew or align')
        return plan
    if plan['kind']=='semantic_region':
        if set(plan)-{'schema','kind','raw_source_hash','source_evidence','observer','contour','content_scope','excluded_scope'}:
            raise ValueError('Unknown semantic target field; a content crop does not authorize deskew/redesign')
        if (plan.get('observer') not in ('human','host_model') or not plan.get('content_scope') or
                not plan.get('excluded_scope')):
            raise ValueError('SEMANTIC_TARGET_OBSERVATION_REQUIRED: original content and excluded capture environment')
        points=np.asarray(plan.get('contour'),float)
        if (points.ndim!=2 or points.shape[1]!=2 or not 4<=len(points)<=64 or not np.isfinite(points).all() or
                (points<0).any() or (points>np.asarray(size)).any()):
            raise ValueError('SEMANTIC_TARGET_CONTOUR_REQUIRED: four to 64 original image points')
        area=abs(float(np.sum(points[:,0]*np.roll(points[:,1],-1)-points[:,1]*np.roll(points[:,0],-1))))/2
        if area<16:
            raise ValueError('SEMANTIC_TARGET_CONTOUR_REQUIRED: nondegenerate observed content area')
        left,top=np.floor(points.min(axis=0)).astype(int);right,bottom=np.ceil(points.max(axis=0)).astype(int)
        if right-left<16 or bottom-top<16 or (right-left)*(bottom-top)>32000000:
            raise ValueError('SEMANTIC_TARGET_CONTOUR_REQUIRED: bounded nonempty content envelope')
        # The contour is a semantic observation. Crop only its bounding envelope;
        # no inferred original aspect ratio, polygon painting or projective warp.
        return plan
    if set(plan)-{'schema','kind','raw_source_hash','source_evidence','observer','corners','output_size','aspect_ratio_basis','source_uncertainty_px','authorization'}:
        raise ValueError('Unknown capture target field; redesign/alignment needs a separate user request')
    if plan.get('observer') not in ('human','host_model') or plan.get('aspect_ratio_basis') not in ('original_metadata','user_authority'):
        raise ValueError('CAPTURE_ASPECT_AUTHORITY_REQUIRED: a photographed quadrilateral alone does not identify the original slide ratio')
    points=np.asarray(plan.get('corners'),float)
    if points.shape!=(4,2) or not np.isfinite(points).all() or (points<0).any() or (points>np.asarray(size)).any():
        raise ValueError('CAPTURE_CORNERS_REQUIRED: four in-bounds TL,TR,BR,BL raw-source corners')
    edges=np.roll(points,-1,axis=0)-points
    following=np.roll(edges,-1,axis=0)
    crosses=edges[:,0]*following[:,1]-edges[:,1]*following[:,0]
    if (crosses<=1e-6).any():raise ValueError('CAPTURE_CORNERS_REQUIRED: distinct convex clockwise image-plane order')
    output=plan.get('output_size',[])
    if len(output)!=2 or any(type(v) is not int or not 16<=v<=8192 for v in output) or output[0]*output[1]>32000000:
        raise ValueError('Bounded explicit target output_size required')
    lengths=np.linalg.norm(edges,axis=1)
    if output[0]>max(lengths[0],lengths[2])+1 or output[1]>max(lengths[1],lengths[3])+1:
        raise ValueError('CAPTURE_INFORMATION_BOUND: output resolution cannot manufacture extra source information')
    uncertainty=plan.get('source_uncertainty_px')
    if type(uncertainty) not in (float,int) or not .5<=uncertainty<=8:
        raise ValueError('Explicit bounded raw corner/raster uncertainty required')
    authority=plan.get('authorization',{})
    if not authority.get('path') or not authority.get('sha256'):raise ValueError('CAPTURE_AUTHORIZATION_REQUIRED: exact user/metadata target authority')
    if project is not None:
        file=safe_path(project,authority['path'])
        if digest(file)!=authority['sha256']:raise ValueError('Capture target authority changed')
    return plan


def matrices(plan,size):
    if plan['kind']=='source_projection':return np.eye(3),np.eye(3),list(size),0.
    if plan['kind']=='semantic_region':
        points=np.asarray(plan['contour'],float)
        left,top=np.floor(points.min(axis=0));right,bottom=np.ceil(points.max(axis=0))
        forward=np.array([[1.,0.,-left],[0.,1.,-top],[0.,0.,1.]])
        return forward,np.linalg.inv(forward),[int(right-left),int(bottom-top)],0.
    w,h=plan['output_size'];corners=plan['corners']
    target=[[0,0],[w,0],[w,h],[0,h]];forward=homography(corners,target);inverse=np.linalg.inv(forward)
    # Propagate observable raw uncertainty; it is never a quality-bound waiver.
    q=np.array([[w*x/8,h*y/8] for y in range(9) for x in range(9)])
    raw=transform(q,inverse);epsilon=.01;gains=[]
    for point in raw:
        origin=transform([point],forward)[0]
        jac=np.column_stack(((transform([point+[epsilon,0]],forward)[0]-origin)/epsilon,
                             (transform([point+[0,epsilon]],forward)[0]-origin)/epsilon))
        gains.append(float(np.linalg.svd(jac,compute_uv=False)[0]))
    roundtrip=float(np.linalg.norm(transform(transform(q,inverse),forward)-q,axis=1).max())
    if roundtrip>1e-6:raise ValueError('CAPTURE_MAPPING_REQUIRED: finite inverse roundtrip failed')
    return forward,inverse,[w,h],max(gains)*plan['source_uncertainty_px']


def freeze(task,raw,plan):
    task=Path(task);raw=Path(raw)
    with Image.open(raw) as image:
        forward,inverse,size,uncertainty=matrices(plan,image.size)
        if plan['kind']=='semantic_region':
            derived=task/'source/target-semantic-region.png'
            left,top=round(inverse[0,2]),round(inverse[1,2])
            image.crop((left,top,left+size[0],top+size[1])).save(derived)
        elif plan['kind']=='slide_surface':
            derived=task/'source/target-slide-surface.png'
            coefficients=(inverse/inverse[2,2]).ravel()[:8]
            image.convert('RGB').transform(tuple(size),Image.Transform.PERSPECTIVE,coefficients,
                Image.Resampling.BICUBIC).save(derived)
        else:derived=raw
    frozen=copy.deepcopy(plan)
    if plan['kind']=='slide_surface':
        authority=Path(plan['authorization']['path'])
        # Caller replaces external authority by an already copied task-local ref.
        if not authority.is_absolute():authority=safe_path(task,authority)
        if digest(authority)!=plan['authorization']['sha256']:raise ValueError('Frozen target authority changed')
    ref=lambda p:{'path':p.relative_to(task).as_posix(),'sha256':digest(p)}
    record={'schema':POLICY,'plan':frozen,'raw_source':ref(raw),'target_source':ref(derived),
        'raw_to_target':forward.tolist(),'target_to_raw':inverse.tolist(),'output_size':size,
        'propagated_source_uncertainty_px':uncertainty,'interpolation':'bicubic' if plan['kind']=='slide_surface' else 'none',
        'alignment_or_redesign':False,'migration':'new task only; old tasks are not silently rebound'}
    file=task/'source'/('Reconstruction-target-'+identity(record)+'.json');write_json(file,record)
    return ref(derived),size,ref(file)


def verify(task,state):
    ref=state.get('reconstruction_target')
    if not ref:return {'passed':True,'applicable':False,'legacy_policy_retained':True}
    file=safe_path(task,ref['path'])
    if digest(file)!=ref['sha256']:raise ValueError('Frozen reconstruction target changed')
    record=read_json(file);raw=safe_path(task,record['raw_source']['path']);target=safe_path(task,record['target_source']['path'])
    if digest(raw)!=record['raw_source']['sha256'] or digest(target)!=record['target_source']['sha256']:
        raise ValueError('Raw or mapped source bytes changed')
    if state['source']!=record['target_source'] or list(state['source_size'])!=record['output_size']:
        raise ValueError('Task source domain escaped its explicit reconstruction target')
    with Image.open(raw) as image:
        plan=validate(record['plan'],image.size,digest(raw),task)
        forward,inverse,size,uncertainty=matrices(plan,image.size)
        if size!=record['output_size']:raise ValueError('Capture output canvas differs from the frozen plan')
        if plan['kind']=='semantic_region':
            left,top=round(inverse[0,2]),round(inverse[1,2])
            recomputed=image.crop((left,top,left+size[0],top+size[1])).convert('RGB')
            with Image.open(target) as saved:
                if saved.size!=tuple(size) or recomputed.tobytes()!=saved.convert('RGB').tobytes():
                    raise ValueError('Semantic content crop differs from the frozen original envelope')
        elif plan['kind']=='slide_surface':
            coefficients=(inverse/inverse[2,2]).ravel()[:8]
            recomputed=image.convert('RGB').transform(tuple(size),Image.Transform.PERSPECTIVE,coefficients,Image.Resampling.BICUBIC)
            with Image.open(target) as saved:
                if saved.size!=tuple(size) or recomputed.tobytes()!=saved.convert('RGB').tobytes():raise ValueError('Derived source is not the frozen raw-to-target mapping')
    if not np.allclose(forward,record['raw_to_target'],atol=1e-10,rtol=0) or not np.allclose(inverse,record['target_to_raw'],atol=1e-10,rtol=0):
        raise ValueError('Capture mapping matrices changed')
    if abs(uncertainty-record['propagated_source_uncertainty_px'])>1e-8:raise ValueError('Capture uncertainty changed')
    return {'passed':True,'target':plan['kind'],'mapping':ref,'raw_source':record['raw_source'],
            'target_source':record['target_source'],'independently_recomputed':True,'artwork_acceptance':False}
