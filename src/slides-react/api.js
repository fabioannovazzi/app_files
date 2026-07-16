const defaultFetchOptions = {
  credentials: "include",
};

function delay(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function fetchJson(url, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const maxRetryCount = method === "GET" ? 4 : 0;
  let attempt = 0;
  while (true) {
    const response = await fetch(url, { ...defaultFetchOptions, ...options });
    if (!response.ok) {
      const isGatewayError = response.status === 502 || response.status === 503 || response.status === 504;
      if (isGatewayError && attempt < maxRetryCount) {
        const retryDelayMs = 500 * (attempt + 1);
        attempt += 1;
        await delay(retryDelayMs);
        continue;
      }
      const text = await response.text();
      let message = text || response.statusText || "Request failed";
      const trimmed = text.trim();
      const isHtmlError = trimmed.startsWith("<!doctype html") || trimmed.startsWith("<html");
      if (isHtmlError) {
        const fallback = response.statusText || "Request failed";
        message = `HTTP ${response.status}: ${fallback}`;
        if (isGatewayError) {
          message = "API temporarily unavailable (gateway error). Please retry in a few seconds.";
        }
      }
      try {
        const parsed = JSON.parse(text);
        message = parsed.detail || parsed.message || message;
      } catch (error) {
        // ignore parse errors
      }
      const err = new Error(message);
      err.status = response.status;
      throw err;
    }
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return response.json();
    }
    return {};
  }
}

export async function listDecks() {
  return fetchJson("/slides/decks");
}

export async function getDeck(deckId) {
  return fetchJson(`/slides/deck/${encodeURIComponent(deckId)}`);
}

export async function saveDeck(deckId, payload) {
  return fetchJson(`/slides/deck/${encodeURIComponent(deckId)}/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function normalizeSlide(slide = {}) {
  return {
    id: slide.id || "",
    titleHtml: slide.titleHtml || "",
    bodyHtml: slide.bodyHtml || "",
    notesHtml: slide.notesHtml || "",
    sourceHtml: slide.sourceHtml || "",
    fullHtml: slide.fullHtml || "",
    kind: slide.kind === "sectionHeader" ? "sectionHeader" : "normal",
    sectionId: slide.sectionId || null,
    subsectionId: slide.subsectionId || null,
  };
}

export function normalizeSection(section = {}) {
  const subsections = Array.isArray(section.subsections)
    ? section.subsections.map((sub) => ({
        id: sub.id || "",
        title: sub.title || "",
        startSlide: sub.startSlide || "",
      }))
    : [];
  return {
    id: section.id || "",
    title: section.title || "",
    startSlide: section.startSlide || "",
    subsections,
  };
}

export async function concatenateDecks(newDeckId, sourceDeckIds, options = {}) {
  const interleaveByIndex = Boolean(options.interleaveByIndex);
  const interleaveGuide =
    options.interleaveGuide === "longest" || options.interleaveGuide === "shortest"
      ? options.interleaveGuide
      : "first";
  const deleteSourceDecks = options.deleteSourceDecks !== false;
  const deleteMode = options.deleteMode === "archive" ? "archive" : "archive";
  return fetchJson("/slides/deck/concatenate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      newDeckId,
      sourceDeckIds,
      interleaveByIndex,
      interleaveGuide,
      deleteSourceDecks,
      deleteMode,
    }),
  });
}

export async function archiveDeck(deckId) {
  return fetchJson(`/slides/deck/${encodeURIComponent(deckId)}/archive`, {
    method: "POST",
  });
}

export async function listPptxTemplates() {
  return fetchJson("/slides/pptx-templates");
}

export async function uploadPptxTemplate(file, options = {}) {
  const formData = new FormData();
  formData.append("file", file, file.name);
  formData.append("setDefault", options.setDefault === false ? "false" : "true");
  return fetchJson("/slides/pptx-templates/upload", {
    method: "POST",
    body: formData,
  });
}

export async function setDefaultPptxTemplate(templateId) {
  return fetchJson("/slides/pptx-templates/default", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ templateId }),
  });
}

export async function importSlide(deckId, payload) {
  return fetchJson(`/slides/deck/${encodeURIComponent(deckId)}/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function uploadPdfDeck(deckId, file, options = {}) {
  const formData = new FormData();
  formData.append("deckId", deckId);
  formData.append("file", file, file.name);
  if (options.lang) {
    formData.append("lang", options.lang);
  }
  if (typeof options.runOcr === "boolean") {
    formData.append("runOcr", options.runOcr ? "true" : "false");
  }
  if (options.promptStyle) {
    formData.append("promptStyle", options.promptStyle);
  }
  if (options.pptxTemplateId) {
    formData.append("pptxTemplateId", options.pptxTemplateId);
  }
  if (options.useUniformTemplate) {
    formData.append("useUniformTemplate", "true");
  }
  return fetchJson("/slides/deck/upload-pdf", {
    method: "POST",
    body: formData,
  });
}

export async function requestDeckOcr(deckId, payload = {}) {
  return fetchJson(`/slides/deck/${encodeURIComponent(deckId)}/ocr`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function fetchDeckOcrAudit(deckId) {
  return fetchJson(`/slides/deck/${encodeURIComponent(deckId)}/ocr/audit`);
}

export async function fetchDeckOcrStatus(deckId) {
  return fetchJson(`/slides/deck/${encodeURIComponent(deckId)}/ocr/status`);
}

export async function fetchDeckOcrSlide(deckId, slideId) {
  return fetchJson(
    `/slides/deck/${encodeURIComponent(deckId)}/ocr/slides/${encodeURIComponent(slideId)}`
  );
}

export async function fetchDeckOcrAnalysis(deckId) {
  return fetchJson(`/slides/deck/${encodeURIComponent(deckId)}/ocr/analysis`);
}

export async function requestDeckLayout(deckId, payload = {}) {
  return fetchJson(`/slides/deck/${encodeURIComponent(deckId)}/layout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function startDeckLayout(deckId, payload = {}) {
  return fetchJson(`/slides/deck/${encodeURIComponent(deckId)}/layout/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function fetchDeckLayoutStatus(deckId) {
  return fetchJson(`/slides/deck/${encodeURIComponent(deckId)}/layout/status`);
}

export async function requestPrint(deckId) {
  return fetchJson(`/slides/deck/${encodeURIComponent(deckId)}/print`, { method: "POST" });
}

export async function pollPrint(jobId) {
  return fetchJson(`/slides/deck/print/${jobId}`);
}

export async function requestPptxExport(deckId, source = "rendered") {
  const normalizedSource = source === "template" ? "template" : "rendered";
  return fetchJson(
    `/slides/deck/${encodeURIComponent(deckId)}/export-pptx?source=${encodeURIComponent(
      normalizedSource,
    )}`,
    { method: "POST" },
  );
}

export async function pollPptxExport(jobId) {
  return fetchJson(`/slides/deck/export-pptx/${jobId}`);
}
