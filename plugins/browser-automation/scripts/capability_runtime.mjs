/**
 * Execute a reviewed browser capability through the connected Chrome tab API.
 *
 * The runner is deterministic because action dispatch, origin enforcement,
 * postcondition checks, extraction shape, hashing, and receipts are mechanical
 * contract work. Page meaning, workflow authoring, and repair remain model-led.
 */

import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { chmod, mkdir, readFile, stat, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";

export const RUNTIME_VERSION = "browser-capability-runtime/6";
export const RECEIPT_SCHEMA = "browser-run-receipt/v1";
export const RECOVERY_PROPOSAL_SCHEMA = "browser-recovery-proposals/v1";

const EXECUTABLE_STATES = new Set(["discovered", "validated_local"]);
const SAFE_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const DEFAULT_TIMEOUT_MS = 10_000;
const MAX_TIMEOUT_MS = 30_000;
const MAX_TRANSITIONS = 100;
const SHA256 = /^[a-f0-9]{64}$/;
const ACTION_OPERATIONS = new Set([
  "goto",
  "wait_for",
  "click",
  "fill",
  "press",
  "select",
  "set_checked",
  "extract",
  "download",
]);
const ACTION_EFFECTS = new Set(["read_only", "reversible", "consequential"]);
const RECOVERY_LOCATOR_KINDS = new Set(["role", "label", "placeholder", "test_id", "text"]);
const EMAIL_ADDRESS = /(^|[^A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}($|[^A-Za-z0-9.-])/;

class LocatorResolutionError extends Error {
  constructor(message) {
    super(message);
    this.name = "LocatorResolutionError";
  }
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function canonicalize(value) {
  if (Array.isArray(value)) {
    return value.map(canonicalize);
  }
  if (isObject(value)) {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, canonicalize(value[key])]),
    );
  }
  return value;
}

export function canonicalJson(value) {
  return `${JSON.stringify(canonicalize(value), null, 2)}\n`;
}

export function sha256Text(value) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

export function executionContract(capability) {
  const projected = structuredClone(capability);
  delete projected.status;
  delete projected.validation;
  return projected;
}

export function executionContractSha256(capability) {
  return sha256Text(canonicalJson(executionContract(capability)));
}

export async function loadCapability(path) {
  return JSON.parse(await readFile(resolve(path), "utf8"));
}

function boundedTimeout(value) {
  if (value == null) {
    return DEFAULT_TIMEOUT_MS;
  }
  if (!Number.isInteger(value) || value < 1 || value > MAX_TIMEOUT_MS) {
    throw new Error(`timeout_ms must be between 1 and ${MAX_TIMEOUT_MS}`);
  }
  return value;
}

function exactKeys(value, expected) {
  return isObject(value) &&
    Object.keys(value).length === expected.size &&
    Object.keys(value).every((key) => expected.has(key));
}

function validateRecoveryLocatorCandidate(candidate) {
  const expectedKeys = new Set(["kind", "role", "value", "exact"]);
  if (!exactKeys(candidate, expectedKeys)) {
    throw new Error("recovery locator candidate has an unsupported shape");
  }
  if (!RECOVERY_LOCATOR_KINDS.has(candidate.kind)) {
    throw new Error("recovery requires a semantic locator candidate");
  }
  if (typeof candidate.exact !== "boolean") {
    throw new Error("recovery locator exact must be boolean");
  }
  if (candidate.kind === "role") {
    if (typeof candidate.role !== "string" || candidate.role.trim() === "") {
      throw new Error("role recovery locator requires a role");
    }
    if (candidate.value !== null && typeof candidate.value !== "string") {
      throw new Error("role recovery locator value must be text or null");
    }
  } else if (
    candidate.role !== null ||
    typeof candidate.value !== "string" ||
    candidate.value.trim() === ""
  ) {
    throw new Error(`${candidate.kind} recovery locator requires a text value and null role`);
  }
  if (typeof candidate.value === "string") {
    if (candidate.value.length > 160 || EMAIL_ADDRESS.test(candidate.value)) {
      throw new Error("recovery locator value is unsafe for retained proposal evidence");
    }
    if (candidate.value.includes("{{")) {
      throw new Error("recovery locator must not introduce runtime templates");
    }
  }
  return structuredClone(candidate);
}

