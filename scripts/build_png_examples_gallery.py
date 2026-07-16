from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import shutil
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from html import escape, unescape
from pathlib import Path
from typing import Any

from PIL import Image
from playwright.sync_api import Browser, sync_playwright

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WIDTH = 1600
DEFAULT_HEIGHT = 1000
MAX_VIEWPORT_WIDTH = 5000
MAX_VIEWPORT_HEIGHT = 5000
PLOTLY_DIV_SELECTOR = ".plotly-graph-div"
EXPLICIT_HTML_ARTIFACT_SELECTOR = "[data-gallery-screenshot]"
HTML_ARTIFACT_SELECTOR = "[data-gallery-screenshot], .page"
HIGH_EDGE_INK_RATIO = 0.02
HIGH_CROP_RISK_INK_RATIO = HIGH_EDGE_INK_RATIO
LOW_NON_WHITE_RATIO = 0.005
SPARSE_RENDERED_GRAMMAR_TOKENS = ("dot", "scatter", "stripplot")
PLUGIN_SOURCE_LABELS = {
    "distribution-analysis": "Distribution Analysis",
    "mix-contribution-analysis": "Mix & Contribution Analysis",
    "period-comparison": "Period Comparison",
    "funnel-analysis": "Funnel Analysis",
    "statement-analysis": "Statement Analysis",
    "scatter-bubble-analysis": "Scatter & Bubble Analysis",
    "set-overlap-analysis": "Set Overlap Analysis",
    "variance-analysis": "Variance Analysis",
    "attribute-tables": "Attribute Tables",
}
SOURCE_FAMILY_LABELS = {
    "movement-source": "Movement and period sources",
    "composition-source": "Mix and composition sources",
    "relationship-source": "Relationship, spread and overlap sources",
    "table-source": "Structured table sources",
}
SOURCE_FAMILY_ORDER = tuple(SOURCE_FAMILY_LABELS)
PLUGIN_SOURCE_FAMILIES = {
    "variance-analysis": "movement-source",
    "period-comparison": "movement-source",
    "mix-contribution-analysis": "composition-source",
    "scatter-bubble-analysis": "relationship-source",
    "distribution-analysis": "relationship-source",
    "set-overlap-analysis": "relationship-source",
    "funnel-analysis": "table-source",
    "statement-analysis": "table-source",
    "attribute-tables": "table-source",
}
PLUGIN_SOURCE_ORDER = (
    "variance-analysis",
    "period-comparison",
    "mix-contribution-analysis",
    "scatter-bubble-analysis",
    "distribution-analysis",
    "set-overlap-analysis",
    "funnel-analysis",
    "statement-analysis",
    "attribute-tables",
)
CAPABILITY_PREFIX_PLUGIN_SOURCES = {
    "attributes": "attribute-tables",
    "distribution": "distribution-analysis",
    "mix": "mix-contribution-analysis",
    "period_comparison": "period-comparison",
    "funnel": "funnel-analysis",
    "statement": "statement-analysis",
    "scatter": "scatter-bubble-analysis",
    "set_overlap": "set-overlap-analysis",
    "variance": "variance-analysis",
}
RUN_PREFIX_PLUGIN_SOURCES = {
    "attributes": "attribute-tables",
    "distribution": "distribution-analysis",
    "mix": "mix-contribution-analysis",
    "period": "period-comparison",
    "funnel": "funnel-analysis",
    "statement": "statement-analysis",
    "scatter": "scatter-bubble-analysis",
    "set_overlap": "set-overlap-analysis",
    "variance": "variance-analysis",
}
DEFAULT_EXCLUDE_FILTERS = (
    # mix_regular is the old umbrella recipe: most current-period charts duplicate
    # mix_current, and most comparison/time charts duplicate mix_comparison. Keep
    # first-class chart capabilities represented at least once in the gallery.
    # Keep the regular stacked-column cards because there is no non-regular
    # gallery route for those chart variants, and keep current-period stacked bars
    # because the comparison recipe also contains plain and marker-overlay bars.
    "mix_regular / stacked_column_synthesis",
    "mix_current / mix_regular / related_metrics_bar",
    "mix_current / mix_regular / stacked_column",
    # mix_multitier_bar is a focused duplicate of mix_comparison's multitier
    # examples; keep one route to the same source artifacts in the review inventory.
    "mix_multitier_bar /",
    "mix_multitier_bar_dimension_panels /",
    # Focused stacked-column synthesis recipe duplicates the mix_comparison
    # synthesis card.
    "mix_stacked_column_synthesis /",
    "mix_cohort_brand /",
    "mix_cohort_product /",
    "mix_comparison / related_metrics_bar_small_multiples_1",
    "mix_comparison / related_metrics_bar_small_multiples_2",
    " / multitier_bar_2",
    " / multitier_bar_3",
    " / multitier_bar_4",
    # Root-cause alternative bridges are instances of one variable-dimension
    # sweep. Keep the sweep context and canonical bridge, not ten separate cards.
    "variance / root_cause_bridge_alt_",
    # Client-report root-cause PNGs are report illustrations, not canonical
    # source artifacts. Keep the capability-owned bridge/drilldown artifacts.
    "variance / root_cause_client_report_",
    # Static plugin documentation examples are not plugin-generated gallery
    # artifacts.
    "variance-analysis / examples /",
    "period-comparison / examples /",
)
DEFAULT_EXACT_EXCLUDE_LABELS: tuple[str, ...] = (
    "period / year_over_year_line_small_multiples",
)
DISPLAY_LABEL_RENAMES = {
    "mix_comparison / mix_regular / area_absolute": "mix_comparison / area_absolute",
    "mix_comparison / mix_regular / area_share": "mix_comparison / area_share",
    "mix_comparison / mix_regular / line": "mix_comparison / line",
    "mix_comparison / mix_regular / line_small_multiples": (
        "mix_comparison / line_small_multiples"
    ),
    "mix_current / mix_regular / area_absolute": "mix_current / area_absolute",
    "mix_current / mix_regular / area_share": "mix_current / area_share",
    "mix_current / mix_regular / barmekko": "mix_current / barmekko",
    "mix_current / mix_regular / barmekko_small_multiples": (
        "mix_current / barmekko_small_multiples"
    ),
    "mix_current / mix_regular / line": "mix_current / line",
    "mix_current / mix_regular / line_small_multiples": (
        "mix_current / line_small_multiples"
    ),
    "mix_current / mix_regular / marimekko": "mix_current / marimekko",
    "mix_current / mix_regular / marimekko_small_multiples": (
        "mix_current / marimekko_small_multiples"
    ),
    "mix_current / mix_regular / pareto": "mix_current / pareto",
    "mix_current / mix_regular / stacked_pareto_abc": (
        "mix_current / stacked_pareto_abc"
    ),
    "mix_current / mix_regular / stacked_pareto_by_dimension": (
        "mix_current / stacked_pareto_by_dimension"
    ),
    "mix_current / mix_regular / stacked_bar": "mix_current / stacked_bar",
    "mix_current / mix_regular / stacked_bar_small_multiples": (
        "mix_current / stacked_bar_small_multiples"
    ),
    "period / year_over_year_by_period": ("period / year_over_year_by_recency_window"),
    "period / year_over_year_by_period_small_multiples": (
        "period / year_over_year_by_recency_window_small_multiples"
    ),
}
SOURCE_LABEL_RENAMES = {value: key for key, value in DISPLAY_LABEL_RENAMES.items()}


@dataclass(frozen=True)
class ArtifactDimensions:
    width: int
    height: int


@dataclass(frozen=True)
class GalleryItem:
    source_path: Path
    output_path: Path
    label: str
    dimensions: ArtifactDimensions | None


@dataclass(frozen=True)
class ImageStats:
    width: int
    height: int
    byte_count: int
    non_white_ratio: float
    edge_ink_ratio: float
    crop_risk_ink_ratio: float = 0.0
    top_edge_ink_ratio: float = 0.0
    right_edge_ink_ratio: float = 0.0
    bottom_edge_ink_ratio: float = 0.0
    left_edge_ink_ratio: float = 0.0


@dataclass(frozen=True)
class SidecarLink:
    label: str
    path: Path


@dataclass(frozen=True)
class ContextSummary:
    grammar: str | None
    metrics: str | None
    dimensions: str | None
    periods: str | None
    trace_widths: str | None
    capability: str | None = None
    source_reference: str | None = None


@dataclass(frozen=True)
class QualityFlag:
    label: str
    detail: str


REQUIRED_ARTIFACT_SIDECARS = (
    "source",
    "context",
    "data",
    "manifest",
    "recipe",
)
DATA_ARTIFACT_SUFFIXES = {".csv", ".json", ".xlsx"}
FALLBACK_DATA_FILENAMES = (
    "distribution_summary.csv",
    "mix_contribution_summary.csv",
    "period_comparison_by_period.csv",
    "period_comparison_monthly.csv",
    "scatter_bubble_summary.csv",
    "set_overlap_set_summary.csv",
    "variance_results.csv",
    "waterfall_small_multiples_summary.csv",
    "root_cause_sweep_summary.csv",
)
PREFERRED_FALLBACK_DATA_FILENAMES = {
    "waterfall": ("variance_results.csv",),
    "waterfall_small_multiples": ("waterfall_small_multiples_summary.csv",),
}
ARTIFACT_CONTRACT_KEYS = (
    "object_type",
    "chart_spec_names",
    "table_spec_names",
    "preferred_chart_spec_name",
    "visual_family",
    "selection_guidance",
    "artifact_selection_guidance",
    "metric_requirements",
    "metric_relationships",
    "dimension_contract",
    "legacy_chartdict_contract",
    "native_table_contract",
    "artifact_request_contract",
    "render_variants",
)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build review PNGs from plugin-owned PNG/HTML artifacts under "
            "runs/png_examples."
        )
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("runs/png_examples"),
        help="Root containing plugin example artifacts.",
    )
    parser.add_argument(
        "--gallery-dir",
        type=Path,
        default=Path("runs/png_examples/png-gallery"),
        help="Directory where review PNGs and index.html are written.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Optional substring filter; can be passed more than once.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=list(DEFAULT_EXCLUDE_FILTERS),
        help=(
            "Optional substring exclusion filter; can be passed more than once. "
            "Defaults suppress duplicate or misleading review-only examples."
        ),
    )
    parser.add_argument(
        "--include-default-excluded",
        action="store_true",
        help="Render examples that are normally suppressed from the review gallery.",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=1_500,
        help="Milliseconds to wait after loading each Plotly HTML artifact.",
    )
    parser.add_argument(
        "--include-source-pack",
        action="store_true",
        help="Include duplicate chart HTML artifacts stored inside source_pack folders.",
    )
    parser.add_argument(
        "--include-review-html",
        action="store_true",
        help="Include review/widget HTML pages rather than only chart artifacts.",
    )
    parser.add_argument(
        "--include-drilldowns",
        action="store_true",
        help="Include drilldown chart artifacts generated by diagnostic workflows.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level.",
    )
    return parser.parse_args(argv)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _audit_dimensions(source_root: Path) -> dict[Path, ArtifactDimensions]:
    dimensions: dict[Path, ArtifactDimensions] = {}
    for audit_path in _iter_audit_json_paths(source_root):
        try:
            payload = _load_json(audit_path)
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Skipping unreadable audit %s: %s", audit_path, exc)
            continue
        for item in _walk_dicts(payload):
            width = _positive_int(item.get("export_width"))
            height = _positive_int(item.get("export_height"))
            if width is None or height is None:
                continue
            for key in ("artifact", "html_artifact"):
                artifact_name = item.get(key)
                if not isinstance(artifact_name, str) or not artifact_name.strip():
                    continue
                artifact_path = (audit_path.parent / artifact_name).resolve()
                dimensions[artifact_path] = ArtifactDimensions(width, height)
    return dimensions


