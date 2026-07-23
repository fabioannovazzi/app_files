"""Local, scope-bound studio archive indexing and retrieval."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sqlite3
import stat
import sys
import tempfile
import warnings
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterator, Sequence

__all__ = [
    "ArchiveError",
    "ArchiveNotConfiguredError",
    "SourceChangedError",
    "configure_archive",
    "list_studio_client_identities",
    "match_studio_email_client",
    "open_archive_source",
    "plan_gmail_client_search",
    "refresh_archive",
    "search_archive",
    "set_studio_client_identity",
    "studio_archive_status",
]

SCHEMA_VERSION = "2"
CONFIG_SCHEMA_VERSION = 1
CLIENT_IDENTITIES_SCHEMA_VERSION = 1
STATE_ENV = "VERA_STUDIO_ARCHIVE_STATE_DIR"
DEFAULT_STATE_SUBDIR = Path(".mparanza") / "vera-studio-archive"
CONFIG_FILENAME = "config.json"
CLIENT_IDENTITIES_FILENAME = "client-identities.json"
DATABASE_FILENAME = "archive.sqlite3"

TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".xml"}
PDF_SUFFIXES = {".pdf"}
DOCX_SUFFIXES = {".docx"}
XLSX_SUFFIXES = {".xlsx"}
EMAIL_SUFFIXES = {".eml"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
SUPPORTED_SUFFIXES = (
    TEXT_SUFFIXES
    | PDF_SUFFIXES
    | DOCX_SUFFIXES
    | XLSX_SUFFIXES
    | EMAIL_SUFFIXES
    | IMAGE_SUFFIXES
)

MAX_FILES = 50_000
MAX_TOTAL_BYTES = 50 * 1024 * 1024 * 1024
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_TEXT_BYTES = 20 * 1024 * 1024
MAX_EMAIL_BYTES = 30 * 1024 * 1024
MAX_PDF_BYTES = 100 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_PDF_TEXT_CHARS = 20_000_000
MAX_IMAGE_FRAMES = 100
MAX_IMAGE_TOTAL_PIXELS = 20_000_000
MAX_WORKBOOK_SHEETS = 100
MAX_WORKSHEET_ROWS = 20_000
MAX_WORKSHEET_COLUMNS = 512
MAX_OOXML_MEMBER_BYTES = 20 * 1024 * 1024
MAX_OOXML_TOTAL_BYTES = 100 * 1024 * 1024
MAX_OOXML_MEMBERS = 5_000
MAX_OOXML_COMPRESSION_RATIO = 200
MAX_CHUNK_CHARS = 6_000
MAX_CHUNK_LINES = 120
MAX_SEARCH_TOKENS = 24
MAX_OPEN_CHARS = 24_000
MAX_STATUS_SCAN_ISSUES = 200
MAX_STATUS_DOCUMENT_ISSUES = 200
MAX_CLIENT_IDENTITIES = 5_000
MAX_CLIENT_EMAIL_ADDRESSES = 20
MAX_CLIENT_LEGAL_NAMES = 20
MAX_CLIENT_TAX_IDENTIFIERS = 20
MAX_GMAIL_QUERY_IDENTITIES = 10
MAX_GMAIL_TOPIC_CHARS = 200
IGNORED_NAMES = {
    ".DS_Store",
    ".git",
    ".hg",
    ".svn",
    "Thumbs.db",
    "__pycache__",
    "desktop.ini",
}


class ArchiveError(RuntimeError):
    """Base class for bounded archive workflow errors."""

    code = "archive_error"


class ArchiveNotConfiguredError(ArchiveError):
    """Raised when an operation needs a configured archive."""

    code = "archive_not_configured"


class SourceChangedError(ArchiveError):
    """Raised when an indexed source no longer matches its recorded bytes."""

    code = "source_changed_refresh_required"


@dataclass(frozen=True)
class Scope:
    """One mechanically selected archive-relative search boundary."""

    scope_id: str
    relative_dir: str
    display_name: str

    def as_json(self) -> dict[str, str]:
        """Return a JSON-safe scope record."""

        return {
            "scope_id": self.scope_id,
            "relative_dir": self.relative_dir,
            "display_name": self.display_name,
        }


@dataclass(frozen=True)
class ArchiveConfig:
    """One user's local archive configuration."""

    archive_root: Path
    scopes: tuple[Scope, ...]
    configured_at: str

    def as_json(self) -> dict[str, Any]:
        """Return the persisted configuration shape."""

        return {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "archive_root": str(self.archive_root),
            "configured_at": self.configured_at,
            "scopes": [scope.as_json() for scope in self.scopes],
        }


@dataclass(frozen=True)
class ClientIdentity:
    """One private client identity record bound to an exact archive scope."""

    scope_id: str
    email_addresses: tuple[str, ...]
    legal_names: tuple[str, ...]
    tax_identifiers: tuple[str, ...]
    updated_at: str

    def as_json(self) -> dict[str, Any]:
        """Return the persisted private-registry shape."""

        return {
            "scope_id": self.scope_id,
            "email_addresses": list(self.email_addresses),
            "legal_names": list(self.legal_names),
            "tax_identifiers": list(self.tax_identifiers),
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class DiscoveredFile:
    """One regular source file discovered inside a configured scope."""

    scope_id: str
    relative_path: str
    path: Path
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True)
class ScanIssue:
    """One skipped archive entry that may limit search completeness."""

    scope_id: str
    relative_path: str
    reason: str
    size_bytes: int | None

    def as_json(self) -> dict[str, Any]:
        """Return a JSON-safe scan issue."""

        return {
            "scope_id": self.scope_id,
            "relative_path": self.relative_path,
            "reason": self.reason,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class ExtractedChunk:
    """One bounded, citable source fragment."""

    ordinal: int
    locator_kind: str
    locator_value: str
    text: str


@dataclass(frozen=True)
class ExtractionResult:
    """Mechanically extracted chunks and limitations for one source."""

    chunks: tuple[ExtractedChunk, ...]
    extraction_method: str
    status: str
    needs_ocr: bool
    limitations: tuple[str, ...]


class _HtmlTextExtractor(HTMLParser):
    """Collect visible text from an HTML email part."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        """Keep non-empty visible text."""

        if data.strip():
            self.parts.append(data)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ArchiveError("Studio Archive source is not a regular file.")
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(prefix: str, *values: str) -> str:
    payload = "\x1f".join(values).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:24]}"


def _state_dir(
    explicit: Path | None = None,
    *,
    create: bool = False,
) -> Path:
    selected = explicit
    if selected is None:
        environment_value = os.environ.get(STATE_ENV, "").strip()
        selected = (
            Path(environment_value).expanduser()
            if environment_value
            else Path.home() / DEFAULT_STATE_SUBDIR
        )
    selected = Path(selected).expanduser()
    if not selected.is_absolute():
        raise ArchiveError("Studio Archive state directory must be absolute.")
    if selected.is_symlink():
        raise ArchiveError("Studio Archive state directory cannot be a symbolic link.")
    if create:
        selected.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            selected.chmod(0o700)
        except OSError as exc:
            raise ArchiveError(f"Could not secure Studio Archive state: {exc}") from exc
    elif selected.exists() and not selected.is_dir():
        raise ArchiveError("Studio Archive state path must be a directory.")
    elif (
        selected.exists()
        and os.name == "posix"
        and stat.S_IMODE(selected.stat().st_mode) & 0o077
    ):
        raise ArchiveError(
            "Studio Archive state directory must not be accessible by group or others."
        )
    return selected.resolve()


def _config_path(state_dir: Path) -> Path:
    return state_dir / CONFIG_FILENAME


def _client_identities_path(state_dir: Path) -> Path:
    return state_dir / CLIENT_IDENTITIES_FILENAME


def _database_path(state_dir: Path) -> Path:
    return state_dir / DATABASE_FILENAME


def _assert_private_file(path: Path, label: str) -> None:
    if os.name != "posix" or not path.exists():
        return
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ArchiveError(
            f"Studio Archive {label} must not be accessible by group or others."
        )


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _validate_archive_root(root: Path, state_dir: Path) -> Path:
    candidate = Path(root).expanduser()
    if not candidate.is_absolute():
        raise ArchiveError("Archive root must be an absolute path.")
    if candidate.is_symlink():
        raise ArchiveError("Archive root cannot be a symbolic link.")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ArchiveError(f"Archive root is unavailable: {exc}") from exc
    if not resolved.is_dir():
        raise ArchiveError("Archive root must be a directory.")
    if _path_is_within(state_dir, resolved) or _path_is_within(resolved, state_dir):
        raise ArchiveError(
            "The private Studio Archive state directory and source archive must "
            "not contain one another."
        )
    return resolved


def _scope_from_relative(relative_dir: str, root: Path) -> Scope:
    if relative_dir == ".":
        display_name = root.name or "Studio Archive"
    else:
        display_name = Path(relative_dir).name
    return Scope(
        scope_id=_stable_id("scope", relative_dir.casefold()),
        relative_dir=relative_dir,
        display_name=display_name,
    )


def _discover_top_level_scopes(root: Path) -> tuple[Scope, ...]:
    directories: list[Path] = []
    root_files = 0
    try:
        entries = sorted(root.iterdir(), key=lambda path: path.name.casefold())
    except OSError as exc:
        raise ArchiveError(f"Could not inspect archive root: {exc}") from exc
    for path in entries:
        if path.name in IGNORED_NAMES:
            continue
        if path.is_symlink():
            root_files += 1
            continue
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            raise ArchiveError(
                f"Could not inspect archive entry {path.name}: {exc}"
            ) from exc
        if stat.S_ISDIR(mode):
            directories.append(path)
        elif stat.S_ISREG(mode):
            root_files += 1
    if directories:
        directory_scopes = tuple(
            _scope_from_relative(path.relative_to(root).as_posix(), root)
            for path in directories
        )
        scopes = (
            (*directory_scopes, _scope_from_relative(".", root))
            if root_files
            else directory_scopes
        )
        if len({scope.scope_id for scope in scopes}) != len(scopes):
            raise ArchiveError(
                "Top-level archive directory names collide when case is ignored."
            )
        return scopes
    if root_files:
        return (_scope_from_relative(".", root),)
    return (_scope_from_relative(".", root),)


def _config_matches(
    path: Path,
    *,
    archive_root: Path,
    scopes: tuple[Scope, ...],
) -> bool:
    """Compare a persisted config without requiring its old paths to exist."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        payload.get("schema_version") == CONFIG_SCHEMA_VERSION
        and payload.get("archive_root") == str(archive_root)
        and payload.get("scopes") == [scope.as_json() for scope in scopes]
    )


