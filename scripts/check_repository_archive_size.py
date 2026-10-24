"""Keep the source download below the Claude directory's 256 MiB limit."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

__all__ = ["archive_size", "main"]

ROOT = Path(__file__).resolve().parents[1]
MIB = 1024 * 1024
MAX_ARCHIVE_BYTES = 230 * MIB
LOGGER = logging.getLogger(__name__)


def archive_size(root: Path) -> int:
    """Measure the compressed HEAD tree, without loading the archive into RAM."""
    with tempfile.TemporaryFile() as archive:
        subprocess.run(
            ["git", "archive", "--format=tar.gz", "HEAD"],
            cwd=root,
            stdout=archive,
            check=True,
        )
        return archive.tell()


def main() -> int:
    """Enforce measured byte headroom before a directory download can be refused."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        size = archive_size(ROOT)
    except (OSError, subprocess.CalledProcessError) as exc:
        LOGGER.error("Cannot measure repository archive: %s", exc)
        return 1
    # Exact byte arithmetic enforces the provider's compressed-download limit.
    if size > MAX_ARCHIVE_BYTES:
        LOGGER.error(
            "Repository archive is %d bytes (%.2f MiB), above the 230 MiB guard. "
            "The Claude directory refuses downloads above 256 MiB. "
            "Remove generated artifacts from Git before merging.",
            size,
            size / MIB,
        )
        return 1
    LOGGER.info(
        "Repository archive: %d bytes (%.2f MiB); within the 230 MiB guard "
        "for the Claude directory's 256 MiB limit.",
        size,
        size / MIB,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
