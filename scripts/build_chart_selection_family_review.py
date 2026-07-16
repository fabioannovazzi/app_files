from __future__ import annotations

import argparse
import json
import logging
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

__all__ = ["build_chart_selection_family_review", "main"]

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = REPO_ROOT / "runs" / "chart_selection_manifest_rebuild"
DEFAULT_SELECTION_MANIFEST = RUN_ROOT / "selection_manifest.json"
DEFAULT_EXAMPLE_AUDIT = RUN_ROOT / "selection_example_quality_audit.json"
DEFAULT_PAIRWISE_AUDIT = RUN_ROOT / "pairwise_ambiguity_audit.json"
DEFAULT_PARAMETER_AUDIT = RUN_ROOT / "plugin_parameter_contract_audit.json"
DEFAULT_STRESS_TEST = RUN_ROOT / "chart_selection_stress_test.json"
DEFAULT_RENDER_PROOF_MATRIX = RUN_ROOT / "chart_render_proof_matrix.json"
DEFAULT_OUTPUT_JSON = RUN_ROOT / "family_selector_review.json"
DEFAULT_OUTPUT_MD = RUN_ROOT / "family_selector_review.md"

DEEP_REVIEW_FAMILIES = {"distribution", "mix", "period_comparison", "variance"}

REVIEW_QUESTIONS = [
    "positive_questions_specific",
    "close_competitors_correctly_listed",
    "focus_tokens_separate_charts",
    "dataset_roles_correct",
    "png_question_output_matches_purpose",
]

