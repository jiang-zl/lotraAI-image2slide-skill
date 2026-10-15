"""Project-local, versioned evidence/assets/experience and dependency caches.

Data does not execute. Blob IDs are portable; a task owner is the only writer.
PPTX snapshots remain authoritative when a recipe cannot express user edits.
"""
import json
import contextlib
import shutil
import sqlite3
import time
from pathlib import Path
from .common import canonical, digest, identity, safe_path, write_json

BUILD_DIR = '.lotraAI-build'
KINDS = {'evidence', 'component', 'recipe', 'asset', 'issue', 'task', 'experience'}


class Library:
    def __init__(self, project, scope=None):
        from .execution_context import _active
        current = _active.get()
        self.scope = scope if scope is not None else (current or {}).get('library_scope')
        self.root = Path(project).expanduser().resolve() / BUILD_DIR / 'library'
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'index.sqlite'
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS records (
                id TEXT NOT NULL, revision INTEGER NOT NULL, kind TEXT NOT NULL,
                semantic_class TEXT, state TEXT, payload TEXT NOT NULL,
                fingerprint TEXT NOT NULL, created REAL NOT NULL,
                PRIMARY KEY(id, revision));
              CREATE INDEX IF NOT EXISTS by_kind ON records(kind, semantic_class, state);
              CREATE TABLE IF NOT EXISTS dependencies (
                dependent TEXT, revision INTEGER, dependency TEXT, fingerprint TEXT,
                PRIMARY KEY(dependent, revision, dependency));
              CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY, payload TEXT, dependencies TEXT, created REAL, payload_hash TEXT);
              CREATE TABLE IF NOT EXISTS outcomes (
                id INTEGER PRIMARY KEY, subject TEXT, evidence TEXT, result TEXT,
                detail TEXT, created REAL);
            ''')
            if 'payload_hash' not in {r['name'] for r in db.execute('PRAGMA table_info(cache)')}:
                try:db.execute('ALTER TABLE cache ADD COLUMN payload_hash TEXT')
                except sqlite3.OperationalError:
                    if 'payload_hash' not in {r['name'] for r in db.execute('PRAGMA table_info(cache)')}:raise
            for name,kind in (('accessed','REAL'),('storage_bytes','INTEGER')):
                if name not in {r['name'] for r in db.execute('PRAGMA table_info(cache)')}:
                    try:db.execute('ALTER TABLE cache ADD COLUMN '+name+' '+kind)
                    except sqlite3.OperationalError:
                        if name not in {r['name'] for r in db.execute('PRAGMA table_info(cache)')}:raise
            db.execute('UPDATE cache SET storage_bytes=length(CAST(payload AS BLOB))+length(CAST(dependencies AS BLOB)) WHERE storage_bytes IS NULL')
            columns = {r['name'] for r in db.execute('PRAGMA table_info(records)')}
            for name in ('task_owner', 'source_hash', 'namespace'):
                if name not in columns:
                    try: db.execute('ALTER TABLE records ADD COLUMN ' + name + ' TEXT')
                    except sqlite3.OperationalError:
                        if name not in {r['name'] for r in db.execute('PRAGMA table_info(records)')}: raise
            # Old records retain their exact payload/fingerprint. A task-name
            # prefix is only a private owner, never public promotion or truth.
            db.execute("UPDATE records SET task_owner=substr(id,1,instr(id,':')-1),namespace='legacy' WHERE namespace IS NULL AND instr(id,':')>1")
            db.execute('CREATE INDEX IF NOT EXISTS by_scope ON records(namespace,task_owner,source_hash,kind,semantic_class)')

    @contextlib.contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db, timeout=20)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def blob(self, file):
        file = Path(file)
        sha = digest(file)
        suffix = file.suffix.lower()
        if not suffix or len(suffix) > 12 or not suffix[1:].isalnum():
            suffix = '.bin'
        relative = 'blobs/' + sha[:2] + '/' + sha + suffix
        destination = safe_path(self.root, relative)
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + '.tmp')
            shutil.copyfile(file, temporary)
            temporary.replace(destination)
        return {'path': relative, 'sha256': sha, 'bytes': file.stat().st_size}

    def resolve(self, ref):
        path = safe_path(self.root, ref['path'])
        if digest(path) != ref['sha256']:
            raise ValueError('Library blob changed: ' + ref['path'])
        return path

    def put(self, kind, record_id, payload, dependencies=None):
        if kind not in KINDS or not isinstance(record_id, str) or not record_id:
            raise ValueError('Unknown record kind or empty identity')
        payload = dict(payload)
        if self.scope:
            declared = payload.get('_scope')
            expected = {'namespace': 'task', 'task_id': self.scope['task_id'], 'source_hash': self.scope['source_hash']}
            if declared is not None and declared != expected:
                raise ValueError('A current task cannot relabel another case or promote private facts')
            payload['_scope'] = expected
        declared = payload.get('_scope', {})
        namespace = declared.get('namespace', 'legacy')
        if namespace == 'public':
            self._public(payload)
        owner = declared.get('task_id', payload.get('task_id'))
        if owner is None and ':' in record_id: owner = record_id.split(':', 1)[0]
        source_hash = declared.get('source_hash')
        fingerprint = identity(payload)
        with self.connect() as db:
            old = db.execute('SELECT * FROM records WHERE id=? ORDER BY revision DESC LIMIT 1',
                             (record_id,)).fetchone()
            if old is not None and old['fingerprint'] == fingerprint:
                previous={r['dependency']:r['fingerprint'] for r in db.execute('SELECT dependency,fingerprint FROM dependencies WHERE dependent=? AND revision=?',(record_id,old['revision']))}
                if previous==(dependencies or {}):
                    return {'id': record_id, 'revision': old['revision'], 'fingerprint': fingerprint}
            revision = old['revision'] + 1 if old is not None else 1
            db.execute('INSERT INTO records(id,revision,kind,semantic_class,state,payload,fingerprint,created,task_owner,source_hash,namespace) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (record_id, revision, kind, payload.get('semantic_class'),
                        payload.get('state', 'task_useful'), canonical(payload).decode(),
                        fingerprint, time.time(), owner, source_hash, namespace))
            for dep, value in (dependencies or {}).items():
                db.execute('INSERT INTO dependencies VALUES(?,?,?,?)',
                           (record_id, revision, dep, value))
        return {'id': record_id, 'revision': revision, 'fingerprint': fingerprint}

    def get(self, record_id, revision=None):
        with self.connect() as db:
            row = (db.execute('SELECT * FROM records WHERE id=? ORDER BY revision DESC LIMIT 1',
                              (record_id,)).fetchone() if revision is None else
                   db.execute('SELECT * FROM records WHERE id=? AND revision=?',
                              (record_id, revision)).fetchone())
        if row is None:
            return None
        if self.scope and not self._permitted(row):
            raise ValueError('LIBRARY_SCOPE_MISMATCH: another case is not current source evidence')
        return {'id': row['id'], 'revision': row['revision'], 'kind': row['kind'],
                'fingerprint': row['fingerprint'], 'payload': json.loads(row['payload'])}

    def find(self, kind, query, limit=3, max_chars=3500):
        """Applicability first; only a few short descriptors enter host context."""
        with self.connect() as db:
            where, parameters = self._scope_sql()
            rows = db.execute('''SELECT r.* FROM records r JOIN
                (SELECT id, MAX(revision) rev FROM records GROUP BY id) latest
                ON r.id=latest.id AND r.revision=latest.rev
                WHERE r.kind=? AND r.semantic_class=? AND (''' + where + ')',
                              (kind, query.get('semantic_class'), *parameters)).fetchall()
        candidates = []
        for row in rows:
            payload = json.loads(row['payload'])
            if row['namespace'] == 'public': self._public(payload)
            if payload.get('state') in ('quarantined', 'stale', 'unresolved'):
                continue
            if query.get('view') and payload.get('view') not in (query['view'], 'any'):
                continue
            if not set(query.get('required_parts', [])) <= set(payload.get('parts', [])):
                continue
            if not set(query.get('edit_targets', [])) <= set(payload.get('edit_targets', [])):
                continue
            if query.get('allowed_representations') and payload.get('representation') not in query['allowed_representations']:
                continue
            if query.get('representation') and payload.get('representation') != query['representation']:
                continue
            conditions = payload.get('conditions', {})
            if any(query.get(key) not in values for key, values in conditions.items()
                   if isinstance(values, list)):
                continue
            score = len(set(query.get('style_tags', [])) & set(payload.get('style_tags', [])))
            candidates.append((score, row, payload))
        output, cost = [], 0
        for _, row, payload in sorted(candidates, key=lambda item: (-item[0], item[1]['id'])):
            item = {key: payload[key] for key in ('semantic_class', 'view', 'parts', 'edit_targets',
                    'style_tags', 'representation', 'preview', 'pptx', 'recipe', 'limits',
                    'slide','component_id','root_name','recipe_state','derived_state','property','stage',
                    'root_evidence','successful_effect') if key in payload}
            item.update(id=row['id'], revision=row['revision'])
            size = len(canonical(item).decode('utf-8'))
            if cost + size > max_chars:
                continue
            output.append(item); cost += size
            if len(output) >= limit:
                break
        return output

    @staticmethod
    def _public(payload):
        """Public constructor descriptors contain no old image/PPT facts."""
        if payload.get('state') != 'promoted' or not payload.get('semantic_class') or not payload.get('recipe'):
            raise ValueError('Public reuse requires a promoted generic constructor')
        forbidden = {'pptx','preview','source','original','root_evidence','source_hash','task_id','successful_effect','slide','component_id','root_name','source_roi'}
        def inspect(value):
            if isinstance(value, dict):
                if forbidden & set(value): raise ValueError('Private source/snapshot cannot be public constructor data')
                for child in value.values(): inspect(child)
            elif isinstance(value, list):
                for child in value: inspect(child)
            elif isinstance(value, str) and ('.lotraAI-build' in value or ':\\' in value or '/home/' in value or value.startswith('\\\\')):
                raise ValueError('Public template cannot reference a private filesystem')
        inspect({k:v for k,v in payload.items() if k != '_scope'})
        promotion = payload.get('promotion', {})
        if promotion.get('kind') != 'generic_constructor' or promotion.get('validated') is not True or not promotion.get('applicability'):
            raise ValueError('Public template needs explicit applicability and validated promotion')

    def _scope_sql(self):
        public = "r.namespace='public' AND r.state='promoted'"
        if not self.scope: return public, []
        terms = [public, '(r.task_owner=? AND r.source_hash=?)']
        values = [self.scope['task_id'], self.scope['source_hash']]
        for item in self.scope.get('lineage', []):
            if item.get('source_hash') != self.scope['source_hash']:
                raise ValueError('History must share the verified original')
            terms.append('(r.task_owner=? AND r.source_hash=?)')
            values.extend((item['task_id'], self.scope['source_hash']))
        return ' OR '.join(terms), values

    def _permitted(self, row):
        if row['namespace'] == 'public' and row['state'] == 'promoted':
            self._public(json.loads(row['payload'])); return True
        if not self.scope: return False
        owners = {self.scope['task_id']} | {r['task_id'] for r in self.scope.get('lineage', []) if r.get('source_hash') == self.scope['source_hash']}
        return row['task_owner'] in owners and row['source_hash']==self.scope['source_hash']

    def cache_get(self, key, dependencies):
        from .execution_context import _active
        if (_active.get() or {}).get('independent'):
            return None  # Current independent gates recompute all predicates.
        with self.connect() as db:
            row = db.execute('SELECT * FROM cache WHERE key=?', (key,)).fetchone()
        if row is None or json.loads(row['dependencies']) != dependencies:
            return None
        if not row['payload_hash']:return None # Old unchecked caches remain historical, not current evidence.
        result=json.loads(row['payload'])
        if identity({'payload':result,'dependencies':dependencies})!=row['payload_hash']:
            raise ValueError('Stored cache payload changed: '+key)
        with self.connect() as db:db.execute('UPDATE cache SET accessed=? WHERE key=?',(time.time(),key))
        return result

    def cache_put(self, key, value, dependencies):
        payload=canonical(value).decode();deps=canonical(dependencies).decode();now=time.time()
        from .context_policy import configuration
        total=len(payload.encode())+len(deps.encode())
        # Large one-off payloads must not flush the small hot working set.
        if total>min(8*1024*1024,configuration()['cache']['max_bytes']//8):return
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO cache(key,payload,dependencies,created,payload_hash,accessed,storage_bytes) VALUES(?,?,?,?,?,?,?)',
                       (key,payload,deps,now,identity({'payload':value,'dependencies':dependencies}),now,len(payload.encode())+len(deps.encode())))
        self.trim_cache()

    def trim_cache(self,max_bytes=None,max_entries=None):
        """Evict recomputable cache rows only, never evidence/assets/receipts."""
        from .context_policy import configuration
        limits=configuration()['cache'];max_bytes=limits['max_bytes'] if max_bytes is None else max_bytes;max_entries=limits['max_entries'] if max_entries is None else max_entries
        if type(max_bytes) is not int or type(max_entries) is not int or min(max_bytes,max_entries)<1:raise ValueError('Positive recomputable cache limits required')
        removed=0
        with self.connect() as db:
            # Separate pixel/numeric working sets. Durable records and evidence are outside this table.
            for prefix,share in (('resource-pixels:',.25),('',.75)):
                clause="key LIKE 'resource-pixels:%'" if prefix else "key NOT LIKE 'resource-pixels:%'"
                rows=db.execute('SELECT key,storage_bytes FROM cache WHERE '+clause+' ORDER BY COALESCE(accessed,created),key').fetchall()
                amount=sum(r['storage_bytes'] for r in rows);entries=len(rows)
                for row in rows:
                    if amount<=max_bytes*share and entries<=max_entries*share:break
                    db.execute('DELETE FROM cache WHERE key=?',(row['key'],));amount-=row['storage_bytes'];entries-=1;removed+=1
            count,total=db.execute('SELECT COUNT(*),COALESCE(SUM(storage_bytes),0) FROM cache').fetchone()
            if count>max_entries or total>max_bytes:
                for row in db.execute('SELECT key,storage_bytes FROM cache ORDER BY COALESCE(accessed,created),key').fetchall():
                    if count<=max_entries and total<=max_bytes:break
                    db.execute('DELETE FROM cache WHERE key=?',(row['key'],));count-=1;total-=row['storage_bytes'];removed+=1
        return {'removed_recomputable_rows':removed,'remaining_rows':count,'bytes':total,'protected':'all records, blobs and task evidence'}

    def invalidate(self, changed_dependencies):
        """Invalidate only conclusions that actually depend on changed data."""
        changed = set(changed_dependencies)
        count = 0
        with self.connect() as db:
            for row in db.execute('SELECT key, dependencies FROM cache').fetchall():
                if changed & set(json.loads(row['dependencies'])):
                    db.execute('DELETE FROM cache WHERE key=?', (row['key'],)); count += 1
        return count

    def outcome(self, subject, evidence, result, detail):
        if result not in ('improved', 'partial', 'ineffective', 'harmful', 'uncertain'):
            raise ValueError('Unknown observed outcome')
        with self.connect() as db:
            db.execute('INSERT INTO outcomes(subject,evidence,result,detail,created) VALUES(?,?,?,?,?)',
                       (subject, evidence, result, canonical(detail).decode(), time.time()))

    def capture_asset(self, asset_id, pptx, descriptor, *, preview=None, source=None, recipe=None):
        payload = dict(descriptor)
        payload['pptx'] = self.blob(pptx)
        if preview:
            payload['preview'] = self.blob(preview)
        if source:
            payload['source'] = self.blob(source)
        if recipe:
            payload['recipe'] = recipe
        payload.setdefault('state', 'task_useful')
        payload.setdefault('limits', [])
        return self.put('asset', asset_id, payload)

    def sync_asset(self, asset_id, edited_pptx):
        """Keep the actual edited PPTX; never reconstruct it from a stale recipe."""
        old = self.get(asset_id)
        if old is None or old['kind'] != 'asset':
            raise ValueError('Unknown PPTX asset')
        payload = dict(old['payload'])
        if payload['pptx']['sha256'] == digest(edited_pptx):
            return {'status': 'UNCHANGED', 'id': asset_id, 'revision': old['revision']}
        from .saved_components import inventory
        payload['pptx'] = self.blob(edited_pptx)
        payload['external_native_inventory'] = inventory(edited_pptx)
        payload['recipe_state'] = 'snapshot_only'
        payload.pop('preview', None)
        payload['derived_state'] = 'refresh_on_use'
        record = self.put('asset', asset_id, payload)
        self.invalidate([asset_id])
        return {'status': 'IMPORTED_USER_VERSION', **record}
