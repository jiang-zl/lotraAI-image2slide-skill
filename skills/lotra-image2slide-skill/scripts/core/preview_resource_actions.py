"""Repair only normalized SVG compatibility previews with exact replay.

The source-derived SVG, viewport, native geometry and every other package part
are protected. No host-supplied pixels, coordinates or numeric waivers exist.
Renderer-dependent PNG resources are frozen before saving the new candidate.
"""
import copy,hashlib,posixpath
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
from .common import digest,identity,read_json,write_json,safe_path,writer
from .mathml import NS


def _construct(task,state,baseline,items):
    from .inspect import inventory
    from . import frame_plan as fp
    with ZipFile(safe_path(task,baseline['pptx']['path'])) as z:
        payload={n:z.read(n) for n in z.namelist()}
    tree=E.fromstring(payload['ppt/slides/slide1.xml']);nodes,duplicate=inventory(tree)
    if duplicate:raise ValueError('Compatibility repair needs unique actual owners')
    rels=E.fromstring(payload['ppt/slides/_rels/slide1.xml.rels']);mapping={r.get('Id'):r for r in rels}
    for item in items:
        node=nodes[item['object']]['node'];blip=node.find('p:blipFill/a:blip',NS)
        if blip is None:raise ValueError('Missing actual compatibility blip')
        vector=node.find('.//{'+fp.ASVG_NS+'}svgBlip')
        if vector is None:raise ValueError('Preview repair must preserve a source-bound native SVG')
        rid=vector.get('{'+fp.R_NS+'}embed');ref=mapping[rid]
        target=posixpath.normpath(posixpath.join('ppt/slides',ref.get('Target')))
        if hashlib.sha256(payload[target]).hexdigest()!=item['svg_sha256']:
            raise ValueError('Normalized SVG changed before compatibility repair')
        png=safe_path(task,item['preview']['path'])
        if digest(png)!=item['preview']['sha256']:raise ValueError('Frozen normalized PNG changed')
        name='ppt/media/lotra-preview-'+item['preview']['sha256']+'.png'
        if name in payload and payload[name]!=png.read_bytes():raise ValueError('Resource identity collision')
        payload[name]=png.read_bytes();serial=1
        while 'rId'+str(serial) in mapping:serial+=1
        newrid='rId'+str(serial)
        added=E.SubElement(rels,'{'+fp.REL_NS+'}Relationship',Id=newrid,Type=fp.R_NS+'/image',Target='../media/'+Path(name).name)
        mapping[newrid]=added;blip.set('{'+fp.R_NS+'}embed',newrid)
    payload['ppt/slides/slide1.xml']=E.tostring(tree,encoding='UTF-8',xml_declaration=True,standalone=True)
    payload['ppt/slides/_rels/slide1.xml.rels']=E.tostring(rels,encoding='UTF-8',xml_declaration=True,standalone=True)
    return payload


def guard(task,state,candidate,approved):
    from .source_layout_actions import guard as source_guard
    record=next((r for r in state.get('preview_resource_attempts',[]) if r['candidate']==candidate['pptx']['sha256']),None)
    if record is None:return {'passed':False,'objects':[],'reason':'No frozen compatibility resource constructor'}
    contract=read_json(safe_path(task,record['contract']['path']))
    if digest(safe_path(task,record['contract']['path']))!=record['contract']['sha256']:
        raise ValueError('Frozen compatibility repair contract changed')
    if contract['source_hash']!=state['source']['sha256'] or contract['frame_plan']!=state['frame_plan']:
        raise ValueError('Compatibility repair must retain the same frozen original frames')
    baseline=contract['baseline']
    if digest(safe_path(task,baseline['pptx']['path']))!=baseline['pptx']['sha256']:
        raise ValueError('Compatibility baseline changed')
    prior=source_guard(task,state,baseline,approved)
    if not prior['passed']:return {'passed':False,'objects':[],'reason':'Protected source predecessor does not replay exactly'}
    expected=_construct(task,state,baseline,contract['items'])
    with ZipFile(safe_path(task,candidate['pptx']['path'])) as z:
        passed=sorted(expected)==sorted(z.namelist()) and all(expected[n]==z.read(n) for n in expected)
    return {'passed':passed,'objects':sorted(set(prior['objects'])|{r['object'] for r in contract['items']}),
        'method':'exact_normalized_preview_and_complete_native_replay','contract':record['contract'],
        'protected':'Only source-normalized PNG compatibility references and their resource parts change; native SVG, crop, geometry, fonts and all unrelated package bytes replay exactly.'}


