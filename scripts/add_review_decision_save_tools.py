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
    save_tool: str
    display_name: str
    validation_type: str
    validate_tool: str
    render_tool: str

    @property
    def server_path(self) -> Path:
        return ROOT / "plugins" / self.plugin / "mcp" / "server.cjs"

    @property
    def instruction(self) -> str:
        if self.plugin == "prompt-optimizer":
            return (
                "Use validate_prompt_optimizer_review before render_prompt_optimizer_review. "
                "Prefer the MCP widget for final Prompt Optimizer package review; "
                "use save_prompt_optimizer_decisions to persist final package review "
                "actions to ui_decisions.json; use native Plan-mode choices or chat "
                "for simple pre-draft intake decisions."
            )
        return (
            f"Use {self.validate_tool} before {self.render_tool}. Prefer the MCP widget "
            f"for {self.display_name} review handoff; use {self.save_tool} to persist "
            "reviewer actions to ui_decisions.json when decisions are collected; fall "
            "back to Markdown/static review only when MCP is unavailable."
        )


TARGETS = [
    Target(
        "deep-research-validator",
        "save_deep_research_decisions",
        "Deep Research",
        "deep_research",
        "validate_deep_research_review",
        "render_deep_research_review",
    ),
    Target(
        "client-intake",
        "save_client_intake_decisions",
        "Client Intake",
        "client_intake",
        "validate_client_intake_review",
        "render_client_intake_review",
    ),
    Target(
        "audit-reconciliation",
        "save_audit_reconciliation_decisions",
        "Audit Reconciliation",
        "audit_reconciliation",
        "validate_audit_reconciliation_review",
        "render_audit_reconciliation_review",
    ),
    Target(
        "journal-sampling",
        "save_journal_sampling_decisions",
        "Journal Sampling",
        "journal_sampling",
        "validate_journal_sampling_review",
        "render_journal_sampling_review",
    ),
    Target(
        "journal-bank-reconciliation",
        "save_journal_bank_decisions",
        "Journal-Bank",
        "journal_bank",
        "validate_journal_bank_review",
        "render_journal_bank_review",
    ),
    Target(
        "report-builder",
        "save_report_builder_decisions",
        "Build Report",
        "report_builder",
        "validate_report_builder_review",
        "render_report_builder_review",
    ),
    Target(
        "prompt-optimizer",
        "save_prompt_optimizer_decisions",
        "Prompt Optimizer",
        "prompt_optimizer",
        "validate_prompt_optimizer_review",
        "render_prompt_optimizer_review",
    ),
    Target(
        "concordato-plan-review",
        "save_concordato_plan_decisions",
        "Concordato Plan Review",
        "concordato_plan",
        "validate_concordato_plan_review",
        "render_concordato_plan_review",
    ),
    Target(
        "variance-analysis",
        "save_variance_analysis_decisions",
        "Variance Analysis",
        "variance_analysis",
        "validate_variance_analysis_review",
        "render_variance_analysis_review",
    ),
    Target(
        "period-comparison",
        "save_period_comparison_decisions",
        "Period Comparison",
        "period_comparison",
        "validate_period_comparison_review",
        "render_period_comparison_review",
    ),
    Target(
        "mix-contribution-analysis",
        "save_mix_contribution_decisions",
        "Mix Contribution",
        "mix_contribution",
        "validate_mix_contribution_review",
        "render_mix_contribution_review",
    ),
    Target(
        "scatter-bubble-analysis",
        "save_scatter_bubble_decisions",
        "Scatter Bubble",
        "scatter_bubble",
        "validate_scatter_bubble_review",
        "render_scatter_bubble_review",
    ),
    Target(
        "distribution-analysis",
        "save_distribution_decisions",
        "Distribution",
        "distribution",
        "validate_distribution_review",
        "render_distribution_review",
    ),
    Target(
        "set-overlap-analysis",
        "save_set_overlap_decisions",
        "Set Overlap",
        "set_overlap",
        "validate_set_overlap_review",
        "render_set_overlap_review",
    ),
]


ACTION_STATUS_BLOCK = """const ACTION_STATUSES = {
  accept: "accepted",
  reject: "rejected",
  edit: "edited",
  mark_unclear: "needs_evidence",
  request_more_documents: "needs_evidence",
  skip: "skipped",
};
const MAX_DECISION_TEXT_LENGTH = 10_000;
"""


