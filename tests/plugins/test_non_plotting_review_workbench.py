from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import generate_non_plotting_review_widgets as widget_generator

ROOT = Path(__file__).resolve().parents[2]


def _bundled_node_or_skip() -> str:
    node = shutil.which("node")
    if node is not None:
        return node
    candidates = sorted(
        (Path.home() / ".cache" / "codex-runtimes").glob("*/dependencies/node/bin/node")
    )
    if not candidates:
        pytest.skip("Node.js is required to exercise review widget behavior.")
    return candidates[-1].as_posix()


WORKBENCH_WIDGETS = [
    (
        "check-entries",
        "assets/check-entries-review-widget.html",
        "Check Entries Review",
    ),
    (
        "deep-research-validator",
        "assets/deep-research-review-widget.html",
        "Deep Research Review",
    ),
    (
        "client-file-preparation",
        "assets/client-file-preparation-review-widget.html",
        "New Client · File Preparation",
    ),
    (
        "new-client",
        "assets/new-client-review-widget.html",
        "New Client Review",
    ),
    (
        "audit-reconciliation",
        "assets/audit-reconciliation-review-widget.html",
        "Audit Reconciliation Review",
    ),
    (
        "journal-sampling",
        "assets/journal-sampling-review-widget.html",
        "Journal Sampling Review",
    ),
    (
        "journal-bank-reconciliation",
        "assets/journal-bank-review-widget.html",
        "Journal-Bank Review",
    ),
    (
        "report-builder",
        "assets/report-builder-review-widget.html",
        "Build Report Review",
    ),
    (
        "prompt-optimizer",
        "assets/prompt-optimizer-review-widget.html",
        "Prompt Optimizer Review",
    ),
    (
        "concordato-plan-review",
        "assets/concordato-plan-review-widget.html",
        "Concordato Plan Review",
    ),
]

REVIEW_SAVE_TOOLS = [
    (
        "check-entries",
        "save_check_entries_decisions",
        "apply_check_entries_decisions",
        "supported_entry",
    ),
    (
        "deep-research-validator",
        "save_deep_research_decisions",
        "apply_deep_research_decisions",
        "supported_claim",
    ),
    (
        "client-file-preparation",
        "save_client_file_preparation_decisions",
        "apply_client_file_preparation_decisions",
        "document_inventory",
    ),
    (
        "audit-reconciliation",
        "save_audit_reconciliation_decisions",
        "apply_audit_reconciliation_decisions",
        "closure_evidence_review",
    ),
    (
        "journal-sampling",
        "save_journal_sampling_decisions",
        "apply_journal_sampling_decisions",
        "sampled_entry",
    ),
    (
        "journal-bank-reconciliation",
        "save_journal_bank_decisions",
        "apply_journal_bank_decisions",
        "matched_pair",
    ),
    (
        "report-builder",
        "save_report_builder_decisions",
        "apply_report_builder_decisions",
        "report_section",
    ),
    (
        "prompt-optimizer",
        "save_prompt_optimizer_decisions",
        "apply_prompt_optimizer_decisions",
        "audit_check",
    ),
    (
        "concordato-plan-review",
        "save_concordato_plan_decisions",
        "apply_concordato_plan_decisions",
        "source_inventory",
    ),
]

# Client File Preparation deliberately refuses ad-hoc persistent directories: its
# own integration suite builds and seals a real phase-one run before Save/Apply.
# The generic persistence fixtures below exercise only servers whose contract
# permits synthetic unsealed output directories.
GENERIC_PERSISTENCE_REVIEW_SAVE_TOOLS = [
    tool for tool in REVIEW_SAVE_TOOLS if tool[0] != "client-file-preparation"
]

REVIEW_RENDER_TOOLS = {
    "check-entries": "render_check_entries_review",
    "deep-research-validator": "render_deep_research_review",
    "client-file-preparation": "render_client_file_preparation_review",
    "new-client": "render_new_client_review",
    "audit-reconciliation": "render_audit_reconciliation_review",
    "journal-sampling": "render_journal_sampling_review",
    "journal-bank-reconciliation": "render_journal_bank_review",
    "report-builder": "render_report_builder_review",
    "prompt-optimizer": "render_prompt_optimizer_review",
    "concordato-plan-review": "render_concordato_plan_review",
}

REVIEW_ITEM_LIMITS = {
    "check-entries": 2500,
    "deep-research-validator": 2500,
    "client-file-preparation": 2500,
    "new-client": 2500,
    "audit-reconciliation": 2500,
    "journal-sampling": 2500,
    "journal-bank-reconciliation": 2500,
    "report-builder": 3000,
    "prompt-optimizer": 2500,
    "concordato-plan-review": 2500,
}


@pytest.mark.parametrize(
    "target",
    widget_generator.TARGETS,
    ids=lambda target: target["plugin"],
)
def test_non_plotting_review_assets_match_generator(
    target: dict[str, Any],
) -> None:
    plugin = str(target["plugin"])
    asset = str(target["asset"])
    asset_dir = ROOT / "plugins" / plugin / "assets"

    assert (asset_dir / asset).read_text(encoding="utf-8") == (
        widget_generator.render_target(target)
    )
    assert (asset_dir / "review-workbench-adapter.json").read_text(
        encoding="utf-8"
    ) == json.dumps(
        widget_generator.adapter_config(target),
        ensure_ascii=True,
        indent=2,
    ) + "\n"


def test_client_file_preparation_widget_forwards_stable_reviewer_attribution() -> None:
    plugin_root = ROOT / "plugins" / "client-file-preparation"
    widget_path = plugin_root / "assets" / "client-file-preparation-review-widget.html"
    widget = widget_path.read_text(encoding="utf-8")
    adapter = json.loads(
        (plugin_root / "assets" / "review-workbench-adapter.json").read_text(
            encoding="utf-8"
        )
    )
    script = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const html = fs.readFileSync(process.argv[1], "utf8");
const match = html.match(/<script>([\s\S]*)<\/script>/);
if (!match) throw new Error("widget script missing");

