const assert = require('node:assert/strict');
(async()=> {
  const {layoutNodes,graphDocument,graphBounds,CARD_WIDTH} = await import('../src/ai4s_demo/web/graph-model.js');
  const models = {
    rfdiffusion:{inputs:{},outputs:{backbone:'PDB',metadata:'TRB'},output_roles:{metadata:'auxiliary'}},
    proteinmpnn:{inputs:{backbone:'PDB'},outputs:{sequences:'FASTA',scores:'NPZ'},output_roles:{scores:'auxiliary'}},
    boltz:{inputs:{sequence:'FASTA',msa:'A3M'},outputs:{structure:'CIF',confidence:'JSON'}},
  };
  const draft = {id:'wf-test',revision:3,nodes:[
    {id:'rfd',model_id:'rfdiffusion',label:'骨架',inputs:{},params:{}},
    {id:'a',model_id:'proteinmpnn',label:'A',inputs:{backbone:{kind:'node_output',node_id:'rfd',port:'backbone'}},params:{}},
    {id:'b',model_id:'proteinmpnn',label:'B',inputs:{},params:{}},
    {id:'prediction',model_id:'boltz',label:'预测',inputs:{},params:{msa_mode:'empty'}},
  ],edges:[{source:'rfd',source_port:'backbone',target:'a',target_port:'backbone'},
           {source:'rfd',source_port:'backbone',target:'b',target_port:'backbone'},
           {source:'a',source_port:'sequences',target:'prediction',target_port:'sequence'}],
    visual:{relations:[{id:'feedback',source:'prediction',source_port:'confidence',target:'rfd',kind:'feedback',label:'检查后重新设计'}]}};
  const before = structuredClone(draft), positions = layoutNodes(draft,models);
  assert.ok(positions.a.x > positions.rfd.x + CARD_WIDTH);
  assert.equal(positions.a.x,positions.b.x);
  assert.ok(Math.abs(positions.b.y - positions.a.y) > 240);
  const doc = graphDocument(draft,models);
  assert.equal(doc.nodes[0].outputs[0].consumers.length,2);
  assert.equal(doc.nodes[0].outputs[1].role,'auxiliary');
  assert.equal(doc.nodes[0].outputs[1].consumers.length,0);
  assert.equal(doc.nodes[3].inputs.find(i=>i.port==='msa').required,false);
  assert.equal(doc.relations[0].target,'rfd');
  assert.deepEqual(draft,before);
  draft.visual.layout='circle'; draft.visual.positions={rfd:{x:-400,y:800}};
  assert.deepEqual(layoutNodes(draft,models).rfd,{x:-400,y:800});
  const bounds = graphBounds(draft.nodes,layoutNodes(draft,models),models);
  assert.ok(bounds.x < -400 && bounds.width > 292);
  console.log('PASS branch layout, auxiliary output lineage, optional MSA, feedback graph, manual positions and bounds');
})().catch(error=>{console.error(error);process.exitCode=1;});
