"""Located line review and persistent doubts, reusing byte-bound crop semantics.

The program supplies identities/checklists, never a semantic PASS. A clear view
can cover several criteria. Only outstanding questions require enlarged views.
"""
import copy
import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from .common import identity, digest, read_json, write_json, safe_path
from .line_contracts import POLICY, CRITERIA, enabled, require_contract
from .line_geometry import flatten

SCHEMA='line-review-1.37.2'


def binding(state,candidate,contract):
    from .component_workflow import implementation
    spec=require_contract(state,contract)
    return {'policy':POLICY,'source':state['source']['sha256'],'pptx':candidate['pptx']['sha256'],
            'preview':candidate.get('preview',{}).get('sha256'),'render':candidate.get('render',{}).get('sha256'),
            'lines':spec['basis'],'implementation':implementation(),'backend':state['capabilities']['fingerprint']}


def _program_issues(report):
    issues={}
    for line,row in report.get('lines',{}).items():
        for criterion,check in row['checks'].items():
            if check.get('passed') is True:continue
            if criterion=='visibility' and any(row['checks'][k].get('passed') is not True for k in ('route','terminals','markers','stroke','topology')):continue
            key='program:'+line+':'+criterion
            issues[key]={'id':key,'line':line,'criterion':criterion,'origin':'program',
                'state':'OPEN','finding':'Current '+criterion+' '+('invalid measurement' if not check.get('valid') else 'constraint failure'),
                'check_hash':identity(check),'valid':check.get('valid') is True}
    return issues


def _box(points,padding,size):
    points=np.asarray(points,float);lo=np.floor(points.min(axis=0)-padding).astype(int);hi=np.ceil(points.max(axis=0)+padding).astype(int)
    x=max(0,int(lo[0]));y=max(0,int(lo[1]));r=min(size[0],int(hi[0])+1);b=min(size[1],int(hi[1])+1)
    if r<=x or b<=y:raise ValueError('LINE_REVIEW_REQUIRED: nonempty original/render scope')
    return [x,y,r-x,b-y]


def precision_request(state,candidate,report,current_width,history):
    """Finite higher-resolution render only when source precision can suffice."""
    if sum(v['pptx']==candidate['pptx']['sha256'] for v in history)>=2:return None
    refinable=[]
    def inspect(value,path):
        if isinstance(value,dict):
            if (value.get('reason')=='BOUND_REFINEMENT_REQUIRED' and value.get('valid') is False and
                    value.get('method') in ('current_marker_paint_both_directions','every_original_shaft_pixel_coverage','paired_original_render_normal_chords')):
                floor=.5 if value['method']=='paired_original_render_normal_chords' else math.sqrt(2)/2
                if value['tolerance']-value['value']>floor+1e-6:refinable.append(path)
            for key,item in value.items():
                if key not in ('prior_inconclusive','items'):inspect(item,path+'/'+key)
            # Aggregate items hold terminal markers; handle only current items.
            for i,item in enumerate(value.get('items',[])):inspect(item,path+'/items/'+str(i))
        elif isinstance(value,list):
            for i,item in enumerate(value):inspect(item,path+'/'+str(i))
    for line,row in report.get('lines',{}).items():
        from .line_verification import has_valid_failure
        if has_valid_failure(row['checks']):continue
        if any(row['checks'][key].get('passed') is not True for key in ('route','terminals','markers','stroke','topology')):continue
        inspect(row['checks']['visibility'],line+'/visibility')
    target=min(6000,max(current_width+1,current_width*2))
    if not refinable or target<=current_width:return None
    return {'operation':'refine_render','pptx':candidate['pptx']['sha256'],'preview':candidate['preview']['sha256'],
            'current_width':current_width,'target_width':target,'questions':sorted(set(refinable)),
            'limits':'Same saved PPTX/backend/source/thresholds; at most two precision refinements per native hash'}


def _crop(image,roi,size,scale):
    sx=image.width/size[0];sy=image.height/size[1];x,y,w,h=roi
    # Fixed source canvas mapping; never align each candidate to its reference.
    box=(math.floor(x*sx),math.floor(y*sy),math.ceil((x+w)*sx),math.ceil((y+h)*sy))
    crop=image.crop(box)
    return crop.resize((max(1,round(w*scale)),max(1,round(h*scale))),Image.Resampling.LANCZOS)


