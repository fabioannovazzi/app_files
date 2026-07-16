from __future__ import annotations

import argparse
import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

__all__ = ["main", "render_cosmetics_question_png_assets"]

LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = Path("/private/tmp/chart_question_review_render/cosmetics_rerun")
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT
    / "runs"
    / "chart_selection_manifest_rebuild"
    / "cosmetics_question_png_assets"
)
DEFAULT_REMOTE_URL = "http://127.0.0.1:9340"
DEFAULT_BROWSER_MODE = "cdp"


@dataclass(frozen=True, slots=True)
class RenderTarget:
    capability_id: str
    source_relative_path: str
    output_name: str
    width: int = 1600
    height: int = 1000
    source_kind: str = "html"
    secondary_source_relative_path: str | None = None


TARGETS: tuple[RenderTarget, ...] = (
    RenderTarget(
        "period_comparison.trend",
        "period/year_over_year_line.html",
        "period_comparison_trend.png",
    ),
    RenderTarget(
        "period_comparison.horizontal_waterfall",
        "period/year_over_year_waterfall.html",
        "period_comparison_horizontal_waterfall.png",
    ),
    RenderTarget(
        "period_comparison.dot",
        "period/year_over_year_dot.html",
        "period_comparison_dot.png",
    ),
    RenderTarget(
        "period_comparison.slope",
        "period/year_over_year_slope.html",
        "period_comparison_slope.png",
    ),
    RenderTarget(
        "period_comparison.by_period",
        "period/year_over_year_by_period.html",
        "period_comparison_by_period.png",
    ),
    RenderTarget(
        "period_comparison.multitier_column",
        "period/year_over_year_column.html",
        "period_comparison_multitier_column.png",
    ),
    RenderTarget(
        "period_comparison.comparison_table",
        "period/comparison_table.html",
        "period_comparison_comparison_table.png",
        width=1800,
        height=1000,
    ),
    RenderTarget(
        "period_comparison.time_series_table",
        "period/time_series_table.html",
        "period_comparison_time_series_table.png",
        width=1800,
        height=1000,
    ),
    RenderTarget(
        "mix.multitier_bar",
        "mix_multitier/multitier_bar_two_dimension.html",
        "mix_multitier_bar.png",
        width=2200,
        height=1400,
    ),
    RenderTarget("mix.bar", "mix_all/bar.html", "mix_bar.png"),
    RenderTarget("mix.column", "mix_all/column_total.html", "mix_column.png"),
    RenderTarget(
        "mix.column_overlay",
        "mix_all/column_total_with_overlay.html",
        "mix_column_overlay.png",
    ),
    RenderTarget(
        "mix.stacked_bar",
        "mix_all/stacked_bar.html",
        "mix_stacked_bar.png",
    ),
    RenderTarget(
        "mix.stacked_bar_overlay",
        "mix_all/related_metrics_bar.html",
        "mix_stacked_bar_overlay.png",
    ),
    RenderTarget("mix.timeline", "mix_all/line.html", "mix_timeline.png"),
    RenderTarget("mix.area", "mix_all/area_absolute.html", "mix_area.png"),
    RenderTarget("mix.barmekko", "mix_all/barmekko.html", "mix_barmekko.png"),
    RenderTarget("mix.marimekko", "mix_all/marimekko.html", "mix_marimekko.png"),
    RenderTarget("mix.pareto", "mix_all/pareto.html", "mix_pareto.png"),
    RenderTarget(
        "mix.stacked_pareto",
        "mix_all/stacked_pareto_abc.html",
        "mix_stacked_pareto.png",
    ),
    RenderTarget(
        "mix.stacked_column",
        "mix_stacked_column/stacked_column.html",
        "mix_stacked_column.png",
    ),
    RenderTarget("scatter.scatter", "scatter/scatter.html", "scatter_scatter.png"),
    RenderTarget("scatter.bubble", "scatter/bubble.html", "scatter_bubble.png"),
    RenderTarget(
        "distribution.histogram",
        "distribution/histogram.html",
        "distribution_histogram.png",
    ),
    RenderTarget(
        "set_overlap.upset_small_multiples",
        "set_overlap/upset_small_multiples.html",
        "set_overlap_upset_small_multiples.png",
        width=1800,
        height=1200,
    ),
    RenderTarget(
        "variance.scenario_bridge",
        "variance/waterfall.png",
        "variance_scenario_bridge.png",
        source_kind="png",
    ),
    RenderTarget(
        "variance.total_by_dimension_bridge",
        "variance/total_by_dimension_bridge.png",
        "variance_total_by_dimension_bridge.png",
        source_kind="png",
    ),
    RenderTarget(
        "variance.exploded_variance_bridge",
        "variance/exploded_variance_bridge.png",
        "variance_exploded_variance_bridge.png",
        source_kind="png",
    ),
    RenderTarget(
        "variance.root_cause_exploded_bridge",
        "variance/root_cause_total_bridge.png",
        "variance_root_cause_exploded_bridge.png",
        source_kind="png_pair",
        secondary_source_relative_path="variance/root_cause_bridge_alt_1_drilldown_row_1.png",
    ),
    RenderTarget(
        "variance.price_volume_mix",
        "variance/pvm_decomposition_ladder.png",
        "variance_price_volume_mix.png",
        source_kind="png",
    ),
    RenderTarget(
        "variance.root_cause_total_bridge",
        "variance/root_cause_total_bridge.png",
        "variance_root_cause_total_bridge.png",
        source_kind="png",
    ),
    RenderTarget(
        "variance.root_cause_component_bridge",
        "variance/root_cause_component_bridge.png",
        "variance_root_cause_component_bridge.png",
        source_kind="png",
    ),
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _wait_for_chart_surface(page: Any) -> None:
    try:
        page.wait_for_selector(
            ".plotly-graph-div, svg, canvas, main, body",
            timeout=15_000,
        )
    except PlaywrightTimeoutError:
        LOGGER.warning("No chart selector found before timeout; capturing page anyway.")
    page.wait_for_timeout(1_500)


def _trim_white_border(path: Path, *, margin: int = 24) -> dict[str, Any]:
    image = Image.open(path).convert("RGB")
    width, height = image.size
    pixels = image.load()
    left = width
    top = height
    right = -1
    bottom = -1
    for y in range(height):
        for x in range(width):
            red, green, blue = pixels[x, y]
            if red < 248 or green < 248 or blue < 248:
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)
    if right < left or bottom < top:
        return {
            "trimmed": False,
            "original_size": [width, height],
            "trimmed_size": [width, height],
        }
    crop_box = (
        max(0, left - margin),
        max(0, top - margin),
        min(width, right + margin + 1),
        min(height, bottom + margin + 1),
    )
    if crop_box == (0, 0, width, height):
        return {
            "trimmed": False,
            "original_size": [width, height],
            "trimmed_size": [width, height],
        }
    trimmed = image.crop(crop_box)
    trimmed.save(path)
    return {
        "trimmed": True,
        "original_size": [width, height],
        "trimmed_size": [trimmed.width, trimmed.height],
        "crop_box": list(crop_box),
    }


