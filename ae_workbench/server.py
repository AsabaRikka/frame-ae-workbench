from __future__ import annotations

import hashlib
import itertools
import json
import mimetypes
import os
import random
import re
import shutil
import socket
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from simple_flow import ROLES, action_of, analyze_folders, target_role
from folder_browser import browse_folder, browse_files, discover_projects
from native_folder import choose_native_folder, PICKER_LOCK
import export_settings
from size_fit import prepare_replacement
from catalog import inventory, validate_selection, finalize_previews
import runtime
from animation import AnimationPreviews
from generation import Generation

ROOT = runtime.RESOURCE_ROOT
DATA = runtime.DATA
OUTPUT = runtime.OUTPUT
DATA.mkdir(parents=True, exist_ok=True)
OUTPUT.mkdir(parents=True, exist_ok=True)
PORT = 8518
AE = runtime.after_effects()
RENDER = AE.with_name('aerender.exe')
EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.mov', '.avi', '.wav', '.mp3'}
LOCK = threading.RLock()
AE_LOCK = threading.Lock()
BUSY = False
SCANNING = False
SHUTTING_DOWN = False
DESKTOP_ACTIVATE = None
CANCEL = threading.Event()
STATE_FILE = DATA / 'workspace.json'


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return default


def write_json(path, value):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


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


STATE = read_json(STATE_FILE) or (read_json(ROOT / 'data' / 'workspace.json') if not runtime.FROZEN and 'FRAME_WORKBENCH_HOME' not in os.environ else None) or dict(project='', assets=[], scan=None, slots=[], plans=[], batches=[], comp='', notice='')
for batch in STATE['batches']:
    for row in batch['rows']:
        if row['status'] in ('running', 'waiting'):
            row['status'] = 'interrupted'
            row['error'] = '程序上次退出，需手动重试'


def save():
    write_json(STATE_FILE, STATE)


PROJECT_FIELDS = ('project', 'scan', 'slots', 'plans', 'simple', 'comp', 'catalogChoices', 'catalogPlans', 'catalogPlanSignature')


def archive_project():
    if not STATE.get('project'):
        return
    folder = DATA / 'projects'
    folder.mkdir(exist_ok=True)
    write_json(folder / (uid(STATE['project'].lower()) + '.json'), {k: STATE[k] for k in PROJECT_FIELDS if k in STATE})


def project_list():
    return [dict(key=p.stem, project=v['project'], name=Path(v['project']).parent.name)
            for p in (DATA/'projects').glob('*.json') if (v := read_json(p)) and v.get('scan')]


def activate_project(project, scan=None):
    archive_project()
    previous = read_json(DATA/'projects'/(uid(str(project).lower())+'.json'), {})
    for key in PROJECT_FIELDS:
        STATE.pop(key, None)
    STATE.update(project=str(project), scan=None, slots=[], plans=[], comp='', catalogChoices={})
    STATE.update(previous)
    if scan:
        adopt_scan(scan)
    initialize_simple()
    archive_project()
    save()


def catalog_slots():
    choices = STATE.get('catalogChoices', {})
    validate_selection(STATE['scan'], choices)
    entries = {str(e['id']): e for e in inventory(STATE['scan'])}
    assets = {a['id']: a for a in STATE['assets']}
    slots = []
    for target, choice in choices.items():
        ids = choice['assetIds']
        selected = choice.get('selectedIds', ids if choice.get('selected') == '*' else [choice.get('selected')])
        if not selected:continue
        if any(a not in ids or a not in assets for a in selected):
            raise ValueError('新素材已变化，请重新选择文件夹')
        entry = entries[target]
        slots.append(dict(id='catalog-'+target, name=entry['name'], targets=[int(target)],
                          candidates=[dict(id=aid, name=assets[aid]['name'], mapping={target:aid}) for aid in selected]))
    return slots


def catalog_plan_signature():
    return uid(json.dumps([STATE['project'],STATE.get('scan',{}).get('scannedAt'),catalog_slots()],sort_keys=True,ensure_ascii=False))


def validate_catalog_plans(plans):
    if not isinstance(plans,list) or not 1<=len(plans)<=500:raise ValueError('组合计划数量须为 1–500')
    slots=catalog_slots();assets={a['id']:a for a in STATE['assets']};seen=set();ids=set()
    for plan in plans:
        if not isinstance(plan,dict) or not isinstance(plan.get('choices'),dict):raise ValueError('组合计划格式无效')
        if not isinstance(plan.get('id'),str) or not re.fullmatch(r'[a-f0-9]{10}',plan['id']) or plan['id'] in ids:raise ValueError('组合计划编号无效或重复')
        ids.add(plan['id'])
        if not isinstance(plan.get('name'),str) or not plan['name'].strip() or len(plan['name'])>150:raise ValueError('请填写不超过 150 字的作品名称')
        if set(plan['choices'])!={s['id'] for s in slots}:raise ValueError('替换位置已变化，请重新生成组合计划')
        replacements=resolve_plan(plan,slots,assets)
        signature=tuple(sorted((r['itemId'],r['path'],bool(r.get('sequence'))) for r in replacements))
        if signature in seen:raise ValueError('组合计划中存在重复搭配，请调整后保存')
        seen.add(signature)
    return plans


