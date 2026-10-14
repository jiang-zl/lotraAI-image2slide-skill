"""One command shares raw facts; each checker owns its independent predicate.

Every lookup freshly hashes the actual artifact. Mutating callers receive
isolated copies. An independent final audit starts a new fact scope.
"""
import contextlib
import copy
import time
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from .common import canonical, digest, identity

_active = ContextVar('lotra_execution_facts', default=None)


@contextlib.contextmanager
def session(task=None, *, independent=False):
    previous = _active.get()
    same_task = previous is not None and (task is None or previous['task'] is not None and Path(task).resolve() == previous['task'].resolve())
    if same_task and not independent:
        yield previous
        return
    scope = {'native': {}, 'hits': 0, 'misses': 0,
             'task': Path(task) if task else None, 'independent': independent}
    from .context_policy import image_budget
    scope['image_budget']=image_budget()
    if task and (Path(task) / 'state.json').is_file():
        from .common import read_json
        from .context_control import library_scope
        state = read_json(Path(task) / 'state.json')
        scope['library_scope'] = library_scope(state)
        scope['project'] = state['project']
    from .resource_facts import Facts
    scope['resources'] = Facts(scope)
    token = _active.set(scope)
    start = time.monotonic()
    try:
        yield scope
    finally:
        try:
            scope['resources'].close()
        finally:
            try:
                if task and (Path(task) / 'state.json').is_file():
                    from .context_control import event
                    event(task, 'runtime', 'independent_facts' if independent else 'shared_facts',
                          seconds=time.monotonic() - start,
                          detail={'hits': scope['hits'], 'misses': scope['misses'],
                                  'resources': dict(scope['resources'].counts),
                                  'authority': 'Raw facts only; elapsed time includes child operations, not a speedup measurement'})
            finally:
                _active.reset(token)


def _clone_native(value):
    if not value:
        return {}
    first = next(iter(value.values()))['node']
    root = first.getroottree().getroot()
    cloned = copy.deepcopy(root)
    mapping = dict(zip(root.iter(), cloned.iter()))
    result = {}
    for name, row in value.items():
        result[name] = {key: mapping[item] if key in ('node', 'parent') else copy.deepcopy(item)
                        for key, item in row.items()}
    return result


def geometry(function):
    @wraps(function)
    def read(pptx, size):
        scope = _active.get()
        if scope is None:
            return function(pptx, size)
        key = identity({'pptx': digest(pptx), 'canvas': list(size),
                        'implementation': digest(function.__globals__['__file__'])})
        if key not in scope['native']:
            from .context_policy import configuration
            while len(scope['native'])>=configuration()['cache']['native_snapshots']:
                scope['native'].pop(next(iter(scope['native'])))
            scope['native'][key] = function(pptx, size)
            scope['misses'] += 1
        else:
            scope['hits'] += 1
        return _clone_native(scope['native'][key])
    return read


def rgb(path, expected_hash=None):
    from .resource_facts import image_copy
    return image_copy(path, expected_hash, mode='RGB')


def metrics(function):
    """Hash-exact hits skip decoding. Changed renders fall back to ROI cache."""
    @wraps(function)
    def measure(task, state, candidate, roi):
        import platform, numpy, scipy, skimage, PIL
        from .resource_facts import resource_library
        from . import quality_policy
        source = state['source']
        current = candidate['preview']
        source_hash = digest(Path(task) / source['path'])
        current_hash = digest(Path(task) / current['path'])
        if source_hash != source['sha256'] or current_hash != current['sha256']:
            raise ValueError('Raw measurement source/current changed')
        dependencies = {'source': source_hash, 'preview': current_hash,
                        'roi': list(roi), 'canvas': state['source_size'],
                        'code': digest(function.__globals__['__file__']),
                        'cache_code': digest(__file__), 'policy': digest(quality_policy.__file__),
                        'sampling': 'registered-round-crop-lanczos',
                        'libraries': [platform.python_version(), numpy.__version__, scipy.__version__, skimage.__version__, PIL.__version__]}
        key = 'exact-image-metrics:' + identity(dependencies)
        library = resource_library(state['project'])
        previous = library.cache_get(key, dependencies)
        if previous is not None:
            telemetry = state.setdefault('telemetry', {})
            for name in ('cache_hits', 'metric_cache_hits', 'predecode_metric_hits'):
                telemetry[name] = telemetry.get(name, 0) + 1
            return previous
        result = function(task, state, candidate, roi)
        library.cache_put(key, result, dependencies)
        return result
    return measure
