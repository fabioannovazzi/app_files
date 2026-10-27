"""Preserve admitted inputs and completed stages independently of the archive."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.plugins.test_archive_fault_isolation import case


def started(case):
    core, studio, state, root, cid, eid, input_id = case
    prepared = core.prepare_studio_client_workflow(
        eid, "posizioni-negoziali", input_ids=[input_id], state_dir=state
    )
    rid = prepared["run"]["run_id"]
    core.start_studio_client_workflow(cid, eid, rid, state_dir=state)
    return core, studio, state, root, cid, eid, rid, prepared


def test_restore_selected_run_retains_completed_work_after_archive_loss(case, tmp_path):
    core, studio, state, root, cid, eid, rid, prepared = started(case)
    progress = Path(prepared["client_engagement"]["output_dir"]) / "completed-stage.md"
    progress.write_bytes(b"Completed stage; do not repeat")
    saved = core.checkpoint_studio_client_workflow(cid, eid, rid, state_dir=state)
    shutil.rmtree(studio)
    destination = tmp_path / "Authorized alternate destination"

    result = core.restore_studio_client_workflow(
        cid, eid, rid, destination, state_dir=state
    )

    assert saved["recovery"]["status"] == "retained"
    assert result["run"]["run_id"] == rid
    assert result["run"]["status"] == "running"
    context = result["client_engagement"]
    assert (
        Path(context["output_dir"]).joinpath("completed-stage.md").read_bytes()
        == b"Completed stage; do not repeat"
    )
    assert (
        Path(context["input_bindings"][0]["path"]).read_text()
        == "Synthetic retained source"
    )
    assert (
        core.start_studio_client_workflow(cid, eid, rid, state_dir=state)["run"][
            "run_id"
        ]
        == rid
    )
    assert not studio.exists()


@pytest.mark.parametrize("damage", ["removed", "changed"])
def test_worker_recovers_exact_admitted_input_without_discarding_changed_bytes(
    case, damage
):
    from vera_assurance import load_client_engagement_context_file

    core, studio, state, root, cid, eid, rid, prepared = started(case)
    context = prepared["client_engagement"]
    source = Path(context["input_bindings"][0]["path"])
    if damage == "removed":
        source.unlink()
    else:
        source.write_bytes(b"Later unadmitted replacement")

    loaded = load_client_engagement_context_file(
        prepared["client_engagement_path"],
        expected_workflow_id="posizioni-negoziali",
        input_paths=[source],
        output_dir=context["output_dir"],
    )

    assert loaded["run_id"] == rid
    assert source.read_text() == "Synthetic retained source"
    history = Path(context["run_root"]) / "recovery-evidence"
    if damage == "changed":
        assert any(
            path.read_bytes() == b"Later unadmitted replacement"
            for path in history.rglob("*")
            if path.is_file()
        )


def test_restore_does_not_overwrite_an_existing_destination(case, tmp_path):
    core, studio, state, root, cid, eid, rid, prepared = started(case)
    destination = tmp_path / "Existing client"
    destination.mkdir()
    existing = destination / "existing-work.md"
    existing.write_bytes(b"Unrelated work")

    with pytest.raises(core.ArchiveError, match="destination"):
        core.restore_studio_client_workflow(cid, eid, rid, destination, state_dir=state)

    assert existing.read_bytes() == b"Unrelated work"
    assert not (destination / "Vera").exists()


def test_completed_helper_is_checkpointed_without_an_extra_agent_step(
    case, tmp_path, monkeypatch
):
    import sys

    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[2] / "plugins/vera/scripts")
    )
    from archive_cli import run_command

    core, studio, state, root, cid, eid, rid, prepared = started(case)
    output = Path(prepared["client_engagement"]["output_dir"]) / "completed-stage.txt"
    completed = run_command(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; Path(sys.argv[1]).write_text('Completed helper stage')",
            str(output),
        ],
        plugin_root=Path(__file__).resolve().parents[2] / "plugins/vera",
        component="posizioni-negoziali",
        arguments=["--client-engagement", prepared["client_engagement_path"]],
        check=False,
    )
    shutil.rmtree(studio)

    restored = core.restore_studio_client_workflow(
        cid, eid, rid, tmp_path / "Alternate", state_dir=state
    )

    assert completed.returncode == 0
    assert (
        Path(restored["client_engagement"]["output_dir"])
        .joinpath(output.name)
        .read_text()
        == "Completed helper stage"
    )


def test_unavailable_checkpoint_does_not_invalidate_unchanged_execution_inputs(case):
    from vera_assurance import load_client_engagement_context_file

    core, studio, state, root, cid, eid, rid, prepared = started(case)
    shutil.rmtree(Path(prepared["recovery"]["store"]))

    context = load_client_engagement_context_file(
        prepared["client_engagement_path"], expected_workflow_id="posizioni-negoziali"
    )

    assert context["run_id"] == rid
    assert core.ledger.load_run(root, eid, rid)["run"]["status"] == "running"


def test_interrupted_restore_continues_same_destination_and_preserves_partial_bytes(
    case, tmp_path, monkeypatch
):
    import vera_assurance.recovery as recovery

    core, studio, state, root, cid, eid, rid, prepared = started(case)
    destination = tmp_path / "Alternate"
    copy = recovery.shutil.copyfileobj

    def interrupted(source, target, *args, **kwargs):
        if isinstance(target.name, str) and Path(target.name).name == "client.json":
            target.write(b"partial client header")
            raise OSError("Synthetic destination disconnect")
        return copy(source, target, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(recovery.shutil, "copyfileobj", interrupted)
        with pytest.raises(core.ArchiveError, match="destination"):
            core.restore_studio_client_workflow(
                cid, eid, rid, destination, state_dir=state
            )

    restored = core.restore_studio_client_workflow(
        cid, eid, rid, destination, state_dir=state
    )

    assert restored["run"]["run_id"] == rid
    partial = list((destination / "work-restore-evidence").glob("*/partial-copy"))
    assert len(partial) == 1
    assert partial[0].read_bytes() == b"partial client header"
    output = Path(restored["client_engagement"]["output_dir"]) / "new-work.txt"
    output.write_text("New progress after recovery")
    repeated = core.restore_studio_client_workflow(
        cid, eid, rid, destination, state_dir=state
    )
    assert repeated["run"]["run_id"] == rid
    assert output.read_text() == "New progress after recovery"


def test_new_cli_process_restores_the_retained_job_without_archive_configuration(
    case, tmp_path
):
    core, studio, state, root, cid, eid, rid, prepared = started(case)
    shutil.rmtree(studio)
    (state / "config.json").unlink()
    cli = (
        Path(__file__).resolve().parents[2]
        / "plugins/studio-archive/scripts/studio_archive.py"
    )

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(cli),
            "restore-workflow",
            "--client-id",
            cid,
            "--engagement-id",
            eid,
            "--run-id",
            rid,
            "--destination",
            str(tmp_path / "Alternate"),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        env={**os.environ, "VERA_STUDIO_ARCHIVE_STATE_DIR": str(state)},
    )

    assert result.returncode == 0, result.stderr
    restored = json.loads(result.stdout)
    assert restored["status"] == "restored"
    assert restored["run"]["run_id"] == rid
    assert not (state / "config.json").exists()
