import {getLocale, subscribeLocale} from './controller.js';

// Native canvas labels can retain the locale used at node creation. Read the
// same backend translations as ComfyUI, keeping names, titles and links intact.
const catalogs=new WeakMap(), instances=new WeakMap();
export function applyNodeLabels(node, definition) {
  if(!definition)return;
  for(const input of node.inputs??[]){const t=definition.inputs?.[input.name];if(t){input.label=t.name;input.tooltip=t.tooltip;}}
  for(const widget of node.widgets??[]){const t=definition.inputs?.[widget.name];if(t){widget.label=t.name;widget.options??={};widget.options.tooltip=t.tooltip;}}
  for(const [index,output] of (node.outputs??[]).entries()){const t=definition.outputs?.[index];if(t){output.label=t.name;output.tooltip=t.tooltip;}}
  node.setDirtyCanvas?.(true,true);
}
export function bindNodeLabels(node,app,api) {
  // Only the supplied template opts in. Other subgraphs and user aliases stay
  // untouched. These are translation profiles, not additional public nodes.
  const profile=node.properties?.anima_sheet_locale;
  const grouped=['AnimaSheetInputs','AnimaSheetRender'].includes(profile);
  const type=grouped?profile:node.comfyClass??node.type;
  if((!grouped&&!['AnimaImageTagger','AnimaCharacterSheetDesigner','AnimaCharacterSheetAssemble'].includes(type))||instances.has(node)||!api.fetchApi)return;
  let active=true;
  let english;
  if(!catalogs.has(api))catalogs.set(api,Promise.resolve().then(()=>api.fetchApi('/i18n')).then(r=>{if(!r.ok)throw new Error('i18n');return r.json();}).catch(()=>null));
  const render=async()=>{const data=await catalogs.get(api);english=data?.en?.nodeDefs?.[type];if(active)applyNodeLabels(node,data?.[getLocale(app)]?.nodeDefs?.[type]??english);};
  const unsubscribe=subscribeLocale(app,render), priorConfigure=node.onConfigure, priorRemove=node.onRemoved, priorAdd=node.onAdded, priorSerialize=node.onSerialize;
  // Save ordinary English aliases regardless of the current display locale.
  // Never change the live widget values, socket names, node titles or links.
  if(grouped)node.onSerialize=function(data){const value=priorSerialize?.call(this,data);applyNodeLabels(data,english);return value;};
  node.onConfigure=function(...args){const value=priorConfigure?.apply(this,args);render();return value;};
  node.onRemoved=function(...args){active=false;unsubscribe();return priorRemove?.apply(this,args);};
  node.onAdded=function(...args){const value=priorAdd?.apply(this,args);if(!active){instances.delete(node);node.onConfigure=priorConfigure;node.onRemoved=priorRemove;node.onAdded=priorAdd;node.onSerialize=priorSerialize;bindNodeLabels(node,app,api);}return value;};
  instances.set(node,true);render();
}
