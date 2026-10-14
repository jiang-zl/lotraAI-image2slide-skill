"""Run a fully prevalidated same-task batch using existing finite executors."""
import contextlib
import io
import time
from pathlib import Path
from .common import digest,read_json,safe_path
from .task_transaction import guard
from .execution_context import session
from .batch_plan import ALLOWED,prepare


def run(task,request):
    import sci_rebuild
    if not isinstance(request,dict)or set(request)-{'source_hash','operations'}:
        raise ValueError('Explicit finite same-task batch request required')
    task=Path(task).resolve();results=[]
    with guard(task),session(task):
        from . import agent_runtime as a
        _,state=a._state(task)
        if request.get('source_hash',state['source']['sha256'])!=state['source']['sha256']:
            raise ValueError('Batch original identity changed')
        rows=prepare(task,request)
        for row in rows:
            name=row['id'];previous={r['id']:r for r in results}
            if any(previous[n]['status']!='EXECUTED'or n in row['requires_status']and previous[n].get('domain_status')!=row['requires_status'][n]for n in row['depends_on']):
                results.append({'id':name,'status':'DEPENDENCY_PENDING'});continue
            start=time.monotonic();stdout=io.StringIO();stderr=io.StringIO();error=None
            try:
                if any(not Path(p).is_file()or digest(p)!=h for p,h in row['inputs'].items()):
                    raise ValueError('A prevalidated input changed; replan against the current evidence')
                if row['output']and Path(row['output']).exists():raise ValueError('Batch output became occupied')
                with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
                    code=sci_rebuild.main(row['argv'])
                if code not in (None,0):raise RuntimeError('Operation returned nonzero execution status')
            except (Exception,SystemExit)as exc:error=exc
            log=safe_path(task,'context/batches/'+name+'-'+str(time.time_ns())+'.txt')
            log.parent.mkdir(parents=True,exist_ok=True)
            log.write_text(stdout.getvalue()+'\n'+stderr.getvalue()+('\n'+type(error).__name__+': '+str(error)if error else ''),encoding='utf8')
            from .context_control import register_output
            result={'id':name,'status':'WORK_REQUIRED'if error else 'EXECUTED','seconds':time.monotonic()-start,'log':register_output(task,log)}
            if error:result.update(reason=str(error)[:600],exception=type(error).__name__)
            elif row['output']:
                path=Path(row['output'])
                if not path.is_file():result.update(status='WORK_REQUIRED',reason='Expected program report was not saved')
                else:
                    result['output']=register_output(task,path)
                    try:
                        body=read_json(path)
                        if isinstance(body,dict):
                            result['domain_status']=body.get('status')
                            if type(body.get('passed'))is bool:result['domain_passed']=body['passed']
                    except (OSError,ValueError)as exc:
                        result.update(status='WORK_REQUIRED',reason='Saved report could not be read: '+str(exc)[:400])
            results.append(result)
    return {'schema':'finite-batch-2','status':'EXECUTED'if all(r['status']=='EXECUTED'for r in results)else 'WORK_REQUIRED',
            'prevalidated':len(rows),'operations':results,
            'authority':'Execution success is not quality PASS. Each action retains its existing semantic/protection validators; final independent acceptance remains mandatory.'}
