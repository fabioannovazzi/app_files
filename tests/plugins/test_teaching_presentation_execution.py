"""Run prepared presentation sources through Clara's actual local deck helpers."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile

import pytest

from tests.plugins._presentation_teaching import (
    WORDS,
    author_deck,
    build_deck,
    command,
    write,
)
from tests.plugins._teaching_release import record_native_check

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_html_kit_builds_source_faithful_standalone_slides(
    tmp_path, monkeypatch, language, phase, record_property
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from courseware.library import CourseLibrary

    kit = CourseLibrary(ROOT / "plugins/clara", {"html-deck"}).render(
        "html-deck", language, tmp_path / "kit"
    )
    inputs = [
        Path(p) for p in kit["source_files" if phase == "demo" else "practice_files"]
    ]
    source = next(p for p in inputs if p.name.startswith("brief-"))
    exercise = next((p for p in inputs if p.name.startswith("new-audience-")), None)
    original = source.read_bytes()
    work = author_deck(source, tmp_path / "work", language, exercise)
    html = build_deck(work, tmp_path / "built")
    rendered = html.read_text(encoding="utf-8")
    report = json.loads((tmp_path / "built-validation.json").read_text())
    assert report["result"] == "pass"
    assert (
        report["evidence"]["status"] == "not_verified"
    )  # No quantitative-content claim.
    assert html.parent.name == hashlib.sha256(html.read_bytes()).hexdigest()
    assert WORDS[language][0] in rendered
    assert WORDS[language][3] in rendered
    assert ('id="example"' in rendered) == (phase == "practice")
    assert 'id="responsibilities"' in rendered
    assert "REPLACE THIS" not in rendered
    assert (tmp_path / "built.zip").is_file()
    assert source.read_bytes() == original
    record_native_check(
        record_property,
        root=ROOT,
        product="clara",
        workflow="html-deck",
        language=language,
        phase=phase,
    )


@pytest.mark.parametrize("language", ["it", "en", "fr", "de", "es"])
@pytest.mark.parametrize("phase", ["demo", "practice"])
def test_correction_kit_changes_only_the_requested_slide(
    tmp_path, monkeypatch, language, phase, record_property
):
    monkeypatch.syspath_prepend(str(ROOT / "plugins/_shared/vendor/modules"))
    from courseware.library import CourseLibrary

    kit = CourseLibrary(ROOT / "plugins/clara", {"deck-correction"}).render(
        "deck-correction", language, tmp_path / "kit"
    )
    files = [
        Path(p) for p in kit["source_files" if phase == "demo" else "practice_files"]
    ]
    archive_path = next(p for p in files if p.suffix == ".zip")
    original_html = next(p for p in files if p.suffix == ".html")
    feedback = next(p for p in files if p.suffix == ".md")
    original = tmp_path / "original"
    original.mkdir()
    expected = {
        "deck.json",
        "deck-plan.json",
        "content-ledger.json",
        "slides.html",
        "custom.css",
        f"brief-{language}.md",
    }
    with ZipFile(archive_path) as archive:
        assert set(archive.namelist()) == expected
        for name in sorted(expected):
            (original / name).write_bytes(archive.read(name))
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in original.iterdir()
    }
    baseline_built = build_deck(original, tmp_path / "baseline-built")
    assert baseline_built.read_bytes() == original_html.read_bytes()
    command("inspect_html_deck.py", original, "--report", tmp_path / "baseline.json")
    inventory = json.loads((tmp_path / "baseline.json").read_text())
    plan = json.loads((original / "deck-plan.json").read_text())
    target = "responsibilities" if phase == "demo" else "decision"
    revision = {
        "schema_version": "clara.html_deck_revision_map.v1",
        "baseline_fingerprint": inventory["deck"]["normalized_dom_fingerprint"],
        "global_edits": ["deck-plan", "content-ledger"],
        "edit_targets": [
            {
                "slide_id": target,
                "scope": "slide",
                "component_ids": [],
                "reason": feedback.read_text(),
            }
        ],
        "untouched_slides": [s["id"] for s in plan["slides"] if s["id"] != target],
        "protected_slides": [],
        "protected_components": [],
        "slide_changes": {
            "add": [],
            "remove": [],
            "rename": [],
            "after_order": [s["id"] for s in plan["slides"]],
        },
    }
    revision_path = tmp_path / "revision-map.json"
    write(revision_path, revision)
    command(
        "validate_revision_map.py",
        original,
        revision_path,
        "--report",
        tmp_path / "map-validation.json",
    )
    corrected = tmp_path / "corrected"
    shutil.copytree(original, corrected)
    (corrected / feedback.name).write_bytes(feedback.read_bytes())
    slide = next(s for s in plan["slides"] if s["id"] == target)
    if phase == "demo":
        assert "Sara" in slide["slots"]["body"]
        slide["slots"]["body"] = slide["slots"]["body"].replace("Sara", "Elena")
    else:
        w = WORDS[language]
        slide["title"] = slide["slots"]["title"] = w[29]
        slide["slots"]["actions"] = [
            {"verb": verb, "body": body}
            for verb, body in zip(w[30], w[31], strict=True)
        ]
        slide["slots"]["closing_line"] = w[32]
        slide["notes"] = w[32]
    slide["source_refs"].append("feedback")
    ledger = json.loads((corrected / "content-ledger.json").read_text())
    ledger["sources"].append(
        {
            "id": "feedback",
            "label": feedback.name,
            "kind": "document",
            "locator": feedback.name,
            "sha256": hashlib.sha256(feedback.read_bytes()).hexdigest(),
            "publish_locator": False,
        }
    )
    claim = next(s for s in ledger["slides"] if s["slide_id"] == target)["claims"][0]
    claim["source_ids"].append("feedback")
    claim["statement"] = slide["title"]
    write(corrected / "deck-plan.json", plan)
    write(corrected / "content-ledger.json", ledger)
    command(
        "compose_html_deck.py",
        corrected / "deck-plan.json",
        "--output-dir",
        corrected,
        "--force",
    )
    command(
        "compare_html_deck_revision.py",
        original,
        corrected,
        "--revision-map",
        revision_path,
        "--report",
        tmp_path / "revision-comparison.json",
    )
    comparison = json.loads((tmp_path / "revision-comparison.json").read_text())
    assert comparison["result"] == "pass"
    html = build_deck(corrected, tmp_path / "corrected-built")
    assert html.read_bytes() != original_html.read_bytes()
    assert {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in original.iterdir()
    } == hashes
    rendered = html.read_text()
    if phase == "demo":
        assert "Elena" in rendered and "Sara" not in rendered
    else:
        assert WORDS[language][29] in rendered
        assert "Sara" in rendered
    record_native_check(
        record_property,
        root=ROOT,
        product="clara",
        workflow="deck-correction",
        language=language,
        phase=phase,
    )
