"""Keep valid client work usable while preserving damaged sibling evidence."""

from __future__ import annotations

import errno
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/studio-archive/scripts"))
    import archive_core as core

    state = tmp_path / "state"
    studio = tmp_path / "Studio"
    studio.mkdir()
    monkeypatch.delenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", raising=False)
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_STATE_DIR", str(state))
    core.configure_archive(studio, state_dir=state)
    created = core.create_studio_client("Synthetic healthy client", state_dir=state)
    cid = created["client"]["client_id"]
    root = Path(
        core.get_studio_client_folder(cid, state_dir=state)["client_folder"][
            "client_root"
        ]
    )
    engagement = core.create_studio_client_engagement(
        cid, "Existing work", state_dir=state
    )["engagement"]["engagement_id"]
    source = tmp_path / "source.txt"
    source.write_text("Synthetic retained source", encoding="utf-8")
    imported = core.import_studio_client_document(
        cid, source, "source", engagement_id=engagement, state_dir=state
    )
    return core, studio, state, root, cid, engagement, imported["input_id"]


def test_damaged_unrelated_client_does_not_prevent_selected_continuation(case):
    core, studio, state, root, cid, eid, input_id = case
    other = core.create_studio_client("Synthetic damaged client", state_dir=state)
    other_id = other["client"]["client_id"]
    other_root = Path(
        core.get_studio_client_folder(other_id, state_dir=state)["client_folder"][
            "client_root"
        ]
    )
    manifest = other_root / "Vera/client.json"
    manifest.write_bytes(b"{}")

    selected = core.get_studio_client_folder(cid, state_dir=state)

    assert selected["client_folder"]["client_root"] == str(root)
    directory = core.list_studio_clients(state_dir=state)
    assert directory["blocked_clients"][0]["available"] is False
    assert manifest.read_bytes() == b"{}"
    with pytest.raises(core.ArchiveError):
        core.get_studio_client_folder(other_id, state_dir=state)


@pytest.mark.parametrize("operation", ["select", "prepare"])
def test_selected_work_does_not_depend_on_or_rewrite_damaged_alias_registry(
    case, operation
):
    core, studio, state, root, cid, eid, input_id = case
    registry = core._client_identities_path(state)
    payload = json.loads(registry.read_text())
    payload["clients"].append({"unrelated_invalid_record": True})
    retained = json.dumps(payload).encode()
    registry.write_bytes(retained)
    actions = {
        "select": lambda: core.get_studio_client_folder(cid, state_dir=state),
        "prepare": lambda: core.prepare_studio_client_workflow(
            eid, "financial-analysis", input_ids=[input_id], state_dir=state
        ),
    }

    result = actions[operation]()

    assert result["status"] == {"select": "ready", "prepare": "prepared"}[operation]
    assert registry.read_bytes() == retained
    assert core.ledger.load_client_manifest(root)["client_id"] == cid


def test_client_directory_retains_healthy_aliases_beside_damaged_record(case):
    core, studio, state, root, cid, eid, input_id = case
    registry = core._client_identities_path(state)
    payload = json.loads(registry.read_text())
    payload["clients"].append({"unrelated_invalid_record": True})
    retained = json.dumps(payload).encode()
    registry.write_bytes(retained)

    result = core.list_studio_clients(state_dir=state)

    assert result["registered_client_count"] == 1
    assert result["clients"][0]["client_id"] == cid
    assert result["identity_registry_complete"] is False
    assert result["identity_issues"][0]["issue_code"] == "invalid_identity_record"
    assert registry.read_bytes() == retained


def test_malformed_alias_file_does_not_hide_portable_client_identity(case):
    core, studio, state, root, cid, eid, input_id = case
    registry = core._client_identities_path(state)
    retained = b"{interrupted registry write"
    registry.write_bytes(retained)

    result = core.list_studio_clients(state_dir=state)

    assert result["clients"][0]["client_id"] == cid
    assert result["directory_complete"] is False
    assert result["identity_issues"][0]["issue_code"] == "identity_registry_unavailable"
    assert registry.read_bytes() == retained


