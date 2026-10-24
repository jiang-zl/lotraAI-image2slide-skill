"""Real lazy-state reload and journal scheduling regression cases."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/lotra-image2slide-skill/scripts'))
from core import state_repository as store, font_selection, component_transactions as tx
from core import agent_runtime as runtime,component_workflow as components,tool_router
from core.common import identity,write_json


class LazyHistory(unittest.TestCase):
    def test_chunked_receipt_retry_survives_reload_and_list_operations(self):
        with tempfile.TemporaryDirectory() as folder:
            repository=store.Repository(folder)
            response={'packet_id':'current','font_bindings':[{'request_id':'first'}]}
            receipt={'applied':True,'packet_id':'current','source_hash':'source',
                     'response_hash':identity(response),'observations':'retained original evidence '*20}
            history=[dict(receipt,packet_id='old-'+str(i)) for i in range(50)]+[receipt]
            repository.save('task',{'source':{'sha256':'source'},'font_submission_history':history})
            state=repository.load('task');values=state['font_submission_history']
            self.assertIsInstance(values,store.LazyList)
            self.assertEqual(font_selection.previous_submission(state,response),receipt)
            self.assertEqual(list(reversed(values)),list(reversed(history)))
            self.assertEqual(values[-3:],history[-3:])
            self.assertEqual(values+[receipt],history+[receipt])
            self.assertEqual([receipt]+values,[receipt]+history)
            self.assertEqual(values.copy(),history)
            self.assertIn(receipt,values)
            self.assertEqual(values.count(receipt),1)
            self.assertEqual(values.index(receipt),50)
            self.assertEqual(copy.deepcopy(values),history)
            self.assertEqual(store.plain(values*2),history*2)
            values += [receipt]
            repository.save('task',state)
            self.assertEqual(store.plain(repository.load('task')['font_submission_history']),history+[receipt])


class RecoveryPriority(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.task=Path(self.temp.name)
        self.pending={'id':'retained','path':'transactions/retained/Transaction.json'}
        self.journal={'id':'retained','path':self.pending['path'],'phase':'STAGED'}
        write_json(self.task/self.pending['path'],self.journal)
        self.state={'task_id':'task','project':str(self.task),'source':{'sha256':'source'},'capabilities':{'fingerprint':'same'},
                    'selected':None,'revision':0,'stage':'font_binding','packet':None,
                    'objectives':{'component_first':True},'component_workflow':{'contract':{}},
                    'font_pending_candidate':{'scene':{},'transaction_path':None}}
        self.contract={'schema':'component-contract-1.32.0','design_revision':8}
        self.ledger={'pending_transaction':self.pending}

    def packet(self,task,state,kind,target,instruction,extra):
        return {'packet_id':'recover','kind':kind,'target':target,**extra}

    def test_orphan_font_pending_cannot_start_another_transaction(self):
        with patch.object(components,'_load',return_value=(self.contract,self.ledger)),\
             patch.object(components,'reference',return_value='retained-reference'),\
             patch.object(runtime,'_packet',side_effect=self.packet):
            packet=tx.recovery_packet(self.task,self.state)
        self.assertEqual(packet['kind'],'component_recovery_work')
        self.assertEqual(packet['recovery_stage'],'STAGED')
        self.assertIn('retain_and_redecide',packet['allowed_recovery_actions'])

    def test_next_routes_recovery_before_pending_font_and_stale_packet(self):
        self.state['packet']={'kind':'font_binding','packet_id':'stale'}
        with patch.object(runtime,'_state',return_value=(self.task,self.state)),\
             patch.object(tool_router,'environment_changed',return_value=False),\
             patch.object(components,'_load',return_value=(self.contract,self.ledger)),\
             patch.object(components,'reference',return_value='retained-reference'),\
             patch.object(runtime,'_packet',side_effect=self.packet),\
             patch.object(runtime,'_pending_font_work') as pending:
            result=runtime.next_packet(self.task)
        pending.assert_not_called()
        self.assertEqual(result['packet']['kind'],'component_recovery_work')

    def test_own_journal_font_dependency_can_continue(self):
        self.state['font_pending_candidate']['transaction_path']=self.pending['path']
        with patch.object(components,'_load',return_value=(self.contract,self.ledger)):
            self.assertIsNone(tx.recovery_packet(self.task,self.state))

    def test_saved_font_commit_routes_recovery_even_if_font_plan_remains(self):
        self.state['font_pending_candidate']['transaction_path']=self.pending['path']
        self.journal['font_commit_pending']={'record':{'path':'owned-font-stage.json'}}
        write_json(self.task/self.pending['path'],self.journal)
        with patch.object(components,'_load',return_value=(self.contract,self.ledger)),\
             patch.object(components,'reference',return_value='reference'),\
             patch.object(runtime,'_packet',side_effect=self.packet):
            self.assertEqual(tx.recovery_packet(self.task,self.state)['kind'],'component_recovery_work')

    def test_saved_render_dependency_is_not_recovered_repeatedly(self):
        candidate={'pptx':{'sha256':'saved'}}
        self.journal.update(phase='DISPLAY_PENDING',candidate=candidate)
        write_json(self.task/self.pending['path'],self.journal)
        self.state.update(stage='host_render',active_candidate=candidate)
        with patch.object(components,'_load',return_value=(self.contract,self.ledger)):
            self.assertIsNone(tx.recovery_packet(self.task,self.state,candidate))

    def test_old_implementation_recovery_packet_is_reissued(self):
        self.state['packet']={'kind':'component_recovery_work','packet_id':'stale','transaction':self.pending,'revision':0,'component_implementation':'old'}
        with patch.object(components,'_load',return_value=(self.contract,self.ledger)),patch.object(components,'reference',return_value='reference'),patch.object(components,'implementation',return_value='current'),patch.object(runtime,'_packet',side_effect=self.packet) as issue:
            result=tx.recovery_packet(self.task,self.state)
        issue.assert_called_once();self.assertEqual(result['packet_id'],'recover')

    def retained_redecision(self,unrelated=False):
        baseline={'pptx':{'sha256':'baseline'}};self.state['active_candidate']=baseline
        reason={'kind':'component_scoped_repair','components':['label']};allowed={'label':['text_body','style.font_size']}
        self.journal.update(source='source',baseline=baseline,allowed=allowed,reason=reason,local_components=['label'],contract={},post_save={'consume_structural_grant':True},native_attempts=['attempt1','attempt2','attempt3'])
        write_json(self.task/self.pending['path'],self.journal)
        font={'scene':{'path':'retained-font-scene','sha256':'font-plan'},'baseline':baseline,'allowed':allowed,'reason':reason,'transaction_path':None,'staged_font_contract':{'bindings':{'new':'retained-not-adopted'}}}
        if unrelated:font=copy.deepcopy(font);font['allowed']={'other':['text_body']}
        self.state['font_pending_candidate']=font
        self.ledger.update(components={'label':{'status':'QUALIFIED'}},structural_grant={'components':['label'],'contract':{},'scene':{'path':'retained-source-scene'}})
        with patch.object(runtime,'_state',return_value=(self.task,self.state)),patch.object(components,'_load',return_value=(self.contract,self.ledger)),patch.object(components,'_resource',return_value=self.task/'evidence'),patch.object(components,'_save_ledger'):
            result=tx.recover(self.task,{'action':'retain_and_redecide','reason':'Located current producer failure','evidence':{'path':'evidence','sha256':'frozen'}})
        return result,font,__import__('json').loads((self.task/self.pending['path']).read_bytes())

    def test_retaining_unsaved_attempt_archives_matching_orphan_font_dependency(self):
        result,font,journal=self.retained_redecision()
        self.assertEqual(result['status'],'SOURCE_DECISION_REQUIRED')
        self.assertNotIn('font_pending_candidate',self.state);self.assertIsNone(self.state['packet']);self.assertEqual(self.state['stage'],'review')
        self.assertEqual(journal['retained_font_dependency'],font)
        self.assertEqual(journal['native_attempts'],['attempt1','attempt2','attempt3'])
        self.assertIn('retained_structural_grant',journal);self.assertNotIn('structural_grant',self.ledger)
        self.assertNotIn('font_contract',self.state)

    def test_retaining_attempt_keeps_unrelated_pending_font_operation(self):
        result,font,journal=self.retained_redecision(unrelated=True)
        self.assertEqual(self.state['font_pending_candidate'],font);self.assertNotIn('retained_font_dependency',journal)

    def test_conflicting_operation_aliases_reject_before_dispatch(self):
        result={'operation':'evaluate','component_request':{'operation':'edit'}}
        with self.assertRaisesRegex(ValueError,'OPERATION_CONFLICT'),\
             patch.object(components,'dispatch') as dispatch:
            components.submit_result(self.task,result,{'kind':'component_local_work'})
        dispatch.assert_not_called()


if __name__=='__main__':unittest.main()
