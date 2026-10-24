from pathlib import Path
import copy,sys,tempfile,unittest
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/lotra-image2slide-skill/scripts'))
from core import capture_target as target,branch_plan
from core.common import digest,read_json,write_json
from test_line_evidence_v1372 import source_line


class CaptureTarget(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        (self.root/'source').mkdir();self.raw=self.root/'source/original.png'
        image=Image.new('RGB',(240,160),'black');ImageDraw.Draw(image).polygon([(20,20),(220,30),(210,140),(30,130)],fill='white');image.save(self.raw)
        self.authority=self.root/'source/authority.txt';self.authority.write_text('Explicit test user request: reconstruct slide plane at documented 16:9 ratio.')
    def plan(self):
        return {'schema':target.POLICY,'kind':'slide_surface','raw_source_hash':digest(self.raw),'observer':'host_model',
                'corners':[[20,20],[220,30],[210,140],[30,130]],'output_size':[176,99],
                'aspect_ratio_basis':'user_authority','source_uncertainty_px':.5,'source_evidence':'Independent original slide corners',
                'authorization':{'path':'source/authority.txt','sha256':digest(self.authority)}}
    def state(self,plan):
        source,size,ref=target.freeze(self.root,self.raw,plan)
        return {'source':source,'source_size':size,'reconstruction_target':ref}

    def test_default_preserves_every_original_pixel_and_offset(self):
        before=digest(self.raw);plan=target.validate(None,[240,160],before,self.root);state=self.state(plan)
        self.assertEqual(state['source']['sha256'],before);self.assertEqual(state['source_size'],[240,160])
        self.assertEqual(target.verify(self.root,state)['target'],'source_projection')

    def test_authorized_plane_has_inverse_mapping_and_independent_recomputation(self):
        plan=target.validate(self.plan(),[240,160],digest(self.raw),self.root);state=self.state(plan)
        result=target.verify(self.root,state);self.assertTrue(result['passed'])
        mapping=read_json(self.root/state['reconstruction_target']['path'])
        actual=target.transform(plan['corners'],mapping['raw_to_target'])
        np.testing.assert_allclose(actual,[[0,0],[176,0],[176,99],[0,99]],atol=1e-8)
        self.assertGreater(mapping['propagated_source_uncertainty_px'],0)

    def test_quadrilateral_alone_cannot_authorize_ratio_or_crop(self):
        plan=self.plan();plan.pop('authorization')
        with self.assertRaisesRegex(ValueError,'AUTHORIZATION_REQUIRED'):target.validate(plan,[240,160],digest(self.raw),self.root)
        plan=self.plan();plan['aspect_ratio_basis']='looks_rectangular'
        with self.assertRaisesRegex(ValueError,'ASPECT_AUTHORITY_REQUIRED'):target.validate(plan,[240,160],digest(self.raw),self.root)

    def test_crossed_corners_and_manufactured_resolution_are_rejected(self):
        plan=self.plan();plan['corners'][1],plan['corners'][2]=plan['corners'][2],plan['corners'][1]
        with self.assertRaisesRegex(ValueError,'CORNERS_REQUIRED'):target.validate(plan,[240,160],digest(self.raw),self.root)
        plan=self.plan();plan['output_size']=[1760,990]
        with self.assertRaisesRegex(ValueError,'INFORMATION_BOUND'):target.validate(plan,[240,160],digest(self.raw),self.root)

    def test_relabeling_a_modified_derived_source_cannot_pass(self):
        state=self.state(self.plan());file=self.root/state['source']['path']
        image=Image.open(file).convert('RGB');image.putpixel((50,50),(255,0,0));image.save(file)
        mapping_file=self.root/state['reconstruction_target']['path'];mapping=read_json(mapping_file)
        mapping['target_source']['sha256']=digest(file);state['source']['sha256']=digest(file)
        write_json(mapping_file,mapping);state['reconstruction_target']['sha256']=digest(mapping_file)
        with self.assertRaisesRegex(ValueError,'not the frozen'):target.verify(self.root,state)

    def test_old_task_has_no_implicit_target_migration(self):
        self.assertFalse(target.verify(self.root,{})['applicable'])


class BranchPlanning(unittest.TestCase):
    def observation(self):
        rows=[];junction={'id':'J','point':[80,60],'features':['bus','arm'],'source_evidence':'Original T'}
        for name,points in [('bus',[[20,60],[140,60]]),('arm',[[80,60],[80,70]])]:
            line=source_line(points);line['topology']['junctions']=[copy.deepcopy(junction)]
            rows.append({'id':name,'line':line})
        return {'source_hash':'original','features':rows}
    def test_bus_and_short_arm_keep_separate_complete_edge_obligations(self):
        plan=branch_plan.prepare(self.observation())
        self.assertEqual(plan['coverage']['planned_edge_ids'],['arm:0','bus:0'])
        self.assertTrue(all(r['terminals']==2 for r in plan['routes']))
        self.assertFalse(plan['automatic_native_write']);self.assertFalse(plan['alignment_or_snapping'])
    def test_disagreeing_source_topology_cannot_be_normalized_away(self):
        value=self.observation();value['features'][1]['line']['topology']['junctions'][0]['point']=[81,60]
        with self.assertRaisesRegex(ValueError,'reciprocal topology'):branch_plan.prepare(value)

if __name__=='__main__':unittest.main()
