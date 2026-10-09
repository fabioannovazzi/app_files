"use strict";
// Explicit fictional transport and event DOM; no native-host or model acceptance.
const fs=require("node:fs"),vm=require("node:vm"),{webcrypto}=require("node:crypto");
function fixture(source,overrides={}){
 class Element{constructor(tag,text){this.tagName=tag.toUpperCase();this.text=text||"";this.children=[];this.attributes={};this.listeners={};this.checked=false;this.disabled=false;this.value="";}append(...items){this.children.push(...items);}setAttribute(k,v){this.attributes[k]=v;}addEventListener(k,v){this.listeners[k]=v;}dispatch(k){return this.listeners[k]?.();}}
 const fields={task:"",question:"",input_ids:[],record_refs:[]};
 const page={work_ref:"fictional-work",revision:"fictional-current-revision",source_ref:"fictional-exact-source",review_ticket:"fictional-ticket",fields,draft_revision:"initial",draft_stale:false,can_write:true,can_author:true,sources:[{input_id:"I1",name:"fictional.txt",byte_count:18}],records:{"ledger_E0001.json":"fictional-hash"},grants:[],...overrides};
 const stageRef="proposal-"+"a".repeat(64),grantRef="mandate-"+"b".repeat(64);
 const grant={grant_ref:grantRef,task:"propose",question:"Fictional exact question",status:"open"};
 const read={status:"open",task:"propose",question:grant.question,obsolete:false,stages:[],reads:[],...overrides.read};
 const calls=[];let panel,current,epoch=0,dirty=false,serial=0;
 const node=(tag,text)=>new Element(tag,text),collect=e=>[e,...e.children.flatMap(collect)];
 const api={node,say(){},setDirty(v){dirty=v;},leaveDraft(){if(dirty)throw new Error('Unsaved fictional question');},enter(){return ++epoch;},isCurrent(v){return v===epoch;},shell(){panel?.dispose();current={nav:node('nav'),main:node('main')};return current;},openWorks:async()=>{},openProducer:async(workRef,operation)=>{calls.push({name:'openProducer',args:{workRef,operation}});},button(text,action){const e=node('button',text);e.action=action;return e;},confirmation(parent,text){const e=node('input');e.type='checkbox';e.setAttribute('aria-label',text);parent.append(e,node('span',text));return e;},async call(name,args){calls.push({name,args:structuredClone(args)});
 if(name==='vera_workspace_patent_box_author_setup')return structuredClone(page);
 if(name==='vera_workspace_patent_box_author_draft_save'){page.fields=structuredClone(args.fields);page.draft_revision='draft-'+(++serial);return {draft_revision:page.draft_revision};}
 if(name==='vera_workspace_patent_box_author_draft_clear'){page.fields=structuredClone(fields);page.draft_stale=false;page.draft_revision='draft-'+(++serial);return {draft_revision:page.draft_revision};}
 if(name==='vera_workspace_patent_box_author_request'){page.grants.push(grant);return grant;}
 if(name==='vera_workspace_patent_box_author_read')return {...structuredClone(read),grant_ref:grantRef,stages:args.stage_ref?[{stage_ref:stageRef}]:read.stages,...(args.stage_ref?{body:{case:{demo:true},controls:[{status:'NOT_TESTED',conclusion:'Fictional located gap'}]},preview:{public_outputs_written:false},metadata:{model:'NO_MODEL_EXECUTED'},reads:[{kind:'context',provider_telemetry:'not_measurable'}]}:{})};
 if(name==='vera_workspace_patent_box_setup')return {fields:{proposal:{case:{demo:true}}},draft_revision:'exact-producer-draft'};
 if(name==='vera_workspace_patent_box_author_adopt')return {status:'adopted',task:'propose',public_outputs_written:false};
 if(name==='vera_workspace_patent_box_author_cancel'){page.grants[0].status='cancelled';return {status:'cancelled'};}
 throw new Error('Unexpected fictional tool '+name);
 }};
 const sandbox={globalThis:{},structuredClone,crypto:webcrypto,setTimeout:()=>1,clearTimeout(){},Object,JSON,Number,Boolean,String,Array};
 vm.runInNewContext(fs.readFileSync(source,'utf8'),sandbox,{filename:source});panel=sandbox.globalThis.VeraPatentBoxAuthoring.create(api);
 return {panel,page,calls,grantRef,stageRef,all:()=>collect(current.main),text:()=>collect(current.main).map(x=>x.text).join(' '),field:label=>collect(current.main).find(x=>x.attributes['aria-label']===label),button:label=>collect(current.main).find(x=>x.tagName==='BUTTON'&&x.text===label),get dirty(){return dirty;}};
}
module.exports={fixture};
