import {escapeHTML as esc} from './api.js';
import {CARD_WIDTH, PORT_TOP, PORT_GAP, cardHeight, layoutNodes, graphDocument, graphBounds} from './graph-model.js';

// DOM/SVG canvas; all semantic writes go through the existing versioned changes API.
export function createGraph(root, {onMove, onError}) {
  const $ = id => root.getElementById(id);
  const viewport = $('graph'), world = $('graph-world'), pipeline = $('pipeline'), wires = $('wires');
  const lifecycle = new AbortController();
  const listen = (element, type, action, options = {}) => element.addEventListener(type, action, {...options, signal:lifecycle.signal});
  let state, models, selected, selectNode, positions = {}, camera = {x:35,y:50,zoom:1}, workflowId, drag = null, suppressClick = false;
  const NS = 'http://www.w3.org/2000/svg';
  const svg = (tag, attrs, text) => {
    const el = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([key,value]) => el.setAttribute(key, value));
    if (text) el.textContent = text;
    return el;
  };
  const summary = n => n.model_id === 'rfdiffusion' ? `${n.params.length} aa · ${n.params.num_designs} 个骨架`
    : n.model_id === 'proteinmpnn' ? `${n.params.num_seq_per_target} 条序列 · T ${n.params.sampling_temp}`
      : `${n.params.diffusion_samples} 个样本 · ${n.params.msa_mode === 'empty' ? '空 MSA' : '已有 A3M'}`;
  const bound = value => Math.max(.08, Math.min(1.8, value));

  function applyCamera() {
    world.style.transform = `translate(${camera.x}px, ${camera.y}px) scale(${camera.zoom})`;
    $('zoom-value').textContent = `${Math.round(camera.zoom * 100)}%`;
    viewport.style.backgroundPosition = `${camera.x}px ${camera.y}px`;
    viewport.style.backgroundSize = `${24 * camera.zoom}px ${24 * camera.zoom}px`;
    if (workflowId) {
      try { localStorage.setItem('ai4s-camera-' + workflowId, JSON.stringify(camera)); } catch { /* Camera is optional personal preference. */ }
    }
  }
  function fit() {
    if (!state || !viewport.clientWidth) return;
    const edges = [...state.draft.edges, ...(state.draft.visual?.relations || [])];
    const hasReturn = edges.some(e => positions[e.target]?.x <= positions[e.source]?.x + CARD_WIDTH + 30);
    const b = graphBounds(state.draft.nodes, positions, models, hasReturn ? 60+edges.length*18 : 0);
    camera.zoom = bound(Math.min((viewport.clientWidth - 24) / b.width, (viewport.clientHeight - 24) / b.height, 1));
    camera.x = (viewport.clientWidth - b.width * camera.zoom) / 2 - b.x * camera.zoom;
    camera.y = (viewport.clientHeight - b.height * camera.zoom) / 2 - b.y * camera.zoom;
    applyCamera();
  }
  function zoom(factor, x = viewport.clientWidth / 2, y = viewport.clientHeight / 2) {
    const next = bound(camera.zoom * factor), ratio = next / camera.zoom;
    camera.x = x - (x-camera.x)*ratio; camera.y = y - (y-camera.y)*ratio; camera.zoom = next;
    applyCamera();
  }
  function focus() {
    const n = state?.draft.nodes.find(n => n.id === selected);
    if (!n) return;
    camera.zoom = 1;
    camera.x = viewport.clientWidth / 2 - positions[n.id].x - CARD_WIDTH / 2;
    camera.y = viewport.clientHeight / 2 - positions[n.id].y - cardHeight(models[n.model_id]) / 2;
    applyCamera();
  }
  function inputDescription(input) {
    if (!input.reference) return input.required ? '待提供' : '可选 · 当前不用';
    const ref = input.reference;
    if (ref.kind === 'node_output') return `${ref.node_id}.${ref.port}`;
    if (ref.kind === 'sequence') return '直接序列';
    return `文件 ${ref.file_id}`;
  }
  function drawNodes(value, definitions, active, select) {
    state = value; models = definitions; selected = active; selectNode = select;
    const switched = workflowId !== state.draft.id;
    workflowId = state.draft.id;
    positions = layoutNodes(state.draft, models);
    const doc = graphDocument(state.draft, models);
    pipeline.innerHTML = state.draft.nodes.map((n,index) => {
      const model = models[n.model_id], info = doc.nodes[index], status = state.checks[n.id].status;
      const role = {rfdiffusion:'backbone',proteinmpnn:'sequence',boltz:'prediction'}[n.model_id];
      const ports = (list, direction) => list.map((p,i) => {
        const output = direction === 'output';
        const usage = output ? p.consumers.length ? `→ ${p.consumers.length} 处输入` : p.relations.length ? '→ 设计关系' : '未连接 · 待生成' : inputDescription(p);
        return `<div class="graph-port ${direction}${p.role === 'auxiliary' ? ' auxiliary' : ''}" style="top:${PORT_TOP + i*PORT_GAP-18}px" title="${esc(p.port + ' · ' + usage)}"><i></i><strong>${esc(p.format)} <small>${esc(p.port)}</small></strong><span>${output && p.role === 'auxiliary' ? '辅助产物 · ' : ''}${esc(usage)}</span></div>`;
      }).join('');
      return `<article class="graph-card role-${role}${n.id === selected ? ' selected' : ''}" data-card-id="${esc(n.id)}" style="left:${positions[n.id].x}px;top:${positions[n.id].y}px;height:${cardHeight(model)}px">
        <div class="graph-drag-handle" data-drag-id="${esc(n.id)}" title="拖动节点；选中后用方向键移动" aria-hidden="true">${String(index+1).padStart(2,'0')} · ${esc(model.role)} <span>⠿</span></div>
        <button class="graph-select" data-node-id="${esc(n.id)}" aria-pressed="${n.id === selected}"><strong>${esc(model.name)}</strong><span>${esc(n.label)}</span></button>
        <div class="graph-summary">${esc(summary(n))}<span>${esc(status)}</span></div>
        <div class="graph-port-head"><span>所需输入</span><span>输出／辅助产物</span></div>
        ${info.inputs.length ? ports(info.inputs,'input') : '<span class="graph-unconditional">无条件生成</span>'}${ports(info.outputs,'output')}
      </article>`;
    }).join('') || '<p class="empty-graph">添加科学步骤，开始构建工作流。</p>';
    drawWires();
    if (switched) {
      let stored;
      try { stored = JSON.parse(localStorage.getItem('ai4s-camera-' + workflowId)); } catch { /* Ignore invalid personal camera state. */ }
      if (stored && ['x','y','zoom'].every(key => Number.isFinite(stored[key]))) { camera = {...stored,zoom:bound(stored.zoom)}; applyCamera(); }
      else requestAnimationFrame(fit);
    } else applyCamera();
  }
  function drawWires() {
    if (!state) return;
    wires.replaceChildren();
    const defs = svg('defs', {});
    for (const [id,color] of [['data','#7770af'],['feedback','#b77925'],['reference','#60768b']]) {
      const marker = svg('marker', {id:'arrow-'+id,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto-start-reverse'});
      marker.append(svg('path',{d:'M0,0 L10,5 L0,10 z',fill:color})); defs.append(marker);
    }
    wires.append(defs);
    const byId = new Map(state.draft.nodes.map(n => [n.id,n]));
    const edges = [...state.draft.edges, ...(state.draft.visual?.relations || [])];
    const graphBottom = Math.max(0,...state.draft.nodes.map(n=>positions[n.id].y+cardHeight(models[n.model_id])));
    edges.forEach((edge,index) => {
      const source = byId.get(edge.source), target = byId.get(edge.target);
      if (!source || !target) return;
      const a = positions[source.id], b = positions[target.id], outputPorts = Object.keys(models[source.model_id].outputs);
      const x1 = a.x+CARD_WIDTH, y1 = a.y+PORT_TOP+Math.max(0,outputPorts.indexOf(edge.source_port))*PORT_GAP;
      const x2 = b.x, y2 = edge.kind ? b.y+38 : b.y+PORT_TOP+Math.max(0,Object.keys(models[target.model_id].inputs).indexOf(edge.target_port))*PORT_GAP;
      const backwards = x2 <= x1 + 30;
      let d, lx, ly;
      if (backwards) {
        const bottom = graphBottom+35+index*18;
        d = `M${x1} ${y1} C${x1+65} ${y1} ${x1+65} ${bottom} ${x1+30} ${bottom} L${x2-35} ${bottom} C${x2-75} ${bottom} ${x2-75} ${y2} ${x2} ${y2}`;
        lx = (x1+x2)/2; ly = bottom-8;
      } else {
        const bend = Math.max(60,(x2-x1)/2);
        d = `M${x1} ${y1} C${x1+bend} ${y1} ${x2-bend} ${y2} ${x2} ${y2}`;
        lx = (x1+x2)/2; ly = (y1+y2)/2-12;
      }
      const kind = edge.kind || 'data', color = kind === 'feedback' ? '#b77925' : kind === 'reference' ? '#60768b' : '#7770af';
      const group = svg('g',{}), path = svg('path',{d,fill:'none',stroke:color,'stroke-width':2,'marker-end':`url(#arrow-${kind})`});
      if (edge.kind || edge.transform) path.setAttribute('stroke-dasharray', edge.kind ? '3 6' : '8 5');
      if (edge.source !== selected && edge.target !== selected) path.setAttribute('opacity',.65);
      const format = models[source.model_id].outputs[edge.source_port];
      const label = edge.kind ? `${edge.kind === 'feedback' ? '反馈' : '参考'} · ${edge.label}` : `${format}${edge.transform ? ' · 需转换' : ''}${edge.record_id ? ' · '+edge.record_id : ''}`;
      group.append(svg('title',{},`${source.label}.${edge.source_port} → ${target.label}${edge.kind ? '（设计关系，不绑定输入）' : '.'+edge.target_port}；未执行`),path,svg('text',{x:lx,y:ly,'text-anchor':'middle',class:'wire-label'},label));
      wires.append(group);
    });
  }
  listen(pipeline,'click',event => {
    if (suppressClick) { suppressClick = false; return; }
    const button = event.target.closest('[data-node-id]');
    if (button) selectNode(button.dataset.nodeId);
  });
  listen(viewport,'pointerdown',event => {
    if (event.button !== 0 && event.button !== 1) return;
    const handle = event.target.closest('[data-drag-id]');
    if (!handle && event.target.closest('button, .graph-card')) return;
    if (handle && root.host.getAttribute('aria-busy') === 'true') return;
    const id = handle?.dataset.dragId;
    drag = {id, pointer:event.pointerId, startX:event.clientX, startY:event.clientY, original:id ? {...positions[id]} : {...camera}, moved:false};
    viewport.setPointerCapture(event.pointerId); viewport.classList.add('dragging'); event.preventDefault();
  });
  listen(viewport,'pointermove',event => {
    if (!drag) return;
    const dx = event.clientX-drag.startX, dy = event.clientY-drag.startY;
    if (Math.hypot(dx,dy) < 4 && !drag.moved) return;
    drag.moved = true;
    if (drag.id) {
      const x = Math.max(-100000,Math.min(100000,Math.round(drag.original.x+dx/camera.zoom)));
      const y = Math.max(-100000,Math.min(100000,Math.round(drag.original.y+dy/camera.zoom)));
      positions[drag.id] = {x,y};
      const card = [...pipeline.children].find(el => el.dataset.cardId === drag.id);
      card.style.left = x+'px'; card.style.top = y+'px'; drawWires();
    } else { camera.x = drag.original.x+dx; camera.y = drag.original.y+dy; applyCamera(); }
  });
  async function finishDrag(event) {
    if (!drag || drag.pointer !== event.pointerId) return;
    const current = drag; drag = null; viewport.classList.remove('dragging');
    if (viewport.hasPointerCapture(event.pointerId)) viewport.releasePointerCapture(event.pointerId);
    if (current.id && current.moved) {
      suppressClick = true;
      setTimeout(() => { suppressClick = false; }, 100);
      if (event.type === 'pointercancel') { drawNodes(state,models,selected,selectNode); return; }
      try { await onMove(current.id,positions[current.id]); }
      catch(error) { onError(error); drawNodes(state,models,selected,selectNode); }
    }
  }
  listen(viewport,'pointerup',finishDrag); listen(viewport,'pointercancel',finishDrag);
  listen(viewport,'wheel',event => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault(); const r = viewport.getBoundingClientRect();
    zoom(Math.exp(-event.deltaY*.003),event.clientX-r.left,event.clientY-r.top);
  },{passive:false});
  listen(viewport,'keydown',event => {
    if (event.target.closest('[data-node-id]') && event.key.startsWith('Arrow')) {
      event.preventDefault();
      if (root.host.getAttribute('aria-busy') === 'true') return;
      const id = event.target.dataset.nodeId, p = {...positions[id]}, delta = event.shiftKey ? 50 : 15;
      p.x += event.key === 'ArrowRight' ? delta : event.key === 'ArrowLeft' ? -delta : 0;
      p.y += event.key === 'ArrowDown' ? delta : event.key === 'ArrowUp' ? -delta : 0;
      onMove(id,p).then(() => [...pipeline.querySelectorAll('[data-node-id]')].find(el=>el.dataset.nodeId===id)?.focus()).catch(onError);
      return;
    }
    if (event.target !== viewport) return;
    if (event.key === '+' || event.key === '=') { event.preventDefault(); zoom(1.2); }
    if (event.key === '-') { event.preventDefault(); zoom(1/1.2); }
    if (event.key === '0') { event.preventDefault(); fit(); }
    if (event.key.startsWith('Arrow')) { event.preventDefault(); camera.x += event.key === 'ArrowLeft' ? 50 : event.key === 'ArrowRight' ? -50 : 0; camera.y += event.key === 'ArrowUp' ? 50 : event.key === 'ArrowDown' ? -50 : 0; applyCamera(); }
  });
  listen($('zoom-in'),'click',()=>zoom(1.2)); listen($('zoom-out'),'click',()=>zoom(1/1.2));
  listen($('fit-graph'),'click',fit); listen($('focus-node'),'click',focus);
  listen($('expand-graph'),'click',()=> {
    const expanded = $('flow-panel').classList.toggle('canvas-expanded');
    $('expand-graph').textContent = expanded ? '收起画布' : '展开画布';
    $('expand-graph').setAttribute('aria-pressed',String(expanded)); requestAnimationFrame(fit);
  });
  listen(root,'keydown',e=> { if (e.key === 'Escape' && $('flow-panel').classList.contains('canvas-expanded')) $('expand-graph').click(); });
  const observer = new ResizeObserver(()=>applyCamera()); observer.observe(viewport);
  return {drawNodes,drawWires,fit,document:()=>graphDocument(state.draft,models),
    pause() { $('flow-panel').classList.remove('canvas-expanded'); $('expand-graph').textContent='展开画布'; $('expand-graph').setAttribute('aria-pressed','false'); },
    destroy() { lifecycle.abort(); observer.disconnect(); }};
}
