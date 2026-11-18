"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const api = async (path, body) => {
    const response = await fetch(
      "./api/engine/" + path,
      body
        ? {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }
        : {},
    );
    const result = await response.json();
    if (!response.ok)
      throw Error(
        typeof result.error === "string"
          ? result.error
          : result.error?.message || "引擎请求失败",
      );
    return result;
  };
  let declaration,
    timer,
    clientRef,
    pendingPayload,
    pending = false;
  const saved = JSON.parse(
    localStorage.getItem("ai4s-engine-requests") || "[]",
  );
  const states = {
    accepted: "已接收",
    submitted: "等待运行",
    running: "运行中",
    finished: "已完成",
    failed: "失败",
  };
  const actions = {
    reuse: "复用已有结果",
    rerun: "重新计算",
    new_sample: "更换种子采样",
  };
  const element = (tag, value) => {
    const node = document.createElement(tag);
    node.textContent = value;
    return node;
  };
  const history = () => {
    $("history").replaceChildren(
      ...saved
        .slice(-12)
        .reverse()
        .map((id) => {
          const li = element("li", ""),
            a = element("a", id);
          a.href = "#" + id;
          li.append(a);
          return li;
        }),
    );
  };
  const renderFields = (group) => {
    Object.entries(declaration.parameters[group]).forEach(([name, rule]) => {
      const label = element("label", rule.label || name),
        input = document.createElement(rule.enum ? "select" : "input");
      input.name = group + "." + name;
      if (rule.enum)
        rule.enum.forEach((value) => {
          const option = element("option", value);
          option.value = value;
          input.append(option);
        });
      else
        input.type =
          rule.type === "boolean"
            ? "checkbox"
            : ["integer", "number"].includes(rule.type)
              ? "number"
              : "text";
      input.step = rule.type === "integer" ? "1" : "any";
      if (rule.minimum !== undefined) input.min = rule.minimum;
      if (rule.maximum !== undefined) input.max = rule.maximum;
      input.required = rule.required;
      const value = declaration.example.params[group][name] ?? rule.default;
      if (rule.type === "boolean") input.checked = !!value;
      else input.value = value ?? "";
      label.append(input);
      $(group).append(label);
    });
  };
  const values = (group) =>
    Object.fromEntries(
      Object.entries(declaration.parameters[group]).map(([name, rule]) => {
        const input = document.querySelector(`[name="${group}.${name}"]`);
        return [
          name,
          rule.type === "boolean"
            ? input.checked
            : ["number", "integer"].includes(rule.type)
              ? Number(input.value)
              : input.value,
        ];
      }),
    );
  const show = async (id) => {
    clearTimeout(timer);
    try {
      const status = await api("requests/" + encodeURIComponent(id));
      const dl = document.createElement("dl");
      const facts = [
        ["状态", states[status.state]],
        ["请求", status.request_id],
        ["执行方式", actions[status.decision?.action] || "等待决定"],
        ["理由", status.decision?.reason_text || "—"],
        ["实际种子", status.effective?.seed ?? "—"],
        ["过程 UUID", status.process?.uuid || "—"],
        ["复用来源", status.cached_from || "—"],
        ["模型身份", status.effective?.identity_digest || "身份未确定"],
        ["计算指纹", status.effective?.fingerprint || "等待计算"],
      ];
      facts.forEach(([key, value]) =>
        dl.append(element("dt", key), element("dd", String(value))),
      );
      $("status").replaceChildren(dl);
      if (status.error) $("status").append(element("p", status.error.message));
      $("outputs").replaceChildren();
      if (status.outputs) {
        $("outputs").append(element("h2", "产物"));
        for (const [port, uuid] of Object.entries(
          status.outputs.artifacts || {},
        )) {
          const link = element("a", port + " · 下载");
          link.href = "./api/engine/files/" + uuid;
          link.style.display = "block";
          $("outputs").append(link);
        }
      }
      const decisions = await api(
        "decisions?request_id=" + encodeURIComponent(id),
      );
      const provenance = status.process
        ? await api("nodes/" + status.process.uuid)
        : null;
      $("source").hidden = false;
      $("provenance").textContent = JSON.stringify(
        { decisions: decisions.records, provenance },
        null,
        2,
      );
      if (!["finished", "failed"].includes(status.state))
        timer = setTimeout(() => show(id), 4000);
    } catch (error) {
      $("error").textContent = error.message;
    }
  };
  $("workflow").onchange = () => {
    $("filter").hidden = $("workflow").value !== "mpnn_filter";
  };
  $("form").onsubmit = async (event) => {
    event.preventDefault();
    if (pending) return;
    pending = true;
    $("submit").disabled = true;
    $("error").textContent = "";
    clientRef ||= crypto.randomUUID();
    try {
      const file = $("pdb").files[0];
      if (!file || file.size > 1024 * 1024)
        throw Error("请选择不超过 1 MiB 的 PDB 文件");
      const upload = await api("uploads", {
        filename: file.name,
        content: await file.text(),
      });
      const workflow = $("workflow").value;
      const payload = {
        schema_version: "ai4s-request-1",
        client_ref: clientRef,
        requester: { member_id: "qhy", display_name: "曲鸿烨" },
        declaration: {
          task_id: declaration.task_id,
          version: declaration.version,
        },
        workflow,
        inputs: { pdb_file: { source: "upload", upload_id: upload.upload_id } },
        params: { inference: values("inference") },
        reuse_policy: $("policy").value,
      };
      if (workflow === "mpnn_filter") payload.params.filter = values("filter");
      pendingPayload ||= payload;
      const status = await api("requests", pendingPayload);
      clientRef = null;
      pendingPayload = null;
      if (!saved.includes(status.request_id)) saved.push(status.request_id);
      localStorage.setItem(
        "ai4s-engine-requests",
        JSON.stringify(saved.slice(-30)),
      );
      history();
      location.hash = status.request_id;
      await show(status.request_id);
    } catch (error) {
      $("error").textContent = error.message;
    } finally {
      pending = false;
      $("submit").disabled = false;
    }
  };
  window.addEventListener("hashchange", () => {
    if (location.hash.startsWith("#req-")) show(location.hash.slice(1));
  });
  history();
  Promise.all([api("health"), api("declarations/proteinmpnn/1")])
    .then(([health, decl]) => {
      declaration = decl;
      renderFields("inference");
      renderFields("filter");
      $("health").textContent = "引擎已连接";
      $("submit").disabled = false;
      if (location.hash.startsWith("#req-")) show(location.hash.slice(1));
    })
    .catch((error) => {
      $("health").textContent = "引擎暂不可用";
      $("error").textContent = error.message;
    });
})();
