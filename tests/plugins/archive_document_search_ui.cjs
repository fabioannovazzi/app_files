"use strict";
// Behavioral DOM/transport regression, not installed-host acceptance.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(tag,text=''){this.tagName=tag;this.textContent=text;this.children=[];this.listeners={};this.style={};this.isConnected=true;}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;}
  setAttribute(){}
  addEventListener(name,callback){this.listeners[name]=callback;}
  focus(){this.focused=true;}
}
const node=(tag,text)=>new Element(tag,text),walk=e=>[e,...e.children.flatMap(walk)];
const calls=[], timers=new Map();let seq=0,resolveOld;
const hit={title:'Cumulo Transizione 5.0 e contributo ISMEA.pdf',client_label:'Eutekne',source_id:'src_example',locator_kind:'page',locator_value:'1',snippet:'Il [[credito]] Transizione 5.0'};
const context={node,document:{createTextNode:text=>node('#text',text)},catalogue:{client_id:'client_eutekne',client_label:'Eutekne'},button:(text,action)=>{const b=node('button',text);b.listeners.click=action;return b;},setTimeout:fn=>{timers.set(++seq,fn);return seq;},clearTimeout:id=>timers.delete(id),call:async(name,args)=>{calls.push({name,args});if(args.query==='old')return new Promise(resolve=>resolveOld=resolve);if(args.query==='failure')throw Error('Source unavailable');return name.endsWith('_source')?{source_verified:true,fragments:[{locator_kind:'page',locator_value:'1',text:'Il credito è discusso con ISMEA.'}],limitations:[]}:{results:args.query==='empty'?[]:[hit]};}};
const source=fs.readFileSync(process.argv[2],'utf8');
vm.runInNewContext(source,context);
context.mount=context.StudioArchiveUI({...context,getCatalogue:()=>context.catalogue}).archiveDocumentSearch;
const parent=node('main'),listing=node('div');context.mount(parent,listing);
const input=walk(parent).find(e=>e.tagName==='input');
async function type(value){input.value=value;input.listeners.input();for(const [id,fn]of [...timers]){timers.delete(id);fn();}await new Promise(resolve=>setImmediate(resolve));}
const text=()=>walk(parent).map(e=>e.textContent).join(' ');
(async()=>{
 await type('credito');assert(listing.hidden);assert(text().includes(hit.title));assert.equal(calls[0].args.client_id,'client_eutekne');assert(!calls[0].args.all_clients);
 await walk(parent).find(e=>e.tagName==='button').listeners.click();assert(text().includes('Documento verificato'));assert(text().includes('ISMEA.'));assert(walk(parent).some(e=>e.tagName==='mark'&&e.textContent==='credito'));
 await type('old');await type('empty');resolveOld({results:[hit]});await new Promise(resolve=>setImmediate(resolve));assert(text().includes('Nessun documento trovato'));assert(!text().includes(hit.title));
 await type('failure');assert(text().includes('Ricerca non disponibile'));
 await type('');assert.equal(listing.hidden,false);assert(!text().includes(hit.title));
 context.catalogue={};const global=node('main');context.mount(global,node('div'));const field=walk(global).find(e=>e.tagName==='input');field.value='credito';field.listeners.input();for(const fn of timers.values())fn();await new Promise(resolve=>setImmediate(resolve));assert.equal(calls.at(-1).args.all_clients,true);
 assert(calls.every(c=>!c.name.includes('refresh')));process.stdout.write('Archive search UI behavior passed\n');
})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});
