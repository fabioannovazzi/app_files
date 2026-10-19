"""Retain a user's decision on an exact proposal without professional credentials."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from .authorization import request_bytes
from .contracts import ContractError, canonical_hash, file_hash, validate
from .review_evidence import (
    _configuration,  # Used only by the optional signed-document inspection route.
)
from .review_evidence import (
    _digest,
    _new,
    _preflight,
    _prior_location,
    _prior_versions,
    _read,
    _scope,
)

__all__ = [
    "prepare_review",
    "accept_review",
    "verify_control_review",
    "verify_reopening",
]
PREFIXES = {
    "REVIEW_CONTROLS": "confirmed_decision",
    "APPROVE_DOSSIER": "professional_approval",
    "REOPEN_CASE": "professional_reopening",
}


def _bindings(
    output: Path, session: dict, proposal: dict, preflight: dict, action: str
) -> dict:
    digest = canonical_hash(proposal)
    bindings = {
        "proposal_sha256": digest,
        "evidence_sha256": canonical_hash(session["inputs"]),
        "rules_sha256": canonical_hash(proposal["rules"]),
        "source_preflight_sha256": canonical_hash(preflight),
        "result_sha256": None,
        "artifacts_sha256": None,
        "prior_approval_sha256": None,
    }
    if action == "APPROVE_DOSSIER":
        directory = output / f"calculation_{digest}"
        if directory.is_symlink() or not directory.is_dir():
            raise ContractError("Calculation directory must be a regular directory")
        manifest = _read(directory / "manifest.json")
        if (
            manifest["run_id"] != session["run_id"]
            or manifest["proposal_digest"] != digest
        ):
            raise ContractError("Calculation belongs to another proposal or run")
        actual = {
            p.name: file_hash(p)
            for p in directory.iterdir()
            if p.name != "manifest.json" and p.is_file() and not p.is_symlink()
        }
        if actual != manifest["artifacts"] or any(
            p.is_symlink() or not p.is_file() for p in directory.iterdir()
        ):
            raise ContractError("Calculation artifacts changed after preparation")
        bindings.update(
            result_sha256=file_hash(directory / "result.json"),
            artifacts_sha256=canonical_hash(manifest),
            prior_approval_sha256=file_hash(
                output / f"confirmed_decision_{digest}.json"
            ),
        )
    return bindings


def _reopening(
    context: dict, session: dict, output: Path, proposal: dict, previous_digest: str
) -> dict:
    if _digest(previous_digest) == canonical_hash(proposal):
        raise ContractError("Reopening requires a different proposal")
    root, previous_session = _prior_location(context, session, output, previous_digest)
    previous = _read(root / f"proposal_{previous_digest}.json")
    if canonical_hash(previous) != previous_digest or _scope(
        context, previous
    ) != _scope(context, proposal):
        raise ContractError("Previous proposal belongs to a different scope")
    # Retain the historical record as evidence, not as authority for the new work.
    approval = root / f"professional_approval_{previous_digest}.json"
    _read(approval)
    return {
        "previous_proposal_sha256": previous_digest,
        "previous_approval_sha256": file_hash(approval),
        "previous_run_id": previous_session["run_id"],
        "prior_versions": _prior_versions(context, output, proposal),
    }


def prepare_review(
    context: dict,
    session: dict,
    output: Path,
    proposal: dict,
    *,
    source_scan: Path,
    action: str,
    at: datetime,
    previous_digest: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    if at.tzinfo is None or action not in PREFIXES:
        raise ContractError("Choose an exact review action and timezone-aware time")
    if action == "APPROVE_DOSSIER":
        verify_control_review(context, session, output, proposal, at=at)
    elif action == "REVIEW_CONTROLS":
        verify_reopening(context, session, output, proposal, at=at)
    preflight = _preflight(proposal, source_scan, at)
    request = {
        "schema_version": "2.0",
        "request_id": str(uuid4()),
        "action": action,
        "demo": session["demo"],
        "scope": _scope(context, proposal),
        "run_id": session["run_id"],
        "created_at": at.isoformat(),
        "expires_at": (at + timedelta(hours=24)).isoformat(),
        "statement": "Confermo questa proposta e le scelte mostrate per procedere con l'operazione indicata.",
        "bindings": _bindings(output, session, proposal, preflight, action),
    }
    if action == "REOPEN_CASE":
        if not previous_digest or not reason or not reason.strip():
            raise ContractError(
                "Reopening needs the selected previous version and a reason"
            )
        request["reopening"] = {
            "previous_proposal_sha256": previous_digest,
            "reason": reason.strip(),
        }
        request["previous_version"] = _reopening(
            context, session, output, proposal, previous_digest
        )
    elif previous_digest is not None or reason is not None:
        raise ContractError("Previous version and reason apply only to reopening")
    validate(request, "proposal-review-request.schema.json")
    fingerprint = canonical_hash(request)
    directory = output / f"professional_request_{fingerprint}"
    directory.mkdir(mode=0o700)
    for name, value in [
        ("request.json", request),
        ("source_preflight.json", preflight),
        ("source_location.json", {"path": str(source_scan.resolve())}),
    ]:
        _new(directory / name, request_bytes(value))
    _new(
        directory / "review.md",
        (
            "# Patent Box — proposta da confermare\n\n"
            + request["statement"]
            + "\n\nLeggere la proposta, le fonti e gli elaborati indicati. La conferma riguarda solo questa versione; non richiede ruolo professionale, firma o mandato.\n\n```json\n"
            + request_bytes(request).decode()
            + "```\n"
        ).encode(),
    )
    return {
        "request_digest": fingerprint,
        "directory": str(directory),
        "request": request,
    }


def _current_request(
    context: dict,
    session: dict,
    output: Path,
    proposal: dict,
    request_digest: str,
    at: datetime,
) -> tuple[dict, Path]:
    directory = output / f"professional_request_{_digest(request_digest)}"
    request = _read(directory / "request.json")
    validate(request, "proposal-review-request.schema.json")
    if at.tzinfo is None or not datetime.fromisoformat(
        request["created_at"]
    ) <= at <= datetime.fromisoformat(request["expires_at"]):
        raise ContractError("Review request is future or expired")
    if canonical_hash(request) != request_digest or (
        directory / "request.json"
    ).read_bytes() != request_bytes(request):
        raise ContractError("Review request bytes changed")
    if (
        request["run_id"] != session["run_id"]
        or request["demo"] != session["demo"]
        or request["scope"] != _scope(context, proposal)
    ):
        raise ContractError("Review belongs to a different run or scope")
    scan = Path(_read(directory / "source_location.json")["path"])
    preflight = _preflight(proposal, scan, at)
    if preflight != _read(directory / "source_preflight.json") or request[
        "bindings"
    ] != _bindings(output, session, proposal, preflight, request["action"]):
        raise ContractError("Review bindings changed")
    if request["action"] == "REOPEN_CASE" and request["previous_version"] != _reopening(
        context,
        session,
        output,
        proposal,
        request["reopening"]["previous_proposal_sha256"],
    ):
        raise ContractError("Previous version changed")
    return request, directory


def accept_review(
    context: dict,
    session: dict,
    output: Path,
    proposal: dict,
    *,
    request_digest: str,
    reviewer: str,
    confirmation_ref: str,
    confirmed: bool,
    at: datetime,
) -> dict[str, Any]:
    if confirmed is not True or any(
        not isinstance(v, str) or not v.strip() for v in [reviewer, confirmation_ref]
    ):
        raise ContractError(
            "The user's actual decision, actor and confirmation reference are required"
        )
    request, _ = _current_request(
        context, session, output, proposal, request_digest, at
    )
    fingerprint = canonical_hash(proposal)
    receipt = {
        "schema_version": "patent_box.user_decision.v1",
        "request": request,
        "request_digest": request_digest,
        "reviewer": reviewer.strip(),
        "confirmation_ref": confirmation_ref.strip(),
        "confirmed": True,
        "recorded_at": at.isoformat(),
    }
    receipt_hash = canonical_hash(receipt)
    _new(output / f"user_decision_{request_digest}.json", request_bytes(receipt))
    record = {
        "schema_version": "2.0",
        "run_id": session["run_id"],
        "proposal_digest": fingerprint,
        "reviewer": reviewer.strip(),
        "confirmation_ref": confirmation_ref.strip(),
        "request_digest": request_digest,
        "confirmed": True,
        "reviewed_on": at.date().isoformat(),
        "recorded_at": at.isoformat(),
        "identity_assurance": "USER_CONFIRMATION_NOT_AUTHENTICATED",
        "evidence_hash": canonical_hash(session["inputs"]),
        "signature": None,
        "receipt_sha256": receipt_hash,
    }
    _new(
        output / f"{PREFIXES[request['action']]}_{fingerprint}.json",
        request_bytes(record),
    )
    return record


def _verify_record(
    context: dict,
    session: dict,
    output: Path,
    proposal: dict,
    *,
    action: str,
    at: datetime,
) -> dict:
    path = output / f"{PREFIXES[action]}_{canonical_hash(proposal)}.json"
    if not path.is_file():
        raise ContractError("Confirmation of the exact current proposal is required")
    record = _read(path)
    receipt = _read(output / f"user_decision_{_digest(record['request_digest'])}.json")
    request, _ = _current_request(
        context, session, output, proposal, record["request_digest"], at
    )
    if (
        record["schema_version"] != "2.0"
        or record["identity_assurance"] != "USER_CONFIRMATION_NOT_AUTHENTICATED"
        or record["signature"] is not None
        or request["action"] != action
        or record["confirmed"] is not True
        or receipt["confirmed"] is not True
        or receipt["request"] != request
        or canonical_hash(receipt) != record["receipt_sha256"]
        or any(
            record[key] != receipt[key]
            for key in ["reviewer", "confirmation_ref", "recorded_at"]
        )
        or record["run_id"] != session["run_id"]
        or record["proposal_digest"] != canonical_hash(proposal)
        or record["evidence_hash"] != canonical_hash(session["inputs"])
    ):
        raise ContractError(
            "Saved decision differs from the current proposal or actual confirmation"
        )
    return record


def verify_control_review(
    context: dict, session: dict, output: Path, proposal: dict, *, at: datetime
) -> dict:
    return _verify_record(
        context, session, output, proposal, action="REVIEW_CONTROLS", at=at
    )


def verify_reopening(
    context: dict, session: dict, output: Path, proposal: dict, *, at: datetime
) -> dict | None:
    if not _prior_versions(context, output, proposal):
        return None
    return _verify_record(
        context, session, output, proposal, action="REOPEN_CASE", at=at
    )
