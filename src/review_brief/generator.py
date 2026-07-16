from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, replace
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Mapping

import polars as pl

from modules.llm.batch_runner import run_step_json
from modules.utilities.config import get_naming_params

from .charts import (
    ChartBuildError,
    ChartCandidate,
    build_brand_attribute_slope,
    build_dimension_stacked_absolute,
    build_dimension_stacked,
    build_dimension_stacked_facets,
    build_total_combo_absolute,
    choose_pair_attributes,
    compute_month_range,
)
from .formatting import format_brief_text_numbers
from .markdown import render_review_brief_markdown
from .models import (
    ChartInterpretation,
    ChartPayload,
    DimensionSpec,
    ReviewBriefNarrative,
    ReviewBriefResult,
    SuggestedSlide,
)

__all__ = ["generate_review_brief"]


_SAFE_FILENAME = re.compile(r"[^a-z0-9]+")
_logger = logging.getLogger(__name__)


def _safe_slug(value: str) -> str:
    base = str(value or "").strip().lower()
    base = _SAFE_FILENAME.sub("-", base).strip("-")
    return base or "brief"


def _build_interpretation_system_prompt() -> str:
    return (
        "You are an analyst who writes short, consulting-style slide notes.\n"
        "You are given ONE chart's already-aggregated sales-share data (no raw tables).\n"
        "You are also given the requested_scope for this brief; keep your interpretation consistent with it.\n"
        "Rules:\n"
        "- Use only the provided numbers; do not invent any values.\n"
        "- Prefer sharp, specific insights (delta in percentage points, biggest winners/losers).\n"
        "- Keep to max 5 short bullets.\n"
        "- Number formatting:\n"
        '  - Shares (%): use one decimal place (e.g., 25.4%). For shares <1%, write "<1%" (do not write 0.39%).\n'
        '  - Deltas (percentage points): use whole numbers only, written as "up N pp" / "down N pp".\n'
        '    Use "up ~N pp" when approximate (e.g., when a share is expressed as "<1%").\n'
        '  - Do not write "+N" or "p.p.".\n'
        "- Return json with keys: chart_id (string), headline (string), bullets (array of strings), relevance (integer 0-100), highlight_item (string).\n"
        "- highlight_item must be either an exact chart label to emphasize, or an empty string when no highlight is needed.\n"
        "- Relevance means: worth including as a slide in a 10–20 slide deck.\n"
    )


def _build_interpretation_prompt(
    chart: Mapping[str, object],
    *,
    requested_scope: Mapping[str, object] | None = None,
) -> str:
    payload: dict[str, object] = {"chart": chart}
    if requested_scope:
        payload["requested_scope"] = dict(requested_scope)
    return json.dumps(payload, ensure_ascii=False)


def _parse_interpretation(
    raw: Mapping[str, object], fallback_id: str
) -> ChartInterpretation:
    chart_id = str(raw.get("chart_id") or fallback_id)
    headline = format_brief_text_numbers(str(raw.get("headline") or "").strip())
    highlight_item_raw = str(
        raw.get("highlight_item") or raw.get("highlightItem") or ""
    ).strip()
    highlight_item = highlight_item_raw or None
    bullets_raw = raw.get("bullets") or []
    bullets: list[str] = []
    if isinstance(bullets_raw, list):
        for item in bullets_raw[:5]:
            text = str(item).strip()
            if text:
                bullets.append(format_brief_text_numbers(text))
    try:
        relevance_val = int(raw.get("relevance", 0))
    except (TypeError, ValueError):
        relevance_val = 0
    relevance = max(0, min(100, relevance_val))
    return ChartInterpretation(
        chart_id=chart_id,
        headline=headline,
        bullets=bullets,
        relevance=relevance,
        highlight_item=highlight_item,
    )


