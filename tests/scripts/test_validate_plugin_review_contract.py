from __future__ import annotations

import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from scripts import validate_plugin_review_contract as validator


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_mcp_contract(
    root: Path,
    plugin: str,
    *,
    item_types: list[str],
    actions: list[str],
) -> None:
    server_dir = root / "plugins" / plugin / "mcp"
    server_dir.mkdir(parents=True)
    action_rows = "\n".join(f'  "{action}",' for action in actions)
    item_rows = "\n".join(f'  "{item_type}",' for item_type in item_types)
    (server_dir / "server.cjs").write_text(
        "\n".join(
            [
                "const ALLOWED_ACTIONS = new Set([",
                action_rows,
                "]);",
                "const ITEM_TYPES = new Set([",
                item_rows,
                "]);",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _review_handoff_output_record() -> dict[str, object]:
    return {
        "path": "review_handoff.md",
        "kind": "md",
        "status": "written",
        "required_text": [
            "Review Handoff",
            "review_payload.json",
            "ui_decisions.json",
            "applied_decisions.json",
            "final_artifacts.json",
        ],
        "qa_checks": ["nonempty_text", "required_text"],
    }


def _set_final_outputs(
    output_dir: Path,
    outputs: list[dict[str, object]],
) -> None:
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    final_artifacts["outputs"] = [_review_handoff_output_record(), *outputs]
    _write_json(final_path, final_artifacts)


def _base_contract(tmp_path: Path) -> Path:
    output_dir = tmp_path / "run"
    output_dir.mkdir()
    run_id = "check-entries-001"
    _write_json(
        output_dir / "run_intake.json",
        {
            "schema_version": "1.0",
            "plugin": "check-entries",
            "workflow": "check-entries",
            "created_at": "2026-06-07T10:00:00Z",
            "language": "en",
            "input_paths": ["entries.xlsx", "support/"],
            "output_dir": output_dir.as_posix(),
            "inferred_task": "check selected journal entries",
            "assumptions": [],
            "unresolved_questions": [],
            "dependency_check": {"status": "passed"},
            "data_posture": {
                "local_files_read": ["entries.xlsx", "support/"],
                "external_connectors_used": [],
                "upload_paths_used": [],
                "remote_sql_execution_used": False,
                "hosted_notebook_execution_used": False,
            },
            "execution_trace": [
                {
                    "step_id": "check_entries_run",
                    "kind": "deterministic_run",
                    "status": "passed",
                    "execution_location": "local_codex_workspace",
                    "command": [
                        "python",
                        "plugins/check-entries/scripts/run_check_entries.py",
                        "--entries",
                        "entries.xlsx",
                        "--support",
                        "support/",
                    ],
                    "inputs": ["entries.xlsx", "support/"],
                    "outputs": [
                        "review_payload.json",
                        "review_handoff.md",
                        "check_results.csv",
                        "final_artifacts.json",
                    ],
                }
            ],
        },
    )
    _write_json(
        output_dir / "review_payload.json",
        {
            "schema_version": "1.0",
            "plugin": "check-entries",
            "workflow": "check-entries",
            "run_id": run_id,
            "source_paths": ["entries.xlsx", "support/"],
            "review_type": "journal_entry_support_review",
            "items": [
                {
                    "id": "entry-1",
                    "title": "Entry 1",
                    "item_type": "supported_entry",
                    "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                }
            ],
            "item_count": 1,
            "columns": [{"field": "title", "label": "Entry"}],
            "source_artifacts": {
                "run_intake": "run_intake.json",
                "check_results": "check_results.csv",
            },
            "evidence": [],
            "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
            "status": "ready_for_review",
        },
    )
    _write_json(
        output_dir / "ui_decisions.json",
        {
            "schema_version": "1.0",
            "plugin": "check-entries",
            "workflow": "check-entries",
            "run_id": run_id,
            "decided_at": "2026-06-07T10:01:00Z",
            "decision_source": "local_html_ui",
            "review_payload_path": "review_payload.json",
            "decisions": [{"item_id": "entry-1", "action": "accept"}],
            "decision_count": 1,
            "status": "reviewed",
        },
    )
    _write_json(
        output_dir / "final_artifacts.json",
        {
            "schema_version": "1.0",
            "plugin": "check-entries",
            "workflow": "check-entries",
            "run_id": run_id,
            "completed_at": "2026-06-07T10:02:00Z",
            "outputs": [
                _review_handoff_output_record(),
                {"path": "check_results.csv", "kind": "csv", "status": "written"},
            ],
            "caveats": [],
            "next_actions": [],
            "status": "final_ready",
        },
    )
    (output_dir / "review_handoff.md").write_text(
        "\n".join(
            [
                "# Check Entries Review Handoff",
                "",
                "- Review payload: `review_payload.json`",
                "- Run intake: `run_intake.json`",
                "- Pending decisions: `ui_decisions.json`",
                "- Applied decisions: `applied_decisions.json`",
                "- Final artifacts: `final_artifacts.json`",
                "",
                "## Review In Codex",
                "1. Validate the payload with `validate_check_entries_review`.",
                "2. Render the review workbench with `render_check_entries_review`.",
                "3. Save reviewer actions with `save_check_entries_decisions`.",
                "4. Apply reviewer actions with `apply_check_entries_decisions`.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "check_results.csv").write_text("id,status\n1,ok\n", encoding="utf-8")
    return output_dir


def _write_xlsx_archive(
    path: Path,
    *,
    workbook_xml: str | None = None,
    include_worksheet: bool = True,
    sheet_names: list[str] | None = None,
    headers_by_sheet: dict[str, list[str]] | None = None,
    rows_by_sheet: dict[str, list[list[str]]] | None = None,
) -> None:
    names = sheet_names or ["Results"]
    sheet_elements = "".join(
        f'<sheet name="{name}" sheetId="{index}" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        f'r:id="rId{index}"/>'
        for index, name in enumerate(names, start=1)
    )
    workbook = workbook_xml or (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheets>"
        f"{sheet_elements}"
        "</sheets>"
        "</workbook>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        relationship_elements = "".join(
            "<Relationship "
            f'Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
            for index, _name in enumerate(names, start=1)
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{relationship_elements}"
            "</Relationships>",
        )
        if include_worksheet:
            for index, name in enumerate(names, start=1):
                headers = (headers_by_sheet or {}).get(name, [])
                header_cells = "".join(
                    f'<c r="{chr(65 + column_index)}1" t="inlineStr"><is><t>{escape(header)}</t></is></c>'
                    for column_index, header in enumerate(headers)
                )
                rows = [f'<row r="1">{header_cells}</row>'] if header_cells else []
                for row_index, row_values in enumerate(
                    (rows_by_sheet or {}).get(name, []), start=2
                ):
                    cells = "".join(
                        f'<c r="{chr(65 + column_index)}{row_index}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
                        for column_index, value in enumerate(row_values)
                    )
                    rows.append(f'<row r="{row_index}">{cells}</row>')
                archive.writestr(
                    f"xl/worksheets/sheet{index}.xml",
                    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    f"<sheetData>{''.join(rows)}</sheetData>"
                    "</worksheet>",
                )


def _write_docx_archive(path: Path, paragraphs: list[str]) -> None:
    body = "".join(
        "<w:p><w:r><w:t>" f"{escape(paragraph)}" "</w:t></w:r></w:p>"
        for paragraph in paragraphs
    )
    document_xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body>"
        "</w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)


def _write_searchable_pdf(path: Path, text: str) -> None:
    path.write_bytes(
        (
            "%PDF-1.4\n"
            "1 0 obj\n"
            f"<< /Length {len(text)} >>\n"
            "stream\n"
            f"{text}\n"
            "endstream\n"
            "endobj\n"
            "%%EOF\n"
        ).encode("latin-1")
    )


def test_validate_contract_accepts_complete_review_session(tmp_path: Path) -> None:
    output_dir = _base_contract(tmp_path)

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
    )

    assert report.ok is True
    assert report.errors == []
    assert report.warnings == []
    assert "review_payload.json" in report.files_checked


def test_validate_contract_rejects_payload_values_rejected_by_mcp_validator(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_dir = _base_contract(tmp_path)
    _write_mcp_contract(
        tmp_path,
        "check-entries",
        item_types=["supported_entry"],
        actions=["accept", "edit", "mark_unclear"],
    )
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    review_payload_path = output_dir / "review_payload.json"
    review_payload = json.loads(review_payload_path.read_text(encoding="utf-8"))
    review_payload["items"][0]["item_type"] = "unsupported_entry"
    review_payload["items"][0]["recommended_action"] = "skip"
    _write_json(review_payload_path, review_payload)

    report = validator.validate_contract(output_dir)

    assert report.ok is False
    assert any("item_type 'unsupported_entry'" in error for error in report.errors)
    assert any(
        "recommends action 'skip', which is rejected by the plugin MCP validator"
        in error
        for error in report.errors
    )
    assert any(
        "actions rejected by the plugin MCP validator: skip" in error
        for error in report.errors
    )


def test_validate_contract_requires_review_handoff_card(tmp_path: Path) -> None:
    output_dir = _base_contract(tmp_path)
    final_artifacts_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_artifacts_path.read_text(encoding="utf-8"))
    final_artifacts["outputs"] = [
        output
        for output in final_artifacts["outputs"]
        if output["path"] != "review_handoff.md"
    ]
    _write_json(final_artifacts_path, final_artifacts)

    report = validator.validate_contract(output_dir)

    assert report.ok is False
    assert any("must include review_handoff.md" in error for error in report.errors)


def test_validate_contract_requires_review_handoff_tool_names(tmp_path: Path) -> None:
    output_dir = _base_contract(tmp_path)
    handoff_path = output_dir / "review_handoff.md"
    handoff_path.write_text(
        handoff_path.read_text(encoding="utf-8").replace(
            "apply_check_entries_decisions",
            "apply_wrong_tool",
        ),
        encoding="utf-8",
    )

    report = validator.validate_contract(output_dir)

    assert report.ok is False
    assert (
        "review_handoff.md is missing required text: apply_check_entries_decisions"
        in report.errors
    )


def test_validate_contract_warns_when_data_posture_is_missing(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    run_intake_path = output_dir / "run_intake.json"
    run_intake = json.loads(run_intake_path.read_text(encoding="utf-8"))
    del run_intake["data_posture"]
    _write_json(run_intake_path, run_intake)

    report = validator.validate_contract(output_dir)

    assert report.ok is True
    assert report.errors == []
    assert "missing recommended data_posture" in report.warnings[0]


def test_validate_contract_can_make_data_posture_strict(tmp_path: Path) -> None:
    output_dir = _base_contract(tmp_path)
    run_intake_path = output_dir / "run_intake.json"
    run_intake = json.loads(run_intake_path.read_text(encoding="utf-8"))
    del run_intake["data_posture"]
    _write_json(run_intake_path, run_intake)

    report = validator.validate_contract(output_dir, strict_data_posture=True)

    assert report.ok is False
    assert "missing recommended data_posture" in report.errors[0]


def test_validate_contract_can_make_execution_trace_strict(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    run_intake_path = output_dir / "run_intake.json"
    run_intake = json.loads(run_intake_path.read_text(encoding="utf-8"))
    del run_intake["execution_trace"]
    _write_json(run_intake_path, run_intake)

    report = validator.validate_contract(output_dir, strict_execution_trace=True)

    assert report.ok is False
    assert "run_intake.json missing execution_trace" in report.errors[0]


def test_validate_contract_rejects_untraced_final_output(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    run_intake_path = output_dir / "run_intake.json"
    run_intake = json.loads(run_intake_path.read_text(encoding="utf-8"))
    run_intake["execution_trace"][0]["outputs"] = ["review_payload.json"]
    _write_json(run_intake_path, run_intake)

    report = validator.validate_contract(output_dir, strict_execution_trace=True)

    assert report.ok is False
    assert (
        "final_artifacts.json output check_results.csv is not listed in "
        "run_intake.json execution_trace outputs"
    ) in report.errors


def test_validate_contract_rejects_remote_trace_without_route_record(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    run_intake_path = output_dir / "run_intake.json"
    run_intake = json.loads(run_intake_path.read_text(encoding="utf-8"))
    run_intake["execution_trace"][0]["execution_location"] = "remote_warehouse"
    _write_json(run_intake_path, run_intake)

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
    )

    assert report.ok is False
    assert (
        "run_intake.json execution_trace includes remote execution_location "
        "remote_warehouse but data_posture "
        "external_routes_used is missing"
    ) in report.errors


def test_validate_contract_requires_review_apply_trace_when_decisions_are_applied(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    final_artifacts_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_artifacts_path.read_text(encoding="utf-8"))
    final_artifacts["review_application"] = {
        "applied_at": "2026-06-07T10:03:00Z",
        "application_status": "final_ready",
        "decision_count": 1,
        "item_count": 1,
        "target_update_paths": ["check_results.csv"],
        "applied_decisions_path": "applied_decisions.json",
    }
    _write_json(final_artifacts_path, final_artifacts)

    report = validator.validate_contract(output_dir, strict_execution_trace=True)

    assert report.ok is False
    assert (
        "run_intake.json execution_trace missing deterministic_review_apply "
        "step for final_artifacts.json review_application"
    ) in report.errors


def test_validate_contract_requires_review_apply_trace_outputs(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    run_intake_path = output_dir / "run_intake.json"
    final_artifacts_path = output_dir / "final_artifacts.json"
    run_intake = json.loads(run_intake_path.read_text(encoding="utf-8"))
    run_intake["execution_trace"].append(
        {
            "step_id": "check_entries_review_apply",
            "kind": "deterministic_review_apply",
            "status": "passed",
            "execution_location": "local_codex_workspace",
            "command": ["check-entries-widgets", "apply_check_entries_decisions"],
            "inputs": ["review_payload.json", "ui_decisions.json"],
            "outputs": ["applied_decisions.json", "final_artifacts.json"],
        }
    )
    final_artifacts = json.loads(final_artifacts_path.read_text(encoding="utf-8"))
    final_artifacts["review_application"] = {
        "applied_at": "2026-06-07T10:03:00Z",
        "application_status": "final_ready",
        "decision_count": 1,
        "item_count": 1,
        "target_update_paths": ["check_results.csv"],
        "applied_decisions_path": "applied_decisions.json",
    }
    _write_json(run_intake_path, run_intake)
    _write_json(final_artifacts_path, final_artifacts)

    report = validator.validate_contract(output_dir, strict_execution_trace=True)

    assert report.ok is False
    assert (
        "final_artifacts.json review_application path check_results.csv is not "
        "listed in a review-apply execution_trace output"
    ) in report.errors


def test_validate_contract_does_not_require_unobservable_model_context_log(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    run_intake_path = output_dir / "run_intake.json"
    run_intake = json.loads(run_intake_path.read_text(encoding="utf-8"))
    assert "model_excerpts_sent" not in run_intake["data_posture"]
    _write_json(run_intake_path, run_intake)

    report = validator.validate_contract(output_dir, strict_data_posture=True)

    assert report.ok is True
    assert report.errors == []


def test_validate_contract_requires_execution_location_fields_in_strict_mode(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    run_intake_path = output_dir / "run_intake.json"
    run_intake = json.loads(run_intake_path.read_text(encoding="utf-8"))
    del run_intake["data_posture"]["remote_sql_execution_used"]
    del run_intake["data_posture"]["hosted_notebook_execution_used"]
    _write_json(run_intake_path, run_intake)

    report = validator.validate_contract(output_dir, strict_data_posture=True)

    assert report.ok is False
    assert (
        "run_intake.json data_posture missing execution fields: "
        "hosted_notebook_execution_used, remote_sql_execution_used"
    ) in report.errors


def test_validate_contract_requires_factual_external_route_record(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    run_intake_path = output_dir / "run_intake.json"
    run_intake = json.loads(run_intake_path.read_text(encoding="utf-8"))
    run_intake["data_posture"]["external_connectors_used"] = ["BigQuery"]
    _write_json(run_intake_path, run_intake)

    report = validator.validate_contract(output_dir, strict_data_posture=True)

    assert report.ok is False
    assert (
        "run_intake.json data_posture external use requires a factual "
        "external_routes_used record"
    ) in report.errors


def test_validate_contract_accepts_factual_external_route_record(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    run_intake_path = output_dir / "run_intake.json"
    run_intake = json.loads(run_intake_path.read_text(encoding="utf-8"))
    run_intake["data_posture"]["remote_sql_execution_used"] = True
    run_intake["data_posture"]["external_routes_used"] = [
        {
            "route": "bigquery_sql",
            "destination_or_origin": "BigQuery workspace connector",
            "payload_category": "analytical query and returned result rows",
            "network_used": True,
            "access_basis": "existing authorized workspace connection",
        }
    ]
    _write_json(run_intake_path, run_intake)

    report = validator.validate_contract(output_dir, strict_data_posture=True)

    assert report.ok is True
    assert report.errors == []


def test_validate_contract_rejects_incomplete_external_route_record(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    run_intake_path = output_dir / "run_intake.json"
    run_intake = json.loads(run_intake_path.read_text(encoding="utf-8"))
    run_intake["data_posture"]["upload_paths_used"] = ["https://example.com/upload"]
    run_intake["data_posture"]["external_routes_used"] = [
        {
            "route": "upload",
            "payload_category": "",
            "network_used": "yes",
            "access_basis": "",
        }
    ]
    _write_json(run_intake_path, run_intake)

    report = validator.validate_contract(output_dir, strict_data_posture=True)

    assert report.ok is False
    assert (
        "run_intake.json data_posture.external_routes_used[0] missing fields: "
        "destination_or_origin"
    ) in report.errors
    assert (
        "run_intake.json data_posture.external_routes_used[0].payload_category "
        "must be a non-empty string"
    ) in report.errors
    assert (
        "run_intake.json data_posture.external_routes_used[0].network_used must be a boolean"
    ) in report.errors
    assert (
        "run_intake.json data_posture.external_routes_used[0].access_basis must be null or a non-empty string"
        in report.errors
    )


def test_validate_contract_accepts_partial_review_with_blocked_final(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    review_path = output_dir / "review_payload.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["items"].append(
        {
            "id": "entry-2",
            "title": "Entry 2",
            "item_type": "missing_support",
            "allowed_actions": ["request_more_documents", "mark_unclear", "skip"],
        }
    )
    review["item_count"] = 2
    _write_json(review_path, review)

    ui_path = output_dir / "ui_decisions.json"
    ui_decisions = json.loads(ui_path.read_text(encoding="utf-8"))
    ui_decisions["status"] = "partial_review"
    _write_json(ui_path, ui_decisions)

    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    final_artifacts["status"] = "blocked"
    final_artifacts["next_actions"] = ["request support for entry-2"]
    _write_json(final_path, final_artifacts)

    report = validator.validate_contract(output_dir, strict_data_posture=True)

    assert report.ok is True
    assert report.errors == []


def test_validate_contract_rejects_disallowed_decision_action(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    ui_path = output_dir / "ui_decisions.json"
    ui_decisions = json.loads(ui_path.read_text(encoding="utf-8"))
    ui_decisions["decisions"] = [{"item_id": "entry-1", "action": "reject"}]
    _write_json(ui_path, ui_decisions)

    report = validator.validate_contract(output_dir, strict_data_posture=True)

    assert report.ok is False
    assert "action 'reject' is not allowed" in report.errors[0]


def test_validate_contract_accepts_workflow_specific_ready_status(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    run_intake_path = output_dir / "run_intake.json"
    run_intake = json.loads(run_intake_path.read_text(encoding="utf-8"))
    run_intake["status"] = "ready_for_new_local_workflow_run"
    _write_json(run_intake_path, run_intake)

    report = validator.validate_contract(output_dir, strict_data_posture=True)

    assert report.ok is True
    assert report.errors == []


def test_validate_contract_accepts_existing_final_artifact_outputs(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    (output_dir / "check_results.csv").write_text("id,status\n1,ok\n", encoding="utf-8")

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
    )

    assert report.ok is True
    assert report.errors == []


def test_validate_contract_accepts_readable_final_artifact_content(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is True
    assert report.errors == []


def test_validate_contract_accepts_readable_image_artifact_content(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    _set_final_outputs(
        output_dir,
        [
            {"path": "chart.png", "kind": "png", "status": "written"},
            {"path": "icon.svg", "kind": "svg", "status": "written"},
        ],
    )
    (output_dir / "chart.png").write_bytes(b"\x89PNG\r\n\x1a\npreview")
    (output_dir / "icon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"></svg>',
        encoding="utf-8",
    )

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is True
    assert report.errors == []


def test_validate_contract_accepts_workbook_with_declared_sheet(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    _set_final_outputs(
        output_dir,
        [{"path": "workpaper.xlsx", "kind": "xlsx", "status": "written"}],
    )
    _write_xlsx_archive(output_dir / "workpaper.xlsx")

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is True
    assert report.errors == []


def test_validate_contract_accepts_workbook_required_sheets(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    _set_final_outputs(
        output_dir,
        [
            {
                "path": "workpaper.xlsx",
                "kind": "xlsx",
                "status": "written",
                "required_sheets": ["summary", "Details"],
            }
        ],
    )
    _write_xlsx_archive(
        output_dir / "workpaper.xlsx",
        sheet_names=["summary", "Details"],
    )

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is True
    assert report.errors == []


def test_validate_contract_accepts_workbook_required_sheet_headers(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    _set_final_outputs(
        output_dir,
        [
            {
                "path": "workpaper.xlsx",
                "kind": "xlsx",
                "status": "written",
                "required_sheets": ["Summary"],
                "required_sheet_headers": {"Summary": ["Status", "Amount"]},
            }
        ],
    )
    _write_xlsx_archive(
        output_dir / "workpaper.xlsx",
        sheet_names=["Summary"],
        headers_by_sheet={"Summary": ["Status", "Amount", "Notes"]},
    )

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is True
    assert report.errors == []


def test_validate_contract_accepts_workbook_required_cells(tmp_path: Path) -> None:
    output_dir = _base_contract(tmp_path)
    _set_final_outputs(
        output_dir,
        [
            {
                "path": "workpaper.xlsx",
                "kind": "xlsx",
                "status": "written",
                "required_cells": {"Summary": {"A1": "Status", "B2": "Ready"}},
            }
        ],
    )
    _write_xlsx_archive(
        output_dir / "workpaper.xlsx",
        sheet_names=["Summary"],
        headers_by_sheet={"Summary": ["Status", "Result"]},
        rows_by_sheet={"Summary": [["entry-1", "Ready"]]},
    )

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is True
    assert report.errors == []


def test_validate_contract_accepts_docx_required_text(tmp_path: Path) -> None:
    output_dir = _base_contract(tmp_path)
    _set_final_outputs(
        output_dir,
        [
            {
                "path": "report.docx",
                "kind": "docx",
                "status": "written",
                "required_text": ["Executive Summary", "Excel Reference"],
            }
        ],
    )
    _write_docx_archive(
        output_dir / "report.docx",
        ["Executive Summary", "Scope and Method", "Excel Reference"],
    )

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is True
    assert report.errors == []


def test_validate_contract_accepts_pdf_required_text(tmp_path: Path) -> None:
    output_dir = _base_contract(tmp_path)
    _set_final_outputs(
        output_dir,
        [
            {
                "path": "report.pdf",
                "kind": "pdf",
                "status": "written",
                "required_text": ["Executive Summary", "Audit appendix"],
            }
        ],
    )
    _write_searchable_pdf(
        output_dir / "report.pdf",
        "Executive Summary\nScope and Method\nAudit appendix",
    )

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is True
    assert report.errors == []


def test_validate_contract_accepts_html_required_visible_text(tmp_path: Path) -> None:
    output_dir = _base_contract(tmp_path)
    _set_final_outputs(
        output_dir,
        [
            {
                "path": "report.html",
                "kind": "html",
                "status": "written",
                "required_text": ["Executive summary", "Audit appendix"],
            }
        ],
    )
    (output_dir / "report.html").write_text(
        "<main><h1>Executive summary</h1><section>Audit appendix</section></main>",
        encoding="utf-8",
    )

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is True
    assert report.errors == []


def test_validate_contract_accepts_csv_table_metadata(tmp_path: Path) -> None:
    output_dir = _base_contract(tmp_path)
    _set_final_outputs(
        output_dir,
        [
            {
                "path": "check_results.csv",
                "kind": "csv",
                "status": "written",
                "row_count": 1,
                "min_rows": 1,
                "required_columns": ["id", "status"],
            }
        ],
    )

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is True
    assert report.errors == []


def test_validate_contract_accepts_json_records_key_metadata(tmp_path: Path) -> None:
    output_dir = _base_contract(tmp_path)
    _set_final_outputs(
        output_dir,
        [
            {
                "path": "report_tables.json",
                "kind": "json",
                "status": "written",
                "records_key": "tables",
                "row_count": 2,
                "required_columns": ["section", "row_count"],
            }
        ],
    )
    _write_json(
        output_dir / "report_tables.json",
        {
            "tables": [
                {"section": "income_statement", "row_count": 2},
                {"section": "cash_flow", "row_count": 3},
            ]
        },
    )

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is True
    assert report.errors == []


def test_validate_contract_rejects_missing_final_artifact_output_in_strict_mode(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    (output_dir / "check_results.csv").unlink()

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
    )

    assert report.ok is False
    assert "references missing written output: check_results.csv" in report.errors[0]


def test_validate_contract_rejects_unreadable_final_artifact_content(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    (output_dir / "check_results.csv").write_text("", encoding="utf-8")

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is False
    assert "output check_results.csv is empty" in report.errors[0]


def test_validate_contract_rejects_invalid_image_artifact_content(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    final_artifacts["outputs"] = [
        {"path": "chart.png", "kind": "png", "status": "written"},
        {"path": "icon.svg", "kind": "svg", "status": "written"},
    ]
    _write_json(final_path, final_artifacts)
    (output_dir / "chart.png").write_bytes(b"not a png")
    (output_dir / "icon.svg").write_text("<div></div>", encoding="utf-8")

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is False
    assert (
        "final_artifacts.json output chart.png does not start with a PNG signature"
        in report.errors
    )
    assert (
        "final_artifacts.json output icon.svg does not have an SVG root element"
        in report.errors
    )


def test_validate_contract_rejects_workbook_without_declared_sheets(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    final_artifacts["outputs"] = [
        {"path": "workpaper.xlsx", "kind": "xlsx", "status": "written"}
    ]
    _write_json(final_path, final_artifacts)
    _write_xlsx_archive(
        output_dir / "workpaper.xlsx",
        workbook_xml=(
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheets/>"
            "</workbook>"
        ),
    )

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is False
    assert (
        "final_artifacts.json output workpaper.xlsx does not declare any worksheets"
        in report.errors
    )


def test_validate_contract_rejects_workbook_without_worksheet_xml(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    final_artifacts["outputs"] = [
        {"path": "workpaper.xlsx", "kind": "xlsx", "status": "written"}
    ]
    _write_json(final_path, final_artifacts)
    _write_xlsx_archive(output_dir / "workpaper.xlsx", include_worksheet=False)

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is False
    assert (
        "final_artifacts.json output workpaper.xlsx does not contain worksheet XML"
        in report.errors
    )


def test_validate_contract_rejects_missing_required_workbook_sheet(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    final_artifacts["outputs"] = [
        {
            "path": "workpaper.xlsx",
            "kind": "xlsx",
            "status": "written",
            "required_sheets": ["summary", "Missing"],
        }
    ]
    _write_json(final_path, final_artifacts)
    _write_xlsx_archive(output_dir / "workpaper.xlsx", sheet_names=["summary"])

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is False
    assert (
        "final_artifacts.json output workpaper.xlsx is missing required sheets: Missing"
        in report.errors
    )


def test_validate_contract_rejects_missing_required_sheet_header(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    final_artifacts["outputs"] = [
        {
            "path": "workpaper.xlsx",
            "kind": "xlsx",
            "status": "written",
            "required_sheet_headers": {"Summary": ["Status", "Missing"]},
        }
    ]
    _write_json(final_path, final_artifacts)
    _write_xlsx_archive(
        output_dir / "workpaper.xlsx",
        sheet_names=["Summary"],
        headers_by_sheet={"Summary": ["Status"]},
    )

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is False
    assert (
        "final_artifacts.json output workpaper.xlsx sheet Summary is missing required headers: Missing"
        in report.errors
    )


def test_validate_contract_rejects_required_workbook_cell_mismatch(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    final_artifacts["outputs"] = [
        {
            "path": "workpaper.xlsx",
            "kind": "xlsx",
            "status": "written",
            "required_cells": {"Summary": {"B2": "Ready"}},
        }
    ]
    _write_json(final_path, final_artifacts)
    _write_xlsx_archive(
        output_dir / "workpaper.xlsx",
        sheet_names=["Summary"],
        headers_by_sheet={"Summary": ["Status", "Result"]},
        rows_by_sheet={"Summary": [["entry-1", "Draft"]]},
    )

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is False
    assert (
        "final_artifacts.json output workpaper.xlsx sheet Summary cell B2 expected 'Ready' but found 'Draft'"
        in report.errors
    )


def test_validate_contract_checks_updated_from_review_workbook_cells(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    final_artifacts["outputs"] = [
        {
            "path": "workpaper.xlsx",
            "kind": "xlsx",
            "status": "updated_from_review",
            "required_cells": {"Summary": {"B2": "Ready"}},
        }
    ]
    _write_json(final_path, final_artifacts)
    _write_xlsx_archive(
        output_dir / "workpaper.xlsx",
        sheet_names=["Summary"],
        headers_by_sheet={"Summary": ["Status", "Result"]},
        rows_by_sheet={"Summary": [["entry-1", "Draft"]]},
    )

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is False
    assert (
        "final_artifacts.json output workpaper.xlsx sheet Summary cell B2 expected 'Ready' but found 'Draft'"
        in report.errors
    )


def test_validate_contract_rejects_missing_required_docx_text(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    final_artifacts["outputs"] = [
        {
            "path": "report.docx",
            "kind": "docx",
            "status": "written",
            "required_text": ["Executive Summary", "Excel Reference"],
        }
    ]
    _write_json(final_path, final_artifacts)
    _write_docx_archive(output_dir / "report.docx", ["Executive Summary"])

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is False
    assert (
        "final_artifacts.json output report.docx is missing required text: Excel Reference"
        in report.errors
    )


def test_validate_contract_rejects_missing_required_pdf_text(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    final_artifacts["outputs"] = [
        {
            "path": "report.pdf",
            "kind": "pdf",
            "status": "written",
            "required_text": ["Executive Summary", "Audit appendix"],
        }
    ]
    _write_json(final_path, final_artifacts)
    _write_searchable_pdf(output_dir / "report.pdf", "Executive Summary")

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is False
    assert (
        "final_artifacts.json output report.pdf is missing required text: Audit appendix"
        in report.errors
    )


def test_validate_contract_rejects_hidden_html_required_text(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    final_artifacts["outputs"] = [
        {
            "path": "report.html",
            "kind": "html",
            "status": "written",
            "required_text": ["Executive summary", "Audit appendix"],
        }
    ]
    _write_json(final_path, final_artifacts)
    (output_dir / "report.html").write_text(
        "<main><h1>Executive summary</h1><script>Audit appendix</script></main>",
        encoding="utf-8",
    )

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is False
    assert (
        "final_artifacts.json output report.html is missing required text: Audit appendix"
        in report.errors
    )


def test_validate_contract_rejects_invalid_required_sheets_metadata(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    final_artifacts["outputs"] = [
        {
            "path": "workpaper.xlsx",
            "kind": "xlsx",
            "status": "written",
            "required_sheets": "summary",
        }
    ]
    _write_json(final_path, final_artifacts)
    _write_xlsx_archive(output_dir / "workpaper.xlsx", sheet_names=["summary"])

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is False
    assert (
        "final_artifacts.json output workpaper.xlsx has invalid required_sheets metadata; expected a list"
        in report.errors
    )


def test_validate_contract_rejects_csv_table_metadata_mismatch(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    final_artifacts["outputs"] = [
        {
            "path": "check_results.csv",
            "kind": "csv",
            "status": "written",
            "row_count": 2,
            "required_columns": ["id", "missing_column"],
        }
    ]
    _write_json(final_path, final_artifacts)

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is False
    assert (
        "final_artifacts.json output check_results.csv row_count metadata 2 "
        "does not match actual 1"
    ) in report.errors


def test_validate_contract_rejects_json_records_key_metadata_mismatch(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    final_artifacts["outputs"] = [
        {
            "path": "report_tables.json",
            "kind": "json",
            "status": "written",
            "records_key": "missing",
            "min_rows": 1,
        }
    ]
    _write_json(final_path, final_artifacts)
    _write_json(output_dir / "report_tables.json", {"tables": []})

    report = validator.validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_output_paths=True,
        strict_output_content=True,
    )

    assert report.ok is False
    assert (
        "final_artifacts.json output report_tables.json declares records_key "
        "'missing' but JSON key is missing"
    ) in report.errors


def test_validate_contract_rejects_incomplete_final_artifact_gallery(
    tmp_path: Path,
) -> None:
    output_dir = _base_contract(tmp_path)
    final_path = output_dir / "final_artifacts.json"
    final_artifacts = json.loads(final_path.read_text(encoding="utf-8"))
    del final_artifacts["outputs"][0]["kind"]
    final_artifacts["next_actions"] = "open the report"
    final_artifacts["blockers"] = "none"
    _write_json(final_path, final_artifacts)

    report = validator.validate_contract(output_dir, strict_data_posture=True)

    assert report.ok is False
    assert (
        "final_artifacts.json outputs[0].kind must be a non-empty string"
        in report.errors
    )
    assert "final_artifacts.json next_actions must be a list" in report.errors
    assert "final_artifacts.json blockers must be a list when provided" in report.errors
