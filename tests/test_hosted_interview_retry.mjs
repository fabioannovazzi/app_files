import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const script = readFileSync(new URL('../static/js/hosted-interview.js', import.meta.url), 'utf8');

function browser({ storage = new Map(), status = 200, attempt = 'new-attempt', mode = 'research_interview', blockedAudio = false, uploadResults = null } = {}) {
  const elements = new Map();
  const requests = [];
  const sent = [];
  const timers = new Map();
  let nextTimer = 0;
  const intervals = new Map();
  let microphoneSignal = 0;
  let now = Date.now();
  class Clock extends Date { static now() { return now; } }
  let peer;
  let recorder;
  class Recorder {
    constructor() { recorder = this; }
    mimeType = "audio/webm";
    listeners = {};
    addEventListener(type, fn) { this.listeners[type] = fn; }
    start() {}
    stop() { this.listeners.stop?.(); }
  }
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      textContent: '', disabled: false, listeners: {},
      classList: { add() {}, remove() {}, toggle() {} },
      addEventListener(type, fn) { this.listeners[type] = fn; },
    });
    return elements.get(id);
  };
  const track = { listeners: {}, stop() {}, addEventListener(type, fn) { this.listeners[type] = fn; } };
  const audio = { pause() {}, async play() { if (blockedAudio) throw Object.assign(new Error('blocked'), { name: 'NotAllowedError' }); } };
  const windowListeners = {};
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
    MediaRecorder: uploadResults ? Recorder : undefined,
    isSecureContext: true,
    sessionStorage: {
      getItem: key => storage.get(key),
      setItem: (key, value) => storage.set(key, value),
      removeItem: key => storage.delete(key),
    },
    AudioContext: class {
      async resume() {} async close() {}
      createAnalyser() { return { fftSize: 1024, getFloatTimeDomainData(samples) { samples.fill(microphoneSignal); } }; }
      createMediaStreamSource() { return { connect() {} }; }
    },
    clearInterval(id) { intervals.delete(id); }, setInterval(fn) { intervals.set(++nextTimer, fn); return nextTimer; }, addEventListener(type, fn) { windowListeners[type] = fn; },
    clearTimeout: id => timers.delete(id),
    setTimeout: callback => { timers.set(++nextTimer, callback); return nextTimer; },
  };
  vm.runInNewContext(script, {
    window, document: {
      body: { dataset: { token: 'synthetic-token', ready: 'true', language: 'it', mode } },
      getElementById: element, createElement: () => audio,
    },
    navigator: { mediaDevices: { getUserMedia: async () => ({
      getAudioTracks: () => [track], getTracks: () => [track],
    }) } },
    RTCPeerConnection: Peer, console, AbortController, Date: Clock,
    MediaRecorder: Recorder, MediaStream: class {}, FormData,
    fetch: async (url, options) => {
      if (url.endsWith('/audio-chunk')) {
        requests.push({ url, payload: Object.fromEntries(options.body) });
        const result = uploadResults.shift() ?? 200;
        if (result instanceof Error) throw result;
        return { ok: result === 200, status: result };
      }
      requests.push({ url, payload: JSON.parse(options.body) });
      return { ok: status === 200, status, text: async () => status === 200 ? JSON.stringify({status:'incomplete'}) : 'active attempt',
        json: async () => ({ attempt_id: attempt, sdp: 'answer' }) };
    },
  });
  return {
    requests, element, sent,
    recordChunk() { recorder.listeners.dataavailable({data: new Blob(["synthetic audio"], {type:"audio/webm"})}); },
    peerState(state) { peer.connectionState = state; peer.listeners.connectionstatechange(); },
    audioTrack() { peer.ontrack({ streams: [{}] }); },
    allowAudio() { blockedAudio = false; },
    hide() { windowListeners.pagehide(); },
    restore() { windowListeners.pageshow({ persisted: true }); },
    micEnded() { track.listeners.ended(); },
    microphoneSignal(value) { microphoneSignal = value; },
    tick(ms = 4000) { now += ms; for (const fn of intervals.values()) fn(); },
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

async function drain() {
  for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve));
}

