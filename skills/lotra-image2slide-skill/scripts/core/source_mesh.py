"""Export original continuous RGB ribbons as a single PDF vector mesh.

The original SVG/PPTX masters and source clip stay immutable. PDF Type4
triangles express each original linear colour interval without many Cairo
gradient objects, repeated complex clipping or a coarse function lookup.
"""
import copy,re
import numpy as np
from lxml import etree


def carrier_svg(blob):
    if b'continuous_original_colour_gradients' not in blob:return blob,None
    root=etree.fromstring(blob);ns='{http://www.w3.org/2000/svg}'
    width=int(root.get('width'));height=int(root.get('height'));rows=[]
    gradients={g.get('id'):g for g in root.iter(ns+'linearGradient')}
    group=next((g for g in root.iter(ns+'g') if g.get('clip-path')=='url(#owned)'),None)
    if group is None:raise ValueError('Original RGB owner clip missing')
    for rect in list(group):
        fill=rect.get('fill','')
        if rect.tag!=ns+'rect' or not fill.startswith('url(#'):
            raise ValueError('Unknown original RGB ribbon')
        gradient=gradients[fill[5:-1]];stops=list(gradient)
        if len(stops)!=width+2 or gradient.get('gradientUnits')!='userSpaceOnUse':
            raise ValueError('Original equally spaced RGB samples changed')
        colours=[]
        for column,stop in enumerate(stops[1:-1]):
            if abs(float(stop.get('offset'))-(column+.5)/width)>1e-8:
                raise ValueError('Original colour coordinate changed')
            text=stop.get('stop-color','')
            if len(text)!=7 or not text.startswith('#') or stop.get('stop-opacity') not in (None,'1'):
                raise ValueError('Original RGB values changed')
            colours.append([int(text[i:i+2],16) for i in (1,3,5)])
        rows.append({'rgb':np.asarray(colours,dtype='uint8'),'top':float(rect.get('y')),
                     'bottom':float(rect.get('y'))+float(rect.get('height'))})
        group.remove(rect)
    if not rows:raise ValueError('Original RGB owner has no rows')
    definitions=next(root.iter(ns+'defs'))
    for gradient in gradients.values():gradient.getparent().remove(gradient)
    gradient=etree.SubElement(definitions,ns+'linearGradient',id='source_mesh_carrier',gradientUnits='userSpaceOnUse',x1='0',y1='0',x2=str(width),y2='0')
    c0=(37,83,149);c1=(218,172,106)
    for offset,colour in ((0,c0),(1,c1)):
        stop=etree.SubElement(gradient,ns+'stop');stop.set('offset',str(offset));stop.set('stop-color','#'+''.join(f'{v:02X}' for v in colour))
    etree.SubElement(group,ns+'rect',x='0',y='0',width=str(width),height=str(height),fill='url(#source_mesh_carrier)')
    from .source_colour_grid import load
    plan={'width':width,'height':height,'rows':rows,'c0':c0,'c1':c1}
    original_grid=load(root,width,height)
    if original_grid is not None:plan['original_grid']=original_grid
    return etree.tostring(root),plan


def restore_mesh(document,plan):
    functions=[]
    for xref in range(1,document.xref_length()):
        obj=document.xref_object(xref,compressed=False)
        if not re.search(r'/FunctionType\s+2\b',obj):continue
        a=re.search(r'/C0\s*\[([^]]+)\]',obj);b=re.search(r'/C1\s*\[([^]]+)\]',obj)
        if a and b and tuple(round(float(v)*255) for v in a.group(1).split())==plan['c0'] and tuple(round(float(v)*255) for v in b.group(1).split())==plan['c1']:
            functions.append(xref)
    shaders=[]
    for xref in range(1,document.xref_length()):
        obj=document.xref_object(xref,compressed=False)
        if not re.search(r'/ShadingType\s+2\b',obj):continue
        function=re.search(r'/Function\s+(\d+)\s+0\s+R',obj)
        if function and int(function.group(1)) in functions:shaders.append(xref)
    if len(shaders)!=1:raise RuntimeError('Original RGB mesh carrier identity unresolved; no placeholder may be exported')
    if plan.get('original_grid') is not None:
        from .source_colour_grid import restore_pdf
        return restore_pdf(document,shaders[0],plan)
    width,height=plan['width'],plan['height'];xs=np.r_[0,np.arange(width)+.5,width]
    xcodes=np.rint(xs/width*65535).astype('>u2');pieces=[]
    dtype=np.dtype([('flag','u1'),('x','>u2'),('y','>u2'),('rgb','u1',(3,))])
    for row in plan['rows']:
        colours=np.vstack((row['rgb'][0],row['rgb'],row['rgb'][-1]))
        mesh=np.zeros((width+1,6),dtype=dtype)
        for slot in (0,3,5):mesh['x'][:,slot]=xcodes[:-1];mesh['rgb'][:,slot]=colours[:-1]
        for slot in (1,2,4):mesh['x'][:,slot]=xcodes[1:];mesh['rgb'][:,slot]=colours[1:]
        top=round(row['top']/height*65535);bottom=round(row['bottom']/height*65535)
        for slot in (0,1,3):mesh['y'][:,slot]=top
        for slot in (2,4,5):mesh['y'][:,slot]=bottom
        pieces.append(mesh.tobytes())
    payload=b''.join(pieces);xref=shaders[0]
    document.update_object(xref,f'<< /ShadingType 4 /ColorSpace /DeviceRGB /BitsPerCoordinate 16 /BitsPerComponent 8 /BitsPerFlag 8 /Decode [0 {width} 0 {height} 0 1 0 1 0 1] /BBox [0 0 {width} {height}] >>')
    document.update_stream(xref,payload,compress=True)
    return {'source_rows':len(plan['rows']),'triangles':len(plan['rows'])*(width+1)*2,
            'representation':'PDF Type4 vector mesh, original RGB values and original ribbon extents',
            'coordinate_quantization_max_source_px':max(width,height)/65535/2,
            'scope':'Vector paper representation only; immutable SVG/PPTX and clip/layout unchanged'}
