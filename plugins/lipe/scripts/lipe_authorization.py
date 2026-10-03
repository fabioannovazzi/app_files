"""Verify externally signed LIPE decisions against an independently configured firm.

Reuses the installed Vera CMS verifier for exact bytes, algorithm policy, chain
and CRLs. Certificate subjects are never converted into professional powers.
The firm establishes powers and signs a separate mandate. No private keys are
accepted and this adapter neither signs nor transmits tax returns.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import jsonschema
from lipe_core import ROOT, ContractError, _nonfinite, _pairs, digest, read_json

__all__ = [
    "request_bytes",
    "provider_hash",
    "load_authority",
    "load_export_registry",
    "verify_approval",
    "read_evidence",
    "read_signed_json",
    "validate_request",
]

MAX_BYTES = 16 * 1024 * 1024
CONFIG_ENV = "VERA_LIPE_AUTHORITY_CONFIG"


def request_bytes(value: dict) -> bytes:
    """Return the exact UTF-8 representation presented for external signing."""
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _validate(value: dict, name: str) -> None:
    schema = read_json(ROOT / "schemas" / (name + ".schema.json"))
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    errors = sorted(
        validator.iter_errors(value), key=lambda error: str(error.json_path)
    )
    if errors:
        raise ContractError(
            f"LIPE authorization {errors[0].json_path}: {errors[0].message}"
        )


def read_evidence(path: Path) -> bytes:
    """Read one bounded original, rejecting links and empty evidence."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ContractError("Authorization requires bounded regular files")
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_BYTES:
        raise ContractError("Authorization evidence is empty or excessive")
    return raw


def read_signed_json(path: Path) -> tuple[dict, bytes]:
    """Parse the same exact bytes that will be verified or preserved."""
    raw = read_evidence(path)
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_nonfinite
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("Authorization requires valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ContractError("Authorization JSON must be an object")
    return value, raw


def validate_request(request: dict) -> None:
    """Check the fixed authorization contract before consuming its fields."""
    _validate(request, "approval-request")


def provider_hash() -> str:
    """Identify the sibling Vera verifier; client-controlled import paths are unused."""
    root = ROOT.parent / "patent-box-review/patent_box"
    files = ("__init__.py", "contracts.py", "formalities.py")
    if root.is_symlink() or not root.is_dir():
        raise ContractError(
            "The installed Vera certificate-verification component is required"
        )
    return digest(
        {name: hashlib.sha256(read_evidence(root / name)).hexdigest() for name in files}
    )


def _provider() -> ModuleType:
    root = ROOT.parent / "patent-box-review/patent_box"
    name = "_lipe_cms_" + provider_hash()
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            name, root / "__init__.py", submodule_search_locations=[str(root)]
        )
        if spec is None or spec.loader is None:
            raise ContractError("The installed CMS verifier cannot be loaded")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return importlib.import_module(name + ".formalities")


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ContractError("Authorization dates require an explicit timezone")
    return parsed.astimezone(timezone.utc)


def _configuration(excluded_roots: list[Path]) -> dict:
    configured = os.environ.get(CONFIG_ENV)
    if not configured:
        raise ContractError(
            "The firm's independent LIPE authority policy is not configured"
        )
    path = Path(configured)
    roots = [ROOT.parent, *excluded_roots]
    if not path.is_absolute() or any(
        path.resolve().is_relative_to(root.resolve()) for root in roots
    ):
        raise ContractError(
            "Authority configuration must be outside client runs and the LIPE component"
        )
    config, _ = read_signed_json(path)
    required = {"policy", "openssl", "trusted_roots", "crls"}
    if not required.issubset(config) or set(config) - required - {"export_registry"}:
        raise ContractError("Authority configuration has unexpected or missing fields")
    _validate(config["policy"], "authority-policy")
    return config


def load_authority(*, excluded_roots: list[Path]) -> dict:
    """Load only host-admin configuration, never a policy chosen by a case file."""
    config = _configuration(excluded_roots)
    roots = [ROOT.parent, *excluded_roots]
    result = {"policy": config["policy"]}
    for key in ("openssl", "trusted_roots", "crls"):
        if not isinstance(config[key], str) or not config[key].strip():
            raise ContractError("Authority provider paths must be absolute strings")
        selected = Path(config[key])
        if not selected.is_absolute() or any(
            selected.resolve().is_relative_to(root.resolve()) for root in roots
        ):
            raise ContractError(
                "Authority executables and trust material must be independent of the case"
            )
        if not selected.resolve().is_file():
            raise ContractError(
                "Configured authority provider or trust file is missing"
            )
        result[key] = selected
    return result


def load_export_registry(*, excluded_roots: list[Path]) -> Path:
    """Use the firm's one configured filename registry, never a case-chosen reset."""
    config = _configuration(excluded_roots)
    value = config.get("export_registry")
    if not isinstance(value, str) or not value.strip():
        raise ContractError(
            "The firm has not configured its shared export filename registry"
        )
    path = Path(value)
    if (
        not path.is_absolute()
        or path.is_symlink()
        or not path.parent.is_dir()
        or any(
            path.resolve().is_relative_to(root.resolve())
            for root in [ROOT.parent, *excluded_roots]
        )
    ):
        raise ContractError(
            "The export registry must be outside client runs and installed components"
        )
    return path


