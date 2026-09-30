"""Bind external professional signatures to exact archive review versions."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .authorization import request_bytes, verify_authorization
from .contracts import (
    ContractError,
    canonical_hash,
    file_hash,
    indexed,
    read_json,
    validate,
)
from .formalities import verify_cms
from .source_acquisition import read_final_scan

__all__ = [
    "prepare_review",
    "accept_review",
    "verify_control_review",
    "verify_reopening",
]

MAX_BYTES = 16 * 1024 * 1024
CONFIG_ENV = "VERA_PATENT_BOX_AUTHORITY_CONFIG"


def _read(path: Path) -> dict[str, Any]:
    if (
        path.is_symlink()
        or path.parent.is_symlink()
        or not path.is_file()
        or path.stat().st_size > MAX_BYTES
    ):
        raise ContractError("Expected bounded regular professional-review evidence")
    result = read_json(path)
    if not isinstance(result, dict):
        raise ContractError("Professional review record must be an object")
    return result


def _new(path: Path, value: bytes) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise ContractError("Symlink review records are forbidden")
    with path.open("xb") as handle:
        handle.write(value)
    path.chmod(0o600)


def _digest(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ContractError("Invalid review digest")
    return value


def _preflight(proposal: dict[str, Any], scan: Path, at: datetime) -> dict[str, Any]:
    final = read_final_scan(scan)
    if final["snapshot"]["coverage"] != "COMPLETE_DECLARED_SCOPE":
        raise ContractError(
            "Professional review needs complete declared source coverage"
        )
    actual = indexed(final["snapshot"]["sources"], "source_id")
    expected = indexed(proposal["rules"]["sources"], "source_id")
    if set(actual) != set(expected):
        raise ContractError(
            "Acquired source population differs from the proposed rules"
        )
    for source_id, source in actual.items():
        acquired = datetime.fromisoformat(source["retrieved_at"])
        if source["fetch_status"] != "OK" or not timedelta(
            0
        ) <= at - acquired <= timedelta(hours=24):
            raise ContractError(
                "Source preflight is unavailable, future or more than 24 hours old"
            )
        if source["content_sha256"] != expected[source_id]["snapshot_sha256"]:
            raise ContractError(
                "Current source bytes differ; propose new rules and review"
            )
    return {
        "scan_hash": final["final_hash"],
        "snapshot": final["snapshot"],
        "review": final["review"],
        "extraction": final["extraction"],
        "exhaustive_legal_monitoring": False,
    }


def _scope(context: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
    case = proposal["case"]
    period = indexed(case["periods"], "period_id")[case["claim_period_id"]]
    return {
        "client_id": context["client_id"],
        "engagement_id": context["engagement_id"],
        "period": {key: period[key] for key in ("period_id", "start", "end")},
    }


def _bindings(
    output: Path,
    session: dict[str, Any],
    proposal: dict[str, Any],
    preflight: dict[str, Any],
    action: str,
) -> dict[str, Any]:
    digest = canonical_hash(proposal)
    result = {
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
            raise ContractError(
                "Calculation manifest belongs to a different run or proposal"
            )
        actual = {
            path.name: file_hash(path)
            for path in directory.iterdir()
            if path.name != "manifest.json" and path.is_file() and not path.is_symlink()
        }
        if actual != manifest["artifacts"] or any(
            path.is_symlink() or not path.is_file() for path in directory.iterdir()
        ):
            raise ContractError("Calculation artifacts changed after preparation")
        previous = output / f"authenticated_decision_{digest}.json"
        result.update(
            result_sha256=file_hash(directory / "result.json"),
            artifacts_sha256=canonical_hash(manifest),
            prior_approval_sha256=file_hash(previous),
        )
    return result


def _prior_versions(
    context: dict[str, Any], output: Path, proposal: dict[str, Any]
) -> dict[str, str]:
    current_name = f"professional_approval_{canonical_hash(proposal)}.json"
    paths = {
        "current/" + path.name: path
        for path in output.glob("professional_approval_*.json")
        if path.name != current_name
    }
    for row in context.get("input_bindings", []):
        path = Path(row["path"])
        if (
            row["kind"] == "upstream_artifact"
            and row["upstream_workflow_id"] == "patent-box-review"
            and re.fullmatch(r"professional_approval_[0-9a-f]{64}\.json", path.name)
        ):
            paths[row["binding_id"]] = path
    for path in paths.values():
        _read(path)
    return {name: file_hash(path) for name, path in sorted(paths.items())}


def _prior_location(
    context: dict[str, Any], session: dict[str, Any], output: Path, previous_digest: str
) -> tuple[Path, dict[str, Any]]:
    name = f"proposal_{previous_digest}.json"
    if (output / name).is_file():
        return output, session
    candidates = [
        row
        for row in context.get("input_bindings", [])
        if row["kind"] == "upstream_artifact"
        and row["upstream_workflow_id"] == "patent-box-review"
        and Path(row["path"]).name == name
    ]
    if len(candidates) != 1:
        raise ContractError(
            "Select the exact prior approved version as archive upstream artifacts"
        )
    run_id = candidates[0]["upstream_run_id"]
    root = Path(context["input_dir"]) / "upstream" / run_id
    selected = {
        Path(row["path"])
        for row in context["input_bindings"]
        if row["kind"] == "upstream_artifact"
        and row["upstream_run_id"] == run_id
        and row["upstream_workflow_id"] == "patent-box-review"
    }
    physical = set(root.rglob("*"))
    if (
        root.is_symlink()
        or any(path.is_symlink() for path in physical)
        or {path for path in physical if path.is_file()} != selected
    ):
        raise ContractError(
            "Prior version must contain only exactly selected archive artifacts"
        )
    previous_session = _read(root / "patent_box_session.json")
    if (
        previous_session["run_id"] != run_id
        or previous_session["demo"] != session["demo"]
    ):
        raise ContractError(
            "Prior archive session identity or synthetic status differs"
        )
    return root, previous_session


def _prior_version(
    context: dict[str, Any],
    session: dict[str, Any],
    output: Path,
    proposal: dict[str, Any],
    previous_digest: str,
    at: datetime,
) -> dict[str, Any]:
    """Check retained bytes; a new signature, not historical trust, authorizes reopening."""
    previous_digest = _digest(previous_digest)
    if previous_digest == canonical_hash(proposal):
        raise ContractError("Reopening requires a different proposed version")
    current_output = output
    prior_versions = _prior_versions(context, output, proposal)
    output, session = _prior_location(context, session, output, previous_digest)
    previous = _read(output / f"proposal_{previous_digest}.json")
    if canonical_hash(previous) != previous_digest or _scope(
        context, previous
    ) != _scope(context, proposal):
        raise ContractError(
            "Prior version belongs to a different proposal or fiscal scope"
        )
    record_path = output / f"professional_approval_{previous_digest}.json"
    record = _read(record_path)
    request_digest = _digest(record["confirmation_ref"])
    directory = output / f"professional_request_{request_digest}"
    request = _read(directory / "request.json")
    validate(request, "professional-request.schema.json")
    if (
        canonical_hash(request) != request_digest
        or (directory / "request.json").read_bytes() != request_bytes(request)
        or request["action"] != "APPROVE_DOSSIER"
        or request["run_id"] != session["run_id"]
        or request["scope"] != _scope(context, proposal)
        or request["demo"] != session["demo"]
    ):
        raise ContractError("Prior final request does not belong to this run and scope")
    preflight = _read(directory / "source_preflight.json")
    if request["bindings"] != _bindings(
        output, session, previous, preflight, "APPROVE_DOSSIER"
    ):
        raise ContractError("Preserved version changed after approval")
    evidence = output / f"professional_evidence_{request_digest}"
    receipt = _read(evidence / "receipt.json")
    receipt_hash = canonical_hash(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    )
    if (
        receipt_hash != receipt["receipt_sha256"]
        or receipt_hash != record["receipt_sha256"]
    ):
        raise ContractError("Prior receipt changed")
    if (
        record["run_id"] != session["run_id"]
        or record["proposal_digest"] != previous_digest
        or record["evidence_hash"] != canonical_hash(session["inputs"])
        or record["confirmed"] is not True
        or receipt["request"] != request
        or receipt["request_sha256"] != file_hash(directory / "request.json")
        or record["reviewer"] != receipt["reviewer_name"]
        or record["signature"] != receipt["input_sha256"]["request_signature"]
    ):
        raise ContractError("Prior approval differs from its retained evidence")
    for name in (
        "request_signature",
        "mandate",
        "mandate_signature",
        "trusted_roots",
        "crls",
    ):
        path = evidence / name
        if (
            path.is_symlink()
            or evidence.is_symlink()
            or file_hash(path) != receipt["input_sha256"][name]
        ):
            raise ContractError("Prior signed evidence changed")
    # Old mandates never authorize new work. Historical certificate/time trust
    # remains separate from byte integrity and the new, current REOPEN_CASE grant.
    proof = verify_cms(
        evidence / "request_signature",
        directory / "request.json",
        openssl=_configuration(current_output)["openssl"],
        at=at,
    )
    if (
        any(
            proof[key]["status"] != "PASS"
            for key in (
                "signature_integrity",
                "document_binding",
                "signature_algorithm_policy",
            )
        )
        or len(proof["signers"]) != 1
        or proof["signers"][0]["certificate_sha256"]
        != receipt["reviewer_certificate_sha256"]
    ):
        raise ContractError(
            "Preserved approval signature does not match its signed bytes"
        )
    return {
        "previous_proposal_sha256": previous_digest,
        "previous_approval_sha256": file_hash(record_path),
        "previous_result_sha256": request["bindings"]["result_sha256"],
        "previous_bindings": request["bindings"],
        "retained_receipt_sha256": receipt_hash,
        "historical_trust_and_timestamp": "NOT_TESTED",
        "prior_run_id": session["run_id"],
        "prior_versions": prior_versions,
    }


def _reopening_bindings(
    context: dict[str, Any],
    session: dict[str, Any],
    output: Path,
    proposal: dict[str, Any],
    preflight: dict[str, Any],
    reopening: dict[str, Any],
    at: datetime,
) -> dict[str, Any]:
    prior = _prior_version(
        context, session, output, proposal, reopening["previous_proposal_sha256"], at
    )
    bindings = _bindings(output, session, proposal, preflight, "REOPEN_CASE")
    bindings.update(
        prior_approval_sha256=prior["previous_approval_sha256"],
        result_sha256=prior["previous_result_sha256"],
        artifacts_sha256=canonical_hash(prior),
    )
    return bindings


def prepare_review(
    context: dict[str, Any],
    session: dict[str, Any],
    output: Path,
    proposal: dict[str, Any],
    *,
    source_scan: Path,
    action: str,
    at: datetime,
    previous_digest: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Prepare exact bytes for external signing; never sign or approve them."""
    if action not in ("REVIEW_CONTROLS", "APPROVE_DOSSIER", "REOPEN_CASE"):
        raise ContractError("Unsupported professional-review action")
    if at.tzinfo is None:
        raise ContractError("Review time needs a timezone")
    if action == "APPROVE_DOSSIER":
        verify_control_review(context, session, output, proposal, at=at)
    elif action == "REVIEW_CONTROLS":
        verify_reopening(context, session, output, proposal, at=at)
    preflight = _preflight(proposal, source_scan, at)
    request = {
        "schema_version": "1.0",
        "request_id": str(uuid4()),
        "action": action,
        "demo": session["demo"],
        "scope": _scope(context, proposal),
        "run_id": session["run_id"],
        "created_at": at.isoformat(),
        "expires_at": (at + timedelta(hours=24)).isoformat(),
        "statement": (
            "Confermo il riesame professionale della proposta, delle fonti e delle regole indicate, mantenendo espliciti gli esiti aperti."
            if action == "REVIEW_CONTROLS"
            else "Approvo professionalmente questa versione esatta degli elaborati e dei risultati, con le riserve registrate."
        ),
        "bindings": _bindings(output, session, proposal, preflight, action),
    }
    if action == "REOPEN_CASE":
        if previous_digest is None or reason is None or not reason.strip():
            raise ContractError(
                "Reopening needs a previous approved version and a reason"
            )
        request["reopening"] = {
            "previous_proposal_sha256": _digest(previous_digest),
            "reason": reason.strip(),
        }
        request["statement"] = (
            "Autorizzo il riesame della nuova proposta collegata alla versione conservata e alla motivazione indicata. La decisione precedente rimane immutata; il nuovo risultato richiede nuovi controlli e una nuova approvazione."
        )
        request["bindings"] = _reopening_bindings(
            context, session, output, proposal, preflight, request["reopening"], at
        )
    elif previous_digest is not None or reason is not None:
        raise ContractError("Previous version and reason apply only to reopening")
    validate(request, "professional-request.schema.json")
    digest = canonical_hash(request)
    directory = output / f"professional_request_{digest}"
    directory.mkdir(mode=0o700)
    _new(directory / "request.json", request_bytes(request))
    _new(directory / "source_preflight.json", request_bytes(preflight))
    _new(
        directory / "source_location.json",
        request_bytes({"path": str(source_scan.resolve())}),
    )
    _new(
        directory / "review.md",
        (
            "# Riesame professionale Patent Box\n\n"
            + request["statement"]
            + "\n\nLeggere la proposta e gli elaborati della pratica prima di firmare request.json con il proprio servizio di firma. La firma del riesame non firma il fascicolo e non attribuisce penalty protection.\n\n"
            + "```json\n"
            + request_bytes(request).decode()
            + "```\n"
        ).encode(),
    )
    return {"request_digest": digest, "directory": str(directory), "request": request}


