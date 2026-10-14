"""Optional local OCR source anchors; never semantics, drawing or acceptance.

Uses an available Windows recognizer directly or across WSL, independently of
Office/mouse availability. Otherwise keep visual source understanding available.
No global language/font installation, external upload or new model API key.
"""
from pathlib import Path
from functools import lru_cache
import subprocess
from .common import digest,identity,read_json,write_json,safe_path

def normalized_anchors(anchors,source_hash):
    """One lossless adapter for every actual recognizer output consumer."""
    from .source_contract import finite
    if anchors.get('source_hash')!=source_hash:
        raise ValueError('OCR original-source identity mismatch')
    if anchors.get('status')=='INFERENCE_EXECUTED':
        if any(item.get('image_hash')!=source_hash for item in anchors.get('items',[])):
            raise ValueError('OCR line belongs to another original')
        lines=[line for item in anchors.get('items',[]) for line in item.get('lines',[]) if line.get('roi')]
    elif anchors.get('status')=='SOURCE_OCR_CANDIDATE_ANCHORS':lines=anchors.get('lines',[])
    else:raise ValueError('Actual original-source OCR candidates required')
    finite(lines,'OCR.lines')
    for line in lines:
        if not isinstance(line.get('text'),str) or not isinstance(line.get('words'),list):
            raise ValueError('OCR line schema is incomplete')
    # Overlapping program tiles may recognize the same physical word twice.
    # Remove only same-literal near-identical source boxes; preserve repeated
    # words elsewhere and conflicting hypotheses for the host to resolve.
    unique=[]
    for line in sorted(lines,key=lambda r:-r.get('score',0.)):
        box=line.get('roi')
        def duplicate(old):
            other=old.get('roi')
            if line['text']!=old['text'] or not box or not other:return False
            x,y,w,h=box;a,b,c,d=other
            area=max(0,min(x+w,a+c)-max(x,a))*max(0,min(y+h,b+d)-max(y,b))
            return area/max(w*h+c*d-area,1e-9)>=.8
        if not any(duplicate(old) for old in unique):unique.append(line)
    unique.sort(key=lambda r:((r.get('roi') or [0,0])[1],(r.get('roi') or [0,0])[0]))
    return {**anchors,'status':'SOURCE_OCR_CANDIDATE_ANCHORS','lines':unique}


def source_literal(unit):
    return next((f['literal'] for f in unit.get('features',[]) if f.get('category')=='content'
                 and f.get('status')=='observed' and isinstance(f.get('literal'),str) and f['literal']),None)


@lru_cache(maxsize=32)
def _saved_texts(file,sha256,exclude_math=False):
    """Parse each immutable actual slide once, outside model context."""
    from .inspect import xml,inventory
    nodes,duplicates=inventory(xml(file));result={}
    uri='{http://schemas.openxmlformats.org/drawingml/2006/main}'
    for name,value in nodes.items():
        if name in duplicates:continue
        body=value['node'].find('{http://schemas.openxmlformats.org/presentationml/2006/main}txBody')
        if body is None:continue
        paragraphs=[]
        for paragraph in body.findall(uri+'p'):
            parts=[]
            for item in paragraph:
                if exclude_math and item.find('.//{urn:lotraai:native-math-span:1}span') is not None:continue
                for node in item.iter():
                    if node.tag==uri+'t':parts.append(node.text or '')
                    elif node.tag==uri+'br':parts.append('\n')
            paragraphs.append(''.join(parts))
        result[name]='\n'.join(paragraphs) if paragraphs else None
    return result


def actual_text(task,candidate,unit):
    """Read one independently named plain-text owner from the saved PPTX."""
    if len(unit.get('objects',[]))!=1:return None
    file=safe_path(task,candidate['pptx']['path'])
    if digest(file)!=candidate['pptx']['sha256']:raise ValueError('Saved native text changed')
    if unit.get('protocol',{}).get('table_cell') is not None:
        cell=actual_cell(task,candidate,unit)
        return cell.get('text') if cell else None
    exclude=any(f.get('math_spans') for f in unit.get('features',[]))
    return _saved_texts(str(file),candidate['pptx']['sha256'],exclude).get(unit['objects'][0])


