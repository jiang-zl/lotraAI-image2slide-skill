"""Independent fixed-raster counterexamples for finite line refinement."""
import sys,unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/lotra-image2slide-skill/scripts'))
from core import line_verification as v
from test_line_evidence_v1372 import source_line,geometry,entry


class RasterRefinement(unittest.TestCase):
    def masks(self,actual_width=4):
        source=np.zeros((120,200),bool);source[59:62,20:181]=True
        actual=np.zeros((192,320),bool);actual[94:94+actual_width,32:290]=True
        return source,actual

    def chord(self,a,b,**changes):
        args=dict(points=[[60,60],[120,60]],tangents=[[1,0],[1,0]],
            origins=((0,0),(0,0)),pixel_sizes=((1,1),(Fraction(5,8),Fraction(5,8))),
            width_limit=6,tolerance=.5,wanted=1)
        args.update(changes)
        return v.axis_cell_width_bound(a,b,**args)

    def test_exact_boundary_has_no_half_source_pixel_floor(self):
        result=self.chord(*self.masks())
        self.assertTrue(result['passed'],result)
        self.assertTrue(result['valid']);self.assertEqual(result['exact_difference'],[1,2])
        self.assertEqual(result['numeric_error'],0)
        self.assertEqual(result['source_widths'],[3,3]);self.assertEqual(result['actual_widths'],[2.5,2.5])

    def test_true_overwidth_remains_valid_failure(self):
        result=self.chord(*self.masks(actual_width=7))
        self.assertTrue(result['valid']);self.assertFalse(result['passed'],result)
        self.assertGreater(result['lower'],.5)

    def test_vertical_chords_use_actual_cell_height(self):
        a,b=self.masks()
        result=self.chord(a.T,b.T,points=[[60,60],[60,120]],tangents=[[0,-1],[0,1]])
        self.assertTrue(result['passed'],result)

    def test_closed_boundary_includes_both_adjacent_cells(self):
        a,b=self.masks();a[:,60]=False;b[:,96]=False
        self.assertTrue(self.chord(a,b)['passed'])

    def test_missing_sites_cannot_be_zipped_by_equal_counts(self):
        a,b=self.masks();a[:,59:61]=False;b[:,191:193]=False
        result=self.chord(a,b)
        self.assertFalse(result['valid']);self.assertIn('absent',result['reason'])

    def test_oblique_or_incomplete_chords_require_another_measurement(self):
        a,b=self.masks()
        result=self.chord(a,b,tangents=[[1,.000000001],[1,0]])
        self.assertFalse(result['valid']);self.assertIn('axis-aligned',result['reason'])
        result=self.chord(a,b,points=[[1,1]],tangents=[[1,0]])
        self.assertFalse(result['valid']);self.assertIn('absent',result['reason'])

    def test_fixed_crop_can_bound_chord_with_empty_guard_cells(self):
        a,b=self.masks()
        result=self.chord(a[56:65],b[90:104],origins=((0,56),(0,Fraction(225,4))))
        self.assertTrue(result['passed'],result)
        self.assertEqual(result['exact_difference'],[1,2])

    def test_painted_clipped_crop_edge_remains_invalid(self):
        a,b=self.masks()
        result=self.chord(a[59:62],b,origins=((0,59),(0,0)))
        self.assertFalse(result['valid']);self.assertIn('boundary',result['reason'])

    def test_wrong_actual_compound_bands_fail(self):
        a,b=self.masks();b[95:97,:]=False
        result=self.chord(a,b)
        self.assertTrue(result['valid']);self.assertFalse(result['passed'])
        self.assertIn('band count',result['reason'])

    def test_unknown_source_compound_bands_stay_invalid(self):
        result=self.chord(*self.masks(),wanted=2)
        self.assertFalse(result['valid']);self.assertIn('Original',result['reason'])

    def test_finite_chord_site_budget_is_explicit(self):
        result=self.chord(*self.masks(),points=[[60,60]]*257,tangents=[[1,0]]*257)
        self.assertFalse(result['valid']);self.assertIn('budget',result['reason'])

    def test_one_way_coverage_does_not_claim_two_way_marker_equivalence(self):
        a=np.ones((2,2),bool);b=np.ones((2,8),bool)
        one=v.paint_cell_bound(a,b,((0,0),(0,0)),((1,1),(1,1)),.5,bidirectional=False)
        both=v.paint_cell_bound(a,b,((0,0),(0,0)),((1,1),(1,1)),.5)
        self.assertTrue(one['passed'],one);self.assertEqual(one['directions'],'original_to_render')
        self.assertTrue(both['valid']);self.assertFalse(both['passed'])

    def test_missing_branch_cells_remain_valid_coverage_failure(self):
        a=np.zeros((20,20),bool);a[2:4,2:18]=True;a[2:16,16:18]=True
        b=a.copy();b[5:,:]=False
        result=v.paint_cell_bound(a,b,((0,0),(0,0)),((1,1),(1,1)),1.5,bidirectional=False)
        self.assertTrue(result['valid']);self.assertFalse(result['passed']);self.assertGreater(result['lower'],8)

    def fixture(self,actual_width=4):
        a,b=self.masks(actual_width);original=np.ones((*a.shape,3));actual=np.ones((*b.shape,3))
        original[a]=0;actual[b]=0
        line=source_line(((20,60),(180,60)));line['stroke']['width']=[3,3]
        line['limits'].update(width=.5,route=1.5)
        row,checks=geometry(line,entry(points=[[20,60],[180,60]],matrix=[[200,0,0],[0,120,0],[0,0,1]]))
        return row,checks,original,actual

    def test_render_producer_refines_same_cells_and_keeps_coarse_records(self):
        result=v.render_check(*self.fixture())
        paired=result['width']['paired_original']
        self.assertTrue(paired['passed'],paired);self.assertFalse(paired['prior_inconclusive']['valid'])
        self.assertTrue(result['passed'],result)
        self.assertEqual(result['source_alignment'],'fixed_no_candidate_alignment')

    def test_valid_coarse_failure_never_calls_width_fallback(self):
        with patch.object(v,'axis_cell_width_bound',side_effect=AssertionError('valid FAIL replaced')):
            result=v.render_check(*self.fixture(actual_width=12))
        self.assertTrue(result['width']['paired_original']['valid'])
        self.assertFalse(result['width']['paired_original']['passed'])

    def test_other_valid_failure_survives_local_width_refinement(self):
        marker={'valid':True,'passed':False,'status':'FAIL','reason':'independently wrong marker'}
        with patch.object(v,'marker_pixels',return_value=marker):result=v.render_check(*self.fixture())
        self.assertTrue(result['width']['paired_original']['passed'])
        self.assertFalse(result['passed']);self.assertTrue(v.has_valid_failure(result))


if __name__=='__main__':unittest.main()
