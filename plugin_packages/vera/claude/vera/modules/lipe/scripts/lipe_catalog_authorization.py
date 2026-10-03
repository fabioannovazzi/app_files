"""Authenticate catalog write roles; tax classes and disclosure remain judgments.

Exact payload, certificate and scope checks enforce studio-assigned permissions.
They do not infer professional powers from a certificate's subject or inspect
whether an entry is legally correct or safe to share. Nothing is transmitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema
from lipe_authorization import (
    provider_hash,
    read_evidence,
    read_signed_json,
    request_bytes,
    verify_cms_document,
)
from lipe_core import ROOT, ContractError, digest, read_json

__all__ = ["prepare_decision", "authorize_event", "verify_preserved", "main"]

CONFIG_ENV = "VERA_LIPE_CATALOG_AUTHORITY_CONFIG"
STATEMENT = (
    "Approvo l'esatta operazione sul catalogo e le evidenze indicate, nei ruoli "
    "assegnati dallo studio. La firma non certifica la correttezza fiscale, "
    "non pubblica dati e non autorizza una dichiarazione o una trasmissione."
)


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _host(
    path: Path, metadata: dict, *excluded_roots: Path
) -> tuple[dict, dict[str, bytes]]:
    configured = os.environ.get(CONFIG_ENV)
    if not configured:
        raise ContractError("Independent catalog authority is not configured")
    selected = Path(configured)
    excluded = [ROOT.parent, path.parent, *excluded_roots]
    if not selected.is_absolute() or any(
        selected.resolve().is_relative_to(root.resolve()) for root in excluded
    ):
        raise ContractError(
            "Catalog authority must be outside the catalog and components"
        )
    config, raw = read_signed_json(selected)
    validator = jsonschema.Draft202012Validator(
        read_json(ROOT / "schemas/catalog-authority.schema.json"),
        format_checker=jsonschema.FormatChecker(),
    )
    errors = sorted(
        validator.iter_errors(config), key=lambda error: str(error.json_path)
    )
    if errors:
        raise ContractError("Catalog authority: " + errors[0].message)
    for key in ("catalog_id", "studio_id", "data_origin"):
        if config[key] != metadata[key]:
            raise ContractError(
                "Catalog authority does not cover this catalog, studio or data origin"
            )
    originals = {"authority.json": raw}
    for key in ("openssl", "trusted_roots", "crls"):
        provider = Path(config[key])
        if not provider.is_absolute() or any(
            provider.resolve().is_relative_to(root.resolve()) for root in excluded
        ):
            raise ContractError(
                "Catalog authority providers must be independent of the catalog"
            )
        if provider.is_symlink() or not provider.is_file():
            raise ContractError("Catalog authority provider must be a regular file")
        if key != "openssl":
            originals[key + ".pem"] = read_evidence(provider)
    fingerprints = [row["certificate_sha256"] for row in config["signers"]]
    if len(fingerprints) != len(set(fingerprints)):
        raise ContractError("Catalog authority has duplicate certificate grants")
    return config, originals


def _operation(event: dict) -> dict:
    return {
        key: value
        for key, value in event.items()
        if key not in {"recorded_at", "source_objects", "authorization"}
    }


def _bindings(state: dict, event: dict, config: dict) -> dict:
    return {
        "schema_version": "lipe.catalog.decision.v1",
        "catalog_id": state["metadata"]["catalog_id"],
        "metadata_hash": digest(state["metadata"]),
        "expected_head": state["head_hash"],
        "policy_id": config["policy_id"],
        "provider_hash": provider_hash(),
        "runtime_hash": digest(
            {
                str(item.relative_to(ROOT)): _hash(read_evidence(item))
                for folder, suffix in (("scripts", "*.py"), ("schemas", "*.json"))
                for item in sorted((ROOT / folder).glob(suffix))
            }
        ),
        "operation": _operation(event),
        "statement": STATEMENT,
    }


def _requirements(state: dict, event: dict) -> list[tuple[str, str, str | None, str]]:
    """Check explicit role and client scope, never the tax meaning of an entry."""
    from lipe_catalog import _entry_at, _latest

    kind = event["kind"]
    if kind == "RECORD":
        entry = event["entry"]
        requirements = [
            (
                "PROFESSIONAL",
                entry["review"]["reviewer"],
                entry["client_id"],
                entry["scope"],
            )
        ]
        if entry["scope"] == "CENTRAL":
            requirements += [
                ("CURATOR", entry["curator_review"]["reviewer"], None, "CENTRAL"),
                (
                    "DISCLOSURE_REVIEWER",
                    entry["disclosure_review"]["reviewer"],
                    None,
                    "CENTRAL",
                ),
            ]
        return requirements
    if kind == "REVOKE":
        current = _latest(state).get(event["entry_id"])
        if current is None:
            raise ContractError("Unknown catalog entry for revocation")
        entry = _entry_at(state, current)
        role = "CURATOR" if entry["scope"] == "CENTRAL" else "PROFESSIONAL"
        return [(role, event["review"]["reviewer"], entry["client_id"], entry["scope"])]
    if kind == "DISPUTE":
        return [("PROFESSIONAL", event["review"]["reviewer"], None, "STUDIO")]
    if kind == "RESOLVE_DISPUTE":
        return [("CURATOR", event["curator_review"]["reviewer"], None, "CENTRAL")]
    raise ContractError("Unsupported catalog operation")


def prepare_decision(path: Path, operation: dict, output: Path) -> Path:
    """Prepare exact bytes for externally supplied signatures; do not mutate a catalog."""
    from lipe_catalog import history

    state = history(path)
    if not state["metadata"].get("require_signatures"):
        raise ContractError("Select a catalog configured for signed decisions")
    if operation != _operation(operation):
        raise ContractError("The proposed operation contains generated event fields")
    try:
        requirements = _requirements(state, operation)
    except (KeyError, TypeError) as exc:
        raise ContractError("Incomplete proposed catalog operation") from exc
    config, _ = _host(path, state["metadata"], output)
    now = datetime.now(timezone.utc)
    request = {
        **_bindings(state, operation, config),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=24)).isoformat(),
    }
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    raw = request_bytes(request)
    _write(output / "request.json", raw)
    readable = json.dumps(request, ensure_ascii=False, indent=2)
    fence = "`" * max(
        3, 1 + max((len(x) for x in re.findall(r"`+", readable)), default=0)
    )
    text = (
        "# LIPE — decisione sul catalogo\n\n"
        "Esaminare l'intera operazione, le fonti originali e le relative impronte. "
        "Firmare esternamente gli esatti byte di request.json. Il catalogo non è ancora modificato. "
        "Una modifica all'operazione o alla testa del catalogo richiede nuove firme.\n\n"
        f"{fence}json\n{readable}\n{fence}\n\n"
        "Sono richiesti i ruoli indicati dalla configurazione indipendente dello studio "
        "per tutti i revisori della decisione. Le firme devono chiamarsi decision-*.p7s. "
        "Non fornire chiavi private. La validità di 24 ore è una politica interna.\n\n"
        "## Quali dati arrivano al modello\n\n"
        "Se aperti, richiesta, codici, classi fiscali, fonti, citazioni, identificativi "
        "del cliente/studio e nomi dei revisori possono entrare nel modello dell'host. "
        "Il verificatore locale non chiama modelli o reti e non pubblica il catalogo.\n"
    )
    _write(output / "request.md", text.encode("utf-8"))
    _write(
        output / "required-roles.json", request_bytes({"requirements": requirements})
    )
    return output


def _write(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle:
        path.chmod(0o600)
        handle.write(raw)


def authorize_event(
    path: Path, state: dict, event: dict, approval: Path | None
) -> dict:
    """Reverify signatures and scope inside the caller's catalog write transaction."""
    if approval is None or approval.is_symlink() or not approval.is_dir():
        raise ContractError(
            "This catalog requires original externally signed decisions"
        )
    config, originals = _host(path, state["metadata"], approval)
    authority_originals = dict(originals)
    request, raw = read_signed_json(approval / "request.json")
    original_binding = {
        key: value
        for key, value in request.items()
        if key not in {"created_at", "expires_at"}
    }
    if original_binding != _bindings(state, event, config):
        raise ContractError(
            "Signed catalog decision is stale or describes a different operation"
        )
    if not all(
        isinstance(request.get(key), str) for key in ("created_at", "expires_at")
    ):
        raise ContractError("Catalog decision requires valid explicit timestamps")
    try:
        start = datetime.fromisoformat(request["created_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(request["expires_at"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError(
            "Catalog decision requires valid explicit timestamps"
        ) from exc
    now = datetime.now(timezone.utc)
    if (
        start.tzinfo is None
        or end.tzinfo is None
        or not start <= now < end
        or end - start > timedelta(hours=24)
    ):
        raise ContractError("Catalog decision is future, expired or exceeds 24 hours")
    if raw != request_bytes(request):
        raise ContractError("Sign the unchanged canonical catalog request bytes")
    signatures = sorted(approval.glob("decision-*.p7s"))
    if not 1 <= len(signatures) <= 8:
        raise ContractError("Supply between one and eight original catalog signatures")
    originals["request.json"] = raw
    verified, granted = [], []
    for index, signature in enumerate(signatures, 1):
        signature_raw = read_evidence(signature)
        proof = verify_cms_document(
            raw,
            signature_raw,
            openssl=Path(config["openssl"]),
            trusted_roots=originals["trusted_roots.pem"],
            crls=originals["crls.pem"],
            at=now,
        )
        fingerprint = proof["certificate_sha256"]
        grant = next(
            (
                row
                for row in config["signers"]
                if row["certificate_sha256"] == fingerprint
            ),
            None,
        )
        if grant is None or fingerprint in config["revoked_certificate_sha256"]:
            raise ContractError("Catalog signer is not currently authorized")
        if any(row["certificate_sha256"] == fingerprint for row in granted):
            raise ContractError("Duplicate catalog signer")
        originals[f"decision-{index}.p7s"] = signature_raw
        verified.append(proof)
        granted.append(grant)
    requirements = _requirements(state, event)
    for role, name, client, scope in requirements:
        if not any(
            row["name"] == name
            and role in row["roles"]
            and scope in row["scopes"]
            and (client is None or row["all_clients"] or client in row["client_ids"])
            for row in granted
        ):
            raise ContractError(
                "A required catalog reviewer role or client permission is not signed"
            )
    _, latest_authority = _host(path, state["metadata"], approval)
    if latest_authority != authority_originals or datetime.now(timezone.utc) >= end:
        raise ContractError(
            "Catalog authority changed or the decision expired during verification"
        )
    evidence_root = path.parent / (path.name + ".authorizations")
    if evidence_root.is_symlink() or not evidence_root.resolve().is_relative_to(
        path.parent.resolve()
    ):
        raise ContractError("Catalog authorization evidence cannot be a symlink")
    evidence_root.mkdir(mode=0o700, exist_ok=True)
    artifacts = []
    for name, value in originals.items():
        filename = _hash(value) + "-" + name
        target = evidence_root / filename
        if target.is_symlink():
            raise ContractError("Catalog authorization evidence cannot be a symlink")
        if target.exists():
            if read_evidence(target) != value:
                raise ContractError("Preserved catalog authorization changed")
        else:
            _write(target, value)
        artifacts.append({"file": filename, "sha256": _hash(value)})
    return {
        "status": "ROLES_VERIFIED_AT_COMMIT",
        "verified_at": now.isoformat(),
        "policy_id": config["policy_id"],
        "request_sha256": _hash(raw),
        "requirements": requirements,
        "signers": granted,
        "verification": verified,
        "artifacts": artifacts,
        "professional_powers": "ASSIGNED_BY_HOST_STUDIO_POLICY",
        "qualified_signature_status": "NOT_TESTED",
        "remote_sharing": False,
    }


def verify_preserved(path: Path, state: dict) -> None:
    """Detect missing or changed historical evidence; do not claim current authority."""
    root = path.parent / (path.name + ".authorizations")
    if root.is_symlink() or not root.resolve().is_relative_to(path.parent.resolve()):
        raise ContractError("Catalog authorization evidence cannot be a symlink")
    for row in state["events"]:
        proof = row["event"].get("authorization")
        mutation = row["event"]["kind"] in {
            "RECORD",
            "REVOKE",
            "DISPUTE",
            "RESOLVE_DISPUTE",
        }
        if state["metadata"].get("require_signatures") and mutation and not proof:
            raise ContractError("Signed catalog contains an unauthenticated event")
        if proof:
            for item in proof["artifacts"]:
                name = item["file"]
                if not re.fullmatch(
                    r"[0-9a-f]{64}-(?:authority.json|request.json|trusted_roots.pem|crls.pem|decision-[1-8].p7s)",
                    name,
                ):
                    raise ContractError("Invalid catalog authorization object name")
                if _hash(read_evidence(root / name)) != item["sha256"]:
                    raise ContractError(
                        "Historical catalog authorization is missing or changed"
                    )


def main(argv: list[str] | None = None) -> int:
    """Prepare a review packet; applying it uses the existing catalog commands."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--operation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    operation, _ = read_signed_json(args.operation)
    result = prepare_decision(args.catalog, operation, args.output)
    logging.info("LIPE catalog decision prepared, not applied: %s", result)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
