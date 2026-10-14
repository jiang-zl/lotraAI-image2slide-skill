"""Project-local, offline OCR routing with verified engines and real probes."""
import os, platform, subprocess, sys, time
from pathlib import Path
from .common import digest,identity,read_json,write_json,safe_path

VERSION='ocr-runtime-1'

def worker_identity():
    root=Path(__file__).resolve().parents[1]
    return identity({name:digest(root/name) for name in ('ocr_infer.py','core/ocr_geometry.py',
        'core/source_contract.py','core/common.py','core/worker_process.py')})

def readiness_tiers(host,provider):
    memory=host.get('ram_available_mib') or 0
    minimum={'tiny':1280,'small':1792,'medium':4096}
    gpu_free=max((r.get('free_mib',0) for r in host.get('gpus',[])),default=0)
    return [tier for tier in ('tiny','small','medium') if memory>=minimum[tier]
        and (provider=='CPUExecutionProvider' or gpu_free>=(4096 if tier=='medium' else 1024))]

def descriptor(project):
    project=Path(project).resolve();path=project/'.lotraAI-build/toolchain/ocr-runtime.json'
    key=('windows' if platform.system()=='Windows' else 'linux' if platform.system()=='Linux' else 'macos')+'-'+platform.machine().lower()+'-cp'+str(sys.version_info.major)+str(sys.version_info.minor)
    local=path.with_name('ocr-runtime-'+key+'.json')
    return local if local.is_file() else path

def core_profile(project):
    """Drawing prerequisites do not depend on OCR weights/provider readiness."""
    project=Path(project).resolve();path=descriptor(project)
    core_path=path.with_name(path.name.replace('ocr-runtime','core-runtime'))
    if core_path.is_file():path=core_path
    if not path.is_file():raise ValueError('Prepare the shipped complete project runtime')
    value=read_json(path);engine=safe_path(project,value['engine']['path'])
    if digest(engine)!=value['engine']['sha256']:raise ValueError('Project engine changed')
    ref=value.get('core_readiness',{});probe=safe_path(project,ref.get('path',''))
    if not probe.is_file() or digest(probe)!=ref.get('sha256') or read_json(probe).get('status')!='CORE_INFERENCE_AND_SVG_RENDER_EXECUTED':
        raise ValueError('Complete numeric/SVG runtime probe is missing or changed')
    return value

def hardware():
    result={'platform':platform.system(),'machine':platform.machine(),'cpu_threads':os.cpu_count(),
            'ram_available_mib':None,'gpus':[]}
    try:
        if platform.system()=='Windows':
            import ctypes
            class Memory(ctypes.Structure):
                _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(k,ctypes.c_ulonglong) for k in
                    ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
            mem=Memory();mem.length=ctypes.sizeof(mem)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):result['ram_available_mib']=mem.available/1048576
        elif platform.system()=='Linux':
            for line in Path('/proc/meminfo').read_text().splitlines():
                if line.startswith('MemAvailable:'):result['ram_available_mib']=int(line.split()[1])/1024
        elif platform.system()=='Darwin':
            import re
            data=subprocess.run(['vm_stat'],capture_output=True,text=True,timeout=5,check=True).stdout
            page=int(re.search(r'page size of (\d+) bytes',data).group(1))
            counts={k:int(v) for k,v in re.findall(r'([^\n:]+):\s+(\d+)\.',data)}
            result['ram_available_mib']=sum(counts.get(k,0) for k in ('Pages free','Pages inactive','Pages purgeable'))*page/1048576
    except (OSError,AttributeError):pass
    try:
        completed=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,memory.free','--format=csv,noheader,nounits'],
            capture_output=True,text=True,timeout=10)
        if completed.returncode==0:
            for line in completed.stdout.splitlines():
                name,total,free=[v.strip() for v in line.rsplit(',',2)]
                result['gpus'].append({'name':name,'total_mib':int(total),'free_mib':int(free)})
    except (OSError,ValueError,subprocess.TimeoutExpired):pass
    return result