def update_simple(folders):
    report = analyze_folders(STATE['scan'], folders, collect_assets)
    existing = {a['id']: a for a in STATE['assets']}
    existing.update({a['id']: a for a in report.pop('assets')})
    STATE['assets'] = list(existing.values())
    STATE['simple'] = dict(folders={key: str(folders.get(key, '')).strip().strip('"') for key in ROLES}, report=report)
    save()
    return STATE['simple']


def initialize_simple():
    if 'simple' in STATE or not STATE.get('scan'):
        return
    write_json(DATA / ('before-simple-' + time.strftime('%Y%m%d-%H%M%S') + '.json'), STATE)
    folders = dict.fromkeys(ROLES, '')
    assets = {a['id']: a for a in STATE['assets']}
    for slot in STATE['slots']:
        if slot['id'] not in ROLES or not slot['candidates']:
            continue
        selected = [assets[aid] for c in slot['candidates'] for aid in c['mapping'].values() if aid in assets]
        parents = {str(Path(a['path']).parent) for a in selected}
        if len(parents) != 1:
            continue
        if slot['id'] == 'background' and any(action_of(a['name']) for a in selected):
            continue
        folders[slot['id']] = parents.pop()
    update_simple(folders)


def adopt_scan(scan):
    if not scan or not scan.get('ok'):
        raise ValueError((scan or {}).get('error', '未收到 AE 扫描结果'))
    STATE['scan'] = scan
    STATE['catalogPlans']=[]
    STATE.pop('catalogPlanSignature',None)
    STATE['project'] = scan['project']
    comps = scan['comps']
    if comps:
        chosen = choose_output_comp(comps)
        STATE['comp'] = chosen['name']
    if not STATE['slots']:
        patterns = [('背景', 'background', ['背景']), ('普通敌人', 'enemy', ['xiaoguai', 'jiangs', 'tianbing', '小怪']), ('BOSS', 'boss', ['erlangshen', 'zz_jyg', 'boss'])]
        for name, key, words in patterns:
            targets = [x['id'] for x in scan['items'] if any(w in (x['name'] + ' ' + ' '.join(x['uses'])).lower() for w in words)]
            if targets:
                STATE['slots'].append(dict(id=key, name=name, targets=targets, candidates=[]))
    if 'simple' in STATE:
        update_simple(STATE['simple']['folders'])
    save()


def choose_output_comp(comps):
    roots = [c for c in comps if 'uses' in c and not c['uses']]
    choices = roots or comps
    for name in ('Finish', '总合成', '最终合成', 'Main', 'Final'):
        match = next((c for c in choices if c['name'].lower() == name.lower()), None)
        if match:
            return match
    return max(choices, key=lambda c: c['duration'])


initial = read_json(DATA / 'initial_scan.json')
if initial and initial.get('ok') and not STATE['scan']:
    adopt_scan(initial)


def run_bridge(payload, timeout=180):
    if not AE.is_file():
        raise ValueError('未找到 AE，请检查安装路径')
    token = uuid.uuid4().hex
    result = DATA / (token + '.json')
    payload['result'] = str(result)
    payload['expires'] = int((time.time() + timeout) * 1000)
    script = DATA / (token + '.jsx')
    script.write_text('var JOB = ' + json.dumps(payload, ensure_ascii=True) + ';\n' + (ROOT / 'bridge.jsx').read_text(encoding='utf-8'), encoding='utf-8-sig')
    with AE_LOCK, runtime.ae_session():
        executable = AE.with_suffix('.com') if AE.with_suffix('.com').is_file() else AE
        with (DATA / (token + '.log')).open('w', encoding='utf-8') as log:
            runtime.launch_external([str(executable), '-r', str(script)], stdout=log, stderr=subprocess.STDOUT, creationflags=0x08000000)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if result.exists():
                value = read_json(result)
                if value is None:
                    time.sleep(.2)
                    continue
                if not value.get('ok'):
                    raise ValueError(value.get('error', 'AE 操作失败'))
                return value
            time.sleep(.5)
    raise ValueError('等待 AE 超时。请检查 AE 弹窗，并在“脚本与表达式”中允许脚本写入文件。')


