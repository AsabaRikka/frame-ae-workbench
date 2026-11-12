"""Start or gracefully restart this source workspace on its fixed local port."""
import argparse
import contextlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data-v02'
URL = 'http://127.0.0.1:8518'
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(path, payload=None):
    body = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(URL + path, data=body, headers={'Content-Type': 'application/json'})
    try:
        with OPENER.open(req, timeout=3) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read(65536)).get('error', '服务返回错误')
        except (ValueError, AttributeError):
            message = '此端口上的服务不支持当前启动接口'
        raise RuntimeError(str(message)) from None


def health():
    try:
        value = request('/api/health')
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None
    except (ValueError, RuntimeError) as exc:
        raise RuntimeError('8518 端口已有其他服务或旧版后台，未操作该进程。请先退出后再启动。') from exc
    if not isinstance(value, dict) or value.get('appId') != 'frame-workbench' or Path(value.get('home', '')).resolve() != ROOT:
        raise RuntimeError('8518 端口被其他工作区或程序占用，未操作该进程。请先退出占用程序。')
    return value


def port_open():
    try:
        with socket.create_connection(('127.0.0.1', 8518), timeout=.3):
            return True
    except OSError:
        return False


@contextlib.contextmanager
def launcher_lock():
    import msvcrt
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / 'launcher.lock').open('a+b') as file:
        if file.tell() == 0:
            file.write(b'0'); file.flush()
        deadline = time.monotonic() + 15
        while True:
            file.seek(0)
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('另一个启动或重启操作尚未结束，请稍后再试。')
                time.sleep(.2)
        try:
            yield
        finally:
            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)


def check_dependencies():
    if sys.version_info < (3, 10):
        raise RuntimeError('源码版需要 Python 3.10 或更高版本。')
    try:
        import PIL.Image
    except ImportError as exc:
        raise RuntimeError('当前 Python 缺少 Pillow，请先执行："' + sys.executable + '" -m pip install Pillow') from exc
    if not (ROOT / 'server.py').is_file():
        raise RuntimeError('找不到 ae_workbench/server.py，请保留完整源码目录。')


def stop_service():
    state = request('/api/state')
    if not isinstance(state, dict):
        raise RuntimeError('无法确认工作台任务状态，已取消重启。')
    if any(state.get(key) for key in ('busy', 'scanning', 'aiBusy')):
        raise RuntimeError('正在扫描、导出或 AI 生成，已取消重启。等任务完成后再双击 restart.cmd。')
    # The backend checks task state again under its own lock before accepting shutdown.
    reply = request('/api/shutdown', {})
    if not isinstance(reply, dict) or not reply.get('ok'):
        raise RuntimeError('旧后台没有确认退出，已取消重启。')
    deadline = time.monotonic() + 20
    while port_open():
        if time.monotonic() >= deadline:
            raise RuntimeError('等待旧后台退出超时，未强行结束任何进程。请稍后再试。')
        time.sleep(.2)


def start_service(timeout):
    if port_open():
        raise RuntimeError('8518 端口已被占用但服务无法正常响应，未启动第二份后台。')
    env = dict(os.environ)
    env.pop('FRAME_WORKBENCH_HOME', None)
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / 'server.log').open('a', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, str(ROOT / 'server.py')], cwd=ROOT,
                                   env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=0x08000000)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = health()
        if value:
            if value.get('pid') != process.pid:
                raise RuntimeError('端口上的后台身份发生变化，请检查后重试。')
            return value
        if process.poll() is not None:
            raise RuntimeError('后台启动失败，请查看日志：' + str(DATA / 'server.log'))
        time.sleep(.2)
    raise RuntimeError('后台尚未就绪，请查看日志；没有强行结束进程：' + str(DATA / 'server.log'))


def operate(command='start', open_browser=True, timeout=30):
    with launcher_lock():
        current = health()
        if command == 'restart' or current is None:
            check_dependencies()
        if command == 'restart' and current:
            stop_service()
            current = None
        if current is None:
            current = start_service(timeout)
        if open_browser:
            webbrowser.open(URL)
        return current


def main():
    parser = argparse.ArgumentParser(description='AE 工作台源码启动器')
    parser.add_argument('command', nargs='?', choices=('start', 'restart'), default='start')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        value = operate(args.command, not args.no_browser)
        print(f"AE 工作台已就绪：{URL}（PID {value['pid']}）")
        return 0
    except Exception as exc:
        message = '启动/重启未完成：' + str(exc)
        if sys.stderr is not None:
            print(message, file=sys.stderr)
        else:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, 'AE 工作台', 16)
        return 1


if __name__ == '__main__':
    sys.exit(main())
