#!/usr/bin/env python3
"""Submit and track user-approved Mparanza plugin change requests."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import logging
import os
import platform
import re
import ssl
import stat
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "ChangeRequestError",
    "check_fixed_requests",
    "main",
    "reserve_suggestion_prompt",
    "start_interview",
    "submit_evidence",
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
LANGUAGES = ("it", "en", "fr", "de", "es")
_CHANGE_REQUEST_ID = re.compile(r"^CR-[1-9]\d*$")
_CA_BCONS_NOT_CRITICAL_VERIFY_CODE = 89
LOGGER = logging.getLogger(__name__)


class ChangeRequestError(RuntimeError):
    """Raised when a change-request operation cannot be completed safely."""


class _StateUnavailableError(ChangeRequestError):
    """Raised when no change-request state location can be used."""


class _StateLockContentionError(OSError):
    """Raised when a valid state lock is already held by another process."""


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
    manifest: Any = None
    for manifest_directory in (".codex-plugin", ".claude-plugin"):
        manifest_path = plugin_root / manifest_directory / "plugin.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, json.JSONDecodeError) as exc:
            raise ChangeRequestError("Could not read the plugin manifest.") from exc
        break
    if manifest is None:
        raise ChangeRequestError("Could not read the plugin manifest.")
    if not isinstance(manifest, Mapping):
        raise ChangeRequestError("The plugin manifest must be a JSON object.")
    name = manifest.get("name")
    version = manifest.get("version")
    if name not in {"clara", "vera"} or not isinstance(version, str) or not version:
        raise ChangeRequestError("Unsupported plugin identity.")
    return str(name), version


def _stable_state_dir(plugin_name: str) -> Path:
    override = os.environ.get("MPARANZA_CHANGE_REQUEST_DATA")
    if override:
        return (Path(override).expanduser() / plugin_name).resolve()
    claude_plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if claude_plugin_data:
        return (Path(claude_plugin_data).expanduser() / "change-requests").resolve()
    return (
        Path.home() / ".codex" / "mparanza" / "change-requests" / plugin_name
    ).resolve()


def _temporary_state_dir(plugin_name: str) -> Path:
    """Return a deterministic private fallback for read-only home directories."""

    get_uid = getattr(os, "getuid", None)
    user_identity = (
        str(get_uid())
        if callable(get_uid)
        else hashlib.sha256(str(Path.home()).encode("utf-8")).hexdigest()[:16]
    )
    stable_identity = str(_stable_state_dir(plugin_name).absolute())
    state_key = hashlib.sha256(
        f"{user_identity}:{stable_identity}".encode("utf-8")
    ).hexdigest()[:20]
    return (
        Path(tempfile.gettempdir())
        / f"mparanza-change-requests-{state_key}"
        / plugin_name
    )


def _state_directories(plugin_name: str, plugin_data: Path | None) -> list[Path]:
    directories = [_stable_state_dir(plugin_name)]
    if plugin_data is not None:
        explicit = (plugin_data.expanduser() / "change-requests").resolve()
        if explicit not in directories:
            directories.append(explicit)
    temporary = _temporary_state_dir(plugin_name)
    if temporary not in directories:
        directories.append(temporary)
    return directories


def _prepare_private_temporary_directory(state_dir: Path) -> None:
    """Create or validate a private, user-owned temporary state directory."""

    get_uid = getattr(os, "getuid", None)
    expected_uid = get_uid() if callable(get_uid) else None
    for directory in (state_dir.parent, state_dir):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        details = directory.lstat()
        if not stat.S_ISDIR(details.st_mode):
            raise OSError(f"Unsafe temporary state path: {directory}")
        if expected_uid is not None and details.st_uid != expected_uid:
            raise PermissionError(
                f"Temporary state path has the wrong owner: {directory}"
            )
        directory.chmod(0o700)
        if stat.S_IMODE(directory.lstat().st_mode) != 0o700:
            raise PermissionError(f"Temporary state path is not private: {directory}")


def _open_state_lock(state_dir: Path) -> tuple[Any, Any]:
    """Open and acquire one state lock without following a lock-file symlink."""

    lock_path = state_dir / ".state.lock"
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise OSError(f"Unsafe state lock path: {lock_path}")
        get_uid = getattr(os, "getuid", None)
        if callable(get_uid) and details.st_uid != get_uid():
            raise PermissionError(f"State lock has the wrong owner: {lock_path}")
        fchmod = getattr(os, "fchmod", None)
        if callable(fchmod):
            fchmod(descriptor, 0o600)
        else:
            lock_path.chmod(0o600)
        lock_file = os.fdopen(descriptor, "r+b")
        descriptor = -1
        try:
            if sys.platform == "win32":
                lock_module = importlib.import_module("msvcrt")
                lock_file.seek(0)
                if not lock_file.read(1):
                    lock_file.write(b"\0")
                    lock_file.flush()
                lock_file.seek(0)
                lock_module.locking(lock_file.fileno(), lock_module.LK_LOCK, 1)
            else:
                lock_module = importlib.import_module("fcntl")
                lock_module.flock(lock_file.fileno(), lock_module.LOCK_EX)
        except OSError as exc:
            lock_file.close()
            raise _StateLockContentionError(
                f"Change-request state lock is busy: {lock_path}"
            ) from exc
        return lock_file, lock_module
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _state_paths(state_directories: list[Path]) -> list[Path]:
    return [directory / STATE_FILE_NAME for directory in state_directories]


def _release_state_lock(lock: tuple[Any, Any]) -> None:
    lock_file, lock_module = lock
    try:
        if sys.platform == "win32":
            lock_file.seek(0)
            lock_module.locking(lock_file.fileno(), lock_module.LK_UNLCK, 1)
        else:
            lock_module.flock(lock_file.fileno(), lock_module.LOCK_UN)
    finally:
        lock_file.close()


@contextmanager
def _locked_state(plugin_name: str, plugin_data: Path | None) -> Iterator[list[Path]]:
    """Serialize mutations while preserving every readable state replica."""

    temporary_state_dir = _temporary_state_dir(plugin_name)
    state_directories: list[Path] = []
    lock_candidates: list[Path] = []
    errors: list[OSError] = []
    for state_dir in _state_directories(plugin_name, plugin_data):
        is_temporary = state_dir == temporary_state_dir
        if not is_temporary:
            state_directories.append(state_dir)
        try:
            if is_temporary:
                _prepare_private_temporary_directory(state_dir)
            else:
                state_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            errors.append(exc)
            continue
        lock_candidates.append(state_dir)

    locks: list[tuple[Any, Any]] = []
    for state_dir in sorted(lock_candidates, key=str):
        try:
            lock = _open_state_lock(state_dir)
        except _StateLockContentionError as exc:
            for acquired_lock in reversed(locks):
                _release_state_lock(acquired_lock)
            raise ChangeRequestError(
                "Change-request state is busy; retry the operation."
            ) from exc
        except OSError as exc:
            errors.append(exc)
            continue
        locks.append(lock)
        if state_dir == temporary_state_dir:
            state_directories.append(state_dir)
    if not locks:
        raise _StateUnavailableError(
            "Could not access a writable change-request state directory."
        ) from (errors[0] if errors else None)
    try:
        yield state_directories
    finally:
        for lock in reversed(locks):
            _release_state_lock(lock)


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


def _entry_has_receipt(entry: Mapping[str, Any]) -> bool:
    request_id = entry.get("change_request_id")
    token = entry.get("status_token")
    return (
        isinstance(request_id, str)
        and _CHANGE_REQUEST_ID.fullmatch(request_id) is not None
        and isinstance(token, str)
        and bool(token)
        and entry.get("status") in {"open", "fixed"}
    )


def _merge_entry(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_has_receipt = _entry_has_receipt(left)
    right_has_receipt = _entry_has_receipt(right)
    left_updated = float(left.get("updated_at", 0) or 0)
    right_updated = float(right.get("updated_at", 0) or 0)
    if left_has_receipt != right_has_receipt:
        older, newer = (right, left) if left_has_receipt else (left, right)
    else:
        older, newer = (left, right) if left_updated <= right_updated else (right, left)
    merged = dict(older)
    merged.update(newer)
    if left_has_receipt or right_has_receipt:
        merged.pop("pending_payload", None)
    notified = [
        value
        for value in (left.get("fixed_notified_at"), right.get("fixed_notified_at"))
        if isinstance(value, (int, float))
    ]
    if notified:
        merged["fixed_notified_at"] = max(float(value) for value in notified)
    return merged


def _load_state(
    plugin_name: str,
    state_directories: list[Path],
) -> dict[str, Any]:
    entries: dict[str, dict[str, Any]] = {}
    prompt_reservations: list[float] = []
    for path in _state_paths(state_directories):
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
    state: dict[str, Any],
    state_directories: list[Path],
) -> None:
    errors: list[OSError] = []
    written = 0
    for path in _state_paths(state_directories):
        try:
            _write_one_state(path, state)
        except OSError as exc:
            errors.append(exc)
        else:
            written += 1
    if written == 0:
        raise _StateUnavailableError("Could not persist change-request state.") from (
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


def _parse_aware_timestamp(value: Any, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ChangeRequestError(f"{field} must be an ISO timestamp with timezone.")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ChangeRequestError(
            f"{field} must be an ISO timestamp with timezone."
        ) from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ChangeRequestError(f"{field} must include a timezone.")


def _validate_string_list(
    value: Any,
    *,
    field: str,
    max_items: int,
    max_chars: int,
) -> None:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > max_items
        or any(
            not isinstance(item, str) or not item.strip() or len(item) > max_chars
            for item in value
        )
    ):
        raise ChangeRequestError(f"{field} must contain bounded non-empty strings.")


def _validate_problem_request(payload: Mapping[str, Any]) -> None:
    """Validate mechanical evidence shape; Claude retains semantic judgment."""

    allowed = {
        "schema_version",
        "title",
        "expected",
        "observed",
        "reproduction",
        "diagnostics",
        "error",
        "plugin_version",
    }
    if payload.get("schema_version") != 2 or set(payload) - allowed:
        raise ChangeRequestError(
            "Problem report must use the supported schema_version 2."
        )
    for field, max_chars in (
        ("title", 256),
        ("expected", 4_000),
        ("observed", 4_000),
    ):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > max_chars:
            raise ChangeRequestError(f"Problem report {field} is missing or too long.")
    _validate_string_list(
        payload.get("reproduction"),
        field="Problem report reproduction",
        max_items=20,
        max_chars=1_000,
    )
    diagnostics = payload.get("diagnostics")
    if not isinstance(diagnostics, dict):
        raise ChangeRequestError("Problem report diagnostics are required.")
    diagnostic_allowed = {
        "occurred_at",
        "runtime",
        "operation",
        "evidence",
        "correlation_ids",
    }
    if set(diagnostics) - diagnostic_allowed:
        raise ChangeRequestError("Problem report diagnostics contain unknown fields.")
    _parse_aware_timestamp(
        diagnostics.get("occurred_at"), field="diagnostics.occurred_at"
    )
    for field, max_chars in (("runtime", 256), ("operation", 512)):
        value = diagnostics.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > max_chars:
            raise ChangeRequestError(f"diagnostics.{field} is missing or too long.")
    _validate_string_list(
        diagnostics.get("evidence"),
        field="diagnostics.evidence",
        max_items=20,
        max_chars=2_000,
    )
    correlation_ids = diagnostics.get("correlation_ids", [])
    if correlation_ids:
        _validate_string_list(
            correlation_ids,
            field="diagnostics.correlation_ids",
            max_items=20,
            max_chars=256,
        )


def _validate_follow_up_evidence(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != 1 or set(payload) != {
        "schema_version",
        "summary",
        "evidence",
    }:
        raise ChangeRequestError("Follow-up evidence must use the supported schema.")
    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 4_000:
        raise ChangeRequestError("Follow-up evidence summary is missing or too long.")
    _validate_string_list(
        payload.get("evidence"),
        field="Follow-up evidence",
        max_items=20,
        max_chars=2_000,
    )


def _client_context(checked_at: float) -> dict[str, str]:
    """Return bounded non-identifying client diagnostics for support correlation."""

    return {
        "submitted_at": datetime.fromtimestamp(checked_at, tz=timezone.utc).isoformat(),
        "platform": (platform.system() or "unknown").lower()[:64],
        "python_version": platform.python_version()[:64],
        "client": "plugin_change_request",
    }


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


def _is_noncritical_ca_verification_error(exc: BaseException) -> bool:
    """Return whether a URL failure wraps OpenSSL verification error 89."""

    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    return (
        isinstance(reason, ssl.SSLCertVerificationError)
        and getattr(reason, "verify_code", None) == _CA_BCONS_NOT_CRITICAL_VERIFY_CODE
    )


def _is_mparanza_https_request(request: urllib.request.Request) -> bool:
    """Return whether a request targets the fixed remote feedback hosts."""

    parts = urllib.parse.urlsplit(request.full_url)
    host = (parts.hostname or "").lower()
    return (
        parts.scheme == "https"
        and host in ALLOWED_REMOTE_HOSTS
        and parts.port in {None, 443}
    )


def _urlopen_with_noncritical_ca_compatibility(
    request: urllib.request.Request, *, timeout_seconds: float
) -> Any:
    """Open Mparanza HTTPS with pre-Python-3.13 X.509 strictness."""

    if not _is_mparanza_https_request(request):
        raise ValueError("CA compatibility is available only for Mparanza HTTPS.")
    context = ssl.create_default_context()
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return urllib.request.urlopen(  # nosec B310
        request,
        timeout=timeout_seconds,
        context=context,
    )


def _post_json(
    base_url: str,
    path: str,
    payload: Mapping[str, Any],
    *,
    opener: Callable[..., Any] | None,
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
        active_opener = urllib.request.urlopen if opener is None else opener
        try:
            with active_opener(request, timeout=timeout_seconds) as response:
                return _response_json(response)
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            if (
                opener is None
                and _is_mparanza_https_request(request)
                and _is_noncritical_ca_verification_error(exc)
            ):
                with _urlopen_with_noncritical_ca_compatibility(
                    request, timeout_seconds=timeout_seconds
                ) as response:
                    return _response_json(response)
            raise
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
    disposition = payload.get("disposition")
    if disposition is None:
        disposition = "fixed" if status == "fixed" else "unresolved"
    if disposition not in {
        "unresolved",
        "needs_info",
        "fixed",
        "duplicate",
        "external",
        "non_actionable",
    } or (status == "fixed") != (disposition == "fixed"):
        raise ChangeRequestError("The response contains an invalid disposition.")
    revision = payload.get("revision", 1)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ChangeRequestError("The response contains an invalid status revision.")
    needs_info_question = payload.get("needs_info_question")
    if disposition == "needs_info":
        if not isinstance(needs_info_question, str) or not needs_info_question.strip():
            raise ChangeRequestError("The response is missing its evidence question.")
    elif needs_info_question is not None:
        raise ChangeRequestError(
            "The response contains an unexpected evidence question."
        )
    fixed_version = payload.get("fixed_version")
    if fixed_version is not None and not isinstance(fixed_version, str):
        raise ChangeRequestError("The response contains an invalid fixed version.")
    return {
        "change_request_id": request_id,
        "status_token": token,
        "status": status,
        "disposition": disposition,
        "revision": revision,
        "needs_info_question": needs_info_question,
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
        "disposition": "unresolved",
        "revision": 1,
        "needs_info_question": None,
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
    fingerprint_payload = dict(request_without_id)
    fingerprint_payload.pop("client_context", None)
    fingerprint = _payload_hash(fingerprint_payload)
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
    with _locked_state(plugin_name, plugin_data) as state_directories:
        state = _load_state(plugin_name, state_directories)
        entry, _created = _find_or_create_entry(
            state,
            kind=kind,
            plugin_name=plugin_name,
            plugin_version=plugin_version,
            request_without_id=request_without_id,
            now=now,
        )
        _write_state(state, state_directories)
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
            "disposition",
            "revision",
            "needs_info_question",
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
    reserved_entry: Mapping[str, Any] | None,
    now: float,
) -> dict[str, Any]:
    with _locked_state(plugin_name, plugin_data) as state_directories:
        state = _load_state(plugin_name, state_directories)
        entry = next(
            (
                candidate
                for candidate in state["requests"]
                if candidate.get("submission_id") == submission_id
            ),
            None,
        )
        if entry is None:
            if (
                reserved_entry is None
                or reserved_entry.get("submission_id") != submission_id
            ):
                raise ChangeRequestError("The reserved change request is missing.")
            entry = dict(reserved_entry)
            state["requests"].append(entry)
        existing = _stored_receipt(entry)
        if existing is not None:
            return existing
        stored = _save_receipt(entry, receipt, now=now)
        _write_state(state, state_directories)
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
    try:
        with _locked_state(plugin_name, plugin_data) as state_directories:
            state = _load_state(plugin_name, state_directories)
            reserved_at = state.get(PROMPT_RESERVED_AT_FIELD)
            ask = (
                reserved_at is None
                or checked_at - float(reserved_at) >= PROMPT_COOLDOWN_SECONDS
            )
            if ask:
                reserved_at = checked_at
                state[PROMPT_RESERVED_AT_FIELD] = checked_at
            # These paths are replicas: one durable write preserves the cooldown,
            # and the next successful cycle repairs a temporarily failed replica.
            _write_state(state, state_directories)
    except _StateUnavailableError:
        return {
            "ask": False,
            "cooldown_seconds": PROMPT_COOLDOWN_SECONDS,
            "reason": "state_unavailable",
        }
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
    opener: Callable[..., Any] | None = None,
    now: float | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Submit one approved text request and return its durable receipt."""

    plugin_name, plugin_version = _read_plugin_identity(plugin_root)
    request_payload = _read_request_file(request_path)
    if kind == "problem":
        _validate_problem_request(request_payload)
    checked_at = time.time() if now is None else now
    body_without_id = {
        "schema_version": 1,
        "kind": kind,
        "plugin": plugin_name,
        "plugin_version": plugin_version,
        "request": request_payload,
        "client_context": _client_context(checked_at),
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
        reserved_entry=entry,
        now=checked_at,
    )


