#!/usr/bin/env python3
"""Submit and track user-approved Mparanza plugin change requests."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import logging
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

__all__ = [
    "ChangeRequestError",
    "check_fixed_requests",
    "main",
    "reserve_suggestion_prompt",
    "start_interview",
    "submit_problem",
    "submit_suggestion",
]

DEFAULT_BASE_URL = "https://mparanza.com"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_REQUEST_FILE_BYTES = 48 * 1024
MAX_WIRE_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
MAX_OPPORTUNITY_CHARS = 4_000
MAX_STATUS_BATCH = 100
PROMPT_COOLDOWN_SECONDS = 14 * 24 * 60 * 60
PROMPT_RESERVED_AT_FIELD = "suggestion_prompt_reserved_at"
STATE_SCHEMA_VERSION = 1
STATE_FILE_NAME = "state.json"
ALLOWED_REMOTE_HOSTS = frozenset({"mparanza.com", "www.mparanza.com"})
LOCAL_TEST_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
LANGUAGES = ("it", "en", "fr", "de")
_CHANGE_REQUEST_ID = re.compile(r"^CR-[1-9]\d*$")
LOGGER = logging.getLogger(__name__)


class ChangeRequestError(RuntimeError):
    """Raised when a change-request operation cannot be completed safely."""


def _normalize_base_url(base_url: str) -> str:
    clean = base_url.strip()
    parts = urllib.parse.urlsplit(clean)
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError as exc:
        raise ChangeRequestError("Invalid change-request server port.") from exc
    if (
        not clean
        or not parts.scheme
        or not host
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in {"", "/"}
    ):
        raise ChangeRequestError("Invalid change-request server URL.")
    if host in LOCAL_TEST_HOSTS:
        if parts.scheme not in {"http", "https"}:
            raise ChangeRequestError("A local test server must use HTTP or HTTPS.")
    elif (
        parts.scheme != "https"
        or host not in ALLOWED_REMOTE_HOSTS
        or port
        not in {
            None,
            443,
        }
    ):
        raise ChangeRequestError(
            "The change-request server must be https://mparanza.com."
        )
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")


def _validate_interview_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChangeRequestError("The interview response is missing interview_url.")
    parts = urllib.parse.urlsplit(value.strip())
    host = (parts.hostname or "").lower()
    if parts.username or parts.password or not parts.path:
        raise ChangeRequestError("The interview response contains an invalid URL.")
    if host in LOCAL_TEST_HOSTS:
        allowed = parts.scheme in {"http", "https"}
    else:
        allowed = parts.scheme == "https" and host in ALLOWED_REMOTE_HOSTS
    if not allowed:
        raise ChangeRequestError("The interview URL is not hosted by Mparanza.")
    return value.strip()


def _validate_install_url(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.startswith(
        "https://chatgpt.com/plugins/"
    ):
        raise ChangeRequestError("The response contains an invalid install URL.")
    return value


def _read_plugin_identity(plugin_root: Path) -> tuple[str, str]:
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChangeRequestError("Could not read the plugin manifest.") from exc
    if not isinstance(manifest, Mapping):
        raise ChangeRequestError("The plugin manifest must be a JSON object.")
    name = manifest.get("name")
    version = manifest.get("version")
    if name not in {"clara", "vera"} or not isinstance(version, str) or not version:
        raise ChangeRequestError("Unsupported plugin identity.")
    return str(name), version


def _stable_state_dir(plugin_name: str) -> Path:
    override = os.environ.get("MPARANZA_CHANGE_REQUEST_DATA")
    base = (
        Path(override).expanduser()
        if override
        else Path.home() / ".codex" / "mparanza" / "change-requests"
    )
    return base / plugin_name


def _state_paths(plugin_name: str, plugin_data: Path | None) -> list[Path]:
    paths = [_stable_state_dir(plugin_name) / STATE_FILE_NAME]
    if plugin_data is not None:
        explicit = (
            plugin_data.expanduser().resolve() / "change-requests" / STATE_FILE_NAME
        )
        if explicit not in paths:
            paths.append(explicit)
    return paths


@contextmanager
def _locked_state(plugin_name: str) -> Iterator[None]:
    """Serialize receipt mutations across parallel local Codex processes."""

    lock_path = _stable_state_dir(plugin_name) / ".state.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        lock_path.chmod(0o600)
        if sys.platform == "win32":
            msvcrt = importlib.import_module("msvcrt")
            lock_file.seek(0)
            if not lock_file.read(1):
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            return
        fcntl = importlib.import_module("fcntl")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _empty_state(plugin_name: str) -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "plugin": plugin_name,
        "requests": [],
    }


def _read_state(path: Path, plugin_name: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChangeRequestError(
            f"Could not read change-request state: {path}"
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != STATE_SCHEMA_VERSION
        or payload.get("plugin") != plugin_name
        or not isinstance(payload.get("requests"), list)
    ):
        raise ChangeRequestError(f"Invalid change-request state: {path}")
    return payload


def _merge_entry(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_updated = float(left.get("updated_at", 0) or 0)
    right_updated = float(right.get("updated_at", 0) or 0)
    older, newer = (left, right) if left_updated <= right_updated else (right, left)
    merged = dict(older)
    merged.update(newer)
    notified = [
        value
        for value in (left.get("fixed_notified_at"), right.get("fixed_notified_at"))
        if isinstance(value, (int, float))
    ]
    if notified:
        merged["fixed_notified_at"] = max(float(value) for value in notified)
    return merged


def _load_state(plugin_name: str, plugin_data: Path | None) -> dict[str, Any]:
    entries: dict[str, dict[str, Any]] = {}
    prompt_reservations: list[float] = []
    for path in _state_paths(plugin_name, plugin_data):
        state = _read_state(path, plugin_name)
        if state is None:
            continue
        prompt_reserved_at = state.get(PROMPT_RESERVED_AT_FIELD)
        if prompt_reserved_at is not None:
            if (
                isinstance(prompt_reserved_at, bool)
                or not isinstance(prompt_reserved_at, (int, float))
                or prompt_reserved_at < 0
            ):
                raise ChangeRequestError(f"Invalid prompt reservation in {path}")
            prompt_reservations.append(float(prompt_reserved_at))
        for raw_entry in state["requests"]:
            if not isinstance(raw_entry, dict):
                raise ChangeRequestError(f"Invalid request entry in {path}")
            submission_id = raw_entry.get("submission_id")
            try:
                uuid.UUID(str(submission_id))
            except (ValueError, AttributeError) as exc:
                raise ChangeRequestError(f"Invalid submission_id in {path}") from exc
            entry = dict(raw_entry)
            if submission_id in entries:
                entries[str(submission_id)] = _merge_entry(
                    entries[str(submission_id)], entry
                )
            else:
                entries[str(submission_id)] = entry
    state = _empty_state(plugin_name)
    state["requests"] = sorted(
        entries.values(), key=lambda entry: float(entry.get("created_at", 0) or 0)
    )
    if prompt_reservations:
        state[PROMPT_RESERVED_AT_FIELD] = max(prompt_reservations)
    return state


def _write_one_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = (
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    )
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary.write(serialized)
            temporary_path = Path(temporary.name)
        temporary_path.chmod(0o600)
        temporary_path.replace(path)
        path.chmod(0o600)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _write_state(
    state: dict[str, Any], plugin_name: str, plugin_data: Path | None
) -> None:
    errors: list[OSError] = []
    written = 0
    for path in _state_paths(plugin_name, plugin_data):
        try:
            _write_one_state(path, state)
        except OSError as exc:
            errors.append(exc)
        else:
            written += 1
    if written == 0:
        raise ChangeRequestError("Could not persist change-request state.") from (
            errors[0] if errors else None
        )


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ChangeRequestError("The change request is not valid JSON.") from exc
    if len(encoded) > MAX_WIRE_BYTES:
        raise ChangeRequestError("The change request is too large to submit.")
    return encoded


def _payload_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _read_request_file(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ChangeRequestError(f"Could not read request file: {path}") from exc
    if size > MAX_REQUEST_FILE_BYTES:
        raise ChangeRequestError("The request file is too large to submit.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ChangeRequestError("The request file is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ChangeRequestError("The request file must contain a JSON object.")
    return payload


def _response_json(response: Any) -> dict[str, Any]:
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ChangeRequestError("The change-request response is too large.")
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ChangeRequestError(
            "The change-request response is not valid JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise ChangeRequestError("The change-request response must be a JSON object.")
    return payload


def _post_json(
    base_url: str,
    path: str,
    payload: Mapping[str, Any],
    *,
    opener: Callable[..., Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    data = _canonical_bytes(payload)
    request = urllib.request.Request(
        f"{_normalize_base_url(base_url)}{path}",
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mparanza-Plugin-Change-Request/1",
        },
    )
    try:
        with opener(request, timeout=timeout_seconds) as response:
            return _response_json(response)
    except urllib.error.HTTPError as exc:
        try:
            detail = _response_json(exc).get("detail")
        except ChangeRequestError:
            detail = None
        message = f"Change-request server rejected the request ({exc.code})."
        if isinstance(detail, str) and detail:
            message += f" {detail}"
        raise ChangeRequestError(message) from exc
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise ChangeRequestError(
            f"Could not reach the change-request server: {exc}"
        ) from exc


def _validate_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    request_id = payload.get("change_request_id")
    token = payload.get("status_token")
    status = payload.get("status")
    if (
        not isinstance(request_id, str)
        or _CHANGE_REQUEST_ID.fullmatch(request_id) is None
    ):
        raise ChangeRequestError("The response contains an invalid change-request ID.")
    if not isinstance(token, str) or not token or len(token) > 2_048:
        raise ChangeRequestError("The response contains an invalid status token.")
    if status not in {"open", "fixed"}:
        raise ChangeRequestError("The response contains an invalid request status.")
    fixed = payload.get("fixed")
    if not isinstance(fixed, bool) or fixed != (status == "fixed"):
        raise ChangeRequestError("The response contains inconsistent fixed status.")
    fixed_version = payload.get("fixed_version")
    if fixed_version is not None and not isinstance(fixed_version, str):
        raise ChangeRequestError("The response contains an invalid fixed version.")
    return {
        "change_request_id": request_id,
        "status_token": token,
        "status": status,
        "fixed": fixed,
        "fixed_version": fixed_version,
        "install_url": _validate_install_url(payload.get("install_url")),
    }


def _validate_interview_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != 1 or payload.get("status") != "open":
        raise ChangeRequestError("The interview response has an unsupported schema.")
    request_id = payload.get("change_request_id")
    token = payload.get("status_token")
    if (
        not isinstance(request_id, str)
        or _CHANGE_REQUEST_ID.fullmatch(request_id) is None
    ):
        raise ChangeRequestError("The interview response has an invalid request ID.")
    if not isinstance(token, str) or not token or len(token) > 2_048:
        raise ChangeRequestError("The interview response has an invalid status token.")
    return {
        "change_request_id": request_id,
        "status_token": token,
        "status": "open",
        "fixed": False,
        "fixed_version": None,
        "install_url": None,
        "interview_url": _validate_interview_url(payload.get("interview_url")),
    }


def _find_or_create_entry(
    state: dict[str, Any],
    *,
    kind: str,
    plugin_name: str,
    plugin_version: str,
    request_without_id: Mapping[str, Any],
    now: float,
) -> tuple[dict[str, Any], bool]:
    fingerprint = _payload_hash(request_without_id)
    for entry in state["requests"]:
        if entry.get("kind") == kind and entry.get("payload_hash") == fingerprint:
            return entry, False
    submission_id = str(uuid.uuid4())
    wire_payload = dict(request_without_id)
    wire_payload["submission_id"] = submission_id
    entry = {
        "submission_id": submission_id,
        "kind": kind,
        "plugin": plugin_name,
        "plugin_version": plugin_version,
        "payload_hash": fingerprint,
        "pending_payload": wire_payload,
        "created_at": now,
        "updated_at": now,
        "status": "pending",
    }
    state["requests"].append(entry)
    return entry, True


def _reserve_entry(
    *,
    kind: str,
    plugin_name: str,
    plugin_version: str,
    plugin_data: Path | None,
    request_without_id: Mapping[str, Any],
    now: float,
) -> dict[str, Any]:
    with _locked_state(plugin_name):
        state = _load_state(plugin_name, plugin_data)
        entry, _created = _find_or_create_entry(
            state,
            kind=kind,
            plugin_name=plugin_name,
            plugin_version=plugin_version,
            request_without_id=request_without_id,
            now=now,
        )
        _write_state(state, plugin_name, plugin_data)
        return dict(entry)


def _stored_receipt(entry: Mapping[str, Any]) -> dict[str, Any] | None:
    request_id = entry.get("change_request_id")
    token = entry.get("status_token")
    if not isinstance(request_id, str) or not isinstance(token, str):
        return None
    return {
        key: entry.get(key)
        for key in (
            "submission_id",
            "change_request_id",
            "status_token",
            "status",
            "fixed",
            "fixed_version",
            "install_url",
            "interview_url",
        )
        if key in entry
    }


def _save_receipt(
    entry: dict[str, Any], receipt: Mapping[str, Any], *, now: float
) -> dict[str, Any]:
    entry.update(receipt)
    entry["updated_at"] = now
    entry.pop("pending_payload", None)
    stored = _stored_receipt(entry)
    if stored is None:
        raise ChangeRequestError("Could not store the change-request receipt.")
    return stored


def _persist_receipt(
    *,
    plugin_name: str,
    plugin_data: Path | None,
    submission_id: str,
    receipt: Mapping[str, Any],
    now: float,
) -> dict[str, Any]:
    with _locked_state(plugin_name):
        state = _load_state(plugin_name, plugin_data)
        entry = next(
            (
                candidate
                for candidate in state["requests"]
                if candidate.get("submission_id") == submission_id
            ),
            None,
        )
        if entry is None:
            raise ChangeRequestError("The reserved change request is missing.")
        existing = _stored_receipt(entry)
        if existing is not None:
            return existing
        stored = _save_receipt(entry, receipt, now=now)
        _write_state(state, plugin_name, plugin_data)
        return stored


def reserve_suggestion_prompt(
    plugin_root: Path,
    *,
    plugin_data: Path | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Atomically reserve one ask; fixed timing prevents concurrent prompt spam."""

    plugin_name, _plugin_version = _read_plugin_identity(plugin_root)
    checked_at = time.time() if now is None else now
    with _locked_state(plugin_name):
        state = _load_state(plugin_name, plugin_data)
        reserved_at = state.get(PROMPT_RESERVED_AT_FIELD)
        ask = (
            reserved_at is None
            or checked_at - float(reserved_at) >= PROMPT_COOLDOWN_SECONDS
        )
        if ask:
            reserved_at = checked_at
            state[PROMPT_RESERVED_AT_FIELD] = checked_at
        # These paths are replicas: one durable write preserves the cooldown, and
        # the next successful load/write cycle repairs a temporarily failed replica.
        _write_state(state, plugin_name, plugin_data)
    next_eligible_at = float(reserved_at) + PROMPT_COOLDOWN_SECONDS
    return {
        "ask": ask,
        "cooldown_seconds": PROMPT_COOLDOWN_SECONDS,
        "reserved_at": float(reserved_at),
        "next_eligible_at": next_eligible_at,
    }


