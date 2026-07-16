"""Authenticated installed-plugin client for the Attribute Reporting bridge."""

from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import logging
import os
import re
import shutil
import stat
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

__all__ = [
    "AttributeReportingServerClient",
    "ServerBridgeClientError",
    "authenticate_opener",
    "extract_evidence_pack",
    "main",
    "request_magic_link",
]

DEFAULT_BASE_URL = "https://mparanza.com"
DEFAULT_TIMEOUT_SECONDS = 300.0
ALLOWED_REMOTE_HOSTS = frozenset({"mparanza.com", "www.mparanza.com"})
LOCAL_TEST_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
LOGGER = logging.getLogger(__name__)
MAX_ARCHIVE_MEMBERS = 1_000
MAX_ARCHIVE_FILE_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024


class ServerBridgeClientError(RuntimeError):
    """Raised when the installed plugin cannot complete a bridge operation."""


def _url_origin(url: str) -> tuple[str, str, int | None]:
    parts = urllib.parse.urlsplit(url)
    try:
        port = parts.port
    except ValueError as exc:
        raise ServerBridgeClientError("Invalid server URL port.") from exc
    if port is None:
        port = (
            443 if parts.scheme == "https" else 80 if parts.scheme == "http" else None
        )
    return parts.scheme.casefold(), (parts.hostname or "").casefold(), port


def _normalize_base_url(base_url: str) -> str:
    clean = base_url.strip()
    parts = urllib.parse.urlsplit(clean)
    host = (parts.hostname or "").casefold()
    if not clean or not parts.scheme or not host:
        raise ServerBridgeClientError("Invalid Attribute Reporting base URL.")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ServerBridgeClientError(
            "The base URL cannot contain credentials, query, or fragment."
        )
    if parts.path not in {"", "/"}:
        raise ServerBridgeClientError("The base URL cannot contain a path.")
    try:
        port = parts.port
    except ValueError as exc:
        raise ServerBridgeClientError("Invalid Attribute Reporting URL port.") from exc
    is_local = host in LOCAL_TEST_HOSTS
    if is_local and parts.scheme not in {"http", "https"}:
        raise ServerBridgeClientError("A local test server must use HTTP or HTTPS.")
    if not is_local and (
        parts.scheme != "https"
        or host not in ALLOWED_REMOTE_HOSTS
        or port not in {None, 443}
    ):
        raise ServerBridgeClientError(
            "The remote Attribute Reporting server must be https://mparanza.com."
        )
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")


class _OriginBoundCookieHeader(urllib.request.BaseHandler):
    """Attach a supplied session cookie only to one approved exact origin."""

    handler_order = 400

    def __init__(self, cookie_header: str, base_url: str) -> None:
        self.cookie_header = cookie_header
        self.origin = _url_origin(base_url)

    def _apply(self, request: urllib.request.Request) -> urllib.request.Request:
        request.remove_header("Cookie")
        if _url_origin(request.full_url) == self.origin:
            request.add_unredirected_header("Cookie", self.cookie_header)
        return request

    def http_request(self, request: urllib.request.Request) -> urllib.request.Request:
        return self._apply(request)

    def https_request(self, request: urllib.request.Request) -> urllib.request.Request:
        return self._apply(request)


def _new_opener(
    cookie_jar: http.cookiejar.CookieJar | None = None,
) -> urllib.request.OpenerDirector:
    if cookie_jar is None:
        cookie_jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))


def _load_session_cookie_jar(path: Path) -> http.cookiejar.MozillaCookieJar:
    raw = path.expanduser()
    if raw.is_symlink():
        raise ServerBridgeClientError("Session cookie file cannot be a symlink.")
    session_path = raw.resolve()
    jar = http.cookiejar.MozillaCookieJar(str(session_path))
    if not session_path.exists():
        return jar
    if not session_path.is_file() or stat.S_IMODE(session_path.stat().st_mode) & 0o077:
        raise ServerBridgeClientError(
            "Session cookie file must be a private 0600 regular file."
        )
    try:
        jar.load(ignore_discard=True, ignore_expires=False)
    except (OSError, http.cookiejar.LoadError) as exc:
        raise ServerBridgeClientError(
            f"Cannot load session cookie file: {exc}"
        ) from exc
    return jar


