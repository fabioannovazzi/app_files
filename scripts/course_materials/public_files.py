"""Store course downloads once and preserve their previously published URLs."""

from __future__ import annotations

import hashlib
import html
import json
import posixpath
import re
import shutil
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

__all__ = ["deduplicate", "resolve_public_file"]

PREFIX = "/static/shared/courses/"
MAPPING = "file-aliases.json"
LINK = re.compile(r"(\b(?:href|src)\s*=\s*)([\"'])(.*?)(\2)", re.IGNORECASE)


def _aliases(directory: Path) -> dict[str, str]:
    path = directory / MAPPING
    return json.loads(path.read_bytes())["aliases"] if path.is_file() else {}


def resolve_public_file(directory: Path, relative: str) -> Path:
    """Resolve the same single-hop file mapping used by the public server."""
    return directory / _aliases(directory).get(relative, relative)


def _rewrite_links(document: str, relative: str, aliases: dict[str, str]) -> str:
    """Make generated views independent of the location of their input files."""

    def replace(match: re.Match[str]) -> str:
        link = urlsplit(html.unescape(match[3]))
        if link.scheme or link.netloc or not link.path:
            return match[0]
        if link.path.startswith("/"):
            if not link.path.startswith(PREFIX):
                return match[0]
            target = unquote(link.path.removeprefix(PREFIX))
        else:
            target = posixpath.normpath(
                posixpath.join(posixpath.dirname(relative), unquote(link.path))
            )
        url = urlunsplit(
            (
                "",
                "",
                PREFIX + quote(aliases.get(target, target), safe="/"),
                link.query,
                link.fragment,
            )
        )
        return match[1] + match[2] + html.escape(url, quote=True) + match[2]

    return LINK.sub(replace, document)


def deduplicate(generated: Path, previous: Path, root: Path) -> None:
    """Deduplicate exact bytes, retain historical downloads and rewrite public links."""
    old_aliases = _aliases(previous)
    # Historical hash URLs remain available even after the lesson changes.
    for path in sorted(previous.glob("*/_files/**/*")):
        if path.is_file():
            if hashlib.sha256(path.read_bytes()).hexdigest() != path.parent.name:
                raise ValueError(f"Immutable course file changed: {path}")
            target = generated / path.relative_to(previous)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)

    attachment_paths: set[str] = set()
    immutable_urls: dict[str, str] = {}
    for product in ("vera", "clara", "lucia"):
        for manifest in sorted(
            (root / f"plugins/{product}/assets/courses").glob("*/course.json")
        ):
            course = json.loads(manifest.read_bytes())
            for asset in course["files"]:
                for language in asset["languages"]:
                    relative = (
                        f"{product}/{manifest.parent.name}/{language}/{asset['path']}"
                    )
                    if (generated / relative).is_file():
                        attachment_paths.add(relative)
                        immutable_urls[relative] = (
                            f"{product}/_files/{asset['sha256']}/{Path(asset['path']).name}"
                        )

    groups: dict[str, list[str]] = defaultdict(list)
    for path in sorted(generated.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(generated).as_posix()
        if "/" not in relative or path.name == "course-provenance.json":
            continue
        if (
            path.suffix == ".html"
            and relative not in attachment_paths
            and "/_files/" not in relative
        ):
            continue
        groups[hashlib.sha256(path.read_bytes()).hexdigest()].append(relative)

    aliases: dict[str, str] = {}
    for digest, names in groups.items():
        existing = sorted(name for name in names if "/_files/" in name)
        first = names[0]
        target = (
            existing[0]
            if existing
            else f"{first.split('/')[0]}/_files/{digest}/{Path(first).name}"
        )
        destination = generated / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        if target not in names:
            shutil.copyfile(generated / first, destination)
        for name in names:
            if name != target:
                aliases[name] = target
                (generated / name).unlink()
            immutable = immutable_urls.get(name)
            if immutable and immutable != target:
                aliases[immutable] = target

    # Pinned HTML attachments are byte-for-byte originals. Their generated reading
    # views and lesson pages may link directly to the shared stored inputs.
    for path in sorted(generated.rglob("*.html")):
        relative = path.relative_to(generated).as_posix()
        if "/_files/" not in relative:
            path.write_text(
                _rewrite_links(path.read_text(encoding="utf-8"), relative, aliases),
                encoding="utf-8",
            )

    # Preserve prior URL bindings, including older versions of a named input.
    merged = {**aliases, **old_aliases}
    for name, target in list(merged.items()):
        seen = {name}
        while target in aliases:
            if target in seen:
                raise ValueError(f"Cyclic course file alias: {name}")
            seen.add(target)
            target = aliases[target]
        if not (generated / target).is_file():
            raise ValueError(f"Missing historical course download: {name} -> {target}")
        merged[name] = target
    (generated / MAPPING).write_text(
        json.dumps(
            {"schema": "mparanza.course_file_aliases.v1", "aliases": merged},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
