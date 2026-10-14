"""Continuous source-colour vector ribbons inside an explicit semantic owner.

No pixels, generated facts or new semantics enter the SVG: each gradient stop
comes from immutable original samples. The source-selected owner and complete
underlay remain independent. This avoids neighbouring contour AA seams.
"""
from pathlib import Path
from xml.sax.saxutils import escape
import numpy as np
from skimage.measure import find_contours
from .common import identity,digest,write_json
from .recipes import node

def construct(task,state,component,spec,rgb,visible,complete,deps):
    from .vector_asset import preview
    from .source_colour_grid import fields,metadata
    if spec.get('registration'):
        raise ValueError('Source gradient ribbons currently require original owner coordinates')
    if rgb.shape[:2]!=visible.shape or complete.shape!=visible.shape:
        raise ValueError('Continuous gradients share source ownership dimensions')
    height,width=visible.shape
    preview_method=spec.get('preview_method','svg_raster')
    if preview_method not in ('svg_raster','source_samples'):raise ValueError('Unknown declared source appearance preview')
    continuous=spec.get('continuous_contours')
    basis=spec.get('contour_basis')
    if continuous is not None:
        from .common import safe_path
        evidence=(basis or {}).get('fit_evidence',{})
        if (not isinstance(continuous,list) or not 1<=len(continuous)<=24
                or (basis or {}).get('source_hash')!=state['source']['sha256']
                or not (basis or {}).get('description') or not evidence.get('path')
                or digest(safe_path(task,evidence['path']))!=evidence.get('sha256')):
            raise ValueError('Continuous source fields require exact original fitted contour evidence')
        from .geometry import path_operations
        for contour in continuous:
            operations=list(path_operations(contour))
            if not contour.get('closed') or not 4<=len(operations)<=256:
                raise ValueError('One bounded continuous material contour per natural source part')
            for op,points in operations:
                for point in points:
                    if len(point)!=2 or not np.isfinite(point).all() or any(not -.25<=v<=1.25 for v in point):
                        raise ValueError('Continuous contour stays in its bounded original source frame')
    overlap=spec.get('edge_overlap_px',.2)
    if not 0<=overlap<=.2:raise ValueError('Bounded shared-row overlap required')
    key=identity({'owner':component['id'],'source':deps,'code':digest(Path(__file__)),
                  'size':[width,height],'overlap':overlap,'fill':spec.get('completion_fill'),'preview_method':preview_method,'field_sampling':spec.get('field_sampling','horizontal_rows'),'vertical_subdivisions':spec.get('vertical_subdivisions',4),'field_code':digest(Path(fields.__code__.co_filename)),'office_display':spec.get('office_display'),'display_evidence':spec.get('display_evidence'),'continuous_contours':continuous,'contour_basis':basis})[:20]
    folder=Path(task)/'scratch'/('gradient-'+component['id']+'-'+key);folder.mkdir(exist_ok=True)
    svg=folder/'artwork.svg';png=folder/'compatibility.png'
    def boundary(mask):
        sequences=[]
        for points in find_contours(np.pad(mask.astype(float),1),.5,fully_connected='high'):
            if len(points)<4:continue
            xy=[(x-.5,y-.5) for y,x in points[:-1]]
            sequences.append('M'+f'{xy[0][0]:.1f},{xy[0][1]:.1f}'+'L'+' '.join(f'{x:.1f},{y:.1f}' for x,y in xy[1:])+'Z')
        return ' '.join(sequences)
    def continuous_boundary():
        from .geometry import path_operations
        sequences=[]
        for contour in continuous:
            for op,points in path_operations(contour):
                if op=='close':sequences.append('Z')
                else:
                    symbol={'moveTo':'M','lnTo':'L','cubicBezTo':'C','quadBezTo':'Q'}[op]
                    sequences.append(symbol+' '.join(f'{x*width:.8f},{y*height:.8f}' for x,y in points))
        return ' '.join(sequences)
    original_boundary=continuous_boundary() if continuous is not None else boundary(visible)
    def colour(values):return '#'+''.join(f'{int(v):02X}' for v in values)
    definitions=['<clipPath id="owned"><path fill-rule="evenodd" d="'+original_boundary+'"/></clipPath>']
    ribbons=[];stops=0
    for row,line,top,bottom in fields(rgb,visible,spec):
        # Original centres, with endpoints extended to the outer cell edge.
        data=['<stop offset="0" stop-color="'+colour(line[0])+'"/>']
        for column,values in enumerate(line):
            data.append(f'<stop offset="{(column+.5)/width:.8f}" stop-color="{colour(values)}"/>')
        data.append('<stop offset="1" stop-color="'+colour(line[-1])+'"/>')
        definitions.append(f'<linearGradient id="r{row}" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{width}" y2="0">'+''.join(data)+'</linearGradient>')
        rendering=' shape-rendering="crispEdges"' if spec.get('field_sampling')=='bilinear_grid' else ''
        ribbons.append(f'<rect x="0" y="{top:.3f}" width="{width}" height="{bottom-top:.3f}" fill="url(#r{row})"{rendering}/>')
        stops+=len(line)+2
    lineage={'source_hash':state['source']['sha256'],'semantic_owner':component['id'],
       'method':'continuous_original_colour_gradients','field_sampling':spec.get('field_sampling','horizontal_rows'),'source_mask_hash':deps['mask'],'continuous_source_contour':basis if continuous is not None else None,
       'scientific_detail':'original sampled colours only; no generated measurement or anatomy',
       'completion':'source-declared underlay only' if np.any(complete & ~visible) else 'none'}
    fill=spec.get('completion_fill')
    if fill is None:fill=''.join(f'{int(v):02X}' for v in np.rint(np.mean(rgb[visible],axis=0)))
    pieces=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
       '<desc>'+escape(str(lineage))+'</desc>'+metadata(rgb,spec)+'<defs>'+''.join(definitions)+'</defs>',
       '<path fill="#'+fill+'" fill-rule="evenodd" d="'+(original_boundary if continuous is not None and np.array_equal(complete,visible) else boundary(complete))+'"/>',
       '<g clip-path="url(#owned)">'+''.join(ribbons)+'</g></svg>']
    svg.write_text(''.join(pieces),encoding='utf-8')
    if preview_method=='source_samples':
        source_sample_preview(png,rgb,visible,complete,fill)
    else:preview(svg,png,width=min(1200,max(384,width*3)))
    asset={'path':svg.relative_to(task).as_posix(),'sha256':digest(svg),
      'preview':{'path':png.relative_to(task).as_posix(),'sha256':digest(png)},
      'representation':'svg','edit_level':'component','lineage':lineage,
      'preview_sampling':preview_method,
      'cost':{'svg_bytes':svg.stat().st_size,'gradient_stops':stops,'rows':len(ribbons),'compatibility_bytes':png.stat().st_size}}
    if spec.get('office_display')=='preview':
        asset.update(office_display='preview',display_reason=spec.get('display_reason'),display_evidence=spec.get('display_evidence'))
    if spec.get('connection_sites'):asset['connection_sites']=spec['connection_sites']
    write_json(folder/'representation.json',asset)
    return [node(component['id'],'svg',component['roi'],asset,semantic=component['semantic_class'])]



