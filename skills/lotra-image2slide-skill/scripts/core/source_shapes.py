"""A measured single native contour for a source-defined continuous silhouette.

Not an image vectorizer or segmentation oracle: the host must first identify
one natural continuous shape and freeze its semantic mask on the source canvas.
"""
from pathlib import Path
import numpy as np
from PIL import Image
from skimage.measure import find_contours,approximate_polygon
from .common import digest,safe_path
from .recipes import node


def construct(task,state,component,spec):
    if component.get('outline_role')!='continuous_complex_contour' or not component.get('source_note'):
        raise ValueError('Choose a suitable native preset first; measured outline needs a natural continuous owner')
    path=safe_path(task,spec['mask']['path'])
    if digest(path)!=spec['mask']['sha256']:raise ValueError('Measured semantic mask changed')
    x,y,w,h=map(int,component['roi']);epsilon=spec.get('epsilon',.35)
    if not 0<=epsilon<=.8:raise ValueError('Keep the measured source contour within subpixel simplification')
    with Image.open(path) as image:
        if image.mode!='L' or image.size!=tuple(state['source_size']):raise ValueError('Mask uses immutable source canvas')
        mask=np.asarray(image)[y:y+h,x:x+w]>0
    observed_spec=spec.get('observed_mask')
    if not observed_spec:raise ValueError('Measured outline needs a separate immutable visible-source mask')
    def frozen_mask(ref):
        file=safe_path(task,ref['path'])
        if digest(file)!=ref['sha256']:raise ValueError('Source contour evidence changed')
        with Image.open(file) as image:
            if image.mode!='L' or image.size!=tuple(state['source_size']):raise ValueError('Contour evidence uses the source canvas')
            return np.asarray(image)[y:y+h,x:x+w]>0
    observed=frozen_mask(observed_spec)
    if np.any(observed & ~mask):raise ValueError('Do not discard visible source-contour pixels')
    additions=mask & ~observed
    if additions.any():
        occluder=spec.get('occlusion_mask')
        if not occluder or np.any(additions & ~frozen_mask(occluder)):
            raise ValueError('Contour completion must stay inside the explicitly observed occluder; preserve negative spaces')
    curves=[]
    for contour in find_contours(np.pad(mask,1),.5):
        if len(contour)<5:continue
        points=approximate_polygon(contour,epsilon)-1
        curves.append({'closed':True,'points':[[float(col)/w,float(row)/h] for row,col in points]})
    if not curves:raise ValueError('No observed continuous silhouette')
    cid=component['id'];root=node(cid,'group',component['roi'],semantic=component['semantic_class'])
    outline=node(cid+'__outline','path',component['roi'],{'contours':curves},cid,'measured_complete_contour',
                 fill=spec['fill'],stroke=spec.get('stroke'),line_width=spec.get('line_width',1))
    return [root,outline]
