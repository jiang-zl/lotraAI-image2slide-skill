"""A newly located original obligation has a lawful, scoped repair packet."""
import copy,unittest
from unittest.mock import patch
import test_source_correction_v1374 as prior_tests
from core import agent_runtime as a,component_source_features as features,component_workflow as c
from core import workflow_guard as guard,source_preflight as preflight
from core.common import identity,read_json,write_json


class PreflightRecovery(unittest.TestCase):
    def setUp(self):
        setup=prior_tests.SourceCorrection();setup.setUp();self.addCleanup(setup.doCleanups)
        self.f=setup.f;self.task=setup.task
        state,packet,contract,request=setup.focused()
        observed=read_json(self.task/state['source_feature_observation']['path'])
        observed['layout_review']={key:{'decision':'not_applicable','source_evidence':'Independent original regions'}
                                   for key in ('alignment','containment','connections')}
        for row in observed['features']:row['form']='freeform'
        observed['units'][0]['appearance_review']=self.review()
        file=self.task/'source/Retained-before-material-review.json';write_json(file,observed)
        state['source_feature_observation']=a._file(self.task,file);state['source_review_policy']=preflight.POLICY
        state['objectives']['context_chars']=9000
        contract['components']=[{'id':name,'source_units':[name]} for name in ('left','right')]
        self.contract=contract;self.ledger={'pending_decision':{'kind':'earlier-banner-failure'}}
        self.packet=packet;self.observed=observed;self.prior=state['source_feature_observation']
        request['source_correction']['prior_observation']=self.prior
        request['source_correction']['features'][0]=copy.deepcopy(observed['features'][0])
        request['source_correction']['features'][0]['requirements']=['editable']
        request['source_correction']['corrections']['features/left.outline']['prior_hash']=identity(observed['features'][0])
        self.request=request;a._save(self.task,state)
        self.addCleanup(patch.stopall)
        patch.object(c,'_load',return_value=(self.contract,self.ledger)).start()
        patch.object(c,'_save_ledger',side_effect=lambda task,state,*args,**kwargs:a._save(task,state)).start()
        patch.object(c,'component_row',side_effect=lambda task,state,contract,name:{'id':name}).start()
        self.reserve=patch('core.problem_control.reserve').start()

    def review(self):
        return {key:{'decision':'absent' if key=='depth' else 'present','source_evidence':'Located flat original surface and sharp corners'}
                for key in ('fill','depth','corners')}

    def queue(self):
        state=self.f.state()
        with guard.packet_writer(self.task,state,self.packet):
            return features.correct_features(self.task,state,self.contract,self.request,{'left'})

    def correction(self):
        value=copy.deepcopy(self.observed);value['units'][1]['appearance_review']=self.review()
        value['observations']+='; Independent reinspection supplies right material applicability.'
        return {'observation':value,'prior_observation':self.prior,'revision_reason':'Original right surface lacked explicit applicability',
            'corrections':{'units/right':{'prior_hash':identity(self.observed['units'][1]),
                'reason':'Located material decisions','source_evidence':'Complete right flat source region'}}}

    def send(self,request):
        state=self.f.state();packet={'packet_id':'preflight-source','source':state['source']['sha256'],'revision':0,
            'kind':'component_contract_source','target':'source_features'}
        state['packet']=packet;a._save(self.task,state)
        with guard.packet_writer(self.task,state,packet):return features.observe(self.task,request)

    def test_unrelated_retained_failure_queues_without_adopting_proposal(self):
        result=self.queue();state=self.f.state()
        self.assertEqual(result['status'],'SOURCE_PREFLIGHT_REVIEW_REQUIRED')
        self.assertFalse(result['acceptance']);self.assertFalse(result['native_write'])
        self.assertEqual(state['source_feature_observation'],self.prior)
        self.assertFalse(state.get('source_observation_history'))
        self.assertEqual(state['spatial_source_decision']['components'],['right'])
        self.assertIsNone(state['packet']);self.assertEqual(self.ledger['pending_decision']['kind'],'earlier-banner-failure')
        self.assertFalse(any(self.task.rglob('*.pptx')))

    def test_next_exposes_existing_original_phase_and_exact_diagnostic(self):
        self.queue();state=self.f.state()
        with patch.object(a,'_preview',return_value=[]),patch('core.problem_control.remaining',return_value=1):
            result=c.next_action(self.task,state)
        packet=result['packet'];self.assertEqual(packet['kind'],'component_contract_source')
        self.assertEqual(packet['target'],'source_features');self.assertNotIn('incremental',packet)
        self.assertIn('prior_hash',packet['objective'])
        self.assertEqual(packet['spatial_source_decision']['prior_observation'],self.prior)

    def test_correct_material_metadata_retains_history_and_requires_rebind(self):
        self.queue();result=self.send(self.correction());state=self.f.state()
        self.assertEqual(result['status'],'SOURCE_FEATURES_OBSERVED')
        self.assertIn(self.prior,state['source_observation_history'])
        self.assertNotIn('spatial_source_decision',state);self.assertTrue(state['source_observation_rebind_required'])
        self.assertTrue(self.ledger['source_observation_dirty']);self.assertTrue(self.ledger['final_dirty'])
        self.reserve.assert_called_once()
        current=read_json(self.task/state['source_feature_observation']['path'])
        self.assertEqual(current['features'],self.observed['features'])
        self.assertEqual(current['units'][0],self.observed['units'][0])

    def test_stale_observation_cannot_use_recovery_grant(self):
        self.queue();request=self.correction();request['prior_observation']={'path':'old','sha256':'old'}
        with self.assertRaisesRegex(ValueError,'exact retained prior observation'):self.send(request)
        self.assertEqual(self.f.state()['source_feature_observation'],self.prior)

    def test_unrelated_feature_cannot_change_under_material_review(self):
        self.queue();request=self.correction();request['observation']['features'][0]['requirements']=['editable']
        with self.assertRaisesRegex(ValueError,'escaped the diagnosed features'):self.send(request)

    def test_material_review_cannot_change_source_roi(self):
        self.queue();request=self.correction();request['observation']['units'][1]['roi']=[51,0,49,100]
        with self.assertRaisesRegex(ValueError,'diagnosed unit material domains'):self.send(request)

    def test_missing_row_hash_cannot_relabel_source(self):
        self.queue();request=self.correction();request['corrections']['units/right'].pop('prior_hash')
        with self.assertRaisesRegex(ValueError,'exact prior hashes'):self.send(request)

    def test_unresolved_depth_stays_failure_without_resetting_decision(self):
        self.queue();request=self.correction();request['observation']['units'][1]['appearance_review']['depth']['decision']='present'
        with self.assertRaisesRegex(ValueError,'VISIBLE_DEPTH_FEATURES_REQUIRED'):self.send(request)
        state=self.f.state();self.assertEqual(state['source_feature_observation'],self.prior)
        self.assertEqual(state['spatial_source_decision']['kind'],'source_preflight')

    def test_invalid_new_proposal_cannot_escalate_a_valid_retained_observation(self):
        observed=copy.deepcopy(self.observed);observed['units'][1]['appearance_review']=self.review()
        file=self.task/'source/Valid-retained.json';write_json(file,observed)
        state=self.f.state();state['source_feature_observation']=a._file(self.task,file);a._save(self.task,state)
        request=copy.deepcopy(self.request);request['source_correction']['prior_observation']=state['source_feature_observation']
        request['source_correction']['features'][0].pop('form')
        with guard.packet_writer(self.task,state,self.packet),self.assertRaisesRegex(ValueError,'ORIGINAL_SURFACE_FORM_REQUIRED'):
            features.correct_features(self.task,state,self.contract,request,{'left'})
        self.assertNotIn('spatial_source_decision',self.f.state())


if __name__=='__main__':unittest.main()
