"""Check declared report dependencies without installing packages at runtime."""

from __future__ import annotations

import argparse
import importlib.metadata
import logging

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Check the declared requirement set and supported installed versions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements", choices=["requirements.txt"], default="requirements.txt"
    )
    parser.parse_args(argv)
    for package, minimum, maximum in (
        ("jsonschema", (4, 23), (5, 0)),
        ("openpyxl", (3, 1), (4, 0)),
        ("python-docx", (1, 1), None),
        ("reportlab", (4, 0), (5, 0)),
    ):
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc:
            raise SystemExit(
                f"Use Vera's declared shared environment for {package}"
            ) from exc
        try:
            parts = tuple(int(value) for value in version.split(".")[:2])
        except ValueError as exc:
            raise SystemExit(
                f"Unsupported installed version for {package}: {version}"
            ) from exc
        if parts < minimum or (maximum is not None and parts >= maximum):
            raise SystemExit(f"Use Vera's declared shared environment for {package}")
        logging.info("%s %s", package, version)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
