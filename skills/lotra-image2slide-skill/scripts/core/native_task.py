"""Per-document Office probes generated from actual saved math and semantic objects."""
import copy
import base64
import gzip
import io
import subprocess
import unicodedata
from pathlib import Path
from lxml import etree as E
from .common import ROOT,digest,identity,read_json,write_json
from .inspect import xml,inventory,parse_math_container,NS
from .mathml import linear_math,canonical_ast,encoded_math_letter
from . import VERSION
MAX_BEFORE_RENDER_BYTES=128*1024*1024


def verify_pdf_preview(pdf,preview,width,height):
    """Replay the shared fixed-canvas PDF kernel without invalidating capture producers."""
    import tempfile
    from PIL import Image,ImageChops
    from .render import rasterize_pdf
    with tempfile.TemporaryDirectory(prefix='lotraai-pdf-replay-') as folder:
        rasterize_pdf(pdf,folder,width,1,height)
        with Image.open(Path(folder)/'Final_preview.png') as expected,Image.open(preview) as observed:
            if observed.size!=(width,height) or ImageChops.difference(expected.convert('RGB'),observed.convert('RGB')).getbbox():
                raise ValueError('Preview pixels differ from the bound actual PDF on the fixed canvas')
    return True


def verify_emf_preview(emf,preview,width,height):
    """Replay the actual Office EMF through the same declared Windows GDI codec."""
    import tempfile,platform
    from PIL import Image,ImageChops
    from .office_bridge import discover,_host_path
    from .office import decode_native_output
    capability=discover()
    if not capability.get('available'):raise ValueError('Actual Windows native EMF pixel replay is unavailable on this caller')
    with tempfile.TemporaryDirectory(prefix='lotraai-emf-replay-') as folder:
        output=Path(folder)/'pixels'
        command=[capability['powershell'],'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',_host_path(ROOT/'scripts/native_task_probe.ps1'),
            '-DecodeNativeEmf','-InputPptx',_host_path(emf),'-OutDir',_host_path(output),'-PreviewWidth',str(width),'-PreviewHeight',str(height)]
        process=subprocess.run(command,capture_output=True,stdin=subprocess.DEVNULL,timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system()=='Windows' else 0)
        if process.returncode:raise ValueError('Actual native EMF replay failed: '+decode_native_output(process.stderr))
        with Image.open(output/'Final_preview.png') as expected,Image.open(preview) as observed:
            if observed.size!=(width,height) or ImageChops.difference(expected.convert('RGB'),observed.convert('RGB')).getbbox():
                raise ValueError('Preview pixels differ from the hash-bound actual Office EMF')
    return True


