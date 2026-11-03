import test from 'node:test';
import assert from 'node:assert/strict';
import {installTagger, DEFAULT_CONFIG, NATIVE_FLAGS} from '../web/tagger.js';
import {bindNodeLabels} from '../web/node_labels.js';
import {readFile} from 'node:fs/promises';

// Small DOM boundary: exercise persistence/lifecycle rather than browser layout.
class Element extends EventTarget {
  constructor(tag){super();this.tagName=tag.toUpperCase();this.children=[];this.value='';this.checked=false;this.hidden=false;this.attributes={};}
  append(e){this.children.push(e);e.parent=this;}
  setAttribute(k,v){this.attributes[k]=v;}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(e=>e!==this);}
  checkValidity(){return this.value==='' || Number.isFinite(Number(this.value)) && Number(this.value)>=Number(this.min??-Infinity) && Number(this.value)<=Number(this.max??Infinity);}
  click(){this.dispatchEvent(new Event('click'));}
}
globalThis.document={createElement:tag=>new Element(tag)};
function setup(saved){
  const api=new EventTarget();api.apiURL=p=>p;
  let resizeCalls=0;
  const node={id:20,widgets:Object.entries({use_image:false,model_id:'wd_eva02_large_v3',device:'auto',config_json:JSON.stringify(DEFAULT_CONFIG),allow_download:false,include_character:false,include_copyright:false,allow_multiple_subjects:false,...saved}).map(([name,value])=>({name,value})),setSize(){resizeCalls++;},computeSize(){return [420,300];},setDirtyCanvas(){},serialize(){return this.widgets.filter(w=>w.serialize!==false).map(w=>w.serializeValue?w.serializeValue():w.value);},addWidget(type,name,value,callback,options){const w={type,name,value,callback,options};this.widgets.push(w);return w;},addDOMWidget(name,type,element,options){const w={name,element,options};this.widgets.push(w);return w;}};
  let changes=0;
  const ui=installTagger(node,{canvas:{emitBeforeChange(){},emitAfterChange(){changes++;}}},api);
  const root=node.widgets.find(w=>w.name==='anima_tagger_ui').element;
  const all=()=>{const a=[];function walk(e){a.push(e);e.children.forEach(walk);}walk(root);return a;};
  const field=label=>all().find(e=>e.tagName==='LABEL' && e.children[0]?.textContent===label)?.children[1];
  const config=()=>JSON.parse(node.widgets.find(w=>w.name==='config_json').value);
  return {node,ui,api,root,all,field,config,changes:()=>changes,resizeCalls:()=>resizeCalls};
}
test('Tagger drafts serialize, reload and clone without a second visual widget',()=>{
  const a=setup();const input=a.field('Exclude raw tags');input.value='blue_hair, blue_hair\noutdoors';input.dispatchEvent(new Event('input'));
  a.node.serialize();assert.deepEqual(a.config().exclude_tags,['blue_hair','outdoors']);assert.equal(a.changes(),1);
  a.ui.sync();assert.equal(installTagger(a.node,{},a.api),a.ui);
  const saved=Object.fromEntries(a.node.widgets.filter(w=>w.serialize!==false).map(w=>[w.name,w.value]));
  const b=setup(saved);assert.equal(b.field('Exclude raw tags').value,'blue_hair, outdoors');assert.equal(b.node.widgets.filter(w=>w.name==='anima_tagger_ui').length,1);
  a.ui.dispose();b.ui.dispose();
});
test('Tagger configure/Undo, composition guard, and immediate queue serialize',()=>{
  const a=setup();const original=a.node.widgets.find(w=>w.name==='config_json').value;
  const input=a.field('Feet / footwear');input.value='black_boots';input.dispatchEvent(new Event('input'));a.root.dispatchEvent(new Event('compositionstart'));
  assert.throws(()=>a.node.serialize(),/IME/);a.root.dispatchEvent(new Event('compositionend'));assert.deepEqual(a.config().scope_additions.feet,['black_boots']);
  a.node.widgets.find(w=>w.name==='config_json').value=original;a.node.onConfigure();assert.equal(a.field('Feet / footwear').value,'');
  a.ui.dispose();
});
test('Tagger rejects stale async results and survives delete/Undo re-add',()=>{
  const a=setup();a.api.dispatchEvent(Object.assign(new Event('executing'),{detail:20}));
  a.node.widgets.find(w=>w.name==='model_id').value='pixai_v1_fp16';a.node.onWidgetChanged();
  a.node.onExecuted({anima_tagger_status:[{mode:'manual'}],anima_tagger_text:['old result']});
  assert.match(a.all().find(e=>e.className==='anima-tagger-execution').textContent,/Settings changed/);
  a.node.onRemoved();assert.equal(a.node.widgets.filter(w=>w.name==='anima_tagger_ui').length,0);
  a.node.onAdded();assert.equal(a.node.widgets.filter(w=>w.name==='anima_tagger_ui').length,1);
  a.node.onRemoved();
});
test('Tagger config changes invalidate status; text/image editors absent; node size is stable',()=>{
  const a=setup();a.node.onExecuted({anima_tagger_status:[{mode:'manual'}],anima_tagger_text:['exact manual']});
  const status=a.all().find(e=>e.className==='anima-tagger-execution');assert.match(status.textContent,/Text input/);
  a.node.onWidgetChanged();assert.match(status.textContent,/Settings changed/);
  const input=a.field('Appearance score');input.value='1.1';input.dispatchEvent(new Event('input'));assert.throws(()=>a.node.serialize(),/numeric/);
  assert.ok(!a.all().some(e=>e.type==='file'||e.attributes['aria-label']==='Last execution prompt'));
  const visual=a.node.widgets.find(w=>w.name==='anima_tagger_ui');assert.equal(visual.options.getHeight(),'100%');
  a.all().find(e=>e.tagName==='BUTTON'&&e.textContent==='Advanced settings').click();assert.equal(a.resizeCalls(),0);
  a.ui.setLocale('ja');assert.ok(a.field('被写体の人数・種類').title.includes('1girl'));assert.match(status.textContent,/設定/);
  a.ui.setLocale('en');assert.ok(a.field('Subject count / type').title.includes('1girl'));
  a.ui.dispose();
});