def current_open_issues(ledger,basis):
    """Old resolutions are evidence-bound, not perpetual semantic waivers."""
    issues={}
    for key,stored in ledger.get('line_issues',{}).items():
        issue=copy.deepcopy(stored)
        if issue['state']=='RESOLVED' and issue.get('resolved_binding')!=basis:
            issue.setdefault('prior_resolutions',[]).append({
                'binding':issue.get('resolved_binding'),'resolution':issue.get('resolution'),
                'check':issue.get('current_check')})
            issue.update(state='OPEN',reopened_binding=basis,
                reopen_reason='Prior resolution belongs to different source/native/render/implementation evidence; inspect and resolve current enlarged views')
        if issue['state']=='OPEN':issues[key]=issue
    return issues


def prepare(task,state,candidate,contract,ledger):
    if not enabled(state):return None
    from .component_workflow import _resource, _ref
    from .line_verification import evaluate
    spec=require_contract(state,contract);basis=binding(state,candidate,contract)
    open_old=current_open_issues(ledger,basis)
    directory=Path(task)/'component-workflow/line-review'/identity({'binding':basis,'open':open_old})
    manifest_file=directory/'Manifest.json'
    if manifest_file.is_file():
        value=read_json(manifest_file)
        verify_manifest(task,value,basis)
        return {'manifest':_ref(task,manifest_file),'pages':value['pages'][:4],
                'page_count':len(value['pages']),'line_count':len(spec['lines']),
                'render_refinement':value.get('render_refinement'),
                'continuation':'Read all manifest targets/pages with the managed selector. A view is evidence, not a program semantic verdict.'}
    directory.mkdir(parents=True,exist_ok=True)
    report=evaluate(task,state,candidate,contract,render=True)
    report_file=directory/'Measurements.json';write_json(report_file,report)
    issues={**open_old,**_program_issues(report)}
    targets=[];pages=[];pixel_total=0
    from .resource_facts import image_region
    with image_region(_resource(task,state['source']),[],state['source']['sha256'],mode='RGB_WHITE') as image:source=image.copy()
    with image_region(_resource(task,candidate['preview']),[],candidate['preview']['sha256'],mode='RGB_WHITE') as image:actual=image.copy()
    # Actual independently decoded owner frames expand the original view, so an
    # incorrectly routed arm cannot disappear outside a source-only crop.
    from .boundary_geometry import saved_nodes
    nodes=saved_nodes(_resource(task,candidate['pptx']),state['source_size'])
    for row in spec['lines']:
        points,_=flatten(row['source']['path']['segments'],max(1e-5,row['source']['limits']['route']/32))
        domains=[points]
        for part in row['parts']:
            entry=nodes.get(part['owner'],{});frame=entry.get('frame')
            if frame:
                x,y,w,h=frame;domains.append(np.array([[x,y],[x+w,y+h]]))
        padding=max(8,row['source']['stroke']['width'][1]+row['source']['limits']['marker'])
        roi=_box(np.vstack(domains),padding,state['source_size'])
        definitions=[('normal',roi,min(2.,1000/max(roi[2:]))) ]
        # Long/thin routes use readable critical-point views while direct pixel
        # measurements cover every intermediate segment. Short clear routes need
        # no mandatory extra enlargement or repeated prose.
        if definitions[0][2]*row['source']['stroke']['width'][0]<2:
            critical=[points[0],points[-1]]
            critical.extend(s['points'][-1] for s in row['source']['path']['segments'][:-1] if s['kind']=='line')
            seen=set()
            for p in critical:
                key=tuple(round(float(v),3) for v in p)
                if key in seen:continue
                seen.add(key);definitions.append(('critical:'+str(len(seen)),_box(np.asarray([p]),max(16,padding*2),state['source_size']),4.))
        for issue in issues.values():
            if issue['line']!=row['id']:continue
            issue_roi=issue.get('roi',roi)
            x,y,w,h=issue_roi
            if w>240 or h>240:
                # Tile the entire located doubt, including curve interiors and
                # every short arm. Endpoint-only crops cannot close a route doubt.
                for yy in range(math.floor(y),math.ceil(y+h),208):
                    for xx in range(math.floor(x),math.ceil(x+w),208):
                        region=[xx,yy,min(240,x+w-xx),min(240,y+h-yy)]
                        definitions.append(('issue:'+issue['id']+':'+str(xx)+':'+str(yy),region,4.))
            else:definitions.append(('issue:'+issue['id'],issue_roi,4.))
        views=[]
        for kind,region,scale in definitions:
            refs={};key=identity({'line':row['id'],'kind':kind,'roi':region,'scale':scale})[:20]
            crops={}
            for role,image in (('source',source),('render',actual)):
                crop=_crop(image,region,state['source_size'],scale);pixel_total+=crop.width*crop.height
                if pixel_total>200_000_000:raise ValueError('LINE_REVIEW_REQUIRED: finite crop budget reached; preserve and paginate scope')
                file=directory/(key+'-'+role+'.png');crop.save(file)
                refs[role]={**_ref(task,file),'roi':region,'scale':scale,'role':role};crops[role]=crop
            sheet=Image.new('RGB',(crops['source'].width+crops['render'].width+16,max(crops['source'].height,crops['render'].height)+24),'white')
            sheet.paste(crops['source'],(0,24));sheet.paste(crops['render'],(crops['source'].width+16,24))
            label=ImageDraw.Draw(sheet);label.text((2,3),'SOURCE',fill='black');label.text((crops['source'].width+18,3),'SAVED RENDER',fill='black')
            file=directory/(key+'-comparison.png');sheet.save(file)
            view={'kind':kind,'evidence':refs,'comparison':_ref(task,file)};views.append(view)
            pages.append({'line':row['id'],'kind':kind,**_ref(task,file)})
        targets.append({'line':row['id'],'criteria':list(CRITERIA),'owners':[p['owner'] for p in row['parts']],
                        'views':views,'required_views':[v['kind'] for v in views]})
    source.close();actual.close()
    value={'schema':SCHEMA,'binding':basis,'targets':targets,'pages':pages,
           'measurements':_ref(task,report_file),'issues':list(issues.values()),
           'limits':'Programs bind identity, coverage and metrics. Semantic observations remain current host/human judgments.'}
    value['render_refinement']=precision_request(state,candidate,report,actual.width,ledger.get('line_render_refinements',[]))
    value['manifest_hash']=identity(value);write_json(manifest_file,value)
    return {'manifest':_ref(task,manifest_file),'pages':pages[:4],'page_count':len(pages),
            'line_count':len(spec['lines']),'render_refinement':value['render_refinement'],
            'continuation':'Read every manifest target/page; use shared crops for several criteria and enlarge all open doubts. When render_refinement is present, submit operation:refine_render with this manifest ref before another judgment.'}


