#!/usr/bin/env python3
"""Validate and package Clara's model-authored advisory assignment contract.

The checks here are deterministic because schema shape, ID references, declared
workflow availability, literal-source preservation, hashes, and packaging are
mechanically verifiable. This module does not decide advisory meaning, scope,
evidence strategy, analytical framing, workflow selection, or professional
judgement, and it never calls a model API.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

__all__ = [
    "ContractValidationError",
    "inventory_literal_anchors",
    "load_contract",
    "package_advisory_contract",
    "validate_advisory_contract",
    "validate_literal_preservation",
]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PLUGIN_ROOT / "contracts" / "advisory_contract.v1.schema.json"
CANONICAL_FILENAME = "advisory_contract.json"
VALIDATION_FILENAME = "advisory_contract_validation.json"
PLANNER_WORKFLOW = "clara:advisory-brief-planner"
DEVELOPER_WORKFLOWS = frozenset({"clara:privacy-surface-review"})

URL_RE = re.compile(r"https?://[^\s)\]>\"']+", re.IGNORECASE)
DATE_RE = re.compile(
    r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b"
)
NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:EUR|USD|GBP|CHF|[$€£])?\s*"
    # Exact grouping avoids swallowing runs of independent large CSV integers.
    r"(?:\d{1,3}(?:,\d{3})+(?!\d)(?:\.\d+)?"
    r"|\d{1,3}(?:\.\d{3})+(?!\d)(?:,\d+)?"
    r"|(?<![,\d])\d+,\d+(?![\d,])"
    r"|\d+(?:\.\d+)?)"
    r"(?:\s*(?:%|EUR|USD|GBP|CHF))?",
    re.IGNORECASE,
)
QUESTION_RE = re.compile(
    r"(?:^|(?<=[.!?]))\s*([^.!?\n]{2,}\?)",
    re.MULTILINE,
)


class ContractValidationError(ValueError):
    """Raised when a contract or literal-source input is not valid JSON/text."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build a JSON object while rejecting duplicate keys."""

    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ContractValidationError(f"duplicate JSON field {key!r}")
        payload[key] = value
    return payload


