"use strict";
(() => {
  const product=archiveProduct, label=product[0].toUpperCase()+product.slice(1);
  const root=document.getElementById("app"), status=document.getElementById("status"), refresh=document.getElementById("refresh");
  let host={}, catalogue={}, epoch=0, sequence=0;
  const pending=new Map();
  const say=text=>{status.textContent=text;};
  function node(tag,text,className){const element=document.createElement(tag);if(text!==undefined)element.textContent=text;if(className)element.className=className;return element;}
  function button(text,action,className){const element=node("button",text,className);element.addEventListener("click",async()=>{element.disabled=true;try{await action();}catch(error){say(error.message);}finally{element.disabled=false;}});return element;}
  function request(method,params={},timeout=120000){return new Promise((resolve,reject)=>{
    const id=++sequence, timer=setTimeout(()=>{pending.delete(id);reject(new Error("Il collegamento con Claude non ha risposto. Riprova."));},timeout);
    pending.set(id,{resolve,reject,timer});window.parent.postMessage({jsonrpc:"2.0",id,method,params},"*");
  });}
  const names={vera_workspace_open:"open",vera_incarico_read:"read_matter",vera_incarico_document:"read_document",vera_workspace_archive_search:"search",vera_workspace_archive_source:"source",vera_workspace_archive_setup:"setup"};
  async function call(name,args={}){
    if(!names[name])throw new Error("Questa lavorazione si riprende dalla chat associata.");
    const result=await request("tools/call",{name:`${product}_archive_${names[name]}`,arguments:args});
    const data=result?._meta?.archive;
    if(result?.isError || !data || data.error)throw new Error(data?.error || "Archivio non disponibile. Riprova con Aggiorna.");return data;
  }
  async function loadCatalogue(args={}){
    const generation=++epoch;say("Caricamento dell’archivio…");root.setAttribute("aria-busy","true");
    try{const result=await call("vera_workspace_open",args);if(generation!==epoch)return;catalogue=result;ui.directory();say("");}
    finally{if(generation===epoch)root.setAttribute("aria-busy","false");}
  }
  function archiveFormShell(title,cancel,cancelLabel){const {nav,main}=ui.shell();nav.append(button(cancelLabel,cancel));main.append(node("p",catalogue.client_label,"eyebrow"),node("h1",title));return main;}
  const ui=StudioArchiveUI({root,node,button,call,request,say,getHost:()=>host,getCatalogue:()=>catalogue,loadCatalogue,renderCatalogue:()=>ui.directory(),archiveFormShell,product:label,showReviewRoute:async()=>{throw new Error("Riprendi questa lavorazione nella chat associata.");}});
  refresh.addEventListener("click",()=>loadCatalogue({...catalogue.client_id?{client_id:catalogue.client_id}:{},...catalogue.engagement_id?{engagement_id:catalogue.engagement_id}:{}}).catch(error=>say(error.message)));
  window.addEventListener("message",event=>{
    if(event.source!==window.parent || event.data?.jsonrpc!=="2.0")return;
    const message=event.data, entry=pending.get(message.id);
    if(entry && !message.method){clearTimeout(entry.timer);pending.delete(message.id);if(message.error)entry.reject(new Error(message.error.message));else entry.resolve(message.result);}
    if(message.method==="ui/notifications/tool-result" && epoch===0 && message.params?._meta?.archive){catalogue=message.params._meta.archive;++epoch;ui.directory();}
    if(message.method==="ui/resource-teardown"){++epoch;for(const entry of pending.values()){clearTimeout(entry.timer);entry.reject(new Error("Pannello chiuso."));}pending.clear();window.parent.postMessage({jsonrpc:"2.0",id:message.id,result:{}},"*");}
  });
  request("ui/initialize",{protocolVersion:"2026-01-26",appInfo:{name:`${label} Studio Archive`,version:"2.0.0"},appCapabilities:{availableDisplayModes:["fullscreen"]}}).then(result=>{
    host=result;refresh.disabled=false;window.parent.postMessage({jsonrpc:"2.0",method:"ui/notifications/initialized"},"*");if(epoch===0)return loadCatalogue();
  }).catch(error=>say(error.message));
})();
