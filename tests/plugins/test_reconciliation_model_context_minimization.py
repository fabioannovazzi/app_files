from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _check_entries_payload_digest(payload: dict[str, object]) -> str:
    content = dict(payload)
    content.pop("content_sha256", None)
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _review_payload(plugin: str) -> dict[str, object]:
    item_types = {
        "open-item-reconciliation": "missing_evidence_review",
        "journal-bank-reconciliation": "unmatched_bank",
        "check-entries": "mismatch",
    }
    payload: dict[str, object] = {
        "schema_version": "2.0" if plugin == "check-entries" else "1.0",
        "plugin": plugin,
        "workflow": plugin,
        "run_id": "PRIVATE-RUN-ID",
        "review_type": "reconciliation_review",
        "items": [
            {
                "id": "PRIVATE-SOURCE-ROW-ID",
                "item_type": item_types[plugin],
                "title": "PRIVATE TITLE FOR ACME",
                "source_path": "/private/customer/acme-ledger.xlsx; row 77",
                "output_path": "private-review-output.json",
                "allowed_actions": ["accept", "mark_unclear", "skip"],
                "recommended_action": "mark_unclear",
                "evidence": [
                    {
                        "kind": "deterministic_check",
                        "status": "FAIL",
                        "reason": "amount_and_date_candidate",
                        "evidence_facts": {
                            "reference": "REF-SECRET-9988",
                            "source_path": "/private/customer/support.pdf",
                            "prepared_entry_id": "PRIVATE-ENTRY-ID",
                            "counterparty_name": "Acme S.p.A.",
                        },
                    }
                ],
                "data": {
                    "status": "needs_review",
                    "description": "Acme S.p.A. settlement",
                    "amount": 123.45,
                    "amount_signed": 123.45,
                    "document_date": "2026-01-02",
                    "entry_date": "2026-01-02",
                    "transaction_date": "2026-01-02",
                    "reference": "REF-SECRET-9988",
                    "target_record_id": "PRIVATE-TARGET-ID",
                    "unmapped_secret": "PRIVATE-UNMAPPED-VALUE",
                    "blank_field": "",
                },
                "status": "needs_review",
            }
        ],
        "item_count": 1,
        "status": "ready_for_review",
    }
    if plugin == "check-entries":
        payload["content_sha256"] = _check_entries_payload_digest(payload)
    return payload


@pytest.mark.parametrize(
    ("plugin", "validate_tool", "render_tool", "case_tool"),
    [
        (
            "open-item-reconciliation",
            "validate_open_item_reconciliation_review",
            "render_open_item_reconciliation_review",
            "get_open_item_reconciliation_case_context",
        ),
        (
            "journal-bank-reconciliation",
            "validate_journal_bank_review",
            "render_journal_bank_review",
            "get_journal_bank_case_context",
        ),
        (
            "check-entries",
            "validate_check_entries_review",
            "render_check_entries_review",
            "get_check_entries_case_context",
        ),
    ],
)
def test_reconciliation_review_exposes_only_selected_case_context_to_model(
    plugin: str,
    validate_tool: str,
    render_tool: str,
    case_tool: str,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the reconciliation MCP servers.")
    process = subprocess.Popen(
        [node, str(ROOT / "plugins" / plugin / "mcp" / "server.cjs"), "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None
    assert process.stdout is not None

    def call_tool(message_id: int, tool: str, arguments: dict[str, object]) -> dict[str, object]:
        process.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "method": "tools/call",
                    "params": {"name": tool, "arguments": arguments},
                }
            )
            + "\n"
        )
        process.stdin.flush()
        response = json.loads(process.stdout.readline())
        assert response["id"] == message_id
        assert "error" not in response
        return response["result"]

    try:
        payload = _review_payload(plugin)
        validated = call_tool(1, validate_tool, {"review_payload": payload})
        model_index = validated["structuredContent"]
        serialized_index = json.dumps(model_index, sort_keys=True)
        assert model_index["model_context_index"]["indexed_case_count"] == 1
        assert model_index["model_context_index"]["cases"][0]["status"] == (
            "needs_review"
        )
        for private_value in (
            "PRIVATE TITLE FOR ACME",
            "PRIVATE-RUN-ID",
            "PRIVATE-SOURCE-ROW-ID",
            "REF-SECRET-9988",
            "/private/customer",
            "Acme S.p.A. settlement",
            "123.45",
            "2026-01-02",
        ):
            assert private_value not in serialized_index

        reference = model_index["review_reference"]
        case_handle = model_index["model_context_index"]["cases"][0]["case_handle"]
        selected = call_tool(
            2,
            case_tool,
            {
                "persistence_token": reference["persistence_token"],
                "case_handles": [case_handle],
            },
        )["structuredContent"]
        serialized_selected = json.dumps(selected, sort_keys=True)
        assert selected["case_count"] == 1
        assert selected["include_exact_identifiers"] is False
        assert "Acme S.p.A. settlement" in serialized_selected
        assert "123.45" in serialized_selected
        assert "2026-01-02" in serialized_selected
        for excluded in (
            "REF-SECRET-9988",
            "PRIVATE-SOURCE-ROW-ID",
            "PRIVATE-TARGET-ID",
            "PRIVATE-UNMAPPED-VALUE",
            "/private/customer",
            "private-review-output.json",
        ):
            assert excluded not in serialized_selected

        selected_with_identifiers = call_tool(
            3,
            case_tool,
            {
                "persistence_token": reference["persistence_token"],
                "case_handles": [case_handle],
                "include_exact_identifiers": True,
            },
        )["structuredContent"]
        assert "REF-SECRET-9988" in json.dumps(
            selected_with_identifiers,
            sort_keys=True,
        )

        rendered = call_tool(
            4,
            render_tool,
            {"persistence_token": reference["persistence_token"]},
        )
        assert "review_payload" not in rendered["structuredContent"]
        assert "PRIVATE TITLE FOR ACME" not in json.dumps(
            rendered["structuredContent"],
            sort_keys=True,
        )
        private_payload = rendered["_meta"]["private_review_payload"]
        assert private_payload["review_payload"] == payload
    finally:
        process.stdin.close()
        process.wait(timeout=10)