def _iter_audit_json_paths(source_root: Path) -> Iterable[Path]:
    for audit_path in source_root.rglob("*.json"):
        if _is_gallery_path(audit_path):
            continue
        if not (
            audit_path.name.endswith("_audit.json")
            or audit_path.name == "final_artifacts.json"
        ):
            continue
        yield audit_path


def _current_artifacts(source_root: Path) -> set[Path]:
    artifact_paths: set[Path] = set()
    for audit_path in _iter_audit_json_paths(source_root):
        try:
            payload = _load_json(audit_path)
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Skipping unreadable audit %s: %s", audit_path, exc)
            continue
        for item in _walk_dicts(payload):
            for key in ("artifact", "html_artifact", "path"):
                artifact_name = item.get(key)
                if not isinstance(artifact_name, str):
                    continue
                if Path(artifact_name).suffix.lower() in {".html", ".png"}:
                    artifact_paths.add((audit_path.parent / artifact_name).resolve())
    artifact_paths.update(_current_source_artifacts(source_root))
    return artifact_paths


def _current_source_artifacts(source_root: Path) -> set[Path]:
    artifact_paths: set[Path] = set()
    for manifest_path in _iter_source_manifest_paths(source_root):
        try:
            artifacts = _source_manifest_artifacts(manifest_path)
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning(
                "Skipping unreadable source manifest %s: %s", manifest_path, exc
            )
            continue
        run_dir = manifest_path.parent.parent
        for artifact in artifacts:
            artifact_paths.update(_source_artifact_source_paths(run_dir, artifact))
    return artifact_paths


def _iter_source_manifest_paths(source_root: Path) -> Iterable[Path]:
    for manifest_path in source_root.rglob("source_pack/manifest.json"):
        if not _is_gallery_path(manifest_path):
            yield manifest_path


def _source_artifact_source_paths(
    run_dir: Path,
    artifact: dict[str, Any],
) -> set[Path]:
    paths: set[Path] = set()
    for candidate in (
        artifact.get("path"),
        artifact.get("source_path"),
        artifact.get("pack_path"),
    ):
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        candidate_path = Path(candidate)
        if candidate_path.suffix.lower() not in {".html", ".png"}:
            continue
        for base_dir in (run_dir, run_dir / "source_pack"):
            resolved_path = (base_dir / candidate_path).resolve()
            if resolved_path.exists():
                paths.add(resolved_path)
    return paths


def _current_html_artifacts(source_root: Path) -> set[Path]:
    return {
        path
        for path in _current_artifacts(source_root)
        if path.suffix.lower() == ".html"
    }


def _is_gallery_path(path: Path) -> bool:
    return any(
        (normalized_part := part.replace("_", "-")) == "png-gallery"
        or normalized_part.startswith("png-gallery-")
        or normalized_part.startswith(".png-gallery")
        for part in path.parts
    )


def _positive_int(value: Any) -> int | None:
    try:
        integer = int(value)
    except (TypeError, ValueError):
        return None
    return integer if integer > 0 else None


def _html_dimensions(path: Path) -> ArtifactDimensions | None:
    try:
        html = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    layout_width = _first_int_match(html, r'"width"\s*:\s*(\d{3,5})')
    layout_height = _first_int_match(html, r'"height"\s*:\s*(\d{3,5})')
    if layout_width and layout_height:
        return ArtifactDimensions(layout_width, layout_height)

    style_height = _first_int_match(html, r"height:\s*(\d{3,5})px")
    style_width = _first_int_match(html, r"width:\s*(\d{3,5})px")
    if style_width and style_height:
        return ArtifactDimensions(style_width, style_height)

    return None


def _first_int_match(text: str, pattern: str) -> int | None:
    match = re.search(pattern, text)
    if match is None:
        return None
    return _positive_int(match.group(1))


def _gallery_output_name(source_root: Path, source_path: Path) -> str:
    relative_parts = _gallery_relative_parts(source_root, source_path)
    parent = "__".join(relative_parts[:-1])
    stem = source_path.stem
    return f"{parent}__{stem}.png" if parent else f"{stem}.png"


def _is_native_reporting_table_html(path: Path) -> bool:
    """Return whether an HTML artifact is a first-class reporting table."""

    return path.suffix.lower() == ".html" and path.stem.endswith("_table")


def _is_default_gallery_html_artifact(path: Path) -> bool:
    """Return whether an HTML file is a chart/table artifact for the PNG gallery."""

    if path.suffix.lower() != ".html":
        return False
    if _is_native_reporting_table_html(path):
        return True
    try:
        html = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        LOGGER.warning("Skipping unreadable HTML artifact %s: %s", path, exc)
        return False
    return "Plotly.newPlot" in html or "data-gallery-screenshot" in html


def _gallery_label(source_root: Path, source_path: Path) -> str:
    relative_parts = _gallery_relative_parts(source_root, source_path)
    parent = " / ".join(relative_parts[:-1])
    label = f"{parent} / {source_path.stem}" if parent else source_path.stem
    return _display_gallery_label(label)


def _display_gallery_label(label: str) -> str:
    return DISPLAY_LABEL_RENAMES.get(label, label)


def _source_gallery_label(label: str) -> str:
    return SOURCE_LABEL_RENAMES.get(label, label)


def _gallery_relative_parts(source_root: Path, source_path: Path) -> tuple[str, ...]:
    """Return gallery path parts without duplicated run folder names."""

    parts = source_path.relative_to(source_root).parts
    if len(parts) >= 3 and parts[0] == parts[1]:
        return (parts[0], *parts[2:])
    return parts


def _iter_source_artifacts(
    source_root: Path,
    gallery_dir: Path,
    dimensions: dict[Path, ArtifactDimensions],
    filters: Sequence[str],
    include_source_pack: bool,
    include_review_html: bool,
    include_drilldowns: bool,
    exclude_filters: Sequence[str] = (),
    exact_exclude_labels: Sequence[str] = (),
) -> list[GalleryItem]:
    preferred_artifacts = _current_artifacts(source_root)
    current_run_dirs = {path.parent for path in preferred_artifacts}
    native_pngs = {
        path.resolve()
        for path in source_root.rglob("*.png")
        if not _is_gallery_path(path)
        and not _is_default_skipped_artifact(
            path,
            include_source_pack=include_source_pack,
            include_review_html=include_review_html,
            include_drilldowns=include_drilldowns,
        )
    }
    preferred_htmls = {
        path
        for path in preferred_artifacts
        if path.suffix.lower() == ".html"
        and (
            path.with_suffix(".png") not in preferred_artifacts
            or _is_native_reporting_table_html(path)
        )
    }
    stale_pngs_with_preferred_html = {
        html_path.with_suffix(".png") for html_path in preferred_htmls
    }
    items: list[GalleryItem] = []
    for source_path in sorted(source_root.rglob("*")):
        if not source_path.is_file() or _is_gallery_path(source_path):
            continue
        if _is_default_skipped_artifact(
            source_path,
            include_source_pack=include_source_pack,
            include_review_html=include_review_html,
            include_drilldowns=include_drilldowns,
        ):
            continue
        if source_path.suffix.lower() not in {".png", ".html"}:
            continue
        if (
            source_path.parent.resolve() in current_run_dirs
            and source_path.resolve() not in preferred_artifacts
        ):
            continue
        if source_path.resolve() in stale_pngs_with_preferred_html:
            continue
        if (
            source_path.suffix.lower() == ".html"
            and source_path.with_suffix(".png").resolve() in native_pngs
            and source_path.resolve() not in preferred_htmls
        ):
            continue
        label = _gallery_label(source_root, source_path)
        if exact_exclude_labels and label in exact_exclude_labels:
            continue
        if filters and not any(token in label for token in filters):
            continue
        if exclude_filters and any(token in label for token in exclude_filters):
            continue
        output_path = gallery_dir / _gallery_output_name(source_root, source_path)
        item_dimensions = dimensions.get(source_path.resolve())
        if item_dimensions is None and source_path.suffix.lower() == ".html":
            item_dimensions = _html_dimensions(source_path)
        items.append(
            GalleryItem(
                source_path=source_path,
                output_path=output_path,
                label=label,
                dimensions=item_dimensions,
            )
        )
    return items


def _artifact_dedupe_key(item: GalleryItem) -> str | None:
    """Return the canonical artifact key for duplicate gallery pruning."""

    record = _source_record_for_item(item)
    artifact = record[1] if record is not None else None
    artifact_id = _record_value(artifact, "artifact_id")
    if isinstance(artifact_id, str) and artifact_id.strip():
        return artifact_id.strip()
    path_value = _record_value(artifact, "path") or _record_value(
        artifact, "source_path"
    )
    if isinstance(path_value, str) and path_value.strip():
        return path_value.strip()
    return None


def _dedupe_gallery_items(items: Sequence[GalleryItem]) -> list[GalleryItem]:
    """Keep one review card per plugin-owned source artifact."""

    deduped: list[GalleryItem] = []
    seen_artifacts: dict[str, GalleryItem] = {}
    for item in items:
        artifact_key = _artifact_dedupe_key(item)
        if artifact_key is None:
            deduped.append(item)
            continue
        existing = seen_artifacts.get(artifact_key)
        if existing is not None:
            LOGGER.info(
                "Skipping duplicate gallery artifact %s: %s duplicates %s",
                artifact_key,
                item.label,
                existing.label,
            )
            continue
        seen_artifacts[artifact_key] = item
        deduped.append(item)
    return deduped


