"""Explicit local AE integration check. Does not edit workspace selections or history."""
import hashlib
import json
import time
from pathlib import Path
from unittest.mock import patch

import server
from catalog import validate_selection
from size_fit import prepare_replacement


SNAPSHOT = r'''
function layerState(layer) {
    var data = {start:layer.startTime, inPoint:layer.inPoint, outPoint:layer.outPoint, stretch:layer.stretch, locked:layer.locked, enabled:layer.enabled, transform:[]};
    var group=layer.property('ADBE Transform Group');
    for(var p=1;p<=group.numProperties;p++) {
        var prop=group.property(p), v={name:prop.matchName, expression:prop.expression, keys:[]};
        try {v.value=prop.valueAtTime(0,false);} catch(e) {v.value='unavailable';}
        for(var k=1;k<=prop.numKeys;k++) v.keys.push([prop.keyTime(k),prop.keyValue(k)]);
        data.transform.push(v);
    }
    return encode(data);
}
var snapshots=[];
for(var cc=1;cc<=app.project.numItems;cc++) {
    var owner=app.project.item(cc);if(!(owner instanceof CompItem))continue;
    for(var ll=1;ll<=owner.numLayers;ll++) {
        var layer=owner.layer(ll);if(!(layer instanceof AVLayer)||!layer.source)continue;
        for(var rr=0;rr<JOB.replacements.length;rr++) if(layer.source.id===JOB.replacements[rr].itemId) {
            snapshots.push({comp:owner.id,layer:ll,originalSource:layer.source.id,sourceIsComp:layer.source instanceof CompItem,state:layerState(layer)});
        }
    }
}
'''

VERIFY = r'''
app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
app.open(output);
var changed=0;
for(var ss=0;ss<snapshots.length;ss++) {
    var snapshot=snapshots[ss], verified=itemById(snapshot.comp).layer(snapshot.layer);
    if(layerState(verified)!==snapshot.state) throw Error('Layer animation/timing changed: '+snapshot.comp+':'+snapshot.layer);
    if(snapshot.sourceIsComp && (!(verified.source instanceof FootageItem)||verified.source.id===snapshot.originalSource)) throw Error('Composition reference was not replaced');
    changed++;
}
var finalState=inspect();
if(finalState.missing.length)throw Error('Missing footage after reopening');
writeResult({ok:true,output:output.fsName,checkedLayers:changed,missing:finalState.missing});
'''


def main():
    root = server.ROOT
    folder = server.OUTPUT / ('catalog-validation-' + time.strftime('%Y%m%d-%H%M%S'))
    folder.mkdir()
    bridge = (root/'bridge.jsx').read_text(encoding='utf-8')
    bridge = bridge.replace('        for (var r = 0; r < JOB.replacements.length; r++) {', SNAPSHOT+'\n        for (var r = 0; r < JOB.replacements.length; r++) {')
    bridge = bridge.replace('        writeResult({ok:true, output:output.fsName, missing:state.missing});', VERIFY)
    (folder/'bridge.jsx').write_text(bridge, encoding='utf-8')
    scans = [server.read_json(p) for p in (server.DATA/'catalog').glob('*/scan.json')]
    august = next(s for s in scans if '0806-' in s['project'])
    july = next(s for s in scans if '0727-' in s['project'])
    blue_bullet = next(e for e in august['items'] if e['id']==20569)['path']
    cases = [(august, [(6202, blue_bullet), (20484, next(e for e in august['items'] if e['id']==220)['path'])]),
             (july, [(23, next(e for e in july['items'] if e['id']==82)['path']),
                     (134, next(e for e in july['items'] if e['id']==947)['path'])])]
    results=[]
    for index,(scan,mappings) in enumerate(cases):
        validate_selection(scan,[item for item,_ in mappings])
        source=Path(scan['project']);before=hashlib.sha256(source.read_bytes()).hexdigest()
        destination=folder/str(index);destination.mkdir()
        targets={e['id']:e for e in scan['items']+scan['comps']}
        replacements=[]
        for item,path in mappings:
            replacement,_=prepare_replacement(dict(itemId=item,path=path,sequence=False), targets[item], destination, server.run_process)
            replacements.append(replacement)
        with patch.object(server,'ROOT',folder),patch.object(server,'DATA',destination):
            result=server.run_bridge(dict(action='replace',project=str(source),output=str(destination/'project.aep'),
                                          replacements=replacements,allowMissing=False),timeout=300)
        assert (destination/'project.aep').stat().st_size>0
        assert hashlib.sha256(source.read_bytes()).hexdigest()==before
        result.update(input=str(source),hash=before,targets=[dict(id=i,name=targets[i]['name'])for i,_ in mappings])
        results.append(result)
        server.write_json(folder/'validation.json',results)
        print(json.dumps(result,ensure_ascii=False),flush=True)
    print(str(folder),flush=True)


if __name__=='__main__':
    main()
