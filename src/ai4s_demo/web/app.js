import { api, post, operationId, escapeHTML as esc, download } from './api.js';
import { renderMessage } from './message.js';
import { createGraph } from './graph.js';
export async function mountAssistant(host, { onApply }) {
    const root = host.attachShadow({ mode: 'open' });
    const response = await fetch(new URL('./workspace.html', import.meta.url));
    if (!response.ok) {
        throw new Error('AI 辅助暂时不可用，请稍后重试。');
    }
    root.innerHTML = await response.text();
    const stylesheet = document.createElement('link');
    stylesheet.rel = 'stylesheet';
    stylesheet.href = new URL('./styles.css', import.meta.url).href;
    const stylesLoaded = new Promise((resolve, reject) => {
        stylesheet.onload = resolve;
        stylesheet.onerror = () => reject(new Error('AI 辅助界面样式未能加载，请重试。'));
    });
    root.prepend(stylesheet);
    await stylesLoaded;
    const $ = id => root.getElementById(id);
    const graph = createGraph(root, { onMove: (node_id, position) => saveGraphOperations([{ type: 'move_node', node_id, ...position }]), onError: showError });
    const { drawNodes, drawWires, destroy } = graph;
    const lifecycle = new AbortController();
    let state, models = {}, files = [], selected = null, tab = 'params', busy = false, dirty = false;
    let preview = null, currentRequest = null, toastTimer, settings;
    const endpoint = suffix => `/api/workflows/${state.draft.id}/${suffix}`;
    const current = () => state?.draft.nodes.find(n => n.id === selected);
    const choices = (values, value) => values.map(([id, label]) => `<option value="${esc(id)}" ${id === value ? 'selected' : ''}>${esc(label)}</option>`).join('');
    function toast(text) {
        $('toast').textContent = text;
        $('toast').hidden = false;
        $('announcer').textContent = text;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => $('toast').hidden = true, 4500);
    }
    function showError(error, target = 'global-error') {
        let text = error.message || '操作失败，请重试';
        if (error.details) {
            text += '\n' + (typeof error.details === 'string' ? error.details : JSON.stringify(error.details, null, 2));
        }
        if (error.status === 409) {
            text += '\n当前输入已保留。请核对后点击「读取新配置」，再重新应用修改。';
        }
        if (error.name === 'TimeoutError') {
            text = '请求超时，保存状态暂不确定。请读取新配置确认后再重试。';
        }
        $(target).textContent = text;
        $(target).hidden = false;
    }
    function refreshDisabled() {
        root.querySelectorAll('button:not([data-confirm-control]):not([data-view-control])').forEach(b => b.disabled = busy);
        $('undo-button').disabled = busy || !state?.can_undo;
        for (const id of ['register-button', 'delete-button', 'import-button'])
            $(id).disabled = busy || !current();
        $('apply-preview').disabled = busy || !preview || !!preview.errors.length || !preview.accepted.length;
        $('download-request').disabled = busy || !currentRequest || !!currentRequest.stale;
        $('chat-input').disabled = busy;
        $('apply-workflow').disabled = busy || !state?.draft.nodes.length;
        $('save-state').textContent = busy ? '正在处理…' : dirty ? '有未保存的表单修改' : `服务端已保存 · r${state?.draft.revision ?? 0}`;
        host.setAttribute('aria-busy', String(busy));
    }
    async function run(action, errorTarget = 'global-error') {
        if (busy) {
            return;
        }
        $(errorTarget).hidden = true;
        busy = true;
        refreshDisabled();
        try {
            await action();
        }
        catch (error) {
            showError(error, errorTarget);
        }
        finally {
            busy = false;
            refreshDisabled();
        }
    }
    async function saveGraphOperations(operations, confirmed = false) {
        if (busy) {
            throw new Error('请等待当前操作完成。');
        }
        if (dirty) {
            throw new Error('请先保存参数表单，再修改画布结构或位置。');
        }
        busy = true;
        refreshDisabled();
        try {
            const result = await post(endpoint('changes'), { expected_revision: state.draft.revision, operation_id: operationId(), operations, confirmed });
            acceptState(result.state);
        }
        finally {
            busy = false;
            refreshDisabled();
        }
    }
    function acceptState(value, focus = null) {
        state = value;
        if (focus && state.draft.nodes.some(n => n.id === focus)) {
            selected = focus;
        }
        if (!current()) {
            selected = state.draft.nodes[0]?.id || null;
        }
        if (currentRequest) {
            currentRequest.stale = currentRequest.generated_at_revision !== state.draft.revision;
        }
        dirty = false;
        render();
    }
    function confirmAction(message, initialText = null) {
        return new Promise(resolve => {
            const dialog = $('confirm-dialog');
            $('confirm-content').textContent = message;
            $('confirm-input-label').hidden = initialText === null;
            $('confirm-input').value = initialText ?? '';
            const finish = value => {
                dialog.removeEventListener('cancel', cancel);
                $('confirm-apply').onclick = null;
                $('confirm-cancel').onclick = null;
                dialog.close();
                resolve(value);
            };
            const cancel = event => {
                event.preventDefault();
                finish(initialText === null ? false : null);
            };
            $('confirm-apply').onclick = () => finish(initialText === null ? true : $('confirm-input').value);
            $('confirm-cancel').onclick = () => finish(initialText === null ? false : null);
            dialog.addEventListener('cancel', cancel);
            dialog.showModal();
            if (initialText !== null) {
                $('confirm-input').focus();
            }
        });
    }
    async function discardOK() {
        return !dirty || await confirmAction('表单有未保存的修改，是否放弃这些修改？');
    }
    async function selectNode(id) {
        if (busy || id === selected || !await discardOK()) {
            return;
        }
        selected = id;
        dirty = false;
        render();
    }
    function render() {
        $('workflow-heading').textContent = state.draft.name;
        $('revision').textContent = `r${state.draft.revision}`;
        const registered = state.draft.nodes.filter(n => state.checks[n.id].status === '已登记').length;
        $('flow-caption').textContent = `${state.draft.nodes.length} 个步骤 · ${state.draft.edges.length} 条输入绑定 · ${state.draft.visual?.relations?.length || 0} 条设计关系 · 已登记 ${registered}`;
        drawNodes(state, models, selected, selectNode);
        const n = current();
        $('detail-title').textContent = n ? `${models[n.model_id].name} · ${n.label}` : '选择一个步骤';
        $('detail-subtitle').textContent = n ? `${n.id} · ${models[n.model_id].role}` : '从「＋ 步骤」开始';
        $('detail-status').textContent = n ? state.checks[n.id].status : '待配置';
        $('detail-status').className = `pill ${n && state.checks[n.id].status === '已登记' ? 'good' : 'warn'}`;
        $('agent-context').textContent = n ? `${models[n.model_id].name} · ${n.label}` : '整条工作流';
        root.querySelectorAll('[data-tab]').forEach(b => {
            const active = b.dataset.tab === tab;
            b.classList.toggle('active', active);
            b.setAttribute('aria-selected', active);
        });
        $('detail-content').setAttribute('aria-labelledby', `tab-${tab}`);
        renderDetail();
        renderConversation();
        renderRequest();
        refreshDisabled();
    }
    function issuesHTML(title, items, style = '') {
        return items.length ? `<div class="check-list ${style}"><strong>${esc(title)}</strong><ul>${items.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : '';
    }
    function renderDetail() {
        const n = current(), root = $('detail-content');
        if (!n) {
            root.innerHTML = '<p class="muted">选中流程图中的一个节点以配置参数。</p>';
            return;
        }
        const model = models[n.model_id], check = state.checks[n.id];
        if (tab === 'json') {
            root.innerHTML = `<p class="field-hint">当前服务端草稿；此处只读。登记快照另行保存。</p><pre class="json-code">${esc(JSON.stringify(n, null, 2))}</pre>`;
            return;
        }
        if (tab === 'source') {
            root.innerHTML = `<p class="field-hint">${esc(model.scenario)}</p><p class="field-hint">定义 ${esc(model.definition_version)} · 代码身份 ${esc(model.code_identity)}</p><a href="${esc(model.source_url)}" target="_blank" rel="noopener noreferrer">查看官方参数入口 ↗</a><div class="source-detail">${esc(model.documentation)}</div><details><summary>本节点参数的登记依据</summary><pre class="json-code">${esc(JSON.stringify(n.provenance, null, 2))}</pre></details>`;
            return;
        }
        root.innerHTML = `<form id="node-form" data-revision="${state.draft.revision}"><label class="field"><span class="field-label">节点名称</span><input name="node_label" maxlength="80" required value="${esc(n.label)}"></label><div class="fields spaced">${model.fields.map(f => {
            const value = n.params[f.key], provenance = n.provenance[f.key];
            const input = f.type === 'select' ? `<select name="param-${esc(f.key)}">${choices(f.options, value)}</select>` : `<input name="param-${esc(f.key)}" type="number" value="${esc(value)}" min="${f.min}" max="${f.max}" step="${f.step}" required>`;
            return `<label class="field"><span class="field-label">${esc(f.label)} <code>${esc(f.key)}</code></span>${input}<span class="provenance">${provenance?.kind === 'example' ? '演示值' : provenance?.kind === 'official_default' ? '资料中的默认值' : provenance?.kind === 'user' ? '用户指定' : '来源待核对'}</span></label>`;
        }).join('')}</div>
    ${n.model_id === 'proteinmpnn' ? `<div class="fields spaced"><label class="field"><span class="field-label">设计链策略</span><select name="chain_mode">${choices([['', '请确认策略'], ['all', '设计全部链'], ['selected', '选择部分链']], n.design_chain_policy?.mode || '')}</select></label><label class="field"><span class="field-label">部分链标识（空格分隔）</span><input name="chains" value="${esc(n.design_chain_policy?.chains?.join(' ') || '')}" placeholder="按实际文件填写"></label></div>` : ''}
    ${Object.entries(model.inputs).map(([port, format]) => inputBlock(n, port, format)).join('')}
    <div class="upload-row"><label class="source-file-label">上传输入文件<input type="file" id="input-upload" accept=".pdb,.fa,.fasta,.faa,.a3m"></label></div><p class="field-hint" id="upload-info">文件保存后还需选择并保存输入绑定。仅检查格式、坐标／链和记录，不代表科学验证通过。</p>
    ${issuesHTML('登记前需要补充', check.missing)}${issuesHTML('执行准备（配置可登记不等于可执行）', check.preparation_issues, 'info')}
    <p id="node-error" class="inline-error" role="alert" hidden></p><div class="inline-actions spaced"><button type="submit" class="button primary">保存草稿</button><button type="button" class="button" id="node-import">导入此模型资料</button></div></form>`;
        root.querySelectorAll('[data-input-port]').forEach(block => {
            updateInputExtras(block, n.inputs[block.dataset.inputPort]);
            block.querySelector('.input-choice').addEventListener('change', () => updateInputExtras(block));
        });
        root.querySelector('form').addEventListener('input', () => {
            dirty = true;
            refreshDisabled();
        });
        root.querySelector('form').addEventListener('change', () => {
            dirty = true;
            refreshDisabled();
        });
        $('node-form').addEventListener('submit', e => {
            e.preventDefault();
            run(saveNode, 'node-error');
        });
        $('node-import').addEventListener('click', openImport);
        $('input-upload').addEventListener('change', uploadInput);
    }
    function inputBlock(n, port, format) {
        const ref = n.inputs[port];
        const options = [['', '暂不绑定']];
        if (ref?.kind === 'node_output') {
            options.push(['upstream', `上游 ${ref.node_id}.${ref.port}`]);
        }
        if (format === 'FASTA') {
            options.push(['sequence', '直接填写一条氨基酸序列']);
        }
        for (const file of files.filter(f => f.format === format))
            options.push([file.id, `${file.name} · ${file.format}`]);
        const value = ref?.kind === 'node_output' ? 'upstream' : ref?.kind === 'sequence' ? 'sequence' : ref?.file_id || '';
        return `<div class="input-block" data-input-port="${esc(port)}"><label class="field"><span class="field-label">输入 ${esc(port)} · ${esc(format)} ${port === 'msa' ? '（仅已有 MSA 模式需要）' : ''}</span><select class="input-choice">${choices(options, value)}</select></label><div class="input-extras"></div></div>`;
    }
    function updateInputExtras(block, original = null) {
        const choice = block.querySelector('.input-choice').value, extras = block.querySelector('.input-extras');
        extras.innerHTML = '';
        if (choice === 'upstream') {
            extras.innerHTML = `<label class="field"><span class="mini-label">选择上游输出记录</span><input class="record-id" value="${esc(original?.record_id || '')}" placeholder="例如 0 或 sample=1"></label><button type="button" class="text-button disconnect-port">断开此输入</button>`;
            extras.querySelector('button').addEventListener('click', () => {
                block.querySelector('.input-choice').value = '';
                extras.innerHTML = '';
                dirty = true;
                refreshDisabled();
            });
        }
        else if (choice === 'sequence') {
            extras.innerHTML = `<label class="field"><span class="mini-label">单条蛋白序列</span><textarea class="sequence-value" placeholder="仅序列，不含 FASTA 标题">${esc(original?.sequence || '')}</textarea></label>`;
        }
        else if (choice) {
            const file = files.find(f => f.id === choice);
            if (file?.format === 'FASTA') {
                extras.innerHTML = `<label class="field"><span class="mini-label">选择序列记录</span><select class="record-id">${choices([['', '请选择'], ...file.records.filter(r => r.selectable).map(r => [r.id, `${r.header} · ${r.sequence.length} aa`])], original?.record_id || '')}</select></label>`;
            }
            else if (file?.format === 'PDB') {
                extras.innerHTML = `<span class="field-hint">实际读取的链：${esc(Object.entries(file.chains).map(([c, length]) => `${c === ' ' ? '空格链' : c} (${length} aa)`).join('、'))}</span>`;
            }
            else if (file?.format === 'A3M') {
                extras.innerHTML = `<span class="field-hint">${file.records.length} 条记录 · ${file.records[0].aligned.length} 个对齐列；登记时检查查询序列一致。</span>`;
            }
        }
    }
    async function saveNode() {
        const n = current(), form = $('node-form'), data = new FormData(form), operations = [];
        const changes = {};
        for (const f of models[n.model_id].fields) {
            const value = f.type === 'number' ? Number(data.get(`param-${f.key}`)) : data.get(`param-${f.key}`);
            if (value !== n.params[f.key]) {
                changes[f.key] = value;
            }
        }
        if (Object.keys(changes).length) {
            operations.push({ type: 'update_params', node_id: n.id, changes });
        }
        if (data.get('node_label') !== n.label) {
            operations.push({ type: 'rename', node_id: n.id, name: data.get('node_label') });
        }
        if (n.model_id === 'proteinmpnn' && data.get('chain_mode')) {
            const mode = data.get('chain_mode');
            const policy = { mode, chains: mode === 'selected' ? String(data.get('chains')).trim().split(/\s+/).filter(Boolean) : [] };
            if (JSON.stringify(policy) !== JSON.stringify(n.design_chain_policy)) {
                operations.push({ type: 'set_chains', node_id: n.id, policy });
            }
        }
        for (const block of form.querySelectorAll('[data-input-port]')) {
            const port = block.dataset.inputPort, choice = block.querySelector('.input-choice').value;
            let value = null;
            if (choice === 'upstream') {
                value = { ...n.inputs[port] };
                const record = block.querySelector('.record-id').value.trim();
                if (record) {
                    value.record_id = record;
                }
                else {
                    delete value.record_id;
                }
            }
            else if (choice === 'sequence') {
                value = { kind: 'sequence', sequence: block.querySelector('.sequence-value').value };
            }
            else if (choice) {
                value = { kind: 'file', file_id: choice };
                const record = block.querySelector('.record-id');
                if (record) {
                    value.record_id = record.value || null;
                }
            }
            if (JSON.stringify(value) !== JSON.stringify(n.inputs[port] || null)) {
                operations.push({ type: 'set_input', node_id: n.id, port, value });
            }
        }
        if (!operations.length) {
            dirty = false;
            toast('配置没有变化');
            return;
        }
        const result = await post(endpoint('changes'), { expected_revision: Number(form.dataset.revision), operation_id: operationId(), operations });
        acceptState(result.state);
        toast('草稿已保存，请检查后确认登记');
    }
    async function uploadInput(e) {
        const file = e.target.files[0];
        if (!file) {
            return;
        }
        await run(async () => {
            const data = new FormData();
            data.append('file', file);
            const info = await api('/api/files', { method: 'POST', body: data });
            files.push(info);
            // Append the uploaded file to selectors without discarding unsaved fields.
            $('node-form').querySelectorAll('[data-input-port]').forEach(block => {
                const expected = models[current().model_id].inputs[block.dataset.inputPort];
                if (info.format === expected) {
                    const option = document.createElement('option');
                    option.value = info.id;
                    option.textContent = `${info.name} · ${info.format}`;
                    block.querySelector('.input-choice').append(option);
                }
            });
            $('upload-info').textContent = `已保存 ${info.name}。请在对应输入下拉框中选择它，再保存草稿。`;
            toast('输入文件已上传');
        });
    }
    function renderConversation() {
        const root = $('conversation');
        const parameterNames = Object.values(models).flatMap(model => model.fields.map(field => field.key));
        root.innerHTML = state.messages.length ? state.messages.map(m => {
            // The save result determines the status; model text was generated before
            // persistence and may describe a proposal rather than the finished action.
            const saved = !!m.summary?.length, proposed = !!m.proposal;
            const text = saved ? '这批修改已保存到草稿，尚未确认登记。' : proposed ? '请确认下方修改提案；尚未保存。' : m.text;
            return `<article class="chat-message ${m.role === 'user' ? 'user' : 'assistant'}"><div class="who">${m.role === 'user' ? '你' : '接入助手'}</div>
        <div class="message-body">${m.role === 'user' ? esc(text) : renderMessage(text, parameterNames)}</div>
        ${saved ? `<div class="chat-summary message-body">${renderMessage(m.summary.map(line => '- ' + line).join('\n'), parameterNames)}</div>` : ''}
        ${saved || proposed ? `<details><summary>查看模型的保存前说明</summary><div class="message-body spaced">${renderMessage(m.text, parameterNames)}</div></details>` : ''}
        ${proposed ? `<div class="chat-actions"><button class="button soft compact" data-apply-message="${esc(m.id)}">查看并确认修改</button></div>` : ''}
        ${m.usage ? `<div class="chat-meta">${esc(m.usage.model)} · ${m.usage.elapsed_seconds}s · ${m.tools?.length || 0} 次工具调用</div>` : ''}</article>`;
        }).join('') : '<div class="chat-greeting">我会根据模型说明协助配置。<br>你可以先导入资料，或直接提出修改。<br><br>试着问：<br>“温度 0.2 是什么意思？”<br>“把当前节点的序列数改为 16”<br><br>所有配置由服务端检查并保存；普通问答不修改参数。</div>';
        root.querySelectorAll('[data-apply-message]').forEach(b => b.addEventListener('click', () => run(async () => {
            const m = state.messages.find(m => m.id === b.dataset.applyMessage);
            if (!await confirmAction('确认应用以下提案？\n' + JSON.stringify(m.proposal.operations, null, 2))) {
                return;
            }
            const result = await post(endpoint('changes'), { ...m.proposal, confirmed: true });
            acceptState(result.state);
            toast('已确认并保存修改');
        })));
        root.scrollTop = root.scrollHeight;
    }
    async function sendMessage(e) {
        e.preventDefault();
        const message = $('chat-input').value.trim();
        if (!message || busy) {
            return;
        }
        if (dirty) {
            showError(new Error('请先保存或放弃表单修改，再让助手修改配置。'));
            return;
        }
        await run(async () => {
            $('agent-pending').hidden = false;
            try {
                const result = await post(endpoint('messages'), { expected_revision: state.draft.revision, operation_id: operationId(), message, selected_node_id: selected });
                acceptState(result.state, result.message.focus_node_id);
                $('chat-input').value = '';
            }
            finally {
                $('agent-pending').hidden = true;
            }
        });
    }
    function openImport() {
        if (!current()) {
            return;
        }
        if (dirty) {
            toast('请先保存表单修改，再导入资料');
            return;
        }
        $('import-model').value = current().model_id;
        preview = null;
        $('import-preview').hidden = true;
        $('import-error').hidden = true;
        refreshDisabled();
        $('import-dialog').showModal();
    }
    async function extractImport(e) {
        e.preventDefault();
        await run(async () => {
            preview = null;
            refreshDisabled();
            preview = await post(endpoint('import-preview'), { model_id: $('import-model').value, content: $('source-text').value, source: $('source-url').value || '用户资料（版本待核实）' });
            const category = { official_default: '资料中的默认值', example: '示例值', user: '用户指定', unknown: '未核实' };
            $('import-preview').innerHTML = `<h3 class="preview-title">识别候选 · 尚未覆盖配置</h3><p class="field-hint">${esc(preview.notes)}</p><table class="source-grid"><thead><tr><th>字段与值</th><th>分类与原文依据</th></tr></thead><tbody>${preview.accepted.map(p => `<tr><td><code>${esc(p.field)}</code><br>${esc(JSON.stringify(p.value))}</td><td>${esc(category[p.category])}<blockquote>${esc(p.quote)}</blockquote></td></tr>`).join('')}</tbody></table>${preview.errors.map(e => `<p class="preview-warning">${esc(e)}</p>`).join('')}<label class="field spaced"><span class="field-label">应用到</span><select id="preview-target">${choices([...state.draft.nodes.filter(n => n.model_id === preview.model_id).map(n => [n.id, n.label]), ['new', '新增此模型节点']], current()?.model_id === preview.model_id ? selected : 'new')}</select></label><p class="field-hint">确认前将展示当前值→候选值。存在非法／无依据字段时，需修正资料后重新识别。</p>`;
            $('import-preview').hidden = false;
        }, 'import-error');
    }
    async function applyPreview() {
        await run(async () => {
            let target = $('preview-target').value, operations = [];
            const existing = state.draft.nodes.find(n => n.id === target);
            const before = existing?.params || models[preview.model_id].sample_params;
            const diff = preview.accepted.map(p => `${p.field}: ${JSON.stringify(before[p.field])} → ${JSON.stringify(p.value)}`).join('\n');
            if (!await confirmAction('确认将候选应用到草稿？\n' + diff)) {
                return;
            }
            if (target === 'new') {
                target = 'n-' + crypto.randomUUID();
                operations.push({ type: 'add_node', node_id: target, model_id: preview.model_id, label: models[preview.model_id].role + ' · 资料导入' });
            }
            operations.push({ type: 'apply_import', node_id: target, preview_id: preview.id });
            const result = await post(endpoint('changes'), { expected_revision: state.draft.revision, operation_id: operationId(), operations, confirmed: true });
            acceptState(result.state, target);
            $('import-dialog').close();
            toast('资料候选已应用到草稿，尚未登记');
        }, 'import-error');
    }
    function scopeIds() {
        if ($('request-scope').value === 'workflow') {
            return state.draft.nodes.map(n => n.id);
        }
        if (!current()) {
            throw new Error('请先选择一个节点');
        }
        return [selected];
    }
    async function registerNodes(ids) {
        if (dirty) {
            throw new Error('请先保存表单修改，再确认登记');
        }
        if (!await confirmAction('确认登记以下节点的当前配置？\n' + ids.map(id => state.draft.nodes.find(n => n.id === id).label).join('、') + '\n登记不会执行科学任务。')) {
            return null;
        }
        const result = await post(endpoint('registrations'), { expected_revision: state.draft.revision, operation_id: operationId(), node_ids: ids });
        acceptState(result.state);
        toast('已确认登记当前配置');
        return result.registration;
    }
    function renderRequest() {
        if (!currentRequest) {
            return;
        }
        $('request-json').textContent = JSON.stringify(currentRequest, null, 2);
        $('request-info').textContent = currentRequest.stale ? '此请求已过期：工作流有后续修改，请重新检查、登记和生成。' : `基于登记快照 r${currentRequest.workflow_revision}，生成时工作流 r${currentRequest.generated_at_revision}。未提交；AiiDA 适配层未接通。`;
        $('request-issues').innerHTML = issuesHTML('不能提交的原因', currentRequest.blocking_issues, 'info');
    }
    async function loadSettings() {
        settings = await api('/api/settings/model');
        $('api-status').textContent = settings.has_key ? '已配置' : '未配置';
        $('sidebar-api').textContent = settings.has_key ? `${settings.model} · 已配置` : '尚未保存 API key';
    }
    async function openSettings() {
        await run(async () => {
            await loadSettings();
            $('model-name').value = settings.model;
            $('api-key').value = '';
            $('remove-key').checked = false;
            $('key-state').textContent = settings.has_key ? '已配置（不回显）' : '未配置';
            $('settings-result').textContent = '';
            $('settings-error').hidden = true;
            $('settings-dialog').showModal();
        });
    }
    async function saveSettings(e) {
        e.preventDefault();
        await run(async () => {
            await post('/api/settings/model', { model: $('model-name').value.trim(), api_key: $('api-key').value || null, remove_key: $('remove-key').checked });
            $('api-key').value = '';
            $('remove-key').checked = false;
            await loadSettings();
            $('key-state').textContent = settings.has_key ? '已配置（不回显）' : '未配置';
            $('settings-result').textContent = '设置已保存。可点击「测试已保存配置」验证真实连接。';
        }, 'settings-error');
    }
    async function openWorkflow(id) {
        const [next, available] = await Promise.all([api(`/api/workflows/${id}`), api('/api/files')]);
        files = available.files;
        currentRequest = null;
        selected = null;
        localStorage.setItem('ai4s-demo-workflow-id', id);
        acceptState(next);
    }
    function setupEvents() {
        root.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', () => $(b.dataset.close).close()));
        root.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', async () => {
            if (!busy && await discardOK()) {
                tab = b.dataset.tab;
                dirty = false;
                render();
            }
        }));
        $('top-settings').addEventListener('click', openSettings);
        $('settings-form').addEventListener('submit', saveSettings);
        $('test-api').addEventListener('click', () => run(async () => {
            if ($('api-key').value) {
                throw new Error('请先保存新密钥，再测试。');
            }
            $('settings-result').textContent = '正在验证真实 DeepSeek 连接与结构化工具返回…';
            const result = await post('/api/settings/model/test');
            $('settings-result').textContent = `${result.message} · ${result.usage.model} · ${result.usage.elapsed_seconds}s`;
        }, 'settings-error'));
        $('refresh-button').addEventListener('click', () => run(async () => {
            if (await discardOK()) {
                await openWorkflow(state.draft.id);
            }
        }));
        $('export-button').addEventListener('click', () => download(`${state.draft.id}-draft.json`, { status: 'draft', ...state.draft }));
        $('undo-button').addEventListener('click', () => run(async () => {
            if (!await discardOK()) {
                return;
            }
            const result = await post(endpoint('undo'), { expected_revision: state.draft.revision, operation_id: operationId() });
            acceptState(result.state);
            toast('已撤销最近一次修改');
        }));
        $('rename-button').addEventListener('click', () => run(async () => {
            if (!await discardOK()) {
                return;
            }
            const name = await confirmAction('修改工作流名称', state.draft.name);
            if (!name?.trim()) {
                return;
            }
            const result = await post(endpoint('changes'), { expected_revision: state.draft.revision, operation_id: operationId(), operations: [{ type: 'rename', name: name.trim() }] });
            acceptState(result.state);
        }));
        $('delete-button').addEventListener('click', () => run(async () => {
            if (!await discardOK()) {
                return;
            }
            const links = state.draft.edges.filter(e => e.source === selected || e.target === selected);
            if (!await confirmAction(`删除「${current().label}」及相关 ${links.length} 条连接？此操作可撤销。`)) {
                return;
            }
            const result = await post(endpoint('changes'), { expected_revision: state.draft.revision, operation_id: operationId(), operations: [{ type: 'remove_node', node_id: selected }], confirmed: true });
            acceptState(result.state);
            toast('步骤已删除');
        }));
        $('add-button').addEventListener('click', () => {
            $('add-label').value = models[$('add-model').value].role + ' ' + (state.draft.nodes.length + 1);
            $('add-dialog').showModal();
        });
        $('add-model').addEventListener('change', () => $('add-label').value = models[$('add-model').value].role + ' ' + (state.draft.nodes.length + 1));
        $('add-form').addEventListener('submit', e => {
            e.preventDefault();
            run(async () => {
                if (!await discardOK()) {
                    return;
                }
                const id = 'n-' + crypto.randomUUID();
                const result = await post(endpoint('changes'), { expected_revision: state.draft.revision, operation_id: operationId(), operations: [{ type: 'add_node', node_id: id, model_id: $('add-model').value, label: $('add-label').value }] });
                acceptState(result.state, id);
                $('add-dialog').close();
            });
        });
        function connectionPorts() {
            const source = state.draft.nodes.find(n => n.id === $('connect-source').value);
            const target = state.draft.nodes.find(n => n.id === $('connect-target').value);
            const kind = $('connect-kind').value;
            $('connect-source-port').innerHTML = choices(Object.entries(models[source?.model_id]?.outputs || {}).map(([port, format]) => [port, `${port} · ${format}`]));
            $('connect-target-port').innerHTML = choices(Object.entries(models[target?.model_id]?.inputs || {}).map(([port, format]) => [port, `${port} · ${format}`]));
            $('target-port-field').hidden = kind !== 'data';
            $('record-field').hidden = kind !== 'data';
            $('relation-label-field').hidden = kind === 'data';
        }
        for (const id of ['connect-kind', 'connect-source', 'connect-target'])
            $(id).addEventListener('change', connectionPorts);
        $('connect-button').addEventListener('click', () => {
            const options = state.draft.nodes.map(n => [n.id, `${models[n.model_id].name} · ${n.label}`]);
            $('connect-source').innerHTML = choices(options, selected);
            $('connect-target').innerHTML = choices(options, state.draft.nodes.find(n => n.id !== selected)?.id);
            $('connect-kind').value = 'data';
            connectionPorts();
            $('connect-record').value = '';
            $('connect-error').hidden = true;
            $('connect-dialog').showModal();
        });
        $('connect-form').addEventListener('submit', e => {
            e.preventDefault();
            run(async () => {
                if (!await discardOK()) {
                    return;
                }
                const source = $('connect-source').value, target = $('connect-target').value;
                if (!source || !target) {
                    throw new Error('请先添加节点');
                }
                const kind = $('connect-kind').value;
                const op = kind === 'data' ? { type: 'connect', source, source_port: $('connect-source-port').value, target, target_port: $('connect-target-port').value, record_id: $('connect-record').value || null }
                    : { type: 'add_relation', relation_id: 'rel-' + crypto.randomUUID(), source, source_port: $('connect-source-port').value, target, kind, label: $('relation-label').value };
                const result = await post(endpoint('changes'), { expected_revision: state.draft.revision, operation_id: operationId(), operations: [op] });
                acceptState(result.state, target);
                $('connect-dialog').close();
            }, 'connect-error');
        });
        for (const [id, layout] of [['layout-tree', 'layered'], ['layout-circle', 'circle']])
            $(id).addEventListener('click', async () => {
                try {
                    await saveGraphOperations([{ type: 'set_layout', layout }]);
                    graph.fit();
                }
                catch (error) {
                    showError(error);
                }
            });
        function showGraphDocument() {
            $('graph-json').textContent = JSON.stringify(graph.document(), null, 2);
            $('graph-relations').innerHTML = (state.draft.visual?.relations || []).map(r => `<div class="graph-relation-row"><span>${esc(r.source)}.${esc(r.source_port)} → ${esc(r.target)} · ${esc(r.label)}</span><button class="button compact" data-remove-relation="${esc(r.id)}">删除关系</button></div>`).join('');
        }
        $('graph-json-button').addEventListener('click', () => {
            showGraphDocument();
            $('graph-operations-error').hidden = true;
            $('graph-operations').value = JSON.stringify([{ type: 'set_layout', layout: 'layered' }], null, 2);
            $('graph-json-dialog').showModal();
        });
        $('download-graph').addEventListener('click', () => download(state.draft.id + '-graph.json', graph.document()));
        $('graph-relations').addEventListener('click', async (e) => {
            const id = e.target.closest('[data-remove-relation]')?.dataset.removeRelation;
            if (!id || !await confirmAction('删除这条设计关系？不影响已有科学输入绑定。')) {
                return;
            }
            try {
                await saveGraphOperations([{ type: 'remove_relation', relation_id: id }]);
                showGraphDocument();
            }
            catch (error) {
                showError(error, 'graph-operations-error');
            }
        });
        $('apply-graph-operations').addEventListener('click', () => run(async () => {
            if (dirty) {
                throw new Error('请先保存参数表单');
            }
            let operations;
            try {
                operations = JSON.parse($('graph-operations').value);
            }
            catch {
                throw new Error('操作 JSON 格式不正确');
            }
            const summary = await post(endpoint('changes/preview'), { expected_revision: state.draft.revision, operation_id: operationId(), operations });
            if (!await confirmAction('以下操作将按当前版本一次性保存：\n' + summary.summary.join('\n'))) {
                return;
            }
            const result = await post(endpoint('changes'), { expected_revision: state.draft.revision, operation_id: operationId(), operations, confirmed: true });
            acceptState(result.state);
            showGraphDocument();
            graph.fit();
        }, 'graph-operations-error'));
        $('apply-workflow').addEventListener('click', () => run(async () => {
            if (dirty) {
                throw new Error('请先保存当前参数表单，再应用到接入草稿。');
            }
            if (!await confirmAction('将当前 AI 草稿的步骤、参数和连接应用到接入表单？已有步骤会替换，已填项目信息保留。服务器路径、运行环境和调用指令仍需人工核对。')) {
                return;
            }
            await onApply({ draft: structuredClone(state.draft), models: structuredClone(models) });
        }));
        $('chat-form').addEventListener('submit', sendMessage);
        $('chat-input').addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
                e.preventDefault();
                $('chat-form').requestSubmit();
            }
        });
        $('import-button').addEventListener('click', openImport);
        $('import-form').addEventListener('submit', extractImport);
        $('apply-preview').addEventListener('click', applyPreview);
        $('load-sample').addEventListener('click', () => {
            const m = models[$('import-model').value];
            $('source-text').value = `模型：${m.name}\n以下为本项目调用示例值，不表示官方默认值。\n${JSON.stringify(m.sample_params, null, 2)}`;
            $('source-url').value = m.source_url + '（参数映射依据；数值为项目示例）';
            invalidatePreview();
        });
        const invalidatePreview = () => {
            preview = null;
            $('import-preview').hidden = true;
            refreshDisabled();
        };
        for (const id of ['source-text', 'source-url', 'import-model'])
            $(id).addEventListener('input', invalidatePreview);
        $('source-file').addEventListener('change', e => run(async () => {
            const file = e.target.files[0];
            if (!file) {
                return;
            }
            if (file.size > 160000 || !/\.(md|txt|json)$/i.test(file.name)) {
                throw new Error('请选择小于 160 KB 的 .md/.txt/.json 文本');
            }
            const text = await file.text();
            if (text.length > 40000) {
                throw new Error('资料上限 40000 字符');
            }
            $('source-text').value = text;
            $('source-file-name').textContent = `${file.name} · 识别时发送给 DeepSeek`;
            invalidatePreview();
        }, 'import-error'));
        $('register-button').addEventListener('click', () => run(() => registerNodes([selected])));
        $('request-button').addEventListener('click', () => {
            $('request-error').hidden = true;
            $('request-dialog').showModal();
            renderRequest();
        });
        $('register-scope').addEventListener('click', () => run(() => registerNodes(scopeIds()), 'request-error'));
        $('generate-request').addEventListener('click', () => run(async () => {
            if (dirty) {
                throw new Error('请先保存表单修改');
            }
            const ids = scopeIds();
            const reg = [...state.registrations].reverse().find(r => r.current && r.node_ids.length === ids.length && ids.every(id => r.node_ids.includes(id)));
            if (!reg) {
                throw new Error('该范围尚未确认登记，或相关配置已变化。请先确认登记。');
            }
            const result = await post(endpoint('requests'), { registration_id: reg.id });
            currentRequest = result.request;
            acceptState(result.state);
            renderRequest();
        }, 'request-error'));
        $('download-request').addEventListener('click', () => {
            if (currentRequest && !currentRequest.stale) {
                download(currentRequest.id + '.json', currentRequest);
            }
        });
        $('workflow-button').addEventListener('click', () => run(async () => {
            const list = await api('/api/workflows');
            $('workflow-list').innerHTML = choices(list.workflows.map(w => [w.id, `${w.name} · r${w.revision}`]), state.draft.id);
            $('workflow-dialog').showModal();
        }));
        $('open-workflow').addEventListener('click', () => run(async () => {
            if (await discardOK()) {
                await openWorkflow($('workflow-list').value);
                $('workflow-dialog').close();
            }
        }));
        $('new-workflow-form').addEventListener('submit', e => {
            e.preventDefault();
            run(async () => {
                if (!await discardOK()) {
                    return;
                }
                const created = await post('/api/workflows', { name: $('new-name').value, template: $('new-template').value });
                await openWorkflow(created.draft.id);
                $('workflow-dialog').close();
            });
        });
        window.addEventListener('resize', () => state && drawWires(state), { signal: lifecycle.signal });
        window.addEventListener('beforeunload', e => {
            if (dirty) {
                e.preventDefault();
                e.returnValue = '';
            }
        }, { signal: lifecycle.signal });
    }
    async function initialize() {
        const catalog = await api('/api/models');
        models = Object.fromEntries(catalog.models.map(m => [m.id, m]));
        const modelOptions = Object.values(models).map(m => [m.id, `${m.name} · ${m.role}`]);
        $('add-model').innerHTML = choices(modelOptions, 'proteinmpnn');
        $('import-model').innerHTML = choices(modelOptions, 'proteinmpnn');
        setupEvents();
        await loadSettings();
        const list = await api('/api/workflows');
        const saved = localStorage.getItem('ai4s-demo-workflow-id');
        const id = list.workflows.some(w => w.id === saved) ? saved : list.workflows[0]?.id;
        if (id) {
            await openWorkflow(id);
        }
        else {
            const created = await post('/api/workflows', {});
            await openWorkflow(created.draft.id);
        }
    }
    try {
        await initialize();
    }
    catch (error) {
        lifecycle.abort();
        destroy();
        throw error;
    }
    return {
        redraw() {
            if (state) {
                requestAnimationFrame(() => drawWires(state));
            }
        },
        pause() {
            root.querySelectorAll('dialog[open]').forEach(dialog => {
                dialog.dispatchEvent(new Event('cancel', { cancelable: true }));
                if (dialog.open) {
                    dialog.close();
                }
            });
            graph.pause();
        },
        destroy() {
            lifecycle.abort();
            destroy();
            clearTimeout(toastTimer);
        },
    };
}
