"""Extract only the selected immutable equation-editor payload into this project."""
from pathlib import Path,PurePosixPath
import hashlib,io,json,os,shutil,subprocess,plistlib,tarfile,zipfile
import importlib.util
import platform
import uuid

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
    ready=False
    if receipt.exists():
        previous=json.loads(receipt.read_text())
        if previous['sha256']!=record['sha256']:raise ValueError('Preserve another math runtime')
        ready=all((root/record[n]).is_file() for n in ('executable','uno_python'))
        for name in ('executable','uno_python'):
            if previous.get(name+'_sha256') and (root/record[name]).is_file() and sha(root/record[name])!=previous[name+'_sha256']:
                raise ValueError('Preserve a changed Math executable')
    if not ready:
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
        if record['format']=='macos-dmg':
            mount=root/'disk-image';mount.mkdir(exist_ok=True)
            attached=False
            try:
                completed=subprocess.run(['hdiutil','attach','-readonly','-nobrowse','-plist','-mountpoint',str(mount),str(source)],capture_output=True,check=True,timeout=180)
                attached=True;plistlib.loads(completed.stdout)
                app=mount/'LibreOffice.app'
                if not app.is_dir() or app.is_symlink():raise ValueError('Official disk image has no regular LibreOffice app')
                for base,dirs,files in os.walk(app,followlinks=False):
                    for name in dirs+files:
                        p=Path(base)/name
                        if p.is_symlink() and not p.resolve().is_relative_to(app.resolve()):raise ValueError('External app-bundle link')
                subprocess.run(['ditto',str(app),str(root/'LibreOffice.app')],capture_output=True,check=True,timeout=300)
            finally:
                if attached:subprocess.run(['hdiutil','detach',str(mount)],capture_output=True,check=True,timeout=90)
        elif record['format']=='zip':
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
    target=project/'.lotraAI-build/Portable-renderer.json'
    value=json.loads(target.read_text()) if target.exists() else {'platforms':{}}
    platform='Windows' if key.startswith('windows') else 'Darwin' if key.startswith('macos') else 'Linux'
    def normal(path):
        text=str(path.resolve())
        return '\\\\'+text[8:] if text.startswith('\\\\?\\UNC\\') else text[4:] if text.startswith('\\\\?\\') else text
    if not all((root/record[n]).is_file() for n in ('executable','uno_python')):raise ValueError('Math package has no required executable/Python launcher')
    if platform=='Darwin':
        checked=subprocess.run(['codesign','--verify','--deep','--strict',normal(root/'LibreOffice.app')],
            capture_output=True,timeout=60)
        if checked.returncode:
            raise ValueError('Official Math application signature verification failed: '+checked.stderr.decode('utf-8','replace')[-2000:])
    if not ready:
        receipt.write_text(json.dumps({'sha256':record['sha256'],'version':record['version'],'tested':False,
                                      **{n+'_sha256':sha(root/record[n]) for n in ('executable','uno_python')}})+'\n')
    value.setdefault('platforms',{})[platform]={'executable':normal(root/record['executable']),
        'uno_python':normal(root/record['uno_python']),'version':record['version'],'installed_not_tested':True,
        'execution_mode':'libreoffice_hosted' if platform=='Darwin' else 'subprocess_uno',
        **({'application_signature_verified':True} if platform=='Darwin' else {})}
    data=json.dumps(value,indent=2)+'\n'
    if not target.exists() or target.read_text()!=data:target.write_text(data)
    return {'status':'INSTALLED_NOT_TESTED','root':str(root),'version':record['version'],'tested':False,'fallback_attempts':0}


def verify_backend(project,skill,workspace,key):
    """Use the exact same bounded backend as export, with no core dependencies."""
    project,skill,workspace=map(Path,(project,skill,workspace))
    folder=workspace/'math-backend-probes'/uuid.uuid4().hex
    folder.mkdir(parents=True,exist_ok=False)
    module_file=skill/'scripts/core/editor_backend.py'
    spec=importlib.util.spec_from_file_location('lotra_install_math_backend',module_file)
    backend=importlib.util.module_from_spec(spec);spec.loader.exec_module(backend)
    configured=json.loads((project/'.lotraAI-build/Portable-renderer.json').read_bytes())['platforms'][platform.system()]
    try:
        # Every install/repeat performs a fresh finite startup check. Historical
        # uno_import_ready receipts cannot certify a different execution mode.
        facts=backend.run(configured,folder,operation='probe',timeout=60,
                          client_file=module_file.with_name('uno_editor_client.py'))
    except backend.BackendError as error:
        (workspace/'Math-backend-failure.json').write_text(json.dumps(error.facts,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        raise ValueError('Math backend unavailable; see '+str(folder/'backend-result.json')) from error
    proof=folder/'backend-result.json'
    record={'status':'READY','execution_mode':facts['execution_mode'],'backend_identity':facts['backend_identity'],
            'probe':{'path':proof.relative_to(project).as_posix(),'sha256':sha(proof)},
            'revalidated':True,'render_status':'NOT_RUN','office_behavior':'NOT_RUN'}
    marker=project/'.lotraAI-build/toolchain'/('LibreOffice-'+configured['version']+'-'+key)/'lotra-runtime.json'
    prior=json.loads(marker.read_bytes())
    marker.write_text(json.dumps({**prior,'uno_import_ready':True,'math_backend':record},sort_keys=True)+'\n',encoding='utf-8')
    return record
