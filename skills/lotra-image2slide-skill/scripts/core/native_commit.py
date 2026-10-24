"""Merge authorized native fields onto the existing PPTX package.

Unrelated ZIP parts and shape subtrees are inherited byte-for-byte. Native
resources are not silently imported; richer media edits use the existing
picture/edit bridge. A candidate is never itself the authoritative baseline.
"""
import copy
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from .common import digest, write_json
from .mathml import NS,el

SHAPES = {'sp','grpSp','cxnSp','graphicFrame','pic'}
SLOT = {'geometry': ('prstGeom','custGeom'), 'fill': ('solidFill','noFill','gradFill','pattFill','grpFill'),
        'line': ('ln',), 'effects': ('effectLst','effectDag','scene3d','sp3d')}


def donor_scene(scene,allowed):
    """Build only authorized donor nodes and coordinate/endpoint dependencies.

    This is never the delivered page. Unedited illustrations stay in the real
    baseline ZIP. Empty coordinate groups use an invisible donor-only envelope.
    """
    objects={o['id']:o for o in scene['objects']};selected={n for n in allowed if n in objects}
    if not selected:
        selected={next(o['id'] for o in scene['objects'] if not o.get('parent'))}
    for name in list(selected):
        if allowed.get(name) in (['add'],['replace_component']) and objects[name]['render_type'] in ('group','trace'):
            pending=[name]
            while pending:
                parent=pending.pop();children=[o['id'] for o in scene['objects'] if o.get('parent')==parent]
                selected.update(children);pending.extend(c for c in children if objects[c]['render_type']=='group')
    # A paint-order donor needs the unchanged next native sibling as a
    # read-only anchor. A donor containing only the moving shape would
    # incorrectly imply that it belongs at the end of its parent.
    order = scene['objects']
    for name, fields in allowed.items():
        if 'paint_order' not in fields or name not in objects:continue
        position=next(i for i,o in enumerate(order) if o['id']==name)
        parent=objects[name].get('parent')
        anchor=next((o['id'] for o in order[position+1:]
                     if o.get('parent')==parent and allowed.get(o['id'])!=['remove']),None)
        if anchor:selected.add(anchor)
    while True:
        previous=set(selected)
        for name in list(selected):
            obj=objects[name]
            if obj.get('parent'):selected.add(obj['parent'])
            if obj['render_type']=='connector':
                selected.update(obj['content'][f] for f in ('source','target','source_anchor_object','target_anchor_object') if obj['content'].get(f))
        if selected==previous:break
    raw=[copy.deepcopy(o) for o in scene['objects'] if o['id'] in selected]
    from .recipes import node
    for obj in list(raw):
        if obj['render_type']=='group' and not obj['content'].get('native_asset') and not any(o.get('parent')==obj['id'] for o in raw):
            raw.append(node(obj['id']+'__donor_envelope','shape',obj['bbox'],{'preset':'rect'},obj['id'],
                            'donor_coordinate_envelope',fill=None,stroke=None))
    result=copy.deepcopy(scene);result['objects']=raw
    # The authoritative candidate was compiled before filtering this private
    # donor. Missing non-target nodes must not trigger another frame compile.
    result.pop('frame_plan',None)
    result['relations']=[r for r in scene['relations'] if r['source'] in selected and r['target'] in selected]
    return result


def _tag(node):
    return E.QName(node).localname


def _props(node):
    return node.find('.//p:cNvPr', NS)


def _nodes(tree):
    result = {}
    for node in tree.iter(*('{'+NS['p']+'}'+tag for tag in SHAPES)):
        props = _props(node)
        name = props.get('name')
        if name in result:
            raise ValueError('Ambiguous native name; synchronize object mapping first: ' + name)
        result[name] = node
    return result


def _sp(node):
    return node.find('p:grpSpPr' if _tag(node)=='grpSp' else 'p:spPr', NS)


def _copy_slot(target, donor, names):
    a, b = _sp(target), _sp(donor)
    if a is None or b is None:
        raise ValueError('Unsupported native property')
    index = next((i for i,n in enumerate(a) if _tag(n) in names), len(a))
    for node in list(a):
        if _tag(node) in names:
            a.remove(node)
    for node in b:
        if _tag(node) in names:
            a.insert(index, copy.deepcopy(node)); index += 1


NATIVE_LEAF_FIELDS=frozenset(('group_translate','style.math_font_policy','style.color',
    'style.text_outline_width_pt','style.text_outline_alpha','style.font_size','style.font','style.bold','style.italic',
    'style.char_spacing_pt','style.line_spacing','style.line_spacing_pt','style.align','style.valign','fill_color','line_color','style.line_width','style.stroke',
    'style.line_cap','style.line_join','style.line_compound','style.dash','style.custom_dash','style.gradient','style.gradient_angle','geometry','fill','line',
    'effects','style.fill','rotation','style.rotation','bbox.left','bbox.top','bbox.width',
    'bbox.height','text_content','text_body','equation','connector','replace_native','table_text','style.fill_alpha','style.stroke_alpha','style.gradient_positions'))

