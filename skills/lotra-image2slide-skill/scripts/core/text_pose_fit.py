"""Bounded native plain-text pose proposals from an actual glyph discrepancy.

No content/font substitution and no image registration. Apply the proposal as
an authorized native patch, render it, and judge each actual source property.
"""
import copy
from .common import read_json,digest


def _actual_word_ink(task,state,candidate,obj):
    """Locate the complete saved word, even outside its source quality ROI."""
    import numpy as np
    from PIL import Image
    from .component_report import _native_ink
    from .typed_metrics import ink_box
    bounds=task/candidate['render']['path'];bounds=bounds.parent/'text-bounds.json'
    if read_json(bounds).get('pptx_hash')!=candidate['pptx']['sha256']:
        raise ValueError('Stale actual Office glyph ownership')
    boxes=_native_ink(task/candidate['pptx']['path'],bounds,state['source_size'])
    box=boxes.get(obj['id'])
    if not box:raise ValueError('Actual glyph owner bounds are unavailable')
    preview=Image.open(task/candidate['preview']['path']).convert('RGB').resize(tuple(state['source_size']),Image.Resampling.LANCZOS)
    left=max(0,int(np.floor(box[0]-1)));top=max(0,int(np.floor(box[1]-1)))
    right=min(preview.width,int(np.ceil(box[0]+box[2]+1)));bottom=min(preview.height,int(np.ceil(box[1]+box[3]+1)))
    data=np.asarray(preview.crop((left,top,right,bottom)),float)
    colour=np.asarray([int(obj['style'].get('color','000000')[i:i+2],16) for i in (0,2,4)])
    if np.ptp(colour)<40 and colour.mean()<100:
        mask=(data.mean(2)<210)&(np.ptp(data,axis=2)<60)
    else:
        contrast=np.linalg.norm(255-colour)
        mask=np.linalg.norm(data-colour,axis=2)<max(35,contrast*.8)
    # Advance rectangles can overlap the blank leading of adjacent text rows.
    # Remove independently named actual neighbours from proposal estimation;
    # the unchanged original ROI remains authoritative for acceptance.
    xx,yy=np.meshgrid(np.arange(data.shape[1])+left+.5,np.arange(data.shape[0])+top+.5)
    for name,other in boxes.items():
        if name==obj['id']:continue
        overlap=(xx>=other[0])&(xx<other[0]+other[2])&(yy>=other[1])&(yy<other[1]+other[3])
        if overlap.any():mask &= ~overlap
    ink=ink_box(mask)
    if not ink:raise ValueError('Actual word collides with another native text owner; resolve its source layout before fitting')
    return [ink[0]+left,ink[1]+top,ink[2]+left,ink[3]+top]


def _content_probe(task,state,baseline,descriptor):
    """Reuse a saved content-only actual render without adopting its defects."""
    from .common import safe_path,identity
    from .source_ocr import source_literal,actual_text
    file=safe_path(task,descriptor['path'])
    if digest(file)!=descriptor['sha256']:raise ValueError('Saved content probe changed')
    probe=read_json(file);grants=probe.get('allowed') or {}
    if (probe.get('baseline')!=baseline['pptx']['sha256'] or not 1<=len(grants)<=16
            or any(fields!=['text_content'] for fields in grants.values())):
        raise ValueError('A content probe must be a bounded text-only drawing from this baseline')
    for key in ('pptx','preview','render','scene'):
        if not probe.get(key) or digest(safe_path(task,probe[key]['path']))!=probe[key]['sha256']:
            raise ValueError('Bind the saved content probe and its actual render')
    receipt=read_json(safe_path(task,probe['render']['path']))
    if receipt.get('pptx_hash')!=probe['pptx']['sha256'] or receipt.get('preview_hash')!=probe['preview']['sha256']:
        raise ValueError('Content probe actual render is stale')
    before=read_json(safe_path(task,baseline['scene']['path']))
    after=read_json(safe_path(task,probe['scene']['path']))
    old={o['id']:o for o in before['objects']};new={o['id']:o for o in after['objects']}
    if old.keys()!=new.keys() or not grants.keys()<=old.keys():raise ValueError('Content probe changed source owners')
    for name,obj in old.items():
        node=new[name];left=copy.deepcopy(obj);right=copy.deepcopy(node)
        if name in grants:
            units=[u for u in state['quality']['units'].values() if u['profile']=='text' and u['objects']==[name]]
            if (len(units)!=1 or source_literal(units[0]) is None or set(obj['content'])!={'text'}
                    or set(node['content'])!={'text'} or actual_text(task,probe,units[0])!=source_literal(units[0])):
                raise ValueError('Read the exact original literal for each content-only probe owner')
            left.pop('content');right.pop('content')
        if identity(left)!=identity(right):raise ValueError('A content probe cannot alter native style, position or other objects')
    return probe


