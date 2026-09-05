"""Deterministic workflow controls for professional-studio websites."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import struct
import tarfile
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from jsonschema import Draft202012Validator, FormatChecker

__all__ = [
    "initialize_workspace",
    "package_website",
    "prepare_run",
    "record_external_delivery",
    "record_quality_assessment",
    "record_review",
    "record_sites_delivery",
    "record_site_brief",
    "prepare_sites_binding",
    "validate_run",
    "validate_site",
]

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = PLUGIN_ROOT / "schemas"
WORKSPACE_MANIFEST = ".presenza-digitale-studio.json"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER_PATTERN = re.compile(r"\b(?:TODO|FIXME|lorem ipsum)\b", re.IGNORECASE)
CSS_URL_PATTERN = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
CSS_IMPORT_PATTERN = re.compile(
    r"@import\s+(?:url\(\s*)?['\"]([^'\"]+)['\"]\s*\)?", re.IGNORECASE
)
JS_IMPORT_PATTERN = re.compile(
    r"(?:import|export)\s+(?:[^'\"]*?\s+from\s+)?['\"]([^'\"]+)['\"]|"
    r"import\(\s*['\"]([^'\"]+)['\"]\s*\)"
)
PREVIEW_ROBOTS_TOKENS = {"noindex", "nofollow", "noarchive"}
ACTIVE_EMBED_TAGS = {"embed", "iframe", "object"}
ACTIVE_EXTERNAL_TAGS = {"form", "script", *ACTIVE_EMBED_TAGS}
PASSIVE_EXTERNAL_TAGS = {"audio", "img", "link", "source", "video"}
VALIDATOR_VERSION = 3
SECRET_QUERY_PATTERN = re.compile(r"(?i)(?:token|code|key|secret|signature|password)=")
REVIEW_SCOPES = {
    "identity_and_claims",
    "responsive_preview",
    "publication_destination",
}
SITES_DELIVERY_FIELDS = {
    "schema_version",
    "provider",
    "kind",
    "destination",
    "project_id",
    "commit_sha",
    "archive_path",
    "archive_sha256",
    "binding_member",
    "site_payload_member",
    "site_payload_sha256",
    "site_version_id",
    "deployment_id",
    "deployment_status",
    "access_level",
    "access_approved_by_user",
    "deployed_url",
    "browser_review",
    "site_digest",
    "validation_digest",
    "quality_assessment_digest",
    "reviews_digest",
    "package_digest",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest_payload(payload: Any) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"JSON path must be a regular non-symlink file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(serialized)
        temp_path = Path(handle.name)
    temp_path.chmod(0o600)
    temp_path.replace(path)


def _validate_schema(payload: dict[str, Any], schema_name: str) -> None:
    schema = _load_json(SCHEMA_ROOT / schema_name)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        details = "; ".join(
            f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
            for error in errors
        )
        raise ValueError(f"Invalid {schema_name}: {details}")


def _require_nonempty(value: str, label: str) -> str:
    """Return stripped text or reject an unusable audit field."""

    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{label} must be non-empty")
    return stripped


def _inside_git_workspace(path: Path) -> bool:
    return any((candidate / ".git").exists() for candidate in (path, *path.parents))


def _assert_private_workspace(path: Path) -> Path:
    expanded = path.expanduser().absolute()
    if any(candidate.is_symlink() for candidate in (expanded, *expanded.parents)):
        raise ValueError("Workspace path must not contain a symlink")
    resolved = expanded.resolve()
    if resolved == Path(resolved.anchor) or resolved == Path.home().resolve():
        raise ValueError("Workspace must not be a filesystem root or home directory")
    if _inside_git_workspace(resolved):
        raise ValueError("Workspace must be outside a Git repository")
    parts = tuple(part.lower() for part in resolved.parts)
    if "static" in parts and "shared" in parts:
        raise ValueError("Workspace must not be inside a published static/shared path")
    return resolved


def initialize_workspace(
    workspace: Path,
    *,
    workspace_id: str,
    owner: str,
    retention_owner: str,
) -> Path:
    """Initialize or verify one owner-controlled website workspace."""

    workspace_id = _require_nonempty(workspace_id, "workspace_id")
    owner = _require_nonempty(owner, "owner")
    retention_owner = _require_nonempty(retention_owner, "retention_owner")
    root = _assert_private_workspace(workspace)
    if root.exists() and not root.is_dir():
        raise ValueError("Workspace must be a directory, not a file or symlink")
    if root.exists() and not (root / WORKSPACE_MANIFEST).exists():
        try:
            next(root.iterdir())
        except StopIteration:
            pass
        else:
            raise ValueError(
                "Existing workspace directory must be empty or already initialized"
            )
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    manifest_path = root / WORKSPACE_MANIFEST
    expected_identity = {
        "schema_version": 1,
        "workspace_id": workspace_id,
        "owner": owner,
        "retention_owner": retention_owner,
    }
    if manifest_path.exists():
        current = _load_json(manifest_path)
        for key, value in expected_identity.items():
            if current.get(key) != value:
                raise ValueError(f"Workspace identity mismatch for {key}")
        return manifest_path
    _write_json(
        manifest_path,
        {**expected_identity, "initialized_at": _utc_now()},
    )
    (root / "runs").mkdir(mode=0o700, exist_ok=True)
    return manifest_path


def _workspace_root(path: Path) -> Path:
    root = _assert_private_workspace(path)
    if not (root / WORKSPACE_MANIFEST).is_file():
        raise ValueError("Workspace is not initialized")
    return root


def _source_snapshot_name(source_id: str, source_path: Path) -> str:
    suffix = "".join(source_path.suffixes)[-24:]
    return f"{source_id}{suffix}"


def _portable_relative_path(path: Path, root: Path) -> str:
    """Serialize a bounded relative path consistently across operating systems."""

    return path.relative_to(root).as_posix()


def prepare_run(workspace: Path, intake_path: Path) -> Path:
    """Validate intake, snapshot selected files, and create one immutable run."""

    root = _workspace_root(workspace)
    intake = _load_json(intake_path.expanduser().resolve())
    _validate_schema(intake, "website_intake.schema.json")
    confirmed_facts = intake["confirmed_facts"]
    source_ids = [item["id"] for item in intake["selected_files"]]
    source_ids.extend(item["id"] for item in confirmed_facts)
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Evidence IDs must be unique")

    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:10]
    )
    runs_root = root / "runs"
    staging = runs_root / f".{run_id}.staging"
    run_dir = runs_root / run_id
    staging.mkdir(parents=False, mode=0o700)
    try:
        inputs_dir = staging / "inputs"
        inputs_dir.mkdir(mode=0o700)
        source_register: list[dict[str, Any]] = []
        for item in intake["selected_files"]:
            source_path = Path(item["path"]).expanduser().resolve()
            if source_path.is_symlink() or not source_path.is_file():
                raise ValueError(
                    f"Selected source must be a regular non-symlink file: {source_path}"
                )
            target = inputs_dir / _source_snapshot_name(item["id"], source_path)
            shutil.copyfile(source_path, target)
            target.chmod(0o400)
            source_register.append(
                {
                    "id": item["id"],
                    "role": item["role"],
                    "origin": "selected_file",
                    "approved_for_website_use": item["approved_for_website_use"],
                    "original_path": str(source_path),
                    "snapshot_path": _portable_relative_path(target, staging),
                    "bytes": target.stat().st_size,
                    "sha256": _sha256_file(target),
                }
            )
        for fact in confirmed_facts:
            target = inputs_dir / f"{fact['id']}.confirmed-fact.json"
            snapshot = {
                "schema_version": 1,
                "id": fact["id"],
                "statement": fact["statement"],
                "confirmed_by": fact["confirmed_by"],
                "confirmed_by_user": True,
                "approved_for_website_use": fact["approved_for_website_use"],
            }
            _write_json(target, snapshot)
            target.chmod(0o400)
            source_register.append(
                {
                    "id": fact["id"],
                    "role": "confirmed_chat_fact",
                    "origin": "confirmed_chat",
                    "approved_for_website_use": fact["approved_for_website_use"],
                    "original_path": None,
                    "snapshot_path": _portable_relative_path(target, staging),
                    "bytes": target.stat().st_size,
                    "sha256": _sha256_file(target),
                }
            )
        _write_json(staging / "run_intake.json", intake)
        _write_json(
            staging / "source_register.json",
            {"schema_version": 1, "sources": source_register},
        )
        intake_digest = _digest_payload(
            {"intake": intake, "source_register": source_register}
        )
        _write_json(
            staging / "run_state.json",
            {
                "schema_version": 1,
                "run_id": run_id,
                "created_at": _utc_now(),
                "status": "prepared",
                "intake_digest": intake_digest,
                "current_site_digest": None,
                "brief_digest": None,
                "packages": {},
                "deliveries": [],
                "sites_bindings": {},
            },
        )
        for relative in ("work/site", "work/sites-project", "reviews", "packages"):
            (staging / relative).mkdir(parents=True, mode=0o700)
        staging.replace(run_dir)
    except (OSError, ValueError, json.JSONDecodeError):
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return run_dir


def _run_file(run_dir: Path, name: str) -> Path:
    root = run_dir.expanduser().resolve()
    state_path = root / "run_state.json"
    if state_path.is_symlink() or not state_path.is_file():
        raise ValueError("Run directory is not prepared")
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Run path must be relative and bounded: {name}")
    candidate = root
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink():
            raise ValueError(f"Run path contains a symlink: {name}")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Run path escapes the run directory: {name}") from exc
    return resolved


def _bound_run_path(run_dir: Path, relative: str) -> Path:
    """Resolve a recorded run-relative path without permitting traversal."""

    return _run_file(run_dir, relative)


def _verified_intake_and_sources(
    run_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Rehash selected evidence because later gates depend on exact bytes."""

    intake = _load_json(_run_file(run_dir, "run_intake.json"))
    _validate_schema(intake, "website_intake.schema.json")
    register = _load_json(_run_file(run_dir, "source_register.json"))
    if register.get("schema_version") != 1 or not isinstance(
        register.get("sources"), list
    ):
        raise ValueError("Invalid source register")
    expected_files = {item["id"]: item for item in intake["selected_files"]}
    expected_facts = {item["id"]: item for item in intake["confirmed_facts"]}
    expected_ids = [*expected_files, *expected_facts]
    if len(set(expected_ids)) != len(expected_ids):
        raise ValueError("Evidence IDs must be unique")
    expected = {**expected_files, **expected_facts}
    recorded = {str(item.get("id")): item for item in register["sources"]}
    if set(recorded) != set(expected) or len(recorded) != len(register["sources"]):
        raise ValueError("Source register does not match selected evidence")
    for source_id, selected in expected.items():
        item = recorded[source_id]
        if source_id in expected_files:
            if item.get("role") != selected["role"]:
                raise ValueError(f"Source role changed for {source_id}")
            if item.get("origin") != "selected_file":
                raise ValueError(f"Source origin changed for {source_id}")
            if item.get("approved_for_website_use") is not True:
                raise ValueError(f"Source website-use approval changed for {source_id}")
            original = str(Path(selected["path"]).expanduser().resolve())
            if item.get("original_path") != original:
                raise ValueError(f"Original source path changed for {source_id}")
        else:
            if item.get("role") != "confirmed_chat_fact":
                raise ValueError(f"Confirmed fact role changed for {source_id}")
            if item.get("origin") != "confirmed_chat":
                raise ValueError(f"Confirmed fact origin changed for {source_id}")
            if item.get("approved_for_website_use") is not True:
                raise ValueError(
                    f"Confirmed fact website-use approval changed for {source_id}"
                )
            if item.get("original_path") is not None:
                raise ValueError(
                    f"Confirmed fact has an unexpected source path: {source_id}"
                )
        snapshot_relative = item.get("snapshot_path")
        if not isinstance(snapshot_relative, str) or not snapshot_relative.startswith(
            "inputs/"
        ):
            raise ValueError(f"Invalid snapshot path for {source_id}")
        snapshot = _bound_run_path(run_dir, snapshot_relative)
        if snapshot.is_symlink() or not snapshot.is_file():
            raise ValueError(f"Evidence snapshot is missing or unsafe: {source_id}")
        if item.get("bytes") != snapshot.stat().st_size:
            raise ValueError(f"Evidence snapshot byte count changed: {source_id}")
        if item.get("sha256") != _sha256_file(snapshot):
            raise ValueError(f"Evidence snapshot hash changed: {source_id}")
        if source_id in expected_facts:
            expected_snapshot = {
                "schema_version": 1,
                "id": source_id,
                "statement": selected["statement"],
                "confirmed_by": selected["confirmed_by"],
                "confirmed_by_user": True,
                "approved_for_website_use": True,
            }
            if _load_json(snapshot) != expected_snapshot:
                raise ValueError(f"Confirmed fact snapshot changed: {source_id}")
    intake_digest = _digest_payload(
        {"intake": intake, "source_register": register["sources"]}
    )
    state = _load_json(_run_file(run_dir, "run_state.json"))
    if state.get("intake_digest") != intake_digest:
        raise ValueError("Run intake digest is stale")
    return intake, register, intake_digest


