"""Original formula guides and narrow native proposals; no OCR math inference."""
import copy
from pathlib import Path
from .common import read_json,write_json,digest,identity


def source_ast(unit):
    return next((f['ast'] for f in unit['features'] if f['category']=='content'
                 and f['status']=='observed' and f.get('ast')),None)


def actual_ast(task,candidate,unit):
    from .inspect import xml,inventory,parse_math_container
    from .mathml import NS
    if len(unit['objects'])!=1:return None
    file=task/candidate['pptx']['path']
    if digest(file)!=candidate['pptx']['sha256']:
        raise ValueError('Bind mathematical content to the actual saved PPTX')
    nodes,duplicates=inventory(xml(file))
    name=unit['objects'][0]
    if name in duplicates or name not in nodes:return None
    equations=nodes[name]['node'].findall('.//m:oMath',NS)
    index=unit.get('protocol',{}).get('math_span_index')
    if index is not None:
        if type(index) is not int or not 0<=index<len(equations):return None
        equations=[equations[index]]
    if len(equations)!=1:return None
    try:return parse_math_container(equations[0])
    except (ValueError,KeyError,AttributeError):return None

def native_run_evidence(task,candidate,unit,expected):
    """Legacy text rendering is not an Office equation and never passes."""
    return None


def span_evidence(task,candidate,unit,spans):
    from .inspect import xml,inventory
    from .mathml import NS
    from .common import safe_path
    file=safe_path(task,candidate['pptx']['path'])
    if digest(file)!=candidate['pptx']['sha256']:raise ValueError('Inline formula bytes changed')
    nodes,duplicates=inventory(xml(file));owner=unit['objects'][0] if len(unit['objects'])==1 else None
    if owner not in nodes or owner in duplicates:return None
    node=nodes[owner]['node'];omml=node.findall('.//m:oMath',NS)
    markers=node.findall('.//{urn:lotraai:native-math-span:1}span')
    if omml:
        values=[actual_ast(task,candidate,{**unit,'protocol':{**unit.get('protocol',{}),'math_span_index':i}}) for i in range(len(spans))]
        passed=not markers and len(omml)==len(spans) and all(v is not None for v in values) and semantic_spans(values)==semantic_spans(spans)
        return {'passed':passed,'count':len(omml),'expected_count':len(spans),'method':'actual_OMML_AST','native_ast':values}
    indices=[r.get('index') for r in markers]
    exact=set(indices)=={str(i) for i in range(len(spans))}
    values=[native_run_evidence(task,candidate,{**unit,'protocol':{**unit.get('protocol',{}),'math_span_index':i}},ast) for i,ast in enumerate(spans)]
    return {'passed':False,'count':len(set(indices)),
            'expected_count':len(spans),'method':'expected_AST_to_actual_marked_native_runs','items':values}

def semantic_spans(value):
    from .source_reading import semantic_ast
    return semantic_ast(value)


def semantic_measure(task,candidate,unit):
    # Use the same narrow Office encoding equivalence as the independently
    # reread source gate; preserve operators, case, scripts and style flags.
    from .source_reading import semantic_ast
    spans=next((f['math_spans'] for f in unit['features'] if f.get('category')=='content' and f.get('status')=='observed' and f.get('math_spans')),None)
    if spans:
        result=span_evidence(task,candidate,unit,spans)
        return float(result['passed']) if result is not None else None
    expected=source_ast(unit);actual=actual_ast(task,candidate,unit)
    if expected is None:return None
    if actual is None:
        native=native_run_evidence(task,candidate,unit,expected)
        if native is not None:return float(native['passed'])
        index=unit.get('protocol',{}).get('math_span_index')
        if index is not None and len(unit['objects'])==1:
            from .inspect import xml,inventory
            from .mathml import NS
            nodes,duplicates=inventory(xml(task/candidate['pptx']['path']));owner=unit['objects'][0]
            if owner not in duplicates and owner in nodes and type(index) is int and index>=len(nodes[owner]['node'].findall('.//m:oMath',NS)):return 0.
        return None
    return float(semantic_ast(expected)==semantic_ast(actual))


