#!/usr/bin/env python3
"""Run deterministic desktop/mobile browser QA for an Attribute Report draft."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "assess_browser_metrics",
    "run_browser_qa",
    "main",
]

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = "attribute_reporting.browser_qa.v1"
VIEWPORTS = (
    {"name": "desktop", "width": 1440, "height": 1000},
    {"name": "mobile", "width": 390, "height": 844},
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _finding(
    code: str,
    status: str,
    message: str,
    *,
    details: Any = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "status": status,
        "message": message,
        "details": details,
    }


def assess_browser_metrics(
    metrics: Mapping[str, Any],
    *,
    viewport_name: str,
    console_errors: Sequence[str] = (),
    page_errors: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Convert mechanically measurable browser state into QA findings."""

    findings: list[dict[str, Any]] = []
    prefix = f"browser.{viewport_name}"
    horizontal_overflow = bool(metrics.get("horizontalOverflow"))
    findings.append(
        _finding(
            f"{prefix}.horizontal_overflow",
            "fail" if horizontal_overflow else "pass",
            (
                "The report document overflows horizontally."
                if horizontal_overflow
                else "The report document fits the viewport horizontally."
            ),
            details=metrics.get("document"),
        )
    )
    broken_images = list(metrics.get("brokenImages") or [])
    findings.append(
        _finding(
            f"{prefix}.local_images",
            "fail" if broken_images else "pass",
            (
                f"Found {len(broken_images)} broken local image(s)."
                if broken_images
                else "Every rendered product image loaded successfully."
            ),
            details=broken_images,
        )
    )
    unsafe_assets = list(metrics.get("unsafeAssets") or [])
    findings.append(
        _finding(
            f"{prefix}.asset_locality",
            "fail" if unsafe_assets else "pass",
            (
                "The report references external or unsafe assets."
                if unsafe_assets
                else "Report scripts and images are local or embedded."
            ),
            details=unsafe_assets,
        )
    )
    table_failures = list(metrics.get("uncontainedWideTables") or [])
    findings.append(
        _finding(
            f"{prefix}.table_scrolling",
            "fail" if table_failures else "pass",
            (
                "One or more wide tables lack a horizontal scroll container."
                if table_failures
                else "Wide tables remain inside scrollable containers."
            ),
            details=table_failures,
        )
    )
    missing_elements = list(metrics.get("missingRequiredElements") or [])
    findings.append(
        _finding(
            f"{prefix}.required_elements",
            "fail" if missing_elements else "pass",
            (
                "Required report elements are missing."
                if missing_elements
                else "Required report structure is present."
            ),
            details=missing_elements,
        )
    )
    unsafe_links = list(metrics.get("unsafeProductLinks") or [])
    findings.append(
        _finding(
            f"{prefix}.product_links",
            "fail" if unsafe_links else "pass",
            (
                "Product links are malformed or missing safe new-tab attributes."
                if unsafe_links
                else "Product links use safe HTTP(S) new-tab behavior."
            ),
            details=unsafe_links,
        )
    )
    runtime_errors = [*console_errors, *page_errors]
    findings.append(
        _finding(
            f"{prefix}.runtime",
            "fail" if runtime_errors else "pass",
            (
                f"Found {len(runtime_errors)} browser runtime error(s)."
                if runtime_errors
                else "No browser console or page errors were observed."
            ),
            details=runtime_errors,
        )
    )
    return findings


_METRICS_SCRIPT = r"""
() => {
  const absolute = (value) => {
    try { return new URL(value, document.baseURI); } catch (_error) { return null; }
  };
  const brokenImages = Array.from(document.images)
    .filter((image) => !image.complete || image.naturalWidth <= 0 || image.naturalHeight <= 0)
    .map((image) => image.getAttribute('src') || '');
  const unsafeAssets = [
    ...Array.from(document.images).map((node) => ({kind: 'image', value: node.getAttribute('src') || ''})),
    ...Array.from(document.scripts).map((node) => ({kind: 'script', value: node.getAttribute('src') || ''})),
  ].filter((item) => {
    if (!item.value) return false;
    const parsed = absolute(item.value);
    return !parsed || !['file:', 'data:'].includes(parsed.protocol);
  });
  const uncontainedWideTables = Array.from(document.querySelectorAll('table')).flatMap((table, index) => {
    if (table.scrollWidth <= table.clientWidth + 1) return [];
    const container = table.closest('.table-scroll');
    if (!container) return [{index, reason: 'missing .table-scroll'}];
    const style = getComputedStyle(container);
    const permitsScroll = ['auto', 'scroll'].includes(style.overflowX) || ['auto', 'scroll'].includes(style.overflow);
    return permitsScroll ? [] : [{index, reason: `overflow-x=${style.overflowX}`}];
  });
  const requiredSelectors = [
    'main.report-shell',
    'header.hero',
    '.verdict-slot',
    '.verdict[data-correctness-verdict="pending"]',
    'nav.report-nav',
    'section[data-section-id="method_and_caveats"]',
  ];
  const missingRequiredElements = requiredSelectors.filter((selector) => !document.querySelector(selector));
  const unsafeProductLinks = Array.from(document.querySelectorAll('.product-card h3 a')).flatMap((link) => {
    const parsed = absolute(link.getAttribute('href') || '');
    const rel = new Set((link.getAttribute('rel') || '').split(/\s+/).filter(Boolean));
    if (!parsed || !['http:', 'https:'].includes(parsed.protocol)) return [{href: link.getAttribute('href') || '', reason: 'invalid protocol'}];
    if (link.getAttribute('target') !== '_blank' || !rel.has('noreferrer')) return [{href: parsed.href, reason: 'unsafe new-tab attributes'}];
    return [];
  });
  const root = document.documentElement;
  return {
    document: {clientWidth: root.clientWidth, scrollWidth: root.scrollWidth, clientHeight: root.clientHeight, scrollHeight: root.scrollHeight},
    horizontalOverflow: root.scrollWidth > root.clientWidth + 1,
    brokenImages,
    unsafeAssets,
    uncontainedWideTables,
    missingRequiredElements,
    unsafeProductLinks,
    warningCount: document.querySelectorAll('[data-warning-code]').length,
    productCardCount: document.querySelectorAll('.product-card').length,
  };
}
"""


