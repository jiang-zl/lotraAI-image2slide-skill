"""Typed checks against actual saved DrawingML, independent of pixel similarity."""
from copy import deepcopy
from lxml import etree as E
from .common import identity
from .mathml import NS
VERSION = 'native-core-1.31'
def intersects(a,b):
    x,y,w,h=a;u,v,s,t=b
    return x<u+s and u<x+w and y<v+t and v<y+h


def package_gate(scene,pptx):
    """Global native invariants checked once, outside per-owner pixel loops."""
    from zipfile import ZipFile
    import hashlib
    from .font_embedding import eot,FONT_REL,REL,P,R
    from .inspect import inventory
    rows=[]
    def add(key,passed):rows.append({'check_id':key,'status':'PASS' if passed else 'FAIL'})
    with ZipFile(pptx) as package:
        slides=[n for n in package.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
        add('single_declared_artboard',slides==['ppt/slides/slide1.xml'])
        present=E.fromstring(package.read('ppt/presentation.xml'))
        size=present.find('p:sldSz',NS);scale=scene['canvas']['target_width_inches']*914400/scene['canvas']['width']
        add('saved_canvas',size is not None and all(abs(int(size.get(k,'0'))-round(scene['canvas'][field]*scale))<=2 for k,field in (('cx','width'),('cy','height'))))
        nodes,duplicates=inventory(E.fromstring(package.read('ppt/slides/slide1.xml')))
        ids=[v['id'] for v in nodes.values()]
        add('native_id_uniqueness',not duplicates and len(ids)==len(set(ids)))
        add('native_owner_coverage',set(nodes)=={o['id'] for o in scene['objects']})
        bindings=scene.get('font_plan',{}).get('bindings',{})
        faces={b['resource']['id']:b['resource'] for b in bindings.values()}
        rels=E.fromstring(package.read('ppt/_rels/presentation.xml.rels'))
        font_targets={r.get('Target') for r in rels if r.get('Type')==FONT_REL}
        for key,face in faces.items():
            part='ppt/fonts/lotra-'+key[:24]+'.fntdata'
            passed=part in package.namelist() and part[4:] in font_targets
            if passed:passed=hashlib.sha256(package.read(part)).digest()==hashlib.sha256(eot(face)).digest()
            add('full_editable_font.'+key,passed)
        add('editable_font_settings',not faces or present.get('embedTrueTypeFonts')=='1' and present.get('saveSubsetFonts')=='0')
    return {'status':'PASS' if all(r['status']=='PASS' for r in rows) else 'FAIL','checks':rows}


def snapshots(pptx):
    from .inspect import xml, inventory
    nodes, duplicates = inventory(xml(pptx))
    if duplicates:
        raise ValueError('Duplicate saved native identity')
    result = {}
    orders={}
    for owner,entry in nodes.items():orders.setdefault(entry['parent'],[]).append(owner)
    for owner, entry in nodes.items():
        node = deepcopy(entry['node'])
        is_group = E.QName(node).localname == 'grpSp'
        children = [k for k, v in nodes.items() if v['parent'] == owner]
        if is_group:
            for child in list(node):
                if E.QName(child).localname in ('sp','grpSp','cxnSp','pic','graphicFrame','AlternateContent'):
                    node.remove(child)
        ancestors = []
        parent = entry['parent']
        while parent:
            ancestors.append(nodes[parent]['node'].find('p:grpSpPr', NS))
            parent = nodes[parent]['parent']
        xf = node.find('p:grpSpPr/a:xfrm' if is_group else 'p:xfrm' if E.QName(node).localname == 'graphicFrame' else 'p:spPr/a:xfrm', NS)
        placement = E.tostring(xf).decode() if xf is not None else None
        if xf is not None:
            for tag in ('off','chOff'):
                child = xf.find('a:'+tag, NS)
                if child is not None: xf.remove(child)
            # Group bounds are generated from child positions, not its body.
            if is_group:
                for tag in ('ext','chExt'):
                    child = xf.find('a:'+tag, NS)
                    if child is not None: xf.remove(child)
            if E.QName(node).localname=='cxnSp':
                # Endpoint-derived extent/flip is placement, not connector style.
                xf.getparent().remove(xf)
        props = node.find('.//p:cNvPr', NS)
        if props is not None:
            for key in ('id','name'):
                props.attrib.pop(key, None)
        result[owner] = {'body': identity([E.tostring(node).decode(), children]),
                         'placement': identity([placement, entry['parent'],orders[entry['parent']].index(owner),
                             [E.tostring(a).decode() for a in ancestors]]),
                         'node': entry['node'], 'parent': entry['parent']}
    return result


def source_checks(expected, actual, phase, tolerance):
    failures = []
    fields = ('render_type','semantic_type','content','style') if phase == 'body' else ('parent','z_order')
    for field in fields:
        wanted,got=expected.get(field),actual.get(field)
        if field=='style':
            def resolved(value):
                value=deepcopy(value)
                if value.get('font'):
                    faces=value.get('font_faces',{})
                    value['font_faces']={k:faces.get(k,value.get('math_font',value['font']) if k=='math' else value['font']) for k in ('latin','ea','cs','math')}
                return value
            wanted,got=resolved(wanted),resolved(got)
        if wanted != got:
            failures.append({'check_id': 'source_'+field, 'status': 'FAIL', 'detail': 'Frozen source property differs'})
    indexes = (2,3) if phase == 'body' else (0,1)
    if any(abs(expected['bbox'][i]-actual['bbox'][i]) > tolerance for i in indexes):
        failures.append({'check_id': 'source_'+phase+'_geometry', 'status': 'FAIL',
                         'detail': {'expected': [expected['bbox'][i] for i in indexes],
                                    'actual': [actual['bbox'][i] for i in indexes], 'tolerance_px': tolerance}})
    return failures


def style_checks(obj, node):
    """Font size/face/weight/colour are native attributes, not raster proxies."""
    rows = []
    def add(name, passed, detail=None):
        rows.append({'object_id': obj['id'], 'check_id': name, 'status': 'PASS' if passed else 'FAIL', 'detail': detail})
    style, content, kind = obj['style'], obj['content'], obj['render_type']
    def run_check(props, expected, label):
        size = expected.get('font_size', 14 if kind=='table' else 20 if kind=='equation' else 16)
        add(label+'.font_size', props is not None and int(props.get('sz',0)) == round(size*100))
        if props is None:return
        for flag in ('bold','italic'):
            add(label+'.'+flag, (props.get('b' if flag=='bold' else 'i','0') in ('1','true')) == bool(expected.get(flag,False)))
        colour = props.find('a:solidFill/a:srgbClr', NS)
        add(label+'.color', colour is not None and colour.get('val') == expected.get('color','17324D'))
        faces = expected.get('font_faces', {})
        primary = expected.get('font','DejaVu Sans')
        for script in ('latin','ea','cs'):
            face = props.find('a:'+script, NS)
            add(label+'.font_'+script, face is not None and face.get('typeface') == faces.get(script,primary))
    if kind == 'text':
        paragraphs = content.get('paragraphs') or [content.get('runs') or [{'text':content.get('text','')}]]
        actual_paragraphs = node.findall('p:txBody/a:p', NS)
        # Plain text containing newlines is serialized as multiple paragraphs.
        if 'text' in content and not content.get('paragraphs') and not content.get('runs'):
            paragraphs = [[{'text': line}] for line in content['text'].split('\n')]
        add('paragraph_count', len(paragraphs) == len(actual_paragraphs))
        for pi, (wanted, paragraph) in enumerate(zip(paragraphs,actual_paragraphs)):
            native = paragraph.findall('a:r', NS)
            ordinary = [r for r in wanted if 'ast' not in r]
            add('run_count.'+str(pi), len(native) == len(ordinary))
            for ri,(want,run) in enumerate(zip(ordinary,native)):
                run_check(run.find('a:rPr',NS), {**style,**want}, 'p%d.r%d'%(pi,ri))
        body = node.find('p:txBody/a:bodyPr', NS)
        add('text_no_autoshrink', body is not None and body.find('a:normAutofit',NS) is None)
    elif kind == 'table':
        native_rows = node.findall('a:graphic/a:graphicData/a:tbl/a:tr',NS)
        columns=node.findall('a:graphic/a:graphicData/a:tbl/a:tblGrid/a:gridCol',NS)
        xf=node.find('p:xfrm/a:ext',NS)
        for label,values,total,nodes,attribute in (
            ('rows',content.get('row_heights',[1]*len(content['rows'])),int(xf.get('cy')),native_rows,'h'),
            ('columns',content.get('column_widths',[1]*len(content['rows'][0])),int(xf.get('cx')),columns,'w')):
            used=0;wanted=[]
            for i,v in enumerate(values):
                size=total-used if i==len(values)-1 else round(total*v/sum(values));used+=size;wanted.append(size)
            add('table_'+label+'_dimensions',len(nodes)==len(wanted) and all(abs(int(n.get(attribute,'0'))-w)<=2 for n,w in zip(nodes,wanted)))
        for ri,row in enumerate(native_rows):
            for ci,cell in enumerate(row.findall('a:tc',NS)):
                selected = {**style, **content.get('cell_styles',[[{} for _ in r] for r in content['rows']])[ri][ci]}
                props = cell.find('a:txBody/a:p/a:pPr/a:defRPr',NS)
                # Table font faces are explicitly on each run, paragraph owns style.
                merged = deepcopy(props) if props is not None else E.Element('{'+NS['a']+'}rPr')
                for face in cell.findall('a:txBody/a:p/a:r/a:rPr/*',NS):
                    if E.QName(face).localname in ('latin','ea','cs'):merged.append(deepcopy(face))
                run_check(merged, selected, 'cell.%d.%d'%(ri,ci))
                fill = cell.find('a:tcPr/a:solidFill/a:srgbClr',NS)
                add('cell.%d.%d.fill'%(ri,ci), fill is not None and fill.get('val') == selected.get('fill','FFFFFF'))
                pp=cell.find('a:txBody/a:p/a:pPr',NS)
                cp=cell.find('a:tcPr',NS)
                add('cell.%d.%d.alignment'%(ri,ci),pp is not None and pp.get('algn','l')=={'left':'l','center':'ctr','right':'r'}[selected.get('align','left')]
                    and cp is not None and cp.get('anchor','ctr')=={'top':'t','middle':'ctr','bottom':'b'}[selected.get('valign','middle')])
    if kind=='equation' or kind=='text' and any('ast' in r for para in content.get('paragraphs',[content.get('runs',[])]) for r in para):
        from .mathml import math_zone
        asts=[(content['ast'],style)] if kind=='equation' else [(r['ast'],{**style,**r}) for para in content.get('paragraphs',[content.get('runs',[])]) for r in para if 'ast' in r]
        wanted=[]
        for ast,st in asts:
            math=math_zone(ast,st.get('font_size',20),st.get('font_faces',{}).get('math',st.get('math_font',st.get('font','Cambria Math'))),
                           color=st.get('color'),font_policy=st.get('math_font_policy','native_math'))
            if kind=='text':
                from .math_typography import apply
                typography={k:st[k] for k in ('bold','italic') if k in st}
                typography.update(st.get('math_typography',{}))
                math=apply(math,typography)
            wanted.extend(math.findall('.//m:r/a:rPr',NS))
        actual=node.findall('.//m:r/a:rPr',NS)
        def properties(pr):
            return {'size':pr.get('sz'),'bold':pr.get('b','0'),'italic':pr.get('i','0'),
                    'faces':[(E.QName(e).localname,e.get('typeface')) for e in pr if E.QName(e).localname in ('latin','ea','cs')],
                    'color':pr.find('a:solidFill/a:srgbClr',NS).get('val') if pr.find('a:solidFill/a:srgbClr',NS) is not None else None}
        add('native_math_style', [properties(pr) for pr in actual]==[properties(pr) for pr in wanted])
    if kind in ('shape','path','bezier','connector'):
        sp = node.find('p:spPr',NS)
        if kind != 'connector' and not style.get('gradient'):
            want = style.get('fill','A7C5DF' if kind=='shape' else None)
            fill = sp.find('a:solidFill/a:srgbClr',NS)
            add('native_fill', sp.find('a:noFill',NS) is not None if want in (None,'none') else fill is not None and fill.get('val')==want)
        line = sp.find('a:ln',NS)
        want = style.get('stroke','17324D')
        colour = line.find('a:solidFill/a:srgbClr',NS) if line is not None else None
        add('native_stroke', line is not None and (line.find('a:noFill',NS) is not None if want is None else colour is not None and colour.get('val')==want))
        if want is not None:
            add('native_line_width', line is not None and int(line.get('w',0))==round(style.get('line_width',1.5)*12700))
        if line is not None:
            dash=line.find('a:prstDash',NS)
            add('native_dash',(dash.get('val') if dash is not None else 'solid')==style.get('dash','solid'))
        alpha=sp.find('a:solidFill/a:srgbClr/a:alpha',NS)
        if style.get('fill') not in (None,'none'):
            add('native_fill_opacity',(int(alpha.get('val')) if alpha is not None else 100000)==round(style.get('fill_alpha',1)*100000))
        if style.get('gradient'):
            colors = [c.get('val') for c in sp.findall('a:gradFill/a:gsLst/a:gs/a:srgbClr',NS)]
            add('native_gradient_palette', colors == style['gradient'])
            positions=[int(c.get('pos')) for c in sp.findall('a:gradFill/a:gsLst/a:gs',NS)]
            expected=style.get('gradient_positions',[i/(len(colors)-1) for i in range(len(colors))])
            add('native_gradient_stops',positions==[round(v*100000) for v in expected])
    if kind=='photo':
        crop=node.find('p:blipFill/a:srcRect',NS)
        wanted=content.get('viewport',{}).get('native_crop',[0,0,0,0])
        actual=[int(crop.get(k,'0'))/100000 if crop is not None else 0 for k in ('l','t','r','b')]
        add('native_photo_crop',all(abs(a-b)<=.00001 for a,b in zip(actual,wanted)))
    return rows


def batch_check(scene, expected, task, pptx, owners, phase):
    from .native_core_inspect import check, xml, inventory
    report = check(scene, task, pptx, owners=set(owners), phase=phase, validated=True)
    saved, _ = inventory(xml(pptx))
    wanted = {o['id']:o for o in expected['objects']}
    actual = {o['id']:o for o in scene['objects']}
    if phase=='placement':
        from .semantic_composition import compile_order
        paint_order=compile_order(scene)
    result = {}
    for owner in owners:
        checks = [c for c in report['checks'] if c['object_id']==owner]
        if owner not in wanted or owner not in actual or owner not in saved:
            checks.append({'check_id':'inventory','status':'FAIL'})
        else:
            precision = wanted[owner].get('acceptance', {}).get('geometry_tolerance_px', expected['canvas']['width']/1000)
            checks += source_checks(wanted[owner],actual[owner],phase,precision)
            if phase=='placement':
                siblings=[k for k,v in saved.items() if v['parent']==saved[owner]['parent']]
                expected_siblings=paint_order.get(actual[owner].get('parent'),[])
                checks.append({'check_id':'native_layer_order','status':'PASS' if siblings==expected_siblings else 'FAIL'})
            if phase=='body':
                checks += style_checks(actual[owner],saved[owner]['node'])
                obj=actual[owner]
                if obj['render_type'] not in ('group','connector'):
                    xf=saved[owner]['node'].find('p:xfrm' if obj['render_type']=='table' else 'p:spPr/a:xfrm',NS)
                    ext=xf.find('a:ext',NS) if xf is not None else None
                    scale=round(scene['canvas']['target_width_inches']*914400)/scene['canvas']['width']
                    passed=ext is not None and all(abs(int(ext.get(k))-round(v*scale))<=2 for k,v in zip(('cx','cy'),obj['bbox'][2:]))
                    checks.append({'check_id':'saved_dimensions','status':'PASS' if passed else 'FAIL'})
        result[owner] = {'status':'PASS' if checks and all(c['status']=='PASS' for c in checks) else 'FAIL',
                         'owner':owner,'phase':phase,'checks':checks,'policy':VERSION}
    return result


def relations_check(scene, relations):
    objects={o['id']:o for o in scene['objects']}
    rows=[]
    tolerance=scene['canvas']['width']/1000
    for relation in relations:
        owners=relation['owners'];kind=relation['kind']
        passed=all(k in objects for k in owners)
        if passed:
            a,b=[objects[k] for k in owners[:2]];x,y,w,h=a['bbox'];u,v,s,t=b['bbox']
            if kind=='contains':passed=u>=x-tolerance and v>=y-tolerance and u+s<=x+w+tolerance and v+t<=y+h+tolerance
            elif kind=='align_x':passed=abs((x+w/2)-(u+s/2))<=tolerance
            elif kind=='align_y':passed=abs((y+h/2)-(v+t/2))<=tolerance
            elif kind=='separate':passed=not intersects(a['bbox'],b['bbox'])
            elif kind=='above':passed=y+h<=v+tolerance
            elif kind=='left_of':passed=x+w<=u+tolerance
            elif kind=='connects':
                c=objects[relation['connector']]['content']
                passed=c.get('source')==owners[0] and c.get('target')==owners[1]
            elif kind=='layer_before':
                order={o['id']:i for i,o in enumerate(scene['objects'])}
                passed=(a.get('z_order',order[a['id']]),order[a['id']])<(b.get('z_order',order[b['id']]),order[b['id']])
            elif kind=='label_for':passed=a['content'].get('text')==relation['text'] and b['id']==relation['target']
            elif kind=='intentional_overlap':passed=True
            else:raise ValueError('Unsupported semantic relation '+kind)
        rows.append({'id':relation['id'],'status':'PASS' if passed else 'FAIL','kind':kind,'owners':owners})
    return rows
