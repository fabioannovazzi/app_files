"""Index advisory source materials in place."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from advisor_case_core import MATERIAL_TYPES, index_materials

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _parse_source_metadata(raw_metadata: str | None) -> dict[str, Any]:
    """Return source metadata supplied as a JSON object."""

    if not raw_metadata:
        return {}
    try:
        parsed = json.loads(raw_metadata)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(
            f"--source-metadata must be valid JSON: {exc.msg}"
        ) from exc
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("--source-metadata must be a JSON object")
    return parsed


def main() -> int:
    """Run material indexing."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("materials", nargs="+", type=Path)
    parser.add_argument(
        "--material-type",
        default="source",
        choices=sorted(MATERIAL_TYPES),
    )
    parser.add_argument(
        "--provenance-note",
        help="Store a provenance note under source_metadata.provenance_note.",
    )
    parser.add_argument(
        "--source-metadata",
        help="Merge an arbitrary source_metadata JSON object into each indexed material.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        source_metadata = _parse_source_metadata(args.source_metadata)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    if args.provenance_note:
        source_metadata["provenance_note"] = args.provenance_note

    indexed = index_materials(
        args.case_dir,
        args.materials,
        material_type=args.material_type,
        source_metadata=source_metadata,
    )
    LOGGER.info("Indexed %s material(s).", len(indexed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
