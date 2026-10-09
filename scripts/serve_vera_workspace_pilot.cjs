#!/usr/bin/env node
"use strict";

// Development host only. It runs the actual stdio server with the builder's
// fictional archive. It does not simulate native-host or model acceptance.
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const readline = require("node:readline");
const { spawn } = require("node:child_process");
const { randomBytes } = require("node:crypto");
const { URI } = require("../plugins/bilancio-xbrl-it/mcp/native-workspace.cjs");
const directory = path.resolve(process.argv[2]);
const env = JSON.parse(fs.readFileSync(path.join(directory, "environment.json")));
if (env.VERA_XBRL_TENANT_ID !== "demo_studio" || env.VERA_XBRL_ACTOR_ID !== "demo_reviewer" || !env.VERA_XBRL_STORAGE_ROOT.startsWith(directory + path.sep)) throw new Error("Only the generated fictional pilot is supported");
const child = spawn(process.execPath, [path.resolve(__dirname, "../plugins/bilancio-xbrl-it/mcp/server.cjs")], { env: { ...process.env, ...env }, stdio: ["pipe", "pipe", "inherit"] });
let sequence = 0;
const pending = new Map();
readline.createInterface({ input: child.stdout }).on("line", line => { const message = JSON.parse(line); const resolve = pending.get(message.id); if (resolve) { pending.delete(message.id); resolve(message); } });
const rpc = (method, params) => new Promise(resolve => { const id = ++sequence; pending.set(id,resolve); child.stdin.write(JSON.stringify({jsonrpc:"2.0",id,method,params})+"\n"); });
const token = randomBytes(20).toString("hex");
const hostHtml = `<!doctype html><html lang="it"><meta charset="utf-8"><title>Vera · anteprima locale</title><style>body{margin:0;font:13px system-ui}header{padding:12px 20px;background:#fff5dc;color:#57441b}iframe{width:100%;height:calc(100vh - 58px);border:0}</style><header>Anteprima locale · dati fittizi. Apertura, fonti e salvataggio sono collegati al fascicolo di prova. La chat non è disponibile.</header><iframe id="app" title="Fascicoli Vera" src="./${token}/ui"></iframe><script>
const frame=document.getElementById('app');
async function rpc(method,params){return (await fetch('./${token}/rpc',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method,params})})).json()}
window.addEventListener('message',async event=>{if(event.source!==frame.contentWindow)return; const m=event.data;if(m.jsonrpc!=='2.0')return;let result;
if(m.method==='ui/initialize')result={protocolVersion:'2026-01-26',hostInfo:{name:'Vera protocol test host',version:'1'},hostCapabilities:{},hostContext:{}};
else if(m.method==='ui/notifications/initialized'){const initial=await rpc('tools/call',{name:'xbrl_workspace_open',arguments:{}});frame.contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:initial.result},location.origin);return;}
else if(m.method==='ui/message'||m.method==='ui/update-model-context'){frame.contentWindow.postMessage({jsonrpc:'2.0',id:m.id,error:{code:-32601,message:'La chat non è disponibile nell’anteprima locale. Nessun messaggio è stato inviato.'}},location.origin);return;}
else if(m.method==='tools/call'){const answer=await rpc(m.method,m.params);result=answer.result;if(answer.error){frame.contentWindow.postMessage({...answer,id:m.id},location.origin);return;}}
else return;
frame.contentWindow.postMessage({jsonrpc:'2.0',id:m.id,result},location.origin);
});</script></html>`;
const server = http.createServer(async (req,res) => {
  if (req.headers.host !== `127.0.0.1:${server.address().port}`) { res.writeHead(403).end(); return; }
  res.setHeader("Cache-Control","no-store");
  if (req.method === "GET" && req.url === `/${token}`) { res.setHeader("Content-Type","text/html; charset=utf-8"); res.end(hostHtml); return; }
  if (req.method === "GET" && req.url === `/${token}/ui`) { const data=await rpc("resources/read",{uri:URI});res.setHeader("Content-Type","text/html; charset=utf-8");res.end(data.result.contents[0].text);return; }
  if (req.method === "POST" && req.url === `/${token}/rpc` && req.headers.origin === `http://${req.headers.host}` && req.headers["content-type"] === "application/json") {
    let body="";for await (const chunk of req) {body+=chunk;if(body.length>64000){res.writeHead(413).end();return;}}
    try { const message=JSON.parse(body);if(message.method!=="tools/call" || !message.params?.name?.startsWith("xbrl_workspace_")) throw new Error("Unsupported test method");res.setHeader("Content-Type","application/json");res.end(JSON.stringify(await rpc(message.method,message.params))); }
    catch { res.writeHead(400).end(); } return;
  }
  res.writeHead(404).end();
});
server.listen(0,"127.0.0.1",()=>process.stdout.write(`http://127.0.0.1:${server.address().port}/${token}\n`));
process.on("SIGINT",()=>{child.kill();server.close();});
process.on("SIGTERM",()=>{child.kill();server.close();});
