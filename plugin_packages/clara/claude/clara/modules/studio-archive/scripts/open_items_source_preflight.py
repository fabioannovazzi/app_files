"""Read-only capability and cell checks before creating Archive records."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS = (
    Path(__file__).resolve().parent.parent.parent / "open-item-reconciliation/scripts"
)
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import audit_assurance as assurance  # noqa: E402

__all__ = ["check_sources", "main"]


def check_sources(request: dict[str, Any]) -> dict[str, Any]:
    """Replay agent-selected tabular mappings against actual bytes, without writes."""
    sources = request["sources"]
    if not sources:
        raise ValueError("Select the reconciliation sources.")
    checked = []
    for source in sources:
        path = Path(source["path"]).resolve(strict=True)
        mapping = source["mapping"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if source.get("sha256") is not None and source["sha256"] != digest:
            raise ValueError(f"Selected source hash changed: {path}")
        receipts = assurance.build_source_receipts(path.parent, [path])
        decisions, errors = assurance.build_reviewed_source_decisions(
            input_root=path.parent,
            source_receipts=receipts,
            adapter_families={path.name: mapping["adapter_family"]},
            assumptions={
                **request.get("assumptions", {}),
                "reviewed_source_decisions": {path.name: mapping},
            },
        )
        if errors:
            raise ValueError(str(errors))
        rows = (
            assurance.read_reviewed_tabular_source(path, decisions[path.name])
            if mapping["adapter_family"] == assurance.TABULAR_ADAPTER
            else None
        )
        checked.append(
            {
                "path": str(path),
                "sha256": digest,
                "role": mapping["role"],
                "rows": len(rows) if rows is not None else None,
            }
        )
    return {"status": "source_capability_checked", "sources": checked}


def main() -> int:
    try:
        result = check_sources(json.load(sys.stdin))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