def _brief_source_ids(brief: dict[str, Any]) -> set[str]:
    referenced: set[str] = set()
    for fact in brief["observed_facts"]:
        referenced.update(fact["source_ids"])
    for field in brief["studio_profile"]:
        referenced.update(field["evidence_ids"])
    for claim in brief["claims"]:
        referenced.update(claim["evidence_ids"])
    return referenced


def _validate_source_use_plan(
    brief: dict[str, Any],
    known_sources: set[str],
) -> None:
    """Require exact source-ID coverage without deciding semantic relevance.

    Exact ID closure is mechanically verifiable and audit-relevant. The model
    remains responsible for each source's purpose and post-brief access mode.
    """

    planned_ids = [str(item["source_id"]) for item in brief["source_use_plan"]]
    if len(planned_ids) != len(set(planned_ids)):
        raise ValueError("Source use plan contains duplicate source IDs")
    planned = set(planned_ids)
    unknown = sorted(planned - known_sources)
    if unknown:
        raise ValueError(
            "Source use plan references unknown source IDs: " + ", ".join(unknown)
        )
    missing = sorted(known_sources - planned)
    if missing:
        raise ValueError("Source use plan is missing source IDs: " + ", ".join(missing))


def _verified_brief(run_dir: Path) -> dict[str, Any]:
    """Verify that the current brief is intact and bound to current evidence."""

    intake, register, intake_digest = _verified_intake_and_sources(run_dir)
    record = _load_json(_run_file(run_dir, "site_brief_record.json"))
    brief = record.get("brief")
    if not isinstance(brief, dict):
        raise ValueError("Site brief record is invalid")
    _validate_schema(brief, "site_brief.schema.json")
    brief_digest = _digest_payload(brief)
    if record.get("brief_digest") != brief_digest:
        raise ValueError("Site brief digest is invalid")
    if record.get("intake_digest") != intake_digest:
        raise ValueError("Site brief is bound to stale evidence")
    if brief["mode"] != intake["mode"]:
        raise ValueError("Brief mode does not match intake mode")
    known_sources = {str(item["id"]) for item in register["sources"]}
    _validate_source_use_plan(brief, known_sources)
    referenced = _brief_source_ids(brief)
    if not referenced:
        raise ValueError(
            "Site brief must reference at least one selected evidence source"
        )
    unknown = sorted(referenced - known_sources)
    if unknown:
        raise ValueError(f"Brief references unknown source IDs: {', '.join(unknown)}")
    state = _load_json(_run_file(run_dir, "run_state.json"))
    if state.get("brief_digest") != brief_digest:
        raise ValueError("Run state brief digest is stale")
    return record


def record_site_brief(
    run_dir: Path,
    brief_path: Path,
    *,
    provider: str,
    model: str,
    recorded_by: str,
) -> Path:
    """Validate and bind one model-led website brief to prepared evidence."""

    provider = _require_nonempty(provider, "provider")
    model = _require_nonempty(model, "model")
    recorded_by = _require_nonempty(recorded_by, "recorded_by")
    brief = _load_json(brief_path.expanduser().resolve())
    _validate_schema(brief, "site_brief.schema.json")
    intake, register, intake_digest = _verified_intake_and_sources(run_dir)
    if brief["mode"] != intake["mode"]:
        raise ValueError("Brief mode does not match intake mode")
    known_sources = {str(item["id"]) for item in register["sources"]}
    _validate_source_use_plan(brief, known_sources)
    referenced = _brief_source_ids(brief)
    if not referenced:
        raise ValueError(
            "Site brief must reference at least one selected evidence source"
        )
    unknown = sorted(referenced - known_sources)
    if unknown:
        raise ValueError(f"Brief references unknown source IDs: {', '.join(unknown)}")
    state = _load_json(_run_file(run_dir, "run_state.json"))
    record = {
        "schema_version": 1,
        "brief": brief,
        "brief_digest": _digest_payload(brief),
        "intake_digest": intake_digest,
        "provenance": {
            "provider": provider,
            "model": model,
            "recorded_by": recorded_by,
            "recorded_at": _utc_now(),
        },
    }
    output = _run_file(run_dir, "site_brief_record.json")
    _write_json(output, record)
    state["brief_digest"] = record["brief_digest"]
    state["quality_assessment_digest"] = None
    state["packages"] = {}
    state["deliveries"] = []
    state["sites_bindings"] = {}
    state["status"] = "brief_ready"
    _write_json(_run_file(run_dir, "run_state.json"), state)
    return output


