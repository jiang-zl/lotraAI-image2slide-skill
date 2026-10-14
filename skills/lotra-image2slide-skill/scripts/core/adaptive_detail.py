"""Source-calibrated, local discrepancy triage with contextual re-observation.

Numbers schedule source interpretation; they do not certify semantic truth.
Frozen source controls never use candidate pixels to loosen thresholds.
"""
import copy, math, hashlib
from pathlib import Path
import numpy as np
from scipy.ndimage import gaussian_filter, distance_transform_edt, label, find_objects
from .common import identity, digest, read_json, write_json, safe_path, writer

VERSION='adaptive-source-detail-1'
# Loss bands are engineering triage settings, not paper-derived pass scores.
# The maximum of the finite source-only control losses is used, not a claim
# about a population false-positive rate or a fitted candidate distribution.
BANDS={
    'geometry': {'ssim_loss': [.18,.38], 'edge_loss': [.15,.35], 'rgb_error': [.10,.24]},
    'illustrative': {'ssim_loss': [.30,.65], 'edge_loss': [.24,.50], 'rgb_error': [.17,.32]},
    'texture': {'ssim_loss': [.36,.72], 'edge_loss': [.35,.65], 'rgb_error': [.20,.40]},
    'curve': {'ssim_loss': [.22,.45], 'edge_loss': [.16,.38], 'rgb_error': [.12,.26]},
}
POLICY={'schema':VERSION,'calibration_revision':2,'bands':BANDS,'control_margin':.035,'edge_tolerance_source_px':1.5,
        'local_window_source_px':24,'local_stride_source_px':12,'missing_edge_cluster_min_pixels':4,
        'local_missing_edge_fraction':.35,'packet_batch':6,'detail_display_scale':4,
        'controls':['blur_.35','blur_.6','shift_x_.35','shift_y_.35','contrast_.97','contrast_1.03'],
        'trigger_rule':'severe class-specific similarity loss, joint structural/photometric loss, or a localized interior missing-edge clue',
        'threshold_role':'re-observation only; source facts and hard structure remain noncompensating'}

def profile(state,unit):
    if unit.get('refinement_profile'):return unit['refinement_profile']
    if unit['profile'] in ('text','formula','relation'):return unit['profile']
    policies=state.get('quality_intent',{}).get('items',[])
    relevant=[p for p in policies if unit['id'] in p.get('quality_units',[])]
    parents={p['id']:p for p in policies}
    if relevant:
        p=min(relevant,key=lambda p:len(p['objects']))
        parent=parents.get(p.get('semantic_parent'),{})
        purpose=parent.get('purpose',p.get('purpose'))
        if purpose=='illustrative':return 'illustrative'
        if purpose in ('texture','raster','photo'):return 'texture'
        if purpose in ('text','formula','relation'):return purpose
    return 'curve' if unit['profile']=='curve' else 'geometry'

def _box(roi,size):
    if len(roi)!=4 or not all(math.isfinite(v) for v in roi) or min(roi[2:])<=0:raise ValueError('Finite positive original window required')
    x,y,w,h=roi
    if x<0 or y<0 or x+w>size[0]+1 or y+h>size[1]+1:raise ValueError('Original detail window outside canvas')
    return (max(0,math.floor(x)),max(0,math.floor(y)),min(size[0],math.ceil(x+w)),min(size[1],math.ceil(y+h)))

def _edges(data):
    g=data@np.array([.2126,.7152,.0722])
    return np.hypot(gaussian_filter(g,.6,order=(0,1)),gaussian_filter(g,.6,order=(1,0)))>.06

def metrics(first,second):
    from .appearance_metrics import image_values
    values=image_values(first,second);a,b=_edges(first),_edges(second)
    tol=POLICY['edge_tolerance_source_px']
    da=distance_transform_edt(~a) if a.any() else np.full(a.shape,np.inf)
    db=distance_transform_edt(~b) if b.any() else np.full(b.shape,np.inf)
    missing=a & (db>tol);extra=b & (da>tol)
    recall=1-float(missing.sum())/max(1,int(a.sum()))
    precision=1-float(extra.sum())/max(1,int(b.sum()))
    f1=2*precision*recall/max(precision+recall,1e-12) if a.any() or b.any() else 1.
    mse=float(np.mean((first-second)**2))
    values.update(edge_f1=f1,missing_source_edge_pixels=int(missing.sum()),extra_edge_pixels=int(extra.sum()),
                  source_edge_pixels=int(a.sum()),psnr_db=-10*math.log10(mse) if mse>0 else None,
                  psnr_status='EXACT_PIXELS' if mse==0 else 'MEASURED')
    losses={'ssim_loss':None if values['ssim'] is None else 1-values['ssim'],
            'edge_loss':1-f1,'rgb_error':values['mean_absolute_rgb_error']}
    return values,losses,missing,extra

