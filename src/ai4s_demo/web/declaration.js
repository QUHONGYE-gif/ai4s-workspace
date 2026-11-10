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
  const endpoint = (suffix) =>
    "/api/declaration-drafts/" + state.id + "/" + suffix;
  container.innerHTML = `
    <section class="declaration-workspace" aria-label="ProteinMPNN 任务声明登记">
      <div class="declaration-heading"><div><h2>ProteinMPNN 任务声明</h2><p>根据真实接口整理定义，核对后导出约定①文件，交给引擎登记。</p></div><button class="button" id="dp-settings">模型 API 设置</button></div>
      <div class="declaration-draftbar"><label>当前声明草稿<select id="dp-drafts" aria-label="当前声明草稿"></select></label><button class="button" id="dp-reload">读取保存版本</button><button class="button" id="dp-new">新建空白声明</button><button class="button" id="dp-complete">从完整定义新建</button><span id="dp-revision" class="pill"></span></div>
      <div class="declaration-notice">声明描述任务接口，具体实验输入和参数通过约定②提交。导出文件后仍需随引擎服务部署；本页面不会提交计算。</div>
      <p class="inline-error" id="dp-error" role="alert" hidden></p><p class="inline-result" id="dp-status" role="status" aria-live="polite"></p>
      <div class="declaration-columns"><section class="panel declaration-editor" aria-label="任务声明定义">
        <div class="panel-heading"><h2>声明与接口</h2><button class="button soft" id="dp-restore">从真实定义补齐缺项</button></div>
        <div class="declaration-body"><form id="dp-form"><div class="fields">
          <label class="field"><span class="field-label">任务标识</span><input value="proteinmpnn" readonly></label>
          <label class="field"><span class="field-label">声明格式</span><input value="ai4s-task-declaration-1" readonly></label>
          <label class="field"><span class="field-label">任务名称</span><input id="dp-name" required maxlength="200"></label>
          <label class="field"><span class="field-label">接口版本</span><input id="dp-version" required pattern="[1-9][0-9]{0,7}"></label></div>
          <p class="field-hint">本任务适用 release：<code id="dp-release"></code>。模型运行身份由引擎按约定③核实。</p>
          <div id="dp-issues" role="status"></div>
          <h3>输入端口</h3><div id="dp-inputs"></div>
          <h3>参数定义</h3><p class="field-hint">必填指实验请求需要明确提供；没有后端默认值的字段留空。类型与默认值必须符合真实接口，改动会先校验。</p>
          <div id="dp-parameters"></div>
          <h3>输出与辅助产物</h3><div id="dp-outputs"></div>
          <details class="declaration-disclosure"><summary>试填联调参数（示例值，不是默认值）</summary><p class="field-hint">示例不包含已上传文件，也不会启动实验；修改发布版本的内容时需使用新的接口版本。</p><div id="dp-example"></div></details>
          <div class="declaration-actions"><button class="button primary" type="submit">校验并预览修改</button><button class="button" id="dp-export" type="button">校验并导出声明</button></div>
        </form>
        <details class="declaration-disclosure"><summary>完整声明 JSON 与高级编辑</summary><p class="field-hint">输入输出和参数定义均包含在内。保存仍需查看差异并确认；不执行任意代码。</p><textarea id="dp-json" aria-label="完整声明 JSON" spellcheck="false"></textarea><button class="button" id="dp-json-preview">校验 JSON 修改</button></details>
        <details class="declaration-disclosure"><summary>来源与执行映射</summary><div id="dp-source"></div><pre id="dp-execution" class="json-code"></pre></details>
        <details class="declaration-disclosure"><summary>确认记录</summary><div id="dp-events"></div></details></div>
      </section>
      <aside class="panel declaration-assistant" aria-label="任务声明助手"><div class="panel-heading"><h2>登记助手</h2><span id="dp-api" class="pill"></span></div><div class="declaration-chat" id="dp-chat" role="log" aria-label="任务声明对话"></div>
        <p id="dp-pending" role="status" hidden>正在核对真实接口并生成回复…</p>
        <details class="declaration-disclosure declaration-material"><summary>导入参考资料</summary><p class="field-hint">粘贴或读取文本资料，助手提出修改后由你确认。与真实接口冲突的默认值不会覆盖。</p><input type="file" id="dp-source-file" accept=".md,.txt,.json" aria-label="读取模型参考资料"><textarea id="dp-material" aria-label="模型参考资料" maxlength="30000" placeholder="粘贴模型文档或参数说明"></textarea></details>
        <form id="dp-chat-form" class="declaration-composer"><label class="sr-only" for="dp-message">向任务声明助手提问</label><textarea id="dp-message" maxlength="8000" placeholder="请根据真实定义补齐缺少的输入、参数和输出"></textarea><button class="button primary" type="submit">发送给登记助手</button></form><p class="field-hint declaration-footnote">普通问答不修改声明；所有提案确认后才写入。</p>
      </aside></div>
      <dialog class="modal" id="dp-confirm" aria-labelledby="dp-confirm-title"><div class="modal-head"><h2 id="dp-confirm-title">核对声明修改</h2></div><div class="modal-body"><p>以下修改尚未写入。确认后整批保存到编辑草稿。</p><p id="dp-evidence" class="field-hint"></p><div id="dp-diff"></div></div><div class="modal-foot"><button class="button" id="dp-cancel">取消修改</button><button class="button primary" id="dp-apply">确认并写入</button></div></dialog>
      <dialog class="modal small-modal" id="dp-discard" aria-labelledby="dp-discard-title"><div class="modal-head"><h2 id="dp-discard-title">读取保存版本？</h2></div><div class="modal-body"><p>尚未确认的表单和 JSON 编辑会被放弃，已保存的声明保持不变。</p></div><div class="modal-foot"><button class="button" id="dp-discard-cancel">继续编辑</button><button class="button primary" id="dp-discard-apply">放弃编辑并读取</button></div></dialog>
      <dialog class="modal small-modal" id="dp-settings-dialog" aria-labelledby="dp-settings-title"><div class="modal-head"><h2 id="dp-settings-title">模型 API 设置</h2><button class="button" id="dp-settings-close">关闭</button></div><form id="dp-settings-form"><div class="modal-body"><label class="field"><span>DeepSeek 模型名</span><input id="dp-model" required></label><label class="field"><span>API key（仅存服务端，留空保留）</span><input type="password" id="dp-key" autocomplete="off"></label><p id="dp-key-info"></p><p id="dp-settings-error" class="inline-error" role="alert"></p></div><div class="modal-foot"><button class="button primary">保存 API 设置</button></div></form></dialog>
    </section>`;
  const listen = (element, event, fn) =>
    element.addEventListener(event, fn, { signal: signal.signal });
  function error(e) {
    $("error").textContent =
      e.message + (e.details ? "\n" + JSON.stringify(e.details, null, 2) : "");
    $("error").hidden = false;
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
  function fieldsTable(ports) {
    const rows = Object.entries(ports || {});
    return rows.length
      ? `<div class="declaration-table-wrap"><table class="source-grid"><thead><tr><th>端口</th><th>类型／格式</th><th>要求</th><th>说明</th></tr></thead><tbody>${rows.map(([port, p]) => `<tr><td><code>${esc(port)}</code>${p.owner ? "<br>" + esc(p.owner === "filter" ? "筛选阶段" : "推理阶段") : ""}</td><td>${esc(p.aiida_type)}${p.format ? "<br>" + esc(p.format) : ""}</td><td>${p.required_if ? "保存概率时必需" : p.required ? "必需" : "可选"}</td><td>${esc(p.description || p.label || "")}</td></tr>`).join("")}</tbody></table></div>`
      : '<p class="declaration-missing">端口尚未补齐，可请助手根据真实定义补全。</p>';
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
    $("revision").textContent = "草稿 r" + state.revision + " · 未部署到引擎";
    $("inputs").innerHTML = fieldsTable(d.inputs);
    $("outputs").innerHTML = fieldsTable(d.outputs);
    $("issues").innerHTML = state.issues.length
      ? `<div class="check-list"><strong>导出前需处理 ${state.issues.length} 项</strong><ul>${state.issues.map((i) => `<li><code>${esc(i.path)}</code>：${esc(i.message)}</li>`).join("")}</ul></div>`
      : '<p class="inline-result">声明定义完整，导出时还会检查发布版本一致性。</p>';
    $("parameters").innerHTML = Object.entries(reference.parameters)
      .map(
        ([group, fields]) =>
          `<h4>${group === "inference" ? "推理参数" : "筛选参数（仅 mpnn_filter）"}</h4><div class="declaration-table-wrap"><table class="source-grid"><thead><tr><th>字段／显示名</th><th>类型</th><th>必填</th><th>后端默认值／约束</th><th>说明</th></tr></thead><tbody>${Object.entries(
            fields,
          )
            .map(([key, source]) => {
              const f = d.parameters?.[group]?.[key];
              if (!f)
                return `<tr><td><code>${esc(key)}</code></td><td colspan="4" class="declaration-missing">缺少定义 · 请补齐</td></tr>`;
              return `<tr data-definition="${group}.${key}"><td><code>${esc(key)}</code><input data-meta="label" aria-label="${group}.${key} 显示名" value="${esc(f.label)}"></td><td><select data-meta="type" aria-label="${group}.${key} 类型">${["string", "integer", "number", "boolean"].map((t) => `<option ${f.type === t ? "selected" : ""}>${t}</option>`).join("")}</select></td><td><input type="checkbox" data-meta="required" aria-label="${group}.${key} 必填" ${f.required ? "checked" : ""}></td><td>${source.type === "boolean" ? `<select data-meta="default" data-value-type="boolean" aria-label="${group}.${key} 默认值"><option value="true" ${f.default === true ? "selected" : ""}>true</option><option value="false" ${f.default === false ? "selected" : ""}>false</option></select>` : `<input data-meta="default" data-value-type="${source.type}" aria-label="${group}.${key} 默认值" placeholder="无默认值" value="${esc(f.default ?? "")}">`}<p class="field-hint">${esc([f.minimum !== undefined ? "≥ " + f.minimum : "", f.maximum !== undefined ? "≤ " + f.maximum : "", f.exclusiveMinimum !== undefined ? "> " + f.exclusiveMinimum : "", f.minLength ? "非空文字" : "", f.enum ? "枚举：" + f.enum.join(" / ") : ""].filter(Boolean).join("；"))}</p></td><td><textarea data-meta="description" aria-label="${group}.${key} 说明">${esc(f.description)}</textarea></td></tr>`;
            })
            .join("")}</tbody></table></div>`,
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
  listen($("form"), "input", () => {
    dirty = true;
    $("status").textContent = "存在尚未确认的表单编辑。";
  });
  listen($("form"), "change", () => {
    dirty = true;
  });
  listen($("json"), "input", () => {
    dirty = true;
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
