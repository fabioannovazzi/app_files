#!/usr/bin/env python3
"""Run mechanical browser QA for a standalone Clara HTML stage deck.

The checks in this module are deterministic because they cover browser-observable
contracts: geometry, overflow, declared collision roles, navigation state,
console output, reduced-motion CSS, and print rendering. Editorial quality and
source fidelity remain explicit manual-review items in the JSON report.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

__all__ = [
    "BrowserCandidate",
    "Viewport",
    "assess_interaction_results",
    "assess_layout_metrics",
    "browser_launch_candidates",
    "launch_chromium_with_fallbacks",
    "main",
    "parse_viewport",
    "run_browser_qa",
]

SCHEMA_VERSION = "clara.html_deck_browser_qa.v1"
QA_PROFILES = {"stage", "static"}
DEFAULT_VIEWPORTS = (
    "presentation=1280x720",
    "full-hd=1920x1080",
    "compact=1024x768",
    "mobile=390x844",
)
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)
VIEWPORT_RE = re.compile(
    r"^(?:(?P<name>[a-zA-Z0-9][a-zA-Z0-9_-]*)=)?"
    r"(?P<width>[0-9]{2,5})x(?P<height>[0-9]{2,5})$"
)


@dataclass(frozen=True)
class Viewport:
    """One named browser viewport."""

    name: str
    width: int
    height: int


@dataclass(frozen=True)
class BrowserCandidate:
    """One Chromium launch option."""

    label: str
    executable_path: str | None


def parse_viewport(value: str) -> Viewport:
    """Parse ``name=WIDTHxHEIGHT`` or ``WIDTHxHEIGHT`` into a viewport."""

    match = VIEWPORT_RE.fullmatch(value.strip())
    if match is None:
        raise argparse.ArgumentTypeError(
            "Viewport must be WIDTHxHEIGHT or name=WIDTHxHEIGHT."
        )
    width = int(match.group("width"))
    height = int(match.group("height"))
    if not 240 <= width <= 8192 or not 135 <= height <= 8192:
        raise argparse.ArgumentTypeError(
            "Viewport width must be 240-8192 and height must be 135-8192."
        )
    return Viewport(
        name=match.group("name") or f"{width}x{height}",
        width=width,
        height=height,
    )


def _resolve_executable(value: str) -> str:
    expanded = Path(value).expanduser()
    if expanded.is_absolute() or expanded.parent != Path("."):
        return str(expanded.resolve())
    resolved = shutil.which(value)
    return resolved or value


def browser_launch_candidates(
    explicit_path: str | None = None,
) -> list[BrowserCandidate]:
    """Return ordered system-Chrome and bundled-Playwright launch candidates."""

    raw_candidates: list[tuple[str, str | None]] = []
    if explicit_path:
        raw_candidates.append(("explicit", _resolve_executable(explicit_path)))
    environment_path = os.environ.get("CLARA_HTML_DECK_BROWSER")
    if environment_path:
        raw_candidates.append(("environment", _resolve_executable(environment_path)))
    for command in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
    ):
        resolved = shutil.which(command)
        if resolved:
            raw_candidates.append((f"system:{command}", resolved))
    raw_candidates.extend(("system:path", path) for path in CHROME_CANDIDATES)
    raw_candidates.append(("playwright:bundled", None))

    candidates: list[BrowserCandidate] = []
    seen: set[str] = set()
    for label, executable in raw_candidates:
        key = executable or "<bundled>"
        if key in seen:
            continue
        seen.add(key)
        candidates.append(BrowserCandidate(label=label, executable_path=executable))
    return candidates


def launch_chromium_with_fallbacks(
    playwright: Any,
    *,
    playwright_error: type[BaseException],
    explicit_path: str | None = None,
) -> tuple[Any | None, dict[str, Any]]:
    """Launch Chromium with local Chrome and bundled-browser fallbacks."""

    attempts: list[dict[str, str]] = []
    for candidate in browser_launch_candidates(explicit_path):
        executable = candidate.executable_path
        if executable is not None:
            path = Path(executable)
            if not path.is_file() or not os.access(path, os.X_OK):
                attempts.append(
                    {
                        "candidate": candidate.label,
                        "executable": executable,
                        "status": "unavailable",
                        "message": "Executable does not exist or is not runnable.",
                    }
                )
                continue
        launch_args: dict[str, Any] = {
            "headless": True,
            "args": ["--disable-gpu", "--hide-scrollbars"],
        }
        if executable is not None:
            launch_args["executable_path"] = executable
        try:
            browser = playwright.chromium.launch(**launch_args)
        except (playwright_error, OSError) as exc:
            attempts.append(
                {
                    "candidate": candidate.label,
                    "executable": executable or "",
                    "status": "failed",
                    "message": str(exc),
                }
            )
            continue
        attempts.append(
            {
                "candidate": candidate.label,
                "executable": executable or "",
                "status": "launched",
                "message": "Chromium launched successfully.",
            }
        )
        return browser, {
            "status": "available",
            "engine": "chromium",
            "candidate": candidate.label,
            "executable": executable,
            "attempts": attempts,
        }
    return None, {
        "status": "blocked",
        "engine": "chromium",
        "candidate": None,
        "executable": None,
        "attempts": attempts,
    }


def _check(
    code: str,
    status: str,
    message: str,
    *,
    details: Any | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "code": code,
        "status": status,
        "message": message,
    }
    if details not in (None, [], {}):
        result["details"] = details
    return result


def assess_layout_metrics(
    metrics: dict[str, Any],
    *,
    include_document_checks: bool = True,
    exact_canvas: bool = False,
) -> list[dict[str, Any]]:
    """Turn browser geometry evidence into deterministic pass/fail checks."""

    checks: list[dict[str, Any]] = []
    checks.append(
        _check(
            "layout.stage_present",
            "pass" if metrics.get("stagePresent") else "fail",
            (
                "The fixed presentation stage is present."
                if metrics.get("stagePresent")
                else "The .deck-stage element is missing."
            ),
        )
    )
    checks.append(
        _check(
            "layout.slide_present",
            "pass" if metrics.get("slidePresent") else "fail",
            (
                "The target slide is present."
                if metrics.get("slidePresent")
                else "The target slide is missing."
            ),
        )
    )
    if not metrics.get("stagePresent") or not metrics.get("slidePresent"):
        return checks

    stage_within = bool(metrics.get("stageWithinViewport"))
    checks.append(
        _check(
            "layout.stage_bounds",
            "pass" if stage_within else "fail",
            (
                "The 16:9 stage is fully inside the viewport."
                if stage_within
                else "The presentation stage extends outside the viewport."
            ),
            details=metrics.get("stageRect"),
        )
    )
    ratio = float(metrics.get("stageRatio") or 0)
    ratio_ok = abs(ratio - (16 / 9)) <= 0.01
    checks.append(
        _check(
            "layout.stage_ratio",
            "pass" if ratio_ok else "fail",
            (
                "The rendered stage preserves a 16:9 ratio."
                if ratio_ok
                else f"The rendered stage ratio is {ratio:.4f}, not 16:9."
            ),
            details={"rendered_ratio": ratio, "expected_ratio": 16 / 9},
        )
    )
    slide_within = bool(metrics.get("slideWithinStage"))
    checks.append(
        _check(
            "layout.slide_bounds",
            "pass" if slide_within else "fail",
            (
                "The active slide fits the stage."
                if slide_within
                else "The active slide extends outside the stage."
            ),
            details=metrics.get("slideRect"),
        )
    )
    if exact_canvas:
        stage_rect = metrics.get("stageRect") or {}
        slide_rect = metrics.get("slideRect") or {}
        exact = all(
            abs(float(rect.get(key) or 0) - expected) <= 1
            for rect in (stage_rect, slide_rect)
            for key, expected in (("width", 1280), ("height", 720))
        )
        checks.append(
            _check(
                "layout.exact_1280x720",
                "pass" if exact else "fail",
                (
                    "The deck and slide render at exactly 1280x720 pixels."
                    if exact
                    else "The static deck or slide is not exactly 1280x720 pixels."
                ),
                details={"stage": stage_rect, "slide": slide_rect},
            )
        )

    bounds = list(metrics.get("boundsViolations") or [])
    checks.append(
        _check(
            "layout.element_bounds",
            "pass" if not bounds else "fail",
            (
                "Visible slide elements remain inside the stage."
                if not bounds
                else f"Found {len(bounds)} visible element(s) outside the stage."
            ),
            details=bounds,
        )
    )
    overflows = list(metrics.get("containerOverflows") or [])
    checks.append(
        _check(
            "layout.container_overflow",
            "pass" if not overflows else "fail",
            (
                "The slide and declared QA containers have no scroll overflow."
                if not overflows
                else f"Found {len(overflows)} overflowing container(s)."
            ),
            details=overflows,
        )
    )
    collisions = list(metrics.get("collisions") or [])
    checks.append(
        _check(
            "layout.declared_role_collisions",
            "pass" if not collisions else "fail",
            (
                "Declared QA roles do not collide."
                if not collisions
                else f"Found {len(collisions)} undeclared role collision(s)."
            ),
            details=collisions,
        )
    )
    svg_label_bounds = list(metrics.get("svgLabelBoundsViolations") or [])
    checks.append(
        _check(
            "visual.svg_label_bounds",
            "pass" if not svg_label_bounds else "fail",
            (
                "Data-visual labels remain inside their SVG canvas."
                if not svg_label_bounds
                else f"Found {len(svg_label_bounds)} data-visual label(s) outside the SVG canvas."
            ),
            details=svg_label_bounds,
        )
    )
    svg_label_collisions = list(metrics.get("svgLabelCollisions") or [])
    checks.append(
        _check(
            "visual.svg_label_collisions",
            "pass" if not svg_label_collisions else "fail",
            (
                "Data-visual labels do not overlap one another."
                if not svg_label_collisions
                else f"Found {len(svg_label_collisions)} overlapping data-visual label pair(s)."
            ),
            details=svg_label_collisions,
        )
    )
    if metrics.get("typographyBudgetDeclared"):
        headline_lines = int(metrics.get("headlineLines") or 0)
        headline_budget = int(metrics.get("headlineBudget") or 0)
        headline_ok = 0 < headline_lines <= headline_budget
        checks.append(
            _check(
                "typography.headline_lines",
                "pass" if headline_ok else "fail",
                (
                    "The headline stays within its declared line budget."
                    if headline_ok
                    else f"The headline uses {headline_lines} lines; the budget is {headline_budget}."
                ),
                details={"lines": headline_lines, "maximum": headline_budget},
            )
        )
        body_violations = list(metrics.get("bodySizeViolations") or [])
        checks.append(
            _check(
                "typography.body_min_size",
                "pass" if not body_violations else "fail",
                (
                    "Registered body copy meets its declared minimum size."
                    if not body_violations
                    else f"Found {len(body_violations)} body element(s) below the declared minimum."
                ),
                details=body_violations,
            )
        )
    if include_document_checks:
        overflow = metrics.get("documentOverflow") or {}
        has_document_overflow = bool(overflow.get("horizontal")) or bool(
            overflow.get("vertical")
        )
        checks.append(
            _check(
                "layout.document_overflow",
                "pass" if not has_document_overflow else "fail",
                (
                    "The deck document does not scroll outside its viewport."
                    if not has_document_overflow
                    else "The deck document has horizontal or vertical scroll overflow."
                ),
                details=overflow,
            )
        )
        broken_hashes = list(metrics.get("brokenAnchorTargets") or [])
        checks.append(
            _check(
                "navigation.anchor_targets",
                "pass" if not broken_hashes else "fail",
                (
                    "Every authored hash link resolves to an element."
                    if not broken_hashes
                    else f"Found {len(broken_hashes)} broken authored hash link(s)."
                ),
                details=broken_hashes,
            )
        )
    return checks


def assess_interaction_results(results: Any) -> list[dict[str, Any]]:
    """Normalize browser interaction results without hiding skipped checks."""

    if not isinstance(results, list):
        return [
            _check(
                "interaction.result_shape",
                "fail",
                "The browser returned an invalid interaction result.",
            )
        ]
    checks: list[dict[str, Any]] = []
    for position, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            checks.append(
                _check(
                    f"interaction.result_{position}",
                    "fail",
                    "The browser returned a non-object interaction result.",
                )
            )
            continue
        status = str(item.get("status") or "fail")
        if status not in {"pass", "fail", "skip"}:
            status = "fail"
        code = str(item.get("code") or f"interaction.result_{position}")
        message = str(item.get("message") or "No interaction message was returned.")
        checks.append(_check(code, status, message, details=item.get("details")))
    return checks


LAYOUT_METRICS_JS = r"""
({ slideId, slideIndex, profile }) => {
  const tolerance = 2;
  const stage = profile === 'static'
    ? document.querySelector('main.deck, main.clara-fixed-16-9-deck, main')
    : document.querySelector('.deck-stage');
  const slides = stage ? Array.from(stage.querySelectorAll(':scope > .slide')) : [];
  const slide = profile === 'static' ? slides[slideIndex] : document.getElementById(slideId);
  const rectData = (rect) => ({
    left: Math.round(rect.left * 100) / 100,
    top: Math.round(rect.top * 100) / 100,
    right: Math.round(rect.right * 100) / 100,
    bottom: Math.round(rect.bottom * 100) / 100,
    width: Math.round(rect.width * 100) / 100,
    height: Math.round(rect.height * 100) / 100,
  });
  const visible = (element) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' &&
      Number.parseFloat(style.opacity || '1') > 0.001 &&
      rect.width > 0.5 && rect.height > 0.5;
  };
  const label = (element) => {
    const role = element.dataset.qaRole || '';
    const id = element.id ? `#${element.id}` : '';
    const className = typeof element.className === 'string'
      ? element.className.trim().split(/\s+/).slice(0, 3).join('.')
      : '';
    return [element.tagName.toLowerCase(), id, role ? `[${role}]` : '', className ? `.${className}` : ''].join('');
  };
  if (!stage || !slide) {
    return { stagePresent: !!stage, slidePresent: !!slide };
  }
  const stageRect = stage.getBoundingClientRect();
  const slideRect = slide.getBoundingClientRect();
  const inRect = (inner, outer) => inner.left >= outer.left - tolerance &&
    inner.top >= outer.top - tolerance && inner.right <= outer.right + tolerance &&
    inner.bottom <= outer.bottom + tolerance;
  const stageWithinViewport = stageRect.left >= -tolerance && stageRect.top >= -tolerance &&
    stageRect.right <= innerWidth + tolerance && stageRect.bottom <= innerHeight + tolerance;

  const boundsViolations = Array.from(slide.querySelectorAll('*')).flatMap((element) => {
    if (!visible(element)) return [];
    if (element.closest('.speaker-notes')) return [];
    if (element.closest('[data-qa-allow-overflow]')) return [];
    if (element.closest('svg') && element.tagName.toLowerCase() !== 'svg') return [];
    const rect = element.getBoundingClientRect();
    if (inRect(rect, stageRect)) return [];
    return [{ element: label(element), rect: rectData(rect) }];
  }).slice(0, 40);

  const overflowCandidates = [
    slide,
    slide.querySelector('.slide-frame'),
    ...slide.querySelectorAll('[data-qa-scroll-check]'),
    ...(profile === 'static' ? Array.from(slide.querySelectorAll('*')).filter((element) => {
      const overflow = `${getComputedStyle(element).overflow} ${getComputedStyle(element).overflowX} ${getComputedStyle(element).overflowY}`;
      return /(hidden|auto|scroll|clip)/.test(overflow);
    }) : []),
  ].filter((element, index, items) => element && items.indexOf(element) === index);
  const containerOverflows = overflowCandidates.flatMap((element) => {
    if (!visible(element) || element.closest('[data-qa-allow-overflow]')) return [];
    const horizontal = element.scrollWidth > element.clientWidth + tolerance;
    const vertical = element.scrollHeight > element.clientHeight + tolerance;
    if (!horizontal && !vertical) return [];
    return [{
      element: label(element), horizontal, vertical,
      scrollWidth: element.scrollWidth, clientWidth: element.clientWidth,
      scrollHeight: element.scrollHeight, clientHeight: element.clientHeight,
    }];
  }).slice(0, 40);

  const roleNodes = (profile === 'static'
    ? Array.from(slide.querySelectorAll('*')).filter((element) => {
        const style = getComputedStyle(element);
        return element.dataset.qaRole || ['absolute', 'fixed'].includes(style.position);
      })
    : Array.from(slide.querySelectorAll('[data-qa-role]'))).filter(visible);
  const allowed = (element, other) => {
    const tokens = String(element.dataset.qaAllowOverlap || '').split(/[\s,]+/).filter(Boolean);
    return tokens.includes('*') || tokens.includes(other.dataset.qaRole || '') ||
      (other.id && (tokens.includes(other.id) || tokens.includes(`#${other.id}`)));
  };
  const collisions = [];
  for (let firstIndex = 0; firstIndex < roleNodes.length; firstIndex += 1) {
    for (let secondIndex = firstIndex + 1; secondIndex < roleNodes.length; secondIndex += 1) {
      const first = roleNodes[firstIndex];
      const second = roleNodes[secondIndex];
      if (first.contains(second) || second.contains(first)) continue;
      if (allowed(first, second) || allowed(second, first)) continue;
      const firstRect = first.getBoundingClientRect();
      const secondRect = second.getBoundingClientRect();
      const width = Math.min(firstRect.right, secondRect.right) - Math.max(firstRect.left, secondRect.left);
      const height = Math.min(firstRect.bottom, secondRect.bottom) - Math.max(firstRect.top, secondRect.top);
      if (width <= tolerance || height <= tolerance || width * height <= 9) continue;
      collisions.push({
        first: label(first), second: label(second),
        overlap: { width: Math.round(width * 100) / 100, height: Math.round(height * 100) / 100 },
      });
      if (collisions.length >= 40) break;
    }
    if (collisions.length >= 40) break;
  }

  const svgLabelNodes = Array.from(slide.querySelectorAll('.data-visual svg text')).filter(visible);
  const svgLabelBoundsViolations = svgLabelNodes.flatMap((element) => {
    const svg = element.closest('svg');
    if (!svg) return [];
    const rect = element.getBoundingClientRect();
    const svgRect = svg.getBoundingClientRect();
    return inRect(rect, svgRect) ? [] : [{ element: label(element), rect: rectData(rect), svg: rectData(svgRect) }];
  }).slice(0, 40);
  const svgLabelCollisions = [];
  for (let firstIndex = 0; firstIndex < svgLabelNodes.length; firstIndex += 1) {
    for (let secondIndex = firstIndex + 1; secondIndex < svgLabelNodes.length; secondIndex += 1) {
      const first = svgLabelNodes[firstIndex];
      const second = svgLabelNodes[secondIndex];
      const firstRect = first.getBoundingClientRect();
      const secondRect = second.getBoundingClientRect();
      const width = Math.min(firstRect.right, secondRect.right) - Math.max(firstRect.left, secondRect.left);
      const height = Math.min(firstRect.bottom, secondRect.bottom) - Math.max(firstRect.top, secondRect.top);
      if (width <= 1 || height <= 1 || width * height <= 4) continue;
      svgLabelCollisions.push({
        first: label(first), second: label(second),
        overlap: { width: Math.round(width * 100) / 100, height: Math.round(height * 100) / 100 },
      });
      if (svgLabelCollisions.length >= 40) break;
    }
    if (svgLabelCollisions.length >= 40) break;
  }

  const documentElement = document.documentElement;
  const body = document.body;
  const documentOverflow = {
    horizontal: Math.max(documentElement.scrollWidth, body.scrollWidth) > innerWidth + tolerance,
    vertical: Math.max(documentElement.scrollHeight, body.scrollHeight) > innerHeight + tolerance,
    scrollWidth: Math.max(documentElement.scrollWidth, body.scrollWidth),
    scrollHeight: Math.max(documentElement.scrollHeight, body.scrollHeight),
    viewportWidth: innerWidth,
    viewportHeight: innerHeight,
  };
  const headlineBudget = Number.parseInt(slide.dataset.qaHeadlineMaxLines || '0', 10);
  const bodyMinimum = Number.parseFloat(slide.dataset.qaBodyMinPx || '0');
  const headline = slide.querySelector('[data-qa-role="title"]');
  const textLineCount = (element) => {
    if (!element || !element.textContent?.trim()) return 0;
    const range = document.createRange();
    range.selectNodeContents(element);
    const tops = [];
    for (const rect of range.getClientRects()) {
      if (rect.width <= .5 || rect.height <= .5) continue;
      if (!tops.some((top) => Math.abs(top - rect.top) <= .75)) tops.push(rect.top);
    }
    return tops.length;
  };
  const headlineLines = textLineCount(headline);
  const bodyNodes = Array.from(slide.querySelectorAll(
    '.clara-layout p:not(.source-note):not(.data-source-note), .clara-layout [data-qa-body]'
  )).filter((element, index, items) => visible(element) && items.indexOf(element) === index);
  const bodySizeViolations = bodyNodes.flatMap((element) => {
    const fontSize = Number.parseFloat(getComputedStyle(element).fontSize || '0');
    const fontSize1280Equivalent = stageRect.width > 0 ? fontSize * 1280 / stageRect.width : 0;
    return bodyMinimum > 0 && fontSize1280Equivalent + .05 < bodyMinimum
      ? [{ element: label(element), fontSize, fontSize1280Equivalent, required1280Equivalent: bodyMinimum }]
      : [];
  });
  const brokenAnchorTargets = Array.from(document.querySelectorAll('a[href^="#"]')).flatMap((anchor) => {
    const value = anchor.getAttribute('href') || '';
    if (!value || value === '#') return [];
    let id = '';
    try { id = decodeURIComponent(value.slice(1)); } catch (_error) { return [value]; }
    return document.getElementById(id) ? [] : [value];
  });
  return {
    stagePresent: true,
    slidePresent: true,
    stageRect: rectData(stageRect),
    slideRect: rectData(slideRect),
    stageRatio: stageRect.height ? stageRect.width / stageRect.height : 0,
    stageWithinViewport,
    slideWithinStage: inRect(slideRect, stageRect),
    boundsViolations,
    containerOverflows,
    collisions,
    svgLabelBoundsViolations,
    svgLabelCollisions,
    documentOverflow,
    typographyBudgetDeclared: headlineBudget > 0 && bodyMinimum > 0,
    headlineBudget,
    headlineLines,
    bodyMinimum,
    bodySizeViolations,
    brokenAnchorTargets,
  };
}
"""


INTERACTION_JS = r"""
async () => {
  const checks = [];
  const add = (code, status, message, details) => checks.push({ code, status, message, details });
  const slides = Array.from(document.querySelectorAll('.deck-stage > .slide'));
  const active = () => slides.find((slide) => slide.classList.contains('is-active'));
  const pause = () => new Promise((resolve) => setTimeout(resolve, 24));
  const key = async (value) => {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: value, bubbles: true, cancelable: true }));
    await pause();
  };
  const showByDot = async (index) => {
    document.querySelectorAll('#deckDots button')[index]?.click();
    await pause();
  };
  if (!slides.length) {
    add('interaction.slides', 'fail', 'No slides are available for interaction QA.');
    return checks;
  }

  const requiredControls = ['prevBtn', 'nextBtn', 'overviewBtn', 'helpBtn', 'fullscreenBtn'];
  const missingControls = requiredControls.filter((id) => !document.getElementById(id));
  add('interaction.controls_present', missingControls.length ? 'fail' : 'pass',
    missingControls.length ? `Missing controls: ${missingControls.join(', ')}` : 'Required presentation controls are present.',
    missingControls);

  await key('Home');
  const homePass = active()?.id === slides[0].id;
  await key('End');
  const endPass = active()?.id === slides.at(-1).id;
  add('interaction.keyboard_home_end', homePass && endPass ? 'pass' : 'fail',
    homePass && endPass ? 'Home and End select the first and last slide.' : 'Home or End did not select the expected slide.',
    { afterHome: homePass, afterEnd: endPass });

  if (slides.length > 1) {
    active()?.querySelectorAll('[data-fragment]').forEach((fragment) => fragment.classList.remove('is-shown'));
    await key('ArrowLeft');
    const leftPass = active()?.id === slides.at(-2).id;
    await key('Home');
    slides[0].querySelectorAll('[data-fragment]').forEach((fragment) => fragment.classList.add('is-shown'));
    await key(' ');
    const spacePass = active()?.id === slides[1].id;
    add('interaction.keyboard_navigation', leftPass && spacePass ? 'pass' : 'fail',
      leftPass && spacePass ? 'ArrowLeft and Space navigate between slides.' : 'ArrowLeft or Space did not navigate as expected.',
      { arrowLeft: leftPass, space: spacePass });

    await key('Home');
    slides[0].querySelectorAll('[data-fragment]').forEach((fragment) => fragment.classList.add('is-shown'));
    document.getElementById('nextBtn')?.click();
    await pause();
    const nextPass = active()?.id === slides[1].id;
    document.getElementById('prevBtn')?.click();
    await pause();
    const previousPass = active()?.id === slides[0].id;
    add('interaction.previous_next_buttons', nextPass && previousPass ? 'pass' : 'fail',
      nextPass && previousPass ? 'Previous and next buttons navigate between slides.' : 'Previous or next button navigation failed.',
      { next: nextPass, previous: previousPass });
  } else {
    add('interaction.keyboard_navigation', 'skip', 'Slide navigation requires at least two slides.');
    add('interaction.previous_next_buttons', 'skip', 'Previous/next navigation requires at least two slides.');
  }

  const fragmentIndex = slides.findIndex((slide) => slide.querySelector('[data-fragment]'));
  if (fragmentIndex >= 0) {
    await showByDot(fragmentIndex);
    const fragmentSlide = slides[fragmentIndex];
    const fragments = Array.from(fragmentSlide.querySelectorAll('[data-fragment]'));
    fragments.forEach((fragment) => fragment.classList.remove('is-shown'));
    const steps = fragments.map((fragment, index) => {
      const parsed = Number.parseInt(fragment.dataset.fragment || '', 10);
      return Number.isFinite(parsed) && parsed > 0 ? parsed : index + 1;
    });
    const firstStep = Math.min(...steps);
    document.getElementById('nextBtn')?.click();
    await pause();
    const revealPass = fragments.every((fragment, index) =>
      fragment.classList.contains('is-shown') === (steps[index] === firstStep));
    const stayedOnSlide = active()?.id === fragmentSlide.id;
    document.getElementById('prevBtn')?.click();
    await pause();
    const retreatPass = fragments.every((fragment) => !fragment.classList.contains('is-shown'));
    add('interaction.fragments', revealPass && stayedOnSlide && retreatPass ? 'pass' : 'fail',
      revealPass && stayedOnSlide && retreatPass
        ? 'Fragment groups reveal and retreat before slide navigation.'
        : 'Fragment reveal or retreat behavior is inconsistent.',
      { reveal: revealPass, stayedOnSlide, retreat: retreatPass });
  } else {
    add('interaction.fragments', 'skip', 'This deck declares no fragments.');
  }

  await key('o');
  const overview = document.getElementById('overviewOverlay');
  const overviewOpen = overview?.hidden === false;
  const overviewCount = document.querySelectorAll('#overviewGrid .overview-card').length;
  await key('Escape');
  const overviewClosed = overview?.hidden === true;
  add('interaction.overview_escape', overviewOpen && overviewClosed && overviewCount === slides.length ? 'pass' : 'fail',
    overviewOpen && overviewClosed && overviewCount === slides.length
      ? 'Overview contains every slide and Escape closes it.'
      : 'Overview open/count/Escape behavior failed.',
    { open: overviewOpen, closed: overviewClosed, cardCount: overviewCount, slideCount: slides.length });

  document.getElementById('overviewBtn')?.click();
  await pause();
  const overviewButtonPass = overview?.hidden === false;
  document.querySelector('#overviewGrid .overview-card')?.click();
  await pause();
  const overviewSelectionPass = overview?.hidden === true && active()?.id === slides[0].id;
  add('interaction.overview_button', overviewButtonPass && overviewSelectionPass ? 'pass' : 'fail',
    overviewButtonPass && overviewSelectionPass
      ? 'The overview button opens the map and a card selects its slide.'
      : 'The overview button or card selection failed.',
    { opened: overviewButtonPass, selected: overviewSelectionPass });

  await key('n');
  const notesPanel = document.getElementById('notesPanel');
  const sourceNotes = active()?.querySelector('.speaker-notes')?.textContent?.trim() || '';
  const displayedNotes = notesPanel?.querySelector('p')?.textContent?.trim() || '';
  const notesOpen = document.body.classList.contains('show-notes');
  await key('Escape');
  const notesClosed = !document.body.classList.contains('show-notes');
  add('interaction.notes_escape', notesOpen && notesClosed && !!sourceNotes && displayedNotes === sourceNotes ? 'pass' : 'fail',
    notesOpen && notesClosed && !!sourceNotes && displayedNotes === sourceNotes
      ? 'Speaker notes open with the active slide text and Escape closes them.'
      : 'Speaker-note display or Escape behavior failed.',
    { open: notesOpen, closed: notesClosed, hasSourceNotes: !!sourceNotes, textMatches: displayedNotes === sourceNotes });

  document.getElementById('helpBtn')?.click();
  await pause();
  const help = document.getElementById('helpOverlay');
  const helpOpen = help?.hidden === false;
  await key('Escape');
  const helpClosed = help?.hidden === true;
  add('interaction.help_escape', helpOpen && helpClosed ? 'pass' : 'fail',
    helpOpen && helpClosed ? 'The help button opens its overlay and Escape closes it.' : 'Help overlay or Escape behavior failed.',
    { open: helpOpen, closed: helpClosed });

  const hashResults = [];
  for (const slide of slides) {
    location.hash = `#${encodeURIComponent(slide.id)}`;
    await pause();
    let decodedHash = '';
    try { decodedHash = decodeURIComponent(location.hash.slice(1)); } catch (_error) { decodedHash = location.hash.slice(1); }
    hashResults.push({ id: slide.id, active: active()?.id, hash: decodedHash });
  }
  const hashesPass = hashResults.every((item) => item.active === item.id && item.hash === item.id);
  add('interaction.hash_navigation', hashesPass ? 'pass' : 'fail',
    hashesPass ? 'Every slide hash activates the matching slide.' : 'One or more slide hashes did not activate the matching slide.',
    hashResults.filter((item) => item.active !== item.id || item.hash !== item.id));
  await key('Home');
  return checks;
}
"""

STATIC_INTERACTION_JS = r"""
async () => {
  const checks = [];
  const add = (code, status, message, details) => checks.push({ code, status, message, details });
  const slides = Array.from(document.querySelectorAll('main > .slide'));
  const visibleIndex = () => slides.findIndex((slide) => {
    const style = getComputedStyle(slide);
    return !slide.hidden && style.display !== 'none' && style.visibility !== 'hidden';
  });
  const pause = () => new Promise((resolve) => setTimeout(resolve, 35));
  const key = async (value) => {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: value, bubbles: true, cancelable: true }));
    await pause();
  };
  if (!slides.length) {
    add('interaction.slides', 'fail', 'No static slides are available.');
    return checks;
  }
  await key('Home');
  const homePass = visibleIndex() === 0;
  await key('End');
  const endPass = visibleIndex() === slides.length - 1;
  add('interaction.static_home_end', homePass && endPass ? 'pass' : 'fail',
    homePass && endPass ? 'Home and End select the first and last slide.' : 'Home or End navigation failed.',
    { homePass, endPass });
  if (slides.length > 1) {
    await key('ArrowLeft');
    const leftPass = visibleIndex() === slides.length - 2;
    await key('Home');
    await key('ArrowRight');
    const rightPass = visibleIndex() === 1;
    add('interaction.static_arrows', leftPass && rightPass ? 'pass' : 'fail',
      leftPass && rightPass ? 'Arrow keys navigate the static deck.' : 'Arrow-key navigation failed.',
      { leftPass, rightPass });
  } else {
    add('interaction.static_arrows', 'skip', 'Arrow navigation requires two slides.');
  }
  return checks;
}
"""


REDUCED_MOTION_JS = r"""
() => {
  const parseTimes = (value) => String(value || '').split(',').map((item) => {
    const token = item.trim();
    if (token.endsWith('ms')) return Number.parseFloat(token) / 1000;
    if (token.endsWith('s')) return Number.parseFloat(token);
    return 0;
  }).filter(Number.isFinite);
  const violations = Array.from(document.querySelectorAll('body *')).flatMap((element) => {
    const style = getComputedStyle(element);
    const maximum = Math.max(0, ...parseTimes(style.transitionDuration), ...parseTimes(style.animationDuration));
    if (maximum <= 0.01) return [];
    return [{
      element: element.id ? `#${element.id}` : element.tagName.toLowerCase(),
      maximumDurationSeconds: maximum,
    }];
  }).slice(0, 30);
  return {
    mediaMatches: matchMedia('(prefers-reduced-motion: reduce)').matches,
    violations,
  };
}
"""


PRINT_METRICS_JS = r"""
() => {
  const slides = Array.from(document.querySelectorAll('.deck-stage > .slide'));
  const visible = (element) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' &&
      Number.parseFloat(style.opacity || '1') >= 0.99 && rect.width > 1 && rect.height > 1;
  };
  const invisibleSlides = slides.filter((slide) => !visible(slide)).map((slide) => slide.id);
  const invisibleFragments = Array.from(document.querySelectorAll('[data-fragment]'))
    .filter((fragment) => !visible(fragment))
    .map((fragment) => fragment.closest('.slide')?.id || '<unknown>');
  const chromeSelectors = [
    '.progress-track', '.deck-rail', '.deck-dots', '.deck-controls',
    '.overlay', '.notes-panel', '.orientation-hint',
  ];
  const visibleChrome = chromeSelectors.filter((selector) =>
    Array.from(document.querySelectorAll(selector)).some((element) => getComputedStyle(element).display !== 'none'));
  const badPageBreaks = slides.slice(0, -1).flatMap((slide) => {
    const value = getComputedStyle(slide).breakAfter;
    return value === 'page' ? [] : [{ id: slide.id, breakAfter: value }];
  });
  const stage = document.querySelector('.deck-stage');
  const stageStyle = stage ? getComputedStyle(stage) : null;
  return {
    mediaMatches: matchMedia('print').matches,
    slideCount: slides.length,
    invisibleSlides,
    invisibleFragments,
    visibleChrome,
    badPageBreaks,
    stagePosition: stageStyle?.position || '',
    stageOverflow: stageStyle?.overflow || '',
  };
}
"""


def _path_for_report(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _slide_screenshot_path(
    output_dir: Path,
    viewport: Viewport,
    slide_index: int,
    slide_id: str,
) -> Path:
    directory = output_dir / "screenshots" / viewport.name
    directory.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", slide_id).strip("-") or "slide"
    return directory / f"{slide_index:03d}-{safe_id}.png"


def _open_page(
    browser: Any,
    *,
    viewport: Viewport,
    reduced_motion: str,
) -> tuple[Any, Any, list[str], list[str], list[str]]:
    context = browser.new_context(
        viewport={"width": viewport.width, "height": viewport.height},
        reduced_motion=reduced_motion,
        device_scale_factor=1,
    )
    page = context.new_page()
    console_errors: list[str] = []
    console_warnings: list[str] = []
    page_errors: list[str] = []

    def capture_console(message: Any) -> None:
        if message.type == "error":
            console_errors.append(message.text)
        elif message.type == "warning":
            console_warnings.append(message.text)

    page.on("console", capture_console)
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    return context, page, console_errors, console_warnings, page_errors


def _load_deck(
    page: Any, input_uri: str, timeout_ms: int, *, profile: str = "stage"
) -> dict[str, Any]:
    page.goto(input_uri, wait_until="load", timeout=timeout_ms)
    stage_selector = ".deck-stage" if profile == "stage" else "main"
    slide_selector = (
        ".deck-stage > .slide.is-active" if profile == "stage" else "main > .slide"
    )
    page.locator(stage_selector).wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_function(
        "(selector) => !!document.querySelector(selector)",
        arg=slide_selector,
        timeout=timeout_ms,
    )
    return page.evaluate(
        """({ profile }) => {
          const selector = profile === 'static' ? 'main > .slide' : '.deck-stage > .slide';
          return ({
          title: document.title,
          language: document.documentElement.lang,
          slides: Array.from(document.querySelectorAll(selector)).map((slide, index) => ({
            index: index + 1,
            id: slide.id || `slide-${index + 1}`,
            title: slide.dataset.slideTitle || slide.dataset.title || slide.querySelector('h1,h2,h3')?.textContent?.trim() || slide.id || `Slide ${index + 1}`,
            fragmentCount: slide.querySelectorAll('[data-fragment]').length,
          })),
        });
        }""",
        {"profile": profile},
    )


def _runtime_message_checks(
    console_errors: list[str],
    console_warnings: list[str],
    page_errors: list[str],
) -> list[dict[str, Any]]:
    return [
        _check(
            "runtime.console_errors",
            "pass" if not console_errors else "fail",
            (
                "The browser console contains no errors."
                if not console_errors
                else f"The browser console emitted {len(console_errors)} error(s)."
            ),
            details=console_errors[:20],
        ),
        _check(
            "runtime.page_errors",
            "pass" if not page_errors else "fail",
            (
                "The page emitted no uncaught errors."
                if not page_errors
                else f"The page emitted {len(page_errors)} uncaught error(s)."
            ),
            details=page_errors[:20],
        ),
        _check(
            "runtime.console_warnings",
            "pass" if not console_warnings else "warning",
            (
                "The browser console contains no warnings."
                if not console_warnings
                else f"The browser console emitted {len(console_warnings)} warning(s)."
            ),
            details=console_warnings[:20],
        ),
    ]


def _audit_viewport(
    browser: Any,
    *,
    input_uri: str,
    output_dir: Path,
    viewport: Viewport,
    timeout_ms: int,
    playwright_error: type[BaseException],
    profile: str = "stage",
) -> tuple[dict[str, Any], dict[str, Any]]:
    report: dict[str, Any] = {
        **asdict(viewport),
        "status": "pass",
        "slides": [],
        "checks": [],
    }
    deck_info: dict[str, Any] = {"title": "", "language": "", "slides": []}
    context, page, console_errors, console_warnings, page_errors = _open_page(
        browser, viewport=viewport, reduced_motion="reduce"
    )
    try:
        deck_info = _load_deck(page, input_uri, timeout_ms, profile=profile)
        for slide in deck_info.get("slides", []):
            slide_id = str(slide.get("id") or "")
            slide_index = int(slide.get("index") or 0)
            slide_report: dict[str, Any] = {
                "index": slide_index,
                "id": slide_id,
                "title": str(slide.get("title") or ""),
                "screenshot": None,
                "checks": [],
            }
            if not slide_id:
                slide_report["checks"].append(
                    _check(
                        "navigation.slide_id",
                        "fail",
                        "A slide is missing the stable ID required for browser QA.",
                    )
                )
                report["slides"].append(slide_report)
                continue
            if profile == "static":
                page.evaluate(
                    """(index) => {
                      const dispatch = (key) => document.dispatchEvent(new KeyboardEvent('keydown', {
                        key,
                        bubbles: true,
                        cancelable: true,
                      }));
                      dispatch('Home');
                      for (let step = 0; step < index; step += 1) dispatch('ArrowRight');
                      Array.from(document.querySelectorAll('main > .slide')).forEach((slide, candidate) => {
                        slide.hidden = candidate !== index;
                        slide.setAttribute('aria-hidden', String(candidate !== index));
                      });
                    }""",
                    slide_index - 1,
                )
            else:
                page.evaluate(
                    "(id) => { location.hash = `#${encodeURIComponent(id)}`; }",
                    slide_id,
                )
                page.wait_for_function(
                    "(id) => document.getElementById(id)?.classList.contains('is-active')",
                    arg=slide_id,
                    timeout=timeout_ms,
                )
                page.evaluate(
                    "(id) => document.getElementById(id)?.querySelectorAll('[data-fragment]').forEach((fragment) => fragment.classList.add('is-shown'))",
                    slide_id,
                )
            page.wait_for_timeout(30)
            metrics = page.evaluate(
                LAYOUT_METRICS_JS,
                {
                    "slideId": slide_id,
                    "slideIndex": slide_index - 1,
                    "profile": profile,
                },
            )
            slide_report["checks"] = assess_layout_metrics(
                metrics,
                include_document_checks=slide_index == 1,
                exact_canvas=profile == "static",
            )
            screenshot_path = _slide_screenshot_path(
                output_dir, viewport, slide_index, slide_id
            )
            try:
                screenshot_scope = _capture_slide_screenshot(
                    page,
                    screenshot_path=screenshot_path,
                    profile=profile,
                )
                slide_report["screenshot"] = _path_for_report(
                    screenshot_path, output_dir
                )
                slide_report["checks"].append(
                    _check(
                        "render.screenshot",
                        "pass",
                        f"Captured a {screenshot_scope} screenshot for this slide.",
                    )
                )
            except (playwright_error, OSError) as exc:
                slide_report["checks"].append(
                    _check(
                        "render.screenshot",
                        "fail",
                        f"Unable to capture the slide screenshot: {exc}",
                    )
                )
            report["slides"].append(slide_report)
        report["checks"].extend(
            _runtime_message_checks(console_errors, console_warnings, page_errors)
        )
    finally:
        context.close()
    checks = report["checks"] + [
        check for slide_report in report["slides"] for check in slide_report["checks"]
    ]
    report["status"] = _section_status(checks)
    return report, deck_info


def _capture_slide_screenshot(
    page: Any,
    *,
    screenshot_path: Path,
    profile: str,
) -> str:
    """Capture a stable slide image and return the screenshot scope label."""

    if profile == "static":
        page.locator("main > .slide:not([hidden])").screenshot(
            path=str(screenshot_path)
        )
        return "slide-element"
    page.screenshot(path=str(screenshot_path), full_page=False)
    return "full-viewport"


def _audit_interactions(
    browser: Any,
    *,
    input_uri: str,
    viewport: Viewport,
    timeout_ms: int,
    profile: str = "stage",
) -> dict[str, Any]:
    context, page, console_errors, console_warnings, page_errors = _open_page(
        browser, viewport=viewport, reduced_motion="reduce"
    )
    try:
        _load_deck(page, input_uri, timeout_ms, profile=profile)
        checks = assess_interaction_results(
            page.evaluate(
                STATIC_INTERACTION_JS if profile == "static" else INTERACTION_JS
            )
        )
        checks.extend(
            _runtime_message_checks(console_errors, console_warnings, page_errors)
        )
    finally:
        context.close()
    return {"status": _section_status(checks), "checks": checks}


def _audit_reduced_motion(
    browser: Any,
    *,
    input_uri: str,
    viewport: Viewport,
    timeout_ms: int,
) -> dict[str, Any]:
    context, page, console_errors, console_warnings, page_errors = _open_page(
        browser, viewport=viewport, reduced_motion="reduce"
    )
    try:
        _load_deck(page, input_uri, timeout_ms)
        metrics = page.evaluate(REDUCED_MOTION_JS)
        media_matches = bool(metrics.get("mediaMatches"))
        violations = list(metrics.get("violations") or [])
        checks = [
            _check(
                "accessibility.reduced_motion_media",
                "pass" if media_matches else "fail",
                (
                    "The browser activates prefers-reduced-motion."
                    if media_matches
                    else "The reduced-motion browser context did not activate its media query."
                ),
            ),
            _check(
                "accessibility.reduced_motion_duration",
                "pass" if not violations else "fail",
                (
                    "Rendered transitions and animations collapse under reduced motion."
                    if not violations
                    else f"Found {len(violations)} element(s) with motion longer than 10ms."
                ),
                details=violations,
            ),
        ]
        checks.extend(
            _runtime_message_checks(console_errors, console_warnings, page_errors)
        )
    finally:
        context.close()
    return {"status": _section_status(checks), "checks": checks}


def _audit_print(
    browser: Any,
    *,
    input_uri: str,
    output_dir: Path,
    viewport: Viewport,
    timeout_ms: int,
    playwright_error: type[BaseException],
) -> dict[str, Any]:
    context, page, console_errors, console_warnings, page_errors = _open_page(
        browser, viewport=viewport, reduced_motion="reduce"
    )
    pdf_path = output_dir / "print-preview.pdf"
    try:
        _load_deck(page, input_uri, timeout_ms)
        page.emulate_media(media="print", reduced_motion="reduce")
        page.wait_for_timeout(30)
        metrics = page.evaluate(PRINT_METRICS_JS)
        invisible_slides = list(metrics.get("invisibleSlides") or [])
        invisible_fragments = list(metrics.get("invisibleFragments") or [])
        visible_chrome = list(metrics.get("visibleChrome") or [])
        bad_breaks = list(metrics.get("badPageBreaks") or [])
        checks = [
            _check(
                "print.media",
                "pass" if metrics.get("mediaMatches") else "fail",
                (
                    "The print media query is active."
                    if metrics.get("mediaMatches")
                    else "The browser did not activate print media."
                ),
            ),
            _check(
                "print.slides_visible",
                "pass" if not invisible_slides else "fail",
                (
                    "Every slide is visible in print mode."
                    if not invisible_slides
                    else "Some slides remain hidden in print mode."
                ),
                details=invisible_slides,
            ),
            _check(
                "print.fragments_visible",
                "pass" if not invisible_fragments else "fail",
                (
                    "Every fragment is visible in print mode."
                    if not invisible_fragments
                    else "Some fragments remain hidden in print mode."
                ),
                details=invisible_fragments,
            ),
            _check(
                "print.operator_chrome_hidden",
                "pass" if not visible_chrome else "fail",
                (
                    "Operator controls and overlays are hidden in print mode."
                    if not visible_chrome
                    else "Some operator chrome remains visible in print mode."
                ),
                details=visible_chrome,
            ),
            _check(
                "print.page_breaks",
                "pass" if not bad_breaks else "fail",
                (
                    "Every non-final slide declares a print page break."
                    if not bad_breaks
                    else "Some slides do not declare a print page break."
                ),
                details=bad_breaks,
            ),
            _check(
                "print.stage_flow",
                (
                    "pass"
                    if metrics.get("stagePosition") == "static"
                    and metrics.get("stageOverflow") == "visible"
                    else "fail"
                ),
                (
                    "The print stage participates in page flow with visible overflow."
                    if metrics.get("stagePosition") == "static"
                    and metrics.get("stageOverflow") == "visible"
                    else "The print stage is still fixed or clipped."
                ),
                details={
                    "position": metrics.get("stagePosition"),
                    "overflow": metrics.get("stageOverflow"),
                },
            ),
        ]
        try:
            page.pdf(
                path=str(pdf_path),
                print_background=True,
                prefer_css_page_size=True,
            )
            pdf_ready = pdf_path.is_file() and pdf_path.stat().st_size > 1000
            checks.append(
                _check(
                    "print.pdf_render",
                    "pass" if pdf_ready else "fail",
                    (
                        "Rendered a non-empty PDF print preview."
                        if pdf_ready
                        else "The generated PDF print preview is empty."
                    ),
                    details={
                        "path": _path_for_report(pdf_path, output_dir),
                        "bytes": pdf_path.stat().st_size if pdf_path.exists() else 0,
                    },
                )
            )
        except (playwright_error, OSError) as exc:
            checks.append(
                _check(
                    "print.pdf_render",
                    "fail",
                    f"Unable to render the PDF print preview: {exc}",
                )
            )
        checks.extend(
            _runtime_message_checks(console_errors, console_warnings, page_errors)
        )
    finally:
        context.close()
    return {
        "status": _section_status(checks),
        "preview": (
            _path_for_report(pdf_path, output_dir) if pdf_path.exists() else None
        ),
        "checks": checks,
    }


def _section_status(checks: list[dict[str, Any]]) -> str:
    statuses = {str(check.get("status")) for check in checks}
    if "blocker" in statuses:
        return "blocked"
    if "fail" in statuses:
        return "fail"
    if "warning" in statuses:
        return "warning"
    if statuses == {"skip"}:
        return "skip"
    return "pass"


def _write_screenshot_index(
    output_dir: Path,
    *,
    deck_title: str,
    viewport_reports: list[dict[str, Any]],
) -> Path | None:
    screenshots = [
        (viewport, slide)
        for viewport in viewport_reports
        for slide in viewport.get("slides", [])
        if slide.get("screenshot")
    ]
    if not screenshots:
        return None
    index_path = output_dir / "screenshots" / "index.html"
    cards: list[str] = []
    for viewport, slide in screenshots:
        screenshot_path = str(slide["screenshot"])
        relative_image = Path(screenshot_path).relative_to("screenshots").as_posix()
        cards.append(
            "<figure>"
            f'<a href="{html.escape(relative_image, quote=True)}">'
            f'<img loading="lazy" src="{html.escape(relative_image, quote=True)}" '
            f'alt="{html.escape(str(slide.get("title") or slide.get("id")), quote=True)}"></a>'
            f"<figcaption>{html.escape(str(viewport.get('name')))} · "
            f"{html.escape(str(slide.get('index')))} · "
            f"{html.escape(str(slide.get('title') or slide.get('id')))}</figcaption>"
            "</figure>"
        )
    rendered = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · browser QA screenshots</title><style>
body{{margin:0;padding:24px;background:#111;color:#eee;font:14px system-ui,sans-serif}}
h1{{font-size:22px}}main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px}}
figure{{margin:0;padding:10px;border:1px solid #3a3a3a;background:#191919}}img{{display:block;width:100%;height:auto;background:#000}}
figcaption{{padding-top:8px;color:#bbb}}
</style></head><body><h1>{title}</h1><main>{cards}</main></body></html>
""".format(title=html.escape(deck_title or "Clara deck"), cards="".join(cards))
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(rendered, encoding="utf-8")
    return index_path


