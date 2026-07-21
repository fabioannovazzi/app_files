from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["main"]

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Target:
    plugin: str
    apply_tool: str
    display_name: str
    validation_type: str
    validate_tool: str
    render_tool: str
    save_tool: str

    @property
    def server_path(self) -> Path:
        return ROOT / "plugins" / self.plugin / "mcp" / "server.cjs"

    @property
    def instruction(self) -> str:
        if self.plugin == "prompt-optimizer":
            return (
                "Use validate_prompt_optimizer_review before render_prompt_optimizer_review. "
                "Prefer the MCP widget for final Prompt Optimizer package review; "
                "use save_prompt_optimizer_decisions to persist review actions and "
                "apply_prompt_optimizer_decisions to write applied_decisions.json plus "
                "final_artifacts.json status; use native Plan-mode choices or chat for "
                "simple pre-draft intake decisions."
            )
        return (
            f"Use {self.validate_tool} before {self.render_tool}. Prefer the MCP widget "
            f"for {self.display_name} review handoff; use {self.save_tool} to persist "
            f"reviewer actions to ui_decisions.json and {self.apply_tool} to write "
            "applied_decisions.json plus final_artifacts.json status when decisions "
            "are collected; fall back to Markdown/static review only when MCP is unavailable."
        )


TARGETS = [
    Target(
        "check-entries",
        "apply_check_entries_decisions",
        "Check Entries",
        "check_entries",
        "validate_check_entries_review",
        "render_check_entries_review",
        "save_check_entries_decisions",
    ),
    Target(
        "deep-research-validator",
        "apply_deep_research_decisions",
        "Deep Research",
        "deep_research",
        "validate_deep_research_review",
        "render_deep_research_review",
        "save_deep_research_decisions",
    ),
    Target(
        "client-file-preparation",
        "apply_client_file_preparation_decisions",
        "New Client · File Preparation",
        "client_file_preparation",
        "validate_client_file_preparation_review",
        "render_client_file_preparation_review",
        "save_client_file_preparation_decisions",
    ),
    Target(
        "audit-reconciliation",
        "apply_audit_reconciliation_decisions",
        "Audit Reconciliation",
        "audit_reconciliation",
        "validate_audit_reconciliation_review",
        "render_audit_reconciliation_review",
        "save_audit_reconciliation_decisions",
    ),
    Target(
        "journal-sampling",
        "apply_journal_sampling_decisions",
        "Journal Sampling",
        "journal_sampling",
        "validate_journal_sampling_review",
        "render_journal_sampling_review",
        "save_journal_sampling_decisions",
    ),
    Target(
        "journal-bank-reconciliation",
        "apply_journal_bank_decisions",
        "Journal-Bank",
        "journal_bank",
        "validate_journal_bank_review",
        "render_journal_bank_review",
        "save_journal_bank_decisions",
    ),
    Target(
        "report-builder",
        "apply_report_builder_decisions",
        "Build Report",
        "report_builder",
        "validate_report_builder_review",
        "render_report_builder_review",
        "save_report_builder_decisions",
    ),
    Target(
        "prompt-optimizer",
        "apply_prompt_optimizer_decisions",
        "Prompt Optimizer",
        "prompt_optimizer",
        "validate_prompt_optimizer_review",
        "render_prompt_optimizer_review",
        "save_prompt_optimizer_decisions",
    ),
    Target(
        "concordato-plan-review",
        "apply_concordato_plan_decisions",
        "Concordato Plan Review",
        "concordato_plan",
        "validate_concordato_plan_review",
        "render_concordato_plan_review",
        "save_concordato_plan_decisions",
    ),
    Target(
        "variance-analysis",
        "apply_variance_analysis_decisions",
        "Variance Analysis",
        "variance_analysis",
        "validate_variance_analysis_review",
        "render_variance_analysis_review",
        "save_variance_analysis_decisions",
    ),
    Target(
        "period-comparison",
        "apply_period_comparison_decisions",
        "Period Comparison",
        "period_comparison",
        "validate_period_comparison_review",
        "render_period_comparison_review",
        "save_period_comparison_decisions",
    ),
    Target(
        "mix-contribution-analysis",
        "apply_mix_contribution_decisions",
        "Mix Contribution",
        "mix_contribution",
        "validate_mix_contribution_review",
        "render_mix_contribution_review",
        "save_mix_contribution_decisions",
    ),
    Target(
        "scatter-bubble-analysis",
        "apply_scatter_bubble_decisions",
        "Scatter Bubble",
        "scatter_bubble",
        "validate_scatter_bubble_review",
        "render_scatter_bubble_review",
        "save_scatter_bubble_decisions",
    ),
    Target(
        "distribution-analysis",
        "apply_distribution_decisions",
        "Distribution",
        "distribution",
        "validate_distribution_review",
        "render_distribution_review",
        "save_distribution_decisions",
    ),
    Target(
        "set-overlap-analysis",
        "apply_set_overlap_decisions",
        "Set Overlap",
        "set_overlap",
        "validate_set_overlap_review",
        "render_set_overlap_review",
        "save_set_overlap_decisions",
    ),
]


