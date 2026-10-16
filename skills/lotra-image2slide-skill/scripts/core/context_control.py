"""Task-scoped context, recoverable references and measured execution costs.

This index is a delivery aid, never a source of semantic or acceptance PASS.
Complete work contracts and the original remain authoritative. No provider
tokens are estimated from these local counters.
"""
import contextlib
import copy
import json
import math
import sqlite3
import time
from pathlib import Path
from .common import canonical, digest, identity, read_json, safe_path, write_json

VERSION = 'context-control-1'


def _state(task):
    task = Path(task).resolve()
    state = read_json(task / 'state.json')
    if not state.get('task_id') or not state.get('source', {}).get('sha256'):
        raise ValueError('Registered task and immutable original required')
    original = safe_path(task, state['source']['path'])
    if digest(original) != state['source']['sha256']:
        raise ValueError('Context original changed')
    return state


@contextlib.contextmanager
def index(task):
    root = safe_path(task, 'context')
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / 'index.sqlite', timeout=20)
    db.row_factory = sqlite3.Row
    try:
        db.executescript('''
          CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
          CREATE TABLE IF NOT EXISTS reads (key TEXT PRIMARY KEY, epoch INTEGER,
            request TEXT, reference TEXT, content_hash TEXT, characters INTEGER,
            bytes INTEGER, hits INTEGER DEFAULT 0);
          CREATE TABLE IF NOT EXISTS fields (key TEXT PRIMARY KEY, epoch INTEGER,
            reference TEXT, characters INTEGER);
          CREATE TABLE IF NOT EXISTS views (key TEXT PRIMARY KEY, epoch INTEGER,
            dependencies TEXT, reference TEXT, requests INTEGER DEFAULT 0);
          CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, stage TEXT,
            operation TEXT, seconds REAL, characters INTEGER, bytes INTEGER,
            detail TEXT, created REAL);
          CREATE TABLE IF NOT EXISTS attempts (key TEXT PRIMARY KEY, status TEXT,
            dependencies TEXT, evidence TEXT, reason TEXT);
          CREATE TABLE IF NOT EXISTS leases (path TEXT PRIMARY KEY, sha256 TEXT,
            task_id TEXT, source_hash TEXT);
        ''')
        if 'needs_body' not in {r['name'] for r in db.execute('PRAGMA table_info(reads)')}:
            try:db.execute('ALTER TABLE reads ADD COLUMN needs_body INTEGER DEFAULT 0')
            except sqlite3.OperationalError:
                if 'needs_body' not in {r['name'] for r in db.execute('PRAGMA table_info(reads)')}:raise
        with db:
            yield db
    finally:
        db.close()


def _epoch(db):
    row = db.execute("SELECT value FROM meta WHERE key='epoch'").fetchone()
    return int(row['value']) if row else 0


def library_scope(state):
    """No name similarity or semantic class grants access to another case."""
    if not state.get('task_id'):
        return None  # Standalone raw diagnostics cannot search private records.
    return {'task_id': state['task_id'], 'source_hash': state['source']['sha256'],
            'lineage': copy.deepcopy(state.get('library_lineage', []))}


