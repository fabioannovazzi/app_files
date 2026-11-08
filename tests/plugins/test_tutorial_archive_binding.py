"""Tutorial output stays addressable by native Archive tools across sessions."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
from tests.plugins.test_vera_local_onboarding import load


@pytest.fixture
def prepared_case(tmp_path, monkeypatch, request):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    profile = tmp_path / "profile"
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", str(profile))
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_STATE_DIR", str(tmp_path / "first-session"))
    root = tmp_path / "teaching"
    root.mkdir()
    (root / load("local_onboarding").MARKER).write_text("local-only")
    source = root / "source.txt"
    source.write_text("fictional source")
    store = SimpleNamespace(
        root=root,
        product="vera",
        plugin_root=ROOT / "plugins/vera",
        worker=lambda *_: {"local_only": True, "lesson": {"directory": str(root)}},
    )
    prepared = load("local_onboarding_case").prepare_case(
        store,
        thread_id="worker",
        workflow=getattr(request, "param", "journal-sampling"),
        token="bound-token",
        sources=[source],
        phase="demo",
        source_root=(
            root if getattr(request, "param", None) == "archive-organization" else None
        ),
    )
    monkeypatch.setenv(
        "VERA_STUDIO_ARCHIVE_STATE_DIR", str(tmp_path / "second-session")
    )
    archive = sys.modules["vera_tutorial_archive"]
    return archive, prepared


def test_prepared_tutorial_native_write_survives_session_change(
    prepared_case, tmp_path
):
    archive, prepared = prepared_case
    run = prepared["run"]

    archive.write_studio_run_artifact(
        run["client_id"],
        run["engagement_id"],
        run["run_id"],
        "mapping-candidate.json",
        '{"review":"pending"}',
    )

    assert prepared["work_binding"]["status"] == "retained"
    assert (
        Path(prepared["output_dir"]) / "authored" / "mapping-candidate.json"
    ).read_text() == '{"review":"pending"}'
    assert not (tmp_path / "second-session" / "config.json").exists()


def test_tutorial_binding_does_not_authorize_another_client(prepared_case):
    archive, prepared = prepared_case
    run = prepared["run"]
    with pytest.raises(archive.ArchiveError):
        archive.write_studio_run_artifact(
            "client_wrong", run["engagement_id"], run["run_id"], "wrong.json", "{}"
        )
    assert not (Path(prepared["output_dir"]) / "authored" / "wrong.json").exists()


def test_tutorial_binding_rejects_changed_context_hash(prepared_case):
    archive, prepared = prepared_case
    run = prepared["run"]
    binding_path = Path(prepared["work_binding"]["path"])
    binding = json.loads(binding_path.read_text())
    binding["static_sha256"] = "0" * 64
    binding_path.write_text(json.dumps(binding))

    with pytest.raises(archive.ArchiveError):
        archive.write_studio_run_artifact(
            run["client_id"], run["engagement_id"], run["run_id"], "wrong.json", "{}"
        )
    assert not (Path(prepared["output_dir"]) / "authored" / "wrong.json").exists()


def test_engagement_import_and_reopen_use_retained_case(prepared_case, tmp_path):
    archive, prepared = prepared_case
    run = prepared["run"]
    ordinary = tmp_path / "ordinary"
    ordinary.mkdir()
    archive.configure_archive(ordinary)
    source = tmp_path / "followup.txt"
    source.write_text("fictional continuation")

    result = archive.import_studio_client_document(
        run["client_id"], source, "support", engagement_id=run["engagement_id"]
    )

    reopened = archive.list_studio_client_engagements(run["client_id"])
    assert result["input_receipt"]["sha256"]
    assert reopened["engagements"][0]["engagement_id"] == run["engagement_id"]
    assert archive._load_config(archive._state_dir(None)).archive_root == ordinary


def test_engagement_import_rejects_foreign_source_scope(prepared_case, tmp_path):
    archive, prepared = prepared_case
    run = prepared["run"]
    sibling = Path(prepared["client_root"]).parent / "another-client"
    sibling.mkdir()
    source = sibling / "private.txt"
    source.write_text("other client")

    with pytest.raises(archive.ArchiveError, match="another Studio Archive scope"):
        archive.import_studio_client_document(
            run["client_id"], source, "source", engagement_id=run["engagement_id"]
        )


def test_engagement_lookup_rejects_changed_binding(prepared_case, tmp_path):
    archive, prepared = prepared_case
    run = prepared["run"]
    binding_path = Path(prepared["work_binding"]["path"])
    value = json.loads(binding_path.read_text())
    value["static_sha256"] = "0" * 64
    binding_path.write_text(json.dumps(value))
    source = tmp_path / "source.txt"
    source.write_text("fictional")

    with pytest.raises(archive.ArchiveError):
        archive.import_studio_client_document(
            run["client_id"], source, "source", engagement_id=run["engagement_id"]
        )


def test_binding_retry_preserves_prepared_job(prepared_case, monkeypatch):
    archive, prepared = prepared_case
    adapter = load("local_onboarding_case")
    monkeypatch.setattr(adapter, "_archive", lambda: archive)
    case_path = Path(prepared["tutorial_case_path"])
    original = case_path.read_bytes()
    original_write = archive._write_private_json

    def denied(*args, **kwargs):
        raise PermissionError("private binding directory")

    monkeypatch.setattr(archive, "_write_private_json", denied)
    failed = adapter.retry_case_binding(case_path)
    assert failed["native_archive_ready"] is False
    assert failed["work_binding"]["reason"] == "PermissionError"
    monkeypatch.setattr(archive, "_write_private_json", original_write)

    recovered = adapter.retry_case_binding(case_path)

    assert recovered["native_archive_ready"] is True
    assert recovered["run"] == json.loads(original)["run"]
    assert recovered["output_dir"] == prepared["output_dir"]


@pytest.mark.parametrize("prepared_case", ["archive-organization"], indirect=True)
def test_inventory_survives_new_process_and_other_archive(prepared_case, tmp_path):
    archive, prepared = prepared_case
    ordinary = tmp_path / "ordinary"
    ordinary.mkdir()
    archive.configure_archive(ordinary)
    code = """
