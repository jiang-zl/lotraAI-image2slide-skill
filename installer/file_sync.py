"""Manifest-owned file delta. Unchanged active files are never rewritten."""
import hashlib, json, os, shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from install import within, same_bytes, write_json, read_json
from download import fetch

NAME='lotra-image2slide-skill'
CONTROL=('MANIFEST.json','.lotraai-image2slide-install.json')


def put(file, data):
    if file.is_file() and file.read_bytes()==data:return
    file.parent.mkdir(parents=True,exist_ok=True)
    part=file.with_name(file.name+'.lotra-sync-'+hashlib.sha256(data).hexdigest()+'.part')
    prior=part.read_bytes() if part.exists() else b''
    if not data.startswith(prior):raise ValueError('Preserve interrupted foreign write: '+str(part))
    with part.open('ab' if part.exists() else 'xb') as output:output.write(data[len(prior):])
    os.replace(part,file)


def reuse(source,destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    try:os.link(source,destination)
    except OSError:shutil.copy2(source,destination)


def owned(root):
    if not root.exists():return {}
    raw=within(root,CONTROL[0]).read_bytes();manifest=json.loads(raw)
    receipt=read_json(within(root,CONTROL[1]))
    if (manifest.get('name')!=NAME or receipt.get('name')!=NAME or
            receipt.get('version')!=manifest.get('version') or
            receipt.get('manifest_sha256')!=hashlib.sha256(raw).hexdigest()):
        raise ValueError('Preserve an unowned skill')
    records={name:{'bytes':ref.get('size',ref.get('bytes')),'sha256':ref['sha256']} for name,ref in manifest['files'].items()}
    for name in CONTROL:
        body=within(root,name).read_bytes();records[name]={'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
    found=set();found_dirs=set()
    for base,dirs,files in os.walk(root,followlinks=False):
        for name in dirs+files:within(root,(Path(base)/name).relative_to(root).as_posix())
        for name in files:found.add((Path(base)/name).relative_to(root).as_posix())
        for name in dirs:found_dirs.add((Path(base)/name).relative_to(root).as_posix())
    if found!=set(records):raise ValueError('Preserve user-added or missing skill files')
    expected_dirs={p.as_posix() for name in records for p in Path(name).parents if p.as_posix()!='.'}
    if found_dirs!=expected_dirs:raise ValueError('Preserve user-added skill directories')
    for name,record in records.items():
        if not same_bytes(within(root,name),record):raise ValueError('Preserve user-modified skill file: '+name)
    return records


def prepare(project,target,records,workspace,local_root=None):
    old=owned(target);candidate=within(workspace,'candidate')
    candidate.mkdir(parents=True,exist_ok=True)
    cache=within(project,'.lotraAI-build/downloads/sha256')
    plan={'old':old,'new':records,'add':[],'replace':[],'delete':sorted(set(old)-set(records)),'keep':[]}
    work=[]
    existing={r['sha256']:within(target,n) for n,r in old.items()}
    for name,record in records.items():
        within(target,name);path=within(candidate,name)
        prior=old.get(name)
        unchanged=prior is not None and prior['sha256']==record['sha256'] and prior['bytes']==record['bytes']
        plan['keep' if unchanged else 'replace' if prior else 'add'].append(name)
        work.append((name,record,unchanged))
    def obtain(item):
        name,record,unchanged=item;path=within(candidate,name)
        if path.exists():
            if not same_bytes(path,record):raise ValueError('Preserve changed candidate file')
            return
        local=within(local_root,name) if local_root else None
        prior_content=existing.get(record['sha256'])
        source=(within(target,name) if unchanged else prior_content if prior_content and same_bytes(prior_content,record)
                else local if local and same_bytes(local,record) else fetch(record,cache))
        reuse(source,path)
    with ThreadPoolExecutor(max_workers=4) as workers:list(workers.map(obtain,work))
    actual={p.relative_to(candidate).as_posix() for p in candidate.rglob('*') if p.is_file()}
    if actual!=set(records):raise ValueError('Candidate differs from the target file set')
    raw=within(candidate,'MANIFEST.json').read_bytes();body=json.loads(raw)
    expected=set(body['files'])|set(CONTROL)
    if body.get('name')!=NAME or expected!=set(records):raise ValueError('Source catalog differs from the skill manifest')
    for name,ref in body['files'].items():
        if ref['sha256']!=records[name]['sha256'] or ref['size']!=records[name]['bytes']:
            raise ValueError('Source manifest content differs from catalog')
    marker=read_json(within(candidate,CONTROL[1]))
    if marker.get('manifest_sha256')!=hashlib.sha256(raw).hexdigest():raise ValueError('New ownership receipt differs')
    write_json(within(workspace,'Plan.json'),plan)
    return candidate,plan


def prune(target,names):
    directories=set()
    for name in names:
        p=within(target,name).parent
        while p!=target and p.is_relative_to(target):directories.add(p);p=p.parent
    for p in sorted(directories,key=lambda p:len(p.parts),reverse=True):
        if p.is_dir():
            try:p.rmdir()
            except OSError:pass


def apply(target,candidate,plan,workspace):
    for name,ref in plan['old'].items():
        if not same_bytes(within(target,name),ref):raise ValueError('Skill changed since delta planning')
    preimage=within(workspace,'preimage');preimage.mkdir(parents=True,exist_ok=True)
    for name in plan['replace']+plan['delete']:
        saved=within(preimage,name)
        if not saved.exists():reuse(within(target,name),saved)
    write_json(within(workspace,'Apply.json'),{'status':'APPLYING','target':str(target),'plan':plan})
    target.mkdir(parents=True,exist_ok=True)
    for name in plan['delete']:within(target,name).unlink()
    prune(target,plan['delete'])
    for name in sorted(plan['add']+plan['replace'],key=lambda n:(n in CONTROL,n)):
        put(within(target,name),within(candidate,name).read_bytes())
    # No write/copy/rename is performed on any entry in plan['keep'].


def rollback(target,workspace):
    journal=within(workspace,'Apply.json')
    if not journal.exists():return
    data=read_json(journal)
    if data['status']=='COMPLETE':return
    if Path(data['target'])!=target:raise ValueError('Preserve a different sync journal')
    plan=data['plan']
    for name in plan['add']+plan['replace']:
        file=within(target,name);ref=plan['new'][name]
        partial=file.with_name(file.name+'.lotra-sync-'+ref['sha256']+'.part')
        if partial.exists():
            expected=within(workspace,'candidate/'+name).read_bytes()
            if hashlib.sha256(expected).hexdigest()!=ref['sha256'] or not expected.startswith(partial.read_bytes()):
                raise ValueError('Preserve foreign interrupted skill write')
            partial.unlink()
    for name in plan['add']:
        file=within(target,name)
        if file.exists():
            if not same_bytes(file,plan['new'][name]):raise ValueError('Preserve changed failed-update file')
            file.unlink()
    prune(target,plan['add'])
    for name in plan['replace']+plan['delete']:
        file=within(target,name);saved=within(workspace,'preimage/'+name)
        if file.exists() and not (same_bytes(file,plan['old'][name]) or name in plan['new'] and same_bytes(file,plan['new'][name])):
            raise ValueError('Preserve changed rollback target')
        put(file,saved.read_bytes())
    write_json(journal,{**data,'status':'ROLLED_BACK'})
