"""Provider-reported token accounting is separate from context size."""
import copy
from pathlib import Path
from .common import read_json,write_json,identity,digest,safe_path,writer

VERSION='provider-usage-ledger-1'
FIELDS=('input_tokens','cached_input_tokens','cache_write_tokens','output_tokens','reasoning_tokens','total_tokens')

def extract(document,path):
    value=document
    for key in path:value=value[int(key)] if isinstance(value,list) else value[key]
    if not isinstance(value,dict):raise ValueError('Usage evidence must select a provider object')
    def number(item):
        if item is None:return None
        if type(item) is not int or item<0:raise ValueError('Reported token counts must be nonnegative integers')
        return item
    result={k:number(value.get(k)) for k in ('input_tokens','output_tokens','total_tokens')}
    input_details=value.get('input_tokens_details') or {};output_details=value.get('output_tokens_details') or {}
    if not isinstance(input_details,dict) or not isinstance(output_details,dict):raise ValueError('Provider token details must be objects')
    result['cached_input_tokens']=number(value.get('cached_input_tokens',input_details.get('cached_tokens')))
    result['cache_write_tokens']=number(value.get('cache_write_tokens',input_details.get('cache_write_tokens')))
    result['reasoning_tokens']=number(value.get('reasoning_tokens',output_details.get('reasoning_tokens')))
    if not any(v is not None for v in result.values()):raise ValueError('No provider token observations present')
    for parent,child in (('input_tokens','cached_input_tokens'),('output_tokens','reasoning_tokens')):
        if result[parent] is not None and result[child] is not None and result[child]>result[parent]:raise ValueError('Token subset exceeds its reported total')
    if all(result[k] is not None for k in ('input_tokens','output_tokens','total_tokens')) and result['input_tokens']+result['output_tokens']!=result['total_tokens']:
        raise ValueError('Provider token totals disagree')
    return result

def record(task,state,request):
    task=Path(task).resolve()
    ref=request['evidence'];file=safe_path(task,ref['path'])
    if file.stat().st_size>8*1024*1024 or digest(file)!=ref['sha256']:raise ValueError('Changed/oversized provider usage evidence')
    document=read_json(file);path=request.get('usage_path',['usage'])
    if not isinstance(path,list) or not all(isinstance(k,(str,int)) and not isinstance(k,bool) for k in path):raise ValueError('Explicit provider JSON usage locator required')
    counts=extract(document,path)
    call_id=document.get('id') if isinstance(document,dict) else None
    key=identity({'provider_call_id':call_id}) if call_id else identity({'evidence_hash':ref['sha256'],'usage_path':path})
    frozen=safe_path(task,'audits/usage/evidence/'+ref['sha256']+'.json')
    if frozen.exists() and digest(frozen)!=ref['sha256']:raise ValueError('Stored provider evidence changed')
    frozen.parent.mkdir(parents=True,exist_ok=True)
    if not frozen.exists():frozen.write_bytes(file.read_bytes())
    item={'id':key,'provider_call_id':call_id,'model':document.get('model') if isinstance(document,dict) else None,
        'evidence':{'path':frozen.relative_to(task).as_posix(),'sha256':digest(frozen)},'usage_path':path,'counts':counts,
        'basis':'provider_reported_from_hash_bound_evidence','stage':request.get('stage',state.get('stage')),'operation':request.get('operation'),'scope':request.get('scope','task_call')} 
    if state.get('usage_ledger'):report(task,state) # Verify existing immutable evidence before extending its ledger.
    ledger=read_json(safe_path(task,state['usage_ledger']['path'])) if state.get('usage_ledger') else {'schema':VERSION,'calls':[]}
    old=next((r for r in ledger['calls'] if r['id']==key),None)
    if old is not None:
        if any(old['counts'].get(k)!=counts.get(k) for k in old['counts']) or old['model']!=item['model']:raise ValueError('A provider call cannot be counted twice with changed usage/model')
    else:ledger['calls'].append(item)
    target=safe_path(task,'audits/usage/Ledger.json');write_json(target,ledger)
    state['usage_ledger']={'path':target.relative_to(task).as_posix(),'sha256':digest(target)}
    return report(task,state)

def report(task,state):
    task=Path(task).resolve()
    calls=[]
    if state.get('usage_ledger'):
        ref=state['usage_ledger'];file=safe_path(task,ref['path'])
        if digest(file)!=ref['sha256']:raise ValueError('Token ledger changed')
        ledger=read_json(file)
        if ledger.get('schema')!=VERSION or len({r['id'] for r in ledger['calls']})!=len(ledger['calls']):raise ValueError('Invalid provider usage ledger')
        for row in ledger['calls']:
            evidence=safe_path(task,row['evidence']['path'])
            if digest(evidence)!=row['evidence']['sha256'] or any(extract(read_json(evidence),row['usage_path']).get(k)!=v for k,v in row['counts'].items()):
                raise ValueError('Reported usage no longer matches immutable provider evidence')
        calls=[{**r,'counts':extract(read_json(safe_path(task,r['evidence']['path'])),r['usage_path'])} for r in ledger['calls']]
    totals={}
    for field in FIELDS:
        known=[r['counts'][field] for r in calls if r['counts'][field] is not None]
        complete=bool(calls) and len(known)==len(calls)
        totals[field]={'value':sum(known) if complete else None,'known_sum':sum(known) if known else None,
            'observed_calls':len(known),'complete':complete}
    telemetry=copy.deepcopy(state.get('telemetry',{}))
    if telemetry.get('context_schema')!='context-storage-1':
        telemetry['legacy_packet_bytes']=telemetry.pop('packet_chars',0)
        telemetry['packet_chars']=None;telemetry['packet_bytes']=None
    return {'schema':VERSION,'reported_calls':len(calls),'token_usage':totals,'context':telemetry,
        'status':'PROVIDER_USAGE_RECORDED' if calls else 'PROVIDER_USAGE_UNAVAILABLE',
        'scope':'Service-reported calls only; characters/bytes/cache hits are separate and no token savings are inferred',
        'attribution':[{'id':r['id'],'stage':r.get('stage'),'operation':r.get('operation'),'scope':r.get('scope','legacy_unattributed'),'counts':r['counts']} for r in calls]}

def dispatch(task,operation,request=None):
    from . import agent_runtime as a
    task,state=a._state(task)
    if operation=='status':return report(task,state)
    if operation!='record' or not request:raise ValueError('Usage record needs actual provider evidence')
    with writer(task):
        result=record(task,state,request);a._save(task,state)
    return result
