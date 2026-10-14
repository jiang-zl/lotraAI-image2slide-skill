"""Independent source transcriptions and deterministic saved-content checks."""
import copy, math, re, unicodedata
from pathlib import Path
from .common import digest,identity,read_json,write_json,safe_path,writer

VERSION='source-reading-1'

def normalized(text):
    text=unicodedata.normalize('NFC',text)
    # A line wrap within CJK prose is layout, not an inserted word boundary.
    # Horizontal spaces remain significant and English word breaks stay spaces.
    text=re.sub(r'([\u3400-\u9fff，。；：！？、）])[^\S\r\n]*\r?\n[^\S\r\n]*(?=[\u3400-\u9fff])',r'\1',text)
    return ' '.join(text.split())

def edit_distance(first,second):
    if len(first)>len(second):first,second=second,first
    previous=list(range(len(first)+1))
    for i,char in enumerate(second,1):
        row=[i]
        for j,other in enumerate(first,1):
            row.append(min(row[-1]+1,previous[j]+1,previous[j-1]+(char!=other)))
        previous=row
    return previous[-1]

def compare_text(expected,actual,pattern=None):
    if not isinstance(expected,str) or not isinstance(actual,str):
        return {'status':'UNMEASURED','passed':False,'exact':None,'normalized_exact':None}
    left,right=normalized(expected),normalized(actual);distance=edit_distance(left,right)
    regex=None
    if pattern is not None:
        if not isinstance(pattern,str) or len(pattern)>512 or len(actual)>8192:
            raise ValueError('Use a bounded source-declared regex, never generated executable code')
        # This diagnostic does not grant acceptance and excludes nested repeats.
        if re.search(r'\([^)]*[+*][^)]*\)[+*{]',pattern):raise ValueError('Nested regex repeats are unsupported')
        regex=bool(re.fullmatch(pattern,right))
    return {'status':'MEASURED','passed':left==right,'exact':expected==actual,'normalized_exact':left==right,
        'edit_distance':distance,'character_error_rate':distance/max(1,len(left)),
        'similarity':max(0.,1-distance/max(1,len(left),len(right))),'regex_match':regex,
        'source_text':expected,'native_text':actual,
        'normalization':'NFC, whitespace folding and CJK soft line wraps only; preserve case, punctuation, digits and English word separation'}

def semantic_ast(value):
    """Office italic letters and mathematical digits; preserve AST and alphabets."""
    from .mathml import canonical_ast
    def convert(item):
        if isinstance(item,dict):return {k:convert(v) for k,v in item.items()}
        if isinstance(item,list):return [convert(v) for v in item]
        if isinstance(item,str):
            return ''.join(unicodedata.normalize('NFKC',c) if unicodedata.name(c,'').startswith('MATHEMATICAL ITALIC ') or 0x1D7CE<=ord(c)<=0x1D7FF
                else ' ' if c=='\u00a0' else c for c in item)
        return item
    return canonical_ast(convert(value))

def formatted_owners(task,candidate):
    """Native non-math scripts require independent source run evidence."""
    if not candidate:return set()
    from .inspect import xml,inventory
    from .mathml import NS
    file=safe_path(task,candidate['pptx']['path'])
    if digest(file)!=candidate['pptx']['sha256']:raise ValueError('Native content inventory changed')
    nodes,_=inventory(xml(file));result=set()
    for name,row in nodes.items():
        body=row['node'].find('p:txBody',NS)
        if body is None:continue
        for run in body.findall('.//a:r',NS):
            props=run.find('a:rPr',NS)
            if props is not None and int(props.get('baseline',0)) and props.find('.//{urn:lotraai:native-math-span:1}span') is None:
                result.add(name)
    return result


