"""One bounded native multi-line caption action from owned original glyph rows.

Original literal and paragraph count are preserved. Saved Office ink
supplies the actual response; no new capture, registration or pass is implied.
"""
from pathlib import Path
import copy,math
import numpy as np
from scipy import ndimage as ndi
from .common import read_json,write_json,digest,identity


def _row_boxes(mask,offset,count):
    labels,n=ndi.label(mask.sum(1)>4);boxes=[]
    from .typed_metrics import ink_box
    for k in range(1,n+1):
        ys=np.flatnonzero(labels==k)
        if len(ys)<3:continue
        own=np.zeros_like(mask);own[ys]=mask[ys]
        b=ink_box(own)
        boxes.append([b[0]+offset[0],b[1]+offset[1],
                      b[2]+offset[0],b[3]+offset[1]])
    if len(boxes)!=count:
        raise ValueError('Locate each original/native caption row independently before fitting: '+str(boxes))
    return boxes


def _extent_support(mask,rgb,boxes,offset):
    """Unowned faint/chromatic fragments cannot silently choose font width.

    No small component is removed. An ambiguous extreme needs its own source
    reading; real dots/punctuation remain in the authoritative original mask.
    """
    rows=[]
    solid=(rgb.mean(2)<120)&(np.ptp(rgb,axis=2)<18)&mask
    labels,count=ndi.label(mask)
    for row,box in enumerate(boxes):
        x0,y0,x1,y1=[round(v-offset[i%2]) for i,v in enumerate(box)]
        yy,xx=np.nonzero(solid[y0:y1])
        if not len(xx):raise ValueError('Read original caption material before deriving glyph extents')
        left,right=int(xx.min()),int(xx.max())+1
        weak=[]
        for k in np.unique(labels[y0:y1]):
            if not k:continue
            ys,xs=np.nonzero((labels==k)&mask)
            if not len(xs) or solid[ys,xs].any():continue
            if int(xs.min())<left-2 or int(xs.max())+1>right+2:
                weak.append({'component':int(k),'pixels':int(len(xs)),
                    'xyxy':[int(xs.min()+offset[0]),int(ys.min()+offset[1]),
                            int(xs.max()+1+offset[0]),int(ys.max()+1+offset[1])]})
        rows.append({'row':row,'solid_horizontal_support':[left+offset[0],right+offset[0]],
                     'unconfirmed_extrema':weak})
    return rows


def _response(task,state,baseline,unit,descriptor):
    """Read one saved actual native owner without adopting its whole drawing."""
    from .common import safe_path
    from .source_ocr import actual_text,source_literal
    file=safe_path(task,descriptor['path'])
    if digest(file)!=descriptor['sha256']:raise ValueError('Saved caption response descriptor changed')
    record=read_json(file)
    if record.get('baseline_hash')!=baseline['pptx']['sha256'] or record.get('source_hash')!=state['source']['sha256']:
        raise ValueError('Bind caption response to this selected baseline and original source')
    response=record['candidate']
    for key in ('pptx','preview','render','scene'):
        if digest(safe_path(task,response[key]['path']))!=response[key]['sha256']:
            raise ValueError('Saved actual caption response changed')
    receipt=read_json(safe_path(task,response['render']['path']))
    if receipt.get('pptx_hash')!=response['pptx']['sha256'] or receipt.get('preview_hash')!=response['preview']['sha256']:
        raise ValueError('Saved caption response has stale actual rendering')
    left=read_json(task/baseline['scene']['path']);right=read_json(task/response['scene']['path'])
    name=unit['objects'][0]
    a=next(o for o in left['objects'] if o['id']==name);b=next(o for o in right['objects'] if o['id']==name)
    if (identity(left['canvas'])!=identity(right['canvas']) or b['render_type']!='text'
            or a.get('parent')!=b.get('parent') or a['bbox'][2:]!=b['bbox'][2:]
            or actual_text(task,response,unit)!=source_literal(unit)):
        raise ValueError('Caption response preserves native owner, frame, source literal and canvas')
    return response,b