def execute(task,request):
    from . import agent_runtime as a,frame_plan as fp
    from .content_viewport import normalize
    from .native_snapshot import snapshot
    from .semantic_composition import guard_saved
    task,state=a._state(task);baseline=state.get('active_candidate') or state['selected']
    if set(request)!={'expected_baseline_sha256'} or request['expected_baseline_sha256']!=baseline['pptx']['sha256'] or not baseline.get('render'):
        raise ValueError('Bind one actually rendered baseline; no preview pixels or coordinates accepted')
    plan=fp.load(task,state['frame_plan']);checked=fp.check(plan,task,safe_path(task,baseline['pptx']['path']),state['source_size']);items=[]
    for row in checked['items']:
        if row['passed']:continue
        if (row.get('compatibility_preview_pass') is not False or row.get('effective_content_media_sha256')!=row.get('expected_media_sha256')
                or row.get('frame_error_source_px',1)>0.01 or row.get('native_crop')!=row.get('expected_crop') or row.get('normalized_full_rectangle_alpha_min',255)!=255):
            raise ValueError('Another frame/content defect requires its own source action: '+row['id'])
        frame=next(f for f in plan['frames'] if row['id'].startswith(f['id']+'.'))
        member=next(m for m in frame.get('members',[]) if m['object']==row['object'])
        window=member['content_window'];normalized=normalize(fp.window_content(window),window['render_type'],window,row['expected_frame'],task)
        # Renderer caches may be regenerated on another host. Freeze the
        # derived program output as its own immutable transaction resource.
        png=safe_path(task,normalized['preview']['path']);frozen=task/'source/preview-repairs'/(normalized['preview']['sha256']+'.png')
        frozen.parent.mkdir(parents=True,exist_ok=True)
        if frozen.exists() and digest(frozen)!=digest(png):raise ValueError('Frozen compatibility resource changed')
        if not frozen.exists():frozen.write_bytes(png.read_bytes())
        items.append({'object':row['object'],'svg_sha256':normalized['sha256'],
            'preview':{'path':frozen.relative_to(task).as_posix(),'sha256':digest(frozen)},'frame':row['id']})
    if not items:return {'status':'NO_NORMALIZED_PREVIEW_REPAIR_REQUIRED'}
    if len(items)>32:raise ValueError('Use at most 32 finite compatibility repairs')
    contract={'schema':'normalized-preview-repair-1','source_hash':state['source']['sha256'],'frame_plan':state['frame_plan'],'baseline':baseline,'items':items}
    key=identity(contract);contract_file=task/'source/preview-repairs'/(key+'.json');write_json(contract_file,contract)
    payload=_construct(task,state,baseline,items)
    with writer(task):
        number=state['revision']+1;folder=task/'versions'/('r'+str(number).zfill(3))
        while folder.exists():number+=1;folder=task/'versions'/('r'+str(number).zfill(3))
        folder.mkdir();target=folder/'drawing.pptx'
        with ZipFile(target,'x',ZIP_DEFLATED,compresslevel=9) as z:
            for name,data in payload.items():z.writestr(name,data)
        prior_scene=read_json(safe_path(task,baseline['scene']['path']));scene=snapshot(task,state,target,prior_scene)
        scene_file=folder/'scene.json';write_json(scene_file,scene)
        candidate={'revision':number,'scene':a._file(task,scene_file),'pptx':a._file(task,target),
            'reason':{'kind':'normalized_preview_program_repair'},'baseline':baseline['pptx']['sha256'],
            'allowed':{r['object']:['media'] for r in items},'font_delivery':copy.deepcopy(baseline.get('font_delivery',{}))}
        candidate['semantic_composition_guard']=guard_saved(task,state,target,baseline,candidate['allowed'])
        record={'baseline':baseline['pptx']['sha256'],'candidate':candidate['pptx']['sha256'],'contract':a._file(task,contract_file),'objects':list(candidate['allowed'])}
        state.setdefault('preview_resource_attempts',[]).append(record)
        state.update(revision=number,active_candidate=candidate,scene=candidate['scene'],stage='host_render',packet=None)
        state.pop('acceptance',None);state.pop('quality_result',None)
        a._event(task,'normalized_preview_program_repair_saved',record);a._save(task,state)
    return {'status':'SAVED_REQUIRES_ACTUAL_RENDER','candidate':candidate,'repaired':len(items),'acceptance':False}
