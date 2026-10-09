"use strict";
// Minimal event DOM and explicit fictional transport; this is not native-host acceptance.
const fs=require("node:fs"),vm=require("node:vm"),{webcrypto}=require("node:crypto");
function fixture(source,overrides={}){
  class Element{
    constructor(tag,text){this.tagName=tag.toUpperCase();this.text=text||"";this.children=[];this.attributes={};this.listeners={};this.value="";this.checked=false;this.disabled=false;}
    append(...items){for(const item of items){item.parentElement=this;this.children.push(item);}}
    replaceChildren(...items){this.children=[];this.append(...items);}
    setAttribute(key,value){this.attributes[key]=value;}
    addEventListener(event,action){this.listeners[event]=action;}
    dispatch(event){return this.listeners[event]?.();}
  }
  const digest="a".repeat(64),second="b".repeat(64);
  const proposal={case:{case_id:"FICTIONAL-RUN",demo:true,claim_period_id:"P2025",ledger_control_total:"100000.00",evidence:[{evidence_id:"E0001",description:"Fictional original",sha256:"c".repeat(64)}],costs:[{cost_id:"C1",book_amount:"100000.00"}]},rules:{demo:true,status:"REVIEWED",sources:[]},controls:[{key:"case/PB.SUBJECT",status:"NOT_TESTED",conclusion:"Fictional gap",evidence_ids:["E0001"],source_ids:[]}],narratives:[{section:"A",text:"Fictional narrative",evidence_ids:["E0001"],locator:"fixture, page 1"}],normalization_digest:"n".repeat(64),normalization_record:{plan:{},result:{}}};
  const calls=[],drafts=structuredClone(overrides.drafts||{}),record={...proposal};
  const base={work_ref:"fictional-work",revision:"r".repeat(64),source_ref:"s".repeat(64),review_ticket:"fictional-ticket",draft_revision:"initial",draft_stale:false,can_write:true,label:"Fictional Patent Box",run_status:"running",session:{demo:true,inputs:[{evidence_id:"E0001",description:"Fictional ledger.csv"}]},selected_sources:[],proposals:[{digest,claim_period_id:"P2025"},{digest:second,claim_period_id:"P2026"}],files:{["proposal_"+digest+".json"]:"p",["review_"+digest+".md"]:"q",["calculation_"+digest+"/fascicolo_A_B.pdf"]:"x"},...overrides};
  delete base.drafts;
  let current,panel,epoch=0,dirty=false,serial=0;
  const node=(tag,text)=>new Element(tag,text),collect=element=>[element,...element.children.flatMap(collect)];
  const api={node,say(){},setDirty(value){dirty=value;},leaveDraft(){if(dirty)throw new Error("Unsaved fictional fields");},enter(){return ++epoch;},isCurrent(value){return value===epoch;},shell(){panel?.dispose();current={nav:node("nav"),main:node("main")};return current;},openWorks:async()=>{},button(label,action){const element=node("button",label);element.action=action;return element;},confirmation(parent,text){const label=node("label"),input=node("input");input.type="checkbox";input.setAttribute("aria-label",text);label.append(input,node("span",text));parent.append(label);return input;},async call(name,args){
    calls.push({name,args:structuredClone(args)});
    if(name.endsWith("_setup")){const d=drafts[args.operation]||{fields:{},stamp:"initial"};return {...structuredClone(base),operation:args.operation,fields:structuredClone(d.fields),draft_revision:d.stamp};}
    if(name.endsWith("_draft_save")){drafts[args.operation]={fields:structuredClone(args.fields),stamp:"draft-"+(++serial)};return {draft_revision:drafts[args.operation].stamp};}
    if(name.endsWith("_draft_clear")){drafts[args.operation]={fields:{},stamp:"draft-"+(++serial)};base.draft_stale=false;return {draft_revision:drafts[args.operation].stamp};}
    if(name.endsWith("_read"))return {content:args.file_ref.endsWith(".md")?"Whole fictional proposal, open controls and unsigned draft":JSON.stringify(record)};
    if(name.endsWith("_execute"))return overrides.refusal?{status:"refused",error:"Fictional producer refusal"}:{status:"complete"};
    if(name.endsWith("_artifact")){const raw=Buffer.from("%PDF-fictional-test-only");return {content:raw.toString("base64"),byte_count:raw.byteLength,sha256:require("node:crypto").createHash("sha256").update(raw).digest("hex"),mime_type:"application/pdf"};}
    throw new Error("Unexpected fictional tool "+name);
  }};
  const sandbox={globalThis:{},structuredClone,crypto:webcrypto,setTimeout:()=>1,clearTimeout(){},URL,Blob,atob,Object,JSON,Number,Boolean,String,Uint8Array,Array};
  vm.runInNewContext(fs.readFileSync(source,"utf8"),sandbox,{filename:source});panel=sandbox.globalThis.VeraPatentBox.create(api);
  const find=predicate=>collect(current.main).find(predicate);
  return {panel,base,drafts,calls,digest,second,proposal,record,get dirty(){return dirty;},all:()=>collect(current.main),field:label=>find(element=>element.attributes["aria-label"]===label),button:label=>find(element=>element.tagName==="BUTTON"&&element.text===label),confirmation:()=>find(element=>element.type==="checkbox"),text:()=>collect(current.main).map(element=>element.text).join(" ")};
}
module.exports={fixture};
