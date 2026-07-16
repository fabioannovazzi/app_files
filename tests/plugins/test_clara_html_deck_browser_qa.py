from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = ROOT / "plugins" / "clara" / "skills" / "html-deck"
SCRIPT_PATH = SKILL_ROOT / "scripts" / "browser_qa_html_deck.py"


def load_browser_qa_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "clara_html_deck_browser_qa_test", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


qa = load_browser_qa_module()


class FakeScreenshotLocator:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def screenshot(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class FakeScreenshotPage:
    def __init__(self) -> None:
        self.locator_selectors: list[str] = []
        self.locator_result = FakeScreenshotLocator()
        self.page_screenshot_calls: list[dict[str, Any]] = []

    def locator(self, selector: str) -> FakeScreenshotLocator:
        self.locator_selectors.append(selector)
        return self.locator_result

    def screenshot(self, **kwargs: Any) -> None:
        self.page_screenshot_calls.append(kwargs)


def test_static_screenshot_captures_visible_slide_element(tmp_path: Path) -> None:
    page = FakeScreenshotPage()
    screenshot_path = tmp_path / "slide.png"

    scope = qa._capture_slide_screenshot(
        page,
        screenshot_path=screenshot_path,
        profile="static",
    )

    assert scope == "slide-element"
    assert page.locator_selectors == ["main > .slide:not([hidden])"]
    assert page.locator_result.calls == [{"path": str(screenshot_path)}]
    assert page.page_screenshot_calls == []


def test_stage_screenshot_captures_full_viewport(tmp_path: Path) -> None:
    page = FakeScreenshotPage()
    screenshot_path = tmp_path / "slide.png"

    scope = qa._capture_slide_screenshot(
        page,
        screenshot_path=screenshot_path,
        profile="stage",
    )

    assert scope == "full-viewport"
    assert page.locator_selectors == []
    assert page.page_screenshot_calls == [
        {"path": str(screenshot_path), "full_page": False}
    ]


def test_parse_viewport_accepts_named_dimensions() -> None:
    viewport = qa.parse_viewport("projector=1920x1080")

    assert viewport == qa.Viewport(name="projector", width=1920, height=1080)


@pytest.mark.parametrize(
    "value",
    ("projector", "projector=100x100", "1280-by-720", "1280x0"),
)
def test_parse_viewport_rejects_invalid_dimensions(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        qa.parse_viewport(value)


def test_assess_layout_metrics_reports_bounds_overflow_and_collision() -> None:
    metrics = {
        "stagePresent": True,
        "slidePresent": True,
        "stageWithinViewport": True,
        "stageRatio": 16 / 9,
        "slideWithinStage": True,
        "stageRect": {"width": 1280, "height": 720},
        "slideRect": {"width": 1280, "height": 720},
        "boundsViolations": [{"element": "p.copy"}],
        "containerOverflows": [{"element": "div[data-visual]"}],
        "collisions": [{"first": "h2[title]", "second": "div[data-visual]"}],
        "documentOverflow": {"horizontal": False, "vertical": False},
        "brokenAnchorTargets": [],
    }

    checks = qa.assess_layout_metrics(metrics)

    statuses = {check["code"]: check["status"] for check in checks}
    assert statuses["layout.stage_bounds"] == "pass"
    assert statuses["layout.element_bounds"] == "fail"
    assert statuses["layout.container_overflow"] == "fail"
    assert statuses["layout.declared_role_collisions"] == "fail"
    assert statuses["layout.document_overflow"] == "pass"


def test_static_layout_profile_requires_exact_1280x720_canvas() -> None:
    metrics = {
        "stagePresent": True,
        "slidePresent": True,
        "stageWithinViewport": True,
        "stageRatio": 16 / 9,
        "slideWithinStage": True,
        "stageRect": {"width": 1270, "height": 720},
        "slideRect": {"width": 1280, "height": 720},
        "boundsViolations": [],
        "containerOverflows": [],
        "collisions": [],
        "documentOverflow": {"horizontal": False, "vertical": False},
        "brokenAnchorTargets": [],
    }

    checks = qa.assess_layout_metrics(metrics, exact_canvas=True)

    statuses = {check["code"]: check["status"] for check in checks}
    assert statuses["layout.exact_1280x720"] == "fail"


def test_layout_assessment_enforces_declared_typography_budgets() -> None:
    metrics = {
        "stagePresent": True,
        "slidePresent": True,
        "stageWithinViewport": True,
        "stageRatio": 16 / 9,
        "slideWithinStage": True,
        "boundsViolations": [],
        "containerOverflows": [],
        "collisions": [],
        "typographyBudgetDeclared": True,
        "headlineLines": 4,
        "headlineBudget": 3,
        "bodyMinimum": 18,
        "bodySizeViolations": [{"element": "p.copy", "fontSize": 12, "required": 18}],
        "documentOverflow": {"horizontal": False, "vertical": False},
        "brokenAnchorTargets": [],
    }

    checks = qa.assess_layout_metrics(metrics)

    statuses = {check["code"]: check["status"] for check in checks}
    assert statuses["typography.headline_lines"] == "fail"
    assert statuses["typography.body_min_size"] == "fail"


def test_layout_assessment_rejects_svg_label_bounds_and_collisions() -> None:
    metrics = {
        "stagePresent": True,
        "slidePresent": True,
        "stageWithinViewport": True,
        "stageRatio": 16 / 9,
        "slideWithinStage": True,
        "boundsViolations": [],
        "containerOverflows": [],
        "collisions": [],
        "svgLabelBoundsViolations": [{"element": "text.data-axis-label"}],
        "svgLabelCollisions": [
            {"first": "text.data-axis-label", "second": "text.data-value-label"}
        ],
        "documentOverflow": {"horizontal": False, "vertical": False},
        "brokenAnchorTargets": [],
    }

    checks = qa.assess_layout_metrics(metrics)

    statuses = {check["code"]: check["status"] for check in checks}
    assert statuses["visual.svg_label_bounds"] == "fail"
    assert statuses["visual.svg_label_collisions"] == "fail"


def test_assess_interaction_results_preserves_explicit_skip() -> None:
    results = [
        {
            "code": "interaction.fragments",
            "status": "skip",
            "message": "This deck declares no fragments.",
        },
        {
            "code": "interaction.hash_navigation",
            "status": "pass",
            "message": "Every hash works.",
        },
    ]

    checks = qa.assess_interaction_results(results)

    assert checks[0]["status"] == "skip"
    assert checks[1]["status"] == "pass"


class FakeLaunchError(Exception):
    """Playwright-like launch failure used by the fallback tests."""


class FakeChromiumWithFallback:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.browser = object()

    def launch(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise FakeLaunchError("first browser failed")
        return self.browser


class FakePlaywrightWithFallback:
    def __init__(self) -> None:
        self.chromium = FakeChromiumWithFallback()


def test_launch_chromium_falls_back_after_explicit_browser_failure(
    tmp_path: Path,
) -> None:
    explicit_browser = tmp_path / "chrome"
    explicit_browser.write_text("stub", encoding="utf-8")
    explicit_browser.chmod(0o755)
    playwright = FakePlaywrightWithFallback()

    browser, launch_report = qa.launch_chromium_with_fallbacks(
        playwright,
        playwright_error=FakeLaunchError,
        explicit_path=str(explicit_browser),
    )

    assert browser is playwright.chromium.browser
    assert len(playwright.chromium.calls) == 2
    assert playwright.chromium.calls[0]["executable_path"] == str(explicit_browser)
    assert launch_report["status"] == "available"
    assert launch_report["attempts"][0]["status"] == "failed"
    assert launch_report["attempts"][-1]["status"] == "launched"


class AlwaysFailChromium:
    def launch(self, **_kwargs: Any) -> Any:
        raise FakeLaunchError("no browser binary")


class AlwaysFailPlaywright:
    def __init__(self) -> None:
        self.chromium = AlwaysFailChromium()


class FakePlaywrightContext:
    def __enter__(self) -> AlwaysFailPlaywright:
        return AlwaysFailPlaywright()

    def __exit__(self, *_args: Any) -> None:
        return None


def test_run_browser_qa_marks_browser_unavailability_as_blocked(
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "index.html"
    index_path.write_text("<!doctype html><title>Deck</title>", encoding="utf-8")

    report = qa.run_browser_qa(
        index_path,
        output_dir=tmp_path / "qa",
        viewports=[qa.Viewport("test", 1280, 720)],
        playwright_factory=FakePlaywrightContext,
        playwright_error=FakeLaunchError,
    )

    assert report["result"] == "blocked"
    assert report["browser"]["status"] == "blocked"
    assert report["summary"]["screenshot_count"] == 0
    assert report["checks"][0]["code"] == "browser.chromium_available"


def build_minimal_deck(tmp_path: Path) -> Path:
    work_dir = tmp_path / "work"
    environment = os.environ.copy()
    environment["PYTHONPYCACHEPREFIX"] = str(tmp_path / ".pycache")
    initialized = subprocess.run(
        [
            sys.executable,
            str(SKILL_ROOT / "scripts" / "init_html_deck.py"),
            "--work-dir",
            str(work_dir),
            "--title",
            "Browser QA fixture",
            "--subtitle",
            "Mechanical browser checks",
            "--author",
            "Clara",
            "--eyebrow",
            "Test deck",
            "--language",
            "en",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert initialized.returncode == 0, initialized.stderr
    (work_dir / "slides.html").write_text(
        """
        <section class="slide is-active" id="opening" data-slide-title="Opening"
          data-chapter="opening" data-chapter-label="Opening" aria-hidden="false">
          <div class="slide-frame">
            <h1 data-qa-role="title">Opening</h1>
            <p data-qa-role="body">A concise browser-QA fixture.</p>
            <div data-qa-role="data-visual" data-qa-allow-overlap="annotation"
              style="position:absolute;right:5%;bottom:5%;width:80px;height:80px"></div>
            <div data-qa-role="annotation"
              style="position:absolute;right:6%;bottom:6%;width:40px;height:40px"></div>
          </div>
          <aside class="speaker-notes">Open the fixture.</aside>
        </section>
        <section class="slide" id="decision" data-slide-title="Decision"
          data-chapter="decision" data-chapter-label="Decision" aria-hidden="true">
          <div class="slide-frame">
            <h2 data-qa-role="title">Decision</h2>
            <p data-qa-role="body" data-fragment="1">Choose the next move.</p>
          </div>
          <aside class="speaker-notes">Close on the decision.</aside>
        </section>
        """,
        encoding="utf-8",
    )
    (work_dir / "content-ledger.json").write_text(
        json.dumps(
            {
                "schema_version": "clara.html_deck_ledger.v1",
                "sources": [],
                "slides": [
                    {
                        "slide_id": "opening",
                        "basis_status": "not-applicable",
                        "basis_note": "Mechanical browser-QA fixture.",
                        "claims": [],
                    },
                    {
                        "slide_id": "decision",
                        "basis_status": "not-applicable",
                        "basis_note": "Mechanical browser-QA fixture.",
                        "claims": [],
                    },
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    output_root = tmp_path / "dist"
    built = subprocess.run(
        [
            sys.executable,
            str(SKILL_ROOT / "scripts" / "build_html_deck.py"),
            str(work_dir),
            "--output-root",
            str(output_root),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert built.returncode == 0, built.stderr or built.stdout
    publication_id = json.loads(built.stdout)["output"]["publication_id"]
    return output_root / publication_id / "index.html"


def test_browser_qa_integration_when_chromium_is_available(tmp_path: Path) -> None:
    index_path = build_minimal_deck(tmp_path)

    report = qa.run_browser_qa(
        index_path,
        output_dir=tmp_path / "browser-qa",
        viewports=[qa.Viewport("integration", 1280, 720)],
    )

    if report["result"] == "blocked":
        pytest.skip("No runnable Chrome or Playwright Chromium is available.")
    assert report["result"] == "pass", json.dumps(report, indent=2)
    assert report["summary"]["screenshot_count"] == 2
    assert (tmp_path / "browser-qa" / "screenshots" / "index.html").is_file()
    assert (tmp_path / "browser-qa" / "print-preview.pdf").is_file()


def test_static_browser_qa_profile_renders_linked_deck_without_clara_hud(
    tmp_path: Path,
) -> None:
    (tmp_path / "styles.css").write_text(
        "html,body{margin:0;overflow:hidden}.deck,.slide{width:1280px;height:720px}"
        ".deck{position:relative}.slide{position:absolute;inset:0;overflow:hidden;display:none}"
        ".slide.is-active{display:block}.slide[hidden]{display:none}"
        "h1{position:absolute;left:60px;top:60px}",
        encoding="utf-8",
    )
    (tmp_path / "deck.js").write_text(
        "(()=>{const s=[...document.querySelectorAll('.slide')];"
        "const show=(i)=>s.forEach((x,n)=>{x.hidden=n!==i;"
        "x.classList.toggle('is-active',n===i)});"
        "addEventListener('keydown',(e)=>{if(e.key==='Home')show(0);"
        "if(e.key==='End')show(s.length-1);if(e.key==='ArrowRight')show(1);"
        "if(e.key==='ArrowLeft')show(0)});show(0)})();",
        encoding="utf-8",
    )
    index = tmp_path / "index.html"
    index.write_text(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>Static</title><link rel='stylesheet' href='styles.css'>"
        "<script src='deck.js' defer></script></head><body><main class='deck'>"
        "<section class='slide'><h1>One</h1></section>"
        "<section class='slide' hidden><h1>Two</h1></section>"
        "</main></body></html>",
        encoding="utf-8",
    )

    report = qa.run_browser_qa(
        index,
        output_dir=tmp_path / "static-qa",
        viewports=[qa.Viewport("benchmark", 1280, 720)],
        profile="static",
    )

    if report["result"] == "blocked":
        pytest.skip("No runnable Chrome or Playwright Chromium is available.")
    assert report["result"] == "pass", json.dumps(report, indent=2)
    assert report["profile"] == "static"
    assert report["summary"]["screenshot_count"] == 2
    assert report["print"]["status"] == "skip"


def test_fixed_stage_cannot_retain_anchor_scroll_when_chromium_is_available(
    tmp_path: Path,
) -> None:
    playwright_sync = pytest.importorskip("playwright.sync_api")
    index_path = build_minimal_deck(tmp_path)

    with playwright_sync.sync_playwright() as playwright:
        browser, launch_report = qa.launch_chromium_with_fallbacks(
            playwright,
            playwright_error=playwright_sync.Error,
        )
        if browser is None:
            pytest.skip(json.dumps(launch_report, indent=2))
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            reduced_motion="reduce",
            device_scale_factor=1,
        )
        try:
            page = context.new_page()
            page.goto(index_path.resolve().as_uri(), wait_until="load")
            page.locator(".deck-stage").wait_for(state="visible")

            geometry = page.evaluate("""() => {
                  const stage = document.querySelector('.deck-stage');
                  const slide = document.querySelector('.slide.is-active');
                  stage.scrollTop = 8;
                  const stageRect = stage.getBoundingClientRect();
                  const slideRect = slide.getBoundingClientRect();
                  return {
                    scrollTop: stage.scrollTop,
                    topDelta: slideRect.top - stageRect.top,
                  };
                }""")
        finally:
            context.close()
            browser.close()

    assert geometry == {"scrollTop": 0, "topDelta": 0}
