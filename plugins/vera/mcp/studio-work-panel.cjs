"use strict";

// App payloads stay in _meta. Exact revisions and canonical signed tickets are
// mechanical owner/runtime safeguards, never semantic scheduling decisions.
const fs = require("node:fs");
const path = require("node:path");
const {spawnSync} = require("node:child_process");
const {createHmac,randomBytes,timingSafeEqual} = require("node:crypto");
const ROOT = path.resolve(__dirname,"..");
const URI = "ui://vera/studio-work-v1.html";
const MIME = "text/html;profile=mcp-app";
const PREFIX = "vera_studio_work_panel_";
const secret = randomBytes(32);
const string = {type:"string",minLength:1,maxLength:20000};
const revision = {type:"integer",minimum:0};
const identity = {form:string,scope_revision:string,expected_draft_revision:revision,review_ticket:string};
function definition(action,description,properties,required,model=false) {
  return {name:PREFIX+action,description,inputSchema:{type:"object",additionalProperties:false,properties,required},
    _meta:{ui:{visibility:model?["app","model"]:["app"],...(action==="open"?{resourceUri:URI}:{})}}};
}
const TOOLS = [
  definition("open","Open the optional owner-local studio work panel. Register content stays in app metadata; calendar execution remains in the connected host workflow.",{},[],true),
  definition("page","Read a stable page or exact incomplete form in the owner-local register.",{collection:{enum:["items","operations","meetings","history"]},offset:revision,form:string,day:string,expected_scope:string},[]),
  definition("draft_save","Retain literal incomplete fields, without creating a commitment or restoring confirmation.",{...identity,fields:{type:"object"}},[...Object.keys(identity),"fields"]),
  definition("draft_clear","Discard only the exact private draft; retain all authoritative commitments, meetings and calendar receipts.",identity,Object.keys(identity)),
  definition("submit","Apply a newly confirmed local capture/change/meeting using the existing public register. Never dispatch a calendar tool.",{...identity,human_confirmed:{type:"boolean"}},[...Object.keys(identity),"human_confirmed"]),
  definition("recover","Recover the exact retained local save through its existing idempotency receipt. No calendar dispatch.",identity,Object.keys(identity)),
  definition("context","Read only the user-selected commitment, meeting or operation at the exact panel revision for discussion. This does not authorize calendar writes.",{scope_revision:string,collection:{enum:["items","operations","meetings"]},item_id:string},["scope_revision","collection","item_id"],true),
];
function validate(tool,args) {
  if (!args || typeof args!=="object" || Array.isArray(args)) throw new Error("Arguments must be an object");
  for(const field of tool.inputSchema.required) if(!(field in args))throw new Error("Missing "+field);
  for(const [field,value] of Object.entries(args)) {
    const rule=tool.inputSchema.properties[field];
    if(!rule)throw new Error("Unknown "+field);
    if(rule.type==="string"&&(typeof value!=="string"||!value.trim()||value.length>20000))throw new Error("Invalid "+field);
    if(rule.type==="integer"&&(!Number.isInteger(value)||value<0))throw new Error("Invalid "+field);
    if(rule.type==="boolean"&&typeof value!=="boolean")throw new Error("Invalid "+field);
    if(rule.type==="object"&&(!value||typeof value!=="object"||Array.isArray(value)))throw new Error("Invalid "+field);
    if(rule.enum&&!rule.enum.includes(value))throw new Error("Invalid "+field);
  }
}
function sign(page) {
  const body=Buffer.from(JSON.stringify({scope:page.scope_revision,form:page.form||null,expires:Date.now()+900000})).toString("base64url");
  return body+"."+createHmac("sha256",secret).update(body).digest("hex");
}
function verify(args) {
  const parts=args.review_ticket.split(".");
  if(parts.length!==2||!/^[A-Za-z0-9_-]+$/.test(parts[0])||!/^[a-f0-9]{64}$/.test(parts[1]))throw new Error("Invalid panel ticket; reread the form");
  const bytes=Buffer.from(parts[0],"base64url");
  if(bytes.toString("base64url")!==parts[0]||!timingSafeEqual(Buffer.from(parts[1],"hex"),createHmac("sha256",secret).update(parts[0]).digest()))throw new Error("Invalid panel ticket; reread the form");
  const claims=JSON.parse(bytes.toString("utf8"));
  if(claims.scope!==args.scope_revision||claims.form!==args.form||claims.expires<Date.now())throw new Error("Expired or mismatched panel ticket; reread the form");
}
function bridge(action,args) {
  let python=process.env.VERA_STUDIO_WORK_PYTHON;
  if(!python) {
    const resolved=spawnSync(process.platform==="win32"?"python":"python3",[path.join(ROOT,"scripts/studio_work_runtime.py")],{encoding:"utf8",timeout:30000});
    if(resolved.error)throw resolved.error;
    if(resolved.status!==0)throw new Error("Complete Vera's managed Python setup before using studio work");
    python=resolved.stdout.trim();
  }
  const result=spawnSync(python,[path.join(ROOT,"scripts/native_studio_work.py")],{input:JSON.stringify({action,arguments:args}),encoding:"utf8",timeout:30000,maxBuffer:8*1024*1024});
  if(result.error)throw result.error;
  if(result.status!==0)throw new Error(result.stderr.trim().split("\n").at(-1)||"Native studio work refused");
  return JSON.parse(result.stdout);
}
function call(name,args) {
  const tool=TOOLS.find(value=>value.name===name);
  if(!tool)throw new Error("Unknown native studio work tool");
  validate(tool,args);
  const action=name.slice(PREFIX.length);
  if(["draft_save","draft_clear","submit","recover"].includes(action))verify(args);
  const {review_ticket,...payload}=args;
  const value=bridge(action==="open"?"page":action,payload);
  if(action==="context")return {content:[{type:"text",text:JSON.stringify(value)}],structuredContent:value};
  value.review_ticket=sign(value);
  const summary={status:value.draft?.state||"ready",collection:value.collection,page_count:value.items.length,total:value.total};
  return {content:[{type:"text",text:JSON.stringify(summary)}],structuredContent:summary,_meta:{studioWork:value}};
}
function resource() {
  const dir=path.join(ROOT,"ui");
  const html=fs.readFileSync(path.join(dir,"studio-work.html"),"utf8")
    .replace("/*__CSS__*/",fs.readFileSync(path.join(dir,"workspace.css"),"utf8")+"\n"+fs.readFileSync(path.join(dir,"studio-work.css"),"utf8"))
    .replace("/*__SELECT_JS__*/",fs.readFileSync(path.join(dir,"custom_select.js"),"utf8"))
    .replace("/*__JS__*/",fs.readFileSync(path.join(dir,"studio-work.js"),"utf8"))
    .replace("__FONT__",fs.readFileSync(path.join(dir,"InstrumentSans-Regular.ttf")).toString("base64"));
  return {contents:[{uri:URI,mimeType:MIME,text:html,_meta:{ui:{prefersBorder:false,csp:{connectDomains:[],resourceDomains:[]}},"openai/ui":{preferredDisplayMode:"fullscreen",availableDisplayModes:["fullscreen"]}}}]};
}
module.exports={TOOLS,URI,MIME,PREFIX,call,resource};
