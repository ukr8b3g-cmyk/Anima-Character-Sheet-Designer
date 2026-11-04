function migrateModelValue(node, index, name) {
 if (Array.isArray(node.widgets_values) && node.widgets_values[index] === 'pixai_v1_int8') {
  node.widgets_values[index] = 'pixai_v1_fp16';
 }
 if (node.widgets_values_named?.[name] === 'pixai_v1_int8') {
  node.widgets_values_named[name] = 'pixai_v1_fp16';
 }
}

// Follow the promoted input to its actual widget, including nested subgraphs.
// Names/labels alone cannot establish that a third-party model_id belongs to us.
function promotedWidget(graph, slot, definitions, visited = new Set()) {
 const key = `${graph.id}:${slot}`;
 if (visited.has(key)) return null;
 visited.add(key);
 const input = graph.inputs?.[slot];
 for (const raw of graph.links ?? []) {
  const [id, origin, originSlot, target, targetSlot] = Array.isArray(raw)
   ? raw : [raw.id, raw.origin_id, raw.origin_slot, raw.target_id, raw.target_slot];
  if (origin !== graph.inputNode?.id || originSlot !== slot || !input?.linkIds?.includes(id)) continue;
  const node = graph.nodes?.find(n => n.id === target);
  if (!node) continue;
  const nested = definitions.get(node.type);
  if (nested) return promotedWidget(nested, targetSlot, definitions, visited);
  const widget = node.inputs?.[targetSlot]?.widget;
  if (widget) return {isModel: node.type === 'AnimaImageTagger' && widget.name === 'model_id'};
 }
 return null;
}

// Migrate only this package's retired sockets/widgets; preserve node titles/settings.
export function migrateAnimaWorkflow(data, definitions = new Map()){
 for (const graph of data.definitions?.subgraphs ?? []) definitions.set(graph.id, graph);
 for(const graph of data.definitions?.subgraphs??[])migrateAnimaWorkflow(graph, definitions);
 for(const node of data.nodes??[]){
  if (node.type === 'AnimaImageTagger') migrateModelValue(node, 1, 'model_id');
  const definition = definitions.get(node.type);
  if (definition) {
   // ComfyUI serializes promoted values in definition-input order, omitting
   // ordinary sockets. Instance inputs can omit unconnected promoted slots.
   let widgetIndex = 0;
   for (const [slot, input] of (definition.inputs ?? []).entries()) {
    const widget = promotedWidget(definition, slot, definitions);
    if (!widget) continue;
    if (widget.isModel) migrateModelValue(node, widgetIndex, input.name);
    widgetIndex++;
   }
  }
  // A native node-definition refresh can rename the first six old sockets
  // before saving, leaving a duplicate view_records socket at index 6.
  const refreshed=node.outputs?.length===7&&node.outputs[4]?.name==='sheet_plan'&&node.outputs[5]?.name==='view_records'&&node.outputs[6]?.name==='view_records';
  if(node.type==='AnimaCharacterSheetDesigner'&&(node.outputs?.[4]?.name==='legacy_image_unused'||refreshed)){
   if(node.outputs[4].links?.length)throw new Error('Disconnect the obsolete legacy_image_unused output before loading this workflow.');
   node.outputs.splice(4,1);
   node.outputs[4].name='sheet_plan';
   if(refreshed){delete node.outputs[4].label;delete node.outputs[4].tooltip;}
   node.outputs.forEach((o,i)=>{if('slot_index' in o)o.slot_index=i;});
   for(const link of data.links??[]){
    if(Array.isArray(link)){if(link[1]===node.id&&link[2]>4)link[2]--;}
    else if(link.origin_id===node.id&&link.origin_slot>4)link.origin_slot--;
   }
  }
  if(node.type==='AnimaImageTagger'){
   // Original six positional widgets included the embedded filename at index 3.
   if(node.widgets_values?.length===6&&typeof node.widgets_values[4]==='string'&&node.widgets_values[4].includes('anima_tagger_config'))node.widgets_values.splice(3,1);
   if(node.widgets_values_named)delete node.widgets_values_named.image_name;
   const index=node.inputs?.findIndex(i=>i.name==='image_name')??-1;
   if(index>=0){
    if(node.inputs[index].link!=null)throw new Error('Replace image_name with a connected Load Image before loading.');
    node.inputs.splice(index,1);
    for(const link of data.links??[]){
     if(Array.isArray(link)){if(link[3]===node.id&&link[4]>index)link[4]--;}
     else if(link.target_id===node.id&&link.target_slot>index)link.target_slot--;
    }
   }
  }
 }
 return data;
}
