"""Parse actual loose and ZIP-contained installer bytes before publication."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile


def members(path,label=None):
    label=label or str(path)
    if path.suffix.lower()!='.zip':
        if path.suffix.lower() in ('.sh','.ps1'):yield label,path.read_bytes(),path.suffix.lower()
        return
    with zipfile.ZipFile(path) as archive:
        yield from zip_members(archive,label)


def zip_members(archive,label):
    for item in archive.infolist():
        name=item.filename
        if name.endswith(('.sh','.ps1')):
            yield label+'::'+name,archive.read(item),Path(name).suffix
        elif name.startswith('payload/lotraAI-image2slide-skill-') and name.endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(archive.read(item))) as inner:
                yield from zip_members(inner,label+'::'+name)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--runtime',type=Path)
    parser.add_argument('--asset',type=Path,action='append',default=[])
    parser.add_argument('--shell',action='append',default=[])
    parser.add_argument('--powershell')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.shell and not args.powershell:parser.error('Select actual shell or PowerShell parsers')
    paths=[args.source/'install-lotra.sh',args.source/'install-lotra.ps1',
           args.source/'installer/install.sh',args.source/'installer/install.ps1',
           args.source/'skills/lotra-image2slide-skill/scripts/install-runtime.sh',
           args.source/'skills/lotra-image2slide-skill/scripts/install-runtime.ps1']
    if args.runtime:paths += [args.runtime/'tools/install_lotra.sh',args.runtime/'tools/install_lotra.ps1']
    paths+=args.asset
    records=[]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='installer-parse-',dir=args.output.parent) as temp:
        for file in paths:
            if file.is_relative_to(args.source):label='source/'+file.relative_to(args.source).as_posix()
            elif args.runtime and file.is_relative_to(args.runtime):label='runtime/'+file.relative_to(args.runtime).as_posix()
            else:label=file.name
            for label,data,ext in members(file,label):
                if ext=='.sh' and (b'\r' in data or data.startswith(b'\xef\xbb\xbf')):
                    raise ValueError('Shell entry must be LF without BOM: '+label)
                row={'file':label,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'parsers':[]}
                target=Path(temp)/('entry'+ext);target.write_bytes(data)
                commands=[[shell,'-n',str(target)] for shell in args.shell] if ext=='.sh' else []
                if ext=='.ps1' and args.powershell:
                    quoted=str(target).replace("'","''")
                    command="$tokens=$null;$parseErrors=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('"+quoted+"',[ref]$tokens,[ref]$parseErrors);if($parseErrors.Count){$parseErrors|ForEach-Object{$_.ToString()};exit 1}"
                    commands.append([args.powershell,'-NoProfile','-NonInteractive','-Command',command])
                for command in commands:
                    p=subprocess.run(command,capture_output=True,timeout=30)
                    if p.returncode:raise ValueError('Parse failed: '+label+' '+p.stderr.decode('utf-8','replace')+p.stdout.decode('utf-8','replace'))
                    row['parsers'].append({'parser':command[0],'exit_code':p.returncode})
                records.append(row)
    summary={'status':'PASS','records':records,'parsed_members':sum(bool(r['parsers']) for r in records),
             'lf_shell_members':sum(r['file'].endswith('.sh') for r in records)}
    args.output.write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='records'}))


if __name__=='__main__':main()
