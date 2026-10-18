const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../web/demo/assets/api.js'),'utf8');
function setup(fetch, storage=null){
 const labels=[];let scheduled;
 const context=vm.createContext({URL,crypto:require('node:crypto').webcrypto,Uint8Array,localStorage:storage||{getItem(){return 'a'.repeat(32)},setItem(){},removeItem(){}},document:{baseURI:'https://example.test/@qhy/dev.dev/apps/preview/'},window:{dispatchEvent(e){labels.push(e.detail)}},CustomEvent:class{constructor(name,options){this.detail=options.detail}},fetch,setTimeout(fn){scheduled=fn;return 1},clearTimeout(){}});
 vm.runInContext(code,context);
 return {api:vm.runInContext('DemoAPI',context),labels,runTimer(){scheduled()}};
}
(async()=>{
 const requests=[];let firstResolve;
 const harness=setup(async(url,options)=>{
  requests.push({url:String(url),options});
  if(!options.method)return {ok:true,json:async()=>({revision:0,state:null})};
  const count=requests.filter(r=>r.options.method==='PUT').length;
  if(count===1)return new Promise(resolve=>{firstResolve=()=>resolve({ok:true,json:async()=>({revision:1})})});
  return {ok:true,json:async()=>({revision:2})};
 });
 await harness.api.loadState();harness.api.scheduleSave({value:1});harness.runTimer();
 harness.api.scheduleSave({value:2});firstResolve();
 await new Promise(setImmediate);await new Promise(setImmediate);
 const puts=requests.filter(r=>r.options.method==='PUT');
 assert.equal(puts.length,2);assert.deepEqual(puts.map(r=>JSON.parse(r.options.body).revision),[0,1]);
 assert.equal(JSON.parse(puts[1].options.body).state.value,2);
 assert.ok(puts[0].url.startsWith('https://example.test/@qhy/dev.dev/apps/preview/api/'));
 assert.equal(harness.api.statusLabel(),'后端已保存');
 console.log('PASS prefix-relative API URLs and serialized newest-state saves');
 let count=0;
 const conflict=setup(async()=>{count++;return {ok:false,status:409,json:async()=>({error:'conflict'})}});
 conflict.api.scheduleSave({value:1});conflict.runTimer();await new Promise(setImmediate);
 conflict.api.scheduleSave({value:2});await conflict.api.flush();
 assert.equal(count,1);assert.match(conflict.api.statusLabel(),/未同步/);
 assert.ok(conflict.labels.some(e=>e.error.includes('另一页面')));
 console.log('PASS revision conflict blocks silent overwrite and reports recovery');
 const values=new Map([['yanxu-demo-browser-session-v1','a'.repeat(32)],['yanxu-product-loop-v1','local-backup'],['yanxu-demo-pending-'+ 'a'.repeat(32),JSON.stringify({revision:3})]]);
 const storage={getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
 let savedRevision;
 const recovery=setup(async(url,options)=>options.method?{ok:true,json:async()=>{savedRevision=JSON.parse(options.body).revision;return {revision:5}}}:{ok:true,json:async()=>({revision:4,state:{version:1}})},storage);
 const loaded=await recovery.api.loadState();assert.equal(loaded.preferLocal,true);assert.equal(loaded.conflict,true);
 recovery.api.scheduleSave({value:'unsynced'});assert.equal(savedRevision,undefined);
 await recovery.api.prepareImport();recovery.api.scheduleSave({value:'explicit recovery'});recovery.runTimer();await new Promise(setImmediate);
 assert.equal(savedRevision,4);assert.equal(values.has('yanxu-demo-pending-'+ 'a'.repeat(32)),false);
 console.log('PASS unsynced local backup survives conflict until explicit recovery');

})().catch(error=>{console.error(error);process.exitCode=1});
