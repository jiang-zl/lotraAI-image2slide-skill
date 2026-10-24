"""Independent source support and explicit non-vacuous applicability."""
import copy
from pathlib import Path
import sys
import unittest
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/lotra-image2slide-skill/scripts'))
from core import source_preflight
from test_line_evidence_v1372 import source_line


class SourceReview(unittest.TestCase):
    def observation(self):
        return {'source_hash':'frozen-original','units':[{'id':'panel','parent':None,
            'appearance_review':{domain:{'decision':'absent' if domain=='depth' else 'present',
                'source_evidence':'Observed original surface'} for domain in ('fill','depth','corners')}}],
            'features':[{'id':'panel.surface','unit':'panel','kind':'surface','form':'freeform','roi':[30,20,600,70]}],
            'spatial':{'relations':[],'footprints':[]},'layout_review':{domain:{'decision':'not_applicable',
                'source_evidence':'Single independent surface with no relational layout'} for domain in ('alignment','containment','connections')}}

    def test_zero_relations_require_an_original_applicability_decision(self):
        value=self.observation();value.pop('layout_review')
        report=source_preflight.evaluate(Image.new('RGB',(720,140),'white'),value)
        self.assertFalse(report['passed'])
        self.assertEqual(sum(row['reason']=='LAYOUT_APPLICABILITY_REQUIRED' for row in report['issues']),3)

    def test_absent_depth_does_not_force_a_shadow(self):
        report=source_preflight.evaluate(Image.new('RGB',(720,140),'white'),self.observation())
        self.assertTrue(report['passed'],report)

    def test_silhouette_cannot_skip_material_applicability(self):
        value=self.observation();value['features'][0]['kind']='silhouette'
        value['units'][0].pop('appearance_review')
        report=source_preflight.evaluate(Image.new('RGB',(720,140),'white'),value)
        self.assertEqual(sum(row['reason']=='MATERIAL_APPLICABILITY_REQUIRED' for row in report['issues']),3)

    def test_claimed_depth_requires_an_owned_source_feature(self):
        value=self.observation();value['units'][0]['appearance_review']['depth']['decision']='present'
        report=source_preflight.evaluate(Image.new('RGB',(720,140),'white'),value)
        self.assertFalse(report['passed'])
        self.assertIn('VISIBLE_DEPTH_FEATURES_REQUIRED',{row['reason'] for row in report['issues']})

    def test_wrong_frozen_route_is_not_called_unobservable_photo(self):
        image=Image.new('RGB',(200,120),'white');ImageDraw.Draw(image).line([(80,20),(80,90)],fill='black',width=2)
        line=source_line(((72,20),(72,90)));line['limits']['route']=.5
        row=source_preflight.line_support(image,{'id':'route','line':line})
        self.assertFalse(row['passed']);self.assertGreater(row['unsupported_samples'],40)
        line['path']['segments'][0]['points']=[[80,20],[80,90]]
        self.assertTrue(source_preflight.line_support(image,{'id':'route','line':line})['passed'])

    def test_source_rectangle_can_challenge_a_wrong_plan_left_edge(self):
        image=Image.new('RGB',(720,140),'white');ImageDraw.Draw(image).rectangle((30,20,630,90),fill='gray')
        feature={'id':'panel','roi':[100,20,600,70],'form':'rect'}
        report=source_preflight.rectangle_support(image,feature)
        self.assertTrue(report['located_reinspection_required'],report)
        self.assertLess(abs(report['edge_candidates'][0]['x']-30),3)
        self.assertEqual(feature['roi'],[100,20,600,70])

    def test_declared_alignment_without_relations_is_not_pass(self):
        value=self.observation();value['layout_review']['alignment']['decision']='declared'
        report=source_preflight.evaluate(Image.new('RGB',(720,140),'white'),value)
        self.assertIn('DECLARED_LAYOUT_RELATION_MISSING',{row['reason'] for row in report['issues']})

    def test_old_task_is_not_silently_migrated(self):
        self.assertFalse(source_preflight.enabled({'font_workflow_policy':'font-workflow-1.37.4'}))


if __name__=='__main__':unittest.main()
