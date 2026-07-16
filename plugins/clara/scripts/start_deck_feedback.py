"""Launch Clara deck feedback capture and import the completed session."""

from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from advisor_case_core import CaseWorkspaceError, validate_case_workspace
from import_hosted_voice_bundle import (
    HostedVoiceImportResult,
    import_hosted_voice_bundle,
)
from import_latest_hosted_voice_bundle import (
    BUNDLE_PATTERNS,
    LatestHostedVoiceBundle,
    find_latest_hosted_voice_bundle,
)
from launch_hosted_voice import (
    DEFAULT_CHROME_PROFILE_DIR,
    DEFAULT_VOICE_LAUNCH_URL,
    MAX_CASE_CONTEXT_CHARS,
    MAX_LAUNCH_URL_CHARS,
    build_limited_launch_url,
    open_launch_url,
)
from prepare_voice_deck_revision import prepare_voice_deck_revision_intake

__all__ = [
    "DeckFeedbackCaptureResult",
    "start_deck_feedback",
    "wait_for_new_hosted_voice_bundle",
]

LOGGER = logging.getLogger(__name__)
DEFAULT_TIMEOUT_SECONDS = 7_200.0
DEFAULT_POLL_SECONDS = 2.0
HANDOFF_FILENAME = "deck_feedback_capture.json"


@dataclass(frozen=True)
class DeckFeedbackCaptureResult:
    """Imported capture and durable target-deck handoff."""

    launch_url: str
    target_deck_path: Path
    target_kind: str
    selected_bundle_path: Path
    import_result: HostedVoiceImportResult
    handoff_path: Path
    deck_revision_intake_path: Path | None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _bundle_snapshot(downloads_dir: Path) -> dict[Path, tuple[int, int]]:
    snapshot: dict[Path, tuple[int, int]] = {}
    for pattern in BUNDLE_PATTERNS:
        for path in downloads_dir.glob(pattern):
            if not path.is_file():
                continue
            stat = path.stat()
            snapshot[path.resolve()] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def _target_kind(target_deck_path: Path) -> str:
    if target_deck_path.is_file() and target_deck_path.suffix.lower() == ".pptx":
        return "pptx"
    if target_deck_path.is_file() and target_deck_path.suffix.lower() in {
        ".html",
        ".htm",
    }:
        return "html"
    if target_deck_path.is_dir() and any(
        (target_deck_path / filename).is_file()
        for filename in ("index.html", "deck-plan.json")
    ):
        return "html"
    raise CaseWorkspaceError(
        "deck feedback target must be a PPTX, an HTML file, or a Clara HTML "
        "deck/work directory"
    )


