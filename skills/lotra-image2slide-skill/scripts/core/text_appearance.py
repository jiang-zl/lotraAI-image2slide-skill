"""Same-source-window whole-string ink dimensions; native frame size is not ink."""
import math
from pathlib import Path
import numpy as np
from PIL import Image
from .common import digest,safe_path


def validate(feature):
    value=feature.get('text_appearance')
    if not isinstance(value,dict) or not value.get('source_evidence') or not value.get('isolation'):
        raise ValueError('TEXT_APPEARANCE_SOURCE_REQUIRED: independent whole-string ink isolation')
    if set(value)-{'source_evidence','isolation','colours','colour_tolerance','limits','spacing_axis','spacing_groups'}:
        raise ValueError('Unknown whole-string text appearance field')
    colours=value.get('colours',[])
    if not colours or len(colours)>16 or any(not isinstance(c,str) or len(c)!=6 or any(k not in '0123456789abcdefABCDEF' for k in c) for c in colours):
        raise ValueError('Original text ink colours required')
    if type(value.get('colour_tolerance')) not in (float,int) or not 0<value['colour_tolerance']<=.25:
        raise ValueError('Bounded original text colour tolerance required')
    limits=value.get('limits',{})
    if set(limits) not in ({'width','height','baseline','spacing'},{'width','height','baseline','spacing','position'}) or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<v<=8 for v in limits.values()):
        raise ValueError('Freeze source-pixel text width/height/baseline/spacing bounds before native construction')
    if value.get('spacing_axis','horizontal') not in ('horizontal','vertical'):
        raise ValueError('Original text spacing axis required')
    if value.get('spacing_groups') is not None:
        grouping=value['spacing_groups'];axis=0 if value.get('spacing_axis','horizontal')=='horizontal' else 1
        if (not isinstance(grouping,dict) or set(grouping)-{'logical_text','groups','source_evidence','observer'} or
                grouping.get('observer') not in ('host_model','human') or not grouping.get('source_evidence') or
                not isinstance(grouping.get('logical_text'),str) or not grouping['logical_text']):
            raise ValueError('TEXT_GROUP_SOURCE_REQUIRED: independent complete logical glyph/row groups')
        groups=grouping.get('groups')
        if not isinstance(groups,list) or not 2<=len(groups)<=256:raise ValueError('Two to 256 independently observed text groups required')
        offset=0;end=None;x,y,w,h=feature['roi']
        for group in groups:
            if not isinstance(group,dict) or set(group)!={'span','roi','source_evidence'} or not group['source_evidence']:
                raise ValueError('Each original text group needs exact span, ROI and source evidence')
            span=group['span'];box=group['roi']
            if (not isinstance(span,list) or len(span)!=2 or any(type(v) is not int for v in span) or span[0]!=offset or
                    not offset<span[1]<=len(grouping['logical_text']) or not grouping['logical_text'][offset:span[1]].strip()):
                raise ValueError('Text groups preserve complete consecutive logical character spans')
            if (not isinstance(box,list) or len(box)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in box) or
                    box[2]<=0 or box[3]<=0 or box[0]<x or box[1]<y or box[0]+box[2]>x+w or box[1]+box[3]>y+h or
                    end is not None and box[axis]<end):
                raise ValueError('Source text groups need disjoint ordered ROIs inside their feature')
            offset=span[1];end=box[axis]+box[axis+2]
        if offset!=len(grouping['logical_text']):raise ValueError('Text group spans omit original characters')
    return value


def _box(mask,left,top):
    yy,xx=np.nonzero(mask)
    if not len(xx):raise ValueError('TEXT_GROUP_INK_SUPPORT_REQUIRED: complete nonempty source/render group')
    return [left+int(xx.min()),top+int(yy.min()),int(xx.max()-xx.min()+1),int(yy.max()-yy.min()+1)]


