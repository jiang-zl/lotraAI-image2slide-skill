"""Fail closed on product-version or content-pin drift in final distributions."""
import argparse
import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import urllib.parse
import zipfile

SOURCE_REPO='https://github.com/jiang-zl/lotraAI-image2slide-skill'
RUNTIME_RAW='https://raw.githubusercontent.com/jiang-zl/lotraAI-image2slide-skill-runtime/'
SKILL_PATH='skills/lotra-image2slide-skill'


def digest(data):return hashlib.sha256(data).hexdigest()


def record(file):
    h=hashlib.sha256()
    with file.open('rb') as stream:
        for data in iter(lambda:stream.read(4*1024*1024),b''):h.update(data)
    return {'bytes':file.stat().st_size,'sha256':h.hexdigest()}


def load(file):return json.loads(file.read_bytes())


def constant(data,name='VERSION'):
    for node in ast.parse(data.decode('utf-8-sig')).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('Missing version constant: '+name)


class Gate:
    def __init__(self,version):self.version=version;self.checks=[]
    def equal(self,label,actual,expected):
        if actual!=expected:raise ValueError('Release consistency mismatch: '+label)
        self.checks.append(label)
    def product(self,label,value):self.equal(label,value,self.version)
    def contains(self,label,text,value):self.equal(label,value in text,True)


def validate_skill_members(archive,gate,label):
    manifest=json.loads(archive.read('MANIFEST.json'))
    gate.product(label+'/MANIFEST',manifest['version'])
    gate.product(label+'/customer-package',json.loads(archive.read('config/customer-package.json'))['version'])
    execution=json.loads(archive.read('config/customer-package.json')).get('execution_policy')
    if execution:
        gate.equal(label+'/execution-policy',constant(archive.read('scripts/core/workflow_guard.py'),'POLICY'),execution)
        gate.contains(label+'/execution-policy-entry',archive.read('SKILL.md').decode(),execution)
    verification=json.loads(archive.read('config/customer-package.json')).get('verification_policy')
    if verification:
        gate.equal(label+'/verification-policy',constant(archive.read('scripts/core/line_contracts.py'),'POLICY'),verification)
        gate.contains(label+'/verification-policy-entry',archive.read('SKILL.md').decode(),verification)
    font_policy=json.loads(archive.read('config/customer-package.json')).get('font_workflow_policy')
    if font_policy:
        gate.equal(label+'/font-workflow-policy',constant(archive.read('scripts/core/font_resolution.py'),'POLICY'),font_policy)
        gate.contains(label+'/font-workflow-policy-entry',archive.read('SKILL.md').decode(),font_policy)
    gate.product(label+'/packager',constant(archive.read('scripts/package_skill.py')))
    gate.product(label+'/product-core',constant(archive.read('scripts/core/__init__.py')))
    gate.contains(label+'/SKILL',archive.read('SKILL.md').decode(),f'# lotraAI Image2Slide v{gate.version}')
    gate.contains(label+'/agent',archive.read('agents/openai.yaml').decode(),f'display_name: "lotraAI Image2Slide v{gate.version}"')
    gate.equal(label+'/inventory',set(archive.namelist()),set(manifest['files'])|{'MANIFEST.json'})
    for name,row in manifest['files'].items():
        data=archive.read(name)
        gate.equal(label+'/'+name,{'size':len(data),'sha256':digest(data)},row)
    return manifest