class _PageAudit(HTMLParser):
    """Collect mechanically inspectable HTML properties."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_lang: str | None = None
        self.title_depth = 0
        self.title_text: list[str] = []
        self.h1_count = 0
        self.ids: list[str] = []
        self.references: list[tuple[str, str]] = []
        self.fragment_references: list[str] = []
        self.inline_styles: list[str] = []
        self.style_depth = 0
        self.style_text: list[str] = []
        self.images_missing_alt = 0
        self.viewport = False
        self.robots_tokens: set[str] = set()
        self.prohibited_elements: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "html":
            self.html_lang = values.get("lang")
        if tag == "title":
            self.title_depth += 1
        if tag == "style":
            self.style_depth += 1
        if tag == "h1":
            self.h1_count += 1
        if values.get("id"):
            self.ids.append(str(values["id"]))
        if tag == "img" and "alt" not in values:
            self.images_missing_alt += 1
        if tag == "form" or tag in ACTIVE_EMBED_TAGS:
            self.prohibited_elements.append(tag)
        if tag == "meta" and str(values.get("name", "")).lower() == "viewport":
            self.viewport = bool(values.get("content"))
        if tag == "meta" and str(values.get("name", "")).lower() == "robots":
            content = str(values.get("content", "")).lower()
            self.robots_tokens.update(
                token for token in re.split(r"[\s,]+", content) if token
            )
        if values.get("style"):
            self.inline_styles.append(str(values["style"]))
        reference_attributes = {
            "a": ("href",),
            "audio": ("src",),
            "embed": ("src",),
            "form": ("action",),
            "iframe": ("src",),
            "img": ("src",),
            "input": ("src",),
            "link": ("href",),
            "object": ("data",),
            "script": ("src",),
            "source": ("src",),
            "video": ("src", "poster"),
        }
        for attr_name in reference_attributes.get(tag, ()):
            if not values.get(attr_name):
                continue
            value = str(values[attr_name])
            self.references.append((tag, value))
            if tag == "a" and value.startswith("#") and len(value) > 1:
                self.fragment_references.append(value[1:])
        if tag in {"img", "source"} and values.get("srcset"):
            for candidate in str(values["srcset"]).split(","):
                value = candidate.strip().split(maxsplit=1)[0]
                if value:
                    self.references.append((tag, value))

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self.title_depth:
            self.title_depth -= 1
        if tag == "style" and self.style_depth:
            self.style_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.title_depth:
            self.title_text.append(data)
        if self.style_depth:
            self.style_text.append(data)


def _css_references(text: str) -> list[str]:
    """Extract mechanically declared CSS imports and URL references."""

    references = [match[1].strip() for match in CSS_URL_PATTERN.findall(text)]
    references.extend(match.strip() for match in CSS_IMPORT_PATTERN.findall(text))
    return [value for value in references if value and not value.startswith("#")]


def _javascript_references(text: str) -> list[str]:
    """Extract statically declared JavaScript module references."""

    references: list[str] = []
    for match in JS_IMPORT_PATTERN.findall(text):
        value = next((part for part in match if part), "").strip()
        if value:
            references.append(value)
    return references


def _site_inventory(site_dir: Path) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for path in sorted(site_dir.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Site package contains a symlink: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"Site package contains a non-regular file: {path}")
        inventory.append(
            {
                "path": path.relative_to(site_dir).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    return inventory


def _site_digest(site_dir: Path) -> tuple[str, list[dict[str, Any]]]:
    inventory = _site_inventory(site_dir)
    return _digest_payload(inventory), inventory


def _local_target(site_dir: Path, page: Path, value: str) -> Path | None:
    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    if scheme in {"http", "https", "mailto", "tel", "data"} or value.startswith("//"):
        return None
    raw_path = unquote(parsed.path)
    if not raw_path:
        return page
    pure = (
        PurePosixPath(raw_path.lstrip("/"))
        if raw_path.startswith("/")
        else PurePosixPath(raw_path)
    )
    if ".." in pure.parts:
        raise ValueError(f"Local reference escapes site root: {value}")
    target = site_dir / pure if raw_path.startswith("/") else page.parent / pure
    target = target.resolve()
    try:
        target.relative_to(site_dir)
    except ValueError as exc:
        raise ValueError(f"Local reference escapes site root: {value}") from exc
    if raw_path.endswith("/"):
        target /= "index.html"
    elif not target.suffix and not target.exists():
        target = target / "index.html"
    return target


def _html_ids(path: Path) -> set[str]:
    parser = _PageAudit()
    parser.feed(path.read_text(encoding="utf-8"))
    return set(parser.ids)


def _check_local_reference(
    site_dir: Path,
    source: Path,
    value: str,
    *,
    tag: str,
    check_fragment: bool = False,
) -> str | None:
    """Enforce mechanically verifiable URL and local-file safety rules."""

    scheme = urlparse(value).scheme.lower()
    if tag == "form" or tag in ACTIVE_EMBED_TAGS:
        return f"{tag} is outside the informational website scope"
    if scheme in {"javascript", "vbscript", "file"}:
        return f"unsafe {scheme} reference: {value}"
    if scheme == "data" and tag not in {"img", "source", "style"}:
        return f"unsafe data reference for {tag}: {value}"
    if scheme == "https" and tag == "script":
        return f"external active script requires a separately reviewed integration: {value}"
    if scheme == "http":
        return f"insecure http reference: {value}"
    if scheme and scheme not in {"https", "mailto", "tel", "data"}:
        return f"unsupported URL scheme {scheme}: {value}"
    if scheme in {"mailto", "tel"} and tag != "a":
        return f"unsupported {scheme} reference for {tag}: {value}"
    if value.startswith("//") and tag == "script":
        return f"external active script requires a separately reviewed integration: {value}"
    try:
        target = _local_target(site_dir, source, value)
    except ValueError as exc:
        return str(exc)
    if target is None:
        return None
    if not target.exists():
        return f"missing local target: {value}"
    fragment = unquote(urlparse(value).fragment)
    if check_fragment and fragment and target.suffix.lower() in {".html", ".htm"}:
        if fragment not in _html_ids(target):
            return f"missing fragment target: {value}"
    return None


def _validation_digest(report: dict[str, Any]) -> str:
    payload = dict(report)
    payload.pop("validation_digest", None)
    payload.pop("validated_at", None)
    return _digest_payload(payload)


def validate_site(run_dir: Path) -> Path:
    """Run deterministic HTML and package-integrity checks."""

    brief = _verified_brief(run_dir)
    _, register, intake_digest = _verified_intake_and_sources(run_dir)
    site_dir = _run_file(run_dir, "work/site")
    index_path = site_dir / "index.html"
    if not index_path.is_file():
        raise ValueError("Site must contain work/site/index.html")
    site_digest, inventory = _site_digest(site_dir)
    errors: list[str] = []
    warnings: list[str] = []
    pages: list[dict[str, Any]] = []
    html_paths = sorted(site_dir.rglob("*.html"))
    for path in html_paths:
        text = path.read_text(encoding="utf-8")
        parser = _PageAudit()
        parser.feed(text)
        relative = path.relative_to(site_dir).as_posix()
        page_errors: list[str] = []
        if not parser.html_lang:
            page_errors.append("missing html lang")
        if not "".join(parser.title_text).strip():
            page_errors.append("missing non-empty title")
        if not parser.viewport:
            page_errors.append("missing viewport metadata")
        if parser.h1_count != 1:
            page_errors.append(f"expected one h1, found {parser.h1_count}")
        if parser.images_missing_alt:
            page_errors.append(
                f"{parser.images_missing_alt} image(s) missing alt attribute"
            )
        duplicate_ids = sorted(
            {item for item in parser.ids if parser.ids.count(item) > 1}
        )
        if duplicate_ids:
            page_errors.append(f"duplicate ids: {', '.join(duplicate_ids)}")
        missing_fragments = sorted(set(parser.fragment_references) - set(parser.ids))
        if missing_fragments:
            page_errors.append(
                f"missing fragment targets: {', '.join(missing_fragments)}"
            )
        if PLACEHOLDER_PATTERN.search(text):
            page_errors.append("placeholder text remains")
        for tag in sorted(set(parser.prohibited_elements)):
            page_errors.append(f"{tag} is outside the informational website scope")
        external_assets: list[str] = []
        for tag, value in parser.references:
            if tag == "form" or tag in ACTIVE_EMBED_TAGS:
                continue
            scheme = urlparse(value).scheme.lower()
            if (
                scheme == "https" or value.startswith("//")
            ) and tag in PASSIVE_EXTERNAL_TAGS:
                external_assets.append(value)
                continue
            error = _check_local_reference(
                site_dir,
                path,
                value,
                tag=tag,
                check_fragment=tag == "a",
            )
            if error:
                page_errors.append(error)
        for value in _css_references(
            "\n".join((*parser.inline_styles, *parser.style_text))
        ):
            if urlparse(value).scheme.lower() == "https":
                external_assets.append(value)
                continue
            error = _check_local_reference(site_dir, path, value, tag="style")
            if error:
                page_errors.append(error)
        if external_assets:
            warnings.append(
                f"{relative}: {len(external_assets)} external asset reference(s)"
            )
        errors.extend(f"{relative}: {message}" for message in page_errors)
        pages.append(
            {
                "path": relative,
                "h1_count": parser.h1_count,
                "robots_tokens": sorted(parser.robots_tokens),
                "external_assets": external_assets,
                "errors": page_errors,
            }
        )
    for path in sorted(site_dir.rglob("*.css")):
        relative = path.relative_to(site_dir).as_posix()
        for value in _css_references(path.read_text(encoding="utf-8")):
            if urlparse(value).scheme.lower() == "https":
                warnings.append(f"{relative}: external asset reference: {value}")
                continue
            error = _check_local_reference(site_dir, path, value, tag="style")
            if error:
                errors.append(f"{relative}: {error}")
    for pattern in ("*.js", "*.mjs"):
        for path in sorted(site_dir.rglob(pattern)):
            relative = path.relative_to(site_dir).as_posix()
            for value in _javascript_references(path.read_text(encoding="utf-8")):
                error = _check_local_reference(site_dir, path, value, tag="script")
                if error:
                    errors.append(f"{relative}: {error}")
    report: dict[str, Any] = {
        "schema_version": 1,
        "validator_version": VALIDATOR_VERSION,
        "validated_at": _utc_now(),
        "intake_digest": intake_digest,
        "source_register_digest": _digest_payload(register),
        "brief_digest": brief["brief_digest"],
        "site_digest": site_digest,
        "inventory": inventory,
        "status": "ready" if not errors else "blocked",
        "errors": errors,
        "warnings": warnings,
        "pages": pages,
    }
    report["validation_digest"] = _validation_digest(report)
    output = _run_file(run_dir, "site_validation.json")
    _write_json(output, report)
    state_path = _run_file(run_dir, "run_state.json")
    state = _load_json(state_path)
    if (
        state.get("current_site_digest") != site_digest
        or state.get("validation_digest") != report["validation_digest"]
        or state.get("brief_digest") != brief["brief_digest"]
    ):
        state["packages"] = {}
        state["deliveries"] = []
        state["sites_bindings"] = {}
        state["quality_assessment_digest"] = None
    state["current_site_digest"] = site_digest
    state["validation_digest"] = report["validation_digest"]
    state["status"] = "site_validated" if not errors else "blocked"
    _write_json(state_path, state)
    return output


def _verified_validation(run_dir: Path) -> dict[str, Any]:
    """Recompute every mechanical dependency of the saved validation record."""

    brief = _verified_brief(run_dir)
    _, register, intake_digest = _verified_intake_and_sources(run_dir)
    validation = _load_json(_run_file(run_dir, "site_validation.json"))
    if validation.get("validator_version") != VALIDATOR_VERSION:
        raise ValueError("Site validation was created by a stale validator")
    if validation.get("validation_digest") != _validation_digest(validation):
        raise ValueError("Site validation digest is invalid")
    site_digest, inventory = _site_digest(_run_file(run_dir, "work/site"))
    if validation.get("site_digest") != site_digest:
        raise ValueError("Site validation is stale")
    if validation.get("inventory") != inventory:
        raise ValueError("Site validation inventory is stale")
    expected = {
        "intake_digest": intake_digest,
        "source_register_digest": _digest_payload(register),
        "brief_digest": brief["brief_digest"],
    }
    for key, value in expected.items():
        if validation.get(key) != value:
            raise ValueError(f"Site validation {key} is stale")
    state = _load_json(_run_file(run_dir, "run_state.json"))
    if state.get("current_site_digest") != site_digest:
        raise ValueError("Run state site digest is stale")
    if state.get("validation_digest") != validation["validation_digest"]:
        raise ValueError("Run state validation digest is stale")
    return validation


def _png_dimensions(path: Path) -> tuple[int, int]:
    """Read PNG dimensions because viewport evidence is a mechanical contract."""

    with path.open("rb") as handle:
        header = handle.read(24)
    if (
        len(header) != 24
        or header[:8] != b"\x89PNG\r\n\x1a\n"
        or header[12:16] != b"IHDR"
    ):
        raise ValueError(f"Browser evidence must be a valid PNG: {path}")
    width, height = struct.unpack(">II", header[16:24])
    if width < 1 or height < 1:
        raise ValueError(f"Browser evidence has invalid dimensions: {path}")
    return width, height


def _verify_viewport_evidence(
    run_dir: Path,
    viewports: list[dict[str, Any]],
    *,
    prefix: str,
) -> None:
    """Bind claimed viewport reviews to exact, correctly sized PNG evidence."""

    seen_paths: set[str] = set()
    for viewport in viewports:
        relative = viewport["screenshot_path"]
        if not relative.startswith(prefix) or relative in seen_paths:
            raise ValueError(
                "Viewport screenshot paths must be unique and correctly scoped"
            )
        seen_paths.add(relative)
        screenshot = _bound_run_path(run_dir, relative)
        if screenshot.is_symlink() or not screenshot.is_file():
            raise ValueError(f"Viewport screenshot is missing or unsafe: {relative}")
        if _sha256_file(screenshot) != viewport["screenshot_sha256"]:
            raise ValueError(f"Viewport screenshot hash is stale: {relative}")
        image_width, image_height = _png_dimensions(screenshot)
        if image_width != viewport["width"] or image_height < viewport["height"]:
            raise ValueError(
                f"Viewport screenshot dimensions do not cover the claimed review: {relative}"
            )


def record_quality_assessment(
    run_dir: Path,
    assessment_path: Path,
    *,
    provider: str,
    model: str,
    recorded_by: str,
) -> Path:
    """Record model-led review of the exact rendered responsive site."""

    provider = _require_nonempty(provider, "provider")
    model = _require_nonempty(model, "model")
    recorded_by = _require_nonempty(recorded_by, "recorded_by")
    assessment = _load_json(assessment_path.expanduser().resolve())
    _validate_schema(assessment, "quality_assessment.schema.json")
    _verify_viewport_evidence(
        run_dir,
        assessment["viewports"],
        prefix="reviews/browser/",
    )
    validation = _verified_validation(run_dir)
    if validation["status"] != "ready":
        raise ValueError("Mechanical site validation is blocked")
    if assessment["site_digest"] != validation["site_digest"]:
        raise ValueError("Assessment site digest is stale")
    if assessment["validation_digest"] != validation["validation_digest"]:
        raise ValueError("Assessment validation digest is stale")
    record = {
        "schema_version": 1,
        "assessment": assessment,
        "assessment_digest": _digest_payload(assessment),
        "provenance": {
            "provider": provider,
            "model": model,
            "recorded_by": recorded_by,
            "recorded_at": _utc_now(),
        },
    }
    output = _run_file(run_dir, "quality_assessment_record.json")
    _write_json(output, record)
    state_path = _run_file(run_dir, "run_state.json")
    state = _load_json(state_path)
    if state.get("quality_assessment_digest") != record["assessment_digest"]:
        state["packages"] = {}
        state["deliveries"] = []
        state["sites_bindings"] = {}
    state["quality_assessment_digest"] = record["assessment_digest"]
    state["status"] = (
        "quality_ready" if assessment["verdict"] == "ready" else assessment["verdict"]
    )
    _write_json(state_path, state)
    return output


def _verified_quality(run_dir: Path, validation: dict[str, Any]) -> dict[str, Any]:
    quality = _load_json(_run_file(run_dir, "quality_assessment_record.json"))
    assessment = quality.get("assessment")
    if not isinstance(assessment, dict):
        raise ValueError("Rendered quality assessment record is invalid")
    _validate_schema(assessment, "quality_assessment.schema.json")
    _verify_viewport_evidence(
        run_dir,
        assessment["viewports"],
        prefix="reviews/browser/",
    )
    if quality.get("assessment_digest") != _digest_payload(assessment):
        raise ValueError("Rendered quality assessment digest is invalid")
    state = _load_json(_run_file(run_dir, "run_state.json"))
    if state.get("quality_assessment_digest") != quality["assessment_digest"]:
        raise ValueError("Run state quality assessment digest is stale")
    if assessment["site_digest"] != validation["site_digest"]:
        raise ValueError("Rendered quality assessment is stale")
    if assessment["validation_digest"] != validation["validation_digest"]:
        raise ValueError("Rendered quality assessment validation is stale")
    return quality


def _current_ready_site(
    run_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    validation = _verified_validation(run_dir)
    quality = _verified_quality(run_dir, validation)
    brief = _verified_brief(run_dir)
    if validation["status"] != "ready":
        raise ValueError("Mechanical site validation is not ready")
    if quality["assessment"]["verdict"] != "ready":
        raise ValueError("Rendered quality assessment is not ready")
    return validation, quality, brief


def record_review(
    run_dir: Path,
    *,
    scope: str,
    decision: str,
    reviewer: str,
) -> Path:
    """Record a professional decision bound to the current site bytes."""

    if scope not in REVIEW_SCOPES:
        raise ValueError(f"Unknown review scope: {scope}")
    if decision not in {"accepted", "returned", "rejected"}:
        raise ValueError(f"Unknown review decision: {decision}")
    reviewer = _require_nonempty(reviewer, "reviewer")
    validation, quality, brief = _current_ready_site(run_dir)
    review_path = _run_file(run_dir, "reviews/review_log.json")
    payload = (
        _load_json(review_path)
        if review_path.exists()
        else {"schema_version": 1, "events": []}
    )
    event = {
        "scope": scope,
        "decision": decision,
        "reviewer": reviewer,
        "confirmed_by_user": True,
        "recorded_at": _utc_now(),
        "site_digest": validation["site_digest"],
        "validation_digest": validation["validation_digest"],
        "quality_assessment_digest": quality["assessment_digest"],
        "brief_digest": brief["brief_digest"],
    }
    event["event_digest"] = _digest_payload(event)
    payload["events"].append(event)
    _write_json(review_path, payload)
    state_path = _run_file(run_dir, "run_state.json")
    state = _load_json(state_path)
    state.get("packages", {}).pop("release", None)
    state["deliveries"] = [
        item for item in state.get("deliveries", []) if item.get("kind") != "release"
    ]
    state.get("sites_bindings", {}).pop("release", None)
    state["status"] = "review_recorded"
    _write_json(state_path, state)
    return review_path


def _review_events(run_dir: Path) -> list[dict[str, Any]]:
    review_path = _run_file(run_dir, "reviews/review_log.json")
    if not review_path.exists():
        return []
    payload = _load_json(review_path)
    if payload.get("schema_version") != 1 or not isinstance(
        payload.get("events"), list
    ):
        raise ValueError("Invalid review log")
    for event in payload["events"]:
        if not isinstance(event, dict):
            raise ValueError("Invalid review event")
        recorded_digest = event.get("event_digest")
        digest_payload = dict(event)
        digest_payload.pop("event_digest", None)
        if recorded_digest != _digest_payload(digest_payload):
            raise ValueError("Review event digest is invalid")
        if event.get("scope") not in REVIEW_SCOPES:
            raise ValueError("Review event scope is invalid")
        if event.get("decision") not in {"accepted", "returned", "rejected"}:
            raise ValueError("Review event decision is invalid")
        if event.get("confirmed_by_user") is not True:
            raise ValueError("Review event lacks user confirmation")
    return list(payload["events"])


def _current_reviews(
    run_dir: Path,
    validation: dict[str, Any],
    quality: dict[str, Any],
    brief: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], str]:
    latest: dict[str, dict[str, Any]] = {}
    for event in _review_events(run_dir):
        if (
            event.get("site_digest") == validation["site_digest"]
            and event.get("validation_digest") == validation["validation_digest"]
            and event.get("quality_assessment_digest") == quality["assessment_digest"]
            and event.get("brief_digest") == brief["brief_digest"]
        ):
            latest[event["scope"]] = event
    accepted = {
        scope: event
        for scope, event in latest.items()
        if event["decision"] == "accepted"
    }
    ordered = {scope: accepted[scope] for scope in sorted(accepted)}
    return accepted, _digest_payload(ordered)


def _selected_route(run_dir: Path, route: str) -> dict[str, Any]:
    intake, _, _ = _verified_intake_and_sources(run_dir)
    return dict(intake["external_routes"][route])


def _manifest_digest(manifest: dict[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("package_digest", None)
    return _digest_payload(payload)


def _verify_package_files(manifest_path: Path) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    expected_fields = {
        "schema_version",
        "kind",
        "created_at",
        "chain_digest",
        "intake_digest",
        "brief_digest",
        "site_digest",
        "validation_digest",
        "quality_assessment_digest",
        "reviews_digest",
        "files",
        "package_digest",
    }
    if set(manifest) != expected_fields or manifest.get("schema_version") != 1:
        raise ValueError("Package manifest shape or schema version is invalid")
    if manifest.get("kind") not in {"preview", "release"}:
        raise ValueError("Package manifest kind is invalid")
    if manifest.get("package_digest") != _manifest_digest(manifest):
        raise ValueError("Package manifest digest is invalid")
    package_site = manifest_path.parent / "site"
    inventory = _site_inventory(package_site)
    if manifest.get("files") != inventory:
        raise ValueError("Package files differ from the recorded manifest")
    if manifest.get("site_digest") != _digest_payload(inventory):
        raise ValueError("Package site digest is invalid")
    return manifest


def _verify_current_package(
    run_dir: Path,
    kind: str,
) -> tuple[dict[str, Any], Path]:
    state = _load_json(_run_file(run_dir, "run_state.json"))
    package = state.get("packages", {}).get(kind)
    if not isinstance(package, dict):
        raise ValueError(f"No current {kind} package exists")
    manifest_relative = package.get("manifest")
    if not isinstance(manifest_relative, str):
        raise ValueError(f"Current {kind} package path is invalid")
    manifest_path = _bound_run_path(run_dir, manifest_relative)
    if not manifest_path.is_file():
        raise ValueError(f"Current {kind} package manifest is missing")
    manifest = _verify_package_files(manifest_path)
    validation, quality, brief = _current_ready_site(run_dir)
    expected = {
        "kind": kind,
        "intake_digest": validation["intake_digest"],
        "brief_digest": brief["brief_digest"],
        "site_digest": validation["site_digest"],
        "validation_digest": validation["validation_digest"],
        "quality_assessment_digest": quality["assessment_digest"],
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"Current {kind} package {key} is stale")
    expected_reviews_digest: str | None = None
    if kind == "release":
        accepted, reviews_digest = _current_reviews(run_dir, validation, quality, brief)
        if set(accepted) != REVIEW_SCOPES:
            raise ValueError("Release reviews are no longer current")
        if manifest.get("reviews_digest") != reviews_digest:
            raise ValueError("Release package review digest is stale")
        expected_reviews_digest = reviews_digest
    elif manifest.get("reviews_digest") is not None:
        raise ValueError("Preview package must not carry release reviews")
    expected_chain_digest = _digest_payload(
        {
            "kind": kind,
            **expected,
            "reviews_digest": expected_reviews_digest,
        }
    )
    if manifest.get("chain_digest") != expected_chain_digest:
        raise ValueError(f"Current {kind} package chain digest is invalid")
    if package.get("site_digest") != manifest["site_digest"]:
        raise ValueError("Run state package site digest is stale")
    if package.get("package_digest") != manifest["package_digest"]:
        raise ValueError("Run state package digest is stale")
    if package.get("chain_digest") != manifest["chain_digest"]:
        raise ValueError("Run state package chain digest is stale")
    return manifest, manifest_path


def _status_after_packaging(state: dict[str, Any], kind: str) -> str:
    """Preserve a current delivery state during idempotent packaging retries."""

    packages = state.get("packages", {})
    deliveries = state.get("deliveries", [])
    release = packages.get("release", {})
    if any(
        item.get("kind") == "release"
        and item.get("package_digest") == release.get("package_digest")
        for item in deliveries
        if isinstance(item, dict)
    ):
        return "published"
    preview = packages.get("preview", {})
    if any(
        item.get("kind") == "preview"
        and item.get("package_digest") == preview.get("package_digest")
        for item in deliveries
        if isinstance(item, dict)
    ):
        return "preview_published"
    return "preview_ready" if kind == "preview" else "release_ready"


def package_website(run_dir: Path, *, kind: str) -> Path:
    """Package exact preview or release bytes after required gates."""

    if kind not in {"preview", "release"}:
        raise ValueError("Package kind must be preview or release")
    validation, quality, brief = _current_ready_site(run_dir)
    site_digest = validation["site_digest"]
    reviews_digest: str | None = None
    if kind == "preview":
        route = _selected_route(run_dir, "preview_publication")
        if not route["selected"] or not route["approved_by_user"]:
            raise ValueError("Preview publication route was not selected")
        pages_without_noindex = [
            page["path"]
            for page in validation["pages"]
            if not PREVIEW_ROBOTS_TOKENS.issubset(set(page["robots_tokens"]))
        ]
        if pages_without_noindex:
            raise ValueError(
                "Preview pages must include noindex, nofollow and noarchive: "
                + ", ".join(pages_without_noindex)
            )
    else:
        pages_with_preview_robots = [
            page["path"]
            for page in validation["pages"]
            if PREVIEW_ROBOTS_TOKENS.intersection(set(page["robots_tokens"]))
        ]
        if pages_with_preview_robots:
            raise ValueError(
                "Release pages must remove preview robots directives: "
                + ", ".join(pages_with_preview_robots)
            )
        accepted, reviews_digest = _current_reviews(run_dir, validation, quality, brief)
        missing = REVIEW_SCOPES - set(accepted)
        if missing:
            raise ValueError("Release reviews missing: " + ", ".join(sorted(missing)))

    chain_digest = _digest_payload(
        {
            "kind": kind,
            "intake_digest": validation["intake_digest"],
            "brief_digest": brief["brief_digest"],
            "site_digest": site_digest,
            "validation_digest": validation["validation_digest"],
            "quality_assessment_digest": quality["assessment_digest"],
            "reviews_digest": reviews_digest,
        }
    )
    package_dir = _run_file(run_dir, f"packages/{kind}-{chain_digest[:16]}")
    manifest_path = package_dir / "package_manifest.json"
    if package_dir.exists():
        if not manifest_path.is_file():
            raise ValueError(f"Existing package is incomplete: {package_dir}")
        manifest = _verify_package_files(manifest_path)
        expected_manifest = {
            "kind": kind,
            "chain_digest": chain_digest,
            "intake_digest": validation["intake_digest"],
            "brief_digest": brief["brief_digest"],
            "site_digest": site_digest,
            "validation_digest": validation["validation_digest"],
            "quality_assessment_digest": quality["assessment_digest"],
            "reviews_digest": reviews_digest,
            "files": validation["inventory"],
        }
        for key, value in expected_manifest.items():
            if manifest.get(key) != value:
                raise ValueError(
                    f"Existing package {key} differs from the current review chain"
                )
        state_path = _run_file(run_dir, "run_state.json")
        state = _load_json(state_path)
        state["packages"][kind] = {
            "manifest": str(manifest_path.relative_to(run_dir.resolve())),
            "site_digest": site_digest,
            "package_digest": manifest["package_digest"],
            "chain_digest": chain_digest,
        }
        state["status"] = _status_after_packaging(state, kind)
        _write_json(state_path, state)
        return manifest_path
    staging_dir = package_dir.parent / f".{package_dir.name}.{uuid.uuid4().hex}.staging"
    staging_dir.mkdir(mode=0o700)
    try:
        output_site = staging_dir / "site"
        shutil.copytree(_run_file(run_dir, "work/site"), output_site)
        inventory = _site_inventory(output_site)
        if inventory != validation["inventory"]:
            raise ValueError("Working site changed while the package was being created")
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "kind": kind,
            "created_at": _utc_now(),
            "chain_digest": chain_digest,
            "intake_digest": validation["intake_digest"],
            "brief_digest": brief["brief_digest"],
            "site_digest": site_digest,
            "validation_digest": validation["validation_digest"],
            "quality_assessment_digest": quality["assessment_digest"],
            "reviews_digest": reviews_digest,
            "files": inventory,
        }
        manifest["package_digest"] = _digest_payload(manifest)
        _write_json(staging_dir / "package_manifest.json", manifest)
        staging_dir.replace(package_dir)
    except (OSError, ValueError, json.JSONDecodeError):
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        raise
    state_path = _run_file(run_dir, "run_state.json")
    state = _load_json(state_path)
    state["packages"][kind] = {
        "manifest": str(manifest_path.relative_to(run_dir.resolve())),
        "site_digest": site_digest,
        "package_digest": manifest["package_digest"],
        "chain_digest": chain_digest,
    }
    state["status"] = _status_after_packaging(state, kind)
    _write_json(state_path, state)
    return manifest_path


def record_external_delivery(
    run_dir: Path,
    *,
    kind: str,
    destination: str,
    visible_receipt: str,
    confirmed_by: str,
) -> Path:
    """Bind visible preview or publication evidence to an exact package."""

    if kind not in {"preview", "release"}:
        raise ValueError("Delivery kind must be preview or release")
    destination = _require_nonempty(destination, "destination")
    visible_receipt = _require_nonempty(visible_receipt, "visible_receipt")
    confirmed_by = _require_nonempty(confirmed_by, "confirmed_by")
    if SECRET_QUERY_PATTERN.search(visible_receipt):
        raise ValueError("Visible receipt must not contain a credential or secret")
    route_name = "preview_publication" if kind == "preview" else "final_publication"
    route = _selected_route(run_dir, route_name)
    if not route["selected"] or not route["approved_by_user"]:
        raise ValueError(f"{route_name} route was not selected")
    if destination != route["destination"]:
        raise ValueError("Delivery destination does not match the selected route")
    if route["provider"] == "sites":
        raise ValueError("Sites delivery must use record_sites_delivery")
    state_path = _run_file(run_dir, "run_state.json")
    state = _load_json(state_path)
    manifest, _ = _verify_current_package(run_dir, kind)
    receipt = {
        "schema_version": 1,
        "provider": route["provider"],
        "kind": kind,
        "destination": destination,
        "visible_receipt": visible_receipt,
        "confirmed_by": confirmed_by,
        "confirmed_by_user": True,
        "recorded_at": _utc_now(),
        "intake_digest": manifest["intake_digest"],
        "brief_digest": manifest["brief_digest"],
        "site_digest": manifest["site_digest"],
        "validation_digest": manifest["validation_digest"],
        "quality_assessment_digest": manifest["quality_assessment_digest"],
        "reviews_digest": manifest["reviews_digest"],
        "package_digest": manifest["package_digest"],
    }
    receipt["receipt_digest"] = _digest_payload(receipt)
    state["deliveries"].append(receipt)
    state["status"] = "published" if kind == "release" else "preview_published"
    _write_json(state_path, state)
    output = _run_file(run_dir, f"{kind}_delivery_receipt.json")
    _write_json(output, receipt)
    return output


def _write_site_payload_zip(site_dir: Path, output: Path) -> str:
    """Create a deterministic ZIP of the approved site for archive binding."""

    inventory = _site_inventory(site_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=output.parent,
        prefix=f".{output.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for item in inventory:
                info = zipfile.ZipInfo(item["path"], date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, (site_dir / item["path"]).read_bytes())
        temporary.chmod(0o600)
        temporary.replace(output)
    except (OSError, ValueError, zipfile.BadZipFile):
        if temporary.exists():
            temporary.unlink()
        raise
    return _sha256_file(output)


def _site_payload_inventory(payload: bytes) -> list[dict[str, Any]]:
    """Inventory a nested site ZIP without extracting untrusted paths."""

    inventory: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names: set[str] = set()
            for info in sorted(archive.infolist(), key=lambda item: item.filename):
                pure = PurePosixPath(info.filename)
                file_type = (info.external_attr >> 16) & 0o170000
                if (
                    info.is_dir()
                    or info.filename in names
                    or pure.is_absolute()
                    or ".." in pure.parts
                    or file_type == 0o120000
                ):
                    raise ValueError(
                        "Sites payload contains an unsafe or duplicate member"
                    )
                names.add(info.filename)
                content = archive.read(info)
                inventory.append(
                    {
                        "path": info.filename,
                        "bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                )
    except zipfile.BadZipFile as exc:
        raise ValueError("Sites payload is not a valid ZIP") from exc
    return inventory


def prepare_sites_binding(run_dir: Path, *, kind: str) -> Path:
    """Write the exact Vera release chain into the run-owned Sites project."""

    if kind not in {"preview", "release"}:
        raise ValueError("Sites binding kind must be preview or release")
    route_name = "preview_publication" if kind == "preview" else "final_publication"
    route = _selected_route(run_dir, route_name)
    if (
        not route["selected"]
        or not route["approved_by_user"]
        or route["provider"] != "sites"
    ):
        raise ValueError(f"{route_name} is not an approved Sites route")
    manifest, manifest_path = _verify_current_package(run_dir, kind)
    sites_project = _run_file(run_dir, "work/sites-project")
    hosting_path = sites_project / ".openai/hosting.json"
    if hosting_path.is_symlink() or not hosting_path.is_file():
        raise ValueError("Sites project must contain .openai/hosting.json")
    hosting = _load_json(hosting_path)
    project_id = hosting.get("project_id")
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("Sites hosting metadata must contain project_id")
    payload_internal_path = manifest_path.parent / "vera-site-package.zip"
    payload_project_path = sites_project / ".openai/vera-site-package.zip"
    payload_sha256 = _write_site_payload_zip(
        manifest_path.parent / "site",
        payload_internal_path,
    )
    shutil.copyfile(payload_internal_path, payload_project_path)
    payload_project_path.chmod(0o600)
    binding: dict[str, Any] = {
        "schema_version": 1,
        "provider": "sites",
        "kind": kind,
        "run_id": _load_json(_run_file(run_dir, "run_state.json"))["run_id"],
        "project_id": project_id.strip(),
        "intake_digest": manifest["intake_digest"],
        "brief_digest": manifest["brief_digest"],
        "site_digest": manifest["site_digest"],
        "validation_digest": manifest["validation_digest"],
        "quality_assessment_digest": manifest["quality_assessment_digest"],
        "reviews_digest": manifest["reviews_digest"],
        "package_digest": manifest["package_digest"],
        "package_manifest": str(manifest_path.relative_to(run_dir.resolve())),
        "site_payload_member": "dist/.openai/vera-site-package.zip",
        "site_payload_sha256": payload_sha256,
        "created_at": _utc_now(),
    }
    binding["binding_digest"] = _digest_payload(binding)
    internal_path = manifest_path.parent / "sites_binding.json"
    project_path = sites_project / ".openai/vera-release-binding.json"
    _write_json(internal_path, binding)
    _write_json(project_path, binding)
    state_path = _run_file(run_dir, "run_state.json")
    state = _load_json(state_path)
    state.setdefault("sites_bindings", {})[kind] = {
        "path": str(internal_path.relative_to(run_dir.resolve())),
        "binding_digest": binding["binding_digest"],
        "project_id": project_id.strip(),
        "package_digest": manifest["package_digest"],
        "site_payload_path": str(payload_internal_path.relative_to(run_dir.resolve())),
        "site_payload_sha256": payload_sha256,
    }
    state["status"] = f"{kind}_sites_binding_ready"
    _write_json(state_path, state)
    return project_path


def _verified_sites_binding(
    run_dir: Path,
    kind: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    state = _load_json(_run_file(run_dir, "run_state.json"))
    entry = state.get("sites_bindings", {}).get(kind)
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
        raise ValueError(f"No current {kind} Sites binding exists")
    binding_path = _bound_run_path(run_dir, entry["path"])
    binding = _load_json(binding_path)
    recorded_digest = binding.get("binding_digest")
    digest_payload = dict(binding)
    digest_payload.pop("binding_digest", None)
    if recorded_digest != _digest_payload(digest_payload):
        raise ValueError("Sites binding digest is invalid")
    expected = {
        "provider": "sites",
        "kind": kind,
        "intake_digest": manifest["intake_digest"],
        "brief_digest": manifest["brief_digest"],
        "site_digest": manifest["site_digest"],
        "validation_digest": manifest["validation_digest"],
        "quality_assessment_digest": manifest["quality_assessment_digest"],
        "reviews_digest": manifest["reviews_digest"],
        "package_digest": manifest["package_digest"],
    }
    for key, value in expected.items():
        if binding.get(key) != value:
            raise ValueError(f"Sites binding {key} is stale")
    if entry.get("binding_digest") != recorded_digest:
        raise ValueError("Run state Sites binding digest is stale")
    if entry.get("project_id") != binding.get("project_id"):
        raise ValueError("Run state Sites project ID is stale")
    if entry.get("package_digest") != manifest["package_digest"]:
        raise ValueError("Run state Sites package digest is stale")
    payload_relative = entry.get("site_payload_path")
    if not isinstance(payload_relative, str):
        raise ValueError("Run state Sites payload path is invalid")
    payload_path = _bound_run_path(run_dir, payload_relative)
    if payload_path.is_symlink() or not payload_path.is_file():
        raise ValueError("Sites payload is missing or unsafe")
    payload_sha256 = _sha256_file(payload_path)
    if payload_sha256 != entry.get("site_payload_sha256"):
        raise ValueError("Run state Sites payload hash is stale")
    if payload_sha256 != binding.get("site_payload_sha256"):
        raise ValueError("Sites binding payload hash is stale")
    if binding.get("site_payload_member") != "dist/.openai/vera-site-package.zip":
        raise ValueError("Sites binding payload member is invalid")
    if _site_payload_inventory(payload_path.read_bytes()) != manifest["files"]:
        raise ValueError("Sites payload files differ from the approved package")
    return binding


def _archive_member_bytes(
    archive_path: Path,
    member_name: str,
    *,
    max_size: int = 1024 * 1024,
) -> bytes:
    """Read one declared archive member without extracting untrusted paths."""

    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as archive:
            matches = [
                info for info in archive.infolist() if info.filename == member_name
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"Sites archive must contain exactly one {member_name}"
                )
            info = matches[0]
            file_type = (info.external_attr >> 16) & 0o170000
            if info.is_dir() or file_type == 0o120000 or info.file_size > max_size:
                raise ValueError("Sites archive member is unsafe or unexpectedly large")
            return archive.read(info)
    try:
        with tarfile.open(archive_path, mode="r:*") as archive:
            matches = [
                member for member in archive.getmembers() if member.name == member_name
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"Sites archive must contain exactly one {member_name}"
                )
            member = matches[0]
            if not member.isfile() or member.size > max_size:
                raise ValueError("Sites archive member is unsafe or unexpectedly large")
            handle = archive.extractfile(member)
            if handle is None:
                raise ValueError("Sites archive member is unreadable")
            return handle.read()
    except tarfile.TarError as exc:
        raise ValueError("Sites deployment archive is not a supported archive") from exc


def record_sites_delivery(
    run_dir: Path,
    receipt_path: Path,
    *,
    confirmed_by: str,
) -> Path:
    """Bind a succeeded Sites version and deployment to the current Vera package."""

    confirmed_by = _require_nonempty(confirmed_by, "confirmed_by")
    supplied = _load_json(receipt_path.expanduser().resolve())
    _validate_schema(supplied, "sites_delivery.schema.json")
    kind = supplied["kind"]
    route_name = "preview_publication" if kind == "preview" else "final_publication"
    route = _selected_route(run_dir, route_name)
    if (
        not route["selected"]
        or not route["approved_by_user"]
        or route["provider"] != "sites"
    ):
        raise ValueError(f"{route_name} is not an approved Sites route")
    if supplied["destination"] != route["destination"]:
        raise ValueError("Sites destination does not match the selected route")
    manifest, _ = _verify_current_package(run_dir, kind)
    binding = _verified_sites_binding(run_dir, kind, manifest)
    expected = {
        "project_id": binding["project_id"],
        "site_digest": manifest["site_digest"],
        "validation_digest": manifest["validation_digest"],
        "quality_assessment_digest": manifest["quality_assessment_digest"],
        "reviews_digest": manifest["reviews_digest"],
        "package_digest": manifest["package_digest"],
    }
    for key, value in expected.items():
        if supplied[key] != value:
            raise ValueError(f"Sites receipt {key} does not match the current package")
    if set(supplied["commit_sha"]) == {"0"}:
        raise ValueError("Sites commit SHA is invalid")
    deployed_url = _require_nonempty(supplied["deployed_url"], "deployed_url")
    if SECRET_QUERY_PATTERN.search(deployed_url):
        raise ValueError("Deployed URL must not expose a credential or secret")
    browser_review = supplied["browser_review"]
    if (
        browser_review["reviewed_url"] != deployed_url
        or browser_review["deployment_id"] != supplied["deployment_id"]
    ):
        raise ValueError("Sites browser review is not bound to this deployment")
    _verify_viewport_evidence(
        run_dir,
        browser_review["viewports"],
        prefix="reviews/sites/",
    )
    archive_path = Path(supplied["archive_path"]).expanduser().resolve()
    if archive_path.is_symlink() or not archive_path.is_file():
        raise ValueError("Sites deployment archive is missing or unsafe")
    if _sha256_file(archive_path) != supplied["archive_sha256"]:
        raise ValueError("Sites deployment archive hash is stale")
    member_bytes = _archive_member_bytes(archive_path, supplied["binding_member"])
    try:
        archived_binding = json.loads(member_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Sites archive binding is invalid JSON") from exc
    if archived_binding != binding:
        raise ValueError("Sites archive does not contain the current Vera binding")
    if supplied["site_payload_member"] != binding["site_payload_member"]:
        raise ValueError("Sites archive payload member does not match the binding")
    payload_bytes = _archive_member_bytes(
        archive_path,
        supplied["site_payload_member"],
        max_size=128 * 1024 * 1024,
    )
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    if (
        payload_sha256 != supplied["site_payload_sha256"]
        or payload_sha256 != binding["site_payload_sha256"]
    ):
        raise ValueError("Sites archive payload hash is stale")
    if _site_payload_inventory(payload_bytes) != manifest["files"]:
        raise ValueError("Sites archive payload differs from the approved website")
    binding_member = PurePosixPath(supplied["binding_member"])
    dist_root = binding_member.parent.parent
    expected_payload_member = dist_root / ".openai/vera-site-package.zip"
    if PurePosixPath(supplied["site_payload_member"]) != expected_payload_member:
        raise ValueError("Sites binding and payload are not in the same dist archive")
    hosting_bytes = _archive_member_bytes(
        archive_path,
        (dist_root / ".openai/hosting.json").as_posix(),
    )
    try:
        archived_hosting = json.loads(hosting_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Sites archive hosting metadata is invalid JSON") from exc
    if archived_hosting.get("project_id") != binding["project_id"]:
        raise ValueError("Sites archive hosting project does not match the binding")
    server_bytes = _archive_member_bytes(
        archive_path,
        (dist_root / "server/index.js").as_posix(),
        max_size=64 * 1024 * 1024,
    )
    if not server_bytes:
        raise ValueError("Sites deployment server bundle is empty")
    receipt = dict(supplied)
    receipt["archive_path"] = str(archive_path)
    receipt.update(
        {
            "confirmed_by": confirmed_by,
            "confirmed_by_user": True,
            "recorded_at": _utc_now(),
            "binding_digest": binding["binding_digest"],
            "browser_review_digest": _digest_payload(browser_review),
        }
    )
    receipt["receipt_digest"] = _digest_payload(receipt)
    state_path = _run_file(run_dir, "run_state.json")
    state = _load_json(state_path)
    state["deliveries"].append(receipt)
    state["status"] = "published" if kind == "release" else "preview_published"
    _write_json(state_path, state)
    output = _run_file(run_dir, f"sites_{kind}_delivery_receipt.json")
    _write_json(output, receipt)
    return output


def _verify_sites_receipt(
    run_dir: Path,
    receipt: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    """Recheck a Sites receipt, its binding, and its retained archive evidence."""

    schema_payload = {key: receipt.get(key) for key in SITES_DELIVERY_FIELDS}
    _validate_schema(schema_payload, "sites_delivery.schema.json")
    kind = schema_payload["kind"]
    route_name = "preview_publication" if kind == "preview" else "final_publication"
    route = _selected_route(run_dir, route_name)
    if (
        not route["selected"]
        or not route["approved_by_user"]
        or route["provider"] != "sites"
        or route["destination"] != schema_payload["destination"]
    ):
        raise ValueError("Sites receipt no longer matches the selected route")
    binding = _verified_sites_binding(run_dir, kind, manifest)
    expected = {
        "project_id": binding["project_id"],
        "site_digest": manifest["site_digest"],
        "validation_digest": manifest["validation_digest"],
        "quality_assessment_digest": manifest["quality_assessment_digest"],
        "reviews_digest": manifest["reviews_digest"],
        "package_digest": manifest["package_digest"],
    }
    for key, value in expected.items():
        if schema_payload[key] != value:
            raise ValueError(f"Sites receipt {key} is stale")
    if receipt.get("binding_digest") != binding["binding_digest"]:
        raise ValueError("Sites receipt binding digest is stale")
    browser_review = schema_payload["browser_review"]
    if (
        browser_review["reviewed_url"] != schema_payload["deployed_url"]
        or browser_review["deployment_id"] != schema_payload["deployment_id"]
        or receipt.get("browser_review_digest") != _digest_payload(browser_review)
    ):
        raise ValueError("Sites receipt browser review is stale")
    _verify_viewport_evidence(
        run_dir,
        browser_review["viewports"],
        prefix="reviews/sites/",
    )
    archive_path = Path(schema_payload["archive_path"]).expanduser().resolve()
    if archive_path.is_symlink() or not archive_path.is_file():
        raise ValueError("Sites deployment archive is missing or unsafe")
    if _sha256_file(archive_path) != schema_payload["archive_sha256"]:
        raise ValueError("Sites deployment archive hash is stale")
    member_bytes = _archive_member_bytes(
        archive_path,
        schema_payload["binding_member"],
    )
    try:
        archived_binding = json.loads(member_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Sites archive binding is invalid JSON") from exc
    if archived_binding != binding:
        raise ValueError("Sites archive binding is stale")
    if schema_payload["site_payload_member"] != binding["site_payload_member"]:
        raise ValueError("Sites archive payload member is stale")
    payload_bytes = _archive_member_bytes(
        archive_path,
        schema_payload["site_payload_member"],
        max_size=128 * 1024 * 1024,
    )
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    if (
        payload_sha256 != schema_payload["site_payload_sha256"]
        or payload_sha256 != binding["site_payload_sha256"]
    ):
        raise ValueError("Sites archive payload hash is stale")
    if _site_payload_inventory(payload_bytes) != manifest["files"]:
        raise ValueError("Sites archive payload differs from the approved website")
    binding_member = PurePosixPath(schema_payload["binding_member"])
    dist_root = binding_member.parent.parent
    if PurePosixPath(schema_payload["site_payload_member"]) != (
        dist_root / ".openai/vera-site-package.zip"
    ):
        raise ValueError("Sites binding and payload archive locations are stale")
    hosting_bytes = _archive_member_bytes(
        archive_path,
        (dist_root / ".openai/hosting.json").as_posix(),
    )
    try:
        archived_hosting = json.loads(hosting_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Sites archive hosting metadata is invalid JSON") from exc
    if archived_hosting.get("project_id") != binding["project_id"]:
        raise ValueError("Sites archive hosting project is stale")
    if not _archive_member_bytes(
        archive_path,
        (dist_root / "server/index.js").as_posix(),
        max_size=64 * 1024 * 1024,
    ):
        raise ValueError("Sites deployment server bundle is empty")


def validate_run(run_dir: Path) -> dict[str, Any]:
    """Return workflow status after recomputing every exact-byte dependency."""

    state = _load_json(_run_file(run_dir, "run_state.json"))
    issues: list[str] = []
    current_digest: str | None = None
    try:
        current_digest, _ = _site_digest(_run_file(run_dir, "work/site"))
    except (OSError, ValueError) as exc:
        issues.append(str(exc))
    if current_digest and state.get("current_site_digest") != current_digest:
        issues.append("current site bytes changed after validation")
    try:
        _verified_intake_and_sources(run_dir)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        issues.append(str(exc))
    try:
        _verified_brief(run_dir)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        issues.append(str(exc))
    validation: dict[str, Any] | None = None
    try:
        validation = _verified_validation(run_dir)
        if validation["status"] != "ready":
            issues.append("mechanical site validation is blocked")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        issues.append(str(exc))
    quality: dict[str, Any] | None = None
    if validation is not None:
        try:
            quality = _verified_quality(run_dir, validation)
            if quality["assessment"]["verdict"] != "ready":
                issues.append("rendered quality assessment is not ready")
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            issues.append(str(exc))
    else:
        issues.append("quality assessment cannot be verified")
    try:
        _review_events(run_dir)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        issues.append(str(exc))
    for kind in sorted(state.get("packages", {})):
        try:
            _verify_current_package(run_dir, kind)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            issues.append(f"{kind} package is stale or invalid: {exc}")
    for kind in sorted(state.get("sites_bindings", {})):
        try:
            manifest, _ = _verify_current_package(run_dir, kind)
            _verified_sites_binding(run_dir, kind, manifest)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            issues.append(f"{kind} Sites binding is stale or invalid: {exc}")
    current_delivery_kinds: set[str] = set()
    for receipt in state.get("deliveries", []):
        if not isinstance(receipt, dict):
            issues.append("delivery receipt is invalid")
            continue
        recorded_digest = receipt.get("receipt_digest")
        receipt_payload = dict(receipt)
        receipt_payload.pop("receipt_digest", None)
        if recorded_digest != _digest_payload(receipt_payload):
            issues.append("delivery receipt digest is invalid")
            continue
        try:
            _require_nonempty(str(receipt.get("destination", "")), "destination")
            _require_nonempty(str(receipt.get("confirmed_by", "")), "confirmed_by")
            visible = receipt.get("deployed_url", receipt.get("visible_receipt", ""))
            _require_nonempty(str(visible), "visible_receipt")
            manifest, _ = _verify_current_package(run_dir, str(receipt["kind"]))
            if receipt.get("provider") == "sites":
                _verify_sites_receipt(run_dir, receipt, manifest)
            else:
                route_name = (
                    "preview_publication"
                    if receipt["kind"] == "preview"
                    else "final_publication"
                )
                route = _selected_route(run_dir, route_name)
                if (
                    not route["selected"]
                    or not route["approved_by_user"]
                    or route["provider"] != receipt.get("provider")
                    or route["destination"] != receipt.get("destination")
                ):
                    raise ValueError(
                        "delivery receipt no longer matches the selected route"
                    )
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            issues.append(f"delivery receipt is stale or invalid: {exc}")
            continue
        if receipt.get("package_digest") != manifest["package_digest"]:
            issues.append("delivery receipt package digest is stale")
            continue
        current_delivery_kinds.add(str(receipt["kind"]))
    if state.get("status") == "published" and "release" not in current_delivery_kinds:
        issues.append("published status lacks a current release receipt")
    if (
        state.get("status") == "preview_published"
        and "preview" not in current_delivery_kinds
    ):
        issues.append("preview-published status lacks a current preview receipt")
    derived_status = state["status"]
    if "release" in current_delivery_kinds:
        derived_status = "published"
    elif "preview" in current_delivery_kinds:
        derived_status = "preview_published"
    return {
        "schema_version": 1,
        "run_id": state["run_id"],
        "status": derived_status if not issues else "blocked",
        "site_digest": current_digest,
        "issues": sorted(set(issues)),
        "valid": not issues,
    }
