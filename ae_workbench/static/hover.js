// Only the hovered card plays. A short dwell avoids preparing previews while passing over cards.
(() => {
  const jobs = new Map();
  let active = null;
  function stop() {
    const current = active; active = null;
    if (!current) return;
    clearTimeout(current.timer); cancelAnimationFrame(current.raf);
    current.video?.pause();
    if (current.video) {current.video.removeAttribute('src'); current.video.load();}
    current.card.classList.remove('hover-playing');
    current.layer?.remove(); current.status?.remove();
  }
  window.stopCatalogHover = stop;
  const alive = current => active === current && current.card.isConnected && !document.hidden && !document.querySelector('dialog[open]');
  function badge(current, text) {
    if (!current.status) {current.status=document.createElement('span');current.status.className='hover-status';current.card.append(current.status);}
    current.status.textContent=text;
  }
  async function motion(current) {
    const key=JSON.stringify([current.project,current.scannedAt,current.entry.id]);
    if (!jobs.has(key)) {
      const request=api('animation',{project:current.project,target:current.entry.id});
      jobs.set(key,request);
      request.catch(()=>{if(jobs.get(key)===request)jobs.delete(key);});
      if(jobs.size>32)jobs.delete(jobs.keys().next().value);
    }
    let result=await jobs.get(key);
    while(result.status==='running' && alive(current)) {
      await new Promise(resolve=>setTimeout(resolve,450));
      if(!alive(current))return null;
      result=await api('animation-status?id='+encodeURIComponent(result.id));
      jobs.set(key,Promise.resolve(result));
    }
    if(!alive(current))return null;
    if(result.status!=='done'){jobs.delete(key);throw new Error(result.error||'动画预览未完成');}
    return result;
  }
  async function play(current) {
    if(!alive(current))return;
    badge(current,'准备动画…');
    try {
      const result=await motion(current);
      if(!result||!alive(current))return;
      current.layer=document.createElement('div');current.layer.className='hover-preview-layer';current.card.append(current.layer);
      if(result.player==='video') {
        const video=document.createElement('video');current.video=video;
        video.muted=true;video.loop=true;video.playsInline=true;
        video.src='/animation-frame?id='+encodeURIComponent(result.id);current.layer.append(video);
        await video.play();
        if(!alive(current))return;
        current.card.classList.add('hover-playing');badge(current,'播放中 · 移开停止');
        return;
      }
      if(!result.frameCount||!result.durations?.length)throw new Error('动画没有可播放的帧');
      const canvas=document.createElement('canvas');current.layer.append(canvas);const ctx=canvas.getContext('2d');
      const frames=new Map();let last=-1,started=performance.now();
      const times=[0];result.durations.forEach(d=>times.push(times.at(-1)+Math.max(1,d)));
      function frame(index) {
        if(!frames.has(index)) {
          const image=new Image();const promise=new Promise((resolve,reject)=>{image.onload=()=>resolve(image);image.onerror=()=>reject(new Error('动画帧加载失败'));});
          image.src=`/animation-frame?id=${encodeURIComponent(result.id)}&frame=${index}`;
          frames.set(index,promise);if(frames.size>24)frames.delete(frames.keys().next().value);
        }
        return frames.get(index);
      }
      async function draw(index) {
        const image=await frame(index);
        if(!alive(current))return;
        canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0);
        current.card.classList.add('hover-playing');badge(current,`${index+1} / ${result.frameCount} 帧 · 移开停止`);
        last=index;frame((index+1)%result.frameCount).catch(()=>{});
      }
      await draw(0);started=performance.now();
      async function tick(now) {
        if(!alive(current))return;
        const elapsed=(now-started)%times.at(-1);let index=0;
        while(index<result.frameCount-1&&times[index+1]<=elapsed)index++;
        try {if(index!==last)await draw(index);}
        catch(error){if(alive(current)){current.card.classList.remove('hover-playing');current.layer.remove();badge(current,'预览失败 · 点击查看');current.status.title=error.message;}return;}
        if(alive(current))current.raf=requestAnimationFrame(tick);
      }
      if(alive(current))current.raf=requestAnimationFrame(tick);
    } catch(error) {
      if(alive(current)){current.card.classList.remove('hover-playing');current.layer?.remove();badge(current,'预览暂不可用 · 点击查看');current.status.title=error.message;}
    }
  }
  window.bindCatalogHover = function() {
    stop();
    document.querySelectorAll('#catalogGrid .catalog-image[data-detail]').forEach(card=>{
      const entry=state.catalog.find(e=>String(e.id)===card.dataset.detail);
      if(!entry?.animated||entry.missing)return;
      card.classList.add('hover-capable');card.title='鼠标停留播放动画；点击打开完整预览和 AI 生成';
      card.addEventListener('pointerenter',event=>{
        if(event.pointerType==='touch'||document.querySelector('dialog[open]'))return;
        stop();const current={card,entry,project:state.project,scannedAt:state.scan?.scannedAt};active=current;
        current.timer=setTimeout(()=>play(current),entry.mediaKind==='composition'?650:300);
      });
      card.addEventListener('pointerleave',()=>{if(active?.card===card)stop();});
      card.addEventListener('click',stop);
    });
  };
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
  window.addEventListener('blur',stop);
  window.addEventListener('scroll',()=>{if(active){const r=active.card.getBoundingClientRect();if(r.bottom<0||r.top>innerHeight)stop();}},true);
  if(typeof state!=='undefined'&&state)window.bindCatalogHover();
})();
