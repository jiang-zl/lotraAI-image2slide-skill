"""Behavioral positive/counterexample checks, independent of the reported art."""
import copy
import json
import math
from pathlib import Path
import sys
import unittest
import tempfile
import hashlib
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO/'.lotraAI-build/validation-v134'
ROOT.mkdir(parents=True,exist_ok=True)
SKILL = REPO/'skills/lotra-image2slide-skill'
sys.path.insert(0,str(SKILL/'scripts'))
import numpy as np
from PIL import Image, ImageDraw
from core import component_source_features as f, native_surfaces as s, surface_metrics as m
from core.recipes import node
from core.component_protocol import metric_result
from core.component_protocol import ready_for_final


def observation():
    return {'schema':f.VERSION,'source_hash':'a'*64,'canvas':[100,100],
        'basis':'unchanged_original','observer':'host_model','observations':'Original square with a visible inner line.',
        'units':[{'id':'icon','roi':[0,0,100,100],'source_evidence':'Original full icon',
                  'decomposition':{'state':'leaf','reason':'One bounded native contour and a separate visible line.'}}],
        'features':[{'id':'outline','unit':'icon','kind':'silhouette','roi':[5,5,90,90],
                     'source_evidence':'Original square boundary','observability':'clear','requirements':['editable','closed_contour']},
                    {'id':'inside','unit':'icon','kind':'internal_line','roi':[20,20,60,60],
                     'source_evidence':'Original independent internal line','observability':'clear','requirements':['editable']}]}


def metric(name, **spec):
    return {'id':name,'unit':m.UNITS[name],'role':'target','direction':'lower','threshold':0,
            'measurement':{'adapter':name,'coordinate_space':'component_roi','source_evidence':'Independent original probe',
                           'window':[0,0,100,100],'foreground':{'mode':'dark','threshold':.5},**spec}}


def image(draw):
    im=Image.new('RGB',(100,100),'white');draw(ImageDraw.Draw(im))
    return np.asarray(im,float)/255


class SourceContracts(unittest.TestCase):
    def test_original_observation_has_no_candidate_owners(self):
        value=observation();f.validate_observation(value,'a'*64,[100,100])
        value['features'][0]['owners']=['drawn_square']
        with self.assertRaises(ValueError):f.validate_observation(value,'a'*64,[100,100])

    def test_recursive_stop_matches_children(self):
        value=observation();value['units'][0]['decomposition']['state']='split'
        with self.assertRaises(ValueError):f.validate_observation(value,'a'*64,[100,100])

    def test_cycle_is_rejected(self):
        value=observation();value['units'][0]['parent']='icon'
        with self.assertRaises(ValueError):f.validate_observation(value,'a'*64,[100,100])

    def test_required_uncertainty_is_not_pass(self):
        row={'source_features':observation()['features']}
        row['source_features'][1]['observability']='unresolved'
        self.assertFalse(f.source_check(row)['passed'])

    def test_single_solid_head_cannot_supply_a_color_partition(self):
        head=node('head','shape',[10,10,20,20],{'preset':'ellipse'},fill='2244CC')
        feature={'id':'head_regions','requirements':['color_partition']}
        binding={'owners':['head'],'representation':{'family':'preset'}}
        with self.assertRaisesRegex(ValueError,'REPRESENTATION_INSUFFICIENT'):
            f.capability_preflight(binding,feature,{'head':head})

    def test_separate_native_regions_can_supply_color_partition(self):
        a=node('head','shape',[10,10,20,20],{'preset':'ellipse'},fill='EEEEEE')
        b=node('cap','shape',[10,10,20,8],{'preset':'rect'},fill='2244CC')
        binding={'owners':['head','cap'],'representation':{'family':'native_composite',
                 'simpler_options':[{'family':'preset','reason':'Independent cap and face','source_evidence':'Original split'}]}}
        self.assertTrue(f.capability_preflight(binding,{'id':'head','requirements':['color_partition']},{'head':a,'cap':b})['passed'])

    def test_raster_icon_is_not_silent_native_fallback(self):
        photo=node('bitmap','photo',[0,0,20,20],{})
        with self.assertRaises(ValueError):
            f.capability_preflight({'owners':['bitmap'],'representation':{'family':'raster_exception','exception_reason':'hard'}},
                                  {'id':'icon','kind':'symbol','requirements':['editable']},{'bitmap':photo})

    def test_local_generic_pass_cannot_hide_missing_feature_review(self):
        row={'source_features':observation()['features'],'feature_basis':'current'}
        with self.assertRaises(ValueError):f.local_review(row,{'feature_basis':'current','verdict':'PASS','observations':'Looks fine'})
        result=f.local_review(row,{'feature_basis':'current','feature_checks':[
            {'feature':'outline','verdict':'PASS','observations':'Corresponding boundary'},
            {'feature':'inside','verdict':'FAIL','observations':'Missing gray line'}]})
        self.assertFalse(result['passed'])

    def test_native_table_cell_retains_exact_editable_source_text(self):
        table=node('table','table',[0,0,80,20],{'rows':[['A','B']]})
        result=f.capability_preflight({'owners':['table'],'representation':{'family':'native_text','table_cell':[0,1]}},
            {'id':'b','kind':'text','text':'B','requirements':['editable','text']},{'table':table})
        self.assertTrue(result['passed'])

    def test_native_table_cell_cannot_bind_another_cell_literal(self):
        table=node('table','table',[0,0,80,20],{'rows':[['A','B']]})
        with self.assertRaisesRegex(ValueError,'exact source literal'):
            f.capability_preflight({'owners':['table'],'representation':{'family':'native_text','table_cell':[0,1]}},
                {'id':'a','kind':'text','text':'A','requirements':['editable','text']},{'table':table})


