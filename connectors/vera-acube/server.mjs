import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { readVaultLogin, VaultLoginError } from '../vera-1password/login.mjs';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { AcubeClient } from 'mcp-server-acube/dist/client.js';
import { z } from 'zod';

const here = dirname(fileURLToPath(import.meta.url));
const archiveSession = process.env.VERA_STUDIO_ARCHIVE_SESSION_ID || process.env.CODEX_THREAD_ID || randomUUID();
const upstreamPath = fileURLToPath(import.meta.resolve('mcp-server-acube'));
const requiredTools = ['download_invoices_once', 'list_invoices', 'get_invoice'];
const fiscalId = z.string().regex(/^(?:\d{11}|[A-Z0-9]{16})$/);
const uuid = z.string().uuid();
const windowFields = { fiscal_id: fiscalId, from_date: z.string().date(), to_date: z.string().date() };
const direction = z.enum(['incoming', 'outgoing']);
class PublicError extends Error {}

// Secret material is confined to these processes. Neither raw provider errors nor
// op/Archive stderr are forwarded through the public MCP surface.
async function credentials(environment, binding) {
  if (!binding && process.env.ACUBE_EMAIL && process.env.ACUBE_PASSWORD) {
    return { email: process.env.ACUBE_EMAIL, password: process.env.ACUBE_PASSWORD };
  }
  const login = await readVaultLogin(binding ?? {vault: 'Vera', item: `A-Cube ${environment}`});
  return {email: login.username, password: login.password};
}

function checkedWindow(args) {
  if (args.from_date > args.to_date) throw new PublicError('The start date is after the end date.');
  return { fiscal_id: args.fiscal_id, from_date: args.from_date, to_date: args.to_date };
}

async function openUpstream(environment, login, nodeArgs = []) {
  const client = new Client({ name: 'vera-acube', version: '0.1.0' });
  const transport = new StdioClientTransport({ command: process.execPath, args: [...nodeArgs, upstreamPath],
    stderr: 'ignore', env: { ACUBE_EMAIL: login.email, ACUBE_PASSWORD: login.password, ACUBE_ENVIRONMENT: environment } });
  try {
    await client.connect(transport);
    const { tools } = await client.listTools();
    if (!requiredTools.every(name => tools.some(tool => tool.name === name))) {
      throw new PublicError('The installed A-Cube MCP lacks the required invoice tools.');
    }
    return client;
  } catch (error) { await client.close(); throw error; }
}

async function callUpstream(client, name, args) {
  const result = await client.callTool({ name, arguments: args });
  const content = result.content?.[0];
  if (result.isError || content?.type !== 'text') {
    const status = /Acube (?:API error|login failed) \((\d{3})\)/.exec(content?.text ?? '')?.[1];
    throw new PublicError(`A-Cube ${name} failed${status ? ` (HTTP ${status})` : ''}.`);
  }
  return content.text;
}

function archiveXml(args, xml, environment, runtime) {
  const python = runtime.python || process.env.VERA_ACUBE_PYTHON || join(here, '../../.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  return new Promise((resolve, reject) => {
    const env = { ...process.env };
    if (runtime.veraRoot) env.VERA_ACUBE_MODULES = join(runtime.veraRoot, 'modules');
    if (environment === 'sandbox') env.VERA_STUDIO_ARCHIVE_SESSION_ID = archiveSession;
    delete env.ACUBE_PASSWORD; delete env.ACUBE_EMAIL;
    const worker = spawn(python, [join(here, 'archive_invoice.py'), args.fiscal_id, args.direction,
      args.uuid, args.engagement_id, environment], { env, stdio: ['pipe', 'pipe', 'ignore'] });
    const chunks = [];
    worker.stdout.on('data', chunk => chunks.push(chunk));
    worker.on('error', () => reject(new PublicError('Vera Archive Python runtime unavailable.')));
    worker.stdin.on('error', () => {}); // The child's exit reports a rejected import.
    worker.on('close', code => {
      try {
        const receipt = JSON.parse(Buffer.concat(chunks).toString());
        if (code === 0) return resolve(receipt);
        if (['client_not_resolved','invoice_party_mismatch','invalid_invoice','archive_import_failed'].includes(receipt.error)) {
          return reject(new PublicError(receipt.error));
        }
      } catch { /* An invalid response must never be relayed to the host. */ }
      reject(new PublicError('Archive import failed. Check the selected engagement and local runtime.'));
    });
    worker.stdin.end(xml);
  });
}