BOUNDED_STRING_BLOCK = """function boundedOptionalString(value, fieldPath) {
  if (value == null) return "";
  if (typeof value !== "string") {
    throw new Error(`${fieldPath} must be a string when provided`);
  }
  if (value.length > MAX_DECISION_TEXT_LENGTH) {
    throw new Error(`${fieldPath} exceeds ${MAX_DECISION_TEXT_LENGTH} characters`);
  }
  return value.trim();
}

"""


DECISION_SCHEMA_BLOCK = """  const decisionSchema = objectSchema(
    {
      item_id: { type: "string", description: "Review item id from review_payload.items[].id." },
      action: { type: "string", enum: Array.from(ALLOWED_ACTIONS) },
      reviewer_note: { type: "string", description: "Optional reviewer note." },
      edit_value: { type: "string", description: "Required replacement text or value when action is edit." },
      requested_documents: {
        type: "array",
        items: { type: "string" },
        description: "Optional document requests when action is request_more_documents.",
      },
    },
    ["item_id", "action"],
  );
  const decisionInputSchema = objectSchema(
    {
      run_intake: { type: "object", description: "Optional run_intake.json object with output_dir for persistence." },
      review_payload: reviewPayload,
      ui_decisions: { type: "object", description: "Optional current ui_decisions.json object." },
      decisions: { type: "array", items: decisionSchema },
      decision_source: { type: "string", description: "Decision source label. Defaults to mcp_widget." },
      reviewer: { type: "string", description: "Optional reviewer name or role." },
    },
    ["review_payload", "decisions"],
  );
"""


