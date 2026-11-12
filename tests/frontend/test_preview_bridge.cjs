const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../resources/ae/bridge.jsx'), 'utf8').split('(function() {')[0];

function fixture(failFirst = false, canCreate = true) {
  const files = new Map();
  let removed = 0, calls = 0;
  class File {
    constructor(name) {this.fsName = name;}
    get exists() {return files.has(this.fsName);}
    get length() {return files.get(this.fsName) || 0;}
    remove() {files.delete(this.fsName); return true;}
  }
  class CompItem {
    constructor(id) {Object.assign(this, {id, duration: 1, frameRate: 12, workAreaStart: 0, workAreaDuration: 1});}
    duplicate() {return new CompItem(this.id);}
    saveFrameToPng(time, file) {
      calls++;
      if (failFirst && this.id === 1) throw new Error('render unavailable');
      files.set(file.fsName, 100);
    }
    remove() {removed++;}
  }
  const originals = [new CompItem(1), new CompItem(2)];
  const project = {numItems: originals.length, item: i => originals[i - 1]};
  Object.defineProperty(project, 'renderQueue', {get() {throw new Error('Preview must not read output templates or render queue');}});
  const context = vm.createContext({File, CompItem, Folder: class {constructor(name) {this.fsName = name; this.exists = canCreate;} create() {return canCreate;}},
    JOB: {previewDir: '/previews'}, app: {project}, $: {sleep() {}}});
  vm.runInContext(source, context);
  const scan = {items: [], comps: originals.map(o => ({id: o.id, name: 'Comp ' + o.id, width: 64, height: 48, layers: []}))};
  return {run() {context.createPreviews(scan); return scan;}, stats() {return {removed, calls};}};
}

test('previews work without any render queue or TIFF template access', () => {
  const f = fixture(), scan = f.run();
  assert.ok(scan.comps.every(e => e.previewPath && e.previewEncoding === 'png-direct-v2'));
  assert.deepEqual(f.stats(), {removed: 2, calls: 2});
});
test('one preview failure preserves inventory and renders the next item', () => {
  const f = fixture(true), scan = f.run();
  assert.equal(scan.comps.length, 2);
  assert.match(scan.comps[0].previewError, /render unavailable/);
  assert.ok(scan.comps[1].previewPath);
  assert.deepEqual(f.stats(), {removed: 2, calls: 2});
});
test('unwritable preview directory does not abort inventory', () => {
  const f = fixture(false, false), scan = f.run();
  assert.equal(scan.comps.length, 2);
  assert.ok(scan.previewWarning);
  assert.ok(scan.comps.every(e => e.previewError));
  assert.equal(f.stats().calls, 0);
});