export function makeServer(environment, { upstreamNodeArgs = [], binding, runtime = {} } = {}) {
  const server = new McpServer({ name: 'vera-acube', version: '0.1.0' });
  let active;
  function session() {
    active ??= credentials(environment, binding).then(async login => ({
      mcp: await openUpstream(environment, login, upstreamNodeArgs),
      sandboxApi: environment === 'sandbox' ? new AcubeClient({ ...login, environment }) : undefined,
    })).catch(error => { active = undefined; throw error; });
    return active;
  }
  function tool(name, description, inputSchema, run) {
    server.registerTool(name, { description: `[${environment}] ${description}`, inputSchema }, async args => {
      try {
        const value = await run(args);
        return { content: [{ type: 'text', text: JSON.stringify({ environment, ...value }) }] };
      } catch (error) {
        return { isError: true, content: [{ type: 'text', text: (error instanceof PublicError || error instanceof VaultLoginError) ? error.message : 'A-Cube connection or response failed. Check the account and retry reads. Verify a download request before resubmitting.' }] };
      }
    });
  }
  tool('connection_status', 'Check the installed upstream MCP and its tools locally. No provider login.', {}, async () => {
    const probe = await openUpstream(environment, { email: 'discovery@example.invalid', password: 'local-discovery-only' }, upstreamNodeArgs);
    try { return { upstream: probe.getServerVersion(), tools_verified: requiredTools, provider_login: 'not_tested' }; }
    finally { await probe.close(); }
  });
  tool('request_invoice_download', 'Request one invoice download for a configured fiscal ID. Production jobs are asynchronous. In sandbox this creates synthetic invoices.', windowFields, async args => {
    const body = checkedWindow(args);
    const { mcp, sandboxApi } = await session();
    if (sandboxApi) {
      // The upstream MCP does not expose A-Cube's distinct simulation endpoint.
      const { data } = await sandboxApi.post('/simulate/jobs/invoice-download', body);
      return { status: 'simulated', job: uuid.parse(data.job), invoice_count: z.array(uuid).parse(data.invoices).length };
    }
    const data = JSON.parse(await callUpstream(mcp, 'download_invoices_once', body));
    const job = uuid.safeParse(data?.uuid ?? data?.job ?? data);
    return { status: 'request_accepted', job: job.success ? job.data : null };
  });
  tool('list_invoice_references', 'List one page of matching A-Cube invoice references. Continue with next_page until null. A list is not evidence that a new job completed.',
    { ...windowFields, direction, page: z.number().int().min(1).default(1) }, async args => {
      checkedWindow(args);
      const { mcp } = await session();
      const party = args.direction === 'incoming' ? 'recipient' : 'sender';
      const isVat = args.fiscal_id.length === 11;
      const field = isVat ? 'business_vat_number_code' : 'business_fiscal_code';
      const data = JSON.parse(await callUpstream(mcp, 'list_invoices', {
        page: args.page, items_per_page: 30, direction: args.direction, [`${party}_${isVat ? 'vat' : 'fiscal_code'}`]: args.fiscal_id,
        invoice_date_from: args.from_date, invoice_date_to: args.to_date, fields: ['uuid', `${party}.${field}`, 'invoice_date'],
      }));
      if (!Array.isArray(data) || data.some(row => row?.[party]?.[field] !== args.fiscal_id ||
        !z.string().date().safeParse(row.invoice_date).success || row.invoice_date < args.from_date || row.invoice_date > args.to_date)) {
        throw new PublicError('A-Cube returned a row outside the requested client or period, or without enough data to verify it.');
      }
      return { invoices: data.map(row => uuid.parse(row.uuid)), next_page: data.length === 30 ? args.page + 1 : null };
    });
  tool('archive_invoice_xml', 'Save an A-Cube XML to the matching Studio Archive client and selected engagement. Returns only its local receipt. Use a synthetic engagement in sandbox.',
    { fiscal_id: fiscalId, direction, uuid, engagement_id: z.string().min(1).max(100) }, async args => {
      const { mcp } = await session();
      const xml = await callUpstream(mcp, 'get_invoice', { uuid: args.uuid, format: 'xml' });
      return archiveXml(args, xml, environment, runtime);
    });
  server.server.onclose = () => { active?.then(s => s.mcp.close()).catch(() => {}); };
  return server;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { values } = parseArgs({options: {
    sandbox: {type: 'boolean'}, production: {type: 'boolean'}, vault: {type: 'string'}, item: {type: 'string'},
    'vera-root': {type: 'string'}, python: {type: 'string'},
  }});
  if ((values.sandbox && values.production) || !!values.vault !== !!values.item) process.exit(2);
  const binding = values.vault ? {vault: values.vault, item: values.item} : undefined;
  const runtime = {veraRoot: values['vera-root'], python: values.python};
  await makeServer(values.production ? 'production' : 'sandbox', {binding, runtime}).connect(new StdioServerTransport());
}
