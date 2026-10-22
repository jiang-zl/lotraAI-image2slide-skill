"""Avoid repeated identical validation failures without closing the task."""
import copy
from functools import wraps
from pathlib import Path
from .common import canonical, digest, identity, read_json, write_json, safe_path
from .context_control import index, register_output


def checked_submit(function):
    @wraps(function)
    def execute(task,result):
        from . import agent_runtime as a
        task,state=a._state(task)
        proposal={k:v for k,v in result.items() if k!='packet_id'}
        decision={k:v for k,v in state.items() if k not in ('packet','telemetry','updated','actions')}
        packet=state.get('packet') or {}
        dependency={'source':state['source']['sha256'],'state':identity(decision),
                    'proposal':proposal,'kind':packet.get('kind'),'owner':packet.get('target'),
                    'code':digest(function.__globals__['__file__']), 'retry_code':digest(__file__)}
        if state.get('objectives',{}).get('component_first'):
            from .component_workflow import implementation
            dependency['component_implementation']=implementation()
        key=identity(dependency)
        with index(task) as db:
            previous=db.execute("SELECT * FROM attempts WHERE key=? AND status='invalid'",(key,)).fetchone()
        if previous:
            ref=__import__('json').loads(previous['evidence'])
            file=safe_path(task,ref['path'])
            if digest(file)!=ref['sha256']:raise ValueError('Stored retry evidence changed')
            evidence=read_json(file)
            if evidence.get('key')!=key or evidence.get('dependencies')!=dependency:
                raise ValueError('Stored retry validation evidence changed')
            raise ValueError(previous['reason']+' [identical invalid proposal retained; change the proposal or its actual dependencies]')
        try:return function(task,result)
        except ValueError as error:
            # Transports, host readiness and concurrency use separate recovery.
            # State-changing partial actions cannot be safely deduplicated.
            current=read_json(Path(task)/'state.json')
            current_decision={k:v for k,v in current.items() if k not in ('packet','telemetry','updated','actions')}
            if identity(current_decision)!=identity(decision):raise
            if any(word in str(error).lower() for word in ('busy','host','capabilit','font environment','transport','edited the baseline')):raise
            file=safe_path(task,'context/errors/'+key+'.json')
            write_json(file,{'key':key,'dependencies':dependency,'reason':str(error),
                             'scope':'Failed validation only; no acceptance or obligation closure'})
            ref=register_output(task,file)
            with index(task) as db:
                db.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?,?,?)',
                           (key,'invalid',canonical(dependency).decode(),canonical(ref).decode(),str(error)))
            raise
    return execute
