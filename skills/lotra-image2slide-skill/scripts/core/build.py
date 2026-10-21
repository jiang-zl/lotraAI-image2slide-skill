"""Deterministic native PresentationML builder; XML extensions isolated here."""

import os
from pathlib import Path
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.util import Inches, Pt
from .common import digest, identity, safe_path, write_json, writer
from .mathml import child, el, insert_math, math_zone, NS
from .scene import validate
from .geometry import custom_geometry,ported_shape,connector_points,bounds,set_native_route
from . import VERSION


def inline_text_runs(ast, font='Cambria Math'):
    """Native editable caption variables supported by Office and LibreOffice.

    Keep structured fractions/scripts as OMML. A single x/y or accented
    variable is ordinary native text, rather than an inline extension which
    some actual renderers silently omit inside a mixed text paragraph.
    """
    import unicodedata
    op=ast.get('op')
    if op=='token':
        return [{'text':ast['text'],'font':font,'italic':not ast.get('normal',False)}]
    if op=='seq':
        result=[]
        for item in ast['items']:
            runs=inline_text_runs(item,font)
            if runs is None:return None
            result.extend(runs)
        return result
    if op in ('sub','sup','scripts'):
        base=inline_text_runs(ast['base'],font)
        if base is None:return None
        result=base
        for key,baseline in [('sub',-30000),('sup',35000)]:
            if key not in ast:continue
            runs=inline_text_runs(ast[key],font)
            if runs is None:return None
            for run in runs:
                run['font_scale']=run.get('font_scale',1)*.72
                run['baseline']=run.get('baseline',0)+baseline
            result.extend(runs)
        return result if all(-35000<=r.get('baseline',0)<=35000 for r in result) else None
    if op=='delimited':
        body=inline_text_runs(ast['body'],font)
        if body is None:return None
        return [{'text':ast['left'],'font':font,'italic':False}]+body+[{'text':ast['right'],'font':font,'italic':False}]
    if op=='accent':
        runs=inline_text_runs(ast['body'],font)
        if runs and len(runs)==1 and len(runs[0]['text'])==1:
            runs[0]['text']=unicodedata.normalize('NFC',runs[0]['text']+ast['mark'])
            return runs
    return None