def _groups(mask,feature,value,left,top,source_plan=None):
    axis=0 if value.get('spacing_axis','horizontal')=='horizontal' else 1
    rows=value['spacing_groups']['groups'];boxes=[];covered=np.zeros_like(mask)
    if source_plan is None:
        for row in rows:
            x,y,w,h=row['roi'];selected=np.zeros_like(mask)
            selected[max(0,math.floor(y-top)):min(mask.shape[0],math.ceil(y+h-top)),
                     max(0,math.floor(x-left)):min(mask.shape[1],math.ceil(x+w-left))]=True
            own=mask&selected
            if (own&covered).any():raise ValueError('TEXT_GROUP_SOURCE_OVERLAP: a source pixel has two owners')
            covered|=own;boxes.append(_box(own,left,top))
        if (mask&~covered).any():raise ValueError('TEXT_GROUP_COVERAGE_REQUIRED: original ink outside declared groups')
        gaps=[boxes[i+1][axis]-boxes[i][axis]-boxes[i][axis+2] for i in range(len(boxes)-1)]
        if any(gap<=0 for gap in gaps):raise ValueError('TEXT_GROUP_SOURCE_SEPARATION_REQUIRED: observe clear inter-group whitespace')
        cuts=[(boxes[i+1][axis]+boxes[i][axis]+boxes[i][axis+2])/2 for i in range(len(boxes)-1)]
        return {'boxes':boxes,'cuts':cuts,'spacing':gaps,'basis':'independent_original_groups','all_ink_owned':True}
    projection=mask.any(axis=0 if axis==0 else 1);sites=np.flatnonzero(projection)
    origin=left if axis==0 else top
    gaps=[(origin+int(a)+1,origin+int(b)) for a,b in zip(sites,sites[1:]) if b-a>1]
    limit=value['limits']['width' if axis==0 else 'baseline'];chosen=[]
    for cut in source_plan['cuts']:
        options=[(a+b)/2 for a,b in gaps if abs((a+b)/2-cut)<=limit]
        if not options:raise ValueError('TEXT_GROUP_RENDER_SEPARATION_REQUIRED: observed original groups lost their located whitespace')
        if len(options)!=1:raise ValueError('TEXT_GROUP_RENDER_AMBIGUOUS: more than one actual gap can own an original group boundary')
        chosen.append(options[0])
    if chosen!=sorted(set(chosen)):raise ValueError('TEXT_GROUP_RENDER_AMBIGUOUS: native group boundary order is unresolved')
    bounds=[0]+[round(cut-origin) for cut in chosen]+[mask.shape[1 if axis==0 else 0]]
    for start,end in zip(bounds,bounds[1:]):
        own=np.zeros_like(mask)
        if axis==0:own[:,start:end]=mask[:,start:end]
        else:own[start:end]=mask[start:end]
        covered|=own;boxes.append(_box(own,left,top))
    if not np.array_equal(covered,mask):raise ValueError('TEXT_GROUP_RENDER_COVERAGE_REQUIRED: actual paint cannot be omitted')
    spacing=[boxes[i+1][axis]-boxes[i][axis]-boxes[i][axis+2] for i in range(len(boxes)-1)]
    return {'boxes':boxes,'cuts':chosen,'spacing':spacing,'basis':'unique_whitespace_near_frozen_source_boundaries',
            'boundary_search_limit_source_px':limit,'all_ink_owned':True,'candidate_alignment':False}


def ink(image,feature,source_plan=None):
    from .line_verification import _mask
    value=validate(feature);x,y,w,h=feature['roi'];pad=math.ceil(max(value['limits'].values()))+2
    left=max(0,math.floor(x-pad));top=max(0,math.floor(y-pad))
    right=min(image.width,math.ceil(x+w+pad));bottom=min(image.height,math.ceil(y+h+pad))
    pixels=np.asarray(image.crop((left,top,right,bottom)).convert('RGB'),np.float32)/255
    mask=np.zeros(pixels.shape[:2],bool)
    for colour in value['colours']:mask |= _mask(pixels,colour,value['colour_tolerance'])
    yy,xx=np.nonzero(mask)
    if not len(xx):raise ValueError('TEXT_INK_SUPPORT_REQUIRED: no isolated whole-string foreground')
    if xx.min()==0 or yy.min()==0 or xx.max()==mask.shape[1]-1 or yy.max()==mask.shape[0]-1:
        raise ValueError('TEXT_INK_ISOLATION_REQUIRED: text foreground reaches the observation window boundary')
    box=[left+int(xx.min()),top+int(yy.min()),int(xx.max()-xx.min()+1),int(yy.max()-yy.min()+1)]
    projection=mask.any(axis=0 if value.get('spacing_axis','horizontal')=='horizontal' else 1)
    sites=np.flatnonzero(projection);gaps=np.diff(sites);gaps=(gaps[gaps>1]-1).tolist()
    result={'bbox':box,'width':box[2],'height':box[3],'baseline':box[1]+box[3],
            'ink_center_x':box[0]+box[2]/2,'ink_center_y':box[1]+box[3]/2,
            'spacing':gaps,'projection_spacing':gaps,'spacing_basis':'raw_projection_bands',
            'pixels':int(mask.sum()),'window':[left,top,right-left,bottom-top]}
    if value.get('spacing_groups'):
        grouped=_groups(mask,feature,value,left,top,source_plan)
        result.update(spacing=grouped['spacing'],spacing_basis='explicit_original_groups',group_plan=grouped)
    return result


