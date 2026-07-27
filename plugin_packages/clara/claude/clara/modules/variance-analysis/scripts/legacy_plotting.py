"""Headless Plotly chart exports for variance-analysis plugin runs."""

from __future__ import annotations

import importlib
import logging
import warnings
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import polars as pl
from ibcs_titles import build_ibcs_title, ibcs_title_html
from legacy_adapter import _ensure_legacy_import_path

__all__ = [
    "WaterfallExport",
    "write_pvm_decomposition_ladder_png",
    "write_waterfall_png",
]

LOGGER = logging.getLogger(__name__)
IBCS_TITLE_X = 0.01
IBCS_TITLE_Y = 0.99
IBCS_TITLE_TOP_MARGIN = 125
LEGACY_RENDER_ERRORS = (
    AttributeError,
    IndexError,
    ImportError,
    KeyError,
    ModuleNotFoundError,
    NameError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
    pl.exceptions.PolarsError,
)


@dataclass(frozen=True)
class WaterfallExport:
    """Waterfall chart export paths and audit metadata."""

    paths: list[str]
    audit: dict[str, Any]


def _draw_waterfall_module() -> Any:
    """Import the vendored headless legacy waterfall module."""

    _ensure_legacy_import_path()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return importlib.import_module("modules.charting.draw_waterfall")


def _write_rendered_png(
    module: Any,
    rendered: Any,
    chart_path: Path,
) -> tuple[str, str | None]:
    """Write a rendered Plotly figure, falling back to the Pillow renderer."""

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            rendered.figure.write_image(str(chart_path), format="png")
        return "plotly+kaleido", None
    except (OSError, RuntimeError, ValueError) as exc:
        module.write_waterfall_fallback_png(rendered.figure, str(chart_path))
        return "plotly+pillow_fallback", str(exc)


def _ibcs_title_layout(title_html: str) -> dict[str, Any]:
    """Return the stable Plotly title layout used by exported variance charts."""

    return {
        "text": title_html,
        "x": IBCS_TITLE_X,
        "xanchor": "left",
        "y": IBCS_TITLE_Y,
        "yanchor": "top",
        "font": {"size": 18},
    }


def _apply_ibcs_title(
    rendered: Any,
    recipe: dict[str, Any],
    *,
    chart_kind: str,
    dimension: str | None = None,
) -> Any:
    """Replace renderer titles with neutral IBCS who/what/when metadata."""

    ibcs_title = build_ibcs_title(
        recipe,
        chart_kind=chart_kind,
        dimension=dimension,
    )
    title_html = ibcs_title_html(ibcs_title)
    rendered.figure.update_layout(title=_ibcs_title_layout(title_html))
    margin = dict(rendered.figure.layout.margin.to_plotly_json())
    margin["t"] = max(int(margin.get("t") or 0), IBCS_TITLE_TOP_MARGIN)
    rendered.figure.update_layout(margin=margin)
    if chart_kind == "standard_variance":
        rendered.figure.layout.annotations = ()
    audit = dict(rendered.audit)
    audit.update(
        {
            "legacy_title": audit.get("title"),
            "title": title_html,
            "chart_title": " / ".join(ibcs_title.lines()),
            "chart_title_lines": ibcs_title.lines(),
            "chart_kind": chart_kind,
            "title_layout": {
                "x": IBCS_TITLE_X,
                "xanchor": "left",
                "y": IBCS_TITLE_Y,
                "yanchor": "top",
                "top_margin": margin["t"],
            },
        }
    )
    if dimension:
        audit["chart_dimension"] = dimension
    return replace(rendered, audit=audit)


