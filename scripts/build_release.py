"""Allowlisted Windows portable build; never copies workspace data or projects."""
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
VERSION='1.1.0'


def main():
    release=ROOT/'releases'
    work=ROOT/'build' / ('v1-'+time.strftime('%Y%m%d-%H%M%S'))
    release.mkdir(exist_ok=True);work.mkdir(parents=True)
    bundle_name=f'帧场AE工作台-{VERSION}-Windows-x64'
    name='帧场AE工作台'
    stage=work/'dist'
    support=work/'support';support.mkdir()
    ffmpeg=Path(shutil.which('ffmpeg') or '')
    ffprobe=Path(shutil.which('ffprobe') or '')
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise RuntimeError('Build requires FFmpeg and FFprobe')
    licenses=support/'licenses';licenses.mkdir()
    shutil.copy2(Path(sys.base_prefix)/'LICENSE.txt',licenses/'Python-LICENSE.txt')
    for package in ('pillow','pyinstaller','charset-normalizer','pywebview','pythonnet','clr_loader','bottle','proxy_tools','cffi','pycparser','typing_extensions'):
        distribution=importlib.metadata.distribution(package)
        for file in distribution.files:
            if any(word in Path(str(file)).name.lower() for word in ('license','copying','notice')):
                source=distribution.locate_file(file)
                if source.is_file():
                    target=licenses/package/Path(str(file)).name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    ffroot=ffmpeg.parent.parent
    shutil.copy2(ffroot/'LICENSE',licenses/'FFmpeg-GPLv3.txt')
    shutil.copy2(ffroot/'README.txt',licenses/'FFmpeg-build-README.txt')
    config=subprocess.run([str(ffmpeg),'-version'],capture_output=True,text=True,check=True).stdout
    (licenses/'FFmpeg-version-and-build.txt').write_text(config,encoding='utf-8')
    (licenses/'THIRD-PARTY-NOTICES.txt').write_text('''帧场 AE 工作台的第三方组件

Python：PSF License，见 Python-LICENSE.txt。https://www.python.org/
Pillow：见 pillow 目录中的许可文件。https://python-pillow.github.io/
PyInstaller 启动器：见 pyinstaller 目录中的许可及启动器例外。https://pyinstaller.org/
charset-normalizer：见 charset-normalizer 目录中的 MIT 许可。https://github.com/jawah/charset_normalizer

FFmpeg / FFprobe：独立命令行程序，Gyan Windows 静态版本，GPLv3。
完整许可、上游说明与编译参数见本目录 FFmpeg-* 文件。
二进制来源：https://www.gyan.dev/ffmpeg/builds/
FFmpeg 8.1.1 对应源码：https://ffmpeg.org/releases/ffmpeg-8.1.1.tar.xz
第三方库及构建说明：https://github.com/GyanD/codexffmpeg
桌面窗口：pywebview (BSD)、pythonnet (MIT)、clr_loader (MIT)，许可见对应目录。
https://pywebview.flowrl.com/  https://github.com/pythonnet/pythonnet
bottle、proxy_tools、cffi、pycparser、typing_extensions 的许可见对应目录。
Microsoft WebView2：微软专有运行库及加载组件，受其分发许可约束。
https://developer.microsoft.com/en-us/microsoft-edge/webview2/
附带的离线安装器来源：https://go.microsoft.com/fwlink/?linkid=2124701
这些独立组件保留其各自的著作权和许可；未包含 Adobe After Effects、插件、字体或用户工程素材。
''',encoding='utf-8')
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed','--noupx',
          '--name',name,'--icon',str(ROOT/'resources/icons/app.ico'),'--distpath',str(stage),'--workpath',str(work/'analysis'),'--specpath',str(work),
          '--add-data',str(ROOT/'resources/icons/app.ico')+':resources/icons','--add-data',str(ROOT/'frontend')+':frontend','--add-data',str(ROOT/'resources/ae/bridge.jsx')+':resources/ae',
          '--add-data',str(ffmpeg)+':tools','--add-data',str(ffprobe)+':tools',
          '--add-data',str(licenses)+':licenses','--exclude-module','numpy','--exclude-module','psutil',
          '--exclude-module','tkinter','--exclude-module','PySide6','--exclude-module','PyQt6',
          '--exclude-module','PyQt5','--exclude-module','PySide2','--exclude-module','qtpy',
          '--paths',str(ROOT/'src'),'--collect-submodules','PIL',str(ROOT/'scripts/desktop.py')]
    subprocess.run(args,cwd=ROOT,check=True)
    bundle=stage/name
    installer=ROOT/'build/desktop-support/MicrosoftEdgeWebView2RuntimeInstallerX64.exe'
    if not installer.is_file():
        raise RuntimeError('缺少微软官方 WebView2 x64 离线安装器')
    (bundle/'runtime-installers').mkdir()
    shutil.copy2(installer,bundle/'runtime-installers'/installer.name)
    (bundle/'使用说明.txt').write_text((ROOT/'docs/user/desktop.txt').read_text(encoding='utf-8'),encoding='utf-8-sig')
    manifest=dict(product='帧场 AE 工作台',version=VERSION,platform='Windows x64',python=sys.version,
                  desktop='pywebview '+importlib.metadata.version('pywebview')+' / Microsoft WebView2',
                  pillow=importlib.metadata.version('pillow'),pyinstaller=importlib.metadata.version('pyinstaller'),
                  ffmpeg=config.splitlines()[0],files=[])
    for path in sorted(bundle.rglob('*')):
        if path.is_file():
            manifest['files'].append(dict(path=path.relative_to(bundle).as_posix(),size=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (bundle/'release-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    archive=release/(bundle_name+'.zip')
    if archive.exists():
        archive=release/(bundle_name+'-'+time.strftime('%H%M%S')+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as output:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                output.write(path,bundle_name+'/'+path.relative_to(bundle).as_posix())
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.sha256.txt').write_text(digest+'  '+archive.name+'\n',encoding='utf-8')
    print(json.dumps(dict(archive=str(archive),bytes=archive.stat().st_size,sha256=digest,build=str(work)),ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
