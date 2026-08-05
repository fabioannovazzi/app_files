#!/usr/bin/env python3
"""Benchmark the deterministic Bilancio engine against specification targets."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

from xbrl_case import (
    MAX_TEMPLATE_ROWS,
    apply_mapping_decisions,
    build_statements,
    confirm_parser,
    create_case,
    determine_forms,
    ingest_trial_balance,
    run_validation,
    save_case,
    select_form,
)

__all__ = ["main", "run_benchmark"]

TARGETS_SECONDS = {
    "parse_20k": 60.0,
    "statement_recompute": 10.0,
    "local_validation": 60.0,
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _statement_hash(statements: dict[str, Any]) -> str:
    payload = dict(statements)
    payload.pop("computed_at", None)
    payload.pop("computation_context", None)
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _prepare_output(output_dir: Path) -> Path:
    if output_dir.is_symlink():
        raise ValueError("Benchmark output must not be a symbolic link")
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise ValueError("Benchmark output directory must be empty")
    return output_dir.resolve()


def _write_trial_balance(path: Path, row_count: int) -> str:
    header = (
        "account_code,account_description,opening_signed,period_debit,"
        "period_credit,closing_signed,prior_closing_signed\n"
    )
    midpoint = row_count // 2
    rows = [header]
    for index in range(row_count):
        code = f"{index + 1:08d}"
        if index < midpoint:
            rows.append(f"{code},Asset {code},90,10,0,100,90\n")
        else:
            rows.append(f"{code},Liability {code},-90,0,10,-100,-90\n")
    payload = "".join(rows)
    path.write_text(payload, encoding="utf-8")
    digest = _sha256_file(path)
    if hashlib.sha256(payload.encode("utf-8")).hexdigest() != digest:
        raise OSError("Benchmark trial-balance checksum verification failed")
    return digest


def _case_payload() -> dict[str, Any]:
    return {
        "case_id": "performance_20k",
        "tenant_id": "performance_benchmark",
        "entity": {
            "legal_name": "Synthetic Performance S.r.l.",
            "tax_identifier": "IT00000000000",
            "registered_office": "Milano (MI), Italia",
            "legal_form": "SRL",
            "accounting_framework": "OIC",
            "listed": False,
            "regulated_sector": False,
            "consolidated": False,
            "final_liquidation": False,
            "first_financial_year": False,
            "prior_year_form": "ABBREVIATED",
            "micro_exclusion_flags": [],
        },
        "period": {"start": "2025-01-01", "end": "2025-12-31"},
        "oic_rule_pack": "OIC_2026.1",
        "taxonomy_checksum": "a" * 64,
    }


def _mapping_decisions(case: dict[str, Any]) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for entry in case["trial_balance"]["entries"]:
        is_asset = not str(entry["closing_signed"]).startswith("-")
        decisions.append(
            {
                "account_id": entry["account_id"],
                "decision": "ACCEPTED",
                "allocations": [
                    {
                        "canonical_line": (
                            "SP.ATTIVO.BENCHMARK"
                            if is_asset
                            else "SP.PASSIVO.BENCHMARK"
                        ),
                        "statement_section": (
                            "ASSETS" if is_asset else "LIABILITIES_EQUITY"
                        ),
                        "current_amount": entry["closing_signed"],
                        "prior_amount": entry["prior_closing_signed"],
                        "evidence_status": "USER_CONFIRMED",
                        "review_reason": "Synthetic performance fixture",
                    }
                ],
            }
        )
    return decisions


def run_benchmark(
    output_dir: Path, rule_pack_path: Path, row_count: int = MAX_TEMPLATE_ROWS
) -> dict[str, Any]:
    """Run one reproducible synthetic benchmark and persist its evidence."""

    if isinstance(row_count, bool) or row_count < 2 or row_count > MAX_TEMPLATE_ROWS:
        raise ValueError(f"row_count must be from 2 to {MAX_TEMPLATE_ROWS}")
    if row_count % 2:
        raise ValueError("row_count must be even so the synthetic ledger balances")
    root = _prepare_output(output_dir)
    if rule_pack_path.is_symlink() or not rule_pack_path.is_file():
        raise ValueError("Rule pack must be a regular local file")
    rule_pack = json.loads(rule_pack_path.read_text(encoding="utf-8"))
    source = root / "trial-balance.csv"
    source_sha256 = _write_trial_balance(source, row_count)
    case_dir = root / "case"
    case = create_case(case_dir, _case_payload(), rule_pack, "benchmark")
    # This benchmark measures the generic accounting kernel rather than the
    # separately audited official-taxonomy presentation inventory.
    case["statutory_presentation_required"] = False

    started = perf_counter()
    case = ingest_trial_balance(case, source, "benchmark", case["revision_id"])
    parse_seconds = perf_counter() - started
    case = confirm_parser(
        case,
        "TURNOVER_EXCLUDES_OPENING",
        "benchmark",
        case["revision_id"],
    )
    metrics = [
        {
            "year": 2025,
            "assets": "100000000",
            "revenue": "100000000",
            "employees": "1000",
        },
        {
            "year": 2024,
            "assets": "100000000",
            "revenue": "100000000",
            "employees": "1000",
        },
    ]
    case = determine_forms(case, metrics, rule_pack, "benchmark", case["revision_id"])
    case = select_form(case, "ORDINARY", "benchmark", case["revision_id"])

    decisions = _mapping_decisions(case)
    started = perf_counter()
    case = apply_mapping_decisions(case, decisions, "benchmark", case["revision_id"])
    mapping_apply_seconds = perf_counter() - started
    started = perf_counter()
    case = build_statements(case, "benchmark", case["revision_id"])
    statement_seconds = perf_counter() - started
    first_statement_hash = _statement_hash(case["statements"])

    started = perf_counter()
    case = build_statements(case, "benchmark", case["revision_id"])
    deterministic_recompute_seconds = perf_counter() - started
    second_statement_hash = _statement_hash(case["statements"])
    if first_statement_hash != second_statement_hash:
        raise RuntimeError("Statement recomputation was not deterministic")

    started = perf_counter()
    case = run_validation(case, "benchmark", case["revision_id"])
    validation_seconds = perf_counter() - started
    save_case(case_dir, case)

    target_results = {
        "parse_20k": {
            "target_seconds": TARGETS_SECONDS["parse_20k"],
            "observed_seconds": parse_seconds,
            "status": (
                "PASS" if parse_seconds <= TARGETS_SECONDS["parse_20k"] else "FAIL"
            ),
        },
        "statement_recompute": {
            "target_seconds": TARGETS_SECONDS["statement_recompute"],
            "observed_seconds": statement_seconds,
            "status": (
                "PASS"
                if statement_seconds <= TARGETS_SECONDS["statement_recompute"]
                else "FAIL"
            ),
        },
        "local_validation": {
            "target_seconds": TARGETS_SECONDS["local_validation"],
            "observed_seconds": validation_seconds,
            "status": (
                "PASS"
                if validation_seconds <= TARGETS_SECONDS["local_validation"]
                else "FAIL"
            ),
        },
    }
    result = {
        "schema_version": 1,
        "benchmark_id": "bilancio-performance-v1",
        "row_count": row_count,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor() or "UNREPORTED",
        },
        "source": {
            "path": source.name,
            "size_bytes": source.stat().st_size,
            "sha256": source_sha256,
        },
        "measurements_seconds": {
            "parse": parse_seconds,
            "mapping_apply": mapping_apply_seconds,
            "statement_recompute": statement_seconds,
            "deterministic_recompute": deterministic_recompute_seconds,
            "local_validation": validation_seconds,
        },
        "statement_sha256": first_statement_hash,
        "deterministic_recompute": True,
        "validation_result": case["validation"]["status"],
        "targets": target_results,
        "status": (
            "PASS"
            if all(item["status"] == "PASS" for item in target_results.values())
            else "FAIL"
        ),
        "not_measured": [
            "MODEL_NARRATIVE_DRAFT_120_SECONDS",
            "PRODUCTION_REVIEW_GRID_RESPONSIVENESS",
        ],
    }
    manifest_path = root / "performance-manifest.json"
    manifest_bytes = _canonical_bytes(result) + b"\n"
    manifest_path.write_bytes(manifest_bytes)
    result["manifest_sha256"] = _sha256_file(manifest_path)
    return result


def main(argv: list[str] | None = None) -> int:
    """Run the benchmark from the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--rule-pack",
        type=Path,
        default=(
            Path(__file__).resolve().parents[1]
            / "rulepacks"
            / "it"
            / "statutory-forms-2026.1.json"
        ),
    )
    parser.add_argument("--rows", type=int, default=MAX_TEMPLATE_ROWS)
    args = parser.parse_args(argv)
    try:
        result = run_benchmark(args.output_dir, args.rule_pack, args.rows)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