def semantic_measure(task,candidate,unit,state=None):
    from .source_reading import compare_text,confirmed_record
    if state is not None:
        from .office_math_contract import unit_evidence
        math=unit_evidence(task,state,candidate,unit)
        if math is not None:return float(math['passed'])
    expected=source_literal(unit);actual=actual_text(task,candidate,unit)
    reading=confirmed_record(task,state,unit) if state is not None else None
    literals=([expected] if expected is not None else [])+([reading['literal']] if reading else [])
    if not literals or actual is None:return None
    # Missing historical literals may use an independently verified reading.
    # A conflicting historical literal remains a failed predicate until an
    # explicit, source-only correction preserves it in the reading history.
    return float(all(compare_text(text,actual)['passed'] for text in literals))


def collect(task,request=None):
    from .ocr_runtime import descriptor as runtime_descriptor,collect as runtime_collect
    from .agent_runtime import _state as runtime_state
    _,runtime=runtime_state(task)
    if runtime_descriptor(runtime['project']).is_file():return runtime_collect(task,request)
    from .agent_runtime import _state
    from .office_bridge import discover,_host_path
    task,state=_state(task);request=request or {};source=safe_path(task,state['source']['path'])
    if digest(source)!=state['source']['sha256']:raise ValueError('Original source changed')
    capability=discover(request.get('windows'));powershell=Path(capability.get('powershell',''))
    if not capability.get('powershell') or not powershell.is_file():
        return {'status':'LOCAL_OCR_UNAVAILABLE','source_hash':state['source']['sha256'],
                'next':'Use original/enlarged source views to declare natural parts and literal glyphs; local OCR is an accelerator, not a requirement for drawing.'}
    wrapper=Path(__file__).resolve().parent.parent/'ocr_windows.ps1'
    dependencies={'source':state['source']['sha256'],'requested_language':request.get('language',''),
        'fallback_language':request.get('fallback_language'),'provider':str(powershell),'implementation':digest(wrapper)}
    folder=task/'source/ocr'/identity(dependencies)[:24];folder.mkdir(parents=True,exist_ok=True);output=folder/'anchors.json'
    if not output.is_file() or request.get('refresh'):
        spec=folder/'request.json';write_json(spec,{'images':[{'case':task.name,'path':_host_path(source),
            'source_hash':state['source']['sha256'],'language':request.get('language',''),
            'fallback_language':request.get('fallback_language'),'output':_host_path(output)}]})
        result=subprocess.run([str(powershell),'-NoProfile','-ExecutionPolicy','Bypass','-File',_host_path(wrapper),
            '-RequestFile',_host_path(spec)],capture_output=True,timeout=120,encoding='utf-8',errors='replace')
        if result.returncode:
            write_json(folder/'failure.json',{'source_hash':state['source']['sha256'],'exit_code':result.returncode,
                'stderr':result.stderr[-1800:],'limits':'Source OCR unavailable; use source views, preserve this diagnosed failure.'})
            return {'status':'LOCAL_OCR_FAILED','source_hash':state['source']['sha256'],'failure':str(folder/'failure.json')}
    anchors=read_json(output)
    if anchors['source_hash']!=state['source']['sha256']:raise ValueError('OCR original-source binding changed')
    return {'status':anchors['status'],'path':output.relative_to(task).as_posix(),'sha256':digest(output),
        'source_hash':anchors['source_hash'],'language':anchors.get('language'),'word_count':sum(len(l['words']) for l in anchors.get('lines',[])),
        'limits':anchors.get('limits','Recognizer unavailable; use original source views')}


