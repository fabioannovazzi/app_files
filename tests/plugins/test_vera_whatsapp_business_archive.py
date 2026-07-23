"""Contracts for Vera's bounded Marketplace WhatsApp Business route."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERA_ROOT = ROOT / "plugins" / "vera"
WRAPPER = VERA_ROOT / "skills" / "studio-archive" / "SKILL.md"
REFERENCE = (
    VERA_ROOT
    / "skills"
    / "studio-archive"
    / "references"
    / "marketplace-whatsapp-business.md"
)
EVALS = VERA_ROOT / "evals" / "marketplace_whatsapp_cases.json"
MANIFEST = VERA_ROOT / ".codex-plugin" / "plugin.json"
SERVICE = VERA_ROOT / "privacy" / "services" / "whatsapp-business-archive.json"
SUBMISSION = ROOT / "chatgpt-app-submission.json"


def test_vera_routes_marketplace_whatsapp_before_local_archive() -> None:
    wrapper = WRAPPER.read_text(encoding="utf-8")
    reference = REFERENCE.read_text(encoding="utf-8")

    assert wrapper.index("asks to search WhatsApp") < wrapper.index(
        "asks to search Gmail"
    )
    assert "references/marketplace-whatsapp-business.md" in wrapper
    assert "`whatsapp_account_status`, `search`, and `fetch`" in wrapper
    assert "configured **With MCP**" in wrapper
    assert "Do not resolve the local module" in wrapper
    assert "new inbound messages" in reference
    assert "does not import the earlier chat history" in reference
    assert "does not download media" in reference
    assert "personal WhatsApp" in reference
    assert "WhatsApp Web automation" in reference


def test_vera_whatsapp_search_is_one_client_read_only_and_bounded() -> None:
    reference = REFERENCE.read_text(encoding="utf-8")
    compact_reference = " ".join(reference.split())

    assert "client:+393331234567" in reference
    assert "one and only one `client:+E164` directive" in compact_reference
    assert "at most 20 metadata-only candidates" in reference
    assert "after 90 days" in reference
    assert "daily cleanup" in reference
    assert "Never send or modify WhatsApp content" in reference
    assert "This connector has no write tool" in reference
    assert "Studio-wide and multi-client searches are rejected" in reference


def test_vera_whatsapp_reviewer_cases_have_five_positive_and_three_negative() -> None:
    payload = json.loads(EVALS.read_text(encoding="utf-8"))

    assert payload["workflow"] == "studio-archive-marketplace-whatsapp-business"
    assert len(payload["positive_cases"]) == 5
    assert len(payload["negative_cases"]) == 3
    assert len({case["id"] for case in payload["positive_cases"]}) == 5
    assert len({case["id"] for case in payload["negative_cases"]}) == 3
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    assert "send" in serialized
    assert "history import" in serialized
    assert "studio-wide" in serialized


def test_chatgpt_submission_matches_hosted_whatsapp_tool_surface() -> None:
    submission = json.loads(SUBMISSION.read_text(encoding="utf-8"))
    evals = json.loads(EVALS.read_text(encoding="utf-8"))

    assert set(submission["tools"]) == {
        "whatsapp_account_status",
        "search",
        "fetch",
    }
    assert len(submission["test_cases"]) == 5
    assert len(submission["negative_test_cases"]) == 3
    assert [case["user_prompt"] for case in submission["test_cases"]] == [
        case["prompt"] for case in evals["positive_cases"]
    ]
    assert [case["user_prompt"] for case in submission["negative_test_cases"]] == [
        case["prompt"] for case in evals["negative_cases"]
    ]


def test_vera_remains_broad_ai_companion_with_bounded_whatsapp_prompt() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    interface = manifest["interface"]

    assert manifest["version"] == "0.1.28"
    assert manifest["description"].startswith("Vera affianca il commercialista")
    assert "WhatsApp Business" in interface["longDescription"]
    assert "controlla evidenze contabili" in interface["longDescription"]
    assert len(interface["defaultPrompt"]) == 3
    assert all(len(prompt) <= 128 for prompt in interface["defaultPrompt"])
    assert any("WhatsApp Business" in prompt for prompt in interface["defaultPrompt"])


def test_vera_whatsapp_shared_service_records_ingestion_and_retrieval() -> None:
    service = json.loads(SERVICE.read_text(encoding="utf-8"))
    boundaries = service["boundaries_beyond_codex"]

    assert service["service_id"] == "whatsapp-business-archive"
    assert service["governed_repository_paths"] == [
        "chatgpt-app-submission.json",
        "config/secrets.example.toml",
        "docs/deployment/vera_whatsapp_business.md",
        "modules/auth",
        "modules/pdp/api.py",
        "modules/pdp/legal_content.py",
        "modules/whatsapp_business",
    ]
    assert {control["id"] for control in service["security_controls"]} == {
        "signed-webhook-before-parse",
        "signed-account-and-tenant-isolation",
        "bounded-read-only-mcp",
        "resource-bound-pkce-oauth",
        "retention-and-user-deletion",
        "fail-closed-hosted-storage",
    }
    assert [boundary["activation"] for boundary in boundaries] == [
        "automatic_after_prior_connection",
        "explicit_user_choice",
    ]
    assert "90 days" in boundaries[0]["retention"]
    assert "raw webhook" in boundaries[0]["content"]
    assert "location events" in boundaries[0]["content"]
    assert "exactly one full client phone" in boundaries[1]["controls"][2]
    assert "no send, reply, history-import" in boundaries[1]["controls"][3]