const elements = new Map();
function element(id = "") {
  return {
    id, textContent: "", innerHTML: "", className: "", value: "",
    disabled: false, style: {}, dataset: {}, addEventListener() {},
    appendChild() {}, remove() {}, select() {}, setAttribute() {},
    closest() { return null; },
  };
}
const document = {
  title: "", documentElement: { lang: "en" }, body: element("body"),
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, element(id));
    return elements.get(id);
  },
  createElement(tag) { return element(tag); },
  execCommand() { return true; },
};
const item = {
  id: "document-1", item_type: "document_inventory", title: "Document",
  allowed_actions: ["accept", "mark_unclear"], recommended_action: "accept",
  status: "needs_review", data: {}, evidence: [],
};
const toolOutput = {
  widget_type: "client_file_preparation_review",
  run_intake: { run_id: "opaque-run", input_paths: [], data_posture: {}, execution_trace: [] },
  review_payload: {
    schema_version: "1.0", plugin: "client-file-preparation",
    workflow: "client-file-preparation", run_id: "opaque-run",
    status: "ready_for_review", items: [item], item_count: 1, summary: {},
  },
  ui_decisions: { decisions: [], decision_count: 0, status: "pending_review" },
  final_artifacts: { outputs: [{ path: "review_payload.json" }] },
  decision_policy: {
    save_tool: "save_client_file_preparation_decisions",
    apply_tool: "apply_client_file_preparation_decisions",
    can_persist: true,
    persistence_token: "a".repeat(43),
  },
};
const context = {
  Blob, URL, URLSearchParams, console, document, navigator: {}, setTimeout, clearTimeout,
  window: {
    location: { search: "" },
    openai: {
      toolOutput, widgetState: null, lastState: null,
      setWidgetState(value) { this.lastState = value; },
    },
  },
};
context.globalThis = context;
vm.createContext(context);
new vm.Script(`${match[1]}
ensureDecision(state.payload.review_payload.items[0], "accept");
state.reviewerAlias = "session_token=do-not-store";
let invalidAliasError = "";
try { validateDecisionInputs(collectDecisionInputs()); } catch (error) { invalidAliasError = error.message; }
state.reviewerAlias = "Fabio Annovazzi";
validateDecisionInputs(collectDecisionInputs());
persistWidgetState();
const persistentSave = saveToolArgs();
const persistentApply = applyToolArgs();
state.payload.decision_policy.can_persist = false;
delete state.payload.decision_policy.persistence_token;
const nonpersistentApply = applyToolArgs();
globalThis.__result = {
  saveReviewer: persistentSave.reviewer,
  applyReviewer: persistentApply.reviewer,
  fallbackReviewer: fallbackUiDecisions().reviewer,
  storedReviewer: window.openai.lastState?.reviewer_alias || null,
  savePersistenceToken: persistentSave.persistence_token,
  applyPersistenceToken: persistentApply.persistence_token,
  persistentHasFinalArtifacts: Object.hasOwn(persistentApply, "final_artifacts"),
  nonpersistentHasFinalArtifacts: Object.hasOwn(nonpersistentApply, "final_artifacts"),
  invalidAliasError,
};`).runInContext(context);
process.stdout.write(JSON.stringify(context.__result));
"""

    completed = subprocess.run(
        [_bundled_node_or_skip(), "-e", script, widget_path.as_posix()],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
        timeout=20,
    )
    result = json.loads(completed.stdout)

    assert adapter["requiresReviewerAlias"] is True
    assert "useDecisionRevision" not in adapter
    assert 'id="reviewer-alias"' in widget
    assert 'maxlength="160"' in widget
    assert "A real professional name is allowed" in widget
    assert "pseudonymous" not in widget
    assert "expected_decision_revision" not in widget
    assert "reuse_saved_details" not in widget
    assert result == {
        "saveReviewer": "Fabio Annovazzi",
        "applyReviewer": "Fabio Annovazzi",
        "fallbackReviewer": "Fabio Annovazzi",
        "storedReviewer": "Fabio Annovazzi",
        "savePersistenceToken": "a" * 43,
        "applyPersistenceToken": "a" * 43,
        "persistentHasFinalArtifacts": False,
        "nonpersistentHasFinalArtifacts": True,
        "invalidAliasError": "Reviewer reference must be at most 160 characters and must not contain credentials, session material, or raw local paths.",
    }


def _assert_widget_resource_meta(meta: dict[str, object], uri: str) -> None:
    description = meta.get("openai/widgetDescription")
    assert isinstance(description, str)
    assert len(description.strip()) >= 20
    assert meta["openai/widgetPrefersBorder"] is False

    csp = meta["openai/widgetCSP"]
    assert isinstance(csp, dict)
    assert csp["connect_domains"] == []
    assert csp["resource_domains"] == []

    ui = meta.get("ui")
    if isinstance(ui, dict) and "resourceUri" in ui:
        assert ui["resourceUri"] == uri
    if "openai/widgetDomain" in meta:
        assert meta["openai/widgetDomain"] == "https://chatgpt.com"


def _assert_review_tool_annotations(
    tools: list[dict[str, object]],
    *,
    validate_tool: str,
    render_tool: str,
    save_tool: str,
    apply_tool: str,
) -> None:
    tools_by_name = {tool["name"]: tool for tool in tools}
    expected_tools = {validate_tool, render_tool, save_tool, apply_tool}
    assert expected_tools <= set(tools_by_name)

    render_meta = tools_by_name[render_tool]["_meta"]
    template = render_meta["openai/outputTemplate"]
    assert isinstance(template, str)
    assert template.startswith("ui://widget/")
    assert template.endswith(".html")
    assert render_meta["openai/widgetAccessible"] is True
    assert render_meta["ui/resourceUri"] == template
    assert render_meta["ui"] == {
        "resourceUri": template,
        "visibility": ["model"],
    }
    invoking = render_meta["openai/toolInvocation/invoking"]
    invoked = render_meta["openai/toolInvocation/invoked"]
    assert isinstance(invoking, str)
    assert invoking.startswith("Rendering ")
    assert len(invoking.strip()) >= 20
    assert isinstance(invoked, str)
    assert invoked.startswith("Rendered ")
    assert len(invoked.strip()) >= 19

    for tool_name in (validate_tool, render_tool):
        annotations = tools_by_name[tool_name]["annotations"]
        assert annotations == {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }

    for tool_name in (save_tool, apply_tool):
        annotations = tools_by_name[tool_name]["annotations"]
        assert annotations == {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": "client_file_preparation" not in tool_name,
            "openWorldHint": False,
        }


@pytest.mark.parametrize(("plugin", "asset", "title"), WORKBENCH_WIDGETS)
def test_non_plotting_review_workbench_exposes_review_ui(
    plugin: str, asset: str, title: str
) -> None:
    html = (ROOT / "plugins" / plugin / asset).read_text(encoding="utf-8")
    adapter = json.loads(
        (
            ROOT / "plugins" / plugin / "assets" / "review-workbench-adapter.json"
        ).read_text(encoding="utf-8")
    )

    assert f"<title>{title}</title>" in html
    assert f'<h1 id="app-title">{title}</h1>' in html
    assert "Preview sample review" in html
    assert "Save decisions" in html
    assert "Apply decisions" in html
    assert "callTool" in html
    assert "decision_policy" in html
    assert adapter["applyTool"] in html
    assert adapter["queueTitle"] in html
    assert adapter["detailTitle"] in html
    assert adapter["detailMode"] in html
    assert {"it", "fr", "de"} <= set(adapter["localized"])
    assert "UI_TEXT" in html
    assert "Applica decisioni" in html
    assert "Appliquer decisions" in html
    assert "Entscheidungen anwenden" in html
    assert "Final outputs" in html
    assert "Helper execution routes" in html
    assert "Optional upload routes" in html
    assert (
        "This does not describe or count the context sent by Codex to the model."
        in html
    )
    assert "Helper remote SQL" in html
    assert "Helper hosted notebook" in html
    assert "Execution provenance" in html
    assert "execution-provenance" in html
    assert "execution_trace" in html
    assert "deterministic_review_session" in html
    assert "local_codex_workspace" in html
    assert "renderExecutionProvenance" in html
    assert "traceEntries" in html
    assert "Review safeguards" in html
    assert "review-safeguards" in html
    assert "safeguardLocalExecution" in html
    assert "safeguardExternalRoute" in html
    assert "safeguardBoundedPayload" in html
    assert "safeguardDecisionPersistence" in html
    assert "safeguardFinalArtifacts" in html
    assert "externalRouteUsed" in html
    assert "external_routes_used" in html
    assert "externalApprovalMissing" not in html
    assert "executionTraceMissing" in html
    assert "renderReviewSafeguards" in html
    assert "externalExecutionUsed" in html
    if plugin == "deep-research-validator":
        assert "Source Support" in html
        assert "Supporto fonte" in html
        assert "Appui de la source" in html
        assert "Quellennachweis" in html
    assert "modelExcerptValue" not in html
    assert "redaction_status" not in html
    assert "model_excerpts_sent" not in html
    assert "Percorsi dati dei processi di supporto" in html
    assert (
        r"Non descrive n\u00e9 conta il contesto inviato da Codex al modello." in html
    )
    assert "Provenienza esecuzione" in html
    assert "Garanzie revisione" in html
    assert "SQL distant" in html
    assert "Provenance execution" in html
    assert "Garde-fous revue" in html
    assert r"Flux de donn\u00e9es des processus auxiliaires" in html
    assert "Datenwege der Hilfsprozesse" in html
    assert "Ausfuehrungsnachweis" in html
    assert "Review-Schutzmassnahmen" in html
    assert "data-posture" in html
    assert "remote_sql_execution_used" in html
    assert "hosted_notebook_execution_used" in html
    assert "artifact-tags" in html
    assert "artifact-qa" in html
    assert "artifactQaHtml" in html
    assert "artifactQaSectionHtml" in html
    assert "Verification details" in html
    assert "Required text" in html
    assert "Required columns" in html
    assert "Required cells" in html
    assert "review_summary.md" in html
    assert "evidence_workbook.xlsx" in html
    assert "local_codex_workspace" in html
    assert "required_sheet_headers" in html
    assert "office_zip" in html
    assert "workbook_xml" in html
    assert "Dettagli verifica" in html
    assert "Details verification" in html
    assert "Pruefdetails" in html
    assert "artifactNotesHtml" in html
    assert "blockerSummary" in html
    assert "followup_context" in html
    assert "state-strip" in html
    assert "state-chip" in html
    assert "data-state-filter" in html
    assert "reviewStateFor" in html
    assert "selectedState" in html
    assert "@media (max-width: 760px)" in html
    assert ".shell { display: flex; flex-direction: column; }" in html
    assert ".review-actions { order: 4; }" in html
    assert ".content { order: 7; }" in html
    assert ".data-posture { order: 9; }" in html
    assert ".execution-provenance { order: 10; }" in html
    assert ".safeguards { order: 11; }" in html
    assert ".progress-meter { grid-template-columns: 1fr; }" in html
    assert ".safeguards__grid { grid-template-columns: 1fr; }" in html
    assert ".action-buttons > *, .tabs > *, .state-filters > *" in html
    assert "flex: 1 1 100%" in html
    assert ".progress-rail { min-width: 0; }" in html
    assert ".execution-kv, .recovery-panel__line" in html
    assert ".row > span" in html
    assert ".row > span:last-child" in html
    assert ".row .action { max-width: 100%; }" in html
    assert ".review-heading > div" in html
    assert ".review-heading { grid-template-columns: 1fr; }" in html
    assert ".review-heading .status-token { justify-self: start; }" in html
    assert ".workflow-detail__grid { grid-template-columns: 1fr; }" in html
    assert ".workflow-detail--prompt-lab .workflow-card--draft" in html
    assert ".decision-grid { display: grid; grid-template-columns: 1fr; }" in html
    assert ".decision-choice { width: 100%; }" in html
    assert ".decision-impact__grid { grid-template-columns: 1fr; }" in html
    assert "word-break: break-word" in html
    assert "progress-rail" in html
    assert "decision-progress-fill" in html
    assert "decision-impact" in html
    assert "decisionImpactHtml" in html
    assert "requestedDocumentHints" in html
    assert "collectExplicitValues" in html
    assert "writeTarget" in html
    assert "MCP save/apply" in html
    assert "Solo copia JSON" in html
    assert "Enregistrer/appliquer MCP" in html
    assert "MCP speichern/anwenden" in html
    assert "review-store" in html
    assert "recovery-panel" in html
    assert "renderReviewStore" in html
    assert "renderRecoveryPanel" in html
    assert "setRecoveryIssue" in html
    assert "canPersistThroughBridge" in html
    assert "changedDecisionCount" in html
    assert "savedDecisionInputs" in html
    assert "appliedDecisionInputs" in html
    assert "recoveredDraftCount" in html
    assert "In sync" in html
    assert "JSON fallback active" in html
    assert "Save did not persist" in html
    assert "Apply did not persist" in html
    assert "non salvate" in html
    assert "Fallback JSON attivo" in html
    assert "non enregistrees" in html
    assert "Fallback JSON actif" in html
    assert "ungespeichert" in html
    assert "JSON-Fallback aktiv" in html
    assert "row_count" in html
    assert "required_columns" in html
    assert "required_sheets" in html
    assert "required_cells" in html
    assert "required_text" in html
    assert "next_actions" in html
    assert "Righe" in html
    assert "Lignes" in html
    assert "Zeilen" in html
    assert "Tutti gli stati" in html
    assert "Tous statuts" in html
    assert "Alle Status" in html
    assert "No review payload loaded" in html
    assert "workflow-detail" in html


@pytest.mark.parametrize(("plugin", "_asset", "_title"), WORKBENCH_WIDGETS)
def test_non_plotting_review_resources_declare_local_widget_metadata(
    plugin: str, _asset: str, _title: str
) -> None:
    responses = {
        response["id"]: response
        for response in _call_mcp_server(
            plugin,
            [{"jsonrpc": "2.0", "id": 1, "method": "resources/list"}],
        )
    }
    resources = responses[1]["result"]["resources"]
    assert len(resources) == 1
    resource = resources[0]
    uri = resource["uri"]
    assert uri.startswith("ui://widget/")
    assert uri.endswith(".html")
    assert resource["mimeType"] == "text/html;profile=mcp-app"
    _assert_widget_resource_meta(resource["_meta"], uri)

    read_responses = {
        response["id"]: response
        for response in _call_mcp_server(
            plugin,
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "resources/read",
                    "params": {"uri": uri},
                }
            ],
        )
    }
    contents = read_responses[1]["result"]["contents"]
    assert len(contents) == 1
    content = contents[0]
    assert content["uri"] == uri
    assert content["mimeType"] == "text/html;profile=mcp-app"
    assert "<html" in content["text"]
    _assert_widget_resource_meta(content["_meta"], uri)


@pytest.mark.parametrize(
    ("plugin", "save_tool", "apply_tool", "_item_type"), REVIEW_SAVE_TOOLS
)
def test_non_plotting_review_tools_declare_safe_intent_annotations(
    plugin: str, save_tool: str, apply_tool: str, _item_type: str
) -> None:
    responses = {
        response["id"]: response
        for response in _call_mcp_server(
            plugin,
            [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}],
        )
    }
    _assert_review_tool_annotations(
        responses[1]["result"]["tools"],
        validate_tool=REVIEW_RENDER_TOOLS[plugin].replace("render_", "validate_"),
        render_tool=REVIEW_RENDER_TOOLS[plugin],
        save_tool=save_tool,
        apply_tool=apply_tool,
    )


def test_non_plotting_review_workbench_adapters_are_workflow_specific() -> None:
    adapters = [
        json.loads(
            (
                ROOT / "plugins" / plugin / "assets" / "review-workbench-adapter.json"
            ).read_text(encoding="utf-8")
        )
        for plugin, _asset, _title in WORKBENCH_WIDGETS
    ]

    assert len({adapter["detailMode"] for adapter in adapters}) == len(adapters)
    assert len({adapter["queueTitle"] for adapter in adapters}) == len(adapters)
    assert len({adapter["detailTitle"] for adapter in adapters}) == len(adapters)
    for adapter in adapters:
        assert adapter["saveTool"].startswith("save_")
        assert adapter["applyTool"].startswith("apply_")
        assert len(adapter["detailGroups"]) >= 3
        for group in adapter["detailGroups"]:
            assert group["title"]
            assert group["fields"]
    check_entries = next(
        adapter for adapter in adapters if adapter["plugin"] == "check-entries"
    )
    support_group = next(
        group
        for group in check_entries["detailGroups"]
        if group["title"] == "Support Document"
    )
    assert "requested_document" in support_group["fields"]
    missing_demo_item = next(
        item
        for item in check_entries["demo"]["items"]
        if item["item_type"] == "missing_support"
    )
    supported_demo_item = next(
        item
        for item in check_entries["demo"]["items"]
        if item["item_type"] == "supported_entry"
    )
    assert supported_demo_item["data"]["target_artifact"] == "check_results.csv"
    assert supported_demo_item["data"]["target_id_field"] == "source_row"
    assert supported_demo_item["data"]["target_record_id"] == "1"
    assert supported_demo_item["data"]["target_field"] == "review_notes"
    assert "edit_hint" in supported_demo_item["data"]
    assert (
        missing_demo_item["data"]["requested_document"]
        == "Supporting PDF for movement 1002"
    )
    assert missing_demo_item["data"]["target_record_id"] == "2"
    journal_bank = next(
        adapter
        for adapter in adapters
        if adapter["plugin"] == "journal-bank-reconciliation"
    )
    match_group = next(
        group
        for group in journal_bank["detailGroups"]
        if group["title"] == "Match Result"
    )
    assert "requested_document" in match_group["fields"]
    matched_demo_item = next(
        item
        for item in journal_bank["demo"]["items"]
        if item["item_type"] == "matched_pair"
    )
    assert matched_demo_item["data"]["target_artifact"] == (
        "reconciliation_matches.csv"
    )
    assert matched_demo_item["data"]["target_id_field"] == "bank_transaction_id"
    assert matched_demo_item["data"]["target_record_id"] == "bank:18"
    assert matched_demo_item["data"]["target_field"] == "review_note"
    assert "edit_hint" in matched_demo_item["data"]
    unmatched_demo_item = next(
        item
        for item in journal_bank["demo"]["items"]
        if item["item_type"] == "unmatched_bank"
    )
    assert unmatched_demo_item["data"]["requested_document"] == (
        "Journal or ledger support for bank transaction FEE9"
    )
    deep_research = next(
        adapter
        for adapter in adapters
        if adapter["plugin"] == "deep-research-validator"
    )
    source_support_group = next(
        group
        for group in deep_research["detailGroups"]
        if group["title"] == "Source Support"
    )
    assert source_support_group["fields"] == [
        "source_quote",
        "source_support",
        "reasoning_review",
    ]
    claim_demo_item = next(
        item
        for item in deep_research["demo"]["items"]
        if item["item_type"] == "supported_claim"
    )
    assert claim_demo_item["evidence"][0]["kind"] == "claim_vs_citation"
    assert claim_demo_item["data"]["source_quote"]
    assert claim_demo_item["data"]["target_artifact"] == "claims_review.json"
    assert claim_demo_item["data"]["target_records_key"] == "claims"
    assert claim_demo_item["data"]["target_id_field"] == "claim_index"
    assert claim_demo_item["data"]["target_record_id"] == "4"
    assert claim_demo_item["data"]["target_field"] == "proposed_fix"
    assert "edit_hint" in claim_demo_item["data"]


def test_non_plotting_review_workbench_scripts_parse() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to parse review widget scripts.")
    files = [
        (ROOT / "plugins" / plugin / asset).as_posix()
        for plugin, asset, _title in WORKBENCH_WIDGETS
    ]
    script = """
