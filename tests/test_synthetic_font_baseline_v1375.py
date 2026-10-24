"""A comparison baseline cannot invalidate an evidenced synthetic font choice."""
import importlib,sys,unittest
from pathlib import Path
from fontTools.ttLib import TTFont
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/lotra-image2slide-skill/scripts'))
from core import font_collection as collection,font_contract as fonts,font_resources as resources,font_resolution as resolution
from core.common import digest

class SyntheticBaseline(unittest.TestCase):
    def setUp(self):
        fixture=importlib.import_module('test_font_steps_v1374').FontSteps();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.fx=fixture;self.scene=fixture.scene;self.state=fixture.state
        self.scene['objects'][0]['style']['bold']=True
        old=fixture.faces[fixture.fixture.old['id']];path=Path(old['path'])
        with TTFont(path) as font:
            font['OS/2'].usWeightClass=700;font['OS/2'].fsSelection|=32;font['head'].macStyle|=1
            font['OS/2'].panose.bFamilyType=2;font['OS/2'].panose.bSerifStyle=11;font.save(path)
        old.update(resources.describe(path,0,digest(path)))
        self.old=old;self.new=fixture.faces[fixture.fixture.new['id']]
        self.request=fonts.requests(self.scene,self.state)[0]
        self.state['font_contract']={'bindings':{self.request['id']:{'resource':self.old}}}

    def scope(self,synthetic=True,ids=None):
        self.state['font_constraints']={self.request['id']:{'source_hash':self.state['source']['sha256'],
            'request_hash':resolution.request_key(self.request),'style_classes':['sans'],
            'resource_ids':ids or [self.new['id']],'synthetic_style':synthetic}}

    def test_old_real_face_cannot_suppress_explicitly_scoped_synthetic_candidate(self):
        self.scope()
        current={face['id'] for face in collection.eligible(self.state,self.request,extend=True)}
        self.assertEqual(current,{self.old['id'],self.new['id']})

    def test_binding_set_does_not_adopt_out_of_scope_comparison_baseline(self):
        self.scope()
        current={face['id'] for face in collection.eligible(self.state,self.request)}
        self.assertEqual(current,{self.new['id']})

    def test_unapproved_simulation_is_still_ineligible(self):
        self.scope(synthetic=False)
        current={face['id'] for face in collection.eligible(self.state,self.request,extend=True)}
        self.assertNotIn(self.new['id'],current)

    def test_real_face_priority_still_applies_inside_current_scope(self):
        self.scope(ids=[self.old['id'],self.new['id']])
        current={face['id'] for face in collection.eligible(self.state,self.request,extend=True)}
        self.assertEqual(current,{self.old['id']})

    def test_source_style_preflight_accepts_only_evidenced_synthetic_resource(self):
        value={'style_group':'revised.source.sans','style_classes':['sans'],'resource_ids':[self.new['id']],
            'synthetic_style':True,'style_description':'Located bold sans source strokes; regular physical face uses explicit native simulated bold',
            'evidence':self.fx.proof,'reason':'A wider observed sans design while retaining the old real face for independent comparison'}
        collection.store_constraints(self.fx.task,self.state,self.scene,{self.request['id']:value})
        stored=self.state['font_constraints'][self.request['id']]
        self.assertTrue(stored['synthetic_style']);self.assertEqual(stored['resource_ids'],[self.new['id']])
        self.assertEqual({row['id'] for row in collection.eligible(self.state,self.request)},{self.new['id']})


if __name__=='__main__':unittest.main()
