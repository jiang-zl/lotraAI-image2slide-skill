"""An explicit delivery boundary, independent of task-relative private paths."""
from datetime import datetime
import ctypes
import errno
import os
from pathlib import Path
import platform
import re
import subprocess
import uuid
from .common import digest,identity,read_json,write_json,writer


def reserve(project,key,*,output_root=None,exact=None,new=False):
    from .presentation_backend import preferences
    project=Path(project).resolve(strict=True)
    root=Path(output_root or preferences(project).get('output_root') or project).expanduser()
    if not root.is_absolute():root=project/root
    root=root.resolve()
    if exact:
        final=Path(exact).expanduser().resolve();root=final.parent
    forbidden={'.git','.agents'}
    if any(p.lower() in forbidden for p in root.parts):raise ValueError('Choose a user delivery directory outside private/runtime/skill/Git storage')
    if root.is_relative_to(project/'.lotraAI-build') or root.is_relative_to(Path.home()/'.codex/skills'):
        raise ValueError('Delivery must stay outside private runtime data and global skills')
    # Existing directories may be user-selected; only newly owned child paths are modified.
    root.mkdir(parents=True,exist_ok=True)
    jobs=project/'.lotraAI-build/delivery-jobs';jobs.mkdir(parents=True,exist_ok=True)
    request=identity({'candidate':key,'root':str(root),'exact':str(exact) if exact else None})
    with writer(jobs):
        index=jobs/(request+'.json')
        if index.is_file() and not new:
            plan=read_json(index)
            if plan.get('status')=='PUBLISHED':return plan
            if not Path(plan['reservation']).is_dir():raise ValueError('Delivery reservation disappeared; preserve interrupted export for inspection')
        else:
            stamp=datetime.now().astimezone().strftime('%Y-%m-%d-%H%M%S-%f')[:-3]
            base=final if exact else root/('output-slide-'+stamp)
            for serial in range(1000):
                candidate=base if serial==0 else base.with_name(base.name+'-'+str(serial))
                lock=candidate.with_name('.'+candidate.name+'.lotra-reservation')
                if candidate.exists():
                    if exact:raise FileExistsError('Preserve existing delivery: '+str(candidate))
                    continue
                try:lock.mkdir()
                except FileExistsError:
                    if exact:raise FileExistsError('Delivery already reserved: '+str(candidate))
                    continue
                break
            else:raise ValueError('Delivery collision limit reached')
            plan={'schema':'lotra-delivery-destination-1','id':uuid.uuid4().hex,'request':request,
                'project':str(project),'root':str(root),'final':str(candidate),'reservation':str(lock),
                'status':'RESERVED','attempts':[],'index':str(index)}
            write_json(lock/'Owner.json',{'job_id':plan['id'],'request':request,'project':str(project)})
        if len(plan['attempts'])>=3:raise ValueError('Interrupted delivery exhausted three owned attempts; inspect its private plan before a new export')
        stage=root/('.lotraai-stage-'+plan['id']+'-'+str(len(plan['attempts'])+1))
        stage.mkdir(exist_ok=False)
        # Builders retain their existing create-new-directory checks.
        stage.rmdir()
        plan['stage']=str(stage);plan['attempts'].append(str(stage));plan['status']='BUILDING'
        write_json(index,plan)
        return plan


def _rename_new(source,target):
    source,target=Path(source),Path(target)
    if source.is_symlink() or source.parent.resolve()!=target.parent.resolve():
        raise ValueError('Delivery publish requires an owned directory and sibling destination')
    if target.exists():raise FileExistsError(target)
    if os.name=='nt':os.rename(source,target);return
    libc=ctypes.CDLL(None,use_errno=True)
    if platform.system()=='Linux':
        call=libc.renameat2
        result=call(-100,os.fsencode(source),-100,os.fsencode(target),1) # RENAME_NOREPLACE
    elif platform.system()=='Darwin':
        result=libc.renamex_np(os.fsencode(source),os.fsencode(target),4) # RENAME_EXCL
    else:raise RuntimeError('This host lacks an atomic no-replace directory publish adapter')
    if result:
        code=ctypes.get_errno()
        if code==errno.EEXIST:raise FileExistsError(target)
        if platform.system()=='Linux' and code in (errno.EINVAL,errno.ENOSYS,errno.EOPNOTSUPP):
            shell=Path('/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe')
            if shell.is_file():
                def host_path(path):
                    import ntpath
                    path=Path(path).resolve();suffix=[]
                    while not path.exists():suffix.insert(0,path.name);path=path.parent
                    anchor=subprocess.run(['wslpath','-w',str(path)],capture_output=True,
                        text=True,timeout=10,check=True).stdout.strip()
                    return ntpath.join(anchor,*suffix) if suffix else anchor
                left,right=host_path(source),host_path(target)
                if re.match(r'^[A-Za-z]:\\',left) and re.match(r'^[A-Za-z]:\\',right):
                    worker=host_path(Path(__file__).parent.parent/'publish_directory.ps1')
                    job=subprocess.run([str(shell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                        '-File',worker,'-SourceDirectory',left,'-TargetDirectory',right],
                        capture_output=True,timeout=30,encoding='utf-8',errors='replace')
                    if job.returncode:raise RuntimeError('Windows volume publish failed; preserve stage: '+job.stderr[-2000:])
                    if source.exists() or not target.is_dir():raise ValueError('Windows publish result is incomplete')
                    return
        raise OSError(code,os.strerror(code),str(target))


def publish(plan,result):
    from .user_delivery import verify
    if plan['status']=='PUBLISHED':
        verify(plan['final'],plan['receipt'])
        return plan['result']
    stage,final,lock=map(Path,(plan['stage'],plan['final'],plan['reservation']))
    owner=read_json(lock/'Owner.json')
    if owner!={'job_id':plan['id'],'request':plan['request'],'project':plan['project']}:
        raise ValueError('Delivery reservation owner changed')
    receipt_file=Path(result['audit_receipt']);receipt=read_json(receipt_file)
    verify(stage,receipt_file)
    expected=receipt['files']
    if set(expected)!={'Final_editable.pptx','Report.md'}:raise ValueError('Unexpected delivery inventory')
    for name,sha in expected.items():
        if (stage/name).is_symlink() or digest(stage/name)!=sha:raise ValueError('Destination-stage bytes changed')
    # Stage and final are siblings on the chosen volume, including cross-drive exports.
    _rename_new(stage,final)
    receipt.update(output=str(final),destination={'policy':plan['schema'],'root':plan['root'],
        'job_id':plan['id'],'publish':'atomic-no-replace-same-volume','stage_hashes_verified':True})
    write_json(receipt_file,receipt);verify(final,receipt_file)
    translated={k:(v.replace(str(stage),str(final)) if isinstance(v,str) else v) for k,v in result.items()}
    translated.update(output=str(final))
    write_json(Path(plan['project'])/'.lotraAI-build/delivery-receipts'/(identity(str(final))+'.json'),
        {'receipt':str(receipt_file),'sha256':digest(receipt_file)})
    plan.update(status='PUBLISHED',receipt=str(receipt_file),result=translated)
    write_json(plan['index'],plan)
    # Only the exact, now-empty owner reservation is removed; failures retain stage/plan.
    (lock/'Owner.json').unlink();lock.rmdir()
    return translated
