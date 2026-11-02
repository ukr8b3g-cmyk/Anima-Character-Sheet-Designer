// Migrate only this package's retired sockets/widgets; preserve node titles/settings.
export function migrateAnimaWorkflow(data){
 for(const graph of data.definitions?.subgraphs??[])migrateAnimaWorkflow(graph);
 for(const node of data.nodes??[]){
  // Retired model IDs in promoted widgets also migrate; node titles stay intact.
  if(Array.isArray(node.widgets_values))node.widgets_values=node.widgets_values.map(v=>v==='pixai_v1_int8'?'pixai_v1_fp16':v);
  if(node.widgets_values_named?.model_id==='pixai_v1_int8')node.widgets_values_named.model_id='pixai_v1_fp16';
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
