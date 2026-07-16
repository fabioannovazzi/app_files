from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.slides.launch_pdf_validator import (
    DEFAULT_LAUNCH_PACKAGE_ROOTS,
    _build_reading_completeness_audit,
    _canonical_text,
    _canonicalize_analysis_payload,
    _iter_slide_units,
    _normalize_text,
    resolve_launch_package_for_pdf,
)

__all__ = ["build_pro_audit_packages", "main"]

LOGGER = logging.getLogger(__name__)

DEFAULT_REPORTS_DIR = Path("launch_reports")
DEFAULT_VALIDATION_DIR = DEFAULT_REPORTS_DIR / "validation"
DEFAULT_OUTPUT_DIR = DEFAULT_REPORTS_DIR / "validator_test_runs" / "pro_audit"
DEFAULT_PACKAGE_ROOT = DEFAULT_LAUNCH_PACKAGE_ROOTS[0]
READING_CACHE_DIRNAME = ".launch_report_reading_cache"
VALIDATION_SUFFIX = ".validation.json"
MAX_PACKAGE_EVIDENCE_ROWS = 5
DATA_ONLY_FILENAMES = (
    "report_context.json",
    "mapped_text_units.json",
    "deterministic_results.json",
    "caught_units.json",
    "unresolved_units.json",
    "non_claim_units.json",
    "mapping_issue_units.json",
    "uncaught_units.json",
    "image_regions.json",
    "unmatched_deterministic_results.json",
    "package_evidence.json",
    "pro_output_schema.json",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a structured Pro audit package for the launch-report validator "
            "test loop."
        )
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory containing launch report PDFs and the reading cache.",
    )
    parser.add_argument(
        "--validation-dir",
        type=Path,
        default=DEFAULT_VALIDATION_DIR,
        help="Directory containing *.validation.json artifacts.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where the audit package run folder will be written.",
    )
    parser.add_argument(
        "--package-root",
        type=Path,
        default=DEFAULT_PACKAGE_ROOT,
        help="Fallback root for deterministic launch packages.",
    )
    parser.add_argument(
        "--report",
        dest="reports",
        action="append",
        default=[],
        help=(
            "Report id to package, such as lipstick or lip_gloss. "
            "May be passed more than once. Defaults to all validation reports."
        ),
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Run folder name. Defaults to a UTC timestamp.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (default: INFO).",
    )
    return parser.parse_args()


def _safe_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object.")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _clear_existing_report_package(report_output_dir: Path) -> None:
    if not report_output_dir.exists():
        return
    for path in report_output_dir.iterdir():
        if path.is_file() and (
            path.name in DATA_ONLY_FILENAMES
            or path.name in {"prompt.md", "instructions.md"}
        ):
            path.unlink()


def _validation_report_id(path: Path) -> str:
    if not path.name.endswith(VALIDATION_SUFFIX):
        raise ValueError(f"{path} is not a validation artifact.")
    return path.name[: -len(VALIDATION_SUFFIX)]


