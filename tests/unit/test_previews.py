import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from frame_workbench.assets.catalog import finalize_previews


class PreviewTests(unittest.TestCase):
    def test_direct_png_keeps_alpha_and_is_not_overwritten_by_legacy_tiff(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            raw = folder / 'preview-1-direct.png'
            Image.new('RGBA', (8, 8), (25, 45, 100, 128)).save(raw)
            (folder / 'preview-1_00001.tif').write_bytes(b'legacy cache')
            entry = dict(id=1, previewEncoding='png-direct-v2', previewPath=str(raw))
            with patch('frame_workbench.assets.catalog.subprocess.run') as run:
                finalize_previews(dict(items=[entry], comps=[]), folder)
                run.assert_not_called()
            with Image.open(folder / '1-thumb.png') as image:
                self.assertEqual(image.getpixel((0, 0)), (49, 89, 199, 128))
            # A cached scan must not apply the alpha correction a second time.
            finalize_previews(dict(items=[entry], comps=[]), folder)
            with Image.open(folder / '1.png') as image:
                self.assertEqual(image.getpixel((0, 0)), (49, 89, 199, 128))

    def test_corrupt_preview_does_not_hide_valid_next_item(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / '1.png').write_bytes(b'broken PNG')
            Image.new('RGBA', (8, 8), (255, 0, 0, 255)).save(folder / '2.png')
            scan = dict(items=[dict(id=1, previewPath=str(folder/'1.png')), dict(id=2)], comps=[])
            finalize_previews(scan, folder)
            self.assertIn('previewError', scan['items'][0])
            self.assertNotIn('previewPath', scan['items'][0])
            self.assertIn('previewPath', scan['items'][1])

    def test_legacy_conversion_timeout_is_an_item_error(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'preview-1_00001.tif').write_bytes(b'legacy cache')
            entry = dict(id=1)
            with patch('frame_workbench.assets.catalog.subprocess.run', side_effect=subprocess.TimeoutExpired('ffmpeg', 30)):
                finalize_previews(dict(items=[entry], comps=[]), folder)
            self.assertIn('previewError', entry)
