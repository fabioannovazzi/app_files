import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtemp, mkdir, readFile, realpath, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { makeServer } from '../server.mjs';
import { xml } from './provider-fixture.mjs';

const repo = fileURLToPath(new URL('../../../', import.meta.url));
const nodeArgs = ['--import', new URL('./provider-fixture.mjs', import.meta.url).href];
const sample = { fiscal_id: '01234567897', from_date: '2026-10-01', to_date: '2026-10-31' };
const id = 'd08489da-1ab4-4a7f-b2bd-2e092fbb79ad';
async function invoke(client, name, args = {}) {
  const result = await client.callTool({ name, arguments: args });
  const text = result.content[0].text;
  assert(!/PRIVATE-(?:PROVIDER|INVOICE)|test-password|test-token|FatturaElettronicaHeader/.test(text));
  return result.isError ? { error: text } : JSON.parse(text);
}
async function connection(t, env) {
  const mcp = makeServer(env, { upstreamNodeArgs: nodeArgs });
  const [a, b] = InMemoryTransport.createLinkedPair();
  const client = new Client({name:'test',version:'1'});
  await Promise.all([mcp.connect(a), client.connect(b)]);
  t.after(() => client.close());
  return client;
}

test('registered entry point discovers genuine upstream tools without an A-Cube account', async t => {
  const client = new Client({name:'smoke',version:'1'});
  await client.connect(new StdioClientTransport({ command: process.execPath, args:[join(repo,'connectors/vera-acube/server.mjs'),'--sandbox'] }));
  t.after(() => client.close());
  const names = (await client.listTools()).tools.map(tool => tool.name).sort();
  assert.deepEqual(names, ['archive_invoice_xml','connection_status','list_invoice_references','request_invoice_download']);
  const info = await invoke(client, 'connection_status');
  assert.equal(info.upstream.name, 'mcp-server-acube');
  assert.equal(info.upstream.version, '0.4.0');
  assert.equal(info.provider_login, 'not_tested');
});

test('sandbox simulation, scoped references, Archive receipt, exact retry, wrong party and sanitized failure', async t => {
  const home = await mkdtemp(join(await realpath(tmpdir()),'vera-acube-test-'));
  t.after(() => rm(home, {recursive:true,force:true}));
  const root = join(home,'Studio');
  await mkdir(root);
  const previous = { ...process.env };
  Object.assign(process.env,{ACUBE_EMAIL:'test@example.invalid',ACUBE_PASSWORD:'test-password', ACUBE_ENVIRONMENT:'sandbox', VERA_ACUBE_SANDBOX_HOME:home});
  t.after(() => { for (const key of ['ACUBE_EMAIL','ACUBE_PASSWORD','ACUBE_ENVIRONMENT','VERA_ACUBE_SANDBOX_HOME']) { if (previous[key] === undefined) delete process.env[key]; else process.env[key] = previous[key]; } });
  const archive = (...args) => JSON.parse(execFileSync(join(repo,'.venv/bin/python'), [join(repo,'plugins/studio-archive/scripts/studio_archive.py'), ...args],
    { env: {...process.env, VERA_STUDIO_ARCHIVE_SESSION_ID:'separate-archive-setup-session', VERA_STUDIO_ARCHIVE_STATE_DIR:join(home,'state'),VERA_STUDIO_ARCHIVE_PROFILE_DIR:join(home,'profile')},encoding:'utf8' }));
  archive('configure','--archive-root',root);
  const clientId = archive('create-client','--legal-name','Synthetic MCP studio','--tax-identifier',sample.fiscal_id).client.client_id;
  const engagement = archive('create-engagement','--client-id',clientId,'--engagement-label','Synthetic October').engagement.engagement_id;
  const client = await connection(t, 'sandbox');
  const job = await invoke(client, 'request_invoice_download', sample);
  assert.equal(job.status,'simulated'); assert.equal(job.invoice_count,1);
  const listed = await invoke(client, 'list_invoice_references', {...sample, direction:'incoming'});
  assert.deepEqual(listed.invoices,[id]); assert.equal(listed.next_page,null);
  const args = { fiscal_id:sample.fiscal_id, direction:'incoming', uuid:id, engagement_id:engagement };
  const saved = await invoke(client, 'archive_invoice_xml', args);
  assert.equal(saved.status,'imported', JSON.stringify(saved));
  assert.equal(await readFile(saved.path,'utf8'),xml);
  const retry = await invoke(client, 'archive_invoice_xml', args);
  assert.equal(retry.status,'already_imported'); assert.equal(retry.input_id,saved.input_id);
  assert.equal((await invoke(client, 'archive_invoice_xml', {...args, fiscal_id:'12345678901'})).error,'invoice_party_mismatch');
  assert.match((await invoke(client, 'archive_invoice_xml', {...args, uuid:'c08489da-1ab4-4a7f-b2bd-2e092fbb79ad'})).error,/HTTP 403/);
  const production = await connection(t, 'production');
  assert.equal((await invoke(production,'request_invoice_download',sample)).status,'request_accepted');
});
