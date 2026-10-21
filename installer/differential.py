"""Runtime-repository install entry: file delta, shared content cache, scoped rollback."""
import argparse, hashlib, json, os, platform, shlex, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from install import (read_json,write_json,within,sha,same_bytes,platform_key,register,
                     acquire_lock,readable_windows_path)
from download import fetch,archive_member
from file_sync import prepare,apply,rollback,put,reuse,owned


def runtime_checkpoint(project,state,key,math_record):
    names={'.lotraAI-build/Portable-renderer.json','.lotraAI-build/toolchain/core-runtime-'+key+'.json',
           '.lotraAI-build/toolchain/ocr-runtime-'+key+'.json','.lotraAI-build/toolchain/ocr-runtime.json',
           '.lotraAI-build/toolchain/install-code-'+key+'.json', '.lotraAI-build/Presentation-backend.json'}
    math_marker='.lotraAI-build/toolchain/LibreOffice-'+math_record['version']+'-'+key+'/lotra-runtime.json'
    if within(project,math_marker).is_file():names.add(math_marker)
    for name in list(names):
        file=within(project,name)
        if not file.is_file() or 'runtime-' not in name:continue
        profile=read_json(file)
        refs=[profile.get('core_readiness',{})]+list(profile.get('probes',{}).values())
        for ref in refs:
            path=ref.get('path','')
            if not path:continue
            if not path.startswith('.lotraAI-build/toolchain/') or not path.endswith('.json'):raise ValueError('Unexpected runtime proof path')
            proof=within(project,path);names.add(path)
            if proof.is_file() and ref.get('sha256') and sha(proof)!=ref['sha256']:raise ValueError('Preserve changed runtime proof')
            if proof.parent.name=='probes':
                for sibling in sorted(proof.parent.glob('*.json'))[:256]:names.add(sibling.relative_to(project).as_posix())
    original={}
    for name in sorted(names):
        file=within(project,name)
        original[name]=sha(file) if file.is_file() else None
        if file.is_file():put(within(state,'runtime-preimage/'+name),file.read_bytes())
    applied=state/'Apply.json'
    write_json(state/'Runtime-preimages.json',{'status':'PENDING','files':original,'prior_apply_sha256':sha(applied) if applied.exists() else None})


def restore_runtime(project,state):
    record=state/'Runtime-preimages.json'
    if not record.exists():return
    saved=read_json(record)
    if saved['status']!='PENDING':return
    applied=state/'Apply.json'
    if applied.exists() and read_json(applied)['status']=='COMPLETE' and sha(applied)!=saved.get('prior_apply_sha256'):
        write_json(record,{**saved,'status':'COMPLETE'});return
    for name,expected in saved['files'].items():
        target=within(project,name)
        if expected is not None:
            original=within(state,'runtime-preimage/'+name)
            if sha(original)!=expected:raise ValueError('Preserve changed runtime preimage')
            put(target,original.read_bytes())
        elif target.exists():target.unlink()
    write_json(record,{**saved,'status':'ROLLED_BACK'})


def finish_runtime(state):
    record=state/'Runtime-preimages.json'
    if record.exists():write_json(record,{**read_json(record),'status':'COMPLETE'})


