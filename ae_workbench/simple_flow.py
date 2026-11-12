"""Folder-based replacements, independent of the legacy manual configuration."""
from pathlib import Path
import re

ROLES = {'background': '背景', 'enemy': '小怪', 'boss': 'BOSS'}
ACTION_PATTERNS = {
    'death': r'死亡|倒地|(?:^|[^a-z])(die|death|dead)(?:[^a-z]|$)',
    'attack': r'攻击|射击|(?:^|[^a-z])(attack|atk|gongji|shoot)(?:[^a-z]|$)',
    'move': r'移动|行走|奔跑|(?:^|[^a-z])(move|walk|run)(?:[^a-z]|$)',
    'idle': r'待机|站立|(?:^|[^a-z])(idle|stand)(?:[^a-z]|$)',
}
ACTION_NAMES = {'death': '死亡', 'attack': '攻击', 'move': '移动', 'idle': '待机', 'appearance': '形象', 'background': '背景'}
VISUAL = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.mov', '.avi'}


def action_of(text):
    text = text.lower()
    found = [action for action, pattern in ACTION_PATTERNS.items() if re.search(pattern, text)]
    return found[0] if len(found) == 1 else None


def target_role(item):
    if not item.get('uses'):
        return None
    name = item['name'].lower()
    uses = ' '.join(item['uses']).lower()
    if re.search(r'boss|首领|头目', name + ' ' + uses):
        return 'boss'
    if re.search(r'小怪|敌人|enemy|xiaoguai|tianbing', name + ' ' + uses):
        # Screenshots in enemy-named compositions must not become character slots.
        if item.get('still') and not re.search(r'小怪|敌人|enemy|xiaoguai|tianbing', name):
            return None
        return 'enemy'
    if re.search(r'背景|background|(?:^|[^a-z])bg(?:[^a-z]|$)', name):
        return 'background'
    return None


def target_action(item):
    return action_of(item['name']) or action_of(' '.join(item.get('uses', []))) or ('appearance' if item.get('still') else None)


def candidate_groups(role, folder, assets):
    if role == 'background':
        # Catch the exact mistake the previous UI allowed: a named actor animation as a background.
        invalid = [a['name'] for a in assets if action_of(a['name'])]
        if invalid:
            raise ValueError('这个目录含角色动作素材，请放到“小怪”或“BOSS”中；背景请选择背景图片或视频目录。')
        return [dict(name=a['name'], actions={'background': a}) for a in assets]
    groups = {}
    for asset in assets:
        relative = Path(asset['path']).relative_to(folder)
        action = action_of(asset['name']) or next((action_of(p) for p in reversed(relative.parts[:-1]) if action_of(p)), None)
        action = action or 'move'
        directories = [p for p in relative.parts[:-1] if not action_of(p)]
        if directories:
            key = '/'.join(directories)
        else:
            key = asset['name'].lower()
            for pattern in ACTION_PATTERNS.values():
                key = re.sub(pattern, '_', key)
            key = key.strip(' _-') or Path(folder).name
        group = groups.setdefault(key, dict(name=key, actions={}))
        if action in group['actions']:
            raise ValueError(f'“{key}”里有多个{ACTION_NAMES[action]}素材，无法确定对应关系。请把不同角色分到独立子文件夹。')
        group['actions'][action] = asset
    return list(groups.values())


def analyze_folders(scan, folders, collect):
    if not scan:
        raise ValueError('请先选择并扫描 AE 工程')
    slots, imported, roles, issues = [], [], [], []
    for role, label in ROLES.items():
        path = str(folders.get(role, '')).strip().strip('"')
        result = dict(id=role, name=label, path=path, count=0, candidates=[], retained=[], error='')
        roles.append(result)
        if not path:
            continue
        try:
            folder = Path(path).resolve()
            assets = [a for a in collect(folder) if a['extension'] in VISUAL]
            if not assets:
                raise ValueError('文件夹里没有支持的图片、PNG 序列或视频')
            if any(a.get('gaps') for a in assets):
                raise ValueError('动画序列编号不连续，请补齐中间缺失的图片')
            imported.extend(assets)
            targets = [item for item in scan['items'] if target_role(item) == role]
            if not targets:
                raise ValueError(f'未找到正在使用的{label}素材。请使用高级设置逐项指定替换位置。')
            by_action = {}
            for item in targets:
                action = 'background' if role == 'background' else target_action(item)
                if action:
                    by_action.setdefault(action, []).append(item)
            groups = candidate_groups(role, folder, assets)
            candidates = []
            matched_sets = []
            for group in groups:
                mapping, details, unused = {}, [], []
                for action, asset in group['actions'].items():
                    matched = by_action.get(action, [])
                    if not matched:
                        unused.append(ACTION_NAMES[action])
                        continue
                    # Multiple independent sprites with the same action are ambiguous.
                    paths = {i['path'] for i in matched}
                    if len(paths) > 1:
                        raise ValueError(f'工程中有 {len(paths)} 套不同的{ACTION_NAMES[action]}素材，无法自动确定要改哪一套。请使用高级设置逐项替换。')
                    for item in matched:
                        mapping[str(item['id'])] = asset['id']
                        details.append(dict(target=item['name'], targetId=item['id'], action=ACTION_NAMES[action], asset=asset['name'], assetId=asset['id'], frames=asset['frames'], sequence=asset['sequence'], targetWidth=item.get('width'), targetHeight=item.get('height')))
                if not mapping:
                    raise ValueError(f'“{group["name"]}”没有能对应到工程的动作，请检查文件名是否包含 move / attack / die 或移动 / 攻击 / 死亡。')
                candidate = dict(id='folder-' + '-'.join(sorted(mapping.values())), name=group['name'], mapping=mapping)
                candidates.append(candidate)
                matched_sets.append(set(mapping))
                result['candidates'].append(dict(**candidate, details=details, unused=unused))
            if any(targets != matched_sets[0] for targets in matched_sets):
                raise ValueError('这个目录中不同角色的动作不齐全。请让每个角色提供相同的动作，或先选择一个角色的文件夹。')
            ids = [int(x) for x in matched_sets[0]]
            result['retained'] = [dict(name=i['name'], action=ACTION_NAMES.get(target_action(i), '其他'), missing=i['missing']) for i in targets if i['id'] not in ids]
            result['count'] = len(candidates)
            slots.append(dict(id=role, name=label, targets=ids, candidates=candidates))
        except (ValueError, OSError) as exc:
            result['error'] = str(exc)
            issues.append(f'{label}：{exc}')
    total = 1 if slots and not issues else 0
    for slot in slots:
        total *= len(slot['candidates'])
    covered = {target for slot in slots for target in slot['targets']}
    missing = [dict(id=i['id'], name=i['name'], path=i['path']) for i in scan['items'] if i['missing'] and i['id'] not in covered]
    return dict(roles=roles, slots=slots, assets=imported, total=total, issues=issues, missing=missing,
                canGenerate=bool(slots) and not issues, canRender=bool(slots) and not issues and not missing)
