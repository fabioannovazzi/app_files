"""Bind model-written research records to the artifacts actually reviewed.

Fixed checks enforce declared issue treatment, references and file hashes.
They cannot judge legal support, research completeness or stopping quality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

__all__ = ["bind_research_record", "verify_research_record", "main"]

MODULE_ROOT = Path(__file__).resolve().parents[1]
for _vendor_root in (
    MODULE_ROOT / "vendor" / "modules",
    MODULE_ROOT.parent.parent / "vendor" / "modules",
    MODULE_ROOT.parent / "_shared" / "vendor" / "modules",
):
    if (_vendor_root / "vera_assurance").is_dir():
        sys.path.insert(0, str(_vendor_root))
        break

from vera_assurance import (  # noqa: E402
    AssuranceContractError,
    load_client_engagement_context_file,
)

METHOD = "shared_agentic_legal_tax_research"
RECORD = "research_review.json"
ISSUE_STATUSES = {
    "open",
    "resolved",
    "qualified",
    "evidence_limited",
    "professional_review",
}


def _file(root: Path, relative: str) -> Path:
    """Keep mechanical artifact inspection within a nonsymlink run path."""
    path = Path(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"Invalid research artifact path: {relative}")
    current = root
    if root.is_symlink():
        raise ValueError("Symlink run rejected")
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Symlink research artifact rejected: {relative}")
    if not current.resolve().is_relative_to(root.resolve()) or not current.is_file():
        raise ValueError(f"Research artifact missing or outside run: {relative}")
    return current


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def _text(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing research explanation: {label}")


def _strings(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"Expected research reference list: {label}")
    return value


def _entries(value: object, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"Missing research entries: {label}")
    result: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"Invalid research entry: {label}")
        identifier = item.get("id")
        _text(identifier, f"{label}.id")
        if identifier in result:
            raise ValueError(f"Duplicate research identifier: {identifier}")
        result[identifier] = item
    return result


def _validate_record(record: dict[str, Any]) -> None:
    """Check declared consistency without evaluating any semantic assessment."""
    if record.get("schema_version") != "1.0" or record.get("method") != METHOD:
        raise ValueError("Unsupported research record schema or method")
    cycles = _entries(record.get("cycles"), "cycles")
    issues = _entries(record.get("issues"), "issues")
    for identifier, cycle in cycles.items():
        for field in ("purpose", "findings", "validation", "challenge"):
            _text(cycle.get(field), f"{identifier}.{field}")
        refs = _strings(cycle.get("issue_ids"), f"{identifier}.issue_ids")
        if not refs or set(refs) - issues.keys():
            raise ValueError(f"Unresolved cycle issue references: {identifier}")
    limited = False
    for identifier, issue in issues.items():
        _text(issue.get("question"), f"{identifier}.question")
        status = issue.get("status")
        if not isinstance(status, str) or status not in ISSUE_STATUSES:
            raise ValueError(f"Invalid declared issue status: {identifier}")
        if status == "open":
            raise ValueError(f"Open research issue: {identifier}")
        _text(issue.get("treatment"), f"{identifier}.treatment")
        _strings(issue.get("evidence"), f"{identifier}.evidence")
        limits = _strings(issue.get("limits"), f"{identifier}.limits")
        refs = _strings(issue.get("cycle_ids"), f"{identifier}.cycle_ids")
        if not refs or set(refs) - cycles.keys():
            raise ValueError(f"Unresolved issue cycle references: {identifier}")
        if any(identifier not in cycles[ref]["issue_ids"] for ref in refs):
            raise ValueError(f"Issue not addressed by referenced cycle: {identifier}")
        if any(
            cycle_id not in refs
            for cycle_id, cycle in cycles.items()
            if identifier in cycle["issue_ids"]
        ):
            raise ValueError(
                f"Cycle treatment missing from issue history: {identifier}"
            )
        if status in {"qualified", "evidence_limited", "professional_review"}:
            if not limits:
                raise ValueError(f"Declared issue limits missing: {identifier}")
        limited |= status == "evidence_limited"
    completion = record.get("completion")
    if not isinstance(completion, dict):
        raise ValueError("Missing research completion assessment")
    status = completion.get("status")
    if not isinstance(status, str) or status not in {"complete", "evidence_limited"}:
        raise ValueError("Research remains in progress or interrupted")
    _text(completion.get("coverage_review"), "completion.coverage_review")
    _text(completion.get("stopping_rationale"), "completion.stopping_rationale")
    limits = _strings(completion.get("limits"), "completion.limits")
    if limited and completion["status"] != "evidence_limited":
        raise ValueError("Evidence-limited issue conflicts with complete research")
    if completion["status"] == "evidence_limited" and not limits:
        raise ValueError("Evidence-limited research needs explicit limits")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_digest(record: dict[str, Any]) -> str:
    substantive = {key: value for key, value in record.items() if key != "binding"}
    return hashlib.sha256(
        json.dumps(substantive, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def bind_research_record(
    root: Path,
    *,
    answer: str,
    answer_contract: str,
    review: str,
    research_log: str = "research_record.md",
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """Snapshot declared research and exact reviewed artifacts after review."""
    path = _file(root, RECORD)
    record = _read(path)
    _validate_record(record)
    artifacts = [
        {"role": role, "path": relative, "sha256": _digest(_file(root, relative))}
        for role, relative in (
            ("answer", answer),
            ("answer_contract", answer_contract),
            ("review", review),
            ("research_log", research_log),
            *(("source", source) for source in (sources or [])),
        )
    ]
    if RECORD in {artifact["path"] for artifact in artifacts}:
        raise ValueError("Research record cannot bind itself as an artifact")
    record["binding"] = {
        "record_sha256": _record_digest(record),
        "artifacts": artifacts,
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return verify_research_record(root)


def verify_research_record(root: Path) -> dict[str, Any]:
    """Reject changed records, inputs or an inconsistent declared closure."""
    record = _read(_file(root, RECORD))
    _validate_record(record)
    binding = record.get("binding")
    if not isinstance(binding, dict) or binding.get("record_sha256") != _record_digest(
        record
    ):
        raise ValueError("Research record changed or has no artifact binding")
    artifacts = binding.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("Research artifact bindings missing")
    roles: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("Invalid research artifact binding")
        role, relative = artifact.get("role"), artifact.get("path")
        _text(role, "artifact.role")
        _text(relative, "artifact.path")
        roles.append(role)
        if relative == RECORD or _digest(_file(root, relative)) != artifact.get(
            "sha256"
        ):
            raise ValueError(f"Research artifact changed: {relative}")
    for role in ("answer", "answer_contract", "review", "research_log"):
        if roles.count(role) != 1:
            raise ValueError(
                f"Required research artifact role missing or repeated: {role}"
            )
    return {
        "record_integrity": "verified",
        "declared_research_status": record["completion"]["status"],
        "semantic_quality": "not_certified_by_helper",
        "artifact_count": len(artifacts),
    }


def main() -> int:
    """Use the existing managed review run; only binding writes artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("bind", "verify"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument("--answer")
    parser.add_argument("--answer-contract")
    parser.add_argument("--review")
    parser.add_argument("--research-log", default="research_record.md")
    parser.add_argument("--source-file", action="append", default=[])
    args = parser.parse_args()
    try:
        root = args.output_dir.expanduser().absolute()
        record_path = _file(root, RECORD)
        load_client_engagement_context_file(
            args.client_engagement,
            expected_workflow_id="deep-research-validator",
            input_paths=[record_path],
            output_dir=root,
            allowed_statuses=(
                ("running", "ready_for_review", "completed")
                if args.action == "verify"
                else ("running",)
            ),
        )
        if args.action == "bind":
            if not all((args.answer, args.answer_contract, args.review)):
                raise ValueError(
                    "Binding needs --answer, --answer-contract and --review"
                )
            result = bind_research_record(
                root,
                answer=args.answer,
                answer_contract=args.answer_contract,
                review=args.review,
                research_log=args.research_log,
                sources=args.source_file,
            )
        else:
            result = verify_research_record(root)
    except (OSError, ValueError, AssuranceContractError) as exc:
        parser.error(str(exc))
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("%s", json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
