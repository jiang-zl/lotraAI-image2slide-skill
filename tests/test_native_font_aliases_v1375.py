"""Same physical compatible family aliases cannot authorize font substitution."""
import copy,importlib,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace as Obj
from unittest.mock import patch
from zipfile import ZipFile
from fontTools.ttLib import TTFont
from lxml import etree as E
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/lotra-image2slide-skill/scripts'))
from core import native_font_aliases as aliases,font_embedding as embedding,font_resources as resources,math_editor
from core.common import digest,identity,write_json


class NativeAliases(unittest.TestCase):
    def setUp(self):
        self.fixture=importlib.import_module('test_font_workflow_v1373').Fonts()
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups);self.root=self.fixture.root
        face=self.fixture.face('Compatible English');file=Path(face['path'])
        with TTFont(file) as font:
            font['name'].setName('兼容中文',1,3,1,0x804)
            font['name'].setName('Wrong Broad Family',16,3,1,0x409);font.save(file)
        self.face=resources.describe(file,0,digest(file));self.face['id']=identity([digest(file),0])
        self.package=self.fixture.package('canonical.pptx',families=['Compatible English']*2)
        embedding.embed(self.package,[{'family':'Compatible English','resource':self.face}])
        self.output=self.root/'render';self.output.mkdir()
        self.input,self.plan=math_editor.prepare(self.package,self.output)

    def test_only_same_face_compatible_id_one_names_are_eligible(self):
        family=self.plan['font_aliases']['families']['Compatible English']
        self.assertIn('兼容中文',family['aliases']);self.assertNotIn('Wrong Broad Family',family['aliases'])
        self.assertEqual(aliases.validate_plan(self.output),self.plan['font_aliases'])

    def test_forged_alias_plan_is_rejected_before_import(self):
        self.plan['font_aliases']['families']['Compatible English']['aliases'].append('Unrelated Font')
        write_json(self.output/'editor-plan.json',self.plan)
        with self.assertRaisesRegex(ValueError,'FONT_NATIVE_ALIAS_PLAN_REQUIRED'):aliases.validate_plan(self.output)

    def test_localized_copy_retains_canonical_content_and_all_nonfont_fields(self):
        before=digest(self.package);target,resolution=aliases.native_input(self.output,self.plan['font_aliases'],['兼容中文'])
        self.assertEqual(resolution['resolved_families']['Compatible English'],'兼容中文')
        self.assertEqual(digest(self.package),before)
        with ZipFile(self.input) as original,ZipFile(target) as actual:
            self.assertEqual(original.namelist(),actual.namelist())
            for part in original.namelist():
                a,b=original.read(part),actual.read(part)
                if part in {row['part'] for row in resolution['changes']}:
                    root=E.fromstring(b)
                    for node in root.iter():
                        if node.get('typeface')=='兼容中文':node.set('typeface','Compatible English')
                    self.assertEqual(E.tostring(E.fromstring(a),method='c14n'),E.tostring(root,method='c14n'))
                else:self.assertEqual(a,b)

    def test_available_declared_family_does_not_need_alias_change(self):
        target,resolution=aliases.native_input(self.output,self.plan['font_aliases'],['Compatible English','兼容中文'])
        self.assertFalse(resolution['changes']);self.assertEqual(target.read_bytes(),self.input.read_bytes())

    def test_typographic_family_or_vertical_alias_does_not_resolve_compatible_family(self):
        target,resolution=aliases.native_input(self.output,self.plan['font_aliases'],['Wrong Broad Family','@兼容中文'])
        self.assertIsNone(resolution['resolved_families']['Compatible English'])
        self.assertFalse(resolution['changes'])

    def test_existing_import_copy_is_preserved(self):
        target=self.output/'editor-native-input.pptx';target.write_bytes(b'prior owned evidence')
        with self.assertRaisesRegex(ValueError,'Preserve existing'):aliases.native_input(self.output,self.plan['font_aliases'],[])
        self.assertEqual(target.read_bytes(),b'prior owned evidence')

    def test_extension_prefixes_and_quoted_nonfont_bytes_are_exactly_preserved(self):
        data=('<?xml version="1.0"?><r xmlns:q="'+aliases.A+'" xmlns:mc="urn:mc" xmlns:ext="urn:ext" mc:Ignorable="ext">'
            '<q:ea data="&gt;keep" typeface = \'Compatible English\'/><ext:n typeface="Compatible English"/>'
            '<q:latin typeface="Compatible&#32;English"/></r>').encode()
        actual,changes=aliases.patch_names(data,{'compatible english':('Compatible English','兼容中文')})
        expected=data.replace(b"typeface = 'Compatible English'","typeface = '兼容中文'".encode()).replace(b'typeface="Compatible&#32;English"','typeface="兼容中文"'.encode())
        self.assertEqual(actual,expected);self.assertEqual(len(changes),2)

    def test_entity_declaration_cannot_redefine_native_font_names(self):
        with self.assertRaisesRegex(ValueError,'DTD/entity'):
            aliases.patch_names(b'<!DOCTYPE r [<!ENTITY x "different">]><r/>',{})

    def test_alias_implementation_change_invalidates_component_qualification(self):
        from core import component_workflow as workflow
        before=workflow.implementation();original=workflow.digest
        def changed(file):return '0'*64 if Path(file).name=='native_font_aliases.py' else original(file)
        with patch.object(workflow,'digest',side_effect=changed):self.assertNotEqual(before,workflow.implementation())

    def fake_document(self,name='兼容中文'):
        class Portion:
            String='中A'
            def getPropertyValue(self,key):return name
        class Paragraph:
            def createEnumeration(self):return [Portion()]
        class Text:
            String='中A'
            def createEnumeration(self):return [Paragraph()]
        class Collection:
            def __init__(self,items):self.items=items;self.Count=len(items)
            def getByIndex(self,i):return self.items[i]
        text=Obj(ShapeType='com.sun.star.drawing.TextShape',Name='nested',Text=Text())
        group=Collection([text]);group.Name='group';group.ShapeType='com.sun.star.drawing.GroupShape'
        model=Obj(Rows=Obj(Count=2),Columns=Obj(Count=2),getCellByPosition=lambda *args:Text())
        table=Obj(ShapeType='com.sun.star.drawing.TableShape',Name='table',Model=model)
        return Obj(DrawPages=Collection([Collection([group,table])]))

    def test_nested_and_every_table_cell_have_actual_portion_coverage(self):
        proof=aliases.ordinary_usage(self.fake_document(),self.plan['font_aliases'],{'resolved_families':{'Compatible English':'兼容中文'}})
        self.assertEqual(proof['coverage'],{'shapes':3,'table_cells':4,'nonempty_text_portions':5})
        family=proof['families']['Compatible English'];self.assertEqual(len(family['owners']),5)
        self.assertEqual(family['native_names'],['兼容中文'])

    def test_unavailable_active_bound_family_cannot_silently_fall_back(self):
        with self.assertRaisesRegex(ValueError,'FONT_NATIVE_ALIAS_UNAVAILABLE'):
            aliases.ordinary_usage(self.fake_document('Compatible English'),self.plan['font_aliases'],{'resolved_families':{'Compatible English':None}})

    def test_pdf_family_fallback_is_failure_despite_native_name_properties(self):
        usage=aliases.ordinary_usage(self.fake_document(),self.plan['font_aliases'],{'resolved_families':{'Compatible English':'兼容中文'}})['families']
        with self.assertRaisesRegex(ValueError,'FONT_RENDER_FAMILY_UNVERIFIED'):aliases.verify_pdf_families(usage,{'ABCDEF+UnrelatedFont'})
        result=aliases.verify_pdf_families(usage,{'ABCDEF+CompatibleEnglish'})
        self.assertEqual(result['status'],'PDF_FAMILIES_OBSERVED');self.assertIn('no per-glyph',result['scope'])

    def test_stale_eot_header_cannot_supply_alias_identity(self):
        invalid=self.root/'invalid.pptx'
        with ZipFile(self.package) as package,ZipFile(invalid,'w') as output:
            for info in package.infolist():
                body=package.read(info.filename)
                if info.filename.startswith('ppt/fonts/'):
                    body=bytearray(body);body[60]^=1;body=bytes(body)
                output.writestr(info,body)
        with self.assertRaisesRegex(ValueError,'CheckSumAdjustment differs'):aliases.family_plan(invalid)


if __name__=='__main__':unittest.main()
