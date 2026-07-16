"""Launch the hosted Clara voice service from the local plugin workflow."""

from __future__ import annotations

import argparse
import base64
import logging
import os
import subprocess
import sys
import webbrowser
import zlib
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from advisor_case_core import (
    CASE_BRIEF_FILENAME,
    CaseWorkspaceError,
    refresh_case_brief,
    validate_case_workspace,
)

__all__ = [
    "DEFAULT_VOICE_LAUNCH_URL",
    "build_case_context",
    "build_limited_launch_url",
    "build_launch_url",
    "build_chrome_launch_args",
    "encode_case_context",
    "main",
    "open_launch_url",
]

LOGGER = logging.getLogger(__name__)

DEFAULT_VOICE_LAUNCH_URL = "https://mparanza.com/case-notes/voice/launch"
MAX_CASE_CONTEXT_CHARS = 2_500
MIN_CASE_CONTEXT_CHARS = 1_200
MAX_LAUNCH_URL_CHARS = 6_000
DEFAULT_CHROME_PROFILE_DIR = Path("/private/tmp/mparanza-case-notes-chrome-voice")


def build_case_context(
    case_dir: Path,
    max_chars: int = MAX_CASE_CONTEXT_CHARS,
    *,
    purpose: str = "transcription",
) -> str:
    """Return compact case context for hosted transcription prompts."""

    if purpose != "transcription":
        raise CaseWorkspaceError(f"Unsupported voice purpose: {purpose}")

    brief_path = case_dir / CASE_BRIEF_FILENAME
    if not brief_path.exists():
        refresh_case_brief(case_dir)
    brief = "\n".join(
        line.rstrip() for line in brief_path.read_text(encoding="utf-8").splitlines()
    ).strip()
    if len(brief) > max_chars:
        return brief[:max_chars].rstrip() + "\n\n[Case brief truncated.]"
    return brief


def encode_case_context(case_context: str) -> str:
    """Compress and URL-safe encode case context for the hosted launch URL."""

    compressed = zlib.compress(case_context.encode("utf-8"), level=9)
    return base64.urlsafe_b64encode(compressed).decode("ascii")


def build_launch_url(
    base_url: str = DEFAULT_VOICE_LAUNCH_URL,
    *,
    case_context: str = "",
) -> str:
    """Return the hosted voice launch URL."""

    clean_base = base_url.strip()
    if not case_context.strip():
        return clean_base
    parts = urlsplit(clean_base)
    query_items = parse_qsl(parts.query, keep_blank_values=True)
    if case_context.strip():
        query_items.append(("case_context_z", encode_case_context(case_context)))
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query_items),
            parts.fragment,
        )
    )