def text_body(shape,content,style):
    frame=shape.text_frame
    frame.margin_left=frame.margin_right=frame.margin_top=frame.margin_bottom=0
    frame.word_wrap=style.get('wrap',False)
    frame.auto_size=MSO_AUTO_SIZE.NONE
    frame.vertical_anchor={'top':MSO_ANCHOR.TOP,'middle':MSO_ANCHOR.MIDDLE,'bottom':MSO_ANCHOR.BOTTOM}[style.get('valign','top')]
    paragraphs=content.get('paragraphs')
    if paragraphs is None:
        paragraphs=[content.get('runs',[{'text':line}]) for line in content.get('text','').split('\n')]
    frame.clear()
    span_index=0
    if content.get('inline_math') in ('native_runs','native_tokens') and any('ast' in item for row in paragraphs for item in row):
        raise ValueError('Mathematical spans require real Office Math; ordinary native runs cannot substitute')
    native_math=False
    for i,runs in enumerate(paragraphs):
        p=frame.paragraphs[0] if i==0 else frame.add_paragraph()
        p.alignment={'left':PP_ALIGN.LEFT,'center':PP_ALIGN.CENTER,'right':PP_ALIGN.RIGHT}[style.get('align','left')]
        p.space_before=p.space_after=Pt(0)
        if 'line_spacing' in style:p.line_spacing=style['line_spacing']
        if 'line_spacing_pt' in style:
            spacing=style['line_spacing_pt']
            if not isinstance(spacing,(int,float)) or not 0<spacing<=72:raise ValueError('Native exact row spacing needs source-supported bounded points')
            p.line_spacing=Pt(spacing)
        if any('ast' in item for item in runs):
            # Office uses paragraph defaults for mixed native mathematical rows.
            faces=style.get('font_faces',{})
            p.font.name=faces.get('latin',faces.get('ea',style.get('font','Times New Roman')));p.font.size=Pt(style.get('font_size',16))
        if content.get('paragraph_layout'):
            layouts=content['paragraph_layout']
            if len(layouts)!=len(paragraphs):raise ValueError('Native paragraph layout count must preserve exact text rows')
            layout=layouts[i]
            if set(layout)-{'left_indent_pt','right_indent_pt'}:raise ValueError('Unknown native paragraph layout field')
            left=layout.get('left_indent_pt',0);right=layout.get('right_indent_pt',0)
            if any(not isinstance(v,(int,float)) or not 0<=v<=72 for v in (left,right)) or left+right>shape.width/12700*.5:
                raise ValueError('Native paragraph indents must remain inside the existing source text frame')
            props=p._p.get_or_add_pPr()
            props.set('marL',str(round(left*12700)));props.set('marR',str(round(right*12700)))
        expanded=[]
        for item in runs:
            faces={**style.get('font_faces',{}),**item.get('font_faces',{})}
            math_face=faces.get('math',item.get('font',style.get('math_font',style.get('font','Cambria Math'))))
            simple=inline_text_runs(item['ast'],math_face) if 'ast' in item and native_math else None
            expanded.extend([{**{k:v for k,v in item.items() if k!='ast'},**r,'_lotra_math_run':True,'_lotra_math_span':span_index} for r in simple] if simple is not None else [item])
            if 'ast' in item:span_index+=1
        for item in expanded:
            size=item.get('font_size',style.get('font_size',16))*item.get('font_scale',1)
            faces={**style.get('font_faces',{}),**item.get('font_faces',{})}
            if 'ast' in item:
                from .math_typography import apply
                typography={k:style[k] for k in ('bold','italic') if k in style}
                typography.update({k:item[k] for k in ('bold','italic') if k in item})
                typography.update(item.get('math_typography',{}))
                p._p.append(apply(math_zone(item['ast'],size,faces.get('math',item.get('font',style.get('math_font',style.get('font','Cambria Math')))),inline=True,color=item.get('color',style.get('color')),font_policy=item.get('math_font_policy',style.get('math_font_policy','native_math'))),typography))
            else:
                r=p.add_run();r.text=item.get('text','')
                primary=(faces.get('math',item.get('font','Cambria Math')) if item.get('_lotra_math_run') else
                         faces.get('latin',faces.get('ea',faces.get('cs',item.get('font',style.get('font','DejaVu Sans'))))))
                r.font.size=Pt(size);r.font.name=primary
                # Latin typeface alone leaves Chinese text on the theme font.
                # Set script-specific faces on each actual native text run.
                rpr=r._r.get_or_add_rPr()
                for script in ('ea','cs'):
                    face=rpr.find('a:'+script,NS)
                    if face is None:face=child(rpr,'a:'+script)
                    face.set('typeface',faces.get(script,primary))
                r.font.bold=item.get('bold',style.get('bold',False));r.font.italic=item.get('italic',style.get('italic',False))
                r.font.color.rgb=RGBColor.from_string(item.get('color',style.get('color','17324D')))
                if style.get('text_outline_width_pt'):
                    width=style['text_outline_width_pt']
                    if not 0 < width <= min(.75,size*.04):
                        raise ValueError('Text outline must preserve the original glyph scale')
                    ln=child(rpr,'a:ln',w=str(round(width*12700)))
                    fill=child(ln,'a:solidFill')
                    colour=child(fill,'a:srgbClr',val=item.get('color',style.get('color','17324D')))
                    if 'text_outline_alpha' in style:
                        alpha=style['text_outline_alpha']
                        if not isinstance(alpha,(int,float)) or not 0<=alpha<=1:
                            raise ValueError('Native text-outline opacity must be bounded')
                        child(colour,'a:alpha',val=round(alpha*100000))
                    child(ln,'a:round')
                    rpr.remove(ln);rpr.insert(0,ln)
                if 'baseline' in item:rpr.set('baseline',str(round(item['baseline'])))
                spacing=item.get('char_spacing_pt',style.get('char_spacing_pt'))
                if spacing is not None:r._r.get_or_add_rPr().set('spc',str(round(spacing*100)))
                if style.get('baseline_offset_pt'):
                    r._r.get_or_add_rPr().set('baseline',str(round(style['baseline_offset_pt']/size*100000)))
                if '_lotra_math_span' in item:
                    extension=child(child(rpr,'a:extLst'),'a:ext',uri='urn:lotraai:native-math-span:1')
                    marker=extension.makeelement('{urn:lotraai:native-math-span:1}span',{'index':str(item['_lotra_math_span'])});extension.append(marker)