def write_waterfall_png(
    result: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    legacy_frame: pl.DataFrame | None = None,
    render_standard: bool = True,
    render_small_multiples: bool = True,
) -> WaterfallExport:
    """Write a Plotly/Kaleido PNG waterfall chart, returning non-blocking audit."""

    options = recipe.get("options") or {}
    enabled = bool(options.get("waterfall_chart", True))
    audit: dict[str, Any] = {
        "enabled": enabled,
        "artifact": "waterfall.png",
        "format": "png",
        "renderer": "plotly+kaleido",
    }
    if not enabled or (not render_standard and not render_small_multiples):
        audit["status"] = "disabled"
        audit["render_standard"] = render_standard
        audit["render_small_multiples"] = render_small_multiples
        return WaterfallExport(paths=[], audit=audit)

    small_multiples = bool(options.get("waterfall_small_multiples", False)) and bool(
        render_small_multiples
    )
    small_multiples_dimension = options.get("waterfall_small_multiples_dimension")
    audit.update(
        {
            "small_multiples": small_multiples,
            "small_multiples_dimension": small_multiples_dimension,
            "render_standard": render_standard,
            "render_small_multiples": render_small_multiples,
        }
    )
    paths: list[str] = []
    module = _draw_waterfall_module()
    if render_standard:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                rendered = module.draw_vertical_waterfall_chart(
                    result,
                    recipe,
                    small_multiples=False,
                    small_multiples_dimension=None,
                    legacy_frame=legacy_frame,
                )
                rendered = _apply_ibcs_title(
                    rendered,
                    recipe,
                    chart_kind="standard_variance",
                )
            chart_path = output_dir / "waterfall.png"
            renderer, plotly_error = _write_rendered_png(module, rendered, chart_path)
        except LEGACY_RENDER_ERRORS as exc:
            LOGGER.warning("Could not write waterfall chart: %s", exc)
            audit.update(
                {
                    "status": "not_written",
                    "error": str(exc),
                    "exception_type": exc.__class__.__name__,
                }
            )
            if not small_multiples:
                return WaterfallExport(paths=[], audit=audit)
        else:
            audit.update(rendered.audit)
            paths.append(str(chart_path))
            audit.update(
                {
                    "status": "written",
                    "path": str(chart_path),
                    "bytes": chart_path.stat().st_size,
                    "renderer": renderer,
                }
            )
            if plotly_error:
                audit["plotly_export_error"] = plotly_error
    else:
        audit.update(
            {
                "status": "skipped_standard_not_selected",
                "artifact": "waterfall.png",
            }
        )
    if small_multiples:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                small_rendered = module.draw_vertical_waterfall_chart(
                    result,
                    recipe,
                    small_multiples=True,
                    small_multiples_dimension=small_multiples_dimension,
                    legacy_frame=legacy_frame,
                )
                chart_dimension = small_multiples_dimension or small_rendered.audit.get(
                    "small_multiples_dimension"
                )
                small_rendered = _apply_ibcs_title(
                    small_rendered,
                    recipe,
                    chart_kind="standard_small_multiples",
                    dimension=str(chart_dimension) if chart_dimension else None,
                )
            small_path = output_dir / "waterfall_small_multiples.png"
            small_renderer, small_plotly_error = _write_rendered_png(
                module,
                small_rendered,
                small_path,
            )
            paths.append(str(small_path))
            audit.update(
                {
                    "small_multiples_status": "written",
                    "small_multiples_artifact": "waterfall_small_multiples.png",
                    "small_multiples_path": str(small_path),
                    "small_multiples_bytes": small_path.stat().st_size,
                    "small_multiples_renderer": small_renderer,
                    "small_multiples_audit": small_rendered.audit,
                }
            )
            if small_plotly_error:
                audit["small_multiples_plotly_export_error"] = small_plotly_error
        except LEGACY_RENDER_ERRORS as exc:
            LOGGER.warning("Could not write waterfall small multiples chart: %s", exc)
            audit.update(
                {
                    "small_multiples_status": "not_written",
                    "small_multiples_artifact": "waterfall_small_multiples.png",
                    "small_multiples_error": str(exc),
                    "small_multiples_exception_type": exc.__class__.__name__,
                }
            )
    elif render_small_multiples:
        audit["small_multiples_status"] = "disabled"
    return WaterfallExport(paths=paths, audit=audit)


def write_pvm_decomposition_ladder_png(
    result: pl.DataFrame,
    recipe: dict[str, Any],
    output_dir: Path,
    *,
    legacy_frame: pl.DataFrame | None = None,
) -> WaterfallExport:
    """Write the legacy PVM decomposition ladder chart."""

    options = recipe.get("options") or {}
    enabled = bool(options.get("pvm_decomposition_ladder", True))
    audit: dict[str, Any] = {
        "enabled": enabled,
        "artifact": "pvm_decomposition_ladder.png",
        "format": "png",
        "renderer": "plotly+kaleido",
    }
    if not enabled:
        audit["status"] = "disabled"
        return WaterfallExport(paths=[], audit=audit)
    if not recipe.get("mappings", {}).get("units_column"):
        audit.update(
            {
                "status": "not_written_missing_units",
                "reason": "PVM decomposition ladder requires a units column.",
            }
        )
        return WaterfallExport(paths=[], audit=audit)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            module = _draw_waterfall_module()
            rendered = module.draw_pvm_decomposition_ladder(
                result,
                recipe,
                legacy_frame=legacy_frame,
            )
            rendered = _apply_ibcs_title(
                rendered,
                recipe,
                chart_kind="pvm_decomposition_ladder",
            )
        chart_path = output_dir / "pvm_decomposition_ladder.png"
        renderer, plotly_error = _write_rendered_png(module, rendered, chart_path)
    except (
        ImportError,
        ModuleNotFoundError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        LOGGER.warning("Could not write PVM decomposition ladder chart: %s", exc)
        audit.update({"status": "not_written", "error": str(exc)})
        return WaterfallExport(paths=[], audit=audit)

    audit.update(rendered.audit)
    audit.update(
        {
            "status": "written",
            "path": str(chart_path),
            "bytes": chart_path.stat().st_size,
            "renderer": renderer,
        }
    )
    if plotly_error:
        audit["plotly_export_error"] = plotly_error
    return WaterfallExport(paths=[str(chart_path)], audit=audit)
