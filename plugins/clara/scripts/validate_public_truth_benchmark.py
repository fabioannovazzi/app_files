#!/usr/bin/env python3
"""Validate a prepared candidate against a pinned public-truth benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

__all__ = ["main", "validate_public_truth_case"]

LOGGER = logging.getLogger(__name__)
BENCHMARK_SCHEMA = "clara.public_truth_benchmark.v1"
REPORT_SCHEMA = "clara.public_truth_validation.v1"
OBSERVATION_COLUMNS = (
    "observation_id",
    "metric_id",
    "period_start",
    "period_end",
    "period_grain",
    "value",
    "unit",
    "reported_increment",
    "source_id",
    "source_locator",
)
ALLOWED_PERIOD_GRAINS = {"month", "quarter"}
ALLOWED_ASSERTIONS = {"linear_identity", "rounded_sum"}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
DECIMAL_PATTERN = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be a list")
    return list(value)


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _sha256(value: Any, *, label: str) -> str:
    digest = _text(value, label=label).lower()
    if SHA256_PATTERN.fullmatch(digest) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _decimal(value: Any, *, label: str, positive: bool = False) -> Decimal:
    text = _text(value, label=label)
    if DECIMAL_PATTERN.fullmatch(text) is None:
        raise ValueError(f"{label} must be a canonical decimal string")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{label} must be a canonical decimal string") from exc
    if not number.is_finite() or (positive and number <= 0):
        qualifier = "positive " if positive else ""
        raise ValueError(f"{label} must be a finite {qualifier}decimal")
    return number


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _case_file(case_root: Path, relative_path: Any, *, label: str) -> Path:
    relative = Path(_text(relative_path, label=label))
    if relative.is_absolute():
        raise ValueError(f"{label} must be relative to the benchmark directory")
    resolved = (case_root / relative).resolve()
    if not resolved.is_relative_to(case_root.resolve()):
        raise ValueError(f"{label} must stay inside the benchmark directory")
    if not resolved.is_file():
        raise ValueError(f"{label} does not exist: {relative}")
    return resolved


def _validate_observation(row: Mapping[str, str], *, label: str) -> dict[str, str]:
    normalized = {
        column: _text(row.get(column), label=f"{label}.{column}")
        for column in OBSERVATION_COLUMNS
    }
    try:
        period_start = date.fromisoformat(normalized["period_start"])
        period_end = date.fromisoformat(normalized["period_end"])
    except ValueError as exc:
        raise ValueError(f"{label} periods must use ISO dates") from exc
    if period_start > period_end:
        raise ValueError(f"{label}.period_start must not follow period_end")
    if normalized["period_grain"] not in ALLOWED_PERIOD_GRAINS:
        raise ValueError(
            f"{label}.period_grain must be one of {sorted(ALLOWED_PERIOD_GRAINS)}"
        )
    _decimal(normalized["value"], label=f"{label}.value")
    _decimal(
        normalized["reported_increment"],
        label=f"{label}.reported_increment",
        positive=True,
    )
    return normalized


def _read_observations(
    path: Path,
    *,
    label: str,
    allow_duplicates: bool,
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    index: dict[str, dict[str, str]] = {}
    duplicates: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != OBSERVATION_COLUMNS:
            raise ValueError(f"{label} columns must equal {list(OBSERVATION_COLUMNS)}")
        for position, raw_row in enumerate(reader, start=2):
            if None in raw_row:
                raise ValueError(
                    f"{label} row {position} contains values beyond the declared columns"
                )
            row = _validate_observation(raw_row, label=f"{label} row {position}")
            observation_id = row["observation_id"]
            rows.append(row)
            if observation_id in index:
                duplicates.append(observation_id)
                if not allow_duplicates:
                    raise ValueError(
                        f"{label} contains duplicate observation_id "
                        f"{observation_id!r}"
                    )
                continue
            index[observation_id] = row
    if not rows:
        raise ValueError(f"{label} must contain at least one observation")
    return rows, index, duplicates


def _validate_sources(raw_sources: Any) -> tuple[list[dict[str, Any]], set[str]]:
    sources: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    for position, raw_source in enumerate(
        _sequence(raw_sources, label="benchmark.sources"), start=1
    ):
        source = _mapping(raw_source, label=f"benchmark.sources[{position}]")
        source_id = _text(
            source.get("source_id"),
            label=f"benchmark.sources[{position}].source_id",
        )
        if source_id in source_ids:
            raise ValueError(f"duplicate benchmark source_id {source_id!r}")
        source_ids.add(source_id)
        url = _text(source.get("url"), label=f"source {source_id}.url")
        if not url.startswith("https://"):
            raise ValueError(f"source {source_id}.url must use https")
        try:
            date.fromisoformat(
                _text(
                    source.get("published_date"),
                    label=f"source {source_id}.published_date",
                )
            )
        except ValueError as exc:
            raise ValueError(
                f"source {source_id}.published_date must use an ISO date"
            ) from exc
        byte_count = source.get("byte_count")
        if type(byte_count) is not int or byte_count <= 0:
            raise ValueError(f"source {source_id}.byte_count must be positive")
        normalized = dict(source)
        normalized["source_id"] = source_id
        normalized["sha256"] = _sha256(
            source.get("sha256"), label=f"source {source_id}.sha256"
        )
        sources.append(normalized)
    if not sources:
        raise ValueError("benchmark.sources must not be empty")
    return sources, source_ids


def _validate_observation_sources(
    rows: Sequence[Mapping[str, str]],
    *,
    source_ids: set[str],
    label: str,
) -> None:
    unknown = sorted({row["source_id"] for row in rows} - source_ids)
    if unknown:
        raise ValueError(f"{label} references unknown sources: {unknown}")


def _validate_reviewed_boundary(
    boundary: Mapping[str, Any],
    expected_rows: Sequence[Mapping[str, str]],
) -> None:
    reported = tuple(
        _text(item, label="reviewed_boundary.monthly_reported_metric_ids[]")
        for item in _sequence(
            boundary.get("monthly_reported_metric_ids"),
            label="reviewed_boundary.monthly_reported_metric_ids",
        )
    )
    not_disclosed = tuple(
        _text(item, label="reviewed_boundary.monthly_not_disclosed_metric_ids[]")
        for item in _sequence(
            boundary.get("monthly_not_disclosed_metric_ids"),
            label="reviewed_boundary.monthly_not_disclosed_metric_ids",
        )
    )
    if (
        not reported
        or len(reported) != len(set(reported))
        or len(not_disclosed) != len(set(not_disclosed))
        or set(reported).intersection(not_disclosed)
    ):
        raise ValueError(
            "reviewed monthly metric lists must be unique, disjoint, and include "
            "at least one reported metric"
        )
    expected_monthly = {
        row["metric_id"] for row in expected_rows if row["period_grain"] == "month"
    }
    if expected_monthly != set(reported):
        raise ValueError(
            "expected monthly observations must equal the reviewed reported metrics"
        )
    expected_quarterly = {
        row["metric_id"] for row in expected_rows if row["period_grain"] == "quarter"
    }
    missing_quarterly = sorted(set(not_disclosed) - expected_quarterly)
    if missing_quarterly:
        raise ValueError(
            "monthly not-disclosed metrics must be evidenced at quarterly grain: "
            f"{missing_quarterly}"
        )


def _validate_assertion_contracts(raw_assertions: Any) -> list[dict[str, Any]]:
    assertions: list[dict[str, Any]] = []
    assertion_ids: set[str] = set()
    for position, raw_assertion in enumerate(
        _sequence(raw_assertions, label="benchmark.assertions"), start=1
    ):
        assertion = dict(
            _mapping(raw_assertion, label=f"benchmark.assertions[{position}]")
        )
        assertion_id = _text(
            assertion.get("assertion_id"),
            label=f"benchmark.assertions[{position}].assertion_id",
        )
        if assertion_id in assertion_ids:
            raise ValueError(f"duplicate assertion_id {assertion_id!r}")
        assertion_ids.add(assertion_id)
        kind = _text(
            assertion.get("kind"),
            label=f"benchmark.assertions[{position}].kind",
        )
        if kind not in ALLOWED_ASSERTIONS:
            raise ValueError(
                f"assertion {assertion_id} kind must be one of "
                f"{sorted(ALLOWED_ASSERTIONS)}"
            )
        assertion["assertion_id"] = assertion_id
        assertion["kind"] = kind
        assertions.append(assertion)
    if not assertions:
        raise ValueError("benchmark.assertions must not be empty")
    return assertions


def _load_benchmark(
    benchmark_path: Path,
) -> tuple[dict[str, Any], Path, Path, list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("benchmark must contain valid JSON") from exc
    root = _mapping(benchmark, label="benchmark")
    if root.get("schema_version") != BENCHMARK_SCHEMA:
        raise ValueError("unsupported public-truth benchmark schema")
    _text(root.get("case_id"), label="benchmark.case_id")
    _text(root.get("purpose"), label="benchmark.purpose")
    boundary = _mapping(root.get("reviewed_boundary"), label="reviewed_boundary")
    if boundary.get("status") != "reviewed":
        raise ValueError("reviewed_boundary.status must be reviewed")
    _text(boundary.get("statement"), label="reviewed_boundary.statement")

    contract = _mapping(root.get("candidate_contract"), label="candidate_contract")
    required_columns = tuple(
        _text(item, label="candidate_contract.required_columns[]")
        for item in _sequence(
            contract.get("required_columns"),
            label="candidate_contract.required_columns",
        )
    )
    if required_columns != OBSERVATION_COLUMNS:
        raise ValueError(
            "candidate_contract.required_columns must equal the validator contract"
        )
    if contract.get("exact_expected_set") is not True:
        raise ValueError("candidate_contract.exact_expected_set must be true")
    if contract.get("truth_to_expected") != "exact_identity":
        raise ValueError("candidate_contract.truth_to_expected must be exact_identity")

    files = _mapping(root.get("files"), label="benchmark.files")
    if set(files) != {"expected", "truth"}:
        raise ValueError("benchmark.files must contain exactly truth and expected")
    truth_record = _mapping(files["truth"], label="benchmark.files.truth")
    expected_record = _mapping(files["expected"], label="benchmark.files.expected")
    case_root = benchmark_path.resolve().parent
    truth_path = _case_file(
        case_root, truth_record.get("path"), label="benchmark.files.truth.path"
    )
    expected_path = _case_file(
        case_root, expected_record.get("path"), label="benchmark.files.expected.path"
    )
    for label, record, path in (
        ("truth", truth_record, truth_path),
        ("expected", expected_record, expected_path),
    ):
        declared = _sha256(
            record.get("sha256"), label=f"benchmark.files.{label}.sha256"
        )
        actual = _file_sha256(path)
        if actual != declared:
            raise ValueError(
                f"benchmark.files.{label} digest mismatch: "
                f"declared {declared}, actual {actual}"
            )

    sources, _source_ids = _validate_sources(root.get("sources"))
    assertions = _validate_assertion_contracts(root.get("assertions"))
    return dict(root), truth_path, expected_path, sources, assertions


def _compare_candidate(
    expected_rows: Sequence[Mapping[str, str]],
    expected_index: Mapping[str, Mapping[str, str]],
    candidate_rows: Sequence[Mapping[str, str]],
    candidate_index: Mapping[str, Mapping[str, str]],
    duplicate_ids: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    results: list[dict[str, Any]] = []
    matched = 0
    missing = 0
    mismatched = 0
    for expected in expected_rows:
        observation_id = expected["observation_id"]
        candidate = candidate_index.get(observation_id)
        if candidate is None:
            missing += 1
            results.append(
                {
                    "observation_id": observation_id,
                    "status": "missing",
                }
            )
            continue
        differences = [
            column
            for column in OBSERVATION_COLUMNS
            if candidate[column] != expected[column]
        ]
        if differences:
            mismatched += 1
            results.append(
                {
                    "observation_id": observation_id,
                    "status": "mismatched",
                    "fields": differences,
                }
            )
            continue
        matched += 1
        results.append({"observation_id": observation_id, "status": "matched"})

    unexpected_ids = sorted(set(candidate_index) - set(expected_index))
    for observation_id in unexpected_ids:
        results.append({"observation_id": observation_id, "status": "unexpected"})

    errors = [
        f"duplicate candidate observation_id: {observation_id}"
        for observation_id in sorted(set(duplicate_ids))
    ]
    counts = {
        "expected": len(expected_rows),
        "candidate": len(candidate_rows),
        "matched": matched,
        "missing": missing,
        "unexpected": len(unexpected_ids),
        "mismatched": mismatched,
        "duplicates": len(duplicate_ids),
    }
    return results, counts, errors


def _rounded_sum_result(
    assertion: Mapping[str, Any],
    index: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    assertion_id = str(assertion["assertion_id"])
    source_ids = [
        _text(item, label=f"assertion {assertion_id}.source_observation_ids[]")
        for item in _sequence(
            assertion.get("source_observation_ids"),
            label=f"assertion {assertion_id}.source_observation_ids",
        )
    ]
    if not source_ids or len(source_ids) != len(set(source_ids)):
        raise ValueError(
            f"assertion {assertion_id} source observations must be non-empty "
            "and unique"
        )
    target_id = _text(
        assertion.get("target_observation_id"),
        label=f"assertion {assertion_id}.target_observation_id",
    )
    missing = sorted(
        observation_id
        for observation_id in [*source_ids, target_id]
        if observation_id not in index
    )
    if missing:
        return {
            "assertion_id": assertion_id,
            "kind": "rounded_sum",
            "status": "failed",
            "reason": "missing_observations",
            "missing_observation_ids": missing,
        }
    source_rows = [index[observation_id] for observation_id in source_ids]
    target = index[target_id]
    units = {row["unit"] for row in [*source_rows, target]}
    if len(units) != 1:
        return {
            "assertion_id": assertion_id,
            "kind": "rounded_sum",
            "status": "failed",
            "reason": "unit_mismatch",
            "units": sorted(units),
        }
    source_total = sum(
        (
            _decimal(row["value"], label=f"{assertion_id}.source.value")
            for row in source_rows
        ),
        Decimal(0),
    )
    target_value = _decimal(target["value"], label=f"{assertion_id}.target.value")
    difference = source_total - target_value
    tolerance = sum(
        (
            _decimal(
                row["reported_increment"],
                label=f"{assertion_id}.source.reported_increment",
                positive=True,
            )
            / 2
            for row in source_rows
        ),
        _decimal(
            target["reported_increment"],
            label=f"{assertion_id}.target.reported_increment",
            positive=True,
        )
        / 2,
    )
    passed = abs(difference) <= tolerance
    return {
        "assertion_id": assertion_id,
        "kind": "rounded_sum",
        "status": "passed" if passed else "failed",
        "source_total": _decimal_text(source_total),
        "target_value": _decimal_text(target_value),
        "difference": _decimal_text(difference),
        "tolerance": _decimal_text(tolerance),
        "unit": target["unit"],
    }


def _linear_identity_result(
    assertion: Mapping[str, Any],
    index: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    assertion_id = str(assertion["assertion_id"])
    target_id = _text(
        assertion.get("target_observation_id"),
        label=f"assertion {assertion_id}.target_observation_id",
    )
    terms = [
        _mapping(item, label=f"assertion {assertion_id}.terms[]")
        for item in _sequence(
            assertion.get("terms"), label=f"assertion {assertion_id}.terms"
        )
    ]
    if not terms:
        raise ValueError(f"assertion {assertion_id}.terms must not be empty")
    term_ids = [
        _text(
            term.get("observation_id"),
            label=f"assertion {assertion_id}.terms[].observation_id",
        )
        for term in terms
    ]
    missing = sorted(
        observation_id
        for observation_id in [*term_ids, target_id]
        if observation_id not in index
    )
    if missing:
        return {
            "assertion_id": assertion_id,
            "kind": "linear_identity",
            "status": "failed",
            "reason": "missing_observations",
            "missing_observation_ids": missing,
        }
    rows = [index[observation_id] for observation_id in term_ids]
    target = index[target_id]
    units = {row["unit"] for row in [*rows, target]}
    if len(units) != 1:
        return {
            "assertion_id": assertion_id,
            "kind": "linear_identity",
            "status": "failed",
            "reason": "unit_mismatch",
            "units": sorted(units),
        }
    computed = sum(
        (
            _decimal(row["value"], label=f"{assertion_id}.term.value")
            * _decimal(
                term.get("factor"),
                label=f"{assertion_id}.terms[].factor",
            )
            for row, term in zip(rows, terms, strict=True)
        ),
        Decimal(0),
    )
    target_value = _decimal(target["value"], label=f"{assertion_id}.target.value")
    difference = computed - target_value
    tolerance = _decimal(
        assertion.get("tolerance"),
        label=f"assertion {assertion_id}.tolerance",
    )
    if tolerance < 0:
        raise ValueError(f"assertion {assertion_id}.tolerance must not be negative")
    passed = abs(difference) <= tolerance
    return {
        "assertion_id": assertion_id,
        "kind": "linear_identity",
        "status": "passed" if passed else "failed",
        "computed_value": _decimal_text(computed),
        "target_value": _decimal_text(target_value),
        "difference": _decimal_text(difference),
        "tolerance": _decimal_text(tolerance),
        "unit": target["unit"],
    }


def _evaluate_assertions(
    assertions: Sequence[Mapping[str, Any]],
    candidate_index: Mapping[str, Mapping[str, str]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for assertion in assertions:
        if assertion["kind"] == "rounded_sum":
            results.append(_rounded_sum_result(assertion, candidate_index))
        else:
            results.append(_linear_identity_result(assertion, candidate_index))
    return results


def _monthly_abstention_result(
    boundary: Mapping[str, Any],
    candidate_rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    metric_ids = [
        _text(item, label="reviewed_boundary.monthly_not_disclosed_metric_ids[]")
        for item in _sequence(
            boundary.get("monthly_not_disclosed_metric_ids"),
            label="reviewed_boundary.monthly_not_disclosed_metric_ids",
        )
    ]
    not_disclosed = set(metric_ids)
    offending_ids = sorted(
        row["observation_id"]
        for row in candidate_rows
        if row["period_grain"] == "month" and row["metric_id"] in not_disclosed
    )
    return {
        "status": "failed" if offending_ids else "passed",
        "metric_ids": metric_ids,
        "offending_observation_ids": offending_ids,
    }


def validate_public_truth_case(
    benchmark_path: Path,
    candidate_path: Path,
) -> dict[str, Any]:
    """Return deterministic validation evidence for one prepared candidate.

    This validator is deterministic because exact file identity, row equality,
    Decimal arithmetic, and declared rounding intervals are mechanically
    verifiable. Source relevance and the meaning of each metric remain the
    reviewed judgement recorded by the benchmark.
    """

    benchmark_path = benchmark_path.resolve()
    candidate_path = candidate_path.resolve()
    if not benchmark_path.is_file():
        raise ValueError(f"benchmark does not exist: {benchmark_path}")
    if not candidate_path.is_file():
        raise ValueError(f"candidate does not exist: {candidate_path}")

    benchmark, truth_path, expected_path, sources, assertions = _load_benchmark(
        benchmark_path
    )
    truth_rows, _truth_index, _truth_duplicates = _read_observations(
        truth_path, label="truth observations", allow_duplicates=False
    )
    expected_rows, expected_index, _expected_duplicates = _read_observations(
        expected_path, label="expected observations", allow_duplicates=False
    )
    if truth_rows != expected_rows:
        raise ValueError(
            "truth and expected observations must be byte-normalized exact identity"
        )
    candidate_rows, candidate_index, duplicate_ids = _read_observations(
        candidate_path, label="candidate observations", allow_duplicates=True
    )
    source_ids = {str(source["source_id"]) for source in sources}
    _validate_observation_sources(
        truth_rows, source_ids=source_ids, label="truth observations"
    )
    _validate_observation_sources(
        expected_rows, source_ids=source_ids, label="expected observations"
    )
    boundary = _mapping(
        benchmark["reviewed_boundary"],
        label="benchmark.reviewed_boundary",
    )
    _validate_reviewed_boundary(boundary, expected_rows)
    _validate_observation_sources(
        candidate_rows, source_ids=source_ids, label="candidate observations"
    )

    fact_results, fact_counts, errors = _compare_candidate(
        expected_rows,
        expected_index,
        candidate_rows,
        candidate_index,
        duplicate_ids,
    )
    abstention_result = _monthly_abstention_result(boundary, candidate_rows)
    assertion_results = _evaluate_assertions(assertions, candidate_index)
    assertions_passed = sum(
        result["status"] == "passed" for result in assertion_results
    )
    assertions_failed = len(assertion_results) - assertions_passed
    warnings: list[str] = []
    status = (
        "passed"
        if not errors
        and fact_counts["missing"] == 0
        and fact_counts["unexpected"] == 0
        and fact_counts["mismatched"] == 0
        and fact_counts["duplicates"] == 0
        and abstention_result["status"] == "passed"
        and assertions_failed == 0
        else "failed"
    )
    counts = {
        **fact_counts,
        "assertions_passed": assertions_passed,
        "assertions_failed": assertions_failed,
        "abstention_failures": len(abstention_result["offending_observation_ids"]),
        "errors": len(errors),
        "warnings": len(warnings),
    }
    return {
        "schema_version": REPORT_SCHEMA,
        "case_id": benchmark["case_id"],
        "status": status,
        "boundary": benchmark["reviewed_boundary"],
        "inputs": {
            "benchmark": {
                "path": benchmark_path.name,
                "sha256": _file_sha256(benchmark_path),
            },
            "truth": {
                "path": truth_path.name,
                "sha256": _file_sha256(truth_path),
            },
            "expected": {
                "path": expected_path.name,
                "sha256": _file_sha256(expected_path),
            },
            "candidate": {
                "sha256": _file_sha256(candidate_path),
            },
            "sources": sources,
        },
        "counts": counts,
        "fact_results": fact_results,
        "abstention_result": abstention_result,
        "assertion_results": assertion_results,
        "errors": errors,
        "warnings": warnings,
        "benchmark_passed": status == "passed",
        "downstream_readiness": {
            "status": "not_assessed",
            "reason": (
                "Render compatibility and evidence sealing are outside this "
                "public-truth benchmark."
            ),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run the public-truth validator CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        report = validate_public_truth_case(args.benchmark, args.candidate)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2
    LOGGER.info(
        "Public-truth benchmark %s: %s",
        report["case_id"],
        report["status"],
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
