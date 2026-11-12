import base64
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from generation import Generation, protect, reference_png
import server


def png_bytes():
    b=io.BytesIO();Image.new('RGBA',(16,16),(230,80,30,255)).save(b,format='PNG');return b.getvalue()


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.g=Generation(self.root/'gen');self.g.save_config(dict(imageModel='test-image',videoModel='test-video'))
        self.ref=self.root/'reference.png';self.ref.write_bytes(png_bytes())
        self.e=dict(id=1,name='Enemy',previewPath=str(self.ref))

    def tearDown(self):self.temp.cleanup()

    def start(self,kind='image'):
        with patch.object(self.g,'key',return_value='private-test-key'),patch('generation.threading.Thread'):
            return self.g.start('A.aep',self.e,dict(kind=kind,prompt='New enemy',reference=True))

    def test_credentials_are_encrypted_and_never_returned(self):
        if os.name!='nt':self.skipTest('Windows DPAPI')
        self.g.save_config(dict(apiKey='private-test-key'))
        self.assertEqual(self.g.key(),'private-test-key')
        self.assertNotIn('private-test-key',self.g.config_path.read_text())
        self.assertNotIn('encryptedKey',self.g.public_config())
        self.assertNotIn('apiKey',self.g.public_config())

    def test_image_request_download_and_verification(self):
        job=self.start();original=self.ref.read_bytes()
        with patch.object(self.g,'key',return_value='private-test-key'),patch('generation.request_json',return_value={'data':[{'b64_json':base64.b64encode(png_bytes()).decode()}]}) as request:
            self.g._run(self.g.jobs[job['id']],False)
        output=self.g.output(job['id'])
        self.assertEqual(output.suffix,'.png');self.assertEqual(self.ref.read_bytes(),original)
        args=request.call_args.args;self.assertEqual(args[0],'/images/generations')
        self.assertTrue(args[2]['image'].startswith('data:image/png;base64,'))
        self.assertEqual(self.g.jobs[job['id']]['status'],'done')
        self.assertNotIn('private-test-key',(output.parent.parent/'job.json').read_text())

    def test_invalid_image_is_not_success_and_no_retry(self):
        job=self.start()
        with patch.object(self.g,'key',return_value='private-test-key'),patch('generation.request_json',return_value={'data':[{'b64_json':base64.b64encode(b'not an image').decode()}]}) as request:
            self.g._run(self.g.jobs[job['id']],False)
        self.assertEqual(request.call_count,1);self.assertEqual(self.g.jobs[job['id']]['status'],'failed')
        with self.assertRaises(ValueError):self.g.output(job['id'])

    def test_video_failure_keeps_remote_id_and_resume_does_not_post(self):
        job=self.start('video');internal=self.g.jobs[job['id']]
        with patch.object(self.g,'key',return_value='private-test-key'),patch('generation.request_json',side_effect=[{'id':'cgt-test-123'},{'status':'failed','error':{'message':'rejected'}}]) as request:
            self.g._run(internal,False)
        self.assertEqual(internal['remoteId'],'cgt-test-123');self.assertEqual(internal['status'],'failed')
        self.assertEqual(request.call_args_list[0].args[2]['content'][1]['role'],'first_frame')
        with patch.object(self.g,'key',return_value='private-test-key'),patch('generation.request_json',return_value={'status':'failed'}) as request:
            self.g._run(internal,True)
        self.assertEqual(len(request.call_args.args),2)
        self.assertEqual(request.call_args.args[0],'/contents/generations/tasks/cgt-test-123')

    def test_restart_does_not_resubmit(self):
        job=self.start('video')
        reopened=Generation(self.g.root)
        self.assertEqual(reopened.jobs[job['id']]['status'],'interrupted')
        self.assertFalse(reopened.busy())

    def test_video_reference_is_padded_without_stretching(self):
        p=self.root/'narrow.png';Image.new('RGBA',(50,400),(255,0,0,128)).save(p)
        out=self.root/'prepared.png';reference_png(p,out,True)
        with Image.open(out) as im:
            self.assertGreaterEqual(min(im.size),300);self.assertGreaterEqual(im.width/im.height,.4)

    def test_stale_project_cannot_apply_generated_asset(self):
        with patch.object(server,'STATE',dict(project='B.aep')):
            with self.assertRaisesRegex(ValueError,'已切换'):
                server.dispatch('/api/generation-apply',dict(project='A.aep',target=1,id='anything'))

    def test_failure_redacts_credential(self):
        job=self.start()
        with patch.object(self.g,'key',return_value='private-test-key'),patch('generation.request_json',side_effect=ValueError('network private-test-key')):
            self.g._run(self.g.jobs[job['id']],False)
        self.assertNotIn('private-test-key',str(self.g.list()))

    def test_current_animation_frame_is_used_as_reference(self):
        preview=dict(project='A.aep',entry=dict(id=1),player='frames')
        with patch.object(server,'STATE',dict(project='A.aep')),patch.object(server,'selected_entry',return_value=self.e),patch.dict(server.ANIMATIONS.jobs,{'test-motion':preview}),patch.object(server.ANIMATIONS,'frame',return_value=self.ref) as frame,patch.object(server.GENERATION,'start',return_value={'id':'test-generation'}) as start:
            server.dispatch('/api/generate',dict(project='A.aep',target=1,animationId='test-motion',referenceFrame=7,reference=True))
            frame.assert_called_once_with('test-motion',7)
            self.assertEqual(start.call_args.args[1]['previewPath'],str(self.ref))

    def test_other_projects_animation_cannot_be_uploaded_as_reference(self):
        preview=dict(project='B.aep',entry=dict(id=1),player='frames')
        with patch.object(server,'STATE',dict(project='A.aep')),patch.object(server,'selected_entry',return_value=self.e),patch.dict(server.ANIMATIONS.jobs,{'test-motion':preview}),patch.object(server.GENERATION,'start') as start:
            with self.assertRaisesRegex(ValueError,'参考动画已变化'):
                server.dispatch('/api/generate',dict(project='A.aep',target=1,animationId='test-motion',referenceFrame=7,reference=True))
            start.assert_not_called()
