"""Validated final MP4 settings, snapshotted by each export batch."""
import math
from fractions import Fraction
from pathlib import Path

DEFAULTS = dict(width=0, height=0, fps=0, fit='contain', mode='quality', crf=18,
                bitrate=12, audio=True, audioBitrate=192)


def normalize(value=None):
    if value is not None and not isinstance(value, dict):
        raise ValueError('视频参数必须是对象')
    result = dict(DEFAULTS)
    result.update({k:v for k,v in (value or {}).items() if k in DEFAULTS})
    for key, low, high, integer in [('width',0,7680,True),('height',0,7680,True),
                                   ('fps',0,120,False),('crf',0,51,True),
                                   ('bitrate',0.1,200,False),('audioBitrate',64,320,True)]:
        raw=result[key]
        try: number=float(raw)
        except (ValueError,TypeError): raise ValueError(f'无效视频参数：{key}') from None
        if isinstance(raw,bool) or not math.isfinite(number) or not low<=number<=high or (integer and number!=int(number)):
            raise ValueError(f'视频参数 {key} 超出范围')
        result[key]=int(number) if integer else number
    w,h=result['width'],result['height']
    if bool(w)!=bool(h) or (w and (min(w,h)<16 or w%2 or h%2)):
        raise ValueError('宽高需同时留为 0，或填写 16–7680 之间的偶数')
    if result['fps'] and result['fps']<1:raise ValueError('帧率需为 0（原帧率）或 1–120')
    if result['fit'] not in ('contain','cover') or result['mode'] not in ('quality','bitrate') or not isinstance(result['audio'],bool):
        raise ValueError('无效的视频适配、画质或音频选项')
    return result


def encode_command(source, target, settings=None):
    if Path(target).exists():raise ValueError('输出视频已存在，拒绝覆盖')
    s=normalize(settings);w,h=s['width'],s['height'];filters=[]
    # Square pixels before fitting, including non-square-pixel AE outputs.
    filters.append('scale=trunc(iw*sar/2)*2:trunc(ih/2)*2,setsar=1')
    if w:
        if s['fit']=='contain':
            filters.append(f'scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2')
        else:
            filters.append(f'scale={w}:{h}:force_original_aspect_ratio=increase:force_divisible_by=2,crop={w}:{h}')
    if s['fps']:filters.append(f'fps={s["fps"]:g}')
    args=['ffmpeg','-nostdin','-n','-i',str(source),'-map','0:v:0','-vf',','.join(filters),'-c:v','libx264','-pix_fmt','yuv420p']
    args+=['-crf',str(s['crf'])] if s['mode']=='quality' else ['-b:v',f'{s["bitrate"]:g}M']
    args+=['-map','0:a:0?','-c:a','aac','-b:a',f'{s["audioBitrate"]}k'] if s['audio'] else ['-an']
    return args+['-movflags','+faststart',str(target)]


def validate_probe(info, settings=None):
    s=normalize(settings)
    videos=[x for x in info.get('streams',[]) if x.get('codec_type')=='video']
    if not videos or float(info.get('format',{}).get('duration',0))<=0:
        raise ValueError('导出视频未通过时长校验')
    v=videos[0]
    if s['width'] and (v.get('width'),v.get('height'))!=(s['width'],s['height']):
        raise ValueError('导出分辨率与设置不一致')
    if s['fps'] and abs(float(Fraction(v.get('avg_frame_rate','0')))-s['fps'])>0.02:
        raise ValueError('导出帧率与设置不一致')
    if not s['audio'] and any(x.get('codec_type')=='audio' for x in info.get('streams',[])):
        raise ValueError('静音导出仍包含音轨')
    return info
