"""Publish the deterministic fictional course catalogue into static assets."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
from pathlib import Path

from build_catalog import ROOT
from render_catalog import render

__all__ = ["build_public", "main"]


def _manifest(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory)
        .as_posix(): hashlib.sha256(path.read_bytes())
        .hexdigest()
        for path in directory.rglob("*")
        if path.is_file()
    }


def build_public(*, check: bool = False) -> int:
    """Rebuild only compiler-owned public files; preserve other static content."""
    target = ROOT / "static/shared/courses"
    if target.is_symlink():
        raise ValueError("Public catalogue must not be a symlink")
    with tempfile.TemporaryDirectory(prefix="teaching-public-") as temporary:
        generated = Path(temporary).resolve() / "courses"
        render(generated, public=True)
        expected = _manifest(generated)
        if check:
            if _manifest(target) != expected:
                raise ValueError(
                    "Public catalogue is stale; run build_public_catalog.py"
                )
        else:
            target.mkdir(parents=True, exist_ok=True)
            for relative in _manifest(target).keys() - expected.keys():
                (target / relative).unlink()
            shutil.copytree(generated, target, dirs_exist_ok=True)
    return len(expected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    print(f"Public catalogue: {build_public(check=parser.parse_args().check)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
