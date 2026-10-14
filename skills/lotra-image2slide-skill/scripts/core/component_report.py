"""Paired source-relative ROI diagnostics and saved component/ink spacing."""
import copy
import csv
import math
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from .common import read_json, write_json, digest
from .quality_policy import profile


def units(state, scene):
    found = {}
    def add(c, method, parent=None):
        found[c['id']] = {**c, 'parent': parent, 'method': method, 'kind': 'semantic_component'}
        for child in method.get('children', []):
            add(child, child['method'], c['id'])
    for component in state['analysis']['components']:
        add(component, state['methods'].get(component['id'], {}))
    for item in scene['objects']:
        kind = item['render_type']
        if kind not in ('group', 'text', 'equation', 'svg', 'photo') or item['id'] in found:
            continue
        if item['id'].startswith('_'):
            continue
        found[item['id']] = {'id': item['id'], 'parent': item.get('parent'),
            'semantic_class': item.get('semantic_type', kind), 'kind': kind,
            'roi': item['bbox'], 'parts': [], 'method': {}, 'scene_object': item}
    return list(found.values())


def _box(roi, size):
    x,y,w,h = roi
    right,bottom = min(size[0], x+w), min(size[1], y+h)
    x,y = max(0, math.floor(x)), max(0, math.floor(y))
    right,bottom = math.ceil(right), math.ceil(bottom)
    return [x,y,right-x,bottom-y] if right>x and bottom>y else None


def _flat(values):
    out = {k:v for k,v in values.items() if isinstance(v,(int,float)) or v is None}
    for key in ('material_contrast', 'texture_energy'):
        item = values.get(key, {})
        out[key+'_source'] = item.get('source')
        out[key+'_output'] = item.get('output')
        if item.get('source') is not None and item.get('output') is not None:
            out[key+'_source_error'] = abs(item['source']-item['output'])
    frequency = values.get('frequency_energy', {})
    if frequency:
        out['frequency_band_l1'] = sum(abs(a-b) for a,b in zip(frequency['source'],frequency['output']))
        for index,value in enumerate(frequency['output']):out['frequency_output_band_'+str(index)] = value
    return out


def _diagnostic(values, family):
    # Explicit uncalibrated source-similarity composite, not a beauty/semantic grade.
    weights = {'academic': {'ssim':.35,'foreground_iou':.30,'edge_iou':.35},
        'solid_icon': {'ssim':.30,'foreground_iou':.30,'edge_iou':.20,'colour_agreement':.20},
        'illustration': {'ssim':.60,'edge_iou':.15,'colour_agreement':.25},
        'scene': {'ssim':.55,'edge_iou':.25,'colour_agreement':.20}}[family]
    measured = dict(values)
    if isinstance(values.get('colour_error'),(int,float)):
        measured['colour_agreement'] = 1-values['colour_error']
    if any(not isinstance(measured.get(k),(int,float)) for k in weights):return None, weights
    return sum(weights[k]*measured[k] for k in weights), weights


def _distance(a,b):
    x,y,w,h = a;u,v,s,t = b
    dx,dy = max(u-x-w,x-u-s,0),max(v-y-h,y-v-t,0)
    overlap = max(0,min(x+w,u+s)-max(x,u))*max(0,min(y+h,v+t)-max(y,v))
    return {'gap_px':math.hypot(dx,dy), 'bbox_overlap_px2':overlap,
            'horizontal_clearance_px':u-(x+w) if u>=x else x-(u+s),
            'vertical_clearance_px':v-(y+h) if v>=y else y-(v+t)}


def _ink(source, box, color):
    import numpy as np
    from PIL import Image
    if not color or len(color.lstrip('#')) != 6:return None
    rgb=np.array([int(color.lstrip('#')[i:i+2],16) for i in (0,2,4)])
    x,y,w,h=box
    from .resource_facts import image_region
    with image_region(source,[('crop',tuple(map(round,(x,y,x+w,y+h))))]) as image:
        data=np.asarray(image).astype(float)
    mask=np.max(np.abs(data-rgb),2)<65
    yy,xx=np.nonzero(mask)
    if len(xx)<3:return None
    return [x+float(xx.min()),y+float(yy.min()),float(xx.max()-xx.min()+1),float(yy.max()-yy.min()+1)]


