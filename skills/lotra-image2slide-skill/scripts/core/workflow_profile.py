"""Current-task command timings; nested inclusive times are never summed."""
import contextlib
import sqlite3
import sys
import time
import uuid
from contextvars import ContextVar
from pathlib import Path
from .common import digest

_spans=ContextVar('lotra_command_spans',default=())


@contextlib.contextmanager
def command_span(task,command,operation=None):
    parents=_spans.get();span={'id':uuid.uuid4().hex,'children':0.0}
    token=_spans.set((*parents,span));start=time.monotonic();created=time.time()
    try:yield
    finally:
        elapsed=time.monotonic()-start;error=sys.exc_info()[0]
        _spans.reset(token)
        if parents:parents[-1]['children']+=elapsed
        task=Path(task)if task else None
        if task and (task/'state.json').is_file():
            from .context_control import event
            detail={'schema':'command-span-1','span_id':span['id'],
                    'parent_span':parents[-1]['id']if parents else None,
                    'operation':operation,'started':created,'finished':time.time(),
                    'inclusive_seconds':elapsed,'exclusive_seconds':max(0.,elapsed-span['children']),
                    'outcome':'raised'if error else 'returned','exception':error.__name__ if error else None,
                    'implementation':digest(__file__),
                    'scope':'Recorded command only; model/host delay and provider usage are separate or unknown.'}
            try:event(task,'command_span',command,seconds=elapsed,detail=detail)
            except (OSError,ValueError,sqlite3.Error)as exc:
                print('WORKFLOW_TELEMETRY_UNAVAILABLE: '+type(exc).__name__,file=sys.stderr)


def report(task,request):
    import json
    from .context_control import index
    limit=request.get('limit',16);offset=request.get('offset',0)
    if type(limit)is not int or not 1<=limit<=64 or type(offset)is not int or offset<0:
        raise ValueError('Bounded profile pagination required')
    with index(task)as db:
        total=db.execute("SELECT COUNT(*) n FROM events WHERE stage='command_span'").fetchone()['n']
        rows=db.execute("SELECT id,operation,detail,created FROM events WHERE stage='command_span' ORDER BY id LIMIT ? OFFSET ?",(limit,offset)).fetchall()
        groups=db.execute("SELECT operation,COUNT(*) calls,SUM(seconds) inclusive_seconds FROM events WHERE stage='command_span' GROUP BY operation ORDER BY operation").fetchall()
        exclusive={};root_seconds=0.;unknown=0
        for row in db.execute("SELECT operation,detail FROM events WHERE stage='command_span'"):
            value=json.loads(row['detail'])
            if value.get('schema')!='command-span-1':unknown+=1;continue
            exclusive[row['operation']]=exclusive.get(row['operation'],0.)+value['exclusive_seconds']
            if value.get('parent_span')is None:root_seconds+=value['inclusive_seconds']
        legacy=db.execute("SELECT COUNT(*) n FROM events WHERE stage='command'").fetchone()['n']
        resource_counts={};fact_scopes=0;independent_scopes=0
        for row in db.execute("SELECT operation,detail FROM events WHERE stage='runtime' AND operation IN ('shared_facts','independent_facts')"):
            value=json.loads(row['detail']);counts=value.get('resources')
            if not isinstance(counts,dict):continue
            fact_scopes+=1;independent_scopes+=int(row['operation']=='independent_facts')
            for name,count in counts.items():
                if type(count) is int and count>=0:resource_counts[name]=resource_counts.get(name,0)+count
    return {'schema':'workflow-profile-1','status':'MEASURED'if total else 'NO_INSTRUMENTED_COMMANDS',
            'total':total,'offset':offset,'count':len(rows),'next_offset':offset+len(rows)if offset+len(rows)<total else None,
            'spans':[{'event_id':r['id'],'command':r['operation'],**json.loads(r['detail'])}for r in rows],
            'commands':[{**dict(r),'exclusive_seconds':exclusive.get(r['operation'])}for r in groups],
            'recorded_root_command_seconds':root_seconds,'legacy_inclusive_only_count':legacy,'unknown_span_count':unknown,
            'resource_counts':resource_counts,'completed_fact_scopes':fact_scopes,'independent_fact_scopes':independent_scopes,
            'whole_task_elapsed_seconds':None,'model_seconds':None,'service_token_savings':None,
            'limits':'Recorded current-task spans only. Do not add runtime/inclusive ledgers or infer end-to-end speedup/provider tokens.'}
