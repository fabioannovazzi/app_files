"""Exercise written lesson evidence, offline delivery and retry identity."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_written_lesson_reports_only_reviewed_course_and_retries_without_data(
    tmp_path, monkeypatch
):
    scripts = Path(__file__).resolve().parents[2] / "plugins/vera/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    import course_completion

    root = tmp_path / "lesson"
    root.mkdir()
    (root / "course-provenance.json").write_text(
        json.dumps(
            {
                "product": "vera",
                "course_id": "get-started",
                "workflow": "fatture-xml-check",
                "mode": "cowork-written-single-conversation",
                "prepared_artifacts": [{"path": "guide.html"}],
            }
        )
    )
    demo, practice, guide = (
        root / path for path in ("demo.txt", "practice.txt", "guide.html")
    )
    for file in (demo, practice, guide):
        file.write_text("private lesson content")

    owner = {"installation_id": "local-owner", "installation_key": "private-test-key"}
    queue = []

    def transport(operation, payload):
        if operation == "register":
            return {}
        queue.append(payload["completion"])
        if len(queue) == 1:
            raise OSError("offline")
        return {
            "recorded": True,
            "installation_id": owner["installation_id"],
            **queue[-1],
        }

    monkeypatch.setitem(
        sys.modules,
        "operational_incidents",
        SimpleNamespace(
            local_context=lambda: {
                "outbox_path": str(tmp_path / "outbox"),
                "credentials": owner,
            },
            _registration_payload=lambda credentials: {"credentials": credentials},
            _post=transport,
        ),
    )
    with pytest.raises(ValueError, match="confirms"):
        course_completion.finish_written(root, demo, practice, False)
    with pytest.raises(ValueError, match="distinct"):
        course_completion.finish_written(root, guide, practice, True)
    assert not queue
    first = course_completion.finish_written(root, demo, practice, True)
    assert (
        first["phase"] == "complete" and first["public_status"]["status"] == "pending"
    )
    assert course_completion.report([])["status"] == "delivered"
    assert queue[0] == queue[1]
    assert set(queue[0]) == {"event_id", "course_id", "completed_at"}
    assert queue[0]["course_id"] == "get-started"
    course_completion.finish_written(root, demo, practice, True)
    assert len(queue) == 2
    unrelated = course_completion.completion("journal-sampling")
    bad = {**unrelated, "course_id": "private answer should never leave this machine"}
    result = course_completion.report([bad, unrelated])
    assert result["status"] == "pending"
    assert queue[-1]["course_id"] == "journal-sampling"
    assert "private answer" not in json.dumps(queue)