def retain_prepared_issues(task,prepared,ledger):
    """Persist program doubts when issued, before a later render can replace them."""
    from .component_workflow import _resource
    manifest=read_json(_resource(task,prepared['manifest']))
    current=ledger.setdefault('line_issues',{});changed=False
    for issue in manifest['issues']:
        if issue.get('state')=='OPEN' and current.get(issue['id'])!=issue:
            current[issue['id']]=copy.deepcopy(issue);changed=True
    return changed


def request_precision(task,request):
    from . import agent_runtime as a,component_workflow as c
    from .line_verification import evaluate
    task,state=a._state(task);contract,ledger=c._load(task,state);candidate=c._candidate(state)
    if not enabled(state):raise ValueError('Current line evidence policy required')
    manifest=read_json(c._resource(task,request['manifest']));verify_manifest(task,manifest,binding(state,candidate,contract))
    report=evaluate(task,state,candidate,contract,render=True)
    with Image.open(c._resource(task,candidate['preview'])) as image:width=image.width
    action=precision_request(state,candidate,report,width,ledger.get('line_render_refinements',[]))
    if not action:raise ValueError('MEASUREMENT_DECISION_REQUIRED: no remaining justified render precision refinement')
    ledger.setdefault('line_issues',{}).update(_program_issues(report))
    ledger.setdefault('line_render_refinements',[]).append({**action,'manifest':request['manifest'],
        'retained_preview':candidate['preview'],'retained_render':candidate['render']})
    current=copy.deepcopy(candidate)
    for key in ('preview','render','render_environment'):current.pop(key,None)
    current['render_request_width']=action['target_width']
    ledger.update(final_visual=None,final_dirty=True,final_result=None)
    state.update(active_candidate=current,packet=None,stage='host_render')
    state.pop('acceptance',None)
    from .common import writer
    with writer(task):c._save_ledger(task,state,ledger,'line_render_precision_requested',action)
    return {'status':'ACTUAL_RENDER_PRECISION_REQUIRED','render_width':action['target_width'],
        'pptx_unchanged':True,'source_and_thresholds_unchanged':True,'acceptance':False}


