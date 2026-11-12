let catalogCategory='', catalogStamp='', catalogProjectKey='';
async function importProjectFolder(){
  if(state.busy||state.scanning||projectScanPending)throw new Error('请等当前扫描或导出完成');
  const initial=state.project?.replace(/[\\/][^\\/]+$/,'')||'';
  await chooseFolder('',async folder=>{
    const version=dialogVersion;
    const result=await api('find-projects',{path:folder});
    if(version!==dialogVersion||!$('#dialog').open)return;
    if(!result.projects.length)throw new Error(result.truncated?'文件夹范围太大，尚未找到 AEP。请进入具体工程文件夹再查找。':result.skipped?'部分目录无法读取，尚未找到 AEP。请检查文件夹权限。':'这个文件夹及子文件夹中没有 .aep 工程。请检查是否仍是压缩包，或选择其他文件夹。');
    const warnings=[result.truncated?'查找范围较大，当前列表可能不完整；可返回选择更具体的文件夹。':'',result.skipped?`${result.skipped} 个位置无法读取。`:''].filter(Boolean).join(' ');
    dialog('选择要导入的 AE 工程',`<p class="dialog-help">找到 ${result.projects.length} 个 AEP。选择后由本机 AE 扫描素材并生成预览，原工程不会修改。</p>${warnings?`<p class="catalog-warning">${esc(warnings)}</p>`:''}<div class="project-file-list">${result.projects.map((p,i)=>`<label class="project-file-option"><input type="radio" name="importAep" value="${esc(p.path)}" required ${result.projects.length===1?'checked':''}><span><strong>${esc(p.name)}${p.backup?' <em>自动保存副本</em>':''}</strong><small>${esc(p.relative)}</small><small>${esc(p.modified)} · ${(p.size/1048576).toFixed(1)} MB</small></span></label>`).join('')}</div><p class="dialog-help">素材会尽量完整列出；用途分类参考名称与引用关系。特殊插件、缺失素材可能影响预览，文字和形状不能直接当图片替换。</p><button class="text-button" type="button" id="chooseAnotherProjectFolder">← 重新选择文件夹</button>`,async()=>{
      const project=$('input[name="importAep"]:checked')?.value;
      if(!project)throw new Error('请先选择一个 AE 工程');
      $('#dialog').close();catalogCategory='';$('#catalogSearch').value='';$('#catalogKind').value='all';
      toast('正在通过 AE 扫描新工程，完成后会自动显示素材和预览');
      await scanProject(project);
    },'导入并扫描');
    $('#chooseAnotherProjectFolder').onclick=()=>safe(importProjectFolder);
  },initial,{title:'导入工程文件夹',label:'查找 AE 工程',help:'进入工程所在文件夹后，点“查找 AE 工程”。会查找当前文件夹及子文件夹中的 .aep，不需要上传文件。'});
  const direct=document.createElement('button');direct.type='button';direct.className='text-button';direct.textContent='已有 AEP 路径？直接填写';
  direct.onclick=()=>dialog('直接导入 AEP',`<div class="field"><label for="projectPath">.aep 文件完整路径</label><input required id="projectPath" placeholder="粘贴本机 AEP 路径"><small>原工程和素材保留，各工程配置独立保存。</small></div>`,async()=>{const project=$('#projectPath').value.trim().replace(/^"|"$/g,'');$('#dialog').close();await scanProject(project);},'导入并扫描');
  $('#dialogBody').appendChild(direct);
}
$('#importProject').onclick=()=>safe(importProjectFolder);
function originalUrl(entry, thumb=true) {return `/original-preview?project=${catalogProjectKey}&id=${entry.id}${thumb?'&thumb=1':''}&v=${entry.previewTime||0}-${entry.previewEncoding||'png'}`;}
function originalPicture(e, thumb=true) {
  if(e.previewBlank) return '<span class="catalog-placeholder">此帧透明 · 查看内部素材</span>';
  if(e.previewError) return `<span class="catalog-placeholder" title="${esc(e.previewError)}">预览失败 · 查看详情</span>`;
  if(e.previewPath) return `<img loading="lazy" src="${originalUrl(e,thumb)}" alt="${esc(e.name)}">`;
  return `<span class="catalog-placeholder">${e.hasVideo===false?'♫ 声音素材':e.kind==='procedural'?'AE 内部图层':'预览未生成'}</span>`;
}
function renderCatalog(force=false) {
  const entries=state.catalog||[], choices=state.catalogChoices||{}, selected=Object.keys(choices).length;
  catalogProjectKey=(state.projects||[]).find(p=>p.project===state.project)?.key||'';
  $('#catalogCount').textContent=entries.filter(e=>e.replaceable).length;
  $('#catalogSelected').textContent=selected?`已选 ${selected} 个替换位置`:'尚未选择替换';
  const capacity=catalogCapacity();
  $('#catalogCapacity').textContent=selected?`共 ${capacity.toLocaleString()} 种不重复组合 · 每个位置可添加多个候选`:'留空保持原样 · 先添加候选素材';
  const count=Number($('#catalogQuantity').value);
  $('#createCatalogPlans').disabled=!selected||state.busy||state.scanning||!Number.isInteger(count)||count<1||count>Math.min(capacity,500);
  $('#viewCatalogPlans').disabled=!(state.catalogPlans||[]).length;
  const progress=state.scanProgress;
  $('#catalogSummary').textContent=state.scanning?`正在扫描与生成预览${progress?' · '+progress.done+' / '+progress.total:''}，请保持 AE 可用`:`${entries.filter(e=>e.kind==='source').length} 项源素材 · ${entries.filter(e=>e.kind==='group').length} 个合成 · ${entries.filter(e=>e.kind==='procedural').length} 个文字 / 形状图层`;
  const stamp=JSON.stringify([state.project,state.scan?.scannedAt,entries.length,entries.filter(e=>e.previewPath).length,choices,state.projects,state.comp]);
  $('#catalogProject').disabled=state.busy||state.scanning;
  if(!force&&stamp===catalogStamp)return;catalogStamp=stamp;
  const projectSelect=$('#catalogProject');projectSelect.innerHTML=(state.projects||[]).map(p=>`<option value="${p.key}" ${p.project===state.project?'selected':''}>${esc(p.name)}</option>`).join('');
  projectSelect.disabled=state.busy||state.scanning;
  const previous=$('#catalogComp').dataset.project===state.project?$('#catalogComp').value:state.comp;
  $('#catalogComp').innerHTML=(state.scan?.comps||[]).filter(c=>!c.uses?.length||c.name===state.comp).map(c=>`<option value="${esc(c.name)}" ${c.name===previous?'selected':''}>${esc(c.name)} · ${Number((c.workAreaDuration??c.duration).toFixed(2))} 秒</option>`).join('');$('#catalogComp').dataset.project=state.project;
  const categories=[...new Set(entries.filter(e=>['source','group'].includes(e.kind)).map(e=>e.category))];
  if(!categories.includes(catalogCategory))catalogCategory='';
  $('#catalogCategories').innerHTML=['',...categories].map(c=>`<button class="filter ${c===catalogCategory?'active':''}" data-category="${esc(c)}">${esc(c||'全部')} <small>${entries.filter(e=>['source','group'].includes(e.kind)&&(!c||e.category===c)).length}</small></button>`).join('');
  $$('[data-category]').forEach(b=>b.onclick=()=>{catalogCategory=b.dataset.category;renderCatalog(true);});
  const q=$('#catalogSearch').value.trim().toLowerCase().replace('集装箱','箱').replace('升级特效','升级').replace('死亡特效','死亡'),kind=$('#catalogKind').value;
  const visible=entries.filter(e=>(kind==='all'?['source','group'].includes(e.kind):kind==='selected'?choices[e.id]:kind==='sequence'?e.mediaKind==='sequence':kind==='animated'?e.animated:e.kind===kind)&&(!catalogCategory||e.category===catalogCategory)&&[e.name,e.category,...(e.uses||[]),...(e.references||[]).map(r=>r.layerName)].join(' ').toLowerCase().includes(q));
  visible.sort((a,b)=>Number(b.replaceable)-Number(a.replaceable)||Number(Boolean(choices[b.id]))-Number(Boolean(choices[a.id])));
  window.stopCatalogHover?.();
  $('#catalogGrid').innerHTML=visible.map(e=>{
    const choice=choices[e.id],asset=state.assets.find(a=>a.id===choice?.selected);
    return `<article class="catalog-card ${choice?'chosen':''}"><button class="catalog-image" data-detail="${esc(e.id)}">${originalPicture(e)}<span>${e.kind==='group'?'整个组合':e.kind==='control'?'控制项':e.kind==='procedural'?'内部图层':'源素材'}</span>${e.mediaLabel?`<span class="media-badge">${esc(e.mediaLabel)}${e.mediaKind==='sequence'?' · '+e.frameCount+' 帧':''}</span>`:''}</button><div class="catalog-copy"><div class="catalog-category">${esc(e.category)} · ${e.referenceCount} 处引用</div><h3 title="${esc(e.name)}">${esc(e.name)}</h3><p>${e.width?`${e.width} × ${e.height}`:''}${e.previewPath?' · 原工程预览':''}${e.missing?' · 文件缺失':''}</p><p class="catalog-use">${esc(e.uses?.slice(0,3).join(' / ')||'未引用')}</p>${choice?`<div class="catalog-choice"><strong>${selectedCandidateIds(choice).length} 个候选参与组合</strong><small>共添加 ${choice.assetIds.length} 项 · 可继续追加</small></div>`:''}<div class="catalog-buttons"><button class="button small" data-detail="${esc(e.id)}">${e.animated?'预览动画 / AI 生成':'预览 / AI 生成'}</button>${choice&&choice.selected!=='*'?`<button type="button" class="button small" data-candidate-preview="${esc(choice.selected)}">预览替换素材</button>`:''}${e.replaceable?`<button class="button small ${choice?'':'primary'}" data-catalog-folder="${e.id}">${choice?'管理 / 添加候选':'添加替换候选'}</button>`:''}${choice?`<button class="text-button" data-catalog-clear="${e.id}">取消替换</button>`:''}</div></div></article>`;
  }).join('')||`<div class="empty">${state.scan?'没有符合条件的素材，试试“全部”或换个关键词。':'还没有工程。点击上方“＋ 导入工程文件夹”开始使用。'}</div>`;
  window.bindCatalogHover?.();
  $$('[data-candidate-preview]').forEach(b=>b.onclick=()=>previewCandidate(b.dataset.candidatePreview));
  $$('[data-detail]').forEach(b=>b.onclick=()=>catalogDetail(b.dataset.detail));
  $$('[data-catalog-folder]').forEach(b=>b.onclick=()=>safe(()=>manageCandidates(b.dataset.catalogFolder)));
  $$('[data-catalog-clear]').forEach(b=>b.onclick=()=>safe(()=>catalogSelect({target:b.dataset.catalogClear,clear:true})));
  $$('[data-catalog-asset]').forEach(s=>s.onchange=()=>safe(()=>catalogSelect({target:s.dataset.catalogAsset,selected:s.value})));
}
async function catalogSelect(payload){await api('catalog-select',{...payload,project:payload.project??state.project});await refresh(false);}
async function pickCatalogFolder(id){
  const e=state.catalog.find(x=>String(x.id)===String(id));
  await chooseFolder(e.name,folder=>catalogSelect({target:id,folder}),state.catalogChoices?.[id]?.folder||'');
}
function catalogStructure(id){
  const e=state.catalog.find(x=>String(x.id)===String(id));if(!e)return;
  const children=(e.children||[]).map(id=>state.catalog.find(x=>x.id===id)).filter(Boolean);
  dialog(e.name,`<div class="catalog-detail-preview">${originalPicture(e,false)}</div><p class="dialog-help">${e.previewBlank?'此时间点没有可见画面。请查看内部素材或在 AE 中查看其他时间点。':e.previewPath?`原素材 / 原合成 ${Number((e.previewTime||0).toFixed(2))} 秒处静帧。合成预览包含自身效果；源素材预览不含父图层上的特效。`:'此项没有可用静帧。可查看其内部素材或所在合成。'}</p>${e.previewError?`<p class="catalog-warning">${esc(e.previewError)}。素材仍可选择替换；可重新扫描重试。</p>`:''}<p class="catalog-warning">${esc(e.reason)}</p>${e.hasVideo===false?`<audio controls src="/original-media?project=${catalogProjectKey}&id=${e.id}"></audio>`:''}${e.path?`<div class="field"><label>原素材位置</label><input readonly value="${esc(e.path)}"></div>`:''}${children.length?`<h3>内部素材 · ${children.length} 项</h3><div class="catalog-children">${children.map(c=>`<button type="button" class="button small" data-child="${c.id}">${esc(c.name)}</button>`).join('')}</div>`:''}${e.parentId?`<button type="button" class="button" data-child="${e.parentId}">查看所在合成</button>`:''}<h3>使用位置 · ${e.referenceCount} 处</h3><div class="catalog-references">${(e.references||[]).map(r=>`<div><button type="button" class="text-button" data-child="${r.compId}">${esc(r.compName)} ↗</button><span>第 ${r.layerIndex} 层 · ${esc(r.layerName)}${!r.enabled?' · 已关闭':''}${r.adjustment?' · 调整层':''}${r.guide?' · 参考层':''}</span></div>`).join('')||'<p>没有其他合成引用。</p>'}</div><p class="dialog-help">静帧不能展示完整运动；导出一份视频检查时长、位置与效果后再批量生成。${e.kind==='group'?'组合按原画布居中等比适配，外层动画保留；内部动画被替换。':''}</p>`,async()=>{},'关闭');
  $$('[data-child]').forEach(b=>b.onclick=()=>catalogDetail(b.dataset.child));
}
$('#catalogSearch').oninput=()=>renderCatalog(true);$('#catalogKind').onchange=()=>{catalogCategory='';renderCatalog(true);};$('#catalogQuantity').oninput=()=>renderCatalog();
$('#catalogProject').onchange=e=>safe(async()=>{await api('project-activate',{key:e.target.value,project:state.project});catalogCategory='';await refresh();});
async function exportCatalog(render){await exportCombinationPlans(render);}
$('#catalogAep').onclick=()=>safe(()=>exportCatalog(false));$('#catalogVideo').onclick=()=>safe(()=>exportCatalog(true));
$('#createCatalogPlans').onclick=()=>safe(async()=>{await api('catalog-plan',{project:state.project,count:Number($('#catalogQuantity').value)});combinationDraft=null;await refresh(false);showTab('combinations');toast('组合计划已生成，确认搭配后再导出');});
$('#viewCatalogPlans').onclick=()=>showTab('combinations');