def propose(task,request):
    from . import agent_runtime as a,source_quality as q
    task,state=a._state(task);candidate=state.get('selected')
    if not candidate or candidate['pptx']['sha256']!=request.get('baseline_hash'):
        raise ValueError('Native text fit binds an observed selected baseline')
    unit=state['quality']['units'][request['unit']]
    if unit['profile']!='text':raise ValueError('Fit plain native glyphs; math has its own route')
    baseline=candidate
    if request.get('content_probe'):
        candidate=_content_probe(task,state,baseline,request['content_probe'])
    scene=read_json(task/candidate['scene']['path']);obj=next(o for o in scene['objects'] if o['id']==request['object_id'])
    baseline_obj=next(o for o in read_json(task/baseline['scene']['path'])['objects'] if o['id']==obj['id'])
    if obj['render_type']!='text' or obj['id'] not in unit['objects']:raise ValueError('Bind the named source glyph unit')
    content=obj['content'];text=content.get('text')
    if text is None:
        paragraphs=content.get('paragraphs',[])
        if len(paragraphs)!=1 or any('ast' in run or any(k in run for k in ('font_size','font','bold','baseline')) for run in paragraphs[0]):
            raise ValueError('Mixed runs/math need an isolated native gallery')
        text=''.join(run.get('text','') for run in paragraphs[0])
    if '\n' in text or not 2<=len(text)<=80:raise ValueError('Source-authored single-line native text only')
    import unicodedata
    norm=lambda v:''.join(unicodedata.normalize('NFKC',v).split())
    source_literal=next((f.get('literal',f['expected']) for f in unit['features']
                         if f['category']=='content' and f['status']=='observed'),None)
    if not source_literal or norm(source_literal)!=norm(text):
        raise ValueError('Confirm exact original literal and glyph ownership before fitting; a generic type or native query is not source evidence')
    diagnostic=q.evaluate(task,state,candidate,unit);m=diagnostic['measurements']
    source,current=m.get('reference_ink_bbox'),m.get('candidate_ink_bbox')
    if not source or not current:raise ValueError('Refine missing source/actual ink domains before fitting')
    from .source_ocr import confirmed_word_anchor
    confirmed=(confirmed_word_anchor(task,state,unit,text)
               and unit['protocol'].get('candidate_native_text_domain') and unit.get('reference_mask'))
    if confirmed:
        # A wrong word pose can clip glyphs in the source acceptance window.
        # Never fit the clipped fragment's width/height. The proposal may read
        # the actual complete owner; acceptance retains the fixed source ROI.
        global_ink=_actual_word_ink(task,state,candidate,obj)
        current=[global_ink[i]-round(unit['roi'][i%2]) for i in range(4)]
    sw,sh=source[2]-source[0],source[3]-source[1];cw,ch=current[2]-current[0],current[3]-current[1]
    if not unit.get('reference_mask') and sw>=unit['roi'][2]*.95 and sh>=unit['roi'][3]*.95:
        raise ValueError('The supposed glyph occupies the full source window; isolate glyphs from panel material/grid borders first')
    ratio=sh/ch
    mass=diagnostic['values'].get('foreground_mass_ratio')
    mass_rule=next((m for m in unit['metrics'] if m['id']=='foreground_mass_ratio'),None)
    frozen_size=bool(mass is not None and mass_rule and
        (mass_rule.get('min') is None or mass>=mass_rule['min']) and
        (mass_rule.get('max') is None or mass<=mass_rule['max']) and
        abs(sh-ch)<=unit['protocol']['boundary_tolerance_px'])
    # Preserve a satisfactory weight/size when the source height difference is
    # already within its frozen sampling tolerance. Fit width/pose separately.
    if frozen_size:ratio=1.
    anchor=unit.get('source_word_anchor') or {}
    lo,hi=(.5,2.0) if confirmed else (.75,1.30)
    if not lo<=ratio<=hi:raise ValueError('Large font-family/source-window discrepancy needs source/glyph investigation')
    # Inherited native PPT dimensions can differ from an authoring default.
    # Point tracking is derived from the authoritative actual saved deck.
    from zipfile import ZipFile
    import xml.etree.ElementTree as E
    with ZipFile(task/candidate['pptx']['path']) as archive:root=E.fromstring(archive.read('ppt/presentation.xml'))
    rect=root.find('{http://schemas.openxmlformats.org/presentationml/2006/main}sldSz')
    points_per_pixel=(int(rect.get('cx'))/12700)/state['source_size'][0]
    tracking=(sw-cw*ratio)/max(1,len(text)-1)*points_per_pixel
    dx=source[0]-current[0];dy=source[1]-current[1]
    if obj['style'].get('valign','middle')=='middle':dy+=(sh-ch)/2
    if obj['style'].get('align','left')=='center':dx+=(sw-cw)/2
    if max(abs(dx),abs(dy))>(32 if confirmed else 12) or abs(tracking)>.5:raise ValueError('Uncertain layout/spacing needs a source window or native gallery')
    if abs(ratio-1)<.005 and abs(tracking)<.01 and max(abs(dx),abs(dy))<.05:
        raise ValueError('No meaningful glyph-pose change; investigate weight/family/material ownership instead of drawing a no-op')
    revised=copy.deepcopy(obj);revised['style']['font_size']=round(obj['style']['font_size']*ratio,4)
    revised['style']['char_spacing_pt']=round(obj['style'].get('char_spacing_pt',0)+tracking,4)
    revised['bbox'][0]+=dx;revised['bbox'][1]+=dy
    fields=(['text_content'] if revised['content']!=baseline_obj['content'] else [])+(['style.font_size'] if ratio!=1 else [])+(['style.char_spacing_pt'] if abs(tracking)>=.01 else [])+(['bbox.left'] if dx else [])+(['bbox.top'] if dy else [])
    return {'status':'BOUNDED_NATIVE_PROPOSAL_REQUIRES_ACTUAL_RENDER','object':revised,'allowed_changes':{obj['id']:fields},
        'baseline_hash':baseline['pptx']['sha256'],'preview_hash':candidate['preview']['sha256'],'unit':unit['id'],
        'content_probe':request.get('content_probe'),'source_hash':state['source']['sha256'],
        'cause':'Source/actual glyph height, width and baseline mismatch in the independently located source word.',
        'measurements':{'source_xyxy':source,'current_xyxy':current,'font_ratio':ratio,'tracking_delta_pt':tracking,'source_position_delta_px':[dx,dy],'font_size_frozen_for_satisfied_ink_mass':frozen_size},
        'limits':'No post-render registration. Font family and non-target scene remain protected. A hash-bound content-only actual probe may supply the confirmed source literal and glyph measurements, without adopting its visual defects. A proposal does not establish quality improvement.'}