def companion(project,spec,key,cache,local_archive=None):
    descriptor=within(project,'.lotraAI-build/toolchain/core-runtime-'+key+'.json')
    prior=read_json(descriptor) if descriptor.exists() else {}
    old=Path(prior.get('companion_path','')).resolve() if prior.get('companion_path') else None
    if old and (not old.is_relative_to(project) or old.is_symlink()):raise ValueError('Preserve external companion')
    old_manifest=read_json(old/'Manifest.json') if old and (old/'Manifest.json').is_file() else {}
    new=spec['manifest']
    # Old full companions and new platform companions compare by selected bytes,
    # not by their ZIP wrapper or publication version.
    files=spec['files']
    existing={r['sha256']:within(old,n) for n,r in old_manifest.get('files',{}).items()} if old else {}
    if old and all(same_bytes(within(old,name),record) for name,record in files.items()):
        old_env=old_manifest.get('environments',{}).get(key)
        if old_env==new['environments'][key]:return old,prior,True
    # Only a fresh installation obtains the complete selected-platform package.
    # Updates always retain member-level retrieval; a changed ZIP wrapper does
    # not make unchanged installed resources eligible for another download.
    package=spec.get('archive')
    if package and not (local_archive and local_archive.is_file()):
        cached=within(cache,package['sha256'])
        if same_bytes(cached,package):local_archive=cached
        elif not old_manifest:local_archive=fetch(package,cache)
    target=within(project,'.lotraAI-build/toolchain/companion-'+key+'-'+spec['manifest_sha256'][:16])
    target.mkdir(parents=True,exist_ok=True)
    def obtain(item):
        name,record=item;destination=within(target,name)
        if destination.exists():
            if not same_bytes(destination,record):raise ValueError('Preserve changed companion file')
            return
        source=within(old,name) if old else None
        if not source or not same_bytes(source,record):source=existing.get(record['sha256'])
        if not source or not same_bytes(source,record):
            if local_archive and local_archive.is_file():
                source=archive_member(local_archive,name,record,cache)
            else:source=fetch(record,cache)
        reuse(source,destination)
    with ThreadPoolExecutor(max_workers=4) as workers:list(workers.map(obtain,files.items()))
    raw=(json.dumps(new,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    if hashlib.sha256(raw).hexdigest()!=spec['manifest_sha256']:raise ValueError('Companion catalog identity differs')
    put(within(target,'Manifest.json'),raw)
    return target,prior,False


def runtime(project,candidate,root,spec,key,cache,workspace):
    local_archive=root.parent/spec['offline_archive'] if spec.get('offline_archive') else None
    body,prior,reused=companion(project,spec,key,cache,local_archive)
    engine=within(project,prior['engine']['path']) if prior.get('engine') else None
    proof=prior.get('core_readiness',{})
    core=within(project,proof['path']) if proof.get('path') else None
    code_file=within(project,'.lotraAI-build/toolchain/install-code-'+key+'.json')
    code=read_json(code_file) if code_file.exists() else {}
    if (reused and engine and engine.is_file() and same_bytes(engine,{'bytes':engine.stat().st_size,'sha256':prior['engine']['sha256']})
            and core and core.is_file() and sha(core)==proof.get('sha256') and code.get('sha256')==spec['install_code_sha256']):
        return {'status':'OFFLINE_RUNTIME_READY','engine':prior['engine'],'core_readiness':proof,
                'environment':key,'resource_reused':True,'revalidated':False}
    out=within(workspace,'Runtime-readiness.json')
    log=within(workspace,'runtime-bootstrap.log')
    with log.open('wb') as stream:
        result=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(root/'bootstrap.py'),
                               '--project',str(project),'--skill',str(candidate),'--companion',str(body),'--out',str(out)],
                              stdout=stream,stderr=subprocess.STDOUT,timeout=1440)
    if result.returncode:raise ValueError('Runtime preparation failed; see '+str(log))
    facts=read_json(out)
    if facts.get('status')!='OFFLINE_RUNTIME_READY':raise ValueError('Core runtime is not ready')
    put(code_file,(json.dumps({'sha256':spec['install_code_sha256']},sort_keys=True)+'\n').encode())
    return facts


def math_runtime(project,bundle,key,cache,workspace,skill):
    from renderer_install import install_renderer,verify_backend
    record=bundle.get('math_renderers',{}).get(key)
    if not record:raise ValueError('This platform has core resources but no supplied Math package: '+key)
    destination=within(project,'.lotraAI-build/toolchain/LibreOffice-'+record['version']+'-'+key)
    marker=within(destination,'lotra-runtime.json')
    reuse_ready=False
    if marker.exists():
        previous=read_json(marker)
        if previous.get('sha256')!=record['sha256']:raise ValueError('Preserve different Math resources')
        reuse_ready=all(within(destination,n).is_file() for n in (record['executable'],record['uno_python']))
    if not reuse_ready:
        local=workspace/record['path']
        archive=local if same_bytes(local,record) else fetch(record,cache)
        destination_file=within(workspace,record['path'])
        if not destination_file.exists():reuse(archive,destination_file)
    facts=install_renderer(workspace,project,bundle,key)
    if facts.get('status')!='INSTALLED_NOT_TESTED':raise ValueError('Math resource preparation incomplete')
    backend=verify_backend(project,skill,workspace,key)
    facts.update(resource_reused=reuse_ready,render_status='NOT_RUN',backend=backend)
    return facts


