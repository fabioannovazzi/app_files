"use strict";
// A minimal event-driven DOM and injected tool transport; no actual native host.
const fs=require("node:fs"),vm=require("node:vm");
function fixture(source, overrides={}) {
  class Element {
    constructor(tag,text){this.tagName=tag.toUpperCase();this.text=text||"";this.children=[];this.attributes={};this.listeners={};this.checked=false;this.disabled=false;this.value="";}
    append(...items){for(const child of items){if(child.parentElement)child.parentElement.children=child.parentElement.children.filter(item=>item!==child);child.parentElement=this;this.children.push(child);}}
    setAttribute(key,value){this.attributes[key]=value;}
    addEventListener(event,action){this.listeners[event]=action;}
    focus(){} select(){}
    dispatch(event){return this.listeners[event]?.();}
  }
  const calls=[],page={work_ref:"fictional-work",revision:"r".repeat(64),source_ref:"s".repeat(64),review_ticket:"fictional-signed-scope",draft_revision:"initial",draft_stale:false,can_write:true,fields:{task:"",subject_ids:[],model_session_ref:"",raw_source_ids:[]},tasks:["WORKFLOW_GUIDANCE","SOURCE_INTERPRETATION"],sources:[],grants:[],public_suggestions:[],...structuredClone(overrides)};
  const draft={...structuredClone(page),fields:{decision:"",reviewer_id:"",reviewer_role:"",notes:""}};
  let generation=0,dirty=false,current,serial=0,panel;
  const node=(tag,text)=>new Element(tag,text);
  function collect(element){return [element,...element.children.flatMap(collect)];}
  function find(predicate){return collect(current.main).find(predicate);}
  const api={node,say(){},setDirty(value){dirty=value;},leaveDraft(){if(dirty)throw new Error("Unsaved literal fields");},enter(){return ++generation;},isCurrent(value){return value===generation;},shell(){panel?.dispose();current={nav:node("nav"),main:node("main")};return current;},openDossier:async()=>{},showJson(value){return node("pre",JSON.stringify(value));},button(label,action){const element=node("button",label);element.action=action;return element;},confirmation(parent,text){const label=node("label"),input=node("input");input.type="checkbox";input.setAttribute("aria-label",text);label.append(input,node("span",text));parent.append(label);return input;},async call(name,args){
    calls.push({name,args:structuredClone(args)});
    if(name.endsWith("author_setup"))return structuredClone(page);
    if(name.endsWith("decision_draft_read"))return structuredClone(draft);
    if(name.endsWith("decision_draft_save")){draft.fields=structuredClone(args.fields);draft.draft_revision="decision-"+(++serial);return {draft_revision:draft.draft_revision};}
    if(name.endsWith("author_draft_save")){page.fields=structuredClone(args.fields);page.draft_revision="task-"+(++serial);return {draft_revision:page.draft_revision};}
    if(name.endsWith("author_request")){if(!args.confirmed||!args.fresh_session_confirmed)throw new Error("Missing consent");page.grants.push({grant_ref:"mandate-"+"a".repeat(64),task:args.fields.task,status:"open",stages:[]});return {grant_ref:page.grants[0].grant_ref};}
    if(name.endsWith("author_read"))return {proposal:{summary_it:"Whole fictional proposal"},normalized_output:{recommendations:[]},metadata:{provider:"fixture-only",model:"fixture-only",prompt_template_version:"bandi-intelligence-v2"}};
    if(name.endsWith("author_record")){page.grants[0].status="recorded";page.grants[0].intelligence_run_id="INTEL-000001";page.public_suggestions=[{intelligence_run_id:"INTEL-000001",status:"MODEL_SUGGESTED"}];return {};}
    if(name.endsWith("author_decide")){page.grants[0].status="decided";return {};}
    if(name.endsWith("author_cancel")){page.grants[0].status="cancelled";return {};}
    throw new Error("Unexpected fixture tool "+name);
  }};
  const sandbox={globalThis:{},structuredClone,crypto:require("node:crypto").webcrypto,setTimeout:()=>1,clearTimeout(){},Object,JSON};
  vm.runInNewContext(fs.readFileSync(source,"utf8"),sandbox,{filename:source});panel=sandbox.globalThis.VeraBandiContributions.create(api);
  return {panel,page,draft,calls,get dirty(){return dirty;},all:()=>collect(current.main),field:label=>find(element=>element.attributes["aria-label"]===label),button:label=>find(element=>element.tagName==="BUTTON"&&element.text===label),text:()=>collect(current.main).map(element=>element.text).join(" ")};
}
module.exports={fixture};
