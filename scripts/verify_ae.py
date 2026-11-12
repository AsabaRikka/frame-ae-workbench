"""Explicit integration checks; requires an idle AE session with saved changes."""
import argparse
import runpy
import _bootstrap

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='真实 AE 集成验证：先保存 AE 改动，避免并发扫描/渲染')
    parser.add_argument('suite', choices=('basic', 'catalog'))
    args = parser.parse_args()
    filename = 'verify_ae.py' if args.suite == 'basic' else 'verify_catalog_ae.py'
    runpy.run_path(str(_bootstrap.ROOT / 'tests' / 'integration' / filename), run_name='__main__')
