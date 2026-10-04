"""Course storage is a prerequisite, including after permissions are revoked."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from tests.plugins import test_desktop_teaching as desktop
from tests.plugins import test_vera_local_onboarding as vera

sys.path.insert(0, str(vera.ROOT / "plugins/_shared/vendor/modules"))
from courseware import access as course_access
from courseware.access import CourseAccessError, verify_course_access
from desktop_teaching import onboarding, teaching

__all__: list[str] = []


def test_preflight_checks_real_io_preserves_files_and_cleans_up(tmp_path, monkeypatch):
    root = tmp_path / "course with spaces"
    root.mkdir()
    saved = root / "progress.json"
    saved.write_text("original progress")
    monkeypatch.setattr("os.access", lambda *_args: False)

    result = verify_course_access([root, root])

    assert result == {"status": "ready", "directories": [str(root)]}
    assert list(root.iterdir()) == [saved]
    assert saved.read_text() == "original progress"


@pytest.mark.parametrize(
    ("method", "operation"),
    [
        ("mkdir", "create_directory"),
        ("write_text", "write_file"),
        ("read_text", "read_file"),
        ("replace", "replace_file"),
        ("unlink", "delete_file"),
        ("rmdir", "delete_directory"),
    ],
)
def test_preflight_reports_actual_failed_operation(
    tmp_path, monkeypatch, method, operation
):
    error = PermissionError(13, "test access denial")
    error.winerror = 5

    def deny(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(Path, method, deny)

    with pytest.raises(CourseAccessError) as failure:
        verify_course_access([tmp_path])

    result = failure.value.as_dict()
    assert result["status"] == "blocked"
    assert result["directory"] == str(tmp_path)
    assert result["operation"] == operation
    assert result["errno"] == 13
    assert result["winerror"] == 5
    assert result["error"] == str(error)


def test_preflight_rejects_failed_update_without_leaving_probe(tmp_path, monkeypatch):
    write = Path.write_text

    def deny_update(path, data, **kwargs):
        if data == "updated\n":
            raise OSError(28, "test disk full")
        return write(path, data, **kwargs)

    monkeypatch.setattr(Path, "write_text", deny_update)

    with pytest.raises(CourseAccessError) as failure:
        verify_course_access([tmp_path])

    assert failure.value.as_dict()["operation"] == "update_file"
    assert failure.value.as_dict()["errno"] == 28
    assert list(tmp_path.iterdir()) == []


def test_preflight_rejects_link_without_writing_target(tmp_path):
    target = tmp_path / "original"
    target.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(target, target_is_directory=True)

    with pytest.raises(CourseAccessError):
        verify_course_access([link])

    assert list(target.iterdir()) == []


@pytest.fixture(params=["vera", "clara", "lucia"])
def product(request, tmp_path, monkeypatch):
    # The repository fixture unloads plugin modules between tests; retain the
    # same exception identity when the standalone Vera script imports again.
    monkeypatch.setitem(sys.modules, "courseware.access", course_access)
    name = request.param
    if name == "vera":
        monkeypatch.syspath_prepend(str(vera.SCRIPTS))
        module = vera.load("local_onboarding")
        monkeypatch.setitem(sys.modules, "local_onboarding", module)
        repeated = vera.load("local_teaching")
        return name, module.Store(tmp_path / name), module.main, repeated.TeachingStore
    root = vera.ROOT / "plugins" / name
    store = onboarding.Store(tmp_path / name, plugin_root=root)
    return (
        name,
        store,
        lambda args: onboarding.main(args, plugin_root=root),
        lambda state_root: teaching.TeachingStore(state_root, plugin_root=root),
    )


def deny_probe(monkeypatch, directory):
    replace = Path.replace

    def deny(path, target):
        if path.parent.parent == directory and path.parent.name.startswith(
            ".course-access-"
        ):
            raise PermissionError(13, "test revoked write access")
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", deny)


def test_preflight_cli_needs_no_input_or_enrollment(product, capsys):
    _, store, main, _ = product

    code = main(["preflight", "--state-root", str(store.root)])

    assert code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ready"
    assert store.status()["phase"] == "required"
    assert list(store.root.iterdir()) == []


def test_denied_begin_cli_does_not_enroll_or_advance(product, monkeypatch, capsys):
    _, store, main, _ = product
    deny_probe(monkeypatch, store.root)

    code = main(["begin", "--state-root", str(store.root)])

    assert code == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "course_file_access"
    assert not store.path.exists()
    assert not store.enrollment.exists()


def test_workspace_cli_returns_exact_folder_without_writing(product, capsys):
    name, store, main, _ = product

    code = main(["workspace", "--state-root", str(store.root)])

    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["product"] == name
    assert result["workspace_directory"] == str(store.root)
    assert result["setup_argv"][-3:] == ["setup", "--state-root", str(store.root)]
    assert not store.root.exists()


def test_setup_saves_and_reloads_new_course_before_first_question(product, capsys):
    _, store, main, _ = product

    code = main(["setup", "--state-root", str(store.root)])

    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["status"] == "ready"
    assert result["course"] == store.status()
    assert result["course"]["phase"] == "interview"
    assert result["course"]["revision"] == 1
    assert result["course"]["lessons"] == []
    assert store.path.is_file()
    assert store.enrollment.is_file()


def test_setup_preserves_existing_profile_and_revision(product):
    _, store, _, _ = product
    state = store.begin()
    store.change("notes", state["revision"], {"notes": "Keep this answer"})
    saved = store.path.read_bytes()
    enrollment = store.enrollment.read_bytes()

    result = store.setup()

    assert result["status"] == "ready"
    assert store.path.read_bytes() == saved
    assert store.enrollment.read_bytes() == enrollment


def test_setup_catches_denied_profile_save_even_when_probe_passes(
    product, monkeypatch, capsys
):
    _, store, main, _ = product
    store.begin()
    saved = store.path.read_bytes()
    replace = os.replace

    def deny_profile(source, destination):
        if Path(destination) == store.path:
            raise PermissionError(13, "Profile replacement denied", str(destination))
        return replace(source, destination)

    monkeypatch.setattr(os, "replace", deny_profile)

    code = main(["setup", "--state-root", str(store.root)])

    result = json.loads(capsys.readouterr().out)
    assert code == 2
    assert result["status"] == "blocked"
    assert result["operation"] == "save_and_reload_profile"
    assert result["filename"] == str(store.path)
    assert result["workspace"]["workspace_directory"] == str(store.root)
    assert store.path.read_bytes() == saved


@pytest.fixture(params=["first", "repeated"])
def active(product, request):
    name, store, _, repeated = product
    workflow = "fatture-xml-check" if name == "vera" else desktop.WORKFLOWS[name][0]
    prepare = vera.prepare if name == "vera" else desktop.prepare
    prepare(store)
    if request.param == "repeated":
        workflows = [item["workflow_id"] for item in store.status()["lessons"]]
        for selected in workflows:
            if name == "vera":
                vera.finish(store, selected)
            else:
                desktop.change(store, "start", workflow_id=selected)
                desktop.evidence(store, "demo", selected)
                desktop.evidence(store, "practice", selected)
                desktop.change(
                    store,
                    "finish",
                    workflow_id=selected,
                    confirmed_by_user=True,
                    understanding="Fixture review",
                )
        store = repeated(store.root)
        state = store.begin(
            {"workflow_id": workflow, "title": "Example", "goal": "Learn"}
        )["session"]
        checkpoint = store.sessions / state["session_id"] / "session.json"
    else:
        state = vera.change(store, "start", workflow_id=workflow)
        checkpoint = store.path
    lesson = state if request.param == "repeated" else state["lessons"][0]
    worker_id = state["pair"]["worker_thread_id"]
    return store, lesson, checkpoint, worker_id, request.param


def test_revoked_lesson_access_blocks_worker_without_changing_progress(
    active, monkeypatch
):
    store, lesson, checkpoint, worker_id, _ = active
    before = checkpoint.read_bytes()
    deny_probe(monkeypatch, Path(lesson["directory"]))

    with pytest.raises(CourseAccessError):
        store.worker(worker_id, lesson["workflow_id"], lesson["worker_token"])

    assert checkpoint.read_bytes() == before


def test_revoked_lesson_access_keeps_resume_paused(active, monkeypatch):
    store, lesson, checkpoint, _, entry = active
    data = {"next_step": "Continue after setup"}
    if entry == "first":
        data["workflow_id"] = lesson["workflow_id"]
    state = store.status()
    revision = state["revision"] if entry == "first" else state["session"]["revision"]
    paused = store.change("pause", revision, data)
    revision = paused["revision"] if entry == "first" else paused["session"]["revision"]
    before = checkpoint.read_bytes()
    deny_probe(monkeypatch, Path(lesson["directory"]))

    with pytest.raises(CourseAccessError):
        store.change("resume", revision, data)

    assert checkpoint.read_bytes() == before


def test_successful_retry_allows_same_lesson_worker(active, monkeypatch):
    store, lesson, checkpoint, worker_id, _ = active
    before = checkpoint.read_bytes()
    with monkeypatch.context() as denied:
        deny_probe(denied, Path(lesson["directory"]))
        with pytest.raises(CourseAccessError):
            store.worker(worker_id, lesson["workflow_id"], lesson["worker_token"])

    result = store.worker(worker_id, lesson["workflow_id"], lesson["worker_token"])

    assert result["state_root"] == str(store.root)
    assert result["lesson"]["directory"] == lesson["directory"]
    assert checkpoint.read_bytes() == before
