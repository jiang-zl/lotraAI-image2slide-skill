"""Current task's bounded frozen reads may reveal exact child dependencies."""
import json,sys,tempfile,unittest
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/lotra-image2slide-skill/scripts'))
from core.common import digest,write_json
from core.context_control import authorize,index
from packet_detail import select

class ManagedDependencies(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.task=Path(self.temp.name)/'task';self.task.mkdir()
        original=self.task/'original.png';original.write_bytes(b'unchanged original')
        self.parent=self.task/'Contract.json'
        write_json(self.task/'state.json',{'task_id':'current','source':self.ref(original),'objectives':{'component_first':True}})
    def ref(self,file):return {'path':file.relative_to(self.task).as_posix(),'sha256':digest(file)}
    def file(self,name,body):
        path=self.task/name;write_json(path,body);return self.ref(path)
    def bind(self,body):
        write_json(self.parent,body);state=json.loads((self.task/'state.json').read_bytes())
        state['registered_contract']=self.ref(self.parent);write_json(self.task/'state.json',state)
        return self.ref(self.parent)
    def test_current_source_scene_and_measurement_child_can_be_read(self):
        scene=self.file('Scene.json',{'objects':[{'id':'lead','style':{'font':'Family A'}}]})
        measurement=self.file('Measurements.json',{'valid':True,'passed':False})
        parent=self.bind({'source_scene':scene,'measurements':measurement})
        select(self.task,parent,['source_scene'],managed=True)
        self.assertEqual(select(self.task,scene,['objects'],managed=True)['items'][0]['id'],'lead')
        select(self.task,parent,['measurements'],managed=True)
        self.assertFalse(select(self.task,measurement,managed=True)['value']['passed'])
    def test_pagination_grants_only_returned_dependencies(self):
        first=self.file('First.json',{'value':1});second=self.file('Second.json',{'value':2})
        parent=self.bind({'children':[first,second]})
        result=select(self.task,parent,['children'],limit=1,managed=True)
        self.assertEqual(result['next_offset'],1);authorize(self.task,first)
        with self.assertRaisesRegex(ValueError,'CONTEXT_SCOPE_MISMATCH'):authorize(self.task,second)
        select(self.task,parent,['children'],offset=1,limit=1,managed=True);authorize(self.task,second)
    def test_cached_parent_read_repairs_missing_child_delivery(self):
        child=self.file('Child.json',{'value':1});parent=self.bind({'child':child})
        select(self.task,parent,['child'],managed=True)
        with index(self.task) as db:db.execute('DELETE FROM leases WHERE path=?',(child['path'],))
        select(self.task,parent,['child'],managed=True);authorize(self.task,child)
    def test_changed_child_and_unregistered_same_task_file_are_rejected(self):
        child=self.file('Child.json',{'value':1});unrelated=self.file('Other.json',{'private':True})
        parent=self.bind({'child':child});select(self.task,parent,['child'],managed=True)
        write_json(self.task/child['path'],{'value':2})
        with self.assertRaises(ValueError):authorize(self.task,child)
        with self.assertRaisesRegex(ValueError,'CONTEXT_SCOPE_MISMATCH'):authorize(self.task,unrelated)
    def test_child_cannot_escape_current_task_or_borrow_another_source(self):
        foreign=Path(self.temp.name)/'Foreign.json';write_json(foreign,{'private':True})
        escaped={'path':'../Foreign.json','sha256':digest(foreign)}
        parent=self.bind({'source_scene':escaped});select(self.task,parent,['source_scene'],managed=True)
        with self.assertRaises(ValueError):authorize(self.task,escaped)
        child=self.file('Child.json',{'value':1});parent=self.bind({'child':child});select(self.task,parent,['child'],managed=True)
        other=self.task/'new-original.png';other.write_bytes(b'another original')
        state=json.loads((self.task/'state.json').read_bytes());state['source']=self.ref(other);write_json(self.task/'state.json',state)
        with self.assertRaisesRegex(ValueError,'CONTEXT_SCOPE_MISMATCH'):authorize(self.task,child)

if __name__=='__main__':unittest.main()
