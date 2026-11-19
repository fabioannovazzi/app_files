"""Reject source/release drift while allowing build-only previews of deferred products."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from pathlib import Path

__all__ = ["check_drift", "main"]
PRODUCTS = ("vera", "clara", "lucia")
ROOT = Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True)


def _artifact_product(path: str) -> str | None:
    for product in PRODUCTS:
        if path.startswith(f"plugin_packages/{product}/") or path in (
            f"static/shared/{product}/downloads/{product}-cowork-plugin.zip",
            f"static/shared/{product}/downloads/{product}-antigravity-plugin.zip",
        ):
            return product
    return None


def check_drift(root: Path, base: str) -> list[str]:
    """Use exact Git/version comparisons so source drift can never be waived."""
    if not base or set(base) == {"0"}:
        base = "HEAD^"
    changed = _git(root, "diff", "--name-only", base, "HEAD").splitlines()
    released = {_artifact_product(path) for path in changed}
    for product in PRODUCTS:
        manifest = f"plugins/{product}/.codex-plugin/plugin.json"
        before = json.loads(_git(root, "show", f"{base}:{manifest}"))["version"]
        after = json.loads((root / manifest).read_text())["version"]
        if before != after:
            released.add(product)
    drift = _git(root, "diff", "--name-only", "HEAD").splitlines()
    return [
        path
        for path in drift
        if _artifact_product(path) is None or _artifact_product(path) in released
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    args = parser.parse_args()
    errors = check_drift(ROOT, args.base)
    for path in errors:
        logging.error("Build drift: %s", path)
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
