"use strict";
// Exercise the real workspace asset with synthetic DOM/host transport only.
const fs = require("node:fs"), vm = require("node:vm");
class Element {
  constructor(tag) {
    this.tagName = tag.toUpperCase(); this.children = []; this.textContent = "";
    this.attributes = {}; this.listeners = {}; this.className = "";
    this.classList = { toggle() {} };
  }
  append(...items) { this.children.push(...items); }
  insertBefore(item, before) { this.children.splice(this.children.indexOf(before), 0, item); }
  replaceChildren(...items) { this.children = items; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(key, callback) { this.listeners[key] = callback; }
}
const elements = { app: new Element("main"), status: new Element("p"), refresh: new Element("button") };
const document = { getElementById: key => elements[key], createElement: tag => new Element(tag) };
const fixture = JSON.parse(fs.readFileSync(0, "utf8")), importMode = process.argv[3] === "import";
const listeners = {}, parent = { postMessage(message) {
  if (!importMode || !message.id) return;
  const result = message.method === "ui/initialize" ? {} : { _meta: { workspace: fixture.import_setup } };
  queueMicrotask(() => listeners.message({ source: parent, data: { jsonrpc: "2.0", id: message.id, result } }));
} };
const window = { parent, addEventListener: (name, callback) => { listeners[name] = callback; } };
const factories = {};
for (const name of ["VeraOpenItemsIntake", "VeraBrowser", "VeraFusion", "VeraRating", "VeraTransformation", "VeraWebsite", "VeraPracticeReviews", "VeraCommunication", "VeraPatentBox", "VeraBandiContributions"]) {
  factories[name] = { create: () => ({ dispose() {}, async flush() {}, active() { return false; } }) };
}
vm.runInNewContext(fs.readFileSync(process.argv[2], "utf8"), {
  document, window, globalThis: factories, setTimeout: () => 1, clearTimeout() {},
}, { filename: process.argv[2] });
const catalogue = importMode ? fixture.catalogue : fixture;
listeners.message({ source: parent, data: {
  jsonrpc: "2.0", method: "ui/notifications/tool-result", params: { _meta: { workspace: catalogue } },
} });
const collect = element => [element, ...element.children.flatMap(collect)];
(async () => {
  if (importMode) {
    await new Promise(resolve => setImmediate(resolve));
    const open = collect(elements.app).find(element => element.tagName === "BUTTON" && element.textContent === "Importa documenti");
    await open.listeners.click();
    const nodes = collect(elements.app);
    process.stdout.write(JSON.stringify({
      text: nodes.map(element => element.textContent || "").join(" "),
      buttons: nodes.filter(element => element.tagName === "BUTTON").map(element => element.textContent),
      filePickers: nodes.filter(element => element.tagName === "INPUT" && element.type === "file").length,
      status: elements.status.textContent,
    }));
  } else {
    const rows = collect(elements.app).filter(element => element.tagName === "SECTION" && element.className === "work-row");
    process.stdout.write(JSON.stringify(rows.map(row => ({
      text: collect(row).map(element => element.textContent || "").join(" "),
      buttons: collect(row).filter(element => element.tagName === "BUTTON").map(element => element.textContent),
    }))));
  }
})().catch(error => { process.stderr.write(error.stack); process.exitCode = 1; });
