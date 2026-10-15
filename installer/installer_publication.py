"""Private install staging; publish one skill only after runtime is deployed."""
import hashlib,importlib.util,json,os,re,shutil
from pathlib import Path
from zipfile import ZipFile
NAME='lotra-image2slide-skill'
RECEIPT='.lotraai-image2slide-install.json'

def discoverable_bundle(root):
    """Reuse an app-imported main entry; never create a second project entry."""
    root=Path(root).resolve()
    return (root.parent.name=='skills' and root.parent.parent.name in ('.codex','.agents','.claude')
            and (root.name==NAME or re.fullmatch(re.escape(NAME)+r'-v\d+\.\d+\.\d+',root.name) is not None))

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def bounded(project,path):
    project,path=Path(project).resolve(),Path(path).absolute()
    if path==project or not path.resolve().is_relative_to(project):raise ValueError('Install path outside project')
    cursor=path
    while cursor.resolve()!=project:
        if cursor.is_symlink() or cursor.exists() and getattr(cursor.lstat(),'st_file_attributes',0)&1024:
            raise ValueError('Preserve redirected install path')
        if cursor.parent==cursor:raise ValueError('Install ancestry does not reach project')
        cursor=cursor.parent
    return path

def owned_skill(folder):
    folder=Path(folder)
    raw=(folder/'MANIFEST.json').read_bytes();m=json.loads(raw)
    marker=json.loads((folder/RECEIPT).read_text())
    if m.get('name')!=NAME or marker.get('name')!=NAME or marker.get('version')!=m.get('version') or marker.get('manifest_sha256')!=hashlib.sha256(raw).hexdigest():
        raise ValueError('Preserve unowned skill '+str(folder))
    if not re.fullmatch(r'\d+\.\d+\.\d+',m['version']):raise ValueError('Invalid owned version')
    expected=set(m['files'])|{'MANIFEST.json',RECEIPT};found=set()
    for base,dirs,files in os.walk(folder,followlinks=False):
        for name in dirs+files:
            p=Path(base)/name
            if p.is_symlink() or getattr(p.lstat(),'st_file_attributes',0)&1024:raise ValueError('Preserve linked skill member')
        for name in files:found.add((Path(base)/name).relative_to(folder).as_posix())
    if found!=expected:raise ValueError('Preserve skill with user-added files '+str(folder))
    for name,ref in m['files'].items():
        p=folder/name
        if not p.resolve().is_relative_to(folder.resolve()) or p.stat().st_size!=ref['size'] or sha(p)!=ref['sha256']:
            raise ValueError('Preserve changed skill file '+str(p))
    return m,raw

def package_helper(root,manifest,state_dir):
    record=manifest['payloads']['skill'];archive=Path(root)/record['path']
    if sha(archive)!=record['sha256']:raise ValueError('Skill payload changed')
    with ZipFile(archive) as z:
        raw=z.read('MANIFEST.json');m=json.loads(raw);code=z.read('scripts/package_skill.py')
        if hashlib.sha256(raw).hexdigest()!=record['manifest_sha256'] or hashlib.sha256(code).hexdigest()!=m['files']['scripts/package_skill.py']['sha256']:
            raise ValueError('Skill installer identity differs')
    helper=Path(state_dir)/'package_skill.py'
    if helper.exists() and helper.read_bytes()!=code:raise ValueError('Preserve changed private installer')
    helper.write_bytes(code)
    spec=importlib.util.spec_from_file_location('lotra_private_installer',helper)
    pkg=importlib.util.module_from_spec(spec);spec.loader.exec_module(pkg)
    return pkg,archive

def stage_skill(root,project,manifest,state_dir,state):
    pkg,archive=package_helper(root,manifest,state_dir)
    payload,raw,m=pkg.verify_archive(archive)
    target=bounded(project,Path(state_dir)/'skill-staging')
    target.mkdir(parents=True,exist_ok=True)
    expected={**payload,'MANIFEST.json':raw,pkg.RECEIPT:pkg.receipt_for(raw)}
    for name,data in expected.items():
        p=bounded(project,target/name);p.parent.mkdir(parents=True,exist_ok=True)
        if p.exists() and p.read_bytes()!=data:raise ValueError('Preserve changed staged skill')
        if not p.exists():p.write_bytes(data)
    pkg.verify_installation(target)
    return target