APPLY_HELPERS = """function resolveRunOutputDir(inputArgs) {
  const runIntake = isPlainObject(inputArgs.run_intake) ? inputArgs.run_intake : null;
  const outputDir = typeof runIntake?.output_dir === "string" ? runIntake.output_dir.trim() : "";
  return outputDir ? path.resolve(outputDir) : null;
}

function resolveAppliedDecisionOutputPath(inputArgs) {
  const outputDir = resolveRunOutputDir(inputArgs);
  return outputDir ? path.join(outputDir, "applied_decisions.json") : null;
}

function resolveFinalArtifactsOutputPath(inputArgs) {
  const outputDir = resolveRunOutputDir(inputArgs);
  return outputDir ? path.join(outputDir, "final_artifacts.json") : null;
}

function shortString(value) {
  return typeof value === "string" ? value.trim() : "";
}

const REVISION_TEXT_EXTENSIONS = new Set([
  ".htm",
  ".html",
  ".md",
  ".sql",
  ".txt",
  ".xml",
  ".yaml",
  ".yml",
]);

const DIRECT_TEXT_UPDATE_EXTENSIONS = new Set([
  ".htm",
  ".html",
  ".md",
  ".sql",
  ".txt",
  ".xml",
  ".yaml",
  ".yml",
]);

const STRUCTURED_UPDATE_EXTENSIONS = new Set([".csv", ".json", ".jsonl"]);

const NATIVE_REGENERATION_EXTENSIONS = new Set([
  ".docx",
  ".pdf",
  ".pptx",
  ".xls",
  ".xlsm",
  ".xlsx",
]);

const DERIVED_NATIVE_REGENERATION_TARGETS = new Map([
  ["check_results.csv", ["check_results.xlsx"]],
  ["codex_run_review.md", ["concordato_review_summary.docx"]],
  ["reconciliation_matches.csv", ["journal_bank_reconciliation.xlsx"]],
]);

function safePathSegment(value, fallback) {
  const cleaned = shortString(value)
    .replace(/[^a-zA-Z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return cleaned || fallback;
}

function revisionExtension(targetArtifact) {
  const extension = path.extname(shortString(targetArtifact)).toLowerCase();
  return REVISION_TEXT_EXTENSIONS.has(extension) ? extension : ".txt";
}

function revisionRelativePath(effect) {
  const extension = revisionExtension(effect.target_artifact);
  const targetArtifact = shortString(effect.target_artifact);
  const targetExtension = path.extname(targetArtifact) || extension;
  const sourceBase = path.basename(targetArtifact || "review-item", targetExtension);
  const base = safePathSegment(sourceBase, "review-item");
  const itemId = safePathSegment(effect.item_id, "item");
  return path.join("revisions", `${base}__${itemId}${extension}`).split(path.sep).join("/");
}

function normalizeRelativePath(filePath) {
  return filePath.split(path.sep).join("/");
}

function artifactPathKey(value) {
  return normalizeRelativePath(shortString(value)).replace(/\\\\/g, "/").replace(/^\\.\\//, "");
}

function resolveSafeRunOutputPath(outputDir, value) {
  const rawPath = shortString(value);
  if (!outputDir || !rawPath) return null;
  const absolutePath = path.resolve(outputDir, rawPath);
  const relativePath = path.relative(outputDir, absolutePath);
  if (!relativePath || relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
    return null;
  }
  return {
    absolutePath,
    relativePath: normalizeRelativePath(relativePath),
  };
}

function canDirectlyUpdateTextArtifact(targetArtifact) {
  const extension = path.extname(shortString(targetArtifact)).toLowerCase();
  return DIRECT_TEXT_UPDATE_EXTENSIONS.has(extension);
}

function canUpdateStructuredArtifact(targetArtifact) {
  const extension = path.extname(shortString(targetArtifact)).toLowerCase();
  return STRUCTURED_UPDATE_EXTENSIONS.has(extension);
}

function needsNativeRegeneration(targetArtifact) {
  const extension = path.extname(shortString(targetArtifact)).toLowerCase();
  return NATIVE_REGENERATION_EXTENSIONS.has(extension);
}

function currentFinalArtifactsForApplication(inputArgs, finalArtifactsPath) {
  return (
    (isPlainObject(inputArgs.final_artifacts) ? inputArgs.final_artifacts : null) ||
    readJsonFileIfPresent(finalArtifactsPath) ||
    {}
  );
}

function finalArtifactsOutputPaths(currentFinalArtifacts) {
  const outputs = Array.isArray(currentFinalArtifacts?.outputs)
    ? currentFinalArtifacts.outputs
    : [];
  return new Set(
    outputs
      .map((output) => artifactPathKey(output?.path))
      .filter(Boolean),
  );
}

function existingDerivedNativeTargets(outputDir, currentFinalArtifacts, sourceArtifact) {
  const sourceKey = artifactPathKey(sourceArtifact);
  const candidates = DERIVED_NATIVE_REGENERATION_TARGETS.get(sourceKey) || [];
  if (!candidates.length) return [];
  const declaredOutputPaths = finalArtifactsOutputPaths(currentFinalArtifacts);
  return candidates.filter((candidate) => {
    const candidateKey = artifactPathKey(candidate);
    if (declaredOutputPaths.has(candidateKey)) return true;
    const target = resolveSafeRunOutputPath(outputDir, candidateKey);
    return Boolean(target && fs.existsSync(target.absolutePath));
  });
}

function csvEscape(value) {
  const text = String(value ?? "");
  if (!/[",\\r\\n]/.test(text)) return text;
  return `"${text.replace(/"/g, '""')}"`;
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (inQuotes) {
      if (char === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        inQuotes = false;
      } else {
        field += char;
      }
      continue;
    }
    if (char === '"') {
      inQuotes = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (char === "\\r") {
      if (text[index + 1] === "\\n") index += 1;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (inQuotes) throw new Error("CSV parse failed: unclosed quoted field");
  if (field !== "" || row.length || !text.endsWith("\\n")) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

function serializeCsv(rows) {
  return `${rows.map((row) => row.map(csvEscape).join(",")).join("\\n")}\\n`;
}

function structuredUpdateSpec(effect) {
  // Native table/object edits are deterministic only when the review payload names the exact row and field.
  if (!effect.target_artifact || !effect.target_id_field || !effect.target_record_id || !effect.target_field) {
    return null;
  }
  return {
    idField: effect.target_id_field,
    recordId: effect.target_record_id,
    targetField: effect.target_field,
    recordsKey: effect.target_records_key || null,
  };
}

function updateMatchingRecord(records, spec, editValue) {
  if (!Array.isArray(records)) throw new Error("structured artifact records must be an array");
  let updated = 0;
  for (const record of records) {
    if (!isPlainObject(record)) continue;
    if (String(record[spec.idField] ?? "") !== spec.recordId) continue;
    record[spec.targetField] = editValue;
    updated += 1;
  }
  if (updated !== 1) {
    throw new Error(
      `structured edit expected exactly one record for ${spec.idField}=${spec.recordId}, found ${updated}`,
    );
  }
  return updated;
}

function updateCsvArtifact(filePath, effect, spec) {
  const rows = parseCsv(fs.readFileSync(filePath, "utf8"));
  if (!rows.length) throw new Error("CSV structured edit requires a header row");
  const header = rows[0];
  const idIndex = header.indexOf(spec.idField);
  const fieldIndex = header.indexOf(spec.targetField);
  if (idIndex < 0) throw new Error(`CSV structured edit missing id column ${spec.idField}`);
  if (fieldIndex < 0) throw new Error(`CSV structured edit missing target column ${spec.targetField}`);
  let updated = 0;
  for (const row of rows.slice(1)) {
    if (String(row[idIndex] ?? "") !== spec.recordId) continue;
    while (row.length < header.length) row.push("");
    row[fieldIndex] = effect.edit_value;
    updated += 1;
  }
  if (updated !== 1) {
    throw new Error(
      `CSV structured edit expected exactly one row for ${spec.idField}=${spec.recordId}, found ${updated}`,
    );
  }
  fs.writeFileSync(filePath, serializeCsv(rows), "utf8");
  return { updatedRows: updated, rowCount: Math.max(rows.length - 1, 0) };
}

function updateJsonArtifact(filePath, effect, spec) {
  const parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
  if (Array.isArray(parsed)) {
    const updatedRows = updateMatchingRecord(parsed, spec, effect.edit_value);
    fs.writeFileSync(filePath, `${JSON.stringify(parsed, null, 2)}\\n`, "utf8");
    return { updatedRows, rowCount: parsed.length };
  }
  if (isPlainObject(parsed) && spec.recordsKey && Array.isArray(parsed[spec.recordsKey])) {
    const records = parsed[spec.recordsKey];
    const updatedRows = updateMatchingRecord(records, spec, effect.edit_value);
    fs.writeFileSync(filePath, `${JSON.stringify(parsed, null, 2)}\\n`, "utf8");
    return { updatedRows, rowCount: records.length };
  }
  if (isPlainObject(parsed) && String(parsed[spec.idField] ?? "") === spec.recordId) {
    parsed[spec.targetField] = effect.edit_value;
    fs.writeFileSync(filePath, `${JSON.stringify(parsed, null, 2)}\\n`, "utf8");
    return { updatedRows: 1, rowCount: 1 };
  }
  throw new Error("JSON structured edit requires an object, array, or explicit records_key array");
}

function updateJsonlArtifact(filePath, effect, spec) {
  const text = fs.readFileSync(filePath, "utf8");
  const records = text
    .split(/\\r?\\n/)
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line));
  const updatedRows = updateMatchingRecord(records, spec, effect.edit_value);
  fs.writeFileSync(filePath, `${records.map((record) => JSON.stringify(record)).join("\\n")}\\n`, "utf8");
  return { updatedRows, rowCount: records.length };
}

function originalBackupRelativePath(effect, targetRelativePath) {
  const extension = path.extname(targetRelativePath).toLowerCase() || ".txt";
  const sourceBase = path.basename(targetRelativePath, extension);
  const base = safePathSegment(sourceBase, "artifact");
  const itemId = safePathSegment(effect.item_id, "item");
  return normalizeRelativePath(path.join("revisions", "originals", `${base}__${itemId}${extension}`));
}

function readJsonFileIfPresent(filePath) {
  if (!filePath || !fs.existsSync(filePath)) return null;
  try {
    const parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
    return isPlainObject(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function uniqueStrings(values) {
  return Array.from(
    new Set(
      values
        .map((value) => shortString(value))
        .filter(Boolean),
    ),
  );
}

function collectReviewApplicationPaths(appliedDecisions, finalArtifacts) {
  const paths = ["ui_decisions.json", "applied_decisions.json", "final_artifacts.json"];
  const finalOutputs = Array.isArray(finalArtifacts?.outputs) ? finalArtifacts.outputs : [];
  if (
    finalOutputs.some(
      (output) => isPlainObject(output) && output.path === "review_handoff.md",
    )
  ) {
    paths.push("review_handoff.md");
  }
  const reviewApplication = isPlainObject(finalArtifacts?.review_application)
    ? finalArtifacts.review_application
    : {};
  for (const fieldName of [
    "applied_decisions_path",
    "revision_paths",
    "target_update_paths",
    "structured_update_paths",
    "native_regeneration_paths",
    "native_regenerated_paths",
    "downstream_regenerated_paths",
    "original_backup_paths",
  ]) {
    const value = reviewApplication[fieldName] ?? appliedDecisions?.[fieldName];
    if (Array.isArray(value)) paths.push(...value);
    else paths.push(value);
  }
  return uniqueStrings(paths);
}

function appendReviewApplicationExecutionTrace(
  inputArgs,
  outputDir,
  appliedDecisions,
  finalArtifacts,
) {
  if (!outputDir) return null;
  const runIntakePath = path.join(outputDir, "run_intake.json");
  const current = readJsonFileIfPresent(runIntakePath) ||
    (isPlainObject(inputArgs.run_intake) ? { ...inputArgs.run_intake } : null);
  if (!current) return null;
  const trace = Array.isArray(current.execution_trace) ? [...current.execution_trace] : [];
  const appliedAt = shortString(appliedDecisions?.applied_at) || new Date().toISOString();
  const stepIdSuffix = appliedAt.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  trace.push({
    step_id: `${shortString(appliedDecisions?.workflow) || "__VALIDATION_TYPE__"}_review_apply_${stepIdSuffix || Date.now()}`,
    kind: "deterministic_review_apply",
    status: "passed",
    execution_location: "local_codex_workspace",
    command: [SERVER_NAME, TOOL_NAMES.applyDecisions],
    inputs: uniqueStrings([
      appliedDecisions?.review_payload?.path || "review_payload.json",
      "ui_decisions.json",
      "final_artifacts.json",
    ]),
    outputs: collectReviewApplicationPaths(appliedDecisions, finalArtifacts),
  });
  const updated = { ...current, execution_trace: trace };
  fs.mkdirSync(path.dirname(runIntakePath), { recursive: true });
  fs.writeFileSync(runIntakePath, `${JSON.stringify(updated, null, 2)}\\n`, "utf8");
  return runIntakePath;
}

function requestedDocumentsFromReviewContext(decision, item, data) {
  if (Array.isArray(decision.requested_documents) && decision.requested_documents.length) {
    return decision.requested_documents;
  }
  if (decision.action !== "request_more_documents") return [];
  const candidates = [];
  function add(value) {
    if (Array.isArray(value)) {
      for (const entry of value) add(entry);
      return;
    }
    const text = shortString(value);
    if (text) candidates.push(text);
  }
  for (const key of [
    "requested_document",
    "requested_documents",
    "missing_document",
    "missing_documents",
    "required_document",
    "required_documents",
    "support_document",
    "support_documents",
  ]) {
    add(data[key]);
  }
  const evidence = Array.isArray(item.evidence) ? item.evidence : [];
  for (const record of evidence) {
    if (!isPlainObject(record)) continue;
    for (const key of [
      "requested_document",
      "requested_documents",
      "missing_document",
      "missing_documents",
      "required_document",
      "required_documents",
      "support_document",
      "support_documents",
    ]) {
      add(record[key]);
    }
  }
  return Array.from(new Set(candidates));
}

function compactContextValue(value) {
  if (value == null || value === "") return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return String(value);
  return "";
}

function followupContextFromReviewContext(decision, item, data) {
  if (isPlainObject(decision.followup_context) && Object.keys(decision.followup_context).length) {
    return decision.followup_context;
  }
  if (!["reject", "mark_unclear", "request_more_documents"].includes(decision.action)) return {};
  const records = [
    data,
    ...(Array.isArray(item.evidence) ? item.evidence.filter(isPlainObject) : []),
  ];
  const fields = [
    ["owner", ["owner", "responsible_party", "assignee", "contact", "client_contact"]],
    ["source_system", ["source_system", "system", "source_system_name"]],
    ["source_file", ["source_file", "filename", "file_name", "source_workbook"]],
    ["source_table", ["source_table", "sheet", "worksheet", "table"]],
    ["due_date", ["due_date", "deadline", "response_due_date"]],
    ["period", ["period", "tax_period", "fiscal_year", "year"]],
    ["entity", ["entity", "client", "company", "account", "counterparty", "beneficiary"]],
    ["record_id", ["record_id", "source_row", "movement_number", "bank_transaction_id", "journal_entry_id", "claim_index"]],
    ["amount", ["amount", "amount_abs", "amount_value"]],
    ["reason", ["reason", "missing_reason", "blocking_reason", "mismatches"]],
    ["priority", ["priority", "severity"]],
  ];
  const context = {};
  for (const [targetKey, sourceKeys] of fields) {
    for (const record of records) {
      for (const sourceKey of sourceKeys) {
        const value = compactContextValue(record[sourceKey]);
        if (!value) continue;
        context[targetKey] = value;
        break;
      }
      if (context[targetKey]) break;
    }
  }
  return context;
}

function buildApplicationEffect(decision, item, appliedAt) {
  const data = isPlainObject(item.data) ? item.data : {};
  const targetArtifact =
    shortString(data.target_artifact) ||
    shortString(item.output_path) ||
    shortString(data.path);
  const targetPath =
    shortString(data.target_path) ||
    shortString(data.field_path) ||
    shortString(data.field);
  const targetIdField =
    shortString(data.target_id_field) ||
    shortString(data.record_id_field);
  const targetRecordId =
    shortString(data.target_record_id) ||
    shortString(data.record_id);
  const targetField =
    shortString(data.target_field) ||
    shortString(data.edit_field);
  const targetRecordsKey =
    shortString(data.target_records_key) ||
    shortString(data.records_key);
  const requiresFollowup = new Set(["reject", "mark_unclear", "request_more_documents"]).has(
    decision.action,
  );
  const requestedDocuments = requestedDocumentsFromReviewContext(decision, item, data);
  const followupContext = followupContextFromReviewContext(decision, item, data);
  const effect = {
    item_id: decision.item_id,
    item_type: decision.item_type,
    title: decision.title,
    action: decision.action,
    status: decision.status,
    applied_at: appliedAt,
    applied: true,
    requires_followup: requiresFollowup,
    target_artifact: targetArtifact || null,
    target_path: targetPath || null,
    target_id_field: targetIdField || null,
    target_record_id: targetRecordId || null,
    target_field: targetField || null,
    target_records_key: targetRecordsKey || null,
    source_path: shortString(item.source_path) || null,
    artifact_update:
      decision.action === "edit"
        ? "revision_artifact_pending"
        : targetArtifact
          ? "decision_manifest_only"
          : "review_record_only",
  };
  if (decision.reviewer_note) effect.reviewer_note = decision.reviewer_note;
  if (decision.edit_value) effect.edit_value = decision.edit_value;
  if (requestedDocuments.length) {
    effect.requested_documents = requestedDocuments;
  }
  if (Object.keys(followupContext).length) {
    effect.followup_context = followupContext;
  }
  return effect;
}

function writeRevisionArtifacts(outputDir, effects) {
  if (!outputDir) return [];
  const revisionOutputs = [];
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    const relativePath = revisionRelativePath(effect);
    const absolutePath = path.join(outputDir, relativePath);
    fs.mkdirSync(path.dirname(absolutePath), { recursive: true });
    fs.writeFileSync(absolutePath, effect.edit_value, "utf8");
    effect.revision_artifact = relativePath;
    effect.artifact_update = "revision_artifact_written";
    revisionOutputs.push({
      path: relativePath,
      kind: revisionExtension(effect.target_artifact).replace(/^\\./, "") || "txt",
      status: "written_revision",
      source_artifact: effect.target_artifact,
      item_id: effect.item_id,
    });
  }
  return revisionOutputs;
}

function writeDirectTextArtifactUpdates(outputDir, effects) {
  if (!outputDir) return { targetOutputs: [], backupOutputs: [] };
  const targetOutputs = [];
  const backupOutputs = [];
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    if (!canDirectlyUpdateTextArtifact(effect.target_artifact)) continue;
    const target = resolveSafeRunOutputPath(outputDir, effect.target_artifact);
    if (!target || !fs.existsSync(target.absolutePath)) continue;
    const stat = fs.statSync(target.absolutePath);
    if (!stat.isFile()) continue;
    const backupRelativePath = originalBackupRelativePath(effect, target.relativePath);
    const backupAbsolutePath = path.join(outputDir, backupRelativePath);
    fs.mkdirSync(path.dirname(backupAbsolutePath), { recursive: true });
    if (!fs.existsSync(backupAbsolutePath)) {
      fs.writeFileSync(backupAbsolutePath, fs.readFileSync(target.absolutePath, "utf8"), "utf8");
    }
    fs.writeFileSync(target.absolutePath, effect.edit_value, "utf8");
    effect.target_artifact = target.relativePath;
    effect.original_artifact_backup = backupRelativePath;
    effect.artifact_update = "target_artifact_updated";
    targetOutputs.push({
      path: target.relativePath,
      kind: path.extname(target.relativePath).replace(/^\\./, "") || "txt",
      status: "updated_from_review",
      item_id: effect.item_id,
    });
    backupOutputs.push({
      path: backupRelativePath,
      kind: path.extname(backupRelativePath).replace(/^\\./, "") || "txt",
      status: "backup_original",
      source_artifact: target.relativePath,
      item_id: effect.item_id,
    });
  }
  return { targetOutputs, backupOutputs };
}

function writeStructuredArtifactUpdates(outputDir, effects) {
  if (!outputDir) return { targetOutputs: [], backupOutputs: [] };
  const targetOutputs = [];
  const backupOutputs = [];
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    const spec = structuredUpdateSpec(effect);
    if (!spec) continue;
    if (!canUpdateStructuredArtifact(effect.target_artifact)) continue;
    const target = resolveSafeRunOutputPath(outputDir, effect.target_artifact);
    if (!target || !fs.existsSync(target.absolutePath)) continue;
    const stat = fs.statSync(target.absolutePath);
    if (!stat.isFile()) continue;
    const backupRelativePath = originalBackupRelativePath(effect, target.relativePath);
    const backupAbsolutePath = path.join(outputDir, backupRelativePath);
    fs.mkdirSync(path.dirname(backupAbsolutePath), { recursive: true });
    if (!fs.existsSync(backupAbsolutePath)) {
      fs.copyFileSync(target.absolutePath, backupAbsolutePath);
    }
    const extension = path.extname(target.relativePath).toLowerCase();
    const result =
      extension === ".csv"
        ? updateCsvArtifact(target.absolutePath, effect, spec)
        : extension === ".jsonl"
          ? updateJsonlArtifact(target.absolutePath, effect, spec)
          : updateJsonArtifact(target.absolutePath, effect, spec);
    effect.target_artifact = target.relativePath;
    effect.original_artifact_backup = backupRelativePath;
    effect.artifact_update = "structured_artifact_updated";
    effect.structured_update = {
      id_field: spec.idField,
      record_id: spec.recordId,
      target_field: spec.targetField,
      records_key: spec.recordsKey,
      updated_rows: result.updatedRows,
    };
    targetOutputs.push({
      path: target.relativePath,
      kind: extension.replace(/^\\./, "") || "file",
      status: "updated_from_review",
      item_id: effect.item_id,
      row_count: result.rowCount,
      required_columns: [spec.idField, spec.targetField],
    });
    backupOutputs.push({
      path: backupRelativePath,
      kind: path.extname(backupRelativePath).replace(/^\\./, "") || "file",
      status: "backup_original",
      source_artifact: target.relativePath,
      item_id: effect.item_id,
    });
  }
  return { targetOutputs, backupOutputs };
}

function markNativeRegenerationPending(effects) {
  const nativeOutputs = [];
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    if (effect.artifact_update !== "revision_artifact_written") continue;
    if (!needsNativeRegeneration(effect.target_artifact)) continue;
    effect.requires_native_regeneration = true;
    effect.native_regeneration_status = "pending";
    effect.artifact_update = "native_regeneration_pending";
    nativeOutputs.push({
      path: effect.target_artifact,
      kind: path.extname(effect.target_artifact || "").replace(/^\\./, "") || "file",
      status: "native_regeneration_pending",
      item_id: effect.item_id,
      revision_artifact: effect.revision_artifact || null,
    });
  }
  return nativeOutputs;
}

function markDerivedNativeRegenerationPending(outputDir, effects, currentFinalArtifacts) {
  const nativeOutputs = [];
  for (const effect of effects) {
    if (effect.action !== "edit" || !effect.edit_value) continue;
    if (!["revision_artifact_written", "structured_artifact_updated"].includes(effect.artifact_update)) continue;
    const derivedTargets = existingDerivedNativeTargets(
      outputDir,
      currentFinalArtifacts,
      effect.target_artifact,
    );
    if (!derivedTargets.length) continue;
    effect.requires_native_regeneration = true;
    effect.native_regeneration_status = "pending";
    effect.derived_native_regeneration_paths = derivedTargets;
    for (const targetPath of derivedTargets) {
      nativeOutputs.push({
        path: targetPath,
        kind: path.extname(targetPath).replace(/^\\./, "") || "file",
        status: "native_regeneration_pending",
        item_id: effect.item_id,
        source_artifact: effect.target_artifact,
      });
    }
  }
  return nativeOutputs;
}

function nativeRegenerationPathsForEffect(effect) {
  const derivedPaths = Array.isArray(effect.derived_native_regeneration_paths)
    ? effect.derived_native_regeneration_paths
    : [];
  const paths = derivedPaths.length
    ? derivedPaths
    : effect.requires_native_regeneration
      ? [effect.target_artifact]
      : [];
  return Array.from(new Set(paths.map(artifactPathKey).filter(Boolean)));
}

function statusFromEffects(effects, itemCount) {
  if (!effects.length) return "pending_review";
  if (effects.some((effect) => effect.requires_followup)) return "blocked";
  if (effects.some((effect) => effect.requires_native_regeneration)) return "partial_review_applied";
  if (effects.length < itemCount) return "partial_review_applied";
  return "final_ready";
}

const REVIEW_HANDOFF_PLUGINS = new Set([
  "check-entries",
  "client-file-preparation",
  "journal-sampling",
  "journal-bank-reconciliation",
  "deep-research-validator",
  "prompt-optimizer",
  "report-builder",
  "concordato-plan-review",
]);

function reviewHandoffOutputRecord() {
  return {
    path: "review_handoff.md",
    kind: "md",
    status: "written",
    required_text: [
      "Review Handoff",
      "review_payload.json",
      "ui_decisions.json",
      "applied_decisions.json",
      "final_artifacts.json",
    ],
    qa_checks: ["nonempty_text", "required_text"],
  };
}

function ensureReviewHandoffCard(inputArgs, outputDir) {
  const reviewPayload = isPlainObject(inputArgs.review_payload) ? inputArgs.review_payload : {};
  const pluginName = shortString(reviewPayload.plugin);
  if (!REVIEW_HANDOFF_PLUGINS.has(pluginName) || !outputDir) return null;

  const handoffPath = path.join(outputDir, "review_handoff.md");
  fs.mkdirSync(outputDir, { recursive: true });
  if (!fs.existsSync(handoffPath)) {
    const displayName = PLUGIN_MANIFEST.name || pluginName || "Review";
    const text = [
      `# ${displayName} Review Handoff`,
      "",
      "- Review payload: `review_payload.json`",
      "- Run intake: `run_intake.json`",
      "- Pending decisions: `ui_decisions.json`",
      "- Applied decisions: `applied_decisions.json`",
      "- Final artifacts: `final_artifacts.json`",
      "",
      "## Review In Codex",
      `1. Validate the payload with \\`${TOOL_NAMES.validateReview}\\`.`,
      `2. Render the review workbench with \\`${TOOL_NAMES.renderReview}\\`.`,
      `3. Save reviewer actions with \\`${TOOL_NAMES.saveDecisions}\\`.`,
      `4. Apply reviewer actions with \\`${TOOL_NAMES.applyDecisions}\\`.`,
    ].join("\\n");
    fs.writeFileSync(handoffPath, `${text}\\n`, "utf8");
  }
  return reviewHandoffOutputRecord();
}

function finalArtifactsWithApplication(
  inputArgs,
  appliedDecisions,
  finalArtifactsPath,
  revisionOutputs = [],
  targetOutputs = [],
  backupOutputs = [],
  nativeRegenerationOutputs = [],
) {
  const reviewPayload = appliedDecisions.review_payload;
  const current = currentFinalArtifactsForApplication(inputArgs, finalArtifactsPath);
  const outputDir = resolveRunOutputDir(inputArgs);
  const outputs = Array.isArray(current.outputs) ? [...current.outputs] : [];
  function upsertOutput(record) {
    const existingIndex = outputs.findIndex((output) => output?.path === record.path);
    if (existingIndex >= 0) outputs[existingIndex] = { ...outputs[existingIndex], ...record };
    else outputs.push(record);
  }
  const handoffOutput = ensureReviewHandoffCard(inputArgs, outputDir);
  if (handoffOutput) upsertOutput(handoffOutput);
  upsertOutput({ path: "ui_decisions.json", kind: "json", status: "written_reviewed" });
  upsertOutput({
    path: "applied_decisions.json",
    kind: "json",
    status: appliedDecisions.application_status,
  });
  for (const output of revisionOutputs) upsertOutput(output);
  for (const output of targetOutputs) upsertOutput(output);
  for (const output of backupOutputs) upsertOutput(output);
  for (const output of nativeRegenerationOutputs) upsertOutput(output);
  const blockers = effectsToBlockers(appliedDecisions.effects);
  return {
    schema_version: current.schema_version || reviewPayload.schema_version || "1.0",
    plugin: current.plugin || reviewPayload.plugin,
    workflow: current.workflow || reviewPayload.workflow,
    run_id: current.run_id || reviewPayload.run_id,
    outputs,
    caveats: Array.isArray(current.caveats) ? current.caveats : [],
    blockers,
    next_actions: nextActionsWithReviewApplication(current.next_actions, appliedDecisions, blockers),
    status: appliedDecisions.application_status,
    review_status: appliedDecisions.application_status,
    review_application: {
      applied_at: appliedDecisions.applied_at,
      application_status: appliedDecisions.application_status,
      decision_count: appliedDecisions.decision_count,
      item_count: appliedDecisions.item_count,
      blocker_count: appliedDecisions.blocker_count,
      revision_count: revisionOutputs.length,
      revision_paths: revisionOutputs.map((output) => output.path),
      target_update_count: targetOutputs.length,
      target_update_paths: targetOutputs.map((output) => output.path),
      structured_update_count: appliedDecisions.structured_update_count || 0,
      structured_update_paths: appliedDecisions.structured_update_paths || [],
      native_regeneration_count: appliedDecisions.native_regeneration_count || 0,
      native_regeneration_paths: appliedDecisions.native_regeneration_paths || [],
      original_backup_paths: backupOutputs.map((output) => output.path),
      applied_decisions_path: "applied_decisions.json",
    },
  };
}

function effectsToBlockers(effects) {
  return effects
    .filter((effect) => effect.requires_followup)
    .map((effect) => {
      const blocker = {
        item_id: effect.item_id,
        item_type: effect.item_type,
        title: effect.title,
        action: effect.action,
        status: effect.status,
        reviewer_note: effect.reviewer_note || null,
        requested_documents: Array.isArray(effect.requested_documents)
          ? effect.requested_documents
          : [],
      };
      if (isPlainObject(effect.followup_context) && Object.keys(effect.followup_context).length) {
        blocker.followup_context = effect.followup_context;
      }
      return blocker;
    });
}

function nextActionsWithReviewApplication(currentNextActions, appliedDecisions, blockers) {
  const nextActions = Array.isArray(currentNextActions) ? [...currentNextActions] : [];
  if (blockers.length) {
    nextActions.push("Resolve blocked review decisions before treating final artifacts as ready.");
  } else if (appliedDecisions.native_regeneration_count) {
    nextActions.push("Regenerate native DOCX/XLSX/PDF outputs before final handoff.");
  } else if (appliedDecisions.application_status === "final_ready") {
    nextActions.push("Use final_artifacts.json as the reviewed artifact gallery for handoff.");
  } else if (appliedDecisions.application_status === "partial_review_applied") {
    nextActions.push("Complete remaining review decisions before final handoff.");
  }
  return Array.from(new Set(nextActions));
}

function applyDecisionPayload(inputArgs) {
  const { uiDecisions, decisionOutputPath } = buildUiDecisions(inputArgs);
  const validationPayload = validateReviewPayload(inputArgs);
  const reviewPayload = validationPayload.review_payload;
  const itemById = new Map(reviewPayload.items.map((item) => [item.id, item]));
  const appliedAt = new Date().toISOString();
  const effects = uiDecisions.decisions.map((decision) =>
    buildApplicationEffect(decision, itemById.get(decision.item_id), appliedAt),
  );
  const outputDir = resolveRunOutputDir(inputArgs);
  const revisionOutputs = writeRevisionArtifacts(outputDir, effects);
  const textUpdates = writeDirectTextArtifactUpdates(outputDir, effects);
  const structuredUpdates = writeStructuredArtifactUpdates(outputDir, effects);
  const appliedOutputPath = resolveAppliedDecisionOutputPath(inputArgs);
  const finalArtifactsPath = resolveFinalArtifactsOutputPath(inputArgs);
  const currentFinalArtifacts = currentFinalArtifactsForApplication(inputArgs, finalArtifactsPath);
  const nativeRegenerationOutputs = [
    ...markNativeRegenerationPending(effects),
    ...markDerivedNativeRegenerationPending(outputDir, effects, currentFinalArtifacts),
  ];
  const targetOutputs = [...textUpdates.targetOutputs, ...structuredUpdates.targetOutputs];
  const backupOutputs = [...textUpdates.backupOutputs, ...structuredUpdates.backupOutputs];
  const structuredUpdatePaths = effects
    .filter((effect) => effect.artifact_update === "structured_artifact_updated")
    .map((effect) => effect.target_artifact);
  const nativeRegenerationPaths = Array.from(
    new Set(effects.flatMap((effect) => nativeRegenerationPathsForEffect(effect))),
  );
  const blockerCount = effects.filter((effect) => effect.requires_followup).length;
  const applicationStatus = statusFromEffects(effects, reviewPayload.items.length);
  const appliedDecisions = {
    schema_version: reviewPayload.schema_version,
    plugin: reviewPayload.plugin,
    workflow: reviewPayload.workflow,
    run_id: reviewPayload.run_id,
    applied_at: appliedAt,
    decision_source: uiDecisions.decision_source || "mcp_widget",
    review_payload: {
      path: uiDecisions.review_payload_path || "review_payload.json",
      item_count: reviewPayload.items.length,
      review_type: reviewPayload.review_type || null,
    },
    decisions: uiDecisions.decisions,
    effects,
    decision_count: uiDecisions.decision_count,
    item_count: reviewPayload.items.length,
    blocker_count: blockerCount,
    revision_count: revisionOutputs.length,
    revision_paths: revisionOutputs.map((output) => output.path),
    target_update_count: targetOutputs.length,
    target_update_paths: targetOutputs.map((output) => output.path),
    structured_update_count: structuredUpdatePaths.length,
    structured_update_paths: structuredUpdatePaths,
    native_regeneration_count: nativeRegenerationPaths.length,
    native_regeneration_paths: nativeRegenerationPaths,
    original_backup_paths: backupOutputs.map((output) => output.path),
    application_status: applicationStatus,
  };
  if (uiDecisions.reviewer) appliedDecisions.reviewer = uiDecisions.reviewer;

  const finalArtifacts = finalArtifactsWithApplication(
    inputArgs,
    appliedDecisions,
    finalArtifactsPath,
    revisionOutputs,
    targetOutputs,
    backupOutputs,
    nativeRegenerationOutputs,
  );
  let persisted = false;
  if (decisionOutputPath) {
    fs.mkdirSync(path.dirname(decisionOutputPath), { recursive: true });
    fs.writeFileSync(decisionOutputPath, `${JSON.stringify(uiDecisions, null, 2)}\\n`, "utf8");
  }
  if (appliedOutputPath) {
    fs.mkdirSync(path.dirname(appliedOutputPath), { recursive: true });
    fs.writeFileSync(appliedOutputPath, `${JSON.stringify(appliedDecisions, null, 2)}\\n`, "utf8");
    persisted = true;
  }
  if (finalArtifactsPath) {
    fs.mkdirSync(path.dirname(finalArtifactsPath), { recursive: true });
    fs.writeFileSync(finalArtifactsPath, `${JSON.stringify(finalArtifacts, null, 2)}\\n`, "utf8");
  }
  const workflowSpecificResult = applyWorkflowSpecificReviewApplication(
    outputDir,
    appliedOutputPath,
    finalArtifactsPath,
  );
  const responseAppliedDecisions =
    (isPlainObject(workflowSpecificResult?.applied_decisions)
      ? workflowSpecificResult.applied_decisions
      : null) ||
    readJsonFileIfPresent(appliedOutputPath) ||
    appliedDecisions;
  const responseFinalArtifacts =
    (isPlainObject(workflowSpecificResult?.final_artifacts)
      ? workflowSpecificResult.final_artifacts
      : null) ||
    readJsonFileIfPresent(finalArtifactsPath) ||
    finalArtifacts;
  const runIntakePath = appendReviewApplicationExecutionTrace(
    inputArgs,
    outputDir,
    responseAppliedDecisions,
    responseFinalArtifacts,
  );
  return {
    ok: true,
    validation_type: "__VALIDATION_TYPE___application",
    run_id: responseAppliedDecisions.run_id,
    decision_count: responseAppliedDecisions.decision_count,
    item_count: responseAppliedDecisions.item_count,
    blocker_count: responseAppliedDecisions.blocker_count,
    revision_count: responseAppliedDecisions.revision_count || revisionOutputs.length,
    target_update_count: responseAppliedDecisions.target_update_count || targetOutputs.length,
    structured_update_count: responseAppliedDecisions.structured_update_count || structuredUpdatePaths.length,
    native_regeneration_count: responseAppliedDecisions.native_regeneration_count || 0,
    native_regenerated_count: responseAppliedDecisions.native_regenerated_count || 0,
    application_status: responseAppliedDecisions.application_status || applicationStatus,
    persisted,
    ui_decisions_path: decisionOutputPath,
    applied_decisions_path: persisted ? appliedOutputPath : null,
    final_artifacts_path: finalArtifactsPath,
    run_intake_path: runIntakePath,
    message: persisted
      ? `Applied ${responseAppliedDecisions.decision_count} __DISPLAY_NAME__ decisions.`
      : "Validated applied decisions. No run_intake.output_dir was provided, so nothing was written.",
    applied_decisions: responseAppliedDecisions,
    final_artifacts: responseFinalArtifacts,
  };
}

__WORKFLOW_SPECIFIC_REVIEW_APPLICATION_HELPER__
"""


