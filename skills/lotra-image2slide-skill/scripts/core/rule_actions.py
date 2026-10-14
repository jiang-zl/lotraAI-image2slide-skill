"""Execute all actionable frozen rule findings on a complete working artifact.

This extends the same loop: save -> actual render -> full checks -> located
issues. It may retain working progress; it cannot award final acceptance.
"""
import copy, shutil, time
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
from .common import digest,identity,read_json,write_json,writer
from .mathml import NS
from . import agent_runtime as a,frame_plan as fp,semantic_composition as sc,execution_contract as ec


def cumulative_grants(state,baseline,grants):
    """Keep the entire unadopted repair chain visible to later shared gates.

    The native writers still receive only this step's finite permissions.
    Prior permissions are carried solely for cumulative observation/adoption.
    """
    pending=state.get('rule_pending_built')
    prior=baseline.get('reason',{}).get('kind')=='program_all_applicable_rule_repair'
    if pending and not prior:
        raise ValueError('Pending rule work cannot be detached from its saved parent')
    total=copy.deepcopy(baseline.get('allowed',{})) if pending and prior else {}
    for name,fields in grants.items():
        total[name]=sorted(set(total.get(name,[]))|set(fields))
    return total


def rule_source(target,source_basis):
    context=source_basis.get('rules',{}).get(target)
    if not source_basis.get('source_hash') or not context:
        raise ValueError('Each deterministic branch needs its own frozen original rule, not a whole-plan hash')
    row=context['contract']
    if context['kind']=='interface':
        # Unrelated frames, other interfaces, file names, free prose and a new
        # contract ID do not change this measurement/cause/operator branch.
        from .source_spacing import binding
        value={**binding(row),'relationship':row['relationship'],'limits':copy.deepcopy(row['limits'])}
    elif context['kind']=='frame':
        if not (target==row['id'] or target.startswith(row['id']+'.')):
            raise ValueError('Locate the actual frozen frame for this finding')
        excluded={'id','evidence','reason','description','threshold_basis','source_view','user_intent','note'}
        def geometric(value):
            if isinstance(value,dict):
                return {k:geometric(v) for k,v in value.items() if k not in excluded and not (k=='path' and 'sha256' in value)}
            if isinstance(value,list):return [geometric(v) for v in value]
            return value
        value=geometric(row)
        # Distinct member findings share one frame but remain independently
        # budgeted. A renamed source contract alone cannot refresh that target.
        value['member']=target.removeprefix(row['id'])
    else:raise ValueError('Use the actually frozen frame/interface rule')
    def numeric(value):
        if isinstance(value,dict):return {k:numeric(v) for k,v in value.items()}
        if isinstance(value,list):return [numeric(v) for v in value]
        if type(value) in (int,float):
            number=float(value)
            if not __import__('math').isfinite(number):raise ValueError('Finite frozen rule coordinates required')
            return 0. if number==0 else number
        return value
    return {'source_hash':source_basis['source_hash'],'kind':context['kind'],'measurement':numeric(value)}


def authorize_rules(state,targets,source_basis,grants):
    """Use the existing finite strategy budget for deterministic rules too."""
    from .repair_strategy import authorize
    ledger=state.setdefault('program_rule_issues',{})
    branches={}
    for target in sorted(set(targets)):
        relevant=rule_source(target,source_basis)
        key='program-rule-'+identity(relevant)[:20]
        if key in branches:
            branches[key]['targets'].append(target);continue
        issue=ledger.setdefault(key,{'id':key,'owner':target,
            'property':'rule:'+target,'attempt_count':0,'strategies':{}})
        # A different file, agent wording or freshly assigned revision cannot
        # reset failures. Only changed frozen source/rule evidence can do so.
        issue['property']='rule:'+identity(relevant)
        branch=authorize(state,issue,{'stage':'instance_geometry'},grants)
        issue['attempt_count']+=1;branches[key]={'branch':branch,'targets':[target]}
    return branches


