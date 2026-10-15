"""Task-owned immutable resource graph with SQLite compare-and-swap roots.

Only loaded branches are re-encoded. Legacy dictionaries/lists remain available
through lazy subclasses; ordinary consumers need not load the legacy archive.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3

SCHEMA = 'lotra-indexed-document-1'
CHUNK = 16384


def plain(value):
    if isinstance(value,Ref):return plain(value.load())
    if isinstance(value, dict): return {key:plain(val) for key,val in value.items()}
    if isinstance(value, (list,tuple)): return [plain(val) for val in value]
    return value


def encoded(value):
    return json.dumps(plain(value), ensure_ascii=False, sort_keys=True, separators=(',',':'), allow_nan=False).encode('utf-8')


class Ref:
    def __init__(self, repo, key):
        self.repo = repo; self.key = key
    def load(self):
        return self.repo.decode(self.key)


class LazyDict(dict):
    def __iter__(self):return dict.__iter__(self)
    def __getitem__(self, key):
        value = dict.__getitem__(self,key)
        if isinstance(value,Ref):
            value = value.load(); dict.__setitem__(self,key,value)
        return value
    def get(self,key,default=None):
        return self[key] if key in self else default
    def items(self):
        for key in dict.__iter__(self): yield key,self[key]
    def values(self):
        for key in dict.__iter__(self): yield self[key]
    def setdefault(self,key,default=None):
        if key not in self: self[key]=default
        return self[key]
    def pop(self,key,*default):
        if key not in self:
            if default: return default[0]
            raise KeyError(key)
        value=self[key]; dict.__delitem__(self,key); return value
    def copy(self): return {key:value for key,value in self.items()}
    def __deepcopy__(self,memo): return copy.deepcopy(self.copy(),memo)
    def __eq__(self,other): return plain(self)==plain(other)
    def __ne__(self,other): return not self==other


class LazyList(list):
    def __getitem__(self,key):
        if isinstance(key,slice): return [self[index] for index in range(*key.indices(len(self)))]
        value=list.__getitem__(self,key)
        if isinstance(value,Ref):
            value=value.load(); list.__setitem__(self,key,value)
        return value
    def __iter__(self):
        for index in range(len(self)): yield self[index]
    def pop(self,index=-1):
        value=self[index]; list.__delitem__(self,index); return value
    def sort(self,*args,**kwargs):
        values=list(self); values.sort(*args,**kwargs); self[:]=values
    def __deepcopy__(self,memo): return copy.deepcopy(list(self),memo)
    def __eq__(self,other): return plain(self)==plain(other)
    def __ne__(self,other): return not self==other


class Repository:
    def __init__(self, task):
        self.task=Path(task).resolve()
        self.folder=self.task/'state'; self.resources=self.task/'resources/state'
        self.folder.mkdir(parents=True,exist_ok=True); self.resources.mkdir(parents=True,exist_ok=True)
        self.database=self.folder/'index.sqlite'
        with self.connection() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS documents (
                name TEXT PRIMARY KEY, revision INTEGER NOT NULL, root TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS history (
                name TEXT NOT NULL, revision INTEGER NOT NULL, root TEXT NOT NULL,
                PRIMARY KEY(name,revision));
              CREATE TABLE IF NOT EXISTS consumers (
                kind TEXT NOT NULL, id TEXT NOT NULL, resource TEXT NOT NULL,
                PRIMARY KEY(kind,id));
            """)
    def connection(self):
        db=sqlite3.connect(self.database,timeout=30)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        return db
    def blob(self,payload):
        data=encoded(payload); key=hashlib.sha256(data).hexdigest()
        file=self.resources/(key+'.json')
        if not file.exists():
            temp=file.with_suffix('.'+str(os.getpid())+'.part')
            with temp.open('wb') as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.replace(temp,file)
        return key
    def encode(self,value):
        if isinstance(value,Ref) and value.repo.task==self.task: return value.key
        # Lazy branches retain untouched references without reading their bodies.
        if isinstance(value,LazyDict):
            return self.blob({'kind':'dict','children':{key:self.encode(val) for key,val in dict.items(value)}})
        if isinstance(value,LazyList):
            return self.blob({'kind':'list','children':[self.encode(val) for val in list.__iter__(value)]})
        raw=encoded(value)
        if len(raw)<=CHUNK or not isinstance(value,(dict,list)):
            return self.blob({'kind':'value','value':value})
        if isinstance(value,dict):
            return self.blob({'kind':'dict','children':{key:self.encode(val) for key,val in value.items()}})
        return self.blob({'kind':'list','children':[self.encode(val) for val in value]})
    def decode(self,key):
        data=(self.resources/(key+'.json')).read_bytes()
        if hashlib.sha256(data).hexdigest()!=key: raise ValueError('Immutable state resource changed')
        payload=json.loads(data)
        if payload['kind']=='dict': return LazyDict({k:Ref(self,v) for k,v in payload['children'].items()})
        if payload['kind']=='list': return LazyList(Ref(self,v) for v in payload['children'])
        return payload['value']
    def load(self,name):
        with self.connection() as db:
            row=db.execute('SELECT revision,root FROM documents WHERE name=?',(name,)).fetchone()
        if row is None: raise FileNotFoundError('Indexed document not registered: '+name)
        value=self.decode(row[1])
        if not isinstance(value,LazyDict): value=LazyDict(value)
        value._store_revision=row[0]; value._store_document=name; value._store_root=row[1]
        value._store_repository=self
        return value
    def save(self,name,value):
        expected=getattr(value,'_store_revision',value.get('_repository_revision'))
        root=self.encode(value)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT revision,root FROM documents WHERE name=?',(name,)).fetchone()
            if row and expected!=row[0]:
                raise ValueError('STALE_DOCUMENT_REVISION: reload before writing '+name)
            revision=(row[0]+1) if row else 1
            db.execute('INSERT OR REPLACE INTO documents VALUES(?,?,?)',(name,revision,root))
            db.execute('INSERT INTO history VALUES(?,?,?)',(name,revision,root))
        if isinstance(value,LazyDict):
            value._store_revision=revision; value._store_document=name; value._store_root=root
        else:
            value['_repository_revision']=revision
        return revision,root
    def index_rows(self,kind,rows):
        with self.connection() as db:
            for key,value in rows.items():
                db.execute('INSERT OR REPLACE INTO consumers VALUES(?,?,?)',(kind,key,self.encode(value)))
    def lookup(self,kind,key):
        with self.connection() as db:
            row=db.execute('SELECT resource FROM consumers WHERE kind=? AND id=?',(kind,key)).fetchone()
        return self.decode(row[0]) if row else None


