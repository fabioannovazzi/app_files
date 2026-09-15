// Execute the complete shipped widget script against a minimal host DOM.
// This regression harness is not a browser rendering or a learner approval.
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const html = fs.readFileSync(input.widget, 'utf8');
const script = html.match(/<script>([\s\S]*)<\/script>/)?.[1];
if (!script) throw new Error('Missing current widget script');
const elements = new Map();
function element(id = '') {
  return {
    id, textContent: '', innerHTML: '', className: '', value: '',
    disabled: false, style: {}, dataset: {}, addEventListener() {},
    appendChild() {}, remove() {}, select() {}, setAttribute() {},
    closest() { return null; },
  };
}
const document = {
  title: '', documentElement: {lang: 'en'}, body: element('body'),
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, element(id));
    return elements.get(id);
  },
  createElement(tag) { return element(tag); },
  execCommand() { return true; },
};
const context = {
  Blob, URL, URLSearchParams, console, document, navigator: {}, setTimeout, clearTimeout,
  input,
  window: {
    addEventListener() {}, location: {search: ''},
    openai: {toolOutput: input.payload, widgetState: null, setWidgetState() {}},
  },
};
vm.createContext(context);
const result = vm.runInContext(script + `
state.decisions = Object.fromEntries(input.decisions.map(d => [d.item_id, d]));
state.reviewerAlias = '';
let missingReviewer = '';
try { validateDecisionInputs(collectDecisionInputs()); }
catch (error) { missingReviewer = error.message; }
state.reviewerAlias = 'session_token=fixture';
let unsafeReviewer = '';
try { validateDecisionInputs(collectDecisionInputs()); }
catch (error) { unsafeReviewer = error.message; }
state.reviewerAlias = 'fictional-regression-reviewer';
validateDecisionInputs(collectDecisionInputs());
JSON.stringify({
  language: activeLanguage(), missingReviewer, unsafeReviewer,
  save: saveToolArgs(), apply: applyToolArgs(),
  firstItem: detailsHtml(items()[0]),
});`, context);
process.stdout.write(result);
