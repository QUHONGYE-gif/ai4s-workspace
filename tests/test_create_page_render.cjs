// Renders the create page and the experiment page against the shipped fixtures
// and asserts their structure: one flow graph, clickable steps, and each step's
// own registered model fields. The catalog below mirrors src/ai4s_demo/catalog.py,
// which the running server injects as fixtures.modelCatalog at bootstrap.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const fixture = JSON.parse(fs.readFileSync(path.join(root, 'configs/workbench-demo.json'), 'utf8'));
fixture.modelCatalog = {
  rfdiffusion: { name: 'RFdiffusion', role: '骨架生成', fields: [], inputs: {}, outputs: {}, sample_params: {} },
  proteinmpnn: {
    name: 'ProteinMPNN', role: '序列设计', inputs: { backbone: 'PDB' }, outputs: { sequences: 'FASTA' },
    fields: [
      { key: 'num_seq_per_target', label: '设计序列数', type: 'number', min: 1, max: 512, step: 1 },
      { key: 'sampling_temp', label: '采样温度', type: 'number', min: 0, max: 2, step: 'any' },
      { key: 'seed', label: '随机种子', type: 'number', min: 0, max: 2147483647, step: 1 },
    ],
    sample_params: { num_seq_per_target: 8, sampling_temp: 0.1, seed: 42 },
  },
  boltz: {
    name: 'Boltz', role: '结构预测', inputs: { sequence: 'FASTA' }, outputs: { structure: 'CIF' },
    fields: [
      { key: 'recycling_steps', label: '循环次数', type: 'number', min: 0, max: 20, step: 1 },
      { key: 'sampling_steps', label: '采样步数', type: 'number', min: 1, max: 1000, step: 1 },
      { key: 'diffusion_samples', label: '预测样本数', type: 'number', min: 1, max: 32, step: 1 },
      { key: 'msa_mode', label: 'MSA 来源', type: 'select', options: [['empty', '空 MSA'], ['precomputed', '提供已有 A3M']] },
    ],
    sample_params: { recycling_steps: 3, sampling_steps: 200, diffusion_samples: 1, msa_mode: 'empty' },
  },
};
let source = fs.readFileSync(path.join(root, 'web/demo/assets/app.js'), 'utf8');
const initialization = [...source.matchAll(/\n\s*workflowDraft\s*=\s*emptyWorkflowDraft\(\);/g)].at(-1);
if (!initialization) throw new Error('Workbench initialization was not found');
source = source.slice(source.indexOf("'use strict';"), initialization.index);
source = source
  .replace('await DemoAPI.bootstrap()', JSON.stringify(fixture))
  .replace('await DemoAPI.loadState()', '({state:null})');
const out = {};
const context = vm.createContext({
  URLSearchParams, console, assert, setTimeout, clearTimeout,
  localStorage: { setItem() {} },
  DemoAPI: { scheduleSave() {} },
  report: (name, html) => { out[name] = html; },
});
vm.runInContext(
  source +
    `
workflowDraft = emptyWorkflowDraft();
seedProduct();
selectWorkflowContext('protein');
const draft = currentDraft() || createExperimentDraft('protein');
report('create', workflowPage());
selectedStep = 'structure';
report('create-selected', workflowPage());
report('experiment', experimentPage(product.experiments[0]));
`,
  context,
);

const checks = [];
const has = (name, needle, want = true) => {
  const got = out[name].includes(needle);
  assert.equal(got, want, `${name} should ${want ? '' : 'not '}contain ${needle}`);
  checks.push(`${name}: ${want ? 'has' : 'no'} ${needle}`);
};
// The experience-scenario bar is gone, and the page is no longer the old long workspace.
has('create', '体验场景', false);
has('create', 'scenario-bar', false);
has('create', 'workspace-grid', false);
has('create', 'class="flow-graph"');
has('create', 'flow-pipeline');
has('create', 'data-action="select-step"');
has('create', '创建实验并开始模拟');
has('create', '更多参数 · 模型版本');
has('create', '点击流程图中的步骤');
// Selecting a step reveals that step's registered model fields, inputs and reason.
has('create-selected', 'recycling_steps');
has('create-selected', 'sampling_steps');
has('create-selected', 'diffusion_samples');
has('create-selected', 'msa_mode', false);
has('create-selected', '本步骤参数（来自工作流登记的模型字段）');
has('create-selected', '复用原因');
// The experiment page draws the same graph with per-step run state.
has('experiment', 'class="flow-graph"');
has('experiment', '本次运行流程');
has('experiment', 'state-dot');
console.log(checks.join('\n'));
console.log(`${checks.length} render checks passed.`);