test('transient disconnect preserves the conversation and cancels finalisation on recovery', async () => {
  const page = browser();
  await page.start(); page.open();
  page.peerState('disconnected');
  assert.match(page.element('statusDetail').textContent, /riconnetterci/);
  assert.equal(page.requests.some(r => r.url.endsWith('/complete')), false);
  page.peerState('connected'); page.settle(); await drain();
  assert.equal(page.requests.some(r => r.url.endsWith('/complete')), false);
  assert.equal(page.requests.filter(r => r.url.endsWith('/session')).length, 1);
  assert.equal(page.requests.some(r => r.payload.event_type === 'connection_recovered'), true);
});

test('persistent disconnection saves partial evidence and enables retry on the same link', async () => {
  const page = browser();
  await page.start(); page.open();
  page.peerState('disconnected'); page.settle(); await drain();
  page.settle(); await drain();
  const completion = page.requests.find(r => r.url.endsWith('/complete'));
  assert.equal(completion.payload.telemetry.completion_reason, 'connection_issue');
  assert.equal(page.element('startButton').disabled, false);
  assert.match(page.element('statusTitle').textContent, /interrotta/);
});

test('blocked speaker audio is visible and can be resumed with a user gesture', async () => {
  const page = browser({ blockedAudio: true });
  await page.start(); page.open(); page.audioTrack(); await drain(); page.tick();
  assert.match(page.element('statusDetail').textContent, /Attiva audio/);
  assert.equal(page.requests.some(r => r.payload.event_type === 'audio_playback_blocked'), true);
  page.allowAudio(); await page.element('enableAudioButton').listeners.click(); page.tick();
  assert.doesNotMatch(page.element('statusDetail').textContent, /Attiva audio/);
});

test('departure sends the attempt identifier for server-side partial finalisation', async () => {
  const page = browser();
  await page.start(); page.open(); page.hide();
  const departure = page.requests.find(r => r.payload.event_type === 'pagehide');
  assert.equal(departure.payload.attempt_id, 'new-attempt');
  assert.equal(departure.payload.payload.script_version, '20260924-audio-upload-retry-v1');
});


test('microphone level displays local signal energy without classifying answers', async () => {
  const page = browser();
  await page.start(); page.open(); page.tick();
  assert.equal(page.element('microphoneLevel').value, 0);
  page.microphoneSignal(0.1); page.tick();
  assert.ok(page.element('microphoneLevel').value > 0.7);
  assert.equal(page.requests.some(r => r.payload.event_type === 'microphone_level'), false);
});


test('returning from browser page cache does not leave a dead interview active', async () => {
  const page = browser();
  await page.start(); page.open(); page.hide(); page.restore();
  assert.equal(page.element('startButton').disabled, false);
  assert.match(page.element('statusDetail').textContent, /ricominciare/);
});

test('closing the page during manual saving still sends server recovery evidence', async () => {
  const page = browser();
  await page.start(); page.open();
  page.element('endButton').listeners.click(); page.hide();
  assert.equal(page.requests.some(r => r.payload.event_type === 'pagehide'), true);
});

test('a timed-out microphone chunk is retried with identical index and bytes', async () => {
  const page = browser({ uploadResults: [Object.assign(new Error('timeout'), {name:'AbortError'}), 200] });
  await page.start();
  page.recordChunk();
  await drain();
  page.settle();
  await drain();
  const uploads = page.requests.filter(r => r.url.endsWith('/audio-chunk'));
  assert.equal(uploads.length, 2);
  assert.equal(uploads[0].payload.chunk_index, '0');
  assert.equal(uploads[1].payload.chunk_index, '0');
  assert.equal(await uploads[0].payload.file.text(), await uploads[1].payload.file.text());
  assert.equal(page.requests.some(r => r.payload.event_type === 'audio_chunk_upload_error'), false);
});

test('permanent audio rejection is recorded without retrying', async () => {
  const page = browser({uploadResults:[409]});
  await page.start();
  page.recordChunk();
  await drain();
  assert.equal(page.requests.filter(r => r.url.endsWith('/audio-chunk')).length, 1);
  const failure = page.requests.find(r => r.payload.event_type === 'audio_chunk_upload_error');
  assert.equal(failure.payload.payload.chunk_index, 0);
});

test('repeated transient upload failure is bounded and recorded', async () => {
  const page = browser({uploadResults:[503,503,503]});
  await page.start();
  page.recordChunk();
  await drain(); page.settle(); await drain(); page.settle(); await drain();
  assert.equal(page.requests.filter(r => r.url.endsWith('/audio-chunk')).length, 3);
  assert.equal(page.requests.filter(r => r.payload.event_type === 'audio_chunk_upload_error').length, 1);
});
