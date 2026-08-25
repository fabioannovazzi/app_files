/**
 * Observe bounded browser state changes while an operator demonstrates a process.
 *
 * This runtime is intentionally read-only. It captures query-free paths and
 * visible control metadata while excluding form values and controls inside
 * tables, grids, and rows. The model interprets the state changes and authors
 * the semantic discovery record; this module only makes repeated observation
 * and hashing reproducible.
 */

import { canonicalJson, sha256Text } from "./capability_runtime.mjs";

export const DISCOVERY_RUNTIME_VERSION = "browser-discovery-runtime/2";

const DEFAULT_MAX_CONTROLS = 120;
const MAX_CONTROLS = 250;
const DEFAULT_POLL_INTERVAL_MS = 500;
const MAX_GUIDED_WINDOW_MS = 60_000;
const PRIVATE_IDENTIFIER_MARKER = "[private identifier]";
const CONTROL_TEXT_FIELDS = ["name", "label", "placeholder", "test_id"];

// This fixed redaction runs before control metadata leaves the local runtime.
// It is deterministic because excluding recognizable identifier shapes is a
// mechanically testable security boundary, not a semantic relevance decision.
const PRIVATE_IDENTIFIER_PATTERNS = [
  /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/giu,
  /\b[0-9A-F]{8}-[0-9A-F]{4}-[1-5][0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}\b/giu,
  /\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b/giu,
  /\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b/giu,
  /\b(?=[A-Z0-9._/-]{8,}\b)(?=[A-Z0-9._/-]*[A-Z])(?=[A-Z0-9._/-]*\d)[A-Z0-9._/-]+\b/giu,
  /\b\d{2,}(?:[\s./_-]+\d{2,})+\b/gu,
  /\b\d{4,}\b/gu,
];

function redactPrivateIdentifiers(value) {
  if (typeof value !== "string" || !value) {
    return { value, redacted: false };
  }
  let sanitized = value;
  for (const pattern of PRIVATE_IDENTIFIER_PATTERNS) {
    sanitized = sanitized.replace(pattern, PRIVATE_IDENTIFIER_MARKER);
  }
  sanitized = sanitized
    .replace(/(?:\[private identifier\]\s*){2,}/gu, `${PRIVATE_IDENTIFIER_MARKER} `)
    .replace(/\s+/gu, " ")
    .trim();
  return { value: sanitized, redacted: sanitized !== value };
}

function sanitizeControlMetadata(control) {
  const sanitized = { ...control };
  const redactedFields = [];
  for (const field of CONTROL_TEXT_FIELDS) {
    const result = redactPrivateIdentifiers(control[field]);
    if (!result.redacted) continue;
    sanitized[field] = field === "test_id" ? null : result.value;
    redactedFields.push(field);
  }
  if (redactedFields.length > 0) {
    sanitized.redacted_fields = redactedFields;
  }
  return sanitized;
}

function normalizeOrigin(value) {
  return new URL(value).origin;
}

function queryFreePath(value) {
  return new URL(value).pathname;
}

function allowedPage(url, allowedOrigins) {
  const parsed = new URL(url);
  if (!allowedOrigins.has(parsed.origin)) {
    throw new Error(`guided discovery left allowed origins: ${parsed.origin}`);
  }
  return { origin: parsed.origin, path: parsed.pathname };
}

function validateOptions({ allowedOrigins, maxControls, includeStructuredControls }) {
  if (!Array.isArray(allowedOrigins) || allowedOrigins.length === 0) {
    throw new Error("guided discovery requires allowed origins");
  }
  if (!Number.isInteger(maxControls) || maxControls < 1 || maxControls > MAX_CONTROLS) {
    throw new Error(`maxControls must be between 1 and ${MAX_CONTROLS}`);
  }
  if (typeof includeStructuredControls !== "boolean") {
    throw new Error("includeStructuredControls must be boolean");
  }
  return new Set(allowedOrigins.map(normalizeOrigin));
}

function stateProjection(state) {
  return {
    origin: state.origin,
    path: state.path,
    controls: state.controls,
    truncated: state.truncated,
  };
}