DEFAULT_WORKFLOW_REVIEW_APPLICATION_HELPER = """function applyWorkflowSpecificReviewApplication(
  _outputDir,
  _appliedOutputPath,
  _finalArtifactsPath,
) {
  return null;
}
"""


def native_regeneration_script_helper(display_name: str, target_path: str) -> str:
    return f"""function pythonExecutable() {{
  const candidates = [
    process.env.PYTHON,
    process.env.VIRTUAL_ENV ? path.join(process.env.VIRTUAL_ENV, "bin", "python") : "",
    path.resolve(PLUGIN_ROOT, "..", "..", ".venv", "bin", "python"),
    "python3",
    "python",
  ].filter(Boolean);
  for (const candidate of candidates) {{
    if (path.isAbsolute(candidate) && !fs.existsSync(candidate)) continue;
    return candidate;
  }}
  return "python3";
}}

function applyWorkflowSpecificReviewApplication(outputDir, appliedOutputPath, finalArtifactsPath) {{
  if (!outputDir || !appliedOutputPath || !finalArtifactsPath) return null;
  const currentApplied = readJsonFileIfPresent(appliedOutputPath);
  if (!currentApplied || !currentApplied.native_regeneration_count) return null;
  if (!hasWorkflowNativeRegenerationTarget(currentApplied)) return null;
  const scriptPath = path.join(PLUGIN_ROOT, "scripts", "apply_review_edits.py");
  const completed = spawnSync(
    pythonExecutable(),
    [
      scriptPath,
      "--output-dir",
      outputDir,
      "--applied-decisions",
      appliedOutputPath,
      "--final-artifacts",
      finalArtifactsPath,
    ],
    {{ cwd: PLUGIN_ROOT, encoding: "utf8" }},
  );
  if (completed.error) throw completed.error;
  if (completed.status !== 0) {{
    throw new Error(
      completed.stderr ||
        completed.stdout ||
        "{display_name} native regeneration failed.",
    );
  }}
  const output = completed.stdout.trim().split(/\\r?\\n/).filter(Boolean).pop();
  if (!output) return null;
  const parsed = JSON.parse(output);
  return isPlainObject(parsed) ? parsed : null;
}}

function hasWorkflowNativeRegenerationTarget(appliedDecisions) {{
  if (!isPlainObject(appliedDecisions)) return false;
  const effects = Array.isArray(appliedDecisions.effects) ? appliedDecisions.effects : [];
  return effects.some((effect) => {{
    if (!isPlainObject(effect)) return false;
    if (effect.action !== "edit") return false;
    if (!effect.requires_native_regeneration) return false;
    return nativeRegenerationPathsForEffect(effect).includes("{target_path}");
  }});
}}
"""


