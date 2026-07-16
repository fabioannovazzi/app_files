from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Mapping

from modules.pdp.sales_brief_config import (
    BRIEF_SERIALIZED_MAX_BULLETS,
    BRIEF_SERIALIZED_MAX_METRICS,
    BRIEF_SUPPRESS_VOLATILITY_WHEN_STRUCTURAL_GROWTH,
    BRIEF_UNSIGNED_PP_METRIC_KEYS,
    DEFAULT_BRIEF_HIGHLIGHT_COUNT,
    DEFAULT_BRIEF_MAX_FINDINGS,
    DEFAULT_BRIEF_MAX_PER_LENS,
)
from modules.pdp.sales_chart_catalog import Lens, ScopeSupport
from modules.pdp.sales_finding_engine import (
    AnalysisScope,
    FindingCandidate,
    FindingEvidenceOption,
    FindingMetric,
    build_analysis_scope,
    build_finding_engine_input,
    build_ranked_finding_shortlist,
    get_finding_lens_spec,
    resolve_finding_evidence_plan,
)

__all__ = [
    "SalesBriefArtifact",
    "SalesBriefFinding",
    "SalesBriefSection",
    "build_sales_brief_artifact",
    "build_sales_brief_payload",
]


@dataclass(frozen=True, slots=True)
class SalesBriefFinding:
    rank: int
    lens: Lens
    lens_label: str
    claim: str
    primary_evidence: FindingEvidenceOption | None
    supporting_evidence: tuple[FindingEvidenceOption, ...]
    evidence_bullets: tuple[str, ...]
    confidence: str
    score_total: float
    caution: str | None
    metrics: tuple[FindingMetric, ...]
    story_key: str | None


@dataclass(frozen=True, slots=True)
class SalesBriefSection:
    lens: Lens
    title: str
    findings: tuple[SalesBriefFinding, ...]


@dataclass(frozen=True, slots=True)
class SalesBriefArtifact:
    title: str
    scope: ScopeSupport
    analysis_scope: AnalysisScope
    attribute_dimensions: tuple[str, ...]
    highlights: tuple[str, ...]
    sections: tuple[SalesBriefSection, ...]
    findings: tuple[SalesBriefFinding, ...]


_DATE_TOKEN_PATTERN = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b")
_HUMAN_DATE_RANGE_PATTERN = re.compile(
    r"from (?P<start_mon>[A-Z][a-z]{2}) (?P<start_year>\d{4}) "
    r"to (?P<end_mon>[A-Z][a-z]{2}) (?P<end_year>\d{4})"
)
_USD_RANGE_PATTERN = re.compile(
    r"from (?P<start>[+-]?\d+(?:\.\d+)?) to (?P<end>[+-]?\d+(?:\.\d+)?) USD\b"
)
_USD_VALUE_PATTERN = re.compile(r"(?P<value>[+-]?\d+(?:\.\d+)?) USD\b")
_ABSOLUTE_CHANGE_PATTERN = re.compile(
    r"Absolute change was (?P<value>[+-]?\d+(?:\.\d+)?)\b"
)


def _round_metric_value(value: float | None, unit: str) -> float | None:
    if value is None:
        return None
    if unit == "x":
        return round(float(value), 2)
    return round(float(value), 1)


def _format_month_label(value: str) -> str:
    for pattern in ("%Y-%m-%d", "%Y-%m"):
        try:
            parsed = datetime.strptime(value, pattern)
            return parsed.strftime("%b %Y")
        except ValueError:
            continue
    return value


def _format_money(value: float, *, signed: bool = False) -> str:
    absolute = abs(float(value))
    if absolute >= 1_000_000_000:
        scaled = absolute / 1_000_000_000
        suffix = "B"
    elif absolute >= 1_000_000:
        scaled = absolute / 1_000_000
        suffix = "M"
    elif absolute >= 1_000:
        scaled = absolute / 1_000
        suffix = "K"
    else:
        scaled = absolute
        suffix = ""
    sign = ""
    if value < 0:
        sign = "-"
    elif signed and value > 0:
        sign = "+"
    return f"{sign}${scaled:.1f}{suffix}"


def _format_metric_display_value(metric: FindingMetric) -> str | None:
    value = metric.value
    unit = metric.unit
    if value is None:
        return None
    numeric_value = float(value)
    if unit == "USD":
        signed = metric.key == "absolute_delta"
        return _format_money(numeric_value, signed=signed)
    if unit == "pct":
        return f"{numeric_value:.1f}%"
    if unit == "pp":
        signed = metric.key not in BRIEF_UNSIGNED_PP_METRIC_KEYS
        return (
            f"{numeric_value:+.1f} pp"
            if signed
            else f"{numeric_value:.1f} pp"
        )
    if unit == "x":
        return f"{numeric_value:.2f}x"
    return f"{numeric_value:.1f}"