def validate_slots(slots):
    if not STATE['scan']:
        raise ValueError('请先完成 AE 工程扫描')
    targets = {x['id'] for x in STATE['scan']['items']}
    targets.update(x['id'] for x in STATE['scan'].get('comps', []) if x.get('references'))
    assets = {x['id']: x for x in STATE['assets']}
    used = set()
    for slot in slots:
        if not slot.get('name', '').strip() or not slot.get('targets'):
            raise ValueError('每个替换位置都需要名称和目标素材')
        if used.intersection(slot['targets']):
            raise ValueError('同一个源素材不能同时属于两个替换位置')
        used.update(slot['targets'])
        if not set(slot['targets']).issubset(targets):
            raise ValueError('替换目标已变化，请重新配置')
        for candidate in slot['candidates']:
            if set(candidate['mapping']) != {str(x) for x in slot['targets']}:
                raise ValueError('素材套装必须为每个目标指定素材')
            if any(a not in assets for a in candidate['mapping'].values()):
                raise ValueError('素材已不存在，请重新选择')
            signature = tuple(sorted(candidate['mapping'].items()))
            if sum(tuple(sorted(c['mapping'].items())) == signature for c in slot['candidates']) > 1:
                raise ValueError('同一个位置不能重复添加完全相同的候选')


def build_plans(slots, count, seed):
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
        plans.append(dict(id=uuid.uuid4().hex[:10], name=f'{Path(STATE["project"]).stem}_{i + 1:03}', choices=choices))
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


def run_process(command, logfile, timeout):
    with open(logfile, 'a', encoding='utf-8') as out:
        proc = runtime.launch_external(command, stdout=out, stderr=subprocess.STDOUT, creationflags=0x08000000)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise ValueError('执行超时，日志：' + str(logfile))
        if code:
            raise ValueError('执行失败，日志：' + str(logfile))


def render_motion(project, entry, folder):
    global SCANNING
    with LOCK:
        if BUSY or SCANNING or SHUTTING_DOWN:
            raise ValueError('AE 正在处理任务，请稍后重试动画预览')
        SCANNING=True
    try:
        return run_bridge(dict(action='motion',project=project,itemId=entry['id'],previewDir=str(folder)),timeout=600)
    finally:
        with LOCK:SCANNING=False


ANIMATIONS=AnimationPreviews(DATA/'animations',run_process,render_motion)
GENERATION=Generation(DATA/'generation')


def selected_entry(data):
    if data.get('project')!=STATE.get('project'):
        raise ValueError('当前工程已切换，请重新打开素材')
    entry=next((e for e in inventory(STATE.get('scan') or {}) if str(e['id'])==str(data.get('target'))),None)
    if not entry:raise ValueError('素材不存在，请重新扫描')
    return entry


def worker(batch):
    global BUSY
    try:
        with runtime.ae_session():
            worker_locked(batch)
    except Exception as exc:
        with LOCK:
            for row in batch['rows']:
                if row['status'] in ('waiting','running'):
                    row.update(status='failed',stage='失败',error=str(exc))
            save()
    finally:
        BUSY=False


def worker_locked(batch):
    global BUSY
    try:
        for row in batch['rows']:
            if CANCEL.is_set():
                break
            if row['status'] == 'done':
                continue
            with LOCK:
                row.update(status='running', error='', stage='生成 AE 工程')
                save()
            try:
                # Every retry receives a new folder, so a partial output is never overwritten.
                folder = OUTPUT / batch['id'] / (row['id'] + '_' + uuid.uuid4().hex[:6])
                folder.mkdir(parents=True)
                project = folder / 'project.aep'
                applied, adjustments = [], []
                if batch.get('sizeTargets'):
                    row['stage'] = '适配素材尺寸'
                    with LOCK:
                        save()
                for replacement in row['replacements']:
                    target = batch.get('sizeTargets', {}).get(str(replacement['itemId']))
                    if target:
                        prepared, adjustment = prepare_replacement(replacement, target, folder, run_process)
                        applied.append(prepared)
                        if adjustment:
                            adjustments.append(adjustment)
                    else:
                        applied.append(replacement)
                row['stage'] = '生成 AE 工程'
                row['sizeAdjustments'] = adjustments
                result = run_bridge(dict(action='replace', project=batch['project'], replacements=applied, output=str(project), allowMissing=not batch['render']))
                if not project.is_file() or project.stat().st_size == 0:
                    raise ValueError('AE 未生成有效的工程文件，请查看日志')
                row['project'] = str(project)
                row['missing'] = result.get('missing', [])
                write_json(folder / 'replacement-report.json', dict(project=str(project), replacements=row['replacements'], appliedReplacements=applied, sizeAdjustments=adjustments, missing=row['missing'], renderRequested=batch['render']))
                if batch['render']:
                    row['stage'] = 'AE 渲染中'
                    with LOCK:
                        save()
                    intermediate = render_intermediate(project, batch['comp'], folder)
                    row['stage'] = '编码 MP4'
                    video = folder / 'video.mp4'
                    settings=batch.get('videoSettings')
                    write_json(folder/'video-settings.json',export_settings.normalize(settings))
                    run_process(export_settings.encode_command(intermediate,video,settings), folder / 'encode.log', 3600)
                    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(video)], capture_output=True, text=True, timeout=30, creationflags=0x08000000)
                    if probe.returncode:raise ValueError('无法校验导出视频')
                    row['videoInfo']=export_settings.validate_probe(json.loads(probe.stdout),settings)
                    row['video'] = str(video)
                    intermediate.unlink()
                row.update(status='done', stage=(f'工程已生成 · 仍有 {len(row["missing"])} 项源素材待补齐' if row['missing'] else '完成'))
            except Exception as exc:
                row.update(status='failed', error=str(exc), stage='失败')
            with LOCK:
                save()
        with LOCK:
            for row in batch['rows']:
                if row['status'] == 'waiting':
                    row['status'] = 'interrupted'
            save()
    finally:
        BUSY = False


