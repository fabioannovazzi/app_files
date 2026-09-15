#!/usr/bin/env python3
"""Notify the user when a newer published Mparanza plugin is available."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

__all__ = ["check_for_update", "is_newer_version", "session_start_output", "main"]

VERSION_MANIFEST_URL = "https://mparanza.com/static/shared/codex-plugin-versions.json"
CHECK_INTERVAL_SECONDS = 24 * 60 * 60
NETWORK_TIMEOUT_SECONDS = 3.0
_SEMVER_PATTERN = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def _parse_semver(version: str) -> tuple[int, int, int, tuple[tuple[int, Any], ...]]:
    """Return a SemVer comparison key; build metadata is intentionally ignored."""

    match = _SEMVER_PATTERN.fullmatch(version.strip())
    if match is None:
        raise ValueError(f"Invalid semantic version: {version}")
    prerelease = match.group("prerelease")
    if prerelease is None:
        prerelease_key: tuple[tuple[int, Any], ...] = ((2, ""),)
    else:
        parts: list[tuple[int, Any]] = []
        for identifier in prerelease.split("."):
            if identifier.isdigit():
                parts.append((0, int(identifier)))
            else:
                parts.append((1, identifier))
        prerelease_key = tuple(parts)
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        prerelease_key,
    )


def is_newer_version(candidate: str, installed: str) -> bool:
    """Return whether ``candidate`` has greater SemVer precedence."""

    return _parse_semver(candidate) > _parse_semver(installed)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError:
        return


def _download_manifest(
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any] | None:
    request = urllib.request.Request(
        VERSION_MANIFEST_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mparanza-Plugin-Update-Check/1",
        },
        method="GET",
    )
    try:
        with opener(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
    except (
        OSError,
        TimeoutError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ):
        return None
    return payload if isinstance(payload, dict) else None


def _manifest_entry(
    manifest: dict[str, Any], plugin_name: str
) -> tuple[str, str] | None:
    if manifest.get("schema_version") != 1:
        return None
    plugins = manifest.get("plugins")
    if not isinstance(plugins, dict):
        return None
    entry = plugins.get(plugin_name)
    if not isinstance(entry, dict):
        return None
    version = entry.get("published_version")
    install_url = entry.get("install_url")
    if not isinstance(version, str) or not isinstance(install_url, str):
        return None
    if not install_url.startswith("https://chatgpt.com/plugins/"):
        return None
    return version, install_url


def check_for_update(
    plugin_root: Path,
    plugin_data: Path | None,
    *,
    now: float | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> str | None:
    """Return a user-facing update message, or ``None`` when none is needed."""

    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    local_manifest = _read_json(manifest_path)
    if local_manifest is None:
        return None
    plugin_name = local_manifest.get("name")
    installed_version = local_manifest.get("version")
    if not isinstance(plugin_name, str) or not isinstance(installed_version, str):
        return None

    checked_at = now if now is not None else time.time()
    cache_path = plugin_data / "update-check.json" if plugin_data is not None else None
    cache = _read_json(cache_path) if cache_path is not None else None
    cached_manifest = cache.get("manifest") if cache is not None else None
    if not isinstance(cached_manifest, dict):
        cached_manifest = None
    remote_manifest: dict[str, Any] | None = None
    if cache is not None:
        cached_at = cache.get("checked_at")
        if (
            isinstance(cached_at, (int, float))
            and checked_at - float(cached_at) < CHECK_INTERVAL_SECONDS
            and cached_manifest is not None
        ):
            remote_manifest = cached_manifest

    if remote_manifest is None:
        downloaded_manifest = _download_manifest(opener)
        remote_manifest = downloaded_manifest or cached_manifest or {}
        if cache_path is not None:
            cache_payload: dict[str, Any] = {
                "checked_at": checked_at,
                "manifest": remote_manifest,
            }
            _write_json(
                cache_path,
                cache_payload,
            )

    entry = _manifest_entry(remote_manifest, plugin_name)
    if entry is None:
        return None
    published_version, install_url = entry
    try:
        update_available = is_newer_version(published_version, installed_version)
    except ValueError:
        return None
    if not update_available:
        return None
    interface = local_manifest.get("interface")
    display_name = (
        interface.get("displayName") if isinstance(interface, dict) else None
    ) or plugin_name
    return (
        f"{display_name} update available: installed {installed_version}, "
        f"published {published_version}. Visit {install_url} to get the latest "
        "published version."
    )


def _check_fixed_change_requests(
    plugin_root: Path, plugin_data: Path | None
) -> str | None:
    """Poll stored CR receipts without making the SessionStart hook fragile."""

    try:
        from change_requests import check_fixed_requests

        return check_fixed_requests(
            plugin_root,
            plugin_data,
            timeout_seconds=2.0,
        )
    except (ImportError, OSError, RuntimeError, ValueError):
        return None


def session_start_output(*, include_change_requests: bool = True) -> dict[str, Any]:
    """Build one hook response; package identity is local, never sent upstream."""
    plugin_root = Path(
        os.environ.get("PLUGIN_ROOT", Path(__file__).resolve().parents[1])
    ).resolve()
    plugin_data_value = os.environ.get("PLUGIN_DATA")
    plugin_data = Path(plugin_data_value).resolve() if plugin_data_value else None
    manifest = _read_json(plugin_root / ".codex-plugin/plugin.json") or {}
    identity = (
        f"Installed plugin manifest: {manifest.get('name', 'unknown')} "
        f"{manifest.get('version', 'unknown')}. "
        "This identifies this package, not Marketplace publication or successful "
        "user-visible behavior. Do not claim a fix is active from source tests, "
        "a download or another cached version."
    )
    messages = []
    if include_change_requests:
        fixed_message = _check_fixed_change_requests(plugin_root, plugin_data)
        if fixed_message:
            messages.append(fixed_message)
    update_message = check_for_update(plugin_root, plugin_data)
    if update_message:
        messages.append(update_message)
    output: dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": identity,
        }
    }
    if messages:
        message = "\n".join(messages)
        output["systemMessage"] = message
        output["hookSpecificOutput"]["additionalContext"] += (
            " Tell the user the following notice in their language before "
            "continuing; do not treat it as proof they saw it: " + message
        )
    return output


def main(argv: list[str] | None = None) -> int:
    """Check from the installed package, including when a trusted hook is absent."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version-only", action="store_true", help="Do not poll change requests."
    )
    args = parser.parse_args(argv)
    output = session_start_output(include_change_requests=not args.version_only)
    sys.stdout.write(json.dumps(output) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
