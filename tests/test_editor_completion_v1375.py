"""Request-bound export completion cannot be confused with UNO shutdown."""
import json,sys,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/lotra-image2slide-skill/scripts'))
from core import editor_backend as backend


class Completion(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.directory=self.root/'export';self.directory.mkdir();self.profile=self.root/'job-identity';self.profile.mkdir()
        for name,data in (('editor-input.pptx',b'immutable native input'),('editor-plan.json',b'{}'),('Final.pdf',b'%PDF-owned-test'),('math-editor.json',b'{"status":"PASS"}')):
            (self.directory/name).write_bytes(data)
        self.job={'schema':'lotra-editor-job-1','job_id':self.profile.name,'operation':'export','directory':str(self.directory),'inputs':{n:backend.digest(self.directory/n) for n in ('editor-input.pptx','editor-plan.json')}}
        self.request=self.profile/'job.json';backend.write_json(self.request,self.job)
        self.reply=self.profile/'result.json';self.result={'schema':'lotra-editor-job-result-1','job_id':self.job['job_id'],'operation':'export',
            'request_sha256':backend.digest(self.request),'status':'PASS','completion':'SYNCHRONOUS_OPERATION_COMPLETE_BEFORE_OWNED_CLEANUP',
            'outputs':{n:{'bytes':(self.directory/n).stat().st_size,'sha256':backend.digest(self.directory/n)} for n in ('Final.pdf','math-editor.json')}}
    def verify(self):
        backend.write_json(self.reply,self.result)
        return backend.subprocess_result(self.reply,self.request,self.directory,self.job)
    def test_exact_operation_outputs_are_verified(self):self.assertEqual(self.verify()['outputs'],self.result['outputs'])
    def test_cross_job_acknowledgement_is_rejected(self):
        self.result['job_id']='another-job'
        with self.assertRaisesRegex(ValueError,'does not match'):self.verify()
    def test_stale_request_is_rejected(self):
        self.result['request_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'does not match'):self.verify()
    def test_output_mutation_and_missing_output_cannot_pass(self):
        (self.directory/'Final.pdf').write_bytes(b'changed PDF')
        with self.assertRaisesRegex(ValueError,'identity changed'):self.verify()
        (self.directory/'Final.pdf').unlink()
        with self.assertRaisesRegex(ValueError,'identity changed'):self.verify()
    def test_existing_artifacts_without_complete_ack_cannot_pass(self):
        self.result.pop('completion')
        with self.assertRaisesRegex(ValueError,'does not match'):self.verify()
    def test_input_mutation_after_export_is_rejected(self):
        (self.directory/'editor-input.pptx').write_bytes(b'changed native input')
        with self.assertRaisesRegex(ValueError,'immutable input changed'):self.verify()
    def test_existing_outputs_are_preserved_before_process_launch(self):
        exe=self.root/'owned-executable';exe.write_bytes(b'owned fixture')
        before=(self.directory/'Final.pdf').read_bytes()
        with patch.object(backend.subprocess,'Popen') as launch:
            with self.assertRaisesRegex(backend.BackendError,'Preserve existing Math operation output'):
                backend.run({'executable':str(exe),'execution_mode':'libreoffice_hosted'},self.directory)
            launch.assert_not_called()
        self.assertEqual((self.directory/'Final.pdf').read_bytes(),before)
    def simulate(self,ack=True,exited=False,project=None,server_exited=False):
        exe=self.root/'soffice';exe.write_bytes(b'exact deployed executable');python=self.root/'python';python.write_bytes(b'exact client interpreter')
        directory=self.root/'probe';directory.mkdir();stopped=[]
        class Process:
            pid=12345;returncode=None
            def poll(self):return self.returncode
            def wait(self,timeout):
                if self.returncode is None:raise subprocess.TimeoutExpired('owned-cleanup',timeout)
                return self.returncode
        def launch(args,**kwargs):
            process=Process()
            if '--job' in args:
                request=Path(args[args.index('--job')+1]);job=json.loads(request.read_bytes())
                if ack:
                    output=directory/'math-probe.json';output.write_text(json.dumps({'status':'PASS','native_math_service':True}))
                    backend.write_json(request.parent/'result.json',{'schema':'lotra-editor-job-result-1','job_id':job['job_id'],'operation':'probe',
                        'request_sha256':backend.digest(request),'status':'PASS','completion':'SYNCHRONOUS_OPERATION_COMPLETE_BEFORE_OWNED_CLEANUP',
                        'outputs':{'math-probe.json':{'bytes':output.stat().st_size,'sha256':backend.digest(output)}}})
                if exited:process.returncode=1
            elif server_exited:process.returncode=1
            return process
        def stop(process):
            if process.poll() is None:stopped.append(process);process.returncode=-15
        with patch.object(backend.platform,'system',return_value='Windows'),patch.object(backend.subprocess,'Popen',side_effect=launch),patch.object(backend,'_stop',side_effect=stop):
            config={'executable':str(exe),'uno_python':str(python),'execution_mode':'subprocess_uno'}
            if project is not None:config['project']=str(project)
            result=backend.run(config,directory,operation='probe',timeout=1)
        return result,stopped
    def test_completed_operation_with_blocked_cleanup_is_finite(self):
        result,stopped=self.simulate();self.assertEqual(result['status'],'PASS');self.assertEqual(len(stopped),2)
        self.assertEqual(result['client_returncode'],-15);self.assertIn('operation_completion',result)
    def test_exit_or_timeout_without_acknowledgement_is_failure(self):
        with self.assertRaisesRegex(backend.BackendError,'before its request-bound result'):self.simulate(ack=False,exited=True)
        # A distinct directory lets this second attempt retain the first failure.
        self.directory=self.root/'second-unused';self.directory.mkdir()
        (self.root/'probe').rename(self.root/'probe-retained')
        with self.assertRaises(backend.BackendError):self.simulate(ack=False)
        facts=json.loads((self.root/'probe/backend-result.json').read_bytes());self.assertTrue(facts['timed_out'])

    def test_profile_for_external_output_stays_in_prepared_project(self):
        project=self.root/'registered';private=project/'.lotraAI-build';private.mkdir(parents=True)
        deep=self.root/('chosen-output-'+'x'*50)/('native-validation-'+'y'*50);deep.mkdir(parents=True)
        profile=backend.profile_directory({'project':str(project)},deep)
        self.assertEqual(profile.parent,(private/'editor-profiles').resolve());self.assertFalse(profile.is_relative_to(deep.resolve()))

    def test_unprepared_project_profile_root_is_rejected(self):
        project=self.root/'unprepared';project.mkdir();(project/'.lotraAI-build').write_bytes(b'preserve existing user file')
        with self.assertRaisesRegex(ValueError,'Prepared project private root'):
            backend.profile_directory({'project':str(project)},self.directory)
        self.assertEqual((project/'.lotraAI-build').read_bytes(),b'preserve existing user file')

    def test_actual_controller_uses_project_profile_for_detached_operation(self):
        project=self.root/'prepared';(project/'.lotraAI-build').mkdir(parents=True)
        result,_=self.simulate(project=project)
        self.assertEqual(Path(result['profile']).parent,(project/'.lotraAI-build/editor-profiles').resolve())

    def test_early_server_exit_fails_without_waiting_for_connection_timeout(self):
        with self.assertRaisesRegex(backend.BackendError,'server exited before completion'):
            self.simulate(ack=False,server_exited=True)


if __name__=='__main__':unittest.main()
