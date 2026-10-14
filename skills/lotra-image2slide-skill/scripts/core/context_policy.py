"""Validated local budgets; none of these values are quality thresholds."""
from .common import ROOT, read_json

def configuration():
    value=read_json(ROOT/'config/context-policy.json')
    if value.get('schema')!='context-policy-1':raise ValueError('Unknown managed context policy')
    cache=value['cache']
    for key,minimum,maximum in (('max_bytes',1048576,1073741824),('max_entries',16,100000),
                               ('decoded_image_bytes',1048576,536870912),('native_snapshots',1,16)):
        if type(cache.get(key)) is not int or not minimum<=cache[key]<=maximum:
            raise ValueError('Bounded cache capacity required: '+key)
    return value

def image_budget():
    cap=configuration()['cache']['decoded_image_bytes']
    available=None
    try:
        import sys
        if sys.platform=='win32':
            import ctypes
            class Memory(ctypes.Structure):
                _fields_=[('length',ctypes.c_uint32),('load',ctypes.c_uint32)]+[(k,ctypes.c_uint64) for k in ('physical','available','page','page_available','virtual','virtual_available','extended')]
            memory=Memory();memory.length=ctypes.sizeof(memory)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):available=memory.available
        elif sys.platform.startswith('linux'):
            from pathlib import Path
            for line in Path('/proc/meminfo').read_text().splitlines():
                if line.startswith('MemAvailable:'):available=int(line.split()[1])*1024
            limit=Path('/sys/fs/cgroup/memory.max');used=Path('/sys/fs/cgroup/memory.current')
            if limit.exists() and used.exists() and limit.read_text().strip()!='max':
                cgroup=max(0,int(limit.read_text())-int(used.read_text()))
                available=min(available,cgroup) if available is not None else cgroup
    except (OSError,ValueError,AttributeError):pass
    return min(cap,max(1048576,int(available)//16)) if available is not None else min(cap,33554432)
