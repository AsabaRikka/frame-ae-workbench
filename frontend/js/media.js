let mediaSession=0, mediaCleanup=()=>{};
const mediaDialog=document.createElement('dialog');mediaDialog.id='mediaDialog';document.body.append(mediaDialog);
mediaDialog.addEventListener('close',()=>{mediaSession++;mediaCleanup();});

async function showGenerationSettings(){
  const c=await api('generation-settings');
  dialog('火山方舟 API 设置',`<p class="dialog-help">填写火山方舟控制台的 API Key，以及已开通的 Seedream / Seedance 模型 ID 或推理接入点 ID。<a href="https://console.volcengine.com/ark/region:cn-beijing/apiKey" target="_blank" rel="noreferrer">打开火山方舟控制台 ↗</a></p><div class="field"><label>API Key ${c.hasKey?'· 已配置（留空保留）':'· 尚未配置'}</label><input id="arkKey" type="password" autocomplete="new-password" placeholder="输入 API Key，不会回显已有密钥"></div><div class="field"><label>生图模型 ID · Seedream</label><input id="arkImageModel" value="${esc(c.imageModel)}" placeholder="复制控制台模型 ID 或 ep- 开头的接入点 ID"></div><div class="field"><label>生视频模型 ID · Seedance</label><input id="arkVideoModel" value="${esc(c.videoModel)}" placeholder="复制支持图生视频的模型 ID 或接入点 ID"></div><label class="checkbox"><input id="arkClearKey" type="checkbox">清除本机保存的密钥</label><p class="dialog-help">服务地址：${esc(c.baseUrl)}<br>密钥使用 Windows 账户加密保存。搬到另一台电脑需重新填写。生成由火山方舟计费；只有点击生成时才会发送提示词及所选参考图。</p>`,async()=>{
    await api('generation-settings',{apiKey:$('#arkKey').value,imageModel:$('#arkImageModel').value,videoModel:$('#arkVideoModel').value,clearKey:$('#arkClearKey').checked});toast('火山方舟配置已保存');
  });
}

function similarPrompt(e,kind){
 const base=`参考图片中的${e.category||'游戏素材'}，生成一个外观有变化的同类游戏素材。保持主体数量、朝向、镜头视角、构图和美术风格，主体完整，不添加文字、水印、界面或额外角色。`;
 return kind==='video'?base+' 固定镜头，让主体进行自然、连贯的动作，保持身份和比例稳定，尽量首尾衔接。':base+' 单独展示主体，边缘清晰，方便后续用于游戏广告素材替换。';
}

