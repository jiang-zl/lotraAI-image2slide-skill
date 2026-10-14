"""Low-clarity diagnosis, original-only enhancement views and reconstruction debt.

No enhanced raster becomes source truth or a delivered icon. Original SSIM /
PSNR remain diagnostics. Native reconstruction, source structure and current
semantic observations stay hard checks in the same local/whole loop.
"""
import copy,math
import numpy as np
from PIL import Image,ImageOps,ImageFilter
from scipy.ndimage import sobel,laplace
from .common import digest,identity,read_json,write_json,safe_path,writer

VERSION='icon-clarity-3'
PROFILES={'three_dimensional','illustration','structured','detail','scene'}

def statistics(image):
    a=np.asarray(image.convert('L'),float)/255.
    if min(a.shape)<1:raise ValueError('Empty source samples cannot measure clarity')
    gx=sobel(a,axis=1)/8;gy=sobel(a,axis=0)/8;g=np.hypot(gx,gy)
    contrast=float(np.percentile(a,95)-np.percentile(a,5));edge=g>max(.015,contrast*.12)
    gradient_energy=float(np.mean(g*g));curvature=float(np.mean(laplace(a)**2))
    # This ratio estimates high-frequency edge response; report its measured
    # support so blank/stochastic fields cannot pretend to be a clear icon.
    return {'samples':list(image.size),'contrast':contrast,'edge_support_fraction':float(edge.mean()),
        'gradient_energy':gradient_energy,'curvature_energy':curvature,
        'edge_sharpness':curvature/max(gradient_energy,1e-12),'saturated_fraction':float(((a<.003)|(a>.997)).mean())}

def _crop(task,state,roi,candidate=None):
    from .execution_contract import resource
    ref=state['source'] if candidate is None else candidate['preview']
    from .resource_facts import image_dimensions,image_region
    path=resource(task,ref)
    width,height=image_dimensions(path,ref['sha256'])
    sx,sy=width/state['source_size'][0],height/state['source_size'][1]
    # A fixed native canvas is quantized to integer preview pixels. Verify
    # that arithmetic directly; a scale-ratio epsilon wrongly rejects a
    # legitimate half-pixel rounding (e.g. 1600 by 742 for 1280 by 594).
    if abs(height-width*state['source_size'][1]/state['source_size'][0])>.500001:
        raise ValueError('Actual clarity comparison must keep the original canvas ratio within integer-pixel rounding')
    x,y,w,h=roi;box=(round(x*sx),round(y*sy),round((x+w)*sx),round((y+h)*sy))
    # Same frozen displayed size, no registration/crop search/blur-to-match.
    return image_region(path,[('crop',box),('resize',(max(3,round(w)),max(3,round(h))),Image.Resampling.LANCZOS)],ref['sha256'])

def eligible(state):
    # A semantic profile cannot opt an original part out of the survey.
    return {u['id']:u for u in state.get('quality',{}).get('units',{}).values() if u.get('roi') and u.get('objects')}

def _flags(stat):
    return {'few_samples':min(stat['samples'])<32,'low_contrast':stat['contrast']<.20,
            'diffuse_edges':stat['edge_sharpness']<1.0 and stat['edge_support_fraction']>.01}

def discover(task,state,candidate):
    from .icon_hd import source_survey,profile
    rows=[]
    for uid,u in eligible(state).items():
        stat=statistics(_crop(task,state,u['roi']))
        rows.append({'unit':uid,'objects':u['objects'],'roi':u['roi'],'source_statistics':stat,
            'diagnostic_flags':_flags(stat),
            'meaning_decision':'Model must distinguish noise/texture from an identifiable icon; no sharpness scalar can decide meaning'})
    return {'kind':'icon_clarity_source','schema':VERSION,'action':'icon-clarity bind','source_hash':state['source']['sha256'],'items':rows,
        'source_survey':source_survey(task,state),'hd_profile':profile(),
        'return':'Classify every original unit AND every fixed original window. Suspect clear/exempt decisions need a second unchanged parent/neighbor-context review. Clear and blurred icons require native-vector multi-scale targets, original features and complete executable relations. Enhancement is diagnostic only.'}

