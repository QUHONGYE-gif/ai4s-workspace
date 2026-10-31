// Convert configuration into a handoff draft, never into executable commands.
export function registrationFromAgent(draft, models, current) {
    const nodes = draft.nodes;
    if (draft.visual?.relations?.length) {
        throw new Error('草稿含反馈或参考设计关系；当前接入表单不能保留这些关系，请保留 AI 草稿，不能直接展平。');
    }
    if (!nodes.length || nodes.length > 12) {
        throw new Error('接入草稿需要 1–12 个步骤。');
    }
    const byId = new Map(nodes.map(node => [node.id, node]));
    const next = new Map(), incoming = new Set();
    for (const edge of draft.edges) {
        if (!byId.has(edge.source) || !byId.has(edge.target) || next.has(edge.source) || incoming.has(edge.target)) {
            throw new Error('接入表单目前支持一条串行链；分支或多输入连接请保留在 AI 草稿中，不能直接展平。');
        }
        next.set(edge.source, edge.target);
        incoming.add(edge.target);
    }
    const starts = nodes.filter(node => !incoming.has(node.id));
    if (starts.length !== 1 || draft.edges.length !== nodes.length - 1) {
        throw new Error('请先将步骤连接为一条串行链，再应用到接入草稿。');
    }
    const ordered = [], seen = new Set();
    for (let node = starts[0]; node && !seen.has(node.id); node = byId.get(next.get(node.id))) {
        ordered.push(node);
        seen.add(node.id);
    }
    if (ordered.length !== nodes.length) {
        throw new Error('连接存在循环或未连接步骤，请先检查 AI 草稿。');
    }
    const registrations = ordered.map((node, index) => {
        const model = models[node.model_id];
        if (!model) {
            throw new Error('存在尚未支持的模型，请先检查 AI 草稿。');
        }
        const previous = current.agentSource?.workflowId === draft.id
            ? current.registrations.find(step => step.agentConfig?.nodeId === node.id)
            : null;
        const config = {
            nodeId: node.id, modelId: node.model_id, modelName: model.name,
            definitionVersion: model.definition_version, referenceVersion: model.code_identity,
            documentation: model.source_url, parameters: structuredClone(node.params),
            inputs: structuredClone(node.inputs), outputs: structuredClone(model.outputs),
            designChainPolicy: structuredClone(node.design_chain_policy || null),
            provenance: structuredClone(node.provenance || {}),
        };
        const unchanged = previous && JSON.stringify(previous.agentConfig) === JSON.stringify(config);
        return {
            id: 'step-' + (index + 1), name: node.label,
            modelPath: previous?.modelPath || '', docPath: previous?.docPath || '',
            version: previous?.version || '', command: unchanged ? previous.command : '',
            input: previous?.input || '', output: previous?.output || '', agentConfig: config,
        };
    });
    return {
        ...structuredClone(current), name: current.name.trim() ? current.name : draft.name,
        template: 'custom', registrations,
        agentSource: { workflowId: draft.id, revision: draft.revision, edges: structuredClone(draft.edges) },
    };
}
