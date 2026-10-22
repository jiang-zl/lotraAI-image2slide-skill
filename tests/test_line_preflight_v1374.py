"""Actual unsaved writer output compared against independent original lines."""
import copy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'skills/lotra-image2slide-skill/scripts'))
from core import line_preflight
from core.common import digest,identity,write_json


class LinePreflight(unittest.TestCase):
    def setUp(self):
        parent=REPO/'.lotraAI-build/line-plan-tests';parent.mkdir(parents=True,exist_ok=True)
        tmp=tempfile.TemporaryDirectory(dir=parent);self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        Image.new('RGB',(200,120),'white').save(self.root/'original.png')
        write_json(self.root/'evidence.json',{});write_json(self.root/'profile.json',{})
        self.scene={'schema_version':'0.1','revision':0,'canvas':{'width':200,'height':120,'unit':'px','target_width_inches':200/96},
            'source':{'path':'original.png','sha256':digest(self.root/'original.png')},
            'evidence':{'path':'evidence.json','sha256':digest(self.root/'evidence.json')},
            'profile':{'path':'profile.json','sha256':digest(self.root/'profile.json')},'relations':[],'prototypes':[],
            'objects':[{'id':'route','render_type':'connector','semantic_type':'decoration','bbox':[20,20,120,70],
                'content':{'points':[[20,20],[140,20],[140,90]],'arrow':'none'},
                'style':{'stroke':'000000','line_width':1.5,'line_cap':'flat','line_join':'round'},
                'versions':dict.fromkeys(('content','structure','style','placement'),1),
                'locks':dict.fromkeys(('content','structure','style','placement'),False),'evidence_status':'observed'}]}
        source=importlib.import_module('test_line_evidence_v1372').source_line()
        self.spec={'basis':identity('frozen source'),'lines':[{'id':'line','unit':'unit','roi':[10,10,150,90],
            'source':source,'parts':[{'owner':'route','role':'shaft'}],'terminal_sites':{},'component':'diagram'}]}

    def test_valid_plan_uses_actual_emission_without_writing_a_pptx(self):
        before=copy.deepcopy(self.scene)
        report=line_preflight.evaluate(self.scene,self.root,self.spec,[])
        self.assertTrue(report['passed'],report)
        self.assertEqual(self.scene,before);self.assertEqual(list(self.root.glob('*.pptx')),[])
        self.assertEqual(list(self.root.glob('*.build*')),[])

    def test_wrong_join_is_located_before_native_save(self):
        self.spec['lines'][0]['source']['stroke']['join']='miter'
        before=copy.deepcopy(self.spec)
        report=line_preflight.evaluate(self.scene,self.root,self.spec,[])
        self.assertFalse(report['passed']);self.assertEqual(self.spec,before)
        self.assertIn('stroke',[item['criterion'] for item in report['issues']])

    def test_implicit_writer_arrow_is_detected_against_unmarked_original(self):
        self.scene['objects'][0]['content'].pop('arrow')
        report=line_preflight.evaluate(self.scene,self.root,self.spec,[])
        self.assertFalse(report['passed'])
        self.assertIn('markers',[item['criterion'] for item in report['issues']])

    def test_explicit_miter_plan_can_satisfy_miter_original(self):
        self.spec['lines'][0]['source']['stroke']['join']='miter'
        self.scene['objects'][0]['style']['line_join']='miter'
        report=line_preflight.evaluate(self.scene,self.root,self.spec,[])
        self.assertTrue(report['passed'],report)

    def test_wrong_elbow_cannot_pass_same_endpoints(self):
        self.scene['objects'][0]['content']['points']=[[20,20],[20,90],[140,90]]
        report=line_preflight.evaluate(self.scene,self.root,self.spec,[])
        self.assertFalse(report['passed'])
        self.assertIn('route',[item['criterion'] for item in report['issues']])

    def test_missing_shared_topology_is_detected_without_rewriting_source(self):
        second=copy.deepcopy(self.scene['objects'][0]);second['id']='second';self.scene['objects'].append(second)
        line=copy.deepcopy(self.spec['lines'][0]);line['id']='second.line';line['parts'][0]['owner']='second';self.spec['lines'].append(line)
        before=copy.deepcopy(self.spec)
        report=line_preflight.evaluate(self.scene,self.root,self.spec,[])
        self.assertFalse(report['passed']);self.assertEqual(self.spec,before)
        self.assertIn('topology',[item['criterion'] for item in report['issues']])

    def junction(self):
        second=copy.deepcopy(self.scene['objects'][0]);second['id']='peer'
        second['bbox']=[140,90,40,1];second['content']['points']=[[140,90],[180,90]];self.scene['objects'].append(second)
        source=importlib.import_module('test_line_evidence_v1372').source_line([[140,90],[180,90]])
        row=copy.deepcopy(self.spec['lines'][0]);row.update(id='peer.line',source=source,parts=[{'owner':'peer','role':'shaft'}])
        junction={'id':'joint','point':[140,90],'features':['line','peer.line'],'source_evidence':'Original incident shafts'}
        for line in (self.spec['lines'][0],row):line['source']['topology']['junctions']=[copy.deepcopy(junction)]
        self.spec['lines'][0]['source']['ends'][1]['attachment']={'kind':'line_junction','feature':'peer.line',
            'distance':[0,0],'source_evidence':'Original visible shaft incidence without a shape port'}
        self.spec['lines'].append(row)
        bindings=[{'feature':'line','owners':['route']},{'feature':'peer.line','owners':['peer']}]
        features={row['id']:{'id':row['id'],'kind':'internal_line','line':row['source']} for row in self.spec['lines']}
        return bindings,features

    def test_observed_open_line_junction_needs_no_hidden_shape_port(self):
        from core.line_contracts import validate_line,validate_source,POLICY
        bindings,features=self.junction()
        for feature in features.values():validate_line(feature['line'],feature,features)
        from core.component_source_features import KINDS
        self.assertTrue(all(feature['kind'] in KINDS for feature in features.values()))
        validate_source({'features':list(features.values())},{'verification_policy':POLICY})
        report=line_preflight.evaluate(self.scene,self.root,self.spec,bindings)
        self.assertTrue(report['passed'],report)
        check=report['lines']['line']['terminals']
        self.assertTrue(check['passed']);self.assertEqual(len(self.scene['objects']),2)

    def test_gap_to_open_junction_peer_fails_before_save(self):
        bindings,_=self.junction();self.scene['objects'][1]['content']['points']=[[150,90],[190,90]]
        report=line_preflight.evaluate(self.scene,self.root,self.spec,bindings)
        self.assertFalse(report['passed']);self.assertFalse(report['lines']['line']['terminals']['passed'])

    def test_junction_attachment_cannot_replace_missing_source_topology(self):
        from core.line_contracts import validate_line
        _,features=self.junction();feature=features['line'];feature['line']['topology']['junctions']=[]
        with self.assertRaisesRegex(ValueError,'explicit incident junction'):validate_line(feature['line'],feature,features)

    def test_junction_attachment_cannot_claim_a_closed_shape_target(self):
        from core.line_contracts import validate_line
        _,features=self.junction();features['peer.line']['kind']='silhouette';feature=features['line']
        with self.assertRaisesRegex(ValueError,'open source line'):validate_line(feature['line'],feature,features)

    def test_failed_preflight_report_is_a_current_managed_dependency(self):
        from core.font_resolution import POLICY
        from core.context_control import authorize
        state={'task_id':'line-report','source':self.scene['source'],'font_workflow_policy':POLICY}
        write_json(self.root/'state.json',state);self.spec['lines'][0]['source']['stroke']['join']='miter'
        with self.assertRaisesRegex(ValueError,'LINE_PLAN_CONSTRAINT_REQUIRED') as caught:
            line_preflight.require(self.root,state,self.scene,{'line_verification':self.spec,'feature_bindings':[]})
        ref=json.loads(str(caught.exception).split('evidence=',1)[1])
        self.assertEqual(authorize(self.root,ref).name,Path(ref['path']).name)


if __name__=='__main__':unittest.main()