def run_browser_qa(
    output_dir: Path,
    *,
    viewports: Sequence[Mapping[str, Any]] = VIEWPORTS,
    output_path: Path | None = None,
    screenshot_dir: Path | None = None,
) -> dict[str, Any]:
    """Open the rendered draft at two viewports and persist QA evidence."""

    output = output_dir.expanduser().resolve()
    render_manifest = _load_json(output / "render_manifest.json")
    catalog = _load_json(output / "evidence_catalog.json")
    draft = output / str(render_manifest.get("draft_html") or "report_draft.html")
    if not draft.is_file():
        raise ValueError(f"Rendered report draft is missing: {draft}")
    if _sha256_file(draft) != str(render_manifest.get("draft_html_sha256") or ""):
        raise ValueError("Rendered report draft hash differs from render_manifest.json")
    target = output_path or output / "browser_qa.json"
    screenshots = screenshot_dir or output / "qa" / "screenshots"
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "checked_at": _utc_now(),
        "report_id": catalog.get("report_id"),
        "targets": {
            "draft_html": str(draft),
            "draft_html_sha256": _sha256_file(draft),
            "render_manifest_sha256": _sha256_file(output / "render_manifest.json"),
        },
        "status": "blocked",
        "viewports": [],
        "findings": [],
        "browser_error": "",
    }
    try:
        from playwright.sync_api import Error as PlaywrightError  # noqa: PLC0415
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError as exc:
        report["browser_error"] = f"Playwright is unavailable: {exc}"
        _write_json(target, report)
        return report

    try:
        screenshots.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for raw_viewport in viewports:
                    name = str(raw_viewport["name"])
                    width = int(raw_viewport["width"])
                    height = int(raw_viewport["height"])
                    context = browser.new_context(
                        viewport={"width": width, "height": height}
                    )
                    page = context.new_page()
                    console_errors: list[str] = []
                    page_errors: list[str] = []
                    page.on(
                        "console",
                        lambda message, errors=console_errors: (
                            errors.append(message.text)
                            if message.type == "error"
                            else None
                        ),
                    )
                    page.on(
                        "pageerror",
                        lambda error, errors=page_errors: errors.append(str(error)),
                    )
                    page.goto(draft.as_uri(), wait_until="load")
                    page.wait_for_timeout(100)
                    metrics = page.evaluate(_METRICS_SCRIPT)
                    screenshot_path = screenshots / f"report-{name}.png"
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    findings = assess_browser_metrics(
                        metrics,
                        viewport_name=name,
                        console_errors=console_errors,
                        page_errors=page_errors,
                    )
                    report["viewports"].append(
                        {
                            "name": name,
                            "width": width,
                            "height": height,
                            "screenshot": screenshot_path.relative_to(
                                output
                            ).as_posix(),
                            "screenshot_sha256": _sha256_file(screenshot_path),
                            "metrics": metrics,
                            "findings": findings,
                        }
                    )
                    report["findings"].extend(findings)
                    context.close()
            finally:
                browser.close()
    except (OSError, PlaywrightError) as exc:
        report["browser_error"] = str(exc)
        _write_json(target, report)
        return report

    report["status"] = (
        "fail"
        if any(item.get("status") == "fail" for item in report["findings"])
        else "pass"
    )
    _write_json(target, report)
    return report


def main() -> int:
    """Run report browser QA from the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--screenshot-dir", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        report = run_browser_qa(
            args.output_dir,
            output_path=args.output,
            screenshot_dir=args.screenshot_dir,
        )
    except ValueError as exc:
        LOGGER.error("Browser QA failed to start: %s", exc)
        return 1
    if report["status"] == "blocked":
        LOGGER.error("Browser QA is blocked: %s", report["browser_error"])
        return 2
    LOGGER.info("Browser QA status: %s", report["status"])
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