def shape_style(shape,style,kind):
    if kind not in ('shape','bezier','path','connector'):return
    effect=shape._element.find('p:style/a:effectRef',NS)
    if effect is not None and not style.get('shadow',False):effect.set('idx','0')
    if kind!='connector':
        fill=style.get('fill','A7C5DF' if kind=='shape' else None)
        if fill is None or fill=='none':shape.fill.background()
        else:
            shape.fill.solid();shape.fill.fore_color.rgb=RGBColor.from_string(fill)
            if 'fill_alpha' in style:
                alpha=style['fill_alpha']
                if not isinstance(alpha,(int,float)) or not 0<=alpha<=1:raise ValueError('Fill opacity must be between zero and one')
                child(shape._element.spPr.find('a:solidFill/a:srgbClr',NS),'a:alpha',val=round(alpha*100000))
        if style.get('gradient'):
            props=shape._element.spPr
            for name in ('solidFill','noFill'):
                old=props.find('a:'+name,NS)
                if old is not None:props.remove(old)
            gradient=el('a:gradFill',rotWithShape='1');stops=child(gradient,'a:gsLst')
            colors=style['gradient']
            if len(colors)<2:raise ValueError('Native material gradient needs at least two colors')
            positions=style.get('gradient_positions',[i/(len(colors)-1) for i in range(len(colors))])
            if len(colors)<2 or len(positions)!=len(colors) or any(type(v) not in (int,float) or not 0<=v<=1 for v in positions) or positions!=sorted(set(positions)):
                raise ValueError('Distinct ordered native gradient stops in [0,1] required')
            for pos,color in zip(positions,colors):child(child(stops,'a:gs',pos=round(pos*100000)),'a:srgbClr',val=color)
            mode=style.get('gradient_kind','linear')
            if mode=='radial':
                focus=style.get('gradient_focus',[.5,.5])
                if len(focus)!=2 or any(type(v) not in (int,float) or not 0<=v<=1 for v in focus):raise ValueError('Native radial material focus must stay inside its shape')
                pathmode=style.get('gradient_path','shape')
                if pathmode not in ('shape','circle','rect'):raise ValueError('Implemented source-supported native gradient path required')
                pathfill=child(gradient,'a:path',path=pathmode)
                child(pathfill,'a:fillToRect',l=round(focus[0]*100000),t=round(focus[1]*100000),r=round((1-focus[0])*100000),b=round((1-focus[1])*100000))
            elif mode=='linear':child(gradient,'a:lin',ang=str(round((style.get('gradient_angle',90)%360)*60000)),scaled='1')
            else:raise ValueError('Implemented native linear/radial gradient required')
            props.insert(2,gradient)
    if style.get('stroke','17324D') is None:shape.line.fill.background()
    else:
        shape.line.color.rgb=RGBColor.from_string(style.get('stroke','17324D'));shape.line.width=Pt(style.get('line_width',1.5))
    line=shape._element.spPr.get_or_add_ln()
    if style.get('line_cap'):line.set('cap',{'round':'rnd','square':'sq','flat':'flat'}[style['line_cap']])
    if style.get('line_join'):
        for old in list(line):
            if old.tag.rsplit('}',1)[-1] in ('round','bevel','miter'):line.remove(old)
        join=el('a:'+style['line_join']);before=next((i for i,item in enumerate(line) if item.tag.rsplit('}',1)[-1] in ('headEnd','tailEnd','extLst')),len(line));line.insert(before,join)
    if style.get('dash'):
        old=line.find('a:prstDash',NS)
        if old is not None:line.remove(old)
        dash=el('a:prstDash',val=style['dash'])
        before=next((i for i,item in enumerate(line) if item.tag.rsplit('}',1)[-1] in ('round','bevel','miter','headEnd','tailEnd','extLst')),len(line))
        line.insert(before,dash)

from .presets import PRESETS