def enhance(task,state,unit):
    u=eligible(state)[unit];im=_crop(task,state,u['roi']);basis=identity({'source':state['source'],'unit':unit,'roi':u['roi'],'pipeline':VERSION})
    folder=task/'views/icon-clarity'/basis;folder.mkdir(parents=True,exist_ok=True)
    specs=[('nearest',{'scale':4,'resampling':'nearest','interpretation':'sample visibility; no added source facts'}),
           ('contrast',{'scale':4,'resampling':'lanczos','autocontrast_cutoff':1}),
           ('edge',{'scale':4,'resampling':'lanczos','autocontrast_cutoff':1,'unsharp_radius':1.,'unsharp_percent':80,'unsharp_threshold':3})]
    views=[]
    for name,parameters in specs:
        file=folder/(name+'.png')
        if not file.exists():
            img=im.resize((im.width*4,im.height*4),Image.Resampling.NEAREST if name=='nearest' else Image.Resampling.LANCZOS)
            if name!='nearest':img=ImageOps.autocontrast(img,cutoff=1)
            if name=='edge':img=img.filter(ImageFilter.UnsharpMask(radius=1.,percent=80,threshold=3))
            img.save(file)
        views.append({'path':file.relative_to(task).as_posix(),'sha256':digest(file),'parameters':parameters})
    result={'schema':VERSION,'unit':unit,'source_hash':state['source']['sha256'],'source_roi':u['roi'],'views':views,
        'diagnostic_only':True,'warning':'Interpolation and sharpening can create halos or apparent features. Confirm all semantic facts against the unchanged original and its context.'}
    write_json(folder/'Enhancement-receipt.json',result)
    return result