def install(project,catalog,root,harness):
    project=project.resolve();key=platform_key()
    if not project.is_dir() or project in (Path.home().resolve(),Path(project.anchor)):raise ValueError('Choose a project directory')
    if catalog.get('schema')!='lotra-differential-release-1' or key not in catalog['platforms']:raise ValueError('Platform not in the release catalog')
    if key not in catalog['bundle'].get('math_renderers',{}):raise ValueError('Core platform exists; complete Math resources are not supplied for '+key)
    state=within(project,'.lotraAI-build/updates/'+catalog['release_id']);state.mkdir(parents=True,exist_ok=True)
    lock=acquire_lock(within(project,'.lotraAI-build/Install.lock'),{'bundle_id':'lotra-differential-install','environment':'project-wide'})
    target=within(project,'.agents/skills/lotra-image2slide-skill')
    canonical=target
    active=project/'.lotraAI-build/Active-skill.json'
    if not target.exists() and active.exists():
        selected=read_json(active)
        entry=selected.get('skill','')
        if selected.get('name')!='lotra-image2slide-skill':raise ValueError('Preserve another selected skill')
        if entry.startswith('../.agents/skills/lotra-image2slide-skill'):
            previous=within(project,entry.removeprefix('../')).parent
            if previous.exists():target=previous
    cache=within(project,'.lotraAI-build/downloads/sha256')
    metadata=('AGENTS.md','.lotraAI-build/Active-skill.json','.lotraAI-build/Bundle-install.json')
    touched=False;relocated=False;committed=False
    phase='SKILL_FILES';stages={'skill_files':'NOT_RUN','math_backend':'NOT_RUN','core_runtime':'NOT_RUN'}
    try:
        restore_runtime(project,state)
        relocation=state/'Relocation.json'
        if relocation.exists() and read_json(relocation)['status']=='MOVING':target=canonical;relocated=True
        rollback(target,state)
        recovered=state/'Apply.json'
        if recovered.exists() and read_json(recovered)['status']=='ROLLED_BACK' and (state/'Registration.json').exists():
            for name,existed in read_json(state/'Registration.json').items():
                p=within(project,name)
                if existed:put(p,within(state,'registration-preimage/'+name).read_bytes())
                elif p.exists():p.unlink()
        if relocated:
            previous=Path(read_json(relocation)['previous'])
            if previous.exists():raise ValueError('Preserve occupied prior skill path')
            canonical.rename(previous);target=previous;relocated=False
            write_json(relocation,{'status':'ROLLED_BACK','previous':str(previous)})
        candidate,plan=prepare(project,target,catalog['skill']['files'],state,root.parent)
        stages['skill_files']='VERIFIED'
        runtime_checkpoint(project,state,key,catalog['bundle']['math_renderers'][key])
        bundle=catalog['bundle']
        # Resolve unsupported optional-platform resources before touching the skill.
        math_record=bundle.get('math_renderers',{}).get(key)
        if math_record:
            local=root.parent/math_record['path']
            if same_bytes(local,math_record):
                linked=within(state,math_record['path'])
                if not linked.exists():reuse(local,linked)
        phase='CORE_RUNTIME'
        facts=runtime(project,candidate,root,catalog['platforms'][key],key,cache,state)
        stages['core_runtime']='READY'
        phase='MATH_BACKEND'
        from presentation_install import qualify,readiness,qualify_fallback
        math=qualify(project,candidate,key,state)
        if math is None:
            math=math_runtime(project,bundle,key,cache,state,candidate)
            math['presentation_probe']=qualify_fallback(project,candidate,key,state)
        stages['math_backend']='READY'
        presentation=readiness(math)
        phase='REGISTRATION'
        selected=project/'.lotraAI-build/Active-skill.json'
        if (not any(plan[n] for n in ('add','replace','delete')) and selected.exists()
                and read_json(selected).get('release_id')==catalog['release_id']):
            result=read_json(project/'.lotraAI-build/Bundle-install.json')
            result.update(runtime=facts,math_renderer=math,math_import_ready=None if math['status']=='LOCAL_NATIVE_READY' else True,math_backend_ready=True,
                          math_execution_mode=math['backend']['execution_mode'],stages=stages,capabilities=presentation,
                          render_ready=presentation['render_ready'],native_edit_ready=presentation['native_edit_ready'])
            write_json(project/'.lotraAI-build/Bundle-install.json',result)
            write_json(state/'Result.json',result)
            finish_runtime(state)
            print(json.dumps({'status':'ALREADY_CURRENT','version':catalog['version'],'skill_entry':str(target/'SKILL.md'),
                              'core_ready':True,'render_status':presentation['render_status'],'report':str(state/'Result.json')}))
            return
        profile=read_json(project/'.lotraAI-build/toolchain'/('core-runtime-'+key+'.json'))
        engine=within(project,profile['engine']['path'])
        preimages={}
        for name in metadata:
            p=within(project,name)
            saved=within(state,'registration-preimage/'+name)
            if p.exists():
                put(saved,p.read_bytes())
                preimages[name]=True
            else:preimages[name]=False
        write_json(within(state,'Registration.json'),preimages)
        touched=True
        if target!=canonical:
            if canonical.exists():raise ValueError('Preserve occupied canonical skill path')
            write_json(state/'Relocation.json',{'status':'MOVING','previous':str(target)})
            target.rename(canonical);target=canonical;relocated=True
        apply(target,candidate,plan,state)
        owned(target)
        prefix=[str(engine),'-I','-X','utf8','-B',str(target/'scripts/run_lotra.py'),'--project',str(project)]
        result={'schema':'lotra-product-install-result-1','version':catalog['version'],'publication_revision':catalog['publication_revision'],
                'bundle_id':catalog['bundle_id'],'environment':key,'project':str(project),'status':'INSTALLED_READY_SINGLE_SKILL',
                'core_ready':True,'runtime':facts,'math_renderer':math,'math_import_ready':None if math['status']=='LOCAL_NATIVE_READY' else True,'math_backend_ready':True,
                'math_execution_mode':math['backend']['execution_mode'],'stages':stages,'runtime_python':str(engine),
                'command_prefix':prefix,'command_text':subprocess.list2cmdline(prefix) if os.name=='nt' else shlex.join(prefix),
                'render_ready':presentation['render_ready'],'native_edit_ready':presentation['native_edit_ready'],'whole_drawing_acceptance':False,
                'capabilities':presentation,
                'installed_skill_count':1,'setup_skill_registered':False,'global_skills':'preserved','global_packages_changed':False,
                'delta':{name:plan[name] for name in ('add','replace','delete','keep')},'report':str(state/'Result.json')}
        register(project,target,bundle,harness,result)
        for name in ('.lotraAI-build/Active-skill.json','.lotraAI-build/Bundle-install.json'):
            value=result if name.endswith('Bundle-install.json') else {**read_json(project/name),'publication_revision':catalog['publication_revision'],'release_id':catalog['release_id']}
            raw=(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode();put(within(project,name),raw)
        write_json(state/'Result.json',result)
        data=read_json(state/'Apply.json');write_json(state/'Apply.json',{**data,'status':'COMPLETE'})
        committed=True;finish_runtime(state)
        if relocated:write_json(state/'Relocation.json',{'status':'COMPLETE'})
        print(json.dumps({'status':result['status'],'version':catalog['version'],'revision':catalog['publication_revision'],
                          'skill_entry':'.agents/skills/lotra-image2slide-skill/SKILL.md','core_ready':True,'render_status':presentation['render_status'],'report':str(state/'Result.json')}))
    except Exception as error:
        if committed:raise
        failed_stage={'SKILL_FILES':'skill_files','MATH_BACKEND':'math_backend','CORE_RUNTIME':'core_runtime'}.get(phase)
        if failed_stage:stages[failed_stage]='FAILED'
        rollback(target,state)
        restore_runtime(project,state)
        registration=state/'Registration.json'
        if touched and registration.exists():
            for name,existed in read_json(registration).items():
                p=within(project,name)
                if existed:put(p,within(state,'registration-preimage/'+name).read_bytes())
                elif p.exists():p.unlink()
        if relocated:
            previous=Path(read_json(state/'Relocation.json')['previous'])
            target.rename(previous)
            write_json(state/'Relocation.json',{'status':'ROLLED_BACK','previous':str(previous)})
        write_json(state/'Failure.json',{'status':'INSTALL_FAILED','reason':str(error),'phase':phase,'stages':stages,
            'core_ready':True if stages['core_runtime']=='READY' else False if stages['core_runtime']=='FAILED' else None,
            'math_backend_ready':stages['math_backend']=='READY','render_status':'NOT_RUN'})
        raise
    finally:lock.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True);parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--harness',default='auto')
    args=parser.parse_args();install(args.project,read_json(args.catalog),Path(__file__).resolve().parent,args.harness)


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'status':'INSTALL_FAILED','reason':str(error)[:320]}));raise SystemExit(1)
