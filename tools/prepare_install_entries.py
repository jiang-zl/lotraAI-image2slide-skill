"""Render canonical OS bootstraps without accumulating changes on repeat runs."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def save(file,data):
    file.parent.mkdir(parents=True,exist_ok=True)
    if file.is_file() and file.read_bytes()==data:return
    file.write_bytes(data)


def prepare(source,runtime,version):
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Use a numeric product version')
    entry=runtime/'tools/install_lotra.py'
    body=entry.read_bytes()
    record={'url':'https://raw.githubusercontent.com/jiang-zl/lotraAI-image2slide-skill-runtime/'+version+'/tools/install_lotra.py',
            'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
    tokens={'@ENTRY_URL@':record['url'],'@ENTRY_SHA256@':record['sha256'],'@ENTRY_BYTES@':str(record['bytes'])}
    for ext,managed in [('sh','sh'),('ps1','ps1')]:
        text=(source/'installer/templates'/('install-lotra.'+ext+'.in')).read_text(encoding='utf-8')
        for key,value in tokens.items():text=text.replace(key,value)
        if re.search(r'@ENTRY_[A-Z0-9_]+@',text):raise ValueError('Unresolved bootstrap token')
        data=text.encode('utf-8') if ext=='sh' else text.replace('\n','\r\n').encode('utf-8')
        for target in (source/('install-lotra.'+ext),runtime/'tools'/('install_lotra.'+ext),
                       source/'skills/lotra-image2slide-skill/scripts'/('install-runtime.'+ext)):
            save(target,data)
    # The local-bundle coordinator is also a shell installation entry.
    coordinator=source/'installer/install.sh'
    if coordinator.is_file():save(coordinator,coordinator.read_bytes().replace(b'\r\n',b'\n'))
    # The local coordinator also pins the product version; keep it in the same
    # repeat-safe preparation step as the public OS entries.
    for name,pattern,replacement in [
        ('installer/install.ps1',r"\$manifest\.version -ne '\d+\.\d+\.\d+'","$manifest.version -ne '"+version+"'"),
        ('installer/install.py',r"(?m)^VERSION = '\d+\.\d+\.\d+'","VERSION = '"+version+"'"),
    ]:
        file=source/name
        if not file.is_file():continue
        prior=file.read_bytes();text=prior.decode('utf-8').replace('\r\n','\n')
        text,count=re.subn(pattern,lambda match:replacement,text)
        if count!=1:raise ValueError('Unexpected coordinator version binding: '+name)
        save(file,text.replace('\n','\r\n').encode() if b'\r\n' in prior else text.encode())
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--version',required=True)
    parser.add_argument('--record',type=Path)
    args=parser.parse_args()
    record=prepare(args.source.resolve(),args.runtime.resolve(),args.version)
    if args.record:save(args.record,(json.dumps(record,sort_keys=True,indent=2)+'\n').encode())
    print(json.dumps(record,sort_keys=True))


if __name__=='__main__':main()