@pytest.mark.parametrize("location", ["shared", "legacy"])
def test_unavailable_alias_metadata_does_not_hide_portable_client_identity(
    case, monkeypatch, location
):
    core, studio, state, root, cid, eid, input_id = case
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", str(state.parent / "profile"))
    core.configure_archive(studio, state_dir=state)
    registry = {
        "shared": core._client_identities_path(state),
        "legacy": state / core.CLIENT_IDENTITIES_FILENAME,
    }[location]
    original = Path.stat

    def unavailable(path, *args, **kwargs):
        if path == registry:
            raise PermissionError(errno.EACCES, "Synthetic unavailable alias metadata")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", unavailable)

    result = core.list_studio_clients(state_dir=state)

    assert result["clients"][0]["client_id"] == cid
    assert result["identity_registry_complete"] is False
    assert result["identity_issues"][0]["issue_code"] == "identity_registry_unavailable"


def test_optional_folder_cache_write_failure_does_not_block_client_listing(
    case, monkeypatch
):
    core, studio, state, root, cid, eid, input_id = case
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", str(state.parent / "profile"))
    core.configure_archive(studio, state_dir=state)
    cache = core._profile_registry_directory(state) / "known-scopes.json"
    retained = cache.read_bytes()
    (studio / "New unrelated folder").mkdir()
    original = core._write_private_json

    def unavailable(path, payload):
        if path == cache:
            raise PermissionError(errno.EACCES, "Synthetic unavailable cache write")
        return original(path, payload)

    monkeypatch.setattr(core, "_write_private_json", unavailable)

    result = core.list_studio_clients(state_dir=state)

    assert result["registered_client_count"] == 1
    assert result["directory_complete"] is True
    assert result["scope_cache"]["status"] == "unavailable"
    assert cache.read_bytes() == retained
    assert core.ledger.load_client_manifest(root)["client_id"] == cid


@pytest.mark.parametrize("operation", ["plan", "match"])
def test_gmail_identity_operations_do_not_require_an_index_refresh(case, operation):
    core, studio, state, root, cid, eid, input_id = case
    scope = core.get_studio_client_folder(cid, state_dir=state)["client_folder"][
        "scope_id"
    ]
    core.set_studio_client_identity(
        scope, email_addresses=["synthetic@example.test"], state_dir=state
    )
    (studio / "Unrelated new folder").mkdir()
    actions = {
        "plan": lambda: core.plan_gmail_client_search(scope, state_dir=state),
        "match": lambda: core.match_studio_email_client(
            ["synthetic@example.test"],
            headers_complete=True,
            expected_scope_id=scope,
            state_dir=state,
        ),
    }

    result = actions[operation]()

    assert result["gmail_connector_called"] is False
    assert result["scope_configuration_changed"] is True
    assert (
        result[{"plan": "profile_status", "match": "routing_status"}[operation]]
        == {
            "plan": "configured",
            "match": "exact",
        }[operation]
    )
    assert not (state / core.DATABASE_FILENAME).exists()


@pytest.mark.parametrize("damage", ["aliases", "client_folder"])
def test_email_cannot_be_automatically_routed_with_unavailable_identity_evidence(
    case, damage
):
    core, studio, state, root, cid, eid, input_id = case
    scope = core.get_studio_client_folder(cid, state_dir=state)["client_folder"][
        "scope_id"
    ]
    core.set_studio_client_identity(
        scope, email_addresses=["synthetic@example.test"], state_dir=state
    )
    registry = core._client_identities_path(state)
    payload = json.loads(registry.read_text())
    payload["clients"].append({"invalid_unrelated_identity": True})
    actions = {
        "aliases": lambda: registry.write_text(json.dumps(payload)),
        "client_folder": lambda: shutil.rmtree(root),
    }
    actions[damage]()

    result = core.match_studio_email_client(
        ["synthetic@example.test"], headers_complete=True, state_dir=state
    )

    assert result["routing_status"] == "incomplete"
    assert result["matched_scope_id"] is None
    assert result["may_use_in_scoped_answer"] is False
    assert result["candidate_scope_ids"] == [scope]
    assert result["gmail_connector_called"] is False


