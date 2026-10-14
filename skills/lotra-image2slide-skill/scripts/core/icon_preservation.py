"""Independent, non-compensating appearance guards for clearer native icons.

Program-owned immutable comparators cannot be supplied by a proposal. Fixed
original windows and the previous eligible unit best remain the ruler; sharpness
and a weighted score never waive a regressed protected measurement.
"""
import copy, math
import numpy as np
from scipy.ndimage import gaussian_filter
from .common import identity, read_json, write_json, digest, writer

VERSION='icon-preservation-1'
REVIEW_AXES=('source_style','material_quality','assembly_coherence')

def saved_render(task,candidate):
    from .execution_contract import resource
    for key in ('pptx','preview','render'):resource(task,candidate[key])
    receipt=read_json(resource(task,candidate['render']))
    if receipt.get('pptx_hash')!=candidate['pptx']['sha256'] or receipt.get('preview_hash')!=candidate['preview']['sha256']:
        raise ValueError('Appearance preservation requires the actual saved/rendered artifact')

def basis(state,unit,row):
    return identity({'source':state['source'],'canvas':state['source_size'],
                     'unit':unit['id'],'roi':unit['roi'],'style':row['target']['profile']})

def freeze(task,state,candidate,unit,row,previous=None):
    from .execution_contract import resource
    wanted=basis(state,unit,row);refs=[]
    if previous:
        if previous.get('basis')!=wanted:
            raise ValueError('HD preservation ruler changed; locate and archive an explicit original-domain correction before rebinding')
        refs=copy.deepcopy(previous['baselines'])
    best=state.get('object_lifecycle',{}).get('units',{}).get('source:'+unit['id'],{}).get('best_in_context')
    proposed=[]
    if best and best.get('eligible') is True:proposed.append(('independent_unit_best',best['candidate']))
    approved=state.get('quality_intent',{}).get('approved')
    if approved:proposed.append(('approved_native_artifact',approved))
    if not refs and candidate:proposed.append(('pre_reconstruction_saved_artifact',candidate))
    for reason,c in proposed:
        if reason=='independent_unit_best' and candidate and c['pptx']['sha256']==candidate['pptx']['sha256']:continue
        if not all(k in c for k in ('pptx','preview','render')):
            raise ValueError('Preservation requires a saved and actually rendered comparator')
        saved_render(task,c)
        if not any(r['candidate']['pptx']['sha256']==c['pptx']['sha256'] for r in refs):
            refs.append({'reason':reason,'candidate':{k:copy.deepcopy(c[k]) for k in ('pptx','preview','render')}})
    if not refs:raise ValueError('Render the first native construction before freezing its HD refinement')
    return {'schema':VERSION,'basis':wanted,'baselines':refs,
            'selection':'Program captures pre-reconstruction, approved and eligible independent-unit bests; proposal cannot choose a weaker comparator'}

def values(source,actual):
    from .appearance_metrics import image_values
    from .typed_metrics import color_histogram
    from .icon_hd import profile
    from skimage.color import rgb2lab,deltaE_ciede2000
    a=np.asarray(source.convert('RGB'),float)/255.;b=np.asarray(actual.convert('RGB'),float)/255.
    measured=image_values(a,b);mse=float(np.mean((a-b)**2))
    measured['psnr']=None if mse==0 else float(-10*math.log10(mse))
    measured['mse']=mse
    p=profile()['color_distribution'];ha=color_histogram(a.reshape(-1,3),p['bins'],p['membership']);hb=color_histogram(b.reshape(-1,3),p['bins'],p['membership'])
    measured.setdefault('raw_hard_color_histogram_tv',measured['color_histogram_tv'])
    measured['color_histogram_tv']=float(np.abs(ha/ha.sum()-hb/hb.sum()).sum()/2)
    measured['color_histogram_membership']=p['membership']
    measured['deltae_mean']=float(deltaE_ciede2000(rgb2lab(a),rgb2lab(b)).mean())
    return measured

def paired_checks(before,after,limits):
    rows=[]
    for key,tolerance in limits.items():
        if key=='psnr':
            # The exact-image case has infinite PSNR; finite arithmetic uses
            # its equivalent MSE ratio rather than inventing a capped score.
            a,b=before['mse'],after['mse']
            passed=b<=a*10**(tolerance/10)+1e-15
            delta=None if a==0 or b==0 else 10*math.log10(a/b)
        else:
            a,b=before.get(key),after.get(key)
            direction=-1 if key in ('color_histogram_tv','mean_absolute_rgb_error','deltae_mean') else 1
            delta=None if a is None or b is None else direction*(b-a)
            passed=delta is not None and math.isfinite(delta) and delta>=-tolerance-1e-12
        rows.append({'id':key,'before':before.get(key),'after':after.get(key),
                     'quality_delta':delta,'allowed_decrease':tolerance,'passed':bool(passed)})
    return rows

