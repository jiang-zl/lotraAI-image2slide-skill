"""Bounded, reversible artwork encodings. Never infer or drop source detail.

The rectangle codec preserves every closed subpath, including its winding and
stroke. The region codec is narrower: filled integer cells, no stroke/effects,
and identical independent raster probes. Native semantic part boundaries are
outside these encoders. PNG palettes map existing samples exactly, never quantize.
"""
import hashlib,io,re,struct,zlib
from lxml import etree as E
from .common import identity

VERSION='equivalent-artwork-1'
MAX_ASSET=32*1024*1024
MAX_CELLS=1024*1024
RECT=re.compile(r'([Mm])(-?\d+),(-?\d+)h(-?\d+)v(-?\d+)h(-?\d+)Z')
D_ATTR=re.compile(rb'\bd="([^"<>]*)"')
PATH_TAG=re.compile(rb'<(?:[A-Za-z_][\w.-]*:)?path\b[^<>]*>')

def sha(data):return hashlib.sha256(data).hexdigest()

def deflate(data,strategy=zlib.Z_DEFAULT_STRATEGY):
    c=zlib.compressobj(9,zlib.DEFLATED,-15,8,strategy)
    return c.compress(data)+c.flush()

def stored(data):return len(deflate(data))

def rectangles(d):
    """Independent absolute coordinate decoder, including SVG closepoint rules."""
    rows=[];cursor=(0,0);pos=0
    for m in RECT.finditer(d):
        if d[pos:m.start()].strip():return None
        op,x,y,w,h,end=m.groups();x,y,w,h,end=map(int,(x,y,w,h,end))
        if end!=-w:return None
        cursor=(x,y) if op=='M' else (cursor[0]+x,cursor[1]+y)
        rows.append((*cursor,w,h));pos=m.end()
    return rows if rows and not d[pos:].strip() else None

def relative_path(rows):
    out=[];last=None
    for x,y,w,h in rows:
        start=f'M{x},{y}' if last is None else f'm{x-last[0]},{y-last[1]}'
        out.append(start+f'h{w}v{h}h{-w}Z');last=(x,y)
    return ''.join(out)

def lexical_svg(data):
    if len(data)>MAX_ASSET:return data,{'status':'INAPPLICABLE','reason':'bounded_asset_size'}
    # Conservative static XML only; modifying a path cannot change JS/animation.
    tree=E.fromstring(data,E.XMLParser(resolve_entities=False,no_network=True))
    if (tree.getroottree().docinfo.doctype or b'<!--' in data or b'<![CDATA[' in data
            or any(E.QName(n).localname in ('script','animate','animateMotion','set') for n in tree.iter() if isinstance(n.tag,str))):
        return data,{'status':'INAPPLICABLE','reason':'non_static_svg'}
    count=[0,0]
    def sub(m):
        try:d=m[1].decode('ascii')
        except UnicodeError:return m[0]
        rows=rectangles(d)
        if rows is None:return m[0]
        result=relative_path(rows)
        if rectangles(result)!=rows:raise ValueError('Closed rectangle geometry changed')
        count[0]+=len(rows);count[1]+=1
        return b'd="'+result.encode('ascii')+b'"'
    out=PATH_TAG.sub(lambda m:D_ATTR.sub(sub,m[0]),data)
    return out,{'status':'EVALUATED','algorithm':'relative_closed_rectangles','rectangles':count[0],
        'paths':count[1],'geometry':'EXACT_COORDINATES_WINDING_CLOSE_AND_STROKE'}

def _mask(rows):
    import numpy as np
    x0=min(min(x,x+w) for x,y,w,h in rows);y0=min(min(y,y+h) for x,y,w,h in rows)
    x1=max(max(x,x+w) for x,y,w,h in rows);y1=max(max(y,y+h) for x,y,w,h in rows)
    if not (0<(x1-x0)*(y1-y0)<=MAX_CELLS):return None
    mask=np.zeros((y1-y0,x1-x0),dtype=bool)
    for x,y,w,h in rows:
        # SVG evenodd: overlap toggles, rather than assuming union semantics.
        mask[min(y,y+h)-y0:max(y,y+h)-y0,min(x,x+w)-x0:max(x,x+w)-x0]^=True
    return mask,(x0,y0)

