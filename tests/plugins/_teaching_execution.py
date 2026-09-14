"""Explicit synthetic host attestations for teaching-state regression tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

__all__ = ["execution_record"]


def execution_record(store, phase, output, workflow=None, *, inputs=None, native=None):
    """Use supplied real run files or clearly labelled lifecycle-only fixtures."""
    status = store.status()
    state = status.get("session", status)
    lesson = (
        state
        if "session_id" in state
        else next(item for item in state["lessons"] if item["workflow_id"] == workflow)
    )
    root = output.parent if phase == "application" else store.lesson_root(lesson)
    if inputs is None:
        source = root / f"{phase}-fixture-source.txt"
        source.write_text(f"Synthetic lifecycle input for {phase}\n")
        inputs = [source]
    if native is None:
        run = root / f"{phase}-fixture-native-run.json"
        run.write_text(json.dumps({"synthetic_test_fixture": True, "phase": phase}))
        native = [run]

    def records(paths):
        return [
            {
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in paths
        ]

    path = root / f"{phase}-execution.json"
    path.write_text(
        json.dumps(
            {
                "schema": "mparanza.teaching_execution.v1",
                "evidence_kind": "host_attested_local_execution",
                "product": store.product,
                "workflow_id": lesson["workflow_id"],
                "phase": phase,
                "worker_thread_id": state["pair"]["worker_thread_id"],
                "outcome": "review_required",
                "skill_sha256": hashlib.sha256(
                    (
                        store.plugin_root
                        / "skills"
                        / lesson["workflow_id"]
                        / "SKILL.md"
                    ).read_bytes()
                ).hexdigest(),
                "inputs": records(inputs),
                "native_records": records(native),
                "outputs": records([output]),
            }
        )
    )
    return str(path)
