"""Owned worker containment. Windows helper joins its Job before spawning.

Only this short-lived helper joins the kill-on-close job. The user's shell,
Codex and Office processes are never joined, closed or terminated.
"""
import ctypes,json,os,signal,subprocess,sys
from pathlib import Path

def own_windows_job():
    from ctypes import wintypes as W
    class BASIC(ctypes.Structure):
        _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),('flags',W.DWORD),
            ('min_working',ctypes.c_size_t),('max_working',ctypes.c_size_t),('process_limit',W.DWORD),
            ('affinity',ctypes.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]
    class IO(ctypes.Structure):
        _fields_=[(name,ctypes.c_ulonglong) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
    class EXTENDED(ctypes.Structure):
        _fields_=[('basic',BASIC),('io',IO),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,W.LPCWSTR];kernel.CreateJobObjectW.restype=W.HANDLE
    kernel.SetInformationJobObject.argtypes=[W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD]
    kernel.AssignProcessToJobObject.argtypes=[W.HANDLE,W.HANDLE]
    kernel.GetCurrentProcess.restype=W.HANDLE
    job=kernel.CreateJobObjectW(None,None);info=EXTENDED();info.basic.flags=0x2000
    if not job or not kernel.SetInformationJobObject(job,9,ctypes.byref(info),ctypes.sizeof(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    return kernel,job

def resume_owned(pid):
    """Resume the suspended owned launcher after its entire tree is contained."""
    from ctypes import wintypes as W
    class THREAD(ctypes.Structure):
        _fields_=[('size',W.DWORD),('usage',W.DWORD),('thread',W.DWORD),('owner',W.DWORD),
            ('base',W.LONG),('delta',W.LONG),('flags',W.DWORD)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];kernel.CreateToolhelp32Snapshot.restype=W.HANDLE
    kernel.OpenThread.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenThread.restype=W.HANDLE
    kernel.Thread32First.argtypes=[W.HANDLE,ctypes.POINTER(THREAD)];kernel.Thread32First.restype=W.BOOL
    kernel.Thread32Next.argtypes=[W.HANDLE,ctypes.POINTER(THREAD)];kernel.Thread32Next.restype=W.BOOL
    kernel.ResumeThread.argtypes=[W.HANDLE];kernel.ResumeThread.restype=W.DWORD
    kernel.CloseHandle.argtypes=[W.HANDLE]
    snapshot=kernel.CreateToolhelp32Snapshot(4,0);row=THREAD();row.size=ctypes.sizeof(row);found=0
    if snapshot==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:
        more=kernel.Thread32First(snapshot,ctypes.byref(row))
        while more:
            if row.owner==pid:
                thread=kernel.OpenThread(2,False,row.thread)
                if not thread:raise ctypes.WinError(ctypes.get_last_error())
                try:
                    if kernel.ResumeThread(thread)==0xffffffff:raise ctypes.WinError(ctypes.get_last_error())
                    found+=1
                finally:kernel.CloseHandle(thread)
            more=kernel.Thread32Next(snapshot,ctypes.byref(row))
    finally:kernel.CloseHandle(snapshot)
    if not found:raise RuntimeError('The owned suspended worker has no resumable thread')

def run(argv,timeout,**kwargs):
    if not 0<float(timeout)<=240:raise ValueError('Finite owned worker timeout required')
    if os.name=='nt':
        kernel,job=own_windows_job();process=None
        from ctypes import wintypes as W
        kernel.CloseHandle.argtypes=[W.HANDLE]
        try:
            process=subprocess.Popen(list(map(str,argv)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                creationflags=0x08000000|0x4,**{k:v for k,v in kwargs.items() if k in ('cwd','env')})
            if not kernel.AssignProcessToJobObject(job,int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
            resume_owned(process.pid)
            out,err=process.communicate(timeout=timeout)
            encoding=kwargs.get('encoding','utf-8');errors=kwargs.get('errors','replace')
            return subprocess.CompletedProcess(argv,process.returncode,out.decode(encoding,errors),err.decode(encoding,errors))
        finally:
            # This handle belongs only to this invocation. Parent cancellation
            # also closes it at OS level, stopping venv redirectors and workers.
            kernel.CloseHandle(job)
            if process is not None:
                if process.poll() is None:process.kill()
                process.communicate()
    helper=Path(__file__).resolve()
    command=[str(argv[0]),'-X','utf8','-B',str(helper),str(timeout),*map(str,argv)]
    options={'start_new_session':True}
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**options,
        **{k:v for k,v in kwargs.items() if k in ('cwd','env')})
    try:
        out,err=process.communicate(timeout=timeout+2)
    except BaseException:
        if os.name=='nt':process.kill()  # Closing the helper's Job kills its entire owned tree.
        else:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        try:process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.communicate()
        raise
    encoding=kwargs.get('encoding','utf-8');errors=kwargs.get('errors','replace')
    if process.returncode==124:
        if os.name!='nt':
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        raise subprocess.TimeoutExpired(argv,timeout,out.decode(encoding,errors),err.decode(encoding,errors))
    return subprocess.CompletedProcess(argv,process.returncode,out.decode(encoding,errors),err.decode(encoding,errors))

if __name__=='__main__':
    # The helper owns a fresh POSIX session. Detect parent death even when the
    # surrounding terminal only terminates the caller, not its process group.
    import threading,time
    parent=os.getppid();child=None
    def cleanup():
        if child is not None:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
    def stopped(signum,frame):
        cleanup();sys.exit(128+signum)
    signal.signal(signal.SIGTERM,stopped);signal.signal(signal.SIGINT,stopped)
    def parent_watch():
        while True:
            if os.getppid()!=parent:
                cleanup()
                os.killpg(os.getpgrp(),signal.SIGKILL)
            time.sleep(.1)
    threading.Thread(target=parent_watch,daemon=True).start()
    timeout=float(sys.argv[1]);argv=sys.argv[2:]
    if not 0<timeout<=240 or not argv:raise ValueError('Finite owned worker invocation required')
    child=subprocess.Popen(argv,start_new_session=True)
    try:code=child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        child.kill();child.wait();code=124
    finally:cleanup()
    sys.exit(code)
