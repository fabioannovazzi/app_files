from __future__ import annotations

import ast
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHARED_MODULES = ROOT / "plugins" / "_shared" / "vendor" / "modules"
if str(SHARED_MODULES) not in sys.path:
    sys.path.insert(0, str(SHARED_MODULES))

from vera_assurance import (  # noqa: E402
    VERA_CLIENT_WORKFLOW_IDS,
    AssuranceContractError,
    canonical_json_sha256,
    load_client_engagement_context_file,
    load_client_workflow_context_for_output,
)

CLIENT_WORKFLOW_ENTRYPOINTS = (
    ("archive-organization", "archive_organization.py"),
    ("open-item-reconciliation", "audit_assurance.py"),
    ("open-item-reconciliation", "build_missing_evidence_requests.py"),
    ("open-item-reconciliation", "build_review_sample.py"),
    ("open-item-reconciliation", "raw_input_runner.py"),
    ("client-file-preparation", "build_file_preparation_outputs.py"),
    ("client-file-preparation", "parse_fatturapa_xml.py"),
    ("client-file-preparation", "parse_fiscal_forms.py"),
    ("new-client", "initialize_case.py"),
    ("new-client", "promote_client_file_preparation.py"),
    ("new-client", "package_new_client.py"),
    ("new-client", "delivery_manifest.py"),
    ("journal-sampling", "inspect_journal.py"),
    ("journal-sampling", "normalize_journal.py"),
    ("journal-sampling", "replay_normalization.py"),
    ("journal-sampling", "review_successor.py"),
    ("journal-sampling", "run_sample.py"),
    ("check-entries", "inspect_entries.py"),
    ("check-entries", "run_checks.py"),
    ("journal-bank-reconciliation", "inspect_inputs.py"),
    ("journal-bank-reconciliation", "run_reconciliation.py"),
    ("journal-bank-reconciliation", "semantic_review.py"),
    ("passive-invoice-audit", "run_audit.py"),
    ("business-planning", "run_business_plan.py"),
    ("sales-plan", "prepare_sales_plan_case.py"),
    ("sales-plan", "run_plan.py"),
    ("variance-analysis", "inspect_inputs.py"),
    ("variance-analysis", "run_variance.py"),
    ("management-control-pack", "inspect_inputs.py"),
    ("management-control-pack", "run_pack.py"),
    ("management-control-pack", "finalize_pack.py"),
    ("centrale-rischi-review", "inspect_inputs.py"),
    ("centrale-rischi-review", "run_analysis.py"),
    ("centrale-rischi-review", "finalize_analysis.py"),
    ("financial-analysis", "run_pack.py"),
    ("financial-analysis", "validate_case_contracts.py"),
    ("financial-analysis", "prepare_customer_concentration_case.py"),
    ("financial-analysis", "prepare_fdd_case.py"),
    ("financial-analysis", "prepare_monthly_pnl_case.py"),
    ("financial-analysis", "prepare_working_capital_case.py"),
    ("report-builder", "inspect_inputs.py"),
    ("report-builder", "build_report.py"),
    ("report-builder", "review_numeric_measures.py"),
    ("report-builder", "apply_review_edits.py"),
    ("report-builder", "seal_review_integrity.py"),
    ("concordato-plan-review", "run_concordato_review.py"),
    ("concordato-plan-review", "review_case_model.py"),
    ("concordato-plan-review", "review_source_roles.py"),
    ("concordato-plan-review", "apply_review_edits.py"),
    ("concordato-plan-review", "replay_assurance.py"),
    ("concordato-plan-review", "finalize_output_closure.py"),
    ("prompt-optimizer", "inspect_question.py"),
    ("prompt-optimizer", "validate_prompt.py"),
    ("deep-research-validator", "inspect_document.py"),
    ("deep-research-validator", "inspect_sources.py"),
    ("deep-research-validator", "package_validation.py"),
    ("previdenza-inps", "register_portal_export.py"),
    ("previdenza-inps", "capture_portal_snapshot.py"),
    ("previdenza-inps", "inventory_case.py"),
    ("previdenza-inps", "validate_case_records.py"),
    ("previdenza-inps", "reconcile_contributions.py"),
    ("previdenza-inps", "package_case.py"),
    ("registro-imprese-sari", "initialize_case.py"),
    ("registro-imprese-sari", "inventory_case.py"),
    ("registro-imprese-sari", "register_official_source.py"),
    ("registro-imprese-sari", "sari_connector.py"),
    ("registro-imprese-sari", "validate_practice_case.py"),
    ("registro-imprese-sari", "package_practice.py"),
    ("bandi-agevolazioni", "initialize_case.py"),
    ("bandi-agevolazioni", "register_source.py"),
    ("bandi-agevolazioni", "link_sources.py"),
    ("bandi-agevolazioni", "record_review.py"),
    ("bandi-agevolazioni", "validate_application.py"),
    ("bandi-agevolazioni", "package_dossier.py"),
    ("bandi-agevolazioni", "intelligence_workflow.py"),
)

