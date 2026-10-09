"""Isolated replay of already reviewed source groups; no semantic worker."""

from __future__ import annotations

import json
import sys
from pathlib import Path

__all__ = ["main"]


def main() -> None:
    root = Path(sys.argv[1])
    if root.name != "passive-invoice-audit" or root.is_symlink():
        raise PermissionError("Unsupported reviewed invoice reader")
    sys.path.insert(0, str(root / "scripts"))
    from reviewed_invoices import load_reviewed_invoices

    request = json.loads(sys.stdin.read(8001))
    if set(request) != {"population"}:
        raise ValueError("Unknown source-group request")
    rows = load_reviewed_invoices(Path(request["population"]))
    sys.stdout.write(
        json.dumps(
            {
                "invoice_count": len(rows),
                "extraction_sha256": rows[0]["extraction_sha256"],
                "professional_approval": False,
            }
        )
    )


if __name__ == "__main__":
    main()
