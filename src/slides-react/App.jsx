import React, { useEffect, useMemo, useReducer } from "react";
import {
  NOTEBOOKLM_DEFAULT_STYLE_KEY,
  getNotebooklmFontStack,
  getNotebooklmStyle,
  resolveNotebooklmStyleKey,
} from "../shared/notebooklmStyle";
import {
  listDecks,
  listPptxTemplates,
  getDeck,
  saveDeck,
  normalizeSlide,
  normalizeSection,
  concatenateDecks,
  archiveDeck,
  uploadPdfDeck,
  uploadPptxTemplate,
  setDefaultPptxTemplate,
  importSlide as importSlideApi,
  requestPrint,
  pollPrint,
  requestPptxExport,
  pollPptxExport,
  fetchDeckOcrAudit,
  fetchDeckOcrStatus,
  requestDeckOcr,
  requestDeckLayout,
  startDeckLayout,
  fetchDeckLayoutStatus,
} from "./api";
import { pollPrintJob } from "./printJobs";

const VIEW_MODES = {
  LIST: "list",
  STORYBOARD: "storyboard",
};

const STORYBOARD_SCALE_MIN = 0.7;
const STORYBOARD_SCALE_MAX = 1.5;
const STORYBOARD_SCALE_STEP = 0.05;
const STORYBOARD_TWO_COLUMN_THRESHOLD = STORYBOARD_SCALE_MAX - STORYBOARD_SCALE_STEP / 2;
const STORYBOARD_TWO_COLUMN_MIN_WIDTH = "calc(50% - (var(--storyboard-gap) * 0.5))";

const NOTEBOOKLM_POINTS_PER_INCH = 72;
const NOTEBOOKLM_PIXELS_PER_INCH = 96;
const OCR_LANG_MAP = {
  en: "eng",
  it: "ita",
  fr: "fra",
  de: "deu",
};

const OCR_LANG_LABELS = {
  eng: "English",
  ita: "Italian",
  fra: "French",
  deu: "German",
};

function ptToPx(pt) {
  return (pt * NOTEBOOKLM_PIXELS_PER_INCH) / NOTEBOOKLM_POINTS_PER_INCH;
}

function buildPromptStyleContext(promptStyleKey) {
  const styleKey = resolveNotebooklmStyleKey(promptStyleKey || NOTEBOOKLM_DEFAULT_STYLE_KEY);
  const styleTokens = getNotebooklmStyle(styleKey);
  const fontStack = getNotebooklmFontStack(styleTokens);
  const titleSizePx = ptToPx(styleTokens.titleSizePt);
  const bodySizePx = ptToPx(styleTokens.bodySizePt);
  const introDateSizePx = Math.round(bodySizePx * 0.85);
  const containerStyle = `font-family: ${fontStack}; background-color: ${styleTokens.bgColor}; color: ${styleTokens.textColor};`;
  return {
    styleKey,
    styleTokens,
    fontStack,
    titleSizePx,
    bodySizePx,
    introDateSizePx,
    containerStyle,
  };
}

const INTRO_TITLE_PLACEHOLDER = "Client Name — Project Title";
const INTRO_SUBTITLE_PLACEHOLDER = "Subtitle or engagement description";
const INTRO_DATE_PLACEHOLDER = "Month YYYY";
const DISCLAIMER_PLACEHOLDER =
  "This presentation has been prepared for discussion purposes only. It contains confidential information and should not be distributed without prior written consent.";

function deckLooksPdfBased(slides = []) {
  return slides.some(
    (slide) =>
      (slide.bodyHtml || "").includes("data-pdf-crop-w-pt") ||
      (slide.bodyHtml || "").includes("data-pdf-rotation"),
  );
}

function countSlidesWithImages(slides = []) {
  return slides.reduce(
    (count, slide) => ((slide?.bodyHtml || "").includes("<img") ? count + 1 : count),
    0,
  );
}

function isImageBackedSlide(slide) {
  const bodyHtml = String(slide?.bodyHtml || "");
  if (!bodyHtml) return false;
  return (
    bodyHtml.includes("<img") ||
    bodyHtml.includes("data-pdf-crop-w-pt") ||
    bodyHtml.includes("data-pdf-rotation")
  );
}

const LAYOUT_BLOCK_COLORS = {
  title: "#d97706",
  text: "#2563eb",
  list: "#059669",
  table: "#7c3aed",
  figure: "#dc2626",
  footer: "#475569",
  header: "#0f766e",
  unknown: "#64748b",
};

function getLayoutBlockColor(type) {
  return LAYOUT_BLOCK_COLORS[String(type || "").trim().toLowerCase()] || LAYOUT_BLOCK_COLORS.unknown;
}

function extractPrimarySlideImageUrl(slide, deckId) {
  const bodyHtml = String(slide?.bodyHtml || "");
  if (!bodyHtml) return "";
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(bodyHtml, "text/html");
    const image = doc.querySelector("img");
    const src = String(image?.getAttribute("src") || "").trim();
    if (!src) return "";
    if (
      src.startsWith("data:") ||
      src.startsWith("http://") ||
      src.startsWith("https://") ||
      src.startsWith("/")
    ) {
      return src;
    }
    const baseHref = buildSlideAssetBaseHref(deckId, slide?.id || "");
    return `${baseHref}${src.replace(/^\.?\//, "")}`;
  } catch (error) {
    return "";
  }
}

function buildOcrPendingMessage({ builtPages, totalPages }) {
  const safeBuiltPages = Number.isFinite(builtPages) ? builtPages : 0;
  const safeTotalPages = Number.isFinite(totalPages) ? totalPages : 0;
  return (
    `Deck processing in progress (OCR). OCR pages done: ` +
    `${safeBuiltPages} of ${safeTotalPages}.`
  );
}

function buildDeckProcessingMessage(status, fallbackTotalPages) {
  const explicitMessage = String(status?.message || "").trim();
  if (explicitMessage) {
    return explicitMessage;
  }
  return buildOcrPendingMessage({
    builtPages: status?.builtPages,
    totalPages: status?.totalPages || fallbackTotalPages,
  });
}

function createEmptyOcrProgress() {
  return {
    active: false,
    deckId: "",
    lang: "",
    message: "",
    step: "",
    startedAt: "",
    updatedAt: "",
    lastCompletedStep: "",
  };
}

function buildDeckProgressState(deckId, status, fallbackTotalPages) {
  return {
    active: true,
    deckId,
    lang: String(status?.lang || "").trim(),
    message: buildDeckProcessingMessage(status, fallbackTotalPages),
    step: String(status?.step || "").trim(),
    startedAt: String(status?.startedAt || "").trim(),
    updatedAt: String(status?.updatedAt || "").trim(),
    lastCompletedStep: String(status?.lastCompletedStep || "").trim(),
  };
}

function formatOcrLanguageLabel(lang) {
  const normalized = String(lang || "").trim().toLowerCase();
  if (!normalized) return "";
  return OCR_LANG_LABELS[normalized] || normalized.toUpperCase();
}

function buildOcrLanguageDebugLabel(uiLang, backendLang) {
  const resolvedUiLang = resolveOcrLang(uiLang);
  const resolvedUiLabel = formatOcrLanguageLabel(resolvedUiLang);
  const resolvedBackendLabel = formatOcrLanguageLabel(backendLang);
  if (resolvedBackendLabel) {
    return `OCR language: ${resolvedBackendLabel}`;
  }
  if (resolvedUiLabel) {
    return `OCR language: ${resolvedUiLabel} (from page locale)`;
  }
  return "";
}

function formatDeckProcessingStep(step) {
  const normalized = String(step || "").trim().toLowerCase();
  if (!normalized) return "";
  if (normalized === "ocr") return "OCR";
  if (normalized === "layout") return "Layout";
  if (normalized === "complete") return "Complete";
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function formatRelativeAge(timestamp, nowMs) {
  const timestampMs = Date.parse(String(timestamp || ""));
  if (!Number.isFinite(timestampMs)) return "";
  const deltaSeconds = Math.max(0, Math.floor((nowMs - timestampMs) / 1000));
  if (deltaSeconds < 5) return "just now";
  if (deltaSeconds < 60) return `${deltaSeconds}s ago`;
  const deltaMinutes = Math.floor(deltaSeconds / 60);
  if (deltaMinutes < 60) return `${deltaMinutes}m ago`;
  const deltaHours = Math.floor(deltaMinutes / 60);
  return `${deltaHours}h ago`;
}

function buildNotebooklmCssVars(styleContext) {
  const { fontStack, titleSizePx, bodySizePx, styleTokens } = styleContext;
  return {
    "--notebooklm-bg-color": styleTokens.bgColor,
    "--notebooklm-text-color": styleTokens.textColor,
    "--notebooklm-font-stack": fontStack,
    "--notebooklm-title-size-px": `${titleSizePx}px`,
    "--notebooklm-body-size-px": `${bodySizePx}px`,
    "--notebooklm-line-height": `${styleTokens.lineHeight}`,
  };
}

function resolveOcrLang(lang) {
  if (!lang) return "eng";
  return OCR_LANG_MAP[lang.toLowerCase()] || "eng";
}

const NOTES_URL_REGEX = /(https?:\/\/[^\s<]+|www\.[^\s<]+)/gi;
const NOTES_OVERLAY_STYLE = [
  "position: absolute",
  "left: 32px",
  "right: 32px",
  "bottom: 0",
  "font-size: 12px",
  "line-height: 1.4",
  "color: #334155",
].join("; ");

function buildSlideAssetBaseHref(deckId, slideId) {
  if (!deckId) return "";
  const normalized = (slideId || "").replace(/\\/g, "/");
  const parts = normalized.split("/").filter(Boolean);
  const dirParts = parts.length > 1 ? parts.slice(0, -1) : [];
  const encodedDir = dirParts.map((part) => encodeURIComponent(part)).join("/");
  return `/slides/deck/${encodeURIComponent(deckId)}/assets/${encodedDir}${encodedDir ? "/" : ""}`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function normalizeNotesUrl(rawUrl) {
  if (!rawUrl) return null;
  if (rawUrl.startsWith("http://") || rawUrl.startsWith("https://")) {
    return rawUrl;
  }
  if (rawUrl.startsWith("www.")) {
    return `https://${rawUrl}`;
  }
  return null;
}

function buildNotesHtmlFromText(text) {
  if (!text) return "";
  const raw = String(text);
  const parts = [];
  let lastIndex = 0;
  NOTES_URL_REGEX.lastIndex = 0;
  let match = NOTES_URL_REGEX.exec(raw);
  while (match) {
    const url = match[0];
    const index = match.index ?? 0;
    const before = raw.slice(lastIndex, index);
    if (before) {
      parts.push(escapeHtml(before));
    }
    const normalized = normalizeNotesUrl(url);
    const label = escapeHtml(url);
    if (normalized) {
      parts.push(
        `<a href="${escapeHtml(normalized)}" target="_blank" rel="noopener noreferrer">${label}</a>`
      );
    } else {
      parts.push(label);
    }
    lastIndex = index + url.length;
    match = NOTES_URL_REGEX.exec(raw);
  }
  const tail = raw.slice(lastIndex);
  if (tail) {
    parts.push(escapeHtml(tail));
  }
  return parts.join("").replace(/\n/g, "<br />");
}

function extractNotesTextFromHtml(notesHtml) {
  if (!notesHtml) return "";
  const normalized = notesHtml.replace(/<br\s*\/?>/gi, "\n");
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(normalized, "text/html");
    return doc.body?.textContent || "";
  } catch (error) {
    return normalized;
  }
}

const initialState = (bootstrap) => ({
  loading: false,
  saving: false,
  uploading: false,
  uploadingPptxTemplate: false,
  concatenating: false,
  deleting: false,
  printing: false,
  printJobId: null,
  pptxExporting: false,
  pptxJobId: null,
  decks: [],
  pptxTemplates: [],
  defaultPptxTemplateId: null,
  currentDeckId: null,
  promptStyleKey: NOTEBOOKLM_DEFAULT_STYLE_KEY,
  uploadTemplateChoice: "",
  pendingUploadFile: null,
  pendingUploadDeckId: null,
  pendingUploadProcessingMode: "ocr",
  slides: [],
  sections: [],
  thumbnails: {},
  hasLayout: false,
  selectedSlideId: null,
  selectedSlideIds: [],
  selectionAnchorId: null,
  status: { message: "", isError: false },
  dirty: false,
  copy: bootstrap?.copy || {},
  storyboardScale: 1,
  previewConfig: {
    styles: mergeUnique(["/static/css/app.css"], bootstrap?.preview_styles || []),
    scripts: mergeUnique([], bootstrap?.preview_scripts || []),
    allowlist: bootstrap?.preview_allowlist || [],
  },
  pageLabel: bootstrap?.page_label || "Slide editor",
  viewMode: VIEW_MODES.LIST,
  lang: bootstrap?.lang || "en",
});

function reducer(state, action) {
  switch (action.type) {
    case "loading":
      return { ...state, loading: action.value };
    case "saving":
      return { ...state, saving: action.value };
    case "set_status":
      return { ...state, status: { message: action.message || "", isError: !!action.isError } };
    case "set_uploading":
      return { ...state, uploading: action.value };
    case "set_uploading_pptx_template":
      return { ...state, uploadingPptxTemplate: action.value };
    case "set_pptx_templates":
      return {
        ...state,
        pptxTemplates: action.templates || [],
        defaultPptxTemplateId: action.defaultTemplateId || null,
      };
    case "set_pending_upload":
      return {
        ...state,
        pendingUploadFile: action.file || null,
        pendingUploadDeckId: action.deckId || null,
        pendingUploadProcessingMode: action.processingMode || "ocr",
      };
    case "set_upload_template_choice":
      return { ...state, uploadTemplateChoice: action.value || "" };
    case "set_concatenating":
      return { ...state, concatenating: action.value };
    case "set_deleting":
      return { ...state, deleting: action.value };
    case "set_printing":
      return { ...state, printing: action.value, printJobId: action.jobId || null };
    case "set_pptx_exporting":
      return { ...state, pptxExporting: action.value, pptxJobId: action.jobId || null };
    case "set_decks":
      const decks = (action.decks || []).map((deck) => ({
        ...deck,
        promptStyle: resolveNotebooklmStyleKey(deck.promptStyle),
      }));
      return { ...state, decks };
    case "set_deck":
      const deckSlides = action.slides || [];
      const validSlideIds = new Set(deckSlides.map((slide) => slide.id));
      const requestedIds = action.selectedSlideIds || (action.selectedSlideId ? [action.selectedSlideId] : []);
      const filteredIds = requestedIds.filter((id) => validSlideIds.has(id));
      const defaultId = deckSlides.length ? deckSlides[0].id : null;
      const primaryId = validSlideIds.has(action.selectedSlideId)
        ? action.selectedSlideId
        : filteredIds.length
        ? filteredIds[filteredIds.length - 1]
        : defaultId;
      const anchorId = validSlideIds.has(action.selectionAnchorId)
        ? action.selectionAnchorId
        : primaryId;
      const promptStyleKey = resolveNotebooklmStyleKey(action.promptStyle || NOTEBOOKLM_DEFAULT_STYLE_KEY);
      const orderedSections = orderSectionsBySlides(action.sections || [], deckSlides);
      return {
        ...state,
        currentDeckId: action.deckId,
        promptStyleKey,
        slides: syncSectionHeaderSlides(deckSlides, orderedSections),
        sections: orderedSections,
        thumbnails: action.thumbnails || {},
        hasLayout: !!action.hasLayout,
        selectedSlideId: primaryId,
        selectedSlideIds: primaryId ? (filteredIds.length ? filteredIds : [primaryId]) : [],
        selectionAnchorId: anchorId,
        dirty: false,
      };
    case "select_slide":
      return {
        ...state,
        selectedSlideId: action.slideId || null,
        selectedSlideIds: action.slideId ? [action.slideId] : [],
        selectionAnchorId: action.slideId || null,
      };
    case "set_selection":
      return {
        ...state,
        selectedSlideId: action.primaryId || null,
        selectedSlideIds: action.ids || [],
        selectionAnchorId: action.anchorId || action.primaryId || null,
      };
    case "update_slide":
      return {
        ...state,
        slides: state.slides.map((slide) =>
          slide.id === action.slideId ? { ...slide, ...action.patch } : slide
        ),
        dirty: true,
      };
    case "set_slides":
      const syncedSlides = syncSectionHeaderSlides(action.slides || [], state.sections || []);
      return {
        ...state,
        slides: syncedSlides,
        dirty: true,
      };
    case "set_sections":
      const orderedSectionsForState = orderSectionsBySlides(action.sections || [], state.slides || []);
      return {
        ...state,
        sections: orderedSectionsForState,
        slides: syncSectionHeaderSlides(state.slides || [], orderedSectionsForState),
        dirty: true,
      };
    case "add_slide":
      return {
        ...state,
        slides: action.slides,
        selectedSlideId: action.newSlideId,
        selectedSlideIds: [action.newSlideId],
        selectionAnchorId: action.newSlideId,
        dirty: true,
      };
    case "delete_slides":
      return {
        ...state,
        slides: action.slides,
        selectedSlideId: action.nextSelection || null,
        selectedSlideIds: action.nextSelection ? [action.nextSelection] : [],
        selectionAnchorId: action.nextSelection || null,
        dirty: true,
      };
    case "set_view_mode":
      return { ...state, viewMode: action.mode };
    case "set_storyboard_scale":
      return { ...state, storyboardScale: action.scale };
    default:
      return state;
  }
}

function label(copy, key, fallback) {
  return copy?.labels?.[key] || fallback;
}

function tooltip(copy, key, fallback) {
  return copy?.tooltips?.[key] || fallback;
}

function applySelectionGesture(event, slideId, onSelectSingle, onToggleSelect, onRangeSelect) {
  if (event.shiftKey) {
    onRangeSelect(slideId);
  } else if (event.metaKey || event.ctrlKey) {
    onToggleSelect(slideId);
  } else {
    onSelectSingle(slideId);
  }
}

function templateChoiceForId(templateId) {
  const normalized = String(templateId || "").trim();
  return normalized ? `template:${normalized}` : "";
}

function templateIdFromChoice(choice) {
  const normalized = String(choice || "").trim();
  if (!normalized.startsWith("template:")) {
    return "";
  }
  return normalized.slice("template:".length).trim();
}

function resolveEffectiveUploadTemplateChoice(state) {
  const explicitChoice = String(state.uploadTemplateChoice || "").trim();
  if (explicitChoice) {
    return explicitChoice;
  }
  const defaultTemplateId = String(state.defaultPptxTemplateId || "").trim();
  if (defaultTemplateId) {
    return templateChoiceForId(defaultTemplateId);
  }
  return "uniform";
}

function mergeUnique(defaults, extras) {
  const seen = new Set();
  const merged = [];
  [...(defaults || []), ...(extras || [])].forEach((entry) => {
    const value = (entry || "").trim();
    if (!value || seen.has(value)) return;
    seen.add(value);
    merged.push(value);
  });
  return merged;
}

function getSlideIndex(slides, slideId) {
  return slides.findIndex((slide) => slide.id === slideId);
}

function compareBySlideStart(slides, leftStartSlide, rightStartSlide) {
  const leftIndex = getSlideIndex(slides, leftStartSlide);
  const rightIndex = getSlideIndex(slides, rightStartSlide);
  const leftMissing = leftIndex < 0;
  const rightMissing = rightIndex < 0;
  if (leftMissing && rightMissing) {
    return 0;
  }
  if (leftMissing) {
    return 1;
  }
  if (rightMissing) {
    return -1;
  }
  return leftIndex - rightIndex;
}

function getSectionAnchorIndex(slides, section) {
  const headerIndex = slides.findIndex(
    (slide) =>
      slide.kind === "sectionHeader" &&
      slide.sectionId === section?.id &&
      !slide.subsectionId
  );
  if (headerIndex >= 0) {
    return headerIndex;
  }
  return getSlideIndex(slides, section?.startSlide);
}

function getSubsectionAnchorIndex(slides, sectionId, subsection) {
  const headerIndex = slides.findIndex(
    (slide) =>
      slide.kind === "sectionHeader" &&
      slide.sectionId === sectionId &&
      slide.subsectionId === subsection?.id
  );
  if (headerIndex >= 0) {
    return headerIndex;
  }
  return getSlideIndex(slides, subsection?.startSlide);
}

function compareAnchorIndex(leftIndex, rightIndex) {
  const leftMissing = leftIndex < 0;
  const rightMissing = rightIndex < 0;
  if (leftMissing && rightMissing) {
    return 0;
  }
  if (leftMissing) {
    return 1;
  }
  if (rightMissing) {
    return -1;
  }
  return leftIndex - rightIndex;
}

function orderSectionsBySlides(sections, slides) {
  return [...(sections || [])]
    .map((section) => ({
      ...section,
      subsections: [...(section?.subsections || [])].sort((left, right) =>
        compareAnchorIndex(
          getSubsectionAnchorIndex(slides, section?.id, left),
          getSubsectionAnchorIndex(slides, section?.id, right)
        )
      ),
    }))
    .sort((left, right) =>
      compareAnchorIndex(
        getSectionAnchorIndex(slides, left),
        getSectionAnchorIndex(slides, right)
      )
    );
}

function buildSectionHeaderBodyHtml(sections, sectionId, subsectionId = null) {
  if (!sectionId) {
    return (
      '<section class="section-header">' +
      '<p class="section-header__placeholder">Define sections to see a preview.</p>' +
      "</section>"
    );
  }
  const sectionLookup = new Map((sections || []).map((section) => [section.id, section]));
  const currentSection = sectionLookup.get(sectionId);
  if (!currentSection) {
    return (
      '<section class="section-header">' +
      `<p class="section-header__placeholder">Unknown section ${escapeHtml(sectionId)}.</p>` +
      "</section>"
    );
  }
  const sectionItems = (sections || []).map((section) => {
    const isCurrent = section.id === sectionId;
    const sectionClasses = ["section-header__section"];
    if (isCurrent) {
      sectionClasses.push("is-current");
    }
    let subsectionMarkup = "";
    if (isCurrent && Array.isArray(section.subsections) && section.subsections.length) {
      const subsectionItems = section.subsections.map((subsection) => {
        const subsectionClasses = ["section-header__subsection"];
        if (subsection.id === subsectionId) {
          subsectionClasses.push("is-current");
        }
        return (
          `<li class="${subsectionClasses.join(" ")}">` +
          `${escapeHtml(subsection.title || subsection.id || "")}` +
          "</li>"
        );
      });
      subsectionMarkup = `<ul class="section-header__subsections">${subsectionItems.join("")}</ul>`;
    }
    return (
      `<li class="${sectionClasses.join(" ")}">` +
      `<span class="section-header__section-label">${escapeHtml(section.title || section.id || "")}</span>` +
      subsectionMarkup +
      "</li>"
    );
  });
  return (
    '<section class="section-header">' +
    '<link rel="stylesheet" href="./section_header.css" />' +
    `<ol class="section-header__sections">${sectionItems.join("")}</ol>` +
    "</section>"
  );
}

function inferSectionContextForHeader(slides, sections, slideIndex) {
  let nextContentId = "";
  for (let index = slideIndex + 1; index < slides.length; index += 1) {
    const candidate = slides[index];
    if (candidate?.kind !== "sectionHeader") {
      nextContentId = candidate?.id || "";
      break;
    }
  }
  if (!nextContentId) {
    return { sectionId: null, subsectionId: null };
  }
  for (const section of sections || []) {
    if (section?.startSlide === nextContentId) {
      return { sectionId: section.id || null, subsectionId: null };
    }
    for (const subsection of section?.subsections || []) {
      if (subsection?.startSlide === nextContentId) {
        return { sectionId: section.id || null, subsectionId: subsection.id || null };
      }
    }
  }
  return { sectionId: null, subsectionId: null };
}

function syncSectionHeaderSlides(slides, sections) {
  const orderedSections = orderSectionsBySlides(sections || [], slides || []);
  return (slides || []).map((slide, index) => {
    if (slide?.kind !== "sectionHeader") {
      return slide;
    }
    let sectionId = slide.sectionId || null;
    let subsectionId = slide.subsectionId || null;
    if (!sectionId) {
      const inferred = inferSectionContextForHeader(slides || [], orderedSections, index);
      sectionId = inferred.sectionId;
      subsectionId = inferred.subsectionId;
    } else if (!subsectionId) {
      const inferred = inferSectionContextForHeader(slides || [], orderedSections, index);
      if (inferred.sectionId === sectionId && inferred.subsectionId) {
        subsectionId = inferred.subsectionId;
      }
    }
    return {
      ...slide,
      sectionId,
      subsectionId,
      titleHtml: "",
      bodyHtml: buildSectionHeaderBodyHtml(orderedSections, sectionId, subsectionId),
      fullHtml: "",
    };
  });
}

function normalizeOverlayBbox(rawBbox) {
  if (!rawBbox || typeof rawBbox !== "object") {
    return null;
  }
  const x = Number(rawBbox.x);
  const y = Number(rawBbox.y);
  const w = Number(rawBbox.w);
  const h = Number(rawBbox.h);
  if (![x, y, w, h].every(Number.isFinite) || w <= 0 || h <= 0) {
    return null;
  }
  return { x, y, w, h };
}

function getOverlayBlockId(block) {
  const rawId = block?.blockId || block?.block_id || "";
  return String(rawId || "").trim();
}

function getOverlayBlockText(block) {
  const text = String(block?.text || "").trim();
  if (text) {
    return text;
  }
  const items = Array.isArray(block?.items)
    ? block.items.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  if (items.length) {
    return items.join(" | ");
  }
  return "";
}

function getOverlayLabelText(block) {
  const type = String(block?.type || "unknown").trim();
  const rawText = getOverlayBlockText(block);
  const normalizedText = rawText.replace(/\s+/g, " ").trim();
  if (!normalizedText) {
    return type;
  }
  const previewText =
    normalizedText.length > 220 ? `${normalizedText.slice(0, 217)}...` : normalizedText;
  return `${type} | ${previewText}`;
}

const EMPTY_SLIDE_HTML =
  "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\" /></head><body><div class=\"slide-container\"></div></body></html>";

function ensureSlideContainer(doc) {
  if (!doc) return null;
  let container = doc.querySelector(".slide-container");
  if (container) return container;
  const body = doc.body || doc.documentElement;
  if (!body) return null;
  container = doc.createElement("div");
  container.className = "slide-container";
  while (body.firstChild) {
    container.appendChild(body.firstChild);
  }
  body.appendChild(container);
  return container;
}

function buildIntroSlideFullHtml(titleHtml, bodyHtml, styleContext) {
  const context = styleContext || buildPromptStyleContext(NOTEBOOKLM_DEFAULT_STYLE_KEY);
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(EMPTY_SLIDE_HTML, "text/html");
    const container = ensureSlideContainer(doc);
    if (!container) return "";
    container.setAttribute("style", context.containerStyle);
    container.innerHTML = "";
    const titleEl = doc.createElement("h1");
    titleEl.className = "slide-title";
    titleEl.setAttribute("data-role", "title");
    titleEl.innerHTML = titleHtml || "";
    const bodyEl = doc.createElement("div");
    bodyEl.className = "slide-body";
    bodyEl.innerHTML = bodyHtml || "";
    container.appendChild(titleEl);
    container.appendChild(bodyEl);
    return "<!DOCTYPE html>\n" + doc.documentElement.outerHTML;
  } catch (error) {
    return "";
  }
}

