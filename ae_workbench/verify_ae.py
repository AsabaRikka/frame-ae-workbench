"""An isolated AE smoke test; never edits the supplied project or workspace state."""
import hashlib
import json
import subprocess
import time
from pathlib import Path
import server

folder = server.DATA / ('verification-' + time.strftime('%Y%m%d-%H%M%S'))
folder.mkdir()
from PIL import Image
source = folder / 'source.png'
replacement = folder / 'replacement.png'
Image.new('RGBA',(320,240),(20,80,180,255)).save(source)
Image.new('RGBA',(320,240),(220,100,30,255)).save(replacement)
baseline = folder / 'baseline.aep'
marker = folder / 'fixture.json'
script = folder / 'fixture.jsx'
script.write_text('''(function(){
if(app.project && app.project.dirty) {alert('请先保存当前工程');return;}
app.beginSuppressDialogs();
try {
app.newProject();
var image=app.project.importFile(new ImportOptions(new File(SOURCE)));
var comp=app.project.items.addComp('SmokeTest',320,240,1,1,12);
var layer=comp.layers.add(image);
layer.transform.scale.setValue([25,25]);
app.project.save(new File(BASELINE));
var f=new File(MARKER); f.encoding='UTF-8'; f.open('w'); f.write('{"itemId":'+image.id+'}'); f.close();
app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
} finally {app.endSuppressDialogs(false);}
})();'''.replace('SOURCE',json.dumps(str(source))).replace('BASELINE',json.dumps(str(baseline))).replace('MARKER',json.dumps(str(marker))),encoding='utf-8')
with (folder/'fixture.log').open('w',encoding='utf-8') as log:
    proc=subprocess.Popen([str(server.AE.with_suffix('.com')),'-r',str(script)],stdout=log,stderr=subprocess.STDOUT,creationflags=0x08000000)
    deadline=time.monotonic()+120
    while not marker.exists() and time.monotonic()<deadline:
        time.sleep(.5)
    if not marker.exists():
        raise RuntimeError('Fixture creation failed; inspect '+str(folder))
target=server.read_json(marker)['itemId']
original_hash=hashlib.sha256(baseline.read_bytes()).hexdigest()
output=folder/'replaced.aep'
print('Fixture created',flush=True)
server.run_bridge(dict(action='replace',project=str(baseline),replacements=[dict(itemId=target,path=str(replacement),sequence=False)],output=str(output)))
print('Replacement saved',flush=True)
assert hashlib.sha256(baseline.read_bytes()).hexdigest()==original_hash
intermediate = server.render_intermediate(output,'SmokeTest',folder,180)
server.run_process(['ffmpeg','-nostdin','-n','-i',str(intermediate),'-c:v','libx264','-pix_fmt','yuv420p',str(folder/'video.mp4')],folder/'encode.log',60)
probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=width,height','-of','json',str(folder/'video.mp4')],capture_output=True,text=True,check=True)
report=dict(ok=True,originalUnchanged=True,output=str(output),video=str(folder/'video.mp4'),probe=json.loads(probe.stdout))
server.write_json(folder/'result.json',report)
print(json.dumps(report,ensure_ascii=True),flush=True)
