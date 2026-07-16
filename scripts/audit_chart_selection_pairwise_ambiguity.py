from __future__ import annotations

import argparse
import json
import logging
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

__all__ = ["audit_chart_selection_pairwise_ambiguity", "main"]

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SELECTION_MANIFEST = (
    REPO_ROOT / "runs" / "chart_selection_manifest_rebuild" / "selection_manifest.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "runs"
    / "chart_selection_manifest_rebuild"
    / "pairwise_ambiguity_audit.json"
)
DEFAULT_OUTPUT_MD = DEFAULT_OUTPUT_JSON.with_suffix(".md")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _signature(capability: dict[str, Any]) -> dict[str, Any] | None:
    contract = capability.get("selection_contract")
    if not isinstance(contract, dict):
        return None
    requirements = contract.get("dataset_requirements")
    if not isinstance(requirements, dict):
        return None
    period = requirements.get("period")
    metrics = requirements.get("metrics")
    dimensions = requirements.get("dimensions")
    if not all(isinstance(item, dict) for item in (period, metrics, dimensions)):
        return None

    source_metric_class_groups = []
    for role in metrics.get("source_metric_roles") or []:
        if isinstance(role, dict) and role.get("required", True):
            source_metric_class_groups.append(
                sorted(role.get("accepted_metric_classes") or [])
            )

    role_requirements = dimensions.get("role_requirements") or {}
    dimension_resolution_types = []
    for role in dimensions.get("required_roles") or []:
        role_requirement = role_requirements.get(role) or {}
        dimension_resolution_types.append(
            role_requirement.get("resolution_type", "direct_dimension")
        )

    return {
        "analysis_task_ids": sorted(capability.get("analysis_task_ids") or []),
        "period_role": period.get("role"),
        "source_metric_count": metrics.get("minimum_source_metric_count"),
        "source_metric_class_groups": sorted(source_metric_class_groups),
        "dimension_count": dimensions.get("minimum_count"),
        "dimension_resolution_types": sorted(dimension_resolution_types),
    }


def _decision_cue_signature(capability: dict[str, Any]) -> tuple[tuple[str, ...], ...]:
    return (
        tuple(capability.get("requires_question_focus") or []),
        tuple(capability.get("forbidden_question_focus") or []),
    )


def _decision_cue_summary(capability: dict[str, Any]) -> dict[str, Any]:
    return {
        "primary_decision_cue": capability.get("primary_decision_cue"),
        "requires_question_focus": capability.get("requires_question_focus") or [],
        "forbidden_question_focus": capability.get("forbidden_question_focus") or [],
        "reject_decision_cues": capability.get("reject_decision_cues") or [],
    }


def _has_negative_example_for(
    capability: dict[str, Any], *, better_capability_id: str
) -> bool:
    examples = capability.get("selection_examples") or {}
    return any(
        isinstance(example, dict)
        and example.get("better_capability_id") == better_capability_id
        for example in examples.get("negative_questions") or []
    )


def _has_ambiguous_example_pair(
    capability: dict[str, Any], *, left_id: str, right_id: str
) -> bool:
    examples = capability.get("selection_examples") or {}
    for example in examples.get("ambiguous_questions") or []:
        if not isinstance(example, dict):
            continue
        candidates = set(example.get("candidate_capability_ids") or [])
        if {left_id, right_id}.issubset(candidates):
            return True
    return False


def _relationship_evidence(
    *,
    left_id: str,
    right_id: str,
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, bool]:
    left_competitors = set(left.get("competing_capability_ids") or [])
    right_competitors = set(right.get("competing_capability_ids") or [])
    return {
        "explicit_competitor_link": (
            right_id in left_competitors or left_id in right_competitors
        ),
        "negative_example_link": (
            _has_negative_example_for(left, better_capability_id=right_id)
            or _has_negative_example_for(right, better_capability_id=left_id)
        ),
        "ambiguous_example_link": (
            _has_ambiguous_example_pair(left, left_id=left_id, right_id=right_id)
            or _has_ambiguous_example_pair(right, left_id=left_id, right_id=right_id)
        ),
    }


def _issue(code: str, severity: str, detail: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "detail": detail}


