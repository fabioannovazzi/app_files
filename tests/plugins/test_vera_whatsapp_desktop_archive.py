"""Contracts for Vera's local WhatsApp Desktop request and communication route."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERA_ROOT = ROOT / "plugins" / "vera"
WRAPPER = VERA_ROOT / "skills" / "studio-archive" / "SKILL.md"
REFERENCE = (
    VERA_ROOT / "skills" / "studio-archive" / "references" / "whatsapp-desktop.md"
)
EVALS = VERA_ROOT / "evals" / "whatsapp_desktop_cases.json"
MANIFEST = VERA_ROOT / ".codex-plugin" / "plugin.json"
COMPONENTS = VERA_ROOT / "components.json"
PRIVACY = VERA_ROOT / "privacy" / "workstreams" / "studio-archive.json"
HOSTED_SERVICE = VERA_ROOT / "privacy" / "services" / "whatsapp-business-archive.json"


def test_vera_routes_local_whatsapp_desktop_before_other_archive_routes() -> None:
    wrapper = WRAPPER.read_text(encoding="utf-8")
    reference = REFERENCE.read_text(encoding="utf-8")

    assert wrapper.index("asks to inspect WhatsApp") < wrapper.index(
        "asks to search Gmail"
    )
    assert "references/whatsapp-desktop.md" in wrapper
    assert "Computer Use" in wrapper
    assert "Mparanza" in wrapper
    assert "server" in wrapper
    assert "WhatsApp Web" in wrapper
    assert "whatsapp_account_status" not in wrapper
    assert "configured **With MCP**" not in wrapper
    assert "net.whatsapp.WhatsApp" in reference


def test_local_route_records_authorized_actions_and_preserves_drafts() -> None:
    reference = REFERENCE.read_text(encoding="utf-8")
    compact = " ".join(reference.split())

    for required in (
        "whatsapp-local-v2",
        "one complete client phone number",
        "exact confirmed international phone number",
        "fresh accessibility snapshot before every action",
        "Preserve existing user drafts",
        "without pressing Return",
        "one-to-one",
        "No Mparanza copy",
    ):
        assert required in compact
    assert "mark messages as read" in compact.casefold()
    assert "background" in compact and "synchron" in compact
    for required in (
        "execute=true",
        "uncertain",
        "retry_of",
        "sha256",
        "Windows",
        "Archive failure",
        "contact-info",
        "specific user instruction",
    ):
        assert required in reference


def test_whatsapp_desktop_evals_cover_success_and_failure_paths() -> None:
    payload = json.loads(EVALS.read_text(encoding="utf-8"))

    assert payload["workflow"] == "studio-archive-whatsapp-desktop-computer-use"
    assert payload["adapter"] == "whatsapp-local-v2"
    assert len({case["id"] for case in payload["positive_cases"]}) == len(
        payload["positive_cases"]
    )
    assert len({case["id"] for case in payload["negative_cases"]}) == len(
        payload["negative_cases"]
    )
    serialized = json.dumps(payload, ensure_ascii=False)
    for required in (
        "chatgpt-lightweight-handoff",
        "studio-wide-or-group",
        "write-request",
        "focus-or-identity-uncertain",
        "separate-professional-desktop",
        "authorized-text-file-roundtrip",
        "archive-failure-restart",
        "uncertain-send",
    ):
        assert required in serialized


def test_vera_manifest_uses_approved_capability_copy() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    interface = manifest["interface"]
    approved_description = (
        (ROOT / "docs" / "marketplace_copy" / "vera-long-description.txt")
        .read_text(encoding="utf-8")
        .strip()
    )

    assert manifest["description"].startswith("Vera affianca commercialisti")
    assert interface["shortDescription"] == "Assistente AI x commercialisti"
    assert interface["longDescription"] == approved_description
    assert len(approved_description.split()) <= 120
    assert len(approved_description.split("\n\n")) == 3
    assert "Cerca la corrispondenza del cliente." not in (interface["longDescription"])
    assert "giudizio professionale" in interface["longDescription"]
    assert "New Client" not in interface["longDescription"]
    assert "indicizzare" not in interface["longDescription"]
    assert "consiglia Codex Desktop" not in interface["longDescription"]
    assert len(interface["defaultPrompt"]) == 3
    assert all(len(prompt) <= 128 for prompt in interface["defaultPrompt"])


def test_whatsapp_desktop_is_a_workstream_boundary_not_a_hosted_service() -> None:
    components = json.loads(COMPONENTS.read_text(encoding="utf-8"))
    privacy = json.loads(PRIVACY.read_text(encoding="utf-8"))
    boundary = next(
        item
        for item in privacy["external_boundaries"]
        if item["id"] == "codex-whatsapp-desktop-client-review"
    )
    controls = " ".join(boundary["controls"])

    assert "whatsapp-business-archive" not in components["shared_services"]
    assert not HOSTED_SERVICE.exists()
    assert boundary["kind"] == "external_connector"
    assert boundary["optional"] is True
    assert boundary["requires_confirmation"] is True
    assert "local WhatsApp Desktop" in boundary["destination"]
    assert "no WhatsApp copy is sent to a Mparanza service" in boundary["content"]
    assert "never fall back to WhatsApp Web" in controls
    assert "Preserve existing drafts" in controls
    assert "specific user authorization" in controls
    assert "creates no Mparanza WhatsApp connector" in controls


def test_api_mode_does_not_share_dispatch_authority() -> None:
    reference = " ".join(REFERENCE.read_text(encoding="utf-8").split())

    assert "official API connection is a separate mode" in reference
    assert "never give both modes authority over one request" in reference