def _confirmed_owned_word(task,state,unit,text):
    """Original host-read glyph ownership is a bounded alternative to OCR.

    OCR is a locator accelerator. It must not become a mandatory oracle for
    a source-confirmed tiny caption. This branch never modifies its literal,
    source mask or metrics and cannot confirm mixed paragraphs/formulae.
    """
    from .source_ocr import source_literal
    from .common import safe_path
    from PIL import Image
    anchor=unit.get('source_word_anchor') or {}
    content=next((f for f in unit['features'] if f['category']=='content'),{})
    if (anchor.get('kind')!='original_owned_glyphs'
            or anchor.get('source_hash')!=state['source']['sha256']
            or anchor.get('host_confirmed_literal')!=text
            or source_literal(unit)!=text
            or anchor.get('word_roi')!=unit['roi']
            or anchor.get('reference_mask')!=unit.get('reference_mask')
            or content.get('evidence',{}).get('source_hash')!=state['source']['sha256']):return False
    for descriptor in (anchor.get('source_view'),anchor.get('reference_mask')):
        if not isinstance(descriptor,dict) or set(('path','sha256'))-descriptor.keys():return False
        file=safe_path(task,descriptor['path'])
        if not file.is_file() or digest(file)!=descriptor['sha256']:return False
    mask=Image.open(safe_path(task,unit['reference_mask']['path'])).convert('L')
    return mask.size==tuple(round(v) for v in unit['roi'][2:]) and mask.getbbox() is not None

