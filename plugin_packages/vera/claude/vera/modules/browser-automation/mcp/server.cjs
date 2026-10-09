#!/usr/bin/env node
"use strict";
// The native panel is a projection over agenzia_acquire.py, never a second engine.
const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const {spawnSync} = require("node:child_process");
const {randomUUID} = require("node:crypto");
const ROOT = path.resolve(__dirname, "..");
const URI = "ui://vera/agenzia-acquisition-v1.html";
const MIME = "text/html;profile=mcp-app";
const bindings = new Map();
let interpreter;
const string = {type:"string",minLength:1,maxLength:4000};
const schema = (properties,required=[]) => ({type:"object",properties,required,additionalProperties:false});
const scope = {workspace_ref:string,run_id:{type:"string",pattern:"^[a-f0-9]{32}$"}};
function tool(name,title,description,inputSchema,write=false,appOnly=true) {
  return {name,title,description,inputSchema,annotations:{readOnlyHint:!write,destructiveHint:false,openWorldHint:/_(start|resume|continue)$/.test(name)},_meta:{ui:{visibility:appOnly?["app"]:["app","model"]}}};
}
const TOOLS = [
  {...tool("agenzia_workspace_open","Acquisizione Agenzia","Open Vera's local acquisition panel for an explicit client plan and output folder. The optional native UI uses the same Python worker and outputs as the ordinary skill; it does not authenticate, download or pay on open.",schema({plan_path:string,output_directory:string,run_id:scope.run_id}),true,false),
   _meta:{ui:{resourceUri:URI},"openai/outputTemplate":URI,"openai/ui":{entrypoints:[{type:"thread"}]}}},
  tool("agenzia_workspace_save","Conserva selezione","Persist an exact-revision draft using only clients from the opened source plan. Saving is separate from launch.",schema({workspace_ref:string,revision:string,plan:{type:"object"}},["workspace_ref","revision","plan"]),true),
  tool("agenzia_workspace_start","Avvia acquisizione","Launch the same local acquisition worker for this exact saved plan. The operator logs in in visible Chrome; credentials never pass through this tool.",schema({workspace_ref:string,revision:string,request_id:string},["workspace_ref","revision","request_id"]),true),
  tool("agenzia_workspace_status","Stato acquisizione","Read a selected saved run. Model-visible output contains status and counts; client rows, original paths and financial evidence stay in private app metadata.",schema({...scope,offset:{type:"integer",minimum:0},exceptions_only:{type:"boolean"}},["workspace_ref","run_id"]),false,false),
  ...["continue","cancel","resume","archive"].map(action=>tool(`agenzia_workspace_${action}`,{continue:"Ho completato l'accesso",cancel:"Interrompi acquisizione",resume:"Riprendi acquisizione",archive:"Importa in Studio Archive"}[action],{continue:"Continue this waiting run after the operator completed authentication in Chrome.",cancel:"Request cooperative cancellation; retained originals and results remain available.",resume:"Re-enumerate the same requested period in a new run, reusing only locally verified originals.",archive:"Import verified originals through the existing Studio Archive API and explicit client/engagement bindings; never infer client identity."}[action],schema(action==="resume"?{...scope,request_id:string}:scope,action==="resume"?["workspace_ref","run_id","request_id"]:["workspace_ref","run_id"]),true)),
  tool("agenzia_workspace_f24","Prepara prospetto F24","Generate a non-submittable PDF working draft from the exact acquired report and explicitly reviewed residual amounts, due dates and notes. Does not send or pay.",schema({...scope,revision:string,review:{type:"object"}},["workspace_ref","run_id","revision","review"]),true),
  tool("agenzia_workspace_download","Scarica riepilogo","Return one allowed existing report file to the private app for local download.",schema({...scope,name:{enum:["riepilogo.xlsx","fatture.csv","model_data_report.md"]}},["workspace_ref","run_id","name"])),
];
function python() {
  if(interpreter) return interpreter;
  if(process.env.VERA_AGENZIA_PYTHON) interpreter = process.env.VERA_AGENZIA_PYTHON;
  else {
    const bootstrap = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
    const result = spawnSync(bootstrap,[path.join(ROOT,"scripts/agenzia_runtime.py")],{encoding:"utf8",timeout:30000});
    if(result.status!==0) throw new Error("managed-runtime-setup-required");
    interpreter=result.stdout.trim();
  }
  const check=spawnSync(interpreter,[path.join(ROOT,"scripts/check_dependencies.py"),"--requirements","requirements-agenzia.txt"],{encoding:"utf8",timeout:30000});
  if(check.status!==0){interpreter=undefined;throw new Error("managed-runtime-dependencies-unavailable");}
  return interpreter;
}
function bridge(binding,action,args={}) {
  const result=spawnSync(python(),[path.join(ROOT,"scripts/agenzia_ui.py")],{
    input:JSON.stringify({...binding,action,args}),encoding:"utf8",timeout:150000,maxBuffer:25_000_000});
  if(result.error || !result.stdout) throw new Error("acquisition-service-unavailable");
  let value;try{value=JSON.parse(result.stdout);}catch{throw new Error("acquisition-service-response-invalid");}
  if(result.status!==0) throw new Error(value.error||"acquisition-service-failed");
  return value;
}
function validate(definition,args) {
  if(!args||typeof args!=="object"||Array.isArray(args))throw new Error("arguments-invalid");
  const spec=definition.inputSchema;
  if(Object.keys(args).some(key=>!Object.hasOwn(spec.properties,key)) || spec.required.some(key=>!Object.hasOwn(args,key)))throw new Error("arguments-invalid");
  for(const [key,value] of Object.entries(args)){
    const field=spec.properties[key];
    if(field.enum&&!field.enum.includes(value))throw new Error("argument-value-invalid");
    if(field.type==="string"&&(typeof value!=="string"||value.length<(field.minLength||0)||value.length>(field.maxLength||4000)||(field.pattern&&!new RegExp(field.pattern).test(value))))throw new Error("argument-value-invalid");
    if(field.type==="integer"&&(!Number.isSafeInteger(value)||value<(field.minimum||0)))throw new Error("argument-value-invalid");
    if(field.type==="boolean"&&typeof value!=="boolean")throw new Error("argument-value-invalid");
    if(field.type==="object"&&(!value||typeof value!=="object"||Array.isArray(value)))throw new Error("argument-value-invalid");
  }
}
function resultFor(data,ref) {
  const summary={state:data.state, ...(ref?{workspace_ref:ref}:{}), ...(data.run_id?{run_id:data.run_id}:{})};
  for(const key of ["downloaded","verified_existing","failed_documents","scopes_complete","scopes_expected","scopes_incomplete","scopes_not_attempted","cash_review_issue_count","error"])
    if(data[key]!==undefined)summary[key]=data[key];
  return {content:[{type:"text",text:JSON.stringify(summary)}],structuredContent:summary,_meta:{agenzia:{...data,workspace_ref:ref}}};
}
function callTool(name,args) {
  const definition=TOOLS.find(item=>item.name===name);
  if(!definition)throw new Error("tool-unavailable");
  validate(definition,args);
  if(name==="agenzia_workspace_open") {
    if(!args.plan_path&&!args.output_directory&&!args.run_id)return resultFor({state:"unbound",message:"Indica a Vera il file clienti, il periodo e la cartella di destinazione per preparare il piano."},null);
    if(!args.plan_path||!args.output_directory)throw new Error("plan-and-output-required");
    const binding={plan_path:args.plan_path,output_directory:args.output_directory};
    let data=bridge(binding,"open");
    binding.source_revision=data.source_revision;
    const ref=randomUUID();bindings.set(ref,binding);
    if(args.run_id)data=bridge(binding,"status",{run_id:args.run_id});
    return resultFor(data,ref);
  }
  const binding=bindings.get(args.workspace_ref);
  if(!binding)throw new Error("workspace-expired-reopen-exact-plan");
  const {workspace_ref,...values}=args;
  return resultFor(bridge(binding,name.slice("agenzia_workspace_".length),values),workspace_ref);
}
function resource() {
  return fs.readFileSync(path.join(ROOT,"ui/agenzia.html"),"utf8")
    .replace("/*__CSS__*/",fs.readFileSync(path.join(ROOT,"ui/agenzia.css"),"utf8"))
    .replace("/*__JS__*/",fs.readFileSync(path.join(ROOT,"ui/agenzia.js"),"utf8"))
    .replace("__FONT_REGULAR__",fs.readFileSync(path.join(ROOT,"ui/InstrumentSans-Regular.ttf")).toString("base64"))
    .replace("__FONT_BOLD__",fs.readFileSync(path.join(ROOT,"ui/InstrumentSans-SemiBold.ttf")).toString("base64"));
}
function handleRpc(message) {
  const id=message.id??null, params=message.params||{};
  const ok=result=>({jsonrpc:"2.0",id,result});
  if(message.method.startsWith("notifications/"))return null;
  if(message.method==="initialize")return ok({protocolVersion:params.protocolVersion||"2024-11-05",serverInfo:{name:"vera-agenzia-acquisition",version:"1.0.0"},capabilities:{tools:{},resources:{}},instructions:"Use agenzia-acquisition for Agenzia downloads. Prepare an explicit client plan with the ordinary skill, then open the native panel if available. Authentication stays in the operator's visible Chrome. UI is optional; never invent completion or payment approval."});
  if(message.method==="tools/list")return ok({tools:TOOLS});
  if(message.method==="resources/list")return ok({resources:[{uri:URI,name:"Acquisizione Agenzia",mimeType:MIME}]});
  if(message.method==="resources/templates/list")return ok({resourceTemplates:[]});
  if(message.method==="resources/read"&&params.uri===URI)return ok({contents:[{uri:URI,mimeType:MIME,text:resource(),_meta:{ui:{prefersBorder:false,csp:{connectDomains:[],resourceDomains:[]}}}}]});
  if(message.method==="tools/call"){
    try{return ok(callTool(params.name,params.arguments||{}));}
    catch(error){const code=/^[a-z0-9-]+$/.test(error.message)?error.message:"acquisition-operation-failed";return ok({isError:true,content:[{type:"text",text:code}]});}
  }
  return {jsonrpc:"2.0",id,error:{code:-32601,message:"method-not-found"}};
}
function main(){
  const input=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
  input.on("line",line=>{
    if(!line.trim())return;
    let response;try{response=handleRpc(JSON.parse(line));}catch{response={jsonrpc:"2.0",id:null,error:{code:-32700,message:"invalid-request"}};}
    if(response)process.stdout.write(JSON.stringify(response)+"\n");
  });
}
module.exports={handleRpc,callTool,TOOLS,URI,resource};
if(require.main===module)main();
