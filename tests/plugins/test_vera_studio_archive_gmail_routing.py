from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_CORE_PATH = ROOT / "plugins" / "studio-archive" / "scripts" / "archive_core.py"
SKILL_PATH = (
    ROOT / "plugins" / "studio-archive" / "skills" / "studio-archive" / "SKILL.md"
)
VERA_WRAPPER_PATH = ROOT / "plugins" / "vera" / "skills" / "studio-archive" / "SKILL.md"
MARKETPLACE_REFERENCE_PATH = (
    ROOT
    / "plugins"
    / "vera"
    / "skills"
    / "studio-archive"
    / "references"
    / "marketplace-gmail.md"
)
MARKETPLACE_CASES_PATH = (
    ROOT / "plugins" / "vera" / "evals" / "marketplace_gmail_cases.json"
)
PRIVACY_MANIFEST_PATH = (
    ROOT / "plugins" / "vera" / "privacy" / "workstreams" / "studio-archive.json"
)


@pytest.fixture(scope="module")
def archive_core() -> ModuleType:
    """Load the Studio Archive core from repository source."""

    module_name = "test_vera_studio_archive_gmail_core"
    spec = importlib.util.spec_from_file_location(module_name, ARCHIVE_CORE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def configured_clients(
    tmp_path: Path,
    archive_core: ModuleType,
) -> SimpleNamespace:
    """Configure two exact client scopes without indexing mailbox content."""

    archive_root = tmp_path / "Studio"
    (archive_root / "Rossi").mkdir(parents=True)
    (archive_root / "Bianchi").mkdir()
    state_dir = tmp_path / "private-state"
    configured = archive_core.configure_archive(archive_root, state_dir=state_dir)
    scopes = {item["display_name"]: item["scope_id"] for item in configured["scopes"]}
    return SimpleNamespace(root=archive_root, state=state_dir, scopes=scopes)


def _configure_two_profiles(
    archive_core: ModuleType,
    configured_clients: SimpleNamespace,
) -> None:
    archive_core.set_studio_client_identity(
        configured_clients.scopes["Rossi"],
        email_addresses=["amministrazione@rossi.it"],
        legal_names=["Rossi SRL"],
        tax_identifiers=["01234567890"],
        state_dir=configured_clients.state,
    )
    archive_core.set_studio_client_identity(
        configured_clients.scopes["Bianchi"],
        email_addresses=["contabilita@bianchi.it"],
        legal_names=["Bianchi SRL"],
        tax_identifiers=["10987654321"],
        state_dir=configured_clients.state,
    )


def test_client_profile_is_private_normalized_and_idempotent(
    archive_core: ModuleType,
    configured_clients: SimpleNamespace,
) -> None:
    scope_id = configured_clients.scopes["Rossi"]

    first = archive_core.set_studio_client_identity(
        scope_id,
        email_addresses=["AMMINISTRAZIONE@ROSSI.IT"],
        legal_names=["  Rossi   SRL  "],
        tax_identifiers=["01234567890"],
        state_dir=configured_clients.state,
    )
    registry_path = configured_clients.state / "client-identities.json"
    before = registry_path.read_bytes()
    second = archive_core.set_studio_client_identity(
        scope_id,
        email_addresses=["amministrazione@rossi.it"],
        legal_names=["Rossi SRL"],
        tax_identifiers=["01234567890"],
        state_dir=configured_clients.state,
    )

    assert first["status"] == "configured"
    assert second["status"] == "unchanged"
    assert second["client"]["email_addresses"] == ["amministrazione@rossi.it"]
    assert second["client"]["legal_names"] == ["Rossi SRL"]
    assert registry_path.read_bytes() == before
    assert stat.S_IMODE(configured_clients.state.stat().st_mode) == 0o700
    if os.name == "posix":
        assert stat.S_IMODE(registry_path.stat().st_mode) == 0o600


def test_duplicate_exact_identifier_is_rejected_without_changing_registry(
    archive_core: ModuleType,
    configured_clients: SimpleNamespace,
) -> None:
    archive_core.set_studio_client_identity(
        configured_clients.scopes["Rossi"],
        email_addresses=["amministrazione@rossi.it"],
        tax_identifiers=["01234567890"],
        state_dir=configured_clients.state,
    )
    registry_path = configured_clients.state / "client-identities.json"
    before = registry_path.read_bytes()

    with pytest.raises(
        archive_core.ArchiveError,
        match="assigned to more than one scope",
    ):
        archive_core.set_studio_client_identity(
            configured_clients.scopes["Bianchi"],
            email_addresses=["AMMINISTRAZIONE@ROSSI.IT"],
            state_dir=configured_clients.state,
        )

    assert registry_path.read_bytes() == before


def test_client_profile_rejects_gmail_query_metacharacters_in_address(
    archive_core: ModuleType,
    configured_clients: SimpleNamespace,
) -> None:
    with pytest.raises(archive_core.ArchiveError, match="email address is invalid"):
        archive_core.set_studio_client_identity(
            configured_clients.scopes["Rossi"],
            email_addresses=["rossi{to:bianchi}@example.com"],
            state_dir=configured_clients.state,
        )


def test_alias_only_scope_returns_bootstrap_candidates_not_exact_routing(
    archive_core: ModuleType,
    configured_clients: SimpleNamespace,
) -> None:
    result = archive_core.plan_gmail_client_search(
        configured_clients.scopes["Rossi"],
        state_dir=configured_clients.state,
    )

    assert result["profile_status"] == "alias_only"
    assert [query["kind"] for query in result["queries"]] == ["identity_candidate"]
    assert '"Rossi"' in result["queries"][0]["query"]
    assert result["warnings"]
    assert result["gmail_connector_called"] is False


def test_gmail_plan_is_bounded_to_selected_client_and_neutralizes_operators(
    archive_core: ModuleType,
    configured_clients: SimpleNamespace,
) -> None:
    _configure_two_profiles(archive_core, configured_clients)

    result = archive_core.plan_gmail_client_search(
        configured_clients.scopes["Rossi"],
        topic="rateazione} OR from:contabilita@bianchi.it",
        after="2026-01-01",
        before="2027-01-01",
        state_dir=configured_clients.state,
    )

    direct_query = next(
        query["query"]
        for query in result["queries"]
        if query["kind"] == "confirmed_participant"
    )
    assert "from:amministrazione@rossi.it" in direct_query
    assert "to:amministrazione@rossi.it" in direct_query
    assert "after:2026/01/01" in direct_query
    assert "before:2027/01/01" in direct_query
    assert "from:contabilita@bianchi.it" not in direct_query
    assert '"rateazione OR from contabilita@bianchi.it"' in direct_query
    assert all(query["max_results"] == 20 for query in result["queries"])


def test_gmail_plan_rejects_studio_wide_scope(
    archive_core: ModuleType,
    configured_clients: SimpleNamespace,
) -> None:
    with pytest.raises(
        archive_core.ArchiveError,
        match="Studio-wide Gmail search is not supported",
    ):
        archive_core.plan_gmail_client_search(
            "all",
            state_dir=configured_clients.state,
        )


def test_exact_address_routes_only_the_expected_client(
    archive_core: ModuleType,
    configured_clients: SimpleNamespace,
) -> None:
    _configure_two_profiles(archive_core, configured_clients)

    result = archive_core.match_studio_email_client(
        [
            "Rossi SRL <AMMINISTRAZIONE@ROSSI.IT>",
            "Studio <professionista@example.com>",
        ],
        headers_complete=True,
        expected_scope_id=configured_clients.scopes["Rossi"],
        state_dir=configured_clients.state,
    )

    assert result["routing_status"] == "exact"
    assert result["matched_scope_id"] == configured_clients.scopes["Rossi"]
    assert result["belongs_to_expected_scope"] is True
    assert result["may_use_in_scoped_answer"] is True
    assert result["requires_semantic_review"] is False


def test_exact_other_client_is_excluded_from_selected_client_answer(
    archive_core: ModuleType,
    configured_clients: SimpleNamespace,
) -> None:
    _configure_two_profiles(archive_core, configured_clients)

    result = archive_core.match_studio_email_client(
        ["Bianchi <contabilita@bianchi.it>"],
        headers_complete=True,
        expected_scope_id=configured_clients.scopes["Rossi"],
        state_dir=configured_clients.state,
    )

    assert result["routing_status"] == "exact"
    assert result["matched_scope_id"] == configured_clients.scopes["Bianchi"]
    assert result["belongs_to_expected_scope"] is False
    assert result["may_use_in_scoped_answer"] is False


def test_message_with_two_clients_is_ambiguous_and_fails_closed(
    archive_core: ModuleType,
    configured_clients: SimpleNamespace,
) -> None:
    _configure_two_profiles(archive_core, configured_clients)

    result = archive_core.match_studio_email_client(
        [
            "amministrazione@rossi.it",
            "contabilita@bianchi.it",
        ],
        headers_complete=True,
        expected_scope_id=configured_clients.scopes["Rossi"],
        state_dir=configured_clients.state,
    )

    assert result["routing_status"] == "ambiguous"
    assert result["matched_scope_id"] is None
    assert result["candidate_scope_ids"] == sorted(configured_clients.scopes.values())
    assert result["belongs_to_expected_scope"] is None
    assert result["may_use_in_scoped_answer"] is False
    assert result["requires_semantic_review"] is True


def test_unmatched_third_party_message_is_not_persisted_or_auto_assigned(
    archive_core: ModuleType,
    configured_clients: SimpleNamespace,
) -> None:
    _configure_two_profiles(archive_core, configured_clients)
    marker = "outside-lawyer-unique@example.net"

    result = archive_core.match_studio_email_client(
        [marker],
        headers_complete=True,
        expected_scope_id=configured_clients.scopes["Rossi"],
        state_dir=configured_clients.state,
    )

    assert result["routing_status"] == "unassigned"
    assert result["candidate_scope_ids"] == []
    assert result["may_use_in_scoped_answer"] is False
    assert result["gmail_data_persisted"] is False
    for path in configured_clients.state.iterdir():
        if path.is_file():
            assert marker.encode("utf-8") not in path.read_bytes()


def test_renamed_scope_profile_can_be_explicitly_rebound_after_refresh(
    archive_core: ModuleType,
    configured_clients: SimpleNamespace,
) -> None:
    rossi_scope = configured_clients.scopes["Rossi"]
    archive_core.set_studio_client_identity(
        rossi_scope,
        email_addresses=["amministrazione@rossi.it"],
        state_dir=configured_clients.state,
    )
    (configured_clients.root / "Rossi").rename(configured_clients.root / "Rossi-Nuovo")

    profiles = archive_core.list_studio_client_identities(
        state_dir=configured_clients.state,
    )

    assert profiles["scope_configuration_changed"] is True
    assert profiles["orphaned_profile_count"] == 1
    assert profiles["orphaned_profiles"][0]["scope_id"] == rossi_scope
    with pytest.raises(archive_core.ArchiveError, match="refresh before planning"):
        archive_core.plan_gmail_client_search(
            rossi_scope,
            state_dir=configured_clients.state,
        )
    refreshed = archive_core.refresh_archive(state_dir=configured_clients.state)
    renamed_scope = next(
        item["scope_id"]
        for item in refreshed["scopes"]
        if item["display_name"] == "Rossi-Nuovo"
    )

    rebound = archive_core.set_studio_client_identity(
        renamed_scope,
        replace_orphaned_scope_id=rossi_scope,
        state_dir=configured_clients.state,
    )
    plan = archive_core.plan_gmail_client_search(
        renamed_scope,
        state_dir=configured_clients.state,
    )

    assert rebound["status"] == "rebound"
    assert rebound["replaced_orphaned_scope_id"] == rossi_scope
    assert rebound["client"]["email_addresses"] == ["amministrazione@rossi.it"]
    assert plan["profile_status"] == "configured"


@pytest.mark.parametrize(
    "header_values",
    [
        ["amministrazione@rossi.it", "not an address"],
        ["Rossi <amministrazione@rossi.it>, not an address"],
    ],
)
def test_incomplete_or_unparseable_headers_never_route_automatically(
    header_values: list[str],
    archive_core: ModuleType,
    configured_clients: SimpleNamespace,
) -> None:
    _configure_two_profiles(archive_core, configured_clients)

    result = archive_core.match_studio_email_client(
        header_values,
        headers_complete=True,
        expected_scope_id=configured_clients.scopes["Rossi"],
        state_dir=configured_clients.state,
    )

    assert result["routing_status"] == "incomplete"
    assert result["matched_scope_id"] is None
    assert result["header_coverage_complete"] is False
    assert result["unparsed_header_count"] == 1
    assert result["may_use_in_scoped_answer"] is False


def test_known_bcc_address_makes_cross_client_message_ambiguous(
    archive_core: ModuleType,
    configured_clients: SimpleNamespace,
) -> None:
    _configure_two_profiles(archive_core, configured_clients)

    result = archive_core.match_studio_email_client(
        [
            "From: amministrazione@rossi.it",
            "Bcc: contabilita@bianchi.it",
        ],
        headers_complete=True,
        expected_scope_id=configured_clients.scopes["Rossi"],
        state_dir=configured_clients.state,
    )

    assert result["routing_status"] == "ambiguous"
    assert result["candidate_scope_ids"] == sorted(configured_clients.scopes.values())
    assert result["may_use_in_scoped_answer"] is False


def test_headers_default_to_incomplete_when_connector_coverage_is_unknown(
    archive_core: ModuleType,
    configured_clients: SimpleNamespace,
) -> None:
    _configure_two_profiles(archive_core, configured_clients)

    result = archive_core.match_studio_email_client(
        ["amministrazione@rossi.it"],
        expected_scope_id=configured_clients.scopes["Rossi"],
        state_dir=configured_clients.state,
    )

    assert result["routing_status"] == "incomplete"
    assert result["header_coverage_complete"] is False
    assert result["may_use_in_scoped_answer"] is False


def test_registry_contains_no_gmail_credentials_or_message_content(
    archive_core: ModuleType,
    configured_clients: SimpleNamespace,
) -> None:
    archive_core.set_studio_client_identity(
        configured_clients.scopes["Rossi"],
        email_addresses=["amministrazione@rossi.it"],
        state_dir=configured_clients.state,
    )

    payload = json.loads(
        (configured_clients.state / "client-identities.json").read_text(
            encoding="utf-8"
        )
    )

    serialized = json.dumps(payload).casefold()
    assert "password" not in serialized
    assert "token" not in serialized
    assert "cookie" not in serialized
    assert "message_id" not in serialized
    assert "body" not in serialized


def test_component_has_independent_marketplace_and_optional_local_gmail_routes() -> (
    None
):
    skill = SKILL_PATH.read_text(encoding="utf-8")
    compact_skill = " ".join(skill.split())
    marketplace = compact_skill.split("## Marketplace Gmail workflow", maxsplit=1)[
        1
    ].split("## Optional local Gmail enhancement", maxsplit=1)[0]
    local_enhancement = compact_skill.split(
        "## Optional local Gmail enhancement",
        maxsplit=1,
    )[1]

    for required in (
        "get_profile",
        "search_emails",
        "batch_read_email",
        "read_email_thread",
        "read_attachment",
        "chat-scoped",
        "at most 20 results per page",
        "absence of an optional Cc or Bcc field alone is not incomplete",
        "cannot prove the absence of an undisclosed Bcc recipient",
    ):
        assert required in marketplace
    assert marketplace.index("get_profile") < marketplace.index("search_emails")
    assert marketplace.index("search_emails") < marketplace.index("batch_read_email")
    for local_dependency in (
        "plan_studio_archive_gmail_search",
        "match_studio_archive_email",
        "configure_studio_archive_client",
        "python scripts/studio_archive.py",
    ):
        assert local_dependency not in marketplace

    for optional_local_tool in (
        "plan_studio_archive_gmail_search",
        "match_studio_archive_email",
    ):
        assert optional_local_tool in local_enhancement


def test_vera_marketplace_wrapper_routes_gmail_without_local_dependencies() -> None:
    wrapper = " ".join(VERA_WRAPPER_PATH.read_text(encoding="utf-8").split())
    reference = " ".join(MARKETPLACE_REFERENCE_PATH.read_text(encoding="utf-8").split())

    assert "references/marketplace-gmail.md" in wrapper
    assert wrapper.index("get_profile") < wrapper.index("resolve `../../modules")
    assert "Do not resolve the local module" in wrapper
    assert "separately distributed OpenAI Gmail plugin" in wrapper
    assert "does not require a local ZIP" in wrapper
    assert reference.index("get_profile") < reference.index("search_emails")
    assert reference.index("search_emails") < reference.index("batch_read_email")
    for local_dependency in (
        "plan_studio_archive_gmail_search",
        "match_studio_archive_email",
        "configure_studio_archive_client",
        "python scripts/studio_archive.py",
    ):
        assert local_dependency not in reference
    for prohibited_action in (
        "send",
        "archive",
        "delete",
        "label",
        "move",
        "IMAP",
        "scrape the browser",
    ):
        assert prohibited_action in reference
    assert "current conversation" in reference
    assert (
        "no local archive, local ZIP, MCP tool, script, or saved registry" in reference
    )
    assert "max_results: 10" in reference
    assert "at most 20 results per page" in reference
    assert "absent optional Cc or Bcc field" in reference
    assert "cannot prove the absence of an undisclosed Bcc recipient" in reference


def test_marketplace_gmail_reviewer_cases_cover_success_and_failure_paths() -> None:
    cases = json.loads(MARKETPLACE_CASES_PATH.read_text(encoding="utf-8"))

    assert len(cases["positive_cases"]) == 5
    assert len(cases["negative_cases"]) == 3
    assert len(cases["synthetic_fixture"]["messages"]) == 5
    assert all("expected_result" in case for case in cases["positive_cases"])
    assert all("why" in case for case in cases["negative_cases"])
    serialized = json.dumps(cases)
    for required in (
        "confirmed-address",
        "discover-and-confirm",
        "multiple-confirmed-addresses",
        "mixed-thread",
        "separate-professional-account",
        "gmail-unavailable",
        "all-clients",
        "ambiguous-message",
    ):
        assert required in serialized


def test_privacy_manifest_records_marketplace_gmail_and_optional_local_registry() -> (
    None
):
    manifest = json.loads(PRIVACY_MANIFEST_PATH.read_text(encoding="utf-8"))
    boundary = next(
        item
        for item in manifest["boundaries_beyond_codex"]
        if item["id"] == "codex-gmail-client-search"
    )
    controls = {item["id"]: item["control"] for item in manifest["security_controls"]}

    assert boundary["kind"] == "external_connector"
    assert boundary["optional"] is True
    assert boundary["requires_confirmation"] is True
    assert (
        "separately installed and connected OpenAI Gmail plugin"
        in boundary["destination"]
    )
    joined_controls = " ".join(boundary["controls"])
    assert "Call get_profile before every search" in joined_controls
    assert "at most ten results for address discovery" in joined_controls
    assert "current conversation" in joined_controls
    assert "absence of an optional Cc or Bcc field alone is not incomplete" in (
        joined_controls
    )
    assert "private-client-identity-registry" in controls
    assert (
        "no plugin-managed cross-chat registry"
        in controls["private-client-identity-registry"]
    )
    assert "fail-closed-gmail-client-routing" in controls
    assert "explicit one-to-one rebind" in controls["fail-closed-gmail-client-routing"]
