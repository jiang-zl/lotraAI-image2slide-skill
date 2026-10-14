"""Serialize official operations on one task with portable process locks."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from .session import _lock

_owned=ContextVar('lotra_task_transactions',default=())

class TaskBusy(RuntimeError):
    pass

@contextmanager
def guard(task):
    task=Path(task).resolve()
    if not task.is_dir():raise ValueError('Existing task directory required for a transaction')
    key=str(task)
    if key in _owned.get():
        yield
        return
    with __import__('contextlib').ExitStack() as stack:
        try:stack.enter_context(_lock(task/'.runtime.lock'))
        except BlockingIOError as error:
            raise TaskBusy('TASK_BUSY: another program operation owns this task; wait for that command to finish and retry the current packet') from error
        token=_owned.set((*_owned.get(),key))
        try:yield
        finally:_owned.reset(token)

def transaction(function):
    @wraps(function)
    def execute(task,*args,**kwargs):
        with guard(task):return function(task,*args,**kwargs)
    return execute
