import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const server=require('../plugins/browser-automation/mcp/server.cjs');

test('native resource is self-contained and exposes a thread entry point',()=>{
  const list=server.handleRpc({id:1,method:'tools/list'}).result.tools;
  const open=list.find(t=>t.name==='agenzia_workspace_open');
  assert.deepEqual(open._meta['openai/ui'].entrypoints,[{type:'thread'}]);
  assert.equal(open._meta.ui.resourceUri,server.URI);
  assert.deepEqual(list.find(t=>t.name==='agenzia_workspace_start')._meta.ui.visibility,['app']);
  const html=server.resource();
  assert.match(html,/ui\/initialize/);
  assert.match(html,/data:font\/ttf;base64,/);
  assert.doesNotMatch(html,/__CSS__|__JS__|__FONT_/);
});

test('unbound open does not run an acquisition or invent a client',()=>{
  const value=server.callTool('agenzia_workspace_open',{});
  assert.deepEqual(value.structuredContent,{state:'unbound'});
  assert.equal(value._meta.agenzia.plan,undefined);
});

test('invalid or expired native inputs cannot reach a worker',()=>{
  assert.throws(()=>server.callTool('agenzia_workspace_start',{workspace_ref:'missing',revision:'r',request_id:'x',password:'secret'}),/arguments-invalid/);
  assert.throws(()=>server.callTool('agenzia_workspace_start',{workspace_ref:'missing',revision:'r',request_id:'x'}),/workspace-expired/);
});

test('real Python projection keeps client and financial evidence out of model text',()=>{
  const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'vera-agenzia-mcp-')));
  try{
    const plan={schema_version:'vera-agenzia-plan/v1',clients:[{name:'CLIENTE RISERVATO',tax_code:'01234567890',vat_number:'01234567890'}],date_from:'2026-01-01',date_to:'2026-01-31',operations:['ricevute']};
    const planPath=path.join(root,'plan.json'),output=path.join(root,'output');
    fs.writeFileSync(planPath,JSON.stringify(plan));
    const opened=server.callTool('agenzia_workspace_open',{plan_path:planPath,output_directory:output});
    assert.equal(opened._meta.agenzia.plan.clients[0].name,'CLIENTE RISERVATO');
    assert.doesNotMatch(JSON.stringify(opened.content),/CLIENTE RISERVATO|01234567890/);
    const run='a'.repeat(32),runPath=path.join(output,'runs',run);fs.mkdirSync(runPath,{recursive:true});
    fs.writeFileSync(path.join(runPath,'plan.json'),JSON.stringify(plan));
    fs.writeFileSync(path.join(runPath,'status.json'),JSON.stringify({state:'failed',error:'browser-unavailable',scopes:[{client:'01234567890'}]}));
    const failed=server.callTool('agenzia_workspace_status',{workspace_ref:opened.structuredContent.workspace_ref,run_id:run});
    assert.equal(failed.structuredContent.state,'failed');
    assert.equal(failed._meta.agenzia.scopes[0].client,'01234567890');
    assert.doesNotMatch(JSON.stringify(failed.content),/01234567890|CLIENTE RISERVATO/);
  }finally{fs.rmSync(root,{recursive:true,force:true});}
});
