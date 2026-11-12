import { api, post, operationId, escapeHTML as esc, download } from "./api.js";
import { renderMessage } from "./message.js";

export async function mountDeclaration(container) {
  const signal = new AbortController();
  const $ = (id) => container.querySelector("#dp-" + id);
  let state,
    reference,
    busy = false,
    dirty = false,
    settings;
  let activeSection = "inputs";
  const endpoint = (suffix) =>
    "/api/declaration-drafts/" + state.id + "/" + suffix;
  container.innerHTML = `
    <section class="declaration-workspace" aria-label="ProteinMPNN 任务声明登记">
      <header class="declaration-heading"><div><h2>ProteinMPNN 任务登记</h2><p>定义模型的输入、参数和输出，供实验页面与引擎使用。</p></div><div class="declaration-actions"><button class="button" id="dp-assistant-toggle" aria-expanded="false" aria-controls="dp-assistant">AI 助手</button><button class="button primary" id="dp-export" type="button">校验并导出</button></div></header>
      <div class="declaration-draftbar"><label><span class="sr-only">当前声明草稿</span><select id="dp-drafts" aria-label="当前声明草稿"></select></label><span id="dp-revision" class="declaration-state"></span><details class="declaration-draft-menu"><summary>草稿操作</summary><div><button class="button" id="dp-reload">读取保存版本</button><button class="button" id="dp-new">新建空白声明</button><button class="button" id="dp-complete">从完整定义新建</button></div></details></div>
      <p class="declaration-notice">登记任务接口，不会启动计算。导出后需交给引擎部署。</p>
      <div class="inline-error" id="dp-error" role="alert" hidden></div><p class="inline-result" id="dp-status" role="status" aria-live="polite"></p>
      <div class="declaration-columns" id="dp-columns"><div class="declaration-main">
        <section class="declaration-map panel" aria-labelledby="dp-map-title"><div class="panel-heading"><div><h3 id="dp-map-title">任务接口</h3><p>点击节点查看定义</p></div><span class="declaration-caption">已保存的定义 · 非运行状态</span></div><div id="dp-flow"></div><div class="declaration-validation"><div id="dp-issues" role="status"></div><button class="button soft" id="dp-restore">补齐缺项</button></div></section>
        <section class="panel declaration-editor" aria-label="任务声明定义">
          <nav class="declaration-tabs" aria-label="查看任务定义">${[
            ["inputs", "输入"],
            ["parameters", "参数"],
            ["outputs", "输出"],
            ["advanced", "高级"],
          ]
            .map(
              ([key, label]) =>
                `<button type="button" class="declaration-tab" data-section="${key}" aria-controls="dp-section-${key}" aria-pressed="${key === "inputs"}">${label}</button>`,
            )
            .join("")}</nav>
          <div class="declaration-body"><form id="dp-form" novalidate>
            <section id="dp-section-inputs" data-detail-section="inputs"><div class="declaration-section-heading"><h3>需要什么输入</h3><p>这里定义文件端口；具体文件在创建实验时选择。</p></div><div id="dp-inputs"></div></section>
            <section id="dp-section-parameters" data-detail-section="parameters" hidden><div class="declaration-section-heading"><h3>参数规则</h3><p>展开查看类型、必填性和默认值。这里编辑规则，实验时再填写具体值。</p></div><div id="dp-parameters"></div><details class="declaration-disclosure"><summary>试填联调参数</summary><p class="field-hint">以下是示例值，不是默认值，也不会启动实验。</p><div id="dp-example"></div></details></section>
            <section id="dp-section-outputs" data-detail-section="outputs" hidden><div class="declaration-section-heading"><h3>会产生什么输出</h3><p>这是产物定义，文件和结果节点将在实际计算后产生。</p></div><div id="dp-outputs"></div></section>
            <section id="dp-section-advanced" data-detail-section="advanced" hidden><div class="declaration-section-heading"><h3>任务信息</h3><p>维护接口版本与来源，保持已发布定义不变。</p></div><div class="fields"><label class="field"><span>任务名称</span><input id="dp-name" required maxlength="200"></label><label class="field"><span>接口版本</span><input id="dp-version" required pattern="[1-9][0-9]{0,7}"></label></div><dl class="declaration-metadata"><div><dt>任务标识</dt><dd><code>proteinmpnn</code></dd></div><div><dt>声明格式</dt><dd><code>ai4s-task-declaration-1</code></dd></div><div><dt>适用模型版本</dt><dd><code id="dp-release"></code></dd></div></dl>
              <details class="declaration-disclosure"><summary>完整 JSON 与高级编辑</summary><p class="field-hint">JSON 编辑单独校验，核对差异后确认写入。</p><textarea id="dp-json" aria-label="完整声明 JSON" spellcheck="false"></textarea><button class="button" id="dp-json-preview" type="button">校验 JSON 修改</button></details>
              <details class="declaration-disclosure"><summary>来源与执行映射</summary><div id="dp-source"></div><pre id="dp-execution" class="json-code"></pre></details>
              <details class="declaration-disclosure"><summary>确认记录</summary><div id="dp-events"></div></details>
            </section>
            <div class="declaration-savebar" id="dp-savebar" hidden><span>有尚未确认的表单编辑</span><button class="button primary" type="submit">预览修改</button></div>
          </form></div>
        </section>
      </div>
      <aside class="panel declaration-assistant" id="dp-assistant" aria-label="任务声明助手" hidden><div class="panel-heading"><div><h3>登记助手</h3><span id="dp-api" class="declaration-caption"></span></div><button class="button" id="dp-assistant-close" type="button">收起</button></div><button class="declaration-settings" id="dp-settings" type="button">模型 API 设置</button><div class="declaration-chat" id="dp-chat" role="log" aria-label="任务声明对话"></div>
        <p id="dp-pending" role="status" hidden>正在核对真实接口并生成回复…</p>
        <details class="declaration-disclosure declaration-material"><summary>参考资料</summary><p class="field-hint">粘贴或读取资料，由助手核对并提出修改。</p><input type="file" id="dp-source-file" accept=".md,.txt,.json" aria-label="读取模型参考资料"><textarea id="dp-material" aria-label="模型参考资料" maxlength="30000" placeholder="粘贴模型文档或参数说明"></textarea></details>
        <form id="dp-chat-form" class="declaration-composer"><label class="sr-only" for="dp-message">向任务声明助手提问</label><textarea id="dp-message" maxlength="8000" placeholder="提问，或描述希望修改的内容…"></textarea><button class="button primary" type="submit">发送</button></form><p class="field-hint declaration-footnote">普通问答不改声明；修改需确认后保存。</p>
      </aside></div>
      <dialog class="modal" id="dp-confirm" aria-labelledby="dp-confirm-title"><div class="modal-head"><h2 id="dp-confirm-title">核对声明修改</h2></div><div class="modal-body"><p>以下修改尚未写入。确认后整批保存到编辑草稿。</p><p id="dp-evidence" class="field-hint"></p><div id="dp-diff"></div></div><div class="modal-foot"><button class="button" id="dp-cancel">取消修改</button><button class="button primary" id="dp-apply">确认并写入</button></div></dialog>
      <dialog class="modal small-modal" id="dp-discard" aria-labelledby="dp-discard-title"><div class="modal-head"><h2 id="dp-discard-title">读取保存版本？</h2></div><div class="modal-body"><p>尚未确认的表单和 JSON 编辑会被放弃，已保存的声明保持不变。</p></div><div class="modal-foot"><button class="button" id="dp-discard-cancel">继续编辑</button><button class="button primary" id="dp-discard-apply">放弃编辑并读取</button></div></dialog>
      <dialog class="modal small-modal" id="dp-settings-dialog" aria-labelledby="dp-settings-title"><div class="modal-head"><h2 id="dp-settings-title">模型 API 设置</h2><button class="button" id="dp-settings-close">关闭</button></div><form id="dp-settings-form"><div class="modal-body"><label class="field"><span>DeepSeek 模型名</span><input id="dp-model" required></label><label class="field"><span>API key（仅存服务端，留空保留）</span><input type="password" id="dp-key" autocomplete="off"></label><p id="dp-key-info"></p><p id="dp-settings-error" class="inline-error" role="alert"></p></div><div class="modal-foot"><button class="button primary">保存 API 设置</button></div></form></dialog>
    </section>`;
  const listen = (element, event, fn) =>
    element.addEventListener(event, fn, { signal: signal.signal });
  function error(e) {
    $("error").innerHTML =
      `<strong>${esc(e.message)}</strong>${Array.isArray(e.details) ? `<ul>${e.details.map((item) => `<li><code>${esc(item.path)}</code>：${esc(item.message)}</li>`).join("")}</ul>` : ""}`;
    $("error").hidden = false;
    $("error").scrollIntoView({ block: "center" });
  }
  function disabled(value) {
    busy = value;
    container
      .querySelectorAll("button, input, select, textarea")
      .forEach((b) => (b.disabled = value));
    $("message").disabled = value;
    container.setAttribute("aria-busy", String(value));
  }
  async function run(fn) {
    if (busy) return;
    $("error").hidden = true;
    disabled(true);
    try {
      await fn();
    } catch (e) {
      error(e);
    } finally {
      disabled(false);
    }
  }
  function requireSaved() {
    if (dirty)
      throw new Error("有尚未确认的编辑，请先预览并确认，或读取保存版本。");
  }
  const json = (value) => JSON.stringify(value, null, 2);
  const typeLabels = {
    string: "文本",
    integer: "整数",
    number: "数值",
    boolean: "开关",
  };
  function fieldsTable(ports) {
    const rows = Object.entries(ports || {});
    return rows.length
      ? `<div class="declaration-port-list">${rows.map(([port, p]) => `<article class="declaration-port"><div class="declaration-port-title"><strong>${esc(p.label || p.filename || port)}</strong><span class="declaration-tag">${esc(p.format || p.aiida_type)}</span><span class="declaration-caption">${p.required_if ? "保存概率时必需" : p.required ? "必需" : "可选"}${p.owner ? " · " + (p.owner === "filter" ? "筛选阶段" : "推理阶段") : ""}</span></div><code>${esc(port)}</code><p>${esc(p.description || p.label || "")}</p></article>`).join("")}</div>`
      : '<p class="declaration-missing">端口尚未补齐，可点击“补齐缺项”。</p>';
  }
  function selectSection(section) {
    activeSection = section;
    container.querySelectorAll("[data-detail-section]").forEach((panel) => {
      panel.hidden = panel.dataset.detailSection !== section;
    });
    container.querySelectorAll("[data-section]").forEach((button) => {
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.section === section),
      );
    });
  }
  function toggleAssistant(open) {
    $("assistant").hidden = !open;
    $("columns").classList.toggle("with-assistant", open);
    $("assistant-toggle").setAttribute("aria-expanded", String(open));
    if (open) $("message").focus();
  }
  function renderFlow(d) {
    const inputs = Object.entries(d.inputs || {});
    const inferenceOutputs = Object.entries(d.outputs || {}).filter(
      ([, p]) => p.owner === "inference",
    );
    const filterOutputs = Object.entries(d.outputs || {}).filter(
      ([, p]) => p.owner === "filter",
    );
    const node = (section, title, caption, entries, kind) =>
      `<button type="button" class="declaration-node ${kind}" data-section="${section}" aria-controls="dp-section-${section}" aria-pressed="false"><span class="declaration-node-kind">${caption}</span><strong>${esc(title)}</strong><span class="declaration-node-ports">${entries.length ? entries.map(([key, p]) => `<span><i aria-hidden="true"></i>${esc(p.filename || key)}${p.format && !p.filename ? " · " + esc(p.format) : ""}${p.required_if ? " · 按需" : ""}</span>`).join("") : '<span class="declaration-caption">待补齐定义</span>'}</span></button>`;
    $("flow").innerHTML =
      `<div class="declaration-flow">${node("inputs", "输入骨架", "INPUT", inputs, "input-node")}<span class="declaration-connector" aria-label="作为模型输入">→</span><button type="button" class="declaration-node model-node" data-section="parameters" aria-controls="dp-section-parameters" aria-pressed="false"><span class="declaration-node-kind">序列设计模型</span><strong>ProteinMPNN</strong><span class="declaration-model-description">根据骨架设计氨基酸序列</span><span class="declaration-model-params">${Object.keys(d.parameters?.inference || {}).length} 项推理参数</span></button><span class="declaration-connector" aria-label="声明的模型输出">→</span>${node("outputs", "模型输出", "OUTPUT", inferenceOutputs, "output-node")}</div>${d.workflow_modes?.includes("mpnn_filter") ? `<div class="declaration-filter-branch"><span class="declaration-branch-line" aria-hidden="true">↳</span><button type="button" class="declaration-filter-node" data-section="parameters" aria-controls="dp-section-parameters" aria-pressed="false"><strong>可选：序列筛选</strong><span>${Object.keys(d.parameters?.filter || {}).length} 项筛选参数 · 推理后处理</span></button><span class="declaration-connector" aria-hidden="true">→</span><button type="button" class="declaration-filter-output" data-section="outputs" aria-controls="dp-section-outputs" aria-pressed="false"><strong>筛选记录与报告</strong><span>${filterOutputs.length} 项输出定义</span></button></div>` : ""}`;
  }
  function inputValue(field) {
    const value = field.type === "checkbox" ? field.checked : field.value;
    if (field.dataset.valueType === "boolean") return Boolean(value);
    if (
      field.dataset.valueType === "integer" ||
      field.dataset.valueType === "number"
    ) {
      if (value === "") return undefined;
      const number = Number(value);
      if (!Number.isFinite(number)) throw new Error("数值必须为有限数");
      return number;
    }
    return value;
  }
  function render() {
    const d = state.declaration;
    $("name").value = d.name || "";
    $("version").value = d.version || "";
    $("release").textContent = d.model?.release || "缺少版本";
    $("revision").textContent = "草稿 r" + state.revision + " · 未部署";
    renderFlow(d);
    selectSection(activeSection);
    $("savebar").hidden = true;
    $("restore").hidden = !state.issues.length;
    $("inputs").innerHTML = fieldsTable(d.inputs);
    $("outputs").innerHTML = fieldsTable(d.outputs);
    $("issues").innerHTML = state.issues.length
      ? `<details class="check-list"><summary>导出前需处理 ${state.issues.length} 项 · 查看详情</summary><ul>${state.issues.map((i) => `<li><code>${esc(i.path)}</code>：${esc(i.message)}</li>`).join("")}</ul></details>`
      : '<p class="declaration-valid">定义完整 <span>· 导出时校验发布版本</span></p>';
    $("parameters").innerHTML = Object.entries(reference.parameters)
      .map(
        ([group, fields]) =>
          `<h4>${group === "inference" ? "推理参数" : "筛选参数 · 仅推理＋筛选流程"}</h4><div class="declaration-parameter-list">${Object.entries(
            fields,
          )
            .map(([key, source]) => {
              const f = d.parameters?.[group]?.[key];
              if (!f)
                return `<div class="declaration-missing"><code>${esc(key)}</code> · 缺少定义</div>`;
              const constraints = [
                f.minimum !== undefined ? "≥ " + f.minimum : "",
                f.maximum !== undefined ? "≤ " + f.maximum : "",
                f.exclusiveMinimum !== undefined
                  ? "> " + f.exclusiveMinimum
                  : "",
                f.minLength ? "非空文字" : "",
                f.enum ? "可选：" + f.enum.join(" / ") : "",
              ]
                .filter(Boolean)
                .join("；");
              return `<details class="declaration-parameter" data-definition="${group}.${key}"><summary><span class="declaration-parameter-name"><strong>${esc(f.label || key)}</strong><code>${esc(key)}</code></span><span class="declaration-parameter-meta">${esc(typeLabels[f.type] || f.type)} · ${f.required ? "必填" : "可选"}${f.default !== undefined ? " · 默认 " + esc(f.default) : ""}</span></summary><div class="declaration-parameter-body"><div class="fields"><label class="field"><span>显示名</span><input data-meta="label" aria-label="${group}.${key} 显示名" value="${esc(f.label)}"></label><label class="field"><span>类型</span><select data-meta="type" aria-label="${group}.${key} 类型">${Object.entries(
                typeLabels,
              )
                .map(
                  ([t, label]) =>
                    `<option value="${t}" ${f.type === t ? "selected" : ""}>${label} · ${t}</option>`,
                )
                .join(
                  "",
                )}</select></label><label class="field"><span>后端默认值</span>${source.type === "boolean" ? `<select data-meta="default" data-value-type="boolean" aria-label="${group}.${key} 默认值"><option value="true" ${f.default === true ? "selected" : ""}>true</option><option value="false" ${f.default === false ? "selected" : ""}>false</option></select>` : `<input data-meta="default" data-value-type="${source.type}" aria-label="${group}.${key} 默认值" placeholder="无默认值" value="${esc(f.default ?? "")}">`}</label><label class="declaration-checkbox"><input type="checkbox" data-meta="required" aria-label="${group}.${key} 必填" ${f.required ? "checked" : ""}> 实验请求必填</label></div><label class="field"><span>说明</span><textarea data-meta="description" aria-label="${group}.${key} 说明">${esc(f.description)}</textarea></label>${constraints ? `<p class="field-hint">约束：${esc(constraints)}</p>` : ""}</div></details>`;
            })
            .join("")}</div>`,
      )
      .join("");
    const example = d.example;
    $("example").innerHTML = example
      ? `<label class="field"><span>示例流程</span><select id="dp-example-mode"><option value="single" ${example.workflow === "single" ? "selected" : ""}>single · 单任务</option><option value="mpnn_filter" ${example.workflow === "mpnn_filter" ? "selected" : ""}>mpnn_filter · 推理＋筛选</option></select></label><div class="fields">${Object.entries(
          example.params || {},
        )
          .flatMap(([group, params]) =>
            Object.entries(params).map(([key, v]) => {
              const type = reference.parameters[group]?.[key]?.type;
              return `<label class="field"><span>${esc(group + "." + key)}</span>${type === "boolean" ? `<select data-example="${group}.${key}" data-value-type="boolean"><option value="true" ${v === true ? "selected" : ""}>true</option><option value="false" ${v === false ? "selected" : ""}>false</option></select>` : `<input data-example="${group}.${key}" data-value-type="${esc(type)}" value="${esc(v)}">`}</label>`;
            }),
          )
          .join("")}</div>`
      : "<p>没有联调示例，可通过完整 JSON 或助手补齐。</p>";
    $("json").value = json(d);
    $("execution").textContent = json(d.execution);
    $("source").innerHTML =
      `<p>依据修订：<code>${esc(d.source_reference?.revision)}</code></p><ul>${(d.source_reference?.paths || []).map((path) => `<li><a href="https://github.com/QUHONGYE-gif/ai4s-workspace/blob/${encodeURIComponent(d.source_reference.revision)}/${path.split("/").map(encodeURIComponent).join("/")}" target="_blank" rel="noopener noreferrer">${esc(path)}</a></li>`).join("")}</ul>`;
    $("events").innerHTML =
      state.events
        .slice(-10)
        .reverse()
        .map(
          (event) =>
            `<p>${esc(event.time)} · ${event.status === "applied" ? "已确认写入" : "已取消"} · r${event.revision}</p>`,
        )
        .join("") || "<p>尚无确认记录。</p>";
    $("chat").innerHTML =
      state.messages
        .map(
          (m) =>
            `<article class="chat-message ${m.role === "user" ? "user" : "assistant"}"><div class="who">${m.role === "user" ? "你" : "登记助手"}</div><div class="message-body">${m.role === "user" ? esc(m.text) : renderMessage(m.text, Object.keys(reference.parameters.inference))}</div>${m.proposal ? `<p>${m.proposal.status === "pending" ? "提案待确认，尚未写入" : m.proposal.status === "applied" ? "已确认写入" : "已取消"}</p>${m.proposal.status === "pending" ? `<button class="button soft" data-proposal="${esc(m.proposal.id)}">查看修改并确认</button>` : ""}` : ""}${m.usage ? `<p class="chat-meta">${esc(m.usage.model)} · ${m.usage.elapsed_seconds.toFixed(2)}s</p>` : ""}</article>`,
        )
        .join("") ||
      '<p class="declaration-greeting">可以问“为什么种子不能为0”，或要求“根据真实接口补齐缺少的输入、参数和输出”。助手只提出修改，确认后才保存。</p>';
    $("chat").scrollTop = $("chat").scrollHeight;
    dirty = false;
  }
  async function refreshList() {
    const list = await api("/api/declaration-drafts");
    $("drafts").innerHTML = list.drafts
      .map(
        (d) =>
          `<option value="${esc(d.id)}" ${d.id === state?.id ? "selected" : ""}>${esc(d.name)} · r${d.revision} · ${esc(d.id.slice(-6))}</option>`,
      )
      .join("");
  }
  async function accept(value) {
    state = value;
    localStorage.setItem("ai4s-declaration-draft-id", state.id);
    render();
    await refreshList();
  }
  function formDocument() {
    const d = structuredClone(state.declaration);
    d.name = $("name").value;
    d.version = $("version").value;
    container.querySelectorAll("[data-definition]").forEach((row) => {
      const [group, key] = row.dataset.definition.split(".");
      const f = d.parameters[group][key];
      row.querySelectorAll("[data-meta]").forEach((input) => {
        const key = input.dataset.meta;
        if (key === "default") {
          const value =
            input.tagName === "SELECT"
              ? input.value === "true"
              : inputValue(input);
          if (value === undefined || value === "") delete f.default;
          else f.default = value;
        } else f[key] = input.type === "checkbox" ? input.checked : input.value;
      });
    });
    container.querySelectorAll("[data-example]").forEach((input) => {
      const [group, key] = input.dataset.example.split(".");
      const value =
        input.tagName === "SELECT" ? input.value === "true" : inputValue(input);
      if (value === undefined || value === "")
        delete d.example.params[group][key];
      else d.example.params[group][key] = value;
    });
    if ($("example-mode")) {
      d.example.workflow = $("example-mode").value;
      if (d.example.workflow === "single") delete d.example.params.filter;
      else
        d.example.params.filter ??= structuredClone(
          reference.example.params.filter,
        );
    }
    return d;
  }
  function showProposal(proposal) {
    $("evidence").textContent =
      "来源：" +
      proposal.origin +
      "；真实接口依据：" +
      (proposal.evidence?.source_revision ||
        reference.source_reference.revision) +
      (proposal.evidence?.edits?.some((e) => e.quote)
        ? "；资料引文：" +
          proposal.evidence.edits
            .filter((e) => e.quote)
            .map((e) => e.quote)
            .join("；")
        : "");
    $("diff").innerHTML = proposal.diff
      .map(
        (change) =>
          `<div class="declaration-diff"><strong>${esc(change.path)}</strong><div><span>旧值</span><pre>${esc(json(change.old))}</pre></div><div><span>新值</span><pre>${esc(json(change.new))}</pre></div></div>`,
      )
      .join("");
    const dialog = $("confirm");
    dialog.showModal();
    const finish = (cancel) =>
      run(async () => {
        const updated = await post(endpoint(cancel ? "cancel" : "confirm"), {
          expected_revision: state.revision,
          operation_id: operationId(),
          proposal_id: proposal.id,
        });
        dialog.close();
        if (cancel) {
          await accept(updated);
          $("status").textContent = "已取消，保存的声明未改变。";
        } else {
          await accept(updated);
          $("status").textContent = "修改已确认保存，尚未部署到引擎。";
        }
      });
    $("apply").onclick = () => finish(false);
    $("cancel").onclick = () => finish(true);
    dialog.oncancel = (e) => {
      e.preventDefault();
      finish(true);
    };
  }
  async function preview(candidate) {
    const result = await post(endpoint("preview"), {
      expected_revision: state.revision,
      operation_id: operationId(),
      declaration: candidate,
    });
    showProposal(result.proposal);
  }
  listen(container, "click", (event) => {
    const button = event.target.closest("[data-section]");
    if (button && !busy) selectSection(button.dataset.section);
  });
  listen($("assistant-toggle"), "click", () =>
    toggleAssistant($("assistant").hidden),
  );
  listen($("assistant-close"), "click", () => {
    toggleAssistant(false);
    $("assistant-toggle").focus();
  });
  listen($("form"), "input", (event) => {
    if (event.target === $("json")) return;
    dirty = true;
    $("savebar").hidden = false;
    $("status").textContent = "存在尚未确认的表单编辑。";
  });
  listen($("form"), "change", (event) => {
    if (event.target === $("json")) return;
    dirty = true;
    $("savebar").hidden = false;
  });
  listen($("json"), "input", (event) => {
    event.stopPropagation();
    dirty = true;
    $("status").textContent = "JSON 有尚未确认的编辑，请点击“校验 JSON 修改”。";
  });
  listen($("form"), "submit", (e) => {
    e.preventDefault();
    run(() => preview(formDocument()));
  });
  listen($("json-preview"), "click", () =>
    run(async () => {
      let candidate;
      try {
        candidate = JSON.parse($("json").value);
      } catch {
        throw new Error("完整声明 JSON 格式不正确");
      }
      await preview(candidate);
    }),
  );
  listen($("restore"), "click", () =>
    run(async () => {
      requireSaved();
      const d = structuredClone(state.declaration);
      function fill(target, source) {
        for (const [key, value] of Object.entries(source)) {
          if (!(key in target)) target[key] = structuredClone(value);
          else if (
            value &&
            typeof value === "object" &&
            !Array.isArray(value) &&
            target[key] &&
            typeof target[key] === "object"
          )
            fill(target[key], value);
        }
      }
      fill(d, reference);
      await preview(d);
    }),
  );
  listen($("export"), "click", () =>
    run(async () => {
      requireSaved();
      const result = await post(endpoint("export"), {
        expected_revision: state.revision,
        operation_id: operationId(),
      });
      download(state.declaration.version + ".json", result.declaration);
      $("status").textContent =
        "已导出声明。交付路径：" +
        result.deployment_path +
        "；尚未部署到引擎。";
    }),
  );
  listen($("reload"), "click", () =>
    run(async () => {
      if (dirty) $("discard").showModal();
      else await acceptFromServer(state.id);
    }),
  );
  listen($("discard-cancel"), "click", () => $("discard").close());
  listen($("discard-apply"), "click", () =>
    run(async () => {
      await acceptFromServer(state.id);
      $("discard").close();
      $("status").textContent = "已读取服务端保存版本。";
    }),
  );
  async function acceptFromServer(id) {
    await accept(await api("/api/declaration-drafts/" + id));
  }
  listen($("drafts"), "change", () =>
    run(async () => {
      if (dirty) {
        $("drafts").value = state.id;
        throw new Error("请先确认编辑或读取保存版本，再切换草稿。");
      }
      await acceptFromServer($("drafts").value);
    }),
  );
  async function create(template) {
    requireSaved();
    await accept(await post("/api/declaration-drafts", { template }));
    container.querySelector(".declaration-draft-menu").open = false;
  }
  listen($("new"), "click", () => run(() => create("empty")));
  listen($("complete"), "click", () => run(() => create("complete")));
  listen($("source-file"), "change", () =>
    run(async () => {
      const file = $("source-file").files[0];
      if (!file) return;
      if (file.size > 120000)
        throw new Error("资料文件过大，请提供不超过30000字的相关片段。");
      const text = await file.text();
      if (text.length > 30000) throw new Error("资料不能超过30000字。");
      $("material").value = text;
      $("status").textContent = "资料已读取，发送要求后由助手核对并提出修改。";
    }),
  );
  listen($("chat-form"), "submit", (e) => {
    e.preventDefault();
    run(async () => {
      requireSaved();
      const message = $("message").value.trim();
      if (!message) return;
      $("pending").hidden = false;
      try {
        const result = await post(endpoint("messages"), {
          expected_revision: state.revision,
          operation_id: operationId(),
          message,
          source_text: $("material").value,
        });
        await accept(result.state);
        $("message").value = "";
      } finally {
        $("pending").hidden = true;
      }
    });
  });
  listen($("chat"), "click", (e) =>
    run(async () => {
      const button = e.target.closest("[data-proposal]");
      if (!button) return;
      requireSaved();
      const proposal = state.messages.find(
        (m) => m.proposal?.id === button.dataset.proposal,
      )?.proposal;
      if (proposal.expected_revision !== state.revision)
        throw new Error("提案已过期，请重新提出修改。");
      showProposal(proposal);
    }),
  );
  async function loadSettings() {
    settings = await api("/api/settings/model");
    $("api").textContent =
      settings.model + " · " + (settings.has_key ? "已配置" : "未配置");
  }
  listen($("settings"), "click", () =>
    run(async () => {
      await loadSettings();
      $("model").value = settings.model;
      $("key").value = "";
      $("key-info").textContent = settings.has_key
        ? "已有密钥，留空将保留。"
        : "尚未配置密钥。";
      $("settings-error").textContent = "";
      $("settings-dialog").showModal();
    }),
  );
  listen($("settings-close"), "click", () => {
    $("key").value = "";
    $("settings-dialog").close();
  });
  listen($("settings-form"), "submit", (e) => {
    e.preventDefault();
    run(async () => {
      const body = { model: $("model").value };
      if ($("key").value.trim()) body.api_key = $("key").value.trim();
      try {
        await post("/api/settings/model", body);
        $("key").value = "";
        await loadSettings();
        $("settings-dialog").close();
      } catch (e) {
        $("key").value = "";
        $("settings-error").textContent = e.message;
      }
    });
  });
  disabled(true);
  reference = await api("/api/task-declarations/proteinmpnn/1");
  await loadSettings();
  const list = await api("/api/declaration-drafts");
  const saved = localStorage.getItem("ai4s-declaration-draft-id");
  const existing = list.drafts.find((d) => d.id === saved) || list.drafts[0];
  if (existing) await acceptFromServer(existing.id);
  else
    await accept(await post("/api/declaration-drafts", { template: "empty" }));
  disabled(false);
  return {
    destroy() {
      signal.abort();
    },
  };
}
