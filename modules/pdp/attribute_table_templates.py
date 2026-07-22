from __future__ import annotations

import html
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import polars as pl

from modules.utilities.utils import get_row_count, get_schema_and_column_names

__all__ = [
    "ATTRIBUTE_TABLE_DIRNAME",
    "ATTRIBUTE_TABLE_TEMPLATE_FILES",
    "ATTRIBUTE_TABLE_TEMPLATES",
    "AttributeTableTemplate",
    "build_attribute_table_frames",
    "build_attribute_tables_from_package",
    "write_attribute_table_artifacts",
]

ATTRIBUTE_TABLE_DIRNAME = "attribute_tables"
ATTRIBUTE_TABLE_TEMPLATE_FILES = {
    "attribute_bundle_comparison_table": "attribute_bundle_comparison_table.csv",
    "attribute_bridge_table": "attribute_bridge_table.csv",
    "rank_weighted_visibility_table": "rank_weighted_visibility_table.csv",
    "product_signal_evidence_table": "product_signal_evidence_table.csv",
}
PACKAGE_FRAME_FILES = {
    "top_seller_pairs": "top_seller_pairs.csv",
    "top_seller_triples": "top_seller_triples.csv",
    "innovation_pairs": "innovation_pairs.csv",
    "innovation_triples": "innovation_triples.csv",
    "web_shelf_selected_shelves": "web_shelf_selected_shelves.csv",
    "web_shelf_robustness_summary": "web_shelf_robustness_summary.csv",
    "top_seller_products": "top_seller_products.csv",
    "recent_products": "recent_products.csv",
}
CSV_LIST_SEPARATOR = " | "
DEFAULT_MAX_ROWS = 5
PRODUCT_SIGNAL_MAX_ROWS = 10
CENTRAL_WEB_SHELF_ALPHA = 1.0
MOJIBAKE_MARKERS = ("\u00c3", "\u00c2", "\u00e2")


@dataclass(frozen=True, slots=True)
class AttributeTableTemplate:
    table_key: str
    title: str
    description: str
    source_files: tuple[str, ...]


ATTRIBUTE_TABLE_TEMPLATES: tuple[AttributeTableTemplate, ...] = (
    AttributeTableTemplate(
        table_key="attribute_bundle_comparison_table",
        title="Attribute Bundle Comparison",
        description=(
            "Ranked bundle rows comparing the focus cohort with its baseline, "
            "using counts, shares, delta, index, and brand breadth."
        ),
        source_files=(
            "top_seller_pairs.csv",
            "top_seller_triples.csv",
            "innovation_pairs.csv",
            "innovation_triples.csv",
        ),
    ),
    AttributeTableTemplate(
        table_key="attribute_bridge_table",
        title="Winner and Emerging Signal Bridge",
        description=(
            "Side-by-side table showing whether a bundle appears as a current "
            "top-seller signal, an emerging recent-product signal, or both."
        ),
        source_files=(
            "top_seller_pairs.csv",
            "top_seller_triples.csv",
            "innovation_pairs.csv",
            "innovation_triples.csv",
        ),
    ),
    AttributeTableTemplate(
        table_key="rank_weighted_visibility_table",
        title="Rank-Weighted Visibility",
        description=(
            "Web-shelf lanes with gross, incremental, and robustness metrics at "
            "the central rank-weighting assumption."
        ),
        source_files=(
            "web_shelf_selected_shelves.csv",
            "web_shelf_robustness_summary.csv",
        ),
    ),
    AttributeTableTemplate(
        table_key="product_signal_evidence_table",
        title="Product Signal Evidence",
        description=(
            "Product examples linked back to selected signal rows with rank, "
            "review, attribute, image, and caveat fields."
        ),
        source_files=(
            "top_seller_pairs.csv",
            "top_seller_triples.csv",
            "innovation_pairs.csv",
            "innovation_triples.csv",
            "top_seller_products.csv",
            "recent_products.csv",
        ),
    ),
)
SPANISH_TEMPLATE_COPY = {
    "attribute_bundle_comparison_table": {
        "title": "Comparación de conjuntos de atributos",
        "description": (
            "Filas de conjuntos ordenadas que comparan la cohorte de interés con "
            "su referencia mediante recuentos, cuotas, delta, índice y amplitud de "
            "marcas."
        ),
    },
    "attribute_bridge_table": {
        "title": "Puente entre señales ganadoras y emergentes",
        "description": (
            "Tabla comparativa que muestra si un conjunto aparece como señal actual "
            "de productos más vendidos, como señal emergente de productos recientes "
            "o en ambas."
        ),
    },
    "rank_weighted_visibility_table": {
        "title": "Visibilidad ponderada por posición",
        "description": (
            "Líneas de estantería digital con métricas brutas, incrementales y de "
            "robustez según el supuesto central de ponderación por posición."
        ),
    },
    "product_signal_evidence_table": {
        "title": "Evidencia de señales de producto",
        "description": (
            "Ejemplos de productos vinculados a las filas de señales seleccionadas, "
            "con campos de posición, reseñas, atributos, imagen y salvedades."
        ),
    },
}


