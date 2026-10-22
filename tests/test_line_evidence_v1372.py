"""Independent source geometry and saved-byte/render/review counterexamples."""
import copy, math, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from lxml import etree as E
from PIL import Image,ImageDraw

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'skills/lotra-image2slide-skill/scripts'))
from core import line_contracts as c,line_geometry as g,line_verification as v
from core.mathml import NS


def source_line(points=((20,20),(140,20),(140,90)),**changes):
    points=[list(p) for p in points]
    value={'schema':c.SCHEMA,'role':'decoration','coordinate_space':'source_canvas','direction':'undirected',
        'path':{'kind':'polyline' if len(points)>2 else 'straight','segments':[{'kind':'line','points':[a,b]} for a,b in zip(points,points[1:])]},
        'ends':[{'point':p,'marker':{'type':'none','filled':False,'anchor_role':'path_endpoint','anchor':p,'width':[0,0],'length':[0,0]},
                 'attachment':{'kind':'free','reason':'Independent test line','source_evidence':'Original endpoint','distance':[0,0]}} for p in (points[0],points[-1])],
        'stroke':{'width':[2,2],'opacity':[1,1],'colour':'000000','cap':'flat','join':'round','compound':'single','dash':{'kind':'solid'}},
        'limits':{'route':2,'endpoint':2,'marker':3,'colour':.1,'width':1,'angle_degrees':3,'source_evidence':'Source raster sampling'},
        'topology':{'junctions':[],'crossings':[],'shared':[]},'visibility':{'hidden':[]},'source_evidence':'Independently specified original route'}
    value.update(changes);return value


def entry(preset='bentConnector2',matrix=None,points=None,marker='none',tag='sp'):
    root=E.Element('{'+NS['p']+'}'+tag,nsmap={'p':NS['p'],'a':NS['a']})
    nv=E.SubElement(root,'{'+NS['p']+'}'+('nvCxnSpPr' if tag=='cxnSp' else 'nvSpPr'));E.SubElement(nv,'{'+NS['p']+'}cNvPr',id='2',name='route')
    if tag=='cxnSp':E.SubElement(nv,'{'+NS['p']+'}cNvCxnSpPr')
    props=E.SubElement(root,'{'+NS['p']+'}spPr')
    if points is None:
        preset_node=E.SubElement(props,'{'+NS['a']+'}prstGeom',prst=preset);E.SubElement(preset_node,'{'+NS['a']+'}avLst')
    else:
        geom=E.SubElement(props,'{'+NS['a']+'}custGeom');path=E.SubElement(E.SubElement(geom,'{'+NS['a']+'}pathLst'),'{'+NS['a']+'}path',w='200',h='120')
        for index,p in enumerate(points):
            op=E.SubElement(path,'{'+NS['a']+'}'+('moveTo' if index==0 else 'lnTo'))
            E.SubElement(op,'{'+NS['a']+'}pt',x=str(p[0]),y=str(p[1]))
    line=E.SubElement(props,'{'+NS['a']+'}ln',w='25400',cap='flat',cmpd='sng')
    E.SubElement(E.SubElement(line,'{'+NS['a']+'}solidFill'),'{'+NS['a']+'}srgbClr',val='000000')
    E.SubElement(line,'{'+NS['a']+'}round')
    E.SubElement(line,'{'+NS['a']+'}tailEnd',type=marker,w='med',len='med')
    return {'tag':tag,'node':root,'matrix':np.array(matrix if matrix is not None else [[120,0,20],[0,70,20],[0,0,1]],float),
            'parent_matrix':np.diag([1/12700,1/12700,1]),'frame':[20,20,120,70]}


def geometry(line,native=None):
    native=native or entry()
    row={'id':'line','parts':[{'owner':'route','role':'shaft'}],'source':line}
    decoded={'route':g.decode(native)}
    return row,g.native_checks(row,decoded,{'route':native},{},.002)


def pixels(points,size=(200,120),width=2):
    image=Image.new('RGB',size,'white');ImageDraw.Draw(image).line([tuple(p) for p in points],fill='black',width=width)
    return np.asarray(image,float)/255


