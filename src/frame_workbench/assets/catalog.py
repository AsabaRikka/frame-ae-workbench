"""Project inventory: discover by structure; names only supply search hints."""
from pathlib import Path
import subprocess
from frame_workbench.media.animation import media_info

CATEGORIES = [
    ('子弹', ('子弹', 'bullet', 'zidan', '弹道', '炮弹')),
    ('死亡 / 受击', ('死亡', 'death', 'dead', 'die', '受击', 'hit')),
    ('升级 / 光效', ('升级', 'levelup', 'upgrade', '光效', '特效', '爆炸', 'effect', '增加队友')),
    ('箱子 / 障碍', ('集装箱', '箱子', '宝箱', '箱', '笼子', '障碍', 'container', 'chest')),
    ('战车 / 武器', ('战车', '载具', '坦克', 'tank', 'vehicle', '炮', '武器', '滑板')),
    ('BOSS', ('boss', 'erlangshen')),
    ('小怪 / 角色', ('小怪', '怪物', 'xiaoguai', 'jiangs', '人物', '角色', 'enemy', 'tianbing')),
    ('背景 / 场景', ('背景', 'bg.', 'background', '桥', '道路', '场景')),
    ('数字 / 门 / 界面', ('门', '数字', 'ui', '按钮', '胜利', '失败', '手指', '血条')),
]


def category(entry):
    if entry.get('hasVideo') is False:
        return '声音'
    # Prefer its own name, then its immediate use; do not let an ancestor
    # such as "背景" relabel every object in the scene.
    for text in (entry['name'], ' '.join(entry.get('uses', []))):
        for label, words in CATEGORIES:
            if any(w in text.lower() for w in words):
                return label
    return '其他素材'


def descendants(scan, item_id):
    comps = {c['id']: c for c in scan.get('comps', [])}
    found, pending = set(), [item_id]
    while pending:
        for layer in comps.get(pending.pop(), {}).get('layers', []):
            source = layer.get('sourceId')
            if source is not None and source not in found:
                found.add(source)
                pending.append(source)
    found.discard(item_id)
    return found


def validate_selection(scan, selected):
    entries = {e['id']: e for e in inventory(scan)}
    ids = set(map(int, selected))
    for item_id in ids:
        entry = entries.get(item_id)
        if not entry or not entry['replaceable']:
            raise ValueError('这个项目不能直接用文件替换，请选择内部源素材')
        overlap = descendants(scan, item_id) & ids
        if overlap:
            other = entries[next(iter(overlap))]['name']
            raise ValueError(f'“{entry["name"]}”包含“{other}”。请只替换整个组合，或只替换内部素材，不能同时选择。')


def inventory(scan):
    result = []
    comps = {c['id']:c for c in scan.get('comps', [])}
    for item in scan.get('items', []) + scan.get('comps', []):
        entry = {k: v for k, v in item.items() if k != 'layers'}
        entry.update(media_info(item))
        refs = item.get('references', [])
        visited, pending, ancestors = set(), [r['compId'] for r in refs if 'compId' in r], []
        while pending:
            parent = pending.pop(0)
            if parent in visited or parent not in comps:
                continue
            visited.add(parent)
            ancestors.append(comps[parent]['name'])
            pending.extend(r['compId'] for r in comps[parent].get('references', []) if 'compId' in r)
        kind = item.get('sourceKind', 'file')
        control = kind in ('solid', 'placeholder')
        is_comp = kind == 'composition'
        entry.update(category=category(item), kind='group' if is_comp else 'control' if control else 'source',
                     replaceable=bool(refs) and (is_comp or kind == 'file'),
                     referenceCount=len(refs), activeReferences=sum(bool(r.get('enabled')) and not r.get('guide') for r in refs),
                     children=list(dict.fromkeys(l['sourceId'] for l in item.get('layers', []) if l.get('sourceId') is not None)))
        entry['contexts'] = ancestors
        if entry['category'] == '其他素材':
            entry['category'] = category(dict(name='', uses=ancestors))
        entry['reason'] = '整组替换：内部动画、数字和特效会一起被新素材取代。' if is_comp and refs else '未被其他合成引用，只供查看。' if is_comp else '控制层 / 纯色 / 占位项，请在 AE 中编辑。' if control else '没有图层引用，替换不会改变当前画面。' if not refs else '同一个源素材的所有引用会一起替换，保留原图层动画。'
        result.append(entry)
    for layer in scan.get('procedural', []):
        result.append(dict(id=f"layer-{layer['compId']}-{layer['layerIndex']}", name=layer['layerName'],
                           kind='procedural', category='文字 / 形状', replaceable=False,
                           uses=[layer['compName']], references=[layer], referenceCount=1,
                           reason='这是 AE 内部文字或形状。可查看所在合成，或在 AE 中编辑；没有独立素材文件。',
                           parentId=layer['compId'], text=layer.get('text', ''), children=[]))
    return result


def finalize_previews(scan, directory):
    """AE may finish writing after saveFrameToPng returns; verify on disk."""
    from PIL import Image
    for entry in scan['items'] + scan['comps']:
        path = Path(directory) / f"{entry['id']}.png"
        try:
            if entry.get('previewEncoding') == 'png-direct-v2':
                raw = Path(entry['previewPath'])
                with Image.open(raw) as image:
                    rgba = image.convert('RGBA')
                    # AE 2022's direct PNG contains premultiplied RGB. Browsers expect straight alpha.
                    straight = Image.frombytes('RGBa', rgba.size, rgba.tobytes()).convert('RGBA')
                    straight.save(path)
                entry['previewEncoding'] = 'rgba-png-v2'
            frames = sorted(list(Path(directory).glob(f"preview-{entry['id']}_*.tif")) +
                            list(Path(directory).glob(f"preview-{entry['id']}-*_*.tif")), key=lambda p:p.stat().st_mtime, reverse=True)
            if frames and entry.get('previewEncoding') not in ('rgba-v1', 'rgba-png-v2'):
                # Older caches contain TIFF with an unspecified fourth (alpha) channel.
                conversion = subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-i', str(frames[0]),
                                             '-frames:v', '1', '-pix_fmt', 'rgba', str(path)],
                                            capture_output=True, timeout=30, creationflags=0x08000000)
                if conversion.returncode:
                    raise OSError('预览图片转换失败')
                entry['previewEncoding'] = 'rgba-v1'
            if not path.is_file():
                if entry.get('previewPath'):
                    raise OSError('预览图片不存在')
                continue
            with Image.open(path) as image:
                image.load()
                entry['previewBlank'] = not image.convert('RGBA').getchannel('A').getbbox()
                thumb = image.copy()
                thumb.thumbnail((640, 480))
                thumb.save(path.with_name(f"{entry['id']}-thumb.png"))
            entry['previewPath'] = str(path)
            entry.pop('previewError', None)
        except (OSError, subprocess.SubprocessError) as exc:
            entry.pop('previewPath', None)
            entry.pop('previewBlank', None)
            entry['previewError'] = str(exc)
    return scan
