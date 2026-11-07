// Regression checks for registration handoff, rescreening and async assistant context.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const fixture = JSON.parse(fs.readFileSync(path.join(root, 'configs/workbench-demo.json')));
let source = fs.readFileSync(path.join(root, 'web/demo/assets/app.js'), 'utf8');
const initialization = [...source.matchAll(/\n\s*workflowDraft\s*=\s*emptyWorkflowDraft\(\);/g)].at(-1);
source = source.slice(source.indexOf("'use strict';"), initialization.index)
  .replace('await DemoAPI.bootstrap()', JSON.stringify(fixture))
  .replace('await DemoAPI.loadState()', '({state:null})')
  .replace('const render = function ()', 'let render = function ()');
let resolveReply;
const element = {value: '用当前产物重新筛选', focus(){}, querySelectorAll(){return []}};
const context = vm.createContext({element, URLSearchParams, location:{hash:''}, console, assert, setTimeout, clearTimeout,
  document:{activeElement:null, body:{style:{}}, querySelector(){return element}},
  localStorage:{setItem(){}}, DemoAPI:{scheduleSave(){}, experimentAgent(){return new Promise(r => {resolveReply=r})}},
  reply(value){resolveReply(value)}});
const result = vm.runInContext(source + `
(async () => {
  workflowDraft = emptyWorkflowDraft(); seedProduct(); render = () => {};
  const makeWorkflow = (id, digest) => ({id, custom:true, template:'custom', name:'Registered',
    registrationSource:{registrationId:id}, defaults:{input:'registered-input', seed:42, count:8, keep:5},
    executionDefinition:{inputPath:'registered-input',environment:'simulation', steps:[{id:'design',version:'v1',command:'simulation-only'}]},
    steps:[{id:'design',name:'Design',model:'proteinmpnn',kind:'FASTA',file:'sequences.fasta',deps:[],cost:120,load:3,size:.01,
      codeIdentity:'v1',inputIdentity:{backbone:{kind:'file',sha256:digest,format:'PDB'}},chainPolicy:{mode:'all',chains:[]},
      inputRequirements:{backbone:'PDB'},parameters:[{key:'count',modelKey:'num_seq_per_target',type:'number',min:1,max:512,step:1,default:8}]},
      {id:'filter',name:'Filter',model:'sequence_filter',kind:'FASTA',file:'selected.fasta',deps:['design'],cost:1,load:1,size:.001,
        parameters:[{key:'keep',modelKey:'filter_count',type:'number',min:1,max:512,step:1,default:5,category:'filter'}]}]});
  workflowInfo.regA = makeWorkflow('regA','aaaa');
  workflowInfo.regB = makeWorkflow('regB','bbbb');
  workflowInfo.regSame = makeWorkflow('regSame','aaaa');
  const d = createExperimentDraft('regA');
  const first = identities(d.config).design;
  selectWorkflowContext('regB');
  assert.notEqual(identities(workflowInfo.regB.defaults).design, first);
  selectWorkflowContext('regSame');
  assert.equal(identities(workflowInfo.regSame.defaults).design, first);
  workflowInfo.regSame.steps[0].chainPolicy = {mode:'selected',chains:['A']};
  assert.notEqual(identities(workflowInfo.regSame.defaults).design, first);
  workflowInfo.regSame.steps[0].chainPolicy = {mode:'all',chains:[]};
  workflowInfo.regSame.steps[0].inputIdentity.backbone.record_id='record-2';
  assert.notEqual(identities(workflowInfo.regSame.defaults).design, first);
  selectWorkflowContext('regA');
  assert.doesNotMatch(workflowPage(), /API 设置|创建前摘要|creation-overview/);
  createExperiment();
  const e = product.experiments.at(-1);
  assert.equal(e.creationConfirmed,false);
  startExperiment(e.id); assert.equal(e.status,'ready');
  // An external structure input must not supersede the designed sequences at filtering.
  const pdb = {...copy(product.catalog[0]),id:'INPUT-PDB',kind:'PDB',status:'complete',accessible:true,retained:true,scope:'team'};
  product.catalog.push(pdb); e.inputArtifactId=pdb.id; e.status='running';
  assert.equal(completeSimulationStep(e,0),true);
  const generated=artifactById(e.outputs[0].artifactId);
  assert.equal(generated.records.length,8);
  assert.equal(completeSimulationStep(e,1),true);
  const filtered=artifactById(e.outputs[1].artifactId);
  assert.equal(filtered.records.length,5);
  assert.deepEqual(filtered.parentArtifactIds,[generated.id]);
  assert.equal(filtered.inputArtifactId,generated.id);
  e.status='completed'; e.creationConfirmed=true;
  const next=applyAgentOperations(e,[{type:'create_experiment_draft',node_id:'filter',input_artifact_id:generated.id}]);
  assert.deepEqual(next.requestedStepIds,['filter']);
  assert.throws(()=>applyAgentOperations(e,[{type:'create_experiment_draft',node_id:'filter',input_artifact_id:generated.id}]),/已有未完成草稿/);
  assert.equal(currentDraft(),next);
  assert.equal(packPlan(next).length,1);
  assert.equal(packPlan(next)[0].deps.length,0);
  createExperiment();
  const screening=product.experiments.at(-1); screening.status='running';
  assert.equal(completeSimulationStep(screening,0),true);
  assert.equal(artifactById(screening.outputs[0].artifactId).records.length,5);
  assert.equal(artifactById(screening.outputs[0].artifactId).inputArtifactId,generated.id);
  // Expanded snapshots survive save/load; the legacy manual limit stays 12.
  workflowInfo.large={...makeWorkflow('large','aa'),steps:Array.from({length:13},(_,i)=>({...copy(workflowInfo.regA.steps[0]),id:'node-'+i}))};
  validateSaved(persistable());
  workflowInfo.large.steps=Array.from({length:65},(_,i)=>({...copy(workflowInfo.regA.steps[0]),id:'node-'+i}));
  assert.throws(()=>validateSaved(persistable()),/流程定义/); delete workflowInfo.large;
  // Context changes while a model response is pending must never create a stale draft.
  for (const mutation of ['artifact','selection','requested','config','choices']) {
    selectWorkflowContext('regA');
    const previousDraft=currentDraft();
    page={name:'experiment',id:e.id,query:new URLSearchParams()}; location.hash='#/experiment/'+e.id;
    selectedPlanStep='filter'; e.agentArtifactId=generated.id;
    element.value='用当前产物重新筛选';
    const pending=sendAgentMessage(e,steps.find(s=>s.id==='filter'));
    if(mutation==='artifact') e.agentArtifactId=filtered.id;
    if(mutation==='selection') selectedPlanStep='design';
    if(mutation==='requested') e.requestedStepIds=['filter'];
    if(mutation==='config') e.config.keep=3;
    if(mutation==='choices') e.choices.filter='compute';
    reply({reply:'筛选草稿',operations:[{type:'create_experiment_draft',node_id:'filter',input_artifact_id:generated.id}]});
    await pending;
    assert.equal(currentDraft(),previousDraft,mutation);
    assert.match(e.agentMessages.at(-1).text,/请求期间变化/);
    e.requestedStepIds=null; e.config.keep=5; e.choices={};
  }
  console.log('PASS input content/chain/record identities, upstream filtering, screening-only lineage, persistence and stale replies');
})()
`,context);
Promise.resolve(result).catch(error=>{console.error(error);process.exitCode=1});
