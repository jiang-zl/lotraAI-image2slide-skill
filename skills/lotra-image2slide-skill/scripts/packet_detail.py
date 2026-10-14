"""Read a hash-bound work-packet section within a fixed context budget."""
import argparse,json
from pathlib import Path
from core.common import safe_path,digest,read_json,canonical

def _select(task,reference,path=(),offset=0,limit=8,max_chars=6000,owner=None):
    if not 0<=offset or not 1<=limit<=32 or not 1000<=max_chars<=16000:raise ValueError('Bounded packet pagination required')
    file=safe_path(task,reference['path'])
    if digest(file)!=reference['sha256']:raise ValueError('Frozen packet detail changed')
    value=read_json(file)
    for key in path:value=value[int(key)] if isinstance(value,list) else value[key]
    if owner is not None:
        if isinstance(value,dict) and owner in value:value=value[owner]
        elif isinstance(value,list):
            matches=[v for v in value if isinstance(v,dict) and any(v.get(k)==owner for k in ('id','object','object_id','target','member'))]
            if len(matches)!=1:raise ValueError('Exactly one frozen owner must match the selector')
            value=matches[0]
        else:raise ValueError('Owner selection requires a named mapping or object list')
    if isinstance(value,list):
        result={'offset':offset,'total':len(value),'items':value[offset:offset+limit]}
        while len(canonical(result).decode('utf-8'))>max_chars-80 and len(result['items'])>1:result['items'].pop()
        result['next_offset']=offset+len(result['items']) if offset+len(result['items'])<len(value) else None
    elif isinstance(value,str):
        length=min(len(value)-min(offset,len(value)),max_chars-500)
        result={'offset':offset,'total':len(value),'text':value[offset:offset+length]}
        while len(canonical(result).decode('utf-8'))>max_chars-80 and length>1:
            length=max(1,length//2);result['text']=value[offset:offset+length]
        result['next_offset']=offset+length if offset+length<len(value) else None
    else:result={'value':value}
    if len(canonical(result).decode('utf-8'))>max_chars:
        keys=list(value) if isinstance(value,dict) else []
        result={'status':'SELECT_CHILD','reference':reference,'path':list(path),
            'keys':keys[offset:offset+limit],'count':len(value) if isinstance(value,(list,dict)) else None,
            'reason':'Select a named child or one list item; all original data remains complete.'}
        while len(canonical(result).decode('utf-8'))>max_chars-80 and len(result['keys'])>1:result['keys'].pop()
        result['next_key_offset']=offset+len(result['keys']) if offset+len(result['keys'])<len(keys) else None
        if len(canonical(result).decode('utf-8'))>max_chars:raise ValueError('Selector identity exceeds the context budget')
        return result
    return result

def select(task,reference,path=(),offset=0,limit=8,max_chars=6000,owner=None,*,managed=False,fresh=False,purpose='current_work'):
    if managed:
        from core.context_control import authorize
        authorize(task,reference)
    result=_select(task,reference,path,offset,limit,max_chars,owner)
    if managed:
        from core.context_control import deliver_read
        result=deliver_read(task,reference,{'path':list(path),'offset':offset,'limit':limit,'max_chars':max_chars,'owner':owner,'purpose':purpose},result,fresh=fresh)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('task',type=Path);p.add_argument('file');p.add_argument('sha256')
    p.add_argument('path',nargs='*');p.add_argument('--offset',type=int,default=0);p.add_argument('--limit',type=int,default=8);p.add_argument('--max-chars',type=int,default=6000)
    p.add_argument('--owner');p.add_argument('--fresh',action='store_true');p.add_argument('--purpose',default='current_work')
    a=p.parse_args();print(json.dumps(select(a.task,{'path':a.file,'sha256':a.sha256},a.path,a.offset,a.limit,a.max_chars,a.owner,managed=(a.task/'state.json').is_file(),fresh=a.fresh,purpose=a.purpose),ensure_ascii=False))