def propose_source_font(task, request):
    """A bounded cheap font/pose proposal; actual Office remains authoritative.

    Installed TrueType probes estimate only the requested source font ratio;
    they neither score the actual output nor distribute private font files.
    Current glyph position is read from the saved Office owner and pixels,
    even when it lies outside a corrected source locator.
    """
    import numpy as np, xml.etree.ElementTree as E
    from pathlib import Path
    from PIL import Image,ImageFont
    from zipfile import ZipFile
    from . import agent_runtime as a,source_quality as q
    from .component_report import _native_ink
    from .typed_metrics import ink_box
    from .source_ocr import confirmed_word_anchor
    task,state=a._state(task);candidate=state.get('selected')
    if not candidate or candidate['pptx']['sha256']!=request.get('baseline_hash'):
        raise ValueError('Bind the actual saved baseline')
    unit=q.unit(state,request['unit'])
    scene=read_json(task/candidate['scene']['path']);obj=next(o for o in scene['objects'] if o['id']==request['object_id'])
    if not unit or unit['profile']!='text' or unit['objects']!=[obj['id']] or not unit.get('reference_mask'):
        raise ValueError('Fit an independently confirmed single native word')
    text=obj['content'].get('text')
    if not text or '\n' in text or not (confirmed_word_anchor(task,state,unit,text) or _confirmed_owned_word(task,state,unit,text)):
        raise ValueError('Mixed runs/math or unconfirmed source literal need their own route')
    style=request.get('source_style',{})
    if not style or set(style)-{'font','bold','italic'} or not request.get('source_typography_evidence'):
        raise ValueError('Source font proposal needs specific original family/weight evidence')
    current=_actual_word_ink(task,state,candidate,obj)
    source=ink_box(q._mask(task,unit['reference_mask']))
    if not current or not source:raise ValueError('Source/current glyph ink is missing')
    source=[source[0]+round(unit['roi'][0]),source[1]+round(unit['roi'][1]),source[2]+round(unit['roi'][0]),source[3]+round(unit['roi'][1])]
    sw,sh=source[2]-source[0],source[3]-source[1];cw,ch=current[2]-current[0],current[3]-current[1]
    with ZipFile(task/candidate['pptx']['path']) as archive:root=E.fromstring(archive.read('ppt/presentation.xml'))
    rect=root.find('{http://schemas.openxmlformats.org/presentationml/2006/main}sldSz')
    pp=(int(rect.get('cx'))/12700)/state['source_size'][0]
    probes=[]
    for key in ('current_font','source_font'):
        record=request[key];file=Path(record['path'])
        if digest(file)!=record['sha256']:raise ValueError('Private installed font probe changed')
        font=ImageFont.truetype(str(file),max(4,round(obj['style']['font_size']/pp*4)))
        b=font.getbbox(text);probes.append([b[2]-b[0],b[3]-b[1]])
    # Size comes from the requested installed source outline at the actual
    # deck point/pixel scale. A neighbouring line inside the old word's
    # advance rectangle must not turn a25px crop into a25px font glyph.
    ratio=sh*4/probes[1][1]
    if not .5<=ratio<=2:raise ValueError('Source font/size requires a fresh original plan')
    diagnostic=q.evaluate(task,state,candidate,unit)
    mass=diagnostic['values'].get('foreground_mass_ratio')
    rule=next((v for v in unit['metrics'] if v['id']=='foreground_mass_ratio'),None)
    same_source_style=all(obj['style'].get(k,False if k in ('bold','italic') else None)==v for k,v in style.items())
    frozen_size=bool(same_source_style and mass is not None and rule and
        (rule.get('min') is None or mass>=rule['min']) and
        (rule.get('max') is None or mass<=rule['max']) and
        abs(sh-ch)<=unit['protocol']['boundary_tolerance_px'])
    # A family-change estimate must not override the already satisfied font
    # size/ink-weight route when the original family/weight is unchanged.
    if frozen_size:ratio=1.
    nw=cw if frozen_size else probes[1][0]/4*ratio
    tracking=(sw-nw)/max(1,len(text)-1)*pp
    if abs(tracking/pp)>max(.5,.2*sw/max(1,len(text))):raise ValueError('Excessive tracking indicates a wrong source font/family')
    centre_x=obj['style'].get('align','left')=='center'
    centre_y=obj['style'].get('valign','top')=='middle'
    dx=(source[0]+source[2]-current[0]-current[2])/2 if centre_x else source[0]-current[0]
    dy=(source[1]+source[3]-current[1]-current[3])/2 if centre_y else source[1]-current[1]
    if max(abs(dx),abs(dy))>32:raise ValueError('Large source position error needs a located layout plan')
    revised=copy.deepcopy(obj);revised['style'].update(style)
    revised['style']['font_size']=round(obj['style']['font_size']*ratio,4)
    revised['style']['char_spacing_pt']=round(obj['style'].get('char_spacing_pt',0)+tracking,4)
    height=max(obj['bbox'][3],revised['style']['font_size']/pp*1.35)
    if centre_y:dy-=(height-obj['bbox'][3])/2
    revised['bbox'][0]+=dx;revised['bbox'][1]+=dy;revised['bbox'][3]=height
    fields=['style.'+k for k in ('font','bold','italic','font_size','char_spacing_pt') if revised['style'].get(k)!=obj['style'].get(k)]
    fields += ['bbox.'+k for i,k in ((0,'left'),(1,'top'),(3,'height')) if revised['bbox'][i]!=obj['bbox'][i]]
    if not fields:raise ValueError('No meaningful native word change')
    return {'status':'SOURCE_FONT_PROPOSAL_REQUIRES_ACTUAL_OFFICE','unit':unit['id'],'object':revised,
            'allowed_changes':{obj['id']:fields},'baseline_hash':candidate['pptx']['sha256'],
            'source_hash':state['source']['sha256'],'source_typography_evidence':request['source_typography_evidence'],
            'measurements':{'source_xyxy':source,'actual_owned_xyxy':current,'font_ratio':ratio,'tracking_delta_pt':tracking,'pose_delta_px':[dx,dy],'size_basis':'satisfied_same_source_font_frozen' if frozen_size else 'installed_source_outline_at_actual_deck_scale','font_size_frozen_for_satisfied_ink_mass':frozen_size},
            'private_font_probes':{k:request[k]['sha256'] for k in ('current_font','source_font')},
            'limits':'Font probes estimate an action only. Original literal/AST, other words and all non-target properties remain protected; measure the actual saved/rendered part before adoption.'}
