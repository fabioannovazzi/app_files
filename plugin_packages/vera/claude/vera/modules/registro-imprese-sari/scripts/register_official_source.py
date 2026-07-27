"""Register a browser-selected or user-provided official source without fetching it."""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Any

from case_core import (
    PLUGIN_NAME,
    ensure_safe_output_dir,
    iso_now,
    load_json_object,
    safe_identifier,
    sha256_bytes,
    validate_iso_date,
    validate_official_source_url,
    write_private_bytes,
    write_private_json,
)

__all__ = ["register_source", "main"]

LOGGER = logging.getLogger(__name__)
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MAX_SNAPSHOT_BYTES = 10_000_000
ALLOWED_SOURCE_TYPES = {
    "official_sari_selected_result",
    "official_cciaa_guidance",
    "official_dire_guidance",
    "official_registro_imprese_guidance",
    "official_inps_guidance",
    "official_ivass_guidance",
    "official_suap_guidance",
    "official_other",
}
ALLOWED_AUTHORIZATION_BASES = {
    "browser_assisted_metadata",
    "user_provided_copy",
    "written_reuse_authorization",
}
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _record_source_registration(
    output_dir: Path,
    *,
    run_id: str,
    source: dict[str, Any],
) -> None:
    run_path = output_dir / "run_intake.json"
    if not run_path.exists():
        return
    run = load_json_object(run_path)
    if run.get("plugin") != PLUGIN_NAME or run.get("run_id") != run_id:
        raise ValueError("run_intake.json belongs to another run")
    trace = run.get("execution_trace")
    if not isinstance(trace, list):
        trace = []
    trace.append(
        {
            "step_id": f"register_official_source_{len(trace) + 1}",
            "kind": "local_source_registration",
            "command": [
                "python",
                "scripts/register_official_source.py",
                "--source-id",
                source["source_id"],
                "--authorization-basis",
                source["authorization_basis"],
            ],
            "execution_location": "local_python",
            "status": "passed",
            "inputs": [source["official_url"]],
            "outputs": ["official_sources.json"],
        }
    )
    run["execution_trace"] = trace
    write_private_json(run_path, run)


def _manifest(output_dir: Path, *, run_id: str) -> dict[str, Any]:
    path = output_dir / "official_sources.json"
    if not path.exists():
        return {
            "schema_version": "1.0",
            "plugin": PLUGIN_NAME,
            "run_id": run_id,
            "created_at": iso_now(),
            "sources": [],
            "source_count": 0,
        }
    payload = load_json_object(path)
    if payload.get("plugin") != PLUGIN_NAME or payload.get("run_id") != run_id:
        raise ValueError("existing official_sources.json belongs to another run")
    if not isinstance(payload.get("sources"), list):
        raise ValueError("existing official_sources.json has invalid sources")
    return payload


def _snapshot_name(source_id: str, original: Path) -> str:
    suffix = original.suffix.lower()[:12]
    stem = SAFE_FILENAME_RE.sub("-", source_id).strip("-._") or "source"
    return f"{stem}{suffix}"


