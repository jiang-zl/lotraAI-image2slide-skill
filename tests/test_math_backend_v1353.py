"""Finite backend dispatch, request isolation and pinned transport regressions."""
import importlib.util
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import contextlib
import io
import shutil
import uuid
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, unquote

REPO=Path(__file__).resolve().parents[1]
TEST_ROOT=REPO/'.lotraAI-build/validation-v1353/tests'
TEST_ROOT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(REPO/'skills/lotra-image2slide-skill/scripts'))
from core import editor_backend as backend

spec=importlib.util.spec_from_file_location('lotra_test_download',REPO/'installer/download.py')
download=importlib.util.module_from_spec(spec);spec.loader.exec_module(download)


@contextlib.contextmanager
def fixture_directory():
    directory=TEST_ROOT/uuid.uuid4().hex
    directory.mkdir()
    try:yield directory
    finally:
        if not directory.resolve().is_relative_to(TEST_ROOT.resolve()):raise ValueError('Unexpected test cleanup path')
        shutil.rmtree(directory)


class BackendContracts(unittest.TestCase):
    def setUp(self):
        self.temp=fixture_directory()
        self.root=self.temp.__enter__()
        self.exe=self.root/'soffice';self.exe.write_bytes(b'fixture executable')
        self.uno=self.root/'python';self.uno.write_bytes(b'fixture interpreter')
        self.config={'executable':str(self.exe),'uno_python':str(self.uno),'execution_mode':'libreoffice_hosted'}
        self.directory=self.root/'job';self.directory.mkdir()

    def tearDown(self):
        if not self.root.resolve().is_relative_to(TEST_ROOT.resolve()):raise ValueError('Unexpected test cleanup path')
        self.temp.__exit__(None,None,None)

    def test_macos_selects_hosted_mode_without_an_override(self):
        with patch.object(backend.platform,'system',return_value='Darwin'):
            self.assertEqual(backend.execution_mode({}),'libreoffice_hosted')

    def test_macos_rejects_the_constrained_interpreter_route(self):
        with patch.object(backend.platform,'system',return_value='Darwin'):
            with self.assertRaisesRegex(ValueError,'LibreOffice-hosted'):
                backend.execution_mode({'execution_mode':'subprocess_uno'})

    def test_hosted_identity_does_not_require_a_cli_interpreter(self):
        self.uno.unlink()
        self.assertEqual(backend.identity(self.config)['execution_mode'],'libreoffice_hosted')

    def test_dispatch_identity_changes_when_execution_mode_changes(self):
        first=backend.identity(self.config)['sha256']
        self.config['execution_mode']='subprocess_uno'
        self.assertNotEqual(first,backend.identity(self.config)['sha256'])

    def test_invalid_operation_does_not_launch_an_editor(self):
        with patch.object(backend.subprocess,'Popen') as launch:
            with self.assertRaises(ValueError):backend.run(self.config,self.directory,operation='shell')
            launch.assert_not_called()

    def test_unbounded_timeout_does_not_launch_an_editor(self):
        with patch.object(backend.subprocess,'Popen') as launch:
            with self.assertRaises(ValueError):backend.run(self.config,self.directory,timeout=301)
            launch.assert_not_called()

    def simulate(self,change=None,reply=True):
        calls=[]
        directory=self.directory
        class Process:
            pid=12345;returncode=0
            def poll(self):return self.returncode
            def wait(self,timeout):return self.returncode
        def launch(args,**kwargs):
            calls.append(args)
            if '--terminate_after_init' in args:return Process()
            argument=next(a for a in args if a.startswith('-env:UserInstallation='))
            uri=urlsplit(argument.split('=',1)[1]);raw=unquote(uri.path)
            if sys.platform=='win32':raw=raw.lstrip('/')
            profile=Path(raw)
            request=profile/'job.json';job=json.loads(request.read_bytes())
            if reply:
                value={'schema':'lotra-editor-job-result-1','job_id':job['job_id'],'operation':job['operation'],
                    'request_sha256':backend.digest(request),'status':'PASS'}
                if change:change(value,job,profile)
                (directory/'math-probe.json').write_text(json.dumps({'status':'PASS','native_math_service':True}))
                (profile/'result.json').write_text(json.dumps(value))
            return Process()
        with patch.object(backend.platform,'system',return_value='Windows'), \
             patch.object(backend.platform,'machine',return_value='AMD64'), \
             patch.object(backend.platform,'release',return_value='fixture'), \
             patch.object(backend.subprocess,'Popen',side_effect=launch):
            result=backend.run(self.config,directory,operation='probe',timeout=2)
        return calls,result

    def test_hosted_handshake_never_spawns_the_interpreter(self):
        calls,result=self.simulate()
        self.assertEqual(result['status'],'PASS')
        self.assertTrue(all(c[0]==str(self.exe) for c in calls))
        self.assertEqual(len(calls),2)

    def test_cross_job_result_is_rejected(self):
        with self.assertRaisesRegex(backend.BackendError,'does not match'):
            self.simulate(lambda result,*unused:result.update(job_id='another-job'))

    def test_stale_request_digest_is_rejected(self):
        with self.assertRaisesRegex(backend.BackendError,'does not match'):
            self.simulate(lambda result,*unused:result.update(request_sha256='0'*64))

    def test_failed_hosted_job_is_not_startup_success(self):
        with self.assertRaisesRegex(backend.BackendError,'fixture failure'):
            self.simulate(lambda result,*unused:result.update(status='FAILED',reason='fixture failure'))

    def test_process_exit_without_reply_is_a_failure(self):
        with self.assertRaisesRegex(backend.BackendError,'before its hosted Math result'):
            self.simulate(reply=False)
        facts=json.loads((self.directory/'backend-result.json').read_bytes())
        self.assertEqual(facts['status'],'FAILED')

    def test_backend_replacement_during_job_is_rejected(self):
        def change(*unused):self.exe.write_bytes(b'changed after launch')
        with self.assertRaisesRegex(backend.BackendError,'changed during'):
            self.simulate(change)


