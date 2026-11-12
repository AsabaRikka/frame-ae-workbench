"""A Windows folder dialog in a short-lived STA helper; no shell interpolation."""
import base64
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path

PICKER_LOCK=threading.Lock()
DESKTOP_PICKER=None
SCRIPT=r'''
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;
public sealed class WorkbenchPickerOwner : IWin32Window {
    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    public IntPtr Handle { get; private set; }
    public WorkbenchPickerOwner() { Handle = GetForegroundWindow(); }
}
"@ -ReferencedAssemblies System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
try {
    $dialog.Description = '选择素材或工程所在的文件夹'
    $dialog.ShowNewFolderButton = $false
    if ($env:FRAME_PICKER_INITIAL) { $dialog.SelectedPath = $env:FRAME_PICKER_INITIAL }
    $owner = New-Object WorkbenchPickerOwner
    $answer = $dialog.ShowDialog($owner)
    if ($answer -eq [System.Windows.Forms.DialogResult]::OK) {
        $result = @{ cancelled = $false; path = $dialog.SelectedPath }
    } else {
        $result = @{ cancelled = $true }
    }
    [System.IO.File]::WriteAllText($env:FRAME_PICKER_RESULT, ($result | ConvertTo-Json -Compress), (New-Object System.Text.UTF8Encoding($false)))
} finally {
    $dialog.Dispose()
}
'''


def initial_directory(value):
    value=str(value or '').strip().strip('"')
    if not value:return ''
    path=Path(value).expanduser()
    if not path.is_absolute():return ''
    while not path.is_dir() and path!=path.parent:
        path=path.parent
    return str(path) if path.is_dir() else ''


def _run_picker(initial):
    if DESKTOP_PICKER is not None:
        return DESKTOP_PICKER(initial)
    from runtime import launch_external
    exe=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    if not exe.is_file():raise ValueError('未找到 Windows 文件夹选择组件，请使用下方磁盘列表浏览')
    with tempfile.TemporaryDirectory(prefix='frame-folder-') as temp:
        result=Path(temp)/'selection.json'
        env=dict(os.environ,FRAME_PICKER_INITIAL=initial,FRAME_PICKER_RESULT=str(result))
        command=[str(exe),'-NoProfile','-NonInteractive','-STA','-WindowStyle','Hidden','-EncodedCommand',base64.b64encode(SCRIPT.encode('utf-16-le')).decode('ascii')]
        process=launch_external(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=0x08000000)
        try:
            process.communicate(timeout=600)
        except subprocess.TimeoutExpired:
            process.kill();process.communicate()
            raise ValueError('文件夹选择已超时，请重新点击浏览文件夹') from None
        if process.returncode or not result.is_file():
            raise ValueError('Windows 文件夹窗口未能打开，请使用下方磁盘列表浏览')
        return json.loads(result.read_text(encoding='utf-8-sig'))


def choose_native_folder(value=''):
    if os.name!='nt':raise ValueError('系统文件夹窗口仅支持 Windows，请使用下方磁盘列表')
    if not PICKER_LOCK.acquire(blocking=False):raise ValueError('已有文件夹选择窗口打开，请先完成或取消选择')
    try:
        result=_run_picker(initial_directory(value))
        if result.get('cancelled'):return dict(cancelled=True)
        path=Path(result.get('path',''))
        if not result.get('path') or not path.is_dir():raise ValueError('选择的文件夹不存在或无法访问')
        return dict(cancelled=False,path=str(path.resolve()))
    finally:
        PICKER_LOCK.release()
