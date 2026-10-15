"""File identity, immutable inputs, single writer and bounded subprocesses."""

import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import shutil
import subprocess
import time
import threading

ROOT = Path(__file__).resolve().parents[2]

def scene_base(file,explicit=None):
    """Resolve generated Scene resources from their task, once at dispatch."""
    if explicit is not None:return Path(explicit).resolve()
    file=Path(file).resolve();scene=read_json(file);ref=scene.get('source',{})
    for parent in file.parents:
        state_file=parent/'state.json'
        if not state_file.is_file():continue
        state=read_json(state_file)
        if state.get('source',{}).get('sha256')!=ref.get('sha256'):continue
        resource=safe_path(parent,ref['path'])
        if resource.is_file() and digest(resource)==ref['sha256']:return parent
    return file.parent


def raster_rgb(image,background=(255,255,255)):
    """Compose source transparency on the explicitly fixed document canvas."""
    from PIL import Image
    if image.mode in ('RGBA','LA') or 'transparency' in image.info:
        surface=Image.new('RGBA',image.size,tuple(background)+(255,))
        surface.alpha_composite(image.convert('RGBA'));return surface.convert('RGB')
    return image.convert('RGB')


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            value.update(block)
    return value.hexdigest()


def canonical(value):
    from .state_repository import plain
    return json.dumps(plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def identity(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if isinstance(value,dict) and value.get('schema')=='lotra-indexed-document-1':
        from .state_repository import load_document
        return load_document(path,value)
    return value


def write_json(path, value):
    path = Path(path)
    repository=getattr(value,'_store_repository',None)
    if repository and path.resolve()==(repository.task/value._store_document).resolve():
        from .state_repository import store_document
        store_document(path,value)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_bytes(canonical(value) + b"\n")
    os.replace(tmp, path)


def portable_resource(relative):
    """Normalize a logical reference before the host's Path can change it.

    User/native relative separators are accepted at this boundary. Persisted
    resource identities use POSIX separators; ZIP entry paths stay stricter.
    Absolute host arguments never go back through this resource parser.
    """
    raw=os.fspath(relative)
    if not isinstance(raw,str) or not raw or any(ord(c)<32 for c in raw):
        raise ValueError('Resource must be a nonempty relative path')
    normalized=raw.replace('\\','/')
    portable=PurePosixPath(normalized)
    windows=PureWindowsPath(raw)
    if portable.is_absolute() or windows.drive or windows.root or '..' in portable.parts or ':' in normalized:
        raise ValueError('Resource must be relative: absolute, drive, UNC and traversal paths belong to a separate host/input interface')
    return portable.as_posix()


def safe_path(base, relative):
    logical=PurePosixPath(portable_resource(relative))
    root=Path(base).resolve()
    target=root.joinpath(*logical.parts).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Resource escapes project")
    return target


@contextlib.contextmanager
def writer(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".writer.lock"
    if lock.exists():
        recorded=read_json(lock)
        if recorded.get('pid')==os.getpid() and recorded.get('thread',threading.get_ident())==threading.get_ident():
            yield
            return
        if recorded.get('owner')=='lotra-task-writer-1':
            pid=recorded.get('pid');alive=True
            if type(pid) is int and pid>0:
                if os.name=='nt':
                    import csv,io
                    result=subprocess.run(['tasklist','/FI','PID eq '+str(pid),'/FO','CSV','/NH'],capture_output=True,text=True,timeout=10)
                    if result.returncode==0:
                        alive=any(len(row)>1 and row[1]==str(pid) for row in csv.reader(io.StringIO(result.stdout)))
                else:
                    try:os.kill(pid,0)
                    except ProcessLookupError:alive=False
                    except PermissionError:alive=True
            if not alive:
                archive=directory/'transactions'/'stale-locks';archive.mkdir(parents=True,exist_ok=True)
                saved=archive/(str(pid)+'-'+str(time.time_ns())+'.json')
                os.replace(lock,saved)
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, canonical({"pid": os.getpid(), "thread":threading.get_ident(),
                               "owner":"lotra-task-writer-1","started": time.time()}))
        os.close(fd)
        yield
    finally:
        lock.unlink()


def run(args, timeout=120):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {args[0]}\n{result.stderr}\n{result.stdout}")
    return result.stdout.strip()


def environment():
    fonts = run(["fc-list", ":", "family"]) if shutil.which("fc-list") else None
    native_fonts=None
    if not fonts and platform.system()=='Darwin':
        roots=[Path('/System/Library/Fonts'),Path('/Library/Fonts'),Path.home()/'Library/Fonts',
               Path('/Applications/Microsoft PowerPoint.app/Contents/Resources/DFonts')]
        native_fonts=[]
        for root in roots:
            if root.exists():
                for path in sorted(root.rglob('*')):
                    if path.suffix.lower() in ('.ttf','.ttc','.otf') and path.is_file():
                        native_fonts.append({'path':str(path),'sha256':digest(path)})
    return {"os": platform.platform(), "python": platform.python_version(),
            "font_inventory_hash": identity(sorted(fonts.splitlines())) if fonts else identity(native_fonts) if native_fonts else None,
            "font_inventory": sorted(set(fonts.splitlines())) if fonts else native_fonts,
            "libreoffice": shutil.which("soffice"), "powershell_bridge": shutil.which("powershell.exe")}


class Budget:
    def __init__(self, seconds, candidates):
        if seconds is None or candidates is None or seconds <= 0 or candidates <= 0:
            raise ValueError("Explicit positive resource budget required")
        self.deadline = time.monotonic() + seconds
        self.remaining = candidates

    def consume(self):
        if time.monotonic() >= self.deadline or self.remaining <= 0:
            raise TimeoutError("PAUSED_RESOURCE_LIMIT")
        self.remaining -= 1