def _submit_text_request(
    plugin_root: Path,
    request_path: Path,
    *,
    kind: str,
    plugin_data: Path | None = None,
    base_url: str = DEFAULT_BASE_URL,
    opener: Callable[..., Any] = urllib.request.urlopen,
    now: float | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Submit one approved text request and return its durable receipt."""

    plugin_name, plugin_version = _read_plugin_identity(plugin_root)
    request_payload = _read_request_file(request_path)
    checked_at = time.time() if now is None else now
    body_without_id = {
        "schema_version": 1,
        "kind": kind,
        "plugin": plugin_name,
        "plugin_version": plugin_version,
        "request": request_payload,
    }
    entry = _reserve_entry(
        kind=kind,
        plugin_name=plugin_name,
        plugin_version=plugin_version,
        plugin_data=plugin_data,
        request_without_id=body_without_id,
        now=checked_at,
    )
    existing = _stored_receipt(entry)
    if existing is not None:
        return existing
    pending_payload = entry.get("pending_payload")
    if not isinstance(pending_payload, dict):
        raise ChangeRequestError(f"The pending {kind} request cannot be retried.")
    response = _post_json(
        base_url,
        "/api/change-requests",
        pending_payload,
        opener=opener,
        timeout_seconds=timeout_seconds,
    )
    return _persist_receipt(
        plugin_name=plugin_name,
        plugin_data=plugin_data,
        submission_id=str(entry["submission_id"]),
        receipt=_validate_receipt(response),
        now=checked_at,
    )


def submit_problem(
    plugin_root: Path,
    request_path: Path,
    *,
    plugin_data: Path | None = None,
    base_url: str = DEFAULT_BASE_URL,
    opener: Callable[..., Any] = urllib.request.urlopen,
    now: float | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Submit one approved problem report and return its durable receipt."""

    return _submit_text_request(
        plugin_root,
        request_path,
        kind="problem",
        plugin_data=plugin_data,
        base_url=base_url,
        opener=opener,
        now=now,
        timeout_seconds=timeout_seconds,
    )


def submit_suggestion(
    plugin_root: Path,
    request_path: Path,
    *,
    plugin_data: Path | None = None,
    base_url: str = DEFAULT_BASE_URL,
    opener: Callable[..., Any] = urllib.request.urlopen,
    now: float | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Submit one approved capability suggestion and return its durable receipt."""

    return _submit_text_request(
        plugin_root,
        request_path,
        kind="capability",
        plugin_data=plugin_data,
        base_url=base_url,
        opener=opener,
        now=now,
        timeout_seconds=timeout_seconds,
    )


def start_interview(
    plugin_root: Path,
    opportunity: str,
    *,
    language: str = "it",
    plugin_data: Path | None = None,
    base_url: str = DEFAULT_BASE_URL,
    opener: Callable[..., Any] = urllib.request.urlopen,
    browser_opener: Callable[[str], Any] = webbrowser.open,
    now: float | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Create or resume a one-minute capability interview and open it."""

    clean_opportunity = opportunity.strip()
    if not clean_opportunity or len(clean_opportunity) > MAX_OPPORTUNITY_CHARS:
        raise ChangeRequestError("The interview opportunity must be 1-4000 characters.")
    if language not in LANGUAGES:
        raise ChangeRequestError("Unsupported interview language.")
    plugin_name, plugin_version = _read_plugin_identity(plugin_root)
    checked_at = time.time() if now is None else now
    body_without_id = {
        "schema_version": 1,
        "plugin": plugin_name,
        "plugin_version": plugin_version,
        "opportunity": clean_opportunity,
        "language": language,
    }
    entry = _reserve_entry(
        kind="capability",
        plugin_name=plugin_name,
        plugin_version=plugin_version,
        plugin_data=plugin_data,
        request_without_id=body_without_id,
        now=checked_at,
    )
    receipt = _stored_receipt(entry)
    if receipt is None:
        pending_payload = entry.get("pending_payload")
        if not isinstance(pending_payload, dict):
            raise ChangeRequestError("The pending interview cannot be retried.")
        response = _post_json(
            base_url,
            "/api/change-requests/interviews",
            pending_payload,
            opener=opener,
            timeout_seconds=timeout_seconds,
        )
        receipt = _persist_receipt(
            plugin_name=plugin_name,
            plugin_data=plugin_data,
            submission_id=str(entry["submission_id"]),
            receipt=_validate_interview_receipt(response),
            now=checked_at,
        )
    interview_url = receipt.get("interview_url")
    if not isinstance(interview_url, str):
        raise ChangeRequestError("The stored interview receipt has no interview URL.")
    browser_opener(interview_url)
    return receipt


def _status_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("requests")
    if not isinstance(rows, list):
        raise ChangeRequestError("The status response has no requests list.")
    parsed: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ChangeRequestError("The status response contains an invalid row.")
        request_id = row.get("change_request_id")
        if (
            not isinstance(request_id, str)
            or _CHANGE_REQUEST_ID.fullmatch(request_id) is None
        ):
            raise ChangeRequestError(
                "The status response contains an invalid request ID."
            )
        found = row.get("found")
        fixed = row.get("fixed")
        if not isinstance(found, bool) or not isinstance(fixed, bool):
            raise ChangeRequestError("The status response contains invalid flags.")
        if not found:
            parsed.append({"change_request_id": request_id, "found": False})
            continue
        status = row.get("status")
        if status not in {"open", "fixed"} or fixed != (status == "fixed"):
            raise ChangeRequestError(
                "The status response contains inconsistent status."
            )
        fixed_version = row.get("fixed_version")
        if fixed_version is not None and not isinstance(fixed_version, str):
            raise ChangeRequestError(
                "The status response has an invalid fixed version."
            )
        parsed.append(
            {
                "change_request_id": request_id,
                "found": True,
                "status": status,
                "fixed": fixed,
                "fixed_version": fixed_version,
                "install_url": _validate_install_url(row.get("install_url")),
            }
        )
    return parsed


def check_fixed_requests(
    plugin_root: Path,
    plugin_data: Path | None,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    now: float | None = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> str | None:
    """Return one-time messages for submitted requests that are now fixed."""

    try:
        plugin_name, _plugin_version = _read_plugin_identity(plugin_root)
        with _locked_state(plugin_name):
            state = _load_state(plugin_name, plugin_data)
            pending = [
                dict(entry)
                for entry in state["requests"]
                if isinstance(entry.get("change_request_id"), str)
                and isinstance(entry.get("status_token"), str)
                and entry.get("fixed_notified_at") is None
            ]
            if not pending:
                _write_state(state, plugin_name, plugin_data)
        if not pending:
            return None
        checked_at = time.time() if now is None else now
        updates_by_id: dict[str, dict[str, Any]] = {}
        for start in range(0, len(pending), MAX_STATUS_BATCH):
            batch = pending[start : start + MAX_STATUS_BATCH]
            response = _post_json(
                base_url,
                "/api/change-requests/status",
                {
                    "requests": [
                        {
                            "change_request_id": entry["change_request_id"],
                            "status_token": entry["status_token"],
                        }
                        for entry in batch
                    ]
                },
                opener=opener,
                timeout_seconds=timeout_seconds,
            )
            for row in _status_rows(response):
                if row.get("found"):
                    updates_by_id[row["change_request_id"]] = row
        newly_fixed: list[dict[str, Any]] = []
        with _locked_state(plugin_name):
            state = _load_state(plugin_name, plugin_data)
            for entry in state["requests"]:
                request_id = entry.get("change_request_id")
                row = updates_by_id.get(str(request_id))
                if row is None or entry.get("fixed_notified_at") is not None:
                    continue
                entry.update(
                    {key: value for key, value in row.items() if key != "found"}
                )
                entry["updated_at"] = checked_at
                if entry.get("status") == "fixed":
                    entry["fixed_notified_at"] = checked_at
                    newly_fixed.append(dict(entry))
            _write_state(state, plugin_name, plugin_data)
    except (ChangeRequestError, OSError, TypeError, ValueError):
        return None
    if not newly_fixed:
        return None
    return "\n".join(
        f"The problem you reported as {entry['change_request_id']} is fixed. Update now?"
        for entry in newly_fixed
    )


def _plugin_data_from_env() -> Path | None:
    value = os.environ.get("PLUGIN_DATA")
    return Path(value).expanduser() if value else None


def main() -> int:
    """Run the change-request command-line client."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plugin-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("MPARANZA_CHANGE_REQUEST_BASE_URL", DEFAULT_BASE_URL),
        help=argparse.SUPPRESS,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("reserve-suggestion-prompt")
    problem_parser = subparsers.add_parser("submit-problem")
    problem_parser.add_argument("--request", type=Path, required=True)
    suggestion_parser = subparsers.add_parser("submit-suggestion")
    suggestion_parser.add_argument("--request", type=Path, required=True)
    interview_parser = subparsers.add_parser("start-interview")
    interview_parser.add_argument("--opportunity", required=True)
    interview_parser.add_argument("--language", choices=LANGUAGES, default="it")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.command == "reserve-suggestion-prompt":
            receipt = reserve_suggestion_prompt(
                args.plugin_root,
                plugin_data=_plugin_data_from_env(),
            )
        elif args.command == "submit-problem":
            receipt = submit_problem(
                args.plugin_root,
                args.request,
                plugin_data=_plugin_data_from_env(),
                base_url=args.base_url,
            )
        elif args.command == "submit-suggestion":
            receipt = submit_suggestion(
                args.plugin_root,
                args.request,
                plugin_data=_plugin_data_from_env(),
                base_url=args.base_url,
            )
        else:
            receipt = start_interview(
                args.plugin_root,
                args.opportunity,
                language=args.language,
                plugin_data=_plugin_data_from_env(),
                base_url=args.base_url,
            )
    except ChangeRequestError as exc:
        LOGGER.error("%s", exc)
        return 2
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
