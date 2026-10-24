import {escapeHTML as esc} from './api.js';

// Visual adaptation of live-panel's light-pastel/motion grammar, not its
// looping template: this editor renders server state and real save events.
// https://github.com/ythx-101/live-panel-skill
const ROLES = {rfdiffusion:'backbone', proteinmpnn:'sequence', boltz:'prediction'};
let previousWorkflow = null, previousRevision = null, previousNodes = new Map();

function summary(n) {
  const p = n.params;
  if (n.model_id === 'rfdiffusion') return `${p.length} aa · ${p.num_designs} 个骨架`;
  if (n.model_id === 'proteinmpnn') return `${p.num_seq_per_target} 条序列 · T ${p.sampling_temp}`;
  return `${p.diffusion_samples} 个样本 · ${p.msa_mode === 'empty' ? '空 MSA' : '已有 A3M'}`;
}

export function drawNodes(state, models, selected, select) {
  const pipeline = document.getElementById('pipeline');
  const hasSaved = previousWorkflow === state.draft.id && previousRevision !== null && state.draft.revision > previousRevision;
  const changed = new Set(state.draft.nodes.filter(n => hasSaved && previousNodes.get(n.id) !== JSON.stringify(n)).map(n => n.id));
  pipeline.innerHTML = state.draft.nodes.length ? state.draft.nodes.map((n, index) => {
    const status = state.checks[n.id].status;
    const inputs = Object.values(models[n.model_id].inputs).filter((v, i, all) => all.indexOf(v) === i).join(' / ') || '无条件';
    const outputs = Object.values(models[n.model_id].outputs).filter((v, i, all) => all.indexOf(v) === i).join(' / ');
    return `<button class="demo-node role-${ROLES[n.model_id]} ${selected === n.id ? 'selected' : ''}" data-node-id="${esc(n.id)}" aria-pressed="${selected === n.id}">
      ${Object.keys(models[n.model_id].inputs).length ? '<span class="node-port in"></span>' : ''}
      <span class="step-index"><span class="role-marker"></span>${String(index + 1).padStart(2, '0')} / ${esc(models[n.model_id].role)}</span>
      <span class="model-name">${esc(models[n.model_id].name)}</span><span class="node-label">${esc(n.label)}</span>
      <span class="node-summary">${esc(summary(n))}</span>
      <span class="pill ${status === '已登记' ? 'good' : status === '待补充' ? 'warn' : 'purple'}">${status} · 未提交</span>
      <span class="node-formats"><span>${esc(inputs)}</span><span aria-hidden="true">→</span><span>${esc(outputs)}</span></span>
      <span class="node-port out"></span></button>`;
  }).join('') : '<div class="empty-graph">还没有科学步骤。点击「＋ 步骤」添加第一个模型。</div>';
  pipeline.querySelectorAll('[data-node-id]').forEach(button => button.addEventListener('click', () => select(button.dataset.nodeId)));
  previousWorkflow = state.draft.id; previousRevision = state.draft.revision;
  previousNodes = new Map(state.draft.nodes.map(n => [n.id, JSON.stringify(n)]));
  // One brief outline response to an actual saved revision; no fake worker
  // states, timers, calls, packet counts or scientific execution animation.
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
    pipeline.querySelectorAll('[data-node-id]').forEach(button => {
      if (changed.has(button.dataset.nodeId)) button.animate([
        {boxShadow:'0 0 0 0px #8173c64d'}, {boxShadow:'0 0 0 7px #8173c61a'}, {boxShadow:'0 0 0 0px #8173c600'},
      ], {duration:650, iterations:1});
    });
  }
  requestAnimationFrame(() => drawWires(state, selected));
}

export function drawWires(state, selected = document.querySelector('.demo-node.selected')?.dataset.nodeId) {
  const graph = document.getElementById('graph'), svg = document.getElementById('wires');
  const base = graph.getBoundingClientRect();
  svg.setAttribute('width', graph.scrollWidth);
  svg.setAttribute('height', graph.scrollHeight);
  const rect = id => Array.from(document.querySelectorAll('[data-node-id]')).find(e => e.dataset.nodeId === id)?.getBoundingClientRect();
  svg.innerHTML = '<defs><marker id="arrowhead" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#aaa2cf"/></marker><marker id="selected-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#7967b1"/></marker></defs>' + state.draft.edges.map((edge, i) => {
    const a = rect(edge.source), b = rect(edge.target);
    if (!a || !b) return '';
    const x1 = a.right - base.left + graph.scrollLeft, y1 = a.top + a.height/2 - base.top + graph.scrollTop;
    const x2 = b.left - base.left + graph.scrollLeft, y2 = b.top + b.height/2 - base.top + graph.scrollTop;
    const lower = Math.max(a.bottom, b.bottom) - base.top + graph.scrollTop + 16 + i * 9;
    const mid = (x1 + x2) / 2;
    const path = x2 >= x1 ? `M${x1},${y1} H${mid} V${y2} H${x2}` : `M${x1},${y1} H${x1+16} V${lower} H${x2-16} V${y2} H${x2}`;
    const active = edge.source === selected || edge.target === selected;
    const label = edge.transform ? '需转换' : 'PDB';
    const title = `${edge.source}.${edge.source_port} → ${edge.target}.${edge.target_port}${edge.transform ? '；FASTA→Boltz YAML 转换尚未接入' : ''}；仅表示配置依赖，未执行计算`;
    return `<g><title>${esc(title)}</title><path d="${path}" fill="none" stroke="${active ? '#7967b1' : '#b7b2cb'}" stroke-width="${active ? 2 : 1.5}" stroke-linejoin="round" marker-end="url(#${active ? 'selected-arrow' : 'arrowhead'})" ${edge.transform ? 'stroke-dasharray="4 3"' : ''}/>${x2 >= x1 ? `<text class="wire-label" x="${mid}" y="${Math.min(y1,y2)-12}" text-anchor="middle">${label}</text>` : ''}</g>`;
  }).join('');
}
