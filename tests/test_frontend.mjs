import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {CONTRACT,DEFAULT_STATE,SCHEMA} from '../web/catalog.js';
import {parseState,serializeState,validatePartPrompt} from '../web/controller.js';
import {migrateAnimaWorkflow} from '../web/workflow_migration.js';
import {TEXT} from '../web/tagger_i18n.js';
import {createExtension} from '../web/integration.js';
const read=p=>JSON.parse(fs.readFileSync(new URL(p,import.meta.url),'utf8'));
test('Python and frontend share identical contracts',()=>{
  assert.deepEqual(CONTRACT,read('../contracts/view_contract.v1.json'));
  assert.deepEqual(DEFAULT_STATE,read('../contracts/default_state.json'));
  assert.deepEqual(SCHEMA,read('../schemas/state.v1.schema.json'));
});
test('State survives roundtrip with Japanese and supplementary Unicode',()=>{
  const s=structuredClone(DEFAULT_STATE);s.part_prompts.face='表情😀'.repeat(100);
  assert.equal(serializeState(parseState(serializeState(s))),JSON.stringify(s));
  assert.doesNotThrow(()=>validatePartPrompt('😀'.repeat(1000)));
  assert.throws(()=>validatePartPrompt('😀'.repeat(1001)));
});
test('Invalid JSON is rejected rather than repaired',()=>{
  const s=serializeState(DEFAULT_STATE);
  for(const raw of [s.replace('1120','1120.0'),s.replace('1120','1.12e3'),s.replace('"views":','"views":[],"views":')]) assert.throws(()=>parseState(raw));
});
test('Workflow has one lazy input switch and no adapter; titles unchanged',()=>{
  const wf=read('../examples/Anima-Character-Sheet-Designer-Text-or-Image.json');
  const groups=[wf,...wf.definitions.subgraphs];
  const nodes=groups.flatMap(g=>g.nodes);
  assert.ok(nodes.every(n=>!Object.hasOwn(n,'title')));
  const inputGroup=wf.definitions.subgraphs.find(g=>g.nodes.some(n=>n.type==='AnimaImageTagger'));
  const targetNames=inputGroup.links.filter(l=>l.origin_id===1).map(l=>{
    const n=inputGroup.nodes.find(n=>n.id===l.target_id);return [n.type,n.inputs[l.target_slot].name];
  });
  assert.deepEqual(targetNames,[['AnimaImageTagger','use_image']]);
  assert.ok(!nodes.some(n=>['AnimaRefAdapter','ComfySwitchNode'].includes(n.type)));
  for(const g of groups)for(const raw of g.links){
    const {id,origin_id:from,origin_slot:slot,target_id:to,target_slot:input,type}=Array.isArray(raw)?Object.fromEntries(['id','origin_id','origin_slot','target_id','target_slot','type'].map((k,i)=>[k,raw[i]])):raw;
    const origin=g.nodes.find(n=>n.id===from), target=g.nodes.find(n=>n.id===to);
    const out=origin?.outputs[slot]??g.inputs?.[slot], inp=target?.inputs[input]??g.outputs?.[input];
    assert.ok((out.links??out.linkIds).includes(id));assert.ok((inp.linkIds??[inp.link]).includes(id));
    assert.equal(out.type,type);assert.ok(inp.type===type||inp.type==='*');
  }
  assert.equal(inputGroup.nodes.find(n=>n.type==='AnimaImageTagger').widgets_values[1],'pixai_v1_fp16');
  assert.deepEqual(wf.nodes.find(n=>n.properties?.anima_sheet_locale==='AnimaSheetInputs').widgets_values.slice(-3),[true,true,false]);
});

test('Positive settings save, migrate and keep blank overrides',()=>{
  const old=structuredClone(DEFAULT_STATE);old.positive_common='discarded';delete old.view_prompts;old.negative_extra='old';
  assert.equal(serializeState(parseState(JSON.stringify(old))),JSON.stringify(DEFAULT_STATE));
  const s=structuredClone(DEFAULT_STATE);s.view_prompts.face_front='';
  assert.equal(serializeState(parseState(serializeState(s))),JSON.stringify(s));
  s.view_prompts.face_front='😀'.repeat(2001);assert.throws(()=>serializeState(s));
});
test('Provisional template preserves user settings and negative is directly editable',()=>{
 const wf=read('../examples/Anima-Character-Sheet-Designer-Text-or-Image.json');
 const designer=wf.nodes.find(n=>n.type==='AnimaCharacterSheetDesigner');
 assert.ok(designer.outputs.every(o=>o.name!=='negative'));
 const group=wf.definitions.subgraphs.find(g=>g.nodes.some(n=>n.type==='KSampler'));
 const sampler=group.nodes.find(n=>n.type==='KSampler');
 const link=group.links.find(l=>l.id===sampler.inputs.find(i=>i.name==='negative').link);
 const encode=group.nodes.find(n=>n.id===link.origin_id);
 assert.equal(encode.type,'CLIPTextEncode');assert.ok(!encode.inputs.some(i=>i.name==='text'));
 assert.equal(typeof encode.widgets_values[0],'string');
 assert.ok(encode.widgets_values[0].includes('worst quality'));
 assert.ok(wf.definitions.subgraphs.flatMap(g=>g.nodes).some(n=>n.type==='LoraLoaderModelOnly'));
});

