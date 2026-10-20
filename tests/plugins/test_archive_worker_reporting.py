"""Observe an exact worker submission through its real Archive-bound entrypoint."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.plugins.test_archive_automatic_reporting import (
    archive_core,
    archive_script_imports,
    client_case,
    reporting_runtime,
    start,
)
from tests.plugins.test_journal_bank_reconciliation_plugin import (
    _mock_semantic_worker_runtime,
    load_semantic_review,
)


@pytest.mark.parametrize(
    "workflow", ["journal-bank-reconciliation", "passive-invoice-audit"]
)
def test_archive_worker_retains_exact_prompt_locally_and_marks_missing_lineage(
    archive_core, client_case, monkeypatch, tmp_path, workflow
):
    from archive_report_store import RunStore, canonical, digest
    from archive_reporting import snapshot_run

    loaded = start(archive_core, client_case, workflow)
    output = Path(loaded["output_dir"]) / "worker"
    output.mkdir()
    semantic = load_semantic_review()
    events = [
        {"type": "thread.started", "thread_id": "synthetic-worker"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "id": "answer",
                "type": "agent_message",
                "text": '{"answer":"synthetic"}',
            },
        },
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}},
    ]
    _mock_semantic_worker_runtime(
        monkeypatch,
        semantic,
        tmp_path,
        {
            "return_code": 0,
            "stdout": "".join(json.dumps(event) + "\n" for event in events).encode(),
            "stderr": b"",
            "duration_ms": 1,
        },
    )
    prompt = "PRIVATE_SYNTHETIC_WORKER_INPUT"

    semantic.run_isolated_luna_worker(
        prompt=prompt,
        output_schema={"type": "object"},
        output_dir=output,
        workflow_id=workflow,
        packet_sha256="a" * 64,
    )

    observed = RunStore(Path(loaded["run_root"])).events()
    submissions = [
        event
        for event in observed
        if event["kind"] == "vera_send" and event["channel"].startswith("model_worker:")
    ]
    assert len(submissions) == 1
    assert submissions[0]["evidence_basis"] == "vera_outgoing_payload"
    submitted = {"prompt": prompt, "output_schema": {"type": "object"}}
    assert submissions[0]["response_sha256"] == digest(submitted)
    assert submissions[0]["characters"] == len(canonical(submitted).decode())
    snapshot = snapshot_run(loaded)
    report_text = Path(snapshot["report_path"]).read_text(encoding="utf-8")
    assert prompt not in report_text
    report = json.loads(report_text)
    assert report["collection_status"] == "incomplete"
    assert "sent_data_has_no_source_coordinates" in report["errors"]
