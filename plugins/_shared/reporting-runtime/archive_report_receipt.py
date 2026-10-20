"""Authenticated, retry-stable proofs binding Archive reports to Vera userID."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from archive_report_store import (
    Registry,
    RunStore,
    atomic_bytes,
    atomic_json,
    canonical,
    run_lock,
)

__all__ = ["stamp_report", "retry_pending", "validate_receipt", "verify_report"]
_SERVER = "https://mparanza.com"
_FIELDS = {
    "schema_version",
    "product",
    "receipt_id",
    "plugin_version",
    "report_sha256",
    "user_id",
    "archive_run_id",
    "report_revision",
}


def _product_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        for relative in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
            manifest = parent / relative
            if (
                manifest.is_file()
                and json.loads(manifest.read_text(encoding="utf-8"))["name"] == "vera"
            ):
                return parent
        if (
            parent.name == "plugins"
            and (parent / "vera/.codex-plugin/plugin.json").is_file()
        ):
            return parent / "vera"
    raise ValueError("Installed Vera root is unavailable")


def _request(report_path: Path, *, persist: bool = True) -> dict[str, Any]:
    from archive_reporting import validate_report

    if report_path.is_symlink():
        raise ValueError("Report cannot be a symbolic link")
    raw = report_path.read_bytes()
    report = validate_report(json.loads(raw))
    if (
        not report["collection_closed"]
        or report["finished_at"] is None
        or report["outcome"] not in {"completed", "failed", "cancelled"}
    ):
        raise ValueError("Only the Archive terminal write can submit a report proof")
    if raw != canonical(report):
        raise ValueError("Report bytes do not match the saved canonical report")
    request_path = report_path.with_name("model_data_receipt_request.json")
    previous = (
        json.loads(request_path.read_text(encoding="utf-8"))
        if persist and request_path.is_file()
        else None
    )
    from notarized_run_receipt import _plugin_version

    if not isinstance(report["user_id"], str):
        raise ValueError("The report has no bound Vera userID")
    request = {
        "schema_version": 3,
        "product": "vera",
        "receipt_id": str(
            uuid5(
                UUID(report["user_id"]),
                f"archive:{report['run_id']}:{report['report_revision']}",
            )
        ),
        "plugin_version": (
            previous["plugin_version"]
            if previous
            else (_plugin_version(_product_root()) if persist else None)
        ),
        "report_sha256": hashlib.sha256(raw).hexdigest(),
        "user_id": report["user_id"],
        "archive_run_id": report["run_id"],
        "report_revision": report["report_revision"],
    }
    if previous is not None and previous != request:
        raise ValueError("Retained receipt request belongs to different report bytes")
    if persist:
        atomic_json(request_path, request)
    return request


def validate_receipt(receipt: Any, request: dict[str, Any]) -> dict[str, Any]:
    """Require all owner/run/hash fields and a proof for the exact fixed endpoint."""
    required = _FIELDS | {
        "stamped_at",
        "key_id",
        "algorithm",
        "signature",
        "public_key",
        "verification_url",
        "signature_valid",
    }
    if not isinstance(receipt, dict) or set(receipt) != required:
        raise ValueError("Invalid Archive receipt fields")
    if any(receipt[key] != request[key] for key in _FIELDS):
        raise ValueError("Receipt owner, run or report hash does not match")
    if receipt["algorithm"] != "Ed25519" or receipt["signature_valid"] is not True:
        raise ValueError("Archive receipt signature is not verified")
    for key in ("signature", "public_key"):
        if (
            not isinstance(receipt[key], str)
            or re.fullmatch(r"[A-Za-z0-9_-]+", receipt[key]) is None
        ):
            raise ValueError("Invalid receipt signature encoding")
    expected = f"{_SERVER}/verify/vera-run-receipt/{request['receipt_id']}?sha256={request['report_sha256']}&user_id={request['user_id']}&archive_run_id={request['archive_run_id']}&report_revision={request['report_revision']}"
    if receipt["verification_url"] != expected:
        raise ValueError("Receipt verification link does not bind this machine and run")
    return receipt


def _html(receipt: dict[str, Any]) -> str:
    fields = (
        "user_id",
        "archive_run_id",
        "report_revision",
        "report_sha256",
        "stamped_at",
    )
    entries = "".join(
        f"<dt>{key}</dt><dd>{html.escape(str(receipt[key]))}</dd>" for key in fields
    )
    return f'<!doctype html><html lang="it"><meta charset="utf-8"><title>Ricevuta del report Vera</title><main><h1>Ricevuta del report Vera</h1><dl>{entries}</dl><p>Il report resta sulla macchina. Questa ricevuta associa la sua impronta all’esecuzione e a Vera userID autenticato.</p><a href="{html.escape(receipt["verification_url"], quote=True)}">Verifica report e Vera userID</a></main></html>'


def stamp_report(report_path: Path) -> dict[str, Any]:
    """Queue before transport; preserve local work through network or identity failures."""
    options_path = report_path.with_name("model_data_report_options.json")
    if options_path.is_file():
        options = json.loads(options_path.read_text(encoding="utf-8"))
        if (
            not isinstance(options, dict)
            or set(options) - {"local_only"}
            or type(options.get("local_only", False)) is not bool
        ):
            raise ValueError("Report options accept only boolean local_only")
        if options.get("local_only"):
            return {"status": "not_requested", "reason": "local_only"}
    if any(
        (parent / ".vera-onboarding-local-only").exists()
        for parent in report_path.parents
    ):
        return {"status": "not_requested", "reason": "local_onboarding"}
    try:
        request = _request(report_path)
        receipt_path = report_path.with_name("model_data_receipt.json")
        from operational_incidents import reporting_credentials, workflow_transport

        credentials = reporting_credentials()
        if credentials["installation_id"] != request["user_id"]:
            raise ValueError(
                "Current Vera userID differs from the run's original machine identity"
            )
        # Revalidate through the authenticated, idempotent endpoint. A locally
        # edited receipt's signature_valid field is not proof of server origin.
        receipt = validate_receipt(
            workflow_transport(
                "archive-stamp",
                {"credentials": credentials, "receipt_request": request},
            ),
            request,
        )
        atomic_json(receipt_path, receipt)
        html_path = report_path.with_name("model_data_receipt.html")
        if html_path.is_symlink():
            raise ValueError("Receipt HTML cannot be a symbolic link")
        atomic_bytes(html_path, _html(receipt).encode("utf-8"))
        return {
            "status": "stamped",
            "user_id": receipt["user_id"],
            "archive_run_id": receipt["archive_run_id"],
            "receipt_path": str(receipt_path),
            "html_path": str(html_path),
            "verification_url": receipt["verification_url"],
        }
    except (
        OSError,
        ValueError,
        TypeError,
        sqlite3.Error,
        urllib.error.URLError,
    ) as exc:
        return {"status": "pending", "reason": type(exc).__name__}


def retry_pending(registry: Registry, *, strict: bool = True) -> None:
    """Retry retained terminal reports; never regenerate or rerun professional work."""
    for root in registry.pending_receipts():
        try:
            _retry_one(registry, root)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            if strict:
                raise
            # Keep the failed proof pending and move it behind other retries.
            # No report or professional artifact is repaired or resealed here.
            registry.receipt_result(root, "pending")
            logging.warning("An Archive proof remains pending: %s", type(exc).__name__)


def _retry_one(registry: Registry, root: Path) -> None:
    if root.is_symlink() or not (root / "run.json").is_file():
        registry.receipt_result(root, "run_removed")
        return
    with run_lock(root):
        state = RunStore(root).state()
        report_path = root / "outputs/model_data_report.json"
        if state is None or not state["collection_closed"] or not report_path.is_file():
            registry.receipt_result(root, "pending")
            return
        status_path = root / "model_data_reporting.json"
        result = (
            json.loads(status_path.read_text(encoding="utf-8"))
            if status_path.is_file()
            else {"status": "available", "report_path": str(report_path)}
        )
        from archive_report_seal import checkpoint, reseal

        baseline = checkpoint(root)
        result["server_receipt"] = stamp_report(report_path)
        reseal(root, baseline)
        atomic_json(status_path, result)
        registry.receipt_result(root, result["server_receipt"]["status"])


def verify_report(report_path: Path, *, user_id: str) -> dict[str, Any]:
    """Verify this file against the requested authenticated machine's retained proof."""
    request = _request(report_path, persist=False)
    if str(UUID(user_id)) != request["user_id"]:
        raise ValueError("Report belongs to another Vera userID")
    query = urllib.parse.urlencode(
        {
            "sha256": request["report_sha256"],
            "user_id": user_id,
            "archive_run_id": request["archive_run_id"],
            "report_revision": request["report_revision"],
        }
    )
    from operational_incidents import _NoRedirect

    url = f"{_SERVER}/api/vera/run-receipts/{request['receipt_id']}?{query}"
    with urllib.request.build_opener(_NoRedirect()).open(url, timeout=8) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError("Receipt response exceeds its size limit")
    receipt = json.loads(raw)
    if not isinstance(receipt, dict) or not isinstance(
        receipt.get("plugin_version"), str
    ):
        raise ValueError("Server receipt lacks its original product version")
    # The report alone remains verifiable after a plugin update or when copied
    # without companion files. The server retains and signs the issuing version.
    request["plugin_version"] = receipt["plugin_version"]
    return validate_receipt(receipt, request)


def main(argv: list[str] | None = None) -> int:
    """Verify exact local report bytes against the machine-bound server proof."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["verify"])
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--user-id")
    args = parser.parse_args(argv)
    try:
        from operational_incidents import reporting_credentials

        user_id = args.user_id or reporting_credentials()["installation_id"]
        receipt = verify_report(args.report, user_id=user_id)
        result = {
            "status": "verified",
            "user_id": receipt["user_id"],
            "archive_run_id": receipt["archive_run_id"],
            "report_revision": receipt["report_revision"],
            "report_sha256": receipt["report_sha256"],
            "verification_url": receipt["verification_url"],
        }
    except (ValueError, TypeError, OSError, sqlite3.Error) as exc:
        sys.stderr.write("Report verification failed: " + type(exc).__name__ + "\n")
        return 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