def complete_render(plan_file,office_directory):
    """Reuse saved actual Office PDF when its direct PNG exporter failed."""
    import shutil
    from .render import rasterize_pdf
    plan_=read_json(plan_file);directory=Path(office_directory);raw=read_json(directory/'operations.json')
    height=round(plan_['preview_width']*plan_['canvas']['height']/plan_['canvas']['width'])
    rows=[]
    for prefix,pdf,preview in [('before',directory/'before/Final.pdf',directory/'before/Final_preview.png'),('after',directory/'After.pdf',directory/'After.png')]:
        if prefix=='after' and raw.get('after_owner_renders'):
            if not owner_render_coverage(plan_,raw['after_owner_renders']):raise ValueError('Owner-only actual render has incomplete or inapplicable edit coverage')
            rows.append({'stage':'after','route':'PowerPoint_edited_text_math_owners_EMF_Windows_GDI','owners':raw['after_owner_renders'],
                'scope':'Every actually edited text/math owner only; full-slide PNG/PDF/EMF exports failed and remain failed. This does not verify geometric edits or full-slide after-layout.'});continue
        if raw.get(prefix+'_png_sha256'):
            if digest(preview)!=raw[prefix+'_png_sha256']:raise ValueError('Actual Office PNG changed')
            rows.append({'stage':prefix,'route':'PowerPoint_verified_cached_input_render' if prefix=='before' and plan_.get('verified_before_render') else 'PowerPoint_direct_PNG','preview_hash':digest(preview)});continue
        if raw.get(prefix+'_emf_sha256'):
            emf=directory/('before/Actual.emf' if prefix=='before' else 'After.emf')
            if digest(emf)!=raw[prefix+'_emf_sha256'] or digest(preview)!=raw.get(prefix+'_emf_preview_sha256'):
                raise ValueError('Actual native EMF/preview changed')
            rows.append({'stage':prefix,'route':'PowerPoint_native_EMF_Windows_GDI','emf_hash':digest(emf),'preview_hash':digest(preview),
                'direct_PNG_status':'FAILED','PDF_status':'FAILED','scope':'Actual PowerPoint native metafile rendered on fixed canvas by Windows GDI; not direct PNG/PDF export'});continue
        if not raw.get(prefix+'_pdf_sha256') or digest(pdf)!=raw[prefix+'_pdf_sha256']:
            raise ValueError('Actual preview requires a hash-bound saved Office PDF, never another presentation renderer')
        derived=directory/('pdf-preview-'+prefix);rasterize_pdf(pdf,derived,plan_['preview_width'],1,height)
        failed=None
        if preview.exists() and digest(preview)!=digest(derived/'Final_preview.png'):
            failed=preview.with_name('Direct-PNG-failed-'+digest(preview)[:16]+'.png')
            if failed.exists():raise ValueError('Preserve conflicting failed direct PNG evidence')
            preview.rename(failed)
        if not preview.exists():shutil.copyfile(derived/'Final_preview.png',preview)
        rows.append({'stage':prefix,'route':'PowerPoint_saved_PDF_rasterized','pdf_hash':digest(pdf),'preview_hash':digest(preview),
            'direct_PNG_status':'FAILED','failed_direct_PNG':{'path':str(failed.relative_to(directory)),'sha256':digest(failed)} if failed else None,
            'scope':'Actual PowerPoint PDF layout; not direct PowerPoint PNG export'})
    receipt={'status':'VERIFIED_RENDER_INPUTS','plan_hash':digest(plan_file),'operations_hash':digest(directory/'operations.json'),'rows':rows}
    write_json(directory/'Native-render.json',receipt)
    return receipt


def owner_render_coverage(plan_,rows):
    actions=plan_.get('actions',[])
    if not actions or any(a['action'] not in ('text','math') for a in actions):return False
    wanted={name:[i for i,a in enumerate(actions) if a['id']==name] for name in {a['id'] for a in actions}}
    actual={r.get('object'):r.get('operation_indices') for r in rows}
    return len(actual)==len(rows) and actual==wanted


def verify_render(plan_,raw,stage,directory):
    height=round(plan_['preview_width']*plan_['canvas']['height']/plan_['canvas']['width'])
    for prefix,pdf_name,preview_name in [('before','before/Final.pdf','before/Final_preview.png'),('after','After.pdf','After.png')]:
        preview=directory/preview_name
        if prefix=='after' and raw.get('after_owner_renders'):
            from .common import safe_path
            from PIL import Image,ImageChops
            if not owner_render_coverage(plan_,raw['after_owner_renders']):return False
            for owner in raw['after_owner_renders']:
                emf=safe_path(directory,owner['emf']);pixels=safe_path(directory,owner['preview']);width,height=owner['canvas_px']
                if (digest(emf)!=owner['emf_sha256'] or digest(safe_path(stage/'result',owner['emf']))!=digest(emf)
                    or digest(pixels)!=owner['preview_sha256'] or digest(safe_path(stage/'result',owner['preview']))!=digest(pixels)):return False
                verify_emf_preview(emf,pixels,width,height)
                with Image.open(pixels) as image:
                    if image.size!=(width,height) or not ImageChops.difference(image.convert('RGB'),Image.new('RGB',image.size,'white')).getbbox():return False
            continue
        if raw.get(prefix+'_png_sha256'):
            if digest(preview)!=raw[prefix+'_png_sha256'] or digest(stage/'result'/preview_name)!=digest(preview):return False
        elif raw.get(prefix+'_emf_sha256'):
            name='before/Actual.emf' if prefix=='before' else 'After.emf';emf=directory/name
            if (digest(emf)!=raw[prefix+'_emf_sha256'] or digest(stage/'result'/name)!=digest(emf)
                or digest(preview)!=raw.get(prefix+'_emf_preview_sha256') or digest(stage/'result'/preview_name)!=digest(preview)):return False
            verify_emf_preview(emf,preview,plan_['preview_width'],height)
        else:
            pdf=directory/pdf_name
            if (not raw.get(prefix+'_pdf_sha256') or digest(pdf)!=raw[prefix+'_pdf_sha256']
                or digest(stage/'result'/pdf_name)!=digest(pdf)):return False
            verify_pdf_preview(pdf,preview,plan_['preview_width'],height)
    if plan_.get('verified_before_render'):
        import tempfile
        from .native_capture_batch import verify_actual_render
        with tempfile.TemporaryDirectory(prefix='lotraai-before-render-') as folder:
            unpack_before_render(plan_['verified_before_render'],Path(folder))
            verify_actual_render(stage/'Input.pptx',Path(folder)/'render.json')
    return True


