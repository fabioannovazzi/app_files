"use strict";

// Fixed schemas, owner-local storage and CAS protect consent/integrity. The host
// model judges source relevance and what the observed page actually establishes.
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {randomUUID} = require("node:crypto");
const PROVIDERS = [
  {id:"eutekne", name:"Eutekne", url:"https://www.eutekne.it/", domains:["eutekne.it", "eutekne.info"]},
  {id:"one-fiscale", name:"One FISCALE", url:"https://onefiscale.wolterskluwer.it/", domains:["wolterskluwer.it", "wolterskluwer.com"]},
];
const RESULTS = ["document_read", "login_required", "unavailable"];
const directory = () => path.resolve(process.env.MPARANZA_RESEARCH_HOME || path.join(os.homedir(), ".mparanza", "research-subscriptions"));
function ownerPath(location) {
  if(location === path.parse(location).root || location === os.homedir()) throw new Error("Use a dedicated private research directory");
  for(let part=location;;part=path.dirname(part)) {
    let stat;
    try {stat=fs.lstatSync(part);}catch(error){if(error.code!=="ENOENT")throw error;}
    if(stat) {
      if(stat.isSymbolicLink() || !stat.isDirectory())throw new Error("Research storage must use real directories");
    }
    if(path.dirname(part)===part)break;
  }
}
function empty() {
  return {schema_version:1, revision:0, providers:Object.fromEntries(PROVIDERS.map(p=>[p.id,{enabled:false, authorized_at:null, pending:null, last_check:null}]))};
}
function read() {
  const dir=directory();ownerPath(dir);const file=path.join(dir,"subscriptions.json");
  let stat;
  try {stat=fs.lstatSync(file);}catch(e){if(e.code==="ENOENT")return empty();throw e;}
  if(stat.isSymbolicLink()||!stat.isFile()||stat.nlink!==1||stat.size>64000 || (process.getuid && (stat.uid!==process.getuid() || (stat.mode&0o077))))throw new Error("Invalid private subscription register");
  let value;
  try{value=JSON.parse(fs.readFileSync(file,"utf8"));}catch(error){if(error instanceof SyntaxError)throw new Error("Subscription register contains invalid JSON; preserve it for recovery");throw error;}
  if(!value || Object.keys(value).sort().join()!=="providers,revision,schema_version" || value.schema_version!==1 || !Number.isSafeInteger(value.revision) || value.revision<0 || !value.providers || Object.keys(value.providers).sort().join()!==PROVIDERS.map(p=>p.id).sort().join())throw new Error("Invalid subscription register; preserve it for recovery");
  for(const row of Object.values(value.providers)) {
    if(typeof row.enabled!=="boolean" || Object.keys(row).sort().join()!=="authorized_at,enabled,last_check,pending")throw new Error("Invalid subscription entry");
    if((row.enabled && (typeof row.authorized_at!=="string" || !Number.isFinite(Date.parse(row.authorized_at)))) || (!row.enabled && (row.authorized_at!==null || row.pending!==null || row.last_check!==null)))throw new Error("Invalid saved subscription authorisation");
    if(row.pending && (Object.keys(row.pending).sort().join()!=="request_id,requested_at" || !/^[a-f0-9-]{36}$/.test(row.pending.request_id) || !Number.isFinite(Date.parse(row.pending.requested_at))))throw new Error("Invalid saved access request");
    if(row.last_check && (!RESULTS.includes(row.last_check.result) || !["browser","connector","none"].includes(row.last_check.route) || row.last_check.basis!=="host_observation_reported" || typeof row.last_check.observed_at!=="string"))throw new Error("Invalid saved access observation");
    if(row.last_check) {
      const check=row.last_check,keys=["result","route","tool_name","observed_at","basis",...(check.result==="document_read"?["source_url","source_title"]:[])];
      if(Object.keys(check).sort().join()!==keys.sort().join() || !Number.isFinite(Date.parse(check.observed_at)))throw new Error("Invalid saved access metadata");
      if(check.route==="none"){if(check.result!=="unavailable" || check.tool_name!==null)throw new Error("Invalid missing-tool observation");}
      else text(check.tool_name,160);
      if(check.result==="document_read"){text(check.source_title,500);if(sourceURL(check.source_url)!==check.source_url)throw new Error("Invalid retained document URL");}
    }
  }
  return value;
}
function view(value=read()) {
  return {schema_version:1, revision:value.revision, providers:PROVIDERS.map(p=>({...p,...value.providers[p.id]})),
    access_basis:"host_observation_reported; recheck during each research run",
    research_method:"shared_agentic_legal_tax_research", optional:true};
}
function mutate(expected, change) {
  const dir=directory();ownerPath(dir);fs.mkdirSync(dir,{recursive:true,mode:0o700});
  if(process.getuid){if(fs.statSync(dir).uid!==process.getuid())throw new Error("Research storage belongs to another OS profile");fs.chmodSync(dir,0o700);}
  const lock=path.join(dir,"write.lock");
  try{fs.mkdirSync(lock,{mode:0o700});}catch(e){if(e.code==="EEXIST")throw new Error("Subscription register is busy; refresh before retrying. An interrupted write may require recovery.");throw e;}
  let temporary;
  try {
    const value=read();
    if(value.revision!==expected)throw new Error("Subscription choices changed; refresh before retrying");
    change(value);value.revision++;
    temporary=path.join(dir,".subscriptions-"+randomUUID()+".json");
    fs.writeFileSync(temporary,JSON.stringify(value,null,2)+"\n",{flag:"wx",mode:0o600});
    fs.renameSync(temporary,path.join(dir,"subscriptions.json"));temporary=null;
    return view(value);
  }finally{
    try{if(temporary)fs.rmSync(temporary,{force:true});}
    finally{fs.rmdirSync(lock);}
  }
}
function provider(id) {
  const value=PROVIDERS.find(p=>p.id===id);if(!value)throw new Error("Unknown research provider");return value;
}
function fields(args, required, optional=[]) {
  if(!args || typeof args!=="object" || Array.isArray(args) || required.some(k=>!(k in args)) || Object.keys(args).some(k=>![...required,...optional].includes(k)))throw new Error("Invalid subscription arguments");
  if("revision" in args && (!Number.isSafeInteger(args.revision)||args.revision<0))throw new Error("Invalid subscription revision");
  if("provider_id" in args)provider(args.provider_id);
}
function sourceURL(raw) {
  const url=new URL(raw);
  // Normalise URL shape only; publisher identity and relevance remain model-led.
  if(url.protocol!=="https:" || url.username || url.password)throw new Error("Use an observed HTTPS document URL without credentials");
  // Query strings/fragments can contain session identifiers; never retain them.
  url.search="";url.hash="";return url.href;
}
function text(value, limit=500) {
  if(typeof value!=="string" || !value.trim() || value.length>limit)throw new Error("Use bounded observed evidence");return value;
}
function dispatch(action,args={}) {
  if(action==="state" || action==="open"){fields(args,[]);return view();}
  if(action==="configure") {
    fields(args,["provider_id","revision","enabled","user_authorized"]);
    if(typeof args.enabled!=="boolean" || args.user_authorized!==true)throw new Error("Use the user's explicit connection choice");
    return mutate(args.revision,value=>{
      const row=value.providers[args.provider_id];row.enabled=args.enabled;row.authorized_at=args.enabled?new Date().toISOString():null;
      row.pending=null;row.last_check=null;
    });
  }
  if(action==="request") {
    fields(args,["provider_id","revision"]);const p=provider(args.provider_id);
    const result=mutate(args.revision,value=>{
      const row=value.providers[p.id];if(!row.enabled)throw new Error("This subscription has not been authorised");
      row.pending={request_id:randomUUID(),requested_at:new Date().toISOString()};
    });
    const row=result.providers.find(v=>v.id===p.id);
    result.handoff={provider_id:p.id,request_id:row.pending.request_id,
      prompt:`Verify my authorised ${p.name} subscription access for Vera. Read Vera's research-subscriptions skill and its reference. Request ${row.pending.request_id}. Use callable connected tools or my signed-in browser, with login performed by me when needed. Open a subscriber document before reporting document_read. Record the actual observation with vera_research_sources_record; a saved preference or homepage is not verified access. Continue the current research in the same loop when there is an assignment. Do not purchase anything or retain credentials.`};
    return result;
  }
  if(action==="record") {
    fields(args,["provider_id","revision","request_id","result","route","tool_name"],["source_url","source_title"]);
    if(!RESULTS.includes(args.result)||!["browser","connector","none"].includes(args.route))throw new Error("Invalid access observation");
    text(args.request_id,100);
    if(args.route==="none") {if(args.result!=="unavailable" || args.tool_name!==null)throw new Error("Missing tools cannot establish attempted or successful access");}
    else text(args.tool_name,160);
    const p=provider(args.provider_id);
    const evidence=args.result==="document_read"?{source_url:sourceURL(text(args.source_url,2000)),source_title:text(args.source_title,500)}:{};
    return mutate(args.revision,value=>{
      const row=value.providers[p.id];
      if(!row.enabled || row.pending?.request_id!==args.request_id)throw new Error("Subscription request changed or was disconnected; inspect current state");
      row.last_check={result:args.result,route:args.route,tool_name:args.tool_name,observed_at:new Date().toISOString(),basis:"host_observation_reported",...evidence};
      row.pending=null;
    });
  }
  throw new Error("Unknown subscription action");
}
module.exports={dispatch,view,read,PROVIDERS,RESULTS};
