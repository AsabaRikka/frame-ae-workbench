import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from frame_workbench import runtime
from frame_workbench.planning.combinations import build_plans


class LayoutTests(unittest.TestCase):
    def test_frontend_references_resolve_inside_resource_directory(self):
        html = (runtime.FRONTEND / 'index.html').read_text(encoding='utf-8')
        references = re.findall(r'(?:src|href)="(/[^"?#]+\.(?:js|css))"', html)
        self.assertGreater(len(references), 10)
        for reference in references:
            self.assertTrue((runtime.FRONTEND / reference.lstrip('/')).is_file(), reference)
        self.assertTrue(runtime.BRIDGE.is_file())
        self.assertTrue(runtime.ICON.is_file())

    def test_default_source_workspace_keeps_legacy_location(self):
        env = dict(os.environ)
        env.pop('FRAME_WORKBENCH_HOME', None)
        result = subprocess.run([sys.executable, '-c',
            "from frame_workbench import runtime; print(runtime.DATA)"],
            env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), runtime.PROJECT_ROOT / 'ae_workbench' / 'data-v02')

    def test_desktop_and_legacy_entry_work_outside_repository(self):
        with tempfile.TemporaryDirectory() as folder:
            for relative in ('scripts/desktop.py', 'ae_workbench/portable.py', 'scripts/launch.py'):
                result = subprocess.run([sys.executable, str(runtime.PROJECT_ROOT / relative), '--help'],
                    cwd=folder, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('usage:', result.stdout)

    def test_planning_does_not_depend_on_server_state(self):
        slots = [dict(id='a', candidates=[dict(id='x'), dict(id='y')])]
        plans = build_plans(slots, 2, 'repeatable', 'Example')
        self.assertEqual([p['name'] for p in plans], ['Example_001', 'Example_002'])
        self.assertEqual({p['choices']['a'] for p in plans}, {'x', 'y'})


if __name__ == '__main__':
    unittest.main()
