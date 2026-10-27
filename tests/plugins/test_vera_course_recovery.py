"""Course relocation preserves admitted progress and original execution evidence."""

from __future__ import annotations

import json
import shutil

import pytest

from tests.plugins.test_vera_local_onboarding import (
    change,
    evidence,
    load,
    module,
    prepare,
    store,
)

__all__: list[str] = []


@pytest.mark.parametrize("changed_receipt", [False, True])
def test_saved_lesson_keeps_admitted_procedure_after_plugin_update(
    module, store, tmp_path, changed_receipt
):
    prepare(store)
    workflow = "fatture-xml-check"
    change(store, "start", workflow_id=workflow)
    evidence(store, workflow, "demo")
    saved = evidence(store, workflow, "practice")
    newer = tmp_path / "new-plugin" / "skills" / workflow
    newer.mkdir(parents=True)
    (newer / "SKILL.md").write_text("New procedure for future work")
    store.plugin_root = newer.parents[1]
    receipt = store.root / "lessons" / workflow / "demo-execution.json"
    if changed_receipt:
        record = json.loads(receipt.read_text())
        record["outcome"] = "completed"
        receipt.write_text(json.dumps(record))
        with pytest.raises(ValueError, match="record changed"):
            change(
                store,
                "finish",
                workflow_id=workflow,
                confirmed_by_user=True,
                understanding="Changed evidence cannot claim the admitted result",
            )
        assert store.status()["revision"] == saved["revision"]
    else:
        completed = change(
            store,
            "finish",
            workflow_id=workflow,
            confirmed_by_user=True,
            understanding="The learner explained the completed work",
        )
        assert completed["lessons"][0]["status"] == "complete"
        assert completed["revision"] == saved["revision"] + 1


def test_course_relocation_retains_progress_and_completes_same_lesson(
    module, store, tmp_path
):
    from courseware.recovery import relocate_course

    prepare(store)
    workflow = "fatture-xml-check"
    change(store, "start", workflow_id=workflow)
    evidence(store, workflow, "demo")
    original = evidence(store, workflow, "practice")
    root = store.root / "lessons" / workflow
    receipt = (root / "demo-execution.json").read_bytes()
    profile_bytes = store.path.read_bytes()
    destination = tmp_path / "available course"

    result = relocate_course(store.root, destination)
    shutil.rmtree(store.root)
    resumed = module.Store(destination)
    completed = change(
        resumed,
        "finish",
        workflow_id=workflow,
        confirmed_by_user=True,
        understanding="The learner explained inputs, results and limitations",
    )

    assert result["onboarding_id"] == original["onboarding_id"]
    assert completed["onboarding_id"] == original["onboarding_id"]
    assert completed["revision"] == original["revision"] + 1
    assert completed["lessons"][0]["status"] == "complete"
    assert completed["pair"] == original["pair"]
    assert (
        destination / "lessons" / workflow / "demo-execution.json"
    ).read_bytes() == receipt
    assert (destination / "profile.previous.json").read_bytes() == profile_bytes


def test_relocated_teaching_session_retains_its_identity(module, store, tmp_path):
    from courseware.recovery import relocate_course

    prepare(store)
    teaching = load("local_teaching")
    selected = teaching.TeachingStore(store.root)
    started = selected.begin(
        {
            "workflow_id": "fatture-xml-check",
            "title": "Existing example",
            "goal": "Review a supplied invoice",
            "mode": "show",
            "pair": {"teacher_thread_id": "teacher", "worker_thread_id": "worker"},
        }
    )
    session = started["session"]
    destination = tmp_path / "recovered course"

    relocate_course(store.root, destination)
    shutil.rmtree(store.root)
    resumed = teaching.TeachingStore(destination, session["session_id"]).status()

    assert resumed["session"]["session_id"] == session["session_id"]
    assert resumed["session"]["revision"] == session["revision"]
    assert resumed["session"]["directory"] == str(
        destination / "teaching/sessions" / session["session_id"] / "files"
    )