CLIENT_WORKFLOW_OUTPUT_DISCOVERY_WRITERS = (
    ("open-item-reconciliation", "review_server.py"),
    ("check-entries", "apply_review_edits.py"),
    ("journal-bank-reconciliation", "apply_review_edits.py"),
    ("passive-invoice-audit", "evaluate_audit.py"),
    ("prompt-optimizer", "apply_review_edits.py"),
    ("deep-research-validator", "apply_review_edits.py"),
    ("variance-analysis", "review_preflight.py"),
)

CLIENT_WORKFLOW_CLI_ALLOWLIST = (
    ("archive-organization", "check_dependencies.py"),
    ("open-item-reconciliation", "check_dependencies.py"),
    ("client-file-preparation", "check_dependencies.py"),
    ("client-file-preparation", "check_environment.py"),
    ("client-file-preparation", "managed_ocr_runtime.py"),
    ("client-file-preparation", "model_handoff.py"),
    ("new-client", "check_dependencies.py"),
    ("journal-sampling", "check_dependencies.py"),
    ("check-entries", "check_dependencies.py"),
    ("journal-bank-reconciliation", "check_dependencies.py"),
    ("passive-invoice-audit", "check_dependencies.py"),
    ("business-planning", "check_dependencies.py"),
    ("business-planning", "run_strategic_plan.py"),
    ("sales-plan", "check_dependencies.py"),
    ("sales-plan", "model_use.py"),
    ("variance-analysis", "check_dependencies.py"),
    ("variance-analysis", "inspect_column_values.py"),
    ("variance-analysis", "model_use.py"),
    ("management-control-pack", "check_dependencies.py"),
    ("centrale-rischi-review", "check_dependencies.py"),
    ("centrale-rischi-review", "evaluate_pdf_corpus.py"),
    ("centrale-rischi-review", "run_gold_benchmark.py"),
    ("financial-analysis", "check_dependencies.py"),
    ("financial-analysis", "model_use.py"),
    ("report-builder", "check_dependencies.py"),
    ("report-builder", "expand_model_context.py"),
    ("report-builder", "prepared_contract.py"),
    ("report-builder", "validate_review_integrity.py"),
    ("concordato-plan-review", "check_dependencies.py"),
    ("prompt-optimizer", "check_dependencies.py"),
    ("prompt-optimizer", "run_fiscalprompt_benchmark.py"),
    ("prompt-optimizer", "summarize_fiscalprompt_benchmark.py"),
    ("deep-research-validator", "check_dependencies.py"),
    ("previdenza-inps", "check_dependencies.py"),
    ("registro-imprese-sari", "check_dependencies.py"),
    ("bandi-agevolazioni", "check_dependencies.py"),
    ("bandi-agevolazioni", "evaluate_intelligence.py"),
    ("bandi-agevolazioni", "opportunity_radar.py"),
)

OUTPUT_DISCOVERY_REVIEW_WRITER_WORKFLOWS = (
    ("check-entries", "2.0", "review_artifact", "check_entries"),
    (
        "journal-bank-reconciliation",
        "1.0",
        "review_artifact",
        "journal_bank",
    ),
    ("prompt-optimizer", "1.0", "review_artifact", "prompt_optimizer"),
    (
        "deep-research-validator",
        "1.0",
        "validation_artifact",
        "deep_research",
    ),
)