def unpack_before_render(cache,directory):
    names={'Final.pdf','Final_preview.png','render.json','job-receipt.json','office-session.json'}
    if set(cache.get('files',{}))!=names:raise ValueError('Complete current actual Office before-render evidence required')
    total=0
    for name,row in cache['files'].items():
        encoded=base64.b64decode(row['base64'],validate=True)
        if row.get('encoding')=='gzip_base64':
            with gzip.GzipFile(fileobj=io.BytesIO(encoded)) as source:data=source.read(MAX_BEFORE_RENDER_BYTES-total+1)
        elif row.get('encoding','base64')=='base64':data=encoded
        else:raise ValueError('Unsupported actual render cache encoding')
        total+=len(data)
        import hashlib
        if total>MAX_BEFORE_RENDER_BYTES or hashlib.sha256(data).hexdigest()!=row['sha256'] or row.get('size_bytes',len(data))!=len(data):
            raise ValueError('Changed or oversized actual before-render cache')
        Path(directory,name).write_bytes(data)


def bind_before_render(pptx,receipt):
    """Reuse only an unchanged, independently verified actual PowerPoint render."""
    from .native_capture_batch import verify_actual_render
    receipt=Path(receipt);verify_actual_render(pptx,receipt)
    row=read_json(receipt)
    if row['backend']!='PowerPoint':raise ValueError('Native equation probe needs actual Office before-render evidence')
    files={};total=0
    for name in ('Final.pdf','Final_preview.png','render.json','job-receipt.json','office-session.json'):
        file=receipt.parent/name;total+=file.stat().st_size
        if total>MAX_BEFORE_RENDER_BYTES:raise ValueError('Actual before-render cache exceeds its declared resource bound before Office execution')
        data=file.read_bytes();files[name]={'sha256':digest(file),'size_bytes':len(data),'encoding':'gzip_base64','base64':base64.b64encode(gzip.compress(data,mtime=0)).decode('ascii')}
    return {'pptx_hash':digest(pptx),'files':files,'canvas':row['pages'][0]['canvas'] if 'canvas' in row['pages'][0] else None,
        'scope':'Previously saved actual PowerPoint render of exactly these unchanged input bytes; not a fresh before-render operation'}


def canonical_math(value):
    """Compare saved mathematical structure, preserving operands and script scope.

    Office turns literal paired fences into delimiter objects and combines the
    sub/sup on the same base. These are presentation changes; attaching an index
    to a different variable is not. Do not use a flattened text comparison.
    """
    if isinstance(value,str):
        return ''.join(unicodedata.normalize('NFKC',c) if c=='ℎ' or 0x1D400<=ord(c)<=0x1D49B or 0x1D6E2<=ord(c)<=0x1D71B or 0x1D7CE<=ord(c)<=0x1D7FF else c for c in value).replace('−','-').replace('∗','*').replace('\u00a0',' ')
    if isinstance(value,list):return [canonical_math(v) for v in value]
    if not isinstance(value,dict):return value
    value={k:canonical_math(v) for k,v in value.items()}
    value=canonical_ast(value)
    if value.get('op')=='token' and value.get('normal') and all(encoded_math_letter(c) for c in value['text']):
        # Encoded calligraphic letters retain their exact codepoints. Quoting
        # them as normal UnicodeMath text would incorrectly collapse 𝒢 to G.
        value.pop('normal',None)
    if value.get('op') in ('sub','sup'):
        base=value['base'];other='sup' if value['op']=='sub' else 'sub'
        if base.get('op')==other:
            value={'op':'scripts','base':base['base'],value['op']:value[value['op']],other:base[other]}
    if value.get('op') in ('token','seq','delimited'):
        return _canonical_fences(value)
    return value


