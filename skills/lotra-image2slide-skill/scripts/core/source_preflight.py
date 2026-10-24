"""Source-only numerical support and explicit layout/material applicability."""
import math
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt,map_coordinates
from .common import digest,identity,write_json,safe_path

POLICY='source-review-1.37.5'


class DecisionRequired(ValueError):
    """A retained original-only failure, with its exact diagnostic resource."""
    def __init__(self,report,reference):
        import json
        self.report=report;self.reference=reference
        super().__init__('SOURCE_OBSERVATION_DECISION_REQUIRED: '+json.dumps(
            {'issues':report['issues'][:12],'evidence':reference},ensure_ascii=False))


def enabled(state):return state.get('source_review_policy')==POLICY


def line_support(image,feature):
    from .line_geometry import flatten
    from .line_verification import _samples,_mask
    source=feature['line'];limits=source['limits'];width=source['stroke']['width']
    points,labels,positions=_samples(source['path']['segments'],.75,max(1e-5,limits['route']/64))
    margin=width[1]/2+limits['route']+2
    lo=np.maximum(0,np.floor(points.min(axis=0)-margin)).astype(int)
    hi=np.minimum(image.size,np.ceil(points.max(axis=0)+margin)+1).astype(int)
    pixels=np.asarray(image.crop((*lo,*hi)).convert('RGB'),np.float32)/255
    mask=_mask(pixels,source['stroke'].get('paint_colour',source['stroke']['colour']),limits['colour'])
    distance=distance_transform_edt(~mask)
    values=map_coordinates(distance,[points[:,1]-lo[1]-.5,points[:,0]-lo[0]-.5],order=1,mode='constant',cval=np.inf)
    visible=np.ones(len(points),bool)
    for hidden in source['visibility']['hidden']:
        sites=np.flatnonzero(labels==hidden['segment'])
        if len(sites):
            q=(positions[sites]-positions[sites[0]])/max(positions[sites[-1]]-positions[sites[0]],1e-12)
            visible[sites[(q>=hidden['range'][0])&(q<=hidden['range'][1])]]=False
    # A route is an uncertain observation, not a line extracted from its own
    # future candidate. Its frozen interval bounds the original support too.
    allowed=width[1]/2+limits['route']+math.sqrt(2)/2
    unsupported=np.flatnonzero(visible&(values>allowed)) if source['stroke']['dash']['kind']=='solid' else np.array([],int)
    lengths=[]
    for segment in source['path']['segments']:
        path,_=flatten([segment],max(1e-5,limits['route']/64))
        lengths.append(float(np.linalg.norm(np.diff(path,axis=0),axis=1).sum()))
    shortest=min(lengths,default=0)
    marker=max((max(end['marker']['width'][1],end['marker']['length'][1]) for end in source['ends']),default=0)
    return {'feature':feature['id'],'passed':not len(unsupported),'source_support_samples':int(visible.sum()),
            'unsupported_samples':int(len(unsupported)),
            'unsupported_sites':points[unsupported[:12]].tolist(),
            'max_source_axis_distance':float(values[visible].max()) if visible.any() and np.isfinite(values[visible]).all() else None,
            'allowed_source_axis_distance':allowed,'shortest_flat_segment_source_px':shortest,
            'isolated_shaft_available':shortest>marker+2*(width[1]+limits['width']+1),
            'terminal_method':'isolated_shaft' if shortest>marker+2*(width[1]+limits['width']+1) else 'joint_short_terminal',
            'source_evidence':source['source_evidence']}


