"""Prepared project archives, exclusive language membership and source-glyph ranking."""
import copy
import math
import os
import shutil
import unicodedata
from pathlib import Path
from .common import ROOT, identity, digest, read_json, write_json, safe_path, writer
from . import font_resources as resources


def policy():
    return read_json(ROOT/'config/font-collections.json')


def language(char):
    code = ord(char)
    if (0x3400 <= code <= 0x4DBF or 0x4E00 <= code <= 0x9FFF or
        0xF900 <= code <= 0xFAFF or 0x20000 <= code <= 0x323AF or
        0x3000 <= code <= 0x303F or 0xFF01 <= code <= 0xFF60):return 'zh'
    if ('LATIN' in unicodedata.name(char, '') or code < 128 or
        unicodedata.category(char)[0] in ('P', 'N', 'S', 'Z', 'C')):return 'en'
    if unicodedata.category(char)[0] == 'M':return 'en'
    return 'unsupported'


def request_key(request):
    return identity({k:request[k] for k in ('owner','location','role','characters','literal_hash','proposed_family','bold','italic')})


def role_language(role):
    return 'zh' if role == 'ea' else 'en' if role == 'latin' else 'math' if role.startswith('math') else 'unsupported'


def classify(face):
    """Metadata classification is independent of the text being reconstructed."""
    settings = policy(); names = {resources.name_key(n) for n in face['aliases']}
    matched = [lang for lang, families in settings['languages'].items()
               if names & {resources.name_key(n) for n in families}]
    if len(matched) == 1:return matched[0], 'curated_family'
    if matched:raise ValueError('Font family appears in conflicting language collections')
    from fontTools.ttLib import TTFont
    font = TTFont(face['path'], fontNumber=face['face_index'], lazy=True)
    try:
        codepages = int(getattr(font.get('OS/2'), 'ulCodePageRange1', 0))
        cmap = font.getBestCmap() or {}
        chinese = sum(ord(c) in cmap for c in settings['chinese_probe'])/len(settings['chinese_probe'])
        latin = all(ord(c) in cmap for c in settings['english_probe'])
        if codepages & ((1 << 18) | (1 << 20)) and chinese >= settings['unknown_chinese_probe_minimum']:
            return 'zh', 'chinese_codepage_and_representative_glyphs'
        # Japanese/Korean/Chinese resources do not enter English on ASCII coverage.
        if latin and codepages & 1 and not codepages & sum(1 << i for i in range(17, 22)) and chinese < 0.1:
            return 'en', 'latin_codepage_without_cjk_family'
    finally:font.close()
    return None, 'unclassified_requires_resource_metadata'


def root(project):
    return Path(project)/'.lotraAI-build/toolchain/font-collections'


def load(project):
    file = root(project)/'Collection.json'
    return read_json(file) if file.is_file() else {'schema':'language-font-archive-1','faces':{},'history':[]}


def archive(project, faces, reason):
    """Archive actual font bytes before publishing a collection revision."""
    directory = root(project); directory.mkdir(parents=True, exist_ok=True)
    with writer(directory):
        previous = load(project); value = copy.deepcopy(previous)
        for face in faces:
            lang, basis = classify(face)
            if lang not in ('zh','en') or not face['editable_embedding'] or face.get('variable'):continue
            if digest(face['path']) != face['file_sha256']:raise ValueError('Font source changed during archive preparation')
            file = directory/'files'/(face['file_sha256']+Path(face['path']).suffix.lower())
            file.parent.mkdir(exist_ok=True)
            if not file.exists():
                temp = file.with_name(file.name+'.part')
                if temp.exists():
                    if digest(temp) == face['file_sha256']:os.replace(temp,file)
                    else:os.replace(temp,temp.with_name(temp.name+'.retained-'+digest(temp)[:24]))
                if not file.exists():shutil.copyfile(face['path'],temp);os.replace(temp,file)
            if digest(file) != face['file_sha256']:raise ValueError('Archived font identity conflict')
            value['faces'][face['id']] = {**face,'path':str(file),'language':lang,'classification':basis,
                'archive_file':file.relative_to(Path(project)).as_posix()}
        value['policy_hash'] = identity(policy())
        # History and immutable snapshots prevent a newer collection changing an old choice.
        if {k:v for k,v in value.items() if k not in ('history','revision')} != {k:v for k,v in previous.items() if k not in ('history','revision')}:
            value['revision'] = identity({'faces':value['faces'],'policy':value['policy_hash']})
            value.setdefault('history',[]).append({'previous':previous.get('revision'),'revision':value['revision'],'reason':reason})
            snapshot = directory/('Collection-'+value['revision']+'.json')
            if not snapshot.exists():write_json(snapshot,value)
            write_json(directory/'Collection.json',value)
    return value


