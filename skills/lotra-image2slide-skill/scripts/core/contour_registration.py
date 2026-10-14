"""Register a generated background's native contours to observed source landmarks.

The reference pixels remain immutable. This transforms vector vertices, not text,
scientific data, or a bitmap delivered in place of editable geometry.
"""
import numpy as np
from .recipes import clip_convex_polygon


def prepare(component,spec):
    registration=spec.get('registration')
    if not registration:return None
    if component.get('paint_role')!='background' or not spec.get('reconstructed') or spec.get('contour_method') not in ('cell_runs','marching'):
        raise ValueError('Landmark registration is limited to disclosed generated background contours')
    landmarks=registration.get('landmarks',[])
    if len(landmarks) not in (3,4):raise ValueError('Three affine or four projective source landmarks required')
    x,y,w,h=component['roi'];rows=[];rhs=[]
    for item in landmarks:
        if not item.get('label'):raise ValueError('Each landmark needs its observed geometric meaning')
        u,v=item['asset'];sx,sy=item['source'];dx,dy=(sx-x)/w,(sy-y)/h
        if not all(np.isfinite([u,v,dx,dy])) or not 0<=u<=1 or not 0<=v<=1 or not 0<=dx<=1 or not 0<=dy<=1:
            raise ValueError('Landmarks use normalized asset coordinates and source pixels inside their owner')
        if len(landmarks)==3:
            rows.extend([[u,v,1,0,0,0],[0,0,0,u,v,1]]);rhs.extend([dx,dy])
        else:
            rows.extend([[u,v,1,0,0,0,-dx*u,-dx*v],[0,0,0,u,v,1,-dy*u,-dy*v]]);rhs.extend([dx,dy])
    try:values=np.linalg.solve(np.asarray(rows),np.asarray(rhs))
    except np.linalg.LinAlgError as exc:raise ValueError('Source landmark arrangement is degenerate') from exc
    matrix=np.array([[*values[:3]],[*values[3:6]],[*(values[6:8] if len(landmarks)==4 else [0,0]),1]])
    denom=np.array([[0,0,1],[1,0,1],[1,1,1],[0,1,1]])@matrix[2]
    if np.min(denom)<=1e-6:raise ValueError('The reference background crosses a projective horizon')
    return matrix


def transform(contours,matrix):
    if matrix is None:return contours
    sizes=[len(c['points']) for c in contours]
    if not sizes:return []
    xy=np.asarray([p for c in contours for p in c['points']]);hom=np.column_stack((xy,np.ones(len(xy))))@matrix.T
    mapped=hom[:,:2]/hom[:,2,None];out=[];offset=0;boundary=[[0,0],[1,0],[1,1],[0,1]]
    for contour,count in zip(contours,sizes):
        points=mapped[offset:offset+count];offset+=count
        if np.any(points<0) or np.any(points>1):points=np.asarray(clip_convex_polygon(points.tolist(),boundary))
        if len(points)>=3:out.append({'closed':True,'points':points.tolist()})
    return out