class Lines(unittest.TestCase):
    def test_reordered_curved_loops_cannot_pass_equal_sets_and_length(self):
        origin=[80,60]
        loops=[{'kind':'cubic','points':[origin,a,b,origin]} for a,b in
            [([20,60],[80,0]),([80,0],[140,60]),([140,60],[80,120]),([80,120],[20,60])]]
        line=source_line((origin,origin));line['path']={'kind':'curve','segments':loops}
        native=entry();decoded=g.decode(native)
        decoded.update(segments=[loops[i] for i in (0,2,1,3)],start=origin,end=origin)
        row={'id':'line','parts':[{'owner':'route','role':'shaft'}],'source':line}
        check=g.native_checks(row,{'route':decoded},{'route':native},{},.002)['route']
        self.assertTrue(check['geometric_bound']['passed'],check)
        self.assertFalse(check['passed']);self.assertFalse(check['valid'])
        self.assertIn('ordered measurement',check['traversal_order']['reason'])

    def test_fixed_paint_cells_resolve_conservative_borderline(self):
        a=np.ones((6,6),bool);b=np.ones((6,6),bool)
        value=v.paint_cell_bound(a,b,((0,0),(2,0)),((1,1),(1,1)),2.4)
        self.assertTrue(value['valid']);self.assertTrue(value['passed'],value)
        self.assertEqual(value['method'],'refined_fixed_raster_cell_bound')
        self.assertLessEqual(value['upper'],2.4)

    def test_fixed_paint_cells_include_filled_interiors(self):
        a=np.ones((12,12),bool);b=a.copy();b[3:9,3:9]=False
        value=v.paint_cell_bound(a,b,((0,0),(0,0)),((1,1),(1,1)),1)
        self.assertTrue(value['valid']);self.assertFalse(value['passed'],value)
        self.assertGreater(value['lower'],1)

    def test_empty_or_unbounded_paint_cells_remain_invalid(self):
        self.assertFalse(v.paint_cell_bound(np.zeros((1,1),bool),np.ones((1,1),bool),((0,0),(0,0)),((1,1),(1,1)),1)['valid'])
        # A finite target cannot allocate an arbitrarily large dense proof grid.
        value=v.paint_cell_bound(np.ones((2,20000),bool),np.ones((2,20000),bool),((0,0),(0,0)),((1,1),(1,1)),.01)
        self.assertFalse(value['valid']);self.assertIn('budget',value['reason'])

    def test_bent2_correct_route_without_writer(self):
        _,checks=geometry(source_line())
        self.assertTrue(checks['route']['passed'],checks['route'])
        self.assertTrue(checks['terminals']['passed'],checks['terminals'])
        self.assertTrue(checks['stroke']['passed'],checks['stroke'])

    def test_equal_endpoints_bbox_and_length_wrong_elbow_fails_route(self):
        _,checks=geometry(source_line(((20,20),(20,90),(140,90))))
        self.assertFalse(checks['route']['passed']);self.assertTrue(checks['route']['valid'])
        self.assertGreater(checks['route']['value'],50)

    def test_short_arm_is_not_averaged_away(self):
        row,checks=geometry(source_line(((20,20),(140,20),(140,23))),entry(matrix=[[120,0,20],[0,3,20],[0,0,1]]))
        self.assertTrue(checks['route']['passed'])
        reference=pixels(((20,20),(140,20),(140,23)))
        actual=pixels(((20,20),(140,20)))
        row['source']['limits']['route']=.15
        result=v.render_check(row,checks,reference,actual)
        self.assertFalse(result['passed'],result)

    def test_signed_terminal_tangent_cannot_be_replaced_by_parallel(self):
        line=source_line(((20,20),(140,20)))
        native=entry(points=[[20,20],[10,20],[140,20]],matrix=[[200,0,0],[0,120,0],[0,0,1]])
        _,checks=geometry(line,native)
        self.assertFalse(checks['terminals']['passed'])
        self.assertLess(checks['terminals']['items'][0]['signed_tangent']['cosine'],0)

    def test_undirected_reverse_encoding_can_pass(self):
        native=entry(points=[[140,90],[140,20],[20,20]],matrix=[[200,0,0],[0,120,0],[0,0,1]])
        _,checks=geometry(source_line(),native)
        self.assertTrue(checks['route']['passed'],checks['route']);self.assertTrue(checks['terminals']['passed'])

    def test_arrow_reversed_fails_marker_without_render(self):
        _,checks=geometry(source_line(),entry(marker='triangle'))
        self.assertFalse(checks['markers']['passed'])

    def test_width_and_style_are_actual_saved_properties(self):
        native=entry();line=native['node'].find('p:spPr/a:ln',NS);line.set('w','127000');line.set('cap','rnd')
        _,checks=geometry(source_line(),native)
        self.assertFalse(checks['stroke']['passed'])

    def test_unknown_native_preset_never_gets_diagonal_fallback(self):
        with self.assertRaisesRegex(ValueError,'unsupported native preset'):g.decode(entry(preset='curvedConnector5'))

    def test_curve_flattening_preserves_backtracking(self):
        p,_=g.flatten([{'kind':'cubic','points':[[0,0],[100,0],[-100,0],[0,0]]}],.01)
        self.assertGreater(len(p),4);self.assertGreater(p[:,0].max(),20);self.assertLess(p[:,0].min(),-20)

    def test_closed_route_has_no_fictitious_terminals(self):
        line=source_line(((20,20),(140,20),(140,90),(20,90),(20,20)),ends=[])
        line['path']['kind']='closed'
        c.validate_line(line,{'id':'line'},{'line':{}})
        _,checks=geometry(line,entry(preset='rect'))
        self.assertTrue(checks['route']['passed'],checks['route']);self.assertFalse(checks['terminals']['applicable'])

    def test_normal_pixels_close_clear_line_without_deep(self):
        row,checks=geometry(source_line());image=pixels(((20,20),(140,20),(140,90)))
        result=v.render_check(row,checks,image,image)
        self.assertTrue(result['passed'],result);self.assertEqual(result['depth'],'normal')

    def test_source_colour_ambiguity_is_invalid(self):
        row,checks=geometry(source_line());image=np.ones((120,200,3))
        result=v.render_check(row,checks,image,image)
        self.assertFalse(result['passed']);self.assertFalse(result['valid'])

    def test_required_source_line_cannot_be_unmeasured(self):
        state={'verification_policy':c.POLICY}
        with self.assertRaisesRegex(ValueError,'LINE_SOURCE_REQUIRED'):
            c.validate_source({'features':[{'id':'line','kind':'internal_line'}]},state)

    def test_bent_connector_qualifies_its_actual_corner_capability(self):
        from core.component_source_features import _capabilities
        caps=_capabilities([{'render_type':'connector','content':{'points':[[0,0],[40,0],[40,20]]},'style':{}}])
        self.assertIn('corners',caps)
        self.assertNotIn('corners',_capabilities([{'render_type':'connector','content':{'points':[[0,0],[40,0]]},'style':{}}]))

    def test_invalid_proposal_cache_depends_on_actual_component_implementation(self):
        import test_workflow_v137 as previous
        from core.retry_context import checked_submit
        fixture=previous.Protocol();fixture.setUp();self.addCleanup(fixture.doCleanups)
        calls=[]
        @checked_submit
        def reject(task,result):
            calls.append(result);raise ValueError('located validation failure')
        with patch('core.component_workflow.implementation',return_value='implementation-A'):
            with self.assertRaisesRegex(ValueError,'located validation'):reject(fixture.task,{'packet_id':'p','proposal':'same'})
            with self.assertRaisesRegex(ValueError,'identical invalid proposal retained'):reject(fixture.task,{'packet_id':'new-p','proposal':'same'})
        self.assertEqual(len(calls),1)
        with patch('core.component_workflow.implementation',return_value='implementation-B'):
            with self.assertRaisesRegex(ValueError,'located validation'):reject(fixture.task,{'packet_id':'current-p','proposal':'same'})
        self.assertEqual(len(calls),2)

    def test_local_template_uses_component_id_not_component_definition(self):
        import test_workflow_v137 as previous
        from core.incremental_contract import template
        from core.common import read_json
        fixture=previous.Protocol();fixture.setUp();self.addCleanup(fixture.doCleanups)
        packet={'packet_id':'local','kind':'component_local_work','target':'left','component_action':{'operation':'evaluate','component':{'id':'left','owners':['owner']}}}
        template(fixture.task,fixture.state(),packet)
        value=read_json(fixture.task/packet['submission_template']['path'])
        self.assertEqual(value['component_request']['component'],'left')

    def test_scoped_connector_repair_adopts_complete_route_frame_only(self):
        from core.native_commit import _field
        old=entry(tag='cxnSp')['node'];new=entry(tag='cxnSp')['node']
        for node,x,w in ((old,119,162),(new,120,161)):
            props=node.find('p:spPr',NS);xf=E.SubElement(props,'{'+NS['a']+'}xfrm',flipV='1')
            E.SubElement(xf,'{'+NS['a']+'}off',x=str(x),y='60');E.SubElement(xf,'{'+NS['a']+'}ext',cx=str(w),cy='120')
        new.find('p:spPr/a:ln/a:solidFill/a:srgbClr',NS).set('val','FF0000')
        _field(old,new,'connector')
        xf=old.find('p:spPr/a:xfrm',NS)
        self.assertEqual(xf.find('a:off',NS).get('x'),'120');self.assertEqual(xf.find('a:ext',NS).get('cx'),'161')
        self.assertEqual(old.find('p:spPr/a:ln/a:solidFill/a:srgbClr',NS).get('val'),'000000')

    def test_broad_declared_width_cannot_hide_thicker_render(self):
        line=source_line(((20,60),(180,60)));line['stroke']['width']=[2,12]
        row,checks=geometry(line,entry(points=[[20,60],[180,60]],matrix=[[200,0,0],[0,120,0],[0,0,1]]))
        reference=pixels(((20,60),(180,60)),width=2);actual=pixels(((20,60),(180,60)),width=10)
        result=v.render_check(row,checks,reference,actual)
        self.assertFalse(result['passed']);self.assertFalse(result['width']['paired_original']['passed'])

    def test_occluder_must_cover_hidden_interval_and_paint_after_shaft(self):
        line=source_line(((20,60),(180,60)));line['visibility']['hidden']=[{'segment':0,'range':[.3,.7],'occluder':'body','source_evidence':'Original opaque body hides this interval'}]
        native=entry(points=[[20,60],[180,60]],matrix=[[200,0,0],[0,120,0],[0,0,1]])
        body=entry(preset='rect',matrix=[[64,0,68],[0,30,45],[0,0,1]])
        E.SubElement(E.SubElement(body['node'].find('p:spPr',NS),'{'+NS['a']+'}solidFill'),'{'+NS['a']+'}srgbClr',val='FFFFFF')
        row={'id':'line','parts':[{'owner':'route','role':'shaft'}],'source':line}
        bindings={'body':{'owners':['body']}};decoded={'route':g.decode(native)}
        result=g.native_checks(row,decoded,{'route':native,'body':body},bindings,.002)
        self.assertTrue(result['visibility_native']['passed'],result['visibility_native'])
        result=g.native_checks(row,decoded,{'body':body,'route':native},bindings,.002)
        self.assertFalse(result['visibility_native']['passed'])

    def test_source_contract_rejects_unordered_geometry(self):
        line=source_line();line['path']['segments'][1]['points'][0]=[90,40]
        with self.assertRaisesRegex(ValueError,'contiguous'):c.validate_line(line,{'id':'line'},{'line':{}})

    def test_source_contract_cannot_silently_omit_marker(self):
        line=source_line();del line['ends'][1]['marker']
        with self.assertRaisesRegex(ValueError,'marker types'):c.validate_line(line,{'id':'line'},{'line':{}})

    def test_missing_compiled_gate_is_not_no_lines(self):
        with self.assertRaisesRegex(ValueError,'LINE_POLICY_REQUIRED'):
            c.require_contract({'verification_policy':c.POLICY,'source':{'sha256':'a'}},{})

    def test_lazy_generic_metrics_do_not_invoke_unrequested_producers(self):
        from core.component_metrics import arrays
        image=pixels(((20,20),(140,20)))
        with patch('skimage.metrics.structural_similarity',side_effect=AssertionError('unrequested SSIM')):
            with patch('core.typed_metrics.color_histogram',side_effect=AssertionError('unrequested histogram')):
                values,boundary=arrays(image,image,requested={'mean_absolute_rgb_error'})
        self.assertEqual(set(values),{'mean_absolute_rgb_error'});self.assertEqual(values['mean_absolute_rgb_error']['value'],0)
        self.assertFalse(boundary['applicable'])

    def test_lazy_requested_values_equal_full_producers(self):
        from core.component_metrics import arrays
        a=pixels(((20,20),(140,20)));b=pixels(((20,21),(140,21)))
        full,_=arrays(a,b)
        for keys in ({'ssim_loss'},{'color_histogram_tv'},{'boundary_distance_max'},{'clarity_ratio'}):
            selected,_=arrays(a,b,requested=keys)
            self.assertEqual(set(selected),keys)
            for key in keys:self.assertEqual(selected[key],full[key])

    def test_rotation_and_flip_are_saved_geometry(self):
        # 90 degree transform and a horizontal flip are independent matrices.
        native=entry(matrix=[[0,-70,160],[120,0,15],[0,0,1]])
        _,checks=geometry(source_line(((160,15),(160,135),(90,135))),native)
        self.assertTrue(checks['route']['passed'],checks['route'])
        native=entry(matrix=[[-120,0,160],[0,70,15],[0,0,1]])
        _,checks=geometry(source_line(((160,15),(40,15),(40,85))),native)
        self.assertTrue(checks['route']['passed'],checks['route'])

    def test_saved_missing_short_segment_fails_native_route(self):
        native=entry(points=[[20,20],[140,20]],matrix=[[200,0,0],[0,120,0],[0,0,1]])
        _,checks=geometry(source_line(),native)
        self.assertFalse(checks['route']['passed'])

    def test_wrong_target_contact_is_not_bbox_acceptance(self):
        line=source_line();line['ends'][1]['attachment']={'kind':'boundary_touch','feature':'body','distance':[0,0],'source_evidence':'Original boundary'}
        target=entry(preset='rect',matrix=[[20,0,160],[0,20,90],[0,0,1]])
        row={'id':'line','parts':[{'owner':'route','role':'shaft'}],'source':line}
        checks=g.native_checks(row,{'route':g.decode(entry())},{'route':entry(),'target':target},{'body':{'owners':['target']}},.002)
        self.assertFalse(checks['terminals']['passed'])

    def test_extra_native_intersection_is_not_a_source_junction(self):
        a={'id':'a','source':source_line(((0,20),(100,20)))};b={'id':'b','source':source_line(((0,23),(100,23)))}
        from shapely.geometry import LineString
        geometries={'a':{'expected':np.array([[0,20],[100,20]]),'paths':[LineString([[0,20],[100,20]])]},
                    'b':{'expected':np.array([[0,23],[100,23]]),'paths':[LineString([[50,10],[50,30]])]}}
        results=v.topology_checks([a,b],geometries,{})
        self.assertFalse(results['a']['passed']);self.assertFalse(results['b']['passed'])

    def test_source_crossing_requires_semantic_record(self):
        from shapely.geometry import LineString
        a={'id':'a','source':source_line(((0,20),(100,20)))};b={'id':'b','source':source_line(((50,0),(50,40)))}
        geometries={r['id']:{'expected':np.asarray([s['points'][0] for s in r['source']['path']['segments']]+[r['source']['path']['segments'][-1]['points'][-1]]),
            'paths':[LineString(r['source']['path']['segments'][0]['points'])]} for r in (a,b)}
        self.assertFalse(v.topology_checks([a,b],geometries,{})['a']['passed'])
        record={'id':'cross','point':[50,20],'features':['a','b'],'kind':'crossing','source_evidence':'Original crossing, no junction'}
        a['source']['topology']['crossings']=[record];b['source']['topology']['crossings']=[copy.deepcopy(record)]
        self.assertTrue(v.topology_checks([a,b],geometries,{})['a']['passed'])

    def test_legacy_policy_is_not_relabelled(self):
        self.assertFalse(c.enabled({}));contract={}
        c.compile_contract({}, {},contract,{})
        self.assertEqual(contract,{})

    def test_unbound_native_line_is_rejected_at_binding(self):
        state={'verification_policy':c.POLICY,'source':{'sha256':'s'}}
        with self.assertRaisesRegex(ValueError,'no source line'):
            c.compile_contract(state,{'features':[]},{'feature_bindings':[]},{'objects':[{'id':'unbound','render_type':'connector','content':{}}]})

    def test_required_report_rejects_missing_criterion_or_line(self):
        state={'verification_policy':c.POLICY,'source':{'sha256':'s'}}
        line=source_line();feature={'id':'f','unit':'u','roi':[0,0,200,120],'kind':'internal_line','line':line}
        contract={'feature_bindings':[{'feature':'f','component':'u','owners':['route']}]}
        c.compile_contract(state,{'features':[feature]},contract,{'objects':[{'id':'route','render_type':'connector','content':{}}]})
        candidate={'pptx':{'sha256':'p'},'preview':{'sha256':'r'}}
        report={'policy':c.POLICY,'basis':contract['line_verification']['basis'],'passed':True,'source_hash':'s','pptx_hash':'p','preview_hash':'r',
                'render_checked':True,'census':{'passed':True},'lines':{'f':{'passed':True,'valid':True,'checks':{key:g.result(True) for key in c.CRITERIA}}}}
        c.require_report(state,candidate,contract,report)
        bad=copy.deepcopy(report);bad['lines']={}
        with self.assertRaisesRegex(ValueError,'LINE_REPORT_REQUIRED'):c.require_report(state,candidate,contract,bad)
        bad=copy.deepcopy(report);del bad['lines']['f']['checks']['markers']
        with self.assertRaisesRegex(ValueError,'LINE_REPORT_REQUIRED'):c.require_report(state,candidate,contract,bad)

    def test_exact_cubic_curve_and_terminal_tangents(self):
        controls=[[20,20],[70,0],[100,110],[140,90]]
        native=entry(points=[[20,20],[140,90]],matrix=[[200,0,0],[0,120,0],[0,0,1]])
        path=native['node'].find('p:spPr/a:custGeom/a:pathLst/a:path',NS);path.remove(path[-1])
        op=E.SubElement(path,'{'+NS['a']+'}cubicBezTo')
        for p in controls[1:]:E.SubElement(op,'{'+NS['a']+'}pt',x=str(p[0]),y=str(p[1]))
        line=source_line(((20,20),(140,90)));line['path']={'kind':'curve','segments':[{'kind':'cubic','points':controls}]}
        _,checks=geometry(line,native)
        self.assertTrue(checks['route']['passed'],checks['route']);self.assertTrue(checks['terminals']['passed'])

    def test_ellipse_arc_is_independently_bounded(self):
        line=source_line(ends=[]);line['path']={'kind':'closed','segments':[{'kind':'arc','center':[80,55],'radii':[60,35],'start_degrees':0,'sweep_degrees':360}]}
        _,checks=geometry(line,entry(preset='ellipse'))
        self.assertTrue(checks['route']['passed'],checks['route'])

    def test_filled_freeform_arrow_checks_complete_body(self):
        outline=[[20,45],[110,45],[110,35],[140,55],[110,75],[110,65],[20,65]]
        native=entry(points=outline,matrix=[[200,0,0],[0,120,0],[0,0,1]])
        props=native['node'].find('p:spPr',NS);path=props.find('a:custGeom/a:pathLst/a:path',NS);E.SubElement(path,'{'+NS['a']+'}close')
        E.SubElement(E.SubElement(props,'{'+NS['a']+'}solidFill'),'{'+NS['a']+'}srgbClr',val='000000')
        sites={'start':{'edge':6,'fraction':.5},'end':{'vertex':3}}
        line=source_line(((20,55),(140,55)));line['path'].update(kind='filled_arrow',outline=outline)
        line['stroke']['width']=[20,40]
        row={'id':'line','parts':[{'owner':'route','role':'shaft'}],'source':line}
        actual=g.decode(native,terminal_sites=sites)
        checks=g.native_checks(row,{'route':actual},{'route':native},{},.002)
        self.assertTrue(checks['route']['passed'],checks['route']);self.assertTrue(checks['stroke']['passed'])
        bad=copy.deepcopy(line);bad['path']['outline'][2]=[80,0];row['source']=bad
        self.assertFalse(g.native_checks(row,{'route':actual},{'route':native},{},.002)['route']['passed'])

    def test_dash_phase_matches_original_without_solid_gap_failure(self):
        line=source_line(((20,60),(180,60)));line['stroke']['dash']={'kind':'dash','pattern':[[6,10],[4,8]]}
        native=entry(points=[[20,60],[180,60]],matrix=[[200,0,0],[0,120,0],[0,0,1]])
        ln=native['node'].find('p:spPr/a:ln',NS);E.SubElement(ln,'{'+NS['a']+'}prstDash',val='dash')
        row,checks=geometry(line,native)
        image=Image.new('RGB',(200,120),'white');d=ImageDraw.Draw(image)
        for x in range(20,180,14):d.line((x,60,min(x+7,180),60),fill='black',width=2)
        pixels=np.asarray(image,float)/255
        self.assertTrue(v.render_check(row,checks,pixels,pixels)['passed'])

    def test_compound_style_and_render_bands_are_distinct(self):
        line=source_line(((20,60),(180,60)));line['stroke'].update(width=[6,6],compound='double')
        native=entry(points=[[20,60],[180,60]],matrix=[[200,0,0],[0,120,0],[0,0,1]])
        ln=native['node'].find('p:spPr/a:ln',NS);ln.set('cmpd','dbl');ln.set('w',str(6*12700))
        row,checks=geometry(line,native);self.assertTrue(checks['stroke']['passed'])
        image=Image.new('RGB',(200,120),'white');d=ImageDraw.Draw(image)
        d.line((20,58,180,58),fill='black',width=2);d.line((20,62,180,62),fill='black',width=2)
        image=np.asarray(image,float)/255
        self.assertTrue(v.render_check(row,checks,image,image)['passed'])
        solid=pixels(((20,60),(180,60)),width=6)
        self.assertFalse(v.render_check(row,checks,image,solid)['passed'])


