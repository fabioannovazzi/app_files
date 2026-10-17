"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const test = require("node:test");
const source = fs.readFileSync("static/shared/vera-testing-status.js", "utf8");

async function surface(reply, hidden = false) {
  const node = {dataset: {testingPipeline: "journal-sampling", testStatus: "untried"}};
  const unavailable = {hidden: true};
  const listeners = {};
  const document = {
    hidden, documentElement: {dataset: {}},
    querySelectorAll: () => [node], querySelector: () => unavailable,
    addEventListener: (name, callback) => { listeners[name] = callback; },
    dispatchEvent: () => { document.updates = (document.updates || 0) + 1; }
  };
  let fetcher = reply;
  let requests = 0;
  let interval;
  const context = {
    document, AbortController, Event,
    setTimeout: () => 1, clearTimeout: () => {},
    setInterval: callback => { interval = callback; },
    fetch: async (url, options) => {
      requests += 1;
      assert.equal(url, "/api/vera/testing-status");
      assert.equal(options.credentials, "omit");
      assert.equal(options.cache, "no-store");
      return fetcher();
    }
  };
  vm.runInNewContext(source, context);
  await new Promise(resolve => setImmediate(resolve));
  return {
    node, unavailable, document, listeners,
    count: () => requests,
    refresh: async next => { fetcher = next; await interval(); }
  };
}

const response = status => async () => ({
  ok: true,
  json: async () => ({schema_version: 1, pipelines: {"journal-sampling": status}})
});

test("received levels update the icon and trigger localized accessible labels", async () => {
  const page = await surface(response("agent"));
  assert.equal(page.node.dataset.testStatus, "agent");
  assert.equal(page.document.documentElement.dataset.testingSource, "received");
  assert.equal(page.document.updates, 1);
  assert.equal(page.unavailable.hidden, true);
});

test("a later reset downgrades previously received status to untried", async () => {
  const page = await surface(response("repeated"));
  await page.refresh(response("untried"));
  assert.equal(page.node.dataset.testStatus, "untried");
  assert.equal(page.count(), 2);
});

test("invalid or missing statuses never partially overwrite received evidence", async () => {
  const page = await surface(response("tried"));
  await page.refresh(async () => ({ok: true, json: async () => ({schema_version: 1, pipelines: {}})}));
  assert.equal(page.node.dataset.testStatus, "tried");
  assert.equal(page.unavailable.hidden, false);
  assert.equal(page.document.updates, 1);
});

test("an outage preserves the last status and shows its availability note", async () => {
  const page = await surface(response("agent"));
  await page.refresh(async () => { throw new Error("offline"); });
  assert.equal(page.node.dataset.testStatus, "agent");
  assert.equal(page.unavailable.hidden, false);
  assert.equal(page.document.documentElement.dataset.testingSource, "unavailable");
});

test("hidden pages do not poll and resume when visible", async () => {
  const page = await surface(response("tried"), true);
  assert.equal(page.count(), 0);
  page.document.hidden = false;
  await page.listeners.visibilitychange();
  assert.equal(page.count(), 1);
  assert.equal(page.node.dataset.testStatus, "tried");
});
