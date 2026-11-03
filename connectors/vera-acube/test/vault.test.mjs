import assert from 'node:assert/strict';
import {mkdtemp, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {delimiter, join} from 'node:path';
import test from 'node:test';
import {readVaultLogin, VaultLoginError} from '../../vera-1password/login.mjs';
import {makeServer} from '../server.mjs';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {InMemoryTransport} from '@modelcontextprotocol/sdk/inMemory.js';

test('a connector uses only the bound vault item; provider and op secrets never appear in tool errors', {skip: process.platform === 'win32' && 'This test uses a POSIX executable in place of op.exe'}, async t => {
  const folder = await mkdtemp(join(tmpdir(),'vera-vault-'));
  t.after(() => rm(folder,{recursive:true,force:true}));
  const stub = join(folder, 'fake-op.cjs');
  await writeFile(stub, `const args=process.argv.slice(2);
    if (JSON.stringify(args)===JSON.stringify(['item','get','Alfa','--vault','Studio','--fields','username,password','--reveal','--format','json'])) {
      process.stdout.write(JSON.stringify([{id:'username',value:'demo-user'},{id:'password',value:'demo-secret'}]));
    } else { process.stderr.write('private-error-canary');process.exitCode=1; }`);
  await writeFile(join(folder,'op'), '#!/bin/sh\nexec node "$(dirname "$0")/fake-op.cjs" "$@"\n',{mode:0o700});
  const oldPath = process.env.PATH;
  process.env.PATH = folder+delimiter+oldPath;
  t.after(() => {process.env.PATH=oldPath;});
  assert.deepEqual(await readVaultLogin({vault:'Studio',item:'Alfa'}),{username:'demo-user',password:'demo-secret'});
  await assert.rejects(readVaultLogin({vault:'Studio',item:'--help'}),VaultLoginError);
  const saved = [process.env.ACUBE_EMAIL,process.env.ACUBE_PASSWORD];
  process.env.ACUBE_EMAIL='unselected@example.invalid';process.env.ACUBE_PASSWORD='unselected-secret';
  t.after(()=>['ACUBE_EMAIL','ACUBE_PASSWORD'].forEach((k,i)=>{if(saved[i]===undefined)delete process.env[k];else process.env[k]=saved[i];}));
  const server = makeServer('sandbox',{binding:{vault:'Other studio',item:'Alfa'}});
  const client = new Client({name:'binding-test',version:'1'});
  const [a,b] = InMemoryTransport.createLinkedPair();
  await Promise.all([server.connect(a),client.connect(b)]);
  t.after(()=>client.close());
  const result = await client.callTool({name:'list_invoice_references',arguments:{fiscal_id:'01234567897',from_date:'2026-10-01',to_date:'2026-10-31',direction:'incoming'}});
  assert.equal(result.isError,true);
  assert.match(result.content[0].text,/selected login/);
  assert.doesNotMatch(JSON.stringify(result),/private-error-canary|demo-secret|unselected-secret/);
});