def partition_rectangles(rows):
    """Exact row-run merge, evaluated in both axes; independent XOR mask proof."""
    import numpy as np
    packed=_mask(rows)
    if packed is None:return None
    mask,(x0,y0)=packed;candidates=[]
    for transpose in (False,True):
        grid=mask.T if transpose else mask;active={};out=[]
        for y,line in enumerate(grid):
            edges=np.diff(np.pad(line.astype(np.int8),(1,1)))
            intervals=list(zip(np.where(edges==1)[0].tolist(),np.where(edges==-1)[0].tolist()))
            current=set(intervals)
            for span in list(active):
                if span not in current:
                    start=active.pop(span);out.append((span[0],start,span[1]-span[0],y-start))
            for span in current:active.setdefault(span,y)
        for span,start in active.items():out.append((span[0],start,span[1]-span[0],len(grid)-start))
        result=[(x0+y,y0+x,h,w) if transpose else (x0+x,y0+y,w,h) for x,y,w,h in out]
        # Check in the original extent, including transparent margins and holes.
        check=np.zeros_like(mask)
        for x,y,w,h in result:check[y-y0:y+h-y0,x-x0:x+w-x0]^=True
        if not np.array_equal(mask,check):raise ValueError('Region coverage changed')
        candidates.append(result)
    return min(candidates,key=lambda rows:stored(relative_path(rows).encode('ascii')))

def _svg_pixels(data,width):
    from .svg_backend import svg2png
    from PIL import Image
    raw=svg2png(bytestring=data,output_width=width)
    with Image.open(io.BytesIO(raw)) as im:return im.size,im.convert('RGBA').tobytes()

def region_svg(data):
    """Candidates may merge colour patches, never separate semantic objects."""
    if len(data)>MAX_ASSET:return data,{'status':'INAPPLICABLE','reason':'bounded_asset_size'}
    parser=E.XMLParser(resolve_entities=False,no_network=True);tree=E.fromstring(data,parser)
    unsafe=('stroke','style','filter','mask','opacity','fill-opacity','stroke-opacity','transform')
    if (tree.getroottree().docinfo.doctype or b'<?xml-stylesheet' in data
            or any(any(k in n.attrib for k in unsafe) for n in tree.iter() if isinstance(n.tag,str))
            or any(E.QName(n).localname in ('style','script','animate','animateMotion','set','use','text','image') for n in tree.iter() if isinstance(n.tag,str))):
        return data,{'status':'INAPPLICABLE','reason':'stroke_effect_or_non_fill_artwork'}
    patches=0;old_count=new_count=0
    for n in tree.iter():
        if not isinstance(n.tag,str):continue
        if E.QName(n).localname!='path' or n.get('fill-rule')!='evenodd':continue
        rows=rectangles(n.get('d',''))
        if rows is None or len(rows)<8:continue
        result=partition_rectangles(rows)
        if result is not None and stored(relative_path(result).encode())<stored(relative_path(rows).encode()):
            n.set('d',relative_path(result));patches+=1;old_count+=len(rows);new_count+=len(result)
    if not patches:return data,{'status':'EVALUATED_NO_GAIN','algorithm':'exact_cell_repartition'}
    out=E.tostring(tree)
    if stored(out)>=stored(data):return data,{'status':'EVALUATED_NO_GAIN','algorithm':'exact_cell_repartition'}
    box=tree.get('viewBox','').split()
    try:width=max(1,min(1024,round(float(box[2])))) if len(box)==4 else 256
    except ValueError:width=256
    # Geometry-equivalent representations can affect AA at seams. Reject them.
    for scale in (1,2,4):
        if _svg_pixels(data,width*scale)!=_svg_pixels(out,width*scale):
            return data,{'status':'REJECTED','algorithm':'exact_cell_repartition','reason':'raster_probe_changed','scale':scale}
    return out,{'status':'EVALUATED','algorithm':'exact_cell_repartition','paths':patches,
        'before_rectangles':old_count,'after_rectangles':new_count,'cell_coverage':'EXACT_XOR',
        'independent_pixels':'EXACT_1_2_4','semantic_path_owners':'PRESERVED'}

