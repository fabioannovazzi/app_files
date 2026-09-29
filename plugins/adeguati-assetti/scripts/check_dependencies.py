"""Check declared manual-rendering dependencies without installing packages."""

from __future__ import annotations

import argparse
import importlib.util
import logging

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Check the existing managed runtime; never install packages during a case."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements", choices=["requirements.txt"], default="requirements.txt"
    )
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    missing = [
        name for name in ("docx", "reportlab") if importlib.util.find_spec(name) is None
    ]
    if missing:
        logging.error(
            "Missing declared manual dependencies: %s; use Vera's managed runtime setup",
            ", ".join(missing),
        )
        return 1
    logging.info("Assetti dependencies are available in this runtime.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
