"""Small release delta + only missing platform resources -> offline installer."""
import argparse
import concurrent.futures
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from download import fetch,sha
from install import platform_key,within,read_json,write_json


def companion(project,manifest,key):
    descriptor=project/'.lotraAI-build/toolchain'/('core-runtime-'+key+'.json')
    if not descriptor.exists():return None
    data=read_json(descriptor)
    file=Path(data.get('companion_path','')).resolve()
    if not file.is_relative_to(project.resolve()) or not (file/'Manifest.json').is_file():return None
    original=read_json(file/'Manifest.json')
    expected=manifest.get('runtime_compatibility',{}).get(key)
    from hashlib import sha256
    def fingerprint(value):return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    selected={n:r for n,r in original['files'].items() if not n.startswith('wheels/') or n.startswith(original['environments'][key]['wheels']+'/')}
    if fingerprint({'files':selected,'environment':original['environments'][key]})!=expected:return None
    for name,record in selected.items():
        if sha(within(file,name))!=record['sha256']:raise ValueError('Preserve changed companion resource')
    engine=within(project,data['engine']['path'])
    if sha(engine)!=data['engine']['sha256']:raise ValueError('Preserve changed prepared interpreter')
    return file


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True);parser.add_argument('--harness',default='auto')
    parser.add_argument('--bundle-root',type=Path,default=Path(__file__).resolve().parent.parent)
    args=parser.parse_args();project=args.project.resolve();root=args.bundle_root.resolve()
    if not project.is_dir() or project==Path.home().resolve() or project==Path(project.anchor):raise ValueError('Select an existing project')
    manifest=read_json(root/'Bundle-manifest.json');release=read_json(root/'Update-manifest.json');key=platform_key()
    if key not in manifest.get('math_renderers',{}):raise ValueError('Complete Math runtime is not supplied for this platform')
    if sha(root/'Bundle-manifest.json')!=release['bundle_manifest_sha256']:raise ValueError('Release manifest changed')
    reuse=companion(project,manifest,key)
    cache=within(project,'.lotraAI-build/downloads/sha256');pending=[]
    required=[manifest['math_renderers'][key]]
    if not reuse:
        complete=manifest['payloads']['runtime']
        required.append(complete if (root/complete['path']).is_file() else manifest['runtime_platforms'][key])
    for record in required:
        destination=within(root,record['path'])
        if destination.exists():
            if sha(destination)!=record['sha256']:raise ValueError('Preserve changed local runtime archive')
        elif record is manifest['math_renderers'][key]:
            receipt=project/'.lotraAI-build/toolchain'/('LibreOffice-'+record['version']+'-'+key)/'lotra-runtime.json'
            if receipt.exists() and read_json(receipt).get('sha256')==record['sha256']:continue
            pending.append(record)
        else:pending.append(record)
    # Two independent large resources at most; no per-part host questions.
    def obtain(record):
        source=fetch({**record,'url':release['resources'][record['path']]['url']},cache)
        destination=within(root,record['path']);destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:list(workers.map(obtain,pending))
    argv=[sys.executable,'-I','-X','utf8','-B',str(root/'installer/install.py'),'--project',str(project),'--harness',args.harness,'--bundle-root',str(root)]
    if reuse:argv+=['--reuse-companion',str(reuse)]
    return subprocess.run(argv,check=False).returncode


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status':'INSTALL_FAILED','phase':'DOWNLOAD_OR_REUSE','reason':str(error)[:320]},ensure_ascii=True));raise SystemExit(1)