def build_limited_launch_url(
    case_dir: Path,
    *,
    base_url: str = DEFAULT_VOICE_LAUNCH_URL,
    purpose: str = "transcription",
    max_context_chars: int = MAX_CASE_CONTEXT_CHARS,
    max_url_chars: int = MAX_LAUNCH_URL_CHARS,
) -> tuple[str, int]:
    """Return a hosted launch URL that stays within the configured URL budget.

    Query-string length is a gateway constraint, so deterministic truncation is
    safer than opening a URL that may fail before authentication.
    """

    if max_context_chars < MIN_CASE_CONTEXT_CHARS:
        raise CaseWorkspaceError(
            f"max_context_chars must be at least {MIN_CASE_CONTEXT_CHARS}"
        )
    if max_url_chars <= len(base_url):
        raise CaseWorkspaceError("max_url_chars is shorter than the launch base URL")
    if purpose != "transcription":
        raise CaseWorkspaceError(f"Unsupported voice purpose: {purpose}")

    context_limit = max_context_chars
    while True:
        case_context = build_case_context(
            case_dir,
            max_chars=context_limit,
            purpose=purpose,
        )
        launch_url = build_launch_url(
            base_url,
            case_context=case_context,
        )
        if len(launch_url) <= max_url_chars:
            return launch_url, context_limit
        if context_limit == MIN_CASE_CONTEXT_CHARS:
            raise CaseWorkspaceError(
                "Hosted voice launch URL is too long even after context truncation "
                f"({len(launch_url)} > {max_url_chars} characters)."
            )
        context_limit = max(MIN_CASE_CONTEXT_CHARS, context_limit // 2)


def build_chrome_launch_args(
    launch_url: str,
    *,
    profile_dir: Path = DEFAULT_CHROME_PROFILE_DIR,
    remote_debugging_port: int = 0,
    auto_accept_microphone: bool = True,
) -> list[str]:
    """Return Chrome arguments for a clean Clara voice session."""

    args = [
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-search-engine-choice-screen",
        "--autoplay-policy=no-user-gesture-required",
    ]
    if remote_debugging_port > 0:
        args.append(f"--remote-debugging-port={remote_debugging_port}")
    if auto_accept_microphone:
        args.append("--use-fake-ui-for-media-stream")
    parts = urlsplit(launch_url)
    if parts.scheme and parts.netloc:
        args.append(
            f"--unsafely-treat-insecure-origin-as-secure={parts.scheme}://{parts.netloc}"
        )
    args.append(launch_url)
    return args


def open_launch_url(
    launch_url: str,
    *,
    browser: str = "default",
    chrome_profile_dir: Path = DEFAULT_CHROME_PROFILE_DIR,
    chrome_remote_debugging_port: int = 0,
    chrome_auto_accept_microphone: bool = True,
) -> None:
    """Open *launch_url* in the requested browser."""

    if browser == "default":
        webbrowser.open(launch_url)
        return
    if browser != "chrome":
        raise CaseWorkspaceError(f"Unsupported browser: {browser}")

    chrome_profile_dir.mkdir(parents=True, exist_ok=True)
    chrome_args = build_chrome_launch_args(
        launch_url,
        profile_dir=chrome_profile_dir,
        remote_debugging_port=chrome_remote_debugging_port,
        auto_accept_microphone=chrome_auto_accept_microphone,
    )
    if sys.platform == "darwin":
        command = ["/usr/bin/open", "-na", "Google Chrome", "--args", *chrome_args]
    else:
        chrome_executable = os.environ.get("GOOGLE_CHROME_BIN") or "google-chrome"
        command = [chrome_executable, *chrome_args]
    subprocess.Popen(  # noqa: S603,S607 - arguments are constructed without a shell.
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    """Open the hosted voice launch URL."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("--server-url", default=DEFAULT_VOICE_LAUNCH_URL)
    parser.add_argument(
        "--purpose",
        choices=("transcription",),
        default="transcription",
        help="Open Clara Voice Capture for recording or uploaded-audio transcription.",
    )
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--browser", choices=("default", "chrome"), default="default")
    parser.add_argument(
        "--chrome-profile-dir",
        type=Path,
        default=DEFAULT_CHROME_PROFILE_DIR,
        help="Dedicated Chrome profile directory used with --browser chrome.",
    )
    parser.add_argument(
        "--chrome-remote-debugging-port",
        type=int,
        default=0,
        help="Optional Chrome remote debugging port used with --browser chrome.",
    )
    parser.add_argument(
        "--no-chrome-auto-accept-microphone",
        action="store_true",
        help="Do not auto-accept the local Chrome microphone prompt.",
    )
    parser.add_argument(
        "--max-context-chars",
        type=int,
        default=MAX_CASE_CONTEXT_CHARS,
        help="Maximum case context characters before compression.",
    )
    parser.add_argument(
        "--max-url-chars",
        type=int,
        default=MAX_LAUNCH_URL_CHARS,
        help="Maximum generated launch URL length.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    errors = validate_case_workspace(args.case_dir)
    if errors:
        raise CaseWorkspaceError("; ".join(errors))

    refresh_case_brief(args.case_dir)
    launch_url, context_limit = build_limited_launch_url(
        args.case_dir,
        base_url=args.server_url,
        purpose=args.purpose,
        max_context_chars=args.max_context_chars,
        max_url_chars=args.max_url_chars,
    )
    if context_limit < args.max_context_chars:
        LOGGER.warning(
            "Hosted voice context truncated to %s characters to keep launch URL "
            "within %s characters.",
            context_limit,
            args.max_url_chars,
        )
    LOGGER.info("Hosted voice launch URL: %s", launch_url)
    if not args.no_open:
        open_launch_url(
            launch_url,
            browser=args.browser,
            chrome_profile_dir=args.chrome_profile_dir,
            chrome_remote_debugging_port=args.chrome_remote_debugging_port,
            chrome_auto_accept_microphone=(not args.no_chrome_auto_accept_microphone),
        )
    LOGGER.info(
        "After the browser downloads the voice bundle, import the newest valid "
        "bundle from Downloads with scripts/import_latest_hosted_voice_bundle.py."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
