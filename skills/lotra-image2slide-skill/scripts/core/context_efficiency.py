"""Bounded context and content-addressed views, without reducing obligations."""
import hashlib,io
from .common import canonical,identity,digest,read_json,write_json,safe_path

VERSION='context-storage-1'

def accounting(value):
    data=canonical(value)
    return {'characters':len(data.decode('utf-8')),'utf8_bytes':len(data),'tokens':None,
        'token_basis':'Unavailable unless supplied by hash-bound provider usage; text size is not a token count'}

def telemetry(state,full,display):
    row=state.setdefault('telemetry',{})
    if row.get('context_schema')!=VERSION:
        # Before this version packet_chars was incremented with UTF-8 bytes.
        # Preserve that historical value under its actual unit.
        row['legacy_packet_bytes']=row.get('packet_chars',0)
        row.update(context_schema=VERSION,packet_chars=0,packet_bytes=0,packet_count=0,full_packet_chars=0,full_packet_bytes=0)
    original,current=accounting(full),accounting(display)
    row['packet_chars']+=current['characters'];row['packet_bytes']+=current['utf8_bytes'];row['packet_count']+=1
    row['full_packet_chars']+=original['characters'];row['full_packet_bytes']+=original['utf8_bytes']

def crop_file(task,crop):
    """Same decoded pixels reuse one verified lossless task-local PNG."""
    from PIL import __version__ as pillow_version
    key=identity({'pixels':hashlib.sha256(crop.tobytes()).hexdigest(),'size':list(crop.size),
        'mode':crop.mode,'pillow':pillow_version,'encoding':'lossless-png-6','version':VERSION})
    png=safe_path(task,'views/content/'+key+'.png');manifest=safe_path(task,'views/content/'+key+'.json')
    if manifest.exists():
        ref=read_json(manifest)
        if ref.get('identity')!=key or not png.is_file() or digest(png)!=ref['sha256']:
            raise ValueError('Stored observation crop changed; retain evidence and regenerate under a new valid identity')
        return png,True
    stream=io.BytesIO();crop.save(stream,format='PNG',compress_level=6);data=stream.getvalue()
    if png.exists() and png.read_bytes()!=data:raise ValueError('Content-addressed crop collision')
    png.parent.mkdir(parents=True,exist_ok=True)
    if not png.exists():png.write_bytes(data)
    write_json(manifest,{'identity':key,'sha256':digest(png),'pixels':hashlib.sha256(crop.tobytes()).hexdigest()})
    return png,False

def bounded_output(task,result,budget=6000):
    if type(budget) is not int or not 1000<=budget<=16000:raise ValueError('Bounded output characters required')
    from .packet_compaction import compact
    return compact(task,result,budget)
