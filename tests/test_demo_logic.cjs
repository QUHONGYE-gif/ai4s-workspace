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

console.log(count + ' simulation checks passed.');

`,
  context,
);