def validate(source,runtime=None,assets=None,bundle=None,final=False):
    source=Path(source);runtime=Path(runtime) if runtime else None
    assets=Path(assets) if assets else None;bundle=Path(bundle) if bundle else None
    if final and not all((runtime,assets,bundle)):raise ValueError('Final gate needs runtime, assets and complete ZIP')
    publication=load(source/'publication.json');version=publication['version']
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version):raise ValueError('Numeric product version required')
    gate=Gate(version);skill=source/SKILL_PATH
    execution=load(skill/'config/customer-package.json').get('execution_policy')
    if execution:
        gate.equal('source/execution-policy',constant((skill/'scripts/core/workflow_guard.py').read_bytes(),'POLICY'),execution)
        gate.equal('publication/execution-policy',publication.get('execution_policy'),execution)
        gate.contains('source/execution-policy-entry',(skill/'SKILL.md').read_text(encoding='utf-8'),execution)
    verification=load(skill/'config/customer-package.json').get('verification_policy')
    if verification:
        gate.equal('source/verification-policy',constant((skill/'scripts/core/line_contracts.py').read_bytes(),'POLICY'),verification)
        gate.equal('publication/verification-policy',publication.get('verification_policy'),verification)
        gate.contains('source/verification-policy-entry',(skill/'SKILL.md').read_text(encoding='utf-8'),verification)
    gate.equal('publication/release_tag',publication['release_tag'],'v'+version)
    font_policy=load(skill/'config/customer-package.json').get('font_workflow_policy')
    if font_policy:
        gate.equal('source/font-workflow-policy',constant((skill/'scripts/core/font_resolution.py').read_bytes(),'POLICY'),font_policy)
        gate.equal('publication/font-workflow-policy',publication.get('font_workflow_policy'),font_policy)
        gate.contains('source/font-workflow-policy-entry',(skill/'SKILL.md').read_text(encoding='utf-8'),font_policy)
    gate.product('publication/version_branch',publication['version_branch'])
    gate.equal('publication/release_branch',publication['release_branch'],'dev')
    gate.equal('publication/release_url',publication['release_url'],SOURCE_REPO+'/releases/tag/v'+version)
    for name in ('config/customer-package.json','MANIFEST.json','.lotraai-image2slide-install.json'):
        gate.product('source/skill/'+name,load(skill/name)['version'])
    for name in ('installer/install.py',SKILL_PATH+'/scripts/package_skill.py',SKILL_PATH+'/scripts/core/__init__.py'):
        gate.product('source/'+name,constant((source/name).read_bytes()))
    gate.contains('source/SKILL', (skill/'SKILL.md').read_text(encoding='utf-8'),f'# lotraAI Image2Slide v{version}')
    gate.contains('source/agent',(skill/'agents/openai.yaml').read_text(encoding='utf-8'),f'display_name: "lotraAI Image2Slide v{version}"')
    gate.contains('source/agent-prompt',(skill/'agents/openai.yaml').read_text(encoding='utf-8'),'v'+version)
    gate.contains('source/local-powershell-pin',(source/'installer/install.ps1').read_text(encoding='utf-8'),"$manifest.version -ne '"+version+"'")
    gate.contains('source/mandatory-policy',(source/'AGENTS.md').read_text(encoding='utf-8'),'Every product version iteration MUST')
    for root,label in [(source,'source')]+([(runtime,'runtime')] if runtime else []):
        for name in ('README.md','README.zh-CN.md'):
            text=(root/name).read_text(encoding='utf-8')
            gate.contains(label+'/'+name+'/current',text,('Current product release: ' if label=='runtime' else 'Current release: ')+version if name=='README.md' else ('当前产品发布版本：' if label=='runtime' else '当前发布版本：')+version)
            gate.contains(label+'/'+name+'/branch',text,'`'+version+'`')
            for found in re.findall(r'lotraAI-image2slide-skill/releases/(?:download|tag)/v([0-9]+\.[0-9]+\.[0-9]+)',text):
                gate.product(label+'/'+name+'/product-link',found)
    channel=load(source/'installer/Current-release.json');gate.product('source/channel',channel['version'])
    if runtime:
        gate.equal('runtime/channel',load(runtime/'releases/current.json'),channel)
        for name,phrase in [('docs/publication-checklist.md','Product/version branch/tag: '+version+' / '+version+' / v'+version),
                            ('docs/publishing.md','current product publication is '+version),
                            ('docs/bundle-contents.md','Product and main skill | lotraAI Image2Slide '+version),
                            ('docs/release-status.md','# '+version+' installation validation')]:
            gate.contains('runtime/current-doc/'+name,(runtime/name).read_text(encoding='utf-8'),phrase)
        entry={'url':RUNTIME_RAW+version+'/tools/install_lotra.py',**record(runtime/'tools/install_lotra.py')}
        gate.equal('runtime/entry-pin',channel['entry'],entry)
        for ext in ('ps1','sh'):
            data=(source/('install-lotra.'+ext)).read_bytes();text=data.decode('utf-8')
            gate.equal('runtime/'+ext+'/copy',(runtime/'tools'/('install_lotra.'+ext)).read_bytes(),data)
            gate.equal('skill/'+ext+'/copy',(skill/'scripts'/('install-runtime.'+ext)).read_bytes(),data)
            gate.contains('entry/'+ext+'/url',text,entry['url']);gate.contains('entry/'+ext+'/sha256',text,entry['sha256'])
            if ext=='ps1':gate.contains('entry/ps1/bytes',text,str(entry['bytes']))
    expected_base=SOURCE_REPO+'/releases/download/v'+version+'/'
    gate.equal('channel/catalog-url',channel['catalog']['url'],expected_base+'release.json')
    gate.equal('channel/bundle-url',channel['bundle']['url'],expected_base+'v'+version+'-bundle.json')
    gate.equal('publication/bundle-record',publication['complete_bundle']['manifest'],channel['bundle'])
    if assets:
        catalog=load(assets/'release.json');manifest=load(assets/('v'+version+'-bundle.json'))
        gate.product('assets/catalog',catalog['version']);gate.product('assets/catalog-bundle',catalog['bundle']['version'])
        gate.product('assets/bundle-manifest',manifest['version'])
        gate.equal('assets/catalog-pin',record(assets/'release.json'),{k:channel['catalog'][k] for k in ('bytes','sha256')})
        gate.equal('assets/bundle-pin',record(assets/('v'+version+'-bundle.json')),{k:channel['bundle'][k] for k in ('bytes','sha256')})
        for name in ('README.md','README.zh-CN.md','install-lotra.sh','install-lotra.ps1','publication.json'):
            gate.equal('assets/'+name,(assets/name).read_bytes(),(source/name).read_bytes())
        for name,row in {**{SKILL_PATH+'/'+n:r for n,r in catalog['skill']['files'].items()},**catalog['installer']}.items():
            gate.equal('catalog/source/'+name,record(source/name),{k:row[k] for k in ('bytes','sha256')})
            gate.equal('catalog/url/'+name,row['url'],'https://raw.githubusercontent.com/jiang-zl/lotraAI-image2slide-skill/v'+version+'/'+name)
        payload=assets/('lotraAI-image2slide-skill-v'+version+'.zip')
        gate.equal('publication/payload-sha',record(payload)['sha256'],publication['skill_payload_sha256'])
        spec=importlib.util.spec_from_file_location('release_gate_packager',skill/'scripts/package_skill.py')
        packager=importlib.util.module_from_spec(spec);spec.loader.exec_module(packager)
        contents,raw,owned=packager.verify_archive(payload)
        gate.equal('skill/own-packager',owned['version'],version)
        gate.equal('skill/source-manifest',(skill/'MANIFEST.json').read_bytes(),raw)
        with zipfile.ZipFile(payload) as archive:validate_skill_members(archive,gate,'assets/skill-zip')
        parts=manifest['bundle']['parts'];count=len(parts)
        gate.equal('bundle/filename',manifest['bundle']['filename'],'lotraAI-image2slide-v'+version+'-bundle.zip')
        gate.equal('bundle/part-count',publication['complete_bundle']['parts'],count)
        gate.equal('bundle/part-order',[p['index'] for p in parts],list(range(1,count+1)))
        gate.equal('bundle/part-bytes',sum(p['bytes'] for p in parts),manifest['bundle']['bytes'])
        for part in parts:
            name=part['filename'];url=urllib.parse.urlsplit(part['url'])
            gate.equal('bundle/part-name/'+str(part['index']),bool(re.fullmatch(r'lotraAI-image2slide-v[0-9]+\.[0-9]+\.[0-9]+-bundle\.zip\.part'+str(part['index']).zfill(3),name)),True)
            gate.equal('bundle/part-url/'+str(part['index']),urllib.parse.unquote(url.path.rsplit('/',1)[-1]),name)
        count_docs=[(source/'docs/download.md',r'(\d+) ordered parts'),(source/'docs/download.zh-CN.md',r'(\d+) 个有序分块')]
        if runtime:count_docs += [(runtime/'README.md',r'provides (\d+) parts'),(runtime/'README.zh-CN.md',r'的 (\d+) 个分块'),
            (runtime/'docs/installation.md',r'of (\d+) ordered,'),(runtime/'docs/installation.zh-CN.md',r'的 (\d+) 个有序分块'),
            (runtime/'docs/bundle-contents.md',r'as (\d+) ordered pieces')]
        for file,pattern in count_docs:
            found=re.search(pattern,file.read_text(encoding='utf-8'))
            gate.equal('docs/part-count/'+file.name,int(found[1]) if found else None,count)
    if bundle:
        if not assets:raise ValueError('Complete ZIP check also needs loose assets')
        gate.equal('complete-zip/identity',record(bundle),{k:manifest['bundle'][k] for k in ('bytes','sha256')})
        with zipfile.ZipFile(bundle) as archive:
            for name in ('Bundle-manifest.json','Differential-manifest.json','Update-manifest.json','MANIFEST.json','.lotraai-image2slide-install.json'):
                gate.product('complete-zip/'+name,json.loads(archive.read(name))['version'])
            root_manifest=archive.read('Bundle-manifest.json')
            gate.equal('complete-zip/bundle-id',digest(root_manifest),catalog['bundle_id'])
            gate.equal('complete-zip/catalog',archive.read('Differential-manifest.json'),(assets/'release.json').read_bytes())
            gate.equal('complete-zip/packager',constant(archive.read('scripts/package_skill.py')),version)
            gate.equal('complete-zip/coordinator',constant(archive.read('installer/install.py')),version)
            nested='payload/lotraAI-image2slide-skill-v'+version+'.zip'
            data=archive.read(nested);gate.equal('complete-zip/nested-identity',digest(data),record(payload)['sha256'])
            with zipfile.ZipFile(io.BytesIO(data)) as inner:validate_skill_members(inner,gate,'complete-zip/nested-skill')
            for name,row in catalog['skill']['files'].items():
                data=archive.read(name);gate.equal('complete-zip/skill/'+name,{'bytes':len(data),'sha256':digest(data)},{k:row[k] for k in ('bytes','sha256')})
            for name,row in catalog['installer'].items():
                data=archive.read(name);gate.equal('complete-zip/'+name,{'bytes':len(data),'sha256':digest(data)},{k:row[k] for k in ('bytes','sha256')})
    return {'status':'PASS','version':version,'final_distribution':final,'checks_count':len(gate.checks),'checks':gate.checks,
            'independent_versions':{k:publication[k] for k in ('workflow_version','runtime_version')}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--runtime',type=Path);parser.add_argument('--assets',type=Path);parser.add_argument('--bundle',type=Path)
    parser.add_argument('--final',action='store_true');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=validate(args.source,args.runtime,args.assets,args.bundle,args.final)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:v for k,v in result.items() if k!='checks'}))


if __name__=='__main__':main()
