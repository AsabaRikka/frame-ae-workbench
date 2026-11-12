let combinationDraft=null,combinationProject='',combinationSignature='',combinationDirty=false,combinationPage=1,combinationStamp='';
const combinationChecked=new Set();
function selectedCandidateIds(c){return c?.selectedIds??(c?.selected==='*'?c.assetIds:c?.selected?[c.selected]:[]);}
function catalogCapacity(){const groups=Object.values(state.catalogChoices||{}).map(selectedCandidateIds).filter(x=>x.length);return groups.length?groups.reduce((n,x)=>n*x.length,1):0;}
function candidatePicture(a){if(!a)return '<span>素材不存在</span>';return ['.png','.jpg','.jpeg','.webp','.gif'].includes(a.extension)?`<img loading="lazy" src="/media?id=${encodeURIComponent(a.id)}" alt="${esc(a.name)}">`:`<span>${['.wav','.mp3'].includes(a.extension)?'♫ 音频':'▶ 视频'}</span>`;}
async function manageCandidates(id){
 const e=state.catalog.find(x=>String(x.id)===String(id));if(!e)return;
 const project=state.project,c=state.catalogChoices?.[id],selected=new Set(selectedCandidateIds(c));
 const sequence=e.mediaKind==='sequence';
 dialog('替换候选 · '+e.name,`<p class="dialog-help">每次添加会保留已有候选。勾选参与随机组合的素材；不勾选的候选暂不参与。${sequence?'序列帧请选包含整套连续编号图片的文件夹。':'单图可直接选择一个文件，也可从多个文件夹追加候选。'}</p>${e.kind==='group'?'<p class="catalog-warning">替换整个组合会替换其内部动画，外层图层动画保留。不能同时替换父组合和内部素材。</p>':''}<div class="candidate-actions">${sequence?'':'<button type="button" class="button primary" id="candidateAddFile">＋ 选择单个文件</button>'}<button type="button" class="button" id="candidateAddFolder">＋ ${sequence?'添加序列帧文件夹':'从文件夹添加候选'}</button></div><div class="candidate-list">${(c?.assetIds||[]).map(aid=>{const a=state.assets.find(x=>x.id===aid);return `<div class="candidate-option"><label><input type="checkbox" data-candidate-check="${esc(aid)}" ${selected.has(aid)?'checked':''}><span class="candidate-thumb">${candidatePicture(a)}</span><span><strong>${esc(a?.name||aid)}</strong><small>${a?.sequence?'序列帧 · '+a.frames+' 帧':'单文件'} · ${a?.width||'—'} × ${a?.height||'—'}</small><small title="${esc(a?.path)}">${esc(a?.path)}</small></span></label><button type="button" class="button small" data-preview-candidate="${esc(aid)}">预览</button><button type="button" class="text-button" data-remove-candidate="${esc(aid)}">移除</button></div>`;}).join('')||'<p class="dialog-help">尚未添加候选。先选择图片或序列帧文件夹。</p>'}</div><p class="dialog-help">改变候选后，现有组合计划需要重新生成；已导出的批次保留。</p>`,async()=>{
  if(c&&JSON.stringify([...selected].sort())!==JSON.stringify(selectedCandidateIds(c).slice().sort()))await catalogSelect({project,target:id,selectedIds:[...selected]});
 },'保存候选');
 $$('[data-candidate-check]').forEach(box=>box.onchange=()=>{if(box.checked)selected.add(box.dataset.candidateCheck);else selected.delete(box.dataset.candidateCheck);});
 $$('[data-preview-candidate]').forEach(b=>b.onclick=()=>previewCandidate(b.dataset.previewCandidate));
 $$('[data-remove-candidate]').forEach(b=>b.onclick=()=>safe(async()=>{await catalogSelect({project,target:id,removeId:b.dataset.removeCandidate,selectedIds:[...selected]});await manageCandidates(id);}));
 async function add(fileMode){
  if(c&&JSON.stringify([...selected].sort())!==JSON.stringify(selectedCandidateIds(c).slice().sort()))await catalogSelect({project,target:id,selectedIds:[...selected]});
  await chooseFolder(e.name,async path=>{await catalogSelect({project,target:id,...(fileMode?{file:path}:{folder:path})});await manageCandidates(id);},c?.folder||e.path?.replace(/[\\/][^\\/]+$/,'')||'',{fileMode,title:fileMode?'选择单个替换文件':'添加候选文件夹',label:fileMode?'添加此文件':'添加此文件夹',help:fileMode?'点击文件夹进入，再点击要用的图片文件。也可直接粘贴完整文件路径；只添加选中的文件。':'进入素材目录后确认。新候选会追加到当前列表，不会覆盖已有候选。'});
 }
 if($('#candidateAddFile'))$('#candidateAddFile').onclick=()=>safe(()=>add(true));
 $('#candidateAddFolder').onclick=()=>safe(()=>add(false));
}
function renderCombinationPlans(force=false){
 const plans=state.catalogPlans||[];
 if(combinationDraft===null||combinationProject!==state.project||combinationSignature!==(state.catalogPlanSignature||'')){
  combinationProject=state.project;combinationSignature=state.catalogPlanSignature||'';combinationDraft=structuredClone(plans);combinationDirty=false;combinationPage=1;combinationChecked.clear();plans.forEach(p=>combinationChecked.add(p.id));$('#combinationQuantity').value=plans.length||1;force=true;
 }else if(!combinationDirty&&JSON.stringify(plans)!==JSON.stringify(combinationDraft)){combinationDraft=structuredClone(plans);force=true;}
 $('#combinationCount').textContent=plans.length;
 $('#combinationSummary').textContent=`${combinationDraft.length} 份组合计划${combinationDirty?' · 有未保存调整':''}`;
 const busy=state.busy||state.scanning;
 $('#combinationSelected').textContent=`已勾选 ${combinationChecked.size} 份`;
 $('#catalogAep').disabled=busy||!combinationChecked.size;$('#catalogVideo').disabled=busy||!combinationChecked.size||Boolean(state.scan?.missing?.length);
 $('#combinationSave').disabled=busy||!combinationDirty;
 $('#combinationQuantity').max=Math.max(1,combinationDraft.length);$('#combinationSelectCount').disabled=!combinationDraft.length;
 if(!force&&$('#combinationList').contains(document.activeElement))return;
 const p=pageSlice(combinationDraft,combinationPage,5);combinationPage=p.page;
 const stamp=JSON.stringify([p,Array.from(combinationChecked),state.catalogChoices,combinationSignature]);if(!force&&stamp===combinationStamp)return;combinationStamp=stamp;
 const assets=new Map(state.assets.map(a=>[a.id,a])),entries=new Map(state.catalog.map(e=>[String(e.id),e]));
 $('#combinationList').innerHTML=p.items.map(plan=>`<article class="combination-card"><div class="combination-head"><label><input type="checkbox" data-plan-check="${plan.id}" ${combinationChecked.has(plan.id)?'checked':''}> 导出</label><input data-plan-name="${plan.id}" value="${esc(plan.name)}" maxlength="150" aria-label="作品名称"></div><div class="combination-materials">${Object.entries(plan.choices).map(([slot,aid])=>{const id=slot.replace('catalog-',''),e=entries.get(id),a=assets.get(aid),ids=selectedCandidateIds(state.catalogChoices?.[id]);return `<div class="combination-material"><strong>${esc(e?.name||id)}</strong><div class="combination-pair"><div>${e?originalPicture(e):''}<small>原素材</small></div><span>→</span><button type="button" data-plan-preview="${esc(aid)}">${candidatePicture(a)}<small>${a?.sequence?'序列帧':'替换素材'} · 点击预览</small></button></div><select data-plan-choice="${plan.id}" data-slot="${esc(slot)}" aria-label="${esc(e?.name||id)}的替换方案">${ids.map(i=>`<option value="${esc(i)}" ${i===aid?'selected':''}>${esc(assets.get(i)?.name||i)}</option>`).join('')}</select></div>`;}).join('')}</div></article>`).join('')||'<div class="empty">还没有组合计划。回到工程素材，添加候选后点击“生成不同组合计划”。</div>';
 $('#combinationList').insertAdjacentHTML('beforeend',pagerMarkup(p,'combinations'));
 $$('[data-plan-check]').forEach(b=>b.onchange=()=>{if(b.checked)combinationChecked.add(b.dataset.planCheck);else combinationChecked.delete(b.dataset.planCheck);$('#combinationQuantity').value=combinationChecked.size;renderCombinationPlans();});
 $$('[data-plan-name]').forEach(input=>input.oninput=()=>{combinationDraft.find(p=>p.id===input.dataset.planName).name=input.value;combinationDirty=true;renderCombinationPlans();});
 $$('[data-plan-choice]').forEach(input=>input.onchange=()=>{combinationDraft.find(p=>p.id===input.dataset.planChoice).choices[input.dataset.slot]=input.value;combinationDirty=true;renderCombinationPlans(true);});
 $$('[data-plan-preview]').forEach(b=>b.onclick=()=>previewCandidate(b.dataset.planPreview));
 $('#combinationList').querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{combinationPage=Number(b.dataset.to);renderCombinationPlans(true);});
}
async function saveCombinationPlans(){
 if(!combinationDraft?.length)throw new Error('请先生成组合计划');
 await api('catalog-plan-save',{project:combinationProject,signature:combinationSignature,plans:combinationDraft});combinationDirty=false;await refresh(false);
}
async function exportCombinationPlans(render){
 await saveCombinationPlans();
 const ids=combinationDraft.filter(p=>combinationChecked.has(p.id)).map(p=>p.id);
 if(!ids.length)throw new Error('请至少勾选一份组合计划');
 await api('catalog-export',{project:combinationProject,signature:combinationSignature,ids,comp:$('#catalogComp').value,render});await refresh(false);showTab('queue');toast(`已按所选组合提交 ${ids.length} 份任务`);
}
$('#combinationBack').onclick=()=>showTab('catalog');
$('#combinationSave').onclick=()=>safe(async()=>{await saveCombinationPlans();toast('组合计划已保存');});
$('#combinationSelectCount').onclick=()=>safe(()=>{const n=Number($('#combinationQuantity').value);if(!Number.isInteger(n)||n<1||n>combinationDraft.length)throw new Error('数量必须介于 1 和计划总数之间');combinationChecked.clear();combinationDraft.slice(0,n).forEach(p=>combinationChecked.add(p.id));renderCombinationPlans(true);});
$('#combinationQuantity').oninput=()=>{const n=Number($('#combinationQuantity').value);combinationChecked.clear();if(Number.isInteger(n)&&n>=1&&n<=combinationDraft.length)combinationDraft.slice(0,n).forEach(p=>combinationChecked.add(p.id));renderCombinationPlans(true);};