test('Native labels switch locales without renaming nodes, inputs or outputs',async()=>{
  const en=JSON.parse(await readFile(new URL('../locales/en/nodeDefs.json',import.meta.url),'utf8'));
  const ja=JSON.parse(await readFile(new URL('../locales/ja/nodeDefs.json',import.meta.url),'utf8'));
  let locale='en',calls=0;const settings=new EventTarget();
  const app={ui:{settings},extensionManager:{setting:{get:()=>locale}}};
  const api={async fetchApi(){calls++;return {ok:true,json:async()=>({en:{nodeDefs:en},ja:{nodeDefs:ja}})};}};
  const nodes=['AnimaImageTagger','AnimaCharacterSheetDesigner','AnimaCharacterSheetAssemble'].map(type=>({type,title:'User title',inputs:Object.keys(en[type].inputs??{}).map(name=>({name})),outputs:Object.keys(en[type].outputs??{}).map(i=>({name:'stable_'+i})),widgets:[{name:'device'}]}));
  for(const node of nodes)bindNodeLabels(node,app,api);
  await new Promise(resolve=>setImmediate(resolve));assert.equal(calls,1);
  locale='ja';settings.dispatchEvent(new Event('Comfy.Locale.change'));await new Promise(resolve=>setImmediate(resolve));
  assert.equal(nodes[0].inputs.find(i=>i.name==='manual_prompt').label,'テキスト入力');
  assert.equal(nodes[0].widgets[0].label,'解析デバイス');
  for(const node of nodes){assert.equal(node.title,'User title');assert.equal(node.outputs[0].name,'stable_0');node.onRemoved();node.onAdded();}
  locale='en';settings.dispatchEvent(new Event('Comfy.Locale.change'));await new Promise(resolve=>setImmediate(resolve));
  assert.equal(nodes[0].inputs.find(i=>i.name==='manual_prompt').label,'Text input');
  nodes.forEach(n=>n.onRemoved());
});

test('Legacy JSON flags migrate to native controls and explicit false survives reload',()=>{
  const cfg={...DEFAULT_CONFIG,include_character:true,include_copyright:true,multi_subject_policy:'allow_with_warning'};
  const old=[true,'pixai_v1_int8','auto',JSON.stringify(cfg),true];
  const a=setup({config_json:old[3],allow_download:true});a.node.onConfigure({widgets_values:old});
  for(const key of NATIVE_FLAGS)assert.equal(a.node.widgets.find(w=>w.name===key).value,true);
  assert.equal(a.node.widgets.find(w=>w.name==='allow_download').value,false);
  assert.ok(!a.all().some(e=>e.type==='checkbox'));
  const flag=a.node.widgets.find(w=>w.name==='include_character');flag.value=false;flag.callback(false);
  const saved=a.node.serialize();a.node.onConfigure({widgets_values:saved});assert.equal(flag.value,false);
  assert.equal(saved.length,8);assert.equal(a.node.widgets.find(w=>w.name==='download_model').serialize,false);
  a.node.onRemoved();a.node.onAdded();assert.equal(a.node.widgets.filter(w=>w.name==='download_model').length,1);a.node.onRemoved();
});