def word_anchors(task,descriptor):
    from .agent_runtime import _state
    import unicodedata,math
    task,state=_state(task);path=safe_path(task,descriptor['path'])
    if digest(path)!=descriptor['sha256']:raise ValueError('Source OCR anchors changed')
    anchors=normalized_anchors(read_json(path),state['source']['sha256'])
    def norm(text):return ''.join(unicodedata.normalize('NFKC',text).split())
    matches=[];unresolved=[]
    selected=state.get('selected') or state.get('active_candidate')
    scene=read_json(safe_path(task,selected['scene']['path'])) if selected else {'objects':[o for b in state.get('built',{}).values() for o in b['objects']]}
    objects={o['id']:o for o in scene['objects']}
    for uid,unit in state['quality']['units'].items():
        if unit['profile']!='text':continue
        content=next((f for f in unit['features'] if f['category']=='content'),{})
        prior=content.get('expected');confirmed_literal=content.get('literal')
        literal=confirmed_literal or prior
        query_origin='confirmed_source_literal' if confirmed_literal else 'frozen_source_property'
        # A known wrong output spelling cannot overwrite an independently read
        # source literal during retrieval. Native text is only a fallback query.
        if not confirmed_literal and len(unit['objects'])==1 and unit['objects'][0] in objects:
            obj=objects[unit['objects'][0]]
            if obj['render_type']=='text':
                payload=obj['content'];plain=payload.get('text')
                if plain is None and not any('ast' in run or 'baseline' in run for para in payload.get('paragraphs',[]) for run in para):
                    plain='\n'.join(''.join(run.get('text','') for run in para) for para in payload.get('paragraphs',[]))
                if plain:
                    # A native literal is only a retrieval query. The original
                    # OCR must independently match it, and the host confirms it.
                    literal=plain;query_origin='native_literal_query_not_source_evidence'
        if not literal or len(norm(literal))<2:continue
        candidates=[]
        for line in anchors['lines']:
            words=line['words']
            for start in range(len(words)):
                text='';owned=[]
                for word in words[start:]:
                    text+=norm(word['text']);owned.append(word)
                    if text==norm(literal):
                        x=min(v['roi'][0] for v in owned);y=min(v['roi'][1] for v in owned)
                        r=max(v['roi'][0]+v['roi'][2] for v in owned);b=max(v['roi'][1]+v['roi'][3] for v in owned)
                        ux,uy,uw,uh=unit['roi'];distance=math.hypot((x+r-2*ux-uw)/2,(y+b-2*uy-uh)/2)
                        if distance<=max(24,uh):candidates.append((distance,[x,y,r-x,b-y],text))
                        break
                    if len(text)>=len(norm(literal)):break
        candidates.sort()
        if not candidates or len(candidates)>1 and candidates[1][0]-candidates[0][0]<8:
            unresolved.append({'unit':uid,'reason':'No unique exact literal source match near its observed component; use enlarged source glyph views.'});continue
        _,roi,text=candidates[0]
        matches.append({'unit':uid,'literal':literal,'prior_source_expected':prior,'query_origin':query_origin,
            'source_word_roi':roi,'old_locator':unit['roi'],
            'source_hash':state['source']['sha256'],'anchor_hash':descriptor['sha256'],
            'status':'ORIGINAL_WORD_LOCATOR_REQUIRES_SOURCE_GUIDE_CONFIRMATION'})
    return {'status':'SOURCE_WORD_LOCATORS_ONLY','matches':matches,'unresolved':unresolved,
        'limits':'Confirm ownership and literal glyphs on original views before a frozen source correction. No automatic acceptance, threshold change or post-render registration.'}