def _native_ink(pptx, file, size):
    if not file or not Path(file).is_file():return {}
    from .resource_facts import xml_part
    root=xml_part(pptx,'ppt/presentation.xml')
    rect=root.find('{http://schemas.openxmlformats.org/presentationml/2006/main}sldSz')
    sx,sy=size[0]/(int(rect.get('cx'))/12700),size[1]/(int(rect.get('cy'))/12700)
    return {item['id']:[item['ink'][0]*sx,item['ink'][1]*sy,item['ink'][2]*sx,item['ink'][3]*sy]
            for item in read_json(file)['objects'] if item.get('status')=='MEASURED' and len(item.get('ink',[]))==4}


def generate(task, output, *, baseline_task=None, office_bounds=None, comparison_candidate=None, final_candidate=None, notes=None):
    from . import agent_runtime as a
    task,state=a._state(task);candidate=final_candidate or state['selected'] or state['active_candidate']
    for key in ('pptx','scene','preview','render'):
        if digest(a._path(task,candidate[key]['path']))!=candidate[key]['sha256']:
            raise ValueError('Component measurement input changed: '+key)
    scene=read_json(a._path(task,candidate['scene']['path']))
    size=state['source_size'];components=units(state,scene)
    objects={q['id']:q for q in scene['objects']}
    source=a._path(task,state['source']['path']);pptx=a._path(task,candidate['pptx']['path'])
    ink=_native_ink(pptx,office_bounds,size)
    paired=None;before_objects={};before_render=None
    if baseline_task:
        bt,bs=a._state(baseline_task);bc=bs['selected'] or bs['active_candidate']
        if bs['source']['sha256']==state['source']['sha256']:
            paired=(bt,bs,bc)
            before_objects={q['id']:q for q in read_json(a._path(bt,bc['scene']['path']))['objects']}
            before_render=read_json(a._path(bt,bc['render']['path']))
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    rows=[]
    comparison_candidate=comparison_candidate or candidate
    for component in components:
        roi=_box(component['roi'],size)
        if not roi:continue
        typed=profile(component);family=typed['family']
        after=a._metrics(task,state,candidate,roi)['values']
        comparable=after if comparison_candidate.get('preview')==candidate.get('preview') else a._metrics(task,state,comparison_candidate,roi)['values']
        before=a._metrics(*paired,roi)['values'] if paired else None
        flat_after,flat_compare=_flat(after),_flat(comparable)
        flat_before=_flat(before) if before else {}
        deltas={k:flat_compare[k]-flat_before[k] for k in flat_compare if isinstance(flat_compare[k],(int,float)) and isinstance(flat_before.get(k),(int,float))}
        score,weights=_diagnostic(comparable,family)
        old_score,_=_diagnostic(before,family) if before else (None,weights)
        ident=component['id'];raw=objects.get(ident);old=before_objects.get(ident)
        fields=[]
        if raw and old:
            for key in ('bbox','render_type','content','style'):
                if raw.get(key)!=old.get(key):fields.append(key)
        row={'id':ident,'parent':component.get('parent'),'kind':component['kind'],'semantic_class':component.get('semantic_class'),
            'roi':roi,'profile':typed,'baseline':before,'current_comparable':comparable,'final_actual_render':after,
            'delta_comparable':deltas,'flat_baseline':flat_before,'flat_comparable':flat_compare,'flat_final':flat_after,
            'diagnostic_similarity':{'baseline':old_score,'current':score,'delta':score-old_score if score is not None and old_score is not None else None,
                'weights':weights,'meaning':'uncalibrated source-similarity composite only; not semantic/aesthetic acceptance'},
            'changed_scene_fields':fields,'observation':(notes or {}).get(ident),
            'limits':'Registered ROI can include neighbours/occlusion. White-mask IoU is conditional; texture, contrast and curvature are descriptive. No fabricated aesthetic/semantic score.'}
        if raw and raw['render_type'] in ('text','equation'):
            row['office_ink_bbox']=ink.get(ident)
            row['source_colour_ink_bbox']=_ink(source,roi,raw.get('style',{}).get('color','111111'))
        rows.append(row)
    spacing=[]
    text=[q for q in scene['objects'] if q['render_type'] in ('text','equation')]
    neighbours=[q for q in scene['objects'] if q['render_type'] in ('group','svg','photo','path','shape','equation','text')
                and q['bbox'][2]*q['bbox'][3] < size[0]*size[1]*.12]
    for first in text:
        candidates=[]
        for second in neighbours:
            if first['id']==second['id'] or first.get('parent')==second['id'] or second.get('parent')==first['id']:continue
            # Containing panels are not neighbour-spacing targets.
            x,y,w,h=first['bbox'];u,v,s,t=second['bbox']
            if u<=x and v<=y and u+s>=x+w and v+t>=y+h:continue
            distance=_distance(first['bbox'],second['bbox'])
            if distance['gap_px']<=40:candidates.append((distance['gap_px'],second,distance))
        for _,second,current in sorted(candidates,key=lambda item:item[0])[:3]:
            old_a,old_b=before_objects.get(first['id']),before_objects.get(second['id'])
            entry={'first':first['id'],'second':second['id'],'first_kind':first['render_type'],'frame_current':current,
                   'frame_baseline':_distance(old_a['bbox'],old_b['bbox']) if old_a and old_b else None,
                   'limits':'Frame distance is not ink distance. Office text ink bounds are real; the neighbour bbox is a geometric envelope, not its visible contour.'}
            if first['id'] in ink:entry['office_text_ink_to_neighbour_envelope']=_distance(ink[first['id']],second['bbox'])
            spacing.append(entry)
    rendered=read_json(a._path(task,candidate['render']['path']))
    common=read_json(a._path(task,comparison_candidate['render']['path']))
    result={'schema':'component-quality-report-1','source_sha256':state['source']['sha256'],'pptx_sha256':digest(pptx),
        'baseline_task':str(baseline_task) if paired else None,'comparison_backend':common.get('backend'),
        'baseline_backend':before_render.get('backend') if before_render else None,
        'same_renderer_version':bool(before_render and before_render.get('backend')==common.get('backend') and before_render.get('backend_version')==common.get('backend_version')),
        'final_render_backend':rendered.get('backend'),'comparison_candidate_pptx':comparison_candidate['pptx']['sha256'],
        'component_count':len(rows),'components':rows,'spacing_pairs':spacing,
        'limits':'Paired source similarity does not prove beauty/scientific meaning. Renderer/font changes are recorded. Final Office ink/frame analysis is separate; no editor-operation claims.'}
    write_json(output/'Component-metrics.json',result)
    keys=['ssim','psnr','mae','foreground_iou','edge_iou','edge_chamfer','colour_error','texture_energy_source_error','material_contrast_source_error','frequency_band_l1','gradient_continuity']
    with (output/'Component-metrics.csv').open('w',newline='',encoding='utf-8-sig') as file:
        columns=['id','kind','family']+[prefix+k for k in keys for prefix in ('baseline_','current_','delta_','final_')]
        writer=csv.DictWriter(file,fieldnames=columns);writer.writeheader()
        for row in rows:
            record={'id':row['id'],'kind':row['kind'],'family':row['profile']['family']}
            for k in keys:
                for prefix,field in (('baseline_','flat_baseline'),('current_','flat_comparable'),('delta_','delta_comparable'),('final_','flat_final')):record[prefix+k]=row[field].get(k)
            writer.writerow(record)
    def value(number):return '—' if number is None else f'{number:.4f}'
    lines=['# 组件级实际绘图指标与间距','',f'共 {len(rows)} 个语义组件、自然子组、独立文字或公式；{len(spacing)} 个文字/公式邻接关系。',
        '', '数值是同源固定坐标 ROI 的诊断，不是语义、美学或编辑功能的满分证明。表中差值使用相同的比较渲染；最终 Office 值、FFT 三个频带、质感/对比度、完整邻接明细见 JSON/CSV。图层遮挡和邻居可能影响 ROI。',
        '', '|组件|类别|SSIM 旧→新|PSNR 旧→新|IoU 旧→新|边缘距离 旧→新|色差 旧→新|诊断综合差值|', '|---|---|---|---|---|---|---|---|']
    for row in rows:
        pair=lambda key:value(row['flat_baseline'].get(key))+' → '+value(row['flat_comparable'].get(key))
        lines.append('|'+ '|'.join([row['id'],row['profile']['family'],pair('ssim'),pair('psnr'),pair('foreground_iou'),pair('edge_chamfer'),pair('colour_error'),value(row['diagnostic_similarity']['delta'])])+'|')
    lines.extend(['','## 修改与保留依据',''])
    for row in rows:
        if row['observation']:lines.append('- **'+row['id']+'**：'+row['observation'])
        elif row['changed_scene_fields']:lines.append('- **'+row['id']+'**：改变 '+', '.join(row['changed_scene_fields'])+'；数值变化见对应行，未自动解释为美观提升。')
    lines.extend(['','## 间距记录','', 'Office-text-bounds.json 保存实际文字墨迹边界；Component-metrics.json 的 spacing_pairs 保存源像素单位的邻接距离。负方向间距/框重叠必须结合真实轮廓判断，不能据此直接认定可见碰撞。'])
    (output/'Component-analysis.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return result