def bind(task,state,candidate,request):
    from .recursive_containment import source_view
    from .icon_hd import validate_target,source_survey,profile,closure
    from .boundary_geometry import saved_nodes
    from .execution_contract import resource
    if request.get('schema')!=VERSION or request.get('source_hash')!=state['source']['sha256']:raise ValueError('Original clarity inventory required')
    rows=request.get('items',[]);units=eligible(state)
    if len({r['unit'] for r in rows})!=len(rows) or {r['unit'] for r in rows}!=set(units):raise ValueError('Classify every source icon candidate, not only reported defects')
    windows=source_survey(task,state);survey=request.get('source_survey',[])
    if len({r.get('id') for r in survey})!=len(survey) or {r.get('id') for r in survey}!={r['id'] for r in windows}:
        raise ValueError('Every fixed original window requires a semantic coverage decision')
    for r,w in zip(sorted(survey,key=lambda v:v['id']),sorted(windows,key=lambda v:v['id'])):
        if r.get('pixel_hash')!=w['pixel_hash'] or not r.get('source_evidence') or r.get('decision') not in ('covered','empty','unresolved'):
            raise ValueError('Original window review must retain exact pixels and uncertainty')
        if r['decision']=='covered' and (not r.get('units') or not set(r['units'])<=set(units)):
            raise ValueError('Missing source objects must be registered before coverage can close')
        if r['decision']=='empty' and w['edge_support']>.005:
            raise ValueError('A source window containing edges cannot be declared empty')
        for uid in r.get('units',[]):
            a,b,c,d=units[uid]['roi'];x,y,wid,hei=w['roi']
            if min(a+c,x+wid)<=max(a,x) or min(b+d,y+hei)<=max(b,y): raise ValueError('Window coverage refers to an unrelated source position')
    nodes=saved_nodes(resource(task,candidate['pptx']),state['source_size']) if candidate else {}
    prior=read_json(resource(task,state['icon_clarity_contract'])) if state.get('icon_clarity_contract') else {}
    prior_rows={r['unit']:r for r in prior.get('items',[])}
    actual=set().union(*(closure(nodes,u['objects']) for u in units.values())) if nodes and units else set()
    if nodes and actual!=set(nodes):raise ValueError('Classify the union of original units and every saved native descendant; unbound owners require source registration')
    for r in rows:
        if r.get('category') not in ('clear_icon','blurred_icon','texture','photo','not_icon','unresolved') or not r.get('source_evidence'):raise ValueError('Original type-specific clarity decision required')
        source_view(task,state,r['source_view'])
        stat=statistics(_crop(task,state,units[r['unit']]['roi']))
        if any(_flags(stat).values()) and r['category'] in ('clear_icon','texture','photo','not_icon'):
            review=r.get('suspicion_review',{})
            if not review.get('reason') or review.get('observability') not in ('identifiable_structure','stochastic_texture','photo','non_icon'):
                raise ValueError('A numerical suspicion cannot be silently dismissed by a semantic category')
            source_view(task,state,review.get('source_context'))
            a,b,c,d=review['source_context']['roi'];x,y,w,h=units[r['unit']]['roi']
            whole_canvas=[x,y,w,h]==[0,0,*state['source_size']]
            if a>x or b>y or a+c<x+w or b+d<y+h or (c*d<=w*h and not whole_canvas):
                raise ValueError('Suspicion review must enlarge the original with parent/neighbor context')
            expected={'clear_icon':'identifiable_structure','texture':'stochastic_texture','photo':'photo','not_icon':'non_icon'}[r['category']]
            if review['observability']!=expected:raise ValueError('Clarity category contradicts the contextual source decision')
        if r['category'] in ('blurred_icon','clear_icon'):
            validate_target(r,units[r['unit']])
            t=r.get('target',{})
            if not r.get('structure_features') or not isinstance(r.get('relations'),list) or t.get('representation')!='editable_vector':raise ValueError('Blurred icon needs a structure/relationship-preserving editable reconstruction target')
            known={f['id'] for f in units[r['unit']].get('features',[])}
            if not set(r['structure_features'])<=known:raise ValueError('Freeze actual original structure IDs before reconstruction')
            if r['category']=='blurred_icon' and (t.get('min_sharpness_gain',0)<1.05 or t.get('min_sharpness_gain',0)>2.):raise ValueError('Freeze a bounded measurable clarity improvement before candidate optimization')
            if not .01<=t.get('min_edge_support',0)<=.5:raise ValueError('A sharp empty field is not a rebuilt icon')
            r['original_statistics']=statistics(_crop(task,state,units[r['unit']]['roi']))
            from .icon_preservation import freeze
            r['preservation']=freeze(task,state,candidate,units[r['unit']],r,prior_rows.get(r['unit'],{}).get('preservation'))
    request['hd_configuration_hash']=identity(profile())
    file=task/'source/icon-clarity'/('contract-'+identity(request)+'.json');write_json(file,request)
    state.setdefault('icon_clarity_history',[]).append(copy.deepcopy(state.get('icon_clarity_contract')))
    state['icon_clarity_contract']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    from .icon_detail import schedule as schedule_detail
    schedule_detail(state,candidate,{'items':[r for r in rows if r['category'] in ('clear_icon','blurred_icon')]},mandatory=True)
    state.pop('acceptance',None);state.pop('quality_result',None)
    return {'status':'ORIGINAL_ICON_CLARITY_BOUND','required':len(rows),'blurred':sum(r['category']=='blurred_icon' for r in rows),'quality_acceptance':False}