def packet_anchors(task,state,roi):
    """Bounded cached original-word evidence for actual execution packets.

    Recognition is an optional local accelerator. It never replaces the host
    source reading, changes a guide or makes an acceptance claim.
    """
    file=task/'source/ocr-descriptor.json'
    descriptor=read_json(file) if file.is_file() else None
    if not descriptor or descriptor.get('source_hash')!=state['source']['sha256']:
        descriptor=collect(task,{'language':''});write_json(file,descriptor)
    if descriptor.get('status')!='SOURCE_OCR_CANDIDATE_ANCHORS':
        return {'status':descriptor.get('status'),'source_hash':state['source']['sha256'],
                'next':'Read enlarged original glyphs; absent OCR never licenses a generic text oracle.'}
    path=safe_path(task,descriptor['path'])
    if digest(path)!=descriptor['sha256']:raise ValueError('Original OCR anchor cache changed')
    anchors=normalized_anchors(read_json(path),state['source']['sha256']);x,y,w,h=roi;lines=[]
    for line in anchors['lines']:
        words=[v for v in line['words'] if v['roi'][0]<x+w and v['roi'][0]+v['roi'][2]>x
               and v['roi'][1]<y+h and v['roi'][1]+v['roi'][3]>y]
        if words:
            lines.append({'text':' '.join(v['text'] for v in words)[:180],
                          'words':[{'text':v['text'],'roi':v['roi']} for v in words[:8]]})
    return {'status':'ORIGINAL_WORD_LOCATORS_REQUIRES_VISUAL_CONFIRMATION',
            'file':descriptor,'lines':lines[:6],'remaining_lines':max(0,len(lines)-6),
            'limits':'Original-source OCR only; confirm literal/ownership and preserve unresolved math. Native content is a query, never an oracle.'}


def confirmed_word_anchor(task,state,unit,text):
    """Confirm the expanded fit's saved original locator, without new OCR.

    Host visual confirmation is still required; a claimed hash/literal alone
    cannot turn an ambiguous native query into independently located evidence.
    """
    import unicodedata
    norm=lambda v:''.join(unicodedata.normalize('NFKC',v).split())
    anchor=unit.get('source_word_anchor') or {}
    descriptor_file=task/'source/ocr-descriptor.json'
    if (anchor.get('source_hash')!=state['source']['sha256']
            or norm(anchor.get('host_confirmed_literal',''))!=norm(text)
            or not descriptor_file.is_file()):return False
    descriptor=read_json(descriptor_file)
    if (descriptor.get('status')!='SOURCE_OCR_CANDIDATE_ANCHORS'
            or descriptor.get('source_hash')!=state['source']['sha256']
            or descriptor.get('sha256')!=anchor.get('anchor_hash')):return False
    file=safe_path(task,descriptor['path'])
    if digest(file)!=descriptor['sha256']:raise ValueError('Original word anchor evidence changed')
    evidence=normalized_anchors(read_json(file),state['source']['sha256']);roi=anchor.get('word_roi')
    if (evidence.get('source_hash')!=state['source']['sha256']
            or evidence.get('status')!='SOURCE_OCR_CANDIDATE_ANCHORS'
            or not isinstance(roi,list) or len(roi)!=4):return False
    matches=[]
    for line in evidence.get('lines',[]):
        words=line['words']
        for start in range(len(words)):
            literal='';owned=[]
            for word in words[start:]:
                literal+=norm(word['text']);owned.append(word)
                if literal==norm(text):
                    x=min(v['roi'][0] for v in owned);y=min(v['roi'][1] for v in owned)
                    right=max(v['roi'][0]+v['roi'][2] for v in owned)
                    bottom=max(v['roi'][1]+v['roi'][3] for v in owned)
                    box=[x,y,right-x,bottom-y]
                    if max(abs(a-b) for a,b in zip(box,roi))<=.5:matches.append(box)
                    break
                if len(literal)>=len(norm(text)):break
    return len(matches)==1


