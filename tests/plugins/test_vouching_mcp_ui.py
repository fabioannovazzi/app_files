from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("delivery", ["mcp", "legacy"])
def test_vouching_hydrates_private_rows_and_ignores_untrusted_updates(
    delivery: str,
) -> None:
    """Execute the complete widget against both documented host delivery paths."""
    widget = ROOT / "plugins/check-entries/assets/check-entries-review-widget.html"
    program = r"""
const fs = require('node:fs'), vm = require('node:vm');
const html = fs.readFileSync(process.argv[1], 'utf8');
const script = html.match(/<script>([\s\S]*)<\/script>/)[1];
const elements = new Map(), listeners = new Map(), sent = [];
const node = id => ({id, textContent:'', innerHTML:'', className:'', value:'',
  disabled:false, style:{}, dataset:{}, addEventListener(){}, appendChild(){},
  remove(){}, select(){}, setAttribute(){}, closest(){return null;}});
const document = {title:'', documentElement:{lang:'en'}, body:node('body'),
  getElementById(id){if(!elements.has(id)) elements.set(id,node(id)); return elements.get(id);},
  createElement:node, execCommand(){return true;}};
const privatePayload = {widget_type:'check_entries_review',
  review_payload:{schema_version:'2.0',plugin:'check-entries',workflow:'check-entries',
    run_id:'diagnostic-only',status:'ready_for_review',item_count:1,
    items:[{id:'entry-diagnostic',item_type:'missing_support',title:'Synthetic private row',
      status:'missing_support',data:{movement_number:'DIAG-1'},evidence:[],
      allowed_actions:['mark_unclear'],recommended_action:'mark_unclear'}],summary:{}},
  ui_decisions:{decisions:[]},final_artifacts:{outputs:[]},decision_policy:{can_persist:false}};
const result = {content:[{type:'text',text:'1 item'}],
  structuredContent:{ok:true,widget_type:'check_entries_review',item_count:1},
  _meta:{private_review_payload:privatePayload}};
const parent = {postMessage(message,origin){sent.push({message,origin});}};
const window = {parent,location:{search:''},
  addEventListener(name,cb){if(!listeners.has(name))listeners.set(name,[]);listeners.get(name).push(cb);},
  dispatchEvent(event){for(const cb of listeners.get(event.type)||[])cb(event);}};
if(process.argv[2]==='legacy') window.openai = {
  toolOutput:result.structuredContent,toolResponseMetadata:result._meta,callTool:async()=>({})};
const context = {window,document,URL,URLSearchParams,Blob,Event,console,navigator:{},
  setTimeout(){return 1;},clearTimeout(){}};
vm.createContext(context);
vm.runInContext(script,context);
const origin = 'https://host.example';
const send = (data,source=parent,eventOrigin=origin) => {
  for(const listener of listeners.get('message')||[])listener({data,source,origin:eventOrigin});
};
const read = () => vm.runInContext('({count:items().length, title:items()[0]?.title || null})',context);
(async()=>{
  const init = sent.find(x=>x.message.method==='ui/initialize');
  if(init){
    send({jsonrpc:'2.0',id:init.message.id,result:{protocolVersion:'2026-01-26',hostCapabilities:{}}});
    await Promise.resolve(); await Promise.resolve();
  }
  const notify = payload => ({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:payload});
  const initializedBeforeResult = sent.some(x=>x.message.method==='ui/notifications/initialized');
  // A standard host sends the result only after initialization. Also deliver it
  // independently below, to distinguish handshake from payload-selection bugs.
  if(process.argv[2]==='mcp' && initializedBeforeResult)send(notify(result));
  const normal = read();
  send(notify(result));
  const forcedDelivery = read();
  const malicious = {...result,_meta:{private_review_payload:{...privatePayload,
    review_payload:{...privatePayload.review_payload,items:[{...privatePayload.review_payload.items[0],title:'UNTRUSTED'}]}}}};
  send(notify(malicious),{});
  send(notify(malicious),parent,'https://wrong-origin.example');
  const afterUntrusted = read();
  send(notify({structuredContent:result.structuredContent}));
  const afterSummary = read();
  process.stdout.write(JSON.stringify({initializes:!!init,initializedBeforeResult,
    displayModes:init?.message.params.appCapabilities.availableDisplayModes,
    normal,forcedDelivery,afterUntrusted,afterSummary}));
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1;});
"""
    completed = subprocess.run(
        ["node", "-e", program, str(widget), delivery],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    observed = json.loads(completed.stdout)
    expected = {"count": 1, "title": "Synthetic private row"}
    assert observed["normal"] == expected, observed
    assert observed["forcedDelivery"] == expected, observed
    assert observed["afterUntrusted"] == expected, observed
    assert observed["afterSummary"] == expected, observed
    assert observed["initializes"] is True, observed
    assert observed["initializedBeforeResult"] is True, observed
    assert observed["displayModes"] == ["inline", "fullscreen"], observed