def rectangle_support(image,feature):
    """Edge-location suggestions only; the host still identifies the surface."""
    x,y,w,h=feature['roi'];x0=max(0,int(x));y0=max(0,int(y))
    x1=min(image.width,int(math.ceil(x+w)));y1=min(image.height,int(math.ceil(y+h)))
    search=min(128,max(12,int(w*.15)))
    top=max(0,int(y+h*.25));bottom=min(image.height,int(y+h*.75))
    left=max(0,x0-search);right=min(image.width,x0+search+1)
    if bottom<=top or right-left<3:return {'applicable':False}
    values=np.asarray(image.crop((left,top,right,bottom)).convert('RGB'),np.float32)
    contrast=np.median(np.linalg.norm(values[:,2:]-values[:,:-2],axis=2),axis=0)
    if not len(contrast):return {'applicable':False}
    order=np.argsort(contrast)[-5:][::-1]
    sites=[{'x':int(left+i+1),'median_rgb_change':float(contrast[i])} for i in order]
    local=[item['median_rgb_change'] for item in sites if abs(item['x']-x0)<=3]
    suspicious=sites[0]['median_rgb_change']>=25 and abs(sites[0]['x']-x0)>max(5,w*.025) and max(local,default=0)<sites[0]['median_rgb_change']*.4
    return {'feature':feature['id'],'applicable':True,'diagnostic_only':True,'source_left':x,
            'edge_candidates':sites,'located_reinspection_required':suspicious,
            'scope':'source pixels only; no automatic bbox update or threshold relaxation'}


def layout_candidates(observation):
    """Finite original-observation hints, never instructions to snap or center."""
    rectangles=[f for f in observation['features'] if f.get('form') in ('rect','round_rect')]
    groups=[]
    for axis in (0,1):
        sites=sorted((f['roi'][axis]+f['roi'][axis+2]/2,f['id']) for f in rectangles)
        current=[]
        for coordinate,name in sites:
            if current and coordinate-current[0][0]>3:
                if len(current)>1:groups.append({'axis':axis,'features':[v[1] for v in current],'source_centers':[v[0] for v in current]})
                current=[]
            current.append((coordinate,name))
        if len(current)>1:groups.append({'axis':axis,'features':[v[1] for v in current],'source_centers':[v[0] for v in current]})
    ports=[{'line':f['id'],'end':i,'point':end['point'],'attachment':end['attachment']}
           for f in observation['features'] if f.get('line') for i,end in enumerate(f['line']['ends'])]
    return {'axis_groups':groups,'declared_containers':[{'unit':u['id'],'parent':u.get('parent')}
            for u in observation['units'] if u.get('parent')],'observed_ports':ports,
            'decision_required':'Confirm a source relation or retain intentional offset/free layout. Coordinates remain unchanged.',
            'automatic_alignment':False}


def evaluate(image,observation,include_math=False):
    issues=[];lines=[];rectangles=[];features={row['id']:row for row in observation['features']}
    for feature in features.values():
        if feature['kind'] in ('surface','silhouette','color_region') and feature.get('form') not in (
            'rect','round_rect','ellipse','freeform','perspective','texture'):
            issues.append({'feature':feature['id'],'reason':'ORIGINAL_SURFACE_FORM_REQUIRED'})
        if feature['kind']=='text' or feature['kind']=='math' and (include_math or feature.get('text_appearance')):
            from .text_appearance import validate as validate_text,ink
            try:validate_text(feature);ink(image,feature)
            except ValueError as error:issues.append({'feature':feature['id'],'reason':str(error)})
        if feature.get('line'):
            row=line_support(image,feature);lines.append(row)
            if not row['passed']:issues.append({'feature':feature['id'],'reason':'ORIGINAL_ROUTE_SUPPORT_REQUIRED','probe':row})
        if feature.get('form') in ('rect','round_rect'):
            row=rectangle_support(image,feature);rectangles.append(row)
            if row.get('located_reinspection_required'):
                issues.append({'feature':feature['id'],'reason':'ORIGINAL_BOUNDARY_REINSPECTION_REQUIRED','probe':row})
    layout=observation.get('layout_review',{})
    for domain in ('alignment','containment','connections'):
        value=layout.get(domain,{})
        if value.get('decision') not in ('declared','intentional_irregular','not_applicable') or not value.get('source_evidence'):
            issues.append({'domain':domain,'reason':'LAYOUT_APPLICABILITY_REQUIRED'})
        elif value['decision']=='declared':
            spatial=observation.get('spatial',{})
            supported=(bool(lines) if domain=='connections' else
                       any(row.get('parent') for row in observation['units']) or bool(spatial.get('footprints')) if domain=='containment' else
                       any(row.get('kind','').startswith(('align','center','equal','spacing')) for row in spatial.get('relations',[])))
            if not supported:issues.append({'domain':domain,'reason':'DECLARED_LAYOUT_RELATION_MISSING'})
    material_units={feature['unit'] for feature in features.values() if feature['kind'] in ('surface','silhouette','color_region','band')}
    for unit in observation['units']:
        if unit['id'] not in material_units:continue
        review=unit.get('appearance_review',{})
        for domain in ('fill','depth','corners'):
            item=review.get(domain,{})
            if item.get('decision') not in ('present','absent','not_applicable','uncertain') or not item.get('source_evidence'):
                issues.append({'unit':unit['id'],'domain':domain,'reason':'MATERIAL_APPLICABILITY_REQUIRED'})
            elif item['decision']=='present' and domain=='depth':
                ids=item.get('feature_ids',[])
                if not ids or any(name not in features or features[name]['unit']!=unit['id'] for name in ids):
                    issues.append({'unit':unit['id'],'domain':domain,'reason':'VISIBLE_DEPTH_FEATURES_REQUIRED'})
    from .branch_plan import prepare as prepare_branches
    branch=prepare_branches(observation)
    return {'schema':POLICY,'source_hash':observation['source_hash'],'observation_hash':identity(observation),
            'passed':not issues,'issues':issues,'line_support':lines,'rectangle_diagnostics':rectangles,
            'branch_plan':branch,
            'layout_candidates':layout_candidates(observation),
            'scope':'Original-only feasibility and explicit applicability; no native or final visual qualification'}