def _save_session_cookie_jar(
    jar: http.cookiejar.MozillaCookieJar,
    path: Path,
) -> None:
    raw = path.expanduser()
    if raw.is_symlink():
        raise ServerBridgeClientError("Session cookie file cannot be a symlink.")
    session_path = raw.resolve()
    session_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    temporary = session_path.with_name(
        f".{session_path.name}.saving-{uuid.uuid4().hex}"
    )
    try:
        jar.save(
            filename=str(temporary),
            ignore_discard=True,
            ignore_expires=True,
        )
        os.chmod(temporary, 0o600)
        temporary.replace(session_path)
    except OSError as exc:
        raise ServerBridgeClientError(
            f"Cannot save session cookie file: {exc}"
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def _has_session_cookie_for_origin(
    jar: http.cookiejar.CookieJar,
    base_url: str,
) -> bool:
    host = _url_origin(_normalize_base_url(base_url))[1]
    return any(
        not cookie.is_expired()
        and (
            host == cookie.domain.lstrip(".").casefold()
            or host.endswith("." + cookie.domain.lstrip(".").casefold())
        )
        for cookie in jar
    )


def _set_cookie_header(
    opener: urllib.request.OpenerDirector,
    cookie_header: str,
    *,
    base_url: str,
) -> None:
    clean = re.sub(r"^\s*cookie\s*:\s*", "", cookie_header, flags=re.IGNORECASE).strip()
    if not clean:
        raise ServerBridgeClientError("Missing Mparanza cookie header.")
    opener.addheaders = [
        (name, value)
        for name, value in opener.addheaders
        if name.casefold() != "cookie"
    ]
    opener.add_handler(_OriginBoundCookieHeader(clean, _normalize_base_url(base_url)))


def _extract_magic_link(value: str) -> str:
    clean = value.strip()
    if not clean:
        raise ServerBridgeClientError("Missing Mparanza magic link.")
    match = re.search(r"https://[^)\s]+/auth/magic/consume\?token=[^)\s]+", clean)
    magic_link = match.group(0) if match else clean
    parts = urllib.parse.urlsplit(magic_link)
    _normalize_base_url(f"{parts.scheme}://{parts.netloc}")
    if parts.path != "/auth/magic/consume" or not parts.query:
        raise ServerBridgeClientError("Invalid Mparanza magic-link URL.")
    return magic_link


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_archive_member(member: zipfile.ZipInfo) -> tuple[str, ...]:
    name = member.filename
    clean = name[:-1] if member.is_dir() and name.endswith("/") else name
    parts = tuple(clean.split("/"))
    mode = (member.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode)
    if (
        not clean
        or len(clean) > 512
        or "\\" in clean
        or "\x00" in clean
        or clean.startswith("/")
        or any(part in {"", ".", ".."} for part in parts)
        or ":" in parts[0]
        or stat.S_ISLNK(mode)
        or (file_type and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)))
    ):
        raise ServerBridgeClientError(
            "Evidence ZIP contains an unsafe member path or file type."
        )
    if member.file_size > MAX_ARCHIVE_FILE_BYTES:
        raise ServerBridgeClientError("Evidence ZIP contains an oversized file.")
    compressed = max(member.compress_size, 1)
    if (
        member.file_size > 1024 * 1024
        and member.file_size > compressed * MAX_COMPRESSION_RATIO
    ):
        raise ServerBridgeClientError(
            "Evidence ZIP contains a suspicious compression ratio."
        )
    return parts