def reflect_rules(state,candidate,current_items):
    """Record actual rule gains once, separately from semantic acceptance."""
    from .repair_strategy import record
    attempt=next((r for r in state.get('rule_attempts',[])
        if r.get('candidate',{}).get('sha256')==candidate['pptx']['sha256']),None)
    if not attempt or not attempt.get('branches') or attempt.get('reflection'):return
    after={r['id']:r for r in current_items};outcomes=[]
    for key,binding in attempt['branches'].items():
        issue=state['program_rule_issues'][key]
        branch=binding if isinstance(binding,str) else binding['branch']
        targets=[issue['owner']] if isinstance(binding,str) else binding['targets']
        measured=[after.get(target) for target in targets]
        gain=all(r and r.get('passed') for r in measured)
        record(state,issue,{'reason':{'strategy_branch':branch}},gain=gain)
        outcomes.append({'rule':targets[0],'rules':targets,'gain':gain,'actual':measured,
            'status':'ACTUAL_RULE_MET' if gain else 'INEFFECTIVE_RULE_BRANCH'})
    attempt['reflection']={'candidate':candidate['pptx']['sha256'],'outcomes':outcomes,
        'semantic_acceptance':False}
    attempt['status']='ACTUAL_RULE_PROGRESS_QUALITY_PENDING' if any(r['gain'] for r in outcomes) else 'INEFFECTIVE_ACTUAL_RULE_ATTEMPT'


def _translate(pptx,output,size,proposals):
    from .boundary_geometry import saved_nodes
    from .frame_actions import _position
    nodes=saved_nodes(pptx,size);before={n:E.tostring(e['node'],method='c14n',exclusive=True) for n,e in nodes.items()}
    moved={};changes=[]
    for proposal in proposals:
        dx,dy=proposal['translation_source_px']
        for name in proposal['objects']:
            if name in moved:raise ValueError('Conflicting interface proposals need one joint source plan')
            moved[name]=(dx,dy);entry=nodes[name];x,y,w,h=entry['frame']
            _position(entry,[x+dx,y+dy,w,h])
            changes.append({'object':name,'fields':['bbox.left','bbox.top'],'translation_source_px':[dx,dy]})
    unauthorized=[]
    for name,entry in nodes.items():
        node=copy.deepcopy(entry['node']);old=E.fromstring(before[name])
        if name in moved:
            for item in (node,old):
                off=item.find('p:spPr/a:xfrm/a:off',NS)
                off.attrib.pop('x',None);off.attrib.pop('y',None)
        elif entry['tag']=='grpSp':
            for item in (node,old):
                for child in list(item):
                    if E.QName(child).localname in ('sp','grpSp','pic','cxnSp','graphicFrame'):item.remove(child)
        if E.tostring(node,method='c14n',exclusive=True)!=E.tostring(old,method='c14n',exclusive=True):unauthorized.append(name)
    if unauthorized:raise ValueError('Unpermitted native interface change: '+repr(unauthorized))
    root=next(iter(nodes.values()))['node'].getroottree().getroot()
    with ZipFile(pptx) as z,output.open('xb') as stream,ZipFile(stream,'w',ZIP_DEFLATED,compresslevel=9) as out:
        for info in z.infolist():
            data=E.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True) if info.filename=='ppt/slides/slide1.xml' else z.read(info.filename)
            out.writestr(info,data,compress_type=ZIP_DEFLATED,compresslevel=9)
    return {'changes':changes,'non_target_native_changes':unauthorized,'pptx_sha256':digest(output)}


