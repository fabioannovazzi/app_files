"""Create Codex mapping tasks from a deterministic evidence package."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from attribute_reporting import ContractError, create_mapping_tasks

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def _load_central_taxonomy(app_root: Path) -> dict:
    root = app_root.expanduser().resolve()
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    from modules.add_attributes.attribute_taxonomy import (  # noqa: PLC0415
        get_runtime_attribute_taxonomy,
    )

    return get_runtime_attribute_taxonomy()


def main() -> int:
    """Load the central taxonomy and write an unresolved mapping workset."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=0,
        help="Maximum tasks to write; zero keeps the complete workset.",
    )
    parser.add_argument(
        "--include-resolved",
        action="store_true",
        help="Recheck existing values during a deliberate legacy-model migration.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        taxonomy = _load_central_taxonomy(args.app_root)
        result = create_mapping_tasks(
            args.package_dir,
            taxonomy,
            args.output,
            max_tasks=args.max_tasks,
            include_resolved=args.include_resolved,
        )
    except (ContractError, FileNotFoundError, ImportError) as exc:
        LOGGER.error("Mapping task creation failed: %s", exc)
        return 1
    coverage = result["coverage"]
    LOGGER.info(
        "Created %s unresolved mapping tasks (truncated=%s)",
        coverage["task_count"],
        coverage["truncated"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