def prepare(task,request):
    """Build source corrections, retaining every earlier unit and floor."""
    import numpy as np
    from PIL import Image
    from . import agent_runtime as a,source_quality as q
    from .mathml import math_node,linear_math
    task,state=a._state(task)
    if request.get('source_hash')!=state['source']['sha256']:
        raise ValueError('Bind the immutable original formula source')
    entries=request.get('entries',[])
    if not 1<=len(entries)<=16 or len({e['unit'] for e in entries})!=len(entries):
        raise ValueError('Use at most16 distinct originally observed formulas')
    original=np.asarray(Image.open(task/state['source']['path']).convert('RGB'))
    revisions={};masks=[]
    for entry in entries:
        u=q.unit(state,entry['unit'])
        if not u or u['profile']!='formula' or not entry.get('source_evidence'):
            raise ValueError('Independently read exact original symbols, structure and glyph domain')
        ast=entry['ast'];math_node(ast)
        # Unicode script glyphs are not a substitute for mathematical structure.
        def tokens(node):
            if isinstance(node,dict):
                if node.get('op')=='token':yield node['text']
                for value in node.values():yield from tokens(value)
            elif isinstance(node,list):
                for value in node:yield from tokens(value)
        if any(any('\u2070'<=c<='\u209f' for c in value) for value in tokens(ast)):
            raise ValueError('Record mathematical sub/superscripts in the AST')
        roi=q._roi(entry['roi'],state['source_size']);word=q._roi(entry['word_roi'],state['source_size'])
        x,y,w,h=map(round,roi);wx,wy,ww,hh=map(round,word)
        if not(x<=wx and y<=wy and wx+ww<=x+w and wy+hh<=y+h):
            raise ValueError('Original formula glyph ownership must lie inside its quality window')
        data=original[y:y+h,x:x+w].astype(float)
        selector=entry.get('foreground_selector',{'mode':'neutral_dark','max_mean_rgb_255':210,'max_chroma_rgb_255':70})
        if selector.get('mode')!='neutral_dark':raise ValueError('Use explicit neutral source glyph ownership')
        mask=(data.mean(2)<selector['max_mean_rgb_255'])&(np.ptp(data,axis=2)<selector['max_chroma_rgb_255'])
        ownership=np.zeros((h,w),bool);ownership[wy-y:wy-y+hh,wx-x:wx-x+ww]=True;mask &= ownership
        if not mask.any():raise ValueError('Empty original formula glyph domain')
        directory=task/'source/formula-masks';directory.mkdir(parents=True,exist_ok=True)
        file=directory/(identity({'source':state['source']['sha256'],'roi':roi,'mask':mask.tobytes().hex()})+'.png')
        if not file.exists():Image.fromarray(mask.astype('uint8')*255).save(file)
        spec=revisions.setdefault(u['owner'],copy.deepcopy(state['quality']['specifications'][u['owner']]))
        part=next(v for v in spec['parts'] if v['id']==u['part'])
        part['roi']=roi;part['reference_mask']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
        part['protocol']={**part.get('protocol',{}),'foreground_selector':selector,'candidate_native_text_domain':True,'foreground_mass_scope':'foreground','edge_scope':'owned_foreground'}
        for feature in part['features']:
            feature['evidence']={'source_hash':state['source']['sha256'],'roi':roi,'description':entry['source_evidence']}
            if feature['category']=='content':feature.update(expected=linear_math(ast),ast=copy.deepcopy(ast),status='observed')
            if feature['category']=='typography':feature['expected']=entry['source_typography']
            if feature['category']=='placement':feature['expected']='Original visible formula ink in '+str(word)+'; preserve independent adjacent words, arrows, panel boundaries and clear gaps.'
        masks.append({'unit':u['id'],'roi':roi,'original_glyph_roi':word,'mask':part['reference_mask']})
    return {'status':'ORIGINAL_MATH_GUIDE_PROPOSALS_REQUIRE_SOURCE_CORRECTION','source_hash':state['source']['sha256'],'revisions':{owner:{'prior_spec_hash':identity(state['quality']['specifications'][owner]),'specification':spec} for owner,spec in revisions.items()},'original_domains':masks,'limits':'Host source reading is evidence, not a candidate content oracle. Submit each correction through the original-view packet. A guide is not a drawing gain.'}


