import { api, post, operationId, escapeHTML as esc } from "./api.js";
import { mountDeclaration } from "./declaration.js";

// Lists and editors share the existing declaration API. This never publishes a task.
export async function mountTaskRegistry(host) {
  let editor;
  let catalog;
  let drafts;
  let trash;
  let pendingDelete;
  let disposed = false;
  const lifecycle = new AbortController();
  host.innerHTML = `<section class="task-registry" aria-label="任务注册中心"><div id="tr-list"></div><div id="tr-editor" hidden></div></section>`;
  const list = host.querySelector("#tr-list");
  const editorHost = host.querySelector("#tr-editor");

  function renderList() {
    const versions = catalog.tasks.flatMap((task) => task.versions);
    list.innerHTML = `
      <div class="registry-toolbar"><h2>任务定义</h2><button class="button primary" id="tr-new">新建声明草稿</button></div>
      <p class="field-hint registry-boundary">仓库版本与编辑草稿分开保存；网页加载声明不代表引擎已加载或可执行。</p>
      <p id="tr-error" class="inline-error" role="alert" hidden></p>
      <div class="registry-definitions">${
        catalog.tasks
          .map(
            (task) => `
        <article class="panel registry-task"><div class="panel-heading"><div><h3>${esc(task.name)}</h3><code>${esc(task.task_id)}</code></div><span class="pill">接口已核验</span></div>
        ${task.versions.map((version) => `<div class="registry-version"><div><strong>声明 v${esc(version.version)}</strong><p>仓库版本 · 网页已加载</p><span class="field-hint">${version.adapter_status === "source_supported" ? "有受支持适配器源码" : "执行适配器待支持"} · 网页提交未接通</span></div><div class="inline-actions"><button class="button" data-view-task="${esc(task.task_id)}" data-version="${esc(version.version)}">查看定义</button><button class="text-button" data-copy-task="${esc(task.task_id)}" data-version="${esc(version.version)}">创建编辑副本</button></div></div>`).join("")}</article>`,
          )
          .join("") || '<p class="field-hint">尚无已核验的仓库声明。</p>'
      }</div>
      <section class="registry-drafts" aria-labelledby="tr-drafts-title"><div class="registry-toolbar"><h2 id="tr-drafts-title">编辑草稿</h2><span class="field-hint">${drafts.length} 份 · 不改变仓库版本</span></div><div class="registry-draft-list">${drafts.map((draft) => `<article class="registry-draft"><div><strong>${esc(draft.name)}</strong><p><code>${esc(draft.task_id)}</code> · v${esc(draft.version)} · r${draft.revision}</p><span class="field-hint">${draft.status === "exported_not_deployed" ? "已校验导出，未部署" : "草稿，未发布"}${draft.issue_count ? ` · ${draft.issue_count} 项待补充` : " · 定义完整"}</span></div><div class="inline-actions"><button class="button" data-open-draft="${esc(draft.id)}">继续编辑</button><button class="text-button danger-text" data-delete-draft="${esc(draft.id)}" aria-label="删除草稿 ${esc(draft.name)}">删除</button></div></article>`).join("") || '<p class="field-hint">尚无草稿。可新建，或从仓库版本创建编辑副本。</p>'}</div></section>
      <details class="registry-trash"><summary>回收站 · ${trash.length}</summary><p class="field-hint">删除只移除编辑草稿，不影响仓库定义、已下载文件或实验。恢复后请重新校验导出。</p>${trash.map(draft => `<article class="registry-draft"><div><strong>${esc(draft.name)}</strong><p>${esc(draft.task_id)} · v${esc(draft.version)}</p></div><button class="button" data-restore-draft="${esc(draft.id)}">恢复草稿</button></article>`).join('') || '<p class="field-hint">回收站为空。</p>'}</details>
      <dialog class="modal small-modal" id="tr-delete" aria-labelledby="tr-delete-title"><div class="modal-head"><h2 id="tr-delete-title">删除声明草稿</h2></div><div class="modal-body"><p id="tr-delete-message"></p><p id="tr-delete-error" class="inline-error" role="alert" hidden></p><p class="field-hint">移入回收站后可恢复。不影响仓库正式定义、已导出文件和其他草稿。</p></div><div class="modal-foot"><button class="button" data-cancel-delete>取消</button><button class="button danger-text" data-confirm-delete>移入回收站</button></div></dialog>
      <details class="registry-planned"><summary>后续任务类型</summary><div class="registry-planned-grid">${catalog.planned.map((task) => `<div><strong>${esc(task.name)}</strong><p>${esc(task.purpose)}</p><span class="field-hint">声明与执行适配待接入</span></div>`).join("")}</div><p class="field-hint">新增工具先核验输入、参数、产物及适配器。仅凭名称不能生成可发布或可执行声明；本轮不提供未知工具的正式声明创建。</p></details>
      <dialog class="modal small-modal" id="tr-create" aria-labelledby="tr-create-title"><div class="modal-head"><h2 id="tr-create-title">新建声明草稿</h2><button class="icon-button" data-close-create aria-label="关闭新建声明">×</button></div><form id="tr-create-form"><div class="modal-body"><label class="field"><span>已核验的任务与依据版本</span><select id="tr-reference" required>${versions.map((item) => `<option value="${esc(item.task_id + "/" + item.version)}">${esc(item.name)} · v${esc(item.version)}</option>`).join("")}</select></label><label class="field spaced"><span>起点</span><select id="tr-template"><option value="empty">空白输入、参数和输出</option><option value="complete">复制完整的已核实定义</option></select></label><p class="field-hint">沿用所选版本的真实约束。新版本需在编辑器中明确设置，导出后再审核与部署。</p><p id="tr-create-error" class="inline-error" role="alert" hidden></p></div><div class="modal-foot"><button class="button" type="button" data-close-create>取消</button><button class="button primary" type="submit" ${versions.length ? "" : "disabled"}>创建草稿</button></div></form></dialog>`;
  }

  async function refresh() {
    [catalog, { drafts }, { drafts: trash }] = await Promise.all([
      api("/api/task-catalog"),
      api("/api/declaration-drafts"),
      api("/api/declaration-drafts?deleted=true"),
    ]);
    if (!disposed) renderList();
  }

  async function openEditor(options) {
    editor?.destroy();
    list.hidden = true;
    editorHost.hidden = false;
    editorHost.innerHTML = '<p role="status">正在读取声明…</p>';
    try {
      editor = await mountDeclaration(editorHost, {
        ...options,
        onBack: async () => {
          editor?.destroy();
          editorHost.hidden = true;
          list.hidden = false;
          await refresh();
        },
      });
    } catch (error) {
      editorHost.textContent = error.message;
      const back = document.createElement("button");
      back.className = "button";
      back.textContent = "返回注册中心";
      back.onclick = () => {
        editorHost.hidden = true;
        list.hidden = false;
      };
      editorHost.append(back);
    }
  }

  async function copy(task_id, version) {
    const draft = await post("/api/declaration-drafts", {
      task_id,
      version,
      template: "complete",
    });
    await openEditor({ draftId: draft.id });
  }

  let busy = false;
  host.addEventListener(
    "click",
    async (event) => {
      const button = event.target.closest("button");
      if (!button || busy) return;
      if (button.dataset.deleteDraft) {
        pendingDelete = drafts.find(draft => draft.id === button.dataset.deleteDraft);
        list.querySelector('#tr-delete-error').hidden = true;
        list.querySelector('#tr-delete-message').textContent = `删除「${pendingDelete.name}」v${pendingDelete.version} · r${pendingDelete.revision}？`;
        list.querySelector('#tr-delete').showModal();
        return;
      }
      if (button.hasAttribute('data-cancel-delete')) {
        list.querySelector('#tr-delete').close();
        pendingDelete = null;
        return;
      }
      if (button.id === "tr-new") list.querySelector("#tr-create").showModal();
      if (button.hasAttribute("data-close-create"))
        list.querySelector("#tr-create").close();
      if (
        !button.dataset.openDraft &&
        !button.dataset.viewTask &&
        !button.dataset.copyTask &&
        !button.dataset.restoreDraft &&
        !button.hasAttribute("data-confirm-delete")
      )
        return;
      busy = true;
      button.disabled = true;
      try {
        if (button.hasAttribute('data-confirm-delete') || button.dataset.restoreDraft) {
          const restoring = !!button.dataset.restoreDraft;
          const draft = restoring ? trash.find(item => item.id === button.dataset.restoreDraft) : pendingDelete;
          await post(`/api/declaration-drafts/${draft.id}/${restoring ? 'restore' : 'delete'}`, {
            expected_revision: draft.revision, operation_id: operationId(),
          });
          list.querySelector('#tr-delete').close();
          pendingDelete = null;
          await refresh();
        }
        if (button.dataset.openDraft)
          await openEditor({ draftId: button.dataset.openDraft });
        if (button.dataset.viewTask)
          await openEditor({
            taskId: button.dataset.viewTask,
            version: button.dataset.version,
            readOnly: true,
          });
        if (button.dataset.copyTask)
          await copy(button.dataset.copyTask, button.dataset.version);
      } catch (error) {
        const errorBox = list.querySelector('#tr-delete').open ? list.querySelector('#tr-delete-error') : list.querySelector('#tr-error');
        errorBox.textContent = error.message + (error.status === 409 ? ' 请关闭对话框并重新进入列表。' : '');
        errorBox.hidden = false;
      } finally {
        busy = false;
        button.disabled = false;
      }
    },
    { signal: lifecycle.signal },
  );

  host.addEventListener(
    "submit",
    async (event) => {
      if (event.target.id !== "tr-create-form") return;
      event.preventDefault();
      if (busy) return;
      busy = true;
      const button = event.target.querySelector('[type="submit"]');
      button.disabled = true;
      try {
        const [task_id, version] = list
          .querySelector("#tr-reference")
          .value.split("/");
        const draft = await post("/api/declaration-drafts", {
          task_id,
          version,
          template: list.querySelector("#tr-template").value,
        });
        list.querySelector("#tr-create").close();
        await openEditor({ draftId: draft.id });
      } catch (error) {
        list.querySelector("#tr-create-error").textContent = error.message;
        list.querySelector("#tr-create-error").hidden = false;
      } finally {
        busy = false;
        button.disabled = false;
      }
    },
    { signal: lifecycle.signal },
  );

  await refresh();
  return {
    redraw() {
      if (editorHost.hidden && !busy) refresh().catch(error => {
        const box = list.querySelector('#tr-error');
        if (box) { box.textContent = error.message; box.hidden = false; }
      });
    },
    pause() {
      host.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    },
    destroy() {
      disposed = true;
      lifecycle.abort();
      editor?.destroy();
    },
  };
}