def _empty_frame(columns: Sequence[str]) -> pl.DataFrame:
    return pl.DataFrame(schema={column: pl.Utf8 for column in columns})


def _columns(df: pl.DataFrame) -> set[str]:
    columns, _schema = get_schema_and_column_names(df)
    return set(columns)


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"none", "null", "nan"}:
        return ""
    return _repair_display_text(text)


def _repair_display_text(text: str) -> str:
    """Repair common UTF-8 mojibake before writing display artifacts."""

    if not any(marker in text for marker in MOJIBAKE_MARKERS):
        return text
    try:
        repaired = text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text
    return unicodedata.normalize("NFC", repaired)


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:
        return None
    return numeric


def _safe_int(value: Any) -> int | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    return int(numeric)


def _format_share(value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return ""
    return f"{numeric * 100:.1f}%"


def _format_delta_pp(value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return ""
    sign = "+" if numeric > 0 else ""
    return f"{sign}{numeric * 100:.1f} pp"


def _format_ratio(value: Any) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return ""
    return f"{numeric:.2f}x"


def _format_count(value: Any) -> str:
    numeric = _safe_int(value)
    if numeric is None:
        return ""
    return f"{numeric:,}"


def _split_examples(value: Any, *, max_items: int = 3) -> str:
    text = _safe_text(value)
    if not text:
        return ""
    parts = [part.strip() for part in text.split(CSV_LIST_SEPARATOR) if part.strip()]
    return CSV_LIST_SEPARATOR.join(parts[:max_items])


def _normalize_key(value: Any) -> str:
    text = _safe_text(value).lower()
    text = re.sub(r"\s+\(#\d+\)$", "", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _humanize_component(value: str) -> str:
    text = value.replace("_", " ").strip()
    if not text:
        return ""
    return " ".join(
        part.upper() if part.lower() == "spf" else part.capitalize()
        for part in text.split()
    )


def _humanize_bundle_key(value: Any) -> str:
    text = _safe_text(value)
    if not text:
        return ""
    if "=" not in text:
        return text
    components: list[str] = []
    for raw_component in text.split("+"):
        component = raw_component.strip()
        if not component:
            continue
        if "=" not in component:
            components.append(_humanize_component(component))
            continue
        family, raw_value = component.split("=", 1)
        components.append(
            f"{_humanize_component(family)} {_humanize_component(raw_value)}"
        )
    return " + ".join(components)


def _signal_usefulness_rank(value: Any) -> int:
    return {
        "headline_signal": 0,
        "selected_signal": 1,
        "supporting_signal": 2,
        "supporting_differentiation": 2,
    }.get(_safe_text(value), 3)


def _bundle_sort_score(row: Mapping[str, Any], *, layer: str) -> tuple[Any, ...]:
    focus_pct_key = "pct_top_seller" if layer == "winning_now" else "pct_recent"
    focus_count_key = "count_top_seller" if layer == "winning_now" else "count_recent"
    return (
        _signal_usefulness_rank(row.get("signal_usefulness")),
        -(_safe_float(row.get("insight_adjusted_signal_score")) or 0.0),
        -(_safe_float(row.get("rank_weighted_incremental_visibility_share")) or 0.0),
        -(_safe_float(row.get("rank_weighted_gross_visibility_share")) or 0.0),
        -(_safe_float(row.get("delta")) or 0.0),
        -(_safe_float(row.get(focus_pct_key)) or 0.0),
        -(_safe_int(row.get(focus_count_key)) or 0),
        _safe_text(row.get("bundle_label")),
    )


def _iter_signal_rows(
    df: pl.DataFrame,
    *,
    layer: str,
    source_file: str,
    max_rows: int,
) -> list[dict[str, Any]]:
    if get_row_count(df) == 0:
        return []
    rows = []
    columns = _columns(df)
    for row in df.to_dicts():
        if _safe_text(row.get("signal_role")) == "category_center":
            continue
        if not _safe_text(row.get("bundle_label")) and not _safe_text(
            row.get("bundle_key")
        ):
            continue
        normalized = dict(row)
        normalized["_source_file"] = source_file
        normalized["_layer"] = layer
        rows.append(normalized)
    if "signal_role" not in columns:
        rows = [row for row in rows if _safe_text(row.get("bundle_label"))]
    return sorted(rows, key=lambda row: _bundle_sort_score(row, layer=layer))[:max_rows]


def _signal_frame_sources(
    frames: Mapping[str, pl.DataFrame],
    *,
    layer: str,
    max_rows: int,
) -> list[dict[str, Any]]:
    source_names = (
        ("top_seller_triples", "top_seller_triples.csv"),
        ("top_seller_pairs", "top_seller_pairs.csv"),
    )
    if layer == "innovation":
        source_names = (
            ("innovation_triples", "innovation_triples.csv"),
            ("innovation_pairs", "innovation_pairs.csv"),
        )
    rows: list[dict[str, Any]] = []
    for frame_key, source_file in source_names:
        rows.extend(
            _iter_signal_rows(
                frames.get(frame_key, pl.DataFrame()),
                layer=layer,
                source_file=source_file,
                max_rows=max_rows,
            )
        )
    return sorted(rows, key=lambda row: _bundle_sort_score(row, layer=layer))[:max_rows]


def _bundle_display_name(row: Mapping[str, Any]) -> str:
    return _safe_text(row.get("bundle_label")) or _humanize_bundle_key(
        row.get("bundle_key")
    )


def _focus_count(row: Mapping[str, Any], *, layer: str) -> Any:
    return (
        row.get("count_top_seller")
        if layer == "winning_now"
        else row.get("count_recent")
    )


def _baseline_count(row: Mapping[str, Any], *, layer: str) -> Any:
    return row.get("count_other") if layer == "winning_now" else row.get("count_rest")


def _focus_share(row: Mapping[str, Any], *, layer: str) -> str:
    return _format_share(
        row.get("pct_top_seller") if layer == "winning_now" else row.get("pct_recent")
    )


def _baseline_share(row: Mapping[str, Any], *, layer: str) -> str:
    return _format_share(
        row.get("pct_other") if layer == "winning_now" else row.get("pct_rest")
    )


def _brand_count(row: Mapping[str, Any], *, layer: str) -> Any:
    return (
        row.get("top_seller_brand_count")
        if layer == "winning_now"
        else row.get("recent_brand_count")
    )


def _example_products(row: Mapping[str, Any], *, layer: str) -> str:
    keys = (
        ("top_seller_top_pareto_products", "top_seller_example_products")
        if layer == "winning_now"
        else ("recent_top_pareto_products", "recent_example_products")
    )
    for key in keys:
        examples = _split_examples(row.get(key))
        if examples:
            return examples
    return _split_examples(row.get("rank_weighted_visibility_top_products"))


def _build_attribute_bundle_comparison_table(
    frames: Mapping[str, pl.DataFrame],
) -> pl.DataFrame:
    columns = [
        "layer",
        "comparison",
        "signal_bundle",
        "focus_n",
        "baseline_n",
        "focus_share",
        "baseline_share",
        "delta",
        "index",
        "brands",
        "source_file",
    ]
    table_rows: list[dict[str, Any]] = []
    layer_specs = [
        ("winning_now", "Winning now", "Top sellers vs others"),
        ("innovation", "Emerging signal", "Recent vs rest"),
    ]
    base_layer_limit = DEFAULT_MAX_ROWS // len(layer_specs)
    extra_layer_rows = DEFAULT_MAX_ROWS % len(layer_specs)
    for index, (layer, layer_label, comparison) in enumerate(layer_specs):
        layer_limit = base_layer_limit + (1 if index < extra_layer_rows else 0)
        for row in _signal_frame_sources(frames, layer=layer, max_rows=layer_limit):
            table_rows.append(
                {
                    "layer": layer_label,
                    "comparison": comparison,
                    "signal_bundle": _bundle_display_name(row),
                    "focus_n": _format_count(_focus_count(row, layer=layer)),
                    "baseline_n": _format_count(_baseline_count(row, layer=layer)),
                    "focus_share": _focus_share(row, layer=layer),
                    "baseline_share": _baseline_share(row, layer=layer),
                    "delta": _format_delta_pp(row.get("delta")),
                    "index": _format_ratio(row.get("prevalence_ratio")),
                    "brands": _format_count(_brand_count(row, layer=layer)),
                    "source_file": _safe_text(row.get("_source_file")),
                }
            )
    if not table_rows:
        return _empty_frame(columns)
    return pl.DataFrame(table_rows, strict=False).select(columns)


def _best_signal_by_key(
    rows: Sequence[Mapping[str, Any]], *, layer: str
) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _normalize_key(row.get("bundle_key")) or _normalize_key(
            row.get("bundle_label")
        )
        if not key:
            continue
        candidate = dict(row)
        current = best.get(key)
        if current is None or _bundle_sort_score(
            candidate, layer=layer
        ) < _bundle_sort_score(current, layer=layer):
            best[key] = candidate
    return best


def _scenario_n(row: Mapping[str, Any] | None, *, layer: str) -> str:
    if row is None:
        return ""
    return _format_count(_focus_count(row, layer=layer))


def _scenario_share(row: Mapping[str, Any] | None, *, layer: str) -> str:
    if row is None:
        return ""
    return _focus_share(row, layer=layer)


def _scenario_delta(row: Mapping[str, Any] | None) -> str:
    if row is None:
        return ""
    return _format_delta_pp(row.get("delta"))


def _scenario_index(row: Mapping[str, Any] | None) -> str:
    if row is None:
        return ""
    return _format_ratio(row.get("prevalence_ratio"))


def _bridge_alignment(
    top_row: Mapping[str, Any] | None,
    innovation_row: Mapping[str, Any] | None,
) -> str:
    if top_row is not None and innovation_row is not None:
        return "Bridge"
    if top_row is not None:
        return "Winning-now only"
    return "Emerging only"


def _bridge_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    alignment_rank = {
        "Bridge": 0,
        "Winning-now only": 1,
        "Emerging only": 2,
    }.get(_safe_text(row.get("alignment")), 3)
    return (
        alignment_rank,
        -(_safe_float(row.get("_score")) or 0.0),
        _safe_text(row.get("bundle")),
    )


def _build_attribute_bridge_table(frames: Mapping[str, pl.DataFrame]) -> pl.DataFrame:
    columns = [
        "signal_bundle",
        "alignment",
        "current_n",
        "current_share",
        "current_delta",
        "current_index",
        "emerging_n",
        "emerging_share",
        "emerging_delta",
        "emerging_index",
        "current_brands",
        "recent_brands",
        "source_files",
    ]
    top_rows = _signal_frame_sources(frames, layer="winning_now", max_rows=24)
    innovation_rows = _signal_frame_sources(frames, layer="innovation", max_rows=24)
    top_by_key = _best_signal_by_key(top_rows, layer="winning_now")
    innovation_by_key = _best_signal_by_key(innovation_rows, layer="innovation")
    table_rows: list[dict[str, Any]] = []
    for key in sorted(set(top_by_key) | set(innovation_by_key)):
        top_row = top_by_key.get(key)
        innovation_row = innovation_by_key.get(key)
        label_row = top_row or innovation_row
        if label_row is None:
            continue
        table_rows.append(
            {
                "signal_bundle": _bundle_display_name(label_row),
                "alignment": _bridge_alignment(top_row, innovation_row),
                "current_n": _scenario_n(top_row, layer="winning_now"),
                "current_share": _scenario_share(top_row, layer="winning_now"),
                "current_delta": _scenario_delta(top_row),
                "current_index": _scenario_index(top_row),
                "emerging_n": _scenario_n(innovation_row, layer="innovation"),
                "emerging_share": _scenario_share(innovation_row, layer="innovation"),
                "emerging_delta": _scenario_delta(innovation_row),
                "emerging_index": _scenario_index(innovation_row),
                "current_brands": _format_count(
                    _brand_count(top_row or {}, layer="winning_now")
                ),
                "recent_brands": _format_count(
                    _brand_count(innovation_row or {}, layer="innovation")
                ),
                "source_files": CSV_LIST_SEPARATOR.join(
                    sorted(
                        {
                            _safe_text(row.get("_source_file"))
                            for row in (top_row, innovation_row)
                            if row is not None and _safe_text(row.get("_source_file"))
                        }
                    )
                ),
                "_score": max(
                    _safe_float((top_row or {}).get("insight_adjusted_signal_score"))
                    or 0.0,
                    _safe_float(
                        (innovation_row or {}).get("insight_adjusted_signal_score")
                    )
                    or 0.0,
                ),
            }
        )
    if not table_rows:
        return _empty_frame(columns)
    trimmed = sorted(table_rows, key=_bridge_sort_key)[:DEFAULT_MAX_ROWS]
    return pl.DataFrame(trimmed, strict=False).select(columns)


def _alpha_columns(row: Mapping[str, Any]) -> int:
    return sum(
        1
        for key in row
        if key.startswith("selected_under_alpha_") and row.get(key) is not None
    )


def _robustness_lookup(df: pl.DataFrame) -> dict[str, dict[str, Any]]:
    if get_row_count(df) == 0 or "bundle_key" not in _columns(df):
        return {}
    return {_safe_text(row.get("bundle_key")): row for row in df.to_dicts()}


def _build_rank_weighted_visibility_table(
    frames: Mapping[str, pl.DataFrame],
) -> pl.DataFrame:
    columns = [
        "rank",
        "lane",
        "gross_weight",
        "incremental",
        "cumulative",
        "skus",
        "brands",
        "robustness",
        "source_file",
    ]
    selected = frames.get("web_shelf_selected_shelves", pl.DataFrame())
    if get_row_count(selected) == 0:
        return _empty_frame(columns)
    selected_columns = _columns(selected)
    visible = selected
    if "alpha" in selected_columns:
        central = selected.filter(pl.col("alpha") == CENTRAL_WEB_SHELF_ALPHA)
        if get_row_count(central) > 0:
            visible = central
    sort_columns = [
        column
        for column in ("shelf_rank", "incremental_weight_share")
        if column in selected_columns
    ]
    if sort_columns:
        descending = [
            False if column == "shelf_rank" else True for column in sort_columns
        ]
        visible = visible.sort(sort_columns, descending=descending, nulls_last=True)
    robustness = _robustness_lookup(
        frames.get("web_shelf_robustness_summary", pl.DataFrame())
    )
    table_rows: list[dict[str, Any]] = []
    for row in visible.head(DEFAULT_MAX_ROWS).to_dicts():
        bundle_key = _safe_text(row.get("bundle_key"))
        if bundle_key == "__residual__":
            continue
        robust = robustness.get(bundle_key, {})
        alpha_total = _alpha_columns(robust) or None
        times_selected = _safe_int(robust.get("times_selected"))
        table_rows.append(
            {
                "rank": _format_count(row.get("shelf_rank")),
                "lane": _humanize_bundle_key(row.get("bundle_key")),
                "gross_weight": _format_share(row.get("gross_weight_share")),
                "incremental": _format_share(row.get("incremental_weight_share")),
                "cumulative": _format_share(row.get("cumulative_weight_share")),
                "skus": _format_count(row.get("incremental_sku_count")),
                "brands": _format_count(row.get("incremental_brand_count")),
                "robustness": (
                    f"{times_selected}/{alpha_total} alpha settings"
                    if times_selected is not None and alpha_total
                    else ""
                ),
                "source_file": "web_shelf_selected_shelves.csv",
            }
        )
    if not table_rows:
        return _empty_frame(columns)
    return pl.DataFrame(table_rows, strict=False).select(columns)


def _product_lookup_rows(
    frames: Mapping[str, pl.DataFrame],
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for frame_key, cohort_label in [
        ("top_seller_products", "Top seller"),
        ("recent_products", "Recent"),
    ]:
        frame = frames.get(frame_key, pl.DataFrame())
        if get_row_count(frame) == 0:
            continue
        for row in frame.to_dicts():
            key = _normalize_key(row.get("product_name"))
            if not key:
                continue
            enriched = dict(row)
            enriched["_cohort_label"] = cohort_label
            enriched["_source_file"] = f"{frame_key}.csv"
            existing = lookup.get(key)
            if existing is None:
                lookup[key] = enriched
                continue
            for image_key in (
                "pack_image_file",
                "pack_image_path",
                "pack_image_source",
                "local_image_path",
                "hero_image_url",
                "swatch_image_url",
                "og_image_url",
            ):
                if not _safe_text(existing.get(image_key)) and _safe_text(
                    enriched.get(image_key)
                ):
                    existing[image_key] = enriched.get(image_key)
    return lookup


def _parse_example_product(value: str) -> tuple[str, str]:
    text = _safe_text(value)
    match = re.search(r"\s+\(#(?P<rank>\d+)\)$", text)
    if match is None:
        return text, ""
    return text[: match.start()].strip(), match.group("rank")


def _product_attribute_text(row: Mapping[str, Any]) -> str:
    parts = []
    for key in (
        "resolved_form",
        "form",
        "resolved_finish",
        "finish",
        "resolved_coverage",
        "coverage",
    ):
        value = _safe_text(row.get(key))
        if value and value not in parts:
            parts.append(value)
    return CSV_LIST_SEPARATOR.join(parts[:4])


def _product_rating(row: Mapping[str, Any]) -> str:
    rating = _safe_float(row.get("rating"))
    if rating is None:
        return ""
    return f"{rating:.1f}"


def _product_review_count(row: Mapping[str, Any]) -> str:
    return _format_count(row.get("review_count"))


def _product_caveat(row: Mapping[str, Any]) -> str:
    caveats: list[str] = []
    if (
        _safe_float(row.get("rating")) is None
        and _safe_int(row.get("review_count")) is None
    ):
        caveats.append("No review metrics in package")
    if not _product_attribute_text(row):
        caveats.append("Sparse resolved attributes")
    if not _safe_text(row.get("pack_image_file")) and not _safe_text(
        row.get("pack_image_path")
    ):
        caveats.append("No package image")
    return "; ".join(caveats)


def _product_has_image(row: Mapping[str, Any]) -> bool:
    return any(
        _safe_text(row.get(key))
        for key in ("pack_image_file", "pack_image_path", "local_image_path")
    )


def _product_signal_candidates(
    frames: Mapping[str, pl.DataFrame],
    lookup: Mapping[str, dict[str, Any]],
    *,
    layer: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for signal_index, signal_row in enumerate(
        _signal_frame_sources(frames, layer=layer, max_rows=12)
    ):
        for example_index, example in enumerate(
            _split_examples(
                _example_products(signal_row, layer=layer), max_items=4
            ).split(CSV_LIST_SEPARATOR)
        ):
            product_name, parsed_rank = _parse_example_product(example)
            product_key = _normalize_key(product_name)
            if not product_key:
                continue
            product_row = lookup.get(product_key)
            if product_row is None:
                continue
            candidates.append(
                {
                    "signal_row": signal_row,
                    "product_row": product_row,
                    "product_name": product_name,
                    "parsed_rank": parsed_rank,
                    "signal_index": signal_index,
                    "example_index": example_index,
                    "has_image": _product_has_image(product_row),
                }
            )
    return sorted(
        candidates,
        key=lambda candidate: (
            not bool(candidate["has_image"]),
            int(candidate["signal_index"]),
            int(candidate["example_index"]),
        ),
    )


def _product_signal_table_row(candidate: Mapping[str, Any]) -> dict[str, Any]:
    signal_row = candidate["signal_row"]
    product_row = candidate["product_row"]
    product_name = _safe_text(product_row.get("product_name")) or _safe_text(
        candidate.get("product_name")
    )
    parsed_rank = _safe_text(candidate.get("parsed_rank"))
    rank = _safe_text(product_row.get("pareto_rank")) or parsed_rank
    return {
        "cohort": _safe_text(product_row.get("_cohort_label")),
        "rank": f"#{rank}" if rank else "",
        "brand": _safe_text(product_row.get("brand")),
        "product": product_name,
        "matched_signal": _bundle_display_name(signal_row),
        "rating": _product_rating(product_row),
        "reviews": _product_review_count(product_row),
        "attributes": _product_attribute_text(product_row),
        "caveat": _product_caveat(product_row),
        "image_file": _safe_text(product_row.get("pack_image_file")),
        "source_file": _safe_text(product_row.get("_source_file")),
    }


def _build_product_signal_evidence_table(
    frames: Mapping[str, pl.DataFrame],
) -> pl.DataFrame:
    columns = [
        "cohort",
        "rank",
        "brand",
        "product",
        "matched_signal",
        "rating",
        "reviews",
        "attributes",
        "caveat",
        "image_file",
        "source_file",
    ]
    lookup = _product_lookup_rows(frames)
    if not lookup:
        return _empty_frame(columns)
    table_rows: list[dict[str, Any]] = []
    seen_products: set[str] = set()
    layer_limits = (("winning_now", 5), ("innovation", 5))
    overflow: list[dict[str, Any]] = []
    for layer, layer_limit in layer_limits:
        layer_count = 0
        for candidate in _product_signal_candidates(frames, lookup, layer=layer):
            product_key = _normalize_key(candidate.get("product_name"))
            if not product_key or product_key in seen_products:
                continue
            if layer_count >= layer_limit:
                overflow.append(candidate)
                continue
            seen_products.add(product_key)
            table_rows.append(_product_signal_table_row(candidate))
            layer_count += 1
    for candidate in overflow:
        if len(table_rows) >= PRODUCT_SIGNAL_MAX_ROWS:
            break
        product_key = _normalize_key(candidate.get("product_name"))
        if not product_key or product_key in seen_products:
            continue
        seen_products.add(product_key)
        table_rows.append(_product_signal_table_row(candidate))
    if not table_rows:
        return _empty_frame(columns)
    return pl.DataFrame(table_rows, strict=False).select(columns)


def build_attribute_table_frames(
    frames: Mapping[str, pl.DataFrame],
) -> dict[str, pl.DataFrame]:
    """Build deterministic attribute report tables from evidence-pack frames.

    The templates are deterministic because they only format already-computed
    package metrics and mechanically selected examples. They intentionally do
    not decide the narrative meaning of the rows.
    """

    return {
        "attribute_bundle_comparison_table": _build_attribute_bundle_comparison_table(
            frames
        ),
        "attribute_bridge_table": _build_attribute_bridge_table(frames),
        "rank_weighted_visibility_table": _build_rank_weighted_visibility_table(frames),
        "product_signal_evidence_table": _build_product_signal_evidence_table(frames),
    }


def _template_by_key() -> dict[str, AttributeTableTemplate]:
    return {template.table_key: template for template in ATTRIBUTE_TABLE_TEMPLATES}


HTML_DISPLAY_COLUMNS = {
    "attribute_bundle_comparison_table": (
        "layer",
        "comparison",
        "signal_bundle",
        "focus_n",
        "baseline_n",
        "focus_share",
        "baseline_share",
        "delta",
        "index",
        "brands",
    ),
    "attribute_bridge_table": (
        "signal_bundle",
        "alignment",
        "current_n",
        "current_share",
        "current_delta",
        "current_index",
        "emerging_n",
        "emerging_share",
        "emerging_delta",
        "emerging_index",
        "current_brands",
        "recent_brands",
    ),
    "rank_weighted_visibility_table": (
        "rank",
        "lane",
        "gross_weight",
        "incremental",
        "cumulative",
        "skus",
        "brands",
        "robustness",
    ),
    "product_signal_evidence_table": (
        "cohort",
        "rank",
        "brand",
        "product",
        "matched_signal",
        "rating",
        "reviews",
        "attributes",
        "caveat",
    ),
}

COLUMN_LABELS = {
    "signal_bundle": "Signal bundle",
    "focus_n": "Focus n",
    "baseline_n": "Baseline n",
    "focus_share": "Focus",
    "baseline_share": "Baseline",
    "current_n": "Current n",
    "current_share": "Current",
    "current_delta": "Current delta",
    "current_index": "Current index",
    "emerging_n": "Emerging n",
    "emerging_share": "Emerging",
    "emerging_delta": "Emerging delta",
    "emerging_index": "Emerging index",
    "current_brands": "Current brands",
    "recent_brands": "Recent brands",
    "gross_weight": "Gross weight",
    "incremental": "Incremental",
    "cumulative": "Cumulative",
    "skus": "SKUs",
}
SPANISH_COLUMN_LABELS = {
    "layer": "Capa",
    "comparison": "Comparación",
    "signal_bundle": "Conjunto de señales",
    "focus_n": "n del foco",
    "baseline_n": "n de referencia",
    "focus_share": "Foco",
    "baseline_share": "Referencia",
    "delta": "Delta",
    "index": "Índice",
    "brands": "Marcas",
    "alignment": "Alineación",
    "current_n": "n actual",
    "current_share": "Actual",
    "current_delta": "Delta actual",
    "current_index": "Índice actual",
    "emerging_n": "n emergente",
    "emerging_share": "Emergente",
    "emerging_delta": "Delta emergente",
    "emerging_index": "Índice emergente",
    "current_brands": "Marcas actuales",
    "recent_brands": "Marcas recientes",
    "rank": "Posición",
    "lane": "Línea",
    "gross_weight": "Peso bruto",
    "incremental": "Incremental",
    "cumulative": "Acumulado",
    "skus": "SKUs",
    "robustness": "Robustez",
    "cohort": "Cohorte",
    "brand": "Marca",
    "product": "Producto",
    "matched_signal": "Señal coincidente",
    "rating": "Valoración",
    "reviews": "Reseñas",
    "attributes": "Atributos",
    "caveat": "Salvedad",
}

NUMERIC_COLUMNS = {
    "rank",
    "focus_n",
    "baseline_n",
    "focus_share",
    "baseline_share",
    "delta",
    "index",
    "brands",
    "current_n",
    "current_share",
    "current_delta",
    "current_index",
    "emerging_n",
    "emerging_share",
    "emerging_delta",
    "emerging_index",
    "current_brands",
    "recent_brands",
    "gross_weight",
    "incremental",
    "cumulative",
    "skus",
    "rating",
    "reviews",
}

STRONG_COLUMNS = {
    "focus_share",
    "delta",
    "current_delta",
    "emerging_delta",
    "incremental",
}


def _language_code(language: str) -> str:
    normalized = str(language or "en").strip().lower().replace("_", "-")
    return normalized.split("-", maxsplit=1)[0]


def _template_display_copy(
    template: AttributeTableTemplate, language: str
) -> tuple[str, str]:
    if _language_code(language) == "es":
        copy = SPANISH_TEMPLATE_COPY[template.table_key]
        return copy["title"], copy["description"]
    return template.title, template.description


def _display_column_label(column: str, language: str = "en") -> str:
    if _language_code(language) == "es":
        return SPANISH_COLUMN_LABELS.get(
            column, COLUMN_LABELS.get(column, column.replace("_", " ").title())
        )
    return COLUMN_LABELS.get(column, column.replace("_", " ").title())


def _html_table(table_key: str, df: pl.DataFrame, language: str = "en") -> str:
    template = _template_by_key()[table_key]
    title, template_description = _template_display_copy(template, language)
    spanish = _language_code(language) == "es"
    frame_columns, _schema = get_schema_and_column_names(df)
    preferred_columns = HTML_DISPLAY_COLUMNS.get(table_key, tuple(frame_columns))
    columns = [column for column in preferred_columns if column in frame_columns]
    if not columns:
        columns = frame_columns
    row_limit = _table_display_row_limit(table_key)
    description = (
        f"{template_description} Se muestran hasta {row_limit} filas."
        if spanish
        else f"{template_description} Showing up to {row_limit} rows."
    )
    header_parts = []
    for column in columns:
        header_class = "num" if column in NUMERIC_COLUMNS else ""
        label = html.escape(_display_column_label(column, language))
        header_parts.append(f'<th class="{header_class}">{label}</th>')
    header_cells = "".join(header_parts)
    body_rows = []
    previous_group = ""
    for row in df.to_dicts():
        current_group = (
            _safe_text(row.get("layer"))
            if table_key == "attribute_bundle_comparison_table"
            else ""
        )
        row_class = (
            ' class="section-break"'
            if previous_group and current_group != previous_group
            else ""
        )
        previous_group = current_group or previous_group
        cell_parts = []
        for column in columns:
            cell_class = " ".join(_cell_classes(column))
            value = html.escape(_safe_text(row.get(column)))
            cell_parts.append(f'<td class="{cell_class}">{value}</td>')
        cells = "".join(cell_parts)
        body_rows.append(f"<tr{row_class}>{cells}</tr>")
    if not body_rows:
        body_rows.append(
            f'<tr><td colspan="{len(columns) or 1}" class="empty">'
            f"{'No hay filas que cumplan los criterios.' if spanish else 'No qualifying rows.'}"
            "</td></tr>"
        )
    return f"""<!doctype html>
<html lang="{'es' if spanish else 'en'}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #1d1f23;
      --muted: #62666d;
      --rule: #d7d9de;
      --soft: #f5f6f7;
      --accent: #2f6f73;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #ffffff;
      color: var(--ink);
      font: 15px/1.28 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .page {{
      width: min(1360px, 100vw);
      padding: 32px 42px 36px;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 36px;
      line-height: 1.05;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .description {{
      max-width: 980px;
      margin: 0 0 18px;
      color: var(--ink);
      font-size: 20px;
      line-height: 1.18;
      font-weight: 650;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      border-top: 4px solid var(--ink);
      border-bottom: 3px solid var(--ink);
    }}
    th {{
      padding: 8px 10px;
      border-bottom: 2px solid var(--ink);
      color: var(--ink);
      font-size: 14px;
      line-height: 1.12;
      font-weight: 700;
      text-align: left;
    }}
    td {{
      padding: 9px 10px;
      border-bottom: 1px solid var(--rule);
      vertical-align: top;
      overflow-wrap: anywhere;
    }}
    tbody tr.section-break td {{ border-top: 2px solid #8f9399; }}
    .num {{
      text-align: right;
      font-variant-numeric: tabular-nums;
    }}
    .strong {{ font-weight: 700; }}
    .empty {{
      color: var(--muted);
      text-align: center;
    }}
  </style>
</head>
<body>
  <main class="page">
    <h1>{html.escape(title)}</h1>
    <p class="description">{html.escape(description)}</p>
    <table>
      <thead><tr>{header_cells}</tr></thead>
      <tbody>
        {"".join(body_rows)}
      </tbody>
    </table>
  </main>
</body>
</html>
"""


def _cell_classes(column: str) -> list[str]:
    classes: list[str] = []
    if column in NUMERIC_COLUMNS:
        classes.append("num")
    if column in STRONG_COLUMNS:
        classes.append("strong")
    return classes


def _validate_table_keys(table_keys: Sequence[str] | None) -> tuple[str, ...]:
    if table_keys is None:
        return tuple(ATTRIBUTE_TABLE_TEMPLATE_FILES)
    requested = tuple(str(table_key).strip() for table_key in table_keys)
    invalid = sorted(
        table_key
        for table_key in requested
        if table_key not in ATTRIBUTE_TABLE_TEMPLATE_FILES
    )
    if invalid:
        raise ValueError(f"Unknown attribute table template(s): {', '.join(invalid)}")
    return requested


def _table_display_row_limit(table_key: str) -> int:
    if table_key == "product_signal_evidence_table":
        return PRODUCT_SIGNAL_MAX_ROWS
    return DEFAULT_MAX_ROWS


def write_attribute_table_artifacts(
    frames: Mapping[str, pl.DataFrame],
    output_dir: Path,
    *,
    table_keys: Sequence[str] | None = None,
    language: str = "en",
) -> list[dict[str, Any]]:
    """Persist CSV/HTML table artifacts and return manifest entries."""

    table_dir = output_dir / ATTRIBUTE_TABLE_DIRNAME
    table_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries: list[dict[str, Any]] = []
    templates = _template_by_key()
    selected_table_keys = _validate_table_keys(table_keys)
    for table_key in selected_table_keys:
        csv_name = ATTRIBUTE_TABLE_TEMPLATE_FILES[table_key]
        frame = frames.get(table_key, _empty_frame([]))
        csv_path = table_dir / csv_name
        html_name = f"{Path(csv_name).stem}.html"
        html_path = table_dir / html_name
        frame.write_csv(csv_path)
        html_path.write_text(
            _html_table(table_key, frame, language=language), encoding="utf-8"
        )
        columns, _schema = get_schema_and_column_names(frame)
        template = templates[table_key]
        title, _description = _template_display_copy(template, language)
        manifest_entries.append(
            {
                "table_key": table_key,
                "title": title,
                "object_type": "table",
                "artifact_type": "table",
                "csv": f"{ATTRIBUTE_TABLE_DIRNAME}/{csv_name}",
                "html": f"{ATTRIBUTE_TABLE_DIRNAME}/{html_name}",
                "row_count": get_row_count(frame),
                "display_row_limit": _table_display_row_limit(table_key),
                "columns": columns,
                "source_files": list(template.source_files),
                "template_version": "1.0",
                "deterministic_policy": (
                    "Rows and columns are selected by fixed package metrics; "
                    "semantic interpretation remains with the report narrative."
                ),
            }
        )
    (table_dir / "manifest.json").write_text(
        json.dumps({"tables": manifest_entries}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest_entries


def _read_package_frames(package_dir: Path) -> dict[str, pl.DataFrame]:
    frames: dict[str, pl.DataFrame] = {}
    for frame_key, file_name in PACKAGE_FRAME_FILES.items():
        path = package_dir / file_name
        frames[frame_key] = pl.read_csv(path) if path.exists() else pl.DataFrame()
    return frames


def build_attribute_tables_from_package(
    package_dir: Path,
    *,
    output_dir: Path | None = None,
    table_keys: Sequence[str] | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Build deterministic attribute table artifacts from one evidence package."""

    resolved_package_dir = Path(package_dir)
    if not resolved_package_dir.exists():
        raise FileNotFoundError(f"Attribute package directory not found: {package_dir}")
    resolved_output_dir = Path(output_dir) if output_dir is not None else package_dir
    selected_table_keys = _validate_table_keys(table_keys)
    table_frames = build_attribute_table_frames(
        _read_package_frames(resolved_package_dir)
    )
    manifest_entries = write_attribute_table_artifacts(
        table_frames,
        resolved_output_dir,
        table_keys=selected_table_keys,
        language=language,
    )
    return {
        "status": "written",
        "package_dir": str(resolved_package_dir),
        "output_dir": str(resolved_output_dir),
        "table_keys": list(selected_table_keys),
        "tables": manifest_entries,
        "manifest_path": str(
            resolved_output_dir / ATTRIBUTE_TABLE_DIRNAME / "manifest.json"
        ),
    }
