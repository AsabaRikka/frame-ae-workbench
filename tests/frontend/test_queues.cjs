const test=require('node:test');
const assert=require('node:assert/strict');
const {pageSlice,batchStatus}=require('../../frontend/js/queues.js');
test('pagination keeps every record accessible and clamps after filtering',()=>{
 const records=Array.from({length:53},(_,i)=>i);
 const all=Array.from({length:11},(_,i)=>pageSlice(records,i+1,5).items).flat();
 assert.deepEqual(all,records);
 assert.equal(pageSlice([1],11,5).page,1);
 assert.deepEqual(pageSlice([],10,5),{items:[],page:1,pages:1,total:0});
});
test('batch status preserves unfinished and failed tasks',()=>{
 const batch=(...statuses)=>({rows:statuses.map(status=>({status}))});
 assert.equal(batchStatus(batch('done','failed')),'failed');
 assert.equal(batchStatus(batch('failed','running')),'running');
 assert.equal(batchStatus(batch('done','interrupted')),'interrupted');
 assert.equal(batchStatus(batch('done','done')),'done');
});
