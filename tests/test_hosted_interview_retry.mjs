import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const script = readFileSync(new URL('../static/js/hosted-interview.js', import.meta.url), 'utf8');

function browser({ storage = new Map(), status = 200, attempt = 'new-attempt', mode = 'research_interview' } = {}) {
  const elements = new Map();
  const requests = [];
  const sent = [];
  const timers = new Map();
  let nextTimer = 0;
  let interval;
  let now = Date.now();
  class Clock extends Date { static now() { return now; } }
  let peer;
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
    constructor() { peer = this; }
    listeners = {};
    connectionState = 'new';
    channel = { listeners: {}, readyState: 'open', send: raw => sent.push(JSON.parse(raw)), addEventListener(type, fn) { this.listeners[type] = fn; } };
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
    clearInterval() {}, setInterval(fn) { interval = fn; }, addEventListener() {},
    clearTimeout: id => timers.delete(id),
    setTimeout: callback => { timers.set(++nextTimer, callback); return nextTimer; },
  };
  vm.runInNewContext(script, {
    window, document: {
      body: { dataset: { token: 'synthetic-token', ready: 'true', language: 'it', mode } },
      getElementById: element, createElement: () => ({}),
    },
    navigator: { mediaDevices: { getUserMedia: async () => ({
      getAudioTracks: () => [track], getTracks: () => [track],
    }) } },
    RTCPeerConnection: Peer, console, AbortController, Date: Clock,
    fetch: async (url, options) => {
      requests.push({ url, payload: JSON.parse(options.body) });
      return { ok: status === 200, status, text: async () => 'active attempt',
        json: async () => ({ attempt_id: attempt, sdp: 'answer' }) };
    },
  });
  return {
    requests, element, sent,
    tick(ms = 4000) { now += ms; interval?.(); },
    open() { peer.channel.listeners.open(); },
    receive(event) { peer.channel.listeners.message({ data: JSON.stringify(event) }); },
    settle() { for (const [id, callback] of [...timers]) { timers.delete(id); callback(); } },
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

function responseDone(page) {
  page.receive({ type: 'response.done', response: { status: 'completed' } });
}
function answer(page, transcript) {
  page.receive({ type: 'conversation.item.input_audio_transcription.completed', transcript });
}

test('follow-up uses the real conversation instead of replacing it with generic input', async () => {
  const page = browser();
  await page.start();
  page.open();
  responseDone(page);
  answer(page, 'Vorrei automatizzare il controllo delle scadenze con validazione umana.');
  page.settle();
  const responses = page.sent.filter(e => e.type === 'response.create');
  assert.equal(responses.length, 2);
  for (const response of responses) {
    assert.equal(Object.hasOwn(response.response, 'input'), false);
    assert.equal(Object.hasOwn(response.response, 'instructions'), false);
    assert.notEqual(response.response.conversation, 'none');
  }
  const direction = page.sent.at(-2);
  assert.equal(direction.type, 'conversation.item.create');
  assert.equal(direction.item.role, 'system');
  assert.match(direction.item.content[0].text, /latest interviewee answer/);
});

test('a transcript arriving during resumed speech waits and combines the answer into one follow-up', async () => {
  const page = browser();
  await page.start();
  page.open();
  responseDone(page);
  page.receive({ type: 'input_audio_buffer.speech_started' });
  answer(page, 'Vorrei un flusso di lavoro');
  page.settle();
  assert.equal(page.sent.filter(e => e.type === 'response.create').length, 1);
  page.receive({ type: 'input_audio_buffer.speech_stopped' });
  answer(page, 'per controllare le scadenze dello studio.');
  page.settle();
  assert.equal(page.sent.filter(e => e.type === 'response.create').length, 2);
});

test('rapid answer fragments queue one follow-up while an interviewer response is active', async () => {
  const page = browser();
  await page.start();
  page.open();
  answer(page, 'Il primo passaggio è importare i documenti.');
  answer(page, 'Poi li valido.');
  page.settle();
  assert.equal(page.sent.filter(e => e.type === 'response.create').length, 1);
  responseDone(page);
  assert.equal(page.sent.filter(e => e.type === 'response.create').length, 2);
});

test('bounded improvement follow-up also preserves conversation context', async () => {
  const page = browser({ mode: 'plugin_improvement_interview' });
  await page.start();
  page.open();
  responseDone(page);
  answer(page, 'Serve un elenco con le scadenze già ordinate.');
  page.settle();
  const responses = page.sent.filter(e => e.type === 'response.create');
  assert.equal(responses.length, 2);
  assert.equal(Object.hasOwn(responses[1].response, 'input'), false);
  assert.equal(responses[1].response.metadata.trigger, 'plugin_improvement_follow_up_or_close');
});


test('empty microphone transcription gives visible help and one contextual recovery, then resumes on clear speech', async () => {
  const page = browser();
  await page.start();
  page.open();
  responseDone(page);
  answer(page, '');
  assert.match(page.element('statusDetail').textContent, /Controlla il microfono/);
  page.tick();
  const recovery = page.sent.filter(e => e.type === 'response.create').at(-1);
  assert.equal(recovery.response.metadata.trigger, 'audio_transcription_recovery');
  assert.equal(Object.hasOwn(recovery.response, 'input'), false);
  responseDone(page);
  answer(page, '');
  page.tick(80000);
  assert.equal(page.sent.filter(e => e.type === 'response.create').length, 2);
  answer(page, 'Non ho ancora usato Vera.');
  page.settle();
  assert.equal(page.sent.filter(e => e.type === 'response.create').length, 3);
  assert.equal(page.sent.at(-1).response.metadata.trigger, 'interviewee_turn_completed');
});

test('empty input during the opening waits until the interviewer finishes instead of overlapping responses', async () => {
  const page = browser();
  await page.start();
  page.open();
  answer(page, '');
  page.tick();
  assert.equal(page.sent.filter(e => e.type === 'response.create').length, 1);
  responseDone(page);
  page.tick();
  assert.equal(page.sent.filter(e => e.type === 'response.create').length, 2);
});

test('failed transcription releases the pending input state and offers a retry', async () => {
  const page = browser();
  await page.start();
  page.open();
  responseDone(page);
  page.receive({ type: 'input_audio_buffer.speech_started' });
  page.receive({ type: 'input_audio_buffer.speech_stopped' });
  page.receive({ type: 'conversation.item.input_audio_transcription.failed', error: { code: 'transcription_error' } });
  page.tick();
  assert.equal(page.sent.at(-1).response.metadata.trigger, 'audio_transcription_recovery');
  assert.match(page.element('statusDetail').textContent, /Controlla il microfono/);
});