def propose(task,request):
    """Fit only one source-confirmed native equation, using actual saved ink."""
    from . import agent_runtime as a,source_quality as q
    from .mathml import canonical_ast
    from zipfile import ZipFile
    import xml.etree.ElementTree as E
    task,state=a._state(task);candidate=state.get('selected')
    if not candidate or request.get('baseline_hash')!=candidate['pptx']['sha256']:
        raise ValueError('Bind the actual saved native formula baseline')
    u=q.unit(state,request['unit']);ast=source_ast(u) if u else None
    if not ast or not u.get('reference_mask') or len(u['objects'])!=1:
        raise ValueError('First confirm exact original AST and source glyph ownership')
    scene=read_json(task/candidate['scene']['path']);old=next(o for o in scene['objects'] if o['id']==u['objects'][0])
    if old['render_type']!='equation':raise ValueError('Use the independently bound native equation')
    style=request.get('source_style',{})
    if set(style)-{'font','color','math_font_policy'} or style and not request.get('source_typography_evidence'):
        raise ValueError('A native math family/colour change requires original typography evidence')
    if old['content'].get('render_mode','office_math')!='office_math':
        raise ValueError('Formatted native runs need a separate structured layout proposal')
    if style.get('math_font_policy','native_math') not in ('native_math','source_typeface','isolated_script_comma'):
        raise ValueError('Unknown native formula font policy')
    if request.get('fit_pose',True) is False:
        if not style or canonical_ast(ast)!=canonical_ast(old['content']['ast']):
            raise ValueError('Font-only proposal preserves already exact source AST')
        revised=copy.deepcopy(old);revised['style'].update(style)
        fields=['style.'+k for k,v in style.items() if old['style'].get(k)!=v]
        if style.get('math_font_policy')=='isolated_script_comma' and old['style'].get('math_font_policy')!='isolated_script_comma':
            # This explicit serialization policy splits one mixed native run;
            # a font-only field grant cannot authorize the changed topology.
            fields=['equation']+fields
        if not fields:raise ValueError('No actual source typeface policy change')
        return {'status':'SOURCE_NATIVE_MATH_PROPOSAL_REQUIRES_ACTUAL_OFFICE',
                'baseline_hash':candidate['pptx']['sha256'],'source_hash':state['source']['sha256'],
                'unit':u['id'],'object':revised,'allowed_changes':{old['id']:fields},
                'limits':'Typography only; exact AST, native structure, pose and size remain protected. Inspect actual saved Office fonts and glyph metrics.'}
    measured=q.evaluate(task,state,candidate,u)
    source=measured['measurements'].get('reference_ink_bbox')
    # A wrong native equation can lie outside the corrected original window.
    # Locate the full saved owner for the proposal; acceptance remains fixed
    # in the original source window, without rendered-pixel registration.
    import numpy as np
    from PIL import Image
    from .component_report import _native_ink
    from .typed_metrics import ink_box
    bounds=task/candidate['render']['path'];bounds=bounds.parent/'text-bounds.json'
    if read_json(bounds).get('pptx_hash')!=candidate['pptx']['sha256']:
        raise ValueError('Stale actual native math owner bounds')
    owner=_native_ink(task/candidate['pptx']['path'],bounds,state['source_size']).get(old['id'])
    if not owner:raise ValueError('Saved native math owner is not measured')
    left=max(0,int(np.floor(owner[0]-2)));top=max(0,int(np.floor(owner[1]-2)))
    right=min(state['source_size'][0],int(np.ceil(owner[0]+owner[2]+2)))
    bottom=min(state['source_size'][1],int(np.ceil(owner[1]+owner[3]+2)))
    pixels=np.asarray(Image.open(task/candidate['preview']['path']).convert('RGB').resize(tuple(state['source_size']),Image.Resampling.LANCZOS).crop((left,top,right,bottom)),float)
    selector=u['protocol']['foreground_selector']
    current=ink_box((pixels.mean(2)<selector['max_mean_rgb_255'])&(np.ptp(pixels,axis=2)<selector['max_chroma_rgb_255']))
    if not source or not current:raise ValueError('Locate missing actual or original formula ink before fitting')
    source=[source[0]+u['roi'][0],source[1]+u['roi'][1],source[2]+u['roi'][0],source[3]+u['roi'][1]]
    current=[current[0]+left,current[1]+top,current[2]+left,current[3]+top]
    sh,ch=source[3]-source[1],current[3]-current[1];ratio=sh/ch
    if not .5<=ratio<=2:raise ValueError('Large source formula discrepancy needs a new source-supported layout')
    unchanged_ast=canonical_ast(ast)==canonical_ast(old['content']['ast'])
    same_style=all(old['style'].get(k)==v for k,v in style.items())
    mass=measured['values'].get('foreground_mass_ratio')
    rule=next(v for v in u['metrics'] if v['id']=='foreground_mass_ratio')
    frozen=bool(unchanged_ast and same_style and mass is not None and rule['min']<=mass<=rule['max'] and abs(sh-ch)<=u['protocol']['boundary_tolerance_px'])
    if frozen:ratio=1.
    revised=copy.deepcopy(old);revised['content']['ast']=copy.deepcopy(ast);revised['style'].update(style)
    revised['style']['font_size']=round(old['style']['font_size']*ratio,4)
    with ZipFile(task/candidate['pptx']['path']) as archive:root=E.fromstring(archive.read('ppt/presentation.xml'))
    pp=(int(root.find('{http://schemas.openxmlformats.org/presentationml/2006/main}sldSz').get('cx'))/12700)/state['source_size'][0]
    width=max(old['bbox'][2],source[2]-source[0]+12)
    height=max(old['bbox'][3],revised['style']['font_size']/pp*1.6)
    if old['style'].get('align','center')=='center':left=(source[0]+source[2]-width)/2
    else:left=source[0]-(current[0]-old['bbox'][0])*ratio
    top=source[1]-(current[1]-old['bbox'][1])*ratio
    revised['bbox']=[left,top,width,height]
    if max(abs(left-old['bbox'][0]),abs(top-old['bbox'][1]))>32:
        raise ValueError('Relocation exceeds the located original formula plan')
    fields=(['equation'] if not unchanged_ast else [])
    fields += ['style.'+k for k in ('font','color','font_size','math_font_policy') if revised['style'].get(k)!=old['style'].get(k)]
    if style.get('math_font_policy')=='isolated_script_comma' and old['style'].get('math_font_policy')!='isolated_script_comma':
        fields=['equation']+[field for field in fields if field!='equation']
    fields += ['bbox.'+k for i,k in enumerate(('left','top','width','height')) if revised['bbox'][i]!=old['bbox'][i]]
    if not fields:raise ValueError('No meaningful formula action; investigate actual family, scripts or neighbouring gaps')
    return {'status':'SOURCE_NATIVE_MATH_PROPOSAL_REQUIRES_ACTUAL_OFFICE','baseline_hash':candidate['pptx']['sha256'],'source_hash':state['source']['sha256'],'unit':u['id'],'object':revised,'allowed_changes':{old['id']:fields},'measurements':{'original_ink_xyxy':source,'actual_ink_xyxy':current,'font_ratio':ratio,'font_size_frozen':frozen},'limits':'Exact AST, symbols and native structure are independent of pixel targets. No raster replacement or post-render registration; all other formulas, words, icons and page data stay protected.'}


