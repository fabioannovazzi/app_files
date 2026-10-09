"use strict";
// Fictional protocol and event DOM, independent of Codex native-host acceptance.
const fs=require("node:fs"),vm=require("node:vm"),{webcrypto,createHash}=require("node:crypto");
function fixture(source,overrides={}){
  class Element{
    constructor(tag,text){this.tagName=tag.toUpperCase();this.text=text||"";this.children=[];this.attributes={};this.listeners={};this.value="";this.checked=false;this.disabled=false;}
    append(...items){for(const item of items){item.parentElement=this;this.children.push(item);}}
    replaceChildren(...items){this.children=[];this.append(...items);}
    setAttribute(key,value){this.attributes[key]=value;}
    addEventListener(event,action){this.listeners[event]=action;}
    dispatch(event){return this.listeners[event]?.();}
  }
  const items=overrides.items||Array.from({length:2},(_,index)=>({id:"SOURCE-"+index,title:"fictional-source-"+index+".pdf",kind:".pdf"}));
  const base={work_ref:"fictional-intake",revision:"a".repeat(64),review_ticket:"fictional-ticket",status:"ready",can_prepare:true,can_discard:true,roles:["open_items","bank_statement"],adapters:["open_items_text_v1","bank_statement_text_v1"],...overrides};
  const draft={fields:structuredClone(overrides.fields||{}),draft_revision:"initial-draft",stale:Boolean(overrides.stale)};
  const calls=[],opened=[],messages=[],urls=[],revoked=[];let current,panel,dirty=false,epoch=0,serial=0;
  const node=(tag,text)=>new Element(tag,text),collect=element=>[element,...element.children.flatMap(collect)];
  const api={node,setDirty(value){dirty=value;},say(text,error){messages.push({text,error});},leaveDraft(){if(dirty)throw new Error("Unsaved fictional fields");},enter(){return ++epoch;},isCurrent(value){return value===epoch;},shell(){panel?.dispose();current={nav:node("nav"),main:node("main")};return current;},openWorks:async()=>{},openReview:async workRef=>{opened.push(workRef);},
    button(label,action,style,flushLocal=true){const button=node("button",label);button.flushLocal=flushLocal;button.action=async()=>{if(flushLocal)await panel?.flush();return action();};return button;},
    confirmation(parent,text){const label=node("label"),input=node("input");input.type="checkbox";input.setAttribute("aria-label",text);label.append(input,node("span",text));parent.append(label);return input;},
    async call(name,args){
      calls.push({name,args:structuredClone(args)});
      if(name.endsWith("_setup")){const offset=args.offset||0;return {...structuredClone(base),items:structuredClone(items.slice(offset,offset+30)),total:items.length,has_more:offset+30<items.length,draft:structuredClone(draft)};}
      if(name.endsWith("_draft_save")){if(base.save_error)throw new Error("Fictional draft refusal");draft.fields=structuredClone(args.fields);draft.draft_revision="draft-"+(++serial);return {draft_revision:draft.draft_revision};}
      if(name.endsWith("_draft_clear")){draft.fields={};draft.draft_revision="";draft.stale=false;base.save_error=false;return {draft_revision:"",cleared:true};}
      if(name.endsWith("_prepare")){if(base.prepare_error){base.status="recovery_required";base.can_prepare=false;throw new Error("Fictional uncertain producer outcome");}base.status="prepared";base.can_prepare=false;return {status:"ready_for_review",report_ready:false,professional_approval:false,run_completed:false};}
      if(name.endsWith("_source")){const raw=Buffer.from("%PDF-1.4\nFICTIONAL ORIGINAL SOURCE");return {input_id:args.input_id,name:"fictional.pdf",content:raw.toString("base64"),encoding:"base64",mime_type:"application/pdf",byte_count:raw.byteLength,sha256:base.tampered_source?"0".repeat(64):createHash("sha256").update(raw).digest("hex")};}
      throw new Error("Unexpected fictional tool "+name);
    }
  };
  const sandbox={globalThis:{},structuredClone,crypto:webcrypto,setTimeout:()=>1,clearTimeout(){},URL:{createObjectURL(value){urls.push(value);return "blob:fictional-"+urls.length;},revokeObjectURL(value){revoked.push(value);}},Blob,atob,Object,JSON,Number,Boolean,String,Uint8Array,Array,Set};
  vm.runInNewContext(fs.readFileSync(source,"utf8"),sandbox,{filename:source});panel=sandbox.globalThis.VeraOpenItemsIntake.create(api);
  const find=predicate=>collect(current.main).find(predicate);
  return {panel,base,draft,calls,opened,messages,urls,revoked,get dirty(){return dirty;},all:()=>collect(current.main),field:label=>find(element=>element.attributes["aria-label"]===label),button:label=>find(element=>element.tagName==="BUTTON"&&element.text===label),text:()=>collect(current.main).map(element=>element.text).join(" ")};
}
module.exports={fixture};