class NativeConstruction(unittest.TestCase):
    def test_extrusion_generates_only_declared_visible_wall(self):
        owners,manifest=s.construct({'id':'solid','kind':'extruded_contour','source_evidence':'One visible side span',
            'contour':s._poly([[10,10],[30,10],[30,30],[10,30]]),'depth':[4,8],
            'front_style':{'fill':'EEEEEE'},
            'walls':[{'id':'right','first_segment':1,'segment_count':1,'style':{'fill':'AAAAAA'}}]})
        self.assertEqual([x['role'] for x in manifest['parts']],['side_surface','front_surface'])
        self.assertEqual(len(owners),2)

    def test_ellipse_stack_does_not_invent_connecting_walls(self):
        owners,_=s.construct({'id':'levels','kind':'ellipse_stack','source_evidence':'Two visible ellipse levels',
            'levels':[{'id':'lower','center':[50,60],'radii':[20,8],'style':{'fill':'AAAAAA'}},
                      {'id':'upper','center':[50,50],'radii':[20,8],'style':{'fill':'EEEEEE'}}]})
        self.assertEqual([x['id'] for x in owners],['levels.lower','levels.upper'])

    def test_source_free_template_preserves_paint_order_without_old_surface_claims(self):
        from core.knowledge import template_from_scene
        group=node('root','group',[0,0,100,100],{})
        a=node('a','shape',[10,10,40,40],{'preset':'rect'},parent='root',fill='AAAAAA');a['z_order']=20
        b=node('b','shape',[10,10,40,40],{'preset':'rect'},parent='root',fill='BBBBBB');b['z_order']=10
        a['content']['source_surface']={'construction':'old-private-task','version':s.VERSION}
        recipe=template_from_scene({'objects':[group,a,b],'relations':[]},'root')
        objects=recipe['parameters']['objects']
        self.assertEqual([x['style']['fill'] for x in objects[1:]],['BBBBBB','AAAAAA'])
        self.assertFalse(any('source_surface' in x['content'] for x in objects))

    def test_shared_prism_vertices_are_not_independent_guesses(self):
        spec={'id':'box','kind':'prism','source_evidence':'Three original faces',
              'footprint':[[10,10],[50,20],[40,40],[0,30]],'depth':[0,12],
              'walls':[{'id':'wall','edge':1,'style':{'fill':'CCCCCC'}}],
              'top_style':{'fill':'FFFFFF'}}
        owners,manifest=s.construct(spec)
        self.assertEqual(len(owners),2)
        def world(o):
            x,y,w,h=o['bbox'];return [[x+p[0]*w,y+p[1]*h] for c in o['content']['contours'][0]['commands'] for p in c['points']]
        wall,top=map(world,owners)
        self.assertEqual(wall[:2],top[1:3])
        self.assertIn('shared_edges',manifest['parts'][0]['capabilities'])

    def test_ring_has_a_real_inner_wall_and_continuous_cubics(self):
        spec={'id':'ring','kind':'annular_sector','source_evidence':'Original annular top and inner wall',
              'center':[50,50],'radii':[40,20],'inner_radii':[26,12],'depth':[0,10],
              'start_degrees':180,'end_degrees':360,'top_style':{'fill':'EEEEEE'},
              'walls':[{'id':'inside','role':'inner_wall','span':[180,360],'style':{'fill':'AAAAAA'}}]}
        owners,manifest=s.construct(spec)
        self.assertEqual(manifest['parts'][0]['role'],'inner_wall')
        self.assertIn('hole',manifest['parts'][-1]['capabilities'])
        self.assertTrue(any(c['op']=='cubicBezTo' for c in owners[0]['content']['contours'][0]['commands']))
        self.assertLess(sum(len(c.get('commands',[])) for o in owners for c in o['content']['contours']),30)

    def test_band_preserves_independent_boundaries(self):
        spec={'id':'signal','kind':'band','source_evidence':'Unequal observed top/bottom bands',
              'upper':s._poly([[10,10],[30,20],[50,10]],False),
              'lower':s._poly([[10,15],[30,32],[50,16]],False),'style':{'fill':'3355CC'}}
        owners,_=s.construct(spec);self.assertEqual(owners[0]['render_type'],'path')
        self.assertEqual(owners[0]['bbox'],[10,10,40,22])

    def test_projective_plane_preserves_vertices_and_bounded_curve(self):
        frame={'homography':[[1,0,10],[0,1,20],[.002,0,1]],'source_evidence':'Observed perspective plane'}
        self.assertEqual(s.project([0,0],frame),[10,20])
        commands=[{'op':'moveTo','points':[[0,0]]},{'op':'cubicBezTo','points':[[20,40],[40,-10],[60,20]]}]
        encoded=s._project_commands(commands,frame,.02)
        self.assertLess(len(encoded),130)
        self.assertEqual(encoded[-1]['points'][-1],s.project([60,20],frame))

    def test_construction_does_not_overwrite_existing_user_owner(self):
        scene={'objects':[node('b.top','shape',[0,0,10,10],{'preset':'rect'})]}
        contract={'native_constructions':[{'id':'b','kind':'prism','source_evidence':'Observed',
            'footprint':[[0,0],[20,0],[20,20],[0,20]],'depth':[0,5],'top_style':{'fill':'FFFFFF'}}]}
        with self.assertRaisesRegex(ValueError,'collides'):s.expand(scene,contract)


