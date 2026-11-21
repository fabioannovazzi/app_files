"""Project renaming preserves retained work and cannot replace another folder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.plugins.test_archive_fault_isolation import case

__all__: list[str] = []


def test_rename_cli_preserves_identity_engagements_and_exact_source_bytes(case, capsys):
    core, studio, state, root, cid, eid, input_id = case
    import studio_archive

    before = {
        p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    result = studio_archive.main(
        ["rename-project", "--client-id", cid, "--name", "Progetto rinominato"]
    )

    renamed = studio / "Progetto rinominato"
    assert result == 0
    assert json.loads(capsys.readouterr().out)["status"] == "renamed"
    assert not root.exists()
    assert {
        p.relative_to(renamed): p.read_bytes()
        for p in renamed.rglob("*")
        if p.is_file()
    } == before
    assert core.get_studio_client_folder(cid, state_dir=state)["client_folder"][
        "client_root"
    ] == str(renamed)
    assert core.ledger.load_engagement_manifest(renamed, eid)["client_id"] == cid


def test_rename_retry_recovers_same_folder_after_lost_response(case):
    core, studio, state, root, cid, _, _ = case
    root.rename(studio / "Recovered name")

    result = core.rename_studio_archive_project(cid, "Recovered name", state_dir=state)

    assert result["status"] == "unchanged"
    assert result["client_id"] == cid


def test_rename_supports_case_only_changes_to_the_selected_project(case):
    core, studio, state, root, cid, _, _ = case
    name = root.name.upper()

    result = core.rename_studio_archive_project(cid, name, state_dir=state)

    assert result["status"] == "renamed"
    assert name in {path.name for path in studio.iterdir()}
    assert result["client_id"] == cid


@pytest.mark.parametrize(
    "name", ["../escape", "CON.txt", "trailing.", ".hidden", "x" * 33, "a/b", "a\\b"]
)
def test_rename_rejects_nonportable_or_traversing_names_without_mutation(case, name):
    core, _, state, root, cid, _, _ = case

    with pytest.raises(core.ArchiveError, match="portable project name"):
        core.rename_studio_archive_project(cid, name, state_dir=state)

    assert root.is_dir()


def test_rename_never_replaces_a_destination_created_after_preflight(case, monkeypatch):
    core, studio, state, root, cid, _, _ = case
    import project_rename

    rename = project_rename.rename_without_replacement
    destination = studio / "Concurrent project"

    def raced(source, target):
        target.mkdir()
        rename(source, target)

    monkeypatch.setattr(project_rename, "rename_without_replacement", raced)

    with pytest.raises(core.ArchiveError):
        core.rename_studio_archive_project(cid, destination.name, state_dir=state)

    assert root.is_dir()
    assert destination.is_dir()


def test_rename_retains_work_and_identity_when_registry_write_fails(case, monkeypatch):
    core, studio, state, root, cid, _, _ = case

    def unavailable(*args, **kwargs):
        raise OSError("Synthetic registry write failure")

    monkeypatch.setattr(core, "_write_client_identities", unavailable)

    result = core.rename_studio_archive_project(
        cid, "Retained project", state_dir=state
    )

    assert result["status"] == "renamed"
    assert result["identity_registry"]["status"] == "unavailable"
    assert (
        core.ledger.load_client_manifest(studio / "Retained project")["client_id"]
        == cid
    )
    assert not root.exists()
