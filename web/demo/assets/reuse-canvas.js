/* Illustrative reuse/storage workspace. No scientific execution or file mutation. */
window.ReuseCanvas = (() => {
  const escape = (value) =>
    String(value).replace(
      /[&<>"']/g,
      (ch) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[ch],
    );
  const views = { lineage: "产物关系", plan: "复用计划", storage: "存储位置" };
  const node = (id, title, kind, status, x, y, description, facts) => ({
    id,
    title,
    kind,
    status,
    x,
    y,
    description,
    facts,
  });
  function graph(view, reuse, cleaned) {
    if (view === "storage")
      return {
        nodes: [
          node(
            "asset",
            "骨架 B1",
            "科学产物",
            cleaned ? "1 份产物 · 1 个可读副本" : "1 份产物 · 2 个副本",
            40,
            180,
            "同一份产物可以拥有多个物理副本，来源记录独立保留。",
            [
              ["生成者", "成员甲"],
              ["共享范围", "项目团队"],
              ["管理对象", "副本，不是删除产物记录"],
            ],
          ),
          node(
            "cache",
            "计算节点缓存",
            "缓存副本",
            cleaned ? "演示：已移除" : "可整理 · 12 MB",
            370,
            70,
            "示例假设：该缓存当前没有活跃任务使用，共享存储中仍有完整副本。",
            [
              ["位置", "计算节点 / 缓存区"],
              ["使用状态", "无活跃任务（示例）"],
              ["整理后", "下次使用需从共享存储读取"],
            ],
          ),
          node(
            "shared",
            "共享存储",
            "受保护副本",
            "保留 · 12 MB",
            370,
            300,
            "项目保留要求保护此副本，不能被此次缓存整理移除。",
            [
              ["保护原因", "项目固定保留"],
              ["读取权限", "团队成员（示例）"],
              ["完整性", "检查通过（示例）"],
            ],
          ),
          node(
            "claim",
            "项目保留要求",
            "保留规则",
            "至少保留 1 份",
            700,
            300,
            "成员解除个人保留，不会自动取消项目的共同保留要求。",
            [
              ["适用对象", "骨架 B1"],
              ["要求", "共享存储保留完整副本"],
              ["过期动作", "重新检查引用与保护"],
            ],
          ),
        ],
        edges: [
          ["asset", "cache", "副本"],
          ["asset", "shared", "副本"],
          ["claim", "shared", "保护"],
        ],
      };
    if (view === "plan")
      return {
        nodes: [
          node(
            "candidate",
            "已有骨架 B1",
            "候选产物",
            "团队共享 · 条件符合",
            30,
            60,
            "示例请求允许沿用固定骨架 B1。是否采用由本次计划决定。",
            [
              ["请求骨架", "B1"],
              ["候选骨架", "B1"],
              ["文件 / 权限", "完整 / 可读取（示例）"],
            ],
          ),
          node(
            "backbone",
            "骨架输入",
            "本次计划",
            reuse ? "采用 B1" : "重新生成",
            330,
            60,
            reuse
              ? "采用指定骨架，省去本次骨架生成。"
              : "演示强制重算。生成结果未知，下游应等待真实输出。",
            [
              ["采用方式", reuse ? "用户选定已有输入" : "强制重算"],
              ["注意", "不把旧结果当作新随机样本"],
            ],
          ),
          node(
            "mpnn",
            "ProteinMPNN",
            "待执行步骤",
            "生成新序列",
            630,
            60,
            "用户要求新增序列，仍需执行采样。",
            [
              ["输入", reuse ? "骨架 B1" : "待新骨架产生"],
              ["采样意图", "新增样本"],
              ["运行状态", "未提交"],
            ],
          ),
          node(
            "msa",
            "MSA 搜索",
            "待执行步骤",
            "待序列确定",
            630,
            300,
            "新序列产生后再按查询、库快照及搜索设置匹配候选。",
            [
              ["候选判断", "暂未进行"],
              ["原因", "输入序列尚未产生"],
            ],
          ),
          node(
            "boltz",
            "Boltz",
            "待执行步骤",
            "待上游确定",
            330,
            300,
            "需要序列与本次配置；输入未确定前不能承诺缓存命中。",
            [
              ["输入", "序列与所需 MSA"],
              ["运行状态", "未提交"],
            ],
          ),
        ],
        edges: [
          ...(reuse ? [["candidate", "backbone", "采用"]] : []),
          ["backbone", "mpnn", "骨架"],
          ["mpnn", "msa", "新序列"],
          ["msa", "boltz", "MSA"],
        ],
      };
    return {
      nodes: [
        node(
          "rfd",
          "RFdiffusion",
          "生成运行",
          "成员甲 · 示例 E01",
          25,
          190,
          "生成共享骨架的原始运行。后续使用不会改变这次生成来源。",
          [
            ["模型", "RFdiffusion"],
            ["输出", "骨架 B1"],
            ["证据", "本图为教学场景，非真实运行"],
          ],
        ),
        node(
          "b1",
          "骨架 B1",
          "科学产物",
          "项目共享 · 2 次使用",
          310,
          190,
          "成员甲和成员乙沿用同一骨架，分别设计新序列。",
          [
            ["类型", "骨架 / PDB"],
            ["来源", "示例运行 E01"],
            ["使用者", "成员甲、成员乙"],
            ["副本", "计算节点缓存、共享存储"],
          ],
        ),
        node(
          "mpnn-a",
          "ProteinMPNN",
          "生成运行",
          "成员甲 · 示例 E02",
          600,
          55,
          "以 B1 为输入生成成员甲的序列，记录新的运行与输出。",
          [
            ["输入", "骨架 B1"],
            ["意图", "新增序列"],
            ["输出", "序列 S1"],
          ],
        ),
        node(
          "mpnn-b",
          "ProteinMPNN",
          "生成运行",
          "成员乙 · 示例 E03",
          600,
          325,
          "共享输入，独立生成。成员乙的结果保留自己的生成来源。",
          [
            ["输入", "骨架 B1"],
            ["意图", "新增序列"],
            ["输出", "序列 S2"],
          ],
        ),
        node(
          "s1",
          "序列 S1",
          "科学产物",
          "成员甲 · FASTA",
          890,
          55,
          "后续搜索与预测按这条序列的真实内容判断。",
          [
            ["来源", "示例 E02"],
            ["后续", "搜索与预测（本图未展开）"],
          ],
        ),
        node(
          "s2",
          "序列 S2",
          "科学产物",
          "成员乙 · FASTA",
          890,
          325,
          "序列 S2 是新的产物，不把骨架复用等同于序列复用。",
          [
            ["来源", "示例 E03"],
            ["后续", "搜索与预测（本图未展开）"],
          ],
        ),
      ],
      edges: [
        ["rfd", "b1", "生成"],
        ["b1", "mpnn-a", "作为输入"],
        ["b1", "mpnn-b", "作为输入"],
        ["mpnn-a", "s1", "生成"],
        ["mpnn-b", "s2", "生成"],
      ],
    };
  }
  function mount(root) {
    let view = "lineage",
      selected = "b1",
      reuse = true,
      cleaned = false,
      preview = false;
    let camera = { x: 20, y: 30, zoom: 1 },
      data,
      drag,
      suppressClick = false;
    const positions = {},
      lifecycle = new AbortController();
    const on = (el, event, fn, options = {}) =>
      el.addEventListener(event, fn, { ...options, signal: lifecycle.signal });
    root.innerHTML = `<section class="reuse-workspace" aria-label="复用与存储关系画布">
      <div class="reuse-top"><div><span class="eyebrow">REUSE EXPLORER</span><h2>把已有成果接到下一次探索</h2><p>示例场景：团队共享骨架，分别设计新序列。</p></div></div>
      <div class="reuse-tabs" role="tablist" aria-label="查看方式">${Object.entries(
        views,
      )
        .map(
          ([key, label]) =>
            `<button role="tab" data-view="${key}" aria-selected="${view === key}">${label}</button>`,
        )
        .join("")}</div>
      <div class="reuse-layout"><div class="reuse-board"><div class="reuse-toolbar"><span class="reuse-context"></span><div><button class="btn" data-camera="out" aria-label="缩小画布">−</button><span class="reuse-zoom">100%</span><button class="btn" data-camera="in" aria-label="放大画布">＋</button><button class="btn" data-camera="fit">适应画布</button></div></div>
      <div class="reuse-viewport" tabindex="0" role="region" aria-label="关系画布，可拖动空白平移，方向键平移，加减键缩放"><div class="reuse-world"><svg class="reuse-wires" aria-hidden="true"></svg><div class="reuse-nodes"></div></div></div>
      <div class="reuse-legend"><span>▭ 运行 / 计划</span><span>▱ 产物 / 副本</span><span>拖动节点调整位置 · 拖动空白平移 · 滚轮缩放</span></div></div>
      <aside class="reuse-detail" aria-label="选中节点详情"></aside></div></section>`;
    const $ = (s) => root.querySelector(s);
    const viewport = $(".reuse-viewport"),
      world = $(".reuse-world");
    function applyCamera() {
      world.style.transform = `translate(${camera.x}px,${camera.y}px) scale(${camera.zoom})`;
      $(".reuse-zoom").textContent = `${Math.round(camera.zoom * 100)}%`;
    }
    function fit() {
      const xmax = Math.max(...data.nodes.map((n) => n.x + 230)),
        ymax = Math.max(...data.nodes.map((n) => n.y + 108));
      camera.zoom = Math.max(
        0.2,
        Math.min(
          1,
          (viewport.clientWidth - 40) / xmax,
          (viewport.clientHeight - 40) / ymax,
        ),
      );
      camera.x = (viewport.clientWidth - xmax * camera.zoom) / 2;
      camera.y = (viewport.clientHeight - ymax * camera.zoom) / 2;
      applyCamera();
    }
    function zoom(
      factor,
      x = viewport.clientWidth / 2,
      y = viewport.clientHeight / 2,
    ) {
      const next = Math.max(0.2, Math.min(1.8, camera.zoom * factor)),
        ratio = next / camera.zoom;
      camera.x = x - (x - camera.x) * ratio;
      camera.y = y - (y - camera.y) * ratio;
      camera.zoom = next;
      applyCamera();
    }
    function draw() {
      $(".reuse-nodes").innerHTML = data.nodes
        .map(
          (n) =>
            `<button class="reuse-node ${n.kind.includes("产物") || n.kind.includes("副本") ? "is-asset" : ""} ${n.id === selected ? "is-selected" : ""}" data-node="${n.id}" style="left:${n.x}px;top:${n.y}px" aria-pressed="${n.id === selected}"><span>${escape(n.kind)}</span><strong>${escape(n.title)}</strong><small>${escape(n.status)}</small></button>`,
        )
        .join("");
      $(".reuse-wires").innerHTML =
        `<defs><marker id="reuse-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#a1a8c3"/></marker></defs>` +
        data.edges
          .map(([a, b, label]) => {
            const s = data.nodes.find((n) => n.id === a),
              t = data.nodes.find((n) => n.id === b);
            const right = t.x >= s.x,
              x1 = s.x + (right ? 230 : 0),
              y1 = s.y + 54,
              x2 = t.x + (right ? 0 : 230),
              y2 = t.y + 54;
            const middle = (x1 + x2) / 2;
            return `<path d="M${x1},${y1} C${middle},${y1} ${middle},${y2} ${x2},${y2}" fill="none" stroke="#a1a8c3" stroke-width="2" marker-end="url(#reuse-arrow)"/><text x="${middle}" y="${(y1 + y2) / 2 - 10}" text-anchor="middle">${label}</text>`;
          })
          .join("");
    }
    function details() {
      const n = data.nodes.find((n) => n.id === selected);
      $(".reuse-detail").innerHTML =
        `<span class="eyebrow">${views[view]} / 节点详情</span><h3>${escape(n.title)}</h3><span class="pill">${escape(n.status)}</span><p>${escape(n.description)}</p><dl>${n.facts.map(([k, v]) => `<div><dt>${escape(k)}</dt><dd>${escape(v)}</dd></div>`).join("")}</dl>
        ${view === "lineage" ? `<div class="reuse-detail-actions"><button class="btn primary" data-jump="plan">查看复用计划</button><button class="btn" data-jump="storage">查看存储副本</button></div>` : ""}
        ${view === "plan" ? `<div class="reuse-choice"><label for="reuse-mode">骨架处理方式</label><select id="reuse-mode"><option value="reuse" ${reuse ? "selected" : ""}>沿用共享骨架 B1</option><option value="compute" ${!reuse ? "selected" : ""}>重新生成骨架</option></select><p>仅更新演示计划。新序列仍需采样，下游保持待判断。</p></div>` : ""}
        ${view === "storage" ? `<div class="reuse-choice"><b>缓存整理预览</b><p>目标：计算节点上的 B1 缓存。</p>${preview ? `<div class="reuse-preview" role="status">预计释放 12 MB；共享副本仍保留；无活跃任务受影响。<br>上述检查均为示例假设。</div>` : ""}<button class="btn ${preview ? "primary" : ""}" data-clean ${cleaned ? "disabled" : ""}>${cleaned ? "演示已完成" : preview ? "模拟移除缓存副本" : "预览整理影响"}</button>${cleaned ? '<button class="link-btn" data-restore>恢复示例</button>' : ""}</div>` : ""}`;
    }
    function show(next = view) {
      if (next !== view) {
        view = next;
        selected =
          view === "lineage" ? "b1" : view === "plan" ? "candidate" : "cache";
      }
      data = graph(view, reuse, cleaned);
      data.nodes.forEach((n) =>
        Object.assign(n, positions[view]?.[n.id] || {}),
      );
      root
        .querySelectorAll("[data-view]")
        .forEach((b) =>
          b.setAttribute("aria-selected", b.dataset.view === view),
        );
      $(".reuse-context").textContent = {
        lineage: "生成来源 → 共享产物 → 后续使用",
        plan: "本次意图：固定骨架，新增序列",
        storage: "骨架 B1 · 物理副本与保留要求",
      }[view];
      draw();
      details();
      fit();
    }
    on(root, "click", (e) => {
      if (suppressClick && viewport.contains(e.target)) {
        suppressClick = false;
        return;
      }
      suppressClick = false;
      const target = e.target.closest("button");
      if (!target) return;
      if (target.dataset.view || target.dataset.jump)
        show(target.dataset.view || target.dataset.jump);
      if (target.dataset.node) {
        selected = target.dataset.node;
        draw();
        details();
        $(".reuse-nodes")
          .querySelector(`[data-node="${selected}"]`)
          .focus({ preventScroll: true });
      }
      if (target.dataset.camera) {
        const action = target.dataset.camera;
        action === "fit" ? fit() : zoom(action === "in" ? 1.2 : 1 / 1.2);
      }
      if (target.hasAttribute("data-clean")) {
        if (preview) {
          cleaned = true;
        }
        preview = true;
        show();
      }
      if (target.hasAttribute("data-restore")) {
        cleaned = false;
        preview = false;
        show();
      }
    });
    on(root, "change", (e) => {
      if (e.target.id === "reuse-mode") {
        reuse = e.target.value === "reuse";
        data = graph(view, reuse, cleaned);
        data.nodes.forEach((n) =>
          Object.assign(n, positions[view]?.[n.id] || {}),
        );
        draw();
        details();
        $("#reuse-mode").focus();
      }
    });
    on(
      viewport,
      "wheel",
      (e) => {
        e.preventDefault();
        const rect = viewport.getBoundingClientRect();
        zoom(
          e.deltaY < 0 ? 1.08 : 1 / 1.08,
          e.clientX - rect.left,
          e.clientY - rect.top,
        );
      },
      { passive: false },
    );
    on(viewport, "pointerdown", (e) => {
      if (e.button !== 0) return;
      suppressClick = false;
      const n = data.nodes.find(
        (n) => n.id === e.target.closest("[data-node]")?.dataset.node,
      );
      drag = {
        id: n?.id,
        startX: e.clientX,
        startY: e.clientY,
        x: n ? n.x : camera.x,
        y: n ? n.y : camera.y,
      };
      viewport.setPointerCapture(e.pointerId);
    });
    on(viewport, "pointermove", (e) => {
      if (!drag) return;
      const dx = e.clientX - drag.startX,
        dy = e.clientY - drag.startY;
      if (Math.hypot(dx, dy) < 4 && !suppressClick) return;
      suppressClick = true;
      if (drag.id) {
        const n = data.nodes.find((n) => n.id === drag.id);
        n.x = Math.max(0, Math.min(1600, drag.x + dx / camera.zoom));
        n.y = Math.max(0, Math.min(1000, drag.y + dy / camera.zoom));
        (positions[view] ??= {})[n.id] = { x: n.x, y: n.y };
        draw();
      } else {
        camera.x = drag.x + dx;
        camera.y = drag.y + dy;
        applyCamera();
      }
    });
    on(viewport, "pointerup", (e) => {
      const id = drag?.id;
      drag = null;
      if (id && !suppressClick) {
        selected = id;
        draw();
        details();
      }
      viewport.releasePointerCapture(e.pointerId);
    });
    on(viewport, "pointercancel", () => {
      drag = null;
      suppressClick = false;
    });
    on(root, "keydown", (e) => {
      const tab = e.target.closest("[data-view]");
      if (tab && ["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
        e.preventDefault();
        const keys = Object.keys(views),
          index = keys.indexOf(view);
        const next =
          e.key === "Home"
            ? 0
            : e.key === "End"
              ? 2
              : (index + (e.key === "ArrowRight" ? 1 : 2)) % 3;
        show(keys[next]);
        root.querySelector(`[data-view="${keys[next]}"]`).focus();
      }
      const id = e.target.closest("[data-node]")?.dataset.node;
      const delta = {
        ArrowLeft: [-20, 0],
        ArrowRight: [20, 0],
        ArrowUp: [0, -20],
        ArrowDown: [0, 20],
      }[e.key];
      if (id && delta) {
        e.preventDefault();
        const n = data.nodes.find((n) => n.id === id);
        n.x = Math.max(0, Math.min(1600, n.x + delta[0]));
        n.y = Math.max(0, Math.min(1000, n.y + delta[1]));
        (positions[view] ??= {})[id] = { x: n.x, y: n.y };
        draw();
        root
          .querySelector(`[data-node="${id}"]`)
          .focus({ preventScroll: true });
      }
    });
    on(viewport, "keydown", (e) => {
      if (e.target !== viewport) return;
      const delta = {
        ArrowLeft: [35, 0],
        ArrowRight: [-35, 0],
        ArrowUp: [0, 35],
        ArrowDown: [0, -35],
      }[e.key];
      if (delta) {
        e.preventDefault();
        camera.x += delta[0];
        camera.y += delta[1];
        applyCamera();
      }
      if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        zoom(1.2);
      }
      if (e.key === "-") {
        e.preventDefault();
        zoom(1 / 1.2);
      }
      if (e.key === "0") fit();
    });
    const resize = new ResizeObserver(() => fit());
    resize.observe(viewport);
    show();
    return {
      destroy() {
        resize.disconnect();
        lifecycle.abort();
      },
    };
  }
  return { mount };
})();
