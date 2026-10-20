"""Evaluate a published dependency lock inside the selected CPython runtime."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

__all__ = ["locked_versions", "main"]


def locked_versions(
    path: Path, environment: dict[str, str] | None = None
) -> dict[str, str]:
    """Require exact versions and hashes, selecting markers on the target host."""
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    versions: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").replace("\\\n", " ").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        requirement_text, *hashes = line.split("--hash=")
        requirement = Requirement(requirement_text.strip())
        specifiers = list(requirement.specifier)
        if (
            requirement.url
            or len(specifiers) != 1
            or specifiers[0].operator != "=="
            or "*" in specifiers[0].version
            or not hashes
            or any(not re.fullmatch(r"sha256:[0-9a-f]{64}", h.strip()) for h in hashes)
        ):
            raise ValueError(
                f"Dependency lock must pin versions and SHA-256: {requirement.name}"
            )
        if requirement.marker and not requirement.marker.evaluate(environment):
            continue
        name = canonicalize_name(requirement.name)
        version = specifiers[0].version
        if name in versions and versions[name] != version:
            raise ValueError(f"Conflicting locked versions for {name}")
        versions[name] = version
    return versions


def main() -> int:
    # Called with -I -S: import only this venv's packages, without running .pth
    # hooks or taking a reader lease while the installer holds the writer lock.
    sites = (
        [Path(sys.executable).parent.parent / "Lib/site-packages"]
        if sys.platform == "win32"
        else list(Path(sys.executable).parent.parent.glob("lib/python*/site-packages"))
    )
    if len(sites) != 1:
        raise ValueError("Cannot identify the managed runtime's site-packages")
    sys.path.insert(0, str(sites[0]))
    sys.stdout.write(
        json.dumps(locked_versions(Path(sys.argv[1])), sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