def prepare_word_revisions(task, request):
    """Compile visually confirmed original locators into guide proposals.

    OCR and native text queries locate evidence; they cannot approve it. The
    host explicitly confirms each original literal/ownership and still
    submits every revision through the existing frozen source-view route.
    """
    import copy, numpy as np
    from PIL import Image
    from . import agent_runtime as a, source_quality as q
    from .common import identity
    task,state=a._state(task)
    if request.get('source_hash')!=state['source']['sha256']:
        raise ValueError('Bind the immutable original source')
    entries=request.get('entries',[])
    if not 1<=len(entries)<=32 or len({v['unit'] for v in entries})!=len(entries):
        raise ValueError('Use a bounded distinct original-word batch')
    original=np.asarray(Image.open(task/state['source']['path']).convert('RGB'))
    revisions={}
    for entry in entries:
        if not entry.get('host_source_confirmation') or not entry.get('literal'):
            raise ValueError('Read the actual original word; no native-query auto-confirmation')
        unit=q.unit(state,entry['unit'])
        if not unit or unit['profile']!='text':raise ValueError('Original plain native word unit required')
        anchor={'source_hash':state['source']['sha256'],'anchor_hash':entry['anchor_hash'],
                'word_roi':entry['word_roi'],'host_confirmed_literal':entry['literal']}
        trial={**unit,'source_word_anchor':anchor}
        if not confirmed_word_anchor(task,state,trial,entry['literal']):
            raise ValueError('Original locator/literal is missing or ambiguous: '+unit['id'])
        owner=unit['owner'];spec=revisions.setdefault(owner,copy.deepcopy(state['quality']['specifications'][owner]))
        part=next(v for v in spec['parts'] if v['id']==unit['part'])
        x,y,w,h=map(round,entry['word_roi']);pad=3
        left=max(0,x-pad);top=max(0,y-pad);right=min(state['source_size'][0],x+w+pad);bottom=min(state['source_size'][1],y+h+pad)
        roi=[left,top,right-left,bottom-top];pixels=original[top:bottom,left:right].astype(float)
        # Source-only light surround, independent of candidate/background.
        lum=pixels.mean(2);light=pixels[lum>=np.percentile(lum,80)]
        bg=np.median(light,axis=0).round().astype(int)
        selector=entry.get('foreground_selector')
        if selector is not None:
            # A coloured panel or white halo is not native glyph ink. Use the
            # already supported typed selector, frozen from original reading,
            # consistently for source ownership and actual candidate pixels.
            if not entry.get('selector_evidence') or selector.get('mode')!='neutral_dark':
                raise ValueError('Original word selector needs explicit neutral-dark evidence')
            for key in ('max_mean_rgb_255','max_chroma_rgb_255'):
                value=selector.get(key)
                if not isinstance(value,(int,float)) or not 0<value<=255:
                    raise ValueError('Source glyph selector requires bounded RGB limits')
            mask=(pixels.mean(2)<selector['max_mean_rgb_255']) & (np.ptp(pixels,axis=2)<selector['max_chroma_rgb_255'])
        else:
            mask=np.linalg.norm(pixels-bg,axis=2)>=.08*255
        owned=np.zeros(mask.shape,bool);owned[y-top:y-top+h,x-left:x-left+w]=True;mask &= owned
        if not mask.any():raise ValueError('Original glyph domain is empty: '+unit['id'])
        directory=task/'source/word-masks';directory.mkdir(exist_ok=True,parents=True)
        file=directory/(identity({'source':state['source']['sha256'],'roi':roi,'mask':mask.tobytes().hex()})+'.png')
        if not file.exists():Image.fromarray(mask.astype('uint8')*255).save(file)
        part['roi']=roi;part['source_word_anchor']=anchor
        part['reference_mask']={'path':file.relative_to(task).as_posix(),'sha256':digest(file)}
        part['protocol']={**part.get('protocol',{}),'background_rgb':bg.tolist(),
                          'candidate_native_text_domain':True,'foreground_mass_scope':'foreground','edge_scope':'owned_foreground'}
        if selector is None:part['protocol'].pop('foreground_selector',None)
        else:part['protocol']['foreground_selector']=copy.deepcopy(selector)
        for feature in part['features']:
            feature['evidence']={'source_hash':state['source']['sha256'],'roi':roi,
                'description':entry['host_source_confirmation']+' Original independently recognized word locator; native content was only a retrieval query.'+((' Original glyph selection: '+entry['selector_evidence']) if selector is not None else '')}
            if feature['category']=='content':
                feature['literal']=entry['literal'];feature['expected']=entry['literal'];feature['status']='observed'
        if entry.get('source_typography'):
            for feature in part['features']:
                if feature['category']=='typography':feature['expected']=entry['source_typography'];feature['status']='observed'
    return {'status':'SOURCE_GUIDE_REVISION_PROPOSALS_NOT_DRAWING_GAINS','source_hash':state['source']['sha256'],
            'revisions':[{'owner':owner,'prior_spec_hash':identity(state['quality']['specifications'][owner]),
                          'specification':spec} for owner,spec in revisions.items()],
            'limits':'Confirm against original source views, then use source_correction; all bounds/prior units/history are retained. No native file is modified.'}


