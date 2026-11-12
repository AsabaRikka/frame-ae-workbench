import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from frame_workbench.media import export_settings as video
from frame_workbench.web import server as server
class ExportSettingsTests(unittest.TestCase):
    def test_invalid_specs_rejected(self):
        for settings in [dict(width=721,height=1280),dict(width=720),dict(fps=float('nan')),dict(fps=121),dict(fps=.1),dict(crf=-1),dict(audio='false'),dict(bitrate=0),dict(fit='stretch')]:
            with self.subTest(settings=settings),self.assertRaises(ValueError):video.normalize(settings)

    def test_project_settings_are_isolated_and_validated_before_save(self):
        state=dict(project='A',videoSettingsByProject={'B':dict(fps=24)})
        with patch.object(server,'STATE',state),patch.object(server,'save') as save:
            server.dispatch('/api/video-settings',dict(project='A',settings=dict(fps=60)))
            self.assertEqual(state['videoSettingsByProject']['A']['fps'],60)
            self.assertEqual(state['videoSettingsByProject']['B']['fps'],24)
            with self.assertRaises(ValueError):server.dispatch('/api/video-settings',dict(project='B',settings={}))
            with self.assertRaises(ValueError):server.dispatch('/api/video-settings',dict(project='A',settings=dict(width=1)))
            self.assertEqual(save.call_count,1)

    def test_old_batches_keep_default_and_new_settings_are_copied(self):
        value=dict(fps=60);snapshot=video.normalize(value);value['fps']=24
        self.assertEqual(snapshot['fps'],60)
        self.assertIn('18',video.encode_command('in.mov','out.mp4'))
        self.assertNotIn('fps=',','.join(video.encode_command('in.mov','out.mp4')))

    def test_enqueue_snapshots_current_project_settings(self):
        state=dict(project='A',scan=dict(items=[],comps=[]),assets=[],batches=[],videoSettingsByProject={'A':dict(fps=60)})
        with patch.object(server,'STATE',state),patch.object(server,'BUSY',False),patch.object(server,'SCANNING',False),patch.object(server,'validate_slots'),patch.object(server,'resolve_plan',return_value=[]),patch.object(server,'save'),patch.object(server.threading,'Thread'):
            server.enqueue_export([dict(id='row',name='sample')],[],False,'Main')
            state['videoSettingsByProject']['A']['fps']=24
            self.assertEqual(state['batches'][0]['videoSettings']['fps'],60)

    def test_output_validation_rejects_wrong_dimensions_fps_audio(self):
        probe=dict(format=dict(duration='1'),streams=[dict(codec_type='video',width=720,height=1280,avg_frame_rate='30/1')])
        video.validate_probe(probe,dict(width=720,height=1280,fps=30))
        for settings in [dict(width=1080,height=1920),dict(fps=60)]:
            with self.assertRaises(ValueError):video.validate_probe(probe,settings)
        probe['streams'].append(dict(codec_type='audio'))
        with self.assertRaises(ValueError):video.validate_probe(probe,dict(audio=False))

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
    def test_real_encode_dimensions_rate_audio_and_no_overwrite(self):
        def run(args):return subprocess.run(args,capture_output=True,timeout=30,creationflags=0x08000000)
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source.mov'
            made=run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=24','-f','lavfi','-i','sine=frequency=440','-t','0.5','-c:v','mpeg4','-c:a','pcm_s16le',str(source)])
            self.assertEqual(made.returncode,0,made.stderr)
            for i,settings in enumerate([dict(width=128,height=128,fps=30,audio=False),dict(width=96,height=160,fps=60,fit='cover',mode='bitrate',bitrate=1,audio=True)]):
                target=Path(temp)/f'{i}.mp4';cmd=video.encode_command(source,target,settings)
                encoded=run(cmd);self.assertEqual(encoded.returncode,0,encoded.stderr)
                probe=run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(target)])
                info=video.validate_probe(json.loads(probe.stdout),settings)
                self.assertEqual(any(s['codec_type']=='audio' for s in info['streams']),settings['audio'])
                with self.assertRaisesRegex(ValueError,'拒绝覆盖'):video.encode_command(source,target,settings)


if __name__=='__main__':unittest.main()