def _canonical_fences(value):
    pairs={'(':')','[':']','{':'}'};closers=set(pairs.values())
    def token(text):return {'op':'token','text':text}
    def pack(items):
        merged=[]
        for item in items:
            if item.get('op')=='token' and not item['text']:continue
            if (merged and item.get('op')=='token' and merged[-1].get('op')=='token'
                    and bool(item.get('normal'))==bool(merged[-1].get('normal'))):
                merged[-1]=dict(merged[-1],text=merged[-1]['text']+item['text'])
            else:merged.append(item)
        return merged[0] if len(merged)==1 else {'op':'seq','items':merged}
    def parts(item):
        op=item.get('op')
        if op=='seq':
            return [part for child in item['items'] for part in parts(child)]
        if op=='delimited':
            return [token(item['left']),*parts(item['body']),token(item['right'])]
        if op=='token' and not item.get('normal'):
            return [token(c) for c in item['text']]
        return [item]
    result=[];stack=[]
    for item in parts(value):
        postfix=None
        if item.get('op') in ('sub','sup','scripts') and item['base'].get('op')=='token' and item['base']['text'] in closers:
            postfix=item;char=item['base']['text']
        else:char=item.get('text') if item.get('op')=='token' and not item.get('normal') else None
        if char in pairs:
            stack.append((char,result));result=[]
        elif char in closers and stack and pairs[stack[-1][0]]==char:
            left,outer=stack.pop()
            fenced={'op':'delimited','left':left,'right':char,'body':pack(result)}
            outer.append(dict(postfix,base=fenced) if postfix else fenced);result=outer
        else:result.append(item)
    while stack:
        left,outer=stack.pop();result=[*outer,token(left),*result]
    return pack(result)


def altered(ast):
    out=copy.deepcopy(ast)
    changed=False
    def visit(value):
        nonlocal changed
        if changed:return
        if isinstance(value,dict):
            if value.get('op')=='token':
                text=value['text']
                for i,c in enumerate(text):
                    if c.isalpha():
                        value['text']=text[:i]+('z' if c!='z' else 'q')+text[i+1:];changed=True;return
            for v in value.values():visit(v)
        elif isinstance(value,list):
            for v in value:visit(v)
    visit(out)
    if not changed:
        def operator(value):
            nonlocal changed
            if changed:return
            if isinstance(value,dict):
                if value.get('op')=='token' and value.get('text'):
                    text=value['text'];value['text']='∏' if text in ('∑','Σ') else '∑' if text=='∏' else ('1' if text[0]=='0' else '0')+text[1:];changed=True;return
                for v in value.values():operator(v)
            elif isinstance(value,list):
                for v in value:operator(v)
        operator(out)
    if not changed:raise ValueError('No editable token in math probe expression')
    return out

def atom_change(before,after):
    if isinstance(before,dict) and isinstance(after,dict):
        if before.get('op')=='token' and before.get('text')!=after.get('text'):
            for index,(old,new) in enumerate(zip(before['text'],after['text'])):
                if old!=new:return old,new,index
        for key,value in before.items():
            if key in after:
                result=atom_change(value,after[key])
                if result:return result
    if isinstance(before,list) and isinstance(after,list):
        for old,new in zip(before,after):
            result=atom_change(old,new)
            if result:return result
    return None


def plan_saved_equations(pptx,output,before_render=None):
    """Inspect all actual saved equation zones without a historical author Scene.

    The projection is an inspection index, not an inferred reconstruction or
    source-semantic certificate. It targets every OMML zone plus one text edit.
    Other edit capabilities require their own component/attachment probes.
    """
    from zipfile import ZipFile
    nodes,_=inventory(xml(pptx))
    with ZipFile(pptx) as package:
        size=E.fromstring(package.read('ppt/presentation.xml')).find('p:sldSz',NS)
        width,height=int(size.get('cx')),int(size.get('cy'))
    objects=[]
    for name,item in nodes.items():
        n=item['node'];body=n.find('p:txBody',NS)
        if body is None and n.find('.//a:tbl',NS) is not None:body=n
        if body is None:continue
        math_zones=body.xpath('.//m:oMath',namespaces=NS)
        text_runs=body.xpath('.//a:p/a:r/a:t/text() | .//a:p/a:fld/a:t/text()',namespaces=NS)
        if not math_zones and not text_runs:continue
        objects.append({'id':name,'render_type':'equation' if math_zones and not any(t.strip() for t in text_runs) else 'text',
                        'parent':item['parent'],'bbox':[0,0,1,1],'content':{},'style':{}})
    projected={'canvas':{'width':1000,'height':round(1000*height/width),'unit':'px','target_width_inches':width/914400},
               'objects':objects,'relations':[],'prototypes':[]}
    result=plan(projected,pptx,output)
    result['source_mode']='saved-equation-inspection-projection'
    result['scope']='All actual first-slide saved OMML equation zones and one native text operation; not semantic, connector or whole-document edit acceptance'
    result['saved_equation_zones']=sum(a['action']=='math' for a in result['actions'])
    if before_render:
        result['verified_before_render']=bind_before_render(pptx,before_render)
        from PIL import Image
        with Image.open(Path(before_render).parent/'Final_preview.png') as image:result['preview_width']=image.width
    write_json(output,result)
    return result


