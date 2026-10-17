"""Cheap finite native geometry trials, followed by one saved-native commit.

The trial renderer is an explicit surrogate. Only an actual saved PPT preview
can qualify a fitted part. Existing specialist source fitters remain available
for models outside the declared primitive/path adapter.
"""
import copy
import math
import numpy as np
from PIL import Image,ImageDraw
from .common import read_json,write_json,identity,writer
from .component_solver import bounded_search
from .component_metrics import arrays,window


def operator_key(row):
    return row['route']+':'+identity({'metrics':row.get('metrics'),
        'adapter':row.get('fit',{}).get('adapter'),'parameters':sorted(row.get('parameters',{}))})[:16]


def apply(scene,row,values,contract=None):
    from .spatial_fit import is_spatial, apply as apply_spatial
    if is_spatial(row):return apply_spatial(scene,row,values,contract)
    result=copy.deepcopy(scene);nodes={n['id']:n for n in result['objects']};allowed={}
    bindings=row['fit'].get('bindings',{})
    if set(bindings)!=set(row.get('parameters',{})):
        raise ValueError('Every parameter requires one explicit native field binding')
    for name,binding in bindings.items():
        if binding['owner'] not in row['owners']: raise ValueError('Fit escaped component ownership')
        path=binding['field'];node=nodes[binding['owner']]
        if not isinstance(path,list) or not path or path[0] not in ('bbox','content','style'):
            raise ValueError('Use a literal native field path; no executable callbacks')
        pointer=node
        for part in path[:-1]:pointer=pointer[part]
        parameter=row['parameters'][name]
        if parameter['state']=='fixed' and pointer[path[-1]]!=values[name]:
            raise ValueError('Fixed native field differs from the original contract')
        if parameter['state']=='fixed': continue
        pointer[path[-1]]=values[name]
        if path[0]=='bbox':field=['bbox.left','bbox.top','bbox.width','bbox.height'][path[1]]
        elif path[0]=='content':field='geometry'
        elif path in (['style','line_width'],['style','rotation']):field='style.'+path[1]
        else:raise ValueError('Only source-bound uncertain geometric parameters are searchable')
        allowed.setdefault(binding['owner'],set()).add(field)
    return result,{key:sorted(fields) for key,fields in allowed.items()}


def _curve(points):
    points=np.asarray(points,float);degree=len(points)-1
    if degree not in (1,2,3):raise ValueError('Observed line/quadratic/cubic model required')
    t=np.linspace(0,1,129)
    return sum(math.comb(degree,i)*(1-t)[:,None]**(degree-i)*t[:,None]**i*point for i,point in enumerate(points)).tolist()


def preview(scene,row,scale=4):
    """Native normalized contours, centered strokes, fixed original coordinates."""
    x,y,w,h=row['roi'];background=row['fit'].get('background','FFFFFF')
    image=Image.new('RGB',(math.ceil(w*scale),math.ceil(h*scale)),'#'+background.lstrip('#'))
    draw=ImageDraw.Draw(image);nodes={n['id']:n for n in scene['objects']}
    px_per_pt=scene['canvas']['width']/(scene['canvas']['target_width_inches']*72)
    def point(p):return ((p[0]-x)*scale,(p[1]-y)*scale)
    def color(value):return None if value in (None,'none') else '#'+value.lstrip('#')
    for owner in sorted(row['owners'],key=lambda n:scene['objects'].index(nodes[n])):
        node=nodes[owner];kind=node['render_type'];bx,by,bw,bh=node['bbox'];style=node.get('style',{});content=node.get('content',{})
        if style.get('rotation',0) or style.get('gradient') or content.get('native_snapshot'):
            raise ValueError('Use the established native/source specialist for rotated, material or imported geometry')
        fill=color(style.get('fill'));stroke=color(style.get('stroke'));width=style.get('line_width',1)*px_per_pt
        pen=max(1,round(width*scale)) if stroke else 0
        contours=[]
        if kind=='shape':
            preset=content.get('preset','rect');box=[*point((bx,by)),*point((bx+bw,by+bh))]
            # Draw fill at the mathematical boundary, then a centered outline.
            if preset in ('ellipse','rect'):
                method=draw.ellipse if preset=='ellipse' else draw.rectangle
                if fill:method(box,fill=fill)
                if stroke:
                    expanded=[box[0]-pen/2,box[1]-pen/2,box[2]+pen/2,box[3]+pen/2]
                    method(expanded,outline=stroke,width=pen)
                continue
            if preset=='triangle':contours=[{'points':[[.5,0],[1,1],[0,1]],'closed':True}]
            elif preset=='diamond':contours=[{'points':[[.5,0],[1,.5],[.5,1],[0,.5]],'closed':True}]
            else:raise ValueError('No calibrated cheap adapter for preset '+preset)
        elif kind=='bezier':contours=[{'points':_curve(content['points']),'closed':False}]
        elif kind=='path':
            contours=content.get('contours',[])
            if not contours:raise ValueError('Inline source-bound native contours required by cheap adapter')
        else:raise ValueError('Use an existing typed constructor for '+kind)
        for contour in contours:
            points=contour.get('points')
            if points is None:
                points=[];last=None
                for command in contour.get('commands',[]):
                    op=command.get('op');p=command.get('points',[])
                    if op in ('move','moveTo'):last=p[0];points.append(last)
                    elif op in ('line','lnTo'):points.extend(p);last=p[-1]
                    elif op in ('cubic','cubicBezTo','quad','quadBezTo') and last is not None:
                        points.extend(_curve([last]+p)[1:]);last=p[-1]
                    elif op in ('close','closePath'):pass
                    else:raise ValueError('Unsupported source path command '+str(op))
            pixels=[point((bx+p[0]*bw,by+p[1]*bh)) for p in points]
            if contour.get('closed') and fill:draw.polygon(pixels,fill=fill)
            if stroke:draw.line(pixels+[pixels[0]] if contour.get('closed') else pixels,fill=stroke,width=pen,joint='curve')
    return np.asarray(image.resize((math.ceil(w),math.ceil(h)),Image.Resampling.LANCZOS),float)/255


