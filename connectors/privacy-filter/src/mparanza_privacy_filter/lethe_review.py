"""Prepare Lethe's local review file; approval and identity values stay out of chat."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .extract import extract_text

__all__ = ["main"]


def main() -> None:
    """Collect upstream detections across the complete job for local review."""
    from lethe.core import detect
    from lethe.store import load_entities

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("documents", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    text = "\n\n".join(extract_text(path) for path in args.documents)
    items = detect(text, load_entities())
    with args.output.open("x", encoding="utf-8") as handle:
        args.output.chmod(0o600)
        json.dump(
            {"approved": False, "items": [asdict(item) for item in items]},
            handle,
            ensure_ascii=False,
            indent=2,
        )


if __name__ == "__main__":
    main()