def plan(scene,pptx,output):
    nodes,_=inventory(xml(pptx));actions=[];plain_text_planned=False
    def path_to(id):
        result=[id];parent=nodes[id]['parent']
        while parent:result.insert(0,parent);parent=nodes[parent]['parent']
        return result
    for obj in scene['objects']:
        id=obj['id'];n=nodes[id]['node'];kind=obj['render_type']
        if kind in ('text','equation'):
            offset=1;existing_offset=1;zone_index=0;linear_parts=[];zone_actions=[]
            body=n.find('p:txBody',NS)
            contexts=[(None,body)] if body is not None else [([ri,ci],cell.find('a:txBody',NS)) for ri,row in enumerate(n.findall('.//a:tbl/a:tr',NS)) for ci,cell in enumerate(row.findall('a:tc',NS))]
            paragraphs=[(cell,p,pi,len(owner.findall('a:p',NS))) for cell,owner in contexts if owner is not None for pi,p in enumerate(owner.findall('a:p',NS))]
            prior_cell=None;preceding_math=''
            for cell,p,p_index,p_count in paragraphs:
                if cell!=prior_cell:offset=1;existing_offset=1;prior_cell=cell;preceding_math=''
                for child in p:
                    tag=child.tag.rsplit('}',1)[-1]
                    if child.tag=='{'+NS['a14']+'}m':
                        math=child.find('m:oMath',NS)
                        if math is None:math=child.find('m:oMathPara/m:oMath',NS)
                        ast=parse_math_container(math);new=altered(ast)
                        change=atom_change(ast,new)
                        if change is None:raise ValueError('No bounded single-token mathematical edit')
                        old_atom,new_atom,atom_index=change
                        normal=lambda s:unicodedata.normalize('NFKC',s)
                        occurrence=normal(preceding_math).count(normal(old_atom))+1
                        linear=linear_math(canonical_math(new))
                        length=len(linear.encode('utf-16-le'))//2
                        zone_actions.append({'id':id,'action':'math','zone_index':zone_index,'offset':offset,'linear':linear,'table_cell':cell,
                            'selection_length':length,'expected_ast':new,'before_ast':ast,'whole_shape':kind=='equation',
                            'existing_offset':existing_offset,'existing_length':sum(len(t.text or '') for t in math.findall('.//m:t',NS)),
                            'atom_edit':{'before':old_atom,'after':new_atom,'occurrence':occurrence}})
                        preceding_math+=''.join(t.text or '' for t in math.findall('.//m:t',NS))
                        linear_parts.append(linear);offset+=length;zone_index+=1
                        for run in math.findall('.//m:r',NS):
                            plain=''.join(t.text or '' for t in run.findall('m:t',NS));normal=run.find('m:rPr/m:nor',NS) is not None
                            existing_offset+=sum(2 if c.isascii() and c.isalpha() and not normal else len(c.encode('utf-16-le'))//2 for c in plain)
                    elif tag in ('r','fld'):
                        text=''.join(child.xpath('.//a:t/text()',namespaces=NS));linear_parts.append(text);offset+=len(text.encode('utf-16-le'))//2;existing_offset+=len(text.encode('utf-16-le'))//2
                    elif tag=='br':linear_parts.append('\v');offset+=1;existing_offset+=1
                if p_index<p_count-1:linear_parts.append('\r');offset+=1;existing_offset+=1
            if zone_actions:
                # TextRange2 does not expose a stable one-character OMML span.
                # Stage the complete task-copy text once and build zones from
                # right to left, so conversion cannot shift a remaining range.
                zone_actions.reverse()
                if kind=='text':
                    # Edit existing inline native fields in-place. Replacing
                    # the whole paragraph can absorb trailing ordinary prose.
                    for row in zone_actions:
                        row['existing_math']=True;row['offset']=row['existing_offset'];row.pop('selection_length',None)
                else:zone_actions[0]['initialize_text']=''.join(linear_parts)
                actions.extend(zone_actions)
            if kind=='text' and body is not None and zone_index==0 and (obj.get('probe_text',False) or not plain_text_planned):
                actions.append({'id':id,'action':'text','text':'Native editing verified'})
                plain_text_planned=True
        if kind=='group' and obj.get('component',False):actions.append({'id':id,'action':'group'})
        if kind=='trace':actions.append({'id':id,'action':'path','native_id':id+'.tone-0'})
    # One movement per referenced node proves applicable anchoring without repeated whole-deck work.
    moved=set()
    for obj in scene['objects']:
        c=obj['content']
        if obj['render_type']=='connector':
            for side in ('source','target'):
                source=c.get(side+'_anchor_object',c.get(side))
                if source and c.get(side+'_anchor',True) and source not in moved:
                    actions.append({'id':obj['id'],'action':'connector','node_id':source,'anchor_id':source,'moving_side':side})
                    moved.add(source)
    for action in actions:
        action['shape_path']=path_to(action['id'])
        if action.get('node_id'):action['node_path']=path_to(action['node_id'])
        if action.get('native_id'):
            action['native_path']=path_to(action['native_id'])
            action['native_geometry_hash']=identity(E.tostring(nodes[action['native_id']]['node'].find('p:spPr/a:custGeom',NS)).decode())
    from .measure import measure
    measured=measure(scene,pptx)
    from .session import implementation_identity
    lookup_leaves={}
    for id,entry in nodes.items():
        if E.QName(entry['node']).localname!='grpSp':
            lookup_leaves[id]=id
            parent=entry['parent']
            while parent:
                lookup_leaves.setdefault(parent,id);parent=nodes[parent]['parent']
    from .office_math_contract import _segments
    protected_prose={name:{'paragraphs':[''.join(s.get('text','') for s in p) for p in _segments(row['node'])],
        'math_count':len(row['node'].findall('.//m:oMath',NS))} for name,row in nodes.items()
        if E.QName(row['node']).localname!='grpSp' and row['node'].find('.//m:oMath',NS) is not None}
    result={'implementation_version':VERSION,'implementation':implementation_identity(),'probe_script_hash':digest(ROOT/'scripts/native_task_probe.ps1'),
            'scene_hash':identity(scene),'pptx_hash':digest(pptx),'actions':actions,'preview_width':scene['canvas']['width'],
            'canvas':scene['canvas'],'objects':scene['objects'],'relations':scene['relations'],'prototypes':scene['prototypes'],'lookup_leaves':lookup_leaves,
            'protected_prose':protected_prose,'initial_connections':{o['id']:measured['objects'][o['id']] for o in scene['objects'] if o['render_type']=='connector'},
            'initial_rigid_paths':{o['id']:measured['objects'][o['id']] for o in scene['objects'] if o['content'].get('attachment_contract',{}).get('kind')=='rigid_parent'},
            'scope':'temporary-copy native editor operations on this input; no edits to original file'}
    write_json(output,result);return result


def verify(plan_file,office_dir,output):
    plan_=read_json(plan_file);office_dir=Path(office_dir);raw=read_json(office_dir/'operations.json')
    deck=office_dir/'Native_test_copy.pptx';nodes,_=inventory(xml(deck));checks=[]
    operations={r['operation_index']:r for r in raw.get('operations',[])}
    from .measure import measure
    after=measure({'canvas':plan_['canvas'],'objects':plan_['objects']},deck)['objects']
    objects={o['id']:o for o in plan_['objects']}
    moved={a['node_id'] for i,a in enumerate(plan_['actions']) if a['action']=='connector' and operations.get(i,{}).get('status')=='EXECUTED'}
    def shift(anchor):
        count=0
        while anchor:
            count+=anchor in moved;anchor=objects.get(anchor,{}).get('parent')
        return count*5/(plan_['canvas']['target_width_inches']*72/plan_['canvas']['width'])
    for index,action in enumerate(plan_['actions']):
        op=operations.get(index,{});ok=op.get('status')=='EXECUTED';detail=op
        if action['action']=='math':
            n=nodes[action['id']]['node']
            zones=n.xpath('.//a:p/a14:m/m:oMath | .//a:p/a14:m/m:oMathPara/m:oMath',namespaces=NS)
            try:
                actual=canonical_math(parse_math_container(zones[action['zone_index']]))
                wanted=canonical_math(action['expected_ast']);ok=ok and actual==wanted
                detail={'actual_ast':actual,'expected_ast':wanted,'raw_operation':op}
            except (IndexError,ValueError,AttributeError,TypeError) as exc:ok=False;detail={'error':str(exc),'raw_operation':op}
        elif action['action']=='connector':
            d=op.get('detail',{});side=action.get('moving_side','source');saved_source=after.get(action['id'],{}).get('anchors',{}).get(side)
            anchor_identity=bool(saved_source) and saved_source.get('object_id')==action['anchor_id']
            ok=ok and d.get('before')!=d.get('after') and d.get('begin_connected' if side=='source' else 'end_connected')==-1 and anchor_identity and d.get(side) in (None,action['anchor_id'])
            c=objects[action['id']]['content'];initial=plan_['initial_connections'][action['id']].get('endpoints');actual=after.get(action['id'],{}).get('endpoints')
            expected=[]
            if initial:
                for i,which in enumerate(('source','target')):
                    delta=shift(c.get(which+'_anchor_object',c.get(which))) if c.get(which) and c.get(which+'_anchor',True) else 0
                    expected.append([initial[i][0]+delta,initial[i][1]])
            error=max((abs(a-b) for p,q in zip(actual or [],expected) for a,b in zip(p,q)),default=float('inf'))
            ok=ok and error<.1
            detail={'raw_operation':op,'saved_source_anchor':saved_source,'expected_endpoints_px':expected,'actual_endpoints_px':actual,'max_endpoint_error_px':error if error!=float('inf') else None}
        elif action['action']=='group':
            d=op.get('detail',{});part=nodes.get(d.get('edited_part'),{}).get('node')
            path='p:spPr/a:ln/a:solidFill/a:srgbClr' if d.get('edited_property')=='line' else 'p:spPr/a:solidFill/a:srgbClr'
            color=part.find(path,NS) if part is not None else None
            ok=ok and d.get('part_count',0)>0 and d.get('part_fill_changed') is True and color is not None and color.get('val')==d.get('expected_rgb')
            detail={'raw_operation':op,'saved_style_color':color.get('val') if color is not None else None}
        elif action['action']=='text':
            n=nodes[action['id']]['node'];actual=''.join(n.xpath('.//a:t/text()',namespaces=NS));ok=ok and actual==action['text']
        elif action['action']=='path':
            n=nodes.get(action['native_id'],{}).get('node');detail=op.get('detail',{})
            ok=ok and n is not None and n.find('p:spPr/a:custGeom',NS) is not None and detail.get('node_count',0)>2 and detail.get('before')!=detail.get('after')
            if ok:
                saved_hash=identity(E.tostring(n.find('p:spPr/a:custGeom',NS)).decode())
                ok=bool(action.get('native_geometry_hash')) and saved_hash!=action['native_geometry_hash']
                detail=dict(detail,saved_geometry_changed=ok,saved_geometry_hash=saved_hash)
        checks.append({'object_id':action['id'],'action':action['action'],'status':'PASS' if ok else 'FAIL','detail':detail})
    # A node can feed several connectors. One movement must check every branch,
    # including branches which were not themselves selected by the probe.
    for id, initial in plan_['initial_connections'].items():
        c=objects[id]['content'];expected=[];affected=False
        for i,which in enumerate(('source','target')):
            anchor=c.get(which+'_anchor_object',c.get(which))
            delta=shift(anchor) if anchor and c.get(which+'_anchor',True) else shift(objects[id].get('parent'))
            affected=affected or bool(delta)
            if initial.get('endpoints'):expected.append([initial['endpoints'][i][0]+delta,initial['endpoints'][i][1]])
        if not affected:continue
        actual=after.get(id,{});endpoints=actual.get('endpoints')
        error=max((abs(a-b) for p,q in zip(endpoints or [],expected) for a,b in zip(p,q)),default=float('inf'))
        anchors_ok=actual.get('anchors')==initial.get('anchors')
        ok=len(expected)==2 and endpoints is not None and error<.1 and anchors_ok
        checks.append({'object_id':id,'action':'all_affected_endpoints','status':'PASS' if ok else 'FAIL',
                       'detail':{'expected_endpoints_px':expected,'actual_endpoints_px':endpoints,'anchors_preserved':anchors_ok,
                                 'max_endpoint_error_px':error if error!=float('inf') else None}})
    for id,initial in plan_.get('initial_rigid_paths',{}).items():
        delta=shift(objects[id].get('parent'));points=initial.get('route_points');actual=after.get(id,{}).get('route_points')
        expected=[[x+delta,y] for x,y in points] if points else []
        error=max((abs(a-b) for p,q in zip(actual or [],expected) for a,b in zip(p,q)),default=float('inf'))
        ok=bool(delta) and len(expected)>1 and actual is not None and len(actual)==len(expected) and error<.1
        checks.append({'object_id':id,'action':'rigid_parent_path','status':'PASS' if ok else 'FAIL',
                       'detail':{'expected_points_px':expected,'actual_points_px':actual,'parent_delta_px':delta,
                                 'max_point_error_px':error if error!=float('inf') else None}})
    from .office_math_contract import _segments
    for name,before in plan_.get('protected_prose',{}).items():
        node=nodes.get(name,{}).get('node');segments=_segments(node) if node is not None else []
        actual={'paragraphs':[''.join(s.get('text','') for s in p) for p in segments], 'math_count':len(node.findall('.//m:oMath',NS)) if node is not None else 0}
        checks.append({'object_id':name,'action':'math_prose_and_zone_protection','status':'PASS' if actual==before else 'FAIL','detail':{'before':before,'after':actual}})
    from .session import implementation_identity
    current_implementation=(plan_.get('implementation')==implementation_identity()
        and plan_.get('implementation_version')==VERSION and plan_.get('probe_script_hash')==digest(ROOT/'scripts/native_task_probe.ps1'))
    bound=(current_implementation
        and raw.get('input_sha256')==plan_['pptx_hash'] and raw.get('output_sha256')==digest(deck) and raw.get('probe_script_hash')==plan_.get('probe_script_hash'))
    job_ok=False;job_reason=None
    try:
        from .office_bridge import _local_path
        job=read_json(office_dir/'job-receipt.json');stage=_local_path(job['staging_directory'])
        execution=read_json(stage/'execute-status.json')
        job_ok=(job['kind']=='native' and job['status']=='COMPLETED_REQUIRES_RESULT_REVIEW' and execution['status']=='COMPLETED'
            and job['input_pptx_hash']==plan_['pptx_hash'] and job['wrapper_hash']==digest(ROOT/'scripts/run_office_job.ps1')
            and digest(stage/'native_task_probe.ps1')==plan_['probe_script_hash'] and digest(stage/'Input.pptx')==plan_['pptx_hash']
            and digest(stage/'result/Native_test_copy.pptx')==digest(deck)
            and digest(stage/'result/operations.json')==digest(office_dir/'operations.json')
            and verify_render(plan_,raw,stage,office_dir))
    except (ValueError,KeyError,OSError,subprocess.SubprocessError) as exc:job_reason=str(exc)
    bound=bound and job_ok
    result={'status':'PASS' if bound and checks and all(c['status']=='PASS' for c in checks) else 'FAIL',
            'checker_version':'task-native-1.0.0','checker_hash':digest(Path(__file__)),'ancestor_ungroups':raw.get('ancestor_ungroups',[]),
            'implementation_version':VERSION,'implementation':plan_.get('implementation'),'probe_script_hash':raw.get('probe_script_hash'),
            'plan_hash':digest(plan_file),
            'source_pptx_hash':plan_['pptx_hash'],'scene_hash':plan_['scene_hash'],
            'edited_pptx_hash':digest(deck),'operations_hash':digest(office_dir/'operations.json'),
            'current_implementation_verified':current_implementation,
            'actual_host_job_verified':job_ok,'actual_host_job_error':job_reason,
            'actual_render_scope':'Every actually edited text/math owner individually; full after-slide export failed' if raw.get('after_owner_renders') else 'Whole before/after slide',
            'full_after_slide_render_verified':bool(job_ok and not raw.get('after_owner_renders')),
            'office_version':raw.get('office_version'),'office_build':raw.get('office_build'),'checks':checks,
            'scope':'listed operations on an isolated copy only; original content/visual QA remains separate'}
    write_json(output,result);return result