def load_contract(path: Path) -> dict[str, Any]:
    """Load one UTF-8 contract object and reject duplicate JSON fields."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractValidationError(f"cannot read {path.name}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ContractValidationError(f"{path.name} is not valid UTF-8") from exc
    try:
        payload = json.loads(text, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as exc:
        raise ContractValidationError(f"invalid JSON in {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractValidationError(f"{path.name} must contain one JSON object")
    return payload


def _ordered_unique(values: Sequence[str]) -> list[str]:
    """Return values once, preserving first occurrence order."""

    return list(dict.fromkeys(value for value in values if value))


def _normalized_literal(value: str) -> str:
    """Normalize only whitespace for mechanical literal comparisons."""

    return " ".join(value.split())


def inventory_literal_anchors(text: str) -> dict[str, list[str]]:
    """Inventory mechanically recognizable literal anchors in source text."""

    return {
        "dates": _ordered_unique(DATE_RE.findall(text)),
        "numbers": _ordered_unique(
            _normalized_literal(match.group(0)) for match in NUMBER_RE.finditer(text)
        ),
        "urls": _ordered_unique(URL_RE.findall(text)),
        "explicit_questions": _ordered_unique(
            _normalized_literal(match.group(1)) for match in QUESTION_RE.finditer(text)
        ),
    }


def _schema() -> dict[str, Any]:
    """Load and meta-validate the published advisory contract schema."""

    schema = load_contract(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    return schema


def _known_handoff_workflows() -> set[str]:
    """Return mechanically available non-developer Clara handoff targets."""

    workflows = {
        f"clara:{skill_dir.name}"
        for skill_dir in (PLUGIN_ROOT / "skills").iterdir()
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file()
    }
    return workflows - DEVELOPER_WORKFLOWS - {PLANNER_WORKFLOW}


def _schema_errors(payload: Mapping[str, Any]) -> list[str]:
    """Return stable path-qualified JSON Schema errors."""

    validator = Draft202012Validator(_schema())
    errors: list[str] = []
    for error in sorted(
        validator.iter_errors(payload),
        key=lambda item: tuple(str(part) for part in item.path),
    ):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"schema {location}: {error.message}")
    return errors


def _duplicate_id_errors(items: Any, *, field: str) -> list[str]:
    """Return duplicate ID errors for a validated list of objects."""

    if not isinstance(items, list):
        return []
    ids = [item.get("id") for item in items if isinstance(item, dict)]
    duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
    return [f"{field} contains duplicate id {item_id!r}" for item_id in duplicates]


def validate_advisory_contract(
    payload: Mapping[str, Any],
    *,
    known_workflows: set[str] | None = None,
) -> list[str]:
    """Validate schema plus mechanically verifiable cross-field consistency."""

    errors = _schema_errors(payload)
    if errors:
        return errors

    workflows = (
        known_workflows if known_workflows is not None else _known_handoff_workflows()
    )
    selected = str(payload["selected_clara_workflow"])
    if selected not in workflows:
        errors.append(
            "selected_clara_workflow must name an available non-developer Clara "
            f"handoff workflow; found {selected!r}"
        )

    handoff = payload["generation_handoff"]
    if handoff["workflow"] != selected:
        errors.append("generation_handoff.workflow must equal selected_clara_workflow")

    available_inputs = payload["available_inputs"]
    errors.extend(_duplicate_id_errors(available_inputs, field="available_inputs"))
    errors.extend(
        _duplicate_id_errors(
            payload["evidence_requirements"], field="evidence_requirements"
        )
    )
    errors.extend(_duplicate_id_errors(payload["analysis_plan"], field="analysis_plan"))
    input_ids = {item["id"] for item in available_inputs}

    referenced_inputs: list[tuple[str, str]] = []
    for field in ("evidence_requirements", "analysis_plan"):
        for item in payload[field]:
            referenced_inputs.extend((field, value) for value in item["input_ids"])
    referenced_inputs.extend(
        ("generation_handoff", value) for value in handoff["input_ids"]
    )
    referenced_inputs.extend(
        ("source_facts", item["input_id"]) for item in payload["source_facts"]
    )
    referenced_inputs.extend(
        ("explicit_questions", item["input_id"])
        for item in payload["explicit_questions"]
    )
    for field, input_id in referenced_inputs:
        if input_id not in input_ids:
            errors.append(f"{field} references unknown available input {input_id!r}")

    handoff_input_ids = set(handoff["input_ids"])
    required_handoff_input_ids = {
        input_id
        for field, input_id in referenced_inputs
        if field != "generation_handoff"
    }
    missing_handoff_input_ids = sorted(required_handoff_input_ids - handoff_input_ids)
    if missing_handoff_input_ids:
        errors.append(
            "generation_handoff.input_ids must include every input referenced by "
            "evidence_requirements, analysis_plan, source_facts, and "
            "explicit_questions; missing "
            + ", ".join(repr(input_id) for input_id in missing_handoff_input_ids)
        )

    blocking_questions = [
        item for item in payload["unresolved_questions"] if item["blocking"]
    ]
    status = payload["contract_status"]
    if status == "ready_for_handoff" and blocking_questions:
        errors.append("ready_for_handoff cannot retain a blocking unresolved question")
    if status == "needs_clarification" and not blocking_questions:
        errors.append("needs_clarification requires a blocking unresolved question")

    review = payload["model_review"]
    review_statuses = [*review["dimensions"].values(), review["overall_status"]]
    if status == "ready_for_handoff" and any(
        review_status != "conforms" for review_status in review_statuses
    ):
        errors.append("ready_for_handoff requires every model_review status to conform")
    return errors


def validate_literal_preservation(
    payload: Mapping[str, Any],
    source_texts: Mapping[str, str],
) -> tuple[list[str], dict[str, dict[str, list[str]]]]:
    """Check model-declared exact anchors, typed literals, and questions."""

    errors: list[str] = []
    inventories: dict[str, dict[str, list[str]]] = {}
    facts_by_input: dict[str, list[Mapping[str, Any]]] = {}
    for fact in payload.get("source_facts", []):
        if isinstance(fact, dict):
            facts_by_input.setdefault(str(fact.get("input_id", "")), []).append(fact)
    questions_by_input: dict[str, list[str]] = {}
    for item in payload.get("explicit_questions", []):
        if isinstance(item, dict):
            questions_by_input.setdefault(str(item.get("input_id", "")), []).append(
                _normalized_literal(str(item.get("question", "")))
            )

    for input_id, source_text in source_texts.items():
        normalized_source = _normalized_literal(source_text)
        facts = facts_by_input.get(input_id, [])
        question_anchors = questions_by_input.get(input_id, [])
        inventory = inventory_literal_anchors(source_text)
        inventories[input_id] = inventory
        for fact in facts:
            anchor = _normalized_literal(str(fact.get("source_anchor", "")))
            if anchor and anchor not in normalized_source:
                errors.append(
                    f"source_facts anchor for {input_id!r} is not literal source text: {anchor!r}"
                )
                continue
            category = str(fact.get("category", ""))
            if category not in {"date", "number"}:
                continue
            literal_value = _normalized_literal(str(fact.get("literal_value", "")))
            inventory_key = f"{category}s"
            source_literals = {
                _normalized_literal(value) for value in inventory[inventory_key]
            }
            anchor_literals = {
                _normalized_literal(value)
                for value in inventory_literal_anchors(anchor)[inventory_key]
            }
            if (
                literal_value not in source_literals
                or literal_value not in anchor_literals
            ):
                errors.append(
                    f"source_facts {category} literal for {input_id!r} is not an "
                    f"exact recognized literal in its source anchor: {literal_value!r}"
                )
        for question in question_anchors:
            if question and question not in normalized_source:
                errors.append(
                    f"explicit_questions entry for {input_id!r} is not literal source text: {question!r}"
                )
    return errors, inventories


def _parse_source_specs(specs: Sequence[str]) -> dict[str, Path]:
    """Parse repeated INPUT_ID=PATH source arguments."""

    sources: dict[str, Path] = {}
    for spec in specs:
        input_id, separator, raw_path = spec.partition("=")
        if not separator or not input_id or not raw_path:
            raise ContractValidationError(
                f"invalid --source {spec!r}; expected INPUT_ID=PATH"
            )
        if input_id in sources:
            raise ContractValidationError(f"duplicate --source input id {input_id!r}")
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            raise ContractValidationError(f"source file does not exist: {path}")
        sources[input_id] = path
    return sources


def _sha256_bytes(value: bytes) -> str:
    """Return the lowercase SHA-256 digest for exact bytes."""

    return hashlib.sha256(value).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically write stable UTF-8 JSON with one trailing newline."""

    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _invalidate_prior_canonical(canonical_path: Path) -> dict[str, Any] | None:
    """Move a stale canonical artifact to a content-addressed recovery path."""

    if not canonical_path.exists():
        return None
    if not canonical_path.is_file():
        raise ContractValidationError(
            f"cannot invalidate non-file canonical artifact: {canonical_path}"
        )
    try:
        raw = canonical_path.read_bytes()
    except OSError as exc:
        raise ContractValidationError(
            f"cannot read prior canonical artifact: {canonical_path}"
        ) from exc
    digest = _sha256_bytes(raw)
    recovery_path = canonical_path.with_name(
        f"{canonical_path.stem}.previous-{digest[:12]}{canonical_path.suffix}"
    )
    if recovery_path.exists():
        try:
            recovery_bytes = recovery_path.read_bytes()
        except OSError as exc:
            raise ContractValidationError(
                f"cannot inspect canonical recovery artifact: {recovery_path}"
            ) from exc
        if recovery_bytes != raw:
            recovery_path = canonical_path.with_name(
                f"{canonical_path.stem}.previous-{digest}{canonical_path.suffix}"
            )
    if recovery_path.exists():
        canonical_path.unlink()
    else:
        canonical_path.replace(recovery_path)
    return {
        "filename": recovery_path.name,
        "sha256": digest,
        "reason": "A later packaging attempt failed, so this prior contract is not current.",
    }


