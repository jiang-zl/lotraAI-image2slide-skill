"""The full-bundle route uses the same resumable content cache as installation."""
import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from download import fetch,sha
from install import VERSION,within,read_json


def download(project,manifest,output):
    if manifest.get('schema')!='lotraai-publication-release-1' or manifest.get('version')!=VERSION:
        raise ValueError('Unsupported complete-bundle manifest')
    bundle=manifest['bundle'];parts=bundle['parts'];name=bundle['filename']
    if name!='lotraAI-image2slide-v'+VERSION+'-bundle.zip':
        raise ValueError('Unexpected complete-bundle filename')
    if not parts or [p['index'] for p in parts]!=list(range(1,len(parts)+1)):
        raise ValueError('Incomplete or unordered complete-bundle parts')
    if len({p['filename'] for p in parts})!=len(parts) or sum(p['bytes'] for p in parts)!=bundle['bytes']:
        raise ValueError('Complete-bundle part identities differ')
    # Unchanged parts retain their original release filename and URL.
    if any(not re.fullmatch(r'lotraAI-image2slide-v[0-9]+\.[0-9]+\.[0-9]+-bundle\.zip\.part'+str(p['index']).zfill(3),p['filename']) or
           p['bytes']<=0 or p['bytes']>128*1024*1024 for p in parts):
        raise ValueError('Unexpected complete-bundle part')
    if output.is_symlink() or getattr(output,'is_junction',lambda:False)():
        raise ValueError('Preserve redirected output directory')
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    destination=within(output,name)
    if destination.exists():
        if destination.stat().st_size!=bundle['bytes'] or sha(destination)!=bundle['sha256']:
            raise ValueError('Preserve a different existing complete bundle')
    else:
        cache=within(project,'.lotraAI-build/downloads/sha256')
        source=fetch({'bytes':bundle['bytes'],'sha256':bundle['sha256'],
                      'parts':parts,'assembly':'ordered-release-parts'},cache)
        # Publish without replacing a concurrently created destination.
        try:os.link(source,destination)
        except FileExistsError:raise ValueError('Preserve a concurrently created output')
        except OSError:
            temporary=within(output,name+'.'+bundle['sha256']+'.assembling')
            offset=temporary.stat().st_size if temporary.exists() else 0
            if offset>bundle['bytes']:raise ValueError('Preserve a different interrupted output')
            with source.open('rb') as inp:
                if temporary.exists():
                    with temporary.open('rb') as prior:
                        for block in iter(lambda:prior.read(4*1024*1024),b''):
                            if inp.read(len(block))!=block:raise ValueError('Preserve different interrupted output bytes')
                with temporary.open('ab' if temporary.exists() else 'xb') as out:shutil.copyfileobj(inp,out,4*1024*1024)
            if sha(temporary)!=bundle['sha256']:raise ValueError('Output copy identity differs')
            if destination.exists():raise ValueError('Preserve a concurrently created output')
            try:os.link(temporary,destination);temporary.unlink()
            except FileExistsError:raise ValueError('Preserve a concurrently created output')
            except OSError:temporary.rename(destination)
    return {'status':'BUNDLE_DOWNLOADED','version':VERSION,'bundle':str(destination),
            'sha256':bundle['sha256'],'parts':len(parts),'product_execution':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(download(args.project.resolve(),read_json(args.manifest),args.output_dir),ensure_ascii=False))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'status':'BUNDLE_DOWNLOAD_FAILED','reason':str(error)[:300]}));raise SystemExit(1)