def choose_provider(host,verified,preference='auto',request=None):
    """Choose only probed language/model/device routes inside a finite budget.

    Calibration is a conservative policy based on the packaged OCR benchmark,
    not a claim that thread throttling emulates every physical weak device.
    Missing resource/probe information selects CPU or source-only host vision.
    """
    from .source_contract import finite
    request=request or {};finite(request,'OCR.request')
    if preference not in ('auto','cpu','gpu'):raise ValueError('OCR preference must be auto/cpu/gpu')
    deadline=request.get('deadline_seconds',30.)
    if type(deadline) not in (int,float) or not 0<deadline<=240:raise ValueError('OCR deadline must be finite and in (0,240] seconds')
    memory=host.get('ram_available_mib') or 0;threads=host.get('cpu_threads') or 1
    ready={p:v for p,v in verified.items() if v.get('status')=='INFERENCE_EXECUTED'}
    supported=lambda p: set(ready.get(p,{}).get('tiers',['medium']))
    gpu_free=max((g.get('free_mib',0) for g in host.get('gpus',[])),default=0)
    gpu_total=max((g.get('total_mib',0) for g in host.get('gpus',[])),default=0)
    provider='CPUExecutionProvider'
    if preference!='cpu' and memory>=2048 and gpu_free>=1024:
        provider=next((p for p in ('CUDAExecutionProvider','DmlExecutionProvider','CoreMLExecutionProvider') if p in ready),provider)
    pixels=request.get('estimated_pixels',1000000)
    if type(pixels) not in (int,float) or pixels<=0:raise ValueError('OCR pixel estimate must be positive')
    if memory<768 or provider not in ready:
        return {'provider':'host_vision','tier':'host_vision','model':None,'recognition_batch':1,'crop_batch':1,
            'deadline_seconds':deadline,'reason':'No verified local route fits the available memory; use source-only host vision'}
    tier='tiny' if memory<2048 or threads<=2 or deadline<=2 else 'small'
    medium_time=(1.5 if provider!='CPUExecutionProvider' else 80.)*max(.05,pixels/1000000)
    if request.get('quality')=='difficult' and memory>=4096 and deadline>=medium_time*1.5 and (provider=='CPUExecutionProvider' or gpu_free>=4096 and gpu_total>=6144):tier='medium'
    if request.get('language','').lower().split('-')[0] in ('ja','jpn','japanese') and tier=='tiny':tier='small'
    minimum={'tiny':1280,'small':1792,'medium':3072}
    if memory<minimum[tier] or tier not in supported(provider):
        fallback=[t for t in ('small','tiny') if t in supported('CPUExecutionProvider') and memory>=minimum[t]
            and not (t=='tiny' and request.get('language','').lower().split('-')[0] in ('ja','jpn','japanese'))]
        if not fallback:return {'provider':'host_vision','tier':'host_vision','model':None,'recognition_batch':1,'crop_batch':1,
            'deadline_seconds':deadline,'reason':'Probed tiers do not fit source language and current resource budget'}
        provider='CPUExecutionProvider';tier=fallback[0]
    return {'provider':provider,'tier':tier,'model':'PP-OCRv6-'+tier,'crop_batch':1,
        'recognition_batch':4 if memory>=8192 and provider!='CPUExecutionProvider' and gpu_free>=8192 else 1,
        'threads':max(1,min(4,threads-1 if threads>2 else 1)),
        'max_pixels':2000000 if memory<4096 else 8000000,'max_side_len':2048 if memory<2048 else 4096,
        'deadline_seconds':deadline,'reason':'Language-compatible, inference-probed tier within current RAM, device and latency policy',
        'calibration':'PP-OCRv6 multi-tier benchmark; fresh hardware budgets are not physical-device equivalence'}