function validateRuntimeShape(capability) {
  if (!isObject(capability)) {
    throw new Error("capability must be an object");
  }
  if (capability.schema_version !== "browser-capability/v2") {
    throw new Error("runtime requires browser-capability/v2");
  }
  if (!EXECUTABLE_STATES.has(capability.status)) {
    throw new Error(`capability status ${JSON.stringify(capability.status)} is not executable`);
  }
  if (!SAFE_ID.test(capability.capability_id ?? "")) {
    throw new Error("capability_id must be a lower-case slug");
  }
  if (!Array.isArray(capability.site?.allowed_origins) || capability.site.allowed_origins.length === 0) {
    throw new Error("capability requires allowed origins");
  }
  if (!Array.isArray(capability.milestones) || capability.milestones.length === 0) {
    throw new Error("capability requires milestones");
  }
  if (!Array.isArray(capability.outputs) || capability.outputs.length === 0) {
    throw new Error("capability requires outputs");
  }
  const outputNames = new Set();
  for (const output of capability.outputs) {
    if (!SAFE_ID.test(output?.name ?? "") || outputNames.has(output.name)) {
      throw new Error("capability output names must be unique lower-case slugs");
    }
    outputNames.add(output.name);
    if (output.type === "download_set" && output.delivery !== "artifact_only") {
      throw new Error("download_set outputs must use artifact_only delivery");
    }
  }
  if (!SAFE_ID.test(capability.entry_milestone ?? "")) {
    throw new Error("capability requires an entry milestone");
  }
  const milestoneIds = new Set();
  const actionIds = new Set();
  for (const milestone of capability.milestones) {
    if (!SAFE_ID.test(milestone?.id ?? "") || milestoneIds.has(milestone.id)) {
      throw new Error("milestone ids must be unique lower-case slugs");
    }
    milestoneIds.add(milestone.id);
    if (!Array.isArray(milestone.actions) || !Array.isArray(milestone.transitions)) {
      throw new Error(`milestone ${milestone.id} requires actions and transitions`);
    }
    for (const action of milestone.actions) {
      if (!SAFE_ID.test(action?.id ?? "") || actionIds.has(action.id)) {
        throw new Error("action ids must be unique lower-case slugs");
      }
      actionIds.add(action.id);
      if (!ACTION_OPERATIONS.has(action.operation)) {
        throw new Error(`action ${action.id} has an unsupported operation`);
      }
      if (!ACTION_EFFECTS.has(action.effect)) {
        throw new Error(`action ${action.id} has an unsupported effect`);
      }
      const expectedConfirmation =
        action.effect === "consequential" ? "action_time" : "none";
      if (action.confirmation !== expectedConfirmation) {
        throw new Error(
          `action ${action.id} confirmation must be ${expectedConfirmation}`,
        );
      }
    }
  }
  if (!milestoneIds.has(capability.entry_milestone)) {
    throw new Error("entry milestone is not declared");
  }
  if (
    capability.runtime?.browser !== "existing_chrome" ||
    capability.runtime?.controller !== "chrome_extension" ||
    capability.runtime?.semantic_driver !== "model" ||
    capability.runtime?.mechanical_driver !== "playwright"
  ) {
    throw new Error("capability runtime contract is unsupported");
  }
  if (
    capability.authority?.operator_authorized !== true ||
    capability.authority?.authentication !== "operator_only" ||
    capability.authority?.secret_policy !== "never_request_read_store" ||
    capability.authority?.consequential_actions !== "confirm_at_action_time"
  ) {
    throw new Error("capability authority contract is unsupported");
  }
  if (
    capability.provenance?.source !== "authorized_live_discovery" ||
    !SHA256.test(capability.provenance?.discovery_record_sha256 ?? "") ||
    !SAFE_ID.test(capability.provenance?.discovery_approval_id ?? "") ||
    typeof capability.provenance?.discovery_approved_at !== "string" ||
    capability.provenance?.portable_bundle_contains_private_evidence !== false
  ) {
    throw new Error("capability lacks reviewed discovery provenance");
  }
}

function resolveInputs(capability, supplied) {
  const resolvedInputs = {};
  const declarations = new Map((capability.inputs ?? []).map((item) => [item.name, item]));
  for (const key of Object.keys(supplied ?? {})) {
    if (!declarations.has(key)) {
      throw new Error(`undeclared runtime input: ${key}`);
    }
  }
  for (const declaration of declarations.values()) {
    const value = supplied?.[declaration.name];
    if (value == null) {
      if (declaration.required) {
        throw new Error(`missing required runtime input: ${declaration.name}`);
      }
      continue;
    }
    const valid =
      (declaration.type === "text" && typeof value === "string") ||
      (declaration.type === "number" && typeof value === "number" && Number.isFinite(value)) ||
      (declaration.type === "boolean" && typeof value === "boolean") ||
      (declaration.type === "date" && typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) ||
      (declaration.type === "enum" && typeof value === "string" && declaration.enum_values.includes(value));
    if (!valid) {
      throw new Error(`runtime input ${declaration.name} does not match type ${declaration.type}`);
    }
    resolvedInputs[declaration.name] = value;
  }
  return resolvedInputs;
}

