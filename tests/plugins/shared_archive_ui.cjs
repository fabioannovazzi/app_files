"use strict";
const fs=require("node:fs"),vm=require("node:vm"),assert=require("node:assert/strict");
class Element {
  constructor(tag,text="",className=""){Object.assign(this,{tagName:tag,textContent:text,className,children:[],listeners:{},style:{},isConnected:true});}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;}
  setAttribute(){}
  addEventListener(name,callback){this.listeners[name]=callback;}
}
const walk=e=>[e,...e.children.flatMap(walk)], text=e=>walk(e).map(x=>x.textContent).join(" ");
(async()=>{
for(const product of ["Vera","Clara","Lucia"]){
  const root=new Element("div"),calls=[],opens=[];
  const node=(tag,text,cls)=>new Element(tag,text,cls),button=(label,action,cls)=>Object.assign(node("button",label,cls),{action});
  const version=n=>({label:`Saved opinion ${n}`,revision:n,issued_at:"2026-11-16",primary_format:"docx",formats:[{name:`opinion-${n}.docx`,format:"docx",available:true,reference:{entry_key:"opinion",revision:n,format:"docx"}},{name:`opinion-${n}.pdf`,format:"pdf",available:true,reference:{entry_key:"opinion",revision:n,format:"pdf"}}]});
  let catalogue={configured:true,level:"runs",client_id:"client",engagement_id:"eng",client_label:"Client",engagement_label:"Matter"};
  catalogue.incarico={client_id:"client",engagement_id:"eng",purpose:"Synthetic",conversations:[{title:"Existing chat",url:"codex://threads/test"}],results:[],documents:[],document_issues:[],deliverables:[{versions:[version(1),version(2)]}]};
  const context={document:{createTextNode:t=>node("text",t)},setTimeout,clearTimeout};vm.runInNewContext(fs.readFileSync(process.argv[2],"utf8"),context);
  const ui=context.StudioArchiveUI({product,root,node,button,getCatalogue:()=>catalogue,getHost:()=>({hostCapabilities:{experimental:{"openai/files":{}}}}),say:()=>{},request:async(method,args)=>{opens.push({method,args});return {};},call:async(name,args)=>{calls.push({name,args});return {name:`Saved revision ${args.reference.revision}`,path:`/verified/rev-${args.reference.revision}.${args.reference.format}`,preview:"Verified content"};},loadCatalogue:async()=>{},renderCatalogue:()=>ui.directory(),archiveFormShell:(title)=>{root.replaceChildren(node("h1",title));return root;}});
  const matterCatalogue=catalogue;
  catalogue={configured:true,level:"clients",clients:[{client_id:"client",display_name:"Client",registration_status:"registered"}],engagements:[]};
  ui.directory();assert(walk(root).some(e=>e.tagName==="button" && e.textContent==="Client"));
  catalogue={configured:true,level:"engagements",client_id:"client",client_label:"Client",clients:[],engagements:[{engagement_id:"eng",label:"Matter",status:"open"}]};
  ui.directory();assert(walk(root).some(e=>e.tagName==="button" && e.textContent==="Matter"));
  catalogue=matterCatalogue;
  ui.directory();assert(text(root).includes("Cerca nei documenti"));assert(text(root).includes("Storico"));assert(!text(root).includes("nuova chat"));
  const buttons=walk(root).filter(e=>e.tagName==="button");assert(!buttons.some(b=>b.textContent==="opinion-2.pdf"));
  await buttons.find(b=>b.textContent==="Existing chat").action();assert.equal(opens[0].method,"ui/open-link");assert.equal(opens[0].args.url,"codex://threads/test");
  await buttons.find(b=>b.textContent==="Saved opinion 1").action();assert.equal(calls[0].args.reference.revision,1);assert.equal(calls[0].args.client_id,"client");assert.equal(opens.at(-1).args.path,"/verified/rev-1.docx");
  await walk(root).find(b=>b.textContent==="opinion-1.pdf").action();assert.equal(calls.at(-1).args.reference.revision,1);assert.equal(opens.at(-1).args.path,"/verified/rev-1.pdf");
}
process.stdout.write("All three products: shared search, saved revisions, companion files and existing chat navigation passed\n");
})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});
