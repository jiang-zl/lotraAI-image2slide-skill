"""Packet command/template consistency; existing quality rules stay authoritative."""
import ast,copy,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
import test_workflow_v137 as previous

from core import agent_runtime as a,component_workflow as c,workflow_guard as g
from core.common import digest,read_json,safe_path,write_json
from core.packet_compaction import compact,restore
from sci_rebuild import parser


class PacketSubmission(unittest.TestCase):
    def setUp(self):
        self.fixture=previous.Protocol();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.task=self.fixture.task
        state=self.fixture.state();state['objectives'].update(context_chars=9000,review_view_width=720,render_width=1600)
        state['capabilities']={'fingerprint':'packet-entry-fixture'};a._save(self.task,state)

    def hint(self,packet):
        packet=restore(self.task,packet);ref=packet['submission_template']
        self.assertEqual(packet['action'],'submit')
        self.assertEqual(digest(safe_path(self.task,ref['path'])),ref['sha256'])
        filled=safe_path(self.task,ref['copy_to'])
        self.assertEqual(filled.parent,self.task/'scratch')
        self.assertNotEqual(filled,safe_path(self.task,ref['path']))
        self.assertEqual(packet['submission_command'],['submit',str(self.task.resolve()),str(filled.resolve())])
        args=parser().parse_args(packet['submission_command'])
        self.assertEqual(args.command,'submit');self.assertEqual(args.task,self.task.resolve())
        with g.command_scope(args):pass
        payload=read_json(safe_path(self.task,ref['path']))
        self.assertEqual(payload['packet_id'],packet['packet_id'])
        return packet,payload

    def source_packet(self):
        return c.next_action(self.task,self.fixture.state())['packet']

    def generated(self,kind,target='phase',extra=None):
        state=self.fixture.state()
        with patch.object(a,'_preview',return_value=[]):
            return a._packet(self.task,state,kind,target,'Complete current evidence.',extra=extra or {})

    def submit_hint(self,packet,request):
        packet,payload=self.hint(packet);payload['component_request']=request
        filled=safe_path(self.task,packet['submission_template']['copy_to']);write_json(filled,payload)
        return a.submit(self.task,read_json(filled))

    def test_initial_observation_hint_executes_current_outline_submission(self):
        packet=self.source_packet();_,payload=self.hint(packet)
        self.assertEqual(payload['component_request']['operation'],'source_outline')
        result=self.submit_hint(packet,self.fixture.outline())
        self.assertEqual(result['status'],'SOURCE_OUTLINE_FROZEN')

    def test_source_chunk_hint_uses_current_template(self):
        self.fixture.send(self.fixture.outline())
        _,payload=self.hint(self.source_packet())
        self.assertEqual(payload['component_request']['operation'],'source_chunk')

    def test_source_seal_hint_uses_current_template(self):
        self.fixture.send(self.fixture.outline());self.fixture.send(self.fixture.chunk('left'));self.fixture.send(self.fixture.chunk('right'))
        packet,payload=self.hint(self.source_packet())
        self.assertEqual(payload['component_request']['operation'],'source_seal')
        self.assertEqual(self.submit_hint(packet,{'operation':'source_seal'})['status'],'SOURCE_OBSERVATION_SEALED')

    def test_binding_hint_does_not_advertise_direct_bind(self):
        self.fixture.observed();_,payload=self.hint(self.source_packet())
        self.assertEqual(payload['component_request']['operation'],'bind_chunk')

    def test_binding_seal_hint_does_not_advertise_direct_bind(self):
        self.fixture.observed()
        self.fixture.send({'operation':'bind_chunk','chunk_id':'correspondences','binding':{'contract':{
            'feature_bindings':[{'feature':name+'.outline','component':name,'owners':[name+'.native']} for name in ('left','right')]}}},'component_contract')
        _,payload=self.hint(self.source_packet())
        self.assertEqual(payload['component_request']['operation'],'bind_seal')

    def test_recovery_producer_and_submission_reach_existing_recovery_handler(self):
        contract={'workflow_version':'1.35.2','design_revision':8}
        ledger={'pending_transaction':{'path':'scratch/recovery.json','sha256':'retained-transaction'}}
        with patch.object(c,'_load',return_value=(contract,ledger)):
            packet=c.next_action(self.task,self.fixture.state())['packet']
        packet,payload=self.hint(packet);self.assertEqual(packet['kind'],'component_recovery_work')
        def recover(task,request):
            g.require(task,'recover');self.assertEqual(g._GRANT.get()['kind'],'component_recovery_work')
            return {'status':'RETAINED_RECOVERY_HANDLER'}
        with patch('core.component_transactions.recover',side_effect=recover) as handler:
            self.assertEqual(a.submit(self.task,payload)['status'],'RETAINED_RECOVERY_HANDLER')
            handler.assert_called_once()

    def test_final_audit_producer_and_submission_reach_existing_final_handler(self):
        scene=self.task/'scratch/scene.json';write_json(scene,{'objects':[]})
        state=self.fixture.state();state['active_candidate']={'pptx':self.fixture.source,'preview':self.fixture.source,
            'render':self.fixture.source,'scene':a._file(self.task,scene)}
        state['component_workflow']={'ledger_path':'scratch/final-ledger.json'};a._save(self.task,state)
        contract={'workflow_version':'1.35.2','design_revision':8,'components':[]}
        ledger={'components':{},'final_dirty':True,'final_result':None}
        with patch.object(c,'_load',return_value=(contract,ledger)),patch.object(c,'refresh'),\
             patch('core.component_actions.available',return_value=[]),patch.object(c,'ready_for_final',return_value={'ready':True}),\
             patch('core.component_fonts.current',return_value=True),patch('core.component_final._visual',return_value={'passed':True}):
            packet=c.next_action(self.task,state)['packet']
        packet,payload=self.hint(packet);self.assertEqual(packet['kind'],'component_final_audit')
        def final(task,*args,**kwargs):
            g.require(task,'final');self.assertEqual(g._GRANT.get()['kind'],'component_final_audit')
            return {'status':'EXISTING_FINAL_HANDLER'}
        with patch.object(c,'run',side_effect=final) as handler:
            self.assertEqual(a.submit(self.task,payload)['status'],'EXISTING_FINAL_HANDLER')
            handler.assert_called_once()

    def test_all_literal_packet_kinds_have_one_executable_submission_entry(self):
        kinds=set()
        for file in (previous.SCRIPTS/'core').glob('*.py'):
            for node in ast.walk(ast.parse(file.read_text(encoding='utf-8-sig'))):
                if isinstance(node,ast.Call) and len(node.args)>2 and ((isinstance(node.func,ast.Name) and node.func.id=='_packet') or
                        (isinstance(node.func,ast.Attribute) and node.func.attr=='_packet')) and isinstance(node.args[2],ast.Constant) and isinstance(node.args[2].value,str):
                    kinds.add(node.args[2].value)
        self.assertIn('tool_render',kinds);self.assertIn('component_final_audit',kinds)
        state=self.fixture.state();state['active_candidate']={'pptx':self.fixture.source};a._save(self.task,state)
        for kind in sorted(kinds):
            with self.subTest(kind=kind):self.hint(self.generated(kind,extra={'action':'component-workflow forbidden-direct-entry'}))

    def test_tool_evidence_instructions_are_retained_with_submission_hint(self):
        packet=self.generated('tool_render',extra={'return':'preview and hash-bound render receipt','render_dispatch':{'backend':'fixture'}})
        packet,_=self.hint(packet)
        self.assertEqual(packet['return'],'preview and hash-bound render receipt')
        self.assertEqual(packet['render_dispatch'],{'backend':'fixture'})

    def test_compaction_retains_the_executable_hint_and_bound_template(self):
        packet,_=self.hint(self.source_packet());packet['diagnostics']='large retained evidence '*3000
        short=compact(self.task,packet,4500)
        self.assertIn('execution_reference',short)
        for key in ('action','submission_command','submission_template'):self.assertEqual(short[key],packet[key])
        self.assertEqual(restore(self.task,short),packet)

    def test_minimum_context_budget_keeps_submit_controls_and_full_contract(self):
        packet,_=self.hint(self.source_packet());packet['diagnostics']='retained original evidence '*3000
        short=compact(self.task,packet,2500)
        from core.common import canonical
        self.assertLessEqual(len(canonical(short).decode('utf-8')),2500)
        for key in ('action','submission_command','submission_template'):self.assertEqual(short[key],packet[key])
        self.assertEqual(restore(self.task,short),packet)

    def compacted(self):
        packet,_=self.hint(self.source_packet());packet['diagnostics']='retained evidence '*3000
        return compact(self.task,packet,4500)

    def test_changed_compacted_action_is_rejected(self):
        short=self.compacted();short['action']='component-workflow bind'
        with self.assertRaisesRegex(ValueError,'identity changed: action'):restore(self.task,short)

    def test_changed_compacted_submission_arguments_are_rejected(self):
        short=self.compacted();short['submission_command']=copy.deepcopy(short['submission_command']);short['submission_command'][1]+='-other-task'
        with self.assertRaisesRegex(ValueError,'identity changed: submission_command'):restore(self.task,short)

    def test_changed_compacted_template_copy_target_is_rejected(self):
        short=self.compacted();short['submission_template']=copy.deepcopy(short['submission_template']);short['submission_template']['copy_to']='scratch/other.json'
        with self.assertRaisesRegex(ValueError,'identity changed: submission_template'):restore(self.task,short)

    def test_legacy_direct_operations_remain_blocked(self):
        for operation in ('observe_source','bind','recover','final'):
            with self.subTest(operation=operation),self.assertRaisesRegex(ValueError,'WORKFLOW_REQUIRED'):
                with g.command_scope(parser().parse_args(['component-workflow',str(self.task),operation])):pass

    def test_structured_arguments_preserve_paths_with_spaces(self):
        task=self.task/'path with spaces';task.mkdir();(task/'packets').mkdir()
        state=self.fixture.state();packet={'packet_id':'space-test','kind':'component_final_audit','target':'final_audit'}
        from core.incremental_contract import template
        packet=template(task,state,packet);args=parser().parse_args(packet['submission_command'])
        self.assertEqual(args.task,task.resolve());self.assertEqual(len(packet['submission_command']),3)

    def test_old_bound_execution_policy_keeps_its_historical_packet(self):
        state=self.fixture.state();state.pop('execution_policy');a._save(self.task,state)
        packet=self.generated('component_contract_source','source_features',extra={'action':'component-workflow observe_source'})
        self.assertEqual(packet['action'],'component-workflow observe_source')
        self.assertNotIn('submission_command',packet);self.assertNotIn('submission_template',packet)


if __name__=='__main__':unittest.main()