def submit_problem(
    plugin_root: Path,
    request_path: Path,
    *,
    plugin_data: Path | None = None,
    base_url: str = DEFAULT_BASE_URL,
    opener: Callable[..., Any] | None = None,
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
    opener: Callable[..., Any] | None = None,
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


def submit_evidence(
    plugin_root: Path,
    change_request_id: str,
    evidence_path: Path,
    *,
    plugin_data: Path | None = None,
    base_url: str = DEFAULT_BASE_URL,
    opener: Callable[..., Any] | None = None,
    now: float | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Submit one requested sanitized evidence update with idempotent retry."""

    if _CHANGE_REQUEST_ID.fullmatch(change_request_id) is None:
        raise ChangeRequestError("Invalid change-request ID.")
    plugin_name, _plugin_version = _read_plugin_identity(plugin_root)
    evidence = _read_request_file(evidence_path)
    _validate_follow_up_evidence(evidence)
    checked_at = time.time() if now is None else now
    evidence_hash = _payload_hash(evidence)
    with _locked_state(plugin_name, plugin_data) as state_directories:
        state = _load_state(plugin_name, state_directories)
        entry = next(
            (
                candidate
                for candidate in state["requests"]
                if candidate.get("change_request_id") == change_request_id
            ),
            None,
        )
        if entry is None or not isinstance(entry.get("status_token"), str):
            raise ChangeRequestError("No local receipt exists for this change request.")
        completed_updates = entry.get("evidence_updates", [])
        if isinstance(completed_updates, list) and any(
            isinstance(update, dict) and update.get("payload_hash") == evidence_hash
            for update in completed_updates
        ):
            stored = _stored_receipt(entry)
            if stored is None:
                raise ChangeRequestError("The local change-request receipt is invalid.")
            return stored
        pending = entry.get("pending_evidence")
        if isinstance(pending, dict) and pending.get("payload_hash") == evidence_hash:
            update_id = str(pending["update_id"])
        else:
            update_id = str(uuid.uuid4())
            entry["pending_evidence"] = {
                "update_id": update_id,
                "payload_hash": evidence_hash,
            }
            entry["updated_at"] = checked_at
            _write_state(state, state_directories)
        status_token = str(entry["status_token"])
    response = _post_json(
        base_url,
        f"/api/change-requests/{change_request_id}/evidence",
        {
            "schema_version": 1,
            "update_id": update_id,
            "status_token": status_token,
            "evidence": evidence,
        },
        opener=opener,
        timeout_seconds=timeout_seconds,
    )
    receipt = _validate_receipt(response)
    with _locked_state(plugin_name, plugin_data) as state_directories:
        state = _load_state(plugin_name, state_directories)
        entry = next(
            (
                candidate
                for candidate in state["requests"]
                if candidate.get("change_request_id") == change_request_id
            ),
            None,
        )
        if entry is None:
            raise ChangeRequestError("The local change-request receipt is missing.")
        entry.update(receipt)
        entry.pop("pending_evidence", None)
        completed_updates = entry.get("evidence_updates", [])
        if not isinstance(completed_updates, list):
            completed_updates = []
        completed_updates.append(
            {
                "update_id": update_id,
                "payload_hash": evidence_hash,
                "submitted_at": checked_at,
            }
        )
        entry["evidence_updates"] = completed_updates
        entry["updated_at"] = checked_at
        _write_state(state, state_directories)
    return receipt


def start_interview(
    plugin_root: Path,
    opportunity: str,
    *,
    language: str = "it",
    plugin_data: Path | None = None,
    base_url: str = DEFAULT_BASE_URL,
    opener: Callable[..., Any] | None = None,
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
            reserved_entry=entry,
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
        disposition = row.get("disposition")
        if disposition is None:
            disposition = "fixed" if status == "fixed" else "unresolved"
        if disposition not in {
            "unresolved",
            "needs_info",
            "fixed",
            "duplicate",
            "external",
            "non_actionable",
        } or (status == "fixed") != (disposition == "fixed"):
            raise ChangeRequestError(
                "The status response contains an invalid disposition."
            )
        revision = row.get("revision", 1)
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ChangeRequestError(
                "The status response contains an invalid status revision."
            )
        needs_info_question = row.get("needs_info_question")
        if disposition == "needs_info":
            if (
                not isinstance(needs_info_question, str)
                or not needs_info_question.strip()
            ):
                raise ChangeRequestError(
                    "The status response is missing its evidence question."
                )
        elif needs_info_question is not None:
            raise ChangeRequestError(
                "The status response contains an unexpected evidence question."
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
                "disposition": disposition,
                "revision": revision,
                "needs_info_question": needs_info_question,
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
    opener: Callable[..., Any] | None = None,
    now: float | None = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> str | None:
    """Return one-time messages for submitted requests that are now fixed."""

    try:
        plugin_name, _plugin_version = _read_plugin_identity(plugin_root)
        with _locked_state(plugin_name, plugin_data) as state_directories:
            state = _load_state(plugin_name, state_directories)
            pending = [
                dict(entry)
                for entry in state["requests"]
                if isinstance(entry.get("change_request_id"), str)
                and isinstance(entry.get("status_token"), str)
            ]
            if not pending:
                _write_state(state, state_directories)
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
        notifications: list[str] = []
        with _locked_state(plugin_name, plugin_data) as state_directories:
            state = _load_state(plugin_name, state_directories)
            for entry in state["requests"]:
                request_id = entry.get("change_request_id")
                row = updates_by_id.get(str(request_id))
                if row is None:
                    continue
                notified_revision = entry.get("notified_revision", 0)
                if isinstance(notified_revision, bool) or not isinstance(
                    notified_revision, (int, float)
                ):
                    notified_revision = 0
                entry.update(
                    {key: value for key, value in row.items() if key != "found"}
                )
                entry["updated_at"] = checked_at
                revision = int(entry.get("revision", 1))
                if revision <= int(notified_revision):
                    continue
                disposition = entry.get("disposition")
                if entry.get("status") == "fixed":
                    fixed_version = entry.get("fixed_version")
                    if not isinstance(fixed_version, str) or not fixed_version:
                        continue
                    entry["fixed_notified_at"] = checked_at
                    notifications.append(
                        f"The problem you reported as {entry['change_request_id']} "
                        f"is fixed in {plugin_name.title()} {fixed_version}. "
                        "Update to the published version and try again. If the "
                        "problem continues, report it again and reference "
                        f"{entry['change_request_id']}."
                    )
                elif disposition == "needs_info":
                    question = entry.get("needs_info_question")
                    if isinstance(question, str):
                        entry["needs_info_notified_question"] = question
                        notifications.append(
                            f"The developer needs more evidence for "
                            f"{entry['change_request_id']}: {question}"
                        )
                elif disposition in {"duplicate", "external", "non_actionable"}:
                    label = str(disposition).replace("_", " ")
                    notifications.append(
                        f"The report {entry['change_request_id']} was closed as "
                        f"{label}; no plugin fix was claimed."
                    )
                elif int(notified_revision) > 0:
                    notifications.append(
                        f"The report {entry['change_request_id']} was reopened and "
                        "is under active investigation."
                    )
                entry["notified_revision"] = revision
            _write_state(state, state_directories)
    except (ChangeRequestError, OSError, TypeError, ValueError):
        return None
    if not notifications:
        return None
    return "\n".join(notifications)


def _plugin_data_from_env() -> Path | None:
    value = os.environ.get("CLAUDE_PLUGIN_DATA") or os.environ.get("PLUGIN_DATA")
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
    evidence_parser = subparsers.add_parser("add-evidence")
    evidence_parser.add_argument("--change-request", required=True)
    evidence_parser.add_argument("--request", type=Path, required=True)
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
        elif args.command == "add-evidence":
            receipt = submit_evidence(
                args.plugin_root,
                args.change_request,
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