PORTABLE_CONTEXT_REVIEW_MCP_WORKFLOWS = frozenset(
    {"prompt-optimizer", "deep-research-validator", "variance-analysis"}
)

DURABLE_REVIEW_MCP_WORKFLOWS = (
    *OUTPUT_DISCOVERY_REVIEW_WRITER_WORKFLOWS,
    ("report-builder", "1.0", "report_section", "report_builder"),
    (
        "concordato-plan-review",
        "1.0",
        "review_artifact",
        "concordato_plan",
    ),
    ("variance-analysis", "1.0", "variance_driver", "variance_analysis"),
)


def _has_main_guard(tree: ast.AST) -> bool:
    """Return whether a module has an executable ``__main__`` guard."""

    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            continue
        test = node.test
        if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
            continue
        if len(test.comparators) != 1:
            continue
        left, right = test.left, test.comparators[0]
        pairs = ((left, right), (right, left))
        if any(
            isinstance(name, ast.Name)
            and name.id == "__name__"
            and isinstance(value, ast.Constant)
            and value.value == "__main__"
            for name, value in pairs
        ):
            return True
    return False


def _load_customer_ledger() -> ModuleType:
    path = ROOT / "plugins" / "studio-archive" / "scripts" / "client_ledger.py"
    module_name = "test_vera_workflow_customer_ledger"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _running_context(
    tmp_path: Path,
    workflow_id: str,
) -> tuple[Path, Path, Path, str]:
    ledger = _load_customer_ledger()
    client_root = tmp_path / "Customer"
    client_root.mkdir()
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client_root, client_id)
    engagement = ledger.create_engagement(client_root, client_id, "Test engagement")
    source = tmp_path / "source.txt"
    source.write_text("exact input\n", encoding="utf-8")
    imported = ledger.import_document(
        client_root,
        client_id,
        engagement["engagement_id"],
        source,
        "source",
    )
    prepared = ledger.prepare_run(
        client_root,
        client_id,
        engagement["engagement_id"],
        workflow_id,
        "test-version",
        input_ids=[imported["receipt"]["input_id"]],
    )
    running = ledger.start_run(
        client_root,
        engagement["engagement_id"],
        prepared["run"]["run_id"],
    )
    return (
        Path(running["context_path"]),
        Path(running["context"]["input_bindings"][0]["path"]),
        Path(running["output_dir"]),
        str(running["context"]["run_id"]),
    )


def _completed_context(
    tmp_path: Path,
    workflow_id: str,
) -> tuple[Path, Path, Path, str]:
    ledger = _load_customer_ledger()
    context_path, input_path, output_dir, run_id = _running_context(
        tmp_path,
        workflow_id,
    )
    context = json.loads(context_path.read_text(encoding="utf-8"))
    artifact = output_dir / "result.txt"
    artifact.write_text("reviewable result\n", encoding="utf-8")
    client_root = context_path.parents[5]
    ledger.finalize_run(
        client_root,
        context["engagement_id"],
        run_id,
        [
            {
                "artifact_id": "prepared.result",
                "path": artifact.name,
                "purpose": "Provide the finalized workflow result.",
                "audience": "review",
                "media_type": "text/plain",
            }
        ],
    )
    ledger.complete_run(client_root, context["engagement_id"], run_id)
    return context_path, input_path, output_dir, run_id


def _review_payload(
    workflow_id: str,
    schema_version: str,
    item_type: str,
    run_id: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": schema_version,
        "plugin": workflow_id,
        "workflow": workflow_id,
        "run_id": run_id,
        "items": [
            {
                "id": "review-item-1",
                "item_type": item_type,
                "title": "Review item",
                "allowed_actions": ["accept"],
                "recommended_action": "accept",
                "status": "needs_review",
            }
        ],
        "item_count": 1,
    }
    if workflow_id == "concordato-plan-review":
        payload["assurance"] = {"final_ready": False}
    if workflow_id in {"check-entries", "concordato-plan-review"}:
        payload["content_sha256"] = canonical_json_sha256(payload)
    return payload


