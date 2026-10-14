"""Offline companion installer. Never downloads or changes global packages."""
import json,platform,subprocess,sys,venv
from pathlib import Path
from .common import ROOT,digest,identity,read_json,write_json,safe_path

def prepare(project,bundle,native_libraries=None):
    from .ocr_runtime import VERSION,hardware,choose_provider,worker_identity,readiness_tiers
    project=Path(project).resolve();bundle=Path(bundle).resolve()
    if not project.is_dir() or not bundle.is_dir():raise ValueError('Existing project and extracted shipped runtime companion are required')
    manifest=read_json(bundle/'Manifest.json')
    if manifest.get('schema')!='lotra-runtime-companion-2' or manifest.get('version')!='1.14.0':
        raise ValueError('Unsupported runtime companion')
    for relative,record in manifest['files'].items():
        path=safe_path(bundle,relative)
        if digest(path)!=record['sha256']:raise ValueError('Runtime companion hash mismatch: '+relative)
    key=('windows' if platform.system()=='Windows' else 'linux' if platform.system()=='Linux' else 'macos')+'-'+platform.machine().lower()+'-cp'+str(sys.version_info.major)+str(sys.version_info.minor)
    spec=manifest['environments'].get(key)
    if spec is None:raise ValueError('This Python/platform is not shipped in the companion: '+key+'; use an explicitly supported host engine or source-only host vision, never a manual missing-model workaround')
    bundle_hash=digest(bundle/'Manifest.json')
    runtime=safe_path(project,'.lotraAI-build/toolchain/runtime-v1.14.0-'+key+'-'+bundle_hash[:12])
    marker=runtime/'Installed-companion.json'
    intent=runtime/'Install-intent.json'
    resume=runtime.exists() and not marker.exists()
    if resume and (not intent.is_file() or read_json(intent)!={'bundle_sha256':bundle_hash,'environment':key}):
        raise ValueError('Preserve an incomplete/foreign runtime without this exact owned install intent')
    if not marker.exists():
        # Some supported Linux distributions omit ensurepip. Bootstrap from
        # the shipped, hash-verified pip wheel, without apt or network access.
        runtime.mkdir(parents=True,exist_ok=True)
        write_json(intent,{'bundle_sha256':bundle_hash,'environment':key})
        venv.EnvBuilder(with_pip=False).create(runtime)
        engine=runtime/('Scripts/python.exe' if platform.system()=='Windows' else 'bin/python')
        pip=safe_path(bundle,spec['bootstrap_pip'])
        bootstrap='import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_module("pip",run_name="__main__")'
        args=[str(engine),'-c',bootstrap,str(pip),'--isolated','install','--no-index','--disable-pip-version-check','--only-binary=:all:','--require-hashes',
              '--find-links',str(safe_path(bundle,spec['wheels'])),'-r',str(safe_path(bundle,spec['lock']))]
        if resume:args.append('--force-reinstall')
        try:completed=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=1200)
        except subprocess.TimeoutExpired as error:
            write_json(runtime/'Offline-install-log.json',{'status':'TIMEOUT','seconds':1200,'diagnosis':'Offline extraction exceeded the bounded install time; preserve this environment and its original companion identity'})
            raise ValueError('Offline installation timed out; preserved its environment and diagnostic log') from error
        write_json(runtime/'Offline-install-log.json',{'exit_code':completed.returncode,'stdout':completed.stdout[-9000:],'stderr':completed.stderr[-2500:]})
        if completed.returncode:raise ValueError('Offline OCR installation failed; preserved the diagnosed environment and log')
        write_json(marker,{'bundle_sha256':bundle_hash,'environment':key,'requirements':spec})
    elif read_json(marker)['bundle_sha256']!=bundle_hash:raise ValueError('Existing runtime belongs to another immutable companion')
    engine=runtime/('Scripts/python.exe' if platform.system()=='Windows' else 'bin/python')
    library_paths=[]
    for value in native_libraries or []:
        path=Path(value).resolve()
        if not path.is_dir():raise ValueError('Discovered native library directory missing')
        library_paths.append(str(path))
    # Probe the complete numeric/drawing/export Python stack, including the
    # actual Cairo shared library. A wheel install alone is never readiness.
    core_probe=runtime/'Core-readiness.json'
    probe_code='''import sys,os,json,io,importlib.metadata as M
sys.path.insert(0,sys.argv[2])
handles=[]
for value in sys.argv[3:]:
 os.environ['PATH']=value+os.pathsep+os.environ.get('PATH','')
 if hasattr(os,'add_dll_directory'):handles.append(os.add_dll_directory(value))
import pptx,lxml,jsonschema,openpyxl,numpy,scipy,skimage,fitz,fontTools,shapely
from core import svg_backend
from PIL import Image
svg=b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><circle cx="16" cy="16" r="10" fill="red"/></svg>'
data=svg_backend.svg2png(bytestring=svg,mode='portable')
im=Image.open(io.BytesIO(data)).convert('RGBA')
assert im.size==(32,32) and im.getpixel((16,16))[3]==255 and im.getpixel((0,0))[3]==0
with fitz.open(stream=svg_backend.svg2pdf(bytestring=svg,mode='portable'),filetype='pdf') as doc:
 assert len(doc)==1 and not doc[0].get_images() and len(doc[0].get_drawings())>0
names=['python-pptx','lxml','Pillow','jsonschema','openpyxl','numpy','scipy','scikit-image','PyMuPDF','fonttools','CairoSVG','Shapely','resvg_py']
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({'status':'CORE_INFERENCE_AND_SVG_RENDER_EXECUTED','packages':{n:M.version(n) for n in names},'svg_backend':svg_backend.backend(),'portable_svg_backend':svg_backend.backend('portable'),'svg_render':{'size':[32,32],'opaque_core':True,'transparent_exterior':True,'pdf_vector_paths':True}}),encoding='utf-8')
'''
    checked=subprocess.run([str(engine),'-X','utf8','-B','-c',probe_code,str(core_probe),str(ROOT/'scripts'),*library_paths],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
    if checked.returncode:
        write_json(runtime/'Core-readiness-failure.json',{'exit_code':checked.returncode,'stderr':checked.stderr[-3000:]})
        raise ValueError('Complete runtime probe failed; preserve diagnostics and route to available host libraries: '+checked.stderr[-1400:])
    models={}
    for name,ref in manifest['models'].items():
        source=safe_path(bundle,ref['path']);target=project/'.lotraAI-build/toolchain/model-store'/(ref['sha256']+'.onnx')
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():__import__('shutil').copyfile(source,target)
        if digest(target)!=ref['sha256']:raise ValueError('Existing content-addressed model cache changed')
        models[name]={'path':target.relative_to(project).as_posix(),'sha256':ref['sha256'],'bytes':target.stat().st_size}
    host=hardware();probes={};worker=ROOT/'scripts/ocr_infer.py';probe_dir=runtime/'probes';probe_dir.mkdir(exist_ok=True)
    fixture=safe_path(bundle,manifest['probe']['path']);source_hash=digest(fixture)
    providers=['CPUExecutionProvider']
    if platform.system()=='Windows':providers.append('DmlExecutionProvider')
    import time
    failures=[];probe_deadline=time.monotonic()+90
    for provider in providers:
      for tier in readiness_tiers(host,provider):
        chosen={k:v for k,v in models.items() if k in ('det-'+tier,'rec-'+tier)}
        if len(chosen)!=2:raise ValueError('Shipped matched OCR tier missing: '+tier)
        request={'models':{k:{**v,'path':str(safe_path(project,v['path']))} for k,v in chosen.items()},'provider':provider,'tier':tier,'threads':1,
            'images':[{'id':'multilingual-readiness','path':str(fixture),'sha256':source_hash,'scale':1.}]}
        request_file=probe_dir/(provider+'-'+tier+'-request.json');output=probe_dir/(provider+'-'+tier+'.json');write_json(request_file,request)
        try:
            remaining=probe_deadline-time.monotonic()
            if remaining<=.1:raise ValueError('Aggregate readiness latency budget exhausted; source-only host reading stays available')
            from .worker_process import run as managed_run
            completed=managed_run([str(engine),'-X','utf8','-B',str(worker),'--request',str(request_file),'--output',str(output)],
                capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=min(remaining,30))
            if completed.returncode:raise ValueError(completed.stderr[-2400:])
            result=read_json(output);text=' '.join(l['text'] for item in result['items'] for l in item['lines'])
            missing=[token for token in manifest['probe']['required_tokens'] if token not in text]
            if missing:raise ValueError('Multilingual fixture missing: '+str(missing))
            probes[provider+'@'+tier]={'provider':provider,'tier':tier,'path':output.relative_to(project).as_posix(),'sha256':digest(output)}
        except (ValueError,OSError,subprocess.TimeoutExpired) as error:
            failures.append({'provider':provider,'tier':tier,'reason':str(error)})
            write_json(probe_dir/'Failures.json',failures)
    profile={'schema':VERSION,'version':'1.14.0','host_platform':platform.system(),'host':host,
        'engine':{'path':engine.relative_to(project).as_posix(),'sha256':digest(engine)},
        'models':models,'probes':probes,'companion_sha256':bundle_hash,'companion_path':str(bundle),'environment':key,
        'worker_sha256':digest(worker),'worker_identity':worker_identity(),'acceleration_failures':failures,
        'readiness':'LOCAL_INFERENCE_ROUTES' if probes else 'SOURCE_ONLY_HOST_ROUTE',
        'native_libraries':library_paths,'core_readiness':{'path':core_probe.relative_to(project).as_posix(),'sha256':digest(core_probe)}}
    directory=project/'.lotraAI-build/toolchain'
    core_descriptor={k:v for k,v in profile.items() if k not in ('models','probes','worker_sha256','acceleration_failures')}
    write_json(directory/('core-runtime-'+key+'.json'),core_descriptor)
    write_json(directory/('ocr-runtime-'+key+'.json'),profile)
    # Host-specific descriptors coexist. The default remains a portable
    # compatibility entry; selecting a Linux engine cannot erase Windows proof.
    write_json(directory/'ocr-runtime.json',profile)
    from .ocr_runtime import profile as verified_profile
    route=choose_provider(host,verified_profile(project)['validated_probes'])
    return {'status':'OFFLINE_RUNTIME_READY','environment':key,'providers':sorted(probes),'selection':route,
        'models':{k:v['sha256'] for k,v in models.items()},'core_readiness':profile['core_readiness'],
        'ocr_failures':failures,'ocr_readiness':profile['readiness'],'network_requests':0,'global_packages_changed':False}