def _screenshot_html(
    *,
    browser_context: Any,
    html_path: Path,
    png_path: Path,
    width: int,
    height: int,
) -> dict[str, Any]:
    page = browser_context.new_page()
    page.set_viewport_size({"width": width, "height": height})
    try:
        page.goto(html_path.resolve().as_uri(), wait_until="domcontentloaded")
        _wait_for_chart_surface(page)
        page.screenshot(path=str(png_path), full_page=True)
    finally:
        page.close()
    if not png_path.exists() or png_path.stat().st_size == 0:
        raise RuntimeError(f"Screenshot was not written: {png_path}")
    return {
        "renderer": "visible_chrome_cdp_playwright_screenshot",
        "width": width,
        "height": height,
    }


def _copy_png(source_path: Path, png_path: Path) -> dict[str, Any]:
    shutil.copy2(source_path, png_path)
    if not png_path.exists() or png_path.stat().st_size == 0:
        raise RuntimeError(f"PNG was not copied: {png_path}")
    return {"renderer": "plugin_png_copy"}


def _compose_png_pair(
    parent_path: Path, drilldown_path: Path, png_path: Path
) -> dict[str, Any]:
    parent = Image.open(parent_path).convert("RGB")
    drilldown = Image.open(drilldown_path).convert("RGB")
    gap = 80
    margin = 40
    canvas_width = parent.width + drilldown.width + gap + (margin * 2)
    canvas_height = max(parent.height, drilldown.height) + (margin * 2)
    image = Image.new("RGB", (canvas_width, canvas_height), "white")
    parent_xy = (margin, margin)
    drilldown_xy = (margin + parent.width + gap, margin)
    image.paste(parent, parent_xy)
    image.paste(drilldown, drilldown_xy)

    draw = ImageDraw.Draw(image)
    y = margin + int(parent.height * 0.32)
    x0 = margin + parent.width + 10
    x1 = drilldown_xy[0] - 10
    mid_x = (x0 + x1) // 2
    draw.line((x0, y, mid_x, y, mid_x, y + 30, x1, y + 30), fill="#2D5BB8", width=3)
    draw.polygon(
        [(x1, y + 30), (x1 - 12, y + 23), (x1 - 12, y + 37)],
        fill="#2D5BB8",
    )

    image.save(png_path)
    if not png_path.exists() or png_path.stat().st_size == 0:
        raise RuntimeError(f"Composite PNG was not written: {png_path}")
    return {"renderer": "plugin_png_pair_composite"}


def _existing_written_outputs(output_root: Path) -> dict[str, dict[str, Any]]:
    manifest_path = output_root / "manifest.json"
    if not manifest_path.exists():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    outputs = {}
    for item in manifest.get("outputs", []):
        capability_id = item.get("capability_id")
        if capability_id and item.get("status") == "written":
            outputs[str(capability_id)] = item
    return outputs


