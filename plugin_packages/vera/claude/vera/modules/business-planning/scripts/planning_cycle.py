"""Preserve planning revisions and mechanically detect unexamined carry-over.

Snapshot identity and exact input differences are reproducible. Whether the new
evidence changes a business decision is deliberately left to the model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from planning_workflow import digest, indexed, require, reviewed

__all__ = ["review_cycle", "narrative_groups"]


def narrative_groups(
    groups: dict[str, Any], case: dict[str, Any], available: set[str], prefix: str
) -> list[str]:
    """Check declared narrative references without interpreting the prose."""
    all_ids = set(indexed(case["narrative"], "narrative"))
    issues = []
    for name, ids in groups.items():
        require(
            isinstance(ids, list)
            and all(isinstance(i, str) for i in ids)
            and len(ids) == len(set(ids))
            and set(ids) <= all_ids,
            f"Invalid {prefix} narrative references: {name}",
        )
        if not ids or not set(ids) <= available:
            issues.append(f"{prefix} {name} is incomplete or contains a withheld claim")
    return issues


def _changes(previous: dict[str, Any], case: dict[str, Any]) -> list[dict[str, Any]]:
    """Compare authored business inputs, excluding review metadata and prose."""
    changes = []
    for field in (
        "entity_name",
        "company_stage",
        "planning_objective",
        "reporting_currency",
        "periods",
        "sources",
        "evidence",
        "assumptions",
        "decisions",
        "observations",
        "resolutions",
        "financial",
        "commercial",
        "financing",
    ):
        before, after = previous.get(field), case.get(field)
        if field == "sources":
            before = [s for s in before if s["role"] != "prior_plan"]
            after = [s for s in after if s["role"] != "prior_plan"]
        if before != after:
            changes.append({"field": field, "before": before, "after": after})
    return changes


def review_cycle(
    case: dict[str, Any], source_root: Path, narrative: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, list[str], set[str]]:
    """Load a registered parent snapshot and withhold unreconsidered conclusions."""
    cycle = case.get("cycle")
    if cycle is None:
        return (
            None,
            ["Planning cycle missing: record the question and next test"],
            set(),
        )
    require(
        set(cycle)
        == {
            "id",
            "parent_source_id",
            "question",
            "trigger_ids",
            "analysis_ids",
            "decision_ids",
            "next_test_ids",
            "reopen_when_ids",
            "reassessed_ids",
        },
        "Unexpected planning cycle fields",
    )
    for field in ("id", "question"):
        require(
            isinstance(cycle[field], str) and bool(cycle[field].strip()),
            f"Planning cycle {field} required",
        )
    available = {n["id"] for n in narrative}
    groups = {
        k: cycle[k]
        for k in ("analysis_ids", "decision_ids", "next_test_ids", "reopen_when_ids")
    }
    issues = narrative_groups(groups, case, available, "Planning cycle")
    refs = set(indexed([*case["evidence"], *case["assumptions"]], "basis"))
    require(
        isinstance(cycle["trigger_ids"], list)
        and all(isinstance(i, str) for i in cycle["trigger_ids"])
        and set(cycle["trigger_ids"]) <= refs,
        "Unknown cycle evidence",
    )
    require(bool(cycle["trigger_ids"]), "Cycle needs evidence or a labelled hypothesis")
    reassessed = cycle["reassessed_ids"]
    require(
        isinstance(reassessed, list)
        and all(isinstance(i, str) for i in reassessed)
        and len(reassessed) == len(set(reassessed))
        and set(reassessed) <= set(indexed(case["narrative"], "narrative")),
        "Invalid reconsidered narrative IDs",
    )
    parent_id = cycle["parent_source_id"]
    prior_sources = {s["id"]: s for s in case["sources"] if s["role"] == "prior_plan"}
    require(
        set(prior_sources) == ({parent_id} if parent_id is not None else set()),
        "Register exactly the selected prior plan for this cycle",
    )
    changes: list[dict[str, Any]] = []
    stale: set[str] = set()
    history = []
    parent_hash = None
    if parent_id is not None:
        source = prior_sources[parent_id]
        previous = json.loads(
            (source_root / source["path"]).read_text(encoding="utf-8")
        )
        require(
            isinstance(previous, dict)
            and previous.get("schema_version") == "mparanza.business_planning_plan.v3",
            "Parent must be a shared business plan snapshot",
        )
        require(
            previous.get("content_sha256")
            == digest({k: v for k, v in previous.items() if k != "content_sha256"}),
            "Prior plan snapshot hash mismatch",
        )
        previous_case = previous["case"]
        require(
            previous.get("case_sha256") == digest(previous_case),
            "Prior case snapshot hash mismatch",
        )
        require(
            previous_case["case_id"] == case["case_id"],
            "Prior plan belongs to another case",
        )
        # A renamed parent file cannot launder its embedded source restrictions.
        from copy import deepcopy

        from planning_report import _check_audience

        parent_permissions = deepcopy(previous_case)
        parent_permissions["audience"] = case["audience"]
        parent_permissions["decisions"].extend(case["decisions"])
        _check_audience(parent_permissions)
        parent_hash = previous["content_sha256"]
        prior_cycle = previous.get("planning_cycle")
        if prior_cycle:
            history = [
                *prior_cycle["history"],
                {
                    "id": previous_case["cycle"]["id"],
                    "question": previous_case["cycle"]["question"],
                    "content_sha256": parent_hash,
                },
            ]
        require(
            cycle["id"] not in {h["id"] for h in history},
            "Cycle ID already exists in this history",
        )
        changes = _changes(previous_case, case)
        if changes:
            if case["review"] == previous_case["review"] and reviewed(case["review"]):
                issues.append(
                    "Changed planning basis requires renewed professional review"
                )
                for entry in narrative:
                    entry["provisional"] = True
            prior_ids = set(indexed(previous_case["narrative"], "prior narrative"))
            stale = prior_ids & set(indexed(case["narrative"], "narrative")) - set(
                reassessed
            )
            if stale:
                issues.append(
                    "Changed planning basis requires reconsideration: "
                    + ", ".join(sorted(stale))
                )
    return (
        {
            "parent_content_sha256": parent_hash,
            "history": history,
            "changes": changes,
            "withheld_narrative_ids": sorted(stale),
        },
        issues,
        stale,
    )