REPORT_BUILDER_REVIEW_APPLICATION_HELPER = """function pythonExecutable() {
  const candidates = [
    process.env.PYTHON,
    process.env.VIRTUAL_ENV ? path.join(process.env.VIRTUAL_ENV, "bin", "python") : "",
    path.resolve(PLUGIN_ROOT, "..", "..", ".venv", "bin", "python"),
    "python3",
    "python",
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (path.isAbsolute(candidate) && !fs.existsSync(candidate)) continue;
    return candidate;
  }
  return "python3";
}

function applyWorkflowSpecificReviewApplication(outputDir, appliedOutputPath, finalArtifactsPath) {
  if (!outputDir || !appliedOutputPath || !finalArtifactsPath) return null;
  const currentApplied = readJsonFileIfPresent(appliedOutputPath);
  if (!currentApplied || !currentApplied.native_regeneration_count) return null;
  if (!hasReportBuilderNativeRegenerationTarget(currentApplied)) return null;
  const scriptPath = path.join(PLUGIN_ROOT, "scripts", "apply_review_edits.py");
  const completed = spawnSync(
    pythonExecutable(),
    [
      scriptPath,
      "--output-dir",
      outputDir,
      "--applied-decisions",
      appliedOutputPath,
      "--final-artifacts",
      finalArtifactsPath,
    ],
    { cwd: PLUGIN_ROOT, encoding: "utf8" },
  );
  if (completed.error) throw completed.error;
  if (completed.status !== 0) {
    throw new Error(
      completed.stderr ||
        completed.stdout ||
        "Report Builder native regeneration failed.",
    );
  }
  const output = completed.stdout.trim().split(/\\r?\\n/).filter(Boolean).pop();
  if (!output) return null;
  const parsed = JSON.parse(output);
  return isPlainObject(parsed) ? parsed : null;
}

function hasReportBuilderNativeRegenerationTarget(appliedDecisions) {
  if (!isPlainObject(appliedDecisions)) return false;
  const effects = Array.isArray(appliedDecisions.effects) ? appliedDecisions.effects : [];
  return effects.some((effect) => {
    if (!isPlainObject(effect)) return false;
    if (effect.action !== "edit") return false;
    if (effect.artifact_update !== "native_regeneration_pending") return false;
    if (shortString(effect.target_artifact) !== "report.docx") return false;
    if (shortString(effect.edit_value) === "") return false;
    return /^sections\\.[^.]+\\.(codex_comment|assigned_table)$/.test(shortString(effect.target_path));
  });
}
"""


