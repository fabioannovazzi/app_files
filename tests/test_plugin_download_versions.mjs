import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

const script = readFileSync(new URL("../static/shared/plugin-download-versions.js", import.meta.url), "utf8");

async function render(product, response) {
  const labels = [{ tagName: "P", hidden: true }, { tagName: "SPAN", hidden: true }];
  const requests = [];
  runInNewContext(script, {
    document: {
      querySelectorAll: (selector) => selector === `[data-plugin-zip-version="${product}"]` ? labels : [],
    },
    fetch: async (url) => {
      requests.push(url);
      if (response instanceof Error) throw response;
      return { ok: true, json: async () => ({ name: product, version: "0.1.999" }), ...response };
    },
  });
  await new Promise(setImmediate);
  return { labels, requests };
}

for (const product of ["vera", "clara", "lucia"]) {
  test(`${product}: show the current ZIP version on the product page and guide`, async () => {
    const { labels, requests } = await render(product);
    assert.deepEqual(requests, [`https://raw.githubusercontent.com/fabioannovazzi/app_files/main/plugins/${product}/.codex-plugin/plugin.json`]);
    assert.equal(labels[0].textContent, "ZIP · v0.1.999");
    assert.equal(labels[1].textContent, " · v0.1.999");
    assert.equal(labels[0].hidden, false);
    assert.equal(labels[1].hidden, false);
  });
}

for (const [scenario, response] of [
  ["network failure", new Error("Offline")],
  ["HTTP failure", { ok: false, status: 404 }],
  ["wrong product", { json: async () => ({ name: "clara", version: "0.1.999" }) }],
  ["missing version", { json: async () => ({ name: "vera" }) }],
  ["malformed version", { json: async () => ({ name: "vera", version: "<b>latest</b>" }) }],
]) {
  test(`${scenario}: do not display an unverified version`, async () => {
    const { labels } = await render("vera", response);
    assert.equal(labels[0].hidden, true);
    assert.equal(labels[1].hidden, true);
    assert.equal(labels[0].textContent, undefined);
  });
}
