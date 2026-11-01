// Exercise the shipped simulation code without a browser, DOM mutation or network.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const fixture = JSON.parse(fs.readFileSync(path.join(root, 'configs/workbench-demo.json'), 'utf8'));
let source = fs.readFileSync(path.join(root, 'web/demo/assets/app.js'), 'utf8');
// Load only the model and view definitions; browser event wiring starts after them.
const initialization = [...source.matchAll(/\n\s*workflowDraft\s*=\s*emptyWorkflowDraft\(\);/g)].at(-1);
if (!initialization) throw new Error('Workbench initialization was not found');
source = source.slice(source.indexOf("'use strict';"), initialization.index);

source = source
  .replace('await DemoAPI.bootstrap()', JSON.stringify(fixture))
  .replace('await DemoAPI.loadState()', '({state:null})');
const context = vm.createContext({
  URLSearchParams,
  location: {hash: ''},
  console,
  assert,
  setTimeout,
  clearTimeout,
  localStorage: { setItem() {} },
  DemoAPI: { scheduleSave() {} },
});
vm.runInContext(
  source +
    `
workflowDraft = emptyWorkflowDraft();
seedProduct();
let count = 0;
function check(name, fn) {
  fn();
  console.log('PASS ' + name);
  count++;
}
check('personal and team candidates are distinct', () => {
  createExperimentDraft('protein');
  assert.equal(plan().filter((s) => s.reuse).length, 5);
  currentDraft().reuseScope = 'mine';
  assert.equal(plan().filter((s) => s.reuse).length, 2);
});
check('missing files do not count as valid candidates', () => {
  const d = createExperimentDraft('protein');
  d.config.predictor = 'fold-v2';
  assert.equal(plan().find((s) => s.id === 'structure').action, 'compute');
});
check('new sampling only invalidates generation and downstream', () => {
  const d = createExperimentDraft('protein');
  d.intent = 'fresh';
  d.config.sampleToken = d.id;
  assert.deepEqual(
    Array.from(
      plan().filter((s) => s.reuse),
      (s) => s.id,
    ),
    ['prepare', 'embedding', 'msa'],
  );
});
check('registered input drives run configuration', () => {
  const data = demoWorkflowDraft('protein');
  data.name = 'Test registered input';
  data.inputPath = 'data/actual.fasta';
  const result = createWorkflow(data);
  assert.equal(result.ok, true);
  assert.equal(createExperimentDraft(result.id).config.input, 'data/actual.fasta');
});
check('workflow identity is separate from output identity', () => {
  selectWorkflowContext('protein');
  const first = identities(proteinBase);
  workflowInfo['protein-copy'] = { ...copy(workflowInfo.protein) };
  selectWorkflowContext('protein-copy');
  assert.equal(identities(proteinBase).structure, first.structure);
});
check('structure cannot be supplied to sequence-only input', () => {
  createExperimentDraft('protein');
  const a = product.catalog.find((a) => a.kind === 'mmCIF' && a.status === 'complete');
  assert.equal(accepts(workflowInfo.protein, a), false);
});

check('creation saves a ready experiment before simulation starts', () => {
  createExperimentDraft('protein');
  createExperiment();
  const experiment = product.experiments.at(-1);
  assert.equal(experiment.status, 'ready');
  assert.equal(experiment.outputs.length, 0);
  assert.equal(experiment.plan.length, 5);
  assert.equal(product.drafts.protein, undefined);
  assert.deepEqual(experiment.choices, {});
  page = {name: 'experiment', id: experiment.id, query: new URLSearchParams()};
});

check('experiment uses one graph and switching views does not start or change the plan', () => {
  const e = product.experiments.find((run) => !run.fixture && run.status === 'ready');
  const before = JSON.stringify(e);
  page.query = new URLSearchParams();
  const config = experimentPage(e);
  assert.match(config, /data-experiment-view="config"/);
  assert.doesNotMatch(config, /execution-flow|role="progressbar"/);
  page.query.set('view', 'results');
  const results = experimentPage(e);
  assert.match(results, /data-experiment-view="results"/);
  assert.match(results, /确认候选并开始模拟/);
  assert.match(results, /role="progressbar"/);
  assert.doesNotMatch(results, /plan-flow/);
  assert.equal((results.match(/class="live-flow /g) || []).length, 1);
  assert.equal(JSON.stringify(e), before);
  page.query = new URLSearchParams();
  const running = {...copy(e),status:'running',currentStep:0};
  assert.match(experimentPage(running), /data-experiment-view="results"/);
  assert.match(experimentPage(running), /aria-current="step"/);
  const completed = {...copy(e),status:'completed'};
  assert.match(experimentPage(completed), /data-experiment-view="results"/);
  page.query.set('view', 'config');
  assert.match(experimentPage(completed), /data-experiment-view="config"/);
  assert.equal((experimentPage(completed).match(/class="live-flow /g) || []).length, 1);
  page.query = new URLSearchParams();
});

check('flow edges follow declared branches including independent molecule input', () => {
  const protein = liveFlow(proteinSteps, 'prepare');
  assert.equal((protein.match(/data-flow-from=/g) || []).length, 5);
  assert.match(protein, /data-flow-from="msa" data-flow-to="structure"/);
  const molecule = liveFlow(moleculeSteps, 'prepare');
  assert.equal((molecule.match(/data-flow-from=/g) || []).length, 4);
  assert.doesNotMatch(molecule, /data-flow-from="prepare" data-flow-to="target"/);
  const custom = [{id:'first',deps:[]},{id:'last',deps:['first']}];
  assert.ok(flowLayout(custom).positions.get('last').x > flowLayout(custom).positions.get('first').x);
});
check('execution flow only animates data entering the current running step', () => {
  const e = {status:'ready', outputs:[], currentStep:0, fixture:false};
  const ready = liveFlow(proteinSteps, '', e);
  assert.equal((ready.match(/<animateMotion/g) || []).length, 5);
  assert.match(ready, /动效为流程示意，尚未执行/);
  assert.doesNotMatch(ready, /aria-current="step"/);
  assert.equal(flowStepState(e, proteinSteps[0], 0), 'pending');
  e.status = 'running';
  e.currentStep = 1;
  e.outputs = [{stepId:'prepare',artifactId:'unknown',mode:'reuse'}];
  const running = liveFlow(proteinSteps, '', e);
  assert.match(running, /当前步骤 · 序列 Embedding/);
  assert.equal((running.match(/<animateMotion/g) || []).length, 1);
  assert.equal(flowStepState(e, proteinSteps[2], 2), 'pending');
  e.status = 'waiting';
  assert.doesNotMatch(liveFlow(proteinSteps, '', e), /animateMotion/);
  assert.equal(flowStepState(e, proteinSteps[1], 1), 'waiting');
  e.status = 'failed';
  assert.equal(flowStepState(e, proteinSteps[1], 1), 'failed');
  assert.equal(flowStepState(e, proteinSteps[2], 2), 'stopped');
  e.status = 'cancelled';
  assert.equal(flowStepState(e, proteinSteps[0], 0), 'complete');
  assert.doesNotMatch(liveFlow(proteinSteps, '', e), /animateMotion|aria-current="step"/);
});




check('node dependencies use the experiment snapshot after workflow edits', () => {
  const d = createExperimentDraft('protein');
  const snapshot = copy(workflowInfo.protein);
  snapshot.steps = copy(proteinSteps);
  snapshot.steps[0].name = 'Original snapshot input';
  const e = {...d, workflowSnapshot:snapshot, outputs:[], status:'completed'};
  const html = nodeDetailPanel(snapshot.steps[1], e, null, e);
  assert.match(html, /Original snapshot input/);
});

console.log(count + ' simulation checks passed.');

`,
  context,
);
