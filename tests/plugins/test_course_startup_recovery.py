"""Regression for failed XML course preparation on a slim installed package."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/_shared/vendor/modules"))
import courseware.library as runtime

from tests.plugins.test_prepared_courses import isolated
from tests.plugins.test_remote_course_files import Response, remote_case


def test_failed_xml_preview_leaves_no_partial_kit_and_retries_same_folder(
    remote_case, tmp_path, monkeypatch
):
    root, _, bodies = remote_case
    monkeypatch.setattr(
        runtime, "urlopen", lambda url, **kw: Response(bodies[url], url)
    )
    original = runtime._xml_input

    def missing(*args):
        raise ModuleNotFoundError("No module named defusedxml", name="defusedxml")

    monkeypatch.setattr(runtime, "_xml_input", missing)
    library = runtime.CourseLibrary(root, {"variance-analysis"})
    destination = tmp_path / "lesson"
    with pytest.raises(runtime.CourseError, match="defusedxml"):
        library.render("variance-analysis", "it", destination)
    assert list(destination.iterdir()) == []
    assert not list(tmp_path.glob(".course-render-*"))

    monkeypatch.setattr(runtime, "_xml_input", original)
    result = library.render("variance-analysis", "it", destination)
    request = json.loads((destination / "execution-request.json").read_text())
    assert Path(result["course"]) == destination / "course.html"
    assert Path(result["course"]).is_file()
    assert all(Path(p).is_relative_to(destination) for p in request["source_files"])
    assert all(Path(p).is_file() for p in request["source_files"])
    assert (destination / "course-provenance.json").is_file()
    assert not list(tmp_path.glob(".course-render-*"))


def test_late_render_failure_preserves_retry_and_existing_user_work(
    isolated, tmp_path, monkeypatch
):
    root, _, _ = isolated
    library = runtime.CourseLibrary(root, {"variance-analysis"})
    destination = tmp_path / "lesson"

    def failure(*args):
        raise OSError("disk write failed")

    monkeypatch.setattr(library, "_teacher", failure)
    with pytest.raises(OSError, match="disk write failed"):
        library.render("variance-analysis", "it", destination)
    assert list(destination.iterdir()) == []

    kept = destination / "my-notes.md"
    kept.write_text("keep this work")
    with pytest.raises(runtime.CourseError, match="preserve existing work"):
        library.render("variance-analysis", "it", destination)
    assert kept.read_text() == "keep this work"


def test_publish_failure_restores_empty_destination_for_retry(
    isolated, tmp_path, monkeypatch
):
    root, _, _ = isolated
    library = runtime.CourseLibrary(root, {"variance-analysis"})
    destination = tmp_path / "lesson"
    rename = Path.rename

    def fail_publish(path, target):
        if target == destination:
            raise PermissionError("publish denied")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_publish)
    with pytest.raises(PermissionError, match="publish denied"):
        library.render("variance-analysis", "it", destination)
    assert destination.is_dir()
    assert list(destination.iterdir()) == []
    assert not list(tmp_path.glob(".course-render-*"))

    monkeypatch.setattr(Path, "rename", rename)
    result = library.render("variance-analysis", "it", destination)
    assert Path(result["course"]).is_file()


def test_concurrent_user_file_is_preserved_at_publication(
    isolated, tmp_path, monkeypatch
):
    root, _, _ = isolated
    library = runtime.CourseLibrary(root, {"variance-analysis"})
    destination = tmp_path / "lesson"
    teacher = library._teacher

    def user_arrives(*args):
        (destination / "notes.md").write_text("keep my notes")
        return teacher(*args)

    monkeypatch.setattr(library, "_teacher", user_arrives)
    with pytest.raises(OSError):
        library.render("variance-analysis", "it", destination)
    assert (destination / "notes.md").read_text() == "keep my notes"
    assert not (destination / "course.html").exists()
    assert not list(tmp_path.glob(".course-render-*"))


@pytest.mark.parametrize("status", [403, 404, 503])
def test_http_failure_reports_status_and_original_file(
    remote_case, tmp_path, monkeypatch, status
):
    root, _, _ = remote_case

    def failure(url, **kwargs):
        raise HTTPError(url, status, "failure", {}, None)

    monkeypatch.setattr(runtime, "urlopen", failure)
    destination = tmp_path / "lesson"
    with pytest.raises(runtime.CourseError, match=f"HTTP {status}.*invoice-01.xml"):
        runtime.CourseLibrary(root, {"variance-analysis"}).render(
            "variance-analysis", "it", destination
        )
    assert list(destination.iterdir()) == []


def test_local_download_save_error_is_not_misreported_as_network(
    remote_case, tmp_path, monkeypatch
):
    root, _, _ = remote_case

    def failure(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(runtime, "urlopen", failure)
    with pytest.raises(runtime.CourseError, match="local save failed: PermissionError"):
        runtime.CourseLibrary(root, {"variance-analysis"}).render(
            "variance-analysis", "it", tmp_path / "lesson"
        )


def test_url_failure_preserves_underlying_reason(remote_case, tmp_path, monkeypatch):
    root, _, _ = remote_case

    def failure(*args, **kwargs):
        raise URLError("network egress blocked")

    monkeypatch.setattr(runtime, "urlopen", failure)
    with pytest.raises(runtime.CourseError, match="network egress blocked"):
        runtime.CourseLibrary(root, {"variance-analysis"}).render(
            "variance-analysis", "it", tmp_path / "lesson"
        )


@pytest.fixture
def cli(monkeypatch):
    import types

    onboarding = types.ModuleType("local_onboarding")
    onboarding.eligible_workflows = lambda: {"variance-analysis"}
    monkeypatch.setitem(sys.modules, "local_onboarding", onboarding)
    path = ROOT / "plugins/vera/scripts/local_courses.py"
    spec = importlib.util.spec_from_file_location("course_startup_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("action", ["render", "results"])
def test_course_cli_uses_verified_managed_launcher_before_render(
    cli, monkeypatch, action
):
    monkeypatch.delenv("MPARANZA_MANAGED_RUNTIME_VERIFY", raising=False)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 23)

    monkeypatch.setattr(cli.subprocess, "run", run)
    args = [action, "--workflow", "variance-analysis", "--language", "it"]
    assert cli.main(args) == 23
    command, kwargs = calls[0]
    assert command[1:3] == ["-X", "utf8"]
    assert Path(command[3]).name == "managed_python_runtime.py"
    assert command[4:] == ["run", "scripts/local_courses.py", *args]
    assert kwargs["cwd"] == cli.PLUGIN_ROOT


@pytest.mark.parametrize("action", ["list", "show", "preflight", "serve", "render"])
def test_managed_child_does_not_relaunch_and_stdlib_actions_stay_local(
    cli, monkeypatch, action
):
    if action == "render":
        monkeypatch.setenv("MPARANZA_MANAGED_RUNTIME_VERIFY", "1")
    else:
        monkeypatch.delenv("MPARANZA_MANAGED_RUNTIME_VERIFY", raising=False)
    monkeypatch.setattr(cli, "_main", lambda root, eligible, args: 0)

    def forbidden(*args, **kwargs):
        pytest.fail("must not launch or provision Python")

    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    assert cli.main([action]) == 0
