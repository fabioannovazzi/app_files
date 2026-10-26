"""Exclude lesson data from packages while pinning immutable public copies."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from .public_files import resolve_public_file
except ImportError:  # Direct script entry point.
    from public_files import resolve_public_file

__all__ = [
    "externalize_course_files",
    "immutable_path",
    "publish_remote_files",
    "withdrawn_public_lesson",
]

ROOT = Path(__file__).resolve().parents[2]
PRODUCTS = frozenset({"vera", "clara", "lucia"})


def _publication_policy(root: Path) -> dict[str, Any]:
    path = root / "scripts/course_materials/publication_policy.json"
    return json.loads(path.read_bytes()) if path.is_file() else {}


def withdrawn_public_lesson(root: Path, product: str, workflow: str) -> bool:
    """Apply the owner's explicit lesson withdrawals, never infer from absence."""
    return f"{product}/{workflow}" in _publication_policy(root).get(
        "withdrawn_lessons", []
    )


def _relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError(f"Invalid course attachment path: {value}")
    return path


def immutable_path(asset: dict[str, Any]) -> str:
    """Name a passive attachment by its exact bytes and original filename."""
    digest = asset["sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Invalid course attachment hash")
    return f"_files/{digest}/{_relative(asset['path']).name}"


def publish_remote_files(root: Path = ROOT, *, check: bool = False) -> int:
    """Verify hash-addressed downloads, including aliases shared across products."""
    count = 0
    public = root / "static/shared/courses"
    for product in sorted(PRODUCTS):
        assets = root / "plugins" / product / "assets/courses"
        index = json.loads((assets / "index.json").read_bytes())
        for workflow, entry in index["courses"].items():
            if withdrawn_public_lesson(root, product, workflow):
                continue
            course = json.loads((assets / _relative(entry["path"])).read_bytes())
            for asset in course["files"]:
                target = resolve_public_file(
                    public, f"{product}/{immutable_path(asset)}"
                )
                if (
                    not target.is_file()
                    or hashlib.sha256(target.read_bytes()).hexdigest()
                    != asset["sha256"]
                ):
                    raise ValueError(
                        f"Missing or altered immutable course file: {target}; run build_public_catalog.py"
                    )
                count += 1
    return count


def externalize_course_files(
    entries: dict[str, bytes], product: str, prefix: str = "", *, root: Path = ROOT
) -> None:
    """Remove only package copies; preserve course manifests and repository data."""
    if product not in PRODUCTS:
        return
    assets = prefix + "assets/courses/"
    index = json.loads(entries[assets + "index.json"])
    if index["product"] != product:
        raise ValueError("Foreign remote course catalogue")
    previous = json.loads(entries.get(assets + "remote.json", b'{"files":{}}'))["files"]
    remote = {}
    removals = set()
    index_changed = False
    for workflow, entry in list(index["courses"].items()):
        manifest = assets + _relative(entry["path"]).as_posix()
        course = json.loads(entries[manifest])
        if course["schema"] != "mparanza.teaching_kit.v2":
            raise ValueError(f"Unsupported remote course schema: {manifest}")
        if withdrawn_public_lesson(root, product, workflow):
            # Only the prepared lesson is withdrawn, not its professional skill.
            del index["courses"][workflow]
            index_changed = True
            folder = str(PurePosixPath(manifest).parent) + "/"
            for name in list(entries):
                if name.startswith(folder):
                    del entries[name]
            continue
        for asset in course["files"]:
            key = f"{workflow}/{_relative(asset['path'])}"
            packaged = (PurePosixPath(manifest).parent / asset["path"]).as_posix()
            content = entries.get(packaged)
            if content is not None:
                if hashlib.sha256(content).hexdigest() != asset["sha256"]:
                    raise ValueError(f"Unreviewed packaged attachment: {packaged}")
            elif previous.get(key, {}).get("sha256") != asset["sha256"]:
                raise ValueError(f"Missing packaged attachment: {packaged}")
            url_path = immutable_path(asset)
            public = resolve_public_file(
                root / "static/shared/courses", f"{product}/{url_path}"
            )
            if (
                not public.is_file()
                or hashlib.sha256(public.read_bytes()).hexdigest() != asset["sha256"]
            ):
                raise ValueError(f"Build immutable public course files first: {public}")
            remote[key] = {"url_path": url_path, "sha256": asset["sha256"]}
            removals.add(packaged)
    unexpected = [
        name
        for name in entries
        if name.startswith(assets)
        and name not in removals
        and name != assets + "remote.json"
        and name != assets + "index.json"
        and not name.endswith("/course.json")
    ]
    if unexpected:
        raise ValueError(f"Unlisted course attachments remain: {unexpected}")
    for name in removals:
        entries.pop(name, None)
    if index_changed:
        entries[assets + "index.json"] = (
            json.dumps(index, ensure_ascii=False, indent=2) + "\n"
        ).encode()
    entries[assets + "remote.json"] = (
        json.dumps(
            {
                "schema": "mparanza.course_files_remote.v1",
                "base": f"https://mparanza.com/static/shared/courses/{product}/",
                "files": remote,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode()


def main() -> int:
    """Verify immutable website downloads before building distributable packages."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    print(
        f"Remote course attachments: {publish_remote_files(check=parser.parse_args().check)} verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