import json, sys
from pathlib import Path
from local_onboarding_case import _archive
archive = _archive()
case = json.loads(Path(sys.argv[1]).read_text())
run = case['run']
result = archive.get_studio_archive_organization_inventory(
    run['client_id'], run['engagement_id'], case['context']['input_bindings'][0]['binding_id'])
sys.stdout.write(json.dumps(result))
"""

    child = subprocess.run(
        [sys.executable, "-c", code, prepared["tutorial_case_path"]],
        env={**os.environ, "PYTHONPATH": str(ROOT / "plugins/vera/scripts")},
        capture_output=True,
        text=True,
        check=True,
    )

    assert json.loads(child.stdout)["status"] == "ready"
    assert archive._load_config(archive._state_dir(None)).archive_root == ordinary


def test_continuation_prepares_same_engagement_without_global_setup(prepared_case):
    archive, prepared = prepared_case
    run = prepared["run"]

    next_run = archive.prepare_studio_client_workflow(
        run["engagement_id"],
        "journal-sampling",
        input_ids=[prepared["context"]["input_bindings"][0]["binding_id"]],
        new_run=True,
    )

    assert next_run["run"]["engagement_id"] == run["engagement_id"]
    assert next_run["run"]["client_id"] == run["client_id"]
    assert next_run["run"]["run_id"] != run["run_id"]
    assert next_run["readable_archive"]["status"] != "unavailable"


def test_engagement_lookup_rejects_two_verified_live_copies(prepared_case, tmp_path):
    import shutil

    archive, prepared = prepared_case
    original = Path(prepared["client_root"])
    run = prepared["run"]
    successor = archive.prepare_studio_client_workflow(
        run["engagement_id"],
        "journal-sampling",
        input_ids=[prepared["context"]["input_bindings"][0]["binding_id"]],
        new_run=True,
    )
    other = tmp_path / "other-copy"
    shutil.copytree(original, other)
    archive.retain_studio_run_binding(
        other, run["engagement_id"], successor["run"]["run_id"]
    )

    with pytest.raises(archive.ArchiveError, match="multiple live locations"):
        archive.list_studio_client_engagements(run["client_id"])


def test_retained_import_rejects_source_in_other_selected_archive(
    prepared_case, tmp_path
):
    archive, prepared = prepared_case
    run = prepared["run"]
    ordinary = tmp_path / "ordinary"
    ordinary.mkdir()
    source = ordinary / "other-client.txt"
    source.write_text("Other client's source")
    archive.configure_archive(ordinary)

    with pytest.raises(archive.ArchiveError, match="another Studio Archive scope"):
        archive.import_studio_client_document(
            run["client_id"], source, "source", engagement_id=run["engagement_id"]
        )


def test_initial_binding_denial_returns_recovery_for_same_prepared_job(
    tmp_path, monkeypatch
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/vera/scripts"))
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_PROFILE_DIR", str(tmp_path / "profile"))
    monkeypatch.setenv("VERA_STUDIO_ARCHIVE_STATE_DIR", str(tmp_path / "session"))
    root = tmp_path / "teaching"
    root.mkdir()
    (root / load("local_onboarding").MARKER).write_text("local-only")
    source = root / "fictional.txt"
    source.write_text("Fictional source")
    store = SimpleNamespace(
        root=root,
        product="vera",
        plugin_root=ROOT / "plugins/vera",
        worker=lambda *_: {"local_only": True, "lesson": {"directory": str(root)}},
    )
    adapter = load("local_onboarding_case")
    archive = adapter._archive()
    monkeypatch.setattr(adapter, "_archive", lambda: archive)
    write = archive._write_private_json

    def denied(path, value):
        if path.parent.name == "work-bindings":
            raise PermissionError("Private binding access denied")
        return write(path, value)

    monkeypatch.setattr(archive, "_write_private_json", denied)
    prepared = adapter.prepare_case(
        store,
        thread_id="worker",
        workflow="journal-sampling",
        token="test",
        sources=[source],
        phase="demo",
    )
    assert prepared["native_archive_ready"] is False
    assert prepared["binding_recovery"]["arguments"] == [
        "--retry-binding",
        prepared["tutorial_case_path"],
    ]
    assert Path(prepared["context_path"]).is_file()
    monkeypatch.setattr(archive, "_write_private_json", write)

    recovered = adapter.retry_case_binding(Path(prepared["tutorial_case_path"]))

    assert recovered["run"] == prepared["run"]
    assert recovered["native_archive_ready"] is True