def execute(task,request=None):
    task,state=a._state(task);request=request or {}
    baseline=state.get('active_candidate') or state.get('selected')
    if not baseline or not baseline.get('preview'):raise ValueError('An actually rendered complete native working baseline is required')
    if request.get('expected_baseline_sha256')!=baseline['pptx']['sha256']:raise ValueError('Stale rule-action baseline')
    inv,scene,_=ec.inventory(task,state,baseline)
    if set(inv['native_names'])!={o['id'] for o in scene['objects']}:raise ValueError('Reconcile the complete actual native Scene before rule actions')
    plan=fp.validate(fp.load(task,state['frame_plan']),task,state,scene)
    checked=fp.check(plan,task,ec.resource(task,baseline['pptx']),state['source_size'])
    failed=[i for i in checked['items'] if not i['passed'] or
            request.get('operation')=='normalize_all_frames' and i.get('object') and '.palette.' not in i['id']]
    grants={};debt=[]
    for item in failed:
        frame=next(f for f in plan['frames'] if item['id']==f['id'] or item['id'].startswith(f['id']+'.'))
        if frame['kind']=='container':
            name=item.get('child') or item.get('object')
            if name is None:
                name=next((m['object'] for m in frame['members'] if item['id']==frame['id']+'.'+m['object']),None)
            member=next((m for m in frame['members'] if m['object']==name),{})
            if member.get('operation')=='clip_fill':grants[name]=['geometry']
            else:debt.append(item)
        elif item.get('object'):
            name=item['object'];grants[name]=['bbox.left','bbox.top','bbox.width','bbox.height']
            member=next((m for m in frame.get('members',[]) if m['object']==name),frame if frame.get('object')==name else {})
            if member.get('content_window'):grants[name].append('media')
        else:debt.append(item)
    proposals=[]
    from .interface_actions import propose
    actual=sc.report(task,state,baseline)
    bad={i['id'] for i in actual['items'] if not i['passed'] and i['kind']=='interface'}
    for row in sc.contracts(task,state):
        if row['id'] not in bad:continue
        proposal=propose(task,state,baseline,row)
        if proposal['status']=='PROPOSED_REQUIRES_ACTUAL_SAVE_RENDER':proposals.append(proposal)
        else:debt.append(proposal)
    for proposal in proposals:
        for name in proposal['objects']:
            if name in grants:raise ValueError('Frame and interface compete for the same source part; return to source planning')
            grants[name]=['bbox.left','bbox.top']
    objects={o['id']:o for o in scene['objects']}
    if any(objects[n].get('locks',{}).get('placement') and any(f.startswith('bbox.') for f in fields) for n,fields in grants.items()):
        raise ValueError('Frozen placement requires the existing explicit user edit workflow')
    signature=identity({'baseline':baseline['pptx'],'plan':state['frame_plan'],'proposals':proposals,'grants':grants})
    if any(v.get('signature')==signature for v in state.get('rule_attempts',[])):
        raise ValueError('Do not repeat an unchanged rule action; revise the located source/strategy')
    if not grants:return {'status':'NO_ACTIONABLE_RULE_REPAIR','debt':debt,'coverage':ec.report(task,state,baseline)}
    total_grants=cumulative_grants(state,baseline,grants)
    with writer(task):
        relevant={}
        for item in failed:
            if item.get('object') not in grants and item.get('child') not in grants:continue
            frame=next(f for f in plan['frames'] if item['id']==f['id'] or item['id'].startswith(f['id']+'.'))
            relevant[item['id']]={'kind':'frame','contract':frame}
        interfaces={r['id']:r for r in sc.contracts(task,state)}
        from .source_spacing import prepare as prepare_source_spacing
        for proposal in proposals:
            target=proposal['contract'];source,effective=prepare_source_spacing(task,state,interfaces[target])
            if effective is None:raise ValueError('A finite repair requires its current program-classified original spacing')
            relevant[target]={'kind':'interface','contract':effective}
        branches=authorize_rules(state,relevant,{'source_hash':state['source']['sha256'],'rules':relevant},grants)
        number=state['revision']+1;folder=task/'versions'/('r'+str(number).zfill(3))
        while folder.exists():number+=1;folder=task/'versions'/('r'+str(number).zfill(3))
        folder.mkdir();target=folder/'drawing.pptx';source=ec.resource(task,baseline['pptx'])
        interface_names={n for p in proposals for n in p['objects']}
        frame_grants={n:v for n,v in grants.items() if n not in interface_names}
        actions=[]
        if frame_grants:
            from .frame_actions import apply
            intermediate=folder/'frames.pptx' if proposals else target
            actions.append(apply(plan,task,source,intermediate,state['source_size'],
                {'expected_baseline_sha256':digest(source),'allowed_changes':frame_grants}))
            source=intermediate
        if proposals:actions.append(_translate(source,target,state['source_size'],proposals))
        from .native_snapshot import snapshot
        current_scene=snapshot(task,state,target,scene);current_scene['revision']=number
        scene_file=folder/'scene.json';write_json(scene_file,current_scene)
        candidate={'revision':number,'scene':a._file(task,scene_file),'pptx':a._file(task,target),
            'reason':{'kind':'program_all_applicable_rule_repair','signature':signature},
            'baseline':state['selected']['pptx']['sha256'],'allowed':total_grants,
            'parent_pptx':copy.deepcopy(baseline['pptx']),'step_allowed':copy.deepcopy(grants),
            'repair_chain':copy.deepcopy(baseline.get('repair_chain',[]))+[
                {'parent':baseline['pptx'],'signature':signature,'allowed':grants}],
            'font_delivery':copy.deepcopy(baseline.get('font_delivery',{}))}
        candidate['semantic_composition_guard']=sc.guard_saved(task,state,target,baseline,grants)
        state.update(revision=number,active_candidate=candidate,scene=candidate['scene'],stage='host_render',packet=None)
        state.pop('acceptance',None)
        updates={}
        for cid,previous in state['built'].items():
            built=copy.deepcopy(previous)
            ids={o['id'] for o in built['objects']}
            built['objects']=[o for o in current_scene['objects'] if o['id'] in ids]
            built['method']['objects']=copy.deepcopy(built['objects']);built['fingerprint']=identity(built['method'])
            if ids & set(total_grants):updates[cid]=built
        state['rule_pending_built']=updates
        evidence={'schema':'rule-action-1','signature':signature,'candidate':candidate['pptx'],'baseline':baseline['pptx'],
            'grants':grants,'cumulative_grants':total_grants,'repair_chain':candidate['repair_chain'],
            'actions':actions,'proposals':proposals,'debt':debt,
            'status':'SAVED_REQUIRES_ACTUAL_RENDER_AND_FULL_CHECKS','acceptance':False}
        write_json(folder/'rule-action.json',evidence)
        state.setdefault('rule_attempts',[]).append({'signature':signature,'candidate':candidate['pptx'],'status':evidence['status'],'branches':branches})
        a._event(task,'program_rule_repair_saved',{'revision':number,'signature':signature,'grants':grants});a._save(task,state)
    return {'status':evidence['status'],'candidate':candidate,'next':'next '+str(task)}


