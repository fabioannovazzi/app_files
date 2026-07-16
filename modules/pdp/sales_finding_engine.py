from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from modules.pdp.sales_brief_config import (
    ATTRIBUTE_EMERGING_MAX_START_SHARE_PCT,
    ATTRIBUTE_EMERGING_MIN_DELTA_PP,
    ATTRIBUTE_EMERGING_MIN_END_SHARE_PCT,
    ATTRIBUTE_POLARIZATION_MIN_DECLINER_DELTA_PP,
    ATTRIBUTE_POLARIZATION_MIN_GAINER_DELTA_PP,
    ATTRIBUTE_POLARIZATION_MIN_START_SHARE_PCT,
    ATTRIBUTE_SHARE_SHIFT_MIN_DELTA_PP,
    BRAND_CHALLENGER_MIN_DELTA_PP,
    BRAND_CHALLENGER_MIN_END_SHARE_PCT,
    BRAND_LEADER_MIN_SHARE_PCT,
    BRAND_REDISTRIBUTION_MIN_TOTAL_PP,
    DEFAULT_SHORTLIST_MAX_FINDINGS,
    DEFAULT_SHORTLIST_MAX_PER_LENS,
    FINDING_SCORE_HIGH_THRESHOLD,
    FINDING_SCORE_MEDIUM_THRESHOLD,
    GROWTH_LEVEL_SHIFT_MIN_RELATIVE_CHANGE,
    GROWTH_SUSTAINED_MIN_DIRECTION_RATIO,
    GROWTH_SUSTAINED_MIN_RELATIVE_CHANGE,
    GROWTH_VOLATILITY_MIN_OBSERVATIONS,
    GROWTH_VOLATILITY_MIN_SPIKE_RATIO,
    PRICE_MID_SHIFT_MAX_VALUE_DELTA_PP,
    PRICE_MID_SHIFT_MIN_MID_DELTA_PP,
    PRICE_PREMIUMIZATION_MAX_VALUE_DELTA_PP,
    PRICE_PREMIUMIZATION_MIN_PREMIUM_DELTA_PP,
    PRICE_STRUCTURE_DOMINANT_MIN_DELTA_PP,
    PRICE_VALUE_SHIFT_MAX_PREMIUM_DELTA_PP,
    PRICE_VALUE_SHIFT_MIN_VALUE_DELTA_PP,
)
from modules.pdp.sales_chart_catalog import (
    EvidenceRole,
    Lens,
    SalesChartCatalogAction,
    ScopeSupport,
    TimeScope,
    load_sales_chart_catalog,
)

__all__ = [
    "AnalysisMode",
    "AnalysisScope",
    "FindingCandidate",
    "FindingClaimMethod",
    "FindingClaimSpec",
    "FindingClaimStatus",
    "FindingEvidenceOption",
    "FindingEvidencePlan",
    "FindingEngineInput",
    "FindingLensSpec",
    "FindingMetric",
    "FindingScore",
    "build_analysis_scope",
    "build_attribute_mix_numeric_payloads",
    "build_finding_engine_input",
    "build_growth_size_candidates",
    "build_brand_shift_candidates",
    "build_slope_numeric_payload",
    "build_stacked_share_numeric_payload",
    "build_total_combo_numeric_payload",
    "build_attribute_mix_candidates",
    "build_price_value_capture_candidates",
    "build_ranked_finding_shortlist",
    "resolve_finding_evidence_plan",
    "get_finding_lens_spec",
    "rank_and_deduplicate_findings",
    "list_enabled_finding_claim_specs",
    "list_initial_finding_claim_specs",
    "list_initial_finding_lens_specs",
]

FindingConfidence = Literal["high", "medium", "low"]
AnalysisMode = Literal["market_report", "brand_report"]
FindingClaimMethod = Literal["direct_observed", "derived_trusted"]
FindingClaimStatus = Literal["enabled", "deferred"]


@dataclass(frozen=True, slots=True)
class AnalysisScope:
    report_mode: AnalysisMode
    dataset: str | None
    retailers: tuple[str, ...]
    categories: tuple[str, ...]
    brands: tuple[str, ...]
    price_bands: tuple[str, ...]
    pareto_classes: tuple[str, ...]
    attribute_filters: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class FindingLensSpec:
    lens: Lens
    label: str
    description: str
    scope_support: tuple[ScopeSupport, ...]
    preferred_time_scopes: tuple[TimeScope, ...]
    preferred_evidence_roles: tuple[EvidenceRole, ...]
    preferred_chart_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FindingClaimSpec:
    lens: Lens
    claim_key: str
    label: str
    description: str
    method: FindingClaimMethod
    status: FindingClaimStatus
    preferred_chart_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FindingMetric:
    key: str
    label: str
    value: float | None
    unit: str


@dataclass(frozen=True, slots=True)
class FindingScore:
    magnitude: float
    persistence: float
    divergence: float
    uniqueness: float
    total: float


@dataclass(frozen=True, slots=True)
class FindingEngineInput:
    lens: Lens
    scope: ScopeSupport
    analysis_scope: AnalysisScope
    selection_context: Mapping[str, Any]
    claim_specs: tuple[FindingClaimSpec, ...]
    candidate_actions: tuple[SalesChartCatalogAction, ...]
    numeric_payloads: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class FindingCandidate:
    lens: Lens
    scope: ScopeSupport
    claim: str
    chart_key: str
    chart_id: str | None
    supporting_chart_keys: tuple[str, ...]
    evidence_bullets: tuple[str, ...]
    metrics: tuple[FindingMetric, ...]
    score: FindingScore
    confidence: FindingConfidence
    caution: str | None = None
    claim_key: str = ""
    story_key: str | None = None


@dataclass(frozen=True, slots=True)
class FindingEvidenceOption:
    chart_key: str
    chart_label: str
    chart_type: str
    chart_id: str | None
    chart_request: Mapping[str, Any] | None
    has_payload: bool
    is_primary: bool


@dataclass(frozen=True, slots=True)
class FindingEvidencePlan:
    candidate: FindingCandidate
    primary_option: FindingEvidenceOption | None
    supporting_options: tuple[FindingEvidenceOption, ...]
    missing_preferred_chart_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _MonthlySeriesPoint:
    month: str
    value: float


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, Mapping):
            return dumped
    if hasattr(value, "__dict__"):
        return {
            key: current
            for key, current in vars(value).items()
            if not key.startswith("_")
        }
    return {}


def _metric_response_rows(response: Any) -> tuple[Mapping[str, Any], ...]:
    raw_rows = getattr(response, "rows", ())
    if not isinstance(raw_rows, (list, tuple)):
        return ()
    rows: list[Mapping[str, Any]] = []
    for raw_row in raw_rows:
        row = _as_mapping(raw_row)
        if row:
            rows.append(row)
    return tuple(rows)


def _metric_response_headers(response: Any) -> tuple[str, ...]:
    raw_headers = getattr(response, "dimension_headers", ())
    if not isinstance(raw_headers, (list, tuple)):
        return ()
    return tuple(str(header).strip() for header in raw_headers if str(header).strip())


