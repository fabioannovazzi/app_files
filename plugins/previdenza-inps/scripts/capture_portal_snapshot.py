#!/usr/bin/env python3
"""Capture one selected, already-open INPS browser page without operating it."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

__all__ = [
    "PortalCaptureError",
    "capture_portal_snapshot",
    "main",
    "normalize_approved_origin",
    "normalize_cdp_url",
    "verify_portal_snapshot",
]

LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION = "previdenza_inps.portal_capture.v3"
VISIBLE_TEXT_NAME = "portal_visible_text.txt"
SCREENSHOT_NAME = "portal_full_page.png"
MANIFEST_NAME = "portal_capture_manifest.json"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CAPTURE_ID_RE = re.compile(r"^inps-capture-[0-9a-f]{32}$")
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
ALLOWED_INPS_SUFFIXES = ("inps.it",)

GUARDRAILS = {
    "authentication_performed_by_connector": False,
    "navigation_performed": False,
    "page_actions_performed": False,
    "cookies_read": False,
    "storage_state_read": False,
    "page_html_read": False,
    "browser_closed": False,
    "case_content_uploaded": False,
}
TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "capture_id",
        "captured_at",
        "route_selected",
        "capture_method",
        "approved_origin",
        "source_url_sha256",
        "page_title_sha256",
        "body_character_count",
        "guardrails",
        "artifacts",
    }
)
ARTIFACT_FIELDS = frozenset({"path", "media_type", "size_bytes", "sha256"})
EXPECTED_ARTIFACTS = {
    VISIBLE_TEXT_NAME: "text/plain; charset=utf-8",
    SCREENSHOT_NAME: "image/png",
}


class PortalCaptureError(ValueError):
    """Raised when a portal capture is unsafe, incomplete, or has drifted."""


def _timezone_datetime(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PortalCaptureError(f"{field} must be a non-empty ISO date-time.")
    clean = value.strip()
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PortalCaptureError(f"{field} must be a valid ISO date-time.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PortalCaptureError(f"{field} must include a timezone.")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _required_text(
    value: Any,
    *,
    field: str,
    maximum_characters: int = 2_000,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PortalCaptureError(f"{field} must be a non-empty string.")
    clean = value.strip()
    if len(clean) > maximum_characters or "\x00" in clean:
        raise PortalCaptureError(f"{field} is invalid or too long.")
    return clean


def normalize_cdp_url(value: str) -> str:
    """Return a root HTTP CDP endpoint after enforcing a loopback-only boundary."""

    clean = _required_text(value, field="remote_url", maximum_characters=500)
    parts = urlsplit(clean)
    host = (parts.hostname or "").casefold()
    if (
        parts.scheme.casefold() != "http"
        or host not in LOOPBACK_HOSTS
        or parts.username
        or parts.password
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
    ):
        raise PortalCaptureError(
            "remote_url must be a root HTTP CDP endpoint on localhost, "
            "127.0.0.1, or ::1."
        )
    try:
        port = parts.port
    except ValueError as exc:
        raise PortalCaptureError("remote_url contains an invalid port.") from exc
    if port is not None and not 1 <= port <= 65_535:
        raise PortalCaptureError("remote_url contains an invalid port.")
    display_host = f"[{host}]" if ":" in host else host
    netloc = f"{display_host}:{port}" if port is not None else display_host
    return urlunsplit(("http", netloc, "", "", ""))


def _is_allowed_inps_host(host: str) -> bool:
    normalized = host.casefold().rstrip(".")
    return any(
        normalized == suffix or normalized.endswith(f".{suffix}")
        for suffix in ALLOWED_INPS_SUFFIXES
    )


def normalize_approved_origin(value: str) -> str:
    """Return an exact HTTPS origin restricted to inps.it and its subdomains."""

    clean = _required_text(value, field="approved_origin", maximum_characters=500)
    parts = urlsplit(clean)
    host = (parts.hostname or "").casefold().rstrip(".")
    try:
        port = parts.port
    except ValueError as exc:
        raise PortalCaptureError("approved_origin contains an invalid port.") from exc
    if (
        parts.scheme.casefold() != "https"
        or not _is_allowed_inps_host(host)
        or parts.username
        or parts.password
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
        or port not in {None, 443}
    ):
        raise PortalCaptureError(
            "approved_origin must be an exact HTTPS origin under inps.it."
        )
    return f"https://{host}"


def _page_origin(value: str) -> str | None:
    """Return a normalized INPS origin for page matching, without exposing the URL."""

    try:
        parts = urlsplit(str(value or ""))
        host = (parts.hostname or "").casefold().rstrip(".")
        port = parts.port
    except ValueError:
        return None
    if (
        parts.scheme.casefold() != "https"
        or not _is_allowed_inps_host(host)
        or parts.username
        or parts.password
        or port not in {None, 443}
    ):
        return None
    return f"https://{host}"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _absolute_path_without_symlinks(path: Path, *, label: str) -> Path:
    expanded = path.expanduser()
    candidate = expanded if expanded.is_absolute() else Path.cwd() / expanded
    absolute = Path(os.path.abspath(candidate))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            raise PortalCaptureError(f"{label} cannot contain symbolic links.")
    return absolute


def _reject_git_workspace(path: Path) -> None:
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            raise PortalCaptureError(
                "portal capture output must be outside a Git workspace."
            )


def _prepare_new_output_path(path: Path) -> Path:
    output = _absolute_path_without_symlinks(path, label="output directory")
    _reject_git_workspace(output)
    if output.exists():
        raise PortalCaptureError("output directory must not already exist.")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PortalCaptureError(
            f"could not prepare the private output location ({type(exc).__name__})."
        ) from exc
    return output


def _write_private_bytes(path: Path, value: bytes) -> None:
    path.touch(mode=0o600, exist_ok=False)
    path.chmod(0o600)
    path.write_bytes(value)
    path.chmod(0o600)


def _write_private_json(path: Path, payload: Mapping[str, Any]) -> None:
    raw = (
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _write_private_bytes(path, raw)


def _load_playwright_runtime() -> tuple[Callable[[], Any], type[BaseException]]:
    """Import Playwright only when a real browser capture is requested."""

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise PortalCaptureError(
            "Playwright is unavailable; install the declared connector dependency first."
        ) from exc
    return sync_playwright, PlaywrightError


def _capture_from_page(
    page: Any, approved_origin: str, timeout_ms: int
) -> tuple[bytes, bytes, str, str]:
    initial_url = str(page.url or "")
    if _page_origin(initial_url) != approved_origin:
        raise PortalCaptureError("the selected page left the approved INPS origin.")
    title = str(page.title() or "")
    body_text = str(page.locator("body").inner_text(timeout=timeout_ms) or "")
    screenshot = page.screenshot(type="png", full_page=True, timeout=timeout_ms)
    final_url = str(page.url or "")
    if final_url != initial_url or _page_origin(final_url) != approved_origin:
        raise PortalCaptureError("the selected page changed during capture.")
    if not isinstance(screenshot, bytes) or not screenshot.startswith(PNG_SIGNATURE):
        raise PortalCaptureError("the browser did not return a valid PNG screenshot.")
    normalized_text = body_text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized_text.encode("utf-8"), screenshot, initial_url, title


def capture_portal_snapshot(
    *,
    remote_url: str,
    approved_origin: str,
    output_dir: Path,
    timeout_ms: int = 20_000,
    playwright_factory: Callable[[], Any] | None = None,
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    """Capture visible evidence from exactly one matching, already-open browser page.

    The fixed read-only boundary is security- and audit-driven: this function never
    authenticates, navigates, clicks, fills fields, reads cookies or browser storage,
    serializes page HTML, uploads case content, or closes the attached browser.
    """

    cdp_url = normalize_cdp_url(remote_url)
    origin = normalize_approved_origin(approved_origin)
    if not isinstance(timeout_ms, int) or not 1 <= timeout_ms <= 120_000:
        raise PortalCaptureError("timeout_ms must be an integer from 1 to 120000.")
    if captured_at is not None and (
        not isinstance(captured_at, datetime)
        or captured_at.tzinfo is None
        or captured_at.utcoffset() is None
    ):
        raise PortalCaptureError("captured_at must include a timezone.")
    output = _prepare_new_output_path(output_dir)

    expected_errors: tuple[type[BaseException], ...] = (
        OSError,
        RuntimeError,
        TypeError,
    )
    if playwright_factory is None:
        sync_playwright, playwright_error = _load_playwright_runtime()
        playwright_factory = lambda: sync_playwright().start()
        expected_errors = (*expected_errors, playwright_error)

    playwright = None
    try:
        playwright = playwright_factory()
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        pages = [page for context in browser.contexts for page in context.pages]
        matches = [
            page for page in pages if _page_origin(str(page.url or "")) == origin
        ]
        if len(matches) != 1:
            raise PortalCaptureError(
                "exactly one already-open page must match the approved INPS origin."
            )
        text_bytes, screenshot_bytes, full_url, title = _capture_from_page(
            matches[0], origin, timeout_ms
        )
    except PortalCaptureError:
        raise
    except expected_errors as exc:
        raise PortalCaptureError(
            f"browser capture failed ({type(exc).__name__})."
        ) from exc
    finally:
        if playwright is not None:
            try:
                playwright.stop()
            except expected_errors:
                pass

    capture_time = captured_at or datetime.now(timezone.utc)
    captured_at_text = (
        capture_time.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    )
    capture_id = f"inps-capture-{uuid.uuid4().hex}"
    artifacts = [
        {
            "path": VISIBLE_TEXT_NAME,
            "media_type": EXPECTED_ARTIFACTS[VISIBLE_TEXT_NAME],
            "size_bytes": len(text_bytes),
            "sha256": _sha256_bytes(text_bytes),
        },
        {
            "path": SCREENSHOT_NAME,
            "media_type": EXPECTED_ARTIFACTS[SCREENSHOT_NAME],
            "size_bytes": len(screenshot_bytes),
            "sha256": _sha256_bytes(screenshot_bytes),
        },
    ]
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "capture_id": capture_id,
        "captured_at": captured_at_text,
        "route_selected": True,
        "capture_method": "attached_chrome_visible_page_read_only",
        "approved_origin": origin,
        "source_url_sha256": _sha256_bytes(full_url.encode("utf-8")),
        "page_title_sha256": _sha256_bytes(title.encode("utf-8")),
        "body_character_count": len(text_bytes.decode("utf-8")),
        "guardrails": dict(GUARDRAILS),
        "artifacts": artifacts,
    }

    temporary = output.with_name(f".{output.name}.capturing-{uuid.uuid4().hex}")
    try:
        temporary.mkdir(mode=0o700, exist_ok=False)
        temporary.chmod(0o700)
        _write_private_bytes(temporary / VISIBLE_TEXT_NAME, text_bytes)
        _write_private_bytes(temporary / SCREENSHOT_NAME, screenshot_bytes)
        _write_private_json(temporary / MANIFEST_NAME, manifest)
        if output.exists():
            raise PortalCaptureError("output directory appeared during capture.")
        temporary.rename(output)
        output.chmod(0o700)
    except (OSError, PortalCaptureError) as exc:
        if temporary.exists():
            shutil.rmtree(temporary)
        if isinstance(exc, PortalCaptureError):
            raise
        raise PortalCaptureError(
            f"could not persist the private capture ({type(exc).__name__})."
        ) from exc

    verify_portal_snapshot(output)
    return manifest


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PortalCaptureError("portal capture manifest is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise PortalCaptureError("portal capture manifest must be an object.")
    return payload


def _assert_private_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise PortalCaptureError("portal capture contains a non-regular file.")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PortalCaptureError("portal capture files must be owner-only (0600).")


def verify_portal_snapshot(output_dir: Path) -> dict[str, Any]:
    """Verify the private manifest and every hash-bound capture artifact."""

    output = _absolute_path_without_symlinks(
        output_dir, label="portal capture directory"
    )
    if not output.is_dir():
        raise PortalCaptureError("portal capture directory does not exist.")
    if stat.S_IMODE(output.stat().st_mode) & 0o077:
        raise PortalCaptureError("portal capture directory must be owner-only (0700).")

    expected_names = {MANIFEST_NAME, *EXPECTED_ARTIFACTS}
    actual_names = {entry.name for entry in output.iterdir()}
    if actual_names != expected_names:
        raise PortalCaptureError("portal capture directory has unexpected files.")

    manifest_path = output / MANIFEST_NAME
    _assert_private_file(manifest_path)
    manifest = _load_manifest(manifest_path)
    if set(manifest) != TOP_LEVEL_FIELDS:
        raise PortalCaptureError("portal capture manifest fields are invalid.")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise PortalCaptureError("unsupported portal capture schema version.")
    if not CAPTURE_ID_RE.fullmatch(str(manifest.get("capture_id", ""))):
        raise PortalCaptureError("portal capture ID is invalid.")
    _timezone_datetime(manifest.get("captured_at"), field="captured_at")
    if manifest.get("route_selected") is not True:
        raise PortalCaptureError("portal capture route selection is invalid.")
    if manifest.get("capture_method") != "attached_chrome_visible_page_read_only":
        raise PortalCaptureError("portal capture method is invalid.")
    normalize_approved_origin(str(manifest.get("approved_origin", "")))
    for field in ("source_url_sha256", "page_title_sha256"):
        if not SHA256_RE.fullmatch(str(manifest.get(field, ""))):
            raise PortalCaptureError(f"{field} must be a lowercase SHA-256 value.")
    if (
        not isinstance(manifest.get("body_character_count"), int)
        or manifest["body_character_count"] < 0
    ):
        raise PortalCaptureError("body_character_count must be a non-negative integer.")
    if manifest.get("guardrails") != GUARDRAILS:
        raise PortalCaptureError("portal capture guardrails are incomplete.")

    raw_artifacts = manifest.get("artifacts")
    if not isinstance(raw_artifacts, list) or len(raw_artifacts) != len(
        EXPECTED_ARTIFACTS
    ):
        raise PortalCaptureError("portal capture artifact ledger is invalid.")
    artifact_records: dict[str, Mapping[str, Any]] = {}
    for record in raw_artifacts:
        if not isinstance(record, Mapping) or set(record) != ARTIFACT_FIELDS:
            raise PortalCaptureError("portal capture artifact record is invalid.")
        relative = str(record.get("path", ""))
        if relative in artifact_records or relative not in EXPECTED_ARTIFACTS:
            raise PortalCaptureError("portal capture artifact path is invalid.")
        artifact_records[relative] = record

    for relative, expected_media_type in EXPECTED_ARTIFACTS.items():
        record = artifact_records.get(relative)
        if record is None or record.get("media_type") != expected_media_type:
            raise PortalCaptureError("portal capture artifact media type is invalid.")
        artifact_path = output / relative
        _assert_private_file(artifact_path)
        size_bytes = artifact_path.stat().st_size
        if record.get("size_bytes") != size_bytes:
            raise PortalCaptureError("portal capture artifact size has changed.")
        expected_sha = str(record.get("sha256", ""))
        if (
            not SHA256_RE.fullmatch(expected_sha)
            or _sha256_file(artifact_path) != expected_sha
        ):
            raise PortalCaptureError("portal capture artifact hash has changed.")

    try:
        visible_text = (output / VISIBLE_TEXT_NAME).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PortalCaptureError("portal visible text is not valid UTF-8.") from exc
    if len(visible_text) != manifest["body_character_count"]:
        raise PortalCaptureError("portal visible text character count has changed.")
    if not (output / SCREENSHOT_NAME).read_bytes().startswith(PNG_SIGNATURE):
        raise PortalCaptureError("portal screenshot is not a valid PNG.")

    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "capture_id": manifest["capture_id"],
        "artifact_count": len(EXPECTED_ARTIFACTS),
    }


def _capture_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "capture", help="Capture exactly one selected, already-open INPS tab."
    )
    parser.add_argument("--remote-url", default="http://127.0.0.1:9222")
    parser.add_argument("--approved-origin", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout-ms", type=int, default=20_000)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the explicit capture or integrity-verification command."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    _capture_parser(subparsers)
    verify_parser = subparsers.add_parser(
        "verify", help="Verify a previously captured local snapshot."
    )
    verify_parser.add_argument("output_dir", type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.command == "verify":
            result = verify_portal_snapshot(args.output_dir)
        else:
            manifest = capture_portal_snapshot(
                remote_url=args.remote_url,
                approved_origin=args.approved_origin,
                output_dir=args.output_dir,
                timeout_ms=args.timeout_ms,
            )
            result = {
                "ok": True,
                "capture_id": manifest["capture_id"],
                "artifact_count": len(manifest["artifacts"]),
            }
    except PortalCaptureError as exc:
        LOGGER.error("Portal capture blocked: %s", exc)
        return 1
    LOGGER.info(
        "Portal capture %s: %s artifact(s) verified.",
        result["capture_id"],
        result["artifact_count"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
