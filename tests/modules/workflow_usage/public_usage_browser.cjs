const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

class Element {
  constructor() { this.children = []; this.hidden = true; this.textContent = ""; this.dataset = {}; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
}

const elements = Object.fromEntries(["status", "functions", "apps", "versions", "empty", "coverage", "results"].map(id => [id, new Element()]));
const totals = ["started", "completed", "failed"].map(key => Object.assign(new Element(), { dataset: { total: key } }));
const responses = [];
const callbacks = {};
let timer;
const snapshot = {
  updated_at: "2026-11-07T12:00:00+00:00",
  minimum_versions: { vera: "0.1.492", clara: "0.1.347", lucia: "0.1.176" },
  minimum_version_release_dates: { vera: "2026-10-25", clara: "2026-10-25", lucia: "2026-10-25" },
  identity_complete: true,
  totals: { started: 3, completed: 2, failed: 1 },
  functions: [
    { product: "vera", pipeline: "business-planning", label: "Business plan", started: 1, completed: 1, failed: 0 },
    { product: "lucia", pipeline: "controllo-documento", label: "Controllo documento", started: 1, completed: 0, failed: 1 },
    { product: "clara", pipeline: "business-planning", label: "Business plan", started: 0, completed: 0, failed: 0 },
  ],
  apps: [
    { app: "codex", started: 2, completed: 2, failed: 0 },
    { app: "cowork", started: 1, completed: 0, failed: 1 },
    { app: "antigravity", started: 0, completed: 0, failed: 0 },
  ],
};
responses.push(snapshot);
const document = {
  hidden: false,
  getElementById: id => elements[id],
  querySelectorAll: selector => { assert.equal(selector, "[data-total]"); return totals; },
  createElement: () => new Element(),
  createTextNode: textContent => ({ textContent }),
  addEventListener: (event, fn) => { callbacks[event] = fn; },
};
vm.runInNewContext(fs.readFileSync("static/shared/utilizzo/usage.js", "utf8"), {
  document,
  Intl,
  Date,
  setInterval: (fn, delay) => { assert.equal(delay, 60000); timer = fn; },
  fetch: async (url, options) => {
    assert.equal(url, "/api/usage-summary");
    assert.equal(options.credentials, "omit");
    const next = responses.shift();
    if (next instanceof Error) throw next;
    return { ok: true, json: async () => next };
  },
});
const settle = () => new Promise(resolve => setImmediate(resolve));

(async () => {
  await settle();
  assert.deepEqual(totals.map(cell => cell.textContent), ["3", "2", "1"]);
  assert.equal(elements.functions.children.length, 2);
  assert.equal(elements.apps.children.length, 2);
  assert.equal(elements.functions.children[1].children[0].children[1].textContent, "Trova errori e incoerenze nel documento");
  assert.equal(elements.results.hidden, false);
  assert.match(elements.versions.textContent, /Vera 0\.1\.492 — 25 ottobre 2026/);
  assert.match(elements.versions.textContent, /Clara 0\.1\.347 — 25 ottobre 2026/);
  assert.match(elements.versions.textContent, /Lucia 0\.1\.176 — 25 ottobre 2026/);
  assert.match(elements.versions.textContent, /senza MCP remoto/);
  assert.match(elements.versions.textContent, /Sono incluse anche le versioni successive/);
  assert.doesNotMatch(elements.versions.textContent, /30 giorni|raccolta|Fabio/);

  responses.push(new Error("offline"));
  await timer();
  assert.deepEqual(totals.map(cell => cell.textContent), ["3", "2", "1"]);
  assert.match(elements.status.textContent, /ultimi dati ricevuti/);

  responses.push({ ...snapshot, totals: { started: 0, completed: 0, failed: 0 }, functions: [], apps: [] });
  document.hidden = true;
  await timer();
  assert.equal(responses.length, 1);
  document.hidden = false;
  callbacks.visibilitychange();
  await settle();
  assert.equal(elements.functions.children.length, 0);
  assert.equal(elements.empty.hidden, false);
  assert.deepEqual(totals.map(cell => cell.textContent), ["0", "0", "0"]);
})().catch(error => { console.error(error); process.exitCode = 1; });
