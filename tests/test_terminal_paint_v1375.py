"""Native line-ending paint must not borrow disconnected nearby text."""
from pathlib import Path
import sys
import unittest
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/lotra-image2slide-skill/scripts'))
from core import line_geometry as g,line_verification as v
from test_line_evidence_v1372 import source_line,entry


class NativeTerminalPaint(unittest.TestCase):
    def geometry(self):
        source=source_line(((80,20),(80,80)))
        source['ends'][1]['marker'].update(type='triangle',filled=True,width=[12,12],length=[12,12])
        native=entry(points=[[80,20],[80,80]],marker='triangle',matrix=[[200,0,0],[0,120,0],[0,0,1]])
        row={'id':'line','parts':[{'owner':'route','role':'shaft'}],'source':source}
        geometry=g.native_checks(row,{'route':g.decode(native)},{'route':native},{},.002)
        return row,geometry

    def pixels(self,*,glyph_shift=0,head=True,width=12,offset=0,hollow=False):
        image=Image.new('RGB',(220,180),'white');draw=ImageDraw.Draw(image)
        draw.line([(80,20),(80,80)],fill='black',width=2)
        if head:
            draw.polygon([(80+offset,80),(80-width/2+offset,80-width),(80+width/2+offset,80-width)],
                         fill='white' if hollow else 'black',outline='black')
        draw.rectangle([110+glyph_shift,90,113+glyph_shift,110],fill='black')
        return np.asarray(image,float)/255

    def test_changed_remote_glyph_does_not_change_marker_measurement(self):
        row,geometry=self.geometry();original=self.pixels()
        unchanged=v.marker_pixels(row,original,self.pixels(),geometry,deep=True)
        changed=v.marker_pixels(row,original,self.pixels(glyph_shift=20),geometry,deep=True)
        self.assertTrue(unchanged['passed'],unchanged)
        self.assertTrue(changed['passed'],changed)
        self.assertEqual(unchanged['items'][1]['value'],changed['items'][1]['value'])
        self.assertGreater(changed['items'][1]['ownership']['render']['disconnected_pixels_excluded'],0)

    def test_missing_head_cannot_borrow_shaft_or_glyph(self):
        row,geometry=self.geometry()
        self.assertFalse(v.marker_pixels(row,self.pixels(),self.pixels(head=False),geometry,deep=True)['passed'])

    def test_large_head_cannot_be_clipped_to_expected_source_size(self):
        row,geometry=self.geometry()
        self.assertFalse(v.marker_pixels(row,self.pixels(),self.pixels(width=60),geometry,deep=True)['passed'])

    def test_shifted_head_cannot_be_replaced_by_a_matching_shaft(self):
        row,geometry=self.geometry()
        self.assertFalse(v.marker_pixels(row,self.pixels(),self.pixels(offset=25),geometry,deep=True)['passed'])

    def test_filled_interior_remains_required(self):
        row,geometry=self.geometry();row['source']['limits']['marker']=1
        self.assertFalse(v.marker_pixels(row,self.pixels(),self.pixels(hollow=True),geometry,deep=True)['passed'])

    def test_junction_ownership_is_not_guessed(self):
        row,geometry=self.geometry()
        row['source']['topology']['junctions']=[{'id':'J','point':[80,70],'source_evidence':'original junction'}]
        result=v.marker_pixels(row,self.pixels(),self.pixels(),geometry,deep=True)
        self.assertFalse(result['valid']);self.assertFalse(result['passed'])


if __name__=='__main__':unittest.main()