function normalizeEditorSlide(slide) {
  const normalized = normalizeSlide(slide);
  const notesText = extractNotesTextFromHtml(normalized.notesHtml);
  return {
    ...normalized,
    notesText,
  };
}

function nextSlideId(slides) {
  const pattern = /^slide(\d+)\.html$/i;
  let max = -1;
  slides.forEach((slide) => {
    const match = pattern.exec(slide.id || "");
    if (match) {
      const value = parseInt(match[1], 10);
      if (!Number.isNaN(value)) {
        max = Math.max(max, value);
      }
    }
  });
  return `slide${max + 1}.html`;
}

function nextSlideIds(slides, count) {
  const pattern = /^slide(\d+)\.html$/i;
  let max = -1;
  slides.forEach((slide) => {
    const match = pattern.exec(slide.id || "");
    if (match) {
      const value = parseInt(match[1], 10);
      if (!Number.isNaN(value)) {
        max = Math.max(max, value);
      }
    }
  });
  return Array.from({ length: count }, (_, index) => `slide${max + index + 1}.html`);
}

function buildTitleSlideContent(styleContext) {
  const context = styleContext || buildPromptStyleContext(NOTEBOOKLM_DEFAULT_STYLE_KEY);
  const { fontStack, titleSizePx, bodySizePx, introDateSizePx, styleTokens } = context;
  const textColor = styleTokens.textColor;
  const titleStyle = [
    `color: ${textColor}`,
    `font-family: ${fontStack}`,
    `font-size: ${titleSizePx}px`,
    `line-height: ${styleTokens.lineHeight}`,
    "font-weight: 600",
  ].join("; ");
  const metaStyle = [
    "display: flex",
    "flex-direction: column",
    "gap: 12px",
    `color: ${textColor}`,
    `font-family: ${fontStack}`,
    `font-size: ${bodySizePx}px`,
    `line-height: ${styleTokens.lineHeight}`,
  ].join("; ");
  const dateStyle = [`font-size: ${introDateSizePx}px`, `color: ${textColor}`].join("; ");
  return {
    titleHtml: `<span class="deck-title__title" style="${titleStyle}">${INTRO_TITLE_PLACEHOLDER}</span>`,
    bodyHtml: `
      <div class="deck-title__meta" style="${metaStyle}">
        <div class="deck-title__subtitle">${INTRO_SUBTITLE_PLACEHOLDER}</div>
        <div class="deck-title__date" style="${dateStyle}">${INTRO_DATE_PLACEHOLDER}</div>
      </div>
    `.trim(),
  };
}

function buildDisclaimerSlideContent(styleContext) {
  const context = styleContext || buildPromptStyleContext(NOTEBOOKLM_DEFAULT_STYLE_KEY);
  const { fontStack, titleSizePx, bodySizePx, styleTokens } = context;
  const textColor = styleTokens.textColor;
  const titleStyle = [
    `color: ${textColor}`,
    `font-family: ${fontStack}`,
    `font-size: ${titleSizePx}px`,
    `line-height: ${styleTokens.lineHeight}`,
    "font-weight: 600",
  ].join("; ");
  const bodyStyle = [
    `color: ${textColor}`,
    `font-family: ${fontStack}`,
    `font-size: ${bodySizePx}px`,
    `line-height: ${styleTokens.lineHeight}`,
    "margin: 0",
  ].join("; ");
  return {
    titleHtml: `<span class="deck-disclaimer__title" style="${titleStyle}">Disclaimer</span>`,
    bodyHtml: `<p class="deck-disclaimer__text" style="${bodyStyle}">${DISCLAIMER_PLACEHOLDER}</p>`,
  };
}

function injectPreviewBase(doc, deckId, slideId) {
  if (!doc || !doc.head || !deckId) return;
  const baseHref = buildSlideAssetBaseHref(deckId, slideId);
  let base = doc.head.querySelector('base[data-preview-base="true"]');
  if (!base) {
    base = doc.createElement("base");
    base.setAttribute("data-preview-base", "true");
    doc.head.insertBefore(base, doc.head.firstChild);
  }
  base.setAttribute("href", baseHref);
}

function ensurePreviewNotes(doc, notesHtml, bodyHtml) {
  if (!doc) return;
  const container = doc.querySelector(".slide-container") || doc.body;
  if (!container) return;
  let notes = container.querySelector("aside.slide-notes");
  if (!notes) {
    notes = doc.createElement("aside");
    notes.className = "slide-notes";
    container.appendChild(notes);
  }
  if (!notesHtml) {
    notes.innerHTML = "";
    notes.style.display = "none";
    notes.removeAttribute("style");
    return;
  }
  notes.style.display = "";
  if (!container.style.position) {
    container.style.position = "relative";
  }
  notes.setAttribute("style", NOTES_OVERLAY_STYLE);
  notes.innerHTML = notesHtml || "";
}

function hasPreviewContent(titleHtml, bodyHtml, notesHtml) {
  return [titleHtml, bodyHtml, notesHtml].some((value) =>
    Boolean(stripHtml(String(value || "")).replace(/\u00a0/g, " ").trim())
  );
}

function buildPreviewDoc(slide, previewConfig, deckId, styleContext) {
  if (!slide) {
    return EMPTY_SLIDE_HTML;
  }
  const titleHtml = slide.titleHtml || "";
  const bodyHtml = slide.bodyHtml || "";
  const notesHtml = slide.notesHtml || "";
  const full = (slide.fullHtml || "").trim();
  if (!full) {
    if (!hasPreviewContent(titleHtml, bodyHtml, notesHtml)) {
      return EMPTY_SLIDE_HTML;
    }
    return buildFallbackDoc(titleHtml, bodyHtml, notesHtml, styleContext);
  }
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(full, "text/html");
    ensurePreviewNotes(doc, notesHtml, bodyHtml);
    ensurePreviewMeta(doc);
    injectPreviewBase(doc, deckId, slide.id);
    injectPreviewBundles(doc, previewConfig);
    injectPreviewFitStyles(doc);
    return "<!DOCTYPE html>\n" + doc.documentElement.outerHTML;
  } catch (error) {
    if (!hasPreviewContent(titleHtml, bodyHtml, notesHtml)) {
      return EMPTY_SLIDE_HTML;
    }
    return buildFallbackDoc(titleHtml, bodyHtml, notesHtml, styleContext);
  }
}

function measureSlideBox(doc) {
  if (!doc) return { width: 0, height: 0 };
  const container = doc.querySelector(".slide-container") || doc.body || doc.documentElement;
  const rect = typeof container.getBoundingClientRect === "function" ? container.getBoundingClientRect() : null;
  return {
    width: rect ? rect.width : 0,
    height: rect ? rect.height : 0,
  };
}

function injectPreviewFitStyles(doc) {
  if (!doc) return;
  let head = doc.head;
  if (!head) {
    head = doc.createElement("head");
    doc.documentElement.insertBefore(head, doc.documentElement.firstChild || null);
  }
  const existing = head.querySelector('style[data-preview-style="fit"]');
  if (existing) {
    existing.remove();
  }
  const style = doc.createElement("style");
  style.setAttribute("data-preview-style", "fit");
  style.textContent = `
    .slide-container {
      max-width: 920px;
      margin: 0 auto;
      width: 100%;
    }
  `;
  head.appendChild(style);
}

function resetPreviewTransforms(doc) {
  if (!doc) return;
  [doc.documentElement, doc.body].forEach((node) => {
    if (!node || !node.style) return;
    node.style.removeProperty("transform");
    node.style.removeProperty("transform-origin");
  });
}

function applyPreviewFit(doc, frame) {
  if (!doc || !frame) return;
  resetPreviewTransforms(doc);
  const { width, height } = measureSlideBox(doc);
  const naturalWidth = Math.max(
    width,
    doc.documentElement?.scrollWidth || 0,
    doc.body?.scrollWidth || 0
  );
  const naturalHeight = Math.max(
    height,
    doc.documentElement?.scrollHeight || 0,
    doc.body?.scrollHeight || 0
  );
  if (!naturalWidth || !naturalHeight) {
    return;
  }

  // Let the container match the slide aspect ratio so the preview window scales like Jinja.
  const parent = frame.parentElement;
  if (parent && parent.style && typeof parent.style.setProperty === "function") {
    parent.style.setProperty("--slides-preview-aspect-ratio", `${naturalWidth} / ${naturalHeight}`);
  }

  // Allow CSS to size the iframe; we only scale the inner document when needed.
  frame.style.width = "100%";
  frame.style.height = "100%";

  const parentRect =
    parent && typeof parent.getBoundingClientRect === "function" ? parent.getBoundingClientRect() : null;
  const frameRect = frame.getBoundingClientRect ? frame.getBoundingClientRect() : null;
  const fitWidth = parentRect?.width || frameRect?.width || naturalWidth;
  const fitHeight = parentRect?.height || frameRect?.height || naturalHeight;
  const scale = Math.min(fitWidth / naturalWidth, fitHeight / naturalHeight, 1);

  if (doc.documentElement?.style) {
    doc.documentElement.style.width = `${naturalWidth}px`;
    doc.documentElement.style.height = `${naturalHeight}px`;
    doc.documentElement.style.transformOrigin = "top left";
    doc.documentElement.style.transform = scale < 1 ? `scale(${scale})` : "";
  }
  if (doc.body?.style) {
    doc.body.style.width = `${naturalWidth}px`;
    doc.body.style.height = `${naturalHeight}px`;
    doc.body.style.transform = "";
    doc.body.style.transformOrigin = "";
  }
}

function measurePreviewImageOverlayMetrics(frame) {
  if (!frame || typeof frame.getBoundingClientRect !== "function") {
    return null;
  }
  const doc = frame.contentDocument;
  const image = doc?.querySelector?.(".slide-container img, img");
  if (!image || typeof image.getBoundingClientRect !== "function") {
    return null;
  }
  const imageRect = image.getBoundingClientRect();
  const frameRect = frame.getBoundingClientRect();
  const frameWidth = Number(frame.clientWidth || frameRect.width || 0);
  const frameHeight = Number(frame.clientHeight || frameRect.height || 0);
  const naturalWidth = Number(image.naturalWidth || 0);
  const naturalHeight = Number(image.naturalHeight || 0);
  if (
    !Number.isFinite(imageRect.left) ||
    !Number.isFinite(imageRect.top) ||
    !Number.isFinite(imageRect.width) ||
    !Number.isFinite(imageRect.height) ||
    imageRect.width <= 0 ||
    imageRect.height <= 0 ||
    frameWidth <= 0 ||
    frameHeight <= 0 ||
    naturalWidth <= 0 ||
    naturalHeight <= 0
  ) {
    return null;
  }
  return {
    left: imageRect.left,
    top: imageRect.top,
    width: imageRect.width,
    height: imageRect.height,
    frameWidth,
    frameHeight,
    naturalWidth,
    naturalHeight,
  };
}

function getContainerWidth(frame) {
  if (!frame) return 0;
  const parent = frame.parentElement;
  if (!parent) return 0;
  if (parent.clientWidth) return parent.clientWidth;
  const rect = typeof parent.getBoundingClientRect === "function" ? parent.getBoundingClientRect() : null;
  return rect ? rect.width : 0;
}

function measurePreviewDocument(doc) {
  const root = doc.documentElement;
  const body = doc.body;
  const rootBox = measureNodeBox(root);
  const bodyBox = measureNodeBox(body);
  const contentBox = measureContentBounds(body);
  const slideContainer = body ? body.querySelector(".slide-container") : null;
  const slideBox = measureNodeBox(slideContainer);
  const preferredWidth = slideBox.width || contentBox.width || bodyBox.width || rootBox.width;
  const preferredHeight = slideBox.height || contentBox.height || bodyBox.height || rootBox.height;
  return {
    height: Math.max(rootBox.height, bodyBox.height, contentBox.height, slideBox.height),
    width: Math.max(rootBox.width, bodyBox.width, contentBox.width, slideBox.width),
    contentWidth: preferredWidth,
    contentHeight: preferredHeight,
  };
}

function measureNodeBox(node) {
  if (!node) {
    return { width: 0, height: 0 };
  }
  const rect = typeof node.getBoundingClientRect === "function" ? node.getBoundingClientRect() : null;
  const width = Math.max(
    rect ? rect.width : 0,
    typeof node.scrollWidth === "number" ? node.scrollWidth : 0,
    typeof node.clientWidth === "number" ? node.clientWidth : 0
  );
  const height = Math.max(
    rect ? rect.height : 0,
    typeof node.scrollHeight === "number" ? node.scrollHeight : 0,
    typeof node.clientHeight === "number" ? node.clientHeight : 0
  );
  return { width, height };
}

function measureContentBounds(container) {
  if (!container || typeof container.getElementsByTagName !== "function") {
    return { width: 0, height: 0 };
  }
  const nodes = container.getElementsByTagName("*");
  const limit = Math.min(nodes.length, 250);
  if (!limit) {
    return { width: 0, height: 0 };
  }
  let width = 0;
  let height = 0;
  for (let index = 0; index < limit; index += 1) {
    const element = nodes[index];
    if (!element || typeof element.getBoundingClientRect !== "function") {
      continue;
    }
    const rect = element.getBoundingClientRect();
    const elementWidth = Math.max(
      rect ? rect.width : 0,
      typeof element.scrollWidth === "number" ? element.scrollWidth : 0,
      typeof element.clientWidth === "number" ? element.clientWidth : 0
    );
    const elementHeight = Math.max(
      rect ? rect.height : 0,
      typeof element.scrollHeight === "number" ? element.scrollHeight : 0,
      typeof element.clientHeight === "number" ? element.clientHeight : 0
    );
    width = Math.max(width, elementWidth);
    height = Math.max(height, elementHeight);
  }
  return { width, height };
}

