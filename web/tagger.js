import {graphTransaction} from './integration.js';
import {getLocale,subscribeLocale} from './controller.js';
import {STATUS,DOWNLOAD,words} from './tagger_i18n.js';
import {taggerSelection} from './tagger_inputs.js';
export const GROUPS=['subject','hair','face','body','upper_outfit','lower_outfit','hands','feet','head_accessories','body_accessories'];
export const DEFAULT_CONFIG={schema_version:1,kind:'anima_tagger_config',thresholds:{general:null,character:null,style:null,copyright:null,meta:null,rating:null},include_character:false,include_copyright:false,exclude_tags:[],scope_additions:{},multi_subject_policy:'block',max_tags:128,device_id:0,refresh_nonce:0};
export function splitTags(text){return [...new Set(text.split(/[,\n]+/).map(t=>t.trim()).filter(Boolean))];}
const instances=new WeakMap();
export const NATIVE_FLAGS=['include_character','include_copyright','allow_multiple_subjects'];
export function migrateTaggerControls(node,info){
 if(!Array.isArray(info?.widgets_values))return;
 const saved=info.widgets_values,config=JSON.parse(node.widgets.find(w=>w.name==='config_json').value);
 const model=node.widgets.find(w=>w.name==='model_id');if(model?.value==='pixai_v1_int8')model.value='pixai_v1_fp16';
 const serial=node.widgets.filter(w=>w.serialize!==false);
 for(const key of NATIVE_FLAGS){const widget=serial.find(w=>w.name===key);if(widget&&typeof saved[serial.indexOf(widget)]!=='boolean')widget.value=key==='allow_multiple_subjects'?config.multi_subject_policy==='allow_with_warning':config[key];}
 // Legacy permission is retained for workflow compatibility, not acquisition policy.
 const legacy=node.widgets.find(w=>w.name==='allow_download');if(legacy)legacy.value=false;
}
export function installTagger(node,app,api){
 if(instances.has(node))return instances.get(node);
 const widgets=Object.fromEntries((node.widgets||[]).map(w=>[w.name,w]));const canonical=widgets.config_json;
 if(!canonical||!node.addDOMWidget)return;
 if(widgets.model_id?.value==='pixai_v1_int8')widgets.model_id.value='pixai_v1_fp16';
 const abort=new AbortController(),fields=[],bindings=[];let disposed=false,composing=false,draft=false,lastRaw='',syncing=false,executionSettings=null,locale=getLocale(app),statusKey='idle',lastMessage=null,errorText='';
 const settingsKey=()=>JSON.stringify(['use_image','model_id','device','config_json',...NATIVE_FLAGS].map(k=>widgets[k]?.value));
 const root=document.createElement('div');root.className='anima-tagger';
 const el=(tag,parent=root)=>{const e=document.createElement(tag);parent.append(e);return e;};
 const bind=(e,key,aria=false)=>{bindings.push({e,key,aria});return e;};
 bind(el('p'),'note');
 const modelInfo=el('p');modelInfo.className='anima-tagger-model';modelInfo.setAttribute('role','status');
 const modelPath=el('p');modelPath.className='anima-tagger-path';
 const modelDate=el('p');modelDate.className='anima-tagger-path';
 const progress=el('progress');progress.max=1;progress.value=0;progress.hidden=true;
 const checkModel=bind(el('button'),'check_model');checkModel.type='button';
 let modelState=null,modelError='',timer=null,requestVersion=0,requestedModel=null,selectionKey='',attempted=false;
 const selection=()=>taggerSelection(node,app);
 const downloadButton=node.addWidget?.('button','download_model',null,()=>refreshModel(true),{serialize:false});
 if(downloadButton){downloadButton.serialize=false;downloadButton.serializeValue=()=>undefined;}
 function renderModel(){
  const t=DOWNLOAD[locale],s=modelState;
  const state=modelError?'unavailable':s?.state||'checking';
  const bytes=s?`${(s.completed/1e6).toFixed(1)} / ${(s.total/1e6).toFixed(1)} MB`:'';
  const percent=s?.total?Math.floor(100*s.completed/s.total):0;
  modelInfo.textContent=`${selection().model??''} · ${t[state]||state}${s?' · '+bytes:''}${modelError?' — '+modelError:s?.error?' — '+s.error:''}`;
  modelPath.textContent=s?.path||'';modelPath.title=t.path;
  const date=value=>{const d=new Date(value);return Number.isFinite(d.getTime())?d.toLocaleString(locale==='ja'?'ja-JP':'en-US'):t.unknown;};
  modelDate.textContent=s?.state==='ready'?`${t.downloaded}: ${s.downloaded_at?date(s.downloaded_at):t.unknown}${s.file_modified_at?' · '+t.modified+': '+date(s.file_modified_at):''}`:'';
  progress.hidden=!['downloading','verifying'].includes(state);progress.value=s?.total?s.completed/s.total:0;
  if(downloadButton){
   downloadButton.label=['checking','downloading','verifying'].includes(state)?`${t[state]}${state==='downloading'?' '+percent+'%':''}`:state==='ready'?t.ready:words('download',locale).label;
   downloadButton.options??={};downloadButton.options.tooltip=words('download',locale).help;
  }
  node.setDirtyCanvas?.(true,true);
 }
 async function refreshModel(download=false,recheck=false,automatic=false){
  if(disposed||!api.fetchApi)return;
  if(download&&['checking','downloading','verifying','ready'].includes(modelState?.state))return;
  const model=selection().model;if(!['pixai_v1_fp16','wd_eva02_large_v3'].includes(model))return;
  clearTimeout(timer);const version=++requestVersion;requestedModel=model;
  try{
   const response=await api.fetchApi(`/anima_character_sheet_designer/v1/models/${encodeURIComponent(model)}${download?'/download':recheck?'?refresh=1':''}`,{method:download?'POST':'GET',signal:abort.signal});
   if(!response.ok)throw new Error(response.status===404?DOWNLOAD[locale].restart:`HTTP ${response.status}`);
   const data=await response.json();if(disposed||version!==requestVersion||model!==selection().model)return;
   modelState=data;modelError='';renderModel();
   if(automatic&&download&&['busy','checking'].includes(data.state))attempted=false;
   if(automatic&&data.state==='missing'&&selection().useImage&&!attempted){attempted=true;void refreshModel(true,false,true);}
   else if(['checking','downloading','verifying','busy'].includes(data.state))timer=setTimeout(()=>refreshModel(false,false,automatic),700);
  }catch(error){if(disposed||version!==requestVersion)return;modelError=error.message;modelState=null;renderModel();}
 }
 const status=el('p');status.className='anima-tagger-execution';status.setAttribute('role','status');
 const advancedButton=bind(el('button'),'advanced');advancedButton.type='button';advancedButton.setAttribute('aria-expanded','false');
 const advanced=el('div');advanced.hidden=true;
 const toggle=()=>{advanced.hidden=!advanced.hidden;advancedButton.setAttribute('aria-expanded',String(!advanced.hidden));node.setDirtyCanvas?.(true,true);};
 advancedButton.addEventListener('click',toggle,{signal:abort.signal});
 bind(el('p',advanced),'thresholds');
 const field=(key,kind,get,set)=>{
  const row=el('label',advanced);row.className='anima-tagger-field';bind(el('span',row),key);
  const input=el(kind==='text'?'textarea':'input',row);bindings.push({e:input,key,aria:true,titleOnly:true});
  if(kind!=='text')input.type=kind;
  if(kind==='number'){input.step='any';input.min='0';input.placeholder='';}
  if(kind==='text')input.rows=2;
  fields.push({input,get,set,kind});
  input.addEventListener('input',()=>{draft=true;stale();},{signal:abort.signal});
  input.addEventListener('change',()=>{if(!composing)flush();},{signal:abort.signal});return input;
 };
 for(const category of Object.keys(DEFAULT_CONFIG.thresholds)){const input=field(category,'number',c=>c.thresholds[category],(c,v)=>c.thresholds[category]=v===''?null:Number(v));input.max='1';input.step='0.01';}
 field('exclude','text',c=>c.exclude_tags.join(', '),(c,v)=>c.exclude_tags=splitTags(v));
 const maximum=field('maximum','number',c=>c.max_tags,(c,v)=>c.max_tags=Number(v));maximum.min='1';maximum.max='128';maximum.step='1';
 const gpu=field('gpu','number',c=>c.device_id,(c,v)=>c.device_id=Number(v));gpu.max='31';gpu.step='1';
 bind(el('p',advanced),'additions');
 for(const group of GROUPS)field(group,'text',c=>(c.scope_additions[group]||[]).join(', '),(c,v)=>{const tags=splitTags(v);if(tags.length)c.scope_additions[group]=tags;else delete c.scope_additions[group];});
 const refresh=bind(el('button',advanced),'refresh');refresh.type='button';
 bind(el('p',advanced),'decisions');const decisions=el('pre',advanced);decisions.className='anima-tagger-decisions';
 function renderStatus(){
  const t=STATUS[locale];
  if(lastMessage){const s=lastMessage;status.textContent=s.mode==='manual'?t.manual:`${s.model_id} · ${s.actual_device.toUpperCase()} · ${s.cache_hit?t.cached:s.total_seconds+' s'}${s.fallback_reason?' · '+s.fallback_reason:''}`;}
  else status.textContent=t[statusKey]+(errorText?' — '+errorText:'');
 }
 function setLocale(value){locale=value==='ja'?'ja':'en';for(const {e,key,aria,titleOnly} of bindings){const t=words(key,locale);e.title=t.help;if(!titleOnly)e.textContent=t.label;if(aria)e.setAttribute('aria-label',t.label);}for(const name of NATIVE_FLAGS){const w=widgets[name];if(w){const t=words(name==='allow_multiple_subjects'?'multiple':name,locale);w.label=t.label;w.options??={};w.options.tooltip=t.help;}}renderStatus();renderModel();node.setDirtyCanvas?.(true,true);}
 function stale(){if(!syncing){lastMessage=null;statusKey='stale';errorText='';decisions.textContent='';renderStatus();}}
 function commitWidget(widget,value){if(!widget||widget.value===value)return;graphTransaction(node,()=>{const old=widget.value;widget.value=value;widget.callback?.(value);node.onWidgetChanged?.(widget.name,value,old,widget);},app.canvas);}
 function flush(){
  if(disposed||!draft)return;
  if(composing)throw new Error(STATUS[locale].ime);
  const next=JSON.parse(canonical.value);
  for(const {input,set,kind} of fields){if(kind==='number'&&!input.checkValidity())throw new Error(STATUS[locale].numeric);set(next,kind==='checkbox'?input.checked:input.value);}
  commitWidget(canonical,JSON.stringify(next));draft=false;lastRaw=canonical.value;
 }
 function sync(){if(disposed)return;syncing=true;try{if(canonical.value!==lastRaw){const c=JSON.parse(canonical.value);for(const f of fields){const v=f.get(c);if(f.kind==='checkbox')f.input.checked=!!v;else f.input.value=v??'';}lastRaw=canonical.value;draft=false;}const current=selection(),key=JSON.stringify(current);if(selectionKey!==key||requestedModel!==current.model){selectionKey=key;attempted=false;requestVersion++;clearTimeout(timer);modelState=null;modelError='';refreshModel(false,true,current.useImage);}}catch(error){statusKey='invalid';errorText=error.message;lastMessage=null;renderStatus();}finally{syncing=false;}}
 root.addEventListener('compositionstart',()=>composing=true,{signal:abort.signal});
 root.addEventListener('compositionend',()=>{composing=false;draft=true;flush();},{signal:abort.signal});
 checkModel.addEventListener('click',()=>refreshModel(false,true),{signal:abort.signal});
 refresh.addEventListener('click',()=>{flush();const c=JSON.parse(canonical.value);c.refresh_nonce++;commitWidget(canonical,JSON.stringify(c));sync();stale();refreshModel(false,true);},{signal:abort.signal});
 const hidden=[];
 for(const name of ['config_json','allow_download']){const w=widgets[name];if(!w)continue;hidden.push([w,w.hidden]);w.hidden=true;if(w.element)w.element.hidden=true;}
 const widget=node.addDOMWidget('anima_tagger_ui','div',root,{serialize:false,hideOnZoom:false,getMinHeight:()=>240,getHeight:()=>'100%',onDraw:drawn=>{drawn.width=undefined;}});widget.serializeValue=()=>undefined;widget.serialize=false;
 const priorSerialize=canonical.serializeValue;canonical.serializeValue=function(...args){flush();return priorSerialize?priorSerialize.apply(this,args):this.value;};
 const hooks=[];
 function hook(name,callback,before=false){const old=node[name];const fn=function(...args){if(before)callback(...args);const value=old?.apply(this,args);if(!before)callback(...args);return value;};node[name]=fn;hooks.push(()=>{if(node[name]===fn)node[name]=old;});}
 hook('serialize',flush,true);hook('onConfigure',info=>{migrateTaggerControls(node,info);lastRaw='';sync();stale();});hook('onWidgetChanged',()=>{sync();stale();});hook('onConnectionsChange',stale);
 for(const name of ['use_image','model_id','device',...NATIVE_FLAGS]){const w=widgets[name];if(!w)continue;const old=w.callback;const callback=function(...args){const value=old?.apply(this,args);sync();stale();return value;};w.callback=callback;hooks.push(()=>{if(w.callback===callback)w.callback=old;});}
 api.addEventListener?.('executing',event=>{if(String(event.detail)===String(node.id)){executionSettings=settingsKey();stale();statusKey='running';renderStatus();}},{signal:abort.signal});
 api.addEventListener?.('execution_error',event=>{if(String(event.detail?.node_id)===String(node.id)){stale();statusKey='failed';errorText=event.detail.exception_message||'';renderStatus();}},{signal:abort.signal});
 hook('onExecuted',message=>{const s=message?.anima_tagger_status?.[0];if(!s)return;if(executionSettings!==null&&executionSettings!==settingsKey()){stale();return;}lastMessage=s;renderStatus();decisions.textContent=s.mode==='manual'?'':JSON.stringify({kept:s.groups,added:s.user_additions,labels:s.identity_labels,excluded:s.excluded,review:s.review},null,2);});
 const unsubscribe=subscribeLocale(app,setLocale);
 // Promoted widgets can change without invoking the inner node callback.
 // Only a selection change makes a request; idle polling performs no network I/O.
 const selectionTimer=setInterval(sync,700);selectionTimer.unref?.();
 const dispose=()=>{if(disposed)return;disposed=true;clearInterval(selectionTimer);clearTimeout(timer);abort.abort();unsubscribe();for(const undo of hooks)undo();canonical.serializeValue=priorSerialize;for(const [w,value] of hidden){w.hidden=value;if(w.element)w.element.hidden=!!value;}for(const owned of [widget,downloadButton]){const index=node.widgets?.indexOf(owned);if(index>=0){if(node.removeWidget)node.removeWidget(owned);else node.widgets.splice(index,1);}}root.remove();instances.delete(node);const previous=node.onAdded;node.onAdded=function(...args){const value=previous?.apply(this,args);node.onAdded=previous;installTagger(node,app,api);return value;};};
 hook('onRemoved',dispose);
 const instance={flush,sync,dispose,setLocale};instances.set(node,instance);sync();setLocale(locale);return instance;
}
export function taggerExtension(app,api){return {name:'Anima.ImageTagger',nodeCreated(node){if(node.comfyClass==='AnimaImageTagger'||node.type==='AnimaImageTagger')installTagger(node,app,api);}};}
