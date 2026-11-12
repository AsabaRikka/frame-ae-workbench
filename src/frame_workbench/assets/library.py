"""Read candidate files and group image sequences without changing originals."""
import hashlib
import re
from pathlib import Path

EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.mov', '.avi', '.wav', '.mp3'}

def uid(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:16]


def collect_assets(folder, allow_file=False):
    folder = Path(folder).resolve()
    single=allow_file and folder.is_file()
    if not single and not folder.is_dir():
        raise ValueError('素材目录不存在')
    files = [folder] if single and folder.suffix.lower() in EXTENSIONS else [] if single else sorted(p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in EXTENSIONS)
    groups, singles = {}, []
    for p in files:
        match = re.match(r'^(.*?[_\-])(\d{2,})$', p.stem)
        if not single and p.suffix.lower() in {'.png', '.jpg', '.jpeg'} and match:
            key = (str(p.parent), match[1], p.suffix.lower())
            groups.setdefault(key, []).append(p)
        else:
            singles.append([p])
    bundles = singles + list(groups.values())
    assets = []
    for group in bundles:
        group.sort(key=lambda f: int(re.search(r'(\d+)$', f.stem)[1]) if re.search(r'(\d+)$', f.stem) else 0)
        p = group[0]
        sequence = len(group) > 1
        numbers = [int(re.search(r'(\d+)$', f.stem)[1]) for f in group] if sequence else []
        gaps = bool(numbers and numbers != list(range(numbers[0], numbers[-1] + 1)))
        width = height = 0
        try:
            from PIL import Image
            with Image.open(p) as im:
                width, height = im.size
        except Exception:
            pass
        name = re.sub(r'[_\-]\d+$', '', p.stem) if sequence else p.stem
        assets.append(dict(id=uid(str(p)+'|single') if single else uid(p), name=name, path=str(p), extension=p.suffix.lower(),
                           sequence=sequence, frames=len(group), width=width, height=height,
                           folder=p.parent.name, gaps=gaps, size=sum(f.stat().st_size for f in group)))
    return assets
