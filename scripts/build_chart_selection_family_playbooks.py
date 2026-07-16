from __future__ import annotations

import argparse
import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

__all__ = ["build_chart_selection_family_playbooks", "main"]

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SELECTION_MANIFEST = (
    REPO_ROOT / "runs" / "chart_selection_manifest_rebuild" / "selection_manifest.json"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "runs"
    / "chart_selection_manifest_rebuild"
    / "family_selector_playbooks"
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return slug or "unknown"


def _inline_list(values: list[Any] | tuple[Any, ...] | None) -> str:
    if not values:
        return "`none`"
    return ", ".join(f"`{value}`" for value in values)


def _text(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else "Not specified."


def _metric_role_summary(capability: dict[str, Any]) -> str:
    requirements = (
        (capability.get("selection_contract") or {})
        .get("dataset_requirements", {})
        .get("metrics", {})
    )
    roles = [
        role.get("role")
        for role in requirements.get("source_metric_roles") or []
        if isinstance(role, dict) and role.get("required", True)
    ]
    if not roles:
        roles = capability.get("display_metric_roles") or []
    return _inline_list(roles)


def _dimension_role_summary(capability: dict[str, Any]) -> str:
    requirements = (
        (capability.get("selection_contract") or {})
        .get("dataset_requirements", {})
        .get("dimensions", {})
    )
    required_roles = requirements.get("required_roles") or []
    optional_roles = requirements.get("optional_roles") or []
    if required_roles or optional_roles:
        parts = []
        if required_roles:
            parts.append("required " + _inline_list(required_roles))
        if optional_roles:
            parts.append("optional " + _inline_list(optional_roles))
        return "; ".join(parts)
    return _inline_list(capability.get("dimension_roles") or [])


def _period_role(capability: dict[str, Any]) -> str:
    requirements = (
        (capability.get("selection_contract") or {})
        .get("dataset_requirements", {})
        .get("period", {})
    )
    return str(
        requirements.get("role")
        or (capability.get("period_semantics") or {}).get("role")
        or "none"
    )


def _positive_question(capability: dict[str, Any]) -> str:
    questions = (capability.get("selection_examples") or {}).get(
        "positive_questions"
    ) or []
    return str(questions[0]) if questions else "Not specified."


def _ambiguous_example(capability: dict[str, Any]) -> dict[str, Any] | None:
    examples = (capability.get("selection_examples") or {}).get(
        "ambiguous_questions"
    ) or []
    for example in examples:
        if isinstance(example, dict):
            return example
    return None


def _pairwise_competitors(manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    pairs_by_capability: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    pairwise = (
        (manifest.get("selector_audit") or {}).get("pairwise_ambiguity") or {}
    ).get("high_overlap_pairs") or []
    for pair in pairwise:
        if not isinstance(pair, dict):
            continue
        capability_ids = pair.get("capability_ids") or []
        if len(capability_ids) != 2:
            continue
        left_id, right_id = capability_ids
        pairs_by_capability[left_id].append(pair)
        pairs_by_capability[right_id].append(pair)
    return {
        capability_id: sorted(pairs, key=lambda item: tuple(item["capability_ids"]))
        for capability_id, pairs in pairs_by_capability.items()
    }


def _family_groups(capabilities: dict[str, Any]) -> dict[str, list[tuple[str, dict]]]:
    families: defaultdict[str, list[tuple[str, dict]]] = defaultdict(list)
    for capability_id, capability in sorted(capabilities.items()):
        if isinstance(capability, dict):
            families[str(capability.get("family") or "unknown")].append(
                (capability_id, capability)
            )
    return dict(sorted(families.items()))


def _capability_table(family_items: list[tuple[str, dict]]) -> list[str]:
    lines = [
        "| Capability | Selection emphasis | Period | Metrics | Dimensions | Primary cue |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for capability_id, capability in family_items:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{capability_id}`",
                    f"`{capability.get('selection_emphasis')}`",
                    f"`{_period_role(capability)}`",
                    _metric_role_summary(capability),
                    _dimension_role_summary(capability),
                    _text(capability.get("primary_decision_cue")).replace("|", "/"),
                ]
            )
            + " |"
        )
    return lines


def _capability_detail(
    *,
    capability_id: str,
    capability: dict[str, Any],
    pairwise_by_capability: dict[str, list[dict[str, Any]]],
) -> list[str]:
    lines = [
        f"### `{capability_id}`",
        "",
        f"- Selection emphasis: `{capability.get('selection_emphasis')}`",
        f"- Visual grammar: `{capability.get('visual_grammar')}`",
        f"- Analysis tasks: {_inline_list(capability.get('analysis_task_ids') or [])}",
        f"- Best when: {_text(capability.get('best_when'))}",
        f"- Avoid when: {_text(capability.get('avoid_when'))}",
        f"- Primary decision cue: {_text(capability.get('primary_decision_cue'))}",
        f"- Requires question focus: {_inline_list(capability.get('requires_question_focus') or [])}",
        f"- Reject decision cues: {_inline_list(capability.get('reject_decision_cues') or [])}",
        f"- Forbidden question focus: {_inline_list(capability.get('forbidden_question_focus') or [])}",
        f"- Period role: `{_period_role(capability)}`",
        f"- Metric roles: {_metric_role_summary(capability)}",
        f"- Dimension roles: {_dimension_role_summary(capability)}",
        f"- Close competitors: {_inline_list(capability.get('competing_capability_ids') or [])}",
        f"- Positive question: {_positive_question(capability)}",
    ]

    ambiguous = _ambiguous_example(capability)
    if ambiguous is not None:
        lines.extend(
            [
                "- Ambiguous question: " + _text(ambiguous.get("question")),
                "- Ambiguous candidates: "
                + _inline_list(ambiguous.get("candidate_capability_ids") or []),
                "- Disambiguation: " + _text(ambiguous.get("disambiguation_needed")),
            ]
        )

    pairwise = pairwise_by_capability.get(capability_id) or []
    if pairwise:
        lines.append("- High-overlap pair evidence:")
        for pair in pairwise:
            other_id = next(
                item for item in pair["capability_ids"] if item != capability_id
            )
            relationship = pair.get("relationship_evidence") or {}
            evidence = [
                key
                for key in (
                    "explicit_competitor_link",
                    "ambiguous_example_link",
                    "negative_example_link",
                )
                if relationship.get(key)
            ]
            lines.append(
                f"  - `{other_id}`: `{pair.get('status')}`; evidence "
                + _inline_list(evidence)
            )
    lines.append("")
    return lines


def _family_markdown(
    *,
    family: str,
    family_items: list[tuple[str, dict]],
    manifest: dict[str, Any],
    pairwise_by_capability: dict[str, list[dict[str, Any]]],
) -> str:
    lines = [
        f"# Chart Selection Playbook: {family}",
        "",
        "Generated from `selection_manifest.json`. This is a manifest-side review "
        "document: it explains chart capability differences, not dataset-specific "
        "semantic validity.",
        "",
        "## How To Use This Family",
        "",
        "1. Start from the question focus and match it to `requires_question_focus`.",
        "2. Reject charts whose `forbidden_question_focus` or reject cues match the question.",
        "3. Check that the dataset profile can provide the required period, metric, and dimension roles.",
        "4. If multiple charts remain, inspect the close competitors and high-overlap pair evidence.",
        "",
        "## Capability Summary",
        "",
        *_capability_table(family_items),
        "",
        "## High-Overlap Pairs",
        "",
    ]
    pairwise = (
        (manifest.get("selector_audit") or {}).get("pairwise_ambiguity") or {}
    ).get("high_overlap_pairs") or []
    family_capability_ids = {capability_id for capability_id, _ in family_items}
    family_pairs = [
        pair
        for pair in pairwise
        if set(pair.get("capability_ids") or []).issubset(family_capability_ids)
    ]
    if not family_pairs:
        lines.append("- None")
    else:
        for pair in family_pairs:
            left_id, right_id = pair["capability_ids"]
            lines.append(
                f"- `{left_id}` <> `{right_id}`: `{pair.get('status')}` "
                f"(`{pair.get('error_count', 0)}` errors, "
                f"`{pair.get('warning_count', 0)}` warnings)"
            )
    lines.extend(["", "## Capability Details", ""])
    for capability_id, capability in family_items:
        lines.extend(
            _capability_detail(
                capability_id=capability_id,
                capability=capability,
                pairwise_by_capability=pairwise_by_capability,
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def _index_markdown(records: list[dict[str, Any]]) -> str:
    lines = [
        "# Chart Selection Family Playbooks",
        "",
        "Generated from `selection_manifest.json`. These files are a human review "
        "surface for the manifest-side selector contract.",
        "",
        "| Family | Capabilities | High-overlap pairs | File |",
        "| --- | ---: | ---: | --- |",
    ]
    for record in records:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{record['family']}`",
                    str(record["capability_count"]),
                    str(record["high_overlap_pair_count"]),
                    f"[{record['filename']}]({record['filename']})",
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def build_chart_selection_family_playbooks(
    *,
    selection_manifest_path: Path = DEFAULT_SELECTION_MANIFEST,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    manifest = _load_json(selection_manifest_path)
    capabilities = manifest.get("capabilities") or {}
    if not isinstance(capabilities, dict):
        raise ValueError("selection manifest capabilities must be an object")

    families = _family_groups(capabilities)
    pairwise_by_capability = _pairwise_competitors(manifest)
    pairwise = (
        (manifest.get("selector_audit") or {}).get("pairwise_ambiguity") or {}
    ).get("high_overlap_pairs") or []

    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for family, family_items in families.items():
        filename = f"{_slug(family)}.md"
        path = output_dir / filename
        family_capability_ids = {capability_id for capability_id, _ in family_items}
        high_overlap_pair_count = sum(
            1
            for pair in pairwise
            if set(pair.get("capability_ids") or []).issubset(family_capability_ids)
        )
        path.write_text(
            _family_markdown(
                family=family,
                family_items=family_items,
                manifest=manifest,
                pairwise_by_capability=pairwise_by_capability,
            ),
            encoding="utf-8",
        )
        records.append(
            {
                "family": family,
                "filename": filename,
                "path": str(path),
                "capability_count": len(family_items),
                "high_overlap_pair_count": high_overlap_pair_count,
            }
        )

    index_path = output_dir / "index.md"
    index_path.write_text(_index_markdown(records), encoding="utf-8")
    return {
        "inputs": {"selection_manifest": str(selection_manifest_path)},
        "output_dir": str(output_dir),
        "index_path": str(index_path),
        "family_count": len(records),
        "capability_count": len(capabilities),
        "families": records,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build per-family chart selector playbooks from the manifest."
    )
    parser.add_argument(
        "--selection-manifest",
        type=Path,
        default=DEFAULT_SELECTION_MANIFEST,
        help="Path to selection_manifest.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated family playbook Markdown files.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    payload = build_chart_selection_family_playbooks(
        selection_manifest_path=args.selection_manifest,
        output_dir=args.output_dir,
    )
    logging.info(
        "Wrote %s family selector playbooks to %s",
        payload["family_count"],
        args.output_dir,
    )
    logging.info("Index: %s", payload["index_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
