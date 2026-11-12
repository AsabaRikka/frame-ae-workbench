async function showEnvironment(){
  const env=await api('environment');
  dialog('环境设置',`<p class="dialog-help">工作台已内置运行和视频处理组件。扫描、预览和导出仍需要这台电脑安装 After Effects。当前主要验证版本为 AE 2022。</p><div class="field"><label for="aeExecutable">AE 安装目录或 AfterFX.exe 路径</label><input id="aeExecutable" value="${esc(env.aePath)}" placeholder="例如 C:\\Program Files\\Adobe\\Adobe After Effects 2022"><small>安装目录、Support Files 目录、AfterFX.exe 完整路径均可。</small></div><div class="folder-buttons"><button type="button" class="button" id="browseAeInstall">浏览 AE 安装目录</button><button type="button" class="button" id="detectAeInstall">重新检测</button></div><div id="aeCandidates"></div><p class="dialog-help">AE：${env.aeAvailable?'已找到':'尚未配置'} · 视频渲染：${env.renderAvailable?'可用':'尚未找到'}<br>FFmpeg：${env.ffmpegAvailable?'可用':'缺失'} · FFprobe：${env.ffprobeAvailable?'可用':'缺失'}<br>配置与预览：${esc(env.data)}<br>输出目录：${esc(env.output)}</p><p class="dialog-help">首次使用时，请在 AE 的“首选项 → 脚本与表达式”中允许脚本写入文件。工程用到的插件、字体和素材也需要齐全。</p>`,async()=>{await api('settings',{aePath:$('#aeExecutable').value});await refresh();toast('AE 路径已保存');},'保存设置');
  function candidates(values){
    $('#aeCandidates').innerHTML=values.length?`<p class="dialog-help">检测到的 AE 安装（点击选择）：</p>${values.map(p=>`<button type="button" class="text-button" data-ae-path="${esc(p)}">${esc(p)}</button>`).join('<br>')}`:'<p class="dialog-help">未自动找到 AE。可以浏览安装目录或粘贴路径。</p>';
    $$('[data-ae-path]').forEach(b=>b.onclick=()=>$('#aeExecutable').value=b.dataset.aePath);
  }
  candidates(env.candidates);
  $('#detectAeInstall').onclick=()=>safe(async()=>{const next=await api('environment');candidates(next.candidates);if(next.candidates.length===1)$('#aeExecutable').value=next.candidates[0];});
  $('#browseAeInstall').onclick=()=>safe(()=>chooseFolder('',async folder=>{await api('settings',{aePath:folder});await refresh();toast('AE 路径已保存');},env.aePath?.replace(/[\\/][^\\/]+$/,'')||'',{title:'选择 AE 安装目录',label:'使用此 AE 安装',help:'进入 Adobe After Effects 安装目录或其中的 Support Files 文件夹。'}));
}
$('#environmentSettings').onclick=()=>safe(showEnvironment);
$('#setupEnvironment').onclick=()=>safe(showEnvironment);
$('#shutdownApp').onclick=()=>safe(async()=>{await api('shutdown',{});clearInterval(pollTimer);$('#connection').textContent='工作台已退出';$('#shutdownApp').disabled=true;toast('工作台已退出，可以关闭页面；下次双击启动程序即可。');});