def _controls(data):
    from scipy.ndimage import shift
    yield gaussian_filter(data,(.35,.35,0))
    yield gaussian_filter(data,(.6,.6,0))
    yield shift(data,(0,.35,0),order=1,mode='nearest')
    yield shift(data,(.35,0,0),order=1,mode='nearest')
    yield np.clip((data-.5)*.97+.5,0,1)
    yield np.clip((data-.5)*1.03+.5,0,1)

def source_units(state):
    units=dict(state.get('quality',{}).get('units',{}))
    for uid,unit in state.get('source_detail_units',{}).items():
        if uid in units:raise ValueError('Original detail unit identity collision')
        units[uid]=unit
    return units

def calibration(task,state):
    from .appearance_metrics import canvas
    units=source_units(state)
    basis=identity({'source':state['source'],'policy':POLICY,
                    'units':{u:{'roi':r['roi'],'profile':profile(state,r)} for u,r in units.items()}})
    file=task/'source/detail/calibration'/(basis+'.json')
    if file.is_file():return read_json(file)
    original=canvas(str(safe_path(task,state['source']['path'])),state['source']['sha256'],tuple(state['source_size']))
    rows={}
    for uid,unit in units.items():
        kind=profile(state,unit)
        local_basis=identity({'source':state['source'],'unit':uid,'roi':unit['roi'],'profile':kind,'policy':POLICY})
        if kind not in BANDS:rows[uid]={'basis':local_basis,'profile':kind,'thresholds':{},'route':'existing exact content/AST/connection programs'};continue
        x0,y0,x1,y1=_box(unit['roi'],state['source_size']);data=original[y0:y1,x0:x1]
        controls=[metrics(data,c)[1] for c in _controls(data)]
        thresholds={k:min(bounds[1],max(bounds[0],max([c[k] for c in controls if c[k] is not None] or [0])+POLICY['control_margin'])) for k,bounds in BANDS[kind].items()}
        rows[uid]={'basis':local_basis,'profile':kind,'thresholds':thresholds,'source_control_losses':controls,
                   'source_native_pixels':[x1-x0,y1-y0],'limits':'Finite nuisance-control envelope, not semantic completeness or a population quantile'}
    result={'schema':VERSION,'source_hash':state['source']['sha256'],'basis':basis,'policy':POLICY,'units':rows}
    write_json(file,result);return result

def _regions(missing,source_edges,box):
    """Merge close residual clues; small distinct interior details survive pooling."""
    from scipy.ndimage import binary_dilation
    joined=binary_dilation(missing,iterations=1);regions=[]
    labels,n=label(joined)
    for i,sl in enumerate(find_objects(labels),1):
        if sl is None:continue
        y,x=sl;owned=labels[sl]==i;count=int((missing[sl]&owned).sum())
        if count<POLICY['missing_edge_cluster_min_pixels']:continue
        regions.append({'roi':[box[0]+x.start,box[1]+y.start,x.stop-x.start,y.stop-y.start],
                        'missing_edge_pixels':count,'kind':'missing_original_structure_candidate'})
    win=POLICY['local_window_source_px'];stride=POLICY['local_stride_source_px'];h,w=missing.shape
    for y in range(0,h,stride):
        for x in range(0,w,stride):
            m=missing[y:y+win,x:x+win];a=source_edges[y:y+win,x:x+win];count=int(m.sum())
            ratio=count/max(1,int(a.sum()))
            if count>=4 and ratio>=POLICY['local_missing_edge_fraction']:
                regions.append({'roi':[box[0]+x,box[1]+y,m.shape[1],m.shape[0]],'missing_edge_pixels':count,
                                'missing_edge_fraction':ratio,'kind':'local_original_structure_candidate'})
    return sorted(regions,key=lambda r:-r['missing_edge_pixels'])[:12]

