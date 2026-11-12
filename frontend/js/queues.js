const queueView={page:1,size:5,query:'',status:'',expanded:new Map(),rows:new Map(),stamp:''};
function pageSlice(items,page,size){const pages=Math.max(1,Math.ceil(items.length/size));page=Math.max(1,Math.min(page,pages));return {items:items.slice((page-1)*size,page*size),page,pages,total:items.length};}
function pagerMarkup(p,key){return `<div class="queue-pager"><span>共 ${p.total} 项 · 第 ${p.page} / ${p.pages} 页</span><button class="button small" data-page="${key}" data-to="${p.page-1}" ${p.page===1?'disabled':''}>上一页</button><button class="button small" data-page="${key}" data-to="${p.page+1}" ${p.page===p.pages?'disabled':''}>下一页</button></div>`;}
function batchStatus(b){return b.rows.some(r=>r.status==='running')?'running':b.rows.some(r=>r.status==='failed')?'failed':b.rows.every(r=>r.status==='done')?'done':b.rows.some(r=>r.status==='waiting')?'waiting':'interrupted';}
const jobLabels={waiting:'等待',running:'进行中',done:'已完成',failed:'失败',interrupted:'已暂停',submitting:'正在提交',queued:'排队中',downloading:'下载并校验'};
function videoSpec(s){if(!s)return '原合成尺寸 / 帧率 · H.264';return `${s.width?s.width+' × '+s.height:'原合成尺寸'} · ${s.fps?s.fps+' fps':'原帧率'} · ${s.mode==='bitrate'?s.bitrate+' Mbps':'CRF '+s.crf} · ${s.audio?'有声（若原片有音轨）':'静音'}`;}
function renderExportQueue(){
 const q=queueView;
 if(!$('#queueSearch')){
  const tools=document.createElement('div');tools.className='queue-tools';tools.innerHTML='<input id="queueSearch" placeholder="搜索工程名、作品名或批次编号" aria-label="搜索导出队列"><select id="queueStatus" aria-label="任务状态"><option value="">全部状态</option><option value="running">进行中</option><option value="waiting">等待</option><option value="done">已完成</option><option value="failed">失败</option><option value="interrupted">已暂停</option></select><select id="queueSize" aria-label="每页批次"><option value="5">每页 5 批</option><option value="10">每页 10 批</option><option value="20">每页 20 批</option></select>';
  $('#batches').before(tools);
  $('#queueSearch').oninput=e=>{q.query=e.target.value;q.page=1;renderExportQueue();};
  $('#queueStatus').onchange=e=>{q.status=e.target.value;q.page=1;renderExportQueue();};
  $('#queueSize').onchange=e=>{q.size=Number(e.target.value);q.page=1;renderExportQueue();};
 }
 const term=q.query.trim().toLowerCase();
 const filtered=state.batches.filter(b=>(!q.status||batchStatus(b)===q.status)&&(!term||[b.project,b.id,...b.rows.map(r=>r.name)].join(' ').toLowerCase().includes(term)));
 const p=pageSlice(filtered,q.page,q.size);q.page=p.page;
 const stamp=JSON.stringify([p,state.busy,Array.from(q.expanded),Array.from(q.rows)]);
 if(stamp===q.stamp)return;q.stamp=stamp;
 $('#batches').innerHTML=p.items.map(b=>{
  const status=batchStatus(b),open=q.expanded.has(b.id)?q.expanded.get(b.id):status==='running';
  const rp=pageSlice(b.rows,q.rows.get(b.id)||1,10);
  const title=b.project.split(/[\\/]/).pop().replace(/\.aep$/i,'');
  const date=b.created||b.id.replace(/^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2}).*/,'$1-$2-$3 $4:$5:$6');
  return `<details class="batch compact-batch" data-batch="${esc(b.id)}" ${open?'open':''}><summary><span class="badge ${status}">${jobLabels[status]}</span><div class="batch-title"><strong>${esc(title)}</strong><small>${esc(date)} · ${esc(b.comp||'')} · ${b.render?'工程 + MP4':'仅 AE 工程'}</small></div><strong class="batch-count">${b.rows.filter(r=>r.status==='done').length} / ${b.rows.length}</strong><span class="expand-hint">展开 / 收起</span></summary><div class="batch-meta"><span>批次 ${esc(b.id)}${b.render?'<br>'+esc(videoSpec(b.videoSettings)):''}</span><button class="button small" data-retry="${esc(b.id)}" ${state.busy||b.rows.every(r=>r.status==='done')?'disabled':''}>重试未完成项</button></div>${rp.items.map(r=>`<div class="job-row"><span class="badge ${r.status}">${r.status==='done'&&r.missing?.length?'待补素材':jobLabels[r.status]||esc(r.status)}</span><div class="job-detail"><strong>${esc(r.name)}</strong><p>${esc(r.error||r.stage)}</p>${r.missing?.length?`<p>待补素材：${r.missing.map(esc).join('、')}</p>`:''}</div>${r.project?`<button class="button small" data-open-batch="${esc(b.id)}" data-open-row="${esc(r.id)}">打开结果 ↗</button>`:''}</div>`).join('')}${rp.pages>1?pagerMarkup(rp,b.id):''}</details>`;
 }).join('')||'<div class="empty">没有符合条件的导出任务</div>';
 $('#batches').insertAdjacentHTML('beforeend',pagerMarkup(p,'batches'));
 $('#batches').querySelectorAll('[data-batch]').forEach(d=>d.ontoggle=()=>{q.expanded.set(d.dataset.batch,d.open);});
 $('#batches').querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{if(b.dataset.page==='batches')q.page=Number(b.dataset.to);else q.rows.set(b.dataset.page,Number(b.dataset.to));renderExportQueue();});
 $$('[data-open-row]').forEach(b=>b.onclick=()=>safe(()=>api('open-result',{batchId:b.dataset.openBatch,rowId:b.dataset.openRow})));
 $$('[data-retry]').forEach(b=>b.onclick=()=>safe(async()=>{await api('retry',{id:b.dataset.retry});await refresh(false);}));
 $('#cancel').disabled=!state.busy;
}

