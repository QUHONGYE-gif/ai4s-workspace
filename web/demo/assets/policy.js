const labels = {
  reuse_policy: "默认复用方式",
  transfer_limit_seconds: "搬运时间阈值",
  storage_limit_bytes: "空间上限",
  retention: "保留策略",
};
const modes = {
  allow_reuse: "允许复用", force_rerun: "强制重算", new_sample: "新采样",
};
const modeDescriptions = {
  allow_reuse: "有符合条件的旧结果时直接复用，找不到时重新计算。",
  force_rerun: "跳过复用，保留原参数和随机种子重新计算。",
  new_sample: "跳过复用，换一个随机种子重新计算。",
};
const retention = {lru: "LRU（最久未用优先淘汰）", cost: "本项目策略"};
const GB = 1e9;
const detailFields = ["transfer_limit_seconds", "storage_limit_bytes", "retention"];

function valueLabel(key, value) {
  if (value === null) return "未设置";
  if (key === "reuse_policy") return modes[value];
  if (key === "retention") return retention[value];
  if (key === "storage_limit_bytes") return `${value / GB} GB`;
  return `${value} 秒`;
}

async function api(path = "", body) {
  const response = await fetch("./agent/api/policy" + path, body ? {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
  } : {cache: "no-store"});
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(result.error || "暂时无法访问策略服务，请重试。");
    error.status = response.status;
    throw error;
  }
  return result;
}

function changeRows(diff, showScope = false) {
  const list = document.createElement("dl");
  list.className = "policy-changes";
  for (const {field, before, after} of diff) {
    const row = document.createElement("div");
    const title = document.createElement("dt");
    title.textContent = labels[field];
    if (showScope && field !== "reuse_policy") {
      const scope = document.createElement("span");
      scope.className = "policy-scope";
      scope.textContent = "仅用于模拟";
      title.append(scope);
    }
    const values = document.createElement("dd");
    const next = document.createElement("strong");
    next.textContent = valueLabel(field, after);
    values.append(`${valueLabel(field, before)} → `, next);
    row.append(title, values);
    list.append(row);
  }
  return list;
}

const historySources = {manual: "手动修改", agent: "助手提案", undo: "撤回"};
const historyTime = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
  hourCycle: "h23",
});

function historyEntry(event, isCurrent) {
  const diff = Object.keys(labels)
    .filter(field => event.before[field] !== event.after[field])
    .map(field => ({field, before: event.before[field], after: event.after[field]}));
  const entry = document.createElement("li");
  entry.className = "policy-history-entry";
  const content = document.createElement("div");
  content.className = "policy-history-content";
  const title = document.createElement("h3");
  if (diff.length === 1) {
    const {field, before, after} = diff[0];
    const previous = document.createElement("span");
    previous.className = "policy-history-previous";
    previous.textContent = valueLabel(field, before);
    const next = document.createElement("span");
    next.textContent = valueLabel(field, after);
    title.append(`${labels[field]}：`, previous, " → ", next);
    if (field !== "reuse_policy") {
      const scope = document.createElement("span");
      scope.className = "policy-scope";
      scope.textContent = "仅用于模拟";
      title.append(scope);
    }
  } else {
    title.textContent = `修改了 ${diff.length} 项设置`;
  }
  const metadata = document.createElement("p");
  metadata.className = "policy-history-meta";
  const author = document.createElement("span");
  author.textContent = `${event.actor.display_name} · ${historySources[event.source]}`;
  const time = document.createElement("time");
  time.dateTime = event.time;
  time.textContent = historyTime.format(new Date(event.time));
  metadata.append(author, time);
  content.append(title, metadata);

  if (diff.length > 1) {
    const details = document.createElement("details");
    details.className = "policy-history-diff";
    const summary = document.createElement("summary");
    summary.textContent = diff.map(({field}) => labels[field]).join("、");
    summary.prepend("查看差异：");
    details.append(summary, changeRows(diff, true));
    content.append(details);
  }

  const actions = document.createElement("div");
  actions.className = "policy-history-actions";
  const version = document.createElement("span");
  version.className = "policy-history-version";
  version.textContent = `版本 ${event.revision}`;
  if (isCurrent) {
    entry.classList.add("is-current");
    version.textContent += " · 当前";
  }
  actions.append(version);
  entry.append(content, actions);
  return entry;
}

function proposalImpact(diff) {
  const reuse = diff.find(item => item.field === "reuse_policy");
  return reuse ? `下次沿用工作区默认设置的真实实验：${modeDescriptions[reuse.after]} 保存后不会启动实验。`
    : "可在模拟对比中检查已保存设置；不会改变真实实验的执行或清理文件。";
}