const fs = require("fs");
const vm = require("vm");
for (const file of process.argv.slice(1)) {
  const html = fs.readFileSync(file, "utf8");
  const match = html.match(/<script>([\\s\\S]*)<\\/script>/);
  if (!match) throw new Error(`missing script in ${file}`);
  new vm.Script(match[1], { filename: file });
}
"""

    subprocess.run([node, "-e", script, *files], check=True, cwd=ROOT)


@pytest.mark.parametrize(
    ("plugin", "_save_tool", "_apply_tool", "item_type"), REVIEW_SAVE_TOOLS
)
def test_non_plotting_review_render_tools_validate_payload_before_rendering(
    plugin: str, _save_tool: str, _apply_tool: str, item_type: str
) -> None:
    adapter = json.loads(
        (
            ROOT / "plugins" / plugin / "assets" / "review-workbench-adapter.json"
        ).read_text(encoding="utf-8")
    )
    render_tool = REVIEW_RENDER_TOOLS[plugin]
    review_payload = _minimal_review_payload(plugin, item_type)
    invalid_payload = {
        **review_payload,
        "item_count": review_payload["item_count"] + 1,
    }
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": render_tool,
                "arguments": {"review_payload": review_payload},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": render_tool,
                "arguments": {"review_payload": invalid_payload},
            },
        },
    ]

    responses = {
        response["id"]: response for response in _call_mcp_server(plugin, messages)
    }

    valid_result = responses[1]["result"]
    valid_payload = valid_result["structuredContent"]
    assert valid_payload["review_payload"]["plugin"] == plugin
    assert valid_payload["review_payload"]["item_count"] == 1
    assert valid_payload["decision_policy"]["apply_tool"] == adapter["applyTool"]
    assert valid_result["_meta"]["openai/outputTemplate"].startswith("ui://widget/")
    assert valid_result["_meta"]["openai/outputTemplate"].endswith(".html")
    assert valid_result["_meta"]["openai/widgetAccessible"] is True

    invalid_result = responses[2]["result"]
    assert invalid_result["isError"] is True
    assert "item_count must equal" in invalid_result["structuredContent"]["error"]


@pytest.mark.parametrize(
    ("plugin", "_save_tool", "_apply_tool", "item_type"), REVIEW_SAVE_TOOLS
)
def test_non_plotting_review_render_tools_enforce_bounded_payload_policy(
    plugin: str, _save_tool: str, _apply_tool: str, item_type: str
) -> None:
    render_tool = REVIEW_RENDER_TOOLS[plugin]
    too_many_items_payload = _review_payload_with_items(
        plugin,
        item_type,
        REVIEW_ITEM_LIMITS[plugin] + 1,
    )
    oversized_payload = _minimal_review_payload(plugin, item_type)
    oversized_payload["items"][0]["data"] = {
        "status": "ready",
        "oversized_note": "x" * 3_100_000,
    }
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": render_tool,
                "arguments": {"review_payload": too_many_items_payload},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": render_tool,
                "arguments": {"review_payload": oversized_payload},
            },
        },
    ]

    responses = {
        response["id"]: response for response in _call_mcp_server(plugin, messages)
    }

    too_many_items_result = responses[1]["result"]
    assert too_many_items_result["isError"] is True
    assert (
        "review_payload.items exceeds"
        in too_many_items_result["structuredContent"]["error"]
    )

    oversized_result = responses[2]["result"]
    assert oversized_result["isError"] is True
    assert "widget payload exceeds" in oversized_result["structuredContent"]["error"]


def _call_mcp_server(plugin: str, messages: list[dict[str, object]]) -> list[dict]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise MCP review save tools.")
    server_path = ROOT / "plugins" / plugin / "mcp" / "server.cjs"
    completed = subprocess.run(
        [node, str(server_path), "--stdio"],
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def _minimal_review_payload(plugin: str, item_type: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": f"{plugin}-save-test",
        "review_type": f"{plugin.replace('-', '_')}_review",
        "items": [
            {
                "id": "item-1",
                "item_type": item_type,
                "title": "Review item",
                "source_path": "source.xlsx",
                "output_path": "review_payload.json",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "status": "needs_review",
                "data": {"status": "ready"},
                "evidence": [{"kind": "test_evidence", "status": "ready"}],
            }
        ],
        "item_count": 1,
        "status": "ready_for_review",
        "summary": {},
    }


def _review_payload_with_items(
    plugin: str, item_type: str, item_count: int
) -> dict[str, object]:
    payload = _minimal_review_payload(plugin, item_type)
    template = payload["items"][0]
    payload["items"] = [
        {
            **template,
            "id": f"item-{index}",
            "title": f"Review item {index}",
        }
        for index in range(item_count)
    ]
    payload["item_count"] = item_count
    return payload


def _two_item_review_payload(plugin: str, item_type: str) -> dict[str, object]:
    payload = _minimal_review_payload(plugin, item_type)
    payload["items"] = [
        payload["items"][0],
        {
            **payload["items"][0],
            "id": "item-2",
            "title": "Review item 2",
            "data": {"status": "needs_evidence"},
            "evidence": [{"kind": "test_evidence", "status": "needs_evidence"}],
        },
    ]
    payload["item_count"] = 2
    return payload


def _adapter_demo_review_payload(plugin: str) -> dict[str, object]:
    adapter = json.loads(
        (
            ROOT / "plugins" / plugin / "assets" / "review-workbench-adapter.json"
        ).read_text(encoding="utf-8")
    )
    demo = adapter["demo"]
    return {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": f"{plugin}-adapter-demo-test",
        "review_type": demo["review_type"],
        "items": demo["items"],
        "item_count": len(demo["items"]),
        "status": "ready_for_review",
        "summary": {"source": "review-workbench-adapter-demo"},
    }


def _demo_decisions(review_payload: dict[str, object]) -> list[dict[str, object]]:
    decisions: list[dict[str, object]] = []
    for item in review_payload["items"]:
        assert isinstance(item, dict)
        data = item.get("data")
        assert isinstance(data, dict)
        action = item.get("recommended_action") or item["allowed_actions"][0]
        decision: dict[str, object] = {
            "item_id": item["id"],
            "action": action,
            "reviewer_note": f"Adapter demo decision for {item['id']}.",
        }
        if action == "edit":
            decision["edit_value"] = (
                f"Reviewer edit for {item['id']} from adapter demo test."
            )
        decisions.append(decision)
    return decisions


def _demo_target_artifact_outputs(
    output_dir: Path, review_payload: dict[str, object]
) -> list[dict[str, object]]:
    outputs: list[dict[str, object]] = [
        {"path": "review_payload.json", "kind": "json", "status": "written"}
    ]
    seen = {"review_payload.json"}
    for item in review_payload["items"]:
        assert isinstance(item, dict)
        declared_paths: list[str] = []
        output_path = item.get("output_path")
        if isinstance(output_path, str) and output_path:
            declared_paths.append(output_path)
        data = item.get("data")
        if isinstance(data, dict):
            target_artifact = data.get("target_artifact")
            if isinstance(target_artifact, str) and target_artifact:
                declared_paths.append(target_artifact)
        for artifact_path in declared_paths:
            if artifact_path in seen:
                continue
            seen.add(artifact_path)
            suffix = Path(artifact_path).suffix.lower().lstrip(".")
            kind = suffix or "artifact"
            outputs.append({"path": artifact_path, "kind": kind, "status": "written"})
            target_path = output_dir / artifact_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if kind in {"md", "txt"}:
                target_path.write_text(
                    "Original adapter demo artifact.\n",
                    encoding="utf-8",
                )
            elif kind == "json":
                target_path.write_text(
                    json.dumps({"language": "en", "review_session": {}}, indent=2)
                    + "\n",
                    encoding="utf-8",
                )
            elif kind == "csv":
                target_path.write_text("id,review_notes\n", encoding="utf-8")
    return outputs


@pytest.mark.parametrize(
    ("plugin", "save_tool", "apply_tool", "_item_type"),
    GENERIC_PERSISTENCE_REVIEW_SAVE_TOOLS,
)
def test_non_plotting_review_save_and_apply_tools_accept_adapter_demo_payloads(
    tmp_path: Path, plugin: str, save_tool: str, apply_tool: str, _item_type: str
) -> None:
    output_dir = tmp_path / plugin / "adapter-demo"
    output_dir.mkdir(parents=True)
    review_payload = _adapter_demo_review_payload(plugin)
    decisions = _demo_decisions(review_payload)
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "outputs": _demo_target_artifact_outputs(output_dir, review_payload),
        "status": "written_pending_review",
    }
    run_intake = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "output_dir": str(output_dir),
        "assumptions": {
            "language": "en",
            "question_text": "Research Swiss tax residence using official sources.",
        },
    }
    for filename, payload in (
        ("run_intake.json", run_intake),
        ("review_payload.json", review_payload),
        ("final_artifacts.json", final_artifacts),
    ):
        (output_dir / filename).write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": save_tool,
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "decisions": decisions,
                    "decision_source": "adapter_demo_test",
                    "reviewer": "pytest",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": apply_tool,
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "final_artifacts": final_artifacts,
                    "decisions": decisions,
                    "decision_source": "adapter_demo_test",
                    "reviewer": "pytest",
                },
            },
        },
    ]

    responses = {
        response["id"]: response for response in _call_mcp_server(plugin, messages)
    }

    save_result = responses[1]["result"]["structuredContent"]
    assert save_result["ok"] is True
    assert save_result["persisted"] is True
    assert save_result["status"] == "reviewed"
    assert save_result["decision_count"] == review_payload["item_count"]

    written = json.loads((output_dir / "ui_decisions.json").read_text(encoding="utf-8"))
    assert written["decision_source"] == "adapter_demo_test"
    assert written["decision_count"] == review_payload["item_count"]
    assert {decision["item_id"] for decision in written["decisions"]} == {
        item["id"] for item in review_payload["items"]
    }

    apply_result = responses[2]["result"]["structuredContent"]
    assert apply_result["ok"] is True
    assert apply_result["persisted"] is True
    assert apply_result["decision_count"] == review_payload["item_count"]
    assert apply_result["application_status"] in {
        "blocked",
        "final_ready",
        "partial_review_applied",
    }

    applied = json.loads(
        (output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    assert applied["decision_source"] == "adapter_demo_test"
    assert applied["decision_count"] == review_payload["item_count"]
    assert len(applied["effects"]) == review_payload["item_count"]
    assert {effect["item_id"] for effect in applied["effects"]} == {
        item["id"] for item in review_payload["items"]
    }

    final = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert final["review_application"]["decision_count"] == review_payload["item_count"]
    assert final["review_status"] == apply_result["application_status"]


def _editable_review_payload(
    plugin: str, item_type: str, target_artifact: str = "draft_memo.md"
) -> dict[str, object]:
    payload = _minimal_review_payload(plugin, item_type)
    payload["items"][0] = {
        **payload["items"][0],
        "id": "editable-1",
        "title": "Editable memo",
        "output_path": target_artifact,
        "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
        "data": {"target_artifact": target_artifact, "status": "ready"},
    }
    return payload


def _structured_edit_review_payload(
    plugin: str,
    item_type: str,
    target_artifact: str,
    target_field: str,
    *,
    records_key: str | None = None,
) -> dict[str, object]:
    payload = _editable_review_payload(plugin, item_type, target_artifact)
    data = {
        "target_artifact": target_artifact,
        "target_id_field": "item_id",
        "target_record_id": "structured-1",
        "target_field": target_field,
        "status": "ready",
    }
    if records_key:
        data["target_records_key"] = records_key
    payload["items"][0] = {
        **payload["items"][0],
        "id": "structured-1",
        "title": "Structured row edit",
        "output_path": target_artifact,
        "data": data,
    }
    return payload


@pytest.mark.parametrize(
    ("plugin", "save_tool", "apply_tool", "item_type"),
    GENERIC_PERSISTENCE_REVIEW_SAVE_TOOLS,
)
def test_non_plotting_review_save_and_apply_tools_persist_review_results(
    tmp_path: Path, plugin: str, save_tool: str, apply_tool: str, item_type: str
) -> None:
    output_dir = tmp_path / plugin
    review_payload = _minimal_review_payload(plugin, item_type)
    run_intake = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "output_dir": str(output_dir),
    }
    messages: list[dict[str, object]] = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": save_tool,
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "decisions": [
                        {
                            "item_id": "item-1",
                            "action": "accept",
                            "reviewer_note": "Reviewed in widget.",
                        }
                    ],
                    "decision_source": "mcp_widget_test",
                    "reviewer": "pytest",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": apply_tool,
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "final_artifacts": {
                        "schema_version": "1.0",
                        "plugin": plugin,
                        "workflow": plugin,
                        "run_id": review_payload["run_id"],
                        "outputs": [
                            {
                                "path": "review_payload.json",
                                "kind": "json",
                                "status": "written",
                            }
                        ],
                        "caveats": ["Original gallery caveat."],
                        "next_actions": ["Original gallery next action."],
                        "status": "written_pending_review",
                    },
                    "decisions": [
                        {
                            "item_id": "item-1",
                            "action": "accept",
                            "reviewer_note": "Reviewed in widget.",
                        }
                    ],
                    "decision_source": "mcp_widget_test",
                    "reviewer": "pytest",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": save_tool,
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "decisions": [{"item_id": "missing", "action": "accept"}],
                },
            },
        },
    ]

    responses = {
        response["id"]: response for response in _call_mcp_server(plugin, messages)
    }

    tool_names = {tool["name"] for tool in responses[1]["result"]["tools"]}
    assert save_tool in tool_names
    assert apply_tool in tool_names

    save_result = responses[2]["result"]["structuredContent"]
    assert save_result["ok"] is True
    assert save_result["persisted"] is True
    assert save_result["decision_count"] == 1
    assert save_result["status"] == "reviewed"

    written = json.loads((output_dir / "ui_decisions.json").read_text(encoding="utf-8"))
    assert written["plugin"] == plugin
    assert written["decision_source"] == "mcp_widget_test"
    assert written["reviewer"] == "pytest"
    assert written["decisions"][0]["item_id"] == "item-1"
    assert written["decisions"][0]["action"] == "accept"

    apply_result = responses[3]["result"]["structuredContent"]
    assert apply_result["ok"] is True
    assert apply_result["persisted"] is True
    assert apply_result["decision_count"] == 1
    assert apply_result["blocker_count"] == 0
    assert apply_result["application_status"] == "final_ready"

    applied = json.loads(
        (output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    assert applied["plugin"] == plugin
    assert applied["application_status"] == "final_ready"
    assert applied["effects"][0]["item_id"] == "item-1"
    assert applied["effects"][0]["target_artifact"] == "review_payload.json"
    assert applied["effects"][0]["artifact_update"] == "decision_manifest_only"

    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert final_artifacts["status"] == "final_ready"
    assert final_artifacts["review_status"] == "final_ready"
    assert final_artifacts["caveats"] == ["Original gallery caveat."]
    assert final_artifacts["blockers"] == []
    assert final_artifacts["next_actions"] == [
        "Original gallery next action.",
        "Use final_artifacts.json as the reviewed artifact gallery for handoff.",
    ]
    output_paths = {output["path"] for output in final_artifacts["outputs"]}
    assert {"ui_decisions.json", "applied_decisions.json"} <= output_paths

    invalid_result = responses[4]["result"]
    assert invalid_result["isError"] is True
    assert "not in review_payload.items" in invalid_result["structuredContent"]["error"]


@pytest.mark.parametrize(
    ("plugin", "save_tool", "apply_tool", "item_type"),
    GENERIC_PERSISTENCE_REVIEW_SAVE_TOOLS,
)
def test_non_plotting_review_save_and_apply_tools_handle_partial_and_blocked_states(
    tmp_path: Path, plugin: str, save_tool: str, apply_tool: str, item_type: str
) -> None:
    partial_dir = tmp_path / plugin / "partial"
    blocked_dir = tmp_path / plugin / "blocked"
    review_payload = _two_item_review_payload(plugin, item_type)
    review_payload["items"][1]["data"] = {
        "status": "needs_evidence",
        "requested_document": f"{plugin}-support.pdf",
    }
    run_intake_partial = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "output_dir": str(partial_dir),
    }
    run_intake_blocked = {
        **run_intake_partial,
        "output_dir": str(blocked_dir),
    }
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "outputs": [
            {"path": "review_payload.json", "kind": "json", "status": "written"}
        ],
        "caveats": ["The review payload is bounded."],
        "next_actions": ["Review remaining items."],
        "status": "written_pending_review",
    }
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": save_tool,
                "arguments": {
                    "run_intake": run_intake_partial,
                    "review_payload": review_payload,
                    "decisions": [{"item_id": "item-1", "action": "accept"}],
                    "decision_source": "partial_review_test",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": apply_tool,
                "arguments": {
                    "run_intake": run_intake_partial,
                    "review_payload": review_payload,
                    "final_artifacts": final_artifacts,
                    "decisions": [{"item_id": "item-1", "action": "accept"}],
                    "decision_source": "partial_review_test",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": apply_tool,
                "arguments": {
                    "run_intake": run_intake_blocked,
                    "review_payload": review_payload,
                    "final_artifacts": final_artifacts,
                    "decisions": [
                        {"item_id": "item-1", "action": "accept"},
                        {
                            "item_id": "item-2",
                            "action": "mark_unclear",
                            "reviewer_note": "Evidence is insufficient.",
                        },
                    ],
                    "decision_source": "blocked_review_test",
                },
            },
        },
    ]

    responses = {
        response["id"]: response for response in _call_mcp_server(plugin, messages)
    }

    partial_save = responses[1]["result"]["structuredContent"]
    assert partial_save["ok"] is True
    assert partial_save["status"] == "partial_review"
    assert partial_save["decision_count"] == 1
    partial_ui_decisions = json.loads(
        (partial_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    assert partial_ui_decisions["status"] == "partial_review"
    assert partial_ui_decisions["item_count"] == 2

    partial_apply = responses[2]["result"]["structuredContent"]
    assert partial_apply["ok"] is True
    assert partial_apply["application_status"] == "partial_review_applied"
    assert partial_apply["blocker_count"] == 0
    partial_final = json.loads(
        (partial_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert partial_final["status"] == "partial_review_applied"
    assert partial_final["review_status"] == "partial_review_applied"
    assert partial_final["caveats"] == ["The review payload is bounded."]
    assert partial_final["blockers"] == []
    assert partial_final["next_actions"] == [
        "Review remaining items.",
        "Complete remaining review decisions before final handoff.",
    ]

    blocked_apply = responses[3]["result"]["structuredContent"]
    assert blocked_apply["ok"] is True
    assert blocked_apply["application_status"] == "blocked"
    assert blocked_apply["blocker_count"] == 1
    blocked_applied = json.loads(
        (blocked_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    assert blocked_applied["application_status"] == "blocked"
    assert blocked_applied["effects"][1]["requires_followup"] is True
    assert blocked_applied["effects"][1]["reviewer_note"] == "Evidence is insufficient."
    blocked_final = json.loads(
        (blocked_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert blocked_final["status"] == "blocked"
    assert blocked_final["review_status"] == "blocked"
    assert blocked_final["review_application"]["blocker_count"] == 1
    assert blocked_final["blockers"] == [
        {
            "item_id": "item-2",
            "item_type": item_type,
            "title": "Review item 2",
            "action": "mark_unclear",
            "status": "needs_evidence",
            "reviewer_note": "Evidence is insufficient.",
            "requested_documents": [],
        }
    ]
    assert blocked_final["next_actions"] == [
        "Review remaining items.",
        "Resolve blocked review decisions before treating final artifacts as ready.",
    ]


@pytest.mark.parametrize(
    ("plugin", "save_tool", "apply_tool", "item_type"),
    GENERIC_PERSISTENCE_REVIEW_SAVE_TOOLS,
)
def test_non_plotting_review_request_more_documents_uses_explicit_item_metadata(
    tmp_path: Path, plugin: str, save_tool: str, apply_tool: str, item_type: str
) -> None:
    output_dir = tmp_path / plugin / "missing-evidence"
    requested_document = f"{plugin}-support.pdf"
    review_payload = _two_item_review_payload(plugin, item_type)
    review_payload["items"][1] = {
        **review_payload["items"][1],
        "allowed_actions": [
            "accept",
            "edit",
            "mark_unclear",
            "request_more_documents",
            "skip",
        ],
        "recommended_action": "request_more_documents",
        "data": {
            "status": "needs_evidence",
            "requested_document": requested_document,
            "responsible_party": "AP team",
            "source_system": "client drive",
            "due_date": "2026-01-15",
            "source_file": "entries.xlsx",
            "source_row": 42,
            "amount_abs": 88.0,
            "reason": "No supporting PDF matched.",
            "priority": "high",
        },
        "evidence": [
            {
                "kind": "missing_document_request",
                "status": "needs_evidence",
                "requested_document": requested_document,
            }
        ],
    }
    run_intake = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "output_dir": str(output_dir),
    }
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "outputs": [
            {"path": "review_payload.json", "kind": "json", "status": "written"}
        ],
        "caveats": ["The review payload is bounded."],
        "next_actions": ["Review remaining items."],
        "status": "written_pending_review",
    }
    decisions = [
        {"item_id": "item-1", "action": "accept"},
        {
            "item_id": "item-2",
            "action": "request_more_documents",
            "reviewer_note": "Need the missing support.",
        },
    ]
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": save_tool,
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "decisions": decisions,
                    "decision_source": "missing_evidence_test",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": apply_tool,
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "final_artifacts": final_artifacts,
                    "decisions": decisions,
                    "decision_source": "missing_evidence_test",
                },
            },
        },
    ]

    responses = {
        response["id"]: response for response in _call_mcp_server(plugin, messages)
    }

    save_result = responses[1]["result"]["structuredContent"]
    assert save_result["ok"] is True
    assert save_result["status"] == "reviewed"
    ui_decisions = json.loads(
        (output_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    assert ui_decisions["decisions"][1]["requested_documents"] == [requested_document]
    assert ui_decisions["decisions"][1]["followup_context"] == {
        "owner": "AP team",
        "source_system": "client drive",
        "source_file": "entries.xlsx",
        "due_date": "2026-01-15",
        "record_id": "42",
        "amount": "88",
        "reason": "No supporting PDF matched.",
        "priority": "high",
    }

    apply_result = responses[2]["result"]["structuredContent"]
    assert apply_result["ok"] is True
    assert apply_result["application_status"] == "blocked"
    assert apply_result["blocker_count"] == 1
    applied = json.loads(
        (output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    assert applied["effects"][1]["requested_documents"] == [requested_document]
    assert applied["effects"][1]["followup_context"]["owner"] == "AP team"
    assert applied["effects"][1]["followup_context"]["record_id"] == "42"
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert final_artifacts["blockers"] == [
        {
            "item_id": "item-2",
            "item_type": item_type,
            "title": "Review item 2",
            "action": "request_more_documents",
            "status": "needs_evidence",
            "reviewer_note": "Need the missing support.",
            "requested_documents": [requested_document],
            "followup_context": {
                "owner": "AP team",
                "source_system": "client drive",
                "source_file": "entries.xlsx",
                "due_date": "2026-01-15",
                "record_id": "42",
                "amount": "88",
                "reason": "No supporting PDF matched.",
                "priority": "high",
            },
        }
    ]


@pytest.mark.parametrize(
    ("plugin", "_save_tool", "apply_tool", "item_type"),
    GENERIC_PERSISTENCE_REVIEW_SAVE_TOOLS,
)
def test_non_plotting_review_apply_tools_update_safe_text_artifacts_for_edit_decisions(
    tmp_path: Path, plugin: str, _save_tool: str, apply_tool: str, item_type: str
) -> None:
    output_dir = tmp_path / plugin / "edit"
    review_payload = _editable_review_payload(plugin, item_type)
    original_text = "Original draft text.\n"
    revised_text = "Revised text from the review UI.\nSecond line."
    output_dir.mkdir(parents=True)
    (output_dir / "draft_memo.md").write_text(original_text, encoding="utf-8")
    run_intake = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "output_dir": str(output_dir),
    }
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "outputs": [{"path": "draft_memo.md", "kind": "md", "status": "written"}],
        "status": "written_pending_review",
    }
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": apply_tool,
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "final_artifacts": final_artifacts,
                    "decisions": [
                        {
                            "item_id": "editable-1",
                            "action": "edit",
                            "edit_value": revised_text,
                            "reviewer_note": "Replace with reviewer wording.",
                        }
                    ],
                    "decision_source": "edit_revision_test",
                    "reviewer": "pytest",
                },
            },
        }
    ]

    responses = {
        response["id"]: response for response in _call_mcp_server(plugin, messages)
    }

    apply_result = responses[1]["result"]["structuredContent"]
    assert apply_result["ok"] is True
    assert apply_result["application_status"] == "final_ready"
    assert apply_result["revision_count"] == 1
    assert apply_result["target_update_count"] == 1
    applied = json.loads(
        (output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    assert applied["target_update_count"] == 1
    assert applied["target_update_paths"] == ["draft_memo.md"]
    assert applied["original_backup_paths"] == [
        "revisions/originals/draft_memo__editable-1.md"
    ]
    effect = applied["effects"][0]
    assert effect["artifact_update"] == "target_artifact_updated"
    assert effect["original_artifact_backup"] == (
        "revisions/originals/draft_memo__editable-1.md"
    )
    assert effect["revision_artifact"] == "revisions/draft_memo__editable-1.md"
    assert effect["edit_value"] == revised_text
    assert (output_dir / "draft_memo.md").read_text(encoding="utf-8") == revised_text
    assert (output_dir / "revisions/originals/draft_memo__editable-1.md").read_text(
        encoding="utf-8"
    ) == original_text
    revision_path = output_dir / effect["revision_artifact"]
    assert revision_path.read_text(encoding="utf-8") == revised_text

    final = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    revision_outputs = [
        output
        for output in final["outputs"]
        if output["path"] == effect["revision_artifact"]
    ]
    assert revision_outputs == [
        {
            "path": "revisions/draft_memo__editable-1.md",
            "kind": "md",
            "status": "written_revision",
            "source_artifact": "draft_memo.md",
            "item_id": "editable-1",
        }
    ]
    target_outputs = [
        output for output in final["outputs"] if output["path"] == "draft_memo.md"
    ]
    assert target_outputs == [
        {
            "path": "draft_memo.md",
            "kind": "md",
            "status": "updated_from_review",
            "item_id": "editable-1",
        }
    ]
    backup_outputs = [
        output
        for output in final["outputs"]
        if output["path"] == "revisions/originals/draft_memo__editable-1.md"
    ]
    assert backup_outputs == [
        {
            "path": "revisions/originals/draft_memo__editable-1.md",
            "kind": "md",
            "status": "backup_original",
            "source_artifact": "draft_memo.md",
            "item_id": "editable-1",
        }
    ]
    assert final["review_application"]["revision_count"] == 1
    assert final["review_application"]["revision_paths"] == [
        "revisions/draft_memo__editable-1.md"
    ]
    assert final["review_application"]["target_update_count"] == 1
    assert final["review_application"]["target_update_paths"] == ["draft_memo.md"]
    assert final["review_application"]["original_backup_paths"] == [
        "revisions/originals/draft_memo__editable-1.md"
    ]


@pytest.mark.parametrize(
    ("plugin", "_save_tool", "apply_tool", "item_type"),
    GENERIC_PERSISTENCE_REVIEW_SAVE_TOOLS,
)
def test_non_plotting_review_apply_tools_keep_binary_targets_revision_only(
    tmp_path: Path, plugin: str, _save_tool: str, apply_tool: str, item_type: str
) -> None:
    output_dir = tmp_path / plugin / "binary-edit"
    review_payload = _editable_review_payload(plugin, item_type, "draft_report.docx")
    original_bytes = b"not a real docx fixture, just a binary target"
    revised_text = "Reviewer text that should not overwrite a binary artifact."
    output_dir.mkdir(parents=True)
    (output_dir / "draft_report.docx").write_bytes(original_bytes)
    run_intake = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "output_dir": str(output_dir),
    }
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "outputs": [{"path": "draft_report.docx", "kind": "docx", "status": "written"}],
        "status": "written_pending_review",
    }
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": apply_tool,
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "final_artifacts": final_artifacts,
                    "decisions": [
                        {
                            "item_id": "editable-1",
                            "action": "edit",
                            "edit_value": revised_text,
                        }
                    ],
                    "decision_source": "binary_edit_guard_test",
                },
            },
        }
    ]

    responses = {
        response["id"]: response for response in _call_mcp_server(plugin, messages)
    }

    apply_result = responses[1]["result"]["structuredContent"]
    assert apply_result["ok"] is True
    assert apply_result["application_status"] == "partial_review_applied"
    assert apply_result["revision_count"] == 1
    assert apply_result["target_update_count"] == 0
    assert apply_result["native_regeneration_count"] == 1
    assert (output_dir / "draft_report.docx").read_bytes() == original_bytes
    applied = json.loads(
        (output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    assert applied["application_status"] == "partial_review_applied"
    assert applied["native_regeneration_count"] == 1
    assert applied["native_regeneration_paths"] == ["draft_report.docx"]
    effect = applied["effects"][0]
    assert effect["artifact_update"] == "native_regeneration_pending"
    assert effect["requires_native_regeneration"] is True
    assert effect["native_regeneration_status"] == "pending"
    assert effect["revision_artifact"] == "revisions/draft_report__editable-1.txt"
    assert "original_artifact_backup" not in effect
    assert (output_dir / "revisions/draft_report__editable-1.txt").read_text(
        encoding="utf-8"
    ) == revised_text
    final = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    assert final["status"] == "partial_review_applied"
    assert final["review_application"]["native_regeneration_count"] == 1
    assert final["review_application"]["native_regeneration_paths"] == [
        "draft_report.docx"
    ]
    assert [
        output for output in final["outputs"] if output["path"] == "draft_report.docx"
    ] == [
        {
            "path": "draft_report.docx",
            "kind": "docx",
            "status": "native_regeneration_pending",
            "item_id": "editable-1",
            "revision_artifact": "revisions/draft_report__editable-1.txt",
        }
    ]
    assert (
        "Regenerate native DOCX/XLSX/PDF outputs before final handoff."
        in final["next_actions"]
    )


@pytest.mark.parametrize(
    ("plugin", "_save_tool", "apply_tool", "item_type"),
    GENERIC_PERSISTENCE_REVIEW_SAVE_TOOLS,
)
def test_non_plotting_review_apply_tools_update_csv_rows_when_target_contract_is_explicit(
    tmp_path: Path, plugin: str, _save_tool: str, apply_tool: str, item_type: str
) -> None:
    output_dir = tmp_path / plugin / "csv-edit"
    target_artifact = "native_results.csv"
    review_payload = _structured_edit_review_payload(
        plugin,
        item_type,
        target_artifact,
        "review_note",
    )
    original_csv = (
        "item_id,status,review_note\nstructured-1,pending,old\nother,pending,keep\n"
    )
    revised_note = 'Approved, "reviewed"'
    output_dir.mkdir(parents=True)
    (output_dir / target_artifact).write_text(original_csv, encoding="utf-8")
    run_intake = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "output_dir": str(output_dir),
    }
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "outputs": [{"path": target_artifact, "kind": "csv", "status": "written"}],
        "status": "written_pending_review",
    }
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": apply_tool,
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "final_artifacts": final_artifacts,
                    "decisions": [
                        {
                            "item_id": "structured-1",
                            "action": "edit",
                            "edit_value": revised_note,
                            "reviewer_note": "Update one native CSV cell.",
                        }
                    ],
                    "decision_source": "structured_csv_edit_test",
                    "reviewer": "pytest",
                },
            },
        }
    ]

    responses = {
        response["id"]: response for response in _call_mcp_server(plugin, messages)
    }

    apply_result = responses[1]["result"]["structuredContent"]
    assert apply_result["ok"] is True
    assert apply_result["revision_count"] == 1
    assert apply_result["target_update_count"] == 1
    assert apply_result["structured_update_count"] == 1
    assert (output_dir / target_artifact).read_text(encoding="utf-8") == (
        'item_id,status,review_note\nstructured-1,pending,"Approved, ""reviewed"""\n'
        "other,pending,keep\n"
    )
    assert (
        output_dir / "revisions/originals/native_results__structured-1.csv"
    ).read_text(encoding="utf-8") == original_csv

    applied = json.loads(
        (output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    effect = applied["effects"][0]
    assert effect["artifact_update"] == "structured_artifact_updated"
    assert effect["revision_artifact"] == "revisions/native_results__structured-1.txt"
    assert effect["original_artifact_backup"] == (
        "revisions/originals/native_results__structured-1.csv"
    )
    assert effect["structured_update"] == {
        "id_field": "item_id",
        "record_id": "structured-1",
        "target_field": "review_note",
        "records_key": None,
        "updated_rows": 1,
    }
    assert applied["structured_update_count"] == 1
    assert applied["structured_update_paths"] == [target_artifact]

    final = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    target_outputs = [
        output for output in final["outputs"] if output["path"] == target_artifact
    ]
    assert target_outputs == [
        {
            "path": target_artifact,
            "kind": "csv",
            "status": "updated_from_review",
            "item_id": "structured-1",
            "row_count": 2,
            "required_columns": ["item_id", "review_note"],
        }
    ]
    assert final["review_application"]["structured_update_count"] == 1
    assert final["review_application"]["structured_update_paths"] == [target_artifact]


def test_non_plotting_review_apply_tool_updates_json_records_when_target_contract_is_explicit(
    tmp_path: Path,
) -> None:
    plugin = "check-entries"
    apply_tool = "apply_check_entries_decisions"
    item_type = "supported_entry"
    output_dir = tmp_path / plugin / "json-edit"
    target_artifact = "native_results.json"
    review_payload = _structured_edit_review_payload(
        plugin,
        item_type,
        target_artifact,
        "review_note",
        records_key="results",
    )
    original_json = {
        "results": [
            {"item_id": "structured-1", "status": "pending", "review_note": "old"},
            {"item_id": "other", "status": "pending", "review_note": "keep"},
        ]
    }
    output_dir.mkdir(parents=True)
    (output_dir / target_artifact).write_text(
        json.dumps(original_json, indent=2) + "\n",
        encoding="utf-8",
    )
    run_intake = {
        "schema_version": "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": review_payload["run_id"],
        "output_dir": str(output_dir),
    }
    messages: list[dict[str, object]] = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": apply_tool,
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "final_artifacts": {
                        "schema_version": "1.0",
                        "plugin": plugin,
                        "workflow": plugin,
                        "run_id": review_payload["run_id"],
                        "outputs": [
                            {
                                "path": target_artifact,
                                "kind": "json",
                                "status": "written",
                                "records_key": "results",
                            }
                        ],
                        "status": "written_pending_review",
                    },
                    "decisions": [
                        {
                            "item_id": "structured-1",
                            "action": "edit",
                            "edit_value": "JSON reviewer note",
                        }
                    ],
                    "decision_source": "structured_json_edit_test",
                },
            },
        }
    ]

    responses = {
        response["id"]: response for response in _call_mcp_server(plugin, messages)
    }

    apply_result = responses[1]["result"]["structuredContent"]
    assert apply_result["ok"] is True
    assert apply_result["structured_update_count"] == 1
    updated_json = json.loads(
        (output_dir / target_artifact).read_text(encoding="utf-8")
    )
    assert updated_json == {
        "results": [
            {
                "item_id": "structured-1",
                "status": "pending",
                "review_note": "JSON reviewer note",
            },
            {"item_id": "other", "status": "pending", "review_note": "keep"},
        ]
    }
    applied = json.loads(
        (output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    assert applied["effects"][0]["structured_update"]["records_key"] == "results"
