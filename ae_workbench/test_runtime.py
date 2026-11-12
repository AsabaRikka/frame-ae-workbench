import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import runtime
import server


class RuntimeTests(unittest.TestCase):
    def test_fresh_workspace_does_not_load_developer_projects(self):
        with tempfile.TemporaryDirectory() as temp:
            env=dict(os.environ,FRAME_WORKBENCH_HOME=temp,PYTHONIOENCODING='utf-8')
            process=subprocess.run([sys.executable,'-c',"import server; assert server.STATE['project']==''; assert not server.STATE['assets']; assert not server.STATE['batches']"],
                                   cwd=Path(__file__).parent,env=env,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)

    def test_ae_install_directory_and_executable_are_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);exe=root/'AE'/'Support Files'/'AfterFX.exe';exe.parent.mkdir(parents=True);exe.write_bytes(b'fixture')
            with patch.object(runtime,'DATA',root/'settings'):
                for value in (exe,exe.parent,exe.parent.parent):
                    self.assertEqual(runtime.save_ae(str(value)),exe)
                self.assertEqual(runtime.after_effects(),exe)
                with self.assertRaises(ValueError):runtime.save_ae(str(root/'missing'))
                self.assertEqual(runtime.after_effects(),exe)

    def test_another_server_cannot_share_our_port(self):
        http=server.LocalHTTPServer(('127.0.0.1',0),server.Handler)
        try:
            with self.assertRaises(OSError):
                duplicate=server.LocalHTTPServer(http.server_address,server.Handler)
                duplicate.server_close()
        finally:
            http.server_close()

    def test_global_ae_lock_rejects_a_second_process(self):
        if os.name!='nt':self.skipTest('Windows only')
        with runtime.ae_session():
            code="import runtime;\ntry:\n with runtime.ae_session():raise AssertionError('second owner')\nexcept ValueError:pass"
            result=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).parent,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':
    unittest.main()
