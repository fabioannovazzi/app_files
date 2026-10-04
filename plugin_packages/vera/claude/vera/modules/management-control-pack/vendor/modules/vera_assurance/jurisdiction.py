"""Mechanical source and decision bindings for jurisdiction-specific adapters.

Professional applicability and source selection remain authored judgments.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

__all__ = ["text", "digest", "citations", "validate_envelope", "seal", "save", "run"]


def text(value: Any, name: str) -> str:
    """Require bounded explicit text; do not interpret its meaning."""
    if not isinstance(value, str) or not value.strip() or len(value) > 20000:
        raise ValueError(f"Missing or invalid {name}")
    return value


def digest(value: Any) -> str:
    """Bind exact JSON content."""
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def citations(rows: Any, source_ids: set[str]) -> None:
    """Check explicit source references without validating their interpretation."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("Source citations are required")
    for row in rows:
        if not isinstance(row, dict) or row.get("source_id") not in source_ids:
            raise ValueError("Unknown cited source")
        text(row.get("locator"), "source locator")


def validate_envelope(payload: dict[str, Any], input_root: Path) -> dict[str, Any]:
    """Check the Geneva adapter envelope and exact local source bytes."""
    payload = copy.deepcopy(payload)
    if payload.get("schema_version") != 1 or payload.get("jurisdiction") != "CH-GE":
        raise ValueError("Expected version 1 CH-GE adapter input")
    if payload.get("language") not in {"fr", "en", "it", "de", "es"}:
        raise ValueError("Select output language independently of jurisdiction")
    as_of = date.fromisoformat(text(payload.get("as_of"), "as_of"))
    text(payload.get("jurisdiction_basis"), "jurisdiction basis")
    text(payload.get("limitations"), "limitations")
    source_ids: set[str] = set()
    if not isinstance(payload.get("sources"), list) or not payload["sources"]:
        raise ValueError("Imported sources are required")
    for source in payload["sources"]:
        identity = text(source.get("id"), "source ID")
        if identity in source_ids:
            raise ValueError("Duplicate source ID")
        source_ids.add(identity)
        text(source.get("title"), "source title")
        relative = Path(text(source.get("path"), "source path"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Source path must be relative to run inputs")
        resolved = (input_root / relative).resolve(strict=True)
        if not resolved.is_relative_to(input_root.resolve()) or not resolved.is_file():
            raise ValueError("Source leaves bound inputs")
        if hashlib.sha256(resolved.read_bytes()).hexdigest() != source.get("sha256"):
            raise ValueError("Source digest mismatch")
    if not isinstance(payload.get("legal_basis"), list) or not payload["legal_basis"]:
        raise ValueError("Applicable professional sources are required")
    for basis in payload["legal_basis"]:
        for key in ("title", "locator", "applicability"):
            text(basis.get(key), f"legal basis {key}")
        url = urlsplit(text(basis.get("url"), "source URL"))
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError(
                "Expected public HTTPS source reference without credentials"
            )
        if date.fromisoformat(basis["checked_at"]) > as_of:
            raise ValueError("Source check date is after assessment date")
    return payload


def seal(
    payload: dict[str, Any],
    results: dict[str, Any],
    *,
    workflow_id: str,
    client_id: str,
    engagement_id: str,
) -> dict[str, Any]:
    """Bind professional decisions to the exact reviewed proposal and outputs."""
    proposal = {k: v for k, v in payload.items() if k != "professional_decision"}
    proposal_hash = digest(
        {
            "input": proposal,
            "results": results,
            "workflow_id": workflow_id,
            "client_id": client_id,
            "engagement_id": engagement_id,
        }
    )
    decision = payload.get("professional_decision")
    if decision is not None:
        if decision.get("proposal_sha256") != proposal_hash:
            raise ValueError("Professional decision does not bind this proposal")
        for key in ("reviewer_ref", "conclusion"):
            text(decision.get(key), key)
        if date.fromisoformat(decision["reviewed_at"]) < date.fromisoformat(
            payload["as_of"]
        ):
            raise ValueError("Review precedes the assessment")
    record = {
        "schema_version": 1,
        "workflow_id": workflow_id,
        "client_id": text(client_id, "client ID"),
        "engagement_id": text(engagement_id, "engagement ID"),
        "status": "professional_decision_recorded" if decision else "draft_for_review",
        "proposal_sha256": proposal_hash,
        "review": payload,
        "results": results,
    }
    record["record_sha256"] = digest(record)
    return record


def save(record: dict[str, Any], memo: str, output: Path) -> Path:
    """Append content-addressed private artifacts without replacing earlier work."""
    if record.get("record_sha256") != digest(
        {k: v for k, v in record.items() if k != "record_sha256"}
    ):
        raise ValueError("Record changed after validation")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = output / f'{record["workflow_id"]}-{record["record_sha256"]}.json'
    for target, content in (
        (
            path,
            json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        ),
        (path.with_suffix(".md"), memo),
    ):
        if target.exists():
            if target.is_symlink() or target.read_text() != content:
                raise ValueError("Existing artifact differs from the bound record")
        else:
            with target.open("x", encoding="utf-8") as handle:
                target.chmod(0o600)
                handle.write(content)
    return path


def run(
    workflow_id: str,
    build: Callable[..., dict[str, Any]],
    render: Callable[[dict[str, Any]], str],
) -> int:
    """Execute one adapter in its existing started Studio Archive workflow."""
    from vera_assurance import load_client_engagement_context_file

    parser = argparse.ArgumentParser(
        description=f"Prepare a reviewed {workflow_id} dossier"
    )
    parser.add_argument("--client-engagement", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    args = parser.parse_args()
    context = load_client_engagement_context_file(
        args.client_engagement,
        expected_workflow_id=workflow_id,
        input_paths=[args.review],
    )
    if context["schema_version"] != "vera.client_workflow_context.v2":
        raise ValueError("A portable v2 Studio Archive run is required")
    payload = json.loads(args.review.read_text())
    input_root = Path(context["run_root"]) / "inputs"
    validate_envelope(payload, input_root)
    load_client_engagement_context_file(
        args.client_engagement,
        expected_workflow_id=workflow_id,
        input_paths=[input_root / row["path"] for row in payload["sources"]],
    )
    record = build(
        payload,
        input_root=input_root,
        client_id=context["client_id"],
        engagement_id=context["engagement_id"],
    )
    logging.info("Saved %s", save(record, render(record), Path(context["output_dir"])))
    return 0