def triggers_for(kind,losses,thresholds,regions,box):
    """Class-specific scheduling, independently from final acceptance.

    A single moderate photometric change is diagnostic. Large SSIM loss still
    schedules interpretation; local interior clues survive a good ROI mean.
    Boundary-only rasterization noise is not a new semantic object by itself.
    """
    flags={k:v for k,v in losses.items() if v is not None and v>thresholds[k]}
    severe=losses.get('ssim_loss') is not None and losses['ssim_loss']>BANDS[kind]['ssim_loss'][1]
    joint='edge_loss' in flags and ('ssim_loss' in flags or 'rgb_error' in flags)
    x,y,w,h=box[0],box[1],box[2]-box[0],box[3]-box[1]
    local=[]
    for r in regions:
        a,b,c,d=r['roi']
        interior=a>x+1 and b>y+1 and a+c<x+w-1 and b+d<y+h-1
        resolved=r['missing_edge_pixels']>=6 and c*d>=9
        if interior and resolved:local.append(r)
    if not (severe or joint or local):return []
    out=[{'metric':k,'loss':v,'trigger_loss':thresholds[k]} for k,v in flags.items()] if severe or joint else []
    if local:out.append({'metric':'localized_interior_source_edge_loss','clues':len(local)})
    return out

def _neighbor_context(state,unit):
    x,y,w,h=unit['roi'];result=[]
    for u in state.get('quality',{}).get('units',{}).values():
        if u['id']==unit['id']:continue
        a,b,c,d=u['roi'];distance=math.hypot(max(a-(x+w),x-(a+c),0),max(b-(y+h),y-(b+d),0))
        if distance<=max(8,min(w,h)*.18):result.append({'unit':u['id'],'roi':u['roi'],'profile':u['profile'],'objects':u['objects']})
    return sorted(result,key=lambda r:r['unit'])[:12]

def scan(task,state,candidate,persist=True):
    from .appearance_metrics import canvas,native_signatures
    if not candidate or not candidate.get('preview'):return {'passed':False,'status':'ACTUAL_RENDER_REQUIRED','items':[],'pending':[]}
    config=calibration(task,state);signatures=native_signatures(str(safe_path(task,candidate['pptx']['path'])),candidate['pptx']['sha256'])
    original=canvas(str(safe_path(task,state['source']['path'])),state['source']['sha256'],tuple(state['source_size']))
    actual=canvas(str(safe_path(task,candidate['preview']['path'])),candidate['preview']['sha256'],tuple(state['source_size']))
    observations=state.get('source_detail',{}).get('observations',{});rows=[];pending=[]
    for uid,unit in source_units(state).items():
        box=_box(unit['roi'],state['source_size']);x0,y0,x1,y1=box;a=original[y0:y1,x0:x1];b=actual[y0:y1,x0:x1]
        values,losses,missing,extra=metrics(a,b);c=config['units'][uid];kind=c['profile'];neighbors=_neighbor_context(state,unit)
        # Actual local paint and related native owners are part of reuse identity.
        # Unrelated whole-file edits do not discard an unchanged source finding.
        basis=identity({'source':state['source']['sha256'],'unit':uid,'roi':unit['roi'],'calibration':c['basis'],
                        'pixels':hashlib.sha256(b.tobytes()).hexdigest(),'native':{n:signatures.get(n) for n in unit['objects']},
                        'relations':{r['unit']:{n:signatures.get(n) for n in r['objects']} for r in neighbors}})
        triggers=[];regions=[]
        if kind in BANDS:
            regions=_regions(missing,_edges(a),box)
            # A local clue is an independent trigger even if the ROI average
            # remains high. It asks the model to interpret, not to label pixels.
            triggers=triggers_for(kind,losses,c['thresholds'],regions,box)
        prior=observations.get(uid);current=bool(prior and prior.get('basis')==basis)
        needs=bool(triggers) and not current
        row={'id':uid,'profile':kind,'roi':unit['roi'],'objects':unit['objects'],'basis':basis,'metrics':values,
             'thresholds':c['thresholds'],'triggers':triggers,'regions':regions,'neighbors':neighbors,
             'status':'CONTEXT_REOBSERVATION_REQUIRED' if needs else ('CURRENT_CONTEXT_OBSERVED' if triggers else 'NO_TRIAGE_TRIGGER'),
             'observation':prior if current else None,'passed':not needs}
        rows.append(row)
        if needs:pending.append(row)
    result={'schema':VERSION,'source_hash':state['source']['sha256'],'candidate_hash':candidate['pptx']['sha256'],
            'preview_hash':candidate['preview']['sha256'],'calibration_basis':config['basis'],'passed':not pending,
            'status':'ADAPTIVE_SOURCE_CONTEXT_CURRENT' if not pending else 'SOURCE_DETAIL_REOBSERVATION_REQUIRED',
            'items':rows,'pending':[r['id'] for r in pending],
            'limits':'Every source unit scanned; no-trigger is not a proof of semantic completeness. Original recursion, exact contents, feature/relationship contracts and actual native ownership independently gate acceptance.'}
    if persist:
        file=task/'source/detail/scans'/(identity(result)+'.json');write_json(file,result)
        state['source_detail_scan']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    return result