def _call_review_tool(
    workflow_id: str,
    tool_name: str,
    arguments: dict[str, object],
) -> dict[str, object]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for MCP review persistence checks")
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    completed = subprocess.run(
        [node, str(ROOT / "plugins" / workflow_id / "mcp" / "server.cjs")],
        input=json.dumps(request) + "\n",
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    responses = [
        json.loads(line)
        for line in completed.stdout.splitlines()
        if line.strip().startswith("{")
    ]
    assert responses
    return responses[-1]["result"]["structuredContent"]


def test_client_workflow_entrypoints_cover_registered_vera_workflows() -> None:
    observed_workflows = {workflow_id for workflow_id, _ in CLIENT_WORKFLOW_ENTRYPOINTS}

    assert observed_workflows == set(VERA_CLIENT_WORKFLOW_IDS)


def test_client_workflow_registry_covers_every_vera_component() -> None:
    components = json.loads(
        (ROOT / "plugins" / "vera" / "components.json").read_text(encoding="utf-8")
    )

    assert set(VERA_CLIENT_WORKFLOW_IDS) == set(components["plugins"]) - {
        "bilancio-xbrl-it",
        "browser-automation",
        "comunicazione-professionale",
        "presenza-digitale-studio",
        "studio-archive",
    }


def test_every_workflow_python_cli_has_exactly_one_lifecycle_classification() -> None:
    classifications = (
        set(CLIENT_WORKFLOW_ENTRYPOINTS),
        set(CLIENT_WORKFLOW_OUTPUT_DISCOVERY_WRITERS),
        set(CLIENT_WORKFLOW_CLI_ALLOWLIST),
    )
    classified = set().union(*classifications)
    discovered: set[tuple[str, str]] = set()
    for workflow_id in VERA_CLIENT_WORKFLOW_IDS:
        for script_path in sorted(
            (ROOT / "plugins" / workflow_id / "scripts").glob("*.py")
        ):
            tree = ast.parse(
                script_path.read_text(encoding="utf-8"),
                filename=str(script_path),
            )
            if _has_main_guard(tree):
                discovered.add((workflow_id, script_path.name))

    classification_counts = {
        entry: sum(entry in group for group in classifications)
        for entry in discovered | classified
    }

    assert discovered == classified
    assert set(classification_counts.values()) == {1}


def test_every_durable_review_mcp_has_exact_customer_run_preflight_marker() -> None:
    durable_servers: dict[str, str] = {}
    for workflow_id in VERA_CLIENT_WORKFLOW_IDS:
        server_path = ROOT / "plugins" / workflow_id / "mcp" / "server.cjs"
        if not server_path.is_file():
            continue
        source = server_path.read_text(encoding="utf-8")
        if "saveDecisions:" in source and "ui_decisions.json" in source:
            durable_servers[workflow_id] = source

    assert durable_servers
    exact_id_comparison = re.compile(
        r"(?:"
        r"(?:result|parsed)\.(?:run_id|client_run_id)\s*!==\s*expectedRunId"
        r"|authority\.run_id\s*!==\s*boundary\.run_id"
        r")"
    )
    for workflow_id, source in durable_servers.items():
        preflight_markers = (
            '"--client-run-preflight-only"' in source,
            "load_client_workflow_context_for_output" in source,
            "auditReviewRequireMatchingCustomerRun" in source,
            "requireMatchingJournalCustomerRun" in source,
        )
        assert sum(preflight_markers) == 1, workflow_id
        assert exact_id_comparison.search(source), workflow_id


@pytest.mark.parametrize("workflow_id", VERA_CLIENT_WORKFLOW_IDS)
def test_registered_workflow_loads_one_running_customer_folder_run(
    tmp_path: Path,
    workflow_id: str,
) -> None:
    context_path, input_path, output_dir, _ = _running_context(tmp_path, workflow_id)

    context = load_client_engagement_context_file(
        context_path,
        expected_workflow_id=workflow_id,
        input_paths=[input_path],
        output_dir=output_dir,
    )

    assert context["schema_version"] == "vera.client_workflow_context.v2"
    assert context["workflow_id"] == workflow_id
    assert Path(context["output_dir"]) == output_dir


def test_customer_folder_run_rejects_an_unreceipted_input(tmp_path: Path) -> None:
    context_path, _, output_dir, _ = _running_context(tmp_path, "financial-analysis")
    unreceipted = tmp_path / "unreceipted.txt"
    unreceipted.write_text("not selected\n", encoding="utf-8")

    with pytest.raises(AssuranceContractError, match="not one of"):
        load_client_engagement_context_file(
            context_path,
            expected_workflow_id="financial-analysis",
            input_paths=[unreceipted],
            output_dir=output_dir,
        )


def test_customer_folder_run_rejects_an_external_output(tmp_path: Path) -> None:
    context_path, input_path, _, _ = _running_context(tmp_path, "financial-analysis")

    with pytest.raises(AssuranceContractError, match="outside"):
        load_client_engagement_context_file(
            context_path,
            expected_workflow_id="financial-analysis",
            input_paths=[input_path],
            output_dir=tmp_path / "external-output",
        )


def test_completed_customer_folder_run_allows_explicit_read_only_hydration(
    tmp_path: Path,
) -> None:
    context_path, input_path, _, _ = _completed_context(
        tmp_path,
        "journal-sampling",
    )

    context = load_client_engagement_context_file(
        context_path,
        expected_workflow_id="journal-sampling",
        input_paths=[input_path],
        allowed_statuses=("ready_for_review", "completed"),
    )

    assert context["schema_version"] == "vera.client_workflow_context.v2"
    assert context["workflow_id"] == "journal-sampling"


def test_closed_engagement_retains_completed_run_read_only_hydration(
    tmp_path: Path,
) -> None:
    ledger = _load_customer_ledger()
    context_path, input_path, output_dir, _ = _completed_context(
        tmp_path,
        "journal-sampling",
    )
    portable = json.loads(context_path.read_text(encoding="utf-8"))
    ledger.close_engagement(
        context_path.parents[5],
        portable["engagement_id"],
    )

    context = load_client_engagement_context_file(
        context_path,
        expected_workflow_id="journal-sampling",
        input_paths=[input_path],
        output_dir=output_dir,
        allowed_statuses=("completed",),
    )

    assert context["schema_version"] == "vera.client_workflow_context.v2"
    assert context["workflow_id"] == "journal-sampling"
    assert Path(context["output_dir"]) == output_dir


def test_completed_customer_folder_run_rejects_default_writer_loader(
    tmp_path: Path,
) -> None:
    _, _, output_dir, _ = _completed_context(tmp_path, "journal-sampling")

    with pytest.raises(AssuranceContractError, match="running state"):
        load_client_workflow_context_for_output(
            output_dir / "late-write.json",
            expected_workflow_id="journal-sampling",
        )


def test_secondary_writer_recovers_context_after_customer_folder_rename(
    tmp_path: Path,
) -> None:
    context_path, _, output_dir, _ = _running_context(tmp_path, "financial-analysis")
    original_client_root = context_path.parents[5]
    renamed_client_root = original_client_root.with_name("Renamed Customer")
    original_client_root.rename(renamed_client_root)
    renamed_output = renamed_client_root / output_dir.relative_to(original_client_root)

    context = load_client_workflow_context_for_output(
        renamed_output / "review",
        expected_workflow_id="financial-analysis",
    )

    assert Path(context["output_dir"]) == renamed_output
    assert Path(context["context_path"]) == (
        renamed_client_root / context_path.relative_to(original_client_root)
    )


def test_secondary_writer_rejects_output_without_customer_run(tmp_path: Path) -> None:
    external = tmp_path / "external" / "review"

    with pytest.raises(AssuranceContractError, match="portable customer-folder"):
        load_client_workflow_context_for_output(
            external,
            expected_workflow_id="financial-analysis",
        )


@pytest.mark.parametrize(
    ("workflow_id", "schema_version", "item_type", "tool_prefix"),
    OUTPUT_DISCOVERY_REVIEW_WRITER_WORKFLOWS,
)
def test_review_writer_preflight_accepts_exact_running_customer_run(
    tmp_path: Path,
    workflow_id: str,
    schema_version: str,
    item_type: str,
    tool_prefix: str,
) -> None:
    del schema_version, item_type, tool_prefix
    _, _, output_dir, _ = _running_context(tmp_path, workflow_id)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "plugins" / workflow_id / "scripts" / "apply_review_edits.py"),
            "--output-dir",
            str(output_dir),
            "--client-run-preflight-only",
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "vera.client_workflow_context.v2"
    assert payload["workflow_id"] == workflow_id
    assert list(output_dir.iterdir()) == []


