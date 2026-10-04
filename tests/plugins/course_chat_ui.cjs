"use strict";
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
async function exercise(action, supported, cancelled) {
  const nodes = new Map();
  const node = id => { if (!nodes.has(id)) nodes.set(id, { addEventListener(type, fn) { this[type] = fn; } }); return nodes.get(id); };
  let listener; const sent=[]; const parent={postMessage(message) {
    if (message.method === "ui/initialize") queueMicrotask(() => listener({source:parent,data:{jsonrpc:"2.0",id:message.id,result:{hostCapabilities:{experimental:supported ? {"openai/message":{}}:{}}}}}));
    if (message.method === "ui/message") { sent.push(message.params); queueMicrotask(() => listener({source:parent,data:{jsonrpc:"2.0",id:message.id,result:{isError:cancelled}}})); }
  }};
  const context = {document:{getElementById:node,documentElement:{}},window:{parent,addEventListener(type,fn){listener=fn;}},setTimeout(){return 1;},clearTimeout(){},queueMicrotask};
  vm.runInNewContext(fs.readFileSync(process.argv[2],"utf8"),context);
  await new Promise(resolve=>setImmediate(resolve));
  listener({source:parent,data:{jsonrpc:"2.0",method:"ui/notifications/tool-result",params:{_meta:{course_chat:{product:"vera",language:"fr",title:"Cours",workflow_id:"fatture-xml-check",state_root:"/course",invitation:"opaque",teacher_thread_id:"teacher",worker_thread_id:"worker",action}}}}});
  assert.equal(node("launch").disabled,!supported);
  // Unrelated tool notifications must not erase the mounted invitation.
  listener({source:parent,data:{jsonrpc:"2.0",method:"ui/notifications/tool-result",params:{structuredContent:{status:"ready"}}}});
  if (!supported) { await node("launch").click(); assert.equal(sent.length,0); return; }
  const first=node("launch").click(); const duplicate=node("launch").click();
  await Promise.all([first,duplicate]);
  assert.equal(sent.length,1);
  assert.equal(sent[0]._meta["openai/message"].target, action === "new" ? "new":"active");
  assert.equal(node("launch").disabled,!cancelled);
  if (cancelled) assert.equal(node("status").className,"error");
  else assert.ok(node("status").textContent.includes("Demande reçue"));
}
(async()=>{await exercise("new",true,false);await exercise("resume",true,false);await exercise("new",false,false);await exercise("new",true,true);process.stdout.write("Course UI confirmation, duplicate click, resume, locale and unsupported-host checks passed\n");})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});
