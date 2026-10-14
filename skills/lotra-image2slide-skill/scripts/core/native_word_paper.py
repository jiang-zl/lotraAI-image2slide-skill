"""Source-bound paper glyph repair; never changes the editable native PPT.

The caller supplies actual saved Office glyph captures, receipts and native
baselines. Current source units decide each result independently. Native text
is retained; this is a vector paper drawing/export route, not EMF playback.
"""
import copy,math
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from .common import read_json,write_json,digest,safe_path

NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}

def _artifact(task,entry):
    file=safe_path(task,entry['path'])
    if digest(file)!=entry['sha256']:raise ValueError('Native paper input artifact changed')
    return file

def _capture_baseline(task,item,name,style):
    baseline=_artifact(task,item['native_baseline']['pptx']);captured=item.get('captured_pptx')
    if not captured:return item['native_baseline']['pptx']['sha256']
    captured_file=_artifact(task,captured);augmentation=item.get('capture_outline_emu')
    if not isinstance(augmentation,int) or not 1<=augmentation<=13 or style.get('text_outline_width_pt'):
        raise ValueError('Only an explicit paper-only hairline can capture an otherwise font-dependent native word')
    with ZipFile(baseline) as original,ZipFile(captured_file) as carrier:
        if set(original.namelist())!=set(carrier.namelist()):raise ValueError('Paper glyph carrier changed package topology')
        for part in original.namelist():
            a,b=original.read(part),carrier.read(part)
            if a==b:continue
            if not part.startswith('ppt/slides/slide') or not part.endswith('.xml'):raise ValueError('Paper-only path capture cannot alter unrelated package parts')
            left=E.fromstring(a);right=E.fromstring(b);shape=next((n for n in right.findall('.//p:sp',NS) if n.find('p:nvSpPr/p:cNvPr',NS).get('name')==name),None)
            if shape is not None:
                for prop in shape.xpath('.//*[local-name()="rPr" or local-name()="defRPr"]'):
                    line=prop.find('a:ln',NS)
                    if line is None or line.get('w')!=str(augmentation):raise ValueError('Declared glyph-capture hairline changed')
                    colour=line.find('a:solidFill/a:srgbClr',NS)
                    if colour is None or colour.get('val').lower()!=style['color'].lower():raise ValueError('Capture retains original native word paint')
                    prop.remove(line)
            if E.tostring(left,method='c14n')!=E.tostring(right,method='c14n'):raise ValueError('Glyph carrier must differ only by the one declared word hairline')
    return captured['sha256']

def _load_word(task,state,candidate,item):
    from . import source_quality as q,native_word_geometry
    unit=q.unit(state,item['unit'])
    if not unit or unit['profile']!='text' or len(unit['objects'])!=1:raise ValueError('One independently bound natural native word is required')
    name=unit['objects'][0];current=read_json(_artifact(task,candidate['scene']));previous=read_json(_artifact(task,item['native_baseline']['scene']));now={o['id']:o for o in current['objects']};old={o['id']:o for o in previous['objects']}
    if now.get(name,{}).get('render_type')!='text':raise ValueError('Paper word route cannot flatten a formula/icon')
    ancestor=name
    while ancestor:
        if ancestor not in old or now[ancestor]!=old[ancestor]:raise ValueError('Cached native word or its parent frame changed')
        ancestor=now[ancestor].get('parent')
    expected_capture=_capture_baseline(task,item,name,now[name]['style']);receipt=read_json(_artifact(task,item['receipt']))
    if receipt.get('stage')!='EXPORTED' or receipt['source_pptx_hash']!=expected_capture:raise ValueError('Actual owned Office native-word receipt is required')
    own=next((w for w in receipt['words'] if w['id']==name),None)
    if own is None:raise ValueError('Native word absent from actual glyph receipt')
    emf=_artifact(task,item['emf'])
    if own['emf_sha256']!=item['emf']['sha256']:raise ValueError('Native glyph file does not match its saved capture')
    with ZipFile(_artifact(task,candidate['pptx'])) as archive:root=E.fromstring(archive.read('ppt/slides/slide1.xml'))
    shapes=[shape for shape in root.findall('.//p:sp',NS) if shape.find('p:nvSpPr/p:cNvPr',NS).get('name')==name]
    if len(shapes)!=1:raise ValueError('Exact current saved native text name is required')
    literal=''.join(shapes[0].xpath('.//a:t/text()',namespaces=NS))
    if literal!=''.join(c['literal'] for c in own['characters']):raise ValueError('Current native literal changed since glyph capture')
    from .native_source_units import points_per_source_pixel
    if points_per_source_pixel(task,state,candidate)!=points_per_source_pixel(task,state,item['native_baseline']):raise ValueError('Cached native glyph canvas changed')
    return unit,now[name],own,literal,native_word_geometry.extract(emf,now[name]['style'])