def _all_checks(report: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for viewport in report.get("viewports", []):
        checks.extend(viewport.get("checks", []))
        for slide in viewport.get("slides", []):
            checks.extend(slide.get("checks", []))
    for section_name in ("interaction", "reduced_motion", "print"):
        section = report.get(section_name) or {}
        checks.extend(section.get("checks", []))
    checks.extend(report.get("checks", []))
    return checks


def _finalize_report(report: dict[str, Any]) -> dict[str, Any]:
    checks = _all_checks(report)
    counts: dict[str, int] = {}
    for check in checks:
        status = str(check.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    screenshot_count = sum(
        1
        for viewport in report.get("viewports", [])
        for slide in viewport.get("slides", [])
        if slide.get("screenshot")
    )
    result = "pass"
    if report.get("browser", {}).get("status") == "blocked" or counts.get("blocker", 0):
        result = "blocked"
    elif counts.get("fail", 0):
        result = "fail"
    report["result"] = result
    report["summary"] = {
        "viewport_count": len(report.get("viewports", [])),
        "slide_count": len(report.get("deck", {}).get("slides", [])),
        "screenshot_count": screenshot_count,
        "check_status_counts": dict(sorted(counts.items())),
    }
    return report


def _base_report(
    input_path: Path, output_dir: Path, *, profile: str = "stage"
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "result": "blocked",
        "profile": profile,
        "input": {
            "path": input_path.as_posix(),
            "bytes": input_path.stat().st_size if input_path.is_file() else 0,
            "sha256": (
                hashlib.sha256(input_path.read_bytes()).hexdigest()
                if input_path.is_file()
                else None
            ),
        },
        "output": {
            "directory": output_dir.as_posix(),
            "screenshot_index": None,
            "print_preview": None,
        },
        "browser": {
            "status": "blocked",
            "engine": "chromium",
            "candidate": None,
            "executable": None,
            "attempts": [],
        },
        "deck": {"title": "", "language": "", "slides": []},
        "viewports": [],
        "interaction": {"status": "blocked", "checks": []},
        "reduced_motion": {"status": "blocked", "checks": []},
        "print": {"status": "blocked", "preview": None, "checks": []},
        "checks": [],
        "manual_review": [
            "Confirm every claim, number, period, qualification, and speaker note against the authoritative sources.",
            "Review the complete screenshot index for hierarchy, legibility, contrast, visual coherence, and editorial quality.",
            "Judge whether each chart or diagram communicates the intended mechanism rather than merely fitting its box.",
            "Review motion at normal speed; the mechanical gate only verifies the reduced-motion contract.",
            "Exercise touch swipe and fullscreen on representative presentation hardware.",
            "Scan the PDF preview page by page for print-specific visual defects.",
        ],
    }


def run_browser_qa(
    input_path: Path,
    *,
    output_dir: Path,
    viewports: tuple[Viewport, ...] | list[Viewport] | None = None,
    browser_executable: str | None = None,
    timeout_ms: int = 15_000,
    playwright_factory: Callable[[], AbstractContextManager[Any]] | None = None,
    playwright_error: type[BaseException] | None = None,
    profile: str = "stage",
) -> dict[str, Any]:
    """Run browser QA and return a JSON-serializable report."""

    resolved_input = input_path.expanduser().resolve()
    resolved_output = output_dir.expanduser().resolve()
    resolved_output.mkdir(parents=True, exist_ok=True)
    if profile not in QA_PROFILES:
        raise ValueError(f"Unsupported browser QA profile: {profile}")
    report = _base_report(resolved_input, resolved_output, profile=profile)
    if not resolved_input.is_file():
        report["checks"].append(
            _check(
                "input.index_html",
                "blocker",
                f"Input HTML does not exist: {resolved_input}",
            )
        )
        return _finalize_report(report)
    if resolved_input.suffix.lower() not in {".html", ".htm"}:
        report["checks"].append(
            _check(
                "input.index_html",
                "blocker",
                "Browser QA requires an .html or .htm input file.",
            )
        )
        return _finalize_report(report)

    viewport_list = tuple(
        viewports or tuple(parse_viewport(item) for item in DEFAULT_VIEWPORTS)
    )
    if not viewport_list:
        report["checks"].append(
            _check("input.viewports", "blocker", "At least one viewport is required.")
        )
        return _finalize_report(report)
    duplicate_names = sorted(
        {
            item.name
            for item in viewport_list
            if sum(candidate.name == item.name for candidate in viewport_list) > 1
        }
    )
    if duplicate_names:
        report["checks"].append(
            _check(
                "input.viewport_names",
                "blocker",
                "Viewport names must be unique.",
                details=duplicate_names,
            )
        )
        return _finalize_report(report)

    factory = playwright_factory
    error_type = playwright_error
    if factory is None or error_type is None:
        try:
            from playwright.sync_api import Error as ImportedPlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            report["checks"].append(
                _check(
                    "browser.playwright_available",
                    "blocker",
                    f"Python Playwright is unavailable: {exc}",
                )
            )
            return _finalize_report(report)
        factory = sync_playwright
        error_type = ImportedPlaywrightError

    if factory is None or error_type is None:
        report["checks"].append(
            _check(
                "browser.playwright_bindings",
                "blocker",
                "Playwright bindings could not be initialized.",
            )
        )
        return _finalize_report(report)
    try:
        with factory() as playwright:
            browser, browser_report = launch_chromium_with_fallbacks(
                playwright,
                playwright_error=error_type,
                explicit_path=browser_executable,
            )
            report["browser"] = browser_report
            if browser is None:
                report["checks"].append(
                    _check(
                        "browser.chromium_available",
                        "blocker",
                        "No local or Playwright-managed Chromium browser could be launched.",
                        details=browser_report.get("attempts"),
                    )
                )
                return _finalize_report(report)
            try:
                input_uri = resolved_input.as_uri()
                deck_info: dict[str, Any] | None = None
                for viewport in viewport_list:
                    try:
                        viewport_report, candidate_deck_info = _audit_viewport(
                            browser,
                            input_uri=input_uri,
                            output_dir=resolved_output,
                            viewport=viewport,
                            timeout_ms=timeout_ms,
                            playwright_error=error_type,
                            profile=profile,
                        )
                    except (error_type, OSError, ValueError) as exc:
                        viewport_report = {
                            **asdict(viewport),
                            "status": "fail",
                            "slides": [],
                            "checks": [
                                _check(
                                    "browser.viewport_runtime",
                                    "fail",
                                    f"Browser QA failed at this viewport: {exc}",
                                )
                            ],
                        }
                        candidate_deck_info = {"slides": []}
                    report["viewports"].append(viewport_report)
                    if deck_info is None and candidate_deck_info.get("slides"):
                        deck_info = candidate_deck_info
                if deck_info is not None:
                    report["deck"] = deck_info

                primary_viewport = viewport_list[0]
                try:
                    report["interaction"] = _audit_interactions(
                        browser,
                        input_uri=input_uri,
                        viewport=primary_viewport,
                        timeout_ms=timeout_ms,
                        profile=profile,
                    )
                except (error_type, OSError, ValueError) as exc:
                    report["interaction"] = {
                        "status": "fail",
                        "checks": [
                            _check(
                                "interaction.runtime",
                                "fail",
                                f"Interaction QA could not complete: {exc}",
                            )
                        ],
                    }
                if profile == "static":
                    report["reduced_motion"] = {
                        "status": "skip",
                        "checks": [
                            _check(
                                "accessibility.reduced_motion_profile",
                                "skip",
                                "Static brief does not require motion or reduced-motion controls.",
                            )
                        ],
                    }
                    report["print"] = {
                        "status": "skip",
                        "preview": None,
                        "checks": [
                            _check(
                                "print.profile",
                                "skip",
                                "Static brief requires full-size screenshots rather than print packaging.",
                            )
                        ],
                    }
                else:
                    try:
                        report["reduced_motion"] = _audit_reduced_motion(
                            browser,
                            input_uri=input_uri,
                            viewport=primary_viewport,
                            timeout_ms=timeout_ms,
                        )
                    except (error_type, OSError, ValueError) as exc:
                        report["reduced_motion"] = {
                            "status": "fail",
                            "checks": [
                                _check(
                                    "accessibility.reduced_motion_runtime",
                                    "fail",
                                    f"Reduced-motion QA could not complete: {exc}",
                                )
                            ],
                        }
                    try:
                        report["print"] = _audit_print(
                            browser,
                            input_uri=input_uri,
                            output_dir=resolved_output,
                            viewport=primary_viewport,
                            timeout_ms=timeout_ms,
                            playwright_error=error_type,
                        )
                    except (error_type, OSError, ValueError) as exc:
                        report["print"] = {
                            "status": "fail",
                            "preview": None,
                            "checks": [
                                _check(
                                    "print.runtime",
                                    "fail",
                                    f"Print QA could not complete: {exc}",
                                )
                            ],
                        }
            finally:
                browser.close()
    except (error_type, OSError) as exc:
        report["checks"].append(
            _check(
                "browser.playwright_runtime",
                "blocker",
                f"Playwright could not initialize: {exc}",
            )
        )
        return _finalize_report(report)

    screenshot_index = _write_screenshot_index(
        resolved_output,
        deck_title=str(report.get("deck", {}).get("title") or "Clara deck"),
        viewport_reports=report["viewports"],
    )
    report["output"]["screenshot_index"] = (
        _path_for_report(screenshot_index, resolved_output)
        if screenshot_index is not None
        else None
    )
    report["output"]["print_preview"] = report.get("print", {}).get("preview")
    return _finalize_report(report)


def main(argv: list[str] | None = None) -> int:
    """Run the browser QA command-line interface."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Standalone Clara index.html")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--report",
        type=Path,
        help="JSON report path (default: <output-dir>/browser-qa.json)",
    )
    parser.add_argument(
        "--viewport",
        type=parse_viewport,
        action="append",
        help="Repeatable WIDTHxHEIGHT or name=WIDTHxHEIGHT viewport.",
    )
    parser.add_argument("--browser-executable")
    parser.add_argument("--timeout-ms", type=int, default=15_000)
    parser.add_argument("--warnings-as-errors", action="store_true")
    parser.add_argument("--profile", choices=sorted(QA_PROFILES), default="stage")
    args = parser.parse_args(argv)
    if args.timeout_ms < 1_000:
        parser.error("--timeout-ms must be at least 1000")

    report = run_browser_qa(
        args.input,
        output_dir=args.output_dir,
        viewports=args.viewport,
        browser_executable=args.browser_executable,
        timeout_ms=args.timeout_ms,
        profile=args.profile,
    )
    report_path = (
        args.report.expanduser().resolve()
        if args.report
        else args.output_dir.expanduser().resolve() / "browser-qa.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    report_path.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    if report["result"] == "blocked":
        return 2
    if report["result"] == "fail":
        return 1
    if args.warnings_as_errors and report["summary"]["check_status_counts"].get(
        "warning", 0
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