def shading(image):
    """Low-frequency material amplitude, direction and color; grain adds no gain."""
    a=np.asarray(image.convert('RGB'),float)/255.;a=gaussian_filter(a,(.8,.8,0))
    h,w=a.shape[:2];y,x=np.mgrid[-1:1:complex(h),-1:1:complex(w)]
    design=np.stack([np.ones_like(x),x,y],-1).reshape(-1,3)
    coef=np.linalg.lstsq(design,a.reshape(-1,3),rcond=None)[0]
    field=design@coef
    return {'amplitude':float(np.linalg.norm(np.percentile(field,95,axis=0)-np.percentile(field,5,axis=0))),
            'gradient':coef[1:].reshape(-1).tolist(),'mean_rgb':a.mean((0,1)).tolist()}

def shading_checks(reference,actual,limits):
    a,b=shading(reference),shading(actual);informative=a['amplitude']>=limits['informative_amplitude']
    ratio=b['amplitude']/max(a['amplitude'],1e-12)
    va,vb=np.array(a['gradient']),np.array(b['gradient']);cos=float(va@vb/max(np.linalg.norm(va)*np.linalg.norm(vb),1e-12))
    color=float(np.linalg.norm(np.array(a['mean_rgb'])-b['mean_rgb']))
    passed=color<=limits['mean_color_distance_max'] and (not informative or limits['amplitude_ratio'][0]<=ratio<=limits['amplitude_ratio'][1] and cos>=limits['gradient_cosine_min'])
    return {'passed':bool(passed),'reference':a,'actual':b,'informative':informative,
            'amplitude_ratio':ratio,'gradient_cosine':cos,'mean_color_distance':color,'limits':limits}

def review_context(task,state,candidate,unit,row):
    from .icon_hd import pdf_evidence,pdf_window
    from .quality_intent import source_view
    from .appearance_metrics import native_signatures
    from PIL import Image
    row=copy.deepcopy(row);row['preservation']=freeze(task,state,candidate,unit,row,row['preservation'])
    x,y,w,h=unit['roi'];size=state['source_size']
    context=[max(0,x-12),max(0,y-12),min(size[0],x+w+12)-max(0,x-12),min(size[1],y+h+12)-max(0,y-12)]
    original=source_view(task,state,context,1)
    views=[]
    for role,c in [('current',candidate)]+[('retained',r['candidate']) for r in row['preservation']['baselines']]:
        pdf,evidence=pdf_evidence(task,state,c);image,mapping=pdf_window(pdf,size,context,4)
        key=identity({'pdf':evidence['pdf_hash'],'roi':context,'scale':4})
        file=task/'observations/icon-style'/(key+'.png')
        if not file.is_file():
            file.parent.mkdir(parents=True,exist_ok=True);Image.fromarray(np.uint8(np.clip(image*255,0,255))).save(file)
        views.append({'role':role,'pptx_hash':c['pptx']['sha256'],'pdf_hash':evidence['pdf_hash'],
                      'path':file.relative_to(task).as_posix(),'sha256':digest(file),'roi':context,'scale':4})
    native=native_signatures(str((task/candidate['pptx']['path']).resolve()),candidate['pptx']['sha256'])
    from .icon_hd import closure
    from .boundary_geometry import saved_nodes
    nodes=saved_nodes(task/candidate['pptx']['path'],size);names=closure(nodes,unit['objects'])
    key=identity({'original':original,'unit':unit['id'],'style':row['target']['profile'],
                  'native':{n:native[n] for n in sorted(names)},'views':[{k:v for k,v in r.items() if k!='pptx_hash'} for r in views]})
    return {'unit':unit['id'],'basis':key,'original_view':original,'views':views,
            'required_axes':list(REVIEW_AXES),'return':'Each retained comparator: criteria for all axes retained_or_improved/regressed/uncertain, actual_facts and located evidence. Confirm subtype/projection, source material/style and coherent assembly against original and actual context. Numeric proxies do not decide subjective appearance.'}

def review_status(task,state,candidate,unit,row):
    row=copy.deepcopy(row);row['preservation']=freeze(task,state,candidate,unit,row,row['preservation'])
    context=review_context(task,state,candidate,unit,row)
    old=state.get('icon_style_reviews',{}).get(unit['id'])
    valid=bool(old and old.get('basis')==context['basis'])
    checks=[]
    for ref in row['preservation']['baselines']:
        key=ref['candidate']['pptx']['sha256'];record=next((r for r in (old or {}).get('comparisons',[]) if r['reference_hash']==key),{})
        checks += [{'id':key+':'+axis,'passed':bool(valid and record.get('criteria',{}).get(axis)=='retained_or_improved')} for axis in REVIEW_AXES]
    return {'passed':bool(checks) and all(c['passed'] for c in checks),'checks':checks,
            'comparisons':copy.deepcopy((old or {}).get('comparisons',[])) if valid else [],
            'status':'CURRENT_REVIEW_RECORDED' if valid else 'CURRENT_STYLE_REVIEW_REQUIRED','context':context}