def _build_narrative_system_prompt() -> str:
    return (
        "You are a senior consultant writing the executive narrative for a slide deck.\n"
        "You are given ONLY already-aggregated chart payloads (sales-share %) plus short analyst notes.\n"
        "Respect the provided requested_scope (active filters and focus attributes) while writing conclusions.\n"
        "Rules:\n"
        "- Do not invent numbers; if you mention a number, it must be present in the input.\n"
        "- Number formatting:\n"
        '  - Shares (%): use one decimal place (e.g., 25.4%). For shares <1%, write "<1%".\n'
        '  - Deltas (percentage points): use whole numbers only as "up N pp" / "down N pp" (or "up ~N pp" when approximate).\n'
        '  - Do not use "+N" or "p.p.".\n'
        "- Keep wording crisp and consulting-style.\n"
        "- Prefer cross-retailer comparisons when charts are faceted by retailer.\n"
        "- Use the provided chart_ids when referencing charts; do not introduce new ids.\n"
        "- Return json with keys:\n"
        "  executive_narrative (string),\n"
        "  key_takeaways (array of <= 6 short strings),\n"
        "  suggested_flow (array of <= 20 objects with keys: title (string), chart_ids (array of strings)).\n"
    )


def _build_narrative_prompt(
    *,
    category_label: str,
    retailers: list[str],
    start_month: str,
    end_month: str,
    charts: list[ChartPayload],
    interpretations: Mapping[str, ChartInterpretation],
    requested_scope: Mapping[str, object] | None = None,
) -> str:
    chart_items: list[dict[str, object]] = []
    for chart in charts:
        chart_items.append(
            {
                "chart": _chart_to_prompt_payload(chart),
                "interpretation": asdict(
                    interpretations.get(
                        chart.chart_id,
                        ChartInterpretation(chart.chart_id, "", [], 0),
                    )
                ),
            }
        )
    payload = {
        "scope": {
            "category": category_label,
            "retailers": retailers,
            "start_month": start_month,
            "end_month": end_month,
            "metric": "sales share (%) of the category total within the selected scope",
        },
        "charts": chart_items,
    }
    if requested_scope:
        payload["requested_scope"] = dict(requested_scope)
    return json.dumps(payload, ensure_ascii=False)


def _parse_narrative(
    raw: Mapping[str, object], *, valid_chart_ids: set[str]
) -> ReviewBriefNarrative:
    exec_text = format_brief_text_numbers(
        str(
            raw.get("executive_narrative")
            or raw.get("executiveNarrative")
            or raw.get("narrative")
            or ""
        ).strip()
    )

    takeaways_raw = (
        raw.get("key_takeaways")
        or raw.get("keyTakeaways")
        or raw.get("takeaways")
        or []
    )
    takeaways: list[str] = []
    if isinstance(takeaways_raw, list):
        for item in takeaways_raw[:6]:
            text = str(item).strip()
            if text:
                takeaways.append(format_brief_text_numbers(text))

    flow_raw = (
        raw.get("suggested_flow") or raw.get("suggestedFlow") or raw.get("flow") or []
    )
    flow: list[SuggestedSlide] = []
    if isinstance(flow_raw, list):
        for item in flow_raw[:20]:
            if isinstance(item, Mapping):
                title = format_brief_text_numbers(str(item.get("title") or "").strip())
                ids_raw = item.get("chart_ids") or item.get("chartIds") or []
                chart_ids: list[str] = []
                if isinstance(ids_raw, list):
                    for cid in ids_raw:
                        text = str(cid).strip()
                        if text and text in valid_chart_ids and text not in chart_ids:
                            chart_ids.append(text)
                if title:
                    flow.append(SuggestedSlide(title=title, chart_ids=chart_ids))
            else:
                title = format_brief_text_numbers(str(item).strip())
                if title:
                    flow.append(SuggestedSlide(title=title, chart_ids=[]))

    return ReviewBriefNarrative(
        executive_narrative=exec_text,
        key_takeaways=takeaways,
        suggested_flow=flow,
    )


def _build_single_chart_flow(
    *,
    charts: list[ChartPayload],
    interpretations: Mapping[str, ChartInterpretation],
    preferred_titles: Mapping[str, str] | None = None,
) -> list[SuggestedSlide]:
    titles = preferred_titles or {}
    flow: list[SuggestedSlide] = []
    for chart in charts:
        chart_id = str(chart.chart_id or "").strip()
        if not chart_id:
            continue
        preferred = str(titles.get(chart_id, "")).strip()
        if preferred:
            title = preferred
        else:
            interp = interpretations.get(chart_id)
            headline = str(interp.headline or "").strip() if interp else ""
            title = headline or str(chart.title or "").strip() or chart_id
        flow.append(SuggestedSlide(title=title, chart_ids=[chart_id]))
    return flow