def _table_cell_field(field):
    import re
    match=re.fullmatch(r'table_cell_format\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)',field)
    return tuple(map(int,match.groups())) if match else None


def _field_order(fields):
    # An explicit text-body grant may change paragraph/run topology. Install
    # that authorized body before applying its accompanying font/alignment
    # leaves. Without this grant the existing topology guards remain binding.
    return (['text_body']+[field for field in fields if field!='text_body']
            if 'text_body' in fields else list(fields))


def _field(target, donor, field):
    selected=_table_cell_field(field)
    if field not in NATIVE_LEAF_FIELDS and selected is None:
        raise ValueError('Unsupported or overly broad property grant: '+str(field))
    if field in ('style.fill_alpha','style.stroke_alpha'):
        a,b=_sp(target),_sp(donor)
        if field=='style.stroke_alpha':a,b=a.find('a:ln',NS),b.find('a:ln',NS)
        if a is None or b is None:raise ValueError('Existing native opacity domain missing')
        old=a.findall('a:solidFill/*',NS);new=b.findall('a:solidFill/*',NS)
        if len(old)!=1 or len(new)!=1:raise ValueError('Scoped opacity requires an existing solid fill')
        for alpha in old[0].findall('a:alpha',NS):old[0].remove(alpha)
        alpha=new[0].find('a:alpha',NS)
        if alpha is not None:old[0].append(copy.deepcopy(alpha))
        return
    if field=='style.gradient_positions':
        a=_sp(target).findall('a:gradFill/a:gsLst/a:gs',NS);b=_sp(donor).findall('a:gradFill/a:gsLst/a:gs',NS)
        if len(a)!=len(b) or not a:raise ValueError('Gradient stops must retain topology')
        for old,new in zip(a,b):old.set('pos',new.get('pos'))
        return
    if field=='table_text':
        old,new=target.findall('.//a:tbl//a:t',NS),donor.findall('.//a:tbl//a:t',NS)
        if len(old)!=len(new):raise ValueError('Changed table topology requires whole-component authority')
        for a,b in zip(old,new):a.text=b.text
        return
    if field in ('style.align','style.valign'):
        bodies=[n.find('p:txBody',NS) for n in (target,donor)]
        if any(body is None for body in bodies):
            raise ValueError('Grant exact text alignment only on an existing native text body')
        old,new=bodies
        if field=='style.valign':
            a,b=old.find('a:bodyPr',NS),new.find('a:bodyPr',NS)
            if a is None or b is None:raise ValueError('Native text anchoring absent')
            for name in ('anchor','anchorCtr'):
                if name in b.attrib:a.set(name,b.get(name))
                else:a.attrib.pop(name,None)
        else:
            oldp,newp=old.findall('a:p',NS),new.findall('a:p',NS)
            if len(oldp)!=len(newp):raise ValueError('Align preserves native paragraph topology')
            for a,b in zip(oldp,newp):
                ap,bp=a.find('a:pPr',NS),b.find('a:pPr',NS)
                if ap is None:ap=E.Element('{'+NS['a']+'}pPr');a.insert(0,ap)
                if bp is not None and bp.get('algn') is not None:ap.set('algn',bp.get('algn'))
                else:ap.attrib.pop('algn',None)
        return
    if selected is not None:
        row,column=selected;tables=[n.find('.//a:tbl',NS) for n in (target,donor)]
        if any(t is None for t in tables):raise ValueError('Cell formatting needs the existing native table')
        cells=[]
        for table in tables:
            rows=table.findall('a:tr',NS)
            if row>=len(rows):raise ValueError('Granted native row absent')
            cols=rows[row].findall('a:tc',NS)
            if column>=len(cols):raise ValueError('Granted native column absent')
            cells.append(cols[column])
        old,new=cells;oldp=old.findall('a:txBody/a:p',NS);newp=new.findall('a:txBody/a:p',NS)
        if len(oldp)!=len(newp) or [n.text for n in old.findall('.//a:t',NS)]!=[n.text for n in new.findall('.//a:t',NS)]:
            raise ValueError('Native cell formatting preserves exact text and paragraph topology')
        for a,b in zip(oldp,newp):
            props=a.find('a:pPr',NS);fresh=b.find('a:pPr',NS)
            if props is not None:a.remove(props)
            if fresh is not None:a.insert(0,copy.deepcopy(fresh))
            ar,br=a.findall('a:r',NS),b.findall('a:r',NS)
            if len(ar)!=len(br):raise ValueError('Cell formatting preserves native run topology')
            for run,other in zip(ar,br):
                props=run.find('a:rPr',NS);fresh=other.find('a:rPr',NS)
                if props is not None:run.remove(props)
                if fresh is not None:run.insert(0,copy.deepcopy(fresh))
        props,fresh=old.find('a:tcPr',NS),new.find('a:tcPr',NS)
        if props is None or fresh is None:raise ValueError('Existing native cell format missing')
        for key in ('anchor','marL','marR','marT','marB'):
            if fresh.get(key) is None:props.attrib.pop(key,None)
            else:props.set(key,fresh.get(key))
        for tag in ('lnL','lnR','lnT','lnB','solidFill','noFill','gradFill'):
            for node in props.findall('a:'+tag,NS):props.remove(node)
            for node in fresh.findall('a:'+tag,NS):props.append(copy.deepcopy(node))
        return
    if field=='group_translate':
        if _tag(target)!='grpSp' or _tag(donor)!='grpSp':raise ValueError('Group translation needs saved groups')
        a,b=_sp(target).find('a:xfrm/a:off',NS),_sp(donor).find('a:xfrm/a:off',NS)
        for k in ('x','y'):a.set(k,b.get(k))
        return
    if field=='style.math_font_policy':
        old=target.findall('.//m:r',NS);new=donor.findall('.//m:r',NS)
        if not old or len(old)!=len(new) or [r.findtext('m:t',namespaces=NS) for r in old]!=[r.findtext('m:t',namespaces=NS) for r in new]:
            raise ValueError('Typeface policy preserves exact native tokens and run topology')
        for a,b in zip(old,new):
            ap,bp=a.find('a:rPr',NS),b.find('a:rPr',NS)
            if ap is None or bp is None:raise ValueError('Typeface policy needs native run properties')
            if 'i' in bp.attrib:ap.set('i',bp.get('i'))
            else:ap.attrib.pop('i',None)
            ar,br=a.find('m:rPr',NS),b.find('m:rPr',NS)
            an=None if ar is None else ar.find('m:nor',NS)
            bn=None if br is None else br.find('m:nor',NS)
            if an is not None:ar.remove(an)
            if bn is not None:
                if ar is None:ar=E.Element('{'+NS['m']+'}rPr');a.insert(0,ar)
                ar.append(copy.deepcopy(bn))
        return
    if field in ('style.line_spacing','style.line_spacing_pt'):
        old=target.findall('p:txBody/a:p',NS);new=donor.findall('p:txBody/a:p',NS)
        if not old or len(old)!=len(new) or [''.join(p.itertext()) for p in old]!=[''.join(p.itertext()) for p in new]:
            raise ValueError('Native line spacing preserves exact paragraph text/count')
        for a,b in zip(old,new):
            props=a.find('a:pPr',NS)
            if props is None:props=el('a:pPr');a.insert(0,props)
            for child in props.findall('a:lnSpc',NS):props.remove(child)
            spacing=b.find('a:pPr/a:lnSpc',NS)
            if spacing is not None:props.insert(0,copy.deepcopy(spacing))
        return
    if field=='style.color':
        color=donor.find('.//a:rPr/a:solidFill/a:srgbClr',NS)
        if color is None:color=donor.find('.//a:defRPr/a:solidFill/a:srgbClr',NS)
        if color is None:raise ValueError('Native text colour needs an explicit RGB donor')
        value=color.get('val')
        for props in target.xpath('.//a:rPr | .//a:defRPr | .//a:endParaRPr',namespaces=NS):
            fill=props.find('a:solidFill',NS)
            if fill is None:fill=el('a:solidFill');props.insert(0,fill)
            rgb=fill.find('a:srgbClr',NS)
            if rgb is None:rgb=el('a:srgbClr');fill.append(rgb)
            rgb.set('val',value)
        paragraph=target.find('p:txBody/a:p',NS)
        if paragraph is not None and paragraph.find('a14:m',NS) is not None:
            pr=paragraph.find('a:pPr',NS)
            if pr is None:pr=el('a:pPr');paragraph.insert(0,pr)
            default=pr.find('a:defRPr',NS)
            if default is None:default=el('a:defRPr');pr.append(default)
            fill=default.find('a:solidFill',NS)
            if fill is None:fill=el('a:solidFill');default.insert(0,fill)
            rgb=fill.find('a:srgbClr',NS)
            if rgb is None:rgb=el('a:srgbClr');fill.append(rgb)
            rgb.set('val',value)
        return
    if field=='style.text_outline_alpha':
        old=target.findall('.//a:rPr',NS);new=donor.findall('.//a:rPr',NS)
        if len(old)!=len(new) or not old:raise ValueError('Keep actual native text run topology')
        for a,b in zip(old,new):
            current=a.find('a:ln/a:solidFill/a:srgbClr',NS)
            proposed=b.find('a:ln/a:solidFill/a:srgbClr',NS)
            if current is None or proposed is None:raise ValueError('Outline opacity needs an existing native outline')
            for node in current.findall('a:alpha',NS):current.remove(node)
            alpha=proposed.find('a:alpha',NS)
            if alpha is not None:current.append(copy.deepcopy(alpha))
        return
    if field=='style.text_outline_width_pt':
        old=target.findall('.//a:rPr',NS);new=donor.findall('.//a:rPr',NS)
        if len(old)!=len(new) or not old:raise ValueError('Keep native text run topology')
        for a,b in zip(old,new):
            for prior in a.findall('a:ln',NS):a.remove(prior)
            outline=b.find('a:ln',NS)
            if outline is not None:a.insert(0,copy.deepcopy(outline))
        return
    if field in ('style.font_size','style.font','style.bold','style.italic','style.char_spacing_pt'):
        old=target.findall('.//a:rPr',NS);new=donor.findall('.//a:rPr',NS)
        if len(old)!=len(new) or not old:
            raise ValueError('Text leaf edit needs unchanged native run topology')
        attr={'style.font_size':'sz','style.bold':'b','style.italic':'i','style.char_spacing_pt':'spc'}.get(field)
        default_pairs=list(zip(target.findall('.//a:defRPr',NS),donor.findall('.//a:defRPr',NS)))
        for a,b in list(zip(old,new))+default_pairs:
            if attr:
                if attr in b.attrib:a.set(attr,b.get(attr))
                else:a.attrib.pop(attr,None)
            elif field=='style.font':
                for script in ('latin','ea','cs'):
                    aa,bb=a.find('a:'+script,NS),b.find('a:'+script,NS)
                    if bb is None:continue
                    if aa is None:a.append(copy.deepcopy(bb))
                    else:aa.set('typeface',bb.get('typeface'))
            else:
                aa,bb=a.find('a:solidFill/a:srgbClr',NS),b.find('a:solidFill/a:srgbClr',NS)
                if aa is None or bb is None:raise ValueError('Text color leaf needs solid RGB')
                aa.set('val',bb.get('val'))
        if field=='style.font_size':
            # Office/LibreOffice math layout also reads the paragraph ending
            # font size. Keeping it at the old size can defeat an authorized
            # OMML run-size repair while the XML run itself appears updated.
            for a,b in zip(target.findall('.//a:endParaRPr',NS),donor.findall('.//a:endParaRPr',NS)):
                if b.get('sz') is not None:a.set('sz',b.get('sz'))
        return
    if field in ('fill_color','line_color','style.line_width','style.stroke'):
        a,b=_sp(target),_sp(donor)
        if field in ('line_color','style.line_width','style.stroke'):
            a,b=a.find('a:ln',NS),b.find('a:ln',NS)
        if a is None or b is None:
            raise ValueError('Native color/line leaf missing')
        if field=='style.stroke' and b.find('a:noFill',NS) is not None:
            for child in list(a):
                if _tag(child) in ('solidFill','noFill','gradFill','pattFill'):a.remove(child)
            a.insert(0,copy.deepcopy(b.find('a:noFill',NS)))
            return
        if field=='style.line_width':
            a.set('w',b.get('w','0'))
        else:
            a,b=a.find('a:solidFill/a:srgbClr',NS),b.find('a:solidFill/a:srgbClr',NS)
            if a is None or b is None:
                raise ValueError('Color-only edit must retain a solid RGB fill')
            a.set('val',b.get('val'))
        return
    if field in ('style.line_cap','style.line_compound'):
        a,b=_sp(target).find('a:ln',NS),_sp(donor).find('a:ln',NS)
        if a is None or b is None:raise ValueError('Native line cap needs an existing line')
        attr='cap' if field=='style.line_cap' else 'cmpd'
        if b.get(attr) is None:a.attrib.pop(attr,None)
        else:a.set(attr,b.get(attr))
        return
    if field in ('style.dash','style.custom_dash','style.line_join'):
        a,b=_sp(target).find('a:ln',NS),_sp(donor).find('a:ln',NS)
        if a is None or b is None:raise ValueError('Native dash requires an existing line')
        slots=('round','bevel','miter') if field=='style.line_join' else ('prstDash','custDash')
        for tag in slots:
            old=a.find('a:'+tag,NS)
            if old is not None:a.remove(old)
        new=next((b.find('a:'+tag,NS) for tag in slots if b.find('a:'+tag,NS) is not None),None)
        before=next((i for i,item in enumerate(a) if item.tag.rsplit('}',1)[-1] in ('headEnd','tailEnd','extLst')),len(a))
        if new is not None:a.insert(before,copy.deepcopy(new))
        return
    if field in ('style.gradient','style.gradient_angle'):
        _field(target,donor,'fill');return
    if field in ('geometry','fill','line','effects'):
        _copy_slot(target,donor,SLOT[field]); return
    aliases = {'style.fill':'fill'}
    if field in aliases:
        _field(target,donor,aliases[field]); return
    if field == 'rotation' or field == 'style.rotation' or field.startswith('bbox.'):
        a=target.find('p:xfrm',NS) if _tag(target)=='graphicFrame' else _sp(target).find('a:xfrm',NS)
        b=donor.find('p:xfrm',NS) if _tag(donor)=='graphicFrame' else _sp(donor).find('a:xfrm',NS)
        if a is None or b is None:
            raise ValueError('Explicit group transform operation required')
        if field in ('rotation','style.rotation'):
            if b.get('rot') is None:
                a.attrib.pop('rot',None)
            else:
                a.set('rot',b.get('rot'))
        else:
            spec={'bbox.left':('off','x'),'bbox.top':('off','y'),
                  'bbox.width':('ext','cx'),'bbox.height':('ext','cy')}
            element,attr=spec[field]
            a.find('a:'+element,NS).set(attr,b.find('a:'+element,NS).get(attr))
        return
    if field == 'text_content':
        old = target.findall('.//a:t',NS); new = donor.findall('.//a:t',NS)
        if len(old) != len(new):
            raise ValueError('Text run topology changed; explicit text_body grant required')
        for a,b in zip(old,new):
            a.text=b.text
        return
    if field == 'text_body':
        old, new=target.find('p:txBody',NS), donor.find('p:txBody',NS)
        if old is None or new is None:
            raise ValueError('Native text body missing')
        target.replace(old,copy.deepcopy(new)); return
    if field == 'equation':
        old=target.find('.//a14:m',NS); new=donor.find('.//a14:m',NS)
        if old is None or new is None:
            marker='lotraAI native equation: editable formatted text runs'
            if marker not in (_props(target).get('descr',''),_props(donor).get('descr','')):
                raise ValueError('Native equation representation is not compiler-owned')
            oldbody,newbody=target.find('p:txBody',NS),donor.find('p:txBody',NS)
            if oldbody is None or newbody is None:raise ValueError('Native equation body missing')
            target.replace(oldbody,copy.deepcopy(newbody))
            _props(target).set('descr',_props(donor).get('descr',''))
            return
        old.getparent().replace(old,copy.deepcopy(new)); return
    if field == 'connector':
        if _tag(target)!='cxnSp' or _tag(donor)!='cxnSp':
            raise ValueError('Connector grant requires native connectors at both ends')
        a=target.find('p:nvCxnSpPr/p:cNvCxnSpPr',NS)
        b=donor.find('p:nvCxnSpPr/p:cNvCxnSpPr',NS)
        for n in list(a):a.remove(n)
        for n in b:a.append(copy.deepcopy(n))
        _copy_slot(target,donor,SLOT['geometry'])
        # Connector content owns its declared arrowheads as well as its route.
        # Keep line colour/width/dash untouched: copy only head/tail subnodes.
        line=_sp(target).find('a:ln',NS);incoming=_sp(donor).find('a:ln',NS)
        if line is None or incoming is None:raise ValueError('Native connector line missing')
        for tag in ('headEnd','tailEnd'):
            for prior in line.findall('a:'+tag,NS):line.remove(prior)
        index=next((i for i,n in enumerate(line) if _tag(n)=='extLst'),len(line))
        for tag in ('headEnd','tailEnd'):
            arrow=incoming.find('a:'+tag,NS)
            if arrow is not None:line.insert(index,copy.deepcopy(arrow));index+=1
        # The complete transform is derived route geometry, including its
        # endpoints' off/ext. Copying only flags puts a repaired route inside
        # the previous box. Parent axes were verified before this scoped merge.
        ax,bx=_sp(target).find('a:xfrm',NS),_sp(donor).find('a:xfrm',NS)
        if ax is None or bx is None:raise ValueError('Native connector route transform is missing')
        ax.getparent().replace(ax,copy.deepcopy(bx))
        return
    if field == 'replace_native':
        # Explicit whole-part grant, still preserving its identity and position
        # in the actual baseline tree. Caller must target one semantic part.
        if _tag(donor) not in ('sp','cxnSp') or _tag(target) not in ('sp','cxnSp'):
            raise ValueError('Whole groups/resources require a dedicated scoped operation')
        name,sid=_props(target).get('name'),_props(target).get('id')
        fresh=copy.deepcopy(donor)
        _props(fresh).set('name',name); _props(fresh).set('id',sid)
        target.getparent().replace(target,fresh); return
    raise ValueError('Unsupported or overly broad property grant: ' + field)