def references(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            yield {'path': value['path'], 'sha256': value['sha256']}
        for child in value.values():
            yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def authorize(task, ref, *, state=None):
    """Registered dependency membership is checked before reading its body."""
    state = state or _state(task)
    path = safe_path(task, ref['path'])
    known = {(r['path'], r['sha256']) for r in references(state)}
    # A frozen complete packet may reference details not repeated in state.
    packet = state.get('packet') or {}
    execution = packet.get('execution_reference')
    if execution and (execution['path'], execution['sha256']) in known:
        file = safe_path(task, execution['path'])
        if digest(file) != execution['sha256']:
            raise ValueError('Current complete context contract changed')
        known.update((r['path'], r['sha256']) for r in references(read_json(file)))
    with index(task) as db:
        lease = db.execute('SELECT * FROM leases WHERE path=? AND sha256=? AND task_id=? AND source_hash=?',
                           (ref['path'], ref['sha256'], state['task_id'], state['source']['sha256'])).fetchone()
    if (ref['path'], ref['sha256']) not in known and lease is None:
        raise ValueError('CONTEXT_SCOPE_MISMATCH: reference is not a current registered dependency')
    if not path.is_file() or digest(path) != ref['sha256']:
        raise ValueError('Context dependency changed')
    return path


def register_output(task, output):
    """Register an actual program output, never a caller's reference claim."""
    task=Path(task).resolve(); output=Path(output).resolve()
    if not output.is_relative_to(task):
        return None
    state=_state(task)
    ref={'path':output.relative_to(task).as_posix(),'sha256':digest(output)}
    with index(task) as db:
        db.execute('INSERT OR REPLACE INTO leases VALUES(?,?,?,?)',
                   (ref['path'],ref['sha256'],state['task_id'],state['source']['sha256']))
    return ref


def deliver_read(task, ref, request, result, *, fresh=False):
    """De-duplicate a model-facing selector; program callers retain full data."""
    state = _state(task)
    authorize(task, ref, state=state)
    purpose = request.get('purpose', 'current_work')
    if not isinstance(purpose, str) or not purpose.strip() or len(purpose) > 160:
        raise ValueError('Bounded explicit read purpose required')
    key = identity({'task': state['task_id'], 'source': state['source']['sha256'],
                    'reference': ref, 'selector': request, 'schema': VERSION})
    data = canonical(result)
    with index(task) as db:
        epoch = _epoch(db)
        old = db.execute('SELECT * FROM reads WHERE key=? AND epoch=?', (key, epoch)).fetchone()
        if old and old['content_hash'] != identity(result):
            raise ValueError('Same frozen selector produced inconsistent data')
        abbreviated={'status': 'ALREADY_READ', 'reference': ref, 'selector': request,
                    'epoch': epoch, 'content_hash': old['content_hash'],
                    'continuation': {k: result[k] for k in ('next_offset', 'next_key_offset', 'total', 'count') if k in result},
                    'recover': 'Use --fresh for the body or context-control resume for a new context epoch.'} if old else None
        if old and not fresh and len(data)>len(canonical(abbreviated))+128:
            db.execute('UPDATE reads SET hits=hits+1 WHERE key=?', (key,))
            return abbreviated
        db.execute('INSERT OR REPLACE INTO reads(key,epoch,request,reference,content_hash,characters,bytes,hits,needs_body) VALUES(?,?,?,?,?,?,?,?,?)',
                   (key, epoch, canonical(request).decode(), canonical(ref).decode(),
                    identity(result), len(data.decode()), len(data), old['hits'] if old else 0,0))
    event(task, 'context', 'read', characters=len(data.decode()), byte_count=len(data),
          detail={'selector': request, 'reference_hash': ref['sha256'], 'fresh': bool(fresh)})
    return result


def checkpoint(task, state):
    """A small recovery envelope points to full state; it closes no work."""
    file = Path(task) / 'state.json'
    if not file.is_file():
        return None
    if read_json(file) != dict(state):
        raise ValueError('Recovery checkpoint requires the exact saved state')
    candidate = state.get('active_candidate') or state.get('selected') or {}
    packet = state.get('packet') or {}
    refs = [state['source']]
    refs.extend(candidate[k] for k in ('pptx', 'preview', 'render', 'scene') if isinstance(candidate.get(k), dict))
    flow = state.get('task_completion', {})
    recovery = {'schema': VERSION, 'task_id': state['task_id'],
                'source_hash': state['source']['sha256'],
                'state': {'path': 'state.json', 'sha256': digest(file)},
                'implementation': digest(__file__), 'stage': state.get('stage'),
                'revision': state.get('revision'), 'references': refs,
                'next': {k: packet[k] for k in ('packet_id', 'kind', 'target', 'revision', 'execution_reference', 'detail_reference') if k in packet},
                'pending_reference': {'path': 'state.json', 'sha256': digest(file),
                                      'fields': ['task_completion', 'analysis', 'source_regions', 'issues', 'packet']},
                'obligation_status': flow.get('status', 'ACTIVE'),
                'authority': 'Resume aid only; original/native coverage and quality_loop remain mandatory.'}
    target = safe_path(task, 'context/Recovery.json')
    write_json(target, recovery)
    return {'path': 'context/Recovery.json', 'sha256': digest(target)}


def resume(task):
    state=_state(task)
    with index(task) as db:
        epoch = _epoch(db) + 1
        db.execute("INSERT OR REPLACE INTO meta VALUES('epoch',?)", (str(epoch),))
    if state.get('objectives',{}).get('component_first'):
        from . import agent_runtime as a,component_workflow as c
        task=Path(task).resolve();contract,ledger=c._load(task,state)
        return {'status':'COMPONENT_RESUME','epoch':epoch,'task':str(task),'revision':state['revision'],
                'pending_transaction':(ledger or {}).get('pending_transaction'),
                'contract':(state.get('component_workflow') or {}).get('contract'),
                'next':a.next_packet(task)}
    state = _state(task)
    from . import agent_runtime as a
    # Includes current source seals, catalog and recursion activation.
    _, verified = a._state(task)
    if dict(verified) != read_json(Path(task) / 'state.json'):
        a._save(task, verified)
    checkpoint(task, verified)
    recovery = read_json(safe_path(task, 'context/Recovery.json'))
    for ref in recovery['references']:
        file = safe_path(task, ref['path'])
        if digest(file) != ref['sha256']:
            raise ValueError('Cannot resume changed artifact; sync it through the native edit route')
    return {'status': 'CONTEXT_RESTORED', 'epoch': epoch, 'recovery': recovery,
            'objectives': state.get('objectives'), 'next': recovery['next'],
            'readiness': 'Re-read needed owners in this epoch; no pending obligation was removed.'}


def present(task, result):
    """Delta display only. The full execution packet is never reduced."""
    if not isinstance(result, dict) or not isinstance(result.get('packet'), dict):
        return result
    state = _state(task)
    packet = result['packet']
    from .packet_compaction import restore, compact, CONTROL
    full = restore(Path(task), packet)
    # Some specialized modern packets are not state['packet']; freeze them too.
    file = safe_path(task, 'packets/context-' + identity(full) + '.json')
    if file.exists() and read_json(file) != full:
        raise ValueError('Frozen context packet collision')
    if not file.exists():
        write_json(file, full)
    reference = {'path': file.relative_to(Path(task).resolve()).as_posix(), 'sha256': digest(file)}
    display = {k: full[k] for k in CONTROL if k in full}
    from .context_policy import configuration
    policy=configuration()
    display['action_references']=full.get('action_references') or policy['reference_routes'].get(full.get('kind'),[policy['fallback_reference']])
    new, reused = {}, {}
    with index(task) as db:
        epoch = _epoch(db)
        db.execute('INSERT OR REPLACE INTO leases VALUES(?,?,?,?)',
                   (reference['path'], reference['sha256'], state['task_id'], state['source']['sha256']))
        for key, value in full.items():
            if key in CONTROL:
                continue
            field = identity({'source': state['source']['sha256'], 'owner': full.get('target'),
                              'kind': full.get('kind'), 'field': key, 'value': value,
                              'objectives': state.get('objectives'), 'execution': state.get('execution_contract'),
                              'implementation': digest(__file__)})
            old = db.execute('SELECT * FROM fields WHERE key=? AND epoch=?', (field, epoch)).fetchone()
            if old and len(canonical(value))>len(canonical({**json.loads(old['reference']),'field':key}))+64:
                old_ref = json.loads(old['reference'])
                old_file = safe_path(task, old_ref['path'])
                if digest(old_file) != old_ref['sha256'] or read_json(old_file).get(key) != value:
                    raise ValueError('Retained context field changed')
                reused[key] = {**old_ref, 'field': key}
            else:
                new[key] = value
                db.execute('INSERT OR REPLACE INTO fields VALUES(?,?,?,?)',
                           (field, epoch, canonical(reference).decode(), len(canonical(value).decode())))
    display.update(new)
    display['execution_reference'] = reference
    if reused:
        display['retained_fields'] = reused
    display['context_epoch'] = epoch
    budget = state.get('objectives', {}).get('context_chars', 9000)
    display = compact(Path(task), display, budget)
    # An already compact full-reference envelope may be cheaper than a delta
    # envelope containing multiple retained references. Compare actual output,
    # not the pre-compaction field sizes, before choosing the model view.
    if reused:
        baseline={**copy.deepcopy(full),'action_references':display.get('action_references',policy['reference_routes'].get(full.get('kind'),[policy['fallback_reference']])),
                  'execution_reference':reference,'context_epoch':epoch}
        baseline=compact(Path(task),baseline,budget)
        if len(canonical(baseline))<=len(canonical(display)):
            display=baseline;reused={}
    with index(task) as db:
        for ref in references(display):
            file = safe_path(task, ref['path'])
            if file.is_file() and digest(file) == ref['sha256']:
                db.execute('INSERT OR REPLACE INTO leases VALUES(?,?,?,?)',
                           (ref['path'], ref['sha256'], state['task_id'], state['source']['sha256']))
    answer = {**result, 'packet': display}
    event(task, 'context', 'packet', characters=len(canonical(answer).decode()), byte_count=len(canonical(answer)),
          detail={'full_characters': len(canonical(result).decode()), 'reused_fields': len(reused),
                  'epoch': epoch, 'packet_id': full.get('packet_id')})
    return answer


def view_requests(task, state, views, *, owner, rubric):
    """A view-file hit is not a model-review hit or a quality verdict."""
    output = []
    with index(task) as db:
        epoch = _epoch(db)
        for view in views:
            file = safe_path(task, view['path'])
            if digest(file) != view['sha256']:
                raise ValueError('Context observation changed')
            dep = {'source': state['source']['sha256'], 'owner': owner, 'view': view,
                   'rubric': rubric, 'policy': state.get('objectives'), 'version': VERSION}
            key = identity(dep)
            old = db.execute('SELECT * FROM views WHERE key=? AND epoch=?', (key, epoch)).fetchone()
            db.execute('INSERT OR REPLACE INTO views VALUES(?,?,?,?,?)',
                       (key, epoch, canonical(dep).decode(), canonical(view).decode(), (old['requests'] if old else 0) + 1))
            output.append({'key': key, 'role': view.get('role'), 'scope': view.get('roi'),
                           'file_repeat': old is not None, 'semantic_reuse': 'Requires independently qualified review_cache evidence'})
    return output


def event(task, stage, operation, *, seconds=0.0, characters=0, byte_count=0, detail=None):
    if _state(task).get('objectives',{}).get('component_first'):
        return None
    if not Path(task).is_dir():
        return
    if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0 or type(characters) is not int or type(byte_count) is not int or min(characters, byte_count) < 0:
        raise ValueError('Finite nonnegative local cost observations required')
    data = canonical(detail or {})
    if len(data) > 16000:
        raise ValueError('Cost event must reference large data, not repeat it')
    with index(task) as db:
        db.execute('INSERT INTO events(stage,operation,seconds,characters,bytes,detail,created) VALUES(?,?,?,?,?,?,?)',
                   (stage, operation, float(seconds), characters, byte_count, data.decode(), time.time()))


def attempt(task, request):
    """Unchanged ineffective branch cannot be mechanically scheduled again."""
    dependencies = request['dependencies']
    if not isinstance(dependencies, dict) or not dependencies:
        raise ValueError('Attempt source/input/operation dependencies required')
    key = identity({'operation': request['operation'], 'dependencies': dependencies, 'version': VERSION})
    with index(task) as db:
        old = db.execute('SELECT * FROM attempts WHERE key=?', (key,)).fetchone()
        if request.get('result') is None:
            return {'key': key, 'allowed': old is None or old['status'] not in ('ineffective', 'harmful'),
                    'previous': {k:old[k] for k in ('status','reason','evidence')} if old else None,
                    'effect': 'A rejected branch leaves its obligation pending; select a changed evidence-supported branch.'}
        if request['result'] not in ('improved', 'partial', 'ineffective', 'harmful', 'transient', 'uncertain'):
            raise ValueError('Typed branch result required')
        ref = request['evidence']
        file = authorize(task, ref)
        db.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?,?,?)',
                   (key, request['result'], canonical(dependencies).decode(), canonical(ref).decode(), request.get('reason', '')))
    return {'key': key, 'recorded': request['result'], 'evidence_hash': digest(file)}


