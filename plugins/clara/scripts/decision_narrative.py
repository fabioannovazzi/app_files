"""Store model-authored decision prose against current case and approval identity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from case_store import atomic_text

__all__ = ["NARRATIVE_FILENAME", "commit_narrative", "load_narrative"]
NARRATIVE_FILENAME = "decision_narrative.json"


def _validate(payload: dict[str, Any], approved_claim_ids: set[str]) -> list[str]:
    if not isinstance(payload, dict):
        raise ValueError("Decision narrative must be a JSON object")
    review = payload.get("review", {})
    if not isinstance(review, dict):
        raise ValueError("Decision narrative review must be an object")
    if (
        review.get("status") not in {"model_reviewed", "human_reviewed"}
        or not str(review.get("reviewed_by", "")).strip()
    ):
        raise ValueError("Decision narrative requires a recorded model or human review")
    paragraphs = payload.get("paragraphs")
    if not isinstance(paragraphs, list) or not paragraphs:
        raise ValueError("Decision narrative requires model-authored paragraphs")
    result = []
    for paragraph in paragraphs:
        if not isinstance(paragraph, dict):
            raise ValueError("Each narrative paragraph must be an object")
        text = paragraph.get("text", "")
        claims = paragraph.get("claim_ids", [])
        if (
            not isinstance(text, str)
            or not text.strip()
            or not isinstance(claims, list)
            or not claims
        ):
            raise ValueError(
                "Each narrative paragraph needs text and declared claim IDs"
            )
        if not all(isinstance(claim, str) for claim in claims):
            raise ValueError("Narrative claim IDs must be strings")
        if not set(claims).issubset(approved_claim_ids):
            raise ValueError(
                "Decision narrative references unapproved or unknown claims"
            )
        result.append(text.strip())
    return result


def commit_narrative(
    case_dir: Path,
    authored: Path,
    *,
    basis: dict[str, Any],
    approved_claim_ids: set[str],
) -> Path:
    """Bind authored prose, not register order, to an exact reviewed case basis."""
    payload = json.loads(authored.read_text(encoding="utf-8"))
    _validate(payload, approved_claim_ids)
    payload["schema_version"] = 1
    payload["basis"] = basis
    payload["boundary"] = (
        "Paragraph meaning and completeness were reviewed by the declared reviewer; code checks identity and approval references only."
    )
    path = case_dir / NARRATIVE_FILENAME
    atomic_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path


def load_narrative(
    case_dir: Path, *, basis: dict[str, Any] | None, approved_claim_ids: set[str]
) -> list[str]:
    """Return current authored paragraphs; never fabricate a missing recommendation."""
    path = case_dir / NARRATIVE_FILENAME
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or basis is None or payload.get("basis") != basis:
        raise ValueError(
            "Decision narrative is stale; review the current workpaper and commit updated prose"
        )
    return _validate(payload, approved_claim_ids)