def render_intermediate(project, comp, folder, timeout=7200):
    run_process([str(RENDER), '-project', str(project), '-comp', comp, '-output', str(folder / 'render.mov')], folder / 'render.log', timeout)
    # AE adjusts extensions to its actual output module (e.g. QuickTime).
    videos = [p for p in folder.glob('render.*') if p.suffix.lower() in {'.mov', '.avi', '.mp4', '.mxf', '.mpg'} and p.stat().st_size > 0]
    if len(videos) != 1:
        raise ValueError('AE 未生成单个视频文件，请检查 render.log 与输出模块；当前 MVP 不支持渲染为图片序列')
    return videos[0]


def enqueue_export(plans, slots, render, comp, selected=None, origin='advanced'):
    global BUSY
    if BUSY or SCANNING:
        raise ValueError('已有任务在运行')
    if not STATE['scan'] or not plans:
        raise ValueError('请先扫描工程并选择新素材')
    validate_slots(slots)
    if render and (not RENDER.is_file() or not shutil.which('ffmpeg') or not shutil.which('ffprobe')):
        raise ValueError('渲染需要 aerender、ffmpeg 和 ffprobe')
    matches = [c for c in STATE['scan']['comps'] if c['name'] == comp]
    if render and len(matches) != 1:
        raise ValueError('输出合成必须存在且名称唯一，请先在 AE 中重命名')
    rows, signatures = [], set()
    selected = set(selected if selected is not None else [p['id'] for p in plans])
    assets = {a['id']: a for a in STATE['assets']}
    for plan in plans:
        if plan['id'] not in selected:
            continue
        replacements = resolve_plan(plan, slots, assets)
        for replacement in replacements:
            source = next(i for i in STATE['scan']['items'] + STATE['scan']['comps'] if i['id'] == replacement['itemId'])
            slot = next(s for s in slots if replacement['itemId'] in s['targets'])
            replacement['role'] = None if source.get('sourceKind') == 'composition' else slot['id'] if slot['id'] in ROLES else target_role(source)
        sig = tuple(sorted((r['itemId'], r['path']) for r in replacements))
        if sig in signatures:
            raise ValueError('搭配存在重复')
        signatures.add(sig)
        covered = {r['itemId'] for r in replacements}
        missing = [i['name'] for i in STATE['scan']['items'] if i['missing'] and i['id'] not in covered]
        if render and missing:
            raise ValueError(f'还有 {len(missing)} 项原素材缺失，暂不能导出完整视频。请先点击“生成替换工程”，之后补齐素材再导出视频。')
        rows.append(dict(id=plan['id'], name=plan['name'], replacements=replacements, status='waiting', stage='等待', error='', missing=missing))
    if not rows:
        raise ValueError('未选择任何搭配')
    settings=export_settings.normalize(STATE.get('videoSettingsByProject',{}).get(STATE['project']))
    batch = dict(id=time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:4], project=STATE['project'], comp=comp, render=render, rows=rows, origin=origin, videoSettings=settings, created=time.strftime('%Y-%m-%d %H:%M:%S'))
    batch['sizeTargets'] = {str(i['id']):dict(i) for i in STATE['scan']['items'] + STATE['scan']['comps'] if i['id'] in {r['itemId'] for row in rows for r in row['replacements']}}
    STATE['batches'].insert(0, batch)
    STATE['comp'] = comp
    save()
    BUSY = True
    CANCEL.clear()
    threading.Thread(target=worker, args=(batch,), daemon=True).start()
    return dict(ok=True, batchId=batch['id'])