export function mountPolicy(host) {
  const $ = selector => host.querySelector(selector);
  $("#policy-default").innerHTML = `
    <div class="panel policy-settings-panel">
      <header class="policy-panel-head">
        <div><p class="policy-kicker">工作区默认策略</p><h2 id="policy-current">正在读取设置…</h2>
          <p class="small muted" id="policy-revision" aria-live="polite"></p></div>
        <button class="btn primary" type="button" id="policy-edit" disabled>编辑策略</button>
      </header>
      <div id="policy-overview" hidden>
        <div class="policy-current-note">
          <span class="pill good">真实实验</span>
          <div><strong id="policy-current-description"></strong><p class="small muted">提交真实实验时默认采用，可对单次实验另设复用方式。</p></div>
        </div>
        <div class="policy-simulation-summary">
          <div class="policy-section-title"><h3>成本与存储</h3><span class="policy-scope">仅用于模拟</span></div>
          <dl>${detailFields.map(field => `<div><dt>${labels[field]}</dt><dd data-policy-value="${field}"></dd></div>`).join("")}</dl>
        </div>
      </div>
      <form id="policy-settings" class="policy-form" hidden>
        <fieldset disabled>
          <legend>编辑默认策略</legend>
          <label>默认复用方式<select name="reuse_policy">${Object.entries(modes).map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}</select></label>
          <p class="small muted" id="policy-edit-description"></p>
          <div class="policy-simulation-fields">
            <div class="policy-section-title"><h3>成本与存储</h3><span class="policy-scope">仅用于模拟</span></div>
            <div class="policy-limits">
              <label>搬运时间阈值（秒）<input type="number" min="0" step="any" name="transfer_limit_seconds" placeholder="未设置"></label>
              <label>空间上限（GB）<input type="number" min="0.000000001" max="9007199.254740991" step="any" name="storage_limit_bytes" placeholder="未设置"></label>
            </div>
            <label>保留策略<select name="retention">${Object.entries(retention).map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}</select></label>
          </div>
          <div class="policy-actions"><button class="btn primary" type="submit">预览修改</button><button class="btn" type="button" id="policy-discard">放弃编辑</button></div>
        </fieldset>
      </form>
      <div class="policy-feedback" id="policy-settings-feedback" hidden>
        <p id="policy-feedback" role="status"></p><button class="btn" type="button" id="policy-refresh" hidden>重新读取设置</button>
      </div>
    </div>
    <details class="panel policy-history">
      <summary class="policy-history-heading"><strong>修改记录</strong><span id="policy-history-count"></span></summary>
      <div class="policy-history-body">
        <p id="policy-history-empty" class="small muted">暂无修改记录。</p>
        <ol id="policy-history" aria-label="策略版本，最新在前" hidden></ol>
        <button class="btn policy-history-undo" id="policy-undo" type="button" hidden>
          <svg class="icon" aria-hidden="true"><use href="#i-reset" /></svg>撤回最近一次修改
        </button>
      </div>
    </details>
    <dialog class="modal policy-dialog" aria-labelledby="policy-confirm-title">
      <h2 id="policy-confirm-title">核对策略修改</h2>
      <div id="policy-diff"></div><p id="policy-confirm-impact" class="small muted"></p>
      <p id="policy-confirm-error" class="policy-error" role="alert"></p>
      <div class="policy-actions"><button class="btn primary" type="button" id="policy-confirm">确认并保存</button><button class="btn" type="button" id="policy-cancel">取消</button></div>
    </dialog>`;
  const assistant = $("#policy-assistant");
  assistant.innerHTML = `
    <header class="policy-assistant-head">
      <div><h2 id="policy-assistant-title" tabindex="-1">策略助手</h2><p class="small muted" id="policy-assistant-context">当前工作区 · 正在读取策略</p></div>
      <button class="btn policy-icon-button" type="button" id="policy-assistant-close" aria-label="收起策略助手" title="收起策略助手"><svg class="icon" aria-hidden="true"><use href="#i-close" /></svg></button>
    </header>
    <div class="policy-thread">
      <div id="policy-chat-start">
        <h3>想了解或调整哪条规则？</h3>
        <p class="small muted">我可以解释当前设置，也可以帮你生成修改提案。</p>
        <div class="policy-suggestions">
          <button type="button" data-policy-question>强制重算和新采样有什么区别？</button>
          <button type="button" data-policy-question>空间上限会影响真实实验吗？</button>
          <button type="button" data-policy-question>把默认复用方式改成允许复用</button>
        </div>
      </div>
      <div id="policy-chat" role="log" aria-label="策略对话"></div>
      <p class="policy-chat-status small muted" id="policy-chat-status" role="status"></p>
    </div>
    <form id="policy-chat-form">
      <div class="policy-composer">
        <label class="policy-sr-only" for="policy-message">给策略助手发消息</label>
        <textarea id="policy-message" maxlength="2000" rows="2" required placeholder="问问策略，或描述你想做的修改…"></textarea>
        <button class="btn primary" type="submit" id="policy-send">发送</button>
      </div>
      <p class="small muted">修改须经你确认。Enter 发送，Shift + Enter 换行。</p>
      <div class="policy-chat-feedback" hidden>
        <p id="policy-chat-error" class="policy-error" role="alert"></p>
        <button class="btn" type="button" id="policy-chat-refresh" hidden>重新读取设置</button>
      </div>
    </form>`;

  const form = $("#policy-settings");
  const dialog = $(".policy-dialog");
  const edit = $("#policy-edit");
  const undo = $("#policy-undo");
  const refresh = $("#policy-refresh");
  const chatRefresh = $("#policy-chat-refresh");
  const dialogConfirm = $("#policy-confirm");
  const dialogCancel = $("#policy-cancel");
  const sample = $("#policy-sample");
  const toggle = $("#policy-assistant-toggle");
  const chatForm = $("#policy-chat-form");
  const message = $("#policy-message");
  const send = $("#policy-send");
  const suggestions = [...assistant.querySelectorAll("[data-policy-question]")];
  let state, manualProposal, agentProposal, busy = false, dirty = false, needsRefresh = false;
  let sampleRequest = 0;

  function syncControls() {
    const blocked = busy || needsRefresh || !state;
    edit.disabled = blocked;
    form.querySelector("fieldset").disabled = blocked;
    undo.disabled = blocked;
    dialogConfirm.disabled = blocked;
    dialogCancel.disabled = busy;
    refresh.disabled = chatRefresh.disabled = busy;
    message.readOnly = busy;
    send.disabled = blocked || !message.value.trim();
    for (const button of suggestions) button.disabled = blocked;
    if (agentProposal) {
      agentProposal.confirm.disabled = blocked;
      agentProposal.cancel.disabled = busy;
    }
  }

  function settingsFeedback(text = "", reload = false) {
    $("#policy-feedback").textContent = text;
    refresh.hidden = !reload;
    $("#policy-settings-feedback").hidden = !text;
  }

  function chatFeedback(text = "", reload = false) {
    $("#policy-chat-error").textContent = text;
    chatRefresh.hidden = !reload;
    $(".policy-chat-feedback").hidden = !text;
  }

  function scrollChat() {
    const thread = $(".policy-thread");
    thread.scrollTop = thread.scrollHeight;
  }

  function setAssistant(open) {
    toggle.setAttribute("aria-expanded", String(open));
    assistant.hidden = !open;
    if (open) {
      $("#policy-assistant-title").focus();
      scrollChat();
    } else toggle.focus();
  }
  toggle.disabled = false;
  toggle.onclick = () => setAssistant(assistant.hidden);
  $("#policy-assistant-close").onclick = () => setAssistant(false);
  assistant.onkeydown = event => {
    if (event.key !== "Escape" || event.isComposing) return;
    event.preventDefault();
    setAssistant(false);
  };

  function resetForm() {
    if (!state) return;
    for (const field of Object.keys(labels)) {
      const value = state.config[field];
      form.elements[field].value = field === "storage_limit_bytes" && value !== null ? value / GB : value ?? "";
    }
    $("#policy-edit-description").textContent = modeDescriptions[state.config.reuse_policy];
    dirty = false;
  }

  function setEditing(editing) {
    edit.hidden = editing;
    form.hidden = !editing;
    $("#policy-overview").hidden = editing;
  }

  function render(saved) {
    state = saved;
    needsRefresh = false;
    const revision = `版本 ${saved.revision}`;
    const mode = modes[saved.config.reuse_policy];
    $("#policy-current").textContent = mode;
    $("#policy-revision").textContent = `${revision} · ${saved.actor.display_name}`;
    $("#policy-current-description").textContent = modeDescriptions[saved.config.reuse_policy];
    $("#policy-assistant-context").textContent = `当前工作区 · ${revision} · ${mode}`;
    for (const field of detailFields) {
      $(`[data-policy-value="${field}"]`).textContent = valueLabel(field, saved.config[field]);
    }
    resetForm();
    setEditing(false);
    if (agentProposal && agentProposal.proposal.revision !== saved.revision) {
      finishProposal("策略版本已更新，请重新提案。", "expired");
    }
    if (sample.open) void loadSimulation();

    const history = $("#policy-history");
    const entries = [...saved.history].reverse().map(event => historyEntry(event, event.revision === saved.revision));
    const latestActions = entries[0]?.querySelector(".policy-history-actions");
    if (latestActions) latestActions.append(undo);
    else $(".policy-history-body").append(undo);
    undo.hidden = !latestActions;
    history.replaceChildren(...entries);
    history.hidden = entries.length === 0;
    $("#policy-history-empty").hidden = entries.length > 0;
    $("#policy-history-count").textContent = `${entries.length} 条`;
  }

  async function run(action, area = "settings") {
    if (busy) return false;
    busy = true;
    syncControls();
    try {
      await action();
      return true;
    } catch (error) {
      const conflict = error.status === 409;
      const text = error instanceof TypeError ? "未能连接策略服务，请检查连接后重试。" : error.message;
      if (conflict) {
        needsRefresh = true;
        finishProposal("提案已失效，请重新读取设置后再试。", "expired");
      }
      if (area === "chat") chatFeedback(text, conflict || needsRefresh);
      else if (dialog.open) $("#policy-confirm-error").textContent = text;
      else settingsFeedback(text, conflict || !state || needsRefresh);
      if (conflict) settingsFeedback(text, true);
      return false;
    } finally {
      busy = false;
      syncControls();
    }
  }

  async function loadSimulation() {
    const status = $("#policy-simulation");
    const request = ++sampleRequest;
    status.textContent = "正在读取示例…";
    try {
      const value = await api("/simulation");
      if (request !== sampleRequest) return;
      const action = {reuse: "复用", rerun: "重算", new_sample: "新采样"}[value.action];
      const removed = value.evicted.length ? value.evicted.join("、") : "无";
      status.textContent = `基于版本 ${value.revision}：示例搬运需 ${value.transfer_seconds} 秒，选择${action}。原有 ${value.initial_bytes / 1e6} MB，保留 ${value.retained_bytes / 1e6} MB，模拟淘汰：${removed}。`;
    } catch (error) {
      if (request === sampleRequest) status.textContent = error.message;
    }
  }
  sample.ontoggle = () => { if (sample.open) void loadSimulation(); };

  function showManualProposal(proposal) {
    if (!proposal) {
      resetForm();
      settingsFeedback("设置没有变化。");
      return;
    }
    if (!host.isConnected) return;
    manualProposal = proposal;
    $("#policy-confirm-title").textContent = proposal.source === "undo" ? "核对撤回内容" : "核对策略修改";
    $("#policy-diff").replaceChildren(changeRows(proposal.diff, true));
    $("#policy-confirm-impact").textContent = proposalImpact(proposal.diff);
    $("#policy-confirm-error").textContent = "";
    dialog.showModal();
  }

  const messageRenderer = import("../agent/assets/message.js").then(module => module.renderMessage).catch(() => null);

  function appendMessage(role, text, renderMessage) {
    const item = document.createElement("div");
    item.className = "policy-message";
    item.dataset.role = role;
    const author = document.createElement("div");
    author.className = "policy-message-author";
    if (role === "assistant") {
      author.innerHTML = `<span class="policy-message-avatar"><svg class="icon" aria-hidden="true"><use href="#i-chat" /></svg></span>策略助手`;
    } else {
      author.textContent = "你";
    }
    const body = document.createElement("div");
    body.className = "policy-message-body";
    if (renderMessage) body.innerHTML = renderMessage(text);
    else body.textContent = text;
    item.append(author, body);
    $("#policy-chat").append(item);
    return item;
  }

  function finishProposal(text, status) {
    if (!agentProposal) return;
    const {card, badge, actions} = agentProposal;
    if (actions.contains(document.activeElement)) card.focus({preventScroll: true});
    card.dataset.status = status;
    badge.textContent = text;
    actions.remove();
    agentProposal = null;
    $("#policy-pending-dot").hidden = true;
  }

  function showAgentProposal(proposal, reply) {
    finishProposal("已被新提案替代", "expired");
    const card = document.createElement("article");
    card.className = "policy-proposal";
    card.dataset.status = "pending";
    card.tabIndex = -1;
    card.innerHTML = `
      <div class="policy-section-title"><h3>修改提案</h3><span class="pill" role="status">待确认</span></div>
      <div class="policy-proposal-changes"></div>
      <p class="small muted policy-proposal-impact"></p>
      <div class="policy-actions"><button class="btn primary" type="button">确认并保存</button><button class="btn" type="button">取消</button></div>`;
    card.querySelector(".policy-proposal-changes").append(changeRows(proposal.diff, true));
    card.querySelector(".policy-proposal-impact").textContent = proposalImpact(proposal.diff);
    const actions = card.querySelector(".policy-actions");
    const [confirm, cancel] = actions.querySelectorAll("button");
    agentProposal = {proposal, card, badge: card.querySelector(".pill"), actions, confirm, cancel};
    $("#policy-pending-dot").hidden = false;
    reply.append(card);
    cancel.onclick = () => finishProposal("已取消", "dismissed");
    confirm.onclick = () => {
      chatFeedback();
      void run(async () => {
        if (dirty) throw new Error("请先保存或放弃手动编辑，再确认助手提案。");
        const saved = await confirmProposal(proposal);
        const revision = saved.history.find(event => event.proposal_id === proposal.id)?.revision ?? saved.revision;
        finishProposal(`已保存为版本 ${revision}`, "saved");
        render(saved);
        settingsFeedback();
      }, "chat");
    };
  }

  function confirmProposal(proposal) {
    return api("/confirm", {expected_revision: proposal.revision, proposal_id: proposal.id});
  }

  edit.onclick = () => {
    settingsFeedback();
    setEditing(true);
    form.elements.reuse_policy.focus();
  };
  $("#policy-discard").onclick = () => {
    resetForm();
    setEditing(false);
    edit.focus();
  };
  form.oninput = () => {
    dirty = true;
    $("#policy-edit-description").textContent = modeDescriptions[form.elements.reuse_policy.value];
  };
  form.onsubmit = event => {
    event.preventDefault();
    const values = new FormData(form);
    const seconds = values.get("transfer_limit_seconds");
    const gb = values.get("storage_limit_bytes");
    const config = {
      reuse_policy: values.get("reuse_policy"),
      transfer_limit_seconds: seconds === "" ? null : Number(seconds),
      storage_limit_bytes: gb === "" ? null : Math.round(Number(gb) * GB),
      retention: values.get("retention"),
    };
    settingsFeedback();
    void run(async () => showManualProposal((await api("/preview", {expected_revision: state.revision, config})).proposal));
  };
  function reload(area) {
    if (dirty && !window.confirm("放弃尚未保存的手动编辑并读取最新设置？")) return;
    void run(async () => {
      render(await api());
      settingsFeedback("已读取最新设置。");
      chatFeedback();
    }, area);
  }
  refresh.onclick = () => reload("settings");
  chatRefresh.onclick = () => reload("chat");
  undo.onclick = () => {
    settingsFeedback();
    void run(async () => {
      if (dirty) throw new Error("请先保存或放弃手动编辑，再撤回历史修改。");
      showManualProposal((await api("/undo-preview", {expected_revision: state.revision})).proposal);
    });
  };
  dialog.addEventListener("cancel", event => { if (busy) event.preventDefault(); });
  dialog.addEventListener("close", () => { manualProposal = null; });
  dialogCancel.onclick = () => dialog.close();
  dialogConfirm.onclick = async () => {
    const focusAfterSave = manualProposal?.source === "undo" ? undo : edit;
    if (await run(async () => {
      const saved = await confirmProposal(manualProposal);
      render(saved);
      dialog.close();
      settingsFeedback(`策略已保存为版本 ${saved.revision}。`);
      chatFeedback();
    })) focusAfterSave.focus();
  };

  message.oninput = syncControls;
  message.onkeydown = event => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    if (!send.disabled) chatForm.requestSubmit();
  };
  for (const suggestion of suggestions) {
    suggestion.onclick = () => {
      message.value = suggestion.textContent;
      syncControls();
      message.focus();
      chatForm.requestSubmit();
    };
  }
  chatForm.onsubmit = async event => {
    event.preventDefault();
    const text = message.value.trim();
    if (!text || send.disabled) return;
    chatFeedback();
    appendMessage("user", text);
    $("#policy-chat-start").hidden = true;
    $("#policy-chat-status").textContent = "助手正在回复…";
    scrollChat();
    const ok = await run(async () => {
      const result = await api("/messages", {expected_revision: state.revision, message: text});
      const reply = appendMessage("assistant", result.reply, await messageRenderer);
      if (result.proposal) showAgentProposal(result.proposal, reply);
    }, "chat");
    if (ok) message.value = "";
    $("#policy-chat-status").textContent = "";
    syncControls();
    scrollChat();
  };
  void run(async () => render(await api())).then(ok => {
    if (!ok) chatFeedback($("#policy-feedback").textContent, true);
  });
}