def report(task,state,candidate,context=None):
    from .execution_contract import resource
    ref=state.get('icon_clarity_contract');units=eligible(state)
    if not units:return {'schema':VERSION,'passed':False,'status':'ORIGINAL_SURVEY_REQUIRED','items':[],'reason':'An empty registration is not evidence that the original has no icons'}
    if not ref:return {'schema':VERSION,'passed':False,'status':'SOURCE_BINDING_REQUIRED','items':[],'next':'icon-clarity discover'}
    c=read_json(resource(task,ref));rows=[];ctx=context or {}
    from .icon_hd import profile,measure,source_survey
    if c.get('schema')!=VERSION or c.get('hd_configuration_hash')!=identity(profile()):
        return {'schema':VERSION,'passed':False,'status':'HD_SOURCE_REBIND_REQUIRED','items':[],'next':'icon-clarity discover'}
    known={r['unit'] for r in c['items']}
    if known!=set(units) or c['source_hash']!=state['source']['sha256']:raise ValueError('Original clarity coverage changed; explicit new original reading required')
    from .icon_hd import closure
    from .boundary_geometry import saved_nodes
    nodes=saved_nodes(resource(task,candidate['pptx']),state['source_size'])
    from .icon_detail import report as detail_report
    original_children=detail_report(task,state,candidate,nodes)
    required_children={r['unit'] for r in c['items'] if r['category'] in ('clear_icon','blurred_icon')}
    missing_children=required_children-set(state.get('icon_detail_requirements',{}).get('units',{}))
    if missing_children:
        original_children={'passed':False,'items':original_children.get('items',[]),'missing_source_child_contracts':sorted(missing_children)}
    covered=set().union(*(closure(nodes,u['objects']) for u in units.values()))
    if covered!=set(nodes):
        rows.append({'id':'actual-native-clarity-coverage','passed':False,'status':'NATIVE_SOURCE_REGISTRATION_REQUIRED','objects':sorted(set(nodes)-covered)})
    for r in c['items']:
        row={'id':'clarity:'+r['unit'],'unit':r['unit'],'category':r['category'],'passed':False,'status':'required_unmeasured'}
        if r['category'] in ('texture','photo','not_icon'):
            row.update(passed=True,status='EVIDENCED_NOT_APPLICABLE',reason='Original category does not require deblurring reconstruction; its own content/appearance checks remain mandatory')
        elif r['category']=='unresolved':row['next_action']='source-detail scan/next/observe with enhanced original context'
        else:
            try:
                source=statistics(_crop(task,state,units[r['unit']]['roi']));actual=statistics(_crop(task,state,units[r['unit']]['roi'],candidate))
                gain=actual['edge_sharpness']/max(source['edge_sharpness'],1e-12);target=r['target']
                policy=[p for p in ctx.get('appearance',[]) if r['unit'] in p.get('quality_units',[])]
                content=bool(policy) and all(p.get('passed') is True for p in policy)
                features=[f for f in ctx.get('features',{}).get('items',[]) if f.get('unit')==r['unit']]
                structure=bool(features) and all(f.get('passed') is True for f in features)
                native=[v for v in ctx.get('native',[]) if v.get('object') in units[r['unit']]['objects']]
                editable=bool(native) and all(v.get('passed') is True for v in native)
                sem=[p for p in ctx.get('host',[]) if r['unit'] in next((i['quality_units'] for i in state.get('quality_intent',{}).get('items',[]) if i['id']==p['id']),[])]
                semantic=bool(sem) and all(v.get('passed') is True for v in sem)
                hd=measure(task,state,candidate,units[r['unit']],r,nodes)
                from .icon_preservation import measure as preservation_measure
                preservation=preservation_measure(task,state,candidate,units[r['unit']],r)
                required=target.get('min_sharpness_gain',1.) if r['category']=='blurred_icon' else None
                row.update(source_statistics=source,actual_statistics=actual,sharpness_gain=gain,required_gain=required,hd=hd,preservation=preservation,
                    structure_pass=structure,content_appearance_pass=content,editability_pass=editable,semantic_pass=semantic,
                    sharpness_gain_applicability='Whole-window curvature/gradient ratio is diagnostic; source-located paired edge-spread gains are mandatory for blurred icons',
                    passed=actual['edge_support_fraction']>=target['min_edge_support'] and hd['passed'] and preservation['passed'] and structure and content and editable and semantic,
                    next_action='Existing object-loop source reconstruction/native proposal with current whole recheck',source_contract=ref)
                row['status']='MEASURED_PASS' if row['passed'] else 'MEASURED_FAIL'
                if hd.get('measurement_valid') is False:
                    row.update(status='MEASUREMENT_INVALID',next_action='icon-clarity probe-review')
            except (ValueError,KeyError,TypeError,FileNotFoundError) as exc:row['reason']=str(exc)
        rows.append(row)
    windows=source_survey(task,state);survey=c.get('source_survey',[])
    survey_pass={r['id']:r['pixel_hash'] for r in survey}=={r['id']:r['pixel_hash'] for r in windows} and all(r['decision']!='unresolved' for r in survey)
    rows.append({'id':'whole-source-windows','passed':survey_pass,'status':'PASS' if survey_pass else 'SOURCE_WINDOW_REVIEW_REQUIRED'})
    if not original_children['passed']:
        rows.append({'id':'mandatory-original-icon-children','passed':False,'status':'SOURCE_CHILD_OR_RESULT_CHECK_REQUIRED','detail':original_children})
    return {'schema':VERSION,'passed':all(r['passed'] for r in rows),'status':'PASS' if all(r['passed'] for r in rows) else 'WORK_REQUIRED','items':rows,
        'source_children':original_children,
        'source_contract':ref,'scope':'No blurry-source imitation; original SSIM/PSNR, clear output and source semantics are separate. A sharpness gain never compensates missing anatomy or editability.'}

