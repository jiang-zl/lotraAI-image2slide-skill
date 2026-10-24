"""Source-owned glyph grouping distinguishes internal whitespace from tracking."""
import copy,sys,unittest
from pathlib import Path
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/lotra-image2slide-skill/scripts'))
from core import text_appearance as text

class SpacingGroups(unittest.TestCase):
    def fixture(self,count=4,limit=2):
        source=Image.new('RGB',(80,130),'white');draw=ImageDraw.Draw(source)
        for i in range(count):draw.rectangle([20,20+i*20,29,31+i*20],fill='black')
        feature={'id':'label','kind':'text','roi':[20,20,10,12+(count-1)*20],
                 'text_appearance':{'source_evidence':'Owned original source groups','isolation':'Black complete glyph boxes on white',
                    'colours':['000000'],'colour_tolerance':.1,'spacing_axis':'vertical','limits':{k:limit for k in ('width','height','baseline','spacing')}}}
        grouped=copy.deepcopy(feature);grouped['text_appearance']['spacing_groups']={'logical_text':'ABCD'[:count],'observer':'host_model',
            'source_evidence':'Independently authored source glyph identity, boundaries and logical order',
            'groups':[{'span':[i,i+1],'roi':[20,20+i*20,10,12],'source_evidence':'Complete original glyph '+str(i)} for i in range(count)]}
        return source,feature,grouped

    def test_internal_glyph_band_is_retained_but_not_counted_as_tracking(self):
        actual,raw,grouped=self.fixture();source=actual.copy();ImageDraw.Draw(source).line((20,65,29,65),fill='white')
        old=text.compare(source,actual,raw);self.assertFalse(old['passed']);self.assertTrue(old['valid'])
        result=text.compare(source,actual,grouped)
        self.assertTrue(result['passed']);self.assertEqual(result['source']['projection_spacing'],[8,8,1,8])
        self.assertEqual(result['source']['spacing'],[8,8,8]);self.assertEqual(result['render']['spacing'],[8,8,8])
        self.assertEqual(len([row for row in result['checks'] if row['field'].startswith('group.')]),24)
        self.assertTrue(result['render']['group_plan']['all_ink_owned']);self.assertFalse(result['candidate_alignment'])

    def test_real_inter_group_spacing_change_keeps_frozen_limits_and_fails(self):
        source,_,grouped=self.fixture();grouped['roi'][3]+=4;actual=source.copy();draw=ImageDraw.Draw(actual)
        draw.rectangle([20,80,29,91],fill='white');draw.rectangle([20,84,29,95],fill='black')
        result=text.compare(source,actual,grouped);self.assertFalse(result['passed'])
        check=next(row for row in result['checks'] if row['field']=='spacing')
        self.assertEqual(check['threshold'],2);self.assertEqual(check['value'],4)

    def test_missing_native_glyph_cannot_be_hidden_by_group_partition(self):
        source,_,grouped=self.fixture();actual=source.copy();ImageDraw.Draw(actual).rectangle([20,60,29,71],fill='white')
        result=text.compare(source,actual,grouped);self.assertFalse(result['passed']);self.assertTrue(result['valid'])
        self.assertIn('SEPARATION_REQUIRED',result['reason'])

    def test_unowned_original_ink_is_invalid_instead_of_excluded(self):
        source,_,grouped=self.fixture();ImageDraw.Draw(source).point((19,65),fill='black')
        with self.assertRaisesRegex(ValueError,'TEXT_GROUP_COVERAGE_REQUIRED'):text.compare(source,source,grouped)

    def test_two_native_boundary_candidates_need_measurement_decision(self):
        source,_,grouped=self.fixture(2,6);actual=source.copy();ImageDraw.Draw(actual).line((20,30,29,30),fill='white')
        result=text.compare(source,actual,grouped);self.assertFalse(result['passed']);self.assertFalse(result['valid'])
        self.assertIn('TEXT_GROUP_RENDER_AMBIGUOUS',result['reason'])

    def test_source_groups_cannot_omit_spans_or_overlap(self):
        source,_,grouped=self.fixture();broken=copy.deepcopy(grouped);broken['text_appearance']['spacing_groups']['groups'][2]['span']=[1,3]
        with self.assertRaisesRegex(ValueError,'consecutive'):text.validate(broken)
        broken=copy.deepcopy(grouped);broken['text_appearance']['spacing_groups']['groups'][2]['roi'][1]=45
        with self.assertRaisesRegex(ValueError,'disjoint'):text.validate(broken)

    def test_whole_bbox_agreement_cannot_hide_a_narrowed_individual_glyph(self):
        source,_,grouped=self.fixture();actual=source.copy();draw=ImageDraw.Draw(actual)
        draw.rectangle([20,60,29,71],fill='white');draw.rectangle([23,60,26,71],fill='black')
        result=text.compare(source,actual,grouped);self.assertFalse(result['passed'])
        self.assertTrue(all(row['passed'] for row in result['checks'] if row['field'] in ('width','height','baseline','spacing')))
        self.assertFalse(next(row for row in result['checks'] if row['field']=='group.2.width')['passed'])

    def test_centered_whole_block_cannot_hide_a_shifted_internal_row(self):
        source,_,grouped=self.fixture();source.paste('white',(0,0,*source.size));draw=ImageDraw.Draw(source)
        grouped['roi'][2]=20
        for index,group in enumerate(grouped['text_appearance']['spacing_groups']['groups']):
            x,width=(26,8) if index==1 else (20,20)
            y=20+index*20;draw.rectangle([x,y,x+width-1,y+11],fill='black');group['roi']=[x,y,width,12]
        actual=source.copy();draw=ImageDraw.Draw(actual);draw.rectangle([26,40,33,51],fill='white');draw.rectangle([29,40,36,51],fill='black')
        result=text.compare(source,actual,grouped);self.assertFalse(result['passed'])
        self.assertTrue(all(row['passed'] for row in result['checks'] if not row['field'].startswith('group.')))
        check=next(row for row in result['checks'] if row['field']=='group.1.ink_center_x')
        self.assertEqual(check['value'],3);self.assertFalse(check['passed'])

if __name__=='__main__':unittest.main()
