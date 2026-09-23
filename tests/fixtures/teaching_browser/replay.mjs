/** Regression only: execute the real capability driver against the real local HTML.
 * Headless Chromium is deliberately UNVERIFIED, never connected-Chrome evidence.
 * Live Chrome lesson acceptance is reviewed separately from these CI regressions.
 */
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { executeCapability } from '../../../plugins/browser-automation/scripts/capability_runtime.mjs';
const config = JSON.parse(await readFile(process.argv[2], 'utf8'));
const require = createRequire(import.meta.url);
const { chromium } = require(config.playwrightPackage);
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  page.setDefaultTimeout(10000);
  const tab = { goto: url => page.goto(url), url: async () => page.url(), playwright: page };
  const capability = JSON.parse(await readFile(config.capabilityPath, 'utf8'));
  const oldOrigin = capability.site.allowed_origins[0];
  const rebound = JSON.parse(JSON.stringify(capability).split(oldOrigin).join(config.origin));
  const first = await executeCapability({ tab, capability: rebound,
    inputs: { 'client-code': 'DEMO-A', 'document-type': 'Invoice', reviewed: true },
    runDirectory: config.demoDirectory, runId: 'teaching-demo',
    environment: { execution_mode: 'unverified' }, downloadDirectory: null });
  let practice = null;
  if (config.practiceDirectory) {
    practice = await executeCapability({ tab, capability: rebound,
      inputs: { 'client-code': 'DEMO-B', 'document-type': 'Credit note', reviewed: true },
      runDirectory: config.practiceDirectory, runId: 'teaching-practice',
      environment: { execution_mode: 'unverified' }, downloadDirectory: null });
  }
  process.stdout.write(JSON.stringify({ demo: first, practice }));
} finally { await browser.close(); }