def propose_content(task,request):
    """Correct one confirmed source literal; keep native typography and pose."""
    import copy
    from . import agent_runtime as a,source_quality as q
    from .source_ocr import source_literal,actual_text
    from .common import read_json,safe_path
    task,state=a._state(task);candidate=state.get('selected')
    if not candidate or request.get('baseline_hash')!=candidate['pptx']['sha256']:
        raise ValueError('Bind the saved selected native text')
    unit=q.unit(state,request['unit']);literal=source_literal(unit) if unit else None
    if not unit or unit['profile']!='text' or literal is None or len(unit['objects'])!=1:
        raise ValueError('Read the exact original plain text and unique native owner first')
    scene=read_json(safe_path(task,candidate['scene']['path']))
    old=next(o for o in scene['objects'] if o['id']==unit['objects'][0])
    if old['render_type']!='text' or set(old['content'])!={'text'}:
        raise ValueError('Mixed native runs need a separately scoped run-content plan')
    actual=actual_text(task,candidate,unit)
    if actual is None or actual==literal:raise ValueError('No confirmed native text-content discrepancy')
    revised=copy.deepcopy(old);revised['content']['text']=literal
    return {'status':'SOURCE_NATIVE_TEXT_CONTENT_PROPOSAL_REQUIRES_ACTUAL_OFFICE',
        'baseline_hash':candidate['pptx']['sha256'],'source_hash':state['source']['sha256'],
        'unit':unit['id'],'object':revised,'allowed_changes':{old['id']:['text_content']},
        'observed_saved_text':actual,'source_literal':literal,
        'limits':'Native content only. Existing run count/style/size/pose, neighbouring labels and figures remain protected. Observe actual source glyphs and spacing after saving.'}