def prepare(state):
    """Run before source font selection; archive common available families once."""
    value = load(state['project'])
    common = {resources.name_key(n) for names in policy()['languages'].values() for n in names}
    available = resources.available(state['capabilities'])
    selected = [f for f in available if common & {resources.name_key(n) for n in f['aliases']}
                and f['editable_embedding'] and not f.get('variable')]
    if value.get('policy_hash') != identity(policy()) or any(f['id'] not in value['faces'] for f in selected):
        value = archive(state['project'],selected,'Prepare common Chinese and English font collections before construction')
    state['font_collection'] = {'revision':value.get('revision'),'policy_hash':identity(policy()),
                              'counts':{lang:sum(f['language']==lang for f in value['faces'].values()) for lang in ('zh','en')}}
    return value


def classifications(state):
    file=root(state['project'])/'Classifications.json'
    existing=read_json(file) if file.is_file() else {}
    code=digest(__file__)
    context=identity({'policy':policy(),'implementation':code,'environment':state['capabilities'].get('fonts',{}).get('environment_key')})
    if existing.get('context')==context:return existing['faces']
    previous=existing.get('faces',{}) if existing.get('policy_hash')==identity(policy()) and existing.get('implementation')==code else {}
    rows={}
    for face in resources.available(state['capabilities']):
        if face['id'] in previous:rows[face['id']]=previous[face['id']]
        else:
            lang,basis=classify(face)
            rows[face['id']]={'language':lang,'classification':basis}
    write_json(file,{'context':context,'policy_hash':identity(policy()),'implementation':code,'faces':rows})
    return rows


def eligible(state, request, extend=False, constrained=True):
    lang = role_language(request['role'])
    if lang == 'math':return resources.available(state['capabilities'])
    if lang == 'unsupported':return []
    value = prepare(state); faces = dict(value['faces'])
    if extend:
        metadata=classifications(state)
        for face in resources.available(state['capabilities']):
            if face['id'] not in faces:
                info=metadata[face['id']]
                if info['language'] == lang:faces[face['id']] = {**face,**info}
    result=[f for f in faces.values() if f['language'] == lang and f['editable_embedding'] and not f.get('variable')
            and not resources.coverage(f,request['characters'])
            and (request['bold'] or f['weight'] < 600) and (request['italic'] or not f['italic'])]
    unfiltered=result
    constraint=state.get('font_constraints',{}).get(request['id'],{}) if constrained else {}
    if constraint.get('source_hash')==state['source']['sha256'] and constraint.get('request_hash')==request_key(request):
        classes=constraint.get('style_classes');ids=constraint.get('resource_ids')
        if classes:result=[f for f in result if f.get('style_class','unknown') in classes]
        if ids:result=[f for f in result if f['id'] in ids]
        # The final comparison must also measure its current legal baseline.
        baseline=state.get('font_contract',{}).get('bindings',{}).get(request['id'],{}).get('resource',{}).get('id') if extend else None
        if baseline and baseline not in {f['id'] for f in result}:
            result+= [f for f in unfiltered if f['id']==baseline]
    return result


def store_constraints(task,state,scene,values):
    from .font_contract import requests
    from . import component_workflow as c
    rows={r['id']:r for r in requests(scene)};updates={}
    for key,value in values.items():
        request=rows[key];proof=value['evidence'];observed=read_json(c._resource(Path(task),proof))
        if (observed.get('source_hash')!=state['source']['sha256'] or observed.get('observer') not in ('host_model','human')
                or not observed.get('observations') or not value.get('reason')):
            raise ValueError('Font narrowing needs an independent located source observation')
        classes=value.get('style_classes',[]);ids=value.get('resource_ids',[])
        if not classes and not ids:raise ValueError('Choose observed style classes or an explicit bounded source-supported resource set')
        if set(classes)-{'serif','sans','unknown'} or len(set(ids))!=len(ids) or len(ids)>policy()['max_ranked_faces']:
            raise ValueError('Unsupported or unbounded font narrowing')
        all_faces={f['id'] for f in eligible(state,request,extend=True,constrained=False)}
        if set(ids)-all_faces:raise ValueError('Font narrowing cannot introduce a wrong-language or ineligible face')
        updates[key]={'source_hash':state['source']['sha256'],'request_hash':request_key(request),
                      'style_classes':classes,'resource_ids':ids,'evidence':proof,'reason':value['reason']}
    state.setdefault('font_constraints',{}).update(updates)