def verify_manifest(task,manifest,current):
    if (manifest.get('schema')!=SCHEMA or manifest.get('manifest_hash')!=identity({k:v for k,v in manifest.items() if k!='manifest_hash'}) or
            manifest.get('binding')!=current):
        raise ValueError('LINE_REVIEW_REQUIRED: stale or changed manifest')
    for target in manifest['targets']:
        for view in target['views']:
            for ref in [*view['evidence'].values(),view['comparison']]:
                if digest(safe_path(task,ref['path']))!=ref['sha256']:raise ValueError('LINE_REVIEW_REQUIRED: crop bytes changed')
    ref=manifest['measurements']
    if digest(safe_path(task,ref['path']))!=ref['sha256']:raise ValueError('LINE_REVIEW_REQUIRED: measurement artifact changed')


def validate(task,state,candidate,contract,ledger,evidence,*,report=None):
    if not enabled(state):return {'passed':True,'applicable':False,'legacy_policy_retained':True}
    spec=require_contract(state,contract)
    if not spec['lines']:
        retained=copy.deepcopy(ledger.get('line_issues',{}));retained.update(current_open_issues(ledger,binding(state,candidate,contract)))
        return {'passed':not any(v['state']=='OPEN' for v in retained.values()),'applicable':False,'issues':retained,
                'scope':'no source/native line obligations; independent final census is still required'}
    review=evidence.get('line_review',{})
    ref=review.get('manifest')
    if not isinstance(ref,dict):return {'passed':False,'reason':'LINE_REVIEW_REQUIRED','issues':copy.deepcopy(ledger.get('line_issues',{}))}
    from .component_workflow import _resource
    manifest=read_json(_resource(task,ref));verify_manifest(task,manifest,binding(state,candidate,contract))
    targets={t['line']:t for t in manifest['targets']}
    expected={r['id'] for r in spec['lines']}
    if set(targets)!=expected or len(targets)!=len(manifest['targets']) or any(t['criteria']!=list(CRITERIA) for t in targets.values()):
        raise ValueError('LINE_REVIEW_REQUIRED: compiled target/criterion set cannot shrink')
    records=review.get('lines',[]);by_id={r.get('line'):r for r in records}
    if len(by_id)!=len(records) or set(by_id)!=expected:
        raise ValueError('LINE_REVIEW_REQUIRED: every current source line needs exactly one record')
    current_report=report or read_json(_resource(task,manifest['measurements']))
    if current_report.get('basis')!=spec['basis'] or current_report.get('pptx_hash')!=candidate['pptx']['sha256']:
        raise ValueError('LINE_REVIEW_REQUIRED: current line measurement basis')
    issues=copy.deepcopy(ledger.get('line_issues',{}));issues.update(current_open_issues(ledger,manifest['binding']))
    issues.update(_program_issues(current_report));failed=[]
    for line,target in targets.items():
        record=by_id[line];criteria=record.get('criteria',{})
        if set(criteria)!=set(CRITERIA):raise ValueError('LINE_REVIEW_REQUIRED: exact criterion coverage')
        refs=record.get('evidence_refs',[])
        allowed=[r for v in target['views'] for r in v['evidence'].values()]
        if any(ref not in allowed for ref in refs):raise ValueError('LINE_REVIEW_REQUIRED: exact target crop reference')
        # Shared references cover several predicates; every required normal,
        # critical or doubt view still needs both original and actual pixels.
        for view in target['views']:
            if any(view['evidence'][role] not in refs for role in ('source','render')):
                raise ValueError('LINE_REVIEW_REQUIRED: all planned original/render views must be accounted for')
        for criterion,value in criteria.items():
            if value not in ('PASS','FAIL','UNRESOLVED'):raise ValueError('LINE_REVIEW_REQUIRED: explicit per-criterion judgment')
            if value!='PASS':failed.append([line,criterion])
    for issue in review.get('issues',[]):
        if (issue.get('line') not in expected or issue.get('criterion') not in CRITERIA or
                not issue.get('id') or not issue.get('finding') or len(issue.get('roi',[]))!=4):
            raise ValueError('LINE_REVIEW_REQUIRED: stable located doubt')
        if by_id[issue['line']]['criteria'][issue['criterion']]=='PASS':
            raise ValueError('LINE_REVIEW_REQUIRED: PASS contradicts a located open doubt')
        key='visual:'+issue['id'];old=issues.get(key)
        if old and any(old.get(k)!=issue.get(k) for k in ('line','criterion','finding','roi')):
            raise ValueError('LINE_REVIEW_REQUIRED: a retained doubt cannot change identity')
        issues[key]={**copy.deepcopy(issue),'id':key,'origin':'visual','state':'OPEN','reported_binding':manifest['binding']}
    located={(v['line'],v['criterion']) for v in issues.values() if v['state']=='OPEN'}
    for line,criterion in failed:
        if (line,criterion) in located:continue
        key='visual:review:'+line+':'+criterion
        original=next(row for row in spec['lines'] if row['id']==line)
        issues[key]={'id':key,'line':line,'criterion':criterion,'origin':'visual','state':'OPEN',
            'finding':'Observer reported '+by_id[line]['criteria'][criterion]+'; an explicit current resolution is required',
            'roi':original['roi'],'reported_binding':manifest['binding']}
    resolutions=review.get('resolutions',[])
    if len({r.get('issue') for r in resolutions})!=len(resolutions):raise ValueError('LINE_REVIEW_REQUIRED: duplicate resolution')
    for resolution in resolutions:
        issue=issues.get(resolution.get('issue'))
        replay=issue is not None and issue['state']=='RESOLVED' and issue.get('resolution')==resolution and issue.get('resolved_binding')==manifest['binding']
        if issue is None or issue['state']!='OPEN' and not replay or resolution.get('kind') not in ('repair','measurement','false_positive','source_decision') or not resolution.get('observations'):
            raise ValueError('LINE_REVIEW_REQUIRED: current explicit doubt resolution')
        line=issue['line'];criterion=issue['criterion'];target=targets[line]
        deep=[v for v in target['views'] if v['kind'].startswith('issue:'+issue['id'])]
        if not deep:raise ValueError('SUSPICION_UNRESOLVED: prepare and inspect the located enlarged evidence')
        resolution_refs=resolution.get('evidence_refs',[])
        if any(v['evidence'][role] not in resolution_refs for v in deep for role in ('source','render')):
            raise ValueError('SUSPICION_UNRESOLVED: resolution needs every corresponding enlarged original/render crop')
        if any(r not in [ref for v in deep for ref in v['evidence'].values()] for r in resolution_refs):
            raise ValueError('SUSPICION_UNRESOLVED: unrelated resolution evidence')
        check=current_report['lines'][line]['checks'][criterion]
        if check.get('passed') is not True or check.get('valid') is not True or by_id[line]['criteria'][criterion]!='PASS':
            raise ValueError('SUSPICION_UNRESOLVED: visual text cannot waive current program failure/invalidity')
        issue.update(state='RESOLVED',resolution=copy.deepcopy(resolution),resolved_binding=manifest['binding'],current_check=identity(check))
    # A current failure always reopens its program issue; a subsequent PASS only
    # closes it with an explicit enlarged, current, same-question resolution.
    open_ids=sorted(k for k,v in issues.items() if v['state']=='OPEN')
    return {'passed':not failed and not open_ids and current_report.get('passed') is True,
            'visual_failure':any(value=='FAIL' for record in records for value in record['criteria'].values()),
            'failed_visual':failed,'open_issues':open_ids,'issues':issues,'manifest':ref,
            'program_failure':any(__import__(__package__+'.line_verification',fromlist=['has_valid_failure']).has_valid_failure(check)
                for row in current_report['lines'].values() for check in row['checks'].values()),
            'measurement':manifest['measurements'],'scope':'located observer judgments plus non-waivable current program checks'}
