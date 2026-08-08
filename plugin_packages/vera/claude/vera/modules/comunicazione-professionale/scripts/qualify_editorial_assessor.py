#!/usr/bin/env python3
"""Qualify one model-led editorial assessor on the bundled anti-slop corpus."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from workflow_core import (
    EDITORIAL_CASES_PATH,
    EDITORIAL_EXPECTED_PATH,
    atomic_write_json,
    canonical_digest,
    load_json,
    load_workspace,
    utc_now,
    validate_schema,
    workflow_lock,
)

__all__ = ["qualify_editorial_assessor", "main"]

LOGGER = logging.getLogger(__name__)


def qualify_editorial_assessor(
    workspace: Path,
    results_path: Path,
    *,
    recorded_by: str,
) -> Path:
    """Score semantic model judgments against fixed product-reviewed outcomes."""

    root = workspace.expanduser().resolve()
    load_workspace(root)
    results = load_json(results_path)
    validate_schema(results, "editorial_benchmark_results.schema.json")
    corpus = load_json(EDITORIAL_CASES_PATH)
    cases = corpus["cases"]
    expectations = load_json(EDITORIAL_EXPECTED_PATH)
    expected_by_id = {row["case_id"]: row for row in expectations["expectations"]}
    case_ids = {row["case_id"] for row in cases}
    if set(expected_by_id) != case_ids:
        raise ValueError("Editorial benchmark corpus and rubric are inconsistent")
    judgments = results["judgments"]
    judgment_ids = [row["case_id"] for row in judgments]
    if len(judgment_ids) != len(set(judgment_ids)):
        raise ValueError("Editorial benchmark repeats a case")
    if set(judgment_ids) != set(expected_by_id):
        raise ValueError("Editorial benchmark must assess every current case exactly")
    correct = 0
    false_ready: list[str] = []
    critical_failures: list[str] = []
    scored: list[dict[str, Any]] = []
    for judgment in judgments:
        case = expected_by_id[judgment["case_id"]]
        matched = judgment["verdict"] == case["expected_verdict"]
        correct += int(matched)
        if judgment["verdict"] == "ready" and case["expected_verdict"] != "ready":
            false_ready.append(case["case_id"])
        if case["critical"] and not matched:
            critical_failures.append(case["case_id"])
        scored.append(
            {
                "case_id": case["case_id"],
                "critical": case["critical"],
                "expected_verdict": case["expected_verdict"],
                "recorded_verdict": judgment["verdict"],
                "matched": matched,
            }
        )
    total = len(cases)
    accuracy = correct / total
    qualified = accuracy >= 0.83 and not false_ready and not critical_failures
    metrics = {
        "case_count": total,
        "correct_count": correct,
        "accuracy": round(accuracy, 6),
        "false_ready_count": len(false_ready),
        "false_ready_case_ids": false_ready,
        "critical_cases_passed": not critical_failures,
        "critical_failure_case_ids": critical_failures,
    }
    record: dict[str, Any] = {
        "schema_version": 1,
        "workflow": "comunicazione-professionale",
        "status": "qualified" if qualified else "not_qualified",
        "qualified_at": utc_now(),
        "recorded_by": recorded_by,
        "assessor_identity": {
            "provider": results["provider"],
            "model": results["model"],
            "assessment_template_version": results["assessment_template_version"],
            "assessor_session_id": results["assessor_session_id"],
        },
        "cases_digest": canonical_digest(corpus),
        "expected_digest": canonical_digest(expectations),
        "results_digest": canonical_digest(results),
        "metrics": metrics,
        "scored_cases": scored,
    }
    record["qualification_digest"] = canonical_digest(record)
    with workflow_lock(root):
        archive = (
            root
            / "editorial-qualifications"
            / (f"qualification-{record['qualification_digest'][:16]}.json")
        )
        atomic_write_json(archive, record)
        output = atomic_write_json(
            root / "editorial_assessor_qualification.json", record
        )
    if not qualified:
        raise ValueError(
            "Editorial assessor did not qualify: "
            f"accuracy={accuracy:.3f}, false_ready={false_ready}, critical={critical_failures}"
        )
    return output


def main(argv: list[str] | None = None) -> int:
    """Qualify one exact editorial assessor configuration."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--recorded-by", required=True)
    args = parser.parse_args(argv)
    try:
        output = qualify_editorial_assessor(
            args.workspace,
            args.results,
            recorded_by=args.recorded_by,
        )
    except (OSError, ValueError, KeyError) as exc:
        LOGGER.error("EDITORIAL_ASSESSOR_QUALIFICATION_FAILED: %s", exc)
        return 1
    LOGGER.info("Qualified editorial assessor: %s", output)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
