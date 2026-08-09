"""Deterministic workflow controls for professional-studio websites."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
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
    "record_site_brief",
    "validate_run",
    "validate_site",
]

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = PLUGIN_ROOT / "schemas"
WORKSPACE_MANIFEST = ".presenza-digitale-studio.json"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER_PATTERN = re.compile(r"\b(?:TODO|FIXME|lorem ipsum)\b", re.IGNORECASE)
REVIEW_SCOPES = {
    "identity_and_claims",
    "responsive_preview",
    "publication_destination",
}


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


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


def _inside_git_workspace(path: Path) -> bool:
    return any((candidate / ".git").exists() for candidate in (path, *path.parents))


def _assert_private_workspace(path: Path) -> Path:
    resolved = path.expanduser().resolve()
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

    root = _assert_private_workspace(workspace)
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


def prepare_run(workspace: Path, intake_path: Path) -> Path:
    """Validate intake, snapshot selected files, and create one immutable run."""

    root = _workspace_root(workspace)
    intake = _load_json(intake_path.expanduser().resolve())
    _validate_schema(intake, "website_intake.schema.json")
    source_ids = [item["id"] for item in intake["selected_files"]]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Selected file IDs must be unique")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:10]
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
            target.chmod(0o600)
            source_register.append(
                {
                    "id": item["id"],
                    "role": item["role"],
                    "original_path": str(source_path),
                    "snapshot_path": str(target.relative_to(staging)),
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
                "packages": {},
                "deliveries": [],
            },
        )
        for relative in ("work/site", "reviews", "packages"):
            (staging / relative).mkdir(parents=True, mode=0o700)
        staging.replace(run_dir)
    except (OSError, ValueError, json.JSONDecodeError):
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return run_dir


def _run_file(run_dir: Path, name: str) -> Path:
    root = run_dir.expanduser().resolve()
    if not (root / "run_state.json").is_file():
        raise ValueError("Run directory is not prepared")
    return root / name


def _source_ids(run_dir: Path) -> set[str]:
    register = _load_json(_run_file(run_dir, "source_register.json"))
    return {str(item["id"]) for item in register["sources"]}


def record_site_brief(
    run_dir: Path,
    brief_path: Path,
    *,
    provider: str,
    model: str,
    recorded_by: str,
) -> Path:
    """Validate and bind one model-led website brief to prepared evidence."""

    brief = _load_json(brief_path.expanduser().resolve())
    _validate_schema(brief, "site_brief.schema.json")
    intake = _load_json(_run_file(run_dir, "run_intake.json"))
    if brief["mode"] != intake["mode"]:
        raise ValueError("Brief mode does not match intake mode")
    known_sources = _source_ids(run_dir)
    referenced: set[str] = set()
    for fact in brief["observed_facts"]:
        referenced.update(fact["source_ids"])
    for field in brief["studio_profile"]:
        referenced.update(field["evidence_ids"])
    for claim in brief["claims"]:
        referenced.update(claim["evidence_ids"])
    unknown = sorted(referenced - known_sources)
    if unknown:
        raise ValueError(f"Brief references unknown source IDs: {', '.join(unknown)}")
    state = _load_json(_run_file(run_dir, "run_state.json"))
    record = {
        "schema_version": 1,
        "brief": brief,
        "brief_digest": _digest_payload(brief),
        "intake_digest": state["intake_digest"],
        "provenance": {
            "provider": provider,
            "model": model,
            "recorded_by": recorded_by,
            "recorded_at": _utc_now(),
        },
    }
    output = _run_file(run_dir, "site_brief_record.json")
    _write_json(output, record)
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
        self.images_missing_alt = 0
        self.viewport = False
        self.noindex = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "html":
            self.html_lang = values.get("lang")
        if tag == "title":
            self.title_depth += 1
        if tag == "h1":
            self.h1_count += 1
        if values.get("id"):
            self.ids.append(str(values["id"]))
        if tag == "img" and "alt" not in values:
            self.images_missing_alt += 1
        if tag == "meta" and str(values.get("name", "")).lower() == "viewport":
            self.viewport = bool(values.get("content"))
        if tag == "meta" and str(values.get("name", "")).lower() == "robots":
            self.noindex = "noindex" in str(values.get("content", "")).lower()
        attr_name = (
            "href"
            if tag in {"a", "link"}
            else "src" if tag in {"img", "script", "source"} else None
        )
        if attr_name and values.get(attr_name):
            value = str(values[attr_name])
            self.references.append((tag, value))
            if tag == "a" and value.startswith("#") and len(value) > 1:
                self.fragment_references.append(value[1:])

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self.title_depth:
            self.title_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.title_depth:
            self.title_text.append(data)


def _site_inventory(site_dir: Path) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for path in sorted(item for item in site_dir.rglob("*") if item.is_file()):
        if path.is_symlink():
            raise ValueError(f"Site package contains a symlink: {path}")
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


def validate_site(run_dir: Path) -> Path:
    """Run deterministic HTML and package-integrity checks."""

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
        external_assets: list[str] = []
        for tag, value in parser.references:
            scheme = urlparse(value).scheme.lower()
            if scheme == "javascript":
                page_errors.append(f"unsafe javascript reference: {value}")
                continue
            if scheme == "http":
                page_errors.append(f"insecure http reference: {value}")
                continue
            if scheme == "https" and tag in {"img", "link", "script", "source"}:
                external_assets.append(value)
                continue
            try:
                target = _local_target(site_dir, path, value)
            except ValueError as exc:
                page_errors.append(str(exc))
                continue
            if target is not None and not target.exists():
                page_errors.append(f"missing local target: {value}")
        if external_assets:
            warnings.append(
                f"{relative}: {len(external_assets)} external asset reference(s)"
            )
        errors.extend(f"{relative}: {message}" for message in page_errors)
        pages.append(
            {
                "path": relative,
                "h1_count": parser.h1_count,
                "noindex": parser.noindex,
                "external_assets": external_assets,
                "errors": page_errors,
            }
        )
    report: dict[str, Any] = {
        "schema_version": 1,
        "validated_at": _utc_now(),
        "site_digest": site_digest,
        "inventory": inventory,
        "status": "ready" if not errors else "blocked",
        "errors": errors,
        "warnings": warnings,
        "pages": pages,
    }
    report["validation_digest"] = _digest_payload(report)
    output = _run_file(run_dir, "site_validation.json")
    _write_json(output, report)
    state_path = _run_file(run_dir, "run_state.json")
    state = _load_json(state_path)
    if state.get("current_site_digest") != site_digest:
        state["reviews"] = {}
        state["packages"] = {}
        state["deliveries"] = []
    state["current_site_digest"] = site_digest
    state["validation_digest"] = report["validation_digest"]
    state["status"] = "site_validated" if not errors else "blocked"
    _write_json(state_path, state)
    return output


def record_quality_assessment(
    run_dir: Path,
    assessment_path: Path,
    *,
    provider: str,
    model: str,
    recorded_by: str,
) -> Path:
    """Record model-led review of the exact rendered responsive site."""

    assessment = _load_json(assessment_path.expanduser().resolve())
    _validate_schema(assessment, "quality_assessment.schema.json")
    validation = _load_json(_run_file(run_dir, "site_validation.json"))
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
    state["quality_assessment_digest"] = record["assessment_digest"]
    state["status"] = (
        "quality_ready" if assessment["verdict"] == "ready" else assessment["verdict"]
    )
    _write_json(state_path, state)
    return output


def _current_ready_site(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    validation = _load_json(_run_file(run_dir, "site_validation.json"))
    quality = _load_json(_run_file(run_dir, "quality_assessment_record.json"))
    if validation["status"] != "ready":
        raise ValueError("Mechanical site validation is not ready")
    if quality["assessment"]["verdict"] != "ready":
        raise ValueError("Rendered quality assessment is not ready")
    if quality["assessment"]["site_digest"] != validation["site_digest"]:
        raise ValueError("Rendered quality assessment is stale")
    return validation, quality


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
    validation, quality = _current_ready_site(run_dir)
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
    }
    payload["events"].append(event)
    _write_json(review_path, payload)
    return review_path


def _accepted_scopes(run_dir: Path, site_digest: str) -> set[str]:
    review_path = _run_file(run_dir, "reviews/review_log.json")
    if not review_path.exists():
        return set()
    decisions: dict[str, str] = {}
    for event in _load_json(review_path)["events"]:
        if event["site_digest"] == site_digest:
            decisions[event["scope"]] = event["decision"]
    return {scope for scope, decision in decisions.items() if decision == "accepted"}


def _selected_route(run_dir: Path, route: str) -> dict[str, Any]:
    intake = _load_json(_run_file(run_dir, "run_intake.json"))
    return dict(intake["external_routes"][route])


def package_website(run_dir: Path, *, kind: str) -> Path:
    """Package exact preview or release bytes after required gates."""

    if kind not in {"preview", "release"}:
        raise ValueError("Package kind must be preview or release")
    validation, quality = _current_ready_site(run_dir)
    site_digest = validation["site_digest"]
    if kind == "preview":
        route = _selected_route(run_dir, "preview_publication")
        if not route["selected"] or not route["approved_by_user"]:
            raise ValueError("Preview publication route was not selected")
        pages_without_noindex = [
            page["path"] for page in validation["pages"] if not page["noindex"]
        ]
        if pages_without_noindex:
            raise ValueError(
                "Preview pages must include noindex: "
                + ", ".join(pages_without_noindex)
            )
    else:
        missing = REVIEW_SCOPES - _accepted_scopes(run_dir, site_digest)
        if missing:
            raise ValueError("Release reviews missing: " + ", ".join(sorted(missing)))

    package_dir = _run_file(run_dir, f"packages/{kind}-{site_digest[:12]}")
    manifest_path = package_dir / "package_manifest.json"
    if package_dir.exists():
        if not manifest_path.is_file():
            raise ValueError(f"Existing package is incomplete: {package_dir}")
        return manifest_path
    package_dir.mkdir(mode=0o700)
    output_site = package_dir / "site"
    shutil.copytree(_run_file(run_dir, "work/site"), output_site)
    inventory = _site_inventory(output_site)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": kind,
        "created_at": _utc_now(),
        "site_digest": site_digest,
        "validation_digest": validation["validation_digest"],
        "quality_assessment_digest": quality["assessment_digest"],
        "files": inventory,
    }
    manifest["package_digest"] = _digest_payload(manifest)
    _write_json(manifest_path, manifest)
    state_path = _run_file(run_dir, "run_state.json")
    state = _load_json(state_path)
    state["packages"][kind] = {
        "manifest": str(manifest_path.relative_to(run_dir.resolve())),
        "site_digest": site_digest,
        "package_digest": manifest["package_digest"],
    }
    state["status"] = "preview_ready" if kind == "preview" else "release_ready"
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
    route_name = "preview_publication" if kind == "preview" else "final_publication"
    route = _selected_route(run_dir, route_name)
    if not route["selected"] or not route["approved_by_user"]:
        raise ValueError(f"{route_name} route was not selected")
    if destination != route["destination"]:
        raise ValueError("Delivery destination does not match the selected route")
    state_path = _run_file(run_dir, "run_state.json")
    state = _load_json(state_path)
    package = state.get("packages", {}).get(kind)
    if not package:
        raise ValueError(f"No current {kind} package exists")
    manifest = _load_json(_run_file(run_dir, package["manifest"]))
    if manifest["package_digest"] != package["package_digest"]:
        raise ValueError("Package manifest digest is stale")
    receipt = {
        "schema_version": 1,
        "kind": kind,
        "destination": destination,
        "visible_receipt": visible_receipt,
        "confirmed_by": confirmed_by,
        "confirmed_by_user": True,
        "recorded_at": _utc_now(),
        "site_digest": package["site_digest"],
        "package_digest": package["package_digest"],
    }
    state["deliveries"].append(receipt)
    state["status"] = "published" if kind == "release" else "preview_published"
    _write_json(state_path, state)
    output = _run_file(run_dir, f"{kind}_delivery_receipt.json")
    _write_json(output, receipt)
    return output


def validate_run(run_dir: Path) -> dict[str, Any]:
    """Return current workflow status after recomputing exact site integrity."""

    state = _load_json(_run_file(run_dir, "run_state.json"))
    site_dir = _run_file(run_dir, "work/site")
    current_digest, _ = _site_digest(site_dir)
    issues: list[str] = []
    if state.get("current_site_digest") != current_digest:
        issues.append("current site bytes changed after validation")
    validation_path = _run_file(run_dir, "site_validation.json")
    if not validation_path.exists():
        issues.append("site validation is missing")
    quality_path = _run_file(run_dir, "quality_assessment_record.json")
    if not quality_path.exists():
        issues.append("quality assessment is missing")
    for kind, package in state.get("packages", {}).items():
        manifest_path = _run_file(run_dir, package["manifest"])
        if not manifest_path.exists():
            issues.append(f"{kind} package manifest is missing")
            continue
        manifest = _load_json(manifest_path)
        if manifest.get("site_digest") != current_digest:
            issues.append(f"{kind} package is stale")
        recorded_digest = manifest.pop("package_digest", None)
        if recorded_digest != _digest_payload(manifest):
            issues.append(f"{kind} package digest is invalid")
    return {
        "schema_version": 1,
        "run_id": state["run_id"],
        "status": state["status"] if not issues else "blocked",
        "site_digest": current_digest,
        "issues": issues,
        "valid": not issues,
    }