def report(task):
    state = _state(task)
    with index(task) as db:
        reads = db.execute('SELECT COUNT(*) n,COALESCE(SUM(hits),0) hits,COALESCE(SUM(characters*hits),0) avoided_characters FROM reads').fetchone()
        views = db.execute('SELECT COUNT(*) n,COALESCE(SUM(requests-1),0) repeat_requests FROM views').fetchone()
        stages = [dict(row) for row in db.execute('SELECT stage,operation,COUNT(*) calls,SUM(seconds) seconds,SUM(characters) characters,SUM(bytes) bytes FROM events GROUP BY stage,operation ORDER BY stage,operation')]
        epoch = _epoch(db)
    return {'schema': VERSION, 'task_id': state['task_id'], 'epoch': epoch,
            'reads': dict(reads), 'views': dict(views), 'stages': stages,
            'provider_tokens': 'Read context-usage; local characters/cache hits are not token counts',
            'guarantee': 'Managed reads and adoption are scoped; generic host filesystem tools need host enforcement.'}


def dispatch(task, operation, request=None):
    from . import agent_runtime as a
    from .task_transaction import guard
    with guard(task):
        if operation == 'status':
            return report(task)
        if operation == 'resume':
            return resume(task)
        if operation == 'attempt':
            return attempt(task, request or {})
        if operation == 'history':
            _, state = a._state(task)
            name = request['task_id']
            import re
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', name):
                raise ValueError('Portable same-source history identity required')
            other = Path(state['project']) / '.lotraAI-build/tasks' / name
            previous = _state(other)
            if previous['source']['sha256'] != state['source']['sha256']:
                raise ValueError('Another original cannot be imported as current source history')
            lineage = state.setdefault('library_lineage', [])
            item = {'task_id': name, 'source_hash': previous['source']['sha256']}
            if item not in lineage:
                lineage.append(item)
            a._save(task, state)
            return {'status': 'SAME_SOURCE_HISTORY_BOUND', 'history': item}
        raise ValueError('Unknown context-control operation')