def _view(task,state,roi,source,candidate):
    from .quality_intent import source_view
    from .quality_observations import candidate_view
    if source:return source_view(task,state,roi,POLICY['detail_display_scale'])
    return candidate_view(task,state,candidate,{'roi':roi})

def enhanced_view(task,state,roi,candidate):
    """Auditable viewing aid; immutable original pixels remain the authority."""
    from PIL import Image,ImageOps,ImageFilter
    raw=_view(task,state,roi,True,candidate)
    pipeline={'autocontrast_cutoff_percent':1,'unsharp_radius_display_px':.7,'unsharp_percent':100,'unsharp_threshold':2}
    key=identity({'original':raw,'pipeline':pipeline});file=task/'source/detail/views'/(key+'.png')
    if not file.is_file():
        file.parent.mkdir(parents=True,exist_ok=True)
        with Image.open(safe_path(task,raw['path'])) as im:
            ImageOps.autocontrast(im.convert('RGB'),cutoff=1).filter(ImageFilter.UnsharpMask(radius=.7,percent=100,threshold=2)).save(file)
    return {'path':file.relative_to(task).as_posix(),'sha256':digest(file),'derived_from_original':raw,
            'pipeline':pipeline,'authority':'display_aid_only; support every identified part again in unchanged original pixels'}

def packet(task,state,candidate=None,force_units=None):
    candidate=candidate or state.get('active_candidate') or state.get('selected')
    if not candidate or not candidate.get('preview'):return None
    result=scan(task,state,candidate)
    from .detail_contracts import checks_report
    failed_facts={r['id']:r for r in checks_report(task,state,candidate)['items'] if not r['passed']}
    pending=set(result['pending'])|set(failed_facts)|set(force_units or [])
    if not pending:return None
    units=source_units(state);rows=[]
    ordered=sorted(result['items'],key=lambda r:r['id'] not in set(force_units or []))
    for item in ordered:
        if item['id'] not in pending:continue
        unit=units[item['id']];parent=next((c for c in state['analysis']['components'] if c['id']==unit['owner']),None)
        details=[]
        for region in item['regions'][:4]:
            details.append({**region,'original_view':_view(task,state,region['roi'],True,candidate),'actual_view':_view(task,state,region['roi'],False,candidate)})
        rows.append({k:item[k] for k in ('id','profile','roi','basis','thresholds','metrics','triggers','objects','neighbors')})
        parent_roi=units.get(unit.get('parent_source_unit'),{}).get('roi') or (parent['roi'] if parent else None)
        rows[-1].update(original_view=_view(task,state,item['roi'],True,candidate),enhanced_original_view=enhanced_view(task,state,item['roi'],candidate),actual_view=_view(task,state,item['roi'],False,candidate),
                        parent={'id':unit.get('parent_source_unit') or parent['id'],'roi':parent_roi,'original_view':_view(task,state,parent_roi,True,candidate)} if parent_roi else None,
                        detail_candidates=details,prior_source_facts=unit['features'])
        failure=failed_facts.get(item['id'])
        rows[-1]['phase']='local_repair_required' if failure else 'source_reobservation_required'
        rows[-1]['failed_detail_predicates']=failure
        if len(rows)==POLICY['packet_batch']:break
    from .source_observability import POLICY as observability_policy
    return {'kind':'adaptive_source_detail','schema':VERSION,'source_hash':state['source']['sha256'],
            'candidate_hash':candidate['pptx']['sha256'],'items':rows,'remaining':len(pending),
            'source_observability_policy':observability_policy,
            'return':'items[{id,basis,original_view_sha256,source_observability:{kind:clear_structure|blurred_illustration|stochastic_texture|subpixel_detail|unresolved,source_evidence,uncertainty_regions:[]},observed_parts[{id,roi,observed,objects,connection_role}],relations[],diagnosis,resolution:restore_structure|appearance_only|uncertain,evidence,checks[]}]',
            'instruction':'Inspect original detail with parent and related owner context. Locate every new/missing feature. Meaning and subdivision are host decisions; execute and verify through typed source detail contracts, not prose matched. Appearance-only findings still need actual source-part bindings and numeric checks.'}

