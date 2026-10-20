"""Installer entry regressions, using loopback HTTP and isolated project paths."""
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('entry_generator',ROOT/'tools/prepare_install_entries.py')
generator=importlib.util.module_from_spec(spec);spec.loader.exec_module(generator)
DATA=b'installer regression payload\n'*100


class Handler(BaseHTTPRequestHandler):
    requests=[]
    def log_message(self,*args):pass
    def do_GET(self):
        type(self).requests.append((self.path,self.headers.get('Range')))
        if self.path=='/missing':self.send_error(404);return
        offset=int(self.headers.get('Range','bytes=0-')[6:].split('-')[0])
        self.send_response(206 if offset else 200)
        if offset:self.send_header('Content-Range',f'bytes {offset}-{len(DATA)-1}/{len(DATA)}')
        self.send_header('Content-Length',str(len(DATA)-offset));self.end_headers()
        self.wfile.write(DATA[offset:])


class InstallerEntries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='lotra-bootstrap-')
        self.addCleanup(self.temp.cleanup);self.case=Path(self.temp.name);Handler.requests=[]
    def entry_function(self,powershell=False):
        text=(ROOT/('install-lotra.ps1' if powershell else 'install-lotra.sh')).read_text()
        if powershell:
            return text[text.index('function Get-LotraResource'):text.index("$ErrorActionPreference='Stop'\n# Host-owned")]
        return text[text.index('hash_file()'):text.index('case "$(uname')]+text[text.index('get() {'):text.index("python=''" )]
    def download(self,primary='/data',partial=False,changed=False):
        destination=self.case/'artifact';digest=hashlib.sha256(DATA).hexdigest()
        if partial:(self.case/'artifact.part').write_bytes(DATA[:73])
        if changed:destination.write_bytes(b'user changed bytes')
        if os.name=='nt':
            script=self.case/'probe.ps1'
            utility="Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1') -ErrorAction Stop\n"
            text=utility+self.entry_function(True)+"\nGet-LotraResource -Uri '"+self.url+primary+"' -Destination '"+str(destination)+"' -Sha256 '"+digest+"' -Bytes "+str(len(DATA))+" -ApiUri '"+self.url+"/data'\n"
            if partial:(self.case/'artifact.owner').write_text(digest+':'+str(len(DATA)))
            script.write_text(text)
            command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script)]
        else:
            script=self.case/'probe.sh'
            text='set -eu\nstate='+str(self.case)+'\n'+self.entry_function()+"\nget '"+self.url+primary+"' '"+str(destination)+"' '"+digest+"' '"+self.url+"/data'\n"
            script.write_text(text)
            command=['/bin/sh',str(script)]
        result=subprocess.run(command,capture_output=True,timeout=40)
        return result,destination
    def test_primary_download(self):
        result,target=self.download();self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(target.read_bytes(),DATA);self.assertEqual(len(Handler.requests),1)
    def test_one_fallback(self):
        result,target=self.download('/missing');self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(target.read_bytes(),DATA)
        self.assertEqual([p for p,_ in Handler.requests],['/missing','/data'])
    def test_partial_resume(self):
        result,target=self.download(partial=True);self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(target.read_bytes(),DATA);self.assertEqual(Handler.requests[0][1],'bytes=73-')
    def test_changed_cache_is_preserved(self):
        result,target=self.download(changed=True);self.assertNotEqual(result.returncode,0)
        self.assertEqual(target.read_bytes(),b'user changed bytes');self.assertEqual(Handler.requests,[])
    def test_verified_cache_is_not_downloaded_or_rewritten(self):
        result,target=self.download();self.assertEqual(result.returncode,0,result.stderr)
        before=target.stat().st_mtime_ns;Handler.requests=[]
        result,target=self.download();self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(target.stat().st_mtime_ns,before);self.assertEqual(Handler.requests,[])
    def test_repeated_generation_preserves_bytes_and_mtimes(self):
        source=self.case/'source';runtime=self.case/'runtime'
        shutil.copytree(ROOT/'installer/templates',source/'installer/templates')
        for name in ('install.ps1','install.py','install.sh'):
            shutil.copy2(ROOT/'installer'/name,source/'installer'/name)
        (runtime/'tools').mkdir(parents=True);(runtime/'tools/install_lotra.py').write_bytes(b'# pinned entry\n')
        generator.prepare(source,runtime,'1.35.4')
        files=[p for root in (source,runtime) for p in root.rglob('*') if p.is_file()]
        before={str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in files}
        generator.prepare(source,runtime,'1.35.4');generator.prepare(source,runtime,'1.35.4')
        self.assertEqual(before,{str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in files})
        shell=(source/'install-lotra.sh').read_bytes()
        self.assertNotIn(b'\r',shell);self.assertEqual(shell.count(b'api=${4:-}'),1)
        self.assertNotIn(b'if ! if !',shell);self.assertEqual(shell.count(b'"$engine_api_url"'),1)
        self.assertIn("$manifest.version -ne '1.35.4'",(source/'installer/install.ps1').read_text())
        self.assertIn("VERSION = '1.35.4'",(source/'installer/install.py').read_text())
    def test_shell_coordinator_and_templates_use_lf(self):
        for file in [ROOT/'install-lotra.sh',ROOT/'installer/install.sh',ROOT/'installer/templates/install-lotra.sh.in']:
            self.assertNotIn(b'\r',file.read_bytes(),str(file))


if __name__=='__main__':unittest.main()
