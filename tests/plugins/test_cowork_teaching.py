"""Exercise the written lesson CLI from installable Cowork archives."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=["vera", "clara", "lucia"])
def installed(request, tmp_path):
    product = request.param
    with ZipFile(
        ROOT / f"plugin_packages/{product}/{product}-claude-plugin.zip"
    ) as archive:
        archive.extractall(tmp_path / "installed")
    manifest = next((tmp_path / "installed").rglob(".claude-plugin/plugin.json"))
    return product, manifest.parent.parent, tmp_path.resolve()


def run(root, *args):
    return subprocess.run(
        [sys.executable, str(root / "scripts/local_courses.py"), *map(str, args)],
        cwd=root.parent,
        capture_output=True,
        text=True,
    )


def test_installed_cowork_prepares_every_supported_course_and_language(installed):
    product, root, output = installed
    result = run(root, "list")
    assert result.returncode == 0, result.stderr
    catalog = json.loads(result.stdout)
    assert len(catalog) == {"vera": 32, "clara": 7, "lucia": 4}[product]
    for entry in catalog:
        workflow = entry["workflow"]
        assert (root / f"skills/{workflow}/SKILL.md").is_file()
        for language in entry["languages"]:
            destination = output / workflow / language
            result = run(
                root,
                "prepare",
                workflow,
                "--language",
                language,
                "--output-dir",
                destination,
            )
            assert result.returncode == 0, result.stderr
            receipt = json.loads(result.stdout)
            assert receipt["execution_receipt"] is False
            assert receipt["understanding_confirmed"] is False
            assert receipt["mode"] == "cowork-written-single-conversation"
            assert not (destination / "execution-request.json").exists()
            assert (destination / ".vera-onboarding-local-only").exists()
            assert "not executed" in (destination / "lesson-progress.md").read_text()
            guide = (destination / "course.html").read_text()
            assert "OpenAI" not in guide
            assert not re.search(
                r"voice (chat|thread)|working (chat|thread|window)|chat vocale|"
                r"conversazione vocale|chat di lavoro|thread di lavoro|finestra di lavoro|"
                r"conversation vocale|fil vocal|Sprachchat|Arbeitschat|"
                r"Arbeitsfenster|Arbeitsthread|conversación de voz|"
                r"hilo de voz|chat de voz|ventana de trabajo",
                guide,
                flags=re.IGNORECASE,
            ), (product, workflow, language)
            assert "Codex" not in guide
            assert "Anthropic" in guide
            assert (
                "execution-request.json" not in (destination / "teacher.md").read_text()
            )


def test_cowork_rejects_foreign_missing_or_unsupported_lesson(installed):
    _, root, output = installed
    for workflow, language in [
        ("not-installed", "en"),
        ("brand-fit", "en"),
        ("new-client", "zz"),
    ]:
        result = run(
            root,
            "prepare",
            workflow,
            "--language",
            language,
            "--output-dir",
            output / workflow,
        )
        assert result.returncode != 0
        assert not (output / workflow).exists()


def test_cowork_rejects_changed_workflow_before_preparing(installed):
    _, root, output = installed
    catalog = json.loads(run(root, "list").stdout)
    entry = catalog[0]
    skill = root / f'skills/{entry["workflow"]}/SKILL.md'
    skill.write_text(skill.read_text() + "\nChanged procedure\n")
    result = run(
        root,
        "prepare",
        entry["workflow"],
        "--language",
        entry["languages"][0],
        "--output-dir",
        output / "lesson",
    )
    assert result.returncode != 0
    assert "editorial refresh" in result.stderr
    assert not (output / "lesson").exists()


def test_cowork_preserves_existing_lesson_on_resume(installed):
    _, root, output = installed
    entry = json.loads(run(root, "list").stdout)[0]
    destination = output / "lesson"
    args = (
        "prepare",
        entry["workflow"],
        "--language",
        entry["languages"][0],
        "--output-dir",
        destination,
    )
    assert run(root, *args).returncode == 0
    progress = destination / "lesson-progress.md"
    progress.write_text("User paused after examining the input.\n")
    assert run(root, *args).returncode != 0
    assert progress.read_text() == "User paused after examining the input.\n"


def test_cowork_tutorial_marker_suppresses_receipt_transport(installed, monkeypatch):
    import importlib.util

    product, root, output = installed
    if product != "vera":
        pytest.skip("Vera owns the receipt transport helper")
    spec = importlib.util.spec_from_file_location(
        "cowork_lesson_receipt", root / "scripts/notarized_run_receipt.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_validated_report", lambda path: {})
    lesson = output / "lesson"
    lesson.mkdir()
    (lesson / ".vera-onboarding-local-only").touch()
    report = lesson / "report.json"
    report.write_text("{}")

    def forbidden_transport(*args, **kwargs):
        pytest.fail("A lesson must not invoke receipt transport")

    result = module.stamp_model_data_report(
        report, output_dir=lesson, plugin_root=root, opener=forbidden_transport
    )
    assert result == {"status": "not_requested", "reason": "local_onboarding"}


@pytest.mark.parametrize("path_type", ["PurePosixPath", "PureWindowsPath"])
def test_course_attachment_archive_names_are_portable(monkeypatch, path_type):
    """A Windows build must resolve the same slash-separated archive input."""
    import hashlib
    import pathlib

    from scripts.cowork_teaching import projection

    skill = "skills/example/SKILL.md"
    attachment = "assets/courses/example/files/input/note.md"
    content = b"Fictional input\n"
    course = {
        "sources": [{"path": skill, "sha256": hashlib.sha256(b"method").hexdigest()}],
        "files": [
            {
                "path": "files/input/note.md",
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ],
    }
    course_bytes = json.dumps(course).encode()
    index = {
        "product": "clara",
        "courses": {
            "example": {
                "path": "example/course.json",
                "sha256": hashlib.sha256(course_bytes).hexdigest(),
            }
        },
    }
    source = {
        "assets/courses/index.json": json.dumps(index).encode(),
        "assets/courses/example/course.json": course_bytes,
        attachment: content,
        skill: b"method",
    }
    entries = {skill: b"projected method", "skills/clara/SKILL.md": b"Clara"}
    original_read = Path.read_text

    def windows_default_read(path, *args, **kwargs):
        if not args:
            kwargs.setdefault("encoding", "cp1252")
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", windows_default_read)
    monkeypatch.setattr(projection, "Path", getattr(pathlib, path_type))
    projection.add_written_teaching(ROOT, "clara", source, entries)
    assert entries[attachment] == content
    assert not any("\\" in name for name in entries)