class GitHubFallback(unittest.TestCase):
    class Response:
        status=200
        headers={}
        def __init__(self,data):self.stream=io.BytesIO(data)
        def read(self,count):return self.stream.read(count)
        def __enter__(self):return self
        def __exit__(self,*unused):return False

    def test_non_github_origin_does_not_use_github_fallback(self):
        self.assertIsNone(download.github_asset_api('https://example.org/a.zip',10))

    def test_other_repositories_are_not_substituted(self):
        self.assertIsNone(download.github_asset_api('https://github.com/other/repo/releases/download/v1/file.zip',10))

    def test_complete_cached_content_needs_no_network(self):
        with fixture_directory() as folder:
            data=b'pinned bytes';sha=hashlib.sha256(data).hexdigest()
            file=Path(folder)/sha;file.write_bytes(data)
            with patch.object(download.urllib.request,'build_opener') as network:
                actual=download.fetch({'url':'https://example.org/asset','bytes':len(data),'sha256':sha},folder)
                self.assertEqual(actual,file);network.assert_not_called()

    def test_changed_verified_cache_is_preserved_and_rejected(self):
        with fixture_directory() as folder:
            sha=hashlib.sha256(b'good').hexdigest();file=Path(folder)/sha;file.write_bytes(b'user edit')
            with self.assertRaisesRegex(ValueError,'Preserve changed'):
                download.fetch({'url':'https://example.org/asset','bytes':4,'sha256':sha},folder)
            self.assertEqual(file.read_bytes(),b'user edit')

    def test_exact_asset_resolution_follows_pagination(self):
        release={'id':10,'tag_name':'v1.35.3'}
        pages=[[{'name':'other-'+str(i)} for i in range(100)],
               [{'name':'fixture.zip','id':99,'size':4,'state':'uploaded'}]]
        responses=[self.Response(json.dumps(row).encode()) for row in [release,*pages]]
        with patch.object(download.urllib.request,'build_opener') as build:
            build.return_value.open.side_effect=responses
            url=download.github_asset_api('https://github.com/jiang-zl/lotraAI-image2slide-skill/releases/download/v1.35.3/fixture.zip',4)
        self.assertTrue(url.endswith('/releases/assets/99'))
        self.assertEqual(build.return_value.open.call_count,3)

    def test_wrong_asset_size_cannot_be_a_fallback(self):
        rows=[{'id':10,'tag_name':'v1.35.3'},[{'name':'fixture.zip','id':99,'size':999,'state':'uploaded'}]]
        with patch.object(download.urllib.request,'build_opener') as build:
            build.return_value.open.side_effect=[self.Response(json.dumps(row).encode()) for row in rows]
            with self.assertRaisesRegex(ValueError,'identity differs'):
                download.github_asset_api('https://github.com/jiang-zl/lotraAI-image2slide-skill/releases/download/v1.35.3/fixture.zip',4)

    def test_fallback_keeps_the_original_content_pin(self):
        with fixture_directory() as folder:
            data=b'pinned bytes';sha=hashlib.sha256(data).hexdigest()
            with patch.object(download.urllib.request,'build_opener') as build, \
                 patch.object(download,'github_asset_api',return_value='https://api.github.com/repos/jiang-zl/lotraAI-image2slide-skill/releases/assets/99'), \
                 patch.object(download.time,'sleep'):
                build.return_value.open.side_effect=[OSError('fixture timeout'),self.Response(data)]
                file=download.fetch({'url':'https://github.com/jiang-zl/lotraAI-image2slide-skill/releases/download/v1.35.3/fixture.zip',
                                     'bytes':len(data),'sha256':sha},folder)
                self.assertEqual(file.read_bytes(),data)
                request=build.return_value.open.call_args.args[0]
                self.assertEqual(request.get_header('Accept'),'application/octet-stream')


