'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
async function exercise(supported){
 const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,{addEventListener(type,fn){this[type]=fn;}});return nodes.get(id);};
 let listener;const calls=[],messages=[],state={session:'a'.repeat(32),operation:'transcribe',language:'it',status:'ready',filename:'synthetic.wav'};
 const parent={postMessage(m){if(m.method==='ui/initialize')reply(m,{hostCapabilities:{experimental:supported?{'openai/message':{}}:{}},hostContext:{permissions:{}}});if(m.method==='tools/call'){calls.push(m.params);reply(m,{_meta:{media:{...state,status:'confirmed'}}});}if(m.method==='ui/message'){messages.push(m.params);reply(m,{});}}};
 function reply(m,result){queueMicrotask(()=>listener({source:parent,data:{jsonrpc:'2.0',id:m.id,result}}));}
 const context={document:{getElementById:node,documentElement:{}},parent,window:{},navigator:{},addEventListener(type,fn){listener=fn;},setTimeout(){return 1;},clearTimeout(){},queueMicrotask};
 const html=fs.readFileSync('plugins/clara/ui/media.html','utf8');vm.runInNewContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],context);
 await new Promise(r=>setImmediate(r));listener({source:parent,data:{jsonrpc:'2.0',method:'ui/notifications/tool-result',params:{_meta:{media:state}}}});
 assert.equal(node('record').hidden,true,'Never offer microphone without host permission');
 assert.equal(node('continue').disabled,!supported);
 const first=node('continue').click(),second=node('continue').click();await Promise.all([first,second]);
 assert.equal(messages.length,supported?1:0,'One native continuation per selection');
 assert.equal(calls.length,supported?1:0,'Confirm once and do not process media in the panel');
 if(supported){assert.equal(calls[0].name,'clara_media_confirm');assert.equal(messages[0]._meta['openai/message'].target,'active');assert.equal(node('continue').disabled,true);}
}
(async()=>{await exercise(true);await exercise(false);process.stdout.write('Media UI capability and duplicate-handoff checks passed\n');})().catch(e=>{process.stderr.write(e.stack+'\n');process.exitCode=1;});
