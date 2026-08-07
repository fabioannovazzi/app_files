"""Register one exact Studio Archive input as a dossier source."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from case_core import (
    PLUGIN_NAME,
    case_lock,
    iso_now,
    load_json_object,
    load_running_context,
    relative_run_path,
    require_run_artifact,
    safe_identifier,
    sha256_file,
    validate_iso_date,
    write_private_json,
)
from opportunity_radar import validate_opportunity_handoff_payload

__all__ = ["register_source", "main"]

LOGGER = logging.getLogger(__name__)
SOURCE_TYPES = {
    "call",
    "formal_amendment",
    "annex",
    "official_faq",
    "portal_instructions",
    "form_template",
    "incorporated_law",
    "beneficiary_evidence",
    "quotation",
    "opportunity_handoff",
    "other",
}
AUTHORITY_ROLES = {
    "primary",
    "amending",
    "incorporated",
    "clarifying",
    "mechanical",
    "evidentiary",
    "unknown",
}


def _optional_date(value: str | None, *, field: str) -> str | None:
    return validate_iso_date(value, field=field) if value else None


def register_source(
    *,
    output_dir: Path,
    client_engagement: Path,
    source: Path,
    source_id: str,
    source_type: str,
    title: str,
    issuer: str,
    authority_role: str,
    selected_by: str,
    publication_date: str | None = None,
    effective_from: str | None = None,
    effective_to: str | None = None,
) -> dict[str, Any]:
    """Bind source metadata to exact selected input bytes without interpreting them."""

    source_id = safe_identifier(source_id, field="source_id")
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"unsupported source_type: {source_type}")
    if authority_role not in AUTHORITY_ROLES:
        raise ValueError(f"unsupported authority_role: {authority_role}")
    if not title.strip() or not issuer.strip() or not selected_by.strip():
        raise ValueError("title, issuer, and selected_by are required")
    context = load_running_context(
        client_engagement,
        output_dir=output_dir,
        input_paths=[source],
    )
    run_id = safe_identifier(context["run_id"], field="run_id")
    output_dir = output_dir.resolve()
    if source_type == "opportunity_handoff":
        if authority_role != "mechanical":
            raise ValueError("opportunity handoff authority_role must be mechanical")
        intake = require_run_artifact(output_dir / "case_intake.json", run_id=run_id)
        validate_opportunity_handoff_payload(
            load_json_object(source),
            expected_client_ref=str(intake["client_reference"]),
        )
    digest = sha256_file(source)
    record = {
        "source_id": source_id,
        "source_type": source_type,
        "title": title.strip(),
        "issuer": issuer.strip(),
        "authority_role": authority_role,
        "path": relative_run_path(source, context),
        "byte_count": source.stat().st_size,
        "sha256": digest,
        "publication_date": _optional_date(publication_date, field="publication_date"),
        "effective_from": _optional_date(effective_from, field="effective_from"),
        "effective_to": _optional_date(effective_to, field="effective_to"),
        "retrieved_at": iso_now(),
        "selected_by": selected_by.strip(),
        "review_status": "candidate",
        "relationships": [],
    }
    with case_lock(output_dir):
        register_path = output_dir / "source_register.json"
        register = require_run_artifact(register_path, run_id=run_id)
        sources = register.get("sources")
        if not isinstance(sources, list):
            raise ValueError("source_register.json has invalid sources")
        for existing in sources:
            if existing.get("source_id") == source_id:
                immutable_keys = {
                    "source_id",
                    "source_type",
                    "title",
                    "issuer",
                    "authority_role",
                    "path",
                    "byte_count",
                    "sha256",
                    "publication_date",
                    "effective_from",
                    "effective_to",
                    "selected_by",
                }
                stable_fields = {key: record.get(key) for key in immutable_keys}
                existing_stable = {key: existing.get(key) for key in immutable_keys}
                if existing_stable == stable_fields:
                    return existing
                raise ValueError("source_id already exists with different content")
            if existing.get("sha256") == digest:
                raise ValueError(
                    "the exact source bytes are already registered as "
                    f"{existing.get('source_id')}"
                )
        sources.append(record)
        register["source_set_revision"] = int(register["source_set_revision"]) + 1
        write_private_json(register_path, register)
        run_state_path = output_dir / "run_state.json"
        run_state = require_run_artifact(run_state_path, run_id=run_id)
        run_state.update(
            {
                "updated_at": iso_now(),
                "phase": "source_baseline_review",
                "status": "needs_review",
                "source_set_revision": register["source_set_revision"],
            }
        )
        write_private_json(run_state_path, run_state)
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--source-type", required=True, choices=sorted(SOURCE_TYPES))
    parser.add_argument("--title", required=True)
    parser.add_argument("--issuer", required=True)
    parser.add_argument(
        "--authority-role", required=True, choices=sorted(AUTHORITY_ROLES)
    )
    parser.add_argument("--selected-by", required=True)
    parser.add_argument("--publication-date")
    parser.add_argument("--effective-from")
    parser.add_argument("--effective-to")
    args = parser.parse_args(argv)
    record = register_source(
        output_dir=args.output_dir,
        client_engagement=args.client_engagement,
        source=args.source,
        source_id=args.source_id,
        source_type=args.source_type,
        title=args.title,
        issuer=args.issuer,
        authority_role=args.authority_role,
        selected_by=args.selected_by,
        publication_date=args.publication_date,
        effective_from=args.effective_from,
        effective_to=args.effective_to,
    )
    LOGGER.info("Registered %s (%s)", record["source_id"], record["sha256"])
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
