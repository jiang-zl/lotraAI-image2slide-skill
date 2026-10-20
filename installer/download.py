"""Finite, resumable, hash-addressed downloads; no model participation."""
import hashlib
import json
import os
import time
import threading
import urllib.error
import urllib.request
import urllib.parse
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def sha(file):
    h=hashlib.sha256()
    with Path(file).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''): h.update(block)
    return h.hexdigest()


_LOCKS={}
_LOCK_GUARD=threading.Lock()


def github_asset_api(url, size):
    """Resolve the exact public release asset; content pins remain unchanged."""
    parsed=urllib.parse.urlsplit(url)
    parts=parsed.path.strip('/').split('/')
    if parsed.scheme!='https' or parsed.netloc!='github.com' or parsed.query or len(parts)!=6 or parts[2:4]!=['releases','download']:
        return None
    repo='/'.join(parts[:2])
    if repo not in ('jiang-zl/lotraAI-image2slide-skill','jiang-zl/lotraAI-image2slide-skill-runtime'):
        return None
    tag,name=map(urllib.parse.unquote,parts[4:])
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def read(endpoint):
        request=urllib.request.Request('https://api.github.com/repos/'+repo+endpoint,
            headers={'User-Agent':'lotraAI-installer','Accept':'application/vnd.github+json'})
        with opener.open(request,timeout=20) as response:
            data=response.read(4*1024*1024+1)
        if len(data)>4*1024*1024:raise ValueError('GitHub asset metadata exceeds byte limit')
        return json.loads(data)
    release=read('/releases/tags/'+urllib.parse.quote(tag,safe=''))
    if release.get('tag_name')!=tag:raise ValueError('GitHub fallback release differs')
    for page in range(1,11):
        assets=read('/releases/'+str(int(release['id']))+'/assets?per_page=100&page='+str(page))
        matches=[a for a in assets if a.get('name')==name]
        if matches:
            if len(matches)!=1 or matches[0].get('size')!=size or matches[0].get('state')!='uploaded':
                raise ValueError('GitHub fallback asset identity differs')
            return 'https://api.github.com/repos/'+repo+'/releases/assets/'+str(int(matches[0]['id']))
        if len(assets)<100:return None
    raise ValueError('GitHub release asset pagination exceeds finite limit')


def archive_member(archive,name,record,cache):
    """Seed the common content cache from a local verified package, resumably."""
    expected=record['sha256'];size=int(record['bytes'])
    if len(expected)!=64 or any(c not in '0123456789abcdef' for c in expected) or size<0:raise ValueError('Invalid member identity')
    with _LOCK_GUARD:lock=_LOCKS.setdefault(expected,threading.Lock())
    with lock:
        cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
        file=cache/expected;part=cache/(expected+'.part');owner=cache/(expected+'.owner.json')
        if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (cache,file,part,owner)):
            raise ValueError('Preserve redirected content cache')
        if file.exists():
            if file.stat().st_size==size and sha(file)==expected:return file
            raise ValueError('Preserve changed verified member')
        identity={'owner':'lotra-download-1','sha256':expected,'bytes':size}
        if owner.exists():
            prior=json.loads(owner.read_text())
            if any(prior.get(k)!=v for k,v in identity.items()):raise ValueError('Preserve another partial member')
        else:
            if part.exists():raise ValueError('Preserve unowned partial member')
            owner.write_text(json.dumps(identity),encoding='utf-8')
        for attempt in range(2):
            offset=part.stat().st_size if part.exists() else 0
            if offset>size:part.unlink();offset=0
            with zipfile.ZipFile(archive) as package:
                if package.getinfo(name).file_size!=size:raise ValueError('Local member size differs')
                with package.open(name) as source,part.open('ab' if offset else 'wb') as output:
                    source.seek(offset)
                    for block in iter(lambda:source.read(4*1024*1024),b''):output.write(block)
            if part.stat().st_size==size and sha(part)==expected:os.replace(part,file);return file
            part.unlink()  # The exact content identity owns this partial.
        raise ValueError('Local archive member differs from the release')


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
        if record.get('assembly')=='ordered-release-parts':
            with ThreadPoolExecutor(max_workers=2) as workers:
                pieces=list(workers.map(lambda item:fetch(item,cache,attempts=attempts),record['parts']))
        else:pieces=[fetch(item,cache,attempts=attempts) for item in record['parts']]
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
    last=None;url=record['url'];api_tried=False
    for attempt in range(attempts):
        offset=part.stat().st_size if part.exists() else 0
        if offset==size and sha(part)==expected:os.replace(part,file);return file
        if offset>=size:part.unlink();offset=0  # Only our exact hash-addressed incomplete file.
        span=record.get('range')
        first=int(span['offset']) if span else 0
        whole=int(span['archive_bytes']) if span else size
        headers={'User-Agent':'lotraAI-installer'}
        if url.startswith('https://api.github.com/'):
            headers['Accept']='application/octet-stream'
        if span or offset:headers['Range']='bytes='+str(first+offset)+'-'+(str(first+size-1) if span else '')
        request=urllib.request.Request(url,headers=headers)
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
        if attempt+1<attempts:
            if not api_tried:
                api_tried=True
                try:
                    alternate=github_asset_api(record['url'],whole)
                    if alternate:url=alternate
                except (OSError,ValueError,KeyError,TypeError):pass
            time.sleep(min(2**attempt,4))
    raise RuntimeError('DOWNLOAD_LIMIT_REACHED: '+str(last)+'; verified checkpoints and owned partial retained')