def excise_original_part(task,state,previous,visible_descriptor,complete_descriptor,exclusion_descriptor,evidence):
    """Regenerate an old RGB mother minus one independently source-owned part.

    Preserve original source RGB, frame, remaining ownership and field recipe.
    No outer SVG wrapper/extra coordinate context is introduced. An actual
    non-target pixel comparison is still required; this is not acceptance.
    """
    from PIL import Image
    from .common import safe_path
    import copy
    lineage=previous.get('content',{}).get('lineage',{})
    if (previous.get('render_type')!='svg' or lineage.get('method')!='continuous_original_colour_gradients'
            or lineage.get('source_hash')!=state['source']['sha256'] or evidence.get('source_hash')!=state['source']['sha256']
            or not evidence.get('natural_unit') or not evidence.get('description')):
        raise ValueError('Excise only one identified original natural part from a bound RGB mother')
    x,y,w,h=previous['bbox']
    if any(int(v)!=v for v in (x,y,w,h)):raise ValueError('Retain the exact original integral field frame')
    x,y,w,h=map(int,(x,y,w,h))
    def read_mask(descriptor):
        file=safe_path(task,descriptor['path'])
        if digest(file)!=descriptor['sha256']:raise ValueError('Original retained/excluded ownership changed')
        result=np.asarray(Image.open(file).convert('L'))>0
        if result.shape!=(h,w):raise ValueError('Original masks share the immutable material frame')
        return result
    visible,complete,excluded=[read_mask(v) for v in (visible_descriptor,complete_descriptor,exclusion_descriptor)]
    if lineage['source_mask_hash']!=visible_descriptor['sha256'] or np.any(visible&~complete) or not np.any(visible&excluded):
        raise ValueError('Bind the exact old original visibility and a nonempty named natural excision')
    from . import source_quality as q
    natural=state.get('quality',{}).get('units',{}).get(evidence['natural_unit'])
    if not natural or not natural.get('reference_mask'):
        raise ValueError('Named natural excision needs its independent original foreground ownership')
    natural_roi=natural['roi']
    if any(int(v)!=v for v in natural_roi):raise ValueError('Natural source ownership uses integral source coordinates')
    nx,ny,nw,nh=map(int,natural_roi);natural_mask=q._mask(task,natural['reference_mask'])
    mapped=np.zeros((h,w),bool);left=max(x,nx);top=max(y,ny);right=min(x+w,nx+nw);bottom=min(y+h,ny+nh)
    if natural_mask.shape!=(nh,nw) or right<=left or bottom<=top:
        raise ValueError('Natural source owner and original material do not overlap')
    mapped[top-y:bottom-y,left-x:right-x]=natural_mask[top-ny:bottom-ny,left-nx:right-nx]
    if np.any(excluded&complete&~mapped):
        raise ValueError('Natural excision cannot remove source material outside its declared original part')
    remaining=visible&~excluded;underlay=complete&~excluded
    if not remaining.any():raise ValueError('A wholly excised leaf needs an explicit remove action')
    folder=Path(task)/'scratch'/('natural-excision-'+identity({'object':previous['id'],'visible':visible_descriptor,'complete':complete_descriptor,'exclusion':exclusion_descriptor,'evidence':evidence})[:20]);folder.mkdir(exist_ok=True)
    masks={}
    for label,data in (('visible',remaining),('complete',underlay)):
        file=folder/(label+'.png');Image.fromarray(data.astype('uint8')*255).save(file);masks[label]={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    rgb=np.asarray(Image.open(safe_path(task,state['source']['path'])).convert('RGB').crop((x,y,x+w,y+h)),np.uint8)
    spec={'field_sampling':lineage.get('field_sampling','horizontal_rows'),'vertical_subdivisions':4,'edge_overlap_px':.2,'completion_fill':previous['style'].get('fill')}
    node=construct(task,state,{'id':previous['id'],'roi':previous['bbox'],'semantic_class':previous['semantic_type']},spec,rgb,remaining,underlay,
        {'source':state['source']['sha256'],'mask':masks['visible']['sha256'],'complete':masks['complete']['sha256'],'source_natural_excision':evidence['natural_unit']})[0]
    for key in ('parent','style','z_order','evidence_status'):
        if key in previous:node[key]=copy.deepcopy(previous[key])
    node['content']['retained_mother']={'path':previous['content']['path'],'sha256':previous['content']['sha256']}
    node['content']['source_natural_excision']={'evidence':evidence,'exclusion':exclusion_descriptor,'remaining_original_masks':masks,
        'limits':'Old source RGB/remaining mask coordinates retained. Actual renderer can still differ; protect remaining owned pixels and every outside unit before adoption.'}
    return node


def bounded_pdf_gradients(blob, maximum_stops=128):
    """Exact export-only subdivision of this module's long row gradients.

    Each adjacent slab shares two original stops, hence the overlapping one-
    pixel field has the identical linear colours. No colour quantization or
    new samples are introduced. Other SVG authors retain their original data.
    """
    if b'continuous_original_colour_gradients' not in blob:
        return blob, {'split_gradients': 0, 'maximum_stops': maximum_stops}
    from lxml import etree
    import copy
    root=etree.fromstring(blob);ns='{http://www.w3.org/2000/svg}'
    gradients={g.get('id'):g for g in root.iter(ns+'linearGradient')}
    count=0;slabs=0
    for rect in list(root.iter(ns+'rect')):
        fill=rect.get('fill','')
        if not fill.startswith('url(#') or not fill.endswith(')'):continue
        gradient=gradients.get(fill[5:-1])
        if gradient is None:continue
        stops=list(gradient)
        if len(stops)<=maximum_stops:continue
        if (gradient.get('gradientUnits')!='userSpaceOnUse'
                or gradient.get('gradientTransform') or rect.get('transform')
                or float(gradient.get('y1','0'))!=float(gradient.get('y2','0'))):
            raise ValueError('Unrecognized source ribbon coordinates; preserve the SVG master')
        def offset(stop):
            value=stop.get('offset','0')
            return float(value[:-1])/100 if value.endswith('%') else float(value)
        positions=[offset(stop) for stop in stops]
        if any(a>b for a,b in zip(positions,positions[1:])):
            raise ValueError('Source gradient stop order changed')
        x1=float(gradient.get('x1','0'));x2=float(gradient.get('x2','1'))
        if x2<=x1:raise ValueError('Source ribbon orientation changed')
        rx=float(rect.get('x','0'));right=rx+float(rect.get('width'))
        parent=rect.getparent();index=parent.index(rect);start=0;part=0
        while start<len(stops)-1:
            end=min(len(stops)-1,start+maximum_stops-1)
            lo,hi=positions[start],positions[end]
            if hi<=lo:raise ValueError('Degenerate source gradient slab')
            left=max(rx,x1+(x2-x1)*lo);edge=min(right,x1+(x2-x1)*hi)
            if edge>left:
                gid=gradient.get('id')+'_bounded_'+str(part)
                child=copy.deepcopy(gradient);child.set('id',gid)
                for node in list(child):child.remove(node)
                child.set('x1',format(x1+(x2-x1)*lo,'.12g'))
                child.set('x2',format(x1+(x2-x1)*hi,'.12g'))
                for stop,value in zip(stops[start:end+1],positions[start:end+1]):
                    node=copy.deepcopy(stop);node.set('offset',format((value-lo)/(hi-lo),'.12g'));child.append(node)
                gradient.getparent().append(child)
                slab=copy.deepcopy(rect);slab.set('x',format(left,'.12g'));slab.set('width',format(edge-left,'.12g'))
                slab.set('fill','url(#'+gid+')');parent.insert(index+part,slab)
                part+=1;slabs+=1
            if end==len(stops)-1:break
            start=end-1
        parent.remove(rect);gradient.getparent().remove(gradient);count+=1
    return etree.tostring(root),{'split_gradients':count,'slabs':slabs,'maximum_stops':maximum_stops,
        'scope':'PDF conversion only; original immutable SVG/PPTX masters unchanged; original stops and linear fields retained'}


def sampled_pdf_plan(blob, maximum_samples=64):
    """Original RGB vector fields in bounded sampled PDF shading slabs.

    A long colour function can be resampled coarsely by a PDF renderer. Bound
    the source span, share two source centres and preserve the same linear
    field in the overlap; do not lower detail to save serialization cost.
    """
    if b'continuous_original_colour_gradients' not in blob:return blob, []
    from lxml import etree
    import copy
    root=etree.fromstring(blob);ns='{http://www.w3.org/2000/svg}';plans=[]
    import re
    owned=next((v for v in root.iter(ns+'clipPath') if v.get('id')=='owned'),None)
    if owned is None:raise ValueError('Original source owner clip is missing')
    paths=list(owned.iter(ns+'path'))
    coordinates=[(float(x),float(y)) for path in paths
        for x,y in re.findall(r'(-?[\d.]+),(-?[\d.]+)',path.get('d',''))]
    if not coordinates:raise ValueError('Original source owner clip is empty')
    bounds=(min(x for x,y in coordinates),min(y for x,y in coordinates),
            max(x for x,y in coordinates),max(y for x,y in coordinates))
    for gradient in list(root.iter(ns+'linearGradient')):
        stops=list(gradient);width=len(stops)-2
        if (width<2 or gradient.get('gradientUnits')!='userSpaceOnUse'
                or gradient.get('gradientTransform')
                or float(gradient.get('x1','0'))!=0
                or float(gradient.get('x2','0'))!=width):
            raise ValueError('Unknown source sampled-gradient grid')
        colours=[]
        for column,stop in enumerate(stops[1:-1]):
            if abs(float(stop.get('offset'))-(column+.5)/width)>1e-8:
                raise ValueError('Original gradient samples are no longer equally spaced')
            text=stop.get('stop-color','')
            if len(text)!=7 or not text.startswith('#') or stop.get('stop-opacity') not in (None,'1'):
                raise ValueError('Original RGB source sample changed')
            colours.append(bytes(int(text[i:i+2],16) for i in (1,3,5)))
        rectangles=[r for r in root.iter(ns+'rect') if r.get('fill')=='url(#'+gradient.get('id')+')']
        if len(rectangles)!=1:raise ValueError('Source row ownership is no longer unique')
        rect=rectangles[0];parent=rect.getparent();position=parent.index(rect);left_column=0;part=0
        while left_column<width-1:
            right_column=min(width,left_column+maximum_samples);count=right_column-left_column
            left=0 if left_column==0 else left_column+.5
            right=width if right_column==width else right_column-.5
            top=float(rect.get('y','0'));bottom=top+float(rect.get('height'))
            if right<=bounds[0] or left>=bounds[2] or bottom<=bounds[1] or top>=bounds[3]:
                # This rectangle has provably zero intersection with the
                # immutable original clip. Cairo legitimately omits it.
                if right_column==width:break
                left_column=right_column-2;continue
            index=len(plans)+1
            if index>=65536:raise ValueError('Source gradient carrier capacity exceeded')
            a=(37,index//256,index%256);b=(218,255-a[1],255-a[2])
            gid=gradient.get('id')+'_sample_'+str(part);child=copy.deepcopy(gradient);child.set('id',gid)
            for stop in list(child):child.remove(stop)
            child.set('x1',str(left_column+.5));child.set('x2',str(right_column-.5))
            for offset,colour in ((0,a),(1,b)):
                node=etree.SubElement(child,ns+'stop');node.set('offset',str(offset))
                node.set('stop-color','#'+''.join(f'{v:02X}' for v in colour))
            gradient.getparent().append(child)
            slab=copy.deepcopy(rect);left=0 if left_column==0 else left_column+.5
            right=width if right_column==width else right_column-.5
            slab.set('x',str(left));slab.set('width',str(right-left));slab.set('fill','url(#'+gid+')')
            parent.insert(position+part,slab)
            plans.append({'c0':a,'c1':b,'width':count,'encode':[0,count-1],
                          'samples':b''.join(colours[left_column:right_column])})
            part+=1
            if right_column==width:break
            left_column=right_column-2
        parent.remove(rect);gradient.getparent().remove(gradient)
    return etree.tostring(root),plans


def restore_pdf_samples(document,plans):
    """Replace uniquely identified carrier functions with PDF Type0/Order1.

    The declared Encode mapping puts original RGB values at the original pixel
    centres, with constant endpoint extension. RGB samples are vector shading
    function data, not image XObjects; the original clip/path is retained.
    """
    import re
    lookup={(tuple(p['c0']),tuple(p['c1'])):p for p in plans};seen=set()
    for xref in range(1,document.xref_length()):
        obj=document.xref_object(xref,compressed=False)
        if not re.search(r'/FunctionType\s+2\b',obj):continue
        first=re.search(r'/C0\s*\[([^]]+)\]',obj);last=re.search(r'/C1\s*\[([^]]+)\]',obj)
        if not first or not last:continue
        def rgb(match):return tuple(round(float(v)*255) for v in match.group(1).split())
        signature=(rgb(first),rgb(last));plan=lookup.get(signature)
        if plan is None:continue
        width=plan['width'];encode=plan.get('encode',[-.5,width-.5])
        document.update_object(xref,'<< /FunctionType 0 /Domain [0 1] /Range [0 1 0 1 0 1] '
            +f'/Size [{width}] /BitsPerSample 8 /Order 1 /Encode [{encode[0]} {encode[1]}] /Decode [0 1 0 1 0 1] >>')
        document.update_stream(xref,plan['samples'],compress=True);seen.add(signature)
    if seen!=set(lookup):
        raise RuntimeError('Source gradient PDF carrier identity unresolved; do not publish placeholder colours')
    return {'rows':len(plans),'sample_bytes':sum(len(p['samples']) for p in plans),
            'representation':'PDF sampled vector shading functions, original RGB rows, linear interpolation',
            'scope':'Export representation only; immutable SVG/PPTX unchanged'}


def source_sample_preview(png, rgb, visible, complete, fill):
    """HD host appearance directly from the same immutable colour samples.

    Explicit semantic supports, underlay and frame are unchanged. A bounded
    two-dimensional Lanczos reconstruction avoids rasterizing a row field
    first and then resampling that already filtered compatibility image.
    No source anatomy, texture or scientific detail is generated here.
    The pure SVG mother is unchanged and assessed separately for paper export.
    """
    from PIL import Image
    if rgb.shape[:2]!=visible.shape or complete.shape!=visible.shape:
        raise ValueError('Source samples and semantic support dimensions differ')
    if np.any(visible & ~complete) or not visible.any():raise ValueError('Preserve visible source support')
    height,width=visible.shape
    rgba=np.zeros((height,width,4),np.uint8)
    underlay=np.array([int(fill[i:i+2],16) for i in (0,2,4)],np.uint8)
    rgba[complete,:3]=underlay;rgba[visible,:3]=rgb[visible]
    rgba[complete,3]=255
    image=Image.fromarray(rgba,'RGBA')
    factor=min(3.,2400/max(width,height))
    if factor<1:raise ValueError('Source HD preview must not downsample original evidence')
    target=(max(width,round(width*factor)),max(height,round(height*factor)))
    if image.size!=target:image=image.resize(target,Image.Resampling.LANCZOS)
    image.save(png,optimize=True)