def probe_review(task,state,candidate,measured=None):
    """Diagnose current edge evidence before authorizing any changed probe."""
    from .workflow_control import current_report
    from .execution_contract import resource
    from .icon_detail import child_context
    from .quality_intent import source_view as original_view
    checked,stale=current_report(task,state,candidate)
    if stale or checked is None:raise ValueError('Run the current whole quality check before edge-probe diagnosis')
    clarity=checked['gates']['icon_clarity']
    if measured is not None and measured!=clarity:raise ValueError('Probe diagnosis must use its exact registered checker result')
    contract=read_json(resource(task,state['icon_clarity_contract']))
    by={r['unit']:r for r in contract['items']};units=eligible(state);rows=[]
    for row in clarity.get('items',[]):
        if row.get('hd',{}).get('measurement_valid') is not False:continue
        uid=row['unit'];failures=row['hd']['measurement_failures']
        source_invalid=sorted({r['id'] for r in failures if r['domain']=='source'})
        display=child_context(task,state,units[uid]['roi'],candidate)
        raw=original_view(task,state,display['roi'],1)
        rows.append({'unit':uid,'objects':units[uid]['objects'],'failures':failures,
            'edge_probes':copy.deepcopy(by[uid]['target']['edge_probes']),
            'source_context':raw,'source_display':display,
            'allowed_probe_changes':source_invalid,
            'route':'icon-clarity rebind-probes' if source_invalid else 'actual-boundary-or-sampling repair with current native/capture contracts',
            'rule':'A valid original probe is frozen. Missing candidate contrast or a displaced candidate edge never authorizes moving it to improve the score.'})
    return {'kind':'icon_edge_measurement_diagnosis','action':'icon-clarity probe-review',
        'source_hash':state['source']['sha256'],'baseline_hash':candidate['pptx']['sha256'],
        'check_report':state['quality_result'],'source_contract':state['icon_clarity_contract'],
        'items':rows,'quality_acceptance':False,
        'return':'For invalid ORIGINAL probes only: rebind-probes{source_hash,baseline_hash,check_report,source_contract,unit,source_context,reason,edge_probes}. Retain IDs and every valid probe. Otherwise repair actual rendering/sampling or source-owned native anatomy through existing actions, then recheck.'}


