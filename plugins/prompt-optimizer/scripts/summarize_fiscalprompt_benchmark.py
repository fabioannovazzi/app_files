#!/usr/bin/env python3
"""Validate blinded reviews and summarize the FiscalPrompt benchmark."""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from run_fiscalprompt_benchmark import (
    REVIEW_SCHEMA,
    RUNS_SCHEMA,
    TREATMENTS,
    _canonical_sha256,
    _mapping,
    _sequence,
    _text,
    _write_json,
    validate_suite,
)

__all__ = ["summarize_benchmark", "validate_review"]

LOGGER = logging.getLogger(__name__)
SUMMARY_SCHEMA = "prompt_optimizer.fiscalprompt_benchmark_summary.v1"


def _score(value: Any, *, label: str) -> int:
    if type(value) is not int or not 1 <= value <= 5:
        raise ValueError(f"{label} must be an integer from 1 to 5")
    return value


def _weights(suite: Mapping[str, Any], artifact_kind: str) -> dict[str, float]:
    rubric = _mapping(suite["rubric"], label="rubric")
    dimensions = _sequence(
        rubric[f"{artifact_kind}_dimensions"], label=f"{artifact_kind}_dimensions"
    )
    return {
        _text(item["id"], label="dimension.id"): float(item["weight"])
        for item in (_mapping(raw, label="dimension") for raw in dimensions)
    }


