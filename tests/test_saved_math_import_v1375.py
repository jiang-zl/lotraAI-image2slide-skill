"""A saved-copy native import does not waive canonical Math style requirements."""
import copy,sys,tempfile,unittest
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/lotra-image2slide-skill/scripts'))
from core import math_editor as editor,presentation_backend as presentation
from core.common import digest
from core.mathml import NS

class SavedMath(unittest.TestCase):
    def setUp(self):
        folder=ROOT/'.lotraAI-build/saved-math-tests';folder.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=folder);self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.canonical=self.root/'Canonical.pptx';presentation.fixture(self.canonical)
        self.saved=self.root/'Application-saved.pptx'
        with ZipFile(self.canonical) as source,ZipFile(self.saved,'w') as target:
            for info in source.infolist():
                data=source.read(info.filename)
                if info.filename=='ppt/slides/slide1.xml':
                    xml=E.fromstring(data)
                    for properties in xml.findall('.//m:r/a:rPr',NS):properties.getparent().remove(properties)
                    data=E.tostring(xml)
                target.writestr(info,data)

    def test_normal_render_still_rejects_missing_explicit_source_style(self):
        output=self.root/'normal';output.mkdir();before=digest(self.saved)
        with self.assertRaisesRegex(ValueError,'no explicit math run'):editor.prepare(self.saved,output)
        self.assertEqual(digest(self.saved),before)

    def test_saved_copy_mode_preserves_true_omml_without_inventing_font_or_size(self):
        output=self.root/'native';output.mkdir();before=digest(self.saved)
        target,plan=editor.prepare(self.saved,output,native_math_import=True)
        self.assertEqual(plan['math_style_scope'],'APPLICATION_SAVED_NATIVE_IMPORT_NO_SOURCE_STYLE_CLAIM')
        self.assertEqual(plan['groups'],[])
        self.assertEqual(plan['native_saved_math']['expected_math_objects'],1)
        self.assertEqual(plan['native_saved_math']['without_explicit_run_style'],1)
        self.assertEqual(target.read_bytes(),self.saved.read_bytes())
        with ZipFile(target) as package,ZipFile(self.saved) as source:
            actual=E.fromstring(package.read('ppt/slides/slide1.xml'));original=E.fromstring(source.read('ppt/slides/slide1.xml'))
            self.assertEqual([E.tostring(n,method='c14n') for n in actual.findall('.//m:oMath',NS)],
                             [E.tostring(n,method='c14n') for n in original.findall('.//m:oMath',NS)])
        self.assertEqual(digest(self.saved),before)

    def test_explicit_style_is_not_discarded_by_saved_copy_mode(self):
        output=self.root/'explicit';output.mkdir();target,plan=editor.prepare(self.canonical,output,native_math_import=True)
        self.assertEqual(target.read_bytes(),self.canonical.read_bytes())
        self.assertEqual(plan['native_saved_math']['without_explicit_run_style'],0)

    def test_mixed_explicit_sizes_are_still_a_capability_decision(self):
        zone=E.Element('{'+NS['a14']+'}m')
        for size in ('1200','1400'):
            run=E.SubElement(zone,'{'+NS['m']+'}r');properties=E.SubElement(run,'{'+NS['a']+'}rPr',sz=size)
            E.SubElement(properties,'{'+NS['a']+'}latin',typeface='Cambria Math')
        with self.assertRaisesRegex(ValueError,'mixed base fonts/sizes'):editor._style(zone)

    def branch(self,math=True):
        root=E.Element('{'+NS['p']+'}sld',nsmap={key:NS[key] for key in ('p','a','a14','m','mc')})
        alternate=E.SubElement(root,'{'+NS['mc']+'}AlternateContent')
        choice=E.SubElement(alternate,'{'+NS['mc']+'}Choice',Requires='a14')
        native=E.SubElement(choice,'{'+NS['p']+'}sp',id='native-primary')
        if math:
            zone=E.SubElement(native,'{'+NS['a14']+'}m');formula=E.SubElement(zone,'{'+NS['m']+'}oMath')
            run=E.SubElement(formula,'{'+NS['m']+'}r');E.SubElement(run,'{'+NS['m']+'}t').text='x'
        fallback=E.SubElement(alternate,'{'+NS['mc']+'}Fallback');E.SubElement(fallback,'{'+NS['p']+'}sp',id='fallback-picture')
        return root,alternate,choice

    def test_supported_math_primary_is_preserved_and_picture_fallback_is_excluded(self):
        root,alternate,choice=self.branch();before=E.tostring(root.find('.//m:oMath',NS),method='c14n')
        records=editor.native_math_branches(root)
        self.assertEqual(len(records),1);self.assertEqual(records[0]['native_math_objects'],1)
        self.assertFalse(root.findall('.//mc:AlternateContent',NS))
        self.assertEqual(root.find('p:sp',NS).get('id'),'native-primary')
        self.assertEqual(E.tostring(root.find('.//m:oMath',NS),method='c14n'),before)

    def test_unknown_required_namespace_is_a_capability_decision(self):
        root,alternate,choice=self.branch();choice.set('Requires','p')
        with self.assertRaisesRegex(ValueError,'unsupported or unbound namespace'):editor.native_math_branches(root)

    def test_unbound_required_prefix_is_not_silently_assumed_supported(self):
        root,alternate,choice=self.branch();choice.set('Requires','unbound')
        with self.assertRaisesRegex(ValueError,'unsupported or unbound namespace'):editor.native_math_branches(root)

    def test_multiple_native_math_choices_are_not_arbitrarily_selected(self):
        root,alternate,choice=self.branch();alternate.insert(1,copy.deepcopy(choice))
        with self.assertRaisesRegex(ValueError,'ambiguous native Math'):editor.native_math_branches(root)

    def test_a_different_native_math_fallback_is_not_hidden(self):
        root,alternate,choice=self.branch()
        alternate.find('mc:Fallback',NS).append(copy.deepcopy(choice.find('.//m:oMath',NS)))
        with self.assertRaisesRegex(ValueError,'ambiguous native Math'):editor.native_math_branches(root)

    def test_unrelated_compatibility_branches_are_exactly_retained(self):
        root,alternate,choice=self.branch(math=False);choice.set('Requires','unbound');before=E.tostring(root)
        self.assertEqual(editor.native_math_branches(root),[]);self.assertEqual(E.tostring(root),before)

    def test_fallback_only_math_cannot_claim_primary_native_support(self):
        root,alternate,choice=self.branch()
        zone=choice.find('.//m:oMath',NS);zone.getparent().remove(zone);alternate.find('mc:Fallback',NS).append(zone)
        with self.assertRaisesRegex(ValueError,'fallback-only native Math'):editor.native_math_branches(root)


if __name__=='__main__':unittest.main()