def _current_request(
    context: dict[str, Any],
    session: dict[str, Any],
    output: Path,
    proposal: dict[str, Any],
    digest: str,
    at: datetime,
) -> tuple[dict[str, Any], Path]:
    directory = output / f"professional_request_{_digest(digest)}"
    request = _read(directory / "request.json")
    validate(request, "professional-request.schema.json")
    if canonical_hash(request) != digest or (
        directory / "request.json"
    ).read_bytes() != request_bytes(request):
        raise ContractError("Professional request bytes changed")
    if (
        request["run_id"] != session["run_id"]
        or request["scope"] != _scope(context, proposal)
        or request["demo"] != session["demo"]
    ):
        raise ContractError("Professional request does not belong to this case")
    if request["action"] == "APPROVE_DOSSIER":
        verify_control_review(context, session, output, proposal, at=at)
    elif request["action"] == "REVIEW_CONTROLS":
        verify_reopening(context, session, output, proposal, at=at)
    location = _read(directory / "source_location.json")
    preflight = _preflight(proposal, Path(location["path"]), at)
    bindings = (
        _reopening_bindings(
            context, session, output, proposal, preflight, request["reopening"], at
        )
        if request["action"] == "REOPEN_CASE"
        else _bindings(output, session, proposal, preflight, request["action"])
    )
    if (
        preflight != _read(directory / "source_preflight.json")
        or request["bindings"] != bindings
    ):
        raise ContractError("Professional request bindings changed")
    return request, directory


