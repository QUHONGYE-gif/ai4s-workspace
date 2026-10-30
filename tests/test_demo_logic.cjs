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
check('selected node fields come from the workflow step definition', () => {
  createExperimentDraft('protein');
  selectedPlanStep = 'structure';
  const html = workflowPage();
  assert.match(html, /data-draft="config\.predictor"/);
  assert.match(html, /data-draft="config\.seed"/);
  assert.doesNotMatch(html, /体验场景/);
});
check('creation saves a ready experiment before simulation starts', () => {
  createExperimentDraft('protein');
  createExperiment();
  const experiment = product.experiments.at(-1);
  assert.equal(experiment.status, 'ready');
  assert.equal(experiment.outputs.length, 0);
  assert.equal(experiment.plan.length, 5);
  assert.equal(product.drafts.protein, undefined);
  page = {name: 'experiment', id: experiment.id, query: new URLSearchParams()};
  const html = experimentPage(experiment);
  assert.match(html, /查看运行与结果/);
  assert.doesNotMatch(html, /data-action="start"/);
  assert.equal((html.match(/class="live-flow /g) || []).length, 1);
  assert.doesNotMatch(html, /node-detail-body/);
  selectedPlanStep = experiment.workflowSnapshot.steps[0].id;
  assert.match(experimentPage(experiment), /查看候选结果/);
});
check('node details stay hidden until a node is selected and can be closed', () => {
  createExperimentDraft('protein');
  selectedPlanStep = '';
  assert.doesNotMatch(workflowPage(), /node-detail-body/);
  selectedPlanStep = 'structure';
  assert.match(workflowPage(), /node-detail-body/);
  assert.match(workflowPage(), /data-close-node-detail/);
  selectedPlanStep = '';
  assert.doesNotMatch(workflowPage(), /node-detail-body/);
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
check('completed result flow preserves artifact and structure tool actions', () => {
  const e = product.experiments.find((run) => run.outputs.some((out) => artifactById(out.artifactId)?.kind === 'mmCIF'));
  const html = liveFlow(e.workflowSnapshot.steps, '', e);
  const structure = e.outputs.find((out) => artifactById(out.artifactId)?.kind === 'mmCIF');
  assert.match(html, new RegExp('data-artifact-detail="' + structure.artifactId + '"'));
  assert.match(html, new RegExp('data-view-artifact="' + structure.artifactId + '"'));
  assert.match(html, /连线动效为数据流向回放/);
  assert.doesNotMatch(html, /aria-current="step"/);
});
check('creation preserves candidate controls, result identity, plan export and failure simulation', () => {
  const d = createExperimentDraft('protein');
  selectedPlanStep = 'prepare';
  const html = workflowPage();
  assert.match(html, /data-choice="prepare"/);
  assert.match(html, /查看候选结果/);
  assert.match(html, new RegExp(identities(d.config).prepare));
  assert.match(html, /data-action="export-plan"/);
  assert.match(html, /data-draft="simulation"/);
  assert.match(html, /value="fail"/);
  assert.match(html, /预计总用时/);
});
check('registered custom workflows retain editable random seed and registered command', () => {
  const data = demoWorkflowDraft('custom');
  data.name = 'Custom audit workflow';
  const created = createWorkflow(data);
  assert.equal(created.ok, true);
  createExperimentDraft(created.id);
  selectedPlanStep = 'step-1';
  const html = workflowPage();
  assert.match(html, /data-draft="config.seed"/);
  assert.match(html, /已登记的调用与版本/);
  assert.ok(html.includes(esc(data.registrations[0].command)));
});
check('result details preserve owners and unreadable artifact history', () => {
  const e = product.experiments.find((run) => run.outputs.length);
  const a = artifactById(e.outputs[0].artifactId);
  const retained = a.retained;
  a.retained = false;
  const html = experimentOutputDetails(e);
  assert.ok(html.includes(esc(a.ownerName)));
  assert.ok(html.includes(esc(a.id)));
  assert.match(html, /仅保留来源记录／文件不可读取/);
  assert.match(html, new RegExp('data-artifact-detail="' + a.id + '"'));
  a.retained = retained;
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