def _signer(verification: dict) -> str:
    for name in (
        "signature_integrity",
        "signature_algorithm_policy",
        "document_binding",
        "certificate_chain",
        "revocation",
    ):
        if verification[name]["status"] != "PASS":
            raise ContractError(f"LIPE authorization {name} is not verified")
    signers = verification["signers"]
    if len(signers) != 1 or signers[0]["key_usage"] != "PASS":
        raise ContractError(
            "A LIPE decision needs one identified signer with signing key usage"
        )
    return str(signers[0]["certificate_sha256"])


def verify_approval(
    request: dict,
    *,
    signature: Path,
    mandate: Path,
    mandate_signature: Path,
    policy: dict,
    openssl: Path,
    trusted_roots: Path,
    crls: Path,
    at: datetime,
) -> dict:
    """Verify current firm authority and signatures; request bindings are checked by the workflow."""
    _validate(request, "approval-request")
    _validate(policy, "authority-policy")
    if at.tzinfo is None:
        raise ContractError("Verification time requires a timezone")
    now = at.astimezone(timezone.utc)
    created, expires = _timestamp(request["created_at"]), _timestamp(
        request["expires_at"]
    )
    if not created <= now < expires or expires - created > timedelta(hours=24):
        raise ContractError(
            "LIPE approval request is future, expired or exceeds 24 hours"
        )
    if request["scope"]["data_origin"] != policy["data_origin"]:
        raise ContractError("Real and synthetic authority cannot be mixed")
    if not policy["admin_certificate_sha256"]:
        raise ContractError("The firm has not configured any trusted mandate issuer")
    current_provider = provider_hash()
    if request["bindings"]["crypto_provider_hash"] != current_provider:
        raise ContractError(
            "The certificate-verification component changed after preparation"
        )
    raw = {
        "request": request_bytes(request),
        "signature": read_evidence(signature),
        "mandate": read_evidence(mandate),
        "mandate_signature": read_evidence(mandate_signature),
        "trusted_roots": read_evidence(trusted_roots),
        "crls": read_evidence(crls),
    }
    provider = _provider()
    with tempfile.TemporaryDirectory(prefix="lipe-approval-") as directory:
        paths = {}
        for name, value in raw.items():
            path = Path(directory) / name
            with path.open("xb") as handle:
                path.chmod(0o600)
                handle.write(value)
            paths[name] = path
        grant = read_json(paths["mandate"])
        _validate(grant, "professional-mandate")
        if (
            grant["policy_id"] != policy["policy_id"]
            or grant["scope"] != request["scope"]
        ):
            raise ContractError(
                "Mandate does not cover this policy and exact case scope"
            )
        if grant["mandate_id"] in policy["revoked_mandate_ids"]:
            raise ContractError("The professional mandate has been revoked")
        if (
            not _timestamp(grant["valid_from"])
            <= now
            < _timestamp(grant["valid_until"])
        ):
            raise ContractError("The professional mandate is future or expired")
        if request["action"] not in grant["actions"]:
            raise ContractError("The mandate does not authorize the requested action")
        options = {
            "openssl": openssl,
            "at": now,
            "trusted_roots": paths["trusted_roots"],
            "crls": paths["crls"],
        }
        try:
            admin_proof = provider.verify_cms(
                paths["mandate_signature"], paths["mandate"], **options
            )
            decision_proof = provider.verify_cms(
                paths["signature"], paths["request"], **options
            )
        except provider.ContractError as exc:
            raise ContractError(str(exc)) from exc
        admin, reviewer = _signer(admin_proof), _signer(decision_proof)
        if (
            admin not in policy["admin_certificate_sha256"]
            or admin in policy["revoked_certificate_sha256"]
        ):
            raise ContractError(
                "Mandate issuer is not a currently trusted firm administrator"
            )
        if (
            reviewer != grant["reviewer_certificate_sha256"]
            or reviewer in policy["revoked_certificate_sha256"]
        ):
            raise ContractError(
                "The decision was not signed by the currently authorized professional"
            )
    receipt = {
        "schema_version": "lipe.authorization.v1",
        "request": request,
        "request_sha256": hashlib.sha256(raw["request"]).hexdigest(),
        "validated_at": now.isoformat(),
        "studio_id": policy["studio_id"],
        "policy_hash": digest(policy),
        "mandate_id": grant["mandate_id"],
        "reviewer_name": grant["reviewer_name"],
        "professional_reference": grant["professional_reference"],
        "reviewer_certificate_sha256": reviewer,
        "powers_evidence": grant["powers_evidence"],
        "identity_assurance": "CERTIFICATE_AND_FIRM_SIGNED_MANDATE",
        "professional_status_basis": "FIRM_ASSERTION_NOT_INDEPENDENT_REGISTER_CHECK",
        "qualified_signature_status": "NOT_TESTED",
        "filing_status": "NOT_SIGNED_OR_TRANSMITTED",
        "input_sha256": {
            name: hashlib.sha256(value).hexdigest() for name, value in raw.items()
        },
        "mandate_verification": admin_proof,
        "review_verification": decision_proof,
    }
    receipt["receipt_hash"] = digest(receipt)
    return receipt
