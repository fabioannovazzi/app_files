// Intercept the HTTP boundary only. The published MCP, its auth client and
// both MCP transports run normally. No test branch contacts an external host.
const id = 'd08489da-1ab4-4a7f-b2bd-2e092fbb79ad';
const vat = '01234567897';
export const xml = `<?xml version="1.0" encoding="UTF-8"?><p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2"><FatturaElettronicaHeader><CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>${vat}</IdCodice></IdFiscaleIVA></DatiAnagrafici></CessionarioCommittente></FatturaElettronicaHeader><FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Data>2026-10-02</Data><Numero>PRIVATE-INVOICE-CANARY</Numero></DatiGeneraliDocumento></DatiGenerali></FatturaElettronicaBody></p:FatturaElettronica>`;
export function provider(url, options) {
  const { host, pathname, searchParams } = new URL(url);
  const isSandbox = process.env.ACUBE_ENVIRONMENT !== 'production';
  if (host === (isSandbox ? 'common-sandbox.api.acubeapi.com' : 'common.api.acubeapi.com') && pathname === '/login' && options.method === 'POST') {
    const login = JSON.parse(options.body);
    if (login.password === 'test-password' && login.email === 'test@example.invalid') return Response.json({ token: 'test-token' });
  }
  if (host === (isSandbox ? 'api-sandbox.acubeapi.com' : 'api.acubeapi.com') && options.headers.Authorization === 'Bearer test-token') {
    if (pathname === (isSandbox ? '/simulate/jobs/invoice-download' : '/jobs/invoice-download') && options.method === 'POST' && JSON.parse(options.body).fiscal_id === vat) {
      return Response.json(isSandbox ? { job: id, invoices: [id] } : { uuid: id });
    }
    if (pathname === '/invoices' && searchParams.get('recipient.business_vat_number_code') === vat && searchParams.get('type') === '1' && searchParams.get('invoice_date[after]') === '2026-10-01') {
      return Response.json([{ uuid: id, invoice_date: '2026-10-02', recipient: {business_vat_number_code: vat} }]);
    }
    if (pathname === `/invoices/${id}` && options.headers.Accept === 'application/xml') return new Response(xml, { headers: { 'content-type': 'application/xml' } });
  }
  return new Response('PRIVATE-PROVIDER-ERROR', { status: 403 });
}
globalThis.fetch = provider;
