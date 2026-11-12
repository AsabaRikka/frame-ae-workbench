"""Run checks with an isolated workspace; never load developer state."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import _bootstrap

def main():
    with tempfile.TemporaryDirectory(prefix='frame-tests-') as workspace:
        env = dict(os.environ, FRAME_WORKBENCH_HOME=workspace, PYTHONPATH=str(_bootstrap.ROOT / 'src'), PYTHONIOENCODING='utf-8')
        commands = [
            [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests/unit', '-p', 'test_*.py'],
            ['node', '--test', 'tests/frontend/test_queues.cjs', 'tests/frontend/test_preview_bridge.cjs'],
        ]
        for command in commands:
            result = subprocess.run(command, cwd=_bootstrap.ROOT, env=env)
            if result.returncode:
                return result.returncode
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
