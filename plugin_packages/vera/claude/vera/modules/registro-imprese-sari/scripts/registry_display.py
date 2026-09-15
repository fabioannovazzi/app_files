"""Translate fixed interface labels without changing authored case content."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

__all__ = ["text", "status", "handoff"]


@lru_cache(maxsize=1)
def _copy() -> dict[str, dict[str, str]]:
    path = Path(__file__).resolve().parents[1] / "assets/registry-display.json"
    return json.loads(path.read_text(encoding="utf-8"))


def text(language: str, key: str) -> str:
    """Look up a fixed label; never translate or classify user-authored text."""
    return _copy()[_language(language)][key]


def status(language: str, value: object) -> str:
    """Present declared machine states; leave unknown values visible."""
    key = f"status.{value}"
    return _copy()[_language(language)].get(key, str(value or "—"))


def _language(value: str) -> str:
    primary = value.lower().replace("_", "-").split("-", 1)[0]
    primary = {"eng": "en", "ita": "it", "fra": "fr", "deu": "de", "spa": "es"}.get(
        primary, primary
    )
    return primary if primary in {"it", "en", "fr", "de", "es"} else "it"


def handoff(language: str) -> list[str]:
    """Describe the real review sequence and its limits in the run language."""
    return [
        "# " + text(language, "handoff_title"),
        "<!-- Review Handoff -->",
        "",
        text(language, "handoff_intro"),
        "",
        "1. " + text(language, "handoff_read"),
        "2. " + text(language, "handoff_decide"),
        "3. " + text(language, "handoff_confirm"),
        "",
        text(language, "handoff_boundary"),
        "",
        "<details><summary>" + text(language, "technical_evidence") + "</summary>",
        "",
        "1. "
        + text(language, "handoff_validate")
        + " `validate_registro_imprese_sari_review`.",
        "2. "
        + text(language, "handoff_render")
        + " `render_registro_imprese_sari_review`.",
        "3. "
        + text(language, "handoff_save")
        + " `save_registro_imprese_sari_decisions`.",
        "4. "
        + text(language, "handoff_apply")
        + " `apply_registro_imprese_sari_decisions`.",
        "",
        "review_payload.json → ui_decisions.json → applied_decisions.json → final_artifacts.json.",
        "",
        "</details>",
        "",
    ]