/** Capture one privacy-bounded page state through the connected Playwright API. */
export async function captureControlState({
  tab,
  allowedOrigins,
  maxControls = DEFAULT_MAX_CONTROLS,
  includeStructuredControls = false,
}) {
  const normalizedOrigins = validateOptions({
    allowedOrigins,
    maxControls,
    includeStructuredControls,
  });
  const currentUrl = await tab.url();
  const page = allowedPage(currentUrl, normalizedOrigins);
  const inventory = await tab.playwright.evaluate(
    ({ controlLimit, includeStructured }) => {
      const interactiveSelector = [
        "a[href]",
        "button",
        "input",
        "select",
        "textarea",
        "[contenteditable='true']",
        "[role]",
      ].join(",");
      const structuredSelector = "table,[role='grid'],[role='row'],[role='treegrid']";
      const compact = (value) => {
        if (typeof value !== "string") return null;
        const normalized = value.replace(/\s+/g, " ").trim();
        if (!normalized) return null;
        return normalized.slice(0, 120);
      };
      const isVisible = (element) => {
        const style = window.getComputedStyle(element);
        const bounds = element.getBoundingClientRect();
        return (
          style.visibility !== "hidden" &&
          style.display !== "none" &&
          bounds.width > 0 &&
          bounds.height > 0
        );
      };
      const associatedLabel = (element) => {
        if (element.labels?.length) return compact(element.labels[0].innerText);
        const id = element.getAttribute("id");
        if (!id) return null;
        const label = Array.from(document.querySelectorAll("label")).find(
          (candidate) => candidate.htmlFor === id,
        );
        return compact(label?.innerText);
      };
      const inferredRole = (element) => {
        const explicit = compact(element.getAttribute("role"));
        if (explicit) return explicit;
        const tag = element.tagName.toLowerCase();
        if (tag === "button") return "button";
        if (tag === "a") return "link";
        if (tag === "select") return "combobox";
        if (tag === "textarea") return "textbox";
        if (tag === "input") {
          const type = (element.getAttribute("type") || "text").toLowerCase();
          if (type === "checkbox") return "checkbox";
          if (type === "radio") return "radio";
          if (["button", "submit", "reset"].includes(type)) return "button";
          return "textbox";
        }
        return null;
      };
      const controlName = (element, structuredContext) => {
        const direct =
          compact(element.getAttribute("aria-label")) ||
          associatedLabel(element) ||
          compact(element.getAttribute("placeholder")) ||
          compact(element.getAttribute("title"));
        if (direct) return direct;
        if (structuredContext) return null;
        const tag = element.tagName.toLowerCase();
        if (tag === "button" || tag === "a") return compact(element.innerText);
        return null;
      };
      const nodes = Array.from(document.querySelectorAll(interactiveSelector)).filter(
        (element) =>
          isVisible(element) &&
          (includeStructured || element.closest(structuredSelector) == null),
      );
      const controls = nodes.slice(0, controlLimit).map((element) => {
        const structuredContext = element.closest(structuredSelector) != null;
        return {
          tag: element.tagName.toLowerCase(),
          role: inferredRole(element),
          name: controlName(element, structuredContext),
          label: associatedLabel(element),
          placeholder: compact(element.getAttribute("placeholder")),
          test_id:
            compact(element.getAttribute("data-testid")) ||
            compact(element.getAttribute("data-test-id")),
          type: compact(element.getAttribute("type")),
          disabled:
            element.matches(":disabled") ||
            element.getAttribute("aria-disabled") === "true",
          structured_context: structuredContext,
        };
      });
      return {
        controls,
        total_control_count: nodes.length,
        truncated: nodes.length > controlLimit,
      };
    },
    {
      controlLimit: maxControls,
      includeStructured: includeStructuredControls,
    },
  );
  const state = {
    schema_version: "browser-control-state/v1",
    runtime_version: DISCOVERY_RUNTIME_VERSION,
    origin: page.origin,
    path: page.path,
    controls: inventory.controls.map(sanitizeControlMetadata),
    total_control_count: inventory.total_control_count,
    truncated: inventory.truncated,
  };
  return {
    ...state,
    control_fingerprint: sha256Text(canonicalJson(stateProjection(state))),
  };
}

/** Return a mechanical delta between two captured control states. */
export function diffControlStates(before, after) {
  const keyed = (controls) =>
    new Map(controls.map((control) => [sha256Text(canonicalJson(control)), control]));
  const beforeControls = keyed(before.controls);
  const afterControls = keyed(after.controls);
  return {
    path_changed: before.origin !== after.origin || before.path !== after.path,
    added_controls: [...afterControls]
      .filter(([key]) => !beforeControls.has(key))
      .map(([, control]) => control),
    removed_controls: [...beforeControls]
      .filter(([key]) => !afterControls.has(key))
      .map(([, control]) => control),
  };
}

/**
 * Observe a short operator demonstration window without injecting listeners or
 * recording form values. The caller asks the operator to demonstrate while
 * this bounded polling loop runs, then the model interprets the returned deltas.
 */
export async function observeGuidedWindow({
  tab,
  allowedOrigins,
  durationMs = 15_000,
  pollIntervalMs = DEFAULT_POLL_INTERVAL_MS,
  maxControls = DEFAULT_MAX_CONTROLS,
  maxTransitions = 20,
  includeStructuredControls = false,
}) {
  if (!Number.isInteger(durationMs) || durationMs < 1_000 || durationMs > MAX_GUIDED_WINDOW_MS) {
    throw new Error(`durationMs must be between 1000 and ${MAX_GUIDED_WINDOW_MS}`);
  }
  if (!Number.isInteger(pollIntervalMs) || pollIntervalMs < 100 || pollIntervalMs > 5_000) {
    throw new Error("pollIntervalMs must be between 100 and 5000");
  }
  if (!Number.isInteger(maxTransitions) || maxTransitions < 1 || maxTransitions > 100) {
    throw new Error("maxTransitions must be between 1 and 100");
  }
  const startedAt = Date.now();
  let previous = await captureControlState({
    tab,
    allowedOrigins,
    maxControls,
    includeStructuredControls,
  });
  const initial = previous;
  const transitions = [];
  while (Date.now() - startedAt < durationMs && transitions.length < maxTransitions) {
    await tab.playwright.waitForTimeout(pollIntervalMs);
    const current = await captureControlState({
      tab,
      allowedOrigins,
      maxControls,
      includeStructuredControls,
    });
    if (current.control_fingerprint === previous.control_fingerprint) continue;
    transitions.push({
      sequence: transitions.length + 1,
      before: previous,
      after: current,
      delta: diffControlStates(previous, current),
    });
    previous = current;
  }
  return {
    schema_version: "browser-guided-capture/v1",
    runtime_version: DISCOVERY_RUNTIME_VERSION,
    duration_ms: Date.now() - startedAt,
    initial,
    transitions,
    final: previous,
    capture_policy: {
      query_free_paths_only: true,
      form_values_excluded: true,
      structured_rows_excluded: !includeStructuredControls,
      structured_control_values_excluded: true,
      private_identifier_tokens_redacted: true,
      screenshots_excluded: true,
    },
  };
}

export function queryFreeUrl(value) {
  const url = new URL(value);
  return `${url.origin}${queryFreePath(value)}`;
}