def _write_failed_validation_report(
    output_dir: Path,
    errors: Sequence[str],
    *,
    source_receipts: Sequence[Mapping[str, Any]] = (),
    inventories: Mapping[str, Mapping[str, Sequence[str]]] | None = None,
) -> Path:
    """Invalidate any prior canonical contract and record the current failure."""

    resolved_output_dir = output_dir.resolve()
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    canonical_path = resolved_output_dir / CANONICAL_FILENAME
    report_path = resolved_output_dir / VALIDATION_FILENAME
    invalidated = _invalidate_prior_canonical(canonical_path)
    report: dict[str, Any] = {
        "schema_version": "clara.advisory_contract_validation.v1",
        "status": "failed",
        "canonical_artifact_written": False,
        "contract_sha256": None,
        "invalidated_prior_canonical": invalidated,
        "source_files": list(source_receipts),
        "literal_inventory": dict(inventories or {}),
        "errors": list(errors),
        "limitations": [
            "Schema and literal checks do not establish advisory correctness, evidence sufficiency, workflow suitability, or professional judgement.",
            "Whole-source literal inventories are observational. Materiality and completeness remain model-led; deterministic checks gate only declared source anchors, declared date and number literal values, and declared exact questions.",
        ],
    }
    _write_json(report_path, report)
    return report_path


