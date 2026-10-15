"""Extract only the selected immutable equation-editor payload into this project."""
from pathlib import Path,PurePosixPath
import hashlib,io,json,os,shutil,tarfile,zipfile

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()

def install_renderer(bundle,project,manifest,key):
    record=manifest.get('math_renderers',{}).get(key)
    if not record:return {'status':'NOT_SUPPLIED','tested':False,'fallback_attempts':0}
    bundle,project=Path(bundle),Path(project)
    source=bundle/record['path']
    root=project/'.lotraAI-build/toolchain'/('LibreOffice-'+record['version']+'-'+key)
    receipt=root/'lotra-runtime.json'
    if receipt.exists():
        if json.loads(receipt.read_text())['sha256']!=record['sha256']:raise ValueError('Preserve another math runtime')
    else:
        if sha(source)!=record['sha256']:raise ValueError('Math runtime archive changed')
        root.mkdir(parents=True,exist_ok=True)
        def safe(name):
            parts=PurePosixPath(name).parts
            if PurePosixPath(name).is_absolute() or '..' in parts or '\\' in name:raise ValueError('Unsafe runtime member')
            path=(root/Path(*parts)).resolve()
            if not path.is_relative_to(root.resolve()):raise ValueError('Escaped runtime member')
            return path
        def put(path,data,mode=None):
            path.parent.mkdir(parents=True,exist_ok=True)
            if path.exists():
                if path.read_bytes()!=data:raise ValueError('Preserve a changed runtime file')
            else:path.write_bytes(data)
            if mode is not None and os.name!='nt':path.chmod(mode&0o777)
        if record['format']=='zip':
            with zipfile.ZipFile(source) as z:
                for member in z.infolist():
                    path=safe(member.filename)
                    if member.is_dir():path.mkdir(parents=True,exist_ok=True)
                    else:put(path,z.read(member))
        else:
            with tarfile.open(source) as outer:
                for package in outer:
                    if not package.name.endswith('.deb'):continue
                    blob=outer.extractfile(package).read()
                    if blob[:8]!=b'!<arch>\n':raise ValueError('Invalid ar package')
                    at=8
                    while at<len(blob):
                        header=blob[at:at+60];size=int(header[48:58]);name=header[:16].decode().strip().rstrip('/')
                        data=blob[at+60:at+60+size];at+=60+size+size%2
                        if not name.startswith('data.tar'):continue
                        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                            for member in archive:
                                path=safe(member.name)
                                if member.isdir():path.mkdir(parents=True,exist_ok=True)
                                elif member.isfile():put(path,archive.extractfile(member).read(),member.mode)
                                elif member.issym():
                                    raw=member.linkname
                                    if raw.startswith('/'):
                                        if not raw.startswith(('/opt/libreoffice26.2/','/usr/share/')):raise ValueError('External runtime symlink')
                                        raw=os.path.relpath(root/raw.lstrip('/'),path.parent)
                                    if not (path.parent/raw).resolve().is_relative_to(root.resolve()):raise ValueError('Escaped runtime link')
                                    path.parent.mkdir(parents=True,exist_ok=True)
                                    if path.is_symlink():
                                        if os.readlink(path)!=raw:raise ValueError('Changed runtime link')
                                    elif path.exists():raise ValueError('Preserve existing runtime link target')
                                    else:path.symlink_to(raw)
                                else:raise ValueError('Unsupported runtime member')
        receipt.write_text(json.dumps({'sha256':record['sha256'],'version':record['version'],'tested':False})+'\n')
    target=project/'.lotraAI-build/Portable-renderer.json'
    value=json.loads(target.read_text()) if target.exists() else {'platforms':{}}
    platform='Windows' if key.startswith('windows') else 'Linux'
    def normal(path):
        text=str(path.resolve())
        return '\\\\'+text[8:] if text.startswith('\\\\?\\UNC\\') else text[4:] if text.startswith('\\\\?\\') else text
    value.setdefault('platforms',{})[platform]={'executable':normal(root/record['executable']),
        'uno_python':normal(root/record['uno_python']),'version':record['version'],'installed_not_tested':True}
    target.write_text(json.dumps(value,indent=2)+'\n')
    return {'status':'INSTALLED_NOT_TESTED','root':str(root),'version':record['version'],'tested':False,'fallback_attempts':0}
