"""Run fictional course inputs through the actual owner-local register CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.plugins._teaching_release import record_native_check

__all__ = []
ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/vera"
sys.path.insert(0, str(ROOT / "plugins/_shared/vendor/modules"))
from courseware.library import CourseLibrary


def command(register: Path, action: str, **arguments: Any) -> dict[str, Any]:
    """Bind only this child process to the fictional tutorial register."""
    result = subprocess.run(
        [sys.executable, str(PLUGIN / "scripts/studio_work.py")],
        input=json.dumps({"action": action, "arguments": arguments}),
        text=True,
        capture_output=True,
        check=True,
        timeout=15,
        env={**os.environ, "VERA_STUDIO_WORK_DATA": str(register)},
        cwd=PLUGIN,
    )
    return json.loads(result.stdout)


def exercise(register: Path, case: dict[str, Any], phase: str) -> dict[str, Any]:
    """Execute an authored regression reading; no model or learner is simulated."""
    command(
        register,
        "configure",
        request_key="configure",
        expected_revision=0,
        preferences=case["preferences"],
    )
    appointment = command(
        register, "capture", request_key="capture", item=case["appointment"]
    )["item"]
    moved = command(
        register,
        "change",
        request_key="move",
        item_id=appointment["id"],
        expected_revision=appointment["revision"],
        patch=case["reschedule_request"],
    )["item"]
    notes = case["meeting_notes"]
    meeting = {key: value for key, value in notes.items() if key != "notes"}
    meeting["summary"] = notes["notes"]
    saved = command(
        register,
        "meeting",
        request_key="meeting",
        meeting=meeting,
        actions=[case["task_request"]],
    )
    task = saved["items"][0]
    if phase == "practice":
        task = command(
            register,
            "change",
            request_key="complete",
            item_id=task["id"],
            expected_revision=task["revision"],
            patch={"status": "done"},
        )["item"]
    return {
        "appointment": command(register, "read", item_id=moved["id"])["item"],
        "task": command(register, "read", item_id=task["id"])["item"],
        "context": command(register, "context", day=case["day"], include_closed=True),
    }


@pytest.mark.parametrize("phase", ["demo", "practice"])
@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
def test_course_saves_reopens_moves_and_keeps_isolated_practice(
    tmp_path: Path, language: str, phase: str, record_property
) -> None:
    """Verify durable results from packaged raw cases and untouched other data."""
    kit = CourseLibrary(PLUGIN, {"organizzazione-lavoro"}).render(
        "organizzazione-lavoro", language, tmp_path / "material"
    )
    source = kit["source_files" if phase == "demo" else "practice_files"][0]
    case = json.loads(Path(source).read_text(encoding="utf-8"))
    ordinary = tmp_path / "ordinary-register"
    sentinel = command(
        ordinary,
        "capture",
        request_key="ordinary",
        item={"title": "Unrelated studio work", "kind": "task", "source": "other"},
    )["item"]
    before = command(ordinary, "context", day=case["day"], include_closed=True)
    demo_register = tmp_path / "demo-register"
    demo_case = json.loads(Path(kit["source_files"][0]).read_text(encoding="utf-8"))
    demo = exercise(demo_register, demo_case, "demo")
    demo_before = command(
        demo_register, "context", day=demo_case["day"], include_closed=True
    )

    actual = (
        demo
        if phase == "demo"
        else exercise(tmp_path / "practice-register", case, phase)
    )

    assert actual["appointment"]["title"] == case["appointment"]["title"]
    assert actual["appointment"]["owner"] == case["appointment"]["owner"]
    assert (
        actual["appointment"]["start_time"] == case["reschedule_request"]["start_time"]
    )
    assert actual["appointment"]["end_time"] == case["reschedule_request"]["end_time"]
    assert actual["appointment"]["revision"] == 2
    assert actual["task"]["title"] == case["task_request"]["title"]
    assert actual["task"]["source"] == case["task_request"]["source"]
    assert actual["task"]["owner"] == case["task_request"]["owner"]
    assert actual["task"]["due_date"] == case["task_request"]["due_date"]
    assert actual["task"]["status"] == {"demo": "open", "practice": "done"}[phase]
    assert actual["context"]["total"] == 2
    assert actual["context"]["meetings"][0]["summary"] == case["meeting_notes"]["notes"]
    assert actual["context"]["operations"] == []
    assert actual["context"]["scheduler_installed"] is False
    assert actual["context"]["calendar_refresh_required"] is True
    assert actual["context"]["settings"]["calendar_id"] == "tutorial-local-only"
    assert "calendar_event_id" not in actual["appointment"]
    assert kit["prepared_material_only"] is True
    assert kit["understanding_confirmed"] is False
    assert command(ordinary, "read", item_id=sentinel["id"])["item"] == sentinel
    assert command(ordinary, "context", day=case["day"], include_closed=True) == before
    assert (
        command(demo_register, "context", day=demo_case["day"], include_closed=True)
        == demo_before
    )
    output = (
        Path(os.environ.get("STUDIO_WORK_COURSE_REVIEW_OUTPUT", str(tmp_path)))
        / f"{language}-{phase}"
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "saved-register.json").write_text(
        json.dumps(actual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    record_native_check(
        record_property,
        root=ROOT,
        product="vera",
        workflow="organizzazione-lavoro",
        language=language,
        phase=phase,
    )
