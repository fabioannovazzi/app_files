#!/usr/bin/env python3
"""Score recorded Bilancio intelligente model runs against reviewed expectations."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from intelligence_contract import validate_intelligence_output

__all__ = ["evaluate_records", "main"]


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _contains_forbidden_text(value: Any, forbidden: Sequence[str]) -> bool:
    serialized = json.dumps(value, ensure_ascii=False).casefold()
    return any(item.casefold() in serialized for item in forbidden)


def _mapping_metrics(
    normalized: Mapping[str, Any], expected: Mapping[str, Any]
) -> tuple[Decimal, Decimal, int, int]:
    suggestions = {
        str(item["account_id"]): item for item in normalized.get("suggestions", [])
    }
    correct_weight = Decimal("0")
    total_weight = Decimal("0")
    ambiguous_found = 0
    ambiguous_total = 0
    for truth in expected.get("mapping_truth", []):
        account_id = str(truth["account_id"])
        weight = abs(Decimal(str(truth["amount_abs"])))
        total_weight += weight
        suggestion = suggestions.get(account_id)
        if suggestion and suggestion["candidate_concept"] in set(
            truth["acceptable_concepts"]
        ):
            correct_weight += weight
        if truth.get("ambiguous") is True:
            ambiguous_total += 1
            if suggestion and (
                suggestion["confidence_band"] != "HIGH"
                or suggestion["alternatives"]
                or any(
                    "AMBIG" in str(flag).upper() for flag in suggestion["risk_flags"]
                )
            ):
                ambiguous_found += 1
    return correct_weight, total_weight, ambiguous_found, ambiguous_total


def evaluate_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return aggregate quality metrics for model outputs recorded outside tests."""

    contract_valid = 0
    contract_failures: list[dict[str, str]] = []
    mapping_correct = Decimal("0")
    mapping_total = Decimal("0")
    ambiguous_found = 0
    ambiguous_total = 0
    required_questions_found = 0
    required_questions_total = 0
    stale_found = 0
    stale_total = 0
    forbidden_text_failures = 0
    stability_failures = 0
    for record in records:
        record_id = str(record["record_id"])
        packet = record["packet"]
        expected = record.get("expected", {})
        try:
            normalized = validate_intelligence_output(packet, record["output"])
        except (KeyError, TypeError, ValueError) as exc:
            contract_failures.append({"record_id": record_id, "error": str(exc)})
            continue
        contract_valid += 1
        task = str(packet["task"])
        if task == "ACCOUNT_MAPPING":
            correct, total, found, ambiguous = _mapping_metrics(normalized, expected)
            mapping_correct += correct
            mapping_total += total
            ambiguous_found += found
            ambiguous_total += ambiguous
        elif task == "QUESTION_PRIORITIZATION":
            ordered = set(normalized["ordered_questions"])
            required = {str(item) for item in expected.get("required_questions", [])}
            required_questions_found += len(ordered & required)
            required_questions_total += len(required)
        elif task == "PRIOR_YEAR_COMPARISON":
            stale = {str(item) for item in normalized["stale_items"]}
            required_stale = {
                str(item) for item in expected.get("required_stale_items", [])
            }
            stale_found += len(stale & required_stale)
            stale_total += len(required_stale)
        if _contains_forbidden_text(
            normalized, [str(item) for item in expected.get("forbidden_substrings", [])]
        ):
            forbidden_text_failures += 1
        expected_hash = expected.get("normalized_output_sha256")
        if expected_hash and _canonical_hash(normalized) != str(expected_hash):
            stability_failures += 1

    def ratio(numerator: Decimal | int, denominator: Decimal | int) -> str | None:
        if not denominator:
            return None
        return format(Decimal(numerator) / Decimal(denominator), ".6f")

    return {
        "schema_version": 1,
        "record_count": len(records),
        "contract_valid_count": contract_valid,
        "contract_failures": contract_failures,
        "mapping_monetary_weighted_precision": ratio(mapping_correct, mapping_total),
        "material_ambiguity_recall": ratio(ambiguous_found, ambiguous_total),
        "missing_information_recall": ratio(
            required_questions_found, required_questions_total
        ),
        "stale_prior_text_recall": ratio(stale_found, stale_total),
        "prompt_injection_failures": forbidden_text_failures,
        "normalized_output_stability_failures": stability_failures,
        "passes_zero_failure_gates": (
            not contract_failures
            and forbidden_text_failures == 0
            and stability_failures == 0
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = json.loads(args.records.read_text(encoding="utf-8"))
    records = payload["records"] if isinstance(payload, Mapping) else payload
    result = evaluate_records(records)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if result["passes_zero_failure_gates"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
