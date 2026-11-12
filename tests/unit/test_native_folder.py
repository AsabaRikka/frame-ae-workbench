import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from frame_workbench.filesystem import dialogs as native_folder
class NativeFolderTests(unittest.TestCase):
    def test_missing_initial_folder_uses_existing_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(native_folder.initial_directory(str(Path(temp)/'不存在'/'子目录')),temp)
        self.assertEqual(native_folder.initial_directory('relative'), '')

    def test_cancel_preserves_selection_and_releases_lock(self):
        with patch.object(native_folder,'_run_picker',return_value={'cancelled':True}):
            self.assertEqual(native_folder.choose_native_folder(),{'cancelled':True})
        self.assertFalse(native_folder.PICKER_LOCK.locked())

    def test_unicode_selected_path(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'素材 [小怪]';folder.mkdir()
            with patch.object(native_folder,'_run_picker',return_value={'path':str(folder)}):
                self.assertEqual(native_folder.choose_native_folder(),{'cancelled':False,'path':str(folder.resolve())})

    def test_invalid_selection_releases_lock(self):
        with patch.object(native_folder,'_run_picker',return_value={'path':''}):
            with self.assertRaisesRegex(ValueError,'不存在'):
                native_folder.choose_native_folder()
        self.assertFalse(native_folder.PICKER_LOCK.locked())

    def test_only_one_picker_at_a_time(self):
        with native_folder.PICKER_LOCK, patch.object(native_folder,'_run_picker') as run:
            with self.assertRaisesRegex(ValueError,'已有文件夹'):
                native_folder.choose_native_folder()
            run.assert_not_called()


if __name__=='__main__':unittest.main()
