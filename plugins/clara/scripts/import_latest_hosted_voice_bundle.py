"""Import the newest downloaded hosted Clara voice bundle into a case workspace."""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from advisor_case_core import CaseWorkspaceError, validate_case_workspace
from import_hosted_voice_bundle import (
    HostedVoiceImportResult,
    import_hosted_voice_bundle,
    read_hosted_voice_bundle_payload,
)

__all__ = [
    "LatestHostedVoiceBundle",
    "find_latest_hosted_voice_bundle",
    "import_latest_hosted_voice_bundle",
    "main",
]

LOGGER = logging.getLogger(__name__)
BUNDLE_PATTERNS = (
    "case-notes-voice-*.zip",
    "case-notes-audio-*.zip",
    "case-notes-voice-*.json",
    "case-notes-audio-*.json",
)


@dataclass(frozen=True)
class LatestHostedVoiceBundle:
    """Downloaded bundle selected for import."""

    path: Path
    captured_at: str
    already_imported: bool


def _compact_timestamp(timestamp: str) -> str:
    compact = re.sub(r"[^0-9]", "", timestamp)
    if len(compact) >= 14:
        return compact[:14] + "Z"
    return ""


def _candidate_paths(downloads_dir: Path) -> Iterable[Path]:
    seen: set[Path] = set()
    for pattern in BUNDLE_PATTERNS:
        for path in downloads_dir.glob(pattern):
            if path in seen:
                continue
            seen.add(path)
            if path.is_file():
                yield path


def _read_hosted_bundle(path: Path) -> Mapping[str, Any] | None:
    try:
        payload = read_hosted_voice_bundle_payload(path)
    except CaseWorkspaceError:
        return None
    if not isinstance(payload, Mapping):
        return None
    if payload.get("source") != "case_notes_hosted_voice":
        return None
    return payload


def _already_imported(case_dir: Path, bundle: Mapping[str, Any]) -> bool:
    timestamp = str(bundle.get("captured_at", "")).strip()
    compact = _compact_timestamp(timestamp)
    if not compact:
        return False
    session_dir = case_dir / "voice_sessions" / compact
    return session_dir.exists()


def find_latest_hosted_voice_bundle(
    case_dir: Path,
    *,
    downloads_dir: Path | None = None,
    include_imported: bool = False,
) -> LatestHostedVoiceBundle:
    """Return the newest valid downloaded voice bundle for *case_dir*."""

    errors = validate_case_workspace(case_dir)
    if errors:
        raise CaseWorkspaceError("; ".join(errors))
    search_dir = (downloads_dir or Path("~/Downloads")).expanduser()
    if not search_dir.exists():
        raise CaseWorkspaceError(f"downloads folder does not exist: {search_dir}")

    candidates: list[tuple[float, Path, Mapping[str, Any], bool]] = []
    for path in _candidate_paths(search_dir):
        bundle = _read_hosted_bundle(path)
        if bundle is None:
            continue
        imported = _already_imported(case_dir, bundle)
        if imported and not include_imported:
            continue
        candidates.append((path.stat().st_mtime, path, bundle, imported))

    if not candidates:
        raise CaseWorkspaceError(
            f"no unimported hosted voice bundles found in {search_dir}"
        )
    _mtime, path, bundle, imported = max(candidates, key=lambda item: item[0])
    return LatestHostedVoiceBundle(
        path=path,
        captured_at=str(bundle.get("captured_at", "")).strip(),
        already_imported=imported,
    )


def import_latest_hosted_voice_bundle(
    case_dir: Path,
    *,
    downloads_dir: Path | None = None,
    include_imported: bool = False,
    title: str = "Hosted voice session",
) -> HostedVoiceImportResult:
    """Find and import the newest downloaded hosted voice bundle."""

    selected = find_latest_hosted_voice_bundle(
        case_dir,
        downloads_dir=downloads_dir,
        include_imported=include_imported,
    )
    LOGGER.info("Selected hosted voice bundle: %s", selected.path)
    return import_hosted_voice_bundle(case_dir, selected.path, title=title)


def main() -> int:
    """Run latest hosted voice bundle import."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--downloads-dir", type=Path, default=Path("~/Downloads"))
    parser.add_argument("--include-imported", action="store_true")
    parser.add_argument("--title", default="Hosted voice session")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = import_latest_hosted_voice_bundle(
        args.case_dir,
        downloads_dir=args.downloads_dir,
        include_imported=args.include_imported,
        title=args.title,
    )
    LOGGER.info("Transcript material: %s", result.material_id)
    LOGGER.info("Clara review: %s", result.clara_review_path)
    LOGGER.info("Session folder: %s", result.session_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