def test_interrupted_course_copy_resumes_without_reenrollment(
    module, store, tmp_path, monkeypatch
):
    from courseware import recovery

    original = prepare(store)
    destination = tmp_path / "recovered course"
    copy = recovery.shutil.copyfile

    def unavailable(source, target):
        if source.name == "profile.json":
            raise OSError("Synthetic destination interruption")
        return copy(source, target)

    with monkeypatch.context() as scoped:
        scoped.setattr(recovery.shutil, "copyfile", unavailable)
        with pytest.raises(OSError, match="interruption"):
            recovery.relocate_course(store.root, destination)
    assert (destination / "enrollment.json").is_file()
    with pytest.raises(ValueError, match="incomplete"):
        recovery.previous_roots(destination)

    recovered = recovery.relocate_course(store.root, destination)

    assert recovered["onboarding_id"] == original["onboarding_id"]
    assert module.Store(destination).status()["revision"] == original["revision"]


def test_relocation_retry_does_not_roll_back_newer_course_work(module, store, tmp_path):
    from courseware.recovery import relocate_course

    prepare(store)
    destination = tmp_path / "recovered course"
    relocate_course(store.root, destination)
    resumed = module.Store(destination)
    progressed = change(resumed, "start", workflow_id="fatture-xml-check")
    retained = resumed.path.read_bytes()
    shutil.rmtree(store.root)

    replayed = relocate_course(store.root, destination)

    assert replayed["status"] == "already_relocated"
    assert resumed.path.read_bytes() == retained
    assert resumed.status()["revision"] == progressed["revision"]


def test_course_relocation_preserves_unrelated_destination(module, store, tmp_path):
    from courseware.recovery import relocate_course

    prepare(store)
    destination = tmp_path / "unrelated"
    destination.mkdir()
    evidence_path = destination / "work.txt"
    evidence_path.write_text("Unrelated work")

    with pytest.raises(ValueError, match="existing destination"):
        relocate_course(store.root, destination)

    assert evidence_path.read_text() == "Unrelated work"


def test_relocation_cli_returns_retained_enrollment(module, store, tmp_path, capsys):
    original = prepare(store)
    destination = tmp_path / "relocated via cli"

    code = module.main(
        ["relocate", "--state-root", str(store.root), "--destination", str(destination)]
    )

    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["course"]["onboarding_id"] == original["onboarding_id"]
    assert result["course"]["revision"] == original["revision"]


def test_relocated_lesson_still_rejects_changed_evidence(module, store, tmp_path):
    from courseware.recovery import relocate_course

    prepare(store)
    workflow = "fatture-xml-check"
    change(store, "start", workflow_id=workflow)
    evidence(store, workflow, "demo")
    evidence(store, workflow, "practice")
    destination = tmp_path / "recovered course"
    relocate_course(store.root, destination)
    resumed = module.Store(destination)
    original_profile = resumed.path.read_bytes()
    changed = destination / "lessons" / workflow / "demo.csv"
    changed.write_text("Changed result")

    with pytest.raises(ValueError, match="artifacts changed"):
        change(
            resumed,
            "finish",
            workflow_id=workflow,
            confirmed_by_user=True,
            understanding="Cannot support completion with changed evidence",
        )

    assert resumed.path.read_bytes() == original_profile
    assert changed.read_text() == "Changed result"


def test_course_relocation_rejects_symlink_without_touching_target(
    module, store, tmp_path
):
    from courseware.recovery import relocate_course

    prepare(store)
    outside = tmp_path / "outside.txt"
    outside.write_text("Unrelated content")
    (store.root / "linked.txt").symlink_to(outside)
    destination = tmp_path / "recovered course"

    with pytest.raises(ValueError, match="symlink"):
        relocate_course(store.root, destination)

    assert not destination.exists()
    assert outside.read_text() == "Unrelated content"
