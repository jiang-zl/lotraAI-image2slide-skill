"""Opt-in source-bound text/primitive/math acceptance; icon paths are untouched.

The contract is read from the original by the agent, never inferred from the
candidate. Group descendants and all other component types remain on v1.30.
"""
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
import copy
from .common import read_json, write_json, digest, identity, safe_path

VERSION='native-core-1.31.0'
KINDS={'text','shape','equation'}


def quantize(value,step=.5):
    d=Decimal(str(value));s=Decimal(str(step))
    if not d.is_finite() or s<=0:raise ValueError('Finite discrete parameter required')
    return float((d/s).quantize(Decimal('1'),rounding=ROUND_HALF_UP)*s)


def normalize(scene,owners):
    value=copy.deepcopy(scene)
    def walk(item):
        if isinstance(item,dict):
            for key,child in list(item.items()):
                if key=='font_size':item[key]=quantize(child)
                else:walk(child)
        elif isinstance(item,list):
            for child in item:walk(child)
    for obj in value['objects']:
        if obj['id'] in owners:walk(obj)
    return value


def contract(task):
    file=Path(task)/'native-core/contract.json'
    if not file.is_file():return None
    value=read_json(file)
    seal=value.pop('seal')
    if identity(value)!=seal:raise ValueError('Frozen native core contract changed')
    value['seal']=seal
    return value


def bind(task,request):
    from .agent_runtime import _state
    task,state=_state(task)
    if request.get('source_sha256')!=state['source']['sha256'] or digest(safe_path(task,state['source']['path']))!=request['source_sha256']:
        raise ValueError('Bind the unchanged original')
    if not request.get('source_reading') or not request.get('font_decisions'):
        raise ValueError('Original-only content/type/geometry and explicit font decisions required')
    scene=copy.deepcopy(request['scene']);owners=request['owners']
    if scene.get('source',{}).get('sha256')!=request['source_sha256']:
        raise ValueError('Frozen scene must bind the same original')
    objects={o['id']:o for o in scene['objects']}
    if not owners or len(set(owners))!=len(owners):raise ValueError('Unique explicit native core owners required')
    for owner in owners:
        obj=objects[owner]
        if obj['render_type'] not in KINDS or obj.get('parent') is not None:
            raise ValueError('Only standalone text, primitive shapes and equations; grouped/icon descendants stay v1.30: '+owner)
        if obj.get('semantic_type') in ('icon','photo','chart','table','scene','curve','connector'):
            raise ValueError('Other component types remain unchanged')
        if obj['render_type'] in ('text','equation') and not {'font','font_size','color'}<=set(obj.get('style',{})):
            raise ValueError('Freeze explicit font, size, weight and colour before building')
    scene=normalize(scene,set(owners))
    value={'schema':VERSION,'source_sha256':request['source_sha256'],'owners':owners,'scene':scene,
           'source_reading':request['source_reading'],'font_decisions':request['font_decisions'],
           'max_distinct_candidates_per_phase':3,'font_step_pt':.5,'optional_score_step':.05}
    value['seal']=identity(value)
    file=task/'native-core/contract.json'
    if file.exists() and read_json(file)!=value:raise ValueError('Contract already frozen; do not retarget to a candidate')
    write_json(file,value);write_json(task/'native-core/Frozen-scene.json',scene)
    return {'status':'SOURCE_BOUND','owners':owners,'scene':str(task/'native-core/Frozen-scene.json'),
            'scope':'Only explicitly selected standalone text/shape/math; no icon or instance changes'}


def owned(task,names):
    c=contract(task)
    return bool(c and names and set(names)<=set(c['owners']))


def check(task,state,candidate,owners=None,force=False):
    from .native_core_checks import batch_check,snapshots
    from .execution_contract import resource
    c=contract(task)
    if not c:return None
    if c['source_sha256']!=state['source']['sha256']:raise ValueError('Native core source changed')
    resource(task,state['source'])
    scene=read_json(resource(task,candidate['scene']));pptx=resource(task,candidate['pptx'])
    wanted=set(c['owners'] if owners is None else owners)
    if not wanted<=set(c['owners']):raise ValueError('Native core cannot evaluate another component type')
    actual=snapshots(pptx);scene_objects={o['id']:o for o in scene['objects']}
    file=Path(task)/'native-core/progress.json'
    progress=read_json(file) if file.exists() else {'seal':c['seal'],'owners':{}}
    if progress['seal']!=c['seal']:raise ValueError('Native progress belongs to another contract')
    body_ready=all(progress['owners'].get(n,{}).get('body',{}).get('locked') for n in c['owners'])
    result={}
    for phase in ('body','placement'):
        if phase=='placement' and not body_ready:continue
        pending=[];keys={}
        for owner in sorted(wanted):
            slot=progress['owners'].setdefault(owner,{}).setdefault(phase,{'attempts':[]})
            snap=actual.get(owner,{}).get(phase)
            obj=scene_objects.get(owner,{})
            fields={k:obj.get(k) for k in (('render_type','semantic_type','content','style') if phase=='body' else ('parent','z_order'))}
            fields['geometry']=obj.get('bbox',[])[2:] if phase=='body' else obj.get('bbox',[])[:2]
            fingerprint=identity([c['seal'],fields,snap,phase,digest(__file__),digest(Path(__file__).with_name('native_core_checks.py')),digest(Path(__file__).with_name('native_core_inspect.py'))])
            keys[owner]=(fingerprint,snap)
            if slot.get('locked') and snap!=slot['locked']:
                result.setdefault(owner,{})[phase]={'status':'FAIL','reason':'LOCKED_ATTRIBUTE_CHANGED'}
            elif not force and slot.get('fingerprint')==fingerprint:
                result.setdefault(owner,{})[phase]=slot['result']
            elif not slot.get('locked') and fingerprint not in slot['attempts'] and len(slot['attempts'])>=3:
                result.setdefault(owner,{})[phase]={'status':'FAIL','reason':'FINITE_CANDIDATES_EXHAUSTED','next':'NEEDS_DECISION'}
            else:pending.append(owner)
        if pending:
            checks=batch_check(scene,c['scene'],task,pptx,pending,phase)
            for owner,row in checks.items():
                slot=progress['owners'][owner][phase];fingerprint,snap=keys[owner]
                if fingerprint not in slot['attempts']:slot['attempts'].append(fingerprint)
                slot.update(fingerprint=fingerprint,result=row)
                if row['status']=='PASS':slot.setdefault('locked',snap)
                result.setdefault(owner,{})[phase]=row
        if phase=='body':
            body_ready=all(progress['owners'].get(n,{}).get('body',{}).get('locked') for n in c['owners'])
    write_json(file,progress)
    rows=[]
    for owner in sorted(wanted):
        phases=result.get(owner,{})
        passed=set(phases)=={'body','placement'} and all(v['status']=='PASS' for v in phases.values())
        rows.append({'owner':owner,'passed':passed,'status':'minimum_met' if passed else 'below_fixed_targets',
                     'phases':phases,'values':{'native_core_match':float(passed)}})
    return {'status':'minimum_met' if rows and all(r['passed'] for r in rows) else 'below_fixed_targets',
            'passed':bool(rows) and all(r['passed'] for r in rows),'items':rows,'policy':VERSION,
            'source_sha256':c['source_sha256'],'pptx_sha256':candidate['pptx']['sha256'],
            'scope':'native semantics and source parameters; final layout/visibility gates remain required'}