def review_packet(task,state,candidate,units=None):
    from .execution_contract import resource
    contract=read_json(resource(task,state['icon_clarity_contract']));items=[]
    for row in contract['items']:
        if row['category'] not in ('clear_icon','blurred_icon') or units is not None and row['unit'] not in units:continue
        status=review_status(task,state,candidate,state['quality']['units'][row['unit']],row)
        if not status['passed']:items.append(status['context'])
    return {'kind':'icon_style_comparison','action':'icon-clarity observe','source_hash':state['source']['sha256'],
            'candidate_hash':candidate['pptx']['sha256'],'items':items[:8],'remaining':len(items)}

def observe(task,state,candidate,request):
    from .execution_contract import resource
    contract=read_json(resource(task,state['icon_clarity_contract']));known={r['unit']:r for r in contract['items'] if r['category'] in ('clear_icon','blurred_icon')}
    if request.get('source_hash')!=state['source']['sha256'] or request.get('candidate_hash')!=candidate['pptx']['sha256']:
        raise ValueError('Icon appearance review needs the exact original and current saved artifact')
    rows=request.get('items',[])
    if not rows or len({r['unit'] for r in rows})!=len(rows):raise ValueError('Distinct actual icon style reviews required')
    records=copy.deepcopy(state.get('icon_style_reviews',{}))
    for r in rows:
        uid=r['unit'];row=copy.deepcopy(known[uid]);row['preservation']=freeze(task,state,candidate,state['quality']['units'][uid],row,row['preservation'])
        context=review_context(task,state,candidate,state['quality']['units'][uid],row)
        if r.get('basis')!=context['basis'] or not r.get('actual_facts') or not r.get('evidence'):
            raise ValueError('Current enlarged original/candidate/comparator context and concrete appearance evidence required')
        expected={b['candidate']['pptx']['sha256'] for b in row['preservation']['baselines']};comparisons=r.get('comparisons',[])
        if len({c['reference_hash'] for c in comparisons})!=len(comparisons) or {c['reference_hash'] for c in comparisons}!=expected:
            raise ValueError('Every program-retained comparator needs an appearance comparison')
        for c in comparisons:
            if set(c.get('criteria',{}))!=set(REVIEW_AXES) or any(v not in ('retained_or_improved','regressed','uncertain') for v in c['criteria'].values()):
                raise ValueError('All source style, material and assembly axes require truthful explicit outcomes')
        if uid in records and records[uid]!=r:state.setdefault('icon_style_review_history',[]).append(records[uid])
        records[uid]=copy.deepcopy(r)
    state['icon_style_reviews']=records;state.pop('acceptance',None);state.pop('quality_result',None)
    return {'status':'ACTUAL_ICON_STYLE_REVIEWS_RECORDED','units':[r['unit'] for r in rows],
            'acceptance':False,'scope':'Host appearance observations supplement numerical non-regression; program verifies coverage and current evidence, not subjective truth'}

def measure(task,state,candidate,unit,row):
    from .icon_clarity import _crop
    from .icon_hd import profile
    from .execution_contract import resource
    guard=row.get('preservation')
    if not guard or guard.get('schema')!=VERSION or guard.get('basis')!=basis(state,unit,row):
        raise ValueError('Program-frozen appearance comparators are required before HD refinement')
    if not guard.get('baselines'):raise ValueError('An empty preservation inventory cannot pass')
    guard=freeze(task,state,candidate,unit,row,guard);row=copy.deepcopy(row);row['preservation']=guard
    saved_render(task,candidate)
    limits=profile()['styles'][row['target']['profile']]['preservation']
    source=_crop(task,state,unit['roi']);actual=_crop(task,state,unit['roi'],candidate);after=values(source,actual)
    comparisons=[]
    for entry in guard['baselines']:
        old=entry['candidate']
        saved_render(task,old)
        before=values(source,_crop(task,state,unit['roi'],old));checks=paired_checks(before,after,limits)
        comparisons.append({'pptx_hash':old['pptx']['sha256'],'reason':entry['reason'],
                            'checks':checks,'passed':all(c['passed'] for c in checks)})
    materials=[]
    if row['target']['profile']=='shaded':
        for patch in row['target']['smooth_patches']:
            result=shading_checks(_crop(task,state,patch['roi']),_crop(task,state,patch['roi'],candidate),profile()['material_preservation'])
            materials.append({'id':patch['id'],'against':'unchanged_original',**result})
            for entry in guard['baselines']:
                result=shading_checks(_crop(task,state,patch['roi'],entry['candidate']),_crop(task,state,patch['roi'],candidate),profile()['material_preservation'])
                materials.append({'id':patch['id']+':'+entry['candidate']['pptx']['sha256'][:12],'against':'retained_comparator',**result})
    review=review_status(task,state,candidate,unit,row)
    return {'schema':VERSION,'numeric_pass':all(r['passed'] for r in comparisons+materials),
            'passed':all(r['passed'] for r in comparisons+materials) and review['passed'],'review':review,
            'comparisons':comparisons,'materials':materials,'current_source_metrics':after,
            'comparator_inventory':guard,
            'scope':'Non-compensating same-original-window appearance and material proxies; source semantics and contextual visual review remain separate mandatory gates'}