def _configuration(output: Path) -> dict[str, Any]:
    configured = os.environ.get(CONFIG_ENV)
    if not configured:
        raise ContractError("Firm professional authorization is not configured")
    path = Path(configured)
    if not path.is_absolute() or path.resolve().is_relative_to(output.resolve()):
        raise ContractError(
            "Authority configuration must be a separate host-admin file"
        )
    config = _read(path)
    if set(config) != {"policy", "openssl", "trusted_roots", "crls"}:
        raise ContractError("Invalid host authority configuration")
    validate(config["policy"], "authority-policy.schema.json")
    for key in ("openssl", "trusted_roots", "crls"):
        configured_path = Path(config[key])
        if (
            not configured_path.is_absolute()
            or configured_path.resolve().is_relative_to(output.resolve())
        ):
            raise ContractError("Authority paths must come from host administration")
        config[key] = configured_path
    return config


def accept_review(
    context: dict[str, Any],
    session: dict[str, Any],
    output: Path,
    proposal: dict[str, Any],
    *,
    request_digest: str,
    signature: Path,
    mandate: Path,
    mandate_signature: Path,
    at: datetime,
) -> dict[str, Any]:
    """Verify external signatures and retain their exact bytes without replacement."""
    request, _ = _current_request(
        context, session, output, proposal, request_digest, at
    )
    config = _configuration(output)
    receipt = verify_authorization(
        request,
        signature=signature,
        mandate=mandate,
        mandate_signature=mandate_signature,
        at=at,
        **config,
    )
    retained = {}
    for name, path in (
        ("request_signature", signature),
        ("mandate", mandate),
        ("mandate_signature", mandate_signature),
    ):
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != receipt["input_sha256"][name]:
            raise ContractError("Signed evidence changed during authorization")
        retained[name] = raw
    digest = canonical_hash(proposal)
    prefix = {
        "REVIEW_CONTROLS": "authenticated_decision",
        "APPROVE_DOSSIER": "professional_approval",
        "REOPEN_CASE": "professional_reopening",
    }[request["action"]]
    record_name = f"{prefix}_{digest}.json"
    if (output / record_name).exists():
        raise ContractError(
            "This review version already exists; preserve it and prepare a new version"
        )
    directory = output / f"professional_evidence_{request_digest}"
    directory.mkdir(mode=0o700)
    for name, raw in retained.items():
        _new(directory / name, raw)
    _new(directory / "receipt.json", request_bytes(receipt))
    _new(directory / "policy.json", request_bytes(config["policy"]))
    for name in ("trusted_roots", "crls"):
        raw = config[name].read_bytes()
        if hashlib.sha256(raw).hexdigest() != receipt["input_sha256"][name]:
            raise ContractError("Authority trust evidence changed during authorization")
        _new(directory / name, raw)
    record = {
        "schema_version": "1.0",
        "run_id": session["run_id"],
        "proposal_digest": digest,
        "reviewer": receipt["reviewer_name"],
        "reviewed_on": at.date().isoformat(),
        "recorded_at": at.isoformat(),
        "confirmed": True,
        "identity_assurance": receipt["identity_assurance"],
        "evidence_hash": canonical_hash(session["inputs"]),
        "confirmation_ref": request_digest,
        "signature": receipt["input_sha256"]["request_signature"],
        "receipt_sha256": receipt["receipt_sha256"],
    }
    _new(output / record_name, request_bytes(record))
    return record


