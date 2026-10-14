"""Source-grid OCR tiling and inverse right-angle coordinates; stdlib only."""
import math
from .source_contract import finite

def inverse_points(points,angle,width,height,scale,offset):
    finite([points,angle,width,height,scale,offset],'OCR.transform')
    sx,sy=scale if isinstance(scale,(list,tuple)) and len(scale)==2 else (scale,scale)
    if angle not in (0,90,180,270) or min(sx,sy)<=0:raise ValueError('Invalid OCR transform')
    result=[]
    for u,v in points:
        x,y=(u,v) if angle==0 else (width-v,u) if angle==90 else (width-u,height-v) if angle==180 else (v,height-u)
        result.append([x/sx+offset[0],y/sy+offset[1]])
    return result

def plan_inputs(inputs,size,route):
    finite([inputs,size,route],'OCR.inputs')
    result=[];ids=set()
    max_pixels=route.get('max_pixels',8000000);max_side=route.get('max_side_len',4096)
    for item in inputs:
        name=item.get('id')
        if not isinstance(name,str) or not name or name in ids:raise ValueError('Unique OCR input IDs required')
        ids.add(name)
        roi=item.get('roi',[0,0,*size]);x,y,w,h=roi;scale=item.get('scale',1.)
        if min(x,y)<0 or min(w,h)<=0 or x+w>size[0] or y+h>size[1] or not 1<=scale<=8:
            raise ValueError('Invalid bounded source-only OCR crop')
        side=max(1,int(min(math.sqrt(max_pixels),max_side)/scale))
        def positions(length):
            if length<=side:return [0]
            stride=max(1,side-max(32,side//4))
            values=list(range(0,math.ceil(length-side),stride));values.append(length-side)
            return values
        xs,ys=positions(w),positions(h)
        for row,dy in enumerate(ys):
            for col,dx in enumerate(xs):
                tile=[x+dx,y+dy,min(w,side),min(h,side)]
                result.append({**item,'id':name if len(xs)*len(ys)==1 else name+'__tile_'+str(row)+'_'+str(col),
                    'roi':tile,'source_item':name,'source_item_roi':roi})
    if len(result)>256:raise ValueError('OCR request exceeds 256 bounded tiles; use source-only host views')
    return result