def _plugin_source_id(item: GalleryItem) -> str:
    """Return the plugin source that owns a gallery item."""

    source_record = _source_record_for_item(item)
    manifest_path = source_record[0] if source_record is not None else None
    artifact = source_record[1] if source_record is not None else None
    plugin = _record_value(artifact, "plugin")
    if not isinstance(plugin, str) or not plugin:
        plugin = _source_manifest_plugin(manifest_path) if manifest_path else None
    if isinstance(plugin, str) and plugin:
        return plugin

    capability_id = _record_value(artifact, "capability_id") or _infer_capability_id(
        item,
        manifest_path,
        artifact,
    )
    if isinstance(capability_id, str) and "." in capability_id:
        prefix = capability_id.split(".", 1)[0]
        plugin_source = CAPABILITY_PREFIX_PLUGIN_SOURCES.get(prefix)
        if plugin_source:
            return plugin_source

    run_name = item.label.split(" / ", 1)[0]
    for prefix, plugin_source in RUN_PREFIX_PLUGIN_SOURCES.items():
        if run_name == prefix or run_name.startswith(f"{prefix}_"):
            return plugin_source
    return run_name


def _plugin_source_label(plugin_source: str) -> str:
    return PLUGIN_SOURCE_LABELS.get(plugin_source, plugin_source.replace("-", " "))


def _source_family_id(plugin_source: str) -> str:
    return PLUGIN_SOURCE_FAMILIES.get(plugin_source, plugin_source)


def _source_family_label(source_family: str) -> str:
    return SOURCE_FAMILY_LABELS.get(
        source_family,
        source_family.replace("-", " "),
    )


def _source_family_sort_index(source_family: str) -> int:
    try:
        return SOURCE_FAMILY_ORDER.index(source_family)
    except ValueError:
        return len(SOURCE_FAMILY_ORDER)


def _plugin_source_sort_index(plugin_source: str) -> int:
    try:
        return PLUGIN_SOURCE_ORDER.index(plugin_source)
    except ValueError:
        return len(PLUGIN_SOURCE_ORDER)


def _gallery_artifact_sort_group(item: GalleryItem) -> int:
    """Keep first-class table variants adjacent inside a plugin section."""

    return 0 if _is_native_reporting_table_html(item.source_path) else 1


MIX_GALLERY_STEM_ORDER = {
    "bar": 0,
    "stacked_bar": 0,
    "bar_small_multiples": 1,
    "stacked_bar_small_multiples": 1,
    "related_metrics_bar": 2,
    "related_metrics_bar_small_multiples": 3,
    "multitier_bar": 4,
    "multitier_bar_dimension_panels": 5,
    "multitier_bar_two_dimension": 6,
    "column_total": 7,
    "column_total_with_overlay": 8,
    "like_for_like_column_total": 9,
    "stacked_column": 10,
    "stacked_column_small_multiples": 11,
    "like_for_like_stacked_column": 12,
    "stacked_column_synthesis": 13,
    "cohort_since_stacked_column": 14,
    "cohort_lost_stacked_column": 15,
    "line": 17,
    "line_small_multiples": 18,
    "area_absolute": 19,
    "area_share": 20,
    "barmekko": 21,
    "barmekko_small_multiples": 22,
    "marimekko": 23,
    "marimekko_small_multiples": 24,
    "pareto": 25,
    "stacked_pareto_abc": 26,
    "stacked_pareto_by_dimension": 27,
}


PERIOD_GALLERY_STEM_ORDER = {
    "comparison_table": 0,
    "time_series_table": 1,
    "year_over_year_by_period": 2,
    "year_over_year_by_recency_window": 2,
    "year_over_year_by_period_small_multiples": 3,
    "year_over_year_by_recency_window_small_multiples": 3,
    "year_over_year_column": 4,
    "year_over_year_column_small_multiples": 5,
    "year_over_year_line": 6,
    "year_over_year_small_multiples": 7,
    "year_over_year_waterfall": 8,
    "year_over_year_waterfall_small_multiples": 9,
    "year_over_year_dot": 10,
    "year_over_year_dot_small_multiples": 11,
    "year_over_year_slope": 12,
    "year_over_year_slope_small_multiples": 13,
}


VARIANCE_GALLERY_STEM_ORDER = {
    "waterfall": 0,
    "waterfall_small_multiples": 1,
    "pvm_decomposition_ladder": 2,
    "total_by_dimension_bridge": 3,
    "root_cause_total_bridge": 4,
    "root_cause_component_bridge": 5,
    "exploded_variance_bridge": 6,
    "root_cause_exploded_bridge": 7,
    "root_cause_total_bridge_drilldown_row_1": 8,
}


def _mix_gallery_sort_key(item: GalleryItem) -> tuple[int, str]:
    """Keep related mix chart families adjacent in review galleries."""

    group, separator, stem = item.label.partition(" / ")
    if not separator or not group.startswith("mix_"):
        return (len(MIX_GALLERY_STEM_ORDER), "")
    return (MIX_GALLERY_STEM_ORDER.get(stem, len(MIX_GALLERY_STEM_ORDER)), item.label)


def _period_gallery_sort_key(item: GalleryItem) -> tuple[int, str]:
    """Keep period chart variants in report-review order."""

    group, separator, stem = item.label.partition(" / ")
    if not separator or group != "period":
        return (len(PERIOD_GALLERY_STEM_ORDER), "")
    return (
        PERIOD_GALLERY_STEM_ORDER.get(stem, len(PERIOD_GALLERY_STEM_ORDER)),
        item.label,
    )


def _variance_gallery_sort_key(item: GalleryItem) -> tuple[int, str]:
    """Keep the two exploded bridge examples last and adjacent."""

    group, separator, stem = item.label.partition(" / ")
    if not separator or group != "variance":
        return (len(VARIANCE_GALLERY_STEM_ORDER), "")
    return (
        VARIANCE_GALLERY_STEM_ORDER.get(stem, len(VARIANCE_GALLERY_STEM_ORDER)),
        item.label,
    )


def _sort_gallery_items(items: Sequence[GalleryItem]) -> list[GalleryItem]:
    """Sort review cards by source family, plugin source, then label."""

    def sort_key(
        item: GalleryItem,
    ) -> tuple[
        int,
        int,
        str,
        int,
        tuple[int, str],
        tuple[int, str],
        tuple[int, str],
        str,
        str,
    ]:
        plugin_source = _plugin_source_id(item)
        source_family = _source_family_id(plugin_source)
        summary = _context_summary(item)
        capability = summary.capability if summary is not None else ""
        return (
            _source_family_sort_index(source_family),
            _plugin_source_sort_index(plugin_source),
            _plugin_source_label(plugin_source),
            _gallery_artifact_sort_group(item),
            _mix_gallery_sort_key(item),
            _period_gallery_sort_key(item),
            _variance_gallery_sort_key(item),
            capability or "",
            item.label,
        )

    return sorted(items, key=sort_key)


def _is_default_skipped_artifact(
    path: Path,
    *,
    include_source_pack: bool,
    include_review_html: bool,
    include_drilldowns: bool,
) -> bool:
    if not include_source_pack and "source_pack" in path.parts:
        return True
    stem = path.stem.lower()
    if not include_drilldowns and (
        "_drilldown_" in stem or stem.endswith("_drilldown")
    ):
        return True
    if include_review_html or path.suffix.lower() != ".html":
        return False
    if (
        stem == "index"
        or stem.endswith("_review")
        or stem.endswith("_widget")
        or "review_payload" in stem
    ):
        return True
    return not _is_default_gallery_html_artifact(path)


def _render_html_artifact(
    browser: Browser,
    item: GalleryItem,
    wait_ms: int,
) -> None:
    dimensions = item.dimensions or ArtifactDimensions(DEFAULT_WIDTH, DEFAULT_HEIGHT)
    viewport_width = min(max(dimensions.width, DEFAULT_WIDTH), MAX_VIEWPORT_WIDTH)
    viewport_height = min(max(dimensions.height, DEFAULT_HEIGHT), MAX_VIEWPORT_HEIGHT)
    page = browser.new_page(
        viewport={"width": viewport_width, "height": viewport_height},
        device_scale_factor=1,
    )
    try:
        page.goto(
            item.source_path.resolve().as_uri(), wait_until="load", timeout=30_000
        )
        if wait_ms > 0:
            page.wait_for_timeout(wait_ms)
        explicit_locator = page.locator(EXPLICIT_HTML_ARTIFACT_SELECTOR).first
        if explicit_locator.count() > 0:
            explicit_locator.screenshot(path=str(item.output_path), timeout=60_000)
        else:
            locator = page.locator(PLOTLY_DIV_SELECTOR).first
            if locator.count() > 0:
                locator.screenshot(path=str(item.output_path), timeout=60_000)
            else:
                html_artifact_locator = page.locator(HTML_ARTIFACT_SELECTOR).first
                if html_artifact_locator.count() > 0:
                    html_artifact_locator.screenshot(
                        path=str(item.output_path),
                        timeout=60_000,
                    )
                else:
                    page.screenshot(
                        path=str(item.output_path),
                        full_page=True,
                        timeout=60_000,
                    )
    finally:
        page.close()


def _write_png_artifact(item: GalleryItem) -> None:
    item.output_path.parent.mkdir(parents=True, exist_ok=True)
    if item.source_path.suffix.lower() == ".png":
        shutil.copyfile(item.source_path, item.output_path)
        return

    raise ValueError(f"Unsupported non-PNG artifact: {item.source_path}")


