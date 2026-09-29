"""CNC uses the standard library and the existing Vera archive contract."""

from __future__ import annotations

import argparse
import logging

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Verify that the packaged archive dependency can be loaded."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--requirements", choices=["requirements.txt"], default="requirements.txt"
    )
    parser.parse_args(argv)
    from cnc_case import _dependencies

    _dependencies()
    logging.info("CNC: standard library and Studio Archive available")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
