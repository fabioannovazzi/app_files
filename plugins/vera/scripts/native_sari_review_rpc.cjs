"use strict";

// One fixed public service/process retains the actual opaque review context.
const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const { spawn } = require("node:child_process");

async function main() {
  const request = JSON.parse(fs.readFileSync(0, "utf8"));
  const root = path.resolve(request.root);
  if (path.basename(root) !== "registro-imprese-sari" || !["read", "preflight", "save", "apply"].includes(request.operation)) throw new Error("Unsupported registry review action");
  const child = spawn(process.execPath, [path.join(root, "mcp/server.cjs"), "--stdio"], {cwd:root,env:process.env,stdio:["pipe","pipe","pipe"]});
  const pending = new Map();let sequence=0;
  const fail=error=>{for(const item of pending.values())item.reject(error);pending.clear();};
  child.on("error",fail);child.on("exit",()=>fail(new Error("Registry public review stopped")));child.stderr.resume();
  const timer=setTimeout(()=>{fail(new Error("Registry public review timed out"));child.kill();},60000);
  readline.createInterface({input:child.stdout}).on("line",line=>{
    try {
      if(Buffer.byteLength(line)>2_000_000)throw new Error("Complete registry response exceeds the limit");
      const message=JSON.parse(line),item=pending.get(message.id);if(!item)return;pending.delete(message.id);
      const value=message.result?.structuredContent;
      if(message.error||message.result?.isError||!value||value.ok===false)item.reject(new Error(message.error?.message||value?.error||message.result?.content?.[0]?.text||"Registry public review refused"));
      else item.resolve(value);
    }catch(error){fail(error);child.kill();}
  });
  const call=(name,args)=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});child.stdin.write(JSON.stringify({jsonrpc:"2.0",id,method:"tools/call",params:{name,arguments:args}})+"\n");});
  try {
    const validation=await call("validate_registro_imprese_sari_review",request.arguments);
    const token=validation.review_reference?.persistence_token;
    const rendered=await call("render_registro_imprese_sari_review",token?{persistence_token:token}:request.arguments);
    let result;
    if(request.operation==="read"){
      delete rendered.persistence_token;
      result=rendered;
    }else if(request.operation==="preflight"){
      // Shape/privacy checking uses the maintained save producer without output authority.
      result=await call("save_registro_imprese_sari_decisions",{review_payload:request.arguments.review_payload,final_artifacts:request.arguments.final_artifacts,...request.choices});
      if(result.persisted!==false)throw new Error("Registry mechanical preflight acquired write authority");
    }else{
      if(!token)throw new Error("Actual registry persistence authority required");
      result=await call(request.operation==="save"?"save_registro_imprese_sari_decisions":"apply_registro_imprese_sari_decisions",{persistence_token:token,...request.choices});
      if(result.persisted!==true)throw new Error("Registry public decision did not persist");
    }
    process.stdout.write(JSON.stringify(result));
  }finally{clearTimeout(timer);child.kill();}
}
main().catch(error=>{process.stderr.write(error.message+"\n");process.exitCode=1;});