test('Download button sends an explicit POST; installed status does not redownload',async()=>{
  const a=setup();let state='missing';const calls=[];
  a.api.fetchApi=async(path,options)=>{calls.push({path,method:options.method});if(options.method==='POST')state='ready';return {ok:true,json:async()=>({state,model_id:'pixai_v1_fp16',downloaded_at:'2026-11-03T00:00:00+00:00',completed:state==='ready'?100:0,total:100,path:'models/anima_tagger/pixai_v1_fp16'})};};
  a.node.widgets.find(w=>w.name==='model_id').value='pixai_v1_fp16';a.ui.sync();await new Promise(resolve=>setImmediate(resolve));
  const button=a.node.widgets.find(w=>w.name==='download_model');assert.equal(button.label,'Download selected model');
  await button.callback();assert.equal(calls.at(-1).method,'POST');assert.match(calls.at(-1).path,/pixai_v1_fp16\/download$/);assert.equal(button.label,'Model ready');
  assert.ok(a.all().some(e=>e.textContent?.startsWith('Downloaded:')));const count=calls.length;await button.callback();assert.equal(calls.length,count);
  a.ui.setLocale('ja');assert.equal(button.label,'モデル準備完了');a.ui.dispose();
});

test('Model-file recheck uses GET from ready/missing; analysis refresh also rechecks',async()=>{
 const a=setup();let state='ready';const calls=[];
 a.api.fetchApi=async(path,options)=>{calls.push({path,method:options.method});return {ok:true,json:async()=>({state,completed:0,total:100})};};
 const button=a.all().find(e=>e.tagName==='BUTTON'&&e.textContent==='Check model files');
 assert.ok(button);button.click();await new Promise(resolve=>setImmediate(resolve));
 assert.deepEqual(calls.at(-1),{path:'/anima_character_sheet_designer/v1/models/wd_eva02_large_v3?refresh=1',method:'GET'});
 state='missing';button.click();await new Promise(resolve=>setImmediate(resolve));
 assert.match(a.all().find(e=>e.className==='anima-tagger-model').textContent,/Not installed/);
 a.all().find(e=>e.tagName==='BUTTON'&&e.textContent==='Refresh analysis / retry device').click();
 await new Promise(resolve=>setImmediate(resolve));assert.equal(calls.at(-1).method,'GET');
 assert.ok(calls.every(x=>x.method==='GET'));a.ui.setLocale('ja');assert.equal(button.textContent,'モデルファイルを再確認');
 a.ui.dispose();
});

test('Template subgraph ports follow locale, save English, and retain values and user titles',async()=>{
 const en=JSON.parse(await readFile(new URL('../locales/en/nodeDefs.json',import.meta.url),'utf8'));
 const ja=JSON.parse(await readFile(new URL('../locales/ja/nodeDefs.json',import.meta.url),'utf8'));
 let locale='en';const settings=new EventTarget();
 const app={ui:{settings},extensionManager:{setting:{get:()=>locale}}};
 const api={fetchApi:async()=>({ok:true,json:async()=>({en:{nodeDefs:en},ja:{nodeDefs:ja}})})};
 for(const profile of ['AnimaSheetInputs','AnimaSheetRender']){
  const node={type:'unchanged-uuid',title:'User group',properties:{anima_sheet_locale:profile},
   inputs:Object.keys(en[profile].inputs).map(name=>({name,link:17})),
   outputs:Object.keys(en[profile].outputs).map((_,i)=>({name:'stable_'+i,links:[18]})),
   widgets:[{name:'device',value:'auto'},{name:'model_id',value:'pixai_v1_fp16'}]};
  bindNodeLabels(node,app,api);await new Promise(resolve=>setImmediate(resolve));
  locale='ja';settings.dispatchEvent(new Event('Comfy.Locale.change'));await new Promise(resolve=>setImmediate(resolve));
  assert.equal(node.outputs[0].label,ja[profile].outputs[0].name);
  const saved=structuredClone({type:node.type,title:node.title,inputs:node.inputs,outputs:node.outputs});node.onSerialize(saved);
  assert.equal(saved.outputs[0].label,en[profile].outputs[0].name);
  assert.equal(node.outputs[0].label,ja[profile].outputs[0].name);
  assert.equal(node.title,'User group');assert.ok(node.inputs.every(i=>i.link===17));
  assert.deepEqual(node.widgets.map(w=>w.value),['auto','pixai_v1_fp16']);
  locale='en';settings.dispatchEvent(new Event('Comfy.Locale.change'));await new Promise(resolve=>setImmediate(resolve));
  assert.equal(node.outputs[0].label,en[profile].outputs[0].name);node.onRemoved();
 }
 const other={type:'other-uuid',inputs:[{name:'image',label:'My input'}]};bindNodeLabels(other,app,api);
 assert.equal(other.onSerialize,undefined);assert.equal(other.inputs[0].label,'My input');
});