def test_index_refresh_does_not_fail_after_commit_on_a_damaged_alias(case):
    core, studio, state, root, cid, eid, input_id = case
    registry = core._client_identities_path(state)
    retained = b"{interrupted alias registry"
    registry.write_bytes(retained)

    result = core.refresh_archive(state_dir=state)

    assert result["status"] == "refreshed"
    assert result["identity_registry_complete"] is False
    assert registry.read_bytes() == retained
    assert core.ledger.load_client_manifest(root)["client_id"] == cid


@pytest.mark.parametrize(
    "query,expected",
    [
        ("Synthetic healthy client", "exact_match"),
        ("Unrecorded client", "incomplete"),
    ],
)
def test_partial_identity_lookup_preserves_known_match_without_claiming_absence(
    case, query, expected
):
    core, studio, state, root, cid, eid, input_id = case
    registry = core._client_identities_path(state)
    payload = json.loads(registry.read_text())
    payload["clients"].append({"unrelated_invalid_record": True})
    retained = json.dumps(payload).encode()
    registry.write_bytes(retained)

    result = core.resolve_studio_client_identity("legal_name", query, state_dir=state)

    assert result["resolution_status"] == expected
    assert result["resolution_complete"] is False
    assert registry.read_bytes() == retained


def test_known_selected_client_remains_available_when_root_cannot_be_listed(
    case, monkeypatch
):
    core, studio, state, root, cid, eid, input_id = case
    original = Path.iterdir

    def unavailable(path):
        if path == studio:
            raise PermissionError(errno.EACCES, "Synthetic unavailable root listing")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", unavailable)

    result = core.get_studio_client_folder(cid, state_dir=state)

    assert result["status"] == "ready"
    assert result["client_folder"]["client_root"] == str(root)
    assert result["directory_complete"] is False
    assert result["directory_issues"][0]["issue_code"] == "scope_listing_unavailable"


def test_fresh_session_uses_known_folders_when_root_listing_is_unavailable(
    case, monkeypatch
):
    core, studio, state, root, cid, eid, input_id = case
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", str(state.parent / "profile"))
    core.configure_archive(studio, state_dir=state)
    retained = (root / "Vera/client.json").read_bytes()
    original = Path.iterdir

    def unavailable(path):
        if path == studio:
            raise PermissionError(errno.EACCES, "Synthetic unavailable root listing")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", unavailable)
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_SESSION_ID", "known-root-recovery")

    result = core.get_studio_client_folder(cid, state_dir=state.parent / "new-session")

    assert result["status"] == "ready"
    assert result["client_folder"]["client_root"] == str(root)
    assert result["directory_complete"] is False
    assert result["directory_issues"][0]["known_scopes_only"] is True
    assert (root / "Vera/client.json").read_bytes() == retained


def test_saved_folder_location_cannot_authorize_a_changed_client_identity(
    case, monkeypatch, tmp_path
):
    core, studio, state, root, cid, eid, input_id = case
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", str(state.parent / "profile"))
    core.configure_archive(studio, state_dir=state)
    replacement = tmp_path / "Replacement"
    replacement.mkdir()
    core.ledger.create_client_manifest(replacement, "client_" + "f" * 24)
    changed = (replacement / "Vera/client.json").read_bytes()
    (root / "Vera/client.json").write_bytes(changed)
    original = Path.iterdir

    def unavailable(path):
        if path == studio:
            raise PermissionError(errno.EACCES, "Synthetic unavailable root listing")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", unavailable)
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_SESSION_ID", "changed-root-recovery")

    with pytest.raises(
        core.ArchiveError, match="selected client identity is unavailable"
    ):
        core.get_studio_client_folder(cid, state_dir=state.parent / "new-session")

    assert (root / "Vera/client.json").read_bytes() == changed