def dispatch(action, data):
    global BUSY, AE, RENDER, SHUTTING_DOWN
    if SHUTTING_DOWN:
        raise ValueError('工作台正在退出，请等重新启动后再操作')
    if action == '/api/desktop-activate':
        if DESKTOP_ACTIVATE is None:
            raise ValueError('此工作区已由后台模式运行，请先退出后台再打开桌面版')
        threading.Thread(target=DESKTOP_ACTIVATE,daemon=True).start()
        return dict(ok=True)
    if action == '/api/video-settings':
        if data.get('project')!=STATE.get('project'):
            raise ValueError('当前工程已切换，请重新打开视频设置')
        settings=export_settings.normalize(data.get('settings'))
        STATE.setdefault('videoSettingsByProject',{})[STATE['project']]=settings
        save()
        return settings
    if action == '/api/generation-settings':
        return GENERATION.save_config(data)
    if action == '/api/generate':
        entry=selected_entry(data)
        if data.get('animationId') and data.get('reference',True):
            preview=ANIMATIONS.jobs.get(data['animationId'],{})
            if preview.get('project')!=STATE['project'] or str(preview.get('entry',{}).get('id'))!=str(entry['id']) or preview.get('player')!='frames':
                raise ValueError('参考动画已变化，请重新打开预览')
            path=ANIMATIONS.frame(data['animationId'],int(data.get('referenceFrame',0)))
            from PIL import Image
            with Image.open(path) as image:blank=not image.convert('RGBA').getchannel('A').getbbox()
            entry=dict(entry,previewPath=str(path),previewBlank=blank)
        return GENERATION.start(STATE['project'],entry,data)
    if action == '/api/generation-resume':
        return GENERATION.resume(data.get('id'))
    if action == '/api/generation-apply':
        entry=selected_entry(data)
        job=GENERATION.jobs.get(data.get('id'),{})
        if job.get('project')!=STATE['project'] or str(job.get('target'))!=str(entry['id']):
            raise ValueError('生成结果不属于当前素材，请返回原工程使用')
        path=GENERATION.output(job['id'])
        return dispatch('/api/catalog-select',dict(project=STATE['project'],target=entry['id'],folder=str(path.parent)))
    if action == '/api/animation':
        entry=selected_entry(data) if not data.get('assetId') else next((dict(a,still=not a.get('sequence') and a.get('extension') not in {'.gif','.webp'},fps=30) for a in STATE['assets'] if a['id']==data['assetId']),None)
        if entry is None:raise ValueError('候选素材不存在')
        return ANIMATIONS.start(STATE['project'],entry)
    if action == '/api/settings':
        if BUSY or SCANNING:
            raise ValueError('请等当前 AE 任务结束后再修改环境设置')
        AE=runtime.save_ae(data.get('aePath',''))
        RENDER=AE.with_name('aerender.exe')
        return runtime.environment(AE)
    if action == '/api/shutdown':
        if PICKER_LOCK.locked():
            raise ValueError('请先完成或取消系统文件夹选择，再退出工作台')
        if BUSY or SCANNING or GENERATION.busy():
            raise ValueError('当前任务仍在运行，请等任务结束后再退出工作台')
        SHUTTING_DOWN = True
        threading.Thread(target=HTTP_SERVER.shutdown,daemon=True).start()
        return dict(ok=True)
    if action in ('/api/catalog-select', '/api/catalog-export', '/api/project-activate', '/api/catalog-plan', '/api/catalog-plan-save'):
        if SCANNING or BUSY:
            raise ValueError('请等当前扫描或导出完成')
        if data.get('project') != STATE['project']:
            raise ValueError('当前工程已切换，请刷新页面后重试')
    if action == '/api/project-activate':
        cached = read_json(DATA/'projects'/(data.get('key', '')+'.json')) if re.fullmatch('[a-f0-9]{16}', data.get('key', '')) else None
        if not cached:
            raise ValueError('没有找到已扫描工程')
        activate_project(cached['project'])
        return dict(ok=True)
    if action == '/api/catalog-select':
        target = str(int(data['target']))
        choices = dict(STATE.get('catalogChoices', {}))
        if data.get('clear'):
            choices.pop(target, None)
        elif 'selected' in data or 'selectedIds' in data or 'removeId' in data:
            choice = dict(choices[target])
            selected=choice.get('selectedIds',choice['assetIds'] if choice.get('selected')=='*' else [choice.get('selected')])
            if 'selectedIds' in data:selected=data['selectedIds']
            elif 'selected' in data:selected=choice['assetIds'] if data['selected']=='*' else [data['selected']]
            if not isinstance(selected,list) or any(not isinstance(a,str) or a not in choice['assetIds'] for a in selected):raise ValueError('候选素材不在当前列表中')
            choice['assetIds']=[a for a in choice['assetIds'] if a!=data.get('removeId')]
            choice['selectedIds']=list(dict.fromkeys(a for a in selected if a in choice['assetIds']))
            choice['selected']='*' if len(choice['selectedIds'])>1 else next(iter(choice['selectedIds']),'')
            if choice['assetIds']:choices[target]=choice
            else:choices.pop(target,None)
        else:
            validate_selection(STATE['scan'], list(choices) + [target])
            entry = next(e for e in inventory(STATE['scan']) if str(e['id']) == target)
            single='file' in data
            if single and entry.get('mediaKind')=='sequence':raise ValueError('序列帧请添加整个序列文件夹')
            source=str(data.get('file') if single else data.get('folder','')).strip().strip('"')
            if single and not Path(source).is_file():raise ValueError('请选择有效的素材文件')
            assets = collect_assets(source,allow_file=single)
            audio = {'.wav', '.mp3'}
            assets = [a for a in assets if (a['extension'] in audio) == (entry.get('hasVideo') is False)]
            if not assets:
                raise ValueError('没有找到可用于此位置的图片、序列、视频或声音')
            existing = {a['id']: a for a in STATE['assets']}
            known={(a['path'].lower(),a['sequence']):a['id'] for a in existing.values()}
            for a in assets:
                a['id']=known.get((a['path'].lower(),a['sequence']),a['id'])
                existing[a['id']]=a
            STATE['assets'] = list(existing.values())
            old=choices.get(target,{})
            old_selected=old.get('selectedIds',old.get('assetIds',[]) if old.get('selected')=='*' else [old['selected']] if old.get('selected') else [])
            ids=list(dict.fromkeys(old.get('assetIds',[])+[a['id'] for a in assets]))
            selected=list(dict.fromkeys(old_selected+[a['id'] for a in assets]))
            choices[target]=dict(folder=str(Path(source).parent) if single else source,assetIds=ids,selectedIds=selected,selected='*' if len(selected)>1 else selected[0])
        STATE['catalogChoices'] = choices
        STATE['catalogPlans']=[];STATE.pop('catalogPlanSignature',None)
        save()
        archive_project()
        return dict(ok=True)
    if action == '/api/catalog-plan':
        count=data.get('count',1)
        if isinstance(count,bool) or not isinstance(count,int):raise ValueError('生成数量必须是整数')
        plans=build_plans(catalog_slots(),count,uuid.uuid4().hex)
        validate_catalog_plans(plans)
        STATE['catalogPlans']=plans;STATE['catalogPlanSignature']=catalog_plan_signature()
        save();archive_project()
        return dict(plans=plans,signature=STATE['catalogPlanSignature'])
    if action == '/api/catalog-plan-save':
        if data.get('signature')!=STATE.get('catalogPlanSignature') or data.get('signature')!=catalog_plan_signature():raise ValueError('候选或工程已变化，请重新生成组合计划')
        plans=validate_catalog_plans(data.get('plans'))
        if {p['id'] for p in plans}!={p['id'] for p in STATE.get('catalogPlans',[])}:raise ValueError('组合计划已更新，请刷新页面')
        STATE['catalogPlans']=plans;save();archive_project()
        return dict(ok=True)
    if action == '/api/catalog-export':
        slots = catalog_slots()
        signature=STATE.get('catalogPlanSignature')
        if not signature or data.get('signature')!=signature or signature!=catalog_plan_signature():raise ValueError('请先生成并确认组合计划；候选变更后需重新生成')
        plans=validate_catalog_plans(STATE.get('catalogPlans'))
        ids=data.get('ids');known={p['id'] for p in plans}
        if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in known for i in ids) or len(set(ids))!=len(ids):raise ValueError('请选择有效且不重复的组合计划')
        return enqueue_export(plans, slots, bool(data.get('render')), data.get('comp', STATE['comp']), selected=ids, origin='catalog')
    if action == '/api/simple-check':
        return update_simple(data.get('folders', STATE.get('simple', {}).get('folders', {})))
    if action == '/api/simple-export':
        if BUSY or SCANNING:
            raise ValueError('已有任务在运行')
        report = update_simple(data.get('folders', STATE.get('simple', {}).get('folders', {})))['report']
        if not report['canGenerate']:
            raise ValueError('；'.join(report['issues']) or '请至少选择一个新素材文件夹')
        plans = build_plans(report['slots'], int(data.get('count', 1)), uuid.uuid4().hex)
        return enqueue_export(plans, report['slots'], bool(data.get('render', False)), data.get('comp', STATE['comp']), origin='simple')
    if action == '/api/native-folder':
        return choose_native_folder(data.get('path',''))
    if action == '/api/pick-folder':
        return browse_folder(data.get('path', ''))
    if action == '/api/pick-file':
        return browse_files(data.get('path',''),EXTENSIONS)
    if action == '/api/find-projects':
        return discover_projects(data.get('path', ''))
    if action == '/api/open-result':
        batch = next((b for b in STATE['batches'] if b['id'] == data.get('batchId')), None)
        row = next((r for r in (batch or {}).get('rows', []) if r['id'] == data.get('rowId')), None)
        if not row or not row.get('project'):
            raise ValueError('还没有生成工程文件')
        folder = Path(row['project']).resolve().parent
        if not folder.is_relative_to(OUTPUT.resolve()) or not folder.is_dir():
            raise ValueError('输出目录不存在')
        os.startfile(str(folder))
        return dict(ok=True)
    if action == '/api/import':
        assets = collect_assets(data['path'])
        existing = {a['id']: a for a in STATE['assets']}
        existing.update({a['id']: a for a in assets})
        STATE['assets'] = list(existing.values())
        save()
        return dict(count=len(assets))
    if action == '/api/scan':
        if BUSY:
            raise ValueError('请等当前导出结束')
        project = Path(data.get('project', STATE['project'])).resolve()
        if project.suffix.lower() != '.aep' or not project.is_file():
            raise ValueError('请选择有效的 .aep 工程')
        preview_dir = DATA / 'catalog' / uid(str(project) + str(project.stat().st_mtime_ns) + 'v5-png')
        preview_dir.mkdir(parents=True, exist_ok=True)
        previous = read_json(preview_dir/'scan.json', {})
        refresh_ids = [int(i) for i in data.get('refreshIds', [])]
        write_json(DATA/'scan-progress.json', dict(done=0,total=0,name='等待 AE'))
        result = run_bridge(dict(action='scan', project=str(project), previewDir=str(preview_dir), refreshIds=refresh_ids, progress=str(DATA/'scan-progress.json')), timeout=900)
        previous_entries = {e['id']:e for e in previous.get('items', [])+previous.get('comps', [])}
        for e in result['items']+result['comps']:
            if e['id'] not in refresh_ids:
                for key in ('previewTime','previewEncoding'):
                    if key not in e and key in previous_entries.get(e['id'], {}):
                        e[key] = previous_entries[e['id']][key]
        finalize_previews(result, preview_dir)
        result['scannedAt'] = time.strftime('%Y-%m-%d %H:%M:%S')
        write_json(preview_dir/'scan.json', result)
        activate_project(str(project), result)
        return result
    if action == '/api/config':
        validate_slots(data['slots'])
        STATE['slots'] = data['slots']
        STATE['plans'] = []
        save()
        return dict(ok=True)
    if action == '/api/plan':
        validate_slots(STATE['slots'])
        STATE['plans'] = build_plans(STATE['slots'], int(data['count']), data.get('seed', uuid.uuid4().hex))
        save()
        return STATE['plans']
    if action == '/api/save-plans':
        assets = {a['id']: a for a in STATE['assets']}
        signatures = set()
        for plan in data['plans']:
            replacements = resolve_plan(plan, STATE['slots'], assets)
            sig = tuple(sorted((r['itemId'], r['path']) for r in replacements))
            if sig in signatures:
                raise ValueError('手动调整后出现重复搭配，请修改后再保存')
            signatures.add(sig)
        STATE['plans'] = data['plans']
        save()
        return dict(ok=True)
    if action == '/api/export':
        return enqueue_export(STATE['plans'], STATE['slots'], bool(data.get('render', True)), data.get('comp', STATE['comp']), data.get('ids'))
    if action == '/api/cancel':
        CANCEL.set()
        return dict(message='当前一项完成后停止，已完成文件保留')
    if action == '/api/retry':
        if BUSY or SCANNING:
            raise ValueError('已有任务在运行')
        batch = next(b for b in STATE['batches'] if b['id'] == data['id'])
        if not any(r['status'] != 'done' for r in batch['rows']):
            raise ValueError('这个批次已经全部完成')
        BUSY = True
        CANCEL.clear()
        threading.Thread(target=worker, args=(batch,), daemon=True).start()
        return dict(ok=True)
    if action == '/api/open-output':
        os.startfile(str(OUTPUT))
        return dict(ok=True)
    raise ValueError('未知操作')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_json(self, value, code=200):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/generation-settings':
            return self.send_json(GENERATION.public_config())
        if parsed.path == '/api/generations':
            params=parse_qs(parsed.query)
            return self.send_json(GENERATION.list(params.get('project',[None])[0],params.get('target',[None])[0]))
        if parsed.path == '/api/animation-status':
            try:return self.send_json(ANIMATIONS.status(parse_qs(parsed.query).get('id',[''])[0]))
            except ValueError as exc:return self.send_json(dict(error=str(exc)),400)
        if parsed.path == '/api/health':
            return self.send_json(dict(appId=runtime.APP_ID,version=runtime.VERSION,home=str(runtime.WORK_HOME),pid=os.getpid(),desktop=DESKTOP_ACTIVATE is not None))
        if parsed.path == '/api/environment':
            return self.send_json(runtime.environment(AE, detect=True))
        if parsed.path == '/api/state':
            with LOCK:
                initial = read_json(DATA / 'initial_scan.json')
                if initial and initial.get('ok') and not STATE['scan']:
                    adopt_scan(initial)
                return self.send_json(dict(**STATE, environment=runtime.environment(AE), catalog=inventory(STATE['scan']) if STATE.get('scan') else [], projects=project_list(), scanProgress=read_json(DATA/'scan-progress.json'), busy=BUSY, scanning=SCANNING, aiBusy=GENERATION.busy(), flowVersion=2, aeAvailable=AE.is_file(), output=str(OUTPUT)))
        if parsed.path == '/api/manifest':
            return self.send_json(dict(project=STATE['project'], slots=STATE['slots'], plans=STATE['plans']))
        if parsed.path in ('/animation-frame','/generation-media'):
            params=parse_qs(parsed.query)
            try:
                path=ANIMATIONS.frame(params.get('id',[''])[0],int(params.get('frame',['0'])[0])) if parsed.path=='/animation-frame' else GENERATION.output(params.get('id',[''])[0])
            except (ValueError,OSError) as exc:return self.send_json(dict(error=str(exc)),400)
        elif parsed.path in ('/original-preview', '/original-media'):
            params = parse_qs(parsed.query)
            if params.get('project', [''])[0] != uid(STATE['project'].lower()):
                self.send_error(404)
                return
            item = next((e for e in (STATE.get('scan') or {}).get('items', []) + (STATE.get('scan') or {}).get('comps', []) if str(e['id']) == params.get('id', [''])[0]), {})
            path = Path(item.get('previewPath', '') if parsed.path == '/original-preview' else item.get('path', ''))
            if parsed.path == '/original-preview' and params.get('thumb') and path.is_file():
                thumb = path.with_name(path.stem+'-thumb.png')
                if thumb.is_file():
                    path = thumb
        elif parsed.path == '/media':
            aid = parse_qs(parsed.query).get('id', [''])[0]
            asset = next((a for a in STATE['assets'] if a['id'] == aid), None)
            if not asset:
                self.send_error(404)
                return
            path = Path(asset['path'])
        elif parsed.path == '/reference.mp4':
            project_dir = Path(STATE['project']).parent
            paths = list(project_dir.glob('参考视频.mp4')) or list(project_dir.glob('*原k帧*.mp4'))
            path = paths[0] if paths else Path('missing')
        else:
            name = parsed.path.strip('/') or 'index.html'
            path = (ROOT / 'static' / name).resolve()
            if not path.is_relative_to(ROOT / 'static'):
                self.send_error(403)
                return
        if not path.is_file():
            self.send_error(404)
            return
        size = path.stat().st_size
        start, end = 0, size - 1
        range_header = self.headers.get('Range')
        if range_header:
            match = re.fullmatch(r'bytes=(\d+)-(\d*)', range_header)
            if not match:
                self.send_error(416)
                return
            start = int(match[1])
            end = min(end, int(match[2])) if match[2] else end
            if start > end:
                self.send_error(416)
                return
        self.send_response(206 if range_header else 200)
        self.send_header('Content-Type', mimetypes.guess_type(path)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Accept-Ranges', 'bytes')
        if range_header:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        try:
            with path.open('rb') as stream:
                stream.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = stream.read(min(remaining, 65536))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_POST(self):
        global SCANNING
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}'):
            return self.send_json(dict(error='仅接受本地工作台请求'), 403)
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length > 2_000_000:
                raise ValueError('请求过大')
            payload = json.loads(self.rfile.read(length) or '{}')
            # Serialize edits, while long-running AE scan does not prevent state reads.
            if self.path == '/api/scan':
                with LOCK:
                    if SCANNING or BUSY:
                        raise ValueError('AE 正在处理任务，请稍后重试')
                    SCANNING = True
                try:
                    value = dispatch(self.path, payload)
                finally:
                    SCANNING = False
            elif self.path in ('/api/pick-folder', '/api/find-projects', '/api/native-folder'):
                value = dispatch(self.path, payload)
            else:
                with LOCK:
                    value = dispatch(self.path, payload)
            self.send_json(value)
        except Exception as exc:
            self.send_json(dict(error=str(exc)), 400)


HTTP_SERVER = None


class LocalHTTPServer(ThreadingHTTPServer):
    allow_reuse_address=False

    def server_bind(self):
        if os.name=='nt':
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()


def serve(http_server=None):
    global HTTP_SERVER, PORT
    HTTP_SERVER=http_server or LocalHTTPServer(('127.0.0.1',PORT),Handler)
    PORT=HTTP_SERVER.server_port
    initialize_simple()
    archive_project()
    save()
    print(f'AE 工作台：http://127.0.0.1:{PORT}', flush=True)
    try:
        HTTP_SERVER.serve_forever()
    finally:
        HTTP_SERVER.server_close()


if __name__ == '__main__':
    serve()
