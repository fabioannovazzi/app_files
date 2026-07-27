#!/usr/bin/env python3
"""Bind locally hydrated image hashes to a public server mapping workset."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from hydrate_images import HydrationError, bind_images_to_mapping_tasks

__all__ = ["main"]

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Write a locally enriched mapping task artifact."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", type=Path)
    parser.add_argument("--image-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = bind_images_to_mapping_tasks(
            args.tasks,
            args.image_manifest,
            args.output,
        )
    except HydrationError as exc:
        LOGGER.error("Mapping image binding failed: %s", exc)
        return 1
    LOGGER.info(
        "Bound local images to %s of %s mapping tasks",
        result["image_bound_task_count"],
        result["task_count"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
