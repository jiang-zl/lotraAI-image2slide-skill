"""Saved separate marker paint owns its envelope, independently of shaft width."""
import copy,sys,unittest
from pathlib import Path
import numpy as np
from lxml import etree as E
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/lotra-image2slide-skill/scripts'))
from core import line_geometry as g,line_verification as v
from core.mathml import NS
from test_line_evidence_v1372 import source_line,entry


class MarkerOwner(unittest.TestCase):
    def fixture(self,width=12,offset=0,stroke=False,effect=False):
        source=source_line();source['ends'][1]['marker'].update(type='triangle',filled=True,width=[12,12],length=[12,12])
        shaft=entry(points=[[20,20],[140,20],[140,90]],matrix=[[200,0,0],[0,120,0],[0,0,1]])
        marker=entry(preset='triangle',matrix=[[width,0,140-width/2+offset],[0,-width,90],[0,0,1]])
        props=marker['node'].find('p:spPr',NS)
        E.SubElement(E.SubElement(props,'{'+NS['a']+'}solidFill'),'{'+NS['a']+'}srgbClr',val='000000')
        if not stroke:
            props.remove(props.find('a:ln',NS));E.SubElement(E.SubElement(props,'{'+NS['a']+'}ln'),'{'+NS['a']+'}noFill')
        if effect:E.SubElement(E.SubElement(props,'{'+NS['a']+'}effectLst'),'{'+NS['a']+'}outerShdw')
        row={'id':'line','source':source,'parts':[{'owner':'shaft','role':'shaft'},{'owner':'marker','role':'end_marker'}]}
        geometry=g.native_checks(row,{'shaft':g.decode(shaft)},{'shaft':shaft,'marker':marker},{},.002)
        return row,geometry,marker

    def images(self,width=12,offset=0,remote=True,near=False,hollow=False):
        images=[]
        for actual in (False,True):
            image=Image.new('RGB',(220,180),'white');draw=ImageDraw.Draw(image)
            draw.line([(20,20),(140,20),(140,90)],fill='black',width=2)
            size=width if actual else 12;dx=offset if actual else 0
            points=[(140+dx,90),(140-size/2+dx,90-size),(140+size/2+dx,90-size)]
            draw.polygon(points,fill='white' if hollow and actual else 'black',outline='black')
            if remote:draw.rectangle([140+(8 if actual else 0),130,143+(8 if actual else 0),142],fill='black')
            if near:draw.rectangle([151+(7 if actual else 0),96,153+(7 if actual else 0),99],fill='black')
            images.append(np.asarray(image,float)/255)
        return images

    def test_native_owner_extent_does_not_use_shaft_multiplier(self):
        row,geometry,_=self.fixture();extent=geometry['marker_paint_extents']['1']
        self.assertEqual(extent['owner'],'marker');self.assertEqual(extent['radius_from_source_anchor'],12)
        self.assertEqual(extent['bounds'],[134,78,146,90])

    def test_unrelated_remote_glyph_is_not_terminal_ownership(self):
        row,geometry,_=self.fixture();images=self.images()
        previous=copy.deepcopy(geometry);previous.pop('marker_paint_extents')
        old=v.marker_pixels(row,*images,previous,deep=True)
        self.assertTrue(old['valid']);self.assertFalse(old['passed'])
        old_copy=copy.deepcopy(old)
        current=v.marker_pixels(row,*images,geometry,deep=True)
        self.assertTrue(current['passed'],current);self.assertEqual(old,old_copy)
        self.assertEqual(current['items'][1]['crop_basis']['method'],'separate_saved_native_marker_paint')

    def test_local_contact_paint_difference_still_fails(self):
        row,geometry,_=self.fixture()
        result=v.marker_pixels(row,*self.images(remote=False,near=True),geometry,deep=True)
        self.assertTrue(result['valid']);self.assertFalse(result['passed'],result)

    def test_enlarged_actual_marker_cannot_be_cropped_to_source_extent(self):
        row,geometry,_=self.fixture(width=70)
        self.assertFalse(geometry['markers']['passed'])
        result=v.marker_pixels(row,*self.images(width=70,remote=False),geometry,deep=True)
        self.assertTrue(result['valid']);self.assertFalse(result['passed'])
        self.assertGreater(result['items'][1]['roi'][2],100)

    def test_translated_actual_marker_remains_in_full_comparison(self):
        row,geometry,_=self.fixture(offset=25)
        self.assertFalse(geometry['markers']['passed'])
        result=v.marker_pixels(row,*self.images(offset=25,remote=False),geometry,deep=True)
        self.assertTrue(result['valid']);self.assertFalse(result['passed'])

    def test_filled_interior_is_still_measured_both_directions(self):
        row,geometry,_=self.fixture()
        row['source']['limits']['marker']=1.5
        result=v.marker_pixels(row,*self.images(remote=False,hollow=True),geometry,deep=True)
        self.assertFalse(result['passed'],result)

    def test_painted_outline_keeps_conservative_producer(self):
        _,geometry,_=self.fixture(stroke=True)
        self.assertNotIn('1',geometry['marker_paint_extents'])

    def test_effect_paint_keeps_conservative_producer(self):
        _,geometry,_=self.fixture(effect=True)
        self.assertNotIn('1',geometry['marker_paint_extents'])

    def test_inherited_or_translucent_fill_is_not_exact_opaque_extent(self):
        _,geometry,marker=self.fixture()
        rgb=marker['node'].find('p:spPr/a:solidFill/a:srgbClr',NS)
        E.SubElement(rgb,'{'+NS['a']+'}alpha',val='50000')
        self.assertIsNone(g.separate_marker_paint_extent(marker,[[134,78],[146,78],[140,90]],[140,90]))

    def test_theme_effect_or_adjusted_preset_needs_qualified_extent(self):
        _,_,marker=self.fixture()
        E.SubElement(E.SubElement(marker['node'],'{'+NS['p']+'}style'),'{'+NS['a']+'}effectRef',idx='2')
        self.assertIsNone(g.separate_marker_paint_extent(marker,[[134,78],[146,78],[140,90]],[140,90]))

    def test_unknown_saved_adjustment_does_not_narrow_envelope(self):
        _,_,marker=self.fixture()
        E.SubElement(marker['node'].find('p:spPr/a:prstGeom/a:avLst',NS),'{'+NS['a']+'}gd',name='adj',fmla='val 40000')
        self.assertIsNone(g.separate_marker_paint_extent(marker,[[134,78],[146,78],[140,90]],[140,90]))

    def test_geometry_for_another_owner_cannot_authorize_smaller_crop(self):
        row,geometry,_=self.fixture();geometry['marker_paint_extents']['1']['owner']='unrelated'
        result=v.marker_pixels(row,*self.images(),geometry,deep=True)
        self.assertFalse(result['passed']);self.assertEqual(result['items'][1]['crop_basis']['method'],'conservative_native_ending_envelope')


if __name__=='__main__':unittest.main()