def _pair_issues(
    *,
    left_id: str,
    right_id: str,
    left: dict[str, Any],
    right: dict[str, Any],
    relationship: dict[str, bool],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if left.get("selection_emphasis") == right.get("selection_emphasis"):
        issues.append(
            _issue(
                "same_selection_emphasis",
                "error",
                "high-overlap pair uses the same selection_emphasis",
            )
        )
    if left.get("primary_decision_cue") == right.get("primary_decision_cue"):
        issues.append(
            _issue(
                "same_primary_decision_cue",
                "error",
                "high-overlap pair uses the same primary_decision_cue",
            )
        )
    if _decision_cue_signature(left) == _decision_cue_signature(right):
        issues.append(
            _issue(
                "same_structured_decision_cues",
                "error",
                "high-overlap pair has identical required and forbidden focus cues",
            )
        )
    if not relationship["explicit_competitor_link"]:
        issues.append(
            _issue(
                "missing_explicit_competitor_link",
                "error",
                "high-overlap pair is not linked through competing_capability_ids",
            )
        )
    if not relationship["ambiguous_example_link"]:
        issues.append(
            _issue(
                "missing_ambiguous_example_link",
                "error",
                "high-overlap pair is not preserved in an ambiguous example",
            )
        )
    if not relationship["negative_example_link"]:
        issues.append(
            _issue(
                "missing_negative_example_link",
                "warning",
                "high-overlap pair has no negative example pointing to the other chart",
            )
        )
    if not left.get("primary_decision_cue") or not right.get("primary_decision_cue"):
        issues.append(
            _issue(
                "missing_primary_decision_cue",
                "error",
                "both charts in a high-overlap pair need primary_decision_cue text",
            )
        )
    return issues


def _signature_groups(
    capabilities: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    groups: defaultdict[str, list[str]] = defaultdict(list)
    signatures_by_key: dict[str, dict[str, Any]] = {}
    missing_contract: list[str] = []
    for capability_id, capability in sorted(capabilities.items()):
        if not isinstance(capability, dict):
            missing_contract.append(capability_id)
            continue
        signature = _signature(capability)
        if signature is None:
            missing_contract.append(capability_id)
            continue
        signature_key = json.dumps(signature, sort_keys=True)
        groups[signature_key].append(capability_id)
        signatures_by_key[signature_key] = signature

    grouped = [
        {
            "signature": signatures_by_key[signature_key],
            "capability_ids": sorted(capability_ids),
            "pair_count": len(capability_ids) * (len(capability_ids) - 1) // 2,
        }
        for signature_key, capability_ids in sorted(groups.items())
        if len(capability_ids) > 1
    ]
    return grouped, sorted(missing_contract)


def _pair_records(
    *,
    capabilities: dict[str, Any],
    signature_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for group in signature_groups:
        for left_id, right_id in combinations(group["capability_ids"], 2):
            left = capabilities[left_id]
            right = capabilities[right_id]
            relationship = _relationship_evidence(
                left_id=left_id,
                right_id=right_id,
                left=left,
                right=right,
            )
            issues = _pair_issues(
                left_id=left_id,
                right_id=right_id,
                left=left,
                right=right,
                relationship=relationship,
            )
            error_count = sum(1 for issue in issues if issue["severity"] == "error")
            warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
            records.append(
                {
                    "capability_ids": [left_id, right_id],
                    "status": "resolved" if error_count == 0 else "unresolved",
                    "error_count": error_count,
                    "warning_count": warning_count,
                    "issues": issues,
                    "signature": group["signature"],
                    "selection_emphases": {
                        left_id: left.get("selection_emphasis"),
                        right_id: right.get("selection_emphasis"),
                    },
                    "structured_decision_cues": {
                        left_id: _decision_cue_summary(left),
                        right_id: _decision_cue_summary(right),
                    },
                    "relationship_evidence": relationship,
                }
            )
    return records


def audit_chart_selection_pairwise_ambiguity(
    *,
    selection_manifest_path: Path = DEFAULT_SELECTION_MANIFEST,
    output_json_path: Path = DEFAULT_OUTPUT_JSON,
    output_md_path: Path = DEFAULT_OUTPUT_MD,
) -> dict[str, Any]:
    manifest = _load_json(selection_manifest_path)
    capabilities = manifest.get("capabilities") or {}
    if not isinstance(capabilities, dict):
        raise ValueError("selection manifest capabilities must be an object")

    # This audit is deterministic because it checks an explicit manifest
    # contract: mechanically similar charts must expose distinct tie-breakers.
    # It does not choose the semantically best chart for a user question.
    signature_groups, missing_contract = _signature_groups(capabilities)
    pairs = _pair_records(capabilities=capabilities, signature_groups=signature_groups)
    issue_counts = Counter(
        issue["code"] for pair in pairs for issue in pair.get("issues") or []
    )
    severity_counts = Counter(
        issue["severity"] for pair in pairs for issue in pair.get("issues") or []
    )
    relationship_counts = Counter(
        key
        for pair in pairs
        for key, value in pair["relationship_evidence"].items()
        if value
    )
    missing_contract_issues = [
        _issue(
            "missing_selection_contract",
            "error",
            "capability is missing a usable selection_contract",
        )
        for _ in missing_contract
    ]
    payload = {
        "purpose": (
            "Audit whether mechanically similar chart capabilities expose "
            "explicit selector tie-breakers through selection emphasis, focus "
            "cues, competitor links, and pairwise examples."
        ),
        "inputs": {"selection_manifest": str(selection_manifest_path)},
        "counts": {
            "capabilities": len(capabilities),
            "signature_groups": len(signature_groups),
            "high_overlap_pairs": len(pairs),
            "resolved_pairs": sum(1 for pair in pairs if pair["status"] == "resolved"),
            "unresolved_pairs": sum(
                1 for pair in pairs if pair["status"] == "unresolved"
            ),
            "missing_selection_contract": len(missing_contract),
            "errors": severity_counts["error"] + len(missing_contract_issues),
            "warnings": severity_counts["warning"],
        },
        "issue_counts": dict(sorted(issue_counts.items())),
        "relationship_evidence_counts": dict(sorted(relationship_counts.items())),
        "missing_selection_contract_capability_ids": missing_contract,
        "signature_groups": signature_groups,
        "high_overlap_pairs": pairs,
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
        "# Chart Selection Pairwise Ambiguity Audit",
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
    missing_contract = payload.get("missing_selection_contract_capability_ids") or []
    if not issue_counts and not missing_contract:
        lines.append("- None")
    else:
        for key, value in issue_counts.items():
            lines.append(f"- `{key}`: `{value}`")
        if missing_contract:
            lines.append(f"- `missing_selection_contract`: `{len(missing_contract)}`")

    lines.extend(["", "## Relationship Evidence", ""])
    relationship_counts = payload.get("relationship_evidence_counts") or {}
    if not relationship_counts:
        lines.append("- None")
    else:
        for key, value in relationship_counts.items():
            lines.append(f"- `{key}`: `{value}`")

    lines.extend(["", "## Signature Groups", ""])
    for group in payload.get("signature_groups") or []:
        capability_ids = ", ".join(f"`{item}`" for item in group["capability_ids"])
        lines.append(f"- {capability_ids}")
        lines.append(f"  - pairs: `{group['pair_count']}`")
        lines.append(
            f"  - signature: `{json.dumps(group['signature'], sort_keys=True)}`"
        )

    lines.extend(["", "## High-Overlap Pairs", ""])
    for pair in payload.get("high_overlap_pairs") or []:
        left_id, right_id = pair["capability_ids"]
        lines.append(
            f"- `{left_id}` <> `{right_id}`: `{pair['status']}` "
            f"(`{pair['error_count']}` errors, `{pair['warning_count']}` warnings)"
        )
        for issue in pair.get("issues") or []:
            lines.append(
                "  - " f"`{issue['severity']}` `{issue['code']}`: {issue['detail']}"
            )
    lines.append("")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit pairwise chart-selection ambiguity in the manifest."
    )
    parser.add_argument(
        "--selection-manifest",
        type=Path,
        default=DEFAULT_SELECTION_MANIFEST,
        help="Path to selection_manifest.json.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=DEFAULT_OUTPUT_JSON,
        help="Path for JSON audit output.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=DEFAULT_OUTPUT_MD,
        help="Path for Markdown audit output.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    payload = audit_chart_selection_pairwise_ambiguity(
        selection_manifest_path=args.selection_manifest,
        output_json_path=args.output_json,
        output_md_path=args.output_md,
    )
    counts = payload["counts"]
    logging.info(
        "Wrote pairwise ambiguity audit to %s and %s",
        args.output_json,
        args.output_md,
    )
    logging.info(
        "Checked %s high-overlap pairs: %s unresolved, %s errors, %s warnings",
        counts["high_overlap_pairs"],
        counts["unresolved_pairs"],
        counts["errors"],
        counts["warnings"],
    )
    return 0 if counts["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