def test_invalid_saved_location_is_preserved_and_cannot_escape_selected_archive(
    case, monkeypatch
):
    core, studio, state, root, cid, eid, input_id = case
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", str(state.parent / "profile"))
    core.configure_archive(studio, state_dir=state)
    cache = core._profile_registry_directory(state) / "known-scopes.json"
    payload = json.loads(cache.read_text())
    payload["scopes"][0]["relative_dir"] = "../outside"
    retained = json.dumps(payload).encode()
    cache.write_bytes(retained)
    original = Path.iterdir

    def unavailable(path):
        if path == studio:
            raise PermissionError(errno.EACCES, "Synthetic unavailable root listing")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", unavailable)
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_SESSION_ID", "invalid-root-recovery")

    with pytest.raises(core.ArchiveError, match="not an immediate child"):
        core.get_studio_client_folder(cid, state_dir=state.parent / "new-session")

    assert cache.read_bytes() == retained
    assert not (state.parent / "new-session/config.json").exists()


def test_reading_known_clients_does_not_require_identity_write_lock(case, monkeypatch):
    core, studio, state, root, cid, eid, input_id = case
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", str(state.parent / "profile"))
    core.configure_archive(studio, state_dir=state)
    core.list_studio_clients(state_dir=state)

    def forbidden(*args, **kwargs):
        raise AssertionError("A read must not wait for an identity mutation")

    monkeypatch.setattr(core.preferences, "registry_lock", forbidden)

    result = core.list_studio_clients(state_dir=state)

    assert result["clients"][0]["client_id"] == cid
    assert result["identity_registry_complete"] is True


@pytest.mark.parametrize("registered", [False, True])
def test_unreadable_unrelated_folder_does_not_block_selected_preparation(
    case, monkeypatch, registered
):
    core, studio, state, root, cid, eid, input_id = case
    other = studio / "Unavailable folder"
    if registered:
        core.create_studio_client(other.name, state_dir=state)
    else:
        other.mkdir()
    original = Path.lstat
    original_manifest = (root / "Vera/client.json").read_bytes()

    def unavailable(path, *args, **kwargs):
        if path == other:
            raise PermissionError(errno.EACCES, "Synthetic unavailable metadata")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", unavailable)

    result = core.prepare_studio_client_workflow(
        eid, "financial-analysis", input_ids=[input_id], state_dir=state
    )

    assert result["status"] == "prepared"
    assert result["client_id"] == cid
    assert result["directory_complete"] is False
    assert result["blocked_clients"][0]["issue_code"] == "scope_metadata_unavailable"
    assert result["blocked_clients"][0]["relative_dir"] == other.name
    assert (root / "Vera/client.json").read_bytes() == original_manifest


def test_unreadable_scope_is_shown_beside_healthy_client_and_stays_unselectable(
    case, monkeypatch
):
    core, studio, state, root, cid, eid, input_id = case
    other = core.create_studio_client("Unavailable client", state_dir=state)
    other_id = other["client"]["client_id"]
    other_root = studio / "Unavailable client"
    original = Path.lstat

    def unavailable(path, *args, **kwargs):
        if path == other_root:
            raise PermissionError(errno.EACCES, "Synthetic unavailable metadata")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", unavailable)

    result = core.list_studio_clients(state_dir=state)

    assert result["directory_complete"] is False
    healthy = next(row for row in result["clients"] if row["client_id"] == cid)
    blocked = next(row for row in result["clients"] if row["client_id"] == other_id)
    assert healthy["registration_status"] == "registered"
    assert blocked["registration_status"] == "blocked"
    assert core.get_studio_client_folder(cid, state_dir=state)["status"] == "ready"
    with pytest.raises(core.ArchiveError, match="metadata is unavailable"):
        core.get_studio_client_folder(other_id, state_dir=state)


