"""Source and archive evidence checks shared by exact-proposal confirmation."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .contracts import ContractError, canonical_hash, file_hash, indexed, read_json
from .source_acquisition import read_final_scan

__all__: list[str] = []
MAX_BYTES = 16 * 1024 * 1024
CONFIG_ENV = "VERA_PATENT_BOX_AUTHORITY_CONFIG"


def _read(path: Path) -> dict[str, Any]:
    if (
        path.is_symlink()
        or path.parent.is_symlink()
        or not path.is_file()
        or path.stat().st_size > MAX_BYTES
    ):
        raise ContractError("Expected bounded regular review evidence")
    result = read_json(path)
    if not isinstance(result, dict):
        raise ContractError("Review evidence must be an object")
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
            "Proposal confirmation needs complete declared source coverage"
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


def _configuration(output: Path) -> dict[str, Any]:
    """Load optional signed-document verification tools, without role or mandate checks."""
    configured = os.environ.get(CONFIG_ENV)
    if not configured:
        raise ContractError(
            "Signature-verification tools and trust sources are not configured"
        )
    path = Path(configured)
    if not path.is_absolute() or path.resolve().is_relative_to(output.resolve()):
        raise ContractError(
            "Verification configuration must be separate from case outputs"
        )
    config = _read(path)
    required = {"openssl", "trusted_roots", "crls"}
    if not required <= config.keys() or set(config) - required - {"policy"}:
        raise ContractError("Invalid signature-verification configuration")
    result: dict[str, Any] = {}
    for key in required:
        configured_path = Path(config[key])
        if (
            not configured_path.is_absolute()
            or configured_path.resolve().is_relative_to(output.resolve())
        ):
            raise ContractError(
                "Verification tools and trust sources must be outside case outputs"
            )
        result[key] = configured_path
    return result
