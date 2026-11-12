import { api, post, operationId, escapeHTML as esc, download } from "./api.js";
import { renderMessage } from "./message.js";

export async function mountDeclaration(
  container,
  { draftId, taskId, version, readOnly = false, onBack } = {},
) {
  const signal = new AbortController();
  const $ = (id) => container.querySelector("#dp-" + id);
  let state,
    reference,
    busy = false,
    dirty = false,
    settings;
  let activeSection = "inputs";
  let editingItem;
  const groupLabels = { inference: "推理参数", filter: "筛选参数" };
  const endpoint = (suffix) =>
    "/api/declaration-drafts/" + state.id + "/" + suffix;
  container.innerHTML = `
    <section class="declaration-workspace ${readOnly ? "declaration-readonly" : ""}" aria-label="任务声明编辑器">
      <header class="declaration-heading"><div><h2 id="dp-title">任务声明</h2><p id="dp-caption"></p></div><div class="declaration-actions"><button class="button" id="dp-back" type="button">返回注册中心</button><button class="button primary" id="dp-export" type="button">校验并导出</button></div></header>
      <div class="declaration-draftbar" id="dp-draftbar"><label><span class="sr-only">当前声明草稿</span><select id="dp-drafts" aria-label="当前声明草稿"></select></label><span id="dp-revision" class="declaration-state"></span><details class="declaration-draft-menu"><summary>草稿操作</summary><div><button class="button" id="dp-reload">读取保存版本</button></div></details></div>
      <p class="declaration-notice">接口定义供节点引用；节点实例的输入与参数独立保存。</p>
      <div class="inline-error" id="dp-error" role="alert" hidden></div><p class="inline-result" id="dp-status" role="status" aria-live="polite"></p>
      <div class="declaration-columns with-assistant" id="dp-columns"><div class="declaration-main">
        <section class="declaration-map panel" aria-labelledby="dp-map-title"><div class="panel-heading"><div><h3 id="dp-map-title">任务接口</h3><p>点击节点查看定义</p></div><span class="declaration-caption">已保存的定义 · 非运行状态</span></div><div id="dp-flow"></div><div class="declaration-validation"><div id="dp-issues" role="status"></div></div></section>
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
            <section id="dp-section-parameters" data-detail-section="parameters" hidden><div class="declaration-section-heading"><h3>参数与约束</h3><p>定义接口规则；具体取值在工作流节点或实验中配置。</p></div><div id="dp-parameters"></div><details class="declaration-disclosure"><summary>跨字段约束</summary><div id="dp-constraints"></div></details><details class="declaration-disclosure"><summary>试填联调参数</summary><p class="field-hint">以下是示例值，不是默认值，也不会启动实验。</p><div id="dp-example"></div></details></section>
            <section id="dp-section-outputs" data-detail-section="outputs" hidden><div class="declaration-section-heading"><h3>会产生什么输出</h3><p>这是产物定义，文件和结果节点将在实际计算后产生。</p></div><div id="dp-outputs"></div></section>
            <section id="dp-section-advanced" data-detail-section="advanced" hidden><div class="declaration-section-heading"><h3>任务信息</h3><p>维护接口版本与来源，保持已发布定义不变。</p></div><div class="fields"><label class="field"><span>任务名称</span><input id="dp-name" required maxlength="200"></label><label class="field"><span>接口版本</span><input id="dp-version" required pattern="[1-9][0-9]{0,7}"></label></div><dl class="declaration-metadata"><div><dt>任务标识</dt><dd><code id="dp-task-id"></code></dd></div><div><dt>声明格式</dt><dd><code id="dp-schema"></code></dd></div><div><dt>适用模型版本</dt><dd><code id="dp-release"></code></dd></div></dl>
              <details class="declaration-disclosure"><summary>批量补齐</summary><p class="field-hint">按已核实定义补齐所有缺项，保留已有内容；也可在各项旁单独填写。</p><button class="button" id="dp-restore" type="button">预览补齐全部缺项</button></details><details class="declaration-disclosure"><summary>完整 JSON 与高级编辑</summary><p class="field-hint">JSON 编辑单独校验，核对差异后确认写入。</p><textarea id="dp-json" aria-label="完整声明 JSON" spellcheck="false"></textarea><button class="button" id="dp-json-preview" type="button">校验 JSON 修改</button></details>
              <details class="declaration-disclosure"><summary>来源与执行映射</summary><div id="dp-source"></div><pre id="dp-execution" class="json-code"></pre></details>
              <details class="declaration-disclosure"><summary>确认记录</summary><div id="dp-events"></div></details>
            </section>
            <div class="declaration-savebar" id="dp-savebar" hidden><span>有尚未确认的表单编辑</span><button class="button primary" type="submit">预览修改</button></div>
          </form></div>
        </section>
      </div>
      <aside class="panel declaration-assistant" id="dp-assistant" aria-label="任务声明助手"><div class="panel-heading"><div class="declaration-assistant-title"><h3>登记助手</h3><span id="dp-api" class="declaration-caption"></span></div><button class="declaration-icon-button" id="dp-assistant-toggle" type="button" aria-label="收起登记助手" title="收起登记助手" aria-expanded="true" aria-controls="dp-assistant-content"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg></button></div><div id="dp-assistant-content"><button class="declaration-settings" id="dp-settings" type="button">模型 API 设置</button><div class="declaration-chat" id="dp-chat" role="log" aria-label="任务声明对话"></div>
        <p id="dp-pending" role="status" hidden>正在核对真实接口并生成回复…</p>
        <details class="declaration-disclosure declaration-material"><summary>参考资料</summary><p class="field-hint">粘贴或读取资料，由助手核对并提出修改。</p><input type="file" id="dp-source-file" accept=".md,.txt,.json" aria-label="读取模型参考资料"><textarea id="dp-material" aria-label="模型参考资料" maxlength="30000" placeholder="粘贴模型文档或参数说明"></textarea></details>
        <form id="dp-chat-form" class="declaration-composer"><label class="sr-only" for="dp-message">向任务声明助手提问</label><textarea id="dp-message" maxlength="8000" placeholder="提问，或描述希望修改的内容…"></textarea><button class="button primary" type="submit">发送</button></form><p class="field-hint declaration-footnote">普通问答不改声明；修改需确认后保存。</p>
      </div></aside></div>
      <dialog class="modal small-modal" id="dp-item-dialog" aria-labelledby="dp-item-title"><div class="modal-head"><h2 id="dp-item-title">填写定义</h2><button class="declaration-icon-button" id="dp-item-close" type="button" aria-label="关闭定义编辑">×</button></div><form id="dp-item-form" novalidate><div class="modal-body"><p id="dp-item-path" class="field-hint"></p><p class="field-hint">填写此项的接口定义；实验输入文件和具体参数值在实验页设置。</p><div id="dp-item-fields"></div><p id="dp-item-error" class="inline-error" role="alert" hidden></p><button class="button soft" id="dp-item-reference" type="button">使用此项已核实定义</button></div><div class="modal-foot"><button class="button" id="dp-item-cancel" type="button">取消</button><button class="button primary" type="submit">预览此项修改</button></div></form></dialog>
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
      .forEach(
        (b) =>
          (b.disabled =
            value || (readOnly && b.matches("input, select, textarea"))),
      );
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
  function itemAt(document, path) {
    const parts = path.split(".");
    return parts[0] === "parameters"
      ? document.parameters?.[parts[1]]?.[parts[2]]
      : document[parts[0]]?.[parts.slice(1).join(".")];
  }
  function putItem(document, path, value) {
    const [section, group, key] = path.split(".");
    if (section === "parameters") {
      document.parameters ??= {};
      document.parameters[group] ??= {};
      document.parameters[group][key] = value;
    } else {
      document[section] ??= {};
      document[section][path.slice(section.length + 1)] = value;
    }
  }
  function itemButtons(path, exists) {
    if (readOnly) return "";
    return `<div class="declaration-item-actions"><button class="button soft" type="button" data-edit-item="${esc(path)}">${exists ? "编辑" : "填写定义"}</button><button class="declaration-inline-action" type="button" data-ask-item="${esc(path)}">请助手协助</button></div>`;
  }
  function fieldsTable(section) {
    return `<div class="declaration-port-list">${Object.entries(
      reference[section],
    )
      .map(([port, expected]) => {
        const p = state.declaration[section]?.[port];
        const path = section + "." + port;
        return `<article class="declaration-port ${p ? "" : "is-missing"}"><div class="declaration-port-title"><strong>${esc(p?.label || expected.label || expected.filename || port)}</strong><span class="declaration-tag">${esc(p?.format || expected.format || expected.aiida_type)}</span><span class="declaration-caption">${!p ? "待填写" : p.required_if ? "保存概率时必需" : p.required ? "必需" : "可选"}${expected.owner ? " · " + (expected.owner === "filter" ? "筛选阶段" : "推理阶段") : ""}</span></div><code>${esc(port)}</code><p>${esc(p?.description || (p ? p.label : "尚未定义，可手动填写或请助手协助。"))}</p>${itemButtons(path, !!p)}</article>`;
      })
      .join("")}</div>`;
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
    $("assistant-content").hidden = !open;
    $("assistant").classList.toggle("is-collapsed", !open);
    $("columns").classList.toggle("with-assistant", open);
    $("columns").classList.toggle("assistant-collapsed", !open);
    $("assistant-toggle").setAttribute("aria-expanded", String(open));
    $("assistant-toggle").setAttribute(
      "aria-label",
      open ? "收起登记助手" : "展开登记助手",
    );
    $("assistant-toggle").title = open ? "收起登记助手" : "展开登记助手";
  }
  function renderItemFields(value) {
    const source = itemAt(reference, editingItem.path);
    const parameter = editingItem.path.startsWith("parameters.");
    const field = (label, control) =>
      `<label class="field"><span>${label}</span>${control}</label>`;
    const fields = [];
    if (Object.hasOwn(source, "label")) {
      fields.push(
        field(
          "名称",
          `<input data-item-field="label" value="${esc(value.label || "")}" placeholder="${esc(source.label)}">`,
        ),
      );
    }
    const types = parameter ? Object.keys(typeLabels) : [source.aiida_type];
    fields.push(
      field(
        parameter ? "参数类型" : "数据类型",
        `<select data-item-field="${parameter ? "type" : "aiida_type"}">${types.map((type) => `<option value="${esc(type)}" ${type === (value.type || value.aiida_type) ? "selected" : ""}>${esc(typeLabels[type] || type)}</option>`).join("")}</select>`,
      ),
    );
    if (source.format) {
      fields.push(
        field(
          "文件格式",
          `<input data-item-field="format" value="${esc(value.format || source.format)}">`,
        ),
      );
    }
    if (source.filename) {
      fields.push(
        field(
          "输出文件名",
          `<input data-item-field="filename" value="${esc(value.filename || source.filename)}">`,
        ),
      );
    }
    fields.push(
      `<label class="declaration-checkbox"><input type="checkbox" data-item-field="required" ${value.required ? "checked" : ""}> ${parameter ? "实验请求必填" : "必需端口"}</label>`,
    );
    if (parameter && Object.hasOwn(source, "default")) {
      const control =
        source.type === "boolean"
          ? `<select data-item-field="default"><option value="">请选择</option><option value="true" ${value.default === true ? "selected" : ""}>true · 开启</option><option value="false" ${value.default === false ? "selected" : ""}>false · 关闭</option></select>`
          : `<input data-item-field="default" type="${["integer", "number"].includes(source.type) ? "number" : "text"}" step="${source.type === "integer" ? "1" : "any"}" value="${esc(value.default ?? "")}" placeholder="${esc(source.default)}">`;
      fields.push(field("后端默认值", control));
    }
    const description = Object.hasOwn(source, "description")
      ? `<label class="field declaration-item-description"><span>说明</span><textarea data-item-field="description" placeholder="说明此项的用途">${esc(value.description || "")}</textarea></label>`
      : "";
    const hints = [];
    if (parameter && !Object.hasOwn(source, "default"))
      hints.push("此参数没有后端默认值。");
    if (source.required_if) hints.push("保存概率时必须提供此输出。");
    hints.push(
      "类型、必填性与其他约束按真实接口校验；其余固定约束沿用已核实定义，均会在预览中展示。",
    );
    $("item-fields").innerHTML =
      `<div class="fields">${fields.join("")}</div>${description}<p class="field-hint">${esc(hints.join(" "))}</p>`;
  }
  function openItem(path) {
    requireSaved();
    const source = itemAt(reference, path);
    if (!source) throw new Error("不支持的接口字段");
    const current = itemAt(state.declaration, path);
    // Fixed interface constraints come from the verified definition; only this item is edited.
    editingItem = { path, base: structuredClone(current || source) };
    $("item-title").textContent =
      (current ? "编辑 · " : "填写 · ") +
      (source.label || source.filename || path.split(".").at(-1));
    $("item-path").textContent = path;
    $("item-error").hidden = true;
    renderItemFields(
      current || {
        ...source,
        label: "",
        description: "",
        ...(Object.hasOwn(source, "default") ? { default: "" } : {}),
      },
    );
    $("item-dialog").showModal();
  }
  function renderFlow(d) {
    const groups = Object.keys(reference.parameters || {});
    const primary = groups[0];
    const outputsFor = (group) =>
      Object.entries(d.outputs || {}).filter(
        ([, port]) => !port.owner || port.owner === group,
      );
    const node = (section, title, caption, entries) =>
      `<button type="button" class="declaration-node" data-section="${section}" aria-controls="dp-section-${section}" aria-pressed="false"><span class="declaration-node-kind">${caption}</span><strong>${esc(title)}</strong><span class="declaration-node-ports">${entries.length ? entries.map(([key, port]) => `<span><i aria-hidden="true"></i>${esc(port.filename || key)}${port.format && !port.filename ? " · " + esc(port.format) : ""}${port.required_if ? " · 按需" : ""}</span>`).join("") : '<span class="declaration-caption">待填写定义</span>'}</span></button>`;
    const primaryCount = Object.keys(d.parameters?.[primary] || {}).length;
    $("flow").innerHTML =
      `<div class="declaration-flow">${node("inputs", "任务输入", "INPUT", Object.entries(d.inputs || {}))}<span class="declaration-connector" aria-label="作为任务输入">→</span><button type="button" class="declaration-node model-node" data-section="parameters" aria-controls="dp-section-parameters" aria-pressed="false"><span class="declaration-node-kind">计算任务</span><strong>${esc(d.name)}</strong><span class="declaration-model-description">${esc(d.task_id)} · 接口 v${esc(d.version)}</span><span class="declaration-model-params">${primaryCount} 项${esc(groupLabels[primary] || primary || "参数")}</span></button><span class="declaration-connector" aria-label="声明的任务输出">→</span>${node("outputs", "任务输出", "OUTPUT", outputsFor(primary))}</div>${groups
        .slice(1)
        .map(
          (group) =>
            `<div class="declaration-filter-branch"><span class="declaration-branch-line" aria-hidden="true">↳</span><button type="button" data-section="parameters" aria-controls="dp-section-parameters" aria-pressed="false"><strong>${esc(groupLabels[group] || group)}</strong><span>${Object.keys(d.parameters?.[group] || {}).length} 项参数 · 独立阶段</span></button><span class="declaration-connector" aria-hidden="true">→</span><button type="button" data-section="outputs" aria-controls="dp-section-outputs" aria-pressed="false"><strong>阶段输出</strong><span>${outputsFor(group).length} 项输出定义</span></button></div>`,
        )
        .join("")}`;
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
    $("title").textContent = d.name || d.task_id;
    $("caption").textContent = readOnly
      ? `仓库声明 v${d.version} · 只读 · 网页服务已加载`
      : `编辑声明 v${d.version} · 确认后保存草稿，导出后仍需审核与部署`;
    $("task-id").textContent = d.task_id;
    $("schema").textContent = d.schema_version;
    $("constraints").innerHTML =
      (d.constraints || [])
        .map(
          (rule) =>
            `<p class="field-hint"><code>${esc(rule.rule)}</code> · ${esc(rule.message)}</p>`,
        )
        .join("") || "<p>没有跨字段约束。</p>";
    $("name").value = d.name || "";
    $("version").value = d.version || "";
    $("release").textContent = d.model?.release || "缺少版本";
    $("revision").textContent =
      "草稿 r" +
      state.revision +
      (state.status === "exported_not_deployed"
        ? " · 已导出，未部署"
        : " · 未发布");
    renderFlow(d);
    selectSection(activeSection);
    $("savebar").hidden = true;
    $("restore").hidden = !state.issues.length;
    $("inputs").innerHTML = fieldsTable("inputs");
    $("outputs").innerHTML = fieldsTable("outputs");
    $("issues").innerHTML = state.issues.length
      ? `<details class="check-list"><summary>导出前需处理 ${state.issues.length} 项 · 查看详情</summary><ul>${state.issues.map((i) => `<li><code>${esc(i.path)}</code>：${esc(i.message)}</li>`).join("")}</ul></details>`
      : '<p class="declaration-valid">定义完整 <span>· 导出时校验发布版本</span></p>';
    $("parameters").innerHTML = Object.entries(reference.parameters)
      .map(
        ([group, fields]) =>
          `<h4>${esc(groupLabels[group] || group)}</h4><div class="declaration-parameter-list">${Object.entries(
            fields,
          )
            .map(([key, source]) => {
              const f = d.parameters?.[group]?.[key];
              if (!f)
                return `<article class="declaration-port is-missing"><strong>${esc(source.label || key)}</strong><code>${esc(key)}</code><p class="declaration-caption">待填写 · ${esc(typeLabels[source.type])}</p>${itemButtons("parameters." + group + "." + key, false)}</article>`;
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
              return `<details class="declaration-parameter"><summary><span class="declaration-parameter-name"><strong>${esc(f.label || key)}</strong><code>${esc(key)}</code></span><span class="declaration-parameter-meta">${esc(typeLabels[f.type] || f.type)} · ${f.required ? "必填" : "可选"}${f.default !== undefined ? " · 默认 " + esc(f.default) : ""}</span></summary><div class="declaration-parameter-body"><p>${esc(f.description)}</p>${constraints ? `<p class="field-hint">约束：${esc(constraints)}</p>` : ""}${itemButtons("parameters." + group + "." + key, true)}</div></details>`;
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
      `<p>依据修订：<code>${esc(d.source_reference?.revision)}</code></p><ul>${(d.source_reference?.paths || []).map((path) => `<li><a href="https://github.com/${esc(d.source_reference.repository)}/blob/${encodeURIComponent(d.source_reference.revision)}/${path.split("/").map(encodeURIComponent).join("/")}" target="_blank" rel="noopener noreferrer">${esc(path)}</a></li>`).join("")}</ul>`;
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
            `<article class="chat-message ${m.role === "user" ? "user" : "assistant"}"><div class="who">${m.role === "user" ? "你" : "登记助手"}</div><div class="message-body">${
              m.role === "user"
                ? esc(m.text)
                : renderMessage(
                    m.text,
                    Object.values(reference.parameters).flatMap((group) =>
                      Object.keys(group),
                    ),
                  )
            }</div>${m.proposal ? `<p>${m.proposal.status === "pending" ? "提案待确认，尚未写入" : m.proposal.status === "applied" ? "已确认写入" : "已取消"}</p>${m.proposal.status === "pending" ? `<button class="button soft" data-proposal="${esc(m.proposal.id)}">查看修改并确认</button>` : ""}` : ""}${m.usage ? `<p class="chat-meta">${esc(m.usage.model)} · ${m.usage.elapsed_seconds.toFixed(2)}s</p>` : ""}</article>`,
        )
        .join("") ||
      '<p class="declaration-greeting">可以问“为什么种子不能为0”，或要求“根据真实接口补齐缺少的输入、参数和输出”。助手只提出修改，确认后才保存。</p>';
    $("chat").scrollTop = $("chat").scrollHeight;
    dirty = false;
  }
  async function refreshList() {
    const list = await api("/api/declaration-drafts");
    $("drafts").innerHTML = list.drafts
      .filter((d) => d.task_id === reference.task_id)
      .map(
        (d) =>
          `<option value="${esc(d.id)}" ${d.id === state?.id ? "selected" : ""}>${esc(d.name)} · r${d.revision} · ${esc(d.id.slice(-6))}</option>`,
      )
      .join("");
  }
  async function accept(value) {
    state = value;
    render();
    if (!readOnly) {
      localStorage.setItem("ai4s-declaration-draft-id", state.id);
      await refreshList();
    }
  }
  function formDocument() {
    const d = structuredClone(state.declaration);
    d.name = $("name").value;
    d.version = $("version").value;
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
    toggleAssistant($("assistant-content").hidden),
  );
  listen(container, "click", (event) => {
    const edit = event.target.closest("[data-edit-item]");
    const ask = event.target.closest("[data-ask-item]");
    if (edit) run(() => openItem(edit.dataset.editItem));
    if (ask && !busy) {
      toggleAssistant(true);
      const request =
        "请帮我核对并补齐 " +
        ask.dataset.askItem +
        " 这一项的定义，只针对这一项提出修改，供我确认。";
      $("message").value = [$("message").value.trim(), request]
        .filter(Boolean)
        .join("\n\n");
      $("message").focus();
    }
  });
  const closeItem = () => $("item-dialog").close();
  listen($("item-close"), "click", closeItem);
  listen($("item-cancel"), "click", closeItem);
  listen($("item-reference"), "click", () =>
    renderItemFields(itemAt(reference, editingItem.path)),
  );
  listen($("item-form"), "submit", (event) => {
    event.preventDefault();
    run(async () => {
      $("item-error").hidden = true;
      try {
        const value = structuredClone(editingItem.base);
        $("item-fields")
          .querySelectorAll("[data-item-field]")
          .forEach((input) => {
            const key = input.dataset.itemField;
            if (key === "required") value[key] = input.checked;
            else if (key === "default") {
              if (!input.value.trim())
                throw new Error("请填写默认值，或引用此项已核实定义。");
              const type = $("item-fields").querySelector(
                '[data-item-field="type"]',
              ).value;
              if (type === "boolean") {
                if (!["true", "false"].includes(input.value.trim()))
                  throw new Error("开关默认值只能为 true 或 false。");
                value[key] = input.value.trim() === "true";
              } else
                value[key] = ["integer", "number"].includes(type)
                  ? Number(input.value)
                  : input.value;
            } else value[key] = input.value;
          });
        const candidate = structuredClone(state.declaration);
        putItem(candidate, editingItem.path, value);
        const response = await post(endpoint("preview"), {
          expected_revision: state.revision,
          operation_id: operationId(),
          declaration: candidate,
        });
        closeItem();
        showProposal(response.proposal);
      } catch (e) {
        $("item-error").textContent =
          e.message +
          (Array.isArray(e.details)
            ? "：" + e.details.map((i) => i.path + " " + i.message).join("；")
            : "");
        $("item-error").hidden = false;
      }
    });
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
      state.status = result.status;
      $("revision").textContent =
        "草稿 r" + state.revision + " · 已导出，未部署";
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
    const value = await api("/api/declaration-drafts/" + id);
    reference = await api(
      `/api/task-declarations/${encodeURIComponent(value.reference.task_id)}/${encodeURIComponent(value.reference.version)}`,
    );
    await accept(value);
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
  listen($("back"), "click", () =>
    run(async () => {
      requireSaved();
      await onBack?.();
    }),
  );
  disabled(true);
  if (readOnly) {
    reference = await api(
      `/api/task-declarations/${encodeURIComponent(taskId)}/${encodeURIComponent(version)}`,
    );
    await accept({
      declaration: reference,
      revision: 0,
      issues: [],
      messages: [],
      events: [],
      status: "repository_loaded",
    });
  } else {
    if (!draftId) throw new Error("请从任务注册中心选择或新建编辑草稿。");
    await acceptFromServer(draftId);
    await loadSettings();
  }
  disabled(false);
  return {
    destroy() {
      signal.abort();
    },
  };
}