DEEP_RESEARCH_REVIEW_APPLICATION_HELPER = """function pythonExecutable() {
  const candidates = [
    process.env.PYTHON,
    process.env.VIRTUAL_ENV ? path.join(process.env.VIRTUAL_ENV, "bin", "python") : "",
    path.resolve(PLUGIN_ROOT, "..", "..", ".venv", "bin", "python"),
    "python3",
    "python",
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (path.isAbsolute(candidate) && !fs.existsSync(candidate)) continue;
    return candidate;
  }
  return "python3";
}

function applyWorkflowSpecificReviewApplication(outputDir, appliedOutputPath, finalArtifactsPath) {
  if (!outputDir || !appliedOutputPath || !finalArtifactsPath) return null;
  const currentApplied = readJsonFileIfPresent(appliedOutputPath);
  if (!currentApplied || !currentApplied.structured_update_count) return null;
  if (!hasDeepResearchClaimFixTarget(currentApplied)) return null;
  const scriptPath = path.join(PLUGIN_ROOT, "scripts", "apply_review_edits.py");
  const completed = spawnSync(
    pythonExecutable(),
    [
      scriptPath,
      "--output-dir",
      outputDir,
      "--applied-decisions",
      appliedOutputPath,
      "--final-artifacts",
      finalArtifactsPath,
    ],
    { cwd: PLUGIN_ROOT, encoding: "utf8" },
  );
  if (completed.error) throw completed.error;
  if (completed.status !== 0) {
    throw new Error(
      completed.stderr ||
        completed.stdout ||
        "Deep Research downstream artifact refresh failed.",
    );
  }
  const output = completed.stdout.trim().split(/\\r?\\n/).filter(Boolean).pop();
  if (!output) return null;
  const parsed = JSON.parse(output);
  return isPlainObject(parsed) ? parsed : null;
}

function hasDeepResearchClaimFixTarget(appliedDecisions) {
  if (!isPlainObject(appliedDecisions)) return false;
  const effects = Array.isArray(appliedDecisions.effects) ? appliedDecisions.effects : [];
  return effects.some((effect) => {
    if (!isPlainObject(effect)) return false;
    if (effect.action !== "edit") return false;
    if (effect.artifact_update !== "structured_artifact_updated") return false;
    if (shortString(effect.target_artifact) !== "claims_review.json") return false;
    if (shortString(effect.target_field) !== "proposed_fix") return false;
    return shortString(effect.edit_value) !== "";
  });
}
"""


