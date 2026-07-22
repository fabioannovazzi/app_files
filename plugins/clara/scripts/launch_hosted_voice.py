"""Launch the hosted Clara voice service from the local plugin workflow."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

from advisor_case_core import (
    CASE_BRIEF_FILENAME,
    SUPPORTED_LANGUAGES,
    CaseWorkspaceError,
    load_case_file,
    refresh_case_brief,
    validate_case_workspace,
)

__all__ = [
    "DEFAULT_VOICE_LAUNCH_URL",
    "build_case_context",
    "build_launch_url",
    "build_voice_session_url",
    "build_chrome_launch_args",
    "main",
    "open_launch_url",
    "prepare_launch_url",
    "read_private_text_file",
    "validate_hosted_url",
]

LOGGER = logging.getLogger(__name__)

DEFAULT_VOICE_LAUNCH_URL = "https://mparanza.com/case-notes/voice/launch"
MAX_CASE_CONTEXT_CHARS = 2_500
DEFAULT_CHROME_PROFILE_DIR = Path("/private/tmp/mparanza-case-notes-chrome-voice")
_HOSTED_HOST = "mparanza.com"
_TEST_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


def read_private_text_file(path: Path, *, label: str) -> str:
    """Read one local secret after forcing owner-only file permissions."""

    source = path.expanduser()
    if source.is_symlink() or not source.is_file():
        raise CaseWorkspaceError(f"{label} file must be a regular local file.")
    try:
        source.chmod(0o600)
        value = source.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise CaseWorkspaceError(f"Could not read {label} file: {source}") from exc
    if not value:
        raise CaseWorkspaceError(f"{label} file is empty.")
    return value


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


def validate_hosted_url(
    value: str,
    *,
    required_path: str | None = None,
    allow_query: bool = False,
    allow_localhost_for_tests: bool = False,
) -> str:
    """Return a pinned Hosted Voice URL or reject the destination."""

    clean = value.strip()
    try:
        parts = urlsplit(clean)
        port = parts.port
    except ValueError as exc:
        raise CaseWorkspaceError(
            "Hosted Voice destination is not a valid URL."
        ) from exc
    is_mparanza = (
        parts.scheme == "https"
        and (parts.hostname or "").lower() == _HOSTED_HOST
        and port in {None, 443}
    )
    is_test_local = (
        allow_localhost_for_tests
        and parts.scheme in {"http", "https"}
        and (parts.hostname or "").lower() in _TEST_LOCAL_HOSTS
    )
    if not (is_mparanza or is_test_local):
        raise CaseWorkspaceError(
            "Hosted Voice destination must be https://mparanza.com."
        )
    if parts.username or parts.password or parts.fragment:
        raise CaseWorkspaceError(
            "Hosted Voice URL contains unsupported credentials or fragment."
        )
    if required_path is not None and parts.path != required_path:
        raise CaseWorkspaceError(f"Hosted Voice URL must use the {required_path} path.")
    if parts.query and not allow_query:
        raise CaseWorkspaceError("Hosted Voice URL must not contain a query string.")
    return clean


def build_launch_url(
    base_url: str = DEFAULT_VOICE_LAUNCH_URL,
) -> str:
    """Return the context-free browser-authenticated launch URL."""

    return validate_hosted_url(
        base_url,
        required_path="/case-notes/voice/launch",
    )


def build_voice_session_url(
    base_url: str,
    *,
    launch_token: str,
) -> str:
    """Return a Hosted Voice page URL containing only an opaque launch token."""

    clean_token = launch_token.strip()
    if not clean_token or any(
        char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        for char in clean_token
    ):
        raise CaseWorkspaceError("Hosted Voice returned an invalid launch token.")
    parts = urlsplit(validate_hosted_url(base_url))
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            "/case-notes/voice",
            urlencode({"session": clean_token}),
            "",
        )
    )


def prepare_launch_url(
    case_dir: Path,
    *,
    server_url: str = DEFAULT_VOICE_LAUNCH_URL,
    purpose: str = "transcription",
    max_context_chars: int = MAX_CASE_CONTEXT_CHARS,
    cookie_header: str = "",
    magic_link: str = "",
    language: str | None = None,
) -> tuple[str, bool]:
    """Prepare an authenticated context launch or an explicit context-free fallback."""

    launch_base_url = build_launch_url(server_url)
    if not (cookie_header.strip() or magic_link.strip()):
        return launch_base_url, False

    from upload_hosted_audio import (
        _new_opener,
        authenticate_with_magic_link,
        bind_session_cookie,
        request_context_launch_token,
    )

    refresh_case_brief(case_dir)
    context = build_case_context(
        case_dir,
        max_chars=max_context_chars,
        purpose=purpose,
    )
    manifest = load_case_file(case_dir, "manifest")
    resolved_language = (
        str(language or manifest.get("output_language") or "it").strip().lower()
    )
    if resolved_language not in SUPPORTED_LANGUAGES:
        raise CaseWorkspaceError(f"Unsupported voice language: {resolved_language}")
    base_parts = urlsplit(launch_base_url)
    hosted_base_url = urlunsplit((base_parts.scheme, base_parts.netloc, "", "", ""))
    opener = _new_opener()
    if magic_link.strip():
        authenticate_with_magic_link(opener, magic_link)
    if cookie_header.strip():
        bind_session_cookie(
            opener,
            base_url=hosted_base_url,
            cookie_header=cookie_header,
        )
    token = request_context_launch_token(
        opener,
        base_url=hosted_base_url,
        case_context=context,
        language=resolved_language,
    )
    return (
        build_voice_session_url(hosted_base_url, launch_token=token),
        True,
    )


def build_chrome_launch_args(
    launch_url: str,
    *,
    profile_dir: Path = DEFAULT_CHROME_PROFILE_DIR,
    remote_debugging_port: int = 0,
    auto_accept_microphone: bool = True,
    allow_localhost_for_tests: bool = False,
) -> list[str]:
    """Return Chrome arguments for a clean Clara voice session."""

    validate_hosted_url(
        launch_url,
        allow_query=True,
        allow_localhost_for_tests=allow_localhost_for_tests,
    )
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

    validate_hosted_url(launch_url, allow_query=True)
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
    parser.add_argument(
        "--language",
        choices=sorted(SUPPORTED_LANGUAGES),
        help="Transcription language; defaults to the Clara case output language.",
    )
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--magic-link-file", type=Path)
    parser.add_argument("--cookie-header-file", type=Path)
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
        help="Maximum case context characters sent in the authenticated body.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    errors = validate_case_workspace(args.case_dir)
    if errors:
        raise CaseWorkspaceError("; ".join(errors))

    cookie_header = ""
    if args.cookie_header_file:
        cookie_header = read_private_text_file(
            args.cookie_header_file,
            label="session cookie",
        )
    magic_link = ""
    if args.magic_link_file:
        magic_link = read_private_text_file(
            args.magic_link_file,
            label="magic link",
        )
    launch_url, context_attached = prepare_launch_url(
        args.case_dir,
        server_url=args.server_url,
        purpose=args.purpose,
        max_context_chars=args.max_context_chars,
        cookie_header=cookie_header,
        magic_link=magic_link,
        language=args.language,
    )
    if context_attached:
        LOGGER.info(
            "Hosted voice launch prepared with authenticated case context; "
            "the opaque token is not printed."
        )
    else:
        LOGGER.warning(
            "No hosted authentication material was supplied. Opening the "
            "browser-authenticated fallback without attaching case context."
        )
    LOGGER.info("Hosted voice destination: https://mparanza.com/case-notes/voice")
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
