"""Source-only surrounding background evidence, separate from owned material."""
import math
import numpy as np
from PIL import Image
from .common import safe_path,digest


def background(task,state,roi,margin=3):
    x,y,w,h=roi;image=Image.open(safe_path(task,state['source']['path'])).convert('RGB')
    left=max(0,math.floor(x)-margin);top=max(0,math.floor(y)-margin)
    right=min(image.width,math.ceil(x+w)+margin);bottom=min(image.height,math.ceil(y+h)+margin)
    rgb=np.asarray(image.crop((left,top,right,bottom)))
    yy,xx=np.indices(rgb.shape[:2]);ring=(xx+left<x)|(xx+left>=x+w)|(yy+top<y)|(yy+top>=y+h)
    samples=rgb[ring]
    if len(samples)<12:return {'status':'REQUIRES_EXPLICIT_SOURCE_BACKGROUND_OR_MASK','reason':'No source context outside the owned part'}
    bins=samples//16;keys,counts=np.unique(bins,axis=0,return_counts=True);index=int(counts.argmax());support=np.all(bins==keys[index],axis=1);dominance=float(support.mean())
    if dominance<.65:return {'status':'REQUIRES_EXPLICIT_SOURCE_BACKGROUND_OR_MASK','reason':'Mixed surrounding materials/other content','dominance':dominance}
    return {'status':'SOURCE_CONTEXT_BACKGROUND','background_rgb':np.median(samples[support],axis=0).astype(int).tolist(),
        'evidence':{'source_hash':state['source']['sha256'],'roi':[left,top,right-left,bottom-top],
            'sampling':'outside owned source ROI, dominant 16-level RGB cell','dominance':dominance},
        'limits':'Not a body colour and not an inferred occlusion mask; source ownership review still applies'}