def compare(original,actual,feature):
    value=validate(feature)
    # Resampling only maps current render cells to the frozen source canvas;
    # there is no candidate translation, scale fitting or glyph alignment.
    if actual.size!=original.size:actual=actual.resize(original.size,Image.Resampling.LANCZOS)
    source=ink(original,feature)
    try:render=ink(actual,feature,source.get('group_plan'))
    except ValueError as error:
        return {'passed':False,'valid':not str(error).startswith('TEXT_GROUP_RENDER_AMBIGUOUS'),'feature':feature['id'],'source':source,
                'reason':'Actual text has missing ink or exceeds the fixed source observation window: '+str(error),
                'candidate_alignment':False}
    checks=[]
    for field in ('width','height','baseline'):
        delta=abs(source[field]-render[field]);checks.append({'field':field,'value':delta,
            'threshold':value['limits'][field],'passed':delta<=value['limits'][field],'unit':'source_px'})
    # Compare the complete painted aggregate at its original position, including
    # intentional source offsets. A centered frame cannot hide shifted glyphs.
    position=value['limits'].get('position',min(value['limits'][key] for key in ('width','height','baseline')))
    for field in ('ink_center_x','ink_center_y'):
        delta=abs(source[field]-render[field]);checks.append({'field':field,'value':delta,
            'threshold':position,'passed':delta<=position,'unit':'source_px',
            'basis':'frozen_source_position; no geometric-center snapping'})
    if source['spacing']:
        same=len(source['spacing'])==len(render['spacing'])
        delta=max((abs(a-b) for a,b in zip(source['spacing'],render['spacing'])),default=0)
        checks.append({'field':'spacing','passed':same and delta<=value['limits']['spacing'],
            'value':delta,'threshold':value['limits']['spacing'],'gap_count_matches':same,'unit':'source_px'})
    else:checks.append({'field':'spacing','passed':True,'applicable':False,'scope':'original projection has no isolatable whitespace gap; no tracking PASS claimed'})
    if value.get('spacing_groups'):
        axis=0 if value.get('spacing_axis','horizontal')=='horizontal' else 1
        for index,(a,b) in enumerate(zip(source['group_plan']['boxes'],render['group_plan']['boxes'])):
            values={'width':abs(a[2]-b[2]),'height':abs(a[3]-b[3]),'baseline':abs(a[1]+a[3]-b[1]-b[3])}
            for field,delta in values.items():
                checks.append({'field':'group.'+str(index)+'.'+field,'value':delta,'threshold':value['limits'][field],
                               'passed':delta<=value['limits'][field],'unit':'source_px'})
            for coordinate,field in enumerate(('ink_center_x','ink_center_y')):
                delta=abs((a[coordinate]+a[coordinate+2]/2)-(b[coordinate]+b[coordinate+2]/2))
                checks.append({'field':'group.'+str(index)+'.'+field,'value':delta,'threshold':position,
                               'passed':delta<=position,'unit':'source_px'})
            limit=value['limits']['width' if axis==0 else 'baseline'];delta=abs(a[axis]-b[axis])
            checks.append({'field':'group.'+str(index)+'.axis_position','value':delta,'threshold':limit,'passed':delta<=limit,'unit':'source_px'})
    return {'passed':all(c['passed'] for c in checks),'valid':True,'feature':feature['id'],
            'source':source,'render':render,'checks':checks,'candidate_alignment':False,
            'baseline_definition':'observed ink bottom in source coordinates; no inferred typographic baseline',
            'scope':'Whole-string optical dimensions; explicit original group geometry/spacing when declared, otherwise raw projection bands. Exact characters and semantic appearance have separate gates'}


def evaluate(task,state,candidate,features):
    from .component_workflow import _resource,actual_render
    selected=[f for f in features if f['kind']=='text' or f['kind']=='math' and
              (f.get('text_appearance') or state.get('source_review_policy')=='source-review-1.37.5')];rows={}
    if not selected:return {'passed':True,'applicable':False,'features':{}}
    actual_render(task,state,candidate,independent=True)
    with Image.open(_resource(task,state['source'])) as original,Image.open(_resource(task,candidate['preview'])) as actual:
        for feature in selected:
            try:rows[feature['id']]=compare(original,actual,feature)
            except ValueError as error:rows[feature['id']]={'passed':False,'valid':False,'reason':str(error)}
    return {'passed':all(v['passed'] for v in rows.values()),'valid':all(v['valid'] for v in rows.values()),
            'features':rows,'source_hash':state['source']['sha256'],'preview_hash':candidate['preview']['sha256']}
