"""Create output-local replacement media without touching source assets or AE layers."""
from pathlib import Path
import re
import subprocess

from PIL import Image

RASTER = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff', '.gif'}
VIDEO = {'.mp4', '.mov', '.avi', '.gif', '.webp'}


def sequence_files(path, sequence):
    path = Path(path)
    if not sequence:
        return [path]
    match = re.fullmatch(r'(.*?)(\d+)', path.stem)
    if not match:
        raise ValueError('动画序列缺少数字编号：' + path.name)
    prefix, first = match[1], int(match[2])
    frames = []
    for p in path.parent.iterdir():
        m = re.fullmatch(re.escape(prefix) + r'(\d+)', p.stem)
        if p.suffix.lower() == path.suffix.lower() and m and int(m[1]) >= first:
            frames.append((int(m[1]), p))
    frames.sort()
    if not frames or [n for n, _ in frames] != list(range(first, frames[-1][0] + 1)):
        raise ValueError('动画序列缺帧或编号重复：' + path.name)
    return [p for _, p in frames]


def image_geometry(paths):
    size, bounds = None, None
    for path in paths:
        with Image.open(path) as image:
            if getattr(image, 'n_frames', 1) > 1:
                return None
            if size is not None and image.size != size:
                raise ValueError('同一动画序列的画布尺寸不一致：' + path.name)
            size = image.size
            box = image.convert('RGBA').getchannel('A').getbbox()
            if box:
                bounds = box if bounds is None else (min(bounds[0], box[0]), min(bounds[1], box[1]), max(bounds[2], box[2]), max(bounds[3], box[3]))
    if not bounds:
        raise ValueError('替换素材全部透明，无法适配尺寸')
    return size, bounds


def target_geometry(target):
    width, height = int(target['width']), int(target['height'])
    fallback = (0, 0, width, height)
    path = Path(target['path'])
    if path.is_file() and path.suffix.lower() in RASTER:
        try:
            frames = sequence_files(path, not target.get('still', True) and path.suffix.lower() in {'.png', '.jpg', '.jpeg'})
            geometry = image_geometry(frames)
            if geometry and geometry[0] == (width, height):
                return geometry[1], 'alpha'
        except (ValueError, OSError):
            pass
    return fallback, 'canvas'


def placement(source_size, source_box, target_size, target_box, role):
    width, height = target_size
    if role == 'background':
        scale = max(width / source_size[0], height / source_size[1])
        return scale, (width-source_size[0]*scale)/2, (height-source_size[1]*scale)/2
    left, top, right, bottom = target_box
    sl, st, sr, sb = source_box
    scale = min((right-left)/(sr-sl), (bottom-top)/(sb-st))
    dx = (left+right)/2 - (sl+sr)*scale/2
    dy = bottom-sb*scale if role in ('enemy', 'boss') else (top+bottom)/2-(st+sb)*scale/2
    return scale, dx, dy


def prepare_replacement(replacement, target, folder, run_process):
    path = Path(replacement['path'])
    if path.suffix.lower() not in RASTER | VIDEO or not target.get('width') or not target.get('height'):
        return dict(replacement), None
    role = replacement.get('role')
    size = (int(target['width']), int(target['height']))
    folder = Path(folder) / 'adapted' / str(replacement['itemId'])
    folder.mkdir(parents=True, exist_ok=False)
    paths = sequence_files(path, replacement['sequence'])
    geometry = image_geometry(paths) if path.suffix.lower() in RASTER else None
    target_box, target_basis = target_geometry(target)
    result = dict(replacement)
    if geometry:
        source_size, source_box = geometry
        scale, dx, dy = placement(source_size, source_box, size, target_box, role)
        for index, frame in enumerate(paths):
            destination = folder / f'frame_{index:06}.png'
            with Image.open(frame) as im:
                # Premultiplied alpha avoids dark fringes at transparent edges.
                normalized = im.convert('RGBA').convert('RGBa').transform(size, Image.Transform.AFFINE,
                    (1/scale, 0, -dx/scale, 0, 1/scale, -dy/scale), Image.Resampling.BICUBIC).convert('RGBA')
                normalized.save(destination)
        result.update(path=str(folder/'frame_000000.png'), sequence=len(paths)>1)
        basis = 'alpha'
    else:
        probe = subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','csv=p=0:s=x',str(path)], capture_output=True, text=True, timeout=30, creationflags=0x08000000)
        if probe.returncode or not probe.stdout.strip():
            raise ValueError('无法读取动画或视频尺寸：' + path.name)
        source_size = tuple(map(int, probe.stdout.strip().splitlines()[0].split('x')))
        source_box = (0, 0, *source_size)
        scale, dx, dy = placement(source_size, source_box, size, target_box, role)
        sw, sh = max(1, round(source_size[0]*scale)), max(1, round(source_size[1]*scale))
        if role == 'background':
            sw, sh = max(sw,size[0]), max(sh,size[1])
            filters = f'scale={sw}:{sh}:flags=lanczos,format=rgba,crop={size[0]}:{size[1]},setsar=1'
        else:
            sw,sh=min(sw,size[0]),min(sh,size[1])
            x=max(0,min(size[0]-sw,round(dx)));y=max(0,min(size[1]-sh,round(dy)))
            filters=f'scale={sw}:{sh}:flags=lanczos,format=rgba,pad={size[0]}:{size[1]}:{x}:{y}:color=black@0,setsar=1'
        destination = folder/'adapted.mov'
        run_process(['ffmpeg','-nostdin','-n','-i',str(path),'-map','0:v:0','-map','0:a?', '-vf',filters,'-c:v','qtrle','-pix_fmt','argb','-c:a','pcm_s16le',str(destination)], folder/'adapt.log', 3600)
        result.update(path=str(destination), sequence=False)
        basis = 'canvas'
    report = dict(itemId=replacement['itemId'], source=str(path), output=result['path'], sourceSize=source_size,
        targetSize=size, sourceBounds=source_box, targetBounds=target_box, sourceBasis=basis, targetBasis=target_basis,
        scale=scale, offset=[dx,dy], alignment='cover-center' if role=='background' else 'bottom-center' if role in ('enemy','boss') else 'center')
    result['expectedSize'] = list(size)
    return result, report
