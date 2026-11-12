"""Portable paths, local tool discovery and cross-process AE ownership."""
import contextlib
import ctypes
import json
import os
import shutil
import sys
import subprocess
import threading
import uuid
from pathlib import Path

VERSION = '1.1.0'
APP_ID = 'frame-workbench'
FROZEN = bool(getattr(sys, 'frozen', False))
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESOURCE_ROOT = Path(sys._MEIPASS) if FROZEN else PROJECT_ROOT
FRONTEND = RESOURCE_ROOT / 'frontend'
BRIDGE = RESOURCE_ROOT / 'resources' / 'ae' / 'bridge.jsx'
ICON = RESOURCE_ROOT / 'resources' / 'icons' / 'app.ico'
APP_HOME = Path(sys.executable).resolve().parent if FROZEN else PROJECT_ROOT / 'ae_workbench'


def writable_home():
    candidate = Path(os.environ.get('FRAME_WORKBENCH_HOME', str(APP_HOME))).resolve()
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / ('.write-check-' + uuid.uuid4().hex)
        probe.write_bytes(b'')
        probe.unlink()
        return candidate
    except OSError:
        if 'FRAME_WORKBENCH_HOME' in os.environ:
            raise
        fallback = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'FrameWorkbench'
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


WORK_HOME = writable_home()
DATA = WORK_HOME / ('data-v1' if FROZEN or 'FRAME_WORKBENCH_HOME' in os.environ else 'data-v02')
OUTPUT = WORK_HOME / 'outputs'
TOOLS = RESOURCE_ROOT / 'tools'
DLL_LOCK = threading.Lock()
if TOOLS.is_dir():
    os.environ['PATH'] = str(TOOLS) + os.pathsep + os.environ.get('PATH', '')


def discover_ae():
    candidates = []
    for variable in ('ProgramFiles', 'ProgramW6432', 'ProgramFiles(x86)'):
        base = Path(os.environ.get(variable, 'C:/Program Files')) / 'Adobe'
        if base.is_dir():
            candidates.extend(base.glob('Adobe After Effects*/Support Files/AfterFX.exe'))
    if os.name == 'nt':
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for flag in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                for key_name in (r'SOFTWARE\Adobe\After Effects', r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'):
                    try:
                        with winreg.OpenKey(hive,key_name,0,winreg.KEY_READ|flag) as key:
                            for index in range(winreg.QueryInfoKey(key)[0]):
                                with winreg.OpenKey(key,winreg.EnumKey(key,index)) as sub:
                                    values={winreg.EnumValue(sub,i)[0]:winreg.EnumValue(sub,i)[1] for i in range(winreg.QueryInfoKey(sub)[1])}
                                    if 'Uninstall' in key_name and 'after effects' not in str(values.get('DisplayName','')).lower():
                                        continue
                                    for field in ('InstallPath','InstallLocation'):
                                        if values.get(field):
                                            base=Path(str(values[field]).strip('"'))
                                            candidates.extend([base/'AfterFX.exe',base/'Support Files'/'AfterFX.exe'])
                    except OSError:
                        pass
                try:
                    with winreg.OpenKey(hive,r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\AfterFX.exe',0,winreg.KEY_READ|flag) as key:
                        candidates.append(Path(winreg.QueryValueEx(key,'')[0].strip('"')))
                except OSError:
                    pass
    unique = {str(p.resolve()):p for p in candidates if p.is_file()}
    return sorted(unique, key=lambda p:('2022' not in p,p.lower()))


def read_settings():
    try:
        return json.loads((DATA/'settings.json').read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):
        return {}


def normalize_ae(value):
    path=Path(str(value).strip().strip('"')).resolve()
    if path.is_dir():
        path=path/'AfterFX.exe' if (path/'AfterFX.exe').is_file() else path/'Support Files'/'AfterFX.exe'
    if path.name.lower()!='afterfx.exe' or not path.is_file():
        raise ValueError('未找到 AfterFX.exe，请选择 AE 安装目录、Support Files 文件夹，或填写 AfterFX.exe 完整路径')
    return path


def after_effects():
    saved=read_settings().get('aePath')
    if saved:
        return Path(saved)
    candidates=discover_ae()
    return Path(candidates[0]) if candidates else RESOURCE_ROOT/'AE-not-configured.exe'


def save_ae(value):
    path=normalize_ae(value)
    DATA.mkdir(parents=True,exist_ok=True)
    settings=read_settings();settings['aePath']=str(path)
    temporary=DATA/'settings.tmp'
    temporary.write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(DATA/'settings.json')
    return path


def environment(ae, detect=False):
    return dict(version=VERSION,portable=FROZEN,aePath=str(ae) if ae.is_file() else read_settings().get('aePath',''),
                aeAvailable=ae.is_file(),renderAvailable=ae.with_name('aerender.exe').is_file(),
                ffmpegAvailable=bool(shutil.which('ffmpeg')),ffprobeAvailable=bool(shutil.which('ffprobe')),
                data=str(DATA),output=str(OUTPUT),candidates=discover_ae() if detect else [])


def launch_external(command, **kwargs):
    if not FROZEN or os.name!='nt':
        return subprocess.Popen(command, **kwargs)
    command=list(command)
    command[0]=shutil.which(command[0]) or command[0]
    env=dict(kwargs.pop('env',os.environ))
    env['PATH']=os.pathsep.join(p for p in env.get('PATH','').split(os.pathsep) if p and not Path(p).resolve().is_relative_to(RESOURCE_ROOT))
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.SetDllDirectoryW.argtypes=[ctypes.c_wchar_p]
    with DLL_LOCK:
        kernel.SetDllDirectoryW(None)
        try:
            return subprocess.Popen(command,env=env,**kwargs)
        finally:
            kernel.SetDllDirectoryW(str(RESOURCE_ROOT))


@contextlib.contextmanager
def ae_session():
    if os.name!='nt':
        yield
        return
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p]
    kernel.CreateMutexW.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    kernel.ReleaseMutex.argtypes=[ctypes.c_void_p]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.CreateMutexW(None,False,r'Local\FrameWorkbench-AE-Automation')
    if not handle:
        raise OSError(ctypes.get_last_error(),'无法创建 AE 任务锁')
    owned=False
    try:
        owned=kernel.WaitForSingleObject(handle,0) in (0,128)
        if not owned:
            raise ValueError('另一份工作台正在操作 AE，请等它完成后再试')
        yield
    finally:
        if owned:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)
