from __future__ import annotations

import argparse
import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any

__all__ = ["audit_chart_selection_examples", "main"]

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SELECTION_MANIFEST = (
    REPO_ROOT / "runs" / "chart_selection_manifest_rebuild" / "selection_manifest.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "runs"
    / "chart_selection_manifest_rebuild"
    / "selection_example_quality_audit.json"
)
DEFAULT_OUTPUT_MD = DEFAULT_OUTPUT_JSON.with_suffix(".md")

WEAK_FOCUS_TERMS = {
    "and",
    "baseline",
    "by",
    "comparison",
    "current",
    "data",
    "evidence",
    "focus",
    "metric",
    "period",
    "question",
    "selected",
    "table",
    "total",
    "value",
    "values",
}

# This is a deterministic evidence check, not semantic judgment: these aliases
# only test whether authored examples contain visible cue words for the manifest
# focus tokens. The model/caller still owns interpretation of user intent.
FOCUS_TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "additive_period_variance": ("variances reconcile", "reconcile", "add up"),
    "area_trend": ("area trend", "area"),
    "attribute_bundle_metrics": ("attribute bundles", "bundle"),
    "attribute_ranking": ("rank", "visibility"),
    "attribute_signal_alignment": ("align", "diverge", "signal"),
    "baseline_to_current_total": ("baseline to current", "current", "prior-year"),
    "bridge_reconciliation": ("reconcile", "waterfall", "bridge"),
    "category_comparison": ("rank categories", "compare categories", "category"),
    "column_summary": ("columns", "column"),
    "comparison_table": ("table", "exact"),
    "component_breakdown": ("component", "breakdown", "composition"),
    "component_root_cause": ("root-cause component", "component"),
    "composition_change": ("mix", "composition", "change"),
    "composition_over_time": ("mix", "composition", "monthly"),
    "composition_size": ("composition", "size", "retailer"),
    "contribution_or_share_over_time": ("contribution", "share", "over time"),
    "conversion_rates": ("conversion", "stage"),
    "cumulative_distribution": ("cumulative", "below"),
    "cumulative_share": ("most", "cumulative", "share"),
    "current_vs_baseline_by_period": ("ac/py", "gap", "months"),
    "current_vs_baseline_period_axis": ("previous year", "monthly", "ac/py"),
    "current_vs_baseline_values": ("two periods", "ac/py", "difference"),
    "current_vs_emerging": ("current", "emerging"),
    "dimension_period_delta": ("two periods", "difference", "delta"),
    "dimension_variance": ("categories account", "dimension", "variance"),
    "distribution_shape": ("distribution", "shape"),
    "distribution_spread": ("spread", "quartiles"),
    "endpoint_change": ("endpoint", "direction", "magnitude"),
    "entity_population_change": ("products by", "cohort", "active"),
    "exact_period_values": ("citeable", "monthly", "values"),
    "exact_summary_values": ("exact", "delta", "percent-delta"),
    "fixed_parent_child_drilldown": ("brands explain", "selected category"),
    "frequency_bins": ("distribution", "observations", "bins"),
    "funnel_stages": ("stage", "funnel"),
    "individual_observations": ("individual", "observations"),
    "like_for_like_population": ("same product", "same products", "active in both"),
    "line_item_values": ("line-item", "p&l"),
    "lost_cohort": ("last active", "lost"),
    "low_clutter_comparison": ("low clutter", "dot"),
    "many_set_intersections": ("shared across", "overlap", "intersections"),
    "nested_driver_drilldown": ("what explains", "selected root-cause"),
    "ordered_periods": ("months", "trend", "monthly"),
    "outliers": ("outliers",),
    "pareto_concentration": ("few", "most", "pareto"),
    "percentile_threshold": ("threshold", "percentile"),
    "period_gap": ("gap", "months"),
    "period_table": ("monthly", "values", "variances"),
    "point_outliers": ("individual", "outliers"),
    "price_volume_mix": ("price", "volume", "mix"),
    "product_level_evidence": ("products", "product"),
    "pvm_decomposition": ("due to price", "price, units, and mix", "decomposes"),
    "rank_plus_marker": ("rank", "overlaying", "marker"),
    "rank_weighted_visibility": ("rank-weighted", "visibility"),
    "ranked_composition": ("composition", "within categories"),
    "relative_direction": ("direction", "magnitude"),
    "root_cause_sequence": ("ordered root-cause path", "root-cause path"),
    "scatter_relationship": ("relate", "relationship"),
    "scenario_bridge": ("plain bridge", "baseline to current", "reconcile"),
    "secondary_metric_marker": ("marker", "context", "overlaying"),
    "selected_variance_component": ("selected", "component"),
    "set_membership": ("shared across", "overlap", "retailers"),
    "set_overlap_panels": ("differ by", "by category", "panels"),
    "share_delta_index": ("share", "delta", "index"),
    "side_by_side_periods": ("compact", "columns", "ac/py"),
    "signal_grounding": ("provide evidence", "signal"),
    "simple_set_overlap": ("simple", "overlap"),
    "since_cohort": ("first active", "since"),
    "single_line_trend": ("single", "trend"),
    "single_metric_rank": ("rank", "categories"),
    "size_encoding": ("weighted by", "bubble", "size"),
    "smoothed_density": ("smoothed", "density"),
    "stacked_periods": ("monthly", "stacked"),
    "stacked_total": ("totals", "composition"),
    "statement_table": ("p&l", "statement"),
    "total_change": ("sales change", "same products"),
    "total_delta_split": ("account for", "variance"),
    "total_metric": ("total", "sales"),
    "total_movement": ("total sales movement", "total movement"),
    "trajectory_shape": ("evolve", "trajectory", "seasonality", "trend"),
    "two_dimension_share": ("category and retailer", "two", "composition"),
    "two_metrics": ("without size", "two metrics"),
    "two_or_three_sets": ("three retailers", "two", "three"),
    "two_value_gap": ("gaps across", "two values"),
    "variable_width_composition": ("variable-width", "width"),
    "variance_bridge": ("variance", "drove"),
    "width_and_height_metrics": ("width", "height"),
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize(text: str) -> str:
    alnum_text = re.sub(r"[^a-z0-9]+", " ", text.casefold())
    return re.sub(r"\s+", " ", alnum_text).strip()


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.casefold())