def _validation_files_by_cache_id(validation_dir: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in sorted(validation_dir.glob(f"*{VALIDATION_SUFFIX}")):
        report_id = _validation_report_id(path)
        if report_id == "batch":
            continue
        files[report_id] = path
        files[_canonical_text(report_id)] = path
    return files


def _report_ids_from_validation_dir(validation_dir: Path) -> list[str]:
    report_ids: list[str] = []
    for path in sorted(validation_dir.glob(f"*{VALIDATION_SUFFIX}")):
        report_id = _validation_report_id(path)
        if report_id != "batch":
            report_ids.append(report_id)
    return report_ids


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stable_hash(parts: list[Any]) -> str:
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _slide_meta(slide: dict[str, Any], fallback_index: int) -> dict[str, Any]:
    slide_number = _int_or_none(slide.get("slide_number") or slide.get("slideNumber"))
    page_number = _int_or_none(slide.get("page_number") or slide.get("pageNumber"))
    slide_id = _normalize_text(slide.get("slide_id") or slide.get("slideId"))
    return {
        "slide_id": slide_id or f"slide-{fallback_index + 1:03d}",
        "slide_number": (
            slide_number if slide_number is not None else fallback_index + 1
        ),
        "page_number": page_number if page_number is not None else fallback_index + 1,
    }


def _unit_match_key(
    *,
    text: Any,
    slide_number: Any,
    source_kind: Any,
    block_id: Any,
) -> tuple[str, str, str, str]:
    slide_value = _int_or_none(slide_number)
    return (
        _canonical_text(text),
        str(slide_value if slide_value is not None else ""),
        _canonical_text(source_kind),
        _canonical_text(block_id),
    )


def _unit_record(
    *,
    report_id: str,
    slide: dict[str, Any],
    slide_index: int,
    unit: dict[str, Any],
    unit_index: int,
) -> dict[str, Any]:
    slide_meta = _slide_meta(slide, slide_index)
    source_kind = _normalize_text(unit.get("source_kind"))
    block_id = _normalize_text(unit.get("block_id")) or None
    text = _normalize_text(unit.get("text"))
    unit_id = (
        f"{report_id}:s{slide_meta['slide_number']}:"
        f"{source_kind or 'unknown'}:{block_id or 'none'}:"
        f"{unit_index}:{_stable_hash([text])}"
    )
    record = {
        "unit_id": unit_id,
        "report_id": report_id,
        **slide_meta,
        "unit_index": unit_index,
        "text": text,
        "canonical_text": _canonical_text(text),
        "source_kind": source_kind or None,
        "block_id": block_id,
        "block_type": _normalize_text(unit.get("block_type")) or None,
        "context_text": _normalize_text(unit.get("context_text")) or None,
        "row_index": _int_or_none(unit.get("row_index")),
        "item_index": _int_or_none(unit.get("item_index")),
        "deterministic_status": "uncaught",
        "deterministic_result_ids": [],
    }
    return record


def _collect_mapped_units(
    *, report_id: str, analysis_payload: dict[str, Any]
) -> list[dict[str, Any]]:
    canonical_analysis = _canonicalize_analysis_payload(analysis_payload)
    slides = (
        canonical_analysis.get("slides")
        if isinstance(canonical_analysis.get("slides"), list)
        else []
    )
    mapped_units: list[dict[str, Any]] = []
    for slide_index, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        for unit_index, unit in enumerate(_iter_slide_units(slide)):
            mapped_units.append(
                _unit_record(
                    report_id=report_id,
                    slide=slide,
                    slide_index=slide_index,
                    unit=unit,
                    unit_index=unit_index,
                )
            )
    return mapped_units


def _result_record(
    *,
    report_id: str,
    result_type: str,
    source_index: int,
    raw_result: dict[str, Any],
) -> dict[str, Any]:
    result_id = (
        f"{report_id}:{result_type}:{source_index}:"
        f"{_stable_hash([raw_result.get('claim_text'), raw_result.get('claim_family')])}"
    )
    details = (
        raw_result.get("details") if isinstance(raw_result.get("details"), dict) else {}
    )
    return {
        "result_id": result_id,
        "report_id": report_id,
        "result_type": result_type,
        "source_index": source_index,
        "status": raw_result.get("status"),
        "claim_family": raw_result.get("claim_family"),
        "claim_text": raw_result.get("claim_text"),
        "slide_id": raw_result.get("slide_id"),
        "slide_number": raw_result.get("slide_number"),
        "page_number": raw_result.get("page_number"),
        "source_kind": raw_result.get("source_kind"),
        "block_id": raw_result.get("block_id"),
        "block_type": raw_result.get("block_type"),
        "entity": raw_result.get("entity"),
        "file": raw_result.get("file"),
        "details": details,
        "has_details": bool(details),
        "has_observed_values": isinstance(details.get("observed_values"), dict),
        "has_expected_values": isinstance(details.get("expected"), dict)
        or isinstance(details.get("package_values"), dict),
        "matched_unit_id": None,
        "raw_result": raw_result,
    }


def _collect_deterministic_results(
    *, report_id: str, validation_payload: dict[str, Any]
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for result_type, key in (
        ("caught", "claims"),
        ("unresolved", "unresolved"),
        ("non_claim", "non_claims"),
        ("mapping_issue", "mapping_issues"),
        ("image_region", "image_regions"),
    ):
        raw_items = validation_payload.get(key)
        if not isinstance(raw_items, list):
            continue
        for source_index, raw_result in enumerate(raw_items):
            if isinstance(raw_result, dict):
                results.append(
                    _result_record(
                        report_id=report_id,
                        result_type=result_type,
                        source_index=source_index,
                        raw_result=raw_result,
                    )
                )
    return results


def _attach_results_to_units(
    *,
    mapped_units: list[dict[str, Any]],
    deterministic_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    unit_lookup: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for unit in mapped_units:
        key = _unit_match_key(
            text=unit.get("text"),
            slide_number=unit.get("slide_number"),
            source_kind=unit.get("source_kind"),
            block_id=unit.get("block_id"),
        )
        unit_lookup.setdefault(key, []).append(unit)

    unmatched: list[dict[str, Any]] = []
    for result in deterministic_results:
        key = _unit_match_key(
            text=result.get("claim_text"),
            slide_number=result.get("slide_number"),
            source_kind=result.get("source_kind"),
            block_id=result.get("block_id"),
        )
        candidates = unit_lookup.get(key, [])
        if not candidates:
            unmatched.append(result)
            continue
        matched_unit = candidates[0]
        result["matched_unit_id"] = matched_unit["unit_id"]
        matched_unit["deterministic_result_ids"].append(result["result_id"])
        if result["result_type"] == "caught":
            matched_unit["deterministic_status"] = "caught"
        elif result["result_type"] in {"non_claim", "mapping_issue"}:
            matched_unit["deterministic_status"] = result["result_type"]
        elif matched_unit["deterministic_status"] == "uncaught":
            matched_unit["deterministic_status"] = "unresolved"
    return unmatched


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        return []


def _row_matches_entity(row: dict[str, str], entity: str) -> bool:
    canonical_entity = _canonical_text(entity)
    if not canonical_entity:
        return False
    preferred_columns = (
        "bundle_label",
        "product_name",
        "brand",
        "entity",
        "name",
        "attribute",
        "segment",
    )
    for column in preferred_columns:
        if column in row and _canonical_text(row.get(column)) == canonical_entity:
            return True
    return any(_canonical_text(value) == canonical_entity for value in row.values())


def _candidate_package_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    details = result.get("details") if isinstance(result.get("details"), dict) else {}
    records: list[dict[str, Any]] = []
    for detail_key in ("candidate_evaluations", "expected_candidates"):
        candidates = details.get(detail_key)
        if not isinstance(candidates, list):
            continue
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                continue
            file_name = _normalize_text(candidate.get("file"))
            package_values = candidate.get("package_values")
            if not file_name or not isinstance(package_values, dict):
                continue
            records.append(
                {
                    "file": file_name,
                    "entity": _normalize_text(result.get("entity")) or None,
                    "matched_rows": [package_values],
                    "detail_source": detail_key,
                    "detail_index": index,
                }
            )
    return records


def _nested_row_dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        rows: list[dict[str, Any]] = []
        for nested_value in value.values():
            rows.extend(_nested_row_dicts(nested_value))
        return rows
    return []


def _row_support_package_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    details = result.get("details") if isinstance(result.get("details"), dict) else {}
    row_support = details.get("row_support")
    if not isinstance(row_support, list):
        return []
    records: list[dict[str, Any]] = []
    for index, support in enumerate(row_support):
        if not isinstance(support, dict):
            continue
        file_name = _normalize_text(support.get("source_file") or support.get("file"))
        if not file_name:
            continue
        rows = [
            row
            for key, value in support.items()
            if key not in {"source_file", "file"}
            for row in _nested_row_dicts(value)
        ][:MAX_PACKAGE_EVIDENCE_ROWS]
        records.append(
            {
                "file": file_name,
                "entity": _normalize_text(result.get("entity")) or None,
                "matched_rows": rows,
                "detail_source": "row_support",
                "detail_index": index,
            }
        )
    return records


def _package_records_from_result_details(
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        *_candidate_package_records(result),
        *_row_support_package_records(result),
    ]


def _add_recorded_package_dir_candidates(
    candidates: list[Path],
    *,
    raw_package_dir: Any,
    package_root: Path,
) -> None:
    if not isinstance(raw_package_dir, str) or not raw_package_dir:
        return
    recorded_path = Path(raw_package_dir)
    candidates.append(recorded_path)
    marker = DEFAULT_PACKAGE_ROOT.parts
    recorded_parts = recorded_path.parts
    for index in range(len(recorded_parts) - len(marker) + 1):
        if recorded_parts[index : index + len(marker)] != marker:
            continue
        suffix = recorded_parts[index + len(marker) :]
        if suffix:
            candidates.append(package_root.joinpath(*suffix))
        return


def _add_resolver_package_dir_candidates(
    candidates: list[Path],
    *,
    resolver: Any,
    package_root: Path,
) -> None:
    if not isinstance(resolver, dict):
        return
    _add_recorded_package_dir_candidates(
        candidates,
        raw_package_dir=resolver.get("package_dir"),
        package_root=package_root,
    )
    retailer = _normalize_text(resolver.get("package_retailer"))
    category_key = _normalize_text(resolver.get("package_category_key"))
    if retailer and category_key:
        candidates.append(package_root / category_key / retailer)
        candidates.append(package_root / retailer / category_key)


def _first_existing_dir(candidates: list[Path]) -> Path | None:
    seen: set[Path] = set()
    for candidate in candidates:
        normalized = candidate.expanduser()
        cache_key = normalized.resolve()
        if cache_key in seen:
            continue
        seen.add(cache_key)
        if _safe_exists(normalized) and normalized.is_dir():
            return normalized
    return None


def _resolve_package_dir(
    *,
    validation_payload: dict[str, Any],
    package_root: Path,
    reports_dir: Path,
    report_id: str,
    cache_id: str,
) -> Path | None:
    candidates: list[Path] = []
    _add_recorded_package_dir_candidates(
        candidates,
        raw_package_dir=validation_payload.get("package_dir"),
        package_root=package_root,
    )
    _add_resolver_package_dir_candidates(
        candidates,
        resolver=validation_payload.get("resolver"),
        package_root=package_root,
    )
    candidates.extend([package_root / report_id, package_root / cache_id])
    resolved_candidate = _first_existing_dir(candidates)
    if resolved_candidate is not None:
        return resolved_candidate

    pdf_path = reports_dir / f"{report_id}.pdf"
    if not pdf_path.exists() and report_id != cache_id:
        pdf_path = reports_dir / f"{cache_id}.pdf"
    if pdf_path.exists():
        resolved_ref, _details = resolve_launch_package_for_pdf(
            pdf_path,
            package_roots=(package_root,),
        )
        if resolved_ref is not None:
            return resolved_ref.package_dir
    return None


def _collect_package_evidence(
    *,
    validation_payload: dict[str, Any],
    deterministic_results: list[dict[str, Any]],
    package_root: Path,
    reports_dir: Path,
    report_id: str,
    cache_id: str,
) -> dict[str, Any]:
    package_dir = _resolve_package_dir(
        validation_payload=validation_payload,
        package_root=package_root,
        reports_dir=reports_dir,
        report_id=report_id,
        cache_id=cache_id,
    )
    evidence = {
        "package_dir": str(package_dir) if package_dir else None,
        "records": [],
        "notes": [],
    }
    if package_dir is None:
        evidence["notes"].append(
            "Package directory was not available locally; evidence is limited to validation output."
        )
        return evidence

    for result in deterministic_results:
        file_name = _normalize_text(result.get("file"))
        entity = _normalize_text(result.get("entity"))
        detail_records = _package_records_from_result_details(result)
        for detail_record in detail_records:
            evidence["records"].append(
                {
                    "result_id": result["result_id"],
                    "file": detail_record["file"],
                    "entity": detail_record["entity"],
                    "matched_rows": detail_record["matched_rows"],
                    "detail_source": detail_record["detail_source"],
                    "detail_index": detail_record["detail_index"],
                    "note": (
                        None
                        if detail_record["matched_rows"]
                        else "No package rows were included in the result details."
                    ),
                }
            )
        if not file_name:
            continue
        csv_path = package_dir / file_name
        rows = _read_csv_rows(csv_path)
        if not rows:
            evidence["records"].append(
                {
                    "result_id": result["result_id"],
                    "file": file_name,
                    "entity": entity or None,
                    "matched_rows": [],
                    "note": "CSV file was missing or empty.",
                }
            )
            continue
        matched_rows = [
            row for row in rows if entity and _row_matches_entity(row, entity)
        ][:MAX_PACKAGE_EVIDENCE_ROWS]
        evidence["records"].append(
            {
                "result_id": result["result_id"],
                "file": file_name,
                "entity": entity or None,
                "matched_rows": matched_rows,
                "note": (
                    None if matched_rows else "No package row matched the cited entity."
                ),
            }
        )
    return evidence


def _reading_completeness(
    *,
    cache_dir: Path,
    analysis_payload: dict[str, Any],
) -> dict[str, Any]:
    layout_path = cache_dir / "layout.json"
    ocr_path = cache_dir / "ocr.json"
    layout_payload = _read_json_object(layout_path) if layout_path.exists() else None
    ocr_payload = _read_json_object(ocr_path) if ocr_path.exists() else None
    return _build_reading_completeness_audit(
        layout_payload=layout_payload,
        ocr_payload=ocr_payload,
        analysis_payload=analysis_payload,
    )


def _instructions_markdown(report_id: str) -> str:
    return f"""# Pro Audit Prompt

You are auditing a deterministic validator for innovation monitoring report
decks. Read this prompt carefully before reading the JSON files.

Report under audit: `{report_id}`.

## Core Context

This project validates innovation monitoring report decks.

The source package is deterministic. The report deck text was generated by an
LLM from that deterministic package. The production validator checks the
LLM-generated report text against the deterministic package.

This package is not the production validator. This is a test-loop audit package.
Your job is to audit what the current deterministic validator did and define
structured expectations for the next deterministic Python implementation pass.

Do not decide whether the whole deck is good or bad.
Do not invent runtime validator behavior.
Do not write Python code.
Do not treat your own output as production validation truth.

Your output is a test oracle for development: it tells the engineers what the
deterministic validator should catch, reject, leave unresolved, or expose better.

## Important Distinction

- Production validator: deterministic runtime checker. It loads mapped deck
  text, checks reading completeness, runs Python filters/checkers, and returns
  auditable evidence.
- Test loop: iterative development process. It uses this Pro audit to inspect
  whether the deterministic validator behaved correctly on this report.

You are only participating in the test loop.

Use the JSON files in this package to audit what the current deterministic
validator did.

## Files

- `report_context.json`: report id, summary, reading completeness, and counts.
- `mapped_text_units.json`: all mapped OCR/layout/LLM text units.
- `deterministic_results.json`: current deterministic caught, unresolved,
  non-claim, OCR/layout mapping issue, and image-region results, including each
  result's visible `details` evidence when available.
- `caught_units.json`: mapped units currently caught as deterministic claims.
- `unresolved_units.json`: mapped units currently marked unresolved.
- `non_claim_units.json`: mapped units currently classified as non-claim text.
- `mapping_issue_units.json`: mapped units currently classified as OCR/layout
  mapping issues.
- `uncaught_units.json`: mapped units with no deterministic result.
- `image_regions.json`: image regions preserved separately without OCR
  interpretation.
- `package_evidence.json`: cited package rows where available.
- `unmatched_deterministic_results.json`: deterministic results that did not
  match a mapped text unit, often figure-region placeholders.
- `pro_output_schema.json`: required response shape.

## Terms

- mapped text unit: one OCR/layout/LLM-mapped text item from the report.
- caught unit: a mapped unit currently recognized by deterministic Python as a
  checked claim.
- unresolved unit: a mapped unit the current validator considered claim-like but
  could not check deterministically.
- uncaught unit: a mapped unit with no deterministic result.
- package evidence: deterministic package rows cited by the current validator.
  These rows may be incomplete or missing; do not hallucinate missing evidence.

`mapped_text_units.json` contains `unit_id`. Deterministic results refer back to
units through `matched_unit_id` or through each unit's
`deterministic_result_ids`.

## What To Audit

Audit caught units first. For every caught unit, decide whether the deterministic
validator behaved correctly:

- Is the text unit a real innovation-report claim or a false positive?
- Is the claim family/rule correct?
- Is the cited package source plausible for this claim?
- Is the observed value parsed from the text plausible?
- Is expected-value / denominator / tolerance evidence sufficient?
- Is the rule generic enough for this report type, or does it look
  overfitted/hard-coded to this wording?

Then audit unresolved and uncaught units:

- Is the text a real residual claim?
- Is it non-claim text?
- Is it an OCR/layout/mapping issue?
- If it is a real residual claim, what claim family should it belong to?
- Does it look computable from deterministic package data?
- What package data would be needed?

Also audit unmatched deterministic results where useful:

- If they are figure-region placeholders with no claim text, usually classify
  them as `ocr_layout_mapping_issue` or `missing_evidence`.
- If they indicate an actual text/mapping failure, flag `investigate_reading`.

## Evidence Rules

- If expected value, observed value, denominator, tolerance, or package row is
  missing from the current validator output, mark `evidence_sufficient` as
  false. Do not assume it is correct.
- First check `deterministic_results.json` result `details` for observed values,
  expected values, candidate rows, row support, thresholds, tolerances, and
  source rows before marking evidence as absent.
- If package evidence is present and clearly supports or contradicts the current
  deterministic result, say so briefly.
- If package evidence is absent, use null for source/value plausibility where
  needed and explain the evidence gap.
- Do not create new numeric definitions for vague terms unless you mark them as
  proposed deterministic definitions, not current truth.

## Classification Values

Use these classifications:

- `legitimate_deterministic_catch`
- `false_positive`
- `wrong_claim_family`
- `wrong_source_mapping`
- `missing_evidence`
- `residual_claim`
- `non_claim`
- `ocr_layout_mapping_issue`
- `other`

## Required Output

Return only JSON. Do not wrap it in Markdown.

Return JSON matching `pro_output_schema.json`.

Every audited mapped unit should appear in `audit_items`. If you cannot fully
decide an item, still include it with null fields and a short reason.

Use short reasons. Do not include hidden chain-of-thought.
"""


def _pro_output_schema(report_id: str) -> dict[str, Any]:
    return {
        "report_id": report_id,
        "audit_items": [
            {
                "unit_id": "string",
                "current_status": (
                    "caught | unresolved | non_claim | mapping_issue | uncaught"
                ),
                "is_real_claim": "true | false | null",
                "classification": (
                    "legitimate_deterministic_catch | false_positive | "
                    "wrong_claim_family | wrong_source_mapping | missing_evidence | "
                    "residual_claim | non_claim | ocr_layout_mapping_issue | other"
                ),
                "expected_claim_family": "string | null",
                "source_mapping_plausible": "true | false | null",
                "observed_value_plausible": "true | false | null",
                "evidence_sufficient": "true | false | null",
                "rule_generic_enough": "true | false | null",
                "should_be_deterministic": "true | false | null",
                "package_data_needed": ["string"],
                "evidence_gaps": ["string"],
                "proposed_deterministic_definition": "string | null",
                "reason": "short explanation",
            }
        ],
        "unmatched_result_audits": [
            {
                "result_id": "string",
                "classification": (
                    "missing_evidence | ocr_layout_mapping_issue | "
                    "investigate_reading | other"
                ),
                "reason": "short explanation",
            }
        ],
        "implementation_recommendations": [
            {
                "recommendation_type": (
                    "fix_filter | fix_mapping | add_filter | add_checker | "
                    "add_evidence | keep_unresolved | investigate_reading"
                ),
                "affected_unit_ids": ["string"],
                "description": "short explanation",
            }
        ],
    }


def _write_report_package(
    *,
    report_id: str,
    cache_id: str,
    validation_payload: dict[str, Any],
    analysis_payload: dict[str, Any],
    cache_dir: Path,
    output_dir: Path,
    package_root: Path,
    reports_dir: Path,
) -> dict[str, Any]:
    mapped_units = _collect_mapped_units(
        report_id=report_id,
        analysis_payload=analysis_payload,
    )
    deterministic_results = _collect_deterministic_results(
        report_id=report_id,
        validation_payload=validation_payload,
    )
    unmatched_results = _attach_results_to_units(
        mapped_units=mapped_units,
        deterministic_results=deterministic_results,
    )
    caught_units = [
        unit for unit in mapped_units if unit["deterministic_status"] == "caught"
    ]
    unresolved_units = [
        unit for unit in mapped_units if unit["deterministic_status"] == "unresolved"
    ]
    non_claim_units = [
        unit for unit in mapped_units if unit["deterministic_status"] == "non_claim"
    ]
    mapping_issue_units = [
        unit for unit in mapped_units if unit["deterministic_status"] == "mapping_issue"
    ]
    uncaught_units = [
        unit for unit in mapped_units if unit["deterministic_status"] == "uncaught"
    ]
    image_regions = (
        validation_payload.get("image_regions")
        if isinstance(validation_payload.get("image_regions"), list)
        else []
    )
    reading_completeness = _reading_completeness(
        cache_dir=cache_dir,
        analysis_payload=analysis_payload,
    )
    package_evidence = _collect_package_evidence(
        validation_payload=validation_payload,
        deterministic_results=deterministic_results,
        package_root=package_root,
        reports_dir=reports_dir,
        report_id=report_id,
        cache_id=cache_id,
    )
    report_output_dir = output_dir / report_id
    report_output_dir.mkdir(parents=True, exist_ok=True)
    _clear_existing_report_package(report_output_dir)
    context = {
        "report_id": report_id,
        "cache_id": cache_id,
        "validation_status": validation_payload.get("status"),
        "validation_summary": validation_payload.get("summary"),
        "reading_quality": validation_payload.get("reading_quality"),
        "reading_completeness": reading_completeness,
        "counts": {
            "mapped_unit_count": len(mapped_units),
            "deterministic_result_count": len(deterministic_results),
            "caught_unit_count": len(caught_units),
            "unresolved_unit_count": len(unresolved_units),
            "non_claim_unit_count": len(non_claim_units),
            "mapping_issue_unit_count": len(mapping_issue_units),
            "uncaught_unit_count": len(uncaught_units),
            "image_region_count": len(image_regions),
            "unmatched_result_count": len(unmatched_results),
        },
    }
    (report_output_dir / "prompt.md").write_text(
        _instructions_markdown(report_id),
        encoding="utf-8",
    )
    _write_json(report_output_dir / "report_context.json", context)
    _write_json(report_output_dir / "mapped_text_units.json", mapped_units)
    _write_json(
        report_output_dir / "deterministic_results.json",
        deterministic_results,
    )
    _write_json(report_output_dir / "caught_units.json", caught_units)
    _write_json(report_output_dir / "unresolved_units.json", unresolved_units)
    _write_json(report_output_dir / "non_claim_units.json", non_claim_units)
    _write_json(report_output_dir / "mapping_issue_units.json", mapping_issue_units)
    _write_json(report_output_dir / "uncaught_units.json", uncaught_units)
    _write_json(report_output_dir / "image_regions.json", image_regions)
    _write_json(
        report_output_dir / "unmatched_deterministic_results.json", unmatched_results
    )
    _write_json(report_output_dir / "package_evidence.json", package_evidence)
    _write_json(
        report_output_dir / "pro_output_schema.json", _pro_output_schema(report_id)
    )
    data_only_zip = output_dir / f"{report_id}_data_only.zip"
    with zipfile.ZipFile(
        data_only_zip, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for filename in DATA_ONLY_FILENAMES:
            archive.write(report_output_dir / filename, arcname=filename)
    return {
        "report_id": report_id,
        "cache_id": cache_id,
        "status": "written",
        "output_dir": str(report_output_dir),
        "prompt_path": str(report_output_dir / "prompt.md"),
        "data_only_zip": str(data_only_zip),
        **context["counts"],
        "reading_completeness_status": reading_completeness.get("status"),
    }


def build_pro_audit_packages(
    *,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    validation_dir: Path = DEFAULT_VALIDATION_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    package_root: Path = DEFAULT_PACKAGE_ROOT,
    report_ids: list[str] | None = None,
    run_id: str | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build Pro audit packages from cached reading artifacts and validation JSON."""

    generated = generated_at or datetime.now(UTC)
    run_name = run_id or generated.strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / run_name
    reading_cache_dir = reports_dir / READING_CACHE_DIRNAME
    validation_by_cache_id = _validation_files_by_cache_id(validation_dir)
    selected_report_ids = report_ids or _report_ids_from_validation_dir(validation_dir)

    reports: list[dict[str, Any]] = []
    for requested_report_id in selected_report_ids:
        requested_cache_id = requested_report_id.strip() or "launch-report"
        validation_path = validation_by_cache_id.get(
            requested_cache_id
        ) or validation_by_cache_id.get(_canonical_text(requested_cache_id))
        if validation_path is None:
            raise ValueError(
                f"No validation artifact found for report {requested_report_id!r}."
            )
        report_id = _validation_report_id(validation_path)
        cache_id = report_id.strip() or "launch-report"
        cache_dir = reading_cache_dir / cache_id
        analysis_path = cache_dir / "slide_analysis.json"
        if not analysis_path.exists():
            raise ValueError(
                f"No cached slide_analysis.json found for report {report_id!r} "
                f"at {analysis_path}."
            )
        reports.append(
            _write_report_package(
                report_id=report_id,
                cache_id=cache_id,
                validation_payload=_read_json_object(validation_path),
                analysis_payload=_read_json_object(analysis_path),
                cache_dir=cache_dir,
                output_dir=run_dir,
                package_root=package_root,
                reports_dir=reports_dir,
            )
        )

    summary = {
        "run_id": run_name,
        "generated_at": generated.isoformat(),
        "reports_dir": str(reports_dir),
        "validation_dir": str(validation_dir),
        "reading_cache_dir": str(reading_cache_dir),
        "output_dir": str(run_dir),
        "report_count": len(reports),
        "reports": reports,
    }
    _write_json(run_dir / "index.json", summary)
    return summary


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(levelname)s:%(name)s:%(message)s",
    )
    summary = build_pro_audit_packages(
        reports_dir=args.reports_dir,
        validation_dir=args.validation_dir,
        output_dir=args.output_dir,
        package_root=args.package_root,
        report_ids=args.reports or None,
        run_id=args.run_id,
    )
    LOGGER.info(
        "Wrote Pro audit package for %s report(s) under %s.",
        summary["report_count"],
        summary["output_dir"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
