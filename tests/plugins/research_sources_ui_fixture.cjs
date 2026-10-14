"use strict";
// Fictional host transport with the actual store, not publisher or installed-host evidence.
const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
function fixture(root,options={}) {
  class Element {constructor(tag,text,cls){this.tagName=tag.toUpperCase();this.textContent=text||"";this.className=cls||"";this.children=[];}append(...items){this.children.push(...items);}replaceChildren(...items){this.children=items;}}
  const main=new Element("main"),calls=[],messages=[];let status="";
  const server=require(path.join(root,"mcp/research-sources.cjs"));
  const api={language:options.language,node:(tag,text,cls)=>new Element(tag,text,cls),main:()=>main,say:text=>{status=text;},button(text,action,cls){const e=new Element("button",text,cls);e.action=action;return e;},async call(name,args){calls.push({name,args});const r=server.call(name,args);if(r.isError)throw new Error(r.content[0].text);return r._meta.researchSources;},async sendToChat(text){messages.push(text);if(options.failMessage)throw new Error("Fictional message failure");return options.message!==false;}};
  const sandbox={globalThis:{}};vm.runInNewContext(fs.readFileSync(path.join(root,"ui/research-sources.js"),"utf8"),sandbox);const panel=sandbox.globalThis.VeraResearchSources.create(api);
  const elements=()=>{const collect=e=>[e,...e.children.flatMap(collect)];return collect(main);};
  return {panel,calls,messages,server,elements,text:()=>elements().map(e=>e.textContent).join(" "),button:(text,index=0)=>elements().filter(e=>e.tagName==="BUTTON"&&e.textContent===text)[index],status:()=>status};
}
module.exports={fixture};