def _humanize_text(text: str) -> str:
    def replace_date(match: re.Match[str]) -> str:
        return _format_month_label(match.group(0))

    def replace_human_date_range(match: re.Match[str]) -> str:
        start_year = match.group("start_year")
        end_year = match.group("end_year")
        if start_year == end_year:
            return f"in {start_year}"
        return f"from {start_year} to {end_year}"

    def replace_usd_range(match: re.Match[str]) -> str:
        return (
            f"from {_format_money(float(match.group('start')))} "
            f"to {_format_money(float(match.group('end')))}"
        )

    def replace_usd_value(match: re.Match[str]) -> str:
        return _format_money(float(match.group("value")))

    def replace_absolute_change(match: re.Match[str]) -> str:
        return f"Absolute change was {_format_money(float(match.group('value')), signed=True)}"

    updated = _DATE_TOKEN_PATTERN.sub(replace_date, text)
    updated = _HUMAN_DATE_RANGE_PATTERN.sub(replace_human_date_range, updated)
    updated = _USD_RANGE_PATTERN.sub(replace_usd_range, updated)
    updated = _USD_VALUE_PATTERN.sub(replace_usd_value, updated)
    updated = _ABSOLUTE_CHANGE_PATTERN.sub(replace_absolute_change, updated)
    return updated


def _serialize_primary_evidence(
    evidence: FindingEvidenceOption | None,
) -> dict[str, Any] | None:
    if evidence is None:
        return None
    payload = {
        "chart_key": evidence.chart_key,
        "chart_label": evidence.chart_label,
        "chart_type": evidence.chart_type,
        "chart_id": evidence.chart_id,
    }
    if evidence.chart_request is not None:
        payload["chart_request"] = dict(evidence.chart_request)
    return payload


def _serialize_metrics(metrics: tuple[FindingMetric, ...]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for metric in metrics[:BRIEF_SERIALIZED_MAX_METRICS]:
        serialized.append(
            {
                "key": metric.key,
                "label": metric.label,
                "value": _round_metric_value(metric.value, metric.unit),
                "unit": metric.unit,
                "display_value": _format_metric_display_value(metric),
            }
        )
    return serialized


def _serialize_finding(finding: SalesBriefFinding) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "rank": finding.rank,
        "lens": finding.lens,
        "lens_label": finding.lens_label,
        "claim": _humanize_text(finding.claim),
        "primary_evidence": _serialize_primary_evidence(finding.primary_evidence),
        "evidence_bullets": [
            _humanize_text(bullet)
            for bullet in finding.evidence_bullets[:BRIEF_SERIALIZED_MAX_BULLETS]
        ],
        "confidence": finding.confidence,
        "metrics": _serialize_metrics(finding.metrics),
    }
    if finding.caution:
        payload["caution"] = _humanize_text(finding.caution)
    return payload


def _serialize_analysis_scope(analysis_scope: AnalysisScope) -> dict[str, Any]:
    return {
        "report_mode": analysis_scope.report_mode,
        "dataset": analysis_scope.dataset,
        "retailers": list(analysis_scope.retailers),
        "categories": list(analysis_scope.categories),
        "brands": list(analysis_scope.brands),
        "price_bands": list(analysis_scope.price_bands),
        "pareto_classes": list(analysis_scope.pareto_classes),
        "attribute_filters": {
            key: list(values)
            for key, values in analysis_scope.attribute_filters.items()
        },
    }


def _format_scope_values(values: tuple[str, ...]) -> str:
    return " / ".join(value for value in values if value)


def _build_brief_title(analysis_scope: AnalysisScope) -> str:
    retailers = _format_scope_values(analysis_scope.retailers)
    categories = _format_scope_values(analysis_scope.categories)
    brands = _format_scope_values(analysis_scope.brands)
    parts = [part for part in (retailers, categories, brands) if part]
    if analysis_scope.report_mode == "brand_report":
        prefix = "Brand scan"
    else:
        prefix = "Market scan"
    if not parts:
        return prefix
    return f"{prefix}: {' / '.join(parts)}"


def _build_brief_finding(
    *,
    rank: int,
    candidate: FindingCandidate,
    selection_context: Mapping[str, Any],
    analysis_scope: AnalysisScope,
    numeric_payloads: Mapping[str, Mapping[str, Any]],
    scope: ScopeSupport,
) -> SalesBriefFinding:
    engine_input = build_finding_engine_input(
        lens=candidate.lens,
        scope=scope,
        analysis_scope=analysis_scope,
        selection_context=selection_context,
        numeric_payloads=numeric_payloads,
    )
    evidence_plan = resolve_finding_evidence_plan(candidate, engine_input)
    return SalesBriefFinding(
        rank=rank,
        lens=candidate.lens,
        lens_label=get_finding_lens_spec(candidate.lens).label,
        claim=candidate.claim,
        primary_evidence=evidence_plan.primary_option,
        supporting_evidence=evidence_plan.supporting_options,
        evidence_bullets=candidate.evidence_bullets,
        confidence=candidate.confidence,
        score_total=candidate.score.total,
        caution=candidate.caution,
        metrics=candidate.metrics,
        story_key=candidate.story_key,
    )