def _dimension_token(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _dimension_label(value: object) -> str:
    text = str(value or "").strip().replace("_", " ")
    return " ".join(text.split())


def _lookup_dimension_value(
    dimension_map: Mapping[str, Any],
    *,
    dimension_label: str,
    segment_key: str,
) -> str:
    direct_keys = (
        dimension_label,
        segment_key,
    )
    for key in direct_keys:
        value = dimension_map.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    normalized_label = _dimension_token(dimension_label)
    normalized_segment_key = _dimension_token(segment_key)
    for key, value in dimension_map.items():
        if _dimension_token(key) in {normalized_label, normalized_segment_key}:
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def build_total_combo_numeric_payload(
    metrics_response: Any,
    *,
    chart_id: str | None = None,
    chart_request: Mapping[str, Any] | None = None,
    metric: str = "sales",
    unit: str = "USD",
    window_months: int | None = None,
) -> dict[str, Any]:
    rows = _metric_response_rows(metrics_response)
    monthly_values: dict[str, float] = {}
    monthly_units: dict[str, float] = {}
    metric_key = str(metric).strip().lower() or "sales"
    for row in rows:
        month = str(row.get("month") or "").strip()
        if not month:
            continue
        try:
            value = float(row.get(metric_key) or 0.0)
            units = float(row.get("units") or 0.0)
        except (TypeError, ValueError):
            continue
        monthly_values[month] = monthly_values.get(month, 0.0) + value
        monthly_units[month] = monthly_units.get(month, 0.0) + units
    payload = {
        "chart_id": chart_id,
        "metric": metric_key,
        "unit": unit,
        "window_months": window_months,
        "monthly_series": [
            {
                "month": month,
                metric_key: monthly_values[month],
                "units": monthly_units[month],
            }
            for month in sorted(monthly_values)
        ],
    }
    if chart_request is not None:
        payload["chart_request"] = dict(chart_request)
    return payload


def build_stacked_share_numeric_payload(
    metrics_response: Any,
    *,
    chart_id: str | None = None,
    chart_request: Mapping[str, Any] | None = None,
    segment_key: str | None = None,
    dimension_label: str | None = None,
) -> dict[str, Any]:
    rows = _metric_response_rows(metrics_response)
    headers = _metric_response_headers(metrics_response)
    resolved_label = (
        str(dimension_label).strip()
        if str(dimension_label or "").strip()
        else (headers[0] if headers else (segment_key or "segment"))
    )
    resolved_segment_key = (
        str(segment_key).strip()
        if str(segment_key or "").strip()
        else _dimension_token(resolved_label) or "segment"
    )
    payload_rows: list[dict[str, Any]] = []
    for row in rows:
        month = str(row.get("month") or "").strip()
        dimensions = row.get("dimensions")
        dimension_map = dimensions if isinstance(dimensions, Mapping) else {}
        segment = (
            _lookup_dimension_value(
                dimension_map,
                dimension_label=resolved_label,
                segment_key=resolved_segment_key,
            )
            or str(row.get(resolved_segment_key) or row.get("segment") or "").strip()
        )
        if not month or not segment:
            continue
        try:
            share_pct = round(float(row.get("sales_share") or 0.0) * 100.0, 4)
        except (TypeError, ValueError):
            continue
        payload_rows.append(
            {"month": month, "segment": segment, "share_pct": share_pct}
        )
    payload = {
        "chart_id": chart_id,
        "segment_key": resolved_segment_key,
        "dimension_label": resolved_label,
        "rows": payload_rows,
    }
    if chart_request is not None:
        payload["chart_request"] = dict(chart_request)
    return payload


def build_slope_numeric_payload(
    metrics_response: Any,
    *,
    chart_id: str | None = None,
    chart_request: Mapping[str, Any] | None = None,
    segment_key: str | None = None,
    dimension_label: str | None = None,
    start_month: str | None = None,
    end_month: str | None = None,
) -> dict[str, Any]:
    rows = _metric_response_rows(metrics_response)
    headers = _metric_response_headers(metrics_response)
    resolved_label = (
        str(dimension_label).strip()
        if str(dimension_label or "").strip()
        else (headers[0] if headers else (segment_key or "segment"))
    )
    resolved_segment_key = (
        str(segment_key).strip()
        if str(segment_key or "").strip()
        else _dimension_token(resolved_label) or "segment"
    )
    months = sorted(
        {
            str(row.get("month") or "").strip()
            for row in rows
            if str(row.get("month") or "").strip()
        }
    )
    if not months:
        payload = {
            "chart_id": chart_id,
            "segment_key": resolved_segment_key,
            "dimension_label": resolved_label,
            "rows": [],
        }
        if chart_request is not None:
            payload["chart_request"] = dict(chart_request)
        return payload
    resolved_start_month = start_month or months[0]
    resolved_end_month = end_month or months[-1]
    start_map: dict[str, float] = {}
    end_map: dict[str, float] = {}
    for row in rows:
        month = str(row.get("month") or "").strip()
        dimensions = row.get("dimensions")
        dimension_map = dimensions if isinstance(dimensions, Mapping) else {}
        segment = (
            _lookup_dimension_value(
                dimension_map,
                dimension_label=resolved_label,
                segment_key=resolved_segment_key,
            )
            or str(
                row.get(resolved_segment_key)
                or row.get("brand")
                or row.get("segment")
                or ""
            ).strip()
        )
        if not month or not segment:
            continue
        try:
            share_pct = round(float(row.get("sales_share") or 0.0) * 100.0, 4)
        except (TypeError, ValueError):
            continue
        if month == resolved_start_month:
            start_map[segment] = share_pct
        if month == resolved_end_month:
            end_map[segment] = share_pct
    payload = {
        "chart_id": chart_id,
        "segment_key": resolved_segment_key,
        "dimension_label": resolved_label,
        "rows": [
            {
                "segment": segment,
                "start_share_pct": start_map.get(segment, 0.0),
                "end_share_pct": end_map.get(segment, 0.0),
            }
            for segment in sorted(set(start_map) | set(end_map))
            if segment
        ],
    }
    if chart_request is not None:
        payload["chart_request"] = dict(chart_request)
    return payload


def build_attribute_mix_numeric_payloads(
    metrics_responses_by_dimension: Mapping[str, Any],
    *,
    chart_id_prefix: str = "attribute",
    chart_metadata_by_dimension: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for dimension_key, metrics_response in metrics_responses_by_dimension.items():
        token = _dimension_token(dimension_key)
        if not token:
            continue
        metadata = (
            chart_metadata_by_dimension.get(token)
            if isinstance(chart_metadata_by_dimension, Mapping)
            else None
        )
        payloads[token] = build_stacked_share_numeric_payload(
            metrics_response,
            chart_id=(
                str(metadata.get("chart_id") or "").strip()
                if isinstance(metadata, Mapping)
                else f"{chart_id_prefix}-{token}"
            ),
            chart_request=(
                metadata.get("chart_request") if isinstance(metadata, Mapping) else None
            ),
            segment_key=token,
            dimension_label=_dimension_label(dimension_key),
        )
    return payloads


def _numeric_payload_aliases_for_lens(lens: Lens, chart_key: str) -> tuple[str, ...]:
    alias_map: dict[tuple[Lens, str], tuple[str, ...]] = {
        (
            "growth_size",
            "total_combo",
        ): ("total_combo_rolling_12", "total_combo_monthly", "total_combo"),
        ("brand_shifts", "slope"): ("slope_brand", "slope"),
        (
            "price_value_capture",
            "stacked_share",
        ): ("stacked_share_price_band", "stacked_share"),
        (
            "attribute_mix",
            "stacked_share",
        ): ("stacked_share_attribute", "stacked_share"),
    }
    return alias_map.get((lens, chart_key), (chart_key,))


def _resolve_numeric_payload(
    engine_input: FindingEngineInput,
    *,
    chart_key: str,
) -> Mapping[str, Any]:
    for payload_key in _numeric_payload_aliases_for_lens(engine_input.lens, chart_key):
        payload = engine_input.numeric_payloads.get(payload_key)
        if isinstance(payload, Mapping):
            return payload
    if engine_input.lens == "attribute_mix" and chart_key == "stacked_share":
        multi_payloads = engine_input.numeric_payloads.get(
            "stacked_share_attribute_payloads"
        )
        if isinstance(multi_payloads, Mapping):
            for payload in multi_payloads.values():
                if isinstance(payload, Mapping):
                    return payload
    return {}


def _resolve_primary_chart_key(
    engine_input: FindingEngineInput,
    preferred_chart_keys: tuple[str, ...],
) -> str:
    for chart_key in preferred_chart_keys:
        payload = _resolve_numeric_payload(engine_input, chart_key=chart_key)
        if payload:
            return chart_key
    return preferred_chart_keys[0]


def _resolve_growth_total_combo_payload(
    engine_input: FindingEngineInput,
    *,
    series_kind: Literal["rolling_12", "monthly"],
) -> Mapping[str, Any]:
    alias_order = (
        ("total_combo_rolling_12", "total_combo")
        if series_kind == "rolling_12"
        else ("total_combo_monthly", "total_combo")
    )
    for payload_key in alias_order:
        payload = engine_input.numeric_payloads.get(payload_key)
        if isinstance(payload, Mapping):
            return payload
    return {}


def _resolve_candidate_payload(
    engine_input: FindingEngineInput,
    *,
    candidate: FindingCandidate,
    chart_key: str,
) -> Mapping[str, Any] | None:
    matched_payload = None
    for payload_key in _numeric_payload_aliases_for_lens(candidate.lens, chart_key):
        current_payload = engine_input.numeric_payloads.get(payload_key)
        if isinstance(current_payload, Mapping):
            chart_id = str(current_payload.get("chart_id") or "").strip() or None
            if candidate.chart_id and chart_id == candidate.chart_id:
                return current_payload
            if matched_payload is None:
                matched_payload = current_payload
    if matched_payload is not None:
        return matched_payload
    if candidate.lens == "attribute_mix" and chart_key == "stacked_share":
        multi_payloads = engine_input.numeric_payloads.get(
            "stacked_share_attribute_payloads"
        )
        if isinstance(multi_payloads, Mapping):
            matched_payload = None
            for payload in multi_payloads.values():
                if not isinstance(payload, Mapping):
                    continue
                chart_id = str(payload.get("chart_id") or "").strip() or None
                if candidate.chart_id and chart_id == candidate.chart_id:
                    return payload
                if matched_payload is None:
                    matched_payload = payload
            return matched_payload
    return None


def list_initial_finding_lens_specs() -> tuple[FindingLensSpec, ...]:
    return (
        FindingLensSpec(
            lens="growth_size",
            label="Growth / Size",
            description="Detect meaningful changes in category size, sales, units, or average price level over time.",
            scope_support=("single_category", "category_vs_market", "cross_category"),
            preferred_time_scopes=("trend", "change"),
            preferred_evidence_roles=("primary",),
            preferred_chart_keys=(
                "total_combo",
                "stacked_column",
                "area_absolute",
                "slope",
            ),
        ),
        FindingLensSpec(
            lens="price_value_capture",
            label="Price / Value Capture",
            description="Explain where value is moving across price bands, premiumization, or price/mix shifts.",
            scope_support=("single_category", "category_vs_market"),
            preferred_time_scopes=("trend", "change", "snapshot"),
            preferred_evidence_roles=("primary", "supporting"),
            preferred_chart_keys=(
                "stacked_share",
                "slope",
                "stacked_column",
                "area_absolute",
            ),
        ),
        FindingLensSpec(
            lens="brand_shifts",
            label="Brand Shifts",
            description="Identify leadership changes, share gains/losses, challenger growth, and redistribution across brands.",
            scope_support=("single_category", "category_vs_market"),
            preferred_time_scopes=("change", "trend", "snapshot"),
            preferred_evidence_roles=("primary", "supporting"),
            preferred_chart_keys=("slope", "stacked_share", "pareto"),
        ),
        FindingLensSpec(
            lens="attribute_mix",
            label="Attribute Mix",
            description="Track structural movement across form, finish, coverage, and related product attributes.",
            scope_support=("single_category", "category_vs_market"),
            preferred_time_scopes=("trend", "change", "snapshot"),
            preferred_evidence_roles=("primary", "supporting"),
            preferred_chart_keys=(
                "stacked_share",
                "slope",
                "stacked_column",
                "pareto",
                "stacked_pareto",
            ),
        ),
    )


def list_initial_finding_claim_specs(
    lens: Lens | None = None,
) -> tuple[FindingClaimSpec, ...]:
    specs = (
        FindingClaimSpec(
            lens="growth_size",
            claim_key="level_shift",
            label="Level shift",
            description="Directly observe whether the slice became materially larger or smaller over the comparison window.",
            method="direct_observed",
            status="enabled",
            preferred_chart_keys=("total_combo", "area_absolute", "stacked_column"),
        ),
        FindingClaimSpec(
            lens="growth_size",
            claim_key="sustained_growth_or_decline",
            label="Sustained growth or decline",
            description="Check whether growth or contraction persisted across the period rather than appearing only as a one-off jump.",
            method="direct_observed",
            status="enabled",
            preferred_chart_keys=("area_absolute", "total_combo", "stacked_column"),
        ),
        FindingClaimSpec(
            lens="growth_size",
            claim_key="volatility_or_spike",
            label="Volatility or spike pattern",
            description="Surface unusually spiky or seasonal growth paths when they are part of the observed trend.",
            method="direct_observed",
            status="enabled",
            preferred_chart_keys=("area_absolute", "total_combo"),
        ),
        FindingClaimSpec(
            lens="growth_size",
            claim_key="units_price_variance",
            label="Units vs price variance",
            description="Attribute sales change to units, price, or both using a trusted decomposition, once that operator is wired in.",
            method="derived_trusted",
            status="deferred",
            preferred_chart_keys=("total_combo",),
        ),
        FindingClaimSpec(
            lens="price_value_capture",
            claim_key="price_band_mix_shift",
            label="Price-band mix shift",
            description="Directly observe whether value moved across premium, mid, and value bands over time.",
            method="direct_observed",
            status="enabled",
            preferred_chart_keys=("stacked_share", "stacked_column", "area_absolute"),
        ),
        FindingClaimSpec(
            lens="price_value_capture",
            claim_key="premiumization_or_value_shift",
            label="Premiumization or value shift",
            description="Identify whether the market tilted toward premium/mid/value without relying on price decomposition math.",
            method="direct_observed",
            status="enabled",
            preferred_chart_keys=("stacked_share", "slope", "stacked_column"),
        ),
        FindingClaimSpec(
            lens="brand_shifts",
            claim_key="leader_change",
            label="Leader change",
            description="Detect clear changes in leading share positions across the selected scope.",
            method="direct_observed",
            status="enabled",
            preferred_chart_keys=("slope", "stacked_share", "pareto"),
        ),
        FindingClaimSpec(
            lens="brand_shifts",
            claim_key="challenger_gain_or_loss",
            label="Challenger gain or loss",
            description="Surface meaningful gains or declines among challenger brands with enough weight to matter.",
            method="direct_observed",
            status="enabled",
            preferred_chart_keys=("slope", "stacked_share", "pareto"),
        ),
        FindingClaimSpec(
            lens="brand_shifts",
            claim_key="share_redistribution",
            label="Share redistribution",
            description="Describe broader redistribution across brands when no single leader-change story fully explains the movement.",
            method="direct_observed",
            status="enabled",
            preferred_chart_keys=("slope", "stacked_share", "pareto"),
        ),
        FindingClaimSpec(
            lens="attribute_mix",
            claim_key="attribute_share_shift",
            label="Attribute share shift",
            description="Detect direct mix changes across form, finish, coverage, or similar attributes.",
            method="direct_observed",
            status="enabled",
            preferred_chart_keys=("stacked_share", "slope", "stacked_column"),
        ),
        FindingClaimSpec(
            lens="attribute_mix",
            claim_key="emerging_attribute_pocket",
            label="Emerging attribute pocket",
            description="Surface unusually strong movement in a smaller attribute bucket only when it clears a stronger threshold.",
            method="direct_observed",
            status="enabled",
            preferred_chart_keys=("slope", "stacked_share", "pareto"),
        ),
        FindingClaimSpec(
            lens="attribute_mix",
            claim_key="attribute_polarization",
            label="Attribute polarization",
            description="Capture split movement toward two different attribute poles when the middle compresses or fragments.",
            method="direct_observed",
            status="enabled",
            preferred_chart_keys=("stacked_share", "stacked_pareto"),
        ),
    )
    if lens is None:
        return specs
    return tuple(spec for spec in specs if spec.lens == lens)


def list_enabled_finding_claim_specs(lens: Lens) -> tuple[FindingClaimSpec, ...]:
    return tuple(
        spec
        for spec in list_initial_finding_claim_specs(lens)
        if spec.status == "enabled"
    )


def get_finding_lens_spec(lens: Lens) -> FindingLensSpec:
    for spec in list_initial_finding_lens_specs():
        if spec.lens == lens:
            return spec
    raise KeyError(f"Unsupported finding lens: {lens}")


def build_analysis_scope(
    *,
    dataset: str | None = None,
    retailers: tuple[str, ...] | list[str] = (),
    categories: tuple[str, ...] | list[str] = (),
    brands: tuple[str, ...] | list[str] = (),
    price_bands: tuple[str, ...] | list[str] = (),
    pareto_classes: tuple[str, ...] | list[str] = (),
    attribute_filters: Mapping[str, tuple[str, ...] | list[str]] | None = None,
) -> AnalysisScope:
    def _normalize_values(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        return tuple(
            value.strip() for value in (str(item) for item in values) if value.strip()
        )

    normalized_brands = _normalize_values(brands)
    normalized_attributes = {
        str(key).strip(): _normalize_values(list(values))
        for key, values in (attribute_filters or {}).items()
        if str(key).strip()
    }
    return AnalysisScope(
        report_mode="brand_report" if normalized_brands else "market_report",
        dataset=str(dataset).strip() if dataset and str(dataset).strip() else None,
        retailers=_normalize_values(retailers),
        categories=_normalize_values(categories),
        brands=normalized_brands,
        price_bands=_normalize_values(price_bands),
        pareto_classes=_normalize_values(pareto_classes),
        attribute_filters=normalized_attributes,
    )


def build_finding_engine_input(
    *,
    lens: Lens,
    scope: ScopeSupport = "single_category",
    analysis_scope: AnalysisScope | None = None,
    selection_context: Mapping[str, Any],
    numeric_payloads: Mapping[str, Mapping[str, Any]] | None = None,
) -> FindingEngineInput:
    spec = get_finding_lens_spec(lens)
    if scope not in spec.scope_support:
        raise ValueError(f"Lens {lens!r} does not support scope {scope!r}.")

    catalog = load_sales_chart_catalog()
    candidate_actions = tuple(
        action
        for action in catalog.actions.values()
        if action.brief_enabled
        and lens in action.lenses
        and scope in action.scope_support
        and action.evidence_role in spec.preferred_evidence_roles
    )
    ordered_actions = tuple(
        sorted(
            candidate_actions,
            key=lambda action: (
                spec.preferred_chart_keys.index(action.chart_key)
                if action.chart_key in spec.preferred_chart_keys
                else len(spec.preferred_chart_keys)
            ),
        )
    )
    return FindingEngineInput(
        lens=lens,
        scope=scope,
        analysis_scope=analysis_scope or build_analysis_scope(),
        selection_context=dict(selection_context),
        claim_specs=list_enabled_finding_claim_specs(lens),
        candidate_actions=ordered_actions,
        numeric_payloads=dict(numeric_payloads or {}),
    )


def _get_claim_spec(lens: Lens, claim_key: str) -> FindingClaimSpec:
    for spec in list_initial_finding_claim_specs(lens):
        if spec.claim_key == claim_key:
            return spec
    raise KeyError(f"Unsupported claim {claim_key!r} for lens {lens!r}.")


def _coerce_monthly_series(
    payload: Mapping[str, Any],
) -> tuple[tuple[_MonthlySeriesPoint, ...], str, str]:
    raw_series = payload.get("monthly_series")
    if not isinstance(raw_series, list):
        return (), "", ""

    metric_key = str(payload.get("metric") or "").strip().lower()
    unit = str(payload.get("unit") or payload.get("unit_label") or "").strip()
    candidate_metric_keys = ((metric_key,) if metric_key else ()) + (
        "sales",
        "units",
        "price",
        "value",
    )

    series: list[_MonthlySeriesPoint] = []
    resolved_metric_key = ""
    for raw_point in raw_series:
        if not isinstance(raw_point, Mapping):
            continue
        month = str(raw_point.get("month") or "").strip()
        if not month:
            continue
        point_metric_key = resolved_metric_key
        if not point_metric_key:
            for candidate_key in candidate_metric_keys:
                if (
                    candidate_key in raw_point
                    and raw_point.get(candidate_key) is not None
                ):
                    point_metric_key = candidate_key
                    break
        if not point_metric_key:
            continue
        try:
            value = float(raw_point[point_metric_key])
        except (TypeError, ValueError):
            continue
        resolved_metric_key = point_metric_key
        series.append(_MonthlySeriesPoint(month=month, value=value))

    ordered_series = tuple(sorted(series, key=lambda point: point.month))
    return ordered_series, resolved_metric_key, unit


def _trim_incomplete_rolling_series(
    payload: Mapping[str, Any],
    series: tuple[_MonthlySeriesPoint, ...],
) -> tuple[_MonthlySeriesPoint, ...]:
    try:
        window_months = int(payload.get("window_months") or 0)
    except (TypeError, ValueError):
        window_months = 0
    if window_months <= 1 or len(series) < window_months:
        return series
    return series[window_months - 1 :]


def _score_total(
    *,
    magnitude: float,
    persistence: float,
    divergence: float = 0.0,
    uniqueness: float = 0.6,
) -> FindingScore:
    bounded_magnitude = max(0.0, min(magnitude, 1.0))
    bounded_persistence = max(0.0, min(persistence, 1.0))
    bounded_divergence = max(0.0, min(divergence, 1.0))
    bounded_uniqueness = max(0.0, min(uniqueness, 1.0))
    total = (
        bounded_magnitude * 0.45
        + bounded_persistence * 0.3
        + bounded_divergence * 0.05
        + bounded_uniqueness * 0.2
    )
    return FindingScore(
        magnitude=bounded_magnitude,
        persistence=bounded_persistence,
        divergence=bounded_divergence,
        uniqueness=bounded_uniqueness,
        total=round(total, 4),
    )


def _confidence_from_score(score: FindingScore) -> FindingConfidence:
    if score.total >= FINDING_SCORE_HIGH_THRESHOLD:
        return "high"
    if score.total >= FINDING_SCORE_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def _supporting_chart_keys(claim_spec: FindingClaimSpec) -> tuple[str, ...]:
    return tuple(claim_spec.preferred_chart_keys[1:])


def _sentence_label(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:1].upper() + text[1:]


def _attribute_mix_dimension_from_story_key(candidate: FindingCandidate) -> str | None:
    if candidate.lens != "attribute_mix":
        return None
    story_key = str(candidate.story_key or "").strip()
    if not story_key:
        return None
    parts = story_key.split(":")
    if len(parts) >= 3 and parts[0] == "attribute_mix":
        return parts[1]
    return None


def rank_and_deduplicate_findings(
    candidates: tuple[FindingCandidate, ...] | list[FindingCandidate],
    *,
    max_findings: int = DEFAULT_SHORTLIST_MAX_FINDINGS,
    max_per_lens: int = DEFAULT_SHORTLIST_MAX_PER_LENS,
) -> tuple[FindingCandidate, ...]:
    confidence_rank = {"high": 0, "medium": 1, "low": 2}
    claim_priority = {
        (spec.lens, spec.claim_key): index
        for index, spec in enumerate(list_initial_finding_claim_specs())
    }
    lens_counts: dict[Lens, int] = {}
    attribute_mix_dimensions: set[str] = set()
    ranked: list[FindingCandidate] = []
    grouped_candidates: dict[str, list[FindingCandidate]] = {}
    for candidate in candidates:
        story_key = (
            candidate.story_key
            or f"{candidate.lens}:{candidate.claim_key or candidate.chart_key}:{candidate.chart_id or ''}"
        )
        grouped_candidates.setdefault(story_key, []).append(candidate)

    representatives = [
        sorted(
            group,
            key=lambda candidate: (
                claim_priority.get((candidate.lens, candidate.claim_key), 999),
                -candidate.score.total,
                -candidate.score.magnitude,
                -candidate.score.persistence,
                confidence_rank.get(candidate.confidence, 3),
                candidate.claim,
            ),
        )[0]
        for group in grouped_candidates.values()
    ]
    ordered_candidates = sorted(
        representatives,
        key=lambda candidate: (
            -candidate.score.total,
            -candidate.score.magnitude,
            -candidate.score.persistence,
            confidence_rank.get(candidate.confidence, 3),
            claim_priority.get((candidate.lens, candidate.claim_key), 999),
            candidate.lens,
            candidate.claim,
        ),
    )
    for candidate in ordered_candidates:
        attribute_dimension = _attribute_mix_dimension_from_story_key(candidate)
        if attribute_dimension and attribute_dimension in attribute_mix_dimensions:
            continue
        if lens_counts.get(candidate.lens, 0) >= max_per_lens:
            continue
        ranked.append(candidate)
        lens_counts[candidate.lens] = lens_counts.get(candidate.lens, 0) + 1
        if attribute_dimension:
            attribute_mix_dimensions.add(attribute_dimension)
        if len(ranked) >= max_findings:
            break
    return tuple(ranked)


def _coerce_monthly_share_rows(
    payload: Mapping[str, Any],
) -> tuple[tuple[dict[str, Any], ...], str]:
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list):
        return (), ""

    segment_key = str(
        payload.get("segment_key") or payload.get("dimension") or "segment"
    ).strip()
    rows: list[dict[str, Any]] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, Mapping):
            continue
        month = str(raw_row.get("month") or "").strip()
        segment = str(raw_row.get(segment_key) or raw_row.get("segment") or "").strip()
        try:
            share_pct = float(raw_row.get("share_pct"))
        except (TypeError, ValueError):
            continue
        if not month or not segment:
            continue
        rows.append(
            {
                "month": month,
                "segment": segment,
                "share_pct": share_pct,
            }
        )
    return (
        tuple(sorted(rows, key=lambda row: (str(row["month"]), str(row["segment"])))),
        segment_key,
    )


def _attribute_mix_payload_items(
    engine_input: FindingEngineInput,
) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    multi_payloads = engine_input.numeric_payloads.get(
        "stacked_share_attribute_payloads"
    )
    if isinstance(multi_payloads, Mapping):
        payload_items = []
        for dimension_key, payload in multi_payloads.items():
            if isinstance(payload, Mapping):
                payload_items.append((str(dimension_key).strip(), payload))
        if payload_items:
            return tuple(payload_items)
    payload = _resolve_numeric_payload(engine_input, chart_key="stacked_share")
    if not payload:
        return ()
    return ((str(payload.get("segment_key") or "attribute").strip(), payload),)


def _attribute_dimension_context(
    payload: Mapping[str, Any], segment_key: str
) -> tuple[str, str]:
    raw_label = str(payload.get("dimension_label") or "").strip() or _dimension_label(
        segment_key
    )
    if not raw_label or _dimension_token(raw_label) == "segment":
        return "", ""
    return raw_label, _sentence_label(raw_label)


def _coerce_slope_rows(
    payload: Mapping[str, Any],
) -> tuple[tuple[dict[str, Any], ...], str]:
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list):
        return (), ""

    segment_key = str(payload.get("segment_key") or "brand").strip()
    rows: list[dict[str, Any]] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, Mapping):
            continue
        label = str(
            raw_row.get(segment_key)
            or raw_row.get("brand")
            or raw_row.get("segment")
            or raw_row.get("label")
            or ""
        ).strip()
        if not label:
            continue
        try:
            start_share_pct = float(raw_row.get("start_share_pct"))
            end_share_pct = float(raw_row.get("end_share_pct"))
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "segment": label,
                "start_share_pct": start_share_pct,
                "end_share_pct": end_share_pct,
            }
        )
    return (
        tuple(
            sorted(
                rows,
                key=lambda row: (
                    -float(row["end_share_pct"]),
                    -float(row["start_share_pct"]),
                    str(row["segment"]),
                ),
            )
        ),
        segment_key,
    )