def _merge_suggested_flow(
    primary: list[SuggestedSlide],
    fallback: list[SuggestedSlide],
) -> list[SuggestedSlide]:
    """Keep the model-proposed flow, then append any omitted selected charts."""

    merged: list[SuggestedSlide] = []
    seen_chart_ids: set[str] = set()

    for slide in primary:
        title = str(slide.title or "").strip()
        chart_ids: list[str] = []
        for raw_chart_id in slide.chart_ids:
            chart_id = str(raw_chart_id or "").strip()
            if not chart_id or chart_id in chart_ids:
                continue
            chart_ids.append(chart_id)
            seen_chart_ids.add(chart_id)
        if title:
            merged.append(SuggestedSlide(title=title, chart_ids=chart_ids))

    for slide in fallback:
        chart_ids = [
            chart_id
            for chart_id in slide.chart_ids
            if chart_id and chart_id not in seen_chart_ids
        ]
        if not chart_ids:
            continue
        seen_chart_ids.update(chart_ids)
        merged.append(SuggestedSlide(title=slide.title, chart_ids=chart_ids))

    return merged


def _normalize_highlight_token(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _resolve_slope_row_label(row: Mapping[str, object]) -> str:
    brand = str(row.get("brand") or row.get("row") or row.get("segment") or "").strip()
    attribute = str(row.get("attribute") or row.get("col") or "").strip()
    if brand and attribute and brand != attribute:
        return f"{brand} · {attribute}"
    if brand:
        return brand
    if attribute:
        return attribute
    return ""


def _resolve_chart_highlight_items(
    chart: ChartPayload, interpretation: ChartInterpretation | None
) -> list[str]:
    if interpretation is None:
        return []
    requested = str(interpretation.highlight_item or "").strip()
    if not requested:
        return []
    payload = chart.payload
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []

    requested_token = _normalize_highlight_token(requested)
    if not requested_token:
        return []

    chart_type = str(chart.chart_type or "").strip().lower()
    if chart_type == "area":
        segments: list[str] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            segment = str(row.get("segment") or "").strip()
            if not segment:
                continue
            token = _normalize_highlight_token(segment)
            if not token or token in seen:
                continue
            seen.add(token)
            segments.append(segment)

        for segment in segments:
            if _normalize_highlight_token(segment) == requested_token:
                return [segment]

        partial = [
            segment
            for segment in segments
            if requested_token in _normalize_highlight_token(segment)
            or _normalize_highlight_token(segment) in requested_token
        ]
        if len(partial) == 1:
            return [partial[0]]
        return []

    if chart_type == "slope":
        labels: list[str] = []
        brands: list[str] = []
        attributes: list[str] = []
        seen_labels: set[str] = set()
        seen_brands: set[str] = set()
        seen_attributes: set[str] = set()

        for row in rows:
            if not isinstance(row, Mapping):
                continue
            label = _resolve_slope_row_label(row)
            if label:
                label_token = _normalize_highlight_token(label)
                if label_token and label_token not in seen_labels:
                    seen_labels.add(label_token)
                    labels.append(label)
            brand = str(row.get("brand") or "").strip()
            if brand:
                brand_token = _normalize_highlight_token(brand)
                if brand_token and brand_token not in seen_brands:
                    seen_brands.add(brand_token)
                    brands.append(brand)
            attribute = str(row.get("attribute") or "").strip()
            if attribute:
                attribute_token = _normalize_highlight_token(attribute)
                if attribute_token and attribute_token not in seen_attributes:
                    seen_attributes.add(attribute_token)
                    attributes.append(attribute)

        for value in labels:
            if _normalize_highlight_token(value) == requested_token:
                return [value]
        for value in brands:
            if _normalize_highlight_token(value) == requested_token:
                return [value]
        for value in attributes:
            if _normalize_highlight_token(value) == requested_token:
                return [value]

        partial = [
            value
            for value in [*labels, *brands, *attributes]
            if requested_token in _normalize_highlight_token(value)
            or _normalize_highlight_token(value) in requested_token
        ]
        if len(partial) == 1:
            return [partial[0]]
        return []

    return []


def _apply_model_highlights(
    charts: list[ChartPayload], interpretations: Mapping[str, ChartInterpretation]
) -> list[ChartPayload]:
    updated: list[ChartPayload] = []
    for chart in charts:
        interpretation = interpretations.get(chart.chart_id)
        highlight_items = _resolve_chart_highlight_items(chart, interpretation)
        if not highlight_items:
            updated.append(chart)
            continue
        payload = dict(chart.payload)
        payload["highlighted_dimension"] = highlight_items
        updated.append(replace(chart, payload=payload))
    return updated


def _merge_selected_charts_into_catalog(
    chart_candidates: list[ChartCandidate], selected: list[ChartPayload]
) -> list[ChartPayload]:
    selected_by_id = {chart.chart_id: chart for chart in selected}
    merged: list[ChartPayload] = []
    for candidate in chart_candidates:
        candidate_chart = candidate.chart
        merged.append(selected_by_id.get(candidate_chart.chart_id, candidate_chart))
    return merged


def generate_review_brief(
    llm_wrapper: Any,
    *,
    joined_full: pl.DataFrame,
    joined_l4l: pl.DataFrame,
    category_key: str,
    category_label: str,
    retailers: list[str],
    brands: list[str],
    placeholder_values: set[str],
    attributes: list[DimensionSpec],
    attribute_value_counts: Mapping[str, int],
    brand: DimensionSpec,
    retailer_dim: DimensionSpec,
    price_band: DimensionSpec | None = None,
    pareto: DimensionSpec | None = None,
    output_dir: Path = Path("reports") / "review_briefs",
    dataset: str | None = None,
    max_selected_charts: int = 20,
    min_selected_charts: int = 10,
    job_id: str | None = None,
    chart_view_base_url: str | None = None,
    requested_scope: Mapping[str, object] | None = None,
    prompt_style: str | None = None,
    chart_palette: str | None = None,
) -> ReviewBriefResult:
    start_month, end_month = compute_month_range(joined_full)
    unique_months = joined_full.select(pl.col("month").drop_nulls().n_unique()).item()
    month_count = int(unique_months) if isinstance(unique_months, int | float) else 0

    charts_full: list[ChartCandidate] = []
    charts_l4l: list[ChartCandidate] = []
    # Base stacked charts
    charts_full.append(
        build_dimension_stacked(
            joined=joined_full,
            category_key=category_key,
            category_label=category_label,
            retailers=retailers,
            brands=brands,
            universe="full",
            segment=retailer_dim,
            placeholder_values=placeholder_values,
            top_n=8,
            aggregation="monthly",
        )
    )
    try:
        charts_full.append(
            build_total_combo_absolute(
                joined=joined_full,
                category_key=category_key,
                category_label=category_label,
                retailers=retailers,
                brands=brands,
                universe="full",
                bar_metric="sales",
                line_metric="units",
            )
        )
    except ChartBuildError:
        pass
    for segment, top_n in (
        (retailer_dim, 8),
        (brand, 10),
    ):
        try:
            charts_full.append(
                build_dimension_stacked_absolute(
                    joined=joined_full,
                    category_key=category_key,
                    category_label=category_label,
                    retailers=retailers,
                    brands=brands,
                    universe="full",
                    segment=segment,
                    placeholder_values=placeholder_values,
                    metric_column="sales",
                    top_n=top_n,
                )
            )
        except ChartBuildError:
            continue
    charts_full.append(
        build_dimension_stacked(
            joined=joined_full,
            category_key=category_key,
            category_label=category_label,
            retailers=retailers,
            brands=brands,
            universe="full",
            segment=brand,
            placeholder_values=placeholder_values,
            top_n=10,
            aggregation="monthly",
        )
    )
    if price_band is not None:
        try:
            charts_full.append(
                build_dimension_stacked(
                    joined=joined_full,
                    category_key=category_key,
                    category_label=category_label,
                    retailers=retailers,
                    brands=brands,
                    universe="full",
                    segment=price_band,
                    placeholder_values=placeholder_values,
                    top_n=5,
                    aggregation="monthly",
                )
            )
        except ChartBuildError:
            pass
        try:
            charts_full.append(
                build_dimension_stacked_absolute(
                    joined=joined_full,
                    category_key=category_key,
                    category_label=category_label,
                    retailers=retailers,
                    brands=brands,
                    universe="full",
                    segment=price_band,
                    placeholder_values=placeholder_values,
                    metric_column="sales",
                    top_n=5,
                )
            )
        except ChartBuildError:
            pass
    if pareto is not None:
        try:
            charts_full.append(
                build_dimension_stacked(
                    joined=joined_full,
                    category_key=category_key,
                    category_label=category_label,
                    retailers=retailers,
                    brands=brands,
                    universe="full",
                    segment=pareto,
                    placeholder_values=placeholder_values,
                    top_n=4,
                    aggregation="monthly",
                )
            )
        except ChartBuildError:
            pass
        try:
            charts_full.append(
                build_dimension_stacked_absolute(
                    joined=joined_full,
                    category_key=category_key,
                    category_label=category_label,
                    retailers=retailers,
                    brands=brands,
                    universe="full",
                    segment=pareto,
                    placeholder_values=placeholder_values,
                    metric_column="sales",
                    top_n=4,
                )
            )
        except ChartBuildError:
            pass
    # Stacked for each attribute
    for attr in attributes:
        try:
            charts_l4l.append(
                build_dimension_stacked(
                    joined=joined_l4l,
                    category_key=category_key,
                    category_label=category_label,
                    retailers=retailers,
                    brands=brands,
                    universe="l4l",
                    segment=attr,
                    placeholder_values=placeholder_values,
                    top_n=8,
                    aggregation="monthly",
                )
            )
        except ChartBuildError:
            continue

    pair_attrs = choose_pair_attributes(
        attributes, dict(attribute_value_counts), max_count=6
    )
    multi_retailer = len({r.strip().lower() for r in retailers if r.strip()}) > 1
    rolling_pair_attrs = pair_attrs[:2]

    if multi_retailer:
        for attr in pair_attrs:
            try:
                charts_l4l.append(
                    build_dimension_stacked_facets(
                        joined=joined_l4l,
                        category_key=category_key,
                        category_label=category_label,
                        retailers=retailers,
                        brands=brands,
                        universe="l4l",
                        segment=attr,
                        facet=retailer_dim,
                        placeholder_values=placeholder_values,
                        top_n=6,
                        aggregation="monthly",
                    )
                )
            except ChartBuildError:
                continue

    for attr in pair_attrs:
        try:
            charts_l4l.append(
                build_brand_attribute_slope(
                    joined=joined_l4l,
                    category_key=category_key,
                    category_label=category_label,
                    retailers=retailers,
                    brands=brands,
                    universe="l4l",
                    brand=brand,
                    attribute=attr,
                    placeholder_values=placeholder_values,
                    facet=None,
                )
            )
        except ChartBuildError:
            pass
        if multi_retailer:
            try:
                charts_l4l.append(
                    build_brand_attribute_slope(
                        joined=joined_l4l,
                        category_key=category_key,
                        category_label=category_label,
                        retailers=retailers,
                        brands=brands,
                        universe="l4l",
                        brand=brand,
                        attribute=attr,
                        placeholder_values=placeholder_values,
                        facet=retailer_dim,
                    )
                )
            except ChartBuildError:
                pass
    for attr in rolling_pair_attrs:
        try:
            charts_l4l.append(
                build_brand_attribute_slope(
                    joined=joined_l4l,
                    category_key=category_key,
                    category_label=category_label,
                    retailers=retailers,
                    brands=brands,
                    universe="l4l",
                    brand=brand,
                    attribute=attr,
                    placeholder_values=placeholder_values,
                    facet=None,
                    rolling_window=True,
                    window_months=12,
                )
            )
        except ChartBuildError:
            pass
        if multi_retailer:
            try:
                charts_l4l.append(
                    build_brand_attribute_slope(
                        joined=joined_l4l,
                        category_key=category_key,
                        category_label=category_label,
                        retailers=retailers,
                        brands=brands,
                        universe="l4l",
                        brand=brand,
                        attribute=attr,
                        placeholder_values=placeholder_values,
                        facet=retailer_dim,
                        rolling_window=True,
                        window_months=12,
                    )
                )
            except ChartBuildError:
                pass

    def _tag_universe(charts: list[ChartCandidate], note: str) -> list[ChartCandidate]:
        tagged: list[ChartCandidate] = []
        suffix = f"Universe: {note}."
        for candidate in charts:
            subtitle = (candidate.chart.subtitle or "").strip()
            if "like-for-like" in note and subtitle.lower().startswith(
                "sales share % of category"
            ):
                subtitle = subtitle.replace(
                    "Sales share % of category",
                    "Sales share % of like-for-like universe",
                    1,
                )
            next_subtitle = f"{subtitle} {suffix}".strip() if subtitle else suffix
            tagged.append(
                ChartCandidate(
                    chart=replace(candidate.chart, subtitle=next_subtitle),
                    csv_rows=candidate.csv_rows,
                )
            )
        return tagged

    charts = _tag_universe(
        charts_full, "full category (all sales in scope)"
    ) + _tag_universe(
        charts_l4l,
        "like-for-like (only SKUs with PDP-derived attributes)",
    )
    if dataset:
        dataset_slug = _safe_slug(dataset)
        prefix = f"{dataset_slug}_"
        tagged_charts: list[ChartCandidate] = []
        for candidate in charts:
            chart = candidate.chart
            if chart.chart_id.startswith(prefix):
                tagged_charts.append(candidate)
                continue
            new_chart_id = f"{prefix}{chart.chart_id}"
            payload = dict(chart.payload)
            payload["instance_id"] = new_chart_id
            tagged_charts.append(
                ChartCandidate(
                    chart=replace(chart, chart_id=new_chart_id, payload=payload),
                    csv_rows=candidate.csv_rows,
                )
            )
        charts = tagged_charts

    if not charts:
        raise ChartBuildError("No chart candidates could be built for this scope.")

    naming = get_naming_params()
    step = naming["reviewBriefChartInterpretationQuery"]
    system_prompt = _build_interpretation_system_prompt()
    prompts = [
        _build_interpretation_prompt(
            _chart_to_prompt_payload(c.chart),
            requested_scope=requested_scope,
        )
        for c in charts
    ]
    raw_results = run_step_json(llm_wrapper, step, system_prompt, prompts)
    interpretations: dict[str, ChartInterpretation] = {}
    for chart, raw in zip(charts, raw_results):
        if isinstance(raw, Mapping):
            interp = _parse_interpretation(raw, chart.chart.chart_id)
        else:
            interp = ChartInterpretation(
                chart_id=chart.chart.chart_id,
                headline="",
                bullets=[],
                relevance=0,
            )
        interpretations[chart.chart.chart_id] = interp

    ranked = sorted(
        charts,
        key=lambda c: (
            interpretations.get(
                c.chart.chart_id, ChartInterpretation(c.chart.chart_id, "", [], 0)
            ).relevance,
            c.chart.title,
        ),
        reverse=True,
    )
    selected: list[ChartPayload] = []
    for candidate in ranked:
        interp = interpretations.get(candidate.chart.chart_id)
        if interp and interp.relevance >= 50:
            selected.append(candidate.chart)
    if len(selected) < min_selected_charts:
        selected = [c.chart for c in ranked[:min_selected_charts]]
    if len(selected) > max_selected_charts:
        selected = selected[:max_selected_charts]
    selected = _apply_model_highlights(selected, interpretations)

    narrative: ReviewBriefNarrative | None = None
    naming = get_naming_params()
    try:
        narrative_step = naming["reviewBriefNarrativeQuery"]
        narrative_results = run_step_json(
            llm_wrapper,
            narrative_step,
            _build_narrative_system_prompt(),
            [
                _build_narrative_prompt(
                    category_label=category_label,
                    retailers=retailers,
                    start_month=start_month.isoformat(),
                    end_month=end_month.isoformat(),
                    charts=selected,
                    interpretations=interpretations,
                    requested_scope=requested_scope,
                )
            ],
            extra_body={"reasoning": {"effort": "high"}},
        )
        narrative_raw = narrative_results[0] if narrative_results else None
        if isinstance(narrative_raw, Mapping):
            narrative = _parse_narrative(
                narrative_raw, valid_chart_ids={c.chart_id for c in selected}
            )
    except Exception as exc:  # noqa: BLE001 - best-effort narrative layer
        _logger.warning(
            "Review brief narrative step failed; continuing without it: %s", exc
        )

    title_by_chart_id: dict[str, str] = {}
    if narrative is not None:
        for slide in narrative.suggested_flow:
            slide_title = str(slide.title or "").strip()
            if not slide_title:
                continue
            for raw_chart_id in slide.chart_ids:
                chart_id = str(raw_chart_id or "").strip()
                if chart_id and chart_id not in title_by_chart_id:
                    title_by_chart_id[chart_id] = slide_title

    deterministic_flow = _build_single_chart_flow(
        charts=selected,
        interpretations=interpretations,
        preferred_titles=title_by_chart_id,
    )
    if narrative is None:
        narrative = ReviewBriefNarrative(
            executive_narrative="",
            key_takeaways=[],
            suggested_flow=deterministic_flow,
        )
    else:
        narrative = ReviewBriefNarrative(
            executive_narrative=narrative.executive_narrative,
            key_takeaways=narrative.key_takeaways,
            suggested_flow=_merge_suggested_flow(
                narrative.suggested_flow,
                deterministic_flow,
            ),
        )

    markdown = render_review_brief_markdown(
        job_id=job_id,
        chart_view_base_url=chart_view_base_url,
        category_key=category_key,
        category_label=category_label,
        retailers=retailers,
        brands=brands,
        start_month=start_month.isoformat(),
        end_month=end_month.isoformat(),
        charts=selected,
        interpretations=interpretations,
        narrative=narrative,
    )

    final_output_dir = output_dir / "jobs" / job_id if job_id else output_dir
    final_output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    file_stub = _safe_slug(f"{category_label}-{','.join(retailers)}-{timestamp}")
    md_path = final_output_dir / f"{file_stub}.md"
    json_path = final_output_dir / f"{file_stub}.json"
    chart_catalog = _merge_selected_charts_into_catalog(charts, selected)
    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "category": category_label,
                "retailers": retailers,
                "dataset": dataset,
                "prompt_style": str(prompt_style or "").strip().lower() or None,
                "chart_palette": str(chart_palette or "").strip().lower() or None,
                "start_month": start_month.isoformat(),
                "end_month": end_month.isoformat(),
                "charts": [_chart_to_prompt_payload(chart) for chart in chart_catalog],
                "interpretations": {k: asdict(v) for k, v in interpretations.items()},
                "selected": [c.chart_id for c in selected],
                "narrative": asdict(narrative) if narrative is not None else None,
                "requested_scope": dict(requested_scope or {}),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return ReviewBriefResult(
        markdown=markdown,
        output_path=str(md_path),
        charts_json_path=str(json_path),
        total_charts=len(charts),
        selected_charts=len(selected),
    )


def _chart_to_prompt_payload(chart) -> dict[str, object]:
    base = {
        "chart_id": chart.chart_id,
        "definition_id": chart.definition_id,
        "chart_type": chart.chart_type,
        "title": chart.title,
        "subtitle": chart.subtitle,
        "normalization": chart.normalization,
        "category_key": chart.category_key,
        "category_label": chart.category_label,
        "retailers": chart.retailers,
        "brands": chart.brands,
        "universe": chart.universe,
        "start_month": chart.start_month,
        "end_month": chart.end_month,
        "dimensions": [asdict(dim) for dim in chart.dimensions],
        "facet": asdict(chart.facet) if chart.facet is not None else None,
    }
    payload = chart.payload
    if isinstance(payload, dict):
        base.update(payload)
    return base
