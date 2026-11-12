import tempfile
import time
import unittest
from pathlib import Path
from PIL import Image
from animation import AnimationPreviews, media_info


class AnimationTests(unittest.TestCase):
    def wait(self, manager, token):
        for _ in range(100):
            result=manager.status(token)
            if result['status']!='running':return result
            time.sleep(.01)
        self.fail('preview worker did not finish')

    def test_numbered_still_is_not_a_sequence(self):
        self.assertEqual(media_info(dict(path='enemy_01.png',still=True))['mediaKind'],'image')
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for i in range(3):Image.new('RGBA',(8,8)).save(root/f'enemy_{i:02}.png')
            info=media_info(dict(path=str(root/'enemy_00.png'),still=False,fps=24,duration=100))
            self.assertEqual((info['mediaKind'],info['frameCount']),('sequence',3))

    def test_sequence_order_fps_and_transparency(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for i in range(8,11):Image.new('RGBA',(16,12),(i,20,30,128)).save(root/f'frame_{i:02}.png')
            manager=AnimationPreviews(root/'cache',None,None)
            job=manager.start('A.aep',dict(id=1,path=str(root/'frame_08.png'),still=False,fps=12))
            result=self.wait(manager,job['id'])
            self.assertEqual((result['status'],result['frameCount'],result['duration']),('done',3,.25))
            with Image.open(manager.frame(job['id'],2)) as im:self.assertEqual(im.getpixel((0,0)),(10,20,30,128))
            with self.assertRaises(ValueError):manager.frame(job['id'],3)

    def test_missing_sequence_frame_is_reported(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for i in (1,3):Image.new('RGBA',(8,8)).save(root/f'f_{i:02}.png')
            manager=AnimationPreviews(root/'cache',None,None)
            job=manager.start('A.aep',dict(id=1,path=str(root/'f_01.png'),still=False))
            result=self.wait(manager,job['id'])
            self.assertEqual(result['status'],'failed');self.assertIn('缺帧',result['error'])

    def test_animated_gif_preserves_frame_durations(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'a.gif'
            frames=[Image.new('RGB',(8,8),c) for c in ('red','blue')]
            frames[0].save(p,save_all=True,append_images=frames[1:],duration=[100,200],loop=0)
            manager=AnimationPreviews(root/'cache',None,None)
            job=manager.start('A.aep',dict(id=1,path=str(p),still=False))
            result=self.wait(manager,job['id'])
            self.assertEqual(result['durations'],[100,200])
            with Image.open(manager.frame(job['id'],1)) as im:self.assertEqual(im.getpixel((0,0))[:3],(0,0,255))
