from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

__all__ = [
    "DuplicateCandidate",
    "find_duplicate_candidates",
    "sha256_file",
    "write_duplicate_candidates_csv",
]

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DuplicateCandidate:
    """A file that belongs to a duplicate candidate group."""

    relative_path: str
    duplicate_type: str
    group_key: str
    size_bytes: int
    sha256: str

    def as_row(self) -> dict[str, str | int]:
        return {
            "relative_path": self.relative_path,
            "duplicate_type": self.duplicate_type,
            "group_key": self.group_key,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute a SHA-256 digest for a file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_stem(path: Path) -> str:
    without_accents = unicodedata.normalize("NFKD", path.stem).encode("ascii", "ignore")
    text = without_accents.decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _group_exact(paths: Sequence[Path]) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    for path in paths:
        digest = sha256_file(path)
        groups.setdefault(digest, []).append(path)
    return {key: value for key, value in groups.items() if len(value) > 1}


def _group_soft(paths: Sequence[Path]) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    for path in paths:
        key = f"{_normalized_stem(path)}|{path.suffix.lower()}|{path.stat().st_size}"
        groups.setdefault(key, []).append(path)
    return {key: value for key, value in groups.items() if len(value) > 1}


def find_duplicate_candidates(
    paths: Iterable[Path],
    base_dir: Path | str,
) -> list[DuplicateCandidate]:
    """Find exact and conservative soft duplicate candidates."""

    base_path = Path(base_dir).resolve()
    files = [path.resolve() for path in paths if path.is_file()]
    exact_groups = _group_exact(files)
    exact_members = {path for group in exact_groups.values() for path in group}
    candidates: list[DuplicateCandidate] = []

    for digest, group in sorted(exact_groups.items(), key=lambda item: item[0]):
        for path in sorted(group):
            candidates.append(
                DuplicateCandidate(
                    relative_path=path.relative_to(base_path).as_posix(),
                    duplicate_type="hash-identico",
                    group_key=digest[:16],
                    size_bytes=path.stat().st_size,
                    sha256=digest,
                )
            )

    for key, group in sorted(_group_soft(files).items(), key=lambda item: item[0]):
        filtered = [path for path in group if path not in exact_members]
        if len(filtered) < 2:
            continue
        for path in sorted(filtered):
            candidates.append(
                DuplicateCandidate(
                    relative_path=path.relative_to(base_path).as_posix(),
                    duplicate_type="nome-dimensione-simile",
                    group_key=key,
                    size_bytes=path.stat().st_size,
                    sha256=sha256_file(path),
                )
            )

    return candidates


def write_duplicate_candidates_csv(
    candidates: Iterable[DuplicateCandidate],
    output_path: Path | str,
) -> Path:
    """Write duplicate candidates to CSV."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "relative_path",
        "duplicate_type",
        "group_key",
        "size_bytes",
        "sha256",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(candidate.as_row())
    return path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Individua duplicati esatti o fortemente sospetti in una cartella."
    )
    parser.add_argument("folder", type=Path, help="Cartella da analizzare.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="File CSV output. Default: <folder>/out/duplicate_candidates.csv",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args()
    out_path = args.out or args.folder / "out" / "duplicate_candidates.csv"
    candidates = find_duplicate_candidates(args.folder.rglob("*"), args.folder)
    write_duplicate_candidates_csv(candidates, out_path)
    LOGGER.info(
        "Trovati %s candidati duplicati. Output in %s", len(candidates), out_path
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
