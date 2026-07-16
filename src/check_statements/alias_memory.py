from __future__ import annotations

"""Alias memory: persist and apply learned global alias rules.

V1 stores a simple global mapping from a normalised name token to its
canonical normalised form. Scoping fields (company_key, bank_key) are
reserved for future use but unused in V1.

Rules are persisted under the cache root as ``statement_alias_rules.json``.
The file format is intentionally simple and tolerant:

{ "map": {"supplieralpha": "supplieralphaltd", ...}, "meta": {"version": 1} }

or just a bare mapping {"supplieralpha": "supplieralphaltd"} for backward compatibility.
"""

import json
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

# Tolerant import so unit tests without full app modules still run
try:  # pragma: no cover - exercised via integration
    from modules.utilities.cache import get_cache_path  # type: ignore
except Exception:  # pragma: no cover - fallback for isolated tests
    logger.warning("modules.utilities.cache import failed; using fallback cache path")

    def get_cache_path(name: str) -> Path:  # type: ignore
        p = Path(".cache_fallback").resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p.parent / name


def get_alias_rules_path() -> Path:
    """Return the JSON path used to persist alias rules."""
    return get_cache_path("statement_alias_rules.json")


def load_alias_rules(path: Path | None = None) -> Dict[str, str]:
    """Load the alias mapping (normalised -> canonical normalised).

    Returns an empty dict if the file does not exist or is invalid.
    """
    p = path or get_alias_rules_path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load alias rules %s: %s", p, exc)
        return {}
    if isinstance(raw, dict) and "map" in raw and isinstance(raw["map"], dict):
        return {str(k): str(v) for k, v in raw["map"].items()}
    if isinstance(raw, dict):
        # Tolerate bare mapping format
        try:
            return {str(k): str(v) for k, v in raw.items()}
        except Exception:
            return {}
    return {}


def save_alias_rules(mapping: Dict[str, str], path: Path | None = None) -> None:
    """Persist the alias mapping to disk.

    The file contains a top-level ``map`` key to allow future metadata.
    """
    p = path or get_alias_rules_path()
    try:
        p.write_text(
            json.dumps(
                {"map": mapping, "meta": {"version": 1}}, ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to save alias rules %s: %s", p, exc)


def apply_alias_to_norm(name_norm: str, mapping: Dict[str, str]) -> str:
    """Return canonical normalised name using ``mapping`` (no-op if missing).

    Expects ``name_norm`` to be already normalised (e.g., via
    :func:`parsers.extractors.normalise_name`). In V1 we just map exact
    tokens; later we may add prefix/regex or scoped variants.
    """
    try:
        if not name_norm:
            return name_norm
        return mapping.get(name_norm, name_norm)
    except Exception:  # pragma: no cover - defensive
        return name_norm


__all__ = (
    "get_alias_rules_path",
    "load_alias_rules",
    "save_alias_rules",
    "apply_alias_to_norm",
)
