import hashlib
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
from size_fit import prepare_replacement


class SizeFitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def sprite(self, name, size, box):
        path = self.root/name
        im = Image.new('RGBA', size)
        ImageDraw.Draw(im).rectangle((box[0],box[1],box[2]-1,box[3]-1), fill=(220,90,30,255))
        im.save(path)
        return path

    def adapt(self, source, original, role='enemy', sequence=False, size=None):
        with Image.open(original) as im:
            target_size = size or im.size
        target = dict(path=str(original),width=target_size[0],height=target_size[1],still=True)
        return prepare_replacement(dict(itemId=1,path=str(source),sequence=sequence,role=role),target,self.root/'output',lambda *_:self.fail('Unexpected media conversion'))

    def test_visible_bounds_fit_and_feet_align_without_changing_sources(self):
        original=self.sprite('old.png',(60,99),(2,6,59,98))
        new=self.sprite('new.png',(100,200),(20,20,80,180))
        hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (original,new)]
        result,report=self.adapt(new,original)
        with Image.open(result['path']) as im:
            self.assertEqual(im.size,(60,99))
            box=im.getchannel('A').point(lambda v:255 if v>127 else 0).getbbox()
        self.assertAlmostEqual(box[3],98,delta=1)
        self.assertAlmostEqual((box[0]+box[2])/2,30.5,delta=1)
        self.assertAlmostEqual((box[2]-box[0])/(box[3]-box[1]),60/160,delta=.025)
        self.assertEqual(hashes,[hashlib.sha256(p.read_bytes()).hexdigest() for p in (original,new)])
        self.assertAlmostEqual(report['scale'],92/160)

    def test_equal_canvas_still_matches_different_transparent_padding(self):
        original=self.sprite('old.png',(100,100),(10,10,90,90))
        new=self.sprite('new.png',(100,100),(35,35,65,65))
        result,report=self.adapt(new,original)
        self.assertGreater(report['scale'],2)
        with Image.open(result['path']) as im:
            box=im.getchannel('A').point(lambda v:255 if v>127 else 0).getbbox()
        self.assertAlmostEqual(box[2]-box[0],80,delta=1)

    def test_sequence_uses_one_transform_and_preserves_motion(self):
        original=self.sprite('old.png',(60,99),(0,0,60,99))
        new=self.sprite('new_00.png',(100,100),(10,10,30,80))
        self.sprite('new_01.png',(100,100),(20,10,40,80))
        result,report=self.adapt(new,original,sequence=True)
        self.assertTrue(result['sequence'])
        boxes=[]
        for p in sorted(Path(result['path']).parent.glob('frame_*.png')):
            with Image.open(p) as im:
                self.assertEqual(im.size,(60,99))
                boxes.append(im.getchannel('A').point(lambda v:255 if v>127 else 0).getbbox())
        self.assertEqual(len(boxes),2)
        self.assertAlmostEqual(boxes[1][0]-boxes[0][0],10*report['scale'],delta=1)
        self.assertEqual(boxes[0][3],boxes[1][3])

    def test_background_covers_canvas_without_stretching(self):
        original=self.sprite('old.png',(60,99),(0,0,60,99))
        new=self.sprite('wide.png',(200,100),(0,0,200,100))
        result,report=self.adapt(new,original,role='background')
        self.assertAlmostEqual(report['scale'],.99)
        with Image.open(result['path']) as im:
            self.assertEqual(im.getchannel('A').getextrema(),(255,255))

    def test_inconsistent_frame_sizes_fail_instead_of_jittering(self):
        original=self.sprite('old.png',(60,99),(0,0,60,99))
        new=self.sprite('new_00.png',(100,100),(10,10,30,80))
        self.sprite('new_01.png',(110,100),(20,10,40,80))
        with self.assertRaisesRegex(ValueError,'画布尺寸不一致'):
            self.adapt(new,original,sequence=True)

    def test_missing_sequence_frame_is_rejected(self):
        original=self.sprite('old.png',(60,99),(0,0,60,99))
        new=self.sprite('new_00.png',(100,100),(10,10,30,80))
        self.sprite('new_02.png',(100,100),(20,10,40,80))
        with self.assertRaisesRegex(ValueError,'缺帧'):
            self.adapt(new,original,sequence=True)


if __name__=='__main__':
    unittest.main()