def selection_context(state,request,extend=False):
    return identity({'source':state['source']['sha256'],'request':request_key(request),'policy':policy(),
        'implementation':digest(__file__),'environment':state['capabilities'].get('fonts',{}).get('environment_key'),
        'extended':extend,
        'faces':sorted(f['id'] for f in eligible(state,request,extend)),
        'samples':state.get('font_samples',{}).get(request['id']),
        'constraint':state.get('font_constraints',{}).get(request['id'])})


def assert_language(face, role):
    lang = role_language(role)
    if lang == 'math':return
    actual, basis = classify(face)
    if lang not in ('zh','en') or actual != lang:
        raise ValueError('FONT_LANGUAGE_CONFLICT: '+role+' cannot use '+face['family'])


def store_samples(task,state,scene,values):
    from .font_contract import requests
    rows = {r['id']:r for r in requests(scene)}
    target = copy.deepcopy(state.get('font_samples',{}))
    for key, samples in values.items():
        row = rows[key]
        if not 1 <= len(samples) <= policy()['max_glyph_samples']:raise ValueError('Bounded original glyph samples required')
        source_roi=row['roi']
        if state.get('component_workflow'):
            from . import component_workflow as c
            contract,_=c._load(task,state)
            frozen=read_json(c._resource(task,contract['source_scene']))
            source_roi=next(n['bbox'] for n in frozen['objects'] if n['id']==row['owner'])
        ox,oy,ow,oh = source_roi
        for sample in samples:
            text = sample['character']; x,y,w,h = sample['roi']
            if len(text)!=1 or text not in row['characters'] or language(text) != role_language(row['role']):
                raise ValueError('Glyph sample must belong to the exact language request')
            if not (ox <= x and oy <= y and 2 <= w <= 256 and 2 <= h <= 256 and x+w <= ox+ow and y+h <= oy+oh):
                raise ValueError('Original isolated glyph sample escaped its text owner')
        target[key]={'source_hash':state['source']['sha256'],'request_hash':request_key(row),'samples':copy.deepcopy(samples)}
    state['font_samples']=target


