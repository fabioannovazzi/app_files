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
  replaceChildren(...items) { this.children = items; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(key, callback) { this.listeners[key] = callback; }
}
const elements = { app: new Element("main"), status: new Element("p"), refresh: new Element("button") };
const document = { getElementById: key => elements[key], createElement: tag => new Element(tag) };
const listeners = {}, parent = { postMessage() {} };
const window = { parent, addEventListener: (name, callback) => { listeners[name] = callback; } };
const factories = {};
for (const name of ["VeraOpenItemsIntake", "VeraBrowser", "VeraFusion", "VeraRating", "VeraTransformation", "VeraWebsite", "VeraPracticeReviews", "VeraCommunication", "VeraPatentBox", "VeraBandiContributions"]) {
  factories[name] = { create: () => ({ dispose() {}, async flush() {}, active() { return false; } }) };
}
vm.runInNewContext(fs.readFileSync(process.argv[2], "utf8"), {
  document, window, globalThis: factories, setTimeout: () => 1, clearTimeout() {},
}, { filename: process.argv[2] });
const catalogue = JSON.parse(fs.readFileSync(0, "utf8"));
listeners.message({ source: parent, data: {
  jsonrpc: "2.0", method: "ui/notifications/tool-result", params: { _meta: { workspace: catalogue } },
} });
const collect = element => [element, ...element.children.flatMap(collect)];
const rows = collect(elements.app).filter(element => element.tagName === "SECTION" && element.className === "work-row");
process.stdout.write(JSON.stringify(rows.map(row => ({
  text: collect(row).map(element => element.textContent || "").join(" "),
  buttons: collect(row).filter(element => element.tagName === "BUTTON").map(element => element.textContent),
}))));