function generationHistory(container,e,project){
 let jobs=[],page=1,status='',query='',stamp='';const expanded=new Map();
 container.innerHTML='<details class="generation-history" open><summary>生成记录 <span class="history-count"></span></summary><div class="queue-tools"><input class="history-search" aria-label="搜索生成记录" placeholder="搜索提示词、时间、任务编号"><select class="history-status" aria-label="生成状态"><option value="">全部状态</option><option value="active">进行中</option><option value="done">已完成</option><option value="failed">失败 / 中断</option></select></div><div class="history-list"></div></details>';
 const root=container.querySelector('.history-list');
 function render(){
  const term=query.trim().toLowerCase();
  const found=jobs.filter(j=>(!status||(status==='active'?!['done','failed','interrupted'].includes(j.status):status==='failed'?['failed','interrupted'].includes(j.status):j.status===status))&&(!term||[j.prompt,j.created,j.id].join(' ').toLowerCase().includes(term))).sort((a,b)=>b.created.localeCompare(a.created));
  const p=pageSlice(found,page,5);page=p.page;
  container.querySelector('.history-count').textContent=`（${jobs.length}）`;
  root.innerHTML=p.items.map(j=>`<details class="generation-result" data-job="${esc(j.id)}" ${expanded.get(j.id)?'open':''}><summary><span class="badge ${j.status}">${jobLabels[j.status]||esc(j.status)}</span><strong>${j.kind==='video'?'视频':'图片'}</strong><small>${esc(j.created)}</small></summary><p class="job-prompt">${esc(j.prompt||'')}</p><small>任务 ${esc(j.id)} · ${esc(j.model||'')}</small>${j.status==='done'?`${j.kind==='video'?`<video controls loop preload="none" src="/generation-media?id=${encodeURIComponent(j.id)}"></video>`:`<img loading="lazy" src="/generation-media?id=${encodeURIComponent(j.id)}" alt="生成结果">`}<div class="media-actions"><a class="button small" href="/generation-media?id=${encodeURIComponent(j.id)}" download="${j.kind==='video'?'video.mp4':'image.png'}">下载结果</a>${e.replaceable?`<button class="button small primary" data-apply-generation="${esc(j.id)}">用作替换素材</button>`:''}</div>`:`<p>${esc(j.error||'任务正在处理，可以关闭窗口稍后查看。')}</p>${j.remoteId&&['failed','interrupted'].includes(j.status)?`<button class="button small" data-resume-generation="${esc(j.id)}">继续查询原任务</button>`:''}`}</details>`).join('')||'<p class="dialog-help">没有符合条件的生成记录</p>';
  root.insertAdjacentHTML('beforeend',pagerMarkup(p,'history'));
  root.querySelectorAll('[data-job]').forEach(d=>d.ontoggle=()=>{expanded.set(d.dataset.job,d.open);if(!d.open)d.querySelectorAll('video').forEach(v=>v.pause());});
  root.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{root.querySelectorAll('video').forEach(v=>v.pause());page=Number(b.dataset.to);render();});
  root.querySelectorAll('[data-apply-generation]').forEach(b=>b.onclick=()=>safe(async()=>{await api('generation-apply',{project,target:e.id,id:b.dataset.applyGeneration});await refresh(false);toast('已选作替换素材，原工程尚未改变');}));
  root.querySelectorAll('[data-resume-generation]').forEach(b=>b.onclick=()=>safe(async()=>{await api('generation-resume',{id:b.dataset.resumeGeneration});toast('已继续查询原任务');}));
 }
 container.querySelector('.history-search').oninput=e=>{query=e.target.value;page=1;render();};
 container.querySelector('.history-status').onchange=e=>{status=e.target.value;page=1;render();};
 container.querySelector('.generation-history').ontoggle=event=>{if(!event.target.open)root.querySelectorAll('video').forEach(v=>v.pause());};
 return next=>{const key=JSON.stringify(next);if(key===stamp)return;stamp=key;jobs=next;render();};
}
if(typeof module!=='undefined')module.exports={pageSlice,batchStatus};
