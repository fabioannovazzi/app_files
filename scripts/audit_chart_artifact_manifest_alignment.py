from __future__ import annotations

import json
import csv
from collections import Counter
from pathlib import Path
from typing import Any

__all__ = ["audit_chart_artifact_manifest_alignment", "main"]

REPO_ROOT = Path(__file__).resolve().parents[1]
GALLERY_DIR = REPO_ROOT / "static" / "shared" / "png-gallery"
DEFAULT_MANIFEST = (
    REPO_ROOT / "runs" / "chart_selection_manifest_rebuild" / "selection_manifest.json"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "runs"
    / "chart_selection_manifest_rebuild"
    / "artifact_manifest_alignment_audit.md"
)


CAPABILITY_TOKENS: dict[str, tuple[str, ...]] = {
    "period_comparison.trend": ("line", "trend", "trajectory", "year_over_year"),
    "period_comparison.by_period": ("period", "gap", "by_period"),
    "period_comparison.time_series_table": ("time_series", "table", "monthly"),
    "period_comparison.comparison_table": ("comparison_table", "summary"),
    "period_comparison.multitier_column": ("column", "side_by_side"),
    "period_comparison.dot": ("dot", "gap"),
    "period_comparison.slope": ("slope", "endpoint"),
    "period_comparison.horizontal_waterfall": ("waterfall", "bridge", "reconciliation"),
    "mix.bar": ("bar", "rank"),
    "mix.stacked_bar": ("stacked_bar", "composition"),
    "mix.stacked_bar_overlay": ("related_metrics", "marker", "overlay"),
    "mix.multitier_bar": ("multitier", "nested"),
    "mix.column": ("column", "total"),
    "mix.column_overlay": ("column", "overlay", "marker"),
    "mix.stacked_column": ("stacked_column", "composition"),
    "mix.like_for_like_column": ("like_for_like", "column"),
    "mix.like_for_like_stacked_column": ("like_for_like", "stacked"),
    "mix.cohort_since_stacked_column": ("cohort", "since"),
    "mix.cohort_lost_stacked_column": ("cohort", "lost"),
    "mix.timeline": ("line", "timeline", "trend"),
    "mix.area": ("area", "share", "absolute"),
    "mix.barmekko": ("barmekko", "width", "height"),
    "mix.marimekko": ("marimekko", "composition"),
    "mix.pareto": ("pareto", "rank", "concentration"),
    "mix.stacked_pareto": ("stacked_pareto", "pareto", "concentration"),
    "scatter.scatter": ("scatter",),
    "scatter.bubble": ("bubble",),
    "distribution.histogram": ("histogram",),
    "distribution.boxplot": ("box", "boxplot"),
    "distribution.stripplot": ("strip", "points"),
    "distribution.ecdf": ("ecdf", "cumulative"),
    "distribution.kernel_density": ("density", "kde", "kernel"),
    "variance.scenario_bridge": ("waterfall", "bridge", "variance"),
    "variance.total_by_dimension_bridge": ("dimension", "bridge", "variance"),
    "variance.exploded_variance_bridge": ("exploded", "drilldown", "bridge"),
    "variance.root_cause_exploded_bridge": (
        "root_cause",
        "exploded",
        "drilldown",
        "bridge",
    ),
    "variance.root_cause_total_bridge": ("root_cause", "total", "bridge"),
    "variance.root_cause_component_bridge": ("root_cause", "component", "bridge"),
    "variance.price_volume_mix": ("price", "volume", "mix", "pvm"),
    "set_overlap.upset": ("upset", "intersection"),
    "set_overlap.upset_small_multiples": ("upset", "small_multiples", "intersection"),
    "set_overlap.venn": ("venn", "overlap"),
    "funnel.stage_table": ("funnel", "stage"),
    "statement.pnl_table": ("pnl", "statement"),
    "attributes.attribute_bundle_comparison_table": ("attribute", "bundle"),
    "attributes.attribute_bridge_table": ("attribute", "bridge"),
    "attributes.rank_weighted_visibility_table": ("rank", "visibility"),
    "attributes.product_signal_evidence_table": ("product", "signal", "evidence"),
}


def _resolve_sidecar(href: str) -> Path:
    return (GALLERY_DIR / href).resolve()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    return str(value)