def test_fresh_session_recovers_healthy_client_despite_unreadable_sibling(
    case, monkeypatch
):
    core, studio, state, root, cid, eid, input_id = case
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", str(state.parent / "profile"))
    core.configure_archive(studio, state_dir=state)
    other = studio / "Unavailable sibling"
    other.mkdir()
    original = Path.lstat

    def unavailable(path, *args, **kwargs):
        if path == other:
            raise PermissionError(errno.EACCES, "Synthetic unavailable metadata")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", unavailable)
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_SESSION_ID", "fresh-scope-recovery")

    result = core.get_studio_client_folder(cid, state_dir=state.parent / "fresh-state")

    assert result["status"] == "ready"
    assert result["client_folder"]["client_root"] == str(root)
    assert result["directory_complete"] is False
    assert result["blocked_clients"][0]["relative_dir"] == other.name


def test_colliding_unrelated_scope_names_do_not_hide_healthy_client(case, monkeypatch):
    core, studio, state, root, cid, eid, input_id = case
    other = studio / "Collision"
    other.mkdir()
    alias = studio / "collision"
    original_iterdir = Path.iterdir
    original_lstat = Path.lstat

    def entries(path):
        if path == studio:
            return iter([root, other, alias])
        return original_iterdir(path)

    def metadata(path, *args, **kwargs):
        return original_lstat(other if path == alias else path, *args, **kwargs)

    monkeypatch.setattr(Path, "iterdir", entries)
    monkeypatch.setattr(Path, "lstat", metadata)

    result = core.prepare_studio_client_workflow(
        eid, "financial-analysis", input_ids=[input_id], state_dir=state
    )

    assert result["status"] == "prepared"
    assert result["directory_complete"] is False
    assert result["blocked_clients"][0]["issue_code"] == "scope_name_collision"
    assert result["blocked_clients"][0]["relative_dirs"] == ["Collision", "collision"]


def test_damaged_engagement_does_not_hide_valid_engagement(case):
    core, studio, state, root, cid, eid, input_id = case
    other = core.create_studio_client_engagement(
        cid, "Damaged sibling", state_dir=state
    )["engagement"]["engagement_id"]
    manifest = root / "Vera/engagements" / other / "engagement.json"
    manifest.write_bytes(b"{}")

    result = core.list_studio_client_engagements(cid, state_dir=state)

    assert [row["engagement_id"] for row in result["engagements"]] == [eid]
    assert result["blocked_engagements"][0]["engagement_id"] == other
    assert result["ledger_complete"] is False
    assert manifest.read_bytes() == b"{}"


def test_damaged_unselected_input_does_not_hide_valid_work(case, tmp_path):
    core, studio, state, root, cid, eid, input_id = case
    source = tmp_path / "other.txt"
    source.write_text("Synthetic unrelated input", encoding="utf-8")
    other = core.import_studio_client_document(
        cid, source, "source", engagement_id=eid, state_dir=state
    )["input_id"]
    receipt = root / "Vera/engagements" / eid / "inputs" / other / "receipt.json"
    receipt.write_bytes(b"{}")

    result = core.list_studio_client_engagements(cid, state_dir=state)

    engagement = result["engagements"][0]
    assert [row["input_id"] for row in engagement["imports"]] == [input_id]
    assert engagement["blocked_inputs"][0]["input_id"] == other
    assert engagement["ledger_complete"] is False
    assert receipt.read_bytes() == b"{}"
    with pytest.raises(core.ledger.LedgerError):
        core.ledger.load_input_receipt(root, eid, other)

    note = tmp_path / "continuation.txt"
    note.write_text("Synthetic continuation of valid work", encoding="utf-8")
    saved = core.import_studio_client_document(
        cid, note, "support", engagement_id=eid, state_dir=state
    )
    assert Path(saved["imported_path"]).read_bytes() == note.read_bytes()
    assert saved["engagement"]["blocked_inputs"][0]["input_id"] == other
    assert receipt.read_bytes() == b"{}"


