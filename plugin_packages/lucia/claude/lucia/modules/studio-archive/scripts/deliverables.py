"""Atomic, pipeline-independent publication of named deliverables and revisions."""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

__all__ = ["Deliverables"]
_KEY = re.compile(r"[a-z][a-z0-9-]{0,79}")
_DESKTOP_METADATA = {".DS_Store", "Thumbs.db", "desktop.ini"}


class Deliverables:
    """One stable result entry, with complete issued versions and grouped formats."""

    def __init__(self, ledger: ModuleType) -> None:
        self.ledger = ledger

    def key(self, value: str) -> str:
        return self.ledger._identifier(value, label="deliverable key", pattern=_KEY)

    def directory(self, root: Path, eid: str) -> Path:
        self.ledger.load_engagement_manifest(root, eid)
        return self.ledger._engagement_root(root.resolve(), eid) / "deliverables"

    def entry(
        self, root: Path, eid: str, key: str, *, verify_bytes: bool = True
    ) -> dict[str, Any]:
        """Read only explicitly issued revisions; staged drafts never count."""
        self.key(key)
        directory = self.directory(root, eid) / key
        versions = []
        if directory.exists() or directory.is_symlink():
            self.ledger._ordinary_directory(directory, label="deliverable entry")
            previous = ""
            for folder in sorted(directory.iterdir()):
                if (
                    folder.name.startswith(".saving-")
                    or folder.name in _DESKTOP_METADATA
                ):
                    continue
                self.ledger._ordinary_directory(folder, label="deliverable revision")
                value = self.ledger._validate_seal(
                    self.ledger._read_json(
                        folder / "receipt.json", label="issued result"
                    ),
                    label="issued result",
                )
                required = {
                    "schema_version",
                    "client_id",
                    "engagement_id",
                    "entry_key",
                    "revision",
                    "label",
                    "issued_at",
                    "formats",
                    "previous_revision",
                    "request_key",
                    "request_sha256",
                    "content_sha256",
                }
                if (
                    set(value) != required
                    or value["schema_version"] != "vera.deliverable.v1"
                    or value["client_id"]
                    != self.ledger.load_client_manifest(root)["client_id"]
                    or value["engagement_id"] != eid
                    or value["entry_key"] != key
                    or type(value["revision"]) is not int
                    or value["revision"] != len(versions) + 1
                    or folder.name != f"{value['revision']:06d}"
                    or value["previous_revision"] != previous
                ):
                    raise self.ledger.LedgerError(
                        "Deliverable revision chain is invalid"
                    )
                self.ledger._text(
                    value["label"], label="deliverable label", maximum=200
                )
                self.ledger._text(value["issued_at"], label="issued date", maximum=80)
                self.ledger._text(
                    value["request_key"], label="publication request", maximum=200
                )
                if (
                    not isinstance(value["formats"], list)
                    or not 1 <= len(value["formats"]) <= 30
                ):
                    raise self.ledger.LedgerError("Deliverable formats are invalid")
                names, formats = set(), set()
                for item in value["formats"]:
                    if not isinstance(item, dict) or set(item) - {
                        "legacy_input_id"
                    } != {
                        "format",
                        "name",
                        "sha256",
                        "byte_count",
                    }:
                        raise self.ledger.LedgerError("Invalid issued format")
                    if "legacy_input_id" in item:
                        self.ledger._identifier(
                            item["legacy_input_id"],
                            label="legacy output input",
                            pattern=self.ledger._INPUT_ID_RE,
                        )
                    self.key(item["format"])
                    self.ledger._validate_imported_names([item["name"]])
                    self.ledger._identifier(
                        item["sha256"],
                        label="format digest",
                        pattern=self.ledger._SHA256_RE,
                    )
                    if (
                        item["format"] in formats
                        or item["name"].casefold() in names
                        or type(item["byte_count"]) is not int
                        or item["byte_count"] < 0
                    ):
                        raise self.ledger.LedgerError(
                            "Duplicate format or invalid byte count"
                        )
                    names.add(item["name"].casefold())
                    formats.add(item["format"])
                    if verify_bytes and self.ledger._stable_file_identity(
                        folder / item["name"], label="issued format"
                    ) != (item["byte_count"], item["sha256"]):
                        raise self.ledger.LedgerError("Issued result bytes changed")
                previous = value["content_sha256"]
                versions.append(value)
        return {
            "entry_key": key,
            "label": versions[-1]["label"] if versions else key,
            "current_revision": len(versions),
            "versions": versions,
        }

    def publish(
        self,
        root: Path,
        eid: str,
        key: str,
        label: str,
        files: list[dict[str, str]],
        expected_revision: int,
        request_key: str,
    ) -> dict[str, Any]:
        """Commit all formats together; retries cannot duplicate or roll back a version."""
        self.key(key)
        self.ledger._text(label, label="deliverable label", maximum=200)
        self.ledger._text(request_key, label="publication request", maximum=200)
        if (
            type(expected_revision) is not int
            or expected_revision < 0
            or not isinstance(files, list)
            or not 1 <= len(files) <= 30
        ):
            raise self.ledger.LedgerError(
                "Select complete formats and the current revision"
            )
        selected = []
        names, formats = set(), set()
        for item in files:
            if not isinstance(item, dict) or set(item) - {"legacy_input_id"} != {
                "format",
                "source_path",
                "sha256",
            }:
                raise self.ledger.LedgerError(
                    "Select an exact format, source path and digest"
                )
            if "legacy_input_id" in item:
                self.ledger._identifier(
                    item["legacy_input_id"],
                    label="legacy output input",
                    pattern=self.ledger._INPUT_ID_RE,
                )
            self.key(item["format"])
            self.ledger._identifier(
                item["sha256"], label="format digest", pattern=self.ledger._SHA256_RE
            )
            path = Path(item["source_path"]).expanduser()
            if not path.is_absolute():
                raise self.ledger.LedgerError("Result source must be absolute")
            self.ledger._validate_imported_names([path.name])
            if item["format"] in formats or path.name.casefold() in names:
                raise self.ledger.LedgerError(
                    "Use one file per format and distinct filenames"
                )
            names.add(path.name.casefold())
            formats.add(item["format"])
            selected.append(
                {
                    "format": item["format"],
                    "name": path.name,
                    "sha256": item["sha256"],
                    "source_path": str(path),
                    **(
                        {"legacy_input_id": item["legacy_input_id"]}
                        if "legacy_input_id" in item
                        else {}
                    ),
                }
            )
        selected.sort(key=lambda item: item["format"])
        # The source's temporary location is not part of the issued byte identity.
        request_sha = self.ledger._canonical_json_sha256(
            {
                "entry_key": key,
                "label": label,
                "files": [
                    {k: v for k, v in item.items() if k != "source_path"}
                    for item in selected
                ],
                "expected_revision": expected_revision,
            }
        )
        with self.ledger._engagement_lock(root, eid):
            current = self.entry(root, eid, key, verify_bytes=False)
            for version in current["versions"]:
                if version["request_key"] == request_key:
                    if version["request_sha256"] != request_sha:
                        raise self.ledger.LedgerError(
                            "Publication retry key was reused for different work"
                        )
                    return {
                        "saved": True,
                        "reused": True,
                        "issued": version,
                        "current_revision": current["current_revision"],
                    }
            if current["current_revision"] != expected_revision:
                raise self.ledger.LedgerError(
                    "Result changed in another chat; reload before publishing"
                )
            if self.ledger.load_engagement_manifest(root, eid)["status"] != "open":
                raise self.ledger.LedgerError("Cannot publish into a closed incarico")
            if not self.ledger.incarichi().read(root, eid)["workflow_id"]:
                raise self.ledger.LedgerError(
                    "Bind the requested work before publishing its results"
                )
            parent = self.ledger._ordinary_directory(
                self.directory(root, eid), label="deliverables", create=True
            )
            parent = self.ledger._ordinary_directory(
                parent / key, label="deliverable entry", create=True
            )
            staging = Path(tempfile.mkdtemp(prefix=".saving-", dir=parent))
            try:
                issued_formats = []
                for item in selected:
                    path = Path(item["source_path"])
                    if "legacy_input_id" in item:
                        receipt = self.ledger.load_input_receipt(
                            root, eid, item["legacy_input_id"]
                        )
                        if (
                            Path(receipt["path"]) != path
                            or receipt["sha256"] != item["sha256"]
                        ):
                            raise self.ledger.LedgerError(
                                "Legacy output selection differs from its original receipt"
                            )
                    if path.resolve(strict=True) != path:
                        raise self.ledger.LedgerError(
                            "Result source cannot contain symbolic links"
                        )
                    size, digest = self.ledger._stable_copy(
                        path, staging / item["name"]
                    )
                    if digest != item["sha256"]:
                        raise self.ledger.LedgerError("Result changed while publishing")
                    issued_formats.append(
                        {
                            "format": item["format"],
                            "name": item["name"],
                            "sha256": digest,
                            "byte_count": size,
                            **(
                                {"legacy_input_id": item["legacy_input_id"]}
                                if "legacy_input_id" in item
                                else {}
                            ),
                        }
                    )
                version = self.ledger._sealed(
                    {
                        "schema_version": "vera.deliverable.v1",
                        "client_id": self.ledger.load_client_manifest(root)[
                            "client_id"
                        ],
                        "engagement_id": eid,
                        "entry_key": key,
                        "revision": expected_revision + 1,
                        "label": label,
                        "issued_at": self.ledger._now_iso(),
                        "formats": issued_formats,
                        "previous_revision": (
                            current["versions"][-1]["content_sha256"]
                            if current["versions"]
                            else ""
                        ),
                        "request_key": request_key,
                        "request_sha256": request_sha,
                    }
                )
                self.ledger._write_json(staging / "receipt.json", version)
                staging.rename(parent / f"{version['revision']:06d}")
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
            return {
                "saved": True,
                "reused": False,
                "issued": version,
                "current_revision": version["revision"],
            }

    def document(
        self, root: Path, eid: str, reference: dict[str, Any]
    ) -> dict[str, Any]:
        """Open exactly one format of an explicitly issued result revision."""
        if (
            set(reference) != {"entry_key", "revision", "format"}
            or type(reference["revision"]) is not int
            or reference["revision"] < 1
        ):
            raise self.ledger.LedgerError("Invalid deliverable reference")
        self.key(reference["format"])
        entry = self.entry(root, eid, reference["entry_key"], verify_bytes=False)
        version = next(
            (v for v in entry["versions"] if v["revision"] == reference["revision"]),
            None,
        )
        item = (
            next(
                (v for v in version["formats"] if v["format"] == reference["format"]),
                None,
            )
            if version
            else None
        )
        if item is None:
            raise self.ledger.LedgerError("Selected issued format does not exist")
        path = (
            self.directory(root, eid)
            / entry["entry_key"]
            / f"{version['revision']:06d}"
            / item["name"]
        )
        if self.ledger._stable_file_identity(path, label="issued format") != (
            item["byte_count"],
            item["sha256"],
        ):
            raise self.ledger.LedgerError("Issued result bytes changed")
        return {
            **item,
            "reference": reference,
            "label": version["label"],
            "path": str(path),
            "role": "result",
            "source_revision": version["content_sha256"],
            "issued_at": version["issued_at"],
        }

    def overview(self, root: Path, eid: str) -> dict[str, Any]:
        """Expose current entries and history without treating a bad file as absent."""
        parent = self.directory(root, eid)
        entries, issues = [], []
        if parent.exists() or parent.is_symlink():
            self.ledger._ordinary_directory(parent, label="deliverables")
            for folder in sorted(parent.iterdir()):
                if folder.name in _DESKTOP_METADATA:
                    continue
                try:
                    entry = self.entry(root, eid, folder.name, verify_bytes=False)
                    if not entry["versions"]:
                        continue
                    for version in entry["versions"]:
                        for item in version["formats"]:
                            item["reference"] = {
                                "entry_key": entry["entry_key"],
                                "revision": version["revision"],
                                "format": item["format"],
                            }
                            try:
                                path = (
                                    folder / f"{version['revision']:06d}" / item["name"]
                                )
                                item["available"] = self.ledger._stable_file_identity(
                                    path, label="issued format"
                                ) == (item["byte_count"], item["sha256"])
                            except (self.ledger.LedgerError, OSError):
                                item["available"] = False
                    entries.append(entry)
                except (self.ledger.LedgerError, OSError):
                    issues.append({"entry_key": folder.name, "available": False})
        return {"deliverables": entries, "deliverable_issues": issues}
