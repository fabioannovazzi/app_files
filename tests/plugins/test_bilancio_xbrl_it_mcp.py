from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "bilancio-xbrl-it"
SERVER = PLUGIN_ROOT / "mcp" / "server.cjs"
RULE_PACK = PLUGIN_ROOT / "rulepacks" / "it" / "statutory-forms-2026.1.json"
NODE = shutil.which("node") or str(
    Path.home()
    / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
)


def _run_server(messages: list[dict[str, object]], env: dict[str, str] | None = None):
    if not Path(NODE).is_file():
        raise RuntimeError("Node.js is required for the MCP contract tests")
    runtime_env = dict(os.environ)
    if env:
        runtime_env.update(env)
    payload = "".join(json.dumps(message) + "\n" for message in messages)
    result = subprocess.run(
        [NODE, str(SERVER)],
        cwd=PLUGIN_ROOT,
        env=runtime_env,
        input=payload,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return [json.loads(line) for line in result.stdout.splitlines()]


def _payload() -> dict[str, object]:
    return {
        "case_id": "case_mcp_2025",
        "entity": {
            "legal_name": "Rossi S.r.l.",
            "tax_identifier": "IT00000000000",
            "registered_office": "Milano (MI), Italia",
            "legal_form": "SRL",
            "accounting_framework": "OIC",
            "listed": False,
            "regulated_sector": False,
            "consolidated": False,
            "final_liquidation": False,
            "first_financial_year": False,
            "prior_year_form": "ABBREVIATED",
            "micro_exclusion_flags": [],
        },
        "period": {"start": "2025-01-01", "end": "2025-12-31"},
        "oic_rule_pack": "OIC_2024_2025.1",
        "filing_campaign_year": 2026,
        "taxonomy_checksum": "a" * 64,
    }


def test_mcp_lists_complete_vera_facing_tool_contract() -> None:
    responses = _run_server(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
    )

    tool_names = {item["name"] for item in responses[1]["result"]["tools"]}
    assert tool_names == {
        "xbrl_case_create",
        "xbrl_document_ingest",
        "xbrl_case_analyze",
        "xbrl_mapping_get_review_packet",
        "xbrl_mapping_apply_decisions",
        "xbrl_questionnaire_get",
        "xbrl_questionnaire_submit",
        "xbrl_draft_generate",
        "xbrl_case_validate",
        "xbrl_case_prepare_xbrl_review",
        "xbrl_case_approve",
        "xbrl_case_export",
        "xbrl_case_get_workpaper",
        "xbrl_case_artifact_download_grant",
        "xbrl_case_get_intelligence_packet",
        "xbrl_case_record_intelligence",
        "xbrl_case_enqueue_job",
        "xbrl_case_job_get",
        "xbrl_case_get_review_view",
    }
    analyze = next(
        item
        for item in responses[1]["result"]["tools"]
        if item["name"] == "xbrl_case_analyze"
    )
    assert (
        "record_statutory_presentation"
        in analyze["inputSchema"]["properties"]["operation"]["enum"]
    )
    assert (
        "migrate_regulatory_versions"
        in analyze["inputSchema"]["properties"]["operation"]["enum"]
    )


def test_mcp_create_uses_authenticated_environment_not_payload_tenant(
    tmp_path: Path,
) -> None:
    responses = _run_server(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "xbrl_case_create",
                    "arguments": {
                        "payload": {**_payload(), "tenant_id": "untrusted_tenant"},
                        "idempotency_key": "create_1",
                    },
                },
            }
        ],
        {
            "VERA_XBRL_STORAGE_ROOT": str(tmp_path / "store"),
            "VERA_XBRL_TENANT_ID": "authenticated_tenant",
            "VERA_XBRL_ACTOR_ID": "preparer_1",
            "VERA_XBRL_ROLES": "PREPARER",
            "VERA_XBRL_PYTHON": sys.executable,
        },
    )

    structured = responses[0]["result"]["structuredContent"]
    assert structured["case_id"] == "case_mcp_2025"
    stored = json.loads(
        (
            tmp_path / "store" / "authenticated_tenant" / "case_mcp_2025" / "case.json"
        ).read_text(encoding="utf-8")
    )
    assert stored["tenant_id"] == "authenticated_tenant"


