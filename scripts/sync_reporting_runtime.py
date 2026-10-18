"""Distribute one reporting implementation to each standalone product package."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

__all__ = ["synchronize", "main"]
ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ("vera", "clara", "lucia")
LOGGER = logging.getLogger(__name__)


def synchronize(root: Path = ROOT, *, check: bool = False) -> list[str]:
    """Compare exact source bytes; packaging may never silently fork this runtime."""
    differences = []
    for source in sorted((root / "plugins/_shared/reporting-runtime").iterdir()):
        if source.suffix not in {".py", ".cjs"}:
            continue
        content = source.read_bytes()
        for product in PRODUCTS:
            target = root / "plugins" / product / "scripts" / source.name
            if not target.is_file() or target.read_bytes() != content:
                differences.append(str(target.relative_to(root)))
                if not check:
                    target.write_bytes(content)
    return differences


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    differences = synchronize(check=args.check)
    if args.check and differences:
        LOGGER.error("Shared reporting source drift: %s", ", ".join(differences))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