def validate_review(
    review: Mapping[str, Any],
    *,
    suite: Mapping[str, Any],
    packet_mapping: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate score shape and evidence bindings, not the tax judgment itself."""

    validated = validate_suite(suite)
    if review.get("schema_version") != REVIEW_SCHEMA:
        raise ValueError("unsupported FiscalPrompt benchmark review schema")
    packet_id = _text(review.get("packet_id"), label="review.packet_id")
    if packet_id != packet_mapping.get("packet_id"):
        raise ValueError("review packet ID does not match private mapping")
    reviewer = _mapping(review.get("reviewer"), label="review.reviewer")
    reviewer_type = _text(reviewer.get("type"), label="reviewer.type")
    if reviewer_type not in validated["required_reviewer_types"]:
        raise ValueError(f"unsupported reviewer type: {reviewer_type}")
    reviewer_id = _text(reviewer.get("id"), label="reviewer.id")
    thread_id = _text(reviewer.get("thread_id"), label="reviewer.thread_id")
    builder_threads = set(
        str(value)
        for value in _mapping(
            packet_mapping.get("builder_thread_ids"), label="builder_thread_ids"
        ).values()
        if value
    )
    if thread_id in builder_threads:
        raise ValueError("reviewer thread must differ from both builder threads")
    if reviewer_type == "model":
        _text(reviewer.get("model"), label="reviewer.model")

    expected_hashes = _mapping(packet_mapping.get("artifacts"), label="artifacts")
    observed_hashes = _mapping(review.get("artifact_hashes"), label="artifact_hashes")
    if dict(observed_hashes) != dict(expected_hashes):
        raise ValueError("review artifact hashes do not match the blinded packet")

    raw_scores = _mapping(review.get("scores"), label="scores")
    normalized_scores: dict[str, dict[str, dict[str, int]]] = {}
    for label in ("A", "B"):
        label_scores = _mapping(raw_scores.get(label), label=f"scores.{label}")
        normalized_scores[label] = {}
        for artifact_kind in ("prompt", "answer"):
            artifact_scores = _mapping(
                label_scores.get(artifact_kind),
                label=f"scores.{label}.{artifact_kind}",
            )
            expected_dimensions = set(validated["rubric_dimensions"][artifact_kind])
            if set(artifact_scores) != expected_dimensions:
                raise ValueError(
                    f"scores.{label}.{artifact_kind} dimensions do not match suite"
                )
            normalized_scores[label][artifact_kind] = {
                dimension: _score(
                    artifact_scores[dimension],
                    label=f"scores.{label}.{artifact_kind}.{dimension}",
                )
                for dimension in sorted(expected_dimensions)
            }

    rubric = _mapping(suite["rubric"], label="rubric")
    allowed_failures = set(
        _text(value, label="hard_failures[]")
        for value in _sequence(rubric.get("hard_failures"), label="hard_failures")
    )
    raw_failures = _mapping(review.get("hard_failures"), label="hard_failures")
    failures: dict[str, list[str]] = {}
    for label in ("A", "B"):
        failures[label] = [
            _text(value, label=f"hard_failures.{label}[]")
            for value in _sequence(
                raw_failures.get(label), label=f"hard_failures.{label}"
            )
        ]
        unknown = set(failures[label]) - allowed_failures
        if unknown:
            raise ValueError(f"unknown hard failures: {sorted(unknown)}")

    winners = _mapping(review.get("pairwise_winner"), label="pairwise_winner")
    normalized_winners: dict[str, str] = {}
    for artifact_kind in ("prompt", "answer"):
        winner = _text(winners.get(artifact_kind), label=f"winner.{artifact_kind}")
        if winner not in {"A", "B", "tie"}:
            raise ValueError("pairwise winner must be A, B, or tie")
        normalized_winners[artifact_kind] = winner
    rationale = _mapping(review.get("rationale"), label="rationale")
    for field in ("A", "B", "comparison"):
        _text(rationale.get(field), label=f"rationale.{field}")
    return {
        "packet_id": packet_id,
        "reviewer_type": reviewer_type,
        "reviewer_id": reviewer_id,
        "thread_id": thread_id,
        "scores": normalized_scores,
        "hard_failures": failures,
        "pairwise_winner": normalized_winners,
    }


def _weighted_score(scores: Mapping[str, int], weights: Mapping[str, float]) -> float:
    return sum(
        float(scores[dimension]) * weight for dimension, weight in weights.items()
    )


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot calculate percentile of empty values")
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _bootstrap_ci(values: Sequence[float], *, seed: int = 0) -> list[float]:
    if not values:
        return []
    generator = random.Random(seed)
    sample_size = len(values)
    means = [
        sum(generator.choice(values) for _ in range(sample_size)) / sample_size
        for _ in range(5000)
    ]
    return [round(_percentile(means, 0.025), 4), round(_percentile(means, 0.975), 4)]


def _review_files(review_root: Path) -> list[Path]:
    return sorted(
        path for path in review_root.rglob("*.json") if path.parent.name == "reviews"
    )


def _mechanical_summary(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_treatment: dict[str, dict[str, Any]] = {}
    for treatment in TREATMENTS:
        selected = [run for run in runs if run.get("treatment") == treatment]
        by_treatment[treatment] = {
            "run_count": len(selected),
            "process_success_count": sum(
                bool(run["mechanical_checks"]["process_succeeded"]) for run in selected
            ),
            "artifact_complete_count": sum(
                bool(run["mechanical_checks"]["required_artifacts_exist"])
                for run in selected
            ),
            "sources_json_valid_count": sum(
                bool(run["mechanical_checks"]["sources_json_valid"]) for run in selected
            ),
            "treatment_isolation_pass_count": sum(
                run["mechanical_checks"]["treatment_isolation"]["status"] == "pass"
                for run in selected
            ),
            "prompt_fact_anchor_pass_count": sum(
                bool(run["mechanical_checks"]["fact_anchors"]["prompt"]["all_present"])
                for run in selected
            ),
            "answer_fact_anchor_pass_count": sum(
                bool(run["mechanical_checks"]["fact_anchors"]["answer"]["all_present"])
                for run in selected
            ),
            "total_tokens": sum(
                int(run["metrics"]["total_tokens"]) for run in selected
            ),
            "noncached_tokens": sum(
                int(run["metrics"]["noncached_tokens"]) for run in selected
            ),
            "duration_ms": sum(int(run["duration_ms"]) for run in selected),
        }
    return by_treatment


def summarize_benchmark(
    suite: Mapping[str, Any],
    runs_payload: Mapping[str, Any],
    reviews: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Map blinded scores and report paired deltas with strict completeness gates."""

    validated = validate_suite(suite)
    if runs_payload.get("schema_version") != RUNS_SCHEMA:
        raise ValueError("unsupported FiscalPrompt benchmark runs schema")
    if runs_payload.get("suite_id") != validated["suite_id"]:
        raise ValueError("runs suite_id does not match suite")
    mappings = [
        dict(_mapping(raw, label="private_review_mappings[]"))
        for raw in _sequence(
            runs_payload.get("private_review_mappings"),
            label="private_review_mappings",
        )
    ]
    mapping_by_packet = {
        _text(mapping.get("packet_id"), label="packet_id"): mapping
        for mapping in mappings
    }
    if len(mapping_by_packet) != len(mappings):
        raise ValueError("duplicate review packet mapping")

    normalized_reviews: list[dict[str, Any]] = []
    reviewer_keys: set[tuple[str, str, str]] = set()
    model_reviewer_threads: set[str] = set()
    for review in reviews:
        packet_id = _text(review.get("packet_id"), label="review.packet_id")
        if packet_id not in mapping_by_packet:
            raise ValueError(f"review references unknown packet: {packet_id}")
        normalized = validate_review(
            review, suite=suite, packet_mapping=mapping_by_packet[packet_id]
        )
        key = (
            normalized["packet_id"],
            normalized["reviewer_type"],
            normalized["reviewer_id"],
        )
        if key in reviewer_keys:
            raise ValueError("duplicate reviewer record for a packet")
        reviewer_keys.add(key)
        if normalized["reviewer_type"] == "model":
            if normalized["thread_id"] in model_reviewer_threads:
                raise ValueError("model reviewer thread must be fresh for each packet")
            model_reviewer_threads.add(normalized["thread_id"])
        normalized_reviews.append(normalized)

    reviews_by_packet: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for review in normalized_reviews:
        reviews_by_packet[review["packet_id"]].append(review)
    missing_reviews: list[dict[str, str]] = []
    for packet_id in mapping_by_packet:
        observed_types = {
            review["reviewer_type"] for review in reviews_by_packet[packet_id]
        }
        for reviewer_type in validated["required_reviewer_types"]:
            if reviewer_type not in observed_types:
                missing_reviews.append(
                    {"packet_id": packet_id, "reviewer_type": reviewer_type}
                )

    prompt_weights = _weights(suite, "prompt")
    answer_weights = _weights(suite, "answer")
    paired_rows: list[dict[str, Any]] = []
    hard_failure_counts = Counter({treatment: 0 for treatment in TREATMENTS})
    winner_counts: dict[str, Counter[str]] = {
        "prompt": Counter(),
        "answer": Counter(),
    }
    if not missing_reviews:
        for packet_id, mapping in mapping_by_packet.items():
            packet_reviews = reviews_by_packet[packet_id]
            treatment_by_label = _mapping(
                mapping.get("treatment_by_label"), label="treatment_by_label"
            )
            treatment_scores: dict[str, dict[str, list[float]]] = {
                treatment: {"prompt": [], "answer": []} for treatment in TREATMENTS
            }
            for review in packet_reviews:
                for label in ("A", "B"):
                    treatment = str(treatment_by_label[label])
                    treatment_scores[treatment]["prompt"].append(
                        _weighted_score(
                            review["scores"][label]["prompt"], prompt_weights
                        )
                    )
                    treatment_scores[treatment]["answer"].append(
                        _weighted_score(
                            review["scores"][label]["answer"], answer_weights
                        )
                    )
                    hard_failure_counts[treatment] += len(
                        review["hard_failures"][label]
                    )
                for artifact_kind in ("prompt", "answer"):
                    winner_label = review["pairwise_winner"][artifact_kind]
                    winner = (
                        "tie"
                        if winner_label == "tie"
                        else str(treatment_by_label[winner_label])
                    )
                    winner_counts[artifact_kind][winner] += 1
            row: dict[str, Any] = {
                "packet_id": packet_id,
                "case_id": mapping["case_id"],
                "repeat": mapping["repeat"],
            }
            for treatment in TREATMENTS:
                for artifact_kind in ("prompt", "answer"):
                    values = treatment_scores[treatment][artifact_kind]
                    row[f"{treatment}_{artifact_kind}_score"] = sum(values) / len(
                        values
                    )
            row["prompt_delta"] = (
                row["optimize_prompt_prompt_score"] - row["fiscalprompt_prompt_score"]
            )
            row["answer_delta"] = (
                row["optimize_prompt_answer_score"] - row["fiscalprompt_answer_score"]
            )
            paired_rows.append(row)

    mechanical = _mechanical_summary(
        [
            _mapping(raw, label="runs[]")
            for raw in _sequence(runs_payload.get("runs"), label="runs")
        ]
    )
    decision_policy = _mapping(suite.get("decision_policy"), label="decision_policy")
    complete = not missing_reviews and len(paired_rows) >= int(
        decision_policy["minimum_complete_pairs"]
    )
    prompt_deltas = [float(row["prompt_delta"]) for row in paired_rows]
    answer_deltas = [float(row["answer_delta"]) for row in paired_rows]
    mean_prompt_delta = (
        sum(prompt_deltas) / len(prompt_deltas) if prompt_deltas else None
    )
    mean_answer_delta = (
        sum(answer_deltas) / len(answer_deltas) if answer_deltas else None
    )
    all_mechanical = all(
        values["process_success_count"] == values["run_count"]
        and values["artifact_complete_count"] == values["run_count"]
        and values["sources_json_valid_count"] == values["run_count"]
        and values["treatment_isolation_pass_count"] == values["run_count"]
        for values in mechanical.values()
    )
    noninferior = bool(
        complete
        and all_mechanical
        and mean_answer_delta is not None
        and mean_answer_delta >= float(decision_policy["answer_noninferiority_floor"])
        and hard_failure_counts["optimize_prompt"]
        <= hard_failure_counts["fiscalprompt"]
        + int(decision_policy["maximum_additional_optimizer_hard_failures"])
    )
    superior = bool(
        noninferior
        and mean_answer_delta is not None
        and mean_answer_delta >= float(decision_policy["answer_superiority_margin"])
        and _bootstrap_ci(answer_deltas)
        and _bootstrap_ci(answer_deltas)[0] > 0
    )
    outcome = (
        "incomplete"
        if not complete
        else (
            "optimizer_superior"
            if superior
            else "optimizer_noninferior" if noninferior else "optimizer_regression"
        )
    )
    return {
        "schema_version": SUMMARY_SCHEMA,
        "suite_id": validated["suite_id"],
        "suite_fingerprint_sha256": _canonical_sha256(suite),
        "status": "complete" if complete else "incomplete",
        "outcome": outcome,
        "benchmark_passed": noninferior if complete else None,
        "review_coverage": {
            "packet_count": len(mapping_by_packet),
            "review_count": len(normalized_reviews),
            "missing_reviews": missing_reviews,
        },
        "mechanical": mechanical,
        "semantic": {
            "paired_rows": paired_rows,
            "mean_prompt_delta": (
                round(mean_prompt_delta, 4) if mean_prompt_delta is not None else None
            ),
            "mean_answer_delta": (
                round(mean_answer_delta, 4) if mean_answer_delta is not None else None
            ),
            "prompt_delta_95pct_bootstrap_ci": _bootstrap_ci(prompt_deltas),
            "answer_delta_95pct_bootstrap_ci": _bootstrap_ci(answer_deltas),
            "winner_counts": {
                artifact_kind: dict(counts)
                for artifact_kind, counts in winner_counts.items()
            },
            "hard_failure_counts": dict(hard_failure_counts),
        },
        "decision_boundary": {
            "semantic_scores_are_reviewer_owned": True,
            "deterministic_code_only_validates_bindings_and_aggregates_scores": True,
            "no_superiority_claim_without_complete_tax_professional_review": True,
        },
    }


def _load_json(path: Path) -> dict[str, Any]:
    return dict(_mapping(json.loads(path.read_text(encoding="utf-8")), label=str(path)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--reviews-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    try:
        suite = _load_json(args.suite)
        runs = _load_json(args.runs)
        review_paths = _review_files(args.reviews_root)
        reviews = [_load_json(path) for path in review_paths]
        summary = summarize_benchmark(suite, runs, reviews)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        _write_json(args.output, summary)
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info("Wrote benchmark summary to %s", args.output)
    if summary["status"] != "complete":
        return 2
    return 0 if summary["benchmark_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
