"""Verify that one Clara case HTML deck is mechanically ready for delivery."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any, Mapping

__all__ = ["verify_advisory_html_delivery", "main"]

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = "clara.advisory_html_delivery.v1"
READY_STATUSES = {"ready", "ready_with_residual_uncertainty"}
EVIDENCE_REGISTER_FILENAME = "advisory_evidence_register.json"
CLAIM_REGISTER_FILENAME = "advisory_claim_register.json"
WORKPAPER_CHECKPOINT_FILENAME = "advisory_workpaper_checkpoint.json"
LINEAGE_SCRIPT_PATH = Path(__file__).with_name("advisory_evidence_lineage.py")


class AdvisoryHTMLDeliveryError(ValueError):
    """Raised when delivery-gate inputs cannot be inspected safely."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdvisoryHTMLDeliveryError(
            f"cannot read JSON artifact {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise AdvisoryHTMLDeliveryError(f"JSON artifact must be an object: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _lineage_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "clara_advisory_html_delivery_lineage", LINEAGE_SCRIPT_PATH
    )
    if spec is None or spec.loader is None:
        raise AdvisoryHTMLDeliveryError(
            f"cannot load advisory lineage helper: {LINEAGE_SCRIPT_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _semantic_claim_register_sha256(payload: Mapping[str, Any]) -> str:
    semantic_payload = json.loads(json.dumps(payload))
    claims = semantic_payload.get("claims", [])
    if isinstance(claims, list):
        for claim in claims:
            if isinstance(claim, dict):
                claim["appearances"] = []
    canonical = json.dumps(
        semantic_payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _html_result(payload: Mapping[str, Any]) -> tuple[str, bool, str | None] | None:
    input_record = payload.get("input")
    input_sha256 = (
        str(input_record.get("sha256"))
        if isinstance(input_record, dict) and input_record.get("sha256")
        else None
    )
    if "browser" in payload and "viewports" in payload:
        return "html_browser_qa", payload.get("result") == "pass", input_sha256
    if "deck" in payload and "checks" in payload and "summary" in payload:
        return "html_static_validation", payload.get("result") == "pass", input_sha256
    return None


def verify_advisory_html_delivery(
    case_dir: Path,
    deck: Path,
    validation_audit_path: Path,
) -> dict[str, Any]:
    """Return a fail-closed receipt over current case and delivery artifacts.

    The active model and partner remain responsible for semantic support and
    readiness. This function only checks exact bytes, declared IDs, current
    lineage state, and authoritative workflow result records.
    """

    resolved_case = case_dir.expanduser().resolve()
    resolved_deck = deck.expanduser().resolve()
    resolved_audit = validation_audit_path.expanduser().resolve()
    if not resolved_deck.is_file():
        raise AdvisoryHTMLDeliveryError(f"HTML deck does not exist: {resolved_deck}")
    if resolved_deck.suffix.casefold() not in {".html", ".htm"}:
        raise AdvisoryHTMLDeliveryError("delivery gate requires an HTML deck")
    if not resolved_audit.is_file():
        raise AdvisoryHTMLDeliveryError(
            f"validation audit does not exist: {resolved_audit}"
        )

    deck_sha256 = _sha256(resolved_deck)
    deck_byte_count = resolved_deck.stat().st_size
    errors: list[str] = []
    checks: list[dict[str, str]] = []

    def check(code: str, condition: bool, success: str, failure: str) -> None:
        checks.append(
            {
                "code": code,
                "status": "pass" if condition else "fail",
                "message": success if condition else failure,
            }
        )
        if not condition:
            errors.append(failure)

    audit = _load_json(resolved_audit)
    audit_deliverable = audit.get("deliverable")
    check(
        "validator.record_complete",
        audit.get("record_complete") is True,
        "The advisory validator record is mechanically complete.",
        "The advisory validator record is not mechanically complete.",
    )
    check(
        "validator.delivery_readiness",
        audit.get("effective_delivery_readiness") in READY_STATUSES,
        "The model-led validator declared a delivery-ready outcome.",
        "The model-led validator did not declare a delivery-ready outcome.",
    )
    deliverable_bound = (
        isinstance(audit_deliverable, dict)
        and audit_deliverable.get("sha256") == deck_sha256
        and audit_deliverable.get("byte_count") == deck_byte_count
        and Path(str(audit_deliverable.get("path", ""))).expanduser().resolve()
        == resolved_deck
    )
    check(
        "validator.exact_deck",
        deliverable_bound,
        "The advisory validator is bound to the exact final HTML bytes.",
        "The advisory validator is not bound to the exact final HTML bytes.",
    )

    evidence_path = resolved_case / EVIDENCE_REGISTER_FILENAME
    claim_path = resolved_case / CLAIM_REGISTER_FILENAME
    checkpoint_path = resolved_case / WORKPAPER_CHECKPOINT_FILENAME
    required_case_paths = [evidence_path, claim_path, checkpoint_path]
    missing_case_paths = [
        str(path) for path in required_case_paths if not path.is_file()
    ]
    check(
        "case.required_artifacts",
        not missing_case_paths,
        "The case evidence, claim, and workpaper checkpoint artifacts exist.",
        "The case is missing required delivery artifacts: "
        + ", ".join(missing_case_paths),
    )
    if missing_case_paths:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "errors": errors,
            "checks": checks,
            "deck": {
                "path": str(resolved_deck),
                "sha256": deck_sha256,
                "byte_count": deck_byte_count,
            },
            "validation_audit": {
                "path": str(resolved_audit),
                "sha256": _sha256(resolved_audit),
            },
            "boundary": "Mechanical closure only; semantic judgement remains model-led and partner-owned.",
        }

    evidence_register = _load_json(evidence_path)
    claim_register = _load_json(claim_path)
    checkpoint = _load_json(checkpoint_path)
    lineage_audit = _lineage_module().validate_lineage(resolved_case)
    check(
        "case.lineage_valid",
        lineage_audit.get("valid") is True,
        "Current case lineage is mechanically valid.",
        "Current case lineage is invalid: "
        + "; ".join(str(item) for item in lineage_audit.get("errors", [])),
    )

    audit_lineage = audit.get("lineage")
    audit_evidence = (
        audit_lineage.get("evidence_register")
        if isinstance(audit_lineage, dict)
        else None
    )
    audit_claims = (
        audit_lineage.get("claim_register") if isinstance(audit_lineage, dict) else None
    )
    generation_time = (
        isinstance(audit_lineage, dict)
        and audit_lineage.get("provenance_mode") == "generation_time"
    )
    check(
        "validator.generation_time_lineage",
        generation_time,
        "The advisory review used generation-time case lineage.",
        "The advisory review did not use generation-time case lineage.",
    )
    evidence_hash_current = isinstance(audit_evidence, dict) and audit_evidence.get(
        "sha256"
    ) == _sha256(evidence_path)
    claim_hash_current = isinstance(audit_claims, dict) and audit_claims.get(
        "sha256"
    ) == _sha256(claim_path)
    check(
        "validator.current_evidence_register",
        evidence_hash_current,
        "The validator is bound to the current evidence register.",
        "The evidence register changed after advisory validation.",
    )
    check(
        "validator.current_claim_register",
        claim_hash_current,
        "The validator is bound to the current claim register.",
        "The claim register changed after advisory validation.",
    )

    checkpoint_workpaper = checkpoint.get("workpaper")
    checkpoint_lineage = checkpoint.get("lineage")
    workpaper_path = resolved_case / "advisory_workpaper.md"
    workpaper_current = (
        checkpoint.get("schema_version") == "clara.advisory_workpaper_checkpoint.v1"
        and workpaper_path.is_file()
        and isinstance(checkpoint_workpaper, dict)
        and checkpoint_workpaper.get("sha256") == _sha256(workpaper_path)
        and checkpoint_workpaper.get("byte_count") == workpaper_path.stat().st_size
    )
    check(
        "workpaper.exact_bytes",
        workpaper_current,
        "The living workpaper matches its controlled checkpoint.",
        "The living workpaper is missing or changed after its checkpoint.",
    )
    workpaper_lineage_current = (
        isinstance(checkpoint_lineage, dict)
        and checkpoint_lineage.get("evidence_register_sha256") == _sha256(evidence_path)
        and checkpoint_lineage.get("claim_semantic_sha256")
        == _semantic_claim_register_sha256(claim_register)
    )
    check(
        "workpaper.current_semantic_lineage",
        workpaper_lineage_current,
        "The workpaper checkpoint matches current evidence and claim meaning.",
        "Evidence or claim meaning changed after the workpaper checkpoint.",
    )

    claims = claim_register.get("claims", [])
    claim_by_id = {
        str(item.get("id")): item
        for item in claims
        if isinstance(item, dict) and item.get("id")
    }
    appeared_direct_claim_ids = {
        claim_id
        for claim_id, claim in claim_by_id.items()
        if claim.get("state") == "active"
        and claim.get("decision_use") == "direct"
        and any(
            isinstance(appearance, dict)
            and appearance.get("artifact_sha256") == deck_sha256
            for appearance in claim.get("appearances", [])
        )
    }
    reviewed_claim_ids = {
        str(value)
        for value in (
            audit_lineage.get("reviewed_claim_ids", [])
            if isinstance(audit_lineage, dict)
            else []
        )
        if str(value)
    }
    checkpoint_claim_ids = {
        str(value)
        for value in (
            checkpoint_lineage.get("referenced_claim_ids", [])
            if isinstance(checkpoint_lineage, dict)
            else []
        )
        if str(value)
    }
    check(
        "deck.direct_claim_appearances",
        bool(appeared_direct_claim_ids),
        "The final deck has active direct claims bound to its exact bytes.",
        "The final deck has no active direct claim bound to its exact bytes.",
    )
    check(
        "validator.reviewed_deck_claims",
        bool(appeared_direct_claim_ids)
        and appeared_direct_claim_ids <= reviewed_claim_ids,
        "Every active direct deck claim was included in the model-led review.",
        "At least one active direct deck claim was omitted from the model-led review.",
    )
    check(
        "workpaper.covers_deck_claims",
        bool(appeared_direct_claim_ids)
        and appeared_direct_claim_ids <= checkpoint_claim_ids,
        "Every active direct deck claim is referenced by the living workpaper checkpoint.",
        "At least one active direct deck claim is absent from the living workpaper checkpoint.",
    )

    observed_html_results: set[str] = set()
    for index, artifact in enumerate(audit.get("format_check_artifacts", [])):
        if (
            not isinstance(artifact, dict)
            or artifact.get("workflow") != "clara:html-deck"
        ):
            continue
        artifact_path = Path(str(artifact.get("path", ""))).expanduser().resolve()
        artifact_current = (
            artifact_path.is_file()
            and artifact.get("sha256") == _sha256(artifact_path)
            and artifact.get("byte_count") == artifact_path.stat().st_size
        )
        check(
            f"html.format_artifact_{index + 1}",
            artifact_current,
            f"HTML format artifact {index + 1} is unchanged.",
            f"HTML format artifact {index + 1} is missing or changed.",
        )
        if not artifact_current:
            continue
        result = _html_result(_load_json(artifact_path))
        if result is None:
            errors.append(f"HTML format artifact is not authoritative: {artifact_path}")
            continue
        result_kind, passed, input_sha256 = result
        observed_html_results.add(result_kind)
        check(
            f"html.{result_kind}",
            passed and input_sha256 == deck_sha256,
            f"{result_kind} passed for the exact final deck bytes.",
            f"{result_kind} did not pass for the exact final deck bytes.",
        )
    missing_html_results = {
        "html_static_validation",
        "html_browser_qa",
    } - observed_html_results
    check(
        "html.required_results",
        not missing_html_results,
        "Static HTML validation and browser QA are both present.",
        "Required HTML results are missing: " + ", ".join(sorted(missing_html_results)),
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready" if not errors else "blocked",
        "errors": errors,
        "checks": checks,
        "deck": {
            "path": str(resolved_deck),
            "sha256": deck_sha256,
            "byte_count": deck_byte_count,
            "active_direct_claim_ids": sorted(appeared_direct_claim_ids),
        },
        "case": {
            "path": str(resolved_case),
            "evidence_register_sha256": _sha256(evidence_path),
            "claim_register_sha256": _sha256(claim_path),
            "workpaper_checkpoint_sha256": _sha256(checkpoint_path),
        },
        "validation_audit": {
            "path": str(resolved_audit),
            "sha256": _sha256(resolved_audit),
        },
        "boundary": "Mechanical closure only; semantic judgement remains model-led and partner-owned.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("deck", type=Path)
    parser.add_argument("validation_audit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        output = args.output.expanduser().resolve()
        protected = {
            args.deck.expanduser().resolve(),
            args.validation_audit.expanduser().resolve(),
        }
        if output in protected:
            raise AdvisoryHTMLDeliveryError(
                "delivery receipt output must not overwrite an input artifact"
            )
        receipt = verify_advisory_html_delivery(
            args.case_dir,
            args.deck,
            args.validation_audit,
        )
        _write_json(output, receipt)
    except (AdvisoryHTMLDeliveryError, OSError, ValueError) as exc:
        LOGGER.error("Advisory HTML delivery verification failed: %s", exc)
        return 2
    LOGGER.info(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