def observe_working(task):
    """Use shared adoption gates after actual rule rendering; never final PASS."""
    from . import candidate_adoption
    task,state=a._state(task)
    candidate=state.get('active_candidate')
    if not candidate or candidate.get('reason',{}).get('kind')!='program_all_applicable_rule_repair' or not candidate.get('render'):
        raise ValueError('Observe the actual pending rule candidate first')
    with writer(task):
        current=fp.check(fp.load(task,state['frame_plan']),task,ec.resource(task,candidate['pptx']),state['source_size'])
        composition=sc.report(task,state,candidate)
        reflect_rules(state,candidate,current['items']+composition['items'])
        # Preserve actual reflection even when a separate source/text/layout
        # adoption gate is still pending; this is not a retained/accepted draw.
        a._save(task,state)
        ticket=candidate_adoption.prepare(task,state,candidate,candidate['allowed'],mode='program_rule_repair')
        result={'status':'WORKING_PROGRESS_RETAINED' if ticket['eligible'] else 'WORKING_CANDIDATE_REQUIRES_SOURCE_QUALITY',
            'candidate':candidate['pptx'],'final_acceptance':False,'gate':candidate['adoption_gate']}
        if ticket['eligible']:
            updates=state.pop('rule_pending_built',{})
            candidate_adoption.retain(task,state,candidate,ticket,updates=updates)
            state['built'].update(updates)
            state['methods'].update({k:v['method'] for k,v in updates.items()})
            state['active_candidate']=None
        ec.report(task,state,candidate)
        a._event(task,'program_rule_candidate_observed',result);a._save(task,state)
        write_json(ec.resource(task,candidate['pptx']).parent/'rule-observation.json',result)
    return result
