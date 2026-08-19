"""Bounded Google Drive access for Studio Archive and archive organization."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from urllib.parse import quote

__all__ = [
    "DRIVE_FOLDER_MIME_TYPE",
    "DRIVE_SHORTCUT_MIME_TYPE",
    "DRIVE_SNAPSHOT_SCHEMA",
    "MAX_EVIDENCE_BYTES",
    "DriveError",
    "DriveGateway",
    "GoogleApiDriveGateway",
    "authorize_google_drive",
    "load_google_drive_gateway",
    "normalize_file_metadata",
    "snapshot_google_drive_folder",
]

DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
DRIVE_SHORTCUT_MIME_TYPE = "application/vnd.google-apps.shortcut"
DRIVE_SNAPSHOT_SCHEMA = "vera.google_drive_folder_snapshot.v1"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
MAX_FILES = 5_000
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_EVIDENCE_BYTES = 100 * 1024 * 1024
_ID_RE = re.compile(r"[A-Za-z0-9_-]{3,256}")
_CHECKSUM_RE = re.compile(r"[0-9a-f]+")
_FILE_FIELDS = (
    "id,name,mimeType,parents,driveId,size,modifiedTime,version,"
    "md5Checksum,sha256Checksum,trashed,"
    "capabilities(canEdit,canDownload,canMoveItemWithinDrive),"
    "shortcutDetails(targetId,targetMimeType)"
)


class DriveError(RuntimeError):
    """Raised when a bounded Drive operation cannot be completed safely."""


class DriveGateway(Protocol):
    """Small testable boundary around the Google Drive v3 API."""

    def get_file(self, file_id: str) -> dict[str, Any]:
        """Return the exact metadata fields used by the safety kernel."""

    def list_children(self, parent_id: str) -> list[dict[str, Any]]:
        """Return every non-trashed direct child of one folder."""

    def create_folder(self, parent_id: str, name: str) -> dict[str, Any]:
        """Create one folder below an already validated parent."""

    def move_file(
        self,
        file_id: str,
        *,
        old_parent_id: str,
        new_parent_id: str,
        new_name: str,
    ) -> dict[str, Any]:
        """Move and rename one file through a single Drive metadata update."""

    def download_bytes(self, file_id: str) -> bytes:
        """Download one bounded binary Drive file."""

    def export_bytes(self, file_id: str, mime_type: str) -> bytes:
        """Export one bounded Google-native document."""


def _drive_id(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value.strip()) is None:
        raise DriveError(f"{label} is not a valid Google Drive ID.")
    return value.strip()


def _text(value: object, *, label: str, maximum: int = 1_000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise DriveError(f"{label} is invalid.")
    return value.strip()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _path_component(name: str, file_id: str, duplicate: bool) -> str:
    encoded = quote(name, safe=" !#$&'()+,-.;=@[]^_`{}~")
    encoded = encoded or "unnamed"
    return f"{encoded}~{file_id[:12]}" if duplicate else encoded


def _optional_checksum(value: object, *, length: int) -> str | None:
    if value in {None, ""}:
        return None
    if (
        not isinstance(value, str)
        or len(value) != length
        or _CHECKSUM_RE.fullmatch(value) is None
    ):
        raise DriveError("Google Drive returned an invalid content checksum.")
    return value


def normalize_file_metadata(item: Mapping[str, Any], parent_id: str) -> dict[str, Any]:
    file_id = _drive_id(item.get("id"), label="Drive file ID")
    parents = item.get("parents")
    if not isinstance(parents, list) or parents != [parent_id]:
        raise DriveError("A Drive item does not have the expected single parent.")
    mime_type = _text(item.get("mimeType"), label="Drive MIME type", maximum=255)
    size_value = item.get("size")
    if size_value in {None, ""}:
        size_bytes: int | None = None
    else:
        try:
            size_bytes = int(size_value)
        except (TypeError, ValueError) as exc:
            raise DriveError("Google Drive returned an invalid file size.") from exc
        if size_bytes < 0:
            raise DriveError("Google Drive returned an invalid file size.")
    version = _text(item.get("version"), label="Drive version", maximum=40)
    if not version.isdigit():
        raise DriveError("Google Drive returned an invalid file version.")
    capabilities = item.get("capabilities") or {}
    if not isinstance(capabilities, Mapping):
        raise DriveError("Google Drive returned invalid capabilities.")
    drive_id = item.get("driveId")
    if drive_id is not None:
        drive_id = _drive_id(drive_id, label="Shared Drive ID")
    return {
        "file_id": file_id,
        "parent_id": parent_id,
        "name": _text(item.get("name"), label="Drive file name", maximum=768),
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "modified_time": _text(
            item.get("modifiedTime"), label="Drive modified time", maximum=80
        ),
        "version": version,
        "md5_checksum": _optional_checksum(item.get("md5Checksum"), length=32),
        "sha256_checksum": _optional_checksum(item.get("sha256Checksum"), length=64),
        "drive_id": drive_id,
        "capabilities": {
            "can_edit": capabilities.get("canEdit") is True,
            "can_download": capabilities.get("canDownload") is True,
            "can_move_within_drive": (
                capabilities.get("canMoveItemWithinDrive") is True
            ),
        },
    }


class GoogleApiDriveGateway:
    """Google API client implementation of the narrow Drive gateway."""

    def __init__(self, service: Any) -> None:
        self._service = service

    @staticmethod
    def _execute(request: Any, *, label: str) -> dict[str, Any]:
        try:
            from googleapiclient.errors import HttpError
        except ModuleNotFoundError as exc:
            raise DriveError("The Google Drive API client is unavailable.") from exc
        try:
            result = request.execute()
        except (HttpError, OSError, RuntimeError, ValueError) as exc:
            raise DriveError(f"{label}: {exc}") from exc
        if not isinstance(result, dict):
            raise DriveError(f"{label}: Google Drive returned malformed metadata.")
        return result

    def get_file(self, file_id: str) -> dict[str, Any]:
        request = self._service.files().get(
            fileId=_drive_id(file_id, label="Drive file ID"),
            fields=_FILE_FIELDS,
            supportsAllDrives=True,
        )
        return self._execute(request, label="Could not read Google Drive metadata")

    def list_children(self, parent_id: str) -> list[dict[str, Any]]:
        selected = _drive_id(parent_id, label="Drive parent ID")
        page_token: str | None = None
        children: list[dict[str, Any]] = []
        while True:
            request = self._service.files().list(
                q=f"'{selected}' in parents and trashed = false",
                spaces="drive",
                pageSize=1_000,
                pageToken=page_token,
                fields=f"nextPageToken,incompleteSearch,files({_FILE_FIELDS})",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            response = self._execute(
                request, label="Could not list Google Drive folder"
            )
            if response.get("incompleteSearch") is True:
                raise DriveError("Google Drive folder search was incomplete.")
            page = response.get("files", [])
            if not isinstance(page, list) or not all(
                isinstance(item, dict) for item in page
            ):
                raise DriveError("Google Drive returned a malformed child list.")
            children.extend(page)
            page_token = response.get("nextPageToken")
            if page_token is None:
                return children
            if not isinstance(page_token, str) or not page_token:
                raise DriveError("Google Drive returned an invalid page token.")

    def create_folder(self, parent_id: str, name: str) -> dict[str, Any]:
        body = {
            "name": _text(name, label="Drive folder name", maximum=255),
            "mimeType": DRIVE_FOLDER_MIME_TYPE,
            "parents": [_drive_id(parent_id, label="Drive parent ID")],
        }
        request = self._service.files().create(
            body=body, fields=_FILE_FIELDS, supportsAllDrives=True
        )
        return self._execute(request, label="Could not create Google Drive folder")

    def move_file(
        self,
        file_id: str,
        *,
        old_parent_id: str,
        new_parent_id: str,
        new_name: str,
    ) -> dict[str, Any]:
        request = self._service.files().update(
            fileId=_drive_id(file_id, label="Drive file ID"),
            addParents=_drive_id(new_parent_id, label="new Drive parent ID"),
            removeParents=_drive_id(old_parent_id, label="old Drive parent ID"),
            body={"name": _text(new_name, label="Drive file name", maximum=768)},
            fields=_FILE_FIELDS,
            supportsAllDrives=True,
        )
        return self._execute(request, label="Could not move Google Drive file")

    @staticmethod
    def _download(request: Any) -> bytes:
        try:
            from googleapiclient.errors import HttpError
            from googleapiclient.http import MediaIoBaseDownload
        except ModuleNotFoundError as exc:
            raise DriveError("The Google Drive API client is unavailable.") from exc
        target = io.BytesIO()
        downloader = MediaIoBaseDownload(target, request)
        done = False
        try:
            while not done:
                _, done = downloader.next_chunk()
                if target.tell() > MAX_EVIDENCE_BYTES:
                    raise DriveError(
                        "Google Drive evidence exceeds the 100 MB read boundary."
                    )
        except DriveError:
            raise
        except (HttpError, OSError, RuntimeError, ValueError) as exc:
            raise DriveError(f"Could not read Google Drive content: {exc}") from exc
        return target.getvalue()

    def download_bytes(self, file_id: str) -> bytes:
        request = self._service.files().get_media(
            fileId=_drive_id(file_id, label="Drive file ID"),
            supportsAllDrives=True,
        )
        return self._download(request)

    def export_bytes(self, file_id: str, mime_type: str) -> bytes:
        request = self._service.files().export_media(
            fileId=_drive_id(file_id, label="Drive file ID"),
            mimeType=_text(mime_type, label="Drive export MIME type", maximum=255),
        )
        return self._download(request)


def _google_dependencies() -> tuple[Any, Any, Any, Any, Any]:
    try:
        import google.auth
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ModuleNotFoundError as exc:
        raise DriveError(
            "Google Drive dependencies are unavailable; install the declared "
            "Studio Archive requirements."
        ) from exc
    return google.auth, Request, Credentials, InstalledAppFlow, build


def authorize_google_drive(
    client_secrets_path: Path,
    token_path: Path,
) -> GoogleApiDriveGateway:
    """Run an explicit installed-app OAuth flow and store a private refresh token."""

    _, _, _, installed_app_flow, build = _google_dependencies()
    secrets_path = client_secrets_path.expanduser().resolve(strict=True)
    token = token_path.expanduser()
    token.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        flow = installed_app_flow.from_client_secrets_file(
            str(secrets_path), [DRIVE_SCOPE]
        )
        credentials = flow.run_local_server(port=0)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{token.name}.", suffix=".tmp", dir=token.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(credentials.to_json())
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(token)
        finally:
            temporary.unlink(missing_ok=True)
        if os.name == "posix":
            token.chmod(0o600)
        service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise DriveError(f"Google Drive authorization failed: {exc}") from exc
    return GoogleApiDriveGateway(service)


def load_google_drive_gateway(token_path: Path | None = None) -> GoogleApiDriveGateway:
    """Load a stored user token or Application Default Credentials."""

    google_auth, request_type, credentials_type, _, build = _google_dependencies()
    selected_token = token_path.expanduser() if token_path is not None else None
    try:
        if selected_token is not None and selected_token.is_file():
            credentials = credentials_type.from_authorized_user_file(
                str(selected_token), [DRIVE_SCOPE]
            )
        else:
            credentials, _ = google_auth.default(scopes=[DRIVE_SCOPE])
        if not credentials.valid:
            if not credentials.expired or not credentials.refresh_token:
                raise DriveError("Google Drive credentials require authorization.")
            credentials.refresh(request_type())
        service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    except DriveError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise DriveError(f"Google Drive credentials are unavailable: {exc}") from exc
    return GoogleApiDriveGateway(service)


def snapshot_google_drive_folder(
    gateway: DriveGateway,
    root_folder_id: str,
    client_id: str,
    engagement_id: str,
    *,
    max_files: int = MAX_FILES,
    max_total_bytes: int = MAX_TOTAL_BYTES,
) -> dict[str, Any]:
    """Return one immutable recursive metadata snapshot for a Drive client folder."""

    root_id = _drive_id(root_folder_id, label="Drive root folder ID")
    root = gateway.get_file(root_id)
    if root.get("mimeType") != DRIVE_FOLDER_MIME_TYPE or root.get("trashed") is True:
        raise DriveError("Selected Google Drive root is not an active folder.")
    root_name = _text(root.get("name"), label="Drive root folder name", maximum=768)
    drive_id = root.get("driveId")
    if drive_id is not None:
        drive_id = _drive_id(drive_id, label="Shared Drive ID")
    files: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    total_bytes = 0
    folder_count = 1
    visited = {root_id}
    pending: list[tuple[str, PurePosixPath]] = [(root_id, PurePosixPath())]
    while pending:
        parent_id, parent_path = pending.pop()
        children = gateway.list_children(parent_id)
        names = Counter(str(item.get("name") or "") for item in children)
        for raw in sorted(
            children,
            key=lambda item: (
                str(item.get("name") or "").casefold(),
                str(item.get("name") or ""),
                str(item.get("id") or ""),
            ),
        ):
            normalized = normalize_file_metadata(raw, parent_id)
            component = _path_component(
                normalized["name"],
                normalized["file_id"],
                names[normalized["name"]] > 1,
            )
            relative_path = (parent_path / component).as_posix()
            if normalized["mime_type"] == DRIVE_FOLDER_MIME_TYPE:
                if normalized["file_id"] in visited:
                    excluded.append(
                        {"relative_path": relative_path, "reason": "folder_cycle"}
                    )
                    continue
                visited.add(normalized["file_id"])
                folder_count += 1
                pending.append((normalized["file_id"], parent_path / component))
                continue
            if normalized["mime_type"] == DRIVE_SHORTCUT_MIME_TYPE:
                excluded.append(
                    {"relative_path": relative_path, "reason": "drive_shortcut"}
                )
                continue
            if len(files) >= max_files:
                raise DriveError(
                    f"Google Drive folder exceeds the {max_files}-file boundary."
                )
            if normalized["size_bytes"] is not None:
                total_bytes += normalized["size_bytes"]
                if total_bytes > max_total_bytes:
                    raise DriveError(
                        "Google Drive folder exceeds the bounded known-byte total."
                    )
            files.append({"relative_path": relative_path, **normalized})
    files.sort(
        key=lambda item: (item["relative_path"].casefold(), item["relative_path"])
    )
    excluded.sort(
        key=lambda item: (item["relative_path"].casefold(), item["relative_path"])
    )
    content = {
        "schema_version": DRIVE_SNAPSHOT_SCHEMA,
        "client_id": _text(client_id, label="client ID", maximum=80),
        "engagement_id": _text(engagement_id, label="engagement ID", maximum=80),
        "root_folder_id": root_id,
        "root_name": root_name,
        "drive_id": drive_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "folder_count": folder_count,
        "known_total_bytes": total_bytes,
        "files": files,
        "excluded": excluded,
    }
    return {**content, "content_sha256": _canonical_sha256(content)}
