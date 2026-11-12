"""Local animation previews; originals are never rewritten."""
import hashlib
import json
import threading
import uuid
from functools import lru_cache
from pathlib import Path
from PIL import Image
from frame_workbench.media.size_fit import sequence_files

RASTER_SEQUENCE = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.exr'}
VIDEO = {'.mp4', '.mov', '.avi', '.mxf', '.webm', '.m4v'}


@lru_cache(maxsize=512)
def sequence_count(path, directory_stamp):
    try:return len(sequence_files(path, True)), ''
    except (OSError, ValueError) as exc:return 0, str(exc)


def media_info(entry):
    ext = Path(entry.get('path', '')).suffix.lower()
    if entry.get('sourceKind') == 'composition':
        kind = 'composition'
    elif entry.get('hasVideo') is False:
        kind = 'audio'
    elif entry.get('sequence') or (ext in RASTER_SEQUENCE and entry.get('still') is False):
        kind = 'sequence'
    elif ext in {'.gif', '.webp'} and entry.get('still') is False:
        kind = 'animated_image'
    elif ext in VIDEO:
        kind = 'video'
    else:
        kind = 'image'
    fps = float(entry.get('fps') or 30)
    frames, sequence_error = 0, ''
    if kind == 'sequence':
        try:
            source=Path(entry.get('path',''))
            frames, sequence_error=sequence_count(str(source),source.parent.stat().st_mtime_ns)
        except OSError as exc:sequence_error=str(exc)
    return dict(mediaKind=kind, mediaLabel={'composition':'合成动画','sequence':'序列帧','animated_image':'动画图片','video':'视频','audio':'声音','image':'图片'}[kind],
                animated=kind in ('composition','sequence','animated_image','video'), fps=fps,
                frameCount=frames, sequenceError=sequence_error)


class AnimationPreviews:
    def __init__(self, root, run_process, render_comp):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.run_process=run_process;self.render_comp=render_comp
        self.jobs={};self.lock=threading.RLock()

    def start(self, project, entry):
        info=media_info(entry)
        if not info['animated']:raise ValueError('此项是静态图片，没有动画')
        with self.lock:
            for job in self.jobs.values():
                if job['project']==project and job['entry']==entry and job['status']=='running':
                    return self.public(job)
            token=uuid.uuid4().hex
            job=dict(id=token,status='running',project=project,entry=dict(entry),kind=info['mediaKind'])
            self.jobs[token]=job
            threading.Thread(target=self._prepare,args=(job,),daemon=True).start()
            return self.public(job)

    def public(self, job):
        return {k:v for k,v in job.items() if k not in ('entry','paths','path','project','premultiplied')}

    def status(self, token):
        with self.lock:
            if token not in self.jobs:raise ValueError('预览已过期，请重新打开')
            return self.public(self.jobs[token])

    def _prepare(self, job):
        folder=self.root/job['id'];folder.mkdir()
        e=job['entry'];path=Path(e.get('path',''));kind=job['kind']
        try:
            if kind=='sequence':
                paths=sequence_files(path,True)
                fps=float(e.get('fps') or 30)
                job.update(paths=paths,frameCount=len(paths),fps=fps,durations=[1000/fps]*len(paths),duration=len(paths)/fps,player='frames')
                if float(e.get('duration') or 0)>len(paths)/fps*1.5:job['note']=f'{len(paths)} 张序列帧 · {fps:g} fps · 预览循环播放一轮；AE 内的循环次数保持原样'
            elif kind=='animated_image':
                with Image.open(path) as im:
                    durations=[]
                    for i in range(im.n_frames):
                        im.seek(i);durations.append(max(10,im.info.get('duration',100)))
                job.update(path=path,frameCount=len(durations),durations=durations,duration=sum(durations)/1000,player='frames')
            elif kind=='composition':
                result=self.render_comp(job['project'],e,folder)
                paths=[folder/f'{i:05}.png' for i in range(result['frames'])]
                if not paths or not all(p.is_file() and p.stat().st_size for p in paths):raise ValueError('AE 动画预览输出不完整')
                job.update(paths=paths,frameCount=len(paths),fps=result['fps'],durations=[1000/result['fps']]*len(paths),duration=len(paths)/result['fps'],player='frames',premultiplied=True,
                           note='合成工作区起点最多 5 秒 · 12 fps 预览；导出仍保留原工程帧率')
            else:
                output=folder/'preview.mp4'
                self.run_process(['ffmpeg','-nostdin','-n','-v','error','-i',str(path),'-t','30','-vf',"scale=640:480:force_original_aspect_ratio=decrease:force_divisible_by=2,format=yuv420p",'-c:v','libx264','-preset','veryfast','-c:a','aac','-movflags','+faststart',str(output)],folder/'convert.log',180)
                if not output.is_file() or not output.stat().st_size:raise ValueError('视频预览未生成')
                job.update(path=output,player='video',note='视频预览最多 30 秒；透明视频在此预览中显示为黑底，原文件不变')
            job['status']='done'
        except Exception as exc:
            job.update(status='failed',error=str(exc))

    def frame(self, token, index):
        with self.lock:
            job=self.jobs.get(token)
            if not job or job['status']!='done':raise ValueError('预览尚未完成')
            if job['player']=='video':return job['path']
            if index<0 or index>=job['frameCount']:raise ValueError('帧编号超出范围')
            output=self.root/token/f'thumb-{index:05}.png'
            if output.is_file():return output
            source=job['paths'][index] if 'paths' in job else job['path']
            with Image.open(source) as im:
                if job['kind']=='animated_image':im.seek(index)
                rgba=im.convert('RGBA')
                if job.get('premultiplied'):rgba=Image.frombytes('RGBa',rgba.size,rgba.tobytes()).convert('RGBA')
                rgba.thumbnail((640,480))
                rgba.save(output)
            return output