def ranking(task,state,request,extend=False):
    """Cheap exact-resource glyph screening; no native page or Office execution."""
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
    from scipy.ndimage import binary_erosion, distance_transform_edt
    choices = eligible(state,request,extend)
    if not choices or len(choices)>policy()['max_ranked_faces']:
        return {'status':'FONT_SELECTION_DECISION_REQUIRED','request_id':request['id'],
            'reason':'NO_ELIGIBLE_LANGUAGE_RESOURCE' if not choices else 'CANDIDATE_BOUND_REACHED',
            'language':role_language(request['role']),'eligible_count':len(choices),
            'style_classes':sorted({f.get('style_class','unknown') for f in choices}),
            'return':'font_constraints{request_id:{style_classes?,resource_ids?,reason,evidence}}; no-resource decisions require current existing eligible resources/configuration, never a language fallback'}
    samples = state.get('font_samples',{}).get(request['id'])
    if not samples or samples['source_hash'] != state['source']['sha256'] or samples['request_hash'] != request_key(request):return None
    if digest(safe_path(task,state['source']['path'])) != state['source']['sha256']:raise ValueError('Original changed')
    input_key=selection_context(state,request,extend)
    cached=Path(task)/'source'/('Font-ranking-input-'+input_key+'.json')
    if cached.is_file():
        ref=read_json(cached)['ranking'];file=safe_path(task,ref['path'])
        if digest(file)!=ref['sha256']:raise ValueError('Immutable font comparison changed')
        state.setdefault('font_rankings',{}).setdefault(request_key(request),{})['extended' if extend else 'initial']=ref
        return ref
    source = Image.open(safe_path(task,state['source']['path'])).convert('RGB')
    def normalize(image):
        pixels = np.asarray(image.convert('RGB'),float)/255
        background = np.median(np.concatenate((pixels[0],pixels[-1],pixels[:,0],pixels[:,-1])),axis=0)
        mask = np.linalg.norm(pixels-background,axis=2) > .2
        yy,xx = np.nonzero(mask)
        if not len(xx):raise ValueError('Original glyph sample has no independently isolated ink')
        crop = Image.fromarray(mask[min(yy):max(yy)+1,min(xx):max(xx)+1].astype('uint8')*255)
        width,height=crop.size
        factor=96/max(width,height)
        crop=crop.resize((max(1,round(width*factor)),max(1,round(height*factor))),Image.Resampling.LANCZOS)
        canvas=Image.new('L',(112,112))
        canvas.paste(crop,((112-crop.width)//2,(112-crop.height)//2))
        return np.asarray(canvas)>127, width/height
    originals=[normalize(source.crop((s['roi'][0],s['roi'][1],s['roi'][0]+s['roi'][2],s['roi'][1]+s['roi'][3]))) for s in samples['samples']]
    results=[]
    for face in choices:
        values=[];font=ImageFont.truetype(face['path'],size=160,index=face['face_index'])
        for sample,(expected,ratio) in zip(samples['samples'],originals):
            bbox=font.getbbox(sample['character']);image=Image.new('RGB',(max(2,bbox[2]-bbox[0]+8),max(2,bbox[3]-bbox[1]+8)),'white')
            ImageDraw.Draw(image).text((4-bbox[0],4-bbox[1]),sample['character'],font=font,fill='black',
                stroke_width=2 if request['bold'] and face['weight']<600 else 0)
            if request['italic'] and not face['italic']:
                expanded=Image.new('RGB',(image.width+math.ceil(image.height*.22),image.height),'white');expanded.paste(image)
                image=expanded.transform(expanded.size,Image.Transform.AFFINE,(1,-.22,image.height*.22,0,1,0),resample=Image.Resampling.BICUBIC,fillcolor='white')
            actual,actual_ratio=normalize(image)
            a=expected & ~binary_erosion(expected);b=actual & ~binary_erosion(actual)
            distance=max(float(distance_transform_edt(~b)[a].mean()),float(distance_transform_edt(~a)[b].mean()))/96
            values.append([distance,float(np.logical_xor(expected,actual).sum()/max(1,np.logical_or(expected,actual).sum())),abs(actual_ratio/ratio-1)])
        merit=[max(v[i] for v in values) for i in range(3)]+[sum(v[1] for v in values)/len(values)]
        results.append({'resource_id':face['id'],'family':face['family'],'merit':merit,'glyphs':values})
    results.sort(key=lambda v:(v['merit'],v['resource_id']))
    if not results:return None
    value={'schema':'language-font-ranking-1','source_hash':state['source']['sha256'],'request_id':request['id'],
           'request_hash':request_key(request),'language':role_language(request['role']),'policy_hash':identity(policy()),
           'collection_revision':load(state['project']).get('revision'),'extended':extend,'samples':samples,'selection_context':input_key,
           'candidates':results,'selected_resource':results[0]['resource_id'],'selected_style':{'font':results[0]['family']},
           'scope':'Normalized isolated glyph shape screening only; fixed size/position and final native appearance remain independent'}
    file=Path(task)/'source'/('Font-ranking-'+identity(value)+'.json');write_json(file,value)
    ref={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
    state.setdefault('font_rankings',{}).setdefault(request_key(request),{})['extended' if extend else 'initial']=ref
    write_json(cached,{'inputs':input_key,'ranking':ref})
    return ref


def verify_choice(task,state,request,face,ref):
    from . import component_workflow as c
    registered=state.get('font_rankings',{}).get(request_key(request),{})
    if ref not in registered.values():raise ValueError('Font ranking must be produced by the normal source-selection program')
    value=read_json(c._resource(Path(task),ref))
    if (value.get('schema')!='language-font-ranking-1' or value.get('request_hash')!=request_key(request) or
        value.get('source_hash')!=state['source']['sha256'] or value.get('language')!=role_language(request['role']) or
        value.get('policy_hash')!=identity(policy()) or value.get('selected_resource')!=face['id']):
        raise ValueError('Select the closest eligible font in the current source-bound language ranking')
    if value.get('selection_context')!=selection_context(state,request,value.get('extended',False)):
        raise ValueError('Font samples, eligible resources or selection implementation changed; request a current comparison')
    return value