def discover(task,state):
    from PIL import Image
    source=safe_path(task,state['source']['path'])
    if digest(source)!=state['source']['sha256']:raise ValueError('Original image changed')
    units={k:v for k,v in state.get('quality',{}).get('units',{}).items() if v['profile'] in ('text','formula')}
    candidate=state.get('active_candidate') or state.get('selected')
    formats=formatted_owners(task,candidate)
    rows=[];folder=task/'source/reading-views';folder.mkdir(parents=True,exist_ok=True)
    with Image.open(source) as original:
        for uid,u in units.items():
            x,y,w,h=u['roi'];padding=12
            box=(max(0,math.floor(x-padding)),max(0,math.floor(y-padding)),min(original.width,math.ceil(x+w+padding)),min(original.height,math.ceil(y+h+padding)))
            if box[0]>=box[2] or box[1]>=box[3]:raise ValueError('Source text has no visible original domain: '+uid)
            roi=[box[0],box[1],box[2]-box[0],box[3]-box[1]]
            key=identity({'source':state['source'],'unit':uid,'roi':roi,'scale':4})
            path=folder/(key+'.png');crop=original.crop(box).convert('RGB')
            if not path.exists():crop.resize((crop.width*4,crop.height*4),Image.Resampling.LANCZOS).save(path)
            rows.append({'unit':uid,'kind':u['profile'],'objects':u.get('objects',[]),
                'needs_formatted_runs':u['profile']=='text' and any(n in formats for n in u.get('objects',[])), 'view':{
                'path':path.relative_to(task).as_posix(),'sha256':digest(path),'source_hash':state['source']['sha256'],
                'roi':roi,'scale':4},'instruction':'Read original only; do not copy the candidate, old literal or OCR hypothesis as ground truth.'})
    unbound=native_obligations(task,state,candidate) if candidate else []
    result={'schema':VERSION,'source_hash':state['source']['sha256'],'items':rows,'unbound_native_content':unbound}
    path=folder/'index.json';write_json(path,result)
    return result

def native_obligations(task,state,candidate):
    """Derive missing text/cell/math obligations from the saved whole slide."""
    from .inspect import xml,inventory
    from .mathml import NS
    from .source_ocr import _saved_cells
    file=safe_path(task,candidate['pptx']['path'])
    if digest(file)!=candidate['pptx']['sha256']:raise ValueError('Native content inventory changed')
    nodes,duplicates=inventory(xml(file));units=state.get('quality',{}).get('units',{});missing=[]
    from .office_math_contract import load as mathematical_inventory
    original_math=mathematical_inventory(task,state)
    classified={r['object']:r for r in (original_math or {}).get('owners',[])}
    bound={u['objects'][0]:u for u in units.values() if u['profile'] in ('text','formula')
        and len(u.get('objects',[]))==1 and u.get('protocol',{}).get('table_cell') is None}
    for name,row in nodes.items():
        body=row['node'].find('p:txBody',NS)
        if body is None:continue
        text=''.join(t.text or '' for t in body.findall('.//a:t',NS));math_count=len(body.findall('.//m:oMath',NS))
        math_count+=len({r.get('index') for r in body.findall('.//{urn:lotraai:native-math-span:1}span')})
        if not text and not math_count:continue
        unit=bound.get(name)
        if unit is None or name in duplicates:
            missing.append({'object':name,'kind':'formula' if math_count else 'text','reason':'NATIVE_CONTENT_HAS_NO_INDEPENDENT_SOURCE_UNIT'})
        elif math_count and unit['profile']=='text' and not any(f.get('math_spans') for f in unit['features']) and not any('ast' in s for p in classified.get(name,{}).get('paragraphs',[]) for s in p):
            missing.append({'object':name,'unit':unit['id'],'kind':'formula','reason':'INLINE_MATH_SPANS_HAVE_NO_SOURCE_AST'})
    cells=_saved_cells(str(file),candidate['pptx']['sha256'])
    cell_units={(u['objects'][0],(u['protocol']['table_cell']['row'],u['protocol']['table_cell']['column'])) for u in units.values()
        if u['profile'] in ('text','formula') and len(u.get('objects',[]))==1 and isinstance(u.get('protocol',{}).get('table_cell'),dict)}
    for name,grid in cells.items():
        for r,row in enumerate(grid):
            for c,cell in enumerate(row):
                if cell['text'] and (name,(r,c)) not in cell_units:
                    missing.append({'object':name,'table_cell':[r,c],'kind':'text','reason':'NATIVE_TABLE_CELL_HAS_NO_INDEPENDENT_SOURCE_UNIT'})
    return missing

