from __future__ import annotations

import importlib.util
import json
import shutil
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "scripts" / "serve_review_workbench.py"


def load_server_module():
    spec = importlib.util.spec_from_file_location("serve_review_workbench", SERVER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _fixture_output_dir(tmp_path: Path) -> Path:
    output_dir = tmp_path / "check-entries-run"
    output_dir.mkdir()
    run_id = "check-entries-local-server-test"
    _write_json(
        output_dir / "run_intake.json",
        {
            "schema_version": "1.0",
            "plugin": "check-entries",
            "workflow": "check-entries",
            "run_id": run_id,
            "created_at": "2026-06-07T10:00:00Z",
            "language": "en",
            "input_paths": ["entries.xlsx", "support.pdf"],
            "output_dir": output_dir.as_posix(),
            "inferred_task": "Test local review write-back",
            "assumptions": [],
            "unresolved_questions": [],
            "dependency_check": {"status": "ok"},
            "execution_trace": [
                {
                    "step_id": "inspect",
                    "kind": "deterministic_review_session",
                    "status": "passed",
                    "execution_location": "local_codex_workspace",
                    "command": ["pytest", "fixture"],
                    "inputs": ["entries.xlsx"],
                    "outputs": ["review_payload.json"],
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
            "source_paths": ["entries.xlsx", "support.pdf"],
            "review_type": "journal_entry_support_review",
            "items": [
                {
                    "id": "entry-1",
                    "item_type": "supported_entry",
                    "title": "1001 | 123.45 | 2025-01-02",
                    "source_path": "entries.xlsx",
                    "output_path": "check_results.csv",
                    "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                    "recommended_action": "edit",
                    "data": {
                        "status": "ok",
                        "source_row": "1",
                        "target_artifact": "check_results.csv",
                        "target_id_field": "source_row",
                        "target_record_id": "1",
                        "target_field": "review_notes",
                    },
                    "evidence": [{"kind": "deterministic_checks", "status": "ok"}],
                }
            ],
            "item_count": 1,
            "columns": ["source_row", "review_notes"],
            "evidence": [{"kind": "deterministic_checks", "status": "ok"}],
            "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
            "status": "ready_for_review",
        },
    )
    _write_json(
        output_dir / "final_artifacts.json",
        {
            "schema_version": "1.0",
            "plugin": "check-entries",
            "workflow": "check-entries",
            "run_id": run_id,
            "outputs": [
                {"path": "check_results.csv", "kind": "csv", "status": "written"}
            ],
            "caveats": [],
            "next_actions": [],
            "status": "written_pending_review",
        },
    )
    (output_dir / "check_results.csv").write_text(
        "source_row,review_notes\n1,\n",
        encoding="utf-8",
    )
    return output_dir


def test_local_review_workbench_injects_browser_write_bridge(tmp_path: Path) -> None:
    server = load_server_module()
    workbench = server.LocalReviewWorkbench(
        plugin_dir=ROOT / "plugins" / "check-entries",
        output_dir=_fixture_output_dir(tmp_path),
    )

    html = server.render_review_html(workbench)
    session = server.build_session_payload(workbench)

    assert "window.openai" in html
    assert "/api/call-tool" in html
    assert "local_review_server" in html
    assert session["decision_policy"]["can_persist"] is True
    assert session["decision_policy"]["save_tool"] == "save_check_entries_decisions"
    assert session["review_payload"]["item_count"] == 1


def test_plugin_dir_resolution_supports_installed_plugin_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = load_server_module()
    plugin_dir = tmp_path / "check-entries"
    (plugin_dir / ".codex-plugin").mkdir(parents=True)
    (plugin_dir / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "check-entries"}) + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "assets").mkdir()
    (plugin_dir / "assets" / "review-workbench-adapter.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (plugin_dir / "mcp").mkdir()
    (plugin_dir / "mcp" / "server.cjs").write_text(
        '"use strict";\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "ROOT", plugin_dir)

    resolved = server._plugin_dir_from_args("check-entries", None)

    assert resolved == plugin_dir.resolve()


def test_local_review_server_rejects_non_loopback_host(tmp_path: Path) -> None:
    server = load_server_module()
    workbench = server.LocalReviewWorkbench(
        plugin_dir=ROOT / "plugins" / "check-entries",
        output_dir=_fixture_output_dir(tmp_path),
    )

    with pytest.raises(ValueError, match="loopback"):
        server.create_review_http_server(workbench, host="0.0.0.0")


def test_local_review_server_formats_ipv6_loopback_url() -> None:
    server = load_server_module()

    assert server._review_url("::1", 12345) == "http://[::1]:12345/review"
    assert server._server_class("::1").address_family == socket.AF_INET6


def test_local_review_server_rejects_oversized_post_body(tmp_path: Path) -> None:
    server = load_server_module()
    workbench = server.LocalReviewWorkbench(
        plugin_dir=ROOT / "plugins" / "check-entries",
        output_dir=_fixture_output_dir(tmp_path),
    )
    handler = server._handler(workbench)

    class Request:
        path = "/api/call-tool"
        rfile = None
        wfile = None
        headers = {"Content-Length": str(server.MAX_POST_BYTES + 1)}

        def send_error(self, *args) -> None:
            raise AssertionError(f"unexpected send_error call: {args}")

        def _json_response(self, payload, *, status) -> None:
            self.payload = payload
            self.status = status

    request = Request()

    handler.do_POST(request)

    assert request.status.value == 400
    assert "exceeds" in request.payload["error"]


def test_local_review_workbench_routes_save_and_apply_to_plugin_mcp(
    tmp_path: Path,
) -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js is required to exercise the local review server bridge.")
    server = load_server_module()
    output_dir = _fixture_output_dir(tmp_path)
    workbench = server.LocalReviewWorkbench(
        plugin_dir=ROOT / "plugins" / "check-entries",
        output_dir=output_dir,
    )
    decisions = [
        {
            "item_id": "entry-1",
            "action": "edit",
            "edit_value": "Reviewed from local browser",
            "reviewer_note": "Applied through shared local review server",
        }
    ]

    save_result = server.call_review_tool(
        workbench,
        "save_check_entries_decisions",
        {"decisions": decisions, "reviewer": "pytest"},
    )
    apply_result = server.call_review_tool(
        workbench,
        "apply_check_entries_decisions",
        {"decisions": decisions, "reviewer": "pytest"},
    )

    assert save_result["ok"] is True
    assert save_result["persisted"] is True
    assert save_result["decision_count"] == 1
    assert apply_result["ok"] is True
    assert apply_result["persisted"] is True
    assert apply_result["structured_update_count"] == 1

    ui_decisions = json.loads(
        (output_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    applied_decisions = json.loads(
        (output_dir / "applied_decisions.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    check_results = (output_dir / "check_results.csv").read_text(encoding="utf-8")

    assert ui_decisions["decision_source"] == "local_review_server"
    assert applied_decisions["decision_source"] == "local_review_server"
    assert final_artifacts["review_application"]["decision_count"] == 1
    assert "Reviewed from local browser" in check_results