def appearance(task,state,candidate,item):
    names=item.get('objects',[])
    if not owned(task,names):return None
    r=check(task,state,candidate,names)
    return {'passed':r['passed'],'native_core':r,'constraints':[{'id':'native_core_match','passed':r['passed']}],
            'score_dimensions':{},'weighted_score':None,'weighted_score_status':'NATIVE_STRUCTURAL',
            'selected_dimensions':[],'target':'source_native_parameters','limits':r['scope']}


def source_result(task,state,candidate,unit):
    if not owned(task,unit.get('objects',[])):return None
    r=check(task,state,candidate,unit['objects']);status=r['status']
    return {'unit':unit['id'],'status':status,'values':{'native_core_match':float(r['passed'])},
            'constraints':[{'id':'native_core_match','status':status,'value':float(r['passed'])}],
            'native_core':r,'candidate_hash':candidate['pptx']['sha256'],'roi':unit['roi']}


def typography(task,state,candidate,ids,force,legacy):
    from .textbox_quality import native_rows
    c=contract(task)
    if not c:return legacy(task,state,candidate,ids,force)
    all_rows=[r for r in native_rows(safe_path(task,candidate['pptx']['path'])) if ids is None or r['id'] in ids]
    selected=[r for r in all_rows if r['object'] in c['owners']]
    if not selected:return legacy(task,state,candidate,ids,force)
    old=[r['id'] for r in all_rows if r not in selected]
    base=legacy(task,state,candidate,old,force) if old else {'items':[]}
    r=check(task,state,candidate,[v['object'] for v in selected],force)
    by={x['owner']:x for x in r['items']}
    for row in selected:
        item=by[row['object']]
        base['items'].append({'id':row['id'],'object':row['object'],'status':item['status'],'native_core':item,
            'values':{'content_match':float(item['passed']),'math_match':float(item['passed']),'format_match':float(item['passed'])},
            'targets':{'content_match':1.,'math_match':1.,'format_match':1.}})
    ownership='NATIVE_CORE_WITH_VALID_LEGACY_OWNERS' if not old or base.get('glyph_ownership_status')=='BOUND_ACTUAL_NATIVE_TEXT_LAYER' else 'LEGACY_BOUNDS_ONLY'
    base.update(status='minimum_met' if all(v['status']=='minimum_met' for v in base['items']) else 'below_or_unmeasured',
                glyph_ownership_status=ownership,schema=VERSION)
    return base


def guarded_text_ids(task,pptx,allowed):
    """Saved text guard uses the same frozen source, without changing icon rows."""
    from .native_core_checks import batch_check
    c=contract(task)
    if not c:return set()
    objects={o['id']:o for o in c['scene']['objects']}
    names=[n for n in c['owners'] if objects[n]['render_type'] in ('text','equation') and (allowed is None or n in allowed)]
    from .inspect import inventory,xml
    saved,_=inventory(xml(pptx))
    bound={n for n in c['owners'] if objects[n]['render_type'] in ('text','equation') and n in saved}
    if not names:return bound
    body=batch_check(c['scene'],c['scene'],task,pptx,names,'body')
    placement=batch_check(c['scene'],c['scene'],task,pptx,names,'placement')
    if any(r['status']!='PASS' for r in [*body.values(),*placement.values()]):
        raise ValueError('Source-bound native text/math attributes differ; repair only the located property')
    return bound


def command(task,operation,request=None):
    if operation=='bind':return bind(task,request)
    from .agent_runtime import _state
    task,state=_state(task)
    candidate=state.get('active_candidate') or state.get('selected')
    if not candidate:raise ValueError('Build the current native candidate before checking')
    return check(task,state,candidate,(request or {}).get('owners'),force=operation=='final')
