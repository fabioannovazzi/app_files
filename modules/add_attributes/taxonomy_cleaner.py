from __future__ import annotations

"""One-shot cleaner for the attribute taxonomy storage.

Loads the taxonomy, normalizes each category branch to remove null
children/synonyms, enforces schema rules (leaf-only synonyms, boolean
hierarchical, unknown/other presence), prunes per budgets, and saves the
file back (with an optional backup).
"""

from datetime import datetime, timezone
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .attribute_taxonomy import (
    TAXONOMY_PATH,
    get_attribute_taxonomy,
    save_attribute_taxonomy,
)
from .taxonomy_schema import validate_branch, branch_metrics

__all__ = ["clean_taxonomy", "clean_taxonomy_file"]


def clean_taxonomy(taxonomy: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Return a cleaned taxonomy and a per-category summary.

    The summary contains category id/label, warnings, and metrics before/after.
    """
    categories = taxonomy.get("categories", []) or []
    out_categories: List[Dict[str, Any]] = []
    report: List[Dict[str, Any]] = []
    for cat in categories:
        # Compute pre metrics
        pre_metrics = branch_metrics(cat)
        cleaned, warnings = validate_branch(cat)
        post_metrics = branch_metrics(cleaned)
        out_categories.append(cleaned)
        report.append(
            {
                "id": cleaned.get("id", cat.get("id")),
                "label": cleaned.get("label", cat.get("label")),
                "warnings": warnings,
                "before": pre_metrics,
                "after": post_metrics,
            }
        )

    new_tax = dict(taxonomy)
    new_tax["categories"] = out_categories
    return new_tax, report


def _write_backup(path: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if path.is_dir() or path.suffix.lower() != ".json":
        backup = path.with_name(f"{path.name}.{ts}.bak")
        shutil.copytree(path, backup)
        return backup
    backup = path.with_suffix(path.suffix + f".{ts}.bak")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup


def clean_taxonomy_file(path: Path | None = None, *, backup: bool = True) -> List[Dict[str, Any]]:
    """Clean the taxonomy file in-place. Returns a per-category report.

    Parameters
    ----------
    path: Optional override of the taxonomy path. Defaults to TAXONOMY_PATH.
    backup: If True, writes a timestamped backup before saving.
    """
    path = path or TAXONOMY_PATH
    tax = get_attribute_taxonomy()
    if backup:
        _write_backup(path)
    cleaned, report = clean_taxonomy(tax)
    save_attribute_taxonomy(cleaned)
    return report