def _focus_terms(focus_token: str) -> tuple[str, ...]:
    aliases = list(FOCUS_TERM_ALIASES.get(focus_token, ()))
    aliases.extend(
        token
        for token in focus_token.split("_")
        if len(token) > 2 and token not in WEAK_FOCUS_TERMS
    )
    deduped: list[str] = []
    for alias in aliases:
        normalized = _normalize(alias)
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return tuple(deduped)


def _matched_focus_tokens(
    question: str, focus_tokens: list[str]
) -> dict[str, list[str]]:
    normalized_question = _normalize(question)
    matches: dict[str, list[str]] = {}
    for token in focus_tokens:
        terms = [
            term for term in _focus_terms(token) if term and term in normalized_question
        ]
        if terms:
            matches[token] = terms
    return matches


def _issue(
    code: str,
    severity: str,
    detail: str,
    *,
    question: str | None = None,
    capability_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "detail": detail,
    }
    if question is not None:
        payload["question"] = question
    if capability_id is not None:
        payload["capability_id"] = capability_id
    return payload


def _positive_issues(
    capability_id: str,
    capability: dict[str, Any],
    *,
    ambiguous_questions: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    examples = capability.get("selection_examples") or {}
    positives = examples.get("positive_questions") or []
    issues: list[dict[str, Any]] = []
    focus_evidence: list[dict[str, Any]] = []
    if len(positives) != 1:
        issues.append(
            _issue(
                "invalid_positive_question_count",
                "error",
                f"expected exactly one positive question, found {len(positives)}",
                capability_id=capability_id,
            )
        )
    for question in positives:
        if not isinstance(question, str) or not question.strip():
            issues.append(
                _issue(
                    "empty_positive_question",
                    "error",
                    "positive question must be a non-empty string",
                    capability_id=capability_id,
                )
            )
            continue
        normalized = _normalize(question)
        word_count = len(_words(question))
        if word_count < 5:
            issues.append(
                _issue(
                    "positive_question_too_short",
                    "warning",
                    "positive question is too short to carry selector evidence",
                    question=question,
                    capability_id=capability_id,
                )
            )
        if normalized in ambiguous_questions:
            issues.append(
                _issue(
                    "positive_question_duplicates_ambiguous_prompt",
                    "error",
                    "positive question duplicates a broad ambiguous question",
                    question=question,
                    capability_id=capability_id,
                )
            )
        focus_tokens = capability.get("requires_question_focus") or []
        matches = _matched_focus_tokens(question, focus_tokens)
        focus_evidence.append(
            {
                "question": question,
                "focus_tokens": focus_tokens,
                "matched_focus_tokens": matches,
            }
        )
        if not matches:
            issues.append(
                _issue(
                    "positive_question_missing_focus_evidence",
                    "error",
                    "positive question does not contain visible evidence for any requires_question_focus token",
                    question=question,
                    capability_id=capability_id,
                )
            )
        elif len(matches) < min(2, len(focus_tokens)):
            issues.append(
                _issue(
                    "positive_question_partial_focus_evidence",
                    "warning",
                    "positive question contains evidence for only part of requires_question_focus",
                    question=question,
                    capability_id=capability_id,
                )
            )
    return issues, focus_evidence


def _negative_issues(
    capability_id: str,
    capability: dict[str, Any],
    capabilities: dict[str, Any],
) -> list[dict[str, Any]]:
    examples = capability.get("selection_examples") or {}
    negatives = examples.get("negative_questions") or []
    issues: list[dict[str, Any]] = []
    if len(negatives) < 2:
        issues.append(
            _issue(
                "too_few_negative_questions",
                "warning",
                f"expected at least two negative questions, found {len(negatives)}",
                capability_id=capability_id,
            )
        )
    for example in negatives:
        if not isinstance(example, dict):
            issues.append(
                _issue(
                    "invalid_negative_question",
                    "error",
                    "negative example must be an object",
                    capability_id=capability_id,
                )
            )
            continue
        question = example.get("question")
        better_id = example.get("better_capability_id")
        why_not = str(example.get("why_not") or "")
        if not isinstance(question, str) or not question.strip():
            issues.append(
                _issue(
                    "empty_negative_question",
                    "error",
                    "negative question must be a non-empty string",
                    capability_id=capability_id,
                )
            )
        if not isinstance(better_id, str) or better_id not in capabilities:
            issues.append(
                _issue(
                    "negative_question_missing_valid_better_capability",
                    "error",
                    "negative question must name a known better_capability_id",
                    question=question if isinstance(question, str) else None,
                    capability_id=capability_id,
                )
            )
            continue
        if better_id == capability_id:
            issues.append(
                _issue(
                    "negative_question_points_to_self",
                    "error",
                    "negative question cannot point back to the same capability",
                    question=question if isinstance(question, str) else None,
                    capability_id=capability_id,
                )
            )
        other_positive = (
            capabilities[better_id]
            .get("selection_examples", {})
            .get("positive_questions", [])
        )
        if isinstance(question, str) and question not in other_positive:
            issues.append(
                _issue(
                    "negative_question_not_grounded_in_better_positive",
                    "warning",
                    "negative question is not the positive example of the better capability",
                    question=question,
                    capability_id=capability_id,
                )
            )
        this_emphasis = str(capability.get("selection_emphasis") or "")
        other_emphasis = str(capabilities[better_id].get("selection_emphasis") or "")
        if this_emphasis and this_emphasis not in why_not:
            issues.append(
                _issue(
                    "negative_why_not_missing_current_emphasis",
                    "warning",
                    "why_not does not mention the current selection_emphasis",
                    question=question if isinstance(question, str) else None,
                    capability_id=capability_id,
                )
            )
        if other_emphasis and other_emphasis not in why_not:
            issues.append(
                _issue(
                    "negative_why_not_missing_better_emphasis",
                    "warning",
                    "why_not does not mention the better capability selection_emphasis",
                    question=question if isinstance(question, str) else None,
                    capability_id=capability_id,
                )
            )
    return issues


def _ambiguous_issues(
    capability_id: str,
    capability: dict[str, Any],
    capabilities: dict[str, Any],
) -> list[dict[str, Any]]:
    examples = capability.get("selection_examples") or {}
    ambiguous = examples.get("ambiguous_questions") or []
    positive_questions = set(examples.get("positive_questions") or [])
    issues: list[dict[str, Any]] = []
    if len(ambiguous) != 1:
        issues.append(
            _issue(
                "invalid_ambiguous_question_count",
                "error",
                f"expected exactly one ambiguous question, found {len(ambiguous)}",
                capability_id=capability_id,
            )
        )
    for example in ambiguous:
        if not isinstance(example, dict):
            issues.append(
                _issue(
                    "invalid_ambiguous_question",
                    "error",
                    "ambiguous example must be an object",
                    capability_id=capability_id,
                )
            )
            continue
        question = example.get("question")
        candidates = example.get("candidate_capability_ids") or []
        disambiguation = str(example.get("disambiguation_needed") or "")
        if not isinstance(question, str) or not question.strip():
            issues.append(
                _issue(
                    "empty_ambiguous_question",
                    "error",
                    "ambiguous question must be a non-empty string",
                    capability_id=capability_id,
                )
            )
        elif question in positive_questions:
            issues.append(
                _issue(
                    "ambiguous_question_duplicates_positive",
                    "error",
                    "ambiguous question duplicates this capability's positive example",
                    question=question,
                    capability_id=capability_id,
                )
            )
        if capability_id not in candidates:
            issues.append(
                _issue(
                    "ambiguous_candidates_missing_self",
                    "error",
                    "ambiguous candidate list must include this capability",
                    question=question if isinstance(question, str) else None,
                    capability_id=capability_id,
                )
            )
        known_candidates = [
            candidate for candidate in candidates if isinstance(candidate, str)
        ]
        unknown_candidates = [
            candidate for candidate in known_candidates if candidate not in capabilities
        ]
        if unknown_candidates:
            issues.append(
                _issue(
                    "ambiguous_candidates_unknown",
                    "error",
                    "ambiguous candidate list contains unknown capabilities: "
                    + ", ".join(unknown_candidates),
                    question=question if isinstance(question, str) else None,
                    capability_id=capability_id,
                )
            )
        if len(set(known_candidates)) < 2:
            issues.append(
                _issue(
                    "ambiguous_candidates_too_few",
                    "error",
                    "ambiguous question needs at least two candidate capabilities",
                    question=question if isinstance(question, str) else None,
                    capability_id=capability_id,
                )
            )
        for candidate in known_candidates:
            if candidate not in capabilities:
                continue
            emphasis = str(capabilities[candidate].get("selection_emphasis") or "")
            if emphasis and emphasis not in disambiguation:
                issues.append(
                    _issue(
                        "ambiguous_disambiguation_missing_candidate_emphasis",
                        "warning",
                        f"disambiguation does not mention `{candidate}` emphasis `{emphasis}`",
                        question=question if isinstance(question, str) else None,
                        capability_id=capability_id,
                    )
                )
    return issues


def _capability_audit(
    capability_id: str,
    capability: dict[str, Any],
    capabilities: dict[str, Any],
    *,
    ambiguous_questions: set[str],
) -> dict[str, Any]:
    positive_issues, focus_evidence = _positive_issues(
        capability_id, capability, ambiguous_questions=ambiguous_questions
    )
    issues = [
        *positive_issues,
        *_negative_issues(capability_id, capability, capabilities),
        *_ambiguous_issues(capability_id, capability, capabilities),
    ]
    error_count = sum(1 for issue in issues if issue["severity"] == "error")
    warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
    return {
        "capability_id": capability_id,
        "family": capability.get("family"),
        "status": "pass" if error_count == 0 else "fail",
        "error_count": error_count,
        "warning_count": warning_count,
        "positive_focus_evidence": focus_evidence,
        "issues": issues,
    }


def audit_chart_selection_examples(
    *,
    selection_manifest_path: Path = DEFAULT_SELECTION_MANIFEST,
    output_json_path: Path = DEFAULT_OUTPUT_JSON,
    output_md_path: Path = DEFAULT_OUTPUT_MD,
) -> dict[str, Any]:
    manifest = _load_json(selection_manifest_path)
    capabilities = manifest.get("capabilities") or {}
    if not isinstance(capabilities, dict):
        raise ValueError("selection manifest capabilities must be an object")
    ambiguous_questions = {
        _normalize(example.get("question"))
        for capability in capabilities.values()
        for example in (capability.get("selection_examples") or {}).get(
            "ambiguous_questions", []
        )
        if isinstance(example, dict) and isinstance(example.get("question"), str)
    }
    results = [
        _capability_audit(
            capability_id,
            capability,
            capabilities,
            ambiguous_questions=ambiguous_questions,
        )
        for capability_id, capability in sorted(capabilities.items())
        if isinstance(capability, dict)
    ]
    issue_counts = Counter(
        issue["code"] for result in results for issue in result.get("issues") or []
    )
    severity_counts = Counter(
        issue["severity"] for result in results for issue in result.get("issues") or []
    )
    family_counts = Counter(
        result["family"]
        for result in results
        if any(issue["severity"] == "error" for issue in result.get("issues") or [])
    )
    payload = {
        "purpose": (
            "Audit whether chart-selection examples are structurally usable "
            "selector evidence: positive examples must carry visible focus cues, "
            "negative examples must point to a better known chart, and ambiguous "
            "examples must preserve candidate distinctions."
        ),
        "inputs": {"selection_manifest": str(selection_manifest_path)},
        "counts": {
            "capabilities": len(results),
            "passed": sum(1 for result in results if result["status"] == "pass"),
            "failed": sum(1 for result in results if result["status"] == "fail"),
            "errors": severity_counts["error"],
            "warnings": severity_counts["warning"],
        },
        "issue_counts": dict(sorted(issue_counts.items())),
        "families_with_errors": dict(sorted(family_counts.items())),
        "results": results,
    }
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    output_md_path.write_text(_markdown(payload), encoding="utf-8")
    return payload


def _markdown(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    lines = [
        "# Chart Selection Example Quality Audit",
        "",
        payload["purpose"],
        "",
        "## Counts",
        "",
    ]
    for key, value in counts.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Issues", ""])
    issue_counts = payload.get("issue_counts") or {}
    if not issue_counts:
        lines.append("- None")
    else:
        for key, value in issue_counts.items():
            lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Capability Results", ""])
    for result in payload["results"]:
        lines.append(
            f"- `{result['capability_id']}`: `{result['status']}` "
            f"(`{result['error_count']}` errors, "
            f"`{result['warning_count']}` warnings)"
        )
        for issue in result.get("issues") or []:
            lines.append(
                "  - " f"`{issue['severity']}` `{issue['code']}`: {issue['detail']}"
            )
    lines.append("")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selection-manifest",
        type=Path,
        default=DEFAULT_SELECTION_MANIFEST,
        help="Selection manifest JSON path.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=DEFAULT_OUTPUT_JSON,
        help="Output JSON audit path.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=DEFAULT_OUTPUT_MD,
        help="Output Markdown audit path.",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper()))
    payload = audit_chart_selection_examples(
        selection_manifest_path=args.selection_manifest,
        output_json_path=args.output_json,
        output_md_path=args.output_md,
    )
    logging.info("wrote %s", args.output_json)
    logging.info("wrote %s", args.output_md)
    return 0 if payload["counts"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