def recover(task,request):
    from .component_transactions import recover as resume
    return resume(task,request)


def fit(task,request):
    from . import agent_runtime as a,component_workflow as c
    from .appearance_metrics import canvas
    task,state=a._state(task);contract,ledger=c._load(task,state);candidate=c._candidate(state)
    if not contract or not candidate:raise ValueError('Current source contract/candidate required')
    c.refresh(task,state,contract,ledger,candidate)
    if ledger.get('pending_transaction'):return {'status':'RECOVERY_REQUIRED','transaction':ledger['pending_transaction']}
    row=c.component_row(task,state,contract,request['component']);record=ledger['components'][row['id']]
    if row['route']!='local_fit' or record['status']=='QUALIFIED':raise ValueError('Fit only a pending tunable local part')
    if state.get('spatial_source_decision') or ledger.get('pending_decision') or ledger.get('structural_grant'):
        raise ValueError('Resolve the current source/measurement decision before numerical fitting')
    from .spatial_repair import guard_fields
    from .spatial_fit import is_spatial, writes as spatial_writes
    guard_fields(contract,ledger,spatial_writes(row) if is_spatial(row) else
        [v for name,v in row.get('fit',{}).get('bindings',{}).items() if row['parameters'][name]['state']=='tunable'])
    if request.get('pptx_hash')!=candidate['pptx']['sha256'] or request.get('source_hash')!=state['source']['sha256']:
        raise ValueError('Fit request must bind the actual source/current candidate')
    if record['status']=='ACTUAL_NATIVE_CONFIRMATION_REQUIRED' and candidate['pptx']['sha256']!=record.get('numeric_baseline_hash'):
        return {'status':'ACTUAL_NATIVE_CONFIRMATION_REQUIRED','report':record.get('last_fit'),
                'evaluations':0,'whole_audit_executed':False,'next':'Evaluate the actual saved candidate before another fit'}
    spatial_adapter = row.get('fit',{}).get('adapter')=='spatial_parameters'
    if row.get('fit',{}).get('adapter') not in ('native_geometry','spatial_parameters'):
        return {'status':'MODEL_OR_SOURCE_DECISION_REQUIRED','component':row['id'],'reason':'Use an existing original-only typed fitter or bind a supported geometric adapter'}
    mask=None;original=None
    if not spatial_adapter:
        source=canvas(str(c._resource(task,state['source'])),state['source']['sha256'],tuple(state['source_size']))
        x,y,r,b=window(row['roi'],state['source_size']);original=source[y:b,x:r]
        if [x,y,r-x,b-y]!=row['roi']:raise ValueError('Cheap trial ROI must use original integer sample coordinates')
        if row.get('support_mask'):mask=np.asarray(Image.open(c._resource(task,row['support_mask'])).convert('L'))>0
    scene=read_json(c._resource(task,candidate['scene']));settings=copy.deepcopy(contract['policy']['parameter_search'])
    settings['parameter_metric_map']=row.get('parameter_metric_map',{})
    _,signatures=c._signatures(task,state,candidate)
    measurement_signature=c._measurement_signature(row,signatures,contract)
    basis_key=basis(row,contract['policy'],state,measurement_signature)
    from . import problem_control as pc
    failed=pc.strategy(task,state,row,basis_key)
    if failed and failed.get('status')!='TARGETS_MET':return dict(failed,duplicate_action_avoided=True,evaluations=0)
    if record['status']=='NUMERIC_READY' and request.get('commit',True):
        from .component_batch import commit
        return commit(task,{**request,'components':[row['id']]})
    if record.get('last_fit'):
        previous=read_json(c._resource(task,record['last_fit']))
        if previous.get('fit_basis')==basis_key and previous.get('status')!='TARGETS_MET':
            return {'status':previous['status'],'report':record['last_fit'],'evaluations':0,
                    'duplicate_action_avoided':True,'whole_audit_executed':False,
                    'next':'Revise the located source/model/measurement decision; identical search is already exhausted'}
        confirmed=record.get('numeric_saved_result') or {}
        same_context=previous.get('fit_basis')==basis_key
        if (not same_context and confirmed.get('fit')==record['last_fit'] and confirmed.get('candidate')):
            _,saved_signatures=c._signatures(task,state,confirmed['candidate'])
            same_context=c._measurement_signature(row,saved_signatures,contract)==measurement_signature
        if (same_context and previous.get('contract')==state['component_workflow']['contract']
                and previous.get('status')=='TARGETS_MET'):
            predicted,_=apply(scene,row,previous['parameters'],contract)
            selected={n['id']:n for n in scene['objects']};fitted={n['id']:n for n in predicted['objects']}
            same=all(selected[name]==fitted[name] for name in row['owners'])
            if same and record['status'] in ('LOCAL_TARGETS_UNMET','SPATIAL_RELATIONS_UNMET'):
                record['status']='MODEL_OR_SOURCE_DECISION_REQUIRED'
                with writer(task):c._save_ledger(task,state,ledger,'surrogate_discrepancy',{'component':row['id'],'report':record['last_fit']})
                return {'status':record['status'],'evaluations':0,'report':record['last_fit'],'whole_audit_executed':False,
                        'reason':'The actual saved candidate failed a target that its cheap model predicted passing; diagnose the model instead of repeating identical parameters'}
    # A new initial value, bound, metric threshold or code revision is not a fresh budget.
    budget_key=identity({'component':row['id'],'source_region':row['source_region_key'],
                         'model':row.get('model'),'adapter':row['fit'].get('adapter'),
                         'bindings':row['fit'].get('bindings')})
    budget_file=task/'component-workflow'/('Search-budget-'+budget_key+'.json')
    budget=read_json(budget_file) if budget_file.exists() else {'id':budget_key,'evaluations':0,'rounds':0,'searches':{}}
    from . import problem_control as pc
    shared_remaining=pc.remaining(task,state,row,'evaluations')
    maximum=min(settings['max_evaluations'],budget['evaluations']+shared_remaining);round_limit=settings['max_rounds']
    if not budget_file.exists():write_json(budget_file,budget)
    checkpoint_file=task/'component-workflow'/('Search-state-'+basis_key+'.json')
    prior=read_json(checkpoint_file) if checkpoint_file.exists() else {}
    recovered=[r for r in prior.get('history',[]) if r.get('valid') and r.get('hard_pass') and r.get('passed')]
    exhausted=budget['evaluations']>=maximum or budget['rounds']>=round_limit
    if exhausted and not recovered:
        record['status']='SEARCH_BOUND_REACHED'
        with writer(task):c._save_ledger(task,state,ledger,'persistent_budget_exhausted',{'component':row['id']})
        return {'status':'SEARCH_BOUND_REACHED','component':row['id'],'whole_audit_executed':False}
    settings['resume_history']=prior.get('history',[])
    settings['resume_rounds']=prior.get('rounds',0)
    settings['resume_search_state']=prior.get('search_state',{})
    settings['max_evaluations']=min(4096,maximum-budget['evaluations']+len(settings['resume_history']))
    settings['max_rounds']=min(256,round_limit-budget['rounds']+settings['resume_rounds'])
    counted_rounds=prior.get('rounds',0)
    def checkpoint(history,rounds,search_state=None):
        nonlocal counted_rounds
        budget['rounds']+=max(0,rounds-counted_rounds);counted_rounds=rounds
        budget['searches'][basis_key]={'evaluations':len(history),'rounds':rounds}
        write_json(budget_file,budget)
        write_json(checkpoint_file,{'basis':basis_key,'history':history,'rounds':rounds,'search_state':search_state or {}})
    def measure(values):
        # Reserve before calculation: crashes and invalid trials consume the finite budget.
        if budget['evaluations']>=maximum:raise ValueError('Persistent measurement budget exhausted')
        pc.reserve(task,state,row,'evaluations')
        budget['evaluations']+=1;write_json(budget_file,budget)
        try:
            constructed,_=apply(scene,row,values,contract)
        except (ValueError, KeyError, IndexError, TypeError, np.linalg.LinAlgError) as error:
            return {'hard_checks':{'valid_spatial_geometry':False},'metrics':{},'reason':str(error)}
        if spatial_adapter:
            from .spatial_fit import measured
            return measured(task,state,candidate,contract,row,constructed)
        actual=preview(constructed,row)
        metrics,_=arrays(original,actual,mask)
        from .component_metric_adapters import geometric
        metrics.update(geometric(actual,row,mask,original))
        hard={'part_count':len(constructed['objects'])==len(scene['objects']),
              'positive_extents':all(min(n['bbox'][2:])>0 for n in constructed['objects'] if n['id'] in row['owners'])}
        return {'hard_checks':hard,'metrics':metrics}
    try:
        if recovered:
            best=min(recovered,key=lambda v:tuple(v['merit']))
            result={'status':'TARGETS_MET','parameters':best['parameters'],'best':best,'initial':prior['history'][0],
                    'history':prior['history'],'evaluations':len(prior['history']),'rounds':prior.get('rounds',0),'recovered_checkpoint':True}
        else:result=bounded_search(row['parameters'],row['metrics'],measure,settings,checkpoint=checkpoint)
    except ValueError as error:
        result={'status':'MODEL_OR_SOURCE_DECISION_REQUIRED','reason':str(error),'evaluations':0,'history':[],'parameters':{k:v['value'] for k,v in row['parameters'].items()}}
    result.update(component=row['id'],source_hash=state['source']['sha256'],baseline_hash=candidate['pptx']['sha256'],
                  fit_basis=basis_key,contract=state['component_workflow']['contract'],
                  measurement_scope='cheap declared geometry surrogate; actual saved-native check remains required',acceptance=False)
    file=task/'component-workflow'/('Fit-'+identity(result)+'.json');write_json(file,result)
    pc.strategy(task,state,row,basis_key,{'status':result['status'],'report':c._ref(task,file),'best_retained':True})
    task,state=a._state(task);contract,ledger=c._load(task,state);record=ledger['components'][row['id']]
    record['last_fit']=c._ref(task,file);record['status']=result['status'] if result['status']!='TARGETS_MET' else 'NUMERIC_READY'
    record['numeric_baseline_hash']=candidate['pptx']['sha256']
    record['numeric_input_signature']=measurement_signature
    record.setdefault('search_budgets',{})[budget_key]={'id':budget_key,'mutable_path':budget_file.relative_to(task).as_posix()}
    initial,best=result.get('initial',{}),result.get('best',{})
    if initial.get('valid') and best.get('valid') and initial.get('hard_pass') and best.get('hard_pass'):
        record['observed_signature']=c._component_signature(row,signatures,contract=contract)
        record['observed_measurement_signature']=measurement_signature
        record['immediate_probe']={'signature':measurement_signature,
            'fit_basis':basis_key,'context':basis_key,'violation_reduction':max(initial['violations'])-max(best['violations']),
            'source_region':row['source_region_key'],'scope':'current finite numeric probe; not cost/effect telemetry'}
    if result['status']=='TARGETS_MET' and request.get('commit',True):
        with writer(task):c._save_ledger(task,state,ledger,'fit_numeric_ready',{'component':row['id'],'report':c._ref(task,file)})
        from .component_batch import commit
        return commit(task,{'components':[row['id']],'source_hash':state['source']['sha256'],
                            'pptx_hash':candidate['pptx']['sha256']})
    with writer(task):c._save_ledger(task,state,ledger,'fit_completed',{'report':c._ref(task,file),'status':record['status']})
    return {'status':record['status'],'report':c._ref(task,file),'evaluations':result['evaluations'],'whole_audit_executed':False}


def basis(row,policy,state,measurement_signature):
    from .component_dependencies import consumer
    return identity({'source_region':row.get('source_region_key'),'model':row.get('model'),
        'parameters':row.get('parameters'),'metrics':row.get('metrics'),'bindings':row.get('fit'),
        'implementation':consumer(row,policy,state),'measurement_signature':measurement_signature})
