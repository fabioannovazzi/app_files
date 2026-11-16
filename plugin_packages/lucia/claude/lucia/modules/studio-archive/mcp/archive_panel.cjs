"use strict";
const fs=require("node:fs"), path=require("node:path"), os=require("node:os");
const {createHash}=require("node:crypto"), {spawnSync}=require("node:child_process");

module.exports=function createArchivePanel({product,pluginRoot,componentRoot,icon}) {
  const label=product[0].toUpperCase()+product.slice(1), assets=path.join(componentRoot,"assets");
  const files=["archive.html","archive.css","archive-ui.js","archive-host.js"];
  const revision=createHash("sha256");for(const file of files)revision.update(fs.readFileSync(path.join(assets,file)));
  const uri=`ui://${product}/studio-archive-${revision.digest("hex").slice(0,16)}.html`, mimeType="text/html;profile=mcp-app";
  const resource={uri,name:`${label} · Archivio dello studio`,mimeType};
  const string={type:"string",minLength:1}, offset={type:"integer",minimum:0};
  const scope={client_id:string,engagement_id:string};
  const definitions=[
    ["open","catalogue",{...scope,offset},[]],
    ["list_matters","catalogue",{client_id:string,offset},["client_id"]],
    ["read_matter","matter",{...scope,offset},["client_id","engagement_id"]],
    ["read_document","document",{...scope,reference:{type:"object"}},["client_id","engagement_id","reference"]],
    ["search","search",{client_id:string,all_clients:{type:"boolean"},query:string},["query"]],
    ["source","source",{client_id:string,all_clients:{type:"boolean"},query:string,source_id:string},["query","source_id"]],
    ["setup","setup",{confirmed:{type:"boolean"}},["confirmed"]],
  ];
  const tools=definitions.map(([suffix,operation,properties,required])=>({
    name:`${product}_archive_${suffix}`,title:resource.name,icons:[icon],
    description:suffix==="open"?`Open ${label}’s Studio Archive, showing only its projects.`:`${operation} for the selected ${label} Archive view.`,
    inputSchema:{type:"object",properties,required,additionalProperties:false},
    annotations:{readOnlyHint:operation!=="setup"},
    _meta:{ui:{visibility:suffix==="open"?["app","model"]:["app"],...(suffix==="open"?{resourceUri:uri}:{})},...(suffix==="open"?{"openai/ui":{entrypoints:[{type:"global"},{type:"thread"}]}}:{})}
  }));
  function call(name,args={}) {
    const index=tools.findIndex(tool=>tool.name===name);if(index<0)throw new Error("Unknown Archive tool");
    const {properties,required}=tools[index].inputSchema;
    if(!args || typeof args!=="object" || Array.isArray(args) || Object.keys(args).some(key=>!Object.hasOwn(properties,key)) || required.some(key=>!Object.hasOwn(args,key)) || Object.entries(args).some(([key,value])=>{
      const type=properties[key].type;
      return type==="integer"? !Number.isInteger(value)||value<0 : type==="object"? !value||typeof value!=="object"||Array.isArray(value) : typeof value!==type || type==="string"&&!value.trim();
    }))return {isError:true,content:[{type:"text",text:"Invalid Archive selection."}]};
    const runtime=process.env.MPARANZA_RUNTIME_ROOT || (process.platform==="win32"?path.join(process.env.LOCALAPPDATA || path.join(os.homedir(),"AppData/Local"),"mpr"):path.join(os.homedir(),".local/share/mparanza/runtime"));
    const managed=path.join(runtime,"venv",process.platform==="win32"?"Scripts/python.exe":"bin/python");
    const python=process.env.VERA_STUDIO_ARCHIVE_PYTHON || (fs.existsSync(managed)?managed:process.platform==="win32"?"python":"python3");
    const result=spawnSync(python,["-X","utf8",path.join(componentRoot,"scripts/archive_panel.py")],{input:JSON.stringify({operation:definitions[index][1],arguments:args}),encoding:"utf8",env:{...process.env,CLARA_ARCHIVE_HOST:product==="clara"?"1":"0",LUCIA_ASSURANCE_HOST:product==="lucia"?"1":"0"},maxBuffer:8*1024*1024,timeout:120000});
    let data;try{data=JSON.parse(result.stdout);}catch{data={error:"Archivio non disponibile. Verifica il runtime locale e riprova."};}
    if(result.error || result.status!==0 || data.error)return {isError:true,content:[{type:"text",text:"Archivio non disponibile nel pannello."}],_meta:{archive:{error:"archive_unavailable"}}};
    return {content:[{type:"text",text:`Archivio di ${label} pronto nel pannello.`}],_meta:{archive:data}};
  }
  function read() {
    const text=fs.readFileSync(path.join(assets,"archive.html"),"utf8")
      .replaceAll("__PRODUCT__",label)
      .replace("/*__CSS__*/",()=>fs.readFileSync(path.join(assets,"archive.css"),"utf8"))
      .replace("/*__SELECT_JS__*/","")
      .replace("/*__JS__*/",()=>`globalThis.archiveProduct=${JSON.stringify(product)};\n`+fs.readFileSync(path.join(assets,"archive-ui.js"),"utf8")+"\n"+fs.readFileSync(path.join(assets,"archive-host.js"),"utf8"))
      .replace("__FONT__",fs.readFileSync(path.join(pluginRoot,"assets/InstrumentSans-Regular.ttf")).toString("base64"))
      .replace("__FONT_BOLD__",fs.readFileSync(path.join(pluginRoot,"assets/InstrumentSans-SemiBold.ttf")).toString("base64"));
    return {contents:[{uri,mimeType,text,_meta:{ui:{prefersBorder:false,csp:{connectDomains:[],resourceDomains:[]}},"openai/ui":{preferredDisplayMode:"fullscreen",availableDisplayModes:["fullscreen"]}}}]};
  }
  return {resource,tools,call,read};
};