def repair(task,request):
    from . import agent_runtime as a,source_quality as q,paper_export
    from . import svg_backend as cairosvg
    import pymupdf as fitz,numpy as np
    from PIL import Image
    task,state=a._state(task);candidate=state['selected']
    if not candidate or request.get('baseline_hash')!=candidate['pptx']['sha256'] or request.get('base_native_hash')!=candidate['pptx']['sha256']:raise ValueError('Bind current selected native PPT and its declared base paper origin; output-only repair never edits it')
    descriptors=request.get('words',[])
    if not 1<=len(descriptors)<=8 or len({row['unit'] for row in descriptors})!=len(descriptors):raise ValueError('Use1..8independent original word units')
    original_pdf=_artifact(task,request['base_pdf']);original_preview=_artifact(task,request['base_preview']);output=safe_path(task,request['output'])
    if output.exists():raise ValueError('Paper drawing/export iterations remain immutable')
    output.mkdir(parents=True);units={};geometry={};slots=[];proposals=[];ns='{http://www.w3.org/2000/svg}'
    with fitz.open(original_pdf) as document:
        page=document[0];width,height=page.rect.width,page.rect.height
        chars=[c for block in page.get_text('rawdict')['blocks'] for line in block.get('lines',[]) for span in line['spans'] for c in span.get('chars',[])]
        def root_svg(groups):
            root=E.Element(ns+'svg',nsmap={None:ns[1:-1]},width=str(width)+'pt',height=str(height)+'pt',viewBox='0 0 '+str(width)+' '+str(height))
            for group in groups:root.append(copy.deepcopy(group))
            return E.tostring(root,xml_declaration=True,encoding='UTF-8')
        def word_group(name,stroke):
            group=E.Element(ns+'g',attrib={'data-native-word':name})
            for path in geometry[name]['fill_paths']:
                node=E.SubElement(group,ns+'path',d=path['d'],fill='#'+path['fill'],attrib={'fill-rule':path['fill_rule']})
                if stroke:node.set('stroke','#'+path['fill']);node.set('stroke-width',str(stroke));node.set('stroke-linejoin','round')
            for path in geometry[name].get('native_cosmetic_pattern_paths',[]):
                E.SubElement(group,ns+'path',d=path['d'],fill='#'+path['fill'],attrib={'fill-rule':path['fill_rule'],'fill-opacity':str(path['fill_opacity'])})
            return group
        def estimate(name,stroke,index):
            payload=cairosvg.svg2pdf(bytestring=root_svg([word_group(name,stroke)]));file=output/(name+'-source-weight-'+str(index)+'.png')
            with fitz.open(stream=payload,filetype='pdf') as doc:doc[0].get_pixmap(matrix=fitz.Matrix(state['source_size'][0]/width,state['source_size'][1]/height),alpha=False).save(file)
            return q.evaluate(task,state,dict(candidate,preview=a._file(task,file)),units[name])
        groups=[]
        for item in descriptors:
            unit,node,own,literal,shape=_load_word(task,state,candidate,item);name=node['id'];units[name]=unit;geometry[name]=shape
            bx,by,bw,bh=own['native_bbox_points'];ax,ay,aw,ah=own['word_advance_bounds_points'];bounds=(min(bx,ax)-1,min(by,ay)-1,max(bx+bw,ax+aw)+1,max(by+bh,ay+ah)+1)
            old_chars=[c for c in chars if bounds[0]<=c['origin'][0]<=bounds[2] and bounds[1]<=c['origin'][1]<=bounds[3]]
            if ''.join(c['c'] for c in old_chars if not c['c'].isspace())!=literal:raise ValueError('Locate exactly this old PDF word before removing any text')
            rect=[min(c['bbox'][0] for c in old_chars)-.02,min(c['bbox'][1] for c in old_chars)-.02,max(c['bbox'][2] for c in old_chars)+.02,max(c['bbox'][3] for c in old_chars)+.02]
            others=[c for c in chars if c not in old_chars and fitz.Rect(c['bbox']).intersects(fitz.Rect(rect)) and not c['c'].isspace()]
            if others:raise ValueError('Word removal would touch independently owned text; narrow the source edit first')
            rule=next((r for r in unit['metrics'] if r['id']=='foreground_mass_ratio'),None)
            if not rule or 'min' not in rule or 'max' not in rule:raise ValueError('Frozen independent source glyph mass interval is required')
            target=float(rule.get('stretch',1));maximum=min(.6,float(node['style']['font_size'])*.035)
            if not rule['min']<=target<=rule['max']:raise ValueError('Original target must remain inside its frozen mass interval')
            # Record the actual opaque geometry response, then fit only one
            # bounded output-stroke parameter. Patterned native contours keep
            # their original explicit opacity and geometry throughout.
            initial=0.0 if shape.get('native_cosmetic_pattern_paths') else float(node['style'].get('text_outline_width_pt',0));second=min(maximum,max(initial+.12,.2));samples=[]
            for stroke in (initial,second):
                measured=estimate(name,stroke,len(samples));mass=measured['values']['foreground_mass_ratio'];samples.append({'stroke_points':stroke,'mass':mass,'metric':measured})
            if samples[-1]['mass']<=samples[0]['mass']:raise ValueError('Source-weight fitting needs a positive saved vector response')
            for step in range(3):
                left,right=samples[-2:];proposal=max(0,min(maximum,right['stroke_points']+(target-right['mass'])*(right['stroke_points']-left['stroke_points'])/(right['mass']-left['mass'])))
                if any(abs(proposal-v['stroke_points'])<1e-7 for v in samples):break
                metric=estimate(name,proposal,len(samples));mass=metric['values']['foreground_mass_ratio'];samples.append({'stroke_points':proposal,'mass':mass,'metric':metric})
                if abs(mass-target)<.015:break
                if len(samples)>2 and abs(samples[-1]['mass']-samples[-2]['mass'])<1e-7:break
            good=[sample for sample in samples if sample['metric']['status']=='numeric_minimum_met']
            if not good:
                write_json(output/'unresolved-word.json',{'unit':unit['id'],'samples':samples})
                raise ValueError('Native paper glyph proposal fails its own fixed source targets: '+name)
            choice=min(good,key=lambda sample:abs(sample['mass']-target));group=word_group(name,choice['stroke_points']);groups.append(group)
            all_bounds=[p['bounds_points'] for p in shape['fill_paths']+shape.get('native_cosmetic_pattern_paths',[])];pad=choice['stroke_points']/2+.15;write_rect=[min(rect[0],min(v[0] for v in all_bounds)-pad),min(rect[1],min(v[1] for v in all_bounds)-pad),max(rect[2],max(v[2] for v in all_bounds)+pad),max(rect[3],max(v[3] for v in all_bounds)+pad)]
            if not (bounds[0]<=write_rect[0] and bounds[1]<=write_rect[1] and write_rect[2]<=bounds[2] and write_rect[3]<=bounds[3]):raise ValueError('Paper word repair escapes its actual source-bound native word owner')
            page.add_redact_annot(fitz.Rect(rect),fill=False,cross_out=False);slots.append({'unit':unit['id'],'name':name,'literal':literal,'removed_exact_old_pdf_chars':old_chars,'read_and_write_rect_points':write_rect,'quality_roi_unchanged':unit['roi'],'native_word_proof':item});proposals.append({'unit':unit['id'],'source_mass_target':target,'maximum_stroke_points':maximum,'samples':samples,'chosen':choice,'limits':'Local fixed-source sampling is proposal evidence, not full-paper acceptance or native PPT modification'})
        # Keep non-text drawings/images. A source-confirmed word can overlap a
        # neighboring native icon; a white rectangle would erase that icon.
        page.apply_redactions(images=0,graphics=0,text=0);overlay=root_svg(groups);(output/'Native-word-overlay.svg').write_bytes(overlay)
        with fitz.open(stream=cairosvg.svg2pdf(bytestring=overlay),filetype='pdf') as words:page.show_pdf_page(page.rect,words,0,keep_proportion=False,overlay=True)
        document.save(output/'Figure.pdf',garbage=4,deflate=True)
    paper_export.render_source_canvas(output/'Figure.pdf',output/'Preview-source-canvas.png',state['source_size']);paper_export._vector_svg(output/'Figure.pdf',output/'Figure.svg',[],{})
    with fitz.open(output/'Figure.pdf') as doc:doc[0].get_pixmap(matrix=fitz.Matrix(2000/doc[0].rect.width,2000/doc[0].rect.width)).save(output/'Preview.png');rasters=len(doc[0].get_images())
    before=np.array(Image.open(original_preview).convert('RGB'));after=np.array(Image.open(output/'Preview-source-canvas.png').convert('RGB'));write_mask=np.zeros(before.shape[:2],bool)
    if tuple(before.shape[:2][::-1])!=tuple(state['source_size']):raise ValueError('Base paper needs its own saved fixed original-grid preview')
    for slot in slots:
        l,t,r,b=slot['read_and_write_rect_points'];box=[max(0,math.floor(l*before.shape[1]/width)-1),max(0,math.floor(t*before.shape[0]/height)-1),min(before.shape[1],math.ceil(r*before.shape[1]/width)+1),min(before.shape[0],math.ceil(b*before.shape[0]/height)+1)];write_mask[box[1]:box[3],box[0]:box[2]]=True;slot['owned_write_pixel_window']=box
    outside=int(np.sum(np.any(before!=after,axis=2)&~write_mask));base=dict(candidate,preview=request['base_preview']);actual=dict(candidate,preview=a._file(task,output/'Preview-source-canvas.png'));part_results=[{'unit':unit['id'],'before':q.evaluate(task,state,base,unit),'after':q.evaluate(task,state,actual,unit)} for unit in units.values()]
    objects=set(units);relations=[unit for unit in state['quality']['units'].values() if unit['profile']=='relation' and any(o in objects for o in unit.get('objects',[]))];relation_results=[{'unit':unit['id'],'before':q.evaluate(task,state,base,unit),'after':q.evaluate(task,state,actual,unit)} for unit in relations]
    result={'status':'ACTUAL_NATIVE_GLYPH_PAPER_REQUIRES_SOURCE_OBSERVATION','native_selected':candidate['pptx'],'base_pdf':request['base_pdf'],'pdf':a._file(task,output/'Figure.pdf'),'svg':a._file(task,output/'Figure.svg'),'preview':actual['preview'],'embedded_raster_images':rasters,'parts':part_results,'affected_relations':relation_results,'weight_proposals':proposals,'native_word_slots':slots,'outside_owned_word_domains_changed_pixels':outside,'limits':'No native PPT/text/font changes. Native EMF glyph fills and declared partial-outline contours are source-bound proposals, not lossless replay. Original quality masks/ROIs/thresholds stay fixed; real source/typographic/spacing observation and independent relation outcomes remain required.'}
    write_json(output/'Native-word-paper.json',result)
    if outside:raise ValueError('Actual paper repair changed pixels outside its exact old/new word owners')
    return result
