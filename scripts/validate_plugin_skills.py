"""Reject skill metadata that requires host repair before publishing package bytes."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from zipfile import ZipFile

__all__ = [
    "validate_skill_frontmatter",
    "validate_skill_entries",
    "validate_skill_archive",
    "main",
]


def validate_skill_frontmatter(content: bytes, *, path: str) -> None:
    """Parse the host metadata contract without rewriting any indexed bytes.

    YAML syntax, unique keys and required string fields are mechanically
    verifiable. Semantic skill instructions remain outside this build gate.
    """
    try:
        import yaml
    except ImportError as error:
        raise RuntimeError(
            "Plugin build dependency missing: install "
            "scripts/requirements-plugin-build.txt before building"
        ) from error

    class UniqueKeyLoader(yaml.SafeLoader):
        def construct_mapping(self, node: Any, deep: bool = False) -> dict:
            keys: set[str] = set()
            for key, _ in node.value:
                if key.tag != "tag:yaml.org,2002:str":
                    raise ValueError("metadata mapping keys must be strings")
                if key.value in keys:
                    raise ValueError(f"duplicate metadata field: {key.value}")
                keys.add(key.value)
            return super().construct_mapping(node, deep=deep)

    try:
        lines = content.decode("utf-8").splitlines()
        if not lines or lines[0] != "---":
            raise ValueError("must start with YAML frontmatter")
        try:
            end = lines.index("---", 1)
        except ValueError as error:
            raise ValueError("unterminated YAML frontmatter") from error
        loader = UniqueKeyLoader("\n".join(lines[1:end]))
        try:
            metadata = loader.get_single_data()
        finally:
            loader.dispose()
        if not isinstance(metadata, dict):
            raise ValueError("frontmatter must be a mapping")
        for key in ("name", "description"):
            value = metadata.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} must be a non-empty string")
    except (UnicodeError, yaml.YAMLError, ValueError) as error:
        raise ValueError(f"Invalid skill metadata in {path}: {error}") from error


def validate_skill_entries(entries: Mapping[str, bytes]) -> None:
    """Validate every skill, including nested modules and future entrypoints."""
    for name, content in entries.items():
        if name.rsplit("/", 1)[-1] == "SKILL.md":
            validate_skill_frontmatter(content, path=name)


def validate_skill_archive(path: Path) -> None:
    """Read final ZIP bytes rather than trusting the pre-serialization tree."""
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate ZIP member in {path}")
        validate_skill_entries(
            {
                name: archive.read(name)
                for name in names
                if name.rsplit("/", 1)[-1] == "SKILL.md"
            }
        )


def main(argv: list[str] | None = None) -> int:
    """Check selected source files, or every source skill for CI and pre-commit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    paths = args.paths or sorted(
        (Path(__file__).resolve().parents[1] / "plugins").glob("*/skills/*/SKILL.md")
    )
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        for path in paths:
            validate_skill_frontmatter(path.read_bytes(), path=str(path))
    except (OSError, ValueError, RuntimeError) as error:
        logging.error("%s", error)
        return 1
    logging.info("Validated %s source skills", len(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