function ensurePreviewMeta(doc) {
  if (!doc.head) {
    const head = doc.createElement("head");
    doc.documentElement.insertBefore(head, doc.documentElement.firstChild);
  }
  if (!doc.head.querySelector("meta[charset]")) {
    const meta = doc.createElement("meta");
    meta.setAttribute("charset", "utf-8");
    doc.head.insertBefore(meta, doc.head.firstChild);
  }
}

function injectPreviewBundles(doc, previewConfig) {
  const head = doc.head;
  const body = doc.body || doc.createElement("body");
  if (!doc.body) {
    doc.documentElement.appendChild(body);
  }
  (previewConfig?.styles || []).forEach((href) => {
    if (!href) return;
    const link = doc.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    head.appendChild(link);
  });
  (previewConfig?.scripts || []).forEach((src) => {
    if (!src) return;
    const script = doc.createElement("script");
    script.src = src;
    script.defer = true;
    body.appendChild(script);
  });
}

function buildFallbackDoc(titleHtml, bodyHtml, notesHtml, styleContext) {
  if (!hasPreviewContent(titleHtml, bodyHtml, notesHtml)) {
    return EMPTY_SLIDE_HTML;
  }
  const context = styleContext || buildPromptStyleContext(NOTEBOOKLM_DEFAULT_STYLE_KEY);
  const notesContent = notesHtml || "";
  const { fontStack, titleSizePx, bodySizePx, styleTokens } = context;
  const textColor = styleTokens.textColor;
  const slideBgColor = styleTokens.bgColor;
  return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <style>
      :root { font-family: ${fontStack}; }
      html, body { min-height: 100%; }
      body { margin: 0; background: #f8fafc; display: flex; align-items: flex-start; justify-content: center; padding: 24px; }
      .preview-stage { flex: 1 1 auto; width: 100%; display: flex; align-items: flex-start; justify-content: center; max-width: 100%; padding: 24px; box-sizing: border-box; }
      .preview-stage__inner { width: 100%; max-width: 960px; display: flex; align-items: stretch; justify-content: center; }
      .slide-container { background: ${slideBgColor}; border: 1px solid #d0d5dd; border-radius: 16px; box-shadow: 0 20px 45px rgba(15, 23, 42, 0.12); width: 100%; max-width: 960px; min-height: auto; padding: 48px; display: flex; flex-direction: column; gap: 28px; box-sizing: border-box; position: relative; }
      .preview-slide__title { font-size: ${titleSizePx}px; font-weight: 600; color: ${textColor}; margin: 0; }
      .preview-slide__body { font-size: ${bodySizePx}px; line-height: ${styleTokens.lineHeight}; color: ${textColor}; }
      .preview-slide__notes { position: absolute; left: 32px; right: 32px; bottom: 0; font-size: 12px; line-height: 1.4; color: ${textColor}; }
      .preview-slide__notes a { color: #2563eb; }
    </style>
  </head>
  <body>
    <div class="preview-stage">
      <div class="preview-stage__inner">
        <section class="slide-container">
          <h1 class="preview-slide__title">${titleHtml || ""}</h1>
          <div class="preview-slide__body">${bodyHtml || ""}</div>
          <aside class="preview-slide__notes">${notesContent}</aside>
        </section>
      </div>
    </div>
  </body>
</html>`;
}

function SlideList({
  slides,
  selectedIds,
  primaryId,
  onSelectSingle,
  onToggleSelect,
  onRangeSelect,
  onReorder,
  copy,
}) {
  const draggedIdRef = React.useRef(null);
  const selectedSet = useMemo(() => new Set(selectedIds || []), [selectedIds]);
  const headerPrefix = label(copy, "section_header_prefix", "Header");
  return (
    <ul className="slides-editor__list" aria-label={label(copy, "slides_heading", "Slides")}>
      {slides.map((slide, index) => {
        const isSelected = selectedSet.has(slide.id);
        const isPrimary = slide.id === primaryId;
        return (
          <li
            key={slide.id}
            className={`slides-editor__list-item${isSelected ? " is-selected" : ""}${isPrimary ? " is-active" : ""}${
              slide.kind === "sectionHeader" ? " is-section-header" : ""
            }`}
            draggable
            onDragStart={(event) => {
              draggedIdRef.current = slide.id;
              event.dataTransfer.effectAllowed = "move";
            }}
            onDragOver={(event) => {
              event.preventDefault();
              event.dataTransfer.dropEffect = "move";
            }}
            onDrop={(event) => {
              event.preventDefault();
              const sourceId = draggedIdRef.current;
              draggedIdRef.current = null;
              if (!sourceId || sourceId === slide.id) return;
              onReorder({ sourceId, targetId: slide.id });
            }}
            onDragEnd={() => {
              draggedIdRef.current = null;
            }}
          >
            <button
              type="button"
              onClick={(event) =>
                applySelectionGesture(event, slide.id, onSelectSingle, onToggleSelect, onRangeSelect)
              }
              className="ghost-button slides-editor__list-button"
              aria-pressed={isSelected}
            >
              <span className="slides-editor__list-button-main">
                {`${index + 1}. ${slide.kind === "sectionHeader" ? `(${headerPrefix}) ` : ""}${stripHtml(slide.titleHtml) || slide.id}`}
              </span>
              <span className="slides-editor__list-button-meta">
                <span aria-hidden="true">↕</span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function StoryboardGrid({
  slides,
  thumbnails,
  sections,
  selectedIds,
  primaryId,
  scale = 1,
  canvasRef,
  onCanvasPointerDown,
  marqueeBox,
  marqueePreviewIds = [],
  gridRef,
  onSelectSingle,
  onToggleSelect,
  onRangeSelect,
  onReorder,
  onDeleteSlide,
  onConvertToHeader,
  copy,
}) {
  const selectedSet = useMemo(() => new Set(selectedIds || []), [selectedIds]);
  const marqueeSet = useMemo(() => new Set(marqueePreviewIds || []), [marqueePreviewIds]);
  const draggedIdRef = React.useRef(null);
  const isTwoColumnScale = scale >= STORYBOARD_TWO_COLUMN_THRESHOLD;
  const cardSizeLabel = label(copy, "storyboard_card_size", "Card size");
  const deleteSlideLabel = label(copy, "delete_slide", "Delete slide");
  const markAsHeaderLabel = label(copy, "storyboard_mark_as_header", "Mark as section header");
  const emptySlideLabel = label(copy, "storyboard_empty_slide", "(empty slide)");
  const storyboardStyle = isTwoColumnScale
    ? {
        "--storyboard-card-scale": scale,
        "--storyboard-card-min-width": STORYBOARD_TWO_COLUMN_MIN_WIDTH,
      }
    : { "--storyboard-card-scale": scale };
  return (
    <div className="slides-storyboard-panel">
      <div className="slides-storyboard-panel__controls">
        <label htmlFor="storyboardZoomInput">{cardSizeLabel}</label>
        <input
          id="storyboardZoomInput"
          type="range"
          min={STORYBOARD_SCALE_MIN}
          max={STORYBOARD_SCALE_MAX}
          step={STORYBOARD_SCALE_STEP}
          value={scale}
          onChange={(e) => {
            const next = parseFloat(e.target.value);
            if (Number.isFinite(next)) {
              onReorder({ type: "scale", scale: next });
            }
          }}
          aria-label={cardSizeLabel}
        />
      </div>
      <div
        className="slides-storyboard-panel__canvas"
        ref={canvasRef}
        onPointerDown={onCanvasPointerDown}
      >
        {marqueeBox ? (
          <div
            className="storyboard-marquee"
            style={{
              left: `${marqueeBox.x1}px`,
              top: `${marqueeBox.y1}px`,
              width: `${Math.max(0, marqueeBox.x2 - marqueeBox.x1)}px`,
              height: `${Math.max(0, marqueeBox.y2 - marqueeBox.y1)}px`,
            }}
          />
        ) : null}
        <div
          id="storyboardGrid"
          className="slides-storyboard slides-storyboard--workspace"
          style={storyboardStyle}
          ref={gridRef}
        >
          {slides.map((slide, index) => {
            const isSelected = selectedSet.has(slide.id);
            const isPrimary = slide.id === primaryId;
            const thumbHtml = thumbnails?.[slide.id] || null;
            const storyboardThumb = buildStoryboardThumbnail(slide, thumbHtml);
            const slideTitle = stripHtml(slide.titleHtml) || slide.id || emptySlideLabel;
            return (
              <div
                key={slide.id}
                className={`slides-storyboard__card${isSelected ? " is-selected" : ""}${isPrimary ? " is-active" : ""}${
                  marqueeSet.has(slide.id) ? " is-marquee-preview" : ""
                }`}
                draggable
                data-slide-id={slide.id}
                onDragStart={(event) => {
                  draggedIdRef.current = slide.id;
                  event.dataTransfer.effectAllowed = "move";
                }}
                onDragOver={(event) => {
                  event.preventDefault();
                  event.dataTransfer.dropEffect = "move";
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  const sourceId = draggedIdRef.current;
                  draggedIdRef.current = null;
                  if (!sourceId || sourceId === slide.id) return;
                  onReorder({ sourceId, targetId: slide.id });
                }}
                onDragEnd={() => {
                  draggedIdRef.current = null;
                }}
              >
                <div className="slides-storyboard__actions">
                  <button
                    type="button"
                    className="ghost-button storyboard-action-btn"
                    title={deleteSlideLabel}
                    aria-label={deleteSlideLabel}
                    onClick={(event) => {
                      event.stopPropagation();
                      if (onDeleteSlide) {
                        onDeleteSlide(slide.id);
                      }
                    }}
                  >
                    ✕
                  </button>
                  {onConvertToHeader && (
                    <button
                      type="button"
                      className="ghost-button storyboard-action-btn"
                      title={markAsHeaderLabel}
                      aria-label={markAsHeaderLabel}
                      onClick={(event) => {
                        event.stopPropagation();
                        onConvertToHeader(slide.id);
                      }}
                    >
                      ↗
                    </button>
                  )}
                </div>
                <button
                  type="button"
                  className="slides-storyboard__card-button"
                  onClick={(event) =>
                    applySelectionGesture(event, slide.id, onSelectSingle, onToggleSelect, onRangeSelect)
                  }
                  aria-pressed={isSelected}
                  title={slideTitle}
                >
                  <div className="slides-storyboard__thumb">
                    {slide.kind === "sectionHeader" ? (
                      <SectionThumbnail slide={slide} sections={sections} copy={copy} />
                    ) : storyboardThumb ? (
                      <div dangerouslySetInnerHTML={{ __html: storyboardThumb }} />
                    ) : (
                      <span className="preview-placeholder">{emptySlideLabel}</span>
                    )}
                  </div>
                  <span className="slides-storyboard__badge" aria-hidden="true">
                    {index + 1}
                  </span>
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function SectionThumbnail({ slide, sections, copy }) {
  const section = (sections || []).find((entry) => entry.id === slide.sectionId) || null;
  const title =
    section?.title ||
    section?.id ||
    slide.sectionId ||
    slide.id ||
    label(copy, "sections_heading", "Section");
  return (
    <div className="storyboard-section-thumb">
      <p className="storyboard-section-thumb__title">{title}</p>
      {buildSectionThumbnailList(section, slide.subsectionId)}
    </div>
  );
}

function buildSectionThumbnailList(section, currentSubsectionId) {
  if (!section || !Array.isArray(section.subsections) || !section.subsections.length) {
    return null;
  }
  if (!currentSubsectionId) {
    return null;
  }
  const currentSubsection = section.subsections.find(
    (subsection) => subsection.id === currentSubsectionId
  );
  if (!currentSubsection) {
    return null;
  }
  return (
    <ul className="storyboard-section-thumb__subsections">
      <li className="storyboard-section-thumb__subsection is-current">
        {currentSubsection.title || currentSubsection.id}
      </li>
    </ul>
  );
}

function stripHtml(html) {
  if (!html) return "";
  const parser = new DOMParser();
  const doc = parser.parseFromString(`<div>${html}</div>`, "text/html");
  return doc.body.textContent || "";
}

function buildStoryboardThumbnail(slide, thumbHtml) {
  if (!thumbHtml) return null;
  return thumbHtml;
}

function BulkActions({ count, firstIndex, lastIndex, total, onPromote, onDemote, onDelete, onClear, copy }) {
  const emptyLabel = label(copy, "bulk_selection_placeholder", "No slides selected");
  const singleLabel = label(copy, "bulk_selection_single", "1 slide selected");
  const multiTemplate = label(copy, "bulk_selection_multi", "{count} slides selected");
  const summary =
    count === 0 ? emptyLabel : count === 1 ? singleLabel : multiTemplate.replace("{count}", String(count));
  const disable = count === 0;
  const promoteDisabled = disable || firstIndex <= 0;
  const demoteDisabled = disable || lastIndex === total - 1;
  return (
    <div
      id="bulkActionsBar"
      className="slides-editor__bulk-actions"
      hidden={count === 0}
    >
      <div
        id="bulkSelectionSummary"
        className="slides-editor__bulk-summary"
        data-empty-label={emptyLabel}
        data-single-label={singleLabel}
        data-multi-label={multiTemplate}
      >
        {summary}
      </div>
      <div className="slides-editor__bulk-buttons">
        <button
          id="bulkPromoteBtn"
          type="button"
          className="ghost-button slides-editor__pill-btn"
          onClick={onPromote}
          disabled={promoteDisabled}
          data-tooltip={tooltip(copy, "bulk_promote", "Move selected slides up one")}
        >
          {label(copy, "bulk_promote", "Move up one")}
        </button>
        <button
          id="bulkDemoteBtn"
          type="button"
          className="ghost-button slides-editor__pill-btn"
          onClick={onDemote}
          disabled={demoteDisabled}
          data-tooltip={tooltip(copy, "bulk_demote", "Move selected slides down one")}
        >
          {label(copy, "bulk_demote", "Move down one")}
        </button>
        <button
          id="bulkDeleteBtn"
          type="button"
          className="ghost-button slides-editor__pill-btn"
          onClick={onDelete}
          disabled={disable}
          data-tooltip={tooltip(copy, "bulk_delete", "Delete selected slides")}
        >
          {label(copy, "bulk_delete", "Delete selected")}
        </button>
        <button
          id="bulkClearSelectionBtn"
          type="button"
          className="ghost-button slides-editor__pill-btn"
          onClick={onClear}
          disabled={disable}
          data-tooltip={tooltip(copy, "bulk_clear", "Clear the current selection")}
        >
          {label(copy, "bulk_clear", "Clear selection")}
        </button>
      </div>
    </div>
  );
}

function LayoutInspectionPreview({
  layoutResult,
  overlayMetrics,
}) {
  const blocks = Array.isArray(layoutResult?.blocks) ? layoutResult.blocks : [];
  if (!layoutResult || !overlayMetrics) {
    return null;
  }
  const {
    left,
    top,
    width,
    height,
    naturalWidth,
    naturalHeight,
  } = overlayMetrics;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
      }}
    >
      {naturalWidth > 0 &&
        naturalHeight > 0 &&
        width > 0 &&
        height > 0 &&
        blocks.map((block, index) => {
          const bbox = block?.bbox;
          if (
            !bbox ||
            !Number.isFinite(bbox.x) ||
            !Number.isFinite(bbox.y) ||
            !Number.isFinite(bbox.w) ||
            !Number.isFinite(bbox.h) ||
            bbox.w <= 0 ||
            bbox.h <= 0
          ) {
            return null;
          }
          const color = getLayoutBlockColor(block.type);
          const labelText = getOverlayLabelText(block);
          return (
            <div
              key={`${block.blockId || block.block_id || block.type || "block"}-${index}`}
              style={{
                position: "absolute",
                left: `${left + (bbox.x / naturalWidth) * width}px`,
                top: `${top + (bbox.y / naturalHeight) * height}px`,
                width: `${(bbox.w / naturalWidth) * width}px`,
                height: `${(bbox.h / naturalHeight) * height}px`,
                border: `2px solid ${color}`,
                background: `${color}14`,
                boxSizing: "border-box",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  top: 0,
                  transform: "translateY(calc(-100% - 2px))",
                  maxWidth: "min(420px, 90vw)",
                  padding: "2px 6px",
                  background: color,
                  color: "#fff",
                  fontSize: 11,
                  fontWeight: 700,
                  lineHeight: 1.2,
                  whiteSpace: "normal",
                  overflowWrap: "anywhere",
                  wordBreak: "break-word",
                  zIndex: 2,
                }}
              >
                {labelText}
              </div>
            </div>
          );
        })}
    </div>
  );
}

function LayoutInspectionOverlay({
  imageUrl,
  layoutResult,
  loading,
  error,
  onInspect,
  onClear,
  copy,
  actionLabel,
  showClear,
  missingSlideMessage,
  blocked,
  blockedMessage,
}) {
  const blocks = Array.isArray(layoutResult?.blocks) ? layoutResult.blocks : [];
  const bulletTexts = Array.isArray(layoutResult?.bulletTexts) ? layoutResult.bulletTexts : [];
  const figureRegions = Array.isArray(layoutResult?.figureRegions) ? layoutResult.figureRegions : [];
  const titleText = String(layoutResult?.titleText || "").trim();

  return (
    <div className="slides-editor__field">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          flexWrap: "wrap",
          marginBottom: 8,
        }}
      >
        <label style={{ fontWeight: 600, margin: 0 }}>
          {label(copy, "layout_inspector_label", "Layout inspector")}
        </label>
        <button
          type="button"
          className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
          onClick={onInspect}
          disabled={!imageUrl || loading || blocked}
        >
          {actionLabel}
        </button>
        {showClear && (
          <button
            type="button"
            className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
            onClick={onClear}
            disabled={loading}
          >
            {label(copy, "layout_inspector_clear", "Clear")}
          </button>
        )}
      </div>
      {!imageUrl ? (
        <div style={{ fontSize: 12, color: "#64748b" }}>
          {label(
            copy,
            "layout_inspector_no_image",
            "This slide does not expose an inspectable image source.",
          )}
        </div>
      ) : null}
      {error ? (
        <div style={{ fontSize: 12, color: "#b91c1c", marginBottom: 8 }}>{error}</div>
      ) : null}
      {!error && missingSlideMessage ? (
        <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8 }}>
          {missingSlideMessage}
        </div>
      ) : null}
      {blocked ? (
        <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8 }}>
          {blockedMessage ||
            label(
              copy,
              "layout_inspector_wait_processing",
              "Wait until deck processing is complete before inspecting layout.",
            )}
        </div>
      ) : null}
      {!loading && !layoutResult && imageUrl ? (
        <div style={{ fontSize: 12, color: "#64748b" }}>
          {label(
            copy,
            "layout_inspector_hint",
            "Analyze the deck layout once, then show the saved Paddle block mapping on the selected slide preview.",
          )}
        </div>
      ) : null}
      {layoutResult ? (
        <div
          style={{
            display: "grid",
            gap: 4,
            fontSize: 12,
            color: "#334155",
          }}
        >
          <div>
            {label(copy, "layout_inspector_blocks", "Blocks")}: {blocks.length}
          </div>
          <div>
            {label(copy, "layout_inspector_figures", "Figure regions")}: {figureRegions.length}
          </div>
          <div>
            {label(copy, "layout_inspector_title", "Detected title")}: {titleText || "n/a"}
          </div>
          <div>
            {label(copy, "layout_inspector_bullets", "Detected bullets")}:{" "}
            {bulletTexts.length ? bulletTexts.join(" | ") : "n/a"}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function App({ bootstrap }) {
  const [state, dispatch] = useReducer(reducer, initialState(bootstrap));
  const { copy } = state;
  const promptStyleContext = useMemo(
    () => buildPromptStyleContext(state.promptStyleKey),
    [state.promptStyleKey]
  );
  const [layoutInspection, setLayoutInspection] = React.useState({
    deckId: "",
    loading: false,
    error: "",
    payload: null,
    visible: false,
  });
  const [ocrProgress, setOcrProgress] = React.useState(createEmptyOcrProgress);
  const [processingClockMs, setProcessingClockMs] = React.useState(() => Date.now());

  function refreshDeckList({ selectedDeckId } = {}) {
    return listDecks()
      .then((resp) => {
        const decks = resp.decks || [];
        dispatch({ type: "set_decks", decks });
        if (!state.currentDeckId && selectedDeckId && decks.length) {
          loadDeck(selectedDeckId);
        }
      })
      .catch((error) => {
        dispatch({ type: "set_status", message: `Failed to refresh decks: ${error.message}`, isError: true });
      });
  }

  function refreshPptxTemplateList(options = {}) {
    const selectedTemplateId = String(options.selectedTemplateId || "").trim();
    return listPptxTemplates()
      .then((resp) => {
        const templates = Array.isArray(resp?.templates) ? resp.templates : [];
        const defaultTemplateId =
          typeof resp?.defaultTemplateId === "string" ? resp.defaultTemplateId : null;
        dispatch({ type: "set_pptx_templates", templates, defaultTemplateId });
        if (selectedTemplateId) {
          dispatch({
            type: "set_upload_template_choice",
            value: templateChoiceForId(selectedTemplateId),
          });
        }
        return resp;
      })
      .catch((error) => {
        dispatch({
          type: "set_status",
          message: `Failed to load PPTX templates: ${error.message}`,
          isError: true,
        });
        return null;
      });
  }

  useEffect(() => {
    dispatch({ type: "loading", value: true });
    listDecks()
      .then((resp) => {
        const decks = resp.decks || [];
        dispatch({ type: "set_decks", decks });
      })
      .catch((error) => {
        dispatch({ type: "set_status", message: `Failed to load decks: ${error.message}`, isError: true });
      })
      .finally(() => dispatch({ type: "loading", value: false }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    refreshPptxTemplateList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const handleBeforeUnload = (event) => {
      if (!state.dirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [state.dirty]);

  function delayMs(ms) {
    return new Promise((resolve) => {
      window.setTimeout(resolve, ms);
    });
  }

  const OCR_READY_TIMEOUT_MS = 6 * 60 * 60 * 1000;

  async function waitForDeckOcrReady(deckId) {
    const normalizedDeckId = String(deckId || "").trim();
    if (!normalizedDeckId) {
      return;
    }
    let status = await fetchDeckOcrStatus(normalizedDeckId);
    if (status.status === "completed" || status.status === "skipped") {
      return;
    }
    if (status.status === "failed") {
      throw new Error(status.error || `OCR failed for ${normalizedDeckId}.`);
    }
    if (status.status === "idle") {
      await requestDeckOcr(normalizedDeckId, { lang: resolveOcrLang(state.lang) });
      return;
    }

    const deadline = Date.now() + OCR_READY_TIMEOUT_MS;
    let lastStatus = status;
    while (Date.now() < deadline) {
      await delayMs(1200);
      status = await fetchDeckOcrStatus(normalizedDeckId);
      lastStatus = status;
      if (status.status === "completed" || status.status === "skipped") {
        return;
      }
      if (status.status === "failed") {
        throw new Error(status.error || `OCR failed for ${normalizedDeckId}.`);
      }
      if (status.status === "idle") {
        await requestDeckOcr(normalizedDeckId, { lang: resolveOcrLang(state.lang) });
        return;
      }
    }
    try {
      await fetchDeckOcrAudit(normalizedDeckId);
      return;
    } catch (error) {
      const builtPages = Number(lastStatus?.builtPages || 0);
      const totalPages = Number(lastStatus?.totalPages || 0);
      const statusValue = String(lastStatus?.status || "unknown");
      throw new Error(
        `Timed out waiting OCR for ${normalizedDeckId} ` +
          `(status=${statusValue}, built=${builtPages}, total=${totalPages}).`
      );
    }
  }

  function ensureDeckOcrPayload(deckId, slidesForOcr, deckMeta) {
    if (!deckId) return Promise.resolve();
    const deckSlides = slidesForOcr || state.slides;
    const ocrTargetCount = countSlidesWithImages(deckSlides) || deckSlides.length;
    const hasImages = deckMeta?.hasImages ?? countSlidesWithImages(deckSlides) > 0;
    const hasPdf = deckMeta?.hasPdf ?? false;
    const startOcrProgress = (message, lang = "") => {
      setOcrProgress({
        ...createEmptyOcrProgress(),
        active: true,
        deckId,
        lang: String(lang || "").trim(),
        message,
        step: "ocr",
      });
    };
    const updateOcrProgress = (message) => {
      setOcrProgress((prev) => {
        if (!prev.active || prev.deckId !== deckId) {
          return prev;
        }
        return { ...prev, message };
      });
    };
    const clearOcrProgress = () => {
      setOcrProgress((prev) => {
        if (prev.deckId !== deckId) {
          return prev;
        }
        return createEmptyOcrProgress();
      });
    };
    if (!hasImages && !hasPdf) {
      dispatch({
        type: "set_status",
        message: "OCR skipped: no PDF or slide images available for this deck.",
        isError: false,
      });
      clearOcrProgress();
      return Promise.resolve();
    }
    const runOcrWithPolling = (statusMessage) => {
      const ocrLang = resolveOcrLang(state.lang);
      startOcrProgress(statusMessage, ocrLang);
      dispatch({
        type: "set_status",
        message: statusMessage,
        isError: false,
      });
      let cancelled = false;
      let pollTimer = null;
      const pollStatus = () => {
        fetchDeckOcrStatus(deckId)
          .then((status) => {
            if (cancelled) return;
            if (status.status === "running") {
              const progressState = buildDeckProgressState(deckId, status, ocrTargetCount);
              setOcrProgress(progressState);
              dispatch({
                type: "set_status",
                message: progressState.message,
                isError: false,
              });
            } else if (status.status === "completed") {
              clearOcrProgress();
              dispatch({
                type: "set_status",
                message: status.message || "Deck processing complete.",
                isError: false,
              });
              cancelled = true;
              return;
            } else if (status.status === "skipped") {
              clearOcrProgress();
              dispatch({
                type: "set_status",
                message: status.message || "Deck processing skipped for this deck.",
                isError: false,
              });
              cancelled = true;
              return;
            } else if (status.status === "failed") {
              clearOcrProgress();
              dispatch({
                type: "set_status",
                message: status.error || "OCR failed.",
                isError: true,
              });
              cancelled = true;
              return;
            }
            pollTimer = window.setTimeout(pollStatus, 1200);
          })
          .catch(() => {
            if (cancelled) return;
            pollTimer = window.setTimeout(pollStatus, 2000);
          });
      };
      pollStatus();
      return requestDeckOcr(deckId, { lang: ocrLang })
        .then(() => {
          cancelled = true;
          if (pollTimer) window.clearTimeout(pollTimer);
          clearOcrProgress();
          dispatch({
            type: "set_status",
            message: "Deck processing complete.",
            isError: false,
          });
        })
        .catch((ocrError) => {
          if (ocrError?.status === 404) {
            return fetchDeckOcrAudit(deckId)
              .then(() => {
                cancelled = true;
                if (pollTimer) window.clearTimeout(pollTimer);
                clearOcrProgress();
                dispatch({
                  type: "set_status",
                  message: "Deck processing complete.",
                  isError: false,
                });
              })
              .catch((auditError) => {
                cancelled = true;
                if (pollTimer) window.clearTimeout(pollTimer);
                clearOcrProgress();
                dispatch({
                  type: "set_status",
                  message: `Failed to run OCR: ${auditError.message}`,
                  isError: true,
                });
              });
          }
          if (ocrError?.status === 504) {
            updateOcrProgress(
              "Deck processing is running in the background.",
            );
            dispatch({
              type: "set_status",
              message: "Deck processing is running in the background (OCR).",
              isError: false,
            });
            return null;
          }
          cancelled = true;
          if (pollTimer) window.clearTimeout(pollTimer);
          clearOcrProgress();
          dispatch({
            type: "set_status",
            message: `Failed to run OCR: ${ocrError.message}`,
            isError: true,
          });
        });
    };
    startOcrProgress("Checking OCR and layout payload.", resolveOcrLang(state.lang));
    return fetchDeckOcrAudit(deckId)
      .then(() => {
        clearOcrProgress();
      })
      .catch((error) => {
        if (error?.status === 404) {
          return runOcrWithPolling(
            `No OCR yet for ${deckId}. Starting deck processing in the background.`
          );
        }
        if (error?.status === 504) {
          return runOcrWithPolling(
            "Preparing deck processing in the background."
          );
        }
        clearOcrProgress();
        dispatch({
          type: "set_status",
          message: `Failed to check OCR payload: ${error.message}`,
          isError: true,
        });
        return null;
      });
  }

  function syncDeckOcrProgress(deckId, deckSlides) {
    if (!deckId) {
      setOcrProgress(createEmptyOcrProgress());
      return Promise.resolve(null);
    }
    const totalPages = countSlidesWithImages(deckSlides) || deckSlides.length || 0;
    return fetchDeckOcrStatus(deckId)
      .then((status) => {
        const statusValue = String(status?.status || "").trim().toLowerCase();
        if (statusValue === "running") {
          const progressState = buildDeckProgressState(deckId, status, totalPages);
          setOcrProgress(progressState);
          dispatch({
            type: "set_status",
            message: progressState.message,
            isError: false,
          });
          return status;
        }
        setOcrProgress((prev) =>
          prev.deckId === deckId ? createEmptyOcrProgress() : prev
        );
        return status;
      })
      .catch(() => {
        setOcrProgress((prev) =>
          prev.deckId === deckId ? createEmptyOcrProgress() : prev
        );
        return null;
      });
  }

  function loadDeck(deckId) {
    if (!deckId) return;
    dispatch({ type: "loading", value: true });
    dispatch({
      type: "set_status",
      message: "Loading deck…",
      isError: false,
    });
    getDeck(deckId)
      .then((deck) => {
        const slides = (deck.slides || []).map(normalizeEditorSlide);
        const sections = (deck.sections || []).map(normalizeSection);
        dispatch({
          type: "set_deck",
          deckId: deck.deckId,
          promptStyle: deck.promptStyle,
          slides,
          sections,
          thumbnails: deck.thumbnails || {},
          hasLayout: !!deck.hasLayout,
        });
        dispatch({ type: "set_status", message: `Loaded deck ${deck.deckId}`, isError: false });
        return syncDeckOcrProgress(deck.deckId, slides).then((ocrStatus) => {
          const statusValue = String(ocrStatus?.status || "").trim().toLowerCase();
          if (deck.hasLayout || statusValue === "completed") {
            invalidateDeckDebugPayloads(deck.deckId);
            return ensureDeckLayoutPayload(deck.deckId, slides, { forceRefresh: true });
          }
          return null;
        });
      })
      .catch((error) => {
        dispatch({ type: "set_status", message: `Failed to load deck: ${error.message}`, isError: true });
      })
      .finally(() => dispatch({ type: "loading", value: false }));
  }

  const selectedSlide = useMemo(
    () => state.slides.find((slide) => slide.id === state.selectedSlideId) || null,
    [state.slides, state.selectedSlideId]
  );
  const selectedSlideIsImageBacked = useMemo(
    () => isImageBackedSlide(selectedSlide),
    [selectedSlide]
  );
  const selectedSlideImageUrl = useMemo(
    () => extractPrimarySlideImageUrl(selectedSlide, state.currentDeckId),
    [selectedSlide, state.currentDeckId]
  );
  const selectedSlideLayoutBase = useMemo(() => {
    const slides = Array.isArray(layoutInspection.payload?.slides)
      ? layoutInspection.payload.slides
      : [];
    return slides.find((slide) => slide?.slideId === selectedSlide?.id) || null;
  }, [layoutInspection.payload, selectedSlide?.id]);
  const selectedSlideLayout = selectedSlideLayoutBase;
  const layoutPreviewVisible =
    selectedSlideIsImageBacked && !!selectedSlideLayout;
  const layoutAnalysisBlocked =
    layoutInspection.loading && layoutInspection.deckId === (state.currentDeckId || "");
  const deckProcessingBlocked =
    ocrProgress.active && ocrProgress.deckId === (state.currentDeckId || "");
  const contentProcessingBlocked = deckProcessingBlocked || layoutAnalysisBlocked;
  const deckProcessingMessage = deckProcessingBlocked
    ? ocrProgress.message ||
      label(
        copy,
        "deck_processing_wait_message",
        "Deck processing is in progress. Please wait until it completes.",
      )
    : "";
  const contentProcessingTitle = deckProcessingBlocked
    ? label(copy, "deck_processing_overlay_title", "Deck processing in progress")
    : label(copy, "layout_processing_overlay_title", "Analyzing layout");
  const contentProcessingMessage = deckProcessingBlocked
    ? deckProcessingMessage
    : label(
        copy,
        "layout_processing_message",
        "Analyzing the deck layout and saving the result.",
      );
  const deckProcessingStepLabel = deckProcessingBlocked
    ? formatDeckProcessingStep(ocrProgress.step)
    : "";
  const deckProcessingLangLabel = deckProcessingBlocked
    ? formatOcrLanguageLabel(ocrProgress.lang)
    : "";
  const persistentOcrLanguageLabel = buildOcrLanguageDebugLabel(
    state.lang,
    ocrProgress.lang,
  );
  const deckProcessingLastUpdateLabel = deckProcessingBlocked
    ? formatRelativeAge(ocrProgress.updatedAt, processingClockMs)
    : "";
  const deckProcessingMeta = [
    deckProcessingLangLabel ? `OCR language: ${deckProcessingLangLabel}` : "",
    deckProcessingStepLabel ? `Current step: ${deckProcessingStepLabel}` : "",
    deckProcessingLastUpdateLabel ? `Last update: ${deckProcessingLastUpdateLabel}` : "",
  ]
    .filter(Boolean)
    .join(" • ");
  const toolbarDeckActionsDisabled = contentProcessingBlocked;

  useEffect(() => {
    layoutRequestIdRef.current += 1;
    setLayoutInspection((prev) => {
      if (prev.deckId === (state.currentDeckId || "")) {
        return prev;
      }
      return {
        deckId: state.currentDeckId || "",
        loading: false,
        error: "",
        payload: null,
        visible: false,
      };
    });
  }, [state.currentDeckId]);

  useEffect(() => {
    if (!deckProcessingBlocked) {
      return undefined;
    }
    setProcessingClockMs(Date.now());
    const intervalId = window.setInterval(() => {
      setProcessingClockMs(Date.now());
    }, 1000);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [deckProcessingBlocked]);

  useEffect(() => {
    if (!ocrProgress.active) {
      return undefined;
    }
    const currentDeckId = state.currentDeckId || "";
    if (!currentDeckId || ocrProgress.deckId !== currentDeckId) {
      return undefined;
    }

    let cancelled = false;
    let pollTimer = null;
    const totalPages = countSlidesWithImages(state.slides) || state.slides.length || 0;

    const pollStatus = () => {
      fetchDeckOcrStatus(currentDeckId)
        .then((status) => {
          if (cancelled) {
            return;
          }
          const statusValue = String(status?.status || "").trim().toLowerCase();
          if (statusValue === "running") {
            const progressState = buildDeckProgressState(currentDeckId, status, totalPages);
            setOcrProgress(progressState);
            dispatch({
              type: "set_status",
              message: progressState.message,
              isError: false,
            });
            pollTimer = window.setTimeout(pollStatus, 1200);
            return;
          }
          if (statusValue === "completed") {
            setOcrProgress(createEmptyOcrProgress());
            dispatch({
              type: "set_status",
              message: status?.message || "Deck processing complete.",
              isError: false,
            });
            invalidateDeckDebugPayloads(currentDeckId);
            ensureDeckLayoutPayload(currentDeckId, state.slides, { forceRefresh: true });
            return;
          }
          if (statusValue === "skipped") {
            setOcrProgress(createEmptyOcrProgress());
            dispatch({
              type: "set_status",
              message: status?.message || "Deck processing skipped for this deck.",
              isError: false,
            });
            return;
          }
          if (statusValue === "failed") {
            setOcrProgress(createEmptyOcrProgress());
            dispatch({
              type: "set_status",
              message: status?.error || "OCR failed.",
              isError: true,
            });
            return;
          }
          pollTimer = window.setTimeout(pollStatus, 2000);
        })
        .catch(() => {
          if (cancelled) {
            return;
          }
          pollTimer = window.setTimeout(pollStatus, 2000);
        });
    };

    pollTimer = window.setTimeout(pollStatus, 1200);
    return () => {
      cancelled = true;
      if (pollTimer) {
        window.clearTimeout(pollTimer);
      }
    };
  }, [ocrProgress.active, ocrProgress.deckId, state.currentDeckId, state.slides]);

  function clearLayoutInspection() {
    setLayoutInspection((prev) => ({
      loading: false,
      error: "",
      payload: prev.payload,
      visible: false,
      deckId: state.currentDeckId || prev.deckId || "",
    }));
  }

  function invalidateDeckDebugPayloads(deckId) {
    const normalizedDeckId = String(deckId || "").trim();
    if (!normalizedDeckId) {
      return;
    }
    setLayoutInspection((prev) => {
      if (prev.deckId !== normalizedDeckId) {
        return prev;
      }
      return {
        deckId: normalizedDeckId,
        loading: false,
        error: "",
        payload: null,
        visible: false,
      };
    });
  }

  function ensureDeckLayoutPayload(deckId, deckSlides, options = {}) {
    if (!deckId) {
      return Promise.resolve(null);
    }
    const forceRefresh = Boolean(options.forceRefresh);
    const slides = deckSlides || state.slides;
    if ((countSlidesWithImages(slides) || 0) <= 0) {
      return Promise.resolve(null);
    }
    if (!forceRefresh && layoutInspection.deckId === deckId) {
      if (layoutInspection.loading) {
        return Promise.resolve(null);
      }
      if (layoutInspection.payload) {
        return Promise.resolve({
          payload: layoutInspection.payload,
          cached: true,
        });
      }
    }

    const requestId = layoutRequestIdRef.current + 1;
    layoutRequestIdRef.current = requestId;
    setLayoutInspection({
      deckId,
      loading: true,
      error: "",
      payload: null,
      visible: false,
    });
    return startDeckLayout(deckId, {
      lang: resolveOcrLang(state.lang),
      force: false,
    })
      .then(() => pollDeckLayoutUntilReady(deckId, requestId))
      .then((json) => {
        if (layoutRequestIdRef.current !== requestId) {
          return null;
        }
        setLayoutInspection({
          deckId,
          loading: false,
          error: "",
          payload: json?.payload || null,
          visible: true,
        });
        dispatch({
          type: "set_status",
          message:
            json?.cached
              ? `Loaded saved layout for ${deckId}.`
              : `Saved layout for ${deckId}.`,
          isError: false,
        });
        return json;
      })
      .catch((error) => {
        if (layoutRequestIdRef.current !== requestId) {
          return null;
        }
        const statusCode =
          error && typeof error === "object" ? Number(error.status) : NaN;
        const errorMessage =
          error instanceof Error ? error.message : String(error || "");
        const isGatewayError =
          [502, 504].includes(statusCode) ||
          (statusCode === 503 &&
            (!errorMessage ||
              errorMessage ===
                "API temporarily unavailable (gateway error). Please retry in a few seconds."));
        setLayoutInspection({
          deckId,
          loading: false,
          error: isGatewayError
            ? "Layout inspection API is unavailable on the running server."
            : errorMessage,
          payload: null,
          visible: false,
        });
        dispatch({
          type: "set_status",
          message: errorMessage || "Layout analysis failed.",
          isError: true,
        });
        return null;
      });
  }

  function pollDeckLayoutUntilReady(deckId, requestId, attempt = 0) {
    return fetchDeckLayoutStatus(deckId).then((status) => {
      if (layoutRequestIdRef.current !== requestId) {
        return null;
      }
      const statusValue = String(status?.status || "").trim().toLowerCase();
      if (statusValue === "completed") {
        return requestDeckLayout(deckId, {
          lang: resolveOcrLang(state.lang),
          force: false,
        });
      }
      if (statusValue === "failed") {
        throw new Error(status?.error || status?.message || "Layout analysis failed.");
      }
      if (statusValue === "skipped") {
        throw new Error(status?.message || "Layout analysis was skipped.");
      }
      if (attempt >= 120) {
        throw new Error("Timed out waiting for saved layout payload.");
      }
      return new Promise((resolve) => {
        window.setTimeout(() => resolve(pollDeckLayoutUntilReady(deckId, requestId, attempt + 1)), 1000);
      });
    });
  }

  function inspectSelectedSlideLayout() {
    if (!selectedSlide || !selectedSlideIsImageBacked) {
      return;
    }
    if (!state.currentDeckId) {
      return;
    }
    if (contentProcessingBlocked) {
      return;
    }
    if (!selectedSlideImageUrl) {
      setLayoutInspection((prev) => ({
        deckId: state.currentDeckId || prev.deckId || "",
        loading: false,
        error: "Selected slide does not expose an image to inspect.",
        payload: prev.payload,
        visible: false,
      }));
      return;
    }
    if (layoutPreviewVisible) {
      setLayoutInspection((prev) => ({
        ...prev,
        error: "",
        visible: false,
      }));
      return;
    }
    if (layoutInspection.payload) {
      setLayoutInspection((prev) => ({
        ...prev,
        error: "",
        visible: true,
      }));
      return;
    }
    const requestId = layoutRequestIdRef.current + 1;
    layoutRequestIdRef.current = requestId;
    setLayoutInspection({
      deckId: state.currentDeckId,
      loading: true,
      error: "",
      payload: null,
      visible: false,
    });
    startDeckLayout(state.currentDeckId, {
      lang: resolveOcrLang(state.lang),
      force: false,
    })
      .then(() => pollDeckLayoutUntilReady(state.currentDeckId, requestId))
      .then((json) => {
        if (layoutRequestIdRef.current !== requestId) {
          return;
        }
        setLayoutInspection({
          deckId: state.currentDeckId,
          loading: false,
          error: "",
          payload: json?.payload || null,
          visible: true,
        });
        dispatch({
          type: "set_status",
          message:
            json?.cached
              ? `Loaded saved layout for ${state.currentDeckId}.`
              : `Saved layout for ${state.currentDeckId}.`,
          isError: false,
        });
      })
      .catch((error) => {
        if (layoutRequestIdRef.current !== requestId) {
          return;
        }
        const statusCode =
          error && typeof error === "object" ? Number(error.status) : NaN;
        const errorMessage =
          error instanceof Error ? error.message : String(error || "");
        const isGatewayError =
          [502, 504].includes(statusCode) ||
          (statusCode === 503 &&
            (!errorMessage ||
              errorMessage ===
                "API temporarily unavailable (gateway error). Please retry in a few seconds."));
        setLayoutInspection({
          deckId: state.currentDeckId,
          loading: false,
          error: isGatewayError
            ? "Layout inspection API is unavailable on the running server."
            : errorMessage,
          payload: null,
          visible: false,
        });
        dispatch({
          type: "set_status",
          message: errorMessage || "Layout analysis failed.",
          isError: true,
        });
      });
  }

  function selectSlide(slideId) {
    commitSelection([slideId], slideId, slideId);
  }

  function toggleSelect(slideId) {
    const set = new Set(state.selectedSlideIds || []);
    if (set.has(slideId)) {
      set.delete(slideId);
    } else {
      set.add(slideId);
    }
    const ids = Array.from(set);
    const primary = ids.length ? ids[ids.length - 1] : null;
    const anchor = ids.length ? state.selectionAnchorId || primary : null;
    commitSelection(ids, primary, anchor);
  }

  function rangeSelect(slideId) {
    const slides = state.slides;
    if (!slides.length) return;
    const anchorId = state.selectionAnchorId || state.selectedSlideId || slideId;
    const anchorIndex = slides.findIndex((s) => s.id === anchorId);
    const targetIndex = slides.findIndex((s) => s.id === slideId);
    if (anchorIndex === -1 || targetIndex === -1) {
      commitSelection([slideId], slideId, slideId);
      return;
    }
    const start = Math.min(anchorIndex, targetIndex);
    const end = Math.max(anchorIndex, targetIndex);
    const ids = slides.slice(start, end + 1).map((s) => s.id);
    commitSelection(ids, slideId, anchorId);
  }

  function clearSelection() {
    commitSelection([], null, null);
  }
  const canEditHtmlFields = Boolean(
    selectedSlide && selectedSlide.kind !== "sectionHeader" && !selectedSlideIsImageBacked
  );
  const canEditNotes = Boolean(selectedSlide && selectedSlide.kind !== "sectionHeader");

  function handleFieldChange(field, value) {
    if (!selectedSlide) return;
    if (selectedSlide.kind === "sectionHeader") return;
    if (isImageBackedSlide(selectedSlide)) return;
    dispatch({ type: "update_slide", slideId: selectedSlide.id, patch: { [field]: value } });
  }

  function handleNotesChange(value) {
    if (!selectedSlide) return;
    if (selectedSlide.kind === "sectionHeader") return;
    const notesHtml = buildNotesHtmlFromText(value);
    dispatch({
      type: "update_slide",
      slideId: selectedSlide.id,
      patch: { notesText: value, notesHtml },
    });
  }

  function handleAddSlide() {
    const newSlideId = nextSlideId(state.slides);
    const newSlide = normalizeEditorSlide({ id: newSlideId });
    const slides = [...state.slides];
    const index = state.slides.findIndex((s) => s.id === state.selectedSlideId);
    if (index === -1) {
      slides.push(newSlide);
    } else {
      slides.splice(index + 1, 0, newSlide);
    }
    dispatch({ type: "add_slide", slides, newSlideId });
  }

  function handleAddIntroSlides() {
    if (!state.currentDeckId) {
      dispatch({ type: "set_status", message: "Select a deck before adding intro slides.", isError: true });
      return;
    }
    const [titleId, disclaimerId] = nextSlideIds(state.slides, 2);
    const titleContent = buildTitleSlideContent(promptStyleContext);
    const disclaimerContent = buildDisclaimerSlideContent(promptStyleContext);
    const titleFullHtml = buildIntroSlideFullHtml(titleContent.titleHtml, titleContent.bodyHtml, promptStyleContext);
    const disclaimerFullHtml = buildIntroSlideFullHtml(
      disclaimerContent.titleHtml,
      disclaimerContent.bodyHtml,
      promptStyleContext
    );
    const titleSlide = normalizeEditorSlide({
      id: titleId,
      titleHtml: titleContent.titleHtml,
      bodyHtml: titleContent.bodyHtml,
      fullHtml: titleFullHtml,
    });
    const disclaimerSlide = normalizeEditorSlide({
      id: disclaimerId,
      titleHtml: disclaimerContent.titleHtml,
      bodyHtml: disclaimerContent.bodyHtml,
      fullHtml: disclaimerFullHtml,
    });
    const slides = [titleSlide, disclaimerSlide, ...state.slides];
    dispatch({ type: "set_slides", slides });
    dispatch({
      type: "set_selection",
      ids: [titleId],
      primaryId: titleId,
      anchorId: titleId,
    });
    dispatch({ type: "set_status", message: "Added title and disclaimer slides.", isError: false });
  }

  function handleDeleteSlide() {
    if (!state.selectedSlideId) return;
    const set = new Set(state.selectedSlideIds);
    if (!set.size) return;
    const remaining = state.slides.filter((slide) => !set.has(slide.id));
    let nextSelection = null;
    if (remaining.length) {
      const deletedIndexes = state.slides
        .map((slide, idx) => ({ id: slide.id, idx }))
        .filter((entry) => set.has(entry.id))
        .map((entry) => entry.idx);
      const minDeleted = deletedIndexes.length ? Math.min(...deletedIndexes) : 0;
      const fallbackIndex = Math.min(minDeleted, remaining.length - 1);
      nextSelection = remaining[fallbackIndex]?.id || remaining[0].id;
    }
    dispatch({ type: "delete_slides", slides: remaining, nextSelection });
    dispatch({ type: "set_status", message: "Deleted selected slides.", isError: false });
  }

  function deleteSlidesById(id) {
    if (!id) return;
    commitSelection([id], id, id);
    handleDeleteSlide();
  }

  function handleSave() {
    if (!state.currentDeckId) {
      dispatch({ type: "set_status", message: "Select a deck before saving.", isError: true });
      return;
    }
    dispatch({ type: "saving", value: true });
    dispatch({
      type: "set_status",
      message: "Saving deck…",
      isError: false,
    });
    const payload = {
      slides: state.slides.map((slide) => ({
        id: slide.id,
        titleHtml: slide.titleHtml,
        bodyHtml: slide.bodyHtml,
        notesHtml: slide.notesHtml,
        sourceHtml: slide.sourceHtml,
        fullHtml: slide.fullHtml,
        kind: slide.kind,
        sectionId: slide.sectionId,
        subsectionId: slide.subsectionId,
      })),
      sections: state.sections.map((section) => ({
        id: section.id,
        title: section.title,
        startSlide: section.startSlide,
        subsections: section.subsections.map((sub) => ({
          id: sub.id,
          title: sub.title,
          startSlide: sub.startSlide,
        })),
      })),
      promptStyle: promptStyleContext.styleKey,
    };
    saveDeck(state.currentDeckId, payload)
      .then((resp) => {
        const slides = (resp.slides || []).map(normalizeEditorSlide);
        const sections = (resp.sections || []).map(normalizeSection);
        dispatch({
          type: "set_deck",
          deckId: resp.deckId,
          promptStyle: resp.promptStyle,
          slides,
          sections,
          thumbnails: resp.thumbnails || {},
          hasLayout: !!resp.hasLayout,
          selectedSlideId: state.selectedSlideId,
          selectedSlideIds: state.selectedSlideIds,
          selectionAnchorId: state.selectionAnchorId,
        });
        dispatch({ type: "set_status", message: "Deck saved successfully.", isError: false });
      })
      .catch((error) => {
        dispatch({ type: "set_status", message: `Failed to save deck: ${error.message}`, isError: true });
      })
      .finally(() => dispatch({ type: "saving", value: false }));
  }

  function handlePrevNext(offset) {
    if (!state.slides.length) return;
    const currentIndex = state.slides.findIndex((slide) => slide.id === state.selectedSlideId);
    const targetIndex = currentIndex + offset;
    if (targetIndex < 0 || targetIndex >= state.slides.length) return;
    commitSelection([state.slides[targetIndex].id], state.slides[targetIndex].id, state.slides[targetIndex].id);
  }

  function moveSelectionBy(offset) {
    if (!Number.isInteger(offset) || !state.slides.length) return;
    const currentId = state.selectedSlideId || state.slides[0].id;
    const currentIndex = state.slides.findIndex((s) => s.id === currentId);
    if (currentIndex === -1) return;
    const nextIndex = Math.min(Math.max(currentIndex + offset, 0), state.slides.length - 1);
    const nextId = state.slides[nextIndex].id;
    commitSelection([nextId], nextId, nextId);
  }

  function commitSelection(ids, primaryId, anchorId) {
    const valid = new Set(state.slides.map((s) => s.id));
    const unique = [];
    const seen = new Set();
    (ids || []).forEach((id) => {
      if (valid.has(id) && !seen.has(id)) {
        seen.add(id);
        unique.push(id);
      }
    });
    let primary = primaryId && valid.has(primaryId) ? primaryId : null;
    if (!primary && unique.length) {
      primary = unique[unique.length - 1];
    }
    const anchor = anchorId && valid.has(anchorId) ? anchorId : primary;
    dispatch({ type: "set_selection", ids: unique, primaryId: primary, anchorId: anchor });
  }

  function ensureSelectionIntegrity() {
    const valid = new Set(state.slides.map((slide) => slide.id));
    const ids = (state.selectedSlideIds || []).filter((id) => valid.has(id));
    const primary = ids.length && valid.has(state.selectedSlideId) ? state.selectedSlideId : ids[0] || null;
    const anchor = ids.length && valid.has(state.selectionAnchorId) ? state.selectionAnchorId : primary;
    commitSelection(ids, primary, anchor);
  }

  function startMarqueeSelection(event) {
    if (state.viewMode !== VIEW_MODES.STORYBOARD) return;
    if (event.button !== 0) return;
    if (!storyboardCanvasRef.current) return;
    if (event.target.closest(".slides-storyboard__card")) return;
    const canvasRect = storyboardCanvasRef.current.getBoundingClientRect();
    const startX = event.clientX - canvasRect.left;
    const startY = event.clientY - canvasRect.top;
    marqueeStartRef.current = { x: startX, y: startY };
    marqueeBaseSelectionRef.current = event.ctrlKey || event.metaKey ? state.selectedSlideIds : [];
    setMarqueePreviewIds([]);
    setMarqueeBox({ x1: startX, y1: startY, x2: startX, y2: startY });
    window.addEventListener("pointermove", handleMarqueeMove);
    window.addEventListener("pointerup", handleMarqueeEnd);
    event.preventDefault();
  }

  function handleMarqueeMove(event) {
    if (!storyboardCanvasRef.current || !storyboardGridRef.current) return;
    const start = marqueeStartRef.current || { x: event.clientX, y: event.clientY };
    const canvasRect = storyboardCanvasRef.current.getBoundingClientRect();
    const currentX = event.clientX - canvasRect.left;
    const currentY = event.clientY - canvasRect.top;
    const nextBox = {
      x1: Math.min(start.x, currentX),
      y1: Math.min(start.y, currentY),
      x2: Math.max(start.x, currentX),
      y2: Math.max(start.y, currentY),
    };
    setMarqueeBox(nextBox);
    updateMarqueePreview(nextBox, event.ctrlKey || event.metaKey);
  }

  function handleMarqueeEnd(event) {
    window.removeEventListener("pointermove", handleMarqueeMove);
    window.removeEventListener("pointerup", handleMarqueeEnd);
    marqueeStartRef.current = null;
    const previews = marqueePreviewRef.current || [];
    if (previews.length) {
      const base = marqueeBaseSelectionRef.current || [];
      const final = new Set(event.ctrlKey || event.metaKey ? base : []);
      previews.forEach((id) => final.add(id));
      const ids = Array.from(final);
      const primary = ids.length ? ids[ids.length - 1] : null;
      commitSelection(ids, primary, primary);
    }
    setMarqueePreviewIds([]);
    setMarqueeBox(null);
  }

  function updateMarqueePreview(box, additive) {
    if (!box || !storyboardCanvasRef.current || !storyboardGridRef.current) return;
    const canvasRect = storyboardCanvasRef.current.getBoundingClientRect();
    const cards = Array.from(storyboardGridRef.current.querySelectorAll(".slides-storyboard__card"));
    const hits = [];
    cards.forEach((card) => {
      const rect = card.getBoundingClientRect();
      const left = rect.left - canvasRect.left;
      const right = rect.right - canvasRect.left;
      const top = rect.top - canvasRect.top;
      const bottom = rect.bottom - canvasRect.top;
      const intersects = right >= box.x1 && left <= box.x2 && bottom >= box.y1 && top <= box.y2;
      if (intersects) {
        const id = card.getAttribute("data-slide-id");
        if (id) hits.push(id);
      }
    });
    const base = additive ? marqueeBaseSelectionRef.current || [] : [];
    const preview = new Set(base);
    hits.forEach((id) => preview.add(id));
    setMarqueePreviewIds(Array.from(preview));
  }

  const selectionSet = useMemo(() => new Set(state.selectedSlideIds || []), [state.selectedSlideIds]);
  const firstSelectedIndex = state.slides.findIndex((s) => selectionSet.has(s.id));
  let lastSelectedIndex = -1;
  state.slides.forEach((slide, idx) => {
    if (selectionSet.has(slide.id)) {
      lastSelectedIndex = idx;
    }
  });

  const previewDoc = useMemo(
    () => buildPreviewDoc(selectedSlide, state.previewConfig, state.currentDeckId, promptStyleContext),
    [selectedSlide, state.previewConfig, state.currentDeckId, promptStyleContext]
  );
  const previewUsesEmptyDoc = previewDoc === EMPTY_SLIDE_HTML;
  const previewFrameRef = React.useRef(null);
  const layoutRequestIdRef = React.useRef(0);
  const storyboardCanvasRef = React.useRef(null);
  const storyboardGridRef = React.useRef(null);
  const marqueeBaseSelectionRef = React.useRef([]);
  const marqueeStartRef = React.useRef(null);
  const [marqueeBox, setMarqueeBox] = React.useState(null);
  const [marqueePreviewIds, setMarqueePreviewIds] = React.useState([]);
  const [previewOverlayMetrics, setPreviewOverlayMetrics] = React.useState(null);
  const marqueePreviewRef = React.useRef([]);

  useEffect(() => {
    marqueePreviewRef.current = marqueePreviewIds;
  }, [marqueePreviewIds]);

  useEffect(() => {
    const frame = previewFrameRef.current;
    if (!frame) return;
    if (previewUsesEmptyDoc) {
      const parent = frame.parentElement;
      if (parent?.style && typeof parent.style.removeProperty === "function") {
        parent.style.removeProperty("--slides-preview-aspect-ratio");
      }
      setPreviewOverlayMetrics(null);
      return;
    }
    let imageNode = null;
    let resizeObserver = null;
    let frameWindow = null;
    let rafId = 0;
    const syncPreviewMetrics = () => {
      window.cancelAnimationFrame(rafId);
      rafId = window.requestAnimationFrame(() => {
        try {
          const doc = frame.contentDocument;
          if (doc) {
            applyPreviewFit(doc, frame);
          }
          if (selectedSlideIsImageBacked) {
            setPreviewOverlayMetrics(measurePreviewImageOverlayMetrics(frame));
          } else {
            setPreviewOverlayMetrics(null);
          }
        } catch (error) {
          setPreviewOverlayMetrics(null);
        }
      });
    };
    const bindImageLoad = () => {
      try {
        const nextImage = frame.contentDocument?.querySelector?.(".slide-container img, img") || null;
        if (imageNode === nextImage) {
          return;
        }
        if (imageNode && typeof imageNode.removeEventListener === "function") {
          imageNode.removeEventListener("load", syncPreviewMetrics);
        }
        imageNode = nextImage;
        if (imageNode && typeof imageNode.addEventListener === "function") {
          imageNode.addEventListener("load", syncPreviewMetrics);
        }
      } catch (error) {
        imageNode = null;
      }
    };
    const handleLoad = () => {
      bindImageLoad();
      syncPreviewMetrics();
    };
    frame.addEventListener("load", handleLoad);
    handleLoad();
    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(() => {
        syncPreviewMetrics();
      });
      resizeObserver.observe(frame);
      if (frame.parentElement) {
        resizeObserver.observe(frame.parentElement);
      }
    }
    try {
      frameWindow = frame.contentWindow;
      if (frameWindow) {
        frameWindow.addEventListener("scroll", syncPreviewMetrics);
      }
    } catch (error) {
      frameWindow = null;
    }
    window.addEventListener("resize", syncPreviewMetrics);
    return () => {
      frame.removeEventListener("load", handleLoad);
      if (imageNode && typeof imageNode.removeEventListener === "function") {
        imageNode.removeEventListener("load", syncPreviewMetrics);
      }
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
      if (frameWindow) {
        frameWindow.removeEventListener("scroll", syncPreviewMetrics);
      }
      window.removeEventListener("resize", syncPreviewMetrics);
      window.cancelAnimationFrame(rafId);
    };
  }, [previewDoc, previewUsesEmptyDoc, selectedSlideIsImageBacked]);

  useEffect(() => {
    function handleKeyDown(event) {
      if (state.viewMode !== VIEW_MODES.STORYBOARD) return;
      if (!state.slides.length) return;
      if (["ArrowLeft", "ArrowUp"].includes(event.key)) {
        event.preventDefault();
        moveSelectionBy(-1);
      } else if (["ArrowRight", "ArrowDown"].includes(event.key)) {
        event.preventDefault();
        moveSelectionBy(1);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [state.viewMode, state.slides, state.selectedSlideId, state.selectedSlideIds]);

  function findFirstContentSlide() {
    const firstContent = state.slides.find((slide) => slide.kind !== "sectionHeader");
    if (firstContent) {
      return firstContent.id;
    }
    return state.slides.length ? state.slides[0].id : "";
  }

  function findSection(sectionId) {
    return state.sections.find((section) => section.id === sectionId) || null;
  }

  function findSubsection(sectionId, subsectionId) {
    const section = findSection(sectionId);
    if (!section || !Array.isArray(section.subsections)) {
      return null;
    }
    return section.subsections.find((sub) => sub.id === subsectionId) || null;
  }

  function insertSectionHeader(sectionId, subsectionId = null) {
    if (!sectionId) {
      return;
    }
    const section = findSection(sectionId);
    if (!section) {
      dispatch({ type: "set_status", message: `Unknown section ${sectionId}`, isError: true });
      return;
    }
    const target = subsectionId
      ? findSubsection(sectionId, subsectionId)?.startSlide
      : section.startSlide;
    if (!target) {
      dispatch({ type: "set_status", message: "Select a start slide before inserting a header.", isError: true });
      return;
    }
    const header = normalizeEditorSlide({
      id: nextSlideId(state.slides),
      titleHtml: "",
      bodyHtml: "",
      kind: "sectionHeader",
      sectionId,
      subsectionId: subsectionId || null,
    });
    let slides = [...state.slides];
    const index = slides.findIndex((slide) => slide.id === target);
    if (index === -1) {
      slides.push(header);
    } else {
      slides.splice(index, 0, header);
    }
    dispatch({ type: "set_slides", slides });
    commitSelection([header.id], header.id, header.id);
    dispatch({ type: "set_status", message: "Inserted section header.", isError: false });
  }

  function convertSelectionToHeader(sectionId, subsectionId = null) {
    const section = findSection(sectionId);
    if (!section) {
      dispatch({ type: "set_status", message: `Unknown section ${sectionId}`, isError: true });
      return;
    }
    const targetSlide = state.slides.find((slide) => slide.id === state.selectedSlideId);
    if (!targetSlide || targetSlide.kind === "sectionHeader") {
      dispatch({ type: "set_status", message: "Select a non-header slide to convert.", isError: true });
      return;
    }
    let slides = [...state.slides];
    const sourceIndex = slides.findIndex((s) => s.id === targetSlide.id);
    const targetId = subsectionId
      ? findSubsection(sectionId, subsectionId)?.startSlide || section.startSlide
      : section.startSlide || targetSlide.id;
    slides[sourceIndex] = {
      ...targetSlide,
      kind: "sectionHeader",
      sectionId,
      subsectionId: subsectionId || null,
      titleHtml: "",
      bodyHtml: "",
    };
    if (targetId && targetId !== targetSlide.id) {
      const headerSlide = slides[sourceIndex];
      slides.splice(sourceIndex, 1);
      const insertIndex = slides.findIndex((s) => s.id === targetId);
      if (insertIndex !== -1) {
        slides.splice(insertIndex, 0, headerSlide);
      } else {
        slides.splice(sourceIndex, 0, headerSlide);
      }
    }
    dispatch({ type: "set_slides", slides });
    commitSelection([targetSlide.id], targetSlide.id, targetSlide.id);
    dispatch({ type: "set_status", message: "Converted slide to section header.", isError: false });
  }

  function handleConvertFromStoryboard(slideId) {
    if (!slideId) {
      return;
    }
    commitSelection([slideId], slideId, slideId);
    const sectionIds = state.sections.map((section) => section.id).filter(Boolean);
    let sectionId = null;
    if (sectionIds.length === 1) {
      sectionId = sectionIds[0];
    } else if (sectionIds.length > 1) {
      sectionId = window.prompt("Convert to which section?", sectionIds[0]) || null;
    }
    if (!sectionId) {
      dispatch({ type: "set_status", message: "Select a section before converting.", isError: true });
      return;
    }
    const section = findSection(sectionId);
    if (!section) {
      dispatch({ type: "set_status", message: `Unknown section ${sectionId}`, isError: true });
      return;
    }
    let subsectionId = null;
    if (section.subsections && section.subsections.length) {
      const choices = section.subsections.map((sub) => sub.id).join(", ");
      const chosen =
        window.prompt(
          `Subsection for this header? Leave empty for section start.${choices ? ` Options: ${choices}` : ""}`,
          section.subsections[0].id
        ) || "";
      if (chosen) {
        const match = section.subsections.find((sub) => sub.id === chosen);
        if (!match) {
          dispatch({ type: "set_status", message: `Unknown subsection ${chosen}`, isError: true });
          return;
        }
        subsectionId = chosen;
      }
    }
    convertSelectionToHeader(sectionId, subsectionId);
  }

  function addSubsection(sectionId) {
    const section = findSection(sectionId);
    if (!section) return;
    const baseIndex = (section.subsections?.length || 0) + 1;
    const defaultId = `${section.id || "Sub"}${baseIndex}`;
    const newSub = {
      id: defaultId,
      title: defaultId,
      startSlide: section.startSlide || findFirstContentSlide(),
    };
    const sections = state.sections.map((s) =>
      s.id === sectionId ? { ...s, subsections: [...(s.subsections || []), newSub] } : s
    );
    dispatch({ type: "set_sections", sections });
  }

  function updateSubsection(sectionId, subsectionId, patch) {
    const sections = state.sections.map((section) => {
      if (section.id !== sectionId) return section;
      const subsections = (section.subsections || []).map((sub) => {
        if (sub.id !== subsectionId) return sub;
        return { ...sub, ...patch };
      });
      return { ...section, subsections };
    });
    let slides = state.slides;
    if (patch.id && patch.id !== subsectionId) {
      slides = slides.map((slide) => {
        if (
          slide.kind === "sectionHeader" &&
          slide.sectionId === sectionId &&
          slide.subsectionId === subsectionId
        ) {
          return { ...slide, subsectionId: patch.id };
        }
        return slide;
      });
      dispatch({ type: "set_slides", slides });
    }
    dispatch({ type: "set_sections", sections });
  }

  function removeSubsection(sectionId, subsectionId) {
    const sections = state.sections.map((section) => {
      if (section.id !== sectionId) return section;
      const subsections = (section.subsections || []).filter((sub) => sub.id !== subsectionId);
      return { ...section, subsections };
    });
    const slides = state.slides.filter(
      (slide) => !(slide.kind === "sectionHeader" && slide.sectionId === sectionId && slide.subsectionId === subsectionId)
    );
    dispatch({ type: "set_sections", sections });
    dispatch({ type: "set_slides", slides });
    ensureSelectionIntegrity();
    dispatch({ type: "set_status", message: `Removed subsection ${subsectionId}.`, isError: false });
  }

  function reorderSlides(sourceId, targetId) {
    if (!sourceId || !targetId || sourceId === targetId) return;
    const selectedSet = new Set(state.selectedSlideIds);
    const sources = selectedSet.has(sourceId) && selectedSet.size ? Array.from(selectedSet) : [sourceId];
    const sourceSet = new Set(sources);
    const slides = state.slides;
    const targetIndex = slides.findIndex((slide) => slide.id === targetId);
    if (targetIndex === -1) return;
    const moving = [];
    const remaining = [];
    slides.forEach((slide) => {
      if (sourceSet.has(slide.id)) {
        moving.push(slide);
      } else {
        remaining.push(slide);
      }
    });
    const insertIndex = remaining.findIndex((slide) => slide.id === targetId);
    if (insertIndex === -1) return;
    const updated = [...remaining.slice(0, insertIndex), ...moving, ...remaining.slice(insertIndex)];
    dispatch({ type: "set_slides", slides: updated });
    dispatch({
      type: "set_selection",
      ids: state.selectedSlideIds,
      primaryId: state.selectedSlideId,
      anchorId: state.selectionAnchorId,
    });
    dispatch({ type: "set_status", message: "Reordered slides.", isError: false });
  }

  function promoteSelected() {
    const ids = state.selectedSlideIds || [];
    if (!ids.length) return;
    const selectionSet = new Set(ids);
    const slides = state.slides;
    const firstIndex = slides.findIndex((s) => selectionSet.has(s.id));
    if (firstIndex <= 0) {
      dispatch({ type: "set_status", message: "Selected slides are already at the top.", isError: false });
      return;
    }
    const selectedSlides = slides.filter((s) => selectionSet.has(s.id));
    const remainingSlides = slides.filter((s) => !selectionSet.has(s.id));
    const previousSlide = slides[firstIndex - 1];
    let insertIndex = remainingSlides.findIndex((s) => s.id === previousSlide.id);
    if (insertIndex === -1) insertIndex = 0;
    const updated = [
      ...remainingSlides.slice(0, insertIndex),
      ...selectedSlides,
      ...remainingSlides.slice(insertIndex),
    ];
    dispatch({ type: "set_slides", slides: updated });
    dispatch({ type: "set_selection", ids, primaryId: state.selectedSlideId, anchorId: state.selectionAnchorId });
    dispatch({ type: "set_status", message: "Promoted selected slides.", isError: false });
  }

  function demoteSelected() {
    const ids = state.selectedSlideIds || [];
    if (!ids.length) return;
    const selectionSet = new Set(ids);
    const slides = state.slides;
    let lastIndex = -1;
    slides.forEach((slide, idx) => {
      if (selectionSet.has(slide.id)) {
        lastIndex = idx;
      }
    });
    if (lastIndex === -1 || lastIndex >= slides.length - 1) {
      dispatch({ type: "set_status", message: "Selected slides are already at the end.", isError: false });
      return;
    }
    const selectedSlides = slides.filter((s) => selectionSet.has(s.id));
    const remainingSlides = slides.filter((s) => !selectionSet.has(s.id));
    const nextSlide = slides[lastIndex + 1];
    let insertIndex = remainingSlides.findIndex((s) => s.id === nextSlide.id);
    if (insertIndex === -1) insertIndex = remainingSlides.length;
    const updated = [
      ...remainingSlides.slice(0, insertIndex + 1),
      ...selectedSlides,
      ...remainingSlides.slice(insertIndex + 1),
    ];
    dispatch({ type: "set_slides", slides: updated });
    dispatch({ type: "set_selection", ids, primaryId: state.selectedSlideId, anchorId: state.selectionAnchorId });
    dispatch({ type: "set_status", message: "Demoted selected slides.", isError: false });
  }

  const bulkSelectionCount = state.selectedSlideIds.length;

  function handleConcatWithMode({ interleaveByIndex, interleaveGuide = "first" }) {
    if (state.concatenating) return;
    const name = window.prompt("Name for the combined deck", state.currentDeckId ? `${state.currentDeckId}-combined` : "deck");
    if (!name) return;
    const selected = window.prompt("Enter deck ids to combine (comma-separated)", state.currentDeckId || "");
    if (!selected) return;
    const deckIds = selected
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (!deckIds.length) {
      dispatch({ type: "set_status", message: "Select at least one deck to combine.", isError: true });
      return;
    }
    dispatch({ type: "set_concatenating", value: true });
    concatenateDecks(name.trim(), deckIds, {
      interleaveByIndex,
      interleaveGuide,
      deleteSourceDecks: true,
      deleteMode: "archive",
    })
      .then((deck) => {
        const slides = (deck.slides || []).map(normalizeEditorSlide);
        const sections = (deck.sections || []).map(normalizeSection);
        const archived = Array.isArray(deck.archivedSourceDecks) ? deck.archivedSourceDecks : [];
        dispatch({
          type: "set_deck",
          deckId: deck.deckId,
          promptStyle: deck.promptStyle,
          slides,
          sections,
          thumbnails: deck.thumbnails || {},
          hasLayout: !!deck.hasLayout,
        });
        const archiveMessage = archived.length ? ` Archived ${archived.join(", ")}.` : "";
        dispatch({
          type: "set_status",
          message: `Created deck ${deck.deckId}.${archiveMessage}`,
          isError: false,
        });
        return refreshDeckList({ selectedDeckId: deck.deckId });
      })
      .catch((error) => {
        const prefix = interleaveByIndex ? "Failed to combine and order decks" : "Failed to combine decks";
        dispatch({ type: "set_status", message: `${prefix}: ${error.message}`, isError: true });
      })
      .finally(() => dispatch({ type: "set_concatenating", value: false }));
  }

  function handleConcat() {
    handleConcatWithMode({ interleaveByIndex: false });
  }

  function handleConcatOrdered() {
    if (state.concatenating) return;
    const defaultGuide = "longest";
    const response = window.prompt("Guide deck for ordering: longest or shortest?", defaultGuide);
    if (response === null) return;
    const normalized = response.trim().toLowerCase();
    const interleaveGuide =
      normalized === "shortest" ? "shortest" : normalized === "longest" || !normalized ? "longest" : null;
    if (!interleaveGuide) {
      dispatch({ type: "set_status", message: "Guide must be 'longest' or 'shortest'.", isError: true });
      return;
    }
    handleConcatWithMode({ interleaveByIndex: true, interleaveGuide });
  }

  function handleArchiveDeck() {
    if (state.deleting || !state.currentDeckId) return;
    const deckId = state.currentDeckId;
    const confirmed = window.confirm(
      `Are you totally sure you want to delete ${deckId}? This archives the deck on the server.`
    );
    if (!confirmed) return;
    const typed = window.prompt(`Type "${deckId}" to confirm deletion.`);
    if (typed !== deckId) {
      dispatch({ type: "set_status", message: "Deck deletion cancelled.", isError: false });
      return;
    }
    dispatch({ type: "set_deleting", value: true });
    archiveDeck(deckId)
      .then(() => {
        dispatch({ type: "set_status", message: `Archived deck ${deckId}.`, isError: false });
        dispatch({
          type: "set_deck",
          deckId: null,
          promptStyle: NOTEBOOKLM_DEFAULT_STYLE_KEY,
          slides: [],
          sections: [],
          thumbnails: {},
          hasLayout: false,
          selectedSlideId: null,
          selectedSlideIds: [],
          selectionAnchorId: null,
        });
        return refreshDeckList({ selectedDeckId: null });
      })
      .catch((error) => {
        dispatch({ type: "set_status", message: `Failed to delete deck: ${error.message}`, isError: true });
      })
      .finally(() => dispatch({ type: "set_deleting", value: false }));
  }

  function handleUploadPdf(processingMode = "ocr") {
    if (state.uploading || state.uploadingPptxTemplate || state.pendingUploadFile) {
      dispatch({ type: "set_status", message: "Please wait for the current upload to finish.", isError: false });
      return;
    }
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".pdf,application/pdf";
    input.multiple = false;
    input.style.display = "none";
    document.body.appendChild(input);
    input.addEventListener("change", (event) => {
      const file = (event.target && event.target.files && event.target.files[0]) || null;
      if (!file) {
        document.body.removeChild(input);
        return;
      }
      const deckId = suggestDeckIdFromFiles([file]);
      dispatch({ type: "set_pending_upload", file, deckId, processingMode });
      dispatch({ type: "set_upload_template_choice", value: "" });
      document.body.removeChild(input);
    });
    input.click();
  }

  function handleUploadPptxTemplate() {
    if (state.uploading || state.uploadingPptxTemplate) {
      dispatch({ type: "set_status", message: "Please wait for the current upload to finish.", isError: false });
      return;
    }
    const input = document.createElement("input");
    input.type = "file";
    input.accept =
      ".pptx,.potx,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/vnd.openxmlformats-officedocument.presentationml.template";
    input.multiple = false;
    input.style.display = "none";
    document.body.appendChild(input);
    input.addEventListener("change", (event) => {
      const file = (event.target && event.target.files && event.target.files[0]) || null;
      if (!file) {
        document.body.removeChild(input);
        return;
      }
      dispatch({ type: "set_uploading_pptx_template", value: true });
      uploadPptxTemplate(file, { setDefault: true })
        .then((template) => {
          dispatch({
            type: "set_status",
            message: `Uploaded PPTX template ${template.name}.`,
            isError: false,
          });
          return refreshPptxTemplateList({ selectedTemplateId: template.templateId });
        })
        .catch((error) => {
          dispatch({
            type: "set_status",
            message: `PPTX template upload failed: ${error.message}`,
            isError: true,
          });
        })
        .finally(() => {
          dispatch({ type: "set_uploading_pptx_template", value: false });
          document.body.removeChild(input);
        });
    });
    input.click();
  }

  function handleSetDefaultPptxTemplate(templateId) {
    const normalizedTemplateId = String(templateId || "").trim();
    if (!normalizedTemplateId || state.uploadingPptxTemplate) {
      return;
    }
    dispatch({ type: "set_uploading_pptx_template", value: true });
    setDefaultPptxTemplate(normalizedTemplateId)
      .then((resp) => {
        dispatch({
          type: "set_pptx_templates",
          templates: Array.isArray(resp?.templates) ? resp.templates : [],
          defaultTemplateId:
            typeof resp?.defaultTemplateId === "string" ? resp.defaultTemplateId : null,
        });
        dispatch({
          type: "set_upload_template_choice",
          value: templateChoiceForId(normalizedTemplateId),
        });
        dispatch({
          type: "set_status",
          message: "Default PPTX template updated.",
          isError: false,
        });
      })
      .catch((error) => {
        dispatch({
          type: "set_status",
          message: `Failed to update default PPTX template: ${error.message}`,
          isError: true,
        });
      })
      .finally(() => dispatch({ type: "set_uploading_pptx_template", value: false }));
  }

  function cancelPendingUpload() {
    dispatch({ type: "set_pending_upload", file: null, deckId: null, processingMode: "ocr" });
    dispatch({ type: "set_upload_template_choice", value: "" });
  }

  function submitPendingUpload({ processingMode } = {}) {
    if (state.uploading || !state.pendingUploadFile || !state.pendingUploadDeckId) {
      return;
    }
    const resolvedProcessingMode = processingMode || state.pendingUploadProcessingMode || "ocr";
    const runOcr = resolvedProcessingMode === "ocr";
    const templateChoice = resolveEffectiveUploadTemplateChoice(state);
    const selectedTemplateId = templateIdFromChoice(templateChoice);
    const useUniformTemplate = templateChoice === "uniform";
    dispatch({
      type: "set_status",
      message: runOcr
        ? `Uploading PDF deck ${state.pendingUploadDeckId.trim()} and starting deck processing.`
        : `Uploading PDF deck ${state.pendingUploadDeckId.trim()}.`,
      isError: false,
    });
    dispatch({ type: "set_uploading", value: true });
    uploadPdfDeck(state.pendingUploadDeckId.trim(), state.pendingUploadFile, {
      lang: state.lang,
      runOcr,
      promptStyle: NOTEBOOKLM_DEFAULT_STYLE_KEY,
      pptxTemplateId: selectedTemplateId || null,
      useUniformTemplate,
    })
      .then((deck) => {
        const slides = (deck.slides || []).map(normalizeEditorSlide);
        const sections = (deck.sections || []).map(normalizeSection);
        dispatch({
          type: "set_deck",
          deckId: deck.deckId,
          promptStyle: deck.promptStyle,
          slides,
          sections,
          thumbnails: deck.thumbnails || {},
          hasLayout: !!deck.hasLayout,
        });
        dispatch({
          type: "set_status",
          message: runOcr
            ? `Uploaded PDF deck ${deck.deckId}. Starting server-side deck processing.`
            : `Uploaded PDF deck ${deck.deckId}.`,
          isError: false,
        });
        if (!runOcr) {
          return refreshDeckList({ selectedDeckId: deck.deckId });
        }
        return Promise.resolve()
          .then(() => {
            return syncDeckOcrProgress(deck.deckId, slides);
          })
          .then((ocrStatus) => {
            const statusValue = String(ocrStatus?.status || "").trim().toLowerCase();
            if (statusValue === "completed") {
              dispatch({
                type: "set_status",
                message: `Uploaded PDF deck ${deck.deckId}. Deck processing complete.`,
                isError: false,
              });
              invalidateDeckDebugPayloads(deck.deckId);
              return ensureDeckLayoutPayload(deck.deckId, slides);
            }
            if (statusValue === "failed") {
              dispatch({
                type: "set_status",
                message: ocrStatus?.error || `Deck processing failed for ${deck.deckId}.`,
                isError: true,
              });
              return null;
            }
            if (statusValue === "skipped") {
              dispatch({
                type: "set_status",
                message: ocrStatus?.message || "Deck processing skipped for this deck.",
                isError: false,
              });
            }
            return null;
          })
          .then(() => refreshDeckList({ selectedDeckId: deck.deckId }));
      })
      .catch((error) => {
        dispatch({ type: "set_status", message: `Upload failed: ${error.message}`, isError: true });
      })
      .finally(() => {
        dispatch({ type: "set_uploading", value: false });
        dispatch({ type: "set_pending_upload", file: null, deckId: null, processingMode: "ocr" });
        dispatch({ type: "set_upload_template_choice", value: "" });
      });
  }

  function confirmPendingUploadWithProcessing() {
    submitPendingUpload({ processingMode: "ocr" });
  }

  function confirmPendingUploadWithoutProcessing() {
    submitPendingUpload({ processingMode: "upload_only" });
  }

  function suggestDeckIdFromFiles(files) {
    if (!files.length) return `deck-${Date.now()}`;
    const first = files[0];
    const path = first.webkitRelativePath || first.name || "deck";
    let base = path.split("/")[0] || path;
    if (!first.webkitRelativePath && base.includes(".")) {
      base = base.replace(/\.[^.]+$/, "");
    }
    base = base.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
    if (!base) {
      base = `deck-${Date.now()}`;
    }
    return base;
  }

  function handleImport() {
    if (!state.currentDeckId) {
      dispatch({ type: "set_status", message: "Load a deck before importing slides.", isError: true });
      return;
    }
    const decks = state.decks.map((d) => d.deckId).filter((id) => id !== state.currentDeckId);
    if (!decks.length) {
      dispatch({ type: "set_status", message: "Upload or load another deck to import from.", isError: true });
      return;
    }
    const deckId = window.prompt("Import from which deck?", decks[0]);
    if (!deckId) return;
    const deck = state.decks.find((d) => d.deckId === deckId);
    if (!deck || !deck.slides?.length) {
      dispatch({ type: "set_status", message: "Selected deck has no slides to import.", isError: true });
      return;
    }
    const slideChoices = deck.slides.map((s) => s.id).join(", ");
    const slideId = window.prompt(`Slide id to import from ${deckId}? Choices: ${slideChoices}`, deck.slides[0].id);
    if (!slideId) return;
    const payload = {
      sourceDeckId: deckId,
      sourceSlideId: slideId,
      afterSlideId: state.selectedSlideId,
      currentOrder: state.slides.map((s) => s.id),
    };
    importSlideApi(state.currentDeckId, payload)
      .then((response) => {
        const slide = normalizeEditorSlide(response.slide);
        const order = response.order || [];
        const existing = new Map(state.slides.map((item) => [item.id, item]));
        existing.set(slide.id, slide);
        const updatedSlides = order.map((id) => existing.get(id)).filter(Boolean);
        dispatch({
          type: "set_deck",
          deckId: state.currentDeckId,
          promptStyle: promptStyleContext.styleKey,
          slides: updatedSlides,
          sections: state.sections,
          thumbnails: state.thumbnails,
          hasLayout: state.hasLayout,
        });
        commitSelection([slide.id], slide.id, slide.id);
        dispatch({ type: "set_status", message: `Imported ${slide.id} from ${deckId}.`, isError: false });
      })
      .catch((error) => {
        dispatch({ type: "set_status", message: `Import failed: ${error.message}`, isError: true });
      });
  }

  function handlePrint() {
    if (!state.currentDeckId) {
      dispatch({ type: "set_status", message: "Load a deck before printing.", isError: true });
      return;
    }
    if (state.pptxExporting) {
      dispatch({ type: "set_status", message: "PPTX export already in progress.", isError: false });
      return;
    }
    if (state.printing) {
      dispatch({ type: "set_status", message: "PDF export already in progress.", isError: false });
      return;
    }
    dispatch({ type: "set_printing", value: true, jobId: null });
    dispatch({ type: "set_status", message: `Generating PDF for ${state.currentDeckId}…`, isError: false });
    requestPrint(state.currentDeckId)
      .then((data) => {
        if (!data || !data.jobId) {
          throw new Error("PDF job did not return an identifier.");
        }
        dispatch({ type: "set_printing", value: true, jobId: data.jobId });
        pollPrintJob({
          jobId: data.jobId,
          pollPrint,
          fileName: `${state.currentDeckId || "deck"}.pdf`,
          onStatus: (message, isError) => dispatch({ type: "set_status", message, isError }),
          onFinalize: () => dispatch({ type: "set_printing", value: false, jobId: null }),
        });
      })
      .catch((error) => {
        dispatch({ type: "set_status", message: `PDF export failed: ${error.message}`, isError: true });
        dispatch({ type: "set_printing", value: false, jobId: null });
      });
  }

  function handlePptxExport(source = "rendered") {
    if (!state.currentDeckId) {
      dispatch({ type: "set_status", message: "Load a deck before exporting PPTX.", isError: true });
      return;
    }
    if (state.printing) {
      dispatch({ type: "set_status", message: "PDF export already in progress.", isError: false });
      return;
    }
    if (state.pptxExporting) {
      dispatch({ type: "set_status", message: "PPTX export already in progress.", isError: false });
      return;
    }
    dispatch({ type: "set_pptx_exporting", value: true, jobId: null });
    const fromTemplate = source === "template";
    const fileName = `${state.currentDeckId || "deck"}.pptx`;
    dispatch({
      type: "set_status",
      message: fromTemplate
        ? `Generating template PPTX for ${state.currentDeckId}…`
        : `Generating PPTX for ${state.currentDeckId}…`,
      isError: false,
    });
    requestPptxExport(state.currentDeckId, source)
      .then((data) => {
        if (!data || !data.jobId) {
          throw new Error("PPTX job did not return an identifier.");
        }
        dispatch({ type: "set_pptx_exporting", value: true, jobId: data.jobId });
        pollPrintJob({
          jobId: data.jobId,
          pollPrint: pollPptxExport,
          fileName,
          onStatus: (message, isError) => dispatch({ type: "set_status", message, isError }),
          onFinalize: () => dispatch({ type: "set_pptx_exporting", value: false, jobId: null }),
          successMessage: "Downloaded PPTX.",
          errorMessage: "PPTX export failed",
          downloadErrorMessage: "Unable to download PPTX.",
        });
      })
      .catch((error) => {
        dispatch({ type: "set_status", message: `PPTX export failed: ${error.message}`, isError: true });
        dispatch({ type: "set_pptx_exporting", value: false, jobId: null });
      });
  }

  function handleAddSection() {
    if (!state.slides.length) {
      dispatch({ type: "set_status", message: "Add at least one slide before creating sections.", isError: true });
      return;
    }
    const baseIndex = state.sections.length + 1;
    const defaultId = `Section${baseIndex}`;
    const firstSlide = findFirstContentSlide();
    const newSection = {
      id: defaultId,
      title: defaultId,
      startSlide: firstSlide,
      subsections: [],
    };
    const nextSections = [...state.sections, newSection];
    dispatch({ type: "set_sections", sections: nextSections });
    dispatch({ type: "set_status", message: `Added section ${defaultId}.`, isError: false });
  }

  function updateSection(sectionId, patch) {
    const sections = state.sections.map((section) => {
      if (section.id !== sectionId) return section;
      return { ...section, ...patch };
    });
    let slides = state.slides;
    if (patch.id && patch.id !== sectionId) {
      slides = slides.map((slide) => {
        if (slide.kind === "sectionHeader" && slide.sectionId === sectionId) {
          return { ...slide, sectionId: patch.id };
        }
        return slide;
      });
      dispatch({ type: "set_slides", slides });
    }
    dispatch({ type: "set_sections", sections });
    dispatch({ type: "set_status", message: "Updated section.", isError: false });
  }

  function removeSection(sectionId) {
    const sections = state.sections.filter((section) => section.id !== sectionId);
    const slides = state.slides.filter((slide) => !(slide.kind === "sectionHeader" && slide.sectionId === sectionId));
    let nextSelection = state.selectedSlideId;
    if (nextSelection && !slides.some((s) => s.id === nextSelection)) {
      nextSelection = slides.length ? slides[0].id : null;
    }
    dispatch({ type: "set_sections", sections });
    dispatch({ type: "set_slides", slides });
    commitSelection(nextSelection ? [nextSelection] : [], nextSelection, nextSelection);
    dispatch({ type: "set_status", message: `Removed section ${sectionId}.`, isError: false });
  }

  const isStoryboard = state.viewMode === VIEW_MODES.STORYBOARD;
  const effectiveUploadTemplateChoice = resolveEffectiveUploadTemplateChoice(state);
  const effectiveUploadTemplateId = templateIdFromChoice(effectiveUploadTemplateChoice);
  const hasSavedPptxTemplates = state.pptxTemplates.length > 0;
  return (
    <section
      className="slides-editor"
      aria-label={state.pageLabel || "Slide editor"}
      data-page-label={state.pageLabel}
      style={buildNotebooklmCssVars(promptStyleContext)}
    >
      <style>
        {`
          .slides-editor .ghost-button.slides-editor__pill-btn {
            border: 1px solid rgba(209, 213, 219, 0.6) !important;
            border-radius: 999px !important;
            padding: 6px 14px !important;
            min-height: 44px !important;
            background: rgba(255, 255, 255, 0.94) !important;
            color: #1f2937 !important;
            font-family: var(--mparanza-pill-font-family) !important;
            font-size: var(--mparanza-pill-font-size, 14px) !important;
            font-weight: var(--mparanza-pill-font-weight, 400) !important;
            line-height: var(--mparanza-pill-line-height, 1.2) !important;
            cursor: pointer !important;
            transition: all 120ms ease !important;
            text-decoration: none !important;
            box-shadow: none !important;
          }
          .slides-editor .ghost-button.slides-editor__pill-btn:hover:not(:disabled) {
            border-color: rgba(148, 163, 184, 0.9) !important;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.12) !important;
          }
          .slides-editor .ghost-button.slides-editor__pill-btn:focus-visible {
            outline: none !important;
            border-color: #0d6efd !important;
            box-shadow: 0 0 0 3px rgba(13, 110, 253, 0.18) !important;
          }
          .slides-editor .ghost-button.slides-editor__pill-btn:disabled {
            border-color: rgba(209, 213, 219, 0.4) !important;
            opacity: 0.5 !important;
            cursor: default !important;
            box-shadow: none !important;
          }
          .slides-editor .slides-editor__prompt-style-pill-btn {
            border: 1px solid #e5e7eb;
            border-radius: 999px;
            padding: 6px 10px;
            min-height: 44px;
            background: #fff;
            color: #111827;
            cursor: pointer;
            font-family: var(--mparanza-pill-font-family);
            font-size: var(--mparanza-pill-font-size, 14px);
            font-weight: var(--mparanza-pill-font-weight, 400);
            line-height: var(--mparanza-pill-line-height, 1.2);
            transition: all 120ms ease;
          }
          .slides-editor .slides-editor__prompt-style-pill-btn:hover:not(:disabled) {
            border-color: #cbd5e1;
          }
          .slides-editor .slides-editor__prompt-style-pill-btn:focus-visible {
            outline: none;
            border-color: #0d6efd;
            box-shadow: 0 0 0 3px rgba(13, 110, 253, 0.18);
          }
          .slides-editor .slides-editor__prompt-style-pill-btn.is-active {
            border-color: #111827;
            background: #111827;
            color: #fff;
          }
          .slides-editor .slides-editor__prompt-style-pill-btn:disabled {
            opacity: 0.5;
            cursor: default;
          }
        `}
      </style>
      <header className="slides-editor__header">
        <div className="slides-editor__header-heading">
          <h1 className="slides-editor__title">{state.pageLabel || "Slide editor"}</h1>
        </div>
        <div className="slides-editor__toolbar">
          <div className="slides-editor__toolbar-card">
            <div className="slides-editor__toolbar-row">
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={() => handleUploadPdf("upload_only")}
                disabled={
                  state.uploading ||
                  state.uploadingPptxTemplate ||
                  state.pendingUploadFile ||
                  contentProcessingBlocked
                }
                data-tooltip={tooltip(
                  copy,
                  "upload_pdf_deck",
                  "Upload a PDF deck without OCR or slide understanding.",
                )}
              >
                {label(copy, "upload_pdf_deck", "Upload PDF deck")}
              </button>
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={() => handleUploadPdf("ocr")}
                disabled={
                  state.uploading ||
                  state.uploadingPptxTemplate ||
                  state.pendingUploadFile ||
                  contentProcessingBlocked
                }
                data-tooltip={tooltip(
                  copy,
                  "upload_pdf_with_ocr_deck",
                  "Upload a PDF deck and start OCR and slide understanding.",
                )}
              >
                {label(copy, "upload_pdf_with_ocr_deck", "Upload and OCR PDF deck")}
              </button>
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={handleUploadPptxTemplate}
                disabled={state.uploading || state.uploadingPptxTemplate}
              >
                {state.uploadingPptxTemplate
                  ? label(copy, "upload_pptx_template_busy", "Uploading PPTX template…")
                  : label(copy, "upload_pptx_template", "Upload PPTX template")}
              </button>
            </div>
            {state.pendingUploadFile && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  flexWrap: "wrap",
                  padding: "6px 10px",
                  border: "1px solid #e5e7eb",
                  borderRadius: 10,
                  background: "#f8fafc",
                  marginTop: 8,
                }}
              >
                <div style={{ fontSize: 12, color: "#111827", fontWeight: 600 }}>
                  {state.pendingUploadFile.name}
                </div>
                <div style={{ fontSize: 12, color: "#475467", width: "100%" }}>
                  {state.pendingUploadProcessingMode === "ocr"
                    ? label(
                        copy,
                        "pending_upload_mode_ocr",
                        "This upload will start OCR and slide understanding after the deck is created.",
                      )
                    : label(
                        copy,
                        "pending_upload_mode_plain",
                        "This upload will only create the deck. OCR and slide understanding will stay off.",
                      )}
                </div>
                <div style={{ width: "100%", display: "grid", gap: 6 }}>
                  <div style={{ fontSize: 12, color: "#475467", fontWeight: 600 }}>
                    {label(copy, "pptx_template_label", "Target PPTX template")}
                  </div>
                  <div
                    role="group"
                    aria-label={label(copy, "pptx_template_label", "Target PPTX template")}
                    style={{ display: "flex", flexWrap: "wrap", gap: 6 }}
                  >
                    <button
                      type="button"
                      className={`slides-editor__prompt-style-pill-btn${
                        effectiveUploadTemplateChoice === "uniform" ? " is-active" : ""
                      }`}
                      aria-pressed={effectiveUploadTemplateChoice === "uniform"}
                      disabled={state.uploading || state.uploadingPptxTemplate}
                      onClick={() =>
                        dispatch({ type: "set_upload_template_choice", value: "uniform" })
                      }
                    >
                      {label(copy, "uniform_template", "Uniform")}
                    </button>
                    {state.pptxTemplates.map((template) => {
                      const choice = templateChoiceForId(template.templateId);
                      const isActive = effectiveUploadTemplateChoice === choice;
                      const templateLabel = template.isDefault
                        ? `${template.name} (${label(copy, "default_label", "Default")})`
                        : template.name;
                      return (
                        <button
                          key={template.templateId}
                          type="button"
                          className={`slides-editor__prompt-style-pill-btn${isActive ? " is-active" : ""}`}
                          aria-pressed={isActive}
                          disabled={state.uploading || state.uploadingPptxTemplate}
                          onClick={() =>
                            dispatch({ type: "set_upload_template_choice", value: choice })
                          }
                        >
                          {templateLabel}
                        </button>
                      );
                    })}
                  </div>
                  {hasSavedPptxTemplates ? (
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                      <div style={{ fontSize: 12, color: "#667085" }}>
                        {effectiveUploadTemplateChoice === "uniform"
                          ? label(copy, "pptx_template_uniform_hint", "Using the built-in Uniform template.")
                          : label(
                              copy,
                              "pptx_template_saved_hint",
                              "Using a saved PPTX template for this upload.",
                            )}
                      </div>
                      {effectiveUploadTemplateId &&
                      effectiveUploadTemplateId !== state.defaultPptxTemplateId ? (
                        <button
                          type="button"
                          className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                          onClick={() => handleSetDefaultPptxTemplate(effectiveUploadTemplateId)}
                          disabled={state.uploading || state.uploadingPptxTemplate}
                        >
                          {label(copy, "set_default_template", "Set as default")}
                        </button>
                      ) : null}
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, color: "#667085" }}>
                      {label(
                        copy,
                        "pptx_template_empty_hint",
                        "No saved PPTX templates yet. Upload one or use Uniform.",
                      )}
                    </div>
                  )}
                </div>
                <div
                  style={{
                    width: "100%",
                    display: "flex",
                    gap: 8,
                    flexWrap: "wrap",
                    paddingTop: 6,
                    marginTop: 2,
                    borderTop: "1px solid #e5e7eb",
                  }}
                >
                  <button
                    type="button"
                    className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                    onClick={
                      state.pendingUploadProcessingMode === "ocr"
                        ? confirmPendingUploadWithProcessing
                        : confirmPendingUploadWithoutProcessing
                    }
                    disabled={state.uploading || state.uploadingPptxTemplate || contentProcessingBlocked}
                    data-tooltip={tooltip(
                      copy,
                      state.pendingUploadProcessingMode === "ocr"
                        ? "upload_with_ocr_help"
                        : "upload_pdf_only_help",
                      state.pendingUploadProcessingMode === "ocr"
                        ? "Upload deck and start OCR and slide understanding."
                        : "Upload deck without OCR or slide understanding.",
                    )}
                  >
                    {state.pendingUploadProcessingMode === "ocr"
                      ? label(copy, "upload_with_ocr_action", "Upload and OCR PDF deck")
                      : label(copy, "upload_pdf_only_action", "Upload PDF deck")}
                  </button>
                  <button
                    type="button"
                    className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                    onClick={cancelPendingUpload}
                    disabled={state.uploading || state.uploadingPptxTemplate}
                  >
                    {label(copy, "cancel_action", "Cancel")}
                  </button>
                </div>
              </div>
            )}
            <div
              style={{
                marginTop: 8,
                display: "grid",
              gap: 4,
              fontSize: 12,
              color: "#475467",
            }}
            >
              <div>
                {label(copy, "session_pdf_decks", "Session PDF decks")}: {state.decks.length}
              </div>
              {persistentOcrLanguageLabel ? (
                <div>{persistentOcrLanguageLabel}</div>
              ) : null}
              {deckProcessingBlocked ? (
                <div style={{ color: "#475467" }}>
                  {label(
                    copy,
                    "deck_processing_wait_message",
                    "Slides stay locked until deck processing is complete.",
                  )}
                  <div style={{ marginTop: 2 }}>
                    {label(
                      copy,
                      "deck_processing_email_message",
                      "You will get an email when it is finished.",
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          </div>

          <div className="slides-editor__toolbar-card">
            <div className="slides-editor__toolbar-row">
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={handleSave}
                disabled={!state.currentDeckId || state.saving || toolbarDeckActionsDisabled}
                data-tooltip={tooltip(copy, "save_deck", "Save changes")}
              >
                {state.saving ? label(copy, "save_deck", "Save deck") + "..." : label(copy, "save_deck", "Save deck")}
              </button>
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={handlePrint}
                disabled={
                  !state.currentDeckId ||
                  state.printing ||
                  state.pptxExporting ||
                  toolbarDeckActionsDisabled
                }
                data-tooltip={tooltip(copy, "print_deck", "Generate a PDF snapshot of the current deck.")}
              >
                {state.printing
                  ? label(copy, "print_deck", "Export PDF") + "..."
                  : label(copy, "print_deck", "Export PDF")}
              </button>
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={handlePptxExport}
                disabled={
                  !state.currentDeckId ||
                  state.printing ||
                  state.pptxExporting ||
                  toolbarDeckActionsDisabled
                }
                data-tooltip={tooltip(copy, "export_pptx", "Download an editable PPTX deck.")}
              >
                {state.pptxExporting
                  ? label(copy, "export_pptx", "Export PPTX") + "..."
                  : label(copy, "export_pptx", "Export PPTX")}
              </button>
            </div>
          </div>

          <div className="slides-editor__toolbar-card">
            <div className="slides-editor__toolbar-row">
              <label className="sr-only" htmlFor="deckSelect">
                {label(copy, "deck_select_label", "Select deck")}
              </label>
              <select
                id="deckSelect"
                className="slides-editor__deck-select"
                value={state.currentDeckId || ""}
                onChange={(e) => loadDeck(e.target.value)}
                disabled={toolbarDeckActionsDisabled}
              >
                <option value="">{label(copy, "deck_placeholder", "Select deck")}</option>
                {state.decks.map((deck) => (
                  <option key={deck.deckId} value={deck.deckId}>
                    {deck.deckId}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={handleConcat}
                disabled={!state.decks.length || state.concatenating || toolbarDeckActionsDisabled}
                data-tooltip={tooltip(copy, "concat_decks", "Combine multiple decks into a new deck.")}
              >
                {state.concatenating
                  ? label(copy, "concat_decks", "Combine decks") + "..."
                  : label(copy, "concat_decks", "Combine decks")}
              </button>
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={handleConcatOrdered}
                disabled={!state.decks.length || state.concatenating || toolbarDeckActionsDisabled}
                data-tooltip={tooltip(
                  copy,
                  "concat_ordered",
                  "Combine decks and interleave slides by index using the longest (or shortest) deck as the guide."
                )}
              >
                {state.concatenating
                  ? label(copy, "concat_ordered", "Combine & order") + "..."
                  : label(copy, "concat_ordered", "Combine & order")}
              </button>
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={handleArchiveDeck}
                disabled={!state.currentDeckId || state.deleting || toolbarDeckActionsDisabled}
                data-tooltip={tooltip(
                  copy,
                  "delete_deck",
                  "Archive the current deck after confirmation."
                )}
              >
                {state.deleting
                  ? label(copy, "delete_deck", "Delete deck") + "..."
                  : label(copy, "delete_deck", "Delete deck")}
              </button>
            </div>
            <div className="slides-editor__toolbar-row">
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={handleImport}
                disabled={!state.currentDeckId || toolbarDeckActionsDisabled}
                data-tooltip={tooltip(
                  copy,
                  "import_slide",
                  "Insert a slide from another deck after the current selection.",
                )}
              >
                {label(copy, "import_slide", "Insert from deck")}
              </button>
            </div>
          </div>

          <div className="slides-editor__toolbar-card">
            <div className="slides-editor__toolbar-row">
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={handleAddSlide}
                disabled={!state.currentDeckId || toolbarDeckActionsDisabled}
                data-tooltip={tooltip(copy, "add_slide", "Create a new slide")}
              >
                {label(copy, "add_slide", "Add slide")}
              </button>
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={handleAddIntroSlides}
                disabled={!state.currentDeckId || toolbarDeckActionsDisabled}
                data-tooltip={tooltip(
                  copy,
                  "add_intro_slides",
                  "Insert a title and disclaimer slide at the start of the deck.",
                )}
              >
                {label(copy, "add_intro_slides", "Add title + disclaimer")}
              </button>
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={handleDeleteSlide}
                disabled={!state.selectedSlideId || toolbarDeckActionsDisabled}
                data-tooltip={tooltip(copy, "delete_slide", "Remove the selected slide")}
              >
                {label(copy, "delete_slide", "Delete slide")}
              </button>
            </div>
          </div>

          <div className="slides-editor__toolbar-card">
            <div className="slides-editor__toolbar-row">
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={() => dispatch({ type: "set_view_mode", mode: VIEW_MODES.LIST })}
                disabled={!state.slides.length || !isStoryboard || toolbarDeckActionsDisabled}
              >
                {label(copy, "list_view", "List view")}
              </button>
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={() => dispatch({ type: "set_view_mode", mode: VIEW_MODES.STORYBOARD })}
                disabled={!state.slides.length || isStoryboard || toolbarDeckActionsDisabled}
              >
                {label(copy, "storyboard_view", "Storyboard")}
              </button>
            </div>
          </div>

          <div className="slides-editor__toolbar-card slides-editor__toolbar-card--nav">
            <div className="slides-editor__toolbar-row">
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={() => handlePrevNext(-1)}
                disabled={!state.selectedSlideId || toolbarDeckActionsDisabled}
              >
                {label(copy, "prev_slide", "Prev")}
              </button>
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={() => handlePrevNext(1)}
                disabled={!state.selectedSlideId || toolbarDeckActionsDisabled}
              >
                {label(copy, "next_slide", "Next")}
              </button>
            </div>
          </div>

        </div>
        <StatusBar status={state.status} loading={state.loading} dirty={state.dirty} copy={copy} />
      </header>

      <section className="slides-editor__content" style={{ position: "relative" }}>
        <div
          className="slides-editor__content-body"
          aria-hidden={contentProcessingBlocked}
          style={
            contentProcessingBlocked
              ? { pointerEvents: "none", opacity: 0.4, filter: "grayscale(0.15)" }
              : undefined
          }
        >
            <aside className="slides-editor__sidebar">
              <h2 className="sr-only">{label(copy, "slides_heading", "Slides")}</h2>
              <BulkActions
                count={bulkSelectionCount}
                firstIndex={firstSelectedIndex}
                lastIndex={lastSelectedIndex}
                total={state.slides.length}
                onPromote={promoteSelected}
                onDemote={demoteSelected}
                onDelete={handleDeleteSlide}
                onClear={clearSelection}
                copy={copy}
              />
              <SectionPanel
                sections={state.sections}
                slides={state.slides}
                onAdd={handleAddSection}
                onUpdate={updateSection}
                onRemove={removeSection}
                onAddSubsection={addSubsection}
                onUpdateSubsection={updateSubsection}
                onRemoveSubsection={removeSubsection}
                onInsertHeader={insertSectionHeader}
                onConvertToHeader={convertSelectionToHeader}
                copy={copy}
              />
              {!isStoryboard && (
                <SlideList
                  slides={state.slides}
                  selectedIds={state.selectedSlideIds}
                  primaryId={state.selectedSlideId}
                  onSelectSingle={selectSlide}
                  onToggleSelect={toggleSelect}
                  onRangeSelect={rangeSelect}
                  onReorder={reorderSlides}
                  copy={copy}
                />
              )}
              {isStoryboard && (
                <p style={{ margin: 0, color: "#475467" }}>
                  {label(
                    copy,
                    "storyboard_active_hint",
                    "Storyboard is active. Use the grid to select and reorder slides.",
                  )}
                </p>
              )}
            </aside>
            <section className="slides-editor__workspace">
              {!isStoryboard && (
                <div className="slides-editor__workspace-pane">
                  <div className="slides-editor__preview">
                    <article className="slides-editor__preview-pane">
                      <div className="slides-editor__preview-frame">
                        <iframe
                          className="slides-editor__preview-iframe"
                          title={label(copy, "preview_label", "Slide preview")}
                          ref={previewFrameRef}
                          srcDoc={previewDoc}
                        />
                        {selectedSlideIsImageBacked && layoutPreviewVisible ? (
                          <LayoutInspectionPreview
                            layoutResult={selectedSlideLayout}
                            overlayMetrics={previewOverlayMetrics}
                          />
                        ) : null}
                      </div>
                    </article>
                  </div>
                  <div className="slides-editor__field">
                    <label htmlFor="titleHtmlInput">{label(copy, "title_label", "Title HTML")}</label>
                    <textarea
                      id="titleHtmlInput"
                      className="slides-editor__textarea"
                      rows={3}
                      value={selectedSlide?.titleHtml || ""}
                      onChange={(e) => handleFieldChange("titleHtml", e.target.value)}
                      disabled={!canEditHtmlFields}
                    />
                  </div>
                  <div className="slides-editor__field">
                    <label htmlFor="bodyHtmlInput">{label(copy, "body_label", "Body HTML")}</label>
                    <textarea
                      id="bodyHtmlInput"
                      className="slides-editor__textarea"
                      rows={12}
                      value={selectedSlide?.bodyHtml || ""}
                      onChange={(e) => handleFieldChange("bodyHtml", e.target.value)}
                      disabled={!canEditHtmlFields}
                    />
                  </div>
                  <div className="slides-editor__field">
                    <label htmlFor="notesHtmlInput">{label(copy, "notes_label", "Notes")}</label>
                    <textarea
                      id="notesHtmlInput"
                      className="slides-editor__textarea"
                      rows={4}
                      value={selectedSlide?.notesText || ""}
                      placeholder={label(
                        copy,
                        "notes_placeholder",
                        "Add a note or link (plain text). Links stay clickable in exports."
                      )}
                      onChange={(e) => handleNotesChange(e.target.value)}
                      disabled={!canEditNotes}
                    />
                  </div>
                </div>
              )}
              {isStoryboard && (
                <>
                  <StoryboardSelectionBar
                    count={bulkSelectionCount}
                    firstIndex={firstSelectedIndex}
                    lastIndex={lastSelectedIndex}
                    total={state.slides.length}
                    selectedId={state.selectedSlideId}
                    dirty={state.dirty}
                    onPromote={promoteSelected}
                    onDemote={demoteSelected}
                    onDelete={handleDeleteSlide}
                    onClear={clearSelection}
                    onPrev={() => handlePrevNext(-1)}
                    onNext={() => handlePrevNext(1)}
                    onListView={() => dispatch({ type: "set_view_mode", mode: VIEW_MODES.LIST })}
                    onSave={handleSave}
                    dirtyLabel={label(copy, "storyboard_dirty_label", "Unsaved changes")}
                    saveLabel={label(copy, "save_deck", "Save deck")}
                    copy={copy}
                  />
                  <StoryboardGrid
                    slides={state.slides}
                    thumbnails={state.thumbnails}
                    sections={state.sections}
                    selectedIds={state.selectedSlideIds}
                    primaryId={state.selectedSlideId}
                    scale={state.storyboardScale}
                    canvasRef={storyboardCanvasRef}
                    gridRef={storyboardGridRef}
                    onCanvasPointerDown={startMarqueeSelection}
                    marqueeBox={marqueeBox}
                    marqueePreviewIds={marqueePreviewIds}
                    onSelectSingle={selectSlide}
                    onToggleSelect={toggleSelect}
                    onRangeSelect={rangeSelect}
                    onReorder={(payload) => {
                      if (payload.type === "scale") {
                        dispatch({ type: "set_storyboard_scale", scale: payload.scale });
                      } else {
                        reorderSlides(payload.sourceId, payload.targetId);
                      }
                    }}
                    onDeleteSlide={deleteSlidesById}
                    onConvertToHeader={handleConvertFromStoryboard}
                    copy={copy}
                  />
                </>
              )}
            </section>
        </div>
        {contentProcessingBlocked ? (
          <div
            aria-live="polite"
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: 24,
              background: "rgba(248, 250, 252, 0.82)",
              backdropFilter: "blur(1px)",
              zIndex: 3,
            }}
          >
            <div
              style={{
                maxWidth: 480,
                width: "100%",
                background: "#ffffff",
                border: "1px solid #e5e7eb",
                borderRadius: 16,
                padding: "18px 20px",
                boxShadow: "0 18px 40px rgba(15, 23, 42, 0.12)",
                display: "grid",
                gap: 8,
              }}
            >
              <div style={{ fontSize: 16, fontWeight: 700, color: "#0f172a" }}>
                {contentProcessingTitle}
              </div>
              <div style={{ fontSize: 13, color: "#334155", lineHeight: 1.5 }}>
                {contentProcessingMessage}
              </div>
              {deckProcessingMeta ? (
                <div style={{ fontSize: 12, color: "#475467", lineHeight: 1.5 }}>
                  {deckProcessingMeta}
                </div>
              ) : null}
              <div style={{ fontSize: 12, color: "#64748b", lineHeight: 1.5 }}>
                {label(
                  copy,
                  "deck_processing_email_message",
                  "You will get an email when it is finished.",
                )}
              </div>
            </div>
          </div>
        ) : null}
      </section>
    </section>
  );
}

function StatusBar({ status, loading, dirty, copy }) {
  const text = status?.message || "";
  const loadingLabel = label(copy, "loading_status", "Loading…");
  const unsavedLabel = label(copy, "unsaved_changes", "Unsaved changes");
  return (
    <div className={`slides-editor__status${status?.isError ? " is-error" : ""}`}>
      {loading ? loadingLabel : text}
      {dirty && !loading ? <span style={{ marginLeft: 8 }}>• {unsavedLabel}</span> : null}
    </div>
  );
}

function StoryboardSelectionBar({
  count,
  firstIndex,
  lastIndex,
  total,
  selectedId,
  dirty,
  onPromote,
  onDemote,
  onDelete,
  onClear,
  onPrev,
  onNext,
  onListView,
  onSave,
  dirtyLabel,
  saveLabel,
  copy,
}) {
  const emptyLabel = label(copy, "bulk_selection_placeholder", "No slides selected");
  const singleLabel = label(copy, "bulk_selection_single", "1 slide selected");
  const multiTemplate = label(copy, "bulk_selection_multi", "{count} slides selected");
  const summary =
    count === 0 ? emptyLabel : count === 1 ? singleLabel : multiTemplate.replace("{count}", String(count));
  const disable = count === 0;
  const promoteDisabled = disable || firstIndex <= 0;
  const demoteDisabled = disable || lastIndex === total - 1;
  const showBar = count > 0 || dirty;
  const disableNav = !selectedId;
  const disableListView = total <= 0;
  return (
    <div className="slides-storyboard-panel__selection" hidden={!showBar}>
      <div className="slides-storyboard-panel__selection-text">
        {summary}
      </div>
      <div className="slides-storyboard-panel__selection-buttons">
        <button
          id="storyboardPromoteBtn"
          type="button"
          className="ghost-button slides-editor__pill-btn"
          onClick={onPromote}
          disabled={promoteDisabled}
          data-tooltip={tooltip(copy, "bulk_promote", "Move the selected slides earlier in the deck.")}
        >
          {label(copy, "bulk_promote", "Move up one")}
        </button>
        <button
          id="storyboardDemoteBtn"
          type="button"
          className="ghost-button slides-editor__pill-btn"
          onClick={onDemote}
          disabled={demoteDisabled}
          data-tooltip={tooltip(copy, "bulk_demote", "Move the selected slides later in the deck.")}
        >
          {label(copy, "bulk_demote", "Move down one")}
        </button>
        <button
          id="storyboardDeleteBtn"
          type="button"
          className="ghost-button slides-editor__pill-btn"
          onClick={onDelete}
          disabled={disable}
          data-tooltip={tooltip(copy, "bulk_delete", "Remove every selected slide from this deck.")}
        >
          {label(copy, "bulk_delete", "Delete selected")}
        </button>
        <button
          id="storyboardClearBtn"
          type="button"
          className="ghost-button slides-editor__pill-btn"
          onClick={onClear}
          disabled={disable}
          data-tooltip={tooltip(copy, "bulk_clear", "Clear the current selection.")}
        >
          {label(copy, "bulk_clear", "Clear selection")}
        </button>
        <button
          type="button"
          className="ghost-button slides-editor__pill-btn"
          onClick={onPrev}
          disabled={disableNav}
          data-tooltip={tooltip(copy, "prev_slide", "Go to the previous slide.")}
        >
          {label(copy, "prev_slide", "Prev")}
        </button>
        <button
          type="button"
          className="ghost-button slides-editor__pill-btn"
          onClick={onNext}
          disabled={disableNav}
          data-tooltip={tooltip(copy, "next_slide", "Go to the next slide.")}
        >
          {label(copy, "next_slide", "Next")}
        </button>
        <button
          type="button"
          className="ghost-button slides-editor__pill-btn"
          onClick={onListView}
          disabled={disableListView}
          data-tooltip={tooltip(copy, "list_view", "Switch to list view.")}
        >
          {label(copy, "list_view", "List view")}
        </button>
        {dirty ? (
          <div className="slides-storyboard-panel__dirty-inline">
            <span>{dirtyLabel || "Unsaved changes"}</span>
            <button
              type="button"
              className="ghost-button slides-editor__pill-btn"
              onClick={onSave}
              data-tooltip={saveLabel || "Save deck"}
            >
              {saveLabel || "Save deck"}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function SectionPanel({
  sections,
  slides,
  onAdd,
  onUpdate,
  onRemove,
  onAddSubsection,
  onUpdateSubsection,
  onRemoveSubsection,
  onInsertHeader,
  onConvertToHeader,
  copy,
}) {
  const contentSlides = slides.filter((slide) => slide.kind !== "sectionHeader");
  const removeLabel = label(copy, "section_remove", "Remove");
  const idLabel = label(copy, "section_id_label", "ID");
  const titleLabel = label(copy, "section_title_label", "Title");
  const startsAtLabel = label(copy, "section_starts_at", "Starts at");
  const insertHeaderLabel = label(copy, "section_insert_header", "Insert header");
  const useSelectionAsHeaderLabel = label(
    copy,
    "section_use_selection_as_header",
    "Use selection as header",
  );
  const addSubsectionLabel = label(copy, "section_add_subsection", "Add subsection");
  const noSubsectionsLabel = label(copy, "section_no_subsections", "No subsections yet.");
  const sectionFallbackTemplate = label(copy, "section_fallback_title", "Section {index}");
  const orderedSections = orderSectionsBySlides(sections, slides);
  return (
    <section
      className="slides-editor__sections-panel"
      aria-label={label(copy, "sections_heading", "Sections")}
    >
      <div className="slides-editor__sections-header">
        <h2>{label(copy, "sections_heading", "Sections")}</h2>
        <button
          type="button"
          className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
          onClick={onAdd}
          aria-label={label(copy, "add_section", "Add section")}
        >
          {label(copy, "add_section", "Add section")}
        </button>
      </div>
      <div className="slides-editor__sections-list">
        {orderedSections.map((section, index) => (
          <div key={section.id} className="slides-editor__section-card">
            <div className="slides-editor__section-header">
              <strong>
                {section.title ||
                  section.id ||
                  sectionFallbackTemplate.replace("{index}", String(index + 1))}
              </strong>
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={() => onRemove(section.id)}
              >
                {removeLabel}
              </button>
            </div>
            <div className="slides-editor__section-fields">
              <label>
                <span>{idLabel}</span>
                <input
                  value={section.id}
                  onChange={(e) => {
                    const nextId = e.target.value.trim();
                    if (nextId) {
                      onUpdate(section.id, { id: nextId });
                    }
                  }}
                />
              </label>
              <label>
                <span>{titleLabel}</span>
                <input
                  value={section.title}
                  onChange={(e) => onUpdate(section.id, { title: e.target.value })}
                />
              </label>
              <label>
                <span>{startsAtLabel}</span>
                <SectionStartSelect
                  slides={contentSlides}
                  value={section.startSlide}
                  onChange={(val) => onUpdate(section.id, { startSlide: val })}
                />
              </label>
            </div>
            <div className="slides-editor__section-actions">
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={() => onInsertHeader?.(section.id)}
              >
                {insertHeaderLabel}
              </button>
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={() => onConvertToHeader?.(section.id)}
              >
                {useSelectionAsHeaderLabel}
              </button>
              <button
                type="button"
                className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                onClick={() => onAddSubsection?.(section.id)}
              >
                {addSubsectionLabel}
              </button>
            </div>
            <div className="slides-editor__subsections">
              {(section.subsections || []).length === 0 ? (
                <p className="slides-editor__sections-helper" style={{ margin: 0 }}>
                  {noSubsectionsLabel}
                </p>
              ) : (
                section.subsections.map((subsection, subIndex) => (
                  <div key={subsection.id || subIndex} className="slides-editor__subsection-card">
                    <div className="slides-editor__section-fields">
                      <label>
                        <span>{idLabel}</span>
                        <input
                          value={subsection.id}
                          onChange={(e) => {
                            const nextId = e.target.value.trim();
                            if (nextId) {
                              onUpdateSubsection?.(section.id, subsection.id, { id: nextId });
                            }
                          }}
                        />
                      </label>
                      <label>
                        <span>{titleLabel}</span>
                        <input
                          value={subsection.title}
                          onChange={(e) =>
                            onUpdateSubsection?.(section.id, subsection.id, { title: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        <span>{startsAtLabel}</span>
                        <SectionStartSelect
                          slides={contentSlides}
                          value={subsection.startSlide}
                          onChange={(val) =>
                            onUpdateSubsection?.(section.id, subsection.id, { startSlide: val })
                          }
                        />
                      </label>
                    </div>
                    <div className="slides-editor__section-actions">
                      <button
                        type="button"
                        className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                        onClick={() => onInsertHeader?.(section.id, subsection.id)}
                      >
                        {insertHeaderLabel}
                      </button>
                      <button
                        type="button"
                        className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                        onClick={() => onConvertToHeader?.(section.id, subsection.id)}
                      >
                        {useSelectionAsHeaderLabel}
                      </button>
                      <button
                        type="button"
                        className="ghost-button slides-editor__toolbar-btn slides-editor__pill-btn"
                        onClick={() => onRemoveSubsection?.(section.id, subsection.id)}
                      >
                        {removeLabel}
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function SectionStartSelect({ slides, value, onChange }) {
  return (
    <select value={value || ""} onChange={(e) => onChange(e.target.value)}>
      {slides.length === 0 && <option value="">No slides</option>}
      {slides.map((slide) => (
        <option key={slide.id} value={slide.id}>
          {stripHtml(slide.titleHtml) || slide.id}
        </option>
      ))}
    </select>
  );
}
