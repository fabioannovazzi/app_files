"""Bind model-written research records to the artifacts actually reviewed.

Fixed checks enforce declared issue treatment, references and file hashes.
They cannot judge legal support, research completeness or stopping quality.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any

__all__ = ["bind_research_record", "verify_research_record", "main"]

_evidence_spec = importlib.util.spec_from_file_location(
    "legal_tax_record_evidence", Path(__file__).with_name("evidence_refs.py")
)
if not _evidence_spec or not _evidence_spec.loader:
    raise RuntimeError("Evidence reference helper unavailable")
_evidence = importlib.util.module_from_spec(_evidence_spec)
_evidence_spec.loader.exec_module(_evidence)

_review_spec = importlib.util.spec_from_file_location(
    "legal_tax_closure_review", Path(__file__).with_name("package_validation.py")
)
if not _review_spec or not _review_spec.loader:
    raise RuntimeError("Final review helper unavailable")
_review = importlib.util.module_from_spec(_review_spec)
_review_spec.loader.exec_module(_review)

TREATMENT_REFERENCES = {
    "source_assessment": {"source_capture", "source_access"},
    "fact_confirmation": {"fact", "source_capture"},
    "scope_revision": {"scope", "answer_contract"},
    "calculation": {"calculation"},
    "claim_removal": {"claim"},
    "qualification": {"claim", "source_capture", "source_access", "fact"},
    "professional_judgment": {"claim", "inspection_note", "treatment_note"},
}

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


def _validate_record(
    record: dict[str, Any], root: Path | None = None
) -> list[tuple[str, Path]]:
    """Check declared consistency without evaluating any semantic assessment."""
    if record.get("schema_version") != "2.0" or record.get("method") != METHOD:
        raise ValueError("Unsupported research record schema or method")
    referenced: list[tuple[str, Path]] = []
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
        treatment_type = issue.get("treatment_type")
        if (
            not isinstance(treatment_type, str)
            or treatment_type not in TREATMENT_REFERENCES
        ):
            raise ValueError(f"Declared treatment type missing: {identifier}")
        evidence = issue.get("evidence")
        if (
            not isinstance(evidence, list)
            or not evidence
            or any(not isinstance(ref, dict) for ref in evidence)
        ):
            raise ValueError(f"Structured treatment evidence missing: {identifier}")
        if not any(
            isinstance(ref.get("kind"), str)
            and ref["kind"] in TREATMENT_REFERENCES[treatment_type]
            for ref in evidence
        ):
            raise ValueError(
                f"Treatment requires its declared evidence kind: {identifier}"
            )
        effects = issue.get("effects")
        if (
            not isinstance(effects, list)
            or not effects
            or any(
                not isinstance(ref, dict)
                or not isinstance(ref.get("kind"), str)
                or ref.get("kind")
                not in {"claim", "answer", "answer_contract", "scope"}
                for ref in effects
            )
        ):
            raise ValueError(f"Reviewed treatment effect missing: {identifier}")
        dependencies = _strings(issue.get("dependencies"), f"{identifier}.dependencies")
        if identifier in dependencies or set(dependencies) - issues.keys():
            raise ValueError(f"Unresolved issue dependencies: {identifier}")
        _text(issue.get("dependency_review"), f"{identifier}.dependency_review")
        if root is not None:
            for reference in [*evidence, *effects]:
                paths = _evidence.validate_reference(root, reference)
                inventory = reference.get("inventory")
                for path in paths:
                    role = (
                        "source"
                        if reference["kind"] == "source_capture"
                        and path != (_file(root, inventory) if inventory else None)
                        else "issue_reference"
                    )
                    referenced.append((role, path))
                if inventory:
                    parent = _file(root, inventory).parent
                    for name in (
                        "source_inventory.json",
                        "source_capture_manifest.json",
                    ):
                        path = parent / name
                        if path.is_file():
                            referenced.append(
                                (
                                    "source_inventory",
                                    _file(root, path.relative_to(root).as_posix()),
                                )
                            )
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
    _text(record.get("answer_revision_sha256"), "answer_revision_sha256")
    return referenced


def _reviewed_effects(
    record: dict[str, Any], root: Path, answer: str, answer_contract: str, review: str
) -> list[tuple[str, Path]]:
    digest = _evidence.verify_answer_identity(_file(root, answer), _file(root, review))
    if record["answer_revision_sha256"] != digest:
        raise ValueError("Research treatments refer to a different answer revision")
    targets = {
        "answer": answer,
        "claim": review,
        "answer_contract": answer_contract,
        "scope": answer_contract,
    }
    for issue in record["issues"]:
        for reference in issue["effects"]:
            if reference["sha256"] != _digest(_file(root, targets[reference["kind"]])):
                raise ValueError(
                    "Treatment effect does not identify the current reviewed revision"
                )
    review_dir = _file(root, review).parent
    inventories = [
        _file(root, (review_dir / name).relative_to(root).as_posix())
        for name in ("document_inventory.json", "source_inventory.json")
    ]
    audit = _review.build_audit(
        _read(inventories[0]),
        _read(inventories[1]),
        _read(_file(root, review)),
        _read(_file(root, answer_contract)),
        source_base_dir=review_dir,
    )
    if (
        audit["record_integrity_status"] != "record_complete"
        or audit["delivery_readiness"] == "revision_required"
    ):
        raise ValueError("Research closure requires a complete final answer review")
    limited = bool(
        audit["evidence_limited_claim_indices"]
        or audit["source_fidelity_limited_claim_indices"]
        or audit["blocked_treatment_claim_indices"]
        or audit["coverage_scope"] != "all_material_claims"
    )
    if limited and record["completion"]["status"] != "evidence_limited":
        raise ValueError("Final review limits must remain visible in research closure")
    if audit["delivery_readiness"] == "professional_review_required" and not any(
        issue["status"] == "professional_review" for issue in record["issues"]
    ):
        raise ValueError(
            "Final professional judgment must remain open for professional review"
        )
    consumed = [("review_input", path) for path in inventories]
    for source in _read(inventories[1]).get("sources", []):
        for capture in [source, *source.get("capture_history", [])]:
            for field in ("captured_text_path", "captured_original_path"):
                if capture.get(field):
                    path = review_dir / capture[field]
                    consumed.append(
                        ("source", _file(root, path.relative_to(root).as_posix()))
                    )
    return consumed


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
    root = root.resolve(strict=True)
    path = _file(root, RECORD)
    record = _read(path)
    # Check authorized artifact paths before following model-written references.
    for relative in (answer, answer_contract, review, research_log, *(sources or [])):
        _file(root, relative)
    referenced = _validate_record(record, root)
    referenced.extend(_reviewed_effects(record, root, answer, answer_contract, review))
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
    seen = {artifact["path"] for artifact in artifacts}
    for role, artifact_path in referenced:
        relative = artifact_path.relative_to(root).as_posix()
        if relative not in seen:
            artifacts.append(
                {"role": role, "path": relative, "sha256": _digest(artifact_path)}
            )
            seen.add(relative)
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
    root = root.resolve(strict=True)
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
    selected = {item["role"]: item["path"] for item in artifacts}
    _validate_record(record, root)
    _reviewed_effects(
        record,
        root,
        selected["answer"],
        selected["answer_contract"],
        selected["review"],
    )
    return {
        "record_integrity": "verified",
        "declared_research_status": record["completion"]["status"],
        "semantic_quality": "not_certified_by_helper",
        "artifact_count": len(artifacts),
    }


def main() -> int:
    """Use the existing managed review run for binding and native UI projection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("bind", "verify", "review-ui"))
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
        context = load_client_engagement_context_file(
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
        elif args.action == "review-ui":
            from pipeline_review import write_pipeline_review

            result = write_pipeline_review(root, context)
        else:
            result = verify_research_record(root)
    except (OSError, ValueError, AssuranceContractError) as exc:
        parser.error(str(exc))
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("%s", json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
