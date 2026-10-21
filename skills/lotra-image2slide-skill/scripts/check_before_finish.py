"""Optional portable harness adapter. Run before sending the final attachment.

Usage: PREPARED_PYTHON check_before_finish.py TASK --attachment FINAL.pptx
Exit 0 permits a verified final attachment; exit 6 means retain/resume/block.
The caller must enforce the result in its own finish/attachment mechanism.
"""
import argparse,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from core.workflow_delivery import check

def main(argv=None):
    p=argparse.ArgumentParser(description='Verify the exact final lotraAI attachment before a harness finishes')
    p.add_argument('task',type=Path);p.add_argument('--attachment',type=Path,required=True)
    p.add_argument('--directory',type=Path);args=p.parse_args(argv)
    result=check(args.task,args.directory,args.attachment)
    print(json.dumps(result,ensure_ascii=False,separators=(',',':')))
    return 0 if result['allow_finish'] else 6

if __name__=='__main__':sys.exit(main())
