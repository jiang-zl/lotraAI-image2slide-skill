"""Bounded native glyph fill extraction, not a general EMF playback engine.

Paper proposals retain native word geometry. Native presentation text outline
is supplied separately; EMF cosmetic pens are recorded, not guessed. Pattern
brushes, source bitmap transfers and other drawing records are unsupported.
"""
import struct,math,copy
from pathlib import Path

def mul(x,y):
    a,b,c,d,e,f=x;g,h,i,j,k,l=y
    return (a*g+c*h,b*g+d*h,a*i+c*j,b*i+d*j,a*k+c*l+e,b*k+d*l+f)

def extract(file,native_text_style=None):
    data=Path(file).read_bytes();offset=0;records=[]
    while offset<len(data):
        kind,size=struct.unpack_from('<II',data,offset)
        if size<8 or size%4 or offset+size>len(data):raise ValueError('Malformed native glyph record')
        records.append((kind,data[offset:offset+size]));offset+=size
    header=records[0][1]
    if records[0][0]!=1 or len(header)<88:raise ValueError('Saved EMF device scale is required')
    dx,dy=struct.unpack_from('<2i',header,72);mx,my=struct.unpack_from('<2i',header,80)
    sx=mx/dx*72/25.4;sy=my/dy*72/25.4
    if abs(sx-sy)>max(sx,sy)*.001:raise ValueError('Native anisotropic map needs explicit handling')
    state={'world':(1,0,0,1,0,0),'brush':{'rgb':'000000','style':0},'pen':None,'fillrule':'evenodd'};stack=[];handles={};path=[];points=[];fills=[];strokes=[];pen_records=[];cosmetic=[];pattern_paths=[]
    partial=bool(native_text_style and 0<native_text_style.get('text_outline_alpha',1)<1 and native_text_style.get('text_outline_width_pt',0)>0)
    def point(x,y):
        a,b,c,d,e,f=state['world'];p=((a*x+c*y+e)*sx,(b*x+d*y+f)*sy);points.append(p);return p
    def command(op,coords):path.append(op+' '.join(format(v,'.7f') for v in coords))
    for kind,r in records:
        if kind in (1,14,70,98):continue
        if kind==33:stack.append(copy.deepcopy(state))
        elif kind==34:
            saved=struct.unpack_from('<i',r,8)[0]
            if saved!=-1 or not stack:raise ValueError('Unsupported native DC restore')
            state=stack.pop()
        elif kind==36:
            m=struct.unpack_from('<6f',r,8);mode=struct.unpack_from('<I',r,32)[0]
            if mode==1:state['world']=(1,0,0,1,0,0)
            elif mode==2:state['world']=mul(state['world'],m)
            elif mode==3:state['world']=mul(m,state['world'])
            else:raise ValueError('Unknown saved native transform mode')
        elif kind==39:
            index,style,colour,hatch=struct.unpack_from('<4I',r,8)
            if style not in (0,1):raise ValueError('Non-solid glyph brush remains unsupported')
            handles[index]={'kind':'brush','rgb':'%02x%02x%02x'%(colour&255,(colour>>8)&255,(colour>>16)&255),'style':style}
        elif kind==95:
            index=struct.unpack_from('<I',r,8)[0];style,width,brushstyle,colour,hatch,count=struct.unpack_from('<6I',r,28)
            if struct.unpack_from('<I',r,16)[0] or struct.unpack_from('<I',r,24)[0]:raise ValueError('Bitmap glyph pen remains unsupported')
            pen={'kind':'pen','raw_style':style,'width':width,'brushstyle':brushstyle,'colour':colour,'style_entries':count};handles[index]=pen;pen_records.append(pen)
        elif kind==94 and partial:
            index,usage,offset_bmi,size_bmi,offset_bits,size_bits=struct.unpack_from('<6I',r,8)
            if min(offset_bmi,offset_bits)<32 or offset_bmi+size_bmi>len(r) or offset_bits+size_bits>len(r):raise ValueError('Malformed native cosmetic DIB brush')
            handles[index]={'kind':'brush','style':'pattern','rgb':None};cosmetic.append({'record':94,'usage':usage,'bitmap_info_bytes':size_bmi,'pattern_bytes':size_bits,'interpretation':'Native partial text-outline cosmetic composition delegated to authoritative actual text style; pattern is neither executed nor rasterized.'})
        elif kind==37:
            index=struct.unpack_from('<I',r,8)[0]
            if index&0x80000000:
                stock=index&0x7fffffff
                if stock in (0,4,5):selected={'kind':'brush','style':int(stock==5),'rgb':'ffffff' if stock==0 else '000000'}
                elif stock in (6,7,8):selected={'kind':'pen','stock':stock}
                else:raise ValueError('Unsupported native stock object')
            else:
                if index not in handles:raise ValueError('Unbound native object')
                selected=handles[index]
            state[selected['kind']]=selected
        elif kind==40:handles.pop(struct.unpack_from('<I',r,8)[0],None)
        elif kind==19:
            rule=struct.unpack_from('<I',r,8)[0]
            if rule not in (1,2):raise ValueError('Unknown native fill rule')
            state['fillrule']='evenodd' if rule==1 else 'nonzero'
        elif kind==59:path=[];points=[]
        elif kind==60:pass
        elif kind==61:path.append('Z')
        elif kind in (27,54):command('M' if kind==27 else 'L',point(*struct.unpack_from('<2i',r,8)))
        elif kind in (88,89):
            count=struct.unpack_from('<I',r,24)[0]
            if 28+4*count>len(r) or kind==88 and count%3:raise ValueError('Malformed saved native glyph curve')
            pts=[point(*struct.unpack_from('<2h',r,28+i*4)) for i in range(count)]
            if kind==88:
                for i in range(0,count,3):command('C',sum(pts[i:i+3],()))
            else:
                for p in pts:command('L',p)
        elif kind in (62,64):
            if not path or not points:raise ValueError('Empty native glyph path')
            entry={'d':' '.join(path),'fill':state['brush']['rgb'],'fill_rule':state['fillrule'],'bounds_points':[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]}
            if kind==62:
                if state['brush']['style']=='pattern' and partial:
                    entry['fill']=native_text_style['color'].lower();entry['fill_opacity']=native_text_style['text_outline_alpha'];entry['delegation']='Actual native partial text-outline contour with authoritative opacity instead of DIB stipple; not lossless replay';pattern_paths.append(entry)
                elif state['brush']['style'] not in (0,1):raise ValueError('Pattern-filled glyph is outside the source-bound native text-alpha route')
                if state['brush']['style']==0:
                    if partial:entry['fill']=native_text_style['color'].lower()
                    fills.append(entry)
            else:strokes.append(dict(entry,pen=copy.deepcopy(state['pen'])))
        elif kind==76:
            rop=struct.unpack_from('<I',r,40)[0]
            if struct.unpack_from('<I',r,88)[0] or struct.unpack_from('<I',r,96)[0]:raise ValueError('Real glyph raster transfer remains unsupported')
            if rop==0x5A0049 and partial:cosmetic.append({'record':76,'rop':rop,'interpretation':'Discarded native partial-outline cosmetic XOR composition; only owned solid glyph fills plus authoritative vector alpha outline are proposed.'})
            elif rop!=0xAA0029:raise ValueError('Real glyph ROP needs a different explicit route')
        elif kind in (20,24) and partial:cosmetic.append({'record':kind,'payload':r[8:].hex(),'interpretation':'Native cosmetic XOR background/composition state, not a glyph geometry field'})
        else:raise ValueError('Unsupported native glyph drawing record '+str(kind))
    if stack or not fills:raise ValueError('Incomplete native glyph fill geometry')
    return {'fill_paths':fills,'native_cosmetic_pattern_paths':pattern_paths,'native_cosmetic_stroke_paths':strokes,'native_pen_records':pen_records,'delegated_native_cosmetic_records':cosmetic,'points_per_device_pixel':[sx,sy],'scope':'Saved native solid glyph fills and explicitly source-bound partial text-outline contours only; preserve native global coordinates. DIB stipple opacity is delegated to authoritative text style, not lossless EMF replay. Unknown bitmap-filled semantics and any source raster transfer remain unsupported; actual own-word evaluation is required.'}
