"""Prepared files cannot stand in for live results in any product's tracker."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from tests.plugins._teaching_execution import execution_record
from tests.plugins.test_desktop_teaching import prepare as prepare_shared
from tests.plugins.test_vera_local_onboarding import load, prepare

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/_shared/vendor/modules"))
from courseware.library import CourseLibrary
from desktop_teaching.onboarding import Store


@pytest.fixture(params=["vera", "clara", "lucia"])
def active(request, tmp_path):
    if request.param == "vera":
        store = load("local_onboarding").Store(tmp_path / "profile")
        prepare(store)
    else:
        store = Store(
            tmp_path / "profile", plugin_root=ROOT / "plugins" / request.param
        )
        prepare_shared(store)
    state = store.status()
    workflow = state["lessons"][0]["workflow_id"]
    state = store.change("start", state["revision"], {"workflow_id": workflow})
    return store, state["lessons"][0]


def attempt(store, lesson, output):
    return {
        "workflow_id": lesson["workflow_id"],
        "artifacts": [str(output)],
        "prompt": "Synthetic lifecycle request",
        "review": "Fixture review only, no learner or professional approval",
        "execution_record": execution_record(
            store, "demo", output, lesson["workflow_id"]
        ),
    }


@pytest.mark.parametrize("copy_outside_kit", [False, True])
def test_prepared_lesson_and_renamed_copy_cannot_complete_a_demo(
    active, copy_outside_kit
):
    store, lesson = active
    root = store.lesson_root(lesson)
    library = CourseLibrary(store.plugin_root, {lesson["workflow_id"]})
    course = library.render(lesson["workflow_id"], "it", root / "kit")
    output = Path(course["course"])
    if copy_outside_kit:
        output = Path(shutil.copyfile(output, root / "renamed-result.html"))
    data = attempt(store, lesson, output)
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="Prepared material"):
        store.change("demo", store.status()["revision"], data)
    assert store.path.read_bytes() == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "mparanza.teaching_execution_request.v1"),
        ("evidence_kind", "provider_authenticated"),
        ("product", "another-product"),
        ("workflow_id", "another-workflow"),
        ("phase", "practice"),
        ("outcome", "failed"),
        ("worker_thread_id", "another-thread"),
        ("skill_sha256", "0" * 64),
        ("native_records", []),
    ],
)
def test_wrong_or_incomplete_execution_does_not_advance_progress(active, field, value):
    store, lesson = active
    output = store.lesson_root(lesson) / "actual-result.txt"
    output.write_text("Synthetic generated output")
    data = attempt(store, lesson, output)
    record_path = Path(data["execution_record"])
    record = json.loads(record_path.read_text())
    record[field] = value
    record_path.write_text(json.dumps(record))
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.change("demo", store.status()["revision"], data)
    assert store.path.read_bytes() == before


def test_a_copied_input_is_not_a_generated_result(active):
    store, lesson = active
    output = store.lesson_root(lesson) / "copied-input.txt"
    output.write_text("Synthetic lifecycle input for demo\n")
    data = attempt(store, lesson, output)
    with pytest.raises(ValueError, match="copied input"):
        store.change("demo", store.status()["revision"], data)


@pytest.mark.parametrize("changed", ["inputs", "native_records", "receipt"])
def test_completion_rechecks_execution_inputs_and_native_record(active, changed):
    store, lesson = active
    root = store.lesson_root(lesson)
    for phase in ("demo", "practice"):
        output = root / f"{phase}-output.txt"
        output.write_text(f"Synthetic generated result {phase}")
        store.change(
            phase,
            store.status()["revision"],
            {
                "workflow_id": lesson["workflow_id"],
                "artifacts": [str(output)],
                "prompt": "Synthetic request",
                "review": "Synthetic review",
                "execution_record": execution_record(
                    store, phase, output, lesson["workflow_id"]
                ),
            },
        )
    receipt = root / "demo-execution.json"
    if changed == "receipt":
        receipt.write_text(receipt.read_text() + "\n")
    else:
        record = json.loads(receipt.read_text())
        Path(record[changed][0]["path"]).write_text("Changed after the review")
    with pytest.raises(ValueError, match="changed"):
        store.change(
            "finish",
            store.status()["revision"],
            {
                "workflow_id": lesson["workflow_id"],
                "confirmed_by_user": True,
                "understanding": "Synthetic participant response",
            },
        )
    assert store.status()["lessons"][0]["status"] == "active"
