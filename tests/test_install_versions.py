"""Product-version bindings, packager integrity and inherited bundle parts."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'installer'))
import bundle_transport as transport
import install


def module(file,name):
    spec=importlib.util.spec_from_file_location(name,file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


packager=module(ROOT/'skills/lotra-image2slide-skill/scripts/package_skill.py','version_packager')
generator=module(ROOT/'tools/prepare_install_entries.py','version_generator')
TEST_ROOT=ROOT/'.lotraAI-build/version-tests'


class InstallVersions(unittest.TestCase):
    def setUp(self):
        TEST_ROOT.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='owned-',dir=TEST_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.project=Path(self.temp.name).resolve()
        assert self.project.is_relative_to(TEST_ROOT.resolve())
        self.cache=self.project/'.lotraAI-build/downloads/sha256'
        self.cache.mkdir(parents=True)

    def fixture(self):
        chunks=(b'first inherited part\n',b'prior tail part\n',b'current tail\n')
        parts=[]
        for index,(version,chunk) in enumerate(zip(('1.34.0','1.35.3',install.VERSION),chunks),1):
            digest=hashlib.sha256(chunk).hexdigest()
            (self.cache/digest).write_bytes(chunk)
            parts.append({'index':index,'filename':f'lotraAI-image2slide-v{version}-bundle.zip.part{index:03d}',
                          'bytes':len(chunk),'sha256':digest,'url':'https://invalid.example/unused'})
        data=b''.join(chunks)
        manifest={'schema':'lotraai-publication-release-1','version':install.VERSION,
                  'bundle':{'filename':f'lotraAI-image2slide-v{install.VERSION}-bundle.zip',
                            'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'parts':parts}}
        return manifest,data

    def test_mixed_release_part_names_assemble_current_bundle(self):
        manifest,data=self.fixture()
        result=transport.download(self.project,manifest,self.project/'download')
        self.assertEqual(result['version'],install.VERSION)
        self.assertEqual(Path(result['bundle']).read_bytes(),data)
        self.assertEqual(result['parts'],3)

    def test_repeat_preserves_output_mtime(self):
        manifest,data=self.fixture()
        result=transport.download(self.project,manifest,self.project/'download')
        output=Path(result['bundle']);before=output.stat().st_mtime_ns
        transport.download(self.project,manifest,self.project/'download')
        self.assertEqual(before,output.stat().st_mtime_ns)
        self.assertEqual(data,output.read_bytes())

    def test_changed_existing_bundle_is_preserved(self):
        manifest,_=self.fixture();output=self.project/'download';output.mkdir()
        file=output/manifest['bundle']['filename'];file.write_bytes(b'user modified bundle')
        with self.assertRaisesRegex(ValueError,'Preserve a different existing complete bundle'):
            transport.download(self.project,manifest,output)
        self.assertEqual(file.read_bytes(),b'user modified bundle')

    def test_wrong_product_version_is_rejected(self):
        manifest,_=self.fixture();manifest['version']='1.34.0'
        with self.assertRaisesRegex(ValueError,'Unsupported complete-bundle manifest'):
            transport.download(self.project,manifest,self.project/'download')
        self.assertFalse((self.project/'download').exists())

    def test_wrong_bundle_filename_is_rejected(self):
        manifest,_=self.fixture();manifest['bundle']['filename']='lotraAI-image2slide-v1.33.0-bundle.zip'
        with self.assertRaisesRegex(ValueError,'Unexpected complete-bundle filename'):
            transport.download(self.project,manifest,self.project/'download')

    def test_wrong_part_index_in_filename_is_rejected(self):
        manifest,_=self.fixture();manifest['bundle']['parts'][0]['filename']='lotraAI-image2slide-v1.34.0-bundle.zip.part002'
        with self.assertRaisesRegex(ValueError,'Unexpected complete-bundle part'):
            transport.download(self.project,manifest,self.project/'download')

    def test_corrupted_cached_part_is_preserved(self):
        manifest,_=self.fixture();file=self.cache/manifest['bundle']['parts'][0]['sha256']
        file.write_bytes(b'changed cache')
        with self.assertRaisesRegex(ValueError,'Preserve changed verified download'):
            transport.download(self.project,manifest,self.project/'download')
        self.assertEqual(file.read_bytes(),b'changed cache')

    def test_packager_matches_current_customer_inventory(self):
        policy=json.loads((packager.SOURCE/'config/customer-package.json').read_bytes())
        self.assertEqual(packager.VERSION,install.VERSION)
        self.assertEqual(packager.VERSION,policy['version'])
        self.assertEqual(set(packager.collect_source()),set(policy['included_paths']))

    def test_current_source_builds_and_verifies_own_archive(self):
        archive=self.project/'skill.zip'
        result=packager.build(archive)
        payload,raw,manifest=packager.verify_archive(archive)
        self.assertEqual(result['version'],install.VERSION)
        self.assertEqual(manifest['version'],install.VERSION)
        self.assertIn('scripts/package_skill.py',payload)

    def test_release_generator_updates_packager_and_is_idempotent(self):
        source=self.project/'source';runtime=self.project/'runtime'
        shutil.copytree(ROOT/'installer/templates',source/'installer/templates')
        for name in ('install.py','install.ps1','install.sh'):
            shutil.copy2(ROOT/'installer'/name,source/'installer'/name)
        script=source/'skills/lotra-image2slide-skill/scripts/package_skill.py'
        script.parent.mkdir(parents=True)
        shutil.copy2(packager.SOURCE/'scripts/package_skill.py',script)
        entry=runtime/'tools/install_lotra.py';entry.parent.mkdir(parents=True);entry.write_bytes(b'# pinned test entry\n')
        generator.prepare(source,runtime,'9.8.7')
        self.assertIn('VERSION = "9.8.7"',script.read_text())
        files=[f for root in (source,runtime) for f in root.rglob('*') if f.is_file()]
        before={str(f):(f.read_bytes(),f.stat().st_mtime_ns) for f in files}
        generator.prepare(source,runtime,'9.8.7');generator.prepare(source,runtime,'9.8.7')
        self.assertEqual(before,{str(f):(f.read_bytes(),f.stat().st_mtime_ns) for f in files})


if __name__=='__main__':unittest.main()