class InstallationStages(unittest.TestCase):
    def test_math_failure_keeps_actual_core_readiness_separate(self):
        sys.path.insert(0,str(REPO/'installer'))
        import differential,presentation_install
        from types import SimpleNamespace
        with fixture_directory() as project:
            catalog={'schema':'lotra-differential-release-1','version':'1.35.3','release_id':'fixture',
                     'platforms':{'fixture':{}},'bundle':{'math_renderers':{'fixture':{'path':'renderer.bin'}}},
                     'skill':{'files':{}}}
            with patch.object(differential,'platform_key',return_value='fixture'), \
                 patch.object(differential,'acquire_lock',return_value=SimpleNamespace(close=lambda:None)), \
                 patch.object(differential,'prepare',return_value=(project/'candidate',{})), \
                 patch.object(differential,'runtime_checkpoint'),patch.object(differential,'restore_runtime'), \
                 patch.object(differential,'rollback'), \
                 patch.object(differential,'math_runtime',side_effect=ValueError('fixture Math failure')), \
                 patch.object(differential,'runtime',return_value={'status':'OFFLINE_RUNTIME_READY'}) as core, \
                 patch.object(presentation_install,'qualify',return_value=None):
                with self.assertRaisesRegex(ValueError,'fixture Math failure'):
                    differential.install(project,catalog,REPO/'installer','codex')
                core.assert_called_once()
            failure=json.loads((project/'.lotraAI-build/updates/fixture/Failure.json').read_bytes())
            self.assertEqual(failure['phase'],'MATH_BACKEND')
            self.assertEqual(failure['stages']['core_runtime'],'READY')
            self.assertEqual(failure['stages']['math_backend'],'FAILED')
            self.assertTrue(failure['core_ready'])
            self.assertFalse(failure['math_backend_ready'])


if __name__=='__main__':unittest.main(verbosity=2)
