"""Actual saved-rule candidate renderer through the ordinary tool packet.

Reuse a baseline's proven backend for comparable local observation. An actual
Office failure may take one available alternative branch, explicitly recorded.
No source/quality/font gate is disabled by backend choice.
"""
import copy
from pathlib import Path
from . import agent_runtime as a
from .common import read_json,write_json,digest,safe_path


def prepare_task(task,force=False):
    """Schedule missing full-inventory observations on identical native bytes."""
    from . import semantic_composition as sc
    task,state=a._state(task)
    with a.writer(task):
        current=state.get('active_candidate') or state.get('selected')
        if not current:return {'status':'NO_SAVED_CANDIDATE'}
        if not current.get('render'):
            file=safe_path(task,current['pptx']['path'])
            if digest(file)!=current['pptx']['sha256']:raise ValueError('Unrendered saved candidate changed')
            current['semantic_composition_guard']=sc.guard_saved(task,state,file)
            state['active_candidate']=current;state['scene']=current['scene'];state.update(stage='host_render',packet=None)
            state.pop('acceptance',None);a._save(task,state)
            return {'status':'ACTUAL_RENDER_ALREADY_REQUIRED'}
        guard=sc.guard_saved(task,state,safe_path(task,current['pptx']['path']))
        if not guard.get('capture_request') and not force:return {'status':'NO_MISSING_NATIVE_OBSERVATIONS'}
        candidate=state.get('active_candidate')
        if candidate is None:
            candidate=copy.deepcopy(current);state['active_candidate']=candidate
        candidate['semantic_composition_guard']=guard
        candidate['prior_render']=candidate['render']
        candidate.pop('render');candidate.pop('preview',None)
        state['stage']='host_render';state['packet']=None;state.pop('acceptance',None)
        a._event(task,'whole_native_observations_required',{'pptx':candidate['pptx'],
            'capture_request':guard['capture_request'],'drawing_gain':False})
        a._save(task,state)
    return {'status':'ACTUAL_NATIVE_OBSERVATIONS_SCHEDULED','remaining':guard.get('remaining_captures',0)}


def render_task(task,_depth=0,force=False):
    if _depth>=32:raise ValueError('Actual capture batch budget reached; preserve unfinished work and its missing captures')
    if _depth==0:prepare_task(task,force)
    packet=a.next_packet(task)
    if packet.get('packet',{}).get('kind')!='tool_render':
        task,state=a._state(task);current=state.get('active_candidate') or state.get('selected')
        if current and current.get('render'):
            return {'status':'ACTUAL_RENDER_COMPLETED_SOURCE_ACTION_REQUIRED','stage':state['stage'],
                    'render':current['render'],'preview':current['preview'],'next':packet,
                    'acceptance':False}
        raise ValueError('The same runtime must request an actual tool_render')
    task,state=a._state(task);candidate=state['active_candidate'];pptx=safe_path(task,candidate['pptx']['path'])
    caps=copy.deepcopy(state['capabilities']);previous=state.get('selected') or {}
    route={'input_sha256':digest(pptx),'selection':'discovered host preference','failures':[],'acceptance':False}
    prior=candidate.get('prior_render') or previous.get('render')
    if prior:
        receipt=read_json(safe_path(task,prior['path']))
        backend=str(receipt.get('backend','')).lower()
        if backend=='libreoffice' and caps['libreoffice']['available']:
            caps['render_preference']='libreoffice';route['selection']='previous actual baseline backend for comparable local checks'
    output=pptx.parent/'actual-render';serial=1
    while output.exists():
        output=pptx.parent/('actual-render-'+str(serial));serial+=1
    from .tool_router import render_saved
    try:actual=render_saved(pptx,output,caps,state['objectives']['render_width'])
    except (RuntimeError,TimeoutError,__import__('subprocess').TimeoutExpired) as error:
        route['failures'].append({'backend':caps.get('render_preference'),'reason':str(error)})
        if caps.get('render_preference')!='powerpoint' or not caps['libreoffice']['available']:raise
        caps['render_preference']='libreoffice';output=output.with_name(output.name+'-alternative')
        actual=render_saved(pptx,output,caps,state['objectives']['render_width'])
        route['selection']='one available alternative after captured actual Office failure'
    route['actual_backend']=actual.get('backend');route['actual_receipt']={'path':(output/'render.json').relative_to(task).as_posix(),'sha256':digest(output/'render.json')}
    write_json(output/'render-routing.json',route)
    result=a.submit(task,{'packet_id':packet['packet']['packet_id'],
        'preview':(output/'Final_preview.png').relative_to(task).as_posix(),'render':(output/'render.json').relative_to(task).as_posix()})
    if result.get('stage')=='host_render':
        following=render_task(task,_depth+1)
        following.setdefault('actual_capture_batches',[]).insert(0,route)
        return following
    return {**result,'actual_backend':actual.get('backend'),'route':route}
