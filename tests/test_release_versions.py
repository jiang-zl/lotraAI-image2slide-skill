"""Version-gate counterexamples; use minimal isolated metadata copies."""
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT.parent/'runtime'
spec=importlib.util.spec_from_file_location('release_versions',ROOT/'tools/validate_release_versions.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
SKILL='skills/lotra-image2slide-skill/'


class ReleaseVersions(unittest.TestCase):
    def setUp(self):
        base=ROOT/'.lotraAI-build/release-version-tests';base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='owned-',dir=base);self.addCleanup(self.temp.cleanup)
        self.source=Path(self.temp.name)/'source';self.runtime=Path(self.temp.name)/'runtime'
        source_names=['publication.json','AGENTS.md','README.md','README.zh-CN.md','install-lotra.sh','install-lotra.ps1',
            'installer/install.py','installer/install.ps1','installer/Current-release.json']
        source_names += [SKILL+n for n in ('config/customer-package.json','MANIFEST.json','.lotraai-image2slide-install.json',
            'SKILL.md','agents/openai.yaml','scripts/package_skill.py','scripts/core/__init__.py','scripts/core/workflow_guard.py','scripts/install-runtime.ps1','scripts/install-runtime.sh')]
        for origin,target,names in [(ROOT,self.source,source_names),(RUNTIME,self.runtime,
            ['README.md','README.zh-CN.md','releases/current.json','tools/install_lotra.py','tools/install_lotra.ps1','tools/install_lotra.sh',
             'docs/publication-checklist.md','docs/publishing.md','docs/bundle-contents.md','docs/release-status.md'])]:
            for name in names:
                file=target/name;file.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(origin/name,file)
        self.version=json.loads((self.source/'publication.json').read_bytes())['version']

    def test_current_metadata_passes_with_independent_versions(self):
        result=gate.validate(self.source,self.runtime)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['independent_versions'],{'workflow_version':'1.35.2','runtime_version':'1.14.0'})

    def test_stale_product_core_version_is_rejected(self):
        file=self.source/SKILL/'scripts/core/__init__.py'
        file.write_text('VERSION = "0.0.1"\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'core/__init__'):
            gate.validate(self.source,self.runtime)

    def test_stale_packager_constant_blocks_release(self):
        file=self.source/SKILL/'scripts/package_skill.py'
        file.write_text(file.read_text().replace('VERSION = "'+self.version+'"','VERSION = "0.0.1"'))
        with self.assertRaisesRegex(ValueError,'package_skill.py'):gate.validate(self.source,self.runtime)

    def test_stale_runtime_channel_blocks_release(self):
        file=self.runtime/'releases/current.json';value=json.loads(file.read_bytes());value['version']='0.0.1'
        file.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'runtime/channel'):gate.validate(self.source,self.runtime)

    def test_stale_readme_current_version_blocks_release(self):
        file=self.source/'README.md'
        file.write_text(file.read_text(encoding='utf-8').replace('Current release: '+self.version,'Current release: 0.0.1'),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'README.md/current'):gate.validate(self.source,self.runtime)

    def test_zip_embedded_old_version_blocks_release(self):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as archive:archive.writestr('MANIFEST.json',json.dumps({'version':'0.0.1'}))
        with zipfile.ZipFile(io.BytesIO(data.getvalue())) as archive:
            with self.assertRaisesRegex(ValueError,'MANIFEST'):gate.validate_skill_members(archive,gate.Gate(self.version),'final-skill-zip')

    def test_final_check_requires_actual_distributions(self):
        with self.assertRaisesRegex(ValueError,'Final gate needs'):gate.validate(self.source,self.runtime,final=True)


if __name__=='__main__':unittest.main()