def require(task,state,observation):
    if not enabled(state):return None
    source=safe_path(task,state['source']['path'])
    if digest(source)!=state['source']['sha256']:raise ValueError('Original changed before source preflight')
    with Image.open(source) as image:
        report=evaluate(image,observation,include_math=state.get('source_review_policy')=='source-review-1.37.5')
        from PIL import ImageDraw
        overlay=image.convert('RGB');draw=ImageDraw.Draw(overlay)
        for feature in observation['features']:
            x,y,w,h=feature['roi'];draw.rectangle([x,y,x+w,y+h],outline='#1976D2' if feature['kind']=='text' else '#A020A0',width=1)
        for line in report['line_support']:
            for x,y in line['unsupported_sites']:draw.ellipse([x-3,y-3,x+3,y+3],outline='#FF0000',width=2)
        overlay_file=Path(task)/'source'/('Observation-overlay-'+identity(report)+'.png')
        if not overlay_file.exists():overlay.save(overlay_file)
        report['original_overlay']={'path':overlay_file.relative_to(task).as_posix(),'sha256':digest(overlay_file),
                                    'role':'Source-only diagnostic overlay; the unchanged original remains authority'}
    file=Path(task)/'source'/('Observation-preflight-'+identity(report)+'.json')
    if not file.exists():write_json(file,report)
    ref={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    if (Path(task)/'state.json').is_file():
        from .context_control import register_output
        register_output(task,file)
        register_output(task,overlay_file)
    if not report['passed']:raise DecisionRequired(report,ref)
    return ref


def queue_retained_failure(task,state,contract,failure):
    """Use the existing source-decision phase; never adopt the rejected proposal."""
    from . import agent_runtime as a
    from .common import read_json,writer
    current=a._state(task)[1]
    if current.get('source_feature_observation')!=state.get('source_feature_observation'):
        raise ValueError('Original observation changed before source-preflight recovery')
    if current.get('spatial_source_decision'):
        raise ValueError('Resolve the retained original decision before another recovery')
    observed=read_json(safe_path(task,current['source_feature_observation']['path']))
    if failure.report['observation_hash']!=identity(observed):
        raise ValueError('Source-preflight recovery must bind the retained observation')
    by_feature={row['id']:row['unit'] for row in observed['features']}
    units={issue.get('unit') or by_feature.get(issue.get('feature')) for issue in failure.report['issues']}
    feature_ids={issue['feature'] for issue in failure.report['issues'] if issue.get('feature')}
    impacted={row['component'] for row in contract.get('feature_bindings',[])
              if row['feature'] in feature_ids or by_feature.get(row['feature']) in units}
    if None in units:impacted.update(row['id'] for row in contract['components'])
    if not impacted:raise ValueError('Source-preflight failure has no bound source consumer')
    decision={'kind':'source_preflight','source_hash':current['source']['sha256'],
        'prior_observation':current['source_feature_observation'],'evidence':failure.reference,
        'components':sorted(impacted),'issue_count':len(failure.report['issues']),
        'rule':'Correct only diagnosed original rows/domains using prior hashes and located evidence. Retain every unrelated source fact and all quality bounds; rebind before native writes.'}
    current['spatial_source_decision']=decision;current['packet']=None
    with writer(task):
        a._event(task,'retained_source_preflight_decision_required',decision);a._save(task,current)
    return {'status':'SOURCE_PREFLIGHT_REVIEW_REQUIRED','decision':decision,'native_write':False,'acceptance':False}


def guard_correction(task,state,old,new,request):
    """A preflight packet grants its diagnosed source rows, never a global edit."""
    from .common import read_json
    decision=state.get('spatial_source_decision',{})
    if decision.get('kind')!='source_preflight':return
    if (request.get('prior_observation')!=decision['prior_observation'] or
            state.get('source_feature_observation')!=decision['prior_observation']):
        raise ValueError('Source-preflight correction needs the exact retained prior observation')
    report_file=safe_path(task,decision['evidence']['path'])
    if digest(report_file)!=decision['evidence']['sha256']:
        raise ValueError('Source-preflight diagnostic changed')
    report=read_json(report_file)
    if report['observation_hash']!=identity(old) or report['source_hash']!=state['source']['sha256']:
        raise ValueError('Source-preflight diagnostic has a stale original basis')
    issues=report['issues'];unit_domains={};feature_ids={};layout_domains=set()
    for issue in issues:
        if issue.get('unit'):unit_domains.setdefault(issue['unit'],set()).add(issue.get('domain'))
        elif issue.get('feature'):feature_ids[issue['feature']]=True
        elif issue.get('domain'):layout_domains.add(issue['domain'])
    fixed={k:v for k,v in old.items() if k not in ('units','features','layout_review','observations')}
    if fixed!={k:v for k,v in new.items() if k not in ('units','features','layout_review','observations')}:
        raise ValueError('Source-preflight correction escaped the diagnosed source scope')
    corrections=request.get('corrections',{})
    changed=0
    for section in ('units','features'):
        before={row['id']:row for row in old[section]};after={row['id']:row for row in new[section]}
        if set(before)-set(after):raise ValueError('Retain every original source row during preflight correction')
        if section=='units' and set(after)!=set(before):raise ValueError('Source-preflight review cannot add unrelated units')
        for name,row in after.items():
            prior=before.get(name)
            if row==prior:continue
            if section=='units':
                domains=unit_domains.get(name,set())
                if (not domains or {k:v for k,v in row.items() if k!='appearance_review'}!=
                        {k:v for k,v in prior.items() if k!='appearance_review'}):
                    raise ValueError('Source-preflight correction escaped the diagnosed unit material domains')
                old_review=prior.get('appearance_review',{});new_review=row.get('appearance_review',{})
                if any(old_review.get(k)!=new_review.get(k) for k in set(old_review)|set(new_review) if k not in domains):
                    raise ValueError('Retain unrelated original material decisions')
            elif name not in feature_ids and not (prior is None and row.get('unit') in unit_domains):
                raise ValueError('Source-preflight correction escaped the diagnosed features')
            correction=corrections.get(section+'/'+name,{})
            if ('prior_hash' not in correction or correction['prior_hash']!=(identity(prior) if prior is not None else None) or
                    not correction.get('reason') or not correction.get('source_evidence')):
                raise ValueError('Source-preflight changed rows need exact prior hashes and located evidence')
            changed+=1
    before=old.get('layout_review',{});after=new.get('layout_review',{})
    if any(before.get(k)!=after.get(k) for k in set(before)|set(after) if k not in layout_domains):
        raise ValueError('Retain unrelated original layout decisions')
    for name in layout_domains:
        if before.get(name)==after.get(name):continue
        correction=corrections.get('layout_review/'+name,{})
        if (correction.get('prior_hash')!=identity(before.get(name)) or
                not correction.get('reason') or not correction.get('source_evidence')):
            raise ValueError('Source-preflight layout changes need exact prior hashes and located evidence')
        changed+=1
    if not changed:raise ValueError('Resolve a diagnosed source-preflight row before rebinding')
