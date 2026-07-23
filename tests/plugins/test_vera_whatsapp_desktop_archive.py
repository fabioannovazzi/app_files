"""Contracts for Vera's local, read-only WhatsApp Desktop route."""

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
    assert "Mparanza server" in wrapper
    assert "WhatsApp Web" in wrapper
    assert "whatsapp_account_status" not in wrapper
    assert "configured **With MCP**" not in wrapper
    assert "net.whatsapp.WhatsApp" in reference


def test_whatsapp_desktop_route_is_one_client_read_only_and_fail_closed() -> None:
    reference = REFERENCE.read_text(encoding="utf-8")
    compact = " ".join(reference.split())

    for required in (
        "whatsapp-desktop-computer-use-v1",
        "one complete client phone number",
        "exact confirmed international phone number",
        "fresh accessibility snapshot before every action",
        "Never type into the message composer",
        "without pressing Return",
        "one-to-one",
        "no Mparanza copy",
    ):
        assert required in compact
    assert "mark messages as read" in compact.casefold()
    assert "background" in compact and "synchron" in compact
    for prohibited in (
        "press Return",
        "reply",
        "forward",
        "react",
        "delete",
        "download",
        "export a chat",
        "save screenshots",
        "change account",
    ):
        assert prohibited in reference


def test_whatsapp_desktop_evals_cover_success_and_failure_paths() -> None:
    payload = json.loads(EVALS.read_text(encoding="utf-8"))

    assert payload["workflow"] == "studio-archive-whatsapp-desktop-computer-use"
    assert payload["adapter"] == "whatsapp-desktop-computer-use-v1"
    assert len(payload["positive_cases"]) == 5
    assert len(payload["negative_cases"]) == 5
    assert len({case["id"] for case in payload["positive_cases"]}) == 5
    assert len({case["id"] for case in payload["negative_cases"]}) == 5
    serialized = json.dumps(payload, ensure_ascii=False)
    for required in (
        "not-codex-desktop",
        "studio-wide-or-group",
        "write-request",
        "focus-or-identity-uncertain",
        "separate-professional-desktop",
    ):
        assert required in serialized


def test_vera_manifest_remains_broad_and_requires_codex_desktop() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    interface = manifest["interface"]

    assert manifest["version"] == "0.1.30"
    assert manifest["description"].startswith("Vera affianca il commercialista")
    assert "Codex Desktop" in interface["longDescription"]
    assert "ChatGPT web o mobile si ferma" in interface["longDescription"]
    assert "Computer Use" in interface["longDescription"]
    assert "controlla evidenze contabili" in interface["longDescription"]
    assert "connettore ospitato" not in interface["longDescription"]
    assert len(interface["defaultPrompt"]) == 3
    assert all(len(prompt) <= 128 for prompt in interface["defaultPrompt"])
    assert any("WhatsApp Desktop" in prompt for prompt in interface["defaultPrompt"])


def test_whatsapp_desktop_is_a_workstream_boundary_not_a_hosted_service() -> None:
    components = json.loads(COMPONENTS.read_text(encoding="utf-8"))
    privacy = json.loads(PRIVACY.read_text(encoding="utf-8"))
    boundary = next(
        item
        for item in privacy["boundaries_beyond_codex"]
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
    assert "never type in the composer" in controls
    assert "creates no Mparanza WhatsApp connector" in controls


def test_future_connector_replaces_only_the_access_adapter() -> None:
    reference = " ".join(REFERENCE.read_text(encoding="utf-8").split())

    assert "If a trusted native WhatsApp connector becomes available later" in reference
    assert "replace this adapter only" in reference
    assert "one-client, read-only, fail-closed routing" in reference
