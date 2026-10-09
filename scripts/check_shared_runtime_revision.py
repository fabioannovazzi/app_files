"""Reject shared runtime recipe changes without a coordinated policy upgrade."""

from __future__ import annotations

import argparse
import ast
import logging
import subprocess
from pathlib import Path
from typing import Callable

__all__ = ["verify_policy", "main"]
PRODUCTS = ("vera", "clara", "lucia")
FILES = (
    "requirements-shared-core.txt",
    "requirements-shared-ocr.txt",
    "constraints-shared-macos-py312.txt",
    "scripts/_shared_python_runtime.py",
)
BACKEND = FILES[-1]
LOGGER = logging.getLogger(__name__)


def _revision(source: bytes) -> int:
    for statement in ast.parse(source).body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "POLICY_REVISION"
            for target in statement.targets
        ):
            value = ast.literal_eval(statement.value)
            if type(value) is int and value > 0:
                return value
    raise ValueError("Shared runtime policy has no positive integer revision")


def verify_policy(root: Path, previous: Callable[[str], bytes] | None = None) -> int:
    """Verify product parity and monotonic revisions against a release baseline."""
    current = {
        product: {
            name: (root / "plugins" / product / name).read_bytes() for name in FILES
        }
        for product in PRODUCTS
    }
    canonical = current["vera"]
    for product in PRODUCTS:
        if current[product] != canonical:
            raise ValueError(f"{product}: shared runtime policy differs from Vera")
    revision = _revision(canonical[BACKEND])
    if previous is not None:
        for product in PRODUCTS:
            old = {name: previous(f"plugins/{product}/{name}") for name in FILES}
            old_revision = _revision(old[BACKEND])
            if revision < old_revision:
                raise ValueError(f"{product}: shared runtime revision cannot decrease")
            if current[product] != old and revision <= old_revision:
                raise ValueError(
                    f"{product}: shared runtime files changed without increasing "
                    f"POLICY_REVISION above {old_revision}"
                )
    return revision


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--base-ref", help="Trusted Git commit before this release")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        previous: Callable[[str], bytes] | None = None
        if args.base_ref:
            baseline = subprocess.check_output(
                ["git", "rev-parse", "--verify", f"{args.base_ref}^{{commit}}"],
                cwd=args.root,
                text=True,
            ).strip()

            def read_previous(path: str) -> bytes:
                return subprocess.check_output(
                    ["git", "show", f"{baseline}:{path}"], cwd=args.root
                )

            previous = read_previous
        revision = verify_policy(args.root, previous)
    except (OSError, ValueError, SyntaxError, subprocess.CalledProcessError) as error:
        LOGGER.error("Shared runtime release rejected: %s", error)
        return 1
    LOGGER.info("[OK] Shared runtime policy revision %s", revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
