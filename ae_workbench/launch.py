"""Compatibility entry; implementation lives under src/ and scripts/."""
import runpy
import sys
from pathlib import Path
scripts = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(scripts))
if __name__ == '__main__':
    runpy.run_path(str(scripts / 'launch.py'), run_name='__main__')