def _build_highlights(
    findings: tuple[SalesBriefFinding, ...],
    *,
    highlight_count: int,
) -> tuple[str, ...]:
    if highlight_count <= 0:
        return ()
    preferred_findings = tuple(
        finding
        for finding in findings
        if not (
            finding.lens == "growth_size"
            and "volatile" in finding.claim.lower()
        )
    )
    highlight_source = preferred_findings or findings
    highlights: list[str] = []
    seen_lenses: set[Lens] = set()
    for finding in highlight_source:
        if finding.lens in seen_lenses:
            continue
        highlights.append(finding.claim)
        seen_lenses.add(finding.lens)
        if len(highlights) >= highlight_count:
            return tuple(highlights)
    for finding in highlight_source:
        if finding.claim in highlights:
            continue
        highlights.append(finding.claim)
        if len(highlights) >= highlight_count:
            break
    return tuple(highlights)


def _filter_export_findings(
    findings: tuple[SalesBriefFinding, ...],
) -> tuple[SalesBriefFinding, ...]:
    has_structural_growth_story = any(
        finding.lens == "growth_size"
        and finding.story_key == "growth_size:trend_level"
        for finding in findings
    )
    filtered: list[SalesBriefFinding] = []
    for finding in findings:
        if (
            BRIEF_SUPPRESS_VOLATILITY_WHEN_STRUCTURAL_GROWTH
            and has_structural_growth_story
            and finding.lens == "growth_size"
            and finding.story_key == "growth_size:volatility"
        ):
            continue
        filtered.append(finding)
    return tuple(
        SalesBriefFinding(
            rank=index,
            lens=finding.lens,
            lens_label=finding.lens_label,
            claim=finding.claim,
            primary_evidence=finding.primary_evidence,
            supporting_evidence=finding.supporting_evidence,
            evidence_bullets=finding.evidence_bullets,
            confidence=finding.confidence,
            score_total=finding.score_total,
            caution=finding.caution,
            metrics=finding.metrics,
            story_key=finding.story_key,
        )
        for index, finding in enumerate(filtered, start=1)
    )


def build_sales_brief_artifact(
    *,
    scope: ScopeSupport = "single_category",
    analysis_scope: AnalysisScope | None = None,
    selection_context: Mapping[str, Any],
    numeric_payloads: Mapping[str, Mapping[str, Any]] | None = None,
    lenses: tuple[Lens, ...] | list[Lens] | None = None,
    attribute_dimensions: tuple[str, ...] | list[str] = (),
    max_findings: int = DEFAULT_BRIEF_MAX_FINDINGS,
    max_per_lens: int = DEFAULT_BRIEF_MAX_PER_LENS,
    highlight_count: int = DEFAULT_BRIEF_HIGHLIGHT_COUNT,
) -> SalesBriefArtifact:
    resolved_scope = analysis_scope or build_analysis_scope()
    resolved_numeric_payloads = dict(numeric_payloads or {})
    shortlisted = build_ranked_finding_shortlist(
        scope=scope,
        analysis_scope=resolved_scope,
        selection_context=selection_context,
        numeric_payloads=resolved_numeric_payloads,
        lenses=lenses,
        max_findings=max_findings,
        max_per_lens=max_per_lens,
    )
    findings = tuple(
        _build_brief_finding(
            rank=index,
            candidate=candidate,
            selection_context=selection_context,
            analysis_scope=resolved_scope,
            numeric_payloads=resolved_numeric_payloads,
            scope=scope,
        )
        for index, candidate in enumerate(shortlisted, start=1)
    )
    findings = _filter_export_findings(findings)
    section_map: dict[Lens, list[SalesBriefFinding]] = {}
    section_order: list[Lens] = []
    for finding in findings:
        if finding.lens not in section_map:
            section_map[finding.lens] = []
            section_order.append(finding.lens)
        section_map[finding.lens].append(finding)
    sections = tuple(
        SalesBriefSection(
            lens=lens,
            title=get_finding_lens_spec(lens).label,
            findings=tuple(section_map[lens]),
        )
        for lens in section_order
    )
    return SalesBriefArtifact(
        title=_build_brief_title(resolved_scope),
        scope=scope,
        analysis_scope=resolved_scope,
        attribute_dimensions=tuple(str(value).strip() for value in attribute_dimensions if str(value).strip()),
        highlights=_build_highlights(findings, highlight_count=highlight_count),
        sections=sections,
        findings=findings,
    )


def build_sales_brief_payload(artifact: SalesBriefArtifact) -> dict[str, Any]:
    return {
        "title": artifact.title,
        "scope": artifact.scope,
        "analysis_scope": _serialize_analysis_scope(artifact.analysis_scope),
        "attribute_dimensions": list(artifact.attribute_dimensions),
        "highlights": [_humanize_text(highlight) for highlight in artifact.highlights],
        "sections": [
            {
                "lens": section.lens,
                "title": section.title,
                "findings": [_serialize_finding(finding) for finding in section.findings],
            }
            for section in artifact.sections
        ],
    }