def publish_skill(root,project,manifest,state_dir,state):
    pkg,archive=package_helper(root,manifest,state_dir)
    stage=bounded(project,Path(state_dir)/'skill-staging')
    pkg.verify_installation(stage)
    imported=Path(root).resolve() if discoverable_bundle(root) else None
    target=imported or bounded(project,Path(project)/'.agents/skills'/NAME)
    folder=bounded(project,Path(project)/'.agents/skills');folder.mkdir(parents=True,exist_ok=True)
    expected=manifest['payloads']['skill']['manifest_sha256'];previous=[];matching=None
    # Preflight registration syntax/ownership before any old skill is archived.
    agents=Path(project)/'AGENTS.md'
    if agents.exists():
        text=agents.read_text(encoding='utf-8-sig');begin='<!-- lotraAI-bundle-entry:start -->';end='<!-- lotraAI-bundle-entry:end -->'
        if begin in text or end in text:
            if text.count(begin)!=1 or text.count(end)!=1 or text.index(begin)>=text.index(end):raise ValueError('Preserve ambiguous managed entry blocks')
        begin,end='<!-- lotraAI-release-policy:start -->','<!-- lotraAI-release-policy:end -->'
        if begin in text or end in text:
            if text.count(begin)!=1 or text.count(end)!=1 or text.index(begin)>=text.index(end):raise ValueError('Preserve ambiguous release policy blocks')
    selected=Path(project)/'.lotraAI-build/Active-skill.json'
    if selected.exists() and json.loads(selected.read_text(encoding='utf-8-sig')).get('name')!=NAME:raise ValueError('Preserve another selected skill')
    # All prior lotra folders must be owned and unchanged before moving any.
    for p in folder.iterdir():
        if not p.is_dir() or p.name!=NAME and not p.name.startswith(NAME+'-v'):continue
        if imported and p.resolve()==imported:continue
        bounded(project,p);m,raw=owned_skill(p)
        if not imported:
            if p==target and hashlib.sha256(raw).hexdigest()==expected:matching=p
            elif matching is None and hashlib.sha256(raw).hexdigest()==expected:matching=p
        previous.append((p,m,raw))
    archives=[]
    for p,m,raw in previous:
        if p==matching:continue
        archive_folder=bounded(project,Path(project)/'productions'/('v'+m['version'])/('installed-'+p.name+'-'+hashlib.sha256(raw).hexdigest()[:12]))
        if archive_folder.exists():raise ValueError('Preserve occupied skill archive')
        archives.append((p,archive_folder))
    journal=Path(state_dir)/'Publication-rollback.json'
    if not journal.exists():
        preimages={}
        for name in ('AGENTS.md','.lotraAI-build/Active-skill.json','.lotraAI-build/Bundle-install.json'):
            p=Path(project)/name
            if p.exists():
                backup=Path(state_dir)/'registration-preimage'/name;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,backup)
                preimages[name]=str(backup)
            else:preimages[name]=None
        journal.write_text(json.dumps({'archives':[(str(a),str(b)) for a,b in archives],'target':str(target),'expected':expected,'stage':str(stage),'preimages':preimages}),encoding='utf-8')
    for source,destination in archives:
        destination.parent.mkdir(parents=True,exist_ok=True);source.rename(destination)
    if imported:
        # Bundle manifest files were checked by install.py before runtime
        # deployment. Root has runtime assets as well as the main code, so it
        # is not an inner package_skill installation with an exact inventory.
        return imported
    if matching:
        if matching!=target:matching.rename(target)
    else:stage.rename(target)
    pkg.verify_installation(target)
    return target


def rollback_publication(project,state_dir):
    journal=Path(state_dir)/'Publication-rollback.json'
    if not journal.exists():return
    data=json.loads(journal.read_text());target=bounded(project,Path(data['target']))
    if data.get('status')=='COMPLETE':return
    archives=[(bounded(project,Path(a)),bounded(project,Path(b))) for a,b in data['archives']]
    if target.exists():
        _,raw=owned_skill(target)
        if hashlib.sha256(raw).hexdigest()!=data['expected']:
            # Failure before this previous skill was archived: restore only
            # already moved siblings, preserving the unchanged active target.
            for old,backup in reversed(archives):
                if backup.exists() and not old.exists():backup.rename(old)
            return
        stage=bounded(project,Path(data['stage']))
        if stage.exists():return
        target.rename(stage)
    for old,backup in reversed(archives):
        if backup.exists() and not old.exists():backup.rename(old)
    for name,backup in data['preimages'].items():
        p=bounded(project,Path(project)/name)
        if backup:shutil.copy2(backup,p)
        elif p.exists():p.unlink()