def build(scene, base, output):
    from .semantic_curves import compile_scene as compile_curves
    scene=compile_curves(scene,scene.get('curve_write_scope'))
    from .font_contract import compile_scene
    scene=compile_scene(scene)
    from .frame_plan import compile_scene as compile_frames
    scene=compile_frames(scene,base,scene.get('curve_write_scope'))
    import time,faulthandler
    output=Path(output)
    begin=time.monotonic()
    stack=output.with_suffix('.build-stack.log').open('a')
    faulthandler.dump_traceback_later(60,repeat=True,file=stack)
    def progress(stage,owner=None):
        write_json(output.with_suffix('.build-progress.json'),
                   {'stage':stage,'owner':owner,'seconds':time.monotonic()-begin})
    progress('scene_contract')
    objects = validate(scene, base)
    from .semantic_composition import compile_order
    semantic_order = compile_order(scene)
    progress('native_geometry')
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    prs = Presentation()
    from .session import implementation_identity
    implementation=implementation_identity()
    prs.core_properties.identifier='lotraai-image2slide/'+VERSION+';scene='+identity(scene)+';implementation='+implementation['files_sha256']
    prs.core_properties.title='Scientific figure reconstruction'
    from .native_input import scene_dimensions
    width,height=scene_dimensions(scene)
    scale = width / scene["canvas"]["width"]
    prs.slide_width = width
    prs.slide_height = height
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb=RGBColor(*scene['canvas'].get('background_rgb',[255,255,255]))
    mapping, shapes = {}, {}
    svg_resources = {}
    children_by_parent={}
    for obj in scene['objects']:children_by_parent.setdefault(obj.get('parent'),[]).append(obj)
    pending=[]
    # One allocator across nested collections avoids scanning every geometry
    # point for //@id on every insertion, and prevents nested turbo ID clashes.
    last_shape_id=slide.shapes._spTree.max_shape_id
    def reserve(collection):
        nonlocal last_shape_id
        collection._cached_max_shape_id=last_shape_id
        last_shape_id+=1

    def make(o, collection, defer=True):
        kind, c, st = o["render_type"], o["content"], o["style"]
        if kind=='connector' and defer:
            pending.append((o,collection));return
        reserve(collection)
        x, y, w, h = [round(v * scale) for v in o["bbox"]]
        if kind == "group":
            # python-pptx's group factory bypasses the collection ID cache and
            # scans //@id across all colour-contour coordinates. Large nested
            # photo layers can exceed libxml's XPath limits. Use the same native
            # group element with our slide-wide allocator instead.
            from pptx.oxml.shapes.groupshape import CT_GroupShape
            element=CT_GroupShape.new_grpSp(last_shape_id,o['id'])
            collection._spTree.insert_element_before(element,'p:extLst')
            s=collection._shape_factory(element)
            nested = s.shapes
            members = children_by_parent.get(o['id'],[])
            for member in members:
                make(member, nested)
            if c.get('native_asset'):
                if members:raise ValueError('Native snapshot root cannot mix stale generated children')
                from .native_asset import instantiate as import_native
                def allocate_native():
                    nonlocal last_shape_id
                    last_shape_id+=1;return last_shape_id
                import_native(s,base,c['native_asset'],[x,y,w,h],o['id'],allocate_native)
            elif not members:
                raise ValueError("Empty semantic group")
        elif kind == "shape":
            if o["semantic_type"] == "native_color_patch" and o.get("parent"):
                # GroupShapes.add_shape recomputes every child extent each time,
                # making thousands of editable paint patches quadratic. Build
                # the same native auto-shape and recalculate groups once below.
                from pptx.shapes.autoshape import AutoShapeType
                sp = collection._add_sp(AutoShapeType(PRESETS[c["preset"]]), x, y, w, h)
                s = collection._shape_factory(sp)
            else:
                s = collection.add_shape(PRESETS[c["preset"]], x, y, w, h)
            for index,value in enumerate(c.get("adjustments",[])):
                s.adjustments[index]=value
            if c.get('connection_sites'):ported_shape(s,o)
        elif kind in ("text", "equation"):
            s = collection.add_textbox(x, y, w, h)
            s.text_frame.margin_left = s.text_frame.margin_right = 0
            s.text_frame.margin_top = s.text_frame.margin_bottom = 0
            s.text_frame.word_wrap = False
            if kind == "text":
                text_body(s,c,st)
            else:
                mode=c.get('render_mode','office_math')
                equation_font=st.get('font_faces',{}).get('math',st.get('font','Cambria Math'))
                if mode=='native_runs':
                    raise ValueError('No native_runs formula fallback: use structured Office Math and inspect actual edit behavior')
                elif mode=='office_math':
                    insert_math(s, c["ast"], st.get("font_size", 20), equation_font,st.get('color'),font_policy=st.get('math_font_policy','native_math'))
                    s.text_frame.auto_size=MSO_AUTO_SIZE.NONE
                    s.text_frame.paragraphs[0].alignment={'left':PP_ALIGN.LEFT,'center':PP_ALIGN.CENTER,'right':PP_ALIGN.RIGHT}[st.get('align','center')]
                    para=s._element.find('p:txBody/a:p/a14:m/m:oMathPara',NS)
                    pr=el('m:oMathParaPr');jc=child(pr,'m:jc');jc.set('{'+NS['m']+'}val',st.get('align','center'));para.insert(0,pr)
                else:raise ValueError('Mathematical expressions require office_math')
        elif kind == "connector":
            points=connector_points(objects,o)
            s=collection.add_connector(MSO_CONNECTOR.STRAIGHT,*[round(v*scale) for v in (*points[0],*points[-1])])
            for which,method,default in [('source',s.begin_connect,3),('target',s.end_connect,1)]:
                if c.get(which) and c.get(which+'_anchor',True):
                    target=shapes[c.get(which+'_anchor_object',c[which])]
                    # Write valid native references without the library's 4-site-only geometry move.
                    nv=s._element.find('p:nvCxnSpPr/p:cNvCxnSpPr',NS)
                    child(nv,'a:stCxn' if which=='source' else 'a:endCxn',id=target.shape_id,idx=c.get(which+'_site',default))
            if c.get('points'):
                set_native_route(s,points,scale)
            ln = s._element.spPr.get_or_add_ln()
            arrow_type={'open':'arrow'}.get(c.get('arrow'),c.get('arrow','triangle'))
            if arrow_type not in ('none','triangle','stealth','diamond','oval','arrow'):
                raise ValueError('Unknown native arrow type: '+str(arrow_type))
            child(ln,"a:tailEnd",type=arrow_type,w=c.get('arrow_width','med'),len=c.get('arrow_length','med'))
            if c.get('start_arrow'):
                head=el('a:headEnd',type=c['start_arrow'],w='med',len='med')
                tail=ln.find('a:tailEnd',NS);ln.insert(ln.index(tail),head)
        elif kind=='path':
            if o['semantic_type']=='native_colour_contour' and o.get('parent'):
                from pptx.shapes.autoshape import AutoShapeType
                sp=collection._add_sp(AutoShapeType(MSO_SHAPE.RECTANGLE),x,y,w,h)
                s=collection._shape_factory(sp)
            else:s=collection.add_shape(MSO_SHAPE.RECTANGLE,x,y,w,h)
            contours=c.get('contours')
            if contours is None:
                resource=c['geometry_ref'];path=safe_path(base,resource['path'])
                if digest(path)!=resource['sha256']:raise ValueError('Geometry asset changed')
                from .common import read_json
                contours=read_json(path)['contours']
            geom=custom_geometry(s,contours,fill=st.get('fill') not in (None,'none'),
                                 bulk=o['semantic_type']=='native_colour_contour')
            if c.get('connection_sites'):
                from .geometry import add_connection_sites
                add_connection_sites(geom,c['connection_sites'])
        elif kind=='trace':
            from .common import read_json
            resource=c['geometry_ref'];path=safe_path(base,resource['path'])
            if digest(path)!=resource['sha256']:raise ValueError('Trace asset changed')
            data=read_json(path);s=collection.add_group_shape()
            for index,layer in enumerate(data['layers']):
                reserve(s.shapes)
                tone=s.shapes.add_shape(MSO_SHAPE.RECTANGLE,x,y,w,h)
                tone.name=o['id']+'.tone-'+str(index)
                custom_geometry(tone,layer['contours'],fill=True)
                shape_style(tone,{'fill':layer['fill'],'stroke':None},'path')
        elif kind == "bezier":
            s = collection.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
            sp = s._element.find("p:spPr", NS)
            sp.remove(sp.find("a:prstGeom", NS))
            geom = el("a:custGeom")
            sp.insert(1, geom)
            for tag in ("avLst", "gdLst", "ahLst", "cxnLst"):
                child(geom, "a:" + tag)
            child(geom, "a:rect", l="0", t="0", r="r", b="b")
            path = child(child(geom, "a:pathLst"), "a:path", w="100000", h="100000", fill="none")
            pts = c["points"]
            if len(pts) not in (3,4):
                raise ValueError("Quadratic/cubic Bezier needs 3/4 control points")
            child(child(path, "a:moveTo"), "a:pt", x=round(pts[0][0] * 100000), y=round(pts[0][1] * 100000))
            cubic = child(path, "a:quadBezTo" if len(pts)==3 else "a:cubicBezTo")
            for px, py in pts[1:]:
                child(cubic, "a:pt", x=round(px * 100000), y=round(py * 100000))
        elif kind == 'svg':
            from .vector_asset import validate as validate_svg, embed
            asset,fallback,info=validate_svg(c,base)
            s=embed(collection,asset,fallback,(x,y,w,h),svg_resources,content=c)
            if c.get('connection_sites'):ported_shape(s,o)
        elif kind == "photo":
            asset = safe_path(base, c["path"])
            if digest(asset) != c["sha256"]:
                raise ValueError("Photo evidence changed")
            s = collection.add_picture(str(asset), x, y, w, h)
            from .content_viewport import apply_crop
            apply_crop(s,c)
            if c.get('connection_sites'):ported_shape(s,o)
        elif kind == "table":
            rows = c["rows"]
            if hasattr(collection,'add_table'):
                s=collection.add_table(len(rows),len(rows[0]),x,y,w,h)
            else:
                # DrawingML permits native tables inside semantic groups even
                # though python-pptx exposes add_table only on SlideShapes.
                slide.shapes._cached_max_shape_id=last_shape_id-1
                s=slide.shapes.add_table(len(rows),len(rows[0]),x,y,w,h)
                collection._spTree.insert_element_before(s._element,'p:extLst')
            for i, row in enumerate(rows):
                for j, text in enumerate(row):
                    cell=s.table.cell(i,j)
                    cs={**st,**c.get("cell_styles",[[{} for _ in row] for row in rows])[i][j]}
                    cell.text=text
                    padding=cs.get('padding',0)
                    cell.margin_left=cell.margin_right=cell.margin_top=cell.margin_bottom=Pt(padding)
                    cell.vertical_anchor={'top':MSO_ANCHOR.TOP,'middle':MSO_ANCHOR.MIDDLE,'bottom':MSO_ANCHOR.BOTTOM}[cs.get('valign','middle')]
                    cell.fill.solid()
                    cell.fill.fore_color.rgb=RGBColor.from_string(cs.get("fill","FFFFFF"))
                    for paragraph in cell.text_frame.paragraphs:
                        faces=cs.get('font_faces',{})
                        primary=faces.get('latin',faces.get('ea',faces.get('cs',cs.get('font','DejaVu Sans'))))
                        paragraph.font.name=primary
                        for run in paragraph.runs:
                            props=run._r.get_or_add_rPr()
                            for script in ('latin','ea','cs'):
                                face=props.find('a:'+script,NS)
                                if face is None:face=child(props,'a:'+script)
                                face.set('typeface',faces.get(script,primary))
                        paragraph.font.size=Pt(cs.get("font_size",14))
                        paragraph.font.color.rgb=RGBColor.from_string(cs.get("color","17324D"))
                        paragraph.font.bold=cs.get('bold',False)
                        paragraph.font.italic=cs.get('italic',False)
                        paragraph.alignment={'left':PP_ALIGN.LEFT,'center':PP_ALIGN.CENTER,'right':PP_ALIGN.RIGHT}[cs.get('align','left')]
                    props=cell._tc.get_or_add_tcPr()
                    for edge_index,edge in enumerate(("lnL","lnR","lnT","lnB")):
                        border=el("a:"+edge,w=round(cs.get("line_width",1)*12700))
                        child(child(border,"a:solidFill"),"a:srgbClr",val=cs.get("stroke","17324D"))
                        child(border,"a:prstDash",val="solid")
                        props.insert(edge_index,border)
            from .tables import apply as apply_table
            apply_table(s.table,c,w,h)
        else:
            raise ValueError(f"BLOCKED: unsupported/unresolved object {o['id']}")
        s.name = o["id"]
        from .geometry import mark_geometry_contract
        mark_geometry_contract(s,o)
        if st.get('rotation'):s.rotation=st['rotation']
        shape_style(s,st,kind)
        if kind in ('path','bezier') and (c.get('arrow') or c.get('start_arrow')):
            if kind=='path' and any(part.get('closed') for part in c.get('contours',[])):
                raise ValueError('A routed line arrow requires an open native contour')
            ln=s._element.spPr.get_or_add_ln()
            for tag,value in [('tailEnd',c.get('arrow','none')),('headEnd',c.get('start_arrow','none'))]:
                value={'open':'arrow'}.get(value,value)
                if value not in ('none','triangle','stealth','diamond','oval','arrow'):raise ValueError('Unknown native line arrow')
                child(ln,'a:'+tag,type=value,w='med',len='med')
        shapes[o["id"]] = s
        mapping[o["id"]] = {"native_id": s.shape_id, "slide": 1, "versions": o["versions"], "semantic_signature": identity(o)}

    roots = [o for o in scene["objects"] if not o.get("parent")]
    # Native connections need their endpoint shapes to exist first.
    for o in [o for o in roots if o["render_type"] != "connector"] + [o for o in roots if o["render_type"] == "connector"]:
        progress('native_geometry',o['id'])
        make(o, slide.shapes)
    for obj,collection in pending:make(obj,collection,False)
    def depth(obj):
        value=0;parent=obj.get('parent')
        while parent:value+=1;parent=objects[parent].get('parent')
        return value
    for obj in sorted(scene['objects'],key=depth,reverse=True):
        if obj['render_type'] in ('group','trace') and not obj['content'].get('native_asset'):
            shapes[obj['id']].shapes._recalculate_extents()
    # Deferral resolves native endpoint references; it must not change paint
    # order. In the absence of explicit z_order, Scene order is authoritative.
    children={};indexes={}
    for index,obj in enumerate(scene['objects']):
        children.setdefault(obj.get('parent'),[]).append(obj);indexes[obj['id']]=index
    for parent in [None]+[o['id'] for o in scene['objects'] if o['render_type']=='group']:
        members=children.get(parent,[])
        tree=(slide.shapes if parent is None else shapes[parent].shapes)._spTree
        desired=[shapes[name]._element for name in semantic_order.get(parent,[])]
        native_tags={'sp','grpSp','cxnSp','pic','graphicFrame'}
        current=[e for e in tree if e.tag.rsplit('}',1)[-1] in native_tags]
        for index,element in enumerate(desired):
            if current[index] is element:continue
            # Reattaching a large unchanged group forces lxml to traverse its
            # whole geometry for namespace reconciliation. Move only mismatches.
            anchor=current[index];tree.remove(element);tree.insert(tree.index(anchor),element)
            current.remove(element);current.insert(index,element)
    with writer(output.parent):
        if output.exists() or output.with_suffix(".mapping.json").exists():
            raise FileExistsError(output)
        tmp = output.with_suffix(".pending.pptx")
        if tmp.exists() or tmp.with_name(tmp.stem+'.construction-raw.pptx').exists():
            raise FileExistsError('Owned build residue must be retained and recovered: '+str(tmp))
        progress('save_pptx')
        prs.save(tmp)
        from .candidate_cost import compact_construction
        storage=compact_construction(tmp)
        from .font_contract import finalize as finalize_fonts
        fonts=finalize_fonts(scene,tmp)
        from .office_compatibility import validate as office_compatibility
        office_compatibility(tmp)
        os.replace(tmp, output)
        record = {"implementation_version":VERSION,"implementation":implementation,"scene_hash": identity(scene), "scene_revision": scene["revision"], "pptx_hash": digest(output), "objects": mapping,"font_delivery":fonts,"construction_storage":storage}
        write_json(output.with_suffix(".mapping.json"), record)
    progress('saved')
    faulthandler.cancel_dump_traceback_later();stack.close()
    return record
