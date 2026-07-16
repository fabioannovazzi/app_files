#!/usr/bin/env python3
"""Notify the user when a newer published Mparanza plugin is available."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

__all__ = ["check_for_update", "is_newer_version", "main"]

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
            if cache is not None:
                for key in ("last_notified_at", "last_notified_version"):
                    if key in cache:
                        cache_payload[key] = cache[key]
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
    if cache is not None:
        last_notified_version = cache.get("last_notified_version")
        last_notified_at = cache.get("last_notified_at")
        if (
            last_notified_version == published_version
            and isinstance(last_notified_at, (int, float))
            and checked_at - float(last_notified_at) < CHECK_INTERVAL_SECONDS
        ):
            return None
    if cache_path is not None:
        _write_json(
            cache_path,
            {
                "checked_at": checked_at,
                "manifest": remote_manifest,
                "last_notified_at": checked_at,
                "last_notified_version": published_version,
            },
        )
    interface = local_manifest.get("interface")
    display_name = (
        interface.get("displayName") if isinstance(interface, dict) else None
    ) or plugin_name
    return (
        f"{display_name} update available: installed {installed_version}, "
        f"published {published_version}. Visit {install_url} to get the latest "
        "published version."
    )


def main() -> int:
    """Run the fail-open SessionStart update check."""

    plugin_root = Path(
        os.environ.get("PLUGIN_ROOT", Path(__file__).resolve().parents[1])
    ).resolve()
    plugin_data_value = os.environ.get("PLUGIN_DATA")
    plugin_data = Path(plugin_data_value).resolve() if plugin_data_value else None
    message = check_for_update(plugin_root, plugin_data)
    if message is not None:
        print(json.dumps({"systemMessage": message}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
