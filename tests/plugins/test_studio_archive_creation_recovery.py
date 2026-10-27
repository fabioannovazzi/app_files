"""A lost or interrupted Archive creation response must not allocate another job."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.plugins.test_archive_fault_isolation import case

__all__: list[str] = []
SCRIPTS = Path(__file__).resolve().parents[2] / "plugins/studio-archive/scripts"

# Interrupt after the durable commit and before the caller receives its result.
INTERRUPTED_WORKER = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import archive_core as core
state, cid, eid, input_id, operation = sys.argv[2:]
writer = core.ledger._write_json
def interrupted(path, payload):
    writer(path, payload)
    if path.name == ('engagement.json' if operation == 'create' else 'run.json'):
        os._exit(37)
core.ledger._write_json = interrupted
if operation == 'create':
    core.create_studio_client_engagement(
        cid, 'Lost process reply', idempotency_key='lost-reply', state_dir=Path(state))
else:
    core.prepare_studio_client_workflow(
        eid, 'posizioni-negoziali', input_ids=[input_id],
        label='  Retained   request  ', purpose='  Draft   response ',
        idempotency_key='lost-reply', state_dir=Path(state))
"""


@pytest.mark.parametrize("operation", ["create", "prepare"])
def test_fresh_cli_recovers_committed_request_after_worker_exit(case, operation):
    core, studio, state, root, cid, eid, input_id = case
    interrupted = subprocess.run(
        [
            sys.executable,
            "-c",
            INTERRUPTED_WORKER,
            str(SCRIPTS),
            str(state),
            cid,
            eid,
            input_id,
            operation,
        ],
        env={**os.environ, "VERA_STUDIO_ARCHIVE_STATE_DIR": str(state)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert interrupted.returncode == 37, interrupted.stderr
    collection = root / "Vera/engagements"
    if operation == "create":
        target = next(path for path in collection.glob("eng_*") if path.name != eid)
        retained = (target / "engagement.json").read_bytes()
        command = [
            "create-engagement",
            "--client-id",
            cid,
            "--engagement-label",
            "Lost process reply",
        ]
    else:
        target = next((collection / eid / "runs").glob("run_*"))
        retained = (target / "run.json").read_bytes()
        # A committed run owns its input copies even if intake receipts disappear.
        import shutil

        shutil.rmtree(collection / eid / "inputs" / input_id)
        command = [
            "prepare-workflow",
            "--engagement-id",
            eid,
            "--workflow-id",
            "posizioni-negoziali",
            "--input-id",
            input_id,
            "--label",
            "  Retained   request  ",
            "--purpose",
            "  Draft   response ",
        ]

    recovered = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "studio_archive.py"),
            *command,
            "--idempotency-key",
            "lost-reply",
        ],
        env={**os.environ, "VERA_STUDIO_ARCHIVE_STATE_DIR": str(state)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert recovered.returncode == 0, recovered.stderr
    result = json.loads(recovered.stdout)
    if operation == "create":
        assert result["status"] == "already_created"
        assert result["engagement"]["engagement_id"] == target.name
        assert (target / "engagement.json").read_bytes() == retained
    else:
        assert result["status"] == "already_prepared"
        assert result["run"]["run_id"] == target.name
        assert (target / "run.json").read_bytes() == retained


def test_repeated_engagement_request_reuses_the_committed_identity(case):
    core, studio, state, root, cid, prior, input_id = case
    arguments = {"state_dir": state, "idempotency_key": "same-admitted-request"}
    first = core.create_studio_client_engagement(cid, "Requested work", **arguments)
    eid = first["engagement"]["engagement_id"]
    evidence = root / "Vera/engagements" / eid / "inputs/retained-note.txt"
    evidence.write_text("Work retained after the response was lost")

    repeated = core.create_studio_client_engagement(cid, "Requested work", **arguments)

    assert repeated["engagement"]["engagement_id"] == eid
    assert repeated["source_archive_mutated"] is False
    assert evidence.read_text() == "Work retained after the response was lost"
    assert len(list((root / "Vera/engagements").glob("eng_*"))) == 2


@pytest.mark.parametrize("interruption", ["before_manifest", "after_manifest"])
def test_interrupted_engagement_creation_resumes_its_original_request(
    case, monkeypatch, interruption
):
    core, studio, state, root, cid, prior, input_id = case
    writer = core.ledger._write_json

    def interrupted(path, payload):
        if path.name == "engagement.json":
            if interruption == "after_manifest":
                writer(path, payload)
            raise OSError("Synthetic storage interruption")
        return writer(path, payload)

    with monkeypatch.context() as scoped:
        scoped.setattr(core.ledger, "_write_json", interrupted)
        with pytest.raises((OSError, core.ArchiveError), match="interruption"):
            core.create_studio_client_engagement(
                cid,
                "Requested work",
                idempotency_key="interrupted-request",
                state_dir=state,
            )
    pending = set((root / "Vera/engagements").glob("eng_*")) - {
        root / "Vera/engagements" / prior
    }
    assert len(pending) == 1

    recovered = core.create_studio_client_engagement(
        cid, "Requested work", idempotency_key="interrupted-request", state_dir=state
    )

    assert pending == {
        root / "Vera/engagements" / recovered["engagement"]["engagement_id"]
    }
    assert len(list((root / "Vera/engagements").glob("eng_*"))) == 2


def test_creation_request_key_cannot_silently_select_a_different_matter(case):
    core, studio, state, root, cid, prior, input_id = case
    created = core.create_studio_client_engagement(
        cid, "Original matter", idempotency_key="retained-request", state_dir=state
    )
    path = (
        root
        / "Vera/engagements"
        / created["engagement"]["engagement_id"]
        / "engagement.json"
    )
    retained = path.read_bytes()

    with pytest.raises(core.ArchiveError, match="different.*request"):
        core.create_studio_client_engagement(
            cid, "Different matter", idempotency_key="retained-request", state_dir=state
        )

    assert path.read_bytes() == retained


def test_concurrent_retries_allocate_one_engagement(case):
    core, studio, state, root, cid, prior, input_id = case

    def create(_):
        return core.ledger.ensure_engagement(
            root, cid, "Requested work", idempotency_key="concurrent-request"
        )

    with ThreadPoolExecutor(max_workers=2) as workers:
        first, second = workers.map(create, range(2))

    assert first["engagement"] == second["engagement"]
    assert sorted([first["created"], second["created"]]) == [False, True]
    assert len(list((root / "Vera/engagements").glob("eng_*"))) == 2


@pytest.mark.parametrize("new_run", [False, True])
def test_preparation_retry_uses_admitted_copies_after_original_receipt_loss(
    case, new_run
):
    core, studio, state, root, cid, eid, input_id = case
    arguments = {
        "input_ids": [input_id],
        "idempotency_key": "retained-preparation",
        "new_run": new_run,
        "state_dir": state,
    }
    prepared = core.prepare_studio_client_workflow(
        eid, "posizioni-negoziali", **arguments
    )
    rid = prepared["run"]["run_id"]
    core.start_studio_client_workflow(cid, eid, rid, state_dir=state)
    binding = prepared["client_engagement"]["input_bindings"][0]
    (root / binding["receipt_relative_path"]).unlink()
    (root / binding["source_relative_path"]).unlink()

    replayed = core.prepare_studio_client_workflow(
        eid, "posizioni-negoziali", **arguments
    )

    assert replayed["run"]["run_id"] == rid
    assert replayed["run"]["status"] == "running"
    assert len(list((root / "Vera/engagements" / eid / "runs").glob("run_*"))) == 1


def test_preparation_request_key_cannot_select_other_inputs(case):
    core, studio, state, root, cid, eid, input_id = case
    prepared = core.prepare_studio_client_workflow(
        eid,
        "posizioni-negoziali",
        input_ids=[input_id],
        idempotency_key="retained-preparation",
        state_dir=state,
    )

    with pytest.raises(core.ArchiveError, match="different run request"):
        core.prepare_studio_client_workflow(
            eid,
            "posizioni-negoziali",
            input_ids=["input_" + "0" * 24],
            idempotency_key="retained-preparation",
            state_dir=state,
        )

    assert (
        core.ledger.load_run(root, eid, prepared["run"]["run_id"])["run"]["status"]
        == "prepared"
    )


def test_verified_result_handoff_does_not_require_upstream_execution_inputs(case):
    core, studio, state, root, cid, eid, input_id = case
    prepared = core.prepare_studio_client_workflow(
        eid, "posizioni-negoziali", input_ids=[input_id], state_dir=state
    )
    rid = prepared["run"]["run_id"]
    core.start_studio_client_workflow(cid, eid, rid, state_dir=state)
    output = Path(prepared["client_engagement"]["output_dir"]) / "result.md"
    output.write_text("Completed professional result")
    core.finalize_studio_client_workflow(
        cid,
        eid,
        rid,
        [
            {
                "artifact_id": "result",
                "path": "result.md",
                "purpose": "Review",
                "audience": "review",
                "media_type": "text/markdown",
            }
        ],
        state_dir=state,
    )
    shutil.rmtree(output.parent.parent / "inputs")
    shutil.rmtree(Path(prepared["recovery"]["store"]))
    arguments = {
        "upstream_artifacts": [
            {"run_id": rid, "artifact_id": "  result ", "role": " source  "}
        ],
        "idempotency_key": "next-step",
        "state_dir": state,
    }

    following = core.prepare_studio_client_workflow(
        eid, "posizioni-negoziali", **arguments
    )
    replay = core.prepare_studio_client_workflow(
        eid, "posizioni-negoziali", **arguments
    )

    assert replay["run"]["run_id"] == following["run"]["run_id"]
    assert following["run"]["run_id"] != rid
    [binding] = following["client_engagement"]["input_bindings"]
    assert Path(binding["path"]).read_bytes() == output.read_bytes()
    assert binding["upstream_run_id"] == rid
