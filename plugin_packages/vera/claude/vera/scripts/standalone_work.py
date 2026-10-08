"""Create a selected standalone task without Studio Archive setup or registration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    vendor = next(
        path
        for path in (
            root / "vendor" / "modules",
            root.parent / "_shared" / "vendor" / "modules",
        )
        if (path / "vera_assurance").is_dir()
    )
    sys.path.insert(0, str(vendor))
    from vera_assurance.contracts import create_standalone_task

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--purpose", required=True)
    args = parser.parse_args(argv)
    context = create_standalone_task(
        args.destination,
        workflow_id=args.workflow,
        sources=args.source,
        label=args.label,
        purpose=args.purpose,
    )
    sys.stdout.write(json.dumps(context, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
