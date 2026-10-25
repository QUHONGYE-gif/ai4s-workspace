import {escapeHTML as esc} from './api.js';

// Visual grammar of live-panel's light-pastel presets: one titled stage frame
// per step, a white card with an icon tile inside it, orthogonal wires that
// end in an arrowhead at the next frame, dashed wires for a pending
// conversion, and one resident data dot per wire.
// This editor renders server state and real save events, so the skill's
// looping template, simulated machines and log are deliberately not used.
// https://github.com/ythx-101/live-panel-skill
const ROLES = {rfdiffusion: 'backbone', proteinmpnn: 'sequence', boltz: 'prediction'};
const ICONS = {
  backbone: '<path d="M12 2.9 3.8 7v10l8.2 4.1 8.2-4.1V7Z"/><path d="m3.8 7 8.2 4.1L20.2 7"/><path d="M12 11.1v10"/>',
  sequence: '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
  prediction: '<circle cx="12" cy="12" r="3.4"/><path d="M12 2.4v3.2M12 18.4v3.2M2.4 12h3.2M18.4 12h3.2"/>',
};
const NS = 'http://www.w3.org/2000/svg';
let previousWorkflow = null, previousRevision = null, previousNodes = new Map();
let flowFrame = null;

function summary(n) {
  const p = n.params;
  if (n.model_id === 'rfdiffusion') return `${p.length} aa · ${p.num_designs} 个骨架`;
  if (n.model_id === 'proteinmpnn') return `${p.num_seq_per_target} 条序列 · T ${p.sampling_temp}`;
  return `${p.diffusion_samples} 个样本 · ${p.msa_mode === 'empty' ? '空 MSA' : '已有 A3M'}`;
}

function formats(model) {
  const unique = dict => Object.values(dict).filter((v, i, all) => all.indexOf(v) === i).join(' / ');
  return {inputs: unique(model.inputs) || '无条件', outputs: unique(model.outputs)};
}

export function drawNodes(state, models, selected, select) {
  const pipeline = document.getElementById('pipeline');
  if (!pipeline) return;
  const hasSaved = previousWorkflow === state.draft.id && previousRevision !== null && state.draft.revision > previousRevision;
  const changed = new Set(state.draft.nodes.filter(n => hasSaved && previousNodes.get(n.id) !== JSON.stringify(n)).map(n => n.id));
  pipeline.innerHTML = state.draft.nodes.length ? state.draft.nodes.map((n, index) => {
    const model = models[n.model_id], role = ROLES[n.model_id] || 'backbone';
    const status = state.checks[n.id].status;
    const statusClass = status === '已登记' ? 'good' : status === '待补充' ? 'warn' : '';
    const {inputs, outputs} = formats(model);
    const active = selected === n.id;
    return `<div class="demo-stage role-${role}${active ? ' selected' : ''}">
      <div class="stage-head"><span class="stage-index">${String(index + 1).padStart(2, '0')}</span><span class="stage-title">${esc(model.role)}</span></div>
      <button class="demo-node${active ? ' selected' : ''}" data-node-id="${esc(n.id)}" aria-pressed="${active}">
        <span class="node-head"><span class="node-icon" aria-hidden="true"><svg viewBox="0 0 24 24">${ICONS[role]}</svg></span><span class="node-titles"><span class="model-name">${esc(model.name)}</span><span class="node-label">${esc(n.label)}</span></span></span>
        <span class="node-summary">${esc(summary(n))}</span>
        <span class="node-state ${statusClass}"><i class="state-dot" aria-hidden="true"></i>${esc(status)} · 未提交</span>
        <span class="node-formats"><span>${esc(inputs)}</span><span aria-hidden="true">→</span><span>${esc(outputs)}</span></span>
      </button>
    </div>`;
  }).join('') : '<div class="empty-graph">还没有科学步骤。点击「＋ 步骤」添加第一个模型。</div>';
  pipeline.querySelectorAll('[data-node-id]').forEach(button => button.addEventListener('click', () => select(button.dataset.nodeId)));
  previousWorkflow = state.draft.id; previousRevision = state.draft.revision;
  previousNodes = new Map(state.draft.nodes.map(n => [n.id, JSON.stringify(n)]));
  // One brief outline response to an actual saved revision; no fake worker
  // states, timers, calls, packet counts or scientific execution animation.
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
    pipeline.querySelectorAll('.demo-stage').forEach(stage => {
      const id = stage.querySelector('[data-node-id]')?.dataset.nodeId;
      if (!changed.has(id)) return;
      stage.animate([
        {boxShadow: '0 0 0 0px #7d4fb04d'}, {boxShadow: '0 0 0 7px #7d4fb01a'}, {boxShadow: '0 0 0 0px #7d4fb000'},
      ], {duration: 650, iterations: 1});
    });
  }
  requestAnimationFrame(() => drawWires(state, selected));
}