def configure_archive(
    archive_root: Path,
    *,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """Configure one local archive and mechanically discover its top-level scopes."""

    planned_state = _state_dir(state_dir)
    root = _validate_archive_root(archive_root, planned_state)
    private_state = _state_dir(state_dir, create=True)
    scopes = _discover_top_level_scopes(root)
    config_path = _config_path(private_state)
    if config_path.is_file() and _config_matches(
        config_path,
        archive_root=root,
        scopes=scopes,
    ):
        if os.name == "posix":
            config_path.chmod(0o600)
        return studio_archive_status(state_dir=private_state)
    config = ArchiveConfig(
        archive_root=root,
        scopes=scopes,
        configured_at=_now_iso(),
    )
    _write_private_json(config_path, config.as_json())
    status = studio_archive_status(state_dir=private_state)
    status["index_requires_refresh"] = True
    return status


def _load_config(
    state_dir: Path,
    *,
    validate_scope_roots: bool = True,
) -> ArchiveConfig:
    path = _config_path(state_dir)
    if not path.is_file():
        raise ArchiveNotConfiguredError(
            "Studio Archive is not configured. Configure an absolute archive root first."
        )
    _assert_private_file(path, "configuration")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchiveError(
            f"Studio Archive configuration is unreadable: {exc}"
        ) from exc
    if payload.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise ArchiveError("Studio Archive configuration version is unsupported.")
    raw_root = payload.get("archive_root")
    raw_scopes = payload.get("scopes")
    if not isinstance(raw_root, str) or not isinstance(raw_scopes, list):
        raise ArchiveError("Studio Archive configuration is malformed.")
    root = _validate_archive_root(Path(raw_root), state_dir)
    scopes: list[Scope] = []
    for item in raw_scopes:
        if not isinstance(item, dict):
            raise ArchiveError("Studio Archive scope configuration is malformed.")
        values = tuple(
            item.get(key) for key in ("scope_id", "relative_dir", "display_name")
        )
        if not all(isinstance(value, str) and value for value in values):
            raise ArchiveError("Studio Archive scope configuration is incomplete.")
        scope = Scope(
            scope_id=str(values[0]),
            relative_dir=str(values[1]),
            display_name=str(values[2]),
        )
        expected = _scope_from_relative(scope.relative_dir, root)
        if scope.scope_id != expected.scope_id:
            raise ArchiveError(
                "Studio Archive scope identifier does not match its path."
            )
        if scope.relative_dir != ".":
            relative = Path(scope.relative_dir)
            if (
                relative.is_absolute()
                or scope.relative_dir != relative.as_posix()
                or any(part in {"", ".", ".."} for part in relative.parts)
            ):
                raise ArchiveError(
                    "Configured archive scope is not a normalized relative path."
                )
        if validate_scope_roots:
            _resolve_scope_root(root, scope)
        scopes.append(scope)
    if not scopes or len({scope.scope_id for scope in scopes}) != len(scopes):
        raise ArchiveError("Studio Archive scopes must be non-empty and unique.")
    configured_at = str(payload.get("configured_at") or "")
    return ArchiveConfig(root, tuple(scopes), configured_at)


def _normalize_email_address(value: str) -> str:
    if not isinstance(value, str):
        raise ArchiveError("Client email addresses must be strings.")
    raw = value.strip()
    parsed = getaddresses([raw])
    if len(parsed) != 1:
        raise ArchiveError(f"Client email address is invalid: {value!r}.")
    address = parsed[0][1].strip().casefold()
    if (
        len(address) > 254
        or address.count("@") != 1
        or re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`|~-]+@[A-Za-z0-9.-]+",
            address,
        )
        is None
    ):
        raise ArchiveError(f"Client email address is invalid: {value!r}.")
    local_part, domain = address.rsplit("@", maxsplit=1)
    if (
        not local_part
        or not domain
        or domain.startswith((".", "-"))
        or domain.endswith((".", "-"))
        or ".." in domain
    ):
        raise ArchiveError(f"Client email address is invalid: {value!r}.")
    return address


def _normalize_email_addresses(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or len(values) > MAX_CLIENT_EMAIL_ADDRESSES:
        raise ArchiveError(
            "A client may have at most "
            f"{MAX_CLIENT_EMAIL_ADDRESSES} confirmed email addresses."
        )
    normalized = {_normalize_email_address(value) for value in values}
    return tuple(sorted(normalized))


def _normalize_legal_names(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or len(values) > MAX_CLIENT_LEGAL_NAMES:
        raise ArchiveError(
            f"A client may have at most {MAX_CLIENT_LEGAL_NAMES} legal names."
        )
    normalized: dict[str, str] = {}
    for value in values:
        if not isinstance(value, str):
            raise ArchiveError("Client legal names must be strings.")
        name = re.sub(r"\s+", " ", value).strip()
        if (
            not name
            or len(name) > 160
            or re.search(r"[\x00-\x1f\x7f]", name) is not None
        ):
            raise ArchiveError("Client legal names must contain 1 to 160 characters.")
        normalized.setdefault(name.casefold(), name)
    return tuple(normalized[key] for key in sorted(normalized))


def _normalize_tax_identifiers(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or len(values) > MAX_CLIENT_TAX_IDENTIFIERS:
        raise ArchiveError(
            "A client may have at most "
            f"{MAX_CLIENT_TAX_IDENTIFIERS} tax identifiers."
        )
    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise ArchiveError("Client tax identifiers must be strings.")
        identifier = re.sub(r"\s+", "", value).upper()
        if re.fullmatch(r"[A-Z0-9]{5,32}", identifier) is None:
            raise ArchiveError(
                "Client tax identifiers must contain 5 to 32 letters or digits."
            )
        normalized.add(identifier)
    return tuple(sorted(normalized))


def _validate_identity_uniqueness(records: Sequence[ClientIdentity]) -> None:
    email_owners: dict[str, str] = {}
    tax_owners: dict[str, str] = {}
    for record in records:
        for email_address in record.email_addresses:
            previous_scope = email_owners.setdefault(email_address, record.scope_id)
            if previous_scope != record.scope_id:
                raise ArchiveError(
                    "Client email address is assigned to more than one scope: "
                    f"{email_address}."
                )
        for tax_identifier in record.tax_identifiers:
            previous_scope = tax_owners.setdefault(tax_identifier, record.scope_id)
            if previous_scope != record.scope_id:
                raise ArchiveError(
                    "Client tax identifier is assigned to more than one scope: "
                    f"{tax_identifier}."
                )


def _load_client_identities(state_dir: Path) -> tuple[ClientIdentity, ...]:
    path = _client_identities_path(state_dir)
    if not path.is_file():
        return ()
    _assert_private_file(path, "client identity registry")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchiveError(
            f"Studio Archive client identity registry is unreadable: {exc}"
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != CLIENT_IDENTITIES_SCHEMA_VERSION
        or not isinstance(payload.get("clients"), list)
    ):
        raise ArchiveError("Studio Archive client identity registry is malformed.")
    raw_clients = payload["clients"]
    if len(raw_clients) > MAX_CLIENT_IDENTITIES:
        raise ArchiveError("Studio Archive client identity registry is too large.")
    records: list[ClientIdentity] = []
    seen_scope_ids: set[str] = set()
    required_keys = {
        "scope_id",
        "email_addresses",
        "legal_names",
        "tax_identifiers",
        "updated_at",
    }
    for item in raw_clients:
        if not isinstance(item, dict) or set(item) != required_keys:
            raise ArchiveError("Studio Archive client identity record is malformed.")
        scope_id = item["scope_id"]
        updated_at = item["updated_at"]
        if (
            not isinstance(scope_id, str)
            or re.fullmatch(r"scope_[0-9a-f]{24}", scope_id) is None
            or scope_id in seen_scope_ids
            or not isinstance(updated_at, str)
            or not updated_at
        ):
            raise ArchiveError("Studio Archive client identity record is invalid.")
        raw_emails = item["email_addresses"]
        raw_names = item["legal_names"]
        raw_tax_ids = item["tax_identifiers"]
        if not all(
            isinstance(values, list) for values in (raw_emails, raw_names, raw_tax_ids)
        ):
            raise ArchiveError("Studio Archive client identity values are malformed.")
        records.append(
            ClientIdentity(
                scope_id=scope_id,
                email_addresses=_normalize_email_addresses(raw_emails),
                legal_names=_normalize_legal_names(raw_names),
                tax_identifiers=_normalize_tax_identifiers(raw_tax_ids),
                updated_at=updated_at,
            )
        )
        seen_scope_ids.add(scope_id)
    _validate_identity_uniqueness(records)
    return tuple(sorted(records, key=lambda record: record.scope_id))


def _write_client_identities(
    state_dir: Path,
    records: Sequence[ClientIdentity],
) -> None:
    _validate_identity_uniqueness(records)
    _write_private_json(
        _client_identities_path(state_dir),
        {
            "schema_version": CLIENT_IDENTITIES_SCHEMA_VERSION,
            "clients": [
                record.as_json()
                for record in sorted(records, key=lambda item: item.scope_id)
            ],
        },
    )


def _client_record(
    record: ClientIdentity | None,
    *,
    scope: Scope,
) -> dict[str, Any]:
    if record is None:
        return {
            **scope.as_json(),
            "profile_status": "alias_only",
            "email_addresses": [],
            "legal_names": [],
            "tax_identifiers": [],
            "updated_at": None,
        }
    profile_status = "configured" if record.email_addresses else "candidate_only"
    return {
        **scope.as_json(),
        "profile_status": profile_status,
        "email_addresses": list(record.email_addresses),
        "legal_names": list(record.legal_names),
        "tax_identifiers": list(record.tax_identifiers),
        "updated_at": record.updated_at,
    }


def list_studio_client_identities(
    *,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """List exact archive scopes and their private Gmail identity profiles."""

    private_state = _state_dir(state_dir)
    stored_config = _load_config(private_state, validate_scope_roots=False)
    config, scopes_changed = _current_scope_view(stored_config)
    records = _load_client_identities(private_state)
    records_by_scope = {record.scope_id: record for record in records}
    active_scope_ids = {scope.scope_id for scope in config.scopes}
    clients = [
        _client_record(records_by_scope.get(scope.scope_id), scope=scope)
        for scope in config.scopes
    ]
    orphaned = [
        {
            **record.as_json(),
            "profile_status": "orphaned",
        }
        for record in records
        if record.scope_id not in active_scope_ids
    ]
    return {
        "scope_configuration_changed": scopes_changed,
        "configured_profile_count": sum(
            client["profile_status"] == "configured" for client in clients
        ),
        "candidate_only_profile_count": sum(
            client["profile_status"] == "candidate_only" for client in clients
        ),
        "alias_only_profile_count": sum(
            client["profile_status"] == "alias_only" for client in clients
        ),
        "orphaned_profile_count": len(orphaned),
        "clients": clients,
        "orphaned_profiles": orphaned,
        "gmail_connector_called": False,
    }


def set_studio_client_identity(
    scope_id: str,
    *,
    email_addresses: Sequence[str] = (),
    legal_names: Sequence[str] = (),
    tax_identifiers: Sequence[str] = (),
    replace_orphaned_scope_id: str | None = None,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """Replace one scope's confirmed private Gmail identity profile."""

    private_state = _state_dir(state_dir)
    config = _load_config(private_state, validate_scope_roots=False)
    _, scopes_changed = _current_scope_view(config)
    if scopes_changed:
        raise ArchiveError(
            "Top-level archive scopes changed; refresh before configuring clients."
        )
    scopes_by_id = {scope.scope_id: scope for scope in config.scopes}
    scope = scopes_by_id.get(scope_id)
    if scope is None:
        raise ArchiveError("Client identity scope is not configured.")
    records = list(_load_client_identities(private_state))
    existing = next(
        (record for record in records if record.scope_id == scope_id),
        None,
    )
    if replace_orphaned_scope_id is not None:
        if (
            not isinstance(replace_orphaned_scope_id, str)
            or re.fullmatch(
                r"scope_[0-9a-f]{24}",
                replace_orphaned_scope_id,
            )
            is None
        ):
            raise ArchiveError("Replacement client scope identifier is invalid.")
        if replace_orphaned_scope_id in scopes_by_id:
            raise ArchiveError(
                "Only an orphaned client profile can be explicitly rebound."
            )
        orphaned = next(
            (
                record
                for record in records
                if record.scope_id == replace_orphaned_scope_id
            ),
            None,
        )
        if orphaned is None:
            raise ArchiveError("Orphaned client profile was not found.")
        if existing is not None:
            raise ArchiveError(
                "The target client scope already has an identity profile."
            )
        if email_addresses or legal_names or tax_identifiers:
            raise ArchiveError(
                "Do not supply identity values while rebinding an orphaned profile."
            )
        replacement = ClientIdentity(
            scope_id=scope_id,
            email_addresses=orphaned.email_addresses,
            legal_names=orphaned.legal_names,
            tax_identifiers=orphaned.tax_identifiers,
            updated_at=_now_iso(),
        )
        updated_records = [
            record for record in records if record.scope_id != replace_orphaned_scope_id
        ] + [replacement]
        _write_client_identities(private_state, updated_records)
        return {
            "status": "rebound",
            "client": _client_record(replacement, scope=scope),
            "replaced_orphaned_scope_id": replace_orphaned_scope_id,
            "gmail_connector_called": False,
            "gmail_credentials_stored": False,
        }
    normalized_emails = _normalize_email_addresses(email_addresses)
    normalized_names = _normalize_legal_names(legal_names)
    normalized_tax_ids = _normalize_tax_identifiers(tax_identifiers)
    if not (normalized_emails or normalized_names or normalized_tax_ids):
        raise ArchiveError(
            "Configure at least one confirmed email address, legal name, "
            "or tax identifier."
        )
    unchanged = existing is not None and (
        existing.email_addresses == normalized_emails
        and existing.legal_names == normalized_names
        and existing.tax_identifiers == normalized_tax_ids
    )
    replacement = ClientIdentity(
        scope_id=scope_id,
        email_addresses=normalized_emails,
        legal_names=normalized_names,
        tax_identifiers=normalized_tax_ids,
        updated_at=existing.updated_at if unchanged else _now_iso(),
    )
    updated_records = [record for record in records if record.scope_id != scope_id] + [
        replacement
    ]
    _validate_identity_uniqueness(updated_records)
    if not unchanged:
        _write_client_identities(private_state, updated_records)
    return {
        "status": "unchanged" if unchanged else "configured",
        "client": _client_record(replacement, scope=scope),
        "gmail_connector_called": False,
        "gmail_credentials_stored": False,
    }


def _gmail_safe_phrase(value: str) -> str:
    normalized = re.sub(r'["{}\\():\[\]]', " ", value)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        raise ArchiveError("Gmail search phrase contains no safe characters.")
    return f'"{normalized}"'


def _gmail_date(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        raise ArchiveError(f"{label} must use YYYY-MM-DD.")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ArchiveError(f"{label} is not a valid calendar date.") from exc
    return value.replace("-", "/")


def _gmail_query_prefix(
    *,
    after: str | None,
    before: str | None,
) -> str:
    parts = ["in:anywhere", "-in:spam", "-in:trash"]
    normalized_after = _gmail_date(after, "after")
    normalized_before = _gmail_date(before, "before")
    if (
        normalized_after is not None
        and normalized_before is not None
        and normalized_after >= normalized_before
    ):
        raise ArchiveError("after must be earlier than before.")
    if normalized_after is not None:
        parts.append(f"after:{normalized_after}")
    if normalized_before is not None:
        parts.append(f"before:{normalized_before}")
    return " ".join(parts)


def _chunked(values: Sequence[str], size: int) -> Iterator[tuple[str, ...]]:
    for offset in range(0, len(values), size):
        yield tuple(values[offset : offset + size])


def plan_gmail_client_search(
    scope_id: str,
    *,
    topic: str | None = None,
    after: str | None = None,
    before: str | None = None,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """Build bounded Gmail-native searches without calling the connector."""

    private_state = _state_dir(state_dir)
    config = _load_config(private_state, validate_scope_roots=False)
    _, scopes_changed = _current_scope_view(config)
    if scopes_changed:
        raise ArchiveError(
            "Top-level archive scopes changed; refresh before planning Gmail search."
        )
    if scope_id == "all":
        raise ArchiveError("Studio-wide Gmail search is not supported.")
    scope = next((item for item in config.scopes if item.scope_id == scope_id), None)
    if scope is None:
        raise ArchiveError("Gmail search scope is not configured.")
    records = _load_client_identities(private_state)
    record = next((item for item in records if item.scope_id == scope_id), None)
    if topic is not None:
        if not isinstance(topic, str) or not topic.strip():
            raise ArchiveError("Gmail search topic must be non-empty when supplied.")
        if len(topic) > MAX_GMAIL_TOPIC_CHARS:
            raise ArchiveError(
                "Gmail search topic must contain at most "
                f"{MAX_GMAIL_TOPIC_CHARS} characters."
            )
        topic_phrase = _gmail_safe_phrase(topic)
    else:
        topic_phrase = None
    prefix = _gmail_query_prefix(after=after, before=before)
    topic_suffix = "" if topic_phrase is None else f" {topic_phrase}"
    queries: list[dict[str, Any]] = []
    if record is not None:
        for query_index, addresses in enumerate(
            _chunked(record.email_addresses, MAX_GMAIL_QUERY_IDENTITIES),
            start=1,
        ):
            participant_terms = " ".join(
                term
                for address in addresses
                for term in (
                    f"from:{address}",
                    f"to:{address}",
                    f"cc:{address}",
                )
            )
            queries.append(
                {
                    "query_id": f"direct-{query_index}",
                    "kind": "confirmed_participant",
                    "query": f"{prefix} {{{participant_terms}}}{topic_suffix}",
                    "max_results": 20,
                    "routing_rule": "exact_unique_address_match_required",
                }
            )
        candidate_values = tuple(
            dict.fromkeys(
                (
                    scope.display_name,
                    *record.legal_names,
                    *record.tax_identifiers,
                )
            )
        )
    else:
        candidate_values = (scope.display_name,)
    for query_index, identities in enumerate(
        _chunked(candidate_values, MAX_GMAIL_QUERY_IDENTITIES),
        start=1,
    ):
        identity_terms = " ".join(_gmail_safe_phrase(value) for value in identities)
        queries.append(
            {
                "query_id": f"candidate-{query_index}",
                "kind": "identity_candidate",
                "query": f"{prefix} {{{identity_terms}}}{topic_suffix}",
                "max_results": 20,
                "routing_rule": "message_read_and_semantic_review_required",
            }
        )
    if record is None:
        profile_status = "alias_only"
    elif record.email_addresses:
        profile_status = "configured"
    else:
        profile_status = "candidate_only"
    return {
        "connector": "gmail",
        "scope_id": scope.scope_id,
        "display_name": scope.display_name,
        "profile_status": profile_status,
        "queries": queries,
        "requires_connector_profile_check": True,
        "requires_message_read_before_use": True,
        "gmail_connector_called": False,
        "warnings": (
            []
            if record is not None and record.email_addresses
            else [
                "No confirmed participant address is configured. Candidate "
                "results must be reviewed and an address confirmed before "
                "automatic client routing."
            ]
        ),
    }


def match_studio_email_client(
    header_addresses: Sequence[str],
    *,
    headers_complete: bool = False,
    expected_scope_id: str | None = None,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """Match Gmail headers only by unique, confirmed full email addresses."""

    if (
        isinstance(header_addresses, (str, bytes))
        or not header_addresses
        or len(header_addresses) > 100
    ):
        raise ArchiveError("Provide between 1 and 100 Gmail header address values.")
    if not isinstance(headers_complete, bool):
        raise ArchiveError("headers_complete must be a boolean.")
    private_state = _state_dir(state_dir)
    config = _load_config(private_state, validate_scope_roots=False)
    _, scopes_changed = _current_scope_view(config)
    if scopes_changed:
        raise ArchiveError(
            "Top-level archive scopes changed; refresh before matching Gmail."
        )
    scopes_by_id = {scope.scope_id: scope for scope in config.scopes}
    if expected_scope_id is not None and expected_scope_id not in scopes_by_id:
        raise ArchiveError("Expected Gmail client scope is not configured.")
    parsed_addresses: set[str] = set()
    unparsed_headers: list[str] = []
    for raw_header in header_addresses:
        if not isinstance(raw_header, str) or len(raw_header) > 2_000:
            raise ArchiveError("Gmail header address values must be bounded strings.")
        parsed = getaddresses([raw_header])
        accepted = False
        parsed_completely = bool(parsed)
        for _, address in parsed:
            if not address:
                parsed_completely = False
                continue
            try:
                parsed_addresses.add(_normalize_email_address(address))
            except ArchiveError:
                parsed_completely = False
                continue
            accepted = True
        if not accepted or not parsed_completely:
            unparsed_headers.append(raw_header)
    records = _load_client_identities(private_state)
    owners = {
        email_address: record.scope_id
        for record in records
        for email_address in record.email_addresses
    }
    matched: dict[str, list[str]] = {}
    for address in sorted(parsed_addresses):
        owner = owners.get(address)
        if owner is not None:
            matched.setdefault(owner, []).append(address)
    candidate_scope_ids = sorted(matched)
    header_coverage_complete = headers_complete and not unparsed_headers
    if len(candidate_scope_ids) > 1:
        routing_status = "ambiguous"
        matched_scope_id = None
    elif not header_coverage_complete:
        routing_status = "incomplete"
        matched_scope_id = None
    elif len(candidate_scope_ids) == 1:
        routing_status = "exact"
        matched_scope_id: str | None = candidate_scope_ids[0]
    else:
        routing_status = "unassigned"
        matched_scope_id = None
    belongs_to_expected_scope: bool | None
    if expected_scope_id is None or matched_scope_id is None:
        belongs_to_expected_scope = None
    else:
        belongs_to_expected_scope = matched_scope_id == expected_scope_id
    return {
        "routing_status": routing_status,
        "matched_scope_id": matched_scope_id,
        "candidate_scope_ids": candidate_scope_ids,
        "matches": [
            {
                "scope_id": scope_id,
                "display_name": scopes_by_id[scope_id].display_name,
                "email_addresses": matched[scope_id],
                "match_method": "exact_email_address",
            }
            for scope_id in candidate_scope_ids
        ],
        "belongs_to_expected_scope": belongs_to_expected_scope,
        "may_use_in_scoped_answer": belongs_to_expected_scope is True,
        "requires_semantic_review": routing_status != "exact",
        "parsed_email_addresses": sorted(parsed_addresses),
        "unparsed_header_count": len(unparsed_headers),
        "header_coverage_complete": header_coverage_complete,
        "gmail_connector_called": False,
        "gmail_data_persisted": False,
    }


def _config_fingerprint(config: ArchiveConfig) -> str:
    payload = json.dumps(
        {
            "schema_version": CONFIG_SCHEMA_VERSION,
            "archive_root": str(config.archive_root),
            "scopes": [scope.as_json() for scope in config.scopes],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_bytes(payload.encode("utf-8"))


def _connect(
    state_dir: Path,
    *,
    readonly: bool = False,
) -> sqlite3.Connection:
    path = _database_path(state_dir)
    if readonly:
        if not path.is_file():
            raise ArchiveError("Studio Archive index is missing; refresh it first.")
        _assert_private_file(path, "index")
        connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if readonly:
        connection.execute("PRAGMA query_only = ON")
        try:
            schema_row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()
        except sqlite3.OperationalError as exc:
            connection.close()
            raise ArchiveError(
                "Studio Archive index is invalid; rebuild it before searching."
            ) from exc
        if schema_row is None or schema_row["value"] != SCHEMA_VERSION:
            connection.close()
            raise ArchiveError("Studio Archive database schema is unsupported.")
        return connection
    connection.execute("PRAGMA secure_delete = ON")
    connection.execute("PRAGMA journal_mode = DELETE")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS documents (
            document_id TEXT PRIMARY KEY,
            scope_id TEXT NOT NULL,
            relative_path TEXT NOT NULL UNIQUE,
            extension TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            extraction_method TEXT NOT NULL,
            status TEXT NOT NULL,
            needs_ocr INTEGER NOT NULL,
            limitations_json TEXT NOT NULL,
            indexed_at TEXT NOT NULL,
            last_seen_generation INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chunks (
            source_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES documents(document_id)
                ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            locator_kind TEXT NOT NULL,
            locator_value TEXT NOT NULL,
            text TEXT NOT NULL,
            text_sha256 TEXT NOT NULL,
            UNIQUE(document_id, ordinal)
        );
        CREATE TABLE IF NOT EXISTS scan_issues (
            relative_path TEXT PRIMARY KEY,
            scope_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            size_bytes INTEGER
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
            source_id UNINDEXED,
            text,
            tokenize = 'unicode61 remove_diacritics 2'
        );
        CREATE INDEX IF NOT EXISTS documents_scope_idx
            ON documents(scope_id, relative_path);
        CREATE INDEX IF NOT EXISTS chunks_document_idx
            ON chunks(document_id, ordinal);
        """)
    try:
        connection.execute(
            "INSERT INTO chunk_fts(chunk_fts, rank) VALUES('secure-delete', 1)"
        )
    except sqlite3.OperationalError as exc:
        connection.close()
        raise ArchiveError(
            "The active SQLite FTS5 runtime does not support secure deletion."
        ) from exc
    connection.execute(
        "INSERT OR IGNORE INTO metadata(key, value) VALUES('schema_version', ?)",
        (SCHEMA_VERSION,),
    )
    schema_row = connection.execute(
        "SELECT value FROM metadata WHERE key = 'schema_version'"
    ).fetchone()
    if schema_row is None or schema_row["value"] != SCHEMA_VERSION:
        connection.close()
        raise ArchiveError("Studio Archive database schema is unsupported.")
    connection.commit()
    try:
        path.chmod(0o600)
    except OSError:
        connection.close()
        raise
    return connection


def _metadata_get(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute(
        "SELECT value FROM metadata WHERE key = ?",
        (key,),
    ).fetchone()
    return None if row is None else str(row["value"])


def _metadata_set(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO metadata(key, value) VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def _clear_index(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM chunk_fts")
    connection.execute("DELETE FROM chunks")
    connection.execute("DELETE FROM documents")
    connection.execute("DELETE FROM scan_issues")


def _replace_scan_issues(
    connection: sqlite3.Connection,
    issues: Sequence[ScanIssue],
) -> None:
    connection.execute("DELETE FROM scan_issues")
    connection.executemany(
        """
        INSERT INTO scan_issues(relative_path, scope_id, reason, size_bytes)
        VALUES (?, ?, ?, ?)
        """,
        (
            (
                issue.relative_path,
                issue.scope_id,
                issue.reason,
                issue.size_bytes,
            )
            for issue in issues
        ),
    )


def _scan_issue_status(
    connection: sqlite3.Connection,
    *,
    scope_id: str | None = None,
) -> dict[str, Any]:
    issue_count = int(
        connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM scan_issues
            WHERE ? IS NULL OR scope_id = ?
            """,
            (scope_id, scope_id),
        ).fetchone()["count"]
    )
    rows = connection.execute(
        """
        SELECT scope_id, relative_path, reason, size_bytes
        FROM scan_issues
        WHERE ? IS NULL OR scope_id = ?
        ORDER BY relative_path
        LIMIT ?
        """,
        (scope_id, scope_id, MAX_STATUS_SCAN_ISSUES),
    ).fetchall()
    return {
        "scan_issue_count": issue_count,
        "scan_issues": [
            {
                "scope_id": str(row["scope_id"]),
                "relative_path": str(row["relative_path"]),
                "reason": str(row["reason"]),
                "size_bytes": (
                    None if row["size_bytes"] is None else int(row["size_bytes"])
                ),
            }
            for row in rows
        ],
        "scan_issues_truncated": issue_count > len(rows),
    }


def _document_issue_status(
    connection: sqlite3.Connection,
    *,
    scope_id: str | None = None,
) -> dict[str, Any]:
    """Return a bounded inventory of indexed documents with evidence limits."""

    issue_count = int(
        connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM (
                SELECT d.document_id
                FROM documents AS d
                LEFT JOIN chunks AS c ON c.document_id = d.document_id
                WHERE ? IS NULL OR d.scope_id = ?
                GROUP BY d.document_id
                HAVING d.status != 'indexed'
                    OR d.needs_ocr = 1
                    OR d.limitations_json != '[]'
                    OR COUNT(c.source_id) = 0
            )
            """,
            (scope_id, scope_id),
        ).fetchone()["count"]
    )
    rows = connection.execute(
        """
        SELECT
            d.scope_id,
            d.relative_path,
            d.status,
            d.needs_ocr,
            d.limitations_json,
            COUNT(c.source_id) AS chunk_count
        FROM documents AS d
        LEFT JOIN chunks AS c ON c.document_id = d.document_id
        WHERE ? IS NULL OR d.scope_id = ?
        GROUP BY
            d.document_id,
            d.scope_id,
            d.relative_path,
            d.status,
            d.needs_ocr,
            d.limitations_json
        HAVING d.status != 'indexed'
            OR d.needs_ocr = 1
            OR d.limitations_json != '[]'
            OR COUNT(c.source_id) = 0
        ORDER BY d.relative_path
        LIMIT ?
        """,
        (scope_id, scope_id, MAX_STATUS_DOCUMENT_ISSUES),
    ).fetchall()
    return {
        "document_issue_count": issue_count,
        "document_issues": [
            {
                "scope_id": str(row["scope_id"]),
                "relative_path": str(row["relative_path"]),
                "document_status": str(row["status"]),
                "needs_ocr": bool(row["needs_ocr"]),
                "limitations": _decode_limitations(str(row["limitations_json"])),
                "chunk_count": int(row["chunk_count"]),
            }
            for row in rows
        ],
        "document_issues_truncated": issue_count > len(rows),
    }


def _resolve_scope_root(root: Path, scope: Scope) -> Path:
    if scope.relative_dir == ".":
        return root
    relative = Path(scope.relative_dir)
    if (
        relative.is_absolute()
        or scope.relative_dir != relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ArchiveError(
            "Configured archive scope is not a normalized relative path."
        )
    candidate = root
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink():
            raise ArchiveError("Configured archive scope contains a symbolic link.")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ArchiveError(f"Configured archive scope is unavailable: {exc}") from exc
    if not _path_is_within(resolved, root) or not resolved.is_dir():
        raise ArchiveError("Configured archive scope escapes the archive root.")
    return resolved


def _walk_archive_entries(directory: Path) -> Iterator[tuple[Path, str | None]]:
    try:
        entries = sorted(
            os.scandir(directory),
            key=lambda entry: entry.name.casefold(),
        )
    except OSError as exc:
        raise ArchiveError(
            f"Archive enumeration failed at {directory.name}: {exc}"
        ) from exc
    for entry in entries:
        if entry.name in IGNORED_NAMES:
            continue
        try:
            if entry.is_symlink():
                yield Path(entry.path), "symbolic_link_not_followed"
            elif entry.is_dir(follow_symlinks=False):
                yield from _walk_archive_entries(Path(entry.path))
            elif entry.is_file(follow_symlinks=False):
                yield Path(entry.path), None
        except OSError as exc:
            raise ArchiveError(
                f"Archive enumeration failed at {entry.name}: {exc}"
            ) from exc


def _scope_entries(
    scope_root: Path,
    scope: Scope,
) -> Iterator[tuple[Path, str | None]]:
    """Yield source files for one non-overlapping configured scope."""

    if scope.relative_dir != ".":
        yield from _walk_archive_entries(scope_root)
        return
    try:
        entries = sorted(scope_root.iterdir(), key=lambda path: path.name.casefold())
    except OSError as exc:
        raise ArchiveError(f"Archive enumeration failed at root: {exc}") from exc
    for path in entries:
        if path.name in IGNORED_NAMES:
            continue
        if path.is_symlink():
            yield path, "symbolic_link_not_followed"
            continue
        try:
            if stat.S_ISREG(path.lstat().st_mode):
                yield path, None
        except OSError as exc:
            raise ArchiveError(
                f"Archive enumeration failed at {path.name}: {exc}"
            ) from exc


def _discover_files(
    config: ArchiveConfig,
) -> tuple[list[DiscoveredFile], list[ScanIssue]]:
    discovered: list[DiscoveredFile] = []
    issues: list[ScanIssue] = []
    total_bytes = 0
    scanned_files = 0
    seen_paths: set[str] = set()
    seen_casefolded_paths: set[str] = set()
    for scope in config.scopes:
        scope_root = _resolve_scope_root(config.archive_root, scope)
        for path, skip_reason in _scope_entries(scope_root, scope):
            relative_path = path.relative_to(config.archive_root).as_posix()
            if relative_path in seen_paths:
                raise ArchiveError(
                    f"Configured scopes overlap at archive path: {relative_path}"
                )
            seen_paths.add(relative_path)
            scanned_files += 1
            if scanned_files > MAX_FILES:
                raise ArchiveError(
                    f"Archive exceeds the {MAX_FILES:,}-file first-version limit."
                )
            if skip_reason is not None:
                issues.append(
                    ScanIssue(
                        scope_id=scope.scope_id,
                        relative_path=relative_path,
                        reason=skip_reason,
                        size_bytes=None,
                    )
                )
                continue
            try:
                metadata = path.stat(follow_symlinks=False)
            except OSError:
                issues.append(
                    ScanIssue(
                        scope_id=scope.scope_id,
                        relative_path=relative_path,
                        reason="source_metadata_unavailable",
                        size_bytes=None,
                    )
                )
                continue
            if not stat.S_ISREG(metadata.st_mode):
                continue
            suffix = path.suffix.lower()
            if suffix not in SUPPORTED_SUFFIXES:
                issues.append(
                    ScanIssue(
                        scope_id=scope.scope_id,
                        relative_path=relative_path,
                        reason="unsupported_extension",
                        size_bytes=metadata.st_size,
                    )
                )
                continue
            casefolded_path = relative_path.casefold()
            if casefolded_path in seen_casefolded_paths:
                raise ArchiveError(
                    "Archive contains paths that collide when case is ignored: "
                    f"{relative_path}"
                )
            seen_casefolded_paths.add(casefolded_path)
            if metadata.st_size > MAX_FILE_BYTES:
                issues.append(
                    ScanIssue(
                        scope_id=scope.scope_id,
                        relative_path=relative_path,
                        reason="file_size_limit_exceeded",
                        size_bytes=metadata.st_size,
                    )
                )
                continue
            total_bytes += metadata.st_size
            if total_bytes > MAX_TOTAL_BYTES:
                raise ArchiveError(
                    "Archive exceeds the first-version total byte limit."
                )
            discovered.append(
                DiscoveredFile(
                    scope_id=scope.scope_id,
                    relative_path=relative_path,
                    path=path,
                    size_bytes=metadata.st_size,
                    mtime_ns=metadata.st_mtime_ns,
                )
            )
    return discovered, issues


def _resolve_source_file(root: Path, relative_path: str) -> Path:
    """Resolve one indexed regular file without following symbolic links."""

    relative = Path(relative_path)
    if (
        relative.is_absolute()
        or relative_path != relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ArchiveError("Indexed source path is not normalized and relative.")
    candidate = root
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink():
            raise ArchiveError("Indexed source path contains a symbolic link.")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise SourceChangedError(f"Indexed source is unavailable: {exc}") from exc
    if not _path_is_within(resolved, root):
        raise ArchiveError("Indexed source path escapes the archive root.")
    if not stat.S_ISREG(resolved.lstat().st_mode):
        raise ArchiveError("Indexed source is not a regular file.")
    return resolved


def _normalize_text(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in text.replace("\r", "\n").split("\n")
    ]
    return "\n".join(line for line in lines if line).strip()


def _text_is_useful(text: str) -> bool:
    compact = _normalize_text(text)
    if len(compact) < 40:
        return False
    alpha_count = sum(character.isalpha() for character in compact)
    return alpha_count >= max(20, len(compact) // 10)


def _chunks_from_numbered_lines(
    rows: Sequence[tuple[int, str]],
    *,
    locator_kind: str,
    locator_prefix: str = "",
) -> tuple[ExtractedChunk, ...]:
    chunks: list[ExtractedChunk] = []
    current: list[tuple[int, str]] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        start = current[0][0]
        end = current[-1][0]
        range_value = str(start) if start == end else f"{start}-{end}"
        locator_value = f"{locator_prefix}{range_value}"
        chunks.append(
            ExtractedChunk(
                ordinal=len(chunks),
                locator_kind=locator_kind,
                locator_value=locator_value,
                text="\n".join(value for _, value in current),
            )
        )
        current = []
        current_chars = 0

    for number, raw_text in rows:
        text = _normalize_text(raw_text)
        if not text:
            continue
        if current and (
            len(current) >= MAX_CHUNK_LINES
            or current_chars + len(text) + 1 > MAX_CHUNK_CHARS
        ):
            flush()
        if len(text) > MAX_CHUNK_CHARS:
            flush()
            for offset in range(0, len(text), MAX_CHUNK_CHARS):
                piece = text[offset : offset + MAX_CHUNK_CHARS]
                chunks.append(
                    ExtractedChunk(
                        ordinal=len(chunks),
                        locator_kind=locator_kind,
                        locator_value=f"{locator_prefix}{number}",
                        text=piece,
                    )
                )
            continue
        current.append((number, text))
        current_chars += len(text) + 1
    flush()
    return tuple(chunks)


def _extract_plain_text(path: Path) -> ExtractionResult:
    if path.stat().st_size > MAX_TEXT_BYTES:
        return ExtractionResult((), "text", "error", False, ("text_file_too_large",))
    payload = path.read_bytes()
    text = payload.decode("utf-8-sig", errors="replace")
    rows = tuple(enumerate(text.splitlines(), start=1))
    chunks = _chunks_from_numbered_lines(rows, locator_kind="lines")
    status = "indexed" if chunks else "partial"
    limitations = () if chunks else ("no_extractable_text",)
    return ExtractionResult(chunks, "plain_text", status, False, limitations)


def _validate_ooxml_archive(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        if len(members) > MAX_OOXML_MEMBERS:
            raise ArchiveError("OOXML archive contains too many members.")
        names = [info.filename for info in members]
        if len(names) != len(set(names)):
            raise ArchiveError("OOXML archive contains duplicate member names.")
        if sum(info.file_size for info in members) > MAX_OOXML_TOTAL_BYTES:
            raise ArchiveError("Expanded OOXML archive exceeds the size limit.")
        for info in members:
            if info.flag_bits & 0x1:
                raise ArchiveError("Encrypted OOXML members are unsupported.")
            ratio = info.file_size / max(info.compress_size, 1)
            if info.file_size > MAX_OOXML_MEMBER_BYTES:
                raise ArchiveError("OOXML member exceeds the size limit.")
            if ratio > MAX_OOXML_COMPRESSION_RATIO:
                raise ArchiveError("OOXML member compression ratio is unsafe.")


def _extract_docx(path: Path) -> ExtractionResult:
    _validate_ooxml_archive(path)
    from docx import Document

    document = Document(path)
    chunks: list[ExtractedChunk] = list(
        _chunks_from_numbered_lines(
            tuple(
                (index, paragraph.text)
                for index, paragraph in enumerate(document.paragraphs, start=1)
            ),
            locator_kind="paragraphs",
        )
    )
    for table_number, table in enumerate(document.tables, start=1):
        rows = [
            "\t".join(_normalize_text(cell.text) for cell in row.cells)
            for row in table.rows
        ]
        for chunk in _chunks_from_numbered_lines(
            tuple(enumerate(rows, start=1)),
            locator_kind="table",
            locator_prefix=f"{table_number}, rows ",
        ):
            chunks.append(
                ExtractedChunk(
                    ordinal=len(chunks),
                    locator_kind=chunk.locator_kind,
                    locator_value=chunk.locator_value,
                    text=chunk.text,
                )
            )
    status = "indexed" if chunks else "partial"
    return ExtractionResult(
        tuple(chunks),
        "docx",
        status,
        False,
        () if chunks else ("no_extractable_text",),
    )


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return _normalize_text(str(value))


def _extract_xlsx(path: Path) -> ExtractionResult:
    _validate_ooxml_archive(path)
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter

    workbook = load_workbook(path, read_only=True, data_only=False)
    chunks: list[ExtractedChunk] = []
    limitations: list[str] = []
    try:
        for sheet_index, worksheet in enumerate(workbook.worksheets, start=1):
            if sheet_index > MAX_WORKBOOK_SHEETS:
                limitations.append("workbook_sheet_limit_reached")
                break
            rows: list[tuple[int, str]] = []
            if int(worksheet.max_column or 0) > MAX_WORKSHEET_COLUMNS:
                limitations.append(f"worksheet_column_limit_reached:{worksheet.title}")
            for row_number, row in enumerate(
                worksheet.iter_rows(max_col=MAX_WORKSHEET_COLUMNS),
                start=1,
            ):
                if row_number > MAX_WORKSHEET_ROWS:
                    limitations.append(f"worksheet_row_limit_reached:{worksheet.title}")
                    break
                values = []
                for column_number, cell in enumerate(row, start=1):
                    value = _cell_text(cell.value)
                    if value:
                        values.append(
                            f"{get_column_letter(column_number)}{row_number}={value}"
                        )
                if values:
                    rows.append((row_number, "\t".join(values)))
            for chunk in _chunks_from_numbered_lines(
                rows,
                locator_kind="sheet",
                locator_prefix=f"{worksheet.title}!rows ",
            ):
                chunks.append(
                    ExtractedChunk(
                        ordinal=len(chunks),
                        locator_kind=chunk.locator_kind,
                        locator_value=chunk.locator_value,
                        text=chunk.text,
                    )
                )
    finally:
        workbook.close()
    status = "indexed" if chunks and not limitations else "partial"
    if not chunks:
        limitations.append("no_extractable_text")
    return ExtractionResult(
        tuple(chunks),
        "xlsx",
        status,
        False,
        tuple(dict.fromkeys(limitations)),
    )


def _html_to_text(value: str) -> str:
    parser = _HtmlTextExtractor()
    parser.feed(value)
    parser.close()
    return " ".join(parser.parts)


def _extract_eml(path: Path) -> ExtractionResult:
    if path.stat().st_size > MAX_EMAIL_BYTES:
        return ExtractionResult((), "eml", "error", False, ("email_too_large",))
    message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    lines = [
        f"Subject: {message.get('subject', '')}",
        f"From: {message.get('from', '')}",
        f"To: {message.get('to', '')}",
        f"Date: {message.get('date', '')}",
    ]
    attachment_count = 0
    for part in message.walk():
        if part.is_multipart():
            continue
        if part.get_content_disposition() == "attachment" or part.get_filename():
            attachment_count += 1
            continue
        if part.get_content_type() not in {"text/plain", "text/html"}:
            continue
        try:
            content = part.get_content()
        except (LookupError, UnicodeError):
            content = (part.get_payload(decode=True) or b"").decode(
                "utf-8",
                errors="replace",
            )
        text = content if isinstance(content, str) else str(content)
        if part.get_content_type() == "text/html":
            text = _html_to_text(text)
        lines.extend(text.splitlines())
    chunks = _chunks_from_numbered_lines(
        tuple(enumerate(lines, start=1)),
        locator_kind="message lines",
    )
    limitations = (
        (f"attachments_not_indexed:{attachment_count}",) if attachment_count else ()
    )
    status = "indexed" if chunks and not limitations else "partial"
    if not chunks:
        limitations = (*limitations, "no_extractable_text")
    return ExtractionResult(chunks, "eml", status, False, limitations)


def _ensure_vendor_import_path() -> None:
    component_root = Path(__file__).resolve().parents[1]
    candidates = (
        component_root / "vendor" / "modules",
        component_root.parent / "_shared" / "vendor" / "modules",
    )
    for candidate in candidates:
        if candidate.is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


def _run_local_ocr(image_bytes: bytes) -> tuple[str, tuple[str, ...], bool]:
    _ensure_vendor_import_path()
    try:
        from vera_ocr import extract_text_from_image_bytes
    except (ImportError, ModuleNotFoundError):
        return "", ("ocr_runtime_unavailable",), False
    result = extract_text_from_image_bytes(
        image_bytes,
        language="it",
        allow_model_download=False,
    )
    if result.network_used:
        raise ArchiveError("Local OCR unexpectedly reported network use.")
    warnings = tuple(str(value) for value in result.warnings)
    if result.status != "ok":
        return "", (f"ocr_{result.status}", *warnings), False
    return _normalize_text(result.text), warnings, True


def _render_pdf_page(path: Path, page_index: int) -> bytes:
    import fitz

    with fitz.open(path) as document:
        page = document.load_page(page_index)
        scale = 200.0 / 72.0
        rendered_pixels = int(page.rect.width * scale) * int(page.rect.height * scale)
        if rendered_pixels > MAX_IMAGE_TOTAL_PIXELS:
            raise ArchiveError("Rendered PDF page exceeds the OCR pixel limit.")
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
        return bytes(pixmap.tobytes("png"))


def _page_chunks(
    text: str,
    *,
    page_number: int,
    ordinal_start: int,
) -> tuple[ExtractedChunk, ...]:
    normalized = _normalize_text(text)
    if not normalized:
        return ()
    pieces = [
        normalized[offset : offset + MAX_CHUNK_CHARS]
        for offset in range(0, len(normalized), MAX_CHUNK_CHARS)
    ]
    return tuple(
        ExtractedChunk(
            ordinal=ordinal_start + index,
            locator_kind="page",
            locator_value=str(page_number),
            text=piece,
        )
        for index, piece in enumerate(pieces)
    )


def _extract_pdf(path: Path, *, enable_ocr: bool) -> ExtractionResult:
    if path.stat().st_size > MAX_PDF_BYTES:
        return ExtractionResult((), "pdf", "error", False, ("pdf_too_large",))
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted and not reader.decrypt(""):
            return ExtractionResult(
                (),
                "pdf",
                "partial",
                False,
                ("password_protected_pdf",),
            )
        total_pages = len(reader.pages)
    except (OSError, PyPdfError, RecursionError, TypeError, ValueError) as exc:
        return ExtractionResult(
            (),
            "pdf",
            "error",
            False,
            (f"pdf_open_failed:{type(exc).__name__}:{exc}",),
        )
    chunks: list[ExtractedChunk] = []
    limitations: list[str] = []
    needs_ocr = False
    used_ocr = False
    unresolved_ocr = False
    extracted_chars = 0
    page_limit = min(total_pages, MAX_PDF_PAGES)
    for page_index in range(page_limit):
        page_number = page_index + 1
        if extracted_chars >= MAX_PDF_TEXT_CHARS:
            limitations.append("pdf_text_character_limit_reached")
            break
        try:
            page = reader.pages[page_index]
            text = page.extract_text() or ""
        except (
            AttributeError,
            KeyError,
            PyPdfError,
            RecursionError,
            TypeError,
            ValueError,
        ):
            text = ""
            limitations.append(f"page_{page_number}_text_extraction_failed")
        if not _text_is_useful(text):
            needs_ocr = True
            native_text = _normalize_text(text)
            if enable_ocr:
                try:
                    image_bytes = _render_pdf_page(path, page_index)
                except (
                    ArchiveError,
                    ImportError,
                    ModuleNotFoundError,
                    OSError,
                    RuntimeError,
                    ValueError,
                ):
                    limitations.append(f"page_{page_number}_ocr_render_unavailable")
                else:
                    ocr_text, warnings, succeeded = _run_local_ocr(image_bytes)
                    limitations.extend(
                        f"page_{page_number}_{warning}" for warning in warnings
                    )
                    if succeeded and ocr_text:
                        text_parts = [native_text] if native_text else []
                        if ocr_text.casefold() not in native_text.casefold():
                            text_parts.append(ocr_text)
                        text = "\n".join(text_parts)
                        used_ocr = True
                        limitations.append(
                            f"page_{page_number}_ocr_text_requires_visual_confirmation"
                        )
            if not _text_is_useful(text):
                unresolved_ocr = True
                limitations.append(f"page_{page_number}_no_extractable_text")
        remaining_chars = MAX_PDF_TEXT_CHARS - extracted_chars
        if len(text) > remaining_chars:
            text = text[:remaining_chars]
            limitations.append("pdf_text_character_limit_reached")
        extracted_chars += len(text)
        chunks.extend(
            _page_chunks(
                text,
                page_number=page_number,
                ordinal_start=len(chunks),
            )
        )
    if total_pages > MAX_PDF_PAGES:
        limitations.append(f"pdf_page_limit_reached:{MAX_PDF_PAGES}/{total_pages}")
    method = "pdf_text+local_ocr" if used_ocr else "pdf_text"
    if not chunks:
        status = "partial"
    elif limitations:
        status = "partial"
    else:
        status = "indexed"
    return ExtractionResult(
        tuple(chunks),
        method,
        status,
        needs_ocr and unresolved_ocr,
        tuple(dict.fromkeys(limitations)),
    )


def _image_frames(path: Path) -> tuple[tuple[bytes, ...], bool]:
    from PIL import Image

    frames: list[bytes] = []
    total_pixels = 0
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                source_frame_count = max(
                    1,
                    int(getattr(image, "n_frames", 1)),
                )
                frame_count = min(
                    source_frame_count,
                    MAX_IMAGE_FRAMES,
                )
                for frame_index in range(frame_count):
                    image.seek(frame_index)
                    frame_pixels = int(image.width) * int(image.height)
                    total_pixels += frame_pixels
                    if total_pixels > MAX_IMAGE_TOTAL_PIXELS:
                        raise ArchiveError("Image frames exceed the OCR pixel limit.")
                    frame = image.convert("RGB")
                    buffer = io.BytesIO()
                    frame.save(buffer, format="PNG")
                    frames.append(buffer.getvalue())
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ArchiveError("Image exceeds the safe decoding limit.") from exc
    return tuple(frames), source_frame_count > MAX_IMAGE_FRAMES


def _extract_image(path: Path, *, enable_ocr: bool) -> ExtractionResult:
    if not enable_ocr:
        return ExtractionResult((), "image", "partial", True, ("ocr_disabled",))
    chunks: list[ExtractedChunk] = []
    limitations: list[str] = []
    unresolved_ocr = False
    try:
        frames, frames_truncated = _image_frames(path)
    except (ArchiveError, ImportError, ModuleNotFoundError, OSError, ValueError):
        return ExtractionResult(
            (),
            "image",
            "partial",
            True,
            ("image_frame_extraction_failed",),
        )
    if frames_truncated:
        limitations.append(f"image_frame_limit_reached:{MAX_IMAGE_FRAMES}")
    for page_number, image_bytes in enumerate(frames, start=1):
        text, warnings, succeeded = _run_local_ocr(image_bytes)
        limitations.extend(f"page_{page_number}_{warning}" for warning in warnings)
        if succeeded and text:
            limitations.append(
                f"page_{page_number}_ocr_text_requires_visual_confirmation"
            )
        else:
            unresolved_ocr = True
            limitations.append(f"page_{page_number}_no_extractable_text")
        chunks.extend(
            _page_chunks(
                text,
                page_number=page_number,
                ordinal_start=len(chunks),
            )
        )
    status = "indexed" if chunks and not limitations else "partial"
    return ExtractionResult(
        tuple(chunks),
        "local_ocr",
        status,
        unresolved_ocr or not bool(chunks),
        tuple(dict.fromkeys(limitations)),
    )


def _extract_document(path: Path, *, enable_ocr: bool) -> ExtractionResult:
    suffix = path.suffix.lower()
    try:
        if suffix in TEXT_SUFFIXES:
            return _extract_plain_text(path)
        if suffix in PDF_SUFFIXES:
            return _extract_pdf(path, enable_ocr=enable_ocr)
        if suffix in DOCX_SUFFIXES:
            return _extract_docx(path)
        if suffix in XLSX_SUFFIXES:
            return _extract_xlsx(path)
        if suffix in EMAIL_SUFFIXES:
            return _extract_eml(path)
        if suffix in IMAGE_SUFFIXES:
            return _extract_image(path, enable_ocr=enable_ocr)
    except (
        ArchiveError,
        AttributeError,
        ImportError,
        KeyError,
        ModuleNotFoundError,
        NotImplementedError,
        OSError,
        RecursionError,
        RuntimeError,
        TypeError,
        UnicodeError,
        ValueError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
    ) as exc:
        return ExtractionResult(
            (),
            suffix.removeprefix(".") or "unknown",
            "error",
            suffix in IMAGE_SUFFIXES,
            (f"extraction_failed:{type(exc).__name__}:{exc}",),
        )
    return ExtractionResult((), "unsupported", "error", False, ("unsupported",))


def _delete_document_chunks(
    connection: sqlite3.Connection,
    document_id: str,
) -> None:
    source_rows = connection.execute(
        "SELECT source_id FROM chunks WHERE document_id = ?",
        (document_id,),
    ).fetchall()
    source_ids = [str(row["source_id"]) for row in source_rows]
    if source_ids:
        connection.executemany(
            "DELETE FROM chunk_fts WHERE source_id = ?",
            ((source_id,) for source_id in source_ids),
        )
    connection.execute(
        "DELETE FROM chunks WHERE document_id = ?",
        (document_id,),
    )


def _replace_document(
    connection: sqlite3.Connection,
    *,
    item: DiscoveredFile,
    source_sha256: str,
    extraction: ExtractionResult,
    generation: int,
    indexed_at: str,
) -> None:
    document_id = _stable_id("doc", item.relative_path.casefold())
    _delete_document_chunks(connection, document_id)
    connection.execute(
        """
        INSERT INTO documents(
            document_id, scope_id, relative_path, extension, size_bytes,
            mtime_ns, sha256, extraction_method, status, needs_ocr,
            limitations_json, indexed_at, last_seen_generation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(document_id) DO UPDATE SET
            scope_id = excluded.scope_id,
            relative_path = excluded.relative_path,
            extension = excluded.extension,
            size_bytes = excluded.size_bytes,
            mtime_ns = excluded.mtime_ns,
            sha256 = excluded.sha256,
            extraction_method = excluded.extraction_method,
            status = excluded.status,
            needs_ocr = excluded.needs_ocr,
            limitations_json = excluded.limitations_json,
            indexed_at = excluded.indexed_at,
            last_seen_generation = excluded.last_seen_generation
        """,
        (
            document_id,
            item.scope_id,
            item.relative_path,
            item.path.suffix.lower(),
            item.size_bytes,
            item.mtime_ns,
            source_sha256,
            extraction.extraction_method,
            extraction.status,
            int(extraction.needs_ocr),
            json.dumps(extraction.limitations, ensure_ascii=False),
            indexed_at,
            generation,
        ),
    )
    for chunk in extraction.chunks:
        text_sha256 = _sha256_bytes(chunk.text.encode("utf-8"))
        source_id = _stable_id(
            "src",
            document_id,
            source_sha256,
            chunk.locator_kind,
            chunk.locator_value,
            str(chunk.ordinal),
            text_sha256,
        )
        connection.execute(
            """
            INSERT INTO chunks(
                source_id, document_id, ordinal, locator_kind, locator_value,
                text, text_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                document_id,
                chunk.ordinal,
                chunk.locator_kind,
                chunk.locator_value,
                chunk.text,
                text_sha256,
            ),
        )
        connection.execute(
            "INSERT INTO chunk_fts(source_id, text) VALUES (?, ?)",
            (source_id, chunk.text),
        )


def refresh_archive(
    *,
    rebuild: bool = False,
    enable_ocr: bool = False,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """Incrementally refresh the private local index without writing source files."""

    private_state = _state_dir(state_dir)
    stored_config = _load_config(private_state, validate_scope_roots=False)
    current_scopes = _discover_top_level_scopes(stored_config.archive_root)
    scopes_changed = current_scopes != stored_config.scopes
    if scopes_changed:
        config = ArchiveConfig(
            archive_root=stored_config.archive_root,
            scopes=current_scopes,
            configured_at=_now_iso(),
        )
        _write_private_json(_config_path(private_state), config.as_json())
    else:
        config = stored_config
    discovered, scan_issues = _discover_files(config)
    connection = _connect(private_state)
    indexed_at = _now_iso()
    try:
        previous_generation = int(_metadata_get(connection, "scan_generation") or "0")
        generation = previous_generation + 1
        fingerprint = _config_fingerprint(config)
        indexed_root = _metadata_get(connection, "archive_root")
        root_changed = indexed_root is not None and indexed_root != str(
            config.archive_root
        )
        if rebuild or root_changed:
            _clear_index(connection)
        existing = {
            str(row["relative_path"]): row
            for row in connection.execute("SELECT * FROM documents").fetchall()
        }
        _replace_scan_issues(connection, scan_issues)
        counts = {
            "discovered_files": len(discovered),
            "indexed_files": 0,
            "unchanged_files": 0,
            "metadata_only_files": 0,
            "removed_files": 0,
            "partial_files": 0,
            "failed_files": 0,
            "needs_ocr_files": 0,
            "unsupported_files": sum(
                issue.reason == "unsupported_extension" for issue in scan_issues
            ),
            "oversized_files": sum(
                issue.reason == "file_size_limit_exceeded" for issue in scan_issues
            ),
        }
        for item in discovered:
            previous = existing.get(item.relative_path)
            requires_reindex = previous is not None and (
                str(previous["status"]) == "error"
                or (enable_ocr and bool(previous["needs_ocr"]))
            )
            try:
                source_path = _resolve_source_file(
                    config.archive_root,
                    item.relative_path,
                )
                source_sha256 = _sha256_file(source_path)
            except (ArchiveError, OSError) as exc:
                extraction = ExtractionResult(
                    (),
                    item.path.suffix.lower().removeprefix(".") or "unknown",
                    "error",
                    item.path.suffix.lower() in IMAGE_SUFFIXES,
                    (f"source_unavailable_before_extraction:{exc}",),
                )
                _replace_document(
                    connection,
                    item=item,
                    source_sha256="",
                    extraction=extraction,
                    generation=generation,
                    indexed_at=indexed_at,
                )
                counts["indexed_files"] += 1
                counts["failed_files"] += 1
                counts["needs_ocr_files"] += int(extraction.needs_ocr)
                continue
            if (
                previous is not None
                and str(previous["sha256"]) == source_sha256
                and not requires_reindex
            ):
                connection.execute(
                    """
                    UPDATE documents
                    SET size_bytes = ?, mtime_ns = ?, last_seen_generation = ?
                    WHERE relative_path = ?
                    """,
                    (
                        item.size_bytes,
                        item.mtime_ns,
                        generation,
                        item.relative_path,
                    ),
                )
                metadata_unchanged = (
                    int(previous["size_bytes"]) == item.size_bytes
                    and int(previous["mtime_ns"]) == item.mtime_ns
                )
                count_key = (
                    "unchanged_files" if metadata_unchanged else "metadata_only_files"
                )
                counts[count_key] += 1
                counts["partial_files"] += int(previous["status"] == "partial")
                counts["failed_files"] += int(previous["status"] == "error")
                counts["needs_ocr_files"] += int(previous["needs_ocr"])
                continue

            extraction = _extract_document(source_path, enable_ocr=enable_ocr)
            try:
                post_metadata = source_path.stat(follow_symlinks=False)
                post_sha256 = _sha256_file(source_path)
            except (ArchiveError, OSError) as exc:
                extraction = ExtractionResult(
                    (),
                    extraction.extraction_method,
                    "error",
                    extraction.needs_ocr,
                    (
                        *extraction.limitations,
                        f"source_unavailable_after_extraction:{exc}",
                    ),
                )
                post_metadata = None
                post_sha256 = ""
            if (
                post_metadata is None
                or post_metadata.st_size != item.size_bytes
                or post_metadata.st_mtime_ns != item.mtime_ns
                or post_sha256 != source_sha256
            ):
                extraction = ExtractionResult(
                    (),
                    extraction.extraction_method,
                    "error",
                    extraction.needs_ocr,
                    (*extraction.limitations, "source_changed_during_refresh"),
                )
            _replace_document(
                connection,
                item=item,
                source_sha256=source_sha256,
                extraction=extraction,
                generation=generation,
                indexed_at=indexed_at,
            )
            counts["indexed_files"] += 1
            counts["partial_files"] += int(extraction.status == "partial")
            counts["failed_files"] += int(extraction.status == "error")
            counts["needs_ocr_files"] += int(extraction.needs_ocr)

        removed_rows = connection.execute(
            """
            SELECT document_id FROM documents
            WHERE last_seen_generation != ?
            """,
            (generation,),
        ).fetchall()
        for row in removed_rows:
            document_id = str(row["document_id"])
            _delete_document_chunks(connection, document_id)
            connection.execute(
                "DELETE FROM documents WHERE document_id = ?",
                (document_id,),
            )
        counts["removed_files"] = len(removed_rows)
        _metadata_set(connection, "scan_generation", str(generation))
        _metadata_set(connection, "last_refresh_at", indexed_at)
        _metadata_set(connection, "config_fingerprint", fingerprint)
        _metadata_set(connection, "archive_root", str(config.archive_root))
        _metadata_set(connection, "ocr_enabled_last_refresh", json.dumps(enable_ocr))
        connection.commit()
        document_count = int(
            connection.execute("SELECT COUNT(*) AS count FROM documents").fetchone()[
                "count"
            ]
        )
        chunk_count = int(
            connection.execute("SELECT COUNT(*) AS count FROM chunks").fetchone()[
                "count"
            ]
        )
        return {
            "status": "refreshed",
            "last_refresh_at": indexed_at,
            "rebuild": bool(rebuild or root_changed),
            "scope_configuration_changed": scopes_changed,
            "scopes": _scope_records(config),
            "ocr_enabled": enable_ocr,
            "document_count": document_count,
            "chunk_count": chunk_count,
            **counts,
            **_scan_issue_status(connection),
            **_document_issue_status(connection),
        }
    finally:
        connection.close()


def _scope_records(config: ArchiveConfig) -> list[dict[str, str]]:
    return [scope.as_json() for scope in config.scopes]


def _current_scope_view(config: ArchiveConfig) -> tuple[ArchiveConfig, bool]:
    current_scopes = _discover_top_level_scopes(config.archive_root)
    changed = current_scopes != config.scopes
    if not changed:
        return config, False
    return (
        ArchiveConfig(
            archive_root=config.archive_root,
            scopes=current_scopes,
            configured_at=config.configured_at,
        ),
        True,
    )


def studio_archive_status(*, state_dir: Path | None = None) -> dict[str, Any]:
    """Return configuration and derived-index status without changing state."""

    private_state = _state_dir(state_dir)
    config_path = _config_path(private_state)
    if not config_path.is_file():
        return {
            "configured": False,
            "document_count": 0,
            "chunk_count": 0,
            "last_refresh_at": None,
            "scopes": [],
            "needs_ocr_document_count": 0,
            "partial_document_count": 0,
            "failed_document_count": 0,
            "scan_issue_count": 0,
            "scan_issues": [],
            "scan_issues_truncated": False,
            "document_issue_count": 0,
            "document_issues": [],
            "document_issues_truncated": False,
        }
    stored_config = _load_config(private_state, validate_scope_roots=False)
    config, scopes_changed = _current_scope_view(stored_config)
    database_path = _database_path(private_state)
    if not database_path.is_file():
        return {
            "configured": True,
            "archive_root": str(config.archive_root),
            "document_count": 0,
            "chunk_count": 0,
            "last_refresh_at": None,
            "scopes": _scope_records(config),
            "index_requires_refresh": True,
            "scope_configuration_changed": scopes_changed,
            "needs_ocr_document_count": 0,
            "partial_document_count": 0,
            "failed_document_count": 0,
            "scan_issue_count": 0,
            "scan_issues": [],
            "scan_issues_truncated": False,
            "document_issue_count": 0,
            "document_issues": [],
            "document_issues_truncated": False,
        }
    connection = _connect(private_state, readonly=True)
    try:
        document_count = int(
            connection.execute("SELECT COUNT(*) AS count FROM documents").fetchone()[
                "count"
            ]
        )
        chunk_count = int(
            connection.execute("SELECT COUNT(*) AS count FROM chunks").fetchone()[
                "count"
            ]
        )
        fingerprint_matches = _metadata_get(
            connection, "config_fingerprint"
        ) == _config_fingerprint(stored_config)
        return {
            "configured": True,
            "archive_root": str(config.archive_root),
            "document_count": document_count,
            "chunk_count": chunk_count,
            "last_refresh_at": _metadata_get(connection, "last_refresh_at"),
            "scopes": _scope_records(config),
            "index_requires_refresh": scopes_changed or not fingerprint_matches,
            "scope_configuration_changed": scopes_changed,
            "needs_ocr_document_count": int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM documents WHERE needs_ocr = 1"
                ).fetchone()["count"]
            ),
            "partial_document_count": int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM documents WHERE status = 'partial'"
                ).fetchone()["count"]
            ),
            "failed_document_count": int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM documents WHERE status = 'error'"
                ).fetchone()["count"]
            ),
            **_scan_issue_status(connection),
            **_document_issue_status(connection),
        }
    finally:
        connection.close()


def _fts_query(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArchiveError("Search query must be non-empty.")
    if len(value) > 500:
        raise ArchiveError("Search query must contain at most 500 characters.")
    tokens: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"[^\W_]+", value, flags=re.UNICODE):
        token = match.group(0)
        key = token.casefold()
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        tokens.append(token)
        if len(tokens) >= MAX_SEARCH_TOKENS:
            break
    if not tokens:
        raise ArchiveError("Search query contains no searchable terms.")
    return " OR ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)


def _citation(relative_path: str, locator_kind: str, locator_value: str) -> str:
    if locator_kind == "page":
        return f"{relative_path}, p. {locator_value}"
    return f"{relative_path}, {locator_kind} {locator_value}"


def _decode_limitations(value: str) -> list[str]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return ["invalid_stored_extraction_limitations"]
    if not isinstance(payload, list) or not all(
        isinstance(item, str) for item in payload
    ):
        return ["invalid_stored_extraction_limitations"]
    return payload


def search_archive(
    query: str,
    *,
    scope_id: str,
    limit: int = 10,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """Search one exact configured scope, or ``all`` when explicitly requested."""

    if not 1 <= int(limit) <= 20:
        raise ArchiveError("Search limit must be between 1 and 20.")
    private_state = _state_dir(state_dir)
    config = _load_config(private_state, validate_scope_roots=False)
    _, scopes_changed = _current_scope_view(config)
    if scopes_changed:
        raise ArchiveError(
            "Top-level archive scopes changed; refresh before searching."
        )
    allowed_scopes = {scope.scope_id for scope in config.scopes}
    if scope_id != "all" and scope_id not in allowed_scopes:
        raise ArchiveError("Search scope is not configured.")
    expression = _fts_query(query)
    connection = _connect(private_state, readonly=True)
    try:
        if _metadata_get(connection, "config_fingerprint") != _config_fingerprint(
            config
        ):
            raise ArchiveError(
                "Archive configuration changed; refresh before searching."
            )
        if scope_id == "all":
            rows = connection.execute(
                """
                SELECT
                    c.source_id,
                    c.document_id,
                    c.ordinal,
                    c.locator_kind,
                    c.locator_value,
                    d.scope_id,
                    d.relative_path,
                    d.sha256,
                    d.extraction_method,
                    d.status,
                    d.needs_ocr,
                    d.limitations_json,
                    d.indexed_at,
                    bm25(chunk_fts) AS score,
                    snippet(chunk_fts, 1, '[[', ']]', ' … ', 28) AS snippet
                FROM chunk_fts
                JOIN chunks AS c ON c.source_id = chunk_fts.source_id
                JOIN documents AS d ON d.document_id = c.document_id
                WHERE chunk_fts MATCH ?
                ORDER BY score, d.relative_path, c.ordinal
                LIMIT ?
                """,
                (expression, int(limit)),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT
                    c.source_id,
                    c.document_id,
                    c.ordinal,
                    c.locator_kind,
                    c.locator_value,
                    d.scope_id,
                    d.relative_path,
                    d.sha256,
                    d.extraction_method,
                    d.status,
                    d.needs_ocr,
                    d.limitations_json,
                    d.indexed_at,
                    bm25(chunk_fts) AS score,
                    snippet(chunk_fts, 1, '[[', ']]', ' … ', 28) AS snippet
                FROM chunk_fts
                JOIN chunks AS c ON c.source_id = chunk_fts.source_id
                JOIN documents AS d ON d.document_id = c.document_id
                WHERE chunk_fts MATCH ?
                  AND d.scope_id = ?
                ORDER BY score, d.relative_path, c.ordinal
                LIMIT ?
                """,
                (expression, scope_id, int(limit)),
            ).fetchall()
        results = [
            {
                "rank": index,
                "source_id": str(row["source_id"]),
                "document_id": str(row["document_id"]),
                "scope_id": str(row["scope_id"]),
                "relative_path": str(row["relative_path"]),
                "locator_kind": str(row["locator_kind"]),
                "locator_value": str(row["locator_value"]),
                "citation": _citation(
                    str(row["relative_path"]),
                    str(row["locator_kind"]),
                    str(row["locator_value"]),
                ),
                "snippet": str(row["snippet"]),
                "extraction_method": str(row["extraction_method"]),
                "document_status": str(row["status"]),
                "needs_ocr": bool(row["needs_ocr"]),
                "limitations": _decode_limitations(str(row["limitations_json"])),
                "source_sha256": str(row["sha256"]),
                "indexed_at": str(row["indexed_at"]),
                "score": float(row["score"]),
                "verification_required": True,
            }
            for index, row in enumerate(rows, start=1)
        ]
        return {
            "query": query,
            "scope_id": scope_id,
            "result_count": len(results),
            "results": results,
            **_scan_issue_status(
                connection,
                scope_id=None if scope_id == "all" else scope_id,
            ),
            **_document_issue_status(
                connection,
                scope_id=None if scope_id == "all" else scope_id,
            ),
        }
    finally:
        connection.close()


def open_archive_source(
    source_id: str,
    *,
    context_chunks: int = 0,
    state_dir: Path | None = None,
) -> dict[str, Any]:
    """Open one indexed source ID after re-verifying the current source bytes."""

    if not isinstance(source_id, str) or not re.fullmatch(
        r"src_[0-9a-f]{24}", source_id
    ):
        raise ArchiveError("Source ID is invalid.")
    if not 0 <= int(context_chunks) <= 2:
        raise ArchiveError("context_chunks must be between 0 and 2.")
    private_state = _state_dir(state_dir)
    config = _load_config(private_state, validate_scope_roots=False)
    _, scopes_changed = _current_scope_view(config)
    if scopes_changed:
        raise ArchiveError(
            "Top-level archive scopes changed; refresh before opening sources."
        )
    connection = _connect(private_state, readonly=True)
    try:
        if _metadata_get(connection, "config_fingerprint") != _config_fingerprint(
            config
        ):
            raise ArchiveError(
                "Archive configuration changed; refresh before opening sources."
            )
        row = connection.execute(
            """
            SELECT c.*, d.relative_path, d.sha256, d.scope_id,
                   d.extraction_method, d.status, d.needs_ocr,
                   d.limitations_json, d.indexed_at
            FROM chunks AS c
            JOIN documents AS d ON d.document_id = c.document_id
            WHERE c.source_id = ?
            """,
            (source_id,),
        ).fetchone()
        if row is None:
            raise ArchiveError("Source ID is not present in the current index.")
        source_path = _resolve_source_file(
            config.archive_root, str(row["relative_path"])
        )
        current_sha256 = _sha256_file(source_path)
        if current_sha256 != str(row["sha256"]):
            raise SourceChangedError(
                "The source file changed after indexing. Refresh before using this "
                "citation; rebuild if the ordinary refresh still reports it as stale."
            )
        context = int(context_chunks)
        context_rows = connection.execute(
            """
            SELECT source_id, ordinal, locator_kind, locator_value, text
            FROM chunks
            WHERE document_id = ? AND ordinal BETWEEN ? AND ?
            ORDER BY ordinal
            """,
            (
                str(row["document_id"]),
                max(0, int(row["ordinal"]) - context),
                int(row["ordinal"]) + context,
            ),
        ).fetchall()
        fragments = [
            {
                "source_id": str(context_row["source_id"]),
                "ordinal": int(context_row["ordinal"]),
                "locator_kind": str(context_row["locator_kind"]),
                "locator_value": str(context_row["locator_value"]),
                "citation": _citation(
                    str(row["relative_path"]),
                    str(context_row["locator_kind"]),
                    str(context_row["locator_value"]),
                ),
                "text": str(context_row["text"])[:MAX_OPEN_CHARS],
            }
            for context_row in context_rows
        ]
        return {
            "source_id": source_id,
            "document_id": str(row["document_id"]),
            "scope_id": str(row["scope_id"]),
            "relative_path": str(row["relative_path"]),
            "locator_kind": str(row["locator_kind"]),
            "locator_value": str(row["locator_value"]),
            "citation": _citation(
                str(row["relative_path"]),
                str(row["locator_kind"]),
                str(row["locator_value"]),
            ),
            "source_sha256": str(row["sha256"]),
            "source_verified": True,
            "extraction_method": str(row["extraction_method"]),
            "document_status": str(row["status"]),
            "needs_ocr": bool(row["needs_ocr"]),
            "limitations": _decode_limitations(str(row["limitations_json"])),
            "indexed_at": str(row["indexed_at"]),
            "fragments": fragments,
            **_scan_issue_status(connection, scope_id=str(row["scope_id"])),
            **_document_issue_status(connection, scope_id=str(row["scope_id"])),
        }
    finally:
        connection.close()
