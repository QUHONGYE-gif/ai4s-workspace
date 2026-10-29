// Renderer-independent graph projection. No scientific state is inferred from geometry.
export const CARD_WIDTH = 292;
export const PORT_TOP = 142;
export const PORT_GAP = 52;
export const cardHeight = model => PORT_TOP + Math.max(1, Object.keys(model.inputs).length, Object.keys(model.outputs).length) * PORT_GAP + 16;

export function layoutNodes(draft, models) {
  const positions = {}, nodes = draft.nodes;
  if (draft.visual?.layout === 'circle' && nodes.length > 1) {
    const radius = Math.max(250, nodes.length * 65);
    nodes.forEach((n, index) => {
      const angle = index / nodes.length * Math.PI * 2 - Math.PI / 2;
      positions[n.id] = {x: Math.round(radius + Math.cos(angle) * radius), y: Math.round(radius + Math.sin(angle) * radius)};
    });
  } else {
    const indegree = new Map(nodes.map(n => [n.id, 0]));
    const level = new Map(nodes.map(n => [n.id, 0]));
    const edges = draft.edges.filter(e => indegree.has(e.source) && indegree.has(e.target));
    edges.forEach(e => indegree.set(e.target, indegree.get(e.target) + 1));
    const queue = nodes.filter(n => !indegree.get(n.id)).map(n => n.id);
    for (let index = 0; index < queue.length; index++) {
      const id = queue[index];
      edges.filter(e => e.source === id).forEach(e => {
        level.set(e.target, Math.max(level.get(e.target), level.get(id) + 1));
        indegree.set(e.target, indegree.get(e.target) - 1);
        if (!indegree.get(e.target)) queue.push(e.target);
      });
    }
    // Fallback remains finite for imported visual graphs with cyclic dependencies.
    const columns = new Map();
    nodes.forEach(n => { const depth = level.get(n.id); if (!columns.has(depth)) columns.set(depth, []); columns.get(depth).push(n); });
    const rowHeight = Math.max(240, ...nodes.map(n => cardHeight(models[n.model_id]))) + 100;
    columns.forEach((items, depth) => items.forEach((n, row) => {
      positions[n.id] = {x: depth * (CARD_WIDTH + 180), y: row * rowHeight};
    }));
  }
  Object.entries(draft.visual?.positions || {}).forEach(([id, position]) => {
    if (Object.hasOwn(positions, id)) positions[id] = {...position};
  });
  return positions;
}

export function graphDocument(draft, models) {
  const positions = layoutNodes(draft, models);
  const relations = draft.visual?.relations || [];
  return {
    schema_version: 'ai4s-graph-1', workflow_id: draft.id, revision: draft.revision,
    execution_status: 'not_submitted', layout: draft.visual?.layout || 'layered',
    nodes: draft.nodes.map(n => ({
      id: n.id, label: n.label, model_id: n.model_id, position: positions[n.id],
      inputs: Object.entries(models[n.model_id].inputs).map(([port, format]) => ({
        port, format, required: !(n.model_id === 'boltz' && port === 'msa' && n.params.msa_mode === 'empty'),
        reference: n.inputs[port] || null,
      })),
      outputs: Object.entries(models[n.model_id].outputs).map(([port, format]) => ({
        port, format, role: models[n.model_id].output_roles?.[port] || 'primary',
        consumers: draft.edges.filter(e => e.source === n.id && e.source_port === port).map(e => ({node_id:e.target, port:e.target_port})),
        relations: relations.filter(r => r.source === n.id && r.source_port === port).map(r => r.id),
      })),
    })),
    bindings: structuredClone(draft.edges), relations: structuredClone(relations),
  };
}

export function graphBounds(nodes, positions, models, extraBottom = 0) {
  if (!nodes.length) return {x:0, y:0, width:500, height:300};
  const left = Math.min(...nodes.map(n => positions[n.id].x));
  const top = Math.min(...nodes.map(n => positions[n.id].y));
  const right = Math.max(...nodes.map(n => positions[n.id].x + CARD_WIDTH));
  const bottom = Math.max(...nodes.map(n => positions[n.id].y + cardHeight(models[n.model_id])));
  return {x:left - 90, y:top - 60, width:right-left+180, height:bottom-top+120+extraBottom};
}
