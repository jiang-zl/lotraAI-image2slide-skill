"""Independent integration regression for obligations surviving real source bind.

This exercises component_workflow.bind through a real registered protocol
fixture. Native rendering is outside this narrow unit-test scope; the mocked
passing report below checks that even a newer passing report cannot erase a
retained doubt. It must never be used as artwork acceptance.
"""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'skills/lotra-image2slide-skill/scripts'))
from core import component_workflow as workflow, line_contracts, line_geometry, line_review
from core import agent_runtime, workflow_guard
from core.common import read_json, write_json, digest
from core.recipes import node
import test_workflow_v137 as protocol_fixture
from test_line_evidence_v1372 import source_line


class RebindLineObligations(unittest.TestCase):
    def setUp(self):
        self.fixture=protocol_fixture.Protocol();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.task=self.fixture.task
        state=self.fixture.state();state['verification_policy']=line_contracts.POLICY
        state['capabilities']={'fingerprint':'owned-rebind-unit-test'}
        agent_runtime._save(self.task,state)
        self.fixture.send(self.fixture.outline())
        left=self.fixture.chunk('left')
        left['observation']['features'].append({
            'id':'left.line','unit':'left','kind':'internal_line','roi':[18,18,26,76],
            'required':True,'observability':'clear','requirements':['editable','corners'],
            'source_evidence':'Independent protocol route, east then south, no terminal markers.',
            'line':source_line(((20,20),(40,20),(40,90)))})
        self.fixture.send(left);self.fixture.send(self.fixture.chunk('right'))
        self.fixture.send({'operation':'source_seal'})
        objects=[
            node('left.native','shape',[5,5,10,10],{'preset':'rect'},fill='4477AA',stroke='17324D',line_width=1),
            node('right.native','shape',[60,10,30,30],{'preset':'rect'},fill='4477AA',stroke='17324D',line_width=1),
            node('route.native','connector',[20,20,20,70],
                 {'points':[[20,20],[40,20],[40,90]],'coordinate_space':'canvas',
                  'start_arrow':'none','arrow':'none','arrow_length':'lg'},
                 stroke='000000',line_width=1.5,line_join='round',line_cap='flat')]
        rows=[{'id':name,'route':'fixed_parameters','owners':owners,'source_units':[name],
               'source_evidence':'Owned protocol construction, source facts remain frozen.',
               'source_refs':[self.fixture.source],'roi':roi,'frozen_parameters':True,'metrics':[],
               'model':{'id':'native_scene','version':1}}
              for name,owners,roi in [('left',['left.native','route.native'],[0,0,50,100]),
                                      ('right',['right.native'],[50,0,50,100])]]
        bindings=[{'feature':name+'.outline','component':name,'owners':[name+'.native'],
                   'representation':{'family':'preset'}} for name in ('left','right')]
        bindings.append({'feature':'left.line','component':'left','owners':['route.native'],
                         'representation':{'family':'native_connector'}})
        self.fixture.send({'operation':'bind_chunk','chunk_id':'owned-line-binding',
            'binding':{'scene':{'canvas':{'width':100,'height':100,'unit':'px','target_width_inches':100/96},
                                'objects':objects},
                       'contract':{'components':rows,'feature_bindings':bindings}}},'component_contract')
        result=self.fixture.send({'operation':'bind_seal'},'component_contract')
        self.assertEqual(result['status'],'COMPONENT_CONTRACT_SEALED')
        self.contract,self.ledger=workflow._load(self.task,self.fixture.state())
        self.old_ledger_path=self.task/self.fixture.state()['component_workflow']['ledger_path']

    def seed_ledger(self,issues,history):
        self.ledger['line_issues']=copy.deepcopy(issues)
        self.ledger['line_render_refinements']=copy.deepcopy(history)
        write_json(self.old_ledger_path,self.ledger)
        self.old_ledger_hash=digest(self.old_ledger_path)

    def rebind_encoding(self):
        """Actually replace the ledger via bind, retaining independent source facts."""
        state=self.fixture.state()
        scene=read_json(workflow._resource(self.task,self.contract['source_scene']))
        route=next(row for row in scene['objects'] if row['id']=='route.native')
        route['content']['arrow_length']='med'
        scene_path=self.task/'scratch/rebound-native-encoding.json';write_json(scene_path,scene)
        request={'source_scene':workflow._ref(self.task,scene_path),
                 'authority':self.contract['authority'],'contract':copy.deepcopy(self.contract),
                 'revision_reason':'Adopt a native construction encoding correction; original line facts and quality limits are unchanged.'}
        packet={'packet_id':'source-rebind','kind':'component_contract_source','target':'component_contract',
                'source':state['source']['sha256'],'revision':state['revision']}
        state['packet']=packet;agent_runtime._save(self.task,state)
        with workflow_guard.packet_writer(self.task,state,packet):
            result=workflow.bind(self.task,request)
        self.assertEqual(result['status'],'COMPONENT_CONTRACT_BOUND')
        state=self.fixture.state();contract,ledger=workflow._load(self.task,state)
        self.assertNotEqual(self.task/state['component_workflow']['ledger_path'],self.old_ledger_path)
        self.assertEqual(digest(self.old_ledger_path),self.old_ledger_hash)
        self.assertTrue(ledger['final_dirty']);self.assertIsNone(ledger['final_result'])
        return state,contract,ledger

    def test_real_bind_preserves_open_doubts_and_consumed_precision_budget(self):
        issues={
            'program:left.line:visibility':{'id':'program:left.line:visibility','line':'left.line',
                'criterion':'visibility','origin':'program','state':'OPEN','finding':'Earlier actual line coverage was inconclusive.','check_hash':'old-check'},
            'visual:marker-question':{'id':'visual:marker-question','line':'left.line',
                'criterion':'markers','origin':'visual','state':'OPEN','finding':'Earlier located terminal observation needs resolution.','roi':[32,78,16,20]}}
        history=[{'operation':'refine_render','pptx':'unchanged-native','target_width':width,
                  'manifest':{'path':'retained-manifest-'+str(width)+'.json','sha256':'retained-'+str(width)}}
                 for width in (1600,3200)]
        self.seed_ledger(issues,history)
        state,contract,ledger=self.rebind_encoding()
        self.assertEqual(ledger['line_issues'],issues)
        self.assertEqual(ledger['line_render_refinements'],history)
        self.assertEqual(set(line_review.current_open_issues(ledger,{})),set(issues))
        # Exercise the retained finite budget, rather than only comparing a key.
        checks={key:line_geometry.result(True) for key in line_contracts.CRITERIA}
        checks['visibility']={'passed':False,'valid':False,
            'probe':{'reason':'BOUND_REFINEMENT_REQUIRED','valid':False,
                     'method':'every_original_shaft_pixel_coverage','tolerance':3,'value':1}}
        report={'lines':{'left.line':{'checks':checks}}}
        candidate={'pptx':{'sha256':'unchanged-native'},'preview':{'sha256':'current-preview'}}
        self.assertIsNotNone(line_review.precision_request(state,candidate,report,3200,[]))
        self.assertIsNone(line_review.precision_request(state,candidate,report,3200,ledger['line_render_refinements']))

    def test_real_bind_then_current_manifest_reopens_old_resolution(self):
        old_resolution={'issue':'visual:resolved-marker','kind':'measurement',
                        'observations':'Prior actual enlarged terminal pair.',
                        'evidence_refs':[{'path':'old-marker.png','sha256':'old-crop'}]}
        issue={'id':'visual:resolved-marker','line':'left.line','criterion':'markers',
               'origin':'visual','state':'RESOLVED','roi':[32,78,16,20],
               'finding':'A terminal proportion question from prior saved bytes.',
               'resolved_binding':{'pptx':'old-native','preview':'old-preview'},
               'resolution':copy.deepcopy(old_resolution),'current_check':'old-marker-check'}
        self.seed_ledger({issue['id']:issue},[])
        state,contract,ledger=self.rebind_encoding()
        self.assertEqual(ledger['line_issues'][issue['id']],issue)
        # These owned placeholder resources are only for current review routing.
        # A passing mock report must still not waive the retained visual doubt.
        pptx=self.task/'scratch/not-a-render-acceptance.pptx';pptx.write_bytes(b'unit test, not native artwork')
        candidate={'pptx':workflow._ref(self.task,pptx),'preview':self.fixture.source,
                   'render':{'path':'new-render.json','sha256':'new-render-receipt'}}
        checks={key:line_geometry.result(True) for key in line_contracts.CRITERIA}
        report={'policy':line_contracts.POLICY,'basis':contract['line_verification']['basis'],
                'passed':True,'valid':True,'source_hash':state['source']['sha256'],
                'pptx_hash':candidate['pptx']['sha256'],'preview_hash':candidate['preview']['sha256'],
                'render_checked':True,'census':{'passed':True},
                'lines':{'left.line':{'passed':True,'valid':True,'checks':checks}}}
        with patch('core.line_verification.evaluate',return_value=report),patch('core.boundary_geometry.saved_nodes',return_value={}):
            prepared=line_review.prepare(self.task,state,candidate,contract,ledger)
        manifest=read_json(self.task/prepared['manifest']['path'])
        reopened=next(row for row in manifest['issues'] if row['id']==issue['id'])
        self.assertEqual(reopened['state'],'OPEN')
        self.assertEqual(reopened['prior_resolutions'][-1]['resolution'],old_resolution)
        self.assertEqual(reopened['prior_resolutions'][-1]['check'],'old-marker-check')
        self.assertTrue(any(view['kind']=='issue:'+issue['id'] for target in manifest['targets'] for view in target['views']))
        proof={'line_review':{'manifest':prepared['manifest'],
            'lines':[{'line':'left.line','criteria':{key:'PASS' for key in line_contracts.CRITERIA},
                      'evidence_refs':[ref for target in manifest['targets'] for view in target['views'] for ref in view['evidence'].values()]}],
            'issues':[],'resolutions':[]}}
        result=line_review.validate(self.task,state,candidate,contract,ledger,proof,report=report)
        self.assertFalse(result['passed']);self.assertIn(issue['id'],result['open_issues'])
        self.assertTrue(line_review.retain_prepared_issues(self.task,prepared,ledger))
        self.assertEqual(ledger['line_issues'][issue['id']]['state'],'OPEN')
        self.assertEqual(ledger['line_issues'][issue['id']]['prior_resolutions'][-1]['resolution'],old_resolution)


if __name__=='__main__':unittest.main()
