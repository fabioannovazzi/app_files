"""Distribute the same privacy governance implementation to all three products."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

__all__ = ["main", "synchronize"]
ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ("vera", "clara", "lucia")
LOGGER = logging.getLogger(__name__)


def synchronize(root: Path = ROOT, *, check: bool = False) -> list[str]:
    """Check exact bytes, a mechanical guarantee against product-specific forks."""
    differences = []
    source_root = root / "plugins/_shared/privacy-runtime"
    for source in sorted(source_root.rglob("*")):
        if not source.is_file() or "__pycache__" in source.parts:
            continue
        relative = source.relative_to(source_root)
        for product in PRODUCTS:
            targets = [root / "plugins" / product / relative]
            if relative.as_posix() in {
                "skills/privacy-surface-review/references/model-data-report-contract.md",
                "skills/privacy-surface-review/references/public-process-page-contract.md",
            }:
                targets.append(
                    root
                    / f"plugins/{product}/skills/{product}/references/{relative.name}"
                )
            for target in targets:
                if not target.is_file() or target.read_bytes() != source.read_bytes():
                    differences.append(target.relative_to(root).as_posix())
                    if not check:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(source.read_bytes())
    return differences


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    differences = synchronize(check=args.check)
    if args.check and differences:
        LOGGER.error("Shared privacy source drift: %s", ", ".join(differences))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
