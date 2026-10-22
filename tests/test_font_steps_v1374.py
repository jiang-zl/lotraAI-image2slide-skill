"""Real preparation/ranking/bind transitions with finite fixture font resources."""
import copy
import importlib
from contextlib import ExitStack
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from PIL import Image,ImageDraw,ImageFont

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'skills/lotra-image2slide-skill/scripts'))
from core import font_contract as fonts,font_collection as collection,font_resources as resources
from core import font_resolution as resolution,font_selection as selection,font_migration
from core.common import digest,identity,read_json,write_json


class FontSteps(unittest.TestCase):
    def setUp(self):
        fixture=importlib.import_module('test_font_workflow_v1373').Fonts();fixture.setUp()
        self.addCleanup(fixture.doCleanups);self.fixture=fixture;self.root=fixture.root;self.task=fixture.task
        image=Image.new('RGB',(100,30),'white')
        ImageDraw.Draw(image).text((0,0),'中文甲乙',font=ImageFont.truetype(fixture.old['path'],20),fill='black')
        file=self.task/'source/original.png';image.save(file)
        self.scene={'source':{'path':'source/original.png','sha256':digest(file)},'revision':0,
            'font_workflow_policy':resolution.POLICY,'objects':[{'id':'lead','render_type':'text','semantic_type':'label',
                'bbox':[0,0,100,30],'style':{'font':fixture.old['family'],'color':'333333'},
                'content':{'runs':[{'text':'中文','color':'FF0000'},{'text':'甲乙'}]}}]}
        self.state={'source':self.scene['source'],'project':str(self.root),'objectives':{},
            'font_workflow_policy':resolution.POLICY,'capabilities':{'fonts':{'environment_key':'fixture'}},
            'font_pending_candidate':{'allowed':{'lead':['replace_component']}},'font_collection':{'revision':'fixture'}}
        faces={face['id']:{**face,'language':'zh','style_class':'sans'} for face in (fixture.old,fixture.new)}
        self.faces=faces;stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.object(resources,'available',return_value=list(faces.values())))
        stack.enter_context(patch.object(collection,'prepare',return_value={'faces':faces,'revision':'fixture'}))
        stack.enter_context(patch.object(collection,'load',return_value={'faces':faces,'revision':'fixture'}))
        stack.enter_context(patch.object(collection,'classify',return_value=('zh','fixture_resource_metadata')))
        evidence=self.task/'source/observation.json'
        write_json(evidence,{'source_hash':self.scene['source']['sha256'],'observer':'host_model',
            'observations':'Independent fixture source regions have sans lettering; red and dark segments share the same observed face style.'})
        self.proof={'path':'source/observation.json','sha256':digest(evidence)}

    def packet(self):
        packet=fonts.packet(self.task,self.state,self.scene)
        packet['packet_id']='packet-'+identity([packet['batch_id'],self.state.get('font_submission_receipt')])[:12]
        return packet

    def receive(self,packet,key,values):
        result={'packet_id':packet['packet_id'],key:values}
        self.state,receipt=selection.receive(self.task,self.state,self.scene,packet,result)
        return result,receipt

    def prepare_samples(self):
        packet=self.packet();self.assertEqual(packet['required_step'],'source_style')
        self.receive(packet,'font_constraints',{r['id']:{'style_classes':['sans'],'style_group':'lead-body',
            'reason':'Original observations place both colour segments in one sans style group','evidence':self.proof} for r in packet['requests']})
        packet=self.packet();self.assertEqual(packet['required_step'],'glyph_samples')
        self.receive(packet,'font_samples',{r['id']:[{'character':r['characters'][0],'roi':[0,0,16,25]}] for r in packet['requests']})

    def test_normal_steps_produce_coherent_staged_binding(self):
        self.prepare_samples();packet=self.packet();self.assertEqual(packet['required_step'],'family_choice')
        self.receive(packet,'font_constraints',{r['id']:{'family':self.fixture.new['family'],
            'comparison_ref':packet['source_glyph_rankings'][r['id']],
            'reason':'Independent original style observations support this candidate family for the complete group',
            'evidence':self.proof} for r in packet['requests']})
        packet=self.packet();self.assertEqual(packet['required_step'],'bind')
        values=[]
        for row in packet['requests']:
            rank=read_json(self.task/packet['source_glyph_rankings'][row['id']]['path'])
            values.append({'request_id':row['id'],'family':self.fixture.new['family'],'resource_id':rank['selected_resource'],
                'origin':'raster_inference','status':'approximate','comparison_ref':packet['source_glyph_rankings'][row['id']],
                'evidence':{'source_hash':self.scene['source']['sha256'],'roi':row['roi'],'description':'Original fixture shape comparison'}})
        result,receipt=self.receive(packet,'font_bindings',values)
        self.assertTrue(receipt['applied']);self.assertEqual(receipt['state'],'staged')
        self.assertNotIn('font_contract',self.state)
        bindings=self.state['font_pending_candidate']['staged_font_contract']['bindings']
        self.assertEqual({row['family'] for row in bindings.values()},{self.fixture.new['family']})
        self.assertEqual(selection.previous_submission(self.state,result),receipt)
        self.assertFalse((self.task/'source/font-bindings.json').exists())

    def test_same_group_different_family_choices_reject_the_entire_batch(self):
        self.prepare_samples();packet=self.packet();before=copy.deepcopy(self.state)
        values={row['id']:{'family':face['family'],'comparison_ref':packet['source_glyph_rankings'][row['id']],
            'reason':'Original group review','evidence':self.proof} for row,face in zip(packet['requests'],self.faces.values())}
        with self.assertRaisesRegex(ValueError,'adopted style group'):
            selection.receive(self.task,self.state,self.scene,packet,{'packet_id':packet['packet_id'],'font_constraints':values})
        self.assertEqual(self.state,before)

    def test_bounded_group_revision_retains_old_faces_until_all_members_are_ready(self):
        self.prepare_samples();packet=self.packet()
        self.receive(packet,'font_constraints',{row['id']:{'family':self.fixture.new['family'],
            'comparison_ref':packet['source_glyph_rankings'][row['id']],'reason':'Original same-family group',
            'evidence':self.proof} for row in packet['requests']})
        old={row['id']:{'request':row,'request_hash':resolution.request_key(row),'family':self.fixture.old['family'],
            'resource':self.fixture.old,'origin':'raster_inference','status':'approximate'} for row in fonts.requests(self.scene,self.state)}
        self.state['font_contract']={'version':fonts.VERSION,'bindings':old,'history':[]}
        packet=self.packet();row=packet['requests'][0]
        rank=read_json(self.task/packet['source_glyph_rankings'][row['id']]['path'])
        self.receive(packet,'font_bindings',[{'request_id':row['id'],'family':self.fixture.new['family'],
            'resource_id':rank['selected_resource'],'origin':'raster_inference','status':'approximate',
            'comparison_ref':packet['source_glyph_rankings'][row['id']],'prior_binding_hash':identity(old[row['id']]),
            'revision_reason':'Current source-supported group revision',
            'evidence':{'source_hash':self.scene['source']['sha256'],'roi':row['roi'],'description':'Original group comparison'}}])
        self.assertEqual(self.state['font_contract']['bindings'],old)
        working=fonts.pending_state(self.state)
        self.assertEqual(len(fonts.missing(self.scene,working)),1)
        with self.assertRaisesRegex(ValueError,'FONT_BINDING_REQUIRED'):fonts.bind_scene(self.task,working,self.scene)

    def test_family_decision_cannot_use_an_unranked_resource_family(self):
        self.prepare_samples();packet=self.packet();row=packet['requests'][0]
        with self.assertRaisesRegex(ValueError,'ranked eligible resource'):
            self.receive(packet,'font_constraints',{row['id']:{'family':'Invented family',
                'comparison_ref':packet['source_glyph_rankings'][row['id']],'reason':'Original review','evidence':self.proof}})

    def test_source_proof_is_required_before_group_narrowing(self):
        packet=self.packet();before=copy.deepcopy(self.state)
        with self.assertRaises((ValueError,KeyError)):
            self.receive(packet,'font_constraints',{packet['requests'][0]['id']:{'style_classes':['sans'],'reason':'No original proof'}})
        self.assertEqual(self.state,before)

    def test_unknown_style_does_not_automatically_enter_sans_group(self):
        packet=self.packet();row=packet['requests'][0]
        with self.assertRaisesRegex(ValueError,'Unknown font style'):
            self.receive(packet,'font_constraints',{row['id']:{'style_classes':['unknown'],
                'reason':'Original review','evidence':self.proof}})

    def test_hint_change_keeps_style_constraint_and_glyph_samples_current(self):
        self.prepare_samples();row=fonts.requests(self.scene,self.state)[0]
        self.scene['objects'][0]['style']['font']='Another construction hint'
        changed=fonts.requests(self.scene,self.state)[0]
        self.assertEqual(resolution.request_key(row),resolution.request_key(changed))
        self.assertEqual(selection.required_step(self.state,changed),'family_choice')

    def test_lost_reply_retry_requires_exact_payload_and_same_original(self):
        packet=self.packet();result,receipt=self.receive(packet,'font_constraints',{
            row['id']:{'style_classes':['sans'],'reason':'Original sans style','evidence':self.proof} for row in packet['requests']})
        before=copy.deepcopy(self.state);self.assertEqual(selection.previous_submission(self.state,result),receipt)
        self.assertEqual(self.state,before)
        changed=copy.deepcopy(result);changed['font_constraints'][packet['request_ids'][0]]['reason']='Different payload'
        self.assertIsNone(selection.previous_submission(self.state,changed))
        self.state['source']={'sha256':identity('another original')}
        self.assertIsNone(selection.previous_submission(self.state,result))

    def test_runtime_pending_packet_persists_real_comparisons_for_family_submit(self):
        from core import agent_runtime as runtime,workflow_guard
        from core.packet_compaction import restore
        self.prepare_samples();file=self.task/'source/pending.json';write_json(file,self.scene)
        self.state.update(schema=runtime.SCHEMA,task_id='pending-fonts',revision=0,selected=None,active_candidate=None,
            source_size=[100,30],stage='font_binding',actions=0,execution_policy=workflow_guard.POLICY)
        from core.execution_contract import VERSION,MANDATORY
        self.state['execution_contract']=VERSION
        self.state['objectives'].update({key:True for key in MANDATORY})
        self.state['objectives'].update(component_first=True,context_chars=9000)
        self.state['font_pending_candidate'].update(scene={'path':'source/pending.json','sha256':digest(file)},
            reason={},baseline=None,staged_font_contract={'version':fonts.VERSION,'bindings':{},'history':[]})
        runtime._save(self.task,self.state);self.state=runtime._read_state(self.task/'state.json')
        with patch.object(runtime,'_preview',return_value=[]):packet=restore(self.task,runtime._pending_font_work(self.task,self.state)['packet'])
        current=runtime._read_state(self.task/'state.json');self.assertNotIn('font_contract',current)
        for row in packet['requests']:
            self.assertIn(packet['source_glyph_rankings'][row['id']],current['font_rankings'][resolution.request_key(row)].values())
        result={'packet_id':packet['packet_id'],'font_constraints':{row['id']:{'family':self.fixture.new['family'],
            'comparison_ref':packet['source_glyph_rankings'][row['id']],'reason':'Current original group comparison',
            'evidence':self.proof} for row in packet['requests']}}
        submitted=runtime.submit(self.task,result)
        self.assertTrue(submitted['font_submission']['applied'])
        updated=runtime._read_state(self.task/'state.json');self.assertNotIn('font_contract',updated)
        self.assertEqual(selection.previous_submission(updated,result),submitted['font_submission'])

    def test_failed_sample_batch_cannot_persist_its_first_valid_entry(self):
        packet=self.packet();self.receive(packet,'font_constraints',{
            row['id']:{'style_classes':['sans'],'reason':'Original sans style','evidence':self.proof} for row in packet['requests']})
        packet=self.packet();before=copy.deepcopy(self.state)
        values={row['id']:[{'character':row['characters'][0],'roi':[0,0,16,25]}] for row in packet['requests']}
        values[packet['request_ids'][-1]][0]['roi']=[1000,0,16,25]
        with self.assertRaisesRegex(ValueError,'escaped its text owner'):
            self.receive(packet,'font_samples',values)
        self.assertEqual(self.state,before)

    def legacy_context(self):
        scene=copy.deepcopy(self.scene);scene.pop('font_workflow_policy')
        state=copy.deepcopy(self.state);state.pop('font_workflow_policy');state['actions']=0
        bindings={}
        for row in fonts.requests(scene):
            bindings[row['id']]={'request':row,'request_hash':resolution.request_key(row),'family':self.fixture.old['family'],
                'resource':self.fixture.old,'origin':'raster_inference','status':'approximate'}
        state['font_contract']={'version':fonts.VERSION,'bindings':bindings,'history':[]}
        file=self.task/'source/migration-intent.json';write_json(file,{
            'source_hash':scene['source']['sha256'],'observer':'host_model','observations':'Original reviewed; construction font names were hints.',
            'requests':[{'request_id':row['id'],'mode':'hint'} for row in fonts.requests(scene)]})
        request={'source_hash':scene['source']['sha256'],'reason':'Explicitly migrate this retained task',
            'intent_map':{'path':'source/migration-intent.json','sha256':digest(file)}}
        return scene,state,request

    def test_explicit_migration_preserves_active_bindings_and_history(self):
        scene,state,request=self.legacy_context();before=copy.deepcopy(state)
        with patch('core.agent_runtime._save') as save:
            result=font_migration.migrate(self.task,state,scene,request)
        self.assertEqual(state,before);self.assertFalse(result['native_write'])
        updated=save.call_args.args[1]
        self.assertEqual(updated['font_contract'],before['font_contract'])
        self.assertEqual(updated['font_workflow_policy'],resolution.POLICY)
        self.assertEqual(updated['font_pending_candidate']['staged_font_contract']['history'][-1]['operation'],'explicit_font_policy_migration')

    def test_migration_cannot_downgrade_an_exact_user_request(self):
        scene,state,request=self.legacy_context();state['objectives']['font_requests']={'ea':self.fixture.old['family']}
        with self.assertRaisesRegex(ValueError,'FONT_MIGRATION_EXACT_AUTHORITY'):
            font_migration.migrate(self.task,state,scene,request)


if __name__=='__main__':unittest.main()