def _portable_path(case_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(case_dir).as_posix()
    except ValueError:
        return str(path)


def wait_for_new_hosted_voice_bundle(
    case_dir: Path,
    *,
    downloads_dir: Path,
    baseline: dict[Path, tuple[int, int]],
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> LatestHostedVoiceBundle:
    """Wait for a valid bundle created or changed after capture launch."""

    if timeout_seconds <= 0:
        raise CaseWorkspaceError("timeout_seconds must be positive")
    if poll_seconds <= 0:
        raise CaseWorkspaceError("poll_seconds must be positive")

    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            selected = find_latest_hosted_voice_bundle(
                case_dir,
                downloads_dir=downloads_dir,
            )
        except CaseWorkspaceError:
            selected = None

        if selected is not None:
            resolved = selected.path.resolve()
            stat = resolved.stat()
            fingerprint = (stat.st_mtime_ns, stat.st_size)
            if baseline.get(resolved) != fingerprint:
                return selected

        if time.monotonic() >= deadline:
            raise CaseWorkspaceError(
                "timed out waiting for a new Clara Voice Capture bundle in "
                f"{downloads_dir}"
            )
        sleep(poll_seconds)


def _write_handoff(
    *,
    case_dir: Path,
    target_deck_path: Path,
    target_kind: str,
    selected_bundle_path: Path,
    import_result: HostedVoiceImportResult,
) -> Path:
    handoff_path = import_result.session_dir / HANDOFF_FILENAME
    payload = {
        "schema_version": 1,
        "source": "clara_deck_feedback_capture",
        "status": "imported",
        "captured_for": "deck_revision",
        "target_deck": {
            "path": _portable_path(case_dir, target_deck_path),
            "kind": target_kind,
        },
        "source_bundle_path": str(selected_bundle_path),
        "voice_session_path": _portable_path(case_dir, import_result.session_dir),
        "transcript_material_id": import_result.material_id,
        "screen_video_path": (
            _portable_path(case_dir, import_result.video_path)
            if import_result.video_path is not None
            else None
        ),
        "feedback_timeline_path": (
            _portable_path(case_dir, import_result.feedback_timeline_path)
            if import_result.feedback_timeline_path is not None
            else None
        ),
        "recorded_at": _now_iso(),
        "data_posture": {
            "local_files_read": [_portable_path(case_dir, case_dir / "case_brief.md")],
            "local_files_referenced": [_portable_path(case_dir, target_deck_path)],
            "hosted_capture_used": True,
            "external_connectors_used": [],
            "local_bundle_imported": True,
        },
    }
    handoff_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return handoff_path


def start_deck_feedback(
    case_dir: Path,
    *,
    target_deck_path: Path,
    downloads_dir: Path | None = None,
    browser: str = "chrome",
    server_url: str = DEFAULT_VOICE_LAUNCH_URL,
    chrome_profile_dir: Path = DEFAULT_CHROME_PROFILE_DIR,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    title: str = "Deck feedback capture",
    open_browser: bool = True,
    sleep: Callable[[float], None] = time.sleep,
) -> DeckFeedbackCaptureResult:
    """Open capture, import its new bundle, and bind it to the target deck."""

    case_dir = case_dir.expanduser().resolve()
    errors = validate_case_workspace(case_dir)
    if errors:
        raise CaseWorkspaceError("; ".join(errors))

    target_deck_path = target_deck_path.expanduser().resolve()
    target_kind = _target_kind(target_deck_path)
    downloads_dir = (downloads_dir or Path("~/Downloads")).expanduser().resolve()
    if not downloads_dir.is_dir():
        raise CaseWorkspaceError(f"downloads folder does not exist: {downloads_dir}")

    baseline = _bundle_snapshot(downloads_dir)
    launch_url, _context_limit = build_limited_launch_url(
        case_dir,
        base_url=server_url,
        max_context_chars=MAX_CASE_CONTEXT_CHARS,
        max_url_chars=MAX_LAUNCH_URL_CHARS,
    )
    if open_browser:
        open_launch_url(
            launch_url,
            browser=browser,
            chrome_profile_dir=chrome_profile_dir,
        )

    LOGGER.info(
        "Clara Voice Capture opened for %s. End the capture normally; the new "
        "bundle will be imported automatically.",
        target_deck_path.name,
    )
    selected = wait_for_new_hosted_voice_bundle(
        case_dir,
        downloads_dir=downloads_dir,
        baseline=baseline,
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
        sleep=sleep,
    )
    import_result = import_hosted_voice_bundle(
        case_dir,
        selected.path,
        title=title,
    )
    handoff_path = _write_handoff(
        case_dir=case_dir,
        target_deck_path=target_deck_path,
        target_kind=target_kind,
        selected_bundle_path=selected.path,
        import_result=import_result,
    )

    deck_revision_intake_path: Path | None = None
    if target_kind == "pptx":
        intake = prepare_voice_deck_revision_intake(
            case_dir,
            voice_session=import_result.session_dir,
            transcript_material_id=import_result.material_id,
            deck_path=target_deck_path,
        )
        deck_revision_intake_path = intake.intake_path

    return DeckFeedbackCaptureResult(
        launch_url=launch_url,
        target_deck_path=target_deck_path,
        target_kind=target_kind,
        selected_bundle_path=selected.path,
        import_result=import_result,
        handoff_path=handoff_path,
        deck_revision_intake_path=deck_revision_intake_path,
    )


def main() -> int:
    """Run the one-command Clara deck-feedback workflow."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--deck", type=Path, required=True)
    parser.add_argument("--downloads-dir", type=Path, default=Path("~/Downloads"))
    parser.add_argument("--browser", choices=("default", "chrome"), default="chrome")
    parser.add_argument("--server-url", default=DEFAULT_VOICE_LAUNCH_URL)
    parser.add_argument(
        "--chrome-profile-dir", type=Path, default=DEFAULT_CHROME_PROFILE_DIR
    )
    parser.add_argument(
        "--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS
    )
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--title", default="Deck feedback capture")
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = start_deck_feedback(
        args.case_dir,
        target_deck_path=args.deck,
        downloads_dir=args.downloads_dir,
        browser=args.browser,
        server_url=args.server_url,
        chrome_profile_dir=args.chrome_profile_dir,
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
        title=args.title,
        open_browser=not args.no_open,
    )
    LOGGER.info("Capture bundle: %s", result.selected_bundle_path)
    LOGGER.info("Voice session: %s", result.import_result.session_dir)
    LOGGER.info("Deck feedback handoff: %s", result.handoff_path)
    if result.deck_revision_intake_path is not None:
        LOGGER.info("Deck revision intake: %s", result.deck_revision_intake_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
