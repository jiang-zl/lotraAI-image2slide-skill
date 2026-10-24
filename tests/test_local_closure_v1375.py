from pathlib import Path
import copy,sys,unittest
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/lotra-image2slide-skill/scripts'))
from core import component_actions as actions,component_protocol as protocol,text_appearance as text


class LocalClosure(unittest.TestCase):
    def fixture(self):
        row={'id':'label','route':'fixed_parameters','owners':['label'],'parameters':{},'feature_basis':'basis'}
        contract={'source_review_policy':'source-review-1.37.5','components':[row],
            'policy':{'stage_order':['source','measurement','structure','fit','assembly','instance']},'relations':[]}
        ledger={'components':{'label':{'status':'QUALIFIED','observed_measurement_signature':{'body':'saved'}}},
                'layout_ready':True}
        return row,contract,ledger

    def test_fixed_native_pass_still_requires_local_appearance(self):
        row,contract,ledger=self.fixture()
        self.assertEqual(actions.available(contract,ledger,{'preview':{}})[0]['operation'],'review_local')
        ready=protocol.ready_for_final(contract,ledger)
        self.assertFalse(ready['ready']);self.assertEqual(ready['appearance_pending'],['label'])

    def test_current_local_review_is_retained_until_own_measurement_changes(self):
        row,contract,ledger=self.fixture();record=ledger['components']['label']
        record['appearance_review']={'passed':True,'signature':copy.deepcopy(record['observed_measurement_signature']),'feature_basis':'basis'}
        self.assertEqual(actions.available(contract,ledger,{}),[])
        self.assertTrue(protocol.ready_for_final(contract,ledger)['ready'])
        record['observed_measurement_signature']['body']='changed'
        self.assertEqual(actions.available(contract,ledger,{})[0]['operation'],'review_local')

    def test_old_contract_is_not_silently_migrated(self):
        row,contract,ledger=self.fixture();contract.pop('source_review_policy')
        self.assertEqual(actions.available(contract,ledger,{}),[])
        self.assertTrue(protocol.ready_for_final(contract,ledger)['ready'])

    def test_unreviewed_mother_cannot_be_reused(self):
        row,contract,ledger=self.fixture()
        contract['components'].append({'id':'copy','route':'instance','owners':['copy'],'mother':'label'})
        ledger['components']['copy']={'status':'PENDING'}
        self.assertEqual([v['id'] for v in actions.available(contract,ledger,{})],['label'])

    def test_formal_delivery_requires_new_gates_only_for_the_bound_new_policy(self):
        from core.workflow_delivery import required_gates
        old=required_gates({})
        current=required_gates({'source_review_policy':'source-review-1.37.5','reconstruction_target':{'path':'mapping','sha256':'frozen'}})
        self.assertEqual(current-old,{'source_observation_support','whole_string_ink','reconstruction_target'})
        self.assertEqual(len(old),12)


class WholeStringInk(unittest.TestCase):
    def feature(self):
        return {'id':'title','kind':'text','roi':[20,20,168,20],
                'text_appearance':{'source_evidence':'Original complete word silhouette','isolation':'Red title without touching other foreground',
                    'colours':['FF0000'],'colour_tolerance':.1,'limits':{'width':2,'height':2,'baseline':2,'spacing':2}}}
    def image(self,width=168,shift=0):
        image=Image.new('RGB',(240,80),'white');ImageDraw.Draw(image).rectangle([20,20+shift,19+width,39+shift],fill='red');return image

    def test_unchanged_string_passes_optical_dimensions(self):
        self.assertTrue(text.compare(self.image(),self.image(),self.feature())['passed'])

    def test_correct_frame_with_narrower_string_cannot_pass(self):
        result=text.compare(self.image(),self.image(143),self.feature())
        self.assertFalse(result['passed']);self.assertEqual(result['checks'][0]['value'],25)

    def test_shifted_baseline_fails_without_alignment_to_candidate(self):
        self.assertFalse(text.compare(self.image(),self.image(shift=4),self.feature())['passed'])

    def test_boundary_contamination_requires_source_decision(self):
        image=self.image();ImageDraw.Draw(image).rectangle([16,20,23,40],fill='red')
        with self.assertRaisesRegex(ValueError,'ISOLATION_REQUIRED'):text.ink(image,self.feature())


if __name__=='__main__':unittest.main()