def merge_native(baseline, donor, allowed, output):
    if not allowed or not isinstance(allowed, dict):
        raise ValueError('Nonempty native field grants required')
    baseline,donor,output=Path(baseline),Path(donor),Path(output)
    if output.exists():
        raise FileExistsError(output)
    with ZipFile(baseline) as base, ZipFile(donor) as incoming:
        parts={i.filename:base.read(i.filename) for i in base.infolist()}
        from .native_input import physical_canvas,same_canvas
        if not same_canvas(physical_canvas(parts['ppt/presentation.xml']),
                           physical_canvas(incoming.read('ppt/presentation.xml'))):
            raise ValueError('Native donor canvas differs')
        slide_part='ppt/slides/slide1.xml'
        tree=E.fromstring(parts[slide_part]); fresh=E.fromstring(incoming.read(slide_part))
        old_nodes,new_nodes=_nodes(tree),_nodes(fresh)
        # A builder may recompute a group's bounds after changing a tiny child.
        # That must not move the rotation centre or silently rescale satisfied
        # siblings. Stage common groups in the baseline's coordinate frame;
        # only explicitly granted parent rotation is adopted from the donor.
        for key,old in old_nodes.items():
            new=new_nodes.get(key)
            if new is None or _tag(old)!='grpSp' or _tag(new)!='grpSp' or allowed.get(key)==['replace_component']:continue
            a,b=_sp(old).find('a:xfrm',NS),_sp(new).find('a:xfrm',NS)
            if a is None or b is None:raise ValueError('Group coordinate frame missing')
            if set(allowed.get(key,[])) & {'rotation','style.rotation'}:
                if b.get('rot') is None:a.attrib.pop('rot',None)
                else:a.set('rot',b.get('rot'))
            staged=copy.deepcopy(a)
            if 'group_translate' in allowed.get(key,[]):
                off=staged.find('a:off',NS);incoming_offset=b.find('a:off',NS)
                for k in ('x','y'):off.set(k,incoming_offset.get(k))
            for field in allowed.get(key,[]):
                if field.startswith('bbox.'):
                    tag,attr={'bbox.left':('off','x'),'bbox.top':('off','y'),'bbox.width':('ext','cx'),'bbox.height':('ext','cy')}[field]
                    staged.find('a:'+tag,NS).set(attr,b.find('a:'+tag,NS).get(attr))
            b.getparent().replace(b,staged)
        existing_ids={int(_props(n).get('id')) for n in old_nodes.values()}
        # Reserve space for donor subtree replacements before subsequent additions.
        next_id=max(existing_ids,default=1)+len(new_nodes)+1
        changes=[]; added_names=set(); removed_names=set(); regrouped_names=set()
        # Structured JSON can reorder grants alphabetically. Create a new
        # semantic envelope before its explicit existing-member reparent
        # fields; mutations depend on native structure, never dict ordering.
        regroup_roots={name for name,fields in allowed.items() if fields==['add']
                       and name in new_nodes and _tag(new_nodes[name])=='grpSp'
                       and any(member in old_nodes and ('reparent' in allowed.get(member,[]) or allowed.get(member)==['replace_component'])
                               for member in _nodes(new_nodes[name]))}
        ordered=list(allowed.items())
        def mutation_order(item):
            name,fields=item
            node=new_nodes.get(name) if fields==['add'] else old_nodes.get(name)
            depth=len(list(node.iterancestors())) if node is not None else 0
            return (0 if name in regroup_roots else 1 if fields==['add'] else 2 if fields==['replace_component'] else 3 if fields==['remove'] else 4,depth,name)
        ordered.sort(key=mutation_order)
        for target,fields in ordered:
            if not isinstance(fields,list) or not fields:
                raise ValueError('Leaf field list required')
            if fields==['add'] and target in added_names:continue
            if fields==['remove'] and target in removed_names:continue
            old,new=old_nodes.get(target),new_nodes.get(target)
            if target in regrouped_names:continue
            if fields == ['add']:
                if old is not None or new is None:
                    raise ValueError('Explicit addition needs a new donor shape')
                parent=new.getparent()
                if _tag(parent)=='spTree':
                    destination=tree.find('p:cSld/p:spTree',NS)
                else:
                    destination=old_nodes.get(_props(parent).get('name'))
                    if destination is None:
                        raise ValueError('Add the natural root rather than orphan parts')
                clone=copy.deepcopy(new)
                subtree=_nodes(clone)
                members={name:old_nodes[name] for name in subtree if name in old_nodes}
                if members:
                    # Wrap explicitly named flat siblings, inheriting their real
                    # native subtrees/IDs/resources. This is not a donor redraw.
                    if _tag(clone)!='grpSp' or any('reparent' not in allowed.get(name,[]) and allowed.get(name)!=['replace_component'] for name in members):
                        raise ValueError('Every existing grouped member needs explicit reparent authority')
                    if any(node.getparent() is not destination or _tag(node)=='grpSp' for node in members.values()):
                        raise ValueError('Regroup only declared flat siblings in their retained parent')
                    positions=sorted(list(destination).index(node) for node in members.values())
                    occupied=list(destination)[positions[0]:positions[-1]+1]
                    if any(node not in members.values() for node in occupied):
                        raise ValueError('Regroup cannot cross an unrelated paint-order sibling')
                    if any(name not in members and allowed.get(name)!=['add'] for name in subtree):
                        raise ValueError('Every new grouped node needs explicit add authority')
                    for name,node in members.items():
                        donor_node=subtree[name];retained=copy.deepcopy(node)
                        if allowed[name]==['replace_component']:
                            retained=copy.deepcopy(donor_node)
                            _props(retained).set('id',_props(node).get('id'))
                            from .native_scope import resources
                            resources(retained,incoming,parts)
                        else:
                            for field in _field_order(allowed[name]):
                                if field=='reparent':continue
                                if field=='paint_order':raise ValueError('Regroup preserves internal sibling paint order')
                                _field(retained,donor_node,field)
                        donor_node.getparent().replace(donor_node,retained)
                        changes.append({'object':name,'fields':allowed[name],'semantic_envelope':target})
                    # The retained parent coordinate axes remain identical.
                    # A non-identity donor group would rescale satisfied nodes.
                    xfrm=_sp(clone).find('a:xfrm',NS)
                    off,ext=xfrm.find('a:off',NS),xfrm.find('a:ext',NS)
                    ch_off,ch_ext=xfrm.find('a:chOff',NS),xfrm.find('a:chExt',NS)
                    if dict(off.attrib)!=dict(ch_off.attrib) or dict(ext.attrib)!=dict(ch_ext.attrib) or xfrm.get('rot'):
                        raise ValueError('Regroup needs an identity member coordinate mapping')
                    new_nodes_inside={name:node for name,node in _nodes(clone).items() if name not in members}
                    if any(_tag(node)=='graphicFrame' and node.find('a:graphic/a:graphicData/a:tbl',NS) is None for node in new_nodes_inside.values()):
                        raise ValueError('Regroup requires self-contained native tables or scoped media')
                    for name,node in new_nodes_inside.items():
                        _props(node).set('id',str(next_id));next_id+=1
                        if _tag(node)!='grpSp':
                            from .native_scope import resources
                            resources(node,incoming,parts)
                    final_inside=_nodes(clone);donor_names={_props(n).get('id'):key for key,n in new_nodes.items()}
                    fresh_names=set(new_nodes_inside)|{name for name in members if allowed[name]==['replace_component']}
                    for name in fresh_names:
                        for cx in final_inside[name].xpath('./p:nvCxnSpPr/p:cNvCxnSpPr/a:stCxn | ./p:nvCxnSpPr/p:cNvCxnSpPr/a:endCxn',namespaces=NS):
                            endpoint=donor_names.get(cx.get('id'));target_node=final_inside.get(endpoint)
                            if target_node is None:target_node=old_nodes.get(endpoint)
                            if target_node is None:raise ValueError('Regroup connector endpoint is unresolved')
                            cx.set('id',_props(target_node).get('id'))
                    # Existing connection IDs and untouched native content stay
                    # exactly as in the authoritative baseline package.
                    for node in members.values():destination.remove(node)
                    destination.insert(positions[0],clone)
                    old_nodes.update(_nodes(clone));added_names.update(new_nodes_inside);regrouped_names.update(members)
                    changes.append({'object':target,'fields':['add'],'regrouped_existing':list(members),
                                    'preservation':'existing native IDs/subtrees/resources and parent axes retained; only named leaf fields applied'})
                    continue
                if any(allowed.get(name)!=['add'] for name in subtree):
                    raise ValueError('Every added native group descendant needs explicit authorization')
                if any(_tag(n)=='graphicFrame' and n.find('a:graphic/a:graphicData/a:tbl',NS) is None for n in subtree.values()):
                    raise ValueError('Unsupported native external graphic requires a dedicated constructor')
                from .native_scope import resources
                resources(clone,incoming,parts)
                added_names.update(subtree)

                ids={}
                for node in clone.iter():
                    if _tag(node) in SHAPES:
                        props=_props(node);ids[props.get('id')]=str(next_id)
                        props.set('id',str(next_id));next_id+=1
                for connection in clone.xpath('.//a:stCxn | .//a:endCxn',namespaces=NS):
                    sid=connection.get('id')
                    if sid not in ids:
                        donor_name=next((n for n,o in new_nodes.items() if _props(o).get('id')==sid),None)
                        if donor_name not in old_nodes:
                            raise ValueError('Unknown added connector endpoint')
                        ids[sid]=_props(old_nodes[donor_name]).get('id')
                    connection.set('id',ids[sid])
                # Keep the incoming paint order using the nearest existing sibling.
                following=list(parent)[list(parent).index(new)+1:]
                anchor=next((old_nodes.get(_props(n).get('name')) for n in following
                             if _tag(n) in SHAPES and _props(n).get('name') in old_nodes),None)
                if anchor is not None and anchor.getparent() is destination:
                    destination.insert(destination.index(anchor),clone)
                else:
                    destination.append(clone)
                old_nodes.update(_nodes(clone))
            elif fields == ['remove']:
                if old is None:
                    raise ValueError('Removal target missing')
                sid=_props(old).get('id')
                subtree=_nodes(old)
                if any(allowed.get(name)!=['remove'] for name in subtree):
                    raise ValueError('Every removed native group descendant needs explicit authorization')
                removed_ids={_props(n).get('id') for n in subtree.values()}
                donor_names={_props(n).get('id'):name for name,n in new_nodes.items()}
                for name,native in list(old_nodes.items()):
                    if _tag(native)!='cxnSp':continue
                    endpoints=native.xpath('./p:nvCxnSpPr/p:cNvCxnSpPr/a:stCxn | ./p:nvCxnSpPr/p:cNvCxnSpPr/a:endCxn',namespaces=NS)
                    if not any(conn.get('id') in removed_ids for conn in endpoints):continue
                    grant=allowed.get(name,[])
                    if grant==['remove']:continue
                    if 'connector' in grant:
                        replacement=new_nodes.get(name)
                        fresh_endpoints=replacement.xpath('./p:nvCxnSpPr/p:cNvCxnSpPr/a:stCxn | ./p:nvCxnSpPr/p:cNvCxnSpPr/a:endCxn',namespaces=NS)
                        if all(donor_names.get(conn.get('id')) not in subtree for conn in fresh_endpoints):continue
                    raise ValueError('Connected node removal needs explicit endpoint repair or connector removal')
                old.getparent().remove(old)
                removed_names.update(subtree)
                for name in subtree:old_nodes.pop(name,None)
            elif fields==['replace_component']:
                if old is None or new is None:raise ValueError('Replacement target absent')
                from .native_scope import replace as scoped_replace
                regrouped_names.update(scoped_replace(old,new,old_nodes,new_nodes,allowed,incoming,parts))
            else:
                if old is None or new is None:
                    raise ValueError('Native edit target missing: '+target)
                # Parent transforms must agree before copying donor-local values.
                from .saved_components import _transform, _group_matrix
                import numpy as np
                a,b=old.getparent(),new.getparent()
                while 'reparent' not in fields and _tag(a)=='grpSp' and _tag(b)=='grpSp':
                    if not np.allclose(_group_matrix(_transform(a)),_group_matrix(_transform(b)),atol=1e-9):
                        raise ValueError('Map donor geometry to the edited parent coordinate frame first')
                    a,b=a.getparent(),b.getparent()
                for field in _field_order(fields):
                    if field=='connector':
                        donor_names={_props(n).get('id'):key for key,n in new_nodes.items()}
                        for cx in new.xpath('.//a:stCxn | .//a:endCxn',namespaces=NS):
                            key=donor_names.get(cx.get('id'))
                            if key not in old_nodes:raise ValueError('Connector endpoint must already exist or be included in the scoped addition')
                            cx.set('id',_props(old_nodes[key]).get('id'))
                    if field=='reparent':
                        parent=new.getparent()
                        destination=tree.find('p:cSld/p:spTree',NS) if _tag(parent)=='spTree' else old_nodes.get(_props(parent).get('name'))
                        if destination is None or destination is old or old in destination.iterancestors():raise ValueError('Invalid native reparent target')
                        if old.getparent() is not destination:
                            old.getparent().remove(old);destination.append(old)
                            oldxf=old.find('p:grpSpPr/a:xfrm' if _tag(old)=='grpSp' else 'p:xfrm' if _tag(old)=='graphicFrame' else 'p:spPr/a:xfrm',NS)
                            newxf=new.find('p:grpSpPr/a:xfrm' if _tag(new)=='grpSp' else 'p:xfrm' if _tag(new)=='graphicFrame' else 'p:spPr/a:xfrm',NS)
                            if oldxf is None or newxf is None:raise ValueError('Explicit reparent frame missing')
                            oldxf.getparent().replace(oldxf,copy.deepcopy(newxf))
                    elif field=='photo_resource':
                        if _tag(old)!='pic' or _tag(new)!='pic':raise ValueError('Photo resource grant requires native pictures')
                        from .native_scope import resources
                        clone=resources(copy.deepcopy(new.find('p:blipFill',NS)),incoming,parts)
                        old.replace(old.find('p:blipFill',NS),clone)
                    elif field!='paint_order':_field(old,new,field)
            changes.append({'object':target,'fields':fields})
        # Resolve explicit paint-order grants from the back, so new sibling
        # chains keep their donor order without disturbing other relative order.
        order_targets=[key for key,fields in allowed.items() if 'paint_order' in fields]
        donor_order={_props(node).get('name'):index for index,node in enumerate(fresh.iter()) if _tag(node) in SHAPES}
        for target in sorted(order_targets,key=lambda key:donor_order[key],reverse=True):
            old,new=old_nodes[target],new_nodes[target];parent=new.getparent();destination=old.getparent()
            if _tag(parent)!=_tag(destination) or (_tag(parent)=='grpSp' and _props(parent).get('name')!=_props(destination).get('name')):
                raise ValueError('Paint order cannot reparent a native object')
            siblings=list(parent);following=siblings[siblings.index(new)+1:]
            anchor=next((old_nodes.get(_props(n).get('name')) for n in following
                         if _tag(n) in SHAPES and _props(n).get('name') in old_nodes),None)
            destination.remove(old)
            if anchor is not None and anchor.getparent() is destination:destination.insert(destination.index(anchor),old)
            else:
                extension=destination.find('p:extLst',NS)
                if extension is None:destination.append(old)
                else:destination.insert(destination.index(extension),old)
        parts[slide_part]=E.tostring(tree,xml_declaration=True,encoding='UTF-8',standalone=True)
        output.parent.mkdir(parents=True,exist_ok=True)
        with ZipFile(output,'w') as merged:
            prior_names=set()
            for info in base.infolist():
                merged.writestr(info,parts[info.filename]);prior_names.add(info.filename)
            for name,data in parts.items():
                if name not in prior_names:merged.writestr(name,data)
    receipt={'status':'AUTHORIZED_NATIVE_FIELDS_MERGED','baseline':digest(baseline),
             'donor':digest(donor),'output':digest(output),'changes':changes,
             'preservation':'baseline package parts and non-target subtrees inherited'}
    write_json(output.with_suffix('.commit.json'),receipt)
    return receipt