def png_chunks(data):
    if data[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Invalid PNG signature')
    p=8;rows=[]
    while p<len(data):
        if p+12>len(data):raise ValueError('Truncated PNG chunk')
        n=struct.unpack('>I',data[p:p+4])[0];tag=data[p+4:p+8];end=p+12+n
        if end>len(data) or zlib.crc32(data[p+4:p+8+n])&0xffffffff!=struct.unpack('>I',data[p+8+n:end])[0]:
            raise ValueError('PNG chunk CRC or length failed')
        rows.append((tag,data[p+8:p+8+n]));p=end
    if not rows or rows[0][0]!=b'IHDR' or rows[-1]!=(b'IEND',b''):raise ValueError('Invalid PNG chunk ordering')
    return rows

def _png(rows):
    out=bytearray(b'\x89PNG\r\n\x1a\n')
    for tag,data in rows:out+=struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)
    return bytes(out)

def png_scanlines(data):
    chunks=png_chunks(data)
    if any(k in (b'acTL',b'fcTL',b'fdAT') for k,v in chunks):return data,{'status':'INAPPLICABLE','reason':'animated_png'}
    decoder=zlib.decompressobj();stream=decoder.decompress(b''.join(v for k,v in chunks if k==b'IDAT'),64*1024*1024+1)
    if len(stream)>64*1024*1024 or decoder.unconsumed_tail:return data,{'status':'INAPPLICABLE','reason':'bounded_inflated_scanlines'}
    if not decoder.eof:raise ValueError('Incomplete PNG compression stream')
    candidates=[]
    for strategy in (zlib.Z_DEFAULT_STRATEGY,zlib.Z_FILTERED,zlib.Z_RLE,zlib.Z_HUFFMAN_ONLY,zlib.Z_FIXED):
        c=zlib.compressobj(9,zlib.DEFLATED,15,8,strategy);blob=c.compress(stream)+c.flush()
        if zlib.decompress(blob)!=stream:raise ValueError('PNG scanlines changed')
        rows=[];written=False
        for k,v in chunks:
            if k==b'IDAT':
                if written:continue
                v=blob;written=True
            rows.append((k,v))
        candidates.append(_png(rows))
    out=min(candidates,key=stored)
    return out,{'status':'EVALUATED','algorithm':'png_same_scanline_deflate_search',
        'scanlines':'BYTE_IDENTICAL','non_IDAT_chunks':'BYTE_IDENTICAL'}

def png_palette(data):
    from PIL import Image
    chunks=png_chunks(data);header=struct.unpack('>IIBBBBB',chunks[0][1])
    if header[2:4]!=(8,2) or header[-1]!=0:return data,{'status':'INAPPLICABLE','reason':'requires_noninterlaced_8bit_RGB'}
    allowed={b'IHDR',b'IDAT',b'IEND',b'bKGD',b'cHRM',b'gAMA',b'sRGB',b'sBIT',b'pHYs',b'tEXt',b'zTXt',b'iTXt',b'iCCP',b'tIME'}
    if any(k not in allowed for k,v in chunks):return data,{'status':'INAPPLICABLE','reason':'unknown_or_transparency_chunk'}
    with Image.open(io.BytesIO(data)) as im:
        colours=im.getcolors(257)
        if colours is None:return data,{'status':'INAPPLICABLE','reason':'exact_palette_exceeds_256'}
        ordered=[c for _,c in sorted(colours,reverse=True)];background=None
        for tag,v in chunks:
            if tag==b'bKGD':
                background=struct.unpack('>HHH',v)
                if max(background)>255:return data,{'status':'INAPPLICABLE','reason':'unsupported_background'}
                if background not in ordered:ordered.append(background)
        if len(ordered)>256:return data,{'status':'INAPPLICABLE','reason':'palette_with_background_exceeds_256'}
        lookup={colour:i for i,colour in enumerate(ordered)}
        pixels=list(im.getdata())
        scan=b''.join(b'\0'+bytes(lookup[p] for p in pixels[y*im.width:(y+1)*im.width]) for y in range(im.height))
    width,height,depth,kind,compression,filtering,interlace=header
    rows=[(b'IHDR',struct.pack('>IIBBBBB',width,height,8,3,compression,filtering,interlace))];placed=written=False
    for tag,v in chunks[1:]:
        if tag in (b'bKGD',b'IDAT',b'IEND') and not placed:
            rows.append((b'PLTE',bytes(c for colour in ordered for c in colour)));placed=True
        if tag==b'IDAT':
            if written:continue
            v=zlib.compress(scan,9);written=True
        elif tag==b'bKGD':v=bytes([lookup[background]])
        rows.append((tag,v))
    out=_png(rows)
    verify_asset(data,out,'png')
    return out,{'status':'EVALUATED','algorithm':'png_exact_palette','distinct_colours':len(ordered),
        'samples':'RGBA_BYTE_IDENTICAL','quantization':False,'resize':False}