test('Old saved sockets migrate once without changing settings or titles',()=>{
 const original=read('./tagger-ui-fix-original.json'), migrated=migrateAnimaWorkflow(structuredClone(original));
 const d=migrated.nodes.find(n=>n.type==='AnimaCharacterSheetDesigner');
 assert.deepEqual(d.outputs.map(o=>o.name),['positive','width','height','seed','sheet_plan','view_records']);
 for(const id of [1,2,5,6,7,11,13,18,19])assert.deepEqual(migrated.nodes.find(n=>n.id===id),original.nodes.find(n=>n.id===id));
 assert.deepEqual(migrateAnimaWorkflow(structuredClone(migrated)),migrated);
 for(const link of migrated.links){const origin=migrated.nodes.find(n=>n.id===link[1]);assert.equal(origin.outputs[link[2]].type,link[5]);}
 const tag=migrated.nodes.find(n=>n.type==='AnimaImageTagger');assert.equal(tag.widgets_values.length,5);assert.match(tag.widgets_values[3],/anima_tagger_config/);
});
test('Both locales provide labels and hover help for every Tagger control and port',()=>{
 for(const row of Object.values(TEXT))for(const key of ['en','ja','helpEn','helpJa'])assert.ok(row[key]?.length>0);
 for(const lang of ['en','ja']){const d=read('../locales/'+lang+'/nodeDefs.json');for(const node of Object.values(d))for(const ports of [node.inputs,node.outputs])for(const port of Object.values(ports)){assert.ok(port.name);assert.ok(port.tooltip);}}
});

test('Resaved Designer sockets retain the plan/records connections after import and roundtrip',()=>{
 const original=read('./wiring-fix-original.json');
 for(const objectLinks of [false,true]){
  const wf=structuredClone(original);
  if(objectLinks)wf.links=wf.links.map(([id,origin_id,origin_slot,target_id,target_slot,type])=>({id,origin_id,origin_slot,target_id,target_slot,type}));
  migrateAnimaWorkflow(wf);
  const designer=wf.nodes.find(n=>n.type==='AnimaCharacterSheetDesigner'),assemble=wf.nodes.find(n=>n.type==='AnimaCharacterSheetAssemble');
  assert.deepEqual(designer.outputs.map(o=>o.name),['positive','width','height','seed','sheet_plan','view_records']);
  for(const name of ['sheet_plan','view_records']){
   const input=assemble.inputs.find(i=>i.name===name),link=wf.links.find(l=>(objectLinks?l.id:l[0])===input.link);
   const slot=objectLinks?link.origin_slot:link[2];
   assert.equal(designer.outputs[slot].name,name);assert.ok(designer.outputs[slot].links.includes(input.link));
  }
  for(const node of wf.nodes)if(node.id!==designer.id)assert.deepEqual(node,original.nodes.find(n=>n.id===node.id));
  assert.deepEqual(designer.widgets_values,original.nodes.find(n=>n.id===designer.id).widgets_values);
  assert.deepEqual(migrateAnimaWorkflow(JSON.parse(JSON.stringify(wf))),wf);
 }
});

test('Retired INT8 model migrates inside subgraphs without changing names or wiring',()=>{
 const n={id:20,type:'AnimaImageTagger',title:'My title',inputs:[{name:'model_id',widget:{name:'model_id'}}],widgets_values:[true,'pixai_v1_int8','auto','{}',false],widgets_values_named:{model_id:'pixai_v1_int8'}};
 const g={nodes:[{type:'subgraph-id',widgets_values:['pixai_v1_int8'],title:'User group'}],definitions:{subgraphs:[{id:'subgraph-id',inputNode:{id:-10},inputs:[{name:'model_id',linkIds:[1]}],nodes:[n],links:[[1,-10,0,20,0,'COMBO']]}]}};
 migrateAnimaWorkflow(g);assert.equal(n.widgets_values[1],'pixai_v1_fp16');assert.equal(n.widgets_values_named.model_id,'pixai_v1_fp16');assert.equal(n.title,'My title');assert.equal(g.nodes[0].widgets_values[0],'pixai_v1_fp16');assert.equal(g.nodes[0].title,'User group');
});

