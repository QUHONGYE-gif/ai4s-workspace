/* Frontend views, routing and deterministic simulation. No model commands execute here. */
(async function startWorkbench() {
  'use strict';
  const fixture = await DemoAPI.bootstrap();
  const serverSaved = await DemoAPI.loadState();
  const proteinBase = fixture.proteinBase,
    proteinSteps = fixture.proteinSteps;
  const moleculeBase = fixture.moleculeBase,
    moleculeSteps = fixture.moleculeSteps;
  const workflowInfo = fixture.workflowInfo,
    builtinPolicies = fixture.policies;
  let activeWorkflow = 'protein',
    baseConfig = proteinBase,
    steps = proteinSteps;
  const toolInfo = {
    pymol: {
      name: 'PyMOL',
      initial: 'Py',
      subtitle: '分子结构工具入口',
      description: '加载真实 PDB 或 mmCIF 文件，在页面中查看并操作 PyMOL。',
      tags: ['结构结果', '会话入口'],
      color: 'green',
    },
    chimerax: {
      name: 'ChimeraX',
      initial: 'Cx',
      subtitle: '分子可视化工具入口',
      description: '连接结构数据与可视化会话，查看文件来源并切换示例显示方式。',
      tags: ['结构查看', '数据追溯'],
      color: 'blue',
    },
  };
  const customPolicies = [];
  let workflowDraft,
    policyDraft = { name: '', reuse: 'cost', storage: 'lru', description: '' };
  let aiHost = null, aiController = null, aiMount = null;
  let workflowFormError = '',
    policyFormError = '',
    registrationCheck = '',
    registrationOpen = 0;
  let config = { ...baseConfig },
    policy = 'cost',
    route = 'workflows',
    busy = false;
  let artifacts = [],
    runs = [];
  let activeTool = null,
    toolStyle = 'sticks',
    toolOpened = false;
  let toastTimer,
    returnFocus = null,
    registrationSaveTimer;
  const DEMO_KEY = 'yanxu-product-loop-v1',
    DEMO_VERSION = 1;
  const ME = { id: 'me', name: '我（演示研究者）' };
  const initialWorkflows = JSON.parse(JSON.stringify(workflowInfo));
  let product = {
    version: DEMO_VERSION,
    catalog: [],
    experiments: [],
    drafts: {},
    next: 1,
    selectedWorkflow: 'protein',
  };
  let page = { name: 'workflows', id: '', query: new URLSearchParams() };
  let storageOK = true,
    storageNotice = '',
    simulationToken = 0,
    activeSimulation = null;
  let catalogScope = 'current',
    catalogText = '',
    experimentScope = 'mine',
    selectedPlanStep = '';
  let flowMotionEnabled = typeof matchMedia !== 'function' ||
    !matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Display helpers
  const $ = (s) => document.querySelector(s);
  const icon = (name) =>
    /* HTML */ `<svg class="icon" aria-hidden="true"><use href="#i-${name}" /></svg>`;
  const esc = (v) =>
    String(v).replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
  const fmt = (n) => (n >= 60 ? `${Math.floor(n / 60)}m ${Math.round(n % 60)}s` : `${n}s`);
  const gb = (n) => (n < 0.01 ? `${Math.round(n * 1000)} MB` : `${n.toFixed(2)} GB`);
  const copy = (value) => JSON.parse(JSON.stringify(value));
  const dateText = (value) => new Date(value).toLocaleString('zh-CN', { hour12: false });
  const notify = function notify(message) {
    $('#toast').textContent = message;
    $('#toast').hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => ($('#toast').hidden = true), 3200);
  };
  const heading = function heading(title, subtitle, actions = '') {
    const scoped = ['catalog', 'runs', 'policy'].includes(route);
    return /* HTML */ `<div class="page-heading">
      <div>
        <div class="eyebrow">AI4S 工作台</div>
        <h1>${esc(title)}</h1>
        <p>${scoped ? esc(workflowInfo[activeWorkflow].short) + ' · ' : ''}${esc(subtitle)}</p>
      </div>
      <div class="heading-actions">${actions}</div>
    </div>`;
  };
  const button = function button(label, action, value = '', primary = false, disabled = false) {
    return /* HTML */ `<button
      type="button"
      class="btn ${primary ? 'primary' : ''}"
      data-action="${action}"
      data-value="${esc(value)}"
      ${disabled ? 'disabled' : ''}
    >
      ${label}
    </button>`;
  };
  const routeButton = function routeButton(label, name, id = '', primary = false) {
    return /* HTML */ `<button
      type="button"
      class="btn ${primary ? 'primary' : ''}"
      data-route="${name}"
      data-id="${esc(id)}"
    >
      ${label}
    </button>`;
  };
  const banner = function banner(text) {
    return /* HTML */ `<div class="info-banner">${text}</div>`;
  };
  const panel = function panel(title, content, meta = '') {
    return /* HTML */ `<section class="panel">
      <div class="panel-head">
        <div class="panel-title">${title}</div>
        ${meta}
      </div>
      ${content}
    </section>`;
  };
  const statusBadge = function statusBadge(value) {
    const names = {
      ready: '待运行',
      completed: '模拟完成',
      running: '模拟进行中',
      waiting: '等待共享结果',
      failed: '模拟失败',
      cancelled: '已取消',
      interrupted: '页面离开后中断',
      complete: '模拟文件可读取',
      missing: '模拟文件缺失',
    };
    return /* HTML */ `<span
      class="pill ${['completed', 'complete'].includes(value)
        ? 'good'
        : ['failed', 'missing', 'interrupted'].includes(value)
          ? 'warn'
          : 'blue'}"
      >${names[value] || esc(value)}</span
    >`;
  };
  const field = function field(label, name, value, type = 'text', hint = '') {
    return /* HTML */ `<label class="field"
      ><span>${esc(label)}</span
      ><input
        data-draft="${name}"
        type="${type}"
        value="${esc(value)}"
        ${type === 'number' ? 'min="0" max="999999" step="1"' : ''}
      />${hint ? /* HTML */ `<div class="field-hint">${esc(hint)}</div>` : ''}</label
    >`;
  };
  const choiceField = function choiceField(label, name, value, options, hint = '') {
    return /* HTML */ `<label class="field"
      ><span>${esc(label)}</span
      ><select data-draft="${name}">
        ${options
          .map(
            ([id, name]) =>
              /* HTML */ `<option
                value="${esc(id)}"
                ${String(value) === String(id) ? 'selected' : ''}
              >
                ${esc(name)}
              </option>`,
          )
          .join('')}</select
      >${hint ? /* HTML */ `<div class="field-hint">${esc(hint)}</div>` : ''}</label
    >`;
  };

  // Workflow definitions and registration
  const workflowKind = function workflowKind(id = activeWorkflow) {
    return workflowInfo[id].template;
  };
  const registrationSteps = function registrationSteps(template) {
    return template === 'protein'
      ? proteinSteps
      : template === 'molecule'
        ? moleculeSteps
        : [{ id: 'step-1', name: '自定义步骤', file: 'output.json', deps: [] }];
  };
  const blankRegistration = function blankRegistration(step, index, template) {
    return {
      id: step.id,
      name: step.name,
      modelPath: '',
      docPath: '',
      command: '',
      version: '',
      input: step.deps.length
        ? step.deps
            .map((id) => registrationSteps(template).find((s) => s.id === id).file)
            .join(', ')
        : template === 'protein'
          ? 'input.fasta'
          : step.id === 'target'
            ? 'target.pdb'
            : 'input.json',
      output: step.file || 'output-' + (index + 1) + '.json',
    };
  };
  const emptyWorkflowDraft = function emptyWorkflowDraft(template = 'custom') {
    return {
      name: '',
      template,
      description: '',
      projectPath: '',
      workflowDoc: '',
      workflowCommand: '',
      environment: '',
      inputPath: '',
      registrations: registrationSteps(template).map((s, i) => blankRegistration(s, i, template)),
    };
  };
  const demoWorkflowDraft = function demoWorkflowDraft(template = 'custom') {
    const d = emptyWorkflowDraft(template);
    d.projectPath = '/workspace/my-science-project';
    d.workflowDoc = 'README.md';
    d.environment = 'conda:science-demo';
    d.inputPath = template === 'protein' ? 'data/input.fasta' : 'data/input.json';
    d.registrations = d.registrations.map((s, i) => ({
      ...s,
      modelPath: 'models/' + s.id,
      docPath: 'docs/' + s.id + '.md',
      version: 'demo-v1',
      command: 'python run.py --input {input} --output {output}',
    }));
    return d;
  };
  const ensureRegistrationDraft = function ensureRegistrationDraft() {
    const fallback = emptyWorkflowDraft(workflowDraft.template || 'custom');
    for (const key of [
      'projectPath',
      'workflowDoc',
      'workflowCommand',
      'environment',
      'inputPath',
      'registrations',
    ])
      if (workflowDraft[key] === undefined) workflowDraft[key] = fallback[key];
  };
  const validateRegistration = function validateRegistration(data) {
    for (const [key, label] of [
      ['projectPath', '项目路径'],
      ['workflowDoc', '流程说明文件'],
      ['environment', '运行环境'],
      ['inputPath', '输入数据路径'],
    ])
      if (!String(data[key] || '').trim()) return '请填写' + label + '。';
    if (!Array.isArray(data.registrations) || !data.registrations.length)
      return '请至少添加一个步骤，并填写接入信息。';
    if (data.registrations.length > 12) return '演示版最多支持 12 个步骤。';
    if (
      data.template !== 'custom' &&
      data.registrations.length !== registrationSteps(data.template).length
    )
      return '模板步骤数量不一致，请重新选择模板。';
    const names = new Set();
    for (let i = 0; i < data.registrations.length; i++) {
      const step = data.registrations[i];
      for (const [key, label] of [
        ['name', '步骤名称'],
        ['modelPath', '模型或程序路径'],
        ['docPath', '说明文件'],
        ['command', '调用指令'],
        ['version', '模型或代码版本'],
        ['input', '输入说明'],
        ['output', '输出文件'],
      ])
        if (!String(step[key] || '').trim()) return '第 ' + (i + 1) + ' 步：请填写' + label + '。';
      if (String(step.name).length > 60) return '步骤名称最多 60 个字。';
      if (String(step.command).length > 4000) return '每条调用指令最多 4000 个字符。';
      if (names.has(step.name.trim())) return '步骤名称重复，请为每一步设置不同名称。';
      names.add(step.name.trim());
    }
    return '';
  };
  const registeredSteps = function registeredSteps(profiles) {
    return profiles.map((p, i) => ({
      id: 'step-' + (i + 1),
      name: p.name,
      file: p.output.split('/').filter(Boolean).pop() || 'output',
      kind: /\.cif$/i.test(p.output) ? 'mmCIF' : /\.sdf$/i.test(p.output) ? 'SDF' : 'FILE',
      icon: i ? 'box' : 'code',
      deps: i ? ['step-' + i] : [],
      cost: 60 * (i + 1),
      load: 2 * (i + 1),
      size: 0.01 * (i + 1),
      description: '使用已登记的程序和调用指令。当前只演示执行顺序，不运行真实命令。',
    }));
  };
  const createWorkflow = function createWorkflow(data) {
    const name = String(data.name || '').trim(),
      description = String(data.description || '').trim(),
      template = data.template;
    if (!name) return { ok: false, error: '请填写流程名称。' };
    if (name.length > 40) return { ok: false, error: '流程名称最多 40 个字。' };
    if (description.length > 160) return { ok: false, error: '简单介绍最多 160 个字。' };
    if (!['protein', 'molecule', 'custom'].includes(template))
      return { ok: false, error: '请选择流程类型。' };
    if (
      Object.values(workflowInfo).some(
        (w) => w.name.toLocaleLowerCase() === name.toLocaleLowerCase(),
      )
    )
      return { ok: false, error: '已有同名流程，请换一个名称。' };
    const error = validateRegistration(data);
    if (error) return { ok: false, error };
    const id =
        'workflow-' +
        String(Object.values(workflowInfo).filter((w) => w.custom).length + 1).padStart(3, '0'),
      base =
        template === 'custom'
          ? { color: 'green', tags: ['自定义模型', '命令接入'], english: 'CUSTOM WORKFLOW' }
          : workflowInfo[template];
    const profiles = data.registrations.map((step, i) => ({
      ...step,
      id: template === 'custom' ? 'step-' + (i + 1) : registrationSteps(template)[i].id,
    }));
    const executionDefinition = JSON.parse(
      JSON.stringify({
        projectPath: data.projectPath.trim(),
        workflowDoc: data.workflowDoc.trim(),
        workflowCommand: String(data.workflowCommand || '').trim(),
        environment: data.environment.trim(),
        inputPath: data.inputPath.trim(),
        steps: profiles,
        ...(data.agentSource ? {agentSource: data.agentSource} : {}),
      }),
    );
    workflowInfo[id] = {
      ...base,
      name,
      short: name,
      description:
        description ||
        (template === 'custom'
          ? '按登记的模型和指令，连接自己的科研任务。'
          : '基于' + base.name + '模板创建。'),
      template,
      custom: true,
      executionDefinition,
      steps:
        template === 'custom'
          ? registeredSteps(profiles)
          : registrationSteps(template).map((step, i) => ({
              ...step,
              name: profiles[i].name,
              file: profiles[i].output.split('/').filter(Boolean).pop() || step.file,
            })),
    };
    const workflow = workflowInfo[id];
    workflow.steps.forEach((step, index) => {
      step.kind = inferredKind(workflow.executionDefinition.steps[index].output);
    });
    return { ok: true, id };
  };
  const inferredKind = function inferredKind(filename) {
    const formats = [
      [/\.(fasta|fa|faa)$/i, 'FASTA'],
      [/\.smi$/i, 'SMILES'],
      [/\.sdf$/i, 'SDF'],
      [/\.cif$/i, 'mmCIF'],
      [/\.pdb$/i, 'PDB'],
      [/\.pdbqt$/i, 'PDBQT'],
      [/\.json$/i, 'JSON'],
      [/\.npy$/i, 'NumPy'],
      [/\.a3m$/i, 'A3M'],
    ];
    for (const [extension, kind] of formats) {
      if (extension.test(filename)) return kind;
    }
    return 'FILE';
  };
  const registrationComplete = function registrationComplete(step) {
    return ['name', 'modelPath', 'docPath', 'command', 'version', 'input', 'output'].every((key) =>
      String(step[key] || '').trim(),
    );
  };
  const projectField = function projectField(key, label, placeholder) {
    return /* HTML */ `<label class="field"
      ><span>${label} <i>必填</i></span
      ><input
        data-project-field="${key}"
        aria-label="${label}"
        value="${esc(workflowDraft[key] || '')}"
        placeholder="${placeholder}"
    /></label>`;
  };
  const registrationField = function registrationField(
    index,
    key,
    label,
    placeholder,
    wide = false,
  ) {
    const step = workflowDraft.registrations[index],
      attrs = `data-reg-index="${index}" data-reg-field="${key}" aria-label="第 ${index + 1} 步 ${label}"`;
    return /* HTML */ `<label class="field ${wide ? 'registration-wide' : ''}"
      ><span>${label} <i>必填</i></span
      >${key === 'command'
        ? /* HTML */ `<textarea
            ${attrs}
            rows="3"
            maxlength="4000"
            spellcheck="false"
            placeholder="${esc(placeholder)}"
          >
${esc(step[key] || '')}</textarea
          >`
        : /* HTML */ `<input
            ${attrs}
            ${key === 'name' ? 'maxlength="60"' : ''}
            value="${esc(step[key] || '')}"
            placeholder="${esc(placeholder)}"
          />`}</label
    >`;
  };
  const registrationCard = function registrationCard(step, index, template) {
    return /* HTML */ `<details
      class="registration-card"
      ${index === registrationOpen ? 'open' : ''}
      data-registration-details="${index}"
    >
      <summary>
        <span class="registration-number">${index + 1}</span
        ><span id="registration-title-${index}">${esc(step.name || '未命名步骤')}</span
        ><span
          class="pill ${registrationComplete(step) ? 'good' : ''}"
          id="registration-status-${index}"
          >${registrationComplete(step) ? '已填写' : '待填写'}</span
        >
      </summary>
      <div class="registration-card-body">
        <div class="registration-grid">
          ${registrationField(index, 'name', '步骤名称', '例如：结构预测')}${registrationField(
            index,
            'version',
            '模型或代码版本',
            '例如：v1.2 / Git commit / 权重哈希',
          )}${registrationField(
            index,
            'modelPath',
            '模型或程序路径',
            'models/my-model 或 /srv/models/my-model',
          )}${registrationField(
            index,
            'docPath',
            '说明文件',
            'README.md 或 docs/model.md',
          )}${registrationField(
            index,
            'command',
            '调用指令',
            'python run.py --input {input} --output {output}',
            true,
          )}${registrationField(
            index,
            'input',
            '输入说明',
            '例如：FASTA 文件 / 上一步输出',
          )}${registrationField(index, 'output', '输出文件', '例如：results/structure.cif')}
        </div>
        ${step.agentConfig ? /* HTML */ `<div class="registration-ai-summary">
          <strong>AI 配置 · ${esc(step.agentConfig.modelName)}</strong>
          <p>${Object.entries(step.agentConfig.parameters || {}).map(([key, value]) => `<code>${esc(key)} = ${esc(JSON.stringify(value))}</code>`).join(' ')}</p>
          <p class="small muted">来源：AI 草稿 r${esc(workflowDraft.agentSource?.revision ?? '')} · 仅配置，部署路径与指令待核对</p>
        </div>` : ''}
        <div class="registration-card-footer">
          <span>指令仅作为文本保存，不会执行。</span>${template === 'custom'
            ? /* HTML */ `<div>
                <button
                  type="button"
                  class="link-btn"
                  data-reg-action="up"
                  data-reg-index="${index}"
                  ${index === 0 ? 'disabled' : ''}
                >
                  上移</button
                ><button
                  type="button"
                  class="link-btn"
                  data-reg-action="down"
                  data-reg-index="${index}"
                  ${index === workflowDraft.registrations.length - 1 ? 'disabled' : ''}
                >
                  下移</button
                ><button
                  type="button"
                  class="link-btn"
                  data-reg-action="remove"
                  data-reg-index="${index}"
                  ${workflowDraft.registrations.length === 1 ? 'disabled' : ''}
                >
                  移除
                </button>
              </div>`
            : ''}
        </div>
      </div>
    </details>`;
  };
  const clearRegistrationCheck = function clearRegistrationCheck() {
    registrationCheck = '';
    if ($('#registration-check')) $('#registration-check').hidden = true;
    if ($('#workflow-form-error')) $('#workflow-form-error').hidden = true;
  };
  const showAIRegistration = function showAIRegistration() {
    nav('newworkflow', '', {mode: 'ai'});
  };
  const mountAIRegistration = async function mountAIRegistration(target) {
    if (!aiHost) {
      aiHost = document.createElement('div');
      target.replaceChildren(aiHost);
      aiMount = Promise.all([
        import(new URL('./agent/assets/app.js', document.baseURI).href),
        import(new URL('./assets/agent-registration.js', document.baseURI).href),
      ]).then(async ([{mountAssistant}, {registrationFromAgent}]) => {
        aiController = await mountAssistant(aiHost, {onApply({draft, models}) {
          workflowDraft = registrationFromAgent(draft, models, workflowDraft);
          registrationOpen = 0;
          registrationCheck = 'AI 步骤与参数已回填。请核对项目路径、环境、输入输出文件及调用指令；参数变化后的旧指令不会自动沿用。';
          workflowFormError = '';
          saveProduct();
          nav('newworkflow');
          notify('AI 配置已应用到接入草稿，请补齐部署信息。');
        }});
      });
    } else target.replaceChildren(aiHost);
    try {
      await aiMount;
      if (target.isConnected) aiController.redraw();
    } catch (error) {
      console.error('AI assistance unavailable', error);
      if (aiHost?.isConnected) {
        target.replaceChildren();
        const message = document.createElement('p');
        message.setAttribute('role', 'alert');
        message.textContent = 'AI 辅助暂时不可用，请稍后重试。你仍可切换到手动填写。';
        const retry = document.createElement('button');
        retry.className = 'btn'; retry.textContent = '重试';
        retry.onclick = () => { aiController?.destroy(); aiHost = null; aiMount = null; render(); };
        target.append(message, retry);
      }
    }
  };
  const reuseLabel = function reuseLabel(value) {
    return { cost: '读取更快时复用', lru: '结果可用就复用', none: '每次重新计算' }[value];
  };
  const storageLabel = function storageLabel(value) {
    return { cost: '优先保留重算费时的结果', lru: '优先保留最近使用的结果', none: '不保存新结果' }[
      value
    ];
  };
  const createPolicy = function createPolicy(data) {
    const name = String(data.name || '').trim(),
      description = String(data.description || '').trim();
    if (!name) return { ok: false, error: '请填写策略名称。' };
    if (name.length > 40) return { ok: false, error: '策略名称最多 40 个字。' };
    if (description.length > 160) return { ok: false, error: '简单介绍最多 160 个字。' };
    if (allPolicies().some((p) => p.name.toLocaleLowerCase() === name.toLocaleLowerCase()))
      return { ok: false, error: '已有同名策略，请换一个名称。' };
    if (
      !['cost', 'lru', 'none'].includes(data.reuse) ||
      !['cost', 'lru', 'none'].includes(data.storage)
    )
      return { ok: false, error: '请选择复用规则和保存规则。' };
    const id = 'policy-' + String(customPolicies.length + 1).padStart(3, '0');
    customPolicies.push({
      id,
      name,
      description: description || reuseLabel(data.reuse) + '；' + storageLabel(data.storage) + '。',
      reuse: data.reuse,
      storage: data.storage,
      custom: true,
    });
    return { ok: true, id };
  };
  const allPolicies = function allPolicies() {
    return [...builtinPolicies, ...customPolicies];
  };
  const policySettings = function policySettings(id = policy) {
    return allPolicies().find((p) => p.id === id) || builtinPolicies[2];
  };

  // Simulation identities and candidate decisions
  const hash = function hash(s) {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return (h >>> 0).toString(16).padStart(8, '0');
  };
  const identities = function (c) {
    const result = {},
      w = workflowInfo[activeWorkflow],
      definition = w.executionDefinition;
    for (const step of steps) {
      let args;
      if (w.template === 'custom')
        args = [step.deps.length ? '' : c.input, c.seed || '42', c.sampleToken || ''];
      else if (w.template === 'protein')
        args =
          step.id === 'prepare'
            ? [c.input, 'normalize-v1']
            : step.id === 'embedding'
              ? [c.embedding]
              : step.id === 'msa'
                ? [c.database]
                : step.id === 'structure'
                  ? [c.predictor, c.seed, c.sampleToken || '']
                  : ['report-v1'];
      else
        args =
          step.id === 'prepare'
            ? [c.input, 'standardize-v1']
            : step.id === 'generate'
              ? [c.embedding, c.seed, c.sampleToken || '']
              : step.id === 'target'
                ? [c.database, 'target-prepare-v1']
                : step.id === 'docking'
                  ? [c.predictor, c.seed, c.sampleToken || '']
                  : ['rank-v1'];
      const profile = definition?.steps.find((s) => s.id === step.id);
      if (profile)
        args.push(
          profile.command,
          profile.version,
          profile.modelPath,
          profile.input,
          profile.output,
          definition.environment,
        );
      result[step.id] =
        step.id +
        '-' +
        hash(JSON.stringify([w.template, step.id, args, step.deps.map((id) => result[id])]));
    }
    return result;
  };
  const versions = function versions(id, c) {
    const definition = workflowInfo[activeWorkflow].executionDefinition,
      profile = definition && definition.steps.find((p) => p.id === id);
    if (profile) return profile.version;
    if (workflowKind() === 'molecule')
      return id === 'prepare'
        ? 'standardize-v1'
        : id === 'generate'
          ? `${c.embedding} · seed ${c.seed}`
          : id === 'target'
            ? `${c.database} · prepare-v1`
            : id === 'docking'
              ? `${c.predictor} · seed ${c.seed}`
              : 'rank-v1';
    return id === 'prepare'
      ? 'normalize-v1'
      : id === 'embedding'
        ? c.embedding
        : id === 'msa'
          ? c.database
          : id === 'structure'
            ? `${c.predictor} · seed ${c.seed}`
            : 'report-v1';
  };
  const artifactById = (id) => product.catalog.find((a) => a.id === id);
  const experimentById = (id) => product.experiments.find((e) => e.id === id);
  const own = (a) => !!a && a.ownerId === ME.id;
  const visible = (a) => !!a && (own(a) || a.scope === 'team');
  const readable = (a) => !!a && a.status === 'complete' && a.accessible && a.retained !== false;
  const usable = (a) => visible(a) && readable(a);
  const workflowById = (id) => (Object.hasOwn(workflowInfo, id) ? workflowInfo[id] : null);
  const inputKinds = function inputKinds(w) {
    if (w.template === 'protein') return ['FASTA'];
    if (w.template === 'molecule') return ['SMILES', 'SDF'];
    const p = w.executionDefinition?.steps[0];
    return p
      ? [
          /\.cif\b/i.test(p.input)
            ? 'mmCIF'
            : /\.pdb\b/i.test(p.input)
              ? 'PDB'
              : /\.fasta\b|\.fa\b/i.test(p.input)
                ? 'FASTA'
                : /\.sdf\b/i.test(p.input)
                  ? 'SDF'
                  : /\.json\b/i.test(p.input)
                    ? 'JSON'
                    : 'FILE',
        ]
      : ['FILE'];
  };
  const accepts = function accepts(w, a) {
    return inputKinds(w).includes(a.kind);
  };
  const coreStep = function coreStep() {
    return workflowKind() === 'custom'
      ? steps[steps.length - 1].id
      : workflowKind() === 'protein'
        ? 'structure'
        : 'docking';
  };
  const currentDraft = function currentDraft() {
    return product.drafts[activeWorkflow] || null;
  };
  const nextId = function nextId(prefix) {
    return prefix + '-' + String(product.next++).padStart(4, '0');
  };
  const selectWorkflowContext = function selectWorkflowContext(id) {
    if (!workflowById(id)) return false;
    activeWorkflow = id;
    product.selectedWorkflow = id;
    steps = workflowInfo[id].steps || (workflowKind() === 'protein' ? proteinSteps : moleculeSteps);
    baseConfig =
      workflowKind() === 'custom'
        ? { input: workflowInfo[id].executionDefinition.inputPath, seed: '42', remote: false }
        : workflowKind() === 'protein'
          ? proteinBase
          : moleculeBase;
    const draft = product.drafts[id];
    config = draft ? draft.config : { ...baseConfig };
    policy = draft ? draft.policy : 'cost';
    artifacts = product.catalog;
    runs = product.experiments;
    return true;
  };
  const createExperimentDraft = function createExperimentDraft(id, from = null) {
    if (!workflowById(id)) return null;
    selectWorkflowContext(id);
    const definition = workflowInfo[id].executionDefinition;
    const c = from ? copy(from.config) : { ...baseConfig };
    if (!from && definition) c.input = definition.inputPath;
    const draft = {
      id: nextId('DRAFT'),
      workflowId: id,
      name: workflowInfo[id].name + ' · 新实验',
      config: c,
      policy: 'cost',
      intent: 'replay',
      reuseScope: 'team',
      shareOutput: 'team',
      inputSource: definition ? 'path' : 'sample',
      inputArtifactId: '',
      inputMeta: null,
      choices: {},
      simulation: 'success',
      createdAt: Date.now(),
    };
    if (from) {
      draft.intent = from.intent || 'replay';
      draft.reuseScope = from.reuseScope || 'team';
      draft.shareOutput = from.shareOutput || 'team';
      draft.inputSource = from.inputSource || 'path';
      draft.inputArtifactId = from.inputArtifactId || '';
      draft.inputMeta = copy(from.inputMeta || null);
      draft.name = (from.name || draft.name) + ' · 副本';
    }
    product.drafts[id] = draft;
    config = draft.config;
    policy = draft.policy;
    saveProduct();
    return draft;
  };
  const seedProduct = function seedProduct() {
    selectWorkflowContext('protein');
    const addSource = (id, ownerId, ownerName, wid, c, selected, extra = {}) => {
      selectWorkflowContext(wid);
      const outputs = selected.map((stepId) => {
        const a = makeArtifact(
          steps.find((s) => s.id === stepId),
          c,
          id,
          { ownerId, ownerName, ...extra },
        );
        product.catalog.push(a);
        return { stepId, artifactId: a.id, mode: 'compute' };
      });
      product.experiments.push({
        id,
        name: ownerId === 'me' ? '我的初始序列处理' : '团队共享示例 · ' + ownerName,
        ownerId,
        ownerName,
        workflowId: wid,
        workflowSnapshot: {
          ...copy(workflowInfo[wid]),
          steps: copy(steps.filter((s) => selected.includes(s.id))),
        },
        config: copy(c),
        intent: 'replay',
        reuseScope: 'team',
        shareOutput: 'team',
        inputSource: 'sample',
        inputArtifactId: '',
        inputMeta: null,
        policy: 'cost',
        policyRules: copy(builtinPolicies[2]),
        plan: [],
        outputs,
        log: ['预置模拟记录，用于体验共享检索；未执行真实计算。'],
        status: extra.status === 'running' ? 'running' : 'completed',
        fixture: true,
        createdAt: Date.now() - 3600000,
        metrics: { total: 0, compute: 0, load: 0 },
        storage: { saved: outputs.length, evicted: 0, skipped: 0 },
      });
    };
    addSource('SEED-001', 'me', ME.name, 'protein', proteinBase, ['prepare', 'embedding']);
    addSource('TEAM-001', 'member-lin', '林同学', 'protein', proteinBase, [
      'msa',
      'structure',
      'analysis',
    ]);
    addSource(
      'TEAM-002',
      'member-chen',
      '陈同学',
      'protein',
      { ...proteinBase, predictor: 'fold-v2', seed: '7' },
      ['structure'],
      { status: 'running' },
    );
    addSource(
      'TEAM-003',
      'member-zhou',
      '周同学',
      'protein',
      { ...proteinBase, predictor: 'fold-v2' },
      ['structure'],
      { status: 'missing', accessible: false },
    );
    addSource('TEAM-004', 'member-lin', '林同学', 'molecule', moleculeBase, ['prepare', 'target']);
    selectWorkflowContext('protein');
  };
  const makeArtifact = function makeArtifact(step, c, runId, extra = {}) {
    const keys = identities(c);
    return {
      id: nextId('ART'),
      key: keys[step.id],
      workflowId: activeWorkflow,
      workflowName: workflowInfo[activeWorkflow].name,
      family: workflowKind(),
      stepId: step.id,
      name: step.file,
      kind: step.kind,
      size: step.size,
      version: versions(step.id, c),
      config: copy(c),
      deps: step.deps.map((id) => keys[id]),
      parentArtifactIds: step.deps.map(
        (id) => product.catalog.find((a) => a.key === keys[id])?.id || null,
      ),
      runId,
      ownerId: ME.id,
      ownerName: ME.name,
      scope: 'team',
      status: 'complete',
      accessible: true,
      retained: true,
      pinned: false,
      lastUsed: Date.now(),
      createdAt: Date.now(),
      ...extra,
    };
  };
  const candidateList = function candidateList(step, key, draft) {
    return product.catalog
      .filter(
        (a) =>
          a.family === workflowKind() &&
          a.stepId === step.id &&
          visible(a) &&
          (draft.reuseScope === 'team' || own(a)),
      )
      .map((a) => ({ ...a, match: a.key === key }));
  };
  const plan = function (c = config, p = policy, draft = currentDraft()) {
    const d = draft || { reuseScope: 'team', choices: {}, intent: 'replay' },
      keys = identities(c),
      rules = policySettings(p);
    return steps.map((step) => {
      const candidates = candidateList(step, keys[step.id], d),
        ready = candidates
          .filter((a) => a.match && usable(a))
          .sort((a, b) => Number(own(b)) - Number(own(a))),
        waiting = candidates.filter((a) => a.match && a.status === 'running' && a.accessible);
      const choice = d.choices[step.id] || 'auto';
      let selectedArtifact = ready[0],
        action = 'compute',
        reason = '未找到可用的等价结果';
      const load = c.remote && step.id === coreStep() ? 1200 : step.load;
      if (ready.length && rules.reuse !== 'none' && (rules.reuse !== 'cost' || load < step.cost)) {
        action = 'reuse';
        reason = own(selectedArtifact)
          ? '我的结果匹配，模拟文件可读取'
          : '团队共享结果匹配，模拟文件可读取';
      } else if (ready.length)
        reason = rules.reuse === 'none' ? '策略要求重新计算' : '结果有效，但预计读取比重算慢';
      else if (waiting.length) reason = '有人正在生成，可选择等待或另算';
      else if (candidates.some((a) => a.match)) reason = '条件匹配，但文件缺失或不可读取';
      else if (candidates.length) reason = '已有历史结果的输入、版本或上游依赖不同';
      if (choice === 'compute') {
        action = 'compute';
        reason = '本次实验选择重新计算';
        selectedArtifact = null;
      } else if (choice.startsWith('reuse:')) {
        selectedArtifact = ready.find((a) => a.id === choice.slice(6));
        if (selectedArtifact) {
          action = 'reuse';
          reason = '手动选择可读取的等价结果';
        } else {
          action = 'compute';
          reason = '原选择已不可用，需重新检查';
        }
      } else if (choice.startsWith('wait:')) {
        selectedArtifact =
          waiting.find((a) => a.id === choice.slice(5)) ||
          ready.find((a) => a.id === choice.slice(5));
        if (selectedArtifact) {
          action = selectedArtifact.status === 'running' ? 'wait' : 'reuse';
          reason = action === 'wait' ? '等待所选团队模拟任务完成' : '所等结果已完成，可以复用';
        } else {
          action = 'compute';
          reason = '等待对象不可用，需重新检查';
        }
      }
      return {
        ...step,
        key: keys[step.id],
        valid: ready.length > 0,
        reuse: action === 'reuse',
        action,
        artifact: selectedArtifact ? copy(selectedArtifact) : null,
        candidates,
        load,
        time: action === 'compute' ? step.cost : action === 'wait' ? load + 30 : load,
        reason,
      };
    });
  };
  const planMetrics = function planMetrics(p) {
    return {
      total: p.reduce((n, s) => n + s.time, 0),
      compute: p.filter((s) => s.action === 'compute').reduce((n, s) => n + s.cost, 0),
      load: p.filter((s) => s.action !== 'compute').reduce((n, s) => n + s.load, 0),
      reuse: p.filter((s) => s.action === 'reuse').length,
      wait: p.filter((s) => s.action === 'wait').length,
    };
  };
  const metrics = function metrics(p = plan()) {
    const total = p.reduce((a, s) => a + s.time, 0),
      baseline = steps.reduce((a, s) => a + s.cost, 0);
    return {
      total,
      baseline,
      reuse: p.filter((s) => s.reuse).length,
      valid: p.filter((s) => s.valid).length,
      saved: Math.max(0, Math.round((1 - total / baseline) * 100)),
      load: p.filter((s) => s.reuse).reduce((a, s) => a + s.load, 0),
      compute: p.filter((s) => !s.reuse).reduce((a, s) => a + s.cost, 0),
    };
  };
  const validateExperiment = function validateExperiment(d) {
    if (!d.name.trim()) return '请填写实验名称。';
    if (!String(d.config.input || '').trim()) return '请选择或填写输入数据。';
    if (!/^\d{1,6}$/.test(String(d.config.seed))) return '随机种子须为 0–999999 的整数。';
    if (d.inputSource === 'upload' && !d.inputMeta) return '请先选择一个本地文件。';
    if (d.inputSource === 'artifact') {
      const a = artifactById(d.inputArtifactId);
      if (!usable(a) || !accepts(workflowInfo[activeWorkflow], a))
        return '所选产物不可读取，或格式不符合此流程。';
    }
    return '';
  };
  const packPlan = function packPlan(d) {
    return plan(d.config, d.policy, d).map((s) => ({
      ...copy(s),
      version: versions(s.id, d.config),
    }));
  };
  const invalidateDraft = function invalidateDraft() {
    const d = currentDraft();
    if (d) {
      d.choices = {};
      config = d.config;
      policy = d.policy;
      saveProduct();
    }
  };
  const setDraftValue = function setDraftValue(name, value) {
    const d = currentDraft();
    if (!d) return;
    if (name.startsWith('config.')) {
      const key = name.slice(7);
      d.config[key] = key === 'remote' ? value === 'true' : value;
    } else d[name] = value;
    if (name === 'intent') {
      if (value === 'fresh') d.config.sampleToken = d.id;
      else delete d.config.sampleToken;
    }
    if (name === 'inputSource') {
      d.inputArtifactId = '';
      d.inputMeta = null;
      d.config.input =
        value === 'sample'
          ? workflowKind() === 'protein'
            ? 'seq-a'
            : workflowKind() === 'molecule'
              ? 'fragment-a'
              : 'demo-input.json'
          : '';
    }
    if (name === 'inputArtifactId') {
      const a = artifactById(value);
      d.config.input = a ? 'artifact:' + a.key : '';
      d.inputMeta = a
        ? { name: a.name, kind: a.kind, note: '已有产物 ' + a.id + '；生成实验 ' + a.runId }
        : null;
    }
    invalidateDraft();
  };

  // Simulation execution and persistence
  const persistable = function persistable() {
    return {
      ...copy(product),
      customWorkflows: Object.fromEntries(Object.entries(workflowInfo).filter(([, w]) => w.custom)),
      customPolicies: copy(customPolicies),
      registrationDraft: copy(workflowDraft),
      policyDraft: copy(policyDraft),
    };
  };
  const saveProduct = function saveProduct() {
    try {
      localStorage.setItem(DEMO_KEY, JSON.stringify(persistable()));
      storageOK = true;
    } catch (error) {
      storageOK = false;
      storageNotice = '浏览器未能保存。请导出体验记录，避免刷新后丢失。';
    }
    DemoAPI.scheduleSave(persistable());
  };
  const validateSaved = function validateSaved(data) {
    if (
      !data ||
      data.version !== DEMO_VERSION ||
      !Array.isArray(data.catalog) ||
      !Array.isArray(data.experiments) ||
      !data.drafts ||
      typeof data.drafts !== 'object' ||
      !Number.isSafeInteger(data.next) ||
      data.next < 1
    )
      throw Error('文件不是此版本的体验记录。');
    if (data.catalog.length > 3000 || data.experiments.length > 1000)
      throw Error('记录数量超出演示上限。');
    const idOK = (id) =>
      typeof id === 'string' &&
      /^[a-zA-Z0-9_-]{1,90}$/.test(id) &&
      !['__proto__', 'constructor', 'prototype'].includes(id);
    const unique = (list) => new Set(list.map((x) => x.id)).size === list.length;
    if (!unique(data.catalog) || !unique(data.experiments)) throw Error('记录编号重复。');
    for (const [id, w] of Object.entries(data.customWorkflows || {}))
      if (
        !idOK(id) ||
        !w.custom ||
        !Array.isArray(w.steps) ||
        !w.steps.length ||
        w.steps.length > 12 ||
        !w.executionDefinition ||
        !Array.isArray(w.executionDefinition.steps) ||
        !['protein', 'molecule', 'custom'].includes(w.template)
      )
        throw Error('流程定义不完整。');
    const ids = new Set([
      ...Object.keys(initialWorkflows),
      ...Object.keys(data.customWorkflows || {}),
    ]);
    for (const a of data.catalog)
      if (
        !idOK(a.id) ||
        !Array.isArray(a.deps) ||
        !a.config ||
        typeof a.name !== 'string' ||
        typeof a.key !== 'string' ||
        !Number.isFinite(a.size) ||
        a.size < 0 ||
        !['complete', 'running', 'missing', 'failed'].includes(a.status)
      )
        throw Error('产物记录不完整。');
    for (const e of data.experiments)
      if (
        !idOK(e.id) ||
        !ids.has(e.workflowId) ||
        !e.workflowSnapshot ||
        !Array.isArray(e.workflowSnapshot.steps) ||
        !e.workflowSnapshot.steps.length ||
        !Array.isArray(e.plan) ||
        !Array.isArray(e.outputs) ||
        !Array.isArray(e.log) ||
        !e.config ||
        typeof e.name !== 'string'
      )
        throw Error('实验记录不完整。');
    for (const [id, d] of Object.entries(data.drafts))
      if (
        !ids.has(id) ||
        !d.config ||
        !d.choices ||
        typeof d.name !== 'string' ||
        !['replay', 'fresh'].includes(d.intent)
      )
        throw Error('实验草稿不完整。');
    for (const p of data.customPolicies || [])
      if (
        !idOK(p.id) ||
        typeof p.name !== 'string' ||
        !['cost', 'lru', 'none'].includes(p.reuse) ||
        !['cost', 'lru', 'none'].includes(p.storage)
      )
        throw Error('策略配置无效。');
    return data;
  };
  const applySaved = function applySaved(data) {
    validateSaved(data);
    Object.keys(workflowInfo).forEach((id) => {
      if (workflowInfo[id].custom) delete workflowInfo[id];
    });
    Object.assign(workflowInfo, copy(data.customWorkflows || {}));
    customPolicies.splice(0, customPolicies.length, ...copy(data.customPolicies || []));
    product = {
      version: DEMO_VERSION,
      catalog: data.catalog,
      experiments: data.experiments,
      drafts: data.drafts,
      next: data.next,
      selectedWorkflow: workflowById(data.selectedWorkflow) ? data.selectedWorkflow : 'protein',
    };
    if (
      data.registrationDraft &&
      ['protein', 'molecule', 'custom'].includes(data.registrationDraft.template) &&
      Array.isArray(data.registrationDraft.registrations)
    )
      workflowDraft = data.registrationDraft;
    if (data.policyDraft && typeof data.policyDraft.name === 'string')
      policyDraft = data.policyDraft;
    for (const e of product.experiments)
      if (!e.fixture && ['running', 'waiting'].includes(e.status)) {
        e.status = 'interrupted';
        e.log.push('页面离开后模拟已中断；已完成步骤的记录保留，请复制配置重新运行。');
      }
    selectWorkflowContext(product.selectedWorkflow);
  };
  const createExperiment = function createExperiment() {
    const d = currentDraft();
    if (!d) return;
    const error = validateExperiment(d);
    if (error) {
      notify(error);
      return;
    }
    const p = packPlan(d),
      w = workflowInfo[activeWorkflow];
    const e = {
      id: nextId('EXP'),
      name: d.name.trim(),
      ownerId: ME.id,
      ownerName: ME.name,
      workflowId: activeWorkflow,
      workflowSnapshot: { ...copy(w), steps: copy(steps) },
      config: copy(d.config),
      intent: d.intent,
      reuseScope: d.reuseScope,
      shareOutput: d.shareOutput,
      choices: copy(d.choices),
      inputSource: d.inputSource,
      inputArtifactId: d.inputArtifactId,
      inputMeta: copy(d.inputMeta),
      policy: d.policy,
      policyRules: copy(policySettings(d.policy)),
      plan: p,
      outputs: [],
      log: ['实验已创建；输入、流程和参数已保存，等待确认运行。'],
      status: 'ready',
      fixture: false,
      createdAt: Date.now(),
      metrics: planMetrics(p),
      storage: { saved: 0, evicted: 0, skipped: 0 },
      simulation: d.simulation,
    };
    product.experiments.push(e);
    delete product.drafts[activeWorkflow];
    selectedPlanStep = '';
    saveProduct();
    nav('experiment', e.id);
  };
  const startExperiment = function startExperiment(id = page.id) {
    const e = experimentById(id);
    if (!e || e.fixture || e.status !== 'ready') return;
    if (product.experiments.some((run) => run !== e && !run.fixture && ['running', 'waiting'].includes(run.status))) {
      notify('已有一个模拟实验进行中，请查看实验记录或取消后再运行。');
      return;
    }
    e.log.push('模拟实验已启动；使用已保存的输入、候选选择和配置快照。');
    e.status = 'running';
    saveProduct();
    render();
    runSimulation(e);
  };
  const runSimulation = async function runSimulation(e) {
    const token = ++simulationToken;
    activeSimulation = e.id;
    for (let i = e.outputs.length; i < e.plan.length; i++) {
      if (token !== simulationToken || !['running', 'waiting'].includes(e.status)) break;
      e.currentStep = i;
      e.status = e.plan[i].action === 'wait' ? 'waiting' : 'running';
      saveProduct();
      render();
      await new Promise((resolve) => setTimeout(resolve, e.status === 'waiting' ? 1100 : 650));
      if (token !== simulationToken || !['running', 'waiting'].includes(e.status)) break;
      if (!completeSimulationStep(e, i)) break;
      render();
    }
    if (token === simulationToken) {
      if (['running', 'waiting'].includes(e.status)) {
        e.status = 'completed';
        e.finishedAt = Date.now();
        e.log.push('模拟完成。耗时、大小及科学产物均为示例。');
      }
      activeSimulation = null;
      saveProduct();
      render();
    }
  };
  const completeSimulationStep = function completeSimulationStep(e, index) {
    if (!['running', 'waiting'].includes(e.status)) return false;
    const s = e.plan[index];
    if (e.simulation === 'fail' && index === Math.min(e.workflowSnapshot.steps.length - 1, 3)) {
      e.status = 'failed';
      e.failedStep = s.id;
      e.log.push(s.name + ' · 模拟步骤失败。已完成产物保留，可复制配置重试。');
      saveProduct();
      return false;
    }
    let a;
    if (s.action === 'wait') {
      a = artifactById(s.artifact.id);
      if (!a || !a.accessible || !visible(a)) {
        e.status = 'failed';
        e.log.push('等待结果无法读取，模拟已停止。');
        saveProduct();
        return false;
      }
      a.status = 'complete';
      const origin = experimentById(a.runId);
      if (origin) {
        origin.status = 'completed';
        origin.log.push('演示推进：协作者的模拟结果已完成。');
      }
      e.log.push(s.name + ' · 模拟协作者任务完成，继续复用。');
    } else if (s.action === 'reuse') a = artifactById(s.artifact.id);
    if (s.action !== 'compute') {
      if (!usable(a) || a.key !== s.key) {
        e.status = 'failed';
        e.log.push('所选结果已失效，模拟已停止；请重新检查候选。');
        saveProduct();
        return false;
      }
      a.lastUsed = Date.now();
      e.outputs.push({ stepId: s.id, artifactId: a.id, mode: s.action });
      e.log.push(
        s.name +
          ' · ' +
          (s.action === 'wait' ? '等待后复用' : '复用') +
          ' ' +
          a.id +
          ' · 来源 ' +
          a.ownerName +
          ' / ' +
          a.runId,
      );
    } else {
      const keys = Object.fromEntries(e.plan.map((s) => [s.id, s.key]));
      a = {
        id: nextId('ART'),
        key: s.key,
        workflowId: e.workflowId,
        workflowName: e.workflowSnapshot.name,
        family: e.workflowSnapshot.template,
        stepId: s.id,
        name: s.file,
        kind: s.kind,
        size: s.size,
        version:
          s.version ||
          e.workflowSnapshot.executionDefinition?.steps.find((x) => x.id === s.id)?.version ||
          'demo · ' + s.id,
        config: copy(e.config),
        deps: s.deps.map((id) => keys[id]),
        parentArtifactIds: s.deps.map(
          (id) => e.outputs.find((out) => out.stepId === id)?.artifactId || null,
        ),
        inputArtifactId: e.inputArtifactId || '',
        runId: e.id,
        ownerId: ME.id,
        ownerName: ME.name,
        scope: e.shareOutput,
        status: 'complete',
        accessible: true,
        retained: true,
        pinned: false,
        createdAt: Date.now(),
        lastUsed: Date.now(),
        computeCost: s.cost,
      };
      product.catalog.push(a);
      retainProduct(a, e);
      e.outputs.push({ stepId: s.id, artifactId: a.id, mode: 'compute' });
      e.log.push(
        s.name +
          ' · 模拟计算完成 · ' +
          a.id +
          (a.retained ? ' · 已登记到复用目录' : ' · 未保留模拟文件，仅保留来源记录'),
      );
    }
    e.status = 'running';
    saveProduct();
    return true;
  };
  const retainProduct = function retainProduct(a, e) {
    const rule = e.policyRules.storage;
    if (rule === 'none') {
      a.retained = false;
      e.storage.skipped++;
      return;
    }
    let used = product.catalog
      .filter((x) => own(x) && x.retained && x.status === 'complete')
      .reduce((n, x) => n + x.size, 0);
    if (used > 4) {
      const protectedIds = new Set(
        product.experiments
          .filter((run) => !run.fixture && ['running', 'waiting'].includes(run.status))
          .flatMap((run) =>
            run.plan.filter((step) => step.action !== 'compute').map((step) => step.artifact?.id),
          ),
      );
      const candidates = product.catalog
        .filter(
          (x) =>
            own(x) && x.retained && !x.pinned && !protectedIds.has(x.id) && x.status === 'complete',
        )
        .sort((a, b) =>
          rule === 'lru'
            ? a.lastUsed - b.lastUsed
            : (a.computeCost || 60) / a.size - (b.computeCost || 60) / b.size,
        );
      for (const item of candidates) {
        if (used <= 4) break;
        item.retained = false;
        used -= item.size;
        if (item.id !== a.id) {
          e.storage.evicted++;
          e.log.push('模拟保留策略移出可复用目录：' + item.name + '；历史来源记录保留。');
        }
      }
    }
    if (a.retained) e.storage.saved++;
    else e.storage.skipped++;
  };
  const cancelExperiment = function cancelExperiment(id) {
    const e = experimentById(id);
    if (!e || e.fixture || !['running', 'waiting'].includes(e.status)) return;
    e.status = 'cancelled';
    e.log.push('用户停止本次模拟；已完成步骤和产物记录保留。');
    simulationToken++;
    activeSimulation = null;
    saveProduct();
    render();
  };
  const cloneExperiment = function cloneExperiment(id, replace = false) {
    const e = experimentById(id);
    if (!e) return;
    if (product.drafts[e.workflowId] && !replace)
      return confirmDraftReplacement(e.workflowId, () => cloneExperiment(id, true));
    const draft = createExperimentDraft(e.workflowId, e);
    if (draft.intent === 'fresh') draft.config.sampleToken = draft.id;
    saveProduct();
    nav('workflow', e.workflowId);
  };
  const useArtifactInput = function useArtifactInput(id, wid, replace = false) {
    const a = artifactById(id),
      w = workflowById(wid);
    if (!usable(a) || !w || !accepts(w, a)) {
      notify('产物不可读取，或该流程不接受此格式。');
      return;
    }
    if (product.drafts[wid] && !replace)
      return confirmDraftReplacement(wid, () => useArtifactInput(id, wid, true));
    createExperimentDraft(wid);
    setDraftValue('inputSource', 'artifact');
    setDraftValue('inputArtifactId', id);
    nav('workflow', wid);
  };
  const confirmDraftReplacement = function confirmDraftReplacement(wid, proceed) {
    openModal(
      '保留或替换实验草稿',
      /* HTML */ `<p>
          此流程已有实验草稿“${esc(
            product.drafts[wid].name,
          )}”。继续创建会替换这份草稿；可以先导出备份。
        </p>
        ${button('导出当前记录', 'export-state')}
        <button class="btn" id="resume-existing">继续原草稿</button>
        <button class="btn primary" id="replace-existing">替换草稿并继续</button>`,
    );
    bindProductActions($('#modal-content'));
    $('#resume-existing').onclick = () => {
      closeModal();
      nav('workflow', wid);
    };
    $('#replace-existing').onclick = () => {
      closeModal();
      proceed();
    };
  };

  // Page templates
  const workflowArt = function workflowArt(kind) {
    if (kind === 'custom')
      return /* HTML */ `<svg viewBox="0 0 560 172" fill="none" aria-hidden="true">
        <g stroke="currentColor" opacity=".5" stroke-width="2">
          <path d="M110 86h340" />
          <rect x="80" y="56" width="60" height="60" rx="12" fill="#eff1f9" />
          <rect x="250" y="56" width="60" height="60" rx="12" fill="#eff1f9" />
          <rect x="420" y="56" width="60" height="60" rx="12" fill="#eff1f9" />
          <path
            d="m101 76-10 10 10 10m18-20 10 10-10 10m155-20-10 10 10 10m18-20 10 10-10 10m155-20-10 10 10 10m18-20 10 10-10 10"
          />
        </g>
      </svg>`;
    return kind === 'protein'
      ? /* HTML */ `<svg viewBox="0 0 560 172" fill="none" aria-hidden="true">
          <g opacity=".13" stroke="currentColor">
            <path d="M10 135H550M10 115H550M10 95H550M10 75H550M10 55H550" />
          </g>
          <g stroke="currentColor" stroke-width="2.3" opacity=".75">
            <path d="M287 4c-8 38 143 28 134 65S277 92 291 132s101 17 129 41" />
            <path d="M414 4c8 38-143 28-134 65s144 23 130 63-101 17-129 41" />
          </g>
          <g stroke="currentColor" opacity=".36">
            <path
              d="m294 22 111 0m-91 15h74m-48 15h23m-37 17h50m-83 17h116m-105 16h101m-78 17h47m-50 17h58m-90 16h118"
            />
          </g>
          <circle cx="281" cy="69" r="4" fill="currentColor" />
          <circle cx="411" cy="132" r="4" fill="currentColor" />
        </svg>`
      : /* HTML */ `<svg viewBox="0 0 560 172" fill="none" aria-hidden="true">
          <g opacity=".1" stroke="currentColor">
            <path d="M10 135H550M10 115H550M10 95H550M10 75H550M10 55H550" />
          </g>
          <g stroke="currentColor" stroke-width="2" stroke-linejoin="round" opacity=".8">
            <path
              d="m313 35 38 22v44l-38 22-38-22V57Zm38 22 38-22 38 22v44l-38 22-38-22m76-44 38-22 38 22v44l-38 22-38-22M275 79h-34M503 79h24M389 35V13M313 123v30"
            />
            <path
              d="m284 62 29-17 29 17m55-17 21 13v37m-59 0 30 17m66-67 29 17v33"
              stroke-width="1.2"
            />
          </g>
          <g fill="currentColor" opacity=".75">
            <circle cx="241" cy="79" r="5" />
            <circle cx="527" cy="79" r="5" />
            <circle cx="389" cy="13" r="5" />
            <circle cx="313" cy="153" r="5" />
          </g>
        </svg>`;
  };
  const toolDrawing = function toolDrawing() {
    const surface = toolStyle === 'surface',
      line = toolStyle === 'lines';
    return /* HTML */ `<svg viewBox="0 0 520 310" fill="none" aria-hidden="true">
      <g stroke="currentColor" opacity=".08">
        <path
          d="M50 80h420M50 130h420M50 180h420M50 230h420M110 30v250M210 30v250M310 30v250M410 30v250"
        />
      </g>
      ${surface
        ? '<g fill="currentColor" opacity=".14"><ellipse cx="228" cy="154" rx="140" ry="73" transform="rotate(-18 228 154)"/><ellipse cx="325" cy="133" rx="95" ry="66" transform="rotate(25 325 133)"/><circle cx="151" cy="195" r="44"/></g>'
        : ''}
      <g
        stroke="currentColor"
        stroke-width="${line ? 1.3 : surface ? 3 : 5}"
        stroke-linecap="round"
        opacity="${surface ? 0.4 : 0.7}"
      >
        <path
          d="m114 179 49-61 64 21 39-60 66 31 17 69-57 46-65-31-64 28-49-43Zm49-61 10-49 62-20 31 30m66 31 56-35 42 35-7 64-74 5m-57 46 16 46m-81-77 0-55m-64 83 7 46m253-94 30 23"
        />
        <path d="m127 176 38-44 53 18m80 62 37-34m61-88 25 23" stroke-width="${line ? 1 : 2}" />
      </g>
      ${line
        ? ''
        : /* HTML */ `<g fill="currentColor"
            >${[
              [114, 179],
              [163, 118],
              [227, 139],
              [266, 79],
              [332, 110],
              [349, 179],
              [292, 225],
              [227, 194],
              [163, 222],
              [173, 69],
              [235, 49],
              [388, 75],
              [430, 110],
              [423, 174],
              [308, 271],
              [170, 268],
            ]
              .map(
                ([x, y], i) =>
                  /* HTML */ `<circle
                    cx="${x}"
                    cy="${y}"
                    r="${i % 3 === 0 ? 8 : 5}"
                    opacity="${i % 3 === 0 ? 0.8 : 0.5}"
                  />`,
              )
              .join('')}</g
          >`}
    </svg>`;
  };
  const workflowsPage = function () {
    return (
      heading(
        '工作流',
        '选用已接入流程创建实验，或登记自己的模型与脚本。',
        routeButton('＋ 接入自定义流程', 'newworkflow'),
      ) +
      banner(
        '演示体验：创建实验 → 检查个人／团队候选 → 模拟运行 → 查看产物与来源 → 用指定产物打开工具。',
      ) +
      /* HTML */ `<div class="section-label">
          <span>已接入的演示流程</span><span class="small muted">流程配置与每次实验分开保存</span>
        </div>
        <div class="entry-grid">
          ${Object.entries(workflowInfo)
            .map(
              ([id, w]) =>
                /* HTML */ `<div class="entry-card">
                  <div class="entry-art ${w.color === 'amber' ? 'amber' : ''}">
                    <span class="art-label">${w.custom ? '自定义接入草稿' : '示例流程'}</span
                    >${workflowArt(w.template)}<span class="art-caption"
                      >${w.template === 'protein'
                        ? '序列 → 结构与分析'
                        : w.template === 'molecule'
                          ? '分子 + 靶点 → 对接与排序'
                          : '已登记程序 → 串行科研步骤'}</span
                    >
                  </div>
                  <div class="entry-copy">
                    <div class="entry-title">
                      <h2>${esc(w.name)}</h2>
                      <span class="pill ${w.custom ? 'blue' : 'good'}"
                        >${w.custom ? '仅登记，未真实验证' : '模拟可用'}</span
                      >
                    </div>
                    <p>${esc(w.description)}</p>
                    <div class="entry-tags">
                      ${w.tags.map((t) => /* HTML */ `<span>${esc(t)}</span>`).join('')}
                    </div>
                    <div class="entry-bottom">
                      <span
                        >${w.steps ? w.steps.length : 5} 个步骤 ·
                        ${product.experiments.filter((e) => !e.fixture && e.workflowId === id)
                          .length}
                        次实验</span
                      >${routeButton(
                        product.drafts[id] ? '继续实验草稿' : '创建实验',
                        'workflow',
                        id,
                        true,
                      )}
                    </div>
                    <div class="card-links">
                      ${button('查看流程配置', 'workflow-definition', id)}${product.drafts[id]
                        ? button('另建一次实验', 'new-draft', id)
                        : ''}
                    </div>
                  </div>
                </div>`,
            )
            .join('')}
        </div>
        <div class="section-label"><span>最近实验</span>${routeButton('全部实验记录', 'runs')}</div>
        ${experimentTable(
          product.experiments
            .filter((e) => !e.fixture)
            .slice(-3)
            .reverse(),
        )}`
    );
  };
  const newWorkflowPage = function newWorkflowPage() {
    ensureRegistrationDraft();
    const d = workflowDraft,
      profiles = d.registrations;
    const ai = page.query.get('mode') === 'ai';
    const intro = heading(
      '接入自定义流程',
      '手动整理接入信息，或通过 AI 对话生成步骤与参数。',
      /* HTML */ `<button class="btn" data-nav="workflows">返回列表</button>`,
    ) + /* HTML */ `<div class="registration-mode-switch" role="group" aria-label="接入方式">
      <button type="button" class="btn ${ai ? '' : 'active'}" data-registration-mode="manual" aria-pressed="${!ai}">手动填写</button>
      <button type="button" class="btn ${ai ? 'active' : ''}" data-registration-mode="ai" aria-pressed="${ai}">AI 辅助生成</button>
    </div>`;
    if (ai) return intro + /* HTML */ `<section id="workflow-ai" class="registration-ai" aria-label="AI 辅助生成"><p role="status">正在读取 AI 辅助配置…</p></section>`;
    return (
      intro +
      /* HTML */ `<form id="create-workflow" novalidate>
        <div class="create-layout registration-layout">
          <div class="left-stack">
            <section class="panel">
              <div class="panel-head">
                <div class="panel-title">1. 项目信息</div>
                <span class="pill">登记服务器路径</span>
              </div>
              <div class="create-body">
                <div class="registration-grid">
                  <label class="field"
                    ><span>流程名称 <i>必填</i></span
                    ><input
                      id="workflow-name"
                      aria-label="流程名称"
                      maxlength="40"
                      value="${esc(d.name)}"
                      placeholder="例如：我的蛋白质设计实验" /></label
                  ><label class="field"
                    ><span>流程类型</span
                    ><select id="workflow-template" aria-label="选择模板">
                      <option value="custom" ${d.template === 'custom' ? 'selected' : ''}>
                        自定义流程 · 自己添加步骤
                      </option>
                      <option value="protein" ${d.template === 'protein' ? 'selected' : ''}>
                        蛋白质设计 · 参考步骤
                      </option>
                      <option value="molecule" ${d.template === 'molecule' ? 'selected' : ''}>
                        小分子药物设计 · 参考步骤
                      </option>
                    </select></label
                  ><label class="field registration-wide"
                    ><span>简单介绍 <i>选填</i></span
                    ><textarea
                      id="workflow-description"
                      aria-label="流程介绍"
                      rows="2"
                      maxlength="160"
                      placeholder="这个流程准备完成什么任务？"
                    >
${esc(d.description)}</textarea
                    ></label
                  >${projectField(
                    'projectPath',
                    '项目路径',
                    '/workspace/my-project',
                  )}${projectField(
                    'workflowDoc',
                    '流程说明文件',
                    'README.md 或 docs/workflow.md',
                  )}${projectField(
                    'environment',
                    '运行环境',
                    'conda:my-env 或 Docker 镜像及版本',
                  )}${projectField('inputPath', '输入数据路径', 'data/input.fasta')}<label
                    class="field registration-wide"
                    ><span>完整流程调用指令 <i>选填</i></span
                    ><textarea
                      data-project-field="workflowCommand"
                      aria-label="完整流程调用指令"
                      rows="2"
                      placeholder="已有整套流程脚本时填写，例如：python workflow.py --config config.yaml"
                    >
${esc(d.workflowCommand)}</textarea
                    ><small
                      >已有完整脚本可在这里登记；演示仍按下方步骤模拟，不执行指令。</small
                    ></label
                  >
                </div>
              </div>
            </section>
            <section class="panel">
              <div class="panel-head">
                <div class="panel-title">
                  2. 模型与步骤 <span class="pill">${profiles.length} 步</span>
                </div>
                <button type="button" class="btn" id="fill-registration-demo">填入示例</button>
              </div>
              <div class="registration-intro">
                每一步都要说明“程序在哪里、怎么调用、接收什么、输出什么”。路径可以相对项目目录填写。
              </div>
              <div class="registration-list">
                ${profiles.map((step, i) => registrationCard(step, i, d.template)).join('')}
              </div>
              ${d.template === 'custom'
                ? /* HTML */ `<div class="registration-add">
                    <button
                      type="button"
                      class="btn"
                      id="add-registration"
                      ${profiles.length >= 12 ? 'disabled' : ''}
                    >
                      ＋ 添加模型或步骤</button
                    ><span>按列表顺序连接，最多 12 步</span>
                  </div>`
                : /* HTML */ `<div class="registration-add muted small">
                    参考模板保留原有依赖关系；如需自由增减步骤，请选择“自定义流程”。
                  </div>`}
              <div class="create-body registration-actions">
                <p
                  id="workflow-form-error"
                  class="form-error"
                  role="alert"
                  ${workflowFormError ? '' : 'hidden'}
                >
                  ${esc(workflowFormError)}
                </p>
                <div
                  id="registration-check"
                  class="callout"
                  role="status"
                  ${registrationCheck ? '' : 'hidden'}
                >
                  ${esc(registrationCheck)}
                </div>
                <div class="create-actions">
                  <button type="button" class="btn" id="check-registration">检查必填项</button
                  ><button type="submit" class="btn primary">保存接入草稿 ${icon('arrow')}</button>
                </div>
              </div>
            </section>
          </div>
          <aside class="panel create-preview">
            <div class="panel-head">
              <div class="panel-title">流程预览</div>
              <span class="pill good">${profiles.length} 个步骤</span>
            </div>
            <div class="create-body">
              <div class="preview-name" id="workflow-preview-name">
                ${esc(d.name.trim() || '未命名流程')}
              </div>
              <p class="preview-hint">
                ${d.template === 'custom'
                  ? '自定义顺序'
                  : d.template === 'protein'
                    ? '蛋白质参考流程'
                    : '小分子参考流程'}
              </p>
              <ol class="step-preview">
                ${profiles
                  .map(
                    (step, i) =>
                      /* HTML */ `<li>
                        <span>${i + 1}</span>
                        <div>
                          <b id="preview-stage-name-${i}">${esc(step.name || '未命名步骤')}</b
                          ><small id="preview-stage-status-${i}"
                            >${registrationComplete(step)
                              ? '接入信息已填写'
                              : '等待填写接入信息'}</small
                          >
                        </div>
                      </li>`,
                  )
                  .join('')}
              </ol>
              <div class="callout">
                当前仅登记配置。服务器接入后，仍需检查文件、依赖和输入输出，并完成小样本试运行。
              </div>
              <p class="tool-helper">
                输入和输出使用 <code>{input}</code>、<code>{output}</code>
                占位符。当前不会替换或执行命令。
              </p>
            </div>
          </aside>
        </div>
      </form>` +
      banner(
        '保存后可创建模拟实验。参考步骤继续使用演示输入输出；真实可运行状态需要另外完成接入检查。',
      )
    );
  };
  const newPolicyPage = function newPolicyPage() {
    return (
      heading(
        '新增策略',
        '设置什么时候复用结果，以及保存哪些结果。',
        /* HTML */ `<button class="btn" data-nav="policy">返回策略列表</button>`,
      ) +
      /* HTML */ `<form id="create-policy" novalidate>
        <div class="create-layout">
          <section class="panel">
            <div class="panel-head">
              <div class="panel-title">策略设置</div>
              <span class="pill">自定义</span>
            </div>
            <div class="create-body">
              <label class="field"
                ><span>策略名称 <i>必填</i></span
                ><input
                  id="policy-name"
                  name="name"
                  aria-label="策略名称"
                  maxlength="40"
                  required
                  value="${esc(policyDraft.name)}"
                  placeholder="例如：快速读取，保留近期结果" /></label
              ><label class="field"
                ><span>什么时候复用？</span
                ><select id="policy-reuse" name="reuse" aria-label="复用规则">
                  ${[
                    ['cost', '读取更快时复用'],
                    ['lru', '结果可用就复用'],
                    ['none', '每次重新计算'],
                  ]
                    .map(
                      ([value, label]) =>
                        /* HTML */ `<option
                          value="${value}"
                          ${policyDraft.reuse === value ? 'selected' : ''}
                        >
                          ${label}
                        </option>`,
                    )
                    .join('')}</select
                ><small>复用前都会检查输入和设置是否一致。</small></label
              ><label class="field"
                ><span>怎样保存结果？</span
                ><select id="policy-storage" name="storage" aria-label="保存规则">
                  ${[
                    ['cost', '优先保留重算费时的结果'],
                    ['lru', '优先保留最近使用的结果'],
                    ['none', '不保存新结果'],
                  ]
                    .map(
                      ([value, label]) =>
                        /* HTML */ `<option
                          value="${value}"
                          ${policyDraft.storage === value ? 'selected' : ''}
                        >
                          ${label}
                        </option>`,
                    )
                    .join('')}</select
                ><small>示例空间为 4 GB，固定保留的结果不会被清理。</small></label
              ><label class="field"
                ><span>简单介绍 <i>选填</i></span
                ><textarea
                  id="policy-description"
                  name="description"
                  aria-label="策略介绍"
                  rows="3"
                  maxlength="160"
                  placeholder="适合什么样的任务？"
                >
${esc(policyDraft.description)}</textarea
                >
              </label>
              <p
                id="policy-form-error"
                class="form-error"
                role="alert"
                ${policyFormError ? '' : 'hidden'}
              >
                ${esc(policyFormError)}
              </p>
              <div class="create-actions">
                <button type="button" class="btn" data-nav="policy">取消</button
                ><button type="submit" class="btn primary">保存策略 ${icon('check')}</button>
              </div>
            </div>
          </section>
          <aside class="panel create-preview">
            <div class="panel-head">
              <div class="panel-title">规则预览</div>
              <span class="pill blue">实时更新</span>
            </div>
            <div class="create-body">
              <div class="preview-name" id="policy-preview-name">
                ${esc(policyDraft.name.trim() || '未命名策略')}
              </div>
              <div class="rule-preview">
                <span class="rule-preview-icon">${icon('flow')}</span>
                <div>
                  <small>遇到已有结果</small
                  ><b id="reuse-preview">${reuseLabel(policyDraft.reuse)}</b>
                </div>
              </div>
              <div class="rule-preview">
                <span class="rule-preview-icon">${icon('data')}</span>
                <div>
                  <small>生成新结果</small
                  ><b id="storage-preview">${storageLabel(policyDraft.storage)}</b>
                </div>
              </div>
              <div class="callout">保存后，回到列表点击“应用此策略”，就能查看预计用时的变化。</div>
            </div>
          </aside>
        </div>
      </form>`
    );
  };
  const flowRibbon = function flowRibbon(stage) {
    return /* HTML */ `<div class="journey">
      ${['创建实验', '检查共享候选', '确认并模拟运行', '结果与工具']
        .map(
          (s, i) =>
            /* HTML */ `<span class="${i === stage ? 'current' : ''}"><b>${i + 1}</b>${s}</span>`,
        )
        .join('')}
    </div>`;
  };
  const inputPanel = function inputPanel(d) {
    const w = workflowInfo[activeWorkflow],
      sources = product.catalog.filter((a) => usable(a) && accepts(w, a));
    let input = choiceField('输入来源', 'inputSource', d.inputSource, [
      ['sample', '使用内置示例'],
      ['artifact', '选择已有产物'],
      ['path', '登记数据位置'],
      ['upload', '选择本地文件'],
    ]);
    if (d.inputSource === 'sample')
      input += choiceField(
        '示例输入',
        'config.input',
        d.config.input,
        w.template === 'protein'
          ? [
              ['seq-a', 'candidate_A.fasta · 256 aa（示例）'],
              ['seq-b', 'candidate_B.fasta · 310 aa（示例）'],
            ]
          : w.template === 'molecule'
            ? [
                ['fragment-a', 'fragment_A.smi · 24 个分子（示例）'],
                ['fragment-b', 'fragment_B.smi · 36 个分子（示例）'],
              ]
            : [['demo-input.json', 'demo-input.json（示例）']],
      );
    if (d.inputSource === 'artifact')
      input += choiceField(
        '可作为输入的产物',
        'inputArtifactId',
        d.inputArtifactId,
        [
          ['', '请选择兼容且可读取的产物'],
          ...sources.map((a) => [a.id, a.name + ' · ' + a.ownerName + ' · ' + a.id]),
        ],
        `此流程接受：${inputKinds(w).join(' / ')}。显示个人及团队可用产物。`,
      );
    if (d.inputSource === 'path')
      input += field(
        '输入数据位置',
        'config.input',
        d.config.input,
        'text',
        '仅登记路径；本演示不读取服务器文件。',
      );
    if (d.inputSource === 'upload')
      input += /* HTML */ `<label class="field"
        ><span>本地文件（不上传）</span><input type="file" id="experiment-file" />
        <div class="field-hint">
          最多 2 MB；仅保存名称、类型和演示内容标识，不保存文件正文。
        </div></label
      >`;
    if (d.inputMeta)
      input += /* HTML */ `<div class="callout">
        ${esc(d.inputMeta.name)} · ${esc(d.inputMeta.kind)} · ${esc(d.inputMeta.sizeLabel || '')}<br />${esc(
          d.inputMeta.note || '',
        )}
      </div>`;
    return input;
  };
  const candidateDecision = function candidateDecision(s, d) {
    const ready = s.candidates.filter((a) => a.match && usable(a)),
      waiting = s.candidates.filter((a) => a.match && a.status === 'running' && a.accessible);
    const choice = d.choices[s.id] || 'auto';
    return /* HTML */ `<select data-choice="${s.id}" aria-label="${esc(s.name)}的执行方式">
      <option value="auto" ${choice === 'auto' ? 'selected' : ''}>自动建议</option>
      <option value="compute" ${choice === 'compute' ? 'selected' : ''}>重新计算</option>
      ${ready
        .map(
          (a) =>
            /* HTML */ `<option
              value="reuse:${a.id}"
              ${choice === 'reuse:' + a.id ? 'selected' : ''}
            >
              复用 ${esc(a.ownerName)} · ${a.id}
            </option>`,
        )
        .join('')}${waiting
        .map(
          (a) =>
            /* HTML */ `<option value="wait:${a.id}" ${choice === 'wait:' + a.id ? 'selected' : ''}>
              等待 ${esc(a.ownerName)} · ${a.id}
            </option>`,
        )
        .join('')}
    </select>`;
  };
  const candidateRows = function candidateRows(s, from = '') {
    return s.candidates.length
      ? s.candidates
          .map(
            (a) =>
              /* HTML */ `<div class="candidate-row">
                <div>
                  <b>${esc(a.ownerName)}</b> · ${esc(a.name)}
                  <div class="reason">
                    ${esc(a.id)} · ${esc(a.runId)} · ${a.scope === 'team' ? '团队共享' : '仅自己'}
                  </div>
                </div>
                <div>
                  <span class="pill ${a.match && usable(a) ? 'good' : a.match ? 'warn' : ''}"
                    >${!a.match
                      ? '生成条件不同'
                      : a.status === 'running'
                        ? '正在生成'
                        : !readable(a)
                          ? '文件不可读取'
                          : '匹配且可读取'}</span
                  ><button class="btn" data-candidate-detail="${a.id}" data-from="${esc(from)}">来源</button>
                </div>
              </div>`,
          )
          .join('')
      : '<div class="muted small">该范围内没有候选。</div>';
  };
  const stepParameterField = function stepParameterField(definition, d, readOnly) {
    const value = d.config[definition.key],
      name = `config.${definition.key}`;
    if (readOnly)
      return /* HTML */ `<div class="kv"><span>${esc(definition.label)}</span><strong>${esc(value)}</strong></div>`;
    if (definition.type === 'select')
      return choiceField(definition.label, name, value, definition.options || []);
    return /* HTML */ `<label class="field">
      <span>${esc(definition.label)}</span>
      <input data-draft="${esc(name)}" type="${esc(definition.type || 'text')}"
        value="${esc(value)}" ${Number.isFinite(definition.min) ? `min="${definition.min}"` : ''}
        ${Number.isFinite(definition.max) ? `max="${definition.max}"` : ''}
        ${definition.step ? `step="${definition.step}"` : ''} />
    </label>`;
  };
  const nodeDetailPanel = function nodeDetailPanel(step, d, planStep = null, experiment = null) {
    const definition = experiment?.workflowSnapshot || workflowInfo[activeWorkflow],
      snapshotSteps = experiment?.workflowSnapshot.steps || steps,
      profile = definition.executionDefinition?.steps.find((item) => item.id === step.id),
      dependencies = step.deps.map((id) => snapshotSteps.find((item) => item.id === id)?.name || id),
      input = dependencies.length ? dependencies.join('、') : d.inputMeta?.name || d.config.input || '未选择',
      output = step.file ? `${step.file} · ${step.kind || '文件'}` : '未定义',
      definitions = (step.parameters || []).map((definition) => stepParameterField(definition, d, !!experiment)).join(''),
      result = experiment?.outputs.find((item) => item.stepId === step.id),
      artifact = result && artifactById(result.artifactId);
    return panel(
      `节点详情 · ${esc(step.name)}`,
      /* HTML */ `<div id="node-details" class="detail-body node-detail-body" tabindex="-1" role="region" aria-label="${esc(step.name)}节点详情">
        <div class="node-detail-toolbar"><button type="button" class="link-btn" data-close-node-detail>关闭节点详情 ×</button></div>
        <div class="node-io-grid">
          <div><span>输入</span><strong>${esc(input)}</strong></div>
          <div><span>输出</span><strong>${esc(output)}</strong></div>
        </div>
        ${definitions
          ? `<div class="node-parameter-fields">${definitions}</div>`
          : '<p class="muted small">此节点没有单独登记的可调参数。</p>'}
        <details class="node-description">
          <summary>步骤说明与依赖</summary>
          <p>${esc(step.description || '此节点按已登记工作流定义执行。')}</p>
          <p class="muted small">依赖：${esc(dependencies.join('、') || '实验输入')}</p>
          ${planStep?.key ? `<p class="muted small">本次结果身份</p><p class="mono source-key">${esc(planStep.key)}</p>` : ''}
        </details>
        ${profile ? `<details class="node-description"><summary>已登记的调用与版本</summary>
          <div class="kv"><span>版本</span><strong>${esc(profile.version)}</strong></div>
          <div class="kv"><span>程序路径</span><strong>${esc(profile.modelPath)}</strong></div>
          <div class="kv"><span>登记输入</span><strong>${esc(profile.input)}</strong></div>
          <div class="kv"><span>登记输出</span><strong>${esc(profile.output)}</strong></div>
          <pre class="log">${esc(profile.command)}</pre>
        </details>` : ''}
        ${planStep
          ? `<div class="node-reuse-summary">
              <div class="kv"><span>本次计划</span><strong>${planStep.action === 'reuse' ? '复用已有结果' : planStep.action === 'wait' ? '等待共享结果' : '重新计算'}</strong></div>
              <p class="callout">${esc(planStep.reason)}</p>
              ${!experiment || experiment.status === 'ready'
                ? `<label class="field"><span>执行方式</span>${candidateDecision(planStep, d)}</label>`
                : ''}
              <div class="kv"><span>预计读取 / 重新计算</span><strong>${fmt(planStep.load)} / ${fmt(planStep.cost)}</strong></div>
              <details class="node-candidates">
                <summary>查看候选结果（${planStep.candidates.length}）</summary>
                ${candidateRows(planStep, experiment?.id || '')}
              </details>
            </div>`
          : ''}
        ${artifact
          ? `<div class="node-output-link"><span class="pill ${result.mode === 'compute' ? 'blue' : 'good'}">${result.mode === 'compute' ? '本次生成' : result.mode === 'wait' ? '等待后复用' : '复用已有结果'}</span>
              <button class="link-btn" data-artifact-detail="${artifact.id}" data-from="${experiment.id}">查看产物 ${esc(artifact.id)}</button>
              <span class="tiny muted">${esc(artifact.ownerName)} · ${readable(artifact) ? '模拟文件可读取' : '仅保留来源记录／文件不可读取'}</span></div>`
          : ''}
      </div>`,
    );
  };
  // live-panel's light-pastel visual grammar. Preview/replay motion illustrates
  // dependencies; execution highlights remain driven by simulation events.
  const flowStepState = function flowStepState(e, step, index) {
    if (!e) return 'planned';
    if (e.outputs.some((out) => out.stepId === step.id)) return 'complete';
    if (e.status === 'failed' && (e.failedStep === step.id ||
        (!e.failedStep && e.currentStep === index))) return 'failed';
    if (!e.fixture && ['running', 'waiting'].includes(e.status) && e.currentStep === index)
      return e.status === 'waiting' ? 'waiting' : 'active';
    if (['cancelled', 'interrupted', 'failed'].includes(e.status)) return 'stopped';
    return 'pending';
  };
  const flowLayout = function flowLayout(p) {
    const byId = new Map(p.map((step) => [step.id, step]));
    const ranks = new Map();
    const rank = (step) => {
      if (ranks.has(step.id)) return ranks.get(step.id);
      const deps = (step.deps || []).filter((id) => byId.has(id));
      const value = deps.length ? 1 + Math.max(...deps.map((id) => rank(byId.get(id)))) : 0;
      ranks.set(step.id, value);
      return value;
    };
    p.forEach(rank);
    const columns = Math.max(0, ...ranks.values()) + 1;
    const groups = Array.from({ length: columns }, (_, i) => p.filter((s) => ranks.get(s.id) === i));
    const rows = Math.max(1, ...groups.map((g) => g.length));
    const height = rows * 212 + (rows - 1) * 24 + 32;
    const positions = new Map();
    groups.forEach((group, col) => group.forEach((step, row) => {
      positions.set(step.id, { x: 16 + col * 224, y: (height - group.length * 212 - (group.length - 1) * 24) / 2 + row * 236 });
    }));
    return { width: Math.max(224, columns * 224 - 16), height, positions };
  };
  const liveFlow = function liveFlow(p, selectedId, e = null) {
    if (!p.length) return '<div class="empty">当前流程没有步骤。</div>';
    const { width, height, positions } = flowLayout(p);
    const view = !e || e.status === 'ready' ? 'preview' :
      e.status === 'completed' ? 'replay' :
      ['failed', 'cancelled', 'interrupted'].includes(e.status) ? 'stopped' : 'execution';
    const labels = { planned: '待确认', pending: e?.status === 'ready' ? '等待启动' : '尚未执行', active: '正在模拟', waiting: '等待共享结果', complete: '已完成', failed: '模拟失败', stopped: '未执行 · 已停止' };
    const byId = new Map(p.map((step, i) => [step.id, { step, state: flowStepState(e, step, i) }]));
    const wires = p.flatMap((step) => (step.deps || []).filter((id) => positions.has(id)).map((id) => {
      const from = positions.get(id), to = positions.get(step.id);
      const start = from.x + 176, end = to.x - 7, middle = (start + end) / 2;
      const path = `M${start} ${from.y + 106}H${middle}V${to.y + 106}H${end}`;
      const state = byId.get(step.id).state;
      const sourceDone = byId.get(id).state === 'complete';
      const wireState = sourceDone && state === 'active' ? 'active' : sourceDone && state === 'complete' ? 'complete' : 'pending';
      const moving = view === 'preview' || wireState === 'active' ||
        (view === 'replay' && wireState === 'complete');
      return `<g class="flow-wire ${wireState}${moving ? ' flowing' : ''}" data-flow-from="${esc(id)}" data-flow-to="${esc(step.id)}">
        <path class="flow-wire-path" d="${path}" />
        <path class="flow-arrow" d="M${end - 5} ${to.y + 102}l5 4-5 4" />
        ${moving ? `<circle class="flow-packet" r="4"><animateMotion dur="${view === 'execution' ? '.55s' : '1.6s'}" repeatCount="indefinite" path="${path}" /></circle>` : ''}
        <title>${esc(byId.get(id).step.name)} → ${esc(step.name)} · ${esc(byId.get(id).step.kind || '数据')}</title>
      </g>`;
    })).join('');
    const nodes = p.map((s, i) => {
      const pos = positions.get(s.id), state = byId.get(s.id).state;
      const out = e?.outputs.find((o) => o.stepId === s.id), a = out && artifactById(out.artifactId);
      const action = (out?.mode || s.action) === 'reuse' ? '复用已有结果' : (out?.mode || s.action) === 'wait' ? '等待后复用' : '本次生成';
      const incoming = (s.deps || []).map((id) => byId.get(id)?.step.kind || '数据').join(' + ') || '实验输入';
      return `<div class="flow-stage tone-${i % 4} ${state} ${selectedId === s.id ? 'selected' : ''}" style="left:${pos.x / width * 100}%;top:${pos.y}px;width:${176 / width * 100}%;--flow-delay:${-i * .37}s" data-flow-state="${state}" data-flow-step="${esc(s.id)}">
        <div class="flow-stage-head"><span>STEP ${String(i + 1).padStart(2, '0')}</span><span>${e ? labels[state] : s.action === 'reuse' ? '复用' : s.action === 'wait' ? '等待后复用' : '重新计算'}</span></div>
        <button type="button" class="flow-card" data-plan-step="${esc(s.id)}" aria-pressed="${selectedId === s.id}" ${state === 'active' || state === 'waiting' ? 'aria-current="step"' : ''} aria-label="查看${esc(s.name)} · ${e ? labels[state] : '参数与计划'}">
          <span class="flow-card-heading"><span class="flow-icon">${icon(s.icon)}</span><strong>${esc(s.name)}</strong></span>
          <span class="flow-file" title="${esc(a?.name || s.file || '待生成产物')}">${esc(a?.name || s.file || '待生成产物')}</span>
          <span class="flow-state"><i aria-hidden="true"></i>${e ? state === 'complete' ? action : labels[state] : fmt(s.time || 0) + ' · 预计用时'}</span>
          <span class="flow-formats" title="${esc(incoming)} → ${esc(s.kind || '产物')}">${esc(incoming)} <span aria-hidden="true">→</span> ${esc(s.kind || '产物')}</span>
        </button>
        <div class="flow-stage-foot">${a ? `<button type="button" class="link-btn" data-artifact-detail="${esc(a.id)}" data-from="${esc(e.id)}">产物详情 ↗</button>${isViewable(a) ? `<button type="button" class="link-btn" data-view-artifact="${esc(a.id)}" data-from="${esc(e.id)}">结构工具 ↗</button>` : `<span title="${esc(a.ownerName)}">${esc(a.id)}</span>`}` : `<span>${e ? '点击节点查看输入与配置' : '点击节点查看参数与候选'}</span>`}</div>
      </div>`;
    }).join('');
    const current = p.find((step, i) => ['active', 'waiting', 'failed'].includes(flowStepState(e, step, i)));
    const summary = !e ? '配置预览' : e.status === 'completed' ? '模拟已完成' : e.status === 'ready' ? '等待启动' : e.status === 'failed' ? '模拟失败' : e.status === 'cancelled' ? '模拟已取消' : e.status === 'interrupted' ? '模拟已中断' : e.fixture ? '历史示例' : '模拟运行中';
    const motionNote = view === 'preview' ? '动效为流程示意，尚未执行' :
      view === 'replay' ? '已完成 · 连线动效为数据流向回放' : '数据流与节点随模拟状态更新';
    return `<div class="live-flow ${e ? 'execution-flow' : 'plan-flow'} flow-motion-${flowMotionEnabled ? 'on' : 'off'}" data-flow-view="${view}">
      <div class="flow-toolbar"><div><span class="flow-live-label ${e && ['running', 'waiting'].includes(e.status) && !e.fixture ? 'on' : ''}"><i aria-hidden="true"></i>${summary}</span><span class="flow-toolbar-caption">${current ? '当前步骤 · ' + esc(current.name) : `${p.length} 个步骤 · ${e ? e.outputs.length + ' 个已有产物' : '输入 → 处理 → 结果'}`}</span></div><button type="button" class="link-btn flow-motion-toggle" data-flow-motion-toggle aria-pressed="${flowMotionEnabled}" aria-label="${flowMotionEnabled ? '暂停流程图动效' : '播放流程图动效'}">${flowMotionEnabled ? 'Ⅱ 暂停动效' : '▷ 播放动效'}</button></div>
      <div class="flow-scroll" tabindex="0" role="region" aria-label="${e ? '本次运行数据流程' : '工作流依赖图'}，可横向滚动">
        <div class="flow-canvas" style="min-width:${Math.max(224, Math.round(width * .85))}px;height:${height}px">
          <svg class="flow-wires" width="100%" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">${wires}</svg>${nodes}
        </div>
      </div>
      <div class="flow-legend">
        ${e ? '<span><i class="legend-complete"></i>已完成</span><span><i class="legend-active"></i>当前步骤</span><span><i class="legend-waiting"></i>等待共享</span><span><i class="legend-pending"></i>待执行</span><span><i class="legend-failed"></i>失败 / 停止</span>' : '<span>输入格式 → 输出格式</span><span>节点标记本次复用或计算计划</span>'}
        <span class="flow-legend-note">${motionNote}</span>
      </div>
    </div>`;
  };
  const experimentDiagram = function experimentDiagram(p, selectedId = '') {
    return panel('工作流', liveFlow(p, selectedId));
  };
  const workflowPage = function () {
    const d = currentDraft() || createExperimentDraft(activeWorkflow);
    const p = plan(d.config, d.policy, d),
      metrics = planMetrics(p),
      selected = steps.find((step) => step.id === selectedPlanStep);
    selectedPlanStep = selected?.id || '';
    return (
      heading(
        '创建实验',
        '配置本次输入和节点参数，创建后在实验详情中检查候选并运行。',
        `${routeButton('我的实验', 'runs')}${button('创建实验', 'create-experiment', '', true)}`,
      ) +
      flowRibbon(0) +
      /* HTML */ `<div class="workspace-grid experiment-create-grid">
          <div class="left-stack">
            ${panel(
              '实验信息与输入',
              /* HTML */ `<div class="create-body">
                <div class="registration-grid">
                  ${field('实验名称', 'name', d.name)}<label class="field"
                    ><span>所用流程</span
                    ><input readonly value="${esc(workflowInfo[activeWorkflow].name)}" /></label
                  >${inputPanel(d)}
                </div>
              </div>`,
            )}${experimentDiagram(p, selected?.id || '')}
            ${selected ? nodeDetailPanel(selected, d, p.find((item) => item.id === selected.id)) : ''}
          </div>
          <aside class="right-stack">
            ${panel(
              '实验范围与策略',
              /* HTML */ `<div class="detail-body">
                <details class="settings-disclosure">
                  <summary>共享与运行选项</summary>
                  <div class="settings-disclosure-body">
                    ${choiceField('本次实验意图', 'intent', d.intent, [
                      ['replay', '复现实验 · 查找等价历史结果'],
                      ['fresh', '生成新样本 · 不替代为旧样本'],
                    ])}
                    ${choiceField('复用查找范围', 'reuseScope', d.reuseScope, [
                      ['team', '我的产物 + 团队共享'],
                      ['mine', '仅我的产物'],
                    ])}
                    ${choiceField('新产物共享范围', 'shareOutput', d.shareOutput, [
                      ['team', '团队共享（模拟）'],
                      ['private', '仅自己（模拟）'],
                    ])}
                    ${choiceField('复用与保存策略', 'policy', d.policy, allPolicies().map((item) => [item.id, item.name]))}
                    ${choiceField('模拟读取位置', 'config.remote', String(!!d.config.remote), [
                      ['false', '本地读取（示例）'],
                      ['true', '远端读取较慢（示例）'],
                    ])}
                    ${!steps.some((step) => step.parameters?.some((param) => param.key === 'seed'))
                      ? field('随机种子', 'config.seed', d.config.seed, 'number') : ''}
                    ${choiceField('模拟结果', 'simulation', d.simulation, [
                      ['success', '正常完成'],
                      ['fail', '在后续步骤模拟失败'],
                    ])}
                  </div>
                </details>
                <details class="settings-disclosure">
                  <summary>计划摘要与导出</summary>
                  <div class="settings-disclosure-body">
                    <div class="kv"><span>预计总用时</span><strong>${fmt(metrics.total)}</strong></div>
                    <div class="kv"><span>复用 / 等待 / 重算</span><strong>${metrics.reuse} / ${metrics.wait} / ${p.length - metrics.reuse - metrics.wait}</strong></div>
                    ${button('导出本次计划', 'export-plan')}
                  </div>
                </details>
                <p class="field-hint">参数仅保存为本次实验快照；共享范围、候选文件和运行耗时均为演示数据。</p>
                <div class="create-page-action">${button('创建实验', 'create-experiment', '', true)}</div>
              </div>`,
            )}
          </aside>
        </div>`
    );
  };
  const experimentTable = function experimentTable(list) {
    return !list.length
      ? /* HTML */ `<div class="panel empty">
          还没有实验。${routeButton('选择流程创建实验', 'workflows')}
        </div>`
      : /* HTML */ `<div class="panel table-scroller">
          <table class="decision-table">
            <thead>
              <tr>
                <th>实验 / 流程</th>
                <th>创建时间</th>
                <th>状态</th>
                <th>已产生结果</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              ${list
                .map(
                  (e) =>
                    /* HTML */ `<tr>
                      <td>
                        <b>${esc(e.name)}</b>
                        <div class="reason">
                          ${esc(e.id)} · ${esc(e.workflowSnapshot.name)} · ${esc(e.ownerName)}
                        </div>
                      </td>
                      <td>${dateText(e.createdAt)}</td>
                      <td>${statusBadge(e.status)}</td>
                      <td>${e.outputs.length} / ${e.workflowSnapshot.steps.length}</td>
                      <td>${routeButton('实验详情', 'experiment', e.id)}</td>
                    </tr>`,
                )
                .join('')}
            </tbody>
          </table>
        </div>`;
  };
  const runsPage = function () {
    const list = product.experiments
      .filter((e) =>
        experimentScope === 'team'
          ? e.ownerId !== 'me'
          : e.ownerId === 'me' && !e.fixture,
      )
      .slice()
      .reverse();
    return (
      heading(
        '实验记录',
        '每次实验的输入、计划、产物和来源均可回看。',
        routeButton('创建实验', 'workflow', activeWorkflow, true),
      ) +
      /* HTML */ `<div class="data-toolbar scope-switch" role="group" aria-label="实验范围">
        <button type="button" class="btn ${experimentScope === 'mine' ? 'active' : ''}" data-action="experiment-scope" data-value="mine" aria-pressed="${experimentScope === 'mine'}">我的实验</button>
        <button type="button" class="btn ${experimentScope === 'team' ? 'active' : ''}" data-action="experiment-scope" data-value="team" aria-pressed="${experimentScope === 'team'}">团队示例</button>
      </div>` +
      experimentTable(list)
    );
  };
  const experimentOutputDetails = function experimentOutputDetails(e) {
    return `<details class="output-disclosure">
      <summary>产物清单与可读状态（${e.outputs.length}）</summary>
      <div class="result-list">${e.outputs.length ? e.outputs.map((out) => {
        const a = artifactById(out.artifactId),
          step = e.workflowSnapshot.steps.find((item) => item.id === out.stepId);
        return `<div class="result-row"><div class="result-meta">
          <b>${esc(step?.name || out.stepId)}</b>
          <div class="reason">${esc(a ? `${a.name} · ${a.ownerName} · ${a.id}` : out.artifactId + ' · 产物记录不可用')}</div>
          <span class="pill ${out.mode === 'compute' ? 'blue' : 'good'}">${out.mode === 'compute' ? '本次生成' : out.mode === 'wait' ? '等待后复用' : '复用已有结果'}</span>
          <span class="tiny muted">${readable(a) ? '模拟文件可读取' : '仅保留来源记录／文件不可读取'}</span>
        </div><div class="row-actions">${a ? `<button class="btn" data-artifact-detail="${esc(a.id)}" data-from="${esc(e.id)}">产物详情</button>${isViewable(a) ? `<button class="btn" data-view-artifact="${esc(a.id)}" data-from="${esc(e.id)}">打开结构工具</button>` : ''}` : ''}</div></div>`;
      }).join('') : '<div class="empty">尚未产生产物，启动后可在流程图中查看当前步骤。</div>'}</div>
    </details>`;
  };
  const experimentFlowPanel = function experimentFlowPanel(e, p, selectedId) {
    const requestedView = page.query.get('view'),
      results = requestedView === 'results' || (requestedView !== 'config' && e.status !== 'ready'),
      done = e.outputs.length,
      total = e.workflowSnapshot.steps.length,
      percent = total ? Math.round(done / total * 100) : 0,
      graphSteps = e.workflowSnapshot.steps.map((step) => ({
        ...step, ...p.find((item) => item.id === step.id), deps: step.deps,
      }));
    const viewSwitch = `<div class="experiment-view-switch" role="group" aria-label="流程图视图">
      <button type="button" class="btn ${results ? '' : 'active'}" data-action="experiment-flow-view" data-value="config" aria-pressed="${!results}">配置视图</button>
      <button type="button" class="btn ${results ? 'active' : ''}" data-action="experiment-flow-view" data-value="results" aria-pressed="${results}">运行与结果</button>
    </div>`;
    return `<div id="experiment-flow-view" tabindex="-1" data-experiment-view="${results ? 'results' : 'config'}">${panel(
      results ? '运行进度与产物' : '工作流配置',
      `${results ? `<div class="run-progress">
        <div class="progress-top"><span>${done} / ${total} 个步骤已产生产物</span><span>${e.status === 'ready' ? '等待启动' : e.status === 'completed' ? '模拟已完成' : percent + '%'}</span></div>
        <div class="progress-track" role="progressbar" aria-label="已产生产物的步骤" aria-valuemin="0" aria-valuemax="${total}" aria-valuenow="${done}"><div class="progress-fill" style="width:${percent}%"></div></div>
      </div>` : ''}
      ${liveFlow(graphSteps, selectedId, results ? e : null)}
      <div class="experiment-flow-actions">
        <span class="muted small">${results ? e.status === 'ready' ? '确认候选后启动，查看当前步骤与数据流。' : '节点状态、产物和日志随本次模拟更新。' : '点击节点检查参数、候选与复用原因，然后进入运行与结果。'}</span>
        ${results ? e.status === 'ready' ? button('确认候选并开始模拟', 'start', e.id, true) : '' : button('查看运行与结果 →', 'experiment-flow-view', 'results', true)}
      </div>
      ${results ? experimentOutputDetails(e) : ''}`,
      viewSwitch,
    )}</div>`;
  };
  const experimentPage = function experimentPage(e) {
    if (!e) return missingPage('找不到这次实验');
    const live = ['running', 'waiting'].includes(e.status) && !e.fixture,
      p = e.plan.length
        ? e.plan
        : e.workflowSnapshot.steps.map((step) => ({ ...step, action: 'compute', time: step.cost || 0 })),
      selected =
        e.workflowSnapshot.steps.find((step) => step.id === selectedPlanStep),
      selectedPlan = !e.fixture && p.find((step) => step.id === selected?.id);
    selectedPlanStep = selected?.id || '';
    return (
      heading(
        e.name,
        '实验快照 · ' + e.id + ' · ' + e.workflowSnapshot.name,
        `${routeButton('我的实验', 'runs')}${button('复制配置创建实验', 'clone-experiment', e.id)}${live ? button('取消本次模拟', 'cancel', e.id) : ''}`,
      ) +
      flowRibbon(e.status === 'ready' ? 1 : live ? 2 : 3) +
      banner(
        `${statusBadge(e.status)} <span style="margin-left:10px">${e.fixture ? '预置示例仅用于共享候选，不计入我的实验。' : e.status === 'ready' ? '配置已保存；确认候选后可启动模拟。' : '所有步骤仅模拟执行，日志中的科学产物与用时为示例。'}</span>`,
      ) +
      /* HTML */ `<div class="workspace-grid">
        <div class="left-stack">
          ${experimentFlowPanel(e, p, selected?.id || '')}
          ${selected ? nodeDetailPanel(selected, e, selectedPlan, e) : ''}
          ${panel(
            '运行日志',
            /* HTML */ `<div class="detail-body">
              <div class="log">${e.log.map(esc).join('\n')}</div>
            </div>`,
          )}
        </div>
        <aside class="right-stack">
          ${panel(
            '输入与配置快照',
            /* HTML */ `<div class="detail-body">
              <div class="kv">
                <span>实验意图</span
                ><strong>${e.intent === 'fresh' ? '生成新样本' : '复现实验'}</strong>
              </div>
              <div class="kv">
                <span>输入来源</span
                ><strong
                  >${esc(
                    {
                      sample: '内置示例',
                      artifact: '已有产物',
                      path: '登记位置',
                      upload: '本地文件信息',
                    }[e.inputSource] || '示例',
                  )}</strong
                >
              </div>
              <div class="kv">
                <span>输入标识</span><strong>${esc(e.inputMeta?.name || e.config.input)}</strong>
              </div>
              ${e.inputArtifactId
                ? /* HTML */ `<button
                    class="link-btn"
                    data-artifact-detail="${esc(e.inputArtifactId)}"
                    data-from="${e.id}"
                  >
                    查看输入产物来源
                  </button>`
                : ''}
              <div class="kv">
                <span>复用范围</span
                ><strong>${e.reuseScope === 'team' ? '个人 + 团队共享' : '仅个人'}</strong>
              </div>
              <div class="kv">
                <span>新产物共享</span
                ><strong>${e.shareOutput === 'team' ? '团队共享' : '仅自己'}</strong>
              </div>
              <details class="snapshot-json">
                <summary>查看完整参数 JSON</summary>
                <pre class="log">${esc(JSON.stringify(e.config, null, 2))}</pre>
              </details>
            </div>`,
          )}${panel(
            '计划与保存',
            /* HTML */ `<div class="detail-body">
              <div class="kv"><span>步骤</span><strong>${p.length}</strong></div>
              <div class="kv"><span>复用 / 等待 / 重算</span><strong>${e.metrics.reuse || 0} / ${e.metrics.wait || 0} / ${Math.max(0, p.length - (e.metrics.reuse || 0) - (e.metrics.wait || 0))}</strong></div>
              <div class="kv"><span>策略</span><strong>${esc(e.policyRules.name)}</strong></div>
              <div class="kv">
                <span>计划总用时</span><strong>${fmt(e.metrics.total)}（估算）</strong>
              </div>
              <div class="kv">
                <span>已保存 / 未保留</span
                ><strong>${e.storage.saved} / ${e.storage.skipped}</strong>
              </div>
              <div class="callout">
                估算用时不代表实际墙钟时间。中断或失败的实验未完成整个计划。
              </div>
              ${button('导出实验快照', 'export-experiment', e.id)}
            </div>`,
          )}
        </aside>
      </div>`
    );
  };
  const isViewable = function isViewable(a) {
    return usable(a) && ['mmCIF', 'PDB', 'SDF', 'PDBQT'].includes(a.kind);
  };
  const compatibleWorkflows = function compatibleWorkflows(a) {
    return Object.entries(workflowInfo).filter(([, w]) => accepts(w, a));
  };
  const artifactPage = function artifactPage(a) {
    if (!a || !visible(a)) return missingPage('找不到可访问的产物');
    const from = page.query.get('from') || '',
      fromDraft = page.query.get('draft') || '',
      origin = experimentById(a.runId);
    const inputTargets = compatibleWorkflows(a);
    return (
      heading(
        a.name,
        '产物详情 · ' + a.id,
        `${fromDraft ? routeButton('返回实验草稿', 'workflow', fromDraft) : from ? routeButton('返回实验', 'experiment', from) : routeButton('返回数据目录', 'catalog')}${isViewable(a) ? /* HTML */ `<button class="btn primary" data-view-artifact="${a.id}" data-from="${esc(from)}">用此产物打开工具</button>` : ''}`,
      ) +
      banner('这是模拟产物的元数据与来源；没有生成真实科学文件。') +
      /* HTML */ `<div class="workspace-grid">
        <div class="left-stack">
          ${panel(
            '身份、来源与有效性',
            /* HTML */ `<div class="detail-body">
              <div class="kv">
                <span>可复用身份</span><strong class="mono">${esc(a.key)}</strong>
              </div>
              <div class="kv">
                <span>生成者 / 共享范围</span
                ><strong
                  >${esc(a.ownerName)} / ${a.scope === 'team' ? '团队共享' : '仅自己'}</strong
                >
              </div>
              <div class="kv"><span>生成流程</span><strong>${esc(a.workflowName)}</strong></div>
              <div class="kv">
                <span>生成实验</span
                ><strong
                  >${origin ? routeButton(a.runId, 'experiment', a.runId) : esc(a.runId)}</strong
                >
              </div>
              <div class="kv">
                <span>文件状态</span
                ><strong
                  >${statusBadge(a.status)} ${a.retained === false ? '未保留模拟文件' : ''}</strong
                >
              </div>
              <div class="kv">
                <span>格式 / 模拟大小</span><strong>${esc(a.kind)} / ${gb(a.size)}</strong>
              </div>
              <div class="kv"><span>版本记录</span><strong>${esc(a.version)}</strong></div>
              <div class="kv">
                <span>演示位置</span
                ><strong class="mono">demo://${esc(a.id)}/${esc(a.name)}</strong>
              </div>
              <h3 class="detail-title">上游依赖</h3>
              ${a.deps.length
                ? a.deps
                    .map((key, index) => {
                      const parent =
                        artifactById(a.parentArtifactIds?.[index]) ||
                        product.catalog.find((p) => p.key === key && p.runId === a.runId) ||
                        product.catalog.find((p) => p.key === key && visible(p));
                      return /* HTML */ `<div class="kv">
                        <span class="mono">${esc(key)}</span>${parent
                          ? routeButton(parent.name, 'artifact', parent.id)
                          : '<strong>仅保留身份记录</strong>'}
                      </div>`;
                    })
                    .join('')
                : '<div class="muted small">外部输入：' +
                  esc(a.config.input) +
                  '</div>' +
                  (a.inputArtifactId
                    ? routeButton('查看输入产物', 'artifact', a.inputArtifactId)
                    : '')}
              <h3 class="detail-title">生成配置快照</h3>
              <div class="log">${esc(JSON.stringify(a.config, null, 2))}</div>
            </div>`,
          )}
        </div>
        <aside class="right-stack">
          ${panel(
            '继续使用此产物',
            /* HTML */ `<div class="detail-body">
              <p class="small muted">下载的是带有模拟标记的 JSON 说明，不是真实结构或序列文件。</p>
              ${button('下载模拟产物说明', 'download-artifact', a.id)}
              <hr class="soft-rule" />
              <label class="field"
                ><span>作为新实验输入</span
                ><select id="input-target" ${inputTargets.length ? '' : 'disabled'}>
                  ${inputTargets
                    .map(
                      ([id, w]) => /* HTML */ `<option value="${esc(id)}">${esc(w.name)}</option>`,
                    )
                    .join('') || '<option>当前没有接受此格式的流程</option>'}
                </select></label
              >${button(
                '使用此输入创建实验',
                'use-input',
                a.id,
                true,
                !usable(a) || !inputTargets.length,
              )}
              <div class="field-hint">
                仅提供输入格式兼容的流程，避免把结构文件直接送入序列处理。
              </div>
            </div>`,
          )}${own(a)
            ? panel(
                '共享与保留',
                /* HTML */ `<div class="detail-body">
                  <div class="kv">
                    <span>共享范围</span
                    ><strong>${a.scope === 'team' ? '团队共享' : '仅自己'}</strong>
                  </div>
                  ${button(a.scope === 'team' ? '改为仅自己' : '共享给团队', 'toggle-share', a.id)}
                  ${button(
                    a.pinned ? '取消固定保留' : '固定保留',
                    'pin',
                    a.id,
                    false,
                    !readable(a),
                  )}
                  <div class="field-hint">仅调整当前浏览器中的模拟权限与保留状态。</div>
                </div>`,
              )
            : panel(
                '团队共享产物',
                /* HTML */ `<div class="detail-body">
                  <div class="callout">
                    可以复用与追溯来源。共享范围和保留设置由模拟生成者维护。
                  </div>
                </div>`,
              )}
        </aside>
      </div>`
    );
  };
  const catalogPage = function () {
    const list = product.catalog.filter(
      (a) =>
        visible(a) &&
        (catalogScope === 'mine'
          ? own(a)
          : catalogScope === 'team'
            ? a.scope === 'team'
            : catalogScope === 'all'
              ? true
              : a.workflowId === activeWorkflow) &&
        [a.name, a.id, a.ownerName, a.key, a.workflowName]
          .join(' ')
          .toLowerCase()
          .includes(catalogText.toLowerCase()),
    );
    const size = product.catalog
      .filter((a) => own(a) && a.retained && a.status === 'complete')
      .reduce((n, a) => n + a.size, 0);
    return (
      heading(
        '数据目录',
        '查看个人与团队共享结果；身份匹配和文件可读取状态分别展示。',
        button('导出完整体验记录', 'export-state'),
      ) +
      /* HTML */ `<div class="storage-row">
          <div class="panel storage-card">
            <div class="eyebrow">个人模拟保留预算</div>
            <div class="stat-number">${size.toFixed(2)}<small>GB / 4 GB</small></div>
            <div class="storage-meter">
              <span style="width:${Math.min(100, (size / 4) * 100)}%"></span>
            </div>
            <div class="small muted">团队成员产物不计入此个人预算。</div>
          </div>
          <div class="panel storage-card">
            <div class="panel-title">跨工作流查找与复用</div>
            <p class="small muted">
              “当前流程”用于定位；“我的产物”和“团队共享”可跨流程查询。<br />生成条件相同的产物共享同一演示身份，流程归属独立记录。
            </p>
          </div>
        </div>
        <div class="panel">
          <div class="data-toolbar">
            ${[
              ['current', '当前流程'],
              ['mine', '我的产物'],
              ['team', '团队共享'],
              ['all', '全部可见产物'],
            ]
              .map(
                ([id, name]) =>
                  /* HTML */ `<button
                    class="filter ${catalogScope === id ? 'active' : ''}"
                    data-action="catalog-scope"
                    data-value="${id}"
                  >
                    ${name}
                  </button>`,
              )
              .join('')}<input
              id="catalog-search"
              class="toolbar-search"
              aria-label="搜索当前目录范围"
              placeholder="文件、生成者、身份或流程"
              value="${esc(catalogText)}"
            />
          </div>
          <div class="table-scroller">
            <table class="decision-table">
              <thead>
                <tr>
                  <th>产物 / 流程</th>
                  <th>生成者</th>
                  <th>共享范围</th>
                  <th>模拟文件状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                ${list
                  .map(
                    (a) =>
                      /* HTML */ `<tr>
                        <td>
                          <b>${esc(a.name)}</b>
                          <div class="reason">${esc(a.id)} · ${esc(a.workflowName)}</div>
                        </td>
                        <td>${esc(a.ownerName)}</td>
                        <td>${a.scope === 'team' ? '团队共享' : '仅自己'}</td>
                        <td>
                          ${statusBadge(a.status)}${a.retained === false
                            ? '<div class="reason">模拟文件未保留；来源可追溯</div>'
                            : ''}
                        </td>
                        <td>${routeButton('产物详情', 'artifact', a.id)}</td>
                      </tr>`,
                  )
                  .join('')}
              </tbody>
            </table>
            ${list.length ? '' : '<div class="empty">此范围没有匹配的产物。</div>'}
          </div>
        </div>`
    );
  };
  const toolsPage = function () {
    if (activeTool) return toolSessionPage();
    const source = page.query.get('artifact') || '',
      from = page.query.get('from') || '';
    return (
      heading(
        '常用工具',
        '从指定产物进入结构查看会话，来源始终可追溯。',
        from ? routeButton('返回实验', 'experiment', from) : '',
      ) +
      banner(
        source
          ? '已锁定产物：' + esc(artifactById(source)?.name || source) + '。选择工具继续。'
          : '选择工具后，再明确选择要查看的可读取产物。',
      ) +
      /* HTML */ `<div class="entry-grid">
        ${Object.entries(toolInfo)
          .map(
            ([id, t]) =>
              /* HTML */ `<div class="entry-card tool-card">
                <div class="entry-copy">
                  <div class="tool-emblem ${t.color === 'blue' ? 'blue' : ''}">${t.initial}</div>
                  <div class="entry-title">
                    <h2>${t.name}</h2>
                    <span class="pill">${id === 'pymol' ? '实时会话' : '模拟会话'}</span>
                  </div>
                  <p>${t.description}</p>
                  <div class="entry-bottom">
                    <span>${id === 'pymol' ? '加载真实结构文件' : '不启动真实软件'}</span
                    ><button
                      class="btn primary"
                      data-tool="${id}"
                      data-source="${esc(source)}"
                      data-from="${esc(from)}"
                    >
                      选择工具 ${icon('arrow')}
                    </button>
                  </div>
                </div>
              </div>`,
          )
          .join('')}
      </div>`
    );
  };
  const pymolCommands = [];
  const pymolPage = function () {
    const viewer = new URL('pymol.html', document.baseURI);
    return (
      heading('PyMOL', '真实结构查看与交互',
        '<button class="btn" id="tool-list-preserve">工具列表</button>') +
      banner('此处连接真实 PyMOL。工作流目录仍使用模拟数据，请选择真实结构文件加载。') +
      /* HTML */ `<div class="tool-layout">
        <section class="panel">
          <div class="panel-head">
            <div class="panel-title">${icon('atom')} PyMOL 实时会话</div>
            <div class="pymol-view-actions">
              <label class="pymol-mode">
                <input id="pymol-full-ui" type="checkbox" role="switch" disabled>
                <span>完整界面</span>
              </label>
              <span class="pill good">真实工具</span>
            </div>
          </div>
          <iframe class="pymol-session" title="PyMOL 实时结构查看" src="${esc(viewer.href)}" allowfullscreen></iframe>
          <div class="pymol-console">
            <form id="pymol-command-form" class="pymol-command-form">
              <label for="pymol-command">PyMOL&gt;</label>
              <input id="pymol-command" type="text" maxlength="4096" autocomplete="off"
                spellcheck="false" placeholder="例如：color cyan, all" disabled>
              <button class="btn primary" id="pymol-execute" type="submit" disabled>执行</button>
            </form>
            <label class="pymol-history">
              <span>命令历史</span>
              <select id="pymol-history"><option value="">选择已执行的命令</option></select>
            </label>
            <details class="pymol-output" open>
              <summary>执行输出</summary>
              <pre id="pymol-output" role="log" aria-live="polite">命令在当前 PyMOL 会话执行，反馈与查询结果显示于此。</pre>
            </details>
          </div>
        </section>
        <aside class="panel">
          <div class="panel-head"><div class="panel-title">结构文件</div></div>
          <div class="tool-settings">
            <label class="field"><span>选择本地结构文件</span>
              <input id="pymol-file" type="file" accept=".pdb,.cif,.mmcif">
              <small>PDB / mmCIF，最大 1 MiB。文件保存在个人工作区。</small>
            </label>
            <label class="field"><span>显示方式</span>
              <select id="pymol-style" disabled>
                <option value="cartoon">卡通</option>
                <option value="sticks">球棍</option>
                <option value="lines">线框</option>
                <option value="surface">表面</option>
              </select>
            </label>
            <div class="source-key" id="pymol-status" role="status">正在连接 PyMOL…</div>
            <button class="btn primary" id="pymol-open" disabled>加载到 PyMOL</button>
            <p class="small muted">本工作区的浏览器页面共用同一个 PyMOL 会话。</p>
          </div>
        </aside>
      </div>`
    );
  };
  const bindPymolControls = function () {
    if (activeTool !== 'pymol') return;
    const fileInput = $('#pymol-file');
    const openButton = $('#pymol-open');
    const styleInput = $('#pymol-style');
    const status = $('#pymol-status');
    const fullUI = $('#pymol-full-ui');
    const commandInput = $('#pymol-command');
    const executeButton = $('#pymol-execute');
    const history = $('#pymol-history');
    const output = $('#pymol-output');
    const refreshHistory = () => {
      history.replaceChildren(new Option('选择已执行的命令', ''));
      for (const command of [...pymolCommands].reverse()) {
        history.add(new Option(command, command));
      }
    };
    refreshHistory();
    history.onchange = () => {
      if (history.value) {
        commandInput.value = history.value;
        commandInput.focus();
      }
    };
    let historyIndex = pymolCommands.length;
    let commandDraft = '';
    commandInput.onkeydown = (event) => {
      if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
      if (!pymolCommands.length) return;
      event.preventDefault();
      if (historyIndex === pymolCommands.length) commandDraft = commandInput.value;
      const step = event.key === 'ArrowUp' ? -1 : 1;
      historyIndex = Math.max(0, Math.min(pymolCommands.length, historyIndex + step));
      commandInput.value = pymolCommands[historyIndex] ?? commandDraft;
    };
    fullUI.onchange = async () => {
      fullUI.disabled = true;
      try {
        const result = await DemoAPI.setPymolMode(fullUI.checked);
        fullUI.checked = result.full_ui;
      } catch (error) {
        fullUI.checked = !fullUI.checked;
        status.textContent = error.message;
      } finally {
        fullUI.disabled = false;
      }
    };
    $('#pymol-command-form').onsubmit = async (event) => {
      event.preventDefault();
      const command = commandInput.value.trim();
      if (!command || executeButton.disabled) return;
      executeButton.disabled = true;
      commandInput.disabled = true;
      pymolCommands.push(command);
      if (pymolCommands.length > 50) pymolCommands.shift();
      historyIndex = pymolCommands.length;
      commandDraft = '';
      refreshHistory();
      output.textContent += `\n\nPyMOL> ${command}\n正在执行…`;
      const pendingOutput = output.textContent;
      const showOutput = (message) => {
        output.textContent = pendingOutput.replace(/正在执行…$/, () => message).slice(-50000);
        output.scrollTop = output.scrollHeight;
      };
      try {
        const result = await DemoAPI.executePymol(command);
        showOutput(result.output || '命令已执行（无文本输出）。');
        commandInput.value = '';
        showStructure(await DemoAPI.pymolStatus());
      } catch (error) {
        showOutput(error.message);
      } finally {
        executeButton.disabled = false;
        commandInput.disabled = false;
        commandInput.focus();
      }
    };
    const showStructure = (result) => {
      status.textContent = result.atoms
        ? `${result.filename} · ${result.atoms} 个原子`
        : 'PyMOL 已就绪，请选择结构文件。';
      styleInput.disabled = !result.atoms;
      if (typeof result.full_ui === 'boolean') fullUI.checked = result.full_ui;
      fullUI.disabled = false;
      commandInput.disabled = false;
      executeButton.disabled = false;
    };
    fileInput.onchange = () => {
      openButton.disabled = !fileInput.files.length;
    };
    openButton.onclick = async () => {
      const file = fileInput.files[0];
      if (!file) return;
      if (file.size > 1024 * 1024) {
        status.textContent = '请选择不超过 1 MiB 的结构文件。';
        return;
      }
      openButton.disabled = true;
      status.textContent = '正在加载结构…';
      try {
        showStructure(await DemoAPI.loadStructure(file, styleInput.value));
      } catch (error) {
        status.textContent = error.message;
      } finally {
        openButton.disabled = !fileInput.files.length;
      }
    };
    styleInput.onchange = async () => {
      try {
        await DemoAPI.setPymolStyle(styleInput.value);
      } catch (error) {
        status.textContent = error.message;
      }
    };
    DemoAPI.pymolStatus().then(showStructure).catch((error) => {
      status.textContent = error.message;
    });
  };
  const toolSessionPage = function () {
    if (activeTool === 'pymol') return pymolPage();
    const t = toolInfo[activeTool],
      sourceId = page.query.get('artifact') || '',
      a = artifactById(sourceId),
      from = page.query.get('from') || '',
      sources = product.catalog.filter(isViewable);
    toolStyle = page.query.get('style') || 'sticks';
    toolOpened = page.query.get('opened') === '1' && isViewable(a);
    return (
      heading(
        t.name,
        '指定产物的结构查看会话 · 示意渲染',
        `${from ? routeButton('返回实验', 'experiment', from) : ''}${a ? /* HTML */ `<button class="btn" data-artifact-detail="${a.id}" data-from="${esc(from)}">返回产物详情</button>` : ''}<button class="btn" id="tool-list-preserve">工具列表</button>`,
      ) +
      banner('界面仅展示模拟会话与结构示意图，不代表所选文件的真实分子结构。') +
      /* HTML */ `<div class="tool-layout">
        <section class="panel">
          <div class="panel-head">
            <div class="panel-title">${icon('atom')} ${a ? esc(a.name) : '尚未选择产物'}</div>
            <span class="pill">${t.name}</span>
          </div>
          <div class="tool-preview ${t.color === 'blue' ? 'blue' : ''}">
            <span class="tool-preview-status pill ${toolOpened ? 'good' : ''}"
              >${toolOpened ? '指定产物的模拟会话已打开' : '等待打开模拟会话'}</span
            >${toolDrawing()}<span class="tool-preview-stamp"
              >ILLUSTRATION ONLY · 非真实结构渲染</span
            >
          </div>
          <div class="tool-foot">
            <span
              >${a
                ? esc(a.id) + ' · ' + esc(a.ownerName) + ' · ' + esc(a.runId)
                : '请选择可读取的结构产物'}</span
            >
          </div>
          ${toolOpened
            ? /* HTML */ `<div class="tool-result">
                已绑定 ${esc(a.id)}；切换显示方式不改变产物来源。
              </div>`
            : ''}
        </section>
        <aside class="panel">
          <div class="panel-head">
            <div class="panel-title">会话配置</div>
            <span class="pill">DEMO</span>
          </div>
          <div class="tool-settings">
            <label class="field"
              ><span>明确选择产物</span
              ><select id="tool-source">
                <option value="">请选择产物</option>
                ${sources
                  .map(
                    (a) =>
                      /* HTML */ `<option value="${a.id}" ${a.id === sourceId ? 'selected' : ''}>
                        ${esc(a.name)} · ${a.id} · ${esc(a.ownerName)}
                      </option>`,
                  )
                  .join('')}
              </select></label
            >${a && !isViewable(a)
              ? '<div class="form-error">指定产物当前不可读取，或不支持结构查看。</div>'
              : ''}<label class="field"
              ><span>示例显示方式</span
              ><select id="tool-style">
                ${[
                  ['sticks', '球棍示意'],
                  ['lines', '线框示意'],
                  ['surface', '表面示意'],
                ]
                  .map(
                    ([id, name]) =>
                      /* HTML */ `<option value="${id}" ${id === toolStyle ? 'selected' : ''}>
                        ${name}
                      </option>`,
                  )
                  .join('')}
              </select></label
            >
            <div class="source-key">
              ${a ? esc(a.id) + '<br>' + esc(a.key) : '不会自动替换为其他产物。'}
            </div>
            ${button('打开指定产物的模拟会话', 'launch-tool', '', true, !isViewable(a))}
          </div>
        </aside>
      </div>`
    );
  };
  const policyPage = function policyPage() {
    const cards = allPolicies();
    return (
      heading(
        '复用与存储',
        '决定哪些结果直接用、哪些重新算，以及保存哪些数据。',
        /* HTML */ `<button class="btn primary" data-nav="newpolicy">＋ 新增策略</button>`,
      ) +
      /* HTML */ `<div class="info-banner">
          用同一组任务，比较不同策略的预计用时。以下数据仅用于演示。
        </div>
        <div class="policy-grid">
          ${cards
            .map((c) => {
              const p = plan(config, c.id),
                m = metrics(p);
              return /* HTML */ `<div
                class="panel policy-card ${policy === c.id ? 'selected' : ''}"
              >
                <span class="pill ${c.custom ? 'blue' : ''}"
                  >${c.custom ? '自定义策略' : '内置策略'}</span
                >
                <h3>${esc(c.name)}</h3>
                <p>${esc(c.description)}</p>
                <div class="policy-number">${fmt(m.total)}</div>
                <div class="small muted">预计用时 · ${m.reuse} 个步骤直接复用</div>
                <div class="kv" style="margin-top:19px">
                  <span>读取结果</span><strong>${fmt(m.load)}</strong>
                </div>
                <div class="kv"><span>重新计算</span><strong>${fmt(m.compute)}</strong></div>
                <div class="policy-rule">
                  <span>复用</span>${reuseLabel(c.reuse)}<br /><span>保存</span>${storageLabel(
                    c.storage,
                  )}
                </div>
                <button
                  class="btn ${policy === c.id ? 'primary' : ''}"
                  data-policy="${c.id}"
                  ${busy ? 'disabled' : ''}
                >
                  ${policy === c.id ? '正在使用' : '应用此策略'}
                </button>
              </div>`;
            })
            .join('')}
        </div>
        <div class="panel" style="margin-top:22px">
          <div class="panel-head">
            <div class="panel-title">怎么选择？</div>
            <span class="pill">示例空间：4 GB</span>
          </div>
          <div class="flow-notes">
            <div class="flow-note">
              <b>先看结果还能不能用</b>
              <p>输入、模型或设置变了，相关步骤就需要重新计算。</p>
            </div>
            <div class="flow-note">
              <b>再比较读取和重算时间</b>
              <p>已有结果不一定更快。数据较远、读取较慢时，可以选择重算。</p>
            </div>
            <div class="flow-note">
              <b>重要结果可以固定保留</b>
              <p>在数据目录中固定的结果，不会被自动清理。</p>
            </div>
          </div>
        </div>`
    );
  };
  const missingPage = function missingPage(message) {
    return heading(
      message,
      '该记录可能尚未导入，或链接已经失效。',
      routeButton('返回工作流', 'workflows'),
    );
  };

  // Navigation, forms and user actions
  const hrefFor = function hrefFor(name, id = '', query = {}) {
    const paths = {
      workflows: 'workflows',
      workflow: 'experiment/new/' + encodeURIComponent(id || activeWorkflow),
      experiment: 'experiment/' + encodeURIComponent(id),
      artifact: 'artifact/' + encodeURIComponent(id),
      tools: 'tools' + (id ? '/' + encodeURIComponent(id) : ''),
      runs: 'experiments',
      catalog: 'catalog',
      policy: 'policy',
      newpolicy: 'policy/new',
      newworkflow: 'workflows/new',
    };
    const qs = new URLSearchParams(query).toString();
    return '#/' + (paths[name] || 'workflows') + (qs ? '?' + qs : '');
  };
  const readRoute = function readRoute() {
    const previousContext = page.name + ':' + page.id;
    const raw = (location.hash || '#/experiments').slice(2),
      [path, query = ''] = raw.split('?');
    let seg;
    try {
      seg = path.split('/').map(decodeURIComponent);
    } catch (error) {
      seg = ['experiments'];
    }
    page = { name: 'workflows', id: '', query: new URLSearchParams(query) };
    if (seg[0] === 'experiment' && seg[1] === 'new')
      page = { ...page, name: 'workflow', id: seg[2] || product.selectedWorkflow };
    else if (seg[0] === 'experiment' && seg[1]) page = { ...page, name: 'experiment', id: seg[1] };
    else if (seg[0] === 'artifact') page = { ...page, name: 'artifact', id: seg[1] };
    else if (seg[0] === 'experiments') page.name = 'runs';
    else if (seg[0] === 'catalog') page.name = 'catalog';
    else if (seg[0] === 'tools') {
      page.name = 'tools';
      page.id = seg[1] || '';
    } else if (seg[0] === 'policy') page.name = seg[1] === 'new' ? 'newpolicy' : 'policy';
    else if (seg[0] === 'workflows' && seg[1] === 'new') page.name = 'newworkflow';
    if (page.name + ':' + page.id !== previousContext) selectedPlanStep = '';
    route = page.name;
    activeTool = page.name === 'tools' && Object.hasOwn(toolInfo, page.id) ? page.id : null;
    if (page.name === 'workflow' && workflowById(page.id)) {
      selectWorkflowContext(page.id);
      if (!currentDraft()) createExperimentDraft(page.id);
    }
    const target =
      page.name === 'experiment'
        ? experimentById(page.id)?.workflowId
        : page.name === 'artifact'
          ? artifactById(page.id)?.workflowId
          : null;
    if (target && workflowById(target)) selectWorkflowContext(target);
  };
  const nav = function (name, id = '', query = {}) {
    const hash = hrefFor(name, id, query);
    if (location.hash === hash) {
      readRoute();
      render();
    } else location.hash = hash;
  };
  const openWorkflow = function (id) {
    if (!workflowById(id)) return false;
    if (!product.drafts[id]) createExperimentDraft(id);
    nav('workflow', id);
    return true;
  };
  const openModal = function openModal(title, html) {
    returnFocus = document.activeElement;
    $('#modal-title').textContent = title;
    $('#modal-content').innerHTML = html;
    $('#modal').hidden = false;
    document.body.style.overflow = 'hidden';
    $('#modal .modal-close').focus();
  };
  const closeModal = function closeModal() {
    $('#modal').hidden = true;
    document.body.style.overflow = '';
    if (returnFocus && returnFocus.isConnected) returnFocus.focus();
  };
  const workflowDefinition = function workflowDefinition(id) {
    const w = workflowById(id);
    if (!w) return;
    const s = w.steps || (w.template === 'protein' ? proteinSteps : moleculeSteps);
    openModal(
      w.name + ' · 流程定义',
      /* HTML */ `<p>${esc(w.description)}</p>
        <div class="callout">
          ${w.custom
            ? '已登记配置；未读取服务器文件或执行命令。'
            : '内置依赖与版本均为演示约定，不代表所有科研工具。'}
        </div>
        ${w.executionDefinition
          ? /* HTML */ `<div class="log">
              ${esc(JSON.stringify(w.executionDefinition, null, 2))}
            </div>`
          : s
              .map(
                (step) =>
                  /* HTML */ `<h3>${esc(step.name)}</h3>
                    <p>${esc(step.description)}</p>`,
              )
              .join('')}
        <p>修改输入、模型或策略请创建实验；历史实验保留独立快照。</p>`,
    );
  };
  const showAbout = function () {
    openModal(
      '研序 · 本地模拟体验',
      /* HTML */ `<h3>完整使用路径</h3>
        <p>
          选择流程 → 创建实验 → 检查个人与团队候选 → 选择复用、重算或等待 → 模拟运行 → 实验详情 →
          产物详情 → 指定产物的工具会话。
        </p>
        <h3>当前模拟边界</h3>
        <p>
          工作流、成员共享、成本和 ChimeraX 会话仍为模拟，不执行登记的模型命令或调用 AI。
          PyMOL 页面提供真实结构查看，可加载本人选择的 PDB 或 mmCIF 文件。工作流下载仍为模拟 JSON。
        </p>
        <h3>保存与恢复</h3>
        <p>
          体验记录和草稿保留浏览器备份，并通过 Python API
          保存到服务端的浏览器独立命名空间；这不是成员鉴权。保存失败或并发冲突时请先导出。刷新会保留已保存记录，运行中的模拟会标为中断。团队数据仍是模拟，未在真实账户间共享。
        </p>
        <div class="modal-actions">
          ${button('导出完整体验记录', 'export-state')}${button(
            '导入体验记录',
            'import-state',
          )}${button('恢复服务端记录', 'restore-backend')}
        </div>
        <p>支持复制实验与新样本请求。自定义流程当前仅支持串行连接。</p>`,
    );
    bindProductActions($('#modal-content'));
  };
  const download = function download(name, data) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
      url = URL.createObjectURL(blob),
      a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    notify('已导出示例 JSON。');
  };
  const downloadProduct = function downloadProduct(name, data) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
      url = URL.createObjectURL(blob),
      a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    notify('已导出带有模拟标记的 JSON。');
  };
  const actionProduct = function actionProduct(action, value, el) {
    if (action === 'restore-backend') {
      openModal(
        '恢复服务端记录',
        /* HTML */ `<p>请先导出本页未同步修改。确认后会用服务端最新快照替换本页数据。</p>
          ${button('导出当前记录', 'export-state')}
          <button class="btn primary" id="restore-backend-confirm">确认恢复服务端记录</button>`,
      );
      bindProductActions($('#modal-content'));
      $('#restore-backend-confirm').onclick = async () => {
        try {
          const saved = await DemoAPI.prepareImport();
          if (!saved.state) {
            notify('服务端尚无快照；当前记录未替换。');
            return;
          }
          applySaved(saved.state);
          saveProduct();
          closeModal();
          nav('workflows');
          notify('服务端记录已恢复。');
        } catch (error) {
          notify('恢复失败；当前记录保留。');
        }
      };
      return;
    }
    if (action === 'create-experiment') return createExperiment();
    if (action === 'experiment-flow-view') {
      if (page.name !== 'experiment' || !['config', 'results'].includes(value)) return;
      page.query.set('view', value);
      // This is a view change, not navigation: preserve the scroll position,
      // current simulation, candidate choices and selected node.
      history.replaceState(null, '', hrefFor('experiment', page.id, Object.fromEntries(page.query)));
      render();
      $('#experiment-flow-view')?.focus({ preventScroll: true });
      return;
    }
    if (action === 'start') return startExperiment(value);
    if (action === 'new-draft') {
      if (product.drafts[value]) {
        openModal(
          '另建一次实验',
          /* HTML */ `<p>当前流程已有草稿。可以导出记录后替换，或继续编辑原草稿。</p>
            ${button('保留原草稿，返回编辑', 'resume-draft', value)}
            ${button('替换为新草稿', 'replace-draft', value)}`,
        );
        bindProductActions($('#modal-content'));
      } else {
        createExperimentDraft(value);
        nav('workflow', value);
      }
      return;
    }
    if (action === 'resume-draft') {
      closeModal();
      nav('workflow', value);
      return;
    }
    if (action === 'replace-draft') {
      closeModal();
      createExperimentDraft(value);
      nav('workflow', value);
      return;
    }
    if (action === 'workflow-definition') return workflowDefinition(value);
    if (action === 'clone-experiment') return cloneExperiment(value);
    if (action === 'cancel') return cancelExperiment(value);
    if (action === 'catalog-scope') {
      catalogScope = value;
      render();
      return;
    }
    if (action === 'experiment-scope') {
      experimentScope = value;
      render();
      return;
    }
    if (action === 'pin' || action === 'toggle-share') {
      const a = artifactById(value);
      if (!a || !own(a)) return;
      if (action === 'pin') {
        if (!readable(a)) return;
        a.pinned = !a.pinned;
      } else a.scope = a.scope === 'team' ? 'private' : 'team';
      saveProduct();
      render();
      return;
    }
    if (action === 'use-input') return useArtifactInput(value, $('#input-target')?.value);
    if (action === 'launch-tool') {
      const a = artifactById(page.query.get('artifact'));
      if (!isViewable(a)) return;
      nav('tools', activeTool, {
        artifact: a.id,
        from: page.query.get('from') || '',
        style: toolStyle,
        opened: '1',
      });
      return;
    }
    if (action === 'export-state')
      return downloadProduct('yanxu-demo-experience.json', { ...persistable(), demo: true });
    if (action === 'export-plan') {
      const d = currentDraft();
      return downloadProduct('yanxu-demo-plan.json', { demo: true, draft: d, plan: packPlan(d) });
    }
    if (action === 'export-experiment')
      return downloadProduct(value + '-demo.json', {
        demo: true,
        experiment: experimentById(value),
      });
    if (action === 'download-artifact')
      return downloadProduct(value + '-simulation.json', {
        demo: true,
        scientificFile: false,
        note: '仅为模拟产物说明，不是真实科学文件。',
        artifact: artifactById(value),
      });
    if (action === 'import-state') {
      $('#state-import').click();
      return;
    }
  };
  const bindProductActions = function bindProductActions(root = document) {
    root
      .querySelectorAll('[data-action]')
      .forEach((el) => (el.onclick = () => actionProduct(el.dataset.action, el.dataset.value, el)));
  };
  const bindCreation = function bindCreation() {
    const workflowForm = $('#create-workflow'),
      policyForm = $('#create-policy');
    if (workflowForm) {
      $('#workflow-name').oninput = (e) => {
        workflowDraft.name = e.target.value;
        $('#workflow-preview-name').textContent = e.target.value.trim() || '未命名流程';
        $('#workflow-form-error').hidden = true;
      };
      $('#workflow-description').oninput = (e) => {
        workflowDraft.description = e.target.value;
      };
      $('#workflow-template').onchange = (e) => {
        workflowDraft.template = e.target.value;
        workflowDraft.registrations = emptyWorkflowDraft(e.target.value).registrations;
        delete workflowDraft.agentSource;
        registrationOpen = 0;
        registrationCheck = '';
        workflowFormError = '';
        render();
        if ($('#workflow-template')) $('#workflow-template').focus();
      };
      workflowForm.onsubmit = (e) => {
        e.preventDefault();
        const result = createWorkflow(workflowDraft);
        if (!result.ok) {
          workflowFormError = result.error;
          $('#workflow-form-error').textContent = result.error;
          $('#workflow-form-error').hidden = false;
          $('#workflow-name').focus();
          return;
        }
        workflowDraft = emptyWorkflowDraft();
        registrationOpen = 0;
        registrationCheck = '';
        workflowFormError = '';
        nav('workflows');
        notify('工作流已创建，点击卡片即可进入。');
      };
    }
    if (policyForm) {
      $('#policy-name').oninput = (e) => {
        policyDraft.name = e.target.value;
        $('#policy-preview-name').textContent = e.target.value.trim() || '未命名策略';
        $('#policy-form-error').hidden = true;
      };
      $('#policy-description').oninput = (e) => {
        policyDraft.description = e.target.value;
      };
      $('#policy-reuse').onchange = (e) => {
        policyDraft.reuse = e.target.value;
        $('#reuse-preview').textContent = reuseLabel(e.target.value);
      };
      $('#policy-storage').onchange = (e) => {
        policyDraft.storage = e.target.value;
        $('#storage-preview').textContent = storageLabel(e.target.value);
      };
      policyForm.onsubmit = (e) => {
        e.preventDefault();
        const result = createPolicy(policyDraft);
        if (!result.ok) {
          policyFormError = result.error;
          $('#policy-form-error').textContent = result.error;
          $('#policy-form-error').hidden = false;
          $('#policy-name').focus();
          return;
        }
        policyDraft = { name: '', reuse: 'cost', storage: 'lru', description: '' };
        policyFormError = '';
        nav('policy');
        notify('策略已保存，可以在列表中应用。');
      };
    }
    for (const formId of ['create-workflow', 'create-policy']) {
      const form = $('#' + formId);
      if (!form) continue;
      const old = form.onsubmit;
      form.onsubmit = (e) => {
        old(e);
        saveProduct();
      };
      form.addEventListener('input', () => {
        clearTimeout(registrationSaveTimer);
        registrationSaveTimer = setTimeout(saveProduct, 200);
      });
      form.addEventListener('change', saveProduct);
    }
    const type = $('#workflow-template');
    if (type) {
      const old = type.onchange;
      type.onchange = (e) => {
        const hasInput = workflowDraft.registrations.some(
          (s) => s.command || s.modelPath || s.version,
        );
        if (hasInput) {
          const chosen = e.target.value;
          e.target.value = workflowDraft.template;
          openModal(
            '更换流程模板',
            /* HTML */ `<p>更换模板会替换当前步骤登记；项目基本信息保留。</p>
              ${button('保留当前步骤', 'keep-template')}
              ${button('确认更换模板', 'change-template', chosen)}`,
          );
          $('#modal-content [data-action="keep-template"]').onclick = closeModal;
          $('#modal-content [data-action="change-template"]').onclick = () => {
            closeModal();
            old({ target: { value: chosen } });
            saveProduct();
          };
        } else {
          old(e);
          saveProduct();
        }
      };
    }
  };
  const bindRegistration = function bindRegistration() {
    document.querySelectorAll('[data-registration-mode]').forEach(button => {
      button.onclick = () => button.dataset.registrationMode === 'ai'
        ? showAIRegistration() : nav('newworkflow');
    });
    if (!$('#create-workflow')) return;
    ensureRegistrationDraft();
    document.querySelectorAll('[data-project-field]').forEach(
      (el) =>
        (el.oninput = () => {
          workflowDraft[el.dataset.projectField] = el.value;
          clearRegistrationCheck();
        }),
    );
    document.querySelectorAll('[data-reg-field]').forEach(
      (el) =>
        (el.oninput = () => {
          const i = Number(el.dataset.regIndex),
            step = workflowDraft.registrations[i];
          step[el.dataset.regField] = el.value;
          clearRegistrationCheck();
          if ($('#registration-title-' + i))
            $('#registration-title-' + i).textContent = step.name || '未命名步骤';
          if ($('#preview-stage-name-' + i))
            $('#preview-stage-name-' + i).textContent = step.name || '未命名步骤';
          const complete = registrationComplete(step);
          if ($('#registration-status-' + i)) {
            $('#registration-status-' + i).textContent = complete ? '已填写' : '待填写';
            $('#registration-status-' + i).classList.toggle('good', complete);
          }
          if ($('#preview-stage-status-' + i))
            $('#preview-stage-status-' + i).textContent = complete
              ? '接入信息已填写'
              : '等待填写接入信息';
        }),
    );
    document.querySelectorAll('[data-registration-details]').forEach(
      (el) =>
        (el.ontoggle = () => {
          if (el.open) registrationOpen = Number(el.dataset.registrationDetails);
        }),
    );
    document.querySelectorAll('[data-reg-action]').forEach(
      (el) =>
        (el.onclick = () => {
          const i = Number(el.dataset.regIndex),
            action = el.dataset.regAction,
            list = workflowDraft.registrations;
          if (action === 'remove' && list.length > 1) {
            list.splice(i, 1);
            registrationOpen = Math.min(i, list.length - 1);
          } else {
            const to = i + (action === 'up' ? -1 : 1);
            if (to < 0 || to >= list.length) return;
            [list[i], list[to]] = [list[to], list[i]];
            registrationOpen = to;
          }
          clearRegistrationCheck();
          render();
        }),
    );
    if ($('#add-registration'))
      $('#add-registration').onclick = () => {
        const list = workflowDraft.registrations;
        if (list.length >= 12) return;
        const i = list.length;
        list.push({
          ...blankRegistration(
            {
              id: 'step-' + (i + 1),
              name: '自定义步骤 ' + (i + 1),
              deps: [],
              file: 'output-' + (i + 1) + '.json',
            },
            i,
            'custom',
          ),
          input: list[i - 1].output,
        });
        registrationOpen = i;
        clearRegistrationCheck();
        render();
      };
    if ($('#fill-registration-demo'))
      $('#fill-registration-demo').onclick = () => {
        const draft = demoWorkflowDraft(workflowDraft.template);
        if (workflowDraft.template === 'custom')
          draft.registrations = workflowDraft.registrations.map((step, i) => ({
            ...step,
            modelPath: 'models/step-' + (i + 1),
            docPath: 'docs/step-' + (i + 1) + '.md',
            version: 'demo-v1',
            command: 'python run.py --input {input} --output {output}',
          }));
        draft.name = workflowDraft.name || '我的科研流程';
        draft.description = workflowDraft.description;
        workflowDraft = draft;
        registrationCheck = '已填入演示内容，请替换为服务器上的实际路径和指令。';
        render();
      };
    if ($('#check-registration'))
      $('#check-registration').onclick = () => {
        const error = validateRegistration(workflowDraft);
        registrationCheck = error || '必填项已齐全。尚未检查服务器文件、环境和真实运行结果。';
        $('#registration-check').textContent = registrationCheck;
        $('#registration-check').hidden = false;
      };
    document.querySelectorAll('[data-project-field],[data-reg-field]').forEach((el) => {
      const original = el.oninput;
      el.oninput = (e) => {
        if (original) original(e);
        saveProduct();
      };
    });
    for (const id of ['fill-registration-demo', 'add-registration']) {
      const el = $('#' + id);
      if (el) {
        const old = el.onclick;
        el.onclick = (e) => {
          if (old) old(e);
          saveProduct();
        };
      }
    }
    document.querySelectorAll('[data-reg-action]').forEach((el) => {
      const old = el.onclick;
      el.onclick = (e) => {
        if (old) old(e);
        saveProduct();
      };
    });
  };
  const bind = function () {
    document
      .querySelectorAll('[data-nav]')
      .forEach((el) => (el.onclick = () => nav(el.dataset.nav)));
    document.querySelectorAll('[data-route]').forEach(
      (el) =>
        (el.onclick = () => {
          if (el.dataset.route === 'workflow') openWorkflow(el.dataset.id);
          else nav(el.dataset.route, el.dataset.id);
        }),
    );
    document.querySelectorAll('[data-draft]').forEach((el) => {
      if (el.tagName === 'SELECT')
        el.onchange = () => {
          setDraftValue(el.dataset.draft, el.value);
          render();
        };
      else {
        el.oninput = () => {
          setDraftValue(el.dataset.draft, el.value);
        };
        el.onchange = () => {
          setDraftValue(el.dataset.draft, el.value);
          if (el.dataset.draft.startsWith('config.')) render();
        };
      }
    });
    document.querySelectorAll('[data-choice]').forEach(
      (el) =>
        (el.onchange = () => {
          const experiment = page.name === 'experiment' ? experimentById(page.id) : null;
          if (experiment?.status === 'ready') {
            experiment.choices ||= {};
            experiment.choices[el.dataset.choice] = el.value;
            experiment.plan = packPlan(experiment);
            experiment.metrics = planMetrics(experiment.plan);
          } else {
            const d = currentDraft();
            if (!d) return;
            d.choices[el.dataset.choice] = el.value;
          }
          saveProduct();
          render();
        }),
    );
    document
      .querySelectorAll('[data-candidate-detail]')
      .forEach(
        (el) =>
          (el.onclick = () =>
            nav(
              'artifact',
              el.dataset.candidateDetail,
              el.dataset.from ? { from: el.dataset.from } : { draft: activeWorkflow },
            )),
      );
    document
      .querySelectorAll('[data-artifact-detail]')
      .forEach(
        (el) =>
          (el.onclick = () =>
            nav(
              'artifact',
              el.dataset.artifactDetail,
              el.dataset.from ? { from: el.dataset.from } : {},
            )),
      );
    document
      .querySelectorAll('[data-view-artifact]')
      .forEach(
        (el) =>
          (el.onclick = () =>
            nav('tools', '', { artifact: el.dataset.viewArtifact, from: el.dataset.from || '' })),
      );
    document.querySelectorAll('[data-tool]').forEach(
      (el) =>
        (el.onclick = () =>
          nav('tools', el.dataset.tool, {
            artifact: el.dataset.source || '',
            from: el.dataset.from || '',
          })),
    );
    if ($('#tool-list-preserve'))
      $('#tool-list-preserve').onclick = () =>
        nav('tools', '', {
          artifact: page.query.get('artifact') || '',
          from: page.query.get('from') || '',
        });
    document.querySelectorAll('[data-plan-step]').forEach(
      (el) =>
        (el.onclick = () => {
          selectedPlanStep = el.dataset.planStep;
          render();
          const details = $('#node-details');
          details?.focus({ preventScroll: true });
          details?.scrollIntoView({ block: 'nearest', behavior: flowMotionEnabled ? 'smooth' : 'instant' });
        }),
    );
    if ($('[data-close-node-detail]')) $('[data-close-node-detail]').onclick = () => {
      const previous = selectedPlanStep;
      selectedPlanStep = '';
      render();
      const node = [...document.querySelectorAll('[data-plan-step]')].find((el) => el.dataset.planStep === previous);
      node?.focus({ preventScroll: true });
      node?.scrollIntoView({ block: 'nearest', behavior: 'instant' });
    };
    const syncFlowMotion = () => {
      document.querySelectorAll('.live-flow').forEach((flow) => {
        flow.classList.toggle('flow-motion-on', flowMotionEnabled);
        flow.classList.toggle('flow-motion-off', !flowMotionEnabled);
        const svg = flow.querySelector('.flow-wires');
        if (flowMotionEnabled) svg.unpauseAnimations();
        else svg.pauseAnimations();
        const toggle = flow.querySelector('[data-flow-motion-toggle]');
        toggle.setAttribute('aria-pressed', String(flowMotionEnabled));
        toggle.setAttribute('aria-label', flowMotionEnabled ? '暂停流程图动效' : '播放流程图动效');
        toggle.textContent = flowMotionEnabled ? 'Ⅱ 暂停动效' : '▷ 播放动效';
      });
    };
    document.querySelectorAll('[data-flow-motion-toggle]').forEach((toggle) => {
      toggle.onclick = () => {
        flowMotionEnabled = !flowMotionEnabled;
        syncFlowMotion();
      };
    });
    syncFlowMotion();
    if ($('#tool-source'))
      $('#tool-source').onchange = (e) =>
        nav('tools', activeTool, {
          artifact: e.target.value,
          from: page.query.get('from') || '',
          style: toolStyle,
        });
    if ($('#tool-style'))
      $('#tool-style').onchange = (e) =>
        nav('tools', activeTool, {
          artifact: page.query.get('artifact') || '',
          from: page.query.get('from') || '',
          style: e.target.value,
          ...(toolOpened ? { opened: '1' } : {}),
        });
    if ($('#catalog-search'))
      $('#catalog-search').oninput = (e) => {
        catalogText = e.target.value;
        const pos = e.target.selectionStart;
        render();
        const input = $('#catalog-search');
        input.focus();
        input.setSelectionRange(pos, pos);
      };
    if ($('#experiment-file'))
      $('#experiment-file').onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const draft = currentDraft();
        if (file.size > 2 * 1024 * 1024) {
          notify('请选择不超过 2 MB 的小文件。');
          return;
        }
        const kind = /\.(fasta|fa|faa)$/i.test(file.name)
          ? 'FASTA'
          : /\.smi$/i.test(file.name)
            ? 'SMILES'
            : /\.sdf$/i.test(file.name)
              ? 'SDF'
              : /\.cif$/i.test(file.name)
                ? 'mmCIF'
                : /\.pdb$/i.test(file.name)
                  ? 'PDB'
                  : /\.json$/i.test(file.name)
                    ? 'JSON'
                    : 'FILE';
        if (!inputKinds(workflowInfo[draft.workflowId]).includes(kind)) {
          notify('文件类型与当前流程输入不匹配。');
          return;
        }
        const text = await file.text();
        if (currentDraft() !== draft || draft.inputSource !== 'upload') return;
        draft.config.input = 'local:' + hash(text);
        draft.inputMeta = {
          name: file.name,
          kind,
          sizeLabel: file.size + ' bytes',
          note: '只保存元数据与演示内容标识，未上传文件。',
        };
        invalidateDraft();
        render();
      };
    document.querySelectorAll('[data-policy]').forEach(
      (el) =>
        (el.onclick = () => {
          const d = currentDraft();
          if (!d) {
            notify('先创建实验，再选择本次策略。');
            return;
          }
          d.policy = el.dataset.policy;
          invalidateDraft();
          notify('已应用到当前实验草稿，请重新检查计划。');
          render();
        }),
    );
    if ($('#about-inline')) $('#about-inline').onclick = showAbout;
    bindProductActions();
  };
  const render = function () {
    aiController?.pause();
    let html;
    try {
      html = (
        {
          workflows: workflowsPage,
          workflow: () => (workflowById(page.id) ? workflowPage() : missingPage('流程不存在')),
          newworkflow: newWorkflowPage,
          catalog: catalogPage,
          runs: runsPage,
          experiment: () => experimentPage(experimentById(page.id)),
          artifact: () => artifactPage(artifactById(page.id)),
          tools: toolsPage,
          policy: policyPage,
          newpolicy: newPolicyPage,
        }[route] || workflowsPage
      )();
    } catch (error) {
      console.error(error);
      html = missingPage('页面暂时无法显示，请返回列表或导入备份');
    }
    $('#main').innerHTML =
      html +
      /* HTML */ `<footer class="footnote">
          <span>研序 / AI4S 工作台 · 本地模拟体验</span
          ><span
            >${storageOK ? '浏览器备份可用' : '浏览器备份受限'} ·
            <span id="persistence-status">${esc(DemoAPI.statusLabel())}</span> ·
            <button class="link-btn" data-action="export-state">导出</button> ·
            <button class="link-btn" data-action="import-state">导入</button> ·
            <button class="link-btn" id="about-inline">体验说明</button></span
          >
        </footer>`;
    const group =
      {
        workflow: 'workflows',
        newworkflow: 'workflows',
        experiment: 'runs',
        artifact: 'catalog',
        newpolicy: 'policy',
      }[route] || route;
    document.querySelectorAll('.nav-item').forEach((el) => {
      const yes = el.dataset.nav === group;
      el.classList.toggle('active', yes);
      if (yes) el.setAttribute('aria-current', 'page');
      else el.removeAttribute('aria-current');
    });
    $('#breadcrumb').textContent =
      {
        workflows: '工作流',
        workflow: '创建实验',
        newworkflow: '接入自定义流程',
        runs: '实验记录',
        experiment: '实验详情',
        catalog: '数据目录',
        artifact: '产物详情',
        tools: activeTool ? toolInfo[activeTool].name : '常用工具',
        policy: '复用与存储',
        newpolicy: '新增策略',
      }[route] || '工作流';
    $('#active-context').textContent = '当前流程 · ' + workflowInfo[activeWorkflow].short;
    $('#workflow-count').textContent = Object.keys(workflowInfo).length;
    $('#catalog-count').textContent = product.catalog.filter(visible).length;
    $('#run-count').textContent = product.experiments.filter((e) => !e.fixture).length;
    bind();
    bindPymolControls();
    bindCreation();
    bindRegistration();
    if ($('#workflow-ai')) void mountAIRegistration($('#workflow-ai'));
  };
  const bootProduct = function bootProduct() {
    let restored = false;
    try {
      const saved = serverSaved.preferLocal
        ? localStorage.getItem(DEMO_KEY)
        : serverSaved.state
          ? JSON.stringify(serverSaved.state)
          : localStorage.getItem(DEMO_KEY);
      if (saved) {
        applySaved(JSON.parse(saved));
        restored = true;
      }
    } catch (error) {
      storageNotice = '未能恢复浏览器记录，请导入导出的体验文件。';
    }
    if (!restored) seedProduct();
    selectWorkflowContext(product.selectedWorkflow);
    readRoute();
    saveProduct();
    render();
    $('#help-btn').onclick = showAbout;
    const global = $('#global-search');
    global.placeholder = '搜索个人与团队产物…';
    global.setAttribute('aria-label', '搜索个人与团队产物');
    global.onkeydown = (e) => {
      if (e.key === 'Enter') {
        catalogText = e.target.value;
        catalogScope = 'all';
        nav('catalog');
      }
    };
    window.addEventListener('hashchange', () => {
      readRoute();
      render();
      window.scrollTo({ top: 0, behavior: 'instant' });
    });
    $('#state-import').onchange = async (e) => {
      const file = e.target.files[0];
      e.target.value = '';
      if (!file) return;
      if (activeSimulation) {
        notify('请先完成或取消当前模拟，再导入记录。');
        return;
      }
      if (file.size > 2 * 1024 * 1024) {
        notify('体验记录文件不能超过 2 MB。');
        return;
      }
      try {
        const data = validateSaved(JSON.parse(await file.text()));
        openModal(
          '恢复体验记录',
          /* HTML */ `<p>
              将用所选记录替换当前浏览器体验，包括 ${data.experiments.length} 次实验与
              ${data.catalog.length} 个产物。可先导出当前记录。
            </p>
            ${button('先导出当前记录', 'export-state')}
            <button class="btn primary" id="confirm-import">确认恢复</button>`,
        );
        bindProductActions($('#modal-content'));
        $('#confirm-import').onclick = async () => {
          try {
            await DemoAPI.prepareImport();
            applySaved(data);
            saveProduct();
            closeModal();
            nav('workflows');
            notify('体验记录已恢复。');
          } catch (error) {
            notify('后端未就绪，尚未替换当前记录。');
          }
        };
      } catch (error) {
        notify('导入失败：' + error.message);
      }
    };
    window.addEventListener('pagehide', () => {
      saveProduct();
      void DemoAPI.flush();
    });
    if (serverSaved.conflict)
      storageNotice = '已保留本地未同步记录。请先导出，或在体验说明中选择恢复服务端记录。';
    if (storageNotice) notify(storageNotice);
  };

  workflowDraft = emptyWorkflowDraft();
  $('#modal .modal-close').onclick = closeModal;
  $('#modal').onclick = (e) => {
    if (e.target === $('#modal')) closeModal();
  };
  document.addEventListener('keydown', (e) => {
    if ($('#modal').hidden) return;
    if (e.key === 'Escape') {
      closeModal();
      return;
    }
    if (e.key === 'Tab') {
      const list = [
        ...$('#modal').querySelectorAll(
          'button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea,[tabindex="0"]',
        ),
      ];
      if (!list.length) {
        e.preventDefault();
        return;
      }
      if (e.shiftKey && document.activeElement === list[0]) {
        e.preventDefault();
        list[list.length - 1].focus();
      } else if (!e.shiftKey && document.activeElement === list[list.length - 1]) {
        e.preventDefault();
        list[0].focus();
      }
    }
  });
  window.addEventListener('demo-api-status', (event) => {
    const label = $('#persistence-status');
    if (label) label.textContent = event.detail.label;
    if (event.detail.error) notify(event.detail.error);
  });
  bootProduct();
})().catch((error) => {
  console.error(error);
  const main = document.querySelector('#main');
  if (main) {
    main.replaceChildren();
    const heading = document.createElement('h1');
    heading.textContent = '工作台暂时无法载入';
    const message = document.createElement('p');
    message.textContent =
      '请使用 python scripts/serve_workbench.py 启动前后端，检查控制台与服务日志后刷新。浏览器原有体验记录未删除。';
    main.append(heading, message);
  }
});