@pytest.mark.parametrize(
    ("workflow_id", "schema_version", "item_type", "tool_prefix"),
    OUTPUT_DISCOVERY_REVIEW_WRITER_WORKFLOWS,
)
def test_review_writer_preflight_rejects_unmanaged_output_without_writing(
    tmp_path: Path,
    workflow_id: str,
    schema_version: str,
    item_type: str,
    tool_prefix: str,
) -> None:
    del schema_version, item_type, tool_prefix
    unmanaged = tmp_path / "unmanaged"
    unmanaged.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "plugins" / workflow_id / "scripts" / "apply_review_edits.py"),
            "--output-dir",
            str(unmanaged),
            "--client-run-preflight-only",
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode != 0
    assert "portable customer-folder run" in result.stderr
    assert list(unmanaged.iterdir()) == []


@pytest.mark.parametrize(
    ("workflow_id", "schema_version", "item_type", "tool_prefix"),
    OUTPUT_DISCOVERY_REVIEW_WRITER_WORKFLOWS,
)
def test_review_mcp_save_persists_only_in_running_customer_run(
    tmp_path: Path,
    workflow_id: str,
    schema_version: str,
    item_type: str,
    tool_prefix: str,
) -> None:
    context_path, _, output_dir, client_run_id = _running_context(tmp_path, workflow_id)
    review_payload = _review_payload(
        workflow_id,
        schema_version,
        item_type,
        client_run_id,
    )
    run_intake = {
        "schema_version": schema_version,
        "plugin": workflow_id,
        "workflow": workflow_id,
        "run_id": review_payload["run_id"],
        "output_dir": str(output_dir),
    }
    arguments: dict[str, object] = {
        "run_intake": run_intake,
        "review_payload": review_payload,
        "decisions": [{"item_id": "review-item-1", "action": "accept"}],
    }
    if workflow_id in PORTABLE_CONTEXT_REVIEW_MCP_WORKFLOWS:
        run_intake["path_reference"] = "run_root_relative"
        run_intake["output_dir"] = output_dir.relative_to(
            context_path.parent
        ).as_posix()
        arguments["client_engagement"] = context_path.as_posix()

    result = _call_review_tool(
        workflow_id,
        f"save_{tool_prefix}_decisions",
        arguments,
    )

    assert result["ok"] is True
    assert result["persisted"] is True
    assert (output_dir / "ui_decisions.json").is_file()


