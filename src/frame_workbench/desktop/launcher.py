"""Desktop portable entry point; never launches a browser or system Python."""
import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def read_health(url):
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url+'/api/health',timeout=1) as response:
            return json.load(response)
    except Exception:
        return {}


def self_test(runtime):
    from PIL import Image
    import shutil
    import tempfile
    result=dict(version=runtime.VERSION,python=sys.version,frozen=runtime.FROZEN,home=str(runtime.WORK_HOME))
    with tempfile.TemporaryDirectory(prefix='frame-check-',dir=runtime.DATA) as temp:
        folder=Path(temp)
        Image.new('RGBA',(32,24),(200,80,30,128)).resize((16,12)).save(folder/'alpha.png')
        with Image.open(folder/'alpha.png') as image:
            assert image.size==(16,12) and image.getpixel((0,0))[3]==128
        for name in ('ffmpeg','ffprobe'):
            path=shutil.which(name)
            if not path or (runtime.FROZEN and not Path(path).is_relative_to(runtime.RESOURCE_ROOT)):
                raise RuntimeError('内置组件缺失：'+name)
            check=subprocess.run([path,'-version'],capture_output=True,text=True,timeout=15,creationflags=0x08000000)
            check.check_returncode();result[name]=dict(path=path,version=check.stdout.splitlines()[0])
        subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=blue:s=64x64:r=10',
                        '-t','0.2','-c:v','libx264','-pix_fmt','yuv420p',str(folder/'test.mp4')],check=True,timeout=30,creationflags=0x08000000)
        check=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(folder/'test.mp4')],check=True,capture_output=True,text=True,timeout=15,creationflags=0x08000000)
        assert float(json.loads(check.stdout)['format']['duration'])>0
    result['ok']=True
    (runtime.DATA/'self-test.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--port',type=int,default=8518)
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--desktop-smoke-test',action='store_true')
    args=parser.parse_args()
    if args.data_dir:
        os.environ['FRAME_WORKBENCH_HOME']=args.data_dir
    from frame_workbench import runtime as runtime
    runtime.DATA.mkdir(parents=True,exist_ok=True)
    log=(runtime.DATA/'launcher.log').open('a',encoding='utf-8',buffering=1)
    sys.stdout=sys.stderr=log
    handle=None
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
    kernel.CreateMutexW.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    kernel.ReleaseMutex.argtypes=[ctypes.c_void_p]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    owned=False
    try:
        if args.self_test:
            self_test(runtime)
            return 0
        mutex_name='Local\\FrameWorkbench-'+hashlib.sha256(str(runtime.WORK_HOME).lower().encode()).hexdigest()[:20]
        handle=kernel.CreateMutexW(None,False,mutex_name)
        if not handle:
            raise OSError('无法创建启动锁')
        owned=kernel.WaitForSingleObject(handle,0) in (0,128)
        if not owned:
            for _ in range(40):
                try:
                    details=json.loads((runtime.DATA/'running.json').read_text(encoding='utf-8'))
                    health=read_health(details['url'])
                    if health.get('appId')==runtime.APP_ID and health.get('home','').lower()==str(runtime.WORK_HOME).lower():
                        if not args.no_browser:
                            request=urllib.request.Request(details['url']+'/api/desktop-activate',data=b'{}',headers={'Content-Type':'application/json'},method='POST')
                            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=5):
                                pass
                        return 0
                except (OSError,ValueError,KeyError):
                    pass
                time.sleep(.25)
            raise RuntimeError('另一份工作台正在启动，请稍后再双击启动程序')
        from frame_workbench.web import server as server
        http=None
        for port in range(args.port,min(args.port+30,65536)):
            try:
                http=server.LocalHTTPServer(('127.0.0.1',port),server.Handler)
                break
            except OSError:
                continue
        if http is None:
            raise RuntimeError('无法启用本地服务，请检查端口是否被占用')
        url=f'http://127.0.0.1:{http.server_port}'
        (runtime.DATA/'running.json').write_text(json.dumps(dict(url=url,pid=os.getpid(),version=runtime.VERSION)),encoding='utf-8')
        if args.no_browser:
            server.serve(http)
        else:
            from frame_workbench.desktop.window import run
            run(server,http,url,runtime,smoke_test=args.desktop_smoke_test)
        return 0
    except Exception as exc:
        import traceback
        traceback.print_exc()
        if not args.no_browser:
            ctypes.windll.user32.MessageBoxW(0,f'启动失败：{exc}\n\n详细记录：{runtime.DATA / "launcher.log"}', '帧场 AE 工作台',16)
        return 1
    finally:
        if owned:
            running=runtime.DATA/'running.json'
            try:
                if json.loads(running.read_text(encoding='utf-8')).get('pid')==os.getpid():
                    running.unlink()
            except (OSError,ValueError):
                pass
        if owned and handle:
            kernel.ReleaseMutex(handle)
        if handle:
            kernel.CloseHandle(handle)


if __name__=='__main__':
    sys.exit(main())
