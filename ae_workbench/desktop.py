"""Windows desktop host for the local workbench, using the WebView2 renderer."""
import ctypes
import json
import threading
import time


def close_blocker(server):
    if server.PICKER_LOCK.locked():
        return '请先完成或取消文件夹选择，再关闭工作台。'
    if server.BUSY or server.SCANNING or server.GENERATION.busy():
        return '扫描、导出或 AI 生成仍在运行，请等任务结束后再关闭。'
    return ''


def request_close(server):
    with server.LOCK:
        message=close_blocker(server)
        if not message:
            server.SHUTTING_DOWN=True
        return message


def run(server,http,url,runtime,smoke_test=False):
    import webview
    import native_folder
    from portable import read_health

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('FrameWorkbench.Desktop.1')
    webview.settings['ALLOW_DOWNLOADS']=True
    webview.settings['ALLOW_FILE_URLS']=False
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER']=True
    stopped=threading.Event()
    started=threading.Event()
    failure=[]

    def serve():
        try:
            server.serve(http)
        except Exception as exc:
            failure.append(exc)
        finally:
            stopped.set()

    thread=threading.Thread(target=serve,name='workbench-server',daemon=True)
    thread.start()
    for _ in range(100):
        if stopped.is_set():
            raise RuntimeError('本地服务启动失败：'+str(failure))
        if read_health(url).get('appId')==runtime.APP_ID:
            break
        time.sleep(.1)
    else:
        raise RuntimeError('本地服务启动超时')

    window=webview.create_window('帧场 AE 工作台 · '+runtime.VERSION,url,width=1440,height=940,
                                min_size=(1000,680),background_color='#f5f6f7',text_select=True)

    def activate():
        window.restore()
        window.show()

    def picker(initial):
        paths=window.create_file_dialog(webview.FileDialog.FOLDER,directory=initial)
        return dict(cancelled=not bool(paths),**({'path':paths[0]} if paths else {}))

    def closing():
        message=request_close(server)
        if message:
            ctypes.windll.user32.MessageBoxW(0,message,'任务尚未结束',64)
            return False
        return True

    def loaded():
        started.set()

    def monitor():
        stopped.wait()
        if started.wait(30):
            window.destroy()

    result={}

    def check():
        try:
            if not started.wait(40):
                raise RuntimeError('桌面页面加载超时')
            for _ in range(100):
                result['title']=window.evaluate_js('document.title')
                result['text']=window.evaluate_js('document.body.innerText')
                if window.evaluate_js("typeof state !== 'undefined' && state !== null && tab === 'catalog' && document.querySelector('#connection').textContent.indexOf('检查中') === -1"):
                    break
                time.sleep(.2)
            else:
                raise RuntimeError('新版导航未加载')
            result['mp4']=window.evaluate_js('document.createElement("video").canPlayType(\'video/mp4; codecs="avc1.42E01E"\')')
            if not result['mp4']:
                raise RuntimeError('当前窗口组件不支持 H.264 视频')
            result['health']=read_health(url)
            result['ok']=True
        except Exception as exc:
            result.update(ok=False,error=str(exc))
        finally:
            (runtime.DATA/'desktop-test.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            window.destroy()

    server.DESKTOP_ACTIVATE=activate
    native_folder.DESKTOP_PICKER=picker
    window.events.closing+=closing
    window.events.loaded+=loaded
    threading.Thread(target=monitor,name='desktop-shutdown',daemon=True).start()
    try:
        webview.start(check if smoke_test else None,gui='edgechromium',debug=False,
                      storage_path=str(runtime.DATA/'webview'),private_mode=False,
                      icon=str(runtime.RESOURCE_ROOT/'app.ico'))
    except Exception as exc:
        raise RuntimeError('桌面窗口未能启动。若缺少 WebView2，请运行程序旁 runtime-installers 中的微软离线安装器，然后重新启动。Windows 还需要 .NET Framework 4.8。\n'+str(exc)) from exc
    finally:
        native_folder.DESKTOP_PICKER=None
        server.DESKTOP_ACTIVATE=None
        if thread.is_alive():
            http.shutdown()
        thread.join(timeout=10)
        http.server_close()
    if smoke_test and not result.get('ok'):
        raise RuntimeError('桌面自检失败：'+str(result))