def _absolute_path_without_symlinks(path: Path, *, label: str) -> Path:
    """Return an absolute path after rejecting every existing symlink component."""

    expanded = path.expanduser()
    absolute = expanded if expanded.is_absolute() else Path.cwd() / expanded
    absolute = Path(os.path.abspath(absolute))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ServerBridgeClientError(f"{label} cannot contain symlinks.")
    return absolute.resolve()


def extract_evidence_pack(archive_path: Path, output_dir: Path) -> dict[str, Any]:
    """Safely extract one checksum-verified server package into local storage."""

    archive = _absolute_path_without_symlinks(
        archive_path,
        label="Evidence ZIP path",
    )
    destination = _absolute_path_without_symlinks(
        output_dir,
        label="Evidence extraction destination",
    )
    if not archive.is_file():
        raise ServerBridgeClientError(f"Evidence ZIP is unavailable: {archive}")
    if destination.exists() and (
        not destination.is_dir() or any(destination.iterdir())
    ):
        raise ServerBridgeClientError(
            "Evidence extraction destination must be absent or empty."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.extracting-{uuid.uuid4().hex}"
    )
    extracted: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if not members or len(members) > MAX_ARCHIVE_MEMBERS:
                raise ServerBridgeClientError(
                    "Evidence ZIP has an invalid number of members."
                )
            total_bytes = sum(member.file_size for member in members)
            if total_bytes > MAX_ARCHIVE_TOTAL_BYTES:
                raise ServerBridgeClientError("Evidence ZIP is too large to extract.")
            safe_members: list[tuple[zipfile.ZipInfo, tuple[str, ...]]] = []
            seen_paths: set[str] = set()
            for member in members:
                parts = _safe_archive_member(member)
                collision_key = "/".join(parts).casefold()
                if collision_key in seen_paths:
                    raise ServerBridgeClientError(
                        "Evidence ZIP contains duplicate member paths."
                    )
                seen_paths.add(collision_key)
                safe_members.append((member, parts))

            temporary.mkdir(parents=False, mode=0o700, exist_ok=False)
            os.chmod(temporary, 0o700)
            for member, parts in safe_members:
                target = temporary.joinpath(*parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                written = 0
                with bundle.open(member) as source, target.open("xb") as output:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > member.file_size:
                            raise ServerBridgeClientError(
                                "Evidence ZIP member exceeded its declared size."
                            )
                        digest.update(chunk)
                        output.write(chunk)
                if written != member.file_size:
                    raise ServerBridgeClientError(
                        "Evidence ZIP member did not match its declared size."
                    )
                extracted.append(
                    {
                        "path": "/".join(parts),
                        "sha256": digest.hexdigest(),
                        "size_bytes": written,
                    }
                )
        if destination.exists():
            destination.rmdir()
        temporary.replace(destination)
        os.chmod(destination, 0o700)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ServerBridgeClientError(
            f"Cannot safely extract evidence ZIP: {exc}"
        ) from exc
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {
        "schema_version": "attribute_reporting.local_extraction_receipt.v1",
        "archive_path": str(archive),
        "archive_sha256": _file_sha256(archive),
        "output_dir": str(destination),
        "file_count": len(extracted),
        "total_size_bytes": sum(item["size_bytes"] for item in extracted),
        "files": extracted,
    }


def _error_detail(body: str, fallback: str) -> Any:
    try:
        payload = json.loads(body) if body.strip() else {}
    except json.JSONDecodeError:
        return body[:1_000] or fallback
    if isinstance(payload, Mapping):
        return payload.get("detail") or payload
    return payload


def request_magic_link(
    opener: urllib.request.OpenerDirector,
    *,
    email: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Ask Mparanza to email a one-time authentication link."""

    base = _normalize_base_url(base_url)
    request = urllib.request.Request(
        f"{base}/auth/magic/request",
        data=_json_bytes(
            {
                "email": email.strip(),
                "redirect_path": "/",
            }
        ),
        method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ServerBridgeClientError(
            f"Magic-link request failed ({exc.code}): {_error_detail(body, str(exc))}"
        ) from exc
    except (OSError, urllib.error.URLError) as exc:
        raise ServerBridgeClientError(f"Magic-link request failed: {exc}") from exc


def authenticate_opener(
    opener: urllib.request.OpenerDirector,
    *,
    magic_link: str = "",
    cookie_header: str = "",
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Authenticate with a consumed magic link or an origin-bound cookie header."""

    if cookie_header.strip():
        _set_cookie_header(opener, cookie_header, base_url=base_url)
        return
    if not magic_link.strip():
        raise ServerBridgeClientError(
            "Authentication required: provide a magic-link or cookie-header file."
        )
    request = urllib.request.Request(_extract_magic_link(magic_link), method="GET")
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ServerBridgeClientError(
            f"Magic-link login failed ({exc.code}): {_error_detail(body, str(exc))}"
        ) from exc
    except (OSError, urllib.error.URLError) as exc:
        raise ServerBridgeClientError(f"Magic-link login failed: {exc}") from exc


class AttributeReportingServerClient:
    """Small cookie-authenticated client with a fixed first-party API surface."""

    def __init__(
        self,
        opener: urllib.request.OpenerDirector,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.opener = opener
        self.base_url = _normalize_base_url(base_url)
        self.timeout_seconds = timeout_seconds
        self.api_root = f"{self.base_url}/case-notes/api/attribute-reporting"

    def _request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = _json_bytes(payload)
        request = urllib.request.Request(
            f"{self.api_root}{path}",
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ServerBridgeClientError(
                f"Attribute Reporting request failed ({exc.code}): "
                f"{_error_detail(body, str(exc))}"
            ) from exc
        except (OSError, urllib.error.URLError) as exc:
            raise ServerBridgeClientError(
                f"Attribute Reporting request failed: {exc}"
            ) from exc
        try:
            result = json.loads(body) if body.strip() else {}
        except json.JSONDecodeError as exc:
            raise ServerBridgeClientError(
                "Attribute Reporting response was not valid JSON."
            ) from exc
        if not isinstance(result, dict):
            raise ServerBridgeClientError(
                "Attribute Reporting response was not a JSON object."
            )
        return result

    def taxonomy_snapshot(self, category_key: str) -> dict[str, Any]:
        """Retrieve one central taxonomy snapshot."""

        category = urllib.parse.quote(category_key.strip(), safe="")
        return self._request_json(f"/taxonomies/{category}")

    def create_evidence_pack(
        self,
        *,
        retailer: str,
        category_key: str,
        taxonomy_version: str,
        taxonomy_sha256: str,
        mapping_submission_id: str | None = None,
    ) -> dict[str, Any]:
        """Start a current-database evidence package build."""

        return self._request_json(
            "/evidence-packs",
            method="POST",
            payload={
                "retailer": retailer,
                "category_key": category_key,
                "taxonomy_version": taxonomy_version,
                "taxonomy_sha256": taxonomy_sha256,
                "mapping_submission_id": mapping_submission_id,
            },
        )

    def evidence_status(self, job_id: str) -> dict[str, Any]:
        """Poll one evidence package job."""

        return self._request_json(
            f"/evidence-packs/{urllib.parse.quote(job_id, safe='')}"
        )

    def download_evidence_pack(self, job_id: str, output_path: Path) -> dict[str, Any]:
        """Download and checksum one ready package into the local workspace."""

        request = urllib.request.Request(
            f"{self.api_root}/evidence-packs/"
            f"{urllib.parse.quote(job_id, safe='')}/download",
            method="GET",
            headers={"Accept": "application/zip"},
        )
        output = output_path.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.name}.download-{uuid.uuid4().hex}")
        digest = hashlib.sha256()
        size_bytes = 0
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                if _url_origin(response.geturl()) != _url_origin(self.base_url):
                    raise ServerBridgeClientError(
                        "Evidence download redirected outside the approved server origin."
                    )
                content_type = str(response.headers.get("Content-Type") or "")
                if (
                    content_type.split(";", 1)[0].strip().casefold()
                    != "application/zip"
                ):
                    raise ServerBridgeClientError(
                        "Evidence download did not return an application/zip response."
                    )
                expected_sha256 = str(response.headers.get("X-Content-SHA256") or "")
                declared_length = str(response.headers.get("Content-Length") or "")
                if declared_length:
                    try:
                        if int(declared_length) > MAX_DOWNLOAD_BYTES:
                            raise ServerBridgeClientError(
                                "Evidence download exceeds the local size limit."
                            )
                    except ValueError as exc:
                        raise ServerBridgeClientError(
                            "Evidence download has an invalid Content-Length."
                        ) from exc
                with temporary.open("xb") as handle:
                    os.chmod(temporary, 0o600)
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                        size_bytes += len(chunk)
                        if size_bytes > MAX_DOWNLOAD_BYTES:
                            raise ServerBridgeClientError(
                                "Evidence download exceeds the local size limit."
                            )
                        handle.write(chunk)
        except urllib.error.HTTPError as exc:
            temporary.unlink(missing_ok=True)
            body = exc.read().decode("utf-8", errors="replace")
            raise ServerBridgeClientError(
                f"Evidence download failed ({exc.code}): "
                f"{_error_detail(body, str(exc))}"
            ) from exc
        except ServerBridgeClientError:
            temporary.unlink(missing_ok=True)
            raise
        except (OSError, urllib.error.URLError) as exc:
            temporary.unlink(missing_ok=True)
            raise ServerBridgeClientError(f"Evidence download failed: {exc}") from exc
        actual_sha256 = digest.hexdigest()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            temporary.unlink(missing_ok=True)
            raise ServerBridgeClientError(
                "Evidence download did not include a valid checksum."
            )
        if actual_sha256 != expected_sha256:
            temporary.unlink(missing_ok=True)
            raise ServerBridgeClientError("Evidence download checksum mismatch.")
        temporary.replace(output)
        return {
            "schema_version": "attribute_reporting.local_download_receipt.v1",
            "job_id": job_id,
            "path": str(output),
            "sha256": actual_sha256,
            "size_bytes": size_bytes,
        }

    def create_mapping_workset(
        self,
        *,
        evidence_job_id: str,
        taxonomy_version: str,
        taxonomy_sha256: str,
        mapping_mode: str = "unresolved",
        correction_reason: str | None = None,
    ) -> dict[str, Any]:
        """Create a pinned unresolved or explicit correction workset."""

        return self._request_json(
            "/mapping-worksets",
            method="POST",
            payload={
                "evidence_job_id": evidence_job_id,
                "taxonomy_version": taxonomy_version,
                "taxonomy_sha256": taxonomy_sha256,
                "mapping_mode": mapping_mode,
                "correction_reason": correction_reason,
            },
        )

    def get_mapping_workset(self, workset_id: str) -> dict[str, Any]:
        """Retrieve one immutable mapping workset."""

        return self._request_json(
            f"/mapping-worksets/{urllib.parse.quote(workset_id, safe='')}"
        )

    def submit_mapping_results(
        self,
        *,
        workset_id: str,
        workset_sha256: str,
        idempotency_key: str,
        mapping_tasks: Mapping[str, Any],
        decisions: Mapping[str, Any],
        validated_mappings: Mapping[str, Any],
        mapping_review: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Submit complete Codex decisions using their validation checksum."""

        return self._request_json(
            f"/mapping-worksets/{urllib.parse.quote(workset_id, safe='')}/submissions",
            method="POST",
            payload={
                "workset_sha256": workset_sha256,
                "idempotency_key": idempotency_key,
                "mapping_tasks": mapping_tasks,
                "decisions": decisions,
                "validated_mappings": validated_mappings,
                "mapping_review": mapping_review,
            },
        )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ServerBridgeClientError(f"Cannot read JSON file: {path}") from exc
    if not isinstance(payload, dict):
        raise ServerBridgeClientError(f"Expected a JSON object in {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    output = path.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(output)


def _write_workset_outputs(
    result: Mapping[str, Any],
    *,
    envelope_path: Path,
    tasks_path: Path,
) -> None:
    mapping_tasks = result.get("mapping_tasks")
    if not isinstance(mapping_tasks, dict):
        raise ServerBridgeClientError(
            "Mapping workset response has no mapping_tasks object."
        )
    _write_json(envelope_path, result)
    _write_json(tasks_path, mapping_tasks)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--magic-link-file", type=Path)
    parser.add_argument("--cookie-header-file", type=Path)
    parser.add_argument(
        "--session-file",
        type=Path,
        help=(
            "Private 0600 Mozilla cookie jar used to persist the Mparanza session "
            "between CLI invocations."
        ),
    )
    parser.add_argument(
        "--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    magic = subparsers.add_parser("request-magic-link")
    magic.add_argument("--email", required=True)

    taxonomy = subparsers.add_parser("taxonomy")
    taxonomy.add_argument("category_key")
    taxonomy.add_argument("--output", type=Path, required=True)

    evidence = subparsers.add_parser("create-evidence")
    evidence.add_argument("--retailer", required=True)
    evidence.add_argument("--category", required=True)
    evidence.add_argument("--taxonomy", type=Path, required=True)
    evidence.add_argument("--mapping-submission-id")
    evidence.add_argument("--output", type=Path, required=True)

    poll = subparsers.add_parser("poll-evidence")
    poll.add_argument("job_id")
    poll.add_argument("--output", type=Path, required=True)

    download = subparsers.add_parser("download-evidence")
    download.add_argument("job_id")
    download.add_argument("--output", type=Path, required=True)
    download.add_argument("--receipt", type=Path, required=True)

    extract = subparsers.add_parser("extract-evidence")
    extract.add_argument("--archive", type=Path, required=True)
    extract.add_argument("--output", type=Path, required=True)
    extract.add_argument("--receipt", type=Path, required=True)

    workset = subparsers.add_parser("create-workset")
    workset.add_argument("--evidence-job-id", required=True)
    workset.add_argument("--taxonomy", type=Path, required=True)
    workset.add_argument(
        "--mapping-mode",
        choices=("unresolved", "correction"),
        default="unresolved",
    )
    workset.add_argument(
        "--correction-reason",
        help="Required audit reason when --mapping-mode=correction.",
    )
    workset.add_argument("--output", type=Path, required=True)
    workset.add_argument("--tasks-output", type=Path, required=True)

    get_workset = subparsers.add_parser("get-workset")
    get_workset.add_argument("workset_id")
    get_workset.add_argument("--output", type=Path, required=True)
    get_workset.add_argument("--tasks-output", type=Path, required=True)

    submit = subparsers.add_parser("submit")
    submit.add_argument("--workset", type=Path, required=True)
    submit.add_argument("--mapping-tasks", type=Path, required=True)
    submit.add_argument("--decisions", type=Path, required=True)
    submit.add_argument("--validated", type=Path, required=True)
    submit.add_argument("--mapping-review", type=Path, required=True)
    submit.add_argument("--mapping-review-validation", type=Path, required=True)
    submit.add_argument("--output", type=Path, required=True)
    return parser


def _read_optional_text(path: Path | None) -> str:
    return path.expanduser().read_text(encoding="utf-8").strip() if path else ""


def main() -> int:
    """Run one explicit authenticated bridge operation."""

    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        session_jar = (
            _load_session_cookie_jar(args.session_file)
            if args.session_file is not None
            else http.cookiejar.MozillaCookieJar()
        )
        opener = _new_opener(session_jar)
        if args.command == "request-magic-link":
            request_magic_link(
                opener,
                email=args.email,
                base_url=args.base_url,
                timeout_seconds=args.timeout_seconds,
            )
            LOGGER.info("Requested a Mparanza magic link for %s", args.email)
            return 0
        if args.command == "extract-evidence":
            result = extract_evidence_pack(args.archive, args.output)
            _write_json(args.receipt, result)
            return 0
        magic_link = _read_optional_text(args.magic_link_file)
        cookie_header = _read_optional_text(args.cookie_header_file)
        if (
            magic_link
            or cookie_header
            or not _has_session_cookie_for_origin(session_jar, args.base_url)
        ):
            authenticate_opener(
                opener,
                magic_link=magic_link,
                cookie_header=cookie_header,
                base_url=args.base_url,
                timeout_seconds=args.timeout_seconds,
            )
        if args.session_file is not None and not cookie_header:
            _save_session_cookie_jar(session_jar, args.session_file)
        client = AttributeReportingServerClient(
            opener,
            base_url=args.base_url,
            timeout_seconds=args.timeout_seconds,
        )
        if args.command == "taxonomy":
            result = client.taxonomy_snapshot(args.category_key)
            _write_json(args.output, result)
        elif args.command == "create-evidence":
            taxonomy = _read_json(args.taxonomy)
            result = client.create_evidence_pack(
                retailer=args.retailer,
                category_key=args.category,
                taxonomy_version=str(taxonomy["version"]),
                taxonomy_sha256=str(taxonomy["sha256"]),
                mapping_submission_id=args.mapping_submission_id,
            )
            _write_json(args.output, result)
        elif args.command == "poll-evidence":
            result = client.evidence_status(args.job_id)
            _write_json(args.output, result)
        elif args.command == "download-evidence":
            result = client.download_evidence_pack(args.job_id, args.output)
            _write_json(args.receipt, result)
        elif args.command == "create-workset":
            taxonomy = _read_json(args.taxonomy)
            result = client.create_mapping_workset(
                evidence_job_id=args.evidence_job_id,
                taxonomy_version=str(taxonomy["version"]),
                taxonomy_sha256=str(taxonomy["sha256"]),
                mapping_mode=args.mapping_mode,
                correction_reason=args.correction_reason,
            )
            _write_workset_outputs(
                result,
                envelope_path=args.output,
                tasks_path=args.tasks_output,
            )
        elif args.command == "get-workset":
            result = client.get_mapping_workset(args.workset_id)
            _write_workset_outputs(
                result,
                envelope_path=args.output,
                tasks_path=args.tasks_output,
            )
        else:
            workset = _read_json(args.workset)
            mapping_tasks = _read_json(args.mapping_tasks)
            decisions = _read_json(args.decisions)
            validated = _read_json(args.validated)
            mapping_review = _read_json(args.mapping_review)
            review_validation = _read_json(args.mapping_review_validation)
            if review_validation.get("review_state") not in {
                "approved",
                "approved_with_caveats",
            }:
                raise ServerBridgeClientError(
                    "Independent semantic mapping review does not approve submission."
                )
            operation_id = _canonical_sha256(
                {
                    "validation_sha256": validated["validation_sha256"],
                    "mapping_review_validation_sha256": review_validation[
                        "review_validation_sha256"
                    ],
                }
            )
            result = client.submit_mapping_results(
                workset_id=str(workset["workset_id"]),
                workset_sha256=str(workset["workset_sha256"]),
                idempotency_key=operation_id,
                mapping_tasks=mapping_tasks,
                decisions=decisions,
                validated_mappings=validated,
                mapping_review=mapping_review,
            )
            _write_json(args.output, result)
        if args.session_file is not None and not cookie_header:
            _save_session_cookie_jar(session_jar, args.session_file)
    except (KeyError, OSError, ServerBridgeClientError, ValueError) as exc:
        LOGGER.error("Attribute Reporting bridge operation failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