function initialOutputs(capability) {
  return Object.fromEntries(
    (capability.outputs ?? []).map((output) => {
      if (output.type === "record_set" || output.type === "download_set") {
        return [output.name, []];
      }
      return [output.name, null];
    }),
  );
}

function renderTemplate(value, inputs) {
  if (typeof value !== "string") {
    return value;
  }
  return value.replace(/\{\{([a-z0-9]+(?:-[a-z0-9]+)*)\}\}/g, (_match, name) => {
    if (!(name in inputs)) {
      throw new Error(`template references missing input: ${name}`);
    }
    return String(inputs[name]);
  });
}

function normalizeOrigin(value) {
  return new URL(value).origin;
}

function queryFreePath(value) {
  const url = new URL(value);
  return url.pathname;
}

function assertAllowedUrl(url, allowedOrigins) {
  const origin = normalizeOrigin(url);
  if (!allowedOrigins.has(origin)) {
    throw new Error(`browser left allowed origins: ${origin}`);
  }
  return { origin, path: queryFreePath(url) };
}

function locatorFromCandidate(base, candidate, inputs) {
  const value = renderTemplate(candidate.value, inputs);
  const options = { exact: candidate.exact };
  switch (candidate.kind) {
    case "role":
      return base.getByRole(candidate.role, value == null ? {} : { name: value, ...options });
    case "label":
      return base.getByLabel(value, options);
    case "placeholder":
      return base.getByPlaceholder(value, options);
    case "test_id":
      return base.getByTestId(value);
    case "text":
      return base.getByText(value, options);
    case "css":
      return base.locator(value);
    default:
      throw new Error(`unsupported locator kind: ${candidate.kind}`);
  }
}