@pytest.mark.parametrize(
    ("workflow_id", "schema_version", "item_type", "tool_prefix"),
    OUTPUT_DISCOVERY_REVIEW_WRITER_WORKFLOWS,
)
def test_review_mcp_save_and_apply_reject_unmanaged_output_before_writing(
    tmp_path: Path,
    workflow_id: str,
    schema_version: str,
    item_type: str,
    tool_prefix: str,
) -> None:
    context_path: Path | None = None
    managed_output: Path | None = None
    if workflow_id in PORTABLE_CONTEXT_REVIEW_MCP_WORKFLOWS:
        context_path, _, managed_output, _ = _running_context(tmp_path, workflow_id)
        unmanaged = managed_output.parent / "unmanaged"
    else:
        unmanaged = tmp_path / "unmanaged"
    unmanaged.mkdir()
    review_payload = _review_payload(
        workflow_id,
        schema_version,
        item_type,
        "review-test-run",
    )
    base_arguments: dict[str, object] = {
        "run_intake": {
            "schema_version": schema_version,
            "plugin": workflow_id,
            "workflow": workflow_id,
            "run_id": review_payload["run_id"],
            "output_dir": str(unmanaged),
        },
        "review_payload": review_payload,
        "decisions": [{"item_id": "review-item-1", "action": "accept"}],
    }
    if context_path is not None:
        run_intake = base_arguments["run_intake"]
        assert isinstance(run_intake, dict)
        run_intake["path_reference"] = "run_root_relative"
        run_intake["output_dir"] = unmanaged.relative_to(context_path.parent).as_posix()
        base_arguments["client_engagement"] = context_path.as_posix()
    save_result = _call_review_tool(
        workflow_id,
        f"save_{tool_prefix}_decisions",
        base_arguments,
    )
    apply_result = _call_review_tool(
        workflow_id,
        f"apply_{tool_prefix}_decisions",
        {
            **base_arguments,
            "final_artifacts": {
                "schema_version": schema_version,
                "plugin": workflow_id,
                "workflow": workflow_id,
                "run_id": review_payload["run_id"],
                "outputs": [],
                "next_actions": [],
                "status": "written_pending_review",
            },
        },
    )

    assert save_result["ok"] is False
    assert apply_result["ok"] is False
    assert list(unmanaged.iterdir()) == []
    if managed_output is not None:
        assert list(managed_output.iterdir()) == []


