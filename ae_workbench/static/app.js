const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state, activeSlot, tab = 'catalog', filter = 'all', query = '', editingPlans = false, dialogSave;
let simpleDraft=null, simpleDirty=false, simpleChecking=false, simpleTimer, simpleCheckQueue=Promise.resolve(), simpleKey='';
const makeId = () => crypto.randomUUID().slice(0, 12);
let toastTimer, refreshSerial=0, dialogVersion=0, projectScanPending=false;
function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 6500); }
async function api(path, payload) {
  const response = await fetch('/api/' + path, payload === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '操作失败');
  return data;
}
async function refresh(full = true) {
  const serial=++refreshSerial;
  const next = await api('state');
  if(serial!==refreshSerial)return;
  if(next.flowVersion!==2&&location.port==='8517'){location.replace('http://127.0.0.1:8518/');return;}
  if (editingPlans && state) next.plans = state.plans;
  if (state && state.project !== next.project) { simpleDraft=null; simpleKey=''; simpleDirty=false; editingPlans=false; }
  state = next;
  if (!state.slots.some(s => s.id === activeSlot)) activeSlot = state.slots[0]?.id;
  renderHeader();
  renderQueue();
  if(window.renderCatalog) renderCatalog();
  if(window.renderCombinationPlans) renderCombinationPlans();
}
function currentSlot() { return state.slots.find(s => s.id === activeSlot); }
function assetOptions(selected) { return state.assets.map(a => `<option value="${a.id}" ${a.id === selected ? 'selected' : ''}>${esc(a.name)}${a.sequence ? ` · ${a.frames} 帧` : ''}</option>`).join(''); }
function renderHeader() {
  const projectTitle=state.project.split(/[\\/]/).pop().replace(/\.aep$/i,'')||'尚未导入工程';
  $$('.current-project-title').forEach(el=>el.textContent=projectTitle);
  const outputComp=state.scan?.comps.find(c=>c.name===state.comp);
  $('#projectSize').textContent=outputComp?`${outputComp.width} × ${outputComp.height}`:'待扫描';
  $('#projectDuration').textContent=outputComp?`${Number((outputComp.workAreaDuration??outputComp.duration).toFixed(2))} 秒`:'—';
  const reference=$('#referenceVideo');
  if(state.project&&reference.dataset.project!==state.project){reference.dataset.project=state.project;reference.removeAttribute('poster');reference.src='/reference.mp4?project='+encodeURIComponent(state.project);}
  $('#assetCount').textContent = state.assets.length;
  $('#planCount').textContent = state.plans.length;
  $('#queueCount').textContent = state.batches.reduce((n,b) => n+b.rows.length,0);
  $('#projectName').textContent = state.project.split(/[\\/]/).pop()||'选择文件夹开始使用';
  $('#scan').disabled=!state.project||!state.aeAvailable||state.busy||state.scanning||projectScanPending;
  $('#environmentNotice').hidden=state.aeAvailable;
  $('#shutdownApp').disabled=state.busy||state.scanning||state.aiBusy||projectScanPending;
  $('#importProject').disabled=$('#changeProject').disabled=state.busy||state.scanning||projectScanPending;
  $('#connection').textContent = state.scanning ? 'AE · 正在扫描与生成预览' : state.scan ? `AE ${state.scan.version.split('.')[0]} · 已扫描` : (state.aeAvailable ? 'AE 已找到 · 待扫描' : 'AE 未连接');
  const missing = state.scan?.missing?.length || 0;
  $('#notice').hidden = tab==='simple' || (!!state.scan && missing === 0);
  $('#notice').textContent = state.scan ? `原工程有 ${missing} 项源素材缺失。可以先生成替换工程；导出完整视频前需要补齐。` : '请先扫描 AE 工程，再选择新素材。';
  if (missing) {
    const button=document.createElement('button');button.className='text-button';button.textContent='查看缺失清单 ↗';
    button.onclick=()=>dialog('缺失素材清单',`<p class="dialog-help">以下路径来自 AE 实际扫描。补齐文件或在 AE 中重新链接，保存后再扫描。</p>${state.scan.items.filter(i=>i.missing).map(i=>`<div class="field"><label>${esc(i.name)}</label><input readonly value="${esc(i.path)}"><small>引用位置：${esc(i.uses.join(' / ')||'未引用')}</small></div>`).join('')}`,async()=>{},'关闭');
    $('#notice').appendChild(button);
  }
}
function showTab(value) {
  if(!['catalog','combinations','queue'].includes(value))value='catalog';
  if(tab!==value)window.scrollTo(0,0);
  tab = value;
  $$('.view').forEach(v => v.hidden = v.id !== value + 'View');
  $$('.nav').forEach(n => n.classList.toggle('active', n.dataset.tab === value));
  const copy = {catalog:['工程素材','工程里能换的，都在这里。','先看原素材，为每个位置添加一个或多个候选，再预览组合计划。'],combinations:['组合计划','先看搭配，再生成作品。','每份计划明确列出要用的素材，导出严格按计划执行。'],queue:['导出队列','查看生成结果。','工程与视频独立保存，查看进度、定位失败、继续重试。']}[value];
  $('.eyebrow').textContent='AE WORKBENCH / '+copy[0];
  $('#crumb').textContent = copy[0]; $('#title').textContent = copy[1]; $('#subtitle').textContent = copy[2];
  $('#primaryAction').hidden = true;
  renderHeader();
}