class CorrespondenceAndFinal(unittest.TestCase):
    def setUp(self):
        self.task=ROOT/'checks/fixtures'/uuid4().hex
        self.task.mkdir(parents=True)
        file=self.task/'observed.json';file.write_text(json.dumps(observation()),encoding='utf-8')
        self.ref={'path':'observed.json','sha256':hashlib.sha256(file.read_bytes()).hexdigest()}
        self.state={'source':{'sha256':'a'*64},'source_size':[100,100],'source_feature_observation':self.ref}
        self.scene={'objects':[node('outline','shape',[5,5,90,90],{'preset':'rect'},fill='FFFFFF'),
                               node('line','connector',[20,50,60,0],{'points':[[20,50],[80,50]]})]}
        self.contract={'workflow_version':'1.34.0','source_inventory':observation()['units'],
            'components':[{'id':'body','route':'fixed_parameters','owners':['outline']},
                          {'id':'inside','route':'fixed_parameters','owners':['line']}],
            'feature_bindings':[{'feature':'outline','component':'body','owners':['outline'],'representation':{'family':'preset'}},
                                {'feature':'inside','component':'inside','owners':['line'],'representation':{'family':'native_connector'}}]}

    def tearDown(self):pass  # Retain the small private source/evidence fixture.

    def test_legacy_source_ledger_required_pending_interface_is_retained(self):
        from core import source_features as legacy
        state={'objectives':{'source_feature_ledger':True},'source_size':[100,100]}
        self.assertTrue(legacy.required(state))
        self.assertEqual(legacy.pending(self.task,state)[0]['status'],'missing_inventory')

    def test_legacy_three_argument_binding_still_records_its_own_debt(self):
        from core import source_features as legacy
        state={'source':{'sha256':'a'*64},'source_size':[100,100],'objectives':{'source_feature_ledger':True},
               'analysis':{'components':[{'id':'icon','parts':['body']}]},'quality':{}}
        legacy.bind(self.task,state,{'source_hash':'a'*64,'features':[{'id':'outline','roi':[0,0,100,100],
            'kind':'shape','status':'observed','evidence':'Original square','owner':'icon','source_part':'body',
            'importance':'major','quality_property':'boundary'}]})
        self.assertTrue((self.task/state['source_features']['path']).is_file())
        self.assertEqual(legacy.pending(self.task,state)[0]['id'],'outline')

    def test_missing_original_feature_cannot_bind(self):
        self.contract['feature_bindings'].pop()
        with self.assertRaises(ValueError):f.bind(self.task,self.state,self.contract,self.scene)

    def table_fixture(self,omit_second=False):
        value=observation();value['features']=[{'id':'grid','unit':'icon','kind':'relation','roi':[0,0,100,100],
            'source_evidence':'Original two-cell table grid','observability':'clear','requirements':['editable','closed_contour']}]
        for i,text in enumerate(['A','B'][:1 if omit_second else 2]):
            value['features'].append({'id':'text'+str(i),'unit':'icon','kind':'text','text':text,'roi':[i*40,0,40,20],
                'source_evidence':'Original cell '+str(i),'observability':'clear','requirements':['editable','text']})
        file=self.task/'table-observation.json';file.write_text(json.dumps(value),encoding='utf-8')
        from core.common import digest
        self.state['source_feature_observation']={'path':file.name,'sha256':digest(file)}
        self.scene={'objects':[node('table','table',[0,0,80,20],{'rows':[['A','B']]})]}
        self.contract.update(source_inventory=value['units'],components=[{'id':'table','route':'fixed_parameters','owners':['table']}],
            feature_bindings=[{'feature':'grid','component':'table','owners':['table'],'representation':{'family':'native_composite',
                'simpler_options':[{'family':'preset','reason':'Independent native cells','source_evidence':'Original table grid'}]}}])
        for i in range(1 if omit_second else 2):
            self.contract['feature_bindings'].append({'feature':'text'+str(i),'component':'table','owners':['table'],
                'representation':{'family':'native_text','table_cell':[0,i]}})

    def test_native_table_all_populated_cells_have_source_correspondence(self):
        self.table_fixture();f.bind(self.task,self.state,self.contract,self.scene)
        self.assertEqual(len(self.contract['components'][0]['source_features']),3)

    def test_single_table_owner_cannot_hide_an_unobserved_populated_cell(self):
        self.table_fixture(omit_second=True)
        with self.assertRaisesRegex(ValueError,'Every populated native table cell'):
            f.bind(self.task,self.state,self.contract,self.scene)

    def test_saved_feature_probe_rejects_a_missing_required_line(self):
        original=self.task/'original.png';actual=self.task/'actual.png'
        im=Image.new('RGB',(100,100),'white');ImageDraw.Draw(im).line((10,50,90,50),fill=(150,150,150),width=2)
        im.save(original);Image.new('RGB',(100,100),'white').save(actual)
        from core.common import digest
        state={'source_size':[100,100],'source':{'path':'original.png','sha256':digest(original)}}
        candidate={'preview':{'path':'actual.png','sha256':digest(actual)}}
        target=metric('feature_missing_fraction',foreground={'mode':'dark','threshold':.75},support_radius_px=1)
        target['threshold']=.1
        result=f.probes(self.task,state,candidate,[{'id':'inside','roi':[0,0,100,100],'metrics':[target]}])
        self.assertFalse(result['passed'])

    def test_cli_compacted_envelope_is_readable_by_managed_selector(self):
        from core.context_efficiency import bounded_output
        from core.common import write_json,digest
        from packet_detail import select
        original=self.task/'original.png';Image.new('RGB',(10,10),'white').save(original)
        write_json(self.task/'state.json',{'task_id':'selector-fixture','source':{'path':'original.png','sha256':digest(original)}})
        value={'status':'WORK_PACKET','packet':{'feature_checks':[{'feature':str(i),'observations':'located original detail '*40} for i in range(40)]}}
        display=bounded_output(self.task,value,1000)
        result=select(self.task,display['execution_reference'],['packet','feature_checks'],limit=2,managed=True)
        self.assertEqual(result['total'],40)
        self.assertEqual(len(result['items']),2)

    def test_envelope_registration_does_not_authorize_unrelated_task_file(self):
        from core.common import write_json,digest
        from core.context_control import authorize
        original=self.task/'original.png';Image.new('RGB',(10,10),'white').save(original)
        write_json(self.task/'state.json',{'task_id':'selector-fixture','source':{'path':'original.png','sha256':digest(original)}})
        unrelated=self.task/'unrelated.json';write_json(unrelated,{'not_a_dependency':True})
        with self.assertRaisesRegex(ValueError,'CONTEXT_SCOPE_MISMATCH'):
            authorize(self.task,{'path':'unrelated.json','sha256':digest(unrelated)})

    def test_extra_unexplained_native_paint_cannot_bind(self):
        self.scene['objects'].append(node('extra','shape',[1,1,5,5],{'preset':'rect'},fill='000000'))
        with self.assertRaisesRegex(ValueError,'no original feature'):f.bind(self.task,self.state,self.contract,self.scene)

    def test_matching_contract_has_scoped_feature_bases(self):
        f.bind(self.task,self.state,self.contract,self.scene)
        self.assertNotEqual(self.contract['components'][0]['feature_basis'],self.contract['components'][1]['feature_basis'])
        self.assertEqual([x['id'] for x in self.contract['components'][1]['source_features']],['inside'])

    def test_six_generic_final_passes_cannot_replace_original_omission_review(self):
        f.bind(self.task,self.state,self.contract,self.scene)
        self.assertFalse(f.final_review(self.task,self.contract,{'dimensions':{'appearance':{'passed':True}}})['passed'])
        from core.common import identity
        review={'source_feature_review':{'source_observation_hash':self.ref['sha256'],
            'bindings_hash':identity(self.contract['feature_bindings']),'basis':'original_to_output',
            'observations':'Independent original-unit comparison',
            'feature_checks':[{'feature':i,'verdict':'PASS','observations':'Located original/current comparison'} for i in ['outline','inside']],
            'omission_checks':[],'unmapped_features':[]}}
        self.assertFalse(f.final_review(self.task,self.contract,review)['passed'])
        review['source_feature_review']['omission_checks']=[{'unit':'icon','verdict':'PASS','observations':'Rechecked the original interior as well as contour'}]
        self.assertTrue(f.final_review(self.task,self.contract,review)['passed'])

    def test_discovered_source_change_blocks_stale_acceptance(self):
        contract={'components':[{'id':'a'}],'relations':[]}
        ledger={'components':{'a':{'status':'QUALIFIED'}},'layout_ready':True,'source_observation_dirty':True}
        self.assertFalse(ready_for_final(contract,ledger)['ready'])

    def test_legacy_final_policy_is_retained_without_fabricated_new_pass(self):
        result=f.final_review(self.task,{'workflow_version':'1.33.0'},{})
        self.assertTrue(result['legacy_policy_retained']);self.assertFalse(result['applicable'])