def profile(project,required=True):
    project=Path(project).resolve();path=descriptor(project)
    if not path.is_file():
        if required:raise ValueError('OCR runtime is not prepared; use offline runtime-bootstrap with the shipped companion bundle')
        return None
    value=read_json(path)
    if value.get('schema')!=VERSION:raise ValueError('Unsupported OCR runtime descriptor')
    for key in ('engine','models'):
        if not value.get(key):raise ValueError('OCR runtime descriptor lacks '+key)
    if not isinstance(value.get('probes'),dict):raise ValueError('OCR runtime descriptor lacks typed probes')
    if not value['probes'] and value.get('readiness')!='SOURCE_ONLY_HOST_ROUTE':raise ValueError('Empty OCR probes need an explicit host-only readiness diagnosis')
    engine=safe_path(project,value['engine']['path'])
    if digest(engine)!=value['engine']['sha256']:raise ValueError('OCR engine launcher changed')
    worker=Path(__file__).resolve().parents[1]/'ocr_infer.py'
    if value.get('worker_sha256')!=digest(worker):raise ValueError('OCR worker changed; rerun the offline readiness probe before activating it')
    if value.get('version')=='1.14.0' and value.get('worker_identity')!=worker_identity():
        raise ValueError('OCR worker dependencies changed; rerun actual offline readiness probes')
    for name,model in value['models'].items():
        target=safe_path(project,model['path'])
        if not target.is_file() and value.get('companion_path'):
            # Repair only an absent content-addressed resource from the
            # registered immutable local release; preserve corrupt files.
            bundle=Path(value['companion_path']).resolve();manifest=read_json(bundle/'Manifest.json')
            if digest(bundle/'Manifest.json')!=value['companion_sha256']:raise ValueError('Registered companion changed')
            source=safe_path(bundle,manifest['models'][name]['path'])
            if digest(source)!=model['sha256']:raise ValueError('Companion repair resource changed')
            target.parent.mkdir(parents=True,exist_ok=True);__import__('shutil').copyfile(source,target)
        if digest(target)!=model['sha256']:raise ValueError('OCR model changed')
    probes={}
    for key,record in value['probes'].items():
        provider=record.get('provider',key);tier=record.get('tier','medium')
        probe=read_json(safe_path(project,record['path']))
        if digest(safe_path(project,record['path']))!=record['sha256'] or probe['requested_provider']!=provider:
            raise ValueError('OCR inference probe identity changed')
        if probe.get('model_hashes')!={k:v['sha256'] for k,v in value['models'].items() if k in ('det-'+tier,'rec-'+tier)}:
            raise ValueError('OCR probe belongs to different models')
        ready=probes.setdefault(provider,{'status':'INFERENCE_EXECUTED','tiers':[],'measurements':{}})
        ready['tiers'].append(tier);ready['measurements'][tier]=probe.get('seconds')
    value['validated_probes']=probes
    return value

def _host_only(task,state,reason,failures=None):
    data={'status':'SOURCE_ONLY_HOST_VISION_REQUIRED','source_hash':state['source']['sha256'],
        'reason':reason,'failures':failures or [],'next':'source-reading discover: read program-generated original-only views with the available multimodal host; no extra API key'}
    file=task/'source/ocr'/identity(data)/'failure.json';write_json(file,data)
    return {**data,'path':file.relative_to(task).as_posix(),'sha256':digest(file)}


