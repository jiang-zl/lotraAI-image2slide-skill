"""Validate actual serialized font bytes, not a stale in-memory header."""
import copy,importlib,io,json,struct,sys,unittest
from pathlib import Path
from zipfile import ZipFile
from fontTools.ttLib import TTFont,reorderFontTables
from fontTools.ttLib.sfnt import calcChecksum
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/lotra-image2slide-skill/scripts'))
from core import font_embedding as embedding,font_retention as retention,font_resources as resources,font_contract as fonts
from core.common import digest,identity,write_json


class EOTIntegrity(unittest.TestCase):
    def setUp(self):
        self.fixture=importlib.import_module('test_font_workflow_v1373').Fonts()
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)

    def face(self):
        face=self.fixture.face('Reordered Font');path=Path(face['path'])
        with TTFont(path) as font:order=list(reversed(font.keys()[1:]))
        data=io.BytesIO();reorderFontTables(io.BytesIO(path.read_bytes()),data,tableOrder=order)
        path.write_bytes(data.getvalue())
        face=resources.describe(path,0,digest(path));face['id']=identity([face['file_sha256'],0])
        return face

    def test_eot_header_uses_actual_saved_sfnt_after_table_reordering(self):
        face=self.face()
        with TTFont(face['path']) as original:prior=original['head'].checkSumAdjustment
        data=embedding.eot(face);body=data[-struct.unpack_from('<I',data,4)[0]:]
        with TTFont(io.BytesIO(body)) as saved:actual=saved['head'].checkSumAdjustment
        self.assertNotEqual(prior,actual,'Fixture must exercise changed serialization offsets')
        self.assertEqual(struct.unpack_from('<I',data,60)[0],actual)
        self.assertEqual(calcChecksum(body),0xB1B0AFBA)
        self.assertEqual(retention.sfnt(data,'application/x-fontdata'),body)

    def test_valid_body_cannot_hide_stale_eot_checksum_field(self):
        data=bytearray(embedding.eot(self.face()));data[60]^=1
        with self.assertRaisesRegex(ValueError,'CheckSumAdjustment differs'):
            retention.sfnt(bytes(data),'application/x-fontdata')

    def test_corrupt_sfnt_is_not_full_resource_retention(self):
        data=bytearray(embedding.eot(self.face()));data[-1]^=1
        with self.assertRaisesRegex(ValueError,'SFNT checksum is invalid'):
            retention.sfnt(bytes(data),'application/x-fontdata')

    def test_provider_raw_font_uses_same_independent_checksum_check(self):
        face=self.face();data=embedding.eot(face);body=data[-struct.unpack_from('<I',data,4)[0]:]
        self.assertEqual(retention.sfnt(body,'application/x-font-ttf'),body)
        damaged=body[:-1]+bytes([body[-1]^1])
        with self.assertRaisesRegex(ValueError,'SFNT checksum is invalid'):
            retention.sfnt(damaged,'application/x-font-ttf')

    def test_table_directory_cannot_escape_the_font_data(self):
        face=self.face();data=embedding.eot(face);body=bytearray(data[-struct.unpack_from('<I',data,4)[0]:])
        struct.pack_into('>I',body,20,len(body)+1)
        with self.assertRaisesRegex(ValueError,'table leaves'):
            retention.saved_checksum_adjustment(bytes(body))

    def test_new_encoder_preserves_and_avoids_prior_stale_cache(self):
        face=self.face();file=self.fixture.package('new-encoder.pptx',families=[face['family']])
        # Put the exact source in an owned private resource tree to exercise
        # the production cache selector, with no deletion/relabel of v2 bytes.
        folder=self.fixture.root/'.lotraAI-build/toolchain/font-snapshots';folder.mkdir(parents=True)
        copy=folder/'bound.ttf';copy.write_bytes(Path(face['path']).read_bytes());face={**face,'path':str(copy)}
        data=bytearray(embedding.eot(face));data[60]^=1
        cache=self.fixture.root/'.lotraAI-build/toolchain/fontdata';cache.mkdir()
        old=cache/('eot-v2-'+face['id']+'.fntdata');old.write_bytes(data)
        write_json(old.with_suffix('.json'),{'source_sha256':face['file_sha256'],'fontdata_sha256':digest(old)})
        before=old.read_bytes();embedding.embed(file,[{'family':face['family'],'resource':face}])
        self.assertEqual(old.read_bytes(),before)
        with ZipFile(file) as package:
            results=retention.verify_package(package,[{'family':face['family'],'resource':face}])
        self.assertEqual(len(results),1)
        self.assertTrue((cache/('eot-v3-saved-head-'+face['id']+'.fntdata')).is_file())

    def test_inferred_binding_reports_missing_ranking_reference(self):
        fixture=importlib.import_module('test_font_steps_v1374').FontSteps()
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        request=fonts.requests(fixture.scene,fixture.state)[0];face=fixture.fixture.old
        row={'request_id':request['id'],'family':face['family'],'resource_id':face['id'],
            'origin':'raster_inference','status':'approximate','comparison_ref':None,
            'evidence':{'source_hash':fixture.state['source']['sha256'],'roi':request['roi'],'description':'Original glyphs'}}
        with self.assertRaisesRegex(ValueError,'FONT_COMPARISON_REFERENCE_REQUIRED.*source_glyph_rankings'):
            fonts.bind(fixture.task,fixture.state,fixture.scene,[row],persist=False)


if __name__=='__main__':unittest.main()