def test_mcp_create_selects_historical_statutory_pack_by_period(
    tmp_path: Path,
) -> None:
    payload = _payload()
    payload["case_id"] = "case_mcp_2020"
    payload["period"] = {"start": "2020-01-01", "end": "2020-12-31"}
    payload["oic_rule_pack"] = "OIC_2016_2023.1"

    responses = _run_server(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "xbrl_case_create",
                    "arguments": {
                        "payload": payload,
                        "idempotency_key": "create_historical_1",
                    },
                },
            }
        ],
        {
            "VERA_XBRL_STORAGE_ROOT": str(tmp_path / "store"),
            "VERA_XBRL_TENANT_ID": "authenticated_tenant",
            "VERA_XBRL_ACTOR_ID": "preparer_1",
            "VERA_XBRL_ROLES": "PREPARER",
            "VERA_XBRL_PYTHON": sys.executable,
        },
    )

    structured = responses[0]["result"]["structuredContent"]
    assert structured["rule_pack_versions"]["statutory_rule_pack"] == ("IT_CC_2016.1")


def test_mcp_mutation_fails_closed_without_authenticated_environment() -> None:
    responses = _run_server(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "xbrl_case_validate",
                    "arguments": {
                        "case_id": "case_1",
                        "revision_id": "rev_1",
                        "idempotency_key": "validate_1",
                    },
                },
            }
        ],
        {
            "VERA_XBRL_STORAGE_ROOT": "",
            "VERA_XBRL_TENANT_ID": "",
            "VERA_XBRL_ACTOR_ID": "",
            "VERA_XBRL_ROLES": "",
            "VERA_XBRL_PYTHON": sys.executable,
        },
    )

    assert responses[0]["error"]["code"] == -32000
    assert "environment is incomplete" in responses[0]["error"]["message"]


def test_mcp_queues_revision_bound_job_and_returns_compact_status(
    tmp_path: Path,
) -> None:
    responses = _run_server(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "xbrl_case_create",
                    "arguments": {
                        "payload": _payload(),
                        "idempotency_key": "create_1",
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "xbrl_case_enqueue_job",
                    "arguments": {
                        "case_id": "case_mcp_2025",
                        "revision_id": "rev_1",
                        "job_id": "validate_1",
                        "operation": "validate",
                        "payload": {},
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "xbrl_case_job_get",
                    "arguments": {
                        "case_id": "case_mcp_2025",
                        "job_id": "validate_1",
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "xbrl_case_get_review_view",
                    "arguments": {
                        "case_id": "case_mcp_2025",
                        "view": "CASE_DASHBOARD",
                    },
                },
            },
        ],
        {
            "VERA_XBRL_STORAGE_ROOT": str(tmp_path / "store"),
            "VERA_XBRL_TENANT_ID": "authenticated_tenant",
            "VERA_XBRL_ACTOR_ID": "preparer_1",
            "VERA_XBRL_ROLES": "PREPARER",
            "VERA_XBRL_PYTHON": sys.executable,
        },
    )

    queued = responses[1]["result"]["structuredContent"]
    status = responses[2]["result"]["structuredContent"]
    assert queued == status
    assert status["status"] == "PENDING"
    assert status["expected_revision"] == "rev_1"
    assert status["resource_id"].endswith("/case_mcp_2025/validate_1")
    assert "payload" not in status
    dashboard = responses[3]["result"]["structuredContent"]
    assert dashboard["view"] == "CASE_DASHBOARD"
    assert dashboard["next_action"] == "INGEST_TRIAL_BALANCE"
