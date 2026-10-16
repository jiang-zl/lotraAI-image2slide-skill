"""Finite, resumable, hash-addressed downloads; no model participation."""
import hashlib
import json
import os
import time
import threading
import urllib.error
import urllib.request
from pathlib import Path


def sha(file):
    h=hashlib.sha256()
    with Path(file).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''): h.update(block)
    return h.hexdigest()


_LOCKS={}
_LOCK_GUARD=threading.Lock()


def fetch(record, cache, *, attempts=3):
    with _LOCK_GUARD:lock=_LOCKS.setdefault(record['sha256'],threading.Lock())
    with lock:return _fetch(record,cache,attempts=attempts)


def _fetch(record, cache, *, attempts=3):
    expected=record['sha256']; size=int(record['bytes'])
    if len(expected)!=64 or any(c not in '0123456789abcdef' for c in expected) or size<0:
        raise ValueError('Invalid pinned download record')
    cache=Path(cache); cache.mkdir(parents=True,exist_ok=True)
    if cache.is_symlink(): raise ValueError('Preserve redirected download cache')
    file=cache/expected; part=cache/(expected+'.part'); owner=cache/(expected+'.owner.json')
    if any(p.is_symlink() for p in (file,part,owner)):raise ValueError('Preserve linked download file')
    if file.exists():
        if file.stat().st_size==size and sha(file)==expected:return file
        raise ValueError('Preserve changed verified download')
    if size==0:
        if expected!=hashlib.sha256(b'').hexdigest():raise ValueError('Invalid empty file identity')
        file.write_bytes(b'');return file
    # The checkpoint owns content bytes, independently of its immutable mirror.
    identity={'owner':'lotra-download-1','sha256':expected,'bytes':size}
    if owner.exists():
        prior=json.loads(owner.read_text())
        if any(prior.get(k)!=v for k,v in identity.items()):raise ValueError('Preserve another partial download')
    else:
        if part.exists():raise ValueError('Preserve unowned partial download')
        owner.write_text(json.dumps(identity),encoding='utf-8')
    if part.exists() and part.stat().st_size==size and sha(part)==expected:os.replace(part,file);return file
    if record.get('parts'):
        pieces=[fetch(item,cache,attempts=attempts) for item in record['parts']]
        if sum(p.stat().st_size for p in pieces)!=size:raise ValueError('Member part sizes differ')
        for _ in range(2):
            offset=part.stat().st_size if part.exists() else 0
            if offset>size:part.unlink();offset=0
            with part.open('ab' if offset else 'wb') as output:
                passed=0
                for piece in pieces:
                    length=piece.stat().st_size
                    skip=max(0,min(length,offset-passed));passed+=length
                    with piece.open('rb') as source:
                        source.seek(skip)
                        for block in iter(lambda:source.read(4*1024*1024),b''):output.write(block)
            if part.stat().st_size==size and sha(part)==expected:os.replace(part,file);return file
            part.unlink()  # Exact owned logical member; verified pieces remain cached.
        raise ValueError('Verified member pieces do not match the complete file')
    last=None
    for attempt in range(attempts):
        offset=part.stat().st_size if part.exists() else 0
        if offset==size and sha(part)==expected:os.replace(part,file);return file
        if offset>=size:part.unlink();offset=0  # Only our exact hash-addressed incomplete file.
        span=record.get('range')
        first=int(span['offset']) if span else 0
        whole=int(span['archive_bytes']) if span else size
        headers={'User-Agent':'lotraAI-installer/1.33.0'}
        if span or offset:headers['Range']='bytes='+str(first+offset)+'-'+(str(first+size-1) if span else '')
        request=urllib.request.Request(record['url'],headers=headers)
        try:
            transport=urllib.request.build_opener(urllib.request.ProxyHandler({})) if attempt and ('10061' in str(last) or 'refused' in str(last).lower()) else urllib.request.build_opener()
            with transport.open(request,timeout=60) as response:
                status=response.status
                if status==206:
                    content_range=response.headers.get('Content-Range','')
                    if not content_range.startswith('bytes '+str(first+offset)+'-') or content_range.rsplit('/',1)[-1]!=str(whole):
                        raise ValueError('Range response does not match the pinned resource')
                elif status==200 and not span:offset=0
                elif status==200:raise ValueError('Range required: refuse downloading an unchanged archive for one changed member')
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
