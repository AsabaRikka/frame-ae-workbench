function encode(v) {
    if (v === null || v === undefined) return 'null';
    if (typeof v === 'string') return '"' + v.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\r/g, '\\r').replace(/\n/g, '\\n').replace(/\t/g, '\\t').replace(/[\x00-\x1f]/g, function(c) { return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4); }) + '"';
    if (typeof v === 'number') return isFinite(v) ? String(v) : 'null';
    if (typeof v === 'boolean') return String(v);
    var a = [], k;
    if (v instanceof Array) { for (k = 0; k < v.length; k++) a.push(encode(v[k])); return '[' + a.join(',') + ']'; }
    for (k in v) if (v.hasOwnProperty(k)) a.push(encode(k) + ':' + encode(v[k]));
    return '{' + a.join(',') + '}';
}
function writeResult(value) {
    var f = new File(JOB.result); f.encoding = 'UTF-8';
    if (!f.open('w')) throw new Error('无法写入结果文件；请在 AE 的脚本与表达式设置中允许脚本写入文件。');
    f.write(encode(value)); f.close();
}
function itemById(id) { for (var i = 1; i <= app.project.numItems; i++) if (app.project.item(i).id == id) return app.project.item(i); return null; }
function inspect() {
    var items = [], comps = [], missing = [], i, j, item, uses, source, file, references = {}, procedural = [];
    for (i = 1; i <= app.project.numItems; i++) {
        item = app.project.item(i);
        if (item instanceof CompItem) {
            uses = []; var parents = item.usedIn;
            for (j = 0; j < parents.length; j++) uses.push(parents[j].name);
            var layers = [];
            for (j = 1; j <= item.numLayers; j++) {
                var layer = item.layer(j), linked = null;
                try { linked = layer.source; } catch (ignored) {}
                var info = {compId:item.id, compName:item.name, layerIndex:j, layerName:layer.name, enabled:layer.enabled, inPoint:layer.inPoint, outPoint:layer.outPoint, sourceId:linked ? linked.id : null, adjustment:!!layer.adjustmentLayer, guide:!!layer.guideLayer};
                if (linked && !layer.nullLayer) {
                    if (!references[linked.id]) references[linked.id] = [];
                    references[linked.id].push(info);
                }
                var kind = 'controller';
                if (layer.nullLayer) kind = 'null';
                else if (layer instanceof TextLayer) kind = 'text';
                else if (layer instanceof ShapeLayer) kind = 'shape';
                else if (linked) kind = 'source';
                info.kind = kind;
                if (kind === 'text') { try { info.text = layer.property('ADBE Text Properties').property('ADBE Text Document').value.text; } catch (ignoredText) {} }
                if (kind === 'text' || kind === 'shape') procedural.push(info);
                layers.push(info);
            }
            comps.push({id:item.id, name:item.name, width:item.width, height:item.height, duration:item.duration, fps:item.frameRate, workAreaStart:item.workAreaStart, workAreaDuration:item.workAreaDuration, uses:uses, layers:layers, sourceKind:'composition', path:'', missing:false, still:false});
        }
        if (!(item instanceof FootageItem)) continue;
        source = item.mainSource;
        file = item.file; uses = [];
        var used = item.usedIn;
        for (j = 0; j < used.length; j++) uses.push(used[j].name);
        var sourceKind = 'placeholder';
        if (file !== null && file !== undefined) sourceKind = 'file';
        else if (source.color !== undefined) sourceKind = 'solid';
        var entry = {id:item.id, name:item.name, path:file ? file.fsName : '', missing:sourceKind === 'file' ? item.footageMissing || !file || !file.exists : sourceKind === 'placeholder', width:item.width, height:item.height, duration:item.duration, fps:item.frameRate, still:source.isStill, uses:uses, sourceKind:sourceKind, hasVideo:item.hasVideo, hasAudio:item.hasAudio};
        if (sourceKind === 'solid') entry.color = source.color;
        items.push(entry);
        if (entry.missing) missing.push(entry.name);
    }
    for (i = 0; i < items.length; i++) items[i].references = references[items[i].id] || [];
    for (i = 0; i < comps.length; i++) comps[i].references = references[comps[i].id] || [];
    return {ok:true, schemaVersion:4, version:app.version, project:app.project.file.fsName, items:items, comps:comps, procedural:procedural, missing:missing};
}
function catalogPreviewProgress(done, total, name) {
    if (!JOB.progress) return;
    var progress = new File(JOB.progress); progress.encoding = 'UTF-8';
    if (progress.open('w')) { progress.write(encode({done:done,total:total,name:name})); progress.close(); }
}
function createPreviews(scan) {
    var folder = new Folder(JOB.previewDir);
    var entries = scan.items.concat(scan.comps);
    if (!folder.exists && !folder.create()) {
        scan.previewWarning = '无法创建预览目录，工程素材已正常读取。请检查目录权限。';
        for (var failed = 0; failed < entries.length; failed++) {
            if (!entries[failed].missing && entries[failed].width && entries[failed].hasVideo !== false) entries[failed].previewError = scan.previewWarning;
        }
        return;
    }
    for (var n = 0; n < entries.length; n++) {
        var entry = entries[n], original = itemById(entry.id), previewComp = null;
        if (entry.missing || !entry.width || !entry.height || entry.hasVideo === false) continue;
        catalogPreviewProgress(n, entries.length, entry.name);
        var output = new File(folder.fsName + '/' + entry.id + '.png');
        var refresh = false;
        if (JOB.refreshIds) for (var ri = 0; ri < JOB.refreshIds.length; ri++) if (JOB.refreshIds[ri] === entry.id) refresh = true;
        if (!refresh && output.exists && output.length > 0) { entry.previewPath = output.fsName; entry.previewEncoding = 'rgba-png-v2'; continue; }
        try {
            output = new File(folder.fsName + '/preview-' + entry.id + '-direct.png');
            if (output.exists && !output.remove()) throw new Error('无法更新预览缓存文件');
            var time = Math.min(Math.max(0, original.duration-1/30), 0.3);
            previewComp = original;
            if (original instanceof CompItem) {
                var start = original.workAreaStart, end = Math.min(original.duration, start+original.workAreaDuration), first = end, firstEnd = end;
                for (var j = 0; j < entry.layers.length; j++) {
                    var l = entry.layers[j];
                    if (l.enabled && l.kind !== 'null' && l.kind !== 'controller' && !l.adjustment && l.outPoint > start) {
                        var visibleStart = Math.max(start,l.inPoint);
                        if (visibleStart < first) { first = visibleStart; firstEnd = Math.min(end,l.outPoint); }
                        else if (visibleStart === first) firstEnd = Math.min(firstEnd,l.outPoint);
                    }
                }
                time = Math.max(0, Math.min(end-1/original.frameRate, first+Math.min(0.3,(firstEnd-first)/2)));
                // Render a copy at reduced resolution; the input is never saved.
                previewComp = original.duplicate();
                var factor = Math.max(1, Math.min(16, Math.ceil(Math.max(entry.width/640,entry.height/480))));
                previewComp.resolutionFactor = [factor,factor];
            } else {
                var ratio = Math.min(640/entry.width, 480/entry.height, 1);
                previewComp = app.project.items.addComp('__workbench_preview__', Math.max(4,Math.round(entry.width*ratio)), Math.max(4,Math.round(entry.height*ratio)), 1, Math.max(1,time+1), 30);
                var visual = previewComp.layers.add(original);
                visual.property('ADBE Transform Group').property('ADBE Scale').setValue([ratio*100,ratio*100]);
            }
            time = Math.floor(time*previewComp.frameRate)/previewComp.frameRate;
            entry.previewTime = time;
            previewComp.saveFrameToPng(time, output);
            for (var wait = 0; wait < 40; wait++) {
                output = new File(output.fsName);
                if (output.exists && output.length > 0) break;
                $.sleep(50);
            }
            if (!output.exists || output.length === 0) throw new Error('AE 未生成预览图片');
            entry.previewPath = output.fsName;
            entry.previewEncoding = 'png-direct-v2';
        } catch (error) {
            entry.previewError = '预览生成失败：' + error.toString();
        } finally {
            if (previewComp && previewComp !== original) {
                try { previewComp.remove(); } catch (ignoredCleanup) {}
            }
        }
    }
    catalogPreviewProgress(entries.length, entries.length, '预览处理完成');
}
function createMotionPreview() {
    var original = itemById(JOB.itemId);
    if (!(original instanceof CompItem)) throw new Error('动画预览目标合成不存在，请重新扫描');
    var folder = new Folder(JOB.previewDir);
    if (!folder.exists && !folder.create()) throw new Error('无法创建动画预览目录');
    var comp = original.duplicate();
    try {
        var factor = Math.max(1, Math.min(16, Math.ceil(Math.max(comp.width/640, comp.height/480))));
        comp.resolutionFactor = [factor,factor];
        var fps = 12, start = comp.workAreaStart, duration = Math.min(5,comp.workAreaDuration,comp.duration-start);
        var frames = Math.max(1,Math.floor(duration*fps));
        for (var i=0;i<frames;i++) {
            var output = new File(folder.fsName+'/'+('00000'+i).slice(-5)+'.png');
            comp.saveFrameToPng(start+i/fps,output);
            for (var w=0;w<40;w++) { output=new File(output.fsName); if(output.exists && output.length>0) break; $.sleep(50); }
            if (!output.exists || output.length===0) throw new Error('合成动画预览缺帧：'+i);
        }
        return {ok:true,frames:frames,fps:fps};
    } finally { comp.remove(); }
}
(function() {
    var suppressed = false, openedProject = false;
    try {
        if (JOB.expires && new Date().getTime() > JOB.expires) throw new Error('任务已过期，请重新发起');
        if (app.project && app.project.dirty) throw new Error('AE 中有未保存的工程。请先保存，再重试。');
        if (app.project && app.project.renderQueue.rendering) throw new Error('AE 正在渲染，请完成后重试。');
        app.beginSuppressDialogs(); suppressed = true;
        var input = new File(JOB.project);
        if (!input.exists) throw new Error('工程文件不存在');
        app.open(input);
        openedProject = true;
        if (JOB.action === 'motion') { writeResult(createMotionPreview()); return; }
        if (JOB.action === 'scan') { var scanned = inspect(); if (JOB.previewDir) createPreviews(scanned); writeResult(scanned); return; }
        for (var r = 0; r < JOB.replacements.length; r++) {
            var replacement = JOB.replacements[r], target = itemById(replacement.itemId), next = new File(replacement.path);
            if (!(target instanceof FootageItem) && !(target instanceof CompItem)) throw new Error('替换目标已改变，请重新扫描工程：' + replacement.itemId);
            if (!next.exists) throw new Error('替换素材不存在：' + replacement.path);
            if (replacement.expectedSize && (target.width !== replacement.expectedSize[0] || target.height !== replacement.expectedSize[1])) throw new Error('原素材尺寸已变化，请重新扫描工程：' + target.name);
            var originalFrameRate = target.frameRate;
            if (target instanceof CompItem) {
                var importOptions = new ImportOptions(next); importOptions.sequence = !!replacement.sequence;
                var imported = app.project.importFile(importOptions); imported.name = target.name + ' · 新素材';
                if (replacement.expectedSize && (imported.width !== replacement.expectedSize[0] || imported.height !== replacement.expectedSize[1])) throw new Error('合成替换尺寸校验失败');
                if (replacement.sequence && originalFrameRate > 0) imported.mainSource.conformFrameRate = originalFrameRate;
                var count = 0;
                for (var ci = 1; ci <= app.project.numItems; ci++) {
                    var owner = app.project.item(ci); if (!(owner instanceof CompItem)) continue;
                    for (var li = 1; li <= owner.numLayers; li++) {
                        var referring = owner.layer(li);
                        if (referring instanceof AVLayer && referring.source === target) {
                            var locked = referring.locked; referring.locked = false;
                            try { referring.replaceSource(imported, false); count++; } finally { referring.locked = locked; }
                        }
                    }
                }
                if (!count) throw new Error('该合成没有可替换的图层引用：' + target.name);
                continue;
            }
            if (replacement.sequence) target.replaceWithSequence(next, false); else target.replace(next);
            if (replacement.expectedSize && (target.width !== replacement.expectedSize[0] || target.height !== replacement.expectedSize[1])) throw new Error('素材尺寸适配校验失败：' + target.name);
            if (replacement.sequence && originalFrameRate > 0) target.mainSource.conformFrameRate = originalFrameRate;
        }
        var state = inspect();
        if (state.missing.length && !JOB.allowMissing) throw new Error('工程仍缺少 ' + state.missing.length + ' 项素材：' + state.missing.slice(0, 5).join('、'));
        var output = new File(JOB.output);
        if (output.exists) throw new Error('输出工程已存在，拒绝覆盖');
        app.project.save(output);
        writeResult({ok:true, output:output.fsName, missing:state.missing});
    } catch (e) {
        try { writeResult({ok:false, error:e.toString()}); } catch (writeError) { alert(writeError.toString()); }
    } finally {
        if (openedProject && app.project) app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
        if (suppressed) app.endSuppressDialogs(false);
        // A generated copy is already saved. Never save the input project here.
    }
})();