const folderIcon='<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M3 9V6h10l3 4h13v16H3V9Z"/><path d="M3 10h13"/></svg>';
async function chooseFolder(role, callback=null, initial='', options={}) {
  let selected='', requestId=0;
  dialog(options.title||'选择'+({background:'背景',enemy:'小怪',boss:'BOSS'}[role]||role)+'素材文件夹', `<p class="dialog-help">${esc(options.help||'点击文件夹进入，找到素材所在目录后点“使用这个文件夹”。也可点击“浏览文件夹”打开系统选择窗口，或直接粘贴路径。')}</p><div class="folder-address"><input id="browsePath" aria-label="文件夹路径" placeholder="例如 D:\\tanyu\\Desktop\\小怪"><button type="button" class="button small" id="browseNative">浏览文件夹…</button><button type="button" class="button small" id="browseGo">前往</button></div><div class="folder-locations" id="browseRoots"></div><button type="button" class="text-button" id="browseUp">↑ 上一级</button><div id="browseFolders" class="browse-folders"></div><p class="dialog-help" id="browseInfo"></p>`, async()=>{
    if(!selected)throw new Error(options.fileMode?'请先选择一个素材文件':'请先进入一个素材文件夹');
    if(callback) await callback(selected); else {simpleDraft[role]=selected;simpleDirty=true;await checkSimpleFolders();}
  },options.label||'使用这个文件夹');
  const pickerVersion=dialogVersion;
  const pickerOpen=()=>pickerVersion===dialogVersion&&$('#dialog').open;
  async function browse(path){
    const id=++requestId;selected='';$('#dialogSubmit').disabled=true;$('#browseInfo').textContent='正在读取…';
    try{
      const result=await api(options.fileMode?'pick-file':'pick-folder',{path});
      if(id!==requestId||!pickerOpen())return;
      selected=result.path;$('#browsePath').value=selected;$('#dialogSubmit').disabled=!selected;
      $('#browseRoots').innerHTML=result.roots.map(r=>`<button type="button" class="button small" data-browse="${esc(r.path)}">${esc(r.name)}</button>`).join('');
      $('#browseUp').hidden=!selected;$('#browseUp').onclick=()=>safe(()=>browse(result.parent));
      $('#browseFolders').innerHTML=result.folders.map(f=>`<button type="button" data-browse="${esc(f.path)}">${folderIcon}<span>${esc(f.name)}</span><span>›</span></button>`).join('')||`<p class="dialog-help">${selected?'这里没有子文件夹，可以直接使用当前文件夹。':'请选择上方磁盘，或在地址栏粘贴文件夹路径。'}</p>`;
      $('#browseInfo').textContent=selected?`当前目录包含 ${result.fileCount} 个文件、${result.folders.length} 个子文件夹。导入时会一并读取子文件夹。`:'';
      $$('[data-browse]').forEach(b=>b.onclick=()=>safe(()=>browse(b.dataset.browse)));
      if(options.fileMode){
        selected='';$('#dialogSubmit').disabled=true;
        $('#browseFolders').insertAdjacentHTML('beforeend',(result.files||[]).map(f=>`<button type="button" data-pick-file="${esc(f.path)}"><span>▧</span><span>${esc(f.name)}</span><span>选择</span></button>`).join(''));
        $('#browseInfo').textContent=`${(result.files||[]).length} 个可选文件。点击文件后确认；仅添加此文件，不会读取同目录其他图片。`;
        $$('[data-pick-file]').forEach(b=>b.onclick=()=>{selected=b.dataset.pickFile;$('#browsePath').value=selected;$('#dialogSubmit').disabled=false;$$('[data-pick-file]').forEach(x=>x.classList.toggle('selected-file',x===b));});
        const exact=$$('[data-pick-file]').find(b=>b.dataset.pickFile.replaceAll('\\','/').toLowerCase()===String(path).replace(/^"|"$/g,'').replaceAll('\\','/').toLowerCase());if(exact)exact.click();
      }
    }catch(error){if(id===requestId&&pickerOpen()){$('#browseInfo').textContent=error.message;$('#browseFolders').innerHTML='';}throw error;}
  }
  $('#browseNative').onclick=()=>safe(async()=>{
    const button=$('#browseNative');button.disabled=true;button.textContent='等待选择…';
    const requestBefore=requestId;
    try {
      const result=await api('native-folder',{path:$('#browsePath').value});
      if(!pickerOpen()||requestBefore!==requestId||result.cancelled)return;
      await browse(result.path);
    } finally {if(pickerOpen()){button.disabled=false;button.textContent='浏览文件夹…';}}
  });
  $('#browseGo').onclick=()=>safe(()=>browse($('#browsePath').value));
  $('#browsePath').oninput=()=>{selected='';$('#dialogSubmit').disabled=true;};
  $('#browsePath').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();safe(()=>browse(e.target.value));}};
  await browse(initial||simpleDraft?.[role]||Object.values(simpleDraft||{}).find(Boolean)||'');
}
function renderSimple() {
  const simple=state.simple,report=simple?.report;
  if(!simpleDraft) simpleDraft={background:'',enemy:'',boss:'',...simple?.folders};
  const key=JSON.stringify([simple,state.busy]);
  if(!simpleDirty&&!simpleChecking&&key!==simpleKey){
    simpleKey=key;
    simpleDraft={background:'',enemy:'',boss:'',...simple?.folders};
    const roles=report?.roles||['background','enemy','boss'].map((id,i)=>({id,name:['背景','小怪','BOSS'][i],path:'',count:0,candidates:[],retained:[]}));
    $('#folderCards').innerHTML=roles.map(role=>{
      const details=role.candidates.flatMap(c=>c.details||[]),first=details[0],asset=first&&state.assets.find(a=>a.id===first.assetId),actions=[...new Set(details.map(d=>d.action))];
      const retained=[...new Set(role.retained.map(r=>r.action))];
      const targetSizes=[...new Set(details.filter(d=>d.targetWidth&&d.targetHeight).map(d=>d.targetWidth+' × '+d.targetHeight))];
      return `<div class="folder-card ${role.path?'configured':''} ${role.error?'invalid':''}"><div class="folder-card-head"><h2>${esc(role.name)}</h2><span class="folder-state">${role.error?'需要检查':role.path?'已选新素材':'保持原样'}</span></div><div class="folder-preview"><div class="folder-thumb">${asset&&['.png','.jpg','.jpeg','.webp','.gif'].includes(asset.extension)?`<img src="/media?id=${asset.id}" alt="${esc(asset.name)}">`:folderIcon}</div><div><strong>${role.error?'暂时无法对应':first?esc(first.asset):'不替换'+esc(role.name)}</strong><p>${first?(asset?.sequence?asset.frames+' 帧动画':'图片或视频')+' · '+role.count+' 套候选':'选择文件夹后自动识别'}</p></div></div><input class="folder-input" data-folder="${role.id}" aria-label="${esc(role.name)}新素材文件夹" value="${esc(simpleDraft[role.id])}" placeholder="选择文件夹，或在这里粘贴路径"><div class="folder-buttons"><button class="button" data-pick-folder="${role.id}">${role.path?'更换文件夹':'选择文件夹'}</button><button class="text-button" data-clear-folder="${role.id}" ${role.path?'':'hidden'}>不替换</button></div><p class="folder-note ${role.error?'folder-error':''}">${role.error?esc(role.error):first?'将替换'+esc(actions.join('、'))+'。'+(retained.length?esc(retained.join('、'))+'保留原素材。':''):role.id==='background'?'可放背景图片或视频。': '可放一套 PNG 序列，或移动、攻击等动作。'}</p>${first?`<p class="size-fit-note">✓ 自动适配原尺寸${targetSizes.length?' · '+esc(targetSizes.join(' / ')):''}<br>${role.id==='background'?'等比例铺满，居中裁边':'等比例缩放，脚底对齐'}</p>`:''}</div>`;
    }).join('');
    $$('[data-folder]').forEach(input=>{
      input.oninput=()=>{simpleDraft[input.dataset.folder]=input.value;simpleDirty=true;updateSimpleButtons();clearTimeout(simpleTimer);simpleTimer=setTimeout(()=>safe(checkSimpleFolders),650);};
      input.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();clearTimeout(simpleTimer);safe(checkSimpleFolders);}};
    });
    $$('[data-pick-folder]').forEach(button=>button.onclick=()=>safe(()=>chooseFolder(button.dataset.pickFolder)));
    $$('[data-clear-folder]').forEach(button=>button.onclick=()=>safe(async()=>{simpleDraft[button.dataset.clearFolder]='';simpleDirty=true;await checkSimpleFolders();}));
    $('#simpleCapacity').textContent=report?.total ? `当前可生成 ${report.total} 种不重复组合` : '先选择素材文件夹';
    const previousComp=$('#simpleComp').value;
    $('#simpleComp').innerHTML=(state.scan?.comps||[]).map(c=>`<option value="${esc(c.name)}" ${c.name===(previousComp||state.comp)?'selected':''}>${esc(c.name)} · ${Number((c.workAreaDuration??c.duration).toFixed(2))} 秒</option>`).join('');
    $('#simpleMapping').innerHTML=roles.flatMap(r=>r.candidates.map(c=>`<div class="mapping-line"><strong>${esc(r.name)} / ${esc(c.name)}</strong>${c.details.map(d=>`<span>${esc(d.action)}：${esc(d.target)} → ${esc(d.asset)}</span>`).join('')}</div>`)).join('')||'<p class="dialog-help">选定文件夹后会显示对应关系。</p>';
    $('#simpleIssues').hidden=!report?.issues.length;
    $('#simpleIssues').textContent=report?.issues.join('；')||'';
  }
  updateSimpleButtons();
  const recent=state.batches.find(b=>b.origin==='simple');
  $('#simpleRecent').innerHTML=recent?`<div class="recent-result"><span class="badge ${recent.rows.some(r=>r.status==='running')?'running':''}">最近一次</span><div><h3>${recent.rows.filter(r=>r.status==='done').length} / ${recent.rows.length} 份已生成</h3><p>${esc(recent.rows.length===1?(recent.rows[0].error||recent.rows[0].stage):'每份结果和缺失说明可在导出队列查看')}</p></div><button class="button small" id="viewSimpleResult">查看结果 ↗</button></div>`:'';
  if($('#viewSimpleResult'))$('#viewSimpleResult').onclick=()=>showTab('queue');
}
function updateSimpleButtons(){
  const report=state.simple?.report,count=Number($('#simpleCount').value),waiting=simpleDirty||simpleChecking;
  const invalid=!Number.isInteger(count)||count<1||count>Math.min(500,report?.total||0);
  $('#simpleProject').disabled=waiting||state.busy||!report?.canGenerate||invalid;
  $('#simpleVideo').disabled=waiting||state.busy||!report?.canRender||invalid;
  $('#checkFolders').disabled=simpleChecking;
  let message='至少为背景、小怪或 BOSS 选择一个文件夹。',tone='';
  if(!state.scan){message='请先点击右上角“重新扫描工程”。';}
  else if(waiting){message='正在识别文件夹和动作对应关系…';}
  else if(report?.issues.length){message='请检查上方标出的文件夹。识别清楚后即可生成。';tone='error';}
  else if(report?.canGenerate){
    if(invalid){message=`数量需要为 1–${Math.min(500,report.total)} 份；当前素材不足以生成更多不同组合。`;tone='attention';}
    else if(report.missing.length){message=`可以生成替换工程。原工程另外 ${report.missing.length} 项素材仍缺失，会保留在新工程中并附缺失清单；补齐后才能导出完整视频。`;tone='attention';}
    else{message='已准备好。直接生成新工程，或同时导出视频。';}
  }
  if(state.busy)message='正在生成，可在“导出队列”查看进度。';
  $('#simpleStatus').className='simple-status '+tone;$('#simpleStatus').textContent=message;
}
function checkSimpleFolders(){
  clearTimeout(simpleTimer);
  const snapshot={...simpleDraft};simpleChecking=true;updateSimpleButtons();
  const request=simpleCheckQueue.catch(()=>{}).then(()=>api('simple-check',{folders:snapshot}));
  simpleCheckQueue=request;
  return request.then(async result=>{
    if(JSON.stringify(snapshot)===JSON.stringify(simpleDraft)){simpleDirty=false;simpleChecking=false;state.simple=result;simpleKey='';await refresh();}
  }).catch(error=>{simpleChecking=false;simpleDirty=true;$('#simpleIssues').hidden=false;$('#simpleIssues').textContent=error.message;updateSimpleButtons();throw error;});
}
async function simpleExport(render){
  await checkSimpleFolders();
  const result=await api('simple-export',{folders:{...simpleDraft},count:Number($('#simpleCount').value),render,comp:$('#simpleComp').value});
  await refresh();showTab('queue');toast(render?'已开始生成工程和视频':'已开始生成替换工程');return result;
}
function renderAssets() {
  $('#slotCount').textContent = state.slots.length;
  $('#slots').innerHTML = state.slots.length ? state.slots.map((s,i) => `<button class="slot ${s.id===activeSlot?'active':''}" data-slot="${s.id}"><div class="slot-top"><span class="slot-icon">${['▧','♙','♜'][i%3]}</span><span>${s.candidates.length} 个候选</span></div><strong>${esc(s.name)}</strong><small>${s.targets.length > 1 ? '整套替换 · '+s.targets.length+' 项' : '单项素材替换'}</small></button>`).join('') : '<div class="empty">扫描工程后，在这里选择背景、敌人和 BOSS 的替换位置。</div>';
  $$('[data-slot]').forEach(el => el.onclick = () => {activeSlot=el.dataset.slot;renderAssets();});
  const slot = currentSlot();
  $('#selectionSummary').innerHTML = slot ? `<span>已选：</span>${slot.candidates.map(c => `<span class="chip">${esc(c.name)}<button data-remove="${c.id}" title="移除候选">×</button></span>`).join('')}${slot.candidates.length?'':'<span>点击下方素材添加候选</span>'}${slot.targets.length>1?'<button class="text-button" id="addPack">＋ 配置整套动作</button>':''}<button class="text-button" id="editCurrent">调整引用位置</button>` : '';
  $$('[data-remove]').forEach(el=>el.onclick=()=>safe(async()=>{const copy=structuredClone(state.slots);copy.find(s=>s.id===activeSlot).candidates=slot.candidates.filter(c=>c.id!==el.dataset.remove);await saveSlots(copy);}));
  if ($('#addPack')) $('#addPack').onclick=()=>packDialog();
  if ($('#editCurrent')) $('#editCurrent').onclick=()=>targetDialog(slot);
  const visible=state.assets.filter(a=>{
    const video=['.mp4','.mov','.avi'].includes(a.extension);
    return (filter==='all'||filter==='sequence'&&a.sequence||filter==='video'&&video||filter==='image'&&!a.sequence&&!video&&!['.wav','.mp3'].includes(a.extension))&&(`${a.name} ${a.folder}`.toLowerCase().includes(query.toLowerCase()));
  });
  $('#libraryCount').textContent=state.assets.length;
  $('#emptyLibrary').hidden=visible.length>0;
  $('#assetGrid').innerHTML=visible.map(a=>{
    const selected=slot?.candidates.some(c=>Object.values(c.mapping).includes(a.id));
    const video=['.mp4','.mov','.avi'].includes(a.extension);
    const picture=['.png','.jpg','.jpeg','.webp','.gif'].includes(a.extension);
    return `<button class="asset-card ${selected?'selected':''}" data-asset="${a.id}" title="${esc(a.name)}"><span class="asset-type">${a.sequence?'序列帧':a.extension.slice(1).toUpperCase()}</span><span class="asset-check">✓</span><div class="asset-image">${picture?`<img loading="lazy" src="/media?id=${a.id}" alt="${esc(a.name)}">`:video?`<video muted preload="metadata" src="/media?id=${a.id}#t=0.2"></video>`:'<span class="placeholder">♫</span>'}</div><div class="asset-copy"><strong>${esc(a.name)}</strong><small>${a.sequence?a.frames+' 帧 · ':''}${a.width?a.width+' × '+a.height:a.extension.slice(1).toUpperCase()} · ${(a.size/1048576).toFixed(1)} MB</small></div></button>`;
  }).join('');
  $$('[data-asset]').forEach(el=>el.onclick=()=>safe(()=>chooseAsset(el.dataset.asset)));
  $('#candidateTotal').textContent=state.slots.reduce((n,s)=>n+s.candidates.length,0)+' 个候选';
  $('#configSummary').innerHTML=state.slots.map(s=>`<div class="summary-row"><span>${esc(s.name)}</span><strong>${s.candidates.length ? s.candidates.length+' 个候选' : '保留原素材'}</strong></div>`).join('')||'<div class="summary-row">等待工程扫描</div>';
}
async function saveSlots(slots) { await api('config',{slots});editingPlans=false;await refresh(); }
async function chooseAsset(id) {
  const slot=currentSlot();
  if(!slot) return toast('请先扫描工程，再配置替换位置');
  if(slot.targets.length>1) return packDialog(id);
  const asset=state.assets.find(a=>a.id===id),copy=structuredClone(state.slots),next=copy.find(s=>s.id===activeSlot);
  const existing=next.candidates.find(c=>c.mapping[String(slot.targets[0])]===id);
  if(existing) next.candidates=next.candidates.filter(c=>c.id!==existing.id);
  else next.candidates.push({id:makeId(),name:asset.name,mapping:{[slot.targets[0]]:id}});
  await saveSlots(copy);
}
function dialog(title,body,onSave,label='保存') {
  dialogVersion++;$('#dialogSubmit').disabled=false;
  $('#dialogTitle').textContent=title;$('#dialogBody').innerHTML=body;$('#dialogSubmit').textContent=label;dialogSave=onSave;$('#dialog').showModal();
}
function packDialog(firstAsset) {
  const slot=currentSlot(),items=state.scan.items.filter(i=>slot.targets.includes(i.id));
  dialog('配置 '+slot.name+' 素材套装',`<p class="dialog-help">为这组素材的每个引用选择新素材。同一源素材在工程中所有引用都会一起替换。帧率、时长和角色位置请先用样片检查。</p><div class="field"><label>套装名称</label><input id="packName" required placeholder="例如：机器人 · 完整动作"></div>${items.map((item,i)=>`<div class="field"><label>${esc(item.name)}${item.missing?' · 原素材缺失':''}</label><select data-pack-target="${item.id}" required><option value="">请选择对应素材</option>${assetOptions(i===0?firstAsset:null)}</select></div>`).join('')}`,async()=>{
    const mapping={};$$('[data-pack-target]').forEach(s=>mapping[s.dataset.packTarget]=s.value);
    if(Object.values(mapping).some(x=>!x)) throw new Error('每个目标都需要指定素材');
    const copy=structuredClone(state.slots);copy.find(s=>s.id===activeSlot).candidates.push({id:makeId(),name:$('#packName').value.trim(),mapping});await saveSlots(copy);
  },'添加候选套装');
}
function targetDialog(slot=null) {
  if(!state.scan) return toast('请先点击“重新扫描工程”');
  const occupied=new Set(state.slots.filter(s=>s.id!==slot?.id).flatMap(s=>s.targets));
  const items=state.scan.items.filter(i=>!occupied.has(i.id));
  dialog(slot?'调整替换位置':'添加替换位置',`<div class="field"><label>名称</label><input id="slotName" required value="${esc(slot?.name||'')}" placeholder="背景 / 普通敌人 / BOSS"></div><p class="dialog-help">选择一个素材为单项替换；选择多个素材为整套替换。修改后此位置的候选与搭配清单会清空。一次替换会影响该源素材在工程中的全部引用。</p><div class="target-list">${items.map(i=>`<label class="target-option ${i.missing?'missing':''}"><input type="checkbox" data-target="${i.id}" ${slot?.targets.includes(i.id)?'checked':''}><span>${esc(i.name)} ${i.missing?'· 缺失':''}<small>${i.width} × ${i.height} · ${esc(i.uses.join(' / ')||'未被合成引用')}</small></span></label>`).join('')}</div>`,async()=>{
    const targets=$$('[data-target]:checked').map(el=>Number(el.dataset.target));
    if(!targets.length) throw new Error('至少选择一个素材');
    const copy=structuredClone(state.slots),entry={id:slot?.id||makeId(),name:$('#slotName').value.trim(),targets,candidates:[]};
    if(slot) copy.splice(copy.findIndex(s=>s.id===slot.id),1,entry);else copy.push(entry);
    activeSlot=entry.id;await saveSlots(copy);
  });
}
function slotsDialog() {
  if(!state.scan) return toast('请先完成 AE 工程扫描');
  dialog('管理替换位置',`<p class="dialog-help">扫描结果只提供工程引用。请确认自动建议的分组，必要时修改。</p>${state.slots.map(s=>`<div class="slot-editor"><button type="button" class="button" data-edit-slot="${s.id}">${esc(s.name)} · ${s.targets.length} 个引用</button><button type="button" class="text-button danger" data-delete-slot="${s.id}">移除</button></div>`).join('')}<button class="button" type="button" id="newSlot">＋ 添加替换位置</button>`,async()=>{},'完成');
  $$('[data-edit-slot]').forEach(b=>b.onclick=()=>{$('#dialog').close();targetDialog(state.slots.find(s=>s.id===b.dataset.editSlot));});
  $$('[data-delete-slot]').forEach(b=>b.onclick=()=>safe(async()=>{await saveSlots(state.slots.filter(s=>s.id!==b.dataset.deleteSlot));$('#dialog').close();slotsDialog();}));
  $('#newSlot').onclick=()=>{$('#dialog').close();targetDialog();};
}
function renderPlans() {
  const active=state.slots.filter(s=>s.candidates.length);
  $('#capacity').textContent=active.length?active.reduce((n,s)=>n*s.candidates.length,1).toLocaleString():0;
  $('#tableCount').textContent=state.plans.length;
  $('#plansTable').innerHTML=state.plans.length?`<table><thead><tr><th>#</th><th>作品名称</th>${active.map(s=>`<th>${esc(s.name)}</th>`).join('')}<th></th></tr></thead><tbody>${state.plans.map((p,i)=>`<tr><td>${String(i+1).padStart(2,'0')}</td><td><input aria-label="作品名称 ${i+1}" data-name="${p.id}" value="${esc(p.name)}"></td>${active.map(s=>`<td><select aria-label="${esc(s.name)}搭配 ${i+1}" data-plan="${p.id}" data-choice="${s.id}">${s.candidates.map(c=>`<option value="${c.id}" ${p.choices[s.id]===c.id?'selected':''}>${esc(c.name)}</option>`).join('')}</select></td>`).join('')}<td><button class="text-button" data-delete-plan="${p.id}" title="移除这一份">×</button></td></tr>`).join('')}</tbody></table>`:'<div class="empty">还没有迭代搭配。先添加候选素材，再选择数量生成。</div>';
  $$('[data-choice]').forEach(el=>el.onchange=()=>{state.plans.find(p=>p.id===el.dataset.plan).choices[el.dataset.choice]=el.value;editingPlans=true;});
  $$('[data-name]').forEach(el=>el.oninput=()=>{state.plans.find(p=>p.id===el.dataset.name).name=el.value;editingPlans=true;});
  $$('[data-delete-plan]').forEach(el=>el.onclick=()=>{state.plans=state.plans.filter(p=>p.id!==el.dataset.deletePlan);editingPlans=true;renderPlans();});
  $('#comp').innerHTML=(state.scan?.comps||[]).map(c=>`<option value="${esc(c.name)}" ${c.name===state.comp?'selected':''}>${esc(c.name)} · ${Number((c.workAreaDuration??c.duration).toFixed(2))} 秒</option>`).join('');
}
function renderQueue() { renderExportQueue(); }
async function safe(fn) { try {await fn();} catch(e) {toast(e.message);} }
async function savePlans() {await api('save-plans',{plans:state.plans});editingPlans=false;await refresh();}
async function startExport(sample) {
  const render=$('#render').checked,comp=$('#comp').value;
  await savePlans();
  await api('export',{render,comp,ids:sample?state.plans.slice(0,1).map(p=>p.id):state.plans.map(p=>p.id)});
  showTab('queue');await refresh();toast('任务已加入队列');
}
$$('[data-tab]').forEach(b=>b.onclick=()=>showTab(b.dataset.tab));
$$('[data-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;$$('[data-filter]').forEach(el=>el.classList.toggle('active',el===b));renderAssets();});
$('#search').oninput=e=>{query=e.target.value;renderAssets();};
$('#primaryAction').onclick=()=>showTab('plans');
$('#simpleCount').oninput=updateSimpleButtons;
$('#checkFolders').onclick=()=>safe(checkSimpleFolders);
$('#simpleProject').onclick=()=>safe(()=>simpleExport(false));
$('#simpleVideo').onclick=()=>safe(()=>simpleExport(true));
$('#editSlots').onclick=slotsDialog;
$('#import').onclick=()=>dialog('导入本地素材目录','<div class="field"><label>素材目录完整路径</label><input id="folderPath" required placeholder="E:\\素材库\\角色"><small>读取目录和子目录。连续编号图片按序列分组，源文件不会被复制或修改。</small></div>',async()=>{const result=await api('import',{path:$('#folderPath').value.trim().replace(/^"|"$/g,'')});await refresh();toast(`已读取 ${result.count} 个素材项`);},'读取素材');
async function scanProject(project) {
  if(!state.aeAvailable){await showEnvironment();throw new Error('请先设置本机 AE 路径，再导入工程');}
  projectScanPending=true;renderHeader();$('#scan').textContent='正在等待 AE…';
  try {await api('scan',{project});await refresh();showTab('catalog');toast('工程扫描完成');}
  finally {projectScanPending=false;renderHeader();$('#scan').textContent='重新扫描工程';}
}
$('#scan').onclick=()=>safe(()=>scanProject(state.project));
$('#changeProject').onclick=()=>safe(importProjectFolder);
$('#generate').onclick=()=>safe(async()=>{await api('plan',{count:Number($('#quantity').value),seed:makeId()});editingPlans=false;await refresh();toast('搭配已生成并保存');});
$('#savePlans').onclick=()=>safe(async()=>{await savePlans();toast('调整已保存，无重复搭配');});
$('#downloadManifest').onclick=()=>safe(async()=>{await savePlans();const data=await api('manifest'),blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='AE迭代搭配.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);});
$('#sample').onclick=()=>safe(()=>startExport(true));$('#exportAll').onclick=()=>safe(()=>startExport(false));
$('#cancel').onclick=()=>safe(async()=>{const r=await api('cancel',{});toast(r.message);});
$('#openOutput').onclick=()=>safe(()=>api('open-output',{}));
$('#closeDialog').onclick=$('#cancelDialog').onclick=()=>$('#dialog').close();
$('#dialogForm').onsubmit=async e=>{e.preventDefault();const version=dialogVersion,submit=dialogSave;$('#dialogSubmit').disabled=true;try{await submit();if(version===dialogVersion)$('#dialog').close();}catch(error){toast(error.message);}finally{if(version===dialogVersion)$('#dialogSubmit').disabled=false;}};
safe(async()=>{await refresh();showTab('catalog');});
const pollTimer=setInterval(()=>safe(()=>refresh(false)),3500);