function openMediaDetail(e, asset=false){
 mediaCleanup();const session=++mediaSession,project=state.project;let kind='image',jobTimer,playing=false,raf=0,frameSerial=0,animationId='',referenceFrame=0;
 const live=()=>session===mediaSession&&mediaDialog.open;
 const image=e.hasVideo===false?`<audio controls src="/original-media?project=${catalogProjectKey}&id=${e.id}"></audio>`:asset?`<img src="/media?id=${encodeURIComponent(e.id)}" alt="${esc(e.name)}">`:originalPicture(e,false);
 const eligible=!asset&&e.kind!=='procedural'&&e.hasVideo!==false;
 const label=e.mediaLabel||(e.sequence?'序列帧':'素材');
 mediaDialog.innerHTML=`<div class="dialog-head"><div><h2>${esc(e.name)}</h2><p class="dialog-help">${esc(label)}${e.frameCount||e.frames?' · '+(e.frameCount||e.frames)+' 帧':''}${e.fps?' · '+Number(e.fps.toFixed(3))+' fps':''}</p></div><button class="close" id="closeMedia" aria-label="关闭">×</button></div><div class="media-detail-layout"><section><div class="catalog-detail-preview" id="motionStage">${image}</div><div id="motionControls"></div><p id="motionNote" class="dialog-help"></p><div class="media-actions">${e.animated||e.sequence?'<button class="button" id="playOriginal">▶ 播放动画预览</button>':''}${!asset?'<button class="button" id="mediaStructure">查看使用位置 / 内部素材</button>':''}</div>${e.previewError?`<p class="catalog-warning">${esc(e.previewError)}</p>`:''}<p class="dialog-help">${asset?'候选序列默认按 30 fps 预览，实际替换沿用原工程的帧率。':'源素材预览不包含父图层特效；合成动画按工作区起点取样。'} ${e.sequence||e.mediaKind==='sequence'?'序列帧会按数字顺序播放，并保留透明背景。':''}</p></section>${eligible?`<section class="generation-pane"><div class="generation-head"><h3>AI 生成新素材</h3><button class="text-button" id="arkSetup">API 设置</button></div><div class="generation-tabs"><button type="button" class="button primary" data-gen-kind="image">生图</button><button type="button" class="button" data-gen-kind="video">生视频</button></div><label class="checkbox"><input id="genReference" type="checkbox" ${e.previewPath&&!e.previewBlank?'checked':''} ${e.previewPath&&!e.previewBlank?'':'disabled'}><span id="genRefLabel">参考原素材扫描静帧</span></label><p class="dialog-help">点击生成会把提示词和勾选的参考图发送至火山方舟，并产生 API 费用。视频以此静帧为首帧，不会上传整个工程或原动画。</p><div class="field"><label for="genPrompt">提示词 · 可以直接修改</label><textarea id="genPrompt" rows="6" maxlength="5000">${esc(similarPrompt(e,'image'))}</textarea></div><div class="generation-options"><label id="genSizeLabel">图片尺寸 <select id="genSize"><option>2K</option><option>4K</option><option>1K</option></select></label><label id="genDurationLabel" hidden>视频时长 <select id="genDuration"><option value="5">5 秒</option><option value="10">10 秒</option></select></label></div><div class="media-actions"><button class="button" id="genSimilar">一键生成相似素材</button><button class="button primary" id="genCustom">按提示词生成</button></div><p class="dialog-help">生成结果不保证透明背景或与原动画逐帧一致。先预览确认，再用作替换；导出时仍会适配原素材尺寸。</p><p id="genError" role="status" class="catalog-warning" hidden></p><div id="generationResults"></div></section>`:''}</div>`;
 $('#closeMedia').onclick=()=>mediaDialog.close();
 if(!mediaDialog.open)mediaDialog.showModal();
 mediaCleanup=()=>{clearTimeout(jobTimer);playing=false;cancelAnimationFrame(raf);mediaDialog.querySelectorAll('video').forEach(v=>v.pause());};
 if($('#mediaStructure'))$('#mediaStructure').onclick=()=>{mediaDialog.close();catalogStructure(e.id);};
 async function startPreview(){
  const button=$('#playOriginal');button.disabled=true;$('#motionNote').textContent='正在准备动画预览…';
  try{
   let motion=await api('animation',{project,target:e.id,...(asset?{assetId:e.id}:{})});
   while(motion.status==='running'&&live()){await new Promise(r=>setTimeout(r,800));motion=await api('animation-status?id='+motion.id);}
   if(!live())return;
   if(motion.status!=='done')throw new Error(motion.error||'动画预览未完成');
   $('#motionNote').textContent=motion.note||`${motion.frameCount} 帧 · ${Number(motion.duration.toFixed(3))} 秒${motion.fps?' · '+Number(motion.fps.toFixed(3))+' fps':''}`;
   button.hidden=true;
   if(motion.player==='video'){$('#motionStage').innerHTML=`<video controls autoplay loop playsinline src="/animation-frame?id=${motion.id}"></video>`;return;}
   animationId=motion.id;if($('#genReference'))$('#genReference').disabled=false;
   $('#motionStage').innerHTML='<canvas id="motionCanvas"></canvas>';
   $('#motionControls').innerHTML=`<button type="button" class="button small" id="motionPlay">暂停</button><button type="button" class="button small" id="motionPrev">上一帧</button><input id="motionSeek" type="range" min="0" max="${motion.frameCount-1}" value="0" aria-label="动画帧"><button type="button" class="button small" id="motionNext">下一帧</button><span id="motionFrame"></span>`;
   const cache=new Map(),canvas=$('#motionCanvas'),ctx=canvas.getContext('2d');let index=0,epoch=0;
   const cumulative=[0];motion.durations.forEach(d=>cumulative.push(cumulative.at(-1)+d));
   function getFrame(i){
    if(!cache.has(i)){const image=new Image();const promise=new Promise((resolve,reject)=>{image.onload=()=>resolve(image);image.onerror=()=>reject(new Error('动画帧读取失败'));});image.src=`/animation-frame?id=${motion.id}&frame=${i}`;cache.set(i,promise);if(cache.size>64)cache.delete(cache.keys().next().value);}
    return cache.get(i);
   }
   async function draw(i){
    index=i;const serial=++frameSerial;const image=await getFrame(i);
    if(!live()||serial!==frameSerial)return;
    referenceFrame=i;if($('#genRefLabel'))$('#genRefLabel').textContent=`参考预览当前帧（第 ${i+1} 帧）`;
    canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0);$('#motionSeek').value=i;$('#motionFrame').textContent=`${i+1} / ${motion.frameCount}`;
    getFrame((i+1)%motion.frameCount).catch(()=>{});
   }
   const pause=()=>{playing=false;cancelAnimationFrame(raf);$('#motionPlay').textContent='播放';};
   function tick(now){
    if(!live()||!playing)return;
    const elapsed=(now-epoch)%cumulative.at(-1);let next=0;
    while(next<motion.frameCount-1&&cumulative[next+1]<=elapsed)next++;
    if(next!==index)draw(next).catch(error=>{pause();$('#motionNote').textContent=error.message;});
    raf=requestAnimationFrame(tick);
   }
   function play(){playing=true;epoch=performance.now()-cumulative[index];$('#motionPlay').textContent='暂停';raf=requestAnimationFrame(tick);}
   $('#motionPlay').onclick=()=>playing?pause():play();
   $('#motionSeek').oninput=event=>{pause();safe(()=>draw(Number(event.target.value)));};
   $('#motionPrev').onclick=()=>{pause();safe(()=>draw((index+motion.frameCount-1)%motion.frameCount));};
   $('#motionNext').onclick=()=>{pause();safe(()=>draw((index+1)%motion.frameCount));};
   await draw(0);play();
  }catch(error){if(live()){$('#motionNote').textContent=error.message;button.disabled=false;}}
 }
 if($('#playOriginal'))$('#playOriginal').onclick=startPreview;
 if(!eligible)return;
 $('#arkSetup').onclick=()=>safe(showGenerationSettings);
 $$('[data-gen-kind]').forEach(b=>b.onclick=()=>{
  const old=kind;kind=b.dataset.genKind;$$('[data-gen-kind]').forEach(t=>t.classList.toggle('primary',t===b));
  if($('#genPrompt').value===similarPrompt(e,old))$('#genPrompt').value=similarPrompt(e,kind);
  $('#genSizeLabel').hidden=kind==='video';$('#genDurationLabel').hidden=kind==='image';
 });
 async function generate(similar){
  const a=$('#genSimilar'),b=$('#genCustom');a.disabled=b.disabled=true;$('#genError').hidden=true;
  try{
   if(similar){if(!animationId&&(!e.previewPath||e.previewBlank))throw new Error('当前没有可用参考帧，请填写提示词后生成');$('#genReference').checked=true;$('#genPrompt').value=similarPrompt(e,kind);}
   await api('generate',{project,target:e.id,animationId,referenceFrame,kind,prompt:$('#genPrompt').value,reference:$('#genReference').checked,size:$('#genSize').value,duration:Number($('#genDuration').value)});
   if(live()){toast('生成任务已提交，可关闭预览窗口，稍后回来查看');await pollJobs();}
  }catch(error){if(live()){$('#genError').textContent=error.message;$('#genError').hidden=false;}}
  finally{if(live())a.disabled=b.disabled=false;}
 }
 $('#genSimilar').onclick=()=>generate(true);$('#genCustom').onclick=()=>generate(false);
 const updateHistory=generationHistory($('#generationResults'),e,project);
 async function pollJobs(){
  clearTimeout(jobTimer);
  try{
   const jobs=await api('generations?project='+encodeURIComponent(project)+'&target='+e.id);
   if(!live())return;
   updateHistory(jobs);
  }catch(error){if(live()){$('#genError').textContent=error.message;$('#genError').hidden=false;}}
  finally{if(live())jobTimer=setTimeout(pollJobs,2500);}
 }
 pollJobs();
}
function catalogDetail(id){const e=state.catalog.find(x=>String(x.id)===String(id));if(e)openMediaDetail(e);}
function previewCandidate(id){const a=state.assets.find(x=>x.id===id);if(a)openMediaDetail({...a,mediaLabel:a.sequence?'序列帧':'候选素材',animated:a.sequence||['.gif','.webp','.mov','.mp4','.avi'].includes(a.extension),fps:30},true);}
$('#generationSettings').onclick=()=>safe(showGenerationSettings);
