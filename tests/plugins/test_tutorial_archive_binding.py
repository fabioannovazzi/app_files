"""Tutorial output stays addressable by native Archive tools across sessions."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
from tests.plugins.test_vera_local_onboarding import load


@pytest.fixture
def prepared_case(tmp_path, monkeypatch):
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
        workflow="journal-sampling",
        token="bound-token",
        sources=[source],
        phase="demo",
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