def validate_view(task,state,view,known):
    if view!=known or view.get('source_hash')!=state['source']['sha256'] or digest(safe_path(task,view['path']))!=view['sha256']:
        raise ValueError('Reading must use the exact program-generated original-only view')

def confirmed_record(task,state,unit):
    ledger=state.get('source_readings',{});row=ledger.get('records',{}).get(unit['id'])
    if row is None:return None
    if (ledger.get('source_hash')!=state['source']['sha256'] or row.get('unit')!=unit['id']
            or row.get('status')!='confirmed' or row.get('method') not in ('host_vision','local_ocr_confirmed','user_transcription')
            or not row.get('evidence') or row.get('confidence') is not None):
        raise ValueError('Current independent source reading identity is invalid')
    known=next((r for r in discover(task,state)['items'] if r['unit']==unit['id']),None)
    if known is None:raise ValueError('The original reading unit no longer exists')
    validate_view(task,state,row['view'],known['view'])
    return row

def bind(task,request):
    from . import agent_runtime as a
    task,state=a._state(task);index=discover(task,state);known={r['unit']:r for r in index['items']}
    if request.get('source_hash')!=state['source']['sha256']:raise ValueError('Source reading identity mismatch')
    entries=request.get('items',[])
    if not entries or len({r.get('unit') for r in entries})!=len(entries):raise ValueError('Unique source readings required')
    reading=copy.deepcopy(state.get('source_readings',{'schema':VERSION,'records':{},'history':[]}))
    for row in entries:
        uid=row.get('unit')
        if uid not in known or row.get('method') not in ('host_vision','local_ocr_confirmed','user_transcription'):
            raise ValueError('Use a current named text/formula and a truthful reading method')
        validate_view(task,state,row['view'],known[uid]['view'])
        if not row.get('evidence') or row.get('confidence') is not None:
            raise ValueError('Describe source evidence; do not invent confidence for host vision')
        if row.get('status')!='confirmed':raise ValueError('Uncertain source tokens need another source-only reading before binding')
        if known[uid]['kind']=='text' and not isinstance(row.get('literal'),str):raise ValueError('Text reading needs literal characters')
        if known[uid].get('needs_formatted_runs') and 'formatted_runs' not in row:
            raise ValueError('Read original sub/superscript runs independently; a matching flattened literal is insufficient')
        if 'formatted_runs' in row:
            from .source_text_actions import runs
            runs(row['formatted_runs'])
            if ''.join(r['text'] for r in row['formatted_runs'])!=row['literal']:
                raise ValueError('Source formatted runs must preserve the exact independent literal')
        if known[uid]['kind']=='formula':
            from .mathml import math_node
            math_node(row['ast'])
        old=reading['records'].get(uid)
        if old and old!=row:reading['history'].append({'unit':uid,'previous':old,'replacement':copy.deepcopy(row)})
        reading['records'][uid]=copy.deepcopy(row)
    reading['source_hash']=state['source']['sha256']
    with writer(task):
        state['source_readings']=reading;state.pop('acceptance',None);state.pop('quality_result',None)
        a._event(task,'independent_source_readings_bound',{'units':[r['unit'] for r in entries],'source_hash':request['source_hash'],'drawing_gain':False})
        a._save(task,state)
    return {'status':'SOURCE_READINGS_BOUND','bound':len(reading['records']),'required':len(known),
            'missing':sorted(set(known)-set(reading['records']))}

