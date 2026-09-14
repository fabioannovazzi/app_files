"""Check the published XML and PDF dependencies without installing packages."""

from __future__ import annotations

import argparse
import importlib.util
import logging

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Require the declared managed-runtime modules."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", action="append", choices=["requirements.txt"])
    parser.parse_args(argv)
    missing = [
        name for name in ("lxml", "fitz") if importlib.util.find_spec(name) is None
    ]
    if missing:
        logging.error("Missing declared dependencies: %s", ", ".join(missing))
        return 1
    logging.info("XML schema and PDF dependencies are available.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
