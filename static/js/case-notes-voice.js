(function () {
  let localStream;
  let screenStream;
  let microphoneStream;
  let lastTranscriptAt = null;
  let captureStartedAt = null;
  let captureStoppedAt = null;
  let bundleDownloadReady = false;
  let uploadInProgress = false;
  let activeUploadJobStatus = null;
  let audioContext = null;
  let mixedAudioContext = null;
  let mixedAudioNodes = [];
  let audioMonitorTimer = null;
  let audioMonitorBuffer = null;
  let liveAudioRecorder = null;
  let liveAudioMimeType = "";
  let liveAudioBlob = null;
  let liveVideoRecorder = null;
  let liveVideoMimeType = "";
  let liveVideoBlob = null;
  let realtimePc = null;
  let realtimeDc = null;
  let realtimeCommitTimer = null;
  let realtimeCallId = "";
  let realtimeSessionStatus = "not_started";
  let realtimeStartedAt = null;
  let realtimeStoppedAt = null;
  let realtimeWindowStartMs = 0;
  let realtimeCommitIndex = 0;
  let realtimeEventIndex = 0;
  let activeSlideCaptureTrack = null;
  let activeSlideCaptureListener = null;
  let activeSlideCaptureSupported = false;
  let activeSlideCaptureStatus = "not_started";
  let liveCaptureSourceMetadata = null;
  const realtimePendingCommits = [];
  const realtimeTimedSegments = [];
  const realtimeTranscriptionEvents = [];
  const activeSlideTimeline = [];
  const realtimeDeltaBuffers = new Map();
  let screenCaptureStartedAt = null;
  let screenCaptureStoppedAt = null;
  let screenCaptureMetadata = {};
  let screenCaptureReason = "";
  let captureAudioMetadata = {};
  let screenVisualMonitorTimer = null;
  let screenVisualCanvas = null;
  let previousScreenFingerprint = null;
  let lastAudioActiveAt = 0;
  let autoStopInProgress = false;
  let autoStopTriggered = false;
  const liveAudioChunks = [];
  const liveVideoChunks = [];
  const captureTelemetry = {
    audioSamples: 0,
    activeAudioSamples: 0,
    peakRms: 0,
  };
  const audioTelemetryIntervalMs = 250;
  const screenVisualSampleIntervalMs = 2000;
  const screenVisualDifferenceThreshold = 8;
  const screenVisualContentThreshold = 10;
  const audioActiveRmsThreshold = 0.006;
  const silenceAutoStopMs = 5 * 60 * 1000;
  const uploadJobPollMs = 2500;
  const maxUploadJobPolls = 1440;
  const audioUploadChunkBytes = 32 * 1024 * 1024;
  const realtimeCommitIntervalMs = 8000;
  const realtimeFinalCommitWaitMs = 5000;
  const realtimeFinalCommitPollMs = 100;
  let crc32Table = null;
  let screenVisualStats = createScreenVisualStats();

  const statusEl = document.getElementById("status");
  const userTranscript = document.getElementById("userTranscript");
  const transcriptPanels = document.getElementById("transcriptPanels");
  const monitorMode = document.getElementById("monitorMode");
  const monitorConnection = document.getElementById("monitorConnection");
  const monitorMicrophone = document.getElementById("monitorMicrophone");
  const monitorTranscript = document.getElementById("monitorTranscript");
  const monitorCapturedLabel = document.getElementById("monitorCapturedLabel");
  const monitorCaptured = document.getElementById("monitorCaptured");
  const connectButton = document.getElementById("connect");
  const stopButton = document.getElementById("stop");
  const screenPreviewPanel = document.getElementById("screenPreviewPanel");
  const screenPreview = document.getElementById("screenPreview");
  const screenPreviewStatus = document.getElementById("screenPreviewStatus");
  const audioFileInput = document.getElementById("audioFile");
  const audioFileName = document.getElementById("audioFileName");
  const languageSelect = document.getElementById("language");
  const uploadAudioButton = document.getElementById("uploadAudio");
  const sourceMetadataFields = {
    source_type: document.getElementById("sourceType"),
    title: document.getElementById("sourceTitle"),
    interview_date: document.getElementById("sourceDate"),
    participants: document.getElementById("sourceParticipants"),
    interviewer: document.getElementById("sourceInterviewer"),
    notes: document.getElementById("sourceNotes"),
  };
  const sourceIdentityFields = [
    sourceMetadataFields.source_type,
    sourceMetadataFields.title,
    sourceMetadataFields.interview_date,
    sourceMetadataFields.participants,
    sourceMetadataFields.interviewer,
    sourceMetadataFields.notes,
  ];
  const sessionToken = document.body.dataset.sessionToken || "";
  const sessionReady = document.body.dataset.sessionReady === "true";
  const transcriptionModel = document.body.dataset.transcriptionModel || "";
  const realtimeTranscriptionModel =
    document.body.dataset.realtimeTranscriptionModel || "gpt-realtime-whisper";
  if (stopButton) {
    stopButton.textContent = "Stop & download";
  }

  function setStatus(message) {
    statusEl.textContent = message;
  }

  function uploadProgressText(payload) {
    const percent = Number(payload?.progress_percent);
    if (Number.isFinite(percent)) {
      return `${Math.max(0, Math.min(100, Math.round(percent)))}%`;
    }
    const totalChunks = Number(payload?.total_chunks);
    if (Number.isFinite(totalChunks) && totalChunks > 0) {
      const completedChunks = Number(payload?.completed_chunks || 0);
      return `${Math.max(0, completedChunks)} / ${totalChunks} chunks`;
    }
    return "Running";
  }

  function uploadPhaseText(payload) {
    const label = String(payload?.phase_label || payload?.status || "File job").trim();
    const currentChunk = Number(payload?.current_chunk);
    const totalChunks = Number(payload?.total_chunks);
    if (
      Number.isFinite(currentChunk) &&
      currentChunk > 0 &&
      Number.isFinite(totalChunks) &&
      totalChunks > 0
    ) {
      return `${label} (${currentChunk}/${totalChunks})`;
    }
    return label;
  }

  function uploadStatusMessage(payload, fallback) {
    const message = String(payload?.message || fallback || "").trim();
    const progress = uploadProgressText(payload);
    if (message && progress !== "Running") {
      return `${message} ${progress}`;
    }
    return message || uploadPhaseText(payload);
  }

  function setUploadMonitor(payload) {
    activeUploadJobStatus = payload || {};
    if (monitorConnection) {
      monitorConnection.textContent =
        activeUploadJobStatus.status === "done" ? "Complete" : "File job";
    }
    if (monitorMicrophone) {
      monitorMicrophone.textContent = "Uploaded file";
    }
    if (monitorTranscript) {
      monitorTranscript.textContent = uploadPhaseText(activeUploadJobStatus);
    }
    if (monitorCapturedLabel) {
      monitorCapturedLabel.textContent = "Progress";
    }
    if (monitorCaptured) {
      monitorCaptured.textContent = uploadProgressText(activeUploadJobStatus);
    }
  }

  function setMonitor({ connection, microphone, transcript } = {}) {
    if (monitorMode) {
      monitorMode.textContent = "Transcription";
    }
    if (connection && monitorConnection) {
      monitorConnection.textContent = connection;
    }
    if (microphone && monitorMicrophone) {
      monitorMicrophone.textContent = microphone;
    }
    if (transcript && monitorTranscript) {
      monitorTranscript.textContent = transcript;
    }
    if (activeUploadJobStatus) {
      setUploadMonitor(activeUploadJobStatus);
      return;
    }
    if (monitorCapturedLabel) {
      monitorCapturedLabel.textContent = "Captured";
    }
    if (monitorCaptured) {
      const wordCount = userTranscript.value.split(/\s+/).filter(Boolean).length;
      const elapsed = secondsSinceCaptureStart();
      monitorCaptured.textContent = elapsed
        ? `${wordCount} words / ${elapsed}s`
        : `${wordCount} words`;
    }
  }

  function updateModeLayout() {
    transcriptPanels?.classList.add("is-hidden");
    transcriptPanels?.setAttribute("aria-hidden", "true");
    setScreenPreviewVisible(shouldShowScreenPreview());
    updateScreenPreviewStatus();
    setMonitor();
  }

  function restoreSelectPreference(select, storageKey) {
    if (!select) return;
    const preferredValue = window.localStorage.getItem(storageKey);
    if (
      preferredValue &&
      Array.from(select.options).some((option) => option.value === preferredValue)
    ) {
      select.value = preferredValue;
    }
    select.addEventListener("change", () => {
      window.localStorage.setItem(storageKey, select.value);
    });
  }

  function updateAudioFileName() {
    const file = audioFileInput?.files?.[0];
    audioFileName.textContent = file ? file.name : "No file selected";
    updateUploadButtonState();
  }

  function updateUploadButtonState() {
    const file = audioFileInput?.files?.[0];
    uploadAudioButton.disabled =
      !sessionReady || !file || uploadInProgress || !hasRequiredSourceMetadata();
  }

  function updateConnectButtonState() {
    const liveCaptureActive = Boolean(captureStartedAt && !captureStoppedAt);
    connectButton.disabled =
      !sessionReady ||
      !sessionToken ||
      liveCaptureActive ||
      !hasRequiredSourceMetadata();
  }

  function collectSourceMetadata() {
    return Object.fromEntries(
      Object.entries(sourceMetadataFields)
        .map(([key, field]) => [key, (field?.value || "").trim()])
        .filter(([, value]) => value)
    );
  }

  function missingRequiredSourceMetadataFields() {
    const requiredFields = [
      { field: sourceMetadataFields.title, label: "short title" },
      { field: sourceMetadataFields.participants, label: "at least one participant" },
    ];
    return requiredFields.filter(({ field }) => !(field?.value || "").trim());
  }

  function hasRequiredSourceMetadata() {
    return missingRequiredSourceMetadataFields().length === 0;
  }

  function updateRequiredSourceMetadataValidity() {
    const missingFields = new Set(
      missingRequiredSourceMetadataFields().map(({ field }) => field)
    );
    [sourceMetadataFields.title, sourceMetadataFields.participants].forEach((field) => {
      if (!field) return;
      field.setAttribute("aria-invalid", missingFields.has(field) ? "true" : "false");
    });
  }

  function updateSourceMetadataState() {
    updateRequiredSourceMetadataValidity();
    updateConnectButtonState();
    updateUploadButtonState();
  }

  function requiredSourceMetadataMessage(missingFields) {
    if (missingFields.length === 1) {
      return `Add ${missingFields[0].label} before recording or uploading.`;
    }
    return "Add a short title and at least one participant before recording or uploading.";
  }

  function validateRequiredSourceMetadata() {
    const missingFields = missingRequiredSourceMetadataFields();
    updateSourceMetadataState();
    if (!missingFields.length) return true;
    setStatus(requiredSourceMetadataMessage(missingFields));
    missingFields[0].field?.focus?.();
    return false;
  }

  function safeDownloadFilename(value, fallback) {
    const clean = String(value || "")
      .replace(/[\\/:*?"<>|]+/g, "-")
      .replace(/\s+/g, " ")
      .trim();
    return clean || fallback;
  }

  function audioExtensionForMimeType(mimeType) {
    const clean = String(mimeType || "").toLowerCase();
    if (clean.includes("mp4")) return "m4a";
    if (clean.includes("ogg")) return "ogg";
    if (clean.includes("wav")) return "wav";
    return "webm";
  }

  function videoExtensionForMimeType(mimeType) {
    const clean = String(mimeType || "").toLowerCase();
    if (clean.includes("mp4")) return "mp4";
    if (clean.includes("quicktime")) return "mov";
    return "webm";
  }

  function preferredAudioMimeType() {
    if (!window.MediaRecorder?.isTypeSupported) return "";
    return (
      [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/mp4",
        "audio/ogg;codecs=opus",
      ].find((mimeType) => window.MediaRecorder.isTypeSupported(mimeType)) || ""
    );
  }

  function preferredVideoMimeType() {
    if (!window.MediaRecorder?.isTypeSupported) return "";
    return (
      [
        "video/webm;codecs=vp8",
        "video/webm;codecs=vp9",
        "video/webm",
        "video/mp4",
      ].find((mimeType) => window.MediaRecorder.isTypeSupported(mimeType)) || ""
    );
  }

  function createLiveAudioFile() {
    if (!liveAudioBlob?.size) return null;
    const capturedAt = captureStoppedAt || new Date();
    const compactTimestamp = capturedAt.toISOString().replace(/[-:.]/g, "").slice(0, 15);
    const audioContentType = liveAudioBlob.type || liveAudioMimeType || "audio/webm";
    const extension = audioExtensionForMimeType(audioContentType);
    return new File(
      [liveAudioBlob],
      `case-notes-live-${compactTimestamp}.${extension}`,
      { type: audioContentType }
    );
  }

  function resetSourceIdentityFields() {
    sourceIdentityFields.forEach((field) => {
      if (field) {
        field.value = "";
      }
    });
  }

  function resetCaptureTelemetry() {
    stopActiveSlideTracking();
    captureStartedAt = null;
    captureStoppedAt = null;
    bundleDownloadReady = false;
    liveAudioBlob = null;
    liveAudioMimeType = "";
    liveVideoBlob = null;
    liveVideoMimeType = "";
    screenCaptureStartedAt = null;
    screenCaptureStoppedAt = null;
    screenCaptureMetadata = {};
    screenCaptureReason = "";
    captureAudioMetadata = {};
    liveAudioChunks.length = 0;
    liveVideoChunks.length = 0;
    stopButton.textContent = "Stop & download";
    captureTelemetry.audioSamples = 0;
    captureTelemetry.activeAudioSamples = 0;
    captureTelemetry.peakRms = 0;
    lastAudioActiveAt = 0;
    autoStopInProgress = false;
    autoStopTriggered = false;
    realtimeCallId = "";
    realtimeSessionStatus = "not_started";
    realtimeStartedAt = null;
    realtimeStoppedAt = null;
    realtimeWindowStartMs = 0;
    realtimeCommitIndex = 0;
    realtimeEventIndex = 0;
    realtimePendingCommits.length = 0;
    realtimeTimedSegments.length = 0;
    realtimeTranscriptionEvents.length = 0;
    realtimeDeltaBuffers.clear();
    activeSlideTimeline.length = 0;
    activeSlideCaptureSupported = false;
    activeSlideCaptureStatus = "not_started";
  }

  function secondsSinceCaptureStart(date = new Date()) {
    if (!captureStartedAt) return null;
    return Number(((date.getTime() - captureStartedAt.getTime()) / 1000).toFixed(2));
  }

  function markCaptureStarted(startedAt = new Date()) {
    captureStartedAt = startedAt;
    lastAudioActiveAt = captureStartedAt.getTime();
  }

  function stopAudioTelemetry() {
    window.clearInterval(audioMonitorTimer);
    audioMonitorTimer = null;
    audioMonitorBuffer = null;
    if (audioContext) {
      audioContext.close().catch((error) => {
        console.warn("Could not close audio telemetry context", error);
      });
    }
    audioContext = null;
  }

  function startAudioTelemetry(stream) {
    stopAudioTelemetry();
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass || !stream?.getAudioTracks().length) return;
    try {
      audioContext = new AudioContextClass();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 2048;
      audioMonitorBuffer = new Uint8Array(analyser.fftSize);
      source.connect(analyser);
      audioMonitorTimer = window.setInterval(() => {
        analyser.getByteTimeDomainData(audioMonitorBuffer);
        let sumSquares = 0;
        for (const value of audioMonitorBuffer) {
          const normalized = (value - 128) / 128;
          sumSquares += normalized * normalized;
        }
        const rms = Math.sqrt(sumSquares / audioMonitorBuffer.length);
        captureTelemetry.audioSamples += 1;
        if (rms > audioActiveRmsThreshold) {
          captureTelemetry.activeAudioSamples += 1;
          lastAudioActiveAt = Date.now();
        }
        captureTelemetry.peakRms = Math.max(captureTelemetry.peakRms, rms);
        maybeAutoStopOnSilence(Date.now());
      }, audioTelemetryIntervalMs);
    } catch (error) {
      console.warn("Audio telemetry unavailable", error);
      stopAudioTelemetry();
    }
  }

  function shouldShowScreenPreview() {
    return true;
  }

  function selectedLanguage() {
    return languageSelect?.value || "it";
  }

  function cleanTranscriptText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function appendTranscript(existing, addition) {
    const cleanExisting = String(existing || "").trim();
    const cleanAddition = cleanTranscriptText(addition);
    if (!cleanAddition) return cleanExisting;
    return cleanExisting ? `${cleanExisting}\n${cleanAddition}` : cleanAddition;
  }

  function sleep(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  function captureRelativeMs(date = new Date()) {
    if (!captureStartedAt) return null;
    return Math.max(0, Math.round(date.getTime() - captureStartedAt.getTime()));
  }

  function cleanActiveSlideField(value, maxLength) {
    return String(value || "").replace(/\s+/g, " ").trim().slice(0, maxLength);
  }

  function appendActiveSlideEvent(context, status) {
    const relativeMs = captureRelativeMs();
    if (relativeMs === null) return;
    const event = context
      ? {
          event_type: "active_slide",
          relative_ms: relativeMs,
          recorded_at: new Date().toISOString(),
          source: "capture_handle",
          slide_id: cleanActiveSlideField(context.slide_id, 120),
          slide_title: cleanActiveSlideField(context.slide_title, 240),
          slide_index: Number.isInteger(context.slide_index)
            ? context.slide_index
            : null,
          slide_number: Number.isInteger(context.slide_number)
            ? context.slide_number
            : null,
          deck_title: cleanActiveSlideField(context.deck_title, 160),
        }
      : {
          event_type: "slide_context_unavailable",
          relative_ms: relativeMs,
          recorded_at: new Date().toISOString(),
          source: "capture_handle",
          status,
          slide_id: "",
          slide_title: "",
        };
    const previous = activeSlideTimeline.at(-1);
    const identity = [
      event.event_type,
      event.slide_id,
      event.slide_title,
      event.slide_index,
      event.slide_number,
      event.deck_title,
      event.status,
    ].join("|");
    const previousIdentity = previous
      ? [
          previous.event_type,
          previous.slide_id,
          previous.slide_title,
          previous.slide_index,
          previous.slide_number,
          previous.deck_title,
          previous.status,
        ].join("|")
      : "";
    if (identity !== previousIdentity) {
      activeSlideTimeline.push(event);
    }
  }

  function recordActiveSlideFromCaptureHandle(track) {
    let captureHandle = null;
    try {
      captureHandle = track?.getCaptureHandle?.() || null;
    } catch (error) {
      activeSlideCaptureStatus = "read_error";
      appendActiveSlideEvent(null, activeSlideCaptureStatus);
      console.warn("Could not read active-slide metadata", error);
      return;
    }
    if (!captureHandle?.handle) {
      activeSlideCaptureStatus = "not_exposed";
      appendActiveSlideEvent(null, activeSlideCaptureStatus);
      return;
    }
    let payload = null;
    try {
      payload = JSON.parse(captureHandle.handle);
    } catch (error) {
      activeSlideCaptureStatus = "invalid_handle";
      appendActiveSlideEvent(null, activeSlideCaptureStatus);
      return;
    }
    if (payload?.source !== "clara_html_deck") {
      activeSlideCaptureStatus = "non_clara_surface";
      appendActiveSlideEvent(null, activeSlideCaptureStatus);
      return;
    }
    if (!payload.slide_id && !payload.slide_title) {
      activeSlideCaptureStatus = "missing_slide_identity";
      appendActiveSlideEvent(null, activeSlideCaptureStatus);
      return;
    }
    activeSlideCaptureStatus = "captured";
    appendActiveSlideEvent(payload, activeSlideCaptureStatus);
  }

  function stopActiveSlideTracking() {
    if (activeSlideCaptureTrack && activeSlideCaptureListener) {
      activeSlideCaptureTrack.removeEventListener(
        "capturehandlechange",
        activeSlideCaptureListener
      );
    }
    activeSlideCaptureTrack = null;
    activeSlideCaptureListener = null;
  }

  function startActiveSlideTracking(stream) {
    stopActiveSlideTracking();
    const track = stream?.getVideoTracks?.()[0];
    activeSlideCaptureSupported = Boolean(
      track && typeof track.getCaptureHandle === "function"
    );
    if (!activeSlideCaptureSupported) {
      activeSlideCaptureStatus = "unsupported";
      appendActiveSlideEvent(null, activeSlideCaptureStatus);
      return;
    }
    activeSlideCaptureTrack = track;
    activeSlideCaptureListener = () => recordActiveSlideFromCaptureHandle(track);
    track.addEventListener("capturehandlechange", activeSlideCaptureListener);
    recordActiveSlideFromCaptureHandle(track);
  }

  function activeSlideAt(relativeMs) {
    const targetMs = Number(relativeMs);
    if (!Number.isFinite(targetMs)) return null;
    let current = null;
    for (const event of activeSlideTimeline) {
      if (event.relative_ms > targetMs) break;
      current = event.event_type === "active_slide" ? event : null;
    }
    return current;
  }

  function timedTranscriptSegmentWithActiveSlide(segment) {
    const activeSlide = activeSlideAt(segment.start_ms ?? segment.end_ms);
    if (!activeSlide) return { ...segment };
    return {
      ...segment,
      active_slide_id: activeSlide.slide_id,
      active_slide_title: activeSlide.slide_title,
      active_slide_index: activeSlide.slide_index,
      active_slide_number: activeSlide.slide_number,
      active_deck_title: activeSlide.deck_title,
      active_slide_relative_ms: activeSlide.relative_ms,
    };
  }

  function activeSlideBundleFields() {
    const identifiedEvents = activeSlideTimeline.filter(
      (event) => event.event_type === "active_slide"
    );
    return {
      active_slide_capture: {
        strategy: "capture_handle",
        status: activeSlideCaptureStatus,
        supported: activeSlideCaptureSupported,
        clock: "milliseconds_since_capture_started_at",
        event_count: activeSlideTimeline.length,
        identified_event_count: identifiedEvents.length,
        note:
          "Cooperating Clara HTML decks expose the active slide mechanically. Screen video remains the fallback when the browser or captured surface does not expose it.",
      },
      active_slide_timeline: activeSlideTimeline.map((event) => ({ ...event })),
    };
  }

  function createScreenVisualStats() {
    return {
      sample_count: 0,
      contentful_samples: 0,
      changed_samples: 0,
      last_sampled_at: null,
      last_changed_at: null,
      last_difference: null,
      average_difference: null,
      average_luminance: null,
      status: "not_started",
      warning: "",
      error: "",
    };
  }

  function resetScreenVisualStats() {
    screenVisualStats = createScreenVisualStats();
    previousScreenFingerprint = null;
    liveCaptureSourceMetadata = null;
  }

  function screenVisualEvidenceMetadata() {
    return { ...screenVisualStats };
  }

  function setScreenPreviewStatus(message) {
    if (screenPreviewStatus) {
      screenPreviewStatus.textContent = message;
    }
  }

  function setScreenPreviewVisible(visible) {
    if (!screenPreviewPanel) return;
    screenPreviewPanel.classList.toggle("is-hidden", !visible);
    screenPreviewPanel.setAttribute("aria-hidden", visible ? "false" : "true");
  }

  function updateScreenPreviewStatus() {
    if (!shouldShowScreenPreview()) {
      setScreenPreviewStatus("No screen selected");
      return;
    }
    if (!screenStream?.getVideoTracks?.().length) {
      setScreenPreviewStatus("No screen selected");
      return;
    }
    if (screenVisualStats.error) {
      setScreenPreviewStatus("Screen preview unavailable");
      return;
    }
    if (!screenVisualStats.sample_count) {
      setScreenPreviewStatus("Waiting for screen preview");
      return;
    }
    if (!screenVisualStats.contentful_samples) {
      setScreenPreviewStatus("Screen captured: no visible content detected");
      return;
    }
    if (screenVisualStats.sample_count >= 3 && !screenVisualStats.changed_samples) {
      setScreenPreviewStatus("Screen captured: static");
      return;
    }
    setScreenPreviewStatus("Screen captured");
  }

  function stopScreenVisualMonitor() {
    if (screenVisualMonitorTimer) {
      window.clearInterval(screenVisualMonitorTimer);
      screenVisualMonitorTimer = null;
    }
  }

  function detachScreenPreview() {
    stopScreenVisualMonitor();
    if (screenPreview) {
      screenPreview.srcObject = null;
    }
    updateScreenPreviewStatus();
  }

  function screenFrameSampleSize(sourceWidth, sourceHeight) {
    const width = 64;
    const height = Math.max(
      1,
      Math.round(width * (sourceHeight || 9) / Math.max(1, sourceWidth || 16))
    );
    return { width, height };
  }

  function updateRollingAverage(previousAverage, sampleCount, value) {
    if (!Number.isFinite(value)) return previousAverage;
    if (previousAverage === null || sampleCount <= 1) return value;
    return previousAverage + (value - previousAverage) / sampleCount;
  }

  function sampleScreenPreviewFrame() {
    if (!screenPreview || !screenPreview.videoWidth || !screenPreview.videoHeight) {
      updateScreenPreviewStatus();
      return;
    }
    try {
      const { width, height } = screenFrameSampleSize(
        screenPreview.videoWidth,
        screenPreview.videoHeight
      );
      screenVisualCanvas ||= document.createElement("canvas");
      screenVisualCanvas.width = width;
      screenVisualCanvas.height = height;
      const context = screenVisualCanvas.getContext("2d", {
        willReadFrequently: true,
      });
      if (!context) {
        throw new Error("Could not read screen preview frames.");
      }
      context.drawImage(screenPreview, 0, 0, width, height);
      const data = context.getImageData(0, 0, width, height).data;
      const fingerprint = new Uint8Array(width * height);
      let minLuminance = 255;
      let maxLuminance = 0;
      let luminanceSum = 0;
      for (let index = 0; index < fingerprint.length; index += 1) {
        const offset = index * 4;
        const luminance = Math.round(
          (data[offset] * 0.2126) +
            (data[offset + 1] * 0.7152) +
            (data[offset + 2] * 0.0722)
        );
        fingerprint[index] = luminance;
        luminanceSum += luminance;
        minLuminance = Math.min(minLuminance, luminance);
        maxLuminance = Math.max(maxLuminance, luminance);
      }
      let difference = 0;
      if (previousScreenFingerprint?.length === fingerprint.length) {
        for (let index = 0; index < fingerprint.length; index += 1) {
          difference += Math.abs(fingerprint[index] - previousScreenFingerprint[index]);
        }
        difference /= fingerprint.length;
      }
      previousScreenFingerprint = fingerprint;
      const sampleCount = screenVisualStats.sample_count + 1;
      const differenceSampleCount = Math.max(1, screenVisualStats.sample_count);
      const sampledAt = new Date().toISOString();
      const luminance = luminanceSum / Math.max(1, fingerprint.length);
      const contentful = maxLuminance - minLuminance >= screenVisualContentThreshold;
      const changed =
        screenVisualStats.sample_count > 0 &&
        difference >= screenVisualDifferenceThreshold;
      screenVisualStats = {
        ...screenVisualStats,
        sample_count: sampleCount,
        contentful_samples:
          screenVisualStats.contentful_samples + (contentful ? 1 : 0),
        changed_samples: screenVisualStats.changed_samples + (changed ? 1 : 0),
        last_sampled_at: sampledAt,
        last_changed_at: changed ? sampledAt : screenVisualStats.last_changed_at,
        last_difference:
          screenVisualStats.sample_count > 0 ? Number(difference.toFixed(2)) : null,
        average_difference:
          screenVisualStats.sample_count > 0
            ? Number(
                updateRollingAverage(
                  screenVisualStats.average_difference,
                  differenceSampleCount,
                  difference
                ).toFixed(2)
              )
            : screenVisualStats.average_difference,
        average_luminance: Number(
          updateRollingAverage(
            screenVisualStats.average_luminance,
            sampleCount,
            luminance
          ).toFixed(2)
        ),
        status: contentful ? "contentful" : "blank",
        warning:
          sampleCount >= 3 && contentful && !screenVisualStats.changed_samples && !changed
            ? "screen_static"
            : "",
        error: "",
      };
    } catch (error) {
      screenVisualStats = {
        ...screenVisualStats,
        status: "not_verified",
        warning: "screen_preview_unavailable",
        error: error?.message || "Screen preview could not be sampled.",
      };
      stopScreenVisualMonitor();
    }
    screenCaptureMetadata = {
      ...screenCaptureMetadata,
      visual_evidence: screenVisualEvidenceMetadata(),
    };
    updateScreenPreviewStatus();
  }

  function attachScreenPreview(stream) {
    if (!screenPreview) return;
    setScreenPreviewVisible(true);
    setScreenPreviewStatus("Waiting for screen preview");
    screenPreview.srcObject = stream;
    screenPreview.play?.().catch(() => {
      setScreenPreviewStatus("Screen preview waiting for playback");
    });
    stopScreenVisualMonitor();
    sampleScreenPreviewFrame();
    screenVisualMonitorTimer = window.setInterval(
      sampleScreenPreviewFrame,
      screenVisualSampleIntervalMs
    );
  }

  function maybeAutoStopOnSilence(now) {
    if (!captureStartedAt || autoStopInProgress) return;
    const startedAt = captureStartedAt?.getTime() || now;
    const lastMeaningfulActivityAt = Math.max(startedAt, lastAudioActiveAt || 0);
    if (now - lastMeaningfulActivityAt < silenceAutoStopMs) return;
    autoStopInProgress = true;
    autoStopTriggered = true;
    setStatus("No audio detected for 5 minutes. Stopping and downloading...");
    stop({ auto: true }).catch((error) => {
      autoStopInProgress = false;
      setStatus(error.message);
    });
  }

  function cleanupCaptureStreams() {
    lastAudioActiveAt = 0;
    stopAudioTelemetry();
    detachScreenPreview();
    setMonitor({ connection: "Stopped", microphone: "Stopped" });
    window.clearInterval(realtimeCommitTimer);
    realtimeCommitTimer = null;
    realtimeDc?.close();
    realtimeDc = null;
    realtimePc?.close();
    realtimePc = null;
    stopActiveSlideTracking();
    localStream?.getTracks().forEach((track) => track.stop());
    localStream = null;
    microphoneStream?.getTracks().forEach((track) => track.stop());
    microphoneStream = null;
    screenStream?.getTracks().forEach((track) => track.stop());
    screenStream = null;
    if (mixedAudioContext) {
      mixedAudioContext.close().catch((error) => {
        console.warn("Could not close mixed audio context", error);
      });
    }
    mixedAudioContext = null;
    mixedAudioNodes = [];
  }

  function startLiveAudioRecording(stream, { required = false } = {}) {
    liveAudioBlob = null;
    liveAudioChunks.length = 0;
    liveAudioMimeType = "";
    if (!window.MediaRecorder) {
      const message = "Live audio recording is unavailable in this browser.";
      if (required) {
        throw new Error(message);
      }
      console.warn(message);
      return;
    }
    const audioTrack = stream?.getAudioTracks?.()[0];
    if (!audioTrack) {
      const message = "Live audio recording requires an audio track.";
      if (required) {
        throw new Error(message);
      }
      console.warn(message);
      return;
    }
    try {
      const mimeType = preferredAudioMimeType();
      const options = mimeType ? { mimeType } : undefined;
      const audioOnlyStream = new MediaStream([audioTrack]);
      liveAudioRecorder = new MediaRecorder(audioOnlyStream, options);
      liveAudioMimeType = liveAudioRecorder.mimeType || mimeType || "audio/webm";
      liveAudioRecorder.addEventListener("dataavailable", (event) => {
        if (event.data?.size) {
          liveAudioChunks.push(event.data);
        }
      });
      liveAudioRecorder.addEventListener("error", (event) => {
        console.warn("Live audio recording failed", event.error || event);
      });
      liveAudioRecorder.start(1000);
    } catch (error) {
      liveAudioRecorder = null;
      liveAudioChunks.length = 0;
      if (required) {
        throw new Error(error?.message || "Live audio recording could not start.");
      }
      console.warn("Live audio recording could not start", error);
    }
  }

  function stopLiveAudioRecording({ discard = false } = {}) {
    const recorder = liveAudioRecorder;
    if (!recorder) {
      if (discard) {
        liveAudioBlob = null;
        liveAudioChunks.length = 0;
      }
      return Promise.resolve(null);
    }
    return new Promise((resolve) => {
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        liveAudioRecorder = null;
        if (discard || !liveAudioChunks.length) {
          liveAudioBlob = null;
          liveAudioChunks.length = 0;
          resolve(null);
          return;
        }
        liveAudioBlob = new Blob(liveAudioChunks, {
          type: liveAudioMimeType || recorder.mimeType || "audio/webm",
        });
        liveAudioChunks.length = 0;
        resolve(liveAudioBlob);
      };
      recorder.addEventListener("stop", finish, { once: true });
      recorder.addEventListener(
        "error",
        (event) => {
          console.warn("Live audio recording failed", event.error || event);
          finish();
        },
        { once: true }
      );
      if (recorder.state === "inactive") {
        finish();
        return;
      }
      try {
        recorder.stop();
      } catch (error) {
        console.warn("Live audio recording could not stop cleanly", error);
        finish();
      }
      window.setTimeout(finish, 3000);
    });
  }

  function screenTrackMetadata(
    track,
    { required = false, captureReason = screenCaptureReason } = {}
  ) {
    const settings = track?.getSettings ? track.getSettings() : {};
    return {
      required,
      provenance_only: !required,
      capture_reason: captureReason || "",
      audio_source: "automatic",
      audio_sources: { ...captureAudioMetadata },
      started_at: screenCaptureStartedAt?.toISOString() || null,
      stopped_at: screenCaptureStoppedAt?.toISOString() || null,
      mime_type: liveVideoMimeType || "",
      width: settings.width || null,
      height: settings.height || null,
      frame_rate: settings.frameRate || null,
      display_surface: settings.displaySurface || "",
      logical_surface: settings.logicalSurface ?? null,
      cursor: settings.cursor || "",
      visual_evidence: screenVisualEvidenceMetadata(),
    };
  }

  function startLiveVideoRecording(
    stream,
    { required = false, captureReason = screenCaptureReason } = {}
  ) {
    liveVideoBlob = null;
    liveVideoChunks.length = 0;
    liveVideoMimeType = "";
    screenCaptureReason = captureReason || screenCaptureReason;
    if (!window.MediaRecorder) {
      const message =
        "Screen recording is unavailable because MediaRecorder is not available.";
      if (required) {
        throw new Error(
          "Screen recording is required but MediaRecorder is not available."
        );
      }
      console.warn(message);
      return;
    }
    const videoTrack = stream?.getVideoTracks?.()[0];
    if (!videoTrack) {
      const message = "Screen recording requires a display video track.";
      if (required) {
        throw new Error(message);
      }
      console.warn(message);
      return;
    }
    try {
      if (!screenCaptureStartedAt) {
        screenCaptureStartedAt = new Date();
      }
      const mimeType = preferredVideoMimeType();
      const options = mimeType ? { mimeType } : undefined;
      const videoOnlyStream = new MediaStream([videoTrack]);
      liveVideoRecorder = new MediaRecorder(videoOnlyStream, options);
      liveVideoMimeType = liveVideoRecorder.mimeType || mimeType || "video/webm";
      screenCaptureMetadata = screenTrackMetadata(videoTrack, {
        required,
        captureReason: screenCaptureReason,
      });
      liveVideoRecorder.addEventListener("dataavailable", (event) => {
        if (event.data?.size) {
          liveVideoChunks.push(event.data);
        }
      });
      liveVideoRecorder.addEventListener("error", (event) => {
        console.warn("Live screen recording failed", event.error || event);
      });
      videoTrack.addEventListener("ended", () => {
        screenCaptureStoppedAt = new Date();
        screenCaptureMetadata = screenTrackMetadata(videoTrack, {
          required,
          captureReason: screenCaptureReason,
        });
        if (!captureStoppedAt) {
          setStatus(
            "Screen sharing stopped. Press Stop & download to save the capture."
          );
        }
      });
      liveVideoRecorder.start(1000);
    } catch (error) {
      liveVideoRecorder = null;
      liveVideoChunks.length = 0;
      if (!required) {
        console.warn("Live screen recording could not start", error);
        return;
      }
      throw new Error(error?.message || "Screen recording could not start.");
    }
  }

  function stopLiveVideoRecording({ discard = false } = {}) {
    const recorder = liveVideoRecorder;
    if (!recorder) {
      if (discard) {
        liveVideoBlob = null;
        liveVideoChunks.length = 0;
      }
      return Promise.resolve(null);
    }
    return new Promise((resolve) => {
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        liveVideoRecorder = null;
        screenCaptureStoppedAt ||= new Date();
        if (discard || !liveVideoChunks.length) {
          liveVideoBlob = null;
          liveVideoChunks.length = 0;
          resolve(null);
          return;
        }
        liveVideoBlob = new Blob(liveVideoChunks, {
          type: liveVideoMimeType || recorder.mimeType || "video/webm",
        });
        liveVideoChunks.length = 0;
        const videoTrack = screenStream?.getVideoTracks?.()[0];
        screenCaptureMetadata = screenTrackMetadata(videoTrack, {
          required: Boolean(screenCaptureMetadata.required),
          captureReason: screenCaptureMetadata.capture_reason || screenCaptureReason,
        });
        resolve(liveVideoBlob);
      };
      recorder.addEventListener("stop", finish, { once: true });
      recorder.addEventListener(
        "error",
        (event) => {
          console.warn("Live screen recording failed", event.error || event);
          finish();
        },
        { once: true }
      );
      if (recorder.state === "inactive") {
        finish();
        return;
      }
      try {
        recorder.stop();
      } catch (error) {
        console.warn("Live screen recording could not stop cleanly", error);
        finish();
      }
      window.setTimeout(finish, 3000);
    });
  }

  function microphoneErrorMessage(error) {
    const name = error?.name || "";
    const message = error?.message || "";
    if (name === "NotAllowedError" || /permission denied/i.test(message)) {
      return [
        "Microphone blocked for this browser/site.",
        "In Chrome, allow Microphone for 127.0.0.1, then reload and start again.",
      ].join(" ");
    }
    if (name === "NotFoundError" || name === "DevicesNotFoundError") {
      return "No microphone was found by this browser.";
    }
    if (name === "NotReadableError" || name === "TrackStartError") {
      return "The microphone is already in use or cannot be opened by this browser.";
    }
    if (message) {
      return message;
    }
    return "Microphone access failed.";
  }

  function screenCaptureErrorMessage(error) {
    const name = error?.name || "";
    const message = error?.message || "";
    const prefix = name ? `${name}: ` : "";
    if (name === "NotAllowedError" || /permission denied|cancel/i.test(message)) {
      return "Screen sharing was not started. Choose the meeting or deck window and share it to record a live session.";
    }
    if (name === "InvalidStateError" || /invalid state/i.test(message)) {
      return `${prefix}Screen sharing must be started from the active Chrome tab. Click this Clara tab, then press Start again.`;
    }
    if (message) {
      return `${prefix}${message}`;
    }
    return "Screen sharing failed.";
  }

  async function assertMicrophonePermissionAvailable() {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("Microphone API is unavailable in this browser.");
    }
    if (!navigator.permissions?.query) {
      return;
    }
    try {
      const permission = await navigator.permissions.query({ name: "microphone" });
      if (permission.state === "denied") {
        throw new Error(
          "Microphone blocked for this browser/site. In Chrome, allow Microphone for 127.0.0.1, then reload and start again."
        );
      }
    } catch (error) {
      if (/Microphone blocked/.test(error?.message || "")) {
        throw error;
      }
    }
  }

  async function openMicrophoneStream() {
    await assertMicrophonePermissionAvailable();
    try {
      return await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    } catch (error) {
      throw new Error(microphoneErrorMessage(error));
    }
  }

  async function openOptionalMicrophoneStream() {
    try {
      return await openMicrophoneStream();
    } catch (error) {
      console.warn(
        "Microphone capture unavailable; continuing if screen audio exists",
        error
      );
      return null;
    }
  }

  async function openScreenCaptureStream() {
    if (!navigator.mediaDevices?.getDisplayMedia) {
      throw new Error("Screen capture is unavailable in this browser.");
    }
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        audio: true,
        video: true,
      });
      if (!stream.getVideoTracks().length) {
        stream.getTracks().forEach((track) => track.stop());
        throw new Error("Live capture requires a shared screen or browser tab.");
      }
      return stream;
    } catch (error) {
      if (/requires a shared screen/.test(error?.message || "")) {
        throw error;
      }
      throw new Error(screenCaptureErrorMessage(error));
    }
  }

  function audioStatusText(metadata = captureAudioMetadata) {
    const hasScreenAudio = Boolean(metadata.screen_audio_tracks);
    const hasMicrophone = Boolean(metadata.microphone_tracks);
    if (hasScreenAudio && hasMicrophone) {
      return "Screen audio + microphone active";
    }
    if (hasScreenAudio) {
      return "Screen audio active";
    }
    if (hasMicrophone) {
      return "Microphone active";
    }
    return "No audio";
  }

  function createMixedAudioStream(displayStream, micStream) {
    const screenAudioTracks = displayStream?.getAudioTracks?.() || [];
    const microphoneTracks = micStream?.getAudioTracks?.() || [];
    const allAudioTracks = [...screenAudioTracks, ...microphoneTracks];
    captureAudioMetadata = {
      mode: "screen_video_plus_auto_audio",
      audio_source: "automatic",
      screen_audio_tracks: screenAudioTracks.length,
      microphone_tracks: microphoneTracks.length,
      mixed_audio_tracks: 0,
      mixed: allAudioTracks.length > 1,
      screen_audio_present: screenAudioTracks.length > 0,
      microphone_present: microphoneTracks.length > 0,
    };
    if (!allAudioTracks.length) {
      throw new Error(
        "No audio was captured. Share a tab/window with audio or allow microphone access."
      );
    }
    if (allAudioTracks.length === 1) {
      captureAudioMetadata.mixed_audio_tracks = 1;
      return new MediaStream([allAudioTracks[0]]);
    }
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {
      throw new Error(
        "Live capture found multiple audio sources, but this browser cannot mix them."
      );
    }
    mixedAudioContext = new AudioContextClass();
    const destination = mixedAudioContext.createMediaStreamDestination();
    mixedAudioNodes = [];
    for (const track of allAudioTracks) {
      const source = mixedAudioContext.createMediaStreamSource(
        new MediaStream([track])
      );
      source.connect(destination);
      mixedAudioNodes.push(source);
    }
    captureAudioMetadata.mixed_audio_tracks =
      destination.stream.getAudioTracks().length;
    return destination.stream;
  }

  async function openLiveCaptureStreams() {
    const displayStream = await openScreenCaptureStream();
    screenStream = displayStream;
    const micStream = await openOptionalMicrophoneStream();
    try {
      localStream = createMixedAudioStream(displayStream, micStream);
    } catch (error) {
      micStream?.getTracks().forEach((track) => track.stop());
      screenStream?.getTracks().forEach((track) => track.stop());
      screenStream = null;
      throw error;
    }
    microphoneStream = micStream;
  }

  function recordRealtimeTranscriptionEvent(type, payload = {}) {
    const entry = {
      event_index: realtimeEventIndex,
      type,
      relative_ms: captureRelativeMs(),
      received_at: new Date().toISOString(),
      ...payload,
    };
    realtimeEventIndex += 1;
    realtimeTranscriptionEvents.push(entry);
    return entry;
  }

  function sendRealtimeClientEvent(payload) {
    if (!realtimeDc || realtimeDc.readyState !== "open") {
      return false;
    }
    try {
      realtimeDc.send(JSON.stringify(payload));
      return true;
    } catch (error) {
      recordRealtimeTranscriptionEvent("client_event_send_failed", {
        requested_type: payload?.type || "",
        message: error?.message || String(error),
      });
      return false;
    }
  }

  function commitRealtimeAudio(reason = "interval") {
    const endMs = captureRelativeMs();
    if (
      endMs === null ||
      !realtimeDc ||
      realtimeDc.readyState !== "open" ||
      endMs <= realtimeWindowStartMs + 250
    ) {
      return false;
    }
    const commit = {
      commit_index: realtimeCommitIndex,
      event_id: `clara_live_commit_${realtimeCommitIndex}`,
      start_ms: realtimeWindowStartMs,
      end_ms: endMs,
      reason,
      sent_at: new Date().toISOString(),
    };
    const sent = sendRealtimeClientEvent({
      type: "input_audio_buffer.commit",
      event_id: commit.event_id,
    });
    if (!sent) {
      return null;
    }
    realtimeCommitIndex += 1;
    realtimeWindowStartMs = endMs;
    realtimePendingCommits.push(commit);
    recordRealtimeTranscriptionEvent("input_audio_buffer.commit.sent", commit);
    return commit;
  }

  function startRealtimeCommitTimer() {
    window.clearInterval(realtimeCommitTimer);
    realtimeCommitTimer = window.setInterval(() => {
      commitRealtimeAudio("interval");
    }, realtimeCommitIntervalMs);
  }

  function noteRealtimeCommittedEvent(event) {
    const itemId = String(event.item_id || "").trim();
    const eventId = String(event.event_id || "").trim();
    const matchingCommit =
      realtimePendingCommits.find((commit) => commit.event_id === eventId) ||
      realtimePendingCommits.find((commit) => !commit.item_id);
    if (matchingCommit && itemId) {
      matchingCommit.item_id = itemId;
    }
    recordRealtimeTranscriptionEvent("input_audio_buffer.committed", {
      item_id: itemId,
      previous_item_id: String(event.previous_item_id || "").trim(),
      event_id: eventId,
    });
  }

  function claimRealtimeCommitForItem(itemId) {
    let commitIndex = realtimePendingCommits.findIndex(
      (commit) => commit.item_id && commit.item_id === itemId
    );
    if (commitIndex < 0) {
      commitIndex = realtimePendingCommits.findIndex((commit) => !commit.claimed);
    }
    if (commitIndex < 0) return null;
    const [commit] = realtimePendingCommits.splice(commitIndex, 1);
    commit.claimed = true;
    return commit;
  }

  function dropOldestPendingRealtimeCommit(reason) {
    if (!realtimePendingCommits.length) return null;
    const [commit] = realtimePendingCommits.splice(0, 1);
    recordRealtimeTranscriptionEvent("input_audio_buffer.commit.dropped", {
      commit_index: commit.commit_index,
      event_id: commit.event_id,
      reason,
    });
    return commit;
  }

  function hasPendingRealtimeCommit(commit) {
    if (!commit) return false;
    return realtimePendingCommits.some(
      (pendingCommit) => pendingCommit.commit_index === commit.commit_index
    );
  }

  async function waitForRealtimeCommitToResolve(commit) {
    if (!commit) return;
    const deadline = Date.now() + realtimeFinalCommitWaitMs;
    while (Date.now() < deadline) {
      if (!hasPendingRealtimeCommit(commit)) {
        recordRealtimeTranscriptionEvent("final_commit_resolved", {
          commit_index: commit.commit_index,
          wait_ms: Math.max(
            0,
            realtimeFinalCommitWaitMs - (deadline - Date.now())
          ),
        });
        return;
      }
      if (realtimeSessionStatus === "error") {
        break;
      }
      await sleep(realtimeFinalCommitPollMs);
    }
    recordRealtimeTranscriptionEvent("final_commit_wait_timeout", {
      commit_index: commit.commit_index,
      wait_ms: realtimeFinalCommitWaitMs,
      pending_commit_count: realtimePendingCommits.length,
    });
  }

  function handleRealtimeTranscriptionEvent(event) {
    const type = String(event.type || "");
    if (type === "input_audio_buffer.committed") {
      noteRealtimeCommittedEvent(event);
      return;
    }
    if (type === "conversation.item.input_audio_transcription.delta") {
      const itemId = String(event.item_id || "pending").trim() || "pending";
      const delta = String(event.delta || "");
      if (delta) {
        realtimeDeltaBuffers.set(itemId, `${realtimeDeltaBuffers.get(itemId) || ""}${delta}`);
      }
      recordRealtimeTranscriptionEvent(type, {
        item_id: itemId,
        content_index: event.content_index ?? null,
        delta,
      });
      setMonitor({ connection: "Recording", transcript: "Live transcript" });
      return;
    }
    if (type === "conversation.item.input_audio_transcription.completed") {
      const itemId = String(event.item_id || "").trim();
      const fallbackText = realtimeDeltaBuffers.get(itemId || "pending") || "";
      const transcript = cleanTranscriptText(event.transcript || fallbackText);
      realtimeDeltaBuffers.delete(itemId);
      realtimeDeltaBuffers.delete("pending");
      const commit = claimRealtimeCommitForItem(itemId);
      const receivedMs = captureRelativeMs();
      recordRealtimeTranscriptionEvent(type, {
        item_id: itemId,
        content_index: event.content_index ?? null,
        transcript,
        usage: event.usage || null,
        commit_index: commit?.commit_index ?? null,
      });
      if (!transcript) {
        return;
      }
      const segment = {
        segment_index: realtimeTimedSegments.length,
        start_ms: commit?.start_ms ?? receivedMs,
        end_ms: commit?.end_ms ?? receivedMs,
        speaker: "",
        text: transcript,
        item_id: itemId,
        commit_index: commit?.commit_index ?? null,
        source: "realtime_asr",
        timing_basis: commit ? "local_audio_commit_window" : "event_receive_time",
      };
      realtimeTimedSegments.push(segment);
      userTranscript.value = appendTranscript(userTranscript.value, transcript);
      lastTranscriptAt = new Date();
      setMonitor({ connection: "Recording", transcript: "Live timed transcript" });
      return;
    }
    if (type === "error") {
      const message = event.error?.message || "Realtime transcription error.";
      recordRealtimeTranscriptionEvent("error", {
        message,
        code: event.error?.code || "",
      });
      if (!/empty|buffer/i.test(message)) {
        realtimeSessionStatus = "error";
        setMonitor({ connection: "Recording", transcript: "Realtime issue" });
      } else {
        dropOldestPendingRealtimeCommit("empty_or_buffer_error");
      }
      return;
    }
    if (type) {
      recordRealtimeTranscriptionEvent(type, {
        item_id: String(event.item_id || "").trim(),
        response_id: String(event.response_id || "").trim(),
      });
    }
  }

  async function startRealtimeTranscription(stream) {
    realtimeSessionStatus = "starting";
    realtimeStartedAt = new Date();
    realtimeStoppedAt = null;
    realtimeWindowStartMs = captureRelativeMs(realtimeStartedAt) || 0;
    if (!window.RTCPeerConnection) {
      throw new Error("Realtime transcription requires WebRTC support.");
    }
    const audioTrack = stream?.getAudioTracks?.()[0];
    if (!audioTrack) {
      throw new Error("Realtime transcription requires an audio track.");
    }
    realtimePc = new RTCPeerConnection();
    realtimePc.addTrack(audioTrack, stream);
    realtimePc.addEventListener("connectionstatechange", () => {
      recordRealtimeTranscriptionEvent("peer_connection_state", {
        state: realtimePc?.connectionState || "",
      });
    });
    realtimeDc = realtimePc.createDataChannel("oai-events");
    realtimeDc.addEventListener("message", (message) => {
      try {
        handleRealtimeTranscriptionEvent(JSON.parse(message.data));
      } catch (error) {
        console.warn("Unparsed realtime transcription event", error);
      }
    });
    realtimeDc.addEventListener("open", () => {
      realtimeSessionStatus = "active";
      recordRealtimeTranscriptionEvent("data_channel_open", {
        commit_interval_ms: realtimeCommitIntervalMs,
      });
      startRealtimeCommitTimer();
      setMonitor({ connection: "Recording", transcript: "Live transcript active" });
    });
    realtimeDc.addEventListener("close", () => {
      if (realtimeSessionStatus === "active") {
        realtimeSessionStatus = "closed";
      }
      recordRealtimeTranscriptionEvent("data_channel_close");
    });
    realtimeDc.addEventListener("error", () => {
      realtimeSessionStatus = "error";
      recordRealtimeTranscriptionEvent("data_channel_error");
    });
    const offer = await realtimePc.createOffer();
    await realtimePc.setLocalDescription(offer);
    const response = await fetch("/case-notes/api/voice/realtime-transcription/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        launch_token: sessionToken,
        sdp: offer.sdp,
        language: selectedLanguage(),
      }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json();
    realtimeCallId = payload.call_id || "";
    await realtimePc.setRemoteDescription({ type: "answer", sdp: payload.sdp });
    recordRealtimeTranscriptionEvent("session_created", {
      call_id: realtimeCallId,
      transcription_model: payload.transcription_model || realtimeTranscriptionModel,
      transcription_delay: payload.transcription_delay || "",
    });
  }

  async function stopRealtimeTranscription({ discard = false } = {}) {
    window.clearInterval(realtimeCommitTimer);
    realtimeCommitTimer = null;
    if (!discard && realtimeDc?.readyState === "open") {
      const finalCommit = commitRealtimeAudio("stop");
      await waitForRealtimeCommitToResolve(finalCommit);
    }
    realtimeStoppedAt = new Date();
    realtimeDc?.close();
    realtimeDc = null;
    realtimePc?.close();
    realtimePc = null;
    if (discard) {
      realtimeSessionStatus = "discarded";
      realtimePendingCommits.length = 0;
      realtimeTimedSegments.length = 0;
      realtimeTranscriptionEvents.length = 0;
      realtimeDeltaBuffers.clear();
    } else if (
      realtimeSessionStatus !== "error" &&
      realtimeSessionStatus !== "not_started"
    ) {
      realtimeSessionStatus = "complete";
    }
  }

  function realtimeTranscriptText() {
    return realtimeTimedSegments
      .map((segment) => segment.text)
      .filter(Boolean)
      .join("\n");
  }

  function realtimeTranscriptionBundleFields(videoFileName = "") {
    if (
      realtimeSessionStatus === "not_started" &&
      !realtimeTimedSegments.length &&
      !realtimeTranscriptionEvents.length
    ) {
      return {};
    }
    return {
      realtime_transcription: {
        status: realtimeSessionStatus,
        model: realtimeTranscriptionModel,
        language: selectedLanguage(),
        call_id: realtimeCallId,
        started_at: realtimeStartedAt?.toISOString() || null,
        stopped_at: realtimeStoppedAt?.toISOString() || null,
        commit_strategy: "webrtc_audio_periodic_commit",
        commit_interval_ms: realtimeCommitIntervalMs,
        commit_count: realtimeCommitIndex,
        pending_commit_count: realtimePendingCommits.length,
        segment_count: realtimeTimedSegments.length,
        event_count: realtimeTranscriptionEvents.length,
      },
      realtime_user_transcript: realtimeTranscriptText(),
      timed_transcript_segments: realtimeTimedSegments.map(
        timedTranscriptSegmentWithActiveSlide
      ),
      realtime_transcription_events: realtimeTranscriptionEvents.map((event) => ({ ...event })),
      transcript_video_sync: {
        strategy: "capture_relative_ms",
        clock: "milliseconds_since_capture_started_at",
        video_file_name: videoFileName || "",
        segment_time_fields: ["start_ms", "end_ms"],
        active_slide_timeline_field: "active_slide_timeline",
        active_slide_time_field: "relative_ms",
        segment_slide_fields: ["active_slide_id", "active_slide_title"],
      },
    };
  }

  function downloadBlob(filename, blob) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    window.setTimeout(() => {
      link.remove();
      URL.revokeObjectURL(url);
    }, 60000);
  }

  function buildCrc32Table() {
    const table = new Uint32Array(256);
    for (let index = 0; index < 256; index += 1) {
      let value = index;
      for (let bit = 0; bit < 8; bit += 1) {
        value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
      }
      table[index] = value >>> 0;
    }
    return table;
  }

  function crc32(bytes) {
    crc32Table ||= buildCrc32Table();
    let crc = 0xffffffff;
    for (const byte of bytes) {
      crc = crc32Table[(crc ^ byte) & 0xff] ^ (crc >>> 8);
    }
    return (crc ^ 0xffffffff) >>> 0;
  }

  function zipDosDateTime(date = new Date()) {
    const year = Math.max(1980, date.getFullYear());
    return {
      time:
        (date.getHours() << 11) |
        (date.getMinutes() << 5) |
        Math.floor(date.getSeconds() / 2),
      date: ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate(),
    };
  }

  function writeZipHeaderValue(view, offset, byteLength, value) {
    if (byteLength === 2) {
      view.setUint16(offset, value, true);
      return;
    }
    view.setUint32(offset, value >>> 0, true);
  }

  async function zipEntryDataBytes(data) {
    if (data instanceof Blob) {
      return new Uint8Array(await data.arrayBuffer());
    }
    if (data instanceof Uint8Array) {
      return data;
    }
    return new TextEncoder().encode(String(data));
  }

  async function createZipBlob(entries) {
    const encoder = new TextEncoder();
    const localParts = [];
    const centralParts = [];
    const now = zipDosDateTime();
    let offset = 0;

    for (const entry of entries) {
      const nameBytes = encoder.encode(entry.name);
      const dataBytes = await zipEntryDataBytes(entry.data);
      if (
        nameBytes.length > 0xffff ||
        dataBytes.length > 0xffffffff ||
        offset > 0xffffffff
      ) {
        throw new Error("Voice bundle is too large for browser ZIP export.");
      }
      const checksum = crc32(dataBytes);
      const localHeader = new Uint8Array(30);
      const localView = new DataView(localHeader.buffer);
      writeZipHeaderValue(localView, 0, 4, 0x04034b50);
      writeZipHeaderValue(localView, 4, 2, 20);
      writeZipHeaderValue(localView, 6, 2, 0x0800);
      writeZipHeaderValue(localView, 8, 2, 0);
      writeZipHeaderValue(localView, 10, 2, now.time);
      writeZipHeaderValue(localView, 12, 2, now.date);
      writeZipHeaderValue(localView, 14, 4, checksum);
      writeZipHeaderValue(localView, 18, 4, dataBytes.length);
      writeZipHeaderValue(localView, 22, 4, dataBytes.length);
      writeZipHeaderValue(localView, 26, 2, nameBytes.length);
      writeZipHeaderValue(localView, 28, 2, 0);
      localParts.push(localHeader, nameBytes, dataBytes);

      const centralHeader = new Uint8Array(46);
      const centralView = new DataView(centralHeader.buffer);
      writeZipHeaderValue(centralView, 0, 4, 0x02014b50);
      writeZipHeaderValue(centralView, 4, 2, 20);
      writeZipHeaderValue(centralView, 6, 2, 20);
      writeZipHeaderValue(centralView, 8, 2, 0x0800);
      writeZipHeaderValue(centralView, 10, 2, 0);
      writeZipHeaderValue(centralView, 12, 2, now.time);
      writeZipHeaderValue(centralView, 14, 2, now.date);
      writeZipHeaderValue(centralView, 16, 4, checksum);
      writeZipHeaderValue(centralView, 20, 4, dataBytes.length);
      writeZipHeaderValue(centralView, 24, 4, dataBytes.length);
      writeZipHeaderValue(centralView, 28, 2, nameBytes.length);
      writeZipHeaderValue(centralView, 30, 2, 0);
      writeZipHeaderValue(centralView, 32, 2, 0);
      writeZipHeaderValue(centralView, 34, 2, 0);
      writeZipHeaderValue(centralView, 36, 2, 0);
      writeZipHeaderValue(centralView, 38, 4, 0);
      writeZipHeaderValue(centralView, 42, 4, offset);
      centralParts.push(centralHeader, nameBytes);

      offset += localHeader.length + nameBytes.length + dataBytes.length;
    }

    const centralOffset = offset;
    const centralSize = centralParts.reduce((total, part) => total + part.length, 0);
    if (
      entries.length > 0xffff ||
      centralOffset > 0xffffffff ||
      centralSize > 0xffffffff
    ) {
      throw new Error("Voice bundle is too large for browser ZIP export.");
    }
    const endRecord = new Uint8Array(22);
    const endView = new DataView(endRecord.buffer);
    writeZipHeaderValue(endView, 0, 4, 0x06054b50);
    writeZipHeaderValue(endView, 4, 2, 0);
    writeZipHeaderValue(endView, 6, 2, 0);
    writeZipHeaderValue(endView, 8, 2, entries.length);
    writeZipHeaderValue(endView, 10, 2, entries.length);
    writeZipHeaderValue(endView, 12, 4, centralSize);
    writeZipHeaderValue(endView, 16, 4, centralOffset);
    writeZipHeaderValue(endView, 20, 2, 0);
    return new Blob([...localParts, ...centralParts, endRecord], {
      type: "application/zip",
    });
  }

  async function downloadZipBundle(filename, entries) {
    downloadBlob(filename, await createZipBlob(entries));
  }

  function startCaptureStatus() {
    setStatus(
      "Recording live session with live timing. Clara will clean-transcribe the audio after you stop."
    );
    setMonitor({ connection: "Recording", microphone: audioStatusText() });
  }

  async function start() {
    if (!sessionReady || !sessionToken) {
      setStatus("Avvia questa sessione dal plugin Clara.");
      return;
    }
    if (!validateRequiredSourceMetadata()) {
      return;
    }
    if (!window.isSecureContext) {
      setStatus("Microphone access requires HTTPS, except on localhost.");
      return;
    }
    setStatus("Requesting screen and audio...");
    setMonitor({
      connection: "Starting",
      microphone: "Requesting screen and microphone",
    });
    connectButton.disabled = true;
    try {
      resetCaptureTelemetry();
      resetScreenVisualStats();
      liveCaptureSourceMetadata = collectSourceMetadata();
      await openLiveCaptureStreams();
      const audioTrack = localStream.getAudioTracks()[0];
      if (!audioTrack) {
        throw new Error("No audio track was available from the live capture.");
      }
      screenCaptureStartedAt = new Date();
      screenCaptureReason = "live_screen_context";
      attachScreenPreview(screenStream);
      startLiveVideoRecording(screenStream, {
        required: true,
        captureReason: "live_screen_context",
      });
      markCaptureStarted(screenCaptureStartedAt || new Date());
      startActiveSlideTracking(screenStream);
      try {
        await startRealtimeTranscription(localStream);
      } catch (error) {
        window.clearInterval(realtimeCommitTimer);
        realtimeCommitTimer = null;
        realtimeDc?.close();
        realtimeDc = null;
        realtimePc?.close();
        realtimePc = null;
        realtimeSessionStatus = "error";
        realtimeStoppedAt = new Date();
        recordRealtimeTranscriptionEvent("session_start_failed", {
          message: error?.message || String(error),
        });
        console.warn("Realtime transcription could not start", error);
        setMonitor({ transcript: "Realtime unavailable" });
      }
      startLiveAudioRecording(localStream, { required: true });
      startAudioTelemetry(localStream);
      setMonitor({ microphone: audioStatusText() });
      stopButton.disabled = false;
      startCaptureStatus();
    } catch (error) {
      await stopRealtimeTranscription({ discard: true });
      await stopLiveAudioRecording({ discard: true });
      await stopLiveVideoRecording({ discard: true });
      cleanupCaptureStreams();
      updateConnectButtonState();
      stopButton.disabled = true;
      setMonitor({ connection: "Not started", microphone: "Unavailable" });
      throw error;
    }
  }

  function hasDownloadableBundle() {
    return Boolean(
      captureStartedAt ||
        liveAudioBlob?.size ||
        liveVideoBlob?.size ||
        userTranscript.value.trim()
    );
  }

  function prepareBundleDownloadButton() {
    bundleDownloadReady = hasDownloadableBundle();
    stopButton.textContent = "Download bundle";
    stopButton.disabled = !bundleDownloadReady;
  }

  async function save() {
    if (!hasDownloadableBundle()) {
      setStatus("No captured session is available to download.");
      return false;
    }
    const capturedAt = new Date().toISOString();
    const stoppedAt = captureStoppedAt || capturedAt;
    const compactTimestamp = capturedAt.replace(/[-:.]/g, "").slice(0, 15);
    const audioContentType = liveAudioBlob?.type || liveAudioMimeType || "";
    const audioFileName = liveAudioBlob?.size
      ? `case-notes-voice-${compactTimestamp}.${audioExtensionForMimeType(audioContentType)}`
      : "";
    const videoContentType = liveVideoBlob?.type || liveVideoMimeType || "";
    const videoFileName = liveVideoBlob?.size
      ? `case-notes-screen-${compactTimestamp}.${videoExtensionForMimeType(videoContentType)}`
      : "";
    const elapsedSeconds =
      captureStartedAt && stoppedAt
        ? Number(
            (
              (new Date(stoppedAt).getTime() - captureStartedAt.getTime()) /
              1000
            ).toFixed(2)
          )
        : null;
    const sourceMetadata =
      liveCaptureSourceMetadata && Object.keys(liveCaptureSourceMetadata).length
        ? liveCaptureSourceMetadata
        : collectSourceMetadata();
    const bundle = {
      schema_version: 1,
      source: "case_notes_hosted_voice",
      captured_at: capturedAt,
      capture_started_at: captureStartedAt?.toISOString() || null,
      capture_stopped_at: stoppedAt,
      capture_elapsed_seconds: elapsedSeconds,
      language: selectedLanguage(),
      audio_file_name: audioFileName,
      audio_content_type: audioContentType,
      video_file_name: videoFileName,
      video_content_type: videoContentType,
      video_chunks: videoFileName ? 1 : 0,
      screen_capture_metadata: {
        ...screenCaptureMetadata,
        required: true,
        provenance_only: false,
        capture_reason:
          screenCaptureMetadata.capture_reason || "live_screen_context",
        audio_sources: { ...captureAudioMetadata },
        started_at: screenCaptureStartedAt?.toISOString() || null,
        stopped_at: screenCaptureStoppedAt?.toISOString() || null,
        visual_evidence: screenVisualEvidenceMetadata(),
      },
      source_metadata: sourceMetadata,
      model: transcriptionModel,
      transcription_model: transcriptionModel,
      capture_telemetry: {
        ...captureTelemetry,
        commit_strategy: realtimeTimedSegments.length
          ? "realtime_timing_plus_record_then_upload"
          : "record_then_upload",
        silence_auto_stop_ms: silenceAutoStopMs,
        auto_stop_triggered: autoStopTriggered,
        audio_active_rms_threshold: audioActiveRmsThreshold,
        audio_sample_interval_ms: audioTelemetryIntervalMs,
        active_audio_seconds: Number(
          (
            (captureTelemetry.activeAudioSamples * audioTelemetryIntervalMs) /
            1000
          ).toFixed(2)
        ),
        audio_sample_seconds: Number(
          (
            (captureTelemetry.audioSamples * audioTelemetryIntervalMs) /
            1000
          ).toFixed(2)
        ),
        active_audio_ratio: captureTelemetry.audioSamples
          ? Number(
              (
                captureTelemetry.activeAudioSamples / captureTelemetry.audioSamples
              ).toFixed(3)
            )
          : null,
        peak_rms: Number(captureTelemetry.peakRms.toFixed(5)),
        raw_chunk_count: 0,
        transcript_words: userTranscript.value.split(/\s+/).filter(Boolean).length,
        transcript_chars: userTranscript.value.length,
        audio_recording_bytes: liveAudioBlob?.size || 0,
        screen_video_bytes: liveVideoBlob?.size || 0,
        audio_sources: { ...captureAudioMetadata },
      },
      transcript_processing_note:
        "Hosted Voice Capture records live screen video and automatically captured audio mechanically. The server transcribes uploaded audio without speaker attribution; local Clara/Codex assigns speakers from the clean transcript, source metadata, and screen context after import.",
      ...realtimeTranscriptionBundleFields(videoFileName),
      ...activeSlideBundleFields(),
      user_transcript: userTranscript.value,
    };
    const jsonFileName = `case-notes-voice-${compactTimestamp}.json`;
    const zipEntries = [
      {
        name: jsonFileName,
        data: `${JSON.stringify(bundle, null, 2)}\n`,
      },
    ];
    if (audioFileName && liveAudioBlob) {
      zipEntries.push({ name: audioFileName, data: liveAudioBlob });
    }
    if (videoFileName && liveVideoBlob) {
      zipEntries.push({ name: videoFileName, data: liveVideoBlob });
    }
    await downloadZipBundle(`case-notes-voice-${compactTimestamp}.zip`, zipEntries);
    resetSourceIdentityFields();
    updateSourceMetadataState();
    setStatus("ZIP bundle downloaded. Import it from the Clara plugin.");
    return true;
  }

  function buildAudioUploadFormData(file, sourceMetadata = collectSourceMetadata()) {
    const formData = new FormData();
    formData.append("launch_token", sessionToken);
    formData.append("language", selectedLanguage());
    formData.append("source_metadata_json", JSON.stringify(sourceMetadata));
    formData.append("audio", file);
    return formData;
  }

  function buildChunkedUploadStartFormData(
    file,
    totalChunks,
    sourceMetadata = collectSourceMetadata()
  ) {
    const formData = new FormData();
    formData.append("launch_token", sessionToken);
    formData.append("language", selectedLanguage());
    formData.append("source_metadata_json", JSON.stringify(sourceMetadata));
    formData.append("filename", file.name || "audio-upload");
    formData.append("content_type", file.type || "application/octet-stream");
    formData.append("total_bytes", String(file.size || 0));
    formData.append("total_chunks", String(totalChunks));
    return formData;
  }

  async function jsonPayloadOrThrow(response) {
    if (!response.ok) {
      const error = new Error(await response.text());
      error.status = response.status;
      throw error;
    }
    return response.json();
  }

  async function submitSingleAudioUpload(file, sourceMetadata) {
    const response = await fetch("/case-notes/api/voice/upload", {
      method: "POST",
      body: buildAudioUploadFormData(file, sourceMetadata),
    });
    return jsonPayloadOrThrow(response);
  }

  async function submitChunkedAudioUpload(file, statusMessage, sourceMetadata) {
    const totalChunks = Math.ceil(file.size / audioUploadChunkBytes);
    const startResponse = await fetch("/case-notes/api/voice/upload/chunks/start", {
      method: "POST",
      body: buildChunkedUploadStartFormData(file, totalChunks, sourceMetadata),
    });
    const startPayload = await jsonPayloadOrThrow(startResponse);
    const uploadId = startPayload.upload_id;
    const chunkSize = startPayload.chunk_size || audioUploadChunkBytes;
    for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex += 1) {
      const start = chunkIndex * chunkSize;
      const end = Math.min(start + chunkSize, file.size);
      const chunk = file.slice(start, end, file.type || "application/octet-stream");
      const chunkFormData = new FormData();
      chunkFormData.append("chunk_index", String(chunkIndex));
      chunkFormData.append(
        "audio",
        chunk,
        `${file.name || "audio-upload"}.part-${chunkIndex + 1}`
      );
      const progress = Math.round((chunkIndex / totalChunks) * 100);
      setUploadMonitor({
        status: "uploading",
        phase_label: "Uploading file",
        message: statusMessage,
        progress_percent: progress,
        completed_chunks: chunkIndex,
        current_chunk: chunkIndex + 1,
        total_chunks: totalChunks,
      });
      setStatus(`${statusMessage} ${progress}%`);
      const chunkResponse = await fetch(
        `/case-notes/api/voice/upload/chunks/${encodeURIComponent(uploadId)}`,
        {
          method: "POST",
          body: chunkFormData,
        }
      );
      await jsonPayloadOrThrow(chunkResponse);
    }
    setUploadMonitor({
      status: "queued",
      phase_label: "Preparing transcription",
      message: "Upload complete. Preparing transcription...",
      progress_percent: 100,
      completed_chunks: totalChunks,
      total_chunks: totalChunks,
    });
    setStatus("Upload complete. Preparing transcription...");
    const finishResponse = await fetch(
      `/case-notes/api/voice/upload/chunks/${encodeURIComponent(uploadId)}/finish`,
      { method: "POST" }
    );
    return jsonPayloadOrThrow(finishResponse);
  }

  function shouldRetryUploadAsChunks(error, file) {
    if (!file?.size || file.size <= audioUploadChunkBytes) return false;
    // Ambiguous network/upstream failures may hide a successfully queued job.
    // Retry only when the server explicitly rejected the request body size.
    return error?.status === 413;
  }

  async function submitAudioUpload(
    file,
    statusMessage,
    { companionVideoBlob = null, sourceMetadata = null } = {}
  ) {
    const uploadSourceMetadata = sourceMetadata || collectSourceMetadata();
    uploadInProgress = true;
    updateUploadButtonState();
    setStatus(statusMessage);
    setUploadMonitor({
      status: "uploading",
      phase_label: "Uploading file",
      message: statusMessage,
      progress_percent: 0,
    });
    try {
      let payload;
      try {
        payload = await submitSingleAudioUpload(file, uploadSourceMetadata);
      } catch (error) {
        if (!shouldRetryUploadAsChunks(error, file)) {
          throw error;
        }
        const retryStatus = `${statusMessage} Retrying in upload parts...`;
        setStatus(retryStatus);
        payload = await submitChunkedAudioUpload(
          file,
          retryStatus,
          uploadSourceMetadata
        );
      }
      const bundle = payload.job_id
        ? await waitForUploadJob(payload.job_id, payload)
        : payload;
      await downloadAudioBundle(bundle, file, companionVideoBlob);
    } finally {
      uploadInProgress = false;
      updateUploadButtonState();
    }
  }

  async function uploadAudioFile() {
    if (!sessionReady || !sessionToken) {
      setStatus("Avvia questa sessione dal plugin Clara.");
      return;
    }
    if (!validateRequiredSourceMetadata()) {
      return;
    }
    const file = audioFileInput?.files?.[0];
    if (!file) {
      setStatus("Choose an audio file first.");
      return;
    }
    await submitAudioUpload(file, "Uploading audio...", {
      sourceMetadata: collectSourceMetadata(),
    });
  }

  async function uploadLiveAudioRecording() {
    if (!sessionReady || !sessionToken) {
      return false;
    }
    const file = createLiveAudioFile();
    if (!file) {
      return false;
    }
    await submitAudioUpload(file, "Uploading recorded audio for transcription...", {
      companionVideoBlob: liveVideoBlob,
      sourceMetadata: liveCaptureSourceMetadata || collectSourceMetadata(),
    });
    return true;
  }

  async function waitForUploadJob(jobId, initialPayload = null) {
    if (initialPayload) {
      setUploadMonitor({
        status: initialPayload.status || "queued",
        phase_label: "Queued",
        message:
          initialPayload.message ||
          "Upload received. Transcription is running in the background.",
        progress_percent: 0,
      });
      setStatus(
        uploadStatusMessage(
          initialPayload,
          "Audio uploaded. Transcription is running..."
        )
      );
    }
    for (let attempt = 0; attempt < maxUploadJobPolls; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, uploadJobPollMs));
      const response = await fetch(
        `/case-notes/api/voice/upload/${encodeURIComponent(jobId)}`,
        { cache: "no-store" }
      );
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const payload = await response.json();
      setUploadMonitor(payload);
      setStatus(
        uploadStatusMessage(
          payload,
          attempt
            ? "Transcription still running..."
            : "Audio uploaded. Transcription is running..."
        )
      );
      if (payload.status === "done") {
        ensureDownloadableAudioBundle(payload.bundle);
        return payload.bundle;
      }
      if (payload.status === "error") {
        throw new Error(payload.message || "Audio transcription failed.");
      }
    }
    throw new Error("Audio transcription is still running. Try again later.");
  }

  function ensureDownloadableAudioBundle(bundle) {
    const metadata = bundle?.transcription_metadata || {};
    const warnings = Array.isArray(metadata.warnings) ? metadata.warnings : [];
    const status = String(metadata.status || "").toLowerCase();
    if (!["complete", "warning"].includes(status) || metadata.coverage_complete !== true) {
      const firstWarning = warnings[0] ? ` ${warnings[0]}` : "";
      throw new Error(
        `Audio transcription did not pass coverage checks. No ZIP was downloaded.${firstWarning}`
      );
    }
  }

  function uploadCompletionStatus(bundle) {
    const metadata = bundle?.transcription_metadata || {};
    if (String(metadata.status || "").toLowerCase() === "warning") {
      return "Audio ZIP bundle downloaded with transcription warnings. Import it from the Clara plugin and review the warning metadata.";
    }
    return "Audio ZIP bundle downloaded. Transcription coverage checks passed. Import it from the Clara plugin.";
  }

  async function downloadAudioBundle(
    bundle,
    sourceAudioFile = null,
    companionVideoBlob = null
  ) {
    ensureDownloadableAudioBundle(bundle);
    const capturedAt = bundle.captured_at || new Date().toISOString();
    const compactTimestamp = capturedAt.replace(/[-:.]/g, "").slice(0, 15);
    const sourceAudioName = bundle.audio_file_name || sourceAudioFile?.name || "audio";
    const audioFileName = sourceAudioFile
      ? `case-notes-audio-${compactTimestamp}-${safeDownloadFilename(sourceAudioName, "audio")}`
      : bundle.audio_file_name || "";
    const videoContentType =
      companionVideoBlob?.type || liveVideoMimeType || "video/webm";
    const videoFileName = companionVideoBlob?.size
      ? `case-notes-screen-${compactTimestamp}.${videoExtensionForMimeType(videoContentType)}`
      : "";
    const elapsedSeconds =
      captureStartedAt && captureStoppedAt
        ? Number(
            (
              (captureStoppedAt.getTime() - captureStartedAt.getTime()) /
              1000
            ).toFixed(2)
          )
        : null;
    let downloadableBundle = sourceAudioFile
      ? {
          ...bundle,
          original_audio_file_name: bundle.audio_file_name || sourceAudioFile.name,
          audio_file_name: audioFileName,
          audio_content_type:
            sourceAudioFile.type || bundle.audio_content_type || "application/octet-stream",
        }
      : bundle;
    if (companionVideoBlob?.size && videoFileName) {
      downloadableBundle = {
        ...downloadableBundle,
        capture_started_at:
          downloadableBundle.capture_started_at ||
          captureStartedAt?.toISOString() ||
          null,
        capture_stopped_at:
          downloadableBundle.capture_stopped_at ||
          captureStoppedAt?.toISOString() ||
          null,
        capture_elapsed_seconds:
          downloadableBundle.capture_elapsed_seconds ?? elapsedSeconds,
        video_file_name: videoFileName,
        video_content_type: videoContentType,
        video_chunks: 1,
        ...realtimeTranscriptionBundleFields(videoFileName),
        ...activeSlideBundleFields(),
        screen_capture_metadata: {
          ...screenCaptureMetadata,
          required: true,
          provenance_only: false,
          capture_reason:
            screenCaptureMetadata.capture_reason ||
            "live_screen_context",
          audio_sources: { ...captureAudioMetadata },
          started_at: screenCaptureStartedAt?.toISOString() || null,
          stopped_at: screenCaptureStoppedAt?.toISOString() || null,
          visual_evidence: screenVisualEvidenceMetadata(),
        },
        capture_telemetry: {
          ...(downloadableBundle.capture_telemetry || {}),
          screen_video_bytes: companionVideoBlob.size,
          audio_sources: { ...captureAudioMetadata },
        },
        video_provenance_note:
          "Screen video was captured mechanically during live capture. Codex decides later whether the video is useful for deck revision or other context.",
      };
    }
    userTranscript.value = downloadableBundle.user_transcript || "";
    lastTranscriptAt = userTranscript.value.trim() ? new Date() : null;
    activeUploadJobStatus = null;
    setMonitor({
      connection: "Audio processed",
      microphone: companionVideoBlob?.size ? "Live capture" : "Uploaded file",
      transcript: lastTranscriptAt ? "Imported audio" : "None yet",
    });
    const jsonFileName = `case-notes-audio-${compactTimestamp}.json`;
    const zipEntries = [
      {
        name: jsonFileName,
        data: `${JSON.stringify(downloadableBundle, null, 2)}\n`,
      },
    ];
    if (sourceAudioFile && audioFileName) {
      zipEntries.push({ name: audioFileName, data: sourceAudioFile });
    }
    if (companionVideoBlob?.size && videoFileName) {
      zipEntries.push({ name: videoFileName, data: companionVideoBlob });
    }
    await downloadZipBundle(`case-notes-audio-${compactTimestamp}.zip`, zipEntries);
    resetSourceIdentityFields();
    updateSourceMetadataState();
    setStatus(uploadCompletionStatus(bundle));
  }

  async function stop({ auto = false } = {}) {
    if (auto) {
      autoStopTriggered = true;
    }
    captureStoppedAt = new Date();
    await stopRealtimeTranscription();
    await stopLiveAudioRecording();
    await stopLiveVideoRecording();
    cleanupCaptureStreams();
    updateConnectButtonState();
    prepareBundleDownloadButton();
    autoStopInProgress = false;
    if (liveAudioBlob?.size) {
      try {
        stopButton.disabled = true;
        if (await uploadLiveAudioRecording()) {
          prepareBundleDownloadButton();
          setStatus(
            auto
              ? "Stopped automatically after 5 minutes of silence. Audio ZIP bundle downloaded."
              : "Stopped. Audio ZIP bundle downloaded."
          );
          return;
        }
      } catch (error) {
        console.warn("Recorded audio transcription failed", error);
        prepareBundleDownloadButton();
        setStatus(
          `Recorded audio transcription failed. ${error.message} Use Download bundle to save the raw session.`
        );
        return;
      }
    }
    if (await save()) {
      setStatus(
        auto
          ? "Stopped automatically after 5 minutes of silence. ZIP bundle downloaded."
          : "Stopped. ZIP bundle downloaded."
      );
      return;
    }
    setStatus(
      auto
        ? "Stopped automatically after 5 minutes of silence. No transcript was captured."
        : "Stopped. No transcript was captured."
    );
  }

  connectButton.addEventListener("click", () => {
    start().catch((error) => setStatus(error.message));
  });
  stopButton.addEventListener("click", () => {
    if (bundleDownloadReady || captureStoppedAt) {
      save().catch((error) => setStatus(error.message));
      return;
    }
    stop().catch((error) => setStatus(error.message));
  });
  restoreSelectPreference(languageSelect, "clara.voice.language");
  audioFileInput.addEventListener("change", updateAudioFileName);
  uploadAudioButton.addEventListener("click", () => {
    uploadAudioFile().catch((error) => setStatus(error.message));
  });
  Object.values(sourceMetadataFields).forEach((field) => {
    field?.addEventListener("input", updateSourceMetadataState);
  });

  if (!sessionReady || !sessionToken) {
    connectButton.disabled = true;
    stopButton.disabled = true;
    audioFileInput.disabled = true;
    if (languageSelect) {
      languageSelect.disabled = true;
    }
    Object.values(sourceMetadataFields).forEach((field) => {
      if (field) {
        field.disabled = true;
      }
    });
    uploadAudioButton.disabled = true;
    setStatus("Avvia questa sessione dal plugin Clara.");
    setMonitor({ connection: "Unavailable", microphone: "Not requested" });
  }
  resetSourceIdentityFields();
  updateSourceMetadataState();
  updateModeLayout();
}());