HELPER_TEMPLATE = """function resolveDecisionOutputPath(inputArgs) {
  const runIntake = isPlainObject(inputArgs.run_intake) ? inputArgs.run_intake : null;
  const outputDir = typeof runIntake?.output_dir === "string" ? runIntake.output_dir.trim() : "";
  if (!outputDir) return null;
  return path.join(path.resolve(outputDir), "ui_decisions.json");
}

function normalizeRequestedDocuments(value, fieldPath) {
  if (value == null) return [];
  if (!Array.isArray(value)) throw new Error(`${fieldPath} must be an array when provided`);
  return value.map((entry, index) => {
    const documentName = boundedOptionalString(entry, `${fieldPath}[${index}]`);
    if (!documentName) throw new Error(`${fieldPath}[${index}] must be a non-empty string`);
    return documentName;
  });
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

function normalizeDecision(decision, itemById, seenIds, decidedAt, index) {
  // Decision persistence is an audit contract: ids, actions, and edit payloads are mechanically verifiable.
  if (!isPlainObject(decision)) throw new Error(`decisions[${index}] must be an object`);
  const itemId = boundedOptionalString(decision.item_id ?? decision.id, `decisions[${index}].item_id`);
  if (!itemId) throw new Error(`decisions[${index}].item_id must be a non-empty string`);
  if (seenIds.has(itemId)) throw new Error(`decisions contains duplicate item_id: ${itemId}`);
  seenIds.add(itemId);
  const item = itemById.get(itemId);
  if (!item) throw new Error(`decisions[${index}].item_id is not in review_payload.items: ${itemId}`);
  const action = boundedOptionalString(decision.action, `decisions[${index}].action`);
  if (!ALLOWED_ACTIONS.has(action)) throw new Error(`decisions[${index}].action is not supported: ${action}`);
  if (!item.allowed_actions.includes(action)) {
    throw new Error(`decisions[${index}].action is not allowed for item ${itemId}: ${action}`);
  }
  const reviewerNote = boundedOptionalString(
    decision.reviewer_note ?? decision.note,
    `decisions[${index}].reviewer_note`,
  );
  const editValue = boundedOptionalString(
    decision.edit_value ?? decision.user_text,
    `decisions[${index}].edit_value`,
  );
  if (action === "edit" && !editValue) {
    throw new Error(`decisions[${index}].edit_value is required when action is edit`);
  }
  const explicitRequestedDocuments = normalizeRequestedDocuments(
    decision.requested_documents,
    `decisions[${index}].requested_documents`,
  );
  // Missing-document requests copy only explicit review metadata; no semantic evidence inference happens here.
  const requestedDocuments = requestedDocumentsFromReviewContext(
    { action, requested_documents: explicitRequestedDocuments },
    item,
    isPlainObject(item.data) ? item.data : {},
  );
  // Follow-up context copies only explicit item/evidence metadata to make blocker queues actionable.
  const followupContext = followupContextFromReviewContext(
    { action },
    item,
    isPlainObject(item.data) ? item.data : {},
  );
  const normalized = {
    item_id: itemId,
    item_type: item.item_type,
    title: item.title,
    action,
    status: ACTION_STATUSES[action],
    decided_at: decidedAt,
  };
  if (reviewerNote) normalized.reviewer_note = reviewerNote;
  if (editValue) normalized.edit_value = editValue;
  if (requestedDocuments.length) normalized.requested_documents = requestedDocuments;
  if (Object.keys(followupContext).length) normalized.followup_context = followupContext;
  return normalized;
}

function buildUiDecisions(inputArgs) {
  const payload = validateReviewPayload(inputArgs);
  const reviewPayload = payload.review_payload;
  const runIntake = payload.run_intake;
  if (runIntake?.run_id != null && runIntake.run_id !== reviewPayload.run_id) {
    throw new Error("run_intake.run_id must match review_payload.run_id");
  }
  if (!Array.isArray(inputArgs.decisions)) throw new Error("decisions must be an array");
  if (inputArgs.decisions.length > reviewPayload.items.length) {
    throw new Error("decisions cannot exceed review_payload.items.length");
  }
  const decidedAt = new Date().toISOString();
  const itemById = new Map(reviewPayload.items.map((item) => [item.id, item]));
  const seenIds = new Set();
  const decisions = inputArgs.decisions.map((decision, index) =>
    normalizeDecision(decision, itemById, seenIds, decidedAt, index),
  );
  const decisionSource =
    boundedOptionalString(inputArgs.decision_source, "decision_source") || "mcp_widget";
  const reviewer = boundedOptionalString(inputArgs.reviewer, "reviewer");
  const currentUiDecisions = isPlainObject(inputArgs.ui_decisions) ? inputArgs.ui_decisions : null;
  const reviewPayloadPath =
    typeof currentUiDecisions?.review_payload_path === "string"
      ? path.basename(currentUiDecisions.review_payload_path)
      : "review_payload.json";
  const status =
    decisions.length === 0
      ? "pending_review"
      : decisions.length === reviewPayload.items.length
        ? "reviewed"
        : "partial_review";
  const uiDecisions = {
    schema_version: reviewPayload.schema_version,
    plugin: reviewPayload.plugin,
    workflow: reviewPayload.workflow,
    run_id: reviewPayload.run_id,
    decided_at: decisions.length ? decidedAt : null,
    decision_source: decisionSource,
    review_payload_path: reviewPayloadPath,
    decisions,
    decision_count: decisions.length,
    item_count: reviewPayload.items.length,
    status,
  };
  if (reviewer) uiDecisions.reviewer = reviewer;
  return {
    uiDecisions,
    decisionOutputPath: resolveDecisionOutputPath(inputArgs),
  };
}

function saveDecisionPayload(inputArgs) {
  const { uiDecisions, decisionOutputPath } = buildUiDecisions(inputArgs);
  let persisted = false;
  if (decisionOutputPath) {
    fs.mkdirSync(path.dirname(decisionOutputPath), { recursive: true });
    fs.writeFileSync(decisionOutputPath, `${JSON.stringify(uiDecisions, null, 2)}\\n`, "utf8");
    persisted = true;
  }
  return {
    ok: true,
    validation_type: "__VALIDATION_TYPE___decisions",
    run_id: uiDecisions.run_id,
    decision_count: uiDecisions.decision_count,
    item_count: uiDecisions.item_count,
    status: uiDecisions.status,
    persisted,
    ui_decisions_path: persisted ? decisionOutputPath : null,
    message: persisted
      ? `Saved ${uiDecisions.decision_count} __DISPLAY_NAME__ decisions.`
      : "Validated decisions. No run_intake.output_dir was provided, so nothing was written.",
    ui_decisions: uiDecisions,
  };
}

"""


def replace_once(text: str, old: str, new: str, description: str) -> str:
    if old not in text:
        raise RuntimeError(f"Could not find {description}")
    return text.replace(old, new, 1)


def patch_tool_names(text: str, target: Target) -> str:
    if "saveDecisions:" in text:
        return text
    pattern = (
        r'(const TOOL_NAMES = \{\n\s+validateReview: "[^"]+",\n'
        r'\s+renderReview: "[^"]+",\n)(\};)'
    )
    replacement = rf'\1  saveDecisions: "{target.save_tool}",\n\2'
    updated, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise RuntimeError("Could not patch TOOL_NAMES")
    return updated


