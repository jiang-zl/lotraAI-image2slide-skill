"""Finite, resumable, hash-addressed downloads; no model participation."""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def sha(file):
    h=hashlib.sha256()
    with Path(file).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''): h.update(block)
    return h.hexdigest()


def fetch(record, cache, *, attempts=3):
    expected=record['sha256']; size=int(record['bytes'])
    if len(expected)!=64 or any(c not in '0123456789abcdef' for c in expected) or size<=0:
        raise ValueError('Invalid pinned download record')
    cache=Path(cache); cache.mkdir(parents=True,exist_ok=True)
    if cache.is_symlink(): raise ValueError('Preserve redirected download cache')
    file=cache/expected; part=cache/(expected+'.part'); owner=cache/(expected+'.owner.json')
    if any(p.is_symlink() for p in (file,part,owner)):raise ValueError('Preserve linked download file')
    if file.exists():
        if file.stat().st_size==size and sha(file)==expected:return file
        raise ValueError('Preserve changed verified download')
    identity={'owner':'lotra-download-1','sha256':expected,'bytes':size,'url':record['url']}
    if owner.exists():
        if json.loads(owner.read_text())!=identity:raise ValueError('Preserve another partial download')
    else:
        if part.exists():raise ValueError('Preserve unowned partial download')
        owner.write_text(json.dumps(identity),encoding='utf-8')
    last=None
    for attempt in range(attempts):
        offset=part.stat().st_size if part.exists() else 0
        if offset==size and sha(part)==expected:os.replace(part,file);return file
        if offset>=size:part.unlink();offset=0  # Only our exact hash-addressed incomplete file.
        request=urllib.request.Request(record['url'],headers={'User-Agent':'lotraAI-installer/1.33.0',**({'Range':'bytes='+str(offset)+'-'} if offset else {})})
        try:
            transport=urllib.request.build_opener(urllib.request.ProxyHandler({})) if attempt and ('10061' in str(last) or 'refused' in str(last).lower()) else urllib.request.build_opener()
            with transport.open(request,timeout=60) as response:
                status=response.status
                if status==206:
                    content_range=response.headers.get('Content-Range','')
                    if not content_range.startswith('bytes '+str(offset)+'-') or content_range.rsplit('/',1)[-1]!=str(size):
                        raise ValueError('Range response does not match the pinned resource')
                elif status==200:offset=0  # A server that ignores Range requires a safe owned restart.
                else:raise ValueError('Unexpected download status '+str(status))
                with part.open('ab' if offset else 'wb') as output:
                    total=offset
                    while True:
                        block=response.read(4*1024*1024)
                        if not block:break
                        total+=len(block)
                        if total>size:raise ValueError('Download exceeds pinned bytes')
                        output.write(block)
            if part.stat().st_size==size and sha(part)==expected:os.replace(part,file);return file
            last='Incomplete or hash-mismatching download'
            if part.stat().st_size==size:part.unlink()
        except urllib.error.HTTPError as error:
            if error.code==416 and part.exists() and part.stat().st_size==size and sha(part)==expected:
                os.replace(part,file);return file
            last=str(error)
        except (OSError,ValueError) as error:last=str(error)
        if attempt+1<attempts:time.sleep(min(2**attempt,4))
    raise RuntimeError('DOWNLOAD_LIMIT_REACHED: '+str(last)+'; verified checkpoints and owned partial retained')
