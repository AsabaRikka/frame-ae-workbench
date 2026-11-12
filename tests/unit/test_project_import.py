import tempfile
import unittest
from pathlib import Path

from frame_workbench.filesystem.browser import discover_projects


class ProjectImportTests(unittest.TestCase):
    def test_nested_projects_and_backups_are_listed_without_modification(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ['main.AEP','nested/another.aep','Adobe After Effects Auto-Save/main 1.aep','media/image.png']:
                path=root/name;path.parent.mkdir(exist_ok=True);path.write_bytes(b'unchanged')
            result=discover_projects(f'"{temp}"')
            self.assertEqual([p['name'] for p in result['projects']],['main.AEP','another.aep','main 1.aep'])
            self.assertEqual([p['backup'] for p in result['projects']],[False,False,True])
            self.assertFalse(result['truncated'])
            self.assertTrue(all(Path(p['path']).read_bytes()==b'unchanged'for p in result['projects']))

    def test_empty_folder_does_not_invent_a_project(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(discover_projects(temp)['projects'],[])
        with self.assertRaises(ValueError):
            discover_projects(temp)
        with self.assertRaises(ValueError):
            discover_projects('')

    def test_large_results_are_explicitly_marked_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            for name in ('a.aep','b.aep','c.aep'):
                (Path(temp)/name).touch()
            result=discover_projects(temp,max_results=2)
            self.assertEqual(len(result['projects']),2)
            self.assertTrue(result['truncated'])


if __name__=='__main__':
    unittest.main()
