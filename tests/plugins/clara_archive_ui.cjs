'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
async function exercise(language){
 const nodes=new Map(),sent=[];let listener;
 function node(tag){return {tag,children:[],textContent:'',disabled:false,append(...items){this.children.push(...items);},replaceChildren(){this.children=[];},addEventListener(type,fn){this[type]=fn;},setAttribute(k,v){this[k]=v;}};}
 const get=id=>{if(!nodes.has(id))nodes.set(id,node(id));return nodes.get(id);};
 const parent={postMessage(m){let result;if(m.method==='ui/initialize')result={hostContext:{locale:language},hostCapabilities:{experimental:{'openai/message':{}}}};
 if(m.method==='tools/call')result={_meta:{archive:m.params.name==='clara_archive_open'?{configured:true,clients:[{client_id:'c1',display_name:'Synthetic client',registration_status:'registered'}]}:{engagements:[{engagement_id:'e1',label:'Synthetic engagement',status:'open'}]}}};
 if(m.method==='ui/message'){sent.push(m.params);result={};}
 if(result)queueMicrotask(()=>listener({source:parent,data:{jsonrpc:'2.0',id:m.id,result}}));}};
 const document={getElementById:get,createElement:node,documentElement:{}};
 const context={document,parent,addEventListener(type,fn){listener=fn;},setTimeout(){return 1;},clearTimeout(){},queueMicrotask};
 const source=fs.readFileSync(process.argv[2],'utf8').split('<script>')[1].split('</script>')[0];vm.runInNewContext(source,context);
 const tick=()=>new Promise(resolve=>setImmediate(resolve));await tick();
 assert.equal(document.documentElement.lang,language);
 function flatten(e){return [e,...e.children.flatMap(flatten)];}
 const find=text=>flatten(get('main')).find(e=>e.tag==='button'&&e.textContent.includes(text));
 await find('Synthetic client').click();await tick();
 const open=find('Synthetic engagement');assert.ok(open,'engagement has a direct open action');
 await open.click();await tick();
 assert.equal(sent.length,1);assert.equal(sent[0]._meta['openai/message'].target,'new');assert.match(sent[0].content[0].text,/clara_archive_case/);
 assert.ok(find('Synthetic engagement').disabled,'acknowledged handoff remains disabled');
 await find('Synthetic engagement').click();await tick();assert.equal(sent.length,1,'duplicate submission suppressed');
 assert.ok(!fs.readFileSync(process.argv[2],'utf8').includes('<aside'),'no empty sidebar');
}
(async()=>{for(const language of ['en','it','fr','de','es'])await exercise(language);process.stdout.write('Archive: direct handoff, localization and duplicate prevention passed\n');})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1;});