def load_document(path,descriptor):
    path=Path(path).resolve(); levels=descriptor['task_levels']
    if type(levels) is not int or not 0<=levels<=8: raise ValueError('Invalid indexed-document root')
    task=path.parents[levels]; name=descriptor['document']
    if (task/name).resolve()!=path: raise ValueError('Indexed document escaped its registered path')
    return Repository(task).load(name)


def store_document(path,value,task=None):
    path=Path(path).resolve()
    if hasattr(value,'_store_repository'):
        repo=value._store_repository; task=repo.task
    else:
        task=Path(task or path.parent).resolve(); repo=Repository(task)
    name=path.relative_to(task).as_posix()
    if path.exists():
        existing=json.loads(path.read_text(encoding='utf-8-sig'))
        if existing.get('schema')!=SCHEMA:
            # One-time migration; bytes and historical failures remain immutable.
            archive=task/'legacy'/('state-'+hashlib.sha256(path.read_bytes()).hexdigest()+'.json')
            archive.parent.mkdir(exist_ok=True)
            if not archive.exists(): shutil.copy2(path,archive)
    # A previously loaded legacy snapshot has no index revision; it may create,
    # never overwrite, an existing indexed document.
    revision,root=repo.save(name,value)
    descriptor={'schema':SCHEMA,'document':name,'task_levels':len(path.relative_to(task).parts)-1}
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.pointer.part'); temp.write_bytes(encoded(descriptor)+b'\n')
    os.replace(temp,path)
    if name=='state.json':
        pointer={'schema':'lotra-task-manifest-1','task_id':value.get('task_id'),'state_index':'state/index.sqlite',
                 'source_ref':plain(value.get('source')),'revision':revision,'state_root':root}
        temp=task/'Task.json.part'; temp.write_bytes(encoded(pointer)+b'\n'); os.replace(temp,task/'Task.json')
    return revision

