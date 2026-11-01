const assert = require('node:assert/strict');
(async () => {
    const { registrationFromAgent } = await import('../web/demo/assets/agent-registration.js');
    const models = {
        rfdiffusion: { name: 'RFdiffusion', definition_version: 'demo-1', code_identity: 'reference-rfd', source_url: 'https://example.test/rfd', outputs: { backbone: 'PDB' } },
        proteinmpnn: { name: 'ProteinMPNN', definition_version: 'demo-1', code_identity: 'reference-mpnn', source_url: 'https://example.test/mpnn', outputs: { sequences: 'FASTA' } },
    };
    const draft = { id: 'ai-test', revision: 2, name: 'AI 草稿', nodes: [
            { id: 'mpnn', model_id: 'proteinmpnn', label: '序列设计', params: { sampling_temp: 0.2 }, inputs: { backbone: { kind: 'node_output', node_id: 'rfd', port: 'backbone' } } },
            { id: 'rfd', model_id: 'rfdiffusion', label: '骨架生成', params: { length: 80 }, inputs: {} },
        ], edges: [{ source: 'rfd', target: 'mpnn', source_port: 'backbone', target_port: 'backbone' }] };
    const current = { name: '已填流程名', projectPath: '/project', environment: 'conda:demo', registrations: [] };
    const before = structuredClone(current);
    const result = registrationFromAgent(draft, models, current);
    assert.equal(result.name, '已填流程名');
    assert.equal(result.projectPath, '/project');
    assert.deepEqual(result.registrations.map(step => step.name), ['骨架生成', '序列设计']);
    assert.equal(result.registrations[1].agentConfig.parameters.sampling_temp, 0.2);
    assert.equal(result.registrations[1].command, '');
    assert.equal(result.registrations[1].output, '');
    assert.deepEqual(result.agentSource.edges, draft.edges);
    assert.deepEqual(current, before);
    assert.throws(() => registrationFromAgent({ ...draft, edges: [] }, models, current), /串行链/);
    const branch = structuredClone(draft);
    branch.nodes.push({ ...structuredClone(draft.nodes[0]), id: 'mpnn-2' });
    branch.edges.push({ source: 'rfd', target: 'mpnn-2' });
    assert.throws(() => registrationFromAgent(branch, models, current), /分支/);
    assert.throws(() => registrationFromAgent({ ...draft, visual: { relations: [{ id: 'feedback' }] } }, models, current), /设计关系/);
    result.registrations[1].command = 'reviewed command';
    assert.equal(registrationFromAgent(draft, models, result).registrations[1].command, 'reviewed command');
    const changed = structuredClone(draft);
    changed.nodes[0].params.sampling_temp = 0.3;
    assert.equal(registrationFromAgent(changed, models, result).registrations[1].command, '');
    console.log('PASS AI handoff order, parameter identity, project preservation, graph constraints, and stale-command invalidation');
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