@pytest.mark.parametrize(
    ("workflow_id", "schema_version", "item_type", "tool_prefix"),
    DURABLE_REVIEW_MCP_WORKFLOWS,
)
@pytest.mark.parametrize("action", ("save", "apply"))
def test_review_mcp_rejects_a_different_customer_run_id_before_writing(
    tmp_path: Path,
    workflow_id: str,
    schema_version: str,
    item_type: str,
    tool_prefix: str,
    action: str,
) -> None:
    context_path, _, output_dir, client_run_id = _running_context(tmp_path, workflow_id)
    mismatched_run_id = "run_" + "f" * 24
    assert mismatched_run_id != client_run_id
    review_payload = _review_payload(
        workflow_id,
        schema_version,
        item_type,
        mismatched_run_id,
    )
    arguments: dict[str, object] = {
        "run_intake": {
            "schema_version": schema_version,
            "plugin": workflow_id,
            "workflow": workflow_id,
            "run_id": mismatched_run_id,
            "output_dir": str(output_dir),
        },
        "review_payload": review_payload,
        "decisions": [{"item_id": "review-item-1", "action": "accept"}],
    }
    if workflow_id in PORTABLE_CONTEXT_REVIEW_MCP_WORKFLOWS:
        run_intake = arguments["run_intake"]
        assert isinstance(run_intake, dict)
        run_intake["path_reference"] = "run_root_relative"
        run_intake["output_dir"] = output_dir.relative_to(
            context_path.parent
        ).as_posix()
        arguments["client_engagement"] = context_path.as_posix()
    if action == "apply":
        arguments["final_artifacts"] = {
            "schema_version": schema_version,
            "plugin": workflow_id,
            "workflow": workflow_id,
            "run_id": mismatched_run_id,
            "outputs": [],
            "next_actions": [],
            "status": "written_pending_review",
        }

    result = _call_review_tool(
        workflow_id,
        f"{action}_{tool_prefix}_decisions",
        arguments,
    )

    assert result["ok"] is False
    assert list(output_dir.iterdir()) == []


def test_secondary_writer_rejects_an_intermediate_output_symlink(
    tmp_path: Path,
) -> None:
    _, _, output_dir, _ = _running_context(tmp_path, "financial-analysis")
    actual = output_dir / "actual"
    review = actual / "review"
    review.mkdir(parents=True)
    alias = output_dir / "alias"
    alias.symlink_to(actual, target_is_directory=True)

    with pytest.raises(AssuranceContractError, match="symbolic link"):
        load_client_workflow_context_for_output(
            alias / "review",
            expected_workflow_id="financial-analysis",
        )


