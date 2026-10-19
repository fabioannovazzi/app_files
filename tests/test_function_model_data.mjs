import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../static/shared/function-model-data.js', import.meta.url), 'utf8');
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.dataset = {}; this.textContent = ''; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this[name] = value; }
  text() { return this.textContent + this.children.map((child) => typeof child === 'string' ? child : child.text()).join(' '); }
}
async function render({ product = 'clara', requested = product, locale = 'it', host = '', catalogProduct = product, unavailable = false } = {}) {
  const main = new Element('main');
  const section = new Element('section');
  const html = { lang: locale };
  let changeLanguage;
  let ready;
  const completed = new Promise((resolve) => { ready = resolve; });
  const catalog = { schema_version: 1, product: catalogProduct, pages: { example: {
    status: 'relevant', role: 'workflow', contract_sha256: 'a'.repeat(64), runtime_profiles: ['openai-codex'],
    copy: { it: [`${product}: testo selezionato.\n\nLimiti osservati.`], en: [`${product}: selected text.`] },
  } } };
  const document = {
    currentScript: { src: 'https://local.invalid/static/shared/function-model-data.js' },
    documentElement: html, body: { dataset: { functionPage: 'example' } }, head: new Element('head'), readyState: 'complete',
    querySelector(selector) { return selector === 'main' ? main : selector === '[data-model-data-status]' ? section : null; },
    createElement: (tag) => new Element(tag), createTextNode: (text) => text,
    dispatchEvent() { ready(); },
  };
  vm.runInNewContext(source, {
    document, URL, URLSearchParams, window: { location: { pathname: '/static/shared/example/index.html', search: `?from=${requested}&host=${host}` } },
    MutationObserver: class { constructor(callback) { changeLanguage = callback; } observe() {} },
    CustomEvent: class {}, fetch: async (url) => ({ ok: !unavailable, json: async () => String(url).endsWith('/index.json') ? { schema_version: 1, pages: { example: [product] } } : catalog }),
  });
  await completed;
  return { main, section, language: (value) => { html.lang = value; changeLanguage(); } };
}
for (const product of ['vera', 'clara', 'lucia']) {
  test(`${product}: renders its reviewed copy, digest and report note`, async () => {
    const { main, section, language } = await render({ product });
    assert.equal(section.dataset.privacyProduct, product);
    assert.equal(section.dataset.privacyContract, 'a'.repeat(64));
    assert.match(section.text(), new RegExp(`${product}: testo selezionato`));
    assert.equal(main.children.at(-1), section);
    if (product === 'vera') {
      assert.doesNotMatch(section.text(), /ogni esecuzione sostanziale/);
    } else {
      assert.match(section.text(), /limiti di verifica/);
    }
    language('en');
    assert.match(section.text(), /selected text/);
    assert.doesNotMatch(section.text(), /testo selezionato/);
  });
}
test('unreviewed host receives a labelled placeholder', async () => {
  const { section } = await render({ host: 'cowork' });
  assert.equal(section.dataset.modelDataStatus, 'placeholder');
  assert.match(section.text(), /in preparazione/);
  assert.equal(section.dataset.privacyContract, undefined);
});
test('foreign product is never substituted for the selected product', async () => {
  const { section } = await render({ requested: 'lucia' });
  assert.equal(section.dataset.modelDataStatus, 'placeholder');
  assert.match(section.text(), /non è disponibile/);
  assert.doesNotMatch(section.text(), /testo selezionato/);
});
test('foreign catalog and failed retrieval cannot appear reviewed', async () => {
  const foreign = await render({ catalogProduct: 'vera' });
  const failed = await render({ unavailable: true });
  assert.equal(foreign.section.dataset.privacyContract, undefined);
  assert.equal(failed.section.dataset.privacyContract, undefined);
});
