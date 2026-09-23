import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const script = readFileSync(new URL('../static/js/hosted-interview.js', import.meta.url), 'utf8');

function browser({ storage = new Map(), status = 200, attempt = 'new-attempt' } = {}) {
  const elements = new Map();
  const requests = [];
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      textContent: '', disabled: false, listeners: {},
      classList: { add() {}, remove() {}, toggle() {} },
      addEventListener(type, fn) { this.listeners[type] = fn; },
    });
    return elements.get(id);
  };
  const track = { stop() {} };
  class Peer {
    listeners = {};
    connectionState = 'new';
    channel = { listeners: {}, addEventListener(type, fn) { this.listeners[type] = fn; } };
    addEventListener(type, fn) { this.listeners[type] = fn; }
    addTrack() {}
    createDataChannel() { return this.channel; }
    async createOffer() { return { sdp: 'offer' }; }
    async setLocalDescription() {}
    async setRemoteDescription() {}
    close() {
      this.connectionState = 'closed';
      this.channel.listeners.close?.();
      this.listeners.connectionstatechange?.();
    }
  }
  const window = {
    isSecureContext: true,
    sessionStorage: {
      getItem: key => storage.get(key),
      setItem: (key, value) => storage.set(key, value),
      removeItem: key => storage.delete(key),
    },
    clearInterval() {}, clearTimeout() {}, addEventListener() {},
    setTimeout: callback => setImmediate(callback),
  };
  vm.runInNewContext(script, {
    window, document: {
      body: { dataset: { token: 'synthetic-token', ready: 'true', language: 'it' } },
      getElementById: element, createElement: () => ({}),
    },
    navigator: { mediaDevices: { getUserMedia: async () => ({
      getAudioTracks: () => [track], getTracks: () => [track],
    }) } },
    RTCPeerConnection: Peer, console,
    fetch: async (url, options) => {
      requests.push({ url, payload: JSON.parse(options.body) });
      return { ok: status === 200, status, text: async () => 'active attempt',
        json: async () => ({ attempt_id: attempt, sdp: 'answer' }) };
    },
  });
  return {
    requests, element,
    async start() {
      element('startButton').listeners.click();
      // Drain promise continuations and delayed close events without real timers.
      for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve));
    },
  };
}

test('rejected startup retains useful error and never completes an unstarted attempt', async () => {
  const page = browser({ status: 409 });
  await page.start();
  assert.deepEqual(page.requests.map(r => r.url), ['/case-notes/api/interviews/synthetic-token/session']);
  assert.match(page.element('statusDetail').textContent, /precedente sessione/);
  assert.equal(page.element('startButton').disabled, false);
});

test('same-tab reload supplies the previous ID and stores the replacement', async () => {
  const storage = new Map();
  const first = browser({ storage, attempt: 'first-attempt' });
  await first.start();
  const reloaded = browser({ storage, attempt: 'second-attempt' });
  await reloaded.start();
  assert.equal(reloaded.requests[0].payload.replace_attempt_id, 'first-attempt');
  assert.equal(storage.get('hosted-interview-attempt:synthetic-token'), 'second-attempt');
});

test('another tab without the attempt ID does not claim replacement', async () => {
  const page = browser();
  await page.start();
  assert.equal(page.requests[0].payload.replace_attempt_id, '');
});