def render_cosmetics_question_png_assets(
    *,
    source_root: Path = DEFAULT_SOURCE_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    remote_url: str = DEFAULT_REMOTE_URL,
    browser_mode: str = DEFAULT_BROWSER_MODE,
    reuse_existing_html: bool = False,
) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    png_dir = output_root / "png"
    png_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[dict[str, Any]] = []
    existing_outputs = (
        _existing_written_outputs(output_root) if reuse_existing_html else {}
    )

    html_targets = [target for target in TARGETS if target.source_kind == "html"]
    html_targets_to_render = [
        target
        for target in html_targets
        if not (reuse_existing_html and target.capability_id in existing_outputs)
    ]
    playwright_context = sync_playwright() if html_targets_to_render else None
    browser = None
    context = None
    if playwright_context:
        playwright = playwright_context.__enter__()
        if browser_mode == "launch":
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
        else:
            browser = playwright.chromium.connect_over_cdp(remote_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
    try:
        for target in TARGETS:
            if reuse_existing_html and target.capability_id in existing_outputs:
                outputs.append(existing_outputs[target.capability_id])
                continue
            source_path = source_root / target.source_relative_path
            png_path = png_dir / target.output_name
            entry: dict[str, Any] = {
                "capability_id": target.capability_id,
                "source_path": str(source_path),
                "source_kind": target.source_kind,
                "png_path": str(png_path),
                "png_relative_path": str(png_path.relative_to(output_root)),
                "status": "pending",
            }
            if (
                reuse_existing_html
                and png_path.exists()
                and png_path.stat().st_size > 0
            ):
                entry.update(
                    {
                        "status": "written",
                        "renderer": "existing_png_reuse",
                        "size_bytes": png_path.stat().st_size,
                        "reuse_reason": "source_missing_or_not_rerendered",
                    }
                )
                outputs.append(entry)
                continue
            try:
                if not source_path.exists():
                    raise FileNotFoundError(source_path)
                if target.source_kind == "html":
                    if context is None:
                        raise RuntimeError(
                            "No browser context available for HTML rendering"
                        )
                    render_info = _screenshot_html(
                        browser_context=context,
                        html_path=source_path,
                        png_path=png_path,
                        width=target.width,
                        height=target.height,
                    )
                elif target.source_kind == "png_pair":
                    if target.secondary_source_relative_path is None:
                        raise ValueError(
                            "png_pair target requires a secondary source path"
                        )
                    secondary_path = source_root / target.secondary_source_relative_path
                    if not secondary_path.exists():
                        raise FileNotFoundError(secondary_path)
                    render_info = _compose_png_pair(
                        source_path,
                        secondary_path,
                        png_path,
                    )
                else:
                    render_info = _copy_png(source_path, png_path)
                render_info["postprocess"] = _trim_white_border(png_path)
                entry.update(render_info)
                entry["status"] = "written"
                entry["size_bytes"] = png_path.stat().st_size
                LOGGER.info("Wrote %s", png_path)
            except Exception as exc:  # noqa: BLE001 - manifest records failures.
                entry["status"] = "failed"
                entry["error"] = str(exc)
                LOGGER.error("Failed to render %s: %s", target.capability_id, exc)
            outputs.append(entry)
    finally:
        if browser is not None:
            browser.close()
        if playwright_context is not None:
            playwright_context.__exit__(None, None, None)

    manifest = {
        "schema_version": "1.0",
        "dataset": "us_cosmetics",
        "source_root": str(source_root),
        "output_root": str(output_root),
        "remote_url": remote_url,
        "requested_count": len(TARGETS),
        "html_screenshot_count": len(html_targets),
        "written_count": sum(1 for item in outputs if item["status"] == "written"),
        "failed_count": sum(1 for item in outputs if item["status"] != "written"),
        "outputs": outputs,
    }
    manifest_path = output_root / "manifest.json"
    _write_json(manifest_path, manifest)
    if manifest["failed_count"]:
        raise RuntimeError(f"{manifest['failed_count']} PNG assets failed to render.")
    return manifest_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render cosmetics question-review chart HTML artifacts to PNG.",
    )
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--remote-url", default=DEFAULT_REMOTE_URL)
    parser.add_argument(
        "--browser-mode",
        choices=("cdp", "launch"),
        default=DEFAULT_BROWSER_MODE,
        help="Use a running Chrome CDP endpoint or launch Playwright Chromium.",
    )
    parser.add_argument(
        "--reuse-existing-html",
        action="store_true",
        help="Reuse already written HTML screenshots and render only PNG targets.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
    args = _parse_args()
    manifest_path = render_cosmetics_question_png_assets(
        source_root=args.source_root,
        output_root=args.output_root,
        remote_url=args.remote_url,
        browser_mode=args.browser_mode,
        reuse_existing_html=args.reuse_existing_html,
    )
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
