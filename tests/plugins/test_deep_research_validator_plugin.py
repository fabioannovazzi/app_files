from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from docx import Document

from scripts.validate_plugin_review_contract import validate_contract

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "deep-research-validator"
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
MCP_SERVER_PATH = PLUGIN_ROOT / "mcp" / "server.cjs"
FREE_PACK_LINK = "/downloads/vera"


def load_script(module_name: str, script_name: str):
    script_path = SCRIPTS_DIR / script_name
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def _call_mcp_server(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip(
            "Node.js is required to exercise the Deep Research Validator MCP server."
        )
    completed = subprocess.run(
        [node, str(MCP_SERVER_PATH), "--stdio"],
        input="\n".join(json.dumps(message) for message in messages) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def _write_docx(path: Path, paragraphs: list[str]) -> None:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(path)


def _docx_text(path: Path) -> str:
    document = Document(path)
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def test_inspect_document_extracts_references_and_claim_candidates(
    tmp_path: Path,
) -> None:
    inspect_mod = load_script(
        "deep_research_validator_inspect_document",
        "inspect_document.py",
    )
    document = tmp_path / "report.md"
    document.write_text(
        "\n".join(
            [
                "# VAT report",
                "The Italian VAT rule applies to the transaction [1].",
                "The conclusion is supported by [Agenzia](https://example.com/source).",
                "[^1]: https://example.com/source",
            ]
        ),
        encoding="utf-8",
    )

    paths = inspect_mod.write_inspection(document, tmp_path / "out")
    inventory = json.loads(paths["document_inventory"].read_text(encoding="utf-8"))

    assert inventory["source_name"] == "report.md"
    assert inventory["headings"] == ["VAT report"]
    assert inventory["urls"] == ["https://example.com/source"]
    assert inventory["markdown_links"][0]["label"] == "Agenzia"
    assert inventory["footnotes"][0]["id"] == "1"
    assert inventory["mechanical_claim_candidates"]


def test_inspect_sources_can_skip_network_fetch(tmp_path: Path) -> None:
    inspect_sources = load_script(
        "deep_research_validator_inspect_sources",
        "inspect_sources.py",
    )
    inventory = tmp_path / "document_inventory.json"
    inventory.write_text(
        json.dumps(
            {"urls": ["https://example.com/a"], "footnotes": [], "markdown_links": []}
        ),
        encoding="utf-8",
    )

    paths = inspect_sources.write_source_inventory(
        inventory,
        tmp_path / "out",
        fetch_urls=False,
    )
    payload = json.loads(paths["source_inventory"].read_text(encoding="utf-8"))

    assert payload["url_count"] == 1
    assert payload["sources"][0]["status"] == "listed_not_fetched"


def test_package_validation_writes_audit_and_package(tmp_path: Path) -> None:
    package_mod = load_script(
        "deep_research_validator_package_validation",
        "package_validation.py",
    )
    document_inventory = tmp_path / "document_inventory.json"
    source_inventory = tmp_path / "source_inventory.json"
    claims_review = tmp_path / "claims_review_draft.json"
    document_inventory.write_text(
        json.dumps(
            {"character_count": 80, "word_count": 12, "urls": ["https://example.com"]}
        ),
        encoding="utf-8",
    )
    source_inventory.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "kind": "url",
                        "url": "https://example.com",
                        "status": "available",
                        "excerpt": "The Italian VAT rule applies to the transaction.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    claims_review.write_text(
        json.dumps(
            {
                "language": "en",
                "claims": [
                    {
                        "claim_index": 1,
                        "claim_text": "The Italian VAT rule applies to the transaction.",
                        "verdict": "supported",
                        "source_refs": ["https://example.com"],
                        "source_quote": "The Italian VAT rule applies",
                        "source_support": "The source directly supports the claim.",
                        "reasoning_review": "The inference is direct.",
                        "proposed_fix": "",
                    }
                ],
                "validated_document": "Validated text.",
            }
        ),
        encoding="utf-8",
    )

    paths = package_mod.write_validation_package(
        document_inventory,
        source_inventory,
        claims_review,
        tmp_path / "out",
    )
    audit = json.loads(paths["validation_audit"].read_text(encoding="utf-8"))
    run_intake = json.loads(
        (tmp_path / "out" / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (tmp_path / "out" / "review_payload.json").read_text(encoding="utf-8")
    )
    ui_decisions = json.loads(
        (tmp_path / "out" / "ui_decisions.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (tmp_path / "out" / "final_artifacts.json").read_text(encoding="utf-8")
    )

    assert audit["status"] == "pass"
    assert audit["review_session"]["run_id"] == run_intake["run_id"]
    assert audit["quote_matches"] == [{"claim_index": 1, "matched": True}]
    assert (
        paths["validated_document"].read_text(encoding="utf-8").strip()
        == "Validated text."
    )
    assert "Deep Research Validation Package" in paths["validation_package"].read_text(
        encoding="utf-8"
    )
    assert review_payload["plugin"] == "deep-research-validator"
    assert review_payload["run_id"] == run_intake["run_id"]
    assert review_payload["review_type"] == "deep_research_validation_review"
    assert review_payload["item_count"] == len(review_payload["items"])
    item_types = {item["item_type"] for item in review_payload["items"]}
    assert {"supported_claim", "validation_artifact"} <= item_types
    claim_item = next(
        item
        for item in review_payload["items"]
        if item["item_type"] == "supported_claim"
    )
    claim_evidence = claim_item["evidence"][0]
    assert claim_evidence["kind"] == "claim_vs_citation"
    assert claim_evidence["claim_text"] == (
        "The Italian VAT rule applies to the transaction."
    )
    assert claim_evidence["source_quote"] == "The Italian VAT rule applies"
    assert claim_evidence["source_support"] == (
        "The source directly supports the claim."
    )
    assert claim_item["data"]["target_artifact"] == "claims_review.json"
    assert claim_item["data"]["target_records_key"] == "claims"
    assert claim_item["data"]["target_id_field"] == "claim_index"
    assert claim_item["data"]["target_record_id"] == "1"
    assert claim_item["data"]["target_field"] == "proposed_fix"
    assert review_payload["summary"]["audit_status"] == "pass"
    assert ui_decisions["status"] == "pending_review"
    assert final_artifacts["status"] == "written_pending_review"
    handoff_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "review_handoff.md"
    )
    handoff_text = (tmp_path / "out" / "review_handoff.md").read_text(encoding="utf-8")
    assert handoff_output["required_text"] == [
        "Review Handoff",
        "review_payload.json",
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
    ]
    assert "render_deep_research_review" in handoff_text
    assert "apply_deep_research_decisions" in handoff_text
    package_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "validation_package.md"
    )
    assert package_output["required_text"] == [
        "# Deep Research Validation Package",
        "## Document Inventory",
        "## Claims Review",
    ]
    contract_report = validate_contract(
        tmp_path / "out",
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert contract_report.ok, contract_report.as_dict()


def test_package_validation_flags_missing_review_fields(tmp_path: Path) -> None:
    package_mod = load_script(
        "deep_research_validator_package_validation_missing",
        "package_validation.py",
    )
    document_inventory = {"character_count": 0, "urls": []}
    source_inventory = {"sources": []}
    claims_review = {"claims": [{"claim_index": 1, "claim_text": "", "verdict": "bad"}]}

    audit = package_mod.build_audit(document_inventory, source_inventory, claims_review)

    assert audit["status"] == "fail"
    assert "document_text_present" in audit["failed_checks"]
    assert "valid_verdicts" in audit["failed_checks"]
    assert "claim_text_present" in audit["failed_checks"]
    assert "review_text_present" in audit["failed_checks"]


def test_static_page_and_skill_match_plugin_contract() -> None:
    page = (
        ROOT / "static" / "shared" / "deep-research-validator" / "index.html"
    ).read_text(encoding="utf-8")
    skill = (PLUGIN_ROOT / "skills" / "deep-research-validator" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    for snippet in (
        "Validate Deep Research",
        "Valida Deep Research",
        "Valider Deep Research",
        "Deep Research validieren",
        "Prompt ready",
        "Prompt pronti",
        "document_inventory.json",
        "source_inventory.json",
        "claims_review.json",
        "validation_audit.json",
        "validated_document.md",
        "validation_package.md",
        FREE_PACK_LINK,
        "Un unico ZIP installa Vera con tutti i suoi undici moduli",
        "/?lang=${lang}",
    ):
        assert snippet in page

    assert "must not make direct OpenAI API calls" in skill
    assert "Keep the improvement note local to chat or run artifacts." in skill
    assert "validate_deep_research_review" in skill
    assert "render_deep_research_review" in skill


def test_deep_research_mcp_server_validates_renders_and_applies_review_payload(
    tmp_path: Path,
) -> None:
    document_inventory_path = tmp_path / "document_inventory.json"
    document_inventory_path.write_text(
        json.dumps(
            {
                "source_name": "deep_research.md",
                "character_count": 128,
                "word_count": 20,
                "urls": ["https://example.com"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    source_inventory_path = tmp_path / "source_inventory.json"
    source_inventory_path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "url": "https://example.com",
                        "title": "Example source",
                        "excerpt": "VAT rule applies in the cited transaction.",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    claims_review_path = tmp_path / "claims_review.json"
    claims_review_path.write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "claim_index": 1,
                        "claim_text": "VAT rule applies.",
                        "verdict": "supported",
                        "source_refs": ["https://example.com"],
                        "source_quote": "VAT rule applies",
                        "source_support": "Directly supported.",
                        "reasoning_review": "The cited source matches.",
                        "proposed_fix": "",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "validation_audit.json").write_text(
        json.dumps({"status": "pass", "claim_count": 1, "source_count": 1}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "validation_package.md").write_text(
        "\n".join(
            [
                "# Deep Research Validation Package",
                "",
                "## Document Inventory",
                "",
                "## Claims Review",
                "",
                "Proposed fix:",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _write_docx(
        tmp_path / "validated_document.docx",
        ["# Deep Research Validation Package", "Original proposed fix."],
    )
    run_intake = {
        "schema_version": "1.0",
        "plugin": "deep-research-validator",
        "workflow": "deep-research-validator",
        "run_id": "deep-research-test-run",
        "created_at": "2026-01-01T00:00:00Z",
        "language": "en",
        "input_paths": [
            "document_inventory.json",
            "source_inventory.json",
            "claims_review.json",
        ],
        "output_dir": tmp_path.as_posix(),
        "inferred_task": "deep_research_validation_review_payload",
        "assumptions": {},
        "unresolved_questions": [],
        "dependency_check": {"status": "not_run"},
        "data_posture": {
            "local_files_read": [
                "document_inventory.json",
                "source_inventory.json",
                "claims_review.json",
            ],
            "model_excerpts_sent": [],
            "external_connectors_used": [],
            "upload_paths_used": [],
            "remote_sql_execution_used": False,
            "hosted_notebook_execution_used": False,
        },
    }
    review_payload = {
        "schema_version": "1.0",
        "plugin": "deep-research-validator",
        "workflow": "deep-research-validator",
        "run_id": "deep-research-test-run",
        "source_paths": [
            "document_inventory.json",
            "source_inventory.json",
            "claims_review.json",
        ],
        "review_type": "deep_research_validation_review",
        "items": [
            {
                "id": "claim-1",
                "item_type": "supported_claim",
                "title": "Claim 1: VAT rule applies.",
                "output_path": "claims_review.json",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [
                    {
                        "kind": "claim_review",
                        "claim_text": "VAT rule applies.",
                        "verdict": "supported",
                        "source_refs": ["https://example.com"],
                        "source_quote": "VAT rule applies",
                        "source_support": "Directly supported.",
                    }
                ],
                "data": {
                    "claim_index": 1,
                    "claim_text": "VAT rule applies.",
                    "verdict": "supported",
                    "target_artifact": "claims_review.json",
                    "target_records_key": "claims",
                    "target_id_field": "claim_index",
                    "target_record_id": "1",
                    "target_field": "proposed_fix",
                },
                "status": "needs_review",
            },
            {
                "id": "source-limit-1",
                "item_type": "source_limit",
                "title": "https://example.com/source",
                "output_path": "source_inventory.json",
                "allowed_actions": [
                    "accept",
                    "edit",
                    "mark_unclear",
                    "request_more_documents",
                    "skip",
                ],
                "recommended_action": "request_more_documents",
                "evidence": [
                    {
                        "kind": "source_availability",
                        "status": "listed_not_fetched",
                    }
                ],
                "data": {"status": "listed_not_fetched"},
                "status": "needs_review",
            },
        ],
        "item_count": 2,
        "columns": [],
        "evidence": {},
        "allowed_actions": [
            "accept",
            "reject",
            "edit",
            "mark_unclear",
            "request_more_documents",
            "skip",
        ],
        "status": "ready_for_review",
        "summary": {
            "audit_status": "pass",
            "claim_count": 1,
            "attention_claim_count": 0,
            "source_count": 1,
            "failed_check_count": 0,
        },
    }
    ui_decisions = {
        "schema_version": "1.0",
        "plugin": "deep-research-validator",
        "workflow": "deep-research-validator",
        "run_id": "deep-research-test-run",
        "review_payload_path": "review_payload.json",
        "decisions": [],
        "decision_count": 0,
        "status": "pending_review",
    }
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": "deep-research-validator",
        "workflow": "deep-research-validator",
        "run_id": "deep-research-test-run",
        "outputs": [
            {
                "path": "claims_review.json",
                "kind": "json",
                "status": "written",
                "records_key": "claims",
                "row_count": 1,
                "required_columns": [
                    "claim_index",
                    "claim_text",
                    "verdict",
                    "proposed_fix",
                ],
            },
            {
                "path": "validation_audit.json",
                "kind": "json",
                "status": "written",
            },
            {
                "path": "validation_package.md",
                "kind": "md",
                "status": "written",
                "required_text": [
                    "# Deep Research Validation Package",
                    "## Document Inventory",
                    "## Claims Review",
                ],
            },
            {
                "path": "validated_document.docx",
                "kind": "docx",
                "status": "written",
            },
        ],
        "caveats": [],
        "next_actions": [],
        "status": "written_pending_review",
    }
    (tmp_path / "run_intake.json").write_text(
        json.dumps(run_intake, indent=2) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "review_payload.json").write_text(
        json.dumps(review_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "final_artifacts.json").write_text(
        json.dumps(final_artifacts, indent=2) + "\n",
        encoding="utf-8",
    )
    messages: list[dict[str, object]] = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "validate_deep_research_review",
                "arguments": {"review_payload": review_payload},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "render_deep_research_review",
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "ui_decisions": ui_decisions,
                    "final_artifacts": final_artifacts,
                },
            },
        },
        {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "resources/read",
            "params": {"uri": "ui://widget/deep-research-review.html"},
        },
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "save_deep_research_decisions",
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "ui_decisions": ui_decisions,
                    "decisions": [
                        {
                            "item_id": "claim-1",
                            "action": "edit",
                            "edit_value": (
                                "Narrow the claim to the cited VAT rule only."
                            ),
                        },
                        {
                            "item_id": "source-limit-1",
                            "action": "accept",
                        },
                    ],
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "apply_deep_research_decisions",
                "arguments": {
                    "run_intake": run_intake,
                    "review_payload": review_payload,
                    "ui_decisions": ui_decisions,
                    "final_artifacts": final_artifacts,
                    "decisions": [
                        {
                            "item_id": "claim-1",
                            "action": "edit",
                            "edit_value": (
                                "Narrow the claim to the cited VAT rule only."
                            ),
                        },
                        {
                            "item_id": "source-limit-1",
                            "action": "accept",
                        },
                    ],
                },
            },
        },
    ]

    responses = {response["id"]: response for response in _call_mcp_server(messages)}

    tool_names = {tool["name"] for tool in responses[1]["result"]["tools"]}
    assert {
        "validate_deep_research_review",
        "render_deep_research_review",
        "save_deep_research_decisions",
        "apply_deep_research_decisions",
    } <= tool_names
    validate_result = responses[2]["result"]["structuredContent"]
    assert validate_result["ok"] is True
    assert validate_result["item_count"] == 2
    render_result = responses[3]["result"]
    assert render_result["structuredContent"]["widget_type"] == "deep_research_review"
    assert (
        render_result["_meta"]["openai/outputTemplate"]
        == "ui://widget/deep-research-review.html"
    )
    resource_uris = {
        resource["uri"] for resource in responses[4]["result"]["resources"]
    }
    assert "ui://widget/deep-research-review.html" in resource_uris
    widget_html = responses[5]["result"]["contents"][0]["text"]
    assert "Deep Research Review" in widget_html
    save_result = responses[6]["result"]["structuredContent"]
    assert save_result["ok"] is True
    assert save_result["persisted"] is True
    assert save_result["decision_count"] == 2
    apply_result = responses[7]["result"]["structuredContent"]
    assert apply_result["ok"] is True
    assert apply_result["run_intake_path"] == str(tmp_path / "run_intake.json")
    assert apply_result["structured_update_count"] == 1
    assert apply_result["native_regeneration_count"] == 0
    assert apply_result["native_regenerated_count"] == 1
    assert apply_result["application_status"] == "final_ready"
    updated_claims = json.loads(claims_review_path.read_text(encoding="utf-8"))
    assert updated_claims["claims"][0]["proposed_fix"] == (
        "Narrow the claim to the cited VAT rule only."
    )
    package_text = (tmp_path / "validation_package.md").read_text(encoding="utf-8")
    assert "Narrow the claim to the cited VAT rule only." in package_text
    docx_text = _docx_text(tmp_path / "validated_document.docx")
    assert "Narrow the claim to the cited VAT rule only." in docx_text
    applied = json.loads((tmp_path / "applied_decisions.json").read_text())
    assert applied["effects"][0]["structured_update"] == {
        "id_field": "claim_index",
        "record_id": "1",
        "target_field": "proposed_fix",
        "records_key": "claims",
        "updated_rows": 1,
    }
    assert applied["effects"][0]["downstream_regeneration_status"] == "regenerated"
    assert applied["effects"][0]["downstream_regenerated_paths"] == [
        "validation_audit.json",
        "validation_package.md",
        "validated_document.docx",
    ]
    assert applied["effects"][0]["native_regeneration_status"] == "regenerated"
    assert applied["effects"][0]["native_regenerated_paths"] == [
        "validated_document.docx"
    ]
    assert applied["downstream_regenerated_paths"] == [
        "validation_audit.json",
        "validation_package.md",
        "validated_document.docx",
    ]
    assert applied["native_regeneration_count"] == 0
    assert applied["native_regenerated_count"] == 1
    assert applied["native_regenerated_paths"] == ["validated_document.docx"]
    final_after_apply = json.loads((tmp_path / "final_artifacts.json").read_text())
    assert final_after_apply["status"] == "final_ready"
    claims_output = next(
        output
        for output in final_after_apply["outputs"]
        if output["path"] == "claims_review.json"
    )
    assert claims_output["status"] == "updated_from_review"
    assert claims_output["records_key"] == "claims"
    assert claims_output["required_columns"] == ["claim_index", "proposed_fix"]
    package_output = next(
        output
        for output in final_after_apply["outputs"]
        if output["path"] == "validation_package.md"
    )
    assert package_output["status"] == "updated_from_review"
    assert (
        "Narrow the claim to the cited VAT rule only."
        in package_output["required_text"]
    )
    docx_output = next(
        output
        for output in final_after_apply["outputs"]
        if output["path"] == "validated_document.docx"
    )
    assert docx_output["status"] == "updated_from_review"
    assert docx_output["native_regenerated"] is True
    assert (
        "Narrow the claim to the cited VAT rule only." in docx_output["required_text"]
    )
    assert final_after_apply["review_application"]["downstream_regenerated_paths"] == [
        "validation_audit.json",
        "validation_package.md",
        "validated_document.docx",
    ]
    assert final_after_apply["review_application"]["native_regenerated_paths"] == [
        "validated_document.docx"
    ]
    run_intake = json.loads((tmp_path / "run_intake.json").read_text())
    review_apply_steps = [
        step
        for step in run_intake["execution_trace"]
        if step["kind"] == "deterministic_review_apply"
    ]
    assert len(review_apply_steps) == 1
    assert {
        "applied_decisions.json",
        "claims_review.json",
        "final_artifacts.json",
        "validated_document.docx",
        "validation_audit.json",
        "validation_package.md",
        "ui_decisions.json",
    } <= set(review_apply_steps[0]["outputs"])
    contract = validate_contract(
        tmp_path,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert contract.ok is True, contract.errors