def _context_sidecar(artifact: dict[str, Any]) -> Path | None:
    for sidecar in artifact.get("sidecars") or []:
        if sidecar.get("label") == "context":
            return _resolve_sidecar(str(sidecar["href"]))
    return None


def _data_sidecar(artifact: dict[str, Any]) -> Path | None:
    for sidecar in artifact.get("sidecars") or []:
        if sidecar.get("label") == "data":
            return _resolve_sidecar(str(sidecar["href"]))
    return None


def _data_header_text(path: Path | None) -> str:
    if path is None or not path.exists() or path.suffix.lower() != ".csv":
        return ""
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return " ".join(next(csv.reader(handle), []))
    except (OSError, StopIteration, csv.Error):
        return ""


def _minimum_metric_count(metrics: dict[str, Any]) -> int:
    count = metrics.get("minimum_source_metric_count", metrics.get("minimum_count", 0))
    return int(count) if isinstance(count, int | float) else 0


def _artifact_alignment(
    artifact: dict[str, Any],
    capabilities: dict[str, Any],
) -> dict[str, Any]:
    capability_id = artifact["capability_id"]
    capability = capabilities[capability_id]
    context_path = _context_sidecar(artifact)
    data_path = _data_sidecar(artifact)
    context = _load_json(context_path) if context_path else {}
    data_header_text = _data_header_text(data_path).lower()
    context_text = " ".join(
        [
            artifact.get("label", ""),
            artifact.get("output", ""),
            _flatten_text(artifact.get("title_context", {})),
            _flatten_text(artifact.get("context_summary", {})),
            _flatten_text(context),
            data_header_text,
        ]
    ).lower()
    tokens = CAPABILITY_TOKENS.get(capability_id, ())
    token_hits = [token for token in tokens if token.lower() in context_text]

    original_contract = artifact.get("original_artifact_contract") or {}
    source_capability = artifact.get("source_capability_id") or original_contract.get(
        "capability_id"
    )
    source_contract_matches = source_capability == capability_id
    override_documented = "capability_override_reason" in artifact

    explicit_context_capability = (
        context.get("capability_id")
        or context.get("capability")
        or context.get("artifact_contract", {}).get("capability_id")
    )
    explicit_context_matches = explicit_context_capability in (None, capability_id)
    context_summary = artifact.get("context_summary") or {}
    requirements = capability["selection_contract"]["dataset_requirements"]
    requires_metrics = _minimum_metric_count(requirements["metrics"]) > 0
    requires_dimensions = requirements["dimensions"]["minimum_count"] > 0
    requires_period = requirements["period"]["role"] in {"axis", "axis_or_table"}
    has_metric_evidence = bool(context_summary.get("metrics")) or any(
        key in context
        for key in (
            "metric",
            "metrics",
            "x_metric",
            "y_metric",
            "metric_label",
            "statement_label",
            "table_rows",
            "totals",
            "components",
            "levels",
            "panels",
        )
    )
    has_dimension_evidence = (
        bool(context_summary.get("dimensions"))
        or any(
            key in context
            for key in (
                "dimension",
                "dimensions",
                "parent_dimension",
                "child_dimension",
                "dot_dimension",
                "x_dimension",
                "y_dimension",
                "selected_sets",
                "intersections",
                "stage_definitions",
                "statement_rows",
                "selection",
                "panels",
                "components",
            )
        )
        or any(
            token in data_header_text
            for token in (
                "company",
                "brand",
                "channel",
                "product",
                "dimension",
                "bridge_dimensions",
                "stage",
                "line",
                "set",
                "intersection",
            )
        )
    )
    has_period_evidence = bool(context_summary.get("periods")) or any(
        key in context
        for key in (
            "comparison",
            "selected_periods",
            "period_adapter",
            "monthly",
            "periods",
        )
    )
    dimension_roles = requirements["dimensions"]["required_roles"]
    if (
        not has_dimension_evidence
        and any(role in dimension_roles for role in ("scenario_or_period_pair",))
        and has_period_evidence
    ):
        has_dimension_evidence = True
    missing_required_evidence = []
    if requires_metrics and not has_metric_evidence:
        missing_required_evidence.append("metric_evidence")
    if requires_dimensions and not has_dimension_evidence:
        missing_required_evidence.append("dimension_evidence")
    if requires_period and not has_period_evidence:
        missing_required_evidence.append("period_evidence")

    evidence_points = []
    if source_contract_matches:
        evidence_points.append("source_contract_matches_capability")
    if override_documented:
        evidence_points.append("documented_capability_override")
    if explicit_context_capability == capability_id:
        evidence_points.append("context_explicitly_matches_capability")
    if token_hits:
        evidence_points.append("context_or_title_contains_capability_tokens")
    if data_path and data_path.exists():
        evidence_points.append("data_sidecar_exists")
    if context_path and context_path.exists():
        evidence_points.append("context_sidecar_exists")
    if has_metric_evidence:
        evidence_points.append("metric_evidence_present")
    if has_dimension_evidence:
        evidence_points.append("dimension_evidence_present")
    if has_period_evidence:
        evidence_points.append("period_evidence_present")

    if (
        (source_contract_matches or override_documented)
        and context_path
        and context_path.exists()
        and data_path
        and data_path.exists()
        and token_hits
        and not missing_required_evidence
    ):
        status = "strong_artifact_manifest_alignment"
    elif (source_contract_matches or override_documented) and token_hits:
        status = "partial_artifact_manifest_alignment"
    else:
        status = "weak_artifact_manifest_alignment"

    return {
        "label": artifact["label"],
        "capability_id": capability_id,
        "visual_grammar": capability["visual_grammar"],
        "selection_emphasis": capability["selection_emphasis"],
        "status": status,
        "source_capability_id": source_capability,
        "source_contract_matches": source_contract_matches,
        "override_documented": override_documented,
        "explicit_context_capability": explicit_context_capability,
        "explicit_context_matches": explicit_context_matches,
        "token_hits": token_hits,
        "context_path": str(context_path) if context_path else None,
        "data_path": str(data_path) if data_path else None,
        "context_sidecar_exists": bool(context_path and context_path.exists()),
        "data_sidecar_exists": bool(data_path and data_path.exists()),
        "missing_required_evidence": missing_required_evidence,
        "evidence_points": evidence_points,
    }