PROMPT_OPTIMIZER_REVIEW_APPLICATION_HELPER = """function pythonExecutable() {
  const candidates = [
    process.env.PYTHON,
    process.env.VIRTUAL_ENV ? path.join(process.env.VIRTUAL_ENV, "bin", "python") : "",
    path.resolve(PLUGIN_ROOT, "..", "..", ".venv", "bin", "python"),
    "python3",
    "python",
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (path.isAbsolute(candidate) && !fs.existsSync(candidate)) continue;
    return candidate;
  }
  return "python3";
}

function applyWorkflowSpecificReviewApplication(outputDir, appliedOutputPath, finalArtifactsPath) {
  if (!outputDir || !appliedOutputPath || !finalArtifactsPath) return null;
  const currentApplied = readJsonFileIfPresent(appliedOutputPath);
  if (!currentApplied || !currentApplied.target_update_count) return null;
  if (!hasPromptOptimizerPromptEditTarget(currentApplied)) return null;
  const scriptPath = path.join(PLUGIN_ROOT, "scripts", "apply_review_edits.py");
  const completed = spawnSync(
    pythonExecutable(),
    [
      scriptPath,
      "--output-dir",
      outputDir,
      "--applied-decisions",
      appliedOutputPath,
      "--final-artifacts",
      finalArtifactsPath,
    ],
    { cwd: PLUGIN_ROOT, encoding: "utf8" },
  );
  if (completed.error) throw completed.error;
  if (completed.status !== 0) {
    throw new Error(
      completed.stderr ||
        completed.stdout ||
        "Prompt Optimizer downstream artifact refresh failed.",
    );
  }
  const output = completed.stdout.trim().split(/\\r?\\n/).filter(Boolean).pop();
  if (!output) return null;
  const parsed = JSON.parse(output);
  return isPlainObject(parsed) ? parsed : null;
}

function hasPromptOptimizerPromptEditTarget(appliedDecisions) {
  if (!isPlainObject(appliedDecisions)) return false;
  const effects = Array.isArray(appliedDecisions.effects) ? appliedDecisions.effects : [];
  return effects.some((effect) => {
    if (!isPlainObject(effect)) return false;
    if (effect.action !== "edit") return false;
    if (effect.artifact_update !== "target_artifact_updated") return false;
    if (shortString(effect.target_artifact) !== "optimized_prompt.md") return false;
    return shortString(effect.edit_value) !== "";
  });
}
"""