def test_previdenza_run_resumes_after_customer_folder_rename(tmp_path: Path) -> None:
    context_path, input_path, output_dir, _ = _running_context(
        tmp_path,
        "previdenza-inps",
    )
    inventory_result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "plugins" / "previdenza-inps" / "scripts" / "inventory_case.py"),
            str(input_path.parent),
            "--output-dir",
            str(output_dir),
            "--client-engagement",
            str(context_path),
            "--no-ocr",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    original_client_root = context_path.parents[5]
    original_root_text = original_client_root.as_posix()
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    file_inventory = json.loads(
        (output_dir / "file_inventory.json").read_text(encoding="utf-8")
    )
    assert inventory_result.returncode == 0, inventory_result.stderr
    assert run_intake["output_dir"] == "outputs"
    assert run_intake["path_reference"] == "run_root_relative"
    assert original_root_text not in json.dumps(run_intake)
    assert original_root_text not in json.dumps(file_inventory)

    renamed_client_root = original_client_root.with_name("Renamed Previdenza Client")
    original_client_root.rename(renamed_client_root)
    renamed_context = renamed_client_root / context_path.relative_to(
        original_client_root
    )
    renamed_output = renamed_client_root / output_dir.relative_to(original_client_root)
    records = renamed_output / "case_records_for_package.json"
    claims = renamed_output / "claims_for_package.json"
    records.write_text("{}\n", encoding="utf-8")
    claims.write_text('{"claims": []}\n', encoding="utf-8")
    package_result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "plugins" / "previdenza-inps" / "scripts" / "package_case.py"),
            str(records),
            str(claims),
            "--output-dir",
            str(renamed_output),
            "--client-engagement",
            str(renamed_context),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert package_result.returncode == 1
    assert (renamed_output / "final_artifacts.json").is_file()
    resumed_intake = json.loads(
        (renamed_output / "run_intake.json").read_text(encoding="utf-8")
    )
    assert resumed_intake["run_id"] == run_intake["run_id"]
    assert resumed_intake["output_dir"] == "outputs"


@pytest.mark.parametrize(
    ("workflow_id", "script_name"),
    CLIENT_WORKFLOW_ENTRYPOINTS,
)
def test_client_workflow_entrypoint_requires_managed_context(
    workflow_id: str,
    script_name: str,
) -> None:
    plugin_root = ROOT / "plugins" / workflow_id
    script_path = plugin_root / "scripts" / script_name
    if workflow_id == "business-planning":
        # This owner delegates parsing to the shared CLI. Test the public boundary
        # instead of requiring its argparse declaration to be physically inline.
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--case",
                "missing.json",
                "--output-dir",
                "missing-output",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2
        assert "required: --client-engagement" in result.stderr
        return
    tree = ast.parse(script_path.read_text(encoding="utf-8"), filename=str(script_path))
    declarations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        and any(
            isinstance(argument, ast.Constant)
            and argument.value == "--client-engagement"
            for argument in node.args
        )
    ]

    assert len(declarations) == 1
    required = next(
        (
            keyword.value
            for keyword in declarations[0].keywords
            if keyword.arg == "required"
        ),
        None,
    )
    assert isinstance(required, ast.Constant)
    expected_required = workflow_id != "variance-analysis"
    assert required.value is expected_required
    loader_names = {
        "load_client_engagement_context",
        "load_client_engagement_context_file",
        "load_running_context",
        "load_running_case_context",
    }
    loader_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name)
            and node.func.id in loader_names
            or isinstance(node.func, ast.Attribute)
            and node.func.attr in loader_names
        )
    ]
    assert loader_calls


@pytest.mark.parametrize(
    ("workflow_id", "script_name"),
    CLIENT_WORKFLOW_OUTPUT_DISCOVERY_WRITERS,
)
def test_output_discovery_writer_loads_customer_run_from_its_output(
    workflow_id: str,
    script_name: str,
) -> None:
    script_path = ROOT / "plugins" / workflow_id / "scripts" / script_name
    tree = ast.parse(
        script_path.read_text(encoding="utf-8"),
        filename=str(script_path),
    )
    loader_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name)
            and node.func.id == "load_client_workflow_context_for_output"
            or isinstance(node.func, ast.Attribute)
            and node.func.attr == "load_client_workflow_context_for_output"
        )
    ]

    assert loader_calls