def _verify_record(
    context: dict[str, Any],
    session: dict[str, Any],
    output: Path,
    proposal: dict[str, Any],
    *,
    at: datetime,
    prefix: str,
    action: str,
) -> dict[str, Any]:
    """Recheck original signed approval and current mandate before reuse."""
    digest = canonical_hash(proposal)
    record = _read(output / f"{prefix}_{digest}.json")
    request_digest = _digest(record["confirmation_ref"])
    request, _ = _current_request(
        context, session, output, proposal, request_digest, at
    )
    if request["action"] != action:
        raise ContractError("Stored review has the wrong authorized action")
    directory = output / f"professional_evidence_{request_digest}"
    original = _read(directory / "receipt.json")
    if (
        canonical_hash(
            {key: value for key, value in original.items() if key != "receipt_sha256"}
        )
        != record["receipt_sha256"]
    ):
        raise ContractError("Stored professional receipt changed")
    receipt = verify_authorization(
        request,
        signature=directory / "request_signature",
        mandate=directory / "mandate",
        mandate_signature=directory / "mandate_signature",
        at=at,
        **_configuration(output),
    )
    if (
        record["run_id"] != session["run_id"]
        or record["proposal_digest"] != digest
        or record["identity_assurance"] != receipt["identity_assurance"]
        or record["recorded_at"] != original["validated_at"]
        or record["reviewed_on"]
        != datetime.fromisoformat(original["validated_at"]).date().isoformat()
        or original["input_sha256"] != receipt["input_sha256"]
        or original["policy_sha256"] != receipt["policy_sha256"]
        or record["reviewer"] != receipt["reviewer_name"]
        or record["signature"] != receipt["input_sha256"]["request_signature"]
        or record["evidence_hash"] != canonical_hash(session["inputs"])
        or record["confirmed"] is not True
    ):
        raise ContractError("Stored review differs from the authenticated evidence")
    return record


def verify_control_review(
    context: dict[str, Any],
    session: dict[str, Any],
    output: Path,
    proposal: dict[str, Any],
    *,
    at: datetime,
) -> dict[str, Any]:
    """Recheck current authority and exact control-review bindings."""
    return _verify_record(
        context,
        session,
        output,
        proposal,
        at=at,
        prefix="authenticated_decision",
        action="REVIEW_CONTROLS",
    )


def verify_reopening(
    context: dict[str, Any],
    session: dict[str, Any],
    output: Path,
    proposal: dict[str, Any],
    *,
    at: datetime,
) -> dict[str, Any] | None:
    """Require fresh authority before revising a run with an approved version."""
    digest = canonical_hash(proposal)
    prior = _prior_versions(context, output, proposal)
    if not prior:
        return None
    if not (output / f"professional_reopening_{digest}.json").is_file():
        raise ContractError(
            "A changed approved case requires an authenticated reopening decision"
        )
    return _verify_record(
        context,
        session,
        output,
        proposal,
        at=at,
        prefix="professional_reopening",
        action="REOPEN_CASE",
    )
