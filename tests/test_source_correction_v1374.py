"""A sealed original retains a finite evidenced correction route before binding."""
import copy,unittest
from unittest.mock import patch
import test_workflow_v137 as previous
from core import agent_runtime as a,incremental_contract as inc,workflow_guard as guard
from core.common import identity,read_json

class SourceCorrection(unittest.TestCase):
    def setUp(self):
        fixture=previous.Protocol();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.f=fixture;self.task=fixture.task;fixture.observed()

    def request(self):
        state=self.f.state();value=inc.load(self.task,state);before=value['features'][0]
        after=copy.deepcopy(before);after['requirements']=['editable']
        return {'operation':'source_correction','chunk_id':'source-correction-1',
            'prior_checkpoint':state['incremental_contract'],'prior_observation':state['source_feature_observation'],
            'revision_reason':'Independent original reinspection corrects the feature requirement.',
            'corrections':{'features/'+before['id']:{'prior_hash':identity(before),'reason':'Located source correction',
                'source_evidence':'Original left region, retained visible editable shape'}},
            'source_corrections':[{'feature':before['id'],'source_evidence':'Independent original left region'}],
            'observation':{'features':[after],'observations':'Corrected source requirement after original reinspection.'}}

    def test_prebind_correction_retains_original_history_and_binding_chunks(self):
        self.f.send({'operation':'bind_chunk','chunk_id':'partial-binding','binding':{'scene':{'objects':[]}}},'component_contract')
        state=self.f.state();old=state['source_feature_observation'];value=inc.load(self.task,state)
        result=self.f.send(self.request(),'component_contract')
        self.assertEqual(result['status'],'SOURCE_CORRECTION_SEALED');current=self.f.state()
        self.assertIn(old,current['source_observation_history']);self.assertNotEqual(old,current['source_feature_observation'])
        changed=inc.load(self.task,current);self.assertEqual(changed['binding_chunks'],value['binding_chunks'])
        self.assertEqual(len(changed['units']),2);self.assertEqual(len(changed['features']),2)
        self.assertFalse(changed['binding_sealed']);self.assertTrue(changed['source_sealed'])
        self.assertIsNone(current.get('component_workflow'));self.assertFalse(any(self.task.rglob('*.pptx')))

    def test_stale_checkpoint_cannot_revise_frozen_observation(self):
        request=self.request();request['prior_checkpoint']={'path':'old','sha256':'old'}
        with self.assertRaisesRegex(ValueError,'exact current checkpoint'):self.f.send(request,'component_contract')

    def test_missing_prior_row_hash_is_rejected_atomically(self):
        request=self.request();request['corrections']['features/left.outline']['prior_hash']='old'
        before=self.f.state()['source_feature_observation']
        with self.assertRaisesRegex(ValueError,'Frozen row conflict'):self.f.send(request,'component_contract')
        self.assertEqual(self.f.state()['source_feature_observation'],before)

    def test_weakened_feature_still_requires_original_domain_correction(self):
        request=self.request();request.pop('source_corrections')
        with self.assertRaisesRegex(ValueError,'Retain frozen feature targets'):self.f.send(request,'component_contract')

    def test_bind_packet_does_not_grant_unvalidated_original_writes(self):
        state=self.f.state();packet={'packet_id':'current','source':state['source']['sha256'],'revision':0,
            'kind':'component_contract_source','target':'component_contract'};state['packet']=packet
        with guard.packet_writer(self.task,state,packet):
            with self.assertRaisesRegex(ValueError,'current source-feature'):guard.require(self.task,'original observation')

    def test_binding_packet_advertises_current_correction_dependencies(self):
        state=self.f.state();packet={'packet_id':'current','kind':'component_contract_source','target':'component_contract'}
        inc.template(self.task,state,packet)
        self.assertIn('source_correction',packet['incremental']['allowed_operations'])
        self.assertEqual(packet['incremental']['source_correction']['prior_observation'],state['source_feature_observation'])

    def focused(self):
        from core import component_workflow as workflow
        state=self.f.state();state['component_workflow']={'ledger_path':'scratch/ledger.json'}
        packet={'packet_id':'focused','source':state['source']['sha256'],'revision':0,'kind':'component_local_work',
            'target':'left','submit_operation':'source_or_measurement_decision'}
        state['packet']=packet;a._save(self.task,state)
        contract={'workflow_version':'1.35.2','feature_bindings':[{'feature':'left.outline','component':'left'},
            {'feature':'right.outline','component':'right'}]}
        request=self.request();request['source_correction']={'prior_observation':request['prior_observation'],
            'features':request['observation']['features'],'corrections':request['corrections']}
        return state,packet,contract,request

    def test_postbind_feature_correction_preserves_history_and_requires_rebind(self):
        from core import component_source_features as features,component_workflow as workflow
        state,packet,contract,request=self.focused();prior=state['source_feature_observation']
        def save_ledger(task,current,*args,**kwargs):a._save(task,current)
        with patch.object(workflow,'_load',return_value=(contract,{})),patch.object(workflow,'_save_ledger',side_effect=save_ledger),guard.packet_writer(self.task,state,packet):
            result=features.correct_features(self.task,state,contract,request,{'left'})
        self.assertFalse(result['native_write']);current=self.f.state()
        self.assertTrue(current['source_observation_rebind_required']);self.assertIn(prior,current['source_observation_history'])
        observed=read_json(self.task/current['source_feature_observation']['path'])
        self.assertEqual(len(observed['units']),2);self.assertEqual(len(observed['features']),2)

    def test_postbind_correction_cannot_escape_component_features(self):
        from core.component_source_features import correct_features
        state,packet,contract,request=self.focused();request['source_correction']['features'][0]['id']='right.outline'
        with guard.packet_writer(self.task,state,packet),self.assertRaisesRegex(ValueError,'escaped the selected component'):
            correct_features(self.task,state,contract,request,{'left'})

    def test_postbind_correction_needs_current_observation_identity(self):
        from core.component_source_features import correct_features
        state,packet,contract,request=self.focused();request['source_correction']['prior_observation']={'path':'old','sha256':'old'}
        with guard.packet_writer(self.task,state,packet),self.assertRaisesRegex(ValueError,'current prior observation'):
            correct_features(self.task,state,contract,request,{'left'})

    def test_evaluate_packet_cannot_grant_postbind_original_correction(self):
        from core.component_source_features import correct_features
        state,packet,contract,request=self.focused();packet['submit_operation']='evaluate';state['packet']=packet
        with guard.packet_writer(self.task,state,packet),self.assertRaisesRegex(ValueError,'current focused source decision'):
            correct_features(self.task,state,contract,request,{'left'})

    def alternative(self,target='left'):
        from core import component_workflow as workflow
        state=self.f.state();state['objectives'].update(context_chars=9000)
        with patch.object(a,'_preview',return_value=[]):packet=a._packet(self.task,state,'component_local_work','left','Inspect current source',
            extra={'submit_operation':'evaluate','component_action':{'operation':'evaluate'},'component_batch':['left']})
        from core.packet_compaction import restore
        packet=restore(self.task,packet);payload=read_json(self.task/packet['submission_template']['path'])
        payload['operation']='source_or_measurement_decision';payload['component_request']={'component':target,'revision_reason':'Located original reinspection'}
        return payload

    def test_advertised_source_alternative_gets_a_focused_bind_grant(self):
        from core import component_workflow as workflow
        payload=self.alternative()
        def decide(task,operation,request):
            self.assertEqual(operation,'source_or_measurement_decision');guard.require(task,'bind')
            with self.assertRaisesRegex(ValueError,'current source-feature'):guard.require(task,'original observation')
            return {'status':'FOCUSED_SOURCE_HANDLER'}
        with patch.object(workflow,'dispatch',side_effect=decide):
            self.assertEqual(a.submit(self.task,payload)['status'],'FOCUSED_SOURCE_HANDLER')

    def test_source_alternative_cannot_expand_the_visible_component_batch(self):
        from core import component_workflow as workflow
        payload=self.alternative('right')
        with patch.object(workflow,'dispatch') as dispatch,self.assertRaisesRegex(ValueError,'packet-selected component'):
            a.submit(self.task,payload)
        dispatch.assert_not_called()

if __name__=='__main__':unittest.main()
