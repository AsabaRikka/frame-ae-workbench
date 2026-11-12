"""Pure combination planning and replacement resolution, independent of HTTP state."""
import random
import uuid
from pathlib import Path

def build_plans(slots, count, seed, project_name):
    active = [s for s in slots if s['candidates']]
    if not active:
        raise ValueError('请先为至少一个替换位置添加候选素材')
    total = 1
    for s in active:
        total *= len(s['candidates'])
    if count < 1 or count > 500:
        raise ValueError('每批数量须为 1–500')
    if count > total:
        raise ValueError(f'当前只有 {total} 种不重复搭配，无法生成 {count} 份。请增加候选素材或减少数量。')
    rng=random.Random(seed)
    if total<=2**63-1:indices=rng.sample(range(total),count)
    else:
        indices=[];seen=set()
        while len(indices)<count:
            index=rng.randrange(total)
            if index not in seen:seen.add(index);indices.append(index)
    plans = []
    for i, index in enumerate(indices):
        choices = {}
        for s in active:
            index, pos = divmod(index, len(s['candidates']))
            choices[s['id']] = s['candidates'][pos]['id']
        plans.append(dict(id=uuid.uuid4().hex[:10], name=f'{project_name}_{i + 1:03}', choices=choices))
    return plans


def resolve_plan(plan, slots, assets):
    replacements = []
    for s in slots:
        if not s['candidates']:
            continue
        cid = plan['choices'].get(s['id'])
        candidate = next((c for c in s['candidates'] if c['id'] == cid), None)
        if not candidate:
            raise ValueError('搭配已过期，请重新生成')
        for target, aid in candidate['mapping'].items():
            asset = assets[aid]
            if not Path(asset['path']).is_file():
                raise ValueError('素材不存在：' + asset['name'])
            replacements.append(dict(itemId=int(target), path=asset['path'], sequence=asset['sequence']))
    return replacements
