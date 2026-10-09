"use strict";
// Fictional DOM/transport for real panel event behavior; not native-host evidence.
const fs=require("node:fs"),vm=require("node:vm");
function fixture(source,overrides={}) {
  class Element {
    constructor(tag,text){this.tagName=tag.toUpperCase();this.text=text||"";this.children=[];this.attributes={};this.listeners={};this.value="";this.checked=false;this.disabled=false;}
    append(...items){for(const item of items){item.parentElement=this;this.children.push(item);}}
    replaceChildren(...items){this.children=[];this.append(...items);}
    setAttribute(key,value){this.attributes[key]=value;}
    addEventListener(key,action){this.listeners[key]=action;}
    dispatch(key){return this.listeners[key]?.();}
  }
  const node=(tag,text)=>new Element(tag,text),main=node("main"),collect=value=>[value,...value.children.flatMap(collect)];
  const items=overrides.items||[],operations=overrides.operations||[],meetings=overrides.meetings||[],history=[];
  const data={items,operations,meetings,history},drafts={};
  const calls=[],messages=[],chat=[];let dirty=false,remembered={},serial=0;
  function page(args){const collection=args.collection||"items",offset=args.offset||0,list=data[collection];const value={scope_revision:"fictional-scope",review_ticket:"fictional-ticket",collection,offset,items:structuredClone(list.slice(offset,offset+30)),total:list.length,next_offset:list.length>offset+30?offset+30:null,counts:Object.fromEntries(Object.entries(data).map(([key,rows])=>[key,rows.length])),settings:{revision:0,configured:false},day:null};if(args.form){value.form=args.form;value.draft=structuredClone(drafts[args.form]||{revision:0,fields:structuredClone(overrides.fields||{}),state:overrides.state||"draft",stale:Boolean(overrides.stale)});if(args.form.startsWith("record:"))value.record=structuredClone(items.find(item=>item.id===args.form.slice(7)));}return value;}
  const panelApi={node,main:()=>main,say:(text,error)=>messages.push({text,error}),setDirty:value=>{dirty=value;},remember:value=>{remembered=value;},sendToChat:async text=>{chat.push(text);return !overrides.no_chat;},button(text,action){const value=node("button",text);value.action=action;return value;},async call(name,args){calls.push({name,args:structuredClone(args)});const action=name.slice("vera_studio_work_panel_".length);if(action==="page")return page(args);if(action==="draft_save"){if(overrides.save_error)throw new Error("Fictional draft refusal");drafts[args.form]={revision:++serial,fields:structuredClone(args.fields),state:"draft",stale:false};return page(args);}if(action==="draft_clear"){drafts[args.form]={revision:++serial,fields:{},state:"draft",stale:false};return page(args);}if(action==="submit"){drafts[args.form].state=overrides.submit_error?"pending":"completed";drafts[args.form].stale=true;if(overrides.submit_error)throw new Error("Fictional lost local save response");drafts[args.form].result={item:{id:"fictional-saved",...drafts[args.form].fields}};return page(args);}if(action==="recover"){drafts[args.form].state="completed";drafts[args.form].result={item:{id:"fictional-recovered"}};return page(args);}throw new Error("Unexpected fictional panel action "+name);}};
  const sandbox={globalThis:{},structuredClone,setTimeout:()=>1,clearTimeout(){}};
  vm.runInNewContext(fs.readFileSync(source,"utf8"),sandbox,{filename:source});const panel=sandbox.globalThis.VeraStudioWork.create(panelApi);
  return {panel,calls,messages,chat,drafts,all:()=>collect(main),field:label=>collect(main).find(value=>value.attributes["aria-label"]===label),fields:label=>collect(main).filter(value=>value.attributes["aria-label"]===label),button:text=>collect(main).find(value=>value.tagName==="BUTTON"&&value.text===text),confirm:()=>collect(main).find(value=>value.tagName==="INPUT"&&value.type==="checkbox"&&value.parentElement.children.some(child=>child.text==="Ho riesaminato i campi e la fonte. Confermo questo salvataggio locale")),discard:()=>collect(main).find(value=>value.tagName==="INPUT"&&value.type==="checkbox"&&value.parentElement.children.some(child=>child.text==="Scarta soltanto i campi incompleti dopo il confronto con il registro corrente")),text:()=>collect(main).map(value=>value.text).join(" "),get dirty(){return dirty;},get remembered(){return remembered;}};
}
module.exports={fixture};