function svgEl(tag, attrs) {
  const node = document.createElementNS(NS, tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}

function stopFlow() {
  if (flowFrame !== null) cancelAnimationFrame(flowFrame);
  flowFrame = null;
}

// polyline -> path with rounded corners, the same shape the skill's loop view draws
function roundedPath(points, radius) {
  let d = `M${points[0].x.toFixed(1)},${points[0].y.toFixed(1)}`;
  for (let i = 1; i < points.length - 1; i++) {
    const a = points[i - 1], b = points[i], c = points[i + 1];
    const l1 = Math.hypot(b.x - a.x, b.y - a.y), l2 = Math.hypot(c.x - b.x, c.y - b.y);
    if (!l1 || !l2) continue;
    const r = Math.min(radius, l1 / 2, l2 / 2);
    const p1 = {x: b.x + (a.x - b.x) / l1 * r, y: b.y + (a.y - b.y) / l1 * r};
    const p2 = {x: b.x + (c.x - b.x) / l2 * r, y: b.y + (c.y - b.y) / l2 * r};
    d += `L${p1.x.toFixed(1)},${p1.y.toFixed(1)}Q${b.x.toFixed(1)},${b.y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
  }
  const end = points[points.length - 1];
  return d + `L${end.x.toFixed(1)},${end.y.toFixed(1)}`;
}

function stageOf(id) {
  const button = Array.from(document.querySelectorAll('[data-node-id]')).find(el => el.dataset.nodeId === id);
  return button ? (button.closest('.demo-stage') || button) : null;
}

export function drawWires(state, selected = document.querySelector('.demo-node.selected')?.dataset.nodeId) {
  const graph = document.getElementById('graph'), svg = document.getElementById('wires');
  if (!graph || !svg) return;
  stopFlow();
  const base = graph.getBoundingClientRect();
  svg.setAttribute('width', graph.scrollWidth);
  svg.setAttribute('height', graph.scrollHeight);
  svg.style.width = `${graph.scrollWidth}px`;
  svg.style.height = `${graph.scrollHeight}px`;
  svg.innerHTML = '';
  const drawn = [];
  state.draft.edges.forEach((edge, index) => {
    const a = stageOf(edge.source), b = stageOf(edge.target);
    if (!a || !b) return;
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    const x1 = ra.right - base.left + graph.scrollLeft, y1 = ra.top + ra.height / 2 - base.top + graph.scrollTop;
    const x2 = rb.left - base.left + graph.scrollLeft, y2 = rb.top + rb.height / 2 - base.top + graph.scrollTop;
    const lower = Math.max(ra.bottom, rb.bottom) - base.top + graph.scrollTop + 14 + index * 9;
    const mid = (x1 + x2) / 2;
    const points = x2 - x1 > 24
      ? (Math.abs(y1 - y2) < 2 ? [{x: x1, y: y1}, {x: x2, y: y2}]
        : [{x: x1, y: y1}, {x: mid, y: y1}, {x: mid, y: y2}, {x: x2, y: y2}])
      : [{x: x1, y: y1}, {x: x1 + 16, y: y1}, {x: x1 + 16, y: lower}, {x: x2 - 16, y: lower}, {x: x2 - 16, y: y2}, {x: x2, y: y2}];
    const path = svgEl('path', {
      d: roundedPath(points, 14), fill: 'none',
      stroke: edge.transform ? '#9aa0a8' : '#5f6670', 'stroke-width': 1.5,
      'stroke-linejoin': 'round', 'stroke-linecap': 'round', opacity: 0.9,
    });
    const active = edge.source === selected || edge.target === selected;
    if (edge.transform) path.setAttribute('stroke-dasharray', '7 5');
    if (active) {
      path.setAttribute('stroke', edge.transform ? '#9a6a0a' : '#6f66a8');
      path.setAttribute('stroke-width', 2);
      path.setAttribute('opacity', 1);
    }
    const title = svgEl('title', {});
    title.textContent = `${edge.source}.${edge.source_port} → ${edge.target}.${edge.target_port}${edge.transform ? '；FASTA→Boltz YAML 转换尚未接入' : ''}；仅表示配置依赖，未执行计算`;
    const group = svgEl('g', {});
    group.appendChild(title);
    group.appendChild(path);
    // arrowhead on the target border, like the skill's edge arrow
    const tip = points[points.length - 1], before = points[points.length - 2];
    const length = Math.hypot(tip.x - before.x, tip.y - before.y) || 1;
    const ux = (tip.x - before.x) / length, uy = (tip.y - before.y) / length, size = 6.5;
    group.appendChild(svgEl('polygon', {
      points: `${tip.x.toFixed(1)},${tip.y.toFixed(1)} ${(tip.x - ux * size + uy * size * 0.52).toFixed(1)},${(tip.y - uy * size - ux * size * 0.52).toFixed(1)} ${(tip.x - ux * size - uy * size * 0.52).toFixed(1)},${(tip.y - uy * size + ux * size * 0.52).toFixed(1)}`,
      fill: active ? (edge.transform ? '#9a6a0a' : '#6f66a8') : (edge.transform ? '#9aa0a8' : '#5f6670'),
    }));
    // the resident "data passes" dot: middle of the longest straight stretch
    let best = -1, middle = points[0];
    for (let i = 0; i + 1 < points.length; i++) {
      const seg = Math.hypot(points[i + 1].x - points[i].x, points[i + 1].y - points[i].y);
      if (seg > best) {
        best = seg;
        middle = {x: (points[i].x + points[i + 1].x) / 2, y: (points[i].y + points[i + 1].y) / 2};
      }
    }
    group.appendChild(svgEl('circle', {cx: middle.x.toFixed(1), cy: middle.y.toFixed(1), r: 3.2, fill: '#2f7d47', opacity: 0.85}));
    const label = edge.transform ? '需转换' : 'PDB';
    const text = svgEl('text', {class: 'wire-label', x: (x2 - x1 > 24 ? mid : (x1 + x2) / 2).toFixed(1), y: (Math.min(y1, y2) - 9).toFixed(1), 'text-anchor': 'middle'});
    text.textContent = label;
    group.appendChild(text);
    svg.appendChild(group);
    const len = path.getTotalLength();
    if (len > 12) drawn.push({path, len});
  });
  // gentle packets drifting along every wire (the skill's light theme keeps this small)
  if (drawn.length && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const dots = drawn.map((wire, index) => {
      const dot = svgEl('circle', {r: 2.6, fill: '#2f7d47', opacity: 0.9});
      svg.appendChild(dot);
      return {...wire, dot, offset: index * 0.5, speed: wire.len / 2600};
    });
    const started = performance.now();
    const tick = now => {
      const elapsed = now - started;
      dots.forEach(({dot, path, len, offset, speed}) => {
        const at = (elapsed * speed + offset * len) % len;
        const point = path.getPointAtLength(at);
        dot.setAttribute('cx', point.x.toFixed(1));
        dot.setAttribute('cy', point.y.toFixed(1));
      });
      flowFrame = requestAnimationFrame(tick);
    };
    flowFrame = requestAnimationFrame(tick);
  }
}
