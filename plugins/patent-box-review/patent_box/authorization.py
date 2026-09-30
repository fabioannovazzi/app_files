"""Verify externally signed professional decisions and firm-issued mandates.

Fixed checks enforce cryptographic identity and exact authorization scope. The
firm establishes professional status/powers; code never infers them from names,
email addresses or certificate subjects. No private signing keys are accepted.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .contracts import ContractError, canonical_hash, read_json, validate
from .formalities import verify_cms

__all__ = ["request_bytes", "verify_authorization"]

MAX_BYTES = 16 * 1024 * 1024


def request_bytes(value: dict[str, Any]) -> bytes:
    """Provide the one exact UTF-8 representation the professional signs."""
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _read(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ContractError("Authorization needs bounded regular evidence files")
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_BYTES:
        raise ContractError("Authorization evidence is empty or excessive")
    return raw


def _date(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ContractError("Authorization time requires a timezone")
    return result.astimezone(timezone.utc)


def _signer(verification: dict[str, Any]) -> str:
    for key in (
        "signature_integrity",
        "signature_algorithm_policy",
        "document_binding",
        "certificate_chain",
        "revocation",
    ):
        if verification[key]["status"] != "PASS":
            raise ContractError(f"Authorization {key} is not verified")
    signers = verification["signers"]
    if len(signers) != 1 or signers[0]["key_usage"] != "PASS":
        raise ContractError(
            "Authorization needs one identified signer with signing key usage"
        )
    return str(signers[0]["certificate_sha256"])


def verify_authorization(
    request: dict[str, Any],
    *,
    signature: Path,
    mandate: Path,
    mandate_signature: Path,
    policy: dict[str, Any],
    openssl: Path,
    trusted_roots: Path,
    crls: Path,
    at: datetime,
) -> dict[str, Any]:
    """Verify a signed decision against an independently configured firm policy.

    The caller must load policy/trust from host administration, not a model or
    client proposal. The receipt proves exact signed statements and a mandate
    asserted by a pinned administrator; it does not certify legal eligibility.
    """
    validate(request, "professional-request.schema.json")
    validate(policy, "authority-policy.schema.json")
    if (request["action"] == "REOPEN_CASE") != ("reopening" in request):
        raise ContractError("Reopening linkage must occur only on a reopening request")
    if at.tzinfo is None:
        raise ContractError("Authorization validation requires a timezone")
    now = at.astimezone(timezone.utc)
    created, expires = _date(request["created_at"]), _date(request["expires_at"])
    if not created <= now < expires or expires - created > timedelta(hours=24):
        raise ContractError(
            "Review request is future, expired or valid for more than 24 hours"
        )
    if not policy["admin_certificate_sha256"]:
        raise ContractError("Firm professional authorization is not configured")
    raw = {
        "mandate": _read(mandate),
        "mandate_signature": _read(mandate_signature),
        "request_signature": _read(signature),
        "trusted_roots": _read(trusted_roots),
        "crls": _read(crls),
        "request": request_bytes(request),
    }
    # Parse and verify the same retained bytes, never a mutable pathname twice.
    with tempfile.TemporaryDirectory(prefix="patent-box-authorization-") as directory:
        root = Path(directory)
        paths = {}
        for name, value in raw.items():
            path = root / name
            path.write_bytes(value)
            path.chmod(0o600)
            paths[name] = path
        grant = read_json(paths["mandate"])
        validate(grant, "professional-mandate.schema.json")
        if grant["policy_id"] != policy["policy_id"]:
            raise ContractError("Mandate belongs to a different firm policy")
        if grant["demo"] != policy["demo"] or request["demo"] != policy["demo"]:
            raise ContractError("Synthetic and real authorization cannot be mixed")
        if grant["scope"] != request["scope"]:
            raise ContractError(
                "Mandate does not cover this exact client, engagement and period"
            )
        if grant["mandate_id"] in policy["revoked_mandate_ids"]:
            raise ContractError("Mandate has been revoked by the firm")
        if not _date(grant["valid_from"]) <= now < _date(grant["valid_until"]):
            raise ContractError("Mandate is future or expired")
        if not grant["powers_evidence"]:
            raise ContractError("Mandate needs identified powers evidence")
        required = {request["action"]}
        if request["action"] == "REVIEW_CONTROLS":
            required.add("REVIEW_RULES")
        if not required.issubset(grant["actions"]):
            raise ContractError(
                "Mandate does not authorize every requested review action"
            )
        bindings = request["bindings"]
        if request["action"] == "APPROVE_DOSSIER" and any(
            bindings[name] is None
            for name in ("result_sha256", "artifacts_sha256", "prior_approval_sha256")
        ):
            raise ContractError(
                "Final approval must bind results, artifacts and the control review"
            )
        if (
            request["action"] == "REOPEN_CASE"
            and bindings["prior_approval_sha256"] is None
        ):
            raise ContractError(
                "Reopening must identify the preserved previous approval"
            )
        options: dict[str, Any] = {
            "openssl": openssl,
            "at": now,
            "trusted_roots": paths["trusted_roots"],
            "crls": paths["crls"],
        }
        admin_proof = verify_cms(
            paths["mandate_signature"], paths["mandate"], **options
        )
        admin = _signer(admin_proof)
        if (
            admin not in policy["admin_certificate_sha256"]
            or admin in policy["revoked_certificate_sha256"]
        ):
            raise ContractError(
                "Mandate was not signed by a currently trusted firm administrator"
            )
        review_proof = verify_cms(
            paths["request_signature"], paths["request"], **options
        )
        reviewer = _signer(review_proof)
        if (
            reviewer != grant["reviewer_certificate_sha256"]
            or reviewer in policy["revoked_certificate_sha256"]
        ):
            raise ContractError(
                "Decision signer differs from the authorized professional"
            )
    receipt = {
        "schema_version": "1.0",
        "identity_assurance": "CERTIFICATE_AND_FIRM_SIGNED_MANDATE",
        "validated_at": now.isoformat(),
        "request": request,
        "request_sha256": hashlib.sha256(raw["request"]).hexdigest(),
        "policy_sha256": canonical_hash(policy),
        "authority_name": policy["authority_name"],
        "mandate_id": grant["mandate_id"],
        "mandate_sha256": hashlib.sha256(raw["mandate"]).hexdigest(),
        "reviewer_name": grant["reviewer_name"],
        "professional_reference": grant["professional_reference"],
        "reviewer_certificate_sha256": reviewer,
        "powers_evidence": grant["powers_evidence"],
        "input_sha256": {
            name: hashlib.sha256(value).hexdigest() for name, value in raw.items()
        },
        "mandate_verification": admin_proof,
        "review_verification": review_proof,
        "qualified_signature_status": "NOT_TESTED",
        "professional_status_basis": "ASSERTED_BY_FIRM_ADMINISTRATOR_NOT_AN_INDEPENDENT_REGISTRY_CHECK",
    }
    receipt["receipt_sha256"] = canonical_hash(receipt)
    return receipt
