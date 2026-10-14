"use strict";
const fs=require("node:fs"),path=require("node:path"),readline=require("node:readline");
const store=require("./research-subscriptions-store.cjs");
const URI="ui://vera/research-sources.html",MIME="text/html;profile=mcp-app",PREFIX="vera_research_sources_";
const id={enum:store.PROVIDERS.map(p=>p.id)},revision={type:"integer",minimum:0};
function tool(action,description,properties={},required=[],app=true,model=true) {
  return {name:PREFIX+action,title:description,inputSchema:{type:"object",additionalProperties:false,properties,required},
    annotations:{readOnlyHint:["open","state"].includes(action),destructiveHint:action==="configure",openWorldHint:false},
    _meta:{ui:{visibility:[...(app?["app"]:[]),...(model?["model"]:[])],...(action==="open"?{resourceUri:URI}:{})},...(action==="open"?{"openai/outputTemplate":URI}:{})}};
}
const TOOLS=[
  tool("open","Open optional research subscriptions; connecting is a user choice, not proof of live access"),
  tool("state","Read optional subscription choices before research; recheck live access each run"),
  tool("configure","Save the user's explicit authorisation or disconnect; never store passwords",{provider_id:id,revision,enabled:{type:"boolean"},user_authorized:{const:true}},["provider_id","revision","enabled","user_authorized"]),
  tool("request","Prepare an access check for the host agent; this tool does not open a browser",{provider_id:id,revision},["provider_id","revision"]),
  tool("record","Record the host's actual access observation; not independent authentication or a source-quality judgment",{provider_id:id,revision,request_id:{type:"string",maxLength:100},result:{enum:store.RESULTS},route:{enum:["browser","connector","none"]},tool_name:{type:["string","null"],maxLength:160},source_url:{type:"string",maxLength:2000},source_title:{type:"string",maxLength:500}},["provider_id","revision","request_id","result","route","tool_name"],false,true),
];
function call(name,args={}) {
  if(!TOOLS.some(t=>t.name===name))throw new Error("Unknown research-source tool");
  const value=store.dispatch(name.slice(PREFIX.length),args);
  const summary=name===PREFIX+"state"?value:{revision:value.revision,providers:value.providers.map(p=>({id:p.id,enabled:p.enabled,last_check:p.last_check?.result||null})),...(value.handoff?{handoff:value.handoff}:{})};
  return {content:[{type:"text",text:JSON.stringify(summary)}],structuredContent:summary,_meta:{researchSources:value}};
}
function resource() {
  const dir=path.resolve(__dirname,"../ui");
  const html=fs.readFileSync(path.join(dir,"research-sources.html"),"utf8")
    .replace("/*__CSS__*/",fs.readFileSync(path.join(dir,"workspace.css"),"utf8")+"\n"+fs.readFileSync(path.join(dir,"research-sources.css"),"utf8"))
    .replace("/*__SELECT_JS__*/",fs.readFileSync(path.join(dir,"custom_select.js"),"utf8"))
    .replace("/*__JS__*/",fs.readFileSync(path.join(dir,"research-sources.js"),"utf8"))
    .replaceAll("__FONT__",fs.readFileSync(path.join(dir,"InstrumentSans-Regular.ttf")).toString("base64"));
  return {contents:[{uri:URI,mimeType:MIME,text:html,_meta:{ui:{csp:{connectDomains:[],resourceDomains:[]}}}}]};
}
function handle(request) {
  if(request.method.startsWith("notifications/"))return null;
  if(request.method==="initialize")return {protocolVersion:"2024-11-05",capabilities:{tools:{},resources:{}},serverInfo:{name:"vera-research-sources",version:"1.0.0"}};
  if(request.method==="ping")return {};
  if(request.method==="tools/list")return {tools:TOOLS};
  if(request.method==="resources/list")return {resources:[{uri:URI,name:"Research sources",mimeType:MIME}]};
  if(request.method==="resources/read" && request.params?.uri===URI)return resource();
  if(request.method==="tools/call") {
    try{return call(request.params.name,request.params.arguments||{});}catch(error){return {isError:true,content:[{type:"text",text:error.message}]};}
  }
  throw new Error("Unsupported research-source method");
}
module.exports={TOOLS,call,resource,handle,main};
function main() {
  if(["--state","--action"].includes(process.argv[2])) {
    try{process.stdout.write(JSON.stringify(process.argv[2]==="--state"?store.dispatch("state"):store.dispatch(process.argv[3],JSON.parse(fs.readFileSync(0,"utf8"))))+"\n");}
    catch(error){process.stderr.write(error.message+"\n");process.exitCode=1;}
  }else readline.createInterface({input:process.stdin,crlfDelay:Infinity}).on("line",line=>{
    let request;
    try{request=JSON.parse(line);const result=handle(request);if(result!==null && request.id!==undefined)process.stdout.write(JSON.stringify({jsonrpc:"2.0",id:request.id,result})+"\n");}
    catch(error){if(request?.id!==undefined)process.stdout.write(JSON.stringify({jsonrpc:"2.0",id:request.id,error:{code:-32602,message:error.message}})+"\n");}
  });
}

if(require.main===module)main();