def audit_chart_artifact_manifest_alignment(
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = [
        _artifact_alignment(artifact, manifest["capabilities"])
        for artifact in manifest["artifacts"]
    ]
    return {
        "artifact_count": len(results),
        "summary": dict(Counter(result["status"] for result in results)),
        "results": sorted(results, key=lambda item: (item["status"], item["label"])),
    }


def _markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Artifact Manifest Alignment Audit",
        "",
        "This checks whether each existing gallery artifact carries sidecar, title,",
        "context, or source-contract evidence that supports its manifest capability.",
        "It is not a substitute for visual inspection; it makes the evidence level explicit.",
        "",
        "## Summary",
        "",
        f"- Artifacts checked: `{audit['artifact_count']}`",
    ]
    for status, count in sorted(audit["summary"].items()):
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(["", "## Results", ""])
    for result in audit["results"]:
        lines.append(
            f"- `{result['label']}` -> `{result['status']}` via "
            f"`{result['capability_id']}` ({result['selection_emphasis']})"
        )
        lines.append(f"  - Visual grammar: `{result['visual_grammar']}`")
        lines.append(
            "  - Source capability: "
            f"`{result['source_capability_id']}`; "
            f"source match: `{result['source_contract_matches']}`; "
            f"override: `{result['override_documented']}`"
        )
        lines.append(
            "  - Sidecars: "
            f"context=`{result['context_sidecar_exists']}`, "
            f"data=`{result['data_sidecar_exists']}`"
        )
        lines.append(
            "  - Token hits: "
            + (
                ", ".join(f"`{token}`" for token in result["token_hits"])
                if result["token_hits"]
                else "`none`"
            )
        )
        lines.append(
            "  - Missing required evidence: "
            + (
                ", ".join(f"`{item}`" for item in result["missing_required_evidence"])
                if result["missing_required_evidence"]
                else "`none`"
            )
        )
        lines.append(
            "  - Evidence: "
            + (
                ", ".join(f"`{point}`" for point in result["evidence_points"])
                if result["evidence_points"]
                else "`none`"
            )
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    audit = audit_chart_artifact_manifest_alignment()
    DEFAULT_OUTPUT.write_text(_markdown(audit), encoding="utf-8")
    print(DEFAULT_OUTPUT)
    print(json.dumps(audit["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