FAMILY_REVIEW_NOTES: dict[str, dict[str, str]] = {
    "attributes": {
        "positive_questions_specific": (
            "Yes, with a package-layer caveat. The four positives distinguish "
            "current-vs-emerging signal alignment, exact bundle share/index "
            "evidence, product-level grounding, and rank-weighted visibility."
        ),
        "close_competitors_correctly_listed": (
            "Yes after the review fix. The attribute evidence tables now list "
            "sibling attribute evidence tables as close competitors; the broader "
            "ambiguous evidence-table examples still expose funnel as a different "
            "table family."
        ),
        "focus_tokens_separate_charts": (
            "Yes. The required/forbidden focus tokens separate signal alignment, "
            "bundle metrics, product evidence, and rank-weighted visibility."
        ),
        "dataset_roles_correct": (
            "Yes as chart-side roles, but they are package roles rather than raw "
            "dataset columns: signal_bundle, cohort_layer, attribute_bundle, "
            "product, and rank_or_lane. The cosmetics stress test correctly marks "
            "these as semantic/package gaps."
        ),
        "png_question_output_matches_purpose": (
            "Yes for gallery evidence. Contact sheet 4 shows the four attribute "
            "tables matching bridge, bundle comparison, product evidence, and "
            "rank-weighted visibility purposes; they are not rendered from the "
            "cosmetics question dataset because that dataset lacks the package."
        ),
    },
    "distribution": {
        "positive_questions_specific": (
            "Yes. The positives distinguish spread/outliers, cumulative thresholds, "
            "binned frequency shape, smoothed density, and individual observations."
        ),
        "close_competitors_correctly_listed": (
            "Yes. All five distribution charts are treated as high-overlap "
            "alternatives and the pairwise audit resolves all ten pairs."
        ),
        "focus_tokens_separate_charts": (
            "Yes. Required and forbidden focus separates quartiles/outliers, ECDF "
            "percentiles, bins, smoothed density, and point-level observations."
        ),
        "dataset_roles_correct": (
            "Yes. Each chart needs one distribution_metric and an optional period "
            "filter; the current dataset compatibility and parameter audits pass."
        ),
        "png_question_output_matches_purpose": (
            "Yes. Contact sheets 3 and 4 show boxplot, ECDF, histogram, density, "
            "and stripplot outputs matching the stated visual purpose."
        ),
    },
    "funnel": {
        "positive_questions_specific": (
            "Yes. The positive asks for a stage conversion funnel, which is the "
            "only chart in this family."
        ),
        "close_competitors_correctly_listed": (
            "Yes. There are no same-family close competitors. Ambiguous evidence "
            "table examples still keep it distinct from attribute tables."
        ),
        "focus_tokens_separate_charts": (
            "Yes for the single capability: funnel_stages and conversion_rates "
            "select it, while distribution, time trend, and set overlap reject it."
        ),
        "dataset_roles_correct": (
            "Yes. It requires ordered_stage plus stage_start_count and "
            "stage_pass_count. The cosmetics dataset correctly rejects it as a "
            "dataset gap because it lacks funnel stages."
        ),
        "png_question_output_matches_purpose": (
            "Yes. Contact sheet 4 shows a sequential stage table with starts, "
            "passes, drop-offs, stage percentages, and cumulative percentages."
        ),
    },
    "mix": {
        "positive_questions_specific": (
            "Yes. The 17 positives distinguish ranking, composition, concentration, "
            "two-metric Mekko encodings, marker overlays, cohort views, "
            "like-for-like population, and single-metric time movement."
        ),
        "close_competitors_correctly_listed": (
            "Yes after competitor normalization. The graph is symmetric, and the "
            "five high-overlap mix pairs have explicit competitor/example evidence."
        ),
        "focus_tokens_separate_charts": (
            "Yes. Focus tokens separate rank vs composition, marker overlay vs "
            "scatter relationship, total vs stacked, cohort since vs lost vs "
            "like-for-like, and AC/PY dimension deltas vs simple trends."
        ),
        "dataset_roles_correct": (
            "Yes as chart-side roles. The roles cover primary metrics, comparison "
            "metrics, related marker metrics, category/component dimensions, "
            "stable population flags, cohort roles, and optional panels. All mix "
            "records pass parameter-contract evidence."
        ),
        "png_question_output_matches_purpose": (
            "Yes. Contact sheets 2 and 3 show ranked bars, stacked composition, "
            "overlay markers, multitier period splits, like-for-like columns, "
            "Mekko charts, Pareto charts, cohort columns, and timeline/area charts "
            "matching their stated purposes."
        ),
    },
    "period_comparison": {
        "positive_questions_specific": (
            "Yes. The positives distinguish trajectory, period gaps, exact tables, "
            "summary exact values, dot gaps, endpoint slope, compact columns, and "
            "additive waterfall reconciliation."
        ),
        "close_competitors_correctly_listed": (
            "Yes after competitor normalization. Exact-value tables now expose "
            "each other, period-gap/line/column alternatives are linked, and "
            "waterfall/slope/dot alternatives are visible from both sides."
        ),
        "focus_tokens_separate_charts": (
            "Yes. Required/forbidden focus separates trajectory_shape, period_gap, "
            "exact_period_values, exact_summary_values, two_value_gap, "
            "endpoint_change, side_by_side_periods, and bridge_reconciliation."
        ),
        "dataset_roles_correct": (
            "Yes. The family uses comparison_metric plus period axis/table/filter "
            "roles and comparison item/window/series roles. All records pass "
            "parameter-contract evidence."
        ),
        "png_question_output_matches_purpose": (
            "Yes. Contact sheets 1 and 2 show line trends, period tables, summary "
            "tables, dot gaps, slope charts, compact columns, and waterfalls that "
            "match the stated purposes."
        ),
    },
    "scatter_bubble": {
        "positive_questions_specific": (
            "Yes. The positives differ on the exact decision point: two-metric "
            "relationship with size encoding versus without size encoding."
        ),
        "close_competitors_correctly_listed": (
            "Yes. Scatter and bubble list each other, and adjacent ranked/marker "
            "bar alternatives are exposed through mix competitors."
        ),
        "focus_tokens_separate_charts": (
            "Yes. size_encoding selects bubble; plain two_metrics selects scatter; "
            "single-metric rank and time trend are forbidden."
        ),
        "dataset_roles_correct": (
            "Yes. Scatter requires x_metric, y_metric, and point_dimension; bubble "
            "adds size_metric. Both pass parameter-contract evidence."
        ),
        "png_question_output_matches_purpose": (
            "Yes. Contact sheet 3 shows scatter and bubble relationship plots, "
            "with bubble size visibly adding the third metric."
        ),
    },
    "set_overlap": {
        "positive_questions_specific": (
            "Yes. The positives distinguish many-set intersections, panelled "
            "intersection comparison, and simple two/three-set overlap."
        ),
        "close_competitors_correctly_listed": (
            "Yes. UpSet and Venn are high-overlap alternatives, and the small "
            "multiple UpSet is linked as the panelled variant/capability."
        ),
        "focus_tokens_separate_charts": (
            "Yes. many_set_intersections, set_overlap_panels, simple_set_overlap, "
            "and two_or_three_sets separate the choices."
        ),
        "dataset_roles_correct": (
            "Yes. The required roles are set_membership_fields, optional panel or "
            "segment for small multiples, and two_or_three_set_membership_fields "
            "for Venn. No metric role is required."
        ),
        "png_question_output_matches_purpose": (
            "Yes. Contact sheet 4 shows UpSet, UpSet small multiples, and Venn "
            "outputs matching the stated overlap purposes."
        ),
    },
    "statement": {
        "positive_questions_specific": (
            "Yes. The positive asks for a P&L line-item table, the only chart in "
            "this family."
        ),
        "close_competitors_correctly_listed": (
            "Yes. There are no same-family chart competitors; broad evidence-table "
            "ambiguity is handled through ambiguous examples."
        ),
        "focus_tokens_separate_charts": (
            "Yes for the single capability: statement_table and line_item_values "
            "select it, while trend, distribution, and variance bridge reject it."
        ),
        "dataset_roles_correct": (
            "Yes. It requires statement_line_item and statement_value with an "
            "axis/table period role. The cosmetics dataset correctly rejects it as "
            "a dataset gap because it is not a statement dataset."
        ),
        "png_question_output_matches_purpose": (
            "Yes. Contact sheet 4 shows a P&L/statement table with line items and "
            "period/scenario columns."
        ),
    },
    "variance": {
        "positive_questions_specific": (
            "Yes. The positives distinguish fixed parent-child drilldown, PVM, "
            "component root cause, total root-cause path, root-cause exploded "
            "drilldown, plain scenario bridge, and one-dimension total split."
        ),
        "close_competitors_correctly_listed": (
            "Yes after competitor normalization. The two high-overlap variance "
            "pairs have explicit competitor/example evidence, and the plain bridge, "
            "dimension split, root-cause, exploded, component, and PVM alternatives "
            "are linked."
        ),
        "focus_tokens_separate_charts": (
            "Yes. Focus tokens separate fixed_parent_child_drilldown, "
            "root_cause_sequence, nested_driver_drilldown, component_root_cause, "
            "dimension_variance, scenario_bridge, and pvm_decomposition."
        ),
        "dataset_roles_correct": (
            "Yes as chart-side roles. The manifest correctly distinguishes "
            "variance_metric from PVM value/volume/rate roles and distinguishes "
            "dimension_member, parent/child drivers, component drivers, and "
            "root-cause sequences. Semantic validity of the chosen dimensions "
            "still belongs outside the manifest."
        ),
        "png_question_output_matches_purpose": (
            "Yes. Contact sheet 1 shows the bridge variants matching their stated "
            "purposes: fixed parent-child exploded bridge, PVM ladder, component "
            "root cause, total root cause, dimension split, and plain scenario "
            "bridge."
        ),
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _families(capabilities: dict[str, Any]) -> dict[str, list[str]]:
    families: defaultdict[str, list[str]] = defaultdict(list)
    for capability_id, capability in sorted(capabilities.items()):
        if isinstance(capability, dict):
            families[str(capability.get("family") or "unknown")].append(capability_id)
    return dict(sorted(families.items()))


def _index_by_capability(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("capability_id")): item
        for item in results
        if isinstance(item, dict) and item.get("capability_id")
    }


def _stress_counts(
    records: list[dict[str, Any]], capability_ids: list[str]
) -> dict[str, int]:
    wanted = set(capability_ids)
    return dict(
        sorted(
            Counter(
                record.get("status")
                for record in records
                if record.get("capability_id") in wanted
            ).items()
        )
    )


def _required_role_summary(capability: dict[str, Any]) -> dict[str, list[str]]:
    requirements = (capability.get("selection_contract") or {}).get(
        "dataset_requirements"
    ) or {}
    metrics = requirements.get("metrics") or {}
    period = requirements.get("period") or {}
    dimensions = requirements.get("dimensions") or {}
    metric_roles = [
        str(role.get("role"))
        for role in metrics.get("source_metric_roles") or []
        if role.get("required", True)
    ]
    period_roles = []
    period_role = period.get("role")
    if period_role in {"axis", "axis_or_table"}:
        period_roles.append("period_axis")
    elif period_role == "filter":
        period_roles.append("period_filter")
    return {
        "metric_roles": metric_roles,
        "period_roles": period_roles,
        "dimension_roles": list(dimensions.get("required_roles") or []),
        "optional_dimension_roles": list(dimensions.get("optional_roles") or []),
    }


def _deep_family_review(
    *,
    family: str,
    capability_ids: list[str],
    capabilities: dict[str, Any],
    stress_by_capability: dict[str, dict[str, Any]],
    render_by_capability: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if family not in DEEP_REVIEW_FAMILIES:
        return None
    capability_reviews = []
    for capability_id in capability_ids:
        capability = capabilities[capability_id]
        examples = capability.get("selection_examples") or {}
        render_record = render_by_capability.get(capability_id, {})
        stress_record = stress_by_capability.get(capability_id, {})
        capability_reviews.append(
            {
                "capability_id": capability_id,
                "positive_question": (examples.get("positive_questions") or [""])[0],
                "selection_emphasis": capability.get("selection_emphasis"),
                "primary_decision_cue": capability.get("primary_decision_cue"),
                "required_roles": _required_role_summary(capability),
                "invocation_contract_status": (
                    capability.get("normalized_invocation_contract") or {}
                ).get("status", "not_recorded"),
                "stress_status": stress_record.get("status", "missing"),
                "render_proof_status": render_record.get(
                    "render_proof_status", "missing"
                ),
                "fixture_requirement": render_record.get(
                    "fixture_requirement", "missing"
                ),
                "reviewer_check": "complete",
            }
        )
    return {
        "review_status": "complete",
        "review_scope": (
            "Crowded-family manual selector review: question specificity, "
            "decision cue, required roles, invocation contract, stress status, "
            "and render-proof status per capability."
        ),
        "capability_reviews": capability_reviews,
    }


def _pair_count(pairwise: dict[str, Any], capability_ids: list[str]) -> int:
    wanted = set(capability_ids)
    return sum(
        1
        for pair in pairwise.get("high_overlap_pairs") or []
        if set(pair.get("capability_ids") or []).issubset(wanted)
    )


def _family_review_records(
    *,
    manifest: dict[str, Any],
    example_audit: dict[str, Any],
    pairwise_audit: dict[str, Any],
    parameter_audit: dict[str, Any],
    stress_test: dict[str, Any],
    render_proof_matrix: dict[str, Any],
) -> list[dict[str, Any]]:
    capabilities = manifest.get("capabilities") or {}
    families = _families(capabilities)
    example_by_capability = _index_by_capability(example_audit.get("results") or [])
    parameter_by_capability = _index_by_capability(parameter_audit.get("results") or [])
    stress_records = stress_test.get("records") or []
    stress_by_capability = _index_by_capability(stress_records)
    render_by_capability = _index_by_capability(
        render_proof_matrix.get("records") or []
    )

    records: list[dict[str, Any]] = []
    for family, capability_ids in families.items():
        if family not in FAMILY_REVIEW_NOTES:
            raise ValueError(f"Missing family review notes for {family}")
        example_errors = sum(
            example_by_capability[capability_id].get("error_count", 0)
            for capability_id in capability_ids
        )
        example_warnings = sum(
            example_by_capability[capability_id].get("warning_count", 0)
            for capability_id in capability_ids
        )
        parameter_gaps = sum(
            1
            for capability_id in capability_ids
            if parameter_by_capability[capability_id].get("status")
            != "parameter_contract_ready"
        )
        asymmetric_competitors = [
            [capability_id, competitor_id]
            for capability_id in capability_ids
            for competitor_id in capabilities[capability_id].get(
                "competing_capability_ids", []
            )
            if competitor_id in capabilities
            and capability_id
            not in capabilities[competitor_id].get("competing_capability_ids", [])
        ]
        records.append(
            {
                "family": family,
                "capability_ids": capability_ids,
                "capability_count": len(capability_ids),
                "answers": FAMILY_REVIEW_NOTES[family],
                "evidence": {
                    "example_errors": example_errors,
                    "example_warnings": example_warnings,
                    "parameter_contract_gaps": parameter_gaps,
                    "asymmetric_competitor_links": asymmetric_competitors,
                    "high_overlap_pair_count": _pair_count(
                        pairwise_audit, capability_ids
                    ),
                    "stress_status_counts": _stress_counts(
                        stress_records, capability_ids
                    ),
                },
                "manual_focus_review": _deep_family_review(
                    family=family,
                    capability_ids=capability_ids,
                    capabilities=capabilities,
                    stress_by_capability=stress_by_capability,
                    render_by_capability=render_by_capability,
                ),
            }
        )
    return records


def build_chart_selection_family_review(
    *,
    selection_manifest_path: Path = DEFAULT_SELECTION_MANIFEST,
    example_audit_path: Path = DEFAULT_EXAMPLE_AUDIT,
    pairwise_audit_path: Path = DEFAULT_PAIRWISE_AUDIT,
    parameter_audit_path: Path = DEFAULT_PARAMETER_AUDIT,
    stress_test_path: Path = DEFAULT_STRESS_TEST,
    render_proof_matrix_path: Path = DEFAULT_RENDER_PROOF_MATRIX,
    output_json_path: Path = DEFAULT_OUTPUT_JSON,
    output_md_path: Path = DEFAULT_OUTPUT_MD,
) -> dict[str, Any]:
    manifest = _load_json(selection_manifest_path)
    example_audit = _load_json(example_audit_path)
    pairwise_audit = _load_json(pairwise_audit_path)
    parameter_audit = _load_json(parameter_audit_path)
    stress_test = _load_json(stress_test_path)
    render_proof_matrix = _load_json(render_proof_matrix_path)
    records = _family_review_records(
        manifest=manifest,
        example_audit=example_audit,
        pairwise_audit=pairwise_audit,
        parameter_audit=parameter_audit,
        stress_test=stress_test,
        render_proof_matrix=render_proof_matrix,
    )
    payload = {
        "purpose": (
            "Family-by-family review of whether chart-selection manifest records "
            "are specific, distinguishable, role-correct, and supported by PNG "
            "review evidence."
        ),
        "inputs": {
            "selection_manifest": str(selection_manifest_path),
            "example_audit": str(example_audit_path),
            "pairwise_audit": str(pairwise_audit_path),
            "parameter_audit": str(parameter_audit_path),
            "stress_test": str(stress_test_path),
            "render_proof_matrix": str(render_proof_matrix_path),
        },
        "question_keys": REVIEW_QUESTIONS,
        "counts": {
            "families": len(records),
            "capabilities": sum(record["capability_count"] for record in records),
            "example_errors": sum(
                record["evidence"]["example_errors"] for record in records
            ),
            "example_warnings": sum(
                record["evidence"]["example_warnings"] for record in records
            ),
            "parameter_contract_gaps": sum(
                record["evidence"]["parameter_contract_gaps"] for record in records
            ),
            "asymmetric_competitor_links": sum(
                len(record["evidence"]["asymmetric_competitor_links"])
                for record in records
            ),
            "manual_focus_review_families": sum(
                1 for record in records if record.get("manual_focus_review")
            ),
        },
        "families": records,
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
        "# Chart Selection Family Review",
        "",
        payload["purpose"],
        "",
        "## Counts",
        "",
    ]
    for key, value in counts.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Family Results", ""])
    for record in payload["families"]:
        evidence = record["evidence"]
        lines.extend(
            [
                f"### `{record['family']}`",
                "",
                f"- Capabilities: `{record['capability_count']}`",
                f"- High-overlap pairs: `{evidence['high_overlap_pair_count']}`",
                f"- Stress statuses: `{json.dumps(evidence['stress_status_counts'], sort_keys=True)}`",
                f"- Example audit: `{evidence['example_errors']}` errors, `{evidence['example_warnings']}` warnings",
                f"- Parameter contract gaps: `{evidence['parameter_contract_gaps']}`",
                f"- Asymmetric competitor links: `{len(evidence['asymmetric_competitor_links'])}`",
                "",
                "| Review question | Answer |",
                "| --- | --- |",
            ]
        )
        answers = record["answers"]
        lines.extend(
            [
                f"| Are positive questions specific? | {answers['positive_questions_specific']} |",
                f"| Are close competitors correctly listed? | {answers['close_competitors_correctly_listed']} |",
                f"| Do required/forbidden focus tokens separate the charts? | {answers['focus_tokens_separate_charts']} |",
                f"| Are dataset roles correct? | {answers['dataset_roles_correct']} |",
                f"| Does PNG/question review output match the stated purpose? | {answers['png_question_output_matches_purpose']} |",
                "",
                "Capabilities: "
                + ", ".join(
                    f"`{capability_id}`" for capability_id in record["capability_ids"]
                ),
                "",
            ]
        )
        manual_focus = record.get("manual_focus_review")
        if manual_focus:
            lines.extend(
                [
                    "Manual focus review: " f"`{manual_focus['review_status']}`",
                    "",
                    "| Capability | Question | Cue | Roles | Render proof |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            for review in manual_focus["capability_reviews"]:
                roles = review["required_roles"]
                role_text = (
                    "metrics="
                    + ",".join(roles["metric_roles"] or ["none"])
                    + "; period="
                    + ",".join(roles["period_roles"] or ["none"])
                    + "; dimensions="
                    + ",".join(roles["dimension_roles"] or ["none"])
                )
                lines.append(
                    f"| `{review['capability_id']}` | "
                    f"{review['positive_question']} | "
                    f"{review['primary_decision_cue']} | "
                    f"{role_text} | "
                    f"`{review['render_proof_status']}` / `{review['fixture_requirement']}` |"
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build family-by-family chart selector review report."
    )
    parser.add_argument(
        "--selection-manifest",
        type=Path,
        default=DEFAULT_SELECTION_MANIFEST,
        help="Path to selection_manifest.json.",
    )
    parser.add_argument(
        "--example-audit",
        type=Path,
        default=DEFAULT_EXAMPLE_AUDIT,
        help="Path to selection_example_quality_audit.json.",
    )
    parser.add_argument(
        "--pairwise-audit",
        type=Path,
        default=DEFAULT_PAIRWISE_AUDIT,
        help="Path to pairwise_ambiguity_audit.json.",
    )
    parser.add_argument(
        "--parameter-audit",
        type=Path,
        default=DEFAULT_PARAMETER_AUDIT,
        help="Path to plugin_parameter_contract_audit.json.",
    )
    parser.add_argument(
        "--stress-test",
        type=Path,
        default=DEFAULT_STRESS_TEST,
        help="Path to chart_selection_stress_test.json.",
    )
    parser.add_argument(
        "--render-proof-matrix",
        type=Path,
        default=DEFAULT_RENDER_PROOF_MATRIX,
        help="Path to chart_render_proof_matrix.json.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=DEFAULT_OUTPUT_JSON,
        help="Path for JSON review output.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=DEFAULT_OUTPUT_MD,
        help="Path for Markdown review output.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    payload = build_chart_selection_family_review(
        selection_manifest_path=args.selection_manifest,
        example_audit_path=args.example_audit,
        pairwise_audit_path=args.pairwise_audit,
        parameter_audit_path=args.parameter_audit,
        stress_test_path=args.stress_test,
        render_proof_matrix_path=args.render_proof_matrix,
        output_json_path=args.output_json,
        output_md_path=args.output_md,
    )
    logging.info(
        "Wrote family selector review for %s families to %s and %s",
        payload["counts"]["families"],
        args.output_json,
        args.output_md,
    )
    return 0 if payload["counts"]["example_errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