def package_advisory_contract(
    draft_path: Path,
    output_dir: Path,
    *,
    source_paths: Mapping[str, Path] | None = None,
) -> tuple[Path | None, Path, list[str]]:
    """Validate a model-authored draft and write canonical package artifacts."""

    source_receipts: list[dict[str, Any]] = []
    inventories: dict[str, dict[str, list[str]]] = {}
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    canonical_path = output_dir / CANONICAL_FILENAME
    report_path = output_dir / VALIDATION_FILENAME
    try:
        payload = load_contract(draft_path)
        errors = validate_advisory_contract(payload)
        sources = dict(source_paths or {})
        declared_input_ids = {
            str(item.get("id"))
            for item in payload.get("available_inputs", [])
            if isinstance(item, dict)
        }
        source_texts: dict[str, str] = {}
        for input_id, path in sorted(sources.items()):
            if input_id not in declared_input_ids:
                errors.append(
                    f"--source references undeclared available input {input_id!r}"
                )
            try:
                raw = path.read_bytes()
            except OSError as exc:
                raise ContractValidationError(
                    f"cannot read source file for {input_id!r}: {path.name}"
                ) from exc
            try:
                source_texts[input_id] = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ContractValidationError(
                    f"source file for {input_id!r} is not UTF-8 text: {path.name}"
                ) from exc
            source_receipts.append(
                {
                    "input_id": input_id,
                    "filename": path.name,
                    "byte_count": len(raw),
                    "sha256": _sha256_bytes(raw),
                }
            )

        if not errors and source_texts:
            literal_errors, inventories = validate_literal_preservation(
                payload, source_texts
            )
            errors.extend(literal_errors)
    except ContractValidationError as exc:
        _write_failed_validation_report(
            output_dir,
            [str(exc)],
            source_receipts=source_receipts,
            inventories=inventories,
        )
        raise

    canonical_written = not errors
    if canonical_written:
        _write_json(canonical_path, payload)
    else:
        report_path = _write_failed_validation_report(
            output_dir,
            errors,
            source_receipts=source_receipts,
            inventories=inventories,
        )
        return None, report_path, errors

    report: dict[str, Any] = {
        "schema_version": "clara.advisory_contract_validation.v1",
        "status": "passed" if canonical_written else "failed",
        "canonical_artifact_written": canonical_written,
        "contract_sha256": _sha256_bytes(canonical_path.read_bytes()),
        "invalidated_prior_canonical": None,
        "source_files": source_receipts,
        "literal_inventory": inventories,
        "errors": errors,
        "limitations": [
            "Schema and literal checks do not establish advisory correctness, evidence sufficiency, workflow suitability, or professional judgement.",
            "Whole-source literal inventories are observational. Materiality and completeness remain model-led; deterministic checks gate only declared source anchors, declared date and number literal values, and declared exact questions.",
        ],
    }
    _write_json(report_path, report)
    return (canonical_path if canonical_written else None), report_path, errors


def _parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(
        description="Validate and package Clara's model-authored advisory contract."
    )
    parser.add_argument("draft_contract", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="INPUT_ID=PATH",
        help="Bind an available-input ID to exact UTF-8 source text; repeat as needed.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run validation and return a process exit code."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parser().parse_args(argv)
    try:
        sources = _parse_source_specs(args.source)
    except ContractValidationError as exc:
        try:
            report_path = _write_failed_validation_report(args.output_dir, [str(exc)])
        except (ContractValidationError, OSError) as report_exc:
            LOGGER.error("%s", report_exc)
        else:
            LOGGER.error("validation report: %s", report_path)
        LOGGER.error("%s", exc)
        return 2
    try:
        canonical_path, report_path, errors = package_advisory_contract(
            args.draft_contract.resolve(),
            args.output_dir,
            source_paths=sources,
        )
    except ContractValidationError as exc:
        LOGGER.error("%s", exc)
        return 2
    if errors:
        LOGGER.error("advisory contract failed validation; see %s", report_path)
        return 1
    LOGGER.info("advisory contract: %s", canonical_path)
    LOGGER.info("validation report: %s", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