def patch_constants(text: str) -> str:
    if "const ACTION_STATUSES" in text:
        return text
    return replace_once(
        text,
        "]);\nconst ITEM_TYPES = new Set([",
        f"]);\n{ACTION_STATUS_BLOCK}const ITEM_TYPES = new Set([",
        "ALLOWED_ACTIONS close",
    )


def patch_bounded_string(text: str) -> str:
    if "function boundedOptionalString" in text:
        return text
    return replace_once(
        text,
        "function validateItem(item, index) {",
        f"{BOUNDED_STRING_BLOCK}function validateItem(item, index) {{",
        "validateItem start",
    )


def patch_decision_schemas(text: str) -> str:
    if "const decisionSchema" in text:
        return text
    return replace_once(
        text,
        "  return [\n",
        f"{DECISION_SCHEMA_BLOCK}  return [\n",
        "toolDefinitions return",
    )


def patch_save_tool_definition(text: str, target: Target) -> str:
    if "name: TOOL_NAMES.saveDecisions" in text:
        return text
    save_tool_object = f"""    {{
      name: TOOL_NAMES.saveDecisions,
      title: "Save {target.display_name} review decisions",
      description:
        "Validate {target.display_name} review decisions and persist them to ui_decisions.json when run_intake.output_dir is available.",
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
    return f"{text[:index]}{save_tool_object}{text[index:]}"


def patch_decision_policy(text: str) -> str:
    if "decision_policy:" in text:
        return text
    return replace_once(
        text,
        "  };\n  if (payloadBytes(payload) > MAX_PAYLOAD_BYTES) {",
        """    decision_policy: {
      save_tool: TOOL_NAMES.saveDecisions,
      can_persist: Boolean(resolveDecisionOutputPath(inputArgs)),
      fallback: "copy_json",
    },
  };
  if (payloadBytes(payload) > MAX_PAYLOAD_BYTES) {""",
        "validateReviewPayload payload close",
    )


def patch_helpers(text: str, target: Target) -> str:
    if "function resolveDecisionOutputPath" in text:
        return text
    helper_block = HELPER_TEMPLATE.replace(
        "__VALIDATION_TYPE__", target.validation_type
    ).replace("__DISPLAY_NAME__", target.display_name)
    return replace_once(
        text,
        "function callTool(name, args = {}) {",
        f"{helper_block}function callTool(name, args = {{}}) {{",
        "callTool start",
    )


def patch_call_tool(text: str) -> str:
    call_tool_start = "function callTool(name, args = {}) {"
    call_tool_index = text.find(call_tool_start)
    if call_tool_index == -1:
        raise RuntimeError("Could not find callTool function")
    prefix = re.sub(
        r"\n\s+if \(name === TOOL_NAMES\.saveDecisions\) \{\n\s+return saveDecisionPayload\(args\);\n\s+\}\n",
        "\n",
        text[:call_tool_index],
    )
    suffix = text[call_tool_index:]
    call_tool_end = suffix.find("\nfunction toolResult")
    if call_tool_end == -1:
        raise RuntimeError("Could not find callTool end")
    if "return saveDecisionPayload(args);" in suffix[:call_tool_end]:
        return prefix + suffix
    marker = "  throw new Error(`unknown"
    if marker not in suffix[:call_tool_end]:
        raise RuntimeError("Could not find unknown tool throw")
    patched_suffix = suffix.replace(
        marker,
        """  if (name === TOOL_NAMES.saveDecisions) {
    return saveDecisionPayload(args);
  }
  throw new Error(`unknown""",
        1,
    )
    return prefix + patched_suffix


def patch_instructions(text: str, target: Target) -> str:
    pattern = r'instructions:\n\s+"[^"]*",'
    replacement = f'instructions:\n          "{target.instruction}",'
    updated, count = re.subn(pattern, replacement, text, count=1)
    return updated if count else text


def patch_server(text: str, target: Target) -> str:
    updated = patch_tool_names(text, target)
    updated = patch_constants(updated)
    updated = patch_bounded_string(updated)
    updated = patch_decision_schemas(updated)
    updated = patch_save_tool_definition(updated, target)
    updated = patch_decision_policy(updated)
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
