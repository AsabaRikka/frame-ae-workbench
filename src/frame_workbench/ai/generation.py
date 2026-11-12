"""Volcengine Ark image/video jobs, with local credentials and validated outputs."""
import base64
import ctypes
import io
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from PIL import Image

BASE='https://ark.cn-beijing.volces.com/api/v3'
ACTIVE={'submitting','queued','running','downloading'}


def write_json(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)


def protect(value, decrypt=False):
    if os.name!='nt':raise ValueError('密钥本地保存需要 Windows')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    raw=base64.b64decode(value) if decrypt else value.encode()
    buffer=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob()
    fn=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    fn.restype=wintypes.BOOL
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise ValueError('无法读取或保存本机密钥，请重新填写 API Key')
    try:
        result=ctypes.string_at(target.data,target.size)
        return result.decode() if decrypt else base64.b64encode(result).decode()
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes=[ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(target.data)


def request_json(route,key,payload=None):
    body=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(BASE+route,data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=180) as response:return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            body=json.loads(exc.read(65536));error=body.get('error',{});message=error.get('message') or error.get('code') or '请求失败'
        except (ValueError,AttributeError):message='请求失败'
        raise ValueError(f'火山方舟返回 {exc.code}：{str(message)[:600].replace(key,"[密钥已隐藏]")}') from None
    except (OSError,ValueError) as exc:
        raise ValueError('火山方舟请求未完成，请检查网络和账户；为避免重复计费，不会自动重新提交。') from exc


def download(url,path,max_bytes=250_000_000):
    # Generated files use provider-signed HTTPS URLs; never forward the API key.
    import ipaddress,socket
    def check(value):
        parsed=urllib.parse.urlparse(value)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ValueError('生成结果下载地址不是有效 HTTPS 地址')
        for item in socket.getaddrinfo(parsed.hostname,parsed.port or 443,type=socket.SOCK_STREAM):
            if not ipaddress.ip_address(item[4][0]).is_global:raise ValueError('生成结果下载地址不是公网地址')
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            check(newurl);return super().redirect_request(req,fp,code,msg,headers,newurl)
    check(url)
    with urllib.request.build_opener(Redirect()).open(url,timeout=90) as response, path.open('xb') as out:
        count=0
        while True:
            block=response.read(1024*1024)
            if not block:break
            count+=len(block)
            if count>max_bytes:raise ValueError('生成文件超过下载大小限制')
            out.write(block)


def reference_png(source,destination,video=False):
    with Image.open(source) as im:
        rgba=im.convert('RGBA');rgba.thumbnail((1536,1536))
        if video:
            # Ark first-frame images need both sides >=300px and a ratio within [0.4,2.5].
            width=max(rgba.width,round(rgba.height*.4));height=max(rgba.height,round(rgba.width/2.5))
            canvas=Image.new('RGBA',(width,height),'white');canvas.alpha_composite(rgba,((width-rgba.width)//2,(height-rgba.height)//2))
            ratio=max(1,300/min(canvas.size));rgba=canvas.resize((round(width*ratio),round(height*ratio)),Image.Resampling.LANCZOS).convert('RGB')
        else:
            ratio=max(1,15/min(rgba.size))
            if ratio>1:rgba=rgba.resize((round(rgba.width*ratio),round(rgba.height*ratio)),Image.Resampling.LANCZOS)
        rgba.save(destination,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(destination.read_bytes()).decode()


class Generation:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.config_path=self.root/'config.json';self.lock=threading.RLock();self.jobs={};self.workers=set()
        for p in self.root.glob('*/job.json'):
            try:
                job=json.loads(p.read_text(encoding='utf-8'))
                if job['status'] in ACTIVE:job.update(status='interrupted',error='程序已重新启动。视频可继续查询原任务；不会自动重复提交。')
                self.jobs[job['id']]=job
            except (ValueError,KeyError,OSError):pass

    def config(self):
        try:return json.loads(self.config_path.read_text(encoding='utf-8'))
        except (ValueError,OSError):return {}

    def public_config(self):
        c=self.config()
        return dict(provider='火山方舟',baseUrl=BASE,imageModel=c.get('imageModel',''),videoModel=c.get('videoModel',''),hasKey=bool(c.get('encryptedKey') or os.environ.get('ARK_API_KEY')))

    def save_config(self,data):
        with self.lock:
            c=self.config()
            for field in ('imageModel','videoModel'):
                value=str(data.get(field,c.get(field,''))).strip()
                if value and not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,160}',value):raise ValueError('模型 ID 格式不正确，请复制控制台的模型 ID 或推理接入点 ID')
                c[field]=value
            if data.get('clearKey'):c.pop('encryptedKey',None)
            elif data.get('apiKey','').strip():c['encryptedKey']=protect(data['apiKey'].strip())
            write_json(self.config_path,c)
        return self.public_config()

    def key(self):
        c=self.config()
        if c.get('encryptedKey'):return protect(c['encryptedKey'],True)
        key=os.environ.get('ARK_API_KEY','')
        if not key:raise ValueError('请先配置火山方舟 API Key')
        return key

    def persist(self,job):
        with self.lock:write_json(self.root/job['id']/'job.json',job)

    def list(self,project=None,target=None):
        with self.lock:return [dict(j) for j in reversed(list(self.jobs.values())) if (project is None or j['project']==project) and (target is None or str(j['target'])==str(target))]

    def busy(self):
        with self.lock:return bool(self.workers)

    def start(self,project,entry,data):
        kind=data.get('kind');prompt=str(data.get('prompt','')).strip();reference=bool(data.get('reference',True))
        if kind not in ('image','video'):raise ValueError('请选择生图或生视频')
        if not prompt or len(prompt)>5000:raise ValueError('提示词需为 1–5000 字')
        c=self.config();model=c.get(kind+'Model','');self.key()
        if not model:raise ValueError('请先填写'+('生图' if kind=='image' else '生视频')+'模型 ID')
        duration=int(data.get('duration',5))
        if kind=='video' and duration not in (5,10):raise ValueError('视频时长请选择 5 或 10 秒')
        size=data.get('size','2K')
        if size not in ('1K','2K','4K'):raise ValueError('图片尺寸参数不正确')
        ref=Path(entry.get('previewPath',''))
        if reference and not ref.is_file():raise ValueError('当前素材没有可用参考图，请先重新扫描，或关闭“参考原素材”')
        if reference and entry.get('previewBlank'):raise ValueError('当前参考帧完全透明，请关闭参考原素材并使用自定义提示词')
        with self.lock:
            if len(self.workers)>=2:raise ValueError('已有两项生成任务，请等待完成')
            for j in self.jobs.values():
                if j['status'] in ACTIVE and j['project']==project and j['target']==entry['id'] and j['prompt']==prompt and j['kind']==kind:raise ValueError('相同生成任务正在进行，请勿重复提交')
            token=uuid.uuid4().hex;folder=self.root/token;folder.mkdir();(folder/'media').mkdir()
            if reference:reference_png(ref,folder/'reference.png',video=kind=='video')
            job=dict(id=token,kind=kind,project=project,target=entry['id'],targetName=entry['name'],model=model,prompt=prompt,reference=reference,
                     duration=duration,size=size,status='submitting',created=time.strftime('%Y-%m-%d %H:%M:%S'))
            self.jobs[token]=job;self.persist(job);self.workers.add(token)
            threading.Thread(target=self._run,args=(job,False),daemon=True).start()
            return dict(job)

    def resume(self,token):
        with self.lock:
            job=self.jobs.get(token)
            if not job or job['kind']!='video' or not job.get('remoteId'):raise ValueError('没有可继续查询的视频任务')
            if job['status']=='done':raise ValueError('视频已经完成，无需重复查询')
            if token in self.workers:return dict(job)
            if len(self.workers)>=2:raise ValueError('已有两项生成任务，请稍后查询')
            self.key();self.workers.add(token);job.update(status='queued');job.pop('error',None);self.persist(job)
            threading.Thread(target=self._run,args=(job,True),daemon=True).start();return dict(job)

    def _run(self,job,resume):
        folder=self.root/job['id'];key=''
        try:
            key=self.key()
            if job['kind']=='image':
                payload=dict(model=job['model'],prompt=job['prompt'],size=job['size'],response_format='b64_json',watermark=False)
                if job['reference']:payload['image']='data:image/png;base64,'+base64.b64encode((folder/'reference.png').read_bytes()).decode()
                reply=request_json('/images/generations',key,payload)
                result=(reply.get('data') or [{}])[0]
                if result.get('error'):raise ValueError('生图失败：'+str(result['error']))
                raw=folder/'download'
                if result.get('b64_json'):raw.write_bytes(base64.b64decode(result['b64_json'],validate=True))
                elif result.get('url'):download(result['url'],raw)
                else:raise ValueError('接口没有返回生成图片')
                output=folder/'media'/'image.png'
                with Image.open(raw) as im:
                    im.load();im.save(output,format='PNG');job.update(width=im.width,height=im.height,hasAlpha=im.mode=='RGBA' and im.getchannel('A').getextrema()[0]<255)
                raw.unlink()
            else:
                if not resume:
                    content=[dict(type='text',text=job['prompt'])]
                    if job['reference']:content.append(dict(type='image_url',image_url=dict(url='data:image/png;base64,'+base64.b64encode((folder/'reference.png').read_bytes()).decode()),role='first_frame'))
                    reply=request_json('/contents/generations/tasks',key,dict(model=job['model'],content=content,duration=job['duration'],watermark=False))
                    remote=str(reply.get('id',''))
                    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,160}',remote):raise ValueError('接口没有返回有效的视频任务 ID')
                    job.update(remoteId=remote,status='queued');self.persist(job)
                deadline=time.monotonic()+1800
                while time.monotonic()<deadline:
                    reply=request_json('/contents/generations/tasks/'+job['remoteId'],key)
                    status=reply.get('status')
                    if status=='succeeded':break
                    if status in ('failed','cancelled','expired'):raise ValueError('视频任务'+status+'：'+str(reply.get('error',{})))
                    job['status']='running' if status=='running' else 'queued';self.persist(job);time.sleep(5)
                else:raise ValueError('等待视频超时，可继续查询原任务，无需重新生成')
                url=reply.get('content',{}).get('video_url')
                if not url:raise ValueError('接口未返回视频下载地址')
                job['status']='downloading';self.persist(job)
                raw=folder/('download-'+uuid.uuid4().hex+'.mp4');download(url,raw)
                probe=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type,width,height:format=duration','-of','json',str(raw)],capture_output=True,text=True,timeout=60,creationflags=0x08000000)
                info=json.loads(probe.stdout);streams=[s for s in info.get('streams',[]) if s.get('codec_type')=='video']
                if probe.returncode or not streams or float(info.get('format',{}).get('duration',0))<=0:raise ValueError('下载文件未通过视频校验')
                output=folder/'media'/'video.mp4';raw.replace(output)
                job.update(width=streams[0]['width'],height=streams[0]['height'],actualDuration=float(info['format']['duration']))
            if not output.is_file() or not output.stat().st_size:raise ValueError('生成结果文件不存在')
            job.update(status='done',output=str(output));job.pop('error',None)
        except Exception as exc:
            message=str(exc)
            if key:message=message.replace(key,'[密钥已隐藏]')
            job.update(status='failed',error=message[:900])
        finally:
            self.persist(job)
            with self.lock:self.workers.discard(job['id'])

    def output(self,token):
        with self.lock:
            job=self.jobs.get(token)
            if not job or job['status']!='done':raise ValueError('生成结果尚未完成')
            p=Path(job['output'])
            if not p.is_file() or not p.resolve().is_relative_to(self.root.resolve()):raise ValueError('生成结果不存在')
            return p