@lru_cache(maxsize=32)
def _saved_cells(file,sha256):
    """Actual immutable table cell text and directly specified native formatting."""
    from lxml import etree as E
    from .inspect import xml,inventory
    from .mathml import NS
    nodes,duplicates=inventory(xml(file));result={}
    for name,record in nodes.items():
        if name in duplicates:continue
        # A group's descendant table belongs to its graphicFrame owner.
        # Counting it again for every ancestor invents duplicate cell duties.
        if E.QName(record['node']).localname!='graphicFrame':continue
        table=record['node'].find('a:graphic/a:graphicData/a:tbl',NS)
        if table is None:continue
        grid=[]
        for row in table.findall('a:tr',NS):
            cells=[]
            for cell in row.findall('a:tc',NS):
                props=cell.find('a:tcPr',NS);body=cell.find('a:txBody',NS)
                paragraphs=[];formats=[]
                for p in body.findall('a:p',NS) if body is not None else []:
                    paragraphs.append(''.join(n.text or '' for n in p.findall('.//a:t',NS)))
                    ppr=p.find('a:pPr',NS);default=ppr.find('a:defRPr',NS) if ppr is not None else None
                    bold=[]
                    for run in p.findall('a:r',NS):
                        rpr=run.find('a:rPr',NS);weight=rpr.get('b') if rpr is not None else None
                        if weight is None:weight=default.get('b') if default is not None else None
                        bold.append(weight=='1' if weight is not None else None)
                    if not bold and default is not None:bold=[default.get('b')=='1']
                    formats.append({'align':{'l':'left','ctr':'center','r':'right'}.get(ppr.get('algn','l') if ppr is not None else 'l'),
                        'bold':bold[0] if bold and all(v==bold[0] for v in bold) else None})
                cell_format={'valign':{'t':'top','ctr':'middle','b':'bottom'}.get(props.get('anchor','t') if props is not None else 't')}
                for key in ('align','bold'):
                    values=[f[key] for f in formats];cell_format[key]=values[0] if values and all(v==values[0] for v in values) else None
                cells.append({'text':'\n'.join(paragraphs),'format':cell_format})
            grid.append(cells)
        result[name]=grid
    return result


def actual_cell(task,candidate,unit):
    if len(unit.get('objects',[]))!=1:return None
    selected=unit.get('protocol',{}).get('table_cell')
    if not isinstance(selected,dict) or set(selected)!={'row','column'} or any(type(selected[k]) is not int or selected[k]<0 for k in selected):
        raise ValueError('Native table cell needs exact nonnegative row and column')
    file=safe_path(task,candidate['pptx']['path'])
    if digest(file)!=candidate['pptx']['sha256']:raise ValueError('Saved native table changed')
    rows=_saved_cells(str(file),candidate['pptx']['sha256']).get(unit['objects'][0])
    if rows is None or selected['row']>=len(rows) or selected['column']>=len(rows[selected['row']]):return None
    return rows[selected['row']][selected['column']]


def cell_format_measure(task,candidate,unit):
    expected=next((f['cell_format'] for f in unit.get('features',[]) if f.get('category')=='typography' and f.get('status')=='observed' and f.get('cell_format')),None)
    actual=actual_cell(task,candidate,unit)
    if expected is None or actual is None:return None
    if set(expected)-{'align','valign','bold'}:raise ValueError('Cell format measure supports explicit source alignment and weight')
    if any(actual['format'].get(k) is None for k in expected):return None
    return float(all(actual['format'][k]==v for k,v in expected.items()))