def definition_proposal(task,request):
    """Compile source-confirmed variable definitions in one native text frame.

    Prose stays ordinary editable text; each variable is a real inline Office
    Math zone. An actual renderer may omit inline zones, so preserve the saved
    outcome and then choose separate native equations if that occurs.
    """
    from . import agent_runtime as a
    from .mathml import math_node
    task,state=a._state(task);candidate=state.get('selected')
    if not candidate or request.get('baseline_hash')!=candidate['pptx']['sha256'] or request.get('source_hash')!=state['source']['sha256']:
        raise ValueError('Bind immutable original and actual saved definition frame')
    old=next(o for o in read_json(task/candidate['scene']['path'])['objects'] if o['id']==request['object'])
    if old['render_type']!='text':raise ValueError('Use the existing native definition text frame')
    entries=request.get('entries',[])
    if not 1<=len(entries)<=16 or not request.get('source_evidence'):
        raise ValueError('Read every original variable, exact prose and source rows first')
    paragraphs=[];prose=[];spans=[]
    for number,entry in enumerate(entries,1):
        if entry.get('number')!=number or not entry.get('description') or not entry.get('source_roi'):
            raise ValueError('Preserve source numbering, complete prose and located formula span')
        ast=copy.deepcopy(entry['ast']);math_node(ast);spans.append(ast)
        prefix=str(number)+'. ';suffix=': '+entry['description']
        policy=request.get('math_font_policy','native_math');math_node(ast,font_policy=policy)
        paragraphs.append([{'text':prefix},{'ast':ast,'font':request.get('math_font','Cambria Math'),'math_font_policy':policy},{'text':suffix}])
        prose.append(prefix+suffix)
    revised=copy.deepcopy(old)
    revised['content']={'paragraphs':paragraphs,'inline_math':'office_math'}
    source_style=request.get('source_style',{})
    if set(source_style)-{'font','font_size','line_spacing','line_spacing_pt','color','align','valign','bold'}:
        raise ValueError('Only source-supported definition typography may change')
    revised['style'].update(source_style)
    if request.get('bbox') is not None:revised['bbox']=list(request['bbox'])
    grant=['text_body']
    grant += ['style.'+key for key in revised['style'] if revised['style'].get(key)!=old['style'].get(key)]
    grant += ['bbox.'+name for i,name in enumerate(('left','top','width','height')) if revised['bbox'][i]!=old['bbox'][i]]
    return {'status':'SOURCE_NATIVE_DEFINITIONS_REQUIRE_ACTUAL_OFFICE','baseline_hash':candidate['pptx']['sha256'],
        'source_hash':state['source']['sha256'],'object':revised,'allowed_changes':{old['id']:grant},
        'source_prose_literal':'\n'.join(prose),'source_math_spans':spans,
        'limits':'Exact original prose and every formula span are separate obligations; observe actual inline rendering, row gaps and external preservation. No Unicode scripts, raster formula or claimed semantic pass from the proposal.'}


def representation_debt(objects,units):
    """Locate scientific Unicode shortcuts omitted by an equation-only loop."""
    import re
    records=[]
    for obj in objects:
        if obj.get('render_type')!='text':continue
        content=obj.get('content',{});values=[content.get('text','')]
        values.extend(run.get('text','') for row in content.get('paragraphs',[content.get('runs',[])]) for run in row)
        if not any(re.search('[\u2070-\u209f]|[A-Za-z][\u0302\u0303]',text) for text in values):continue
        refs=[u['id'] for u in units.values() if obj['id'] in u.get('objects',[])]
        records.append({'object':obj['id'],'quality_units':refs,'roi':obj['bbox'],'kind':'mixed_scientific_text',
            'description':'Read source mathematical spans in this text frame; ordinary Unicode script/accent glyphs do not prove structured formulas. Confirm source AST/prose and use native definitions or independently bound equations.'})
    return records
