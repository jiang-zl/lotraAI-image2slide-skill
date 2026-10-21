"""Protocol bypasses and persistent positive progress; no external art claims."""
import argparse,copy,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from PIL import Image

REPO=Path(__file__).resolve().parents[1]
SCRIPTS=REPO/'skills/lotra-image2slide-skill/scripts'
sys.path.insert(0,str(SCRIPTS))
from core import agent_runtime as a,incremental_contract as inc,workflow_guard as g
from core.common import write_json,read_json,digest
from core.execution_contract import MANDATORY,VERSION
from core.workflow_delivery import check


class Protocol(unittest.TestCase):
    def setUp(self):
        root=REPO/'.lotraAI-build/workflow-tests';root.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=root);self.addCleanup(self.tmp.cleanup)
        self.project=Path(self.tmp.name);self.task=self.project/'.lotraAI-build/tasks/current'
        (self.task/'source').mkdir(parents=True);(self.task/'scratch').mkdir()
        original=self.task/'source/original.png';Image.new('RGB',(100,100),'white').save(original)
        self.source={'path':'source/original.png','sha256':digest(original)}
        write_json(self.task/'source/evidence.json',{'source':self.source,'size':[100,100]})
        (self.task/'source/profile.json').write_bytes((SCRIPTS.parent/'config/quality.seed.json').read_bytes())
        state={'schema':a.SCHEMA,'task_id':'current','project':str(self.project),'source':self.source,'source_size':[100,100],
            'execution_contract':VERSION,'execution_policy':g.POLICY,'objectives':{**{k:True for k in MANDATORY},'component_first':True},
            'revision':0,'packet':None,'selected':None,'active_candidate':None,'stage':'source_observation'}
        a._save(self.task,state)

    def state(self):return a._state(self.task)[1]

    def send(self,request,target='source_features',packet_id='current-packet'):
        from core.component_workflow import implementation
        state=self.state();packet={'packet_id':packet_id,'source':self.source['sha256'],'revision':0,'kind':'component_contract_source',
            'target':target,'views':[],'component_implementation':implementation()}
        inc.template(self.task,state,packet)
        state['packet']=packet;a._save(self.task,state)
        return a.submit(self.task,{'packet_id':packet_id,'component_request':request})

    def outline(self):
        return {'operation':'source_outline','outline':{'source_hash':self.source['sha256'],'canvas':[100,100],
            'observer':'host_model','complete_scope':True,'observations':'Two separate original square regions, with all scope retained.',
            'units':[{'id':v,'roi':roi,'source_evidence':'Original '+v} for v,roi in [('left',[0,0,50,100]),('right',[50,0,50,100])]]}}

    def chunk(self,name):
        roi=[0,0,50,100] if name=='left' else [50,0,50,100]
        return {'operation':'source_chunk','chunk_id':name,'observation':{
            'units':[{'id':name,'roi':roi,'source_evidence':'Original '+name,'decomposition':{'state':'leaf','reason':'One visible square.'},
                'spatial':{'mode':'planar','frame':'canvas','placement':'free','container':False,'observability':'clear','source_evidence':'Flat original square'}}],
            'features':[{'id':name+'.outline','unit':name,'kind':'silhouette','roi':roi,'source_evidence':'Original outline',
                'observability':'clear','requirements':['editable','closed_contour']}],
            'spatial':{'frames':[{'id':'canvas','kind':'canvas','units':'source_px','owner_unit':'left','source_evidence':'Original pixel canvas'}],
                'landmarks':[],'relations':[],'footprints':[]},'observations':'Located original '+name}}

    def observed(self):
        self.send(self.outline());self.send(self.chunk('left'));self.send(self.chunk('right'))
        self.send({'operation':'source_seal'})

    def test_raw_build_without_task_never_writes(self):
        from core.build import build
        output=self.project/'result.pptx'
        with self.assertRaisesRegex(ValueError,'WORKFLOW_REQUIRED'):build({},self.project,output)
        self.assertFalse(output.exists())

    def test_public_build_requires_explicit_private_draft(self):
        args=argparse.Namespace(command='build',task=None,out=self.project/'Final_editable.pptx',developer_draft=False,project=self.project)
        with self.assertRaisesRegex(ValueError,'WORKFLOW_REQUIRED'):
            with g.command_scope(args):pass
        args.developer_draft=True
        with self.assertRaisesRegex(ValueError,'Draft_editable'):
            with g.command_scope(args):pass
        args.out=self.project/'Draft_editable.pptx'
        with self.assertRaisesRegex(ValueError,'private'):
            with g.command_scope(args):pass

    def test_explicit_private_draft_scope_is_allowed(self):
        output=self.project/'.lotraAI-build/developer-drafts/example/Draft_editable.pptx'
        args=argparse.Namespace(command='build',task=None,out=output,developer_draft=True,project=self.project)
        with g.command_scope(args):g.require_build(self.project,output)

    def test_missing_contract_still_blocks_with_packet_grant(self):
        state=self.state();packet={'packet_id':'p','source':self.source['sha256'],'revision':0,'kind':'component_build_work'};state['packet']=packet
        with g.packet_writer(self.task,state,packet):
            with self.assertRaisesRegex(ValueError,'complete original'):g.require_build(self.task,self.task/'versions/x.pptx')

    def test_writer_grant_cannot_cross_tasks(self):
        state=self.state();packet={'packet_id':'p','source':self.source['sha256'],'revision':0};state['packet']=packet
        with g.packet_writer(self.task,state,packet):
            other=self.task.parent/'other';other.mkdir();write_json(other/'state.json',state)
            with self.assertRaisesRegex(ValueError,'writer grant'):g.require(other,'build')

    def test_stale_packet_grant_is_rejected(self):
        state=self.state();state['packet']={'packet_id':'current'}
        with self.assertRaisesRegex(ValueError,'current original'):
            with g.packet_writer(self.task,state,{'packet_id':'old','source':self.source['sha256'],'revision':0}):pass

    def test_current_source_packet_cannot_grant_native_construction(self):
        state=self.state();packet={'packet_id':'p','source':self.source['sha256'],'revision':0,
            'kind':'component_contract_source','target':'source_features'};state['packet']=packet
        with g.packet_writer(self.task,state,packet):
            with self.assertRaisesRegex(ValueError,'packet phase'):g.require(self.task,'native construction')

    def test_direct_component_write_is_rejected(self):
        args=argparse.Namespace(command='component-workflow',operation='bind',task=self.task)
        with self.assertRaisesRegex(ValueError,'current packet'):
            with g.command_scope(args):pass
        from core.component_workflow import bind
        with self.assertRaisesRegex(ValueError,'writer grant'):bind(self.task,{})

    def test_status_is_not_blocked_by_mutation_guard(self):
        args=argparse.Namespace(command='component-workflow',operation='status',task=self.task)
        with g.command_scope(args):pass

    def test_source_outline_and_chunks_survive_reload(self):
        result=self.send(self.outline());self.assertFalse(result['acceptance'])
        self.send(self.chunk('left'));state=self.state();value=inc.load(self.task,state)
        self.assertEqual(inc.counts(value)['pending_units'],['right'])
        self.assertIsNone(state.get('component_workflow'))
        self.send(self.chunk('right'));self.send({'operation':'source_seal'})
        state=self.state();self.assertTrue(inc.load(self.task,state)['source_sealed'])
        observed=read_json(self.task/state['source_feature_observation']['path'])
        self.assertEqual({u['id'] for u in observed['units']},{'left','right'})
        self.assertEqual(len(observed['features']),2)

    def test_outline_cannot_shrink_to_empty_or_incomplete_scope(self):
        for change in ({'units':[]},{'complete_scope':False}):
            request=self.outline();request['outline'].update(change)
            with self.assertRaises(ValueError):self.send(request)

    def test_seal_cannot_skip_an_outline_unit(self):
        self.send(self.outline());self.send(self.chunk('left'))
        with self.assertRaises(ValueError):self.send({'operation':'source_seal'})
        self.assertIsNone(self.state().get('source_feature_observation'))

    def test_conflicting_chunk_cannot_overwrite_observed_features(self):
        self.send(self.outline());self.send(self.chunk('left'))
        request=self.chunk('left');request['observation']['features'][0]['requirements']=[]
        with self.assertRaisesRegex(ValueError,'Chunk identity conflict'):self.send(request)

    def test_conflicting_row_with_new_chunk_id_is_rejected(self):
        self.send(self.outline());self.send(self.chunk('left'))
        request=self.chunk('left');request['chunk_id']='different';request['observation']['units'][0]['source_evidence']='Changed claim'
        with self.assertRaisesRegex(ValueError,'Frozen row conflict'):self.send(request)

    def test_observation_cannot_copy_native_owners(self):
        self.send(self.outline());left=self.chunk('left');left['observation']['features'][0]['owners']=['drawn']
        with self.assertRaisesRegex(ValueError,'before choosing native'):self.send(left)
        self.assertEqual(inc.counts(inc.load(self.task,self.state()))['observed_units'],0)

    def test_bad_cross_reference_can_be_corrected_with_retained_checkpoint(self):
        self.send(self.outline());left=self.chunk('left');left['observation']['units'][0]['spatial']['frame']='missing'
        self.send(left);self.send(self.chunk('right'))
        with self.assertRaises(ValueError):self.send({'operation':'source_seal'})
        state=self.state();value=inc.load(self.task,state);prior=next(u for u in value['units'] if u['id']=='left')
        from core.common import identity
        repaired=self.chunk('left');repaired.update(chunk_id='left-correction',prior_checkpoint=state['incremental_contract'],
            corrections={'units/left':{'prior_hash':identity(prior),'reason':'Correct a mistyped frame ID',
                'source_evidence':'The original left square is in the observed canvas frame'}})
        self.send(repaired);self.send({'operation':'source_seal'})
        self.assertTrue(inc.load(self.task,self.state())['source_sealed'])

    def test_full_spatial_validator_is_used_at_seal(self):
        self.send(self.outline());left=self.chunk('left');left['observation']['units'][0]['spatial']['mode']='solid'
        self.send(left);self.send(self.chunk('right'))
        with self.assertRaisesRegex(ValueError,'orientation'):self.send({'operation':'source_seal'})

    def test_binding_phase_cannot_begin_before_original_seal(self):
        self.send(self.outline())
        with self.assertRaises(ValueError):self.send({'operation':'bind_chunk','chunk_id':'a','binding':{}},'component_contract')

    def test_binding_chunks_persist_without_creating_contract(self):
        self.observed()
        request={'operation':'bind_chunk','chunk_id':'left','binding':{'scene':{'objects':[]},'contract':{
            'feature_bindings':[{'feature':'left.outline','component':'left','owners':['left.native'],'representation':{'family':'preset'}}]}}}
        self.send(request,'component_contract');state=self.state();value=inc.load(self.task,state)
        self.assertEqual(inc.counts(value)['pending_features'],['right.outline'])
        self.assertIsNone(state.get('component_workflow'))
        with self.assertRaises(ValueError):self.send({'operation':'bind_seal'},'component_contract')

    def test_binding_chunk_cannot_lower_independent_policy(self):
        self.observed()
        request={'operation':'bind_chunk','chunk_id':'a','binding':{'contract':{'workflow_version':'1.32.0'}}}
        with self.assertRaisesRegex(ValueError,'cannot lower'):self.send(request,'component_contract')

    def test_nonfinite_or_oversize_chunk_is_rejected(self):
        self.send(self.outline());request=self.chunk('left');request['observation']['features'][0]['roi'][0]=float('nan')
        with self.assertRaises(ValueError):self.send(request)

    def test_source_outline_cycle_is_rejected(self):
        request=self.outline();request['outline']['units'][0]['parent']='right';request['outline']['units'][1]['parent']='left'
        with self.assertRaisesRegex(ValueError,'cycle'):self.send(request)

    def test_packet_template_does_not_fill_unknown_original_geometry(self):
        self.send(self.outline());state=self.state();packet={'packet_id':'new','kind':'component_contract_source','target':'source_features'}
        inc.template(self.task,state,packet);template=read_json(self.task/packet['submission_template']['path'])
        self.assertEqual(template['component_request']['observation']['units'],[])
        self.assertEqual(packet['incremental']['coverage']['pending_units_count'],2)

    def test_intermediate_and_forged_accepted_state_are_not_deliverable(self):
        before=digest(self.task/'state.json');result=check(self.task)
        self.assertFalse(result['allow_finish']);self.assertEqual(digest(self.task/'state.json'),before)
        state=self.state();state['stage']='accepted';state['acceptance']={'status':'ACCEPTED'};a._save(self.task,state)
        self.assertFalse(check(self.task)['allow_finish'])

    def test_finish_adapter_rejects_candidate_without_mutating_state(self):
        before=digest(self.task/'state.json')
        proc=subprocess.run([sys.executable,'-I','-B',str(SCRIPTS/'check_before_finish.py'),str(self.task),'--attachment',str(self.project/'draft.pptx')],capture_output=True,text=True)
        self.assertEqual(proc.returncode,6,proc.stderr);self.assertFalse(json.loads(proc.stdout)['allow_finish'])
        self.assertEqual(digest(self.task/'state.json'),before)

    def test_old_bound_policy_is_not_silently_relabelled(self):
        state=self.state();state.pop('execution_policy');a._save(self.task,state)
        self.assertIn('older execution policy',check(self.task)['reason'])
        self.assertNotIn('execution_policy',self.state())

    def test_forty_components_two_hundred_features_close_in_small_chunks(self):
        from core.recipes import node
        names=['unit'+str(i) for i in range(40)]
        boxes={name:[i%10*10,i//10*20,8,15] for i,name in enumerate(names)}
        request=self.outline();request['outline']['units']=[{'id':name,'roi':boxes[name],'source_evidence':'Synthetic protocol region '+name} for name in names]
        self.send(request)
        for index in range(0,40,10):
            units=[];features=[]
            for name in names[index:index+10]:
                chunk=self.chunk('left');unit=chunk['observation']['units'][0]
                unit.update(id=name,roi=boxes[name]);units.append(unit)
                for detail in range(5):
                    feature=copy.deepcopy(chunk['observation']['features'][0]);feature.update(id=name+'.f'+str(detail),unit=name,roi=boxes[name]);features.append(feature)
            self.send({'operation':'source_chunk','chunk_id':'source'+str(index),'observation':{'units':units,'features':features,
                'spatial':{'frames':[{'id':'canvas','kind':'canvas','units':'source_px','owner_unit':names[0],'source_evidence':'Synthetic protocol source frame'}],
                    'landmarks':[],'relations':[],'footprints':[]}}})
        self.send({'operation':'source_seal'})
        for index in range(0,40,10):
            objects=[];rows=[];bindings=[]
            for name in names[index:index+10]:
                owner=name+'.native';objects.append(node(owner,'shape',boxes[name],{'preset':'rect'},fill='4477AA',stroke='17324D',line_width=1))
                rows.append({'id':name,'route':'fixed_parameters','owners':[owner],'source_units':[name],
                    'source_evidence':'Synthetic bounded native correspondence','source_refs':[self.source],'roi':boxes[name],
                    'frozen_parameters':True,'metrics':[]})
                bindings.extend({'feature':name+'.f'+str(detail),'component':name,'owners':[owner],'representation':{'family':'preset'}} for detail in range(5))
            self.send({'operation':'bind_chunk','chunk_id':'binding'+str(index),'binding':{'scene':{'objects':objects},
                'contract':{'components':rows,'feature_bindings':bindings}}},'component_contract')
        result=self.send({'operation':'bind_seal'},'component_contract')
        self.assertEqual(result['coverage']['components'],40);self.assertEqual(result['coverage']['bound_features'],200)
        state=self.state();value=inc.load(self.task,state)
        self.assertTrue(value['binding_sealed']);self.assertEqual(value['sealed_contract'],state['component_workflow']['contract'])
        self.assertFalse(list(self.task.rglob('*.pptx')),'Staging/sealing cannot construct native files')

    def test_empty_or_incomplete_component_ledger_is_never_ready(self):
        from core.component_protocol import ready_for_final
        self.assertFalse(ready_for_final({'components':[]},{'components':{},'layout_ready':True})['ready'])
        self.assertFalse(ready_for_final({'components':[{'id':'a'}]},{'components':{},'layout_ready':True})['ready'])

    def test_sqlite_connection_is_closed_at_context_exit(self):
        from core.state_repository import Repository
        import sqlite3
        repo=Repository(self.task)
        with repo.connection() as connection:connection.execute('SELECT 1').fetchone()
        with self.assertRaises(sqlite3.ProgrammingError):connection.execute('SELECT 1')

    def test_staged_scalar_typo_requires_current_prior_bound_correction(self):
        self.observed()
        first={'operation':'bind_chunk','chunk_id':'canvas','binding':{'scene':{'canvas':{'width':100,'height':100,'unit':'px','target_width_inches':0}}}}
        self.send(first,'component_contract');state=self.state()
        request={'operation':'bind_chunk','chunk_id':'canvas-fixed','binding':{'scene':{'canvas':{'target_width_inches':10}}}}
        with self.assertRaisesRegex(ValueError,'Frozen field conflict'):self.send(request,'component_contract')
        from core.common import identity
        request.update(prior_checkpoint=self.state()['incremental_contract'],corrections={
            'scene.canvas/target_width_inches':{'prior_hash':identity(0),'reason':'Correct invalid physical-width entry',
                'source_evidence':'Source pixel canvas remains 100 by 100; standard physical output width is ten inches'}})
        self.send(request,'component_contract')
        self.assertEqual(inc.load(self.task,self.state())['scene']['canvas']['target_width_inches'],10)

    def test_stale_accepted_final_cannot_remain_the_next_action_exit(self):
        from core.component_workflow import invalidate_stale_final,implementation
        state=self.state();state['capabilities']={'fingerprint':'current-render'}
        state['component_workflow']={'contract':{'path':'contract.json','sha256':'c'*64}}
        candidate={'pptx':{'sha256':'b'*64},'preview':{'sha256':'d'*64}}
        proof={'status':'ACCEPTED','implementation':'obsolete','source_hash':self.source['sha256'],
            'contract':state['component_workflow']['contract'],'pptx_hash':'b'*64,'preview_hash':'d'*64,'render_environment':'current-render'}
        file=self.task/'scratch/final.json';write_json(file,proof);ref={'path':'scratch/final.json','sha256':digest(file)}
        ledger={'final_result':ref,'final_dirty':False}
        self.assertTrue(invalidate_stale_final(self.task,state,{},ledger,candidate))
        self.assertTrue(ledger['final_dirty']);self.assertIsNone(ledger['final_result']);self.assertEqual(ledger['retained_final_results'],[ref])
        self.assertFalse(invalidate_stale_final(self.task,state,{},ledger,candidate))


if __name__=='__main__':unittest.main()