def propose_weight(task,request):
    """Reuse two actual native responses to estimate a protected stroke action."""
    from . import agent_runtime as a,source_quality as q
    from .common import safe_path,identity
    from .source_ocr import actual_text,source_literal
    task,state=a._state(task);selected=state.get('selected')
    if not selected or request.get('baseline_hash')!=selected['pptx']['sha256']:
        raise ValueError('Bind the current saved selected drawing')
    unit=q.unit(state,request['unit']);literal=source_literal(unit) if unit else None
    if not unit or unit['profile']!='text' or len(unit['objects'])!=1 or not literal:
        raise ValueError('Read a unique original plain native word before stroke fitting')
    name=unit['objects'][0]
    def load(descriptor):
        file=safe_path(task,descriptor['path'])
        if digest(file)!=descriptor['sha256']:raise ValueError('Actual response descriptor changed')
        candidate=read_json(file)
        for key in ('pptx','preview','render','scene'):
            if digest(safe_path(task,candidate[key]['path']))!=candidate[key]['sha256']:
                raise ValueError('Bind each saved native response and actual rendering')
        receipt=read_json(safe_path(task,candidate['render']['path']))
        if receipt.get('pptx_hash')!=candidate['pptx']['sha256'] or receipt.get('preview_hash')!=candidate['preview']['sha256']:
            raise ValueError('Actual native response rendering is stale')
        if actual_text(task,candidate,unit)!=literal:raise ValueError('Stroke responses retain exact source content')
        scene=read_json(safe_path(task,candidate['scene']['path']))
        obj=next(o for o in scene['objects'] if o['id']==name)
        if obj['render_type']!='text' or set(obj['content'])!={'text'}:
            raise ValueError('Mixed native runs/math need their dedicated source plan')
        return candidate,scene,obj
    base,base_scene,base_obj=load(request['response_baseline'])
    plain,plain_scene,plain_obj=load(request['plain_response'])
    stroke,stroke_scene,stroke_obj=load(request['stroke_response'])
    current=read_json(task/selected['scene']['path']);current_obj=next(o for o in current['objects'] if o['id']==name)
    if identity(base_obj)!=identity(current_obj) or any(identity(sc['canvas'])!=identity(current['canvas']) for sc in (base_scene,plain_scene,stroke_scene)):
        raise ValueError('The repaired word or native canvas changed; do not reuse a stale response')
    if q._crop_images(task,state,base,unit['roi'])[1].tobytes()!=q._crop_images(task,state,selected,unit['roi'])[1].tobytes():
        raise ValueError('Actual word context changed; observe its current local response first')
    a_obj,b_obj=copy.deepcopy(plain_obj),copy.deepcopy(stroke_obj)
    for obj in (a_obj,b_obj):
        obj['style'].pop('text_outline_width_pt',None);obj['style'].pop('text_outline_alpha',None)
    if identity(a_obj)!=identity(b_obj) or plain_obj['style'].get('text_outline_width_pt',0):
        raise ValueError('Use identical actual word pose/family/content, varying only stroke')
    if any(stroke_obj['style'].get(k)!=base_obj['style'].get(k) for k in ('font','bold','italic','color')):
        raise ValueError('Source response fitting preserves native family/weight class/colour')
    pm=q.evaluate(task,state,plain,unit)['values'].get('foreground_mass_ratio')
    sm=q.evaluate(task,state,stroke,unit)['values'].get('foreground_mass_ratio')
    rule=next(v for v in unit['metrics'] if v['id']=='foreground_mass_ratio')
    target=rule.get('stretch') or (rule['min']+rule['max'])/2
    if pm is None or sm is None or sm<=pm or not rule['min']<=target<=rule['max'] or not pm<target<sm:
        raise ValueError('Actual responses do not bracket an original source weight target')
    revised=copy.deepcopy(stroke_obj);revised['style']['text_outline_alpha']=round((target-pm)/(sm-pm),6)
    fields=['style.'+k for k in ('font_size','char_spacing_pt','text_outline_width_pt','text_outline_alpha') if revised['style'].get(k)!=current_obj['style'].get(k)]
    fields += ['bbox.'+k for i,k in enumerate(('left','top','width','height')) if revised['bbox'][i]!=current_obj['bbox'][i]]
    return {'status':'ACTUAL_RESPONSE_NATIVE_STROKE_PROPOSAL_REQUIRES_RENDER','unit':unit['id'],
        'baseline_hash':selected['pptx']['sha256'],'source_hash':state['source']['sha256'],
        'object':revised,'allowed_changes':{name:fields},
        'response_evidence':{key:request[key] for key in ('response_baseline','plain_response','stroke_response')},
        'measurements':{'actual_plain_mass':pm,'actual_stroke_mass':sm,'source_target_mass':target,'estimated_outline_alpha':revised['style']['text_outline_alpha']},
        'limits':'Actual response interpolation estimates an action only. Exact source targets, scientific content, same native family/colour and unrelated frozen fields remain protected. Render and independently observe glyphs, literal, weight, presence and affected relationships.'}
