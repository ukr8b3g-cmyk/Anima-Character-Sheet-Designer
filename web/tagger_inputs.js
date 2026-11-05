// Resolve literal controls through promoted subgraph inputs and Primitive nodes.
// Computed inputs stay unknown until execution; never guess a model or Boolean.
export function taggerSelection(node, app) {
 const root=app.rootGraph||app.graph;
 function find(graph,parents=[],seen=new Set()) {
  if(!graph||seen.has(graph))return;
  const next=new Set(seen).add(graph);
  const nodes=graph.nodes||graph._nodes||[];
  if(nodes.includes(node))return {graph,parents};
  for(const host of nodes){if(host.subgraph&&host.mode!==2&&host.mode!==4){const found=find(host.subgraph,[...parents,{host,graph}],next);if(found)return found;}}
 }
 const context=find(root)||{graph:node.graph,parents:[]};
 function value(target,name,ctx,seen=new Set()) {
  if(!target||seen.has(target))return;
  const next=new Set(seen).add(target),input=target.inputs?.find(i=>i.name===name);
  const link=input?.link!=null?(ctx.graph?.getLink?.(input.link)||ctx.graph?.links?.[input.link]):null;
  if(link){
   if(link.origin_id===ctx.graph?.inputNode?.id){
    const parent=ctx.parents.at(-1);if(!parent)return;
    const outer=parent.host.inputs?.[link.origin_slot];if(!outer)return;
    return value(parent.host,outer.name,{graph:parent.graph,parents:ctx.parents.slice(0,-1)},next);
   }
   const source=ctx.graph?.getNodeById?.(link.origin_id);
   if(['PrimitiveBoolean','PrimitiveString','PrimitiveNode'].includes(source?.type))return value(source,'value',ctx,next);
   return;
  }
  const widget=(input&&target.getWidgetFromSlot?.(input))||target.widgets?.find(w=>w.name===(input?.widget?.name||name));
  return widget?.value;
 }
 return {model:value(node,'model_id',context),useImage:value(node,'use_image',context)===true};
}