def report(task,state,candidate):
    from .source_ocr import actual_text
    from .source_math import actual_ast
    index=discover(task,state);known={r['unit']:r for r in index['items']};bound=state.get('source_readings',{}).get('records',{})
    rows=[]
    for uid,item in known.items():
        unit=state['quality']['units'][uid];reading=bound.get(uid)
        row={'unit':uid,'kind':item['kind'],'objects':unit.get('objects',[]),'passed':False,'status':'SOURCE_READING_REQUIRED'}
        from .office_math_contract import unit_evidence
        structured=unit_evidence(task,state,candidate,unit)
        if structured is not None:
            row.update(structured,legacy_source_reading=copy.deepcopy(reading),
                       transition='Historical literal/formatted-run evidence retained; current original reading and actual structured equation use ordered prose/AST comparison')
            rows.append(row);continue
        if reading:
            validate_view(task,state,reading['view'],item['view'])
            if item['kind']=='text':
                row.update(compare_text(reading['literal'],actual_text(task,candidate,unit),reading.get('regex')))
                if item.get('needs_formatted_runs') and 'formatted_runs' not in reading:
                    row.update(passed=False,status='SOURCE_FORMATTED_READING_REQUIRED')
                if 'formatted_runs' in reading:
                    from .inspect import xml,inventory
                    from .mathml import NS
                    nodes,duplicates=inventory(xml(safe_path(task,candidate['pptx']['path'])));name=unit['objects'][0]
                    values=[]
                    for native in nodes[name]['node'].findall('p:txBody/a:p/a:r',NS):
                        props=native.find('a:rPr',NS);text=native.find('a:t',NS)
                        values.append({'text':text.text or '' if text is not None else '',
                            'baseline':int(props.get('baseline',0)) if props is not None else 0,
                            'size':int(props.get('sz',0)) if props is not None else 0,
                            'italic':props.get('i','0') in ('1','true') if props is not None else False})
                    expected=reading['formatted_runs'];base=values[0]['size'] if values else 0
                    matched=len(values)==len(expected) and base>0 and all(v['text']==e['text'] and v['baseline']==e.get('baseline',0)
                        and ('italic' not in e or v['italic']==e['italic']) and abs(v['size']-round(base*e.get('font_scale',1.)))<=1 for v,e in zip(values,expected))
                    row['native_formatted_runs']=values;row['formatted_runs_match']=matched;row['passed']&=matched
            else:
                actual=actual_ast(task,candidate,unit);expected=reading['ast']
                row.update(status='MEASURED' if actual is not None else 'UNMEASURED',
                    passed=actual is not None and semantic_ast(expected)==semantic_ast(actual),
                    raw_ast_equal=expected==actual,source_ast=expected,native_ast=actual,
                    representation_rule='Mathematical Italic letter and NBSP encoding only; all operators, scripts, case and style flags retained')
                if actual is None:
                    from .source_math import native_run_evidence
                    native=native_run_evidence(task,candidate,unit,expected)
                    if native is not None:row.update(passed=False,status='MATH_REPRESENTATION_FAILED',native_run_evidence=native)
            if 'math_spans' in reading:
                from .source_math import span_evidence
                evidence=span_evidence(task,candidate,unit,reading['math_spans'])
                row['native_math_span_evidence']=evidence;row['expected_math_span_count']=len(reading['math_spans'])
                row['native_math_span_count']=evidence['count'] if evidence else None
                row['math_spans_match']=bool(evidence and evidence['passed'])
                row['passed']=row['passed'] and row['math_spans_match']
            row['source_evidence']=reading['view'];row['reading_method']=reading['method']
        rows.append(row)
    for missing in native_obligations(task,state,candidate):
        rows.append({'unit':'native-content:'+missing['object']+(':'+str(missing['table_cell']) if 'table_cell' in missing else ''),
            'objects':[missing['object']],'kind':missing['kind'],'passed':False,'status':'SOURCE_BINDING_REQUIRED',**missing})
    return {'schema':VERSION,'source_hash':state['source']['sha256'],'pptx_hash':candidate['pptx']['sha256'],
        'items':rows,'passed':all(r['passed'] for r in rows),'applicability':'APPLICABLE' if rows else 'NO_SAVED_TEXT_OR_FORMULA',
        'text_count':sum(r['kind']=='text' for r in rows),'formula_count':sum(r['kind']=='formula' for r in rows)}