def collect(task,request=None):
    from . import agent_runtime as a
    from .ocr_geometry import plan_inputs
    task,state=a._state(task);request=request or {};project=Path(state['project']).resolve()
    try:ready=profile(project)
    except (ValueError,OSError,KeyError) as error:return _host_only(task,state,str(error))
    host=hardware();source=safe_path(task,state['source']['path'])
    if digest(source)!=state['source']['sha256']:raise ValueError('OCR original source changed')
    if ready.get('host_platform')=='Windows' and platform.system()!='Windows':
        host={**ready['host'],'ram_available_mib':None};request={**request,'preference':'cpu'}
    inputs=request.get('items') or [{'id':task.name,'roi':[0,0,*state['source_size']],'scale':1.}]
    estimated=sum(r.get('roi',[0,0,*state['source_size']])[2]*r.get('roi',[0,0,*state['source_size']])[3]*r.get('scale',1.)**2 for r in inputs)
    request={**request,'estimated_pixels':estimated}
    route=choose_provider(host,ready['validated_probes'],request.get('preference','auto'),request)
    if route['provider']=='host_vision':return _host_only(task,state,route['reason'])
    dependencies={'source':state['source'],'inputs':inputs,'route':route,'runtime':identity(ready),
                  'worker':worker_identity()}
    folder=task/'source/ocr'/identity(dependencies);folder.mkdir(parents=True,exist_ok=True)
    output=folder/'result.json';engine=safe_path(project,ready['engine']['path']);worker=Path(__file__).resolve().parents[1]/'ocr_infer.py'
    if ready.get('host_platform')=='Windows':
        from .office_bridge import _host_path
        host_path=_host_path
    else:host_path=lambda p:str(p)
    if not output.is_file() or request.get('refresh'):
        failures=[];deadline=time.monotonic()+route['deadline_seconds'];actual_route=route;succeeded=False
        for attempt in range(2):
            remaining=deadline-time.monotonic()
            if remaining<=.1:break
            if attempt:
                fresh=hardware()
                actual_route=choose_provider(fresh,ready['validated_probes'],'cpu',
                    {**request,'deadline_seconds':min(remaining,240),'quality':'balanced'})
                if actual_route['provider']=='host_vision':break
            try:
                tiles=plan_inputs(inputs,state['source_size'],actual_route);tier=actual_route['tier']
                models={k:{**v,'path':host_path(safe_path(project,v['path']))} for k,v in ready['models'].items() if k in ('det-'+tier,'rec-'+tier)}
                if len(models)!=2:raise ValueError('Complete selected OCR tier is not installed')
                spec={k:actual_route[k] for k in ('provider','tier','recognition_batch','threads','max_pixels','max_side_len')}
                spec.update(models=models,images=[{**r,'path':host_path(source),'sha256':state['source']['sha256']} for r in tiles])
                specfile=folder/('request-'+str(attempt)+'.json');write_json(specfile,spec)
                limit=remaining*.6 if attempt==0 and actual_route['provider']!='CPUExecutionProvider' else remaining
                from .worker_process import run as managed_run
                result=managed_run([str(engine),'-X','utf8','-B',host_path(worker),'--request',host_path(specfile),'--output',host_path(output)],
                    capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=limit)
                if result.returncode:raise RuntimeError(result.stderr[-2400:])
                value=read_json(output)
                if (value.get('status')!='INFERENCE_EXECUTED' or value.get('requested_provider')!=actual_route['provider']
                    or value.get('model_hashes')!={k:v['sha256'] for k,v in models.items()}):raise ValueError('OCR worker returned a different route or model identity')
                value.update(route={**actual_route,'failures':failures,'actual_provider':value['requested_provider']},
                             source_hash=state['source']['sha256'],dependencies_hash=identity(dependencies))
                write_json(output,value);succeeded=True;break
            except (RuntimeError,OSError,ValueError,subprocess.TimeoutExpired) as error:
                failures.append({'attempt':attempt,'provider':actual_route['provider'],'tier':actual_route['tier'],
                    'reason':str(error),'kind':'TIMEOUT' if isinstance(error,subprocess.TimeoutExpired) else type(error).__name__})
                write_json(folder/'failure.json',{'status':'LOCAL_OCR_ATTEMPT_FAILED','source_hash':state['source']['sha256'],'failures':failures})
                if actual_route['provider']=='CPUExecutionProvider':break
        else:pass
        if not succeeded:
            return _host_only(task,state,'Bounded local OCR routes exhausted; original-only host reading remains available',failures)
    value=read_json(output)
    if value.get('dependencies_hash')!=identity(dependencies) or value.get('source_hash')!=state['source']['sha256'] or any(r['image_hash']!=state['source']['sha256'] for r in value['items']):
        raise ValueError('OCR source/runtime binding mismatch')
    return {'status':'SOURCE_OCR_CANDIDATE_ANCHORS','path':output.relative_to(task).as_posix(),'sha256':digest(output),
        'source_hash':state['source']['sha256'],'provider':value['requested_provider'],'model':'PP-OCRv6-'+value.get('tier',value['route']['tier']),
        'line_count':sum(len(i['lines']) for i in value['items']),'limits':value['limits']}