class LocatedReview(unittest.TestCase):
    def setUp(self):
        from core import line_review as r
        from core.common import write_json,digest
        self.r=r;self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.root.joinpath('saved.pptx').write_bytes(b'owned test bytes, not an actual render acceptance')
        image=Image.fromarray((pixels(((20,20),(140,20),(140,90)))*255).astype('uint8'))
        image.save(self.root/'source.png');image.save(self.root/'preview.png')
        self.state={'verification_policy':c.POLICY,'source':{'path':'source.png','sha256':digest(self.root/'source.png')},'source_size':[200,120],
            'capabilities':{'fingerprint':'owned-unit-fixture'}}
        self.candidate={'pptx':{'path':'saved.pptx','sha256':digest(self.root/'saved.pptx')},'preview':{'path':'preview.png','sha256':digest(self.root/'preview.png')}}
        self.contract={'feature_bindings':[{'feature':'f','component':'u','owners':['route']}]}
        feature={'id':'f','unit':'u','roi':[10,10,150,90],'kind':'internal_line','line':source_line()}
        c.compile_contract(self.state,{'features':[feature]},self.contract,{'objects':[{'id':'route','render_type':'connector','content':{}}]})
        self.report={'policy':c.POLICY,'basis':self.contract['line_verification']['basis'],'passed':True,'source_hash':self.state['source']['sha256'],
            'pptx_hash':self.candidate['pptx']['sha256'],'preview_hash':self.candidate['preview']['sha256'],'render_checked':True,
            'census':{'passed':True},'lines':{'f':{'passed':True,'valid':True,'checks':{key:g.result(True) for key in c.CRITERIA}}}}

    def prepared(self,ledger=None):
        from core.common import read_json
        with patch('core.line_verification.evaluate',return_value=self.report),patch('core.boundary_geometry.saved_nodes',return_value={}):
            prepared=self.r.prepare(self.root,self.state,self.candidate,self.contract,ledger or {})
        return prepared,read_json(self.root/prepared['manifest']['path'])

    def evidence(self,prepared,manifest):
        return {'line_review':{'manifest':prepared['manifest'],'lines':[{'line':'f','criteria':{key:'PASS' for key in c.CRITERIA},
            'evidence_refs':[ref for target in manifest['targets'] for view in target['views'] for ref in view['evidence'].values()]}],
            'issues':[],'resolutions':[]}}

    def test_clear_hash_bound_review_passes(self):
        p,m=self.prepared();proof=self.evidence(p,m)
        self.assertTrue(self.r.validate(self.root,self.state,self.candidate,self.contract,{},proof)['passed'])

    def test_missing_review_does_not_pass(self):
        self.assertFalse(self.r.validate(self.root,self.state,self.candidate,self.contract,{}, {})['passed'])

    def test_crop_bytes_changed_is_rejected(self):
        p,m=self.prepared();proof=self.evidence(p,m)
        file=self.root/m['targets'][0]['views'][0]['evidence']['source']['path'];file.write_bytes(file.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'crop bytes changed'):self.r.validate(self.root,self.state,self.candidate,self.contract,{},proof)

    def test_omitted_render_crop_is_rejected(self):
        p,m=self.prepared();proof=self.evidence(p,m);proof['line_review']['lines'][0]['evidence_refs'].pop()
        with self.assertRaisesRegex(ValueError,'views must be accounted'):self.r.validate(self.root,self.state,self.candidate,self.contract,{},proof)

    def test_nonpass_creates_persistent_doubt_without_free_text(self):
        p,m=self.prepared();proof=self.evidence(p,m);proof['line_review']['lines'][0]['criteria']['route']='UNRESOLVED'
        first=self.r.validate(self.root,self.state,self.candidate,self.contract,{},proof)
        self.assertFalse(first['passed']);self.assertTrue(first['open_issues'])
        proof['line_review']['lines'][0]['criteria']['route']='PASS'
        second=self.r.validate(self.root,self.state,self.candidate,self.contract,{'line_issues':first['issues']},proof)
        self.assertFalse(second['passed']);self.assertEqual(first['open_issues'],second['open_issues'])

    def test_prepared_program_doubt_survives_new_measurement_before_observation(self):
        self.report['passed']=False;self.report['lines']['f']['checks']['visibility']=g.invalid('original crop precision')
        p,m=self.prepared();ledger={}
        self.assertTrue(self.r.retain_prepared_issues(self.root,p,ledger))
        self.report['passed']=True;self.report['lines']['f']['checks']['visibility']=g.result(True)
        p,m=self.prepared(ledger)
        self.assertTrue(any(v['kind'].startswith('issue:program:f:visibility') for v in m['targets'][0]['views']))
        self.assertFalse(self.r.validate(self.root,self.state,self.candidate,self.contract,ledger,self.evidence(p,m))['passed'])

    def test_changed_evidence_reopens_old_resolution_and_preserves_history(self):
        old_binding=self.r.binding(self.state,self.candidate,self.contract)
        issue={'id':'visual:old-marker','line':'f','criterion':'markers','state':'RESOLVED',
            'roi':[130,75,15,20],'resolved_binding':old_binding,
            'resolution':{'kind':'measurement','observations':'Previous actual detail pair'},'current_check':'prior-check'}
        ledger={'line_issues':{issue['id']:copy.deepcopy(issue)}}
        self.candidate['render']={'path':'new-render.json','sha256':'new-actual-render-receipt'}
        p,m=self.prepared(ledger)
        reopened=next(v for v in m['issues'] if v['id']==issue['id'])
        self.assertEqual(reopened['state'],'OPEN');self.assertEqual(reopened['prior_resolutions'][0]['resolution'],issue['resolution'])
        self.assertTrue(any(v['kind'].startswith('issue:'+issue['id']) for v in m['targets'][0]['views']))
        self.assertFalse(self.r.validate(self.root,self.state,self.candidate,self.contract,ledger,self.evidence(p,m))['passed'])
        self.r.retain_prepared_issues(self.root,p,ledger)
        self.assertFalse(self.r.validate(self.root,self.state,self.candidate,self.contract,ledger,self.evidence(p,m))['passed'])

    def test_visual_fail_is_located_repair_and_unresolved_is_not_failure(self):
        p,m=self.prepared();proof=self.evidence(p,m)
        proof['line_review']['lines'][0]['criteria']['route']='FAIL'
        self.assertTrue(self.r.validate(self.root,self.state,self.candidate,self.contract,{},proof)['visual_failure'])
        proof['line_review']['lines'][0]['criteria']['route']='UNRESOLVED'
        self.assertFalse(self.r.validate(self.root,self.state,self.candidate,self.contract,{},proof)['visual_failure'])

    def test_explicit_enlarged_resolution_and_idempotent_final_check(self):
        p,m=self.prepared();proof=self.evidence(p,m);proof['line_review']['lines'][0]['criteria']['route']='UNRESOLVED'
        first=self.r.validate(self.root,self.state,self.candidate,self.contract,{},proof);ledger={'line_issues':first['issues']}
        p,m=self.prepared(ledger);proof=self.evidence(p,m);issue=first['open_issues'][0]
        refs=[ref for view in m['targets'][0]['views'] if view['kind'].startswith('issue:'+issue) for ref in view['evidence'].values()]
        self.assertTrue(refs)
        proof['line_review']['resolutions']=[{'issue':issue,'kind':'false_positive','observations':'Owned test explicitly inspects the current detail pair','evidence_refs':refs}]
        resolved=self.r.validate(self.root,self.state,self.candidate,self.contract,ledger,proof)
        self.assertTrue(resolved['passed'],resolved)
        repeat=self.r.validate(self.root,self.state,self.candidate,self.contract,{'line_issues':resolved['issues']},proof,report=self.report)
        self.assertTrue(repeat['passed'],repeat)

    def test_text_cannot_waive_program_failure(self):
        self.report['passed']=False;self.report['lines']['f']['checks']['route']=g.result(False)
        p,m=self.prepared();proof=self.evidence(p,m)
        result=self.r.validate(self.root,self.state,self.candidate,self.contract,{},proof)
        self.assertFalse(result['passed']);self.assertTrue(result['program_failure'])

    def test_new_pptx_hash_makes_review_stale(self):
        p,m=self.prepared();proof=self.evidence(p,m);self.candidate['pptx']['sha256']='other-current-bytes'
        with self.assertRaisesRegex(ValueError,'stale or changed'):self.r.validate(self.root,self.state,self.candidate,self.contract,{},proof)

    def test_stale_accepted_visual_returns_review_readiness_not_exception(self):
        from core import component_final as final
        from core.common import write_json,digest
        value={'source_hash':self.state['source']['sha256'],'pptx_hash':self.candidate['pptx']['sha256'],
            'preview_hash':self.candidate['preview']['sha256'],'observer':'host_model',
            'dimensions':{k:{'passed':True,'observations':'Owned current fixture'} for k in final.DIMENSIONS}}
        file=self.root/'old-review.json';write_json(file,value)
        issues={'known':{'id':'known','state':'OPEN'}}
        ledger={'final_visual':{'path':'old-review.json','sha256':digest(file)},'line_issues':issues}
        with patch('core.component_workflow._load',return_value=(self.contract,ledger)),patch('core.component_source_features.final_review',return_value={'passed':True}),patch('core.spatial_frames.review',return_value={'passed':True}),patch('core.line_review.validate',side_effect=ValueError('LINE_REVIEW_REQUIRED: stale or changed manifest')):
            result=final._visual(self.root,self.state,self.candidate,ledger)
        self.assertFalse(result['passed']);self.assertTrue(result['line_review']['review_required'])
        self.assertEqual(result['line_review']['issues'],issues);self.assertEqual(ledger['line_issues'],issues)

    def executable(self):
        from zipfile import ZipFile
        from core.common import write_json,digest
        with ZipFile(self.root/'saved.pptx','w') as z:z.writestr('owned.xml','<fixture/>')
        self.candidate['pptx']['sha256']=digest(self.root/'saved.pptx')
        write_json(self.root/'scene.json',{'objects':[{'id':'route','render_type':'connector','content':{'points':[[20,20],[140,20],[140,90]]}}]})
        self.candidate['scene']={'path':'scene.json','sha256':digest(self.root/'scene.json')}

    def measured(self):
        with patch('core.boundary_geometry.saved_nodes',return_value={'route':entry()}),patch('core.component_workflow.actual_render'):
            return v.evaluate(self.root,self.state,self.candidate,self.contract)

    def test_sufficient_normal_evidence_does_not_run_deep_producer(self):
        self.executable()
        with patch('core.line_verification.render_check',wraps=v.render_check) as producer:
            result=self.measured()
        self.assertTrue(result['passed'],result)
        self.assertEqual(result['method_counts'],{'normal':1,'deep':0});self.assertEqual(producer.call_count,1)

    def test_valid_fail_cannot_be_replaced_by_refinement(self):
        self.executable()
        with patch('core.line_verification.render_check',return_value={**g.result(False),'method':'normal_line_pixels'}) as producer:
            result=self.measured()
        self.assertFalse(result['passed']);self.assertEqual(producer.call_count,1)
        self.assertEqual(result['method_counts']['deep'],0)

    def test_only_inconclusive_measurement_selects_refinement(self):
        self.executable()
        with patch('core.line_verification.render_check',side_effect=[g.invalid('precise local support needed'),{**g.result(True),'method':'refined_line_pixels'}]) as producer:
            result=self.measured()
        self.assertTrue(result['passed'],result);self.assertEqual(producer.call_count,2)
        self.assertTrue(producer.call_args.kwargs['deep'])

    def test_valid_leaf_failure_prevents_refinement_of_mixed_invalid_result(self):
        self.executable()
        value={'passed':False,'valid':False,'method':'normal_line_pixels','items':[g.result(False),g.invalid('uncertain elsewhere')]}
        with patch('core.line_verification.render_check',return_value=value) as producer:result=self.measured()
        self.assertFalse(result['passed']);self.assertEqual(producer.call_count,1)

    def test_pixel_bound_can_request_real_higher_resolution(self):
        check=g.bounded(2.13,.884,3,method='current_marker_paint_both_directions')
        report=copy.deepcopy(self.report);report['lines']['f']['checks']['visibility']=check
        action=self.r.precision_request(self.state,self.candidate,report,1600,[])
        self.assertEqual(action['target_width'],3200)
        self.assertEqual(action['pptx'],self.candidate['pptx']['sha256'])
        self.assertIsNone(self.r.precision_request(self.state,self.candidate,report,1600,[action,action]))

    def test_irreducible_source_error_and_valid_fail_do_not_rerender(self):
        report=copy.deepcopy(self.report)
        report['lines']['f']['checks']['visibility']=g.bounded(2.6,.884,3,method='current_marker_paint_both_directions')
        self.assertIsNone(self.r.precision_request(self.state,self.candidate,report,1600,[]))
        report['lines']['f']['checks']['visibility']={'passed':False,'valid':False,'items':[g.result(False),g.bounded(2.13,.884,3,method='current_marker_paint_both_directions')]}
        self.assertIsNone(self.r.precision_request(self.state,self.candidate,report,1600,[]))

    def test_clear_program_evidence_has_no_render_precision_request(self):
        self.assertIsNone(self.r.precision_request(self.state,self.candidate,self.report,1600,[]))

    def test_zero_line_applicability_cannot_drop_an_existing_open_question(self):
        issue={'id':'retained-source-question','line':'previous-line','criterion':'route','state':'OPEN'}
        with patch('core.line_review.require_contract',return_value={'lines':[],'basis':'explicit-zero-line-fixture'}):
            result=self.r.validate(self.root,self.state,self.candidate,self.contract,{'line_issues':{issue['id']:issue}}, {})
        self.assertFalse(result['passed']);self.assertEqual(result['issues'][issue['id']]['state'],'OPEN')

if __name__=='__main__':unittest.main()