def build_growth_size_candidates(
    engine_input: FindingEngineInput,
) -> tuple[FindingCandidate, ...]:
    if engine_input.lens != "growth_size":
        raise ValueError(
            f"build_growth_size_candidates only supports 'growth_size', got {engine_input.lens!r}."
        )

    structural_payload = _resolve_growth_total_combo_payload(
        engine_input,
        series_kind="rolling_12",
    )
    structural_series, structural_metric_key, structural_unit = _coerce_monthly_series(
        structural_payload
    )
    structural_series = _trim_incomplete_rolling_series(
        structural_payload,
        structural_series,
    )
    structural_chart_id = (
        str(structural_payload.get("chart_id") or "").strip() or None
        if structural_payload
        else None
    )
    monthly_payload = _resolve_growth_total_combo_payload(
        engine_input,
        series_kind="monthly",
    )
    monthly_series, monthly_metric_key, monthly_unit = _coerce_monthly_series(
        monthly_payload
    )
    monthly_chart_id = (
        str(monthly_payload.get("chart_id") or "").strip() or None
        if monthly_payload
        else None
    )

    candidates: list[FindingCandidate] = []

    if len(structural_series) >= 2:
        start_point = structural_series[0]
        end_point = structural_series[-1]
        start_value = start_point.value
        end_value = end_point.value
        absolute_delta = end_value - start_value
        if start_value == 0:
            relative_change = 0.0 if end_value == 0 else 1.0
        else:
            relative_change = (end_value - start_value) / abs(start_value)

        deltas = [
            current.value - previous.value
            for previous, current in zip(
                structural_series, structural_series[1:], strict=False
            )
        ]
        positive_ratio = (
            sum(1 for delta in deltas if delta > 0) / len(deltas) if deltas else 0.0
        )
        negative_ratio = (
            sum(1 for delta in deltas if delta < 0) / len(deltas) if deltas else 0.0
        )

        level_shift_spec = _get_claim_spec("growth_size", "level_shift")
        level_shift_chart_key = _resolve_primary_chart_key(
            engine_input, level_shift_spec.preferred_chart_keys
        )
        if abs(relative_change) >= GROWTH_LEVEL_SHIFT_MIN_RELATIVE_CHANGE:
            direction = "grew" if relative_change > 0 else "declined"
            level_shift_score = _score_total(
                magnitude=min(abs(relative_change) / 0.5, 1.0),
                persistence=max(positive_ratio, negative_ratio),
            )
            candidates.append(
                FindingCandidate(
                    lens="growth_size",
                    scope=engine_input.scope,
                    claim=(
                        f"The slice {direction} materially from {start_point.month} to {end_point.month}."
                    ),
                    chart_key=level_shift_chart_key,
                    chart_id=monthly_chart_id or structural_chart_id,
                    supporting_chart_keys=_supporting_chart_keys(level_shift_spec),
                    evidence_bullets=(
                        f"{structural_metric_key or 'value'} moved from {start_value:.1f} to {end_value:.1f} {structural_unit}".strip(),
                        f"Absolute change was {absolute_delta:+.1f} and relative change was {relative_change * 100:+.1f}%.",
                    ),
                    metrics=(
                        FindingMetric(
                            "start_value", "Start value", start_value, structural_unit
                        ),
                        FindingMetric(
                            "end_value", "End value", end_value, structural_unit
                        ),
                        FindingMetric(
                            "absolute_delta",
                            "Absolute change",
                            absolute_delta,
                            structural_unit,
                        ),
                        FindingMetric(
                            "relative_change_pct",
                            "Relative change %",
                            relative_change * 100.0,
                            "pct",
                        ),
                    ),
                    score=level_shift_score,
                    confidence=_confidence_from_score(level_shift_score),
                    caution="Direct observed change only; no units/price attribution is applied.",
                    claim_key="level_shift",
                    story_key="growth_size:trend_level",
                )
            )

        sustained_spec = _get_claim_spec("growth_size", "sustained_growth_or_decline")
        sustained_chart_key = _resolve_primary_chart_key(
            engine_input, sustained_spec.preferred_chart_keys
        )
        sustained_direction = ""
        sustained_ratio = 0.0
        if (
            relative_change >= GROWTH_SUSTAINED_MIN_RELATIVE_CHANGE
            and positive_ratio >= GROWTH_SUSTAINED_MIN_DIRECTION_RATIO
        ):
            sustained_direction = "growth"
            sustained_ratio = positive_ratio
        elif (
            relative_change <= -GROWTH_SUSTAINED_MIN_RELATIVE_CHANGE
            and negative_ratio >= GROWTH_SUSTAINED_MIN_DIRECTION_RATIO
        ):
            sustained_direction = "decline"
            sustained_ratio = negative_ratio
        if sustained_direction:
            sustained_score = _score_total(
                magnitude=min(abs(relative_change) / 0.4, 1.0),
                persistence=sustained_ratio,
            )
            candidates.append(
                FindingCandidate(
                    lens="growth_size",
                    scope=engine_input.scope,
                    claim=(
                        f"The slice showed sustained {sustained_direction} across the observed rolling 12-month series."
                    ),
                    chart_key=sustained_chart_key,
                    chart_id=monthly_chart_id or structural_chart_id,
                    supporting_chart_keys=_supporting_chart_keys(sustained_spec),
                    evidence_bullets=(
                        f"{sustained_ratio * 100:.0f}% of rolling-window moves were in the same direction as the net change.",
                        f"Net change from {start_point.month} to {end_point.month} was {relative_change * 100:+.1f}%.",
                    ),
                    metrics=(
                        FindingMetric(
                            "same_direction_window_share_pct",
                            "Same-direction rolling-window share %",
                            sustained_ratio * 100.0,
                            "pct",
                        ),
                        FindingMetric(
                            "relative_change_pct",
                            "Relative change %",
                            relative_change * 100.0,
                            "pct",
                        ),
                    ),
                    score=sustained_score,
                    confidence=_confidence_from_score(sustained_score),
                    caution="Persistence is based on rolling 12-month directionality, not causal decomposition.",
                    claim_key="sustained_growth_or_decline",
                    story_key="growth_size:trend_level",
                )
            )

    volatility_spec = _get_claim_spec("growth_size", "volatility_or_spike")
    volatility_chart_key = _resolve_primary_chart_key(
        engine_input, volatility_spec.preferred_chart_keys
    )
    if len(monthly_series) >= GROWTH_VOLATILITY_MIN_OBSERVATIONS:
        monthly_values = [point.value for point in monthly_series]
        median_value = sorted(monthly_values)[len(monthly_values) // 2]
        peak_value = max(monthly_values)
        trough_value = min(monthly_values)
        spike_ratio = peak_value / median_value if median_value > 0 else 0.0
    else:
        spike_ratio = 0.0
        peak_value = 0.0
        trough_value = 0.0
        median_value = 0.0
    if (
        len(monthly_series) >= GROWTH_VOLATILITY_MIN_OBSERVATIONS
        and spike_ratio >= GROWTH_VOLATILITY_MIN_SPIKE_RATIO
    ):
        volatility_score = _score_total(
            magnitude=min((spike_ratio - 1.0) / 0.7, 1.0),
            persistence=min(len(monthly_series) / 24.0, 1.0),
        )
        candidates.append(
            FindingCandidate(
                lens="growth_size",
                scope=engine_input.scope,
                claim="The slice showed a spiky or highly volatile monthly pattern.",
                chart_key=volatility_chart_key,
                chart_id=monthly_chart_id or structural_chart_id,
                supporting_chart_keys=_supporting_chart_keys(volatility_spec),
                evidence_bullets=(
                    f"Peak month reached {peak_value:.1f} {(monthly_unit or structural_unit)}".strip(),
                    f"Peak-to-median ratio was {spike_ratio:.2f}x across {len(monthly_series)} observed months.",
                ),
                metrics=(
                    FindingMetric(
                        "peak_value",
                        "Peak month value",
                        peak_value,
                        monthly_unit or structural_unit,
                    ),
                    FindingMetric(
                        "median_value",
                        "Median month value",
                        median_value,
                        monthly_unit or structural_unit,
                    ),
                    FindingMetric(
                        "spike_ratio", "Peak / median ratio", spike_ratio, "x"
                    ),
                    FindingMetric(
                        "trough_value",
                        "Trough month value",
                        trough_value,
                        monthly_unit or structural_unit,
                    ),
                ),
                score=volatility_score,
                confidence=_confidence_from_score(volatility_score),
                caution="This is a volatility flag from the monthly series, not a statement about the underlying cause.",
                claim_key="volatility_or_spike",
                story_key="growth_size:volatility",
            )
        )

    return tuple(candidates)


def build_brand_shift_candidates(
    engine_input: FindingEngineInput,
) -> tuple[FindingCandidate, ...]:
    if engine_input.lens != "brand_shifts":
        raise ValueError("build_brand_shift_candidates only supports 'brand_shifts'.")

    slope_payload = _resolve_numeric_payload(engine_input, chart_key="slope")
    if not slope_payload:
        return ()
    rows, _segment_key = _coerce_slope_rows(slope_payload)
    if len(rows) < 2:
        return ()

    chart_id = str(slope_payload.get("chart_id") or "").strip() or None
    start_sorted = sorted(
        rows,
        key=lambda row: (
            -float(row["start_share_pct"]),
            -float(row["end_share_pct"]),
            str(row["segment"]),
        ),
    )
    end_sorted = list(rows)
    start_leader = start_sorted[0]
    end_leader = end_sorted[0]
    deltas = {
        str(row["segment"]): float(row["end_share_pct"]) - float(row["start_share_pct"])
        for row in rows
    }
    total_redistribution = sum(abs(delta) for delta in deltas.values()) / 2.0
    candidates: list[FindingCandidate] = []

    leader_change_spec = _get_claim_spec("brand_shifts", "leader_change")
    leader_change_chart_key = _resolve_primary_chart_key(
        engine_input, leader_change_spec.preferred_chart_keys
    )
    leader_changed = (
        str(start_leader["segment"]) != str(end_leader["segment"])
        and float(start_leader["start_share_pct"]) >= BRAND_LEADER_MIN_SHARE_PCT
        and float(end_leader["end_share_pct"]) >= BRAND_LEADER_MIN_SHARE_PCT
    )
    if leader_changed:
        leader_change_score = _score_total(
            magnitude=min(
                max(
                    abs(deltas.get(str(start_leader["segment"]), 0.0)),
                    abs(deltas.get(str(end_leader["segment"]), 0.0)),
                )
                / 15.0,
                1.0,
            ),
            persistence=0.8,
        )
        candidates.append(
            FindingCandidate(
                lens="brand_shifts",
                scope=engine_input.scope,
                claim=(
                    f"Leadership shifted from {start_leader['segment']} to {end_leader['segment']} over the period."
                ),
                chart_key=leader_change_chart_key,
                chart_id=chart_id,
                supporting_chart_keys=_supporting_chart_keys(leader_change_spec),
                evidence_bullets=(
                    f"{start_leader['segment']} moved from {float(start_leader['start_share_pct']):.1f}% to {float(start_leader['end_share_pct']):.1f}%.",
                    f"{end_leader['segment']} ended at {float(end_leader['end_share_pct']):.1f}% share after starting at {float(end_leader['start_share_pct']):.1f}%.",
                ),
                metrics=(
                    FindingMetric(
                        "start_leader_start_share_pct",
                        "Start leader share %",
                        float(start_leader["start_share_pct"]),
                        "pct",
                    ),
                    FindingMetric(
                        "end_leader_end_share_pct",
                        "End leader share %",
                        float(end_leader["end_share_pct"]),
                        "pct",
                    ),
                    FindingMetric(
                        "leader_swap_delta_pp",
                        "Leader swap delta",
                        max(
                            abs(deltas.get(str(start_leader["segment"]), 0.0)),
                            abs(deltas.get(str(end_leader["segment"]), 0.0)),
                        ),
                        "pp",
                    ),
                ),
                score=leader_change_score,
                confidence=_confidence_from_score(leader_change_score),
                caution="Direct observed share change only; no causal explanation is implied.",
                claim_key="leader_change",
                story_key="brand_shifts:leader_change",
            )
        )

    challenger_spec = _get_claim_spec("brand_shifts", "challenger_gain_or_loss")
    challenger_chart_key = _resolve_primary_chart_key(
        engine_input, challenger_spec.preferred_chart_keys
    )
    excluded_challenger_labels = {str(end_leader["segment"])}
    if leader_changed:
        excluded_challenger_labels.add(str(start_leader["segment"]))
    non_leader_rows = [
        row for row in rows if str(row["segment"]) not in excluded_challenger_labels
    ]
    if non_leader_rows:
        top_move = max(
            non_leader_rows,
            key=lambda row: abs(
                float(row["end_share_pct"]) - float(row["start_share_pct"])
            ),
        )
        top_move_delta = float(top_move["end_share_pct"]) - float(
            top_move["start_share_pct"]
        )
        if (
            abs(top_move_delta) >= BRAND_CHALLENGER_MIN_DELTA_PP
            and float(top_move["end_share_pct"]) >= BRAND_CHALLENGER_MIN_END_SHARE_PCT
        ):
            direction = "gained" if top_move_delta > 0 else "lost"
            challenger_score = _score_total(
                magnitude=min(abs(top_move_delta) / 12.0, 1.0),
                persistence=0.7,
            )
            candidates.append(
                FindingCandidate(
                    lens="brand_shifts",
                    scope=engine_input.scope,
                    claim=(
                        f"{_sentence_label(top_move['segment'])} {direction} meaningful share outside the leading position."
                    ),
                    chart_key=challenger_chart_key,
                    chart_id=chart_id,
                    supporting_chart_keys=_supporting_chart_keys(challenger_spec),
                    evidence_bullets=(
                        f"{top_move['segment']} moved from {float(top_move['start_share_pct']):.1f}% to {float(top_move['end_share_pct']):.1f}%.",
                        f"Change was {top_move_delta:+.1f} percentage points.",
                    ),
                    metrics=(
                        FindingMetric(
                            "start_share_pct",
                            f"{top_move['segment']} start share %",
                            float(top_move["start_share_pct"]),
                            "pct",
                        ),
                        FindingMetric(
                            "end_share_pct",
                            f"{top_move['segment']} end share %",
                            float(top_move["end_share_pct"]),
                            "pct",
                        ),
                        FindingMetric("delta_pp", "Share change", top_move_delta, "pp"),
                    ),
                    score=challenger_score,
                    confidence=_confidence_from_score(challenger_score),
                    caution="This is a challenger-style share move within the observed brand set.",
                    claim_key="challenger_gain_or_loss",
                    story_key="brand_shifts:challenger_moves",
                )
            )

    redistribution_spec = _get_claim_spec("brand_shifts", "share_redistribution")
    redistribution_chart_key = _resolve_primary_chart_key(
        engine_input, redistribution_spec.preferred_chart_keys
    )
    if total_redistribution >= BRAND_REDISTRIBUTION_MIN_TOTAL_PP:
        top_gainer_segment, top_gainer_delta = max(
            deltas.items(),
            key=lambda item: (item[1], item[0]),
        )
        top_decliner_segment, top_decliner_delta = min(
            deltas.items(),
            key=lambda item: (item[1], item[0]),
        )
        if top_gainer_delta > 0 and top_decliner_delta < 0:
            redistribution_claim = (
                f"Brand shares redistributed materially, with "
                f"{_sentence_label(top_decliner_segment)} down and "
                f"{_sentence_label(top_gainer_segment)} up."
            )
        else:
            redistribution_claim = (
                "Brand shares redistributed materially across the period."
            )
        redistribution_score = _score_total(
            magnitude=min(total_redistribution / 20.0, 1.0),
            persistence=0.7,
        )
        candidates.append(
            FindingCandidate(
                lens="brand_shifts",
                scope=engine_input.scope,
                claim=redistribution_claim,
                chart_key=redistribution_chart_key,
                chart_id=chart_id,
                supporting_chart_keys=_supporting_chart_keys(redistribution_spec),
                evidence_bullets=(
                    f"Total share redistribution across brands was {total_redistribution:.1f} percentage points.",
                    f"The largest brand-level move was {max(abs(delta) for delta in deltas.values()):.1f} pp.",
                ),
                metrics=(
                    FindingMetric(
                        "total_redistribution_pp",
                        "Total redistribution",
                        total_redistribution,
                        "pp",
                    ),
                    FindingMetric(
                        "largest_brand_move_pp",
                        "Largest brand move",
                        max(abs(delta) for delta in deltas.values()),
                        "pp",
                    ),
                ),
                score=redistribution_score,
                confidence=_confidence_from_score(redistribution_score),
                caution="This summarizes observed share movement across brands and does not imply a single winner-loser narrative.",
                claim_key="share_redistribution",
                story_key="brand_shifts:redistribution",
            )
        )

    return tuple(candidates)


def build_attribute_mix_candidates(
    engine_input: FindingEngineInput,
) -> tuple[FindingCandidate, ...]:
    if engine_input.lens != "attribute_mix":
        raise ValueError(
            "build_attribute_mix_candidates only supports 'attribute_mix'."
        )

    candidates: list[FindingCandidate] = []
    share_shift_spec = _get_claim_spec("attribute_mix", "attribute_share_shift")
    share_shift_chart_key = _resolve_primary_chart_key(
        engine_input, share_shift_spec.preferred_chart_keys
    )
    emerging_spec = _get_claim_spec("attribute_mix", "emerging_attribute_pocket")
    emerging_chart_key = _resolve_primary_chart_key(
        engine_input, emerging_spec.preferred_chart_keys
    )
    polarization_spec = _get_claim_spec("attribute_mix", "attribute_polarization")
    polarization_chart_key = _resolve_primary_chart_key(
        engine_input, polarization_spec.preferred_chart_keys
    )
    for raw_dimension_key, stacked_share_payload in _attribute_mix_payload_items(
        engine_input
    ):
        rows, segment_key = _coerce_monthly_share_rows(stacked_share_payload)
        if len(rows) < 2:
            continue

        chart_id = str(stacked_share_payload.get("chart_id") or "").strip() or None
        months = sorted({str(row["month"]) for row in rows})
        if len(months) < 2:
            continue
        start_month = months[0]
        end_month = months[-1]

        start_shares: dict[str, float] = {}
        end_shares: dict[str, float] = {}
        for row in rows:
            segment = str(row["segment"]).strip()
            share_pct = float(row["share_pct"])
            if row["month"] == start_month:
                start_shares[segment] = start_shares.get(segment, 0.0) + share_pct
            if row["month"] == end_month:
                end_shares[segment] = end_shares.get(segment, 0.0) + share_pct

        normalized_segments = {
            segment.strip().lower() for segment in set(start_shares) | set(end_shares)
        }
        if normalized_segments and normalized_segments <= {"premium", "mid", "value"}:
            continue

        deltas = {
            segment: end_shares.get(segment, 0.0) - start_shares.get(segment, 0.0)
            for segment in sorted(set(start_shares) | set(end_shares))
        }
        if not deltas:
            continue

        dimension_key = (
            _dimension_token(raw_dimension_key or segment_key) or "attribute"
        )
        dimension_label, dimension_title = _attribute_dimension_context(
            stacked_share_payload, segment_key
        )
        mix_prefix = f"{dimension_title} mix " if dimension_title else ""
        within_prefix = f"Within {dimension_label.lower()}, " if dimension_label else ""

        dominant_segment, dominant_delta = max(
            deltas.items(), key=lambda item: abs(float(item[1]))
        )
        if abs(dominant_delta) >= ATTRIBUTE_SHARE_SHIFT_MIN_DELTA_PP:
            direction = "gained" if dominant_delta > 0 else "lost"
            share_shift_score = _score_total(
                magnitude=min(abs(dominant_delta) / 15.0, 1.0),
                persistence=0.75,
            )
            if mix_prefix:
                claim_text = f"{mix_prefix}shifted as {_sentence_label(dominant_segment)} {direction} meaningful share from {start_month} to {end_month}."
            else:
                claim_text = f"{_sentence_label(dominant_segment)} {direction} meaningful share from {start_month} to {end_month}."
            candidates.append(
                FindingCandidate(
                    lens="attribute_mix",
                    scope=engine_input.scope,
                    claim=claim_text,
                    chart_key=share_shift_chart_key,
                    chart_id=chart_id,
                    supporting_chart_keys=_supporting_chart_keys(share_shift_spec),
                    evidence_bullets=(
                        f"{_sentence_label(dominant_segment)} moved from {start_shares.get(dominant_segment, 0.0):.1f}% to {end_shares.get(dominant_segment, 0.0):.1f}%.",
                        f"Change was {dominant_delta:+.1f} percentage points across the period.",
                    ),
                    metrics=(
                        FindingMetric(
                            "start_share_pct",
                            f"{_sentence_label(dominant_segment)} start share %",
                            start_shares.get(dominant_segment, 0.0),
                            "pct",
                        ),
                        FindingMetric(
                            "end_share_pct",
                            f"{_sentence_label(dominant_segment)} end share %",
                            end_shares.get(dominant_segment, 0.0),
                            "pct",
                        ),
                        FindingMetric(
                            "delta_pp",
                            f"{_sentence_label(dominant_segment)} share change",
                            dominant_delta,
                            "pp",
                        ),
                    ),
                    score=share_shift_score,
                    confidence=_confidence_from_score(share_shift_score),
                    caution="This is a direct observed attribute mix shift.",
                    claim_key="attribute_share_shift",
                    story_key=f"attribute_mix:{dimension_key}:structure_shift",
                )
            )

        emerging_candidates = [
            (segment, delta)
            for segment, delta in deltas.items()
            if delta >= ATTRIBUTE_EMERGING_MIN_DELTA_PP
            and start_shares.get(segment, 0.0) < ATTRIBUTE_EMERGING_MAX_START_SHARE_PCT
            and end_shares.get(segment, 0.0) >= ATTRIBUTE_EMERGING_MIN_END_SHARE_PCT
        ]
        if emerging_candidates:
            emerging_segment, emerging_delta = max(
                emerging_candidates, key=lambda item: float(item[1])
            )
            emerging_score = _score_total(
                magnitude=min(float(emerging_delta) / 12.0, 1.0),
                persistence=0.7,
            )
            if within_prefix:
                claim_text = f"{within_prefix}{_sentence_label(emerging_segment)} emerged as a meaningful pocket."
            else:
                claim_text = f"{_sentence_label(emerging_segment)} emerged as a meaningful pocket within the mix."
            candidates.append(
                FindingCandidate(
                    lens="attribute_mix",
                    scope=engine_input.scope,
                    claim=claim_text,
                    chart_key=emerging_chart_key,
                    chart_id=chart_id,
                    supporting_chart_keys=_supporting_chart_keys(emerging_spec),
                    evidence_bullets=(
                        f"{_sentence_label(emerging_segment)} rose from {start_shares.get(emerging_segment, 0.0):.1f}% to {end_shares.get(emerging_segment, 0.0):.1f}%.",
                        f"Start share was small, but the gain was {emerging_delta:+.1f} pp.",
                    ),
                    metrics=(
                        FindingMetric(
                            "start_share_pct",
                            f"{_sentence_label(emerging_segment)} start share %",
                            start_shares.get(emerging_segment, 0.0),
                            "pct",
                        ),
                        FindingMetric(
                            "end_share_pct",
                            f"{_sentence_label(emerging_segment)} end share %",
                            end_shares.get(emerging_segment, 0.0),
                            "pct",
                        ),
                        FindingMetric("delta_pp", "Share change", emerging_delta, "pp"),
                    ),
                    score=emerging_score,
                    confidence=_confidence_from_score(emerging_score),
                    caution="Emerging-pocket claims require a stronger threshold because the starting share is small.",
                    claim_key="emerging_attribute_pocket",
                    story_key=f"attribute_mix:{dimension_key}:emerging_pocket",
                )
            )

        strong_gainers = [
            (segment, delta)
            for segment, delta in deltas.items()
            if delta >= ATTRIBUTE_POLARIZATION_MIN_GAINER_DELTA_PP
        ]
        strong_decliners = [
            (segment, delta)
            for segment, delta in deltas.items()
            if delta <= ATTRIBUTE_POLARIZATION_MIN_DECLINER_DELTA_PP
        ]
        if len(strong_gainers) >= 2 and len(strong_decliners) >= 1:
            top_gainers = sorted(strong_gainers, key=lambda item: -float(item[1]))[:2]
            top_decliner = min(strong_decliners, key=lambda item: float(item[1]))
            if all(
                start_shares.get(segment, 0.0)
                >= ATTRIBUTE_POLARIZATION_MIN_START_SHARE_PCT
                for segment, _delta in top_gainers
            ):
                polarization_score = _score_total(
                    magnitude=min(
                        (
                            abs(float(top_gainers[0][1]))
                            + abs(float(top_gainers[1][1]))
                            + abs(float(top_decliner[1]))
                        )
                        / 18.0,
                        1.0,
                    ),
                    persistence=0.7,
                )
                gainer_labels = " and ".join(
                    _sentence_label(segment) for segment, _delta in top_gainers
                )
                if mix_prefix:
                    claim_text = f"{mix_prefix}polarized, with {gainer_labels} gaining while {_sentence_label(top_decliner[0])} declined."
                else:
                    claim_text = f"The mix polarized, with {gainer_labels} gaining while {_sentence_label(top_decliner[0])} declined."
                candidates.append(
                    FindingCandidate(
                        lens="attribute_mix",
                        scope=engine_input.scope,
                        claim=claim_text,
                        chart_key=polarization_chart_key,
                        chart_id=chart_id,
                        supporting_chart_keys=_supporting_chart_keys(polarization_spec),
                        evidence_bullets=(
                            f"{_sentence_label(top_gainers[0][0])} changed by {float(top_gainers[0][1]):+.1f} pp and {_sentence_label(top_gainers[1][0])} by {float(top_gainers[1][1]):+.1f} pp.",
                            f"{_sentence_label(top_decliner[0])} declined by {float(top_decliner[1]):+.1f} pp.",
                        ),
                        metrics=(
                            FindingMetric(
                                "top_gainer_delta_pp",
                                f"{_sentence_label(top_gainers[0][0])} change",
                                float(top_gainers[0][1]),
                                "pp",
                            ),
                            FindingMetric(
                                "second_gainer_delta_pp",
                                f"{_sentence_label(top_gainers[1][0])} change",
                                float(top_gainers[1][1]),
                                "pp",
                            ),
                            FindingMetric(
                                "top_decliner_delta_pp",
                                f"{_sentence_label(top_decliner[0])} change",
                                float(top_decliner[1]),
                                "pp",
                            ),
                        ),
                        score=polarization_score,
                        confidence=_confidence_from_score(polarization_score),
                        caution="This polarization claim summarizes multiple observed attribute moves rather than a single dominant shift.",
                        claim_key="attribute_polarization",
                        story_key=f"attribute_mix:{dimension_key}:polarization",
                    )
                )
    return tuple(candidates)


def build_price_value_capture_candidates(
    engine_input: FindingEngineInput,
) -> tuple[FindingCandidate, ...]:
    if engine_input.lens != "price_value_capture":
        raise ValueError(
            "build_price_value_capture_candidates only supports 'price_value_capture'."
        )

    stacked_share_payload = _resolve_numeric_payload(
        engine_input, chart_key="stacked_share"
    )
    if not stacked_share_payload:
        return ()
    rows, _segment_key = _coerce_monthly_share_rows(stacked_share_payload)
    if len(rows) < 2:
        return ()

    chart_id = str(stacked_share_payload.get("chart_id") or "").strip() or None
    months = sorted({str(row["month"]) for row in rows})
    if len(months) < 2:
        return ()
    start_month = months[0]
    end_month = months[-1]

    start_shares: dict[str, float] = {}
    end_shares: dict[str, float] = {}
    for row in rows:
        segment = str(row["segment"]).strip().lower()
        share_pct = float(row["share_pct"])
        if row["month"] == start_month:
            start_shares[segment] = start_shares.get(segment, 0.0) + share_pct
        if row["month"] == end_month:
            end_shares[segment] = end_shares.get(segment, 0.0) + share_pct

    deltas = {
        segment: end_shares.get(segment, 0.0) - start_shares.get(segment, 0.0)
        for segment in sorted(set(start_shares) | set(end_shares))
    }
    if not deltas:
        return ()

    candidates: list[FindingCandidate] = []

    premium_delta = deltas.get("premium", 0.0)
    mid_delta = deltas.get("mid", 0.0)
    value_delta = deltas.get("value", 0.0)
    claim_text = ""
    preferred_segment: str | None = None
    if (
        premium_delta >= PRICE_PREMIUMIZATION_MIN_PREMIUM_DELTA_PP
        and value_delta <= PRICE_PREMIUMIZATION_MAX_VALUE_DELTA_PP
    ):
        claim_text = "The mix premiumized over the period."
        preferred_segment = "premium"
    elif (
        value_delta >= PRICE_VALUE_SHIFT_MIN_VALUE_DELTA_PP
        and premium_delta <= PRICE_VALUE_SHIFT_MAX_PREMIUM_DELTA_PP
    ):
        claim_text = "The mix shifted toward value over the period."
        preferred_segment = "value"
    elif (
        mid_delta >= PRICE_MID_SHIFT_MIN_MID_DELTA_PP
        and value_delta <= PRICE_MID_SHIFT_MAX_VALUE_DELTA_PP
    ):
        claim_text = "The mix moved toward mid-priced bands over the period."
        preferred_segment = "mid"

    dominant_segment = preferred_segment
    if dominant_segment is None:
        dominant_segment = max(deltas.items(), key=lambda item: abs(float(item[1])))[0]
    dominant_delta = deltas.get(dominant_segment, 0.0)

    mix_shift_spec = _get_claim_spec("price_value_capture", "price_band_mix_shift")
    mix_shift_chart_key = _resolve_primary_chart_key(
        engine_input, mix_shift_spec.preferred_chart_keys
    )
    if abs(dominant_delta) >= PRICE_STRUCTURE_DOMINANT_MIN_DELTA_PP:
        dominant_score = _score_total(
            magnitude=min(abs(dominant_delta) / 12.0, 1.0),
            persistence=0.75,
        )
        direction = "gained" if dominant_delta > 0 else "lost"
        candidates.append(
            FindingCandidate(
                lens="price_value_capture",
                scope=engine_input.scope,
                claim=(
                    f"{dominant_segment.title()} price band {direction} meaningful share from {start_month} to {end_month}."
                ),
                chart_key=mix_shift_chart_key,
                chart_id=chart_id,
                supporting_chart_keys=_supporting_chart_keys(mix_shift_spec),
                evidence_bullets=(
                    f"{dominant_segment.title()} moved from {start_shares.get(dominant_segment, 0.0):.1f}% to {end_shares.get(dominant_segment, 0.0):.1f}%.",
                    f"Change was {dominant_delta:+.1f} percentage points across the period.",
                ),
                metrics=(
                    FindingMetric(
                        "start_share_pct",
                        f"{dominant_segment.title()} start share %",
                        start_shares.get(dominant_segment, 0.0),
                        "pct",
                    ),
                    FindingMetric(
                        "end_share_pct",
                        f"{dominant_segment.title()} end share %",
                        end_shares.get(dominant_segment, 0.0),
                        "pct",
                    ),
                    FindingMetric(
                        "delta_pp",
                        f"{dominant_segment.title()} share change",
                        dominant_delta,
                        "pp",
                    ),
                ),
                score=dominant_score,
                confidence=_confidence_from_score(dominant_score),
                caution="This is a direct observed mix shift, not a price/units variance decomposition.",
                claim_key="price_band_mix_shift",
                story_key="price_value_capture:price_band_structure",
            )
        )

    premiumization_spec = _get_claim_spec(
        "price_value_capture", "premiumization_or_value_shift"
    )
    premiumization_chart_key = _resolve_primary_chart_key(
        engine_input, premiumization_spec.preferred_chart_keys
    )
    if claim_text:
        premiumization_score = _score_total(
            magnitude=min(
                max(abs(premium_delta), abs(mid_delta), abs(value_delta)) / 12.0, 1.0
            ),
            persistence=0.75,
        )
        candidates.append(
            FindingCandidate(
                lens="price_value_capture",
                scope=engine_input.scope,
                claim=claim_text,
                chart_key=premiumization_chart_key,
                chart_id=chart_id,
                supporting_chart_keys=_supporting_chart_keys(premiumization_spec),
                evidence_bullets=(
                    f"Premium changed by {premium_delta:+.1f} pp, mid by {mid_delta:+.1f} pp, and value by {value_delta:+.1f} pp.",
                    f"Comparison window runs from {start_month} to {end_month}.",
                ),
                metrics=(
                    FindingMetric(
                        "premium_delta_pp", "Premium change", premium_delta, "pp"
                    ),
                    FindingMetric("mid_delta_pp", "Mid change", mid_delta, "pp"),
                    FindingMetric("value_delta_pp", "Value change", value_delta, "pp"),
                ),
                score=premiumization_score,
                confidence=_confidence_from_score(premiumization_score),
                caution="Observed from price-band shares only; no claim is made about the causal source of the shift.",
                claim_key="premiumization_or_value_shift",
                story_key="price_value_capture:price_band_structure",
            )
        )

    return tuple(candidates)


def build_ranked_finding_shortlist(
    *,
    scope: ScopeSupport = "single_category",
    analysis_scope: AnalysisScope | None = None,
    selection_context: Mapping[str, Any],
    numeric_payloads: Mapping[str, Mapping[str, Any]] | None = None,
    lenses: tuple[Lens, ...] | list[Lens] | None = None,
    max_findings: int = DEFAULT_SHORTLIST_MAX_FINDINGS,
    max_per_lens: int = DEFAULT_SHORTLIST_MAX_PER_LENS,
) -> tuple[FindingCandidate, ...]:
    detector_registry = {
        "growth_size": (build_growth_size_candidates,),
        "price_value_capture": (build_price_value_capture_candidates,),
        "brand_shifts": (build_brand_shift_candidates,),
        "attribute_mix": (build_attribute_mix_candidates,),
    }
    requested_lenses = tuple(
        lenses
        or [
            spec.lens
            for spec in list_initial_finding_lens_specs()
            if scope in spec.scope_support
        ]
    )
    all_candidates: list[FindingCandidate] = []
    for lens in requested_lenses:
        engine_input = build_finding_engine_input(
            lens=lens,
            scope=scope,
            analysis_scope=analysis_scope,
            selection_context=selection_context,
            numeric_payloads=numeric_payloads,
        )
        for detector in detector_registry.get(lens, ()):
            all_candidates.extend(detector(engine_input))
    return rank_and_deduplicate_findings(
        all_candidates,
        max_findings=max_findings,
        max_per_lens=max_per_lens,
    )


def resolve_finding_evidence_plan(
    candidate: FindingCandidate,
    engine_input: FindingEngineInput,
) -> FindingEvidencePlan:
    if candidate.lens != engine_input.lens:
        raise ValueError(
            f"Candidate lens {candidate.lens!r} does not match engine input lens {engine_input.lens!r}."
        )

    claim_spec = _get_claim_spec(candidate.lens, candidate.claim_key)
    action_by_chart_key = {
        action.chart_key: action for action in engine_input.candidate_actions
    }
    preferred_chart_keys = (
        candidate.chart_key,
        *tuple(
            chart_key
            for chart_key in claim_spec.preferred_chart_keys
            if chart_key != candidate.chart_key
        ),
    )
    available_options: list[FindingEvidenceOption] = []
    missing_chart_keys: list[str] = []
    for index, chart_key in enumerate(preferred_chart_keys):
        action = action_by_chart_key.get(chart_key)
        payload = _resolve_candidate_payload(
            engine_input,
            candidate=candidate,
            chart_key=chart_key,
        )
        chart_id = None
        chart_request = None
        if isinstance(payload, Mapping):
            chart_id = str(payload.get("chart_id") or "").strip() or None
            current_request = payload.get("chart_request")
            if isinstance(current_request, Mapping):
                chart_request = dict(current_request)
        if action is None:
            missing_chart_keys.append(chart_key)
            continue
        available_options.append(
            FindingEvidenceOption(
                chart_key=chart_key,
                chart_label=action.label,
                chart_type=action.chart_type,
                chart_id=chart_id,
                chart_request=chart_request,
                has_payload=isinstance(payload, Mapping) and bool(payload),
                is_primary=index == 0,
            )
        )
    primary_option = available_options[0] if available_options else None
    supporting_options = tuple(available_options[1:])
    return FindingEvidencePlan(
        candidate=candidate,
        primary_option=primary_option,
        supporting_options=supporting_options,
        missing_preferred_chart_keys=tuple(missing_chart_keys),
    )