def rebind_probes(task,state,candidate,request):
    """Change invalid source probe locations; all anatomy/targets stay exact."""
    from .execution_contract import resource
    from .recursive_containment import source_view
    from .icon_hd import validate_target,edge_profile
    from .resource_facts import image_region
    import math,numpy as np
    if set(request)-{'source_hash','baseline_hash','check_report','source_contract','unit','source_context','reason','edge_probes'}:
        raise ValueError('Probe repair cannot change unrelated source or target fields')
    packet=probe_review(task,state,candidate)
    for key in ('source_hash','baseline_hash','check_report','source_contract'):
        if request.get(key)!=packet[key]:raise ValueError('Current hash-bound probe diagnosis required: '+key)
    row=next((r for r in packet['items'] if r['unit']==request.get('unit')),None)
    if not row or not row['allowed_probe_changes'] or not request.get('reason'):
        raise ValueError('Only diagnosed invalid original probes may be reobserved')
    if request.get('source_context')!=row['source_context']:raise ValueError('Read the current unchanged original/neighbor context')
    source_view(task,state,request['source_context'])
    old={r['id']:r for r in row['edge_probes']};new=request.get('edge_probes',[])
    if len(new)!=len(old) or {r.get('id') for r in new}!=set(old):raise ValueError('Preserve every probe identity and complete coverage')
    for probe in new:
        if probe['id'] not in row['allowed_probe_changes'] and probe!=old[probe['id']]:
            raise ValueError('Preserve each valid source probe exactly')
    contract=read_json(resource(task,state['icon_clarity_contract']));bound=next(r for r in contract['items'] if r['unit']==row['unit'])
    units=eligible(state);unit=units[row['unit']];bound['target']['edge_probes']=copy.deepcopy(new)
    validate_target(bound,unit)
    x,y,w,h=unit['roi'];width,height=state['source_size']
    box=[math.floor(max(0,x-8)),math.floor(max(0,y-8)),math.ceil(min(width,x+w+8)),math.ceil(min(height,y+h+8))]
    with image_region(resource(task,state['source']),[('crop',box)],state['source']['sha256']) as crop:
        pixels=np.asarray(crop,float)/255.
    checks=[{'id':p['id'],**edge_profile(pixels,{'origin':box[:2],'scale':1},p['points'])} for p in new]
    if any(r.get('valid') is not True for r in checks):raise ValueError('Replacement original probes must have actual bracketed edge crossings')
    file=task/'source/icon-clarity'/('contract-'+identity(contract)+'.json');write_json(file,contract)
    state.setdefault('icon_clarity_history',[]).append(copy.deepcopy(state['icon_clarity_contract']))
    state['icon_clarity_contract']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    state.setdefault('icon_probe_rebindings',[]).append({'unit':row['unit'],'check_report':request['check_report'],
        'prior_contract':request['source_contract'],'contract':state['icon_clarity_contract'],'reason':request['reason'],'source_checks':checks})
    state.pop('acceptance',None);state.pop('quality_result',None)
    return {'status':'SOURCE_PROBES_REBOUND_REQUIRES_CURRENT_WHOLE_CHECK','source_contract':state['icon_clarity_contract'],
        'checks':checks,'quality_acceptance':False,'protected':'All valid probes, source anatomy, categories, thresholds, parts, relations, preservation and child obligations retained'}


def dispatch(task,operation,request=None):
    from . import agent_runtime as a
    task,state=a._state(task);candidate=state.get('active_candidate') or state.get('selected');request=request or {}
    if operation=='discover':return discover(task,state,candidate)
    if operation=='enhance':return enhance(task,state,request['unit'])
    if operation=='report':return report(task,state,candidate)
    if operation=='probe-review':return probe_review(task,state,candidate)
    if operation=='rebind-probes':
        result=rebind_probes(task,state,candidate,copy.deepcopy(request))
        with writer(task):a._save(task,state)
        return result
    if operation in ('review','observe'):
        from .icon_preservation import review_packet,observe
        if operation=='review':return review_packet(task,state,candidate)
        result=observe(task,state,candidate,request)
        with writer(task):a._save(task,state)
        return result
    if operation!='bind':raise ValueError('Unknown icon-clarity operation')
    result=bind(task,state,candidate,copy.deepcopy(request))
    with writer(task):a._save(task,state)
    return result