def bind(task,request,_state=None):
    from . import agent_runtime as a
    from .detail_contracts import validate_checks,merge_facts
    task,state=a._state(task) if _state is None else (task,_state)
    candidate=state.get('active_candidate') or state['selected']
    if request.get('source_hash')!=state['source']['sha256'] or request.get('candidate_hash')!=candidate['pptx']['sha256']:raise ValueError('Current original/result identities required')
    current={r['id']:r for r in scan(task,state,candidate)['items']};rows=request.get('items',[])
    from .boundary_geometry import saved_nodes
    from .source_observability import validate as validate_observability
    nodes=saved_nodes(safe_path(task,candidate['pptx']['path']),state['source_size'])
    if not rows or len({r['id'] for r in rows})!=len(rows):raise ValueError('Distinct located source observations required')
    ledger=copy.deepcopy(state.get('source_detail',{'schema':VERSION,'observations':{},'history':[]}))
    validated=[]
    for row in rows:
        item=current[row['id']];view=_view(task,state,item['roi'],True,candidate)
        if row.get('basis')!=item['basis'] or row.get('original_view_sha256')!=view['sha256']:raise ValueError('Source detail evidence is stale')
        if row.get('resolution') not in ('restore_structure','appearance_only','uncertain') or not row.get('diagnosis') or not row.get('evidence'):raise ValueError('Located truthful diagnosis required')
        parts=row.get('observed_parts',[])
        if not parts or not row.get('checks'):raise ValueError('Prose agreement cannot close a detail packet; source parts and executable checks required')
        for p in parts:
            _box(p['roi'],state['source_size'])
            if not p.get('id') or not p.get('observed') or not p.get('objects'):raise ValueError('Each original part needs a saved-object binding')
            if p.get('connection_role') not in ('none','internal_geometry','scientific_connection','uncertain'):
                raise ValueError('Classify new source lines/parts before retaining an earlier scientific connection survey')
            x,y,w,h=p['roi'];a0,b0,c0,d0=item['roi']
            if x<a0-1 or y<b0-1 or x+w>a0+c0+1 or y+h>b0+d0+1:raise ValueError('Part escaped source child; declare external relation separately')
        validate_checks(row['checks'],state['source_size'])
        from .icon_detail import validate_children
        validate_children(task,state,item,row)
        validate_observability(row,{**source_units(state)[row['id']],**item},nodes,state)
        checked={n for c in row['checks'] for n in c.get('objects',[])} | {c[k] for c in row['checks'] for k in ('object','a','b') if k in c}
        if {n for p in parts for n in p['objects']}-checked:raise ValueError('Every observed source part requires its own executable output check')
        record=copy.deepcopy(row);record.update(source_hash=state['source']['sha256'],candidate_at_observation=candidate['pptx']['sha256'],
                                               original_view=view,original_roi=item['roi'],trigger_context={k:item[k] for k in ('regions','metrics','triggers','neighbors')})
        if row['resolution']=='uncertain':record['basis']=None
        previous=ledger['observations'].get(row['id'])
        if previous and {k:v for k,v in previous.items() if k!='candidate_at_observation'}=={k:v for k,v in record.items() if k!='candidate_at_observation'}:
            continue
        if previous:ledger['history'].append(previous)
        ledger['observations'][row['id']]=record;validated.append(record)
    def commit():
        state['source_detail']=ledger
        if validated:
            merge_facts(task,state,validated)
            from .icon_detail import record
            record(state,validated)
        state.pop('quality_result',None);state.pop('acceptance',None)
        a._event(task,'adaptive_source_detail_observed',{'units':[r['id'] for r in validated]})
    if _state is None:
        with writer(task):commit();a._save(task,state)
    else:commit()
    return {'status':'ORIGINAL_DETAIL_FACTS_RETAINED','units':[r['id'] for r in validated]}

def command(task,operation,request=None):
    from . import agent_runtime as a
    task,state=a._state(task);candidate=state.get('active_candidate') or state.get('selected')
    if operation=='observe':return bind(task,request or {})
    if operation=='children':
        from .icon_detail import child_views
        return child_views(task,state,candidate,request or {})
    if operation=='next':
        result=packet(task,state,candidate) or {'status':'NO_PENDING_SOURCE_DETAIL_CONTEXT'}
    elif operation=='scan':result=scan(task,state,candidate)
    elif operation=='report':
        from .detail_contracts import report
        result=report(task,state,candidate)
    else:raise ValueError('Unknown source detail operation')
    with writer(task):a._save(task,state)
    return result