def propose(task,request):
    from . import agent_runtime as a,source_quality as q
    from .source_ocr import source_literal,actual_text
    from .text_pose_fit import _actual_word_ink
    task,state=a._state(task);candidate=state.get('selected')
    if not candidate or request.get('baseline_hash')!=candidate['pptx']['sha256'] or request.get('source_hash')!=state['source']['sha256']:
        raise ValueError('Bind original source and selected actual native caption')
    unit=q.unit(state,request['unit']);literal=source_literal(unit) if unit else None
    if not unit or unit['profile']!='text' or len(unit['objects'])!=1 or not unit.get('reference_mask') or not request.get('source_evidence'):
        raise ValueError('Confirm exact multi-line source literal and owned glyph mask')
    scene=read_json(task/candidate['scene']['path'])
    obj=next(o for o in scene['objects'] if o['id']==unit['objects'][0])
    baseline=candidate;baseline_obj=copy.deepcopy(obj)
    if request.get('actual_response'):
        candidate,obj=_response(task,state,baseline,unit,request['actual_response'])
    if obj['render_type']!='text':raise ValueError('Keep the existing native text owner')
    if set(obj['content'])=={'text'}:lines=obj['content']['text'].split('\n')
    elif set(obj['content'])<={'paragraphs','paragraph_layout'} and 'paragraphs' in obj['content'] and all(len(p)==1 and 'text' in p[0] and 'ast' not in p[0] for p in obj['content']['paragraphs']):
        lines=[p[0]['text'] for p in obj['content']['paragraphs']]
    else:raise ValueError('Mixed scientific math/multi-run paragraphs use their separate native route')
    if not 2<=len(lines)<=6 or any(not 2<=len(line)<=80 for line in lines) or actual_text(task,candidate,unit)!=literal:
        raise ValueError('Keep exact confirmed two-to-six native paragraph lines')
    if obj['style'].get('align') not in ('left','center') or obj['style'].get('valign') not in ('top','middle'):
        raise ValueError('Declare a source plan for another paragraph-anchor family')
    dependencies={'request':request,'unit':{k:v for k,v in unit.items() if k not in ('status','built_fingerprint')},
        'native_object':obj,'implementation':digest(Path(__file__))}
    folder=task/'scratch/native-text-lines'/identity(dependencies)[:24]
    file=folder/'proposal.json'
    if file.exists():
        result=read_json(file)
        result['proposal']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
        return result
    source=q._mask(task,unit['reference_mask'])
    source_boxes=_row_boxes(source,unit['roi'][:2],len(lines))
    source_rgb=np.asarray(q._crop_images(task,state,candidate,unit['roi'])[0],float)
    extent_audit=_extent_support(source,source_rgb,source_boxes,unit['roi'][:2])
    folder.mkdir(parents=True,exist_ok=True);write_json(folder/'original-extent-support.json',extent_audit)
    if any(row['unconfirmed_extrema'] for row in extent_audit):
        raise ValueError('Original caption width has unconfirmed faint/chromatic extrema; read their semantic ownership before font fitting')
    ink=_actual_word_ink(task,state,candidate,obj)
    roi=[math.floor(ink[0]),math.floor(ink[1]),
        math.ceil(ink[2])-math.floor(ink[0]),math.ceil(ink[3])-math.floor(ink[1])]
    _,pixels=q._crop_images(task,state,candidate,roi)
    current=np.asarray(pixels,float)
    # This conditional route is achromatic text on a confirmed light plane;
    # colored diagrams must not become caption samples inside an advance box.
    color=obj['style'].get('color','000000')
    rgb=np.array([int(color[i:i+2],16) for i in (0,2,4)])
    if np.ptp(rgb)>40 or rgb.mean()>100:
        raise ValueError('Colored captions need their source material selector')
    current_mask=(current.mean(2)<180)&(np.ptp(current,axis=2)<70)
    current_boxes=_row_boxes(current_mask,roi[:2],len(lines))
    source_boxes=np.array(source_boxes,float);current_boxes=np.array(current_boxes,float)
    heights=lambda boxes:boxes[:,3]-boxes[:,1]
    from .native_source_units import points_per_source_pixel
    pp=points_per_source_pixel(task,state,candidate)
    ratio=float(np.median(heights(source_boxes)/heights(current_boxes)))
    source_rows=request.get('source_rows');font_audit=[];lead_ratio=1.;response_rows=[]
    if source_rows:
        from PIL import ImageFont
        if len(source_rows)!=len(lines) or not request.get('current_font'):
            raise ValueError('Bind installed source outlines and original style evidence for every caption row')
        current_file=Path(request['current_font']['path'])
        if digest(current_file)!=request['current_font']['sha256']:raise ValueError('Current private font probe changed')
        current_font=ImageFont.truetype(str(current_file),round(obj['style']['font_size']/pp*4))
        for line,row in zip(lines,source_rows):
            if not row.get('source_typography_evidence') or set(row.get('source_style',{}))!={'font','bold','italic'}:
                raise ValueError('Confirm original font/weight for each independent row')
            descriptor=row['source_font'];font_file=Path(descriptor['path'])
            if digest(font_file)!=descriptor['sha256']:raise ValueError('Source private font probe changed')
            font=ImageFont.truetype(str(font_file),round(obj['style']['font_size']/pp*4))
            box=font.getbbox(line)
            font_audit.append({'width':(box[2]-box[0])/4,'height':(box[3]-box[1])/4,
                'lead':sum(font.getmetrics()),'sha256':descriptor['sha256'],
                'source_style':row['source_style']})
        if len({r['source_style']['font'] for r in source_rows})!=1:
            raise ValueError('A different-family multiline caption needs independently isolated row ownership')
        actual_styles=[dict(obj['style'],**(p[0] if p else {})) for p in obj['content'].get('paragraphs',[[{}] for _ in lines])]
        matched=np.array([all(style.get(k,False if k in ('bold','italic') else None)==row['source_style'][k]
                          for k in ('font','bold','italic')) for style,row in zip(actual_styles,source_rows)])
        response_rows=np.flatnonzero(matched).tolist() if request.get('actual_response') else []
        ratio=float(np.median(heights(source_boxes)[matched]/heights(current_boxes)[matched])) if response_rows else float(np.median(heights(source_boxes)/np.array([r['height'] for r in font_audit])))
        lead_ratio=float(np.median([r['lead'] for r in font_audit])/sum(current_font.getmetrics()))
        if response_rows:lead_ratio=1.
    if not .75<=ratio<=1.30:raise ValueError('Investigate source family/glyph ownership before a large caption size change')
    before=q.evaluate(task,state,candidate,unit)
    mass=before['values'].get('foreground_mass_ratio')
    mass_rule=next((m for m in unit['metrics'] if m['id']=='foreground_mass_ratio'),None)
    same_source_style=not source_rows or bool(matched.all())
    frozen=bool(same_source_style and mass is not None and mass_rule and
        (mass_rule.get('min') is None or mass>=mass_rule['min']) and
        (mass_rule.get('max') is None or mass<=mass_rule['max']) and
        np.max(np.abs(heights(source_boxes)-heights(current_boxes)))<=unit['protocol']['boundary_tolerance_px'])
    if frozen:ratio=1.
    sw=source_boxes[:,2]-source_boxes[:,0];cw=current_boxes[:,2]-current_boxes[:,0]
    advances=np.array([len(line)-1 for line in lines],float)
    if source_rows:
        probes=np.array([r['width'] for r in font_audit])
        existing_tracking=obj['style'].get('char_spacing_pt',0)/pp*advances
        if response_rows:
            ids=np.array(response_rows);calibration=float(np.median((cw[ids]-existing_tracking[ids])/probes[ids]))
            cw=probes*calibration+existing_tracking
        else:cw=probes+existing_tracking
    tracking=float(np.dot(advances,sw-cw*ratio)/np.dot(advances,advances)*pp)
    source_pitch=float(np.median(np.diff(source_boxes[:,1])))
    current_pitch=float(np.median(np.diff(current_boxes[:,1])))
    spacing=float(obj['style'].get('line_spacing',1.))*source_pitch/current_pitch/ratio/lead_ratio
    center=obj['style']['align']=='center'
    row_dx=(source_boxes[:,0]+source_boxes[:,2]-current_boxes[:,0]-current_boxes[:,2])/2 if center else source_boxes[:,0]-current_boxes[:,0]
    dx=float(np.median(row_dx))
    dy=float((source_boxes[0,1]+source_boxes[-1,3]-current_boxes[0,1]-current_boxes[-1,3])/2 if obj['style']['valign']=='middle' else source_boxes[0,1]-current_boxes[0,1])
    audit={'original_rows_xyxy':source_boxes.tolist(),'actual_rows_xyxy':current_boxes.tolist(),
        'font_ratio':ratio,'tracking_delta_pt':tracking,'line_spacing':spacing,
        'pose_delta_px':[dx,dy],'font_size_frozen_for_satisfied_ink_mass':frozen,
        'private_font_outline_estimates':font_audit,'original_row_horizontal_delta_px':row_dx.tolist()}
    audit.update(source_extent_support=extent_audit,actual_response=request.get('actual_response'),
                 actual_same_source_style_rows=response_rows)
    folder.mkdir(parents=True,exist_ok=True);write_json(folder/'row-plan.json',audit)
    if max(abs(dx),abs(dy))>32 or abs(tracking)>.5 or not .65<=spacing<=1.5:
        raise ValueError('Uncertain caption pose/advance/pitch needs an original row plan')
    revised=copy.deepcopy(obj)
    revised['style'].update(font_size=round(obj['style']['font_size']*ratio,4),
        char_spacing_pt=round(obj['style'].get('char_spacing_pt',0)+tracking,4),
        line_spacing=round(spacing,6))
    if source_rows:
        revised['style'].update(font=source_rows[0]['source_style']['font'],bold=False,italic=False)
        revised['content']={'paragraphs':[[{'text':line,**row['source_style']}] for line,row in zip(lines,source_rows)]}
    # Preserve one native caption while each original row keeps its actual
    # source anchor. Indents change native paragraph layout, not reference
    # registration, and still require the same fixed-source actual scoring.
    if center and np.max(np.abs(row_dx-dx))>.05:
        if 'paragraphs' not in revised['content']:
            revised['content']={'paragraphs':[[{'text':line}] for line in lines]}
        previous=obj['content'].get('paragraph_layout',[{} for _ in lines])
        if len(previous)!=len(lines):raise ValueError('Native caption paragraph layout count changed')
        layouts=[]
        for offset,prior in zip(row_dx-dx,previous):
            shift=2*float(offset)*pp+float(prior.get('left_indent_pt',0))-float(prior.get('right_indent_pt',0))
            layouts.append({'left_indent_pt':round(max(0,shift),6),'right_indent_pt':round(max(0,-shift),6)})
        revised['content']['paragraph_layout']=layouts
    if request.get('source_ink_rgb') is not None:
        paint=request['source_ink_rgb']
        if len(paint)!=3 or any(type(v) is not int or not 0<=v<=60 for v in paint):
            raise ValueError('Use observed original achromatic dark glyph material')
        source_rgb=np.asarray(q._crop_images(task,state,candidate,unit['roi'])[0],float)
        solid=source_rgb[source]
        if max(abs(np.percentile(solid,10,axis=0)-paint))>8:
            raise ValueError('Original caption ink proposal lacks solid-source support')
        revised['style']['color']=''.join(f'{v:02X}' for v in paint)
    revised['bbox'][0]+=dx;revised['bbox'][1]+=dy
    fields=['style.'+k for k in ('font','bold','italic','font_size','char_spacing_pt','line_spacing','color') if revised['style'].get(k)!=baseline_obj['style'].get(k)]
    if revised['content']!=baseline_obj['content']:fields.append('text_body')
    fields+=['bbox.'+k for i,k in ((0,'left'),(1,'top')) if revised['bbox'][i]!=baseline_obj['bbox'][i]]
    if not fields:raise ValueError('No meaningful multi-line native action; investigate source weight/family')
    result={'status':'OWNED_NATIVE_CAPTION_PROPOSAL_REQUIRES_ACTUAL_OFFICE',
        'unit':unit['id'],'object':revised,'allowed_changes':{obj['id']:fields},
        'baseline_hash':baseline['pptx']['sha256'],'source_hash':state['source']['sha256'],
        'source_evidence':request['source_evidence'],
        'measurements':audit,
        'limits':'One original native text owner, exact literal/paragraph count and frames. An explicit source-row plan may restore independently evidenced native family/weight using private installed outline estimates; no font files are distributed or glyphs flattened. Proposal is not satisfaction. Each row pose/weight and affected neighbors still need actual independent comparison.'}
    write_json(file,result)
    result['proposal']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    return result