def register_source(
    *,
    output_dir: Path,
    run_id: str,
    source_id: str,
    source_type: str,
    title: str,
    official_url: str,
    publisher: str,
    territorial_applicability: str,
    authorization_basis: str,
    authorization_reference: str,
    selected_by: str,
    updated_date: str | None = None,
    snapshot: Path | None = None,
) -> dict[str, Any]:
    """Register one selected official source with provenance and optional local bytes."""

    run_id = safe_identifier(run_id, field="run_id")
    source_id = safe_identifier(source_id, field="source_id")
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise ValueError(f"unsupported source_type: {source_type}")
    title = " ".join(str(title or "").split())
    publisher = " ".join(str(publisher or "").split())
    territory = " ".join(str(territorial_applicability or "").split())
    selected_by = " ".join(str(selected_by or "").split())
    if not title or len(title) > 400:
        raise ValueError("title must contain 1-400 characters")
    if not publisher or len(publisher) > 200:
        raise ValueError("publisher must contain 1-200 characters")
    if not territory or len(territory) > 200:
        raise ValueError("territorial_applicability must contain 1-200 characters")
    if not selected_by or len(selected_by) > 120:
        raise ValueError("selected_by must identify the human/model selection role")
    if authorization_basis not in ALLOWED_AUTHORIZATION_BASES:
        raise ValueError("unsupported authorization_basis")
    authorization_reference = " ".join(str(authorization_reference or "").split())
    if len(authorization_reference) < 3 or len(authorization_reference) > 200:
        raise ValueError("authorization_reference must contain 3-200 characters")
    official_url = validate_official_source_url(official_url)
    normalized_updated_date = (
        validate_iso_date(updated_date, field="updated_date") if updated_date else None
    )
    safe_output = ensure_safe_output_dir(output_dir, plugin_root=PLUGIN_ROOT)
    artifact_path: str | None = None
    artifact_sha256: str | None = None
    if snapshot is not None:
        if snapshot.is_symlink() or not snapshot.is_file():
            raise ValueError("snapshot must be a regular local file")
        if authorization_basis == "browser_assisted_metadata":
            raise ValueError(
                "browser_assisted_metadata cannot persist content; use metadata only"
            )
        raw = snapshot.read_bytes()
        if len(raw) > MAX_SNAPSHOT_BYTES:
            raise ValueError(f"snapshot exceeds {MAX_SNAPSHOT_BYTES} bytes")
        destination = safe_output / "sources" / _snapshot_name(source_id, snapshot)
        write_private_bytes(destination, raw)
        artifact_path = destination.relative_to(safe_output).as_posix()
        artifact_sha256 = sha256_bytes(raw)

    source = {
        "source_id": source_id,
        "source_type": source_type,
        "title": title,
        "publisher": publisher,
        "official_url": official_url,
        "territorial_applicability": territory,
        "updated_date": normalized_updated_date,
        "registered_at": iso_now(),
        "selection_status": "selected_requires_professional_applicability_review",
        "selected_by": selected_by,
        "authorization_basis": authorization_basis,
        "authorization_reference": authorization_reference,
        "artifact_path": artifact_path,
        "artifact_sha256": artifact_sha256,
    }
    manifest = _manifest(safe_output, run_id=run_id)
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise ValueError("official source manifest has invalid sources")
    sources[:] = [item for item in sources if item.get("source_id") != source_id]
    sources.append(source)
    sources.sort(key=lambda item: str(item.get("source_id") or ""))
    manifest["source_count"] = len(sources)
    manifest["updated_at"] = iso_now()
    write_private_json(safe_output / "official_sources.json", manifest)
    _record_source_registration(
        safe_output,
        run_id=run_id,
        source=source,
    )
    return source


def main(argv: list[str] | None = None) -> int:
    """Register one official source selected through a public browser or local copy."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument(
        "--source-type", choices=sorted(ALLOWED_SOURCE_TYPES), required=True
    )
    parser.add_argument("--title", required=True)
    parser.add_argument("--official-url", required=True)
    parser.add_argument("--publisher", required=True)
    parser.add_argument("--territorial-applicability", required=True)
    parser.add_argument(
        "--authorization-basis",
        choices=sorted(ALLOWED_AUTHORIZATION_BASES),
        required=True,
    )
    parser.add_argument("--authorization-reference", required=True)
    parser.add_argument("--selected-by", required=True)
    parser.add_argument("--updated-date")
    parser.add_argument("--snapshot", type=Path)
    args = parser.parse_args(argv)
    try:
        source = register_source(**vars(args))
    except (OSError, ValueError) as exc:
        LOGGER.error("SOURCE_REGISTRATION_BLOCKED: %s", exc)
        return 2
    LOGGER.info("Registered official source %s", source["source_id"])
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