def test_incidental_collection_file_does_not_hide_existing_engagement(case):
    core, studio, state, root, cid, eid, input_id = case
    incidental = root / "Vera/engagements/.DS_Store"
    incidental.write_bytes(b"synthetic finder metadata")

    result = core.list_studio_client_engagements(cid, state_dir=state)

    assert result["engagements"][0]["engagement_id"] == eid
    assert result["blocked_engagements"][0]["entry_name"] == ".DS_Store"
    assert incidental.read_bytes() == b"synthetic finder metadata"


def test_recovery_after_unrelated_folder_change_does_not_require_index(case):
    core, studio, state, root, cid, eid, input_id = case
    (studio / "Unrelated new folder").mkdir()
    manifest = root / "Vera/client.json"
    before = manifest.read_bytes()

    result = core.recover_studio_client_ledger(state_dir=state)

    assert result["client_count"] == 1
    assert result["engagement_count"] == 1
    assert manifest.read_bytes() == before
    assert json.loads(before)["client_id"] == cid


def test_navigation_failure_after_commit_returns_saved_engagement(case, monkeypatch):
    core, studio, state, root, cid, eid, input_id = case
    select = core.get_studio_client_folder
    calls = 0

    def directory_unavailable_after_write(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise core.ArchiveError("Synthetic post-commit directory outage")
        return select(*args, **kwargs)

    monkeypatch.setattr(
        core, "get_studio_client_folder", directory_unavailable_after_write
    )

    result = core.create_studio_client_engagement(cid, "Retained work", state_dir=state)

    saved = core.ledger.load_engagement_manifest(
        root, result["engagement"]["engagement_id"]
    )
    assert saved["label"] == "Retained work"
    assert result["readable_archive"]["status"] == "unavailable"
    assert "post-commit directory outage" in result["readable_archive"]["error"]


@pytest.mark.parametrize(
    "linked_level", ["ledger", "engagements", "engagement", "inputs"]
)
def test_linked_ledger_parent_cannot_redirect_selected_import(
    case, tmp_path, linked_level
):
    core, studio, state, root, cid, eid, input_id = case
    ledger = root / "Vera"
    engagement = ledger / "engagements" / eid
    paths = {
        "ledger": ledger,
        "engagements": ledger / "engagements",
        "engagement": engagement,
        "inputs": engagement / "inputs",
    }
    selected = paths[linked_level]
    outside = tmp_path / "Outside retained archive"
    selected.rename(outside)
    selected.symlink_to(outside, target_is_directory=True)
    source = tmp_path / "new.txt"
    source.write_bytes(b"Synthetic import must stay inside its archive")
    before = sorted(path.relative_to(outside).as_posix() for path in outside.rglob("*"))

    with pytest.raises(core.ledger.LedgerError, match="real directory"):
        core.ledger.import_document(root, cid, eid, source, "source")

    assert (
        sorted(path.relative_to(outside).as_posix() for path in outside.rglob("*"))
        == before
    )
    assert source.read_bytes() == b"Synthetic import must stay inside its archive"


def test_engagement_manifest_from_another_directory_is_not_adopted(case):
    core, studio, state, root, cid, eid, input_id = case
    other = core.ledger.create_engagement(root, cid, "Independent engagement")
    directory = root / "Vera/engagements"
    target = directory / eid / "engagement.json"
    target.write_bytes(
        (directory / other["engagement_id"] / "engagement.json").read_bytes()
    )

    with pytest.raises(core.ledger.LedgerError, match="directory and manifest IDs"):
        core.ledger.load_engagement_manifest(root, eid)

    inventory = core.ledger.inspect_engagements(root, cid)
    assert [row["engagement_id"] for row in inventory["engagements"]] == [
        other["engagement_id"]
    ]
    assert inventory["blocked_engagements"][0]["engagement_id"] == eid


def test_native_client_and_engagement_navigation_survives_folder_changes(
    case, monkeypatch
):
    core, studio, state, root, cid, eid, input_id = case
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    monkeypatch.setenv("VERA_WORKSPACE_ROLES", "REVIEWER")
    import native_archive_navigation as navigation

    (studio / "Unrelated new folder").mkdir()

    catalogue = navigation.catalogue(ROOT / "plugins/studio-archive", {})

    assert catalogue["refresh_required"] is False
    assert catalogue["scope_configuration_changed"] is True
    node = shutil.which("node")
    assert node is not None
    rendered = subprocess.run(
        [
            node,
            str(ROOT / "tests/plugins/archive_run_list_ui.cjs"),
            str(ROOT / "plugins/vera/ui/workspace.js"),
        ],
        input=json.dumps(catalogue),
        capture_output=True,
        encoding="utf-8",
        check=True,
        timeout=20,
    )
    rows = json.loads(rendered.stdout)
    healthy = next(row for row in rows if "Synthetic healthy client" in row["text"])
    assert healthy["buttons"] == ["Apri incarichi →"]
    engagements = navigation.catalogue(
        ROOT / "plugins/studio-archive", {"client_id": cid}
    )
    assert engagements["can_create_engagement"] is True
    assert engagements["engagements"][0]["engagement_id"] == eid


@pytest.mark.skipif(os.name != "posix", reason="POSIX metadata permissions")
def test_existing_private_archive_profile_does_not_require_chmod(case, monkeypatch):
    core, studio, state, root, cid, eid, input_id = case
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", str(state.parent / "profile"))
    first = core.list_studio_clients(state_dir=state)

    def denied(*args, **kwargs):
        raise PermissionError(
            "Host denies permission changes on existing private state"
        )

    monkeypatch.setattr(Path, "chmod", denied)

    observed = core.list_studio_clients(state_dir=state)

    assert observed == {**first, "scope_cache": {"status": "current"}}


@pytest.mark.parametrize("collection", ["inputs", "runs"])
def test_missing_sibling_collection_does_not_hide_healthy_engagement(case, collection):
    core, studio, state, root, cid, eid, input_id = case
    other = core.create_studio_client_engagement(
        cid, "Unavailable collection", state_dir=state
    )["engagement"]["engagement_id"]
    missing = root / "Vera/engagements" / other / collection
    missing.rmdir()

    result = core.list_studio_client_engagements(cid, state_dir=state)

    rows = {row["engagement_id"]: row for row in result["engagements"]}
    assert rows[eid]["imports"][0]["input_id"] == input_id
    assert rows[other]["ledger_complete"] is False
    assert result["ledger_complete"] is False
    assert not missing.exists()


def test_native_run_inventory_reports_missing_collection_as_incomplete(
    case, monkeypatch
):
    core, studio, state, root, cid, eid, input_id = case
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    import native_archive_navigation as navigation

    missing = root / "Vera/engagements" / eid / "runs"
    missing.rmdir()

    result = navigation.catalogue(
        ROOT / "plugins/studio-archive", {"client_id": cid, "engagement_id": eid}
    )

    assert result["works"] == []
    assert result["ledger_complete"] is False
    assert result["collection_issues"][0]["issue_code"] == "unavailable_collection"
    assert not missing.exists()


def test_duplicate_client_identity_blocks_only_the_ambiguous_folders(case):
    core, studio, state, root, cid, eid, input_id = case
    other = core.create_studio_client("Independent client", state_dir=state)
    other_id = other["client"]["client_id"]
    shutil.copytree(root, studio / "Duplicate client folder")

    directory = core.list_studio_clients(state_dir=state)

    assert len(directory["blocked_clients"]) == 2
    assert core.get_studio_client_folder(other_id, state_dir=state)["status"] == "ready"
    with pytest.raises(core.ArchiveError, match="same stable client ID"):
        core.get_studio_client_folder(cid, state_dir=state)