class SavedPixelCounterexamples(unittest.TestCase):
    def test_full_annular_surface_has_no_radial_stroke_bridge(self):
        nodes,_=s.construct({'id':'ring','kind':'annular_sector','source_evidence':'Full observed ring',
            'center':[50,50],'radii':[40,20],'inner_radii':[20,10],'depth':[0,4],
            'top_style':{'fill':'EEEEEE','stroke':'777777','line_width':1}})
        contours=nodes[0]['content']['contours']
        self.assertEqual(len(contours),2)
        self.assertFalse(any(c['op']=='lnTo' for p in contours for c in p['commands']))

    def test_curved_band_join_uses_only_the_lower_endpoint(self):
        nodes,_=s.construct({'id':'curve_band','kind':'band','source_evidence':'Two independently observed cubic boundaries',
            'upper':[{'op':'moveTo','points':[[0,10]]},{'op':'cubicBezTo','points':[[10,0],[20,20],[30,10]]}],
            'lower':[{'op':'moveTo','points':[[0,16]]},{'op':'cubicBezTo','points':[[10,10],[20,30],[30,18]]}],
            'style':{'fill':'405BCB','line_width':0}})
        commands=nodes[0]['content']['contours'][0]['commands']
        self.assertEqual(len(next(c for c in commands if c['op']=='lnTo')['points']),1)
        self.assertEqual(sum(c['op']=='cubicBezTo' for c in commands),2)

    def test_missing_low_contrast_line_is_detected_locally(self):
        source=image(lambda d:d.line((10,50,90,50),fill=(150,150,150),width=2))
        actual=np.ones_like(source)
        target=metric('feature_missing_fraction',foreground={'mode':'dark','threshold':.75},support_radius_px=1)
        m.validate(target)
        self.assertEqual(m.measure(source,source,target)['value'],0)
        self.assertEqual(m.measure(source,actual,target)['value'],1)

    def test_face_color_and_occlusion_mismatch(self):
        source=image(lambda d:d.rectangle((0,0,99,99),fill=(220,220,220)))
        actual=image(lambda d:d.rectangle((0,0,99,99),fill=(40,70,210)))
        for name in ('face_color_error','occlusion_color_error'):
            target=metric(name)
            self.assertGreater(m.measure(source,actual,target)['value'],.3)

    def test_wrong_edge_orientation_is_not_compensated_by_alignment(self):
        source=image(lambda d:d.line((10,30,90,30),fill='black',width=2))
        actual=image(lambda d:d.line((20,20,70,70),fill='black',width=2))
        result=m.measure(source,actual,metric('edge_angle_error'))
        self.assertTrue(result['valid']);self.assertGreater(result['value'],40)

    def test_removed_hole_is_a_hard_count_difference(self):
        source=image(lambda d:(d.ellipse((10,10,90,90),fill='black'),d.ellipse((30,30,70,70),fill='white')))
        actual=image(lambda d:d.ellipse((10,10,90,90),fill='black'))
        result=m.measure(source,actual,metric('hole_count_error'))
        self.assertTrue(result['valid']);self.assertEqual(result['value'],1)

    def test_material_lightness_order_is_source_relative(self):
        source=image(lambda d:(d.rectangle((0,0,49,99),fill=(230,230,230)),d.rectangle((50,0,99,99),fill=(160,160,160))))
        actual=source[:,::-1,:].copy()
        target=metric('face_lightness_error',windows=[[0,0,40,100],[60,0,40,100]])
        self.assertGreater(m.measure(source,actual,target)['value'],.5)

    def test_invalid_measurement_never_becomes_a_passing_zero(self):
        target=metric('edge_angle_error')
        result=m.measure(np.ones((100,100,3)),np.ones((100,100,3)),target)
        self.assertFalse(result['valid'])
        self.assertFalse(metric_result({'metrics':[target]},{target['id']:result})['passed'])


