"""A native path from an explicitly located, colour-isolated source curve."""
import numpy as np
from PIL import Image
from .recipes import path


def observed_curve(source,roi,color,cid,parent=None,*,tolerance=90,line_width=.75,chroma_similarity=.985,
                   semantic='observed_curve',curve_model=None,task=None,function_spec=None):
    x,y,w,h=map(int,roi)
    with Image.open(source) as image:rgb=np.array(image.convert('RGB').crop((x,y,x+w,y+h))).astype(float)
    target=np.array([int(color[i:i+2],16) for i in (0,2,4)])
    distance=np.linalg.norm(rgb-target,axis=2)
    saturation=rgb.max(axis=2)-rgb.min(axis=2)
    chroma=rgb-rgb.mean(axis=2,keepdims=True)
    target_chroma=target-target.mean()
    norm=np.linalg.norm(target_chroma)
    if norm<20:raise ValueError('A chromatic source curve must be isolated from neutral axes and labels')
    similarity=np.sum(chroma*target_chroma,axis=2)/(np.maximum(np.linalg.norm(chroma,axis=2),1)*norm)
    selected=(distance<tolerance)&(saturation>25)&(similarity>=chroma_similarity)
    points=[]
    for xx in range(w):
        yy=np.flatnonzero(selected[:,xx])
        if len(yy):points.append([x+xx+.5,y+float(np.median(yy))+.5])
    if len(points)<4:raise ValueError('Source curve is not isolated; author its observed geometry explicitly')
    result=path(cid,points,parent,color,width=line_width,semantic=semantic)
    if task is not None:
        from pathlib import Path
        from .common import identity,digest,write_json
        task=Path(task).resolve();spec=dict(function_spec or {})
        evidence={'source_hash':digest(source),'coordinate_space':'source_px','points':points,'roi':list(roi),
                  'selector':{'color':color,'tolerance':tolerance,'chroma_similarity':chroma_similarity}}
        file=task/'scratch'/('Curve-samples-'+identity(evidence)+'.json');write_json(file,evidence)
        spec.update(samples_ref={'path':file.relative_to(task).as_posix(),'sha256':digest(file)},source_hash=evidence['source_hash'])
        result['content']['function_spec']=spec
        return result
    if curve_model:
        if semantic in ('observed_curve','scientific_curve','chart_curve','data_series'):
            raise ValueError('Use task and function_spec for source-bound functional scientific curves')
        result['content']['curve_model']=curve_model
    return result
