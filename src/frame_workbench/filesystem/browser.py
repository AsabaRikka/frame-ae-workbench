"""Read-only directory navigation for the local folder picker."""
import os
import time
from pathlib import Path


def browse_folder(value):
    roots = [Path(f'{letter}:/') for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' if Path(f'{letter}:/').is_dir()] if os.name == 'nt' else [Path('/')]
    result = dict(path='', parent='', folders=[], fileCount=0, roots=[dict(name=str(p), path=str(p)) for p in roots])
    if not str(value).strip():
        return result
    folder = Path(str(value).strip().strip('"')).resolve()
    if not folder.is_dir():
        raise ValueError('文件夹不存在，请检查路径')
    try:
        entries = list(folder.iterdir())
        children = []
        for entry in entries:
            try:
                if entry.is_dir():
                    children.append(dict(name=entry.name, path=str(entry)))
            except OSError:
                continue
    except PermissionError:
        raise ValueError('无法读取这个文件夹，请选择有访问权限的素材目录') from None
    result.update(path=str(folder), parent=str(folder.parent) if folder.parent != folder else '',
                  folders=sorted(children, key=lambda p: p['name'].casefold()), fileCount=len(entries)-len(children))
    return result


def browse_files(value, extensions):
    value=str(value or '').strip().strip('"')
    if value and Path(value).is_file():value=str(Path(value).parent)
    result=browse_folder(value)
    result['files']=[]
    if result['path']:
        result['files']=[dict(name=p.name,path=str(p)) for p in sorted(Path(result['path']).iterdir(),key=lambda p:p.name.casefold()) if p.is_file() and p.suffix.lower() in extensions]
    return result


def discover_projects(value, max_results=200, max_directories=2000):
    value = str(value).strip().strip('"')
    if not value:
        raise ValueError('请先选择工程所在文件夹')
    folder = Path(value).resolve()
    if not folder.is_dir():
        raise ValueError('工程文件夹不存在')
    projects, skipped = [], []
    count, files_seen, truncated = 0, 0, False
    deadline = time.monotonic() + 8
    for directory, children, files in os.walk(folder, followlinks=False, onerror=lambda e: skipped.append(str(e.filename))):
        count += 1
        if count > max_directories or time.monotonic() > deadline:
            truncated = True
            break
        parent = Path(directory)
        children[:] = sorted(name for name in children if not (parent/name).is_symlink() and not (parent/name).is_junction())
        for name in sorted(files):
            files_seen += 1
            if files_seen > 100000 or time.monotonic() > deadline:
                truncated = True
                break
            path = parent/name
            if path.suffix.lower() != '.aep' or path.is_symlink():
                continue
            try:
                info = path.stat()
                relative = path.relative_to(folder)
                backup = any('auto-save' in part.lower() or 'autosave' in part.lower() or '自动保存' in part for part in relative.parts[:-1])
                projects.append(dict(path=str(path), name=path.name, relative=str(relative), backup=backup,
                                     modified=time.strftime('%Y-%m-%d %H:%M', time.localtime(info.st_mtime)), size=info.st_size))
            except OSError:
                skipped.append(str(path))
            if len(projects) >= max_results:
                truncated = True
                break
        if truncated:
            break
    projects.sort(key=lambda p:(p['backup'], len(Path(p['relative']).parts), p['relative'].casefold()))
    return dict(folder=str(folder), projects=projects, truncated=truncated, skipped=len(skipped))
