const labels = {
  reuse_policy: "默认复用方式",
  transfer_limit_seconds: "搬运时间阈值",
  storage_limit_bytes: "空间上限",
  retention: "保留策略",
};
const modes = {
  allow_reuse: "允许复用", force_rerun: "强制重算", new_sample: "新采样",
};
const retention = { lru: "LRU（最久未用优先淘汰）", cost: "本项目策略" };
const GB = 1e9;

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
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error || "无法读取策略");
    error.status = response.status;
    throw error;
  }
  return result;
}

function changeRows(diff) {
  const list = document.createElement("ul");
  list.className = "policy-changes";
  for (const {field, before, after} of diff) {
    const item = document.createElement("li");
    item.textContent = `${labels[field]}：${valueLabel(field, before)} → ${valueLabel(field, after)}`;
    list.append(item);
  }
  return list;
}

export function mountPolicy(host) {
  host.innerHTML = `
    <div class="policy-columns">
      <form class="panel policy-form" id="policy-settings">
        <h2>工作区默认策略</h2>
        <p id="policy-revision" class="small muted" aria-live="polite">正在读取设置…</p>
        <fieldset disabled>
          <label>默认复用方式<select name="reuse_policy">
            <option value="allow_reuse">允许复用</option>
            <option value="force_rerun">强制重算</option>
            <option value="new_sample">新采样</option>
          </select></label>
          <p class="small muted">提交真实实验时默认采用此设置，可单次覆盖。</p>
          <div class="policy-limits">
            <label>搬运时间阈值（秒）<input type="number" min="0" step="any" name="transfer_limit_seconds" placeholder="未设置"></label>
            <label>空间上限（GB）<input type="number" min="0.000000001" max="9007199.254740991" step="any" name="storage_limit_bytes" placeholder="未设置"></label>
          </div>
          <label>保留策略<select name="retention">
            <option value="lru">LRU（最久未用优先淘汰）</option>
            <option value="cost">本项目策略</option>
          </select></label>
          <p class="small muted">阈值、空间上限和保留策略已支持保存，当前用于模拟自测。数值留空表示未设置。</p>
          <button class="btn primary" type="submit">预览修改</button>
        </fieldset>
        <button class="link-btn" type="button" id="policy-refresh">读取已保存设置</button>
      </form>
      <aside class="panel policy-assistant" aria-label="策略助手">
        <h2>策略助手</h2>
        <div id="policy-chat" class="policy-chat" role="log" aria-label="策略对话">
          <p class="small muted">可以问「强制重算和新采样有什么区别？」或说「默认改成强制重算」。</p>
        </div>
        <form id="policy-chat-form">
          <label for="policy-message">给助手留言</label>
          <textarea id="policy-message" maxlength="2000" rows="2" required></textarea>
          <button class="btn" type="submit">发送</button>
        </form>
      </aside>
    </div>
    <p id="policy-feedback" role="status" aria-live="polite"></p>
    <details class="panel policy-history"><summary>用示例检查已保存设置</summary><p id="policy-simulation" role="status"></p></details>
    <section class="panel policy-history" aria-labelledby="policy-history-title">
      <div class="policy-actions"><h2 id="policy-history-title">修改记录</h2><button class="btn" id="policy-undo" type="button">撤回最近一次修改</button></div>
      <div id="policy-history"></div>
    </section>
    <dialog class="modal policy-dialog" aria-labelledby="policy-confirm-title">
      <h2 id="policy-confirm-title">核对策略修改</h2>
      <div id="policy-diff"></div>
      <p id="policy-confirm-error" role="alert"></p>
      <div class="policy-actions"><button class="btn" id="policy-cancel">取消</button><button class="btn primary" id="policy-confirm">确认保存</button></div>
    </dialog>`;

  const $ = (selector) => host.querySelector(selector);
  const form = $("#policy-settings");
  const dialog = $("dialog");
  const fieldset = $("fieldset");
  const feedback = $("#policy-feedback");
  const confirm = $("#policy-confirm");
  const cancel = $("#policy-cancel");
  const undo = $("#policy-undo");
  const simulation = $("#policy-simulation");
  const chatForm = $("#policy-chat-form");
  const message = $("#policy-message");
  let state, pending, busy = false, dirty = false;

  function enableControls() {
    fieldset.disabled = busy || !state;
    undo.disabled = busy || !state?.history.length;
    confirm.disabled = cancel.disabled = busy;
    message.disabled = chatForm.querySelector("button").disabled = busy || !state;
    $("#policy-refresh").disabled = busy;
  }

  function render(saved) {
    state = saved;
    if (simulation.parentElement.open) loadSimulation();
    dirty = false;
    for (const [name, value] of Object.entries(saved.config)) {
      form.elements[name].value = name === "storage_limit_bytes" && value !== null ? value / GB : value ?? "";
    }
    $("#policy-revision").textContent = `版本 ${state.revision} · ${state.actor.display_name}`;
    const history = $("#policy-history");
    history.replaceChildren();
    if (!saved.history.length) {
      history.textContent = "暂无修改记录。";
      return;
    }
    const source = { manual: "手动修改", agent: "助手提案", undo: "撤回" };
    for (const event of [...saved.history].reverse()) {
      const entry = document.createElement("details");
      const title = document.createElement("summary");
      const time = new Date(event.time).toLocaleString("zh-CN", {hour12: false});
      title.textContent = `版本 ${event.revision} · ${source[event.source]} · ${event.actor.display_name} · ${time}`;
      entry.append(title, changeRows(Object.keys(labels)
        .filter(key => event.before[key] !== event.after[key])
        .map(field => ({field, before: event.before[field], after: event.after[field]}))));
      history.append(entry);
    }
  }

  async function run(action) {
    if (busy) return;
    busy = true;
    feedback.textContent = "";
    enableControls();
    try {
      await action();
    } catch (error) {
      const target = dialog.open ? $("#policy-confirm-error") : feedback;
      target.textContent = error.message;
    } finally {
      busy = false;
      enableControls();
    }
  }

  async function loadSimulation() {
    simulation.textContent = "正在读取示例…";
    try {
      const value = await api("/simulation");
      const action = {reuse: "复用", rerun: "重算", new_sample: "新采样"}[value.action];
      const removed = value.evicted.length ? value.evicted.join("、") : "无";
      simulation.textContent = `模拟版本 ${value.revision}。候选搬运需 ${value.transfer_seconds} 秒，选择${action}。示例原有 ${value.initial_bytes / 1e6} MB，保留 ${value.retained_bytes / 1e6} MB，模拟淘汰 ${removed}。`;
    } catch (error) {
      simulation.textContent = error.message;
    }
  }
  simulation.parentElement.addEventListener("toggle", () => {
    if (simulation.parentElement.open) loadSimulation();
  });

  function showProposal(proposal) {
    if (!proposal) {
      feedback.textContent = "当前设置没有变化。";
      return;
    }
    if (!host.isConnected) return;
    pending = proposal;
    $("#policy-confirm-error").textContent = "";
    $("#policy-diff").replaceChildren(changeRows(proposal.diff));
    dialog.showModal();
  }

  function appendMessage(speaker, text) {
    const item = document.createElement("p");
    const name = document.createElement("strong");
    name.textContent = speaker + " ";
    item.append(name, document.createTextNode(text));
    const chat = $("#policy-chat");
    chat.append(item);
    chat.scrollTop = chat.scrollHeight;
  }

  form.oninput = () => { dirty = true; };
  form.onsubmit = (event) => {
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
    run(async () => {
      const result = await api("/preview", {expected_revision: state.revision, config});
      if (!result.proposal) dirty = false;
      showProposal(result.proposal);
    });
  };
  $("#policy-refresh").onclick = () => run(async () => {
    if (dirty && !window.confirm("放弃表单中尚未保存的编辑并读取最新设置？")) return;
    render(await api());
  });
  undo.onclick = () => run(async () => {
    if (dirty) throw new Error("请先保存表单，或读取已保存设置。");
    showProposal((await api("/undo-preview", {expected_revision: state.revision})).proposal);
  });
  dialog.addEventListener("cancel", event => { if (busy) event.preventDefault(); });
  dialog.addEventListener("close", () => { pending = null; });
  cancel.onclick = () => dialog.close();
  confirm.onclick = () => run(async () => {
    const saved = await api("/confirm", {expected_revision: pending.revision, proposal_id: pending.id});
    render(saved);
    dialog.close();
    feedback.textContent = "策略已保存。";
  });
  chatForm.onsubmit = (event) => {
    event.preventDefault();
    const text = message.value.trim();
    if (!text || busy) return;
    run(async () => {
      if (dirty) throw new Error("请先保存表单，或读取已保存设置，再让助手修改。");
      appendMessage("你", text);
      feedback.textContent = "正在等待助手回复…";
      const result = await api("/messages", {expected_revision: state.revision, message: text});
      message.value = "";
      feedback.textContent = "";
      appendMessage("助手", result.reply);
      if (result.proposal) showProposal(result.proposal);
    });
  };
  enableControls();
  run(async () => render(await api()));
}
