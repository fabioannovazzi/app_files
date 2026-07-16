from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "clara"
SKILL_ROOT = PLUGIN_ROOT / "skills" / "html-deck"
RUNTIME_PATH = PLUGIN_ROOT / "scripts" / "html_deck_runtime.py"


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_script(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPYCACHEPREFIX"] = "/tmp/html-deck-test-pycache"
    return subprocess.run(
        [sys.executable, str(path), *args],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def minimal_slides() -> str:
    return """
    <section class="slide is-active" id="opening" data-slide-title="Opening claim"
      data-chapter="opening" data-chapter-label="Opening" aria-hidden="false">
      <div class="slide-frame"><h1>Opening claim</h1>
        <section data-qa-role="evidence"><p>Evidence and implication.</p></section></div>
      <aside class="speaker-notes">Explain the decision context.</aside>
    </section>
    <section class="slide" id="decision" data-slide-title="Decision"
      data-chapter="decision" data-chapter-label="Decision" aria-hidden="true">
      <div class="slide-frame"><h2>Choose the governed next move</h2>
        <p data-fragment="1">Condition one.</p><p data-fragment="2">Condition two.</p></div>
      <aside class="speaker-notes">Close on the owner and next action.</aside>
    </section>
    """


def write_minimal_ledger(work: Path) -> None:
    ledger = {
        "schema_version": "clara.html_deck_ledger.v1",
        "sources": [
            {
                "id": "source-a",
                "label": "Approved workpaper",
                "kind": "workpaper",
                "locator": "/private/advisory_workpaper.md",
            }
        ],
        "slides": [
            {
                "slide_id": "opening",
                "basis_status": "speaker-judgement",
                "basis_note": "Advisor-approved opening framing.",
                "claims": [],
            },
            {
                "slide_id": "decision",
                "basis_status": "source-backed",
                "basis_note": "",
                "claims": [
                    {
                        "id": "claim-decision",
                        "statement": "The next move needs explicit governance.",
                        "classification": "judgement",
                        "basis_status": "source-backed",
                        "basis_note": "",
                        "source_ids": ["source-a"],
                    }
                ],
            },
        ],
    }
    (work / "content-ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def initialize_work(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    result = run_script(
        SKILL_ROOT / "scripts" / "init_html_deck.py",
        "--work-dir",
        str(work),
        "--title",
        "Decision Brief",
        "--subtitle",
        "From evidence to action",
        "--author",
        "Advisory team",
        "--eyebrow",
        "Leadership discussion",
        "--language",
        "en",
    )
    assert result.returncode == 0, result.stderr
    return work


def test_skill_identity_uses_plugin_namespace_without_redundant_prefix() -> None:
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    agent_metadata = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert "\nname: html-deck\n" in f"\n{skill_text}"
    assert 'display_name: "HTML Deck"' in agent_metadata
    assert "Use $html-deck" in agent_metadata
    assert not (PLUGIN_ROOT / "skills" / "clara-html-deck").exists()


def test_runtime_supports_stacked_and_stage_profiles() -> None:
    runtime = load_module("clara_html_deck_runtime_v2", RUNTIME_PATH)
    stacked = "<!doctype html><html><head></head><body><main><section>One</section></main></body></html>"
    fixed_stacked = runtime.apply_fixed_16_9_deck_runtime(stacked)
    runtime.assert_html_deck_runtime(fixed_stacked, label="stacked", profile="stacked")
    assert runtime.apply_fixed_16_9_deck_runtime(fixed_stacked) == fixed_stacked

    stage = (
        '<!doctype html><html><head></head><body><main class="deck-stage" '
        'data-clara-deck-mode="stage"><section class="slide is-active" id="one" '
        'data-slide-title="One" aria-hidden="false"></section></main></body></html>'
    )
    fixed_stage = runtime.apply_html_deck_runtime(stage, profile="stage")
    runtime.assert_html_deck_runtime(fixed_stage, label="stage", profile="stage")
    assert runtime.apply_html_deck_runtime(fixed_stage, profile="stage") == fixed_stage
    assert "stageProfile" in fixed_stage
    assert "MutationObserver" in fixed_stage
    assert "clara:slidechange" in fixed_stage
    assert "slide.classList.contains('is-active')" in fixed_stage
    assert "slide.dataset.title" in fixed_stage
    with pytest.raises(ValueError, match="already contains"):
        runtime.apply_html_deck_runtime(fixed_stage, profile="stacked")


def test_scaffold_builds_content_addressed_standalone_deck(tmp_path: Path) -> None:
    work = initialize_work(tmp_path)
    assert (work / "deck-plan.json").is_file()
    starter_plan = json.loads((work / "deck-plan.json").read_text(encoding="utf-8"))
    starter_ledger = json.loads(
        (work / "content-ledger.json").read_text(encoding="utf-8")
    )
    assert [slide["id"] for slide in starter_plan["slides"]] == [
        slide["slide_id"] for slide in starter_ledger["slides"]
    ]
    (work / "slides.html").write_text(minimal_slides(), encoding="utf-8")
    write_minimal_ledger(work)
    output_root = tmp_path / "dist"
    package = tmp_path / "deck.zip"
    report = tmp_path / "validation.json"
    build = run_script(
        SKILL_ROOT / "scripts" / "build_html_deck.py",
        str(work),
        "--output-root",
        str(output_root),
        "--package",
        str(package),
        "--report",
        str(report),
    )
    assert build.returncode == 0, build.stderr or build.stdout
    payload = json.loads(build.stdout)
    publication_id = payload["output"]["publication_id"]
    assert len(publication_id) == 64
    assert set(publication_id) <= set("0123456789abcdef")
    index_path = output_root / publication_id / "index.html"
    assert index_path.is_file()
    html_text = index_path.read_text(encoding="utf-8")
    assert 'data-clara-runtime-profile="stage"' in html_text
    assert "noindex,nofollow,noarchive" in html_text
    assert "https://" not in html_text
    assert "http://" not in html_text
    assert "box-shadow" not in html_text
    assert "slideCounter" not in html_text
    assert 'id="claraContentLedger"' in html_text
    assert "/private/advisory_workpaper.md" not in html_text
    assert json.loads(report.read_text(encoding="utf-8"))["result"] == "pass"
    with ZipFile(package) as archive:
        assert archive.namelist() == [
            f"{publication_id}/",
            f"{publication_id}/index.html",
        ]
        assert archive.read(f"{publication_id}/index.html") == index_path.read_bytes()

    first_package = package.read_bytes()
    rebuild = run_script(
        SKILL_ROOT / "scripts" / "build_html_deck.py",
        str(work),
        "--output-root",
        str(output_root),
        "--package",
        str(package),
    )
    assert rebuild.returncode == 0, rebuild.stderr or rebuild.stdout
    assert package.read_bytes() == first_package


def test_unedited_scaffold_is_rejected(tmp_path: Path) -> None:
    work = initialize_work(tmp_path)
    result = run_script(
        SKILL_ROOT / "scripts" / "build_html_deck.py",
        str(work),
        "--output-root",
        str(tmp_path / "dist"),
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    failed = {item["code"] for item in payload["checks"] if item["status"] == "fail"}
    assert "content.template_examples" in failed
    assert "content.placeholders" in failed


def test_validator_rejects_remote_resources_and_duplicate_ids(tmp_path: Path) -> None:
    work = initialize_work(tmp_path)
    slides = minimal_slides().replace('id="decision"', 'id="opening"')
    (work / "slides.html").write_text(slides, encoding="utf-8")
    write_minimal_ledger(work)
    (work / "custom.css").write_text(
        '@import url("https://example.com/theme.css");\n', encoding="utf-8"
    )
    result = run_script(
        SKILL_ROOT / "scripts" / "build_html_deck.py",
        str(work),
        "--output-root",
        str(tmp_path / "dist"),
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    failed = {item["code"] for item in payload["checks"] if item["status"] == "fail"}
    assert "slides.ids_unique" in failed
    assert "document.ids_unique" in failed
    assert "resources.css_embedded" in failed


def test_validator_rejects_claim_reference_from_another_slide(tmp_path: Path) -> None:
    work = initialize_work(tmp_path)
    slides = minimal_slides().replace(
        'id="opening" data-slide-title="Opening claim"',
        'id="opening" data-slide-title="Opening claim" '
        'data-claim-ids="claim-decision"',
    )
    (work / "slides.html").write_text(slides, encoding="utf-8")
    write_minimal_ledger(work)

    result = run_script(
        SKILL_ROOT / "scripts" / "build_html_deck.py",
        str(work),
        "--output-root",
        str(tmp_path / "dist"),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    failed = {item["code"] for item in payload["checks"] if item["status"] == "fail"}
    assert "provenance.claim_refs" in failed


@pytest.mark.parametrize(
    "unsafe_markup",
    [
        '<a href="jav&#x61;script:alert(1)">Run</a>',
        '<svg/onload="alert(1)"></svg>',
    ],
)
def test_validator_rejects_executable_attributes(
    tmp_path: Path,
    unsafe_markup: str,
) -> None:
    work = initialize_work(tmp_path)
    slides = minimal_slides().replace(
        "<p>Evidence and implication.</p>",
        f"<p>Evidence and implication.</p>{unsafe_markup}",
    )
    (work / "slides.html").write_text(slides, encoding="utf-8")
    write_minimal_ledger(work)

    result = run_script(
        SKILL_ROOT / "scripts" / "build_html_deck.py",
        str(work),
        "--output-root",
        str(tmp_path / "dist"),
    )

    assert result.returncode == 1
    failed = {
        item["code"]
        for item in json.loads(result.stdout)["checks"]
        if item["status"] == "fail"
    }
    assert "security.executable_attributes" in failed


def test_validator_does_not_treat_prose_or_ledger_words_as_code(tmp_path: Path) -> None:
    work = initialize_work(tmp_path)
    phrase = "fetch WebSocket eval( box-shadow slideCounter TODO url(example)"
    slides = minimal_slides().replace(
        "Explain the decision context.",
        phrase,
    )
    (work / "slides.html").write_text(slides, encoding="utf-8")
    write_minimal_ledger(work)
    ledger_path = work / "content-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["slides"][0]["claims"] = [
        {
            "id": "claim-keyword-prose",
            "statement": phrase,
            "classification": "judgement",
            "basis_status": "speaker-judgement",
            "basis_note": "Literal terminology in the reviewed source.",
            "source_ids": [],
        }
    ]
    ledger_path.write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = run_script(
        SKILL_ROOT / "scripts" / "build_html_deck.py",
        str(work),
        "--output-root",
        str(tmp_path / "dist"),
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_validator_does_not_leak_slide_state_after_void_image(tmp_path: Path) -> None:
    work = initialize_work(tmp_path)
    pixel = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    slides = minimal_slides().replace(
        "<p>Evidence and implication.</p>",
        f'<p>Evidence and implication.</p><img src="{pixel}" alt="Evidence mark">',
    )
    slides += '<div data-source-ids="outside-slide">Outside the stage slides.</div>'
    (work / "slides.html").write_text(slides, encoding="utf-8")
    write_minimal_ledger(work)

    result = run_script(
        SKILL_ROOT / "scripts" / "build_html_deck.py",
        str(work),
        "--output-root",
        str(tmp_path / "dist"),
    )

    assert result.returncode == 0, result.stderr or result.stdout


def write_static_compatibility_deck(root: Path) -> Path:
    """Write the narrow linked-file profile used by the sealed benchmark."""

    (root / "assets").mkdir(parents=True)
    (root / "assets" / "chart.png").write_bytes(b"sealed-chart")
    (root / "styles.css").write_text(
        "html,body{margin:0;overflow:hidden}.deck,.slide{width:1280px;height:720px}"
        ".deck{position:relative}.slide{position:absolute;inset:0;overflow:hidden}"
        ".slide[hidden]{display:none}",
        encoding="utf-8",
    )
    (root / "deck.js").write_text(
        "window.addEventListener('keydown',(event)=>{"
        "if(event.key==='ArrowRight')location.hash='2';"
        "if(event.key==='ArrowLeft')location.hash='1';});",
        encoding="utf-8",
    )
    index = root / "index.html"
    index.write_text(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=1280, initial-scale=1'>"
        "<title>Static deck</title><link rel='stylesheet' href='styles.css'>"
        "<script src='deck.js' defer></script></head><body><main class='deck'>"
        "<section class='slide'><h1>One</h1><img src='assets/chart.png' alt='Chart'></section>"
        "<section class='slide' hidden><h1>Two</h1></section>"
        "</main></body></html>",
        encoding="utf-8",
    )
    return index


def write_static_content_spec(root: Path) -> Path:
    """Write the controlling visible-copy contract for the static test deck."""

    empty_fields = {
        "eyebrow": "",
        "brand": "",
        "chart_caption_left": "",
        "chart_caption_right": "",
        "narrative_headline": "",
        "note": "",
        "footer": "",
    }
    spec = {
        "slides": [
            {
                **empty_fields,
                "title": "ONE",
                "kpis": [{"label": "Growth", "value": "+26.3%"}],
                "number": 1,
            },
            {
                **empty_fields,
                "title": "Two",
                "kpis": [],
                "number": 2,
            },
        ]
    }
    path = root / "deck_spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def add_static_controlled_copy(index: Path) -> None:
    """Add exactly the copy declared by ``write_static_content_spec``."""

    source = index.read_text(encoding="utf-8")
    source = source.replace(
        "<h1>One</h1>", "<h1>One</h1><p>Growth +26.3%</p><span>1</span>"
    )
    source = source.replace("<h1>Two</h1>", "<h1>Two</h1><span>2</span>")
    index.write_text(source, encoding="utf-8")


def test_static_profile_allows_sealed_linked_deck_without_clara_chrome(
    tmp_path: Path,
) -> None:
    index = write_static_compatibility_deck(tmp_path)

    compatible = run_script(
        SKILL_ROOT / "scripts" / "validate_html_deck.py",
        str(index),
        "--profile",
        "static",
        "--allow-readable-path",
    )
    strict = run_script(
        SKILL_ROOT / "scripts" / "validate_html_deck.py",
        str(index),
        "--allow-readable-path",
    )

    compatible_report = json.loads(compatible.stdout)
    assert compatible.returncode == 0, compatible.stderr or compatible.stdout
    assert compatible_report["profile"] == "static"
    assert compatible_report["result"] == "pass"
    assert not any(
        check["code"] == "content.exact_spec_copy"
        for check in compatible_report["checks"]
    )
    assert strict.returncode == 1
    strict_failures = {
        check["code"]
        for check in json.loads(strict.stdout)["checks"]
        if check["status"] == "fail"
    }
    assert "resources.self_contained" in strict_failures
    assert "slides.notes" in strict_failures


def test_static_content_spec_accepts_exact_visible_token_multisets(
    tmp_path: Path,
) -> None:
    index = write_static_compatibility_deck(tmp_path)
    add_static_controlled_copy(index)
    content_spec = write_static_content_spec(tmp_path)

    result = run_script(
        SKILL_ROOT / "scripts" / "validate_html_deck.py",
        str(index),
        "--profile",
        "static",
        "--allow-readable-path",
        "--content-spec",
        str(content_spec),
    )

    report = json.loads(result.stdout)
    copy_check = next(
        check
        for check in report["checks"]
        if check["code"] == "content.exact_spec_copy"
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert copy_check["status"] == "pass"
    assert "2 slides" in copy_check["message"]


def test_static_content_spec_rejects_extra_visible_page_number_tokens(
    tmp_path: Path,
) -> None:
    index = write_static_compatibility_deck(tmp_path)
    add_static_controlled_copy(index)
    index.write_text(
        index.read_text(encoding="utf-8").replace(
            "<span>1</span>", "<span>1 / 2</span>"
        ),
        encoding="utf-8",
    )
    content_spec = write_static_content_spec(tmp_path)

    result = run_script(
        SKILL_ROOT / "scripts" / "validate_html_deck.py",
        str(index),
        "--profile",
        "static",
        "--allow-readable-path",
        "--content-spec",
        str(content_spec),
    )

    report = json.loads(result.stdout)
    copy_check = next(
        check
        for check in report["checks"]
        if check["code"] == "content.exact_spec_copy"
    )
    assert result.returncode == 1
    assert copy_check["status"] == "fail"
    assert '"slide": 1' in copy_check["message"]
    assert '"extra": {"2": 1}' in copy_check["message"]


@pytest.mark.parametrize(
    ("spec_content", "expected_message"),
    [
        (None, "Unable to load controlling content spec"),
        ("{not-json", "Unable to load controlling content spec"),
        ('{"slides": [{}]}', "Invalid controlling content spec"),
    ],
)
def test_static_content_spec_load_or_shape_errors_are_explicit_checks(
    tmp_path: Path,
    spec_content: str | None,
    expected_message: str,
) -> None:
    index = write_static_compatibility_deck(tmp_path)
    spec_path = tmp_path / "invalid-deck-spec.json"
    if spec_content is not None:
        spec_path.write_text(spec_content, encoding="utf-8")

    result = run_script(
        SKILL_ROOT / "scripts" / "validate_html_deck.py",
        str(index),
        "--profile",
        "static",
        "--allow-readable-path",
        "--content-spec",
        str(spec_path),
    )

    report = json.loads(result.stdout)
    copy_check = next(
        check
        for check in report["checks"]
        if check["code"] == "content.exact_spec_copy"
    )
    assert result.returncode == 1
    assert copy_check["status"] == "fail"
    assert expected_message in copy_check["message"]


def test_static_profile_still_rejects_remote_dependencies(tmp_path: Path) -> None:
    index = write_static_compatibility_deck(tmp_path)
    index.write_text(
        index.read_text(encoding="utf-8").replace(
            "styles.css", "https://example.com/styles.css"
        ),
        encoding="utf-8",
    )

    result = run_script(
        SKILL_ROOT / "scripts" / "validate_html_deck.py",
        str(index),
        "--profile",
        "static",
        "--allow-readable-path",
    )

    assert result.returncode == 1
    failures = {
        check["code"]
        for check in json.loads(result.stdout)["checks"]
        if check["status"] == "fail"
    }
    assert "resources.no_remote" in failures


def test_skill_assets_are_generic_and_match_clara_quality_gate() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in SKILL_ROOT.rglob("*")
        if path.is_file()
        and path.suffix in {".md", ".html", ".css", ".js", ".py", ".yaml"}
    )
    for forbidden in ("/Users/", "@gmail.com", "Private Client", "Client Surname"):
        assert forbidden not in text
    engine = (SKILL_ROOT / "assets" / "deck-engine" / "deck.css").read_text(
        encoding="utf-8"
    )
    shell = (SKILL_ROOT / "assets" / "deck-engine" / "shell.html").read_text(
        encoding="utf-8"
    )
    assert "box-shadow" not in engine
    assert "slideCounter" not in engine
    assert "slideCounter" not in shell

    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    for required in (
        "python scripts/check_dependencies.py",
        "deck-plan.json",
        "content-ledger.json",
        "build_layout_gallery.py",
        "compose_html_deck.py",
        "browser_qa_html_deck.py",
        "--warnings-as-errors",
        "inspect_html_deck.py",
        "validate_revision_map.py",
        "compare_html_deck_revision.py",
    ):
        assert required in skill