def workflow_review_application_helper(target: Target) -> str:
    if target.plugin == "check-entries":
        return native_regeneration_script_helper(
            target.display_name,
            "check_results.xlsx",
        )
    if target.plugin == "deep-research-validator":
        return DEEP_RESEARCH_REVIEW_APPLICATION_HELPER
    if target.plugin == "journal-bank-reconciliation":
        return native_regeneration_script_helper(
            target.display_name,
            "journal_bank_reconciliation.xlsx",
        )
    if target.plugin == "concordato-plan-review":
        return native_regeneration_script_helper(
            target.display_name,
            "concordato_review_summary.docx",
        )
    if target.plugin == "report-builder":
        return REPORT_BUILDER_REVIEW_APPLICATION_HELPER
    if target.plugin == "prompt-optimizer":
        return PROMPT_OPTIMIZER_REVIEW_APPLICATION_HELPER
    return DEFAULT_WORKFLOW_REVIEW_APPLICATION_HELPER


def patch_tool_names(text: str, target: Target) -> str:
    if "applyDecisions:" in text:
        return text
    pattern = r'(saveDecisions: "[^"]+",\n)(\};)'
    updated, count = re.subn(
        pattern,
        rf'\1  applyDecisions: "{target.apply_tool}",\n\2',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("Could not patch TOOL_NAMES applyDecisions")
    return updated


def patch_decision_policy(text: str) -> str:
    if "apply_tool: TOOL_NAMES.applyDecisions" in text:
        return text
    return text.replace(
        "      save_tool: TOOL_NAMES.saveDecisions,\n",
        "      save_tool: TOOL_NAMES.saveDecisions,\n      apply_tool: TOOL_NAMES.applyDecisions,\n",
        1,
    )


def patch_tool_definition(text: str, target: Target) -> str:
    if "name: TOOL_NAMES.applyDecisions" in text:
        return text
    apply_tool_object = f"""    {{
      name: TOOL_NAMES.applyDecisions,
      title: "Apply {target.display_name} review decisions",
      description:
        "Validate {target.display_name} review decisions, write applied_decisions.json, and update final_artifacts.json status when run_intake.output_dir is available.",
      inputSchema: decisionInputSchema,
      annotations: {{
        readOnlyHint: false,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      }},
    }},
"""
    marker = "  ];\n}\n\nfunction resources"
    index = text.find(marker)
    if index == -1:
        raise RuntimeError("Could not find toolDefinitions end")
    return f"{text[:index]}{apply_tool_object}{text[index:]}"


def patch_helpers(text: str, target: Target) -> str:
    helper_block = APPLY_HELPERS.replace(
        "__VALIDATION_TYPE__", target.validation_type
    ).replace("__DISPLAY_NAME__", target.display_name)
    helper_block = helper_block.replace(
        "__WORKFLOW_SPECIFIC_REVIEW_APPLICATION_HELPER__",
        workflow_review_application_helper(target),
    )
    if "function applyDecisionPayload" in text:
        pattern = (
            r"function resolveRunOutputDir\(inputArgs\) "
            r"\{[\s\S]*?\n\}\n\nfunction callTool\(name, args = \{\}\) \{"
        )
        replacement = f"{helper_block}function callTool(name, args = {{}}) {{"
        updated, count = re.subn(pattern, lambda _match: replacement, text, count=1)
        if count != 1:
            raise RuntimeError("Could not replace existing apply helpers")
        return updated
    marker = "function callTool(name, args = {}) {"
    index = text.find(marker)
    if index == -1:
        raise RuntimeError("Could not find callTool")
    return f"{text[:index]}{helper_block}{text[index:]}"


def patch_call_tool(text: str) -> str:
    call_tool_start = text.find("function callTool(name, args = {}) {")
    if call_tool_start == -1:
        raise RuntimeError("Could not find callTool function")
    suffix = text[call_tool_start:]
    call_tool_end = suffix.find("\nfunction toolResult")
    if call_tool_end == -1:
        raise RuntimeError("Could not find callTool end")
    if "return applyDecisionPayload(args);" in suffix[:call_tool_end]:
        return text
    marker = "  throw new Error(`unknown"
    local = suffix[:call_tool_end]
    marker_index = local.find(marker)
    if marker_index == -1:
        raise RuntimeError("Could not find unknown tool throw")
    patched_suffix = suffix.replace(
        marker,
        """  if (name === TOOL_NAMES.applyDecisions) {
    return applyDecisionPayload(args);
  }
  throw new Error(`unknown""",
        1,
    )
    return text[:call_tool_start] + patched_suffix


def patch_instructions(text: str, target: Target) -> str:
    pattern = r'instructions:\n\s+"[^"]*",'
    replacement = f'instructions:\n          "{target.instruction}",'
    updated, count = re.subn(pattern, replacement, text, count=1)
    return updated if count else text


def patch_workflow_specific_imports(text: str, target: Target) -> str:
    if target.plugin not in {
        "check-entries",
        "deep-research-validator",
        "journal-bank-reconciliation",
        "prompt-optimizer",
        "report-builder",
    }:
        return text
    import_line = 'const { spawnSync } = require("node:child_process");'
    if import_line in text:
        return text
    marker = 'const readline = require("node:readline");\n'
    if marker not in text:
        raise RuntimeError("Could not find readline import")
    return text.replace(marker, f"{marker}{import_line}\n", 1)


def patch_server(text: str, target: Target) -> str:
    updated = patch_workflow_specific_imports(text, target)
    updated = patch_tool_names(updated, target)
    updated = patch_decision_policy(updated)
    updated = patch_tool_definition(updated, target)
    updated = patch_helpers(updated, target)
    updated = patch_call_tool(updated)
    return patch_instructions(updated, target)


def main() -> None:
    for target in TARGETS:
        path = target.server_path
        original = path.read_text(encoding="utf-8")
        updated = patch_server(original, target)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            LOGGER.info("updated %s", path.relative_to(ROOT))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