def _image_stats(path: Path) -> ImageStats:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        pixels = rgba.load()
        non_white = 0
        edge_ink = 0
        top_edge_ink = 0
        right_edge_ink = 0
        bottom_edge_ink = 0
        left_edge_ink = 0
        edge_band = max(2, min(width, height) // 100)
        for y_value in range(height):
            for x_value in range(width):
                r_value, g_value, b_value, alpha = pixels[x_value, y_value]
                is_non_white = alpha > 0 and min(r_value, g_value, b_value) < 245
                if is_non_white:
                    non_white += 1
                    is_top_edge = y_value < edge_band
                    is_right_edge = x_value >= width - edge_band
                    is_bottom_edge = y_value >= height - edge_band
                    is_left_edge = x_value < edge_band
                    if is_top_edge:
                        top_edge_ink += 1
                    if is_right_edge:
                        right_edge_ink += 1
                    if is_bottom_edge:
                        bottom_edge_ink += 1
                    if is_left_edge:
                        left_edge_ink += 1
                    if is_top_edge or is_right_edge or is_bottom_edge or is_left_edge:
                        edge_ink += 1
    pixel_count = max(width * height, 1)
    edge_pixel_count = max(
        (width * height) - ((width - 2 * edge_band) * (height - 2 * edge_band)),
        1,
    )
    horizontal_edge_pixel_count = max(width * edge_band, 1)
    vertical_edge_pixel_count = max(height * edge_band, 1)
    crop_risk_pixel_count = max(
        horizontal_edge_pixel_count + vertical_edge_pixel_count,
        1,
    )
    return ImageStats(
        width=width,
        height=height,
        byte_count=path.stat().st_size,
        non_white_ratio=non_white / pixel_count,
        edge_ink_ratio=edge_ink / edge_pixel_count,
        crop_risk_ink_ratio=(top_edge_ink + right_edge_ink) / crop_risk_pixel_count,
        top_edge_ink_ratio=top_edge_ink / horizontal_edge_pixel_count,
        right_edge_ink_ratio=right_edge_ink / vertical_edge_pixel_count,
        bottom_edge_ink_ratio=bottom_edge_ink / horizontal_edge_pixel_count,
        left_edge_ink_ratio=left_edge_ink / vertical_edge_pixel_count,
    )


def _rendered_image_hash(path: Path) -> str:
    """Return a gallery-only visual hash for duplicate PNG cards."""

    try:
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            digest = hashlib.sha256(rgba.tobytes()).hexdigest()
            return f"pixels:{rgba.width}x{rgba.height}:{digest}"
    except OSError:
        return f"bytes:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _dedupe_rendered_gallery_items(items: Sequence[GalleryItem]) -> list[GalleryItem]:
    """Remove visually identical rendered cards without changing artifact selection."""

    deduped: list[GalleryItem] = []
    seen_hashes: dict[str, GalleryItem] = {}
    for item in items:
        if not item.output_path.exists():
            deduped.append(item)
            continue
        image_hash = _rendered_image_hash(item.output_path)
        existing = seen_hashes.get(image_hash)
        if existing is not None:
            LOGGER.info(
                "Skipping duplicate rendered gallery image %s: %s duplicates %s",
                image_hash[:32],
                item.label,
                existing.label,
            )
            item.output_path.unlink(missing_ok=True)
            continue
        seen_hashes[image_hash] = item
        deduped.append(item)
    return deduped


def _filter_readable_gallery_images(items: Sequence[GalleryItem]) -> list[GalleryItem]:
    """Skip copied or rendered outputs that Pillow cannot decode as images."""

    readable: list[GalleryItem] = []
    for item in items:
        if not item.output_path.exists():
            LOGGER.warning(
                "Skipping missing gallery image output: %s from %s",
                item.output_path,
                item.source_path,
            )
            continue
        try:
            with Image.open(item.output_path) as image:
                image.verify()
        except OSError as exc:
            LOGGER.warning(
                "Skipping unreadable gallery image output: %s from %s (%s)",
                item.output_path,
                item.source_path,
                exc,
            )
            item.output_path.unlink(missing_ok=True)
            continue
        readable.append(item)
    return readable


def _sidecar_stems(item: GalleryItem) -> list[str]:
    sidecar_stems = [item.source_path.stem]
    unnumbered_stem = re.sub(r"_\d+$", "", item.source_path.stem)
    if unnumbered_stem not in sidecar_stems:
        sidecar_stems.append(unnumbered_stem)
    return sidecar_stems


def _sidecar_links(item: GalleryItem) -> list[SidecarLink]:
    links = [SidecarLink("source", item.source_path)]
    sidecar_stems = _sidecar_stems(item)
    seen_paths = {item.source_path.resolve()}
    seen_labels = {"source"}
    for stem in sidecar_stems:
        for context_name in (f"{stem}_chart_context.json", f"{stem}_context.json"):
            context_path = item.source_path.with_name(context_name)
            if context_path.exists():
                resolved_context = context_path.resolve()
                if resolved_context not in seen_paths:
                    links.append(SidecarLink("context", context_path))
                    seen_paths.add(resolved_context)
                    seen_labels.add("context")
        for data_name in (
            f"{stem}_chart_data.csv",
            f"{stem}_chart_data.json",
            f"{stem}_summary.csv",
            f"{stem}_summary.json",
            f"{stem}.csv",
            f"{stem}.xlsx",
        ):
            data_path = item.source_path.with_name(data_name)
            if data_path.exists():
                resolved_data = data_path.resolve()
                if resolved_data not in seen_paths:
                    links.append(SidecarLink("data", data_path))
                    seen_paths.add(resolved_data)
                    seen_labels.add("data")
    for label, path in _source_sidecar_paths(item):
        if label in seen_labels:
            continue
        resolved_path = path.resolve()
        if resolved_path not in seen_paths:
            links.append(SidecarLink(label, path))
            seen_paths.add(resolved_path)
            seen_labels.add(label)
    manifest_path = item.source_path.parent / "manifest.json"
    if manifest_path.exists():
        resolved_manifest = manifest_path.resolve()
        if resolved_manifest not in seen_paths and "manifest" not in seen_labels:
            links.append(SidecarLink("manifest", manifest_path))
            seen_paths.add(resolved_manifest)
            seen_labels.add("manifest")
    recipe_path = _recipe_sidecar_path(item)
    if recipe_path is not None:
        links.append(SidecarLink("recipe", recipe_path))
    return links


def _recipe_sidecar_path(item: GalleryItem) -> Path | None:
    recipe_path = item.source_path.parent / "used_recipe.json"
    if recipe_path.exists():
        return recipe_path
    run_intake_path = item.source_path.parent / "run_intake.json"
    if run_intake_path.exists():
        return run_intake_path
    if _plugin_source_id(item) == "attribute-tables":
        local_catalog_path = item.source_path.parent / "attribute_table_catalog.json"
        if local_catalog_path.exists():
            return local_catalog_path
        catalog_path = REPO_ROOT / "modules" / "pdp" / "attribute_table_catalog.json"
        if catalog_path.exists():
            return catalog_path
    return None


def _context_sidecar_path(item: GalleryItem) -> Path | None:
    for stem in _sidecar_stems(item):
        for context_name in (f"{stem}_chart_context.json", f"{stem}_context.json"):
            context_path = item.source_path.with_name(context_name)
            if context_path.exists():
                return context_path
    source_context = _source_context_path(item)
    if source_context is not None:
        return source_context
    fallback_context = _fallback_context_path(item)
    if fallback_context is not None:
        return fallback_context
    return None


def _source_sidecar_paths(item: GalleryItem) -> list[tuple[str, Path]]:
    record = _source_record_for_item(item)
    if record is None:
        manifest_path = _nearest_source_manifest(item.source_path)
        return [("manifest", manifest_path)] if manifest_path is not None else []
    manifest_path, artifact = record
    paths = [("manifest", manifest_path)]
    context_path = _resolve_source_payload_path(
        manifest_path,
        artifact.get("source_payload_path") or artifact.get("context"),
    )
    if context_path is None:
        context_path = _fallback_context_path(item)
    if context_path is not None:
        paths.insert(0, ("context", context_path))
    data_path = _source_data_path(item)
    if data_path is not None:
        paths.insert(1, ("data", data_path))
    return paths


def _source_context_path(item: GalleryItem) -> Path | None:
    record = _source_record_for_item(item)
    if record is None:
        return None
    manifest_path, artifact = record
    return _resolve_source_payload_path(
        manifest_path,
        artifact.get("source_payload_path") or artifact.get("context"),
    )


def _fallback_context_path(item: GalleryItem) -> Path | None:
    record = _source_record_for_item(item)
    manifest_path = (
        record[0] if record is not None else _nearest_source_manifest(item.source_path)
    )
    if manifest_path is None:
        return None
    run_dir = manifest_path.parent.parent
    context_names: list[str] = []
    for stem in _sidecar_stems(item):
        context_names.extend([f"{stem}_chart_context.json", f"{stem}_context.json"])
    context_names.extend(
        [
            "distribution_context.json",
            "mix_contribution_context.json",
            "period_comparison_context.json",
            "scatter_bubble_context.json",
            "set_overlap_context.json",
            "standard_variance_context.json",
        ]
    )
    for context_name in context_names:
        for base_dir in (run_dir, run_dir / "source_pack" / "contexts"):
            context_path = base_dir / context_name
            if context_path.exists():
                return context_path
    return None


def _source_data_path(item: GalleryItem) -> Path | None:
    for stem in _sidecar_stems(item):
        for name in (
            f"{stem}_chart_data.csv",
            f"{stem}_chart_data.json",
            f"{stem}.csv",
            f"{stem}.xlsx",
        ):
            data_path = item.source_path.with_name(name)
            if data_path.exists():
                return data_path
    exact_source_data = _exact_source_data_path(item)
    if exact_source_data is not None:
        return exact_source_data
    fallback_data = _fallback_source_data_path(item)
    if fallback_data is not None:
        return fallback_data
    return None


def _exact_source_data_path(item: GalleryItem) -> Path | None:
    record = _source_record_for_item(item)
    if record is None:
        return None
    manifest_path, artifact = record
    run_dir = manifest_path.parent.parent
    candidate_stems = set(_sidecar_stems(item))
    artifact_id = artifact.get("artifact_id")
    if isinstance(artifact_id, str) and artifact_id:
        candidate_stems.add(artifact_id)
    chart_spec_name = _record_value(artifact, "chart_spec_name")
    if isinstance(chart_spec_name, str) and chart_spec_name:
        candidate_stems.add(chart_spec_name)
    candidate_stems.update(f"{stem}_summary" for stem in tuple(candidate_stems) if stem)

    for source_artifact in _source_manifest_artifacts(manifest_path):
        if not _is_data_artifact(source_artifact):
            continue
        path = _resolve_source_artifact_path(run_dir, source_artifact)
        if path is None:
            continue
        source_artifact_id = source_artifact.get("artifact_id")
        source_artifact_stems = {path.stem}
        if isinstance(source_artifact_id, str) and source_artifact_id:
            source_artifact_stems.add(source_artifact_id)
        if candidate_stems & source_artifact_stems:
            return path
    return None


def _fallback_source_data_path(item: GalleryItem) -> Path | None:
    record = _source_record_for_item(item)
    if record is None:
        return None
    manifest_path, _artifact = record
    run_dir = manifest_path.parent.parent
    for filename in PREFERRED_FALLBACK_DATA_FILENAMES.get(
        item.source_path.stem,
        (),
    ):
        path = _source_data_path_by_filename(manifest_path, run_dir, filename)
        if path.exists():
            return path
    for filename in FALLBACK_DATA_FILENAMES:
        path = _source_data_path_by_filename(manifest_path, run_dir, filename)
        if path.exists():
            return path

    for source_artifact in _source_manifest_artifacts(manifest_path):
        if not _is_data_artifact(source_artifact):
            continue
        path = _resolve_source_artifact_path(run_dir, source_artifact)
        if path is not None:
            return path
    return None


def _source_data_path_by_filename(
    manifest_path: Path,
    run_dir: Path,
    filename: str,
) -> Path:
    path = run_dir / filename
    if path.exists():
        return path
    for source_artifact in _source_manifest_artifacts(manifest_path):
        if not _is_data_artifact(source_artifact):
            continue
        artifact_path = _resolve_source_artifact_path(run_dir, source_artifact)
        if artifact_path is not None and artifact_path.name == filename:
            return artifact_path
    return path


def _is_data_artifact(artifact: dict[str, Any]) -> bool:
    path_value = (
        artifact.get("path") or artifact.get("source_path") or artifact.get("pack_path")
    )
    if not isinstance(path_value, str) or not path_value.strip():
        return False
    if Path(path_value).suffix.lower() not in DATA_ARTIFACT_SUFFIXES:
        return False
    artifact_kind = str(
        artifact.get("kind") or artifact.get("artifact_type") or ""
    ).lower()
    return (
        "table" in artifact_kind
        or "data" in artifact_kind
        or "results" in artifact_kind
        or artifact_kind == ""
    )


def _resolve_source_artifact_path(
    run_dir: Path,
    artifact: dict[str, Any],
) -> Path | None:
    for candidate in (
        artifact.get("path"),
        artifact.get("source_path"),
        artifact.get("pack_path"),
    ):
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        candidate_path = Path(candidate)
        for base_dir in (run_dir, run_dir / "source_pack"):
            resolved_path = (base_dir / candidate_path).resolve()
            if resolved_path.exists():
                return resolved_path
    return None


def _source_record_for_item(item: GalleryItem) -> tuple[Path, dict[str, Any]] | None:
    manifest_path = _nearest_source_manifest(item.source_path)
    if manifest_path is None:
        return None
    try:
        artifacts = _source_manifest_artifacts(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Skipping unreadable source manifest %s: %s", manifest_path, exc)
        return None
    for artifact in artifacts:
        if _matches_source_artifact(item.source_path, manifest_path, artifact):
            return manifest_path, artifact
    return None


def _nearest_source_manifest(source_path: Path) -> Path | None:
    for directory in [source_path.parent, *source_path.parents]:
        manifest_path = directory / "source_pack" / "manifest.json"
        if manifest_path.exists():
            return manifest_path
    return None


@lru_cache(maxsize=None)
def _source_manifest_artifacts(manifest_path: Path) -> tuple[dict[str, Any], ...]:
    payload = _load_json(manifest_path)
    artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
    if not isinstance(artifacts, list):
        return ()
    return tuple(artifact for artifact in artifacts if isinstance(artifact, dict))


@lru_cache(maxsize=None)
def _source_manifest_plugin(manifest_path: Path) -> str | None:
    payload = _load_json(manifest_path)
    if not isinstance(payload, dict):
        return None
    plugin = payload.get("plugin")
    if isinstance(plugin, str) and plugin:
        return str(plugin)
    producer = payload.get("producer")
    if isinstance(producer, dict):
        producer_plugin = producer.get("plugin")
        if isinstance(producer_plugin, str) and producer_plugin:
            return producer_plugin
    return None


@lru_cache(maxsize=1)
def _capability_catalogs_by_id() -> dict[str, dict[str, Any]]:
    catalogs: dict[str, dict[str, Any]] = {}
    catalog_paths = [
        REPO_ROOT / "modules" / "pdp" / "attribute_table_catalog.json",
    ]
    for catalog_path in catalog_paths:
        if not catalog_path.exists():
            continue
        try:
            payload = _load_json(catalog_path)
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning(
                "Skipping unreadable capability catalog %s: %s",
                catalog_path,
                exc,
            )
            continue
        if not isinstance(payload, dict):
            continue
        plugin = payload.get("plugin")
        if not isinstance(plugin, str) or not plugin:
            plugin = (
                "attribute-tables"
                if catalog_path.name == "attribute_table_catalog.json"
                else catalog_path.parts[-3]
            )
        if not isinstance(plugin, str) or not plugin:
            continue
        execution_contract = payload.get("execution_contract")
        for capability in payload.get("capabilities") or []:
            if not isinstance(capability, dict):
                continue
            capability_id = capability.get("capability_id")
            if not isinstance(capability_id, str) or not capability_id:
                continue
            catalogs[capability_id] = {
                "plugin": plugin,
                "path": catalog_path.relative_to(REPO_ROOT).as_posix(),
                "capability": capability,
                "execution_contract": execution_contract,
            }
    return catalogs


@lru_cache(maxsize=1)
def _capability_ids_by_plugin_and_chart_spec() -> dict[str, dict[str, str]]:
    capabilities_by_plugin: dict[str, dict[str, str]] = {}
    for catalog in _capability_catalogs_by_id().values():
        plugin = catalog["plugin"]
        capability = catalog["capability"]
        plugin_capabilities = capabilities_by_plugin.setdefault(plugin, {})
        if capability.get("status") != "available":
            continue
        capability_id = capability.get("capability_id")
        if not isinstance(capability_id, str) or not capability_id:
            continue
        chart_spec_names = capability.get("chart_spec_names")
        if not isinstance(chart_spec_names, list):
            chart_spec_names = []
        if capability.get("chart_spec_name"):
            chart_spec_names = [*chart_spec_names, capability["chart_spec_name"]]
        table_spec_names = capability.get("table_spec_names")
        if not isinstance(table_spec_names, list):
            table_spec_names = []
        spec_names = [*chart_spec_names, *table_spec_names]
        for spec_name in spec_names:
            if isinstance(spec_name, str) and spec_name:
                plugin_capabilities.setdefault(spec_name, capability_id)
    return capabilities_by_plugin


def _chart_spec_lookup_names(raw_name: Any) -> list[str]:
    if not isinstance(raw_name, str) or not raw_name:
        return []
    names = [raw_name]
    without_number_suffix = re.sub(r"_\d+$", "", raw_name)
    if without_number_suffix != raw_name:
        names.append(without_number_suffix)
    return names


def _artifact_chart_spec_candidates(
    item: GalleryItem,
    artifact: dict[str, Any] | None,
) -> list[str]:
    raw_candidates: list[Any] = [item.source_path.stem]
    if artifact is not None:
        raw_candidates.extend(
            [
                artifact.get("artifact_id"),
                artifact.get("chart_spec_name"),
                artifact.get("table_spec_name"),
                _record_value(artifact, "chart_spec_name"),
                _record_value(artifact, "table_spec_name"),
                _record_value(artifact, "table_key"),
                _record_value(artifact, "chart_type"),
            ]
        )
        artifact_path = artifact.get("path") or artifact.get("source_path")
        if isinstance(artifact_path, str) and artifact_path:
            raw_candidates.append(Path(artifact_path).stem)
    candidates: list[str] = []
    seen: set[str] = set()
    for raw_candidate in raw_candidates:
        for candidate in _chart_spec_lookup_names(raw_candidate):
            if candidate not in seen:
                candidates.append(candidate)
                seen.add(candidate)
    return candidates


def _infer_capability_id(
    item: GalleryItem,
    manifest_path: Path | None,
    artifact: dict[str, Any] | None,
) -> str | None:
    plugin = _record_value(artifact, "plugin")
    if (not isinstance(plugin, str) or not plugin) and manifest_path is not None:
        plugin = _source_manifest_plugin(manifest_path)
    capabilities_by_plugin = _capability_ids_by_plugin_and_chart_spec()
    candidates = _artifact_chart_spec_candidates(item, artifact)
    if isinstance(plugin, str) and plugin in capabilities_by_plugin:
        plugin_capabilities = capabilities_by_plugin[plugin]
        for candidate in candidates:
            capability_id = plugin_capabilities.get(candidate)
            if capability_id:
                return capability_id
    for candidate in candidates:
        matching_capability_ids = {
            plugin_capabilities[candidate]
            for plugin_capabilities in capabilities_by_plugin.values()
            if candidate in plugin_capabilities
        }
        if len(matching_capability_ids) == 1:
            return next(iter(matching_capability_ids))
    return None


def _matches_source_artifact(
    source_path: Path,
    manifest_path: Path,
    artifact: dict[str, Any],
) -> bool:
    artifact_kind = str(
        artifact.get("kind") or artifact.get("artifact_type") or ""
    ).lower()
    if artifact_kind and "chart" not in artifact_kind and "table" not in artifact_kind:
        return False
    source_suffix = source_path.suffix.lower()
    if artifact_kind and source_suffix in {".html", ".png"}:
        is_html_table_source = source_suffix == ".html" and "table" in artifact_kind
        if "chart" not in artifact_kind and not is_html_table_source:
            return False
    candidate_values = [
        artifact.get("path"),
        artifact.get("source_path"),
        artifact.get("pack_path"),
    ]
    run_dir = manifest_path.parent.parent
    resolved_source = source_path.resolve()
    for candidate in candidate_values:
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        candidate_path = Path(candidate)
        if candidate_path.name == source_path.name:
            return True
        for base_dir in (run_dir, run_dir / "source_pack"):
            if (base_dir / candidate_path).resolve() == resolved_source:
                return True
    artifact_id = artifact.get("artifact_id")
    if isinstance(artifact_id, str) and artifact_id:
        return artifact_id == source_path.stem
    return False


def _resolve_source_payload_path(
    manifest_path: Path,
    payload_path: Any,
) -> Path | None:
    if not isinstance(payload_path, str) or not payload_path.strip():
        return None
    raw_path = Path(payload_path)
    if raw_path.is_absolute():
        return raw_path if raw_path.exists() else None
    run_dir = manifest_path.parent.parent
    candidates = [
        run_dir / raw_path,
        run_dir / "source_pack" / raw_path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _compact_list(value: Any, max_items: int = 3) -> str | None:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = [str(item) for item in value if item is not None and str(item) != ""]
    else:
        return None
    if not values:
        return None
    if len(values) <= max_items:
        return ", ".join(values)
    shown = ", ".join(values[:max_items])
    return f"{shown} +{len(values) - max_items}"


def _numeric_values(value: Any) -> Iterable[float]:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield float(value)
        return
    if isinstance(value, list):
        for item in value:
            yield from _numeric_values(item)


def _format_float(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _format_widths(widths: Iterable[float]) -> str | None:
    unique_widths = sorted({round(width, 4) for width in widths})
    if not unique_widths:
        return None
    return _compact_list([_format_float(width) for width in unique_widths], 4)


def _trace_widths(payload: dict[str, Any]) -> str | None:
    explicit_widths = _format_widths(_numeric_values(payload.get("trace_widths")))
    if explicit_widths is not None:
        return explicit_widths
    widths: list[float] = []
    figures = payload.get("plotly_figures")
    if not isinstance(figures, list):
        return None
    for figure in figures:
        if not isinstance(figure, dict):
            continue
        traces = figure.get("traces")
        if not isinstance(traces, list):
            continue
        for trace in traces:
            if not isinstance(trace, dict):
                continue
            widths.extend(_numeric_values(trace.get("width")))
    return _format_widths(widths)


def _record_value(
    artifact: dict[str, Any] | None,
    key: str,
) -> Any:
    if artifact is None:
        return None
    resolved_parameters = artifact.get("resolved_parameters")
    if isinstance(resolved_parameters, dict) and key in resolved_parameters:
        return resolved_parameters[key]
    return artifact.get(key)


def _record_periods(artifact: dict[str, Any] | None) -> list[str] | None:
    selected_periods = _record_value(artifact, "selected_periods")
    if isinstance(selected_periods, list) and selected_periods:
        return [str(period) for period in selected_periods]
    if artifact is None:
        return None
    resolved_parameters = artifact.get("resolved_parameters")
    if not isinstance(resolved_parameters, dict):
        return None
    periods = [
        resolved_parameters.get("baseline_period"),
        resolved_parameters.get("comparison_period"),
    ]
    values = [str(period) for period in periods if period not in (None, "")]
    return values or None


def _record_dimensions(payload: dict[str, Any], artifact: dict[str, Any] | None) -> Any:
    """Return plotted dimensions without showing mix candidate dimensions."""

    active_dimensions = _record_value(artifact, "active_dimensions")
    if active_dimensions:
        return active_dimensions
    configured_dimensions = _record_value(artifact, "configured_dimensions")
    available_dimensions = _record_value(artifact, "available_dimensions")
    if configured_dimensions or available_dimensions:
        return None
    payload_dimensions = payload.get("active_dimensions") or payload.get("dimensions")
    if payload_dimensions:
        return payload_dimensions
    return _record_value(artifact, "dimensions")


def _compact_source_reference(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if len(value) <= 24:
        return value
    return f"{value[:24]}..."


def _html_trace_widths(path: Path) -> str | None:
    try:
        html = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        LOGGER.warning("Skipping unreadable chart HTML %s: %s", path, exc)
        return None
    widths: list[float] = []
    for match in re.finditer(r'"width"\s*:\s*\[([^\]]{1,2000})\]', html):
        values = re.findall(r"-?\d+(?:\.\d+)?", match.group(1))
        widths.extend(float(value) for value in values)
    return _format_widths(widths)


def _html_has_nonempty_plotly_data(path: Path) -> bool:
    try:
        html = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        LOGGER.warning("Skipping unreadable chart HTML %s: %s", path, exc)
        return False
    if "Plotly.newPlot" not in html:
        return False
    empty_plot = re.search(
        r"Plotly\.newPlot\(\s*['\"][^'\"]+['\"]\s*,\s*\[\s*\]\s*,",
        html,
        re.DOTALL,
    )
    return empty_plot is None


def _is_intentionally_sparse_rendered_chart(item: GalleryItem) -> bool:
    label = item.label.lower()
    stem = item.source_path.stem.lower()
    if not any(
        token in label or token in stem for token in SPARSE_RENDERED_GRAMMAR_TOKENS
    ):
        return False
    if item.source_path.suffix.lower() == ".html":
        return _html_has_nonempty_plotly_data(item.source_path)
    return (
        item.source_path.suffix.lower() == ".png"
        and item.source_path.stat().st_size > 0
    )


def _context_summary(item: GalleryItem) -> ContextSummary | None:
    context_path = _context_sidecar_path(item)
    payload: dict[str, Any] = {}
    if context_path is not None:
        try:
            loaded_payload = _load_json(context_path)
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning(
                "Skipping unreadable chart context %s: %s", context_path, exc
            )
            loaded_payload = None
        if isinstance(loaded_payload, dict):
            payload = loaded_payload
    source_record = _source_record_for_item(item)
    manifest_path = source_record[0] if source_record is not None else None
    artifact = source_record[1] if source_record is not None else None
    if not payload and artifact is None:
        return None
    capability_id = _record_value(artifact, "capability_id") or _infer_capability_id(
        item,
        manifest_path,
        artifact,
    )
    metric_values = (
        payload.get("metric_label")
        or payload.get("metrics")
        or payload.get("metric")
        or _record_value(artifact, "metrics")
        or _record_value(artifact, "metric")
    )
    trace_widths = _trace_widths(payload)
    if trace_widths is None and item.source_path.suffix.lower() == ".html":
        trace_widths = _html_trace_widths(item.source_path)
    grammar = _display_grammar(
        capability_id,
        payload.get("legacy_chart")
        or payload.get("chart")
        or capability_id
        or _record_value(artifact, "chart_type"),
    )
    return ContextSummary(
        grammar=_compact_list(grammar, 1),
        metrics=_compact_list(metric_values),
        dimensions=_compact_list(_record_dimensions(payload, artifact)),
        periods=_compact_list(
            payload.get("selected_periods") or _record_periods(artifact)
        ),
        trace_widths=trace_widths,
        capability=_compact_list(capability_id, 1),
        source_reference=_compact_source_reference(
            _record_value(artifact, "artifact_id")
        ),
    )


def _display_grammar(capability_id: Any, raw_grammar: Any) -> Any:
    """Return gallery-facing grammar labels for overloaded legacy chart families."""

    if capability_id == "mix.bar":
        return "bar"
    if capability_id == "mix.stacked_bar":
        return "stacked bar"
    if capability_id == "mix.stacked_bar_overlay":
        return "bar with marker"
    return raw_grammar


def _render_context_summary(item: GalleryItem) -> str:
    summary = _context_summary(item)
    if summary is None:
        return ""
    parts = [
        ("capability", summary.capability),
        ("grammar", summary.grammar),
        ("metric", summary.metrics),
        ("dimension", summary.dimensions),
        ("period", summary.periods),
        ("trace width", summary.trace_widths),
        ("source", summary.source_reference),
    ]
    rendered_parts = [
        f"<b>{escape(label)}</b> {escape(value)}" for label, value in parts if value
    ]
    if not rendered_parts:
        return ""
    return f'<div class="context">{" | ".join(rendered_parts)}</div>'


def _quality_flags(item: GalleryItem, stats: ImageStats) -> list[QualityFlag]:
    flags: list[QualityFlag] = []
    if stats.crop_risk_ink_ratio >= HIGH_CROP_RISK_INK_RATIO:
        flags.append(
            QualityFlag(
                label="crop risk",
                detail="High ink near top/right image edges; inspect for cropping.",
            )
        )
    if (
        stats.non_white_ratio <= LOW_NON_WHITE_RATIO
        and not _is_intentionally_sparse_rendered_chart(item)
    ):
        flags.append(
            QualityFlag(
                label="sparse",
                detail="Very low non-white pixel share; inspect for blank output.",
            )
        )
    return flags


def _render_quality_flags(item: GalleryItem, stats: ImageStats) -> str:
    flags = _quality_flags(item, stats)
    if not flags:
        return ""
    return "".join(
        [
            '<div class="flags">',
            " ".join(
                (
                    f'<span class="flag" title="{escape(flag.detail)}">'
                    f"{escape(flag.label)}</span>"
                )
                for flag in flags
            ),
            "</div>",
        ]
    )


def _quality_summary(
    items: Sequence[GalleryItem], stats: dict[Path, ImageStats]
) -> str:
    flagged_count = sum(
        1 for item in items if _quality_flags(item, stats[item.output_path])
    )
    edge_count = sum(
        1
        for item in items
        if stats[item.output_path].crop_risk_ink_ratio >= HIGH_CROP_RISK_INK_RATIO
    )
    sparse_count = sum(
        1
        for item in items
        if stats[item.output_path].non_white_ratio <= LOW_NON_WHITE_RATIO
        and not _is_intentionally_sparse_rendered_chart(item)
    )
    return (
        f"{flagged_count} QA-flagged | {edge_count} crop-risk | "
        f"{sparse_count} sparse"
    )


def _source_href(gallery_dir: Path, path: Path) -> str:
    resolved_path = path.resolve()
    source_root = gallery_dir.resolve().parent
    try:
        relative = resolved_path.relative_to(source_root)
    except ValueError:
        return resolved_path.as_uri()
    return f"../{relative.as_posix()}"


def _render_sidecar_links(item: GalleryItem, gallery_dir: Path) -> str:
    links = _sidecar_links(item)
    if not links:
        return ""
    return "".join(
        [
            '<div class="links">',
            " ".join(
                (
                    f'<a href="{escape(_source_href(gallery_dir, link.path))}">'
                    f"{escape(link.label)}</a>"
                )
                for link in links
            ),
            "</div>",
        ]
    )


def _build_index(
    items: Sequence[GalleryItem],
    stats: dict[Path, ImageStats],
    gallery_dir: Path,
) -> str:
    family_plugin_sources: dict[str, set[str]] = {}
    for item in items:
        plugin_source = _plugin_source_id(item)
        source_family = _source_family_id(plugin_source)
        family_plugin_sources.setdefault(source_family, set()).add(plugin_source)

    sections: list[str] = []
    current_source_family: str | None = None
    current_family_sections: list[str] = []
    current_family_count = 0
    current_plugin_source: str | None = None
    current_cards: list[str] = []

    def flush_section() -> None:
        nonlocal current_cards, current_family_count
        if current_plugin_source is None:
            return
        heading = _plugin_source_label(current_plugin_source)
        family_heading = (
            _source_family_label(current_source_family)
            if current_source_family is not None
            else ""
        )
        suppress_heading = (
            current_source_family is not None
            and len(family_plugin_sources.get(current_source_family, set())) == 1
            and heading == family_heading
        )
        section_lines = [
            '<section class="plugin-section" ' f'id="{escape(current_plugin_source)}">'
        ]
        if not suppress_heading:
            section_lines.append(
                f'<h2 class="plugin-heading">{escape(heading)} '
                f"<span>{len(current_cards)} items</span></h2>"
            )
        section_lines.extend(
            ['<div class="grid">', *current_cards, "</div>", "</section>"]
        )
        current_family_sections.extend(section_lines)
        current_family_count += len(current_cards)
        current_cards = []

    def flush_family() -> None:
        nonlocal current_source_family, current_family_count
        nonlocal current_family_sections, current_plugin_source
        flush_section()
        if current_source_family is None:
            return
        heading = _source_family_label(current_source_family)
        sections.extend(
            [
                (
                    '<section class="source-family" '
                    f'id="{escape(current_source_family)}">'
                ),
                (
                    f'<h2 class="source-heading">{escape(heading)} '
                    f"<span>{current_family_count} items</span></h2>"
                ),
                *current_family_sections,
                "</section>",
            ]
        )
        current_family_sections = []
        current_family_count = 0
        current_plugin_source = None

    for item in items:
        item_plugin_source = _plugin_source_id(item)
        item_source_family = _source_family_id(item_plugin_source)
        if item_source_family != current_source_family:
            flush_family()
            current_source_family = item_source_family
        if item_plugin_source != current_plugin_source:
            flush_section()
            current_plugin_source = item_plugin_source
            current_cards = []
        item_stats = stats[item.output_path]
        current_cards.append(
            "".join(
                [
                    '<div class="card">',
                    f'<div class="label">{escape(item.label)}</div>',
                    (
                        f'<a href="{escape(item.output_path.name)}">'
                        f'<img src="{escape(item.output_path.name)}" '
                        f'width="{item_stats.width}" '
                        f'height="{item_stats.height}" loading="lazy"></a>'
                    ),
                    (
                        '<div class="meta">'
                        f"{item_stats.width}x{item_stats.height} | "
                        f"{item_stats.byte_count:,} bytes | "
                        f"non-white {item_stats.non_white_ratio:.1%} | "
                        f"edge ink {item_stats.edge_ink_ratio:.1%} | "
                        f"crop-risk {item_stats.crop_risk_ink_ratio:.1%}"
                        "</div>"
                    ),
                    _render_quality_flags(item, item_stats),
                    _render_context_summary(item),
                    _render_sidecar_links(item, gallery_dir),
                    "</div>",
                ]
            )
        )
    flush_family()
    return "\n".join(
        [
            "<!doctype html>",
            "<html>",
            "<head>",
            '<meta charset="utf-8">',
            "<title>Report source examples</title>",
            "<style>",
            (
                "body{font-family:Arial,sans-serif;margin:24px;background:#ffffff;"
                "color:#222}"
            ),
            (
                "h1{font-size:24px;margin:0 0 8px}p{margin:0 0 20px;color:#555}"
                ".source-family{margin-top:30px;scroll-margin-top:24px}"
                ".source-heading{font-size:22px;line-height:1.2;margin:0 0 14px;"
                "color:#222}.source-heading span{font-size:12px;font-weight:400;"
                "color:#777;margin-left:8px}.plugin-section{margin-top:18px;"
                "scroll-margin-top:24px}.plugin-heading{font-size:18px;"
                "line-height:1.2;margin:0 0 10px;color:#222}.plugin-heading span{"
                "font-size:12px;font-weight:400;color:#777;margin-left:8px}"
                ".grid{display:grid;grid-template-columns:repeat(auto-fill,"
                "minmax(360px,1fr));gap:18px}.card{background:white;border:"
                "1px solid #ddd;border-radius:6px;padding:12px}.card img{width:"
                "100%;height:auto;border:1px solid #eee;background:white}.label{"
                "font-size:13px;font-weight:700;margin:0 0 8px}.meta{font-size:"
                "12px;color:#777;margin-top:6px}.context{font-size:12px;color:#444;"
                "line-height:1.35;margin-top:7px}.context b{color:#666}.links{"
                "font-size:12px;margin-top:8px;display:flex;gap:10px;flex-wrap:"
                "wrap}.links a{color:#155a7a;text-decoration:none}.links a:hover{"
                "text-decoration:underline}.summary{font-size:13px;color:#555}"
                ".flags{display:flex;gap:6px;flex-wrap:wrap;margin-top:7px}.flag{"
                "font-size:11px;text-transform:uppercase;letter-spacing:.03em;"
                "border:1px solid #b77b00;background:#fff6dd;color:#704500;"
                "border-radius:3px;padding:2px 5px}"
            ),
            "</style>",
            "</head>",
            "<body>",
            "<h1>Report source examples</h1>",
            (
                f'<p class="summary">{escape(_quality_summary(items, stats))} | '
                '<a href="manifest.json">manifest.json</a></p>'
            ),
            *sections,
            "<script>",
            "(function(){",
            "function scrollToHashTarget(){",
            "if(!window.location.hash)return;",
            "var id=decodeURIComponent(window.location.hash.slice(1));",
            "var target=document.getElementById(id);",
            "if(!target)return;",
            "target.scrollIntoView({block:'start'});",
            "}",
            "function scheduleHashScroll(){",
            "scrollToHashTarget();",
            "[50,250,750,1500].forEach(function(delay){",
            "window.setTimeout(scrollToHashTarget,delay);",
            "});",
            "}",
            "window.addEventListener('hashchange',scheduleHashScroll);",
            "window.addEventListener('load',scheduleHashScroll);",
            "Array.from(document.images).forEach(function(image){",
            "if(image.complete)return;",
            "image.addEventListener('load',scheduleHashScroll,{once:true});",
            "image.addEventListener('error',scheduleHashScroll,{once:true});",
            "});",
            "scheduleHashScroll();",
            "}());",
            "</script>",
            "</body></html>",
        ]
    )


def _context_summary_dict(
    summary: ContextSummary | None,
) -> dict[str, str | None] | None:
    if summary is None:
        return None
    return {
        "capability": summary.capability,
        "grammar": summary.grammar,
        "metrics": summary.metrics,
        "dimensions": summary.dimensions,
        "periods": summary.periods,
        "trace_widths": summary.trace_widths,
        "source_reference": summary.source_reference,
    }


def _title_context(item: GalleryItem, gallery_dir: Path) -> dict[str, Any] | None:
    context_path = _context_sidecar_path(item)
    context_payload = _context_payload(item)
    title_lines = _title_lines_from_context_payload(context_payload)
    title_source = context_path
    if len(title_lines) < 3:
        title_lines = _title_lines_from_html_source(item.source_path)
        title_source = item.source_path
    if len(title_lines) < 3:
        title_lines = _fallback_title_lines(item)
        title_source = context_path or item.source_path
    if len(title_lines) < 3:
        return None
    lines = title_lines[:3]
    payload: dict[str, Any] = {
        "lines": lines,
        "who": lines[0],
        "what": lines[1],
        "when": lines[2],
    }
    if title_source is not None:
        payload["source"] = _source_href(gallery_dir, title_source)
    return payload


def _fallback_title_lines(item: GalleryItem) -> list[str]:
    summary = _context_summary(item)
    plugin_source = _plugin_source_label(_plugin_source_id(item))
    what_parts = [
        value
        for value in (
            summary.grammar if summary is not None else None,
            summary.metrics if summary is not None else None,
            summary.dimensions if summary is not None else None,
        )
        if isinstance(value, str) and value.strip()
    ]
    when = summary.periods if summary is not None else None
    lines = [
        plugin_source,
        " | ".join(what_parts) if what_parts else item.label,
        when if isinstance(when, str) and when.strip() else "Selected scope",
    ]
    return _clean_title_lines(lines)


def _title_lines_from_context_payload(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    for candidate in (
        payload.get("lines"),
        [payload.get("who"), payload.get("what"), payload.get("when")],
        payload.get("chart_title_lines"),
    ):
        lines = _clean_title_lines(candidate)
        if len(lines) >= 3:
            return lines
    contract = payload.get("title_contract")
    if isinstance(contract, dict):
        lines = _clean_title_lines(
            [contract.get("who"), contract.get("what"), contract.get("when")]
        )
        if len(lines) >= 3:
            return lines
    lines = _split_title_rows(payload.get("chart_title"))
    if len(lines) >= 3:
        return lines
    exports = payload.get("exports")
    if isinstance(exports, list):
        for export in exports:
            lines = _title_lines_from_context_payload(export)
            if len(lines) >= 3:
                return lines
    return []


def _title_lines_from_html_source(path: Path) -> list[str]:
    if path.suffix.lower() not in {".html", ".htm"}:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        LOGGER.warning("Skipping unreadable chart HTML title %s: %s", path, exc)
        return []
    for pattern in (
        r'"title"\s*:\s*\{[^{}]*"text"\s*:\s*"((?:\\.|[^"])*)"',
        r'"text"\s*:\s*"((?:\\.|[^"])*)"\s*,\s*"title"',
    ):
        for match in re.finditer(pattern, text):
            try:
                candidate = match.group(1).encode().decode("unicode_escape")
            except UnicodeDecodeError:
                candidate = match.group(1)
            lines = _split_title_rows(candidate)
            if len(lines) >= 3:
                return lines
    return _split_title_rows(_semantic_html_title(text))


def _semantic_html_title(text: str) -> str:
    title_block = re.search(
        r'<(?:header|div|section)[^>]+class="[^"]*(?:title|headline)[^"]*"[^>]*>'
        r"(.*?)</(?:header|div|section)>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if title_block:
        return title_block.group(1)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", text, flags=re.IGNORECASE | re.DOTALL)
    return h1.group(1) if h1 else ""


def _split_title_rows(value: Any) -> list[str]:
    text = str(value or "")
    text = re.sub(r"</(?:h1|h2|p|div|span)>", "<br>", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return _clean_title_lines(text.splitlines())


def _clean_title_lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_lines = re.split(r"\s*/\s*|<br\s*/?>|\n", value, flags=re.IGNORECASE)
    elif isinstance(value, list):
        raw_lines = [str(item) for item in value if item not in (None, "")]
    else:
        return []
    return [
        cleaned
        for cleaned in (
            re.sub(r"\s+", " ", unescape(line)).strip() for line in raw_lines
        )
        if cleaned
    ]


def _capability_id_for_item(item: GalleryItem) -> str | None:
    source_record = _source_record_for_item(item)
    manifest_path = source_record[0] if source_record is not None else None
    artifact = source_record[1] if source_record is not None else None
    capability_id = _record_value(artifact, "capability_id") or _infer_capability_id(
        item,
        manifest_path,
        artifact,
    )
    if isinstance(capability_id, str) and capability_id:
        return capability_id
    context_payload = _context_payload(item)
    context_capability_id = context_payload.get("capability_id")
    if isinstance(context_capability_id, str) and context_capability_id:
        return context_capability_id
    context_contract = context_payload.get("artifact_contract")
    if isinstance(context_contract, dict):
        context_contract_capability_id = context_contract.get("capability_id")
        if (
            isinstance(context_contract_capability_id, str)
            and context_contract_capability_id
        ):
            return context_contract_capability_id
    fallback_capability_id = _fallback_capability_id_for_item(item)
    if fallback_capability_id is not None:
        return fallback_capability_id
    return None


def _fallback_capability_id_for_item(item: GalleryItem) -> str | None:
    plugin_source = _plugin_source_id(item)
    if plugin_source == "variance-analysis":
        if item.source_path.stem in {"waterfall", "waterfall_small_multiples"}:
            return "variance.scenario_bridge"
        if item.source_path.stem == "pvm_decomposition_ladder":
            return "variance.price_volume_mix"
    if plugin_source == "set-overlap-analysis":
        if item.source_path.stem == "upset_small_multiples":
            return "set_overlap.upset_small_multiples"
        if item.source_path.stem in {"upset", "venn"}:
            return f"set_overlap.{item.source_path.stem}"
    return None


def _context_payload(item: GalleryItem) -> dict[str, Any]:
    context_path = _context_sidecar_path(item)
    if context_path is None:
        return {}
    try:
        payload = _load_json(context_path)
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Skipping unreadable chart context %s: %s", context_path, exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def _fallback_artifact_contract(
    item: GalleryItem,
    capability_id: str,
    context_payload: dict[str, Any],
) -> dict[str, Any]:
    interpretation_contract = context_payload.get("codex_interpretation_contract")
    if not isinstance(interpretation_contract, dict):
        interpretation_contract = {}
    when_to_use = (
        interpretation_contract.get("purpose")
        or context_payload.get("analysis_type")
        or context_payload.get("chart_type")
        or capability_id
    )
    required_parameters = [
        key
        for key in (
            "source_file",
            "metric",
            "comparison_basis",
            "baseline_period",
            "comparison_period",
            "dimension",
            "dimensions",
        )
        if key in context_payload
    ]
    if not required_parameters:
        required_parameters = ["source_file", "metric"]
    return {
        "capability_id": capability_id,
        "status": "context_only",
        "when_to_use": str(when_to_use),
        "required_parameters": required_parameters,
        "optional_parameters": [],
        "outputs": [
            {
                "artifact_type": item.source_path.suffix.lower().lstrip(".")
                or "artifact",
                "formats": [item.source_path.suffix.lower().lstrip(".")],
            }
        ],
    }


def _artifact_contract(item: GalleryItem) -> dict[str, Any] | None:
    capability_id = _capability_id_for_item(item)
    if capability_id is None:
        return None
    context_payload = _context_payload(item)
    context_contract = context_payload.get("artifact_contract")
    catalog = _capability_catalogs_by_id().get(capability_id)
    if catalog is None:
        fallback_contract = _fallback_artifact_contract(
            item,
            capability_id,
            context_payload,
        )
        if isinstance(context_contract, dict):
            contract = dict(context_contract)
            contract.setdefault("capability_id", capability_id)
            for key, value in fallback_contract.items():
                if contract.get(key) in (None, "", [], {}):
                    contract[key] = value
            return contract
        return fallback_contract
    capability = catalog["capability"]
    contract: dict[str, Any] = {
        "capability_id": capability_id,
        "plugin": catalog["plugin"],
        "catalog_path": catalog["path"],
        "status": capability.get("status"),
        "when_to_use": capability.get("use_when") or capability.get("description"),
        "required_parameters": capability.get("required_parameters") or [],
        "optional_parameters": capability.get("optional_parameters") or [],
        "outputs": capability.get("outputs") or [],
    }
    if catalog.get("execution_contract") not in (None, "", [], {}):
        contract["execution_contract"] = catalog["execution_contract"]
    for key in ARTIFACT_CONTRACT_KEYS:
        value = capability.get(key)
        if value not in (None, "", [], {}):
            contract[key] = value
    return contract


def _artifact_readiness(item: GalleryItem) -> dict[str, Any]:
    sidecars = _sidecar_links(item)
    labels = {link.label: link.path for link in sidecars}
    missing = [label for label in REQUIRED_ARTIFACT_SIDECARS if label not in labels]
    broken = [
        {"label": label, "path": str(path)}
        for label, path in labels.items()
        if not path.exists()
    ]
    missing_contract = _artifact_contract(item) is None
    issues = [f"missing_{label}" for label in missing]
    if missing_contract:
        issues.append("missing_artifact_contract")
    if broken:
        issues.append("broken_sidecar")
    return {
        "ready": not issues,
        "required_sidecars": list(REQUIRED_ARTIFACT_SIDECARS),
        "missing_sidecars": missing,
        "broken_sidecars": broken,
        "issues": issues,
    }


def _manifest_item(
    item: GalleryItem,
    item_stats: ImageStats,
    gallery_dir: Path,
) -> dict[str, Any]:
    plugin_source = _plugin_source_id(item)
    artifact_type = (
        "table"
        if _is_native_reporting_table_html(item.source_path)
        else item.source_path.suffix.lower().lstrip(".")
    )
    artifact_contract = _artifact_contract(item)
    artifact_readiness = _artifact_readiness(item)
    payload = {
        "label": item.label,
        "plugin_source": plugin_source,
        "plugin_source_label": _plugin_source_label(plugin_source),
        "source": _source_href(gallery_dir, item.source_path),
        "output": item.output_path.name,
        "artifact_type": artifact_type,
        "dimensions": {
            "width": item_stats.width,
            "height": item_stats.height,
        },
        "stats": {
            "byte_count": item_stats.byte_count,
            "non_white_ratio": item_stats.non_white_ratio,
            "edge_ink_ratio": item_stats.edge_ink_ratio,
            "crop_risk_ink_ratio": item_stats.crop_risk_ink_ratio,
            "top_edge_ink_ratio": item_stats.top_edge_ink_ratio,
            "right_edge_ink_ratio": item_stats.right_edge_ink_ratio,
            "bottom_edge_ink_ratio": item_stats.bottom_edge_ink_ratio,
            "left_edge_ink_ratio": item_stats.left_edge_ink_ratio,
        },
        "quality_flags": [
            {"label": flag.label, "detail": flag.detail}
            for flag in _quality_flags(item, item_stats)
        ],
        "context_summary": _context_summary_dict(_context_summary(item)),
        "title_context": _title_context(item, gallery_dir),
        "sidecars": [
            {
                "label": link.label,
                "href": _source_href(gallery_dir, link.path),
            }
            for link in _sidecar_links(item)
        ],
        "artifact_contract": artifact_contract,
        "artifact_readiness": artifact_readiness,
    }
    source_record = _source_record_for_item(item)
    artifact = source_record[1] if source_record is not None else None
    display_row_limit = _record_value(artifact, "display_row_limit")
    if display_row_limit is not None:
        payload["display_row_limit"] = display_row_limit
    return payload


def _build_manifest(
    items: Sequence[GalleryItem],
    stats: dict[Path, ImageStats],
    gallery_dir: Path,
) -> dict[str, Any]:
    item_payloads = [
        _manifest_item(item, stats[item.output_path], gallery_dir) for item in items
    ]
    return {
        "schema_version": "1.1",
        "item_count": len(item_payloads),
        "quality_summary": _quality_summary(items, stats),
        "quality_thresholds": {
            "high_edge_ink_ratio": HIGH_EDGE_INK_RATIO,
            "high_crop_risk_ink_ratio": HIGH_CROP_RISK_INK_RATIO,
            "low_non_white_ratio": LOW_NON_WHITE_RATIO,
        },
        "items": item_payloads,
    }


def _build_gallery(args: argparse.Namespace) -> int:
    source_root = args.source_root.resolve()
    gallery_dir = args.gallery_dir.resolve()
    staging_dir = _staging_gallery_dir(gallery_dir)
    _prepare_staging_gallery_dir(staging_dir)

    try:
        dimensions = _audit_dimensions(source_root)
        filters = [str(token) for token in args.only]
        exclude_filters = (
            []
            if bool(args.include_default_excluded)
            else [str(token) for token in args.exclude]
        )
        exact_exclude_labels = (
            []
            if bool(args.include_default_excluded)
            else list(DEFAULT_EXACT_EXCLUDE_LABELS)
        )
        items = _iter_source_artifacts(
            source_root,
            staging_dir,
            dimensions,
            filters,
            include_source_pack=bool(args.include_source_pack),
            include_review_html=bool(args.include_review_html),
            include_drilldowns=bool(args.include_drilldowns),
            exclude_filters=exclude_filters,
            exact_exclude_labels=exact_exclude_labels,
        )
        items = _sort_gallery_items(_dedupe_gallery_items(items))
        html_items = [
            item for item in items if item.source_path.suffix.lower() == ".html"
        ]
        png_items = [
            item for item in items if item.source_path.suffix.lower() == ".png"
        ]

        LOGGER.info("Gallery items: %s HTML, %s PNG", len(html_items), len(png_items))
        for item in png_items:
            _write_png_artifact(item)

        if html_items:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-gpu",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                    ],
                )
                try:
                    for index, item in enumerate(html_items, start=1):
                        LOGGER.info(
                            "Rendering %s/%s %s",
                            index,
                            len(html_items),
                            item.source_path,
                        )
                        _render_html_artifact(browser, item, int(args.wait_ms))
                finally:
                    browser.close()

        items = _filter_readable_gallery_images(_dedupe_rendered_gallery_items(items))
        stats = {item.output_path: _image_stats(item.output_path) for item in items}
        (staging_dir / "index.html").write_text(
            _build_index(items, stats, gallery_dir),
            encoding="utf-8",
        )
        (staging_dir / "manifest.json").write_text(
            json.dumps(_build_manifest(items, stats, gallery_dir), indent=2),
            encoding="utf-8",
        )
        _publish_staging_gallery_dir(staging_dir, gallery_dir)
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)

    LOGGER.info("Wrote %s", gallery_dir / "index.html")
    return 0


def _staging_gallery_dir(gallery_dir: Path) -> Path:
    return gallery_dir.with_name(f".{gallery_dir.name}.staging")


def _prepare_staging_gallery_dir(staging_dir: Path) -> None:
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)


def _publish_staging_gallery_dir(staging_dir: Path, gallery_dir: Path) -> None:
    gallery_dir.mkdir(parents=True, exist_ok=True)
    _clear_gallery_dir(gallery_dir)
    for path in staging_dir.iterdir():
        target = gallery_dir / path.name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        shutil.move(str(path), str(target))


def _clear_gallery_dir(gallery_dir: Path) -> None:
    for path in gallery_dir.iterdir():
        if path.is_file() and (
            path.suffix.lower() == ".png"
            or path.name in {"index.html", "manifest.json"}
        ):
            path.unlink()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(message)s",
    )
    return _build_gallery(args)


if __name__ == "__main__":
    raise SystemExit(main())