def verify_asset(before,after,kind):
    if before==after:return True
    if kind=='svg':
        # Canonicalize only validated rectangle d attributes; everything else
        # including clip windows, colour, layer order and semantic ids stays exact.
        def canonical(data):
            def sub(m):
                try:rows=rectangles(m[1].decode('ascii'))
                except UnicodeError:rows=None
                return b'd="'+repr(rows).encode()+b'"' if rows is not None else m[0]
            return PATH_TAG.sub(lambda m:D_ATTR.sub(sub,m[0]),data)
        if canonical(before)==canonical(after):return True
        # Repartition is allowed only for the encoder's exact deterministic result.
        lexical,_=lexical_svg(before);result,proof=region_svg(lexical)
        if result!=after or proof.get('status')!='EVALUATED':raise ValueError('Unproved SVG representation change')
        return True
    if kind=='png':
        from PIL import Image
        a,b=png_chunks(before),png_chunks(after)
        ah,bh=struct.unpack('>IIBBBBB',a[0][1]),struct.unpack('>IIBBBBB',b[0][1])
        if ah[:2]!=bh[:2]:raise ValueError('PNG dimensions changed')
        if ah==bh and [(k,v) for k,v in a if k!=b'IDAT']==[(k,v) for k,v in b if k!=b'IDAT']:
            if zlib.decompress(b''.join(v for k,v in a if k==b'IDAT'))!=zlib.decompress(b''.join(v for k,v in b if k==b'IDAT')):
                raise ValueError('PNG filtered samples changed')
        else:
            if ah[2:4]!=(8,2) or bh[2:4]!=(8,3):raise ValueError('Unexpected PNG encoding change')
            metadata=lambda rows:[(k,v) for k,v in rows if k not in (b'IHDR',b'PLTE',b'IDAT',b'IEND',b'bKGD')]
            if metadata(a)!=metadata(b):raise ValueError('PNG colour/metadata changed')
            background=lambda rows:next((v for k,v in rows if k==b'bKGD'),None)
            x,y=background(a),background(b)
            if bool(x)!=bool(y):raise ValueError('PNG background changed')
            if x:
                palette=next(v for k,v in b if k==b'PLTE');index=y[0]
                if struct.unpack('>HHH',x)!=tuple(palette[index*3:index*3+3]):raise ValueError('PNG background colour changed')
        with Image.open(io.BytesIO(before)) as a,Image.open(io.BytesIO(after)) as b:
            if a.size!=b.size or a.convert('RGBA').tobytes()!=b.convert('RGBA').tobytes():raise ValueError('PNG actual samples changed')
        return True
    raise ValueError('Protected resource cannot be reencoded')

def optimize(data,kind,*,region_limit=200000):
    candidates=[('original',data)];evaluations=[]
    if kind=='svg':
        result,proof=lexical_svg(data);candidates.append(('relative_svg',result));evaluations.append(proof)
        # Expensive region search is bounded; lexical codec always covers dense assets.
        if len(data)<=region_limit:
            result,proof=region_svg(result);candidates.append(('cell_partition',result));evaluations.append(proof)
        else:evaluations.append({'status':'INAPPLICABLE','algorithm':'exact_cell_repartition','reason':'bounded_region_search'})
    elif kind=='png' and len(data)<=MAX_ASSET:
        for fn,name in ((png_scanlines,'scanlines'),(png_palette,'exact_palette')):
            result,proof=fn(data);candidates.append((name,result));evaluations.append(proof)
    else:evaluations.append({'status':'INAPPLICABLE','reason':'protected_or_unsupported_type'})
    label,result=min(candidates,key=lambda item:stored(item[1]))
    if result!=data:verify_asset(data,result,kind)
    return result,{'version':VERSION,'selection':label,'status':'OPTIMIZED' if result!=data else 'RETAINED',
        'before_sha256':sha(data),'after_sha256':sha(result),'before_raw':len(data),'after_raw':len(result),
        'before_deflate':stored(data),'after_deflate':stored(result),'evaluations':evaluations}
