"""Actual-delivery reopen dispatch, failure retention and renderer identity."""
import json,shutil,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/lotra-image2slide-skill/scripts'))
from core import libreoffice_backend as backend,presentation_backend as presentation
from core.common import digest

class Reopen(unittest.TestCase):
    def setUp(self):
        base=ROOT/'.lotraAI-build/reopen-tests';base.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.source=self.root/'Canonical.pptx';presentation.fixture(self.source)
        self.before=digest(self.source);self.renderer={'backend':'LibreOffice','executable':str(self.root/'soffice'),'identity':'fixed-resource'}

    def saved(self,command,**kwargs):
        target=Path(command[command.index('--outdir')+1])/self.source.name
        shutil.copyfile(self.source,target)
        class Process:
            returncode=0
            def wait(self,**kwargs):return 0
            def poll(self):return 0
        return Process()

    def test_owned_saved_copy_reopens_through_bound_editor_and_keeps_pdf_ownership(self):
        import pymupdf
        def reopened(file,output,renderer,**kwargs):
            self.assertEqual(Path(file).parent.name,'saved');self.assertEqual(renderer,self.renderer)
            output=Path(output);output.mkdir();pdf=output/'Final.pdf'
            document=pymupdf.open();document.new_page().insert_text((10,20),'owned reopen');document.save(pdf);document.close()
            return {'status':'PASS','backend':'LibreOffice','pptx_hash':digest(file),'pdf_hash':digest(pdf),'pdf':{'status':'EXPORTED'}}
        output=self.root/'proof'
        with patch.object(backend.subprocess,'Popen',side_effect=self.saved),patch('core.portable_editor.render',side_effect=reopened) as editor,patch('core.render.render') as old:
            result=backend.save_reopen(self.source,output,'declared',renderer=self.renderer)
        editor.assert_called_once();old.assert_not_called()
        self.assertEqual(result['reopen_transport'],'REQUEST_BOUND_EDITOR');self.assertEqual(digest(self.source),self.before)
        marker=json.loads((output/'reopen-render/Pdf-lifecycle.json').read_bytes())
        self.assertEqual(marker['pptx'],str((output/'saved'/self.source.name).resolve()))
        self.assertEqual(marker['pdf_sha256'],result['pdf_sha256'])

    def test_failed_reopen_does_not_adopt_an_existing_pdf_or_claim_save_reopen(self):
        output=self.root/'failed'
        def fail(file,folder,*args,**kwargs):
            folder=Path(folder);folder.mkdir();(folder/'Final.pdf').write_bytes(b'failed partial PDF')
            raise RuntimeError('request acknowledgement missing')
        with patch.object(backend.subprocess,'Popen',side_effect=self.saved),patch('core.portable_editor.render',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'acknowledgement missing'):backend.save_reopen(self.source,output,'declared',renderer=self.renderer)
        self.assertFalse((output/'Save-reopen.json').exists())
        self.assertEqual(json.loads((output/'Backend-failure.json').read_bytes())['status'],'FAILED')
        self.assertEqual(digest(self.source),self.before)

    def test_project_renderer_cannot_switch_executable_at_final_delivery(self):
        caps={'project':str(self.root),'presentation_backend':{'backend':'LibreOffice','executable':str(self.root/'declared')}}
        with patch('core.portable_runtime.capabilities',return_value={'status':'READY','backend':'LibreOffice','executable':str(self.root/'other')}),patch.object(backend,'save_reopen') as action:
            with self.assertRaisesRegex(ValueError,'differs from the declared'):presentation.validate_delivery(self.source,self.root/'audit',caps)
        action.assert_not_called();self.assertEqual(digest(self.source),self.before)

if __name__=='__main__':unittest.main()