test('Loading unrelated workflows preserves exact retired-ID text and third-party model fields',()=>{
 const nodes=[
  {id:1,type:'CLIPTextEncode',widgets_values:['pixai_v1_int8']},
  {id:2,type:'OtherTagger',widgets_values:['pixai_v1_int8'],widgets_values_named:{model_id:'pixai_v1_int8'}},
  {id:3,type:'OtherNode',widgets_values:[true,12,'pixai_v1_int8',false]},
 ];
 const workflow={nodes,definitions:{subgraphs:[{id:'unrelated',nodes:structuredClone(nodes),links:[]}]}};
 const original=structuredClone(workflow);
 createExtension({},{}).beforeConfigureGraph(workflow);
 assert.deepEqual(workflow,original);
});

test('Anima migration changes only the model field, including aliased nested promotions',()=>{
 for(const objectLinks of [true,false]){
  const workflow=read('../examples/Anima-Character-Sheet-Designer-Text-or-Image.json');
  const group=workflow.definitions.subgraphs.find(g=>g.nodes.some(n=>n.type==='AnimaImageTagger'));
  const instance=workflow.nodes.find(n=>n.type===group.id);
  const tagger=group.nodes.find(n=>n.type==='AnimaImageTagger');
  tagger.widgets_values[1]='pixai_v1_int8';
  tagger.widgets_values_named.model_id='pixai_v1_int8';
  tagger.widgets_values[3]='pixai_v1_int8'; // Arbitrary non-model text must survive.
  instance.widgets_values[2]='pixai_v1_int8';
  instance.widgets_values[3]='pixai_v1_int8'; // Unrelated promoted VAE widget.
  instance.widgets_values_named.model_id='pixai_v1_int8';
  instance.widgets_values_named.vae_name='pixai_v1_int8';
  // An outer group exposes an ordinary socket, an unrelated widget and then
  // the model under a user alias. The model's array index is therefore 1.
  const outer={id:'outer',inputNode:{id:-10},inputs:[
   {name:'picture',linkIds:[901]}, {name:'other',linkIds:[902]}, {name:'custom_model',linkIds:[903]},
  ],nodes:[instance],links:[
   [901,-10,0,instance.id,8,'IMAGE'],[902,-10,1,instance.id,3,'COMBO'],[903,-10,2,instance.id,2,'COMBO'],
  ]};
  const host={id:100,type:'outer',title:'My group',widgets_values:['pixai_v1_int8','pixai_v1_int8'],widgets_values_named:{other:'pixai_v1_int8',custom_model:'pixai_v1_int8'}};
  workflow.nodes=workflow.nodes.filter(n=>n!==instance);
  workflow.nodes.push(host);
  workflow.definitions.subgraphs.push(outer);
  if(!objectLinks)for(const g of workflow.definitions.subgraphs)g.links=g.links.map(l=>Array.isArray(l)?l:[l.id,l.origin_id,l.origin_slot,l.target_id,l.target_slot,l.type]);
  const expected=structuredClone(workflow);
  const expectedGroup=expected.definitions.subgraphs.find(g=>g.id===group.id);
  const expectedTagger=expectedGroup.nodes.find(n=>n.id===tagger.id);
  expectedTagger.widgets_values[1]='pixai_v1_fp16';expectedTagger.widgets_values_named.model_id='pixai_v1_fp16';
  const expectedInstance=expected.definitions.subgraphs.at(-1).nodes[0];
  expectedInstance.widgets_values[2]='pixai_v1_fp16';expectedInstance.widgets_values_named.model_id='pixai_v1_fp16';
  expected.nodes.at(-1).widgets_values[1]='pixai_v1_fp16';expected.nodes.at(-1).widgets_values_named.custom_model='pixai_v1_fp16';
  const hook=createExtension({},{}).beforeConfigureGraph;
  hook(workflow);assert.deepEqual(workflow,expected);
  const saved=JSON.parse(JSON.stringify(workflow));hook(saved);assert.deepEqual(saved,expected);
 }
});

test('Current template is unchanged and incomplete or cyclic promotions are left alone',()=>{
 const template=read('../examples/Anima-Character-Sheet-Designer-Text-or-Image.json');
 assert.deepEqual(migrateAnimaWorkflow(structuredClone(template)),template);
 const workflow={nodes:[{type:'loop',widgets_values:['pixai_v1_int8']},{type:'missing',widgets_values:['pixai_v1_int8']}],definitions:{subgraphs:[
  {id:'loop',inputNode:{id:-10},inputs:[{name:'model_id',linkIds:[1]}],nodes:[{id:1,type:'loop'}],links:[[1,-10,0,1,0,'COMBO']]},
 ]}};
 assert.deepEqual(migrateAnimaWorkflow(structuredClone(workflow)),workflow);
});
