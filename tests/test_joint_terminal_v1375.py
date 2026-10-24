from pathlib import Path
import sys,unittest,copy
import numpy as np
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/lotra-image2slide-skill/scripts'))
from core import terminal_paint as terminal,line_geometry as g
from test_line_evidence_v1372 import source_line,entry


class JointTerminals(unittest.TestCase):
    def fixture(self):
        rows=[];geometries={}
        landmark={'id':'J','point':[80,60],'features':['arm','bus'],'source_evidence':'Original T contact'}
        for name,points in [('arm',[[80,60],[80,70]]),('bus',[[30,60],[140,60]])]:
            source=source_line(points);source['topology']['junctions']=[copy.deepcopy(landmark)]
            if name=='arm':source['ends'][1]['marker'].update(type='triangle',filled=True,width=[8,8],length=[8,8])
            native=entry(points=points,marker='triangle' if name=='arm' else 'none',matrix=[[200,0,0],[0,120,0],[0,0,1]])
            row={'id':name,'parts':[{'owner':name,'role':'shaft'}],'source':source};rows.append(row)
            geometries[name]=g.native_checks(row,{name:g.decode(native)},{name:native},{},.002)
        return rows,geometries

    def pixels(self,arm=True,width=2,extra=False,remote=False):
        image=Image.new('RGB',(200,120),'white');draw=ImageDraw.Draw(image)
        draw.line([(30,60),(140,60)],fill='black',width=width)
        if arm:
            draw.line([(80,60),(80,70)],fill='black',width=width)
            draw.polygon([(80,70),(76,62),(84,62)],fill='black')
        if extra:draw.line([(80,60),(110,25)],fill='black',width=2)
        if remote:draw.rectangle([160,35,170,42],fill='black')
        return np.asarray(image,float)/255

    def test_complete_declared_short_arm_and_bus_can_be_measured(self):
        rows,geo=self.fixture();result=terminal.joint(rows[0],rows,geo,self.pixels(),self.pixels())
        self.assertTrue(result['passed'],result);self.assertEqual(result['members'],['arm','bus'])

    def test_missing_short_arm_cannot_borrow_bus(self):
        rows,geo=self.fixture();self.assertFalse(terminal.joint(rows[0],rows,geo,self.pixels(),self.pixels(arm=False))['passed'])

    def test_thicker_joint_cannot_hide_as_unmeasurable_width(self):
        rows,geo=self.fixture();self.assertFalse(terminal.joint(rows[0],rows,geo,self.pixels(),self.pixels(width=7))['passed'])

    def test_extra_connected_branch_fails_and_remote_glyph_is_not_owned(self):
        rows,geo=self.fixture()
        self.assertFalse(terminal.joint(rows[0],rows,geo,self.pixels(),self.pixels(extra=True))['passed'])
        self.assertTrue(terminal.joint(rows[0],rows,geo,self.pixels(),self.pixels(remote=True))['passed'])

    def test_missing_peer_needs_decision(self):
        rows,geo=self.fixture();result=terminal.joint(rows[0],rows[:1],geo,self.pixels(),self.pixels())
        self.assertFalse(result['valid']);self.assertFalse(result['passed'])

if __name__=='__main__':unittest.main()