class ExportPreviewComparisons(unittest.TestCase):
    def exercise(self,base_size,*,changed=False):
        from unittest.mock import patch
        from core import transient_export as export
        from core.common import digest,write_json
        root=ROOT/'export-preview-fixtures'/uuid4().hex;root.mkdir(parents=True)
        before=root/'before.pptx';after=root/'after.pptx'
        before.write_bytes(b'synthetic original package');after.write_bytes(before.read_bytes())
        host={k:'same-host' for k in ('backend','backend_version','office_build','font_inventory_hash','renderer_script_hash')}
        def render(pptx,folder,size,pixels,actual_size):
            folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
            Image.new('RGB',actual_size,pixels).save(folder/'Final_preview.png')
            (folder/'Final.pdf').write_bytes(b'synthetic PDF; fingerprint is separately stubbed')
            row={**host,'status':'PASS','pptx_hash':digest(pptx),'pdf_hash':digest(folder/'Final.pdf'),
                'pdf':{'status':'EXPORTED'},'pages':[{'path':'Final_preview.png'}]}
            write_json(folder/'render.json',row);return row
        base=root/'accepted-render';render(before,base,None,'white',base_size)
        calls=[]
        def actual_render(pptx,folder,caps,size):
            calls.append((Path(pptx).name,size))
            return render(pptx,folder,size,'black' if changed and Path(pptx)==after else 'white',(32,20))
        with patch('core.delivery_size.verify_package'),patch('core.delivery_size.package_plan',return_value={}),\
             patch('core.tool_router.render_saved',side_effect=actual_render),\
             patch.object(export,'fingerprint',return_value={'pages':[{'pixels':'fixed'}]}),\
             patch.object(export,'release',return_value={'status':'DISPOSED'}):
            if changed:
                with self.assertRaisesRegex(export.EquivalenceError,'preview pixels changed'):
                    export.validate(before,after,root/'comparison',{},base_render=base/'render.json')
            else:
                proof=export.validate(before,after,root/'comparison',{},base_render=base/'render.json')
                self.assertEqual(proof['preview_pixels'],'EXACT')
        return calls

    def test_different_base_canvas_requires_fresh_original_render(self):
        self.assertEqual(self.exercise((16,10)),[('after.pptx',2000),('before.pptx',2000)])

    def test_same_base_canvas_retains_exact_preview_reuse(self):
        self.assertEqual(self.exercise((32,20)),[('after.pptx',2000)])

    def test_fresh_comparator_still_rejects_changed_pixels(self):
        self.assertEqual(self.exercise((16,10),changed=True),[('after.pptx',2000),('before.pptx',2000)])


if __name__=='__main__':unittest.main(verbosity=2)