async function resolveLocator(base, candidates, inputs, { wait = false, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  const failures = [];
  for (let index = 0; index < candidates.length; index += 1) {
    const candidate = candidates[index];
    const locator = locatorFromCandidate(base, candidate, inputs);
    try {
      if (wait) {
        await locator.waitFor({ state: "visible", timeoutMs });
      } else if (!(await locator.isVisible())) {
        failures.push(`${candidate.kind}[${index}] not visible`);
        continue;
      }
      return { locator, candidateIndex: index, candidateKind: candidate.kind };
    } catch (error) {
      failures.push(`${candidate.kind}[${index}]: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  throw new LocatorResolutionError(`no locator candidate matched (${failures.join("; ")})`);
}

async function readLocator(locator, read, timeoutMs) {
  if (read.kind === "inner_text") {
    return (await locator.innerText({ timeoutMs })).trim();
  }
  if (read.kind === "text_content") {
    return ((await locator.textContent({ timeoutMs })) ?? "").trim();
  }
  if (read.kind === "attribute") {
    return await locator.getAttribute(read.attribute, { timeoutMs });
  }
  throw new Error(`unsupported read kind: ${read.kind}`);
}

async function readField(container, field, inputs, timeoutMs) {
  try {
    if (field.locator_candidates.length === 0) {
      return await readLocator(container, field.read, timeoutMs);
    }
    const resolved = await resolveLocator(container, field.locator_candidates, inputs, { timeoutMs });
    return await readLocator(resolved.locator, field.read, timeoutMs);
  } catch (error) {
    if (!field.required) {
      return null;
    }
    throw error;
  }
}

function coerceFieldValue(value, declaration, itemIndex = null) {
  const suffix = itemIndex == null ? "" : ` at item ${itemIndex}`;
  if (value == null || String(value).trim() === "") {
    if (declaration.required) {
      throw new Error(`required extracted field is empty: ${declaration.name}${suffix}`);
    }
    return null;
  }
  const text = String(value).trim();
  if (declaration.type === "text") return text;
  if (declaration.type === "date") {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) {
      throw new Error(`extracted field is not an ISO date: ${declaration.name}${suffix}`);
    }
    return text;
  }
  if (declaration.type === "number") {
    const number = Number(text);
    if (!Number.isFinite(number)) {
      throw new Error(`extracted field is not a number: ${declaration.name}${suffix}`);
    }
    return number;
  }
  if (declaration.type === "boolean") {
    if (text.toLowerCase() === "true") return true;
    if (text.toLowerCase() === "false") return false;
    throw new Error(`extracted field is not a boolean: ${declaration.name}${suffix}`);
  }
  throw new Error(`unsupported extracted field type: ${declaration.type}`);
}

async function extractRecords(action, rootLocator, declaration, inputs, timeoutMs) {
  const extraction = action.extract;
  let maxItems = extraction.max_items;
  if (extraction.limit_input_ref != null) {
    const suppliedLimit = inputs[extraction.limit_input_ref];
    if (!Number.isInteger(suppliedLimit) || suppliedLimit < 1) {
      throw new Error(`extraction limit must be a positive integer: ${extraction.limit_input_ref}`);
    }
    maxItems = Math.min(maxItems, suppliedLimit);
  }
  const fieldDeclarations = new Map(declaration.fields.map((field) => [field.name, field]));
  const readRecord = async (container, itemIndex = null) => {
    const record = {};
    for (const field of extraction.fields) {
      const fieldDeclaration = fieldDeclarations.get(field.name);
      if (fieldDeclaration == null) {
        throw new Error(`extraction references an undeclared output field: ${field.name}`);
      }
      const value = await readField(container, field, inputs, timeoutMs);
      record[field.name] = coerceFieldValue(value, fieldDeclaration, itemIndex);
    }
    return record;
  };
  const records = [];
  if (extraction.mode === "single") {
    records.push(await readRecord(rootLocator.nth(0)));
  } else {
    const count = Math.min(await rootLocator.count(), maxItems);
    for (let index = 0; index < count; index += 1) {
      records.push(await readRecord(rootLocator.nth(index), index));
    }
  }
  if (!extraction.empty_allowed && records.length === 0) {
    throw new Error(`extraction produced no records for ${action.output_ref}`);
  }
  if (extraction.dedupe_by.length === 0) {
    return records;
  }
  const seen = new Set();
  return records.filter((record) => {
    const key = canonicalJson(extraction.dedupe_by.map((field) => record[field]));
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

async function extractOutput(action, rootLocator, declaration, inputs, timeoutMs) {
  if (declaration.type === "scalar" || declaration.type === "summary") {
    if (action.extract.mode !== "text") {
      throw new Error(`output ${declaration.name} requires text extraction mode`);
    }
    const value = (await rootLocator.innerText({ timeoutMs })).trim();
    if (!action.extract.empty_allowed && value === "") {
      throw new Error(`text extraction produced an empty value for ${declaration.name}`);
    }
    return value;
  }
  if (declaration.type === "record" && action.extract.mode !== "single") {
    throw new Error(`record output ${declaration.name} requires single extraction mode`);
  }
  if (declaration.type === "record_set" && action.extract.mode !== "list") {
    throw new Error(`record_set output ${declaration.name} requires list extraction mode`);
  }
  const records = await extractRecords(action, rootLocator, declaration, inputs, timeoutMs);
  return declaration.type === "record" ? records[0] ?? null : records;
}

async function downloadedFileEvidence(path) {
  const fileStat = await stat(path);
  if (!fileStat.isFile()) {
    throw new Error("download path is not a regular file");
  }
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) {
    hash.update(chunk);
  }
  return {
    path,
    byte_length: fileStat.size,
    sha256: hash.digest("hex"),
  };
}

function outputCount(value) {
  if (Array.isArray(value)) {
    return value.length;
  }
  return value == null ? 0 : 1;
}

function sanitizedErrorMetadata(code, detail) {
  return {
    code,
    detail_sha256: sha256Text(String(detail)),
  };
}

function classifyRunFailure(error) {
  const detail = error instanceof Error ? error.message : String(error);
  if (error instanceof LocatorResolutionError) return "locator_resolution_failed";
  if (detail.startsWith("browser left allowed origins:")) return "origin_boundary_violation";
  if (detail.startsWith("postcondition failed:")) return "postcondition_failed";
  if (detail.startsWith("required output is missing or incomplete:")) {
    return "required_output_incomplete";
  }
  if (detail.startsWith("consequential action requires current operator approval:")) {
    return "operator_confirmation_required";
  }
  if (detail.startsWith("no transition matched after milestone:")) {
    return "branch_resolution_failed";
  }
  if (detail.startsWith("capability exceeded ")) return "transition_limit_exceeded";
  if (detail.startsWith("connected Chrome runtime lacks ")) return "native_gap";
  return "run_failed";
}

function safeRecoveryText(value, field) {
  if (typeof value !== "string" || value.trim() === "" || value.length > 500) {
    throw new Error(`recovery ${field} must be non-empty text of at most 500 characters`);
  }
  if (EMAIL_ADDRESS.test(value)) {
    throw new Error(`recovery ${field} must not contain an email address`);
  }
  return value.trim();
}

function recoveryRequest({ capability, milestone, action, page, error }) {
  return {
    schema_version: "browser-recovery-request/v1",
    capability: {
      capability_id: capability.capability_id,
      version: capability.version,
      site_name: capability.site.name,
      allowed_origins: capability.site.allowed_origins,
      process_objective: capability.process.objective,
    },
    milestone: {
      milestone_id: milestone.id,
      intent: milestone.intent,
    },
    action: {
      action_id: action.id,
      intent: action.intent,
      operation: action.operation,
      effect: action.effect,
      locator_candidates: structuredClone(action.locator_candidates),
      postcondition_kind: action.postcondition.kind,
    },
    page,
    failure: sanitizedErrorMetadata("locator_not_found", error.message),
    constraints: {
      permitted_change: "one_semantic_locator_candidate",
      same_action_intent_required: true,
      same_operation_required: true,
      same_effect_required: true,
      same_origin_boundary_required: true,
      no_capability_mutation: true,
      no_consequential_recovery: true,
    },
  };
}

async function attemptModelRecovery({
  recoveryHandler,
  capability,
  milestone,
  action,
  context,
  error,
  recoveryProposals,
}) {
  if (
    !(error instanceof LocatorResolutionError) ||
    action.effect === "consequential" ||
    action.operation === "goto"
  ) {
    return null;
  }
  const page = assertAllowedUrl(await context.tab.url(), context.allowedOrigins);
  const request = recoveryRequest({ capability, milestone, action, page, error });
  if (typeof recoveryHandler !== "function") {
    context.pendingRecoveryRequest = request;
    return null;
  }
  const response = await recoveryHandler(request);
  if (response == null) {
    context.pendingRecoveryRequest = request;
    return null;
  }
  if (
    !exactKeys(
      response,
      new Set(["locator_candidate", "rationale", "uncertainty"]),
    )
  ) {
    throw new Error("recovery handler returned an unsupported response shape");
  }
  const candidate = validateRecoveryLocatorCandidate(response.locator_candidate);
  if (
    action.locator_candidates.some(
      (declared) => canonicalJson(declared) === canonicalJson(candidate),
    )
  ) {
    throw new Error("recovery locator must differ from declared candidates");
  }
  const proposal = {
    sequence: recoveryProposals.length + 1,
    milestone_id: milestone.id,
    action_id: action.id,
    action_intent: action.intent,
    operation: action.operation,
    effect: action.effect,
    origin: page.origin,
    path: page.path,
    original_locator_candidates_sha256: sha256Text(
      canonicalJson(action.locator_candidates),
    ),
    candidate_index: action.locator_candidates.length,
    candidate,
    candidate_sha256: sha256Text(canonicalJson(candidate)),
    rationale: safeRecoveryText(response.rationale, "rationale"),
    uncertainty: safeRecoveryText(response.uncertainty, "uncertainty"),
    original_failure: sanitizedErrorMetadata("locator_not_found", error.message),
    outcome: null,
    outcome_error: null,
    approved_for_persistence: false,
  };
  const patchedAction = structuredClone(action);
  patchedAction.locator_candidates.push(candidate);
  try {
    const evidence = await executeAction(patchedAction, context);
    proposal.outcome = "passed";
    recoveryProposals.push(proposal);
    return evidence;
  } catch (recoveryError) {
    proposal.outcome = "failed";
    proposal.outcome_error = sanitizedErrorMetadata(
      "recovery_failed",
      recoveryError instanceof Error ? recoveryError.message : String(recoveryError),
    );
    recoveryProposals.push(proposal);
    throw recoveryError;
  }
}

async function evaluateCondition(condition, context) {
  const { tab, capability, inputs, outputs } = context;
  const timeoutMs = boundedTimeout(condition.timeout_ms);
  switch (condition.kind) {
    case "always":
      return true;
    case "url_path_equals":
      return queryFreePath(await tab.url()) === renderTemplate(condition.value, inputs);
    case "url_includes":
      return (await tab.url()).includes(renderTemplate(condition.value, inputs));
    case "locator_visible": {
      try {
        await resolveLocator(tab.playwright, condition.locator_candidates, inputs, {
          wait: true,
          timeoutMs,
        });
        return true;
      } catch {
        return false;
      }
    }
    case "locator_hidden": {
      try {
        await resolveLocator(tab.playwright, condition.locator_candidates, inputs, { timeoutMs });
        return false;
      } catch {
        return true;
      }
    }
    case "locator_text_contains": {
      try {
        const { locator } = await resolveLocator(tab.playwright, condition.locator_candidates, inputs, {
          wait: true,
          timeoutMs,
        });
        const expected = renderTemplate(condition.value, inputs);
        const deadline = Date.now() + timeoutMs;
        do {
          if ((await locator.innerText({ timeoutMs })).includes(expected)) {
            return true;
          }
          await tab.playwright.waitForTimeout(100);
        } while (Date.now() < deadline);
        return false;
      } catch {
        return false;
      }
    }
    case "output_empty":
      return outputCount(outputs[condition.output_ref]) === 0;
    case "output_nonempty":
      return outputCount(outputs[condition.output_ref]) > 0;
    case "output_count": {
      const count = outputCount(outputs[condition.output_ref]);
      if (condition.comparator === "eq") return count === condition.expected;
      if (condition.comparator === "gte") return count >= condition.expected;
      if (condition.comparator === "lte") return count <= condition.expected;
      throw new Error(`unsupported output comparator: ${condition.comparator}`);
    }
    default:
      throw new Error(`unsupported condition kind: ${condition.kind}`);
  }
}

async function verifyPostcondition(postcondition, context) {
  if (postcondition.kind === "none") {
    return true;
  }
  const passed = await evaluateCondition(postcondition, context);
  if (!passed) {
    throw new Error(`postcondition failed: ${postcondition.kind}`);
  }
  return true;
}

async function executeAction(action, context) {
  const {
    tab,
    capability,
    inputs,
    outputs,
    outputDeclarations,
    approvedConsequentialActions,
  } = context;
  const timeoutMs = boundedTimeout(action.timeout_ms);
  if (action.effect === "consequential" && !approvedConsequentialActions.has(action.id)) {
    throw new Error(`consequential action requires current operator approval: ${action.id}`);
  }

  let locatorCandidate = null;
  let locator = null;
  if (!["goto"].includes(action.operation)) {
    const resolved = await resolveLocator(tab.playwright, action.locator_candidates, inputs, {
      wait: action.operation === "wait_for",
      timeoutMs,
    });
    locator = resolved.locator;
    locatorCandidate = {
      index: resolved.candidateIndex,
      kind: resolved.candidateKind,
    };
  }

  if (action.operation === "goto") {
    const targetOrigin = action.target_origin ?? capability.site.allowed_origins[0];
    if (!capability.site.allowed_origins.includes(targetOrigin)) {
      throw new Error(`goto target origin is not allowed: ${targetOrigin}`);
    }
    await tab.goto(new URL(renderTemplate(action.path, inputs), targetOrigin).href);
  } else if (action.operation === "wait_for") {
    if (!(await locator.isEnabled())) {
      throw new Error(`waited control is disabled: ${action.id}`);
    }
  } else if (action.operation === "click") {
    await locator.click({ timeoutMs });
  } else if (action.operation === "fill") {
    await locator.fill(String(inputs[action.input_ref]), { timeoutMs });
  } else if (action.operation === "press") {
    await locator.press(action.key, { timeoutMs });
  } else if (action.operation === "select") {
    await locator.selectOption(String(inputs[action.input_ref]), { timeoutMs });
  } else if (action.operation === "set_checked") {
    await locator.setChecked(Boolean(inputs[action.input_ref]), { timeoutMs });
  } else if (action.operation === "extract") {
    const declaration = outputDeclarations.get(action.output_ref);
    if (declaration == null || declaration.type === "download_set") {
      throw new Error(`extract action references an incompatible output: ${action.output_ref}`);
    }
    outputs[action.output_ref] = await extractOutput(
      action,
      locator,
      declaration,
      inputs,
      timeoutMs,
    );
  } else if (action.operation === "download") {
    const declaration = outputDeclarations.get(action.output_ref);
    if (declaration?.type !== "download_set" || declaration.delivery !== "artifact_only") {
      throw new Error(`download action requires an artifact-only download_set output`);
    }
    const downloadPromise = tab.playwright.waitForEvent("download", { timeoutMs });
    await locator.click({ timeoutMs });
    const download = await downloadPromise;
    if (typeof download?.path !== "function") {
      throw new Error("connected Chrome runtime lacks download path evidence");
    }
    const path = await download.path({ timeoutMs });
    if (path == null) {
      throw new Error(`download did not produce a local path: ${action.id}`);
    }
    outputs[action.output_ref].push(await downloadedFileEvidence(path));
  } else {
    throw new Error(`unsupported operation: ${action.operation}`);
  }

  const page = assertAllowedUrl(await tab.url(), context.allowedOrigins);
  await verifyPostcondition(action.postcondition, context);
  const outputValue = action.output_ref == null ? null : outputs[action.output_ref];
  return {
    locator_candidate: locatorCandidate,
    origin: page.origin,
    path: page.path,
    output_ref: action.output_ref,
    output_count: outputCount(outputValue),
    output_sha256: outputValue == null ? null : sha256Text(canonicalJson(outputValue)),
  };
}

function requiredOutputSatisfied(declaration, value) {
  if (declaration.type === "record_set") return Array.isArray(value);
  if (declaration.type === "download_set") return Array.isArray(value) && value.length > 0;
  if (declaration.type === "record") return isObject(value);
  if (declaration.type === "scalar") return value !== null && !isObject(value) && !Array.isArray(value);
  if (declaration.type === "summary") return typeof value === "string" && value.trim() !== "";
  return false;
}

async function writeOwnerOnly(path, text) {
  await writeFile(path, text, { encoding: "utf8", flag: "wx", mode: 0o600 });
  await chmod(path, 0o600);
}

function receiptOutputEntries(capability, outputs) {
  return capability.outputs.map((declaration) => {
    const value = outputs[declaration.name];
    return {
      name: declaration.name,
      type: declaration.type,
      sensitivity: declaration.sensitivity,
      delivery: declaration.delivery,
      record_count: outputCount(value),
      sha256: sha256Text(canonicalJson(value)),
      artifact: "outputs.json",
    };
  });
}

function publicSummary(
  receiptPath,
  outputsPath,
  lockPath,
  recoveryProposalsPath,
  recoveryProposalCount,
  receipt,
  capability,
  outputs,
  recoveryRequestForModel,
) {
  const deliveredOutputs = Object.fromEntries(
    capability.outputs
      .filter((declaration) => declaration.delivery !== "artifact_only")
      .map((declaration) => [declaration.name, outputs[declaration.name]]),
  );
  return {
    run_id: receipt.run_id,
    result: receipt.result,
    capability_id: receipt.capability_id,
    completed_milestones: receipt.completed_milestones,
    terminal_milestone: receipt.terminal_milestone,
    outputs: receipt.outputs.map(({ name, type, record_count, sha256 }) => ({
      name,
      type,
      record_count,
      sha256,
    })),
    delivered_outputs: deliveredOutputs,
    receipt_path: receiptPath,
    outputs_path: outputsPath,
    lock_path: lockPath,
    recovery_proposals_path: recoveryProposalsPath,
    recovery_proposal_count: recoveryProposalCount,
    recovery_request: recoveryRequestForModel,
  };
}

export async function executeCapability({
  tab,
  capability,
  inputs = {},
  runDirectory,
  runId,
  approvedConsequentialActions = [],
  recoveryHandler = null,
  clock = () => new Date().toISOString(),
  environment = {},
}) {
  validateRuntimeShape(capability);
  if (!tab?.playwright || typeof tab.url !== "function" || typeof tab.goto !== "function") {
    throw new Error("executeCapability requires a connected Chrome tab");
  }
  if (!SAFE_ID.test(runId ?? "")) {
    throw new Error("runId must be a lower-case slug");
  }
  const consequentialActionIds = new Set(
    capability.milestones.flatMap((milestone) =>
      milestone.actions
        .filter((action) => action.effect === "consequential")
        .map((action) => action.id),
    ),
  );
  for (const actionId of approvedConsequentialActions) {
    if (!consequentialActionIds.has(actionId)) {
      throw new Error(`approval does not name a consequential action: ${actionId}`);
    }
  }
  const resolvedInputs = resolveInputs(capability, inputs);
  const resolvedRunDirectory = resolve(runDirectory);
  await mkdir(dirname(resolvedRunDirectory), { recursive: true, mode: 0o700 });
  await mkdir(resolvedRunDirectory, { mode: 0o700 });
  await chmod(resolvedRunDirectory, 0o700);

  const startedAt = clock();
  const allowedOrigins = new Set(capability.site.allowed_origins.map(normalizeOrigin));
  const inputHashes = Object.fromEntries(
    Object.entries(resolvedInputs).map(([name, value]) => [name, sha256Text(canonicalJson(value))]),
  );
  const outputs = initialOutputs(capability);
  const outputDeclarations = new Map(capability.outputs.map((output) => [output.name, output]));
  const milestones = new Map(capability.milestones.map((milestone) => [milestone.id, milestone]));
  const completedMilestones = [];
  const actionResults = [];
  const recoveryProposals = [];
  const approved = new Set(approvedConsequentialActions);
  const executionHash = executionContractSha256(capability);
  let currentMilestoneId = capability.entry_milestone;
  let terminalMilestone = null;
  let failure = null;

  const context = {
    tab,
    capability,
    inputs: resolvedInputs,
    outputs,
    outputDeclarations,
    allowedOrigins,
    approvedConsequentialActions: approved,
    pendingRecoveryRequest: null,
  };

  try {
    for (let transitionCount = 0; transitionCount < MAX_TRANSITIONS; transitionCount += 1) {
      const milestone = milestones.get(currentMilestoneId);
      if (milestone == null) {
        throw new Error(`unknown milestone: ${currentMilestoneId}`);
      }
      for (const action of milestone.actions) {
        const actionStartedAt = clock();
        try {
          let evidence;
          try {
            evidence = await executeAction(action, context);
          } catch (error) {
            evidence = await attemptModelRecovery({
              recoveryHandler,
              capability,
              milestone,
              action,
              context,
              error,
              recoveryProposals,
            });
            if (evidence == null) {
              throw error;
            }
          }
          actionResults.push({
            milestone_id: milestone.id,
            action_id: action.id,
            operation: action.operation,
            result: "passed",
            started_at: actionStartedAt,
            finished_at: clock(),
            ...evidence,
            error: null,
          });
        } catch (error) {
          actionResults.push({
            milestone_id: milestone.id,
            action_id: action.id,
            operation: action.operation,
            result: "failed",
            started_at: actionStartedAt,
            finished_at: clock(),
            locator_candidate: null,
            origin: null,
            path: null,
            output_ref: action.output_ref,
            output_count: 0,
            output_sha256: null,
            error: sanitizedErrorMetadata(
              "action_failed",
              error instanceof Error ? error.message : String(error),
            ),
          });
          throw error;
        }
      }
      completedMilestones.push(milestone.id);
      let transition = null;
      for (const candidate of milestone.transitions) {
        if (await evaluateCondition(candidate.when, context)) {
          transition = candidate;
          break;
        }
      }
      if (transition == null) {
        throw new Error(`no transition matched after milestone: ${milestone.id}`);
      }
      if (transition.terminal) {
        terminalMilestone = milestone.id;
        break;
      }
      currentMilestoneId = transition.next_milestone;
    }
    if (terminalMilestone == null) {
      throw new Error(`capability exceeded ${MAX_TRANSITIONS} milestone transitions`);
    }
    if (!capability.completion.terminal_milestones.includes(terminalMilestone)) {
      throw new Error(`undeclared terminal milestone: ${terminalMilestone}`);
    }
    for (const output of capability.completion.required_outputs) {
      const declaration = outputDeclarations.get(output);
      if (declaration == null || !requiredOutputSatisfied(declaration, outputs[output])) {
        throw new Error(`required output is missing or incomplete: ${output}`);
      }
    }
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    failure = sanitizedErrorMetadata(classifyRunFailure(error), detail);
  }

  const outputsPath = join(resolvedRunDirectory, "outputs.json");
  const receiptPath = join(resolvedRunDirectory, "run.receipt.json");
  const lockPath = join(resolvedRunDirectory, "run.lock.json");
  const recoveryProposalsPath =
    recoveryProposals.length === 0
      ? null
      : join(resolvedRunDirectory, "recovery.proposals.json");
  await writeOwnerOnly(outputsPath, canonicalJson(outputs));
  let recoveryProposalsText = null;
  if (recoveryProposalsPath != null) {
    recoveryProposalsText = canonicalJson({
      schema_version: RECOVERY_PROPOSAL_SCHEMA,
      runtime_version: RUNTIME_VERSION,
      run_id: runId,
      capability_id: capability.capability_id,
      capability_version: capability.version,
      execution_contract_sha256: executionHash,
      discovery_record_sha256: capability.provenance.discovery_record_sha256,
      proposals: recoveryProposals,
      portable: false,
      requires_operator_review_before_persistence: true,
    });
    await writeOwnerOnly(recoveryProposalsPath, recoveryProposalsText);
  }
  const receipt = {
    schema_version: RECEIPT_SCHEMA,
    runtime_version: RUNTIME_VERSION,
    run_id: runId,
    capability_id: capability.capability_id,
    capability_version: capability.version,
    execution_contract_sha256: executionHash,
    discovery_record_sha256: capability.provenance.discovery_record_sha256,
    started_at: startedAt,
    finished_at: clock(),
    result: failure == null ? "passed" : "failed",
    entry_milestone: capability.entry_milestone,
    completed_milestones: completedMilestones,
    terminal_milestone: terminalMilestone,
    action_results: actionResults,
    outputs: receiptOutputEntries(capability, outputs),
    input_hashes: inputHashes,
    locator_changes_during_run: recoveryProposals.length > 0,
    private_evidence_retained: false,
    environment: {
      browser: "existing_chrome",
      controller: "chrome_extension",
      origin_ui: capability.site.name,
      locale: environment.locale ?? "unknown",
    },
    error: failure,
  };
  const receiptText = canonicalJson(receipt);
  await writeOwnerOnly(receiptPath, receiptText);
  const lock = {
    schema_version:
      recoveryProposalsText == null ? "browser-run-lock/v1" : "browser-run-lock/v2",
    run_id: runId,
    capability_id: capability.capability_id,
    execution_contract_sha256: executionHash,
    outputs_sha256: sha256Text(canonicalJson(outputs)),
    receipt_sha256: sha256Text(receiptText),
    ...(recoveryProposalsText == null
      ? {}
      : { recovery_proposals_sha256: sha256Text(recoveryProposalsText) }),
  };
  await writeOwnerOnly(lockPath, canonicalJson(lock));

  const summary = publicSummary(
    receiptPath,
    outputsPath,
    lockPath,
    recoveryProposalsPath,
    recoveryProposals.length,
    receipt,
    capability,
    outputs,
    context.pendingRecoveryRequest,
  );
  if (failure != null) {
    const error = new Error(
      `browser capability run failed: ${failure.code} (${failure.detail_sha256})`,
    );
    error.code = failure.code;
    error.detailSha256 = failure.detail_sha256;
    error.runSummary = summary;
    throw error;
  }
  return summary;
}
