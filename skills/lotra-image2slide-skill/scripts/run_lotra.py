"""Stdlib launcher; consumes its prefix only, preserving command arguments."""
import argparse,os,runpy,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from core.ocr_runtime import core_profile
from core.common import digest,safe_path,read_json

def arguments(argv):
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--project',type=Path,required=True)
    count=1 if argv and argv[0].startswith('--project=') else 2
    args=parser.parse_args(argv[:count]);remaining=list(argv[count:])
    if not remaining:raise ValueError('Supply a runtime command after --project PROJECT')
    if remaining[0] in ('start','presentation-backend','validate-presentation','render','formula-render') and not any(v=='--project' or v.startswith('--project=') for v in remaining):
        remaining+=['--project',str(args.project)]
    return args,remaining

def main(argv=None):
    args,remaining=arguments(sys.argv[1:] if argv is None else argv)
    ready=core_profile(args.project)
    expected=safe_path(args.project,ready['engine']['path'])
    if Path(sys.executable).resolve()!=expected.resolve():
        os.execv(str(expected),[str(expected),'-X','utf8','-B',str(Path(__file__).resolve()),'--project',str(args.project),*remaining])
    handles=[]
    for value in ready.get('native_libraries',[]):
        path=Path(value).resolve()
        if not path.is_dir():raise ValueError('Previously probed native library directory is unavailable')
        os.environ['PATH']=str(path)+os.pathsep+os.environ.get('PATH','')
        if hasattr(os,'add_dll_directory'):handles.append(os.add_dll_directory(str(path)))
    sys.argv=[str(Path(__file__).with_name('sci_rebuild.py')),*remaining]
    runpy.run_path(sys.argv[0],run_name='__main__')

if __name__=='__main__':main()
